"""Leitura dos artefatos de uma proposta e derivação dos campos do banco.

Um lugar só para responder "o que este workspace diz sobre esta proposta?".
Usado pelo import (que lê pastas legadas) e pelo motor (que lê o que acabou de
gerar). Nada aqui escreve.
"""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import config as cfg

# `ler_ficha` é a autoridade sobre o formato de entrada/dados-cliente.md.
# Reimplementar aqui seria criar uma segunda verdade que diverge na primeira
# mudança do parser.
sys.path.insert(0, str(cfg.SCRIPTS))
from precificar import ler_ficha  # noqa: E402

FASES = ["01", "02", "03", "04", "05", "06"]

# De que cada fase depende. Um artefato só é "desta rodada" se for mais novo
# que tudo que a fase leu — comparar com o início da tentativa reprovaria uma
# retentativa em que o agente, com razão, não reescreveu um arquivo que já
# estava correto.
ENTRADA_DA_FASE = {
    "01": ["../entrada/transcricao.md", "../entrada/dados-cliente.md"],
    "02": ["01-briefing.md", "ajustes.md"],
    "03": ["02-escopo.json"],
    "04": ["03-orcamento.json", "02-escopo.md", "ajustes.md"],
    "05": ["04-narrativa.md", "03-orcamento.json"],
    "06": ["proposta.html"],
}

# Artefato canônico de cada fase, relativo à pasta proposta/ do workspace.
ARTEFATO_DA_FASE = {
    "01": ["01-briefing.md"],
    "02": ["02-escopo.md", "02-escopo.json"],
    "03": ["03-orcamento.md", "03-orcamento.json"],
    "04": ["04-narrativa.md"],
    "05": ["05-montagem.md", "proposta.html"],
    "06": ["06-revisao.md"],
}


# -----------------------------------------------------------------------------
# Leitura crua
# -----------------------------------------------------------------------------


def ler_json(caminho: Path) -> dict | None:
    try:
        return json.loads(caminho.read_text("utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def artefatos_desatualizados(fase: str, pasta: Path) -> list[str]:
    """Artefatos da fase que faltam ou são anteriores às entradas dela.

    É a checagem que separa "o agente produziu" de "sobrou da rodada passada".
    Um arquivo intocado numa retentativa continua válido, desde que seja mais
    novo do que aquilo que a fase leu para produzi-lo.
    """
    entradas = []
    for rel in ENTRADA_DA_FASE.get(fase, []):
        alvo = pasta / rel
        if alvo.is_file():
            entradas.append(alvo.stat().st_mtime)
    piso = max(entradas) if entradas else 0

    problemas = []
    for nome in ARTEFATO_DA_FASE.get(fase, []):
        alvo = pasta / nome
        if not alvo.is_file():
            problemas.append(f"{nome} (não existe)")
        elif alvo.stat().st_mtime < piso - 2:
            problemas.append(f"{nome} (mais antigo que as entradas da fase)")
    return problemas


def hash_orcamento(orc: dict) -> str:
    """Hash do conteúdo do orçamento, ignorando a data de geração.

    O `hash_entrada` do precificar.py cobre apenas os três TOML de preço — ele
    NÃO se move quando o escopo muda, então não serve para detectar que uma
    aprovação ficou obsoleta. Este hash cobre o orçamento inteiro e é o que o
    app usa no gate.
    """
    copia = {k: v for k, v in orc.items() if k != "gerado_em"}
    canonico = json.dumps(copia, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return "sha256:" + hashlib.sha256(canonico.encode("utf-8")).hexdigest()[:16]


def _iso_de_mtime(caminho: Path) -> str:
    ts = datetime.fromtimestamp(caminho.stat().st_mtime, tz=timezone.utc)
    return ts.replace(microsecond=0).isoformat()


def _data_br_para_iso(valor: str | None) -> str | None:
    if not valor:
        return None
    casou = re.match(r"^\s*(\d{1,2})/(\d{1,2})/(\d{4})\s*$", valor)
    if casou:
        d, m, a = casou.groups()
        return f"{a}-{int(m):02d}-{int(d):02d}"
    if re.match(r"^\d{4}-\d{2}-\d{2}$", valor.strip()):
        return valor.strip()
    return None


def _sim_nao(valor: str | None) -> int | None:
    if not valor:
        return None
    v = valor.strip().lower()
    if v in ("sim", "s", "true", "1"):
        return 1
    if v in ("nao", "não", "n", "false", "0"):
        return 0
    return None


def _auto_para_none(valor: str | None, validos: list[str]) -> str | None:
    if not valor:
        return None
    v = valor.strip().lower()
    return v if v in validos else None


def paginas_do_pdf(pdf: Path) -> int | None:
    try:
        r = subprocess.run(["pdfinfo", str(pdf)], capture_output=True, text=True, timeout=20)
        casou = re.search(r"^Pages:\s+(\d+)", r.stdout, re.M)
        return int(casou.group(1)) if casou else None
    except (OSError, subprocess.SubprocessError, ValueError):
        return None


# -----------------------------------------------------------------------------
# Retrato de um workspace
# -----------------------------------------------------------------------------


class Retrato:
    """Tudo que se sabe sobre uma proposta olhando só para os arquivos dela.

    `base` é uma pasta contendo entrada/, proposta/ e saida/ — serve tanto para
    um workspace do app quanto para uma pasta de arquivo/ ou para a raiz do repo.
    """

    def __init__(self, base: Path):
        self.base = Path(base)
        self.p_entrada = self.base / "entrada"
        self.p_proposta = self.base / "proposta"
        self.p_saida = self.base / "saida"

        self.manifest = ler_json(self.p_proposta / "manifest.json") or {}
        self.orcamento = ler_json(self.p_proposta / "03-orcamento.json") or {}
        self.escopo = ler_json(self.p_proposta / "02-escopo.json") or {}
        self.ficha = ler_ficha(self.p_entrada / "dados-cliente.md") or {}

    # -- presença ------------------------------------------------------------

    def existe(self) -> bool:
        """Vale a pena importar? Precisa de pelo menos um dos dois âncoras."""
        return bool(self.manifest or self.orcamento)

    def pdf(self) -> Path | None:
        declarado = (self.manifest.get("saida") or {}).get("pdf")
        if declarado:
            alvo = self.base / declarado
            if alvo.is_file():
                return alvo
        achados = sorted(self.p_saida.glob("*.pdf")) if self.p_saida.is_dir() else []
        return achados[0] if achados else None

    def artefatos_ausentes(self) -> list[str]:
        """Artefatos que o manifest declara como concluídos e não estão no disco.

        Acontece de verdade: propostas arquivadas pelo fluxo antigo têm o
        manifest dizendo 'concluida' para as seis fases e só metade dos arquivos.
        """
        faltando = []
        for fase, bloco in (self.manifest.get("fases") or {}).items():
            if bloco.get("status") != "concluida":
                continue
            for chave in ("artefato", "espelho", "saida"):
                rel = bloco.get(chave)
                if rel and not (self.base / rel).is_file():
                    faltando.append(f"{fase}: {rel}")
        return faltando

    def fase_derivada(self) -> str:
        """Maior fase cujo artefato principal existe. Usada quando o manifest
        não diz nada, ou para conferir o que ele diz."""
        ultima = "00"
        for fase in FASES:
            nomes = ARTEFATO_DA_FASE[fase]
            if any((self.p_proposta / n).is_file() for n in nomes):
                ultima = fase
        return ultima

    # -- campos do banco -----------------------------------------------------

    def cliente(self, fallback: str = "") -> str:
        return (
            self.manifest.get("cliente")
            or (self.orcamento.get("cliente") or {}).get("nome")
            or self.ficha.get("cliente")
            or fallback
            or "Cliente sem nome"
        )

    def financeiro(self) -> dict:
        """Total, tipo e o mensal da evolução.

        O total segue o modelo principal: numa proposta de implantação o número
        é o valor único, mesmo quando existe um bloco de evolução — ali ele é
        alternativa convertida, não contratação.
        """
        totais = self.orcamento.get("totais") or {}
        evolucao = self.orcamento.get("evolucao") or {}
        modelo = (self.orcamento.get("proposta") or {}).get("modelo_principal") or self.manifest.get(
            "modelo_principal"
        )

        dados = {
            "evolucao_mensal": totais.get("evolucao_mensal"),
            "evolucao_mensal_fmt": totais.get("evolucao_mensal_fmt"),
            "total_cru": None,
            "total_fmt": None,
            "total_tipo": None,
        }

        if modelo == "evolucao" and evolucao.get("aplicavel"):
            dados["total_cru"] = totais.get("evolucao_mensal")
            dados["total_fmt"] = totais.get("evolucao_mensal_fmt")
            dados["total_tipo"] = "mensal"
        elif totais.get("implantacao_total") is not None:
            dados["total_cru"] = totais.get("implantacao_total")
            dados["total_fmt"] = totais.get("implantacao_total_fmt")
            dados["total_tipo"] = "unico"
        return dados

    def campos(self) -> dict:
        """O dicionário pronto para virar linha de `propostas`, menos slug,
        workspace, origem e o que é decisão do humano (status comercial)."""
        orc = self.orcamento
        man = self.manifest
        ficha = self.ficha
        cli = orc.get("cliente") or {}
        prop = orc.get("proposta") or {}
        impl = orc.get("implantacao") or {}
        checkpoint = man.get("checkpoint_humano") or {}

        pdf = self.pdf()
        render_em = (man.get("saida") or {}).get("render_em")
        if not render_em and pdf:
            render_em = _iso_de_mtime(pdf)

        campos = {
            "cliente": self.cliente(),
            "razao_social": cli.get("razao_social") or ficha.get("razao_social"),
            "contato": cli.get("contato_nome") or ficha.get("contato"),
            "cargo_contato": ficha.get("cargo_do_contato"),
            "email": cli.get("contato_email") or ficha.get("e_mail"),
            "whatsapp": cli.get("contato_whatsapp") or ficha.get("whatsapp"),
            "validade": prop.get("validade") or _data_br_para_iso(ficha.get("validade")),
            "modelo": _auto_para_none(ficha.get("modelo_da_proposta"), cfg.MODELOS_PROPOSTA),
            "plataforma": _auto_para_none(ficha.get("plataforma"), cfg.PLATAFORMAS),
            "natureza": _auto_para_none(ficha.get("natureza"), cfg.NATUREZAS),
            "layout_do_cliente": (
                1 if (impl.get("design") or {}).get("fornecido_pelo_cliente") else
                _sim_nao(ficha.get("layout_fornecido_pelo_cliente"))
            ),
            "pacote_mensal_h": None,
            "reuniao_por": ficha.get("reuniao_conduzida_por"),
            "data_reuniao": _data_br_para_iso(ficha.get("data_da_reuniao")),
            "outros_presentes": ficha.get("outros_presentes"),
            "modelo_res": prop.get("modelo_principal")
            or man.get("modelo_principal")
            or self.escopo.get("modelo_principal"),
            "natureza_res": prop.get("natureza")
            or man.get("natureza")
            or self.escopo.get("natureza"),
            "plataforma_res": impl.get("plataforma")
            or man.get("plataforma")
            or self.escopo.get("plataforma"),
            "prazo_fmt": (impl.get("condicoes") or {}).get("prazo_fmt"),
            "hash_dados": orc.get("hash_entrada"),
            "hash_orcamento": hash_orcamento(orc) if orc else None,
            "precos_versao": orc.get("precos_versao"),
            "checkpoint_status": checkpoint.get("status") or "pendente",
            "checkpoint_em": checkpoint.get("aprovado_em"),
            "fase_atual": man.get("fase_atual") or self.fase_derivada(),
            "pdf_caminho": str(pdf.relative_to(self.base)) if pdf else None,
            "pdf_paginas": (man.get("saida") or {}).get("paginas")
            or (paginas_do_pdf(pdf) if pdf else None),
            "pdf_gerado_em": render_em,
        }
        campos.update(self.financeiro())

        # A plataforma do cadastro cai para a resolvida quando a ficha veio em
        # 'auto' — o comercial não precisa ver o campo vazio numa proposta pronta.
        if not campos["plataforma"]:
            campos["plataforma"] = campos["plataforma_res"]

        pacote = ficha.get("pacote_mensal_recomendado")
        if pacote and re.search(r"\d", pacote):
            campos["pacote_mensal_h"] = int(re.search(r"\d+", pacote).group())

        return campos

    def status_derivado(self) -> tuple[str, str | None]:
        """(status, erro_mensagem) a partir do que existe no disco."""
        if self.pdf():
            return "gerada", None
        if (self.p_proposta / "03-orcamento.json").is_file():
            return "aguardando_aprovacao", None
        if (self.p_proposta / "01-briefing.md").is_file():
            return "erro", "importada incompleta: parou antes do orçamento"
        return "rascunho", None

    def alertas(self) -> list[dict]:
        itens = []
        for a in self.orcamento.get("alertas") or []:
            if isinstance(a, dict):
                itens.append(
                    {
                        "codigo": a.get("codigo"),
                        "severidade": a.get("severidade") or "media",
                        "mensagem": a.get("mensagem") or "",
                    }
                )
        # O manifest guarda alertas como strings soltas; entram com severidade
        # média para não sumirem do painel.
        for a in self.manifest.get("alertas") or []:
            if isinstance(a, str) and a.strip():
                itens.append({"codigo": "MANIFEST", "severidade": "media", "mensagem": a})
        return itens

    def lacunas(self) -> list[str]:
        return [l for l in (self.orcamento.get("lacunas") or []) if isinstance(l, str)]

    def observacoes_do_checkpoint(self) -> list[str]:
        obs = (self.manifest.get("checkpoint_humano") or {}).get("observacoes") or []
        return [o for o in obs if isinstance(o, str) and o.strip()]
