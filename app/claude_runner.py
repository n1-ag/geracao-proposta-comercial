"""Execução headless do Claude Code, uma fase por vez.

O app substitui o orquestrador conversacional (`.claude/commands/proposta.md`)
por código Python, mas as fases de conteúdo continuam sendo os mesmos slash
commands do repositório — invocados por `claude -p`. O que este módulo faz é:
montar a linha de comando certa, ler o `stream-json` linha a linha e traduzir o
que passa por ali em progresso legível na tela.

Dois cuidados que definem se isso funciona ou não:

1. **Ninguém pode fazer pergunta.** Os comandos do repositório foram escritos
   para uma conversa ("pergunte se deve refazer"). Sem `CONTRATO_HEADLESS`, uma
   fase trava esperando resposta até o timeout.
2. **O exit code não é o sinal de sucesso.** Quem diz se deu certo é o evento
   `result` do stream, junto com a existência dos artefatos no disco.

Uma ferramenta negada pelo allow-list (`permission_denials`) é registrada e
mostrada, mas **não reprova a fase por si só**: o agente frequentemente tenta um
comando exploratório, é barrado e resolve de outro jeito. Quem reprova é o
artefato ausente. Quando os dois acontecem juntos, a negação vira a explicação
do erro — é quase sempre a causa.
"""

from __future__ import annotations

import contextlib
import json
import os
import re
import signal
import subprocess
import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path

import config as cfg
import eventos

# Slash command de cada fase de conteúdo. As fases 03 e 06a não estão aqui: são
# script, e o motor as chama direto, sem pagar um turno de LLM para digitar uma
# linha de comando.
# De quanto em quanto tempo avisar que a fase continua viva durante o silêncio.
SINAL_DE_VIDA_S = 30

COMANDOS = {
    "01": "/proposta-briefing",
    "02": "/proposta-escopo",
    "04": "/proposta-narrativa",
    "05": "/proposta-html",
    "06": "/proposta-revisao",
}

# Ferramentas por fase. O ajuste cirúrgico não recebe `Task`: é justamente a
# delegação ao subagente que o fazia reler a transcrição e o catálogo inteiros,
# oito minutos para mudar uma linha.
FERRAMENTAS_AJUSTE = "Read Edit Write Grep Glob"

# Um ajuste no escopo quase nunca é remapear: é tirar um item, trocar a
# complexidade, corrigir uma quantidade. Reprocessar a fase 02 do zero para
# isso custa minutos e reabre decisões que já estavam certas.
PROMPT_AJUSTE_RAPIDO = """\
Aplique os ajustes pendentes ao escopo desta proposta. **Não remapeie nada.**

1. Leia `proposta/02-escopo.json`, `proposta/02-escopo.md` e `proposta/ajustes.md`.
2. Em `ajustes.md`, aplique **todos** os blocos marcados **PENDENTE** — pode ser
   mais de um. Se um deles já estiver de fato aplicado no escopo, não o aplique
   de novo (duplicaria o item); registre que já estava valendo.
3. Consulte `dados/catalogo-modulos.toml` **apenas** para os itens que os ajustes
   tocam — para pegar o `catalogo_id` correto e o `criterio_complexidade` de quem
   você precisar classificar.
4. Edite `proposta/02-escopo.json` mudando somente o que os ajustes pedem.
5. Atualize `proposta/02-escopo.md` para continuar dizendo a mesma coisa que o
   JSON. Os dois são espelhos: se o JSON diz `alta`, **toda** menção àquele item
   no markdown — tabela, texto corrido, lacuna que descreva a classificação —
   passa a dizer `alta` também. Deixar os dois divergentes reprova a auditoria e
   é pior do que não ter aplicado o ajuste.
6. Acrescente ao fim de `02-escopo.md` uma seção "Ajuste aplicado — <data>" com
   uma linha por mudança: o que mudou e por quê. Se algo pedido **não** pôde ser
   aplicado, diga ali e explique.

**Item que os ajustes não citam não se toca.** Nem redação, nem ordem, nem
origem, nem observação. O trabalho é cirúrgico.

Regras que continuam valendo:
- Você **não precifica**. Não escreva cifrão, não escreva total, não some horas —
  nem para citar, nem para negar que fez, nem entre crases. Os caracteres de
  moeda não podem aparecer em `02-escopo.md`: a auditoria procura por eles e
  reprova a fase. Pediram um preço específico? Registre na seção que não pôde ser
  aplicado — quem fecha valor é uma pessoa, no botão «Fechar valor» da tela.
- Item cotado precisa de `origem` não vazia e, quando o catálogo exigir,
  complexidade `baixa`, `media` ou `alta`.
- Não cote item que esteja no escopo padrão: ele já vem no valor base.
- Não invoque subagente. Faça você mesmo, direto nos arquivos.
"""


@dataclass
class Resultado:
    ok: bool
    fase: str
    session_id: str | None = None
    exit_code: int | None = None
    custo_usd: float = 0.0
    turnos: int = 0
    duracao_ms: int = 0
    resumo: str = ""
    erro: str = ""
    bloco: dict | None = None          # o JSON final que o contrato headless pede
    negacoes: list = field(default_factory=list)   # ferramentas barradas pelo allow-list
    stderr_cauda: str = ""
    log: str | None = None


# -----------------------------------------------------------------------------
# Humanização do stream
# -----------------------------------------------------------------------------

def _curto(caminho: str) -> str:
    """Caminho relativo à raiz do repo, para caber na linha de progresso."""
    try:
        return str(Path(caminho).resolve().relative_to(cfg.RAIZ))
    except (ValueError, OSError):
        return caminho


def _texto_rate_limit(info: dict) -> str:
    """Mensagem de limite com a hora real do reset, não o epoch cru."""
    quando = info.get("resetsAt")
    if quando:
        from datetime import datetime

        try:
            hora = datetime.fromtimestamp(int(quando)).strftime("%H:%M")
            return f"limite de uso da conta atingido; ele reseta às {hora}"
        except (ValueError, OSError, OverflowError):
            pass
    return "limite de uso da conta atingido"


def _ultima_frase(texto: str, limite: int = 150) -> str:
    """A última frase inteira do que o agente escreveu até agora.

    Cortar os últimos N caracteres crus faz a linha de progresso começar no meio
    de uma palavra ("ntrada/dados-cliente.md existem…"), o que parece defeito.
    Preferimos recomeçar na última fronteira de frase.
    """
    limpo = " ".join((texto or "").split())
    if not limpo:
        return ""
    if len(limpo) <= limite:
        return limpo

    cauda = limpo[-limite:]
    for marca in (". ", "! ", "? ", "; ", ": "):
        corte = cauda.find(marca)
        if 0 <= corte < limite - 30:
            return cauda[corte + len(marca):].strip()
    # Sem fronteira de frase, ao menos não parta a palavra.
    espaco = cauda.find(" ")
    return cauda[espaco + 1:].strip() if espaco > 0 else cauda.strip()


def descrever_ferramenta(nome: str, entrada: dict) -> str | None:
    """Traduz um tool_use em uma frase que o comercial entende.

    Devolve None para o que não vale a pena mostrar — a linha de progresso é
    uma só, e enchê-la de ruído esconde o que importa.
    """
    if nome == "Read":
        return f"Lendo {_curto(entrada.get('file_path', '?'))}"
    if nome in ("Write", "Edit"):
        return f"Escrevendo {_curto(entrada.get('file_path', '?'))}"
    if nome == "Task":
        agente = entrada.get("subagent_type") or "subagente"
        # Enquanto o subagente trabalha, o stream do pai fica em silêncio — pode
        # levar minutos. Dizer isso evita que a tela pareça travada.
        return f"Delegando para o agente {agente} — isso costuma levar alguns minutos"
    if nome == "Bash":
        comando = (entrada.get("command") or "").strip()
        if "auditar.py" in comando:
            sub = comando.split("auditar.py", 1)[1].strip().split()[:1]
            return f"Auditando {sub[0] if sub else ''}".strip()
        return f"Rodando {comando[:70]}"
    if nome in ("Glob", "Grep"):
        return f"Procurando {entrada.get('pattern', '')}"[:80]
    return None


# -----------------------------------------------------------------------------
# Linha de comando
# -----------------------------------------------------------------------------


def montar_comando(fase: str, prompt: str, session_id: str,
                   ferramentas: str | None = None) -> list[str]:
    extras = ["--allowedTools", *ferramentas.split()] if ferramentas else []
    return [
        "claude", "-p", prompt,
        "--output-format", "stream-json",
        "--verbose",                                # exigido pelo stream-json
        "--include-partial-messages",               # deltas → linha viva na UI
        "--permission-mode", "acceptEdits",
        # O allow-list de .claude/settings.json é barreira real (Bash(rm:*) está
        # negado). Contorná-lo com bypassPermissions trocaria um erro visível por
        # um estrago silencioso.
        "--setting-sources", "user,project",        # sem isso os subagentes somem
        # Os MCP servers do ambiente entram sozinhos e um deles pode estar
        # quebrado ou pedindo autenticação. Nenhuma fase precisa deles.
        "--strict-mcp-config", "--mcp-config", '{"mcpServers":{}}',
        "--model", cfg.modelo_da_fase(fase),
        "--max-budget-usd", str(cfg.TETO_USD_FASE),
        "--session-id", session_id,
        "--append-system-prompt", cfg.CONTRATO_HEADLESS,
        *extras,
    ]


def _ambiente() -> dict:
    """Ambiente limpo do que atropelaria o --model."""
    env = dict(os.environ)
    for chave in ("ANTHROPIC_MODEL", "ANTHROPIC_SMALL_FAST_MODEL", "CLAUDE_CODE_MODEL"):
        env.pop(chave, None)
    return env


def resumir_negacoes(negacoes: list) -> str:
    """Frase curta dizendo o que foi barrado, para log e mensagem de erro."""
    if not negacoes:
        return ""
    comandos = []
    for d in negacoes:
        entrada = d.get("tool_input") or {}
        alvo = entrada.get("command") or entrada.get("file_path") or ""
        comandos.append(f"{d.get('tool_name')}({alvo[:60]})" if alvo else str(d.get("tool_name")))
    unicos = list(dict.fromkeys(comandos))
    return ", ".join(unicos[:4]) + (f" e mais {len(unicos) - 4}" if len(unicos) > 4 else "")


def extrair_bloco_json(texto: str) -> dict | None:
    """Pega o último bloco ```json da resposta — o que o contrato headless pede."""
    blocos = re.findall(r"```json\s*(\{.*?\})\s*```", texto or "", re.S)
    for bruto in reversed(blocos):
        try:
            return json.loads(bruto)
        except json.JSONDecodeError:
            continue
    return None


# -----------------------------------------------------------------------------
# Execução
# -----------------------------------------------------------------------------


class Cancelado(Exception):
    """A execução foi cancelada de fora, pela fila."""


def executar(
    fase: str,
    prompt: str,
    proposta_id: int,
    log_caminho: Path,
    ao_iniciar=None,
    cancelado=None,
    ferramentas: str | None = None,
) -> Resultado:
    """Roda uma fase e devolve o resultado.

    `cancelado` é um callable sem argumentos: quando devolver True, o processo é
    encerrado. `ao_iniciar(pid, session_id)` é chamado assim que o processo sobe.
    """
    session_id = str(uuid.uuid4())
    comando = montar_comando(fase, prompt, session_id, ferramentas)
    limite = cfg.timeout_da_fase(fase)
    comeco = time.monotonic()

    log_caminho.parent.mkdir(parents=True, exist_ok=True)
    log = log_caminho.open("w", encoding="utf-8")

    proc = subprocess.Popen(
        comando,
        cwd=cfg.RAIZ,                # os caminhos dos contratos são relativos à raiz
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,
        start_new_session=True,      # grupo próprio: dá para matar a árvore inteira
        env=_ambiente(),
    )

    if ao_iniciar:
        ao_iniciar(proc.pid, session_id)

    stderr_linhas: list[str] = []

    def drenar_stderr():
        for linha in proc.stderr:
            stderr_linhas.append(linha)
            if len(stderr_linhas) > 80:
                del stderr_linhas[:40]

    threading.Thread(target=drenar_stderr, daemon=True).start()

    resultado = Resultado(ok=False, fase=fase, session_id=session_id, log=str(log_caminho))
    parcial: list[str] = []
    ultimo_delta = 0.0
    motivo_morte = ""

    # Silêncio prolongado é normal (o subagente trabalha fora do stream do pai),
    # mas indistinguível de travamento na tela. O watchdog mostra que o relógio
    # está correndo.
    ultimo_sinal = [time.monotonic()]
    ultimo_limite: dict = {}
    vivo = threading.Event()

    def watchdog():
        while not vivo.wait(SINAL_DE_VIDA_S):
            quieto = time.monotonic() - ultimo_sinal[0]
            if quieto >= SINAL_DE_VIDA_S:
                minutos = int((time.monotonic() - comeco) // 60)
                eventos.progresso(
                    proposta_id, fase,
                    f"trabalhando há {minutos} min — o agente está processando",
                    tipo="espera",
                )

    threading.Thread(target=watchdog, daemon=True).start()

    def matar(motivo: str):
        nonlocal motivo_morte
        motivo_morte = motivo
        try:
            os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
            proc.wait(timeout=cfg.ESPERA_SIGKILL_S)
        except subprocess.TimeoutExpired:
            with contextlib.suppress(ProcessLookupError):
                os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            pass

    try:
        for linha in proc.stdout:
            # Flush por linha: o log é a única janela para depurar uma fase que
            # está rodando agora, e um buffer de 8 KB o deixaria 15 minutos atrás.
            log.write(linha)
            log.flush()

            if time.monotonic() - comeco > limite:
                matar(f"a fase {fase} passou de {limite // 60} minutos e foi interrompida")
                break
            if cancelado and cancelado():
                matar("cancelada")
                break

            linha = linha.strip()
            if not linha:
                continue
            ultimo_sinal[0] = time.monotonic()
            try:
                evento = json.loads(linha)
            except json.JSONDecodeError:
                continue

            tipo = evento.get("type")

            if tipo == "system" and evento.get("subtype") == "init":
                quebrados = [
                    m.get("name") for m in evento.get("mcp_servers") or []
                    if m.get("status") != "connected"
                ]
                if quebrados:
                    eventos.progresso(
                        proposta_id, fase,
                        f"MCP inesperado no ambiente: {', '.join(map(str, quebrados))}",
                        tipo="aviso",
                    )

            elif tipo == "stream_event":
                bloco = (evento.get("event") or {}).get("delta") or {}
                texto = bloco.get("text")
                if texto:
                    parcial.append(texto)
                    agora = time.monotonic()
                    if agora - ultimo_delta > 0.3:
                        ultimo_delta = agora
                        trecho = _ultima_frase("".join(parcial))
                        if trecho:
                            eventos.progresso(proposta_id, fase, trecho, tipo="texto")

            elif tipo == "assistant":
                for item in (evento.get("message") or {}).get("content") or []:
                    if isinstance(item, dict) and item.get("type") == "tool_use":
                        frase = descrever_ferramenta(item.get("name", ""), item.get("input") or {})
                        if frase:
                            eventos.progresso(proposta_id, fase, frase)

            elif tipo == "user":
                for item in (evento.get("message") or {}).get("content") or []:
                    if not (isinstance(item, dict) and item.get("type") == "tool_result"
                            and item.get("is_error")):
                        continue
                    conteudo = item.get("content")
                    texto = conteudo if isinstance(conteudo, str) else json.dumps(conteudo)
                    # Comando barrado pelo allow-list é rotina: o agente tenta
                    # outro caminho e segue. Anunciar como "ferramenta falhou"
                    # faz parecer que a geração quebrou.
                    if "requires approval" in texto or "permission" in texto.lower():
                        eventos.progresso(
                            proposta_id, fase,
                            "um comando foi barrado pelas permissões; o agente vai por outro caminho",
                        )
                    else:
                        eventos.progresso(
                            proposta_id, fase,
                            f"tentativa sem sucesso, refazendo: {texto[:120]}", tipo="aviso",
                        )

            elif tipo == "rate_limit_event":
                # Evento puramente informativo sobre a janela de uso: o Claude
                # Code o emite de tempos em tempos, quase sempre com
                # `status: "allowed"`, e a execução segue normalmente.
                #
                # Não vira aviso na tela. Um banner dizendo que tudo parou
                # enquanto o pipeline continua rodando é ruído que ensina o
                # comercial a ignorar avisos — inclusive os que importam.
                # Guardamos o estado e só o usamos se a fase de fato morrer,
                # onde ele explica o porquê.
                info = evento.get("rate_limit_info") or {}
                if info.get("status") not in (None, "allowed"):
                    ultimo_limite.update(info)

            elif tipo == "result":
                resultado.custo_usd = float(evento.get("total_cost_usd") or 0)
                resultado.turnos = int(evento.get("num_turns") or 0)
                resultado.negacoes = evento.get("permission_denials") or []
                texto_final = evento.get("result") or ""
                resultado.bloco = extrair_bloco_json(texto_final)
                resultado.resumo = (
                    (resultado.bloco or {}).get("resumo")
                    or re.sub(r"```json.*?```", "", texto_final, flags=re.S).strip()[:400]
                )
                resultado.ok = not evento.get("is_error") and evento.get("subtype") == "success"
                if not resultado.ok:
                    resultado.erro = f"o Claude Code terminou com {evento.get('subtype') or 'erro'}"

        resultado.exit_code = proc.wait(timeout=20)

    finally:
        vivo.set()
        log.close()
        with contextlib.suppress(Exception):
            proc.stderr.close()

    resultado.duracao_ms = int((time.monotonic() - comeco) * 1000)
    resultado.stderr_cauda = "".join(stderr_linhas)[-2000:]

    if motivo_morte == "cancelada":
        raise Cancelado()
    if motivo_morte:
        resultado.ok = False
        resultado.erro = motivo_morte
    elif resultado.exit_code not in (0, None) and not resultado.erro:
        resultado.ok = False
        resultado.erro = f"o Claude Code saiu com código {resultado.exit_code}"

    # Aqui sim a informação de limite serve: a fase morreu e este é o motivo
    # mais provável.
    if not resultado.ok and ultimo_limite:
        resultado.erro = f"{resultado.erro} — {_texto_rate_limit(ultimo_limite)}"

    return resultado
