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
- **Justifique o número quando ele surpreende.** "28h porque o ERP exige de-para
  de códigos" vale mais que "28h".
- **Assuma o que não sabe.** "A confirmar com o time de catálogo" é uma frase
  forte numa proposta, não fraca.
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
