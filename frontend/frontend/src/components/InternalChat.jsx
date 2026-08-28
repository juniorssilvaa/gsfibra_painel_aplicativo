import React, { useState, useEffect, useRef, useContext } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from './ui/card';
import { Button } from './ui/button';
import { Input } from './ui/input';
import { Textarea } from './ui/textarea';
import { Badge } from './ui/badge';
import { Avatar, AvatarFallback } from './ui/avatar';
import { NotificationContext } from '../contexts/NotificationContext';
import { 
  MessageSquare, 
  Send, 
  Paperclip, 
  Image, 
  Video, 
  Mic, 
  Phone,
  Users,
  Settings,
  Search,
  MoreVertical,
  Smile,
  Reply,
  Download
} from 'lucide-react';
import axios from 'axios';
import { buildWebSocketUrl } from '../utils/websocketUrl';

const InternalChat = () => {
  const { loadInternalChatUnreadCount } = useContext(NotificationContext);
  const [chatRooms, setChatRooms] = useState([]);
  const [selectedRoom, setSelectedRoom] = useState(null);
  const [messages, setMessages] = useState([]);
  const [newMessage, setNewMessage] = useState('');
  const [participants, setParticipants] = useState([]);
  const [isTyping, setIsTyping] = useState(false);
  const [typingUsers, setTypingUsers] = useState([]);
  const [onlineUsers, setOnlineUsers] = useState(new Set());
  const [ws, setWs] = useState(null);
  const [loading, setLoading] = useState(false);
  const [isRecording, setIsRecording] = useState(false);
  const [showEmojiPicker, setShowEmojiPicker] = useState(false);
  const [replyingTo, setReplyingTo] = useState(null);
  
  const messagesEndRef = useRef(null);
  const fileInputRef = useRef(null);
  const audioInputRef = useRef(null);
  const typingTimeoutRef = useRef(null);
  
  // Usar URL relativa (será resolvida pelo proxy do Vite)
  const API_BASE = '/api';

  // ===== EFEITOS =====
  
  useEffect(() => {
    loadChatRooms();
  }, []);
  
  useEffect(() => {
    if (selectedRoom) {
      localStorage.setItem('internal_selected_room_id', String(selectedRoom.id));
      connectWebSocket();
      loadMessages();
      loadParticipants();
      setReplyingTo(null);
    }
    
    return () => {
      if (ws) {
        ws.close();
      }
    };
  }, [selectedRoom]);
  
  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  // ===== FUNÇÕES DE API =====
  
  const loadChatRooms = async () => {
    try {
      // Priorizar auth_token que é o padrão salvo no Login, mas aceitar token também para compatibilidade
      const token = localStorage.getItem('auth_token') || localStorage.getItem('token');
      const response = await axios.get(`${API_BASE}/conversations/internal-chat/rooms/`, {
        headers: { Authorization: `Token ${token}` }
      });
      setChatRooms(response.data);
      
      // Selecionar primeira sala se existir
      if (response.data.length > 0 && !selectedRoom) {
        const savedId = localStorage.getItem('internal_selected_room_id');
        const found = savedId ? response.data.find(r => String(r.id) === String(savedId)) : null;
        setSelectedRoom(found || response.data[0]);
      }
    } catch (error) {
      console.error('Erro ao carregar salas:', error);
    }
  };
  
  const loadMessages = async () => {
    if (!selectedRoom) {
      return;
    }
    
    try {
      setLoading(true);
      // Priorizar auth_token que é o padrão salvo no Login, mas aceitar token também para compatibilidade
      const token = localStorage.getItem('auth_token') || localStorage.getItem('token');
      const response = await axios.get(`${API_BASE}/conversations/internal-chat/messages/`, {
        headers: { Authorization: `Token ${token}` },
        params: { room_id: selectedRoom.id }
      });
      
      // Remover mensagens temporárias antes de carregar as mensagens do backend
      // A API pode retornar array direto ou objeto com results (paginação)
      const confirmedMessages = response.data.results || response.data || [];
      const messagesArray = Array.isArray(confirmedMessages) ? confirmedMessages : [];
      // Ordenar mensagens por created_at para garantir ordem correta
      const sortedMessages = messagesArray.sort((a, b) => {
        const dateA = new Date(a.created_at || 0);
        const dateB = new Date(b.created_at || 0);
        return dateA - dateB;
      });
      setMessages(sortedMessages);
      
      // Marcar todas as mensagens como lidas quando carregar
      await markAllMessagesAsRead();
      
    } catch (error) {
      console.error('Erro ao carregar mensagens:', error);
    } finally {
      setLoading(false);
    }
  };

  const markAllMessagesAsRead = async () => {
    if (!selectedRoom) {
      return;
    }
    
    try {
      // Priorizar auth_token que é o padrão salvo no Login, mas aceitar token também para compatibilidade
      const token = localStorage.getItem('auth_token') || localStorage.getItem('token');
      
      await axios.post(`${API_BASE}/conversations/internal-chat/messages/mark_all_read/`, {
        room_id: selectedRoom.id
      }, {
        headers: { Authorization: `Token ${token}` }
      });
      
      // Recarregar contador de mensagens não lidas
      if (loadInternalChatUnreadCount) {
        loadInternalChatUnreadCount();
      }
      
    } catch (error) {
      console.error('Erro ao marcar mensagens como lidas:', error);
    }
  };
  
  const loadParticipants = async () => {
    if (!selectedRoom) return;
    
    try {
      // Priorizar auth_token que é o padrão salvo no Login, mas aceitar token também para compatibilidade
      const token = localStorage.getItem('auth_token') || localStorage.getItem('token');
      // Usar a URL correta para buscar usuários do provedor
      const response = await axios.get(`${API_BASE}/users/my_provider_users/`, {
        headers: { Authorization: `Token ${token}` }
      });
      setParticipants(response.data.users || []);
    } catch (error) {
      console.error('Erro ao carregar participantes:', error);
    }
  };
  
  // ===== WEBSOCKET =====
  
  const connectWebSocket = () => {
    if (!selectedRoom) return;
    
    // Priorizar auth_token que é o padrão salvo no Login, mas aceitar token também para compatibilidade
    const token = localStorage.getItem('auth_token') || localStorage.getItem('token');
    if (!token) return;
    
    const wsUrl = buildWebSocketUrl(`/ws/internal-chat/${selectedRoom.id}/`, { token });
    const websocket = new WebSocket(wsUrl);
    
    websocket.onopen = () => {
      console.log('WebSocket conectado ao chat interno');
      setWs(websocket);
    };
    
    websocket.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        console.log('[InternalChat] Mensagem WebSocket recebida:', data.type, data);
        handleWebSocketMessage(data);
      } catch (error) {
        console.error('[InternalChat] Erro ao processar mensagem WebSocket:', error);
      }
    };
    
    websocket.onclose = () => {
      console.log('WebSocket desconectado');
      setWs(null);
    };
    
    websocket.onerror = (error) => {
      // CORREÇÃO DE SEGURANÇA: Não expor token em logs
      // O erro pode conter a URL com token, mas não vamos logá-la
    };
  };
  
  const handleWebSocketMessage = (data) => {
    switch (data.type) {
      case 'new_message':
        // Verificar se é uma mensagem que já foi adicionada temporariamente
        setMessages(prev => {
          // Filtrar mensagens temporárias que correspondem à nova mensagem (mesmo conteúdo e remetente)
          const filtered = prev.filter(msg => {
            if (msg.id && msg.id.startsWith && msg.id.startsWith('temp_')) {
              // Se a mensagem temporária tem o mesmo conteúdo e foi enviada pelo mesmo usuário
              return !(msg.content === data.message.content && 
                       msg.sender?.id === data.message.sender?.id);
            }
            return true;
          });
          
          // Adicionar a mensagem confirmada, evitando duplicatas
          if (!filtered.some(msg => msg.id === data.message.id)) {
            const newMessages = [...filtered, data.message];
            // Ordenar mensagens por created_at para garantir ordem correta
            return newMessages.sort((a, b) => {
              const dateA = new Date(a.created_at || 0);
              const dateB = new Date(b.created_at || 0);
              return dateA - dateB;
            });
          }
          return filtered; // A mensagem já existe, não adicionar novamente
        });
        break;
        
      case 'message_read':
        setMessages(prev => prev.map(msg => 
          msg.id === data.message_id 
            ? { ...msg, is_read: true }
            : msg
        ));
        break;
        
      case 'reaction_added':
      case 'reaction_removed':
        loadMessages(); // Recarregar para pegar reações atualizadas
        break;
        
      case 'typing_notification':
        handleTypingNotification(data);
        break;
        
      case 'user_status_changed':
        handleUserStatusChange(data);
        break;
        
      case 'room_event':
        if (data.event_type === 'user_joined' || data.event_type === 'user_left') {
          loadParticipants();
        }
        break;
    }
  };
  
  const handleTypingNotification = (data) => {
    if (data.is_typing) {
      setTypingUsers(prev => [...prev.filter(u => u.id !== data.user_id), {
        id: data.user_id,
        username: data.username
      }]);
    } else {
      setTypingUsers(prev => prev.filter(u => u.id !== data.user_id));
    }
  };
  
  const handleUserStatusChange = (data) => {
    if (data.status === 'online') {
      setOnlineUsers(prev => new Set([...prev, data.user_id]));
    } else {
      setOnlineUsers(prev => {
        const newSet = new Set(prev);
        newSet.delete(data.user_id);
        return newSet;
      });
    }
  };
  
  // ===== ENVIO DE MENSAGENS =====
  
  const sendMessage = async () => {
    if (!newMessage.trim()) return;
    if (!selectedRoom) return;
    
    try {
      // Priorizar auth_token que é o padrão salvo no Login, mas aceitar token também para compatibilidade
      const token = localStorage.getItem('auth_token') || localStorage.getItem('token');
      if (!token) {
        console.error('Token não encontrado');
        return;
      }
      
      // Decodificar token JWT de forma segura
      let userId = null;
      try {
        const tokenParts = token.split('.');
        if (tokenParts.length === 3) {
          const payload = JSON.parse(atob(tokenParts[1]));
          userId = payload.user_id;
        }
      } catch (decodeError) {
        console.error('Erro ao decodificar token:', decodeError);
      }
      
      const messageData = {
        content: newMessage.trim(),
        room_id: selectedRoom.id,
        message_type: 'text'
      };
      
      if (replyingTo) {
        messageData.reply_to_id = replyingTo.id;
      }
      
      // Adiciona a mensagem imediatamente à lista local antes de enviar à API
      // para exibição imediata (otimistic update)
      const tempId = `temp_${Date.now()}`;
      const tempMessage = {
        id: tempId,
        content: newMessage.trim(),
        sender: { id: userId, name: 'Você' },
        message_type: 'text',
        created_at: new Date().toISOString(),
        is_read: false,
        reply_to: replyingTo || null
      };
      
      setMessages(prev => [...prev, tempMessage]);
      
      await axios.post(`${API_BASE}/conversations/internal-chat/messages/`, messageData, {
        headers: { Authorization: `Token ${token}` }
      });
      
      setNewMessage('');
      setReplyingTo(null);
      stopTyping();
      
    } catch (error) {
      console.error('Erro ao enviar mensagem:', error);
      // Remover a mensagem temporária em caso de erro
      setMessages(prev => prev.filter(msg => !msg.id.startsWith('temp_')));
    }
  };
  
  const sendFileMessage = async (file, messageType) => {
    if (!selectedRoom) return;
    
    try {
      // Priorizar auth_token que é o padrão salvo no Login, mas aceitar token também para compatibilidade
      const token = localStorage.getItem('auth_token') || localStorage.getItem('token');
      const formData = new FormData();
      formData.append('file', file);
      formData.append('room_id', selectedRoom.id);
      formData.append('message_type', messageType);
      if (replyingTo) {
        formData.append('reply_to_id', replyingTo.id);
      }
      
      await axios.post(`${API_BASE}/conversations/internal-chat/messages/`, formData, {
        headers: { 
          Authorization: `Token ${token}`,
          'Content-Type': 'multipart/form-data'
        }
      });
      setReplyingTo(null);
      
    } catch (error) {
      console.error('Erro ao enviar arquivo:', error);
    }
  };
  
  const handleFileUpload = (event) => {
    const file = event.target.files[0];
    if (!file) return;
    
    let messageType = 'file';
    if (file.type.startsWith('image/')) messageType = 'image';
    else if (file.type.startsWith('video/')) messageType = 'video';
    else if (file.type.startsWith('audio/')) messageType = 'audio';
    
    sendFileMessage(file, messageType);
    event.target.value = '';
  };
  
  // ===== DIGITAÇÃO =====
  
  const handleInputChange = (e) => {
    setNewMessage(e.target.value);
    
    if (!isTyping) {
      setIsTyping(true);
      ws?.send(JSON.stringify({ type: 'typing_start' }));
    }
    
    // Reset timeout
    if (typingTimeoutRef.current) {
      clearTimeout(typingTimeoutRef.current);
    }
    
    typingTimeoutRef.current = setTimeout(stopTyping, 2000);
  };
  
  const stopTyping = () => {
    if (isTyping) {
      setIsTyping(false);
      ws?.send(JSON.stringify({ type: 'typing_stop' }));
    }
    
    if (typingTimeoutRef.current) {
      clearTimeout(typingTimeoutRef.current);
    }
  };
  
  // ===== REAÇÕES =====
  
  const reactToMessage = async (messageId, emoji) => {
    try {
      const token = localStorage.getItem('token');
      await axios.post(`${API_BASE}/conversations/internal-chat/messages/${messageId}/react/`, 
        { emoji },
        { headers: { Authorization: `Token ${token}` } }
      );
    } catch (error) {
      console.error('Erro ao reagir:', error);
    }
  };
  
  // ===== UTILITÁRIOS =====
  
  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };
  
  const formatTime = (timestamp) => {
    return new Date(timestamp).toLocaleTimeString('pt-BR', {
      hour: '2-digit',
      minute: '2-digit'
    });
  };
  
  const getFileIcon = (messageType) => {
    switch (messageType) {
      case 'image': return <Image className="w-4 h-4" />;
      case 'video': return <Video className="w-4 h-4" />;
      case 'audio': return <Mic className="w-4 h-4" />;
      default: return <Paperclip className="w-4 h-4" />;
    }
  };
  
  const emojis = ['👍', '❤️', '😂', '😮', '😢', '😡'];

  // ===== RENDER =====
  
  return (
    <div className="flex h-[calc(100vh-120px)] bg-background">
      {/* Sidebar - Salas de Chat */}
      <div className="w-80 border-r border-border bg-card">
        <div className="p-4 border-b border-border">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-lg font-semibold text-foreground">Chat Interno</h2>
            <div className="flex gap-2">
              <Button size="sm" variant="ghost">
                <Settings className="w-4 h-4" />
              </Button>
              <Button size="sm" variant="ghost" onClick={onClose}>
                ✕
              </Button>
            </div>
          </div>
          
          <div className="relative">
            <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 w-4 h-4 text-muted-foreground" />
            <Input 
              placeholder="Buscar salas..." 
              className="pl-10"
            />
          </div>
        </div>
        
        <div className="flex-1 overflow-y-auto">
          {chatRooms.map(room => (
            <div
              key={room.id}
              onClick={() => setSelectedRoom(room)}
              className={`p-4 border-b border-border cursor-pointer hover:bg-muted transition-colors ${
                selectedRoom?.id === room.id ? 'bg-muted border-l-4 border-l-primary' : ''
              }`}
            >
              <div className="flex items-center justify-between mb-2">
                <h3 className="font-medium text-foreground">{room.name}</h3>
                {room.unread_count > 0 && (
                  <Badge variant="destructive" className="text-xs">
                    {room.unread_count}
                  </Badge>
                )}
              </div>
              
              <div className="flex items-center gap-2 text-sm text-muted-foreground">
                <Users className="w-3 h-3" />
                <span>{room.participant_count} participantes</span>
              </div>
              
              {room.last_message && (
                <p className="text-sm text-muted-foreground mt-1 truncate">
                  {room.last_message.sender.name}: {room.last_message.content || '[Arquivo]'}
                </p>
              )}
            </div>
          ))}
        </div>
      </div>
      
      {/* Área Principal do Chat */}
      <div className="flex-1 flex flex-col">
        {selectedRoom ? (
          <>
            {/* Header do Chat */}
            <div className="p-4 border-b border-border bg-card">
              <div className="flex items-center justify-between">
                <div>
                  <h2 className="text-lg font-semibold text-foreground">{selectedRoom.name}</h2>
                  <div className="flex items-center gap-2 text-sm text-muted-foreground">
                    <Users className="w-3 h-3" />
                    <span>{participants.length} participantes</span>
                    {typingUsers.length > 0 && (
                      <span className="text-primary">
                        • {typingUsers.map(u => u.username).join(', ')} digitando...
                      </span>
                    )}
                  </div>
                </div>
                
                <div className="flex items-center gap-2">
                  {/* Ícones removidos conforme solicitado */}
                </div>
              </div>
            </div>
            
            {/* Área de Mensagens */}
            <div className="flex-1 overflow-y-auto p-4 bg-background">
              {loading ? (
                <div className="flex justify-center items-center h-full">
                  <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary"></div>
                </div>
              ) : (
                <div className="space-y-4">
                  {messages.map(message => (
                    <div key={message.id} className="group">
                      {/* Mensagem de resposta */}
                      {message.reply_to && (
                        <div className="ml-12 mb-1 p-2 bg-muted rounded text-sm border-l-2 border-primary">
                          <div className="font-medium text-muted-foreground">
                            {message.reply_to.sender.name}
                          </div>
                          <div className="text-foreground">
                            {message.reply_to.content || `[${message.reply_to.message_type}]`}
                          </div>
                        </div>
                      )}
                      
                      <div className="flex items-start gap-3">
                        <Avatar className="w-8 h-8">
                          <AvatarFallback>
                            {message.sender.name?.slice(0, 2).toUpperCase()}
                          </AvatarFallback>
                        </Avatar>
                        
                        <div className="flex-1">
                          <div className="flex items-center gap-2 mb-1">
                            <span className="font-medium text-foreground text-sm">
                              {message.sender.name}
                            </span>
                            <span className="text-xs text-muted-foreground">
                              {formatTime(message.created_at)}
                            </span>
                            {onlineUsers.has(message.sender.id) && (
                              <div className="w-2 h-2 bg-green-500 rounded-full"></div>
                            )}
                          </div>
                          
                          {/* Conteúdo da mensagem */}
                          <div className="bg-card border border-border rounded-lg p-3 max-w-lg">
                            {message.message_type === 'text' ? (
                              <p className="text-foreground">{message.content}</p>
                            ) : (
                              <div className="flex items-center gap-2">
                                {getFileIcon(message.message_type)}
                                <div>
                                  <p className="text-foreground font-medium">
                                    {message.file_name}
                                  </p>
                                  {message.file_size && (
                                    <p className="text-xs text-muted-foreground">
                                      {(message.file_size / 1024 / 1024).toFixed(2)} MB
                                    </p>
                                  )}
                                </div>
                                {message.file_url && (
                                  <Button size="sm" variant="ghost" asChild>
                                    <a href={message.file_url} download>
                                      <Download className="w-4 h-4" />
                                    </a>
                                  </Button>
                                )}
                              </div>
                            )}
                            
                            {/* Reações */}
                            {message.reactions && message.reactions.length > 0 && (
                              <div className="flex gap-1 mt-2">
                                {message.reactions.map(reaction => (
                                  <button
                                    key={`${reaction.user.id}-${reaction.emoji}`}
                                    onClick={() => reactToMessage(message.id, reaction.emoji)}
                                    className="text-xs bg-muted hover:bg-muted/80 rounded px-2 py-1 transition-colors"
                                  >
                                    {reaction.emoji}
                                  </button>
                                ))}
                              </div>
                            )}
                          </div>
                          
                          {/* Ações da mensagem (aparecem no hover) */}
                          <div className="flex gap-1 mt-1 opacity-0 group-hover:opacity-100 transition-opacity">
                            <Button 
                              size="sm" 
                              variant="ghost"
                              onClick={() => setReplyingTo(message)}
                            >
                              <Reply className="w-3 h-3" />
                            </Button>
                            
                            {/* Emojis rápidos */}
                            {emojis.map(emoji => (
                              <Button
                                key={emoji}
                                size="sm"
                                variant="ghost"
                                onClick={() => reactToMessage(message.id, emoji)}
                                className="text-xs"
                              >
                                {emoji}
                              </Button>
                            ))}
                          </div>
                        </div>
                      </div>
                    </div>
                  ))}
                  <div ref={messagesEndRef} />
                </div>
              )}
            </div>
            
            {/* Resposta ativa */}
            {replyingTo && (
              <div className="px-4 py-2 bg-muted border-t border-border">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <Reply className="w-4 h-4 text-primary" />
                    <span className="text-sm text-foreground">
                      Respondendo a <strong>{replyingTo.sender.name}</strong>
                    </span>
                  </div>
                  <Button 
                    size="sm" 
                    variant="ghost"
                    onClick={() => setReplyingTo(null)}
                  >
                    ✕
                  </Button>
                </div>
                <p className="text-sm text-muted-foreground ml-6 truncate">
                  {replyingTo.content || `[${replyingTo.message_type}]`}
                </p>
              </div>
            )}
            
            {/* Área de Input */}
            <div className="p-4 border-t border-border bg-card">
              <div className="flex items-end gap-2">
                <div className="flex gap-1">
                  <Button 
                    size="sm" 
                    variant="ghost"
                    onClick={() => fileInputRef.current?.click()}
                  >
                    <Paperclip className="w-4 h-4" />
                  </Button>
                  
                  <Button 
                    size="sm" 
                    variant="ghost"
                    onClick={() => setShowEmojiPicker(!showEmojiPicker)}
                  >
                    <Smile className="w-4 h-4" />
                  </Button>
                  
                  <Button 
                    size="sm" 
                    variant="ghost"
                    onClick={() => audioInputRef.current?.click()}
                  >
                    <Mic className="w-4 h-4" />
                  </Button>
                </div>
                
                <Textarea
                  value={newMessage}
                  onChange={handleInputChange}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter' && !e.shiftKey) {
                      e.preventDefault();
                      sendMessage();
                    }
                  }}
                  placeholder="Digite sua mensagem..."
                  className="flex-1 min-h-0 resize-none"
                  rows={1}
                />
                
                <Button 
                  onClick={() => {
                    console.log('DEBUG: Botão de enviar clicado');
                    sendMessage();
                  }}
                  disabled={!newMessage.trim()}
                  size="sm"
                >
                  <Send className="w-4 h-4" />
                </Button>
              </div>
              
              {/* Emoji Picker */}
              {showEmojiPicker && (
                <div className="mt-2 p-2 bg-background border border-border rounded-lg">
                  <div className="grid grid-cols-8 gap-1">
                    {emojis.map(emoji => (
                      <button
                        key={emoji}
                        onClick={() => {
                          setNewMessage(prev => prev + emoji);
                          setShowEmojiPicker(false);
                        }}
                        className="p-2 hover:bg-muted rounded text-lg"
                      >
                        {emoji}
                      </button>
                    ))}
                  </div>
                </div>
              )}
              
              {/* Inputs ocultos */}
              <input
                ref={fileInputRef}
                type="file"
                hidden
                onChange={handleFileUpload}
                accept="image/*,video/*,.pdf,.doc,.docx,.txt"
              />
              
              <input
                ref={audioInputRef}
                type="file"
                hidden
                onChange={handleFileUpload}
                accept="audio/*"
              />
            </div>
          </>
        ) : (
          <div className="flex-1 flex items-center justify-center bg-background">
            <div className="text-center">
              <MessageSquare className="w-16 h-16 text-muted-foreground mx-auto mb-4" />
              <h3 className="text-lg font-medium text-foreground mb-2">
                Selecione uma sala
              </h3>
              <p className="text-muted-foreground">
                Escolha uma sala de chat para começar a conversar
              </p>
            </div>
          </div>
        )}
      </div>
      
      {/* Sidebar - Participantes */}
      {selectedRoom && (
        <div className="w-64 border-l border-border bg-card">
          <div className="p-4 border-b border-border">
            <h3 className="font-medium text-foreground">Participantes</h3>
          </div>
          
          <div className="p-2 space-y-1">
            {participants.map(participant => (
              <div key={participant.id} className="flex items-center gap-2 p-2 rounded hover:bg-muted">
                <div className="relative">
                  <Avatar className="w-8 h-8">
                    <AvatarFallback>
                      {participant.user.name?.slice(0, 2).toUpperCase()}
                    </AvatarFallback>
                  </Avatar>
                  {onlineUsers.has(participant.user.id) && (
                    <div className="absolute -bottom-1 -right-1 w-3 h-3 bg-green-500 border-2 border-background rounded-full"></div>
                  )}
                </div>
                
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-medium text-foreground truncate">
                    {participant.user.name}
                  </p>
                  <p className="text-xs text-muted-foreground">
                    {participant.is_admin ? 'Admin' : 'Membro'}
                  </p>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
};

export default InternalChat;