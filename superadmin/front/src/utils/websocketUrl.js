/**
 * URLs WebSocket — mesmo contrato do painel-provedor.
 * Em admin.niohub.com.br (Superadmin same-origin), usa o host da página quando não há VITE_WS_URL.
 */

export const getWebSocketHost = () => {
  const envWsUrl = import.meta.env.VITE_WS_URL;
  if (envWsUrl) {
    try {
      const url = new URL(envWsUrl.startsWith('ws') ? envWsUrl : `ws://${envWsUrl}`);
      return url.host;
    } catch {
      return envWsUrl.replace(/^wss?:\/\//, '').split('/')[0];
    }
  }

  if (
    typeof window !== 'undefined'
    && (window.location?.hostname === 'admin.niohub.com.br'
      || window.location?.hostname === 'app.niohub.com.br')
  ) {
    return window.location.host;
  }

  if (typeof window !== 'undefined' && window.location) {
    const hostname = window.location.hostname;

    if (hostname.endsWith('niohub.com.br')) {
      if (hostname.startsWith('api-local') || hostname.startsWith('chat-local')) {
        return 'api-local.niohub.com.br';
      }
      return 'api.niohub.com.br';
    }

    if (hostname === 'localhost' || hostname === '127.0.0.1') {
      return 'localhost:8010';
    }
  }

  if (import.meta.env.DEV) {
    return 'localhost:8010';
  }

  return 'api.niohub.com.br';
};

export const getWebSocketProtocol = () => {
  const envWsUrl = import.meta.env.VITE_WS_URL;
  if (envWsUrl) {
    if (envWsUrl.startsWith('wss://')) return 'wss';
    if (envWsUrl.startsWith('ws://')) return 'ws';
  }

  const hostname = typeof window !== 'undefined' ? window.location.hostname : 'localhost';
  if (hostname === 'localhost' || hostname === '127.0.0.1') {
    return 'ws';
  }

  return window.location.protocol === 'https:' ? 'wss' : 'ws';
};

export const buildWebSocketUrl = (endpoint, options = {}) => {
  const protocol = getWebSocketProtocol();
  const host = getWebSocketHost();

  const cleanEndpoint = endpoint.startsWith('/') ? endpoint : `/${endpoint}`;

  let url = `${protocol}://${host}${cleanEndpoint}`;

  const token =
    options.token ||
    (typeof window !== 'undefined' ? localStorage.getItem('auth_token') || localStorage.getItem('token') : null);
  if (token) {
    const separator = url.includes('?') ? '&' : '?';
    url = `${url}${separator}token=${token}`;
  }

  return url;
};

export const buildPainelWebSocketEndpoint = (provedorId) => {
  const useSubdomainMode = String(import.meta.env.VITE_WS_PAINEL_BY_SUBDOMAIN || 'false').toLowerCase() === 'true';
  if (useSubdomainMode) {
    return '/ws/painel/';
  }
  if (provedorId) {
    return `/ws/painel/${provedorId}/`;
  }
  return '/ws/painel/';
};

export default {
  getWebSocketHost,
  getWebSocketProtocol,
  buildWebSocketUrl,
  buildPainelWebSocketEndpoint,
};
