"""Barramento de eventos em memória para o SSE.

Publish/subscribe simples: o motor publica, cada aba conectada consome de uma
fila própria. Nada é persistido — quem chega depois pega o estado atual pelas
rotas REST, não pelo histórico do barramento.
"""

from __future__ import annotations

import itertools
import queue
import threading

# Fila por assinante. Fila cheia significa aba travada ou lenta: descartamos o
# evento mais antigo em vez de bloquear o motor.
TAMANHO_FILA = 200

_assinantes: dict[int, queue.Queue] = {}
_trava = threading.Lock()
_proximo_id = itertools.count(1)
_proximo_evento = itertools.count(1)

# Último estado conhecido por tipo, para quem acabou de conectar receber o
# retrato de agora sem esperar o próximo acontecimento.
_ultimo: dict[str, dict] = {}


class Assinatura:
    def __init__(self):
        self.fila: queue.Queue = queue.Queue(maxsize=TAMANHO_FILA)
        with _trava:
            self.id = next(_proximo_id)
            _assinantes[self.id] = self.fila

    def fechar(self) -> None:
        with _trava:
            _assinantes.pop(self.id, None)

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.fechar()
        return False


def publicar(tipo: str, dados: dict) -> None:
    evento = {"id": next(_proximo_evento), "tipo": tipo, "dados": dados}

    if tipo in ("fila", "proposta"):
        _ultimo[tipo] = evento

    with _trava:
        filas = list(_assinantes.values())

    for fila in filas:
        try:
            fila.put_nowait(evento)
        except queue.Full:
            # Descarta o mais antigo e tenta de novo. Perder um "progresso" numa
            # aba lenta é aceitável; travar o motor não é.
            try:
                fila.get_nowait()
                fila.put_nowait(evento)
            except (queue.Empty, queue.Full):
                pass


def estado_inicial() -> list[dict]:
    """O que uma aba recém-conectada recebe antes do primeiro evento novo."""
    return list(_ultimo.values())


def quantos() -> int:
    with _trava:
        return len(_assinantes)


# -----------------------------------------------------------------------------
# Atalhos com o vocabulário do domínio
# -----------------------------------------------------------------------------


def fase(proposta_id: int, execucao_id: int, fase_: str, status: str, **extra) -> None:
    publicar("fase", {"proposta_id": proposta_id, "execucao_id": execucao_id,
                      "fase": fase_, "status": status, **extra})


def progresso(proposta_id: int, fase_: str, texto: str, tipo: str = "tool") -> None:
    publicar("progresso", {"proposta_id": proposta_id, "fase": fase_,
                           "tipo": tipo, "texto": texto})


def proposta(linha: dict) -> None:
    publicar("proposta", {k: linha.get(k) for k in (
        "id", "slug", "cliente", "status", "status_comercial", "fase_atual",
        "total_fmt", "total_tipo", "checkpoint_status", "erro_mensagem", "custo_usd",
    )})


def aviso(tipo: str, mensagem: str, **extra) -> None:
    publicar("aviso", {"tipo": tipo, "mensagem": mensagem, **extra})


def erro(proposta_id: int | None, fase_: str | None, mensagem: str) -> None:
    publicar("erro", {"proposta_id": proposta_id, "fase": fase_, "mensagem": mensagem})
