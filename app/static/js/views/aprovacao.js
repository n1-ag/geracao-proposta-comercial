// A tela do gate. É o único lugar do app onde alguém decide alguma coisa que
// custa dinheiro, então tudo que sustenta o número está aqui: de onde veio cada
// item, o que já está incluso no valor base, os alertas e a memória de cálculo
// inteira.
//
// Nenhum valor é formatado aqui. Todo `R$` vem de um campo `*_fmt` do
// 03-orcamento.json, escrito pelo precificar.py — reformatar arriscaria mostrar
// na tela um número diferente do que sai no PDF.

import { api } from '../api.js';
import { esc, dataHora } from '../fmt.js';
import { render as md, acharEvidencia } from '../md.js';
import { ouvir } from '../sse.js';

let dados = null;

export async function montar({ conteudo, acoes, titulo, params }) {
  const id = Number(params.id);
  dados = await api.get(`/api/propostas/${id}/orcamento`);

  const p = dados.proposta;
  titulo.textContent = `Revisão — ${p.cliente}`;
  acoes.innerHTML = `<a class="btn" href="#/proposta/${id}">Ver a proposta</a>`;

  if (p.status !== 'aguardando_aprovacao') {
    conteudo.innerHTML = `<div class="aviso-faixa info">
      Esta proposta está em <strong>${esc(p.status)}</strong>, não há orçamento esperando
      aprovação. <a href="#/proposta/${id}">Voltar ao detalhe</a>.
    </div>` + corpo(dados, { somenteLeitura: true });
    ligarChat(conteudo, id);
    ligarCatalogo(conteudo, id);
    return;
  }

  conteudo.innerHTML = corpo(dados, { somenteLeitura: false });
  ligar(conteudo, id);
  ligarChat(conteudo, id);
  ligarCatalogo(conteudo, id);
}

// ------------------------------------------------------------------- markup

function corpo(d, { somenteLeitura }) {
  const orc = d.orcamento;
  const impl = orc.implantacao || {};
  const evol = orc.evolucao || {};
  const prop = orc.proposta || {};
  const totais = orc.totais || {};
  const mensal = prop.modelo_principal === 'evolucao';

  return `
    ${cabecalho(d, orc, prop)}
    ${avisoFechamento(impl)}
    ${heroi(impl, evol, totais, mensal)}
    ${tabelaEscopo(impl, d.escopo)}
    ${editorEscopo(impl, d.escopo, somenteLeitura)}
    ${escopoPadrao(impl)}
    ${foraDeEscopo(d.escopo)}
    ${alternativaMensal(evol, mensal)}
    ${blocoAlertas(d.alertas, somenteLeitura)}
    ${blocoLacunas(d.lacunas, somenteLeitura)}
    ${blocoChat()}
    ${historicoAjustes(d.ajustes)}
    ${memoria(d.memoria_md)}
    ${somenteLeitura ? '' : acoesGate(d)}
    <aside id="painel-evidencia" class="painel-lateral" hidden>
      <div class="painel-topo">
        <span id="ev-codigo" class="mono"></span>
        <button class="btn pequeno" id="fechar-evidencia">fechar</button>
      </div>
      <div id="ev-texto"></div>
    </aside>`;
}

function cabecalho(d, orc, prop) {
  const p = d.proposta;
  const impl = orc.implantacao || {};
  const rodada = d.ajustes.length ? ` · rodada ${d.ajustes.length + 1}` : '';
  const enquadramento = [
    prop.modelo_principal === 'evolucao' ? 'Evolução' : 'Implantação',
    prop.natureza, impl.plataforma_nome || p.plataforma_res,
  ].filter(Boolean).join(' · ');

  return `<div class="sec">
    <div class="entre">
      <div>
        <h2 class="mb0">${esc(p.cliente)}</h2>
        <div class="dim pequeno">${esc(enquadramento)}${esc(rodada)}</div>
      </div>
      <div class="dim pequeno" style="text-align:right">
        Validade ${esc(prop.validade_fmt || '—')}<br>
        tabela de preços <code>${esc(orc.precos_versao || '?')}</code>
      </div>
    </div>
  </div>`;
}

function avisoFechamento(impl) {
  const f = impl.fechamento_comercial;
  if (!f) return '';
  return `<div class="aviso-faixa aviso">
    <strong>Valor fechado por decisão comercial.</strong>
    O cálculo do escopo dava ${esc(f.valor_calculado_fmt)} —
    ${esc(f.sentido)} de ${esc(f.diferenca_fmt)}.
    ${f.motivo ? `<div class="pequeno" style="margin-top:5px">${esc(f.motivo)}</div>` : ''}
    <button class="btn pequeno" id="btn-desfazer-fechamento" style="margin-top:8px">
      voltar ao valor calculado</button>
  </div>`;
}

function heroi(impl, evol, totais, mensal) {
  const cond = impl.condicoes || {};

  if (mensal) {
    return `<div class="sec card-preco">
      <div class="preco-rotulo">Fee mensal</div>
      <div class="preco-num">${esc(totais.evolucao_mensal_fmt || '—')}<span class="preco-suf">/mês</span></div>
      <div class="preco-metas">
        <span>${esc(evol.pacote_horas_fmt || '')} · ${esc(evol.faixa_rotulo_fmt || '')}</span>
        <span>hora excedente ${esc(evol.hora_excedente_fmt || '—')}</span>
        <span>fidelidade ${esc(String(evol.fidelidade_meses ?? '—'))} meses</span>
      </div>
    </div>`;
  }

  return `<div class="sec card-preco">
    <div class="preco-rotulo">Investimento de implantação</div>
    <div class="preco-num">${esc(totais.implantacao_total_fmt || '—')}</div>
    <div class="preco-metas">
      <span>${esc(cond.parcelamento || '')}</span>
      <span title="${esc(cond.prazo_origem || '')}">prazo ${esc(cond.prazo_fmt || '—')}</span>
      <span>${esc(cond.garantia || '')}</span>
    </div>
    ${cond.entrada_valor_fmt ? `<div class="preco-parcelas">
      entrada de ${esc(cond.entrada_valor_fmt)} + ${esc(String(cond.parcelas_restante))}×
      de ${esc(cond.parcela_valor_fmt)}
    </div>` : ''}
  </div>`;
}

function brl(v) {
  return Number(v).toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' });
}

function pills(origens) {
  return (origens || [])
    .map((o) => `<span class="pill-evidencia" data-ev="${esc(o)}">${esc(o)}</span>`)
    .join(' ');
}

function editorEscopo(impl, escopo, somenteLeitura) {
  if (somenteLeitura) return '';
  const linhas = (escopo.itens || []).map((i, k) => {
    const cotada = (impl.linhas || []).find((l) => l.catalogo_id === i.catalogo_id) || {};
    const semComplexidade = !i.complexidade;   // escopo padrão ou regra especial
    const opcoes = ['baixa', 'media', 'alta']
      .map((c) => `<option value="${c}" ${i.complexidade === c ? 'selected' : ''}>${c}</option>`)
      .join('');
    return `<tr data-item="${k}" data-id="${esc(i.catalogo_id)}">
      <td>
        <input class="ed-rotulo" type="text" value="${esc(i.rotulo || '')}"
               placeholder="${esc(cotada.nome || i.catalogo_id)}"
               title="o nome que o cliente lê nesta linha do PDF">
        <div class="dim pequeno mono">${esc(i.catalogo_id)}</div>
      </td>
      <td>${semComplexidade
        ? '<span class="dim pequeno">regra própria</span>'
        : `<select class="ed-complexidade">${opcoes}</select>`}</td>
      <td><input class="ed-qtd" type="number" min="1" value="${i.quantidade || 1}"></td>
      <td class="num dim">${esc(cotada.horas_total_fmt || '—')}</td>
      <td class="num">
        <input class="ed-valor" type="text" inputmode="decimal"
               value="${i.valor_fixo != null ? esc(brl(i.valor_fixo)) : ''}"
               placeholder="${esc(cotada.valor_fmt || '—')}"
               title="digite para fixar o valor desta linha; vazio volta ao cálculo por horas">
      </td>
      <td><button class="btn pequeno perigo ed-remover" title="remover item">×</button></td>
    </tr>`;
  }).join('');

  return `<div class="sec card" id="editor-escopo">
    <div class="entre" style="margin-bottom:6px">
      <h2 class="mb0">Ajustar o escopo</h2>
      <span class="dim pequeno">recalcula na hora, sem o agente</span>
    </div>
    <p class="pequeno dim mt0">
      Mude o nome que o cliente lê, a complexidade, a quantidade, <strong>o
      valor</strong>, ou remova um item — e recalcule. Valor digitado é o valor
      que sai: ele não é arredondado para hora fechada, e nem o rateio de um
      total negociado mexe nele. Deixe em branco para a linha voltar a sair do
      cálculo por horas. Dois itens do mesmo tipo precisam de nomes diferentes,
      senão viram duas linhas iguais no PDF com preços diferentes. A contagem
      («— 3 páginas») é acrescentada sozinha. O
      <code>precificar.py</code> refaz a conta — quem decide o valor continua sendo
      o script, o que muda aqui é a escolha dos itens. A edição fica registrada
      no escopo.
    </p>

    <div class="cabecalho-escopo">
      <label class="campo">
        <span class="campo-rotulo">Plataforma</span>
        <select id="ed-plataforma">${PLATAFORMAS.map((p) =>
          `<option value="${p}" ${escopo.plataforma === p ? 'selected' : ''}>${p}</option>`).join('')}</select>
      </label>
      <label class="campo">
        <span class="campo-rotulo">Valor base</span>
        <input type="text" id="ed-valor-base" inputmode="decimal"
               value="${escopo.valor_base_override != null ? esc(brl(escopo.valor_base_override)) : ''}"
               placeholder="${esc(impl.valor_base_fmt || '—')} (da plataforma)">
        <span class="campo-dica">
          Digite <strong>0</strong> em projeto pontual: não há plataforma sendo
          implantada, então não há valor base. Vazio usa o da plataforma.
        </span>
      </label>
    </div>

    <div class="tabela-rolavel">
      <table class="lista" id="tab-editor">
        <thead><tr>
          <th>Como aparece no PDF</th><th>Complexidade</th><th>Qtd</th>
          <th class="num">Horas</th><th class="num">Valor</th><th></th>
        </tr></thead>
        <tbody>${linhas || '<tr><td colspan="6" class="dim">nenhum item cotado</td></tr>'}</tbody>
      </table>
    </div>

    <div class="linha" style="margin-top:14px;flex-wrap:wrap">
      <select id="add-item" style="min-width:280px"><option value="">acrescentar item do catálogo…</option></select>
      <button class="btn pequeno" id="btn-add">Acrescentar</button>
      <button class="btn primario pequeno" id="btn-recalcular">Recalcular</button>
      <span class="dim pequeno" id="editor-estado"></span>
    </div>
  </div>`;
}

function tabelaEscopo(impl, escopo) {
  const linhas = impl.linhas || [];
  const fora = impl.linhas_fora_catalogo || [];
  if (!linhas.length && !fora.length) {
    return `<div class="sec card"><h2>Escopo cotado</h2>
      <p class="dim">Nada além do escopo padrão foi cotado nesta proposta.</p></div>`;
  }

  // O JSON do orçamento não carrega a origem de cada linha — ela vive no
  // 02-escopo.json. Casamos pelo id do catálogo para a rastreabilidade chegar
  // até aqui.
  const origemPorId = Object.fromEntries((escopo.itens || []).map((i) => [i.catalogo_id, i.origem]));
  const origemPorNome = Object.fromEntries(
    (escopo.itens_fora_catalogo || []).map((i) => [i.nome, i.origem])
  );

  const corpoCatalogo = linhas.map((l) => `
    <tr>
      <td>${esc(l.nome)}<div class="pequeno">${pills(l.origem || origemPorId[l.catalogo_id])}</div></td>
      <td class="dim">${esc(l.complexidade || '—')}</td>
      <td class="num">${esc(String(l.quantidade ?? 1))}</td>
      <td class="num">${esc(l.horas_total_fmt || '—')}</td>
      <td class="num">${esc(l.valor_fmt || '—')}</td>
    </tr>`).join('');

  const corpoFora = fora.map((l) => `
    <tr>
      <td>
        ${esc(l.nome)} <span class="badge aguardando">fora do catálogo</span>
        <button class="btn pequeno btn-catalogar" data-nome="${esc(l.nome)}"
                title="incorporar este item ao catálogo de módulos">Catalogar</button>
        <div class="pequeno">${pills(l.origem || origemPorNome[l.nome])}</div>
        ${l.justificativa ? `<details class="pequeno dim" style="margin-top:4px">
          <summary>por que não usar item existente</summary>${esc(l.justificativa)}</details>` : ''}
      </td>
      <td class="dim">—</td>
      <td class="num">1</td>
      <td class="num">${esc(l.horas_total_fmt || '—')}</td>
      <td class="num">${esc(l.valor_fmt || '—')}</td>
    </tr>`).join('');

  const s = impl.subtotais || {};
  return `<div class="sec card">
    <h2>Escopo cotado</h2>
    <p class="pequeno dim mt0">
      Clique num marcador <span class="pill-evidencia">E00</span> para ver o trecho da
      reunião que sustenta o item. <span class="mono">O##</span> é observação do comercial,
      não fala do cliente.
    </p>
    <div class="tabela-rolavel">
      <table class="lista">
        <thead><tr><th>Item</th><th>Complexidade</th><th class="num">Qtd</th>
          <th class="num">Horas</th><th class="num">Valor</th></tr></thead>
        <tbody>${corpoCatalogo}${corpoFora}</tbody>
        <tfoot>
          <tr><td colspan="4">Valor base da plataforma</td><td class="num">${esc(s.base_fmt || '—')}</td></tr>
          <tr><td colspan="4">Adicionais (${esc(s.horas_adicionais_fmt || '0h')})</td>
              <td class="num">${esc(s.adicionais_fmt || '—')}</td></tr>
          ${Number(s.abatimento_design) ? `<tr><td colspan="4">Abatimento de design (layout do cliente)</td>
              <td class="num">− ${esc(s.abatimento_design_fmt)}</td></tr>` : ''}
          <tr class="total"><td colspan="4">Total</td><td class="num">${esc(impl.total_fmt || '—')}</td></tr>
        </tfoot>
      </table>
    </div>
  </div>`;
}

function escopoPadrao(impl) {
  const itens = impl.escopo_padrao_incluso || [];
  if (!itens.length) return '';
  return `<div class="sec card">
    <details>
      <summary><strong>Já incluso no valor base</strong>
        <span class="dim">— ${itens.length} itens, sem custo adicional</span></summary>
      <p class="pequeno dim">
        Se o cliente pedir desconto por algum destes, ele já está pago.
      </p>
      <div class="chips">${itens.map((i) => `<span class="chip">${esc(i)}</span>`).join('')}</div>
    </details>
  </div>`;
}

function foraDeEscopo(escopo) {
  const itens = escopo.fora_de_escopo || [];
  if (!itens.length) return '';
  return `<div class="sec card">
    <h2>Fora de escopo</h2>
    <ul class="cruz">${itens.map((i) => `<li>${esc(i)}</li>`).join('')}</ul>
  </div>`;
}

function alternativaMensal(evol, jaEhMensal) {
  if (jaEhMensal || !evol.aplicavel) return '';
  const faixas = (evol.tabela_faixas || []).map((f) => `
    <tr class="${f.id === evol.faixa_id ? 'destaque' : ''}">
      <td>${esc(f.rotulo_fmt)}</td><td class="num">${esc(f.valor_hora_fmt)}</td>
    </tr>`).join('');

  return `<div class="sec card">
    <details>
      <summary><strong>Alternativa em fee mensal</strong>
        <span class="dim">— ${esc(evol.valor_mensal_fmt || '')}/mês</span></summary>
      <p class="pequeno dim">
        Mesma entrega, cobrada como pacote de horas. Serve quando o cliente trava no
        valor único.
      </p>
      <div class="grid k2">
        <div>
          <div class="linha-dado"><span>Pacote</span><strong>${esc(evol.pacote_horas_fmt || '—')}</strong></div>
          <div class="linha-dado"><span>Valor da hora</span><strong>${esc(evol.valor_hora_fmt || '—')}</strong></div>
          <div class="linha-dado"><span>Mensal</span><strong>${esc(evol.valor_mensal_fmt || '—')}</strong></div>
          <div class="linha-dado"><span>Hora excedente</span><strong>${esc(evol.hora_excedente_fmt || '—')}</strong></div>
          <div class="linha-dado"><span>Acúmulo de saldo</span><strong>${esc(String(evol.acumulo_saldo_pct ?? '—'))}%</strong></div>
          <div class="linha-dado"><span>Fidelidade</span><strong>${esc(String(evol.fidelidade_meses ?? '—'))} meses</strong></div>
        </div>
        <div><table class="lista compacta">
          <thead><tr><th>Faixa</th><th class="num">Hora</th></tr></thead>
          <tbody>${faixas}</tbody></table></div>
      </div>
    </details>
  </div>`;
}

const NOME_SEVERIDADE = { alta: 'Alta', media: 'Média', baixa: 'Baixa' };

function blocoAlertas(alertas, somenteLeitura) {
  if (!alertas.length) return '';
  const altos = alertas.filter((a) => a.severidade === 'alta');

  const item = (a) => `
    <li class="alerta ${esc(a.severidade)}">
      ${a.severidade === 'alta' && !somenteLeitura
        ? `<label class="ciente"><input type="checkbox" class="chk-alto" data-id="${a.id}">
             <span>estou ciente</span></label>`
        : ''}
      <div>
        <span class="mono alerta-codigo">${esc(a.codigo || '')}</span>
        <span class="dim pequeno">${esc(NOME_SEVERIDADE[a.severidade] || a.severidade)}</span>
        <div>${esc(a.mensagem || '')}</div>
      </div>
    </li>`;

  return `<div class="sec card">
    <h2>Alertas</h2>
    ${altos.length && !somenteLeitura ? `<p class="pequeno dim mt0">
      Os ${altos.length} alerta(s) de severidade alta precisam ser reconhecidos antes de aprovar.
    </p>` : ''}
    <ul class="alertas">${alertas.map(item).join('')}</ul>
  </div>`;
}

function blocoLacunas(lacunas, somenteLeitura) {
  if (!lacunas.length) return '';
  return `<div class="sec card">
    <details ${lacunas.length <= 6 ? 'open' : ''}>
      <summary><strong>Lacunas</strong> <span class="dim">— ${lacunas.length} pontos não confirmados</span></summary>
      <p class="pequeno dim">
        Marque as que você vai levar ao cliente: elas entram como observação no registro
        da aprovação.
      </p>
      <ul class="lacunas">${lacunas.map((l) => `
        <li>${somenteLeitura ? '' :
          `<label><input type="checkbox" class="chk-lacuna" value="${l.id}"></label>`}
          <span>${esc(l.texto)}</span></li>`).join('')}</ul>
    </details>
  </div>`;
}

function historicoAjustes(ajustes) {
  if (!ajustes.length) return '';
  return `<div class="sec card">
    <details>
      <summary><strong>Ajustes pedidos</strong> <span class="dim">— ${ajustes.length}</span></summary>
      <ol class="ajustes">${ajustes.map((a) => `
        <li>
          <div class="pequeno dim">${esc(dataHora(a.criado_em))}
            ${a.sobre_total_fmt ? `· sobre ${esc(a.sobre_total_fmt)}` : ''}
            · ${a.aplicado_em ? 'aplicado' : '<strong>pendente</strong>'}</div>
          <div>${esc(a.texto)}</div>
        </li>`).join('')}</ol>
    </details>
  </div>`;
}

function memoria(markdown) {
  if (!markdown) return '';
  return `<div class="sec card">
    <details>
      <summary><strong>Memória de cálculo</strong>
        <span class="dim">— como o script chegou nestes números</span></summary>
      <div class="markdown">${md(markdown)}</div>
    </details>
  </div>`;
}

function acoesGate(d) {
  return `<div class="sec card gate">
    <h2>Decisão</h2>
    <div class="aviso-faixa erro" id="gate-erro" hidden></div>

    <label class="campo largo">
      <span class="campo-rotulo">Observações para o registro</span>
      <textarea id="obs-aprovacao" rows="2"
        placeholder="Opcional. Fica gravado no manifest junto com a aprovação."></textarea>
    </label>

    <div class="linha" style="margin-top:16px">
      <button class="btn primario" id="btn-aprovar">Aprovar e gerar PDF</button>
      <button class="btn" id="btn-ajuste">Pedir ajuste</button>
      <button class="btn" id="btn-fechar">Fechar valor</button>
      <a class="btn" href="#/nova/${d.proposta.id}">Editar cadastro</a>
      <span class="dim pequeno" id="gate-estado"></span>
    </div>

    <div id="caixa-fechar" hidden style="margin-top:18px">
      <div class="campos">
        <label class="campo">
          <span class="campo-rotulo">Valor final do projeto</span>
          <input type="text" id="valor-fechado" inputmode="decimal"
                 placeholder="36000 ou 36.000,00">
        </label>
        <label class="campo">
          <span class="campo-rotulo">Por quê</span>
          <input type="text" id="motivo-fechado"
                 placeholder="ex.: negociado com o cliente; escopo reduzido no contrato">
        </label>
      </div>
      <span class="campo-dica" style="display:block;margin-top:8px">
        Substitui o total calculado pelo escopo. O valor do cálculo continua registrado
        ao lado, com um alerta de severidade alta — nada some, e a diferença fica
        visível para quem aprovar. Entrada e parcelas são recalculadas.
        <strong>Não usa o agente:</strong> responde em segundos.
      </span>
      <button class="btn primario" id="btn-aplicar-fechamento" style="margin-top:12px">
        Aplicar valor</button>
    </div>

    <div id="caixa-ajuste" hidden style="margin-top:18px">
      <label class="campo largo">
        <span class="campo-rotulo">O que precisa mudar</span>
        <textarea id="texto-ajuste" rows="4"
          placeholder="Escreva em português corrido, do jeito que você diria ao time. Ex.: &quot;o megamenu já está incluso no comum, não cobra separado&quot; ou &quot;tira uma landing page, ficaram 3&quot;."></textarea>
        <span class="campo-dica">
          Escreva tudo de uma vez: valor final, preço ou horas de um módulo, item
          que passa a ser incluso, prazo, o que tirar ou acrescentar. Eu leio,
          mostro o que entendi de cada frase, e só aplico depois que você
          confirmar. O que o cálculo resolve sozinho é instantâneo — só o que
          sobra vai para o agente.
        </span>
      </label>
      <button class="btn primario" id="btn-enviar-ajuste">Ler meu pedido</button>
      <div id="interpretacao" hidden></div>
    </div>
  </div>`;
}

// ---------------------------------------------------------------- interação

function ligar(raiz, id) {
  const erro = raiz.querySelector('#gate-erro');
  const estado = raiz.querySelector('#gate-estado');
  const aprovar = raiz.querySelector('#btn-aprovar');
  const altos = [...raiz.querySelectorAll('.chk-alto')];

  const mostrarErro = (msg) => {
    erro.innerHTML = msg;
    erro.hidden = false;
    erro.scrollIntoView({ behavior: 'smooth', block: 'center' });
  };

  // O botão de aprovar só destrava quando todos os alertas altos forem
  // reconhecidos, um a um.
  const revisarTravas = () => {
    const faltam = altos.filter((c) => !c.checked).length;
    aprovar.disabled = faltam > 0;
    aprovar.title = faltam ? `reconheça os ${faltam} alerta(s) alto(s) acima` : '';
  };
  altos.forEach((c) => c.addEventListener('change', revisarTravas));
  revisarTravas();

  // Painel lateral com o trecho da reunião por trás de cada evidência.
  const painel = raiz.querySelector('#painel-evidencia');
  raiz.addEventListener('click', (e) => {
    const pill = e.target.closest('.pill-evidencia');
    if (pill && pill.dataset.ev) {
      const codigo = pill.dataset.ev;
      const trecho = acharEvidencia(dados.briefing_md, codigo);
      raiz.querySelector('#ev-codigo').textContent = codigo;
      raiz.querySelector('#ev-texto').innerHTML = trecho
        ? md(trecho)
        : `<p class="dim">Não encontrei ${esc(codigo)} no briefing desta proposta.</p>`;
      painel.hidden = false;
    }
    if (e.target.id === 'fechar-evidencia') painel.hidden = true;
  });

  aprovar.addEventListener('click', async () => {
    erro.hidden = true;
    aprovar.disabled = true;
    estado.textContent = 'aprovando e enfileirando a geração do PDF…';
    try {
      await api.post(`/api/propostas/${id}/aprovar`, {
        hash: dados.hash,
        observacoes: raiz.querySelector('#obs-aprovacao').value,
        lacunas_marcadas: [...raiz.querySelectorAll('.chk-lacuna:checked')].map((c) => Number(c.value)),
        ciente_alertas_altos: altos.length ? altos.every((c) => c.checked) : true,
      });
      location.hash = `#/proposta/${id}`;
    } catch (err) {
      const extra = err.codigo === 'orcamento_mudou'
        ? ' <a href="javascript:location.reload()">Recarregar a página</a>.' : '';
      mostrarErro(`<strong>Não deu para aprovar.</strong> ${esc(err.message)}${extra}`);
      revisarTravas();
      estado.textContent = '';
    }
  });

  // -- editor de escopo ------------------------------------------------------

  const editor = raiz.querySelector('#editor-escopo');
  if (editor) {
    const estadoEd = editor.querySelector('#editor-estado');
    const seletor = editor.querySelector('#add-item');

    // O catálogo inteiro, para saber o que dá para acrescentar.
    api.get('/api/catalogo/itens').then(({ itens }) => {
      const porCategoria = {};
      for (const i of itens) {
        if (i.no_escopo_padrao) continue;   // já está no valor base
        (porCategoria[i.categoria || 'outros'] ||= []).push(i);
      }
      for (const [cat, lista] of Object.entries(porCategoria)) {
        const g = document.createElement('optgroup');
        g.label = cat;
        for (const i of lista) {
          const o = document.createElement('option');
          o.value = i.id;
          o.textContent = i.nome;
          o.dataset.especial = i.regra_especial ? '1' : '';
          g.appendChild(o);
        }
        seletor.appendChild(g);
      }
    }).catch(() => {});

    const linhasAtuais = () => [...editor.querySelectorAll('#tab-editor tbody tr[data-id]')]
      .map((tr) => ({
        catalogo_id: tr.dataset.id,
        rotulo: tr.querySelector('.ed-rotulo')?.value.trim() || '',
        valor_fixo: tr.querySelector('.ed-valor')?.value.trim() || null,
        complexidade: tr.querySelector('.ed-complexidade')?.value || null,
        quantidade: Number(tr.querySelector('.ed-qtd')?.value || 1),
      }));

    editor.addEventListener('click', (e) => {
      if (e.target.classList.contains('ed-remover')) {
        e.target.closest('tr').remove();
        estadoEd.textContent = 'alterado — clique em Recalcular';
      }
    });
    editor.addEventListener('change', () => {
      estadoEd.textContent = 'alterado — clique em Recalcular';
    });
    // `change` em campo de texto só dispara ao sair dele; sem isto, quem digita
    // o rótulo e clica direto em Recalcular não vê que havia algo pendente.
    editor.addEventListener('input', (e) => {
      if (e.target.classList.contains('ed-rotulo')
          || e.target.classList.contains('ed-valor')
          || e.target.id === 'ed-valor-base') {
        estadoEd.textContent = 'alterado — clique em Recalcular';
      }
    });

    editor.querySelector('#btn-add').addEventListener('click', () => {
      const op = seletor.selectedOptions[0];
      if (!op || !op.value) return;
      if (editor.querySelector(`tr[data-id="${op.value}"]`)) {
        estadoEd.textContent = 'esse item já está no escopo';
        return;
      }
      const corpo = editor.querySelector('#tab-editor tbody');
      const vazia = corpo.querySelector('tr:not([data-id])');
      if (vazia) vazia.remove();
      const tr = document.createElement('tr');
      tr.dataset.id = op.value;
      tr.innerHTML = `
        <td><div>${esc(op.textContent)}</div>
            <div class="dim pequeno mono">${esc(op.value)}</div></td>
        <td>${op.dataset.especial
          ? '<span class="dim pequeno">regra própria</span>'
          : `<select class="ed-complexidade">
               <option value="baixa">baixa</option>
               <option value="media" selected>media</option>
               <option value="alta">alta</option></select>`}</td>
        <td><input class="ed-qtd" type="number" min="1" value="1"></td>
        <td class="num dim">—</td><td class="num dim">a calcular</td>
        <td><button class="btn pequeno perigo ed-remover">×</button></td>`;
      corpo.appendChild(tr);
      seletor.value = '';
      estadoEd.textContent = 'alterado — clique em Recalcular';
    });

    editor.querySelector('#btn-recalcular').addEventListener('click', async (e) => {
      e.target.disabled = true;
      estadoEd.textContent = 'recalculando…';
      try {
        const r = await api.post(`/api/propostas/${id}/escopo`, {
          itens: linhasAtuais(),
          plataforma: editor.querySelector('#ed-plataforma')?.value || '',
          valor_base_override: editor.querySelector('#ed-valor-base')?.value.trim() || null,
        });
        estadoEd.textContent = `total: ${r.total_fmt}`;
        location.reload();
      } catch (err) {
        estadoEd.textContent = '';
        mostrarErro(`<strong>Não deu para recalcular.</strong> ${esc(err.message)}`);
        e.target.disabled = false;
      }
    });
  }

  // -- fechamento comercial --------------------------------------------------

  const aplicarFechamento = async (valor, motivo, botao) => {
    erro.hidden = true;
    if (botao) botao.disabled = true;
    estado.textContent = 'reprecificando…';
    try {
      const r = await api.post(`/api/propostas/${id}/fechar-valor`, { valor, motivo });
      estado.textContent = `total agora: ${r.total_fmt}`;
      location.reload();
    } catch (err) {
      mostrarErro(`<strong>Não deu para fechar o valor.</strong> ${esc(err.message)}`);
      if (botao) botao.disabled = false;
      estado.textContent = '';
    }
  };

  const caixaFechar = raiz.querySelector('#caixa-fechar');
  raiz.querySelector('#btn-fechar')?.addEventListener('click', () => {
    caixaFechar.hidden = !caixaFechar.hidden;
    if (!caixaFechar.hidden) raiz.querySelector('#valor-fechado').focus();
  });

  raiz.querySelector('#btn-aplicar-fechamento')?.addEventListener('click', (e) => {
    const valor = raiz.querySelector('#valor-fechado').value.trim();
    if (!valor) return mostrarErro('Informe o valor final do projeto.');
    aplicarFechamento(valor, raiz.querySelector('#motivo-fechado').value.trim(), e.target);
  });

  raiz.querySelector('#btn-desfazer-fechamento')?.addEventListener('click', (e) => {
    if (!confirm('Voltar ao valor calculado pelo escopo?')) return;
    aplicarFechamento(null, '', e.target);
  });

  const caixa = raiz.querySelector('#caixa-ajuste');
  raiz.querySelector('#btn-ajuste').addEventListener('click', () => {
    caixa.hidden = !caixa.hidden;
    if (!caixa.hidden) raiz.querySelector('#texto-ajuste').focus();
  });

  // Duas etapas: ler e mostrar, depois aplicar o que foi confirmado. A primeira
  // não muda nada — é o que permite discordar antes de o orçamento se mexer.
  const painelOps = raiz.querySelector('#interpretacao');

  const descrever = (o) => {
    const v = (x) => (x ?? 0).toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' });
    switch (o.tipo) {
      case 'valor_total':  return `Valor final da proposta → <strong>${v(o.valor)}</strong>`;
      case 'valor_item':   return `${esc(o.nome)} → <strong>${o.horas}h</strong> · ${v(o.valor_efetivo)}`
        + (Math.abs(o.valor_efetivo - o.valor) > 0.5
            ? `<span class="dim"> — você pediu ${v(o.valor)}; a ${v(o.valor_efetivo / o.horas / (o.quantidade||1))}/h o mais próximo é ${v(o.valor_efetivo)}</span>` : '');
      case 'horas_item':   return `${esc(o.nome)} → <strong>${o.horas}h</strong> · ${v(o.valor_efetivo)}`;
      case 'item_incluso': return `${esc(o.nome)} → <strong>incluso no valor base</strong>, sem custo`
        + (o.ja_cotado ? '' : '<span class="dim"> — será acrescentado ao escopo</span>');
      case 'remover_item': return `${esc(o.nome)} → <strong>removido</strong> do escopo`;
      case 'acrescentar_item': return `Acrescentar <strong>${esc(o.rotulo || o.nome)}</strong>`
        + ` (${o.complexidade || 'regra própria'}, ${o.quantidade}×)`;
      case 'rotulo_item':  return `${esc(o.nome)} → aparece como «<strong>${esc(o.rotulo)}</strong>»`;
      case 'valor_base':   return `Valor base → <strong>${v(o.valor)}</strong>`;
      case 'prazo':        return `Prazo → <strong>${o.min} a ${o.max} semanas</strong>`;
      case 'texto_livre':  return `<strong>Vai para o agente:</strong> ${esc(o.instrucao || '')}`;
      default:             return esc(o.tipo);
    }
  };

  const pintarInterpretacao = (d) => {
    const linhas = d.operacoes.map((o, k) => `
      <div class="op ${o.ok ? '' : 'recusada'}">
        <label>
          <input type="checkbox" class="op-chk" data-k="${k}" ${o.ok ? 'checked' : 'disabled'}>
          <span class="op-trecho">${esc(o.trecho || '—')}</span>
        </label>
        <div class="op-seta">→</div>
        <div class="op-acao">${o.ok ? descrever(o) : `<span class="op-nao">${esc(o.motivo)}</span>`}</div>
      </div>`).join('');

    const resumo = [
      d.instantaneas ? `${d.instantaneas} instantânea(s)` : '',
      d.pelo_agente ? `${d.pelo_agente} pelo agente (alguns minutos)` : '',
      d.recusadas ? `${d.recusadas} não entendida(s)` : '',
    ].filter(Boolean).join(' · ');

    painelOps.innerHTML = `
      <h3 class="op-titulo">Entendi isto</h3>
      <div class="ops">${linhas}</div>
      <div class="linha" style="margin-top:14px;align-items:center">
        <button class="btn primario" id="btn-aplicar-ajuste">Aplicar</button>
        <button class="btn" id="btn-refazer-leitura">Reescrever o pedido</button>
        <span class="dim pequeno">${esc(resumo)}</span>
      </div>`;
    painelOps.hidden = false;
    painelOps.dataset.ops = JSON.stringify(d.operacoes);
  };

  raiz.querySelector('#btn-enviar-ajuste').addEventListener('click', async (e) => {
    const texto = raiz.querySelector('#texto-ajuste').value.trim();
    if (texto.length < 5) return mostrarErro('Escreva o que precisa mudar no orçamento.');

    erro.hidden = true;
    e.target.disabled = true;
    estado.textContent = 'lendo o seu pedido…';
    try {
      pintarInterpretacao(await api.post(`/api/propostas/${id}/ajustar/interpretar`, { texto }));
      estado.textContent = '';
    } catch (err) {
      mostrarErro(`<strong>Não consegui ler o pedido.</strong> ${esc(err.message)}`);
    } finally {
      e.target.disabled = false;
    }
  });

  painelOps?.addEventListener('click', async (ev) => {
    if (ev.target.id === 'btn-refazer-leitura') {
      painelOps.hidden = true;
      raiz.querySelector('#texto-ajuste').focus();
      return;
    }
    if (ev.target.id !== 'btn-aplicar-ajuste') return;

    const todas = JSON.parse(painelOps.dataset.ops || '[]');
    const escolhidas = [...painelOps.querySelectorAll('.op-chk:checked')]
      .map((c) => todas[Number(c.dataset.k)]);
    if (!escolhidas.length) return mostrarErro('Marque ao menos uma operação.');

    ev.target.disabled = true;
    estado.textContent = 'aplicando…';
    try {
      const r = await api.post(`/api/propostas/${id}/ajustar/aplicar`, {
        texto: raiz.querySelector('#texto-ajuste').value.trim(),
        operacoes: escolhidas,
      });
      // Só recarrega aqui se nada foi para a fila; se foi, o detalhe mostra o
      // acompanhamento da execução.
      location.hash = r.execucao_id ? `#/proposta/${id}` : location.hash;
      location.reload();
    } catch (err) {
      mostrarErro(`<strong>Não deu para aplicar.</strong> ${esc(err.message)}`);
      ev.target.disabled = false;
      estado.textContent = '';
    }
  });
}

// ---------------------------------------------------------------------- chat

// Perguntas que quase sempre são a primeira. Deixá-las a um clique poupa a
// página em branco — ninguém sabe o que perguntar para um agente até ver um
// exemplo do que dá para perguntar.
const SUGESTOES = [
  'Por que este item entrou no escopo?',
  'De onde saiu o prazo?',
  'O que ficou de fora e por quê?',
  'Que riscos você vê neste escopo?',
];

function blocoChat() {
  return `
  <section class="bloco chat" id="bloco-chat">
    <h2>Perguntar ao agente</h2>
    <p class="dim sub">
      Ele lê os artefatos desta proposta e responde citando a evidência.
      Só lê: nada do que for dito aqui altera o escopo ou o valor.
    </p>
    <div class="chat-linha" id="chat-linha"></div>
    <div class="chat-sugestoes" id="chat-sugestoes">
      ${SUGESTOES.map((t) => `<button class="btn pequeno sugestao">${esc(t)}</button>`).join('')}
    </div>
    <form class="chat-entrada" id="chat-form">
      <textarea id="chat-pergunta" rows="2" placeholder="Por que a busca com autocomplete foi cotada à parte?"></textarea>
      <button class="btn primario" id="chat-enviar" type="submit">Perguntar</button>
    </form>
    <p class="chat-erro" id="chat-erro" hidden></p>
  </section>`;
}

function balao(m) {
  const eu = m.papel === 'humano';
  const corpoTexto = eu ? `<p>${esc(m.texto)}</p>` : md(m.texto || '');
  return `<div class="balao ${eu ? 'meu' : 'agente'}">
    <span class="quem">${eu ? 'você' : 'agente'}</span>
    <div class="balao-corpo">${corpoTexto}</div>
  </div>`;
}

function ligarChat(raiz, id) {
  const linha = raiz.querySelector('#chat-linha');
  const form = raiz.querySelector('#chat-form');
  const campo = raiz.querySelector('#chat-pergunta');
  const enviar = raiz.querySelector('#chat-enviar');
  const erro = raiz.querySelector('#chat-erro');
  if (!linha) return;

  let respondendo = false;
  // O balão em construção fica fora do histórico: ele é substituído a cada
  // delta, e reconstruir a conversa inteira 4×/s faria a página piscar.
  let rascunho = null;

  const fim = () => linha.scrollTop = linha.scrollHeight;

  const trocarEstado = (v) => {
    respondendo = v;
    enviar.disabled = v;
    enviar.textContent = v ? 'pensando…' : 'Perguntar';
  };

  const pintar = (mensagens) => {
    linha.innerHTML = mensagens.length
      ? mensagens.map(balao).join('')
      : '<p class="dim vazio">Nenhuma pergunta ainda.</p>';
    rascunho = null;
    fim();
  };

  api.get(`/api/propostas/${id}/chat`)
    .then((d) => { pintar(d.mensagens); if (d.respondendo) trocarEstado(true); })
    .catch(() => pintar([]));

  const perguntar = async (texto) => {
    if (!texto.trim() || respondendo) return;
    erro.hidden = true;
    trocarEstado(true);
    campo.value = '';
    try {
      await api.post(`/api/propostas/${id}/chat`, { pergunta: texto });
    } catch (e) {
      trocarEstado(false);
      erro.textContent = e.mensagem || 'não consegui enviar a pergunta';
      erro.hidden = false;
    }
  };

  form.addEventListener('submit', (e) => { e.preventDefault(); perguntar(campo.value); });

  // Enter envia, Shift+Enter quebra linha — como em todo campo de conversa.
  campo.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); perguntar(campo.value); }
  });

  raiz.querySelectorAll('.sugestao').forEach((b) =>
    b.addEventListener('click', () => { campo.value = b.textContent; campo.focus(); }));

  ouvir('chat', (d) => {
    if (Number(d.proposta_id) !== Number(id)) return;
    const vazio = linha.querySelector('.vazio');
    if (vazio) vazio.remove();

    if (d.papel === 'humano') {
      linha.insertAdjacentHTML('beforeend', balao(d));
      rascunho = null;
      fim();
      return;
    }

    if (!rascunho) {
      linha.insertAdjacentHTML('beforeend', balao({ papel: 'agente', texto: '' }));
      rascunho = linha.lastElementChild;
    }
    const alvo = rascunho.querySelector('.balao-corpo');
    if (d.estado === 'pensando') {
      alvo.innerHTML = '<p class="dim pulsando">lendo os artefatos…</p>';
    } else if (d.estado === 'lendo' && !d.texto) {
      alvo.innerHTML = `<p class="dim pulsando">consultando ${esc(d.consultando || 'os artefatos')}…</p>`;
    } else {
      alvo.innerHTML = md(d.texto || '');
    }
    if (d.estado === 'pronto') { rascunho = null; trocarEstado(false); }
    fim();
  });
}

// ------------------------------------------------------- catalogar item ----

// Item cotado fora do catálogo apareceu em todas as propostas geradas até hoje,
// e nenhum foi incorporado: o caminho era um comando de terminal. Aqui o Sonnet
// propõe a ficha, uma pessoa revisa, e o script grava — o catálogo é a fonte da
// verdade de preço, e ninguém escreve nele sem passar por gente.
const PLATAFORMAS = ['shopify', 'vtex', 'wake', 'nuvemshop', 'wordpress', 'template-html'];

const CATEGORIAS = ['conteudo', 'componente', 'integracao', 'migracao', 'seo', 'apoio'];

function faixa(rotulo, chave, v) {
  const [a, b] = v || ['', ''];
  return `<label class="cat-faixa"><span>${rotulo}</span>
    <input type="number" min="1" data-f="${chave}-min" value="${a}">
    <span class="dim">a</span>
    <input type="number" min="1" data-f="${chave}-max" value="${b}"></label>`;
}

function formularioCatalogo(f) {
  const opc = CATEGORIAS.map((c) =>
    `<option value="${c}" ${f.categoria === c ? 'selected' : ''}>${c}</option>`).join('');
  return `
    <div class="cat-form">
      <p class="dim pequeno mt0">
        Estimado em <strong>${esc(String(f._estimativa ?? '—'))}h</strong> nesta proposta.
        Revise antes de gravar: o catálogo vale para todas as propostas daqui em diante.
      </p>
      <label class="campo"><span class="campo-rotulo">Identificador</span>
        <input type="text" data-f="id" value="${esc(f.id || '')}" class="mono"></label>
      <label class="campo"><span class="campo-rotulo">Nome</span>
        <input type="text" data-f="nome" value="${esc(f.nome || '')}"></label>
      <div class="campos">
        <label class="campo"><span class="campo-rotulo">Categoria</span>
          <select data-f="categoria">${opc}</select></label>
        <label class="campo"><span class="campo-rotulo">Unidade</span>
          <input type="text" data-f="unidade" value="${esc(f.unidade || '')}"></label>
      </div>
      <div class="cat-faixas">
        ${faixa('baixa', 'baixa', f.horas_baixa)}
        ${faixa('média', 'media', f.horas_media)}
        ${faixa('alta', 'alta', f.horas_alta)}
      </div>
      <label class="campo largo"><span class="campo-rotulo">Critério de complexidade</span>
        <textarea data-f="criterio_complexidade" rows="4">${esc(f.criterio_complexidade || '')}</textarea>
        <span class="campo-dica">É o texto que o agente lê para classificar as próximas cotações.</span></label>
      <label class="campo largo"><span class="campo-rotulo">Descrição para a proposta</span>
        <input type="text" data-f="descricao_proposta" value="${esc(f.descricao_proposta || '')}">
        <span class="campo-dica">A frase que vai ao cliente no PDF.</span></label>
      <div class="linha" style="margin-top:12px">
        <button class="btn primario" id="cat-gravar">Gravar no catálogo</button>
        <button class="btn" id="cat-cancelar">Cancelar</button>
        <span class="dim pequeno" id="cat-estado"></span>
      </div>
    </div>`;
}

function ligarCatalogo(raiz, id) {
  raiz.addEventListener('click', async (e) => {
    const botao = e.target.closest('.btn-catalogar');
    if (!botao) return;

    const nome = botao.dataset.nome;
    const tr = botao.closest('tr');
    if (tr.nextElementSibling?.classList.contains('cat-linha')) {
      tr.nextElementSibling.remove();
      return;
    }

    botao.disabled = true;
    botao.textContent = 'lendo…';
    let ficha;
    try {
      ficha = (await api.post(`/api/propostas/${id}/catalogar/propor`, { nome })).ficha;
    } catch (err) {
      botao.disabled = false;
      botao.textContent = 'Catalogar';
      return alert(err.message || 'não consegui propor a ficha');
    }
    botao.textContent = 'Catalogar';
    botao.disabled = false;

    tr.insertAdjacentHTML('afterend',
      `<tr class="cat-linha"><td colspan="5">${formularioCatalogo(ficha)}</td></tr>`);
    const caixa = tr.nextElementSibling;
    const estado = caixa.querySelector('#cat-estado');

    caixa.querySelector('#cat-cancelar').addEventListener('click', () => caixa.remove());
    caixa.querySelector('#cat-gravar').addEventListener('click', async (ev) => {
      const v = (k) => caixa.querySelector(`[data-f="${k}"]`)?.value.trim() || '';
      const par = (k) => [Number(v(`${k}-min`)), Number(v(`${k}-max`))];
      const nova = {
        id: v('id'), nome: v('nome'), categoria: v('categoria'), unidade: v('unidade'),
        horas_baixa: par('baixa'), horas_media: par('media'), horas_alta: par('alta'),
        criterio_complexidade: v('criterio_complexidade'),
        descricao_proposta: v('descricao_proposta'),
      };
      ev.target.disabled = true;
      estado.textContent = 'gravando…';
      try {
        await api.post(`/api/propostas/${id}/catalogar`, { nome, ficha: nova });
        location.reload();
      } catch (err) {
        estado.textContent = '';
        ev.target.disabled = false;
        alert(err.message || 'não deu para gravar');
      }
    });
  });
}
