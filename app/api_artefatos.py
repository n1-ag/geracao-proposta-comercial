"""Rotas que servem arquivo: PDF, previews, artefatos e logs.

Todas passam pela mesma defesa dupla contra travessia de caminho: whitelist de
nomes em `workspace.resolver_artefato` e confinamento ao workspace da proposta.
"""

from __future__ import annotations

import io
import zipfile
from pathlib import Path
from urllib.parse import parse_qs, quote, urlparse

import workspace as ws
from api_propostas import carregar
from roteador import RESPOSTA_JA_ENVIADA, erro_400, erro_404, rota

TIPOS = {
    ".md": "text/markdown; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".html": "text/html; charset=utf-8",
    ".png": "image/png",
    ".pdf": "application/pdf",
}


def _query(req) -> dict:
    return {k: v[0] for k, v in parse_qs(urlparse(req.path).query).items()}


def _servir(req, caminho: Path, tipo: str, disposicao: str = "inline"):
    dados = caminho.read_bytes()
    req.responder_bytes(
        200, tipo, dados,
        {
            "Content-Disposition": f'{disposicao}; filename="{quote(caminho.name)}"',
            "Cache-Control": "no-cache",
        },
    )
    return RESPOSTA_JA_ENVIADA


@rota("GET", r"^/api/propostas/(?P<pid>\d+)/pdf$")
def pdf(req, pid):
    linha = carregar(pid)
    if not linha["pdf_caminho"]:
        raise erro_404("esta proposta ainda não tem PDF")

    alvo = (ws.caminho(linha["slug"]) / linha["pdf_caminho"]).resolve()
    base = ws.caminho(linha["slug"]).resolve()
    if not alvo.is_relative_to(base) or not alvo.is_file():
        raise erro_404("o arquivo do PDF não está mais no lugar registrado")

    baixar = _query(req).get("baixar") == "1"
    return _servir(req, alvo, "application/pdf", "attachment" if baixar else "inline")


@rota("GET", r"^/api/propostas/(?P<pid>\d+)/preview/(?P<n>\d+)$")
def preview(req, pid, n):
    linha = carregar(pid)
    nome = f"pagina-{int(n):02d}.png"
    alvo = (ws.caminho(linha["slug"]) / "saida" / "preview" / nome).resolve()
    base = ws.caminho(linha["slug"]).resolve()
    if not alvo.is_relative_to(base) or not alvo.is_file():
        raise erro_404(f"não há preview da página {n}")
    return _servir(req, alvo, "image/png")


@rota("GET", r"^/api/propostas/(?P<pid>\d+)/artefato/(?P<nome>[A-Za-z0-9._-]+)$")
def artefato(req, pid, nome):
    linha = carregar(pid)
    try:
        alvo = ws.resolver_artefato(linha["slug"], nome)
    except ValueError as e:
        raise erro_400("artefato_invalido", str(e)) from None
    if not alvo.is_file():
        raise erro_404(f"{nome} não existe nesta proposta")
    return _servir(req, alvo, TIPOS.get(alvo.suffix, "text/plain; charset=utf-8"))


@rota("GET", r"^/api/propostas/(?P<pid>\d+)/logs$")
def logs(req, pid):
    """O stream bruto de uma fase, humanizado o suficiente para depurar."""
    import json

    linha = carregar(pid)
    q = _query(req)
    pasta = ws.caminho(linha["slug"]) / "logs"
    if not pasta.is_dir():
        raise erro_404("esta proposta não tem logs")

    arquivos = sorted(pasta.glob("*.jsonl"))
    if q.get("arquivo"):
        arquivos = [a for a in arquivos if a.name == q["arquivo"]]
    elif q.get("fase"):
        arquivos = [a for a in arquivos if f"-{q['fase']}-" in a.name]
    if not arquivos:
        raise erro_404("nenhum log corresponde ao filtro")

    alvo = arquivos[-1]
    saida = [f"# {alvo.name}", ""]
    for bruto in alvo.read_text("utf-8").splitlines():
        try:
            e = json.loads(bruto)
        except json.JSONDecodeError:
            continue
        tipo = e.get("type")
        if tipo == "system":
            saida.append(f"[init] modelo={e.get('model')} cwd={e.get('cwd')}")
        elif tipo == "assistant":
            for item in (e.get("message") or {}).get("content") or []:
                if item.get("type") == "tool_use":
                    entrada = json.dumps(item.get("input") or {}, ensure_ascii=False)[:220]
                    saida.append(f"[tool] {item.get('name')} {entrada}")
                elif item.get("type") == "text" and item.get("text", "").strip():
                    saida.append(f"[texto] {item['text'].strip()[:400]}")
        elif tipo == "user":
            for item in (e.get("message") or {}).get("content") or []:
                if item.get("type") == "tool_result" and item.get("is_error"):
                    saida.append(f"[erro de ferramenta] {str(item.get('content'))[:300]}")
        elif tipo == "result":
            saida.append(
                f"[result] erro={e.get('is_error')} subtype={e.get('subtype')} "
                f"custo=US$ {e.get('total_cost_usd')} turnos={e.get('num_turns')}"
            )

    req.responder_bytes(
        200, "text/plain; charset=utf-8", "\n".join(saida).encode("utf-8"),
        {"X-Log-Arquivo": alvo.name},
    )
    return RESPOSTA_JA_ENVIADA


@rota("GET", r"^/api/propostas/(?P<pid>\d+)/exportar$")
def exportar(req, pid):
    """Zip do workspace inteiro. O app roda numa máquina só; esta é a saída de
    emergência para levar a proposta para outro lugar."""
    linha = carregar(pid)
    base = ws.caminho(linha["slug"])
    if not base.is_dir():
        raise erro_404("o workspace desta proposta não existe mais")

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as z:
        for item in base.rglob("*"):
            if item.is_file():
                z.write(item, f"{linha['slug']}/{item.relative_to(base)}")

    dados = buffer.getvalue()
    req.responder_bytes(
        200, "application/zip", dados,
        {"Content-Disposition": f'attachment; filename="{linha["slug"]}.zip"'},
    )
    return RESPOSTA_JA_ENVIADA
