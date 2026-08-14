// Listagem de propostas, com filtros e o status comercial editável na linha.

import { api } from '../api.js';
import { badge, brl, esc, relativo } from '../fmt.js';
import { ouvir } from '../sse.js';
import { perguntarExclusao } from '../dialogo.js';

let filtros = { q: '', status: '', comercial: '', plataforma: '', incluir_arquivadas: '' };
let catalogo = null;
let cancelar = [];

const NOME_PLATAFORMA = {
  shopify: 'Shopify', vtex: 'VTEX', wake: 'Wake', nuvemshop: 'Nuvemshop',
  wordpress: 'WordPress', 'template-html': 'Template HTML',
};

const ARQUIVADAS = [
  ['', 'ativas'],
  ['1', 'incluir as removidas'],
];

const ESTADOS = [
  ['', 'todos os estados'],
  ['rascunho', 'Rascunho'],
  ['aguardando_aprovacao', 'Aguardando aprovação'],
  ['gerada', 'Gerada'],
  ['erro', 'Com erro'],
];
const COMERCIAIS = [
  ['', 'qualquer situação'],
  ['sem', 'ainda não enviada'],
  ['enviada', 'Enviada'],
  ['aceita', 'Aceita'],
  ['recusada', 'Recusada'],
];

export function desmontar() {
  cancelar.forEach((f) => f());
  cancelar = [];
}

export async function montar({ conteudo, acoes }) {
  acoes.innerHTML = `<a class="btn primario" href="#/nova">Nova proposta</a>`;
  catalogo ||= await api.get('/api/catalogo');

  conteudo.innerHTML = `
    <div class="sec filtros" id="filtros">
      <input type="search" id="f-q" placeholder="buscar por cliente, razão social ou contato"
             value="${esc(filtros.q)}">
      ${select('f-status', ESTADOS, filtros.status)}
      ${select('f-comercial', COMERCIAIS, filtros.comercial)}
      ${select('f-plataforma',
        [['', 'todas as plataformas'], ...catalogo.plataformas.map((p) => [p.id, p.nome])],
        filtros.plataforma)}
      ${select('f-arquivadas', ARQUIVADAS, filtros.incluir_arquivadas)}
      <button class="btn pequeno" id="f-limpar">limpar</button>
    </div>
    <div id="resultado"><div class="carregando">carregando…</div></div>`;

  ligarFiltros(conteudo);
  await recarregar();

  // Uma execução que termina em outra aba muda esta lista.
  cancelar.push(ouvir('proposta', () => recarregar()));
}

function select(id, opcoes, atual) {
  return `<select id="${id}">${opcoes
    .map(([v, t]) => `<option value="${esc(v)}" ${v === atual ? 'selected' : ''}>${esc(t)}</option>`)
    .join('')}</select>`;
}

let debounce = null;
let ultimoResultado = [];

function ligarFiltros(raiz) {
  raiz.querySelector('#f-q').addEventListener('input', (e) => {
    filtros.q = e.target.value;
    clearTimeout(debounce);
    debounce = setTimeout(recarregar, 250);
  });
  for (const [campo, id] of [['status', '#f-status'], ['comercial', '#f-comercial'],
                             ['plataforma', '#f-plataforma'],
                             ['incluir_arquivadas', '#f-arquivadas']]) {
    raiz.querySelector(id).addEventListener('change', (e) => {
      filtros[campo] = e.target.value;
      recarregar();
    });
  }
  raiz.querySelector('#f-limpar').addEventListener('click', () => {
    filtros = { q: '', status: '', comercial: '', plataforma: '', incluir_arquivadas: '' };
    raiz.querySelector('#f-q').value = '';
    ['#f-status', '#f-comercial', '#f-plataforma', '#f-arquivadas']
      .forEach((s) => { raiz.querySelector(s).value = ''; });
    recarregar();
  });
}

async function recarregar() {
  const alvo = document.getElementById('resultado');
  if (!alvo) return;

  const params = new URLSearchParams(
    Object.entries(filtros).filter(([, v]) => v)
  );
  const d = await api.get(`/api/propostas?${params}`);
  ultimoResultado = d.itens;
  alvo.innerHTML = desenhar(d);
  ligarLinhas(alvo);
}

function desenhar(d) {
  if (!d.itens.length) {
    return `<div class="card vazio">
      <div class="titulo">Nenhuma proposta encontrada</div>
      <div>${Object.values(filtros).some(Boolean)
        ? 'Tente afrouxar os filtros.'
        : 'Comece por <a href="#/nova">Nova proposta</a>.'}</div>
    </div>`;
  }

  const linhas = d.itens.map((p) => `
    <tr data-id="${p.id}" class="${p.arquivada ? 'removida' : ''}">
      <td class="clicavel">
        <div>${esc(p.cliente)}</div>
        ${p.contato ? `<div class="dim pequeno">${esc(p.contato)}</div>` : ''}
      </td>
      <td class="clicavel dim">${esc(NOME_PLATAFORMA[p.plataforma_res || p.plataforma] || '—')}</td>
      <td class="clicavel">
        ${badge(p.status, p.status_comercial)}
        ${p.arquivada ? '<span class="badge rascunho">removida</span>' : ''}
        ${p.erro_mensagem ? `<div class="pequeno" style="color:var(--erro)">${esc(p.erro_mensagem.slice(0, 70))}</div>` : ''}
      </td>
      <td class="clicavel num">
        ${p.total_fmt ? esc(p.total_fmt) + (p.total_tipo === 'mensal' ? '<span class="dim">/mês</span>' : '')
                      : '<span class="dim">—</span>'}
      </td>
      <td class="clicavel dim">${esc(relativo(p.atualizado_em))}</td>
      <td class="acoes-linha">
        ${p.arquivada ? `<button class="btn pequeno" data-restaurar="${p.id}">Trazer de volta</button>` : `
          ${p.status === 'aguardando_aprovacao'
            ? `<a class="btn pequeno primario" href="#/proposta/${p.id}/aprovar">Aprovar</a>` : ''}
          ${p.pdf_caminho
            ? `<a class="btn pequeno" href="/api/propostas/${p.id}/pdf" target="_blank">PDF</a>` : ''}
          ${p.status === 'gerada' ? seletorComercial(p) : ''}
        `}
        <button class="btn pequeno perigo" data-excluir="${p.id}" title="excluir proposta">×</button>
      </td>
    </tr>`).join('');

  return `<div class="card" style="padding:6px 4px">
    <table class="lista">
      <thead><tr>
        <th>Cliente</th><th>Plataforma</th><th>Status</th>
        <th class="num">Valor</th><th>Atualizada</th><th></th>
      </tr></thead>
      <tbody>${linhas}</tbody>
    </table>
  </div>
  <div class="dim pequeno" style="margin-top:10px">
    ${d.total} proposta(s)${d.total > d.itens.length ? ` · mostrando ${d.itens.length}` : ''}
  </div>`;
}

function seletorComercial(p) {
  const opcoes = [['', '—'], ['enviada', 'Enviada'], ['aceita', 'Aceita'], ['recusada', 'Recusada']];
  return `<select class="sel-comercial" data-id="${p.id}" title="status comercial">
    ${opcoes.map(([v, t]) =>
      `<option value="${v}" ${(p.status_comercial || '') === v ? 'selected' : ''}>${t}</option>`).join('')}
  </select>`;
}

function ligarLinhas(raiz) {
  raiz.querySelectorAll('td.clicavel').forEach((td) => {
    td.style.cursor = 'pointer';
    td.addEventListener('click', () => {
      location.hash = `#/proposta/${td.closest('tr').dataset.id}`;
    });
  });

  raiz.querySelectorAll('[data-excluir]').forEach((b) =>
    b.addEventListener('click', async () => {
      const p = ultimoResultado.find((x) => x.id === Number(b.dataset.excluir));
      if (!p) return;
      const escolha = await perguntarExclusao(p);
      if (!escolha) return;
      b.disabled = true;
      const url = escolha === 'purgar'
        ? `/api/propostas/${p.id}?purgar=1&confirmacao=${encodeURIComponent(p.cliente)}`
        : `/api/propostas/${p.id}`;
      try {
        await api.del(url);
        recarregar();
      } catch (err) {
        alert(err.message);
        b.disabled = false;
      }
    }));

  raiz.querySelectorAll('[data-restaurar]').forEach((b) =>
    b.addEventListener('click', async () => {
      b.disabled = true;
      try {
        await api.post(`/api/propostas/${b.dataset.restaurar}/restaurar`);
        recarregar();
      } catch (err) {
        alert(err.message);
        b.disabled = false;
      }
    }));

  raiz.querySelectorAll('.sel-comercial').forEach((sel) => {
    sel.addEventListener('change', async () => {
      const anterior = sel.dataset.anterior ?? '';
      try {
        await api.post(`/api/propostas/${sel.dataset.id}/status`,
                       { status_comercial: sel.value || null });
        recarregar();
      } catch (err) {
        alert(err.message);
        sel.value = anterior;
      }
    });
    sel.dataset.anterior = sel.value;
  });
}
