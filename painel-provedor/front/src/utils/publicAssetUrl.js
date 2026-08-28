/**
 * URL absoluta para ficheiros em `public/` (Vite copia para `dist/` na raiz do site).
 *
 * Usa `window.location.origin` + `import.meta.env.BASE_URL` para garantir que
 * o path seja sempre correcto, independente de onde o React Router está montado.
 *
 * @param {string} path — ex.: `sounds/01.mp3` ou `/sounds/01.mp3`
 * @returns {string}
 */
export function publicAssetUrl(path) {
  const rawBase = import.meta.env.BASE_URL ?? '/';
  const base = rawBase.endsWith('/') ? rawBase : `${rawBase}/`;
  const normalized = String(path || '').replace(/^\/+/, '');

  if (!normalized) {
    return base === '//' ? '/' : base;
  }

  // Usar URL absoluta com origin para evitar problemas com sub-paths do React Router
  const origin =
    typeof window !== 'undefined' && window.location?.origin
      ? window.location.origin
      : '';

  if (origin) {
    // base = '/' → origin + '/sounds/01.mp3'
    // base = '/app/' → origin + '/app/sounds/01.mp3'
    const prefix = base === '/' || base === '' ? '' : base.replace(/\/$/, '');
    return `${origin}${prefix}/${normalized}`;
  }

  // SSR fallback
  if (base === '/' || base === '') {
    return `/${normalized}`;
  }
  return `${base}${normalized}`;
}
