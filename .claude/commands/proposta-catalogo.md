---
description: Incorpora ao catálogo de módulos um item que foi cotado fora dele, com faixas de horas e critério de complexidade.
argument-hint: "[nome do item]"
---

Utilitário de manutenção do catálogo. Item: `$ARGUMENTS`.

1. Leia `specs/contracts/catalogo.contract.md` e `dados/catalogo-modulos.toml`.
2. Se houver `proposta/02-escopo.json`, liste os `itens_fora_catalogo` e pergunte
   qual incorporar.
3. **Antes de criar, tente não criar.** Percorra o catálogo e verifique se algum
   item existente cobre o caso com outra complexidade. Um catálogo que só cresce
   perde a função de padronizar. Se houver candidato, proponha usá-lo.
4. Se for mesmo item novo, colete e **exija**:
   - `id` em kebab-case, único
   - `nome`, `categoria`, `unidade`
   - as três faixas `horas_baixa`, `horas_media`, `horas_alta`, com `min ≤ max`
   - `criterio_complexidade` com as três linhas (baixa/media/alta) — este é o
     texto que o agente de escopo vai ler para classificar; sem ele a
     classificação vira palpite
   - `descricao_proposta`, na voz da N1 (ver `steering/tom-de-voz.md`)
   - `exige_app`, se instala/configura aplicativo
   - a **justificativa** de por que nenhum item existente servia
5. Acrescente o bloco `[[itens]]` na seção temática correta do arquivo,
   preservando os comentários.
6. Valide:
   ```
   python3 scripts/auditar.py precos
   ```
7. Se o item estava em `itens_fora_catalogo`, ofereça reescrever o
   `02-escopo.json` movendo-o para `itens` — e lembre que isso derruba o
   checkpoint e exige rodar a fase 03 de novo.
