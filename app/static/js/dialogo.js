// Diálogo de confirmação.
//
// O `confirm()` do navegador não serve aqui: exclusão de proposta tem dois
// níveis e o comercial precisa ver, antes de decidir, o que exatamente some em
// cada um. Para o nível irreversível, pedimos o nome do cliente digitado — a
// mesma proteção que `scripts/arquivar.py --limpar` usa no terminal.

import { esc } from './fmt.js';

/**
 * @param {object} opts
 *   titulo, corpo (HTML), acoes: [{rotulo, classe, valor}],
 *   exigirTexto: string a ser digitado para liberar a ação perigosa,
 *   rotuloTexto: label do campo de confirmação
 * @returns {Promise<string|null>} o `valor` da ação escolhida, ou null se cancelou
 */
export function perguntar({ titulo, corpo, acoes, exigirTexto = null, rotuloTexto = '' }) {
  return new Promise((resolver) => {
    const fundo = document.createElement('div');
    fundo.className = 'modal-fundo';
    fundo.innerHTML = `
      <div class="modal" role="dialog" aria-modal="true" aria-label="${esc(titulo)}">
        <h2>${esc(titulo)}</h2>
        <div class="modal-corpo">${corpo}</div>
        ${exigirTexto ? `
          <label class="campo" style="margin-top:14px">
            <span class="campo-rotulo">${esc(rotuloTexto)}</span>
            <input type="text" id="modal-confirmacao" autocomplete="off" spellcheck="false">
          </label>` : ''}
        <div class="modal-acoes">
          <button class="btn" data-valor="">Cancelar</button>
          ${acoes.map((a) => `
            <button class="btn ${a.classe || ''}" data-valor="${esc(a.valor)}"
                    ${a.perigosa ? 'data-perigosa' : ''}
                    ${a.perigosa && exigirTexto ? 'disabled' : ''}>${esc(a.rotulo)}</button>`).join('')}
        </div>
      </div>`;
    document.body.appendChild(fundo);

    const fechar = (valor) => {
      document.removeEventListener('keydown', aoTeclar);
      fundo.remove();
      resolver(valor || null);
    };
    const aoTeclar = (e) => { if (e.key === 'Escape') fechar(null); };
    document.addEventListener('keydown', aoTeclar);
    fundo.addEventListener('click', (e) => { if (e.target === fundo) fechar(null); });

    if (exigirTexto) {
      const campo = fundo.querySelector('#modal-confirmacao');
      const perigosas = [...fundo.querySelectorAll('[data-perigosa]')];
      const revisar = () => {
        const bate = campo.value.trim().toLowerCase() === exigirTexto.trim().toLowerCase();
        perigosas.forEach((b) => { b.disabled = !bate; });
      };
      campo.addEventListener('input', revisar);
      campo.addEventListener('keydown', (e) => {
        if (e.key === 'Enter') { e.preventDefault(); perigosas.find((b) => !b.disabled)?.click(); }
      });
      setTimeout(() => campo.focus(), 40);
    }

    fundo.querySelectorAll('[data-valor]').forEach((b) =>
      b.addEventListener('click', () => fechar(b.dataset.valor)));
  });
}

/** O diálogo específico de excluir proposta, para não repetir o texto em duas telas. */
export function perguntarExclusao(p) {
  const temPdf = Boolean(p.pdf_caminho);
  return perguntar({
    titulo: `Excluir a proposta da ${p.cliente}?`,
    corpo: `
      <p><strong>Remover do app</strong> — ela some do painel e da listagem, mas a
      pasta em <code>propostas/${esc(p.slug)}/</code> continua no disco${temPdf ? ', com o PDF dentro' : ''}.
      Dá para trazer de volta depois.</p>
      <p><strong>Apagar de vez</strong> — some a pasta inteira${temPdf ? ', o PDF' : ''} e todo o
      histórico do banco: alertas, lacunas, ajustes e execuções. <em>Não tem volta.</em></p>
      ${p.origem === 'importado'
        ? `<p class="dim pequeno">Esta proposta veio de <code>arquivo/</code>. Apagar aqui não
           mexe na pasta original — ela pode ser reimportada.</p>`
        : ''}`,
    exigirTexto: p.cliente,
    rotuloTexto: `Para apagar de vez, digite o nome do cliente: ${p.cliente}`,
    acoes: [
      { rotulo: 'Remover do app', valor: 'arquivar' },
      { rotulo: 'Apagar de vez', valor: 'purgar', classe: 'perigo', perigosa: true },
    ],
  });
}
