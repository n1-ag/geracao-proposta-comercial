"""Conversão entre o cadastro do app e `entrada/dados-cliente.md`.

O arquivo markdown continua sendo o formato de entrada do pipeline — o app não
inventa um formato próprio, ele preenche o mesmo que uma pessoa preencheria à
mão. `precificar.ler_ficha` é quem lê do outro lado, e o teste de aceitação
deste módulo é simples: `ler_ficha(escrever(d))` tem que devolver `d`.
"""

from __future__ import annotations

import re
from datetime import date, datetime, timedelta
from pathlib import Path

import config as cfg

# (chave no app, rótulo no markdown, seção). A ordem é a do arquivo gerado.
CAMPOS = [
    ("cliente", "Cliente", "identificacao"),
    ("razao_social", "Razão social", "identificacao"),
    ("contato", "Contato", "identificacao"),
    ("cargo_contato", "Cargo do contato", "identificacao"),
    ("email", "E-mail", "identificacao"),
    ("whatsapp", "WhatsApp", "identificacao"),
    ("validade", "Validade", "identificacao"),
    ("modelo", "Modelo da proposta", "enquadramento"),
    ("plataforma", "Plataforma", "enquadramento"),
    ("natureza", "Natureza", "enquadramento"),
    ("layout_do_cliente", "Layout fornecido pelo cliente", "enquadramento"),
    ("pacote_mensal_h", "Pacote mensal recomendado", "enquadramento"),
    ("reuniao_por", "Reunião conduzida por", "observacoes"),
    ("data_reuniao", "Data da reunião", "observacoes"),
    ("outros_presentes", "Outros presentes", "observacoes"),
]

# Campos que o comercial pode deixar no automático. Vão para o arquivo como
# `auto`, que é a convenção documentada em dados-cliente.exemplo.md: o agente
# infere da transcrição e mostra os sinais que usou.
AUTOMATIZAVEIS = {"modelo", "plataforma", "natureza"}


def _iso_para_br(iso: str | None) -> str:
    if not iso:
        return ""
    try:
        return datetime.strptime(iso[:10], "%Y-%m-%d").strftime("%d/%m/%Y")
    except ValueError:
        return iso


def _br_para_iso(br: str | None) -> str | None:
    if not br:
        return None
    casou = re.match(r"^\s*(\d{1,2})/(\d{1,2})/(\d{4})\s*$", br)
    if casou:
        d, m, a = casou.groups()
        return f"{a}-{int(m):02d}-{int(d):02d}"
    return br if re.match(r"^\d{4}-\d{2}-\d{2}$", br.strip()) else None


def validade_padrao(dias: int = 45) -> str:
    return (date.today() + timedelta(days=dias)).isoformat()


def _valor_markdown(chave: str, dados: dict) -> str:
    """Como o campo aparece no arquivo. String vazia = campo em branco, que
    `ler_ficha` descarta e a proposta declara como lacuna."""
    bruto = dados.get(chave)

    if chave in AUTOMATIZAVEIS:
        return (bruto or "auto").strip()

    if chave == "layout_do_cliente":
        if bruto in (None, "", "auto"):
            return ""
        return "sim" if bruto in (1, True, "1", "sim", "true") else "nao"

    if chave == "validade":
        return _iso_para_br(bruto)

    if chave == "data_reuniao":
        return _iso_para_br(bruto)

    if chave == "pacote_mensal_h":
        return f"{bruto} horas" if bruto else ""

    return str(bruto).strip() if bruto not in (None, "") else ""


CABECALHO = """# Ficha do cliente

> Gerada pelo app N1 Propostas. Campo em branco vira lacuna declarada na
> proposta — é de propósito: uma lacuna visível custa uma pergunta, um dado
> errado custa a conta.
"""


def escrever(dados: dict, destino: Path) -> Path:
    """Grava `entrada/dados-cliente.md` no formato que o pipeline espera."""
    secoes = {
        "identificacao": ["", "## Identificação", ""],
        "enquadramento": ["", "## Enquadramento comercial", ""],
        "observacoes": ["", "## Observações", ""],
    }

    for chave, rotulo, secao in CAMPOS:
        secoes[secao].append(f"- **{rotulo}:** {_valor_markdown(chave, dados)}".rstrip())

    linhas = [CABECALHO]
    for secao in ("identificacao", "enquadramento", "observacoes"):
        linhas.extend(secoes[secao])

    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text("\n".join(linhas).rstrip() + "\n", "utf-8")
    return destino


def ler(origem: Path) -> dict:
    """O caminho inverso: markdown → dicionário do cadastro."""
    import sys

    sys.path.insert(0, str(cfg.SCRIPTS))
    from precificar import ler_ficha

    bruto = ler_ficha(origem) or {}
    if not bruto:
        return {}

    def limpo(valor: str | None) -> str | None:
        """'auto' no arquivo significa 'ninguém decidiu' — no banco isso é NULL."""
        if not valor or valor.strip().lower() == "auto":
            return None
        return valor.strip()

    pacote = bruto.get("pacote_mensal_recomendado")
    horas = int(re.search(r"\d+", pacote).group()) if pacote and re.search(r"\d", pacote) else None

    layout = (bruto.get("layout_fornecido_pelo_cliente") or "").strip().lower()

    return {
        "cliente": bruto.get("cliente"),
        "razao_social": bruto.get("razao_social"),
        "contato": bruto.get("contato"),
        "cargo_contato": bruto.get("cargo_do_contato"),
        "email": bruto.get("e_mail"),
        "whatsapp": bruto.get("whatsapp"),
        "validade": _br_para_iso(bruto.get("validade")),
        "modelo": limpo(bruto.get("modelo_da_proposta")),
        "plataforma": limpo(bruto.get("plataforma")),
        "natureza": limpo(bruto.get("natureza")),
        "layout_do_cliente": 1 if layout == "sim" else (0 if layout in ("nao", "não") else None),
        "pacote_mensal_h": horas,
        "reuniao_por": bruto.get("reuniao_conduzida_por"),
        "data_reuniao": _br_para_iso(bruto.get("data_da_reuniao")),
        "outros_presentes": bruto.get("outros_presentes"),
    }


# -----------------------------------------------------------------------------
# Observações do comercial
# -----------------------------------------------------------------------------

CABECALHO_OBS = """# Observações do comercial

> Escritas por quem conduziu a reunião, no cadastro da proposta. **Analise junto
> com a transcrição**: elas compõem o cenário geral, corrigem atribuição de fala,
> explicam o que ficou implícito e sinalizam o que o cliente não disse.
>
> Numere cada afirmação relevante como `O01`, `O02`, … — o namespace `O` existe
> para separar interpretação do comercial de citação literal do cliente (`E##`).
> Quando observação e transcrição divergirem, **prevalece a transcrição**, e a
> divergência vira lacuna declarada.

---

"""


def escrever_observacoes(texto: str, destino: Path) -> Path | None:
    """Grava `entrada/observacoes.md`. Sem texto, remove o arquivo — a ausência
    é o sinal de que não há observação, e um arquivo vazio confundiria o agente."""
    texto = (texto or "").strip()
    destino.parent.mkdir(parents=True, exist_ok=True)

    if not texto:
        destino.unlink(missing_ok=True)
        return None

    destino.write_text(CABECALHO_OBS + texto + "\n", "utf-8")
    return destino


def ler_observacoes(origem: Path) -> str:
    """Devolve só o texto do comercial, sem o cabeçalho de instruções."""
    try:
        conteudo = origem.read_text("utf-8")
    except OSError:
        return ""
    _, marcador, corpo = conteudo.partition("\n---\n")
    return (corpo if marcador else conteudo).strip()
