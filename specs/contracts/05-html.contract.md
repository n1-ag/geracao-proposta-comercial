# Contrato 05 — Montagem do HTML

**Entrada:** `04-narrativa.md`, `03-orcamento.json`, `templates/`
**Saída:** `proposta/proposta.html` + `proposta/05-montagem.md`
**Executor:** agente `montador-html`

O montador **não escreve texto novo e não escreve HTML estrutural de cabeça**.
Lê os arquivos de `templates/`, substitui marcadores e concatena.

## Três níveis

1. `templates/proposta.template.html` — casca: `{{LANG}}`, `{{TITULO_DOC}}`,
   `{{ASSET_BASE}}`, `{{PAGINAS}}`.
2. `templates/secoes/*.html` — uma seção lógica por arquivo. A ramificação
   implantação/evolução se resolve **escolhendo o arquivo**, nunca com `if`.
3. `templates/blocos/*.html` — snippets repetíveis. Substitua os marcadores
   internos e junte com `\n`.

## Escolha de seções

| Página | `implantacao` | `evolucao` |
|---|---|---|
| capa | `capa.html` | `capa.html` |
| 01 | `01-apresentacao.html` | `01-apresentacao.html` |
| 02 | `02-escopo-modulos.html` | `02-escopo-evolucao.html` |
| 03 | `03-conducao.html` (fluxo de projeto) | `03-conducao.html` (fluxo de demanda) |
| 04 | `04-investimento-implantacao.html` | `04-investimento-evolucao.html` |
| 04b | `04b-alternativa-evolucao.html` **se** `evolucao.aplicavel` | — |
| 05 | `05-premissas.html` | `05-premissas.html` |
| fim | `06-fechamento.html` | `06-fechamento.html` |

Cada página de corpo é envelopada por `blocos/pagina-corpo.html`, que já traz o
`.sec-head` e o `.foot`.

## Marcadores

Casca: `{{LANG}}` `{{TITULO_DOC}}` `{{ASSET_BASE}}` `{{PAGINAS}}`
Envelope: `{{SEC_HEAD_CLASSES}}` `{{SEC_NUM_HTML}}` `{{SEC_TITULO}}`
`{{SEC_KICKER}}` `{{PAGE_CONTEUDO}}` `{{CLIENTE_NOME}}` `{{FOOT_SECAO}}` `{{FOOT_NUM}}`
Capa: `{{CAPA_REF}}` `{{CAPA_TITULO_HTML}}` `{{CAPA_SUBTITULO}}` `{{FACTBAR_ITENS}}`
01: `{{APRESENTACAO_PARAGRAFOS}}` `{{STATS_ITENS}}` `{{PORQUE_TITULO}}` `{{PORQUE_ITENS}}` `{{COBERTURA_TITULO}}` `{{COBERTURA_ITENS}}`
02: `{{ESCOPO_INTRO}}` `{{FRENTES}}` `{{TABELA_TITULO}}` `{{ESCOPO_TABELA_LINHAS}}` `{{ESCOPO_NOTA}}`
03: `{{CONDUCAO_INTRO}}` `{{FLOW_ETAPAS}}` `{{CONDUCAO_CARD_DESTAQUE}}` `{{CONDUCAO_DUAS_COLUNAS}}` `{{CONDUCAO_CARD_RODAPE}}`
04: `{{PRICE_TAG}}` `{{PRICE_VALOR}}` `{{PRICE_CENTAVOS}}` `{{PRICE_SUFIXO}}` `{{PRICE_META_ITENS}}` `{{PRICE_NOTA}}` `{{PLANOS}}` `{{CONDICOES_TITULO}}` `{{TABELA_CONDICOES_LINHAS}}` `{{INCLUI_TITULO}}` `{{INCLUI_ITENS}}` `{{COMPLEMENTARES_TITULO}}` `{{COMPLEMENTARES_CARD}}` `{{INVEST_RODAPE_NOTA}}` `{{VALIDADE_NOTA}}`
04b: `{{ALT_INTRO}}` `{{ALT_TAG}}` `{{ALT_PRICE_VALOR}}` `{{ALT_PRICE_CENTAVOS}}` `{{ALT_META_ITENS}}` `{{ALT_PRICE_NOTA}}` `{{ALT_TABELA_TITULO}}` `{{ALT_TABELA_LINHAS}}` `{{ALT_CARD}}`
05: `{{PREMISSAS_TITULO}}` `{{PREMISSAS_ITENS}}` `{{TRANSICAO_BLOCO}}` `{{JANELA_CARD}}` `{{NAO_CONTEMPLADO_TITULO}}` `{{NAO_CONTEMPLADO_ITENS}}`
Fim: `{{CLOSE_HEADLINE}}` `{{CLOSE_TEXTO}}` `{{PASSOS}}` `{{CONTATOS}}` `{{CLOSE_BARRA}}`

Blocos repetíveis: `factbar-item` (2–4) · `stat` (3–4) · `bullet-lead` /
`bullet` · `frente` (até 5) · `flow-etapa` (4–5) · `card` · `price-meta` (1–3) ·
`plano-card` (3) · `linha-tabela` (+`linha-tabela-sub`) · `check-item` ·
`cross-item` · `passo` (3) · `contato` (4).

Marcador condicional que não se aplica recebe **string vazia**, nunca o texto do
marcador.

## Tokens de número

`«orc:caminho.do.campo»` é resolvido por caminho de chave contra
`03-orcamento.json`. Token que não resolve é **erro fatal**: pare e reporte.
Nunca escreva o número à mão como contorno.

O `.price` divide o valor: `{{PRICE_VALOR}}` recebe a parte inteira sem `R$`
(ex.: `54.800`) e `{{PRICE_CENTAVOS}}` recebe `,00`.

## Orçamento de altura

Área útil da `.body-page`: **745,76pt** (de 48,03pt a 793,79pt).

| Bloco | Altura |
|---|---|
| `.sec-head` | 35pt (já está no envelope) |
| linha de `<p>` (≈96 caracteres) | 16,8pt + 9,07pt de margem no fim do parágrafo |
| `.stats` | 72,5pt + 31,3pt de margem |
| `h3` | 18,9pt + 8pt |
| item de `ul.bullets`/`check`/`cross` | 14,88pt por linha + 5,35pt |
| `.frente` | 14pt + 5pt + 13,95pt por linha de texto + 22,6pt |
| `.flow` | 71pt + 21pt |
| `.card` | 27,8pt + 14,88pt por linha + 15pt |
| `.price` | 33pt + 42pt + 13,33pt por linha da nota + 16,3pt |
| `.planos` | 96pt + 18pt |
| `tr` da tabela | 27,7pt (41,9pt com sub-nota) |
| `.two` | a maior das colunas |

Limites práticos: **5 `.frente` por página** (4 se algum texto passar de 320
caracteres) · 4 `.stats` · 5 etapas de `.flow` · 8 linhas de tabela · 10 itens de
`ul.check` em 2 colunas.

## Espaçamento

Use as classes utilitárias `.mb-0 .mb-9 .mb-11 .mb-15 .mb-16 .mb-17 .mb-19 .mb-20`.
**Nunca `style=` inline** e nunca `margin-top`: margens de irmãos colapsam.

## Regras finais

- Nenhum `{{` ou `«` pode sobrar no arquivo.
- Só classes declaradas em `proposta.css`.
- Capa e fechamento não têm `.foot`. O `.pg` do rodapé é o ordinal físico
  começando em `01` na primeira página após a capa.
- Página de continuação: `.sec-head cont`, `{{SEC_NUM_HTML}}` vazio e
  `{{SEC_KICKER}}` = "continuação".

## Verificação

```
python3 scripts/auditar.py template proposta/proposta.html
python3 scripts/auditar.py numeros  proposta/proposta.html proposta/03-orcamento.json
```
