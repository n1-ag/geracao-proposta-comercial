"""Catalogar, pela tela, um item que foi cotado fora do catálogo.

Item fora do catálogo apareceu em todas as seis propostas que este app gerou, e
nenhum foi incorporado — o único caminho era um comando de terminal. Enquanto
isso o alerta `ITEM_NAO_CATALOGADO` fica aceso a cada rodada e o catálogo não
aprende com o que já foi vendido.

O Sonnet propõe os campos a partir do que a proposta já sabe; uma pessoa revisa;
o script grava. A regra de que nenhum agente escreve em `dados/` continua de pé:
quem escreve é `scripts/catalogar.py`, com o que foi aprovado na tela.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys

import aplicador
import config as cfg
import db
import modelo
import workspace as ws
from api_propostas import carregar
from roteador import erro_400, erro_409, rota

sys.path.insert(0, str(cfg.SCRIPTS))

MODELO_PROPOSTA = "sonnet"
TETO_USD = float(os.environ.get("N1_TETO_CATALOGO_USD", "1.0"))
TIMEOUT_S = 120

SISTEMA = """\
Você propõe a ficha de catálogo de um serviço que a N1 acabou de cotar fora do
catálogo. Alguém vai revisar e corrigir na tela antes de gravar — proponha bem,
mas não tente acertar sozinho o que depende de decisão comercial.

Responda **somente** com um objeto JSON. Sem preâmbulo, sem markdown, sem crases.

```
{"id":"kebab-case-unico","nome":"...","categoria":"...","unidade":"...",
 "horas_baixa":[n,n],"horas_media":[n,n],"horas_alta":[n,n],
 "criterio_complexidade":"baixa: ...;\\nmedia: ...;\\nalta: ...",
 "descricao_proposta":"..."}
```

- `categoria`: uma de conteudo, componente, integracao, migracao, seo, apoio.
  Manutenção e correção de coisa existente é `apoio`. Página nova é `conteudo`.
- `unidade`: o que se conta. página, componente, integração, template, projeto.
- As três faixas são [mínimo, máximo] de horas, crescentes entre si. Ancore-as na
  estimativa desta cotação: ela é um caso real, e costuma ser o meio da faixa
  média. Não invente ordens de grandeza distantes dela.
- `criterio_complexidade` é o texto que o agente de escopo vai ler para decidir a
  complexidade de futuras cotações. Escreva três linhas concretas, com o que
  distingue uma da outra — "media: escopo típico" não ajuda ninguém. Fale de
  causa, dependência, quantidade, integração.
- `descricao_proposta` é a frase que vai ao cliente no PDF. Uma linha, sem
  jargão interno, sem preço, sem hora.
- O `id` não pode ser um destes, que já existem: <<IDS>>

Português do Brasil.
"""


def _catalogo_ids() -> list:
    import tomllib
    with open(cfg.DADOS_REPO / "catalogo-modulos.toml", "rb") as f:
        return [i["id"] for i in tomllib.load(f)["itens"]]


def _escopo(linha: dict) -> tuple[dict, object]:
    caminho = ws.caminho(linha["slug"]) / "proposta" / "02-escopo.json"
    if not caminho.is_file():
        raise erro_409("sem_escopo", "esta proposta ainda não tem escopo")
    return json.loads(caminho.read_text("utf-8")), caminho


def _achar_fora(escopo: dict, nome: str) -> dict | None:
    for i in escopo.get("itens_fora_catalogo", []):
        if (i.get("nome") or "").strip() == nome.strip():
            return i
    return None


@rota("POST", r"^/api/propostas/(?P<pid>\d+)/catalogar/propor$")
def propor(req, pid):
    """Sonnet lê o item cotado e propõe a ficha. Não grava nada."""
    linha = carregar(pid)
    nome = (req.json_do_corpo().get("nome") or "").strip()
    escopo, _ = _escopo(linha)

    item = _achar_fora(escopo, nome)
    if item is None:
        raise erro_400("item_desconhecido",
                       f"não achei '{nome}' entre os itens fora do catálogo")

    pergunta = (
        f"Serviço: {item['nome']}\n"
        f"Estimativa nesta cotação: {item.get('horas_estimadas')} horas\n"
        f"Por que não coube em nenhum item do catálogo:\n{item.get('justificativa') or '—'}"
    )
    sistema = SISTEMA.replace("<<IDS>>", ", ".join(_catalogo_ids()))

    cmd = [
        "claude", "-p", pergunta,
        "--output-format", "json",
        "--permission-mode", "default",
        "--setting-sources", "user,project",
        "--strict-mcp-config", "--mcp-config", '{"mcpServers":{}}',
        "--model", MODELO_PROPOSTA,
        "--max-budget-usd", str(TETO_USD),
        "--disallowedTools", "Read", "Write", "Edit", "Bash", "Glob", "Grep", "Agent",
        "--append-system-prompt", sistema,
    ]

    env = dict(os.environ)
    for chave in ("ANTHROPIC_MODEL", "ANTHROPIC_SMALL_FAST_MODEL", "CLAUDE_CODE_MODEL"):
        env.pop(chave, None)

    try:
        r = subprocess.run(cmd, cwd=cfg.RAIZ, capture_output=True, text=True,
                           timeout=TIMEOUT_S, env=env)
        envelope = json.loads(r.stdout)
    except (FileNotFoundError, subprocess.TimeoutExpired, json.JSONDecodeError):
        raise erro_409("falhou_propor", "não consegui montar a proposta de ficha") from None

    bruto = (envelope.get("result") or "").strip()
    if bruto.startswith("```"):
        bruto = re.sub(r"^```[a-z]*\n?|\n?```$", "", bruto).strip()
    try:
        ficha = json.loads(bruto)
    except json.JSONDecodeError:
        m = re.search(r"\{[\s\S]*\}", bruto)
        if not m:
            raise erro_409("falhou_propor", "a proposta de ficha veio ilegível") from None
        ficha = json.loads(m.group())

    ficha["_estimativa"] = item.get("horas_estimadas")
    return {"ficha": ficha, "custo_usd": float(envelope.get("total_cost_usd") or 0)}


@rota("POST", r"^/api/propostas/(?P<pid>\d+)/catalogar$")
def gravar(req, pid):
    """Grava a ficha revisada no catálogo e move o item para o escopo cotado."""
    linha = carregar(pid)
    corpo = req.json_do_corpo()
    ficha = corpo.get("ficha") or {}
    nome_original = (corpo.get("nome") or "").strip()

    if linha["status"] in modelo.EXECUTANDO or linha["status"] == "enfileirada":
        raise erro_409("ja_na_fila", "esta proposta está executando; espere terminar")

    escopo, caminho = _escopo(linha)
    item = _achar_fora(escopo, nome_original)
    if item is None:
        raise erro_400("item_desconhecido",
                       f"não achei '{nome_original}' entre os itens fora do catálogo")

    from catalogar import Recusa, catalogar

    try:
        gravado = catalogar(ficha)
    except Recusa as e:
        raise erro_400("catalogo_recusou", str(e)) from None

    # O item sai de `itens_fora_catalogo` e entra como cotado, com as horas da
    # estimativa: catalogar é organizar o catálogo, não renegociar o preço. O
    # total não pode se mexer por causa disso.
    escopo["itens_fora_catalogo"] = [
        i for i in escopo.get("itens_fora_catalogo", [])
        if (i.get("nome") or "").strip() != nome_original
    ]
    escopo.setdefault("itens", []).append({
        "catalogo_id": gravado["id"],
        "complexidade": None,
        "quantidade": 1,
        "rotulo": item["nome"],
        "design_pela_n1": True,
        "origem": item.get("origem") or ["catalogado no gate"],
        "observacao": item.get("justificativa", ""),
        "horas": int(item["horas_estimadas"]),
    })
    caminho.write_text(json.dumps(escopo, ensure_ascii=False, indent=2) + "\n", "utf-8")

    ok, mensagem = aplicador.reprecificar(linha)
    if not ok:
        raise erro_409("falhou_precificar", mensagem)

    db.evento(linha["id"], "item_catalogado",
              f"{gravado['id']} — {gravado['nome']} (era item fora do catálogo)")
    modelo.reabrir_para_gate(linha["id"], f"item '{gravado['nome']}' entrou no catálogo")

    import eventos
    atual = db.um("SELECT * FROM propostas WHERE id = ?", (linha["id"],))
    eventos.proposta(atual)
    return {"ok": True, "catalogo_id": gravado["id"], "total_fmt": atual["total_fmt"]}
