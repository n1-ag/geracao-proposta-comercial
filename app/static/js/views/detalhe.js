// Detalhe da proposta: estado, progresso ao vivo, artefatos, previews e PDF.
//
// É a tela onde o comercial espera. Enquanto uma execução roda, a linha de
// progresso mostra o que o agente está fazendo agora — sem isso a espera de
// dez minutos parece travamento.

import { api } from '../api.js';
import { badge, brl, dataHora, duracao, esc, relativo, rotulo } from '../fmt.js';
import { ouvir } from '../sse.js';
import { perguntarExclusao } from '../dialogo.js';
import { NOME_FASE, anunciarEnfileiramento, observar, estadoAtual } from '../progresso.js';

let d = null;
let id = null;
let cancelarOuvintes = [];

const ORDEM = ['01', '02', '03', '04', '05', '06'];

export function desmontar() {
  cancelarOuvintes.forEach((f) => f());
  cancelarOuvintes = [];
  clearInterval(tickCronometro);
  tickCronometro = null;
  inicioExecucao = null;
  ultimaLinha = '';
}

export async function montar({ conteudo, acoes, titulo, params }) {
  id = Number(params.id);
  await recarregar();

  titulo.textContent = d.proposta.cliente;
  conteudo.innerHTML = desenhar();
  acoes.innerHTML = botoesTopo();
  ligar(conteudo, acoes);

  // Só os eventos desta proposta interessam.
  const meu = (dados) => dados.proposta_id === id || dados.id === id;

  cancelarOuvintes.push(
    // A seção de execução vem do estado global — assim ela já nasce preenchida
    // quando o comercial abre a tela no meio de uma geração.
    observar(pintarExecucao),
    ouvir('progresso', (dados) => { if (meu(dados)) mostrarProgresso(dados); }),
    ouvir('fase', (dados) => { if (meu(dados)) marcarFase(dados); }),
    ouvir('proposta', async (dados) => {
      if (!meu(dados)) return;
      // Mudou de estado: o resto da tela (artefatos, PDF, valores) mudou junto.
      await recarregar();
      conteudo.innerHTML = desenhar();
      acoes.innerHTML = botoesTopo();
      ligar(conteudo, acoes);
      // `desenhar()` recria o elemento da seção vazio; sem repintar, ela some
      // até o próximo evento chegar.
      pintarExecucao(estadoAtual());
    }),
  );
}

async function recarregar() {
  d = await api.get(`/api/propostas/${id}`);
}

// ------------------------------------------------------------------- markup

function botoesTopo() {
  const p = d.proposta;
  const executando = p.status.startsWith('executando') || p.status === 'enfileirada';

  if (executando) {
    return `<button class="btn perigo" id="btn-cancelar">Cancelar execução</button>`;
  }
  if (p.status === 'aguardando_aprovacao') {
    return `<a class="btn primario" href="#/proposta/${id}/aprovar">Revisar e aprovar</a>`;
  }
  if (p.status === 'rascunho') {
    return `<button class="btn primario" id="btn-executar">Gerar proposta</button>`;
  }
  if (p.status === 'erro') {
    return `<button class="btn primario" id="btn-retomar">Retomar</button>`;
  }
  if (p.pdf_caminho) {
    return `<a class="btn primario" href="/api/propostas/${id}/pdf?baixar=1">Baixar PDF</a>
      <button class="btn" id="btn-reabrir" title="volta ao gate para mexer no escopo">Reabrir e editar escopo</button>`;
  }
  return '';
}

function desenhar() {
  const p = d.proposta;
  return `
    ${faixaEstado(p)}
    <section class="execucao" id="execucao"
             ${p.status.startsWith('executando') || p.status === 'enfileirada' ? '' : 'hidden'}></section>

    <div class="sec grid k2">
      ${cartaoResumo(p)}
      ${cartaoPipeline()}
    </div>

    ${p.pdf_caminho ? blocoPdf(p) : ''}
    ${blocoStatusComercial(p)}
    ${blocoAlertasLacunas()}
    ${blocoArtefatos()}
    ${blocoHistorico()}`;
}

function faixaEstado(p) {
  if (p.arquivada) {
    return `<div class="aviso-faixa info">
      <strong>Esta proposta foi removida do app.</strong>
      Ela não aparece no painel nem na listagem, mas os arquivos continuam no disco.
      <button class="btn pequeno" id="btn-restaurar" style="margin-left:10px">Trazer de volta</button>
    </div>`;
  }
  if (p.status === 'erro') {
    return `<div class="aviso-faixa erro">
      <strong>A geração parou.</strong> ${esc(p.erro_mensagem || 'sem detalhe registrado')}
      <div class="pequeno" style="margin-top:6px">
        Os artefatos já produzidos continuam no lugar — dá para retomar da fase que falhou.
      </div>
    </div>`;
  }
  if (p.status === 'aguardando_aprovacao') {
    return `<div class="aviso-faixa aviso">
      <strong>O orçamento está pronto e esperando você.</strong>
      O PDF só é gerado depois da aprovação.
      <a href="#/proposta/${id}/aprovar">Revisar ${esc(p.total_fmt || '')}</a>
    </div>`;
  }
  if (p.status === 'enfileirada') {
    return `<div class="aviso-faixa info">Na fila, aguardando a execução anterior terminar.</div>`;
  }
  return '';
}

function cartaoResumo(p) {
  const linha = (rot, valor) =>
    `<div class="linha-dado"><span>${esc(rot)}</span><strong>${valor}</strong></div>`;

  return `<div class="card">
    <div class="entre" style="margin-bottom:10px">
      <h2 class="mb0">Resumo</h2>
      ${badge(p.status, p.status_comercial)}
    </div>
    ${linha('Valor', p.total_fmt
      ? esc(p.total_fmt) + (p.total_tipo === 'mensal' ? '<span class="dim">/mês</span>' : '')
      : '<span class="dim">ainda não calculado</span>')}
    ${linha('Prazo', esc(p.prazo_fmt || '—'))}
    ${linha('Plataforma', esc(p.plataforma_res || p.plataforma || '—'))}
    ${linha('Modelo', esc(p.modelo_res || p.modelo || '—'))}
    ${linha('Contato', esc(p.contato || '—'))}
    ${linha('Validade', esc(p.validade ? p.validade.split('-').reverse().join('/') : '—'))}
    ${linha('Checkpoint', p.checkpoint_status === 'aprovado'
      ? `<span style="color:var(--ok)">aprovado ${esc(relativo(p.checkpoint_em))}</span>`
      : '<span class="dim">pendente</span>')}
    ${linha('Criada', esc(dataHora(p.criado_em)))}
    <div class="linha" style="margin-top:14px">
      <a class="btn pequeno" href="#/nova/${id}">Editar cadastro</a>
      <a class="btn pequeno" href="/api/propostas/${id}/exportar">Exportar</a>
      <button class="btn pequeno perigo" id="btn-excluir">Excluir</button>
    </div>
  </div>`;
}

function cartaoPipeline() {
  // Estado por fase: o manifest é a fonte, com as execuções recentes por cima.
  const doManifest = (d.manifest?.fases) || {};
  const chave = { '01': '01-briefing', '02': '02-escopo', '03': '03-orcamento',
                  '04': '04-narrativa', '05': '05-html', '06': '06-revisao' };

  const ultima = {};
  for (const f of d.fases) if (!ultima[f.fase]) ultima[f.fase] = f;

  const itens = ORDEM.map((n) => {
    const m = doManifest[chave[n]] || {};
    const f = ultima[n];
    const estado = f?.status === 'executando' ? 'executando'
      : m.status === 'concluida' ? 'ok'
      : m.status === 'desatualizada' ? 'velha'
      : f?.status === 'erro' ? 'erro' : 'pendente';
    const detalhe = f?.duracao_ms ? duracao(f.duracao_ms)
      : m.atualizado_em ? m.atualizado_em : '';
    return `<li class="fase ${estado}" data-fase="${n}">
      <span class="fase-n">${n}</span>
      <span class="fase-nome">${esc(NOME_FASE[n])}</span>
      <span class="fase-detalhe dim">${esc(detalhe)}${m.versao > 1 ? ` · v${m.versao}` : ''}</span>
    </li>`;
  }).join('');

  return `<div class="card">
    <h2>Pipeline</h2>
    <p class="pequeno dim mt0">
      A barreira fica depois da 03: sem aprovação, as fases 04 a 06 não rodam.
    </p>
    <ul class="fases">${itens}</ul>
  </div>`;
}

function blocoPdf(p) {
  const previews = d.previews.map((_, i) => `
    <a class="miniatura" href="/api/propostas/${id}/pdf" target="_blank" title="página ${i + 1}">
      <img src="/api/propostas/${id}/preview/${i + 1}" alt="página ${i + 1}" loading="lazy">
      <span>${i + 1}</span>
    </a>`).join('');

  return `<div class="sec card">
    <div class="entre" style="margin-bottom:12px">
      <h2 class="mb0">PDF</h2>
      <div class="linha">
        <span class="dim pequeno">${p.pdf_paginas || '?'} páginas · ${esc(relativo(p.pdf_gerado_em))}</span>
        ${p.checkpoint_status !== 'aprovado' ? `<p class="aviso-faixa aviso" style="margin:0 0 10px">
          <strong>O escopo mudou depois deste PDF.</strong> Ele continua aqui porque
          pode já ter ido para o cliente, mas não vale mais: aprove de novo para
          gerar a versão atual.
        </p>` : ''}
        <a class="btn pequeno" href="/api/propostas/${id}/pdf" target="_blank">Abrir</a>
        <a class="btn pequeno primario" href="/api/propostas/${id}/pdf?baixar=1">Baixar</a>
        <button class="btn pequeno" id="btn-rerender" title="refaz só o PDF a partir do HTML atual, sem reexecutar agente">Re-gerar</button>
      </div>
    </div>
    ${previews ? `<div class="miniaturas">${previews}</div>` : ''}
  </div>`;
}

function blocoStatusComercial(p) {
  if (p.status !== 'gerada') return '';
  const opcao = (valor, texto) => `
    <button class="btn pequeno ${p.status_comercial === valor ? 'primario' : ''}"
            data-comercial="${valor}">${texto}</button>`;

  return `<div class="sec card">
    <div class="entre">
      <div>
        <h2 class="mb0">Status comercial</h2>
        <div class="pequeno dim">
          ${p.enviada_em ? `enviada ${esc(relativo(p.enviada_em))}` : 'ainda não enviada'}
          ${p.decidida_em ? ` · decidida ${esc(relativo(p.decidida_em))}` : ''}
        </div>
      </div>
      <div class="linha" id="botoes-comercial">
        ${opcao('enviada', 'Enviada')}
        ${opcao('aceita', 'Aceita')}
        ${opcao('recusada', 'Recusada')}
      </div>
    </div>
  </div>`;
}

function blocoAlertasLacunas() {
  if (!d.alertas.length && !d.lacunas.length) return '';
  const altos = d.alertas.filter((a) => a.severidade === 'alta');
  return `<div class="sec card">
    <details ${altos.length ? 'open' : ''}>
      <summary><strong>Alertas e lacunas</strong>
        <span class="dim">— ${d.alertas.length} alerta(s), ${d.lacunas.length} lacuna(s)</span></summary>
      <ul class="alertas">${d.alertas.map((a) => `
        <li class="alerta ${esc(a.severidade)}"><div>
          <span class="mono alerta-codigo">${esc(a.codigo || '')}</span>
          <div>${esc(a.mensagem || '')}</div>
        </div></li>`).join('')}</ul>
      ${d.lacunas.length ? `<ul class="lacunas">${d.lacunas
        .map((l) => `<li><span>${esc(l.texto)}</span></li>`).join('')}</ul>` : ''}
    </details>
  </div>`;
}

function blocoArtefatos() {
  const item = (a) => `
    <li class="${a.existe ? '' : 'ausente'}">
      ${a.existe
        ? `<a href="/api/propostas/${id}/artefato/${encodeURIComponent(a.nome)}" target="_blank">${esc(a.nome)}</a>
           <span class="dim pequeno">${(a.bytes / 1024).toFixed(1)} KB</span>`
        : `<span>${esc(a.nome)}</span>
           <span class="dim pequeno">ausente — esta proposta não tem este arquivo</span>`}
    </li>`;

  const ausentes = d.artefatos.filter((a) => !a.existe).length;
  return `<div class="sec card">
    <details>
      <summary><strong>Artefatos</strong>
        <span class="dim">— ${d.artefatos.length - ausentes} de ${d.artefatos.length} presentes</span></summary>
      <ul class="artefatos">${d.artefatos.map(item).join('')}</ul>
    </details>
  </div>`;
}

function blocoHistorico() {
  const execs = d.execucoes.map((e) => `
    <li>
      <span class="badge ${e.status === 'concluida' ? 'aceita' : e.status === 'erro' ? 'erro' : 'rascunho'}">${esc(e.status)}</span>
      <span>${esc(e.alvo)}</span>
      <span class="dim pequeno">${esc(dataHora(e.enfileirada_em))}
</span>
      ${e.erro ? `<div class="pequeno" style="color:var(--erro)">${esc(e.erro)}</div>` : ''}
    </li>`).join('');

  const eventos = d.eventos.map((e) => `
    <li><span class="mono pequeno dim">${esc(e.tipo)}</span> ${esc(e.detalhe || '')}
      <span class="dim pequeno">${esc(relativo(e.criado_em))}</span></li>`).join('');

  return `<div class="sec card">
    <details>
      <summary><strong>Histórico</strong></summary>
      <div class="grid k2" style="margin-top:12px">
        <div><h3>Execuções</h3><ul class="historico">${execs || '<li class="dim">nenhuma</li>'}</ul></div>
        <div><h3>Eventos</h3><ul class="historico">${eventos || '<li class="dim">nenhum</li>'}</ul></div>
      </div>
    </details>
  </div>`;
}

// ---------------------------------------------------------------- ao vivo

let inicioExecucao = null;
let tickCronometro = null;
let ultimaLinha = '';

function tempo(s) {
  if (s == null) return '—';
  s = Math.max(0, Math.round(s));
  if (s < 60) return `${s}s`;
  const m = Math.floor(s / 60);
  if (m < 60) return `${m} min`;
  return `${Math.floor(m / 60)} h ${String(m % 60).padStart(2, '0')} min`;
}

function mostrarProgresso(dados) {
  ultimaLinha = dados.texto || '';
  const alvo = document.getElementById('exec-atividade');
  if (alvo) {
    alvo.textContent = ultimaLinha;
    alvo.classList.toggle('aviso', dados.tipo === 'aviso');
  }
}

/** A seção que responde "está rodando, em que pé, e quanto falta".
 *
 *  Ela é grande de propósito: durante uma geração, essa é a única pergunta que
 *  o comercial tem, e a resposta não pode estar numa tarja de 40px. */
function pintarExecucao(estado) {
  const secao = document.getElementById('execucao');
  if (!secao) return;

  const e = estado?.executando;
  const minha = e && e.proposta_id === id;

  if (!minha) {
    secao.hidden = true;
    clearInterval(tickCronometro);
    tickCronometro = null;
    inicioExecucao = null;
    return;
  }

  secao.hidden = false;
  secao.classList.remove('falhou');
  inicioExecucao ||= e.desde ? new Date(e.desde).getTime() : Date.now();

  const previsao = e.previsao;
  const fases = previsao?.fases || [];
  const feitas = fases.filter((f) => f.estado === 'concluida').length;
  const pct = fases.length
    ? Math.round(((feitas + (previsao.total_s ? 0.5 : 0)) / fases.length) * 100)
    : 5;

  const passo = (f) => {
    const marca = { concluida: '✓', atual: '', pendente: '' }[f.estado];
    return `<li class="passo ${f.estado}">
      <span class="passo-marca">${f.estado === 'atual' ? '<span class="girando"></span>' : marca || '○'}</span>
      <span class="passo-nome">${esc(NOME_FASE[f.fase] || f.fase)}</span>
      <span class="passo-tempo dim">${
        f.estado === 'concluida' ? 'pronto'
        : f.segundos <= 5 ? 'rápido'
        : `~${tempo(f.segundos)}`}</span>
    </li>`;
  };

  secao.innerHTML = `
    <div class="exec-cabecalho">
      <span class="girando grande"></span>
      <div>
        <h2 class="mb0">${esc(e.fase ? NOME_FASE[e.fase] || `Fase ${e.fase}` : 'Preparando')}</h2>
        <div class="dim pequeno">
          ${esc(e.cliente || '')}${e.tentativa > 1 ? ` · tentativa ${e.tentativa}` : ''}
        </div>
      </div>
      <div class="exec-numeros">
        <div><span class="exec-num" id="exec-decorrido">${
          tempo((Date.now() - inicioExecucao) / 1000)}</span><span class="dim"> decorrido</span></div>
        ${previsao ? `<div><span class="exec-num ciano">~${tempo(previsao.restante_s)}</span>
          <span class="dim"> restantes</span></div>` : ''}
      </div>
    </div>

    <div class="exec-trilho grande"><div class="exec-barra" style="width:${pct}%"></div></div>

    <ul class="passos">${fases.map(passo).join('')}</ul>

    <div class="exec-atividade">
      <span class="dim">agora:</span>
      <span id="exec-atividade">${esc(ultimaLinha || 'iniciando…')}</span>
    </div>

    <p class="exec-calma">
      Está tudo correndo bem — o silêncio é normal, o agente passa minutos lendo e
      escrevendo sem falar. <strong>Você pode fechar esta aba:</strong> o processo
      continua no servidor e o resultado fica salvo.
      ${previsao && !previsao.aprendido
        ? '<br><span class="dim pequeno">A estimativa ainda é a média de referência; ela se ajusta ao seu histórico depois de algumas propostas.</span>'
        : ''}
    </p>`;

  if (!tickCronometro) {
    const pintar = () => {
      const alvo = document.getElementById('exec-decorrido');
      if (alvo && inicioExecucao) alvo.textContent = tempo((Date.now() - inicioExecucao) / 1000);
    };
    pintar();
    tickCronometro = setInterval(pintar, 1000);
  }
}

/** Compatibilidade com os pontos que chamavam o cronômetro antigo. */
function cronometro(ligar) {
  if (!ligar) {
    clearInterval(tickCronometro);
    tickCronometro = null;
    inicioExecucao = null;
  }
}

function marcarFase(dados) {
  const li = document.querySelector(`.fase[data-fase="${dados.fase}"]`);
  if (li) li.className = `fase ${dados.status === 'executando' ? 'executando' : dados.status}`;
  if (dados.status === 'executando') ultimaLinha = '';
}

// ---------------------------------------------------------------- interação

function ligar(raiz, acoes) {
  /** Erro de ação aparece na tela, não num alert que o navegador pode suprimir
   *  e que some ao primeiro clique — foi assim que um "não disparou nada"
   *  ficou sem explicação. */
  const mostrarFalha = (mensagem) => {
    const secao = document.getElementById('execucao');
    if (!secao) return alert(mensagem);
    secao.hidden = false;
    secao.classList.add('falhou');
    secao.innerHTML = `
      <div class="exec-cabecalho">
        <span class="exec-x">×</span>
        <div>
          <h2 class="mb0">Não deu para iniciar</h2>
          <div class="dim pequeno">nada foi executado; a proposta continua como estava</div>
        </div>
      </div>
      <p class="exec-erro">${esc(mensagem)}</p>
      <div class="linha">
        <button class="btn pequeno" onclick="location.reload()">Recarregar a página</button>
      </div>`;
    secao.scrollIntoView({ behavior: 'smooth', block: 'center' });
  };

  const agir = async (fn, botao, rotuloEspera) => {
    if (botao) {
      botao.disabled = true;
      if (rotuloEspera) {
        botao.dataset.rotulo = botao.textContent;
        botao.textContent = rotuloEspera;
      }
    }
    try {
      await fn();
    } catch (err) {
      mostrarFalha(err.message);
      if (botao) {
        botao.disabled = false;
        if (botao.dataset.rotulo) botao.textContent = botao.dataset.rotulo;
      }
    }
  };

  // Entre o clique e o primeiro evento do servidor há uma janela de segundos.
  // Sem isto a tela fica idêntica e parece que o clique não pegou.
  const comecar = (fn) => async (e) => {
    ultimaLinha = 'enfileirando…';
    anunciarEnfileiramento(d.proposta);
    await agir(fn, e.target, 'enfileirando…');
  };

  acoes.querySelector('#btn-executar')?.addEventListener('click',
    comecar(() => api.post(`/api/propostas/${id}/executar`, { desde: '01' })));

  acoes.querySelector('#btn-retomar')?.addEventListener('click',
    comecar(() => api.post(`/api/propostas/${id}/executar`,
                           { desde: proximaFaseAposErro() })));

  acoes.querySelector('#btn-cancelar')?.addEventListener('click', (e) => {
    const emAndamento = d.execucoes.find((x) => ['fila', 'executando'].includes(x.status));
    if (!emAndamento) return;
    if (!confirm('Cancelar a execução? Os artefatos já produzidos são preservados.')) return;
    agir(() => api.post('/api/fila/cancelar', { execucao_id: emAndamento.id }), e.target);
  });

  acoes.querySelector('#btn-reabrir')?.addEventListener('click', async (e) => {
    e.target.disabled = true;
    try {
      await api.post(`/api/propostas/${id}/reabrir`, {});
      location.hash = `#/proposta/${id}/aprovar`;
    } catch (err) {
      e.target.disabled = false;
      alert(err.message || 'não deu para reabrir');
    }
  });

  raiz.querySelector('#btn-rerender')?.addEventListener('click',
    comecar(() => api.post(`/api/propostas/${id}/rerender`)));

  raiz.querySelector('#btn-excluir')?.addEventListener('click', async () => {
    const escolha = await perguntarExclusao(d.proposta);
    if (!escolha) return;

    const url = escolha === 'purgar'
      ? `/api/propostas/${id}?purgar=1&confirmacao=${encodeURIComponent(d.proposta.cliente)}`
      : `/api/propostas/${id}`;
    try {
      await api.del(url);
      // Apagada de vez não tem tela de detalhe para voltar.
      location.hash = escolha === 'purgar' ? '#/propostas' : `#/proposta/${id}`;
      if (escolha !== 'purgar') location.reload();
    } catch (err) {
      alert(err.message);
    }
  });

  raiz.querySelector('#btn-restaurar')?.addEventListener('click', (e) =>
    agir(async () => {
      await api.post(`/api/propostas/${id}/restaurar`);
      location.reload();
    }, e.target));

  raiz.querySelectorAll('[data-comercial]').forEach((b) =>
    b.addEventListener('click', () =>
      agir(() => api.post(`/api/propostas/${id}/status`,
                          { status_comercial: b.dataset.comercial }), b)));
}

/** Depois de um erro, retoma da fase que falhou — não do começo. */
function proximaFaseAposErro() {
  const falhou = d.fases.find((f) => f.status === 'erro');
  if (!falhou) return '01';
  return falhou.fase.replace(/[ab]$/, '');
}
