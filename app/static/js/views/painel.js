// Painel — os quatro recortes: funil, valores, produção no tempo e negócio.

import { api } from '../api.js';
import { brl, num, pct, esc, badge, relativo, rotulo } from '../fmt.js';
import * as g from '../graficos.js';

const NOME_PLATAFORMA = {
  shopify: 'Shopify', vtex: 'VTEX', wake: 'Wake', nuvemshop: 'Nuvemshop',
  wordpress: 'WordPress', 'template-html': 'Template HTML',
};
const NOME_MODELO = { implantacao: 'Implantação', evolucao: 'Evolução' };

const MES = ['jan','fev','mar','abr','mai','jun','jul','ago','set','out','nov','dez'];
function rotuloMes(periodo) {
  const [a, m] = (periodo || '').split('-');
  return m ? `${MES[+m - 1]}/${a.slice(2)}` : periodo;
}

export async function montar({ conteudo, acoes }) {
  acoes.innerHTML = `<a class="btn primario" href="#/nova">Nova proposta</a>`;

  const d = await api.get('/api/dashboard');
  const v = d.valores;
  const f = d.funil;
  const p = d.pendencias;

  conteudo.innerHTML = `
    ${faixaPendencias(p)}

    <div class="sec">
      <div class="grid k4">
        ${kpi('Propostas', num(v.total_propostas), rodapeContagem(f, p))}
        ${kpi('Em aberto', brl(v.em_aberto), 'enviadas, aguardando resposta', 'ciano')}
        ${kpi('Aceito', brl(v.total_aceito), taxaTexto(f), 'ok')}
        ${kpi('Ticket médio', brl(v.ticket_medio_geral), tickeTexto(v))}
      </div>
    </div>

    <div class="sec grid k2">
      <div class="card">
        <h2>Funil</h2>
        <p class="pequeno dim mt0">Valores anualizados: propostas de evolução entram como 12× o mensal.</p>
        ${g.funil(etapasDoFunil(f), { formatarValor: brl })}
        ${resumoConversao(f)}
      </div>

      <div class="card">
        <h2>Produção</h2>
        <p class="pequeno dim mt0">PDFs gerados por mês.</p>
        ${g.barras(d.producao.por_mes.map((m) => ({ rotulo: rotuloMes(m.periodo), valor: m.geradas })))}
        ${tempos(d.producao)}
      </div>
    </div>

    <div class="sec grid k2">
      ${cardRecorte('Por plataforma', d.recortes.plataformas, NOME_PLATAFORMA)}
      ${cardRecorte('Por modelo', d.recortes.modelos, NOME_MODELO)}
    </div>

    <div class="sec">
      <div class="entre" style="margin-bottom:12px">
        <h2>Últimas propostas</h2>
        <a href="#/propostas" class="pequeno">ver todas</a>
      </div>
      ${tabelaRecentes(d.recentes)}
    </div>`;
}

// ------------------------------------------------------------------ pedaços

function kpi(rot, valor, nota, classe = '') {
  return `<div class="card kpi">
    <div class="rotulo">${esc(rot)}</div>
    <div class="valor ${classe}">${esc(valor)}</div>
    <div class="nota">${esc(nota)}</div>
  </div>`;
}

function rodapeContagem(f, p) {
  const partes = [];
  if (p.executando) partes.push(`${p.executando} executando`);
  if (p.na_fila) partes.push(`${p.na_fila} na fila`);
  if (p.aguardando_aprovacao) partes.push(`${p.aguardando_aprovacao} aguardando você`);
  return partes.join(' · ') || `${f.enviadas} já enviadas`;
}

function taxaTexto(f) {
  if (f.taxa_aceite_pct == null) return 'nenhuma proposta enviada ainda';
  return `${pct(f.taxa_aceite_pct)} das ${f.enviadas} enviadas`;
}

function tickeTexto(v) {
  if (!v.ticket_medio_aceito) return 'sobre todas as propostas com valor';
  return `${brl(v.ticket_medio_aceito)} entre as aceitas`;
}

function faixaPendencias(p) {
  const avisos = [];
  if (p.com_erro) {
    avisos.push(`<div class="aviso-faixa erro">
      <strong>${p.com_erro} proposta(s) com erro.</strong>
      <a href="#/propostas">Ver quais</a> — dá para retomar da fase que falhou.
    </div>`);
  }
  if (p.aguardando_aprovacao) {
    avisos.push(`<div class="aviso-faixa aviso">
      <strong>${p.aguardando_aprovacao} orçamento(s) esperando sua aprovação.</strong>
      Enquanto ninguém aprova, o PDF não é gerado.
    </div>`);
  }
  if (p.alertas_altos.length) {
    const lista = p.alertas_altos
      .map((a) => `<a href="#/proposta/${a.id}">${esc(a.cliente)}</a> <span class="mono dim">${esc(a.codigo)}</span>`)
      .join(' · ');
    avisos.push(`<div class="aviso-faixa info">
      <strong>Alertas altos em aberto:</strong> ${lista}
    </div>`);
  }
  return avisos.join('');
}

function etapasDoFunil(f) {
  // Ordem do funil, não ordem de contagem: o desenho tem que ler como um
  // caminho, da esquerda para a direita da vida da proposta.
  const ORDEM = [
    'rascunho', 'enfileirada', 'executando_01_03', 'executando_02_03',
    'aguardando_aprovacao', 'executando_04_06', 'gerada', 'erro',
    'enviada', 'aceita', 'recusada',
  ];
  const porChave = Object.fromEntries(f.etapas.map((e) => [e.etapa, e]));
  return ORDEM
    .filter((k) => porChave[k])
    .map((k) => ({ rotulo: rotulo(k), n: porChave[k].n, valor: porChave[k].valor }));
}

function resumoConversao(f) {
  if (!f.enviadas) return '';
  const linhas = [`<strong>${f.aceitas}</strong> de <strong>${f.enviadas}</strong> enviadas viraram sim`];
  if (f.taxa_aceite_decididas_pct != null && f.taxa_aceite_decididas_pct !== f.taxa_aceite_pct) {
    linhas.push(`${pct(f.taxa_aceite_decididas_pct)} considerando só quem já respondeu`);
  }
  return `<div class="pequeno dim" style="margin-top:14px">${linhas.join(' · ')}</div>`;
}

function tempos(prod) {
  const itens = [
    ['do cadastro ao PDF', prod.horas_cadastro_ate_pdf, 'h'],
    ['de máquina', prod.minutos_de_maquina, 'min'],
    ['parado no gate', prod.horas_no_gate, 'h'],
  ].filter(([, v]) => v != null);

  if (!itens.length) return '';
  return `<div class="tempos">${itens.map(([rot, v, un]) =>
    `<div><span class="tempo-num">${num(v)}${un}</span><span class="dim pequeno"> ${esc(rot)}</span></div>`
  ).join('')}</div>`;
}

function cardRecorte(titulo, linhas, nomes) {
  if (!linhas.length) {
    return `<div class="card"><h2>${esc(titulo)}</h2>
      <div class="dim pequeno">sem dados ainda</div></div>`;
  }
  const fatias = linhas.map((l) => ({ rotulo: nomes[l.chave] || l.chave, valor: l.n }));
  const tabela = linhas.map((l) => `
    <tr>
      <td>${esc(nomes[l.chave] || l.chave)}</td>
      <td class="num">${l.n}</td>
      <td class="num">${esc(brl(l.valor))}</td>
      <td class="num">${l.taxa_aceite_pct == null ? '<span class="dim">—</span>' : esc(pct(l.taxa_aceite_pct))}</td>
    </tr>`).join('');

  return `<div class="card">
    <h2>${esc(titulo)}</h2>
    ${g.rosca(fatias)}
    <table class="lista compacta" style="margin-top:14px">
      <thead><tr><th></th><th class="num">Prop.</th><th class="num">Valor</th><th class="num">Aceite</th></tr></thead>
      <tbody>${tabela}</tbody>
    </table>
  </div>`;
}

function tabelaRecentes(linhas) {
  if (!linhas.length) {
    return `<div class="card vazio">
      <div class="titulo">Nenhuma proposta ainda</div>
      <div>Comece por <a href="#/nova">Nova proposta</a>.</div>
    </div>`;
  }
  const corpo = linhas.map((l) => `
    <tr onclick="location.hash='#/proposta/${l.id}'" style="cursor:pointer">
      <td>${esc(l.cliente)}</td>
      <td class="dim">${esc(NOME_PLATAFORMA[l.plataforma_res || l.plataforma] || '—')}</td>
      <td>${badge(l.status, l.status_comercial)}</td>
      <td class="num">${l.total_fmt ? esc(l.total_fmt) + (l.total_tipo === 'mensal' ? '<span class="dim">/mês</span>' : '') : '<span class="dim">—</span>'}</td>
      <td class="dim">${esc(relativo(l.atualizado_em))}</td>
    </tr>`).join('');

  return `<div class="card" style="padding:6px 4px">
    <table class="lista">
      <thead><tr><th>Cliente</th><th>Plataforma</th><th>Status</th><th class="num">Valor</th><th>Atualizada</th></tr></thead>
      <tbody>${corpo}</tbody>
    </table>
  </div>`;
}
