/**
 * Tickets de curta duração para WebSocket / SSE.
 * O token DRF de longa duração NÃO deve ir na query string.
 */
import { buildApiPath } from './apiBaseUrl';

let cachedTicket = null;
let cachedExpiresAt = 0;
let inflight = null;

const SKEW_MS = 15000; // renovar 15s antes de expirar

function getAuthToken() {
  if (typeof window === 'undefined') return null;
  return localStorage.getItem('auth_token') || localStorage.getItem('token');
}

export function clearRealtimeTicketCache() {
  cachedTicket = null;
  cachedExpiresAt = 0;
  inflight = null;
}

/**
 * Obtém (ou renova) um ticket realtime.
 * @returns {Promise<string|null>}
 */
export async function getRealtimeTicket(force = false) {
  const now = Date.now();
  if (!force && cachedTicket && cachedExpiresAt > now + SKEW_MS) {
    return cachedTicket;
  }

  const authToken = getAuthToken();
  if (!authToken) {
    clearRealtimeTicketCache();
    return null;
  }

  if (inflight) {
    return inflight;
  }

  inflight = (async () => {
    try {
      const res = await fetch(buildApiPath('/api/auth/realtime-ticket/'), {
        method: 'POST',
        headers: {
          Authorization: `Token ${authToken}`,
          'Content-Type': 'application/json',
          Accept: 'application/json',
        },
        body: '{}',
      });
      if (!res.ok) {
        clearRealtimeTicketCache();
        return null;
      }
      const data = await res.json();
      const ticket = data?.ticket;
      const expiresIn = Number(data?.expires_in) || 90;
      if (!ticket) {
        clearRealtimeTicketCache();
        return null;
      }
      cachedTicket = ticket;
      cachedExpiresAt = Date.now() + expiresIn * 1000;
      return cachedTicket;
    } catch (_) {
      clearRealtimeTicketCache();
      return null;
    } finally {
      inflight = null;
    }
  })();

  return inflight;
}
