import { useCallback, useEffect, useRef, useState } from 'react';
import axios from 'axios';
import { Settings } from 'lucide-react';

const POLL_OK_MS = 15000;
const POLL_MAINTENANCE_MS = 5000;
// Falhas seguidas do backend (502/503/504/sem resposta) antes de assumir atualização em andamento
const FAILURES_TO_ENTER = 2;
const SKIP_FLAG = '__maintenanceProbe';

const isGatewayFailure = (error) => {
  if (axios.isCancel?.(error) || error?.code === 'ERR_CANCELED') return false;
  const status = error?.response?.status;
  if (status) return status === 502 || status === 503 || status === 504;
  return true;
};

export default function MaintenanceGate() {
  const [active, setActive] = useState(false);
  const activeRef = useRef(false);
  const failuresRef = useRef(0);
  const checkingRef = useRef(false);
  const timerRef = useRef(null);

  const enter = useCallback(() => {
    activeRef.current = true;
    setActive(true);
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
      if (res.data?.maintenance?.active) {
        enter();
      } else if (activeRef.current) {
        window.location.reload();
      }
    } catch (error) {
      if (typeof navigator !== 'undefined' && navigator.onLine === false) return;
      if (!isGatewayFailure(error)) return;
      failuresRef.current += 1;
      if (failuresRef.current >= FAILURES_TO_ENTER) enter();
    } finally {
      checkingRef.current = false;
    }
  }, [enter]);

  useEffect(() => {
    let cancelled = false;
    const schedule = () => {
      window.clearTimeout(timerRef.current);
      timerRef.current = window.setTimeout(async () => {
        if (cancelled) return;
        await check();
        if (!cancelled) schedule();
      }, activeRef.current ? POLL_MAINTENANCE_MS : POLL_OK_MS);
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

    return () => {
      cancelled = true;
      window.clearTimeout(timerRef.current);
      axios.interceptors.response.eject(interceptor);
    };
  }, [check]);

  if (!active) return null;

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
