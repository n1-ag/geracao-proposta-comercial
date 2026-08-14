// Gráficos em SVG gerado à mão. Sem biblioteca: são três formas simples e uma
// dependência a menos para manter o app offline.

import { esc } from './fmt.js';

// Alternando matiz a cada passo: duas fatias vizinhas nunca saem parecidas.
// (#3CCBDA e #69C7F0 são ambos azuis e ficam indistinguíveis lado a lado.)
const CICLO = ['#3CCBDA', '#F6AB00', '#69C7F0', '#3CDA9B', '#8E7CF0', '#E0596B'];
export const cor = (i) => CICLO[i % CICLO.length];

/** Barras verticais com rótulo embaixo e valor no topo. */
export function barras(dados, { altura = 130, formatar = (v) => v } = {}) {
  if (!dados.length) return '<div class="dim pequeno">sem dados ainda</div>';

  const max = Math.max(...dados.map((d) => d.valor), 1);
  const larguraBarra = 100 / dados.length;

  const colunas = dados.map((d, i) => {
    const alt = Math.max(2, (d.valor / max) * (altura - 26));
    return `
      <div class="barra-col" style="width:${larguraBarra}%" title="${esc(d.rotulo)}: ${esc(formatar(d.valor))}">
        <div class="barra-valor">${esc(formatar(d.valor))}</div>
        <div class="barra" style="height:${alt}px;opacity:${0.45 + 0.55 * (d.valor / max)}"></div>
        <div class="barra-rotulo">${esc(d.rotulo)}</div>
      </div>`;
  }).join('');

  return `<div class="barras" style="height:${altura + 22}px">${colunas}</div>`;
}

/** Funil horizontal: uma faixa por etapa, largura proporcional à contagem. */
export function funil(etapas, { formatarValor = (v) => v } = {}) {
  if (!etapas.length) return '<div class="dim pequeno">sem propostas ainda</div>';

  const max = Math.max(...etapas.map((e) => e.n), 1);
  return `<div class="funil">${etapas.map((e, i) => `
    <div class="funil-linha">
      <div class="funil-rotulo">${esc(e.rotulo)}</div>
      <div class="funil-trilho">
        <div class="funil-barra" style="width:${(e.n / max) * 100}%;background:${cor(i)}"></div>
      </div>
      <div class="funil-n">${e.n}</div>
      <div class="funil-valor dim">${esc(formatarValor(e.valor))}</div>
    </div>`).join('')}</div>`;
}

/** Rosca. Devolve SVG puro para não depender de layout externo. */
export function rosca(fatias, { tamanho = 132, espessura = 15 } = {}) {
  const total = fatias.reduce((s, f) => s + f.valor, 0);
  if (!total) return '<div class="dim pequeno">sem dados ainda</div>';

  const r = (tamanho - espessura) / 2;
  const c = tamanho / 2;
  const circ = 2 * Math.PI * r;

  let percorrido = 0;
  const arcos = fatias.map((f, i) => {
    const fracao = f.valor / total;
    const arco = `${(fracao * circ).toFixed(2)} ${circ.toFixed(2)}`;
    // -25% roda o início para o topo; o offset negativo acumula no sentido horário.
    const deslocamento = -percorrido * circ;
    percorrido += fracao;
    return `<circle cx="${c}" cy="${c}" r="${r}" fill="none"
      stroke="${cor(i)}" stroke-width="${espessura}"
      stroke-dasharray="${arco}" stroke-dashoffset="${deslocamento.toFixed(2)}"
      transform="rotate(-90 ${c} ${c})"><title>${esc(f.rotulo)}: ${f.valor}</title></circle>`;
  }).join('');

  const legenda = fatias.map((f, i) => `
    <div class="legenda-item">
      <span class="legenda-cor" style="background:${cor(i)}"></span>
      <span class="legenda-nome">${esc(f.rotulo)}</span>
      <span class="legenda-n dim">${f.valor}</span>
    </div>`).join('');

  return `<div class="rosca-caixa">
    <svg width="${tamanho}" height="${tamanho}" viewBox="0 0 ${tamanho} ${tamanho}">${arcos}</svg>
    <div class="legenda">${legenda}</div>
  </div>`;
}
