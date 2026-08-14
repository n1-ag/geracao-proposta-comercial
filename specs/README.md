# specs/ — a fonte da verdade do workflow

Os agentes em `.claude/agents/` são apenas executores. **O que torna o fluxo
replicável e auditável são os documentos daqui.**

- `steering/` — contexto permanente. Todo agente lê antes de começar.
- `contracts/` — a interface de cada fase: o que entra, o que sai, e quais
  seções o artefato é obrigado a ter.

**Regra de ouro da replicabilidade:** se um agente precisa de uma informação,
ela **tem** de estar num artefato anterior, num arquivo de `dados/` ou na
entrada. Nada de invenção sem origem.

**Regra de ouro do dinheiro:** o LLM decide *o quê*; o Python decide *quanto*.
Nenhum agente escreve um número monetário. Quem calcula é
`scripts/precificar.py`, e a única forma de um valor chegar ao PDF é vindo de
um campo `*_fmt` de `proposta/03-orcamento.json`.

## Como mudar alguma coisa

| Quero mudar | Edito |
|---|---|
| Um preço, uma faixa, o multiplicador da conversão | `dados/precos.toml` |
| As horas de um módulo, ou incluir um módulo novo | `dados/catalogo-modulos.toml` |
| Parcelamento, prazo, fidelidade, validade | `dados/condicoes-comerciais.toml` |
| O que a proposta afirma sobre a N1 | `dados/perfil-n1.toml` |
| O que uma fase precisa entregar | o contrato da fase em `contracts/` |
| Como o agente trabalha para entregar aquilo | o agente em `.claude/agents/` |
| A aparência do PDF | `templates/assets/css/proposta.css` |
| Uma seção nova no PDF | um arquivo em `templates/secoes/` + o contrato 05 |
