#!/usr/bin/env python3
"""
precificar.py — o ÚNICO lugar do boilerplate onde há aritmética de dinheiro.

Nenhum agente calcula preço. O agente da fase 02 escreve `02-escopo.json`
contendo apenas SELEÇÕES (id do catálogo, complexidade, quantidade) — não há
campo para horas nem para valor. Este script lê essas seleções e `dados/*.toml`
e produz `03-orcamento.json`, com todo valor duplicado em `_fmt` já formatado
em pt-BR. As fases seguintes só podem usar os campos `_fmt`.

Tudo em `Decimal` com ROUND_HALF_UP. Nada de `float` em dinheiro.

Uso
  python3 scripts/precificar.py --escopo proposta/02-escopo.json \
      --dados-cliente entrada/dados-cliente.md --saida proposta/03-orcamento.json
  python3 scripts/precificar.py --simular --plataforma vtex --horas-adicionais 40
  python3 scripts/precificar.py --simular --converter 50000
  python3 scripts/precificar.py --simular --pacote 26

Saída: 0 ok · 2 erro de uso · 3 erro nos dados (item fora do catálogo, etc.)
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import sys
import tomllib
from datetime import date, timedelta
from decimal import ROUND_DOWN, ROUND_HALF_UP, Decimal
from pathlib import Path

VERSAO = "1.0.0"
RAIZ = Path(__file__).resolve().parent.parent
DADOS = RAIZ / "dados"

CENTAVO = Decimal("0.01")
D = Decimal


# -----------------------------------------------------------------------------
# Formatação pt-BR sem `locale` (que depende de o locale estar instalado)
# -----------------------------------------------------------------------------
def brl(v: Decimal) -> str:
    v = D(v).quantize(CENTAVO, rounding=ROUND_HALF_UP)
    inteiro, _, cent = f"{abs(v):.2f}".partition(".")
    grupos = []
    while len(inteiro) > 3:
        grupos.insert(0, inteiro[-3:])
        inteiro = inteiro[:-3]
    grupos.insert(0, inteiro)
    return f"{'-' if v < 0 else ''}R$ {'.'.join(grupos)},{cent}"


def num(v: Decimal) -> float:
    """Valor numérico para o JSON, sempre com 2 casas."""
    return float(D(v).quantize(CENTAVO, rounding=ROUND_HALF_UP))


def half_up(v: Decimal) -> int:
    return int(D(v).quantize(D("1"), rounding=ROUND_HALF_UP))


MESES = ("janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho",
         "agosto", "setembro", "outubro", "novembro", "dezembro")


def data_extenso(d: date) -> str:
    return f"{d.day} de {MESES[d.month - 1]} de {d.year}"


# -----------------------------------------------------------------------------
# Carga dos dados
# -----------------------------------------------------------------------------
def carregar(nome: str) -> dict:
    caminho = DADOS / nome
    if not caminho.is_file():
        raise SystemExit(f"erro: falta {caminho}")
    with open(caminho, "rb") as f:
        return tomllib.load(f)


class Dados:
    def __init__(self):
        self.precos = carregar("precos.toml")
        self.condicoes = carregar("condicoes-comerciais.toml")
        cat = carregar("catalogo-modulos.toml")
        self.catalogo = {i["id"]: i for i in cat["itens"]}
        if len(self.catalogo) != len(cat["itens"]):
            raise SystemExit("erro: há ids repetidos em catalogo-modulos.toml")
        self.faixas = self.precos["evolucao"]["faixas"]

    def hash(self) -> str:
        h = hashlib.sha256()
        for nome in ("precos.toml", "catalogo-modulos.toml", "condicoes-comerciais.toml"):
            h.update((DADOS / nome).read_bytes())
        return "sha256:" + h.hexdigest()[:16]


# -----------------------------------------------------------------------------
# B) Faixa de fee mensal
# -----------------------------------------------------------------------------
def resolver_faixa(dados: Dados, horas: int) -> dict:
    for f in dados.faixas:
        if f["horas_min"] <= horas <= f["horas_max"]:
            return f
    # Acima do último teto, vale a última faixa.
    return dados.faixas[-1]


def tabela_faixas(dados: Dados) -> list:
    """
    A tabela de preço por hora, faixa a faixa, já formatada.

    Existe para a proposta poder oferecer **continuidade em evolução depois da
    entrega** sem que nenhum agente digite um número: o texto referencia
    `evolucao.tabela_faixas.N.valor_hora_fmt` e o montador resolve. O rótulo
    também sai em `_fmt` porque ele carrega dígitos ("até 10 h/mês") e
    `auditar.py numeros` só aceita valores vindos de chave `_fmt`.
    """
    return [{
        "id": f["id"],
        "rotulo_fmt": f["rotulo"],
        "valor_hora": num(f["valor_hora"]),
        "valor_hora_fmt": brl(D(f["valor_hora"])),
    } for f in dados.faixas]


def precificar_pacote(dados: Dados, horas: int) -> dict:
    f = resolver_faixa(dados, horas)
    mensal = D(horas) * D(f["valor_hora"])
    return {
        "horas": horas,
        "faixa_id": f["id"],
        "faixa_rotulo": f["rotulo"],
        "valor_hora": num(f["valor_hora"]), "valor_hora_fmt": brl(D(f["valor_hora"])),
        "valor_mensal": num(mensal), "valor_mensal_fmt": brl(mensal),
        "valor_12m": num(mensal * 12), "valor_12m_fmt": brl(mensal * 12),
    }


def opcoes_pacote(dados: Dados, horas_recomendadas: int) -> dict:
    """Três degraus da escada em torno do recomendado, com o do meio marcado."""
    escada = sorted(dados.precos["evolucao"]["pacotes_sugeridos"])
    if len(escada) < 3:
        raise SystemExit("erro: `pacotes_sugeridos` precisa de ao menos 3 degraus")
    # degrau mais próximo; empate resolve para o maior (mais valor entregue)
    alvo = min(range(len(escada)), key=lambda i: (abs(escada[i] - horas_recomendadas), -escada[i]))
    inicio = max(0, min(alvo - 1, len(escada) - 3))
    trio = escada[inicio:inicio + 3]
    rec = escada[alvo]
    return {
        "horas_recomendadas_calculadas": horas_recomendadas,
        "recomendado_horas": rec,
        "opcoes": [{**precificar_pacote(dados, h), "recomendado": h == rec} for h in trio],
    }


# -----------------------------------------------------------------------------
# C) Conversão implantação -> evolução
# -----------------------------------------------------------------------------
def converter(dados: Dados, valor_implantacao: Decimal) -> dict:
    conv = dados.precos["conversao"]
    anual = D(valor_implantacao) * D(str(conv["multiplicador_anual"]))
    mensal_alvo = anual / D(conv["contrato_meses"])

    avaliadas, fecham = [], []
    for f in dados.faixas:
        h = mensal_alvo / D(f["valor_hora"])
        dentro = D(f["horas_min"]) <= h <= D(f["horas_max"])
        avaliadas.append({
            "faixa_id": f["id"], "valor_hora": f["valor_hora"],
            "h": float(h.quantize(D("0.01"), rounding=ROUND_HALF_UP)),
            "dentro_da_faixa": dentro,
        })
        if dentro:
            fecham.append((f, h))

    ajuste, desempate = None, False
    if fecham:
        if len(fecham) > 1:
            desempate = True
            fecham.sort(key=lambda t: t[1], reverse=True)   # desempate = mais horas
        faixa, h_bruto = fecham[0]
    else:
        # Vale entre faixas: adota o piso da primeira faixa cujo mínimo o alvo
        # não alcança. São duas janelas estreitas — ver os casos golden.
        ajuste = "vale_entre_faixas"
        escolhida = None
        for f in dados.faixas:
            if mensal_alvo / D(f["valor_hora"]) < D(f["horas_min"]):
                escolhida = f
                break
        faixa = escolhida or dados.faixas[-1]
        h_bruto = D(faixa["horas_min"])

    h_final = max(1, half_up(h_bruto))
    # Arredondar pode jogar as horas para outra faixa; nesse caso vale a tabela,
    # não a faixa de origem — senão a proposta contradiz o próprio preço/hora.
    faixa_final = resolver_faixa(dados, h_final)
    mensal_final = D(h_final) * D(faixa_final["valor_hora"])

    alertas = []
    aplicavel = True
    if h_bruto < D(conv["piso_horas_mes"]):
        aplicavel = False
        alertas.append("VALOR_MUITO_BAIXO")
    elif h_final > conv["teto_horas_mes_alerta"]:
        alertas.append("VALOR_MUITO_ALTO")

    desvio = (mensal_final - mensal_alvo) / mensal_alvo * 100 if mensal_alvo else D(0)

    return {
        "aplicavel": aplicavel,
        "origem": "alternativa_convertida",
        "pacote_horas": h_final,
        "pacote_horas_fmt": f"{h_final} horas",
        "faixa_id": faixa_final["id"],
        "faixa_rotulo": faixa_final["rotulo"],
        "valor_hora": num(faixa_final["valor_hora"]),
        "valor_hora_fmt": brl(D(faixa_final["valor_hora"])),
        "valor_mensal": num(mensal_final), "valor_mensal_fmt": brl(mensal_final),
        "contrato_meses": conv["contrato_meses"],
        "valor_12m": num(mensal_final * conv["contrato_meses"]),
        "valor_12m_fmt": brl(mensal_final * conv["contrato_meses"]),
        "calculo": {
            "valor_referencia": num(valor_implantacao),
            "valor_referencia_fmt": brl(D(valor_implantacao)),
            "multiplicador_anual": conv["multiplicador_anual"],
            "receita_anual_alvo": num(anual), "receita_anual_alvo_fmt": brl(anual),
            "mensal_alvo": num(mensal_alvo), "mensal_alvo_fmt": brl(mensal_alvo),
            "faixas_avaliadas": avaliadas,
            "faixas_que_fecham": [f["id"] for f, _ in fecham],
            "criterio_desempate": conv["desempate"] if desempate else None,
            "h_bruto": float(h_bruto.quantize(D("0.0001"), rounding=ROUND_HALF_UP)),
            "arredondamento": conv["arredondamento"],
            "h_final": h_final,
            "ajuste_de_borda": ajuste,
            "desvio_vs_alvo_pct": float(desvio.quantize(D("0.01"), rounding=ROUND_HALF_UP)),
        },
        "alertas": alertas,
    }


# -----------------------------------------------------------------------------
# A) Implantação
# -----------------------------------------------------------------------------
def horas_do_item(dados: Dados, item: dict, sel: dict, design_do_cliente: bool) -> tuple:
    """Devolve (horas_unit_min, horas_unit_max, horas_unit, detalhe, alerta)."""
    imp = dados.precos["implantacao"]
    politica = imp["politica_faixa_horas"]

    # Uma pessoa disse que este item, nesta proposta, está incluso. Vale para o
    # cliente que negociou assim; a lista global de `precos.toml` continua sendo
    # o padrão de todo mundo.
    if sel.get("incluso_no_padrao"):
        return 0, 0, 0, {"regra": "incluso_por_decisao"}, "ITEM_INCLUSO_POR_DECISAO"

    if item.get("no_escopo_padrao"):
        return 0, 0, 0, {"regra": "escopo_padrao"}, "ITEM_JA_INCLUSO"

    # Horas fixadas à mão vencem a faixa do catálogo. É como "cote o
    # personalizador em 16 horas" e "esse módulo vale 6 mil" chegam ao cálculo:
    # o segundo vira o primeiro por uma divisão feita em Python, nunca por um
    # agente escrevendo valor.
    if sel.get("horas") is not None:
        try:
            h = int(sel["horas"])
        except (TypeError, ValueError):
            raise SystemExit(
                f"erro: item '{sel.get('catalogo_id')}' com `horas` não inteiro: {sel['horas']!r}"
            ) from None
        if h < 0:
            raise SystemExit(f"erro: item '{sel.get('catalogo_id')}' com `horas` negativo")
        return h, h, h, {"regra": "horas_fixadas", "complexidade": sel.get("complexidade")}, \
            "HORAS_FIXADAS_MANUALMENTE"

    if item.get("regra_especial") == "landing_page":
        lp = imp["landing_page"]
        # As 4h de design só entram quando o protótipo é da N1. Se a seleção não
        # disser, herda do dado comercial do cliente.
        n1_faz_design = sel.get("design_pela_n1", not design_do_cliente)
        hd = lp["horas_design"] if n1_faz_design else 0
        h = hd + lp["horas_dev"]
        return h, h, h, {
            "regra": "landing_page", "design_pela_n1": n1_faz_design,
            "horas_design_unit": hd, "horas_dev_unit": lp["horas_dev"],
        }, None

    cx = sel.get("complexidade")
    if cx not in ("baixa", "media", "alta"):
        raise SystemExit(
            f"erro: item '{sel['catalogo_id']}' exige complexidade baixa|media|alta "
            f"(recebido: {cx!r})"
        )
    faixa = item.get(f"horas_{cx}")
    if not faixa:
        raise SystemExit(f"erro: catálogo sem faixa 'horas_{cx}' para '{item['id']}'")
    mn, mx = int(faixa[0]), int(faixa[1])
    h = {"maximo": mx, "minimo": mn, "media": (mn + mx) // 2}[politica]
    return mn, mx, h, {"regra": "catalogo", "complexidade": cx, "politica_faixa": politica}, None


# Degrau do rateio. Preço de módulo com centavo — "R$ 3.260,75" — parece erro de
# planilha, não proposta comercial: quem lê desconfia do número antes de olhar o
# escopo. Em degraus de dez, toda linha termina em zero.
PASSO_RATEIO = D(10)


def ratear(partes: list, alvo: "D", passo: "D" = PASSO_RATEIO, absorve: int = -1) -> list:
    """Distribui `alvo` entre `partes`, na proporção de cada uma, fechando exato.

    Quando o valor é fechado na negociação, as linhas calculadas não somam o
    total: a Viveo calcula 22.000 e foi fechada em 36.000. Mostrar as linhas
    originais ao lado do total fechado imprime uma tabela que não soma, e uma
    tabela que não soma é pior do que não ter tabela.

    A conta é feita em **degraus de `passo` reais**, não em centavos. Ratear no
    centavo fecha a soma mas produz "R$ 3.260,75" por módulo — número que não se
    escreve numa proposta. Rateando em dezenas, cada linha termina em zero.

    Arredondar cada parte isoladamente não fecharia a coluna, então o resto vai
    por **maior resto**: cada parte fica com os degraus truncados e os que
    sobrarem são entregues, um a um, a quem perdeu a maior fração. O que não
    couber num degrau inteiro — se o total negociado não for múltiplo do passo —
    vai todo para a linha `absorve`, que por padrão é a última: o valor base.
    É a única que pode carregar um número quebrado sem parecer erro, porque
    ninguém a compara com uma tabela de preços.
    """
    soma = sum(partes)
    if soma <= 0:
        return [D(0) for _ in partes]

    degraus_alvo = int((alvo / passo).to_integral_value(rounding=ROUND_DOWN))
    resto = alvo - D(degraus_alvo) * passo

    exatos = [(pt * degraus_alvo / soma) for pt in partes]
    piso = [int(e) for e in exatos]

    # Módulo que zeraria no arredondamento fica com um degrau: linha de R$ 0,00
    # numa proposta é pior do que a imprecisão de dez reais que ela evita.
    for i, pt in enumerate(partes):
        if pt > 0 and piso[i] == 0 and sum(piso) < degraus_alvo:
            piso[i] = 1

    falta = degraus_alvo - sum(piso)
    ordem = sorted(range(len(exatos)), key=lambda i: exatos[i] - piso[i], reverse=True)
    for k in range(max(falta, 0)):
        piso[ordem[k % len(piso)]] += 1
    for k in range(max(-falta, 0)):                 # passou: devolve de quem tem mais
        maiores = sorted(range(len(piso)), key=lambda i: piso[i], reverse=True)
        for i in maiores:
            if piso[i] > 1:
                piso[i] -= 1
                break

    valores = [D(d) * passo for d in piso]
    if resto:
        valores[absorve] += resto
    return valores


# Plural das unidades do catálogo. Dez palavras, escritas à mão: gerar plural em
# português por regra dá "seçãos" e "integraçãos", e o rótulo vai para o cliente.
PLURAIS = {
    "página": "páginas", "template": "templates", "conjunto": "conjuntos",
    "componente": "componentes", "fluxo": "fluxos", "projeto": "projetos",
    "hotsite": "hotsites", "seção": "seções", "funcionalidade": "funcionalidades",
    "integração": "integrações",
}


def rotulo_da_linha(item: dict, sel: dict) -> str:
    """O que o cliente lê como nome da linha.

    O `nome` do catálogo é fixo por `catalogo_id`, então uma proposta que cota
    cinco páginas institucionais diferentes imprime cinco linhas idênticas com
    preços diferentes — e quem lê não sabe qual é qual. `rotulo` é o nome desta
    venda; o `nome` do catálogo é só o fallback.

    A contagem é acrescentada aqui, não pelo agente: quantas páginas são é um
    número, e número quem escreve é o script.
    """
    base = (sel.get("rotulo") or "").strip() or item["nome"]
    qtd = int(sel.get("quantidade", 1))
    if qtd > 1:
        unidade = (item.get("unidade") or "").strip()
        plural = PLURAIS.get(unidade, f"{unidade}s" if unidade else "")
        if plural:
            base = f"{base} — {qtd} {plural}"
    return base


def precificar_implantacao(dados: Dados, escopo: dict, valor_fechado=None,
                           motivo_fechado: str = "") -> dict:
    """Precifica a implantação.

    `valor_fechado` é a negociação comercial entrando no cálculo pela porta da
    frente. A regra do repositório continua valendo — nenhum agente escreve
    valor —, mas uma pessoa pode fechar o preço, e quando fecha isso precisa
    ficar registrado ao lado do valor calculado, não substituí-lo em silêncio.
    """
    imp = dados.precos["implantacao"]
    slug = escopo["plataforma"]
    if slug not in imp["plataformas"]:
        raise SystemExit(f"erro: plataforma desconhecida: {slug}")
    plat = imp["plataformas"][slug]
    hora = D(imp["valor_hora_adicional"])
    design_do_cliente = bool(escopo.get("design_fornecido_pelo_cliente"))

    linhas, fora, alertas = [], [], []
    h_min = h_max = h_tot = 0
    adicionais = D(0)

    for ordem, sel in enumerate(escopo.get("itens", []), 1):
        cid = sel["catalogo_id"]
        item = dados.catalogo.get(cid)
        if item is None:
            # Erro fatal por decisão de projeto: nunca há fallback silencioso.
            raise SystemExit(
                f"erro: '{cid}' não existe em catalogo-modulos.toml. "
                f"Use `itens_fora_catalogo` ou rode /proposta-catalogo para incorporá-lo."
            )
        qtd = int(sel.get("quantidade", 1))
        mn, mx, hu, det, alerta = horas_do_item(dados, item, sel, design_do_cliente)
        horas = hu * qtd
        valor = D(horas) * hora
        if alerta == "HORAS_FIXADAS_MANUALMENTE":
            alertas.append({
                "codigo": alerta, "severidade": "alta", "item": cid,
                "mensagem": (
                    f"'{item['nome']}' está com {hu}h fixadas à mão, no lugar da faixa "
                    f"do catálogo. Confira antes de aprovar: o valor da linha sai daí."
                ),
            })
        elif alerta == "ITEM_INCLUSO_POR_DECISAO":
            alertas.append({
                "codigo": alerta, "severidade": "alta", "item": cid,
                "mensagem": (
                    f"'{item['nome']}' foi marcado como incluso nesta proposta e está "
                    f"cotado a zero. Não é o padrão da casa — vale só para este cliente."
                ),
            })
        elif alerta:
            alertas.append({"codigo": alerta, "severidade": "media", "item": cid,
                            "mensagem": f"'{item['nome']}' já faz parte do escopo padrão; cotado a zero."})
        linhas.append({
            "ordem": ordem, "catalogo_id": cid, "nome": item["nome"],
            "rotulo": (sel.get("rotulo") or "").strip(),
            "rotulo_exibido": rotulo_da_linha(item, sel),
            "categoria": item.get("categoria"), "unidade": item.get("unidade"),
            "quantidade": qtd, "exige_app": bool(item.get("exige_app")),
            **det,
            "horas_min_total": mn * qtd, "horas_max_total": mx * qtd, "horas_total": horas,
            "horas_total_fmt": f"{horas}h",
            "valor": num(valor), "valor_fmt": brl(valor),
            "origem": sel.get("origem", []), "no_catalogo": True,
            "observacao": sel.get("observacao", ""),
            "descricao_proposta": item.get("descricao_proposta", ""),
        })
        h_min += mn * qtd; h_max += mx * qtd; h_tot += horas
        adicionais += valor

    for sel in escopo.get("itens_fora_catalogo", []):
        horas = int(sel["horas_estimadas"])
        valor = D(horas) * hora
        fora.append({
            "nome": sel["nome"], "horas_total": horas, "horas_total_fmt": f"{horas}h",
            "valor": num(valor), "valor_fmt": brl(valor),
            "justificativa": sel.get("justificativa", ""), "origem": sel.get("origem", []),
            "no_catalogo": False,
        })
        h_min += horas; h_max += horas; h_tot += horas
        adicionais += valor
    if fora:
        alertas.append({
            "codigo": "ITEM_NAO_CATALOGADO", "severidade": "alta",
            "mensagem": f"{len(fora)} item(ns) cotado(s) fora do catálogo; "
                        f"rode /proposta-catalogo para incorporá-lo(s).",
        })

    base = D(plat["valor_base"])

    # "Cotamos todas as páginas separadamente, remove o valor base." O base vem
    # da plataforma em `precos.toml` e vale para o caso normal; quando o escopo
    # inteiro foi cotado item a item, cobrá-lo de novo é cobrar duas vezes.
    if escopo.get("valor_base_override") is not None:
        anterior = base
        base = D(str(escopo["valor_base_override"]))
        if base < 0:
            raise SystemExit("erro: `valor_base_override` não pode ser negativo")
        alertas.append({
            "codigo": "VALOR_BASE_ALTERADO", "severidade": "alta",
            "mensagem": (
                f"O valor base da plataforma ({brl(anterior)}) foi substituído por "
                f"{brl(base)} por decisão comercial."
            ),
        })
    embutido = D(plat["design_embutido"])
    abatimento = embutido if design_do_cliente else D(0)
    total = base + adicionais - abatimento
    base_exibida = base
    for l in linhas + fora:
        l["valor_exibido"] = l["valor"]
        l["valor_exibido_fmt"] = l["valor_fmt"]

    # Fechamento comercial: uma pessoa decidiu o preço final. O valor calculado
    # não é apagado — fica ao lado, para que a diferença seja sempre visível.
    fechamento = None
    if valor_fechado is not None:
        calculado = total
        total = D(str(valor_fechado))
        diferenca = total - calculado
        fechamento = {
            "valor_calculado": num(calculado), "valor_calculado_fmt": brl(calculado),
            "valor_fechado": num(total), "valor_fechado_fmt": brl(total),
            "diferenca": num(diferenca), "diferenca_fmt": brl(abs(diferenca)),
            "sentido": "desconto" if diferenca < 0 else ("acréscimo" if diferenca > 0 else "igual"),
            "motivo": motivo_fechado or "",
        }
        alertas.append({
            "codigo": "VALOR_FECHADO_MANUALMENTE",
            "severidade": "alta",
            "mensagem": (
                f"O valor final foi fechado em {brl(total)} por decisão comercial. "
                f"O cálculo do escopo dava {brl(calculado)} "
                f"({fechamento['sentido']} de {brl(abs(diferenca))})."
                + (f" Motivo: {motivo_fechado}" if motivo_fechado else "")
            ),
        })

        # As linhas passam a exibir a parte que lhes cabe do valor fechado. O
        # `valor_fmt` calculado continua no JSON como verdade interna — é o que
        # a memória de cálculo e a auditoria usam —, mas não é o que vai ao PDF.
        # O alvo é `total + abatimento`, não `total`: a etapa de design entra na
        # tabela como linha própria e subtrai depois. Ratear direto no total
        # faria a coluna fechar abaixo do valor negociado, pelo abatimento.
        #
        # E os itens fora do catálogo entram no rateio junto: deixá-los de fora
        # os manteria no valor calculado enquanto o resto se move, e a soma da
        # coluna erraria por exatamente o valor deles.
        cotadas = linhas + fora
        partes = [D(str(l["valor"])) for l in cotadas] + [base]
        rateado = ratear(partes, total + abatimento)
        for l, v in zip(cotadas, rateado):
            l["valor_exibido"] = num(v)
            l["valor_exibido_fmt"] = brl(v)
        base_exibida = rateado[-1]

    # Prazo derivado das horas — ver o aviso REVISAR em condicoes-comerciais.toml
    pz = dados.condicoes["implantacao"]["prazo"]
    semanas = max(pz["semanas_minimas"],
                  math.ceil((pz["horas_base_equivalentes"] + h_tot) / pz["horas_por_semana"]))
    semanas_max = semanas + pz["folga_semanas"]
    prazo_origem = "derivado das horas do escopo"

    # Override de prazo: existe porque o prazo às vezes é COMPROMISSO ASSUMIDO na
    # reunião, e uma proposta que contradiz o que foi dito ao vivo custa caro. Só
    # vale quando declarado com evidência no 02-escopo.json — e sempre emite
    # alerta, para nunca passar em silêncio pelo checkpoint humano.
    ov = escopo.get("prazo_semanas")
    if ov:
        if not ov.get("origem"):
            raise SystemExit("erro: `prazo_semanas` exige `origem` com a evidência [E##] "
                             "que sustenta o prazo prometido.")
        semanas, semanas_max = int(ov["min"]), int(ov["max"])
        if semanas > semanas_max:
            raise SystemExit(f"erro: `prazo_semanas` com min > max: {semanas} > {semanas_max}")
        prazo_origem = "declarado no escopo — " + (ov.get("justificativa") or "sem justificativa")
        derivado = max(pz["semanas_minimas"],
                       math.ceil((pz["horas_base_equivalentes"] + h_tot) / pz["horas_por_semana"]))
        alertas.append({
            "codigo": "PRAZO_DEFINIDO_MANUALMENTE", "severidade": "alta",
            "mensagem": f"Prazo fixado em {semanas} a {semanas_max} semanas por "
                        f"{', '.join(ov['origem'])}; a fórmula derivaria "
                        f"{derivado} a {derivado + pz['folga_semanas']} semanas para "
                        f"{h_tot}h de adicionais. Confirme a capacidade antes de assinar.",
        })

    pag = dados.condicoes["implantacao"]["pagamento"]

    return {
        "aplicavel": True,
        "plataforma": slug, "plataforma_nome": plat["nome"],
        "valor_base": num(base), "valor_base_fmt": brl(base),
        # O que a tabela do PDF mostra na linha do valor base. Igual ao
        # calculado, exceto quando houve fechamento comercial.
        "valor_base_exibido": num(base_exibida), "valor_base_exibido_fmt": brl(base_exibida),
        "escopo_padrao_incluso": [dados.catalogo[i]["nome"] for i in imp["escopo_padrao"]
                                  if i in dados.catalogo],
        "valor_hora": num(hora), "valor_hora_fmt": brl(hora),
        "design": {
            "parcela_embutida": num(embutido), "parcela_embutida_fmt": brl(embutido),
            "fornecido_pelo_cliente": design_do_cliente,
            "abatimento": num(abatimento), "abatimento_fmt": brl(abatimento),
        },
        "linhas": linhas,
        "linhas_fora_catalogo": fora,
        "subtotais": {
            "base": num(base), "base_fmt": brl(base),
            "horas_adicionais": h_tot,
            "horas_adicionais_min": h_min, "horas_adicionais_max": h_max,
            "horas_adicionais_fmt": f"{h_tot}h",
            "adicionais": num(adicionais), "adicionais_fmt": brl(adicionais),
            "abatimento_design": num(abatimento), "abatimento_design_fmt": brl(abatimento),
        },
        "total": num(total), "total_fmt": brl(total),
        "fechamento_comercial": fechamento,
        "condicoes": {
            "parcelamento": pag["texto"],
            "entrada_pct": pag["entrada_pct"],
            "entrada_valor": num(total * D(pag["entrada_pct"]) / D(100)),
            "entrada_valor_fmt": brl(total * D(pag["entrada_pct"]) / D(100)),
            "parcelas_restante": pag["parcelas_restante"],
            "parcela_valor": num(total * D(100 - pag["entrada_pct"]) / D(100) / D(pag["parcelas_restante"])),
            "parcela_valor_fmt": brl(total * D(100 - pag["entrada_pct"]) / D(100) / D(pag["parcelas_restante"])),
            "prazo_semanas_min": semanas,
            "prazo_semanas_max": semanas_max,
            "prazo_fmt": f"{semanas} a {semanas_max} semanas",
            "prazo_origem": prazo_origem,
            "garantia": dados.condicoes["implantacao"]["garantia"]["texto"],
        },
        "alertas": alertas,
    }


# -----------------------------------------------------------------------------
# Ficha do cliente (entrada/dados-cliente.md) — leitura tolerante
# -----------------------------------------------------------------------------
def _slug_chave(texto: str) -> str:
    import unicodedata
    sem_acento = "".join(c for c in unicodedata.normalize("NFKD", texto)
                         if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", "_", sem_acento.lower()).strip("_")


def ler_ficha(caminho: Path) -> dict:
    """
    Lê os pares `- **Rótulo:** valor` do markdown. Campo ausente vira "".
    O negrito é removido ANTES de procurar o `:` — em `- **Cliente:** Fulano`
    os dois-pontos ficam dentro dos asteriscos, e casar o padrão bruto devolvia
    valores como `"** Fulano"`.
    """
    if not caminho or not Path(caminho).is_file():
        return {}
    campos = {}
    for linha in Path(caminho).read_text(encoding="utf-8").splitlines():
        if not re.match(r"\s*[-*+]\s", linha):
            continue
        limpa = re.sub(r"\*\*|__|`", "", linha).strip().lstrip("-*+ ").strip()
        rotulo, sep, valor = limpa.partition(":")
        if not sep:
            continue
        valor = valor.strip()
        # `<preencher>` e `( ) opção` são placeholders do modelo, não resposta.
        # Cuidado: um telefone começa com "(" — o descarte é só do checkbox vazio.
        placeholder = valor.startswith("<") or re.match(r"^\(\s*\)", valor)
        if valor and not placeholder:
            campos[_slug_chave(rotulo)] = valor
    return campos


# -----------------------------------------------------------------------------
# Orçamento completo
# -----------------------------------------------------------------------------
def ler_valor(texto: str) -> Decimal:
    """Interpreta um valor monetário escrito por gente ou por máquina.

    O ponto é ambíguo entre as duas convenções: em `36.000,00` ele separa
    milhar, em `36000.0` ele separa decimal. Tratar todo ponto como milhar
    transformava o `36000.0` que o app envia em **360000** — dez vezes o preço
    combinado. A vírgula é o desempate: onde ela existe, ela é o decimal.
    """
    bruto = str(texto).replace("R$", "").replace(" ", "").replace("\u00a0", "").strip()
    if not bruto:
        raise ValueError("valor vazio")

    if "," in bruto:                       # pt-BR: ponto é milhar, vírgula é decimal
        bruto = bruto.replace(".", "").replace(",", ".")
    elif bruto.count(".") > 1:             # 1.234.567 — só pode ser milhar
        bruto = bruto.replace(".", "")
    elif "." in bruto:
        inteiro, _, frac = bruto.partition(".")
        if len(frac) == 3 and inteiro:     # 36.000 — milhar à brasileira
            bruto = inteiro + frac
        # senão (36000.0, 36000.75) o ponto é decimal e fica como está

    try:
        return D(bruto)
    except Exception:
        raise ValueError(f"não entendi o valor: {texto}") from None


def montar_orcamento(dados: Dados, escopo: dict, ficha: dict, hoje: date,
                     valor_fechado=None, motivo_fechado: str = "") -> dict:
    modelo = escopo.get("modelo_principal", "implantacao")
    validade = hoje + timedelta(days=dados.condicoes["meta"]["validade_dias_padrao"])
    if ficha.get("validade"):
        try:
            d, m, a = ficha["validade"].split("/")
            validade = date(int(a), int(m), int(d))
        except Exception:
            pass

    orc = {
        "schema_versao": "1.0",
        "gerado_em": hoje.isoformat(),
        "gerado_por": f"scripts/precificar.py {VERSAO}",
        "precos_versao": dados.precos["meta"]["versao"],
        "hash_entrada": dados.hash(),
        "cliente": {
            "nome": ficha.get("cliente") or ficha.get("nome_de_tratamento") or escopo.get("cliente", "Cliente"),
            "razao_social": ficha.get("razao_social", ""),
            "contato_nome": ficha.get("contato", ""),
            "contato_email": ficha.get("e_mail", ""),
            "contato_whatsapp": ficha.get("whatsapp", ""),
        },
        "proposta": {
            "modelo_principal": modelo,
            "natureza": escopo.get("natureza", "novo"),
            "validade": validade.isoformat(),
            "validade_fmt": validade.strftime("%d/%m/%Y"),
            "validade_extenso": data_extenso(validade),
        },
        "alertas": [],
        "lacunas": escopo.get("lacunas", []),
        "rastreabilidade": [],
    }

    if modelo == "implantacao":
        imp = precificar_implantacao(dados, escopo, valor_fechado, motivo_fechado)
        orc["implantacao"] = imp
        orc["alertas"] += imp.pop("alertas")
        # Regra C: a alternativa em fee mensal acompanha toda implantação.
        ev = converter(dados, D(str(imp["total"])))
        ev["fidelidade_meses"] = dados.condicoes["evolucao"]["fidelidade_meses_conversao"]
        orc["evolucao"] = ev
        orc["alertas"] += [{"codigo": c, "severidade": "media", "mensagem": c} for c in ev.pop("alertas")]
        orc["rastreabilidade"] = [
            {"campo": "implantacao.valor_base",
             "origem": f"dados/precos.toml §implantacao.plataformas.{imp['plataforma']}.valor_base"},
            {"campo": "implantacao.subtotais.adicionais",
             "origem": "dados/catalogo-modulos.toml × precos.toml §implantacao.valor_hora_adicional"},
            {"campo": "evolucao.valor_mensal",
             "origem": "dados/precos.toml §conversao + §evolucao.faixas"},
        ]
        if escopo.get("prazo_semanas"):
            ov = escopo["prazo_semanas"]
            orc["rastreabilidade"].append({
                "campo": "implantacao.condicoes.prazo_fmt",
                "origem": f"proposta/02-escopo.json §prazo_semanas ← {', '.join(ov['origem'])}",
            })
    else:
        rec = escopo.get("evolucao_solicitada", {}).get("horas_mes")
        if not rec:
            raise SystemExit("erro: proposta de evolução exige `evolucao_solicitada.horas_mes` "
                             "no 02-escopo.json (o pacote recomendado).")
        pacotes = opcoes_pacote(dados, int(rec))
        principal = next(o for o in pacotes["opcoes"] if o["recomendado"])
        cond = dados.condicoes["evolucao"]
        orc["implantacao"] = {"aplicavel": False}
        orc["evolucao"] = {
            "aplicavel": True, "origem": "contratada",
            **{k: v for k, v in principal.items() if k != "recomendado"},
            "pacote_horas": principal["horas"],
            "pacote_horas_fmt": f"{principal['horas']} horas",
            "opcoes": pacotes["opcoes"],
            "horas_recomendadas_calculadas": pacotes["horas_recomendadas_calculadas"],
            "hora_excedente": num(cond["hora_excedente"]),
            "hora_excedente_fmt": brl(D(cond["hora_excedente"])),
            "acumulo_saldo_pct": cond["acumulo_saldo_pct"],
            "fidelidade_meses": cond["fidelidade_meses_padrao"],
            "faturamento": cond["faturamento"],
        }
        orc["rastreabilidade"] = [
            {"campo": "evolucao.valor_hora", "origem": "dados/precos.toml §evolucao.faixas"},
            {"campo": "evolucao.opcoes", "origem": "dados/precos.toml §evolucao.pacotes_sugeridos"},
        ]

    if orc["evolucao"].get("aplicavel"):
        cond = dados.condicoes["evolucao"]
        orc["evolucao"]["tabela_faixas"] = tabela_faixas(dados)
        if orc["evolucao"].get("faixa_rotulo"):
            orc["evolucao"]["faixa_rotulo_fmt"] = orc["evolucao"]["faixa_rotulo"]
        orc["evolucao"].setdefault("hora_excedente", num(cond["hora_excedente"]))
        orc["evolucao"].setdefault("hora_excedente_fmt", brl(D(cond["hora_excedente"])))
        orc["evolucao"].setdefault("acumulo_saldo_pct", cond["acumulo_saldo_pct"])
        orc["evolucao"].setdefault("faturamento", cond["faturamento"])

    orc["totais"] = {
        "moeda": "BRL",
        "implantacao_total": orc["implantacao"].get("total"),
        "implantacao_total_fmt": orc["implantacao"].get("total_fmt"),
        "evolucao_mensal": orc["evolucao"].get("valor_mensal"),
        "evolucao_mensal_fmt": orc["evolucao"].get("valor_mensal_fmt"),
    }
    return orc


# -----------------------------------------------------------------------------
# Memória de cálculo em markdown — para o humano ler no checkpoint
# -----------------------------------------------------------------------------
def orcamento_md(orc: dict) -> str:
    L = [f"# Orçamento — {orc['cliente']['nome']}", "",
         f"- Gerado em: {orc['gerado_em']} por `{orc['gerado_por']}`",
         f"- Tabela de preços: `{orc['precos_versao']}` · hash das entradas: `{orc['hash_entrada']}`",
         f"- Modelo: **{orc['proposta']['modelo_principal']}** · natureza: {orc['proposta']['natureza']}",
         f"- Validade: {orc['proposta']['validade_fmt']}", ""]

    imp = orc.get("implantacao", {})
    if imp.get("aplicavel"):
        L += [f"## Implantação — {imp['plataforma_nome']}", "",
              "| Item | Complexidade | Qtd | Horas | Valor | Origem |",
              "|---|---|---:|---:|---:|---|",
              f"| **Valor base** (escopo padrão) | — | 1 | — | {imp['valor_base_fmt']} | precos.toml |"]
        for l in imp["linhas"] + imp["linhas_fora_catalogo"]:
            cx = l.get("complexidade") or l.get("regra", "—")
            org = ", ".join(l.get("origem", [])) or "—"
            marca = "" if l.get("no_catalogo", True) else " ⚠️ fora do catálogo"
            L.append(f"| {l['nome']}{marca} | {cx} | {l.get('quantidade', 1)} | "
                     f"{l['horas_total']}h | {l['valor_fmt']} | {org} |")
        if imp["design"]["fornecido_pelo_cliente"]:
            L.append(f"| **Abatimento de design** (layout do cliente) | — | — | — | "
                     f"−{imp['design']['abatimento_fmt']} | precos.toml |")
        s = imp["subtotais"]
        fc = imp.get("fechamento_comercial")
        if fc:
            L += ["", f"> **Valor fechado por decisão comercial: {fc['valor_fechado_fmt']}**",
                  f"> O cálculo do escopo dava {fc['valor_calculado_fmt']} — "
                  f"{fc['sentido']} de {fc['diferenca_fmt']}."
                  + (f" Motivo: {fc['motivo']}" if fc["motivo"] else ""), ""]
        L += ["", f"**Memória:** base {imp['valor_base_fmt']} + adicionais "
                  f"{s['horas_adicionais']}h × {imp['valor_hora_fmt']} = {s['adicionais_fmt']}"
                  + (f" − design {imp['design']['abatimento_fmt']}"
                     if imp["design"]["fornecido_pelo_cliente"] else "")
                  + f" = **{imp['total_fmt']}**", "",
              f"- Pagamento: {imp['condicoes']['parcelamento']} "
              f"({imp['condicoes']['entrada_valor_fmt']} + {imp['condicoes']['parcelas_restante']}× "
              f"{imp['condicoes']['parcela_valor_fmt']})",
              f"- Prazo estimado: {imp['condicoes']['prazo_fmt']} "
              f"({imp['condicoes'].get('prazo_origem', 'derivado das horas do escopo')})", ""]

    ev = orc.get("evolucao", {})
    if ev.get("aplicavel"):
        titulo = ("Alternativa em evolução (fee mensal)" if ev.get("origem") == "alternativa_convertida"
                  else "Evolução — pacote mensal")
        L += [f"## {titulo}", ""]
        if ev.get("origem") == "alternativa_convertida":
            c = ev["calculo"]
            L += [f"- Referência: {c['valor_referencia_fmt']} × {c['multiplicador_anual']} = "
                  f"{c['receita_anual_alvo_fmt']}/ano → {c['mensal_alvo_fmt']}/mês",
                  "", "| Faixa | R$/h | h = mensal/hora | fecha? |", "|---|---:|---:|:--:|"]
            for f in c["faixas_avaliadas"]:
                L.append(f"| {f['faixa_id']} | {f['valor_hora']} | {f['h']:.2f} | "
                         f"{'sim' if f['dentro_da_faixa'] else 'não'} |")
            extra = []
            if c["criterio_desempate"]:
                extra.append(f"desempate por *{c['criterio_desempate']}*")
            if c["ajuste_de_borda"]:
                extra.append(f"ajuste de borda: *{c['ajuste_de_borda']}*")
            L += ["", f"- h bruto {c['h_bruto']} → arredondado ({c['arredondamento']}) para "
                      f"**{c['h_final']}h** · desvio {c['desvio_vs_alvo_pct']:+.2f}%"
                      + (f" · {'; '.join(extra)}" if extra else "")]
        if ev.get("opcoes"):
            L += ["", "| Pacote | R$/h | Mensal | |", "|---:|---:|---:|---|"]
            for o in ev["opcoes"]:
                L.append(f"| {o['horas']}h | {o['valor_hora_fmt']} | {o['valor_mensal_fmt']} | "
                         f"{'**recomendado**' if o['recomendado'] else ''} |")
        L += ["", f"**{ev['pacote_horas_fmt']} × {ev['valor_hora_fmt']} = "
                  f"{ev['valor_mensal_fmt']}/mês** ({ev.get('faixa_rotulo', '')})",
              f"- Hora excedente: {ev.get('hora_excedente_fmt', '—')} · "
              f"saldo acumulável: {ev.get('acumulo_saldo_pct', '—')}% · "
              f"fidelidade: {ev.get('fidelidade_meses', '—')} meses", ""]

    if orc["alertas"]:
        L += ["## Alertas", ""] + [f"- **{a['codigo']}** — {a['mensagem']}" for a in orc["alertas"]] + [""]
    if orc["lacunas"]:
        L += ["## Lacunas", ""] + [f"- {x}" for x in orc["lacunas"]] + [""]
    L += ["## Rastreabilidade", ""] + [f"- `{r['campo']}` ← {r['origem']}" for r in orc["rastreabilidade"]]
    return "\n".join(L) + "\n"


# -----------------------------------------------------------------------------
# CLI
# -----------------------------------------------------------------------------
def main() -> int:
    ap = argparse.ArgumentParser(description="Calcula o orçamento da proposta.")
    ap.add_argument("--escopo", type=Path)
    ap.add_argument("--dados-cliente", type=Path)
    ap.add_argument("--saida", type=Path, default=Path("proposta/03-orcamento.json"))
    ap.add_argument("--hoje", help="AAAA-MM-DD; útil para reprodutibilidade")
    ap.add_argument("--simular", action="store_true")
    ap.add_argument("--plataforma"); ap.add_argument("--horas-adicionais", type=int, default=0)
    ap.add_argument("--layout-do-cliente", action="store_true")
    ap.add_argument("--converter", type=str, help="valor de implantação a converter em fee mensal")
    ap.add_argument("--pacote", type=int, help="horas/mês recomendadas -> 3 opções")
    ap.add_argument(
        "--valor-fechado", type=str,
        help="fecha o total de implantação neste valor, por decisão comercial. "
             "O cálculo do escopo é preservado ao lado e um alerta de severidade "
             "alta registra a diferença.",
    )
    ap.add_argument("--motivo-fechado", type=str, default="",
                    help="por que o valor foi fechado; entra no alerta e na memória")
    args = ap.parse_args()

    dados = Dados()
    hoje = date.fromisoformat(args.hoje) if args.hoje else date.today()

    if args.simular:
        if args.converter:
            print(json.dumps(converter(dados, D(args.converter)), ensure_ascii=False, indent=2))
        elif args.pacote:
            print(json.dumps(opcoes_pacote(dados, args.pacote), ensure_ascii=False, indent=2))
        elif args.plataforma:
            escopo = {"modelo_principal": "implantacao", "plataforma": args.plataforma,
                      "design_fornecido_pelo_cliente": args.layout_do_cliente,
                      "itens": [],
                      "itens_fora_catalogo": ([{"nome": "Simulação de horas adicionais",
                                                "horas_estimadas": args.horas_adicionais}]
                                              if args.horas_adicionais else [])}
            print(orcamento_md(montar_orcamento(dados, escopo, {}, hoje)))
        else:
            ap.error("--simular precisa de --converter, --pacote ou --plataforma")
        return 0

    if not args.escopo or not args.escopo.is_file():
        ap.error("--escopo é obrigatório (proposta/02-escopo.json)")

    escopo = json.loads(args.escopo.read_text(encoding="utf-8"))
    ficha = ler_ficha(args.dados_cliente)
    fechado = None
    if args.valor_fechado:
        try:
            fechado = ler_valor(args.valor_fechado)
        except ValueError as e:
            raise SystemExit(f"erro: --valor-fechado inválido: {e}")
        if fechado <= 0:
            raise SystemExit("erro: --valor-fechado precisa ser positivo")

    orc = montar_orcamento(dados, escopo, ficha, hoje, fechado, args.motivo_fechado)

    args.saida.parent.mkdir(parents=True, exist_ok=True)
    args.saida.write_text(json.dumps(orc, ensure_ascii=False, indent=2), encoding="utf-8")
    md = args.saida.with_suffix(".md")
    md.write_text(orcamento_md(orc), encoding="utf-8")
    print(f"{args.saida}\n{md}")
    if orc["alertas"]:
        print("\nALERTAS:", file=sys.stderr)
        for a in orc["alertas"]:
            print(f"  [{a['severidade']}] {a['codigo']} — {a['mensagem']}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
