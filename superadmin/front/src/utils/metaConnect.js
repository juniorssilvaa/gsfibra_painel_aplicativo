/**
 * Host central onde corre o SDK da Meta (ex.: https://connect.niohub.com.br).
 * Definido em build-time: VITE_META_CONNECT_ORIGIN.
 */
export function getMetaConnectOrigin() {
  const raw = (import.meta.env.VITE_META_CONNECT_ORIGIN || '').trim().replace(/\/+$/, '');
  return raw || null;
}

/**
 * Query no URL do iframe connect-inner para invalidar cache de CDN/browser
 * quando o fluxo Meta mudar (ex.: token por postMessage).
 * Incrementar após alterações críticas em connect-inner / hook.
 */
export const META_CONNECT_IFRAME_CACHE_BUSTER = '7';

/** true = usar fluxo via connect… (evita host JS SDK inválido no superadmin) */
export function shouldUseMetaConnectBridge() {
  const connect = getMetaConnectOrigin();
  if (!connect || typeof window === 'undefined') return false;
  return window.location.origin !== connect;
}

/** true = fluxo Meta em iframe connect… (mesma lógica do painel do provedor) */
export function shouldUseMetaConnectIframe() {
  return shouldUseMetaConnectBridge();
}

