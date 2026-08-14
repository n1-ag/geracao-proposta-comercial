"""Rotas de execução, aprovação, ajustes e fila."""

from __future__ import annotations

from urllib.parse import parse_qs, urlparse

import artefatos
import config as cfg
import db
import executor
import modelo
import workspace as ws
from api_propostas import carregar
from roteador import erro_400, erro_409, rota

FASES_VALIDAS = {"01", "02", "03", "04", "05", "06"}


def _query(req) -> dict:
    return {k: v[0] for k, v in parse_qs(urlparse(req.path).query).items()}


def _publicar(pid: int) -> dict:
    import eventos

    linha = db.um("SELECT * FROM propostas WHERE id = ?", (pid,))
    eventos.proposta(linha)
    return linha


# -----------------------------------------------------------------------------
# Disparo
# -----------------------------------------------------------------------------


@rota("POST", r"^/api/propostas/(?P<pid>\d+)/executar$")
def executar(req, pid):
    linha = carregar(pid)
    corpo = req.json_do_corpo()
    desde = (corpo.get("desde") or "01").strip()

    if desde not in FASES_VALIDAS:
        raise erro_400("fase_invalida", f"fase '{desde}' não existe")
    if linha["status"] in modelo.EXECUTANDO or linha["status"] == "enfileirada":
        raise erro_409("ja_na_fila", "esta proposta já está na fila ou executando")

    base = ws.caminho(linha["slug"])
    if not (base / "entrada" / "transcricao.md").is_file():
        raise erro_409("sem_transcricao", "esta proposta não tem transcrição — edite o cadastro")

    # Retomar de 04 em diante é continuar depois do gate, e o gate precisa estar
    # de pé.
    if desde in ("04", "05", "06"):
        modelo.exigir_aprovado(linha)
        alvo = "bloco_04_06"
    else:
        alvo = "bloco_01_03"

    modelo.mudar_status(linha["id"], modelo.ENFILEIRADA, f"execução a partir da fase {desde}",
                        erro_mensagem=None)
    execucao_id = executor.enfileirar(linha["id"], alvo, desde_fase=desde)
    _publicar(linha["id"])

    return 202, {
        "execucao_id": execucao_id,
        "posicao_fila": db.valor(
            "SELECT COUNT(*) FROM execucoes WHERE status='fila' AND id <= ?", (execucao_id,), 1
        ),
    }


@rota("POST", r"^/api/propostas/(?P<pid>\d+)/rerender$")
def rerender(req, pid):
    """Refaz só o PDF, a partir do HTML que já existe. Não reexecuta agente
    nenhum — é o caminho para reabrir uma proposta antiga."""
    linha = carregar(pid)
    if linha["status"] in modelo.EXECUTANDO or linha["status"] == "enfileirada":
        raise erro_409("ja_na_fila", "esta proposta já está na fila ou executando")
    if not (ws.caminho(linha["slug"]) / "proposta" / "proposta.html").is_file():
        raise erro_409("sem_html", "esta proposta não tem `proposta.html` para renderizar")

    modelo.mudar_status(linha["id"], modelo.ENFILEIRADA, "re-render", erro_mensagem=None)
    execucao_id = executor.enfileirar(linha["id"], "rerender")
    _publicar(linha["id"])
    return 202, {"execucao_id": execucao_id}


@rota("POST", r"^/api/propostas/(?P<pid>\d+)/recalcular$")
def recalcular(req, pid):
    """Refaz 02→03 com a tabela de preços de hoje.

    Ação separada e explícita de propósito: recalcular derruba a aprovação e
    pode mudar o valor. Uma proposta de março não vira outro preço em silêncio.
    """
    linha = carregar(pid)
    corpo = req.json_do_corpo()
    if corpo.get("confirmo") is not True:
        raise erro_400(
            "confirmacao_necessaria",
            "recalcular derruba a aprovação e pode mudar o valor da proposta; "
            "envie confirmo=true para seguir",
        )
    if linha["status"] in modelo.EXECUTANDO or linha["status"] == "enfileirada":
        raise erro_409("ja_na_fila", "esta proposta já está na fila ou executando")

    modelo.mudar_status(linha["id"], modelo.ENFILEIRADA, "recálculo pedido", erro_mensagem=None)
    execucao_id = executor.enfileirar(linha["id"], "reajuste_02_03")
    _publicar(linha["id"])
    return 202, {"execucao_id": execucao_id}


# -----------------------------------------------------------------------------
# Fila
# -----------------------------------------------------------------------------


@rota("GET", r"^/api/fila$")
def fila(req):
    return executor.estado_da_fila()


@rota("POST", r"^/api/fila/cancelar$")
def cancelar(req):
    corpo = req.json_do_corpo()
    execucao_id = corpo.get("execucao_id")
    if not execucao_id:
        raise erro_400("execucao_id_obrigatorio", "diga qual execução cancelar")
    if not executor.cancelar(int(execucao_id)):
        raise erro_409("nao_cancelavel", "esta execução já terminou")
    return {"ok": True}


# -----------------------------------------------------------------------------
# Gate: o orçamento para aprovação
# -----------------------------------------------------------------------------


@rota("GET", r"^/api/propostas/(?P<pid>\d+)/orcamento$")
def orcamento(req, pid):
    """Tudo que a tela de aprovação precisa, em uma chamada."""
    linha = carregar(pid)
    base = ws.caminho(linha["slug"])
    retrato = artefatos.Retrato(base)

    if not retrato.orcamento:
        raise erro_409("sem_orcamento", "esta proposta ainda não tem orçamento calculado")

    memoria = base / "proposta" / "03-orcamento.md"
    briefing = base / "proposta" / "01-briefing.md"

    return {
        "proposta": linha,
        "orcamento": retrato.orcamento,
        "escopo": retrato.escopo,
        "memoria_md": memoria.read_text("utf-8") if memoria.is_file() else "",
        "briefing_md": briefing.read_text("utf-8") if briefing.is_file() else "",
        "alertas": db.buscar(
            "SELECT * FROM alertas WHERE proposta_id = ? ORDER BY "
            "CASE severidade WHEN 'alta' THEN 0 WHEN 'media' THEN 1 ELSE 2 END, id",
            (linha["id"],),
        ),
        "lacunas": db.buscar("SELECT * FROM lacunas WHERE proposta_id = ? ORDER BY id", (linha["id"],)),
        "ajustes": db.buscar("SELECT * FROM ajustes WHERE proposta_id = ? ORDER BY ordem", (linha["id"],)),
        # O front devolve este hash ao aprovar. Se o orçamento tiver mudado no
        # meio-tempo, a aprovação é recusada em vez de valer para outro número.
        "hash": linha["hash_orcamento"],
    }


@rota("POST", r"^/api/propostas/(?P<pid>\d+)/aprovar$")
def aprovar(req, pid):
    linha = carregar(pid)
    corpo = req.json_do_corpo()

    modelo.exigir_aprovavel(linha, corpo.get("hash"))

    altos = db.buscar(
        "SELECT * FROM alertas WHERE proposta_id = ? AND severidade = 'alta'", (linha["id"],)
    )
    if altos and not corpo.get("ciente_alertas_altos"):
        raise erro_409(
            "alertas_altos",
            f"há {len(altos)} alerta(s) de severidade alta; marque que está ciente antes de aprovar",
            [a["codigo"] for a in altos],
        )

    observacoes = []
    livre = (corpo.get("observacoes") or "").strip()
    if livre:
        observacoes.append(livre)

    for lacuna_id in corpo.get("lacunas_marcadas") or []:
        lac = db.um("SELECT * FROM lacunas WHERE id = ? AND proposta_id = ?",
                    (int(lacuna_id), linha["id"]))
        if lac:
            observacoes.append(f"Lacuna levada ao cliente: {lac['texto']}")

    for a in altos:
        observacoes.append(f"Ciente do alerta alto {a['codigo']}")

    import getpass

    observacoes.append(
        f"Aprovado no app N1 Propostas em {db.hoje()} (usuário do SO: {getpass.getuser()})"
    )

    # Escrever o checkpoint exige os singletons montados: é lá que o pipeline lê
    # o manifest na próxima fase.
    with executor.Lock(linha["id"], linha["slug"]):
        ws.montar(linha["slug"])
        executor.gravar_checkpoint(linha["id"], observacoes)
        ws.recolher()

    with db.transacao():
        db.atualizar("propostas", linha["id"], {
            "checkpoint_status": "aprovado",
            "checkpoint_em": db.agora(),
            "atualizado_em": db.agora(),
        })
        db.evento(linha["id"], "checkpoint_aprovado", linha["total_fmt"] or "")

    modelo.mudar_status(linha["id"], modelo.ENFILEIRADA, "orçamento aprovado")
    execucao_id = executor.enfileirar(linha["id"], "bloco_04_06")
    _publicar(linha["id"])

    return 202, {"execucao_id": execucao_id, "ok": True}


# -----------------------------------------------------------------------------
# Ajustes
# -----------------------------------------------------------------------------

CABECALHO_AJUSTES = """---
cliente: {cliente}
fase: checkpoint — ajustes pedidos pelo comercial
atualizado_em: {data}
---

# Ajustes pedidos no checkpoint

Cada bloco é um pedido do comercial sobre uma versão do orçamento. O bloco
marcado **PENDENTE** é o que precisa ser aplicado agora; os demais já foram
aplicados e ficam como histórico.

"""


def reescrever_ajustes_md(linha: dict) -> None:
    """Regenera `proposta/ajustes.md` a partir da tabela.

    O arquivo é o canal que chega ao agente e o que sobrevive se o banco sumir;
    a tabela é o que a UI lê. Manter os dois é redundância deliberada.
    """
    ajustes = db.buscar(
        "SELECT * FROM ajustes WHERE proposta_id = ? ORDER BY ordem", (linha["id"],)
    )
    partes = [CABECALHO_AJUSTES.format(cliente=linha["cliente"], data=db.hoje())]

    for a in ajustes:
        estado = "aplicado" if a["aplicado_em"] else "**PENDENTE**"
        sobre = f" — sobre {a['sobre_total_fmt']}" if a["sobre_total_fmt"] else ""
        hash_ = f" (`{a['sobre_hash']}`)" if a["sobre_hash"] else ""
        partes.append(
            f"## Ajuste {a['ordem']} — {a['criado_em'][:10]}{sobre}{hash_} — {estado}\n\n"
            f"{a['texto'].strip()}\n"
        )

    alvo = ws.caminho(linha["slug"]) / "proposta" / "ajustes.md"
    alvo.parent.mkdir(parents=True, exist_ok=True)
    alvo.write_text("\n".join(partes).rstrip() + "\n", "utf-8")


@rota("POST", r"^/api/propostas/(?P<pid>\d+)/ajustar$")
def ajustar(req, pid):
    """O comercial escreve o que está errado; o servidor re-roda 02→03."""
    linha = carregar(pid)
    corpo = req.json_do_corpo()

    texto = (corpo.get("texto") or "").strip()
    if len(texto) < 5:
        raise erro_400("ajuste_vazio", "escreva o que precisa mudar no orçamento")
    if len(texto) > 4000:
        raise erro_400("ajuste_longo", "o pedido de ajuste passou de 4000 caracteres")

    if linha["status"] in modelo.EXECUTANDO or linha["status"] == "enfileirada":
        raise erro_409("ja_na_fila", "esta proposta já está na fila ou executando")
    if not linha["hash_orcamento"]:
        raise erro_409("sem_orcamento", "não há orçamento para ajustar")

    with db.transacao():
        ordem = (db.valor("SELECT MAX(ordem) FROM ajustes WHERE proposta_id = ?",
                          (linha["id"],), 0) or 0) + 1
        ajuste_id = db.inserir("ajustes", {
            "proposta_id": linha["id"],
            "ordem": ordem,
            "texto": texto,
            "sobre_hash": linha["hash_orcamento"],
            "sobre_total_fmt": linha["total_fmt"],
            "criado_em": db.agora(),
        })
        db.evento(linha["id"], "ajuste_pedido", texto[:200])

    reescrever_ajustes_md(linha)

    # A aprovação anterior morre aqui, explicitamente. Não dá para deduzir isso
    # de divergência de hash: `hash_entrada` só cobre os TOML de preço e não se
    # move quando o escopo muda.
    modelo.derrubar_checkpoint(linha["id"], f"ajuste #{ordem} pedido pelo comercial")

    modelo.mudar_status(linha["id"], modelo.ENFILEIRADA, f"ajuste #{ordem}", erro_mensagem=None)
    execucao_id = executor.enfileirar(linha["id"], "reajuste_02_03")
    _publicar(linha["id"])

    return 202, {"ajuste_id": ajuste_id, "ordem": ordem, "execucao_id": execucao_id}


# -----------------------------------------------------------------------------
# Status comercial
# -----------------------------------------------------------------------------


@rota("POST", r"^/api/propostas/(?P<pid>\d+)/status$")
def status_comercial(req, pid):
    corpo = req.json_do_corpo()
    novo = corpo.get("status_comercial")
    if novo not in (*cfg.STATUS_COMERCIAIS, None, ""):
        raise erro_400("status_invalido",
                       f"use um de: {', '.join(cfg.STATUS_COMERCIAIS)} — ou vazio para limpar")

    linha = modelo.mudar_comercial(int(pid), novo or None, corpo.get("observacao") or "")
    ws.escrever_meta(linha["slug"], linha)
    _publicar(linha["id"])
    return {"ok": True, "proposta": linha}
