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

Cada item de `linhas[]`: `ordem`, `catalogo_id`, `nome`, `categoria`, `unidade`,
`quantidade`, `exige_app`, `regra`, `complexidade`, `politica_faixa`,
`horas_min_total`, `horas_max_total`, `horas_total(_fmt)`, `valor(_fmt)`,
`origem[]`, `no_catalogo`, `observacao`, `descricao_proposta`.

`horas_min_total` e `horas_max_total` existem para auditoria interna; **o cliente
vê um número só** (`horas_total`), definido por `politica_faixa_horas`.

## `evolucao`

`aplicavel` · `origem` (`"contratada"` ou `"alternativa_convertida"`) ·
`pacote_horas(_fmt)` · `faixa_id` · `faixa_rotulo` · `valor_hora(_fmt)` ·
`valor_mensal(_fmt)` · `valor_12m(_fmt)` · `contrato_meses` ·
`hora_excedente(_fmt)` · `acumulo_saldo_pct` · `fidelidade_meses` · `faturamento`

Quando `origem == "contratada"`, também `opcoes[]` — três pacotes, cada um com
`horas`, `valor_hora(_fmt)`, `valor_mensal(_fmt)`, `valor_12m(_fmt)` e
`recomendado`.

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
