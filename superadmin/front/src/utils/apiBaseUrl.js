function stripTrailingSlash(value = '') {
  return value.replace(/\/+$/, '')
}

export function getApiBaseUrl() {
  const envApiUrl = import.meta.env.VITE_API_URL || ''
  if (envApiUrl) {
    let cleaned = stripTrailingSlash(envApiUrl)
    if (cleaned.endsWith('/api')) cleaned = cleaned.slice(0, -4)
    return cleaned
  }

  // Superadmin em produção usa mesmo domínio (app.niohub.com.br)
  // e Traefik roteia /api para o backend.
  return ''
}

export function buildApiPath(path) {
  const normalizedPath = path?.startsWith('/') ? path : `/${path}`
  const baseUrl = getApiBaseUrl()
  return baseUrl ? `${baseUrl}${normalizedPath}` : normalizedPath
}

/**
 * Origem absoluta do backend (OAuth redirect_uri, etc.).
 * Quando getApiBaseUrl() é '' (mesmo host que o painel), usa window.location.origin.
 */
export function getBackendAbsoluteBase() {
  const base = getApiBaseUrl()
  if (base) return stripTrailingSlash(base)
  if (typeof window !== 'undefined' && window.location?.origin) {
    return stripTrailingSlash(window.location.origin)
  }
  const envApiUrl = import.meta.env.VITE_API_URL || import.meta.env.VITE_API_BASE_URL
  if (envApiUrl) {
    let cleaned = stripTrailingSlash(envApiUrl)
    if (cleaned.endsWith('/api')) cleaned = cleaned.slice(0, -4)
    return cleaned
  }
  return 'https://api.niohub.com.br'
}
