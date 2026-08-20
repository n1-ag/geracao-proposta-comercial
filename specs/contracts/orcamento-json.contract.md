# Contrato — `proposta/03-orcamento.json`

Escrito **exclusivamente** por `scripts/precificar.py`. Todo valor monetário
aparece duas vezes: cru (para conferência) e `_fmt` (pt-BR, para uso). **As
fases 04 e 05 só podem usar os campos `_fmt`.**

## Blocos de topo

| Campo | Conteúdo |
|---|---|
| `schema_versao` | `"1.0"` |
| `gerado_em` · `gerado_por` | data e versão do script |
| `precos_versao` | `meta.versao` de `precos.toml` |
| `hash_entrada` | sha256 dos três TOML de preço — é o que ancora o checkpoint |
| `cliente` | `nome`, `razao_social`, `contato_nome`, `contato_email`, `contato_whatsapp` |
| `proposta` | `modelo_principal`, `natureza`, `validade`, `validade_fmt`, `validade_extenso` |

## `implantacao`

`aplicavel` · `plataforma` · `plataforma_nome` · `valor_base(_fmt)` ·
`escopo_padrao_incluso[]` · `valor_hora(_fmt)` ·
`design{ parcela_embutida(_fmt), fornecido_pelo_cliente, abatimento(_fmt) }` ·
`linhas[]` · `linhas_fora_catalogo[]` · `subtotais{}` · `total(_fmt)` ·
`condicoes{ parcelamento, entrada_pct, entrada_valor(_fmt), parcelas_restante,
parcela_valor(_fmt), prazo_semanas_min, prazo_semanas_max, prazo_fmt, garantia }`

Cada item de `linhas[]`: `ordem`, `catalogo_id`, `nome`, `rotulo`,
`rotulo_exibido`, `categoria`, `unidade`, `quantidade`, `exige_app`, `regra`,
`complexidade`, `politica_faixa`, `horas_min_total`, `horas_max_total`,
`horas_total(_fmt)`, `valor(_fmt)`, `valor_exibido(_fmt)`, `origem[]`,
`no_catalogo`, `observacao`, `descricao_proposta`.

### O que vai ao cliente e o que fica aqui

| Campo | Papel |
|---|---|
| `nome` | o rótulo genérico do catálogo, fixo por `catalogo_id` |
| `rotulo` | o nome desta venda, escrito na fase 02; vazio quando não precisa |
| `rotulo_exibido` | **o que o PDF imprime** — `rotulo` ou `nome`, mais a contagem quando `quantidade > 1` |
| `valor(_fmt)` | o valor calculado pelo escopo — verdade interna |
| `valor_exibido(_fmt)` | **o que o PDF imprime** — igual ao calculado, exceto sob fechamento comercial |
| `horas_*` | esforço. **Não entra no documento do cliente.** |

`horas_min_total` e `horas_max_total` existem para auditoria interna. `horas_total`
também: junto com `valor_hora`, ele entrega a margem, então nenhum dos dois
aparece no PDF de implantação — `auditar.py numeros` reprova. Na evolução o
pacote de horas é o produto e aparece normalmente.

### `opcoes[]` — quando a proposta tem vários formatos

Presente em `implantacao` quando o escopo trouxe `opcoes`. Cada item:
`id`, `nome`, `resumo`, `principal`, `total(_fmt)` e `inclui[]` — os rótulos das
linhas daquele formato, que viram os bullets do cartão no PDF.

Os campos de `implantacao` fora de `opcoes[]` são **os do formato principal**:
total, condições, prazo e linhas. É o que mantém o resto do pipeline inalterado —
nada a jusante precisa saber que existem formatos.

`inclui[]` **não traz hora**. `auditar.py numeros` só autoriza hora vinda da
subárvore `evolucao`, e um cartão de formato não é pacote de horas.

### `valor_exibido` sob fechamento comercial

Quando uma pessoa fecha o preço na negociação, as linhas calculadas não somam o
total: a Viveo calculou R$ 22.000 e foi fechada em R$ 36.000. Imprimir as linhas
originais ao lado do total fechado dá uma tabela que não soma.

`precificar.py` rateia o fechado entre as linhas e o valor base, na proporção de
cada uma, **em degraus de R$ 10** e com o resto por maior resto: a coluna fecha
exata e toda linha termina em zero. Ratear no centavo também fechava, mas
produzia "R$ 3.260,75" por módulo — número que parece erro de planilha e faz
quem lê desconfiar antes de olhar o escopo.

O que não couber num degrau inteiro — só quando o total negociado não é múltiplo
de dez — vai para a linha do valor base, a única que pode carregar um número
quebrado sem ser comparada a uma tabela de preços.
`valor_base_exibido(_fmt)` é a contraparte do valor base.

Fora do fechamento, `valor_exibido` é idêntico a `valor`. Ele é emitido **sempre**
para que o redator e o montador usem um campo só e nunca precisem decidir qual.

## `evolucao`

`aplicavel` · `origem` (`"contratada"` ou `"alternativa_convertida"`) ·
`pacote_horas(_fmt)` · `faixa_id` · `faixa_rotulo` · `valor_hora(_fmt)` ·
`valor_mensal(_fmt)` · `valor_12m(_fmt)` · `contrato_meses` ·
`hora_excedente(_fmt)` · `acumulo_saldo_pct` · `fidelidade_meses` · `faturamento`

Quando `origem == "contratada"`, também `opcoes[]` — três pacotes, cada um com
`horas`, `valor_hora(_fmt)`, `valor_mensal(_fmt)`, `valor_12m(_fmt)` e
`recomendado`.

`origem == "contratada"` **pode** coexistir com `implantacao.aplicavel = true`:
é a implantação que vende acompanhamento junto, ligada por
`evolucao_solicitada.ativa` no escopo. Nesse caso não há `calculo{}` — não houve
conversão a memorizar — e `fidelidade_meses` é 6, não 12. Ver §C do
`03-orcamento.contract.md`.

Quando `origem == "alternativa_convertida"`, também `calculo{}` com a memória
completa: `valor_referencia(_fmt)`, `multiplicador_anual`,
`receita_anual_alvo(_fmt)`, `mensal_alvo(_fmt)`, `faixas_avaliadas[]` (cada uma
com `faixa_id`, `valor_hora`, `h`, `dentro_da_faixa`), `faixas_que_fecham[]`,
`criterio_desempate`, `h_bruto`, `arredondamento`, `h_final`, `ajuste_de_borda`,
`desvio_vs_alvo_pct`.

## `totais`, `alertas`, `lacunas`, `rastreabilidade`

`alertas[]`: `codigo`, `severidade`, `mensagem`. Códigos conhecidos:
`ITEM_NAO_CATALOGADO` (alta) · `ITEM_JA_INCLUSO` (média) ·
`VALOR_MUITO_BAIXO` · `VALOR_MUITO_ALTO` · `MODELO_AMBIGUO`.

`rastreabilidade[]`: `campo` → `origem` (arquivo e chave).
