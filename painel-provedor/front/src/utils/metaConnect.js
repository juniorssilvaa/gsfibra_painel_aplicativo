/**
 * Query no URL do iframe connect-inner para invalidar cache de CDN/browser
 * quando o fluxo Meta mudar (ex.: token por postMessage).
 * Incrementar após alterações críticas em connect-inner / hook.
 */
export const META_CONNECT_IFRAME_CACHE_BUSTER = '8';

/**
 * Host central onde corre o JS SDK da Meta (ex.: https://connect.niohub.com.br).
 * Definido em build-time: VITE_META_CONNECT_ORIGIN. Vazio = fluxo legacy no próprio subdomínio do provedor.
 */
export function getMetaConnectOrigin() {
  const raw = (import.meta.env.VITE_META_CONNECT_ORIGIN || '').trim().replace(/\/+$/, '');
  return raw || null;
}

/** true em localhost, *.local.niohub.com.br ou Vite dev (:8012) */
export function isLocalDevOrigin() {
  if (typeof window === 'undefined') return false;
  const host = window.location.hostname;
  const port = window.location.port;
  if (host === 'localhost' || host === '127.0.0.1') return true;
  if (host.endsWith('.local.niohub.com.br')) return true;
  if (port === '8012') return true;
  return false;
}

/** Origens confiáveis para postMessage do callback OAuth Instagram (api central). */
export function isInstagramOAuthMessageOrigin(origin) {
  if (!origin || origin === 'null') return true;
  if (origin === window.location.origin) return true;
  try {
    const host = new URL(origin).hostname;
    return host === 'api.niohub.com.br' || host === 'api-local.niohub.com.br';
  } catch {
    return false;
  }
}

export function shouldUseMetaConnectIframe() {
  const connect = getMetaConnectOrigin();
  if (!connect || typeof window === 'undefined') return false;
  return window.location.origin !== connect;
}

/** Valida origem do tenant passada na query (iframe). */
export function isAllowedTenantOriginForMeta(origin) {
  if (!origin || typeof origin !== 'string') return false;
  try {
    const u = new URL(origin);
    const host = u.hostname;
    if (host === 'localhost' || host === '127.0.0.1') {
      return u.protocol === 'http:' || u.protocol === 'https:';
    }
    if (u.protocol !== 'https:') return false;
    if (!host.endsWith('.niohub.com.br') && host !== 'niohub.com.br') return false;
    const connectHost = getMetaConnectOrigin();
    if (connectHost) {
      const ch = new URL(connectHost).hostname;
      if (host === ch) return false;
    }
    return true;
  } catch {
    return false;
  }
}
