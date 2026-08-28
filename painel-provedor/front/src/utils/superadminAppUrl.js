/**
 * URL base da app Superadmin (handoff a partir do painel do provedor).
 * Build-time: VITE_SUPERADMIN_APP_URL. Fallback para produção Niohub.
 */
export function getSuperadminAppBaseUrl() {
  const raw = import.meta.env.VITE_SUPERADMIN_APP_URL;
  const trimmed = typeof raw === 'string' ? raw.trim().replace(/\/$/, '') : '';
  return trimmed || 'https://app.niohub.com.br';
}
