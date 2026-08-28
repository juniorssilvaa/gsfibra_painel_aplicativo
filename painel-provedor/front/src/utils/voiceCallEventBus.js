import { buildVoiceCallEventsUrl } from './apiBaseUrl';
import { addVoiceCallListener, dispatchVoiceCallEvent } from './voiceCallPainelBus';

export { dispatchVoiceCallEvent } from './voiceCallPainelBus';

let abortCtrl = null;
let refCount = 0;
let reconnectTimer = null;
let connecting = false;

function scheduleReconnect() {
  if (reconnectTimer || refCount === 0) return;
  reconnectTimer = setTimeout(() => {
    reconnectTimer = null;
    if (refCount === 0) return;
    disconnect();
    connect();
  }, 2500);
}

function parseSseChunk(buffer, onEvent) {
  let rest = buffer;
  while (true) {
    const sep = rest.indexOf('\n\n');
    if (sep < 0) break;
    const block = rest.slice(0, sep);
    rest = rest.slice(sep + 2);
    for (const line of block.split('\n')) {
      if (!line.startsWith('data:')) continue;
      const payload = line.slice(5).trim();
      if (!payload || payload === '[DONE]') continue;
      try {
        const msg = JSON.parse(payload);
        if (msg?.type === 'error') continue;
        onEvent(msg);
      } catch (_) {}
    }
  }
  return rest;
}

/**
 * SSE via fetch + Authorization (sem ticket/token na URL).
 * EventSource não permite header Authorization — por isso usamos fetch.
 */
async function attachFetchSse(url, authToken, signal) {
  const res = await fetch(url, {
    method: 'GET',
    headers: {
      Accept: 'text/event-stream',
      Authorization: `Token ${authToken}`,
      'Cache-Control': 'no-cache',
    },
    signal,
    cache: 'no-store',
  });

  if (!res.ok || !res.body) {
    throw new Error(`SSE HTTP ${res.status}`);
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    buffer = parseSseChunk(buffer, dispatchVoiceCallEvent);
  }
}

async function connect() {
  if (abortCtrl || connecting) return;
  const authToken = localStorage.getItem('auth_token') || localStorage.getItem('token');
  if (!authToken) return;

  connecting = true;
  const ctrl = new AbortController();
  abortCtrl = ctrl;

  try {
    const url = buildVoiceCallEventsUrl();
    if (!url) {
      abortCtrl = null;
      return;
    }
    connecting = false;
    await attachFetchSse(url, authToken, ctrl.signal);
    // Stream terminou — reconectar se ainda houver assinantes
    if (abortCtrl === ctrl) abortCtrl = null;
    scheduleReconnect();
  } catch (err) {
    if (ctrl.signal.aborted) return;
    if (abortCtrl === ctrl) abortCtrl = null;
    scheduleReconnect();
  } finally {
    connecting = false;
  }
}

function disconnect() {
  if (reconnectTimer) {
    clearTimeout(reconnectTimer);
    reconnectTimer = null;
  }
  connecting = false;
  if (abortCtrl) {
    try {
      abortCtrl.abort();
    } catch (_) {}
    abortCtrl = null;
  }
}

/**
 * SSE de fallback + listener compartilhado com o WebSocket do painel.
 */
export function subscribeVoiceCallEvents(handler) {
  const remove = addVoiceCallListener(handler);
  refCount += 1;
  connect();
  return () => {
    remove();
    refCount = Math.max(0, refCount - 1);
    if (refCount === 0) disconnect();
  };
}
