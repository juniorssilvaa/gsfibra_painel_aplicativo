import React, { createContext, useContext, useEffect, useRef, useState, useCallback } from 'react';
import axios from 'axios';
import { getApiBaseUrl } from '../utils/apiBaseUrl';
import { clearRealtimeTicketCache } from '../utils/realtimeTicket';
import { toast, friendlyApiError } from '../lib/notify';
import {
  emitProvedorPaymentBlocked,
  isProvedorPaymentBlockedError,
} from '../utils/provedorPaymentBlock';

const AuthContext = createContext(null);

// Configurar baseURL do axios UMA ÚNICA VEZ
axios.defaults.baseURL = getApiBaseUrl();



export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);

  const booted = useRef(false);
  const refreshing = useRef(false);
  const refreshQueue = useRef([]);
  const loginInProgress = useRef(false);

  const logout = useCallback(async () => {
    try {
      await axios.post('/api/auth/logout/');
    } catch { }

    clearRealtimeTicketCache();
    localStorage.removeItem('auth_token');
    localStorage.removeItem('token');
    localStorage.removeItem('user');
    booted.current = false;
    setUser(null);
  }, []);

  const refreshToken = React.useCallback(async () => {
    if (refreshing.current) {
      return new Promise((resolve, reject) => {
        refreshQueue.current.push({ resolve, reject });
      });
    }

    refreshing.current = true;

    try {
      const { data } = await axios.post('/api/auth/refresh/');
      if (!data?.token) throw new Error('Token de refresh ausente');

      localStorage.setItem('auth_token', data.token);

      refreshQueue.current.forEach(p => p.resolve(data.token));
      refreshQueue.current = [];

      return data.token;
    } catch (err) {
      refreshQueue.current.forEach(p => p.reject(err));
      refreshQueue.current = [];
      clearRealtimeTicketCache();
      localStorage.removeItem('auth_token');
      localStorage.removeItem('token');
      localStorage.removeItem('user');
      setUser(null);
      throw err;
    } finally {
      refreshing.current = false;
    }
  }, []);

  // Request interceptor — adiciona token se existir
  useEffect(() => {
    const req = axios.interceptors.request.use(config => {
      const token = localStorage.getItem('auth_token');
      if (token) {
        config.headers = config.headers || {};
        config.headers.Authorization = `Token ${token}`;
      }
      return config;
    });
    return () => axios.interceptors.request.eject(req);
  }, []);

  // Response interceptor — tenta refresh se 401
  useEffect(() => {
    const res = axios.interceptors.response.use(
      r => r,
      async error => {
        const original = error.config;
        const status = error.response?.status;

        if (isProvedorPaymentBlockedError(error)) {
          emitProvedorPaymentBlocked();
          return Promise.reject(error);
        }

        const token = localStorage.getItem('auth_token');
        if (!token) return Promise.reject(error);

        const isAuthEndpoint = original.url?.includes('/api/auth/login/') ||
          original.url?.includes('/api/auth/logout/') ||
          original.url?.includes('/api/auth/refresh/');

        if (status !== 401 || original._retry || isAuthEndpoint) {
          const skipToast = original?.skipErrorToast === true;
          const silentStatuses = new Set([401, 0]);
          if (!skipToast && status && !silentStatuses.has(status)) {
            toast.error(friendlyApiError(error, 'Ocorreu um erro. Tente novamente.'));
          }
          return Promise.reject(error);
        }

        original._retry = true;

        try {
          const newToken = await refreshToken();
          original.headers.Authorization = `Token ${newToken}`;
          return axios(original);
        } catch (refreshError) {
          return Promise.reject(refreshError);
        }
      }
    );
    return () => axios.interceptors.response.eject(res);
  }, [refreshToken]);

  const bootstrap = useCallback(async () => {
    if (booted.current) return;
    booted.current = true;

    const token = localStorage.getItem('auth_token');
    if (!token || !token.trim()) {
      if (token) localStorage.removeItem('auth_token');
      setLoading(false);
      return;
    }

    let retries = 0;
    const maxRetries = 2;

    while (retries <= maxRetries) {
      try {
        const { data } = await axios.get('/api/auth/me/');
        setUser(data);
        localStorage.setItem('user', JSON.stringify(data));
        setLoading(false);
        return;
      } catch (err) {
        const status = err.response?.status;

        if (status === 401 && retries < maxRetries) {
          try {
            await refreshToken();
            await new Promise(resolve => setTimeout(resolve, 100));
            retries++;
            continue;
          } catch {
            // Refresh falhou — limpar sessão local
            clearRealtimeTicketCache();
      localStorage.removeItem('auth_token');
            localStorage.removeItem('token');
            localStorage.removeItem('user');
            booted.current = false;
            setUser(null);
            setLoading(false);
            return;
          }
        } else {
          // Token inválido ou expirou — limpar sessão local
          clearRealtimeTicketCache();
      localStorage.removeItem('auth_token');
          localStorage.removeItem('token');
          localStorage.removeItem('user');
          booted.current = false;
          setUser(null);
          setLoading(false);
          return;
        }
      }
    }
  }, [logout, refreshToken]);

  const login = useCallback(async (username, password) => {
    if (loginInProgress.current) throw new Error('Login já em progresso');
    loginInProgress.current = true;

    try {
      const { data } = await axios.post('/api/auth/login/', { username, password });
      if (!data?.token) throw new Error('Token ausente');

      localStorage.setItem('auth_token', data.token);

      try {
        const { data: userData } = await axios.get('/api/auth/me/');
        setUser(userData);
        localStorage.setItem('user', JSON.stringify(userData));
        return userData;
      } catch (err) {
        clearRealtimeTicketCache();
      localStorage.removeItem('auth_token');
        throw err;
      }
    } finally {
      loginInProgress.current = false;
    }
  }, []);

  // Forçar refresh de /me/ — útil quando o provedor_id estava null no primeiro boot
  const refresh = useCallback(async () => {
    try {
      const { data } = await axios.get('/api/auth/me/');
      setUser(data);
      localStorage.setItem('user', JSON.stringify(data));
      return data;
    } catch { return null; }
  }, []);

  // Bootstrap executa UMA ÚNICA VEZ
  useEffect(() => {
    bootstrap();
  }, [bootstrap]);

  return (
    <AuthContext.Provider value={{ user, loading, login, logout, refresh }}>
      {children}
    </AuthContext.Provider>
  );
}

export const useAuth = () => {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error('useAuth deve ser usado dentro de AuthProvider');
  }
  return context;
};
