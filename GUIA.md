# Guia de uso

## 1. O modelo de uso: uma proposta por vez

O repositório é **um só**, e trabalha uma proposta por vez. Não duplique a pasta
por cliente: `dados/` precisa continuar sendo fonte única de preço, e doze cópias
da tabela divergem em silêncio — você descobre quando manda uma proposta com o
valor do ano passado.

O ciclo é:

```
entrada/  →  proposta/  →  saida/  →  arquivo/<cliente>-<data>/
```

Quando a proposta sai, você encerra e o repositório volta ao estado limpo:

```
/proposta-nova              # arquiva a atual e prepara a próxima
/proposta-nova --descartar  # descarta sem guardar (pede confirmação)
/proposta-nova --reset      # limpa tudo, inclusive a entrada, do zero
```

O arquivamento leva junto uma cópia da transcrição e da ficha — sem elas, o
arquivo não se explica daqui a seis meses. `arquivo/` fica **fora do git**: é
dado de cliente. O PDF que importa deve ir para o Drive ou o CRM, não ficar só
aqui.

Histórico do que já saiu: `python3 scripts/arquivar.py --listar`

## 2. Antes de rodar

```bash
cp entrada/transcricao.exemplo.md  entrada/transcricao.md
cp entrada/dados-cliente.exemplo.md entrada/dados-cliente.md
```

**Regra de ouro:** os dois únicos arquivos que você preenche à mão são esses.
Campo da ficha que você não souber, deixe em branco — vira lacuna declarada na
proposta. Uma lacuna visível custa uma pergunta; um dado errado custa a conta.

Não limpe a transcrição. Hesitação e mudança de ideia são informação.

## 3. Rodando

```
/proposta
```

O pipeline vai até a fase 03 e **para**. Você vê:

- a tabela de itens de escopo, cada um com a evidência `[E##]` que o originou;
- a memória de cálculo completa (`proposta/03-orcamento.md`);
- os alertas — em especial `ITEM_NAO_CATALOGADO`;
- as lacunas que ainda podem mudar o valor.

Você aprova, ajusta ou manda refazer. Só depois da aprovação explícita o texto é
escrito e o PDF é gerado.

## 4. O checkpoint é uma barreira

Se você mandar ajustar o escopo, o pipeline volta para a fase 02, roda a 03 de
novo e **retorna ao checkpoint**. Refazer 02 ou 03 muda o hash do orçamento e
derruba a aprovação — as fases 04, 05 e 06 ficam bloqueadas até nova aprovação.

É proposital: impede que um preço aprovado vire outro preço em silêncio.

## 5. Ajustando preços

| Quero mudar | Edito |
|---|---|
| Valor base de uma plataforma | `dados/precos.toml` |
| Faixas de fee mensal, multiplicador da conversão | `dados/precos.toml` |
| Horas de um módulo | `dados/catalogo-modulos.toml` |
| Parcelamento, prazo, fidelidade, validade | `dados/condicoes-comerciais.toml` |
| O que a proposta afirma sobre a N1 | `dados/perfil-n1.toml` |
| Parágrafos que se repetem entre propostas | `dados/biblioteca-textos.md` |

Sempre depois: `python3 scripts/auditar.py precos`

Se um caso golden falhar, **não mude o caso para o script passar.** Decida qual
dos dois está certo. Mudou uma regra de negócio? Atualize o caso golden também, e
conscientemente.

## 6. Simulando um valor rápido

```bash
python3 scripts/precificar.py --simular --converter 50000
python3 scripts/precificar.py --simular --pacote 26
python3 scripts/precificar.py --simular --plataforma vtex --horas-adicionais 40
python3 scripts/precificar.py --simular --plataforma shopify --layout-do-cliente
```

Na conversa com o Claude, a skill `precificacao-n1` força esse caminho em vez de
uma resposta de cabeça.

## 7. Um módulo novo apareceu

O agente de escopo cota itens fora do catálogo em `itens_fora_catalogo`, com
alerta visível no checkpoint. Para incorporar de vez:

```
/proposta-catalogo
```

Ele primeiro tenta convencer você de que um item existente já serve — catálogo
que só cresce perde a função de padronizar.

## 8. Quando o PDF não sai

| Código | O que aconteceu | O que fazer |
|---|---|---|
| 2 | Um recurso deu 404 (CSS, logo) | confira os caminhos relativos do HTML |
| 3 | Transbordo de página, ou nº de páginas divergente | leia `saida/relatorio-paginacao.json`; a página e o bloco estão lá |
| 4 | A Poppins não carregou | confira `templates/assets/fonts/` |
| 5 | PDF saiu sem metadata | `pip install --user pypdf` |

Transbordo **não** é resolvido cortando texto. O montador move o bloco para uma
página de continuação; se o problema for texto longo demais, volta para o
redator com o limite estourado.

## 9. Retocando o layout à mão

Editou `proposta/proposta.html` ou o CSS? Re-renderize sem reprocessar conteúdo:

```
/proposta-pdf
```

Ele avisa se a tabela de preços mudou desde que o orçamento foi calculado.

## 10. Verificando por fora

```bash
python3 scripts/auditar.py precos                  # dados + 35 casos golden
python3 scripts/auditar.py escopo                  # .md × .json, rastreabilidade
python3 scripts/auditar.py numeros                 # todo número do HTML veio do orçamento
python3 scripts/auditar.py template                # só classes declaradas no CSS
python3 scripts/auditar.py pdf saida/<arquivo>.pdf # páginas, fontes, metadata, marcadores
```

O `auditar.py numeros` é o que pega alucinação numérica de forma mecânica: ele
extrai todo `R$`, hora e percentual do HTML e reprova o que não veio de um campo
`_fmt` do orçamento.

## 11. Customizando o boilerplate

| Quero mudar | Arquivo |
|---|---|
| O que uma fase precisa entregar | `specs/contracts/<NN>-*.contract.md` |
| Como o agente trabalha para entregar aquilo | `.claude/agents/<agente>.md` |
| A aparência do PDF | `templates/assets/css/proposta.css` |
| Uma seção nova no PDF | arquivo em `templates/secoes/` + contrato 05 |
| O tom de voz | `specs/steering/tom-de-voz.md` |
| Adicionar uma fase | novo agente + novo contrato + ajuste em `/proposta` |

Ao mexer no CSS, valide contra a referência:

```bash
python3 scripts/render_pdf.py --html templates/exemplo/urban-arts.html \
    --saida /tmp/ref.pdf --auditar --estrito
```

`templates/exemplo/urban-arts.html` é a reconstrução fiel de uma proposta real —
é o teste de regressão visual do template.

## 12. Os três exemplos

| Arquivo | Para quê |
|---|---|
| `urban-arts.html` | proposta de evolução, 7 páginas. Reconstrução fiel do PDF original — use como referência de fidelidade |
| `implantacao-shopify.html` | proposta de implantação, 8 páginas, com tabela de módulos e a alternativa em fee mensal |
| `evolucao-3-planos.html` | uma página; referência do bloco de 3 opções de pacote |
