import { useCallback, useEffect, useRef, useState } from 'react';
import axios from 'axios';
import { AlertTriangle, Loader2, Settings } from 'lucide-react';

const POLL_OK_MS = 15000;
const POLL_MAINTENANCE_MS = 5000;
// Backend respondendo 502/503/504 seguidamente por esse tempo: mostra o erro real (não é atualização).
// Oscilação curta de rede/servidor não gera aviso.
const FAILURES_TO_REPORT = 3;
const FAILURE_WINDOW_MS = 20000;
const GATEWAY_STATUS_TEXT = { 502: 'Bad Gateway', 503: 'Service Unavailable', 504: 'Gateway Timeout' };
const SKIP_FLAG = '__maintenanceProbe';
// Se o frontend continuar com o mesmo build (atualização só de backend), recarrega após esse tempo
const SAME_BUILD_GRACE_MS = 60000;
const RESUME_MAX_AGE_MS = 15 * 60 * 1000;

const RESUME_KEY = 'niohub:resume-after-update';
export const RESUME_DRAFT_KEY = 'niohub:resume-draft';
export const BEFORE_UPDATE_RELOAD_EVENT = 'niohub:before-update-reload';

const isGatewayFailure = (error) => {
  if (axios.isCancel?.(error) || error?.code === 'ERR_CANCELED') return false;
  // Sem resposta (timeout, Wi-Fi oscilando, PC saindo da suspensão) é rede do cliente, não deploy:
  // durante a atualização o proxy responde 502/503/504.
  const status = error?.response?.status;
  return status === 502 || status === 503 || status === 504;
};

const ENTRY_SCRIPT_RE = /<script[^>]*type="module"[^>]*src="([^"]+)"/i;

const loadedEntryScript = () =>
  document.querySelector('script[type="module"][src*="/assets/"]')?.getAttribute('src') || null;

const fetchFrontEntry = async () => {
  try {
    const res = await fetch(`/?_=${Date.now()}`, { cache: 'no-store', credentials: 'same-origin' });
    if (!res.ok) return { ok: false };
    const html = await res.text();
    if (!html.includes('id="root"')) return { ok: false };
    return { ok: true, entry: html.match(ENTRY_SCRIPT_RE)?.[1] || null };
  } catch {
    return { ok: false };
  }
};

const readJson = (storage, key) => {
  try {
    const raw = storage.getItem(key);
    return raw ? JSON.parse(raw) : null;
  } catch {
    return null;
  }
};

/** Conversa aberta antes do reload pós-atualização (uso único). */
export const consumeResumeAfterUpdate = () => {
  const saved = readJson(sessionStorage, RESUME_KEY);
  sessionStorage.removeItem(RESUME_KEY);
  if (!saved || Date.now() - (saved.ts || 0) > RESUME_MAX_AGE_MS) return null;
  return saved;
};

/** Rascunho digitado na conversa antes do reload pós-atualização (uso único). */
export const consumeResumeDraft = (conversationId) => {
  const saved = readJson(sessionStorage, RESUME_DRAFT_KEY);
  if (!saved) return null;
  const stale = Date.now() - (saved.ts || 0) > RESUME_MAX_AGE_MS;
  if (stale || String(saved.conversationId) === String(conversationId)) {
    sessionStorage.removeItem(RESUME_DRAFT_KEY);
  }
  return !stale && String(saved.conversationId) === String(conversationId) ? saved.text : null;
};

const reloadPreservingState = () => {
  window.dispatchEvent(new Event(BEFORE_UPDATE_RELOAD_EVENT));
  try {
    const conversation = readJson(localStorage, 'selectedConversation');
    sessionStorage.setItem(RESUME_KEY, JSON.stringify({ ts: Date.now(), conversationId: conversation?.id ?? null }));
  } catch {
    // sessionStorage indisponível: recarrega sem restaurar a conversa
  }
  window.location.reload();
};

// Chunks do build anterior somem quando o frontend novo entra no ar (o servidor devolve index.html)
const STALE_CHUNK_RE = /Failed to fetch dynamically imported module|Importing a module script failed|error loading dynamically imported module|Unable to preload CSS|ChunkLoadError|Loading (CSS )?chunk \S+ failed|not a valid JavaScript MIME type/i;
const STALE_RELOAD_KEY = 'niohub:stale-build-reload-at';
// Se o mesmo erro voltar logo após o reload, não é troca de build: deixa o erro aparecer (sem loop)
const STALE_RELOAD_COOLDOWN_MS = 2 * 60 * 1000;
let staleBuildRecovering = false;

export const isStaleChunkError = (error) => STALE_CHUNK_RE.test(String(error?.message || error || ''));

/** Recarrega (preservando a conversa) quando o frontend novo responder. false = já tentou há pouco. */
export const recoverFromStaleBuild = () => {
  if (staleBuildRecovering) return true;
  const last = Number(sessionStorage.getItem(STALE_RELOAD_KEY) || 0);
  if (Date.now() - last < STALE_RELOAD_COOLDOWN_MS) return false;
  staleBuildRecovering = true;
  const attempt = async () => {
    const front = await fetchFrontEntry();
    if (!front.ok) {
      window.setTimeout(attempt, POLL_MAINTENANCE_MS);
      return;
    }
    try {
      sessionStorage.setItem(STALE_RELOAD_KEY, String(Date.now()));
    } catch {
      // sem sessionStorage não há proteção contra loop; o cooldown do próximo erro não se aplica
    }
    reloadPreservingState();
  };
  void attempt();
  return true;
};

export function MaintenanceScreen() {
  return (
    <div
      className="fixed inset-0 z-[2147483000] flex items-center justify-center bg-[#F5F6F8] px-6"
      role="alertdialog"
      aria-live="assertive"
      aria-label="Sistema em atualização"
    >
      <div className="max-w-md text-center">
        <Settings
          className="mx-auto mb-10 h-10 w-10 text-[#1A73E8] animate-[spin_6s_linear_infinite]"
          strokeWidth={2.2}
        />
        <h1 className="text-[28px] font-bold leading-tight text-[#1F2328]">
          Estamos preparando algumas melhorias!
        </h1>
        <p className="mt-4 text-[15px] leading-relaxed text-[#57606A]">
          Nosso sistema está recebendo uma atualização para ficar ainda melhor para você. Voltaremos em instantes.
        </p>
        <p className="mt-8 text-xs text-[#8C959F]">
          Esta página será recarregada automaticamente.
        </p>
      </div>
    </div>
  );
}

/** Troca de build detectada (arquivos da versão anterior sumiram): só recarrega. */
export function ReloadingScreen() {
  return (
    <div
      className="fixed inset-0 z-[2147483000] flex items-center justify-center bg-[#F5F6F8] px-6"
      role="status"
      aria-live="polite"
      aria-label="Recarregando o sistema"
    >
      <div className="max-w-md text-center">
        <Loader2 className="mx-auto mb-6 h-8 w-8 text-[#1A73E8] animate-spin" strokeWidth={2.2} />
        <p className="text-[15px] leading-relaxed text-[#57606A]">Recarregando o sistema…</p>
      </div>
    </div>
  );
}

function ServerErrorBanner({ status }) {
  const statusText = GATEWAY_STATUS_TEXT[status] || '';
  return (
    <div
      className="fixed inset-x-0 top-0 z-[2147482000] flex items-center justify-center gap-2 bg-red-600 px-4 py-2 text-center text-sm font-medium text-white shadow"
      role="alert"
      aria-live="assertive"
    >
      <AlertTriangle className="h-4 w-4 flex-shrink-0" />
      <span>
        Servidor indisponível no momento (erro {status}{statusText ? ` – ${statusText}` : ''}).
        Tentando reconectar automaticamente…
      </span>
    </div>
  );
}

export default function MaintenanceGate() {
  // Tela de atualização: só com manutenção ligada pelo Superadmin (/api/health/ → maintenance.active)
  const [active, setActive] = useState(false);
  const [serverErrorStatus, setServerErrorStatus] = useState(null);
  const activeRef = useRef(false);
  const failuresRef = useRef(0);
  const firstFailureAtRef = useRef(0);
  const checkingRef = useRef(false);
  const timerRef = useRef(null);
  const sameBuildSinceRef = useRef(null);

  const enter = useCallback(() => {
    if (!activeRef.current) sameBuildSinceRef.current = null;
    activeRef.current = true;
    setActive(true);
  }, []);

  // Só recarrega quando o frontend responde (evita cair no "Bad Gateway" do proxy) e, se possível,
  // já com o build novo, para o atendente voltar com as correções aplicadas.
  const resumeWhenFrontReady = useCallback(async () => {
    const front = await fetchFrontEntry();
    if (!front.ok) return;
    const loaded = loadedEntryScript();
    const isNewBuild = !loaded || !front.entry || front.entry !== loaded;
    if (!isNewBuild) {
      if (!sameBuildSinceRef.current) sameBuildSinceRef.current = Date.now();
      if (Date.now() - sameBuildSinceRef.current < SAME_BUILD_GRACE_MS) return;
    }
    reloadPreservingState();
  }, []);

  const check = useCallback(async () => {
    if (checkingRef.current) return;
    checkingRef.current = true;
    try {
      const res = await axios.get('/api/health/', {
        timeout: 6000,
        params: { _: Date.now() },
        [SKIP_FLAG]: true,
      });
      failuresRef.current = 0;
      firstFailureAtRef.current = 0;
      setServerErrorStatus(null);
      if (res.data?.maintenance?.active) {
        enter();
      } else if (activeRef.current) {
        await resumeWhenFrontReady();
      }
    } catch (error) {
      if (typeof navigator !== 'undefined' && navigator.onLine === false) return;
      if (!isGatewayFailure(error)) return;
      failuresRef.current += 1;
      if (failuresRef.current === 1) firstFailureAtRef.current = Date.now();
      if (
        failuresRef.current >= FAILURES_TO_REPORT
        && Date.now() - firstFailureAtRef.current >= FAILURE_WINDOW_MS
      ) {
        setServerErrorStatus(error.response.status);
      }
    } finally {
      checkingRef.current = false;
    }
  }, [enter, resumeWhenFrontReady]);

  useEffect(() => {
    let cancelled = false;
    const schedule = () => {
      window.clearTimeout(timerRef.current);
      timerRef.current = window.setTimeout(async () => {
        if (cancelled) return;
        await check();
        if (!cancelled) schedule();
      }, activeRef.current || failuresRef.current > 0 ? POLL_MAINTENANCE_MS : POLL_OK_MS);
    };

    void check().then(() => { if (!cancelled) schedule(); });

    let probeScheduled = false;
    const interceptor = axios.interceptors.response.use(
      (response) => response,
      (error) => {
        if (!error?.config?.[SKIP_FLAG] && isGatewayFailure(error) && !probeScheduled) {
          probeScheduled = true;
          window.setTimeout(() => {
            probeScheduled = false;
            void check();
          }, 1500);
        }
        return Promise.reject(error);
      }
    );

    const onPreloadError = () => {
      recoverFromStaleBuild();
    };
    window.addEventListener('vite:preloadError', onPreloadError);

    return () => {
      cancelled = true;
      window.clearTimeout(timerRef.current);
      axios.interceptors.response.eject(interceptor);
      window.removeEventListener('vite:preloadError', onPreloadError);
    };
  }, [check]);

  if (active) return <MaintenanceScreen />;
  if (serverErrorStatus) return <ServerErrorBanner status={serverErrorStatus} />;
  return null;
}
