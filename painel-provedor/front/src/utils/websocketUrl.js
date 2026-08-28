/**
 * Utilitário centralizado para construir URLs de WebSocket
 * Garante que o domínio correto seja usado em todos os lugares
 * PRIORIDADE: Variáveis de ambiente > Modo DEV > Hostname
 *
 * Autenticação: usa ticket de curta duração (?ticket=), nunca o token DRF longo.
 */

import { getRealtimeTicket } from './realtimeTicket';

/**
 * Obtém o domínio base para WebSocket baseado no ambiente
 * @returns {string} Domínio base para WebSocket (sem protocolo)
 */
export const getWebSocketHost = () => {
  // 1) Browser + niohub.com.br: mesmo host do painel (ignora VITE_WS_URL do CI, que costuma ser api.niohub.com.br).
  //    O build do Actions grava VITE_WS_URL no bundle; em stacks por subdomínio (e-tech, chat, …) o WS tem de ser no mesmo Host do Traefik.
  if (typeof window !== 'undefined' && window.location) {
    const hostname = window.location.hostname;
    const host = window.location.host;

    if (hostname.endsWith('niohub.com.br')) {
      if (hostname.startsWith('api-local') || hostname.startsWith('chat-local')) {
        return 'api-local.niohub.com.br';
      }
      if (!hostname.startsWith('api.')) {
        return host;
      }
    }

    if (hostname === 'localhost' || hostname === '127.0.0.1') {
      // Dev: Vite do painel (8012) — WS no mesmo host; proxy encaminha /ws → backend 8011
      const port = window.location.port;
      if (port === '8012' || !port) {
        return host;
      }
      const backendPort = import.meta.env.VITE_BACKEND_PORT || '8011';
      return `localhost:${backendPort}`;
    }
  }

  // 2) VITE_WS_URL (build): só quando não aplicámos regra de mesmo host acima (ex.: front servido em api.*).
  const envWsUrl = import.meta.env.VITE_WS_URL;
  if (envWsUrl) {
    try {
      const url = new URL(envWsUrl.startsWith('ws') ? envWsUrl : `ws://${envWsUrl}`);
      return url.host;
    } catch {
      return envWsUrl.replace(/^wss?:\/\//, '').split('/')[0];
    }
  }

  if (import.meta.env.DEV) {
    const backendPort = import.meta.env.VITE_BACKEND_PORT || '8011';
    return `localhost:${backendPort}`;
  }

  return 'api.niohub.com.br';
};

/**
 * Obtém o protocolo WebSocket baseado no ambiente
 * @returns {string} 'ws' ou 'wss'
 */
export const getWebSocketProtocol = () => {
  // Se VITE_WS_URL estiver definido, extrair protocolo da URL
  const envWsUrl = import.meta.env.VITE_WS_URL;
  if (envWsUrl) {
    if (envWsUrl.startsWith('wss://')) return 'wss';
    if (envWsUrl.startsWith('ws://')) return 'ws';
    // Se não tiver protocolo, inferir do ambiente
  }
  
  // Em desenvolvimento local (localhost), sempre usar ws (não wss)
  const hostname = typeof window !== 'undefined' ? window.location.hostname : 'localhost';
  if (hostname === 'localhost' || hostname === '127.0.0.1') {
    return 'ws';
  }
  
  // Em produção/staging (incluindo Cloudflare Tunnel), usar wss se a página estiver em HTTPS
  return window.location.protocol === 'https:' ? 'wss' : 'ws';
};

/**
 * Constrói URL de WebSocket (síncrono). Prefira buildAuthenticatedWebSocketUrl.
 * @param {string} endpoint
 * @param {object} options
 * @param {string} [options.ticket] - ticket realtime (obrigatório para auth)
 */
export const buildWebSocketUrl = (endpoint, options = {}) => {
  const protocol = getWebSocketProtocol();
  const host = getWebSocketHost();
  
  const cleanEndpoint = endpoint.startsWith('/') ? endpoint : `/${endpoint}`;
  let url = `${protocol}://${host}${cleanEndpoint}`;
  
  const ticket = options.ticket || null;
  if (ticket) {
    const separator = url.includes('?') ? '&' : '?';
    url = `${url}${separator}ticket=${encodeURIComponent(ticket)}`;
  }
  
  return url;
};

/**
 * Constrói URL de WebSocket com ticket fresco (nunca coloca token DRF na query).
 * Aceita options.token apenas como sinal de "usuário autenticado" (ignorado na URL).
 */
export const buildAuthenticatedWebSocketUrl = async (endpoint, options = {}) => {
  const hasAuth =
    options.ticket ||
    options.token ||
    (typeof window !== 'undefined' &&
      (localStorage.getItem('auth_token') || localStorage.getItem('token')));
  if (!hasAuth) {
    return buildWebSocketUrl(endpoint, {});
  }
  const ticket = options.ticket || (await getRealtimeTicket());
  if (!ticket) {
    return buildWebSocketUrl(endpoint, {});
  }
  return buildWebSocketUrl(endpoint, { ticket });
};

/**
 * Resolve endpoint de WebSocket do painel com fallback seguro.
 * Mantém compatibilidade por provedorId e habilita modo subdomínio via feature flag.
 */
export const buildPainelWebSocketEndpoint = (provedorId) => {
  const useSubdomainMode = String(import.meta.env.VITE_WS_PAINEL_BY_SUBDOMAIN || "false").toLowerCase() === "true";
  if (useSubdomainMode) {
    return "/ws/painel/";
  }
  if (provedorId) {
    return `/ws/painel/${provedorId}/`;
  }
  return "/ws/painel/";
};

export default {
  getWebSocketHost,
  getWebSocketProtocol,
  buildWebSocketUrl,
  buildAuthenticatedWebSocketUrl,
  buildPainelWebSocketEndpoint
};
