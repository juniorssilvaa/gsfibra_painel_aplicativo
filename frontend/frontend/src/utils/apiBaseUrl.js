const FRONT_HOST = 'chat.niohub.com.br';
const FRONT_LOCAL_HOST = 'chat-local.niohub.com.br';
const APP_HOST = 'chat.niohub.com.br';

function stripTrailingSlash(value = '') {
  return value.replace(/\/+$/, '');
}

export function getApiBaseUrl() {
  // PRIORIDADE 1: Variável de ambiente VITE_API_URL (padrão) ou VITE_API_BASE_URL (legado)
  const envApiUrl = import.meta.env.VITE_API_URL || import.meta.env.VITE_API_BASE_URL;
  if (envApiUrl) {
    // Remover trailing slash E também remover /api se estiver no final
    // Isso evita duplicação quando as rotas já começam com /api/
    let cleaned = stripTrailingSlash(envApiUrl);
    if (cleaned.endsWith('/api')) {
      cleaned = cleaned.slice(0, -4); // Remove '/api' do final
    }
    return cleaned;
  }
  
  // PRIORIDADE 2: Modo de desenvolvimento - SEMPRE usar proxy (vazio) ou localhost
  if (import.meta.env.DEV) {
    // Se VITE_USE_LOCAL_BACKEND estiver definido, sempre usar URL relativa (proxy)
    const forceLocalBackend = import.meta.env.VITE_USE_LOCAL_BACKEND === 'true';
    if (forceLocalBackend) {
      return '';
    }
    // Em desenvolvimento, usar proxy do Vite (URL relativa)
    return '';
  }

  // PRIORIDADE 3: Detecção por hostname (apenas em produção/staging)
  const hostname = window.location.hostname;
  
  // Em produção (chat.niohub.com.br ou qualquer subdomínio que não seja api/front)
  if (hostname.endsWith('niohub.com.br')) {
    if (hostname.startsWith('api')) {
      return ''; // Já está na API
    }
    if (hostname.startsWith('chat-local')) {
      return 'https://api-local.niohub.com.br';
    }
    if (hostname.startsWith('chat')) {
      return ''; // Usar proxy em chat.niohub.com.br
    }
    // Para chat.niohub.com.br ou qualquer outro (ex: cliente.niohub.com.br)
    return 'https://api.niohub.com.br';
  }

  // FALLBACK SEGURO: Em desenvolvimento, usar proxy (nunca produção)
  return '';
}

export function buildApiPath(path) {
  const normalizedPath = path?.startsWith('/') ? path : `/${path}`;
  const baseUrl = getApiBaseUrl();
  return baseUrl ? `${baseUrl}${normalizedPath}` : normalizedPath;
}

