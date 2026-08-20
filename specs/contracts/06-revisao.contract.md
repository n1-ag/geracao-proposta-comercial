# Contrato 06 — Render e revisão

**Entrada:** `proposta/proposta.html`, `proposta/03-orcamento.json`
**Saída:** `saida/*.pdf`, `saida/relatorio-paginacao.json`, `proposta/06-revisao.md`
**Executores:** o script `render_pdf.py` (medição) + o agente `revisor-proposta` (leitura)

## Checklist binário do script

| # | Verificação | Falha |
|---|---|---|
| 1 | Todos os recursos carregaram (CSS, logo) | exit 2 |
| 2 | A Poppins foi carregada de fato | exit 4 |
| 3 | Zero transbordo e zero colisão com o rodapé | exit 3 |
| 4 | Nº de páginas do PDF == nº de `<section class="page">` | exit 3 |
| 5 | Metadata Title/Author/Subject preenchidas | exit 5 |

Depois: `auditar.py pdf`, `auditar.py numeros` e `auditar.py template` precisam
passar sem falha.

## Leitura qualitativa do agente

O que a máquina não pega:

1. O nome do cliente está correto e idêntico em capa, rodapés e corpo?
2. A numeração das seções é sequencial, sem buraco, e o rodapé bate?
3. Alguma frase ficou órfã — uma linha sozinha no fim de um bloco?
4. O tom está de acordo com `steering/tom-de-voz.md`? Escapou algum superlativo,
   jargão ou promessa de resultado?
5. As afirmações sobre a N1 batem com `perfil-n1.toml`?
6. Sobrou alguma menção ao fornecedor atual em tom de crítica?
7. A validade aparece coerente nas duas formas (`30/09/2026` e "30 de setembro
   de 2026")?
8. O escopo descrito na página 02 bate com o que está sendo cobrado na 04?
9. **Vazou alguma lacuna, observação de auditoria ou justificativa de
   catalogação para o texto do cliente?** Procure o sintoma: menção à nossa
   mecânica interna ("entrou fora do catálogo padrão", "estimativa própria") ou
   confissão de indefinição em voz própria ("ainda não foi definido",
   "ainda não foi confirmado", "a confirmar", "ainda depende de conversa"). O que
   afeta o valor precisa estar coberto por uma premissa redigida como condição —
   não pela frase de dúvida. Se sumiu por completo sem virar premissa nem
   entrega afirmativa, também é falha: a proteção contra escopo crescendo
   precisa continuar em algum lugar do documento.

## Seções obrigatórias de `06-revisao.md`

1. Frontmatter.
2. **Resultado do script** — páginas, transbordos, metadata, resultado de cada
   auditoria.
3. **Leitura qualitativa** — os 9 pontos acima, cada um com veredito e, se
   houver problema, a página e o trecho.
4. **Pendências** — o que precisa voltar para 04 ou 05, se algo precisar.
5. **Veredito** — `pronto para envio` ou `precisa de correção`.

O agente **não corrige** — reporta. Correção é reinvocação da fase responsável.
