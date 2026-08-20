# Tom de voz

## Como a N1 escreve

Primeira pessoa do plural. Frases curtas. Afirmação direta, sem rodeio de
agência. O leitor é um dono de operação de e-commerce que já ouviu muita
promessa — o que convence é precisão, não entusiasmo.

## Faça

- **Descreva o problema do cliente com as palavras dele.** Se na reunião ele
  disse "o cadastro é refeito à mão", escreva isso, não "ineficiência operacional
  no fluxo de dados".
- **Diga o que está incluso e o que não está,** com a mesma clareza.
- **Justifique o número quando ele surpreende, sem expor o processo interno.**
  "28h porque o ERP exige de-para de códigos" vale mais que "28h" — é uma razão
  técnica que o cliente reconhece. Mas a razão nunca pode ser a nossa mecânica de
  catalogação: nada de "porque entrou fora do catálogo padrão" ou "com estimativa
  própria". Se a única justificativa disponível é interna, não justifique —
  apenas afirme o número.
- **Assuma o que não sabe — nos artefatos internos, não no documento do
  cliente.** "A confirmar com o time de catálogo" é uma frase forte no
  `02-escopo.md` e no `03-orcamento.md`, onde vira instrução de quem decide. No
  PDF ela é uma confissão de instabilidade. Lá, o que está em aberto se resolve
  de duas formas: (a) o mecanismo que trata isso vira premissa — não "o alcance
  ainda depende de conversa com você sobre a prioridade", mas "o escopo de cada
  ciclo é definido na reunião de planejamento mensal"; ou (b) a entrega é
  descrita pelo que ela certamente cobre, sem mencionar o que ainda não foi
  decidido. Nunca as duas frases-espelho da mesma incerteza no mesmo documento.
- **Recomende.** A leitura técnica entra como recomendação, nunca como imposição
  sobre a decisão do cliente.

## Não faça

- Superlativo sem lastro: "a melhor", "líder de mercado", "referência absoluta".
- Promessa de resultado: "vamos aumentar sua conversão em X%".
- Jargão: "sinergia", "ecossistema", "solução end-to-end", "alavancar".
- Voz passiva impessoal: "será realizado", "poderá ser avaliado" quando cabe
  "fazemos" e "avaliamos".
- Emoji, exclamação, pergunta retórica.
- Adjetivo empilhado: "solução robusta, moderna e escalável".
- Falar mal do fornecedor atual. Descreva o sintoma, não a culpa.

## Comprimento

Cada bloco do PDF tem um orçamento de caracteres no contrato 04. Ele não é
sugestão: estourar o limite provoca transbordo de página, e o render em modo
estrito recusa o PDF. Escrever curto é requisito técnico, não estilo.

## Números por extenso

Não escreva número em prosa ("cerca de trinta horas"). Todo número vem de token
`«orc:…»`. O `auditar.py numeros` reprova qualquer valor que não venha do
orçamento — inclusive os escritos de improviso.
