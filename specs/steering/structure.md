# Estrutura, nomes e estado

## Pastas

```
entrada/     o que você preenche à mão (gitignored, exceto os .exemplo)
dados/       a fonte da verdade comercial (versionada, editada à mão)
specs/       contratos e contexto permanente
templates/   casca, seções, blocos, CSS e assets do PDF
scripts/     precificar.py · render_pdf.py · auditar.py
proposta/    artefatos gerados da proposta em andamento (gitignored)
saida/       o PDF e os relatórios (gitignored)

app/         o webapp local para o time comercial (stdlib pura + SQLite)
propostas/   um workspace por proposta, gerido pelo app (gitignored)
arquivo/     propostas encerradas pelo fluxo de terminal (gitignored)
```

`entrada/`, `proposta/` e `saida/` são **singletons**: uma proposta por vez, para
que `dados/` continue sendo fonte única de preço. O app contorna isso guardando
cada proposta em `propostas/<NNNN>-<slug>/` e **montando** nos singletons só a que
vai rodar, em fila serial. Consequência prática: **não rode `/proposta` no
terminal com o app ligado** — os dois disputam as mesmas pastas. O
`GET /api/saude` mostra qual proposta está montada.

## Nomes de artefato

`proposta/NN-slug.md` — o `NN` é fixo e imutável. **Não renomeie.**

| NN | Artefato | Espelho JSON |
|---|---|---|
| 01 | `01-briefing.md` | — |
| 02 | `02-escopo.md` | `02-escopo.json` |
| 03 | `03-orcamento.md` | `03-orcamento.json` |
| 04 | `04-narrativa.md` | — |
| 05 | `05-montagem.md` | `proposta.html` |
| 06 | `06-revisao.md` | — |

## Frontmatter

Todo artefato `.md` começa com:

```yaml
---
cliente: <nome>
fase: <NN — Nome da Fase>
versao: 1
atualizado_em: AAAA-MM-DD
entradas: [entrada/transcricao.md, proposta/01-briefing.md]
---
```

`entradas` é a declaração explícita de dependência. É o que permite saber o que
precisa ser refeito quando algo muda.

## Evidências

O agente 01 numera cada fato extraído da transcrição como `E01`, `E02`, … e
guarda a citação literal no apêndice. Todas as fases seguintes referenciam por
esse código. Uma afirmação sem `[E##]` é violação de contrato, exceto quando
marcada `[INFERÊNCIA]` e listada em Lacunas.

## Tokens de número

A narrativa nunca escreve um valor. Escreve `«orc:evolucao.valor_mensal_fmt»`.
O montador resolve o caminho contra `03-orcamento.json`. Token que não resolve é
**erro fatal** — nunca vira texto no PDF.

## manifest.json

Estado único do workflow. **Só os comandos escrevem nele**; agentes de conteúdo
nunca. Estados: `pendente` | `concluida` | `desatualizada`.

Refazer a fase N marca todas as fases > N como `desatualizada`. Refazer 02 ou 03
muda o hash do orçamento e derruba o checkpoint humano para `pendente`.

## Classes de respiro do CSS

`.mb-0 .mb-9 .mb-11 .mb-15 .mb-16 .mb-17 .mb-19 .mb-20` — os valores saem da
medição do PDF original. Não invente outros, e não use `style=` inline:
`auditar.py template` avisa.
