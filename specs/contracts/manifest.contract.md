# Contrato — `proposta/manifest.json`

Estado único do workflow. **Só os comandos escrevem aqui.** Agentes de conteúdo
nunca tocam neste arquivo.

```json
{
  "cliente": "Ateliê Verde",
  "criado_em": "2026-08-13",
  "atualizado_em": "2026-08-13",
  "modelo_principal": "implantacao",
  "natureza": "migracao",
  "plataforma": "shopify",
  "fase_atual": "04",

  "checkpoint_humano": {
    "exigido_apos": "03",
    "status": "pendente | aprovado",
    "aprovado_em": "2026-08-13",
    "aprovado_sobre": {
      "orcamento_hash": "sha256:…",
      "total_fmt": "R$ 54.800,00"
    },
    "observacoes": ["Reduzir de 4 para 3 LPs"]
  },

  "fases": {
    "01-briefing":  { "status": "concluida", "versao": 1, "atualizado_em": "2026-08-13", "artefato": "proposta/01-briefing.md" },
    "02-escopo":    { "status": "concluida", "versao": 2, "atualizado_em": "2026-08-13", "artefato": "proposta/02-escopo.md",   "espelho": "proposta/02-escopo.json" },
    "03-orcamento": { "status": "concluida", "versao": 2, "atualizado_em": "2026-08-13", "artefato": "proposta/03-orcamento.md","espelho": "proposta/03-orcamento.json" },
    "04-narrativa": { "status": "pendente",  "versao": 0, "atualizado_em": null, "artefato": "proposta/04-narrativa.md" },
    "05-html":      { "status": "pendente",  "versao": 0, "atualizado_em": null, "artefato": "proposta/05-montagem.md", "saida": "proposta/proposta.html" },
    "06-revisao":   { "status": "pendente",  "versao": 0, "atualizado_em": null, "artefato": "proposta/06-revisao.md" }
  },

  "saida": { "pdf": null, "paginas": null, "transbordos": null, "render_em": null },
  "rastreabilidade": [
    { "decisao": "Modelo = implantação", "origem": "E03, E07 (tabela de sinais do contrato 01)" }
  ],
  "alertas": []
}
```

## Regras de estado

- Estados: `pendente` | `concluida` | `desatualizada`.
- Refazer a fase N marca **todas** as fases > N como `desatualizada`.
- Refazer 02 ou 03 muda o `orcamento_hash`; quando o hash gravado no checkpoint
  diverge do atual, `checkpoint_humano.status` volta a `pendente` e as fases
  04, 05 e 06 ficam **bloqueadas** até nova aprovação explícita. É a invalidação
  em cascata aplicada ao gate humano — e é o que impede um preço aprovado de
  virar outro preço em silêncio.
- `versao` incrementa a cada reexecução da fase.
