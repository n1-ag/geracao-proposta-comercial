"""O motor: fila serial, lock dos singletons e a orquestração das seis fases.

Este módulo é a reimplementação em Python do que `.claude/commands/proposta.md`
faz conversando. A diferença que importa: as fases determinísticas (03 e 06a)
viram chamada de script, e o gate do orçamento vira invariante de código em vez
de instrução em prosa.

Uma execução por vez, sempre. `entrada/`, `proposta/` e `saida/` são singletons
do repositório; duas execuções simultâneas se sobrescreveriam.
"""

from __future__ import annotations

import json
import os
import queue
import threading
import time
from pathlib import Path

import artefatos
import claude_runner
import config as cfg
import db
import estimativas
import eventos
import modelo
import scripts_runner
import workspace as ws

# -----------------------------------------------------------------------------
# Lock dos singletons
# -----------------------------------------------------------------------------


def _processo_vivo(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True  # existe, é de outro usuário
    return True


def ler_lock() -> dict | None:
    try:
        return json.loads(cfg.LOCK.read_text("utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


class ConflitoDeExecucao(Exception):
    """Duas execuções disputando os singletons do repositório."""


class Lock:
    """Lock de arquivo com PID, para que um servidor morto não deixe o app travado."""

    def __init__(self, proposta_id: int, slug: str):
        self.proposta_id = proposta_id
        self.slug = slug

    def __enter__(self):
        cfg.DADOS_APP.mkdir(parents=True, exist_ok=True)
        conteudo = json.dumps(
            {"pid": os.getpid(), "iniciado_em": db.agora(),
             "proposta_id": self.proposta_id, "workspace": self.slug},
            ensure_ascii=False,
        )
        try:
            fd = os.open(cfg.LOCK, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            dono = ler_lock() or {}
            # Mensagem para quem lê na tela, não para quem lê o traceback.
            raise ConflitoDeExecucao(
                "outra proposta está sendo gerada agora; esta entra na fila e "
                "começa assim que aquela terminar"
                + (f" ({dono.get('workspace')})" if dono.get("workspace") else "")
            ) from None
        with os.fdopen(fd, "w") as f:
            f.write(conteudo)
        return self

    def __exit__(self, *_):
        cfg.LOCK.unlink(missing_ok=True)
        return False


def limpar_lock_orfao() -> str | None:
    """Chamado na subida do servidor. Um lock cujo dono morreu não protege nada."""
    dono = ler_lock()
    if not dono:
        return None
    pid = dono.get("pid")
    if pid and _processo_vivo(pid) and pid != os.getpid():
        return None
    cfg.LOCK.unlink(missing_ok=True)
    return f"lock órfão removido (pid {pid} não está mais rodando)"


# -----------------------------------------------------------------------------
# Recuperação na subida
# -----------------------------------------------------------------------------


def recuperar() -> list[str]:
    """Conserta o que ficou pela metade e **retoma sozinho** o que foi cortado.

    Reiniciar o serviço mata a fase que estiver rodando. Sem retomada
    automática, atualizar o app exigia esperar a fila esvaziar ou deixar
    proposta parada em erro à espera de um clique — o que na prática significa
    adiar correção porque tem trabalho em voo.

    Aqui a interrupção vira só um atraso: as fases já concluídas são
    preservadas, e a execução volta para a fila a partir da que morreu.
    """
    notas = []
    retomar: list[tuple[int, str, str]] = []   # (proposta_id, alvo, desde_fase)

    nota = limpar_lock_orfao()
    if nota:
        notas.append(nota)

    for e in db.buscar("SELECT * FROM execucoes WHERE terminou_em IS NULL"):
        # De onde recomeçar: a fase que estava aberta quando o corte veio.
        aberta = db.um(
            "SELECT fase FROM fases WHERE execucao_id = ? AND terminou_em IS NULL "
            "ORDER BY id DESC LIMIT 1",
            (e["id"],),
        )
        if e["status"] == "executando" and aberta:
            retomar.append((e["proposta_id"], e["alvo"], aberta["fase"].rstrip("ab")))
        elif e["status"] == "fila":
            retomar.append((e["proposta_id"], e["alvo"], e["desde_fase"] or ""))

        db.executar(
            "UPDATE execucoes SET status='interrompida', terminou_em=?, erro=? WHERE id=?",
            (db.agora(), "o servidor foi reiniciado; a execução foi retomada", e["id"]),
        )

    db.executar(
        "UPDATE fases SET status='erro', terminou_em=? WHERE terminou_em IS NULL",
        (db.agora(),),
    )

    presas = db.buscar(
        "SELECT * FROM propostas WHERE status IN ('executando_01_03','executando_02_03',"
        "'executando_04_06','enfileirada')"
    )
    vai_retomar = {p for p, _, _ in retomar}
    for p in presas:
        if p["id"] in vai_retomar:
            continue          # o estado é resolvido ao reenfileirar, logo abaixo
        retrato = artefatos.Retrato(ws.caminho(p["slug"]))
        derivado, erro = retrato.status_derivado()
        if derivado == "rascunho":
            derivado, erro = "erro", "interrompida antes de produzir qualquer artefato"
        elif derivado == "erro":
            erro = f"interrompida na fase {retrato.fase_derivada()} — dá para retomar dali"

        db.executar(
            "UPDATE propostas SET status=?, erro_mensagem=?, atualizado_em=? WHERE id=?",
            (derivado, erro, db.agora(), p["id"]),
        )
        db.registrar_mudanca(p["id"], "status", p["status"], derivado, "recuperada na subida")
        notas.append(f"#{p['id']} {p['cliente']}: {p['status']} → {derivado}")

    for proposta_id, alvo, desde in retomar:
        linha = db.um("SELECT * FROM propostas WHERE id = ?", (proposta_id,))
        if not linha:
            continue
        db.executar(
            "UPDATE propostas SET status='enfileirada', erro_mensagem=NULL, atualizado_em=? "
            "WHERE id=?",
            (db.agora(), proposta_id),
        )
        eid = enfileirar(proposta_id, alvo, desde_fase=desde or None, retomada=True)
        db.evento(proposta_id, "retomada_automatica",
                  f"{alvo} a partir da fase {desde or 'inicial'} (execução #{eid})")
        notas.append(
            f"#{proposta_id} {linha['cliente']}: retomada automática de {alvo}"
            + (f" na fase {desde}" if desde else "")
        )

    return notas


# -----------------------------------------------------------------------------
# Fila
# -----------------------------------------------------------------------------

_fila: queue.Queue = queue.Queue()
_cancelados: set[int] = set()
_atual: dict | None = None
_trava_atual = threading.Lock()


def estado_da_fila() -> dict:
    with _trava_atual:
        executando = dict(_atual) if _atual else None

    # A previsão acompanha o estado: quem espera precisa saber quanto falta, e
    # o número tem que encolher conforme as fases passam.
    if executando:
        import time as _t

        decorrido = _t.time() - executando.get("_marca_fase", _t.time())
        executando["previsao"] = estimativas.restante(
            executando["alvo"], executando.get("fase"), decorrido
        )

    return {
        "executando": executando,
        "aguardando": db.buscar(
            """SELECT e.id, e.proposta_id, e.alvo, e.enfileirada_em, p.cliente, p.slug
               FROM execucoes e JOIN propostas p ON p.id = e.proposta_id
               WHERE e.status = 'fila' ORDER BY e.id"""
        ),
    }


def registrar_linha(proposta_id: int, texto: str) -> None:
    """Guarda o que o agente está fazendo agora.

    Quem abre a tela no meio de uma execução precisa ver a atividade atual
    imediatamente — sem isso, a linha fica em "iniciando…" até o próximo evento,
    que pode demorar meio minuto.
    """
    with _trava_atual:
        if _atual and _atual.get("proposta_id") == proposta_id:
            _atual["ultima_linha"] = texto


def _publicar_fila() -> None:
    eventos.publicar("fila", estado_da_fila())


def enfileirar(proposta_id: int, alvo: str, desde_fase: str | None = None,
               retomada: bool = False) -> int:
    """Põe uma execução na fila.

    `retomada=True` marca que isto é a continuação de algo cortado no meio, e
    não um pedido novo. A diferença importa: numa retomada, uma fase cujo
    artefato já está pronto e coerente com as entradas é pulada, em vez de
    refeita — refazer custaria minutos e dólares para reescrever um arquivo que
    já está certo. Num pedido explícito, tudo o que foi pedido roda.
    """
    execucao_id = db.inserir(
        "execucoes",
        {
            "proposta_id": proposta_id,
            "alvo": alvo,
            "desde_fase": desde_fase,
            "status": "fila",
            "enfileirada_em": db.agora(),
            "retomada": 1 if retomada else 0,
        },
    )
    _fila.put(execucao_id)
    _publicar_fila()
    return execucao_id


def cancelar(execucao_id: int) -> bool:
    linha = db.um("SELECT * FROM execucoes WHERE id = ?", (execucao_id,))
    if not linha or linha["status"] not in ("fila", "executando"):
        return False

    _cancelados.add(execucao_id)

    if linha["status"] == "fila":
        db.executar(
            "UPDATE execucoes SET status='cancelada', terminou_em=? WHERE id=?",
            (db.agora(), execucao_id),
        )
        # Volta ao estado que os arquivos sustentam. Fixar 'rascunho' rebaixaria
        # uma proposta que já tem PDF só porque alguém desistiu de refazê-la.
        _resolver_estado(linha["proposta_id"], "execução cancelada antes de começar")
        _publicar_fila()
    return True


def _foi_cancelada(execucao_id: int) -> bool:
    return execucao_id in _cancelados


# -----------------------------------------------------------------------------
# Registro de fase
# -----------------------------------------------------------------------------


def _abrir_fase(execucao_id: int, proposta_id: int, fase: str, executor: str,
                comando: str, tentativa: int = 1) -> int:
    # A fila mostra em que fase a execução está agora; sem isto o painel ficaria
    # preso na primeira fase do bloco até o fim.
    with _trava_atual:
        if _atual and _atual.get("execucao_id") == execucao_id:
            _atual["fase"] = fase
            _atual["tentativa"] = tentativa
            _atual["_marca_fase"] = time.time()
    _publicar_fila()

    fid = db.inserir(
        "fases",
        {
            "execucao_id": execucao_id, "proposta_id": proposta_id, "fase": fase,
            "executor": executor, "comando": comando, "status": "executando",
            "tentativa": tentativa, "comecou_em": db.agora(),
        },
    )
    eventos.fase(proposta_id, execucao_id, fase, "executando", tentativa=tentativa)
    return fid


def _fechar_fase(fid: int, proposta_id: int, execucao_id: int, fase: str,
                 ok: bool, **campos) -> None:
    db.atualizar("fases", fid, {"status": "ok" if ok else "erro",
                                "terminou_em": db.agora(), **campos})
    eventos.fase(proposta_id, execucao_id, fase, "ok" if ok else "erro",
                 resumo=campos.get("resumo") or campos.get("stderr_cauda", "")[:200])


class FalhaDeFase(Exception):
    def __init__(self, fase: str, mensagem: str):
        super().__init__(mensagem)
        self.fase = fase
        self.mensagem = mensagem


# -----------------------------------------------------------------------------
# Fases
# -----------------------------------------------------------------------------


def _fase_claude(ctx: dict, fase: str, sufixo: str = "", tentativa: int = 1) -> None:
    """Roda uma fase de conteúdo e valida os quatro critérios de sucesso."""
    # Numa retomada, o que já está pronto e coerente com as entradas não é
    # refeito. É a diferença entre um restart custar segundos ou custar todas
    # as fases de novo.
    if ctx.get("retomada") and not sufixo and tentativa == 1:
        if not artefatos.artefatos_desatualizados(fase, cfg.SINGLETON_PROPOSTA):
            eventos.progresso(ctx["proposta_id"], fase,
                              "já estava pronta desta rodada — pulando", tipo="texto")
            db.evento(ctx["proposta_id"], "fase_pulada", f"fase {fase}: artefato já válido")
            return

    # Um alvo pode trocar o comando da fase por um prompt próprio — é assim que
    # o ajuste pontual evita reprocessar a fase 02 inteira.
    base = ctx.get("prompt_da_fase", {}).get(fase) or claude_runner.COMANDOS[fase]
    ferramentas = ctx.get("ferramentas_da_fase", {}).get(fase)
    prompt = base + (f"\n\n{sufixo}" if sufixo else "")
    log = ws.caminho(ctx["slug"]) / "logs" / f"{ctx['execucao_id']:04d}-{fase}-t{tentativa}.jsonl"

    rotulo = base if base.startswith("/") else "ajuste pontual no escopo"
    fid = _abrir_fase(ctx["execucao_id"], ctx["proposta_id"], fase, "claude",
                      rotulo, tentativa)
    inicio = time.time()

    def ao_iniciar(pid, session_id):
        db.atualizar("fases", fid, {"session_id": session_id})
        db.executar("UPDATE execucoes SET pid=? WHERE id=?", (pid, ctx["execucao_id"]))

    try:
        r = claude_runner.executar(
            fase, prompt, ctx["proposta_id"], log,
            ao_iniciar=ao_iniciar,
            cancelado=lambda: _foi_cancelada(ctx["execucao_id"]),
            ferramentas=ferramentas,
        )
    except claude_runner.Cancelado:
        _fechar_fase(fid, ctx["proposta_id"], ctx["execucao_id"], fase, False,
                     resumo="cancelada")
        raise

    db.atualizar("fases", fid, {"custo_usd": r.custo_usd})
    db.executar(
        "UPDATE execucoes SET custo_usd = custo_usd + ? WHERE id = ?",
        (r.custo_usd, ctx["execucao_id"]),
    )
    db.executar(
        "UPDATE propostas SET custo_usd = custo_usd + ? WHERE id = ?",
        (r.custo_usd, ctx["proposta_id"]),
    )

    campos = {
        "exit_code": r.exit_code, "duracao_ms": r.duracao_ms, "custo_usd": r.custo_usd,
        "resumo": r.resumo, "stderr_cauda": r.stderr_cauda, "log_caminho": str(log),
    }

    if r.negacoes:
        # Não reprova: o agente costuma tentar um comando exploratório, apanhar
        # do allow-list e seguir por outro caminho. Mas fica visível, porque
        # quando a fase falha esta é quase sempre a causa.
        barradas = claude_runner.resumir_negacoes(r.negacoes)
        eventos.progresso(
            ctx["proposta_id"], fase,
            f"bloqueado pelo allow-list de .claude/settings.json: {barradas}",
            tipo="aviso",
        )
        db.evento(ctx["proposta_id"], "permissao_negada", f"fase {fase}: {barradas}")

    if not r.ok:
        _fechar_fase(fid, ctx["proposta_id"], ctx["execucao_id"], fase, False, **campos)
        raise FalhaDeFase(fase, r.erro or "a fase falhou sem dizer por quê")

    # Terceiro critério: os artefatos existem e são posteriores às entradas da
    # fase. Comparar com o início da tentativa reprovava a retentativa em que o
    # agente, corretamente, não reescreveu um arquivo que já estava bom.
    faltando = artefatos.artefatos_desatualizados(fase, cfg.SINGLETON_PROPOSTA)
    if faltando:
        _fechar_fase(fid, ctx["proposta_id"], ctx["execucao_id"], fase, False, **campos)
        mensagem = f"a fase {fase} não deixou artefato válido: {', '.join(faltando)}"
        if r.negacoes:
            mensagem += (
                f". O allow-list de .claude/settings.json barrou "
                f"{claude_runner.resumir_negacoes(r.negacoes)} — provavelmente é a causa."
            )
        raise FalhaDeFase(fase, mensagem)

    _fechar_fase(fid, ctx["proposta_id"], ctx["execucao_id"], fase, True, **campos)
    _atualizar_manifest_fase(fase)
    ws.recolher()


def _fase_script(ctx: dict, fase: str, comando: str, funcao) -> tuple:
    fid = _abrir_fase(ctx["execucao_id"], ctx["proposta_id"], fase, "script", comando)
    inicio = time.time()
    resultado = funcao()
    duracao = int((time.time() - inicio) * 1000)
    ok = resultado[0]
    _fechar_fase(
        fid, ctx["proposta_id"], ctx["execucao_id"], fase, ok,
        duracao_ms=duracao, resumo=("" if ok else resultado[-1][:400]),
    )
    return resultado


# -----------------------------------------------------------------------------
# Manifest
# -----------------------------------------------------------------------------

NOME_DA_FASE = {
    "01": "01-briefing", "02": "02-escopo", "03": "03-orcamento",
    "04": "04-narrativa", "05": "05-html", "06": "06-revisao",
}
ORDEM = ["01", "02", "03", "04", "05", "06"]


def _ler_manifest(pasta: Path | None = None) -> dict:
    alvo = (pasta or cfg.SINGLETON_PROPOSTA) / "manifest.json"
    try:
        return json.loads(alvo.read_text("utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _escrever_manifest(m: dict, pasta: Path | None = None) -> None:
    destino = pasta or cfg.SINGLETON_PROPOSTA
    destino.mkdir(parents=True, exist_ok=True)
    (destino / "manifest.json").write_text(
        json.dumps(m, ensure_ascii=False, indent=2) + "\n", "utf-8"
    )


def preparar_manifest(linha: dict) -> None:
    m = _ler_manifest()
    m.setdefault("criado_em", db.hoje())
    m["cliente"] = linha["cliente"]
    m["atualizado_em"] = db.hoje()
    m.setdefault("checkpoint_humano", {"exigido_apos": "03", "status": "pendente"})
    m.setdefault(
        "fases",
        {
            NOME_DA_FASE[f]: {"status": "pendente", "versao": 0, "atualizado_em": None,
                              "artefato": f"proposta/{artefatos.ARTEFATO_DA_FASE[f][0]}"}
            for f in ORDEM
        },
    )
    m.setdefault("saida", {"pdf": None, "paginas": None, "transbordos": None, "render_em": None})
    m.setdefault("alertas", [])
    m.setdefault("rastreabilidade", [])
    _escrever_manifest(m)


def marcar_fase_no_manifest(pasta: Path, fase: str) -> None:
    """Marca a fase como concluída no manifest de um workspace específico.

    Existe para quem trabalha direto no workspace, sem montar nos singletons —
    hoje o fechamento comercial, que roda a fase 03 sem entrar na fila.
    """
    m = _ler_manifest(pasta)
    bloco = m.setdefault("fases", {}).setdefault(NOME_DA_FASE[fase], {"versao": 0})
    bloco["versao"] = int(bloco.get("versao") or 0) + 1
    bloco["status"] = "concluida"
    bloco["atualizado_em"] = db.hoje()
    for posterior in ORDEM[ORDEM.index(fase) + 1:]:
        outro = m["fases"].get(NOME_DA_FASE[posterior])
        if outro and outro.get("status") == "concluida":
            outro["status"] = "desatualizada"
    m["atualizado_em"] = db.hoje()
    _escrever_manifest(m, pasta)


def _atualizar_manifest_fase(fase: str) -> None:
    """Marca a fase como concluída e as posteriores como desatualizadas.

    O comando slash já faz parte disso quando roda pelo terminal; aqui é o
    servidor quem garante — o agente pode ter esquecido, e o manifest é o que
    o resto do pipeline lê.
    """
    m = _ler_manifest()
    fases = m.setdefault("fases", {})
    nome = NOME_DA_FASE[fase]
    bloco = fases.setdefault(nome, {"versao": 0})

    # Só incrementa se o comando não tiver incrementado antes de nós.
    if bloco.get("status") != "concluida" or not bloco.get("atualizado_em") == db.hoje():
        bloco["versao"] = int(bloco.get("versao") or 0) + 1
    bloco["status"] = "concluida"
    bloco["atualizado_em"] = db.hoje()
    bloco["artefato"] = f"proposta/{artefatos.ARTEFATO_DA_FASE[fase][0]}"
    if fase == "02":
        bloco["espelho"] = "proposta/02-escopo.json"
    if fase == "03":
        bloco["espelho"] = "proposta/03-orcamento.json"
    if fase == "05":
        bloco["saida"] = "proposta/proposta.html"

    for posterior in ORDEM[ORDEM.index(fase) + 1:]:
        outro = fases.get(NOME_DA_FASE[posterior])
        if outro and outro.get("status") == "concluida":
            outro["status"] = "desatualizada"

    m["fase_atual"] = fase
    m["atualizado_em"] = db.hoje()
    _escrever_manifest(m)


def gravar_checkpoint(proposta_id: int, slug: str, observacoes: list[str]) -> None:
    """Grava a aprovação no manifest, no formato que a fase 04 confere.

    Escreve **direto no workspace**, sem montar nos singletons. Aprovar é
    operação de metadado: exigir o lock de execução para isso fazia a aprovação
    falhar sempre que outra proposta estivesse gerando — e não havia motivo,
    porque quem for rodar a fase 04 monta o workspace na hora dela.
    """
    pasta = ws.caminho(slug) / "proposta"
    orc = artefatos.ler_json(pasta / "03-orcamento.json") or {}
    m = _ler_manifest(pasta)
    m["checkpoint_humano"] = {
        "exigido_apos": "03",
        "status": "aprovado",
        "aprovado_em": db.hoje(),
        "aprovado_sobre": {
            "orcamento_hash": orc.get("hash_entrada"),
            "total_fmt": (orc.get("totais") or {}).get("implantacao_total_fmt")
            or (orc.get("totais") or {}).get("evolucao_mensal_fmt"),
        },
        "observacoes": observacoes,
    }
    m["atualizado_em"] = db.hoje()
    _escrever_manifest(m, pasta)

    # Se esta proposta é a que está montada agora, o singleton também precisa
    # da aprovação: um `recolher()` posterior copiaria o manifest de lá por
    # cima do workspace e desfaria o que acabamos de gravar.
    if ws.montado() == slug:
        _escrever_manifest(m, cfg.SINGLETON_PROPOSTA)


# -----------------------------------------------------------------------------
# Sincronização banco ↔ orçamento
# -----------------------------------------------------------------------------


def sincronizar_orcamento(proposta_id: int, slug: str) -> dict:
    """Puxa do `03-orcamento.json` recém-escrito o que o banco precisa saber."""
    retrato = artefatos.Retrato(ws.caminho(slug))
    campos = retrato.campos()

    interessa = {
        k: campos[k] for k in (
            "total_cru", "total_fmt", "total_tipo", "evolucao_mensal", "evolucao_mensal_fmt",
            "prazo_fmt", "hash_orcamento", "hash_dados", "precos_versao",
            "modelo_res", "natureza_res", "plataforma_res",
        )
    }
    interessa["atualizado_em"] = db.agora()

    with db.transacao():
        db.atualizar("propostas", proposta_id, interessa)
        db.executar("DELETE FROM alertas WHERE proposta_id = ?", (proposta_id,))
        db.executar("DELETE FROM lacunas WHERE proposta_id = ?", (proposta_id,))
        for a in retrato.alertas():
            db.inserir("alertas", {**a, "proposta_id": proposta_id,
                                   "hash_orcamento": interessa["hash_orcamento"],
                                   "criado_em": db.agora()})
        for texto in retrato.lacunas():
            db.inserir("lacunas", {"proposta_id": proposta_id, "texto": texto,
                                   "hash_orcamento": interessa["hash_orcamento"],
                                   "criado_em": db.agora()})
    return interessa


# -----------------------------------------------------------------------------
# Blocos de execução
# -----------------------------------------------------------------------------


def _bloco_ate_orcamento(ctx: dict, fases: list[str]) -> None:
    """01 → 02 → 03, ou só 02 → 03 num reajuste."""
    for fase in fases:
        if fase == "03":
            ok, mensagem = scripts_runner.auditar_escopo()
            if not ok:
                raise FalhaDeFase("02", mensagem)

            ok, mensagem = _fase_script(
                ctx, "auditoria", "python3 scripts/auditar.py precos",
                scripts_runner.auditar_precos,
            )
            if not ok:
                raise FalhaDeFase("03", mensagem)

            # O valor fechado vive na proposta, não no orçamento: assim ele
            # sobrevive a um reajuste de escopo. Sem isso, pedir uma correção
            # no escopo desfaria em silêncio o preço combinado com o cliente.
            atual = db.um("SELECT valor_fechado, motivo_fechado FROM propostas WHERE id = ?",
                          (ctx["proposta_id"],)) or {}
            ok, _orc, mensagem = _fase_script(
                ctx, "03", "python3 scripts/precificar.py",
                lambda: scripts_runner.precificar(
                    valor_fechado=atual.get("valor_fechado"),
                    motivo_fechado=atual.get("motivo_fechado") or "",
                ),
            )
            if not ok:
                raise FalhaDeFase("03", mensagem)

            _atualizar_manifest_fase("03")
            ws.recolher()
            sincronizar_orcamento(ctx["proposta_id"], ctx["slug"])
        else:
            sufixo = ctx.get("sufixo_da_fase", {}).get(fase, "")
            _fase_claude(ctx, fase, sufixo)


def _bloco_pdf(ctx: dict, fases: list[str] | None = None) -> None:
    """04 → 05 → 06a (render, com retry de transbordo) → 06b (revisão).

    `fases` permite retomar do meio: pedir "retomar da 05" não pode reescrever a
    narrativa que já estava boa.
    """
    fases = fases or ["04", "05", "06"]
    dados: dict = {}

    if "04" in fases:
        _fase_claude(ctx, "04")

    tentativa = 1
    auditorias = 0
    sufixo = ""
    while True:
        if "05" in fases or tentativa > 1:
            _fase_claude(ctx, "05", sufixo, tentativa=tentativa)

        ok, mensagem = scripts_runner.auditar_html()
        if not ok:
            # Reprovar sem devolver o motivo mata a proposta com o trabalho
            # pronto ao lado. O montador recebe o relatório e corrige — é o
            # mesmo tratamento que o transbordo já tinha.
            if auditorias >= cfg.MAX_RETRY_AUDITORIA:
                raise FalhaDeFase("05", mensagem)
            auditorias += 1
            tentativa += 1
            sufixo = (
                "O HTML que você montou não passou na auditoria de números. "
                "Corrija **no `proposta/proposta.html`** e não mexa em mais nada.\n\n"
                f"{mensagem.strip()}\n\n"
                "Como corrigir:\n"
                "- Rótulo proibido: apague a linha `<tr>` ou o `<div class=\"stat\">` "
                "inteiro. Trocar o número não resolve — é o rótulo que não pode existir.\n"
                "- Esforço em horas: tire o `NNh · ` do `td.val`, deixando só o valor. "
                "Na linha de total, idem.\n"
                "- Se sobrar um cartão a menos na faixa de `.stat`, ponha no lugar um "
                "número que o orçamento já tenha (prazo, número de módulos), nunca hora "
                "nem valor da hora.\n"
                "- A cláusula de horas excedentes **fica**: é preço que o cliente paga.\n"
                "- Frase de insegurança (\"ainda não foi definido\", \"a confirmar\", "
                "\"fora do catálogo padrão\", \"estimativa própria\"...): reescreva a frase "
                "descrevendo o que a entrega cobre. Se a incerteza afeta o valor ou o "
                "escopo, mova-a para a seção de premissas como condição do projeto, no "
                "padrão de `dados/biblioteca-textos.md` — nunca como confissão de que algo "
                "não foi decidido.\n"
                f"Tentativa {auditorias} de {cfg.MAX_RETRY_AUDITORIA}."
            )
            eventos.progresso(ctx["proposta_id"], "05",
                              "a auditoria reprovou o HTML — devolvendo para o montador corrigir",
                              tipo="aviso")
            db.evento(ctx["proposta_id"], "auditoria_html_retry", mensagem[:600])
            continue

        ok, dados, mensagem = _fase_script(
            ctx, "06a", "python3 scripts/render_pdf.py",
            lambda: scripts_runner.renderizar(ctx.get("titulo_pdf")),
        )
        if ok:
            break

        if not dados.get("transbordo") or tentativa > cfg.MAX_RETRY_TRANSBORDO:
            raise FalhaDeFase("06a", mensagem)

        # Transbordou: em vez de desistir, devolve o relatório de paginação para
        # a fase 05 corrigir. Duas tentativas; depois é problema de texto, não
        # de montagem, e quem resolve é uma pessoa.
        tentativa += 1
        problemas = scripts_runner.paginas_problematicas()
        quais = ", ".join(
            f"página {p.get('pagina')} ({p.get('transbordo_px')}px além"
            + (", colide com o rodapé" if p.get("colide_com_rodape") else "") + ")"
            for p in problemas
        ) or "veja o relatório"
        sufixo = (
            f"O render anterior transbordou: {quais}. Leia "
            f"`saida/relatorio-paginacao.json` e corrija, nesta ordem: (1) mova o último "
            f"bloco da página que estourou para uma página de continuação; (2) reduza a "
            f"quantidade de itens em listas longas; (3) se o problema for texto longo "
            f"demais, reporte que é preciso voltar ao redator em vez de espremer.\n"
            f"Tentativa {tentativa} de {cfg.MAX_RETRY_TRANSBORDO + 1}.\n"
            f"Detalhe: {json.dumps(problemas, ensure_ascii=False)[:900]}"
        )
        eventos.progresso(ctx["proposta_id"], "05",
                          f"transbordo de paginação — refazendo a montagem (tentativa {tentativa})",
                          tipo="aviso")

    ws.recolher()
    _registrar_pdf(ctx, dados)

    # Auditoria final do PDF: páginas, fontes embutidas, metadados e marcadores
    # não resolvidos. Informativa — o PDF existe e já passou pelo render estrito;
    # reprovar aqui desfaria trabalho bom por um detalhe que uma pessoa resolve.
    pdf = cfg.SINGLETON_SAIDA / Path(dados["pdf"]).name
    if pdf.is_file():
        ok_pdf, aviso_pdf = scripts_runner.auditar_pdf(pdf)
        if not ok_pdf:
            eventos.progresso(ctx["proposta_id"], "06a",
                              f"a auditoria do PDF apontou algo: {aviso_pdf[:160]}", tipo="aviso")
            db.evento(ctx["proposta_id"], "auditoria_pdf", aviso_pdf[:600])

    if "06" not in fases:
        return

    # A revisão qualitativa é desejável, não obrigatória: o PDF já existe e é
    # válido. Falhar aqui não pode desfazer o que deu certo.
    try:
        _fase_claude(ctx, "06")
    except FalhaDeFase as e:
        eventos.progresso(ctx["proposta_id"], "06",
                          f"a revisão qualitativa não rodou ({e.mensagem[:120]}) — o PDF está pronto",
                          tipo="aviso")


def _registrar_pdf(ctx: dict, dados: dict) -> None:
    base = ws.caminho(ctx["slug"])
    pdf = Path(dados["pdf"])
    relativo = None
    achados = sorted((base / "saida").glob("*.pdf"))
    if achados:
        relativo = str(achados[-1].relative_to(base))
    elif pdf.is_file():
        relativo = f"saida/{pdf.name}"

    m = _ler_manifest()
    m["saida"] = {
        "pdf": relativo, "paginas": dados.get("paginas"),
        "transbordos": 0, "render_em": db.agora(),
    }
    _escrever_manifest(m)
    ws.recolher()

    db.atualizar("propostas", ctx["proposta_id"], {
        "pdf_caminho": relativo,
        "pdf_paginas": dados.get("paginas"),
        "pdf_gerado_em": db.agora(),
        "atualizado_em": db.agora(),
    })


# -----------------------------------------------------------------------------
# Laço do motor
# -----------------------------------------------------------------------------

PLANOS = {
    "bloco_01_03": (["01", "02", "03"], modelo.EXEC_01_03),
    "reajuste_02_03": (["02", "03"], modelo.EXEC_02_03),
    "bloco_04_06": ([], modelo.EXEC_04_06),
    "rerender": ([], modelo.EXEC_04_06),
}


def _executar(execucao: dict) -> None:
    global _atual

    proposta = db.um("SELECT * FROM propostas WHERE id = ?", (execucao["proposta_id"],))
    if not proposta:
        return

    alvo = execucao["alvo"]
    fases, estado = PLANOS[alvo]

    todas = ["04", "05", "06"] if alvo == "bloco_04_06" else ["01", "02", "03"]
    if alvo == "bloco_04_06":
        fases = list(todas)
    if execucao["desde_fase"] and execucao["desde_fase"] in todas:
        fases = todas[todas.index(execucao["desde_fase"]):]

    ctx = {
        "proposta_id": proposta["id"],
        "slug": proposta["slug"],
        "execucao_id": execucao["id"],
        "retomada": bool(execucao["retomada"] if "retomada" in execucao.keys() else 0),
        "titulo_pdf": _titulo_pdf(proposta),
        "sufixo_da_fase": {},
        "prompt_da_fase": {},
        "ferramentas_da_fase": {},
    }

    if alvo == "reajuste_02_03":
        # `/proposta-escopo` delega ao escopo-mapper, que relê transcrição,
        # briefing e o catálogo inteiro — minutos para mudar uma linha, e a
        # chance de mexer no que ninguém pediu. Aqui o agente abre só os três
        # arquivos que importam e edita o que foi pedido.
        ctx["prompt_da_fase"]["02"] = claude_runner.PROMPT_AJUSTE_RAPIDO
        ctx["ferramentas_da_fase"]["02"] = claude_runner.FERRAMENTAS_AJUSTE

    with _trava_atual:
        _atual = {"execucao_id": execucao["id"], "proposta_id": proposta["id"],
                  "cliente": proposta["cliente"], "alvo": alvo,
                  "fase": fases[0] if fases else "04",
                  "desde": db.agora(), "_marca_fase": time.time()}
    _publicar_fila()

    db.executar("UPDATE execucoes SET status='executando', comecou_em=? WHERE id=?",
                (db.agora(), execucao["id"]))
    modelo.mudar_status(proposta["id"], estado, f"execução #{execucao['id']}", erro_mensagem=None)
    eventos.proposta(db.um("SELECT * FROM propostas WHERE id = ?", (proposta["id"],)))

    erro_final = None
    try:
        with Lock(proposta["id"], proposta["slug"]):
            ws.montar(proposta["slug"])
            preparar_manifest(proposta)

            if alvo == "rerender":
                ok, dados, mensagem = _fase_script(
                    ctx, "06a", "python3 scripts/render_pdf.py",
                    lambda: scripts_runner.renderizar(ctx["titulo_pdf"]),
                )
                if not ok:
                    raise FalhaDeFase("06a", mensagem)
                ws.recolher()
                _registrar_pdf(ctx, dados)
            elif alvo == "bloco_04_06":
                atual = db.um("SELECT * FROM propostas WHERE id = ?", (proposta["id"],))
                modelo.exigir_aprovado(atual)
                _bloco_pdf(ctx, fases)
            else:
                _bloco_ate_orcamento(ctx, fases)
                modelo.derrubar_checkpoint(
                    proposta["id"],
                    "o orçamento foi recalculado; a aprovação anterior não vale mais",
                )

            ws.recolher()

            # Depois de recolher, nunca antes: `recolher()` copia o singleton
            # por cima do workspace, e o singleton ainda tem o `ajustes.md`
            # antigo. Fechar os ajustes antes fazia o **PENDENTE** voltar do
            # túmulo — e o agente da rodada seguinte reaplicava tudo de novo.
            if alvo == "reajuste_02_03":
                _marcar_ajustes_aplicados(proposta["id"], execucao["id"])

    except claude_runner.Cancelado:
        erro_final = "cancelada"
    except FalhaDeFase as e:
        erro_final = e.mensagem
    except ConflitoDeExecucao as e:
        erro_final = str(e)
    except Exception as e:  # noqa: BLE001
        # Erro não previsto é bug nosso, não do pipeline: o traceback tem que
        # aparecer no console de quem roda o servidor.
        import traceback

        traceback.print_exc()
        erro_final = f"erro interno do app — {type(e).__name__}: {e}"
    finally:
        # Recolher fora do lock também: se o montar falhou no meio, o que estava
        # nos singletons ainda precisa voltar para o dono.
        try:
            ws.recolher()
        except Exception:  # noqa: BLE001
            pass
        with _trava_atual:
            _atual = None
        _cancelados.discard(execucao["id"])

    if erro_final == "cancelada":
        db.executar("UPDATE execucoes SET status='cancelada', terminou_em=? WHERE id=?",
                    (db.agora(), execucao["id"]))
        _resolver_estado(proposta["id"], "execução cancelada")
    elif erro_final:
        db.executar("UPDATE execucoes SET status='erro', terminou_em=?, erro=? WHERE id=?",
                    (db.agora(), erro_final, execucao["id"]))
        modelo.mudar_status(proposta["id"], modelo.ERRO, "falha na execução",
                            erro_mensagem=erro_final)
        eventos.erro(proposta["id"], None, erro_final)
    else:
        db.executar("UPDATE execucoes SET status='concluida', terminou_em=? WHERE id=?",
                    (db.agora(), execucao["id"]))
        destino = modelo.GERADA if alvo in ("bloco_04_06", "rerender") else modelo.AGUARDANDO
        modelo.mudar_status(proposta["id"], destino, "execução concluída", erro_mensagem=None)

    linha = db.um("SELECT * FROM propostas WHERE id = ?", (proposta["id"],))
    ws.escrever_meta(proposta["slug"], linha)
    eventos.proposta(linha)
    _publicar_fila()


def _marcar_ajustes_aplicados(proposta_id: int, execucao_id: int) -> None:
    """Fecha os ajustes que esta rodada acabou de aplicar.

    Sem isto o ajuste fica "pendente" para sempre: a tela nunca mostra que ele
    foi processado, e — pior — `ajustes.md` continua marcando **PENDENTE**, de
    modo que o próximo ajuste faria o agente reaplicar todos os anteriores.
    """
    pendentes = db.buscar(
        "SELECT id FROM ajustes WHERE proposta_id = ? AND aplicado_em IS NULL",
        (proposta_id,),
    )
    if not pendentes:
        return
    agora = db.agora()
    for a in pendentes:
        db.atualizar("ajustes", a["id"], {"aplicado_em": agora, "execucao_id": execucao_id})
    db.evento(proposta_id, "ajustes_aplicados", f"{len(pendentes)} ajuste(s)")

    # `ajustes.md` é o que o agente lê; ele precisa refletir o novo estado.
    linha = db.um("SELECT * FROM propostas WHERE id = ?", (proposta_id,))
    if linha:
        import api_execucao

        api_execucao.reescrever_ajustes_md(linha)


def _resolver_estado(proposta_id: int, motivo: str) -> None:
    """Depois de um cancelamento, o estado sai do disco, não de um palpite.

    Uma proposta com PDF volta a `gerada`; uma com orçamento volta a
    `aguardando_aprovacao`. Só quem não produziu nada vira `erro`.
    """
    linha = db.um("SELECT * FROM propostas WHERE id = ?", (proposta_id,))
    if not linha:
        return
    retrato = artefatos.Retrato(ws.caminho(linha["slug"]))
    destino, erro = retrato.status_derivado()
    if destino == "rascunho" and linha["status"] not in ("rascunho", "enfileirada"):
        destino, erro = modelo.ERRO, motivo
    db.executar("UPDATE propostas SET status=?, erro_mensagem=?, atualizado_em=? WHERE id=?",
                (destino, erro if destino == modelo.ERRO else None, db.agora(), proposta_id))
    db.registrar_mudanca(proposta_id, "status", linha["status"], destino, motivo)


def _titulo_pdf(proposta: dict) -> str:
    modelo_ = proposta["modelo_res"] or proposta["modelo"] or "implantacao"
    assunto = "Implantação do E-commerce" if modelo_ == "implantacao" else "Evolução e Sustentação"
    return f"Proposta Comercial N1.AG — {assunto} {proposta['cliente']}"


def _laco() -> None:
    while True:
        execucao_id = _fila.get()
        try:
            linha = db.um("SELECT * FROM execucoes WHERE id = ?", (execucao_id,))
            if not linha or linha["status"] != "fila":
                continue
            if _foi_cancelada(execucao_id):
                _cancelados.discard(execucao_id)
                continue
            _executar(linha)
        except Exception:  # noqa: BLE001
            import traceback

            traceback.print_exc()
        finally:
            _fila.task_done()


_thread: threading.Thread | None = None


def iniciar() -> list[str]:
    """Sobe o motor e devolve as notas da recuperação, para o log de subida."""
    global _thread

    notas = recuperar()

    # Fila durável: o que estava esperando quando o servidor caiu volta a esperar.
    for e in db.buscar("SELECT id FROM execucoes WHERE status = 'fila' ORDER BY id"):
        _fila.put(e["id"])

    if _thread is None or not _thread.is_alive():
        _thread = threading.Thread(target=_laco, name="motor", daemon=True)
        _thread.start()

    return notas
