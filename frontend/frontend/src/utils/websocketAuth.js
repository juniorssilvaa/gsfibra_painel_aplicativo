/**
 * Utilitário para autenticação WebSocket segura
 * Não expõe tokens em logs ou builds
 */

/**
 * Utilitário para autenticação WebSocket segura
 * CORRIGIDO: Usa auth_token (padrão do Login) em vez de token
 */
export const createAuthenticatedWebSocket = (url) => {
  try {
    // Priorizar auth_token que é o padrão salvo no Login, mas aceitar token também para compatibilidade
    const token = localStorage.getItem('auth_token') || localStorage.getItem('token');
    if (!token) {
      return new WebSocket(url);
    }
    
    const separator = url.includes('?') ? '&' : '?';
    const authenticatedUrl = `${url}${separator}token=${token}`;
    return new WebSocket(authenticatedUrl);
  } catch (_) {
    return new WebSocket(url);
  }
};

export const getWebSocketUrl = (baseUrl) => {
  try {
    // Priorizar auth_token que é o padrão salvo no Login, mas aceitar token também para compatibilidade
    const token = localStorage.getItem('auth_token') || localStorage.getItem('token');
    if (!token) {
      return baseUrl;
    }
    
    const separator = baseUrl.includes('?') ? '&' : '?';
    return `${baseUrl}${separator}token=${token}`;
  } catch (_) {
    return baseUrl;
  }
};
