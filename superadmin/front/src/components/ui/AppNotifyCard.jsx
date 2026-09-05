import { AlertCircle, Check, Info, X } from 'lucide-react'

const VARIANTS = {
  error: {
    shell: 'bg-red-600',
    iconWrap: 'bg-red-700/50',
    border: 'border-red-800',
    Icon: AlertCircle,
  },
  success: {
    shell: 'bg-emerald-600',
    iconWrap: 'bg-emerald-700/50',
    border: 'border-emerald-800',
    Icon: Check,
  },
  info: {
    shell: 'bg-sky-600',
    iconWrap: 'bg-sky-700/50',
    border: 'border-sky-800',
    Icon: Info,
  },
}

export default function AppNotifyCard({ variant = 'success', message, onClose }) {
  const v = VARIANTS[variant] || VARIANTS.success
  const { Icon } = v

  return (
    <div
      className={`flex w-[min(calc(100vw-2rem),420px)] items-center gap-3 rounded-md border-b-4 px-4 py-3 shadow-[0_8px_24px_rgba(0,0,0,0.35)] ${v.shell} ${v.border}`}
      role="alert"
    >
      <div className={`flex h-7 w-7 shrink-0 items-center justify-center rounded ${v.iconWrap}`}>
        <Icon className="h-4 w-4 text-white" strokeWidth={2.5} />
      </div>
      <p className="min-w-0 flex-1 text-sm font-semibold leading-snug text-white">{message}</p>
      <button
        type="button"
        onClick={() => onClose?.()}
        className="shrink-0 rounded p-1 text-white/80 transition-colors hover:bg-white/15 hover:text-white"
        aria-label="Fechar"
      >
        <X className="h-4 w-4" strokeWidth={2} />
      </button>
    </div>
  )
}
