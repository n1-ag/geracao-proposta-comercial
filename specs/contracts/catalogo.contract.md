# Contrato — `dados/catalogo-modulos.toml`

O catálogo é **fechado**: o agente de escopo só pode cotar o que existe aqui.

## Schema de um item

```toml
[[itens]]
id = "int-erp"                 # kebab-case, único
nome = "Integração com ERP"
categoria = "integracao"       # escopo-padrao | conteudo | componente | integracao | migracao | seo | apoio
unidade = "integração"
no_escopo_padrao = false       # true -> custo zero, sempre
exige_app = true               # instala/configura app na loja
regra_especial = ""            # "" ou "landing_page"
horas_baixa = [10, 14]
horas_media = [20, 28]
horas_alta  = [36, 56]
criterio_complexidade = """
baixa: …;
media: …;
alta: …."""
descricao_proposta = "Frase pronta para o PDF, na voz da N1."
```

## Regras

- `id` único, kebab-case. `auditar.py precos` reprova duplicata.
- Faixas obrigatórias e `min ≤ max`, **exceto** para itens com
  `no_escopo_padrao = true` ou `regra_especial`.
- `criterio_complexidade` é obrigatório: é o texto que o agente lê para
  classificar. Sem ele, a classificação vira palpite.
- `descricao_proposta` é obrigatória: é a frase que vai para a proposta.
- `regra_especial = "landing_page"` ignora complexidade e aplica a regra de
  `precos.toml`: `horas_design × design_pela_n1 + horas_dev`, por página.
- `no_escopo_padrao = true` força valor zero e emite `ITEM_JA_INCLUSO`. É o que
  impede alguém de cobrar a Home duas vezes.

## Como incluir um item novo

Rode `/proposta-catalogo`. Ele exige: nome, categoria, as três faixas de horas,
o critério de complexidade, a descrição de proposta e a **justificativa** de por
que o item não cabia em nenhum existente. Depois roda `auditar.py precos`.

Enquanto o item não estiver no catálogo, ele vive em `itens_fora_catalogo` do
`02-escopo.json` — cotado, mas com alerta `ITEM_NAO_CATALOGADO` visível no
checkpoint. Isso é intencional: o catálogo cresce com controle, e um item
estimado ad hoc nunca passa despercebido.

## Como mexer nas horas

Edite a faixa e rode `python3 scripts/auditar.py precos`. Se algum caso golden
quebrar, é porque a mudança altera um valor de referência — decida se o caso
golden é que precisa mudar, e mude os dois de uma vez, conscientemente.
