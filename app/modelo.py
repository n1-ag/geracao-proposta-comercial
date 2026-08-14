"""Máquina de estados da proposta.

Duas dimensões, propositalmente separadas:

* `status` — onde a proposta está no pipeline (operacional).
* `status_comercial` — o que aconteceu com ela no mundo (enviada, aceita,
  recusada). Uma proposta recusada não deixa de ter PDF; o painel precisa das
  duas coisas.
"""

from __future__ import annotations

import db
from roteador import erro_409

RASCUNHO = "rascunho"
ENFILEIRADA = "enfileirada"
EXEC_01_03 = "executando_01_03"
EXEC_02_03 = "executando_02_03"
AGUARDANDO = "aguardando_aprovacao"
EXEC_04_06 = "executando_04_06"
GERADA = "gerada"
ERRO = "erro"

EXECUTANDO = {EXEC_01_03, EXEC_02_03, EXEC_04_06}

# Para onde cada estado pode ir. Transição fora daqui é bug, não caso de uso.
TRANSICOES = {
    RASCUNHO:    {ENFILEIRADA, ERRO},
    ENFILEIRADA: {EXEC_01_03, EXEC_02_03, EXEC_04_06, ERRO, RASCUNHO},
    EXEC_01_03:  {AGUARDANDO, ERRO, RASCUNHO},
    EXEC_02_03:  {AGUARDANDO, ERRO},
    AGUARDANDO:  {ENFILEIRADA, EXEC_02_03, EXEC_04_06, ERRO, RASCUNHO},
    EXEC_04_06:  {GERADA, ERRO, AGUARDANDO},
    GERADA:      {ENFILEIRADA, AGUARDANDO, ERRO},
    ERRO:        {ENFILEIRADA, RASCUNHO, AGUARDANDO, GERADA},
}

COMERCIAIS = {None: {"enviada"}, "enviada": {"aceita", "recusada", None},
              "aceita": {"enviada", "recusada"}, "recusada": {"enviada", "aceita"}}


def pode_ir(de: str, para: str) -> bool:
    return para in TRANSICOES.get(de, set())


def mudar_status(proposta_id: int, para: str, observacao: str = "", **extras) -> dict:
    """Aplica a transição dentro de uma transação, ou explica por que não dá."""
    with db.transacao():
        linha = db.um("SELECT * FROM propostas WHERE id = ?", (proposta_id,))
        if not linha:
            raise erro_409("proposta_sumiu", f"proposta {proposta_id} não existe mais")

        de = linha["status"]
        if de == para:
            if extras:
                db.atualizar("propostas", proposta_id, {**extras, "atualizado_em": db.agora()})
            return db.um("SELECT * FROM propostas WHERE id = ?", (proposta_id,))

        if not pode_ir(de, para):
            raise erro_409(
                "transicao_invalida",
                f"não dá para ir de '{de}' para '{para}'",
                {"de": de, "para": para},
            )

        db.atualizar("propostas", proposta_id, {"status": para, "atualizado_em": db.agora(), **extras})
        db.registrar_mudanca(proposta_id, "status", de, para, observacao)
        return db.um("SELECT * FROM propostas WHERE id = ?", (proposta_id,))


def mudar_comercial(proposta_id: int, para: str | None, observacao: str = "") -> dict:
    with db.transacao():
        linha = db.um("SELECT * FROM propostas WHERE id = ?", (proposta_id,))
        if not linha:
            raise erro_409("proposta_sumiu", f"proposta {proposta_id} não existe mais")
        if linha["status"] != GERADA:
            raise erro_409(
                "sem_pdf",
                "só dá para marcar o status comercial depois que o PDF foi gerado",
            )

        de = linha["status_comercial"]
        if de == para:
            return linha
        if para not in COMERCIAIS.get(de, set()):
            raise erro_409("transicao_invalida", f"não dá para ir de '{de or 'nenhum'}' para '{para}'")

        campos = {"status_comercial": para, "atualizado_em": db.agora()}
        if para == "enviada" and not linha["enviada_em"]:
            campos["enviada_em"] = db.agora()
        if para in ("aceita", "recusada"):
            campos["decidida_em"] = db.agora()
        elif para == "enviada":
            campos["decidida_em"] = None

        db.atualizar("propostas", proposta_id, campos)
        db.registrar_mudanca(proposta_id, "status_comercial", de, para or "nenhum", observacao)
        return db.um("SELECT * FROM propostas WHERE id = ?", (proposta_id,))


# -----------------------------------------------------------------------------
# Invariantes do gate
# -----------------------------------------------------------------------------


def exigir_aprovavel(linha: dict, hash_visto: str | None) -> None:
    """Só aprova quem está esperando aprovação, com orçamento na mão e sobre a
    versão que a tela mostrou."""
    if linha["status"] != AGUARDANDO:
        raise erro_409(
            "nao_aguardando",
            f"esta proposta está em '{linha['status']}', não há orçamento esperando aprovação",
        )
    if not linha["hash_orcamento"]:
        raise erro_409("sem_orcamento", "não há orçamento calculado para aprovar")
    if hash_visto and hash_visto != linha["hash_orcamento"]:
        raise erro_409(
            "orcamento_mudou",
            "o orçamento mudou desde que você abriu esta tela — recarregue e confira "
            "os valores antes de aprovar",
            {"visto": hash_visto, "atual": linha["hash_orcamento"]},
        )


def exigir_aprovado(linha: dict) -> None:
    """O portão do PDF. Nada de 04→06 sem aprovação vigente."""
    if linha["checkpoint_status"] != "aprovado":
        raise erro_409(
            "checkpoint_pendente",
            "o orçamento precisa ser aprovado antes de gerar o PDF",
        )


def derrubar_checkpoint(proposta_id: int, motivo: str) -> None:
    """Rebaixa a aprovação. Chamado sempre que 02 ou 03 são refeitas.

    Explicitamente, sem comparar hash: `hash_entrada` do precificar.py cobre só
    os TOML de preço e não se move quando o escopo muda. Confiar em divergência
    de hash deixaria passar exatamente o caso que este gate existe para pegar.
    """
    db.executar(
        "UPDATE propostas SET checkpoint_status='pendente', checkpoint_em=NULL, "
        "atualizado_em=? WHERE id=?",
        (db.agora(), proposta_id),
    )
    db.evento(proposta_id, "checkpoint_derrubado", motivo)
