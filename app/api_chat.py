"""Rotas do chat da proposta.

`POST` responde 202 e devolve na hora: a resposta chega pelo SSE, escrita ao
vivo. Esperar o HTTP terminar significaria segurar a conexão por até um minuto e
mostrar uma tela parada justamente no momento em que há mais o que mostrar.
"""

from __future__ import annotations

import threading

import chat
import db
from api_propostas import carregar
from roteador import erro_400, erro_409, rota

# Uma pergunta por proposta de cada vez. Duas em paralelo atropelariam o
# `--resume`: as duas retomariam a mesma sessão e a segunda escreveria por cima
# do histórico da primeira.
_em_curso: set[int] = set()
_trava = threading.Lock()

LIMITE_PERGUNTA = 2000


@rota("GET", r"^/api/propostas/(?P<pid>\d+)/chat$")
def ler(req, pid):
    proposta = carregar(int(pid))
    return {
        "proposta_id": proposta["id"],
        "mensagens": chat.historico(proposta["id"]),
        "respondendo": int(pid) in _em_curso,
    }


@rota("POST", r"^/api/propostas/(?P<pid>\d+)/chat$")
def perguntar(req, pid):
    proposta = carregar(int(pid))
    pergunta = (req.json_do_corpo().get("pergunta") or "").strip()

    if not pergunta:
        raise erro_400("pergunta_vazia", "escreva a pergunta")
    if len(pergunta) > LIMITE_PERGUNTA:
        raise erro_400("pergunta_longa",
                       f"a pergunta passou de {LIMITE_PERGUNTA} caracteres")

    with _trava:
        if proposta["id"] in _em_curso:
            raise erro_409("chat_ocupado", "a pergunta anterior ainda está sendo respondida")
        _em_curso.add(proposta["id"])

    def rodar():
        try:
            chat.perguntar(proposta["id"], proposta["slug"], proposta["cliente"], pergunta)
        finally:
            with _trava:
                _em_curso.discard(proposta["id"])

    threading.Thread(target=rodar, daemon=True).start()
    return 202, {"ok": True}


@rota("DELETE", r"^/api/propostas/(?P<pid>\d+)/chat$")
def limpar(req, pid):
    """Esquece a conversa — inclusive a sessão, então a próxima pergunta começa do zero."""
    proposta = carregar(int(pid))
    db.executar("DELETE FROM conversas WHERE proposta_id = ?", (proposta["id"],))
    return {"ok": True}
