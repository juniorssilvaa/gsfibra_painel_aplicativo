import { useEffect, useRef, useCallback } from 'react';
import { toast } from '../lib/notify';
import axios from 'axios';

const SESSION_TIMEOUT_EVENT = 'niochat:session-timeout-changed';
const DEFAULT_TIMEOUT_MINUTES = 30;

/** Valores do seletor em Perfil → Segurança (minutos). */
export const SESSION_TIMEOUT_OPTIONS = [
  { value: 1, label: '1 minuto' },
  { value: 2, label: '2 minutos' },
  { value: 15, label: '15 minutos' },
  { value: 30, label: '30 minutos' },
  { value: 60, label: '1 hora' },
  { value: 120, label: '2 horas' },
  { value: 180, label: '3 horas' },
  { value: 240, label: '4 horas' },
];

let sharedTimeoutMinutes = DEFAULT_TIMEOUT_MINUTES;

function readTimeoutFromStorage() {
  try {
    const savedUser = JSON.parse(localStorage.getItem('user') || 'null');
    const n = Number(savedUser?.session_timeout);
    if (Number.isFinite(n) && n > 0) return n;
  } catch {
    /* ignore */
  }
  return null;
}

/**
 * Aplica o timeout em todas as instâncias do hook (App + Perfil).
 * Chamar após salvar em Perfil → Segurança.
 */
export function applySessionTimeout(minutes) {
  const n = Number(minutes);
  if (!Number.isFinite(n) || n <= 0) return;
  sharedTimeoutMinutes = n;
  try {
    const savedUser = JSON.parse(localStorage.getItem('user') || '{}');
    savedUser.session_timeout = n;
    localStorage.setItem('user', JSON.stringify(savedUser));
  } catch {
    /* ignore */
  }
  if (typeof window !== 'undefined') {
    window.dispatchEvent(
      new CustomEvent(SESSION_TIMEOUT_EVENT, { detail: { minutes: n } })
    );
  }
}

const useSessionTimeout = (user) => {
  const timeoutRef = useRef(null);
  const warningTimeoutRef = useRef(null);
  const eventsBoundRef = useRef(false);
  const onUserActivityRef = useRef(() => {});

  const clearTimers = useCallback(() => {
    if (timeoutRef.current) {
      clearTimeout(timeoutRef.current);
      timeoutRef.current = null;
    }
    if (warningTimeoutRef.current) {
      clearTimeout(warningTimeoutRef.current);
      warningTimeoutRef.current = null;
    }
  }, []);

  const logoutForInactivity = useCallback(() => {
    [
      'auth_token',
      'token',
      'user',
      'selectedConversation',
      'unread_messages_by_user',
      'internal_chat_unread_count',
    ].forEach((key) => localStorage.removeItem(key));

    toast.error(
      'Sua sessão expirou por inatividade. Você será redirecionado para a página de login.'
    );
    window.location.href = '/login';
  }, []);

  const scheduleTimers = useCallback(() => {
    clearTimers();
    const timeoutMinutes = sharedTimeoutMinutes;
    if (!timeoutMinutes || timeoutMinutes <= 0) return;

    const timeoutMs = timeoutMinutes * 60 * 1000;
    timeoutRef.current = setTimeout(logoutForInactivity, timeoutMs);

    if (timeoutMinutes > 1) {
      warningTimeoutRef.current = setTimeout(() => {
        toast.info(
          'Sua sessão expirará em 30 segundos por inatividade. Realize alguma ação para continuar.'
        );
      }, Math.max(timeoutMs - 30000, 0));
    } else if (timeoutMinutes === 1) {
      warningTimeoutRef.current = setTimeout(() => {
        toast.info(
          'Sua sessão expirará em 30 segundos por inatividade. Realize alguma ação para continuar.'
        );
      }, 30 * 1000);
    }
  }, [clearTimers, logoutForInactivity]);

  onUserActivityRef.current = scheduleTimers;

  const resolveTimeoutMinutes = useCallback(async () => {
    if (user?.session_timeout != null) {
      const fromUser = Number(user.session_timeout);
      if (Number.isFinite(fromUser) && fromUser > 0) {
        sharedTimeoutMinutes = fromUser;
        return fromUser;
      }
    }

    try {
      const token = localStorage.getItem('auth_token') || localStorage.getItem('token');
      if (token) {
        const response = await axios.get('/api/auth/me/', {
          headers: { Authorization: `Token ${token}` },
          __skip401Logout: true,
        });
        const fromApi = Number(response.data?.session_timeout);
        if (Number.isFinite(fromApi) && fromApi > 0) {
          sharedTimeoutMinutes = fromApi;
          return fromApi;
        }
      }
    } catch {
      /* fallback */
    }

    const fromStorage = readTimeoutFromStorage();
    if (fromStorage) {
      sharedTimeoutMinutes = fromStorage;
      return fromStorage;
    }

    return sharedTimeoutMinutes || DEFAULT_TIMEOUT_MINUTES;
  }, [user]);

  const activityHandler = useCallback((e) => {
    onUserActivityRef.current?.(e);
  }, []);

  const bindActivityListeners = useCallback(() => {
    if (eventsBoundRef.current) return;
    ['mousedown', 'mousemove', 'keypress', 'scroll', 'touchstart', 'click', 'keydown'].forEach(
      (event) => document.addEventListener(event, activityHandler, true)
    );
    eventsBoundRef.current = true;
  }, [activityHandler]);

  const unbindActivityListeners = useCallback(() => {
    if (!eventsBoundRef.current) return;
    ['mousedown', 'mousemove', 'keypress', 'scroll', 'touchstart', 'click', 'keydown'].forEach(
      (event) => document.removeEventListener(event, activityHandler, true)
    );
    eventsBoundRef.current = false;
  }, [activityHandler]);

  const startTimeout = useCallback(async () => {
    await resolveTimeoutMinutes();
    bindActivityListeners();
    scheduleTimers();
  }, [resolveTimeoutMinutes, bindActivityListeners, scheduleTimers]);

  const updateTimeout = useCallback(
    async (minutes) => {
      if (minutes != null) {
        applySessionTimeout(minutes);
      } else {
        await resolveTimeoutMinutes();
      }
      scheduleTimers();
    },
    [resolveTimeoutMinutes, scheduleTimers]
  );

  // Só a instância do App (com user) controla o cronômetro ativo.
  useEffect(() => {
    if (!user?.id) {
      clearTimers();
      unbindActivityListeners();
      return undefined;
    }

    let cancelled = false;

    (async () => {
      await resolveTimeoutMinutes();
      if (cancelled) return;
      bindActivityListeners();
      scheduleTimers();
    })();

    const onChanged = (e) => {
      const mins = Number(e?.detail?.minutes);
      if (Number.isFinite(mins) && mins > 0) {
        sharedTimeoutMinutes = mins;
        scheduleTimers();
      }
    };
    window.addEventListener(SESSION_TIMEOUT_EVENT, onChanged);

    return () => {
      cancelled = true;
      window.removeEventListener(SESSION_TIMEOUT_EVENT, onChanged);
      clearTimers();
      unbindActivityListeners();
    };
  }, [
    user?.id,
    user?.session_timeout,
    resolveTimeoutMinutes,
    bindActivityListeners,
    unbindActivityListeners,
    scheduleTimers,
    clearTimers,
  ]);

  return { startTimeout, updateTimeout };
};

export default useSessionTimeout;
