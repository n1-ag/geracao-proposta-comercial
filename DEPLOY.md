# Deploy — comercialn1.homolog.live

O app roda em `70.35.196.223` (AlmaLinux 9), atrás do nginx que já serve outros
doze sites no mesmo servidor.

```
https://comercialn1.homolog.live
```

## Atualizar

```bash
ssh root@70.35.196.223 n1-atualizar
```

Faz `git pull --ff-only` da `main` e reinicia o serviço. É o único passo: o
código no servidor é um clone do mesmo repositório.

## Como está montado

| | |
|---|---|
| Código | `/opt/n1-propostas` (clone da `main`) |
| Runtime | `/opt/n1-propostas/app/dados/` — banco, lock, estado |
| Workspaces | `/opt/n1-propostas/propostas/` — uma pasta por proposta, com os PDFs |
| Serviço | `n1-propostas.service`, usuário `n1propostas` |
| Config | `/etc/n1-propostas.env` (modo 600, fora do git) |
| nginx | `/etc/nginx/conf.d/comercialn1.homolog.live.conf` |
| Python | `/opt/n1-propostas/.venv` sobre o `python3.11` do sistema |

O app escuta só em `127.0.0.1:7801`. Quem enfrenta a internet é o nginx, que
termina o TLS e faz proxy.

### O usuário do serviço não é o root

`n1propostas`, com home em `/var/lib/n1-propostas` — **fora** do checkout, de
propósito: com o home dentro do código, a credencial do Claude cairia dentro do
repositório git e o `git pull` conflitaria com ela.

O Claude Code guarda credencial por usuário, então a instalação e o
`~/.claude/.credentials.json` foram copiados de `/root` para o home do serviço.
**Quando a autenticação do Claude expirar**, reautentique como root e copie de
novo:

```bash
cp -a /root/.claude/.credentials.json /var/lib/n1-propostas/.claude/
chown n1propostas:n1propostas /var/lib/n1-propostas/.claude/.credentials.json
systemctl restart n1-propostas
```

### O workspace precisa ser confiável

`/var/lib/n1-propostas/.claude.json` marca `/opt/n1-propostas` com
`hasTrustDialogAccepted: true`. Sem isso o Claude Code **ignora em silêncio** as
18 regras de `permissions.allow` do projeto e toda chamada de Bash e Write é
recusada — o pipeline falha em todas as fases, com uma mensagem que não explica
o motivo.

### SSE

O acompanhamento ao vivo é Server-Sent Events. O bloco `/api/eventos` no nginx
tem `proxy_buffering off` e `proxy_read_timeout 3600s`. Com o buffer padrão, o
navegador não receberia nada até a fase terminar — a tela de progresso ficaria
parada justamente quando ela mais importa.

## Acesso

Login em `/login`. O primeiro usuário é semeado na migração do banco e só
enquanto não houver nenhum — trocar a senha e reiniciar não traz o de fábrica de
volta.

Trocar a senha derruba todas as sessões abertas.

## Diagnóstico

```bash
systemctl status n1-propostas
journalctl -u n1-propostas -f
curl -s localhost:7801/api/saude | python3 -m json.tool
```

`/api/saude` responde sem login (é o healthcheck) e diz se Claude Code, Chrome,
Playwright, pypdf e poppler estão no lugar.

## O que não está resolvido

- **Backup**: o banco e os workspaces vivem só neste servidor.
- **Conta compartilhada**: um login para todo o time, sem trilha de quem fez o quê.
- **Fila serial**: uma geração por vez. Com várias pessoas usando, uma espera a outra.
