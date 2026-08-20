#!/usr/bin/env python3
"""Parseia o JS do app como **módulo ES**, que é como o browser carrega.

Existe por um estrago concreto: uma `const` declarada duas vezes dentro da mesma
função derrubou a tela de aprovação inteira, de todas as propostas, e foi para
produção porque `node --check` aprovou o arquivo.

`node --check` trata o arquivo como script CommonJS. Nesse modo ele não acusa
redeclaração; carregado como módulo, o mesmo arquivo estoura com
`Identifier 'painel' has already been declared` antes de executar uma linha.
A verificação que eu rodava não era a verificação que importava.

Uso:
    python3 scripts/checar_js.py            # tudo em app/static/js
    python3 scripts/checar_js.py a.js b.js
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
JS = RAIZ / "app" / "static" / "js"

VERIFICADOR = """
const vm = require('vm');
const fs = require('fs');
const alvos = JSON.parse(process.argv[1]);
let falhou = 0;
for (const caminho of alvos) {
  try {
    new vm.SourceTextModule(fs.readFileSync(caminho, 'utf8'), { identifier: caminho });
  } catch (e) {
    console.log(`FALHA ${caminho}: ${e.message}`);
    falhou = 1;
  }
}
process.exit(falhou);
"""


def main() -> int:
    alvos = [Path(a) for a in sys.argv[1:]] or sorted(JS.rglob("*.js"))
    if not alvos:
        print("nenhum arquivo .js encontrado", file=sys.stderr)
        return 1

    r = subprocess.run(
        ["node", "--experimental-vm-modules", "-e", VERIFICADOR,
         json.dumps([str(a) for a in alvos])],
        capture_output=True, text=True, cwd=RAIZ,
    )
    saida = "\n".join(l for l in (r.stdout + r.stderr).splitlines()
                      if l.strip() and "Warning" not in l and "trace-warnings" not in l)
    if saida:
        print(saida)
    if r.returncode:
        return 1

    print(f"  {len(alvos)} arquivo(s) parseiam como módulo ES.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
