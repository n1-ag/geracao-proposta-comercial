---
description: Roda isoladamente a Fase 03 — a precificação. É script, não agente: nenhum LLM calcula valor aqui.
---

Execute **somente** a Fase 03. Esta fase não tem agente: quem calcula é o Python.

1. Leia `specs/contracts/03-orcamento.contract.md`.
2. Confira que `proposta/02-escopo.json` existe e está atualizado.
3. Rode a suíte golden **antes** de qualquer coisa:
   ```
   python3 scripts/auditar.py precos
   ```
   Se falhar, **pare**. Não prossiga e não ajuste número nenhum na mão.
4. Rode a precificação:
   ```
   python3 scripts/precificar.py --escopo proposta/02-escopo.json \
       --dados-cliente entrada/dados-cliente.md --saida proposta/03-orcamento.json
   ```
5. Confira a coerência entre os espelhos do escopo:
   ```
   python3 scripts/auditar.py escopo proposta/02-escopo.json proposta/02-escopo.md
   ```
6. Apresente **na íntegra** o conteúdo de `proposta/03-orcamento.md` — é a
   memória de cálculo que o humano precisa ler no checkpoint.
7. Atualize o manifest e marque `checkpoint_humano.status` como `pendente`,
   gravando o `orcamento_hash` atual.
8. Lembre que as fases 04 em diante estão bloqueadas até a aprovação explícita.
