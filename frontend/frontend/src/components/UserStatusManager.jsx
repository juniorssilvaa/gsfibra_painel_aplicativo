import React, { useEffect, useRef } from 'react';
import { buildWebSocketUrl } from '../utils/websocketUrl';

/**
 * Componente para gerenciar o status online do usuário logado
 * Conecta ao WebSocket individual do usuário para marcar como online/offline automaticamente
 */
function UserStatusManager({ user }) {
  const websocketRef = useRef(null);
  const reconnectTimeoutRef = useRef(null);
  const pingIntervalRef = useRef(null);

  const connectUserWebSocket = () => {
    if (!user || !user.id) return;

    // Priorizar auth_token que é o padrão salvo no Login, mas aceitar token também para compatibilidade
    const token = user.token || localStorage.getItem('auth_token') || localStorage.getItem('token');
    if (!token) return;

    // Fechar conexão anterior se existir
    if (websocketRef.current && websocketRef.current.readyState === WebSocket.OPEN) {
      websocketRef.current.close();
    }

    try {
      // Priorizar auth_token que é o padrão salvo no Login, mas aceitar token também para compatibilidade
      const token = localStorage.getItem('auth_token') || localStorage.getItem('token');
      if (!token) return;
      
      const wsUrl = buildWebSocketUrl('/ws/user_status/', { token });
      const ws = new WebSocket(wsUrl);
      
      ws.onopen = () => {
        // Log removido para não expor dados sensíveis
        websocketRef.current = ws;
        
        // Limpar timeout de reconexão
        if (reconnectTimeoutRef.current) {
          clearTimeout(reconnectTimeoutRef.current);
          reconnectTimeoutRef.current = null;
        }
        
        // Enviar ping a cada 30 segundos para manter conexão ativa
        pingIntervalRef.current = setInterval(() => {
          if (ws.readyState === WebSocket.OPEN) {
            ws.send(JSON.stringify({ type: 'ping' }));
          }
        }, 30000);
      };
      
      ws.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);
          
          if (data.type === 'pong') {
            // Pong recebido do usuário
          }
        } catch (error) {
          console.warn('Erro ao processar mensagem WebSocket do usuário:', error);
        }
      };
      
      ws.onclose = () => {
        // Log removido('WebSocket do usuário desconectado');
        websocketRef.current = null;
        
        // Limpar ping interval
        if (pingIntervalRef.current) {
          clearInterval(pingIntervalRef.current);
          pingIntervalRef.current = null;
        }
        
        // Reconectar após 5 segundos
        reconnectTimeoutRef.current = setTimeout(() => {
          // Log removido('Tentando reconectar WebSocket do usuário');
          connectUserWebSocket();
        }, 5000);
      };
      
      ws.onerror = (error) => {
        // CORREÇÃO DE SEGURANÇA: Não expor token em logs
        // O erro pode conter a URL com token, mas não vamos logá-la
      };
      
    } catch (error) {
      // CORREÇÃO DE SEGURANÇA: Não expor detalhes do erro que podem conter token
      // Silenciar erro para não expor informações sensíveis
    }
  };

  // Conectar quando o usuário for definido
  useEffect(() => {
    if (user && user.id) {
      // Aguardar um pouco para garantir que o usuário esteja totalmente carregado
      const timer = setTimeout(() => {
        connectUserWebSocket();
      }, 1000);
      
      return () => {
        clearTimeout(timer);
        if (websocketRef.current && websocketRef.current.readyState === WebSocket.OPEN) {
          websocketRef.current.close();
        }
        if (reconnectTimeoutRef.current) {
          clearTimeout(reconnectTimeoutRef.current);
        }
        if (pingIntervalRef.current) {
          clearInterval(pingIntervalRef.current);
        }
      };
    }
  }, [user?.id]);

  // Não renderiza nada - é apenas um gerenciador de estado
  return null;
}

export default UserStatusManager;



