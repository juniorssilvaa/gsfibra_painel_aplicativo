/**
 * Utilitário para autenticação WebSocket segura
 * Usa ticket de curta duração — nunca expõe token DRF na query string.
 */

import { buildAuthenticatedWebSocketUrl } from './websocketUrl';

function toEndpoint(url) {
  if (url.includes('://')) {
    const parsed = new URL(url);
    return `${parsed.pathname}${parsed.search}`;
  }
  return url;
}

/**
 * Cria WebSocket com ticket realtime (async).
 * @param {string} url - endpoint ou URL completa ws(s)://...
 */
export const createAuthenticatedWebSocket = async (url) => {
  try {
    const authenticatedUrl = await buildAuthenticatedWebSocketUrl(toEndpoint(url));
    return new WebSocket(authenticatedUrl);
  } catch (_) {
    return new WebSocket(url);
  }
};

/**
 * Retorna URL de WebSocket autenticada com ticket (async).
 * @param {string} baseUrl - endpoint ou URL completa
 */
export const getWebSocketUrl = async (baseUrl) => {
  try {
    return await buildAuthenticatedWebSocketUrl(toEndpoint(baseUrl));
  } catch (_) {
    return baseUrl;
  }
};
