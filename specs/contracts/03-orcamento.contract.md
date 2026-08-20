# Contrato 03 — Orçamento

**Entrada:** `proposta/02-escopo.json`, `entrada/dados-cliente.md`, `dados/*.toml`
**Saída:** `proposta/03-orcamento.json` + `proposta/03-orcamento.md`
**Executor:** **o script** `scripts/precificar.py`. Nenhum agente escreve aqui.

## As regras de preço, como norma

### A) Implantação

| Plataforma | Valor base | Design embutido |
|---|---|---|
| Template HTML | R$ 18.000 | R$ 8.000 |
| WordPress | R$ 18.000 | R$ 8.000 |
| Nuvemshop | R$ 22.000 | R$ 8.000 |
| Shopify | R$ 28.000 | R$ 8.000 |
| Wake | R$ 45.000 | R$ 12.000 |
| VTEX | R$ 52.000 | R$ 12.000 |

O valor base cobre o escopo padrão: Home, PLP, PDP, Sobre Nós, Políticas, Minha
conta, Menu de navegação, Filtros, Minicart, SEO técnico e Checkout (dentro das
possibilidades da plataforma). Se o cliente entrega o layout, o design embutido
é **abatido** do total.

Menu, filtros, minicart e SEO técnico entram no valor base **na versão padrão**.
Os módulos `mega-menu`, `filtros-facetas`, `minicart-carrinho-custom` e
`seo-tecnico-onpage` continuam cobráveis para o que ultrapassa esse padrão — o
critério de cada um diz onde fica a fronteira.

**Template HTML** é a modalidade sem implantação: a N1 entrega UX, layout e os
templates em HTML/CSS/JS responsivos e navegáveis, com a estrutura semântica que
o SEO exige, e o time do cliente aplica no back-end dele. Vale para plataforma
própria ou qualquer stack fora das cinco acima. Não há linha de plataforma,
integração nem go-live nessa modalidade.

Hora adicional: **R$ 200**. LP institucional, blog e página de serviço:
**4h de design + 6h de dev por página** — as 4h só entram se o protótipo for da
N1. Integrações que exigem app: horas por complexidade, conforme o catálogo.

**`natureza` não entra em nenhuma fórmula.** Migração e projeto novo custam o
mesmo. `auditar.py precos` verifica isso lendo o código de `precificar.py`.

### B) Fee mensal

| Pacote | R$/hora |
|---|---|
| até 10 h/mês | 240 |
| 11 a 19 h/mês | 220 |
| 20 a 29 h/mês | 210 |
| 30 h/mês ou mais | 200 |

### C) Conversão implantação → evolução

Toda proposta de implantação apresenta também a alternativa em fee mensal, com
contrato de 12 meses:

1. `receita_anual_alvo = valor_implantacao × 1,3`
2. `mensal_alvo = receita_anual_alvo / 12`
3. Ponto fixo: para cada faixa, `h = mensal_alvo / valor_hora`; aceita a faixa em
   que `h` cai dentro dela mesma.
4. Mais de uma faixa fecha → escolhe a que entrega **mais horas**.
   Nenhuma fecha → adota o `horas_min` da faixa superior (`vale_entre_faixas`).
5. `h_final = arredonda_half_up(h)`; se o arredondamento cruzar de faixa, vale a
   faixa nova. `mensal_final = h_final × valor_hora`.
6. `h < 4` → alternativa não é oferecida (`VALOR_MUITO_BAIXO`, o bloco 04b some).
   `h > 60` → calcula e alerta (`VALOR_MUITO_ALTO`).

**Caso de referência:** R$ 50.000 → R$ 65.000/ano → R$ 5.416,67/mês → faixa
20–29 @ R$ 210 → 25,79h → **26h × 210 = R$ 5.460,00/mês**.

#### Quando a implantação já vende acompanhamento

A conversão é o **padrão**, não a única saída. Se o `02-escopo.json` trouxer
`evolucao_solicitada.ativa = true` com `horas_mes`, o bloco de fee mensal deixa
de ser a alternativa convertida e passa a ser o **pacote contratado**: horas
combinadas na reunião, preço direto da tabela de faixas, `origem: "contratada"`,
fidelidade `fidelidade_meses_padrao` (6 meses, não os 12 da conversão).

São produtos diferentes, e a diferença é o que o cliente lê:

| | Alternativa convertida | Pacote contratado |
|---|---|---|
| O que é | outra **forma de pagar** o mesmo projeto | trabalho **a mais**, depois do go-live |
| De onde vem o valor | 1,3× o total da implantação | as horas acordadas × a faixa |
| Fidelidade | 12 meses | 6 meses |
| Convive com o projeto | não — é "em vez de" | sim — é "além de" |

Emite `EVOLUCAO_CONTRATADA_EM_IMPLANTACAO` (severidade média) no checkpoint: a
regra C não foi aplicada, e quem aprova precisa ver isso. Golden que trava a
bifurcação: `roteamento_evolucao` em `casos-teste-precificacao.toml` — o mesmo
projeto de R$ 36.000 dá **R$ 4.200,00/mês** (20h contratadas) ou
**R$ 3.960,00/mês** (18h convertidas), e mandar o número do caminho errado é o
erro que aquele par de casos existe para impedir.

### Três opções de pacote (fee mensal nativo)

`pacotes_sugeridos` em `precos.toml` é a escada. O script escolhe o degrau mais
próximo do recomendado e seus dois vizinhos, marcando o escolhido.

## O que o script emite em `03-orcamento.md`

1. Cabeçalho: cliente, modelo, data, versão da tabela, hash das entradas.
2. Composição da implantação, linha a linha, com origem `[E##]`.
3. Memória de cálculo: `base + horas × R$/h − abatimento = total`.
4. Memória da conversão: alvo anual, mensal alvo, **todas as faixas avaliadas com
   o `h` de cada e se fechou**, desempate, arredondamento, desvio %.
5. Condições comerciais aplicadas.
6. Alertas.
7. Rastreabilidade: cada campo → arquivo e chave de origem.

## Regras do JSON

- Todo valor monetário aparece duas vezes: `total` e `total_fmt`.
- **As fases 04 e 05 só podem usar os campos `_fmt`.**
- `Decimal` com `ROUND_HALF_UP` em todo lugar; nunca `float`.

## Verificação

`python3 scripts/auditar.py precos` — a suíte golden precisa passar **inteira**
antes de a fase 03 ser aceita. O caso R$ 50.000 → R$ 5.460 é nomeado na saída.
