import { useState, useEffect, useRef, useCallback } from 'react';
import axios from 'axios';
import { buildWebSocketUrl } from '../utils/websocketUrl';

export default function useBackendStatus() {
  const [httpStatus, setHttpStatus] = useState('offline');
  const [wsStatus, setWsStatus] = useState('offline');
  const healthCheckIntervalRef = useRef(null);
  const wsRef = useRef(null);
  const reconnectTimeoutRef = useRef(null);
  const pingIntervalRef = useRef(null);

  const getFinalStatus = useCallback(() => {
    if (httpStatus === 'offline') {
      return 'offline';
    }
    if (httpStatus === 'online' && wsStatus === 'online') {
      return 'online';
    }
    if (httpStatus === 'online' && wsStatus === 'connecting') {
      return 'connecting';
    }
    if (httpStatus === 'online' && wsStatus === 'offline') {
      return 'connecting';
    }
    return 'offline';
  }, [httpStatus, wsStatus]);

  const finalStatus = getFinalStatus();

  const checkHealth = useCallback(async () => {
    try {
      await axios.get('/api/health/', {
        timeout: 3000,
        validateStatus: (status) => status === 200 || status === 301,
      });

      setHttpStatus('online');
      return true;
    } catch {
      setHttpStatus('offline');
      setWsStatus('offline');

      if (wsRef.current && wsRef.current.readyState !== WebSocket.CLOSED) {
        wsRef.current.close();
      }

      return false;
    }
  }, []);

  const connectWebSocket = useCallback(() => {
    try {
      const token = localStorage.getItem('auth_token') || localStorage.getItem('token');
      if (!token) {
        setWsStatus('offline');
        return;
      }

      if (wsRef.current && wsRef.current.readyState !== WebSocket.CLOSED) {
        wsRef.current.close();
      }

      if (pingIntervalRef.current) {
        clearInterval(pingIntervalRef.current);
        pingIntervalRef.current = null;
      }

      const wsUrl = buildWebSocketUrl('/ws/user_status/', { token });
      const ws = new WebSocket(wsUrl);
      wsRef.current = ws;

      setWsStatus('connecting');

      ws.onopen = () => {
        setWsStatus('online');

        if (reconnectTimeoutRef.current) {
          clearTimeout(reconnectTimeoutRef.current);
          reconnectTimeoutRef.current = null;
        }

        pingIntervalRef.current = setInterval(() => {
          if (ws.readyState === WebSocket.OPEN) {
            try {
              ws.send(JSON.stringify({ type: 'ping' }));
            } catch {
              /* ignore */
            }
          } else if (pingIntervalRef.current) {
            clearInterval(pingIntervalRef.current);
            pingIntervalRef.current = null;
          }
        }, 30000);
      };

      ws.onclose = (event) => {
        wsRef.current = null;

        if (pingIntervalRef.current) {
          clearInterval(pingIntervalRef.current);
          pingIntervalRef.current = null;
        }

        const permanentErrorCodes = [4001, 4003];

        if (permanentErrorCodes.includes(event.code)) {
          setWsStatus('offline');
          return;
        }

        checkHealth().then((httpOk) => {
          if (!httpOk) {
            setWsStatus('offline');
          } else {
            setWsStatus('connecting');

            if (reconnectTimeoutRef.current) {
              clearTimeout(reconnectTimeoutRef.current);
            }
            reconnectTimeoutRef.current = setTimeout(() => {
              checkHealth().then((stillOk) => {
                if (stillOk && (wsRef.current === null || wsRef.current.readyState === WebSocket.CLOSED)) {
                  connectWebSocket();
                }
              });
            }, 3000);
          }
        });
      };

      ws.onerror = () => {
        checkHealth().then((httpOk) => {
          if (!httpOk) {
            setWsStatus('offline');
          } else {
            setWsStatus('connecting');
          }
        });
      };
    } catch {
      setWsStatus('offline');
    }
  }, [checkHealth]);

  useEffect(() => {
    checkHealth().then((httpOk) => {
      if (httpOk) {
        connectWebSocket();
      } else {
        setWsStatus('offline');
      }
    });

    healthCheckIntervalRef.current = setInterval(() => {
      checkHealth().then((httpOk) => {
        if (httpOk && (wsRef.current === null || wsRef.current.readyState === WebSocket.CLOSED)) {
          connectWebSocket();
        }
      });
    }, 10000);

    return () => {
      if (healthCheckIntervalRef.current) {
        clearInterval(healthCheckIntervalRef.current);
      }
      if (reconnectTimeoutRef.current) {
        clearTimeout(reconnectTimeoutRef.current);
      }
      if (pingIntervalRef.current) {
        clearInterval(pingIntervalRef.current);
      }
      if (wsRef.current && wsRef.current.readyState !== WebSocket.CLOSED) {
        wsRef.current.close();
      }
    };
  }, [checkHealth, connectWebSocket]);

  return { status: finalStatus };
}
