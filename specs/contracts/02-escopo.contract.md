# Contrato 02 — Escopo

**Entrada:** `proposta/01-briefing.md`, `dados/catalogo-modulos.toml`,
`proposta/ajustes.md` (opcional, nas refações pedidas no checkpoint)
**Saída:** `proposta/02-escopo.md` + `proposta/02-escopo.json`
**Executor:** agente `escopo-mapper`

Esta fase **traduz demanda em item de catálogo**. Copia as horas de referência
do catálogo; **não soma, não multiplica, não precifica.**

## Seções obrigatórias de `02-escopo.md`

1. Frontmatter.
2. **Modelo e plataforma** — confirmados e travados.
3. **Escopo padrão incluso no valor base** — a lista, marcada "sem custo adicional".
4. **Tabela de itens cotados** — colunas: `ID do catálogo | Item | Complexidade |
   Qtd | Horas de referência | Origem [E##] | Observação`. A coluna de horas é
   **copiada literalmente** do catálogo (a faixa, ex.: `20–28`), sem conta.
5. **Itens fora do catálogo** — nome, horas estimadas, justificativa técnica,
   evidência; mais a nota de que exigem `/proposta-catalogo` para virar
   permanentes.
6. **Critério de complexidade aplicado** — para cada item, a frase do
   `criterio_complexidade` que motivou a classificação.
7. **Design** — o cliente fornece o layout? O impacto declarado em palavras
   (abatimento aplicável), sem cifra.
8. **Fora de escopo** — o que foi citado na reunião e **não** entra.
9. **Lacunas de escopo** — o que precisa de confirmação antes de fechar.
10. **Espelho de dados** — declara que o `.json` foi escrito e é consistente.
11. **Ajustes aplicados** — obrigatória **quando `proposta/ajustes.md` existe**.
    Para cada ajuste pendente: o que mudou no mapeamento e por quê. Ajuste não
    aplicado também entra, com o motivo. É o que permite a quem aprova conferir
    que o pedido dele foi entendido.

## Schema de `02-escopo.json`

```json
{
  "schema_versao": "1.0",
  "modelo_principal": "implantacao | evolucao",
  "natureza": "migracao | novo | evolucao",
  "plataforma": "shopify | vtex | wake | nuvemshop | wordpress | template-html",
  "design_fornecido_pelo_cliente": false,
  "evolucao_solicitada": { "ativa": false, "horas_mes": null },
  "prazo_semanas": { "min": 6, "max": 7, "origem": ["E71"], "justificativa": "" },
  "itens": [
    { "catalogo_id": "int-erp", "complexidade": "media", "quantidade": 1,
      "rotulo": "", "design_pela_n1": true, "origem": ["E12"], "observacao": "" }
  ],
  "itens_fora_catalogo": [
    { "nome": "…", "horas_estimadas": 32, "justificativa": "…", "origem": ["E31"] }
  ],
  "fora_de_escopo": ["Gestão de mídia paga [E24]"],
  "lacunas": ["…"]
}
```

**Não existe campo para horas nem para valor nos `itens`.** É por construção: o
agente não pode errar uma conta que não tem permissão de escrever.

### `rotulo` — o nome do que está sendo vendido

O `nome` do catálogo é fixo por `catalogo_id`. Uma proposta que cota cinco
páginas institucionais diferentes imprime cinco linhas idênticas —
"Página institucional adicional" — com preços de R$ 1.200 a R$ 9.600, e quem lê
não sabe qual é qual. Aconteceu, e o documento foi para o cliente assim.

`rotulo` é o nome dessa venda, na voz do cliente. **Obrigatório** quando o nome
do catálogo não identifica o que se está vendendo:

- o mesmo `catalogo_id` aparece mais de uma vez no escopo;
- o item cobre um grupo (`quantidade > 1`).

```json
{ "catalogo_id": "pagina-institucional-extra", "complexidade": "alta",
  "quantidade": 2, "rotulo": "Páginas das verticais Syngular Trust e Mais",
  "origem": ["E09","E10"],
  "observacao": "Cluster 1 — estruturais. Ver lacuna 18." }
```

Repare na divisão: `observacao` é a nota de auditoria — cluster, lacuna, por que
a complexidade é essa — e **não vai para o PDF**. `rotulo` vai. São públicos
diferentes, por isso são campos diferentes.

**Não escreva a quantidade dentro do `rotulo`.** "2 páginas" é número, e número
quem escreve é o `precificar.py`, que compõe `rotulo_exibido` a partir de
`rotulo` + `quantidade` + a unidade do catálogo. Escrever à mão duplica
("Páginas X — 2 páginas — 2 páginas") e desalinha quando a quantidade muda no
gate.

Sem `rotulo`, vale o `nome` do catálogo — o comportamento de sempre.

### Campos de decisão humana — o agente **não** escreve

Três campos existem para o comercial ajustar no gate, e são gravados pelo app,
nunca por agente:

| Campo | Onde | O que faz |
|---|---|---|
| `horas` | no item | fixa o esforço da linha, no lugar da faixa do catálogo |
| `valor_fixo` | no item | fixa o preço da linha; o valor digitado é o que sai, sem arredondar para hora fechada, e o rateio de um total negociado não mexe nele |
| `incluso_no_padrao` | no item | a linha passa a custar zero e a aparecer entre os inclusos, **nesta proposta** |
| `valor_base_override` | na raiz | substitui o valor base da plataforma |

Os três disparam alerta de severidade alta, que trava o botão de aprovar até
alguém reconhecer. São exceções declaradas, não atalhos.

Você, agente, **continua sem escrever valor e sem somar hora**. Se um ajuste
pedir preço ou esforço, ele não chega até você: o app resolve antes, com o
número que a pessoa escreveu e conferiu na tela. Se mesmo assim aparecer um
pedido desses no `ajustes.md`, registre que não é seu e siga.

`auditar.py escopo` reprova `catalogo_id` repetido cujos rótulos não distingam
uma linha da outra.

- `complexidade` é obrigatória, exceto quando o item tem `no_escopo_padrao` ou
  `regra_especial` no catálogo.
- `design_pela_n1` só vale para itens com `regra_especial = "landing_page"`.
  Ausente, herda de `design_fornecido_pelo_cliente`.
- Numa proposta `evolucao`, `evolucao_solicitada.horas_mes` é obrigatório: é o
  pacote recomendado, derivado do volume de demandas recorrentes levantado.
- `prazo_semanas` é **opcional** e só existe para um caso: o prazo foi
  **prometido na reunião**. Uma proposta que contradiz o que foi dito ao vivo
  custa caro. Omitido, o prazo é derivado das horas do escopo. Declarado, exige
  `origem` com a evidência — sem ela o script aborta — e sempre dispara
  `PRAZO_DEFINIDO_MANUALMENTE` no checkpoint, com o prazo que a fórmula daria,
  para que a diferença seja uma decisão e não um descuido. Não use este campo
  para "encaixar" um prazo que ninguém prometeu.

## Regras

- **Proibido escrever `R$`** em qualquer lugar da fase. `auditar.py escopo` reprova.
- **Proibido somar horas.** O total é responsabilidade do script.
- Todo item cotado tem `origem` com ao menos um `E##` ou `O##`. `E##` é citação
  do cliente; `O##` é observação do comercial (contrato 01, seção 12b).
- Item sustentado **apenas** por `O##` entra em Lacunas como "a confirmar com o
  cliente": foi o comercial que afirmou, não o cliente.
- `catalogo_id` inexistente é erro fatal no script — use `itens_fora_catalogo`.
- Não cote item do escopo padrão como adicional: ele já está no valor base.

## Verificação

`python3 scripts/auditar.py escopo proposta/02-escopo.json proposta/02-escopo.md`
