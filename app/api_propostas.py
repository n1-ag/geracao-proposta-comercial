"""Rotas de CRUD das propostas.

Importado por `servidor.py` pelo efeito colateral: registrar as rotas.
"""

from __future__ import annotations

import re
import shutil
from urllib.parse import parse_qs, urlparse

import artefatos
import config as cfg
import db
import ficha
import workspace as ws
from roteador import erro_400, erro_404, erro_409, rota

# Estados em que o cadastro ainda pode ser editado. Depois que a narrativa foi
# escrita, mexer na ficha sem refazer o pipeline produziria um PDF incoerente
# com o que está no banco.
EDITAVEIS = {"rascunho", "erro", "aguardando_aprovacao"}


# -----------------------------------------------------------------------------
# Validação do cadastro
# -----------------------------------------------------------------------------

TEXTOS = [
    "cliente", "razao_social", "contato", "cargo_contato", "email", "whatsapp",
    "reuniao_por", "outros_presentes",
]
ESCOLHAS = {
    "modelo": cfg.MODELOS_PROPOSTA,
    "plataforma": cfg.PLATAFORMAS,
    "natureza": cfg.NATUREZAS,
}
LIMITE_TRANSCRICAO = 2_000_000  # ~2 MB; uma reunião de 3 h dá ~100 KB


def _texto(valor, limite=400) -> str | None:
    if valor is None:
        return None
    limpo = str(valor).strip()
    if not limpo:
        return None
    if len(limpo) > limite:
        raise erro_400("campo_longo", f"campo com mais de {limite} caracteres")
    return limpo


def _escolha(valor, validos: list[str], campo: str) -> str | None:
    """Vazio e 'auto' viram NULL: é o agente que decide, a partir da transcrição."""
    if valor in (None, "", "auto"):
        return None
    v = str(valor).strip().lower()
    if v not in validos:
        raise erro_400("valor_invalido", f"{campo} precisa ser um de: {', '.join(validos)} ou auto")
    return v


def _data_iso(valor, campo: str) -> str | None:
    if not valor:
        return None
    v = str(valor).strip()
    if re.match(r"^\d{4}-\d{2}-\d{2}$", v):
        return v
    casou = re.match(r"^(\d{1,2})/(\d{1,2})/(\d{4})$", v)
    if casou:
        d, m, a = casou.groups()
        return f"{a}-{int(m):02d}-{int(d):02d}"
    raise erro_400("data_invalida", f"{campo} precisa estar em DD/MM/AAAA")


def validar_cadastro(corpo: dict, criando: bool) -> dict:
    dados = {campo: _texto(corpo.get(campo)) for campo in TEXTOS}

    if criando and not dados["cliente"]:
        raise erro_400("cliente_obrigatorio", "o nome do cliente é obrigatório")

    for campo, validos in ESCOLHAS.items():
        dados[campo] = _escolha(corpo.get(campo), validos, campo)

    dados["validade"] = _data_iso(corpo.get("validade"), "validade")
    dados["data_reuniao"] = _data_iso(corpo.get("data_reuniao"), "data da reunião")

    layout = corpo.get("layout_do_cliente")
    dados["layout_do_cliente"] = (
        None if layout in (None, "", "auto") else (1 if layout in (True, 1, "1", "sim") else 0)
    )

    pacote = corpo.get("pacote_mensal_h")
    try:
        dados["pacote_mensal_h"] = int(pacote) if pacote not in (None, "") else None
    except (TypeError, ValueError):
        raise erro_400("pacote_invalido", "o pacote mensal precisa ser um número de horas") from None

    return dados


def validar_transcricao(corpo: dict, obrigatoria: bool) -> str | None:
    bruta = corpo.get("transcricao")
    if bruta is None:
        if obrigatoria:
            raise erro_400("transcricao_obrigatoria", "cole a transcrição da reunião")
        return None
    texto = str(bruta)
    if len(texto) > LIMITE_TRANSCRICAO:
        raise erro_400("transcricao_longa", "a transcrição passou de 2 MB")
    if obrigatoria and len(texto.strip()) < 200:
        raise erro_400(
            "transcricao_curta",
            "a transcrição tem menos de 200 caracteres — cole o texto completo da reunião",
        )
    return texto


# -----------------------------------------------------------------------------
# Consulta
# -----------------------------------------------------------------------------


def carregar(proposta_id: str | int) -> dict:
    linha = db.um("SELECT * FROM propostas WHERE id = ?", (int(proposta_id),))
    if not linha:
        raise erro_404(f"proposta {proposta_id} não existe")
    return linha


def _query(req) -> dict:
    return {k: v[0] for k, v in parse_qs(urlparse(req.path).query).items()}


@rota("GET", r"^/api/propostas$")
def listar(req):
    q = _query(req)
    onde = []
    params: list = []

    if q.get("incluir_arquivadas") != "1":
        onde.append("arquivada = 0")
    if q.get("status"):
        onde.append("status = ?")
        params.append(q["status"])
    if q.get("comercial"):
        if q["comercial"] == "sem":
            onde.append("status_comercial IS NULL")
        else:
            onde.append("status_comercial = ?")
            params.append(q["comercial"])
    if q.get("plataforma"):
        onde.append("COALESCE(plataforma_res, plataforma) = ?")
        params.append(q["plataforma"])
    if q.get("q"):
        onde.append("(cliente LIKE ? OR razao_social LIKE ? OR contato LIKE ?)")
        alvo = f"%{q['q']}%"
        params += [alvo, alvo, alvo]

    filtro = f"WHERE {' AND '.join(onde)}" if onde else ""
    total = db.valor(f"SELECT COUNT(*) FROM propostas {filtro}", tuple(params), 0)

    por_pagina = min(int(q.get("por_pagina", 50)), 200)
    pagina = max(int(q.get("pagina", 1)), 1)

    itens = db.buscar(
        f"""SELECT id, slug, cliente, contato, plataforma, plataforma_res, modelo_res,
                   total_cru, total_fmt, total_tipo, status, status_comercial,
                   fase_atual, checkpoint_status, pdf_caminho, erro_mensagem,
                   criado_em, atualizado_em, arquivada, origem
            FROM propostas {filtro}
            ORDER BY atualizado_em DESC LIMIT ? OFFSET ?""",
        (*params, por_pagina, (pagina - 1) * por_pagina),
    )
    return {"itens": itens, "total": total, "pagina": pagina, "por_pagina": por_pagina}


@rota("GET", r"^/api/propostas/(?P<pid>\d+)$")
def detalhar(req, pid):
    linha = carregar(pid)
    slug = linha["slug"]
    base = ws.caminho(slug)

    retrato = artefatos.Retrato(base)

    return {
        "proposta": linha,
        "manifest": retrato.manifest or None,
        "transcricao_bytes": (
            (base / "entrada" / "transcricao.md").stat().st_size
            if (base / "entrada" / "transcricao.md").is_file() else 0
        ),
        "observacoes": ficha.ler_observacoes(base / "entrada" / "observacoes.md"),
        "artefatos": ws.artefatos(slug),
        "previews": ws.previews(slug),
        "alertas": db.buscar(
            "SELECT * FROM alertas WHERE proposta_id = ? ORDER BY "
            "CASE severidade WHEN 'alta' THEN 0 WHEN 'media' THEN 1 ELSE 2 END",
            (linha["id"],),
        ),
        "lacunas": db.buscar("SELECT * FROM lacunas WHERE proposta_id = ? ORDER BY id", (linha["id"],)),
        "ajustes": db.buscar("SELECT * FROM ajustes WHERE proposta_id = ? ORDER BY ordem", (linha["id"],)),
        "execucoes": db.buscar(
            "SELECT * FROM execucoes WHERE proposta_id = ? ORDER BY id DESC LIMIT 10", (linha["id"],)
        ),
        "fases": db.buscar(
            "SELECT * FROM fases WHERE proposta_id = ? ORDER BY id DESC LIMIT 40", (linha["id"],)
        ),
        "eventos": db.buscar(
            "SELECT * FROM eventos WHERE proposta_id = ? ORDER BY id DESC LIMIT 20", (linha["id"],)
        ),
        "montada": ws.montado() == slug,
    }


# -----------------------------------------------------------------------------
# Escrita
# -----------------------------------------------------------------------------


def _gravar_entradas(slug: str, cadastro: dict, transcricao: str | None, observacoes) -> None:
    """Materializa o cadastro nos arquivos que o pipeline lê."""
    base = ws.caminho(slug)
    ficha.escrever(cadastro, base / "entrada" / "dados-cliente.md")
    if transcricao is not None:
        (base / "entrada" / "transcricao.md").write_text(transcricao, "utf-8")
    if observacoes is not None:
        ficha.escrever_observacoes(observacoes, base / "entrada" / "observacoes.md")


@rota("POST", r"^/api/propostas$")
def criar(req):
    corpo = req.json_do_corpo()
    cadastro = validar_cadastro(corpo, criando=True)
    transcricao = validar_transcricao(corpo, obrigatoria=True)
    observacoes = corpo.get("observacoes") or ""

    if not cadastro["validade"]:
        cadastro["validade"] = ficha.validade_padrao()

    slug = ws.novo_slug(cadastro["cliente"])
    ws.criar(slug)

    agora = db.agora()
    with db.transacao():
        pid = db.inserir(
            "propostas",
            {
                **cadastro,
                "slug": slug,
                "workspace": f"propostas/{slug}",
                "origem": "app",
                "status": "rascunho",
                "fase_atual": "00",
                "criado_em": agora,
                "atualizado_em": agora,
            },
        )
        db.registrar_mudanca(pid, "status", None, "rascunho", "criada no app")
        db.evento(pid, "criada", f"workspace propostas/{slug}")

    _gravar_entradas(slug, cadastro, transcricao, observacoes)
    ws.escrever_meta(slug, db.um("SELECT * FROM propostas WHERE id = ?", (pid,)))

    return 201, {"id": pid, "slug": slug, "workspace": f"propostas/{slug}"}


@rota("PUT", r"^/api/propostas/(?P<pid>\d+)$")
def editar(req, pid):
    linha = carregar(pid)
    if linha["status"] not in EDITAVEIS:
        raise erro_409(
            "estado_nao_editavel",
            f"não dá para editar uma proposta em '{linha['status']}' — "
            f"espere a execução terminar ou retome a partir do erro",
        )

    corpo = req.json_do_corpo()
    cadastro = validar_cadastro(corpo, criando=False)
    transcricao = validar_transcricao(corpo, obrigatoria=False)
    observacoes = corpo.get("observacoes")

    # Só sobrescreve o que veio no corpo: um PUT parcial não deve apagar campo
    # que a tela nem mostrou.
    mudancas = {k: v for k, v in cadastro.items() if k in corpo}
    if "cliente" in mudancas and not mudancas["cliente"]:
        raise erro_400("cliente_obrigatorio", "o nome do cliente não pode ficar vazio")

    mudancas["atualizado_em"] = db.agora()
    with db.transacao():
        db.atualizar("propostas", linha["id"], mudancas)
        db.evento(linha["id"], "cadastro_editado", ", ".join(sorted(mudancas)))

    atualizada = db.um("SELECT * FROM propostas WHERE id = ?", (linha["id"],))
    _gravar_entradas(linha["slug"], atualizada, transcricao, observacoes)
    ws.escrever_meta(linha["slug"], atualizada)

    # Editar depois do orçamento invalida a aprovação: o número foi calculado
    # sobre outra ficha.
    if linha["status"] == "aguardando_aprovacao" and linha["checkpoint_status"] == "aprovado":
        db.executar(
            "UPDATE propostas SET checkpoint_status='pendente', checkpoint_em=NULL WHERE id=?",
            (linha["id"],),
        )

    return {"ok": True, "proposta": db.um("SELECT * FROM propostas WHERE id = ?", (linha["id"],))}


@rota("DELETE", r"^/api/propostas/(?P<pid>\d+)$")
def excluir(req, pid):
    """Exclusão em dois níveis.

    Sem `?purgar=1`: a proposta sai do app e do painel, mas a linha e os
    arquivos continuam onde estão. É reversível por `POST .../restaurar`.

    Com `?purgar=1`: apaga a linha (o CASCADE leva alertas, lacunas, ajustes,
    fases, execuções e histórico) **e** a pasta do workspace, com o PDF dentro.
    Irreversível, e por isso exige o nome do cliente digitado em
    `?confirmacao=` — a mesma proteção que `scripts/arquivar.py --limpar` usa
    no fluxo de terminal.
    """
    linha = carregar(pid)

    if linha["status"].startswith("executando") or linha["status"] == "enfileirada":
        raise erro_409(
            "em_execucao",
            "esta proposta está na fila ou executando; cancele na Fila antes de excluir",
        )

    q = _query(req)
    purgar = q.get("purgar") == "1"

    if not purgar:
        with db.transacao():
            db.atualizar("propostas", linha["id"], {"arquivada": 1, "atualizado_em": db.agora()})
            db.evento(linha["id"], "excluida", "removida do app; arquivos preservados")
        return {"ok": True, "purgado": False, "proposta_id": linha["id"]}

    # A partir daqui é irreversível.
    if (q.get("confirmacao") or "").strip().casefold() != linha["cliente"].strip().casefold():
        raise erro_400(
            "confirmacao_incorreta",
            f"para apagar de vez, confirme digitando o nome do cliente: {linha['cliente']}",
        )

    # Se ela estiver montada nos singletons, desmonta antes: apagar o workspace
    # sob os pés deixaria `entrada/`, `proposta/` e `saida/` com os arquivos de
    # uma proposta que não existe mais, e o `estado.json` apontando para o nada.
    if ws.montado() == linha["slug"]:
        outra = db.um(
            "SELECT slug FROM propostas WHERE id <> ? AND arquivada = 0 "
            "ORDER BY atualizado_em DESC LIMIT 1",
            (linha["id"],),
        )
        if outra:
            ws.montar(outra["slug"])
        else:
            ws.limpar_singletons()

    with db.transacao():
        db.executar("DELETE FROM propostas WHERE id = ?", (linha["id"],))

    base = ws.caminho(linha["slug"]).resolve()
    if base.is_relative_to(cfg.WORKSPACES.resolve()) and base != cfg.WORKSPACES.resolve():
        shutil.rmtree(base, ignore_errors=True)

    return {"ok": True, "purgado": True, "cliente": linha["cliente"]}


@rota("POST", r"^/api/propostas/(?P<pid>\d+)/restaurar$")
def restaurar(req, pid):
    """Desfaz a exclusão leve."""
    linha = carregar(pid)
    if not linha["arquivada"]:
        return {"ok": True, "proposta": linha}

    if not ws.caminho(linha["slug"]).is_dir():
        raise erro_409(
            "workspace_sumiu",
            "os arquivos desta proposta não estão mais no disco; não há o que restaurar",
        )

    with db.transacao():
        db.atualizar("propostas", linha["id"], {"arquivada": 0, "atualizado_em": db.agora()})
        db.evento(linha["id"], "restaurada", "trazida de volta para o app")

    return {"ok": True, "proposta": db.um("SELECT * FROM propostas WHERE id = ?", (linha["id"],))}


@rota("GET", r"^/api/propostas/(?P<pid>\d+)/entrada$")
def ler_entrada(req, pid):
    """A transcrição e as observações, para reabrir o formulário de edição."""
    linha = carregar(pid)
    base = ws.caminho(linha["slug"])
    transcricao = base / "entrada" / "transcricao.md"
    return {
        "transcricao": transcricao.read_text("utf-8") if transcricao.is_file() else "",
        "observacoes": ficha.ler_observacoes(base / "entrada" / "observacoes.md"),
    }
