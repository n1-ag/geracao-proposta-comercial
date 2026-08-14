---
description: Valida os dados comerciais e roda a suíte golden de precificação. Rode sempre depois de mexer em dados/*.toml.
argument-hint: "[--simular ...]"
---

Verificação dos dados comerciais.

1. Rode:
   ```
   python3 scripts/auditar.py precos
   ```
   Isso valida `precos.toml`, `catalogo-modulos.toml` e
   `condicoes-comerciais.toml` (ids únicos, faixas coerentes, critério de
   complexidade presente, faixas de fee sem buraco, `natureza` fora do cálculo) e
   roda todos os casos de `dados/casos-teste-precificacao.toml`.

2. Se algum caso golden falhar, **não altere o caso para o script passar.**
   Decida primeiro qual dos dois está certo:
   - mudou uma regra de negócio → atualize o caso golden **e** diga isso na saída;
   - o script regrediu → conserte o script.

3. Simulações rápidas, se `$ARGUMENTS` pedir:
   ```
   python3 scripts/precificar.py --simular --converter 50000
   python3 scripts/precificar.py --simular --pacote 26
   python3 scripts/precificar.py --simular --plataforma vtex --horas-adicionais 40
   python3 scripts/precificar.py --simular --plataforma shopify --layout-do-cliente
   ```

4. Reporte quantas verificações passaram e o resultado do caso de referência
   (R$ 50.000 → 26h × R$ 210,00 = R$ 5.460,00/mês).
