# Princípios inegociáveis

1. **Responsabilidade única.** Cada fase faz uma coisa. Extrair fato não é
   decidir escopo; decidir escopo não é precificar; redigir não é paginar.

2. **Agente não digita número.** Nenhum agente escreve valor monetário, hora ou
   percentual. Quem calcula é `scripts/precificar.py`. O texto usa tokens
   `«orc:caminho.do.campo_fmt»`, resolvidos na montagem.

3. **Rastreabilidade obrigatória.** Toda afirmação sobre o cliente cita a
   evidência (`[E07]`). Toda linha de escopo cita a evidência que a originou.
   Todo número tem origem declarada em `dados/`.

4. **Lacuna é resposta.** O que a reunião não respondeu vira item declarado em
   "Lacunas". Preencher por conta própria é o pior erro possível aqui, porque o
   resultado parece completo.

5. **O catálogo é fechado.** Só se cota o que existe em `catalogo-modulos.toml`.
   Item novo vai para `itens_fora_catalogo`, o que gera alerta no checkpoint —
   de propósito.

6. **O checkpoint humano é uma barreira, não um aviso.** As fases 04 em diante
   não rodam sem aprovação registrada no manifest. Refazer 02 ou 03 derruba a
   aprovação.

7. **Espaçamento é `margin-bottom` do bloco anterior.** Nunca `margin-top` do
   seguinte: margens de irmãos colapsam, e o ajuste simplesmente não pega.

8. **Transbordo é falha de build.** O render em modo estrito não emite PDF com
   conteúdo cortado. Texto longo demais volta para o redator, não é truncado.

9. **Nada sobre a N1 sem fonte.** Credenciais, números institucionais e frases
   de posicionamento saem de `dados/perfil-n1.toml`, verbatim.

10. **Português do Brasil, pronto para o cliente ler.** Sem jargão de agência,
    sem superlativo, sem promessa de resultado. Frases curtas.

11. **Consistência de nomes.** O nome do cliente, dos módulos e das seções é
    definido uma vez e reusado idêntico em todas as fases.

12. **Dois espelhos, uma verdade.** Onde há `.md` e `.json` para a mesma fase, o
    JSON é o que as máquinas leem e o MD é o que o humano revisa. Divergência
    entre eles é falha detectada por `auditar.py escopo`.
