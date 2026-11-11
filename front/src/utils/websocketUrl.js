/**
 * URLs WebSocket — GSFibra usa o backend do Superadmin.
 * Preferir VITE_WS_URL; senão host da API / fallback Niohub.
 */

export const getWebSocketHost = () => {
  const envWsUrl = import.meta.env.VITE_WS_URL
  if (envWsUrl) {
    try {
      const url = new URL(envWsUrl.startsWith('ws') ? envWsUrl : `ws://${envWsUrl}`)
      return url.host
    } catch {
      return envWsUrl.replace(/^wss?:\/\//, '').split('/')[0]
    }
  }

  const envApi = import.meta.env.VITE_API_URL || ''
  if (envApi) {
    try {
      return new URL(envApi).host
    } catch {
      /* ignore */
    }
  }

  if (typeof window !== 'undefined' && window.location) {
    const hostname = window.location.hostname

    if (hostname === 'gsfibra.niohub.com.br' || hostname === 'app.niohub.com.br') {
      return 'app.niohub.com.br'
    }

    if (hostname.endsWith('niohub.com.br')) {
      if (hostname.startsWith('api-local') || hostname.startsWith('chat-local')) {
        return 'api-local.niohub.com.br'
      }
      return 'app.niohub.com.br'
    }

    if (hostname === 'localhost' || hostname === '127.0.0.1') {
      return 'localhost:8010'
    }
  }

  if (import.meta.env.DEV) {
    return 'localhost:8010'
  }

  return 'app.niohub.com.br'
}

export const getWebSocketProtocol = () => {
  const envWsUrl = import.meta.env.VITE_WS_URL
  if (envWsUrl) {
    if (envWsUrl.startsWith('wss://')) return 'wss'
    if (envWsUrl.startsWith('ws://')) return 'ws'
  }

  const hostname = typeof window !== 'undefined' ? window.location.hostname : 'localhost'
  if (hostname === 'localhost' || hostname === '127.0.0.1') {
    return 'ws'
  }

  return window.location.protocol === 'https:' ? 'wss' : 'ws'
}

export const buildWebSocketUrl = (endpoint, options = {}) => {
  const protocol = getWebSocketProtocol()
  const host = getWebSocketHost()
  const cleanEndpoint = endpoint.startsWith('/') ? endpoint : `/${endpoint}`
  let url = `${protocol}://${host}${cleanEndpoint}`

  const token =
    options.token ||
    (typeof window !== 'undefined' ? localStorage.getItem('auth_token') || localStorage.getItem('token') : null)
  if (token) {
    const separator = url.includes('?') ? '&' : '?'
    url = `${url}${separator}token=${token}`
  }

  return url
}

export default {
  getWebSocketHost,
  getWebSocketProtocol,
  buildWebSocketUrl,
}
