/**
 * Utilitário centralizado para construir URLs de WebSocket
 * Garante que o domínio correto seja usado em todos os lugares
 * PRIORIDADE: Variáveis de ambiente > Modo DEV > Hostname
 */

/**
 * Obtém o domínio base para WebSocket baseado no ambiente
 * @returns {string} Domínio base para WebSocket (sem protocolo)
 */
export const getWebSocketHost = () => {
  // PRIORIDADE 1: Variável de ambiente VITE_WS_URL (mais confiável)
  const envWsUrl = import.meta.env.VITE_WS_URL;
  if (envWsUrl) {
    // Extrair host da URL (remover protocolo e path)
    try {
      const url = new URL(envWsUrl.startsWith('ws') ? envWsUrl : `ws://${envWsUrl}`);
      return url.host;
    } catch {
      // Se não for uma URL válida, tratar como host:port
      return envWsUrl.replace(/^wss?:\/\//, '').split('/')[0];
    }
  }
  
  // PRIORIDADE 2: Detecção por hostname (runtime, funciona em qualquer build)
  if (typeof window !== 'undefined' && window.location) {
    const hostname = window.location.hostname;
    
    // Se estiver em qualquer subdomínio niohub.com.br
    if (hostname.endsWith('niohub.com.br')) {
      if (hostname.startsWith('api-local') || hostname.startsWith('chat-local')) {
        return 'api-local.niohub.com.br';
      }
      // Padrão: api.niohub.com.br
      return 'api.niohub.com.br';
    }

    // Compatibilidade temporária com niohub.com.br
    if (hostname.endsWith('niohub.com.br')) {
      return 'api.niohub.com.br';
    }
    
    // Se estiver em desenvolvimento local, usar localhost
    if (hostname === 'localhost' || hostname === '127.0.0.1') {
      return 'localhost:8010';
    }
  }
  
  // PRIORIDADE 3: Modo de desenvolvimento (import.meta.env.DEV) - apenas se hostname não foi detectado
  if (import.meta.env.DEV) {
    return 'localhost:8010';
  }
  
  // FALLBACK SEGURO: Em caso de dúvida, usar api.niohub.com.br
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
 * Constrói uma URL completa de WebSocket
 * @param {string} endpoint - Endpoint do WebSocket (ex: '/ws/painel/1/')
 * @param {object} options - Opções adicionais
 * @param {string} options.token - Token de autenticação (opcional)
 * @returns {string} URL completa do WebSocket
 */
export const buildWebSocketUrl = (endpoint, options = {}) => {
  const protocol = getWebSocketProtocol();
  const host = getWebSocketHost();
  
  // Garantir que o endpoint comece com /
  const cleanEndpoint = endpoint.startsWith('/') ? endpoint : `/${endpoint}`;
  
  // Construir URL base
  let url = `${protocol}://${host}${cleanEndpoint}`;
  
  // Adicionar token se fornecido (priorizar auth_token que é o padrão do Login)
  const token = options.token || (typeof window !== 'undefined' ? (localStorage.getItem('auth_token') || localStorage.getItem('token')) : null);
  if (token) {
    const separator = url.includes('?') ? '&' : '?';
    url = `${url}${separator}token=${token}`;
  }
  
  return url;
};

export default {
  getWebSocketHost,
  getWebSocketProtocol,
  buildWebSocketUrl
};
