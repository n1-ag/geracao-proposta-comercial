-- v5 — o ajuste passa a ter resposta.
--
-- Até aqui o pedido de ajuste era só texto: entrava, sumia dentro de uma
-- execução de agente, e o vendedor descobria pelo total (ou pela ausência dele)
-- o que tinha acontecido. Guardar a interpretação e o resultado é o que permite
-- a tela dizer, linha por linha, o que foi feito e o que não foi.

ALTER TABLE ajustes ADD COLUMN interpretacao TEXT;
ALTER TABLE ajustes ADD COLUMN resultado TEXT;
