// Bootstrap e roteador de hash. Uma casca, várias telas; cada tela é um módulo
// com montar(alvo, params) e, opcionalmente, desmontar().

import { api, ErroApi } from './api.js';
import { esc } from './fmt.js';
import { ouvir } from './sse.js';
import * as progresso from './progresso.js';

const conteudo = document.getElementById('conteudo');
const tituloEl = document.getElementById('titulo');
const acoesEl = document.getElementById('acoes');

// -------------------------------------------------------------- roteamento

// Cada entrada: [regex do hash, título, carregador do módulo].
const ROTAS = [
  [/^#?\/?$/,                        'Painel',          () => import('./views/painel.js')],
  [/^#\/painel$/,                    'Painel',          () => import('./views/painel.js')],
  [/^#\/nova$/,                      'Nova proposta',   () => import('./views/novaproposta.js')],
  [/^#\/nova\/(?<id>\d+)$/,           'Editar proposta', () => import('./views/novaproposta.js')],
  [/^#\/propostas$/,                 'Propostas',       () => import('./views/lista.js')],
  [/^#\/fila$/,                      'Fila',            () => import('./views/fila.js')],
  [/^#\/proposta\/(?<id>\d+)$/,      'Proposta',        () => import('./views/detalhe.js')],
  [/^#\/proposta\/(?<id>\d+)\/aprovar$/, 'Aprovação',   () => import('./views/aprovacao.js')],
];

let telaAtual = null;

async function navegar() {
  const hash = location.hash || '#/painel';

  const achou = ROTAS.find(([rx]) => rx.test(hash));
  if (!achou) {
    tituloEl.textContent = 'Não encontrado';
    acoesEl.innerHTML = '';
    conteudo.innerHTML = `<div class="vazio">
      <div class="titulo">Esta tela não existe</div>
      <div>${esc(hash)}</div>
    </div>`;
    return;
  }

  const [rx, titulo, carregar] = achou;
  const params = rx.exec(hash)?.groups || {};

  if (telaAtual?.desmontar) {
    try { telaAtual.desmontar(); } catch (e) { console.error(e); }
  }
  telaAtual = null;

  tituloEl.textContent = titulo;
  acoesEl.innerHTML = '';
  conteudo.innerHTML = '<div class="carregando">carregando…</div>';
  marcarNav(hash);

  try {
    const modulo = await carregar();
    telaAtual = modulo;
    await modulo.montar({ conteudo, acoes: acoesEl, titulo: tituloEl, params });
  } catch (e) {
    console.error(e);
    conteudo.innerHTML = `<div class="aviso-faixa erro">
      <strong>Não deu para abrir esta tela.</strong><br>${esc(e.message || e)}
    </div>`;
  }
}

function marcarNav(hash) {
  const base = '#/' + (hash.split('/')[1] || 'painel');
  document.querySelectorAll('#nav a').forEach((a) => {
    a.classList.toggle('ativo', a.getAttribute('href') === base);
  });
}

// ------------------------------------------------------------------ saúde

const bolinha = document.getElementById('saude-bolinha');
const saudeTexto = document.getElementById('saude-texto');

/** O que o pipeline precisa e o rótulo para quem não é técnico. */
const REQUISITOS = [
  ['claude', 'Claude Code'],
  ['chrome', 'Google Chrome'],
  ['playwright', 'Playwright'],
  ['pypdf', 'pypdf'],
  ['poppler', 'poppler-utils'],
];

export let saude = null;

async function checarSaude() {
  try {
    saude = await api.get('/api/saude');
  } catch (e) {
    bolinha.className = 'bolinha ruim';
    saudeTexto.textContent = 'servidor fora do ar';
    return;
  }

  const amb = saude.ambiente;
  const faltando = REQUISITOS
    .filter(([k]) => (k === 'claude' ? !amb.claude.presente : !amb[k]))
    .map(([, nome]) => nome);

  if (faltando.length === 0) {
    bolinha.className = 'bolinha ok';
    saudeTexto.textContent = `pronto · preços ${saude.precos_versao || '?'}`;
    saudeTexto.title = '';
  } else {
    bolinha.className = 'bolinha ruim';
    saudeTexto.textContent = `faltando ${faltando.length}`;
    saudeTexto.title = `Não encontrei: ${faltando.join(', ')}`;
  }
}

// ------------------------------------------------------------- avisos globais

// Alguns avisos valem para a sessão inteira, não para uma tela: bater no limite
// de uso da conta mata a execução em curso e todas as próximas até o reset.
const TEMPO_DO_AVISO = { rate_limit: 0, reconectado: 4000 };  // 0 = fica até fechar

function avisar({ tipo, mensagem }) {
  document.getElementById('aviso-global')?.remove();

  const faixa = document.createElement('div');
  faixa.id = 'aviso-global';
  faixa.className = `aviso-global ${tipo === 'rate_limit' ? 'erro' : 'info'}`;
  faixa.innerHTML = `<span>${esc(mensagem)}</span>
    <button class="btn pequeno" id="fechar-aviso">fechar</button>`;
  document.body.appendChild(faixa);
  faixa.querySelector('#fechar-aviso').onclick = () => faixa.remove();

  const vida = TEMPO_DO_AVISO[tipo] ?? 8000;
  if (vida) setTimeout(() => faixa.remove(), vida);
}

ouvir('aviso', (dados) => {
  if (dados.tipo === 'rate_limit') {
    avisar({
      tipo: 'rate_limit',
      mensagem: `Limite de uso da conta atingido${dados.mensagem.includes('reseta') ? ` — ${dados.mensagem}` : ''}. `
        + 'As execuções em andamento param aqui; retome depois do reset.',
    });
  } else if (dados.tipo !== 'reconectado') {
    avisar(dados);
  }
});

ouvir('erro', (dados) => {
  avisar({ tipo: 'erro', mensagem: dados.mensagem });
});

// ------------------------------------------------------------------ subida

window.addEventListener('hashchange', navegar);

checarSaude();
setInterval(checarSaude, 30000);
progresso.iniciar();
navegar();
