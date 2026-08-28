/** Barramento leve para eventos de chamada (sem SSE — evita dependências circulares). */
const listeners = new Set();
/** callIds de ligações iniciadas pelo painel (saída) — não abrir popup global. */
const outboundCallIds = new Set();
/** Atendente está em fluxo de saída (antes mesmo do callId existir). */
let outboundBusy = false;
/** Chamada ativa no host global (entrada) — ChatArea não deve abrir outro card. */
let globalActiveCallId = null;
/** Popup global de entrada visível (ringing) — ChatArea esconde painel de saída. */
let globalIncomingVisible = false;

function emit(msg) {
  listeners.forEach((fn) => {
    try {
      fn(msg);
    } catch (_) {}
  });
}

export function setOutboundVoiceBusy(busy) {
  outboundBusy = Boolean(busy);
  emit({ type: 'outbound-voice-busy', busy: outboundBusy });
}

export function isOutboundVoiceBusy() {
  return outboundBusy || outboundCallIds.size > 0;
}

export function setGlobalIncomingVisible(visible) {
  globalIncomingVisible = Boolean(visible);
  emit({ type: 'global-incoming-visible', visible: globalIncomingVisible });
}

export function isGlobalIncomingVisible() {
  return globalIncomingVisible;
}

export function setGlobalActiveVoiceCall(callId) {
  globalActiveCallId = String(callId || '').trim() || null;
  emit({ type: 'global-voice-active', callId: globalActiveCallId });
}

export function clearGlobalActiveVoiceCall(callId) {
  const id = String(callId || '').trim();
  if (id && globalActiveCallId && id !== globalActiveCallId) return;
  globalActiveCallId = null;
  emit({ type: 'global-voice-active', callId: null });
}

export function getGlobalActiveVoiceCall() {
  return globalActiveCallId;
}

export function registerOutboundVoiceCall(callId) {
  const id = String(callId || '').trim();
  if (id) outboundCallIds.add(id);
}

export function unregisterOutboundVoiceCall(callId) {
  const id = String(callId || '').trim();
  if (id) outboundCallIds.delete(id);
  if (outboundCallIds.size === 0) outboundBusy = false;
}

export function isOutboundVoiceCall(callId) {
  const id = String(callId || '').trim();
  return id ? outboundCallIds.has(id) : false;
}

export function isInboundVoiceEvent(msg, callId) {
  // Saída em andamento no painel: nunca abrir popup de "chamada recebida".
  if (outboundBusy || isOutboundVoiceCall(callId)) return false;
  const dir = String(msg?.direction || msg?.Direction || '').toLowerCase();
  if (dir === 'outbound') return false;
  if (dir === 'inbound') return true;
  // Sem direction explícita: só trata como entrada se não houver atividade de saída.
  return !isOutboundVoiceBusy();
}

export function dispatchVoiceCallEvent(msg) {
  if (!msg || typeof msg !== 'object') return;
  emit(msg);
}

export function addVoiceCallListener(handler) {
  listeners.add(handler);
  return () => listeners.delete(handler);
}
