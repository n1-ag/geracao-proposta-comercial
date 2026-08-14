# Boilerplate — Proposta Comercial N1.AG

Transcrição de reunião entra de um lado, proposta comercial em PDF sai do outro.

A arquitetura tem uma regra central: **o LLM decide *o quê*; o Python decide
*quanto*.** Nenhum agente escreve um número monetário. O escopo é mapeado por
agente, o preço é calculado por script, e um checkpoint humano fica entre os dois
e o PDF.

Há **dois jeitos de usar**: o app local, feito para o time comercial, e os slash
commands no terminal, para quem quer o controle fino. Os dois rodam o mesmo
pipeline sobre os mesmos dados.

## Quick start — o app (recomendado para o comercial)

```bash
python3 app/importar.py     # só na primeira vez: traz o histórico de arquivo/
python3 app/servidor.py     # abre http://127.0.0.1:7801
```

Cadastre o cliente, cole a transcrição, escreva as observações e mande gerar. O
app roda 01 → 03, para na tela de aprovação com o escopo e os valores, e só
depois do seu aval segue para 04 → 06 e entrega o PDF. Nenhum terminal
envolvido. Veja [app/README.md](app/README.md).

## Quick start — o terminal

```bash
cp entrada/transcricao.exemplo.md  entrada/transcricao.md    # cole a transcrição real
cp entrada/dados-cliente.exemplo.md entrada/dados-cliente.md # preencha a ficha
```

No Claude Code, dentro desta pasta:

```
/proposta
```

O pipeline roda 01 → 03, **para no checkpoint** com o escopo e a memória de
cálculo na tela, e só depois de você aprovar segue para 04 → 06 e emite o PDF em
`saida/`.

Terminou? `/proposta-nova` arquiva e deixa o repositório pronto para o próximo
cliente. O repositório é um só e trabalha **uma proposta por vez** — não duplique
a pasta, senão a tabela de preços diverge entre as cópias.

## O pipeline

| Fase | Executor | Entrega |
|---|---|---|
| 01 Briefing | agente `transcricao-analyzer` | fatos extraídos e numerados como evidências `E##` |
| 02 Escopo | agente `escopo-mapper` | demandas traduzidas em itens do catálogo |
| 03 Orçamento | **script** `precificar.py` | os números, com memória de cálculo |
| — | **você** | aprova o escopo e o valor |
| 04 Narrativa | agente `redator-proposta` | o texto, com tokens no lugar dos números |
| 05 Montagem | agente `montador-html` | o HTML, montado dos templates |
| 06 Render | `render_pdf.py` + agente `revisor-proposta` | o PDF e a revisão |

## Comandos

| Comando | O quê |
|---|---|
| `/proposta` | o pipeline inteiro, com os gates |
| `/proposta-briefing` `/proposta-escopo` `/proposta-orcamento` | fases 01–03 isoladas |
| `/proposta-narrativa` `/proposta-html` `/proposta-revisao` | fases 04–06 isoladas |
| `/proposta-pdf` | re-renderiza o PDF sem reprocessar conteúdo |
| `/proposta-catalogo` | incorpora ao catálogo um módulo cotado fora dele |
| `/proposta-precos` | valida `dados/*.toml` e roda a suíte golden |
| `/proposta-nova` | arquiva a proposta atual e prepara o repo para a próxima |

## Onde ficam os preços

Tudo em `dados/`, em TOML, para editar à mão:

| Arquivo | O quê |
|---|---|
| `precos.toml` | valor base por plataforma, design embutido, hora, faixas de fee, conversão |
| `catalogo-modulos.toml` | 58 módulos com horas por complexidade |
| `condicoes-comerciais.toml` | parcelamento, prazo, fidelidade, validade |
| `perfil-n1.toml` | o que a proposta pode afirmar sobre a N1 |

Depois de mexer: `python3 scripts/auditar.py precos`.

## Requisitos

- Python 3.11+ (usa `tomllib` da stdlib)
- `playwright` + Google Chrome instalado — o render usa o Chrome do sistema
- `pypdf` para a metadata do PDF
- `poppler-utils` (`pdftotext`, `pdfinfo`, `pdffonts`) para as auditorias

```bash
python3 -c "import tomllib, playwright, pypdf; print('ok')"
```

## Estrutura

```
entrada/     transcrição e ficha do cliente (você preenche)
dados/       a fonte da verdade comercial (você edita)
specs/       contratos e contexto permanente dos agentes
templates/   casca, seções, blocos, CSS e assets do PDF
scripts/     precificar.py · render_pdf.py · auditar.py
proposta/    artefatos da proposta em andamento (gerado)
saida/       o PDF e os relatórios (gerado)
arquivo/     propostas encerradas, uma pasta por cliente (gerado, fora do git)

app/         o webapp local para o time comercial (stdlib pura + SQLite)
propostas/   um workspace por proposta, gerido pelo app (gerado, fora do git)
```

Leia o `GUIA.md` para o uso no dia a dia e `specs/README.md` para entender o
desenho.
