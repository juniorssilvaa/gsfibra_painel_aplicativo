import { useEffect, useRef, useState } from 'react';
import { GripHorizontal, Mic, MicOff, Phone, PhoneOff, PhoneIncoming, X } from 'lucide-react';
import { attachMeter, dbToLevel } from '../utils/audioMeter';

const CARD_MARGIN = 8;

function CompactCallCard({
  contactName,
  contactPhone,
  elapsed,
  statusText,
  connecting,
  muted,
  onHangup,
  onToggleMute,
  audioRef,
}) {
  const cardRef = useRef(null);
  const pulseRef = useRef(null);
  const iconWrapRef = useRef(null);
  const [position, setPosition] = useState(null);
  const dragRef = useRef({
    active: false,
    startX: 0,
    startY: 0,
    originX: 0,
    originY: 0,
  });

  // Pulsa o ícone verde ao ritmo do áudio recebido do cliente (feedback visual de "está chegando som").
  // O <audio> do card recebe o srcObject de forma imperativa (fora do React), então observamos
  // por polling até o stream aparecer/trocar, em vez de depender de um evento/estado.
  useEffect(() => {
    let stopMeter = null;
    let lastStream = null;
    let cancelled = false;

    const applyLevel = (db) => {
      const level = dbToLevel(db);
      if (pulseRef.current) {
        pulseRef.current.style.opacity = String(level * 0.55);
        pulseRef.current.style.transform = `scale(${1 + level * 0.75})`;
      }
      if (iconWrapRef.current) {
        iconWrapRef.current.style.transform = `scale(${1 + level * 0.12})`;
      }
    };

    const poll = setInterval(() => {
      if (cancelled) return;
      const stream = audioRef?.current?.srcObject || null;
      if (stream && stream !== lastStream) {
        lastStream = stream;
        if (stopMeter) stopMeter();
        stopMeter = attachMeter(stream, applyLevel);
      } else if (!stream && lastStream) {
        lastStream = null;
        if (stopMeter) {
          stopMeter();
          stopMeter = null;
        }
        applyLevel(-60);
      }
    }, 250);

    return () => {
      cancelled = true;
      clearInterval(poll);
      if (stopMeter) stopMeter();
    };
  }, [audioRef]);

  const getCardSize = () => {
    const el = cardRef.current;
    if (el) {
      const rect = el.getBoundingClientRect();
      return { width: rect.width, height: rect.height };
    }
    return { width: 320, height: 64 };
  };

  const clampPosition = (x, y) => {
    const { width, height } = getCardSize();
    return {
      x: Math.min(Math.max(CARD_MARGIN, x), window.innerWidth - width - CARD_MARGIN),
      y: Math.min(Math.max(CARD_MARGIN, y), window.innerHeight - height - CARD_MARGIN),
    };
  };

  const getDefaultPosition = () => {
    const { width, height } = getCardSize();
    return clampPosition(window.innerWidth - width - 16, window.innerHeight - height - 16);
  };

  const endDrag = () => {
    if (!dragRef.current.active) return;
    dragRef.current.active = false;
    document.body.style.userSelect = '';
    document.body.style.cursor = '';
  };

  const handlePointerDown = (e) => {
    if (e.button !== 0) return;
    if (e.target.closest('button')) return;
    e.preventDefault();
    const current = position || getDefaultPosition();
    if (!position) setPosition(current);
    dragRef.current = {
      active: true,
      startX: e.clientX,
      startY: e.clientY,
      originX: current.x,
      originY: current.y,
    };
    document.body.style.userSelect = 'none';
    document.body.style.cursor = 'grabbing';
  };

  useEffect(() => {
    const frame = requestAnimationFrame(() => setPosition(getDefaultPosition()));
    return () => cancelAnimationFrame(frame);
  }, []);

  useEffect(() => {
    const onPointerMove = (e) => {
      if (!dragRef.current.active) return;
      const dx = e.clientX - dragRef.current.startX;
      const dy = e.clientY - dragRef.current.startY;
      setPosition(
        clampPosition(dragRef.current.originX + dx, dragRef.current.originY + dy)
      );
    };
    window.addEventListener('pointermove', onPointerMove);
    window.addEventListener('pointerup', endDrag);
    window.addEventListener('pointercancel', endDrag);
    return () => {
      window.removeEventListener('pointermove', onPointerMove);
      window.removeEventListener('pointerup', endDrag);
      window.removeEventListener('pointercancel', endDrag);
      document.body.style.userSelect = '';
      document.body.style.cursor = '';
    };
  }, []);

  useEffect(() => {
    if (!position) return undefined;
    const onResize = () => {
      setPosition((pos) => (pos ? clampPosition(pos.x, pos.y) : pos));
    };
    window.addEventListener('resize', onResize);
    return () => window.removeEventListener('resize', onResize);
  }, [position]);

  const cardStyle = position
    ? { left: position.x, top: position.y }
    : { right: 16, bottom: 16 };

  return (
    <>
      <div
        ref={cardRef}
        style={cardStyle}
        className="fixed z-[201] flex w-[min(100vw-2rem,320px)] cursor-grab items-center gap-2 rounded-xl border border-border bg-card px-3 py-3 text-foreground shadow-2xl active:cursor-grabbing"
        role="dialog"
        aria-label="Chamada em andamento"
        onPointerDown={handlePointerDown}
      >
        <GripHorizontal className="h-4 w-4 shrink-0 text-muted-foreground/60" aria-hidden />

        <div className="relative flex h-10 w-10 shrink-0 items-center justify-center">
          <span
            ref={pulseRef}
            className="pointer-events-none absolute inset-0 rounded-full bg-[#00E676] opacity-0 will-change-transform"
            aria-hidden
          />
          <div
            ref={iconWrapRef}
            className="relative flex h-10 w-10 items-center justify-center rounded-full bg-[#00C853] will-change-transform"
          >
            <svg viewBox="0 0 24 24" className="h-5 w-5" fill="#FFFFFF" aria-hidden>
              <path d="M6.62 10.79a15.15 15.15 0 006.59 6.59l2.2-2.2a1 1 0 011.01-.24c1.12.37 2.33.57 3.58.57a1 1 0 011 1V20a1 1 0 01-1 1C10.4 21 3 13.6 3 4a1 1 0 011-1h3.5a1 1 0 011 1c0 1.25.2 2.46.57 3.58a1 1 0 01-.25 1.02l-2.2 2.19z" />
            </svg>
          </div>
        </div>

        <div className="min-w-0 flex-1 select-none">
          <p className="truncate text-sm font-semibold">{contactName || 'Cliente WhatsApp'}</p>
          <p className="text-xs tabular-nums text-muted-foreground">
            {connecting && statusText
              ? statusText
              : `${elapsed}${contactPhone ? ` · ${contactPhone}` : ''}`}
          </p>
        </div>

        <div className="flex shrink-0 items-center gap-2" onPointerDown={(e) => e.stopPropagation()}>
          <button
            type="button"
            onClick={onToggleMute}
            className={`inline-flex h-9 w-9 items-center justify-center rounded-full border ${
              muted ? 'border-red-500 bg-red-500 text-white' : 'border-border bg-muted text-foreground'
            }`}
            title={muted ? 'Ativar microfone' : 'Mudo'}
          >
            {muted ? <MicOff className="h-4 w-4" /> : <Mic className="h-4 w-4" />}
          </button>
          <button
            type="button"
            onClick={onHangup}
            className="inline-flex h-10 w-10 items-center justify-center rounded-full bg-red-600 text-white shadow hover:bg-red-500"
            title="Encerrar"
          >
            <PhoneOff className="h-5 w-5" />
          </button>
        </div>
      </div>
    </>
  );
}

export default function IncomingCallPopup({
  open,
  contactName,
  contactPhone,
  statusText,
  inCall,
  connecting,
  incoming,
  elapsed,
  muted,
  onAccept,
  onReject,
  onHangup,
  onToggleMute,
  onStart,
  canStart,
  onDismiss,
  audioRef,
}) {
  const ringing = Boolean(incoming) && !inCall && !connecting;
  const outboundActive = !incoming && inCall;
  const hasStatusMessage = Boolean(statusText) && statusText !== 'Conectando…' && statusText !== 'Chamando…';
  const outboundIdle =
    !incoming && !inCall && !connecting && typeof onStart === 'function' && !hasStatusMessage;
  // Enquanto conecta (após atender), usa o card compacto — evita modal "Chamada recebida" residual.
  const compact =
    outboundActive || (inCall && !connecting) || (connecting && !incoming && !outboundIdle);
  const showBackdrop = ringing || (connecting && Boolean(incoming));
  const canDismiss =
    typeof onDismiss === 'function' && !inCall && !ringing && !connecting;

  // <audio> SEMPRE montado (mesmo com open=false). Se ficar dentro de `if (!open) return null`,
  // o srcObject some e o autoplay não desbloqueia no clique de atender.
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

      {!open ? null : compact ? (
        <CompactCallCard
          contactName={contactName}
          contactPhone={contactPhone}
          elapsed={elapsed}
          statusText={statusText}
          connecting={connecting}
          muted={muted}
          onHangup={onHangup}
          onToggleMute={onToggleMute}
          audioRef={audioRef}
        />
      ) : (
        <>
          {showBackdrop ? (
            <div className="fixed inset-0 z-[200] bg-black/50 backdrop-blur-[2px]" aria-hidden />
          ) : null}

          <div
            className={`fixed z-[201] overflow-hidden rounded-2xl border border-border bg-card text-foreground shadow-2xl ${
              showBackdrop
                ? 'left-1/2 top-1/2 w-[min(100vw-2rem,380px)] -translate-x-1/2 -translate-y-1/2'
                : 'bottom-4 right-4 w-[min(100vw-2rem,320px)]'
            }`}
            role="dialog"
            aria-modal={showBackdrop ? 'true' : undefined}
            aria-label={ringing ? 'Chamada recebida' : 'Ligação'}
          >
        {canDismiss ? (
          <button
            type="button"
            onClick={onDismiss}
            className="absolute right-3 top-3 z-10 inline-flex h-8 w-8 items-center justify-center rounded-full text-muted-foreground hover:bg-muted hover:text-foreground"
            aria-label="Fechar"
            title="Fechar"
          >
            <X className="h-4 w-4" />
          </button>
        ) : null}

        <div
          className={`px-6 pt-8 pb-6 text-center ${
            ringing ? 'animate-[pulse_2s_ease-in-out_infinite]' : ''
          }`}
        >
          <div
            className={`mx-auto mb-4 flex h-16 w-16 items-center justify-center rounded-full ${
              ringing ? 'bg-[#00C853]' : 'bg-muted text-muted-foreground'
            }`}
          >
            {ringing ? (
              <svg
                viewBox="0 0 24 24"
                className="h-8 w-8 animate-bounce"
                fill="#FFFFFF"
                aria-hidden
              >
                <path d="M6.62 10.79a15.15 15.15 0 006.59 6.59l2.2-2.2a1 1 0 011.01-.24c1.12.37 2.33.57 3.58.57a1 1 0 011 1V20a1 1 0 01-1 1C10.4 21 3 13.6 3 4a1 1 0 011-1h3.5a1 1 0 011 1c0 1.25.2 2.46.57 3.58a1 1 0 01-.25 1.02l-2.2 2.19z" />
              </svg>
            ) : (
              <PhoneIncoming className="h-8 w-8" />
            )}
          </div>

          {ringing ? (
            <p className="text-xs font-semibold uppercase tracking-wide text-[#00C853]">
              Recebendo chamada
            </p>
          ) : (
            <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
              {connecting ? 'Conectando…' : inCall ? 'Em chamada' : 'Ligação'}
            </p>
          )}
          <p className="mt-2 truncate text-lg font-semibold">
            {contactName || contactPhone || 'Cliente WhatsApp'}
          </p>
          {contactPhone && contactName && contactName !== contactPhone ? (
            <p className="mt-1 text-sm text-muted-foreground tabular-nums">{contactPhone}</p>
          ) : null}

          <p className="mt-4 min-h-[20px] text-sm font-medium text-muted-foreground tabular-nums">
            {inCall ? elapsed : connecting && !ringing ? statusText : null}
          </p>

          {ringing && (
            <div className="mt-8 flex justify-center gap-6">
              <button
                type="button"
                onClick={onAccept}
                className="inline-flex h-14 w-14 items-center justify-center rounded-full bg-green-600 text-white shadow-lg ring-4 ring-green-600/25 hover:bg-green-500"
                title="Atender"
              >
                <Phone className="h-6 w-6" />
              </button>
              <button
                type="button"
                onClick={onReject}
                className="inline-flex h-14 w-14 items-center justify-center rounded-full bg-red-600 text-white shadow-lg ring-4 ring-red-600/25 hover:bg-red-500"
                title="Recusar"
              >
                <PhoneOff className="h-6 w-6" />
              </button>
            </div>
          )}

          {(inCall || connecting) && !compact && (
            <div className="mt-8 flex justify-center gap-5">
              <button
                type="button"
                onClick={onToggleMute}
                disabled={connecting}
                className={`inline-flex h-12 w-12 items-center justify-center rounded-full border disabled:opacity-50 ${
                  muted ? 'border-red-500 bg-red-500 text-white' : 'border-border bg-muted text-foreground'
                }`}
                title={muted ? 'Ativar microfone' : 'Mudo'}
              >
                {muted ? <MicOff className="h-5 w-5" /> : <Mic className="h-5 w-5" />}
              </button>
              <button
                type="button"
                onClick={onHangup}
                className="inline-flex h-14 w-14 items-center justify-center rounded-full bg-red-600 text-white shadow-lg hover:bg-red-500"
                title="Encerrar"
              >
                <PhoneOff className="h-6 w-6" />
              </button>
            </div>
          )}

          {outboundIdle && canStart && (
            <button
              type="button"
              onClick={onStart}
              className="mt-8 inline-flex h-14 w-14 items-center justify-center rounded-full bg-green-600 text-white shadow-lg ring-4 ring-green-600/25 hover:bg-green-500"
              title="Ligar"
            >
              <Phone className="h-6 w-6" />
            </button>
          )}

          {!inCall && !ringing && !connecting && statusText && (
            <p className="mt-6 text-sm leading-relaxed text-amber-600 dark:text-amber-400">{statusText}</p>
          )}
        </div>
      </div>
        </>
      )}
    </>
  );
}
