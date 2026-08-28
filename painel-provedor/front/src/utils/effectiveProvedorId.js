/**
 * Resolve o ID do provedor para rotas e pedidos API.
 * Evita URLs como /app/accounts/null/... ou ?provedor_id=null.
 */

export function parseRouteProvedorId(raw) {
  if (raw == null || raw === '') return null;
  const s = String(raw).trim().toLowerCase();
  if (s === 'null' || s === 'undefined' || s === 'nan') return null;
  const n = Number(raw);
  if (!Number.isFinite(n) || n <= 0) return null;
  return n;
}

export function effectiveProvedorFromUser(user) {
  if (!user || typeof user !== 'object') return null;

  const direct = parseRouteProvedorId(user.provedor_id);
  if (direct) return direct;

  const admins = user.provedores_admin;
  if (Array.isArray(admins) && admins.length > 0) {
    const first = parseRouteProvedorId(admins[0]);
    if (first) return first;
  }

  return null;
}

/**
 * Prioridade: segmento da rota (se válido) → dados do utilizador (/me/).
 */
export function getEffectiveProvedorId(routeParam, user) {
  return parseRouteProvedorId(routeParam) ?? effectiveProvedorFromUser(user);
}
