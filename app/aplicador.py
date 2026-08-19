"""Executa as operações que a triagem entendeu. Determinístico, sem LLM.

A triagem lê o português e nomeia a operação; aqui ela vira escrita em disco e
uma chamada ao `precificar.py`. Nenhum número é decidido neste módulo: os que
chegam vieram do texto do vendedor e passaram pela tela de conferência.

Tudo que não é `texto_livre` acontece em menos de um segundo, sem fila e sem
disputar as pastas de trabalho — é o mesmo caminho da edição manual de escopo.
Só o que sobra vai para o agente.
"""

from __future__ import annotations

import json
import shutil
from datetime import datetime

import config as cfg
import db
import executor
import modelo
import scripts_runner
import workspace as ws

ORIGEM_MANUAL = "ajuste pedido no gate"


def reprecificar(linha: dict) -> tuple[bool, str]:
    """Roda o `precificar.py` sobre o workspace e propaga o resultado.

    Extraído para um lugar só porque a sequência é sutil e três rotas precisam
    dela: precificar sobre o workspace, marcar a fase no manifest, espelhar no
    singleton **se** for a proposta montada, e sincronizar o total no banco.
    Errar a ordem deixa a tela mostrando um número e o PDF outro.
    """
    base = ws.caminho(linha["slug"])
    ok, _orc, mensagem = scripts_runner.precificar(
        valor_fechado=linha["valor_fechado"],
        motivo_fechado=linha["motivo_fechado"] or "",
        base=base,
    )
    if not ok:
        return False, mensagem

    executor.marcar_fase_no_manifest(base / "proposta", "03")
    if ws.montado() == linha["slug"]:
        for nome in ("02-escopo.json", "02-escopo.md", "03-orcamento.json",
                     "03-orcamento.md", "manifest.json"):
            origem = base / "proposta" / nome
            if origem.is_file():
                shutil.copy2(origem, cfg.SINGLETON_PROPOSTA / nome)

    executor.sincronizar_orcamento(linha["id"], linha["slug"])
    return True, ""


# -----------------------------------------------------------------------------
# As operações
# -----------------------------------------------------------------------------


def _linha(itens: list, op: dict) -> dict | None:
    """A linha que a operação mira, pelo índice que a triagem resolveu.

    Pelo `catalogo_id` não dá: cinco `pagina-institucional-extra` na mesma
    proposta e a busca acertaria sempre a primeira.
    """
    k = op.get("alvo")
    if k is not None and 0 <= k < len(itens):
        return itens[k]
    cid = op.get("catalogo_id")
    iguais = [i for i in itens if i.get("catalogo_id") == cid]
    return iguais[0] if len(iguais) == 1 else None


def _aplicar_no_escopo(escopo: dict, op: dict) -> str:
    """Muda o escopo em memória. Devolve a frase do rastro."""
    tipo = op["tipo"]
    itens = escopo.setdefault("itens", [])
    cid = op.get("catalogo_id")
    nome = op.get("nome") or cid

    if tipo in ("valor_item", "horas_item"):
        item = _linha(itens, op)
        if item is None:
            raise ValueError("não achei a linha para fixar as horas")
        item["horas"] = op["horas"]
        # A complexidade deixa de mandar no esforço, mas continua no arquivo:
        # ela é o registro de como o item foi classificado, e apagá-la perderia
        # a informação de que a fixação foi uma decisão contra a faixa.
        return (f"- **Horas fixadas:** `{cid}` — {nome}: {op['horas']}h por unidade"
                + (f" (pedido de {_brl(op['valor'])})" if tipo == "valor_item" else ""))

    if tipo == "item_incluso":
        item = _linha(itens, op) if op.get("ja_cotado") else None
        if item is None:
            itens.append({
                "catalogo_id": cid, "complexidade": None, "quantidade": 1,
                "rotulo": "", "design_pela_n1": True,
                "origem": [ORIGEM_MANUAL], "observacao": "",
                "incluso_no_padrao": True,
            })
        else:
            item["incluso_no_padrao"] = True
            item.pop("horas", None)
        return f"- **Incluso no valor base:** `{cid}` — {nome}, cotado a zero nesta proposta"

    if tipo == "remover_item":
        item = _linha(itens, op)
        if item is None:
            raise ValueError("não achei a linha para remover")
        escopo["itens"] = [i for i in itens if i is not item]
        return f"- **Removido:** `{cid}` — {nome}"

    if tipo == "acrescentar_item":
        itens.append({
            "catalogo_id": cid,
            "complexidade": op.get("complexidade"),
            "quantidade": op.get("quantidade", 1),
            "rotulo": op.get("rotulo", ""),
            "design_pela_n1": True,
            "origem": [ORIGEM_MANUAL],
            "observacao": "",
        })
        return (f"- **Acrescentado:** `{cid}` — {nome} "
                f"(complexidade {op.get('complexidade') or 'não se aplica'}, "
                f"{op.get('quantidade', 1)}×)")

    if tipo == "rotulo_item":
        item = _linha(itens, op)
        if item is None:
            raise ValueError("não achei a linha para renomear")
        antigo = (item.get("rotulo") or "").strip() or nome
        item["rotulo"] = op["rotulo"]
        return f"- **Rótulo:** `{cid}` — «{antigo}» → «{op['rotulo']}»"

    if tipo == "valor_base":
        escopo["valor_base_override"] = op["valor"]
        return f"- **Valor base:** substituído por {_brl(op['valor'])}"

    if tipo == "prazo":
        escopo["prazo_semanas"] = {
            "min": op["min"], "max": op["max"],
            # `precificar.py` exige origem para prazo declarado: um prazo
            # prometido sem lastro é o tipo de promessa que cobra depois.
            "origem": [ORIGEM_MANUAL],
            "justificativa": "definido pelo comercial no gate",
        }
        return f"- **Prazo:** {op['min']} a {op['max']} semanas"

    return ""


def aplicar(linha: dict, operacoes: list, quem: str) -> dict:
    """Executa as operações escolhidas. Devolve o resultado por operação."""
    base = ws.caminho(linha["slug"])
    caminho = base / "proposta" / "02-escopo.json"
    if not caminho.is_file():
        return {"ok": False, "erro": "esta proposta ainda não tem escopo"}

    escopo = json.loads(caminho.read_text("utf-8"))
    resultado, rastro, livres = [], [], []
    valor_total = None

    for op in operacoes:
        tipo = op.get("tipo")
        try:
            if tipo == "texto_livre":
                livres.append(op.get("instrucao") or op.get("trecho") or "")
                resultado.append({**op, "feito": True, "como": "enviado ao agente"})
            elif tipo == "valor_total":
                valor_total = op["valor"]
                resultado.append({**op, "feito": True,
                                  "como": f"total fechado em {_brl(op['valor'])}"})
            else:
                frase = _aplicar_no_escopo(escopo, op)
                rastro.append(frase)
                resultado.append({**op, "feito": True, "como": frase.split("** ", 1)[-1]})
        except Exception as e:  # noqa: BLE001
            resultado.append({**op, "feito": False, "como": f"falhou: {e}"})

    if rastro:
        caminho.write_text(json.dumps(escopo, ensure_ascii=False, indent=2) + "\n", "utf-8")
        _registrar(base, rastro, quem)

    if valor_total is not None:
        db.executar(
            "UPDATE propostas SET valor_fechado=?, motivo_fechado=?, fechado_em=?, "
            "atualizado_em=? WHERE id=?",
            (valor_total, "pedido no ajuste", db.agora(), db.agora(), linha["id"]),
        )
        linha = db.um("SELECT * FROM propostas WHERE id = ?", (linha["id"],))

    if rastro or valor_total is not None:
        ok, mensagem = reprecificar(linha)
        if not ok:
            return {"ok": False, "erro": mensagem, "resultado": resultado}

    atualizada = db.um("SELECT * FROM propostas WHERE id = ?", (linha["id"],))
    return {"ok": True, "resultado": resultado, "livres": livres,
            "total_fmt": atualizada["total_fmt"]}


def _registrar(base, rastro: list, quem: str) -> None:
    """Anexa ao `02-escopo.md` o que mudou.

    Os dois espelhos precisam contar a mesma história: `auditar.py escopo`
    reprova item que está no JSON e não aparece no `.md`, e uma edição sem
    rastro apagaria o porquê de um número ter mudado.
    """
    alvo = base / "proposta" / "02-escopo.md"
    if not alvo.is_file():
        return
    carimbo = datetime.now().strftime("%d/%m/%Y %H:%M")
    texto = alvo.read_text("utf-8").rstrip()
    texto += (
        f"\n\n## Ajuste aplicado — {carimbo}\n\n"
        f"Pedido por {quem} na tela de aprovação, lido e conferido antes de aplicar. "
        f"O total foi recalculado por `scripts/precificar.py`.\n\n"
        + "\n".join(rastro) + "\n"
    )
    alvo.write_text(texto, "utf-8")


def _brl(v) -> str:
    return "R$ " + f"{float(v):,.2f}".replace(",", "§").replace(".", ",").replace("§", ".")
