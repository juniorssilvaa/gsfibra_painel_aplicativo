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

function scrubSuperadminCopy(text) {
  return String(text || '')
    .replace(/\s+no\s+Superadmin/gi, '')
    .replace(/\s+do\s+Superadmin/gi, '')
    .replace(/\s+pelo\s+Superadmin/gi, '')
    .replace(/\bau\s+Superadmin\b/gi, 'ao painel')
    .replace(/\bSuperadmins?\b/gi, 'painel')
    .replace(/\ssuperadmin\b/gi, 'painel')
    .replace(/  +/g, ' ')
    .trim()
}

function normalizeMessage(message) {
  const text =
    typeof message === 'string' ? message : message?.message || message?.detail || ''
  return scrubSuperadminCopy(String(text || '').trim())
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

  const fromInterPayload = (payload) => {
    if (!payload || typeof payload !== 'object') return ''
    const violacoes = payload.violacoes || payload.violations
    if (Array.isArray(violacoes) && violacoes.length) {
      const razoes = violacoes
        .map((v) => (v && typeof v === 'object' ? String(v.razao || v.message || '').trim() : ''))
        .filter(Boolean)
      if (razoes.length) return razoes.join(' | ')
    }
    return String(payload.detail || payload.title || payload.message || payload.error || '').trim()
  }

  const parseMaybeJson = (raw) => {
    const text = String(raw || '').trim()
    if (!text) return ''
    const human = fromInterPayload(text.startsWith('{') ? (() => {
      try { return JSON.parse(text) } catch { return null }
    })() : null)
    if (human) return human
    const start = text.indexOf('{')
    if (start >= 0) {
      try {
        const parsed = JSON.parse(text.slice(start))
        const nested = fromInterPayload(parsed)
        if (nested) return nested
      } catch {
        /* ignore */
      }
    }
    return text
  }

  let raw = fallback
  if (typeof data === 'string' && data.trim()) raw = parseMaybeJson(data)
  else if (data && typeof data === 'object') {
    const interMsg = fromInterPayload(data)
    if (interMsg) raw = interMsg
    else if (data.error) raw = parseMaybeJson(data.error)
    else if (data.detail) raw = parseMaybeJson(data.detail)
    else if (data.message) raw = parseMaybeJson(data.message)
  } else if (error?.message) raw = parseMaybeJson(error.message)
  return scrubSuperadminCopy(raw)
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
