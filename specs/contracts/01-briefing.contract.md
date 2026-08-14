# Contrato 01 — Briefing comercial

**Entrada:** `entrada/transcricao.md`, `entrada/dados-cliente.md`
**Saída:** `proposta/01-briefing.md`
**Executor:** agente `transcricao-analyzer`

Esta fase **extrai fatos**. Não decide escopo, não estima esforço, não precifica.

## Seções obrigatórias

1. **Frontmatter** — conforme `steering/structure.md`.
2. **Identificação** — cliente, razão social, contato, e-mail, WhatsApp,
   validade. Da ficha; o que faltar vira lacuna.
3. **Contexto do negócio** — o que a empresa vende, porte, canais.
4. **Situação atual** — plataforma de hoje, quem atende, o que está quebrado.
5. **Dores declaradas** — lista; cada item com `[E##]`.
6. **Objetivo** — o que o cliente quer alcançar com o projeto.
7. **Demandas citadas** — lista **bruta e literal**, com as palavras da reunião.
   Não mapear para o catálogo aqui: isso é a fase 02.
8. **Integrações e sistemas citados** — ERP, hub, gateway, CRM, o que aparecer.
9. **Restrições** — prazo, janela, orçamento sinalizado, decisores, sazonalidade.
10. **Modelo e natureza inferidos** — o valor, mais a tabela de sinais que levou
    à inferência.
11. **Lacunas** — o que a reunião não respondeu.
12. **Evidências** — apêndice `E01`..`En`, cada uma com a **citação literal** da
    transcrição, no máximo 300 caracteres.

## Tabela de sinais para inferir o modelo

| Sinal na transcrição | Modelo |
|---|---|
| "site novo", "refazer a loja", "migrar para X", "sair da plataforma Y", "go-live", "projeto" | `implantacao` |
| "pacote de horas", "fee", "sustentação", "manutenção mensal", "trocar de agência", "a loja já roda em X" | `evolucao` |
| Sinais dos dois lados | `implantacao` + alerta `MODELO_AMBIGUO`; **exige confirmação humana no gate 01** |
| Nenhum sinal | Lacuna declarada; o pipeline para |

`natureza`: "migrar", "sair de", "trocar de plataforma" → `migracao`;
"loja nova", "primeiro e-commerce" → `novo`.

## Regras

- Toda linha das seções 3 a 11 termina com um ou mais `[E##]`. Linha sem
  evidência é violação de contrato.
- Inferência do analista é marcada `[INFERÊNCIA]` e repetida em Lacunas.
- Não invente nome de sistema, volume de SKU ou prazo. Se a transcrição diz
  "uns quatro mil produtos", registre "uns quatro mil produtos [E07]", não "4.000".
- Se `entrada/transcricao.md` não existir ou for o exemplo, pare e avise.

## Resposta ao orquestrador

3 a 5 linhas: modelo e natureza inferidos, quantas evidências foram extraídas, e
a lista das lacunas que travam a fase 02.
