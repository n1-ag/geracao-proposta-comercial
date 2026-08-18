#!/usr/bin/env python3
"""Servidor do app N1 Propostas.

    python3 app/servidor.py

Stdlib pura: ThreadingHTTPServer + roteamento por tabela.

Escuta só em 127.0.0.1. Em uso local isso basta; publicado, quem fala com a
internet é o nginx, que termina o TLS e faz proxy para cá. O app nunca se expõe
direto.

Toda requisição passa por `Handler.autenticar()` antes de chegar ao roteador —
a lista `ABERTAS` é de exceções, para que uma rota nova nasça protegida.
"""

from __future__ import annotations

import contextlib
import json
import os
import queue
import shutil
import socket
import subprocess
import sys
import threading
import traceback
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import auth  # noqa: E402
import config as cfg  # noqa: E402
import dashboard  # noqa: E402
import db  # noqa: E402
import eventos  # noqa: E402
import executor as executor_mod  # noqa: E402
from roteador import (  # noqa: E402
    RESPOSTA_JA_ENVIADA, ErroHTTP, erro_400, erro_404, resolver, rota,
)

# -----------------------------------------------------------------------------
# Tipos de conteúdo dos estáticos
# -----------------------------------------------------------------------------

# O mapa do sistema varia entre distribuições; declarar o que o app serve evita
# fonte que não carrega e módulo JS recusado pelo navegador.
TIPOS = {
    ".html": "text/html; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".svg": "image/svg+xml",
    ".ttf": "font/ttf",
    ".woff2": "font/woff2",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".ico": "image/x-icon",
    ".md": "text/markdown; charset=utf-8",
    ".pdf": "application/pdf",
    ".txt": "text/plain; charset=utf-8",
}


def tipo_de(caminho: Path) -> str:
    return TIPOS.get(caminho.suffix.lower(), "application/octet-stream")


# -----------------------------------------------------------------------------
# Handler
# -----------------------------------------------------------------------------


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server_version = f"N1Propostas/{cfg.VERSAO_APP}"

    # -- infraestrutura ------------------------------------------------------

    def log_message(self, formato, *args):  # noqa: A003
        # O log padrão do BaseHTTPRequestHandler é ruidoso e vai para stderr sem
        # contexto. Só reportamos o que não for 2xx/3xx.
        try:
            status = int(args[1])
        except (IndexError, ValueError):
            status = 0
        if status >= 400:
            sys.stderr.write(f"[http] {self.command} {self.path} → {status}\n")

    def _corpo(self) -> bytes:
        """Lê exatamente Content-Length bytes. rfile.read() sem argumento pendura."""
        self.corpo_lido = True
        tamanho = int(self.headers.get("Content-Length") or 0)
        if tamanho <= 0:
            return b""
        return self.rfile.read(tamanho)

    def _drenar_corpo(self) -> None:
        """Descarta o corpo que o handler não leu.

        Em HTTP/1.1 a conexão é reaproveitada. Se um POST manda `{}` e o handler
        ignora o corpo, esses dois bytes ficam no socket e a requisição seguinte
        começa a ler neles — a linha de requisição vira `{}GET /... HTTP/1.1` e o
        servidor responde 501. Drenar aqui resolve para todos os handlers de uma
        vez, em vez de exigir que cada um se lembre de ler.
        """
        if getattr(self, "corpo_lido", False):
            return
        tamanho = int(self.headers.get("Content-Length") or 0)
        restante = tamanho
        while restante > 0:
            pedaco = self.rfile.read(min(restante, 65536))
            if not pedaco:
                break
            restante -= len(pedaco)
        self.corpo_lido = True

    def json_do_corpo(self) -> dict:
        bruto = self._corpo()
        if not bruto:
            return {}
        try:
            dados = json.loads(bruto.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as e:
            raise erro_400("json_invalido", f"corpo não é JSON válido: {e}") from e
        if not isinstance(dados, dict):
            raise erro_400("json_invalido", "o corpo precisa ser um objeto JSON")
        return dados

    def handle_expect_100(self) -> bool:
        # A transcrição chega com dezenas de KB; alguns clientes mandam
        # Expect: 100-continue e ficam esperando.
        self.send_response_only(100)
        self.end_headers()
        return True

    def responder_bytes(self, status: int, tipo: str, corpo: bytes, extra=None):
        self.send_response(status)
        self.send_header("Content-Type", tipo)
        self.send_header("Content-Length", str(len(corpo)))
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(corpo)

    def responder_json(self, status: int, dados):
        corpo = json.dumps(dados, ensure_ascii=False, default=str).encode("utf-8")
        self.responder_bytes(status, "application/json; charset=utf-8", corpo)

    def responder_erro(self, e: ErroHTTP):
        self.responder_json(
            e.status,
            {"erro": {"codigo": e.codigo, "mensagem": e.mensagem, "detalhe": e.detalhe}},
        )

    # -- estáticos -----------------------------------------------------------

    def servir_estatico(self, relativo: str):
        alvo = (cfg.STATIC / relativo.lstrip("/")).resolve()
        if not alvo.is_relative_to(cfg.STATIC.resolve()) or not alvo.is_file():
            raise erro_404(f"estático inexistente: {relativo}")
        cache = "no-cache" if alvo.suffix in (".html", ".css", ".js") else "max-age=86400"
        self.responder_bytes(200, tipo_de(alvo), alvo.read_bytes(), {"Cache-Control": cache})

    # -- despacho ------------------------------------------------------------

    # O que responde sem sessão. Tudo o mais exige login — a lista é de
    # exceções justamente para que uma rota nova nasça protegida por omissão.
    ABERTAS = {
        ("GET", "/login"),
        ("POST", "/api/login"),
        ("GET", "/api/saude"),      # healthcheck do nginx, sem dado sensível
    }

    def autenticar(self, metodo: str, caminho: str) -> bool:
        """Preenche `self.usuario` e diz se o pedido pode seguir."""
        self.usuario = auth.usuario_da_sessao(auth.ler_cookie(self.headers.get("Cookie")))
        if self.usuario or (metodo, caminho) in self.ABERTAS:
            return True

        # Navegação de página vai para o login; chamada de API recebe 401 e
        # deixa o front decidir — redirecionar um fetch daria HTML onde o
        # JavaScript espera JSON.
        aceita_html = "text/html" in (self.headers.get("Accept") or "")
        if aceita_html and not caminho.startswith("/api/"):
            self.send_response(302)
            self.send_header("Location", "/login")
            self.send_header("Content-Length", "0")
            self.end_headers()
        else:
            self.responder_json(
                401, {"erro": {"codigo": "nao_autenticado", "mensagem": "faça login para continuar"}}
            )
        return False

    def despachar(self, metodo: str):
        caminho = self.path.split("?", 1)[0].rstrip("/") or "/"
        self.corpo_lido = False
        try:
            # Estáticos são a casca e a identidade visual, servidos antes do
            # login porque a própria página de login depende deles.
            if caminho.startswith("/static/"):
                return self.servir_estatico(caminho[len("/static/"):])
            if caminho == "/login":
                return self.servir_estatico("login.html")

            if not self.autenticar(metodo, caminho):
                return

            if caminho == "/" or caminho == "/index.html":
                return self.servir_estatico("index.html")

            handler, grupos = resolver(metodo, caminho)
            resultado = handler(self, **grupos)

            if resultado is None:
                return self.responder_bytes(204, "text/plain", b"")
            if isinstance(resultado, tuple):
                status, dados = resultado
                return self.responder_json(status, dados)
            if resultado is RESPOSTA_JA_ENVIADA:
                return
            return self.responder_json(200, resultado)

        except ErroHTTP as e:
            self.responder_erro(e)
        except executor_mod.ConflitoDeExecucao as e:
            # Disputa pelas pastas de trabalho não é erro do servidor: é uma
            # espera. 409 com o motivo, nunca 500 com nome de classe Python.
            self.responder_erro(ErroHTTP(409, "ocupado", str(e)))
        except BrokenPipeError:
            pass  # cliente fechou a aba no meio; não é erro nosso
        except Exception as e:  # noqa: BLE001
            traceback.print_exc()
            self.responder_erro(
                ErroHTTP(500, "erro_interno", f"{type(e).__name__}: {e}")
            )
        finally:
            with contextlib.suppress(OSError, ValueError):
                self._drenar_corpo()

    def do_GET(self):  # noqa: N802
        self.despachar("GET")

    def do_HEAD(self):  # noqa: N802
        self.despachar("GET")

    def do_POST(self):  # noqa: N802
        self.despachar("POST")

    def do_PUT(self):  # noqa: N802
        self.despachar("PUT")

    def do_DELETE(self):  # noqa: N802
        self.despachar("DELETE")



class Servidor(ThreadingHTTPServer):
    allow_reuse_address = True
    daemon_threads = True  # sem isso, Ctrl-C fica preso nas threads de SSE


# -----------------------------------------------------------------------------
# Diagnóstico de ambiente
# -----------------------------------------------------------------------------


def _versao_claude() -> str | None:
    try:
        r = subprocess.run(
            ["claude", "--version"], capture_output=True, text=True, timeout=15
        )
        return r.stdout.strip() or None
    except (OSError, subprocess.SubprocessError):
        return None


def _tem_modulo(nome: str) -> bool:
    import importlib.util

    try:
        return importlib.util.find_spec(nome) is not None
    except (ImportError, ValueError):
        return False


def _precos_versao() -> str | None:
    import tomllib

    try:
        with open(cfg.DADOS_REPO / "precos.toml", "rb") as f:
            return tomllib.load(f).get("meta", {}).get("versao")
    except (OSError, tomllib.TOMLDecodeError):
        return None


def diagnostico() -> dict:
    """Tudo que precisa existir para o pipeline rodar ponta a ponta."""
    return {
        "claude": {"presente": shutil.which("claude") is not None, "versao": _versao_claude()},
        "chrome": shutil.which("google-chrome") is not None
        or shutil.which("google-chrome-stable") is not None,
        "playwright": _tem_modulo("playwright"),
        "pypdf": _tem_modulo("pypdf"),
        "poppler": all(shutil.which(b) for b in ("pdftotext", "pdfinfo", "pdffonts")),
        "python": f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
    }


def _lock_atual() -> dict | None:
    try:
        return json.loads(cfg.LOCK.read_text("utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _montado() -> str | None:
    try:
        return json.loads(cfg.ESTADO.read_text("utf-8")).get("montado")
    except (OSError, json.JSONDecodeError):
        return None


# -----------------------------------------------------------------------------
# Rotas de sistema
# -----------------------------------------------------------------------------


@rota("GET", r"^/api/saude$")
def api_saude(req):
    amb = diagnostico()
    return {
        "ok": amb["claude"]["presente"] and amb["chrome"] and amb["playwright"],
        "versao_app": cfg.VERSAO_APP,
        "porta": PORTA_EM_USO,
        "ambiente": amb,
        "precos_versao": _precos_versao(),
        "montado": _montado(),
        "lock": _lock_atual(),
        "economico": cfg.ECONOMICO,
    }


@rota("GET", r"^/api/catalogo$")
def api_catalogo(req):
    """Opções de enquadramento para o formulário, lidas de dados/."""
    import tomllib

    with open(cfg.DADOS_REPO / "precos.toml", "rb") as f:
        precos = tomllib.load(f)
    with open(cfg.DADOS_REPO / "condicoes-comerciais.toml", "rb") as f:
        condicoes = tomllib.load(f)

    plataformas = []
    for slug in cfg.PLATAFORMAS:
        bloco = precos.get("implantacao", {}).get("plataformas", {}).get(slug, {})
        plataformas.append(
            {
                "id": slug,
                "nome": bloco.get("nome") or slug.replace("-", " ").title(),
                "valor_base": bloco.get("valor_base"),
                "design_embutido": bloco.get("design_embutido"),
            }
        )

    return {
        "plataformas": plataformas,
        "modelos": cfg.MODELOS_PROPOSTA,
        "naturezas": cfg.NATUREZAS,
        "validade_dias_padrao": condicoes.get("meta", {}).get("validade_dias_padrao", 45),
        "precos_versao": precos.get("meta", {}).get("versao"),
    }


@rota("GET", r"^/api/dashboard$")
def api_dashboard(req):
    return dashboard.tudo()


@rota("GET", r"^/api/eventos$")
def api_eventos(req):
    """Stream de eventos (SSE), escrito na mão.

    Sem Content-Length e com Connection: close — é uma resposta que não termina.
    O heartbeat periódico serve para dois fins: manter proxies e o próprio
    navegador de fecharem a conexão ociosa, e detectar do nosso lado que a aba
    sumiu (o write levanta BrokenPipe).
    """
    req.send_response(200)
    req.send_header("Content-Type", "text/event-stream; charset=utf-8")
    req.send_header("Cache-Control", "no-cache")
    req.send_header("X-Accel-Buffering", "no")
    req.send_header("Connection", "close")
    req.end_headers()

    def enviar(evento: dict) -> None:
        corpo = json.dumps(evento["dados"], ensure_ascii=False, default=str)
        req.wfile.write(
            f"id: {evento['id']}\nevent: {evento['tipo']}\ndata: {corpo}\n\n".encode("utf-8")
        )
        req.wfile.flush()

    try:
        with eventos.Assinatura() as assinatura:
            # Quem acabou de conectar precisa do retrato de agora, não só do
            # próximo acontecimento.
            for inicial in eventos.estado_inicial():
                enviar(inicial)

            while True:
                try:
                    enviar(assinatura.fila.get(timeout=cfg.SSE_HEARTBEAT_S))
                except queue.Empty:
                    req.wfile.write(b": heartbeat\n\n")
                    req.wfile.flush()
    except (BrokenPipeError, ConnectionResetError, OSError):
        pass  # a aba fechou

    return RESPOSTA_JA_ENVIADA


# Importados pelo efeito colateral: cada módulo registra as rotas dele no
# roteador ao ser carregado. Ficam no fim para que `rota` já exista.
import api_auth  # noqa: E402,F401
import api_propostas  # noqa: E402,F401
import api_execucao  # noqa: E402,F401
import api_chat  # noqa: E402,F401
import api_escopo  # noqa: E402,F401
import api_artefatos  # noqa: E402,F401


# -----------------------------------------------------------------------------
# Subida
# -----------------------------------------------------------------------------

PORTA_EM_USO = cfg.PORTA


def escolher_porta() -> int:
    for porta in cfg.PORTAS_ALTERNATIVAS:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                s.bind((cfg.HOST, porta))
                return porta
            except OSError:
                continue
    raise SystemExit(
        f"erro: nenhuma porta livre entre {cfg.PORTA} e {cfg.PORTA + 9}. "
        f"Feche o outro servidor ou defina N1_PORTA."
    )


def preparar() -> list[str]:
    cfg.DADOS_APP.mkdir(parents=True, exist_ok=True)
    cfg.WORKSPACES.mkdir(parents=True, exist_ok=True)
    db.migrar()

    vencidas = auth.limpar_sessoes_vencidas()
    import executor

    notas = executor.iniciar()
    if vencidas:
        notas.append(f"{vencidas} sessão(ões) vencida(s) removida(s)")
    return notas


def main():
    global PORTA_EM_USO

    notas = preparar()
    PORTA_EM_USO = escolher_porta()
    url = f"http://{cfg.HOST}:{PORTA_EM_USO}"

    amb = diagnostico()
    faltando = [
        nome
        for nome, ok in (
            ("claude", amb["claude"]["presente"]),
            ("google-chrome", amb["chrome"]),
            ("playwright", amb["playwright"]),
            ("pypdf", amb["pypdf"]),
            ("poppler-utils", amb["poppler"]),
        )
        if not ok
    ]

    print(f"N1 Propostas {cfg.VERSAO_APP}  ·  {url}")
    if faltando:
        print(f"  atenção: faltando {', '.join(faltando)} — parte do pipeline não vai rodar")
    if cfg.ECONOMICO:
        print("  modo econômico ligado: todas as fases em sonnet")
    for nota in notas:
        print(f"  recuperação: {nota}")

    servidor = Servidor((cfg.HOST, PORTA_EM_USO), Handler)

    if os.environ.get("N1_ABRIR", "1") == "1":
        threading.Timer(0.5, lambda: webbrowser.open(url)).start()

    try:
        servidor.serve_forever()
    except KeyboardInterrupt:
        print("\nencerrando…")
    finally:
        servidor.shutdown()
        servidor.server_close()


if __name__ == "__main__":
    main()
