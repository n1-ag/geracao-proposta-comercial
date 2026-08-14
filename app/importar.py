#!/usr/bin/env python3
"""Traz para o app as propostas feitas antes dele existir.

    python3 app/importar.py [--dry-run] [--refazer-copia]

Varre `arquivo/*/` (histórico do fluxo de terminal) e a proposta viva na raiz
do repositório, copia cada uma para `propostas/<NNNN>-<slug>/` e registra no
banco.

É idempotente: a chave é a pasta de origem. Rodar de novo atualiza os metadados
e NÃO mexe no que é decisão humana — status comercial, datas de envio e a marca
de arquivada continuam como o comercial deixou.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
import unicodedata
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import artefatos  # noqa: E402
import config as cfg  # noqa: E402
import db  # noqa: E402

# Campos que o humano controla dentro do app. O import nunca os sobrescreve.
NAO_SOBRESCREVER = {"status_comercial", "enviada_em", "decidida_em", "arquivada"}


def brl(valor) -> str:
    """Formata em real sem depender de locale, como faz o precificar.py."""
    inteiro, _, centavos = f"{(valor or 0):.2f}".partition(".")
    milhar = f"{int(inteiro):,}".replace(",", ".")
    return f"R$ {milhar},{centavos}"


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


def copiar_workspace(origem: Path, destino: Path) -> None:
    """Espelha entrada/, proposta/ e saida/. `dados/` nunca é copiado — ele
    continua sendo fonte única de preço na raiz."""
    destino.mkdir(parents=True, exist_ok=True)

    # De entrada/ só interessam os insumos reais desta proposta. Os `.exemplo.md`
    # são o modelo versionado do repositório e não têm por que ser duplicados em
    # cada workspace.
    (destino / "entrada").mkdir(exist_ok=True)
    for nome in ("transcricao.md", "dados-cliente.md", "observacoes.md"):
        arquivo = origem / "entrada" / nome
        if arquivo.is_file():
            shutil.copy2(arquivo, destino / "entrada" / nome)

    for sub in ("proposta", "saida"):
        o = origem / sub
        if o.is_dir():
            shutil.copytree(o, destino / sub, dirs_exist_ok=True)
        else:
            (destino / sub).mkdir(exist_ok=True)

    (destino / "logs").mkdir(exist_ok=True)


def escrever_meta(workspace: Path, linha: dict) -> None:
    """Espelho legível da linha do banco, para o workspace se explicar sozinho."""
    (workspace / "meta.json").write_text(
        json.dumps(linha, ensure_ascii=False, indent=2, default=str) + "\n", "utf-8"
    )


# -----------------------------------------------------------------------------
# Descoberta
# -----------------------------------------------------------------------------


def candidatas() -> list[tuple[Path, str]]:
    """(pasta, rótulo). A raiz do repo entra por último.

    Uma pasta em `arquivo/` não vira proposta `arquivada`: no fluxo de terminal
    "arquivar" significa "terminou", e proposta terminada é exatamente o
    histórico que o funil precisa contar. `arquivada` fica reservado para o
    descarte feito dentro do app.
    """
    achadas: list[tuple[Path, str]] = []

    if cfg.ARQUIVO.is_dir():
        for pasta in sorted(cfg.ARQUIVO.iterdir()):
            if pasta.is_dir():
                achadas.append((pasta, f"arquivo/{pasta.name}"))

    if (cfg.SINGLETON_PROPOSTA / "manifest.json").is_file() or (
        cfg.SINGLETON_PROPOSTA / "03-orcamento.json"
    ).is_file():
        achadas.append((cfg.RAIZ, "proposta em andamento (raiz)"))

    return achadas


# -----------------------------------------------------------------------------
# Importação de uma pasta
# -----------------------------------------------------------------------------


def importar_uma(pasta: Path, rotulo: str, opts) -> dict:
    resultado = {"rotulo": rotulo, "acao": None, "avisos": [], "slug": None, "id": None}

    retrato = artefatos.Retrato(pasta)
    if not retrato.existe():
        resultado["acao"] = "pulada"
        resultado["avisos"].append("sem manifest.json nem 03-orcamento.json")
        return resultado

    origem_ref = str(pasta.resolve())
    existente = db.um("SELECT * FROM propostas WHERE origem_ref = ?", (origem_ref,))

    nome_pasta = pasta.name if pasta != cfg.RAIZ else ""
    fallback = re.sub(r"-\d{4}-\d{2}-\d{2}$", "", nome_pasta).replace("_", " ").strip()
    cliente = retrato.cliente(fallback)

    campos = retrato.campos()
    campos["cliente"] = cliente
    status, erro = retrato.status_derivado()
    campos["status"] = status
    campos["erro_mensagem"] = erro
    campos["atualizado_em"] = db.agora()
    campos["criado_em"] = retrato.manifest.get("criado_em") or db.agora()

    if opts.dry_run:
        resultado["acao"] = "atualizaria" if existente else "criaria"
        resultado["slug"] = existente["slug"] if existente else f"NNNN-{slugificar(cliente)}"
        resultado["campos"] = campos
        resultado["avisos"] = [f"artefato ausente — {a}" for a in retrato.artefatos_ausentes()]
        return resultado

    with db.transacao():
        if existente:
            proposta_id = existente["id"]
            slug = existente["slug"]
            workspace = cfg.RAIZ / existente["workspace"]
            db.atualizar(
                "propostas", proposta_id, {k: v for k, v in campos.items() if k not in NAO_SOBRESCREVER}
            )
            resultado["acao"] = "atualizada"
        else:
            slug = f"{proximo_numero():04d}-{slugificar(cliente)}"
            workspace = cfg.WORKSPACES / slug
            proposta_id = db.inserir(
                "propostas",
                {
                    **campos,
                    "slug": slug,
                    "workspace": f"propostas/{slug}",
                    "origem": "importado",
                    "origem_ref": origem_ref,
                },
            )
            db.registrar_mudanca(proposta_id, "status", None, campos["status"], "importada")
            resultado["acao"] = "criada"

        # Alertas e lacunas têm escopo de proposta, não de linha: refazer o
        # conjunto inteiro é mais simples e não deixa órfão de uma versão antiga.
        db.executar("DELETE FROM alertas WHERE proposta_id = ?", (proposta_id,))
        db.executar("DELETE FROM lacunas WHERE proposta_id = ?", (proposta_id,))
        for a in retrato.alertas():
            db.inserir(
                "alertas",
                {**a, "proposta_id": proposta_id,
                 "hash_orcamento": campos.get("hash_orcamento"), "criado_em": db.agora()},
            )
        for texto in retrato.lacunas():
            db.inserir(
                "lacunas",
                {"proposta_id": proposta_id, "texto": texto,
                 "hash_orcamento": campos.get("hash_orcamento"), "criado_em": db.agora()},
            )

        # As observações do checkpoint são o histórico de negociação: cada uma
        # foi um pedido de ajuste que alguém fez e que já foi aplicado.
        if not db.valor("SELECT COUNT(*) FROM ajustes WHERE proposta_id = ?", (proposta_id,), 0):
            aprovado_em = campos.get("checkpoint_em")
            for i, obs in enumerate(retrato.observacoes_do_checkpoint(), start=1):
                db.inserir(
                    "ajustes",
                    {
                        "proposta_id": proposta_id,
                        "ordem": i,
                        "texto": obs,
                        "sobre_hash": campos.get("hash_orcamento"),
                        "sobre_total_fmt": campos.get("total_fmt"),
                        "criado_em": aprovado_em or db.agora(),
                        "aplicado_em": aprovado_em or db.agora(),
                    },
                )

        for ausente in retrato.artefatos_ausentes():
            aviso = f"{ausente} — declarado no manifest e ausente no disco"
            resultado["avisos"].append(aviso)
            db.evento(proposta_id, "importacao_aviso", aviso)

        # O hash do checkpoint não bate com o do orçamento? É o sintoma de que
        # `Dados.hash()` só cobre os TOML de preço: o gate do fluxo de terminal
        # não percebe mudança de escopo. Fica registrado, não bloqueia.
        gravado = ((retrato.manifest.get("checkpoint_humano") or {}).get("aprovado_sobre") or {}).get(
            "orcamento_hash"
        )
        atual = retrato.orcamento.get("hash_entrada")
        if gravado and atual and gravado != atual:
            aviso = (
                f"o checkpoint foi aprovado sobre {gravado} e o orçamento traz {atual}; "
                f"os totais conferem, então a aprovação foi mantida"
            )
            resultado["avisos"].append(aviso)
            db.evento(proposta_id, "hash_divergente", aviso)

    resultado["id"] = proposta_id
    resultado["slug"] = slug

    if not workspace.exists() or opts.refazer_copia:
        copiar_workspace(pasta, workspace)
    else:
        resultado["avisos"].append("workspace já existia — arquivos não recopiados")

    linha = db.um("SELECT * FROM propostas WHERE id = ?", (proposta_id,))
    escrever_meta(workspace, linha)

    # A proposta viva já está nos singletons; registrar isso evita que a
    # primeira execução do app atropele o trabalho que está lá.
    if pasta == cfg.RAIZ:
        cfg.ESTADO.write_text(json.dumps({"montado": slug}, ensure_ascii=False) + "\n", "utf-8")
        resultado["avisos"].append(f"marcada como montada nos singletons (estado.json)")

    return resultado


# -----------------------------------------------------------------------------
# CLI
# -----------------------------------------------------------------------------


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dry-run", action="store_true", help="mostra o que faria, sem tocar em nada")
    ap.add_argument(
        "--refazer-copia",
        action="store_true",
        help="recopia os arquivos mesmo se o workspace já existir (descarta edições feitas no app)",
    )
    opts = ap.parse_args()

    if not opts.dry_run:
        cfg.DADOS_APP.mkdir(parents=True, exist_ok=True)
        cfg.WORKSPACES.mkdir(parents=True, exist_ok=True)
    db.migrar()

    achadas = candidatas()
    if not achadas:
        print("nada para importar: arquivo/ está vazio e não há proposta em andamento.")
        return 0

    print(f"{len(achadas)} pasta(s) candidata(s)\n")
    resultados = [importar_uma(p, rot, opts) for p, rot in achadas]

    for r in resultados:
        marca = {"criada": "+", "atualizada": "~", "criaria": "+", "atualizaria": "~", "pulada": "·"}
        print(f" {marca.get(r['acao'], '?')} {r['rotulo']}")
        if r["slug"]:
            campos = r.get("campos")
            if campos:
                print(f"     {campos['cliente']} · {campos.get('plataforma_res') or '?'} · "
                      f"{campos.get('total_fmt') or 'sem valor'} · {campos['status']}")
            else:
                linha = db.um("SELECT * FROM propostas WHERE id = ?", (r["id"],))
                print(f"     #{linha['id']} {linha['slug']} · {linha['total_fmt'] or 'sem valor'} "
                      f"· {linha['status']}")
        for aviso in r["avisos"]:
            print(f"     ! {aviso}")
        print()

    if opts.dry_run:
        print("(--dry-run: nada foi escrito)")
        return 0

    total = db.valor("SELECT COUNT(*) FROM propostas", (), 0)
    soma = db.valor("SELECT SUM(valor_anualizado) FROM propostas WHERE arquivada = 0", (), 0)
    print(f"banco: {total} proposta(s); {brl(soma)} em carteira")
    print(f"\nAs pastas de origem NÃO foram apagadas. Confira o resultado no app antes de\n"
          f"remover `arquivo/` à mão.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
