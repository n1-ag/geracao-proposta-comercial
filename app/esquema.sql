-- Esquema v1 do app N1 Propostas.
--
-- O banco é índice e registro comercial; a verdade dos artefatos continua sendo
-- o sistema de arquivos (propostas/<slug>/). Se o banco sumir, `importar.py`
-- reconstrói tudo a partir dos workspaces — menos o que só existe aqui: o
-- status comercial e o histórico.

PRAGMA user_version = 1;

-- ---------------------------------------------------------------- propostas

CREATE TABLE propostas (
  id                INTEGER PRIMARY KEY AUTOINCREMENT,
  slug              TEXT NOT NULL UNIQUE,          -- '0007-tireshop'
  workspace         TEXT NOT NULL UNIQUE,          -- 'propostas/0007-tireshop'
  origem            TEXT NOT NULL DEFAULT 'app',   -- 'app' | 'importado'
  origem_ref        TEXT UNIQUE,                   -- pasta de origem: chave de idempotência do import

  -- cadastro: o que o comercial digita
  cliente           TEXT NOT NULL,
  razao_social      TEXT,
  contato           TEXT,
  cargo_contato     TEXT,
  email             TEXT,
  whatsapp          TEXT,
  validade          TEXT,                          -- ISO 'AAAA-MM-DD'
  modelo            TEXT,                          -- implantacao|evolucao|NULL(auto)
  plataforma        TEXT,
  natureza          TEXT,
  layout_do_cliente INTEGER,                       -- 0|1|NULL(auto)
  pacote_mensal_h   INTEGER,
  reuniao_por       TEXT,
  data_reuniao      TEXT,
  outros_presentes  TEXT,

  -- o que o pipeline resolveu de fato (pode divergir do cadastro quando 'auto')
  modelo_res        TEXT,
  plataforma_res    TEXT,
  natureza_res      TEXT,

  -- resultado financeiro
  total_cru         REAL,                          -- numérico: é o que o dashboard soma
  total_fmt         TEXT,                          -- pronto do precificar.py; nunca reformatado
  total_tipo        TEXT,                          -- 'unico' (implantação) | 'mensal' (evolução)
  -- Implantação e evolução não somam na mesma unidade. Anualizar o mensal põe
  -- as duas na mesma régua para os totais do painel.
  valor_anualizado  REAL GENERATED ALWAYS AS (
                      CASE WHEN total_tipo = 'mensal' THEN total_cru * 12 ELSE total_cru END
                    ) STORED,
  evolucao_mensal     REAL,
  evolucao_mensal_fmt TEXT,
  prazo_fmt         TEXT,
  hash_orcamento    TEXT,                          -- nosso: sha256 do conteúdo canônico do 03-orcamento.json
  hash_dados        TEXT,                          -- do script: hash_entrada (só os TOML de preço)
  precos_versao     TEXT,

  -- estado
  status            TEXT NOT NULL DEFAULT 'rascunho',
  status_comercial  TEXT,                          -- NULL|enviada|aceita|recusada
  fase_atual        TEXT,
  checkpoint_status TEXT NOT NULL DEFAULT 'pendente',
  checkpoint_em     TEXT,
  erro_mensagem     TEXT,
  arquivada         INTEGER NOT NULL DEFAULT 0,

  -- saída
  pdf_caminho       TEXT,                          -- relativo ao workspace
  pdf_paginas       INTEGER,
  pdf_gerado_em     TEXT,

  custo_usd         REAL NOT NULL DEFAULT 0,

  criado_em         TEXT NOT NULL,
  atualizado_em     TEXT NOT NULL,
  enviada_em        TEXT,
  decidida_em       TEXT
);

CREATE INDEX ix_prop_status ON propostas(status);
CREATE INDEX ix_prop_com    ON propostas(status_comercial);
CREATE INDEX ix_prop_criado ON propostas(criado_em);
CREATE INDEX ix_prop_pdf    ON propostas(pdf_gerado_em);

-- ---------------------------------------------------------------- execuções

CREATE TABLE execucoes (
  id             INTEGER PRIMARY KEY AUTOINCREMENT,
  proposta_id    INTEGER NOT NULL REFERENCES propostas(id) ON DELETE CASCADE,
  alvo           TEXT NOT NULL,   -- bloco_01_03|reajuste_02_03|bloco_04_06|rerender|so_fase
  desde_fase     TEXT,
  status         TEXT NOT NULL,   -- fila|executando|concluida|erro|interrompida|cancelada
  enfileirada_em TEXT NOT NULL,
  comecou_em     TEXT,
  terminou_em    TEXT,
  custo_usd      REAL NOT NULL DEFAULT 0,
  erro           TEXT,
  pid            INTEGER
);

CREATE INDEX ix_exec_status ON execucoes(status);
CREATE INDEX ix_exec_prop   ON execucoes(proposta_id, enfileirada_em);

-- -------------------------------------------------------------------- fases

CREATE TABLE fases (
  id           INTEGER PRIMARY KEY AUTOINCREMENT,
  execucao_id  INTEGER NOT NULL REFERENCES execucoes(id) ON DELETE CASCADE,
  proposta_id  INTEGER NOT NULL REFERENCES propostas(id) ON DELETE CASCADE,
  fase         TEXT NOT NULL,   -- 01|02|03|04|05|06a|06b|auditoria
  executor     TEXT NOT NULL,   -- claude|script
  comando      TEXT,
  status       TEXT NOT NULL,   -- executando|ok|erro|pulada
  tentativa    INTEGER NOT NULL DEFAULT 1,
  comecou_em   TEXT,
  terminou_em  TEXT,
  duracao_ms   INTEGER,
  exit_code    INTEGER,
  session_id   TEXT,            -- permite `claude --resume <id>` para depurar
  custo_usd    REAL NOT NULL DEFAULT 0,
  resumo       TEXT,
  stderr_cauda TEXT,
  log_caminho  TEXT
);

CREATE INDEX ix_fases_prop ON fases(proposta_id, fase);
CREATE INDEX ix_fases_exec ON fases(execucao_id);

-- ------------------------------------------------------------------ ajustes

-- Pedidos do comercial no checkpoint. Espelhados em
-- propostas/<slug>/proposta/ajustes.md, que é o canal que chega ao agente.
CREATE TABLE ajustes (
  id              INTEGER PRIMARY KEY AUTOINCREMENT,
  proposta_id     INTEGER NOT NULL REFERENCES propostas(id) ON DELETE CASCADE,
  ordem           INTEGER NOT NULL,
  texto           TEXT NOT NULL,
  sobre_hash      TEXT,          -- hash_orcamento vigente quando foi pedido
  sobre_total_fmt TEXT,
  criado_em       TEXT NOT NULL,
  execucao_id     INTEGER REFERENCES execucoes(id) ON DELETE SET NULL,
  aplicado_em     TEXT
);

CREATE UNIQUE INDEX ix_ajuste_ordem ON ajustes(proposta_id, ordem);

-- ------------------------------------------------------------------ alertas

CREATE TABLE alertas (
  id             INTEGER PRIMARY KEY AUTOINCREMENT,
  proposta_id    INTEGER NOT NULL REFERENCES propostas(id) ON DELETE CASCADE,
  codigo         TEXT,
  severidade     TEXT,           -- alta|media|baixa
  mensagem       TEXT,
  hash_orcamento TEXT,           -- a qual versão do orçamento este alerta pertence
  criado_em      TEXT NOT NULL
);

CREATE INDEX ix_alerta_prop ON alertas(proposta_id, severidade);

-- ------------------------------------------------------------------ lacunas

CREATE TABLE lacunas (
  id             INTEGER PRIMARY KEY AUTOINCREMENT,
  proposta_id    INTEGER NOT NULL REFERENCES propostas(id) ON DELETE CASCADE,
  texto          TEXT NOT NULL,
  hash_orcamento TEXT,
  criado_em      TEXT NOT NULL
);

CREATE INDEX ix_lacuna_prop ON lacunas(proposta_id);

-- -------------------------------------------------------- histórico e trilha

-- A coluna status_comercial sozinha não sabe que uma "recusada" já foi
-- "enviada". O funil e o tempo de ciclo do painel saem daqui.
CREATE TABLE historico_status (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  proposta_id INTEGER NOT NULL REFERENCES propostas(id) ON DELETE CASCADE,
  campo       TEXT NOT NULL,     -- 'status' | 'status_comercial'
  de          TEXT,
  para        TEXT NOT NULL,
  observacao  TEXT,
  em          TEXT NOT NULL
);

CREATE INDEX ix_hist ON historico_status(proposta_id, campo, em);

CREATE TABLE eventos (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  proposta_id INTEGER REFERENCES propostas(id) ON DELETE CASCADE,
  tipo        TEXT NOT NULL,
  detalhe     TEXT,
  criado_em   TEXT NOT NULL
);

CREATE INDEX ix_evento_prop ON eventos(proposta_id, criado_em);
