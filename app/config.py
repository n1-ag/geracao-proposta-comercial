"""Configuração do app N1 Propostas.

Um lugar só para porta, caminhos, modelos por fase, timeouts e tetos de custo.
Nada aqui depende de biblioteca externa.
"""

from __future__ import annotations

import os
from pathlib import Path

# -----------------------------------------------------------------------------
# Caminhos
# -----------------------------------------------------------------------------

APP = Path(__file__).resolve().parent
RAIZ = APP.parent                      # raiz do repositório — cwd de todo subprocesso
STATIC = APP / "static"
DADOS_APP = APP / "dados"              # runtime: banco, estado, lock
BANCO = DADOS_APP / "propostas.db"
ESTADO = DADOS_APP / "estado.json"     # {"montado": "0002-tireshop"}
LOCK = DADOS_APP / ".lock"

WORKSPACES = RAIZ / "propostas"        # um diretório por proposta
ARQUIVO = RAIZ / "arquivo"             # histórico do fluxo antigo (fonte do import)
DADOS_REPO = RAIZ / "dados"            # fonte única de preço — nunca copiada
SCRIPTS = RAIZ / "scripts"

# Os singletons do repositório. O app monta e recolhe; nunca duas propostas ao
# mesmo tempo. É a restrição arquitetural central.
SINGLETON_ENTRADA = RAIZ / "entrada"
SINGLETON_PROPOSTA = RAIZ / "proposta"
SINGLETON_SAIDA = RAIZ / "saida"

# -----------------------------------------------------------------------------
# Servidor
# -----------------------------------------------------------------------------

# Nunca 0.0.0.0: em uso local não há a quem expor, e publicado quem enfrenta a
# internet é o nginx, que termina o TLS e faz proxy para cá.
HOST = "127.0.0.1"
PORTA = int(os.environ.get("N1_PORTA", "7801"))
PORTAS_ALTERNATIVAS = range(PORTA, PORTA + 10)

SSE_HEARTBEAT_S = 15                   # comentário periódico que mantém a conexão viva
VERSAO_APP = "0.1.0"

# -----------------------------------------------------------------------------
# Motor
# -----------------------------------------------------------------------------

# Modelo por fase. A 02 é onde errar custa caro (mapeia escopo, e escopo vira
# preço), então ela leva o modelo mais forte. As demais são mais mecânicas.
MODELOS = {
    "01": "sonnet",
    "02": "opus",
    "04": "opus",
    "05": "sonnet",
    "06": "sonnet",
}
MODELO_ECONOMICO = "sonnet"            # usado quando ECONOMICO está ligado
ECONOMICO = os.environ.get("N1_ECONOMICO", "") == "1"

# Disjuntor por fase, em dólares. É proteção contra loop de tool-use, não
# orçamento: precisa ficar bem acima do que uma fase custa quando dá certo.
#
# Custos observados em execuções reais: 01 ≈ 1,30 · 02 ≈ 2,25 · 04 ≈ 3,02 ·
# 05 ≈ 3,04 · 06 ≈ 2,01. Com o teto em 3,00 as fases 04 e 05 morriam de
# `error_max_budget_usd` exatamente na linha de chegada, depois de dez minutos
# de trabalho — o disjuntor virou a maior causa de falha.
TETO_USD_FASE = float(os.environ.get("N1_TETO_USD", "8.0"))

# Timeouts em segundos. Estourou → SIGTERM, 5 s, SIGKILL.
TIMEOUTS = {
    "01": 20 * 60,
    "02": 20 * 60,
    "04": 20 * 60,
    "05": 25 * 60,
    "06": 15 * 60,
}
TIMEOUT_PADRAO = 20 * 60
ESPERA_SIGKILL_S = 5

# Quantas vezes reinvocar /proposta-html quando o render acusar transbordo.
MAX_RETRY_TRANSBORDO = 2


def modelo_da_fase(fase: str) -> str:
    if ECONOMICO:
        return MODELO_ECONOMICO
    return MODELOS.get(fase, "sonnet")


def timeout_da_fase(fase: str) -> int:
    return TIMEOUTS.get(fase, TIMEOUT_PADRAO)


# -----------------------------------------------------------------------------
# Contrato injetado em toda invocação headless
# -----------------------------------------------------------------------------

# Os comandos do repositório foram escritos para uma conversa com humano do outro
# lado ("pergunte se deve refazer"). Sem estas regras, uma fase trava esperando
# resposta até o timeout.
CONTRATO_HEADLESS = """\
Você está sendo executado por um servidor local, sem humano no terminal.

Regras absolutas desta execução:
1. NUNCA faça perguntas. Não há quem responda; a execução morre esperando.
2. Diante de ambiguidade, escolha a opção mais conservadora, registre o ponto em
   Lacunas e siga em frente.
3. Não peça confirmação para sobrescrever artefato: sobrescreva.
4. NUNCA rode um subagente em background. Você é um processo headless: quando
   você termina, o processo morre e o trabalho em background morre junto.
   Invoque a Task e AGUARDE o resultado dentro do seu próprio turno.
5. Um comando de shell por chamada. Nada de `&&`, `;`, `|` ou `&`: o allow-list
   de permissões não casa comandos compostos e eles são recusados.
6. A última coisa da sua resposta deve ser um bloco ```json com:
   {"fase":"NN","status":"ok|erro","artefatos":["caminho",...],
    "resumo":"uma frase","alertas":[],"lacunas_novas":0}
7. Não rode git, não instale nada, e não altere dados/, specs/ nem templates/.
"""

# -----------------------------------------------------------------------------
# Domínio
# -----------------------------------------------------------------------------

PLATAFORMAS = ["shopify", "vtex", "wake", "nuvemshop", "wordpress", "template-html"]
MODELOS_PROPOSTA = ["implantacao", "evolucao"]
NATUREZAS = ["migracao", "novo", "evolucao"]

STATUS_COMERCIAIS = ["enviada", "aceita", "recusada"]

STATUS_OPERACIONAIS = [
    "rascunho",
    "enfileirada",
    "executando_01_03",
    "executando_02_03",
    "aguardando_aprovacao",
    "executando_04_06",
    "gerada",
    "erro",
    "arquivada",
]

# Nomes que /api/propostas/:id/artefato aceita servir. Whitelist estrita: é a
# defesa contra path traversal, junto com a checagem de is_relative_to.
ARTEFATOS_SERVIVEIS = {
    "01-briefing.md",
    "02-escopo.md",
    "02-escopo.json",
    "03-orcamento.md",
    "03-orcamento.json",
    "04-narrativa.md",
    "05-montagem.md",
    "06-revisao.md",
    "proposta.html",
    "manifest.json",
    "ajustes.md",
}
ARTEFATOS_SAIDA = {"relatorio-paginacao.json"}
