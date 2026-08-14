"""Workspace por proposta, e a ponte dele com os singletons do repositório.

O repositório trabalha com `entrada/`, `proposta/` e `saida/` na raiz — uma
proposta por vez, porque `dados/` precisa continuar sendo fonte única de preço.
O app guarda cada proposta em `propostas/<slug>/` e **monta** a que vai rodar nos
singletons, uma de cada vez.

Montar é destrutivo por natureza: sobrescreve o que está na raiz. Por isso
`montar()` recolhe o que estiver montado antes de trocar, e nunca é chamado sem
o lock de execução em mãos.
"""

from __future__ import annotations

import json
import re
import shutil
import unicodedata
from pathlib import Path

import config as cfg

SUBPASTAS = ("entrada", "proposta", "saida")

# Só estes três arquivos de entrada pertencem a uma proposta. Os `.exemplo.md`
# são o modelo versionado do repositório e ficam de fora.
ENTRADAS = ("transcricao.md", "dados-cliente.md", "observacoes.md")


# -----------------------------------------------------------------------------
# Identidade
# -----------------------------------------------------------------------------


def slugificar(texto: str) -> str:
    sem_acento = "".join(
        c for c in unicodedata.normalize("NFKD", texto) if not unicodedata.combining(c)
    )
    return re.sub(r"[^a-z0-9]+", "-", sem_acento.lower()).strip("-") or "proposta"


def proximo_numero() -> int:
    maior = 0
    for p in cfg.WORKSPACES.glob("[0-9][0-9][0-9][0-9]-*"):
        try:
            maior = max(maior, int(p.name[:4]))
        except ValueError:
            continue
    return maior + 1


def novo_slug(cliente: str) -> str:
    return f"{proximo_numero():04d}-{slugificar(cliente)}"


def caminho(slug: str) -> Path:
    return cfg.WORKSPACES / slug


def criar(slug: str) -> Path:
    base = caminho(slug)
    for sub in (*SUBPASTAS, "logs"):
        (base / sub).mkdir(parents=True, exist_ok=True)
    (base / "saida" / "preview").mkdir(exist_ok=True)
    return base


def escrever_meta(slug: str, linha: dict) -> None:
    """Espelho legível da linha do banco — o workspace se explica sozinho mesmo
    se alguém só abrir a pasta."""
    (caminho(slug) / "meta.json").write_text(
        json.dumps(linha, ensure_ascii=False, indent=2, default=str) + "\n", "utf-8"
    )


# -----------------------------------------------------------------------------
# Estado do que está montado
# -----------------------------------------------------------------------------


def montado() -> str | None:
    try:
        return json.loads(cfg.ESTADO.read_text("utf-8")).get("montado")
    except (OSError, json.JSONDecodeError):
        return None


def _marcar_montado(slug: str | None) -> None:
    cfg.DADOS_APP.mkdir(parents=True, exist_ok=True)
    cfg.ESTADO.write_text(json.dumps({"montado": slug}, ensure_ascii=False) + "\n", "utf-8")


# -----------------------------------------------------------------------------
# Espelhamento
# -----------------------------------------------------------------------------


def _espelhar_pasta(origem: Path, destino: Path, apagar_extras: bool = True) -> None:
    """Deixa `destino` igual a `origem`. Sem origem, esvazia o destino.

    O apagar_extras existe porque montar tem que remover o artefato da proposta
    anterior: se a proposta A gerou `04-narrativa.md` e a B ainda não chegou lá,
    a B não pode encontrar o arquivo da A esperando por ela.
    """
    destino.mkdir(parents=True, exist_ok=True)

    if not origem.is_dir():
        if apagar_extras:
            for item in destino.iterdir():
                shutil.rmtree(item) if item.is_dir() else item.unlink()
        return

    esperados = set()
    for item in origem.rglob("*"):
        rel = item.relative_to(origem)
        esperados.add(rel)
        alvo = destino / rel
        if item.is_dir():
            alvo.mkdir(parents=True, exist_ok=True)
        else:
            alvo.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(item, alvo)

    if not apagar_extras:
        return
    # De baixo para cima, para esvaziar as pastas antes de removê-las.
    for item in sorted(destino.rglob("*"), key=lambda p: len(p.parts), reverse=True):
        if item.relative_to(destino) not in esperados:
            shutil.rmtree(item, ignore_errors=True) if item.is_dir() else item.unlink(missing_ok=True)


def _espelhar_entrada(origem: Path, destino: Path) -> None:
    """Só os três arquivos de entrada, preservando os `.exemplo.md` do repo."""
    destino.mkdir(parents=True, exist_ok=True)
    for nome in ENTRADAS:
        o, d = origem / nome, destino / nome
        if o.is_file():
            shutil.copy2(o, d)
        else:
            d.unlink(missing_ok=True)


# -----------------------------------------------------------------------------
# Montar e recolher
# -----------------------------------------------------------------------------


def recolher() -> str | None:
    """Traz de volta para o workspace o que o pipeline escreveu nos singletons.

    Chamado ao fim de cada fase (é barato — dezenas de KB) e obrigatoriamente no
    `finally` da execução, para que uma falha no meio não perca o trabalho já
    feito.
    """
    slug = montado()
    if not slug:
        return None

    base = caminho(slug)
    if not base.is_dir():
        # O workspace sumiu debaixo dos pés: não há para onde recolher, e
        # insistir sobrescreveria o singleton com nada.
        _marcar_montado(None)
        return None

    _espelhar_entrada(cfg.SINGLETON_ENTRADA, base / "entrada")
    _espelhar_pasta(cfg.SINGLETON_PROPOSTA, base / "proposta")
    _espelhar_pasta(cfg.SINGLETON_SAIDA, base / "saida")
    return slug


def limpar_singletons() -> None:
    """Esvazia `entrada/`, `proposta/` e `saida/` e marca que nada está montado.

    Usado quando a proposta montada é apagada de vez: deixar os arquivos dela na
    raiz depois que ela deixou de existir confundiria tanto o app quanto quem
    abrir o repositório no terminal.
    """
    for nome in ENTRADAS:
        (cfg.SINGLETON_ENTRADA / nome).unlink(missing_ok=True)
    _espelhar_pasta(cfg.SINGLETON_PROPOSTA.parent / "__inexistente__", cfg.SINGLETON_PROPOSTA)
    _espelhar_pasta(cfg.SINGLETON_SAIDA.parent / "__inexistente__", cfg.SINGLETON_SAIDA)
    _marcar_montado(None)


def montar(slug: str) -> Path:
    """Coloca a proposta nos singletons. Recolhe a anterior antes, se houver."""
    base = caminho(slug)
    if not base.is_dir():
        raise FileNotFoundError(f"workspace inexistente: {base}")

    atual = montado()
    if atual == slug:
        # Já está lá. Reespelhar mesmo assim custa pouco e protege contra
        # edição manual feita na raiz enquanto o app estava parado.
        _espelhar_entrada(base / "entrada", cfg.SINGLETON_ENTRADA)
        _espelhar_pasta(base / "proposta", cfg.SINGLETON_PROPOSTA)
        _espelhar_pasta(base / "saida", cfg.SINGLETON_SAIDA)
        return base

    if atual:
        recolher()

    _espelhar_entrada(base / "entrada", cfg.SINGLETON_ENTRADA)
    _espelhar_pasta(base / "proposta", cfg.SINGLETON_PROPOSTA)
    _espelhar_pasta(base / "saida", cfg.SINGLETON_SAIDA)
    _marcar_montado(slug)
    return base


# -----------------------------------------------------------------------------
# Consulta
# -----------------------------------------------------------------------------


def artefatos(slug: str) -> list[dict]:
    """O que existe no workspace, para a tela de detalhe.

    Sempre devolve a lista inteira, com `existe: false` no que faltar — proposta
    importada costuma ter buraco, e a UI precisa mostrar o buraco em vez de
    fingir que a fase não aconteceu.
    """
    base = caminho(slug)
    itens = []

    for nome in sorted(cfg.ARTEFATOS_SERVIVEIS):
        alvo = base / "proposta" / nome
        itens.append(
            {
                "nome": nome,
                "onde": "proposta",
                "existe": alvo.is_file(),
                "bytes": alvo.stat().st_size if alvo.is_file() else None,
            }
        )

    for nome in sorted(cfg.ARTEFATOS_SAIDA):
        alvo = base / "saida" / nome
        itens.append(
            {
                "nome": nome,
                "onde": "saida",
                "existe": alvo.is_file(),
                "bytes": alvo.stat().st_size if alvo.is_file() else None,
            }
        )

    return itens


def resolver_artefato(slug: str, nome: str) -> Path:
    """Caminho de um artefato, com as duas defesas contra travessia: whitelist
    de nomes e confinamento ao workspace."""
    if nome in cfg.ARTEFATOS_SERVIVEIS:
        alvo = caminho(slug) / "proposta" / nome
    elif nome in cfg.ARTEFATOS_SAIDA:
        alvo = caminho(slug) / "saida" / nome
    else:
        raise ValueError(f"artefato não servível: {nome}")

    base = caminho(slug).resolve()
    alvo = alvo.resolve()
    if not alvo.is_relative_to(base):
        raise ValueError("caminho fora do workspace")
    return alvo


def previews(slug: str) -> list[str]:
    pasta = caminho(slug) / "saida" / "preview"
    if not pasta.is_dir():
        return []
    return sorted(p.name for p in pasta.glob("pagina-*.png"))
