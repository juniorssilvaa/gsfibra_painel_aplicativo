// Configuração de ambiente - Separação entre desenvolvimento e produção
// PRIORIDADE: Variáveis de ambiente > Modo DEV > Hostname
// IMPORTANTE: Em desenvolvimento, SEMPRE usar localhost, nunca produção

const hostname = typeof window !== 'undefined' ? window.location.hostname : 'localhost';
const isProduction = hostname === 'chat.niohub.com.br' || hostname === 'app.niohub.com.br';
const isStaging = hostname === 'front.niohub.com.br';
const isStagingLocal = hostname === 'chat-local.niohub.com.br';
const isLocal = hostname === 'localhost' || hostname === '127.0.0.1';
const isDev = import.meta.env.DEV; // Modo de desenvolvimento do Vite

// Função auxiliar para obter URL de API
const getApiUrl = () => {
  // PRIORIDADE 1: Variável de ambiente VITE_API_URL
  const envApiUrl = import.meta.env.VITE_API_URL;
  if (envApiUrl) {
    return envApiUrl;
  }
  
  // PRIORIDADE 2: Modo de desenvolvimento - SEMPRE usar proxy (vazio) ou localhost
  if (isDev) {
    return ''; // Usa proxy do Vite em desenvolvimento
  }
  
  // PRIORIDADE 3: Detecção por hostname (apenas em produção/staging)
  if (isProduction || isStaging) {
    return 'https://api.niohub.com.br';
  }
  
  // Em staging local via Cloudflare Tunnel
  if (isStagingLocal) {
    return 'https://api-local.niohub.com.br';
  }
  
  // FALLBACK SEGURO: Em desenvolvimento, usar proxy (nunca produção)
  return '';
};

// Função auxiliar para obter URL de WebSocket
const getWsUrl = () => {
  // PRIORIDADE 1: Variável de ambiente VITE_WS_URL
  const envWsUrl = import.meta.env.VITE_WS_URL;
  if (envWsUrl) {
    return envWsUrl;
  }
  
  // PRIORIDADE 2: Modo de desenvolvimento - SEMPRE usar localhost
  if (isDev) {
    return 'ws://localhost:8010';
  }
  
  // PRIORIDADE 3: Detecção por hostname (apenas em produção/staging)
  if (isProduction || isStaging) {
    return 'wss://api.niohub.com.br';
  }
  
  // Em staging local via Cloudflare Tunnel
  if (isStagingLocal) {
    return 'wss://api-local.niohub.com.br';
  }
  
  // FALLBACK SEGURO: Em desenvolvimento, usar localhost (nunca produção)
  return 'ws://localhost:8010';
};

// Função auxiliar para obter URL de mídia
const getMediaUrl = () => {
  // PRIORIDADE 1: Variável de ambiente VITE_MEDIA_URL (se existir)
  const envMediaUrl = import.meta.env.VITE_MEDIA_URL;
  if (envMediaUrl) {
    return envMediaUrl;
  }
  
  // PRIORIDADE 2: Modo de desenvolvimento - SEMPRE usar localhost
  if (isDev) {
    return ''; // Usa proxy do Vite em desenvolvimento
  }
  
  // PRIORIDADE 3: Detecção por hostname (apenas em produção/staging)
  if (isProduction || isStaging) {
    return 'https://api.niohub.com.br';
  }
  
  // Em staging local via Cloudflare Tunnel
  if (isStagingLocal) {
    return 'https://api-local.niohub.com.br';
  }
  
  // FALLBACK SEGURO: Em desenvolvimento, usar localhost (nunca produção)
  return 'http://localhost:8010';
};

export const config = {
  // URLs baseadas em prioridade: env > DEV > hostname
  baseUrl: isProduction 
    ? 'https://chat.niohub.com.br'   // PRODUÇÃO
    : isStagingLocal
    ? 'https://chat-local.niohub.com.br'  // STAGING LOCAL (Cloudflare Tunnel)
    : isStaging
    ? 'https://front.niohub.com.br'  // STAGING/DESENVOLVIMENTO
    : 'http://localhost:8012',        // LOCAL
  
  // Configurações de API - prioriza variável de ambiente
  apiUrl: getApiUrl(),
  
  // Configurações de WebSocket - prioriza variável de ambiente
  wsUrl: getWsUrl(),
  
  // Configurações de mídia - prioriza variável de ambiente
  mediaUrl: getMediaUrl(),
}

// Função para construir URLs de mídia
export const buildMediaUrl = (fileUrl) => {
  if (!fileUrl) return null
  
  // Se já é uma URL completa
  if (fileUrl.startsWith('http')) {
    // Remover barra final se houver
    return fileUrl.endsWith('/') ? fileUrl.slice(0, -1) : fileUrl
  }
  
  const path = fileUrl.startsWith('/') ? fileUrl : `/${fileUrl}`
  let fullUrl = `${config.mediaUrl}${path}`
  
  // SEMPRE remover barra final para URLs de arquivo
  return fullUrl.endsWith('/') ? fullUrl.slice(0, -1) : fullUrl
}

// Função para construir URLs de API
export const buildApiUrl = (endpoint) => {
  return `${config.apiUrl}${endpoint}`
}

// Função para construir URLs de WebSocket
export const buildWsUrl = (endpoint) => {
  return `${config.wsUrl}${endpoint}`
}

export default config
