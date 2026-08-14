---
name: precificacao-n1
description: Regras de precificação da N1.AG para propostas comerciais — valor base por plataforma, abatimento de design, hora adicional, faixas de fee mensal e conversão de implantação em evolução. Use sempre que a conversa envolver quanto custa, quanto dá, quantas horas ou qual o valor de um escopo.
---

# Precificação N1.AG

## A regra que vem antes de todas

**Nunca calcule preço de cabeça. Rode o script.**

```
python3 scripts/precificar.py --simular --converter 50000
python3 scripts/precificar.py --simular --pacote 26
python3 scripts/precificar.py --simular --plataforma vtex --horas-adicionais 40
python3 scripts/precificar.py --simular --plataforma shopify --layout-do-cliente
```

Aritmética de cabeça em conversa vira número citado em proposta. O script lê
`dados/*.toml`, usa `Decimal` e tem 35 casos golden. Você não tem nada disso.

## O resumo das regras (para reconhecer o caso, não para calcular)

**Implantação — valor base, com design incluso, para o escopo padrão**
(Home, PLP, PDP, Sobre Nós, Políticas, Checkout):
WordPress R$ 18.000 · Nuvemshop R$ 22.000 · Shopify R$ 28.000 ·
Wake R$ 45.000 · VTEX R$ 52.000.

Design embutido, abatido se o cliente entrega o layout: R$ 8.000 em WordPress,
Nuvemshop e Shopify; R$ 12.000 em Wake e VTEX.

Hora adicional: R$ 200. LP institucional, blog e página de serviço: 4h de design
+ 6h de dev por página — as 4h só se o protótipo for da N1.

**Migração e projeto novo custam o mesmo.** A natureza muda a narrativa, não o
preço.

**Fee mensal:** até 10h → R$ 240/h · 11–19h → R$ 220/h · 20–29h → R$ 210/h ·
30h ou mais → R$ 200/h.

**Conversão implantação → evolução** (sempre oferecida numa implantação, em
contrato de 12 meses): alvo anual de 1,3× o valor da implantação, dividido por
12, resolvido contra a tabela de faixas por ponto fixo. Referência:
R$ 50.000 → 26h × R$ 210,00 = **R$ 5.460,00/mês**.

## Onde ficam os números

| Arquivo | O quê |
|---|---|
| `dados/precos.toml` | bases, design, hora, faixas, regras de conversão |
| `dados/catalogo-modulos.toml` | horas por módulo e complexidade |
| `dados/condicoes-comerciais.toml` | parcelamento, prazo, fidelidade, validade |

Mudou algum? Rode `python3 scripts/auditar.py precos`.

## O que não fazer

- Não estime horas de um módulo que não esteja no catálogo sem dizer que está
  fora dele — item fora do catálogo gera alerta de propósito.
- Não aplique desconto. Desconto é decisão comercial humana, aplicada depois.
- Não arredonde "para ficar mais bonito". O arredondamento já está na regra.
- Não use `float` se for escrever código que toca em dinheiro.
