// Cadastro de proposta. Um formulário só: identificação, enquadramento (com
// tudo em "auto" por padrão), a transcrição e as observações do comercial.

import { api } from '../api.js';
import { esc } from '../fmt.js';

let catalogo = null;

export async function montar({ conteudo, acoes, titulo, params }) {
  const id = params?.id ? Number(params.id) : null;
  if (id) titulo.textContent = 'Editar proposta';
  acoes.innerHTML = '';

  catalogo ||= await api.get('/api/catalogo');

  let dados = {};
  let entrada = { transcricao: '', observacoes: '' };
  if (id) {
    const d = await api.get(`/api/propostas/${id}`);
    dados = d.proposta;
    entrada = await api.get(`/api/propostas/${id}/entrada`);
  }

  conteudo.innerHTML = formulario(dados, entrada, id);
  ligar(conteudo, id);
}

// ------------------------------------------------------------------- markup

function campo(nome, rotulo, valor, extra = {}) {
  const { tipo = 'text', dica = '', placeholder = '', largura = '' } = extra;
  return `<label class="campo ${largura}">
    <span class="campo-rotulo">${esc(rotulo)}</span>
    <input type="${tipo}" name="${nome}" value="${esc(valor ?? '')}"
           placeholder="${esc(placeholder)}" autocomplete="off">
    ${dica ? `<span class="campo-dica">${esc(dica)}</span>` : ''}
  </label>`;
}

function seletor(nome, rotulo, valor, opcoes, dica) {
  const itens = opcoes
    .map((o) => `<option value="${esc(o.id)}" ${String(valor ?? '') === o.id ? 'selected' : ''}>${esc(o.nome)}</option>`)
    .join('');
  return `<label class="campo">
    <span class="campo-rotulo">${esc(rotulo)}</span>
    <select name="${nome}">${itens}</select>
    ${dica ? `<span class="campo-dica">${esc(dica)}</span>` : ''}
  </label>`;
}

const AUTO = { id: 'auto', nome: 'auto — o agente decide' };

function formulario(d, entrada, id) {
  const plataformas = [AUTO, ...catalogo.plataformas.map((p) => ({ id: p.id, nome: p.nome }))];
  const modelos = [AUTO, { id: 'implantacao', nome: 'Implantação' }, { id: 'evolucao', nome: 'Evolução' }];
  const naturezas = [AUTO, { id: 'migracao', nome: 'Migração' }, { id: 'novo', nome: 'Projeto novo' },
                     { id: 'evolucao', nome: 'Evolução' }];
  const layouts = [AUTO, { id: 'nao', nome: 'Não — o design é com a N1' },
                   { id: 'sim', nome: 'Sim — o cliente entrega o layout' }];

  const dataBR = (iso) => (iso ? iso.split('-').reverse().join('/') : '');

  return `
  <form id="form-proposta" class="formulario">
    <div class="aviso-faixa info" id="aviso" hidden></div>

    <div class="card sec">
      <h2>Quem é o cliente</h2>
      <p class="pequeno dim mt0">
        Campo que você não souber, deixe em branco — vira lacuna declarada na proposta.
        Uma lacuna visível custa uma pergunta; um dado errado custa a conta.
      </p>
      <div class="campos">
        ${campo('cliente', 'Cliente *', d.cliente, { placeholder: 'Nome pelo qual a empresa é conhecida' })}
        ${campo('razao_social', 'Razão social', d.razao_social)}
        ${campo('contato', 'Contato', d.contato, { placeholder: 'Quem decide do lado do cliente' })}
        ${campo('cargo_contato', 'Cargo do contato', d.cargo_contato)}
        ${campo('email', 'E-mail', d.email, { tipo: 'email' })}
        ${campo('whatsapp', 'WhatsApp', d.whatsapp, { placeholder: '(21) 99999-0000' })}
        ${campo('validade', 'Validade da proposta', dataBR(d.validade), {
          placeholder: 'DD/MM/AAAA',
          dica: `em branco = ${catalogo.validade_dias_padrao} dias a partir de hoje`,
        })}
      </div>
    </div>

    <div class="card sec">
      <h2>Enquadramento comercial</h2>
      <p class="pequeno dim mt0">
        Preencha só o que já estiver decidido. Em <strong>auto</strong>, o agente infere
        da transcrição e mostra os sinais que usou — você confere no orçamento.
      </p>
      <div class="campos">
        ${seletor('modelo', 'Modelo da proposta', d.modelo ?? 'auto', modelos)}
        ${seletor('plataforma', 'Plataforma', d.plataforma ?? 'auto', plataformas)}
        ${seletor('natureza', 'Natureza', d.natureza ?? 'auto', naturezas)}
        ${seletor('layout_do_cliente', 'Layout fornecido pelo cliente',
                  d.layout_do_cliente == null ? 'auto' : (d.layout_do_cliente ? 'sim' : 'nao'),
                  layouts, 'sim abate a parcela de design do valor base')}
        ${campo('pacote_mensal_h', 'Pacote mensal recomendado', d.pacote_mensal_h, {
          tipo: 'number', dica: 'em horas; só para modelo evolução',
        })}
      </div>
    </div>

    <div class="card sec">
      <h2>A reunião</h2>
      <div class="campos">
        ${campo('reuniao_por', 'Conduzida por', d.reuniao_por)}
        ${campo('data_reuniao', 'Data', dataBR(d.data_reuniao), { placeholder: 'DD/MM/AAAA' })}
        ${campo('outros_presentes', 'Outros presentes', d.outros_presentes, { largura: 'largo' })}
      </div>

      <label class="campo largo" style="margin-top:16px">
        <span class="campo-rotulo">Transcrição *</span>
        <textarea name="transcricao" rows="14" spellcheck="false"
          placeholder="Cole aqui a transcrição bruta, do jeito que saiu da ferramenta de gravação.">${esc(entrada.transcricao)}</textarea>
        <span class="campo-dica">
          <strong>Não limpe a transcrição.</strong> Hesitação, repetição e desvio de assunto
          são informação — é neles que o agente encontra o que o cliente não disse com todas as letras.
          <span id="contador-transcricao" class="dim"></span>
        </span>
      </label>

      <label class="campo largo" style="margin-top:16px">
        <span class="campo-rotulo">Observações do comercial</span>
        <textarea name="observacoes" rows="6"
          placeholder="O que você sabe e não está na gravação: contexto de conversas anteriores, o clima da reunião, o que ficou implícito, o que o cliente evitou dizer.">${esc(entrada.observacoes)}</textarea>
        <span class="campo-dica">
          Analisadas <em>junto</em> com a transcrição. Ficam marcadas como <span class="mono">[O##]</span>
          na proposta, separadas das falas do cliente — e quando as duas divergirem, prevalece a transcrição.
        </span>
      </label>
    </div>

    <div class="linha">
      <button type="submit" class="btn primario" id="salvar">
        ${id ? 'Salvar alterações' : 'Criar proposta'}
      </button>
      ${id ? `<a class="btn" href="#/proposta/${id}">Cancelar</a>`
           : '<a class="btn" href="#/painel">Cancelar</a>'}
      <span class="dim pequeno" id="estado-salvar"></span>
    </div>
  </form>`;
}

// ---------------------------------------------------------------- interação

function ligar(raiz, id) {
  const form = raiz.querySelector('#form-proposta');
  const aviso = raiz.querySelector('#aviso');
  const botao = raiz.querySelector('#salvar');
  const estado = raiz.querySelector('#estado-salvar');
  const transcricao = form.elements.transcricao;
  const contador = raiz.querySelector('#contador-transcricao');

  const atualizarContador = () => {
    const n = transcricao.value.length;
    contador.textContent = n ? ` · ${n.toLocaleString('pt-BR')} caracteres coladas` : '';
  };
  transcricao.addEventListener('input', atualizarContador);
  atualizarContador();

  form.addEventListener('submit', async (e) => {
    e.preventDefault();
    aviso.hidden = true;
    botao.disabled = true;
    estado.textContent = 'salvando…';

    const corpo = Object.fromEntries(new FormData(form).entries());

    try {
      if (id) {
        await api.put(`/api/propostas/${id}`, corpo);
        location.hash = `#/proposta/${id}`;
      } else {
        const r = await api.post('/api/propostas', corpo);
        location.hash = `#/proposta/${r.id}`;
      }
    } catch (err) {
      aviso.className = 'aviso-faixa erro';
      aviso.innerHTML = `<strong>Não deu para salvar.</strong> ${esc(err.message)}`;
      aviso.hidden = false;
      aviso.scrollIntoView({ behavior: 'smooth', block: 'center' });
      botao.disabled = false;
      estado.textContent = '';
    }
  });
}
