import { Mic, MicOff, Phone, PhoneOff, X } from 'lucide-react';

export default function VoiceCallPanel({
  open,
  onClose,
  contactName,
  contactPhone,
  statusText,
  inCall,
  connecting = false,
  incoming,
  elapsed,
  muted,
  onStart,
  onAccept,
  onReject,
  onHangup,
  onToggleMute,
  canCall,
  unavailableReason,
  audioRef,
}) {
  // <audio> sempre montado para o srcObject / autoplay não se perderem.
  return (
    <>
      <audio
        ref={audioRef}
        autoPlay
        playsInline
        style={{
          position: 'fixed',
          width: 1,
          height: 1,
          opacity: 0,
          pointerEvents: 'none',
          left: 0,
          bottom: 0,
        }}
      />

      {!open ? null : (
    <div className="fixed bottom-24 right-6 z-[90] w-[min(100vw-2rem,300px)] overflow-hidden rounded-xl border border-border bg-card text-foreground shadow-2xl">
      <div className="flex items-center gap-2 border-b border-border px-3 py-2.5">
        <span className="h-2 w-2 shrink-0 rounded-full bg-green-500" />
        <span className="flex-1 text-sm font-semibold">
          {inCall && !connecting && elapsed && elapsed !== '00:00'
            ? 'Em chamada'
            : inCall || connecting
              ? 'Chamando…'
              : 'Iniciar ligação'}
        </span>
        <button
          type="button"
          onClick={onClose}
          className="rounded p-1 text-muted-foreground hover:bg-muted hover:text-foreground"
          aria-label="Fechar"
        >
          <X className="h-4 w-4" />
        </button>
      </div>

      <div className="px-4 py-5 text-center">
        <p className="truncate text-sm font-semibold">{contactName || contactPhone || 'Contato'}</p>
        {contactPhone && (
          <p className="mt-0.5 text-xs text-muted-foreground tabular-nums">{contactPhone}</p>
        )}

        {!canCall && !inCall && !incoming && (
          <p className="mt-4 text-xs text-muted-foreground leading-relaxed">
            {unavailableReason || 'Ligações não disponíveis nesta conversa.'}
          </p>
        )}

        {(inCall || incoming || connecting) && (
          <p className="mt-3 min-h-[16px] text-xs font-medium text-muted-foreground tabular-nums">
            {inCall && !connecting && elapsed && elapsed !== '00:00' ? elapsed : statusText}
          </p>
        )}

        {!inCall && !incoming && canCall && (
          <button
            type="button"
            onClick={onStart}
            className="mt-5 inline-flex h-14 w-14 items-center justify-center rounded-full bg-green-600 text-white shadow-lg hover:bg-green-500"
            title="Ligar"
          >
            <Phone className="h-6 w-6" />
          </button>
        )}

        {incoming && !inCall && (
          <div className="mt-5 flex justify-center gap-4">
            <button
              type="button"
              onClick={onAccept}
              className="inline-flex h-12 w-12 items-center justify-center rounded-full bg-green-600 text-white hover:bg-green-500"
              title="Atender"
            >
              <Phone className="h-5 w-5" />
            </button>
            <button
              type="button"
              onClick={onReject}
              className="inline-flex h-12 w-12 items-center justify-center rounded-full bg-red-600 text-white hover:bg-red-500"
              title="Recusar"
            >
              <PhoneOff className="h-5 w-5" />
            </button>
          </div>
        )}

        {inCall && (
          <div className="mt-5 flex justify-center gap-4">
            <button
              type="button"
              onClick={onToggleMute}
              className={`inline-flex h-11 w-11 items-center justify-center rounded-full border ${
                muted ? 'border-red-500 bg-red-500 text-white' : 'border-border bg-muted text-foreground'
              }`}
              title={muted ? 'Ativar microfone' : 'Mudo'}
            >
              {muted ? <MicOff className="h-5 w-5" /> : <Mic className="h-5 w-5" />}
            </button>
            <button
              type="button"
              onClick={onHangup}
              className="inline-flex h-12 w-12 items-center justify-center rounded-full bg-red-600 text-white hover:bg-red-500"
              title="Encerrar"
            >
              <PhoneOff className="h-5 w-5" />
            </button>
          </div>
        )}

        {statusText && !inCall && !incoming && (
          <p className="mt-3 text-xs text-amber-600 dark:text-amber-400">{statusText}</p>
        )}
      </div>
    </div>
      )}
    </>
  );
}
