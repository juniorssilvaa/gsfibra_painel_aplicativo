import { useSyncExternalStore } from 'react';
import { createPortal } from 'react-dom';
import AppNotifyCard from '../components/ui/AppNotifyCard';
import { friendlyApiError } from './apiError';
import '../styles/app-notify.css';

let toasts = [];
let listeners = new Set();
let nextId = 1;
const timersById = new Map();

function emit() {
  listeners.forEach((listener) => listener());
}

function normalizeMessage(message) {
  const text =
    typeof message === 'string'
      ? message
      : message?.message || message?.detail || '';
  return String(text || '').trim();
}

function clearTimer(id) {
  const timer = timersById.get(id);
  if (timer) {
    clearTimeout(timer);
    timersById.delete(id);
  }
}

function dismissToast(id) {
  if (id == null) return;
  clearTimer(id);
  toasts = toasts.filter((item) => item.id !== id);
  emit();
}

function pushToast(variant, message, options = {}) {
  const text = normalizeMessage(message);
  if (!text) return null;

  const existingId = options.id;
  if (existingId != null) {
    dismissToast(existingId);
  }

  // Evita empilhar vários alertas vermelhos (ex.: interceptor + catch da página).
  if (variant === 'error' && existingId == null) {
    const currentErrors = toasts.filter((item) => item.variant === 'error');
    for (const prev of currentErrors) {
      clearTimer(prev.id);
    }
    toasts = toasts.filter((item) => item.variant !== 'error');
  }

  const id = existingId != null ? existingId : nextId++;
  const duration =
    options.duration ??
    (variant === 'loading' ? null : variant === 'error' ? 7000 : 4500);

  toasts = [...toasts.filter((item) => item.id !== id), { id, variant, message: text }];
  emit();

  if (duration != null) {
    clearTimer(id);
    const timer = setTimeout(() => {
      timersById.delete(id);
      toasts = toasts.filter((item) => item.id !== id);
      emit();
    }, duration);
    timersById.set(id, timer);
  }

  return id;
}

function subscribe(listener) {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

function getSnapshot() {
  return toasts;
}

function showNotify(variant, message, options = {}) {
  return pushToast(variant, message, options);
}

export const notify = {
  success: (message, options) => showNotify('success', message, options),
  error: (message, options) => showNotify('error', message, options),
  info: (message, options) => showNotify('info', message, options),
  loading: (message, options) => showNotify('loading', message, options),
  dismiss: (id) => dismissToast(id),
  /** Vermelho — confirmação de exclusão/remoção bem-sucedida. */
  deleted: (message, options) => showNotify('error', message, options),
};

/** API unificada do painel — verde (success), vermelho (error/deleted), azul (info). */
export const toast = {
  success: (message, options) => notify.success(message, options),
  error: (message, options) => notify.error(message, options),
  info: (message, options) => notify.info(message, options),
  loading: (message, options) => notify.loading(message, options),
  dismiss: (id) => notify.dismiss(id),
  deleted: (message, options) => notify.deleted(message, options),
  apiError: (error, fallback, options) =>
    notify.error(friendlyApiError(error, fallback), options),
};

export { friendlyApiError };

export function showPanelToast(message, type = 'success', options = {}) {
  const text = normalizeMessage(message);
  if (!text) return;
  if (type === 'error' || type === 'deleted') notify.error(text, options);
  else if (type === 'info' || type === 'warning' || type === 'loading') notify.info(text, options);
  else notify.success(text, options);
}

export function AppToaster() {
  const items = useSyncExternalStore(subscribe, getSnapshot, getSnapshot);

  if (typeof document === 'undefined' || !items.length) return null;

  return createPortal(
    <div className="fixed top-5 right-5 z-[100000] flex flex-col items-end gap-2.5 pointer-events-none px-4 sm:px-0">
      {items.map((item) => (
        <div key={item.id} className="pointer-events-auto">
          <AppNotifyCard
            variant={item.variant === 'loading' ? 'info' : item.variant}
            message={item.message}
            onClose={() => dismissToast(item.id)}
          />
        </div>
      ))}
    </div>,
    document.body
  );
}
