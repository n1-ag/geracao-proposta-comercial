// Cliente HTTP do app. Toda chamada passa por aqui para que o tratamento de
// erro seja um só: o servidor sempre responde {erro:{codigo,mensagem,detalhe}}.

export class ErroApi extends Error {
  constructor(status, codigo, mensagem, detalhe) {
    super(mensagem);
    this.status = status;
    this.codigo = codigo;
    this.detalhe = detalhe;
  }
}

async function pedir(metodo, caminho, corpo) {
  let r;
  try {
    r = await fetch(caminho, {
      method: metodo,
      headers: corpo === undefined ? {} : { 'Content-Type': 'application/json' },
      body: corpo === undefined ? undefined : JSON.stringify(corpo),
    });
  } catch (e) {
    // Rede caiu ou o servidor morreu. Mensagem útil, não "Failed to fetch".
    throw new ErroApi(0, 'sem_conexao', 'o servidor do app não respondeu — ele ainda está rodando?');
  }

  if (r.status === 204) return null;

  const tipo = r.headers.get('Content-Type') || '';
  if (!tipo.includes('application/json')) {
    const texto = await r.text();
    if (!r.ok) throw new ErroApi(r.status, 'resposta_inesperada', texto.slice(0, 300));
    return texto;
  }

  const dados = await r.json();
  if (!r.ok) {
    const e = dados.erro || {};
    throw new ErroApi(r.status, e.codigo || 'erro', e.mensagem || 'erro desconhecido', e.detalhe);
  }
  return dados;
}

export const api = {
  get:  (c) => pedir('GET', c),
  post: (c, corpo) => pedir('POST', c, corpo ?? {}),
  put:  (c, corpo) => pedir('PUT', c, corpo ?? {}),
  del:  (c) => pedir('DELETE', c),
};
