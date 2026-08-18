// Conexão de eventos ao vivo.
//
// UM EventSource para a aba inteira, nunca um por card: HTTP/1.1 limita ~6
// conexões por origem e o app ficaria sem canal para as chamadas REST.
// Quem quer eventos assina aqui; a conexão é compartilhada.

const TIPOS = ['fila', 'fase', 'progresso', 'proposta', 'aviso', 'erro', 'chat'];

const ouvintes = new Map(TIPOS.map((t) => [t, new Set()]));
let fonte = null;
let tentativa = 0;
let timerReconexao = null;

/** Assina um tipo de evento. Devolve a função que cancela a assinatura. */
export function ouvir(tipo, fn) {
  if (!ouvintes.has(tipo)) throw new Error(`tipo de evento desconhecido: ${tipo}`);
  ouvintes.get(tipo).add(fn);
  conectar();
  return () => ouvintes.get(tipo).delete(fn);
}

function emitir(tipo, dados) {
  for (const fn of ouvintes.get(tipo)) {
    try { fn(dados); } catch (e) { console.error(`ouvinte de ${tipo} falhou`, e); }
  }
}

function conectar() {
  if (fonte && fonte.readyState !== EventSource.CLOSED) return;
  clearTimeout(timerReconexao);

  fonte = new EventSource('/api/eventos');

  fonte.onopen = () => {
    if (tentativa > 0) {
      // Voltou de uma queda: o estado pode ter andado enquanto estávamos fora.
      // Um evento perdido não volta, então ressincronizamos pelo REST.
      emitir('aviso', { tipo: 'reconectado', mensagem: 'conexão restabelecida' });
    }
    tentativa = 0;
  };

  for (const tipo of TIPOS) {
    fonte.addEventListener(tipo, (e) => {
      try { emitir(tipo, JSON.parse(e.data)); } catch { /* linha truncada */ }
    });
  }

  fonte.onerror = () => {
    fonte.close();
    // O EventSource reconecta sozinho, mas sem controle de intervalo: com o
    // servidor parado isso vira uma enxurrada de requisições. Fazemos na mão,
    // com espera crescente até 30 s.
    const espera = Math.min(1000 * 2 ** tentativa, 30000);
    tentativa += 1;
    timerReconexao = setTimeout(conectar, espera);
  };
}

export function conectado() {
  return fonte?.readyState === EventSource.OPEN;
}
