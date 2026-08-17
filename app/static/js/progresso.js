// Indicador global de execução.
//
// Gerar uma proposta leva de 8 a 40 minutos. Se o retorno visual só existe na
// tela de detalhe, quem navegou para outro lugar não sabe se ainda está
// rodando, em que pé está, nem se deu erro. Este módulo assina os eventos uma
// vez e mantém, em qualquer tela, a resposta para "o que está acontecendo
// agora": cliente, etapa nomeada, quanto falta, há quanto tempo e o que o
// agente está fazendo neste segundo.

import { api } from './api.js';
import { esc } from './fmt.js';
import { ouvir } from './sse.js';

// O comercial não sabe o que é "fase 02". Nome e posição resolvem.
export const FASES = ['01', '02', '03', '04', '05', '06'];
export const NOME_FASE = {
  '01': 'Lendo a reunião',
  '02': 'Montando o escopo',
  '03': 'Calculando o preço',
  '04': 'Escrevendo a proposta',
  '05': 'Montando o documento',
  '06': 'Revisando',
  '06a': 'Gerando o PDF',
  '06b': 'Revisando',
  auditoria: 'Conferindo a tabela de preços',
};

/** Nome curto + posição, para caber numa linha. */
export function rotuloFase(fase) {
  const nome = NOME_FASE[fase] || `Fase ${fase}`;
  const i = FASES.indexOf(String(fase).replace(/[ab]$/, ''));
  return i >= 0 ? `${nome} · ${i + 1} de 6` : nome;
}

export function percentualFase(fase) {
  const i = FASES.indexOf(String(fase).replace(/[ab]$/, ''));
  return i < 0 ? 0 : Math.round(((i + 1) / FASES.length) * 100);
}

// -------------------------------------------------------------- estado vivo

const estado = {
  executando: null,   // {proposta_id, cliente, fase, desde, tentativa}
  aguardando: [],
  ultimaLinha: '',
  desdeFase: null,
};

const assinantes = new Set();

/** Assina o estado de execução. Chamado de imediato com o estado atual. */
export function observar(fn) {
  assinantes.add(fn);
  fn(estado);
  return () => assinantes.delete(fn);
}

function avisar() {
  for (const fn of assinantes) {
    try { fn(estado); } catch (e) { console.error(e); }
  }
}

/** Marca otimista: o clique em "Gerar" tem que responder na hora, sem esperar
 *  o servidor confirmar pelo SSE. */
export function anunciarEnfileiramento(proposta) {
  if (estado.executando) return;      // já há algo rodando; a fila cuida
  estado.executando = {
    proposta_id: proposta.id,
    cliente: proposta.cliente,
    fase: null,
    desde: new Date().toISOString(),
    enfileirando: true,
  };
  estado.ultimaLinha = 'enfileirando…';
  estado.desdeFase = Date.now();
  pintar();
  avisar();
}

// ------------------------------------------------------------------ eventos

function aoFila(dados) {
  const mudouProposta = dados.executando?.proposta_id !== estado.executando?.proposta_id;
  estado.executando = dados.executando;
  estado.aguardando = dados.aguardando || [];
  if (mudouProposta) {
    estado.desdeFase = Date.now();
  }
  // O servidor lembra a última linha: quem abre a tela no meio já vê o que o
  // agente está fazendo, sem esperar o próximo evento.
  if (dados.executando?.ultima_linha) {
    estado.ultimaLinha = dados.executando.ultima_linha;
  } else if (mudouProposta) {
    estado.ultimaLinha = '';
  }
  pintar();
  avisar();
}

function aoFase(dados) {
  if (estado.executando && dados.proposta_id === estado.executando.proposta_id) {
    estado.executando.fase = dados.fase;
    estado.executando.tentativa = dados.tentativa;
    estado.desdeFase = Date.now();
    if (dados.status !== 'executando') estado.ultimaLinha = '';
  }
  pintar();
  avisar();
}

function aoProgresso(dados) {
  estado.ultimaLinha = dados.texto || '';
  pintar();
  avisar();
}

// -------------------------------------------------------------- o cartão

let tick = null;

function decorrido() {
  if (!estado.desdeFase) return '';
  const s = Math.floor((Date.now() - estado.desdeFase) / 1000);
  return s < 60 ? `${s}s` : `${Math.floor(s / 60)}min ${String(s % 60).padStart(2, '0')}s`;
}

function pintar() {
  const caixa = document.getElementById('exec-cartao');
  const contador = document.getElementById('nav-fila');
  if (!caixa || !contador) return;

  const pendentes = estado.aguardando.length + (estado.executando ? 1 : 0);
  contador.textContent = pendentes;
  contador.hidden = pendentes === 0;

  if (!estado.executando) {
    caixa.hidden = true;
    clearInterval(tick);
    tick = null;
    return;
  }

  const e = estado.executando;
  const pct = e.fase ? percentualFase(e.fase) : 4;

  caixa.hidden = false;
  caixa.innerHTML = `
    <a href="#/proposta/${e.proposta_id}" class="exec-topo">
      <span class="girando"></span>
      <span class="exec-cliente">${esc(e.cliente || 'proposta')}</span>
    </a>
    <div class="exec-fase">
      ${esc(e.fase ? rotuloFase(e.fase) : 'preparando')}
      ${e.tentativa > 1 ? `<span class="dim">· tentativa ${e.tentativa}</span>` : ''}
    </div>
    <div class="exec-trilho"><div class="exec-barra" style="width:${pct}%"></div></div>
    <div class="exec-rodape">
      <span class="exec-linha" title="${esc(estado.ultimaLinha)}">${esc(estado.ultimaLinha || 'trabalhando…')}</span>
      <span class="exec-tempo" id="exec-tempo">${decorrido()}</span>
    </div>
    ${estado.aguardando.length
      ? `<div class="exec-fila dim">+${estado.aguardando.length} na fila</div>` : ''}`;

  // O relógio precisa correr mesmo quando o agente fica minutos em silêncio —
  // é o que diferencia "processando" de "travado".
  if (!tick) {
    tick = setInterval(() => {
      const alvo = document.getElementById('exec-tempo');
      if (alvo) alvo.textContent = decorrido();
    }, 1000);
  }
}

// ------------------------------------------------------------------ subida

export async function iniciar() {
  ouvir('fila', aoFila);
  ouvir('fase', aoFase);
  ouvir('progresso', aoProgresso);

  // O SSE já manda o estado inicial da fila ao conectar, mas se o servidor
  // reiniciou sem execução alguma esse evento nunca vem — buscamos uma vez.
  try {
    aoFila(await api.get('/api/fila'));
  } catch { /* o banner de saúde já reporta servidor fora do ar */ }
}

export const estadoAtual = () => estado;
