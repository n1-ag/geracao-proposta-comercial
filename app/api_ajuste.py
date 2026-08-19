"""Rotas do ajuste em duas etapas: entender, depois aplicar.

A rota antiga (`/ajustar`) aceitava o texto sem olhar, derrubava a aprovação e
enfileirava minutos de agente — inclusive para pedidos que ela já sabia que não
seriam atendidos. Estas duas separam as coisas: a primeira **só lê** e não muda
nada; a segunda executa o que o vendedor confirmou.
"""

from __future__ import annotations

import json

import aplicador
import db
import executor
import modelo
import triagem
import workspace as ws
from api_execucao import reescrever_ajustes_md
from api_propostas import carregar
from roteador import erro_400, erro_409, rota

LIMITE = 4000


def _escopo(linha: dict) -> dict:
    caminho = ws.caminho(linha["slug"]) / "proposta" / "02-escopo.json"
    if not caminho.is_file():
        raise erro_409("sem_escopo", "esta proposta ainda não tem escopo")
    return json.loads(caminho.read_text("utf-8"))


@rota("POST", r"^/api/propostas/(?P<pid>\d+)/ajustar/interpretar$")
def interpretar(req, pid):
    """Lê o pedido e devolve o que entendeu. **Não muda nada.**"""
    linha = carregar(pid)
    texto = (req.json_do_corpo().get("texto") or "").strip()

    if len(texto) < 5:
        raise erro_400("ajuste_vazio", "escreva o que precisa mudar")
    if len(texto) > LIMITE:
        raise erro_400("ajuste_longo", f"o pedido passou de {LIMITE} caracteres")

    operacoes, custo, erro = triagem.interpretar(texto, _escopo(linha))
    if erro:
        raise erro_409("nao_entendi", erro)

    return {
        "operacoes": operacoes,
        "custo_usd": custo,
        # O que o vendedor mais quer saber antes de clicar: isto vai demorar?
        "instantaneas": sum(1 for o in operacoes if o["ok"] and o["tipo"] != "texto_livre"),
        "pelo_agente": sum(1 for o in operacoes if o["ok"] and o["tipo"] == "texto_livre"),
        "recusadas": sum(1 for o in operacoes if not o["ok"]),
    }


@rota("POST", r"^/api/propostas/(?P<pid>\d+)/ajustar/aplicar$")
def aplicar(req, pid):
    """Executa as operações confirmadas."""
    linha = carregar(pid)
    corpo = req.json_do_corpo()
    texto = (corpo.get("texto") or "").strip()
    brutas = corpo.get("operacoes") or []

    if linha["status"] in modelo.EXECUTANDO or linha["status"] == "enfileirada":
        raise erro_409("ja_na_fila", "esta proposta está executando; espere terminar")
    if not brutas:
        raise erro_400("sem_operacoes", "nenhuma operação para aplicar")

    # Revalida do zero. O que veio da tela passou por JavaScript, e o que passa
    # por JavaScript pode ter sido editado — a validação no cliente é conforto,
    # não garantia.
    operacoes = [o for o in triagem.validar(brutas, _escopo(linha)) if o["ok"]]
    if not operacoes:
        raise erro_400("sem_operacoes", "nenhuma das operações passou na validação")

    usuario = getattr(req, "usuario", None)
    quem = usuario["email"] if usuario else "app"

    with db.transacao():
        ordem = (db.valor("SELECT MAX(ordem) FROM ajustes WHERE proposta_id = ?",
                          (linha["id"],), 0) or 0) + 1
        ajuste_id = db.inserir("ajustes", {
            "proposta_id": linha["id"], "ordem": ordem,
            "texto": texto or "(operações escolhidas na tela)",
            "sobre_hash": linha["hash_orcamento"],
            "sobre_total_fmt": linha["total_fmt"],
            "interpretacao": json.dumps(operacoes, ensure_ascii=False),
            "criado_em": db.agora(),
        })

    saida = aplicador.aplicar(linha, operacoes, quem)
    if not saida.get("ok"):
        db.atualizar("ajustes", ajuste_id, {
            "resultado": json.dumps(saida.get("resultado") or [], ensure_ascii=False)})
        raise erro_409("falhou_aplicar", saida.get("erro") or "não deu para aplicar")

    livres = [t for t in (saida.get("livres") or []) if t.strip()]
    execucao_id = None

    if livres:
        # Só o que o Python não sabe fazer chega ao agente, e o `ajustes.md`
        # passa a conter apenas isso — em vez do texto inteiro, do qual a maior
        # parte já foi resolvida aqui.
        db.atualizar("ajustes", ajuste_id, {"texto": "\n\n".join(livres)})
        atual = db.um("SELECT * FROM propostas WHERE id = ?", (linha["id"],))
        reescrever_ajustes_md(atual)
        modelo.mudar_status(linha["id"], modelo.ENFILEIRADA, f"ajuste #{ordem}",
                            erro_mensagem=None)
        execucao_id = executor.enfileirar(linha["id"], "reajuste_02_03")
    else:
        # Nada para o agente: o ajuste já está inteiro no escopo, e deixá-lo
        # marcado como pendente faria a próxima rodada tentar reaplicá-lo.
        db.atualizar("ajustes", ajuste_id, {"aplicado_em": db.agora()})
        atual = db.um("SELECT * FROM propostas WHERE id = ?", (linha["id"],))
        reescrever_ajustes_md(atual)
        modelo.reabrir_para_gate(linha["id"], f"ajuste #{ordem} aplicado no gate")

    db.atualizar("ajustes", ajuste_id, {
        "resultado": json.dumps(saida["resultado"], ensure_ascii=False)})
    db.evento(linha["id"], "ajuste_aplicado",
              f"{len(operacoes)} operação(ões); {len(livres)} para o agente")

    import eventos
    final = db.um("SELECT * FROM propostas WHERE id = ?", (linha["id"],))
    eventos.proposta(final)

    return {"ok": True, "ajuste_id": ajuste_id, "execucao_id": execucao_id,
            "total_fmt": final["total_fmt"], "resultado": saida["resultado"]}
