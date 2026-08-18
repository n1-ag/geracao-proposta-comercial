"""Chamadas diretas aos scripts do repositório.

As fases 03 (orçamento) e 06a (render) são script puro. Pedir a um LLM que digite
a linha de comando custa um turno e cria uma classe de erro que não precisa
existir — o app chama por subprocess.

Isso também torna o gate do orçamento inviolável por construção: nenhum agente é
sequer convidado a rodar `precificar.py`.

Cada função devolve `(ok, dados, mensagem)`, com a mensagem já escrita para o
comercial ler — não é lugar de vazar traceback.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import config as cfg

TIMEOUT_SCRIPT = 300


def _rodar(argumentos: list[str], timeout: int = TIMEOUT_SCRIPT) -> subprocess.CompletedProcess:
    # cwd = raiz do repositório sempre: só `precificar.py` resolve `dados/` de
    # forma absoluta (via __file__); todos os caminhos de artefato são relativos
    # ao cwd.
    return subprocess.run(
        ["python3", *argumentos],
        cwd=cfg.RAIZ,
        capture_output=True,
        text=True,
        timeout=timeout,
    )


# -----------------------------------------------------------------------------
# Auditorias
# -----------------------------------------------------------------------------


def auditar_precos() -> tuple[bool, str]:
    """Roda a suíte golden antes de precificar qualquer coisa.

    Se os dados comerciais estiverem quebrados, é melhor não ter proposta do que
    ter uma com o preço errado — e o erro aparece antes de gastar um token de LLM.
    """
    r = _rodar(["scripts/auditar.py", "precos", "--somente-validar"])
    if r.returncode == 0:
        return True, ""
    return False, (
        "os dados comerciais não passaram na auditoria — a proposta não foi "
        f"precificada. Rode `python3 scripts/auditar.py precos` para ver o que "
        f"quebrou.\n\n{(r.stdout + r.stderr).strip()[-1200:]}"
    )


def auditar_escopo() -> tuple[bool, str]:
    r = _rodar(["scripts/auditar.py", "escopo"])
    if r.returncode == 0:
        return True, ""
    return False, f"o escopo não passou na auditoria:\n{(r.stdout + r.stderr).strip()[-1200:]}"


def auditar_html() -> tuple[bool, str]:
    """Duas checagens sobre o HTML montado: classes declaradas e — a que importa
    de verdade — todo número impresso vindo de um campo `_fmt` do orçamento."""
    problemas = []
    for sub in ("template", "numeros"):
        r = _rodar(["scripts/auditar.py", sub])
        if r.returncode != 0:
            problemas.append(f"[{sub}] {(r.stdout + r.stderr).strip()[-900:]}")
    if not problemas:
        return True, ""
    return False, "o HTML montado não passou na auditoria:\n" + "\n\n".join(problemas)


def auditar_pdf(pdf: Path) -> tuple[bool, str]:
    r = _rodar(["scripts/auditar.py", "pdf", str(pdf)])
    if r.returncode == 0:
        return True, ""
    return False, f"o PDF não passou na auditoria:\n{(r.stdout + r.stderr).strip()[-900:]}"


# -----------------------------------------------------------------------------
# Fase 03 — precificação
# -----------------------------------------------------------------------------


def precificar(hoje: str | None = None, valor_fechado=None,
               motivo_fechado: str = "", base: Path | None = None) -> tuple[bool, dict | None, str]:
    """Roda a fase 03.

    `base` permite precificar **direto num workspace**, sem montar nos
    singletons. O script resolve `dados/` de forma absoluta (via `__file__`) e
    aceita caminhos para escopo, ficha e saída — então não há motivo para
    disputar o lock de execução só para recalcular um total. É o que faz fechar
    um valor funcionar enquanto outra proposta é gerada.
    """
    raiz = Path(base) if base else cfg.RAIZ
    escopo = raiz / "proposta" / "02-escopo.json"
    if not escopo.is_file():
        return False, None, "a fase 02 não produziu `proposta/02-escopo.json`"

    argumentos = [
        "scripts/precificar.py",
        "--escopo", str(escopo),
        "--dados-cliente", str(raiz / "entrada" / "dados-cliente.md"),
        "--saida", str(raiz / "proposta" / "03-orcamento.json"),
    ]
    if hoje:
        argumentos += ["--hoje", hoje]
    if valor_fechado:
        argumentos += ["--valor-fechado", str(valor_fechado)]
        if motivo_fechado:
            argumentos += ["--motivo-fechado", motivo_fechado]

    r = _rodar(argumentos)

    # Exit 2 = uso, 3 = dados quebrados. No caminho normal o script sai 0 mesmo
    # com alerta grave — por isso a verdade vem do JSON, nunca do returncode.
    if r.returncode != 0:
        motivo = {2: "erro de uso ao chamar o precificador", 3: "os dados comerciais estão quebrados"}
        return False, None, (
            f"{motivo.get(r.returncode, 'o precificador falhou')}:\n"
            f"{(r.stderr or r.stdout).strip()[-1200:]}"
        )

    saida = raiz / "proposta" / "03-orcamento.json"
    try:
        orcamento = json.loads(saida.read_text("utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        return False, None, f"o precificador rodou mas o JSON não pôde ser lido: {e}"

    return True, orcamento, ""


# -----------------------------------------------------------------------------
# Fase 06a — render
# -----------------------------------------------------------------------------

# Os cinco códigos de saída do render_pdf.py, traduzidos.
ERROS_RENDER = {
    2: "faltou um arquivo referenciado pelo HTML (imagem, CSS ou fonte)",
    3: "o conteúdo transbordou a página",
    4: "as fontes de templates/assets/fonts/ não carregaram no navegador",
    5: "o pypdf não está instalado, então o PDF sairia sem metadados",
}


def renderizar(titulo: str | None = None) -> tuple[bool, dict, str]:
    """Gera o PDF. Devolve (ok, {pdf, paginas, transbordo}, mensagem).

    `transbordo=True` no retorno é o sinal para o motor reinvocar a fase 05 com
    o relatório de paginação em mãos, em vez de desistir.
    """
    html = cfg.SINGLETON_PROPOSTA / "proposta.html"
    if not html.is_file():
        return False, {}, "a fase 05 não produziu `proposta/proposta.html`"

    (cfg.SINGLETON_SAIDA / "preview").mkdir(parents=True, exist_ok=True)

    argumentos = [
        "scripts/render_pdf.py",
        "--html", "proposta/proposta.html",
        "--orcamento", "proposta/03-orcamento.json",
        "--auditar", "--estrito",
        "--relatorio", "saida/relatorio-paginacao.json",
        "--png", "saida/preview/",
    ]
    if titulo:
        argumentos += ["--titulo", titulo]

    r = _rodar(argumentos, timeout=600)

    if r.returncode == 0:
        # stdout final: "PDF: <caminho absoluto>  (N páginas)"
        caminho, paginas = None, None
        for linha in reversed((r.stdout or "").strip().splitlines()):
            if linha.startswith("PDF:"):
                import re

                casou = re.match(r"PDF:\s*(.+?)\s*\((\d+)\s+páginas?\)", linha)
                if casou:
                    caminho, paginas = casou.group(1), int(casou.group(2))
                break
        if not caminho:
            achados = sorted((cfg.SINGLETON_SAIDA).glob("*.pdf"))
            caminho = str(achados[-1]) if achados else None
        if not caminho:
            return False, {}, "o render disse que deu certo mas nenhum PDF apareceu em saida/"
        return True, {"pdf": caminho, "paginas": paginas}, ""

    detalhe = (r.stderr or r.stdout).strip()[-1200:]
    mensagem = ERROS_RENDER.get(r.returncode, f"o render falhou (código {r.returncode})")
    return False, {"transbordo": r.returncode == 3}, f"{mensagem}:\n{detalhe}"


def relatorio_paginacao() -> dict | None:
    alvo = cfg.SINGLETON_SAIDA / "relatorio-paginacao.json"
    try:
        return json.loads(alvo.read_text("utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def paginas_problematicas() -> list[dict]:
    """Só as páginas que estouraram ou colidiram com o rodapé.

    Cuidado com o formato: no relatório, `paginas` é a **contagem** de páginas
    (um int), não a lista. O detalhe por página vive em `detalhe`.
    """
    relatorio = relatorio_paginacao() or {}
    problemas = []
    for pagina in relatorio.get("detalhe") or []:
        if not isinstance(pagina, dict):
            continue
        if pagina.get("transbordo_px") or pagina.get("colide_com_rodape"):
            problemas.append({
                "pagina": pagina.get("pagina"),
                "transbordo_px": pagina.get("transbordo_px"),
                "colide_com_rodape": pagina.get("colide_com_rodape"),
                "blocos": (pagina.get("blocos") or [])[:6],
            })
    return problemas
