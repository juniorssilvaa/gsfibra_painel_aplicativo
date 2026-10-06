import { useEffect, useState } from 'react';
import axios from 'axios';

const cache = new Map();

function currentToken() {
  return localStorage.getItem('auth_token') || localStorage.getItem('token') || '';
}

function fetchAgentMode(token) {
  if (!cache.has(token)) {
    const request = axios
      .get('/api/provider/config/', {
        headers: token ? { Authorization: `Token ${token}` } : {},
        skipErrorToast: true,
      })
      .then((res) => String(res.data?.agent_mode || 'isp').toLowerCase())
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
    fetchAgentMode(token).then((value) => {
      if (alive && value) setMode(value);
    });
    return () => {
      alive = false;
    };
  }, []);

  return mode;
}
