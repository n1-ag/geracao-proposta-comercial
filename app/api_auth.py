"""Rotas de sessão: entrar, sair e saber quem está logado."""

from __future__ import annotations

import auth
import db
from roteador import RESPOSTA_JA_ENVIADA, erro_400, rota


def ip_do_pedido(req) -> str:
    """IP real do cliente.

    Atrás do nginx, `client_address` é sempre 127.0.0.1 — o freio de força
    bruta ficaria global em vez de por origem, e um único atacante trancaria o
    app para todo mundo. O `X-Forwarded-For` vem do nosso próprio proxy; o
    primeiro da lista é quem originou.
    """
    encaminhado = req.headers.get("X-Forwarded-For")
    if encaminhado:
        return encaminhado.split(",")[0].strip()
    return req.client_address[0] if req.client_address else "?"


def _https(req) -> bool:
    """Se a conexão que chegou ao usuário é HTTPS.

    O app fala HTTP com o nginx; quem sabe do TLS é o proxy, que informa em
    `X-Forwarded-Proto`. Sem isso o cookie sairia sem `Secure` em produção.
    """
    return (req.headers.get("X-Forwarded-Proto") or "").lower() == "https"


@rota("POST", r"^/api/login$")
def entrar(req):
    corpo = req.json_do_corpo()
    email = (corpo.get("email") or "").strip().lower()
    senha = corpo.get("senha") or ""
    ip = ip_do_pedido(req)

    if auth.bloqueado(ip):
        raise erro_400(
            "muitas_tentativas",
            f"tentativas demais deste endereço; espere {auth.JANELA_MIN} minutos",
        )

    if not email or not senha:
        raise erro_400("faltou_dado", "informe e-mail e senha")

    usuario = auth.por_email(email)
    # Confere a senha mesmo com usuário inexistente seria o ideal para não
    # revelar quais e-mails existem; aqui o app tem uma conta só e conhecida,
    # então a mensagem genérica basta.
    if not usuario or not auth.conferir_senha(senha, usuario["senha_hash"], usuario["salt"]):
        auth.registrar_tentativa(ip, False)
        raise erro_400("credenciais_invalidas", "e-mail ou senha incorretos")

    auth.registrar_tentativa(ip, True)
    token = auth.abrir_sessao(usuario["id"], ip)
    db.evento(None, "login", f"{email} de {ip}")

    req.responder_bytes(
        200,
        "application/json; charset=utf-8",
        b'{"ok": true}',
        {"Set-Cookie": auth.cabecalho_cookie(token, _https(req))},
    )
    return RESPOSTA_JA_ENVIADA


@rota("POST", r"^/api/logout$")
def sair(req):
    token = auth.ler_cookie(req.headers.get("Cookie"))
    if token:
        auth.fechar_sessao(token)
    req.responder_bytes(
        200,
        "application/json; charset=utf-8",
        b'{"ok": true}',
        {"Set-Cookie": auth.cabecalho_cookie_vazio()},
    )
    return RESPOSTA_JA_ENVIADA


@rota("GET", r"^/api/eu$")
def eu(req):
    usuario = getattr(req, "usuario", None)
    return {"email": usuario["email"] if usuario else None}
