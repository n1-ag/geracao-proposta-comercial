-- Migração v2 → v3.

-- Fechamento comercial: o preço que uma pessoa negociou, no lugar do que o
-- escopo calculou. Fica na proposta (não só no orçamento gerado) porque
-- precisa sobreviver a um reprocessamento das fases 02 e 03 — senão, pedir um
-- ajuste de escopo desfaria o valor combinado com o cliente.
ALTER TABLE propostas ADD COLUMN valor_fechado REAL;
ALTER TABLE propostas ADD COLUMN motivo_fechado TEXT;
ALTER TABLE propostas ADD COLUMN fechado_em TEXT;

-- Conversa com o agente sobre a proposta, no gate de aprovação.
CREATE TABLE conversas (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  proposta_id INTEGER NOT NULL REFERENCES propostas(id) ON DELETE CASCADE,
  papel       TEXT NOT NULL,           -- 'humano' | 'agente'
  texto       TEXT NOT NULL,
  session_id  TEXT,
  custo_usd   REAL NOT NULL DEFAULT 0,
  criado_em   TEXT NOT NULL
);

CREATE INDEX ix_conversa_prop ON conversas(proposta_id, id);
