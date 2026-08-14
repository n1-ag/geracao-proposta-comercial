# N1 Propostas — o app

Webapp local que embrulha o pipeline de proposta comercial para quem não quer
abrir um terminal. Cadastra o cliente, cola a transcrição, aprova o orçamento e
baixa o PDF.

```bash
python3 app/servidor.py          # http://127.0.0.1:7801
```

Sem `pip install`: stdlib pura, SQLite, HTML e JS sem framework. As mesmas
dependências do pipeline (Claude Code, Chrome, Playwright, pypdf, poppler) já
bastam — o `/api/saude` avisa se faltar alguma.

---

## Primeira vez

```bash
python3 app/importar.py --dry-run   # mostra o que faria
python3 app/importar.py             # traz arquivo/ e a proposta em andamento
```

O import é idempotente: rodar de novo atualiza metadados e **não mexe** no que é
decisão humana (status comercial, datas de envio, descarte). As pastas de origem
não são apagadas.

---

## Como funciona

O app **substitui o orquestrador conversacional** por código Python. As fases de
conteúdo continuam sendo os mesmos slash commands do repositório, invocados por
`claude -p` headless; as fases determinísticas viram chamada direta de script.

| Fase | Quem executa |
|---|---|
| 01 Briefing · 02 Escopo · 04 Narrativa · 05 Montagem · 06 Revisão | `claude -p "/proposta-*"` |
| **03 Orçamento** | `subprocess` de `scripts/precificar.py` |
| **06a Render** | `subprocess` de `scripts/render_pdf.py` |
| Auditorias | `subprocess` de `scripts/auditar.py` |

Chamar os scripts direto corta o custo de um turno de LLM, elimina a classe de
erro "o agente digitou o caminho errado" e torna o gate inviolável: nenhum
agente é convidado a rodar o precificador.

### O gate

Depois da fase 03 a execução para. A tela de aprovação mostra o valor, o escopo
item a item com a evidência de origem, o que já está incluso no valor base, os
alertas e a memória de cálculo inteira. Alerta de severidade alta trava o botão
até ser reconhecido, um a um.

Aprovou → roda 04, 05 e 06 e entrega o PDF.
Não gostou → escreve o que está errado e o app refaz as fases 02 e 03.

### Uma proposta por vez

`entrada/`, `proposta/` e `saida/` são singletons do repositório — é o que
mantém `dados/` como fonte única de preço. O app guarda cada proposta em
`propostas/<NNNN>-<slug>/` e **monta** nos singletons só a que vai rodar, em
fila serial, protegida por um lock de arquivo com PID.

> **Não rode `/proposta` no terminal com o app ligado.** Os dois disputam as
> mesmas pastas. O lock é consultivo e não impede isso; `/api/saude` mostra qual
> proposta está montada.

Se o servidor morrer no meio de uma execução, a subida seguinte remove o lock
órfão, marca a execução como interrompida e devolve a proposta ao último estado
consistente **derivado dos arquivos no disco** — não de um palpite do banco.

---

## Observações do comercial

O cadastro tem um campo livre que vira `entrada/observacoes.md` e é analisado
**junto** com a transcrição na fase 01. É onde entra o que a gravação não pegou:
contexto de conversas anteriores, o que ficou implícito, o que o cliente evitou
dizer.

Essas afirmações são numeradas `O01`, `O02`, … — namespace separado do `E##` de
propósito: `E##` é citação do cliente, `O##` é interpretação de quem estava lá.
Quando as duas divergem, **prevalece a transcrição**, e a divergência vira lacuna
declarada. Item sustentado só por `O##` entra em Lacunas como "a confirmar".

---

## Estrutura

```
servidor.py        ThreadingHTTPServer, roteamento, SSE, estáticos
config.py          porta, modelos por fase, timeouts, teto de custo
roteador.py        registro de rotas e erros HTTP
db.py · esquema.sql  SQLite: conexão por thread, migração, DDL
modelo.py          máquina de estados e os invariantes do gate
workspace.py       montar/recolher entre workspace e singletons
ficha.py           cadastro ↔ entrada/dados-cliente.md
artefatos.py       lê um workspace e deriva os campos do banco
claude_runner.py   claude -p headless, parser do stream-json
scripts_runner.py  precificar.py, render_pdf.py, auditar.py
executor.py        fila serial, lock, orquestração das seis fases
eventos.py         pub/sub em memória para o SSE
dashboard.py       as agregações do painel, em SQL
importar.py        importação idempotente do legado
api_*.py           rotas: propostas, execução, artefatos
static/            HTML, CSS e JS sem framework
exemplos/          transcrição fictícia para testar o app
```

Runtime (fora do git): `app/dados/` (banco, lock, estado) e `propostas/`.

---

## Configuração

Variáveis de ambiente, todas opcionais:

| Variável | Padrão | O que faz |
|---|---|---|
| `N1_PORTA` | `7801` | porta; se ocupada, tenta até a 7810 |
| `N1_ABRIR` | `1` | abre o navegador na subida; `0` desliga |
| `N1_ECONOMICO` | `0` | `1` roda todas as fases em sonnet |
| `N1_TETO_USD` | `3.0` | disjuntor de custo por fase |

Modelo por fase e timeouts ficam em [config.py](config.py). O padrão usa opus
nas fases 02 e 04 — a 02 é onde errar custa caro, porque escopo vira preço.

**Custo por proposta:** ordem de grandeza de US$ 5 a 15 e 20 a 40 minutos, a
depender do tamanho da transcrição. O painel acumula o gasto por proposta.

---

## Quando algo dá errado

A tela de detalhe mostra a fase que falhou, a mensagem em português e um botão
para **retomar dali** — os artefatos já produzidos ficam no lugar. O stream cru
de cada fase fica em `propostas/<slug>/logs/*.jsonl`, e o `session_id` gravado
permite reabrir a sessão com `claude --resume <id>` para investigar.

| Sintoma | Provável causa |
|---|---|
| "a fase X terminou sem escrever" | o agente parou antes de gerar o artefato; veja o log |
| "bloqueado pelo allow-list" | falta uma regra em `.claude/settings.json` |
| "os dados comerciais não passaram na auditoria" | `dados/*.toml` quebrado; rode `auditar.py precos` |
| "o conteúdo transbordou a página" | duas tentativas automáticas de remontagem; depois é texto longo demais |
| "limite de uso atingido" | rate limit da conta; retome depois do reset |
