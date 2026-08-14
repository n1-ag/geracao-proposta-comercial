// Renderizador de Markdown mínimo, só o que os artefatos do pipeline usam:
// títulos, tabelas, listas, negrito/itálico, código e citação.
//
// Não é um parser completo e não pretende ser — é o suficiente para a memória
// de cálculo e o briefing ficarem legíveis, sem trazer uma biblioteca para um
// app que precisa rodar offline.

import { esc } from './fmt.js';

/** Trechos inline: código, negrito, itálico, link. Escapa antes de tudo. */
function inline(texto) {
  let s = esc(texto);
  s = s.replace(/`([^`]+)`/g, '<code>$1</code>');
  s = s.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>');
  s = s.replace(/(^|\W)_([^_]+)_(?=\W|$)/g, '$1<em>$2</em>');
  s = s.replace(/(^|[^*])\*([^*]+)\*/g, '$1<em>$2</em>');
  s = s.replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href="$2" target="_blank" rel="noopener">$1</a>');
  // Marcadores de evidência viram pílula clicável — é a rastreabilidade do
  // pipeline aparecendo na interface.
  s = s.replace(/\[([EO]\d{2})\]/g, '<span class="pill-evidencia" data-ev="$1">$1</span>');
  return s;
}

const alinhamento = (celula) => {
  const c = celula.trim();
  if (c.startsWith(':') && c.endsWith(':')) return ' style="text-align:center"';
  if (c.endsWith(':')) return ' style="text-align:right"';
  return '';
};

const celulas = (linha) =>
  linha.replace(/^\||\|$/g, '').split('|').map((c) => c.trim());

export function render(markdown) {
  const linhas = (markdown || '').replace(/\r\n/g, '\n').split('\n');
  const saida = [];
  let i = 0;

  // Frontmatter YAML: os artefatos começam com um, e mostrá-lo cru só polui.
  if (linhas[0]?.trim() === '---') {
    const fim = linhas.indexOf('---', 1);
    if (fim > 0) i = fim + 1;
  }

  let emLista = null;   // 'ul' | 'ol'
  let emCodigo = false;

  const fecharLista = () => {
    if (emLista) { saida.push(`</${emLista}>`); emLista = null; }
  };

  for (; i < linhas.length; i++) {
    const linha = linhas[i];

    if (linha.trim().startsWith('```')) {
      fecharLista();
      saida.push(emCodigo ? '</code></pre>' : '<pre class="bloco-codigo"><code>');
      emCodigo = !emCodigo;
      continue;
    }
    if (emCodigo) { saida.push(esc(linha)); continue; }

    if (!linha.trim()) { fecharLista(); continue; }

    const titulo = linha.match(/^(#{1,6})\s+(.*)$/);
    if (titulo) {
      fecharLista();
      const nivel = Math.min(titulo[1].length + 1, 6); // h1 do artefato vira h2 na tela
      saida.push(`<h${nivel}>${inline(titulo[2])}</h${nivel}>`);
      continue;
    }

    if (/^\s*([-*_])\1{2,}\s*$/.test(linha)) { fecharLista(); saida.push('<hr>'); continue; }

    // Tabela: precisa da linha separadora logo abaixo do cabeçalho.
    if (linha.includes('|') && /^\s*\|?[\s:|-]+\|[\s:|-]*$/.test(linhas[i + 1] || '')) {
      fecharLista();
      const cabecalho = celulas(linha);
      const alinhas = celulas(linhas[i + 1]);
      const corpo = [];
      i += 2;
      while (i < linhas.length && linhas[i].includes('|')) {
        corpo.push(celulas(linhas[i]));
        i++;
      }
      i--;
      saida.push('<div class="tabela-rolavel"><table class="md">');
      saida.push('<thead><tr>' + cabecalho
        .map((c, k) => `<th${alinhamento(alinhas[k] || '')}>${inline(c)}</th>`).join('') + '</tr></thead>');
      saida.push('<tbody>' + corpo
        .map((l) => '<tr>' + l.map((c, k) => `<td${alinhamento(alinhas[k] || '')}>${inline(c)}</td>`).join('') + '</tr>')
        .join('') + '</tbody></table></div>');
      continue;
    }

    if (linha.startsWith('>')) {
      fecharLista();
      saida.push(`<blockquote>${inline(linha.replace(/^>\s?/, ''))}</blockquote>`);
      continue;
    }

    const ordenada = linha.match(/^\s*\d+[.)]\s+(.*)$/);
    const marcada = linha.match(/^\s*[-*+]\s+(.*)$/);
    if (ordenada || marcada) {
      const tipo = ordenada ? 'ol' : 'ul';
      if (emLista !== tipo) { fecharLista(); saida.push(`<${tipo}>`); emLista = tipo; }
      saida.push(`<li>${inline((ordenada || marcada)[1])}</li>`);
      continue;
    }

    fecharLista();
    saida.push(`<p>${inline(linha)}</p>`);
  }

  fecharLista();
  if (emCodigo) saida.push('</code></pre>');
  return saida.join('\n');
}

/** Extrai o trecho de uma evidência E##/O## do briefing, para o painel lateral. */
export function acharEvidencia(briefing, codigo) {
  const linhas = (briefing || '').split('\n');
  const rx = new RegExp(`\\*\\*${codigo}\\*\\*|^\\s*-?\\s*${codigo}\\b|\\b${codigo}\\s*—`);
  for (const linha of linhas) {
    if (rx.test(linha) && (linha.includes('—') || linha.includes('"'))) {
      return linha.replace(/^\s*[-*]\s*/, '').trim();
    }
  }
  return null;
}
