const FRONT_HOST = 'chat.niohub.com.br';
const FRONT_LOCAL_HOST = 'chat-local.niohub.com.br';
const APP_HOST = 'chat.niohub.com.br';

function stripTrailingSlash(value = '') {
  return value.replace(/\/+$/, '');
}

export function getApiBaseUrl() {
  const hostname = typeof window !== 'undefined' ? window.location.hostname : 'localhost';

  // PRIORIDADE 1: Multi-tenant detection (Produção niohub.com.br)
  if (hostname.endsWith('niohub.com.br')) {
    // Se for subdomínio da API, usa URL relativa
    if (hostname.startsWith('api')) {
      return '';
    }
    // Se for staging local
    if (hostname.startsWith('chat-local')) {
      return 'https://api-local.niohub.com.br';
    }
    // Para qualquer outro subdomínio (e-tech, chat, etc)
    // O Traefik roteia /api/ para o backend correto
    return '';
  }

  // PRIORIDADE 2: Variável de ambiente (Especialmente para builds customizados ou outros domínios)
  const envApiUrl = import.meta.env.VITE_API_URL || import.meta.env.VITE_API_BASE_URL;
  if (envApiUrl) {
    let cleaned = stripTrailingSlash(envApiUrl);
    if (cleaned.endsWith('/api')) {
      cleaned = cleaned.slice(0, -4);
    }
    return cleaned;
  }
  
  // PRIORIDADE 3: Modo de desenvolvimento (localhost)
  if (import.meta.env.DEV) {
    return ''; // Usa proxy do Vite
  }

  return '';
}

export function buildApiPath(path) {
  const normalizedPath = path?.startsWith('/') ? path : `/${path}`;
  const baseUrl = getApiBaseUrl();
  return baseUrl ? `${baseUrl}${normalizedPath}` : normalizedPath;
}

/**
 * URL do SSE de ligações (sem credenciais na query).
 * Auth vai no header Authorization via fetch (ver voiceCallEventBus).
 * Em localhost DEV: Django direto (8011) para evitar buffering do Vite.
 * Em host de tunnel/produção: mesma origem (proxy Traefik/Vite).
 */
export function buildVoiceCallEventsUrl() {
  if (import.meta.env.DEV && typeof window !== 'undefined') {
    const { hostname } = window.location;
    const envBase = stripTrailingSlash(
      import.meta.env.VITE_SSE_BACKEND_URL || import.meta.env.VITE_API_URL || ''
    );
    if (envBase) {
      return `${envBase}/api/voice-calls/events/`;
    }
    if (hostname === 'localhost' || hostname === '127.0.0.1') {
      return 'http://127.0.0.1:8011/api/voice-calls/events/';
    }
    // chat.niohub.com.br / tunnel: NÃO usar :8011 — passa pelo proxy da mesma origem
    return buildApiPath('/api/voice-calls/events/');
  }
  return buildApiPath('/api/voice-calls/events/');
}

/**
 * Origem absoluta do backend (OAuth redirect_uri, proxy de media, etc.).
 * Quando getApiBaseUrl() é '' (mesmo host que o painel), usa window.location.origin.
 */
export function getBackendAbsoluteBase() {
  const base = getApiBaseUrl();
  if (base) {
    return stripTrailingSlash(base);
  }
  if (typeof window !== 'undefined' && window.location?.origin) {
    return stripTrailingSlash(window.location.origin);
  }
  const envApiUrl = import.meta.env.VITE_API_URL || import.meta.env.VITE_API_BASE_URL;
  if (envApiUrl) {
    let cleaned = stripTrailingSlash(envApiUrl);
    if (cleaned.endsWith('/api')) {
      cleaned = cleaned.slice(0, -4);
    }
    return cleaned;
  }
  if (import.meta.env.DEV) {
    return 'http://localhost:8010';
  }
  return 'https://api.niohub.com.br';
}

