# Biblioteca de textos canônicos

Parágrafos que se repetem entre propostas. O redator usa **verbatim** quando o
caso encaixa, trocando apenas o nome do cliente e o que estiver entre `<>`.
Escrever de novo o que já está resolvido só introduz variação de tom.

Quando nenhum texto daqui servir, o redator escreve — seguindo
`specs/steering/tom-de-voz.md`.

---

## Premissas — implantação

- O valor fechado corresponde ao escopo desta proposta. Módulos não listados são
  cotados em horas e aprovados antes de entrar em execução.
- A etapa de design está inclusa. Caso a `<cliente>` forneça o layout ou a
  referência visual pronta, o orçamento contempla apenas o desenvolvimento.
- A `<cliente>` fornecerá os acessos necessários à plataforma, ao ERP e às
  ferramentas de terceiros contratadas.
- Validações de protótipo e homologação acontecem em janelas acordadas no
  kick-off; atrasos nessas janelas deslocam o cronograma na mesma medida.
- Configurações comerciais de meios de pagamento, antifraude e contratos
  logísticos permanecem sob a operação da `<cliente>`.

## Premissas — evolução

- O pacote de `«orc:evolucao.pacote_horas_fmt»` mensais é distribuído entre as
  frentes de escopo conforme a priorização definida em conjunto a cada ciclo.
- Demandas que envolvam criação de layout são orçadas incluindo a etapa de
  design; quando a `<cliente>` fornecer o layout ou a referência visual, o
  orçamento contempla apenas o desenvolvimento.
- A `<cliente>` fornecerá os acessos necessários aos ambientes da plataforma e às
  ferramentas de terceiros contratadas.
- As primeiras semanas concentram naturalmente ajustes e correções de herança; a
  evolução propriamente dita ganha ritmo à medida que o time domina o código.
- Configurações de ERP, meios de pagamento, antifraude, integrações logísticas e
  cadastro de produtos permanecem sob a operação da `<cliente>`.

## Quando algo ainda depende de decisão

Textos para os casos mais comuns de lacuna que afeta o escopo ou o valor — a
condição vira cláusula, nunca confissão de indefinição.

- **Ferramenta de terceiro a escolher** (ex.: mapa de calor, heatmap, A/B test):
  Instalamos e configuramos a ferramenta de `<categoria da ferramenta>`
  escolhida em conjunto com a `<cliente>`. A leitura dos dados e a
  transformação em backlog de ajustes entram na conversa de priorização de cada
  ciclo.
- **Alcance que depende de volume não levantado** (ex.: quantas páginas,
  quantos itens): Revisamos `<o que será revisado>` dentro do pacote de horas
  contratado, com o alcance de cada ciclo definido em conjunto conforme a
  prioridade do momento.
- **Diagnóstico ou ajuste sobre algo já existente**, sem módulo equivalente no
  catálogo padrão (ex.: revisão de UX/UI, correção de comportamento): É
  diagnóstico e ajuste sobre o que já está em operação — dimensionado à parte
  para caber no formato de horas do pacote mensal.

## Não contemplado — comum a todas

- Gestão de mídia paga, tráfego e growth — frente independente deste contrato.
- Produção de conteúdo: textos, imagens, fotografia de produto e cadastro item a item.
- Licenças e mensalidades de plataforma e serviços de terceiros.

## Não contemplado — implantação

**Leia `evolucao.origem` antes de usar o item abaixo — ele tem duas versões, e
usar a errada contradiz outra página da mesma proposta.**

- `evolucao.origem == "alternativa_convertida"` (o caso comum): "Sustentação
  após o go-live — coberta pelo contrato de evolução, orçado à parte."
- `evolucao.origem == "contratada"` (a implantação já vende o pacote mensal,
  seção 04b/06): **não use este item.** O acompanhamento não está "fora do
  escopo, a orçar depois" — já foi cotado e detalhado duas páginas antes. Se a
  proposta encontrou esta situação na primeira revisão (Reed7, 2026-08-20): o
  item apareceu verbatim em "Não contemplado" enquanto a página do
  acompanhamento mensal já mostrava pacote, valor e fidelidade fechados — o
  revisor pegou a contradição e a fase 04 precisou ser refeita. Se quiser
  registrar o acompanhamento aqui mesmo assim, ligue as duas páginas
  explicitamente: "O acompanhamento mensal depois do go-live é o contrato
  detalhado na seção Acompanhamento mensal — não uma cotação em aberto."

## Não contemplado — evolução

- Projetos de redesign completo ou migração de plataforma — orçados em proposta própria.

## Transição de fornecedor (evolução, quando há parceiro atual)

Para que a virada ocorra sem perda de ritmo, dois pontos precisam ser
encaminhados pela `<cliente>` junto ao fornecedor atual:

- **Entrega do repositório da loja**, atualizado e com a última tarefa aprovada
  publicada. Como o código sobe compilado para a plataforma, o repositório é o
  único insumo que permite ao nosso time assumir a operação sem retrabalho.
- **Verificação da carência contratual** e do prazo de aviso prévio — que costuma
  variar de 30 a 90 dias —, para alinhar a data de início sem sobreposição de
  contratos.

## Migração de plataforma (implantação, quando `natureza = migracao`)

Dois pontos precisam ser encaminhados pela `<cliente>` para que a virada ocorra
sem perda de posicionamento:

- **Exportação completa do catálogo atual**, com especificações e imagens em
  resolução original. É o insumo que permite normalizar os dados antes da carga,
  em vez de corrigir depois.
- **Lista das URLs com tráfego relevante**, extraída do analytics e do Search
  Console. É a base do plano de redirecionamentos — sem ela, o mapeamento vira
  suposição.

## Janela de virada

Recomendamos posicionar o go-live **fora do pico do calendário comercial**.
Migração de plataforma sempre carrega um período de estabilização, e concentrá-lo
em semana de campanha transforma um ajuste rotineiro em incidente. A data é
acordada no kick-off, com o cronograma correndo de trás para frente a partir dela.

## Próximos passos — implantação

1. **Alinhamento do escopo** — Conversa para revisar os módulos e ajustar o que
   fizer sentido antes de fechar.
2. **Escolha do modelo** — Projeto fechado ou contrato de evolução, conforme a
   distribuição do investimento.
3. **Kick-off** — Apresentação do time, acessos, cronograma detalhado e início da
   descoberta.

## Próximos passos — evolução

1. **Apresentação aos decisores** — Conversa para detalhar o modelo de trabalho e
   esclarecer dúvidas técnicas.
2. **Definição da janela** — Verificação da carência contratual e do repositório,
   com a data de virada acordada.
3. **Kick-off** — Apresentação do gestor e do time, configuração do Runrun.it e
   priorização do primeiro ciclo.

## Nota de validade (pé da página de investimento)

Condições válidas até `«orc:proposta.validade_extenso»`. Licenças e mensalidades
da plataforma e de terceiros são de responsabilidade da `<cliente>`.

## Nota do bloco de preço — implantação

Valor fechado para o escopo desta proposta, com a etapa de design inclusa.
Alterações de escopo são cotadas em horas e aprovadas antes de entrar em
execução — o valor acima não se move sozinho.

## Nota do bloco de preço — evolução

Pacote mensal de horas técnicas de desenvolvimento e sustentação, distribuídas
livremente entre as frentes de escopo, com governança e acompanhamento inclusos.
Quanto maior o volume contratado, menor o valor da hora — o upgrade de plano pode
ser avaliado a qualquer momento.
