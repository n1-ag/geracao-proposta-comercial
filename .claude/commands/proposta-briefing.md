---
description: Roda isoladamente a Fase 01 do workflow de proposta comercial (transcricao-analyzer).
---

Execute **somente** a Fase 01.

1. Leia `specs/steering/*.md` e `specs/contracts/01-briefing.contract.md`.
2. Confira a dependência: `entrada/transcricao.md` e `entrada/dados-cliente.md`
   precisam existir e estar atualizados. Se não estiverem, sugira a fase anterior
   e **pare**.
   `entrada/observacoes.md` é opcional — quando existir, lembre o subagente de
   analisá-lo **junto** com a transcrição e numerar como `O##` (contrato 01,
   seção 12b).
3. Invoque o subagente `transcricao-analyzer` via Task, passando o objetivo da fase, o
   caminho do contrato e o lembrete de rastreabilidade.
5. Valide a saída contra o contrato. Se faltar seção obrigatória, reinvoque com
   o apontamento específico (até 2×).
6. Atualize `proposta/manifest.json`: status `concluida`, `versao`+1,
   `atualizado_em` de hoje, e marque as fases posteriores como `desatualizada`.
   Se esta fase for a 02, derrube também `checkpoint_humano.status` para
   `pendente`.
7. Reporte o que foi produzido em `proposta/01-briefing.md` e o que ficou pendente.
