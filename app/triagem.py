"""Lê o pedido de ajuste em português e devolve operações que o Python executa.

O «Pedir ajuste» sempre aceitou qualquer texto, mas só uma fatia dele virava
ação — e em silêncio. Pedido de preço então era recusado por construção: o
prompt do agente proibia tocar em valor, e a recusa ia parar numa linha do
`02-escopo.md` que ninguém abre. O comercial escrevia seis pedidos, um
acontecia, e nada dizia qual.

Aqui o texto é **lido antes de qualquer coisa acontecer**. Vira uma lista de
operações estruturadas, o comercial confere na tela, e só então o Python executa.

**A regra da casa continua de pé.** "O LLM decide o quê; o Python decide quanto."
Este módulo não calcula nada: ele transcreve um número que uma pessoa escreveu
para dentro de um campo. Quem divide, multiplica e soma é o `precificar.py`, e o
que ele recebe passou pelos olhos de quem pediu.

Não lê arquivo nenhum: o escopo atual e o catálogo vão inteiros no prompt, em
forma compacta. Sem ferramenta, sem passeio pelo disco — uma pergunta, uma
resposta, poucos segundos.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import tomllib

import config as cfg

TETO_USD = float(os.environ.get("N1_TETO_TRIAGEM_USD", "1.0"))
TIMEOUT_S = 120
MODELO = "sonnet"

TIPOS = {
    "valor_total", "valor_item", "horas_item", "item_incluso", "remover_item",
    "acrescentar_item", "rotulo_item", "valor_base", "prazo", "evolucao_horas",
    "texto_livre",
}

SISTEMA = """\
Você traduz um pedido de ajuste, escrito em português corrido por um vendedor,
numa lista de operações que um programa vai executar. **Você não executa nada e
não calcula nada** — só entende o que foi pedido e nomeia a operação.

Responda **somente** com um array JSON. Sem preâmbulo, sem markdown, sem crases.

Cada operação tem `tipo`, `trecho` (o pedaço literal do texto que a originou) e
os campos do seu tipo:

- `valor_total`      — o total da proposta. `{"valor": 28000}`
- `valor_item`       — quanto a linha passa a valer, exato. `{"alvo": 0, "valor": 6000}`
- `horas_item`       — esforço de uma linha. `{"alvo": 0, "horas": 16}`
- `item_incluso`     — passa a valer sem custo. `{"alvo": 0}` ou `{"catalogo_id":"..."}` se ainda não estiver cotado
- `remover_item`     — tira do escopo. `{"alvo": 0}`
- `acrescentar_item` — `{"catalogo_id":"...","complexidade":"baixa|media|alta","quantidade":1,"rotulo":"..."}`
- `rotulo_item`      — muda o nome que o cliente lê. `{"alvo": 0, "rotulo":"..."}`
- `valor_base`       — substitui o valor base da plataforma. `{"valor": 0}`
- `prazo`            — `{"min": 10, "max": 12}`
- `evolucao_horas`   — pacote mensal de acompanhamento contratado. `{"horas": 20}`
- `texto_livre`      — o que não couber em nenhum tipo acima. `{"instrucao":"..."}`

Regras:
- **Número vem do texto, nunca de você.** "28 mil" → 28000. "6 mil" → 6000.
  "60k" → 60000. "R$ 18.000,00" → 18000. Não estime, não arredonde, não converta
  valor em hora: quem faz conta é o programa.
- **Pedido impreciso vira `texto_livre`**, não um chute. "próximo de 60 mil",
  "algo em torno de 30k", "um pouco mais barato" — não têm número, então não
  viram `valor_total`. Escreva na `instrucao` o que falta para poder aplicar.
- **Para mexer numa linha já cotada, use `alvo` com o número dela** (o `#0`,
  `#1`… da lista abaixo). Não use `catalogo_id`: a mesma proposta pode ter cinco
  linhas do mesmo tipo, e só o número distingue "Unidades de atendimento" de
  "Carreiras". O vendedor cita a linha pelo rótulo — traduza o rótulo no número.
- `catalogo_id` só em `acrescentar_item`, e em `item_incluso` de item que ainda
  não esteja na lista. Não invente id: se o pedido citar algo fora do catálogo,
  use `texto_livre`.
- Um pedido pode virar várias operações; um texto com cinco frases costuma virar
  cinco. Não junte, não resuma, não descarte.
- Frase que não pede mudança nenhuma (contexto, desabafo, agradecimento) você
  simplesmente ignora — não vire operação.
- Se o mesmo item aparecer com valor **e** com horas, prefira `horas_item`.

Escopo cotado hoje nesta proposta:
<<ITENS>>

Itens do catálogo disponíveis:
<<CATALOGO>>

Valor da hora: R$ <<HORA>>.
"""


def _catalogo() -> dict:
    with open(cfg.DADOS_REPO / "catalogo-modulos.toml", "rb") as f:
        return {i["id"]: i for i in tomllib.load(f)["itens"]}


def _valor_hora() -> float:
    with open(cfg.DADOS_REPO / "precos.toml", "rb") as f:
        return float(tomllib.load(f)["implantacao"]["valor_hora_adicional"])


def _resumo_escopo(escopo: dict, cat: dict) -> str:
    """Lista numerada. O número é o que identifica a linha.

    O `catalogo_id` não serve de identificador: uma proposta pode cotar cinco
    `pagina-institucional-extra` com rótulos e quantidades diferentes, e operar
    "pelo id" acerta a primeira que aparecer — que quase nunca é a certa.
    """
    linhas = []
    for k, i in enumerate(escopo.get("itens", [])):
        cid = i.get("catalogo_id")
        nome = cat.get(cid, {}).get("nome", cid)
        rot = (i.get("rotulo") or "").strip()
        extra = f' — "{rot}"' if rot else ""
        linhas.append(f"- #{k} `{cid}` {nome}{extra} · complexidade "
                      f"{i.get('complexidade') or 'não se aplica'} · {i.get('quantidade', 1)}×")
    return "\n".join(linhas) or "- (nenhum item cotado ainda)"


def _resumo_catalogo(cat: dict) -> str:
    return "\n".join(f"- `{i['id']}` {i['nome']}" for i in cat.values())


def _extrair_json(texto: str) -> list:
    """Pega o array JSON da resposta, mesmo se vier embrulhado em prosa."""
    texto = texto.strip()
    if texto.startswith("```"):
        texto = re.sub(r"^```[a-z]*\n?|\n?```$", "", texto).strip()
    try:
        dados = json.loads(texto)
    except json.JSONDecodeError:
        m = re.search(r"\[[\s\S]*\]", texto)
        if not m:
            return []
        try:
            dados = json.loads(m.group())
        except json.JSONDecodeError:
            return []
    return dados if isinstance(dados, list) else []


def _ambiente() -> dict:
    env = dict(os.environ)
    for chave in ("ANTHROPIC_MODEL", "ANTHROPIC_SMALL_FAST_MODEL", "CLAUDE_CODE_MODEL"):
        env.pop(chave, None)
    return env


def interpretar(texto: str, escopo: dict) -> tuple[list, float, str]:
    """Devolve (operações validadas, custo_usd, erro).

    Operação que não passar na validação volta com `ok: False` e o motivo — em
    vez de sumir. O vendedor precisa ver o que não foi entendido tanto quanto o
    que foi.
    """
    cat = _catalogo()
    # Substituição literal, não `.format()`: o prompt é cheio de exemplos JSON e
    # cada `{"valor": …}` seria lido como campo de formatação.
    sistema = (SISTEMA
               .replace("<<ITENS>>", _resumo_escopo(escopo, cat))
               .replace("<<CATALOGO>>", _resumo_catalogo(cat))
               .replace("<<HORA>>", f"{_valor_hora():.2f}".replace(".", ",")))

    cmd = [
        "claude", "-p", texto,
        "--output-format", "json",
        "--permission-mode", "default",
        "--setting-sources", "user,project",
        "--strict-mcp-config",
        "--mcp-config", '{"mcpServers":{}}',
        "--model", MODELO,
        "--max-budget-usd", str(TETO_USD),
        # Sem ferramenta nenhuma: tudo que ele precisa saber está no prompt, e
        # um classificador que sai lendo disco vira o problema que ele resolve.
        "--disallowedTools", "Read", "Write", "Edit", "Bash", "Glob", "Grep", "Agent",
        "--append-system-prompt", sistema,
    ]

    try:
        r = subprocess.run(cmd, cwd=cfg.RAIZ, capture_output=True, text=True,
                           timeout=TIMEOUT_S, env=_ambiente())
    except FileNotFoundError:
        return [], 0.0, "o executável `claude` não está no PATH do serviço"
    except subprocess.TimeoutExpired:
        return [], 0.0, "a leitura do pedido passou do tempo limite"

    try:
        envelope = json.loads(r.stdout)
    except json.JSONDecodeError:
        return [], 0.0, "não consegui ler a resposta do classificador"

    custo = float(envelope.get("total_cost_usd") or 0)
    if envelope.get("is_error"):
        return [], custo, f"o classificador falhou: {envelope.get('subtype') or 'erro'}"

    brutas = _extrair_json(envelope.get("result") or "")
    if not brutas:
        return [], custo, "não identifiquei nenhum pedido aplicável neste texto"

    return validar(brutas, escopo, cat), custo, ""


# -----------------------------------------------------------------------------
# Validação — nada chega ao disco sem passar por aqui
# -----------------------------------------------------------------------------

def validar(brutas: list, escopo: dict, cat: dict | None = None) -> list:
    cat = cat if cat is not None else _catalogo()
    itens = escopo.get("itens", [])
    hora = _valor_hora()

    # O mesmo interpretador do `precificar.py`. Uma segunda implementação de
    # leitura de moeda já custou um "36.000,00" virar dez vezes o preço.
    import sys as _sys
    _sys.path.insert(0, str(cfg.SCRIPTS))
    from precificar import ler_valor

    saida = []
    for b in brutas:
        if not isinstance(b, dict):
            continue
        op = {"tipo": (b.get("tipo") or "").strip(),
              "trecho": (b.get("trecho") or "").strip(),
              "ok": True, "motivo": ""}

        def recusa(motivo):
            op["ok"] = False
            op["motivo"] = motivo
            return op

        if op["tipo"] not in TIPOS:
            saida.append(recusa(f"tipo desconhecido: {op['tipo']!r}"))
            continue

        # --- qual linha do escopo, quando o tipo exige ---
        POR_ALVO = ("valor_item", "horas_item", "remover_item", "rotulo_item")
        if op["tipo"] in POR_ALVO or op["tipo"] == "item_incluso":
            alvo = b.get("alvo")
            item = None
            if alvo is not None:
                try:
                    k = int(alvo)
                except (TypeError, ValueError):
                    k = -1
                if 0 <= k < len(itens):
                    item = itens[k]
                    op["alvo"] = k
            # Sem `alvo`, aceita o id — mas só quando ele identifica uma linha
            # sozinho. Com duas linhas do mesmo tipo, adivinhar seria pior do
            # que recusar: o vendedor veria o preço mudar no item errado.
            if item is None:
                cid = (b.get("catalogo_id") or "").strip()
                iguais = [k for k, i in enumerate(itens) if i.get("catalogo_id") == cid]
                if op["tipo"] == "item_incluso" and not iguais:
                    if cid not in cat:
                        saida.append(recusa(f"não achei '{cid}' no catálogo"))
                        continue
                    op["catalogo_id"], op["nome"], op["ja_cotado"] = cid, cat[cid]["nome"], False
                    saida.append(op)
                    continue
                if len(iguais) == 1:
                    op["alvo"] = iguais[0]
                    item = itens[iguais[0]]
                elif len(iguais) > 1:
                    saida.append(recusa(
                        f"há {len(iguais)} linhas de '{cat.get(cid, {}).get('nome', cid)}' "
                        f"e o pedido não diz qual — cite o nome que aparece na proposta"))
                    continue
                else:
                    saida.append(recusa(
                        f"'{cat.get(cid, {}).get('nome', cid)}' não está cotado nesta proposta"))
                    continue
            cid = item.get("catalogo_id")
            op["catalogo_id"] = cid
            op["nome"] = (item.get("rotulo") or "").strip() or cat.get(cid, {}).get("nome", cid)
            op["ja_cotado"] = True

        if op["tipo"] == "acrescentar_item":
            cid = (b.get("catalogo_id") or "").strip()
            if cid not in cat:
                saida.append(recusa(f"não achei '{cid}' no catálogo"))
                continue
            op["catalogo_id"], op["nome"] = cid, cat[cid]["nome"]
            op["catalogo_id"] = cid
            op["nome"] = cat[cid]["nome"]

        # --- números ---
        if op["tipo"] in ("valor_total", "valor_item", "valor_base"):
            try:
                valor = float(ler_valor(b.get("valor")))
            except (ValueError, TypeError):
                saida.append(recusa("não entendi o valor pedido"))
                continue
            if valor < 0 or (valor == 0 and op["tipo"] != "valor_base"):
                saida.append(recusa("o valor precisa ser maior que zero"))
                continue
            op["valor"] = valor

            # O valor pedido é o valor que sai. Antes isto virava hora — 6.500
            # numa hora de 200 dava 32h, ou seja 6.400 —, e o número impresso
            # não era o número pedido. Agora a linha carrega o valor decidido, e
            # as horas ficam como referência interna.
            if op["tipo"] == "valor_item":
                op["quantidade"] = _qtd_da_linha(itens, op.get("alvo"))
                op["valor_efetivo"] = valor

        if op["tipo"] == "horas_item":
            try:
                horas = int(b.get("horas"))
            except (TypeError, ValueError):
                saida.append(recusa("não entendi a quantidade de horas"))
                continue
            if horas < 1:
                saida.append(recusa("as horas precisam ser pelo menos 1"))
                continue
            op["horas"] = horas
            op["valor_efetivo"] = horas * hora * _qtd_da_linha(itens, op.get("alvo"))

        if op["tipo"] == "prazo":
            try:
                mn = int(b.get("min"))
                mx = int(b.get("max", b.get("min")))
            except (TypeError, ValueError):
                saida.append(recusa("não entendi o prazo pedido"))
                continue
            if mn < 1 or mx < mn:
                saida.append(recusa(f"prazo inválido: {mn} a {mx} semanas"))
                continue
            op["min"], op["max"] = mn, mx

        if op["tipo"] == "evolucao_horas":
            try:
                horas = int(b.get("horas"))
            except (TypeError, ValueError):
                saida.append(recusa("não entendi o pacote de horas pedido"))
                continue
            if horas < 1:
                saida.append(recusa("o pacote precisa de ao menos 1 hora"))
                continue
            op["horas"] = horas

        if op["tipo"] == "acrescentar_item":
            cx = (b.get("complexidade") or "").strip().lower() or None
            item = cat[op["catalogo_id"]]
            if not item.get("no_escopo_padrao") and not item.get("regra_especial"):
                if cx not in ("baixa", "media", "alta"):
                    saida.append(recusa(
                        f"'{item['nome']}' precisa de complexidade baixa, media ou alta"))
                    continue
            else:
                cx = None
            op["complexidade"] = cx
            try:
                op["quantidade"] = max(1, int(b.get("quantidade") or 1))
            except (TypeError, ValueError):
                op["quantidade"] = 1
            op["rotulo"] = (b.get("rotulo") or "").strip()

        if op["tipo"] == "rotulo_item":
            rot = (b.get("rotulo") or "").strip()
            if not rot:
                saida.append(recusa("o rótulo veio vazio"))
                continue
            op["rotulo"] = rot

        if op["tipo"] == "texto_livre":
            instr = (b.get("instrucao") or op["trecho"]).strip()
            if not instr:
                continue
            op["instrucao"] = instr

        saida.append(op)
    return saida


def _qtd_da_linha(itens: list, alvo) -> int:
    if alvo is None or not (0 <= alvo < len(itens)):
        return 1
    try:
        return max(1, int(itens[alvo].get("quantidade", 1)))
    except (TypeError, ValueError):
        return 1


def _brl(v: float) -> str:
    return "R$ " + f"{v:,.2f}".replace(",", "§").replace(".", ",").replace("§", ".")
