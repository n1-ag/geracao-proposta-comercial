---
description: Re-renderiza o PDF a partir do HTML já montado, sem reprocessar conteúdo. Use depois de um ajuste manual no HTML ou no CSS.
---

Re-render isolado. **Não invoque agente nenhum e não reprocesse conteúdo.**

1. Confira que `proposta/proposta.html` existe.
2. Se `proposta/03-orcamento.json` existir, compare o `hash_entrada` gravado com
   o hash atual de `dados/*.toml`. Se divergirem, **avise em destaque**: a tabela
   de preços mudou desde que este orçamento foi calculado, e re-renderizar vai
   produzir um PDF com valores antigos. Ofereça rodar a fase 03 de novo.
3. Renderize:
   ```
   python3 scripts/render_pdf.py --html proposta/proposta.html \
       --orcamento proposta/03-orcamento.json --auditar --estrito --png saida/preview/
   ```
4. Rode as auditorias:
   ```
   python3 scripts/auditar.py pdf      saida/<arquivo>.pdf --html proposta/proposta.html --orcamento proposta/03-orcamento.json
   python3 scripts/auditar.py numeros  proposta/proposta.html proposta/03-orcamento.json
   python3 scripts/auditar.py template proposta/proposta.html
   ```
5. Atualize o bloco `saida` do manifest e reporte o caminho do PDF.
