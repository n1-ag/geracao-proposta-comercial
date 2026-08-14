#!/usr/bin/env python3
"""
render_pdf.py — HTML da proposta -> PDF A4, com auditoria de paginação.

Por que um servidor HTTP efêmero em vez de abrir o arquivo direto: sob `file://`
o Chrome trata cada arquivo como origem opaca e o `@font-face` local falha em
silêncio. O PDF sai "quase certo", em fonte de fallback. Servindo por HTTP o
problema simplesmente não existe, e ainda dá para checar `document.fonts`.

Códigos de saída
  0  tudo certo
  2  erro de uso / arquivo ausente
  3  transbordo de página (com --estrito) ou contagem de páginas divergente
  4  a Poppins não carregou
  5  PDF gerado, mas sem metadata (pypdf ausente)

Uso típico
  python3 scripts/render_pdf.py --html proposta/proposta.html \
      --orcamento proposta/03-orcamento.json --auditar --estrito
"""
from __future__ import annotations

import argparse
import functools
import http.server
import json
import os
import re
import socket
import socketserver
import sys
import threading
import unicodedata
from pathlib import Path

EXIT_OK, EXIT_USO, EXIT_PAGINACAO, EXIT_FONTE, EXIT_SEM_METADATA = 0, 2, 3, 4, 5

# JS de medição. Roda no DOM já renderizado, antes de imprimir: compara a altura
# do conteúdo com a da caixa e verifica se o último bloco encosta no rodapé.
JS_AUDITORIA = r"""
() => [...document.querySelectorAll('.page')].map((p, i) => {
  const body = p.querySelector('.body-page');
  const foot = p.querySelector('.foot');
  if (!body) return { pagina: i + 1, tipo: 'especial', transbordo_px: 0, colide_com_rodape: false, blocos: [] };
  const limite = foot ? foot.getBoundingClientRect().top : p.getBoundingClientRect().bottom;
  const filhos = [...body.children].map(el => ({
    tag: el.className || el.tagName,
    topo: Math.round(el.getBoundingClientRect().top - body.getBoundingClientRect().top),
    base: Math.round(el.getBoundingClientRect().bottom - body.getBoundingClientRect().top),
    altura: Math.round(el.getBoundingClientRect().height),
  }));
  // `.pe-pagina` é ancorada na base de propósito: encostar no rodapé é o
  // comportamento correto dela, não um sintoma de transbordo.
  const fluxo = [...body.children].filter(el => !el.classList.contains('pe-pagina'));
  const ultimoEl = fluxo.length ? fluxo[fluxo.length - 1] : null;
  // `scrollHeight` nunca é menor que `clientHeight`, então ele só serve para
  // detectar transbordo — não para saber quanto sobrou. A folga real é a
  // distância entre a base do último bloco em fluxo e o filete do rodapé.
  const baseUltimo = ultimoEl ? ultimoEl.getBoundingClientRect().bottom : body.getBoundingClientRect().top;
  return {
    pagina: i + 1,
    tipo: 'corpo',
    altura_conteudo: body.scrollHeight,
    altura_caixa: body.clientHeight,
    transbordo_px: Math.max(0, body.scrollHeight - body.clientHeight),
    folga_px: Math.round(limite - baseUltimo),
    colide_com_rodape: ultimoEl ? ultimoEl.getBoundingClientRect().bottom > limite - 6 : false,
    blocos: filhos,
  };
})
"""


def slug(texto: str) -> str:
    """'Lojas Pompéia' -> 'Lojas_Pompeia'. Regra única, usada só aqui."""
    sem_acento = "".join(
        c for c in unicodedata.normalize("NFKD", texto) if not unicodedata.combining(c)
    )
    limpo = re.sub(r"[^A-Za-z0-9]+", "_", sem_acento).strip("_")
    return re.sub(r"_+", "_", limpo)


class _Silencioso(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *_):  # o servidor não polui a saída do script
        pass


def raiz_de_servico(html: Path) -> tuple[Path, str]:
    """
    Descobre de onde servir. Servir a pasta do HTML quebra qualquer referência
    `../assets/...`, porque o SimpleHTTPRequestHandler recusa sair da raiz — e o
    sintoma é um 404 silencioso que só aparece como "PDF sem estilo". Então
    contamos o `../` mais profundo do próprio HTML e subimos o mesmo tanto.
    Devolve (raiz, caminho_do_html_relativo_à_raiz).
    """
    texto = html.read_text(encoding="utf-8", errors="replace")
    profundidade = 0
    for ref in re.findall(r'(?:src|href)\s*=\s*["\']([^"\']+)["\']', texto):
        if "://" in ref or ref.startswith(("data:", "#", "/")):
            continue
        subidas = 0
        while ref.startswith("../"):
            ref = ref[3:]
            subidas += 1
        profundidade = max(profundidade, subidas)

    raiz = html.parent
    for _ in range(profundidade):
        if raiz.parent == raiz:
            break
        raiz = raiz.parent
    return raiz, html.relative_to(raiz).as_posix()


def sobe_servidor(raiz: Path):
    """Servidor efêmero em porta livre. Devolve (url_base, encerrar)."""
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        porta = s.getsockname()[1]
    handler = functools.partial(_Silencioso, directory=str(raiz))
    httpd = socketserver.TCPServer(("127.0.0.1", porta), handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return f"http://127.0.0.1:{porta}", httpd.shutdown


def abre_navegador(pw, motor: str):
    """Chrome do sistema primeiro: o chromium do playwright pode não estar baixado."""
    if motor == "chromium":
        return pw.chromium.launch()
    try:
        return pw.chromium.launch(channel="chrome")
    except Exception:
        return pw.chromium.launch()


def grava_metadata(pdf: Path, titulo: str, autor: str, assunto: str) -> bool:
    try:
        from pypdf import PdfReader, PdfWriter
    except ImportError:
        return False
    leitor = PdfReader(str(pdf))
    escritor = PdfWriter()
    escritor.append_pages_from_reader(leitor)
    escritor.add_metadata(
        {"/Title": titulo, "/Author": autor, "/Subject": assunto, "/Creator": "N1.AG"}
    )
    tmp = pdf.with_suffix(".tmp.pdf")
    with open(tmp, "wb") as f:
        escritor.write(f)
    tmp.replace(pdf)
    return True


def main() -> int:
    ap = argparse.ArgumentParser(description="Renderiza o HTML da proposta em PDF A4.")
    ap.add_argument("--html", required=True, type=Path)
    ap.add_argument("--saida", type=Path, help="caminho do PDF; derivado do orçamento se omitido")
    ap.add_argument("--orcamento", type=Path, help="03-orcamento.json, para nome e metadata")
    ap.add_argument("--titulo"); ap.add_argument("--autor", default="N1.AG"); ap.add_argument("--assunto")
    ap.add_argument("--motor", choices=("auto", "chromium"), default="auto")
    ap.add_argument("--auditar", action="store_true", help="mede transbordo antes de imprimir")
    ap.add_argument("--estrito", action="store_true", help="com transbordo, não emite o PDF")
    ap.add_argument("--relatorio", type=Path, help="onde gravar o relatorio-paginacao.json")
    ap.add_argument("--png", type=Path, help="diretório para os previews por página")
    ap.add_argument("--somente-auditoria", action="store_true")
    ap.add_argument("--debug", action="store_true", help="liga as guias visuais do CSS")
    args = ap.parse_args()

    html = args.html.resolve()
    if not html.is_file():
        print(f"erro: HTML não encontrado: {html}", file=sys.stderr)
        return EXIT_USO

    # --- nome do arquivo e metadata, a partir do orçamento quando houver ------
    orc = {}
    if args.orcamento and args.orcamento.is_file():
        orc = json.loads(args.orcamento.read_text(encoding="utf-8"))
    cliente = (orc.get("cliente") or {}).get("nome", "Cliente")
    prop = orc.get("proposta") or {}
    modelo = {"implantacao": "Implantação do E-commerce", "evolucao": "Evolução e Sustentação"}.get(
        prop.get("modelo_principal", ""), "Proposta"
    )
    data = orc.get("gerado_em") or prop.get("emitida_em") or "sem-data"

    saida = args.saida or Path("saida") / f"Proposta_Comercial_N1_{slug(cliente)}_{data}.pdf"
    saida = saida.resolve()
    saida.parent.mkdir(parents=True, exist_ok=True)

    titulo = args.titulo or f"Proposta Comercial N1.AG — {modelo} {cliente}"
    assunto = args.assunto or f"Proposta comercial — {cliente}"

    from playwright.sync_api import sync_playwright

    raiz, rel = raiz_de_servico(html)
    base, encerrar = sobe_servidor(raiz)
    codigo = EXIT_OK
    try:
        with sync_playwright() as pw:
            nav = abre_navegador(pw, args.motor)
            pg = nav.new_page(viewport={"width": 900, "height": 1273})
            falhas: list[str] = []
            pg.on("response", lambda r: falhas.append(f"{r.status} {r.url}") if r.status >= 400 else None)
            pg.goto(f"{base}/{rel}", wait_until="networkidle")
            if args.debug:
                pg.evaluate("() => document.body.classList.add('debug')")
            pg.evaluate("() => document.fonts.ready")
            pg.wait_for_timeout(250)

            # Um CSS ou logo em 404 produz um PDF "quase certo" — o pior modo de
            # falha possível, porque parece pronto. Aqui ele vira erro visível.
            for f in falhas:
                if not f.endswith("favicon.ico"):
                    print(f"erro: recurso não carregou — {f}", file=sys.stderr)
            if any(not f.endswith("favicon.ico") for f in falhas):
                nav.close()
                return EXIT_USO

            # --- a Poppins carregou mesmo? ---------------------------------
            # `document.fonts.check()` devolve true para família inexistente
            # (considera o fallback "disponível"), então não serve. O único
            # teste confiável é procurar a FontFace de fato carregada.
            carregadas = pg.evaluate(
                "() => [...document.fonts].filter(f => f.status === 'loaded')"
                ".map(f => f.family.replace(/[\"']/g, '') + ':' + f.weight)"
            )
            if not any("Poppins" in f for f in carregadas):
                print("erro: a Poppins não foi carregada — o PDF sairia em fonte de fallback.",
                      file=sys.stderr)
                nav.close()
                return EXIT_FONTE

            n_secoes = pg.evaluate("() => document.querySelectorAll('.page').length")

            # --- auditoria de paginação ------------------------------------
            relatorio = None
            if args.auditar or args.estrito:
                paginas = pg.evaluate(JS_AUDITORIA)
                transbordos = [p for p in paginas if p.get("transbordo_px", 0) > 0]
                colisoes = [p for p in paginas if p.get("colide_com_rodape")]
                relatorio = {
                    "html": str(html), "paginas": n_secoes,
                    "transbordos": len(transbordos), "colisoes_rodape": len(colisoes),
                    "detalhe": paginas,
                }
                destino = args.relatorio or saida.parent / "relatorio-paginacao.json"
                destino.parent.mkdir(parents=True, exist_ok=True)
                destino.write_text(json.dumps(relatorio, ensure_ascii=False, indent=2), encoding="utf-8")

                for p in transbordos:
                    print(f"TRANSBORDO página {p['pagina']}: {p['transbordo_px']}px além da caixa",
                          file=sys.stderr)
                for p in colisoes:
                    if p not in transbordos:
                        print(f"COLISÃO página {p['pagina']}: o último bloco encosta no rodapé",
                              file=sys.stderr)
                if (transbordos or colisoes) and args.estrito:
                    print("abortado: corrija a paginação antes de emitir o PDF.", file=sys.stderr)
                    nav.close()
                    return EXIT_PAGINACAO

            # --- previews por página ---------------------------------------
            if args.png:
                args.png.mkdir(parents=True, exist_ok=True)
                for i, el in enumerate(pg.query_selector_all(".page"), 1):
                    el.screenshot(path=str(args.png / f"pagina-{i:02d}.png"))

            if args.somente_auditoria:
                nav.close()
                print(f"auditoria concluída: {n_secoes} páginas, "
                      f"{(relatorio or {}).get('transbordos', 0)} transbordos")
                return EXIT_OK

            # --- impressão --------------------------------------------------
            pg.pdf(path=str(saida), format="A4", print_background=True,
                   prefer_css_page_size=True,
                   margin={"top": "0", "right": "0", "bottom": "0", "left": "0"})
            nav.close()
    finally:
        encerrar()

    # --- metadata -------------------------------------------------------------
    if not grava_metadata(saida, titulo, args.autor, assunto):
        print("aviso: pypdf ausente — PDF emitido sem metadata.", file=sys.stderr)
        codigo = EXIT_SEM_METADATA

    # --- o PDF tem o mesmo número de páginas que o HTML? ----------------------
    try:
        from pypdf import PdfReader
        n_pdf = len(PdfReader(str(saida)).pages)
        if n_pdf != n_secoes:
            print(f"erro: o HTML tem {n_secoes} seções .page mas o PDF saiu com {n_pdf} páginas.",
                  file=sys.stderr)
            codigo = EXIT_PAGINACAO
    except ImportError:
        pass

    print(f"PDF: {saida}  ({n_secoes} páginas)")
    return codigo


if __name__ == "__main__":
    sys.exit(main())
