import { useEffect, useState } from 'react';
import axios from 'axios';

const cache = new Map();

function currentToken() {
  return localStorage.getItem('auth_token') || localStorage.getItem('token') || '';
}

function fetchProviderConfig(token) {
  if (!cache.has(token)) {
    const request = axios
      .get('/api/provider/config/', {
        headers: token ? { Authorization: `Token ${token}` } : {},
        skipErrorToast: true,
      })
      .then((res) => res.data || {})
      .catch(() => {
        cache.delete(token);
        return null;
      });
    cache.set(token, request);
  }
  return cache.get(token);
}

/** Modo do agente do provedor ('isp' ou 'support'); null enquanto carrega. */
export default function useAgentMode() {
  const [mode, setMode] = useState(null);

  useEffect(() => {
    const token = currentToken();
    if (!token) return undefined;
    let alive = true;
    fetchProviderConfig(token).then((data) => {
      if (alive && data) setMode(String(data.agent_mode || 'isp').toLowerCase());
    });
    return () => {
      alive = false;
    };
  }, []);

  return mode;
}

/** Modo de atendimento ('ia' ou 'chatbot'); null enquanto carrega. */
export function useBotMode() {
  const [mode, setMode] = useState(null);

  useEffect(() => {
    const token = currentToken();
    if (!token) return undefined;
    let alive = true;
    fetchProviderConfig(token).then((data) => {
      if (alive && data) setMode(String(data.bot_mode || 'ia').toLowerCase());
    });
    return () => {
      alive = false;
    };
  }, []);

  return mode;
}
