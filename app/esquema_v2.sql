-- Migração v1 → v2: autenticação.
--
-- O app passou a ser exposto num subdomínio público. Estas três tabelas são o
-- que separa "o time comercial usa" de "a internet usa".

CREATE TABLE usuarios (
  id            INTEGER PRIMARY KEY AUTOINCREMENT,
  email         TEXT NOT NULL UNIQUE,
  senha_hash    TEXT NOT NULL,
  salt          TEXT NOT NULL,
  criado_em     TEXT NOT NULL,
  ultimo_acesso TEXT
);

-- Sessão em banco, não em token assinado: é o que faz "sair" e a revogação em
-- massa (troca de senha) terem efeito imediato.
CREATE TABLE sessoes (
  token      TEXT PRIMARY KEY,
  usuario_id INTEGER NOT NULL REFERENCES usuarios(id) ON DELETE CASCADE,
  criado_em  TEXT NOT NULL,
  expira_em  TEXT NOT NULL,
  ip         TEXT
);

CREATE INDEX ix_sessao_usuario ON sessoes(usuario_id);
CREATE INDEX ix_sessao_expira  ON sessoes(expira_em);

CREATE TABLE tentativas_login (
  id      INTEGER PRIMARY KEY AUTOINCREMENT,
  ip      TEXT NOT NULL,
  em      TEXT NOT NULL,
  sucesso INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX ix_tentativa ON tentativas_login(ip, em);
