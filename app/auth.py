"""Autenticação: usuários, sessões e freio de força bruta.

O app nasceu local e sem login — a decisão era consciente, porque ele rodava em
`127.0.0.1` na máquina de quem o usava. Publicá-lo num subdomínio muda isso de
natureza: sem login, qualquer pessoa geraria propostas, leria dado de cliente e
gastaria a conta Claude.

Tudo com a stdlib, como o resto do app: `hashlib.scrypt` para a senha,
`secrets` para o token, e a sessão no SQLite — não num JWT — para que sair e
revogar funcionem de verdade.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone
from http.cookies import SimpleCookie

import db

COOKIE = "n1sessao"
DIAS_DE_SESSAO = 14

# Freio de força bruta. Uma senha compartilhada exposta na internet sem isso é
# chute livre: 8 tentativas por IP a cada 10 minutos.
JANELA_MIN = 10
TENTATIVAS_MAX = 8

# Parâmetros do scrypt: caro o bastante para atrapalhar quem tenta em massa,
# barato para um login humano.
#
# `maxmem` vai explícito porque o OpenSSL impõe um teto de 32 MB por padrão e
# `hashlib.scrypt` estoura nele sem aviso útil ("memory limit exceeded"). Com
# n=2^14 e r=8 são 16 MB de fato; o teto de 64 MB deixa margem e faz o
# comportamento ser o mesmo aqui e no servidor, seja qual for o default local.
SCRYPT = {"n": 2**14, "r": 8, "p": 1, "dklen": 64, "maxmem": 64 * 1024 * 1024}


# -----------------------------------------------------------------------------
# Senha
# -----------------------------------------------------------------------------


def _derivar(senha: str, salt: bytes) -> str:
    return hashlib.scrypt(senha.encode("utf-8"), salt=salt, **SCRYPT).hex()


def criar_hash(senha: str) -> tuple[str, str]:
    salt = secrets.token_bytes(16)
    return _derivar(senha, salt), salt.hex()


def conferir_senha(senha: str, senha_hash: str, salt_hex: str) -> bool:
    try:
        calculado = _derivar(senha, bytes.fromhex(salt_hex))
    except ValueError:
        return False
    # compare_digest: comparação de tempo constante, para não vazar o prefixo
    # correto pelo tempo de resposta.
    return hmac.compare_digest(calculado, senha_hash)


# -----------------------------------------------------------------------------
# Usuários
# -----------------------------------------------------------------------------


def criar_usuario(email: str, senha: str) -> int:
    senha_hash, salt = criar_hash(senha)
    return db.inserir(
        "usuarios",
        {
            "email": email.strip().lower(),
            "senha_hash": senha_hash,
            "salt": salt,
            "criado_em": db.agora(),
        },
    )


def trocar_senha(usuario_id: int, senha: str) -> None:
    senha_hash, salt = criar_hash(senha)
    with db.transacao():
        db.atualizar("usuarios", usuario_id, {"senha_hash": senha_hash, "salt": salt})
        # Trocar a senha derruba as sessões abertas: é o que faz a troca
        # significar alguma coisa quando a antiga vazou.
        db.executar("DELETE FROM sessoes WHERE usuario_id = ?", (usuario_id,))


def por_email(email: str) -> dict | None:
    return db.um("SELECT * FROM usuarios WHERE email = ?", (email.strip().lower(),))


# -----------------------------------------------------------------------------
# Sessão
# -----------------------------------------------------------------------------


def _expira_em() -> str:
    return (
        datetime.now(timezone.utc) + timedelta(days=DIAS_DE_SESSAO)
    ).replace(microsecond=0).isoformat()


def abrir_sessao(usuario_id: int, ip: str = "") -> str:
    token = secrets.token_urlsafe(32)
    db.inserir(
        "sessoes",
        {
            "token": token,
            "usuario_id": usuario_id,
            "criado_em": db.agora(),
            "expira_em": _expira_em(),
            "ip": ip,
        },
    )
    db.executar("UPDATE usuarios SET ultimo_acesso = ? WHERE id = ?", (db.agora(), usuario_id))
    return token


def fechar_sessao(token: str) -> None:
    db.executar("DELETE FROM sessoes WHERE token = ?", (token,))


def usuario_da_sessao(token: str | None) -> dict | None:
    if not token:
        return None
    linha = db.um(
        """SELECT u.id, u.email, s.token, s.expira_em
           FROM sessoes s JOIN usuarios u ON u.id = s.usuario_id
           WHERE s.token = ?""",
        (token,),
    )
    if not linha:
        return None
    if linha["expira_em"] < db.agora():
        fechar_sessao(token)
        return None
    return linha


def limpar_sessoes_vencidas() -> int:
    cur = db.executar("DELETE FROM sessoes WHERE expira_em < ?", (db.agora(),))
    return cur.rowcount or 0


# -----------------------------------------------------------------------------
# Freio de força bruta
# -----------------------------------------------------------------------------


def _desde() -> str:
    return (
        datetime.now(timezone.utc) - timedelta(minutes=JANELA_MIN)
    ).replace(microsecond=0).isoformat()


def bloqueado(ip: str) -> bool:
    n = db.valor(
        "SELECT COUNT(*) FROM tentativas_login WHERE ip = ? AND sucesso = 0 AND em > ?",
        (ip, _desde()),
        0,
    )
    return n >= TENTATIVAS_MAX


def registrar_tentativa(ip: str, sucesso: bool) -> None:
    db.inserir(
        "tentativas_login",
        {"ip": ip, "em": db.agora(), "sucesso": 1 if sucesso else 0},
    )
    if sucesso:
        # Acertou: zera o contador do IP, senão um acerto legítimo continuaria
        # penalizado pelas tentativas anteriores.
        db.executar("DELETE FROM tentativas_login WHERE ip = ? AND sucesso = 0", (ip,))


# -----------------------------------------------------------------------------
# Cookie
# -----------------------------------------------------------------------------


def ler_cookie(cabecalho: str | None) -> str | None:
    if not cabecalho:
        return None
    try:
        biscoitos = SimpleCookie()
        biscoitos.load(cabecalho)
    except Exception:  # noqa: BLE001
        return None
    valor = biscoitos.get(COOKIE)
    return valor.value if valor else None


def cabecalho_cookie(token: str, seguro: bool) -> str:
    partes = [
        f"{COOKIE}={token}",
        "Path=/",
        "HttpOnly",
        "SameSite=Lax",
        f"Max-Age={DIAS_DE_SESSAO * 86400}",
    ]
    # `Secure` só quando a conexão é HTTPS: em desenvolvimento, sobre
    # `http://127.0.0.1`, o navegador descartaria o cookie em silêncio.
    if seguro:
        partes.append("Secure")
    return "; ".join(partes)


def cabecalho_cookie_vazio() -> str:
    return f"{COOKIE}=; Path=/; HttpOnly; SameSite=Lax; Max-Age=0"
