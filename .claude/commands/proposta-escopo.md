---
description: Roda isoladamente a Fase 02 do workflow de proposta comercial (escopo-mapper).
---

Execute **somente** a Fase 02.

1. Leia `specs/steering/*.md` e `specs/contracts/02-escopo.contract.md`.
2. Confira a dependência: `proposta/01-briefing.md` precisa existir e estar atualizado. Se não
   estiver, sugira a fase anterior e **pare**.
3. Invoque o subagente `escopo-mapper` via Task, passando o objetivo da fase, o
   caminho do contrato e o lembrete de rastreabilidade.
5. Valide a saída contra o contrato. Se faltar seção obrigatória, reinvoque com
   o apontamento específico (até 2×).
6. Atualize `proposta/manifest.json`: status `concluida`, `versao`+1,
   `atualizado_em` de hoje, e marque as fases posteriores como `desatualizada`.
   Se esta fase for a 02, derrube também `checkpoint_humano.status` para
   `pendente`.
7. Reporte o que foi produzido em `proposta/02-escopo.md e proposta/02-escopo.json` e o que ficou pendente.
