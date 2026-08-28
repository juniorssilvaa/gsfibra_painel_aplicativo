import React, { useState, useEffect, useRef } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from './ui/card';
import { Button } from './ui/button';
import { Input } from './ui/input';
import { Textarea } from './ui/textarea';
import { Badge } from './ui/badge';
import { Avatar, AvatarFallback, AvatarImage } from './ui/avatar';
import { 
  X,
  Send, 
  Paperclip, 
  Image, 
  Video, 
  Mic, 
  Smile,
  Reply,
  Download,
  Phone,
  VideoIcon,
  MoreVertical,
  Plus
} from 'lucide-react';
import axios from 'axios';
import { buildMediaUrl } from '../config/environment';
import { useNotifications } from '../contexts/NotificationContext';
import { buildWebSocketUrl } from '../utils/websocketUrl';

const PrivateChatSidebar = ({ 
  isOpen, 
  onClose, 
  selectedUser, 
  currentUser 
}) => {
  const [messages, setMessages] = useState([]);
  const [newMessage, setNewMessage] = useState('');
  const [loading, setLoading] = useState(false);
  const [ws, setWs] = useState(null);
  const [isRecording, setIsRecording] = useState(false);
  const [showEmojiPicker, setShowEmojiPicker] = useState(false);
  const [replyingTo, setReplyingTo] = useState(null);
  const [isTyping, setIsTyping] = useState(false);
  const [otherUserTyping, setOtherUserTyping] = useState(false);
  const [otherUserRecording, setOtherUserRecording] = useState(false);
  const [showFileMenu, setShowFileMenu] = useState(false);
  const [dragStartX, setDragStartX] = useState(null);
  const [dragMsgId, setDragMsgId] = useState(null);
  
  // Hook para notificações
  const { markAsRead } = useNotifications();
  
  const messagesEndRef = useRef(null);
  const fileInputRef = useRef(null);
  const imageInputRef = useRef(null);
  const videoInputRef = useRef(null);
  const audioInputRef = useRef(null);
  const typingTimeoutRef = useRef(null);
  const otherTypingTimeoutRef = useRef(null);
  const TYPING_IDLE_MS = 800;
  const OTHER_TYPING_IDLE_MS = 1200;
  const mediaRecorderRef = useRef(null);
  const recordingTimeoutRef = useRef(null);
  const otherRecordingTimeoutRef = useRef(null);
  const OTHER_RECORDING_IDLE_MS = 15000;
  
  // Usar URL relativa (será resolvida pelo proxy do Vite)
const API_BASE = '/api';

  // ===== EFEITOS =====
  
  useEffect(() => {
    if (isOpen && selectedUser) {
      loadMessages();
      connectWebSocket();
    }
    
    return () => {
      if (ws) {
        ws.close();
      }
    };
  }, [isOpen, selectedUser]);
  
  useEffect(() => {
    scrollToBottom();
  }, [messages]);
  
  // Fechar menus ao clicar fora (corrigido para não interferir nos cliques)
  useEffect(() => {
    const handleClickOutside = (event) => {
      // Verificar se o clique foi fora dos menus
      const isFileMenuClick = event.target.closest('[data-file-menu]');
      const isEmojiMenuClick = event.target.closest('[data-emoji-menu]');
      
      if (!isFileMenuClick && showFileMenu) {
        setShowFileMenu(false);
      }
      
      if (!isEmojiMenuClick && showEmojiPicker) {
        setShowEmojiPicker(false);
      }
    };
    
    document.addEventListener('mousedown', handleClickOutside);
    return () => {
      document.removeEventListener('mousedown', handleClickOutside);
    };
  }, [showFileMenu, showEmojiPicker]);

  // ===== FUNÇÕES DE API =====
  
  const loadMessages = async () => {
    if (!selectedUser) return;
    
    try {
      setLoading(true);
      const token = localStorage.getItem('token');
      if (!token) {
        setLoading(false);
        return;
      }
      const cacheKey = `private_chat_cache_${selectedUser.id}`;
      try {
        const cached = localStorage.getItem(cacheKey);
        if (cached) {
          const parsed = JSON.parse(cached);
          if (Array.isArray(parsed) && parsed.length > 0) {
            setMessages(parsed);
          }
        }
      } catch (_) {}
      
      // Buscar TODAS as mensagens privadas entre os dois usuários
      // Implementar paginação automática para carregar todas as mensagens
      let allMessages = [];
      let page = 1;
      let hasMore = true;
      const maxPages = 10; // Proteção contra loops infinitos
      
      while (hasMore && page <= maxPages) {
        try {
          const response = await axios.get(`${API_BASE}/private-messages/`, {
        headers: { Authorization: `Token ${token}` },
        params: { 
              other_user_id: selectedUser.id,
              user_id: selectedUser.id,
              page: page
            }
          });
          
          const messagesData = response.data.results || [];
          allMessages = [...allMessages, ...messagesData];
          
          // Verificar se há mais páginas
          const totalCount = response.data.count || 0;
          const currentTotal = allMessages.length;
          
          // Parar se já carregamos todas as mensagens ou se a página está vazia
          hasMore = currentTotal < totalCount && messagesData.length > 0;
          
          console.log(`[DEBUG] Página ${page}: ${messagesData.length} mensagens, Total: ${currentTotal}/${totalCount}, HasMore: ${hasMore}`);
          
          // Parar se não há mais mensagens
          if (messagesData.length === 0) {
            hasMore = false;
          }
          
          page++;
        } catch (error) {
          console.error(`[DEBUG] Erro na página ${page}:`, error);
          try {
            const fallback = await axios.get(`${API_BASE}/private-messages/`, {
              headers: { Authorization: `Token ${token}` },
              params: { other_user_id: selectedUser.id }
            });
            const messagesData = fallback.data.results || fallback.data || [];
            allMessages = [...allMessages, ...messagesData];
          } catch (_) {}
          hasMore = false;
          break;
        }
      }
      
      allMessages.sort((a, b) => new Date(a.created_at) - new Date(b.created_at));
      const unique = [];
      const seen = new Set();
      for (const m of allMessages) {
        const id = m?.id;
        if (id && !seen.has(id)) {
          seen.add(id);
          unique.push(m);
        }
      }
      setMessages(unique);
      try { localStorage.setItem(cacheKey, JSON.stringify(unique)); } catch (_) {}
      
      // Marcar mensagens como lidas quando abrir o chat
      if (selectedUser && allMessages.length > 0) {
        markAsRead(null, selectedUser.id);
      }
      
      console.log(`Carregadas ${allMessages.length} mensagens para o chat`);
      console.log(`[DEBUG] Primeira mensagem:`, allMessages[0]);
      console.log(`[DEBUG] Última mensagem:`, allMessages[allMessages.length - 1]);
    } catch (error) {
      console.error('Erro ao carregar mensagens:', error);
    } finally {
      setLoading(false);
    }
  };
  
  // ===== WEBSOCKET =====
  
  const connectWebSocket = () => {
    if (ws && ws.readyState === WebSocket.OPEN) {
      return;
    }
    if (ws && ws.readyState !== WebSocket.CLOSED) {
      try { ws.close(); } catch (e) { void e; }
    }
    const token = localStorage.getItem('token');
    if (!token) return;
    
    const wsUrl = buildWebSocketUrl('/ws/private-chat/', { token });
    const websocket = new WebSocket(wsUrl);
    
    websocket.onopen = () => {
      
      setWs(websocket);
      
      // Marcar todas as mensagens como lidas quando conectar
      if (selectedUser) {

        websocket.send(JSON.stringify({
          type: 'join_conversation',
          other_user_id: selectedUser.id
        }));
      }
    };
    
    websocket.onmessage = (event) => {
      const data = JSON.parse(event.data);
      handleWebSocketMessage(data);
    };
    
    websocket.onclose = () => {
      
      setWs(null);
    };
    
    websocket.onerror = () => {
      // CORREÇÃO DE SEGURANÇA: Não expor token em logs
      // O erro pode conter a URL com token, mas não vamos logá-la
    };
  };
  
  const handleWebSocketMessage = (data) => {
    // Log removido para não expor dados sensíveis
    
    switch (data.type) {
      case 'new_private_message':
        // Log removido para não expor dados sensíveis
        // Adicionar nova mensagem ao chat
        {
          const cacheKey = `private_chat_cache_${selectedUser?.id}`;
          setMessages(prev => {
            const incoming = data.message;
            const incomingId = incoming?.id;
            if (incomingId && prev.some(m => m.id === incomingId)) {
              return prev;
            }
            const next = [...prev, incoming];
            try { localStorage.setItem(cacheKey, JSON.stringify(next)); } catch (_) {}
            return next;
          });
        }
        
        // Marcar como lida se o chat estiver aberto
        if (isOpen && selectedUser && data.message.sender?.id === selectedUser.id) {
          markAsRead(null, selectedUser.id);
          setOtherUserTyping(false);
          if (otherTypingTimeoutRef.current) {
            clearTimeout(otherTypingTimeoutRef.current);
            otherTypingTimeoutRef.current = null;
          }
        }
        
        // Enviar notificação se o chat não estiver aberto
        if (!isOpen || !selectedUser || data.message.sender?.id !== selectedUser.id) {
          // Notificação do navegador
          if ('Notification' in window && Notification.permission === 'granted') {
            new Notification('Nova Mensagem no Chat Interno', {
              body: `${data.message.sender?.username || 'Usuario'}: ${data.message.content}`,
              icon: '/favicon.png',
              tag: 'chat-interno'
            });
          }
          
          // Som de notificação
          try {
            const audio = new Audio('data:audio/wav;base64,UklGRnoGAABXQVZFZm10IBAAAAABAAEAQB8AAEAfAAABAAgAZGF0YQoGAACBhYqFbF1fdJivrJBhNjVgodDbq2EcBj+a2/LDciUFLIHO8tiJNwgZaLvt559NEAxQp+PwtmMcBjiR1/LMeSwFJHfH8N2QQAoUXrTp66hVFApGn+DyvmwhBSuBzvLZiTYIG2m98OScTgwOUarm7blmGgU7k9n1unEiBC13yO/eizEIHWq+8+OWT');
            audio.play().catch(() => {});
          } catch {
            console.log('Som nao disponivel');
          }
        }
        break;
        
      case 'typing_notification':
        setOtherUserTyping(data.is_typing);
        if (data.is_typing) {
          if (otherTypingTimeoutRef.current) {
            clearTimeout(otherTypingTimeoutRef.current);
          }
          otherTypingTimeoutRef.current = setTimeout(() => {
            setOtherUserTyping(false);
            otherTypingTimeoutRef.current = null;
          }, OTHER_TYPING_IDLE_MS);
        } else {
          if (otherTypingTimeoutRef.current) {
            clearTimeout(otherTypingTimeoutRef.current);
            otherTypingTimeoutRef.current = null;
          }
        }
        break;
      
      case 'recording_notification':
        setOtherUserRecording(data.is_recording);
        if (data.is_recording) {
          if (otherRecordingTimeoutRef.current) {
            clearTimeout(otherRecordingTimeoutRef.current);
          }
          otherRecordingTimeoutRef.current = setTimeout(() => {
            setOtherUserRecording(false);
            otherRecordingTimeoutRef.current = null;
          }, OTHER_RECORDING_IDLE_MS);
        } else {
          if (otherRecordingTimeoutRef.current) {
            clearTimeout(otherRecordingTimeoutRef.current);
            otherRecordingTimeoutRef.current = null;
          }
        }
        break;
        
      case 'message_read':
        setMessages(prev => prev.map(msg => 
          msg.id === data.message_id 
            ? { ...msg, is_read: true }
            : msg
        ));
        break;
    }
  };
  
  // ===== ENVIO DE MENSAGENS =====
  
  const sendMessage = async () => {
    if (!newMessage.trim()) return;
    if (!selectedUser) return;
    
    try {
      const token = localStorage.getItem('token');
      const messageData = {
        content: newMessage.trim(),
        recipient_id: selectedUser.id,
        message_type: 'text'
      };
      
      if (replyingTo) {
        messageData.reply_to_id = replyingTo.id;
      }
      
      const response = await axios.post(`${API_BASE}/private-messages/`, messageData, {
        headers: { Authorization: `Token ${token}` }
      });
      
      // Adicionar mensagem localmente para exibição imediata
      if (response.data) {
        const newMessageObj = {
          id: response.data.id || Date.now(), // Usar ID da API ou timestamp como fallback
          content: messageData.content,
          sender: { id: currentUser?.id, username: currentUser?.username, name: currentUser?.username },
          recipient: { id: selectedUser.id, username: selectedUser.username, name: selectedUser.username },
          message_type: messageData.message_type,
          created_at: new Date().toISOString(),
          is_read: false,
          reply_to: response.data.reply_to || (replyingTo ? {
            id: replyingTo.id,
            content: replyingTo.content,
            sender: replyingTo.sender,
            message_type: replyingTo.message_type
          } : undefined)
        };
        
        const cacheKey = `private_chat_cache_${selectedUser.id}`;
        setMessages(prev => {
          if (newMessageObj.id && prev.some(m => m.id === newMessageObj.id)) return prev;
          const next = [...prev, newMessageObj];
          try { localStorage.setItem(cacheKey, JSON.stringify(next)); } catch (_) {}
          return next;
        });
      }
      
      setNewMessage('');
      setReplyingTo(null);
      stopTyping();
      
    } catch (error) {
      console.error('Erro ao enviar mensagem:', error);
    }
  };
  
  const sendFileMessage = async (file, messageType) => {
    if (!selectedUser) return;
    
    try {
      const token = localStorage.getItem('token');
      const formData = new FormData();
      formData.append('file', file);
      formData.append('recipient_id', selectedUser.id);
      formData.append('message_type', messageType);
      if (replyingTo) {
        formData.append('reply_to_id', replyingTo.id);
      }
      
      const response = await axios.post(`${API_BASE}/private-messages/`, formData, {
        headers: { 
          Authorization: `Token ${token}`,
          'Content-Type': 'multipart/form-data'
        }
      });
      
      // Adicionar mensagem localmente para exibição imediata
      if (response.data) {

        const newMessageObj = {
          id: response.data.id || Date.now(),
          content: null,
          sender: { id: currentUser?.id, username: currentUser?.username, name: currentUser?.username },
          recipient: { id: selectedUser.id, username: selectedUser.username, name: selectedUser.username },
          message_type: messageType,
          file_url: response.data.file_url,
          file_name: response.data.file_name,
          file_size: response.data.file_size,
          created_at: new Date().toISOString(),
          is_read: false,
          reply_to: response.data.reply_to || (replyingTo ? {
            id: replyingTo.id,
            content: replyingTo.content,
            sender: replyingTo.sender,
            message_type: replyingTo.message_type
          } : undefined)
        };
        

        const cacheKey = `private_chat_cache_${selectedUser.id}`;
        setMessages(prev => {
          if (newMessageObj.id && prev.some(m => m.id === newMessageObj.id)) return prev;
          const next = [...prev, newMessageObj];
          try { localStorage.setItem(cacheKey, JSON.stringify(next)); } catch (_) {}
          return next;
        });
      }
      setReplyingTo(null);
      
    } catch (error) {
      console.error('Erro ao enviar arquivo:', error);
    }
  };
  
  const handleFileUpload = (event, messageType) => {
    const file = event.target.files[0];
    if (!file) return;
    
    sendFileMessage(file, messageType);
    event.target.value = '';
  };
  
  // ===== DIGITAÇÃO =====
  
  const handleInputChange = (e) => {
    setNewMessage(e.target.value);
    
    if (!isTyping && selectedUser) {
      setIsTyping(true);
      ws?.send(JSON.stringify({ 
        type: 'typing_start',
        recipient_id: selectedUser.id
      }));
    }
    
    // Reset timeout
    if (typingTimeoutRef.current) {
      clearTimeout(typingTimeoutRef.current);
    }
    
    typingTimeoutRef.current = setTimeout(stopTyping, TYPING_IDLE_MS);
  };
  
  const stopTyping = () => {
    if (isTyping && selectedUser) {
      setIsTyping(false);
      ws?.send(JSON.stringify({ 
        type: 'typing_stop',
        recipient_id: selectedUser.id
      }));
    }
    
    if (typingTimeoutRef.current) {
      clearTimeout(typingTimeoutRef.current);
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
  
  const getUserName = (user) => {
    if (!user) return 'Usuário';
    const firstName = user.first_name || '';
    const lastName = user.last_name || '';
    const fullName = `${firstName} ${lastName}`.trim();
    return fullName || user.username || user.name || 'Usuário';
  };
  
  const getUserInitials = (user) => {
    const name = getUserName(user);
    return name.split(' ').map(n => n[0]).join('').toUpperCase().slice(0, 2);
  };

  
  
  // Inferir MIME de áudio pelo sufixo da URL
  const guessMimeFromUrl = (url) => {
    const u = (url || '').toLowerCase();
    if (u.endsWith('.webm')) return 'audio/webm';
    if (u.endsWith('.ogg') || u.endsWith('.oga')) return 'audio/ogg';
    if (u.endsWith('.mp3')) return 'audio/mpeg';
    if (u.endsWith('.wav')) return 'audio/wav';
    return 'audio/*';
  };
  
  const emojis = ['👍', '❤️', '😂', '😮', '😢', '😡', '🎉', '👏', '🔥', '💯'];
  
  // ===== GRAVAÇÃO DE ÁUDIO =====
  
  const startRecording = async () => {
    try {
      if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
        alert('Gravação de áudio não é suportada neste navegador.');
        return;
      }
      const isSecure = window.location.protocol === 'https:' || 
                      window.location.hostname === 'localhost' || 
                      window.location.hostname === '127.0.0.1' ||
                      window.location.hostname.includes('ngrok');
      if (!isSecure) {
        alert('Gravação de áudio requer HTTPS ou localhost.');
        return;
      }
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      let mimeType = 'audio/webm;codecs=opus';
      if (typeof MediaRecorder !== 'undefined' && MediaRecorder.isTypeSupported) {
        if (!MediaRecorder.isTypeSupported(mimeType)) {
          if (MediaRecorder.isTypeSupported('audio/webm')) {
            mimeType = 'audio/webm';
          } else if (MediaRecorder.isTypeSupported('audio/ogg')) {
            mimeType = 'audio/ogg';
          } else {
            mimeType = '';
          }
        }
      }
      const mediaRecorder = mimeType 
        ? new MediaRecorder(stream, { mimeType }) 
        : new MediaRecorder(stream);
      const chunks = [];
      mediaRecorderRef.current = mediaRecorder;
      mediaRecorder.ondataavailable = (event) => {
        if (event.data && event.data.size > 0) {
          chunks.push(event.data);
        }
      };
      mediaRecorder.onstop = () => {
        const containerType = mimeType.includes('ogg') ? 'audio/ogg' : 'audio/webm';
        const blob = new Blob(chunks, { type: containerType });
        const ext = containerType === 'audio/ogg' ? 'ogg' : 'webm';
        const file = new File([blob], `audio-message.${ext}`, { type: containerType });
        sendFileMessage(file, 'audio');
        stream.getTracks().forEach(track => track.stop());
        if (selectedUser) {
          ws?.send(JSON.stringify({ 
            type: 'recording_stop',
            recipient_id: selectedUser.id
          }));
        }
      };
      mediaRecorder.start();
      setIsRecording(true);
      if (selectedUser) {
        ws?.send(JSON.stringify({ 
          type: 'recording_start',
          recipient_id: selectedUser.id
        }));
      }
      if (recordingTimeoutRef.current) {
        clearTimeout(recordingTimeoutRef.current);
      }
      recordingTimeoutRef.current = setTimeout(() => {
        if (mediaRecorder.state === 'recording') {
          mediaRecorder.stop();
        }
        setIsRecording(false);
      }, 10000);
    } catch (error) {
      console.error('Erro ao acessar microfone:', error);
      alert('Erro ao acessar o microfone. Verifique permissões e HTTPS.');
    }
  };

  const stopRecording = () => {
    try {
      if (recordingTimeoutRef.current) {
        clearTimeout(recordingTimeoutRef.current);
        recordingTimeoutRef.current = null;
      }
      const mr = mediaRecorderRef.current;
      if (mr && isRecording) {
        mr.stop();
        setIsRecording(false);
      }
    } catch (e) { void e; }
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-y-0 right-0 w-96 bg-card border-l border-border shadow-lg z-50 flex flex-col">
      {/* Header */}
      <div className="flex items-center justify-between p-4 border-b border-border bg-card">
        <div className="flex items-center gap-3">
          <Avatar className="h-10 w-10">
            <AvatarImage src={selectedUser?.avatar} />
            <AvatarFallback className="bg-primary text-primary-foreground">
              {selectedUser ? getUserInitials(selectedUser) : '??'}
            </AvatarFallback>
          </Avatar>
          
                      <div>
              <h3 className="font-medium text-foreground">
                {selectedUser ? getUserName(selectedUser) : 'Chat Privado'}
              </h3>
              <p className="text-xs text-muted-foreground">
                {otherUserRecording ? (
                  <span className="text-red-500 animate-pulse">🔴 Gravando áudio...</span>
                ) : otherUserTyping ? (
                  'Digitando...'
                ) : (
                  'Online'
                )}
              </p>
            </div>
        </div>
        
        <div className="flex items-center gap-1">
          <Button 
            size="sm" 
            variant="ghost" 
            onClick={onClose}
            className="h-8 w-8 p-0"
          >
            <X className="h-4 w-4" />
          </Button>
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
            {(Array.isArray(messages) ? messages : []).map(message => (
              <div key={message.id} className={`flex ${
                message.sender.id === currentUser?.id ? 'justify-end' : 'justify-start'
              }`}>
                <div
                  onContextMenu={(e) => { e.preventDefault(); setReplyingTo(message); }}
                  onMouseDown={(e) => { setDragStartX(e.clientX); setDragMsgId(message.id); }}
                  onMouseMove={(e) => {
                    if (dragStartX !== null && dragMsgId === message.id) {
                      const dx = e.clientX - dragStartX;
                      if (dx > 60) { setReplyingTo(message); setDragStartX(null); setDragMsgId(null); }
                    }
                  }}
                  onMouseUp={() => { setDragStartX(null); setDragMsgId(null); }}
                  className={`group max-w-xs lg:max-w-md px-4 py-2 rounded-lg ${
                  message.sender.id === currentUser?.id
                    ? 'bg-primary text-primary-foreground ml-4'
                    : 'bg-muted text-foreground mr-4'
                }`}
                >
                  {/* Resposta */}
                  {message.reply_to && (
                    <div
                      className={`mb-2 rounded-md px-2 py-1 border-l-4 ${
                        message.sender.id === currentUser?.id
                          ? 'border-emerald-500 bg-white/10'
                          : 'border-blue-500 bg-black/10'
                      }`}
                    >
                      <div className="flex items-start gap-2">
                        {/* Preview da imagem/vídeo - SEMPRE mostrar quando for imagem */}
                        {message.reply_to && message.reply_to.message_type === 'image' && (
                          <div className="flex-shrink-0 w-12 h-12 relative rounded overflow-hidden bg-black/10">
                            {message.reply_to.file_url ? (
                              <>
                                <img
                                  key={`reply-img-${message.reply_to.id}-${message.reply_to.file_url}`}
                                  src={buildMediaUrl(message.reply_to.file_url)}
                                  alt="Imagem"
                                  className="w-full h-full object-cover"
                                  onError={(e) => {
                                    console.error('Erro ao carregar imagem do reply:', {
                                      file_url: message.reply_to.file_url,
                                      built_url: buildMediaUrl(message.reply_to.file_url),
                                      reply_to: message.reply_to
                                    });
                                    e.target.style.display = 'none';
                                    const placeholder = e.target.nextSibling;
                                    if (placeholder) {
                                      placeholder.style.display = 'flex';
                                    }
                                  }}
                                />
                                {/* Placeholder de fallback */}
                                <div 
                                  className="absolute inset-0 bg-black/20 flex items-center justify-center"
                                  style={{ display: 'none' }}
                                >
                                  <svg className="w-6 h-6 opacity-50" fill="currentColor" viewBox="0 0 20 20">
                                    <path fillRule="evenodd" d="M4 3a2 2 0 00-2 2v10a2 2 0 002 2h12a2 2 0 002-2V5a2 2 0 00-2-2H4zm12 12H4l4-8 3 6 2-4 3 6z" clipRule="evenodd" />
                                  </svg>
                                </div>
                              </>
                            ) : (
                              <div className="w-full h-full bg-black/20 flex items-center justify-center">
                                <svg className="w-6 h-6 opacity-50" fill="currentColor" viewBox="0 0 20 20">
                                  <path fillRule="evenodd" d="M4 3a2 2 0 00-2 2v10a2 2 0 002 2h12a2 2 0 002-2V5a2 2 0 00-2-2H4zm12 12H4l4-8 3 6 2-4 3 6z" clipRule="evenodd" />
                                </svg>
                              </div>
                            )}
                          </div>
                        )}
                        {message.reply_to.message_type === 'video' && (
                          <div className="flex-shrink-0 relative w-12 h-12 bg-black/20 rounded flex items-center justify-center">
                            <svg className="w-6 h-6" fill="currentColor" viewBox="0 0 20 20">
                              <path d="M6.3 2.841A1.5 1.5 0 004 4.11V15.89a1.5 1.5 0 002.3 1.269l9.344-5.89a1.5 1.5 0 000-2.538L6.3 2.84z" />
                            </svg>
                          </div>
                        )}
                        {message.reply_to.message_type === 'audio' && (
                          <div className="flex-shrink-0 relative w-12 h-12 bg-black/20 rounded flex items-center justify-center">
                            <svg className="w-6 h-6" fill="currentColor" viewBox="0 0 20 20">
                              <path fillRule="evenodd" d="M9.383 3.076A1 1 0 0110 4v12a1 1 0 01-1.617.793L4.617 13H2a1 1 0 01-1-1V8a1 1 0 011-1h2.617l3.766-3.793a1 1 0 011.617.793zM14.657 2.929a1 1 0 011.414 0A9.972 9.972 0 0119 10a9.972 9.972 0 01-2.929 7.071 1 1 0 01-1.414-1.414A7.971 7.971 0 0017 10c0-2.21-.894-4.208-2.343-5.657a1 1 0 010-1.414zm-2.829 2.828a1 1 0 011.415 0A5.983 5.983 0 0115 10a5.984 5.984 0 01-1.757 4.243 1 1 0 01-1.415-1.415A3.984 3.984 0 0013 10a3.983 3.983 0 00-1.172-2.828 1 1 0 010-1.415z" clipRule="evenodd" />
                            </svg>
                          </div>
                        )}
                        
                        {/* Conteúdo da resposta */}
                        <div className="flex-1 min-w-0">
                          <div
                            className={`text-xs font-semibold ${
                              message.sender.id === currentUser?.id
                                ? 'text-emerald-300'
                                : 'text-blue-600'
                            }`}
                          >
                            {message.reply_to.sender ? getUserName(message.reply_to.sender) : 'Usuário'}
                          </div>
                          <div className="text-xs break-words max-h-16 overflow-hidden mt-0.5">
                            {message.reply_to.message_type === 'image' ? (
                              <span className="opacity-75">Foto</span>
                            ) : message.reply_to.message_type === 'video' ? (
                              <span className="opacity-75">Vídeo</span>
                            ) : message.reply_to.message_type === 'audio' ? (
                              <span className="opacity-75">Áudio</span>
                            ) : (
                              message.reply_to.content || `[${message.reply_to.message_type}]`
                            )}
                          </div>
                        </div>
                      </div>
                    </div>
                  )}
                  
                  {/* Conteúdo */}
          
                  
                  {/* Mensagem de texto */}
                  {message.message_type === 'text' && message.content && (
                    <p className="text-sm">{message.content}</p>
                  )}

                  {/* Removido: seta de resposta ao passar o mouse */}
                  
                  {/* Mensagem de imagem */}
                        {message.message_type === 'image' && (
        <div className="space-y-2">
          <img
            src={buildMediaUrl(message.file_url)}
            alt={message.file_name || 'Imagem'}
            className="max-w-full h-auto rounded-lg cursor-pointer hover:opacity-90 transition-opacity"
            onClick={() => window.open(buildMediaUrl(message.file_url), '_blank')}
            onError={(e) => {
              console.error('Erro ao carregar imagem:', e.target.src);
              e.target.style.display = 'none';
            }}
          />
        </div>
      )}
                  
                  {/* Mensagem de vídeo */}
                  {message.message_type === 'video' && (
                    <div className="space-y-2">
                      <video 
                        controls 
                        className="max-w-full h-auto rounded-lg"
                        src={buildMediaUrl(message.file_url)}
                      >
                        Seu navegador não suporta vídeos.
                      </video>
                    </div>
                  )}
                  
                  {/* Mensagem de áudio */}
                  {message.message_type === 'audio' && (
                    <div className="space-y-2">
                      <audio 
                        controls
                        preload="metadata"
                        className="w-[280px] max-w-full h-10 rounded-lg"
                      >
                        <source src={buildMediaUrl(message.file_url)} type={guessMimeFromUrl(message.file_url)} />
                        Seu navegador não suporta áudio.
                      </audio>
                    </div>
                  )}
                  
                  {/* Outros tipos de arquivo */}
                  {message.message_type !== 'text' && message.message_type !== 'image' && message.message_type !== 'video' && message.message_type !== 'audio' && (
                    <div className="flex items-center gap-2">
                      <Paperclip className="w-4 h-4" />
                      <a 
                        href={buildMediaUrl(message.file_url)} 
                        target="_blank" 
                        rel="noopener noreferrer"
                        className="text-sm text-primary hover:underline cursor-pointer"
                      >
                        {message.file_name || 'Arquivo'}
                      </a>
                    </div>
                  )}
                  
                  {/* Debug: mostrar informações da mensagem */}

                  
                  {/* Timestamp */}
                  <div className="text-xs opacity-75 mt-1">
                    {formatTime(message.created_at)}
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
              <span className="text-sm text-foreground">Respondendo</span>
            </div>
            <Button 
              size="sm" 
              variant="ghost"
              onClick={() => setReplyingTo(null)}
              className="h-6 w-6 p-0"
            >
              <X className="w-3 h-3" />
            </Button>
          </div>
          <div className="mt-2 rounded-md px-2 py-1 border-l-4 border-emerald-500 bg-black/10">
            <div className="text-xs font-semibold text-emerald-600">{getUserName(replyingTo.sender)}</div>
            <div className="text-xs text-muted-foreground break-words max-h-16 overflow-hidden">{replyingTo.content || `[${replyingTo.message_type}]`}</div>
          </div>
        </div>
      )}
      
      {/* Área de Input */}
      <div className="p-4 border-t border-border bg-card">
        {/* Removido - botões de arquivo agora no botão "+" */}
        
        {/* Campo de Mensagem */}
        <div className="flex items-end gap-2">
          {/* Botão "+" para Arquivos */}
          <div className="relative" data-file-menu>
            <Button 
              size="sm" 
              variant="ghost"
              onClick={(e) => {
                e.preventDefault();
                e.stopPropagation();
                console.log('Plus button clicked');
                setShowFileMenu(!showFileMenu);
              }}
              className="h-10 w-10 p-0 rounded-full"
            >
              <Plus className="w-5 h-5" />
            </Button>
            
            {/* Menu de Arquivos */}
            {showFileMenu && (
              <div className="absolute bottom-12 left-0 bg-card border border-border rounded-lg shadow-lg p-2 z-10" data-file-menu>
                <div className="flex flex-col gap-1">
                  <Button 
                    size="sm" 
                    variant="ghost"
                    onClick={() => {
                      imageInputRef.current?.click();
                      setShowFileMenu(false);
                    }}
                    className="justify-start gap-2 h-8"
                  >
                    <Image className="w-4 h-4" />
                    Foto
                  </Button>
                  
                  <Button 
                    size="sm" 
                    variant="ghost"
                    onClick={() => {
                      videoInputRef.current?.click();
                      setShowFileMenu(false);
                    }}
                    className="justify-start gap-2 h-8"
                  >
                    <Video className="w-4 h-4" />
                    Vídeo
                  </Button>
                  
                  <Button 
                    size="sm" 
                    variant="ghost"
                    onClick={() => {
                      audioInputRef.current?.click();
                      setShowFileMenu(false);
                    }}
                    className="justify-start gap-2 h-8"
                  >
                    <Mic className="w-4 h-4" />
                    Áudio
                  </Button>
                  
                  <Button 
                    size="sm" 
                    variant="ghost"
                    onClick={() => {
                      fileInputRef.current?.click();
                      setShowFileMenu(false);
                    }}
                    className="justify-start gap-2 h-8"
                  >
                    <Paperclip className="w-4 h-4" />
                    Arquivo
                  </Button>
                </div>
              </div>
            )}
          </div>
          
          {/* Campo de Texto */}
          <div className="flex-1">
            <Textarea
              value={newMessage}
              onChange={handleInputChange}
              onKeyDown={(e) => {
                if (e.key === 'Enter' && !e.shiftKey) {
                  e.preventDefault();
                  sendMessage();
                }
              }}
              placeholder="Digite uma mensagem"
              className="private-chat-textarea min-h-0 resize-none rounded-full px-4 py-2 caret-white"
              rows={1}
            />
          </div>
          
          {/* Botão Emoji */}
          <Button 
            size="sm" 
            variant="ghost"
            onClick={(e) => {
              e.preventDefault();
              e.stopPropagation();
              console.log('Emoji button clicked');
              setShowEmojiPicker(!showEmojiPicker);
            }}
            className="h-10 w-10 p-0 rounded-full"
            data-emoji-menu
          >
            <Smile className="w-5 h-5" />
          </Button>
          
          {/* Botão Principal: Mic ou Send */}
          <Button 
            onClick={(e) => {
              e.preventDefault();
              e.stopPropagation();
              console.log('Main button clicked', { hasMessage: !!newMessage.trim(), isRecording });
              if (newMessage.trim()) {
                sendMessage();
              } else {
                if (isRecording) {
                  stopRecording();
                } else {
                  startRecording();
                }
              }
            }}
            size="sm"
            className={`h-10 w-10 p-0 rounded-full transition-colors ${
              newMessage.trim() 
                ? 'bg-primary hover:bg-primary/90' 
                : isRecording 
                  ? 'bg-red-500 hover:bg-red-600 animate-pulse' 
                  : 'bg-primary hover:bg-primary/90'
            }`}
            disabled={false}
          >
            {newMessage.trim() ? (
              <Send className="w-5 h-5" />
            ) : (
              <Mic className={`w-5 h-5 ${isRecording ? 'text-white' : ''}`} />
            )}
          </Button>
        </div>
        
        {/* Emoji Picker */}
        {showEmojiPicker && (
          <div className="mt-2 p-2 bg-background border border-border rounded-lg" data-emoji-menu>
            <div className="grid grid-cols-5 gap-1">
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
          onChange={(e) => handleFileUpload(e, 'file')}
          accept=".pdf,.doc,.docx,.txt,.zip,.rar"
        />
        
        <input
          ref={imageInputRef}
          type="file"
          hidden
          onChange={(e) => handleFileUpload(e, 'image')}
          accept="image/*"
        />
        
        <input
          ref={videoInputRef}
          type="file"
          hidden
          onChange={(e) => handleFileUpload(e, 'video')}
          accept="video/*"
        />
        
        <input
          ref={audioInputRef}
          type="file"
          hidden
          onChange={(e) => handleFileUpload(e, 'audio')}
          accept="audio/*"
        />
      </div>
    </div>
  );
};

export default PrivateChatSidebar;