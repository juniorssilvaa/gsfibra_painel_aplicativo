import React, { createContext, useContext, useEffect, useState, useRef, useCallback } from 'react';
import { buildWebSocketUrl } from '../utils/websocketUrl';
import axios from 'axios';
import { useAuth } from './AuthContext';

export const NotificationContext = createContext();

export const useNotifications = () => {
  const context = useContext(NotificationContext);
  if (!context) {
    throw new Error('useNotifications deve ser usado dentro de NotificationProvider');
  }
  return context;
};

export const NotificationProvider = ({ children }) => {
  // ✅ Usar usuário do AuthContext ao invés de buscar novamente
  const { user: authUser } = useAuth();
  const [unreadCount, setUnreadCount] = useState(0);
  const [hasNewMessages, setHasNewMessages] = useState(false);
  const [currentUser, setCurrentUser] = useState(null);
  const websocketRef = useRef(null);
  const reconnectTimeoutRef = useRef(null);
  const [isConnected, setIsConnected] = useState(false);
  const [painelWsConnected, setPainelWsConnected] = useState(false);
  const [unreadMessagesByUser, setUnreadMessagesByUser] = useState({});

  const internalChatWsRef = useRef(null);
  const [internalChatUnreadCount, setInternalChatUnreadCount] = useState(0);
  const [internalChatUnreadByUser, setInternalChatUnreadByUser] = useState({});
  const [activeReminders, setActiveReminders] = useState([]);
  const initializingRef = useRef(false);
  const painelWsRef = useRef(null);
  const painelReconnectRef = useRef(null);
  const connectionFailuresRef = useRef({ internalChat: 0, privateChat: 0 });
  const soundEnabledRef = useRef(false);
  const newMsgSoundRef = useRef('01.mp3');
  const newMsgVolumeRef = useRef(1.0);
  const newConvSoundRef = useRef('02.mp3');
  const newConvVolumeRef = useRef(1.0);
  const audioRef = useRef(null);
  const faviconTimerRef = useRef(null);
  const isFaviconBlinkingRef = useRef(false);
  const lastSoundTimeRef = useRef(0);
  const processedEventsRef = useRef(new Set());
  const PROCESSED_EVENTS_LIMIT = 50;

  const refreshSettings = useCallback(() => {
    // Carregar configurações do localStorage para atualização imediata
    const storedEnabled = localStorage.getItem('sound_notifications_enabled');
    const storedMsgSound = localStorage.getItem('sound_new_message');
    const storedConvSound = localStorage.getItem('sound_new_conversation');
    const storedMsgVolume = localStorage.getItem('sound_new_message_volume');
    const storedConvVolume = localStorage.getItem('sound_new_conversation_volume');

    if (storedEnabled !== null) soundEnabledRef.current = storedEnabled === 'true';
    if (storedMsgSound) newMsgSoundRef.current = storedMsgSound;
    if (storedConvSound) newConvSoundRef.current = storedConvSound;
    if (storedMsgVolume) newMsgVolumeRef.current = parseFloat(storedMsgVolume);
    if (storedConvVolume) newConvVolumeRef.current = parseFloat(storedConvVolume);
  }, []);

  // ✅ Sincronizar usuário do AuthContext com currentUser local
  useEffect(() => {
    if (authUser) {
      setCurrentUser(authUser);
      soundEnabledRef.current = !!authUser.sound_notifications_enabled;
      if (authUser.new_message_sound) newMsgSoundRef.current = authUser.new_message_sound;
      if (authUser.new_message_sound_volume !== undefined) newMsgVolumeRef.current = authUser.new_message_sound_volume;
      if (authUser.new_conversation_sound) newConvSoundRef.current = authUser.new_conversation_sound;
      if (authUser.new_conversation_sound_volume !== undefined) newConvVolumeRef.current = authUser.new_conversation_sound_volume;
    } else {
      setCurrentUser(null);
    }
    // Sempre tentar carregar do localStorage também para garantir o estado mais recente
    refreshSettings();
  }, [authUser, refreshSettings]);

  // Ouvir eventos de atualização de configurações
  useEffect(() => {
    const handleSettingsUpdate = () => refreshSettings();
    window.addEventListener('notification-settings-updated', handleSettingsUpdate);
    window.addEventListener('storage', (e) => {
      if (e.key && e.key.includes('sound_')) refreshSettings();
    });
    return () => {
      window.removeEventListener('notification-settings-updated', handleSettingsUpdate);
      window.removeEventListener('storage', handleSettingsUpdate);
    };
  }, [refreshSettings]);

  useEffect(() => {
    if (currentUser?.id) {

      connectWebSocket();
      connectPainelWebSocket();
      connectInternalChatWebSocket();
      loadInternalChatUnreadCount();
      loadInternalChatUnreadByUser();
    }

    return () => {
      if (websocketRef.current) {
        websocketRef.current.close();
      }
      if (reconnectTimeoutRef.current) {
        clearTimeout(reconnectTimeoutRef.current);
      }
      if (painelWsRef.current) {
        painelWsRef.current.close();
      }
      if (painelReconnectRef.current) {
        clearTimeout(painelReconnectRef.current);
      }
      if (internalChatWsRef.current) {
        internalChatWsRef.current.close();
      }
    };
  }, [currentUser?.id]);



  // ✅ REMOVIDO: loadCurrentUser não é mais necessário
  // O usuário vem do AuthContext, evitando chamadas duplicadas de /me

  const loadInternalChatUnreadCount = async () => {
    try {
      // Priorizar auth_token que é o padrão salvo no Login, mas aceitar token também para compatibilidade
      const token = localStorage.getItem('auth_token') || localStorage.getItem('token');
      const response = await axios.get('/api/internal-chat-unread-count/', {
        headers: { Authorization: `Token ${token}` }
      });

      if (response.status === 200) {
        const data = response.data;
        const count = data.total_unread || 0;
        setInternalChatUnreadCount(count);

        if (count === 0) {
          localStorage.removeItem('internal_chat_unread_count');
        }
      }
    } catch (error) {
      console.error('Erro ao carregar contador do chat interno:', error);
      setInternalChatUnreadCount(0);
    }
  };

  const loadInternalChatUnreadByUser = async () => {
    try {
      // Priorizar auth_token que é o padrão salvo no Login, mas aceitar token também para compatibilidade
      const token = localStorage.getItem('auth_token') || localStorage.getItem('token');
      const response = await axios.get('/api/internal-chat-unread-by-user/', {
        headers: { Authorization: `Token ${token}` }
      });

      if (response.status === 200) {
        const data = response.data;
        setInternalChatUnreadByUser(data);
      }
    } catch (error) {
      console.error('Erro ao carregar contadores por usuário do chat interno:', error);
    }
  };

  const checkReminders = useCallback(async () => {
    if (!currentUser?.id) return;

    try {
      const token = localStorage.getItem('auth_token') || localStorage.getItem('token');
      const response = await axios.get('/api/reminders/check/', {
        headers: { Authorization: `Token ${token}` }
      });

      if (response.status === 200 && response.data.length > 0) {
        setActiveReminders(prev => {
          const existingIds = new Set(prev.map(r => r.id));
          const newReminders = response.data.filter(r => !existingIds.has(r.id));

          if (newReminders.length > 0) {
            playSound(newMsgSoundRef.current, newMsgVolumeRef.current);

            if ('Notification' in window && Notification.permission === 'granted') {
              newReminders.forEach(reminder => {
                new Notification('Lembrete Agendado', {
                  body: reminder.message,
                  icon: '/favicon.png',
                  tag: `reminder-${reminder.id}`
                });
              });
            }
          }

          return [...prev, ...newReminders];
        });
      }
    } catch (error) {
      // Erro silencioso no polling
    }
  }, [currentUser?.id]);

  const dismissReminder = async (reminderId) => {
    try {
      const token = localStorage.getItem('auth_token') || localStorage.getItem('token');
      await axios.patch(`/api/reminders/${reminderId}/mark_notified/`, {}, {
        headers: { Authorization: `Token ${token}` }
      });

      setActiveReminders(prev => prev.filter(r => r.id !== reminderId));
    } catch (error) {
      console.error('Erro ao marcar lembrete como notificado:', error);
      setActiveReminders(prev => prev.filter(r => r.id !== reminderId));
    }
  };

  // Polling para lembretes a cada 45 segundos
  useEffect(() => {
    if (currentUser?.id) {
      checkReminders();
      const interval = setInterval(checkReminders, 15000);
      return () => clearInterval(interval);
    }
  }, [currentUser?.id, checkReminders]);

  const connectInternalChatWebSocket = () => {
    if (internalChatWsRef.current?.readyState === WebSocket.OPEN) {
      return;
    }

    if (internalChatWsRef.current && internalChatWsRef.current.readyState !== WebSocket.CLOSED) {
      internalChatWsRef.current.close();
    }

    try {
      // Priorizar auth_token que é o padrão salvo no Login, mas aceitar token também para compatibilidade
      const token = localStorage.getItem('auth_token') || localStorage.getItem('token');
      // CORREÇÃO: Usar função centralizada para construir URL de WebSocket
      const wsUrl = buildWebSocketUrl('/ws/internal-chat/notifications/', { token });

      internalChatWsRef.current = new WebSocket(wsUrl);

      internalChatWsRef.current.onopen = () => {
        // Resetar contador de falhas quando conectar com sucesso
        connectionFailuresRef.current.internalChat = 0;
        internalChatWsRef.current.send(JSON.stringify({
          type: 'join_notifications'
        }));
      };

      internalChatWsRef.current.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);

          if (data.type === 'unread_count_update') {
            setInternalChatUnreadCount(data.total_unread || 0);
            if (data.unread_by_user) {
              setInternalChatUnreadByUser(data.unread_by_user);
            }
          }
        } catch (error) {
          // Erro silencioso - não logar para evitar poluição do console
        }
      };

      internalChatWsRef.current.onclose = (event) => {
        // Não tentar reconectar se foi fechado intencionalmente
        if (event.wasClean || event.code === 1000) {
          return;
        }

        // Limitar tentativas de reconexão para evitar spam de erros
        connectionFailuresRef.current.internalChat++;
        if (connectionFailuresRef.current.internalChat > 3) {
          // Parar de tentar reconectar após 3 falhas consecutivas
          return;
        }

        setTimeout(() => {
          if (currentUser?.id) {
            connectInternalChatWebSocket();
          }
        }, 5000);
      };

      internalChatWsRef.current.onerror = (error) => {
        // Suprimir erro nativo do navegador - não fazer nada para evitar poluição do console
        // O erro já será mostrado pelo navegador, não precisamos logar novamente
      };

    } catch (error) {
      // CORREÇÃO DE SEGURANÇA: Não expor detalhes do erro que podem conter token
      // Silenciar erro para não expor informações sensíveis
    }
  };

  const connectWebSocket = () => {
    if (websocketRef.current?.readyState === WebSocket.OPEN) {
      return;
    }

    if (websocketRef.current && websocketRef.current.readyState !== WebSocket.CLOSED) {
      websocketRef.current.close();
    }

    try {
      // Priorizar auth_token que é o padrão salvo no Login, mas aceitar token também para compatibilidade
      const token = localStorage.getItem('auth_token') || localStorage.getItem('token');
      // CORREÇÃO: Usar função centralizada para construir URL de WebSocket
      const wsUrl = buildWebSocketUrl('/ws/private-chat/', { token });

      websocketRef.current = new WebSocket(wsUrl);

      websocketRef.current.onopen = () => {
        // Resetar contador de falhas quando conectar com sucesso
        connectionFailuresRef.current.privateChat = 0;
        setIsConnected(true);

        if (currentUser?.id) {
          websocketRef.current.send(JSON.stringify({
            type: 'join_notifications',
            user_id: currentUser.id
          }));
        }
      };

      websocketRef.current.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);

          if (data.type === 'new_private_message') {
            const recipientId = data.message?.recipient_id ?? data.message?.recipient?.id;
            if (recipientId === currentUser?.id) {
              const senderId = data.message?.sender?.id?.toString();
              setUnreadCount(prev => prev + 1);
              setHasNewMessages(true);
              if (senderId) {
                setUnreadMessagesByUser(prev => {
                  const newUnreadByUser = {
                    ...prev,
                    [senderId]: (prev[senderId] || 0) + 1
                  };
                  localStorage.setItem('unread_messages_by_user', JSON.stringify(newUnreadByUser));
                  window.dispatchEvent(new Event('unread-messages-changed'));
                  return newUnreadByUser;
                });
              }
              if ('Notification' in window && Notification.permission === 'granted') {
                new Notification('Nova Mensagem no Chat Interno', {
                  body: `${data.message?.sender?.name || 'Usuario'}: ${data.message?.content}`,
                  icon: '/favicon.png',
                  tag: 'chat-interno'
                });
              }
            }
          }
        } catch (error) {
          // Erro silencioso - não logar para evitar poluição do console
        }
      };

      websocketRef.current.onclose = (event) => {
        setIsConnected(false);

        // Não tentar reconectar se foi fechado intencionalmente
        if (event.wasClean || event.code === 1000) {
          return;
        }

        // Limitar tentativas de reconexão para evitar spam de erros
        connectionFailuresRef.current.privateChat++;
        if (connectionFailuresRef.current.privateChat > 3) {
          // Parar de tentar reconectar após 3 falhas consecutivas
          return;
        }

        reconnectTimeoutRef.current = setTimeout(() => {
          if (currentUser?.id) {
            connectWebSocket();
          }
        }, 5000);
      };

      websocketRef.current.onerror = (error) => {
        // Suprimir erro nativo do navegador - não fazer nada para evitar poluição do console
        // O erro já será mostrado pelo navegador, não precisamos logar novamente
        setIsConnected(false);
      };

    } catch (error) {
      // Erro silencioso - não logar para evitar poluição do console
    }
  };

  const connectPainelWebSocket = () => {
    try {
      // Tentar obter provedorId do usuário ou da URL como fallback
      let pId = currentUser?.provedor_id;
      if (!pId) {
        const match = window.location.pathname.match(/\/app\/accounts\/(\d+)/);
        if (match) pId = parseInt(match[1]);
      }

      if (!pId) {
        return;
      }
      // Priorizar auth_token que é o padrão salvo no Login, mas aceitar token também para compatibilidade
      const token = localStorage.getItem('auth_token') || localStorage.getItem('token');
      if (!token) {
        return;
      }
      // CORREÇÃO: Usar função centralizada para construir URL de WebSocket
      const wsUrl = buildWebSocketUrl(`/ws/painel/${pId}/`, { token });

      if (painelWsRef.current?.readyState === WebSocket.OPEN) return;
      if (painelWsRef.current && painelWsRef.current.readyState !== WebSocket.CLOSED) {
        painelWsRef.current.close();
      }
      const ws = new WebSocket(wsUrl);
      painelWsRef.current = ws;

      ws.onopen = () => {
        setPainelWsConnected(true);
      };

      ws.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);
          // PRIORIDADE: event_type é mais específico que type no WebSocket do painel
          const evt = data.event_type || data.type || data.action;


          const isMessageEvent = evt === 'message_received' || evt === 'message_created' || evt === 'new_message' || evt === 'chat_message';

          // Gerar um ID único mais abrangente
          const eventId = data.id ||
            data.message?.id ||
            data.data?.id ||
            data.data?.message?.id ||
            (data.conversation?.id ? `conv_${data.conversation.id}_${evt}` : null) ||
            (data.conversation_id ? `conv_${data.conversation_id}_${evt}` : null);

          if (eventId && processedEventsRef.current.has(eventId)) {

            return;
          }

          if (isMessageEvent) {
            // ISOLAMENTO: Só tocar som se a mensagem for para o usuário logado
            // O WebSocket do painel envia todas as mensagens do provedor.
            // Precisamos verificar se a conversa está atribuída a este atendente.
            const messageData = data.message || data.data?.message || data.data;
            const assigneeId = data.conversation?.assignee_id || data.data?.conversation?.assignee_id || data.assignee_id;

            // SÓ TOCAR SOM SE A MENSAGEM FOR DO CLIENTE (OU SE NÃO TIVERMOS CERTEZA)
            // Isso evita duplicidade com mensagens enviadas pelo próprio atendente ou bot
            if (messageData && messageData.is_from_customer === false) {
              return;
            }

            // ISOLAMENTO: Só tocar som se for conversa MINHA ou DESATRIBUÍDA
            const isUnassigned = !assigneeId || assigneeId === "" || assigneeId === 0;
            const isMine = assigneeId && currentUser?.id && parseInt(assigneeId) === currentUser.id;
            
            if (!isUnassigned && !isMine) {
              return;
            }

            // Verificar se esta mensagem pertence a uma conversa que ACABOU de tocar som de "Nova Conversa"
            const convId = data.conversation_id || data.conversation?.id || data.data?.conversation_id;
            if (convId && processedEventsRef.current.has(`silence_msg_${convId}`)) {
              return;
            }

            if (eventId) {
              processedEventsRef.current.add(eventId);
              if (processedEventsRef.current.size > PROCESSED_EVENTS_LIMIT) {
                const first = processedEventsRef.current.values().next().value;
                processedEventsRef.current.delete(first);
              }
            }

            playSound(newMsgSoundRef.current, newMsgVolumeRef.current);
            startBlinkingFavicon();
          } else if (evt === 'conversation_created' || evt === 'chat_created') {
            // LÓGICA: Som de "Novas Conversas" APENAS em eventos de criação real
            const conv = data.conversation || data.payload || data.data || data.data?.conversation;


            playSound(newConvSoundRef.current, newConvVolumeRef.current);
            startBlinkingFavicon();

            // Se tocou som de nova conversa, silenciar sons de mensagem desta conversa pelos próximos segundos
            if (conv?.id) {
              const silenceKey = `silence_msg_${conv.id}`;
              processedEventsRef.current.add(silenceKey);
              setTimeout(() => {
                processedEventsRef.current.delete(silenceKey);
              }, 5000);
            }
          } else if (evt === 'conversation_updated' || evt === 'conversation_event' || evt === 'update_conversation') {
            // LÓGICA: Status pending/snoozed também toca som de "Novas Conversas" (re-atendimento)
            const conv = data.conversation || data.payload || data.data || data.data?.conversation;
            const status = conv?.status || conv?.additional_attributes?.status;
            const assigneeId = conv?.assignee_id || conv?.assignee?.id;

            // Se entrar em pendente sem atendente, toca som para todos (nova conversa em espera)
            // Se entrar em pendente COM atendente, toca som apenas para o atendente (isolamento)
            const isUnassigned = !assigneeId;
            const isMine = assigneeId && currentUser?.id && parseInt(assigneeId) === currentUser.id;
            const isCriticalStatus = status === 'pending' || status === 'snoozed';

            if (isCriticalStatus && (isUnassigned || isMine)) {

              playSound(newConvSoundRef.current, newConvVolumeRef.current);
              startBlinkingFavicon();
            }
          }
        } catch (_) { }
      };
      ws.onclose = (event) => {
        setPainelWsConnected(false);
        // Códigos que indicam erro permanente (não tentar reconectar)
        // 4001 = Unauthorized, 4003 = Forbidden
        const permanentErrorCodes = [4001, 4003];

        if (permanentErrorCodes.includes(event.code)) {
          // Erro de permissão ou autenticação - não tentar reconectar
          return;
        }

        // Apenas reconectar se não foi erro permanente
        painelReconnectRef.current = setTimeout(connectPainelWebSocket, 3000);
      };
      ws.onerror = () => {
        try { ws.close(); } catch (_) { }
      };
    } catch (e) {
      // CORREÇÃO DE SEGURANÇA: Não expor detalhes do erro que podem conter token
      // Silenciar erro para não expor informações sensíveis
    }
  };

  const playSound = (fileName, volume = 1.0) => {
    // Fallback: se soundEnabledRef.current for falso, verificar localStorage por garantia
    const isEnabled = soundEnabledRef.current || localStorage.getItem('sound_notifications_enabled') === 'true';

    if (!isEnabled) {
      return;
    }
    // DEBOUNCE: Reduzido para 1.0s para ser mais responsivo em conversas rápidas
    const now = Date.now();
    if (now - lastSoundTimeRef.current < 1000) {
      return;
    }
    lastSoundTimeRef.current = now;

    try {
      const src = `/sounds/${fileName}`;
      if (!audioRef.current) {
        audioRef.current = new Audio(src);
      } else {
        audioRef.current.pause();
        audioRef.current.src = src;
      }
      audioRef.current.volume = volume;
      audioRef.current.currentTime = 0;
      audioRef.current.play().catch(() => { });
    } catch (_) { }
  };

  const setFavicon = (hrefBase) => {
    try {
      const href = `${hrefBase}?v=${Date.now()}`;
      // Alvos principais: link rel="icon" e link rel="shortcut icon"
      // Evitamos sobrescrever o manifest ou o apple-touch-icon aqui.
      const selectors = [
        "link[rel='icon']",
        "link[rel='shortcut icon']",
        "link[rel~='icon']"
      ];
      const links = Array.from(document.querySelectorAll(selectors.join(',')));
      
      if (links.length > 0) {
        links.forEach(l => {
          // Só atualizar se for um dos ícones principais de exibição na aba
          if (l.rel.includes('icon') && !l.rel.includes('apple-touch-icon')) {
            l.href = href;
          }
        });
      }
    } catch (_) { }
  };

  const startBlinkingFavicon = () => {
    if (isFaviconBlinkingRef.current) return;
    isFaviconBlinkingRef.current = true;
    const defaultIcon = '/favicon-96x96.png';
    const notifyIcon = '/favicon_red.png';
    let toggle = false;
    faviconTimerRef.current = setInterval(() => {
      if (document.visibilityState === 'visible') {
        stopBlinkingFavicon();
        return;
      }
      toggle = !toggle;
      setFavicon(toggle ? notifyIcon : defaultIcon);
    }, 800);
  };

  const stopBlinkingFavicon = () => {
    if (faviconTimerRef.current) {
      clearInterval(faviconTimerRef.current);
      faviconTimerRef.current = null;
    }
    isFaviconBlinkingRef.current = false;
    // Restaurar para o ícone padrão de 96x96 que é o principal do pacote
    setFavicon('/favicon-96x96.png');
    
    // Pequeno delay para garantir que o navegador perceba a mudança e normalize
    setTimeout(() => {
       // Opcional: recarregar o .ico como backup
       // setFavicon('/favicon.ico');
    }, 100);
  };

  const clearNotifications = () => {
    setUnreadCount(0);
    setHasNewMessages(false);
    setUnreadMessagesByUser({});
    localStorage.removeItem('unread_messages_by_user');
    window.dispatchEvent(new Event('unread-messages-changed'));
  };

  const markAsRead = (count = null, userId = null) => {
    if (userId) {
      setUnreadMessagesByUser(prev => {
        const userUnreadCount = prev[userId] || 0;
        const newUnreadByUser = { ...prev };
        delete newUnreadByUser[userId];
        setUnreadCount(prevTotal => Math.max(0, prevTotal - userUnreadCount));
        localStorage.setItem('unread_messages_by_user', JSON.stringify(newUnreadByUser));
        window.dispatchEvent(new Event('unread-messages-changed'));
        return newUnreadByUser;
      });
    } else if (count !== null) {
      setUnreadCount(prev => Math.max(0, prev - count));
    } else {
      clearNotifications();
    }
  };

  // ✅ REMOVIDO: useEffect que chamava connectWebSocket sem verificar usuário
  // A conexão agora é feita apenas quando há currentUser (linha 44-69)

  useEffect(() => {
    if (currentUser?.id && websocketRef.current?.readyState === WebSocket.OPEN) {
      websocketRef.current.send(JSON.stringify({
        type: 'join_notifications',
        user_id: currentUser.id
      }));
    }
  }, [currentUser]);

  useEffect(() => {
    if ('Notification' in window && Notification.permission === 'default') {
      Notification.requestPermission();
    }
  }, []);

  useEffect(() => {
    const onVisibility = () => {
      if (document.visibilityState === 'visible') {
        stopBlinkingFavicon();
      }
    };
    document.addEventListener('visibilitychange', onVisibility);
    return () => {
      document.removeEventListener('visibilitychange', onVisibility);
      stopBlinkingFavicon();
    };
  }, []);

  const value = {
    unreadCount,
    hasNewMessages,
    currentUser,
    isConnected,
    painelWsConnected,
    unreadMessagesByUser,
    internalChatUnreadCount,
    internalChatUnreadByUser,
    loadInternalChatUnreadCount,
    loadInternalChatUnreadByUser,
    clearNotifications,
    markAsRead,
    activeReminders,
    dismissReminder,
    websocket: websocketRef.current
  };

  return (
    <NotificationContext.Provider value={value}>
      {children}
    </NotificationContext.Provider>
  );
};
