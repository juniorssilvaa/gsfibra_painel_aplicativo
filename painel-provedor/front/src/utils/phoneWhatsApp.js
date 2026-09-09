/**
 * Normalização/validação de telefone para WhatsApp (E.164 sem '+').
 * Aceita DDI de qualquer país; só prefixa 55 em números que parecem BR local.
 */

export function digitsOnly(value) {
  return String(value || '').replace(/\D/g, '');
}

/** Telefone local BR (sem DDI): DDD + fixo (10) ou DDD + 9 + móvel (11). */
export function looksLikeBrazilianLocal(digits) {
  const d = digitsOnly(digits);
  if (d.length === 10) {
    return /^[1-9][1-9]\d{8}$/.test(d);
  }
  if (d.length === 11) {
    return /^[1-9][1-9]9\d{8}$/.test(d);
  }
  return false;
}

/**
 * Normaliza para dígitos internacionais.
 * - Já com '+' (ex.: +1… EUA, +351… PT) → mantém DDI
 * - BR local (10/11) → prefixa 55
 * - Já com DDI sem '+' (ex.: 1… EUA, 55… BR) → mantém
 */
export function normalizeWhatsAppPhone(value) {
  const raw = String(value || '').trim();
  let d = digitsOnly(raw);
  if (!d) return '';
  if (raw.startsWith('+')) {
    return d;
  }
  if (!d.startsWith('55') && looksLikeBrazilianLocal(d)) {
    d = `55${d}`;
  }
  return d;
}

/** E.164: 8–15 dígitos, não começa com 0. */
export function isValidWhatsAppPhone(value) {
  const d = normalizeWhatsAppPhone(value);
  return /^\d{8,15}$/.test(d) && !d.startsWith('0');
}

export const WHATSAPP_PHONE_HINT =
  'Use DDI + número (só dígitos).';

export const WHATSAPP_PHONE_ERROR =
  'Telefone inválido. Informe com DDI do país (8 a 15 dígitos).';
