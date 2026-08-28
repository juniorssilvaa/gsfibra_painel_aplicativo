/**
 * Converte erros de API / rede em mensagens legíveis para o usuário final (sempre PT-BR).
 */
export const WHATSAPP_CALL_REJECTED_MSG = 'WhatsApp rejeitou a ligação de forma inesperada.';

const DEFAULT_FALLBACK = 'Ocorreu um erro. Tente novamente.';

function looksLikeHtml(text) {
  const t = String(text || '').trim();
  if (!t) return false;
  return (
    t.startsWith('<!DOCTYPE') ||
    t.startsWith('<html') ||
    t.startsWith('<HTML') ||
    /<\/?(html|head|body|title|style|script)\b/i.test(t)
  );
}

function looksLikeTechnicalEnglish(text) {
  const t = String(text || '').trim();
  if (!t) return false;
  if (/[áàâãéêíóôõúçÁÀÂÃÉÊÍÓÔÕÚÇ]/.test(t)) return false;
  return (
    /cloudflare|cf-ray|origin web server|invalid or incomplete response|misconfigured|overloaded/i.test(t) ||
    /bad gateway|gateway timeout|service unavailable|internal server error|attention required/i.test(t) ||
    /request failed with status code|network error|econnrefused|econnreset|etimedout/i.test(t) ||
    /traceback|exception inside application|stack trace|at\s+\w+\.\w+\(/i.test(t) ||
    /^(error|exception|failed|timeout|undefined|null)\b/i.test(t)
  );
}

function looksLikeCodePayload(text) {
  const t = String(text || '').trim();
  if (!t) return false;
  if (t.startsWith('{') || t.startsWith('[') || t.startsWith('<')) return true;
  if (/^HTTP\s*\d{3}\b/i.test(t)) return true;
  if (/^[A-Z_]{3,}=/.test(t)) return true;
  return false;
}

function messageForStatus(status, fallback) {
  if (status === 401) return 'Sessão expirada ou acesso não autorizado. Faça login novamente.';
  if (status === 403) return 'Você não tem permissão para realizar esta ação.';
  if (status === 404) return 'Informação não encontrada.';
  if (status === 408 || status === 504) return 'O servidor demorou para responder. Tente novamente.';
  if (status === 429) return 'Muitas tentativas. Aguarde um momento e tente novamente.';
  if (status === 502 || status === 503) {
    return 'Serviço temporariamente indisponível. Tente novamente em instantes.';
  }
  if (status >= 500) {
    return 'Erro interno no servidor. Tente novamente em instantes. Se continuar, contate o suporte.';
  }
  return fallback || DEFAULT_FALLBACK;
}

function sanitizeApiText(raw, status, fallback) {
  const text = String(raw || '').trim();
  if (!text) return '';
  if (looksLikeHtml(text)) return messageForStatus(status, fallback);
  if (looksLikeTechnicalEnglish(text)) return messageForStatus(status, fallback);
  if (looksLikeCodePayload(text)) return messageForStatus(status, fallback);
  if (/traceback|exception inside application|internal server error/i.test(text)) {
    return messageForStatus(status, fallback);
  }
  if (text.length > 220) return messageForStatus(status, fallback);
  return text;
}

export function mapVoiceCallApiError(raw) {
  const text = String(raw || '').trim();
  if (!text) return '';
  if (looksLikeHtml(text)) return '';
  if (looksLikeTechnicalEnglish(text)) return '';
  if (/no such call|439|sem sessão|e2e/i.test(text)) return WHATSAPP_CALL_REJECTED_MSG;
  if (/websocket not connected|whatsapp desconectado/i.test(text)) {
    return (
      'WhatsApp do QR desconectado ou há duas instâncias na porta 8080. ' +
      'Encerre a instância antiga e reinicie com .\\tools\\niohub-telefonia\\start-niohub-telefonia.ps1.'
    );
  }
  return text;
}

export function friendlyApiError(error, fallback = DEFAULT_FALLBACK) {
  const safeFallback = String(fallback || DEFAULT_FALLBACK).trim() || DEFAULT_FALLBACK;
  if (!error) return safeFallback;

  const status = error.response?.status;
  const data = error.response?.data;

  if (typeof data === 'string' && data.trim()) {
    const cleaned = sanitizeApiText(data, status, safeFallback);
    if (cleaned) return mapVoiceCallApiError(cleaned) || cleaned;
    return messageForStatus(status, safeFallback);
  }

  if (data && typeof data === 'object') {
    const candidates = [data.error, data.detail, data.message];
    for (const candidate of candidates) {
      if (typeof candidate === 'string' && candidate.trim()) {
        const cleaned = sanitizeApiText(candidate, status, safeFallback);
        if (cleaned) return mapVoiceCallApiError(cleaned) || cleaned;
      }
    }
    if (Array.isArray(data.non_field_errors) && data.non_field_errors.length) {
      const cleaned = sanitizeApiText(data.non_field_errors[0], status, safeFallback);
      if (cleaned) return cleaned;
    }
    const firstField = Object.values(data).find(
      (v) => (typeof v === 'string' && v.trim()) || (Array.isArray(v) && v[0])
    );
    if (typeof firstField === 'string') {
      const cleaned = sanitizeApiText(firstField, status, safeFallback);
      if (cleaned) return cleaned;
    }
    if (Array.isArray(firstField) && firstField[0]) {
      const cleaned = sanitizeApiText(firstField[0], status, safeFallback);
      if (cleaned) return cleaned;
    }
  }

  if (error.message === 'Network Error' || !error.response) {
    return 'Sem conexão com o servidor. Verifique sua internet e tente novamente.';
  }

  const rawMessage = typeof error.message === 'string' ? error.message.trim() : '';
  if (/^Request failed with status code \d+$/i.test(rawMessage)) {
    return messageForStatus(status, safeFallback);
  }
  if (status) return messageForStatus(status, safeFallback);

  if (
    rawMessage &&
    !looksLikeHtml(rawMessage) &&
    !looksLikeTechnicalEnglish(rawMessage) &&
    !looksLikeCodePayload(rawMessage) &&
    rawMessage.length <= 220
  ) {
    return rawMessage;
  }

  return safeFallback;
}
