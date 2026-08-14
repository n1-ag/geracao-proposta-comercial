# Contrato 02 — Escopo

**Entrada:** `proposta/01-briefing.md`, `dados/catalogo-modulos.toml`
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

## Schema de `02-escopo.json`

```json
{
  "schema_versao": "1.0",
  "modelo_principal": "implantacao | evolucao",
  "natureza": "migracao | novo | evolucao",
  "plataforma": "shopify | vtex | wake | nuvemshop | wordpress",
  "design_fornecido_pelo_cliente": false,
  "evolucao_solicitada": { "ativa": false, "horas_mes": null },
  "itens": [
    { "catalogo_id": "int-erp", "complexidade": "media", "quantidade": 1,
      "design_pela_n1": true, "origem": ["E12"], "observacao": "" }
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

- `complexidade` é obrigatória, exceto quando o item tem `no_escopo_padrao` ou
  `regra_especial` no catálogo.
- `design_pela_n1` só vale para itens com `regra_especial = "landing_page"`.
  Ausente, herda de `design_fornecido_pelo_cliente`.
- Numa proposta `evolucao`, `evolucao_solicitada.horas_mes` é obrigatório: é o
  pacote recomendado, derivado do volume de demandas recorrentes levantado.

## Regras

- **Proibido escrever `R$`** em qualquer lugar da fase. `auditar.py escopo` reprova.
- **Proibido somar horas.** O total é responsabilidade do script.
- Todo item cotado tem `origem` com ao menos um `E##`.
- `catalogo_id` inexistente é erro fatal no script — use `itens_fora_catalogo`.
- Não cote item do escopo padrão como adicional: ele já está no valor base.

## Verificação

`python3 scripts/auditar.py escopo proposta/02-escopo.json proposta/02-escopo.md`
