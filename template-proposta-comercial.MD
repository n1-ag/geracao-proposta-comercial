# Template de Proposta Comercial — N1.AG

> **Este documento foi substituído.** Ele descrevia um `template_proposta_n1.html`
> e uma pasta `assets/` que não existiam neste repositório — só os PDFs
> renderizados sobreviveram. O template foi reconstruído por medição direta
> desses PDFs e agora vive em `templates/`.

## Onde está cada coisa agora

| O que você procurava | Onde está |
|---|---|
| O template HTML | `templates/proposta.template.html` + `templates/secoes/` + `templates/blocos/` |
| O exemplo pronto (Urban Arts) | `templates/exemplo/urban-arts.html` |
| Os assets (logo, Poppins) | `templates/assets/img/` e `templates/assets/fonts/` |
| A identidade visual, com as medidas | `specs/steering/marca.md` |
| Como gerar o PDF | `scripts/render_pdf.py` — ver `GUIA.md` §7 |
| Os blocos disponíveis e seus marcadores | `specs/contracts/05-html.contract.md` |

## O que mudou em relação ao documento original

- **Renderizador:** Chrome headless via `playwright`, não WeasyPrint. O layout
  usa flexbox e o Chrome já está instalado; o `render_pdf.py` sobe um servidor
  HTTP efêmero, porque sob `file://` o `@font-face` falha em silêncio e o PDF sai
  em fonte de fallback.
- **Transbordo:** deixou de ser um cuidado manual. `.page` tem `overflow: hidden`
  e o render mede o transbordo antes de imprimir — em modo estrito, não emite PDF
  com conteúdo cortado.
- **Renumeração:** continua manual, mas agora é verificada por
  `auditar.py pdf`.
- **O glifo ✓:** virou SVG inline. A Poppins não tem U+2713, e depender da fonte
  de fallback do sistema era a falha silenciosa clássica.
- **Um bloco novo:** `.planos`, para as três opções de pacote nas propostas de
  fee mensal.

Comece pelo `README.md`.
