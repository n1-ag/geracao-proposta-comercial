"""Registro de rotas e erros HTTP.

Módulo próprio para que `servidor.py` e os módulos de API possam se referir ao
mesmo registro sem import circular: todos importam daqui, ninguém importa o
servidor.
"""

from __future__ import annotations

import re
from typing import Callable


class ErroHTTP(Exception):
    """Erro que vira resposta JSON com status próprio."""

    def __init__(self, status: int, codigo: str, mensagem: str, detalhe=None):
        super().__init__(mensagem)
        self.status = status
        self.codigo = codigo
        self.mensagem = mensagem
        self.detalhe = detalhe


def erro_400(codigo: str, mensagem: str, detalhe=None) -> ErroHTTP:
    return ErroHTTP(400, codigo, mensagem, detalhe)


def erro_404(mensagem: str = "não encontrado") -> ErroHTTP:
    return ErroHTTP(404, "nao_encontrado", mensagem)


def erro_409(codigo: str, mensagem: str, detalhe=None) -> ErroHTTP:
    return ErroHTTP(409, codigo, mensagem, detalhe)


# Sentinela para handlers que escrevem a resposta na mão (SSE, PDF, PNG).
RESPOSTA_JA_ENVIADA = object()


# (método, regex compilada, função). A função recebe (req, **grupos nomeados) e
# devolve um dict (JSON 200), uma tupla (status, dict), None (204), ou a
# sentinela acima.
ROTAS: list[tuple[str, re.Pattern, Callable]] = []


def rota(metodo: str, padrao: str):
    def registrar(fn):
        ROTAS.append((metodo, re.compile(padrao), fn))
        return fn

    return registrar


def resolver(metodo: str, caminho: str):
    """Devolve (handler, grupos). Levanta 404 ou 405."""
    caminho_existe = False
    for m, rx, fn in ROTAS:
        casou = rx.match(caminho)
        if not casou:
            continue
        caminho_existe = True
        if m == metodo:
            return fn, casou.groupdict()
    if caminho_existe:
        raise ErroHTTP(405, "metodo_nao_permitido", f"{metodo} não vale para {caminho}")
    raise erro_404(f"rota desconhecida: {caminho}")
