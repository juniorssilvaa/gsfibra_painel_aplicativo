import React, { useState, useEffect, useRef } from 'react';
import { Bell, X, CheckCircle } from 'lucide-react';
import axios from 'axios';
import NotificationModal from './NotificationModal';
import { buildWebSocketUrl } from '../utils/websocketUrl';

const NotificationBell = () => {
  const [notifications, setNotifications] = useState([]);
  const [showDropdown, setShowDropdown] = useState(false);
  const [loading, setLoading] = useState(false);
  const [showModal, setShowModal] = useState(false);
  const [currentNotification, setCurrentNotification] = useState(null);
  const [currentUser, setCurrentUser] = useState(null);
  const wsRef = useRef(null);
  const modalClosedManuallyRef = useRef(false);
  const lastModalCloseTimeRef = useRef(null);
  
  // Estado para mensagens removidas pelo usuário (persistido no localStorage)
  const [removedNotifications, setRemovedNotifications] = useState(() => {
    try {
      const saved = localStorage.getItem('removed_notifications');
      return saved ? JSON.parse(saved) : [];
    } catch {
      return [];
    }
  });

  // Buscar notificações do usuário
  const fetchNotifications = async () => {
    try {
      // Priorizar auth_token que é o padrão salvo no Login, mas aceitar token também para compatibilidade
      const token = localStorage.getItem('auth_token') || localStorage.getItem('token');
      
      // Verificar se o usuário é admin de provedor
      const userResponse = await axios.get('/api/auth/me/', {
        headers: { Authorization: `Token ${token}` }
      });
      
      const user = userResponse.data;
      
      // Permitir que admins e agentes do provedor vejam notificações
      const isAuthorized = (user.user_type === 'admin' || user.user_type === 'agent');
      const hasProvedor = (user.provedores_admin && user.provedores_admin.length > 0) || (user.provedor_id);
      
      if (isAuthorized && hasProvedor) {
        const response = await axios.get('/api/mensagens-sistema/minhas_mensagens/', {
          headers: { Authorization: `Token ${token}` }
        });
        
        // Obter lista atual de removidas do localStorage (sempre ler do localStorage para ter o estado mais atualizado)
        const saved = localStorage.getItem('removed_notifications');
        const currentRemoved = saved ? JSON.parse(saved) : [];
        
        // Filtrar mensagens removidas pelo usuário
        const allNotifications = response.data || [];
        const filteredNotifications = allNotifications.filter(
          n => !currentRemoved.includes(n.id)
        );
        
        setNotifications(filteredNotifications);
      } else {
        // Usuário não é admin de provedor, não mostrar notificações
        setNotifications([]);
      }
    } catch (err) {
      console.error('Erro ao buscar notificações:', err);
      // Em caso de erro, não mostrar notificações
      setNotifications([]);
    }
  };
  
  // Função para remover notificação da lista (persistir no localStorage)
  const removeNotification = (notificationId) => {
    const newRemoved = [...removedNotifications, notificationId];
    setRemovedNotifications(newRemoved);
    
    // Salvar no localStorage
    try {
      localStorage.setItem('removed_notifications', JSON.stringify(newRemoved));
    } catch (err) {
      console.error('Erro ao salvar notificações removidas:', err);
    }
    
    // Remover da lista local imediatamente
    setNotifications(prev => prev.filter(n => n.id !== notificationId));
  };
  
  // Função auxiliar para verificar se a notificação foi lida pelo usuário atual
  const isReadByCurrentUser = (notification, userId) => {
    if (!notification || !userId) return false;
    if (!notification.visualizacoes) return false;
    // O backend armazena as chaves como strings (user_id)
    return !!notification.visualizacoes[userId.toString()];
  };

  // Função para limpar todas as mensagens lidas pelo usuário atual
  const clearReadNotifications = () => {
    if (!currentUser?.id) return;
    
    const readNotifications = notifications.filter(
      n => isReadByCurrentUser(n, currentUser.id)
    );
    
    const readIds = readNotifications.map(n => n.id);
    const newRemoved = [...removedNotifications, ...readIds];
    setRemovedNotifications(newRemoved);
    
    // Salvar no localStorage
    try {
      localStorage.setItem('removed_notifications', JSON.stringify(newRemoved));
    } catch (err) {
      console.error('Erro ao salvar notificações removidas:', err);
    }
    
    // Remover da lista local imediatamente as que o usuário já leu
    setNotifications(prev => prev.filter(
      n => !isReadByCurrentUser(n, currentUser.id)
    ));
  };

  // Marcar como visualizada
  const markAsRead = async (notificationId) => {
    try {
      setLoading(true);
      const token = localStorage.getItem('auth_token') || localStorage.getItem('token');
      const response = await axios.patch(`/api/mensagens-sistema/${notificationId}/marcar-visualizada/`, {}, {
        headers: { Authorization: `Token ${token}` }
      });
      
      // Mensagem marcada como visualizada
      
      // Atualizar lista
      await fetchNotifications();
    } catch (err) {
      console.error('Erro ao marcar como visualizada:', err);
      if (err.response) {
        console.error('Status:', err.response.status);
        console.error('Data:', err.response.data);
      }
      // Mostrar mensagem de erro ao usuário
      alert('Erro ao marcar como visualizada. Tente novamente.');
    } finally {
      setLoading(false);
    }
  };

  // Callback para quando o modal marca como visualizada
  const handleModalMarkAsRead = (notificationId) => {
    markAsRead(notificationId);
    setShowModal(false);
    setCurrentNotification(null);
    // Resetar flags quando marcar como visualizada
    modalClosedManuallyRef.current = false;
    lastModalCloseTimeRef.current = null;
    // Atualizar lista para remover a mensagem das não lidas
    fetchNotifications();
  };

  // Fechar modal sem marcar como visualizada
  // A mensagem continuará aparecendo a cada 15 minutos
  const handleCloseModal = () => {
    // Fechando modal...
    setShowModal(false);
    // Marcar que o modal foi fechado manualmente
    modalClosedManuallyRef.current = true;
    lastModalCloseTimeRef.current = Date.now();
    // Não limpar currentNotification para que possa ser reaberto após 15 minutos
  };

  // Conectar ao WebSocket de notificações
  useEffect(() => {
    const connectWebSocket = () => {
      if (!currentUser?.id) return;
      
      const token = localStorage.getItem('auth_token') || localStorage.getItem('token');
      if (!token) return;
      
      // Fechar conexão anterior se existir
      if (wsRef.current) {
        wsRef.current.close();
      }
      
      try {
        const wsUrl = buildWebSocketUrl(`/ws/notifications/${currentUser.id}/`, { token });
        const ws = new WebSocket(wsUrl);
        wsRef.current = ws;
        
        ws.onopen = () => {
          // WebSocket de notificações conectado
        };
        
        ws.onmessage = (event) => {
          try {
            const data = JSON.parse(event.data);
            console.log('[NOTIFICATION WS] Mensagem recebida:', data);
            
            // Se recebeu uma nova mensagem do sistema, atualizar lista
            if (data.type === 'system_message' && data.message) {
              console.log('[NOTIFICATION WS] Nova mensagem do sistema detectada:', data.message.assunto);
                // Verificar se a mensagem não foi removida pelo usuário
                const saved = localStorage.getItem('removed_notifications');
                const currentRemoved = saved ? JSON.parse(saved) : [];
                
                if (!currentRemoved.includes(data.message.id)) {
                  // Adicionar nova mensagem no início da lista
                  setNotifications(prev => {
                    // Verificar se a mensagem já existe para evitar duplicatas
                    const exists = prev.some(n => n.id === data.message.id);
                    if (exists) {
                      return prev;
                    }
                    return [data.message, ...prev];
                  });
                }
              
              // Mostrar modal se for uma nova mensagem
              if (!showModal) {
                // Resetar flags de controle manual para garantir que novas mensagens sempre apareçam
                modalClosedManuallyRef.current = false;
                lastModalCloseTimeRef.current = null;
                
                setCurrentNotification(data.message);
                setShowModal(true);
              }
            }
          } catch (err) {
            console.error('Erro ao processar mensagem WebSocket:', err);
          }
        };
        
        ws.onclose = (event) => {
          // Reconectar após 3 segundos se não foi fechado intencionalmente
          if (event.code !== 1000) {
            setTimeout(() => {
              if (currentUser?.id) {
                connectWebSocket();
              }
            }, 3000);
          }
        };
        
        ws.onerror = (error) => {
          console.error('Erro no WebSocket de notificações:', error);
        };
      } catch (err) {
        console.error('Erro ao conectar WebSocket de notificações:', err);
      }
    };
    
    if (currentUser?.id) {
      connectWebSocket();
    }
    
    return () => {
      if (wsRef.current) {
        wsRef.current.close();
      }
    };
  }, [currentUser?.id, showModal]);
  
  // Buscar usuário atual e notificações
  useEffect(() => {
    const loadUser = async () => {
      try {
        const token = localStorage.getItem('auth_token') || localStorage.getItem('token');
        if (!token) return;
        
        const userResponse = await axios.get('/api/auth/me/', {
          headers: { Authorization: `Token ${token}` }
        });
        
        setCurrentUser(userResponse.data);
      } catch (err) {
        console.error('Erro ao carregar usuário:', err);
      }
    };
    
    loadUser();
  }, []);
  
  // Executar imediatamente e configurar intervalo
  useEffect(() => {
    // Função que busca notificações usando o estado atual de removedNotifications
    const fetchWithFilter = async () => {
      try {
        const token = localStorage.getItem('auth_token') || localStorage.getItem('token');
        if (!token) return;
        
        const userResponse = await axios.get('/api/auth/me/', {
          headers: { Authorization: `Token ${token}` }
        });
        
        const user = userResponse.data;
        
        const isAuthorized = (user.user_type === 'admin' || user.user_type === 'agent');
        const hasProvedor = (user.provedores_admin && user.provedores_admin.length > 0) || (user.provedor_id);
        
        if (isAuthorized && hasProvedor) {
          const response = await axios.get('/api/mensagens-sistema/minhas_mensagens/', {
            headers: { Authorization: `Token ${token}` }
          });
          
          // Obter lista atual de removidas do localStorage
          const saved = localStorage.getItem('removed_notifications');
          const currentRemoved = saved ? JSON.parse(saved) : [];
          
          // Filtrar mensagens removidas
          const allNotifications = response.data || [];
          const filteredNotifications = allNotifications.filter(
            n => !currentRemoved.includes(n.id)
          );
          
          setNotifications(filteredNotifications);
        } else {
          setNotifications([]);
        }
      } catch (err) {
        console.error('Erro ao buscar notificações:', err);
        setNotifications([]);
      }
    };
    
    // Executar imediatamente
    fetchWithFilter();
    
    // Buscar a cada 30 segundos (fallback caso WebSocket falhe)
    const interval = setInterval(() => {
      fetchWithFilter();
    }, 30000);
    
    return () => {
      clearInterval(interval);
    };
  }, []); // Não precisa de dependências, usa localStorage diretamente

  // Verificar se há novas mensagens não lidas e mostrar modal
  useEffect(() => {
    // Só mostrar modal se tivermos o usuário carregado e houver notificações
    if (currentUser?.id && notifications.length > 0) {
      // Filtrar notificações que o usuário atual ainda não visualizou
      const unreadNotifications = notifications.filter(n => !isReadByCurrentUser(n, currentUser.id));
      
      // Só mostrar modal se:
      // 1. Há mensagens não lidas
      // 2. O modal não está aberto
      // 3. O modal não foi fechado manualmente recentemente (ou passou 15 minutos)
      const shouldShowModal = unreadNotifications.length > 0 && !showModal;
      
      if (shouldShowModal) {
        // Verificar se o modal foi fechado manualmente e se passou 15 minutos
        if (modalClosedManuallyRef.current && lastModalCloseTimeRef.current) {
          const timeSinceClose = Date.now() - lastModalCloseTimeRef.current;
          const fifteenMinutes = 15 * 60 * 1000;
          
          // Se passou menos de 15 minutos desde o fechamento manual, não reabrir
          if (timeSinceClose < fifteenMinutes) {
            return;
          }
          
          // Se passou 15 minutos, resetar a flag e reabrir
          modalClosedManuallyRef.current = false;
          lastModalCloseTimeRef.current = null;
        }
        
        // Mostrar modal para a primeira mensagem não lida
        setCurrentNotification(unreadNotifications[0]);
        setShowModal(true);
        modalClosedManuallyRef.current = false; // Resetar flag quando abrir
      }
    }
  }, [notifications, showModal]);

  // Reabrir modal a cada 15 minutos se houver mensagens não lidas
  // Este intervalo força a reabertura mesmo se o usuário fechar manualmente
  useEffect(() => {
    // Só configurar intervalo se houver mensagens não lidas
    const unreadNotifications = notifications.filter(n => !n.visualizacoes || Object.keys(n.visualizacoes).length === 0);
    
    if (unreadNotifications.length === 0) {
      // Não há mensagens não lidas, não precisa de intervalo
      return;
    }

    // Configurar intervalo para reabrir modal a cada 15 minutos (900000 ms)
    const interval = setInterval(() => {
      // Verificar novamente se ainda há mensagens não lidas
      const currentUnread = notifications.filter(n => !n.visualizacoes || Object.keys(n.visualizacoes).length === 0);
      
      if (currentUnread.length > 0 && !showModal) {
        // Forçar reabertura após 15 minutos, resetando as flags
        modalClosedManuallyRef.current = false;
        lastModalCloseTimeRef.current = null;
        setCurrentNotification(currentUnread[0]);
        setShowModal(true);
      }
    }, 15 * 60 * 1000); // 15 minutos em milissegundos

    return () => {
      clearInterval(interval);
    };
  }, [notifications, showModal]);

  // Contar notificações não lidas
  const unreadCount = notifications.filter(n => !n.visualizacoes || Object.keys(n.visualizacoes).length === 0).length;

  return (
    <div className="relative">
      {/* Sino de notificações */}
      <button
        onClick={() => setShowDropdown(!showDropdown)}
        className="relative p-2 rounded-lg transition-colors text-topbar-foreground hover:bg-sidebar-accent hover:text-sidebar-accent-foreground"
      >
        <Bell size={20} />
        {unreadCount > 0 && (
          <span className="absolute -top-1 -right-1 bg-red-500 text-white text-xs rounded-full h-5 w-5 flex items-center justify-center">
            {unreadCount > 9 ? '9+' : unreadCount}
          </span>
        )}
      </button>

      {/* Dropdown de notificações */}
      {showDropdown && (
        <div className="absolute right-0 mt-2 w-80 bg-card rounded-lg shadow-lg border border-border z-50">
          <div className="p-4 border-b border-border">
            <div className="flex items-center justify-between">
              <h3 className="text-lg font-semibold text-foreground">
                Notificações
              </h3>
              <button
                onClick={() => setShowDropdown(false)}
                className="text-muted-foreground hover:text-foreground"
              >
                <X size={16} />
              </button>
            </div>
          </div>

          <div className="max-h-96 overflow-y-auto">
            {notifications.length === 0 ? (
              <div className="p-4 text-center text-muted-foreground">
                Nenhuma notificação
              </div>
            ) : (
              notifications.map((notification) => {
                const isRead = notification.visualizacoes && Object.keys(notification.visualizacoes).length > 0;
                return (
                  <div
                    key={notification.id}
                    className={`p-4 border-b border-border cursor-pointer hover:bg-muted/50 transition-colors ${
                      !isRead ? 'bg-blue-500/10' : ''
                    }`}
                    onClick={() => {
                      // Abrir modal ao clicar na notificação
                      setCurrentNotification(notification);
                      setShowModal(true);
                    }}
                  >
                    <div className="flex items-start justify-between">
                      <div className="flex-1">
                        <h4 className="font-medium text-foreground mb-1">
                          {notification.assunto}
                        </h4>
                        <p className="text-sm text-muted-foreground mb-2 line-clamp-2">
                          {notification.mensagem}
                        </p>
                        <div className="flex items-center justify-between text-xs text-muted-foreground">
                          <span>
                            {new Date(notification.created_at).toLocaleDateString('pt-BR')}
                          </span>
                          <span className="capitalize">
                            {notification.tipo}
                          </span>
                        </div>
                      </div>
                      
                      <div className="flex items-center gap-2 ml-2" onClick={(e) => e.stopPropagation()}>
                        {!isRead && (
                          <button
                            onClick={() => markAsRead(notification.id)}
                            disabled={loading}
                            className="p-1 text-blue-500 hover:text-blue-600 disabled:opacity-50 rounded hover:bg-blue-500/10"
                            title="Marcar como visualizada"
                          >
                            <CheckCircle size={16} />
                          </button>
                        )}
                        {isRead && (
                          <button
                            onClick={(e) => {
                              e.stopPropagation();
                              removeNotification(notification.id);
                            }}
                            className="p-1 text-red-500 hover:text-red-600 rounded hover:bg-red-500/10"
                            title="Remover da lista"
                          >
                            <X size={16} />
                          </button>
                        )}
                      </div>
                    </div>
                  </div>
                );
              })
            )}
          </div>

          {notifications.length > 0 && (
            <div className="p-3 border-t border-border flex items-center justify-between">
              <button
                onClick={clearReadNotifications}
                className="text-sm text-red-500 hover:text-red-600"
                title="Remover mensagens lidas"
              >
                Limpar Lidas
              </button>
              <button
                onClick={fetchNotifications}
                className="text-sm text-blue-500 hover:text-blue-600"
              >
                Atualizar
              </button>
            </div>
          )}
        </div>
      )}

      {/* Overlay para fechar ao clicar fora */}
      {showDropdown && (
        <div
          className="fixed inset-0 z-40"
          onClick={() => setShowDropdown(false)}
        />
      )}

      {/* Modal de notificação automático */}
      <NotificationModal
        isOpen={showModal}
        onClose={handleCloseModal}
        notification={currentNotification}
        onMarkAsRead={handleModalMarkAsRead}
      />
    </div>
  );
};

export default NotificationBell; 