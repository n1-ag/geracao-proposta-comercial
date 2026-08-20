# Contrato 04 — Narrativa

**Entrada:** `01-briefing.md`, `02-escopo.md`, `03-orcamento.md`, `dados/perfil-n1.toml`, `dados/biblioteca-textos.md`
**Saída:** `proposta/04-narrativa.md`
**Executor:** agente `redator-proposta`
**Pré-condição:** `manifest.checkpoint_humano.status == "aprovado"`.

Uma seção por bloco do PDF. **Cada uma com limite de caracteres declarado** — o
limite não é sugestão: estourar provoca transbordo e o render recusa o PDF.

## `02-escopo.md` e `03-orcamento.md` são insumo, não texto pronto

Você lê os dois inteiros, mas nem tudo neles é para o cliente ver.

`observacao` de cada item, a coluna de justificativa dos itens fora do
catálogo, o critério de complexidade aplicado e a seção `## Lacunas` são **notas
de auditoria interna** — registradas para quem decide o preço e quem revisa o
checkpoint, não para quem recebe a proposta. Elas explicam *por que classificamos
assim*; a proposta só diz *o que entregamos*.

O sintoma de transcrever direto é reconhecível: a frase cita mecânica nossa
("entrou fora do catálogo padrão, com estimativa própria"), ou admite que algo
"ainda não foi definido/confirmado/levantado" em vez de descrever a entrega pelo
que ela cobre. Se a frase que você está escrevendo não faria sentido dita em voz
alta para o cliente, ela é insumo, não é conteúdo — reescreva a partir do que
está decidido.

Uma lacuna sobre algo que muda o valor não desaparece — vira **premissa** (seção
05), redigida como condição do projeto, não como confissão de incerteza. Ver
`steering/tom-de-voz.md` para o par de exemplos.

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
- O rótulo de cada linha da tabela é o **`rotulo_exibido`** da linha do
  orçamento, não o `nome` do catálogo. Ele já vem com a contagem quando o item
  cobre um grupo ("Landing pages institucionais — 3 páginas"): copie como está.
- **A tabela carrega valor, nunca esforço.** Nada de `26h · R$ 5.200,00`, nada
  de "134h × R$ 200,00" na composição do investimento, nada de cartão com o
  total de horas ou com o valor da hora técnica. O cliente compra entregas por
  um preço; horas e taxa horária são a nossa conta, e juntas entregam a margem.
  `auditar.py numeros` reprova a fase.
  A exceção é o pacote de horas do fee mensal: ali a hora é o produto.

O **valor da hora técnica não aparece em proposta nenhuma**, nem na de fee
mensal: com o pacote impresso ("30 horas · R$ 6.000,00") a taxa é uma divisão, e
declará-la só chama atenção para a conta em vez da entrega.

A **hora excedente** é outra coisa e continua na proposta: é cláusula, o cliente
precisa saber quanto paga se estourar o pacote, e escondê-la seria pior do que
mostrá-la.

- O valor de cada linha é o **`valor_exibido_fmt`**, nunca o `valor_fmt`. Os
  dois são iguais na maioria das propostas; quando houve fechamento comercial,
  só o `exibido` soma o total impresso.

### `## 02B FORMATOS` *(só quando o orçamento tem `implantacao.opcoes`)*
- `intro`: até 320 caracteres; diga a qual formato a tabela detalhada se refere
- por cartão: `nome` ≤ 34 caracteres · `resumo` ≤ 160 · 3 a 5 bullets ≤ 46 cada
- `nota`: até 200 caracteres
- Nome e valor de cada formato vêm de `implantacao.opcoes[]`. Não invente
  formato, não reordene: a ordem do JSON é a ordem do documento.

A forma, literal — **é isto que você escreve**, sem procurar exemplo em outro
lugar:

```markdown
## 02B FORMATOS

**intro:** A conversa apontou três caminhos, e nenhum é meio caminho: cada um
resolve um problema inteiro, num recorte diferente. A tabela da página anterior
detalha o formato completo; os outros dois são recortes dele.

### Formato 1 — «orc:implantacao.opcoes.0.nome»
- **valor:** `«orc:implantacao.opcoes.0.total_fmt»`
- **resumo:** Aporte dos dados para a nova plataforma, com validação técnica do
  que já foi construído. *(118)*
- Migração do catálogo *(21)*
- Migração de clientes e pedidos *(30)*
- Redirects e conferência de slugs *(33)*

### Formato 2 — «orc:implantacao.opcoes.1.nome»
- **valor:** `«orc:implantacao.opcoes.1.total_fmt»`
- **resumo:** …
- …

**nota:** Os formatos são cumulativos: o maior contém os menores. Trocar de
formato antes do kick-off é recotar a diferença, não refazer a proposta.
```

Um `### Formato N` por item de `opcoes[]`, na ordem. O número entre parênteses é
a contagem de caracteres, como nas outras seções. Valor sempre por token — nunca
digitado.

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
- tabela de 5 a 6 linhas · 1 card (até 620 caracteres)

**Leia `evolucao.origem` antes de escrever esta seção. Ela decide o que a seção
é, e qual template a fase 05 escolhe — não é só questão de tom.**

- `"alternativa_convertida"` — o comportamento de sempre: é **outra forma de
  pagar o mesmo projeto**. Vai para `04b-alternativa-evolucao.html`, com um
  preço único. Escreva como escolha entre dois caminhos, compare os dois
  valores, e o card é de comparação. Use `price_tag`.
- `"contratada"` — é **trabalho a mais, que começa depois do go-live**: o
  projeto entrega, e o acompanhamento continua dali, no pacote que a reunião
  combinou. Vai para `04b-alternativa-planos.html`, com **três cartões de
  pacote** (`evolucao.opcoes[]`) — o mesmo card de plano da proposta de
  evolução pura, não um preço único. Aqui a seção **não é uma alternativa**, e
  escrevê-la como alternativa vende o oposto do que foi combinado — oferece ao
  cliente sair do projeto que ele já fechou.
  - Nunca "em vez de", "ou então", "como alternativa ao investimento".
  - **Não compare com o valor do projeto.** Um é fechado, o outro é mensal
    recorrente; lado a lado, o mensal parece um desconto do projeto. Os três
    cartões comparam pacotes de horas entre si, nunca com `implantacao.total_fmt`.
  - Prefira "depois do go-live", "a partir da entrega", "o mês a mês que
    sustenta o que foi construído".
  - Não há `price_tag` nesta variante — os três cartões falam por si. O card do
    fim deixa de ser comparação e passa a ser o que entra no pacote mensal.
  - `ALT_TABELA_TITULO` segue a mesma voz: acompanhamento, não alternativa.

O nome do bloco é histórico em ambos os casos, mas **o template não é o mesmo**
— a fase 05 escolhe entre os dois arquivos pelo `evolucao.origem`. Escreva o
texto pensando em qual dos dois vai receber.

### `## 05 PREMISSAS`
- 5 premissas de até 220 caracteres
- bloco de transição/migração (condicional) · card de janela (condicional)
- `nao_contemplado`: 4 itens de até 130 caracteres
- **É aqui que uma lacuna que afeta o valor ou o escopo vira texto do cliente.**
  Não como "isso ainda não foi definido", mas como a condição que protege o
  projeto: quem define, quando, e o que acontece se mudar. Prefira o padrão
  canônico de `dados/biblioteca-textos.md` (ex.: "o pacote mensal é distribuído
  entre as frentes conforme a priorização definida em conjunto a cada ciclo") a
  escrever a incerteza do zero.

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
7. **Nenhuma lacuna, observação de auditoria ou justificativa de catalogação
   chega ao cliente em forma reconhecível.** O que muda o valor vira premissa
   (seção 05); o resto orienta a escolha das palavras, mas não aparece. Ver a
   seção acima, "`02-escopo.md` e `03-orcamento.md` são insumo, não texto
   pronto". `auditar.py numeros` reprova frases desta família.
