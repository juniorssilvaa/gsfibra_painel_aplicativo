/** Evento disparado quando a API indica provedor bloqueado por inadimplência. */
export const PROVEDOR_PAYMENT_BLOCKED_EVENT = 'niohub:provedor-payment-blocked';

export const PROVEDOR_PAYMENT_BLOCKED_CODE = 'PROVEDOR_PAYMENT_BLOCKED';

/**
 * Detecta 403 de suspensão/inadimplência (middleware / ProvedorNotSuspended).
 */
export function isProvedorPaymentBlockedError(error) {
  const status = error?.response?.status;
  if (status !== 403) return false;

  const data = error?.response?.data;
  if (data && typeof data === 'object') {
    if (data.code === PROVEDOR_PAYMENT_BLOCKED_CODE) return true;
    const text = String(data.detail || data.error || data.message || '').toLowerCase();
    if (
      text.includes('fatura está em atraso') ||
      text.includes('fatura em atraso') ||
      text.includes('reativar o acesso') ||
      text.includes('acesso suspenso') ||
      text.includes('inadimpl') ||
      text.includes('regularize o pagamento')
    ) {
      return true;
    }
  }
  return false;
}

export function emitProvedorPaymentBlocked() {
  if (typeof window === 'undefined') return;
  window.dispatchEvent(new CustomEvent(PROVEDOR_PAYMENT_BLOCKED_EVENT));
}
