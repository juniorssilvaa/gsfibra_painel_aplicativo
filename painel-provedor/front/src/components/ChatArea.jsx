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
  Film,
  Zap,
  X,
  Image,
  Music,
  Wallet,
  CreditCard,
  Calendar,
  Copy,
  Database,
  Smartphone,
  Edit2,
  Check,
  Phone,
} from 'lucide-react';
import SgpSidebar from './SgpSidebar';
import IncomingCallPopup from './IncomingCallPopup';
import LocationMessageCard, { getMessageLocation } from './LocationMessageCard';
import { useNioHubVoiceCall } from '../hooks/useNioHubVoiceCall';
import axios from 'axios';
import { toast } from '../lib/notify';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogPortal, DialogOverlay } from './ui/dialog';
import * as DialogPrimitive from '@radix-ui/react-dialog';
import whatsappIcon from '../assets/whatsapp.png';
import telegramIcon from '../assets/telegram.png';
import gmailIcon from '../assets/gmail.png';
import instagramIcon from '../assets/instagram.png';
import logoImage from '../assets/logo.png';
import chatBgPattern from '../assets/modo_dark.png';
import chatBgPatternLight from '../assets/modo_claro.png';
import CustomAudioPlayer from './ui/CustomAudioPlayer';
import FilePreview from './FilePreview';
import { formatWhatsAppPreviewHtml } from './InvoiceCardMessagePreview';
import { buildMediaUrl } from '../config/environment';
import { buildAuthenticatedWebSocketUrl } from '../utils/websocketUrl';
import { useTheme } from '../hooks/useTheme';
import {
  CHAT_ORANGE_SEND_BTN,
  CONVERSATION_ACTION_BTN_BASE,
  chatOrangeSendStyle,
  chatSaveStyle,
  conversationActionStyle,
} from '../constants/conversationActionButtons';
import { isReplyBlockedUntilAssignment } from '../utils/conversationAssignment';
import '../styles/wa-template-preview.css';

const INVOICE_PIX_ICON = 'https://logospng.org/download/pix/logo-pix-icone-1024.png';
const INVOICE_COPY_ICON = 'https://img.icons8.com/ios/50/11a24d/copy--v1.png';

function formatInvoiceCardAmount(amount, content = '') {
  if (amount != null && amount !== '') {
    if (typeof amount === 'string' && /R\$\s*/i.test(amount)) return amount.trim();
    const raw = String(amount).trim();
    const normalized = raw.includes(',') && !raw.includes('.')
      ? raw.replace(/\./g, '').replace(',', '.')
      : raw.replace(/[^\d.-]/g, '');
    const n = Number(normalized);
    if (!Number.isNaN(n)) {
      return n.toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' });
    }
  }
  const fromContent =
    content.match(/VALOR:\s*R\$\s*([\d.,]+)/i)?.[1] ||
    content.match(/R\$\s*([\d.,]+)/)?.[1];
  if (fromContent) {
    const n = Number(String(fromContent).replace(/\./g, '').replace(',', '.'));
    if (!Number.isNaN(n)) {
      return n.toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' });
    }
    return `R$ ${fromContent}`;
  }
  return 'R$ 0,00';
}

function formatInvoiceCardDueDate(vencimento, content = '') {
  const d = vencimento || content.match(/Vence(?:mento)?(?:\s*em)?:\s*([^\n*]+)/i)?.[1]?.trim();
  if (!d) return '';
  if (d.includes('/') || d.includes('.')) return d;
  const parts = String(d).split('-');
  if (parts.length === 3) return `${parts[2]}.${parts[1]}.${parts[0]}`;
  return d;
}

function resolveInvoicePaymentFlags(attrs = {}) {
  const type = String(attrs.payment_type || '').toLowerCase();
  const hasPixCode = Boolean(attrs.pix_code && String(attrs.pix_code).trim());
  const hasLineCode = Boolean(
    (attrs.line_code && String(attrs.line_code).trim()) ||
    (attrs.boleto_code && String(attrs.boleto_code).trim())
  );

  // Fonte da verdade: o que o backend marcou como enviado / códigos persistidos.
  // Não inferir pelo texto do body (pode citar "boleto" sem ter sido enviado).
  let hasPix = hasPixCode || attrs.has_pix === true || type === 'pix';
  let hasBoleto = hasLineCode || attrs.has_boleto === true || type === 'boleto';

  // WhatsApp Oficial: boleto só aparece se a linha digitável foi gravada (incluída no card Meta).
  if (type === 'whatsapp_oficial') {
    hasPix = hasPixCode || attrs.has_pix === true;
    hasBoleto = hasLineCode;
  }

  if (!hasPix && !hasBoleto && attrs.is_invoice) {
    hasPix = true;
  }
  return { hasPix, hasBoleto };
}

/** Nome só emoji ou igual ao telefone — sugerir edição manual. */
function contactNameLooksLikePlaceholder(name, phone) {
  const n = (name || '').trim();
  if (!n) return true;
  const phoneDigits = String(phone || '').replace(/\D/g, '');
  if (phoneDigits && n.replace(/\D/g, '') === phoneDigits) return true;
  try {
    const withoutEmoji = n.replace(/[\p{Emoji}\p{Emoji_Presentation}\p{Extended_Pictographic}]/gu, '').trim();
    if (withoutEmoji.length === 0) return true;
  } catch {
    /* regex Unicode indisponível */
  }
  return false;
}

function getMessageTranscription(msg) {
  const attrs = msg?.additional_attributes || {};
  const fromAttrs = String(attrs.transcription || attrs.transcription1 || '').trim();
  if (fromAttrs) return fromAttrs;

  const raw = String(msg?.content || '').trim();
  if (!raw) return null;

  const prefixed = raw.match(/^Transcrição do (?:áudio|vídeo) enviado pelo cliente:\s*([\s\S]+)$/i);
  if (prefixed) return prefixed[1].trim();

  const inline = raw.match(/Transcrição do (?:áudio|vídeo) enviado pelo cliente:\s*([\s\S]+)/i);
  if (inline) return inline[1].trim();

  return null;
}

function getContentWithoutTranscription(content, transcription) {
  if (!transcription) return content || '';
  let display = String(content || '').trim();
  if (!display || display === transcription) return '';

  display = display.replace(/\n?Transcrição do (?:áudio|vídeo) enviado pelo cliente:\s*[\s\S]*/i, '').trim();
  return display === transcription ? '' : display;
}

function messageHasTranscription(msg) {
  const mt = String(msg?.message_type || '').toLowerCase();
  if (!['audio', 'ptt', 'video'].includes(mt)) return false;
  return Boolean(getMessageTranscription(msg));
}

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

const ChatArea = ({ conversation, onConversationClose, onConversationUpdate, user, supervisorMode = false }) => {
  const navigate = useNavigate();
  const isDarkTheme = useTheme();
  const authReady = !!user;

  // HOOKS DEVEM VIR ANTES DE QUALQUER RETURN CONDICIONAL (Regra dos Hooks)
  const [message, setMessage] = useState('');
  const [messages, setMessages] = useState([]);
  const [loading, setLoading] = useState(false);
  const [loadingOlder, setLoadingOlder] = useState(false);
  const [hasOlderMessages, setHasOlderMessages] = useState(false);
  const messagesPageRef = useRef(1);
  const [error, setError] = useState('');
  const [assigningConversation, setAssigningConversation] = useState(false);
  const voiceCall = useNioHubVoiceCall(conversation?.id);
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
  const [isEditingContactName, setIsEditingContactName] = useState(false);
  const [editingContactName, setEditingContactName] = useState('');
  const [savingContactName, setSavingContactName] = useState(false);
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

  const replyBlockedUntilAssignment = useMemo(
    () => isReplyBlockedUntilAssignment(conversation, user),
    [conversation, user]
  );

  const cannotReply = hideWaitingQueueContent || replyBlockedUntilAssignment || supervisorMode;

  const [loadingProfilePic, setLoadingProfilePic] = useState(false);
  const [showTransferDropdown, setShowTransferDropdown] = useState(false);
  const [agents, setAgents] = useState([]);
  const [agentsStatus, setAgentsStatus] = useState({});
  const [profilePicture, setProfilePicture] = useState(null);
  const [loadingAgents, setLoadingAgents] = useState(false);
  const [sendingMedia, setSendingMedia] = useState(false);

  // Estados para visualização de mídia

  // Estados para reações e exclusão
  const [showReactionPicker, setShowReactionPicker] = useState(false);
  const [selectedMessageForReaction, setSelectedMessageForReaction] = useState(null);
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);
  const [messageToDelete, setMessageToDelete] = useState(null);
  const [replyingToMessage, setReplyingToMessage] = useState(null);
  const [expandedTranscriptions, setExpandedTranscriptions] = useState(() => new Set());
  const [showCloseCSATModal, setShowCloseCSATModal] = useState(false);
  const [isClosingConversation, setIsClosingConversation] = useState(false);
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

  // Throttle do indicador de digitação do WhatsApp (Meta remove após ~25s ou ao enviar)
  const typingIndicatorLastSentRef = useRef(0);
  useEffect(() => {
    typingIndicatorLastSentRef.current = 0;
  }, [conversation?.id]);

  const maybeSendTypingIndicator = () => {
    if (!conversation?.id) return;
    const channelType = conversation.inbox?.channel_type;
    if (channelType !== 'whatsapp' && channelType !== 'whatsapp_oficial') return;

    const now = Date.now();
    // Reenviar a cada ~20s enquanto o atendente continuar digitando
    if (now - typingIndicatorLastSentRef.current < 20000) return;
    typingIndicatorLastSentRef.current = now;

    const token = localStorage.getItem('auth_token') || localStorage.getItem('token');
    if (!token) return;

    axios.post('/api/messages/typing-indicator/', {
      conversation_id: conversation.id
    }, {
      headers: { Authorization: `Token ${token}` },
      // Evita que o interceptor global de erros mostre um toast: indicador de
      // digitação é best-effort e não deve interromper o atendente.
      skipErrorToast: true
    }).catch(() => {
      // Silenciar erros - indicador de digitação não é crítico
    });
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

    if (val.trim().length > 0) {
      maybeSendTypingIndicator();
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

  /** Extrai assinatura do atendente (*Nome disse:* / *Nome*) e devolve nome + corpo limpo. */
  const stripAgentSignature = (content) => {
    if (!content || typeof content !== 'string') {
      return { name: null, body: content };
    }
    let match = content.match(/^\s*\*([^*\n]+?)\s+disse:\*\s*\n+([\s\S]*)$/i);
    if (match) {
      return { name: match[1].trim(), body: match[2] };
    }
    match = content.match(/^\s*\*\*([^*\n]+)\*\*\s*\n+([\s\S]*)$/);
    if (match) {
      return { name: match[1].trim(), body: match[2] };
    }
    match = content.match(/^\s*\*([^*\n]+)\*\s*\n+([\s\S]*)$/);
    if (match && !/disse/i.test(match[1])) {
      return { name: match[1].trim(), body: match[2] };
    }
    return { name: null, body: content };
  };

  const resolveAgentDisplayName = (msg, contentForParse = msg?.content) => {
    const fromAttrs = (
      msg?.additional_attributes?.agent_name ||
      msg?.agent_display_name ||
      msg?.sender?.name ||
      ''
    ).trim();
    if (fromAttrs) return fromAttrs;
    if (msg?.is_from_customer) return '';
    const { name } = stripAgentSignature(contentForParse || '');
    return (name || '').trim();
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
    const playedAt = message.additional_attributes?.played_at;
    const readAt = message.additional_attributes?.read_at;
    const deliveredAt = message.additional_attributes?.delivered_at;
    const sentAt = message.additional_attributes?.sent_at;

    // Para áudio/mensagem de voz, "lida" (cliente abriu a conversa) NÃO significa que
    // o áudio foi reproduzido. A Meta só confirma isso via webhook "played" — então
    // até esse status chegar, tratamos "read" visualmente como "delivered" (cinza).
    const isVoiceMessage = message.message_type === 'audio' || message.message_type === 'ptt';

    // Determinar o status atual (prioridade: played > read > delivered > sent)
    let currentStatus = status;
    if (playedAt || status === 'played') {
      currentStatus = 'played';
    } else if (readAt || status === 'read') {
      currentStatus = isVoiceMessage ? 'delivered' : 'read';
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

    // 4️⃣ Mensagem de voz reproduzida pelo cliente - 2 tickets azuis bem fortes
    if (currentStatus === 'played') {
      return (
        <span className="inline-flex items-center ml-1 transition-all duration-300 ease-in-out" title="Áudio reproduzido pelo cliente">
          <svg
            width="16"
            height="12"
            viewBox="0 0 16 11"
            fill="none"
            xmlns="http://www.w3.org/2000/svg"
            className="transition-all duration-300 ease-in-out"
          >
            <path
              d="M0.5 5.5L3 8L7 4"
              stroke="#0066FF"
              strokeWidth="2.2"
              strokeLinecap="round"
              strokeLinejoin="round"
              fill="none"
            />
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
      case 'app_mobile':
        return <Smartphone className="w-3.5 h-3.5 text-orange-500" />;
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
      'whatsapp_oficial': 'WhatsApp Oficial',
      'app_mobile': 'App Mobile',
    };

    return channelTypes[inbox.channel_type] || inbox.channel_type || 'Canal';
  };

  // Função para buscar mensagens (últimas 150; histórico antigo sob demanda)
  const processRawMessages = (rawList) => {
    return (rawList || []).map(msg => {
      let processedContent = processMessageContent(msg.content, msg.is_from_customer);
      const agentDisplayName = resolveAgentDisplayName(msg, processedContent);

      if (processedContent && !msg.is_from_customer) {
        const stripped = stripAgentSignature(processedContent);
        if (stripped.name) {
          processedContent = stripped.body;
        }
      }

      const isFromAI = msg.from_ai === true ||
        msg.additional_attributes?.from_ai === true ||
        msg.sender?.sender_type === 'ai';

      return {
        ...msg,
        content: processedContent,
        agent_display_name: agentDisplayName || undefined,
        sender: msg.sender || (!msg.is_from_customer && isFromAI ? { sender_type: 'ai' } : { sender_type: 'agent' }),
        from_ai: isFromAI,
      };
    });
  };

  const fetchMessages = async () => {
    if (!conversation) return;
    const requestedConversationId = conversation.id;
    setMessages([]);
    setHasOlderMessages(false);
    messagesPageRef.current = 1;
    setLoading(true);
    setError('');
    const token = localStorage.getItem('auth_token') || localStorage.getItem('token');
    try {
      const auditQuery = supervisorMode ? '&for_audit=1' : '';
      const res = await axios.get(
        `/api/messages/?conversation=${requestedConversationId}&page_size=150&ordering=-created_at&page=1${auditQuery}`,
        { headers: { Authorization: `Token ${token}` } }
      );

      const pageMessages = res.data.results || (Array.isArray(res.data) ? res.data : []);
      const allMessages = [...pageMessages].reverse();
      const processedMessages = processRawMessages(allMessages);

      if (Number(activeConversationIdRef.current) !== Number(requestedConversationId)) {
        return;
      }
      setMessages(processedMessages);
      setHasOlderMessages(Boolean(res.data.next));
    } catch (err) {
      if (Number(activeConversationIdRef.current) === Number(requestedConversationId)) {
        setError('Erro ao carregar mensagens.');
      }
    } finally {
      if (Number(activeConversationIdRef.current) === Number(requestedConversationId)) {
        setLoading(false);
      }
    }
  };

  const loadOlderMessages = async () => {
    if (!conversation || loadingOlder || !hasOlderMessages) return;
    const requestedConversationId = conversation.id;
    const nextPage = messagesPageRef.current + 1;
    const token = localStorage.getItem('auth_token') || localStorage.getItem('token');
    if (!token) return;

    setLoadingOlder(true);
    try {
      const auditQuery = supervisorMode ? '&for_audit=1' : '';
      const res = await axios.get(
        `/api/messages/?conversation=${requestedConversationId}&page_size=150&ordering=-created_at&page=${nextPage}${auditQuery}`,
        { headers: { Authorization: `Token ${token}` } }
      );
      const pageMessages = res.data.results || [];
      if (Number(activeConversationIdRef.current) !== Number(requestedConversationId)) {
        return;
      }
      const olderMessages = processRawMessages([...pageMessages].reverse());
      setMessages((prev) => [...olderMessages, ...prev]);
      messagesPageRef.current = nextPage;
      setHasOlderMessages(Boolean(res.data.next));
    } catch (_) {
      /* mantém mensagens já carregadas */
    } finally {
      if (Number(activeConversationIdRef.current) === Number(requestedConversationId)) {
        setLoadingOlder(false);
      }
    }
  };

  // Atualizar estado local do nome do contato quando a conversa mudar
  useEffect(() => {
    setContactName(conversation.contact?.name);
    setIsEditingContactName(false);
    setEditingContactName((conversation.contact?.name || '').trim());

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

        // Em caso de erro, usar dados da conversa que já temos como último recurso
        // Mas sempre priorizar o valor calculado pelo backend
        if (conversation) {
          const currentIsWhatsApp = ['whatsapp', 'whatsapp_oficial', 'whatsapp_session'].includes(channelType);
          if (currentIsWhatsApp) {

            // Usar o valor do backend se disponível, senão assumir fechada
            if (conversation.is_24h_window_open !== undefined) {
              setIs24hWindowOpen(conversation.is_24h_window_open);
            } else {
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
    supervisorMode,
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

    let ws;
    let cancelled = false;

    (async () => {
      // Priorizar auth_token que é o padrão salvo no Login, mas aceitar token também para compatibilidade
      const token = localStorage.getItem('auth_token') || localStorage.getItem('token');
      if (!token) return;

      const wsUrl = await buildAuthenticatedWebSocketUrl('/ws/user_status/', { token });
      if (cancelled) return;
      ws = new WebSocket(wsUrl);

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
    })();

    return () => {
      cancelled = true;
      if (ws && ws.readyState === WebSocket.OPEN) {
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

      const wsUrl = await buildAuthenticatedWebSocketUrl(`/ws/conversations/${conversation.id}/`, { token });
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
                }
                  let processedContent = processMessageContent(data.message.content, data.message.is_from_customer);
                  const agentDisplayName = resolveAgentDisplayName(data.message, processedContent);

                  // Remover assinatura do texto do balão (nome vai no cabeçalho)
                  if (processedContent && !data.message.is_from_customer) {
                    const stripped = stripAgentSignature(processedContent);
                    if (stripped.name) {
                      processedContent = stripped.body;
                    }
                  }

                  // CORREÇÃO: Identificar mensagens da IA de forma mais robusta
                  const isFromAI = data.message.from_ai === true ||
                    data.message.additional_attributes?.from_ai === true ||
                    data.message.sender?.sender_type === 'ai' ||
                    data.sender === 'ai';

                  const processedMessage = {
                    ...data.message,
                    content: processedContent,
                    agent_display_name: agentDisplayName || undefined,
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
                  if (data.status === 'played') {
                    updatedAttrs.played_at = data.timestamp;
                    updatedAttrs.played_by = data.recipient_id;
                  } else if (data.status === 'read') {
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

            // Nome do contato atualizado (ex.: consulta SGP no chatbot)
            if (
              data.event_type === 'contact_updated' &&
              data.conversation_id === conversation.id
            ) {
              const newName =
                data.data?.contact_name ||
                data.conversation?.contact?.name;
              if (newName) {
                setContactName(newName);
                setEditingContactName(newName.trim());
              }
              if (onConversationUpdate) {
                if (data.conversation) {
                  onConversationUpdate(data.conversation);
                } else if (newName && conversation.contact) {
                  onConversationUpdate({
                    ...conversation,
                    contact: { ...conversation.contact, name: newName },
                  });
                }
              }
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

            if (data.event_type === 'protocol_updated' && data.conversation_id === conversation.id) {
              if (onConversationUpdate) {
                if (data.conversation) {
                  onConversationUpdate(data.conversation);
                } else {
                  onConversationUpdate({
                    ...conversation,
                    additional_attributes: {
                      ...(conversation.additional_attributes || {}),
                      protocolo: data.data?.protocolo,
                      protocol_source: data.data?.protocol_source,
                    },
                  });
                }
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
          if (process.env.NODE_ENV === 'development') {
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

  const scrollToBottom = (behavior = 'smooth') => {
    const el = scrollContainerRef.current;
    if (el) {
      if (behavior === 'auto') {
        el.scrollTop = el.scrollHeight;
      } else {
        el.scrollTo({ top: el.scrollHeight, behavior });
      }
      return;
    }
    messagesEndRef.current?.scrollIntoView({ behavior });
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
    } finally {
      setIsCorrecting(false);
    }
  };

  const handleSendMessage = async () => {
    if (!message.trim() || !conversation) return;

    // A Meta remove o indicador de digitação ao enviar; zera o throttle para a próxima digitação
    typingIndicatorLastSentRef.current = 0;

    if (isReplyBlockedUntilAssignment(conversation, user)) {
      toast.error('Clique em Atender para assumir o atendimento e enviar mensagens.');
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

      // Formatar mensagem com nome do usuário (WhatsApp etc.). App mobile não usa assinatura no texto.
      const channelType = conversation?.inbox?.channel_type;
      const formattedMessage =
        channelType === 'app_mobile' ? message : `*${userName} disse:*\n${message}`;

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

      const appendMessageFromApi = (data) => {
        if (!data?.id) return;
        const rawContent = processMessageContent(data.content, data.is_from_customer);
        const agentDisplayName = resolveAgentDisplayName(data, rawContent);
        let content = rawContent;
        if (!data.is_from_customer) {
          const stripped = stripAgentSignature(rawContent);
          if (stripped.name) content = stripped.body;
        }
        const processedMessage = {
          ...data,
          content,
          agent_display_name: agentDisplayName || undefined,
        };
        setMessages((currentMessages) => {
          if (currentMessages.some((m) => m.id === data.id)) return currentMessages;
          return [...currentMessages, processedMessage].sort(
            (a, b) => new Date(a.created_at) - new Date(b.created_at)
          );
        });
        setTimeout(() => scrollToBottom(), 50);
      };

      if (response.data?.sent_success === false) {
        const failMsg =
          response.data?.error_message ||
          response.data?.error ||
          'Não foi possível enviar a mensagem.';
        setError(failMsg);
        toast.error(failMsg);
        pendingMessagesRef.current.delete(messageKey);
        setPendingMessages((prev) => {
          const next = new Set(prev);
          next.delete(messageKey);
          return next;
        });
        return;
      }

      // Mostrar na hora (Redis/WebSocket pode estar indisponível)
      appendMessageFromApi(response.data);
      pendingMessagesRef.current.delete(messageKey);
      setPendingMessages((prev) => {
        const next = new Set(prev);
        next.delete(messageKey);
        return next;
      });

      setMessage('');
      setReplyingToMessage(null);

    } catch (e) {

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
      if (isReplyBlockedUntilAssignment(conversation, user)) {
        toast.error('Clique em Atender para assumir o atendimento e gravar áudio.');
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

      let mimeType = 'audio/webm;codecs=opus';
      if (typeof MediaRecorder !== 'undefined' && MediaRecorder.isTypeSupported) {
        if (!MediaRecorder.isTypeSupported(mimeType)) {
          if (MediaRecorder.isTypeSupported('audio/webm')) {
            mimeType = 'audio/webm';
          } else if (MediaRecorder.isTypeSupported('audio/ogg;codecs=opus')) {
            mimeType = 'audio/ogg;codecs=opus';
          } else if (MediaRecorder.isTypeSupported('audio/ogg')) {
            mimeType = 'audio/ogg';
          }
        }
      }

      const mediaRecorder = new MediaRecorder(
        stream,
        MediaRecorder.isTypeSupported?.(mimeType) ? { mimeType } : undefined
      );

      mediaRecorderRef.current = mediaRecorder;
      const chunks = [];

      mediaRecorder.ondataavailable = (event) => {
        if (event.data.size > 0) {
          chunks.push(event.data);
        }
      };

      mediaRecorder.onstop = () => {
        const containerType = mimeType.includes('ogg') ? 'audio/ogg' : 'audio/webm';
        const ext = mimeType.includes('ogg') ? 'ogg' : 'webm';
        const blob = new Blob(chunks, { type: containerType });
        setAudioBlob(blob);
        setAudioUrl(URL.createObjectURL(blob));
        mediaRecorderRef.current._recordedExt = ext;

        stream.getTracks().forEach(track => track.stop());
      };

      mediaRecorder.start();
      setIsRecording(true);
      setRecordingTime(0);

      recordingIntervalRef.current = setInterval(() => {
        setRecordingTime(prev => prev + 1);
      }, 1000);

    } catch (error) {

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

    if (isReplyBlockedUntilAssignment(conversation, user)) {
      toast.error('Clique em Atender para assumir o atendimento e enviar mensagens.');
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

      const recordedExt = mediaRecorderRef.current?._recordedExt || 'webm';
      const audioFile = new File([audioBlob], `audio_${Date.now()}.${recordedExt}`, {
        type: audioBlob.type || (recordedExt === 'ogg' ? 'audio/ogg' : 'audio/webm')
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
        setError('Erro interno: tipo de mídia inválido');
        return;
      }

      await handleSendMedia(audioFile, finalMediaType, null);

      // Log removido(' Áudio enviado com sucesso!');

      setAudioBlob(null);
      setAudioUrl(null);
      setRecordingTime(0);

    } catch (error) {
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
        setPlayingAudio(null);
      });
    }

    audio.play().then(() => {
      setPlayingAudio(messageId);
    }).catch(e => {
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

    if (isReplyBlockedUntilAssignment(conversation, user)) {
      toast.error('Clique em Atender para assumir o atendimento e enviar arquivos.');
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
    }

    try {
      //  NÃO adicionar mensagem de "enviando..." - deixar o WebSocket fazer isso

      // Buscar informações do usuário atual se houver caption (exceto para PTT)
      let formattedCaption = caption;
      if (caption && mediaType !== 'ptt') {
        const channelType = conversation?.inbox?.channel_type;
        if (channelType === 'app_mobile') {
          formattedCaption = caption;
        } else {
          const userResponse = await axios.get('/api/auth/me/', {
            headers: { Authorization: `Token ${token}` }
          });

          const currentUser = userResponse.data;
          const userName = currentUser.first_name || currentUser.username || 'Usuário';
          formattedCaption = `*${userName} disse:*\n${caption}`;
        }
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

  const startEditContactName = () => {
    const current = ((contactName || conversation.contact?.name || '') + '').trim();
    setEditingContactName(
      contactNameLooksLikePlaceholder(current, conversation.contact?.phone) ? '' : current
    );
    setIsEditingContactName(true);
  };

  const cancelEditContactName = () => {
    setIsEditingContactName(false);
    setEditingContactName((contactName || conversation.contact?.name || '').trim());
  };

  const saveContactName = async () => {
    const name = editingContactName.trim();
    if (!name) {
      toast.error('Informe um nome para o contato.');
      return;
    }
    if (!conversation?.contact?.id) {
      toast.error('Contato não encontrado.');
      return;
    }
    const token = localStorage.getItem('auth_token') || localStorage.getItem('token');
    if (!token) {
      toast.error('Sessão expirada. Faça login novamente.');
      return;
    }
    setSavingContactName(true);
    try {
      const response = await axios.patch(
        `/api/contacts/${conversation.contact.id}/`,
        { name },
        { headers: { Authorization: `Token ${token}` } }
      );
      const savedName = (response.data?.name || name).trim();
      setContactName(savedName);
      setIsEditingContactName(false);
      if (onConversationUpdate) {
        onConversationUpdate({
          ...conversation,
          contact: {
            ...conversation.contact,
            name: savedName,
          },
        });
      }
      toast.success('Nome do contato salvo.');
    } catch (err) {
      const msg =
        err.response?.data?.name?.[0] ||
        err.response?.data?.detail ||
        err.response?.data?.error ||
        'Não foi possível salvar o nome.';
      toast.error(typeof msg === 'string' ? msg : 'Não foi possível salvar o nome.');
    } finally {
      setSavingContactName(false);
    }
  };

  // Função para atribuir conversa para o usuário atual
  const handleAssignToMe = async () => {
    if (!conversation || assigningConversation) return;

    const token = localStorage.getItem('auth_token') || localStorage.getItem('token');
    setAssigningConversation(true);
    try {
      const response = await axios.post(`/api/conversations/${conversation.id}/assign/`, {}, {
        headers: { Authorization: `Token ${token}` },
      });

      if (onConversationUpdate && response.data.conversation) {
        onConversationUpdate(response.data.conversation);
      }
      fetchMessages();
      toast.success(response.data?.message || 'Atendimento atribuído com sucesso.');
    } catch {
      // Erro exibido pelo popup global (AuthContext + toast)
    } finally {
      setAssigningConversation(false);
    }
  };

  // Função para encerrar conversa
  const confirmCloseConversation = async (sendCSAT) => {
    if (!conversation) return;

    const token = localStorage.getItem('auth_token') || localStorage.getItem('token');
    try {
      setIsClosingConversation(true);
      const response = await axios.post(
        `/api/conversations/${conversation.id}/close_conversation_agent/`,
        { resolution_type: 'resolved', resolution_notes: '', send_csat: !!sendCSAT },
        { headers: { Authorization: `Token ${token}` } }
      );

      if (sendCSAT && response.data?.csat_sent === false) {
        toast.warning(
          response.data?.message ||
            'Conversa encerrada, mas a pesquisa não chegou ao cliente. Verifique o WhatsApp.'
        );
      }

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
      toast.error('Erro ao encerrar conversa. Tente novamente.');
    } finally {
      setIsClosingConversation(false);
      setShowCloseCSATModal(false);
    }
  };

  const handleCloseConversation = () => {
    if (!conversation) return;
    setShowCloseCSATModal(true);
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

      toast.error(errorMessage);
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

  const toggleMessageTranscription = (messageId) => {
    setExpandedTranscriptions((prev) => {
      const next = new Set(prev);
      if (next.has(messageId)) next.delete(messageId);
      else next.add(messageId);
      return next;
    });
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
        }
      }

      if (!channelId) {
        setError('Não foi possível identificar o canal do WhatsApp para carregar templates. Verifique as configurações de integração.');
        setLoadingTemplates(false);
        return;
      }


      const response = await axios.get(`/api/canais/${channelId}/message-templates/`, {
        headers: { Authorization: `Token ${token}` }
      });

      if (response.data && response.data.success) {
        setTemplates(response.data.templates || []);
      } else {
        setError(response.data?.error || 'Erro ao buscar templates');
      }
    } catch (error) {
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

    if (isReplyBlockedUntilAssignment(conversation, user)) {
      toast.error('Clique em Atender para assumir o atendimento antes de enviar templates.');
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

    if (isReplyBlockedUntilAssignment(conversation, user)) {
      toast.error('Clique em Atender para assumir o atendimento e enviar arquivos.');
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

  // Permitir colar (Ctrl+V) imagens no chat, como no WhatsApp Web
  const handlePasteIntoChat = (e) => {
    try {
      if (isReplyBlockedUntilAssignment(conversation, user)) {
        return;
      }
      if (is24hWindowOpen === false && isWhatsAppChannel) {
        return;
      }
      if (pendingFile || sendingMedia) {
        return;
      }

      const items = e.clipboardData?.items ? Array.from(e.clipboardData.items) : [];
      const imageItem = items.find((it) => it.kind === 'file' && (it.type || '').startsWith('image/'));
      if (!imageItem) return;

      const blob = imageItem.getAsFile?.();
      if (!blob) return;

      // Criar um File com nome previsível para manter UX consistente
      const ext = (blob.type || 'image/png').split('/')[1] || 'png';
      const filename = `print_${new Date().toISOString().replace(/[:.]/g, '-')}.${ext}`;
      const file = new File([blob], filename, { type: blob.type || 'image/png' });

      setPendingFilePreview(URL.createObjectURL(file));
      setPendingFile(file);
      setPendingFileType('image');
      setPendingFileCaption('');

      // Não colar texto/bytes no textarea quando for imagem
      e.preventDefault();
    } catch (_) {
      // Silenciar — colar texto normal continua funcionando
    }
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

  const openImageInNewTab = (imageUrl) => {
    if (!imageUrl) return;
    window.open(imageUrl, '_blank', 'noopener,noreferrer');
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
    <div className="flex min-h-0 flex-1 flex-row overflow-hidden bg-background">
      {/* Área Principal do Chat (Lado Esquerdo) */}
      <div className="flex min-h-0 flex-1 flex-col relative overflow-hidden bg-background border-r">
        {/* Header da conversa */}
        <div className="border-b border-border px-3 py-2 bg-card shrink-0">
          <div className="flex items-center justify-between gap-2">
          <div className="flex items-center space-x-2 min-w-0">
            <div className="flex-shrink-0">
              <div className="w-8 h-8 rounded-full flex items-center justify-center overflow-hidden bg-primary/10">
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
                  size={16} 
                  className={`text-primary ${conversation.contact?.avatar ? 'hidden' : 'block'}`} 
                />
              </div>
            </div>

            <div className="flex-1 min-w-0">
              <div className="flex flex-wrap items-center gap-x-2 gap-y-0">
                {isEditingContactName ? (
                  <div className="flex flex-wrap items-center gap-1.5 min-w-0 flex-1">
                    <input
                      type="text"
                      value={editingContactName}
                      onChange={(e) => setEditingContactName(e.target.value)}
                      onKeyDown={(e) => {
                        if (e.key === 'Enter') saveContactName();
                        if (e.key === 'Escape') cancelEditContactName();
                      }}
                      maxLength={255}
                      autoFocus
                      disabled={savingContactName}
                      placeholder="Nome do cliente"
                      className="h-7 min-w-[140px] max-w-[280px] flex-1 rounded-md border border-border bg-background px-2 text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-primary/40"
                    />
                    <button
                      type="button"
                      onClick={saveContactName}
                      disabled={savingContactName}
                      className="p-1 rounded-md text-white hover:opacity-90 disabled:opacity-50"
                      style={chatSaveStyle()}
                      title="Salvar nome"
                    >
                      <Check className="w-3.5 h-3.5" />
                    </button>
                    <button
                      type="button"
                      onClick={cancelEditContactName}
                      disabled={savingContactName}
                      className="p-1 rounded-md text-muted-foreground hover:bg-muted hover:text-foreground disabled:opacity-50"
                      title="Cancelar"
                    >
                      <X className="w-3.5 h-3.5" />
                    </button>
                  </div>
                ) : (
                  <>
                    <h3 className="text-sm font-medium text-foreground truncate max-w-[240px] sm:max-w-[320px]">
                      {(() => {
                        const displayName =
                          (contactName && contactName.trim()) ||
                          conversation.contact?.name?.trim();
                        const contactPhone = conversation.contact?.phone;
                        if (displayName && displayName.length > 0) {
                          return displayName;
                        }
                        return contactPhone || 'Contato sem nome';
                      })()}
                    </h3>
                    <button
                      type="button"
                      onClick={startEditContactName}
                      disabled={supervisorMode}
                      className="p-0.5 rounded-md text-muted-foreground hover:text-foreground hover:bg-muted transition-colors shrink-0 disabled:opacity-40 disabled:pointer-events-none"
                      title={supervisorMode ? 'Edição indisponível em modo supervisão' : 'Editar nome do contato'}
                    >
                      <Edit2 className="w-3 h-3" />
                    </button>
                  </>
                )}
                <div className="flex items-center space-x-1 text-[11px] text-muted-foreground shrink-0">
                  {getChannelIcon(conversation.inbox?.channel_type)}
                  <span className="font-medium">
                    Canal: {getChannelDisplayName(conversation.inbox)}
                  </span>
                </div>
              </div>
              {conversation.contact?.phone && (
                <p className="text-[11px] leading-tight text-muted-foreground mt-0.5 truncate">
                  {conversation.contact.phone}
                  {(conversation.additional_attributes?.protocolo ||
                    conversation.protocolo) && (
                    <span className="ml-2 text-[11px] font-medium text-foreground/80">
                      · Protocolo:{' '}
                      <span className="font-semibold tracking-wide">
                        {conversation.additional_attributes?.protocolo ||
                          conversation.protocolo}
                      </span>
                      {conversation.additional_attributes?.protocol_source === 'sgp' && (
                        <span className="ml-1 text-[10px] font-normal text-emerald-600 dark:text-emerald-400">
                          (SGP)
                        </span>
                      )}
                    </span>
                  )}
                  {!isEditingContactName &&
                    contactNameLooksLikePlaceholder(
                      contactName || conversation.contact?.name,
                      conversation.contact?.phone
                    ) && (
                      <span className="ml-1.5 text-[10px] text-amber-600 dark:text-amber-400">
                        · Defina um nome com o lápis
                      </span>
                    )}
                </p>
              )}
              {!conversation.contact?.phone &&
                (conversation.additional_attributes?.protocolo || conversation.protocolo) && (
                <p className="text-[11px] leading-tight text-muted-foreground mt-0.5 truncate">
                  Protocolo:{' '}
                  <span className="font-semibold text-foreground/80 tracking-wide">
                    {conversation.additional_attributes?.protocolo || conversation.protocolo}
                  </span>
                  {conversation.additional_attributes?.protocol_source === 'sgp' && (
                    <span className="ml-1 text-[10px] font-normal text-emerald-600 dark:text-emerald-400">
                      (SGP)
                    </span>
                  )}
                </p>
              )}
            </div>
          </div>

          <div className="flex items-center space-x-1.5 shrink-0">

            {/* Toggle SGP Sidebar */}
            <button
              type="button"
              onClick={() => setShowSgpSidebar(!showSgpSidebar)}
              className={`${CONVERSATION_ACTION_BTN_BASE} h-7 px-2`}
              style={conversationActionStyle(showSgpSidebar ? 'sgpAtivo' : 'sgp')}
              title={showSgpSidebar ? 'Fechar painel SGP' : 'Abrir painel SGP'}
            >
              <Database className="h-3.5 w-3.5 shrink-0" />
            </button>

            {!supervisorMode && isWhatsAppChannel && voiceCall.capability?.configured !== false && (
              <button
                type="button"
                onClick={() => {
                  if (voiceCall.inCall) return;
                  if (voiceCall.capability?.available) {
                    voiceCall.startOutboundCall();
                  } else {
                    voiceCall.setPanelOpen(true);
                  }
                }}
                disabled={!voiceCall.capability?.available && !voiceCall.inCall && !voiceCall.incoming}
                className={`${CONVERSATION_ACTION_BTN_BASE} h-7 px-2 disabled:opacity-40`}
                style={conversationActionStyle(
                  voiceCall.inCall || voiceCall.incoming ? 'atender' : 'sgp'
                )}
                title={
                  voiceCall.capability?.available
                    ? 'Ligar'
                    : voiceCall.capability?.reason || 'Ligações indisponíveis'
                }
              >
                <Phone className="h-3.5 w-3.5 shrink-0" />
              </button>
            )}

            <div className="flex items-center gap-1.5 border-l border-white/10 pl-1.5 ml-1">
              {!supervisorMode && (
                <button
                  type="button"
                  onClick={handleAssignToMe}
                  disabled={assigningConversation}
                  className={`${CONVERSATION_ACTION_BTN_BASE} h-7 px-2 disabled:opacity-60`}
                  style={conversationActionStyle('atender')}
                  title="Atender conversa"
                >
                  <UserCheck className="w-3.5 h-3.5 shrink-0" />
                  <span className="text-nowrap">{assigningConversation ? 'Atribuindo...' : 'Atender'}</span>
                </button>
              )}

              <button
                type="button"
                onClick={handleTransferConversation}
                disabled={loadingAgents}
                className={`${CONVERSATION_ACTION_BTN_BASE} h-7 px-2`}
                style={conversationActionStyle('transferir')}
                title={supervisorMode ? 'Transferir atendimento para outro agente' : 'Transferir conversa'}
              >
                <ArrowRightLeft className="w-3.5 h-3.5 shrink-0" />
                <span className="text-nowrap">Transferir</span>
              </button>

              {!supervisorMode && (
                <button
                  type="button"
                  onClick={handleCloseConversation}
                  className={`${CONVERSATION_ACTION_BTN_BASE} h-7 px-2`}
                  style={conversationActionStyle('encerrar')}
                  title="Encerrar conversa"
                >
                  <CheckCircle2 className="w-3.5 h-3.5 shrink-0" />
                  <span className="text-nowrap">Encerrar</span>
                </button>
              )}
            </div>
          </div>
        </div>
      </div>

      {/* Lista de mensagens */}
      <div
        ref={scrollContainerRef}
        onScroll={handleScrollContainer}
        className="relative z-0 min-h-0 flex-1 overflow-y-auto overflow-x-hidden px-4 pt-4"
        style={{
          // Fundo do chat (modo escuro / modo claro)
          backgroundColor: isDarkTheme ? '#0b141a' : '#efeae2',
          backgroundImage: `url(${isDarkTheme ? chatBgPattern : chatBgPatternLight})`,
          backgroundRepeat: 'no-repeat',
          backgroundSize: 'cover',
          backgroundPosition: 'center center',
          opacity: 1
        }}
      >
        {/* min-h-full + justify-end: poucas mensagens no rodapé; histórico longo permite scroll para cima */}
        <div className="relative flex min-h-full w-full flex-col justify-end space-y-4 pb-[3.75rem]">
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
                Use <span className="font-medium text-amber-50">Atender</span> para assumir o atendimento e visualizar o histórico.
              </p>
            </div>
          ) : filteredMessages.length === 0 ? (
            <div className="text-center text-muted-foreground py-8">
              <p>Nenhuma mensagem encontrada</p>
            </div>
          ) : (
            <>
              {hasOlderMessages && !hideWaitingQueueContent && (
                <div className="flex justify-center pb-2">
                  <button
                    type="button"
                    onClick={loadOlderMessages}
                    disabled={loadingOlder}
                    className="rounded-full border border-border bg-card/90 px-4 py-1.5 text-xs text-muted-foreground hover:bg-accent hover:text-foreground disabled:opacity-50"
                  >
                    {loadingOlder ? 'Carregando...' : 'Carregar mensagens anteriores'}
                  </button>
                </div>
              )}
              {filteredMessages.map((msg) => {
              const attachmentList = Array.isArray(msg.attachments) ? msg.attachments : [];
              const hasRenderableAttachments = attachmentList.length > 0;
              const content = msg.content || '';
              const isCustomer = msg.is_from_customer;
              const inferredAgentName = (
                msg.agent_display_name ||
                msg.additional_attributes?.agent_name ||
                resolveAgentDisplayName(msg, content) ||
                ''
              ).trim();
              const hasHumanAgentMarker = Boolean(
                inferredAgentName ||
                msg.additional_attributes?.sent_by ||
                msg.sender?.sender_type === 'agent'
              );
              // CORREÇÃO: Identificar mensagens da IA corretamente - verificação mais robusta
              const isAI = !isCustomer && !hasHumanAgentMarker && (
                msg.sender?.sender_type === 'ai' ||
                msg.from_ai === true ||
                msg.additional_attributes?.from_ai === true
              );

              const isBot = !isCustomer && !isAI && !hasHumanAgentMarker && (msg.message_type === 'incoming' || msg.sender?.sender_type === 'bot');
              const isAgent = !isCustomer && !isBot && !isAI;
              const chatbotDisplayName = (
                msg.additional_attributes?.chatbot_name ||
                conversation?.inbox?.provedor?.chatbot_name ||
                ''
              ).trim();
              const agentDisplayName = isAgent ? inferredAgentName : '';
              // Não usar heurística por "transferid" no conteúdo: respostas da IA ao cliente
              // (ex.: "chamado foi transferido...") não devem virar bolha de sistema.
              const isAssignmentMessage =
                !isAI &&
                typeof msg.content === 'string' &&
                (msg.content.includes('Conversa atribuída para') ||
                  msg.content.includes('Conversa transferida para') ||
                  msg.content.includes('Protocolo alterado de'));
              const isSystemMessage = !isAI && (msg.additional_attributes?.system_message || isAssignmentMessage);
              // Amarelo só no resumo interno da IA para a equipe (não em protocolo/apenas_atendentes genérico)
              const isResumoSuporte = msg.additional_attributes?.tipo === 'resumo_suporte';
              const isLarge = isLargeMessage(content);
              const isAgentAudioPlaceholderText =
                !isCustomer &&
                (msg.message_type === 'audio' || msg.message_type === 'ptt') &&
                (content || '').trim() === 'Mensagem de voz';
              const isMediaPlaceholderText = /^\[(image|audio|video|document|attachment|file|ig_reel|share|story_mention)\]$/i.test(
                (content || '').trim()
              );
              const messageTranscription = getMessageTranscription(msg);
              const hasTranscription = messageHasTranscription(msg);
              const displayTextContent = getContentWithoutTranscription(content, messageTranscription);
              const isTranscriptionExpanded = expandedTranscriptions.has(msg.id);

              // Determinar se a mensagem tem mídia
              const hasImage = attachmentList.some(att => att.file_type === 'image') ||
                (msg.message_type === 'image' && msg.file_url);
              const hasVideo = attachmentList.some(att => att.file_type === 'video') ||
                (msg.message_type === 'video' && msg.file_url);
              const hasAudio = attachmentList.some(att => att.file_type === 'audio') ||
                ((msg.message_type === 'audio' || msg.message_type === 'ptt') && msg.file_url);
              const hasDocument = attachmentList.some(att => att.file_type === 'file') ||
                (msg.message_type === 'document' && msg.file_url);

              const trimmedContent = (displayTextContent || '').trim();
              const hasCaptionText =
                trimmedContent &&
                !isMediaPlaceholderText &&
                !isAgentAudioPlaceholderText &&
                !(msg.additional_attributes?.is_invoice || trimmedContent.includes('dados para pagamento de sua fatura')) &&
                !trimmedContent.includes('QR Code PIX') &&
                !(trimmedContent.includes('🔗') && trimmedContent.includes('Link do Boleto:'));

              const isPureImageMessage =
                hasImage &&
                !hasVideo &&
                !hasAudio &&
                !hasDocument &&
                !hasCaptionText &&
                !(msg.message_type === 'image' && msg.content && msg.content.includes('QR Code PIX'));

              const isImageWithCaption =
                hasImage &&
                hasCaptionText &&
                !hasVideo &&
                !hasAudio &&
                !hasDocument;

              const locationInfo = getMessageLocation(msg);
              const isLocationMessage = Boolean(locationInfo);

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
                  relative
                  ${isPureImageMessage || isLocationMessage
                        ? 'p-0 bg-transparent shadow-none'
                        : isImageWithCaption
                          ? 'p-0 overflow-hidden shadow-sm rounded-2xl'
                          : 'px-5 py-3 shadow-sm rounded-2xl'
                      }
                  ${isReplyHighlight ? 'ring-2 ring-amber-400 dark:ring-amber-300 z-[1]' : ''}
                  ${isPureImageMessage || isLocationMessage
                        ? ''
                        : isCustomer
                        ? 'bg-[#4A5568] text-white'  // Mensagens recebidas (cliente)
                        : isResumoSuporte
                          ? 'bg-[#FFF9C4] text-[#856404] border border-[#FFE69C]'  // Resumo suporte - amarelo fraco
                          : isSystemMessage
                            ? 'bg-zinc-200/70 text-zinc-800 border border-zinc-300/60 dark:bg-zinc-800/55 dark:text-zinc-100 dark:border-white/10'  // Sistema (atribuição/transferência) - cinza fraco
                            : isAI || isBot
                              ? 'bg-[#2196F3] text-white'  // IA / bot
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
                      {/* Nome do chatbot / atendente — canto superior do balão */}
                      {!isCustomer && !isSystemMessage && !isLocationMessage && (isAI || isBot) && chatbotDisplayName && (
                        <div className="text-[11px] font-bold tracking-wide text-white/95 mb-3 pb-1.5 border-b border-white/20 text-left leading-tight">
                          {chatbotDisplayName}
                        </div>
                      )}
                      {!isCustomer && !isSystemMessage && !isLocationMessage && isAgent && agentDisplayName && (
                        <div className="text-[11px] font-semibold tracking-wide text-white/90 mb-2 pb-1 border-b border-white/15 text-left leading-tight">
                          {agentDisplayName}
                        </div>
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

                      {/* Card de localização (WhatsApp pin) */}
                      {isLocationMessage && locationInfo && (
                        <div className="shadow-md rounded-xl overflow-hidden">
                          <LocationMessageCard
                            lat={locationInfo.lat}
                            lng={locationInfo.lng}
                            name={locationInfo.name}
                            address={locationInfo.address}
                            isCustomer={isCustomer}
                          />
                        </div>
                      )}

                      {/* Anexos de imagem */}
                      {hasImage && hasRenderableAttachments && attachmentList.filter(att => att.file_type === 'image').map((attachment, index) => (
                        <div key={index} className={isPureImageMessage ? '' : 'mb-2'}>
                          <img
                            src={attachment.data_url}
                            alt="Imagem"
                            className={`max-w-full h-auto cursor-pointer hover:opacity-95 transition-opacity block ${
                              isPureImageMessage
                                ? 'rounded-2xl shadow-md'
                                : isImageWithCaption
                                  ? 'w-full rounded-t-2xl'
                                  : 'rounded-lg'
                            }`}
                            onClick={() => openImageInNewTab(attachment.data_url)}
                            style={{ maxHeight: isPureImageMessage ? '420px' : '300px' }}
                          />

                        </div>
                      ))}

                      {/* Imagens via file_url (WhatsApp/Telegram etc) - só se não tiver attachments */}
                      {hasImage && msg.message_type === 'image' && msg.file_url && !hasRenderableAttachments && (
                        <div className={isPureImageMessage ? '' : 'mb-2'}>
                          <img
                            src={buildMediaUrl(msg.file_url)}
                            alt="Imagem"
                            className={`max-w-full h-auto cursor-pointer hover:opacity-95 transition-opacity block ${
                              isPureImageMessage
                                ? 'rounded-2xl shadow-md'
                                : isImageWithCaption
                                  ? 'w-full rounded-t-2xl'
                                  : 'rounded-lg'
                            }`}
                            onClick={() => openImageInNewTab(buildMediaUrl(msg.file_url))}
                            style={{ maxHeight: isPureImageMessage ? '420px' : '300px' }}
                            onError={(e) => {
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

                      {/* Lista interativa do chatbot (menu/planos) — UI estilo WhatsApp; não exibir no Telegram */}
                      {conversation?.inbox?.channel_type !== 'telegram' &&
                        msg.additional_attributes?.interactive_rows &&
                        msg.additional_attributes.interactive_rows.length > 0 && (
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

                      {/* Botões interativos do chatbot (Menu) — UI estilo WhatsApp; não exibir no Telegram */}
                      {conversation?.inbox?.channel_type !== 'telegram' &&
                        msg.additional_attributes?.interactive_buttons &&
                        msg.additional_attributes.interactive_buttons.length > 0 && (
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

                      {/* Card de fatura — visual Meta / WhatsApp Oficial */}
                      {(msg.additional_attributes?.is_invoice ||
                        (content && content.includes('dados para pagamento de sua fatura'))) && (() => {
                        const attrs = msg.additional_attributes || {};
                        const invoiceNumber =
                          attrs.invoice_number ||
                          content.match(/N[ºo°]\s*(?:DA\s*)?COBRAN[ÇC]A:\s*(\d+)/i)?.[1] ||
                          'Fatura';
                        const { hasPix, hasBoleto } = resolveInvoicePaymentFlags(attrs);
                        const totalLabel = formatInvoiceCardAmount(attrs.amount, content || '');
                        const dueLabel = formatInvoiceCardDueDate(attrs.vencimento, content || '');
                        const merchant =
                          conversation?.inbox?.provedor?.nome ||
                          user?.provedores_admin?.[0]?.nome ||
                          user?.provedor?.nome ||
                          attrs.merchant_name ||
                          conversation?.inbox?.provedor?.company ||
                          conversation?.inbox?.provedor?.razao_social ||
                          '';
                        const pdfUrl = attrs.document_url || msg.file_url || '';
                        const bodyHtml = formatWhatsAppPreviewHtml(
                          (content || '').trim() || 'Dados para pagamento da fatura'
                        );

                        const copyFeedback = (btn, okText) => {
                          const span = btn.querySelector('[data-copy-label]');
                          if (!span) return;
                          const original = span.textContent;
                          span.textContent = okText;
                          setTimeout(() => {
                            span.textContent = original;
                          }, 2000);
                        };

                        return (
                          <div className="wa-tpl-card relative z-10 mt-2 mb-1 w-full max-w-[300px] shadow-lg">
                            <div className="wa-tpl-header">
                              <img className="h-4 w-4 shrink-0" src={whatsappIcon} alt="" />
                              <span className="min-w-0 truncate font-bold tracking-tight">Fatura</span>
                            </div>

                            <div className="wa-tpl-body">
                              <div className="wa-tpl-box shadow-sm">
                                <div className="border-b border-dashed border-[#8d9197] px-2.5 py-1.5 text-[11px] text-[#646464]">
                                  Nº da cobrança: {invoiceNumber}
                                </div>

                                {pdfUrl ? (
                                  <button
                                    type="button"
                                    onClick={(e) => {
                                      e.stopPropagation();
                                      window.open(pdfUrl, '_blank');
                                    }}
                                    className="m-2 flex w-[calc(100%-1rem)] items-center justify-between rounded-md border border-[#d9dce0] bg-[#f2f3f5] p-3 text-left transition-colors hover:bg-[#e8eaed]"
                                  >
                                    <div className="flex min-w-0 items-center gap-3">
                                      <FileText className="h-8 w-8 shrink-0 text-red-500" />
                                      <div className="min-w-0">
                                        <div className="truncate text-[13px] font-bold text-black">Fatura.pdf</div>
                                        <div className="text-[11px] text-[#444]">PDF · Abrir</div>
                                      </div>
                                    </div>
                                  </button>
                                ) : (
                                  <div className="m-2 flex items-center justify-between rounded-md border border-[#d9dce0] bg-[#f2f3f5] p-3">
                                    <div className="flex min-w-0 items-center gap-3">
                                      <FileText className="h-8 w-8 shrink-0 text-red-500" />
                                      <div className="min-w-0">
                                        <div className="truncate text-[13px] font-bold text-black">
                                          Cobrança {invoiceNumber}
                                        </div>
                                        <div className="text-[11px] text-[#444]">Quantidade: 1</div>
                                      </div>
                                    </div>
                                  </div>
                                )}

                                <div className="wa-tpl-payment">
                                  <div className="wa-tpl-payment-title">
                                    <span>Pagar com</span>
                                    <div className="flex items-center gap-2">
                                      {hasBoleto && (
                                        <div
                                          className="h-[17px] w-[17px] rounded-[2px]"
                                          style={{
                                            background:
                                              'repeating-linear-gradient(to right, #000 0px, #000 2px, #fff 2px, #fff 3px)',
                                          }}
                                          title="Boleto"
                                        />
                                      )}
                                      {hasPix && (
                                        <img
                                          className="h-[22px] w-[22px] object-contain"
                                          src={INVOICE_PIX_ICON}
                                          alt="Pix"
                                        />
                                      )}
                                    </div>
                                  </div>
                                  <div className="wa-tpl-total">
                                    <span>Total</span>
                                    <span className="text-right">
                                      {totalLabel}
                                      {dueLabel ? (
                                        <span className="mt-0.5 block text-[10px] font-normal text-[#6b7280]">
                                          Vence em: {dueLabel}
                                        </span>
                                      ) : null}
                                    </span>
                                  </div>
                                </div>

                                <div
                                  className="wa-tpl-message"
                                  style={{ maxHeight: '12rem', fontStyle: 'normal' }}
                                  dangerouslySetInnerHTML={{ __html: bodyHtml }}
                                />

                                {merchant ? (
                                  <div className="wa-tpl-footer uppercase tracking-wide">{merchant}</div>
                                ) : null}
                              </div>

                              {hasPix && (
                                <button
                                  type="button"
                                  className="wa-tpl-action"
                                  onClick={(e) => {
                                    e.stopPropagation();
                                    const pixCode =
                                      attrs.pix_code ||
                                      attrs.button_choices?.[0]?.split('copy:')[1] ||
                                      content.split('copy:')[1]?.split('\n')[0] ||
                                      '';
                                    if (pixCode) {
                                      navigator.clipboard.writeText(pixCode.trim());
                                      copyFeedback(e.currentTarget, 'Código Pix copiado!');
                                    } else {
                                      toast.info('Código Pix indisponível nesta mensagem');
                                    }
                                  }}
                                >
                                  <img className="h-4 w-4 shrink-0" src={INVOICE_COPY_ICON} alt="" />
                                  <span data-copy-label>Copiar código Pix</span>
                                </button>
                              )}
                              {hasBoleto && (
                                <button
                                  type="button"
                                  className="wa-tpl-action"
                                  onClick={(e) => {
                                    e.stopPropagation();
                                    const lineCode =
                                      attrs.line_code ||
                                      attrs.button_choices?.[1]?.split('copy:')[1] ||
                                      '';
                                    if (lineCode) {
                                      navigator.clipboard.writeText(lineCode.trim());
                                      copyFeedback(e.currentTarget, 'Código do boleto copiado!');
                                    } else if (pdfUrl) {
                                      window.open(pdfUrl, '_blank');
                                    } else {
                                      toast.info('Código do boleto indisponível nesta mensagem');
                                    }
                                  }}
                                >
                                  <img className="h-4 w-4 shrink-0" src={INVOICE_COPY_ICON} alt="" />
                                  <span data-copy-label>Copiar código do boleto</span>
                                </button>
                              )}
                            </div>
                          </div>
                        );
                      })()}

                      {hasTranscription && isTranscriptionExpanded && (
                        <div
                          className={`mt-2 rounded-lg px-3 py-2 text-sm ${
                            isCustomer ? 'bg-black/10' : 'bg-white/10'
                          }`}
                        >
                          <div className="mb-1 text-xs opacity-70">Transcrição</div>
                          <div className="whitespace-pre-wrap break-words">{messageTranscription}</div>
                        </div>
                      )}

                      {/* Conteúdo da mensagem (Texto) */}
                      {displayTextContent &&
                       !isLocationMessage &&
                       !isMediaPlaceholderText &&
                       !isAgentAudioPlaceholderText &&
                       !(msg.additional_attributes?.is_invoice ||
                        (displayTextContent && displayTextContent.includes('dados para pagamento de sua fatura'))) && (
                        <div className={`whitespace-pre-wrap break-words break-all ${isImageWithCaption ? 'px-4 py-3' : ''}`} style={{ wordBreak: 'break-word', overflowWrap: 'anywhere' }}>
                          {(() => {
                            let displayContent = displayTextContent;
                            if (!isCustomer) {
                              const stripped = stripAgentSignature(displayTextContent);
                              if (stripped.name) {
                                displayContent = stripped.body;
                              } else if (displayTextContent.includes('*') && displayTextContent.includes('disse:*')) {
                                displayContent = displayTextContent.split('\n').slice(1).join('\n').trim() || displayTextContent;
                              }
                            }
                            // Evitar duplicar nome: já exibido no canto superior do balão
                            const headerName = agentDisplayName || chatbotDisplayName;
                            if (headerName && displayContent) {
                              const boldPrefix = `*${headerName}*`;
                              if (displayContent.startsWith(boldPrefix)) {
                                displayContent = displayContent.slice(boldPrefix.length).replace(/^\n+/, '');
                              } else if (displayContent.startsWith(headerName)) {
                                displayContent = displayContent.slice(headerName.length).replace(/^[:\s\n]+/, '');
                              }
                            }
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
                      <div className={`flex w-full min-w-0 items-center justify-between gap-2 ${isLocationMessage ? 'mt-1.5 px-0.5' : 'mt-1'}`}>
                        <div
                          className={`flex min-w-0 flex-wrap items-center gap-x-2 gap-y-0.5 text-left text-xs ${
                            isLocationMessage
                              ? 'text-muted-foreground'
                              : isCustomer
                                ? 'text-muted-foreground'
                                : 'text-white'
                          }`}
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
                          {hasTranscription && (
                            <button
                              type="button"
                              onClick={() => toggleMessageTranscription(msg.id)}
                              className={`rounded-full p-1 text-xs hover:bg-white/20 ${isCustomer ? 'hover:bg-black/10' : ''} ${
                                isTranscriptionExpanded ? 'opacity-100' : 'opacity-75'
                              }`}
                              title={isTranscriptionExpanded ? 'Ocultar transcrição' : 'Ver transcrição'}
                            >
                              <FileText className="h-4 w-4" />
                            </button>
                          )}
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
              })}
            </>
          )}

          <div ref={messagesEndRef} />
        </div>
      </div>

      {/* Composer fixo: resposta, prévias e gravação acima do campo (não ficam por baixo do rodapé) */}
      <div className="pointer-events-auto absolute bottom-0 left-0 right-0 z-20 flex flex-col">
        {/* Área de resposta */}
        {replyingToMessage && (
          <div className="shrink-0 border-t border-border bg-card px-3 py-2.5 shadow-[0_-4px_16px_rgba(0,0,0,0.35)]">
          <div className="flex items-center justify-between gap-3 rounded-lg border border-border bg-muted px-3 py-2">
            <div className="min-w-0 flex-1 border-l-2 border-primary pl-2.5">
              <div className="mb-0.5 text-xs font-semibold text-primary">Respondendo a:</div>
              <div className="truncate text-sm text-foreground">
                {replyingToMessage.content || 'Mensagem'}
              </div>
            </div>
            <button
              type="button"
              onClick={cancelReply}
              className="h-8 shrink-0 rounded-md border-0 px-3 text-sm font-medium text-white shadow-sm transition-opacity hover:opacity-90 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-red-500/60 focus-visible:ring-offset-2 focus-visible:ring-offset-background"
              style={{ backgroundColor: '#DC2626' }}
              title="Cancelar resposta"
            >
              ✕
            </button>
          </div>
        </div>
      )}

      {/* Preview de áudio gravado — mesmo visual do balão de mensagem do agente */}
      {audioUrl && (
        <div className="shrink-0 border-t border-border bg-card/95 px-3 py-3 shadow-[0_-4px_16px_rgba(0,0,0,0.35)]">
          <div className="ml-auto flex max-w-[min(100%,22rem)] flex-col items-end gap-2">
            <div className="w-full rounded-2xl bg-[#2196F3] px-4 py-3 text-white shadow-sm">
              <div className="mb-2 text-xs font-semibold text-white/95">
                {user?.first_name || user?.username || 'Você'}
              </div>
              <CustomAudioPlayer
                src={audioUrl}
                isCustomer={false}
                conversationId={conversation?.id}
              />
              <div className="mt-2 text-[10px] text-white/70">
                Áudio gravado · pronto para enviar
              </div>
            </div>
            <div className="flex items-center gap-2">
              <button
                type="button"
                onClick={sendAudioMessage}
                disabled={sendingMedia}
                className="rounded-lg bg-white px-4 py-2 text-sm font-semibold text-[#1e293b] shadow-sm transition hover:bg-white/90 disabled:opacity-50"
              >
                {sendingMedia ? 'Enviando...' : 'Enviar'}
              </button>
              <button
                type="button"
                onClick={() => {
                  if (audioUrl) URL.revokeObjectURL(audioUrl);
                  setAudioBlob(null);
                  setAudioUrl(null);
                  setRecordingTime(0);
                }}
                disabled={sendingMedia}
                className="rounded-lg px-4 py-2 text-sm font-semibold text-white shadow-sm transition hover:opacity-90 disabled:opacity-50"
                style={{ backgroundColor: '#DC2626' }}
              >
                Cancelar
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Prévia de Mídia Pendente */}
      {pendingFile && (
        <div className="shrink-0 border-t border-border bg-card p-4 animate-in slide-in-from-bottom-2">
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

        {/* Barra de gravação — sempre acima do campo de texto */}
        {isRecording && (
          <div className="shrink-0 border-t border-primary/35 bg-background/95 px-4 py-2.5 shadow-[0_-6px_20px_rgba(234,88,12,0.22)] backdrop-blur-md dark:bg-zinc-950/95">
            <div className="flex items-center justify-between gap-3">
              <div className="flex min-w-0 items-center gap-2 text-sm text-muted-foreground">
                <span className="inline-flex h-2 w-2 shrink-0 animate-pulse rounded-full bg-red-500" aria-hidden />
                <span className="truncate font-medium text-foreground">Gravando áudio</span>
                <span className="font-mono text-red-500 tabular-nums">{formatRecordingTime(recordingTime)}</span>
              </div>
              <div className="flex shrink-0 items-center gap-2">
                <button
                  type="button"
                  onClick={cancelRecording}
                  className="rounded-lg p-2 text-red-500 transition-colors hover:bg-red-50 dark:hover:bg-red-950"
                  title="Cancelar gravação"
                >
                  <Square className="h-5 w-5" />
                </button>
                <button
                  type="button"
                  onClick={stopRecording}
                  className="rounded-lg p-2 text-green-600 transition-colors hover:bg-green-50 dark:hover:bg-green-950"
                  title="Parar e revisar"
                >
                  <MicOff className="h-5 w-5" />
                </button>
              </div>
            </div>
          </div>
        )}

      {/* Input de mensagem */}
      <div className="glass-chat-footer shrink-0 overflow-visible py-2 px-4">
        {!cannotReply && is24hWindowOpen === false && isWhatsAppChannel ? (
          <div className="flex w-full items-center justify-between gap-3 rounded-xl border border-black/10 bg-zinc-200/90 px-4 py-3 shadow-inner backdrop-blur-md dark:border-white/15 dark:bg-zinc-900/75">
            <p className="min-w-0 flex-1 text-left text-sm font-medium leading-snug text-red-600 dark:text-red-400">
              O período de 24h para enviar mensagens expirou. Envie um novo template para continuar o atendimento.
            </p>
            <button
              type="button"
              onClick={openTemplatesModal}
              className="shrink-0 rounded-lg bg-[#1877f2] px-4 py-2.5 text-sm font-semibold text-white shadow-md transition-colors hover:bg-[#1664d8] active:scale-[0.98]"
              title="Escolher template do WhatsApp"
            >
              Enviar template
            </button>
          </div>
        ) : (
        <div className="flex items-end space-x-2 overflow-visible">
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
            disabled={cannotReply || sendingMedia || (is24hWindowOpen === false && isWhatsAppChannel)}
            className="p-2 text-muted-foreground hover:text-primary hover:bg-white/10 rounded-xl transition-all disabled:opacity-50"
            title={cannotReply ? 'Clique em Atender para enviar arquivos' : (is24hWindowOpen === false && isWhatsAppChannel) ? "Janela de 24 horas fechada" : "Enviar arquivo"}
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
              disabled={cannotReply || (is24hWindowOpen === false && isWhatsAppChannel)}

              className={`p-2 rounded-xl transition-all disabled:opacity-50 ${showEmojiPicker ? 'text-primary bg-white/10' : 'text-muted-foreground hover:text-primary hover:bg-white/10'}`}
              title={cannotReply ? 'Clique em Atender para usar o chat' : 'Inserir emoji'}
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
              disabled={cannotReply || sendingMedia || (is24hWindowOpen === false && isWhatsAppChannel)}
              className={`p-2 rounded-xl transition-all disabled:opacity-50 ${showEmojiGallery ? 'text-primary bg-white/10' : 'text-muted-foreground hover:text-primary hover:bg-white/10'}`}
              title={cannotReply ? 'Clique em Atender para usar o chat' : 'Galeria de emojis (imagem)'}
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
            {cannotReply ? (
              <div
                className={`w-full rounded-lg border px-3 py-2.5 text-sm font-medium shadow-sm ${
                  supervisorMode
                    ? 'border-emerald-600/50 bg-emerald-950 text-emerald-50'
                    : hideWaitingQueueContent
                    ? 'border-sky-600/50 bg-sky-950 text-sky-50'
                    : 'border-red-800 bg-[#2a0c10] text-red-50'
                }`}
              >
                {supervisorMode
                  ? 'Modo supervisão: Não é possível enviar mensagens neste atendimento.'
                  : hideWaitingQueueContent
                  ? 'Atribua esta conversa a você para ver o histórico e enviar mensagens.'
                  : 'Para responder o cliente, primeiro assuma o atendimento clicando em “Atender”.'}
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
                  onPaste={handlePasteIntoChat}
                  placeholder="Digite sua mensagem..."
                  className="w-full resize-none rounded-2xl border border-input bg-white px-4 py-2 pr-12 text-sm text-black caret-orange-600 ring-offset-background placeholder:text-muted-foreground focus:outline-none focus:ring-1 focus:ring-ring disabled:cursor-not-allowed disabled:opacity-50 transition-all shadow-lg dark:border-white/15 dark:bg-zinc-900 dark:text-white dark:placeholder:text-zinc-400 dark:focus:ring-white/25"
                  rows={1}
                  style={{
                    minHeight: '38px',
                    maxHeight: '150px',
                    height: 'auto',
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

          {/* Botão de gravação/envio — durante gravação os controlos estão na barra acima */}
          <div className="shrink-0 self-end pb-0.5">
          {cannotReply ? (
            <button
              disabled
              className="p-2 bg-accent text-accent-foreground rounded-lg transition-colors disabled:cursor-not-allowed disabled:opacity-50"
              title="Clique em Atender para enviar mensagens"
            >
              <Send className="w-5 h-5" />
            </button>
          ) : isRecording ? (
            <div className="h-10 w-10 shrink-0" aria-hidden />
          ) : (
            <button
              onClick={message.trim() ? handleSendMessage : startRecording}
              disabled={cannotReply || sendingMedia}
              className={CHAT_ORANGE_SEND_BTN}
              style={chatOrangeSendStyle()}
              title={cannotReply ? 'Clique em Atender primeiro' : message.trim() ? 'Enviar mensagem' : 'Gravar áudio'}
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
                        if (msg.message_type === 'location' || getMessageLocation(msg)) return '[Localização]';
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
                          className="ml-4 px-4 py-2 text-white rounded-lg hover:opacity-90 transition-colors disabled:opacity-50 disabled:cursor-not-allowed text-sm font-medium"
                          style={chatOrangeSendStyle()}
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
            onConversationUpdate={onConversationUpdate}
          />
        </div>
      )}

      {/* Modal CSAT ao encerrar */}
      {showCloseCSATModal && (
        <Dialog open={showCloseCSATModal} onOpenChange={setShowCloseCSATModal}>
          <DialogContent className="max-w-md">
            <DialogHeader>
              <DialogTitle>Encerrar atendimento</DialogTitle>
              <DialogDescription>
                Deseja enviar a pesquisa de satisfação (CSAT) para o cliente após encerrar?
              </DialogDescription>
            </DialogHeader>
            <div className="flex items-center justify-end gap-2 pt-2">
              <button
                type="button"
                onClick={() => setShowCloseCSATModal(false)}
                disabled={isClosingConversation}
                className="h-8 rounded-md px-3 text-xs font-semibold border border-border bg-muted text-foreground hover:bg-muted/80 disabled:opacity-50"
              >
                Cancelar
              </button>
              <button
                type="button"
                onClick={() => confirmCloseConversation(false)}
                disabled={isClosingConversation}
                className="h-8 rounded-md px-3 text-xs font-semibold border-0 shadow-sm transition-opacity hover:opacity-90 disabled:opacity-50"
                style={{ backgroundColor: '#64748B', color: '#ffffff' }}
              >
                Encerrar sem CSAT
              </button>
              <button
                type="button"
                onClick={() => confirmCloseConversation(true)}
                disabled={isClosingConversation}
                className="h-8 rounded-md px-3 text-xs font-semibold border-0 shadow-sm transition-opacity hover:opacity-90 disabled:opacity-50"
                style={{ backgroundColor: '#16A34A', color: '#ffffff' }}
              >
                {isClosingConversation ? 'Encerrando…' : 'Encerrar e enviar CSAT'}
              </button>
            </div>
          </DialogContent>
        </Dialog>
      )}

      <IncomingCallPopup
        open={voiceCall.panelVisible}
        contactName={contactName || conversation?.contact?.name}
        contactPhone={voiceCall.capability?.contact_phone || conversation?.contact?.phone}
        statusText={voiceCall.statusText}
        inCall={voiceCall.inCall}
        connecting={voiceCall.connecting}
        incoming={null}
        elapsed={voiceCall.elapsed}
        muted={voiceCall.muted}
        onAccept={() => {}}
        onReject={() => {}}
        onHangup={voiceCall.hangup}
        onToggleMute={voiceCall.toggleMute}
        onStart={voiceCall.startOutboundCall}
        canStart={Boolean(voiceCall.capability?.available)}
        onDismiss={voiceCall.dismissPanel}
        audioRef={voiceCall.audioRef}
      />
    </div>
  );
};

export default ChatArea;
