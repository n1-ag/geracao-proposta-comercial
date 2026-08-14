"""Acesso ao SQLite.

Uma conexão por thread (o servidor é multi-thread e sqlite3 não gosta de
conexão compartilhada). WAL aguenta um escritor + vários leitores, e o motor é
serial de qualquer forma; o RLock existe para o caso de um POST do usuário cair
junto com uma escrita do motor.
"""

from __future__ import annotations

import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path

import config as cfg

_local = threading.local()
_escrita = threading.RLock()

ESQUEMA_VERSAO = 1


def agora() -> str:
    """Timestamp ISO em UTC, com segundos. Formato único no banco inteiro."""
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def hoje() -> str:
    return datetime.now().strftime("%Y-%m-%d")


def conexao() -> sqlite3.Connection:
    con = getattr(_local, "con", None)
    if con is not None:
        return con

    cfg.DADOS_APP.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(cfg.BANCO, timeout=10, isolation_level=None)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("PRAGMA foreign_keys=ON")
    con.execute("PRAGMA busy_timeout=5000")
    con.execute("PRAGMA synchronous=NORMAL")
    _local.con = con
    return con


def migrar() -> None:
    """Cria o esquema se o banco for novo. Migrações futuras entram aqui,
    comparando PRAGMA user_version."""
    con = conexao()
    versao = con.execute("PRAGMA user_version").fetchone()[0]
    if versao >= ESQUEMA_VERSAO:
        return
    if versao == 0:
        ddl = (Path(__file__).resolve().parent / "esquema.sql").read_text("utf-8")
        with _escrita:
            con.executescript(ddl)
        return
    raise SystemExit(
        f"erro: banco na versão {versao}, o app espera {ESQUEMA_VERSAO}. "
        f"Não há migração automática — faça backup de {cfg.BANCO} e apague-o "
        f"para reconstruir com `python3 app/importar.py`."
    )


# -----------------------------------------------------------------------------
# Helpers de consulta
# -----------------------------------------------------------------------------


def buscar(sql: str, params=()) -> list[dict]:
    return [dict(r) for r in conexao().execute(sql, params).fetchall()]


def um(sql: str, params=()) -> dict | None:
    r = conexao().execute(sql, params).fetchone()
    return dict(r) if r else None


def valor(sql: str, params=(), padrao=None):
    r = conexao().execute(sql, params).fetchone()
    return padrao if r is None or r[0] is None else r[0]


def executar(sql: str, params=()) -> sqlite3.Cursor:
    with _escrita:
        return conexao().execute(sql, params)


def inserir(tabela: str, dados: dict) -> int:
    colunas = ", ".join(dados)
    marcas = ", ".join("?" for _ in dados)
    cur = executar(
        f"INSERT INTO {tabela} ({colunas}) VALUES ({marcas})", tuple(dados.values())
    )
    return cur.lastrowid


def atualizar(tabela: str, id_: int, dados: dict) -> None:
    if not dados:
        return
    sets = ", ".join(f"{k} = ?" for k in dados)
    executar(f"UPDATE {tabela} SET {sets} WHERE id = ?", (*dados.values(), id_))


class transacao:
    """Agrupa escritas relacionadas. Mantém o RLock durante toda a transação
    para que o motor e um request não intercalem BEGIN/COMMIT."""

    def __enter__(self):
        _escrita.acquire()
        conexao().execute("BEGIN IMMEDIATE")
        return conexao()

    def __exit__(self, tipo, *_):
        con = conexao()
        try:
            con.execute("ROLLBACK" if tipo else "COMMIT")
        finally:
            _escrita.release()
        return False


# -----------------------------------------------------------------------------
# Escritas de domínio usadas em vários lugares
# -----------------------------------------------------------------------------


def evento(proposta_id: int | None, tipo: str, detalhe: str = "") -> None:
    inserir(
        "eventos",
        {"proposta_id": proposta_id, "tipo": tipo, "detalhe": detalhe, "criado_em": agora()},
    )


def registrar_mudanca(proposta_id: int, campo: str, de, para, observacao: str = "") -> None:
    inserir(
        "historico_status",
        {
            "proposta_id": proposta_id,
            "campo": campo,
            "de": de,
            "para": para,
            "observacao": observacao,
            "em": agora(),
        },
    )


def tocar(proposta_id: int) -> None:
    executar("UPDATE propostas SET atualizado_em = ? WHERE id = ?", (agora(), proposta_id))
