---
description: Roda isoladamente a Fase 05 do workflow de proposta comercial (montador-html).
---

Execute **somente** a Fase 05.

1. Leia `specs/steering/*.md` e `specs/contracts/05-html.contract.md`.
2. Confira a dependência: `proposta/04-narrativa.md` precisa existir e estar atualizado. Se não
   estiver, sugira a fase anterior e **pare**.
3. Invoque o subagente `montador-html` via Task, passando o objetivo da fase, o
   caminho do contrato e o lembrete de rastreabilidade.\n4. Depois que o agente terminar, rode e reporte:\n   ```\n   python3 scripts/auditar.py template proposta/proposta.html\n   python3 scripts/auditar.py numeros  proposta/proposta.html proposta/03-orcamento.json\n   ```\n
5. Valide a saída contra o contrato. Se faltar seção obrigatória, reinvoque com
   o apontamento específico (até 2×).
6. Atualize `proposta/manifest.json`: status `concluida`, `versao`+1,
   `atualizado_em` de hoje, e marque as fases posteriores como `desatualizada`.
   Se esta fase for a 02, derrube também `checkpoint_humano.status` para
   `pendente`.
7. Reporte o que foi produzido em `proposta/proposta.html e proposta/05-montagem.md` e o que ficou pendente.
