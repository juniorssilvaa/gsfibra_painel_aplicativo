// Configuração de ambiente - Separação entre desenvolvimento e produção
// PRIORIDADE: Variáveis de ambiente > Modo DEV > Hostname
// IMPORTANTE: Em desenvolvimento, SEMPRE usar localhost, nunca produção

const hostname = typeof window !== 'undefined' ? window.location.hostname : 'localhost';
// Multi-tenant: qualquer subdomínio *.niohub.com.br é produção
const isNiohubDomain = hostname.endsWith('niohub.com.br');
const isProduction = isNiohubDomain && !hostname.startsWith('chat-local') && !hostname.startsWith('front');
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
  // Multi-tenant: cada provedor tem sua própria API no mesmo subdomínio via Traefik
  if (isProduction || isStaging) {
    return ''; // URL relativa - Traefik roteia /api/ para o backend correto
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
  
  // PRIORIDADE 2: Dev — mesmo host do Vite (proxy /ws → backend 8011)
  if (isDev) {
    if (typeof window !== 'undefined' && window.location?.host) {
      return `ws://${window.location.host}`;
    }
    const backendPort = import.meta.env.VITE_BACKEND_PORT || '8011';
    return `ws://localhost:${backendPort}`;
  }
  
  // PRIORIDADE 3: Detecção por hostname (apenas em produção/staging)
  // Multi-tenant: WebSocket no mesmo subdomínio
  if (isProduction || isStaging) {
    return `wss://${hostname}`;
  }
  
  // Em staging local via Cloudflare Tunnel
  if (isStagingLocal) {
    return 'wss://api-local.niohub.com.br';
  }
  
  const backendPort = import.meta.env.VITE_BACKEND_PORT || '8011';
  return `ws://localhost:${backendPort}`;
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
  // Multi-tenant: mídia servida pelo mesmo subdomínio
  if (isProduction || isStaging) {
    return ''; // URL relativa
  }
  
  // Em staging local via Cloudflare Tunnel
  if (isStagingLocal) {
    return 'https://api-local.niohub.com.br';
  }
  
  const backendPort = import.meta.env.VITE_BACKEND_PORT || '8011';
  return `http://localhost:${backendPort}`;
};

export const config = {
  // URLs baseadas em prioridade: env > DEV > hostname
  // Multi-tenant: usa o hostname atual como base
  baseUrl: isProduction 
    ? `https://${hostname}`            // PRODUÇÃO (qualquer subdomínio)
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

// Função para construir URLs de mídia (preserva ?expires=&sig= da assinatura)
export const buildMediaUrl = (fileUrl) => {
  if (!fileUrl) return null

  // Preservar trailing slash das rotas Django (/api/media/.../) para a assinatura bater com request.path
  const stripTrailingSlashKeepQuery = (url) => {
    const isApiMedia = url.includes('/api/media/')
    if (isApiMedia) return url
    if (!url.includes('?')) {
      return url.endsWith('/') ? url.slice(0, -1) : url
    }
    const [pathPart, queryPart] = url.split('?', 2)
    const cleanPath = pathPart.endsWith('/') ? pathPart.slice(0, -1) : pathPart
    return `${cleanPath}?${queryPart}`
  }
  
  // URL absoluta: em dev, usar só o path (+query) para passar pelo proxy do Vite (/media)
  if (fileUrl.startsWith('http')) {
    try {
      const parsed = new URL(fileUrl)
      if (parsed.pathname.startsWith('/media/') || parsed.pathname.startsWith('media/') ||
          parsed.pathname.startsWith('/api/media/')) {
        const path = parsed.pathname.startsWith('/') ? parsed.pathname : `/${parsed.pathname}`
        const withQuery = parsed.search ? `${path}${parsed.search}` : path
        return stripTrailingSlashKeepQuery(withQuery)
      }
    } catch (_) {}
    return stripTrailingSlashKeepQuery(fileUrl)
  }
  
  const path = fileUrl.startsWith('/') ? fileUrl : `/${fileUrl}`
  let fullUrl = `${config.mediaUrl}${path}`
  
  return stripTrailingSlashKeepQuery(fullUrl)
}

/** Abre mídia em nova aba sem navegar o painel (usa token para /api/media/). */
export const openMediaInNewTab = async (fileUrl, event) => {
  if (event) {
    event.preventDefault()
    event.stopPropagation()
  }
  const mediaUrl = buildMediaUrl(fileUrl)
  if (!mediaUrl) return

  const token = localStorage.getItem('auth_token') || localStorage.getItem('token')

  if (mediaUrl.includes('/api/media/') && token) {
    try {
      const response = await fetch(mediaUrl, {
        method: 'GET',
        headers: {
          Authorization: `Token ${token}`,
          Accept: '*/*',
        },
        credentials: 'include',
      })
      if (response.ok) {
        const blob = await response.blob()
        if (blob && blob.size > 0) {
          const blobUrl = window.URL.createObjectURL(blob)
          const popup = window.open(blobUrl, '_blank', 'noopener,noreferrer')
          if (popup) {
            setTimeout(() => window.URL.revokeObjectURL(blobUrl), 120000)
            return
          }
          window.URL.revokeObjectURL(blobUrl)
        }
      }
    } catch (_) {
      /* fallback abaixo */
    }
  }

  window.open(mediaUrl, '_blank', 'noopener,noreferrer')
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
