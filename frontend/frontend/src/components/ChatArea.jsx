import { useState, useRef, useEffect, useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Send,
  Paperclip,
  Smile,
  User,
  MessageCircle,
  Globe,
  UserCheck,
  CheckCircle2,
  ArrowRightLeft,
  Mic,
  MicOff,
  Square,
  FileText,
  Zap,
  X,
  Image,
  Music,
  Wallet,
  CreditCard,
  Calendar,
  Copy,
  Barcode,
  Database,
  Smartphone
} from 'lucide-react';
import SgpSidebar from './SgpSidebar';
import axios from 'axios';
import { toast } from 'sonner';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogPortal, DialogOverlay } from './ui/dialog';
import * as DialogPrimitive from '@radix-ui/react-dialog';
import whatsappIcon from '../assets/whatsapp.png';
import telegramIcon from '../assets/telegram.png';
import gmailIcon from '../assets/gmail.png';
import instagramIcon from '../assets/instagram.png';
import logoImage from '../assets/logo.png';
import chatBgPattern from '../assets/chat-bg-pattern.svg';
import chatBgPatternLight from '../assets/chat-bg-pattern-light.svg';
import CustomAudioPlayer from './ui/CustomAudioPlayer';
import FilePreview from './FilePreview';
import { buildMediaUrl } from '../config/environment';
import { buildWebSocketUrl } from '../utils/websocketUrl';
import { useTheme } from '../hooks/useTheme';

/** Atendente sem permissão: conversa na espera sem assignee — não exibir conteúdo até atribuir. */
function isWaitingQueueContentHiddenForAgent(conversation, user) {
  if (!conversation || !user) return false;
  if (user.user_type !== 'agent') return false;
  if (conversation.panel_waiting_content_hidden === true) return true;
  if (conversation.panel_waiting_content_hidden === false) return false;
  const perms = Array.isArray(user.permissions) ? user.permissions : [];
  if (perms.includes('view_waiting_history_before_assignment')) return false;
  if (conversation.waiting_for_agent !== true) return false;
  const aid = conversation.assignee?.id ?? conversation.assignee_id;
  if (aid != null && aid !== '' && !Number.isNaN(Number(aid))) return false;
  return true;
}

const ChatArea = ({ conversation, onConversationClose, onConversationUpdate, user }) => {
  const navigate = useNavigate();
  const isDarkTheme = useTheme();
  const authReady = !!user;

  // HOOKS DEVEM VIR ANTES DE QUALQUER RETURN CONDICIONAL (Regra dos Hooks)
  const [message, setMessage] = useState('');
  const [messages, setMessages] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  // Estado para verificar se a janela de 24 horas está aberta
  // Inicializar com o valor da prop se disponível, senão null
  const channelType = conversation?.inbox?.channel_type;
  const isWhatsAppChannel = ['whatsapp', 'whatsapp_oficial', 'whatsapp_session'].includes(channelType);
  const initialIs24hWindowOpen = isWhatsAppChannel
    ? (conversation?.is_24h_window_open ?? null)
    : true; // Para outros canais, sempre aberta

  const [is24hWindowOpen, setIs24hWindowOpen] = useState(initialIs24hWindowOpen);
  const fetchedStatusConversationIdRef = useRef(null);
  // Estado local para o nome do contato (pode ser atualizado via WebSocket)
  const [contactName, setContactName] = useState(conversation.contact?.name);
  const messagesEndRef = useRef(null);
  const scrollContainerRef = useRef(null);
  const highlightClearTimeoutRef = useRef(null);
  const [shouldAutoScroll, setShouldAutoScroll] = useState(true);
  const wsRef = useRef(null);
  /** Sempre a conversa aberta no painel — evita fetch/WS/fallback de outra conversa após troca rápida */
  const activeConversationIdRef = useRef(null);
  useEffect(() => {
    activeConversationIdRef.current = conversation?.id ?? null;
  }, [conversation?.id]);

  const conversationRef = useRef(conversation);
  const userRef = useRef(user);
  useEffect(() => {
    conversationRef.current = conversation;
  }, [conversation]);
  useEffect(() => {
    userRef.current = user;
  }, [user]);

  const hideWaitingQueueContent = useMemo(
    () => isWaitingQueueContentHiddenForAgent(conversation, user),
    [conversation, user]
  );

  const [loadingProfilePic, setLoadingProfilePic] = useState(false);
  const [showTransferDropdown, setShowTransferDropdown] = useState(false);
  const [agents, setAgents] = useState([]);
  const [agentsStatus, setAgentsStatus] = useState({});
  const [profilePicture, setProfilePicture] = useState(null);
  const [loadingAgents, setLoadingAgents] = useState(false);
  const [sendingMedia, setSendingMedia] = useState(false);

  // Estados para visualização de mídia
  const [selectedImage, setSelectedImage] = useState(null);
  const [showImageModal, setShowImageModal] = useState(false);

  // Estados para reações e exclusão
  const [showReactionPicker, setShowReactionPicker] = useState(false);
  const [selectedMessageForReaction, setSelectedMessageForReaction] = useState(null);
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);
  const [messageToDelete, setMessageToDelete] = useState(null);
  const [replyingToMessage, setReplyingToMessage] = useState(null);
  /** Destaque ao ir até a mensagem citada (clique em "Resposta a:" / "Respondendo a:") */
  const [highlightTargetMessageId, setHighlightTargetMessageId] = useState(null);

  // Estados para gravação de áudio
  const [isRecording, setIsRecording] = useState(false);
  const [recordingTime, setRecordingTime] = useState(0);
  const [audioBlob, setAudioBlob] = useState(null);
  const [audioUrl, setAudioUrl] = useState(null);
  const mediaRecorderRef = useRef(null);
  const recordingIntervalRef = useRef(null);

  // Estados para templates
  const [showTemplatesModal, setShowTemplatesModal] = useState(false);
  const [templates, setTemplates] = useState([]);
  const [loadingTemplates, setLoadingTemplates] = useState(false);
  const [sendingTemplate, setSendingTemplate] = useState(false);
  const [isCorrecting, setIsCorrecting] = useState(false);

  // Estados para reprodução de áudio
  const [playingAudio, setPlayingAudio] = useState(null);
  const [audioProgress, setAudioProgress] = useState({});
  const audioRefs = useRef({});
  const [showEmojiPicker, setShowEmojiPicker] = useState(false);
  const [showEmojiGallery, setShowEmojiGallery] = useState(false);
  const [galleryItems, setGalleryItems] = useState([]);
  const [loadingGallery, setLoadingGallery] = useState(false);
  const [showSgpSidebar, setShowSgpSidebar] = useState(() => {
    const saved = localStorage.getItem('niochat_showSgpSidebar');
    // Se não houver nada salvo, o padrão agora é FALSE (fechado)
    return saved === 'true';
  });
  const emojiPickerRef = useRef(null);
  const emojiGalleryRef = useRef(null);

  // Lista abrangente de emojis categorizada
  const emojiList = [
    // Smiles & People
    '😀', '😃', '😄', '😁', '😅', '😂', '🤣', '😊', '😇', '🙂', '🙃', '😉', '😌', '😍', '🥰', '😘', '😗', '😙', '😚', '😋', '😛', '😝', '😜', '🤪', '🤨', '🧐', '🤓', '😎', '🤩', '🥳', '😏', '😒', '😞', '😔', '😟', '😕', '🙁', '☹️', '😣', '😖', '😫', '😩', '🥺', '😢', '😭', '😤', '😠', '😡', '🤬', '🤯', '😳', '🥵', '🥶', '😱', '😨', '😰', '😥', '😓', '🤗', '🤔', '🤭', '🤫', '🤥', '😶', '😐', '😑', '😬', '🙄', '😯', '😦', '😧', '😮', '😲', '🥱', '😴', '🤤', '😪', '😵', '🤐', '🥴', '🤢', '🤮', '🤧', '😷', '🤒', '🤕', '🤑', '🤠', '😈', '👿', '👹', '👺', '🤡', '💩', '👻', '💀', '☠️', '👽', '👾', '🤖', '🎃', '😺', '😸', '😹', '😻', '😼', '😽', '🙀', '😿', '😾',
    // Hands & Body
    '👋', '🤚', '🖐️', '✋', '🖖', '👌', '🤏', '✌️', '🤞', '🤟', '🤘', '🤙', '👈', '👉', '👆', '🖕', '👇', '☝️', '👍', '👎', '✊', '👊', '🤛', '🤜', '👏', '🙌', '👐', '🤲', '🤝', '🙏', '✍️', '💅', '🤳', '💪', '🦾', '🦵', '🦿', '🦶', '👂', '🦻', '👃', '🧠', '🦷', '🦴', '👀', '👁️', '👅', '👄', '💋', '🩸',
    // Heart & Symbols
    '❤️', '🧡', '💛', '💚', '💙', '💜', '🖤', '🤍', '🤎', '💔', '❣️', '💕', '💞', '💓', '💗', '💖', '💘', '💝', '💟', '☮️', '✝️', '☪️', '🕉️', '☸️', '✡️', '🔯', '🕎', '☯️', '☦️', '🛐', '⛎', '♈', '♉', '♊', '♋', '♌', '♍', '♎', '♏', '♐', '♑', '♒', '♓',
    // Activities & Objects
    '⚽', '🏀', '🏈', '⚾', '🥎', '🎾', '🏐', '🏉', '🏓', '🏸', '🥅', '⛳', '🪁', '🏹', '🎣', '🤿', '🥊', '🥋', '🎽', '🛹', '🛼', '🛷', '⛸️', '🎿', '⛷️', '🏂', '🏋️', '🤺', '🤼', '🤸', '⛹️', '🤺', '🧗', '🚵', '🚴', '🏆', '🥇', '🥈', '🥉', '🏅', '🎖️', '🏵️', '🎗️', '🎫', '🎟️', '🎪', '🎭', '🖼️', '🎨', '🧵', '🪡', '🧶', '✨', '🎈', '🎆', '🎇', '🧨', '🧧', '🎀', '🎁', '🎂', '🎉', '🎊', '🎋', '🎍', '🎑', '🎐', '🎏', '💎'
  ];
  const [pendingMessages, setPendingMessages] = useState(new Set());
  const pendingMessagesRef = useRef(new Set());

  // Efeito para fechar seletores de emoji ao clicar fora
  useEffect(() => {
    function handleClickOutside(event) {
      const clickedOutsideEmojiPicker = emojiPickerRef.current && !emojiPickerRef.current.contains(event.target);
      const clickedOutsideEmojiGallery = emojiGalleryRef.current && !emojiGalleryRef.current.contains(event.target);

      if (clickedOutsideEmojiPicker && clickedOutsideEmojiGallery) {
        setShowEmojiPicker(false);
        setShowEmojiGallery(false);
      }
    }
    if (showEmojiPicker || showEmojiGallery) {
      document.addEventListener('mousedown', handleClickOutside);
    }
    return () => {
      document.removeEventListener('mousedown', handleClickOutside);
    };
  }, [showEmojiPicker, showEmojiGallery]);

  const addEmoji = (emoji) => {
    setMessage((prev) => prev + emoji);
    setTimeout(() => document.getElementById('message-input')?.focus(), 10);
  };

  const loadGalleryItems = async () => {
    try {
      setLoadingGallery(true);
      const token = localStorage.getItem('auth_token') || localStorage.getItem('token');
      const provedorId = conversation?.inbox?.provedor?.id || user?.provedor_id || user?.provedores_admin?.[0]?.id;

      if (!token || !provedorId) {
        setGalleryItems([]);
        return;
      }

      const res = await axios.get('/api/provider-gallery/', {
        headers: { Authorization: `Token ${token}` },
        params: { provedor: provedorId },
      });

      const data = res.data?.results || res.data || [];
      setGalleryItems(Array.isArray(data) ? data : []);
    } catch (error) {
      console.error('Erro ao carregar imagens da galeria:', error);
      setGalleryItems([]);
    } finally {
      setLoadingGallery(false);
    }
  };

  const emojiToCodepoint = (emoji) =>
    Array.from(emoji)
      .map((char) => char.codePointAt(0).toString(16))
      .filter((cp) => cp !== 'fe0f')
      .join('-');

  const createEmojiImageFile = async (emoji) => {
    const canvas = document.createElement('canvas');
    canvas.width = 256;
    canvas.height = 256;
    const ctx = canvas.getContext('2d');

    if (!ctx) throw new Error('Canvas indisponivel para gerar emoji');

    // Fundo transparente e emoji centralizado para envio como imagem.
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    ctx.font = "200px 'Apple Color Emoji', 'Segoe UI Emoji', 'Noto Color Emoji', sans-serif";
    ctx.fillText(emoji, canvas.width / 2, canvas.height / 2 + 8);

    const blob = await new Promise((resolve, reject) => {
      canvas.toBlob((generatedBlob) => {
        if (generatedBlob) resolve(generatedBlob);
        else reject(new Error('Falha ao converter emoji em imagem'));
      }, 'image/png');
    });

    return new File([blob], `emoji-${emojiToCodepoint(emoji)}.png`, { type: 'image/png' });
  };

  const handleSendEmojiImage = async (emoji) => {
    try {
      const file = await createEmojiImageFile(emoji);

      setShowEmojiGallery(false);
      await handleSendMedia(file, 'image', '');
    } catch (error) {
      console.error('Erro ao enviar emoji como imagem:', error);
      toast.error('Não foi possível enviar o emoji como imagem.');
    }
  };

  const handleSendGalleryImage = async (item) => {
    try {
      if (!item?.image_url) {
        toast.error('Imagem invalida na galeria.');
        return;
      }

      const token = localStorage.getItem('auth_token') || localStorage.getItem('token');
      const imageResponse = await axios.get(item.image_url, {
        responseType: 'blob',
        headers: token ? { Authorization: `Token ${token}` } : {},
      });

      const safeName = (item.nome || 'imagem').replace(/[^\w\s-]/g, '').trim().replace(/\s+/g, '-').toLowerCase();
      const file = new File([imageResponse.data], `${safeName || 'imagem-galeria'}.png`, {
        type: imageResponse.data.type || 'image/png',
      });

      setShowEmojiGallery(false);
      await handleSendMedia(file, 'image', item.nome || '');
    } catch (error) {
      console.error('Erro ao enviar imagem da galeria:', error);
      toast.error('Nao foi possivel enviar a imagem da galeria.');
    }
  };

  useEffect(() => {
    if (showEmojiGallery) {
      loadGalleryItems();
    }
  }, [showEmojiGallery, conversation?.inbox?.provedor?.id, user?.provedor_id]);

  // Persistir estado do Sidebar SGP
  useEffect(() => {
    localStorage.setItem('niochat_showSgpSidebar', showSgpSidebar);
  }, [showSgpSidebar]);

  // Estados para mídias pendentes (prévia antes de enviar)
  const [pendingFile, setPendingFile] = useState(null);
  const [pendingFileType, setPendingFileType] = useState(null);
  const [pendingFileCaption, setPendingFileCaption] = useState('');
  const [pendingFilePreview, setPendingFilePreview] = useState(null);

  // Respostas Rápidas
  const [quickReplies, setQuickReplies] = useState([]);
  const [showQuickReplies, setShowQuickReplies] = useState(false);
  const [quickReplyFilter, setQuickReplyFilter] = useState('');
  const [quickReplyIndex, setQuickReplyIndex] = useState(0);

  useEffect(() => {
    const fetchQuickReplies = async () => {
      try {
        const token = localStorage.getItem('auth_token') || localStorage.getItem('token');
        const provedorId = user?.provedor_id || user?.provedores_admin?.[0]?.id;
        if (!token || !provedorId) return;
        const res = await axios.get(`/api/respostas-rapidas/?provedor=${provedorId}`, {
          headers: { Authorization: `Token ${token}` }
        });
        setQuickReplies(res.data?.results || res.data || []);
      } catch (err) {
        console.error('Erro ao buscar respostas rápidas:', err);
      }
    };
    if (user) fetchQuickReplies();
  }, [user]);

  const filteredQuickReplies = quickReplies.filter(r =>
    r.titulo.toLowerCase().includes(quickReplyFilter.toLowerCase()) ||
    r.conteudo.toLowerCase().includes(quickReplyFilter.toLowerCase())
  );

  const selectQuickReply = (qr) => {
    setMessage(qr.conteudo);
    setShowQuickReplies(false);
    setTimeout(() => document.getElementById('message-input')?.focus(), 10);
  };

  const handleMessageChange = (e) => {
    const val = e.target.value;
    setMessage(val);

    if (val === '/') {
      setShowQuickReplies(true);
      setQuickReplyFilter('');
      setQuickReplyIndex(0);
    } else if (val.startsWith('/')) {
      setShowQuickReplies(true);
      setQuickReplyFilter(val.substring(1));
      setQuickReplyIndex(0);
    } else {
      setShowQuickReplies(false);
    }
  };

  // Ref para rastrear mensagens já marcadas como lidas nesta sessão
  const markedAsReadRef = useRef(new Set());

  // Função para processar conteúdo da mensagem (parsear JSON se necessário)
  const processMessageContent = (content, isFromCustomer = false) => {
    if (!content || typeof content !== 'string') {
      return content;
    }

    // Se parece ser JSON, tentar parsear
    if (content.trim().startsWith('{')) {
      try {
        // Primeiro, tentar parsear como está
        const parsed = JSON.parse(content);
        if (parsed.text) {
          return parsed.text;
        }
      } catch (e) {
        // Se falhou, tentar converter aspas simples para duplas
        try {
          const contentWithDoubleQuotes = content.replace(/'/g, '"');
          const parsed = JSON.parse(contentWithDoubleQuotes);
          if (parsed.text) {
            return parsed.text;
          }
        } catch (e2) {
          // Se ambos falharem, retornar o conteúdo original
        }
      }
    }

    return content;
  };

  //  FUNÇÃO PARA LIMPAR MENSAGENS DUPLICADAS
  const cleanDuplicateMessages = (messages) => {
    const uniqueMessages = [];
    const seenIds = new Set();

    messages.forEach(msg => {
      //  CORRIGIDO: Permitir TODAS as mensagens com ID válido
      if (msg.id && !seenIds.has(msg.id)) {
        seenIds.add(msg.id);
        uniqueMessages.push(msg);
      }
      //  CORRIGIDO: Permitir mensagens temporárias SEM ID apenas
      else if (!msg.id && (msg.isTemporary || msg.is_sending)) {
        // Verificar duplicatas por conteúdo e timestamp apenas para temporárias
        const isDuplicate = uniqueMessages.some(existingMsg => {
          if (!existingMsg.isTemporary && !existingMsg.is_sending) return false;
          const timeDiff = Math.abs(new Date(existingMsg.created_at) - new Date(msg.created_at));
          return existingMsg.content === msg.content &&
            existingMsg.is_from_customer === msg.is_from_customer &&
            timeDiff < 1000; // 1 segundo de tolerância
        });

        if (!isDuplicate) {
          uniqueMessages.push(msg);
        }
      }
      //  NOVO: Fallback para mensagens sem ID que não são temporárias (casos raros)
      else if (!msg.id && !msg.isTemporary && !msg.is_sending) {
        // Verificar se já existe uma mensagem igual por conteúdo e timestamp
        const isDuplicate = uniqueMessages.some(existingMsg => {
          const timeDiff = Math.abs(new Date(existingMsg.created_at) - new Date(msg.created_at));
          return existingMsg.content === msg.content &&
            existingMsg.is_from_customer === msg.is_from_customer &&
            timeDiff < 2000; // 2 segundos de tolerância para mensagens sem ID
        });

        if (!isDuplicate) {
          uniqueMessages.push(msg);
        }
      }
    });

    return uniqueMessages.sort((a, b) => new Date(a.created_at) - new Date(b.created_at));
  };

  // Componente para exibir ícone de status de leitura (estilo WhatsApp)
  const MessageStatusIcon = ({ message }) => {
    const status = message.additional_attributes?.last_status;
    const readAt = message.additional_attributes?.read_at;
    const deliveredAt = message.additional_attributes?.delivered_at;
    const sentAt = message.additional_attributes?.sent_at;

    // Determinar o status atual (prioridade: read > delivered > sent)
    let currentStatus = status;
    if (readAt || status === 'read') {
      currentStatus = 'read';
    } else if (deliveredAt || status === 'delivered') {
      currentStatus = 'delivered';
    } else if (sentAt || status === 'sent') {
      currentStatus = 'sent';
    }

    // Se não há status definido mas a mensagem não é temporária e tem external_id, assumir "sent"
    // (mensagem foi enviada com sucesso)
    if (!currentStatus && !message.isTemporary && (message.external_id || message.additional_attributes?.external_id)) {
      currentStatus = 'sent';
    }

    // 3️⃣ Mensagem lida pelo usuário - 2 tickets azuis bem fortes
    if (currentStatus === 'read') {
      return (
        <span className="inline-flex items-center ml-1 transition-all duration-300 ease-in-out" title="Lida">
          <svg
            width="16"
            height="12"
            viewBox="0 0 16 11"
            fill="none"
            xmlns="http://www.w3.org/2000/svg"
            className="transition-all duration-300 ease-in-out"
          >
            {/* Primeiro checkmark (atrás) - azul bem forte */}
            <path
              d="M0.5 5.5L3 8L7 4"
              stroke="#0066FF"
              strokeWidth="2.2"
              strokeLinecap="round"
              strokeLinejoin="round"
              fill="none"
            />
            {/* Segundo checkmark (frente, deslocado) - azul bem forte */}
            <path
              d="M8.5 5.5L11 8L15.5 3"
              stroke="#0066FF"
              strokeWidth="2.2"
              strokeLinecap="round"
              strokeLinejoin="round"
              fill="none"
            />
          </svg>
        </span>
      );
    }

    // 2️⃣ Mensagem entregue no celular - 2 tickets cinza bem neutros (sem tom roxo)
    if (currentStatus === 'delivered') {
      return (
        <span className="inline-flex items-center ml-1 transition-all duration-300 ease-in-out" title="Entregue">
          <svg
            width="16"
            height="12"
            viewBox="0 0 16 11"
            fill="none"
            xmlns="http://www.w3.org/2000/svg"
            className="transition-all duration-300 ease-in-out"
          >
            {/* Primeiro checkmark (atrás) - cinza claro neutro */}
            <path
              d="M0.5 5.5L3 8L7 4"
              stroke="#D1D5DB"
              strokeWidth="2.2"
              strokeLinecap="round"
              strokeLinejoin="round"
              fill="none"
            />
            {/* Segundo checkmark (frente, deslocado) - cinza médio neutro */}
            <path
              d="M8.5 5.5L11 8L15.5 3"
              stroke="#9CA3AF"
              strokeWidth="2.2"
              strokeLinecap="round"
              strokeLinejoin="round"
              fill="none"
            />
          </svg>
        </span>
      );
    }

    // 1️⃣ Mensagem enviada - 1 ticket cinza neutro (sem tom roxo)
    return (
      <span
        className="inline-flex items-center ml-1 transition-all duration-300 ease-in-out"
        title={currentStatus === 'sent' ? 'Enviada' : 'Enviando...'}
      >
        <svg
          width="12"
          height="10"
          viewBox="0 0 12 9"
          fill="none"
          xmlns="http://www.w3.org/2000/svg"
          className="transition-all duration-300 ease-in-out"
        >
          {/* Checkmark único cinza neutro (sem tom roxo) */}
          <path
            d="M1 4.5L4.5 8L11 1.5"
            stroke="#9CA3AF"
            strokeWidth="2.4"
            strokeLinecap="round"
            strokeLinejoin="round"
            fill="none"
          />
        </svg>
      </span>
    );
  };

  // Função para renderizar ícone do canal
  const getChannelIcon = (channelType) => {
    switch (channelType) {
      case 'whatsapp':
      case 'whatsapp_oficial':
        return <img src={whatsappIcon} alt="WhatsApp" className="w-3 h-3" />;
      case 'telegram':
        return <img src={telegramIcon} alt="Telegram" className="w-3 h-3" />;
      case 'email':
        return <img src={gmailIcon} alt="Gmail" className="w-3 h-3" />;
      case 'instagram':
        return <img src={instagramIcon} alt="Instagram" className="w-3 h-3" />;
      case 'webchat':
        return <Globe className="w-3 h-3 text-cyan-500" />;
      default:
        return <MessageCircle className="w-3 h-3 text-muted-foreground" />;
    }
  };

  // Função para obter nome limpo do canal
  const getChannelDisplayName = (inbox) => {
    if (!inbox) return 'Canal';

    // Priorizar o nome customizado se existir
    if (inbox.custom_name) {
      return inbox.custom_name;
    }

    // Fallback para o nome do inbox (preenchido no backend)
    // Se o nome não for genérico/vazio, usar ele
    if (inbox.name && 
        inbox.name !== 'whatsapp_oficial' && 
        inbox.name !== 'WhatsApp Oficial' &&
        !inbox.name.includes('WhatsApp - null')) {
      return inbox.name;
    }

    const channelTypes = {
      'whatsapp': 'WhatsApp',
      'email': 'Email',
      'telegram': 'Telegram',
      'webchat': 'Chat Web',
      'facebook': 'Facebook',
      'instagram': 'Instagram',
      'whatsapp_oficial': 'WhatsApp Oficial'
    };

    return channelTypes[inbox.channel_type] || inbox.channel_type || 'Canal';
  };

  // Função para buscar mensagens
  const fetchMessages = async () => {
    if (!conversation) return;
    const requestedConversationId = conversation.id;
    setMessages([]);
    setLoading(true);
    setError('');
    // Priorizar auth_token que é o padrão salvo no Login, mas aceitar token também para compatibilidade
    const token = localStorage.getItem('auth_token') || localStorage.getItem('token');
    try {
      // Buscar TODAS as mensagens da conversa com paginação automática
      let allMessages = [];
      let page = 1;
      let hasMore = true;
      const maxPages = 20; // Proteção contra loops infinitos (máx 200k mensagens)

      while (hasMore && page <= maxPages) {
        const res = await axios.get(`/api/messages/?conversation=${requestedConversationId}&page_size=10000&ordering=created_at&page=${page}`, {
          headers: { Authorization: `Token ${token}` }
        });

        const pageMessages = res.data.results || (Array.isArray(res.data) ? res.data : []);
        allMessages = [...allMessages, ...pageMessages];

        // Verificar se há mais páginas
        hasMore = res.data.next !== null && pageMessages.length > 0;
        page++;

        // Parar se não há mais mensagens
        if (pageMessages.length === 0) {
          hasMore = false;
        }
      }

      // Processar todas as mensagens sem filtros desnecessários
      const processedMessages = allMessages.map(msg => {
        let processedContent = processMessageContent(msg.content, msg.is_from_customer);

        //  Remover assinatura do agente se presente
        if (processedContent && processedContent.match(/\*.*disse:\*\n/) && !msg.is_from_customer) {
          processedContent = processedContent.replace(/\*.*disse:\*\n/, '');
        }

        // CORREÇÃO: Identificar mensagens da IA de forma mais robusta
        // Verificar from_ai do serializer, additional_attributes.from_ai, ou sender.sender_type
        const isFromAI = msg.from_ai === true ||
          msg.additional_attributes?.from_ai === true ||
          msg.sender?.sender_type === 'ai';

        return {
          ...msg,
          content: processedContent,
          // Garantir que campos do serializer estejam presentes
          sender: msg.sender || (!msg.is_from_customer && isFromAI ? { sender_type: 'ai' } : { sender_type: 'agent' }),
          from_ai: isFromAI  // CORREÇÃO: Usar verificação robusta
        };
      });

      if (Number(activeConversationIdRef.current) !== Number(requestedConversationId)) {
        return;
      }
      setMessages(processedMessages);
    } catch (err) {
      if (Number(activeConversationIdRef.current) === Number(requestedConversationId)) {
        setError('Erro ao carregar mensagens.');
        console.error('Erro ao buscar mensagens:', err);
      }
    } finally {
      if (Number(activeConversationIdRef.current) === Number(requestedConversationId)) {
        setLoading(false);
      }
    }
  };

  // Atualizar estado local do nome do contato quando a conversa mudar
  useEffect(() => {
    setContactName(conversation.contact?.name);

    // NÃO definir estado inicial baseado na prop conversation
    // Sempre buscar do backend para garantir dados atualizados
    // Isso evita usar dados antigos que podem estar na prop

    // Buscar conversa atualizada do backend para garantir dados corretos (especialmente status da janela de 24h)
    const fetchConversationStatus = async () => {
      if (!conversation?.id) return;

      try {
        const token = localStorage.getItem('auth_token') || localStorage.getItem('token');
        if (!token) return;

        const response = await axios.get(`/api/conversations/${conversation.id}/`, {
          headers: { Authorization: `Token ${token}` }
        });

        if (response.data) {
          const updatedConversation = response.data;

          // Atualizar status da janela de 24 horas
          // IMPORTANTE: Sempre usar o valor calculado pelo backend (is_24h_window_open)
          // que busca a mensagem mais recente do cliente e usa o created_at real
          const currentIsWhatsApp = ['whatsapp', 'whatsapp_oficial', 'whatsapp_session'].includes(channelType);
          if (currentIsWhatsApp) {

            // O backend sempre retorna is_24h_window_open calculado corretamente
            // usando o created_at da mensagem mais recente do cliente
            if (updatedConversation.is_24h_window_open !== undefined) {
              setIs24hWindowOpen(updatedConversation.is_24h_window_open);
            } else {
              // Fallback: se não veio do backend, assumir fechada para segurança
              console.warn(`[ChatArea] is_24h_window_open não veio do backend para conversa ${conversation.id}, assumindo fechada`);
              setIs24hWindowOpen(false);
            }
          } else {
            setIs24hWindowOpen(true);
          }
        }
      } catch (error) {
        // Após encerrar, a conversa pode ser migrada/removida da base ativa.
        // Nesses casos, 404 significa que ela já não está mais disponível para atendimento.
        if (error.response?.status === 404) {
          localStorage.removeItem('selectedConversation');
          if (onConversationUpdate) {
            onConversationUpdate(null);
          }
          if (onConversationClose) {
            onConversationClose();
          }
          return;
        }

        console.error('Erro ao buscar status da conversa:', error);
        // Em caso de erro, usar dados da conversa que já temos como último recurso
        // Mas sempre priorizar o valor calculado pelo backend
        if (conversation) {
          const currentIsWhatsApp = ['whatsapp', 'whatsapp_oficial', 'whatsapp_session'].includes(channelType);
          if (currentIsWhatsApp) {

            // Usar o valor do backend se disponível, senão assumir fechada
            if (conversation.is_24h_window_open !== undefined) {
              console.log(`[ChatArea] Usando valor da prop conversation como fallback: ${conversation.is_24h_window_open}`);
              setIs24hWindowOpen(conversation.is_24h_window_open);
            } else {
              console.warn(`[ChatArea] Nenhum valor disponível, assumindo janela fechada`);
              setIs24hWindowOpen(false);
            }
          } else {
            setIs24hWindowOpen(true);
          }
        }
      }
    };

    // Buscar conversa atualizada quando a conversa mudar
    // IMPORTANTE: Sempre buscar do backend, não usar valores da prop que podem estar desatualizados
    if (conversation?.id && fetchedStatusConversationIdRef.current !== conversation.id) {
      fetchedStatusConversationIdRef.current = conversation.id;
      fetchConversationStatus();
    }
  }, [conversation?.id]);

  // Buscar mensagens ao abrir conversa ou quando deixa de haver bloqueio (ex.: após atribuir)
  useEffect(() => {
    fetchMessages();
  }, [
    conversation?.id,
    conversation?.assignee?.id,
    conversation?.assignee_id,
    conversation?.waiting_for_agent,
    conversation?.panel_waiting_content_hidden,
  ]);

  useEffect(() => {
    if (highlightClearTimeoutRef.current) {
      window.clearTimeout(highlightClearTimeoutRef.current);
      highlightClearTimeoutRef.current = null;
    }
    setHighlightTargetMessageId(null);
  }, [conversation?.id]);

  // Função para marcar mensagem como lida no WhatsApp
  const markMessageAsRead = async (messageId) => {
    try {
      // Priorizar auth_token que é o padrão salvo no Login, mas aceitar token também para compatibilidade
      const token = localStorage.getItem('auth_token') || localStorage.getItem('token');
      if (!token) return;

      await axios.post('/api/messages/mark_as_read/', {
        message_id: messageId
      }, {
        headers: { Authorization: `Token ${token}` }
      });
    } catch (error) {
      // Silenciar erros - não é crítico se falhar
      console.error('Erro ao marcar mensagem como lida:', error);
    }
  };

  // Marcar mensagens do cliente como lidas quando a conversa estiver aberta (apenas WhatsApp)
  useEffect(() => {
    // Só marcar como lida se:
    // 1. A conversa estiver aberta e carregada
    // 2. For uma conversa do WhatsApp
    // 3. Tiver mensagens carregadas
    // 4. O usuário for o atendente atribuído (assignee)
    if (!conversation || !conversation.id || messages.length === 0) return;

    // SEGURANÇA: Apenas o atendente atribuído marca como lida para evitar tempestade de requisições
    const currentUserId = user?.id;
    const assigneeId = conversation.assignee?.id || conversation.assignee_id;

    if (user?.user_type !== 'superadmin' && assigneeId && assigneeId !== currentUserId) {
      return;
    }

    const channelType = conversation.inbox?.channel_type;
    if (channelType !== 'whatsapp') return;

    // Limpar o ref quando mudar de conversa
    if (!markedAsReadRef.current.has(`conversation_${conversation.id}`)) {
      markedAsReadRef.current.clear();
      markedAsReadRef.current.add(`conversation_${conversation.id}`);
    }

    // Usar um timeout para aguardar o carregamento completo das mensagens
    const timeoutId = setTimeout(() => {
      // Filtrar mensagens do cliente que ainda não foram marcadas como lidas
      const unreadMessages = messages.filter((msg) => {
        const alreadyMarkedInSession = markedAsReadRef.current.has(msg.id);
        const alreadyMarkedPreviously = msg.additional_attributes?.marked_as_read_at;

        return (
          msg.is_from_customer &&
          msg.id &&
          msg.external_id &&
          !alreadyMarkedInSession &&
          !alreadyMarkedPreviously
        );
      });

      if (unreadMessages.length > 0) {
        // OTIMIZAÇÃO: Marcar apenas a ÚLTIMA mensagem como lida.
        // A API da Meta marcará automaticamente todas as anteriores.
        // Isso reduz N requisições para apenas 1 por lote de mensagens.
        const lastUnreadMsg = unreadMessages[unreadMessages.length - 1];

        // Registrar todas no ref para evitar novas tentativas neste ciclo
        unreadMessages.forEach(msg => markedAsReadRef.current.add(msg.id));

        // Chamar o backend apenas para a última
        markMessageAsRead(lastUnreadMsg.id);
      }
    }, 1500); // Aguardar 1.5s após o carregamento das mensagens

    return () => {
      clearTimeout(timeoutId);
    };
  }, [conversation?.id, messages.length, user?.id]);



  // Monitorar status dos usuários via WebSocket (tempo real)
  useEffect(() => {
    if (!showTransferDropdown || !agents.length) return;

    // Priorizar auth_token que é o padrão salvo no Login, mas aceitar token também para compatibilidade
    const token = localStorage.getItem('auth_token') || localStorage.getItem('token');
    if (!token) return;

    const wsUrl = buildWebSocketUrl('/ws/user_status/', { token });
    const ws = new WebSocket(wsUrl);

    ws.onopen = () => {
      // Buscar status inicial via API apenas uma vez
      axios.get('/api/users/status/', {
        headers: { Authorization: `Token ${token}` }
      }).then(response => {
        if (response.data && response.data.users) {
          const statusUpdates = {};
          response.data.users.forEach(user => {
            statusUpdates[user.id] = user.is_online;
          });
          setAgentsStatus(prev => ({ ...prev, ...statusUpdates }));
        }
      }).catch(() => { });
    };

    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        if (data.type === 'user_status_update' && data.user_id) {
          setAgentsStatus(prev => ({
            ...prev,
            [data.user_id]: data.is_online
          }));
        }
      } catch (_) { }
    };

    ws.onerror = () => { };
    ws.onclose = () => {
      // Reconectar após 5 segundos se ainda precisar
      if (showTransferDropdown) {
        setTimeout(() => {
          if (showTransferDropdown) {
            ws.close();
          }
        }, 5000);
      }
    };

    return () => {
      if (ws.readyState === WebSocket.OPEN) {
        ws.close();
      }
    };
  }, [showTransferDropdown, agents]);

  //  WebSocket CORRIGIDO - Melhor controle de duplicatas
  useEffect(() => {
    if (!conversation || !conversation.id) return;

    let reconnectAttempts = 0;
    const MAX_RECONNECT_ATTEMPTS = 10;
    let shouldReconnect = true;
    let reconnectTimeout = null;

    const connectWebSocket = async () => {
      // OTIMIZAÇÃO: Não fazer GET de validação antes de conectar
      // O WebSocket vai falhar naturalmente se a conversa não existir
      // Isso evita chamadas HTTP desnecessárias

      // Priorizar auth_token que é o padrão salvo no Login, mas aceitar token também para compatibilidade
      const token = localStorage.getItem('auth_token') || localStorage.getItem('token');
      if (!token) return;

      // Fechar conexão anterior se existir
      if (wsRef.current && wsRef.current.readyState !== WebSocket.CLOSED) {
        wsRef.current.close();
      }

      const wsUrl = buildWebSocketUrl(`/ws/conversations/${conversation.id}/`, { token });
      const ws = new window.WebSocket(wsUrl);
      wsRef.current = ws;

      ws.onopen = () => {
        // WebSocket conectado - resetar tentativas
        reconnectAttempts = 0;
        shouldReconnect = true;
      };

      ws.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);
          
          if (process.env.NODE_ENV === 'development') {
            console.log('[WebSocket] Evento recebido:', {
              type: data.type,
              message_id: data.message?.id,
              action: data.action,
              has_conversation: !!data.conversation
            });
          }
          // WebSocket recebeu dados

          if (data.type === 'message' || data.type === 'chat_message' || data.type === 'message_created' || data.type === 'message_received') {
            if (data.message) {
              const __expectedConv = activeConversationIdRef.current;
              const __mc = data.message.conversation;
              const __incomingConv =
                __mc != null
                  ? typeof __mc === 'object' && __mc != null
                    ? Number(__mc.id)
                    : Number(__mc)
                  : data.conversation_id != null
                    ? Number(data.conversation_id)
                    : null;
              const __wsConvMismatch =
                __incomingConv != null &&
                !Number.isNaN(__incomingConv) &&
                __expectedConv != null &&
                !Number.isNaN(Number(__expectedConv)) &&
                Number(__expectedConv) !== __incomingConv;
              if (__wsConvMismatch) {
                if (process.env.NODE_ENV === 'development') {
                  console.warn('[WebSocket] Ignorando mensagem de outra conversa', {
                    incoming: __incomingConv,
                    active: __expectedConv,
                  });
                }
              }
              if (!__wsConvMismatch) {
              if (isWaitingQueueContentHiddenForAgent(conversationRef.current, userRef.current)) {
                return;
              }
              // Atualizar nome do contato se vier no payload da mensagem
              if (data.message.contact_name && data.message.contact_name.trim()) {
                setContactName(data.message.contact_name.trim());
                // Notificar componente pai sobre atualização (se necessário)
                if (onConversationUpdate && conversation.contact) {
                  const updatedConversation = {
                    ...conversation,
                    contact: {
                      ...conversation.contact,
                      name: data.message.contact_name.trim()
                    }
                  };
                  onConversationUpdate(updatedConversation);
                }
              }

              setMessages(currentMessages => {
                if (
                  __incomingConv != null &&
                  !Number.isNaN(__incomingConv) &&
                  activeConversationIdRef.current != null &&
                  Number(activeConversationIdRef.current) !== __incomingConv
                ) {
                  return currentMessages;
                }

                // VERIFICAÇÃO DE DUPLICATAS (ID real ou temp_id)
                const messageExists = currentMessages.some(m => 
                  (m.id && m.id === data.message.id) || 
                  (m.temp_id && m.temp_id === data.message.temp_id)
                );

                if (messageExists) {
                  if (process.env.NODE_ENV === 'development') {
                    console.log(`[WebSocket] Mensagem ${data.message.id} já existe no estado. Ignorando.`);
                  }
                  return currentMessages;
                }

                const cutoffIso = conversation?.additional_attributes?.agent_chat_visible_from;
                if (cutoffIso && data.message?.created_at) {
                  const tMsg = new Date(data.message.created_at).getTime();
                  const tCut = new Date(cutoffIso).getTime();
                  if (!Number.isNaN(tMsg) && !Number.isNaN(tCut) && tMsg < tCut) {
                    return currentMessages;
                  }
                }

                if (process.env.NODE_ENV === 'development') {
                  console.log(`[WebSocket] Adicionando nova mensagem: ${data.message.id}`);
                }
                  let processedContent = processMessageContent(data.message.content, data.message.is_from_customer);

                  //  Remover assinatura do agente se presente (WebSocket)
                  if (processedContent && processedContent.match(/\*.*disse:\*\n/) && !data.message.is_from_customer) {
                    processedContent = processedContent.replace(/\*.*disse:\*\n/, '');
                  }

                  // CORREÇÃO: Identificar mensagens da IA de forma mais robusta
                  const isFromAI = data.message.from_ai === true ||
                    data.message.additional_attributes?.from_ai === true ||
                    data.message.sender?.sender_type === 'ai' ||
                    data.sender === 'ai';

                  const processedMessage = {
                    ...data.message,
                    content: processedContent,
                    // Garantir que mensagens da IA sejam identificadas corretamente
                    sender: data.message.sender || (isFromAI ? { sender_type: 'ai' } : { sender_type: 'agent' }),
                    from_ai: isFromAI  // CORREÇÃO: Usar verificação robusta
                  };

                  // Se a mensagem é do cliente e é WhatsApp, reabrir a janela de 24 horas
                  if (processedMessage.is_from_customer && (conversation?.inbox?.channel_type === 'whatsapp' || conversation?.inbox?.channel_type === 'whatsapp_oficial')) {
                    // Se a conversa atualizada foi enviada no evento, usar os dados dela
                    if (data.conversation) {
                      const updatedConversation = data.conversation;

                      // Atualizar a conversa no componente pai se callback disponível
                      if (onConversationUpdate) {
                        onConversationUpdate(updatedConversation);
                      }

                      // Atualizar status da janela de 24 horas
                      if (updatedConversation.is_24h_window_open !== undefined) {
                        setIs24hWindowOpen(updatedConversation.is_24h_window_open);
                      } else {
                        // Se não veio do backend, assumir fechada para segurança
                        // O backend sempre deve retornar is_24h_window_open calculado corretamente
                        setIs24hWindowOpen(false);
                      }
                    } else {
                      // Se não veio a conversa no evento, buscar do backend para garantir dados atualizados
                      const fetchUpdatedConversation = async () => {
                        try {
                          const token = localStorage.getItem('auth_token') || localStorage.getItem('token');
                          const response = await axios.get(`/api/conversations/${conversation.id}/`, {
                            headers: { Authorization: `Token ${token}` }
                          });

                          if (response.data) {
                            const updatedConversation = response.data;
                            if (onConversationUpdate) {
                              onConversationUpdate(updatedConversation);
                            }

                            // Atualizar status da janela
                            // Sempre usar o valor calculado pelo backend
                            if (updatedConversation.is_24h_window_open !== undefined) {
                              setIs24hWindowOpen(updatedConversation.is_24h_window_open);
                            } else {
                              // Se não veio do backend, assumir fechada para segurança
                              setIs24hWindowOpen(false);
                            }
                          }
                        } catch (error) {
                          console.error('Erro ao buscar conversa atualizada:', error);
                          // Fallback: assumir que está aberta quando cliente envia mensagem
                          setIs24hWindowOpen(true);
                        }
                      };

                      // Buscar conversa atualizada do backend
                      fetchUpdatedConversation();
                    }
                    setError(''); // Limpar erro se houver
                  }

                  //  Remover das mensagens pendentes se existir
                  setPendingMessages(prev => {
                    const newSet = new Set(prev);
                    // Remover a mensagem original (sem assinatura) das pendentes
                    const originalContent = processedMessage.content.replace(/\*.*disse:\*\n/, '');
                    newSet.delete(originalContent);
                    pendingMessagesRef.current.delete(originalContent);
                    return newSet;
                  });

                  //  Remover mensagens temporárias relacionadas
                  const filteredMessages = currentMessages.filter(m => {
                    // Remover mensagens temporárias com conteúdo similar
                    if (m.isTemporary || m.is_sending) {
                      const originalContent = processedMessage.content.replace(/\*.*disse:\*\n/, '');
                      return !(m.content === originalContent &&
                        m.is_from_customer === processedMessage.is_from_customer);
                    }
                    return true;
                  });

                  return [...filteredMessages, processedMessage].sort((a, b) =>
                    new Date(a.created_at) - new Date(b.created_at)
                  );
              });
              }
            }
          }

          // Atualização de reação em tempo real (via webhook)
          if (data.type === 'message_updated' && data.action === 'reaction_updated') {
            // Quando a reação vem do cliente via webhook, atualizar apenas a mensagem específica
            // Evitar recarregar toda a lista para não causar polling desnecessário
            if (data.message_id && data.reaction) {
              setMessages(currentMessages =>
                currentMessages.map(msg =>
                  msg.id === data.message_id
                    ? { ...msg, reaction: data.reaction }
                    : msg
                )
              );
            }
          }

          // Handler para eventos de reação via WebSocket
          if (data.type === 'message_reaction' && data.message_id && data.reaction) {
            setMessages(currentMessages =>
              currentMessages.map(msg => {
                if (msg.id === data.message_id) {
                  // Atualizar o campo reactions (array) do backend
                  const existingReactions = msg.reactions || [];
                  const reactionExists = existingReactions.some(r =>
                    r.id === data.reaction.id ||
                    (r.emoji === data.reaction.emoji && r.is_from_customer === data.reaction.is_from_customer)
                  );

                  if (!reactionExists) {
                    // Adicionar nova reação ao array
                    return {
                      ...msg,
                      reactions: [...existingReactions, data.reaction]
                    };
                  } else {
                    // Atualizar reação existente
                    return {
                      ...msg,
                      reactions: existingReactions.map(r =>
                        (r.id === data.reaction.id ||
                          (r.emoji === data.reaction.emoji && r.is_from_customer === data.reaction.is_from_customer))
                          ? data.reaction
                          : r
                      )
                    };
                  }
                }
                return msg;
              })
            );
          }

          // Atualização de status de mensagem (sent, delivered, read)
          if (data.type === 'message_status_update' && data.message_id && data.status) {
            setMessages(currentMessages =>
              currentMessages.map(msg => {
                if (msg.id === data.message_id) {
                  // Atualizar additional_attributes com o novo status
                  const updatedAttrs = {
                    ...(msg.additional_attributes || {}),
                    last_status: data.status,
                    last_status_timestamp: data.timestamp
                  };

                  // Adicionar campos específicos por status
                  if (data.status === 'read') {
                    updatedAttrs.read_at = data.timestamp;
                    updatedAttrs.read_by = data.recipient_id;
                  } else if (data.status === 'delivered') {
                    updatedAttrs.delivered_at = data.timestamp;
                  } else if (data.status === 'sent') {
                    updatedAttrs.sent_at = data.timestamp;
                  }

                  // Atualizar histórico de status
                  const statusHistory = updatedAttrs.status_history || [];
                  statusHistory.push({
                    status: data.status,
                    timestamp: data.timestamp,
                    recipient_id: data.recipient_id
                  });
                  updatedAttrs.status_history = statusHistory;

                  return {
                    ...msg,
                    additional_attributes: updatedAttrs
                  };
                }
                return msg;
              })
            );
          }

          if (data.type === 'conversation_updated') {
            // Conversa atualizada via WebSocket
            const updatedConversation = data.conversation || conversation;

            const wasHidden = isWaitingQueueContentHiddenForAgent(conversationRef.current, userRef.current);
            const nowHidden = isWaitingQueueContentHiddenForAgent(updatedConversation, userRef.current);

            // Atualizar status da janela de 24 horas se a conversa foi atualizada
            if (updatedConversation) {
              const channelType = updatedConversation.inbox?.channel_type;
              if (channelType === 'whatsapp' || channelType === 'whatsapp_oficial') {
                // Sempre usar o valor calculado pelo backend
                if (updatedConversation.is_24h_window_open !== undefined) {
                  setIs24hWindowOpen(updatedConversation.is_24h_window_open);
                } else {
                  // Se não veio do backend, assumir fechada para segurança
                  setIs24hWindowOpen(false);
                }
              } else {
                // Para outros canais, janela sempre aberta
                setIs24hWindowOpen(true);
              }
            }

            if (onConversationUpdate) {
              onConversationUpdate(updatedConversation);
            }

            if (wasHidden && !nowHidden) {
              fetchMessages();
            }

            const visCut = updatedConversation?.additional_attributes?.agent_chat_visible_from;
            if (visCut) {
              setMessages((prev) =>
                prev.filter((m) => {
                  if (!m.created_at) return true;
                  const tm = new Date(m.created_at).getTime();
                  const tc = new Date(visCut).getTime();
                  if (Number.isNaN(tm) || Number.isNaN(tc)) return true;
                  return tm >= tc;
                })
              );
            }
          }

          // Listener para eventos de encerramento de conversa
          if (data.type === 'conversation_event') {
            // Evento de conversa recebido

            if (data.event_type === 'conversation_closed' || data.event_type === 'conversation_ended') {
              // Verificar se a conversa atual realmente está fechada antes de fechar a interface
              // Só fechar se a conversa atual for a mesma que foi fechada E se ela realmente estiver fechada
              if (data.conversation_id === conversation.id) {
                // Verificar status atual da conversa antes de fechar
                // Se a conversa já estava fechada quando foi aberta, não fechar novamente
                const currentStatus = conversation.status;

                // Só fechar se a conversa estava aberta e agora foi fechada
                if (currentStatus && currentStatus !== 'closed' && currentStatus !== 'ended') {
                  // Conversa encerrada via WebSocket

                  // Atualizar estado da conversa
                  if (onConversationUpdate) {
                    onConversationUpdate({
                      ...conversation,
                      status: 'closed',
                      closed_at: data.timestamp
                    });
                  }

                  // Notificar usuário e fechar a interface
                  if (onConversationClose) {
                    onConversationClose();
                  }
                } else {
                  // Apenas atualizar o status sem fechar a interface
                  if (onConversationUpdate) {
                    onConversationUpdate({
                      ...conversation,
                      status: data.data?.status || 'closed',
                      closed_at: data.timestamp
                    });
                  }
                }
              }

              // Manter histórico de mensagens; apenas atualiza status
            }

            // Listener para atribuição de conversa
            if (data.event_type === 'conversation_assigned') {
              // Conversa atribuída via WebSocket

              if (onConversationUpdate) {
                onConversationUpdate({
                  ...conversation,
                  assignee_id: data.data.assignee_id
                });
              }
              fetchMessages();
            }

            // Listener para mudanças de provedor (isolamento multi-tenant)
            if (data.event_type === 'provedor_changed') {
              // Mudança de provedor detectada via WebSocket

              // Verificar se a conversa atual pertence ao provedor correto
              if (data.data.provedor_id !== conversation?.contact?.provedor?.id) {
                // Conversa não pertence ao provedor atual, redirecionando

                // Redirecionar para lista de conversas
                if (onConversationClose) {
                  onConversationClose();
                }

                // Manter histórico de mensagens; apenas fecha a conversa
              }
            }
          }

        } catch (error) {
          console.error('[WebSocket] Erro ao processar mensagem:', error);
          if (process.env.NODE_ENV === 'development') {
            console.error('[WebSocket] Payload problemático:', event.data);
          }
        }
      };

      ws.onerror = (error) => {
        // CORREÇÃO DE SEGURANÇA: Não expor token em logs
        // O erro pode conter a URL com token, mas não vamos logá-la
      };

      ws.onclose = async (event) => {
        // Códigos de erro que indicam que a conversa não existe ou sem permissão
        // 4001 = Unauthorized, 4003 = Forbidden, 4000 = Internal error (quando conversa não existe)
        const fatalCodes = [4001, 4003, 4000];
        if (fatalCodes.includes(event.code)) {
          localStorage.removeItem('selectedConversation');
          if (onConversationClose) {
            onConversationClose();
          }
          shouldReconnect = false;
          reconnectAttempts = MAX_RECONNECT_ATTEMPTS;
          return;
        }

        // WebSocket desconectado - tentar reconectar apenas se:
        // 1. Ainda deve reconectar
        // 2. Não excedeu o limite de tentativas
        // 3. A conversa ainda está selecionada
        if (shouldReconnect && reconnectAttempts < MAX_RECONNECT_ATTEMPTS && conversation && conversation.id) {
          reconnectAttempts++;
          reconnectTimeout = setTimeout(() => {
            if (shouldReconnect && conversation && conversation.id) {
              connectWebSocket();
            }
          }, 3000);
        } else if (reconnectAttempts >= MAX_RECONNECT_ATTEMPTS) {
          // Excedeu tentativas - parar de tentar
          shouldReconnect = false;
        }
      };
    };

    connectWebSocket();

    return () => {
      // Parar tentativas de reconexão
      shouldReconnect = false;
      if (reconnectTimeout) {
        clearTimeout(reconnectTimeout);
      }

      // Fechando WebSocket
      if (wsRef.current) {
        if (wsRef.current.heartbeatInterval) {
          clearInterval(wsRef.current.heartbeatInterval);
        }
        if (wsRef.current.readyState === WebSocket.OPEN) {
          wsRef.current.close(1000);
        }
        wsRef.current = null;
      }
    };
  }, [conversation?.id, authReady]); // ESTABILIZADO: Só reconecta se trocar de conversa ou mudar auth

  //  LIMPEZA AUTOMÁTICA DE MENSAGENS TEMPORÁRIAS
  useEffect(() => {
    const cleanupInterval = setInterval(() => {
      setMessages(currentMessages => {
        const now = Date.now();
        return currentMessages.filter(msg => {
          if (msg.isTemporary || msg.is_sending) {
            const messageAge = now - new Date(msg.created_at).getTime();
            return messageAge <= 15000; // Manter por no máximo 15 segundos
          }
          return true;
        });
      });
    }, 5000); // Executar a cada 5 segundos

    return () => {
      clearInterval(cleanupInterval);
    };
  }, [conversation]);

  // Status da conversa é monitorado via WebSocket do painel (tempo real)
  // Não é necessário polling - o WebSocket já envia conversation_event quando há mudanças

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  const handleScrollContainer = () => {
    const el = scrollContainerRef.current;
    if (!el) return;
    const threshold = 80; // px de tolerância para considerar "no fundo"
    const distanceFromBottom = el.scrollHeight - el.scrollTop - el.clientHeight;
    const atBottom = distanceFromBottom <= threshold;
    setShouldAutoScroll(atBottom);
  };

  const scrollToReplyTarget = (replyToMessageId) => {
    const rid =
      replyToMessageId != null && replyToMessageId !== ''
        ? Number(replyToMessageId)
        : NaN;
    if (!Number.isFinite(rid)) return;
    const root = scrollContainerRef.current;
    if (!root) return;
    const el = root.querySelector(`[data-chat-message-id="${rid}"]`);
    if (!el) {
      toast.info('Mensagem original não está carregada ou não foi encontrada.');
      return;
    }
    if (highlightClearTimeoutRef.current) {
      window.clearTimeout(highlightClearTimeoutRef.current);
      highlightClearTimeoutRef.current = null;
    }
    setShouldAutoScroll(false);
    setHighlightTargetMessageId(null);
    requestAnimationFrame(() => {
      setHighlightTargetMessageId(rid);
      el.scrollIntoView({ behavior: 'smooth', block: 'center' });
      highlightClearTimeoutRef.current = window.setTimeout(() => {
        setHighlightTargetMessageId(null);
        highlightClearTimeoutRef.current = null;
      }, 2800);
    });
  };

  useEffect(() => {
    return () => {
      if (highlightClearTimeoutRef.current) {
        window.clearTimeout(highlightClearTimeoutRef.current);
      }
    };
  }, []);

  useEffect(() => {
    if (shouldAutoScroll) {
      scrollToBottom();
    }
  }, [messages, shouldAutoScroll]);

  //  handleSendMessage CORRIGIDO - SEM mensagem temporária
  const handleCorrectText = async () => {
    if (!message.trim() || isCorrecting) return;

    try {
      setIsCorrecting(true);
      const token = localStorage.getItem('auth_token') || localStorage.getItem('token');

      const res = await axios.post('/api/text/correct/', {
        text: message,
        language: 'pt-BR'
      }, {
        headers: { Authorization: `Token ${token}` }
      });

      if (res.data?.success && res.data?.corrected_text) {
        setMessage(res.data.corrected_text);

        // Ajustar altura da textarea após a correção
        setTimeout(() => {
          const textarea = document.getElementById('message-input');
          if (textarea) {
            textarea.style.height = 'auto';
            textarea.style.height = Math.min(textarea.scrollHeight, 120) + 'px';
          }
        }, 50);
      }
    } catch (err) {
      console.error('Erro ao corrigir texto:', err);
    } finally {
      setIsCorrecting(false);
    }
  };

  const handleSendMessage = async () => {
    if (!message.trim() || !conversation) return;

    if (isWaitingQueueContentHiddenForAgent(conversation, user)) {
      toast.error('Atribua a conversa para enviar mensagens.');
      return;
    }

    // Verificar se a janela de 24 horas está aberta para WhatsApp
    // Se is24hWindowOpen for null, ainda não foi carregado do backend, então permitir
    if (is24hWindowOpen === false && isWhatsAppChannel) {

      const msg24h = '⚠️ Janela de 24 horas fechada. Use um template para reabrir o contato.';
      setError(msg24h);
      toast.error(msg24h);
      return;
    }

    setError('');
    // Priorizar auth_token que é o padrão salvo no Login, mas aceitar token também para compatibilidade
    const token = localStorage.getItem('auth_token') || localStorage.getItem('token');

    //  Marcar mensagem como pendente para evitar duplicatas - Usar REF para evitar stale closure
    const messageKey = message.trim();
    if (pendingMessagesRef.current.has(messageKey)) {
      // Mensagem já está sendo enviada, ignorando
      return;
    }

    setPendingMessages(prev => {
      const newSet = new Set(prev);
      newSet.add(messageKey);
      return newSet;
    });
    pendingMessagesRef.current.add(messageKey);

    const sendConversationId = conversation.id;

    try {
      // Otimização: Usar os dados do usuário já presentes na prop 'user'
      const userName = user?.first_name || user?.username || 'Usuário';

      // Formatar mensagem com nome do usuário para enviar ao WhatsApp
      const formattedMessage = `*${userName} disse:*\n${message}`;

      //  NÃO adicionar mensagem temporária - deixar o WebSocket fazer isso

      // Preparar payload para envio
      const payload = {
        conversation_id: sendConversationId,
        content: formattedMessage
      };

      // Adicionar informações de resposta se estiver respondendo a uma mensagem
      if (replyingToMessage) {
        const replyId = replyingToMessage.external_id || replyingToMessage.additional_attributes?.external_id || replyingToMessage.id;
        payload.reply_to_message_id = replyId;
        payload.reply_to_content = replyingToMessage.content;
        // Debug removido
      }

      // Enviar mensagem formatada para o WhatsApp
      const response = await axios.post('/api/messages/send_text/', payload, {
        headers: { Authorization: `Token ${token}` }
      });

      //  Se o WebSocket não funcionar, adicionar mensagem do response
      setTimeout(() => {
        // CORREÇÃO: Usar pendingMessagesRef.current em vez do estado pendingMessages
        // para evitar o problema de "stale closure" no setTimeout
        if (Number(activeConversationIdRef.current) !== Number(sendConversationId)) {
          pendingMessagesRef.current.delete(messageKey);
          setPendingMessages(prev => {
            const next = new Set(prev);
            next.delete(messageKey);
            return next;
          });
          return;
        }
        if (pendingMessagesRef.current.has(messageKey)) {
          console.warn(`[WebSocket] Mensagem "${messageKey.substring(0, 20)}..." não recebida via WS após 2s, usando fallback da API.`);
          
          if (response.data && response.data.id) {
            const processedMessage = {
              ...response.data,
              content: processMessageContent(response.data.content, response.data.is_from_customer)
            };

            setMessages(currentMessages => {
              const messageExists = currentMessages.some(m => m.id === response.data.id);
              if (!messageExists) {
                return [...currentMessages, processedMessage].sort((a, b) =>
                  new Date(a.created_at) - new Date(b.created_at)
                );
              }
              return currentMessages;
            });
          }

          // Remover das pendentes (ref e estado)
          pendingMessagesRef.current.delete(messageKey);
          setPendingMessages(prev => {
            const newSet = new Set(prev);
            newSet.delete(messageKey);
            return newSet;
          });
        }
      }, 2000); // Aguardar 2 segundos pelo WebSocket

      setMessage('');
      setReplyingToMessage(null);

    } catch (e) {
      console.error(' Erro ao enviar mensagem:', e);

      // Verificar se é erro de janela de 24 horas fechada
      let errorMessage = 'Erro ao enviar mensagem.';

      if (e.response?.data?.error_message) {
        // Mensagem específica do backend (ex: janela de 24 horas)
        errorMessage = e.response.data.error_message;
      } else if (e.response?.data?.error) {
        // Mensagem de erro genérica do backend
        errorMessage = e.response.data.error;
      } else if (e.response?.data?.detail) {
        // Mensagem de erro detalhada
        errorMessage = e.response.data.detail;
      } else if (e.message) {
        // Mensagem de erro do axios
        errorMessage = e.message;
      }

      // Verificar se é erro de janela de 24 horas (código 131047)
      if (e.response?.data?.error_code === 131047 ||
        errorMessage.includes('24 horas') ||
        errorMessage.includes('janela de atendimento')) {
        errorMessage = '⚠️ ' + errorMessage;
      }
      setError(errorMessage);
      toast.error(errorMessage);

      //  Remover das pendentes em caso de erro
      pendingMessagesRef.current.delete(messageKey);
      setPendingMessages(prev => {
        const newSet = new Set(prev);
        newSet.delete(messageKey);
        return newSet;
      });
    }
  };

  const handleKeyPress = (e) => {
    if (showQuickReplies) {
      if (e.key === 'ArrowDown') {
        e.preventDefault();
        setQuickReplyIndex(prev => Math.min(prev + 1, filteredQuickReplies.length - 1));
        return;
      }
      if (e.key === 'ArrowUp') {
        e.preventDefault();
        setQuickReplyIndex(prev => Math.max(prev - 1, 0));
        return;
      }
      if (e.key === 'Enter') {
        e.preventDefault();
        if (filteredQuickReplies.length > 0) {
          selectQuickReply(filteredQuickReplies[quickReplyIndex]);
        }
        return;
      }
      if (e.key === 'Escape') {
        setShowQuickReplies(false);
        return;
      }
    }

    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSendMessage();
    }
  };

  // Funções para gravação de áudio
  const startRecording = async () => {
    try {
      if (isWaitingQueueContentHiddenForAgent(conversation, user)) {
        toast.error('Atribua a conversa para gravar áudio.');
        return;
      }

      if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
        throw new Error('getUserMedia não é suportado neste navegador');
      }

      const isSecure = window.location.protocol === 'https:' ||
        window.location.hostname === 'localhost' ||
        window.location.hostname === '127.0.0.1' ||
        window.location.hostname.includes('ngrok');

      if (!isSecure) {
        throw new Error('Gravação de áudio requer HTTPS. Use HTTPS ou localhost para gravar áudio.');
      }

      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const mediaRecorder = new MediaRecorder(stream, {
        mimeType: 'audio/webm;codecs=opus'
      });

      mediaRecorderRef.current = mediaRecorder;
      const chunks = [];

      mediaRecorder.ondataavailable = (event) => {
        if (event.data.size > 0) {
          chunks.push(event.data);
        }
      };

      mediaRecorder.onstop = () => {
        const blob = new Blob(chunks, { type: 'audio/webm' });
        setAudioBlob(blob);
        setAudioUrl(URL.createObjectURL(blob));

        stream.getTracks().forEach(track => track.stop());
      };

      mediaRecorder.start();
      setIsRecording(true);
      setRecordingTime(0);

      recordingIntervalRef.current = setInterval(() => {
        setRecordingTime(prev => prev + 1);
      }, 1000);

    } catch (error) {
      console.error('Erro ao iniciar gravação:', error);

      if (error.name === 'NotAllowedError') {
        setError('Permissão de microfone negada. Clique no ícone do microfone na barra de endereços para permitir.');
      } else if (error.name === 'NotFoundError') {
        setError('Nenhum microfone encontrado. Verifique se há um microfone conectado.');
      } else if (error.message.includes('getUserMedia não é suportado')) {
        setError('Gravação de áudio não é suportada neste navegador. Tente usar HTTPS ou um navegador mais recente.');
      } else if (error.message.includes('requer HTTPS')) {
        setError('Gravação de áudio requer HTTPS. Use HTTPS ou localhost para gravar áudio.');
      } else if (error.name === 'NotSupportedError') {
        setError('Este navegador não suporta gravação de áudio. Tente usar Chrome, Firefox ou Edge.');
      } else {
        setError('Erro ao acessar microfone. Verifique as permissões ou tente usar HTTPS.');
      }
    }
  };

  const stopRecording = () => {
    if (mediaRecorderRef.current && isRecording) {
      mediaRecorderRef.current.stop();
      setIsRecording(false);

      if (recordingIntervalRef.current) {
        clearInterval(recordingIntervalRef.current);
        recordingIntervalRef.current = null;
      }
    }
  };

  const cancelRecording = () => {
    if (mediaRecorderRef.current && isRecording) {
      mediaRecorderRef.current.stop();
      setIsRecording(false);
      setAudioBlob(null);
      setAudioUrl(null);
      setRecordingTime(0);

      if (recordingIntervalRef.current) {
        clearInterval(recordingIntervalRef.current);
        recordingIntervalRef.current = null;
      }

      if (mediaRecorderRef.current.stream) {
        mediaRecorderRef.current.stream.getTracks().forEach(track => track.stop());
      }
    }
  };

  const sendAudioMessage = async () => {
    if (!audioBlob || !conversation) return;

    if (isWaitingQueueContentHiddenForAgent(conversation, user)) {
      toast.error('Atribua a conversa para enviar mensagens.');
      return;
    }

    // Verificar se a janela de 24 horas está aberta para WhatsApp
    // Se is24hWindowOpen for null, ainda não foi carregado do backend, então permitir
    if (is24hWindowOpen === false && isWhatsAppChannel) {

      const msg24h = '⚠️ Janela de 24 horas fechada. Use um template para reabrir o contato.';
      setError(msg24h);
      toast.error(msg24h);
      return;
    }

    if (sendingMedia) {
      // Já está enviando áudio, ignorando
      return;
    }

    try {
      // Iniciando envio de áudio PTT

      const audioFile = new File([audioBlob], `audio_${Date.now()}.webm`, {
        type: 'audio/webm'
      });

      // Dados do áudio

      const maxSize = 16 * 1024 * 1024;
      if (audioFile.size > maxSize) {
        setError('Áudio muito grande. Tamanho máximo: 16MB');
        return;
      }

      if (audioBlob.size === 0) {
        setError('Áudio inválido. Tente gravar novamente.');
        return;
      }

      // Validações passaram, enviando áudio

      const finalMediaType = 'ptt';
      // Usando media_type

      if (finalMediaType !== 'ptt') {
        console.error(' ERRO: media_type não é PTT!');
        setError('Erro interno: tipo de mídia inválido');
        return;
      }

      await handleSendMedia(audioFile, finalMediaType, null);

      // Log removido(' Áudio enviado com sucesso!');

      setAudioBlob(null);
      setAudioUrl(null);
      setRecordingTime(0);

    } catch (error) {
      console.error(' Erro ao enviar áudio:', error);
      setError('Erro ao enviar áudio: ' + error.message);
    }
  };

  const formatRecordingTime = (seconds) => {
    const mins = Math.floor(seconds / 60);
    const secs = seconds % 60;
    return `${mins}:${secs.toString().padStart(2, '0')}`;
  };

  const playAudio = (messageId, audioUrl) => {
    // Log removido('🎵 Reproduzindo áudio:', { messageId, audioUrl });

    if (playingAudio && playingAudio !== messageId) {
      const prevAudio = audioRefs.current[playingAudio];
      if (prevAudio) {
        prevAudio.pause();
        prevAudio.currentTime = 0;
      }
    }

    let audio = audioRefs.current[messageId];
    if (!audio) {
      audio = new Audio(audioUrl);
      audioRefs.current[messageId] = audio;

      audio.addEventListener('timeupdate', () => {
        const progress = (audio.currentTime / audio.duration) * 100;
        setAudioProgress(prev => ({ ...prev, [messageId]: progress }));
      });

      audio.addEventListener('ended', () => {
        setPlayingAudio(null);
        setAudioProgress(prev => ({ ...prev, [messageId]: 0 }));
      });

      audio.addEventListener('error', (e) => {
        console.error('Erro ao reproduzir áudio:', e);
        setPlayingAudio(null);
      });
    }

    audio.play().then(() => {
      setPlayingAudio(messageId);
    }).catch(e => {
      console.error('Erro ao reproduzir áudio:', e);
    });
  };

  const pauseAudio = (messageId) => {
    const audio = audioRefs.current[messageId];
    if (audio) {
      audio.pause();
      setPlayingAudio(null);
    }
  };

  // Cleanup ao desmontar componente
  useEffect(() => {
    return () => {
      if (recordingIntervalRef.current) {
        clearInterval(recordingIntervalRef.current);
      }
      if (audioUrl) {
        URL.revokeObjectURL(audioUrl);
      }
      if (audioRefs.current) {
        Object.values(audioRefs.current).forEach(audio => {
          if (audio) {
            audio.pause();
            audio.src = '';
          }
        });
        audioRefs.current = {};
      }
    };
  }, [audioUrl]);

  //  handleSendMedia CORRIGIDO - SEM mensagem temporária
  const handleSendMedia = async (file, mediaType, caption = '') => {
    if (!conversation) return;

    // Verificar se a janela de 24 horas está aberta para WhatsApp
    // Se is24hWindowOpen for null, ainda não foi carregado do backend, então permitir
    if (is24hWindowOpen === false && isWhatsAppChannel) {

      const msg24h = '⚠️ Janela de 24 horas fechada. Use um template para reabrir o contato.';
      setError(msg24h);
      toast.error(msg24h);
      return;
    }

    if (sendingMedia) {
      // Log removido('🚫 Já está enviando mídia, ignorando...');
      return;
    }

    setError('');
    setSendingMedia(true);
    const token = localStorage.getItem('token');
    const sendMediaConversationId = conversation.id;

    // Iniciando envio de mídia

    const maxSize = 16 * 1024 * 1024;
    if (file.size > maxSize) {
      setError('Arquivo muito grande. Tamanho máximo: 16MB');
      setSendingMedia(false);
      return;
    }

    // Validar tipo de arquivo
    const allowedTypes = {
      image: ['image/jpeg', 'image/png', 'image/gif', 'image/webp'],
      video: ['video/mp4', 'video/avi', 'video/mov', 'video/wmv'],
      audio: ['audio/mp3', 'audio/wav', 'audio/ogg', 'audio/m4a', 'audio/webm'],
      ptt: ['audio/webm', 'audio/mp3', 'audio/wav', 'audio/ogg', 'audio/m4a'],
      myaudio: ['audio/webm', 'audio/mp3', 'audio/wav', 'audio/ogg', 'audio/m4a'],
      document: ['application/pdf', 'application/msword', 'application/vnd.openxmlformats-officedocument.wordprocessingml.document']
    };

    if (!allowedTypes[mediaType]?.includes(file.type)) {
      console.warn('Tipo de arquivo não reconhecido:', file.type);
    }

    try {
      //  NÃO adicionar mensagem de "enviando..." - deixar o WebSocket fazer isso

      // Buscar informações do usuário atual se houver caption (exceto para PTT)
      let formattedCaption = caption;
      if (caption && mediaType !== 'ptt') {
        const userResponse = await axios.get('/api/auth/me/', {
          headers: { Authorization: `Token ${token}` }
        });

        const currentUser = userResponse.data;
        const userName = currentUser.first_name || currentUser.username || 'Usuário';
        formattedCaption = `*${userName} disse:*\n${caption}`;
      }

      const formData = new FormData();
      formData.append('conversation_id', sendMediaConversationId);
      formData.append('media_type', mediaType);
      formData.append('file', file);
      // Para PTT (mensagens de voz), não enviar caption
      if (formattedCaption && mediaType !== 'ptt') {
        formData.append('caption', formattedCaption);
      }

      // Adicionar informações de resposta se estiver respondendo a uma mensagem
      if (replyingToMessage) {
        const replyId = replyingToMessage.external_id || replyingToMessage.additional_attributes?.external_id || replyingToMessage.id;
        formData.append('reply_to_message_id', replyId);
        // Enviando mídia como resposta para mensagem
      }

      // Enviando mídia para o backend

      // Enviar mídia com caption formatado para o WhatsApp
      const response = await axios.post('/api/messages/send_media/', formData, {
        headers: {
          Authorization: `Token ${token}`,
          'Content-Type': 'multipart/form-data'
        }
      });

      // Log removido(' Mídia enviada com sucesso:', response.data);

      //  Se o WebSocket não funcionar, adicionar mensagem do response
      setTimeout(() => {
        if (Number(activeConversationIdRef.current) !== Number(sendMediaConversationId)) {
          return;
        }
        if (response.data && response.data.id) {
          setMessages(currentMessages => {
            const messageExists = currentMessages.some(m => m.id === response.data.id);
            if (!messageExists) {
              // Log removido('WebSocket não recebeu mídia, adicionando do response');
              return [...currentMessages, response.data].sort((a, b) =>
                new Date(a.created_at) - new Date(b.created_at)
              );
            }
            return currentMessages;
          });
        }
      }, 2000); // Aguardar 2 segundos pelo WebSocket

    } catch (e) {
      console.error(' Erro ao enviar mídia:', e);
      console.error(' Detalhes do erro:', e.response?.data);

      // Verificar se é erro de janela de 24 horas fechada
      let errorMessage = 'Erro ao enviar mídia.';

      if (e.response?.data?.error_message) {
        // Mensagem específica do backend (ex: janela de 24 horas)
        errorMessage = e.response.data.error_message;
      } else if (e.response?.data?.error) {
        // Mensagem de erro genérica do backend
        errorMessage = e.response.data.error;
      } else if (e.response?.data?.detail) {
        // Mensagem de erro detalhada
        errorMessage = e.response.data.detail;
      } else if (e.message) {
        // Mensagem de erro do axios
        errorMessage = e.message;
      }

      // Verificar se é erro de janela de 24 horas (código 131047)
      if (e.response?.data?.error_code === 131047 ||
        errorMessage.includes('24 horas') ||
        errorMessage.includes('janela de atendimento')) {
        errorMessage = '⚠️ ' + errorMessage;
      } else {
        errorMessage = 'Erro ao enviar mídia: ' + errorMessage;
      }
      setError(errorMessage);
      toast.error(errorMessage);
    } finally {
      setSendingMedia(false);
    }
  };

  // Função para atribuir conversa para o usuário atual
  const handleAssignToMe = async () => {
    if (!conversation) return;

    const token = localStorage.getItem('auth_token') || localStorage.getItem('token');
    try {
      // Usar o novo endpoint específico para atribuição
      const response = await axios.post(`/api/conversations/${conversation.id}/assign/`, {}, {
        headers: { Authorization: `Token ${token}` }
      });


      // Log removido('Conversa atribuída com sucesso:', response.data);

      // O WebSocket ou o callback onConversationUpdate cuidará da atualização da UI
      if (onConversationUpdate && response.data.conversation) {
        onConversationUpdate(response.data.conversation);
      }
      fetchMessages();
    } catch (error) {
      console.error('Erro ao atribuir conversa:', error);
      console.error('Detalhes do erro:', error.response?.data);
      const apiMessage = error?.response?.data?.error;
      const friendlyMessage = typeof apiMessage === 'string' && apiMessage.trim()
        ? apiMessage
        : 'Não foi possível atribuir o atendimento agora. Tente novamente em instantes.';
      toast.error(friendlyMessage);
    }
  };

  // Função para encerrar conversa
  const handleCloseConversation = async () => {
    if (!conversation) return;

    const token = localStorage.getItem('auth_token') || localStorage.getItem('token');
    try {
      const response = await axios.patch(`/api/conversations/${conversation.id}/`, {
        status: 'closed'
      }, {
        headers: { Authorization: `Token ${token}` }
      });


      // Log removido('Conversa encerrada com sucesso:', response.data);

      // CORREÇÃO: Limpar conversa selecionada do localStorage imediatamente
      localStorage.removeItem('selectedConversation');

      // CORREÇÃO: Notificar atualização com null para limpar seleção
      if (onConversationUpdate) {
        onConversationUpdate(null);
      }

      // Chamar callback para fechar a conversa
      if (onConversationClose) {
        onConversationClose();
      }

      // Fallback: navegar de volta para a lista de conversas
      if (!onConversationClose) {
        const provedorId = conversation.inbox?.provedor?.id || '';
        navigate(`/${provedorId}/chat`);
      }
    } catch (error) {
      console.error('Erro ao encerrar conversa:', error);
      console.error('Detalhes do erro:', error.response?.data);
      toast.error('Erro ao encerrar conversa. Tente novamente.');
    }
  };

  // Função para buscar atendentes do provedor
  const fetchAgents = async () => {
    if (!conversation) return;

    const token = localStorage.getItem('token');
    setLoadingAgents(true);

    try {
      // Usar o novo endpoint específico para usuários do provedor
      const response = await axios.get('/api/users/my_provider_users/', {
        headers: { Authorization: `Token ${token}` }
      });

      const agents = response.data.users || [];
      // Log removido('Agentes encontrados:', agents);
      setAgents(agents);

      // Buscar status atual dos usuários
      await fetchUsersStatus(agents, token);

      setShowTransferDropdown(true);
    } catch (error) {
      console.error('Erro ao buscar atendentes:', error);
      setAgents([]);
    } finally {
      setLoadingAgents(false);
    }
  };

  // Função para buscar status atual dos usuários
  const fetchUsersStatus = async (users, token) => {
    try {
      // Buscar status atual dos usuários
      // Log removido('Buscando status dos usuários...');
      const statusResponse = await axios.get('/api/users/status/', {
        headers: { Authorization: `Token ${token}` }
      });

      // Log removido('Resposta do status:', statusResponse.data);

      if (statusResponse.data && statusResponse.data.users) {
        const statusUpdates = {};
        statusResponse.data.users.forEach(user => {
          statusUpdates[user.id] = user.is_online;
        });
        setAgentsStatus(prev => ({ ...prev, ...statusUpdates }));
        // Log removido('Status dos usuários atualizado:', statusUpdates);
      }
    } catch (error) {
      console.error('Erro ao buscar status dos usuários:', error);
      // Se não conseguir buscar status, usar o status do backend
      const statusUpdates = {};
      users.forEach(user => {
        statusUpdates[user.id] = user.is_online;
      });
      setAgentsStatus(prev => ({ ...prev, ...statusUpdates }));
    }
  };

  // Função para atualizar status dos agentes em tempo real
  const updateAgentStatus = (agentId, isOnline) => {
    setAgentsStatus(prev => ({
      ...prev,
      [agentId]: isOnline
    }));
  };

  // Função para transferir conversa
  const handleTransferConversation = async () => {
    await fetchAgents();
  };

  // Função para transferir para um agente específico
  const handleTransferToAgent = async (agentId) => {
    if (!conversation) return;

    const token = localStorage.getItem('token');
    const url = `/api/conversations/${conversation.id}/transfer/`;

    // Log removido(' DEBUG: URL de transferência:', url);
    // Log removido(' DEBUG: Axios baseURL:', axios.defaults.baseURL);
    // Log removido(' DEBUG: URL completa:', axios.defaults.baseURL + url);

    try {
      // Usar o mesmo endpoint do ConversasDashboard
      const response = await axios.post(url, {
        user_id: agentId
      }, {
        headers: { Authorization: `Token ${token}` }
      });

      // Log removido('Conversa transferida com sucesso!');
      toast.success('Transferido com sucesso!');
      setShowTransferDropdown(false);

      // Atualizar a interface em vez de recarregar a página
      if (response.data.success) {
        const updatedConversation = {
          ...conversation,
          status: 'pending',
          assignee: null
        };
        if (onConversationUpdate) {
          onConversationUpdate(updatedConversation);
        }
        setShowTransferDropdown(false);
      }

    } catch (_) {
      toast.error('Erro ao transferir atendimento.');
    }
  };

  const fetchProfilePicture = async (silent = false) => {
    if (!conversation || !conversation.contact) {
      return;
    }

    setLoadingProfilePic(true);
    const token = localStorage.getItem('token');

    try {
      // Determinar o tipo de integração baseado no canal
      // Para todas as conversas WhatsApp, usar Uazapi (que está funcionando)
      const integrationType = (conversation.inbox?.channel_type === 'whatsapp' ||
        // whatsapp_session é o valor do banco de dados para sessões Uazapi
        conversation.inbox?.channel_type === 'whatsapp_session') ? 'uazapi' : 'evolution';

      // Para Uazapi, usar a instância configurada no provedor
      // Para Evolution, usar a instância do canal
      let instanceName;
      if (integrationType === 'uazapi') {
        // Para Uazapi, usar uma instância padrão ou buscar do provedor
        instanceName = 'teste-niochat'; // Instância padrão da Uazapi
      } else {
        // Para Evolution, usar a instância do canal
        instanceName = conversation.inbox?.settings?.evolution_instance ||
          conversation.inbox?.settings?.instance ||
          conversation.inbox?.name?.replace('WhatsApp ', '');
      }

      // Log removido(` Buscando foto via ${integrationType}, instância: ${instanceName}`);
      // Log removido(` Channel type: ${conversation.inbox?.channel_type}`);

      const response = await axios.post('/api/whatsapp/profile-picture/', {
        phone: conversation.contact.phone,
        instance_name: instanceName,
        integration_type: integrationType
      }, {
        headers: { Authorization: `Token ${token}` }
      });

      if (response.data.success) {
        if (!silent) {
          toast.success('Foto do perfil atualizada com sucesso!');
        }
      } else {
        if (!silent) {
          toast.error('Não foi possível obter a foto do perfil: ' + response.data.error);
        }
      }
    } catch (error) {
      console.error('Erro ao buscar foto do perfil:', error);
      if (!silent) {
        toast.error('Erro ao buscar foto do perfil.');
      }
    } finally {
      setLoadingProfilePic(false);
    }
  };

  // Função para enviar reação
  const sendReaction = async (messageId, emoji) => {
    try {
      // Priorizar auth_token que é o padrão salvo no Login, mas aceitar token também para compatibilidade
      const token = localStorage.getItem('auth_token') || localStorage.getItem('token');

      // Chamar endpoint do backend para enviar reação
      const response = await axios.post('/api/messages/react/', {
        message_id: messageId,
        emoji: emoji
      }, {
        headers: { Authorization: `Token ${token}` }
      });

      if (response.data.success) {
        // Log removido('Reação enviada com sucesso');
        setShowReactionPicker(false);
        setSelectedMessageForReaction(null);

        // Log removido(' Processando mensagem após reação...');

        // Atualizar a mensagem localmente com a resposta do backend
        // O backend retorna a reação, não a mensagem completa atualizada
        // Vamos atualizar o campo reactions da mensagem
        if (response.data.reaction) {
          // Atualizar a mensagem localmente adicionando a reação ao array reactions
          setMessages(prevMessages =>
            prevMessages.map(msg => {
              if (msg.id === messageId) {
                const existingReactions = msg.reactions || [];
                const reactionData = {
                  id: response.data.reaction.id,
                  emoji: response.data.reaction.emoji,
                  is_from_customer: false, // Agente está reagindo
                  created_at: new Date().toISOString()
                };

                // Verificar se já existe uma reação com o mesmo emoji do agente
                const existingReactionIndex = existingReactions.findIndex(r =>
                  r.emoji === reactionData.emoji && r.is_from_customer === false
                );

                if (existingReactionIndex >= 0) {
                  // Atualizar reação existente
                  const updatedReactions = [...existingReactions];
                  updatedReactions[existingReactionIndex] = reactionData;
                  return {
                    ...msg,
                    reactions: updatedReactions
                  };
                } else {
                  // Adicionar nova reação
                  return {
                    ...msg,
                    reactions: [...existingReactions, reactionData]
                  };
                }
              }
              return msg;
            })
          );
        }
      } else {
        toast.error('Erro ao enviar reação: ' + (response.data.error || 'Erro desconhecido'));
      }
    } catch (error) {
      console.error('Erro ao enviar reação:', error);

      let errorMessage = 'Erro ao enviar reação';
      if (error.response?.status === 401) {
        errorMessage = 'Erro de autenticação. Faça login novamente.';
      } else if (error.response?.status === 404) {
        errorMessage = 'Mensagem não encontrada.';
      } else if (error.response?.status === 400) {
        errorMessage = error.response.data?.error || 'Dados inválidos.';
      } else {
        errorMessage = error.response?.data?.error || error.message;
      }

      toast.error(errorMessage);
    }
  };

  // Função para apagar mensagem
  const deleteMessage = async (messageId) => {
    try {
      // Priorizar auth_token que é o padrão salvo no Login, mas aceitar token também para compatibilidade
      const token = localStorage.getItem('auth_token') || localStorage.getItem('token');
      // Log removido(' DEBUG: Tentando excluir mensagem:', messageId);
      // Log removido('DEBUG: Credenciais verificadas');

      // Chamar endpoint do backend para deletar mensagem
      const response = await axios.post('/api/messages/delete_message/', {
        message_id: messageId
      }, {
        headers: { Authorization: `Token ${token}` }
      });

      // Log removido(' DEBUG: Resposta do servidor:', response.status, response.data);

      if (response.data.success) {
        // Log removido('Mensagem apagada com sucesso');
        setShowDeleteConfirm(false);
        setMessageToDelete(null);

        // Atualizar a mensagem localmente com a resposta do backend
        const updatedMessage = response.data.updated_message;

        // Processar o conteúdo da mensagem atualizada
        const processedMessage = {
          ...updatedMessage,
          content: processMessageContent(updatedMessage.content, updatedMessage.is_from_customer)
        };

        // Atualizar no estado local
        setMessages(prevMessages =>
          prevMessages.map(msg =>
            msg.id === messageId ? processedMessage : msg
          )
        );
      } else {
        toast.error('Erro ao apagar mensagem: ' + (response.data.error || 'Erro desconhecido'));
      }
    } catch (error) {
      let errorMessage = 'Erro ao apagar mensagem';
      if (error.response?.status === 401) {
        errorMessage = 'Erro de autenticação. Faça login novamente.';
      } else if (error.response?.status === 404) {
        errorMessage = 'Mensagem não encontrada.';
      } else if (error.response?.status === 400) {
        errorMessage = error.response.data?.error || 'Dados inválidos.';
      } else {
        errorMessage = error.response?.data?.error || error.message;
      }

      alert(errorMessage);
    }
  };

  // Função para abrir seletor de reação
  const openReactionPicker = (message) => {
    setSelectedMessageForReaction(message);
    setShowReactionPicker(true);
  };

  // Função para responder a uma mensagem
  const handleReplyToMessage = (message) => {
    setReplyingToMessage(message);
    // Focar no input de mensagem
    const messageInput = document.getElementById('message-input');
    if (messageInput) {
      messageInput.focus();
    }
  };

  // Função para cancelar resposta
  const cancelReply = () => {
    setReplyingToMessage(null);
  };

  // Função para buscar templates do canal (mesma lógica do Integrations.jsx)
  const fetchTemplates = async () => {
    // Verificar se temos os dados necessários
    if (!conversation) {
      setError('Conversa não encontrada');
      return;
    }

    if (!conversation.inbox) {
      setError('Inbox não encontrado');
      return;
    }

    // Permitir templates para 'whatsapp' e 'whatsapp_oficial'
    const channelType = conversation.inbox.channel_type;
    if (channelType !== 'whatsapp' && channelType !== 'whatsapp_oficial') {
      setError('Templates só estão disponíveis para WhatsApp');
      return;
    }

    setLoadingTemplates(true);
    setError(''); // Limpar erro anterior
    try {
      const token = localStorage.getItem('auth_token') || localStorage.getItem('token');

      if (!token) {
        setError('Token de autenticação não encontrado');
        setLoadingTemplates(false);
        return;
      }

      // 1. Tentar usar channel_real_id do backend (preferencial e validado)
      let channelId = conversation.inbox.channel_real_id;

      // 2. Fallback: Buscar canais e encontrar o mais compatível (se o backend não resolveu)
      if (!channelId) {
        console.log('ID real do canal não resolvido pelo backend, buscando na lista de canais...');
        const channelsResponse = await axios.get('/api/canais/', {
          headers: { Authorization: `Token ${token}` }
        });

        const channelsList = Array.isArray(channelsResponse.data)
          ? channelsResponse.data
          : channelsResponse.data.results || [];

        const provedorId = conversation.inbox?.provedor?.id;
        
        // Tentar encontrar um canal que case com o provedor, seja do tipo oficial e TENHA WABA_ID
        const bestMatch = channelsList.find(c => 
          (c.tipo === 'whatsapp_oficial' || c.tipo === 'whatsapp') && 
          c.ativo &&
          c.waba_id && // Importante: priorizar canal com WABA configurado para templates
          (!provedorId || c.provedor === provedorId || c.provedor?.id === provedorId)
        ) || channelsList.find(c => 
          (c.tipo === 'whatsapp_oficial' || c.tipo === 'whatsapp') && 
          c.ativo &&
          (!provedorId || c.provedor === provedorId || c.provedor?.id === provedorId)
        );

        if (bestMatch) {
          channelId = bestMatch.id;
          console.log('Canal compatível encontrado via fallback:', channelId);
        }
      }

      if (!channelId) {
        setError('Não foi possível identificar o canal do WhatsApp para carregar templates. Verifique as configurações de integração.');
        setLoadingTemplates(false);
        return;
      }

      console.log('Buscando templates para canal:', channelId);

      const response = await axios.get(`/api/canais/${channelId}/message-templates/`, {
        headers: { Authorization: `Token ${token}` }
      });

      if (response.data && response.data.success) {
        setTemplates(response.data.templates || []);
      } else {
        setError(response.data?.error || 'Erro ao buscar templates');
      }
    } catch (error) {
      console.error('Erro ao buscar templates:', error);
      let errorMessage = 'Erro ao carregar templates';
      if (error.response?.status === 404) {
        errorMessage = 'Canal de templates não encontrado. Verifique se a integração do WhatsApp Oficial está ativa.';
      } else if (error.response?.data?.error) {
        errorMessage = error.response.data.error;
      } else {
        errorMessage = error.message || 'Erro desconhecido';
      }
      setError(errorMessage);
    } finally {
      setLoadingTemplates(false);
    }
  };

  // Função para abrir modal de templates
  const openTemplatesModal = () => {
    setShowTemplatesModal(true);
    fetchTemplates();
  };

  // Função para enviar template
  const sendTemplate = async (template) => {
    if (!conversation?.contact?.phone) {
      setError('Número de telefone do contato não encontrado');
      toast.error('Número de telefone do contato não encontrado');
      return;
    }

    setSendingTemplate(true);
    try {
      // Priorizar auth_token que é o padrão salvo no Login, mas aceitar token também para compatibilidade
      const token = localStorage.getItem('auth_token') || localStorage.getItem('token');

      const response = await axios.post('/api/conversations/start-with-template/', {
        phone: conversation.contact.phone,
        template_name: template.name,
        template_language: template.language || 'pt_BR',
        template_components: [], // Pode ser expandido para suportar variáveis
        provedor_id: conversation.inbox?.provedor?.id,
        canal_id: conversation.inbox?.channel_id,
        conversation_id: conversation.id // Enviar ID da conversa atual para usar a mesma conversa
      }, {
        headers: { Authorization: `Token ${token}` }
      });

      if (response.data.success) {
        setShowTemplatesModal(false);
        setError('');

        // Se a resposta retornou uma conversa diferente, atualizar para ela
        if (response.data.conversation && response.data.conversation.id !== conversation.id) {
          // Nova conversa foi criada, atualizar para ela
          if (onConversationUpdate) {
            onConversationUpdate(response.data.conversation);
          }
        } else {
          // Mesma conversa, apenas atualizar status da janela e recarregar mensagens
          setIs24hWindowOpen(true);
          // Aguardar um pouco antes de recarregar para dar tempo do backend criar a mensagem
          setTimeout(() => {
            fetchMessages();
          }, 500);
        }
      } else {
        setError('Erro ao enviar template: ' + (response.data.error || 'Erro desconhecido'));
      }
    } catch (error) {
      console.error('Erro ao enviar template:', error);
      const errorMessage = 'Erro ao enviar template: ' + (error.response?.data?.error || error.message);
      setError(errorMessage);
      toast.error(errorMessage);
    } finally {
      setSendingTemplate(false);
    }
  };

  // Função para confirmar exclusão
  const confirmDelete = (message) => {
    setMessageToDelete(message);
    setShowDeleteConfirm(true);
  };

  // Função para determinar se uma mensagem é grande (estilo WhatsApp)
  const isLargeMessage = (content) => {
    if (!content) return false;

    // Considerar mensagem grande se:
    // 1. Tem mais de 100 caracteres
    // 2. Tem mais de 3 linhas
    // 3. Contém quebras de linha
    const charCount = content.length;
    const lineCount = content.split('\n').length;
    const hasLineBreaks = content.includes('\n');

    return charCount > 100 || lineCount > 3 || hasLineBreaks;
  };

  // Função para determinar o alinhamento da mensagem
  const getMessageAlignment = (msg, content) => {
    const isCustomer = msg.is_from_customer;

    // TODAS as mensagens do sistema (IA ou atendente) ficam do lado direito
    if (!isCustomer) {
      return 'justify-end';
    }

    // Mensagens do cliente ficam do lado esquerdo
    return 'justify-start';
  };

  // Função para determinar a ordem da mensagem
  const getMessageOrder = (msg, content) => {
    const isCustomer = msg.is_from_customer;

    // TODAS as mensagens do sistema (IA ou atendente) usam ordem 2 (direita)
    if (!isCustomer) {
      return 'order-2';
    }

    // Mensagens do cliente usam ordem 1 (esquerda)
    return 'order-1';
  };

  // Lógica de filtragem e limpeza movida para antes do return para evitar duplicidade

  // Função para lidar com upload de arquivo
  const handleFileUpload = (event) => {
    const file = event.target.files[0];
    if (!file) return;

    if (isWaitingQueueContentHiddenForAgent(conversation, user)) {
      toast.error('Atribua a conversa para enviar arquivos.');
      event.target.value = '';
      return;
    }

    // Verificar se a janela de 24 horas está aberta para WhatsApp
    // Se is24hWindowOpen for null, ainda não foi carregado do backend, então permitir
    if (is24hWindowOpen === false && isWhatsAppChannel) {

      setError('⚠️ Mais de 24 horas se passaram desde que o cliente respondeu pela última vez. Para enviar mensagens após este período, é necessário usar um modelo de mensagem (template). O cliente precisa entrar em contato primeiro para reabrir a janela de atendimento.');
      event.target.value = ''; // Limpar input
      return;
    }

    // Determinar tipo de mídia baseado no tipo do arquivo
    let mediaType = 'document'; // Padrão

    if (file.type.startsWith('image/')) {
      mediaType = 'image';
      setPendingFilePreview(URL.createObjectURL(file));
    } else if (file.type.startsWith('video/')) {
      mediaType = 'video';
      setPendingFilePreview(URL.createObjectURL(file));
    } else if (file.type.startsWith('audio/')) {
      mediaType = 'audio';
    }

    // Em vez de enviar direto, colocar em estado pendente para prévia
    setPendingFile(file);
    setPendingFileType(mediaType);
    setPendingFileCaption('');

    // Limpar input
    event.target.value = '';
  };

  const cancelPendingFile = () => {
    if (pendingFilePreview) {
      URL.revokeObjectURL(pendingFilePreview);
    }
    setPendingFile(null);
    setPendingFileType(null);
    setPendingFileCaption('');
    setPendingFilePreview(null);
  };

  // Função para abrir modal de imagem
  const openImageModal = (imageUrl) => {
    setSelectedImage(imageUrl);
    setShowImageModal(true);
  };

  // Função para renderizar mensagem com links clicáveis
  const renderMessageWithLinks = (text) => {
    if (!text || typeof text !== 'string') return text;

    // Regex melhorada para detectar URLs completas
    // Detecta: https://, http://, www., e domínios com protocolo
    // Suporta URLs longas com query strings, fragmentos, etc.
    // Padrão: protocolo://domínio/caminho?query#fragmento
    // Captura qualquer caractere válido em URL até encontrar espaço, quebra de linha ou pontuação final
    const urlRegex = /(https?:\/\/[^\s\n<>"']+|www\.[^\s\n<>"']+)/gi;

    // Dividir o texto em partes (texto e URLs)
    const parts = [];
    let lastIndex = 0;
    let match;

    // Resetar regex para garantir que funciona corretamente
    urlRegex.lastIndex = 0;

    while ((match = urlRegex.exec(text)) !== null) {
      // Adicionar texto antes da URL
      if (match.index > lastIndex) {
        parts.push({ type: 'text', content: text.substring(lastIndex, match.index) });
      }

      // Adicionar a URL (remover caracteres inválidos no final se houver)
      let urlContent = match[0];
      // Remover pontuação final comum que não faz parte da URL
      urlContent = urlContent.replace(/[.,;:!?]+$/, '');

      parts.push({ type: 'url', content: urlContent });

      lastIndex = match.index + match[0].length;
    }

    // Adicionar texto restante
    if (lastIndex < text.length) {
      parts.push({ type: 'text', content: text.substring(lastIndex) });
    }

    // Se não encontrou URLs, retornar texto original
    if (parts.length === 0) {
      return text;
    }

    // Renderizar partes como elementos React
    return parts.map((part, index) => {
      if (part.type === 'url') {
        // Adicionar protocolo se não tiver
        let url = part.content.trim();
        if (!url.startsWith('http://') && !url.startsWith('https://')) {
          url = 'https://' + url;
        }

        return (
          <a
            key={index}
            href={url}
            target="_blank"
            rel="noopener noreferrer"
            className="underline transition-colors break-all"
            onClick={(e) => e.stopPropagation()}
            style={{
              wordBreak: 'break-all',
              color: '#7DD3FC',
              textDecoration: 'underline',
              textDecorationColor: '#7DD3FC'
            }}
            onMouseEnter={(e) => {
              e.target.style.color = '#5BC0EB';
              e.target.style.textDecorationColor = '#5BC0EB';
            }}
            onMouseLeave={(e) => {
              e.target.style.color = '#7DD3FC';
              e.target.style.textDecorationColor = '#7DD3FC';
            }}
          >
            {part.content}
          </a>
        );
      }
      return <span key={index}>{part.content}</span>;
    });
  };

  //  USAR LIMPEZA DE DUPLICATAS NO RENDER
  const uniqueMessages = cleanDuplicateMessages(messages);

  // Filtrar mensagens apenas para atendentes se o usuário atual for cliente
  const isViewingAsAgent = user && (user.user_type === 'superadmin' || user.user_type === 'admin' || user.user_type === 'agent');
  const filteredMessages = isViewingAsAgent
    ? uniqueMessages
    : uniqueMessages.filter(msg => !msg.additional_attributes?.apenas_atendentes);

  // Guards de segurança APÓS todos os hooks (Regra dos Hooks do React)
  if (!conversation) {
    return (
      <div className="flex-1 flex items-center justify-center bg-background">
        <div className="text-center max-w-md mx-auto px-4">
          <div className="mb-6">
            <img src={logoImage} alt="NioChat Logo" className="w-32 h-32 mx-auto object-contain" />
          </div>
          <p className="text-base text-muted-foreground mb-2">Selecione uma conversa para iniciar o atendimento</p>
          <p className="text-sm text-muted-foreground leading-relaxed">Os atendimentos em andamento aparecerão aqui.</p>
        </div>
      </div>
    );
  }

  if (!conversation.contact) {
    return (
      <div className="flex-1 flex items-center justify-center bg-background">
        <div className="text-center text-muted-foreground">
          <h3 className="text-lg font-medium mb-2">Conversa inválida</h3>
          <p>Esta conversa não possui informações de contato válidas</p>
        </div>
      </div>
    );
  }

  if (!user) {
    return (
      <div className="flex-1 flex items-center justify-center bg-background">
        <div className="text-center">
          <div className="w-12 h-12 border-4 border-primary border-t-transparent rounded-full animate-spin mx-auto mb-4" />
          <p className="text-muted-foreground">Carregando dados do usuário...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="flex-1 flex flex-row overflow-hidden bg-background">
      {/* Área Principal do Chat (Lado Esquerdo) */}
      <div className="flex-1 flex flex-col relative overflow-hidden bg-background border-r">
        {/* Header da conversa */}
        <div className="border-b border-border p-4 bg-card">
          <div className="flex items-center justify-between">
          <div className="flex items-center space-x-3">
            <div className="flex-shrink-0">
              <div className="w-10 h-10 rounded-full flex items-center justify-center overflow-hidden bg-primary/10">
                {conversation.contact?.avatar ? (
                  <img
                    src={conversation.contact.avatar}
                    alt={conversation.contact.name}
                    className="w-full h-full object-cover"
                    onError={(e) => {
                      e.target.style.display = 'none';
                      e.target.nextSibling.style.display = 'flex';
                    }}
                  />
                ) : null}
                <User 
                  size={20} 
                  className={`text-primary ${conversation.contact?.avatar ? 'hidden' : 'block'}`} 
                />
              </div>
            </div>

            <div className="flex-1">
              <div className="flex items-center space-x-2">
                <h3 className="font-medium text-foreground">
                  {(() => {
                    // SEMPRE priorizar nome do contato quando disponível
                    // Usar estado local (pode ser atualizado via WebSocket) ou nome da prop
                    const displayName = (contactName && contactName.trim()) || conversation.contact?.name?.trim();
                    const contactPhone = conversation.contact?.phone;

                    // Se tem nome válido (mesmo que seja igual ao telefone), usar o nome
                    if (displayName && displayName.length > 0) {
                      return displayName;
                    }

                    // Caso contrário, exibir telefone
                    return contactPhone || 'Contato sem nome';
                  })()}
                </h3>
                <div className="flex items-center space-x-1 text-xs text-muted-foreground">
                  {getChannelIcon(conversation.inbox?.channel_type)}
                  <span className="font-medium">
                    Canal: {getChannelDisplayName(conversation.inbox)}
                  </span>
                </div>
              </div>
              {conversation.contact?.phone && (
                <p className="text-sm text-muted-foreground">
                  {(() => {
                    // Exibir telefone sempre que disponível
                    const contactName = conversation.contact?.name?.trim();
                    const contactPhone = conversation.contact?.phone;

                    // Exibir telefone sempre (é útil para identificar o contato)
                    return contactPhone;
                  })()}
                </p>
              )}
            </div>
          </div>

          <div className="flex items-center space-x-2">

            {/* Toggle SGP Sidebar */}
            <button
                onClick={() => setShowSgpSidebar(!showSgpSidebar)}
                className={`p-2 ml-1 rounded-lg transition-all duration-300 ${showSgpSidebar ? 'bg-white/10 text-white' : 'text-muted-foreground hover:bg-white/5 hover:text-white'}`}
                title={showSgpSidebar ? "Fechar painel SGP" : "Abrir painel SGP"}
            >
                <Database size={19} />
            </button>

            {/* Botões de Ação Diretos */}
            <div className="flex items-center space-x-1 border-l border-white/5 pl-2 ml-2">
              <button
                onClick={handleAssignToMe}
                className="p-2 text-muted-foreground hover:bg-white/5 hover:text-white rounded-lg transition-all flex items-center space-x-2 group"
                title="Atribuir para mim"
              >
                <UserCheck className="w-4 h-4 group-hover:scale-110 transition-transform" />
                <span className="text-xs font-medium text-nowrap">Atribuir</span>
              </button>
              
              <button
                onClick={handleTransferConversation}
                disabled={loadingAgents}
                className="p-2 text-muted-foreground hover:bg-white/5 hover:text-white rounded-lg transition-all flex items-center space-x-2 disabled:opacity-50 group"
                title="Transferir conversa"
              >
                <ArrowRightLeft className="w-4 h-4 group-hover:rotate-180 transition-transform duration-500" />
                <span className="text-xs font-medium text-nowrap">Transferir</span>
              </button>

              <button
                onClick={handleCloseConversation}
                className="p-2 text-red-400 hover:bg-red-500/10 hover:text-red-500 rounded-lg transition-all flex items-center space-x-2 group"
                title="Encerrar conversa"
              >
                <CheckCircle2 className="w-4 h-4 group-hover:scale-110 transition-transform" />
                <span className="text-xs font-medium text-nowrap">Encerrar</span>
              </button>
            </div>
          </div>
        </div>
      </div>

      {/* Lista de mensagens */}
      <div
        ref={scrollContainerRef}
        onScroll={handleScrollContainer}
        className="relative flex-1 overflow-y-auto overflow-x-hidden p-4 dark:bg-background bg-[#efeae2]"
        style={{
          minHeight: '200px',
          // Tema de fundo estilo WhatsApp (imagem enviada)
          backgroundImage: `url(${isDarkTheme ? chatBgPattern : chatBgPatternLight})`,
          backgroundRepeat: 'no-repeat',
          backgroundSize: 'cover',
          backgroundPosition: 'center center',
          opacity: 1
        }}
      >
        {/* Conteúdo das mensagens */}
        <div className="relative space-y-4">
          {loading && (
            <div className="flex justify-center">
              <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary"></div>
            </div>
          )}

          {error && (
            <div className={`text-center p-3 rounded-lg mb-2 ${error.includes('24 horas') || error.includes('janela de atendimento') || error.includes('⚠️')
              ? 'text-amber-600 dark:text-amber-400 bg-amber-50 dark:bg-amber-950 border border-amber-200 dark:border-amber-800'
              : 'text-red-500 bg-red-50 dark:bg-red-950 border border-red-200 dark:border-red-800'
              }`}>
              <div className="font-medium">{error}</div>
            </div>
          )}

          {hideWaitingQueueContent ? (
            <div className="mx-auto max-w-lg rounded-xl border border-amber-500/35 bg-amber-950/35 px-5 py-6 text-center text-amber-50 shadow-sm">
              <p className="text-base font-semibold">Conteúdo protegido</p>
              <p className="mt-2 text-sm leading-relaxed text-amber-100/90">
                Sem permissão para ver mensagens desta conversa enquanto ela estiver na fila de espera sem atendente.
                Use <span className="font-medium text-amber-50">Atribuir</span> para assumir o atendimento e visualizar o histórico.
              </p>
            </div>
          ) : filteredMessages.length === 0 ? (
            <div className="text-center text-muted-foreground py-8">
              <p>Nenhuma mensagem encontrada</p>
            </div>
          ) : (
            filteredMessages.map((msg) => {
              const attachmentList = Array.isArray(msg.attachments) ? msg.attachments : [];
              const hasRenderableAttachments = attachmentList.length > 0;
              const content = msg.content || '';
              const isCustomer = msg.is_from_customer;
              // CORREÇÃO: Identificar mensagens da IA corretamente - verificação mais robusta
              const isAI = !isCustomer && (
                msg.sender?.sender_type === 'ai' ||
                msg.from_ai === true ||
                msg.additional_attributes?.from_ai === true
              );

              const isBot = !isCustomer && !isAI && (msg.message_type === 'incoming' || msg.sender?.sender_type === 'bot');
              const isAgent = !isCustomer && !isBot && !isAI;
              const isSystemMessage = msg.additional_attributes?.system_message || msg.content?.includes('Conversa atribuída para');
              const isResumoSuporte = msg.additional_attributes?.tipo === 'resumo_suporte' || msg.additional_attributes?.apenas_atendentes;
              const isLarge = isLargeMessage(content);
              const isAgentAudioPlaceholderText =
                !isCustomer &&
                (msg.message_type === 'audio' || msg.message_type === 'ptt') &&
                (content || '').trim() === 'Mensagem de voz';

              // Determinar se a mensagem tem mídia
              const hasImage = attachmentList.some(att => att.file_type === 'image') ||
                (msg.message_type === 'image' && msg.file_url);
              const hasVideo = attachmentList.some(att => att.file_type === 'video') ||
                (msg.message_type === 'video' && msg.file_url);
              const hasAudio = attachmentList.some(att => att.file_type === 'audio') ||
                ((msg.message_type === 'audio' || msg.message_type === 'ptt') && msg.file_url);
              const hasDocument = attachmentList.some(att => att.file_type === 'file') ||
                (msg.message_type === 'document' && msg.file_url);

              /** Eco smb_message_echoes: texto/mídia enviados pelo WhatsApp Business no celular */
              const showWhatsAppPhoneSentBadge =
                !isCustomer &&
                msg.additional_attributes?.source === 'whatsapp_business_app';

              const isReplyHighlight =
                highlightTargetMessageId != null &&
                Number(highlightTargetMessageId) === Number(msg.id);

              // Debug: logar dados da mensagem
              if (msg.message_type === 'image' || attachmentList.some(att => att.file_type === 'image')) {
                // Debug removido
              }

              return (
                <div
                  key={msg.id}
                  data-chat-message-id={msg.id}
                  className={`flex ${getMessageAlignment(msg, content)} group mb-4 min-w-0`}
                >
                  <div className={`max-w-[70%] min-w-0 ${getMessageOrder(msg, content)}`}>
                    <div
                      className={`
                  relative px-5 py-3 shadow-sm rounded-2xl
                  ${isReplyHighlight ? 'ring-2 ring-amber-400 dark:ring-amber-300 z-[1]' : ''}
                  ${isCustomer
                        ? 'bg-[#4A5568] text-white'  // Mensagens recebidas (cliente)
                        : isResumoSuporte
                          ? 'bg-[#FFF9C4] text-[#856404] border border-[#FFE69C]'  // Resumo suporte - amarelo fraco
                          : isAI || isBot || isSystemMessage
                            ? 'bg-[#2196F3] text-white'  // IA / bot / sistema
                            : 'bg-[#2196F3] text-white'  // Mensagens do agente (envio) - igual ao exemplo
                      }
                `}
                    >
                      {isReplyHighlight && (
                        <div
                          className={`pointer-events-none absolute top-3 bottom-3 w-[3px] rounded-full bg-amber-300 shadow-[0_0_14px_rgba(252,211,77,0.95)] z-[2] animate-pulse ${
                            isCustomer ? 'left-2' : 'right-2'
                          }`}
                          aria-hidden
                        />
                      )}
                      {/* Resposta a mensagem anterior — clique leva até a mensagem citada */}
                      {msg.additional_attributes?.is_reply && (
                        <div
                          role="button"
                          tabIndex={0}
                          title="Ir para a mensagem citada"
                          onClick={(e) => {
                            e.stopPropagation();
                            scrollToReplyTarget(msg.additional_attributes?.reply_to_message_id);
                          }}
                          onKeyDown={(e) => {
                            if (e.key === 'Enter' || e.key === ' ') {
                              e.preventDefault();
                              e.stopPropagation();
                              scrollToReplyTarget(msg.additional_attributes?.reply_to_message_id);
                            }
                          }}
                          className={`mb-2 p-2 rounded-lg text-xs cursor-pointer select-none transition-opacity hover:opacity-100 focus:outline-none focus-visible:ring-2 focus-visible:ring-white/70 ${
                            isCustomer ? 'bg-white/30' : 'bg-black/10'
                          } opacity-90`}
                        >
                          <div className="font-medium">{isCustomer ? 'Resposta a:' : 'Respondendo a:'}</div>
                          <div className="truncate">
                            {msg.additional_attributes.reply_to_content || 'Mensagem anterior'}
                          </div>
                        </div>
                      )}

                      {/* Anexos de imagem */}
                      {hasImage && hasRenderableAttachments && attachmentList.filter(att => att.file_type === 'image').map((attachment, index) => (
                        <div key={index} className="mb-2">
                          <img
                            src={attachment.data_url}
                            alt="Imagem"
                            className="max-w-full h-auto rounded-lg cursor-pointer hover:opacity-90 transition-opacity"
                            onClick={() => openImageModal(attachment.data_url)}
                            style={{ maxHeight: '300px' }}
                          />

                        </div>
                      ))}

                      {/* Imagens via file_url (WhatsApp/Telegram etc) - só se não tiver attachments */}
                      {hasImage && msg.message_type === 'image' && msg.file_url && !hasRenderableAttachments && (
                        <div className="mb-2">
                          <img
                            src={buildMediaUrl(msg.file_url)}
                            alt="Imagem"
                            className="max-w-full h-auto rounded-lg cursor-pointer hover:opacity-90 transition-opacity"
                            onClick={() => openImageModal(buildMediaUrl(msg.file_url))}
                            style={{ maxHeight: '300px' }}
                            onError={(e) => {
                              console.error('Erro ao carregar imagem:', msg.file_url);
                              e.target.style.display = 'none';
                            }}
                          />

                        </div>
                      )}

                      {/* Anexos de vídeo */}
                      {hasVideo && hasRenderableAttachments && attachmentList.filter(att => att.file_type === 'video').map((attachment, index) => (
                        <div key={index} className="mb-2">
                          <video
                            controls
                            className="max-w-full h-auto rounded-lg"
                            style={{ maxHeight: '300px' }}
                          >
                            <source src={attachment.data_url} type="video/mp4" />
                            Seu navegador não suporta o elemento de vídeo.
                          </video>

                        </div>
                      ))}

                      {/* Vídeos via file_url - só se não tiver attachments */}
                      {hasVideo && msg.message_type === 'video' && msg.file_url && !hasRenderableAttachments && (
                        <div className="mb-2">
                          <video
                            controls
                            className="max-w-full h-auto rounded-lg"
                            style={{ maxHeight: '300px' }}
                            onError={(e) => {
                              console.error('Erro ao carregar vídeo:', msg.file_url);
                            }}
                          >
                            <source src={buildMediaUrl(msg.file_url)} type="video/mp4" />
                            Seu navegador não suporta o elemento de vídeo.
                          </video>

                        </div>
                      )}

                      {/* Anexos de áudio */}
                      {hasAudio && hasRenderableAttachments && attachmentList.filter(att => att.file_type === 'audio').map((attachment, index) => (
                        <div key={index} className="mb-2">
                          <CustomAudioPlayer
                            src={attachment.data_url}
                            isCustomer={isCustomer}
                            conversationId={conversation?.id}
                          />

                        </div>
                      ))}

                      {/* Áudios via file_url (só se não tiver attachments) */}
                      {hasAudio && (msg.message_type === 'audio' || msg.message_type === 'ptt') && msg.file_url && !hasRenderableAttachments && (
                        <div className="mb-2">
                          <CustomAudioPlayer
                            src={buildMediaUrl(msg.file_url)}
                            isCustomer={isCustomer}
                            conversationId={conversation?.id}
                          />

                        </div>
                      )}

                      {/* Anexos de documento */}
                      {hasDocument && hasRenderableAttachments && attachmentList.filter(att => att.file_type === 'file').map((attachment, index) => (
                        <div key={index} className="mb-2">
                          <a
                            href={attachment.data_url}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="flex items-center space-x-2 p-2 bg-black/10 rounded-lg hover:bg-black/20 transition-colors"
                          >
                            <Paperclip className="w-4 h-4" />
                            <span className="text-sm">{attachment.file_name || 'Documento'}</span>
                          </a>

                        </div>
                      ))}

                      {/* Documentos via file_url - só se não tiver attachments */}
                      {hasDocument && msg.message_type === 'document' && msg.file_url && !hasRenderableAttachments && (
                        <div className="mb-2">
                          <FilePreview
                            file={{
                              url: msg.file_url,
                              name: msg.file_name || msg.content || 'Documento',
                              size: msg.file_size,
                              type: msg.additional_attributes?.file_type || 'application/pdf',
                              pages: msg.additional_attributes?.pages,
                              jpegThumbnail: msg.additional_attributes?.pdf_thumbnail,
                              uazapi_url: msg.additional_attributes?.file_url,
                              additional_attributes: msg.additional_attributes
                            }}
                            isCustomer={isCustomer}
                            content={msg.content}
                          />

                        </div>
                      )}

                      {/* QR Codes PIX */}
                      {msg.message_type === 'image' && msg.content && msg.content.includes('QR Code PIX') && (
                        <div className="mb-2 p-3 bg-green-50 dark:bg-green-900/20 rounded-lg border border-green-200 dark:border-green-800">
                          <div className="text-sm font-medium text-green-900 dark:text-green-100 mb-2">
                            🎯 QR Code PIX
                          </div>
                          <div className="text-xs text-green-700 dark:text-green-300 mb-2">
                            Escaneie este QR code com o app do seu banco para pagar via PIX
                          </div>
                          {msg.file_url && (
                            <div className="bg-white p-2 rounded border">
                              <img
                                src={buildMediaUrl(msg.file_url)}
                                alt="QR Code PIX"
                                className="w-32 h-32 mx-auto"
                                onError={(e) => {
                                  e.target.style.display = 'none';
                                  e.target.nextSibling.style.display = 'block';
                                }}
                              />
                              <div className="hidden text-center text-xs text-gray-500">
                                QR Code PIX (imagem não disponível)
                              </div>
                            </div>
                          )}
                        </div>
                      )}

                      {/* Links de boleto */}
                      {msg.content && msg.content.includes('🔗') && msg.content.includes('Link do Boleto:') && (
                        <div className="mb-2 p-3 bg-orange-50 dark:bg-orange-900/20 rounded-lg border border-orange-200 dark:border-orange-800">
                          <div className="text-sm font-medium text-orange-900 dark:text-orange-100 mb-2">
                            📄 Boleto Bancário
                          </div>
                          <div className="text-xs text-orange-700 dark:text-orange-300 mb-2">
                            Clique no link abaixo para acessar o boleto completo
                          </div>
                          {msg.content.split('\n').map((line, index) => {
                            if (line.includes('https://')) {
                              return (
                                <a
                                  key={index}
                                  href={line.trim()}
                                  target="_blank"
                                  rel="noopener noreferrer"
                                  className="block w-full px-3 py-2 bg-orange-600 text-white rounded-lg hover:bg-orange-700 transition-colors text-sm text-center"
                                >
                                  📥 Baixar Boleto PDF
                                </a>
                              );
                            }
                            return null;
                          })}
                        </div>
                      )}

                      {/* Botões interativos (como "Copiar Chave PIX") */}
                      {msg.additional_attributes?.has_buttons && msg.additional_attributes?.button_choices && (
                        <div className="mt-3 space-y-2">
                          {msg.additional_attributes.button_choices.map((choice, index) => {
                            const [nome, acao] = choice.split('|', 2);
                            if (acao && acao.startsWith('copy:')) {
                              const textoParaCopiar = acao.replace('copy:', '');
                              return (
                                <button
                                  key={index}
                                  onClick={() => {
                                    navigator.clipboard.writeText(textoParaCopiar);
                                    // Mostrar feedback visual
                                    const btn = event.target;
                                    const originalText = btn.textContent;
                                    btn.textContent = '✅ Copiado!';
                                    btn.className = 'w-full px-4 py-2 bg-gradient-to-r from-orange-500 to-yellow-500 hover:from-orange-600 hover:to-yellow-600 text-white rounded-lg shadow-lg hover:shadow-xl transition-all duration-200 text-sm font-medium';
                                    setTimeout(() => {
                                      btn.textContent = originalText;
                                      btn.className = 'w-full px-4 py-2 bg-foreground text-background hover:opacity-90 rounded-lg shadow-md transition-all duration-200 text-sm font-bold';
                                    }, 2000);
                                  }}
                                  className="w-full px-4 py-2 bg-foreground text-background hover:opacity-90 rounded-lg shadow-md transition-all duration-200 text-sm font-bold"
                                >
                                  {nome}
                                </button>
                              );
                            }
                            return null;
                          })}
                        </div>
                      )}

                      {/* Lista interativa do chatbot (menu/planos) */}
                      {msg.additional_attributes?.interactive_rows && msg.additional_attributes.interactive_rows.length > 0 && (
                        <div className="mt-3 space-y-1.5">
                          <div className="text-[10px] font-bold text-slate-400 dark:text-slate-500 uppercase tracking-wider mb-2">
                            Opções da lista do menu
                          </div>
                          {msg.additional_attributes.interactive_rows.map((row, index) => (
                            <div
                              key={row.id || index}
                              className="px-3 py-2 bg-white/10 dark:bg-slate-700/50 border border-slate-200/20 dark:border-slate-600/30 rounded-lg"
                            >
                              <div className="text-xs font-bold text-foreground">
                                {row.title}
                              </div>
                              {row.description && (
                                <div className="text-[10px] text-slate-500 dark:text-slate-400 mt-0.5">
                                  {row.description}
                                </div>
                              )}
                            </div>
                          ))}
                        </div>
                      )}

                      {/* Botões interativos do chatbot (Menu) */}
                      {msg.additional_attributes?.interactive_buttons && msg.additional_attributes.interactive_buttons.length > 0 && (
                        <div className="mt-3 space-y-1.5">
                          {msg.additional_attributes.interactive_buttons.map((btn, index) => (
                            <div
                              key={btn.id || index}
                              className="px-3 py-2 bg-blue-500/10 dark:bg-blue-500/20 border border-blue-300/30 dark:border-blue-600/30 rounded-lg text-center"
                            >
                              <span className="text-xs font-bold text-blue-600 dark:text-blue-400">
                                {btn.title}
                              </span>
                            </div>
                          ))}
                        </div>
                      )}

                      {/* Renderizador de Card de Pagamento Estilo WhatsApp Nativo (DINÂMICO) */}
                      {(msg.additional_attributes?.is_invoice || 
                        (content && content.includes('dados para pagamento de sua fatura'))) && (
                        <div className="mt-4 mb-2 overflow-hidden rounded-xl bg-[#1f2c34] text-[#d1d7db] shadow-lg max-w-[320px] border border-[#2a3942]">
                          {/* Header Simples */}
                          <div className="px-4 py-3 border-b border-[#2a3942]">
                            <p className="text-[11px] text-[#8696a0] font-medium">Nº da cobrança: {msg.additional_attributes?.invoice_number || (content.match(/Nº DA COBRANÇA:\s?(\d+)/i)?.[1] || 'SGP-' + msg.id.toString().slice(-4))}</p>
                          </div>

                          {/* Conteúdo Principal Estilo Zap */}
                          <div className="p-4 space-y-4">
                            <div>
                              <p className="text-lg font-bold text-white">{msg.additional_attributes?.invoice_number || (content.match(/Nº DA COBRANÇA:\s?(\d+)/i)?.[1] || 'Fatura')}</p>
                              <p className="text-xs text-[#8696a0]">Quantidade: 1</p>
                            </div>

                            <div className="flex items-center justify-between py-2 border-t border-b border-[#2a3942] border-dashed">
                              <p className="text-sm">Pagar com</p>
                              <div className="flex items-center justify-center">
                                {msg.additional_attributes?.payment_type === 'pix' ? (
                                  <div className="bg-[#00a884]/10 p-1 rounded">
                                    <svg width="24" height="24" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg" className="w-5 h-5 text-[#00a884]">
                                      <path d="M12 2L4 12L12 22L20 12L12 2Z" fill="currentColor" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
                                      <path d="M12 7L7 12L12 17L17 12L12 7Z" fill="white" />
                                    </svg>
                                  </div>
                                ) : (
                                  <div className="bg-[#00a884]/10 p-1 rounded">
                                    <Barcode className="w-5 h-5 text-[#00a884]" />
                                  </div>
                                )}
                              </div>
                            </div>

                            <div className="flex items-center justify-between text-sm">
                              <p>Total</p>
                              <div className="text-right">
                                <p className="font-bold text-white">
                                  R$ {msg.additional_attributes?.amount || (content.match(/VALOR:\s?R\$\s?([\d,.]+)/i)?.[1] || content.match(/R\$\s?[\d,.]+/)?.[0]?.replace('R$', '') || '0,00')}
                                </p>
                                {msg.additional_attributes?.vencimento && (
                                  <p className="text-[10px] text-[#8696a0]">
                                    Vence em: {(() => {
                                      const d = msg.additional_attributes.vencimento;
                                      if (d.includes('/')) return d;
                                      const parts = d.split('-');
                                      return parts.length === 3 ? `${parts[2]}/${parts[1]}/${parts[0]}` : d;
                                    })()}
                                  </p>
                                )}
                              </div>
                            </div>

                            <div className="space-y-1">
                              <p className="text-xs font-bold text-[#d1d7db]">
                                Pagar com {msg.additional_attributes?.payment_type === 'pix' ? 'PIX' : 'Boleto'}: 👇
                              </p>
                              <ol className="text-[11px] text-[#8696a0] space-y-1 ml-0.5">
                                {msg.additional_attributes?.payment_type === 'pix' ? (
                                  <>
                                    <li>1. Copie o código PIX abaixo;</li>
                                    <li>2. Abra o aplicativo do seu banco;</li>
                                    <li>3. Cole o código e finalize o pagamento.</li>
                                  </>
                                ) : (
                                  <>
                                    <li>1. Copie o código do boleto abaixo;</li>
                                    <li>2. Use o aplicativo do seu banco para pagar.</li>
                                  </>
                                )}
                              </ol>
                            </div>
                            
                            <p className="text-[10px] text-[#8696a0] font-bold uppercase tracking-wider">
                              {conversation?.inbox?.provedor?.nome || conversation?.inbox?.provedor?.razao_social || 'NIO NET'}
                            </p>
                          </div>

                          {/* Botões de Cópia Estilo Nativo (Verde) */}
                          <div className="border-t border-[#2a3942]">
                            {/* Botão Copiar para PIX */}
                            {(msg.additional_attributes?.payment_type === 'pix' || (content && content.includes('PIX'))) && (
                              <button
                                onClick={(e) => {
                                  e.stopPropagation();
                                  const pixCode = msg.additional_attributes?.pix_code || 
                                                 msg.additional_attributes?.button_choices?.[0]?.split('copy:')[1] || 
                                                 content.split('copy:')[1]?.split('\n')[0] ||
                                                 '';
                                  if (pixCode) {
                                    navigator.clipboard.writeText(pixCode.trim());
                                    const btn = e.currentTarget;
                                    const span = btn.querySelector('span:last-child');
                                    const originalText = span.textContent;
                                    span.textContent = 'Código Pix copiado!';
                                    setTimeout(() => span.textContent = originalText, 2000);
                                  }
                                }}
                                className="w-full py-4 hover:bg-[#2a3942] flex items-center justify-center space-x-2 transition-colors group"
                              >
                                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" className="text-[#06cf9c]">
                                  <rect x="9" y="9" width="13" height="13" rx="2" ry="2"></rect>
                                  <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path>
                                </svg>
                                <span className="text-sm font-bold text-[#06cf9c]">Copiar código Pix</span>
                              </button>
                            )}

                            {/* Botão Copiar para Boleto */}
                            {(msg.additional_attributes?.payment_type === 'boleto' || (content && content.includes('Boleto'))) && (
                              <button
                                onClick={(e) => {
                                  e.stopPropagation();
                                  const lineCode = msg.additional_attributes?.line_code || 
                                                  msg.additional_attributes?.button_choices?.[1]?.split('copy:')[1] || 
                                                  '';
                                  if (lineCode) {
                                    navigator.clipboard.writeText(lineCode.trim());
                                    const btn = e.currentTarget;
                                    const span = btn.querySelector('span:last-child');
                                    const originalText = span.textContent;
                                    span.textContent = 'Código do boleto copiado!';
                                    setTimeout(() => span.textContent = originalText, 2000);
                                  }
                                  
                                  // Se houver PDF, abrir ao clicar
                                  const pdfUrl = msg.additional_attributes?.document_url || msg.file_url;
                                  if (pdfUrl) window.open(pdfUrl, '_blank');
                                }}
                                className="w-full py-4 hover:bg-[#2a3942] flex items-center justify-center space-x-2 transition-colors border-t border-[#2a3942]"
                              >
                                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" className="text-[#06cf9c]">
                                  <rect x="9" y="9" width="13" height="13" rx="2" ry="2"></rect>
                                  <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path>
                                </svg>
                                <span className="text-sm font-bold text-[#06cf9c]">Copiar código do boleto</span>
                              </button>
                            )}
                          </div>
                        </div>
                      )}

                      {/* Conteúdo da mensagem (Texto) */}
                      {content && 
                       !isAgentAudioPlaceholderText &&
                       !(msg.additional_attributes?.is_invoice || 
                        (content && content.includes('dados para pagamento de sua fatura'))) && (
                        <div className="whitespace-pre-wrap break-words break-all" style={{ wordBreak: 'break-word', overflowWrap: 'anywhere' }}>
                          {(() => {
                            const displayContent = !isCustomer && content.includes('*') && content.includes('disse:*')
                              ? content.split('\n').slice(1).join('\n').trim() || content
                              : content;
                            return renderMessageWithLinks(displayContent);
                          })()}
                        </div>
                      )}

                      {/* Mostrar apenas a última reação recebida ou enviada */}
                      {msg.reactions && msg.reactions.length > 0 && (() => {
                        // Ordenar reações por data (mais recente primeiro) e pegar apenas a última
                        const sortedReactions = [...msg.reactions].sort((a, b) => {
                          const dateA = new Date(a.created_at || 0);
                          const dateB = new Date(b.created_at || 0);
                          return dateB - dateA;
                        });
                        const lastReaction = sortedReactions[0];

                        return (
                          <div className="mt-2 flex items-center">
                            <div
                              className={`rounded-full px-2 py-1 text-xs flex items-center space-x-1 ${isCustomer
                                ? 'bg-black/10'
                                : 'bg-white/20'
                                }`}
                            >
                              <span>{lastReaction.emoji}</span>
                              <span className="text-xs opacity-75">✓</span>
                            </div>
                          </div>
                        );
                      })()}

                      {/* Fallback para reações antigas em additional_attributes (compatibilidade) */}
                      {(!msg.reactions || msg.reactions.length === 0) && (
                        ((msg.additional_attributes?.reaction) ||
                          (isCustomer && msg.additional_attributes?.agent_reaction) ||
                          (!isCustomer && msg.additional_attributes?.received_reactions?.[0]?.emoji) ||
                          (isCustomer && msg.additional_attributes?.received_reactions?.[0]?.emoji)) && (
                          <div className="mt-2 flex items-center space-x-1 flex-wrap">
                            {/* Reação existente */}
                            {msg.additional_attributes?.reaction && (
                              <div className="bg-white/20 rounded-full px-2 py-1 text-xs flex items-center space-x-1">
                                <span>{msg.additional_attributes.reaction.emoji}</span>
                                <span className="text-xs opacity-75">
                                  {msg.additional_attributes.reaction.status === 'sent' ? '✓' : '⏳'}
                                </span>
                              </div>
                            )}

                            {/* Reação do agente para mensagens do cliente */}
                            {isCustomer && msg.additional_attributes?.agent_reaction && (
                              <div className="bg-white/20 rounded-full px-2 py-1 text-xs flex items-center space-x-1">
                                <span>{msg.additional_attributes.agent_reaction.emoji}</span>
                                <span className="text-xs opacity-75">✓</span>
                              </div>
                            )}

                            {/* Reação do cliente para mensagens do agente */}
                            {!isCustomer && msg.additional_attributes?.received_reactions?.[0]?.emoji && (
                              <div className="bg-white/20 rounded-full px-2 py-1 text-xs flex items-center space-x-1">
                                <span>{msg.additional_attributes.received_reactions[0].emoji}</span>
                                <span className="text-xs opacity-75">✓</span>
                              </div>
                            )}

                            {/* Reação do cliente nas próprias mensagens */}
                            {isCustomer && msg.additional_attributes?.received_reactions?.[0]?.emoji && (
                              <div className="bg-white/20 rounded-full px-2 py-1 text-xs flex items-center space-x-1">
                                <span>{msg.additional_attributes.received_reactions[0].emoji}</span>
                                <span className="text-xs opacity-75">✓</span>
                              </div>
                            )}
                          </div>
                        )
                      )}

                      {/* Timestamp (canto inferior esquerdo da bolha) + status e ações à direita */}
                      <div className="flex w-full min-w-0 items-center justify-between gap-2 mt-1">
                        <div
                          className={`flex min-w-0 flex-wrap items-center gap-x-2 gap-y-0.5 text-left text-xs ${isCustomer ? 'text-muted-foreground' : 'text-white'}`}
                        >
                          <span className="inline-flex items-center gap-1 shrink-0">
                            {new Date(msg.created_at || msg.timestamp).toLocaleString('pt-BR', {
                              hour: '2-digit',
                              minute: '2-digit',
                              day: '2-digit',
                              month: '2-digit'
                            })}
                            {showWhatsAppPhoneSentBadge && (
                              <Smartphone
                                className={`h-3.5 w-3.5 shrink-0 opacity-90 ${isCustomer ? '' : 'text-white'}`}
                                title="Enviado pelo WhatsApp no celular (fora do painel NioChat)"
                                aria-label="Enviado pelo WhatsApp no celular"
                              />
                            )}
                          </span>
                          {msg.isTemporary && (
                            <span className="opacity-60">Enviando...</span>
                          )}
                        </div>
                        <div className="flex shrink-0 items-center gap-0.5">
                          {!isCustomer && isWhatsAppChannel && !msg.isTemporary && (
                            <MessageStatusIcon
                              key={`status-${msg.id}-${msg.additional_attributes?.last_status || 'pending'}`}
                              message={msg}
                            />
                          )}
                          <button
                            type="button"
                            onClick={() => openReactionPicker(msg)}
                            className={`rounded-full p-1 text-xs hover:bg-white/20 ${isCustomer ? 'hover:bg-black/10' : ''}`}
                            title="Reagir à mensagem"
                          >
                            😊
                          </button>
                          <button
                            type="button"
                            onClick={() => handleReplyToMessage(msg)}
                            className={`rounded-full p-1 text-xs hover:bg-white/20 ${isCustomer ? 'hover:bg-black/10' : ''}`}
                            title="Responder mensagem"
                          >
                            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                              <path d="M9 17l-5-5 5-5M20 12H4" />
                            </svg>
                          </button>
                        </div>
                      </div>
                    </div>
                  </div>
                </div>
              );
            })
          )}

          <div ref={messagesEndRef} />
        </div>
      </div>

      {/* Área de resposta */}
      {replyingToMessage && (
        <div className="border-t border-border bg-accent/50 p-3">
          <div className="flex items-center justify-between">
            <div className="flex-1">
              <div className="text-xs text-muted-foreground mb-1">Respondendo a:</div>
              <div className="text-sm truncate">
                {replyingToMessage.content || 'Mensagem'}
              </div>
            </div>
            <button
              onClick={cancelReply}
              className="p-1 hover:bg-accent rounded text-muted-foreground transition-colors"
            >
              ✕
            </button>
          </div>
        </div>
      )}

      {/* Preview de áudio gravado */}
      {audioUrl && (
        <div className="border-t border-border bg-accent/50 p-3">
          <div className="flex items-center justify-between">
            <div className="flex items-center space-x-3">
              <div className="text-sm font-medium">Áudio gravado</div>
              <audio controls src={audioUrl} className="h-8" />
            </div>
            <div className="flex items-center space-x-2">
              <button
                onClick={sendAudioMessage}
                disabled={sendingMedia}
                className="px-4 py-2 bg-foreground text-background hover:opacity-90 rounded-lg shadow-md transition-all duration-200 disabled:opacity-50 text-sm font-bold"
              >
                {sendingMedia ? 'Enviando...' : 'Enviar'}
              </button>
              <button
                onClick={() => {
                  setAudioBlob(null);
                  setAudioUrl(null);
                  setRecordingTime(0);
                }}
                className="px-3 py-1 bg-red-500 text-white rounded-lg hover:bg-red-600 text-sm"
              >
                Cancelar
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Prévia de Mídia Pendente */}
      {pendingFile && (
        <div className="border-t border-border bg-card p-4 animate-in slide-in-from-bottom-2">
          <div className="flex flex-col space-y-4 max-w-lg mx-auto bg-muted/30 p-4 rounded-xl border border-border/50">
            <div className="flex items-start justify-between">
              <div className="flex items-center space-x-3">
                <div className="w-12 h-12 rounded-lg bg-muted flex items-center justify-center overflow-hidden">
                  {pendingFileType === 'image' ? (
                    <img src={pendingFilePreview} alt="Preview" className="w-full h-full object-cover" />
                  ) : pendingFileType === 'video' ? (
                    <Film className="w-6 h-6 text-foreground" />
                  ) : pendingFileType === 'audio' ? (
                    <Music className="w-6 h-6 text-foreground" />
                  ) : (
                    <FileText className="w-6 h-6 text-foreground" />
                  )}
                </div>
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-medium truncate">{pendingFile.name}</p>
                  <p className="text-xs text-muted-foreground">
                    {(pendingFile.size / 1024 / 1024).toFixed(2)} MB
                  </p>
                </div>
              </div>
              <button
                onClick={cancelPendingFile}
                className="p-1 hover:bg-accent rounded-full transition-colors"
              >
                <X className="w-5 h-5 text-muted-foreground" />
              </button>
            </div>

            {pendingFileType !== 'audio' && (
              <div className="space-y-2">
                <label className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">
                  Legenda (opcional)
                </label>
                <textarea
                  value={pendingFileCaption}
                  onChange={(e) => setPendingFileCaption(e.target.value)}
                  placeholder="Escreva uma legenda..."
                  className="w-full resize-none rounded-lg border border-input bg-background px-3 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-border transition-all"
                  rows={2}
                />
              </div>
            )}

            <div className="flex justify-end space-x-2">
              <button
                onClick={cancelPendingFile}
                className="px-4 py-2 text-sm font-medium border border-border rounded-lg hover:bg-accent transition-colors"
                disabled={sendingMedia}
              >
                Cancelar
              </button>
              <button
                onClick={async () => {
                  await handleSendMedia(pendingFile, pendingFileType, pendingFileCaption);
                  cancelPendingFile();
                }}
                disabled={sendingMedia}
                className="px-6 py-2 text-sm font-bold bg-foreground text-background rounded-lg hover:opacity-90 transition-all flex items-center space-x-2 shadow-md"
              >
                {sendingMedia ? (
                  <>
                    <div className="w-4 h-4 border-2 border-current border-t-transparent rounded-full animate-spin" />
                    <span>Enviando...</span>
                  </>
                ) : (
                  <>
                    <Send className="w-4 h-4" />
                    <span>Enviar Arquivo</span>
                  </>
                )}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Input de mensagem */}
      <div className="border-t border-border p-4 bg-card overflow-visible">
        {/* Botão de templates quando janela fechada */}
        {!hideWaitingQueueContent && is24hWindowOpen === false && isWhatsAppChannel && (

          <div className="mb-3">
            <button
              onClick={openTemplatesModal}
              className="w-full flex items-center justify-center gap-2 px-4 py-2 bg-foreground text-background rounded-lg transition-all shadow-md hover:shadow-lg disabled:opacity-50 font-bold"
              title="Ver templates disponíveis"
            >
              <FileText className="w-5 h-5" />
              <span className="font-medium">Usar Template para Reabrir Conversa</span>
            </button>
          </div>
        )}

        <div className="flex items-center space-x-2 overflow-visible">
          {/* Upload de arquivo */}
          <input
            type="file"
            id="file-upload"
            className="hidden"
            onChange={handleFileUpload}
            accept="image/*,video/*,audio/*,.pdf,.doc,.docx"
          />
          <button
            onClick={() => document.getElementById('file-upload').click()}
            disabled={hideWaitingQueueContent || sendingMedia || (is24hWindowOpen === false && isWhatsAppChannel)}
            className="p-2 text-muted-foreground hover:text-primary hover:bg-accent rounded-lg transition-colors disabled:opacity-50"
            title={hideWaitingQueueContent ? 'Atribua a conversa para enviar arquivos' : (is24hWindowOpen === false && isWhatsAppChannel) ? "Janela de 24 horas fechada" : "Enviar arquivo"}
          >
            <Paperclip className="w-5 h-5" />
          </button>

          {/* Botão de Emojis (texto) */}
          <div className="relative overflow-visible" ref={emojiPickerRef}>
            <button
              onClick={() => {
                setShowEmojiPicker(!showEmojiPicker);
                setShowEmojiGallery(false);
              }}
              disabled={hideWaitingQueueContent || (is24hWindowOpen === false && isWhatsAppChannel)}

              className={`p-2 rounded-lg transition-colors disabled:opacity-50 ${showEmojiPicker ? 'text-primary bg-accent' : 'text-muted-foreground hover:text-primary hover:bg-accent'}`}
              title={hideWaitingQueueContent ? 'Atribua a conversa para usar o chat' : 'Inserir emoji'}
            >
              <Smile className="w-5 h-5" />
            </button>

            {showEmojiPicker && (
              <div className="absolute bottom-full left-0 mb-2 w-80 max-w-[85vw] bg-card border border-border rounded-xl shadow-2xl z-[120] overflow-hidden animate-in fade-in slide-in-from-bottom-2">
                <div className="p-2 border-b border-border bg-accent/50 flex justify-between items-center">
                  <span className="text-xs font-bold text-muted-foreground uppercase tracking-wider">Emojis (texto)</span>
                  <button onClick={() => setShowEmojiPicker(false)} className="text-muted-foreground hover:text-foreground">
                    <X size={14} />
                  </button>
                </div>
                <div className="h-64 overflow-y-auto p-2 grid grid-cols-7 gap-2 custom-scrollbar">
                  {emojiList.map((emoji, index) => (
                    <button
                      key={index}
                      onClick={() => addEmoji(emoji)}
                      className="p-1.5 hover:bg-accent rounded-lg transition-colors flex items-center justify-center border border-transparent hover:border-border text-2xl"
                      title={`Inserir emoji ${emoji}`}
                    >
                      <span aria-hidden="true">{emoji}</span>
                    </button>
                  ))}
                </div>
              </div>
            )}
          </div>

          {/* Botão Galeria (envia emoji como imagem) */}
          <div className="relative overflow-visible" ref={emojiGalleryRef}>
            <button
              onClick={() => {
                setShowEmojiGallery(!showEmojiGallery);
                setShowEmojiPicker(false);
              }}
              disabled={hideWaitingQueueContent || sendingMedia || (is24hWindowOpen === false && isWhatsAppChannel)}
              className={`p-2 rounded-lg transition-colors disabled:opacity-50 ${showEmojiGallery ? 'text-primary bg-accent' : 'text-muted-foreground hover:text-primary hover:bg-accent'}`}
              title={hideWaitingQueueContent ? 'Atribua a conversa para usar o chat' : 'Galeria de emojis (imagem)'}
            >
              <Image className="w-5 h-5" />
            </button>

            {showEmojiGallery && (
              <div className="absolute bottom-full left-0 mb-2 w-80 max-w-[85vw] bg-card border border-border rounded-xl shadow-2xl z-[120] overflow-hidden animate-in fade-in slide-in-from-bottom-2">
                <div className="p-2 border-b border-border bg-accent/50 flex justify-between items-center">
                  <span className="text-xs font-bold text-muted-foreground uppercase tracking-wider">Galeria de Imagens</span>
                  <button onClick={() => setShowEmojiGallery(false)} className="text-muted-foreground hover:text-foreground">
                    <X size={14} />
                  </button>
                </div>
                <div className="h-72 overflow-y-auto p-2 custom-scrollbar">
                  {loadingGallery ? (
                    <div className="h-full flex items-center justify-center text-sm text-muted-foreground">
                      Carregando galeria...
                    </div>
                  ) : galleryItems.length === 0 ? (
                    <div className="h-full flex items-center justify-center text-sm text-muted-foreground text-center px-4">
                      Nenhuma imagem cadastrada na galeria.
                    </div>
                  ) : (
                    <div className="space-y-2">
                      {galleryItems.map((item) => (
                        <button
                          key={item.id}
                          onClick={() => handleSendGalleryImage(item)}
                          className="w-full p-2 rounded-lg border border-border/70 hover:bg-accent transition-colors flex items-center gap-2 text-left"
                          title={`Enviar ${item.nome || 'imagem'} ao cliente`}
                          disabled={sendingMedia}
                        >
                          <div className="w-12 h-12 rounded-md bg-muted/40 overflow-hidden flex-shrink-0 border border-border/70">
                            {item.image_url ? (
                              <img src={item.image_url} alt={item.nome || 'Imagem da galeria'} className="w-full h-full object-cover" />
                            ) : (
                              <div className="w-full h-full flex items-center justify-center text-xs text-muted-foreground">Sem img</div>
                            )}
                          </div>
                          <div className="min-w-0 flex-1">
                            <p className="gallery-item-name text-sm font-medium truncate">{item.nome || 'Imagem sem nome'}</p>
                          </div>
                        </button>
                      ))}
                    </div>
                  )}
                </div>
              </div>
            )}
          </div>

          {/* Input de texto */}
          <div className="flex-1 relative">
            {hideWaitingQueueContent ? (
              <div className="w-full rounded-lg border border-sky-500/40 bg-sky-950/40 px-3 py-2 text-sm text-sky-100">
                Atribua esta conversa a você para ver o histórico e enviar mensagens.
              </div>
            ) : is24hWindowOpen === false && isWhatsAppChannel ? (

              <div className="w-full rounded-lg border border-amber-300 dark:border-amber-700 bg-amber-50 dark:bg-amber-950 px-3 py-2 text-sm text-amber-700 dark:text-amber-300">
                ⚠️ Mais de 24 horas se passaram desde que o cliente respondeu pela última vez. Para enviar mensagens após este período, é necessário usar um modelo de mensagem (template). O cliente precisa entrar em contato primeiro para reabrir a janela de atendimento.
              </div>
            ) : (
              <div className="relative w-full">
                {showQuickReplies && filteredQuickReplies.length > 0 && (
                  <div className="absolute bottom-full left-0 mb-2 w-full max-w-md bg-card border border-border rounded-xl shadow-2xl overflow-hidden z-50 animate-in fade-in slide-in-from-bottom-2">
                    <div className="p-2 border-b border-border bg-accent/50">
                      <p className="text-xs font-bold text-muted-foreground uppercase tracking-widest flex items-center gap-1.5">
                        <Zap className="w-3 h-3" /> Respostas Rápidas
                      </p>
                    </div>
                    <div className="max-h-60 overflow-y-auto p-1">
                      {filteredQuickReplies.map((qr, idx) => (
                        <button
                          key={qr.id}
                          onClick={() => selectQuickReply(qr)}
                          className={`w-full text-left p-3 rounded-lg transition-colors flex items-start gap-3 ${idx === quickReplyIndex ? 'bg-accent text-accent-foreground' : 'hover:bg-accent text-foreground'}`}
                          onMouseEnter={() => setQuickReplyIndex(idx)}
                        >
                          <div className={`mt-0.5 flex items-center justify-center flex-shrink-0 ${idx === quickReplyIndex ? 'text-accent-foreground' : 'text-muted-foreground'}`}>
                            <Zap className="w-4 h-4" strokeWidth={2} />
                          </div>
                          <div className="flex-1 min-w-0">
                            <p className="text-sm font-bold truncate">{qr.titulo}</p>
                            <p className="text-xs opacity-70 line-clamp-1">{qr.conteudo}</p>
                          </div>
                        </button>
                      ))}
                    </div>
                  </div>
                )}

                <textarea
                  id="message-input"
                  value={message}
                  onChange={handleMessageChange}
                  onKeyPress={handleKeyPress}
                  placeholder="Digite sua mensagem..."
                  className="w-full resize-none rounded-lg border border-input bg-background px-3 py-2 pr-10 text-sm ring-offset-background placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50"
                  rows={1}
                  style={{
                    minHeight: '40px',
                    maxHeight: '120px',
                    height: 'auto',
                    color: '#ffffff',
                    caretColor: '#ffffff',
                    WebkitTextFillColor: '#ffffff'
                  }}
                  onInput={(e) => {
                    e.target.style.height = 'auto';
                    e.target.style.height = Math.min(e.target.scrollHeight, 120) + 'px';
                  }}
                />

                {message.trim().length > 2 && (
                  <button
                    onClick={handleCorrectText}
                    disabled={isCorrecting}
                    title="Corrigir texto com IA"
                    className="absolute right-2 bottom-2 text-muted-foreground hover:text-primary transition-colors p-1 rounded-md hover:bg-accent disabled:opacity-50"
                  >
                    {isCorrecting ? (
                      <div className="w-4 h-4 border-2 border-primary border-t-transparent rounded-full animate-spin" />
                    ) : (
                      <span className="text-lg leading-none" style={{ filter: 'grayscale(100%) brightness(1.2)' }}>✨</span>
                    )}
                  </button>
                )}
              </div>
            )}
          </div>

          {/* Botão de gravação/envio */}
          {hideWaitingQueueContent ? (
            <button
              disabled
              className="p-2 bg-accent text-accent-foreground rounded-lg transition-colors disabled:cursor-not-allowed disabled:opacity-50"
              title="Atribua a conversa para enviar mensagens"
            >
              <Send className="w-5 h-5" />
            </button>
          ) : is24hWindowOpen === false && isWhatsAppChannel ? (

            <button
              disabled
              className="p-2 bg-accent text-accent-foreground rounded-lg transition-colors disabled:cursor-not-allowed disabled:opacity-50"
              title="Janela de 24 horas fechada"
            >
              <Send className="w-5 h-5" />
            </button>
          ) : isRecording ? (
            <div className="flex items-center space-x-2">
              <div className="text-sm text-red-500 font-mono">
                {formatRecordingTime(recordingTime)}
              </div>
              <button
                onClick={cancelRecording}
                className="p-2 text-red-500 hover:bg-red-50 dark:hover:bg-red-950 rounded-lg transition-colors"
                title="Cancelar gravação"
              >
                <Square className="w-5 h-5" />
              </button>
              <button
                onClick={stopRecording}
                className="p-2 text-green-500 hover:bg-green-50 dark:hover:bg-green-950 rounded-lg transition-colors"
                title="Parar gravação"
              >
                <MicOff className="w-5 h-5" />
              </button>
            </div>
          ) : (
            <button
              onClick={message.trim() ? handleSendMessage : startRecording}
              disabled={hideWaitingQueueContent || sendingMedia}
              className="p-2 bg-primary text-primary-foreground hover:bg-primary/90 rounded-lg transition-colors disabled:opacity-50"
              title={hideWaitingQueueContent ? 'Atribua a conversa primeiro' : message.trim() ? "Enviar mensagem" : "Gravar áudio"}
            >
              {sendingMedia ? (
                <div className="w-5 h-5 border-2 border-current border-t-transparent rounded-full animate-spin" />
              ) : message.trim() ? (
                <Send className="w-5 h-5" />
              ) : (
                <Mic className="w-5 h-5" />
              )}
            </button>
          )}
        </div>
      </div>

      {/* Modal de transferência */}
      {showTransferDropdown && (
        <Dialog open={showTransferDropdown} onOpenChange={setShowTransferDropdown}>
          <DialogContent className="max-w-md">
            <DialogHeader>
              <DialogTitle>Transferir Atendimento</DialogTitle>
              <DialogDescription>
                Selecione um atendente para transferir esta conversa.
              </DialogDescription>
            </DialogHeader>
            <div className="space-y-2 max-h-60 overflow-y-auto">
              {agents.length === 0 ? (
                <p className="text-muted-foreground text-center py-4">
                  Nenhum atendente disponível
                </p>
              ) : (
                agents.map((agent) => (
                  <button
                    key={agent.id}
                    onClick={() => handleTransferToAgent(agent.id)}
                    className="w-full text-left p-3 hover:bg-accent rounded-lg transition-colors flex items-center justify-between"
                  >
                    <div className="flex items-center space-x-3">
                      <div className="relative">
                        <div className="w-8 h-8 rounded-full bg-gradient-to-br from-blue-500 to-purple-600 flex items-center justify-center text-white font-medium text-sm">
                          {(agent.first_name || agent.username || 'U').charAt(0).toUpperCase()}
                        </div>
                        <div className={`absolute -bottom-1 -right-1 w-3 h-3 rounded-full border-2 border-background ${agentsStatus[agent.id] ? 'bg-green-500' : 'bg-gray-400'
                          }`} />
                      </div>
                      <div>
                        <div className="font-medium">
                          {agent.first_name || agent.username}
                        </div>
                        <div className="text-xs text-muted-foreground">
                          {agentsStatus[agent.id] ? 'Online' : 'Offline'}
                        </div>
                      </div>
                    </div>
                  </button>
                ))
              )}
            </div>
          </DialogContent>
        </Dialog>
      )}

      {/* Modal de imagem */}
      {showImageModal && selectedImage && (
        <Dialog open={showImageModal} onOpenChange={setShowImageModal}>
          <DialogContent className="max-w-4xl max-h-[90vh]">
            <div className="flex items-center justify-center">
              <img
                src={selectedImage}
                alt="Imagem ampliada"
                className="max-w-full max-h-[80vh] object-contain"
              />
            </div>
          </DialogContent>
        </Dialog>
      )}

      {/* Modal de Seleção de Reações */}
      {showReactionPicker && selectedMessageForReaction && selectedMessageForReaction.id && (
        <Dialog open={showReactionPicker} onOpenChange={setShowReactionPicker}>
          <DialogContent className="sm:max-w-md">
            <DialogHeader>
              <DialogTitle>Escolha uma reação</DialogTitle>
              <DialogDescription className="sr-only">
                Selecione um emoji para reagir à mensagem selecionada.
              </DialogDescription>
            </DialogHeader>
            <div className="flex flex-col space-y-4">
              <div>
                <p className="text-sm text-muted-foreground">
                  {selectedMessageForReaction && (
                    <>
                      Reaja à mensagem: "{(() => {
                        const msg = selectedMessageForReaction;
                        if (msg.content) {
                          return msg.content.slice(0, 50);
                        }
                        if (msg.file_name) {
                          return `Arquivo: ${msg.file_name}`;
                        }
                        if (msg.message_type === 'image') return '[Imagem]';
                        if (msg.message_type === 'video') return '[Vídeo]';
                        if (msg.message_type === 'audio' || msg.message_type === 'ptt') return '[Áudio]';
                        if (msg.message_type === 'document') return '[Documento]';
                        return '[Mídia]';
                      })()}..."
                    </>
                  )}
                </p>
              </div>

              {/* Grid de emojis */}
              <div className="grid grid-cols-6 gap-2">
                {['👍', '👎', '❤️', '😂', '😮', '😢', '😡', '🤩', '🔥', '👏', '💯', '🎉', '😘', '🥰', '😍', '🤗', '🙌', '✨'].map((emoji) => (
                  <button
                    key={emoji}
                    onClick={() => {
                      if (selectedMessageForReaction && selectedMessageForReaction.id) {
                        sendReaction(selectedMessageForReaction.id, emoji);
                      }
                    }}
                    className="p-3 text-2xl hover:bg-accent rounded-lg transition-colors flex items-center justify-center"
                    title={`Reagir com ${emoji}`}
                  >
                    {emoji}
                  </button>
                ))}
              </div>

              {/* Botão para remover reação */}
              {selectedMessageForReaction && selectedMessageForReaction.additional_attributes?.reaction && (
                <div className="border-t pt-4">
                  <button
                    onClick={() => {
                      if (selectedMessageForReaction && selectedMessageForReaction.id) {
                        sendReaction(selectedMessageForReaction.id, '');
                      }
                    }}
                    className="w-full p-2 text-red-600 hover:bg-red-50 rounded-lg transition-colors"
                  >
                    Remover reação
                  </button>
                </div>
              )}

              {/* Botões de ação */}
              <div className="flex justify-end space-x-2 pt-4 border-t">
                <button
                  onClick={() => setShowReactionPicker(false)}
                   className="px-4 py-2 text-sm border border-border rounded-lg hover:bg-accent transition-colors"
                >
                  Cancelar
                </button>
              </div>
            </div>
          </DialogContent>
        </Dialog>
      )}

      {/* Modal de Templates */}
      {showTemplatesModal && (
        <Dialog open={showTemplatesModal} onOpenChange={setShowTemplatesModal}>
          <DialogContent className="max-w-2xl max-h-[80vh]">
            <DialogHeader>
              <DialogTitle className="flex items-center gap-2">
                <FileText className="w-5 h-5" />
                Templates Disponíveis
              </DialogTitle>
            </DialogHeader>
            <div className="mt-4">
              {loadingTemplates ? (
                <div className="flex items-center justify-center py-8">
                  <div className="w-8 h-8 border-4 border-primary border-t-transparent rounded-full animate-spin" />
                  <span className="ml-3 text-muted-foreground">Carregando templates...</span>
                </div>
              ) : templates.length === 0 ? (
                <div className="text-center py-8">
                  <p className="text-muted-foreground">Nenhum template encontrado</p>
                  <p className="text-sm text-muted-foreground mt-2">
                    Configure templates no WhatsApp Business Manager para usar esta funcionalidade.
                  </p>
                </div>
              ) : (
                <div className="space-y-2 max-h-[60vh] overflow-y-auto">
                  {templates.map((template, index) => (
                    <div
                      key={index}
                      className="border border-border rounded-lg p-4 hover:bg-accent/50 transition-colors"
                    >
                      <div className="flex items-start justify-between">
                        <div className="flex-1">
                          <div className="flex items-center gap-2 mb-2">
                            <h3 className="font-semibold text-primary">{template.name}</h3>
                            {template.status && (
                              <span className={`text-xs px-2 py-1 rounded ${template.status === 'APPROVED'
                                ? 'bg-green-100 text-green-700 dark:bg-green-900 dark:text-green-300'
                                : template.status === 'PENDING'
                                  ? 'bg-yellow-100 text-yellow-700 dark:bg-yellow-900 dark:text-yellow-300'
                                  : 'bg-red-100 text-red-700 dark:bg-red-900 dark:text-red-300'
                                }`}>
                                {template.status === 'APPROVED' ? 'Aprovado' :
                                  template.status === 'PENDING' ? 'Pendente' : 'Rejeitado'}
                              </span>
                            )}
                          </div>
                          {template.language && (
                            <p className="text-xs text-muted-foreground mb-2">
                              Idioma: {template.language}
                            </p>
                          )}
                          {template.category && (
                            <p className="text-xs text-muted-foreground mb-2">
                              Categoria: {template.category}
                            </p>
                          )}
                          {template.components && template.components.length > 0 && (
                            <div className="mt-2 space-y-1">
                              {template.components.map((comp, compIndex) => {
                                if (comp.type === 'HEADER' && comp.format === 'TEXT') {
                                  return (
                                    <div key={compIndex} className="text-sm">
                                      <span className="font-medium text-muted-foreground">Cabeçalho:</span>{' '}
                                      <span className="text-primary">{comp.text || comp.example?.header_text?.[0]?.[0] || 'N/A'}</span>
                                    </div>
                                  );
                                }
                                if (comp.type === 'BODY') {
                                  return (
                                    <div key={compIndex} className="text-sm">
                                      <span className="font-medium text-muted-foreground">Corpo:</span>{' '}
                                      <span className="text-primary">{comp.text || 'N/A'}</span>
                                    </div>
                                  );
                                }
                                if (comp.type === 'FOOTER') {
                                  return (
                                    <div key={compIndex} className="text-sm">
                                      <span className="font-medium text-muted-foreground">Rodapé:</span>{' '}
                                      <span className="text-primary">{comp.text || 'N/A'}</span>
                                    </div>
                                  );
                                }
                                return null;
                              })}
                            </div>
                          )}
                        </div>
                        <button
                          onClick={() => sendTemplate(template)}
                          disabled={sendingTemplate || template.status !== 'APPROVED'}
                          className="ml-4 px-4 py-2 bg-primary text-primary-foreground rounded-lg hover:bg-primary/90 transition-colors disabled:opacity-50 disabled:cursor-not-allowed text-sm font-medium"
                          title={template.status !== 'APPROVED' ? 'Template não aprovado' : 'Enviar template'}
                        >
                          {sendingTemplate ? (
                            <div className="flex items-center gap-2">
                              <div className="w-4 h-4 border-2 border-current border-t-transparent rounded-full animate-spin" />
                              <span>Enviando...</span>
                            </div>
                          ) : (
                            'Enviar'
                          )}
                        </button>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
            {error && (
                <div className="p-3 bg-red-50 dark:bg-red-950 border border-red-200 dark:border-red-800 rounded-lg">
                <p className="text-sm text-red-700 dark:text-red-300">{error}</p>
              </div>
            )}
            <div className="flex justify-end mt-6 pt-4 border-t">
              <button
                onClick={() => {
                  setShowTemplatesModal(false);
                  setError('');
                }}
                className="px-4 py-2 text-sm border border-border rounded-lg hover:bg-accent transition-colors"
              >
                Fechar
              </button>
            </div>
          </DialogContent>
        </Dialog>
      )}
      </div>

      {/* Sidebar SGP (Lado Direito) - Render Condicional */}
      {showSgpSidebar && (
        <div className="animate-in slide-in-from-right duration-300">
          <SgpSidebar 
            conversation={conversation} 
            user={user} 
            messages={filteredMessages} 
            onClose={() => setShowSgpSidebar(false)}
          />
        </div>
      )}
    </div>
  );
};

export default ChatArea;
