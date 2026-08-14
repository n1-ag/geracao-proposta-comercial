#!/usr/bin/env python3
"""
arquivar.py — encerra a proposta atual e deixa o repositório pronto para a próxima.

`proposta/` e `saida/` são pastas de trabalho de UMA proposta por vez. Isso é
proposital: `dados/` precisa ser fonte única de preço, e duplicar o repositório
por cliente faz a tabela de preços divergir em silêncio. O que se arquiva é o
resultado, não o boilerplate.

    python3 scripts/arquivar.py            # arquiva a proposta atual
    python3 scripts/arquivar.py --listar   # mostra o que já foi arquivado
    python3 scripts/arquivar.py --limpar   # descarta sem arquivar (pede confirmação)
    python3 scripts/arquivar.py --reset    # zera tudo, inclusive entrada/, do zero

O destino é `arquivo/<cliente>-<data>/`, que fica fora do git: é dado de cliente,
não pertence ao boilerplate.

Saída: 0 ok · 1 nada a arquivar · 2 destino já existe
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
import unicodedata
from datetime import date
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
TRABALHO = ("proposta", "saida")
ARQUIVO = RAIZ / "arquivo"


def slug(texto: str) -> str:
    sem_acento = "".join(c for c in unicodedata.normalize("NFKD", texto)
                         if not unicodedata.combining(c))
    return re.sub(r"_+", "_", re.sub(r"[^A-Za-z0-9]+", "_", sem_acento)).strip("_") or "sem-cliente"


def le_manifest() -> dict:
    m = RAIZ / "proposta" / "manifest.json"
    if m.is_file():
        try:
            return json.loads(m.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            pass
    return {}


def tem_trabalho() -> bool:
    return any((RAIZ / d).is_dir() and any((RAIZ / d).iterdir()) for d in TRABALHO)


def listar() -> int:
    if not ARQUIVO.is_dir() or not any(ARQUIVO.iterdir()):
        print("Nenhuma proposta arquivada ainda.")
        return 0
    print(f"{'Proposta':<40} {'Modelo':<13} {'Valor':>14}  PDF")
    for d in sorted(ARQUIVO.iterdir()):
        if not d.is_dir():
            continue
        orc, modelo, valor = d / "proposta" / "03-orcamento.json", "—", "—"
        if orc.is_file():
            try:
                o = json.loads(orc.read_text(encoding="utf-8"))
                modelo = o["proposta"]["modelo_principal"]
                valor = (o["totais"].get("implantacao_total_fmt")
                         or o["totais"].get("evolucao_mensal_fmt", "—"))
                if modelo == "evolucao":
                    valor += "/mês"
            except Exception:
                pass
        pdfs = list((d / "saida").glob("*.pdf")) if (d / "saida").is_dir() else []
        print(f"{d.name:<40} {modelo:<13} {valor:>14}  {pdfs[0].name if pdfs else '—'}")
    return 0


def zera_entrada() -> list:
    """Devolve entrada/ ao estado de partida: cópias limpas dos exemplos."""
    tocados = []
    for nome in ("transcricao", "dados-cliente"):
        alvo = RAIZ / "entrada" / f"{nome}.md"
        exemplo = RAIZ / "entrada" / f"{nome}.exemplo.md"
        if exemplo.is_file():
            shutil.copy2(exemplo, alvo)
            tocados.append(alvo.name)
        elif alvo.is_file():
            alvo.unlink()
            tocados.append(alvo.name)
    return tocados


def main() -> int:
    ap = argparse.ArgumentParser(description="Encerra a proposta atual.")
    ap.add_argument("--listar", action="store_true")
    ap.add_argument("--limpar", action="store_true", help="descarta sem arquivar")
    ap.add_argument("--reset", action="store_true",
                    help="zera tudo, inclusive entrada/, voltando ao estado de instalação")
    ap.add_argument("--nome", help="nome da pasta de destino (default: <cliente>-<data>)")
    ap.add_argument("--sim", action="store_true", help="não pergunta nada")
    args = ap.parse_args()

    if args.listar:
        return listar()

    # --reset é o "do zero": descarta o trabalho e devolve entrada/ ao exemplo.
    # Não toca em dados/, specs/, templates/ nem arquivo/ — o boilerplate e o
    # histórico não são estado de proposta.
    if args.reset:
        man = le_manifest()
        cliente = man.get("cliente")
        if tem_trabalho():
            print(f"Proposta em andamento: {cliente or '(sem manifest)'}")
        arquivadas = len([d for d in ARQUIVO.iterdir() if d.is_dir()]) if ARQUIVO.is_dir() else 0
        print(f"Isto DESCARTA a proposta atual e devolve entrada/ ao exemplo.")
        print(f"Preservados: dados/, specs/, templates/ e as {arquivadas} proposta(s) em arquivo/.")
        if not args.sim:
            if input("Digite RESET para confirmar: ").strip() != "RESET":
                print("Cancelado.")
                return 0
        for d in TRABALHO:
            shutil.rmtree(RAIZ / d, ignore_errors=True)
        tocados = zera_entrada()
        print(f"\nLimpo. entrada/ restaurada ({', '.join(tocados) or 'nada a restaurar'}).")
        print("Cole a transcrição do novo cliente, preencha a ficha e rode /proposta")
        return 0

    if not tem_trabalho():
        print("Nada a arquivar: `proposta/` e `saida/` já estão vazias.")
        return 1

    man = le_manifest()
    cliente = man.get("cliente", "sem-cliente")
    fase = man.get("fase_atual", "?")
    checkpoint = man.get("checkpoint_humano", {}).get("status", "?")
    pdfs = sorted((RAIZ / "saida").glob("*.pdf")) if (RAIZ / "saida").is_dir() else []

    print(f"Proposta atual: {cliente}  ·  fase {fase}  ·  checkpoint {checkpoint}")
    print(f"PDF gerado: {pdfs[0].name if pdfs else 'nenhum'}")

    if args.limpar:
        if not args.sim:
            print("\nIsto DESCARTA a proposta sem guardar cópia.")
            if input("Digite o nome do cliente para confirmar: ").strip() != cliente:
                print("Cancelado.")
                return 0
        for d in TRABALHO:
            shutil.rmtree(RAIZ / d, ignore_errors=True)
        print("Descartada. Pronto para a próxima proposta.")
        return 0

    destino = ARQUIVO / (args.nome or f"{slug(cliente)}-{date.today().isoformat()}")
    if destino.exists():
        print(f"erro: {destino} já existe. Use --nome para diferenciar.", file=sys.stderr)
        return 2

    destino.mkdir(parents=True)
    for d in TRABALHO:
        origem = RAIZ / d
        if origem.is_dir():
            shutil.move(str(origem), str(destino / d))

    # A transcrição, a ficha e as observações do comercial são o insumo: sem
    # elas o arquivo não se explica.
    entradas = destino / "entrada"
    for nome in ("transcricao.md", "dados-cliente.md", "observacoes.md"):
        f = RAIZ / "entrada" / nome
        if f.is_file():
            entradas.mkdir(exist_ok=True)
            shutil.copy2(f, entradas / nome)

    print(f"\nArquivada em  {destino.relative_to(RAIZ)}/")
    print("Próxima proposta: substitua entrada/transcricao.md e entrada/dados-cliente.md, "
          "depois rode /proposta")
    return 0


if __name__ == "__main__":
    sys.exit(main())
