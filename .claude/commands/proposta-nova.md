---
description: Encerra a proposta atual e prepara o repositório para a próxima — arquivando, descartando ou zerando tudo. Rode entre um cliente e outro.
argument-hint: "[--descartar] [--reset]"
---

Encerramento e preparação para a próxima proposta. Argumentos: `$ARGUMENTS`.

`proposta/` e `saida/` são pastas de trabalho de **uma proposta por vez** — o
repositório não é duplicado por cliente, porque `dados/` precisa continuar sendo
fonte única de preço.

## 1. Mostre o que está em andamento

Leia `proposta/manifest.json`, se existir, e diga de quem é a proposta atual, em
que fase está e se o PDF chegou a ser gerado. Liste também o histórico:

```
python3 scripts/arquivar.py --listar
```

**Se houver proposta em andamento sem PDF final**, avise antes de seguir: o
trabalho será guardado (ou perdido, no descarte), mas está incompleto.

## 2. Escolha o modo

| Argumento | O que faz | Quando |
|---|---|---|
| *(nenhum)* | arquiva em `arquivo/<cliente>-<data>/` | o normal: a proposta saiu |
| `--descartar` | apaga sem guardar cópia | teste, ou proposta abortada que não interessa |
| `--reset` | apaga **e** devolve `entrada/` ao exemplo | recomeçar do zero, do jeito que o repositório veio |

```
python3 scripts/arquivar.py            # arquivar
python3 scripts/arquivar.py --limpar   # --descartar
python3 scripts/arquivar.py --reset    # --reset
```

Os dois modos destrutivos pedem confirmação digitada. **Não passe `--sim`** para
pular isso a não ser que o usuário tenha pedido explicitamente.

Nenhum modo toca em `dados/`, `specs/`, `templates/` ou nas propostas já
arquivadas. Preço, contratos e histórico não são estado de proposta.

## 3. Oriente os próximos passos

- substituir `entrada/transcricao.md` pela transcrição do novo cliente;
- preencher `entrada/dados-cliente.md` — campo que não souber, deixar em branco;
- rodar `/proposta`.

## 4. Lembre do que não fica aqui

`arquivo/` está **fora do git** — é dado de cliente. Se a proposta precisa ser
guardada em lugar durável, o PDF vai para o Drive ou o CRM, não fica só nesta
máquina.
