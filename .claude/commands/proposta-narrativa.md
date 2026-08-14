---
description: Roda isoladamente a Fase 04 do workflow de proposta comercial (redator-proposta).
---

Execute **somente** a Fase 04.

1. Leia `specs/steering/*.md` e `specs/contracts/04-narrativa.contract.md`.
2. Confira a dependência: `proposta/03-orcamento.md e o checkpoint aprovado` precisa existir e estar atualizado. Se não
   estiver, sugira a fase anterior e **pare**.
3. Invoque o subagente `redator-proposta` via Task, passando o objetivo da fase, o
   caminho do contrato e o lembrete de rastreabilidade.\n4. **Verifique o checkpoint.** Se `manifest.checkpoint_humano.status` não for\n   `"aprovado"`, ou se o `orcamento_hash` gravado divergir do atual, **pare**:\n   a fase 04 é bloqueada até nova aprovação.\n
5. Valide a saída contra o contrato. Se faltar seção obrigatória, reinvoque com
   o apontamento específico (até 2×).
6. Atualize `proposta/manifest.json`: status `concluida`, `versao`+1,
   `atualizado_em` de hoje, e marque as fases posteriores como `desatualizada`.
   Se esta fase for a 02, derrube também `checkpoint_humano.status` para
   `pendente`.
7. Reporte o que foi produzido em `proposta/04-narrativa.md` e o que ficou pendente.
