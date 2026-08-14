// Formatação. Os valores monetários que vêm do orçamento já chegam formatados
// pelo precificar.py (campos *_fmt) e NÃO são reformatados aqui — reformatar
// arriscaria divergir do que está impresso no PDF. Estas funções servem só para
// números que o app calcula: somas do dashboard, contagens, durações.

const BRL = new Intl.NumberFormat('pt-BR', {
  style: 'currency', currency: 'BRL', minimumFractionDigits: 2,
});
const NUM = new Intl.NumberFormat('pt-BR');

export const brl = (v) => (v == null ? '—' : BRL.format(v));
export const num = (v) => (v == null ? '—' : NUM.format(v));

export function pct(v, casas = 1) {
  if (v == null) return '—';
  return `${v.toFixed(casas).replace('.', ',')}%`;
}

export function data(iso) {
  if (!iso) return '—';
  const d = new Date(iso.length <= 10 ? `${iso}T12:00:00` : iso);
  if (isNaN(d)) return iso;
  return d.toLocaleDateString('pt-BR');
}

export function dataHora(iso) {
  if (!iso) return '—';
  const d = new Date(iso);
  if (isNaN(d)) return iso;
  return d.toLocaleString('pt-BR', { dateStyle: 'short', timeStyle: 'short' });
}

export function duracao(ms) {
  if (ms == null) return '—';
  const s = Math.round(ms / 1000);
  if (s < 60) return `${s}s`;
  const m = Math.floor(s / 60);
  if (m < 60) return `${m}min ${s % 60}s`;
  return `${Math.floor(m / 60)}h ${m % 60}min`;
}

export function relativo(iso) {
  if (!iso) return '—';
  const d = new Date(iso);
  if (isNaN(d)) return iso;
  const seg = (Date.now() - d.getTime()) / 1000;
  if (seg < 60) return 'agora';
  if (seg < 3600) return `há ${Math.floor(seg / 60)} min`;
  if (seg < 86400) return `há ${Math.floor(seg / 3600)} h`;
  if (seg < 604800) return `há ${Math.floor(seg / 86400)} d`;
  return data(iso);
}

export function slug(s) {
  return (s || '')
    .normalize('NFD').replace(/[\u0300-\u036f]/g, '')
    .toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '');
}

/** Escapa texto para interpolação segura em template de HTML. */
export function esc(s) {
  return String(s ?? '').replace(/[&<>"']/g, (c) => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
  }[c]));
}

const ROTULOS = {
  rascunho: 'Rascunho',
  enfileirada: 'Na fila',
  executando_01_03: 'Executando 01→03',
  executando_02_03: 'Reprocessando 02→03',
  aguardando_aprovacao: 'Aguardando aprovação',
  executando_04_06: 'Gerando PDF',
  gerada: 'Gerada',
  erro: 'Erro',
  arquivada: 'Arquivada',
  enviada: 'Enviada',
  aceita: 'Aceita',
  recusada: 'Recusada',
};

const CLASSES = {
  rascunho: 'rascunho',
  enfileirada: 'aguardando',
  executando_01_03: 'executando',
  executando_02_03: 'executando',
  aguardando_aprovacao: 'aguardando',
  executando_04_06: 'executando',
  gerada: 'gerada',
  erro: 'erro',
  arquivada: 'rascunho',
  enviada: 'enviada',
  aceita: 'aceita',
  recusada: 'recusada',
};

/** O badge combina as duas dimensões: o comercial tem precedência sobre o
 *  operacional, porque "aceita" diz mais que "gerada". */
export function badge(status, statusComercial) {
  const chave = statusComercial || status;
  return `<span class="badge ${CLASSES[chave] || 'rascunho'}">${ROTULOS[chave] || chave}</span>`;
}

export const rotulo = (chave) => ROTULOS[chave] || chave;
