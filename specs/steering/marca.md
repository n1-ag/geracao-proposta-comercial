# Identidade visual

Tudo aqui foi obtido por medição direta dos PDFs originais (Urban Arts e Lojas
Pompeia), não por estimativa. As medidas estão em pontos, a unidade nativa do
PDF: A4 = 595,28 × 841,89pt.

## Cores

| Token | Hex | Uso |
|---|---|---|
| `--navy` | `#0C1F59` | fundo escuro, títulos |
| `--navy-mid` | `#16337F` | cartões da capa, filetes decorativos |
| `--navy-rule` | `#22407F` | separador dentro do bloco escuro |
| `--cyan` | `#06ADC2` | destaques, numeração, marcadores |
| `--tint` | `#F4F7FC` | fundo dos cartões claros |
| `--tint-border` | `#DCE4F2` | borda do cartão com fundo |
| `--border` | `#E3E8F2` | borda de cartão sem fundo, filetes, tabela |
| `--flow-line` | `#CFDAEC` | linha que conecta as etapas do fluxo |
| `--on-navy` | `#C6D2EC` | texto corrido sobre fundo escuro |
| `--ink` | `#3A4666` | texto corrido sobre fundo claro |

## Tipografia — Poppins 400/500/600/700

| Elemento | Tamanho | Entrelinha |
|---|---|---|
| Título da capa | 29pt / 700 | 33,64pt |
| Título de seção | 15pt / 700 | 1 |
| Kicker da seção | 8,6pt / 400 | 1 |
| Texto corrido | 10pt / 400 | 16,8pt |
| `h3` | 11,5pt / 700 | 18,9pt |
| Título de frente | 10pt / 700 | 1,4 |
| Texto de frente | 9pt / 400 | 13,95pt |
| Bullet / check / cross | 9,6pt / 400 | 14,88pt |
| Número do `.stats` | 17pt / 700 | 1,4 |
| Valor do `.price` | 30pt / 700 | 1 |
| Tabela | 9,2pt · sub-nota 8,2pt | 1,4 |
| Rodapé | 7,2pt | 1,4 |

## Geometria

- Respiro lateral: **45,30pt** nas páginas de corpo, **51,02pt** na capa e no fechamento.
- Topo do conteúdo: **48,03pt**. Filete do rodapé: **793,79pt**.
- Vão padrão entre colunas: **16,99pt**.

## Blocos

`.cover` (+`.factbar`) · `.sec-head` (+`.sec-num`, `.sec-kicker`) · `.stats` ·
`.frente` · `.flow` · `.card` (+`.tint`, `.navy`, `.card-sm`) · `.two` ·
`.price` (+`.price-tag`, `.price-metas`, `.price-nota`) · `.planos` (+`.plano.rec`) ·
`table` (+`tr.tot`, `.sub`) · `ul.bullets` · `ul.check` · `ul.cross` (+`.two-col`) ·
`.nota` · `.fine` · `.pe-pagina` · `.close` · `.foot`.

## Cuidados

1. **Cartão escuro (`.navy`):** o `<strong>` sai em ciano automaticamente. Não
   aplique cor manual.
2. **Rodapé:** `.foot` é posicionado de forma absoluta. Copie-o junto sempre que
   duplicar uma página. Capa e fechamento **não têm** rodapé.
3. **Numeração:** o `.pg` do rodapé é o ordinal físico começando em `01` na
   primeira página depois da capa.
4. **O ✓ é SVG, não texto.** A Poppins não tem o glifo U+2713 e depender da
   fonte de fallback do sistema é a falha silenciosa clássica.
5. **Logo:** `n1_white.svg` em fundo escuro, `n1_color.svg` em fundo claro. O
   branco foi extraído do PDF original; o colorido é derivação (moldura navy).
