#!/usr/bin/env python3
"""Incorpora um item ao `dados/catalogo-modulos.toml`.

Item cotado fora do catálogo apareceu em **todas** as seis propostas que este
app gerou, e nenhum foi incorporado: o único caminho era um comando de terminal,
que é justamente o que o app veio eliminar. Enquanto isso o alerta
`ITEM_NAO_CATALOGADO` fica aceso e o catálogo não aprende nada.

**Não reescreve o arquivo.** O catálogo tem cinco seções temáticas separadas por
banners de comentário, e os comentários explicam decisões de precificação —
"REVISE OS NÚMEROS", "todas pressupõem instalar app na loja". Serializar de novo
com uma biblioteca apagaria tudo isso e trocaria a ordem dos campos.

Em vez disso, insere um bloco de texto imediatamente antes do banner da seção
seguinte. Todo o resto do arquivo continua byte a byte idêntico, o que torna o
`git diff` legível: só o bloco novo.

Uso:
    python3 scripts/catalogar.py --json '<item>'
    echo '<item>' | python3 scripts/catalogar.py
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import tomllib
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
CATALOGO = RAIZ / "dados" / "catalogo-modulos.toml"

CATEGORIAS = ("escopo-padrao", "conteudo", "componente", "integracao",
              "migracao", "seo", "apoio")

# Onde cada categoria mora no arquivo. O valor é um trecho do banner da seção;
# a ordem aqui é a ordem física das seções no arquivo.
SECOES = [
    ("escopo-padrao", "ESCOPO PADRÃO"),
    ("conteudo", "PÁGINAS E CONTEÚDO"),
    ("componente", "COMPONENTES E EXPERIÊNCIA"),
    ("integracao", "INTEGRAÇÕES"),
    ("migracao", "MIGRAÇÃO, SEO E APOIO"),
    ("seo", "MIGRAÇÃO, SEO E APOIO"),
    ("apoio", "MIGRAÇÃO, SEO E APOIO"),
]


class Recusa(Exception):
    """O item não entra. A mensagem é para uma pessoa ler."""


# -----------------------------------------------------------------------------
# Validação — o mesmo que `auditar.py precos` cobra, checado antes de escrever
# -----------------------------------------------------------------------------


def validar(item: dict, catalogo: dict) -> dict:
    limpo = {}

    cid = (item.get("id") or "").strip()
    if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", cid):
        raise Recusa(f"id fora do padrão kebab-case: {cid!r} "
                     f"(minúsculas, números e hífen entre palavras)")
    if cid in catalogo:
        raise Recusa(f"já existe um item com o id '{cid}': {catalogo[cid]['nome']}")
    limpo["id"] = cid

    for campo in ("nome", "descricao_proposta", "criterio_complexidade"):
        valor = (item.get(campo) or "").strip()
        if not valor:
            raise Recusa(f"`{campo}` é obrigatório")
        limpo[campo] = valor

    categoria = (item.get("categoria") or "").strip()
    if categoria not in CATEGORIAS:
        raise Recusa(f"categoria inválida: {categoria!r}. Use uma de: {', '.join(CATEGORIAS)}")
    limpo["categoria"] = categoria

    unidade = (item.get("unidade") or "").strip()
    if not unidade:
        raise Recusa("`unidade` é obrigatória (página, componente, integração…)")
    limpo["unidade"] = unidade

    limpo["exige_app"] = bool(item.get("exige_app"))
    regra = (item.get("regra_especial") or "").strip()
    if regra and regra != "landing_page":
        raise Recusa(f"regra_especial só aceita 'landing_page' (recebido {regra!r})")
    limpo["regra_especial"] = regra
    limpo["no_escopo_padrao"] = bool(item.get("no_escopo_padrao"))

    # Faixa é dispensada exatamente nos casos em que o `auditar.py` dispensa.
    if not limpo["no_escopo_padrao"] and not regra:
        for cx in ("baixa", "media", "alta"):
            faixa = item.get(f"horas_{cx}")
            if not isinstance(faixa, (list, tuple)) or len(faixa) != 2:
                raise Recusa(f"`horas_{cx}` precisa ser [mínimo, máximo]")
            try:
                mn, mx = int(faixa[0]), int(faixa[1])
            except (TypeError, ValueError):
                raise Recusa(f"`horas_{cx}` precisa ter dois inteiros") from None
            if mn < 1 or mx < mn:
                raise Recusa(f"`horas_{cx}` inválida: [{mn}, {mx}]")
            limpo[f"horas_{cx}"] = [mn, mx]

    if "baixa:" not in limpo["criterio_complexidade"] and not limpo["no_escopo_padrao"]:
        raise Recusa("o critério de complexidade precisa das três linhas "
                     "(baixa: … ; media: … ; alta: …) — é o texto que o agente "
                     "lê para classificar")
    return limpo


# -----------------------------------------------------------------------------
# Escrita
# -----------------------------------------------------------------------------


def bloco(item: dict) -> str:
    """O texto do item, no formato exato que o arquivo já usa.

    Um espaço em torno do `=`, campos falsos omitidos em vez de escritos como
    `false`, e `criterio_complexidade` em aspas triplas com quebra logo após a
    abertura e o fechamento colado na última linha. Copiar a forma importa: o
    arquivo é lido por gente.
    """
    L = ["[[itens]]",
         f'id = "{item["id"]}"',
         f'nome = "{_escapar(item["nome"])}"',
         f'categoria = "{item["categoria"]}"',
         f'unidade = "{_escapar(item["unidade"])}"']

    if item["no_escopo_padrao"]:
        L.append("no_escopo_padrao = true")
    if item["regra_especial"]:
        L.append(f'regra_especial = "{item["regra_especial"]}"')
    if item["exige_app"]:
        L.append("exige_app = true")

    for cx in ("baixa", "media", "alta"):
        if f"horas_{cx}" in item:
            mn, mx = item[f"horas_{cx}"]
            L.append(f"horas_{cx} = [{mn}, {mx}]")

    criterio = item["criterio_complexidade"].strip()
    L.append(f'criterio_complexidade = """\n{criterio}"""')
    L.append(f'descricao_proposta = "{_escapar(item["descricao_proposta"])}"')
    return "\n".join(L) + "\n"


def _escapar(s: str) -> str:
    return s.replace("\\", "\\\\").replace('"', '\\"')


def _ponto_de_insercao(texto: str, categoria: str) -> int:
    """A posição onde o bloco entra: fim da seção da categoria.

    Achar o banner da seção seguinte e voltar até antes dele é o que mantém o
    arquivo organizado por tema — item de integração no meio dos componentes
    seria válido para o parser e ilegível para quem abre o arquivo.
    """
    banners = [(m.start(), m.group(1).strip())
               for m in re.finditer(r"^# =+\n^# (.+)\n^# =+$", texto, re.M)]
    if not banners:
        return len(texto)

    alvo = dict(SECOES).get(categoria)
    indice = next((k for k, (_, t) in enumerate(banners) if alvo and t.startswith(alvo)), None)
    if indice is None:
        return len(texto)

    # Começo do próximo banner, ou fim do arquivo se for a última seção.
    return banners[indice + 1][0] if indice + 1 < len(banners) else len(texto)


def inserir(item: dict, caminho: Path = CATALOGO) -> str:
    texto = caminho.read_text("utf-8")
    corte = _ponto_de_insercao(texto, item["categoria"])
    antes, depois = texto[:corte].rstrip("\n"), texto[corte:]
    novo = antes + "\n\n" + bloco(item) + ("\n" + depois if depois else "\n")
    caminho.write_text(novo, "utf-8")
    return novo


def catalogar(bruto: dict, caminho: Path = CATALOGO) -> dict:
    """Valida, escreve e confere. Reprovou na auditoria, desfaz."""
    with open(caminho, "rb") as f:
        catalogo = {i["id"]: i for i in tomllib.load(f)["itens"]}

    item = validar(bruto, catalogo)
    guarda = caminho.read_text("utf-8")
    inserir(item, caminho)

    # A auditoria é a mesma que o pipeline roda. Escrever um catálogo que ela
    # reprova quebraria a próxima proposta, não esta.
    r = subprocess.run([sys.executable, str(RAIZ / "scripts" / "auditar.py"), "precos"],
                       capture_output=True, text=True, cwd=RAIZ)
    if r.returncode != 0:
        caminho.write_text(guarda, "utf-8")
        falhas = [l.strip() for l in r.stdout.splitlines() if "FALHA" in l]
        raise Recusa("a auditoria reprovou o catálogo e a mudança foi desfeita: "
                     + (" | ".join(falhas[:3]) or r.stdout[-300:]))

    return item


def main() -> int:
    ap = argparse.ArgumentParser(description="Incorpora um item ao catálogo de módulos.")
    ap.add_argument("--json", help="o item em JSON; sem isto, lê da entrada padrão")
    args = ap.parse_args()

    try:
        bruto = json.loads(args.json if args.json else sys.stdin.read())
    except json.JSONDecodeError as e:
        print(f"erro: JSON inválido: {e}", file=sys.stderr)
        return 2

    try:
        item = catalogar(bruto)
    except Recusa as e:
        print(f"erro: {e}", file=sys.stderr)
        return 1

    print(f"catalogado: {item['id']} — {item['nome']} (seção {item['categoria']})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
