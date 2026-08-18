"""Chat somente-leitura sobre uma proposta já gerada.

Quem valida uma proposta precisa perguntar *por quê*: por que a busca virou item
cotado, de onde saiu "complexidade alta", em que ponto da reunião o cliente pediu
aquilo. Hoje a resposta existe — está espalhada entre `01-briefing.md`,
`02-escopo.md` e `03-orcamento.md` — mas achá-la significa abrir três arquivos e
cruzar códigos de evidência na mão.

Duas decisões moldam este módulo:

**Roda no workspace da proposta, não nos singletons.** É o que permite perguntar
sobre a proposta #3 enquanto a #5 está sendo gerada: o chat não monta pasta
nenhuma, não toca o lock, não entra na fila. Sem isso ele seria inútil justamente
quando mais serve — no meio de uma rodada.

**Não escreve.** Uma pergunta não pode alterar a proposta em silêncio; se pudesse,
o número aprovado na tela deixaria de ser o número auditado. O bloqueio é por
`--disallowedTools`, não por convenção no prompt: instrução se contorna, flag não.
"""

from __future__ import annotations

import json
import os
import subprocess
import threading
import time
import uuid

import config as cfg
import db
import eventos
import workspace as ws

# Teto por pergunta. Responder sobre artefatos prontos custa centavos; o teto é
# disjuntor contra loop de leitura, não orçamento.
TETO_USD_PERGUNTA = float(os.environ.get("N1_TETO_CHAT_USD", "1.5"))
TIMEOUT_S = 5 * 60
MODELO = "sonnet"

FERRAMENTAS = ["Read", "Grep", "Glob"]
BLOQUEADAS = ["Write", "Edit", "NotebookEdit", "Bash", "Task", "WebFetch", "WebSearch"]

# O `{base}` é o workspace desta proposta. Os arquivos precisam vir de lá e não
# dos singletons: `proposta/` na raiz pertence a quem estiver gerando agora, e
# responder com o escopo de outro cliente seria pior do que não responder.
SISTEMA = """\
Você responde perguntas de um vendedor sobre uma proposta comercial que já foi
gerada. Ele está na tela de aprovação decidindo se aprova o documento.

Sua base são **exclusivamente** os arquivos desta proposta, em `{base}/`:
- `{base}/proposta/01-briefing.md` — os fatos da reunião, cada um numerado `[E##]`
- `{base}/proposta/02-escopo.md` e `02-escopo.json` — o que entrou no escopo e por quê
- `{base}/proposta/03-orcamento.md` e `03-orcamento.json` — as horas e os valores
- `{base}/proposta/ajustes.md` — os ajustes pedidos no checkpoint, se houver
- `dados/catalogo-modulos.toml` e `dados/precos.toml` — catálogo e regras de preço

Não leia `proposta/` na raiz do repositório nem a pasta de outra proposta: são de
outro cliente. Cliente desta proposta: **{cliente}**.

Como responder:
- **Cite a origem.** A evidência `[E##]` quando vier da reunião, ou o nome do
  arquivo. Quem lê precisa poder conferir.
- **Se o dado não existe, diga que não existe.** Não deduza, não estime, não
  preencha lacuna com o que seria razoável. "Isso não foi falado na reunião" é
  uma resposta melhor que um palpite plausível — o vendedor vai repetir o que
  você disser para o cliente.
- **Curto.** Dois ou três parágrafos. Ele está com o cliente esperando.
- Português do Brasil, direto, sem preâmbulo. Não abra com "Ótima pergunta".
- Nada de bloco JSON no fim: isto é uma conversa, não uma fase do pipeline.

Você **não altera nada**. Não tem ferramenta de escrita e não deve prometer
mudanças: quem ajusta escopo ou fecha valor é o próprio vendedor, nos controles
da tela. Se ele pedir uma alteração, diga qual controle faz isso.
"""


def historico(proposta_id: int) -> list[dict]:
    return db.buscar(
        "SELECT id, papel, texto, custo_usd, criado_em FROM conversas "
        "WHERE proposta_id = ? ORDER BY id",
        (proposta_id,),
    )


def _sessao_anterior(proposta_id: int) -> str | None:
    """A sessão da última resposta, para continuar a conversa em vez de recomeçá-la.

    Sem isso, cada pergunta relê tudo do zero: mais lenta, mais cara, e sem
    memória do que acabou de ser discutido três linhas acima.
    """
    linha = db.um(
        "SELECT session_id FROM conversas WHERE proposta_id = ? AND papel = 'agente' "
        "AND session_id IS NOT NULL ORDER BY id DESC LIMIT 1",
        (proposta_id,),
    )
    return linha["session_id"] if linha else None


def _comando(pergunta: str, sistema: str, retomar: str | None) -> tuple[list[str], str]:
    sessao = retomar or str(uuid.uuid4())
    cmd = [
        "claude", "-p", pergunta,
        "--output-format", "stream-json",
        "--verbose",
        "--include-partial-messages",
        "--permission-mode", "default",
        "--setting-sources", "user,project",
        "--strict-mcp-config",
        "--mcp-config", '{"mcpServers":{}}',
        "--model", MODELO,
        "--max-budget-usd", str(TETO_USD_PERGUNTA),
        "--allowedTools", *FERRAMENTAS,
        "--disallowedTools", *BLOQUEADAS,
        "--append-system-prompt", sistema,
    ]
    # `--resume` e `--session-id` são mutuamente exclusivos: um continua uma
    # sessão que existe, o outro nomeia uma que ainda não existe.
    cmd += ["--resume", sessao] if retomar else ["--session-id", sessao]
    return cmd, sessao


def _ambiente() -> dict:
    env = dict(os.environ)
    for chave in ("ANTHROPIC_MODEL", "ANTHROPIC_SMALL_FAST_MODEL", "CLAUDE_CODE_MODEL"):
        env.pop(chave, None)
    return env


def perguntar(proposta_id: int, slug: str, cliente: str, pergunta: str) -> None:
    """Roda a pergunta e transmite a resposta. Bloqueia; chame numa thread."""
    pasta = ws.caminho(slug)
    base = pasta.relative_to(cfg.RAIZ).as_posix()
    retomar = _sessao_anterior(proposta_id)
    cmd, sessao = _comando(pergunta, SISTEMA.format(base=base, cliente=cliente), retomar)

    db.executar(
        "INSERT INTO conversas (proposta_id, papel, texto, criado_em) VALUES (?,?,?,?)",
        (proposta_id, "humano", pergunta, db.agora()),
    )
    eventos.publicar("chat", {"proposta_id": proposta_id, "papel": "humano",
                              "texto": pergunta, "estado": "pronto"})
    eventos.publicar("chat", {"proposta_id": proposta_id, "papel": "agente",
                              "texto": "", "estado": "pensando"})

    log = pasta / "logs" / f"chat-{int(time.time())}.jsonl"
    log.parent.mkdir(parents=True, exist_ok=True)

    partes: list[str] = []
    custo = 0.0
    erro = ""
    ultimo_envio = 0.0

    try:
        proc = subprocess.Popen(
            cmd, cwd=cfg.RAIZ, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            text=True, bufsize=1, start_new_session=True, env=_ambiente(),
        )
    except FileNotFoundError:
        _falhar(proposta_id, "o executável `claude` não está no PATH do serviço")
        return

    def matar_no_tempo():
        try:
            proc.wait(timeout=TIMEOUT_S)
        except subprocess.TimeoutExpired:
            proc.kill()

    threading.Thread(target=matar_no_tempo, daemon=True).start()

    with log.open("w", encoding="utf-8") as fl:
        for linha in proc.stdout:
            fl.write(linha)
            linha = linha.strip()
            if not linha:
                continue
            try:
                evento = json.loads(linha)
            except json.JSONDecodeError:
                continue

            tipo = evento.get("type")
            if tipo == "stream_event":
                texto = ((evento.get("event") or {}).get("delta") or {}).get("text")
                if texto:
                    partes.append(texto)
                    agora = time.monotonic()
                    if agora - ultimo_envio > 0.25:
                        ultimo_envio = agora
                        eventos.publicar("chat", {
                            "proposta_id": proposta_id, "papel": "agente",
                            "texto": "".join(partes), "estado": "escrevendo",
                        })
            elif tipo == "assistant":
                for item in (evento.get("message") or {}).get("content") or []:
                    if isinstance(item, dict) and item.get("type") == "tool_use":
                        alvo = (item.get("input") or {}).get("file_path") or \
                               (item.get("input") or {}).get("pattern") or ""
                        eventos.publicar("chat", {
                            "proposta_id": proposta_id, "papel": "agente",
                            "texto": "".join(partes), "estado": "lendo",
                            "consultando": str(alvo).split("/")[-1],
                        })
            elif tipo == "result":
                custo = float(evento.get("total_cost_usd") or 0)
                if evento.get("is_error") or evento.get("subtype") != "success":
                    erro = str(evento.get("subtype") or "erro desconhecido")
                # `result.result` é a resposta completa. Prefiro-a aos deltas
                # acumulados: se algum delta se perdeu, aqui vem inteiro.
                final = evento.get("result")
                if isinstance(final, str) and final.strip():
                    partes = [final]

    proc.wait()
    resposta = "".join(partes).strip()

    if not resposta:
        _falhar(proposta_id, _explicar(erro))
        return

    db.executar(
        "INSERT INTO conversas (proposta_id, papel, texto, session_id, custo_usd, criado_em) "
        "VALUES (?,?,?,?,?,?)",
        (proposta_id, "agente", resposta, sessao, custo, db.agora()),
    )
    db.executar("UPDATE propostas SET custo_usd = custo_usd + ? WHERE id = ?",
                (custo, proposta_id))
    eventos.publicar("chat", {"proposta_id": proposta_id, "papel": "agente",
                              "texto": resposta, "estado": "pronto"})


def _explicar(subtipo: str) -> str:
    if "budget" in subtipo:
        return (f"a pergunta passou do teto de US$ {TETO_USD_PERGUNTA:.2f}. "
                "Tente algo mais específico.")
    if "max_turns" in subtipo:
        return "o agente se perdeu procurando. Tente perguntar de forma mais direta."
    return "não consegui responder desta vez. Tente de novo."


def _falhar(proposta_id: int, motivo: str) -> None:
    texto = f"⚠ {motivo}"
    db.executar(
        "INSERT INTO conversas (proposta_id, papel, texto, criado_em) VALUES (?,?,?,?)",
        (proposta_id, "agente", texto, db.agora()),
    )
    eventos.publicar("chat", {"proposta_id": proposta_id, "papel": "agente",
                              "texto": texto, "estado": "pronto"})
