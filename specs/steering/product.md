# O que este workflow produz

Uma **proposta comercial da N1.AG em PDF**, a partir da transcrição de uma
reunião de levantamento, com o escopo extraído e precificado.

## Para quem

Para o time comercial da N1. Quem opera o workflow é quem conduziu a reunião e
vai assinar a proposta — não é uma ferramenta de autoatendimento do cliente.

## Os dois modelos de proposta

| Modelo | Quando | O que precifica |
|---|---|---|
| `implantacao` | Loja nova, migração de plataforma, replatform | Valor base da plataforma + módulos adicionais em horas, menos o abatimento de design se o layout vier do cliente. **Sempre** acompanhada da alternativa em fee mensal. |
| `evolucao` | Sustentação e evolução de uma loja que já roda | Pacote mensal de horas, com três opções de tamanho e uma marcada como recomendada. |

`natureza` (migração ou projeto novo) **não muda preço nenhum** — muda só a
narrativa. Isso é normativo e verificado por `auditar.py precos`.

## O que este workflow NÃO faz

- Não decide preço fora da tabela. Desconto é decisão humana, aplicada depois.
- Não inventa credencial, número ou case da N1 que não esteja em `perfil-n1.toml`.
- Não escreve contrato, proposta jurídica ou termo de serviço.
- Não faz o diagnóstico técnico do site do cliente (isso é Web Insights).
- Não envia a proposta. O PDF sai em `saida/`; quem envia é uma pessoa.
- Não substitui a reunião. Se a transcrição não disser, o workflow declara a
  lacuna — nunca preenche por conta própria.

## O critério de qualidade

Uma proposta boa aqui é uma proposta **defensável**: cada linha de escopo tem
uma evidência na transcrição, e cada número tem uma origem em `dados/`. Se o
cliente perguntar "de onde saiu isso?", a resposta está em
`proposta/03-orcamento.md`.
