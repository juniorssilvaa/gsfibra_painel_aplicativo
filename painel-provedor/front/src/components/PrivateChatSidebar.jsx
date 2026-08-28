import React, { useState, useEffect, useRef } from 'react';
import { toast } from '../lib/notify';
import { createPortal } from 'react-dom';
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
  Plus,
  GripHorizontal,
  MessageCircle,
} from 'lucide-react';
import axios from 'axios';
import { buildMediaUrl } from '../config/environment';
import { useNotifications } from '../contexts/NotificationContext';
import { buildAuthenticatedWebSocketUrl } from '../utils/websocketUrl';
import useOnlineUsers from '../hooks/useOnlineUsers';

const PrivateChatSidebar = ({ 
  isOpen, 
  onClose, 
  selectedUser, 
  currentUser,
  embedded = false,
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
  const [panelPosition, setPanelPosition] = useState(null);

  // Hook para notificações
  const { markAsRead } = useNotifications();

  let isUserOnline = () => false;
  try {
    const onlineUsersHook = useOnlineUsers();
    isUserOnline = onlineUsersHook.isUserOnline || (() => false);
  } catch (_) {}

  const contactIsOnline =
    selectedUser &&
    (isUserOnline(selectedUser.id) || Boolean(selectedUser.is_online));

  const panelRef = useRef(null);
  const panelDragRef = useRef({
    active: false,
    startX: 0,
    startY: 0,
    originX: 0,
    originY: 0,
  });
  const PANEL_POS_KEY = 'private_chat_panel_position';
  const PANEL_MARGIN = 8;
  const PANEL_WIDTH = 400;
  const PANEL_HEIGHT = 560;
  const [uploadingMedia, setUploadingMedia] = useState(false);

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

  const getAuthToken = () =>
    localStorage.getItem('auth_token') || localStorage.getItem('token');

  const getPanelSize = () => {
    const el = panelRef.current;
    if (el) {
      const rect = el.getBoundingClientRect();
      return { width: rect.width, height: rect.height };
    }
    const height = Math.min(PANEL_HEIGHT, window.innerHeight - 88);
    return { width: PANEL_WIDTH, height };
  };

  const clampPanelPosition = (x, y) => {
    const { width, height } = getPanelSize();
    return {
      x: Math.min(
        Math.max(PANEL_MARGIN, x),
        window.innerWidth - width - PANEL_MARGIN
      ),
      y: Math.min(
        Math.max(PANEL_MARGIN, y),
        window.innerHeight - height - PANEL_MARGIN
      ),
    };
  };

  const getDefaultPanelPosition = () => {
    const { width, height } = getPanelSize();
    return clampPanelPosition(
      window.innerWidth - width - 16,
      window.innerHeight - height - 16
    );
  };

  const persistPanelPosition = (pos) => {
    try {
      localStorage.setItem(PANEL_POS_KEY, JSON.stringify(pos));
    } catch (_) {}
  };

  const handlePanelHeaderPointerDown = (e) => {
    if (e.button !== 0) return;
    e.preventDefault();
    const current = panelPosition || getDefaultPanelPosition();
    if (!panelPosition) {
      setPanelPosition(current);
    }
    panelDragRef.current = {
      active: true,
      startX: e.clientX,
      startY: e.clientY,
      originX: current.x,
      originY: current.y,
    };
    document.body.style.userSelect = 'none';
    document.body.style.cursor = 'grabbing';
  };

  const endPanelDrag = () => {
    if (!panelDragRef.current.active) return;
    panelDragRef.current.active = false;
    document.body.style.userSelect = '';
    document.body.style.cursor = '';
    setPanelPosition((pos) => {
      if (pos) persistPanelPosition(pos);
      return pos;
    });
  };

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
  }, [isOpen, selectedUser?.id]);

  useEffect(() => {
    if (!isOpen) return;

    let saved = null;
    try {
      const raw = localStorage.getItem(PANEL_POS_KEY);
      if (raw) saved = JSON.parse(raw);
    } catch (_) {}

    if (
      saved &&
      typeof saved.x === 'number' &&
      typeof saved.y === 'number'
    ) {
      setPanelPosition(clampPanelPosition(saved.x, saved.y));
      return;
    }

    setPanelPosition(null);
    const frame = requestAnimationFrame(() => {
      setPanelPosition(getDefaultPanelPosition());
    });
    return () => cancelAnimationFrame(frame);
  }, [isOpen, selectedUser?.id]);

  useEffect(() => {
    const onPointerMove = (e) => {
      if (!panelDragRef.current.active) return;
      const dx = e.clientX - panelDragRef.current.startX;
      const dy = e.clientY - panelDragRef.current.startY;
      setPanelPosition(
        clampPanelPosition(
          panelDragRef.current.originX + dx,
          panelDragRef.current.originY + dy
        )
      );
    };

    window.addEventListener('pointermove', onPointerMove);
    window.addEventListener('pointerup', endPanelDrag);
    window.addEventListener('pointercancel', endPanelDrag);

    return () => {
      window.removeEventListener('pointermove', onPointerMove);
      window.removeEventListener('pointerup', endPanelDrag);
      window.removeEventListener('pointercancel', endPanelDrag);
      document.body.style.userSelect = '';
      document.body.style.cursor = '';
    };
  }, []);

  useEffect(() => {
    if (!isOpen || !panelPosition) return;

    const onResize = () => {
      setPanelPosition((pos) => (pos ? clampPanelPosition(pos.x, pos.y) : pos));
    };

    window.addEventListener('resize', onResize);
    return () => window.removeEventListener('resize', onResize);
  }, [isOpen, panelPosition]);
  
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
      const token = getAuthToken();
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
          
          
          // Parar se não há mais mensagens
          if (messagesData.length === 0) {
            hasMore = false;
          }
          
          page++;
        } catch (error) {
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
      
    } catch (error) {
    } finally {
      setLoading(false);
    }
  };
  
  // ===== WEBSOCKET =====
  
  const connectWebSocket = async () => {
    if (ws && ws.readyState === WebSocket.OPEN) {
      return;
    }
    if (ws && ws.readyState !== WebSocket.CLOSED) {
      try { ws.close(); } catch (e) { void e; }
    }
    const token = getAuthToken();
    if (!token) return;
    
    const wsUrl = await buildAuthenticatedWebSocketUrl('/ws/private-chat/', { token });
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
          }
        }
        break;
        
      case 'typing':
      case 'typing_notification': {
        const fromId = data.from_user_id ?? data.sender_id;
        if (!selectedUser || Number(fromId) !== Number(selectedUser.id)) {
          break;
        }
        setOtherUserTyping(!!data.is_typing);
        if (data.is_typing) {
          if (otherTypingTimeoutRef.current) {
            clearTimeout(otherTypingTimeoutRef.current);
          }
          otherTypingTimeoutRef.current = setTimeout(() => {
            setOtherUserTyping(false);
            otherTypingTimeoutRef.current = null;
          }, OTHER_TYPING_IDLE_MS);
        } else if (otherTypingTimeoutRef.current) {
          clearTimeout(otherTypingTimeoutRef.current);
          otherTypingTimeoutRef.current = null;
        }
        break;
      }
      
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
      const token = getAuthToken();
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
    }
  };
  
  const appendMediaMessage = (data, fallbackType) => {
    if (!data?.id || !selectedUser) return;
    const resolvedType = data.message_type || fallbackType;
    const newMessageObj = {
      id: data.id,
      content: data.content || null,
      sender: data.sender || {
        id: currentUser?.id,
        username: currentUser?.username,
        name: currentUser?.username,
      },
      recipient: data.recipient || {
        id: selectedUser.id,
        username: selectedUser.username,
        name: selectedUser.username,
      },
      message_type: resolvedType,
      file_url: data.file_url,
      file_name: data.file_name,
      file_size: data.file_size,
      created_at: data.created_at || new Date().toISOString(),
      is_read: false,
      reply_to: data.reply_to,
    };

    const cacheKey = `private_chat_cache_${selectedUser.id}`;
    setMessages((prev) => {
      if (prev.some((m) => m.id === newMessageObj.id)) return prev;
      const next = [...prev, newMessageObj];
      try {
        localStorage.setItem(cacheKey, JSON.stringify(next));
      } catch (_) {}
      return next;
    });
  };

  const sendFileMessage = async (file, messageType) => {
    if (!selectedUser || !file) return;

    try {
      setUploadingMedia(true);
      const token = getAuthToken();
      if (!token) return;

      const formData = new FormData();
      formData.append('file', file, file.name || `upload.${messageType}`);
      formData.append('recipient_id', String(selectedUser.id));
      formData.append('message_type', messageType);
      if (replyingTo?.id) {
        formData.append('reply_to_id', String(replyingTo.id));
      }

      const response = await axios.post(`${API_BASE}/private-messages/`, formData, {
        headers: { Authorization: `Token ${token}` },
      });

      if (response.data?.file_url) {
        appendMediaMessage(response.data, messageType);
      } else {
        await loadMessages();
      }
      setReplyingTo(null);
    } catch (error) {
      const detail =
        error.response?.data?.content?.[0] ||
        error.response?.data?.detail ||
        error.response?.data?.file?.[0] ||
        'Não foi possível enviar o arquivo. Tente novamente.';
      toast.error(typeof detail === 'string' ? detail : 'Não foi possível enviar o arquivo.');
    } finally {
      setUploadingMedia(false);
    }
  };
  
  const handleFileUpload = (event, messageType) => {
    const file = event.target.files[0];
    if (!file) return;
    
    sendFileMessage(file, messageType);
    event.target.value = '';
  };

  const handlePasteIntoChat = (e) => {
    if (!selectedUser || uploadingMedia || isRecording) return;

    try {
      const items = e.clipboardData?.items ? Array.from(e.clipboardData.items) : [];
      const imageItem = items.find(
        (it) => it.kind === 'file' && (it.type || '').startsWith('image/')
      );

      let file = imageItem?.getAsFile?.() || null;

      if (!file && e.clipboardData?.files?.length) {
        file = Array.from(e.clipboardData.files).find((f) =>
          (f.type || '').startsWith('image/')
        );
      }

      if (!file) return;

      const ext = (file.type || 'image/png').split('/')[1] || 'png';
      const filename =
        file.name && file.name !== 'image.png'
          ? file.name
          : `captura_${Date.now()}.${ext}`;
      const imageFile = new File([file], filename, {
        type: file.type || 'image/png',
      });

      e.preventDefault();
      sendFileMessage(imageFile, 'image');
    } catch (_) {
      // Colar texto normal continua funcionando
    }
  };
  
  // ===== DIGITAÇÃO =====
  
  const sendTypingState = (typing) => {
    if (!selectedUser || !ws || ws.readyState !== WebSocket.OPEN) return;
    ws.send(JSON.stringify({
      type: 'typing',
      target_user_id: selectedUser.id,
      is_typing: typing,
    }));
  };

  const handleInputChange = (e) => {
    setNewMessage(e.target.value);

    if (!isTyping && selectedUser) {
      setIsTyping(true);
      sendTypingState(true);
    }

    if (typingTimeoutRef.current) {
      clearTimeout(typingTimeoutRef.current);
    }

    typingTimeoutRef.current = setTimeout(stopTyping, TYPING_IDLE_MS);
  };

  const stopTyping = () => {
    if (isTyping && selectedUser) {
      setIsTyping(false);
      sendTypingState(false);
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

  const formatLastSeenLabel = (iso) => {
    if (!iso) return 'Offline';
    const date = new Date(iso);
    if (Number.isNaN(date.getTime())) return 'Offline';
    const diffMin = Math.floor((Date.now() - date.getTime()) / 60000);
    if (diffMin < 1) return 'Visto agora';
    if (diffMin < 60) return `Visto há ${diffMin} min`;
    const diffH = Math.floor(diffMin / 60);
    if (diffH < 24) return `Visto há ${diffH}h`;
    return `Visto em ${date.toLocaleDateString('pt-BR', { day: '2-digit', month: '2-digit' })}`;
  };

  
  
  // Inferir MIME de áudio pelo sufixo da URL
  const guessMimeFromUrl = (url, fileName) => {
    const u = `${url || ''} ${fileName || ''}`.toLowerCase();
    if (u.includes('.webm')) return 'audio/webm';
    if (u.includes('.ogg') || u.includes('.oga')) return 'audio/ogg';
    if (u.includes('.mp3')) return 'audio/mpeg';
    if (u.includes('.wav')) return 'audio/wav';
    if (u.includes('.m4a')) return 'audio/mp4';
    return 'audio/webm';
  };

  /** Áudios gravados em .webm às vezes foram salvos como message_type=video no backend */
  const isAudioMessage = (message) => {
    if (message?.message_type === 'audio') return true;
    if (message?.message_type !== 'video') return false;
    const hint = `${message.file_name || ''} ${message.file_url || ''}`.toLowerCase();
    return (
      hint.includes('audio-message') ||
      /\.(ogg|opus|mp3|wav|m4a|aac)(\?|$)/.test(hint) ||
      (hint.includes('.webm') && !hint.includes('video'))
    );
  };
  
  const emojis = ['👍', '❤️', '😂', '😮', '😢', '😡', '🎉', '👏', '🔥', '💯'];
  
  // ===== GRAVAÇÃO DE ÁUDIO =====
  
  const startRecording = async () => {
    try {
      if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
        toast.error('Gravação de áudio não é suportada neste navegador.');
        return;
      }
      const isSecure = window.location.protocol === 'https:' || 
                      window.location.hostname === 'localhost' || 
                      window.location.hostname === '127.0.0.1' ||
                      window.location.hostname.includes('ngrok');
      if (!isSecure) {
        toast.error('Gravação de áudio requer HTTPS ou localhost.');
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
      mediaRecorder.onstop = async () => {
        if (mediaRecorder.state !== 'inactive') {
          try {
            mediaRecorder.requestData();
          } catch (_) {}
        }
        const containerType = mimeType.includes('ogg') ? 'audio/ogg' : 'audio/webm';
        const blob = new Blob(chunks, { type: containerType });
        if (!blob.size) {
          toast.error('Gravação vazia. Segure o microfone por mais tempo e tente novamente.');
          stream.getTracks().forEach((track) => track.stop());
          return;
        }
        const ext = containerType === 'audio/ogg' ? 'ogg' : 'webm';
        const file = new File([blob], `audio-message.${ext}`, { type: containerType });
        await sendFileMessage(file, 'audio');
        stream.getTracks().forEach(track => track.stop());
        if (selectedUser) {
          ws?.send(JSON.stringify({ 
            type: 'recording_stop',
            recipient_id: selectedUser.id
          }));
        }
      };
      mediaRecorder.start(250);
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
      toast.error('Erro ao acessar o microfone. Verifique permissões e HTTPS.');
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
        if (mr.state === 'recording') {
          try {
            mr.requestData();
          } catch (_) {}
          mr.stop();
        }
        setIsRecording(false);
      }
    } catch (e) { void e; }
  };

  if (!isOpen && !embedded) return null;

  if (embedded && !selectedUser) {
    return (
      <div className="flex flex-1 min-h-0 flex-col items-center justify-center bg-background/90 p-8 text-center">
        <MessageCircle className="mb-3 h-14 w-14 text-muted-foreground/30" />
        <p className="text-sm font-medium text-foreground">Chat interno da equipe</p>
        <p className="mt-1 max-w-[220px] text-xs text-muted-foreground">
          Selecione um colega na lista para iniciar ou continuar uma conversa.
        </p>
      </div>
    );
  }

  if (!embedded && !isOpen) return null;

  const panelStyle = embedded
    ? undefined
    : panelPosition
      ? { left: panelPosition.x, top: panelPosition.y }
      : { right: 16, bottom: 16 };

  const outerClassName = embedded
    ? 'flex flex-1 min-h-0 min-w-0 flex-col bg-card'
    : 'fixed z-[200] flex w-[400px] max-w-[calc(100vw-2rem)] h-[min(560px,calc(100vh-4rem))] max-h-[calc(100vh-4rem)] flex-col rounded-xl border border-border bg-card shadow-2xl';

  const panel = (
    <div
      ref={embedded ? null : panelRef}
      style={panelStyle}
      className={outerClassName}
      role="dialog"
      aria-label="Chat interno"
    >
      {/* Header */}
      <div
        className={`flex items-center justify-between px-2 py-2 border-b border-border bg-card shrink-0 ${
          embedded ? '' : 'cursor-grab active:cursor-grabbing select-none'
        }`}
        onPointerDown={embedded ? undefined : handlePanelHeaderPointerDown}
      >
        {!embedded && (
          <GripHorizontal className="h-4 w-4 shrink-0 text-muted-foreground/70 mx-1" aria-hidden />
        )}
        <div className="flex items-center gap-2 min-w-0 flex-1">
          <Avatar className="h-7 w-7 shrink-0">
            <AvatarImage src={selectedUser?.avatar} />
            <AvatarFallback className="bg-primary text-primary-foreground">
              {selectedUser ? getUserInitials(selectedUser) : '??'}
            </AvatarFallback>
          </Avatar>
          
                      <div className="min-w-0">
              <h3 className="font-medium text-sm text-foreground truncate">
                {selectedUser ? getUserName(selectedUser) : 'Chat Privado'}
              </h3>
              <p className="text-[11px] text-muted-foreground truncate">
                {otherUserRecording ? (
                  <span className="text-red-500 animate-pulse">🔴 Gravando áudio...</span>
                ) : otherUserTyping ? (
                  'Digitando...'
                ) : contactIsOnline ? (
                  'Online'
                ) : selectedUser?.last_seen ? (
                  formatLastSeenLabel(selectedUser.last_seen)
                ) : (
                  'Offline'
                )}
              </p>
            </div>
        </div>
        
        <div className="flex items-center gap-1 shrink-0">
          {!embedded && (
          <Button 
            size="sm" 
            variant="ghost" 
            onClick={onClose}
            onPointerDown={(e) => e.stopPropagation()}
            className="h-8 w-8 p-0 cursor-pointer"
          >
            <X className="h-4 w-4" />
          </Button>
          )}
        </div>
      </div>
      
      {/* Área de Mensagens */}
      <div className="flex-1 min-h-0 overflow-y-auto overflow-x-hidden px-2 py-2 bg-background rounded-none">
        {loading ? (
          <div className="flex justify-center items-center h-full">
            <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary"></div>
          </div>
        ) : (
          <div className="space-y-2">
            {(Array.isArray(messages) ? messages : []).map(message => (
              <div key={message.id} className={`flex ${
                message.sender?.id === currentUser?.id ? 'justify-end' : 'justify-start'
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
                  className={`group max-w-[90%] px-2.5 py-1 rounded-lg text-xs ${
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
            className="max-w-full h-auto rounded-lg cursor-pointer"
            onClick={() => window.open(buildMediaUrl(message.file_url), '_blank')}
            onError={(e) => {
              e.target.style.display = 'none';
            }}
          />
        </div>
      )}
                  
                  {/* Mensagem de vídeo */}
                  {message.message_type === 'video' && !isAudioMessage(message) && message.file_url && (
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
                  {isAudioMessage(message) && (
                    <div className="private-chat-audio-wrap my-1 min-w-[200px] max-w-full">
                      {message.file_url ? (
                        <audio
                          key={`audio-${message.id}-${message.file_url}`}
                          controls
                          controlsList="nodownload"
                          preload="metadata"
                          className="private-chat-audio w-full min-h-[40px] rounded-lg"
                          src={buildMediaUrl(message.file_url)}
                        >
                          <source
                            src={buildMediaUrl(message.file_url)}
                            type={guessMimeFromUrl(message.file_url, message.file_name)}
                          />
                        </audio>
                      ) : (
                        <div className="flex items-center gap-2 text-xs opacity-80">
                          <Mic className="w-4 h-4 shrink-0" />
                          <span>Áudio indisponível</span>
                        </div>
                      )}
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

            {otherUserTyping && (
              <div className="flex justify-start">
                <div className="bg-muted text-muted-foreground text-sm px-4 py-2 rounded-lg mr-4 italic animate-pulse">
                  Digitando...
                </div>
              </div>
            )}

            <div ref={messagesEndRef} />
          </div>
        )}
      </div>

      {/* Resposta ativa */}
      {replyingTo && (
        <div className="shrink-0 px-4 py-2 bg-muted border-t border-border">
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
      
      {isRecording && (
        <div className="shrink-0 flex items-center justify-between gap-2 border-t border-red-500/40 bg-red-950/50 px-3 py-2 text-xs">
          <span className="flex items-center gap-2 text-red-400 font-medium animate-pulse">
            <span className="inline-block h-2 w-2 rounded-full bg-red-500" />
            Gravando áudio…
          </span>
          <button
            type="button"
            onClick={stopRecording}
            className="rounded-md bg-red-600 px-2.5 py-1 text-white text-xs font-medium hover:bg-red-500"
          >
            Parar e enviar
          </button>
        </div>
      )}

      {/* Área de Input */}
      <div className="shrink-0 relative z-20 overflow-visible rounded-b-xl border-t border-border bg-card px-2 py-2.5">
        {uploadingMedia && (
          <p className="text-[11px] text-muted-foreground mb-1 px-1">Enviando mídia...</p>
        )}

        {/* Campo de Mensagem */}
        <div className="flex items-center gap-1.5">
          {/* Botão "+" para Arquivos */}
          <div className="relative" data-file-menu>
            <Button 
              size="sm" 
              variant="ghost"
              disabled={uploadingMedia || isRecording}
              onClick={(e) => {
                e.preventDefault();
                e.stopPropagation();
                setShowFileMenu(!showFileMenu);
              }}
              className="h-8 w-8 p-0 rounded-full shrink-0"
            >
              <Plus className="w-3.5 h-3.5" />
            </Button>
            
            {/* Menu de Arquivos */}
            {showFileMenu && (
              <div className="absolute bottom-full left-0 mb-2 bg-card border border-border rounded-lg shadow-lg p-2 z-[250]" data-file-menu>
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
              onPaste={handlePasteIntoChat}
              onKeyDown={(e) => {
                if (e.key === 'Enter' && !e.shiftKey) {
                  e.preventDefault();
                  sendMessage();
                }
              }}
              placeholder="Digite uma mensagem"
              className="private-chat-textarea min-h-0 resize-none rounded-full px-3 py-1.5 text-sm caret-white"
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
              setShowEmojiPicker(!showEmojiPicker);
            }}
            className="h-8 w-8 p-0 rounded-full shrink-0"
            data-emoji-menu
          >
            <Smile className="w-4 h-4" />
          </Button>
          
          {/* Botão Principal: Mic ou Send */}
          <Button 
            disabled={uploadingMedia}
            onClick={(e) => {
              e.preventDefault();
              e.stopPropagation();
              if (newMessage.trim()) {
                sendMessage();
              } else if (isRecording) {
                stopRecording();
              } else {
                startRecording();
              }
            }}
            size="sm"
            className={`h-8 w-8 p-0 rounded-full shrink-0 transition-colors ${
              newMessage.trim() 
                ? 'bg-primary hover:bg-primary/90' 
                : isRecording 
                  ? 'bg-red-500 hover:bg-red-600 animate-pulse' 
                  : 'bg-primary hover:bg-primary/90'
            }`}
          >
            {newMessage.trim() ? (
              <Send className="w-4 h-4" />
            ) : (
              <Mic className={`w-4 h-4 ${isRecording ? 'text-white' : ''}`} />
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

  if (embedded) {
    return panel;
  }

  return createPortal(panel, document.body);
};

export default PrivateChatSidebar;