// Fila de execução. Uma proposta por vez — `entrada/`, `proposta/` e `saida/`
// são singletons do repositório, e duas execuções simultâneas se atropelariam.

import { api } from '../api.js';
import { dataHora, esc, relativo } from '../fmt.js';
import { ouvir } from '../sse.js';

let cancelar = [];
let ultimoProgresso = null;

const NOME_ALVO = {
  bloco_01_03: 'briefing → escopo → orçamento',
  reajuste_02_03: 'reprocessando escopo e orçamento',
  bloco_04_06: 'narrativa → montagem → PDF',
  rerender: 're-gerando o PDF',
};

export function desmontar() {
  cancelar.forEach((f) => f());
  cancelar = [];
}

export async function montar({ conteudo, acoes }) {
  acoes.innerHTML = '';
  await pintar(conteudo);

  cancelar.push(
    ouvir('fila', (dados) => pintar(conteudo, dados)),
    ouvir('progresso', (dados) => {
      ultimoProgresso = dados;
      const alvo = document.getElementById('fila-progresso');
      if (alvo) alvo.textContent = `${dados.fase} · ${dados.texto}`;
    }),
    ouvir('erro', () => pintar(conteudo)),
  );
}

async function pintar(conteudo, dados) {
  const d = dados || (await api.get('/api/fila'));
  const saude = await api.get('/api/saude').catch(() => null);
  conteudo.innerHTML = desenhar(d, saude);
  ligar(conteudo);
}

function desenhar(d, saude) {
  return `
    ${d.executando ? cartaoExecutando(d.executando) : `
      <div class="card vazio">
        <div class="titulo">Nada executando</div>
        <div>Quando você mandar gerar uma proposta, o andamento aparece aqui.</div>
      </div>`}

    ${d.aguardando.length ? `
      <div class="sec card">
        <h2>Na fila</h2>
        <p class="pequeno dim mt0">
          Uma de cada vez: as pastas de trabalho do repositório são compartilhadas,
          então as execuções são serializadas.
        </p>
        <ul class="historico">${d.aguardando.map((e, i) => `
          <li>
            <span class="fase-n">${i + 1}</span>
            <span>${esc(e.cliente)}</span>
            <span class="dim pequeno">${esc(NOME_ALVO[e.alvo] || e.alvo)}
              · enfileirada ${esc(relativo(e.enfileirada_em))}</span>
            <button class="btn pequeno perigo" data-cancelar="${e.id}">cancelar</button>
          </li>`).join('')}</ul>
      </div>` : ''}

    ${saude ? cartaoAmbiente(saude) : ''}`;
}

function cartaoExecutando(e) {
  return `<div class="sec card" style="border:1px solid rgba(60,203,218,.3)">
    <div class="entre">
      <div>
        <h2 class="mb0">${esc(e.cliente)}</h2>
        <div class="pequeno dim">${esc(NOME_ALVO[e.alvo] || e.alvo)}
          · começou ${esc(relativo(e.desde))}</div>
      </div>
      <div class="linha">
        <span class="badge executando">fase ${esc(e.fase)}${e.tentativa > 1 ? ` · tentativa ${e.tentativa}` : ''}</span>
        <a class="btn pequeno" href="#/proposta/${e.proposta_id}">abrir</a>
        <button class="btn pequeno perigo" data-cancelar="${e.execucao_id}">cancelar</button>
      </div>
    </div>
    <div class="progresso-vivo" style="margin:14px 0 0">
      <span class="girando"></span>
      <span id="fila-progresso" class="dim">${esc(
        ultimoProgresso ? `${ultimoProgresso.fase} · ${ultimoProgresso.texto}` : 'aguardando o agente…'
      )}</span>
    </div>
  </div>`;
}

function cartaoAmbiente(s) {
  const a = s.ambiente;
  const item = (nome, ok, extra = '') => `
    <div class="linha-dado">
      <span>${esc(nome)}</span>
      <strong style="color:${ok ? 'var(--ok)' : 'var(--erro)'}">
        ${ok ? 'ok' : 'não encontrado'}${extra ? ` <span class="dim">${esc(extra)}</span>` : ''}
      </strong>
    </div>`;

  return `<div class="sec card">
    <details>
      <summary><strong>Ambiente</strong>
        <span class="dim">— o que o pipeline precisa para rodar</span></summary>
      <div style="margin-top:10px">
        ${item('Claude Code', a.claude.presente, a.claude.versao || '')}
        ${item('Google Chrome', a.chrome, 'render do PDF')}
        ${item('Playwright', a.playwright)}
        ${item('pypdf', a.pypdf, 'metadados do PDF')}
        ${item('poppler-utils', a.poppler, 'auditoria do PDF')}
        <div class="linha-dado"><span>Python</span><strong>${esc(a.python)}</strong></div>
        <div class="linha-dado"><span>Tabela de preços</span><strong>${esc(s.precos_versao || '?')}</strong></div>
        <div class="linha-dado">
          <span>Proposta montada nas pastas do repo</span>
          <strong class="mono">${esc(s.montado || 'nenhuma')}</strong>
        </div>
        ${s.lock ? `<div class="linha-dado"><span>Lock</span>
          <strong class="mono">pid ${esc(String(s.lock.pid))} · ${esc(s.lock.workspace || '')}</strong></div>` : ''}
      </div>
      <p class="pequeno dim" style="margin-top:12px">
        Com o app ligado, não rode <code>/proposta</code> no terminal: os dois disputam
        as mesmas pastas de trabalho.
      </p>
    </details>
  </div>`;
}

function ligar(raiz) {
  raiz.querySelectorAll('[data-cancelar]').forEach((b) =>
    b.addEventListener('click', async () => {
      if (!confirm('Cancelar esta execução? Os artefatos já produzidos são preservados.')) return;
      b.disabled = true;
      try {
        await api.post('/api/fila/cancelar', { execucao_id: Number(b.dataset.cancelar) });
      } catch (err) {
        alert(err.message);
        b.disabled = false;
      }
    }));
}
