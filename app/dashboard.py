"""As agregações do painel.

Tudo em SQL. Nenhuma soma acontece no JavaScript — o front recebe números
prontos e só desenha.

Convenções que valem para o arquivo inteiro:

* `arquivada = 0` em toda consulta: proposta descartada no app sai das contas.
* `valor_anualizado` no lugar de `total_cru`: implantação (valor único) e
  evolução (mensal) não somam na mesma unidade; a coluna gerada põe as duas na
  mesma régua.
* "enviada" no funil significa *já passou por enviada alguma vez*, o que sai de
  `historico_status`. A coluna `status_comercial` sozinha esqueceria que uma
  recusada foi enviada antes — e a taxa de conversão sairia errada.
"""

from __future__ import annotations

import db

ATIVAS = "arquivada = 0"


# -----------------------------------------------------------------------------
# (a) funil
# -----------------------------------------------------------------------------


def funil() -> dict:
    etapas = db.buscar(
        f"""
        WITH v AS (
          SELECT COALESCE(status_comercial, status) AS etapa,
                 COALESCE(valor_anualizado, 0)      AS valor
          FROM propostas WHERE {ATIVAS}
        )
        SELECT etapa, COUNT(*) AS n, SUM(valor) AS valor
        FROM v GROUP BY etapa ORDER BY n DESC
        """
    )

    passou = db.um(
        """
        SELECT
          (SELECT COUNT(DISTINCT proposta_id) FROM historico_status
            WHERE campo = 'status_comercial' AND para = 'enviada')  AS enviadas,
          (SELECT COUNT(DISTINCT proposta_id) FROM historico_status
            WHERE campo = 'status_comercial' AND para = 'aceita')   AS aceitas,
          (SELECT COUNT(DISTINCT proposta_id) FROM historico_status
            WHERE campo = 'status_comercial' AND para = 'recusada') AS recusadas
        """
    ) or {}

    enviadas = passou.get("enviadas") or 0
    aceitas = passou.get("aceitas") or 0
    decididas = aceitas + (passou.get("recusadas") or 0)

    return {
        "etapas": etapas,
        "enviadas": enviadas,
        "aceitas": aceitas,
        "recusadas": passou.get("recusadas") or 0,
        # Sobre as enviadas: mede quanto do que saiu já voltou como sim.
        "taxa_aceite_pct": round(100.0 * aceitas / enviadas, 1) if enviadas else None,
        # Sobre as decididas: ignora quem ainda não respondeu. É a taxa "real"
        # quando há muita proposta em aberto.
        "taxa_aceite_decididas_pct": round(100.0 * aceitas / decididas, 1) if decididas else None,
    }


# -----------------------------------------------------------------------------
# (b) valores
# -----------------------------------------------------------------------------


def valores() -> dict:
    linha = db.um(
        f"""
        SELECT
          COUNT(*)                                                       AS total_propostas,
          SUM(CASE WHEN status_comercial IN ('enviada','aceita','recusada')
                   THEN valor_anualizado END)                            AS total_enviado,
          SUM(CASE WHEN status_comercial = 'aceita'
                   THEN valor_anualizado END)                            AS total_aceito,
          SUM(CASE WHEN status_comercial = 'enviada'
                   THEN valor_anualizado END)                            AS em_aberto,
          SUM(CASE WHEN status_comercial = 'recusada'
                   THEN valor_anualizado END)                            AS total_perdido,
          SUM(CASE WHEN status_comercial IS NULL AND status = 'gerada'
                   THEN valor_anualizado END)                            AS gerado_sem_envio,
          AVG(CASE WHEN status_comercial = 'aceita'
                   THEN valor_anualizado END)                            AS ticket_medio_aceito,
          AVG(CASE WHEN valor_anualizado > 0
                   THEN valor_anualizado END)                            AS ticket_medio_geral,
          SUM(COALESCE(custo_usd, 0))                                    AS custo_usd
        FROM propostas WHERE {ATIVAS}
        """
    ) or {}
    return {k: (round(v, 2) if isinstance(v, float) else v) for k, v in linha.items()}


# -----------------------------------------------------------------------------
# (c) produção no tempo
# -----------------------------------------------------------------------------


def producao() -> dict:
    por_mes = db.buscar(
        f"""
        SELECT strftime('%Y-%m', pdf_gerado_em) AS periodo,
               COUNT(*)                         AS geradas,
               SUM(valor_anualizado)            AS valor
        FROM propostas
        WHERE {ATIVAS} AND pdf_gerado_em IS NOT NULL
        GROUP BY periodo ORDER BY periodo
        """
    )

    por_semana = db.buscar(
        f"""
        SELECT strftime('%Y-W%W', pdf_gerado_em) AS periodo, COUNT(*) AS geradas
        FROM propostas
        WHERE {ATIVAS} AND pdf_gerado_em >= date('now', '-84 days')
        GROUP BY periodo ORDER BY periodo
        """
    )

    # Do cadastro ao PDF. Inclui o tempo em que a proposta ficou parada
    # esperando alguém aprovar — é o número que o comercial sente.
    horas_totais = db.valor(
        f"""
        SELECT AVG((julianday(pdf_gerado_em) - julianday(criado_em)) * 24.0)
        FROM propostas WHERE {ATIVAS} AND pdf_gerado_em IS NOT NULL
        """
    )

    # Só as fases somadas. É o custo de máquina, sem espera humana.
    minutos_maquina = db.valor(
        """
        SELECT AVG(t.min_total) FROM (
          SELECT proposta_id, SUM(duracao_ms) / 60000.0 AS min_total
          FROM fases WHERE status = 'ok' GROUP BY proposta_id
        ) t
        """
    )

    # Quanto tempo o orçamento espera no gate humano.
    horas_no_gate = db.valor(
        """
        SELECT AVG((julianday(p.checkpoint_em) - julianday(f.terminou_em)) * 24.0)
        FROM propostas p
        JOIN fases f ON f.proposta_id = p.id AND f.fase = '03' AND f.status = 'ok'
        WHERE p.checkpoint_status = 'aprovado' AND p.checkpoint_em IS NOT NULL
        """
    )

    return {
        "por_mes": por_mes,
        "por_semana": por_semana,
        "horas_cadastro_ate_pdf": round(horas_totais, 1) if horas_totais else None,
        "minutos_de_maquina": round(minutos_maquina, 1) if minutos_maquina else None,
        "horas_no_gate": round(horas_no_gate, 1) if horas_no_gate else None,
    }


# -----------------------------------------------------------------------------
# (d) recortes de negócio
# -----------------------------------------------------------------------------

_RECORTE = """
SELECT
  COALESCE(NULLIF({col_res}, ''), NULLIF({col}, ''), 'não informada')     AS chave,
  COUNT(*)                                                               AS n,
  SUM(valor_anualizado)                                                  AS valor,
  AVG(valor_anualizado)                                                  AS ticket_medio,
  SUM(CASE WHEN status_comercial = 'aceita' THEN 1 ELSE 0 END)           AS aceitas,
  SUM(CASE WHEN status_comercial IN ('enviada','aceita','recusada')
           THEN 1 ELSE 0 END)                                            AS enviadas
FROM propostas WHERE {ativas}
GROUP BY chave ORDER BY n DESC, valor DESC
"""


def _recorte(col_res: str, col: str) -> list[dict]:
    linhas = db.buscar(_RECORTE.format(col_res=col_res, col=col, ativas=ATIVAS))
    for l in linhas:
        l["ticket_medio"] = round(l["ticket_medio"], 2) if l["ticket_medio"] else None
        l["taxa_aceite_pct"] = (
            round(100.0 * l["aceitas"] / l["enviadas"], 1) if l["enviadas"] else None
        )
    return linhas


def recortes() -> dict:
    return {
        "plataformas": _recorte("plataforma_res", "plataforma"),
        "modelos": _recorte("modelo_res", "modelo"),
    }


# -----------------------------------------------------------------------------
# Complementares
# -----------------------------------------------------------------------------


def pendencias() -> dict:
    """O que exige ação de alguém agora."""
    return {
        "aguardando_aprovacao": db.valor(
            f"SELECT COUNT(*) FROM propostas WHERE {ATIVAS} AND status = 'aguardando_aprovacao'", (), 0
        ),
        "com_erro": db.valor(
            f"SELECT COUNT(*) FROM propostas WHERE {ATIVAS} AND status = 'erro'", (), 0
        ),
        "na_fila": db.valor("SELECT COUNT(*) FROM execucoes WHERE status = 'fila'", (), 0),
        "executando": db.valor("SELECT COUNT(*) FROM execucoes WHERE status = 'executando'", (), 0),
        "alertas_altos": db.buscar(
            f"""
            SELECT p.id, p.cliente, a.codigo, a.mensagem
            FROM alertas a JOIN propostas p ON p.id = a.proposta_id
            WHERE a.severidade = 'alta' AND p.{ATIVAS}
              AND (p.status_comercial IS NULL OR p.status_comercial <> 'recusada')
            ORDER BY p.atualizado_em DESC LIMIT 8
            """
        ),
    }


def recentes(limite: int = 6) -> list[dict]:
    return db.buscar(
        f"""
        SELECT id, slug, cliente, plataforma_res, plataforma, total_fmt, total_tipo,
               status, status_comercial, atualizado_em
        FROM propostas WHERE {ATIVAS}
        ORDER BY atualizado_em DESC LIMIT ?
        """,
        (limite,),
    )


def tudo() -> dict:
    return {
        "funil": funil(),
        "valores": valores(),
        "producao": producao(),
        "recortes": recortes(),
        "pendencias": pendencias(),
        "recentes": recentes(),
    }
