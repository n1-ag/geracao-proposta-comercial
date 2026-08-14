---
description: Roda a Fase 06 — render do PDF em modo estrito e revisão qualitativa.
---

Execute **somente** a Fase 06.

1. Leia `specs/contracts/06-revisao.contract.md`.
2. Confira que `proposta/proposta.html` e `proposta/03-orcamento.json` existem.
3. Renderize em modo estrito:
   ```
   python3 scripts/render_pdf.py --html proposta/proposta.html \
       --orcamento proposta/03-orcamento.json --auditar --estrito --png saida/preview/
   ```
   - Código 3 (transbordo): reinvoque `montador-html` com
     `saida/relatorio-paginacao.json`. Máximo de 2 tentativas.
   - Código 4 (fonte): a Poppins não carregou. Confira `templates/assets/fonts/`.
   - Código 2: algum recurso deu 404. Confira os caminhos relativos do HTML.
4. Invoque o subagente `revisor-proposta` via Task.
5. Atualize o bloco `saida` do manifest: caminho do PDF, páginas, transbordos e
   data do render.
6. Reporte o veredito e, se houver correção pendente, qual fase reinvocar.
