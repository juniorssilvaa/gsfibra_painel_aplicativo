import { useState, useEffect, useRef, useCallback } from 'react';
import axios from 'axios';
import { buildWebSocketUrl } from '../utils/websocketUrl';

/**
 * Hook para monitorar o status da conexão com o backend
 * Faz polling do health check HTTP e monitora WebSocket
 * 
 * @returns {Object} { status: 'online' | 'connecting' | 'offline' }
 */
export default function useBackendStatus() {
  const [httpStatus, setHttpStatus] = useState('offline'); // 'online' | 'offline'
  const [wsStatus, setWsStatus] = useState('offline'); // 'online' | 'connecting' | 'offline'
  const healthCheckIntervalRef = useRef(null);
  const wsRef = useRef(null);
  const reconnectTimeoutRef = useRef(null);
  const pingIntervalRef = useRef(null);
  
  // Calcular status final combinando HTTP e WebSocket
  const getFinalStatus = useCallback(() => {
    // Se HTTP está offline, backend está offline
    if (httpStatus === 'offline') {
      return 'offline';
    }
    
    // Se HTTP está online e WebSocket está online -> online
    if (httpStatus === 'online' && wsStatus === 'online') {
      return 'online';
    }
    
    // Se HTTP está online mas WebSocket está conectando -> connecting
    if (httpStatus === 'online' && wsStatus === 'connecting') {
      return 'connecting';
    }
    
    // Se HTTP está online mas WebSocket está offline -> connecting (tentando reconectar)
    if (httpStatus === 'online' && wsStatus === 'offline') {
      return 'connecting';
    }
    
    // Default: offline
    return 'offline';
  }, [httpStatus, wsStatus]);
  
  const finalStatus = getFinalStatus();
  
  // Health check HTTP - polling a cada 10 segundos
  const checkHealth = useCallback(async () => {
    try {
      const response = await axios.get('/api/health/', {
        timeout: 3000, // Timeout de 3 segundos
        validateStatus: (status) => status === 200 || status === 301 // Aceitar 200 e 301 (redirect)
      });
      
      // HTTP está respondendo
      setHttpStatus('online');
      return true;
    } catch (error) {
      // Health check falhou
      setHttpStatus('offline');
      setWsStatus('offline');
      
      // Fechar WebSocket se existir
      if (wsRef.current && wsRef.current.readyState !== WebSocket.CLOSED) {
        wsRef.current.close();
      }
      
      return false;
    }
  }, []);
  
  // Conectar ao WebSocket do user_status
  const connectWebSocket = useCallback(() => {
    try {
      const token = localStorage.getItem('auth_token') || localStorage.getItem('token');
      if (!token) {
        setWsStatus('offline');
        return;
      }
      
      // Fechar conexão anterior se existir
      if (wsRef.current && wsRef.current.readyState !== WebSocket.CLOSED) {
        wsRef.current.close();
      }
      
      // Limpar intervalos anteriores
      if (pingIntervalRef.current) {
        clearInterval(pingIntervalRef.current);
        pingIntervalRef.current = null;
      }
      
      const wsUrl = buildWebSocketUrl('/ws/user_status/', { token });
      const ws = new WebSocket(wsUrl);
      wsRef.current = ws;
      
      // Marcar como tentando conectar
      setWsStatus('connecting');
      
      ws.onopen = () => {
        // WebSocket conectado
        setWsStatus('online');
        
        // Limpar timeout de reconexão
        if (reconnectTimeoutRef.current) {
          clearTimeout(reconnectTimeoutRef.current);
          reconnectTimeoutRef.current = null;
        }
        
        // Enviar ping periodicamente para manter conexão viva
        pingIntervalRef.current = setInterval(() => {
          if (ws.readyState === WebSocket.OPEN) {
            try {
              ws.send(JSON.stringify({ type: 'ping' }));
            } catch (e) {
              // Ignorar erros de envio
            }
          } else {
            if (pingIntervalRef.current) {
              clearInterval(pingIntervalRef.current);
              pingIntervalRef.current = null;
            }
          }
        }, 30000); // Ping a cada 30 segundos
      };
      
      ws.onclose = (event) => {
        // WebSocket desconectado
        wsRef.current = null;
        
        // Limpar ping interval
        if (pingIntervalRef.current) {
          clearInterval(pingIntervalRef.current);
          pingIntervalRef.current = null;
        }
        
        // Códigos que indicam erro permanente (não tentar reconectar)
        const permanentErrorCodes = [4001, 4003]; // Unauthorized, Forbidden
        
        if (permanentErrorCodes.includes(event.code)) {
          setWsStatus('offline');
          return;
        }
        
        // Verificar se HTTP ainda está respondendo
        checkHealth().then(httpOk => {
          if (!httpOk) {
            // HTTP também falhou - offline completo
            setWsStatus('offline');
          } else {
            // HTTP OK mas WebSocket caiu - tentar reconectar
            setWsStatus('connecting');
            
            // Reconectar após 3 segundos
            if (reconnectTimeoutRef.current) {
              clearTimeout(reconnectTimeoutRef.current);
            }
            reconnectTimeoutRef.current = setTimeout(() => {
              // Só reconectar se HTTP ainda estiver OK
              checkHealth().then(httpOk => {
                if (httpOk && (wsRef.current === null || wsRef.current.readyState === WebSocket.CLOSED)) {
                  connectWebSocket();
                }
              });
            }, 3000);
          }
        });
      };
      
      ws.onerror = () => {
        // Erro no WebSocket - verificar HTTP
        checkHealth().then(httpOk => {
          if (!httpOk) {
            setWsStatus('offline');
          } else {
            setWsStatus('connecting');
          }
        });
      };
      
    } catch (error) {
      setWsStatus('offline');
    }
  }, [checkHealth]);
  
  // Inicializar monitoramento
  useEffect(() => {
    // Verificação inicial de saúde
    checkHealth().then(httpOk => {
      if (httpOk) {
        // HTTP OK - tentar conectar WebSocket
        connectWebSocket();
      } else {
        // HTTP falhou - offline
        setWsStatus('offline');
      }
    });
    
    // Polling do health check a cada 10 segundos
    healthCheckIntervalRef.current = setInterval(() => {
      checkHealth().then(httpOk => {
        // Se HTTP voltou a responder e WebSocket está offline, tentar reconectar
        if (httpOk && (wsRef.current === null || wsRef.current.readyState === WebSocket.CLOSED)) {
          connectWebSocket();
        }
      });
    }, 10000);
    
    // Cleanup
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

