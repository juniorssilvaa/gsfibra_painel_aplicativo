/** Produção — domínio público do superadmin. */
export const SUPERADMIN_PRODUCTION_ORIGIN = 'https://app.niohub.com.br';

/** Dev local — hosts apontando para localhost (ex.: nginx / etc/hosts). */
export const SUPERADMIN_LOCAL_ORIGIN = 'https://admin.niohub.com.br';

function stripTrailingSlash(value = '') {
  return String(value).replace(/\/+$/, '');
}

function isLocalDevHost(host = '') {
  return host === 'localhost' || host === '127.0.0.1' || host === 'admin.niohub.com.br';
}

/**
 * Origem usada para links externos (webhook Asaas, OAuth, etc.).
 * - Produção: app.niohub.com.br (ou VITE_SUPERADMIN_APP_URL)
 * - Local: admin.niohub.com.br quando em localhost / admin.niohub.com.br
 */
export function getSuperadminPublicOrigin() {
  const configured = import.meta.env.VITE_SUPERADMIN_APP_URL;
  if (configured && String(configured).trim()) {
    return stripTrailingSlash(String(configured).trim());
  }

  if (typeof window !== 'undefined' && window.location?.origin) {
    const host = window.location.hostname || '';
    if (isLocalDevHost(host)) {
      return SUPERADMIN_LOCAL_ORIGIN;
    }
    return stripTrailingSlash(window.location.origin);
  }

  return SUPERADMIN_PRODUCTION_ORIGIN;
}

export function getAsaasWebhookUrl() {
  return `${getSuperadminPublicOrigin()}/api/webhooks/asaas/`;
}

export function isSuperadminLocalDev() {
  if (typeof window === 'undefined') return false;
  return isLocalDevHost(window.location.hostname || '');
}
