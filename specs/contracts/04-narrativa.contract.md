# Contrato 04 — Narrativa

**Entrada:** `01-briefing.md`, `02-escopo.md`, `03-orcamento.md`, `dados/perfil-n1.toml`, `dados/biblioteca-textos.md`
**Saída:** `proposta/04-narrativa.md`
**Executor:** agente `redator-proposta`
**Pré-condição:** `manifest.checkpoint_humano.status == "aprovado"`.

Uma seção por bloco do PDF. **Cada uma com limite de caracteres declarado** — o
limite não é sugestão: estourar provoca transbordo e o render recusa o PDF.

## Seções e limites

### `## CAPA`
- `titulo`: até 3 linhas de no máximo 26 caracteres cada (use `|` para separar)
- `subtitulo`: 180–260 caracteres
- `factbar`: 3 pares rótulo/valor; rótulo ≤ 10 caracteres

### `## 01 APRESENTACAO`
- 3 parágrafos de 280–420 caracteres cada
- `stats`: 4 cartões; label ≤ 22 caracteres em até 2 linhas
- `porque`: 4 a 5 itens de `perfil-n1.toml`, verbatim, escolhidos por pertinência
- `cobertura`: 5 a 6 itens de até 52 caracteres

### `## 02 ESCOPO`
- `intro`: até 260 caracteres
- **evolução:** 5 frentes; título ≤ 48 caracteres, texto 200–330
- **implantação:** `incluido` (6 itens ≤ 52 car.) + a tabela de módulos, cuja
  sub-nota por linha tem até 68 caracteres + `nota` de até 200

### `## 03 CONDUCAO`
- `intro`: até 240 caracteres
- 5 etapas de fluxo; título ≤ 16 caracteres, texto ≤ 46
- 1 card de destaque (até 700 caracteres), 2 cards em coluna (4 itens cada),
  1 card de rodapé (até 560 caracteres)

### `## 04 INVESTIMENTO`
- `price_tag` ≤ 24 caracteres · `price_nota` 260–420 caracteres
- `condicoes`: 5 a 7 linhas; rótulo ≤ 34 car., sub-nota ≤ 68
- `inclui`: 5 a 6 itens de até 62 caracteres
- `complementares`: 1 card + nota de até 200 caracteres

### `## 04B ALTERNATIVA` *(só implantação, e só se `evolucao.aplicavel`)*
- `intro` 300–460 caracteres · `price_nota` 200–320
- tabela de 5 a 6 linhas · 1 card de comparação (até 620 caracteres)

### `## 05 PREMISSAS`
- 5 premissas de até 220 caracteres
- bloco de transição/migração (condicional) · card de janela (condicional)
- `nao_contemplado`: 4 itens de até 130 caracteres

### `## FECHAMENTO`
- `headline`: até 2 linhas de 30 caracteres
- `texto`: 150–230 caracteres
- 3 passos: título ≤ 26 caracteres, texto ≤ 110

## Regras

1. **Nenhum dígito de dinheiro, hora ou percentual.** Use tokens
   `«orc:implantacao.total_fmt»`, `«orc:evolucao.pacote_horas_fmt»`. Nem por
   extenso ("cerca de trinta horas") — `auditar.py numeros` reprova.
2. **`[E##]` ao lado de toda afirmação sobre o cliente.** As referências ficam no
   markdown da narrativa; o montador as remove ao gerar o HTML.
3. **Frases sobre a N1 são verbatim** de `perfil-n1.toml` e
   `biblioteca-textos.md`. Escolher qual usar é seu; reescrever não.
4. Não fale mal do fornecedor atual. Descreva o sintoma, não a culpa.
5. Siga `steering/tom-de-voz.md`.
6. Se um limite não couber com o conteúdo necessário, **avise no fim do
   artefato** em vez de estourar em silêncio.
