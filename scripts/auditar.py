#!/usr/bin/env python3
"""
auditar.py — as verificações mecânicas do pipeline.

    precos     valida dados/*.toml e roda a suíte golden de precificação
    escopo     confere 02-escopo.md contra 02-escopo.json e exige rastreabilidade
    numeros    garante que todo número do HTML veio de 03-orcamento.json
    template   garante que o HTML só usa classes declaradas no CSS
    pdf        confere o PDF final (páginas, metadata, marcadores residuais)

Saída: 0 tudo certo · 1 falhou · 2 erro de uso.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import tomllib
from decimal import Decimal as D
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "scripts"))

import precificar as P  # noqa: E402


class Relatorio:
    def __init__(self, titulo):
        self.titulo, self.erros, self.avisos, self.ok = titulo, [], [], 0

    def falha(self, msg): self.erros.append(msg)
    def aviso(self, msg): self.avisos.append(msg)
    def passou(self): self.ok += 1

    def fim(self) -> int:
        print(f"\n=== {self.titulo} ===")
        for a in self.avisos: print(f"  aviso  {a}")
        for e in self.erros: print(f"  FALHA  {e}")
        print(f"  {self.ok} verificações passaram, {len(self.erros)} falharam.")
        return 1 if self.erros else 0


# -----------------------------------------------------------------------------
# precos
# -----------------------------------------------------------------------------
def valida_dados(dados: P.Dados, r: Relatorio):
    cat = dados.catalogo
    for cid, item in cat.items():
        if not re.fullmatch(r"[a-z0-9-]+", cid):
            r.falha(f"catálogo: id fora do padrão kebab-case: {cid!r}")
        if not item.get("nome"): r.falha(f"catálogo: {cid} sem `nome`")
        if not item.get("descricao_proposta"): r.falha(f"catálogo: {cid} sem `descricao_proposta`")
        if item.get("no_escopo_padrao") or item.get("regra_especial"):
            continue
        for cx in ("baixa", "media", "alta"):
            faixa = item.get(f"horas_{cx}")
            if not faixa or len(faixa) != 2:
                r.falha(f"catálogo: {cid} sem faixa `horas_{cx}` = [min, max]")
            elif faixa[0] > faixa[1]:
                r.falha(f"catálogo: {cid} horas_{cx} com min > max: {faixa}")
        if not item.get("criterio_complexidade"):
            r.falha(f"catálogo: {cid} sem `criterio_complexidade` — o agente não teria como classificar")
    r.passou()

    faixas = dados.faixas
    for a, b in zip(faixas, faixas[1:]):
        if a["horas_max"] + 1 != b["horas_min"]:
            r.falha(f"faixas de fee com buraco/sobreposição entre {a['id']} e {b['id']}")
        if a["valor_hora"] < b["valor_hora"]:
            r.aviso(f"faixa {b['id']} custa mais por hora que {a['id']} — pacote maior deveria ser mais barato")
    if faixas[0]["horas_min"] != 1:
        r.falha("a primeira faixa de fee deveria começar em 1 hora")
    r.passou()

    for slug, p in dados.precos["implantacao"]["plataformas"].items():
        if p["design_embutido"] >= p["valor_base"]:
            r.falha(f"plataforma {slug}: design embutido >= valor base")
    r.passou()

    # NORMATIVO: `natureza` não pode entrar em nenhuma conta.
    fonte = (RAIZ / "scripts" / "precificar.py").read_text(encoding="utf-8")
    calculo = fonte.split("# Ficha do cliente")[0]
    if re.search(r'natureza', calculo):
        r.falha("precificar.py lê `natureza` no caminho de cálculo — "
                "migração e projeto novo devem custar o mesmo")
    r.passou()


def roda_golden(dados: P.Dados, r: Relatorio):
    with open(RAIZ / "dados" / "casos-teste-precificacao.toml", "rb") as f:
        casos = tomllib.load(f)

    for c in casos.get("conversao", []):
        got = P.converter(dados, D(str(c["valor_implantacao"])))
        nome = f"conversão/{c['id']}"
        if got["aplicavel"] != c["espera_aplicavel"]:
            r.falha(f"{nome}: aplicavel={got['aplicavel']}, esperado {c['espera_aplicavel']}")
            continue
        if c["espera_aplicavel"]:
            for campo, esperado, obtido in (
                ("faixa", c["espera_faixa"], got["faixa_id"]),
                ("valor_hora", c["espera_valor_hora"], got["valor_hora"]),
                ("horas", c["espera_horas"], got["pacote_horas"]),
                ("mensal", c["espera_mensal"], got["valor_mensal"]),
            ):
                iguais = (esperado == obtido if isinstance(esperado, str)
                          else float(esperado) == float(obtido))
                if not iguais:
                    r.falha(f"{nome}: {campo}={obtido}, esperado {esperado}")
                    break
            else:
                if "espera_ajuste_de_borda" in c and got["calculo"]["ajuste_de_borda"] != c["espera_ajuste_de_borda"]:
                    r.falha(f"{nome}: ajuste_de_borda={got['calculo']['ajuste_de_borda']!r}, "
                            f"esperado {c['espera_ajuste_de_borda']!r}")
                elif c.get("espera_desempate") and not got["calculo"]["criterio_desempate"]:
                    r.falha(f"{nome}: esperava desempate entre faixas, não houve")
                else:
                    r.passou()
        if "espera_alerta" in c and c["espera_alerta"] not in got["alertas"]:
            r.falha(f"{nome}: esperava alerta {c['espera_alerta']}, veio {got['alertas']}")
        elif not c["espera_aplicavel"]:
            r.passou()

    for c in casos.get("faixa", []):
        got = P.precificar_pacote(dados, c["horas"])
        if got["faixa_id"] != c["espera_faixa"] or got["valor_mensal"] != c["espera_mensal"]:
            r.falha(f"faixa/{c['horas']}h: {got['faixa_id']} {got['valor_mensal']}, "
                    f"esperado {c['espera_faixa']} {c['espera_mensal']}")
        else:
            r.passou()

    for c in casos.get("implantacao", []):
        escopo = {"modelo_principal": "implantacao", "plataforma": c["plataforma"],
                  "design_fornecido_pelo_cliente": c["design_fornecido_pelo_cliente"],
                  "itens": c.get("itens", [])}
        got = P.precificar_implantacao(dados, escopo)
        nome = f"implantação/{c['id']}"
        if got["total"] != c["espera_total"]:
            r.falha(f"{nome}: total={got['total']}, esperado {c['espera_total']}")
        elif got["subtotais"]["horas_adicionais"] != c["espera_horas_adicionais"]:
            r.falha(f"{nome}: horas={got['subtotais']['horas_adicionais']}, "
                    f"esperado {c['espera_horas_adicionais']}")
        elif "espera_alerta" in c and c["espera_alerta"] not in [a["codigo"] for a in got["alertas"]]:
            r.falha(f"{nome}: esperava alerta {c['espera_alerta']}")
        else:
            r.passou()

    for c in casos.get("opcoes", []):
        got = P.opcoes_pacote(dados, c["horas_recomendadas"])
        horas = [o["horas"] for o in got["opcoes"]]
        rec = next(o["horas"] for o in got["opcoes"] if o["recomendado"])
        if horas != c["espera_horas"] or rec != c["espera_recomendado"]:
            r.falha(f"opções/{c['id']}: {horas} rec={rec}, "
                    f"esperado {c['espera_horas']} rec={c['espera_recomendado']}")
        else:
            r.passou()


def cmd_precos(args) -> int:
    r = Relatorio("Preços e catálogo")
    dados = P.Dados()
    valida_dados(dados, r)
    if not args.somente_validar:
        roda_golden(dados, r)
        ref = [c for c in tomllib.load(open(RAIZ / "dados" / "casos-teste-precificacao.toml", "rb"))["conversao"]
               if c["id"] == "referencia-50k"]
        if ref:
            g = P.converter(dados, D("50000"))
            marca = "OK" if g["valor_mensal"] == 5460.00 and g["pacote_horas"] == 26 else "FALHOU"
            print(f"  caso de referência R$ 50.000 → {g['pacote_horas']}h × "
                  f"{g['valor_hora_fmt']} = {g['valor_mensal_fmt']}/mês  [{marca}]")
    return r.fim()


# -----------------------------------------------------------------------------
# escopo
# -----------------------------------------------------------------------------
def cmd_escopo(args) -> int:
    r = Relatorio("Escopo")
    esc = json.loads(Path(args.json).read_text(encoding="utf-8"))
    md = Path(args.md).read_text(encoding="utf-8") if args.md and Path(args.md).is_file() else ""
    dados = P.Dados()

    for i in esc.get("itens", []):
        cid = i["catalogo_id"]
        if cid not in dados.catalogo:
            r.falha(f"item '{cid}' não existe no catálogo")
            continue
        if not i.get("origem"):
            r.falha(f"item '{cid}' sem `origem` — toda linha cotada precisa citar a evidência [E##]")
        if md and cid not in md:
            r.falha(f"item '{cid}' está no JSON mas não aparece em 02-escopo.md (deriva entre espelhos)")
        item = dados.catalogo[cid]
        if not item.get("no_escopo_padrao") and not item.get("regra_especial"):
            if i.get("complexidade") not in ("baixa", "media", "alta"):
                r.falha(f"item '{cid}' sem complexidade válida")
        r.passou()

    # Linha repetida sem rótulo que a distinga. A Certifica foi para o cliente com
    # cinco "Página institucional adicional" de R$ 1.200 a R$ 9.600, e nada no
    # documento dizia qual era qual — o escopo sabia, o PDF não mostrava.
    por_id: dict = {}
    for i in esc.get("itens", []):
        por_id.setdefault(i.get("catalogo_id"), []).append((i.get("rotulo") or "").strip())
    for cid, rotulos in por_id.items():
        if len(rotulos) < 2:
            continue
        if len(set(rotulos)) < len(rotulos) or "" in rotulos:
            nome = dados.catalogo.get(cid, {}).get("nome", cid)
            r.falha(
                f"'{cid}' aparece {len(rotulos)}× e os rótulos não distinguem as linhas. "
                f"No PDF viram {len(rotulos)} linhas iguais chamadas '{nome}' com preços "
                f"diferentes. Dê um `rotulo` próprio a cada uma dizendo o que ela é."
            )
        else:
            r.passou()

    for i in esc.get("itens_fora_catalogo", []):
        if not i.get("justificativa"):
            r.falha(f"item fora do catálogo '{i.get('nome')}' sem justificativa técnica")
        if not i.get("origem"):
            r.falha(f"item fora do catálogo '{i.get('nome')}' sem `origem`")
        r.aviso(f"item fora do catálogo: {i.get('nome')} — rode /proposta-catalogo para incorporá-lo")
        r.passou()

    if md and "R$" in md:
        # Dizer só "contém" manda quem for corrigir varrer 300 linhas à mão — e
        # quase sempre é uma frase só, às vezes uma em que o agente jura que não
        # escreveu valor nenhum.
        onde = [f"linha {n}: {linha.strip()[:90]}"
                for n, linha in enumerate(md.splitlines(), 1) if "R$" in linha]
        r.falha("02-escopo.md contém 'R$' — a fase 02 não precifica; quem precifica "
                "é o script. Ocorrências: " + " | ".join(onde[:5]))
    else:
        r.passou()
    return r.fim()


# -----------------------------------------------------------------------------
# numeros — o teste que pega alucinação numérica de forma mecânica
# -----------------------------------------------------------------------------
RE_DINHEIRO = re.compile(r"R\$\s*[\d][\d.\s]*(?:,\d{2})?")
RE_HORAS = re.compile(r"\b\d+\s*(?:h\b|horas?\b|h/mês|h / mês)")
RE_PCT = re.compile(r"\b\d+\s*%")
RE_RELOGIO = re.compile(r"(?:às|as|até|após\s+as|depois\s+das|a\s+partir\s+das)\s*\d+\s*h\b",
                        re.IGNORECASE)


# O que é conta nossa e não vai para o documento do cliente. Esforço em horas e
# valor da hora são a matéria-prima do preço: com os dois, quem lê reconstrói a
# margem. O cliente compra entregas por um valor, não horas por uma taxa.
#
# Isto era convenção editorial — o montador copiava o formato do exemplar — e
# por isso variava: Pekon e Viveo saíram sem uma hora sequer, Certifica com
# treze linhas delas. Aqui vira regra.
CAMPOS_INTERNOS = (
    "valor_hora_fmt", "horas_total_fmt", "horas_adicionais_fmt",
    "horas_min_total", "horas_max_total", "horas_adicionais_min",
    "horas_adicionais_max",
)

# `valor_hora_fmt` também não aparece na proposta de fee mensal: com o pacote
# ("30 horas · R$ 6.000,00") a taxa é uma divisão, e imprimi-la só chama atenção
# para a conta. `hora_excedente_fmt` é outra coisa — é cláusula: o cliente
# precisa saber quanto paga se estourar o pacote, e escondê-la seria pior.
CAMPOS_INTERNOS_EVOLUCAO = ("valor_hora_fmt",)


def _subarvore(orc: dict, chave: str) -> dict:
    return orc.get(chave) or {}


def horas_permitidas(orc: dict) -> set:
    """Horas que podem aparecer: só as dos pacotes de fee mensal.

    Na evolução o pacote de horas é o produto — "28 horas por mês" é o que está
    sendo vendido, e omiti-lo deixaria a oferta incompreensível. Na implantação
    a hora é custo interno.
    """
    perm = set()

    # Só as chaves que falam de horas. Varrer todo número da subárvore deixava
    # `contrato_meses: 12` autorizar "12h" e `valor_hora: 210` autorizar "210h" —
    # o conjunto ficava tão largo que a regra não pegava nada.
    def e_de_horas(chave: str) -> bool:
        return "horas" in chave or chave in ("pacote", "pacote_fmt")

    def anda(n):
        if isinstance(n, dict):
            for k, v in n.items():
                # Texto na subárvore de evolução já é rótulo de cliente
                # (`pacote_horas_fmt`, `faixa_rotulo`): o que estiver escrito
                # ali pode aparecer. Número solto, só de chave que fala de hora.
                if isinstance(v, str):
                    for m in RE_HORAS.finditer(v):
                        perm.add(m.group().strip())
                elif e_de_horas(k) and isinstance(v, (int, float)) and not isinstance(v, bool):
                    perm.add(f"{int(v)}h"); perm.add(f"{int(v)} h"); perm.add(f"{int(v)} horas")
                anda(v)
        elif isinstance(n, list):
            for v in n:
                anda(v)

    anda(_subarvore(orc, "evolucao"))
    return {re.sub(r"\s+", " ", x).strip() for x in perm}


def valores_internos(orc: dict) -> set:
    """Os textos formatados que o HTML não pode conter."""
    achados = set()

    def anda(n):
        if isinstance(n, dict):
            for k, v in n.items():
                if k in CAMPOS_INTERNOS and v not in (None, "", 0):
                    achados.add(f"{int(v)}h" if isinstance(v, (int, float)) else str(v).strip())
                anda(v)
        elif isinstance(n, list):
            for v in n:
                anda(v)

    anda(_subarvore(orc, "implantacao"))

    evo = _subarvore(orc, "evolucao")
    for k in CAMPOS_INTERNOS_EVOLUCAO:
        v = evo.get(k)
        if v:
            achados.add(str(v).strip())
    return achados


def valores_permitidos(orc: dict) -> set:
    """Todo `*_fmt`, mais os inteiros que a proposta legitimamente cita."""
    perm = set()

    def anda(n):
        if isinstance(n, dict):
            for k, v in n.items():
                if isinstance(v, str) and (k.endswith("_fmt") or k in ("parcelamento", "prazo_fmt")):
                    perm.add(v)
                    for m in RE_DINHEIRO.finditer(v): perm.add(m.group().strip())
                    for m in RE_HORAS.finditer(v): perm.add(m.group().strip())
                    for m in RE_PCT.finditer(v): perm.add(m.group().strip())
                elif isinstance(v, (int, float)) and not isinstance(v, bool):
                    perm.add(f"{int(v)}h"); perm.add(f"{int(v)} h")
                    perm.add(f"{int(v)} horas"); perm.add(f"{int(v)}%"); perm.add(f"{int(v)} %")
                    perm.add(f"{int(v)} meses")
                anda(v)
        elif isinstance(n, list):
            for v in n: anda(v)

    anda(orc)
    return {re.sub(r"\s+", " ", p).strip() for p in perm}


def cmd_numeros(args) -> int:
    r = Relatorio("Números do HTML vs. orçamento")
    html = Path(args.html).read_text(encoding="utf-8")
    orc = json.loads(Path(args.orcamento).read_text(encoding="utf-8"))
    texto = re.sub(r"<[^>]+>", " ", re.sub(r"<(script|style)[\s\S]*?</\1>", " ", html))
    texto = re.sub(r"\s+", " ", texto)
    # O bloco .price parte o valor em spans (`54.800` + `,00`) para tipografar os
    # centavos menores. Remover as tags deixa um espaço no meio do número; sem
    # esta costura, todo valor destacado viraria falso positivo.
    texto = re.sub(r"(\d)\s+(,\d{2})", r"\1\2", texto)
    perm = valores_permitidos(orc)

    for regex, rotulo in ((RE_DINHEIRO, "valor"), (RE_HORAS, "horas"), (RE_PCT, "percentual")):
        for m in regex.finditer(texto):
            achado = re.sub(r"\s+", " ", m.group()).strip()
            if achado not in perm:
                r.falha(f"{rotulo} no HTML que não veio do orçamento: {achado!r}")
            else:
                r.passou()

    # Bater com o orçamento não basta: há número que confere e mesmo assim não
    # deveria estar num documento que vai para o cliente.
    horas_ok = horas_permitidas(orc)
    # "publicação após as 16h" é hora do relógio, não esforço. Sai da varredura
    # antes da conta, senão a política de publicação reprova a proposta.
    sem_relogio = RE_RELOGIO.sub(" ", texto)
    vazadas = sorted({re.sub(r"\s+", " ", m.group()).strip()
                      for m in RE_HORAS.finditer(sem_relogio)} - horas_ok)
    if vazadas:
        resto = len(vazadas) - 8
        r.falha(
            "esforço em horas no HTML: " + ", ".join(vazadas[:8])
            + (f" (e mais {resto})" if resto > 0 else "")
            + ". O cliente vê o valor de cada módulo, não as horas que o compõem "
              "(só o pacote de horas do fee mensal pode aparecer)."
        )
    else:
        r.passou()

    internos = [v for v in valores_internos(orc) if v and v in texto]
    if internos:
        # Dinheiro primeiro: a taxa horária é o achado mais grave e, em ordem
        # alfabética, ficava atrás de uma fila de "10h, 18h, 2h…" e sumia no
        # corte da mensagem — quem lesse concluiria que ela não foi pega.
        ordenados = sorted(internos, key=lambda v: (not v.startswith("R$"), v))
        mostra = ordenados[:8]
        resto = len(ordenados) - len(mostra)
        r.falha(
            "dado interno no HTML: " + ", ".join(mostra)
            + (f" (e mais {resto})" if resto else "")
            + ". São campos de cálculo nosso — valor da hora e esforço — e não "
              "entram no documento."
        )
    else:
        r.passou()

    for marcador in re.findall(r"\{\{[A-Z_0-9]+\}\}|«[^»]+»", html):
        r.falha(f"marcador não resolvido no HTML final: {marcador}")
    return r.fim()


# -----------------------------------------------------------------------------
# template
# -----------------------------------------------------------------------------
def cmd_template(args) -> int:
    r = Relatorio("Classes do HTML vs. CSS")
    html = Path(args.html).read_text(encoding="utf-8")
    css = (RAIZ / "templates" / "assets" / "css" / "proposta.css").read_text(encoding="utf-8")
    declaradas = set(re.findall(r"\.([a-zA-Z][\w-]*)", re.sub(r"/\*[\s\S]*?\*/", "", css)))
    usadas = set()
    for m in re.finditer(r'class="([^"]+)"', html):
        usadas |= set(m.group(1).split())
    inventadas = sorted(usadas - declaradas)
    for c in inventadas:
        r.falha(f"classe usada no HTML mas não declarada no CSS: .{c}")
    if not inventadas:
        r.passou()
    if 'style="' in html and not args.permitir_style:
        n = html.count('style="')
        r.aviso(f"{n} atributo(s) style= inline — prefira classes utilitárias do CSS")
    return r.fim()


# -----------------------------------------------------------------------------
# pdf
# -----------------------------------------------------------------------------
def cmd_pdf(args) -> int:
    r = Relatorio("PDF final")
    pdf = Path(args.pdf)
    if not pdf.is_file():
        print(f"erro: {pdf} não existe"); return 1
    info = subprocess.run(["pdfinfo", str(pdf)], capture_output=True, text=True).stdout
    paginas = int(re.search(r"Pages:\s+(\d+)", info).group(1))

    if args.html:
        n = Path(args.html).read_text(encoding="utf-8").count('class="page')
        if n != paginas:
            r.falha(f"o HTML tem {n} seções .page mas o PDF saiu com {paginas}")
        else:
            r.passou()

    if not re.search(r"Page size:\s+59[0-9.]+ x 84[0-9.]+ pts", info):
        r.falha(f"tamanho de página não é A4: {re.search(r'Page size:.*', info).group()}")
    else:
        r.passou()

    fontes = subprocess.run(["pdffonts", str(pdf)], capture_output=True, text=True).stdout
    if "Poppins" not in fontes:
        r.falha("a Poppins não está embutida no PDF — saiu em fonte de fallback")
    else:
        r.passou()

    texto = subprocess.run(["pdftotext", "-layout", str(pdf), "-"],
                           capture_output=True, text=True).stdout
    for marcador in re.findall(r"\{\{[A-Z_0-9]+\}\}|«[^»]+»", texto):
        r.falha(f"marcador não resolvido dentro do PDF: {marcador}")

    if args.orcamento:
        orc = json.loads(Path(args.orcamento).read_text(encoding="utf-8"))
        cliente = orc["cliente"]["nome"]
        if cliente and cliente not in texto:
            r.falha(f"o nome do cliente ({cliente!r}) não aparece no PDF")
        else:
            r.passou()
        for campo in ("Title", "Author", "Subject"):
            if not re.search(rf"^{campo}:\s+\S", info, re.M):
                r.falha(f"metadata sem {campo}")
            else:
                r.passou()
    return r.fim()


def main() -> int:
    ap = argparse.ArgumentParser(description="Verificações mecânicas do pipeline.")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("precos"); p.add_argument("--somente-validar", action="store_true")
    p.set_defaults(fn=cmd_precos)

    p = sub.add_parser("escopo")
    p.add_argument("json", nargs="?", default="proposta/02-escopo.json")
    p.add_argument("md", nargs="?", default="proposta/02-escopo.md")
    p.set_defaults(fn=cmd_escopo)

    p = sub.add_parser("numeros")
    p.add_argument("html", nargs="?", default="proposta/proposta.html")
    p.add_argument("orcamento", nargs="?", default="proposta/03-orcamento.json")
    p.set_defaults(fn=cmd_numeros)

    p = sub.add_parser("template")
    p.add_argument("html", nargs="?", default="proposta/proposta.html")
    p.add_argument("--permitir-style", action="store_true")
    p.set_defaults(fn=cmd_template)

    p = sub.add_parser("pdf")
    p.add_argument("pdf")
    p.add_argument("--html"); p.add_argument("--orcamento")
    p.set_defaults(fn=cmd_pdf)

    args = ap.parse_args()
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
