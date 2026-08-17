"""Quanto tempo cada fase costuma levar.

Gerar uma proposta leva dezenas de minutos, e boa parte disso é o agente em
silêncio. Sem uma previsão, quem espera não distingue "demorado" de "travado" —
então o app precisa dizer, com honestidade, quanto ainda falta.

A fonte preferida é o histórico do próprio app: a mediana das execuções bem
sucedidas de cada fase, que se ajusta ao tamanho das transcrições e ao modelo
configurado. Enquanto não houver histórico suficiente, valem os padrões abaixo,
medidos em execuções reais deste repositório.
"""

from __future__ import annotations

import db

# Segundos por fase, medidos numa proposta de implantação Shopify com uma
# transcrição de 130 linhas. São ordem de grandeza, não promessa.
PADRAO = {
    "01": 220,   # briefing: lê a transcrição inteira e numera as evidências
    "02": 295,   # escopo: lê o catálogo de 58 itens e mapeia demanda por demanda
    "03": 2,     # orçamento: script, praticamente instantâneo
    "04": 490,   # narrativa: escreve as 8 seções dentro dos limites
    "05": 560,   # montagem: monta o HTML dos templates
    "06a": 5,    # render: script + Chrome
    "06": 535,   # revisão qualitativa sobre o PDF
    "auditoria": 2,
}

# Abaixo disso a mediana é ruído, não sinal.
MINIMO_DE_AMOSTRAS = 3

ORDEM = ["01", "02", "03", "04", "05", "06"]

# O que cada bloco de execução percorre.
BLOCOS = {
    "bloco_01_03": ["01", "02", "03"],
    "reajuste_02_03": ["02", "03"],
    "bloco_04_06": ["04", "05", "06a", "06"],
    "rerender": ["06a"],
}


def _mediana(valores: list[float]) -> float:
    ordenados = sorted(valores)
    meio = len(ordenados) // 2
    if len(ordenados) % 2:
        return ordenados[meio]
    return (ordenados[meio - 1] + ordenados[meio]) / 2


def por_fase() -> dict[str, int]:
    """Segundos esperados por fase, com o histórico por cima dos padrões."""
    esperado = dict(PADRAO)

    # Só tentativas bem sucedidas: uma fase que falhou no meio não diz nada
    # sobre quanto ela leva quando dá certo.
    linhas = db.buscar(
        """SELECT fase, duracao_ms FROM fases
           WHERE status = 'ok' AND duracao_ms > 0
           ORDER BY id DESC LIMIT 200"""
    )
    amostras: dict[str, list[float]] = {}
    for l in linhas:
        amostras.setdefault(l["fase"], []).append(l["duracao_ms"] / 1000)

    for fase, valores in amostras.items():
        if len(valores) >= MINIMO_DE_AMOSTRAS:
            esperado[fase] = int(_mediana(valores))

    return esperado


def restante(alvo: str, fase_atual: str | None, decorrido_na_fase: float = 0) -> dict:
    """Quanto falta para o bloco terminar.

    Devolve `total_s`, `restante_s` e o desdobramento por fase, para a tela
    mostrar o caminho inteiro em vez de só um número.
    """
    esperado = por_fase()
    fases = BLOCOS.get(alvo, ORDEM)

    detalhe = []
    restam = 0
    passou = True

    for f in fases:
        segundos = esperado.get(f, 0)
        if fase_atual is None:
            estado = "pendente"
            restam += segundos
        elif f == fase_atual:
            estado = "atual"
            passou = False
            # O que já correu nesta fase não conta como restante — mas se ela
            # já passou do previsto, não fingimos que falta tempo negativo.
            restam += max(segundos - decorrido_na_fase, 0)
        elif passou:
            estado = "concluida"
        else:
            estado = "pendente"
            restam += segundos
        detalhe.append({"fase": f, "segundos": segundos, "estado": estado})

    return {
        "total_s": sum(esperado.get(f, 0) for f in fases),
        "restante_s": int(restam),
        "fases": detalhe,
        "aprendido": len(db.buscar(
            "SELECT 1 FROM fases WHERE status='ok' AND duracao_ms>0 LIMIT ?",
            (MINIMO_DE_AMOSTRAS,),
        )) >= MINIMO_DE_AMOSTRAS,
    }
