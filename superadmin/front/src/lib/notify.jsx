import { useSyncExternalStore } from 'react'
import { createPortal } from 'react-dom'
import AppNotifyCard from '../components/ui/AppNotifyCard'

let toasts = []
let listeners = new Set()
let nextId = 1
const timersById = new Map()

function emit() {
  listeners.forEach((listener) => listener())
}

function normalizeMessage(message) {
  const text =
    typeof message === 'string' ? message : message?.message || message?.detail || ''
  return String(text || '').trim()
}

function clearTimer(id) {
  const timer = timersById.get(id)
  if (timer) {
    clearTimeout(timer)
    timersById.delete(id)
  }
}

function dismissToast(id) {
  if (id == null) return
  clearTimer(id)
  toasts = toasts.filter((item) => item.id !== id)
  emit()
}

function pushToast(variant, message, options = {}) {
  const text = normalizeMessage(message)
  if (!text) return null

  const existingId = options.id
  if (existingId != null) dismissToast(existingId)

  if (variant === 'error' && existingId == null) {
    for (const prev of toasts.filter((item) => item.variant === 'error')) {
      clearTimer(prev.id)
    }
    toasts = toasts.filter((item) => item.variant !== 'error')
  }

  const id = existingId != null ? existingId : nextId++
  const duration =
    options.duration ?? (variant === 'loading' ? null : variant === 'error' ? 7000 : 4500)

  toasts = [...toasts.filter((item) => item.id !== id), { id, variant, message: text }]
  emit()

  if (duration != null) {
    clearTimer(id)
    const timer = setTimeout(() => {
      timersById.delete(id)
      toasts = toasts.filter((item) => item.id !== id)
      emit()
    }, duration)
    timersById.set(id, timer)
  }

  return id
}

function subscribe(listener) {
  listeners.add(listener)
  return () => listeners.delete(listener)
}

function getSnapshot() {
  return toasts
}

export function friendlyApiError(error, fallback = 'Erro') {
  const data = error?.response?.data
  if (typeof data === 'string' && data.trim()) return data.trim()
  if (data?.error) return String(data.error)
  if (data?.detail) return String(data.detail)
  if (data?.message) return String(data.message)
  if (error?.message) return String(error.message)
  return fallback
}

export const toast = {
  success: (message, options) => pushToast('success', message, options),
  error: (message, options) => pushToast('error', message, options),
  info: (message, options) => pushToast('info', message, options),
  loading: (message, options) => pushToast('info', message, options),
  dismiss: (id) => dismissToast(id),
  /** Exclusão concluída — mesmo estilo vermelho do painel de atendimento. */
  deleted: (message, options) => pushToast('error', message, options),
  apiError: (error, fallback, options) =>
    pushToast('error', friendlyApiError(error, fallback), options),
}

export function AppToaster() {
  const items = useSyncExternalStore(subscribe, getSnapshot, getSnapshot)

  if (typeof document === 'undefined' || !items.length) return null

  return createPortal(
    <div className="pointer-events-none fixed top-5 right-5 z-[100000] flex flex-col items-end gap-2.5 px-4 sm:px-0">
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
    document.body,
  )
}
