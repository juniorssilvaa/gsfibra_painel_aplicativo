import { AlertCircle, Check, Info, X } from 'lucide-react';

const VARIANTS = {
  error: {
    shell: 'bg-red-600',
    iconWrap: 'bg-red-700/50',
    Icon: AlertCircle,
  },
  success: {
    shell: 'bg-emerald-600',
    iconWrap: 'bg-emerald-700/50',
    Icon: Check,
  },
  info: {
    shell: 'bg-sky-600',
    iconWrap: 'bg-sky-700/50',
    Icon: Info,
  },
};

export default function AppNotifyCard({ id, variant = 'error', message, onClose }) {
  const v = VARIANTS[variant] || VARIANTS.error;
  const { Icon } = v;

  const handleClose = () => {
    if (typeof onClose === 'function') {
      onClose();
    }
  };

  return (
    <div
      className={`flex w-[min(calc(100vw-2rem),420px)] items-center gap-3 rounded-md border-b-4 px-4 py-3 shadow-[0_8px_24px_rgba(0,0,0,0.35)] ${v.shell} ${
        variant === 'error'
          ? 'border-red-800'
          : variant === 'success'
            ? 'border-emerald-800'
            : 'border-sky-800'
      }`}
      role="alert"
    >
      <div className={`flex h-7 w-7 shrink-0 items-center justify-center rounded ${v.iconWrap}`}>
        <Icon className="h-4 w-4 text-white" strokeWidth={2.5} />
      </div>
      <p className="min-w-0 flex-1 text-sm font-semibold leading-snug text-white">
        {message}
      </p>
      <button
        type="button"
        onClick={handleClose}
        className="shrink-0 rounded p-1 text-white/80 transition-colors hover:bg-white/15 hover:text-white"
        aria-label="Fechar"
      >
        <X className="h-4 w-4" strokeWidth={2} />
      </button>
    </div>
  );
}
