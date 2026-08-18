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
    return;
  }

  conteudo.innerHTML = corpo(dados, { somenteLeitura: false });
  ligar(conteudo, id);
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
    ${escopoPadrao(impl)}
    ${foraDeEscopo(d.escopo)}
    ${alternativaMensal(evol, mensal)}
    ${blocoAlertas(d.alertas, somenteLeitura)}
    ${blocoLacunas(d.lacunas, somenteLeitura)}
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

function pills(origens) {
  return (origens || [])
    .map((o) => `<span class="pill-evidencia" data-ev="${esc(o)}">${esc(o)}</span>`)
    .join(' ');
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
          O agente relê a transcrição e o catálogo, aplica o ajuste e o script recalcula.
          Isso <strong>derruba a aprovação</strong> e refaz as fases 02 e 03 — leva alguns minutos.
          <br><strong>Para mudar o preço, use «Fechar valor».</strong> O agente mexe no
          escopo, nunca no valor — se você pedir um número aqui, ele vai registrar
          que não pôde aplicar e o total continuará saindo do cálculo.
        </span>
      </label>
      <button class="btn primario" id="btn-enviar-ajuste">Reprocessar com este ajuste</button>
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

  raiz.querySelector('#btn-enviar-ajuste').addEventListener('click', async (e) => {
    const texto = raiz.querySelector('#texto-ajuste').value.trim();
    if (texto.length < 5) return mostrarErro('Escreva o que precisa mudar no orçamento.');

    erro.hidden = true;
    e.target.disabled = true;
    estado.textContent = 'reprocessando as fases 02 e 03…';
    try {
      await api.post(`/api/propostas/${id}/ajustar`, { texto });
      location.hash = `#/proposta/${id}`;
    } catch (err) {
      mostrarErro(`<strong>Não deu para pedir o ajuste.</strong> ${esc(err.message)}`);
      e.target.disabled = false;
      estado.textContent = '';
    }
  });
}
