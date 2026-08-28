import React, { useState, useEffect, useRef } from 'react';
import { buildWebSocketUrl } from '../utils/websocketUrl';
import axios from 'axios';

export default function useOnlineUsers() {
  // Verificar se estamos em um ambiente React válido
  if (typeof window === 'undefined') {
    return {
      isUserOnline: () => false,
      getOnlineCount: () => 0,
      onlineUsers: []
    };
  }

  const [onlineUsers, setOnlineUsers] = useState(new Set());
  const [websocket, setWebsocket] = useState(null);
  const reconnectTimeoutRef = useRef(null);

  // Função para verificar se um usuário está online
  const isUserOnline = (userId) => {
    const key = String(userId);
    return onlineUsers.has(key);
  };

  // Função para obter a contagem de usuários online
  const getOnlineCount = () => {
    return onlineUsers.size;
  };

  // Função para buscar usuários online via API REST (fallback)
  const fetchOnlineUsers = async () => {
    try {
      const token = localStorage.getItem('token');
      if (!token) return;

      const response = await axios.get('/api/users/', {
        headers: {
          'Authorization': `Token ${token}`
        }
      });

      if (response.status === 200) {
        const data = response.data;
        const users = data.results || data;
        const onlineUserIds = users
          .filter(user => user.is_online)
          .map(user => String(user.id));
        setOnlineUsers(new Set(onlineUserIds));
        // Status online atualizado via API
      }
    } catch (_) {}
  };

  // Conectar ao WebSocket para monitorar usuários online em tempo real
  const connectWebSocket = () => {
    // Priorizar auth_token que é o padrão salvo no Login, mas aceitar token também para compatibilidade
    const token = localStorage.getItem('auth_token') || localStorage.getItem('token');
    if (!token) return;

    // Fechar WebSocket anterior se existir
    if (websocket && websocket.readyState === WebSocket.OPEN) {
      websocket.close();
    }

    try {
      // Priorizar auth_token que é o padrão salvo no Login, mas aceitar token também para compatibilidade
      const token = localStorage.getItem('auth_token') || localStorage.getItem('token');
      if (!token) return;
      
      const wsUrl = buildWebSocketUrl('/ws/user_status/', { token });
      const ws = new WebSocket(wsUrl);
      
      ws.onopen = () => {
        // Log removido('WebSocket de status conectado');
        setWebsocket(ws);
        
        // Buscar status inicial via API
        fetchOnlineUsers();
        
        // Limpar timeout de reconexão
        if (reconnectTimeoutRef.current) {
          clearTimeout(reconnectTimeoutRef.current);
          reconnectTimeoutRef.current = null;
        }
      };
      
      ws.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);
          // Log removido('Mensagem WebSocket status:', data);
          
          if (data.type === 'user_status_update') {
            if (data.users) {
              // Formato antigo com lista de usuários
              const onlineUserIds = data.users
                .filter(u => u.is_online)
                .map(u => String(u.id));
              setOnlineUsers(new Set(onlineUserIds));
            } else if (data.user_id !== undefined) {
              // Novo formato com atualização individual
              setOnlineUsers(prevUsers => {
                const newUsers = new Set(prevUsers);
                const key = String(data.user_id);
                if (data.is_online) {
                  newUsers.add(key);
                } else {
                  newUsers.delete(key);
                }
                return newUsers;
              });
            }
            // Log removido('Status online atualizado via WebSocket');
          }
        } catch (_) {}
      };
      
      ws.onclose = () => {
        // Log removido('WebSocket de status desconectado');
        setWebsocket(null);
        
        // Reconectar após 5 segundos
        reconnectTimeoutRef.current = setTimeout(() => {
          // Log removido('Tentando reconectar WebSocket...');
          connectWebSocket();
        }, 5000);
      };
      
      ws.onerror = () => {};
      
    } catch (_) {
      fetchOnlineUsers();
    }
  };

  // Inicializar sistema de status online via WebSocket
  useEffect(() => {
    const timer = setTimeout(() => {
      connectWebSocket();
      // Buscar status inicial apenas uma vez ao conectar
      fetchOnlineUsers();
    }, 2000);

    return () => {
      clearTimeout(timer);
      if (websocket && websocket.readyState === WebSocket.OPEN) {
        websocket.close();
      }
      if (reconnectTimeoutRef.current) {
        clearTimeout(reconnectTimeoutRef.current);
      }
    };
  }, []);

  return {
    isUserOnline,
    getOnlineCount,
    onlineUsers: Array.from(onlineUsers)
  };
}