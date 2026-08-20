"""Edição direta do escopo, com reprecificação imediata.

O caminho por agente ("Pedir ajuste") relê a transcrição e o catálogo, e leva
minutos. Serve para "o megamenu já está incluso" — uma correção de
interpretação. Não serve para negociar: quando o comercial está com o cliente na
linha e precisa tirar um item, trocar a complexidade ou ver quanto fica sem
determinado módulo, esperar oito minutos por uma releitura da reunião não é
opção.

Aqui o escopo é editado à mão e o `precificar.py` roda em cima. Sem LLM, sem
fila, sem disputar as pastas de trabalho: responde em segundos.

A regra de ouro continua de pé — **quem calcula é o script**. O que muda é quem
escolhe os itens: nesta rota, uma pessoa, e a escolha fica registrada.
"""

from __future__ import annotations

import json
import tomllib
from datetime import datetime

import config as cfg
import db
import executor
import modelo
import scripts_runner
import workspace as ws
from api_propostas import carregar
from roteador import erro_400, erro_409, rota

COMPLEXIDADES = ("baixa", "media", "alta")


def _brl(v) -> str:
    return "R$ " + f"{float(v):,.2f}".replace(",", "§").replace(".", ",").replace("§", ".")


def catalogo() -> dict:
    with open(cfg.DADOS_REPO / "catalogo-modulos.toml", "rb") as f:
        return {i["id"]: i for i in tomllib.load(f)["itens"]}


@rota("GET", r"^/api/catalogo/itens$")
def listar_itens(req):
    """O catálogo inteiro, para a tela oferecer o que dá para acrescentar."""
    itens = []
    for i in catalogo().values():
        itens.append({
            "id": i["id"],
            "nome": i["nome"],
            "categoria": i.get("categoria"),
            "descricao": i.get("descricao_proposta"),
            "no_escopo_padrao": bool(i.get("no_escopo_padrao")),
            "regra_especial": i.get("regra_especial"),
            "horas": {c: i.get(f"horas_{c}") for c in COMPLEXIDADES},
            "criterio": i.get("criterio_complexidade"),
        })
    return {"itens": sorted(itens, key=lambda x: (x["categoria"] or "", x["nome"]))}


def _valor_fixo(bruto: dict, item: dict) -> dict:
    """Lê o campo Valor do editor. Vazio devolve a linha ao cálculo por horas.

    O mesmo interpretador do `precificar.py`: aceita `3500`, `3.500,00`,
    `R$ 3.500`. Uma segunda implementação de leitura de moeda já custou um
    "36.000,00" virar dez vezes o preço combinado.
    """
    bruta = bruto.get("valor_fixo")
    if bruta in (None, "", False):
        return {}

    import sys as _sys
    _sys.path.insert(0, str(cfg.SCRIPTS))
    from precificar import ler_valor

    try:
        valor = float(ler_valor(bruta))
    except (ValueError, TypeError):
        raise erro_400("valor_invalido",
                       f"não entendi o valor de '{item['nome']}': {bruta!r}") from None
    if valor < 0:
        raise erro_400("valor_invalido", f"o valor de '{item['nome']}' não pode ser negativo")
    return {"valor_fixo": valor}


def _validar_opcoes(opcoes: list, cat: dict, escopo: dict) -> list:
    """Só o preço de pacote é editável pela tela; o resto do formato é do agente."""
    atuais = {o.get("id"): o for o in (escopo.get("opcoes") or [])}
    saida = []
    for bruto in opcoes:
        oid = (bruto.get("id") or "").strip()
        base = dict(atuais.get(oid) or {})
        if not base:
            raise erro_400("opcao_desconhecida", f"não achei o formato '{oid}'")
        if "valor_fixo" in bruto:
            v = bruto.get("valor_fixo")
            if v in (None, ""):
                base.pop("valor_fixo", None)
            else:
                import sys as _sys
                _sys.path.insert(0, str(cfg.SCRIPTS))
                from precificar import ler_valor
                try:
                    base["valor_fixo"] = float(ler_valor(v))
                except (ValueError, TypeError):
                    raise erro_400("valor_invalido",
                                   f"não entendi o valor do formato '{base.get('nome')}'") from None
        saida.append(base)
    return saida


def _validar(itens: list, cat: dict) -> list:
    limpos = []
    for bruto in itens:
        cid = (bruto.get("catalogo_id") or "").strip()
        if cid not in cat:
            raise erro_400("item_desconhecido", f"'{cid}' não existe no catálogo")

        item = cat[cid]
        complexidade = (bruto.get("complexidade") or "").strip().lower() or None
        fixo = _valor_fixo(bruto, item)

        # Decisões manuais tomadas no ajuste. O editor precisa **carregá-las
        # adiante**: descartá-las fazia um clique em Recalcular apagar em
        # silêncio horas fixadas e itens marcados como inclusos — o comercial
        # mexia na quantidade de uma linha e perdia a decisão de outra.
        preservado = {}
        if bruto.get("horas") not in (None, ""):
            try:
                preservado["horas"] = int(bruto["horas"])
            except (TypeError, ValueError):
                raise erro_400("horas_invalidas",
                               f"horas inválidas em '{item['nome']}'") from None
        if bruto.get("incluso_no_padrao"):
            preservado["incluso_no_padrao"] = True

        # Complexidade só é exigida de quem depende da faixa do catálogo para
        # saber o esforço. Item com horas ou valor fixados não depende, e item
        # marcado como incluso custa zero — cobrar complexidade deles recusava
        # justamente as linhas que alguém já tinha resolvido à mão.
        dispensa = (item.get("no_escopo_padrao") or item.get("regra_especial")
                    or preservado.get("horas") is not None
                    or preservado.get("incluso_no_padrao")
                    or "valor_fixo" in fixo)
        if not dispensa:
            if complexidade not in COMPLEXIDADES:
                raise erro_400(
                    "complexidade_invalida",
                    f"'{item['nome']}' precisa de complexidade baixa, media ou alta",
                )
        elif item.get("no_escopo_padrao") or item.get("regra_especial"):
            complexidade = None

        try:
            qtd = int(bruto.get("quantidade") or 1)
        except (TypeError, ValueError):
            raise erro_400("quantidade_invalida", f"quantidade inválida em '{item['nome']}'") from None
        if qtd < 1:
            raise erro_400("quantidade_invalida", f"'{item['nome']}' precisa de quantidade ≥ 1")

        origem = bruto.get("origem") or []
        if isinstance(origem, str):
            origem = [origem]
        # `origem` não pode ficar vazia: é o que a auditoria exige e o que
        # permite saber de onde veio cada linha meses depois.
        if not origem:
            origem = ["ajuste manual no gate"]

        limpos.append({
            "catalogo_id": cid,
            "complexidade": complexidade,
            "quantidade": qtd,
            # O nome que o cliente lê. Sem ele, itens repetidos viram linhas
            # idênticas no PDF com preços diferentes.
            "rotulo": (bruto.get("rotulo") or "").strip(),
            **fixo,
            **preservado,
            "design_pela_n1": bool(bruto.get("design_pela_n1", True)),
            "origem": origem,
            "observacao": (bruto.get("observacao") or "").strip(),
        })
    return limpos


def _registrar_no_md(base, antes: list, depois: list, cat: dict, quem: str) -> None:
    """Anexa ao `02-escopo.md` o que foi mexido à mão.

    Os dois espelhos precisam contar a mesma história: `auditar.py escopo`
    reprova item que está no JSON e não aparece no `.md`, e uma edição sem
    rastro apagaria o porquê de um número mudar.
    """
    alvo = base / "proposta" / "02-escopo.md"
    if not alvo.is_file():
        return

    # A chave é (`catalogo_id`, `rotulo`), não só o id: uma proposta pode cotar
    # o mesmo tipo várias vezes — cinco páginas institucionais diferentes — e
    # indexar só pelo id colapsaria as cinco numa linha de rastro, escondendo
    # justamente o que a edição fez.
    def chavear(itens):
        m = {}
        for i in itens:
            cid = i.get("catalogo_id")
            if cid:
                m.setdefault((cid, (i.get("rotulo") or "").strip()), []).append(i)
        return m

    antes_k, depois_k = chavear(antes), chavear(depois)

    def descrever(i, cid):
        rot = (i.get("rotulo") or "").strip()
        nome = cat[cid]["nome"]
        return f"«{rot}»" if rot else nome

    linhas = []
    for chave, itens in depois_k.items():
        cid, _rot = chave
        antigos = antes_k.get(chave, [])
        for k, i in enumerate(itens):
            if k < len(antigos):
                a = antigos[k]
                # O JSON escrito pelo agente nem sempre traz todas as chaves —
                # item de regra especial costuma vir sem `complexidade`.
                ac, aq = a.get("complexidade"), a.get("quantidade", 1)
                if ac != i["complexidade"] or aq != i["quantidade"]:
                    linhas.append(
                        f"- **Alterado:** `{cid}` — {descrever(i, cid)}: "
                        f"{ac or '—'}/{aq}× → {i['complexidade'] or '—'}/{i['quantidade']}×"
                    )
            else:
                linhas.append(
                    f"- **Acrescentado:** `{cid}` — {descrever(i, cid)} "
                    f"(complexidade {i['complexidade'] or 'não se aplica'}, {i['quantidade']}×)"
                )

    # Rótulo mudado aparece como remoção + acréscimo pela chave composta; a
    # comparação por id recupera a intenção e escreve uma linha só.
    so_id_antes = {}
    so_id_depois = {}
    for (cid, rot), itens in antes_k.items():
        so_id_antes.setdefault(cid, []).extend([rot] * len(itens))
    for (cid, rot), itens in depois_k.items():
        so_id_depois.setdefault(cid, []).extend([rot] * len(itens))
    for cid, rots in so_id_depois.items():
        velhos = sorted(set(so_id_antes.get(cid, [])) - set(rots))
        novos = sorted(set(rots) - set(so_id_antes.get(cid, [])))
        if velhos and novos and len(velhos) == len(novos):
            nome = cat[cid]["nome"]
            for v, n in zip(velhos, novos):
                linhas.append(f"- **Rótulo:** `{cid}` — «{v or nome}» → «{n or nome}»")

    for chave, itens in antes_k.items():
        cid, _rot = chave
        sobra = len(itens) - len(depois_k.get(chave, []))
        # Só é remoção de verdade se o id sumiu ou encolheu no total.
        if sobra > 0 and len(so_id_depois.get(cid, [])) < len(so_id_antes.get(cid, [])):
            for _ in range(sobra):
                linhas.append(f"- **Removido:** `{cid}` — {cat[cid]['nome']}")

    if not linhas:
        return

    carimbo = datetime.now().strftime("%d/%m/%Y %H:%M")
    texto = alvo.read_text("utf-8").rstrip()
    texto += (
        f"\n\n## Edição manual do escopo — {carimbo}\n\n"
        f"Feita por {quem} na tela de aprovação, sem passar pelo agente. O total "
        f"foi recalculado por `scripts/precificar.py` sobre os itens abaixo.\n\n"
        + "\n".join(linhas) + "\n"
    )
    alvo.write_text(texto, "utf-8")


@rota("POST", r"^/api/propostas/(?P<pid>\d+)/escopo$")
def editar_escopo(req, pid):
    """Substitui os itens cotados e reprecifica na hora."""
    linha = carregar(pid)
    corpo = req.json_do_corpo()

    if linha["status"] in modelo.EXECUTANDO or linha["status"] == "enfileirada":
        raise erro_409("ja_na_fila", "esta proposta está executando; espere terminar")

    base = ws.caminho(linha["slug"])
    caminho_escopo = base / "proposta" / "02-escopo.json"
    if not caminho_escopo.is_file():
        raise erro_409("sem_escopo", "esta proposta ainda não tem escopo")

    escopo = json.loads(caminho_escopo.read_text("utf-8"))
    cat = catalogo()
    antes = list(escopo.get("itens") or [])
    depois = _validar(corpo.get("itens") or [], cat)

    escopo["itens"] = depois

    # Os formatos da proposta ficam onde estão. `_validar` monta o item do zero
    # a partir de uma lista fixa de campos, e foi assim que um clique em
    # Recalcular já apagou horas fixadas e itens inclusos — aqui apagaria as três
    # opções inteiras, com os preços de pacote negociados dentro.
    if "opcoes" in corpo:
        escopo["opcoes"] = _validar_opcoes(corpo.get("opcoes") or [], cat, escopo)

    # Cabeçalho do escopo: a plataforma decide o valor base, e o valor base pode
    # ser substituído. Num projeto pontual — uma correção, uma lista de tarefas —
    # não há plataforma sendo implantada e o valor base não deveria existir.
    if "plataforma" in corpo:
        nova = (corpo.get("plataforma") or "").strip()
        if nova and nova not in cfg.PLATAFORMAS:
            raise erro_400("plataforma_invalida",
                           f"'{nova}' não é uma das plataformas cotadas: "
                           f"{', '.join(cfg.PLATAFORMAS)}")
        if nova:
            escopo["plataforma"] = nova

    if "valor_base_override" in corpo:
        bruta = corpo.get("valor_base_override")
        if bruta in (None, ""):
            escopo.pop("valor_base_override", None)
        else:
            import sys as _sys
            _sys.path.insert(0, str(cfg.SCRIPTS))
            from precificar import ler_valor
            try:
                escopo["valor_base_override"] = float(ler_valor(bruta))
            except (ValueError, TypeError):
                raise erro_400("valor_invalido",
                               f"não entendi o valor base: {bruta!r}") from None

    # O pacote de acompanhamento. Vazio devolve a proposta ao padrão: o fee
    # mensal volta a ser a alternativa convertida do valor do projeto.
    if "evolucao_horas_mes" in corpo:
        bruta = corpo.get("evolucao_horas_mes")
        if bruta in (None, ""):
            # Numa proposta que é só fee mensal o pacote é o produto: sem ele o
            # `precificar.py` aborta e a proposta fica sem orçamento nenhum.
            if escopo.get("modelo_principal") == "evolucao":
                raise erro_400(
                    "pacote_obrigatorio",
                    "esta proposta é de fee mensal: o pacote de horas é o que "
                    "está sendo vendido e não pode ficar vazio")
            escopo.pop("evolucao_solicitada", None)
        else:
            try:
                horas = int(str(bruta).strip())
            except (ValueError, TypeError):
                raise erro_400("horas_invalidas",
                               f"não entendi as horas do pacote: {bruta!r}") from None
            if horas < 1:
                raise erro_400("horas_invalidas", "o pacote precisa de ao menos 1 hora")
            escopo["evolucao_solicitada"] = {"ativa": True, "horas_mes": horas}

    caminho_escopo.write_text(
        json.dumps(escopo, ensure_ascii=False, indent=2) + "\n", "utf-8"
    )

    usuario = getattr(req, "usuario", None)
    _registrar_no_md(base, antes, depois, cat, usuario["email"] if usuario else "app")

    ok, _orc, mensagem = scripts_runner.precificar(
        valor_fechado=linha["valor_fechado"],
        motivo_fechado=linha["motivo_fechado"] or "",
        base=base,
    )
    if not ok:
        raise erro_409("falhou_precificar", mensagem)

    executor.marcar_fase_no_manifest(base / "proposta", "03")
    if ws.montado() == linha["slug"]:
        import shutil

        for nome in ("02-escopo.json", "02-escopo.md", "03-orcamento.json",
                     "03-orcamento.md", "manifest.json"):
            origem = base / "proposta" / nome
            if origem.is_file():
                shutil.copy2(origem, cfg.SINGLETON_PROPOSTA / nome)

    executor.sincronizar_orcamento(linha["id"], linha["slug"])
    # Reabre em vez de só derrubar: editando por fora da UI, uma proposta
    # `gerada` ficava com o checkpoint pendente e sem caminho de volta.
    modelo.reabrir_para_gate(linha["id"], "o escopo foi editado à mão e o total mudou")
    db.evento(linha["id"], "escopo_editado", f"{len(antes)} → {len(depois)} itens cotados")

    atualizada = db.um("SELECT * FROM propostas WHERE id = ?", (linha["id"],))
    import eventos

    eventos.proposta(atualizada)
    return {"ok": True, "total_fmt": atualizada["total_fmt"], "itens": len(depois)}
