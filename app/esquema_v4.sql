-- Migração v3 → v4.
--
-- Marca que a execução é a continuação de algo cortado no meio (reinício do
-- serviço), e não um pedido novo. Numa retomada, fase cujo artefato já está
-- válido é pulada em vez de refeita — é o que torna atualizar o app barato,
-- mesmo com proposta em andamento.
ALTER TABLE execucoes ADD COLUMN retomada INTEGER NOT NULL DEFAULT 0;
