import React, { useState, useEffect, useRef, useMemo, memo } from 'react';
import { Search, Filter, MoreHorizontal, User, Clock, Tag, MoreVertical, UserPlus, X, UserCheck, Archive } from 'lucide-react';
import axios from 'axios';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from './ui/dialog';
import { useNotifications } from '../contexts/NotificationContext';
import TemplateSelectWithPreview from './TemplateSelectWithPreview';
import TemplateMessagePreview from './TemplateMessagePreview';
import { findTemplateByName } from '../utils/templatePreview';
import { toast } from '../lib/notify';
import {
  getConversationStatus as getConversationStatusShared,
  hasHumanAssignee as hasHumanAssigneeShared,
  isAutomationConversation as isAutomationConversationShared,
  isClosedConversation as isClosedConversationShared,
  isWaitingConversation as isWaitingConversationShared,
} from '../utils/conversationNotificationSound';
import {
  isValidWhatsAppPhone,
  normalizeWhatsAppPhone,
  WHATSAPP_PHONE_ERROR,
} from '../utils/phoneWhatsApp';
import '../styles/wa-template-preview.css';

const MODAL_SELECT_CLASS =
  'attendance-modal-select w-full min-w-0 max-w-full rounded-lg border border-white/10 bg-[#1a1a1a] px-3 py-2 text-sm text-white focus:outline-none focus:ring-1 focus:ring-white/20';
const MODAL_OPTION_CLASS = 'bg-[#1a1a1a] text-white';

const ConversationList = memo(({ onConversationSelect, selectedConversation, provedorId, onConversationUpdate, onActiveTabChange, user }) => {
  const { subscribePainelEvents } = useNotifications();

  const [searchTerm, setSearchTerm] = useState(() => {
    return localStorage.getItem('conversationSearchTerm') || '';
  });

  const [activeTab, setActiveTab] = useState(() => {
    const savedTab = localStorage.getItem('conversationListActiveTab');
    // Compatibilidade com aba antiga "ai"
    if (savedTab === 'ai') return 'automation';
    return savedTab || 'mine';
  });

  const [conversations, setConversations] = useState([]);
  const [loading, setLoading] = useState(false);
  const [elapsedTick, setElapsedTick] = useState(0);
  const userPermissions = useMemo(() => user?.permissions || [], [user]);
  const userRole = useMemo(() => user?.role || user?.user_type || '', [user]);
  const isProviderAdmin = useMemo(() => {
    return ['admin', 'company_admin', 'provedor_admin'].includes(userRole);
  }, [userRole]);
  const canBulkClose = useMemo(() => {
    return userRole === 'superadmin' || userRole === 'admin';
  }, [userRole]);

  /** IDs de equipes do utilizador (auth/me devolve teams + team principal). */
  const userTeamIds = useMemo(() => {
    const ids = new Set();
    const list = user?.teams;
    if (Array.isArray(list)) {
      list.forEach((t) => {
        if (t && t.id != null) ids.add(String(t.id));
      });
    }
    if (user?.team?.id != null) {
      ids.add(String(user.team.id));
    }
    return ids;
  }, [user]);
  const [hasInitialized, setHasInitialized] = useState(false);
  const [newMessageNotification, setNewMessageNotification] = useState(false);
  const faviconTimerRef = useRef(null);
  const isFaviconBlinkingRef = useRef(false);
  const [lastUpdateTime, setLastUpdateTime] = useState(null);
  const authReady = useMemo(() => !!user, [user]);

  //  Estados para novo atendimento
  const [showMenuAtendimento, setShowMenuAtendimento] = useState(false);
  const [modalNovoContato, setModalNovoContato] = useState(false);
  const [modalContatoExistente, setModalContatoExistente] = useState(false);

  const [novoContato, setNovoContato] = useState({
    nome: '',
    telefone: '',
    canal: 'whatsapp',
    mensagem: '',
    usarTemplate: false,
    templateSelecionado: null,
    inboxId: null,
    canal_id: null
  });

  const [templates, setTemplates] = useState([]);
  const [carregandoTemplates, setCarregandoTemplates] = useState(false);

  const [contatoExistente, setContatoExistente] = useState({
    busca: '',
    contato: null,
    mensagem: '',
    usarTemplate: false,
    templateSelecionado: null,
    inboxId: null,
    canal: 'whatsapp',
    canal_id: null
  });

  const [enviandoAtendimento, setEnviandoAtendimento] = useState(false);
  const [buscandoContato, setBuscandoContato] = useState(false);
  const [contatosEncontrados, setContatosEncontrados] = useState([]);
  const [inboxes, setInboxes] = useState([]);
  const [carregandoInboxes, setCarregandoInboxes] = useState(false);

  const [showBulkCloseModal, setShowBulkCloseModal] = useState(false);
  const [bulkCloseScope, setBulkCloseScope] = useState('automation');
  const [bulkCloseTimeMode, setBulkCloseTimeMode] = useState('any');
  const [bulkCloseMinutes, setBulkCloseMinutes] = useState('10');
  const [bulkClosePreviewCount, setBulkClosePreviewCount] = useState(null);
  const [bulkCloseLoading, setBulkCloseLoading] = useState(false);
  const [bulkCloseError, setBulkCloseError] = useState('');
  const [providerConfig, setProviderConfig] = useState(null);
  const automationTabLabel = providerConfig?.chatbot_mode ? 'Automação' : 'Com a IA';

  //  Função para buscar contatos existentes
  const buscarContatos = async (termo) => {
    if (!termo.trim()) {
      setContatosEncontrados([]);
      return;
    }

    setBuscandoContato(true);
    // Priorizar auth_token que é o padrão salvo no Login, mas aceitar token também para compatibilidade
    const token = localStorage.getItem('auth_token') || localStorage.getItem('token');

    try {
      const response = await axios.get(`/api/contacts/?search=${termo}`, {
        headers: { Authorization: `Token ${token}` }
      });

      setContatosEncontrados(response.data.results || []);
    } catch (error) {
      // Erro ao buscar contatos
      setContatosEncontrados([]);
    } finally {
      setBuscandoContato(false);
    }
  };

  // Função para buscar inboxes
  const fetchInboxes = async () => {
    if (!provedorId) return;

    setCarregandoInboxes(true);
    const token = localStorage.getItem('auth_token') || localStorage.getItem('token');

    try {
      const response = await axios.get('/api/inboxes/', {
        headers: { Authorization: `Token ${token}` },
        params: { provedor_id: provedorId }
      });

      const results = response.data.results || response.data || [];
      const filteredInboxes = results.filter(i => i.is_active !== false);
      setInboxes(filteredInboxes);

      // Auto-selecionar se houver apenas um
      if (filteredInboxes.length === 1) {
        const inboxId = filteredInboxes[0].id;
        setNovoContato(prev => ({ ...prev, inboxId }));
        setContatoExistente(prev => ({ ...prev, inboxId }));
      }
    } catch (error) {
    } finally {
      setCarregandoInboxes(false);
    }
  };

  // Removido prompt de desbloqueio (UX simplificada)
  useEffect(() => { }, [authReady]);

  // Modo do provedor: chatbot = Automação, ia = Com a IA
  useEffect(() => {
    const fetchProviderConfig = async () => {
      if (!authReady) return;
      const token = localStorage.getItem('auth_token') || localStorage.getItem('token');
      if (!token) return;
      try {
        const response = await axios.get('/api/provider/config/', {
          headers: { Authorization: `Token ${token}` },
        });
        setProviderConfig(response.data);
      } catch (err) {
      }
    };
    fetchProviderConfig();
  }, [authReady]);

  // Buscar templates quando modal abrir
  useEffect(() => {
    if (modalNovoContato) {
      buscarCanalWhatsApp();
      fetchInboxes();
    } else if (modalContatoExistente) {
      buscarCanalWhatsApp();
      fetchInboxes();
    } else if (!modalNovoContato && !modalContatoExistente) {
      // Limpar templates quando fechar modal
      setTemplates([]);
      setNovoContato(prev => ({ ...prev, usarTemplate: false, templateSelecionado: null, canal_id: null, inboxId: null }));
      setContatoExistente(prev => ({ ...prev, usarTemplate: false, templateSelecionado: null, canal_id: null, inboxId: null }));
    }
  }, [modalNovoContato, modalContatoExistente]);

  // Função para buscar templates do canal WhatsApp
  const buscarTemplates = async (canalId) => {
    if (!canalId) return;

    setCarregandoTemplates(true);
    // Priorizar auth_token que é o padrão salvo no Login, mas aceitar token também para compatibilidade
    const token = localStorage.getItem('auth_token') || localStorage.getItem('token');

    try {
      const response = await axios.get(`/api/canais/${canalId}/message-templates/`, {
        headers: { Authorization: `Token ${token}` }
      });

      // O endpoint retorna { success: true, templates: [...] }
      const templatesList = response.data?.templates || response.data || [];


      // Filtrar apenas templates aprovados (case-insensitive para segurança)
      const templatesAprovados = templatesList.filter(t =>
        t.status && t.status.toUpperCase() === 'APPROVED'
      );

      setTemplates(templatesAprovados);


      if (templatesAprovados.length === 0 && templatesList.length > 0) {
      }
    } catch (error) {
      setTemplates([]);
    } finally {
      setCarregandoTemplates(false);
    }
  };

  // Função para buscar canal WhatsApp ativo compatível com templates
  const buscarCanalWhatsApp = async () => {
    const token = localStorage.getItem('auth_token') || localStorage.getItem('token');
    try {
      const params = {};
      if (provedorId) {
        params.provedor_id = provedorId;
      }

      const response = await axios.get('/api/canais/', {
        headers: { Authorization: `Token ${token}` },
        params: params
      });

      const canais = response.data.results || response.data || [];

      // Tentar encontrar WhatsApp Oficial com WABA_ID primeiro, depois qualquer WhatsApp oficial ativo
      const canalWhatsApp = canais.find(c => c.tipo === 'whatsapp_oficial' && c.ativo && c.waba_id) || 
                          canais.find(c => c.tipo === 'whatsapp_oficial' && c.ativo) ||
                          canais.find(c => c.tipo === 'whatsapp' && c.ativo);

      if (canalWhatsApp) {
        setNovoContato(prev => ({ ...prev, canal_id: canalWhatsApp.id }));
        setContatoExistente(prev => ({ ...prev, canal_id: canalWhatsApp.id }));
        buscarTemplates(canalWhatsApp.id);
      } else {
        setTemplates([]);
      }
    } catch (error) {
      setTemplates([]);
    }
  };

  //  Função para criar atendimento com novo contato
  const handleNovoContato = async () => {
    if (!novoContato.nome || !novoContato.telefone) {
      toast.error('Por favor, preencha nome e telefone');
      return;
    }

    // Se usar template, não precisa de mensagem
    if (!novoContato.usarTemplate && !novoContato.mensagem) {
      toast.error('Por favor, digite uma mensagem ou selecione um template');
      return;
    }

    // Se usar template, deve ter template selecionado
    if (novoContato.usarTemplate && !novoContato.templateSelecionado) {
      toast.error('Por favor, selecione um template');
      return;
    }

    const telefoneFormatado = normalizeWhatsAppPhone(novoContato.telefone);
    if (!isValidWhatsAppPhone(telefoneFormatado)) {
      toast.error(WHATSAPP_PHONE_ERROR);
      return;
    }

    setEnviandoAtendimento(true);
    // Priorizar auth_token que é o padrão salvo no Login, mas aceitar token também para compatibilidade
    const token = localStorage.getItem('auth_token') || localStorage.getItem('token');

    try {
      // Se usar template e canal for WhatsApp (qualquer tipo), usar endpoint de template
      if (novoContato.usarTemplate && (novoContato.canal === 'whatsapp' || novoContato.canal === 'whatsapp_oficial') && novoContato.canal_id) {
        const template = templates.find(t => t.name === novoContato.templateSelecionado);

        if (!template) {
          toast.error('Template não encontrado');
          setEnviandoAtendimento(false);
          return;
        }

        const response = await axios.post('/api/conversations/start-with-template/', {
          phone: telefoneFormatado,
          template_name: template.name,
          template_language: template.language || 'pt_BR',
          template_components: [], // TODO: Adicionar suporte a parâmetros
          canal_id: novoContato.canal_id,
          contact_name: novoContato.nome
        }, {
          headers: { Authorization: `Token ${token}` }
        });

        if (response.data.success) {
          toast.success('Template enviado com sucesso! A conversa aparecerá no painel em instantes.');
          setNovoContato({ nome: '', telefone: '', canal: 'whatsapp', mensagem: '', usarTemplate: false, templateSelecionado: null, canal_id: null });
          setModalNovoContato(false);
          setTimeout(() => fetchConversations(true), 1000);
        } else {
          throw new Error(response.data.error || 'Erro ao enviar template');
        }

        setEnviandoAtendimento(false);
        return;
      }

      // Fluxo original para mensagem normal
      const userResponse = await axios.get('/api/auth/me/', {
        headers: { Authorization: `Token ${token}` }
      });

      // 1. Criar ou buscar contato
      let contactResponse;
      try {
        contactResponse = await axios.post('/api/contacts/', {
          name: novoContato.nome,
          phone: telefoneFormatado,
          provedor: 2
        }, {
          headers: { Authorization: `Token ${token}` }
        });
      } catch (error) {
        if (error.response?.status === 400 && error.response?.data?.non_field_errors?.[0]?.includes('único')) {
          // Contato já existe, buscar o existente
          const contactsResponse = await axios.get(`/api/contacts/?phone=${telefoneFormatado}`, {
            headers: { Authorization: `Token ${token}` }
          });
          contactResponse = { data: contactsResponse.data.results[0] };
        } else {
          throw error;
        }
      }

      // 2. Buscar inbox (usar o selecionado ou o padrão)
      let inboxId = novoContato.inboxId;

      if (!inboxId) {
        const inboxesResponse = await axios.get('/api/inboxes/', {
          headers: { Authorization: `Token ${token}` }
        });

        const inbox = inboxesResponse.data.results.find(
          inbox => inbox.channel_type === novoContato.canal
        ) || inboxesResponse.data.results[0];

        if (!inbox) {
          throw new Error('Nenhum inbox encontrado');
        }
        inboxId = inbox.id;
      }

      // 3. Criar conversa
      const conversationResponse = await axios.post('/api/conversations/', {
        contact_id: contactResponse.data.id,
        inbox_id: inboxId,
        assignee_id: userResponse.data.id,
        status: 'open'
      }, {
        headers: { Authorization: `Token ${token}` }
      });

      // 4. Enviar mensagem inicial
      const messageResponse = await axios.post('/api/messages/send_text/', {
        content: novoContato.mensagem,
        conversation_id: conversationResponse.data.id
      }, {
        headers: { Authorization: `Token ${token}` }
      });

      toast.success('Atendimento criado com sucesso! Aparecerá no painel em instantes.');
      setNovoContato({ nome: '', telefone: '', canal: 'whatsapp', mensagem: '', usarTemplate: false, templateSelecionado: null, canalId: null });
      setModalNovoContato(false);

      // Recarregar conversas
      setTimeout(() => fetchConversations(true), 1000);

    } catch (error) {
      // Erro exibido pelo popup global
    } finally {
      setEnviandoAtendimento(false);
    }
  };

  //  Função para criar atendimento com contato existente
  const handleContatoExistente = async () => {
    if (!contatoExistente.contato) {
      toast.error('Por favor, selecione um contato');
      return;
    }

    if (!contatoExistente.usarTemplate && !contatoExistente.mensagem) {
      toast.error('Por favor, digite uma mensagem ou selecione um template');
      return;
    }

    // Se usar template, deve ter template selecionado
    if (contatoExistente.usarTemplate && !contatoExistente.templateSelecionado) {
      toast.error('Por favor, selecione um template');
      return;
    }

    setEnviandoAtendimento(true);
    // Priorizar auth_token que é o padrão salvo no Login, mas aceitar token também para compatibilidade
    const token = localStorage.getItem('auth_token') || localStorage.getItem('token');

    try {
      // Se usar template, usar endpoint de template
      if (contatoExistente.usarTemplate && contatoExistente.canal_id) {
        const template = templates.find(t => t.name === contatoExistente.templateSelecionado);

        if (!template) {
          toast.error('Template não encontrado');
          setEnviandoAtendimento(false);
          return;
        }

        const response = await axios.post('/api/conversations/start-with-template/', {
          phone: contatoExistente.contato.phone,
          template_name: template.name,
          template_language: template.language || 'pt_BR',
          template_components: [],
          canal_id: contatoExistente.canal_id,
          contact_name: contatoExistente.contato.name
        }, {
          headers: { Authorization: `Token ${token}` }
        });

        if (response.data.success) {
          toast.success('Template enviado com sucesso! A conversa aparecerá no painel em instantes.');
          setContatoExistente({ busca: '', contato: null, mensagem: '', usarTemplate: false, templateSelecionado: null, canal_id: null });
          setModalContatoExistente(false);
          setContatosEncontrados([]);
          setTimeout(() => fetchConversations(true), 1000);
        } else {
          throw new Error(response.data.error || 'Erro ao enviar template');
        }

        setEnviandoAtendimento(false);
        return;
      }

      // Fluxo original para mensagem normal
      const userResponse = await axios.get('/api/auth/me/', {
        headers: { Authorization: `Token ${token}` }
      });

      // 1. Buscar inbox (usar o selecionado ou o padrão)
      let inboxId = contatoExistente.inboxId;

      if (!inboxId) {
        const inboxesResponse = await axios.get('/api/inboxes/', {
          headers: { Authorization: `Token ${token}` }
        });

        const inbox = inboxesResponse.data.results.find(
          inbox => inbox.channel_type === 'whatsapp'
        ) || inboxesResponse.data.results[0];

        if (!inbox) {
          throw new Error('Nenhum inbox encontrado');
        }
        inboxId = inbox.id;
      }

      // 2. Criar conversa (incluindo assignee_id para inibir IA)
      const conversationResponse = await axios.post('/api/conversations/', {
        contact_id: contatoExistente.contato.id,
        inbox_id: inboxId,
        assignee_id: userResponse.data.id,
        status: 'open'
      }, {
        headers: { Authorization: `Token ${token}` }
      });

      // 3. Enviar mensagem inicial
      const messageResponse = await axios.post('/api/messages/send_text/', {
        content: contatoExistente.mensagem,
        conversation_id: conversationResponse.data.id
      }, {
        headers: { Authorization: `Token ${token}` }
      });

      toast.success('Atendimento criado com contato existente! Aparecerá no painel em instantes.');
      setContatoExistente({ busca: '', contato: null, mensagem: '', usarTemplate: false, templateSelecionado: null, canalId: null });
      setModalContatoExistente(false);
      setContatosEncontrados([]);

      // Recarregar conversas
      setTimeout(() => fetchConversations(true), 1000);

    } catch (error) {
      // Erro exibido pelo popup global
    } finally {
      setEnviandoAtendimento(false);
    }
  };

  // Ref para verificar se o componente está montado
  const isMounted = useRef(true);
  const retryTimeoutRef = useRef(null);
  const handlePainelWsEventRef = useRef(null);

  // Cleanup quando o componente desmontar
  useEffect(() => {
    isMounted.current = true;

    return () => {
      isMounted.current = false;
      if (retryTimeoutRef.current) {
        clearTimeout(retryTimeoutRef.current);
      }
    };
  }, []);

  // Salvar termo de busca no localStorage
  useEffect(() => {
    localStorage.setItem('conversationSearchTerm', searchTerm);
  }, [searchTerm]);

  // Salvar aba ativa no localStorage
  useEffect(() => {
    localStorage.setItem('conversationListActiveTab', activeTab);
  }, [activeTab]);

  const setFavicon = (hrefBase) => {
    try {
      const href = `${hrefBase}?v=${Date.now()}`; // cache-busting
      const links = Array.from(document.querySelectorAll("link[rel~='icon']"));
      if (links.length > 0) {
        links.forEach(l => { l.href = href; });
      } else {
        // Criar tanto 'icon' quanto 'shortcut icon' para compatibilidade
        const link1 = document.createElement('link');
        link1.rel = 'icon';
        link1.type = 'image/png';
        link1.href = href;
        document.head.appendChild(link1);
        const link2 = document.createElement('link');
        link2.rel = 'shortcut icon';
        link2.type = 'image/png';
        link2.href = href;
        document.head.appendChild(link2);
      }
    } catch (_) { }
  };

  const startBlinkingFavicon = () => {
    if (isFaviconBlinkingRef.current) return;
    isFaviconBlinkingRef.current = true;
    const defaultIcon = '/favicon.png';
    const notifyIcon = '/favicon_red.png';
    let toggle = false;
    faviconTimerRef.current = setInterval(() => {
      if (document.visibilityState === 'visible') {
        // parar quando a aba estiver ativa
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
    setFavicon('/favicon.png');
  };

  const fetchTimeoutRef = useRef(null);
  /** Após o primeiro ciclo de fetch (sucesso ou erro), permite alinhar seleção com a aba ativa. */
  const conversationsListFetchedRef = useRef(false);
  const selectedConversationRef = useRef(selectedConversation);
  const onConversationUpdateRef = useRef(onConversationUpdate);

  useEffect(() => {
    selectedConversationRef.current = selectedConversation;
  }, [selectedConversation]);

  useEffect(() => {
    onConversationUpdateRef.current = onConversationUpdate;
  }, [onConversationUpdate]);

  useEffect(() => {
    conversationsListFetchedRef.current = false;
  }, [provedorId, authReady]);

  // Função para buscar conversas com debounce
  const fetchConversations = async (forceRefresh = false) => {
    if (!isMounted.current || !authReady) {
      return;
    }

    // Se já houver um agendamento, cancelar para evitar múltiplas chamadas
    if (fetchTimeoutRef.current) {
      clearTimeout(fetchTimeoutRef.current);
    }

    // Debounce de 300ms para evitar tempestade de requisições
    fetchTimeoutRef.current = setTimeout(async () => {
      if (forceRefresh && (!hasInitialized || conversations.length === 0)) {
        setLoading(true);
      }

      try {
        const token = localStorage.getItem('auth_token') || localStorage.getItem('token');
        if (!token) {
          setLoading(false);
          return;
        }

        const params = new URLSearchParams({
          page_size: '200',
          ordering: '-last_message_at',
          include_bot: 'true',
        });

        if (forceRefresh) {
          params.append('_t', new Date().getTime().toString());
        }

        if (provedorId) {
          params.append('provedor_id', provedorId);
        }

        const res = await axios.get(`/api/conversations/?${params.toString()}`, {
          headers: { Authorization: `Token ${token}` }
        });

        if (!isMounted.current) return;

        const conversationsData = res.data.results || res.data || [];

        const closedStatuses = ['closed', 'encerrada', 'resolved', 'finalizada'];
        let activeConversations = conversationsData.filter(conv => {
          const status = conv.status || conv.additional_attributes?.status;
          const isClosed = closedStatuses.includes(status);
          return !isClosed;
        });

        // Usar ref (não closure) — evita limpar seleção após clique durante debounce do fetch
        const selectedNow = selectedConversationRef.current;
        if (selectedNow?.id != null) {
          const selectedId = String(selectedNow.id);
          const selectedStatus = selectedNow.status || selectedNow.additional_attributes?.status;
          const selectedClosed = closedStatuses.includes(selectedStatus);
          const selectedStillExists = activeConversations.some((c) => String(c.id) === selectedId);

          if (selectedClosed) {
            if (onConversationUpdate) onConversationUpdate(null);
            localStorage.removeItem('selectedConversation');
          } else if (!selectedStillExists) {
            // Mantém a conversa aberta mesmo se a página da API não a trouxe (lista grande)
            activeConversations = [selectedNow, ...activeConversations];
          }
        }

        const selectedId = selectedConversationRef.current?.id;
        setConversations(
          selectedId
            ? activeConversations.map((c) =>
                Number(c.id) === Number(selectedId) ? { ...c, unread_count: 0 } : c
              )
            : activeConversations
        );
        setHasInitialized(true);
        setLastUpdateTime(new Date());

      } catch (err) {
        if (isMounted.current) {
          if (err.response?.status === 401) {
            setConversations([]);
          } else if (err.response?.status === 403) {
            setConversations([]);
          } else {
            setConversations([]);
          }
          setHasInitialized(true);
        }
      } finally {
        if (isMounted.current) {
          setLoading(false);
        }
        fetchTimeoutRef.current = null;
        conversationsListFetchedRef.current = true;
      }
    }, 300);
  };

  const mapActiveTabToBulkScope = (tabId) => {
    if (tabId === 'unassigned') return 'waiting';
    return 'automation';
  };

  const buildBulkClosePayload = () => {
    const payload = {
      scope: bulkCloseScope,
    };
    if (provedorId) {
      payload.provedor_id = provedorId;
    }
    const minutes = parseInt(bulkCloseMinutes, 10);
    if (bulkCloseTimeMode === 'more_than' && Number.isFinite(minutes) && minutes >= 0) {
      payload.min_minutes = minutes;
    }
    if (bulkCloseTimeMode === 'less_than' && Number.isFinite(minutes) && minutes >= 0) {
      payload.max_minutes = minutes;
    }
    return payload;
  };

  const openBulkCloseModal = () => {
    setBulkCloseScope(mapActiveTabToBulkScope(activeTab));
    setBulkCloseTimeMode('any');
    setBulkCloseMinutes('10');
    setBulkClosePreviewCount(null);
    setBulkCloseError('');
    setShowBulkCloseModal(true);
  };

  const previewBulkClose = async () => {
    setBulkCloseLoading(true);
    setBulkCloseError('');
    try {
      const token = localStorage.getItem('auth_token') || localStorage.getItem('token');
      const response = await axios.post(
        '/api/conversations/bulk-close-preview/',
        buildBulkClosePayload(),
        { headers: { Authorization: `Token ${token}` } }
      );
      setBulkClosePreviewCount(response.data?.count ?? 0);
    } catch (error) {
      setBulkClosePreviewCount(null);
      setBulkCloseError(error.response?.data?.error || 'Erro ao calcular quantidade.');
    } finally {
      setBulkCloseLoading(false);
    }
  };

  const executeBulkClose = async () => {
    setBulkCloseLoading(true);
    setBulkCloseError('');
    try {
      const token = localStorage.getItem('auth_token') || localStorage.getItem('token');
      const payload = buildBulkClosePayload();
      const previewRes = await axios.post(
        '/api/conversations/bulk-close-preview/',
        payload,
        { headers: { Authorization: `Token ${token}` }, skipErrorToast: true }
      );
      const count = previewRes.data?.count ?? 0;
      setBulkClosePreviewCount(count);
      if (count === 0) {
        setBulkCloseError('Nenhum atendimento corresponde aos filtros.');
        return;
      }
      const confirmed = window.confirm(
        `Encerrar ${count} atendimento(s)? Esta ação não pode ser desfeita.`
      );
      if (!confirmed) return;

      const response = await axios.post(
        '/api/conversations/bulk-close/',
        payload,
        { headers: { Authorization: `Token ${token}` }, skipErrorToast: true }
      );
      const closedIds = new Set((response.data?.ids || []).map(String));
      if (selectedConversation && closedIds.has(String(selectedConversation.id))) {
        onConversationUpdate?.(null);
        localStorage.removeItem('selectedConversation');
      }
      setShowBulkCloseModal(false);
      setBulkClosePreviewCount(null);
      fetchConversations(true);
      toast.success(response.data?.message || `${response.data?.closed || 0} atendimento(s) encerrado(s).`);
    } catch (error) {
      const msg = error.response?.data?.error || 'Erro ao encerrar atendimentos.';
      setBulkCloseError(msg);
      toast.error(msg);
    } finally {
      setBulkCloseLoading(false);
    }
  };

  // Inicialização: Marcar como inicializado quando o usuário estiver disponível
  useEffect(() => {
    if (user) {
      setHasInitialized(true);
    }
  }, [user]);

  // Buscar conversas quando auth estiver pronto
  useEffect(() => {
    if (authReady && isMounted.current && provedorId) {
      // Auth pronto, buscando conversas
      fetchConversations(true);
    }
  }, [authReady, provedorId]);

  // Expor função de recarregamento
  useEffect(() => {
    if (onConversationUpdate && authReady) {
      onConversationUpdate(() => fetchConversations(true));
    }
  }, [onConversationUpdate, authReady]);

  // Eventos do painel via NotificationContext (uma única conexão WS)
  handlePainelWsEventRef.current = (data) => {
    if (!isMounted.current) return;

    try {
      if (data.type === 'conversation_event' &&
        (data.event_type === 'conversation_closed' || data.event_type === 'conversation_ended')) {
        const closedConversationId = data.conversation_id;

        setConversations(prevConversations => {
          const filtered = prevConversations.filter(conv => {
            const status = conv.status || conv.additional_attributes?.status;
            const closedStatuses = ['closed', 'encerrada', 'resolved', 'finalizada', 'closing'];
            return conv.id !== closedConversationId && !closedStatuses.includes(status);
          });
          return filtered;
        });

        if (selectedConversationRef.current?.id === closedConversationId) {
          onConversationUpdateRef.current?.(null);
          localStorage.removeItem('selectedConversation');
        }

        setTimeout(() => fetchConversations(false), 300);
        return;
      }

      if (
        data.type === 'conversation_event'
        && data.event_type === 'conversation_status_changed'
        && data.data?.status === 'closing'
      ) {
        const closingId = data.conversation_id;
        setConversations((prev) =>
          prev.filter((conv) => conv.id !== closingId)
        );
        if (selectedConversationRef.current?.id === closingId) {
          onConversationUpdateRef.current?.(null);
          localStorage.removeItem('selectedConversation');
        }
        return;
      }

      const isConversationEvent = data.type === 'conversation_created' ||
        data.type === 'conversation_updated' ||
        data.type === 'conversation_event';
      const isMessageEvent = data.type === 'new_message' ||
        data.type === 'message_created' ||
        data.type === 'message' ||
        data.type === 'chat_message' ||
        data.type === 'messages' ||
        data.event_type === 'new_message' ||
        data.event_type === 'message_received' ||
        data.event_type === 'message_sent' ||
        data.event_type === 'message' ||
        data.event_type === 'chat_message' ||
        data.event_type === 'messages';

      if (!isConversationEvent && !isMessageEvent) {
        return;
      }

      try {
        if (isMessageEvent || isConversationEvent) {
          startBlinkingFavicon();
        }
      } catch (_) { }

      setNewMessageNotification(true);
      setTimeout(() => setNewMessageNotification(false), 3000);

      const convAtualizada = data.conversation || (data.data && data.data.conversation) || data.payload || data.conversation_data;
      const messagePayload = data.data?.message || data.message || null;
      const eventConversationId = convAtualizada?.id || data.conversation_id || messagePayload?.conversation_id;
      const selectedId = selectedConversationRef.current?.id;
      const fromCustomer = messagePayload?.is_from_customer === true
        || convAtualizada?.last_message?.is_from_customer === true;

      if (eventConversationId && selectedId && Number(eventConversationId) === Number(selectedId) && fromCustomer) {
        const token = localStorage.getItem('auth_token') || localStorage.getItem('token');
        if (token) {
          axios.post(
            `/api/conversations/${eventConversationId}/mark_panel_read/`,
            {},
            { headers: { Authorization: `Token ${token}` } }
          ).catch(() => {});
        }
      }

      if (convAtualizada && convAtualizada.id) {
        setConversations(prev => {
          const previousConversation = prev.find(c => c.id === convAtualizada.id);
          const isSelected = selectedId && Number(convAtualizada.id) === Number(selectedId);
          let unreadCount = previousConversation?.unread_count || 0;
          if (isSelected) {
            unreadCount = 0;
          } else if (isMessageEvent && fromCustomer) {
            unreadCount = unreadCount + 1;
          } else if (typeof convAtualizada.unread_count === 'number') {
            unreadCount = convAtualizada.unread_count;
          }

          const mergedConversation = previousConversation
            ? {
              ...previousConversation,
              ...convAtualizada,
              contact: convAtualizada.contact ?? previousConversation.contact,
              inbox: convAtualizada.inbox ?? previousConversation.inbox,
              assignee: convAtualizada.assignee ?? previousConversation.assignee,
              additional_attributes: {
                ...(previousConversation.additional_attributes || {}),
                ...(convAtualizada.additional_attributes || {}),
              },
              unread_count: unreadCount,
            }
            : { ...convAtualizada, unread_count: unreadCount };
          const listaSemAntiga = prev.filter(c => c.id !== convAtualizada.id);
          const novaLista = [mergedConversation, ...listaSemAntiga];
          return novaLista.sort((a, b) => {
            const timeA = a.last_message?.created_at || a.updated_at || a.created_at || 0;
            const timeB = b.last_message?.created_at || b.updated_at || b.created_at || 0;
            return new Date(timeB) - new Date(timeA);
          });
        });

        onConversationUpdateRef.current?.(convAtualizada);
      } else if (isConversationEvent) {
        if (fetchTimeoutRef.current) {
          clearTimeout(fetchTimeoutRef.current);
        }
        fetchTimeoutRef.current = setTimeout(() => {
          if (isMounted.current) {
            fetchConversations(false);
            fetchTimeoutRef.current = null;
          }
        }, 400);
      }
    } catch (_) {
      /* silencioso */
    }
  };

  useEffect(() => {
    if (!provedorId || !authReady) {
      return undefined;
    }

    const listener = (data) => {
      handlePainelWsEventRef.current?.(data);
    };

    return subscribePainelEvents(listener);
  }, [provedorId, authReady, subscribePainelEvents]);

  // Parar piscar quando a aba ficar visível
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

  // Atualiza o texto "Há X min" a cada minuto
  useEffect(() => {
    const id = setInterval(() => setElapsedTick((n) => n + 1), 60000);
    return () => clearInterval(id);
  }, []);

  // Conversas são atualizadas via WebSocket do painel (tempo real)
  // Não é necessário polling - o WebSocket já envia conversation_event quando há mudanças

  const hasHumanAssignee = hasHumanAssigneeShared;
  const getConversationStatus = getConversationStatusShared;
  const isClosedStatus = (status) =>
    ['closed', 'encerrada', 'resolved', 'finalizada', 'closing'].includes(status);
  const isWaitingConversation = isWaitingConversationShared;
  const isAutomationConversation = isAutomationConversationShared;

  /** Atendimento humano em curso (com atendente atribuído). Visível na aba Em andamento (admin). */
  const isInProgressConversation = (conversation) => {
    if (isClosedConversationShared(conversation)) return false;
    return hasHumanAssignee(conversation);
  };

  const getAssigneeDisplayName = (conversation) => {
    const a = conversation?.assignee;
    if (!a) return 'Sem atendente';
    const full = [a.first_name, a.last_name].filter(Boolean).join(' ').trim();
    return full || a.first_name || a.username || a.email || 'Atendente';
  };

  const formatConversationElapsed = (conversation) => {
    // Tempo desde a atribuição (quando o contato entrou no atendimento).
    // Sem assigned_at (legado / fila): usa criação da conversa.
    const ref =
      conversation?.additional_attributes?.assigned_at ||
      conversation?.created_at;
    if (!ref) return '';
    const agora = new Date();
    const inicio = new Date(ref);
    const diffMs = agora - inicio;
    if (Number.isNaN(diffMs)) return '';
    const diffMinutos = Math.floor(diffMs / (1000 * 60));
    const diffHoras = Math.floor(diffMinutos / 60);
    const diffDias = Math.floor(diffHoras / 24);

    if (diffDias > 0) {
      return `${diffDias} dia${diffDias > 1 ? 's' : ''}`;
    }
    if (diffHoras > 0) {
      return `${diffHoras}h ${diffMinutos % 60}min`;
    }
    return `${Math.max(diffMinutos, 0)} min`;
  };

  /** Remove assinatura do atendente no preview da lista (*Nome disse:* / *Nome*). */
  const stripAgentSignaturePreview = (content) => {
    if (!content || typeof content !== 'string') return content || '';
    let match = content.match(/^\s*\*([^*\n]+?)\s+disse:\*\s*\n*([\s\S]*)$/i);
    if (match) return (match[2] || '').trim() || content;
    match = content.match(/^\s*\*\*([^*\n]+)\*\*\s*\n+([\s\S]*)$/);
    if (match) return (match[2] || '').trim() || content;
    match = content.match(/^\s*\*([^*\n]+)\*\s*\n+([\s\S]*)$/);
    if (match && !/disse/i.test(match[1])) return (match[2] || '').trim() || content;
    return content.trim();
  };

  const isVisibleInWaitingTab = (conversation) => {
    if (hasHumanAssignee(conversation)) return false;

    const assignedUser = conversation.additional_attributes?.assigned_user;
    const attrsTeam = conversation.additional_attributes?.assigned_team;
    const convTeam = conversation.team;
    // Destino de equipe pode estar só em additional_attributes (transferência) ou só em team (ex.: chatbot).
    const assignedTeam =
      attrsTeam?.id != null
        ? attrsTeam
        : convTeam?.id != null
          ? { id: convTeam.id, name: convTeam.name }
          : null;
    const currentUserId = user?.id != null ? String(user.id) : null;

    // Se há destino explícito de transferência, só mostra para o destinatário.
    if (assignedUser?.id != null) {
      return currentUserId != null && String(assignedUser.id) === currentUserId;
    }
    if (assignedTeam?.id != null) {
      // Admins do provedor veem todas as filas por equipe (evita cegueira quando o user não tem TeamMember).
      if (isProviderAdmin) {
        return isWaitingConversation(conversation);
      }
      return userTeamIds.size > 0 && userTeamIds.has(String(assignedTeam.id));
    }

    // Fila geral (sem destino específico) continua visível na aba Espera.
    return isWaitingConversation(conversation);
  };

  // Definir abas baseado nas permissões
  const getAvailableTabs = () => {
    const activeConversations = conversations.filter(c => {
      const status = getConversationStatus(c);
      return !isClosedStatus(status);
    });

    const tabs = [];

    // Abas padrão - Minhas sempre primeiro
    tabs.push({
      id: 'mine',
      label: 'Atendimento',
      count: activeConversations.filter(c => {
        const a = c.assignee;
        if (!a || !user) return false;
        return (a.id?.toString() === user.id?.toString()) || (a.username && a.username === user.username);
      }).length,
    });

    // Aba Não atribuídas - fila de espera + transferências sem atendente
    tabs.push({
      id: 'unassigned',
      label: 'Espera',
      count: activeConversations.filter(c => isVisibleInWaitingTab(c)).length,
    });

    if (isProviderAdmin) {
      tabs.push({
        id: 'in_progress',
        label: 'Em andamento',
        count: activeConversations.filter(c => isInProgressConversation(c)).length,
      });
    }

    const canViewAutomationConversations =
      isProviderAdmin ||
      userPermissions.includes('view_ai_conversations') ||
      userPermissions.includes('view_chatbot_conversations');

    // Aba Automação / Com a IA para admin do provedor (ou com permissão explícita).
    if (canViewAutomationConversations) {
      tabs.push({
        id: 'automation',
        label: automationTabLabel,
        count: activeConversations.filter(c => {
          return isAutomationConversation(c);
        }).length,
      });
    }

    return tabs;
  };

  const tabs = getAvailableTabs();

  useEffect(() => {
    // Evita ficar preso em uma aba indisponível para o perfil atual.
    if (!tabs.some(tab => tab.id === activeTab)) {
      setActiveTab('mine');
    }
  }, [tabs, activeTab]);

  useEffect(() => {
    onActiveTabChange?.(activeTab);
  }, [activeTab, onActiveTabChange]);

  // Conversas visíveis na aba atual (sem busca) — usado para alinhar o painel do chat com a lista
  const tabFilteredConversations = useMemo(() => {
    let filtered = conversations.filter(c => {
      const status = getConversationStatus(c);
      return !isClosedStatus(status);
    });

    if (activeTab === 'automation') {
      filtered = filtered.filter(c => isAutomationConversation(c));
    } else if (activeTab === 'mine') {
      filtered = filtered.filter(c => {
        const a = c.assignee;
        if (!a || !user) return false;
        return (a.id?.toString() === user.id?.toString()) || (a.username && a.username === user.username);
      });
    } else if (activeTab === 'unassigned') {
      filtered = filtered.filter(c => isVisibleInWaitingTab(c));
    } else if (activeTab === 'in_progress') {
      filtered = filtered.filter(c => isInProgressConversation(c));
    }

    return filtered;
  }, [conversations, activeTab, user, userTeamIds, isProviderAdmin]);

  // Filtrar conversas baseado na aba ativa e termo de busca
  const filteredConversations = useMemo(() => {
    let filtered = tabFilteredConversations;

    if (searchTerm && searchTerm.trim().length >= 2) {
      const searchLower = searchTerm.toLowerCase();
      filtered = filtered.filter(c => {
        const contactName = c.contact?.name || '';
        const lastMessage = c.last_message?.content || '';
        const phone = c.contact?.phone || '';

        return contactName.toLowerCase().includes(searchLower) ||
          lastMessage.toLowerCase().includes(searchLower) ||
          phone.includes(searchTerm);
      });
    }

    return filtered;
  }, [tabFilteredConversations, searchTerm]);

  // Só limpa a seleção quando o USUÁRIO muda de aba e a conversa não pertence à nova aba.
  // NÃO limpar em refresh/WS — isso fechava o ChatArea com muitos atendimentos.
  const prevActiveTabRef = useRef(activeTab);
  useEffect(() => {
    const tabChanged = prevActiveTabRef.current !== activeTab;
    prevActiveTabRef.current = activeTab;
    if (!tabChanged || !conversationsListFetchedRef.current || !selectedConversation?.id) return;
    const sid = String(selectedConversation.id);
    const stillInActiveTab = tabFilteredConversations.some((c) => String(c.id) === sid);
    if (!stillInActiveTab) {
      onConversationUpdate?.(null);
    }
  }, [activeTab, tabFilteredConversations, selectedConversation?.id, onConversationUpdate]);

  return (
    <div
      className={`${isProviderAdmin ? 'w-[300px] min-w-[300px]' : 'w-[240px] min-w-[240px]'} flex-shrink-0 border-r border-border bg-background flex flex-col h-full`}
    >
      <style>{`
        .conversation-list::-webkit-scrollbar {
          width: 6px;
          background: transparent;
        }
        .conversation-list::-webkit-scrollbar-track {
          background: transparent;
        }
        .conversation-list::-webkit-scrollbar-thumb {
          background: #4a5568;
          border-radius: 3px;
          border: none;
        }
        .conversation-list::-webkit-scrollbar-thumb:hover {
          background: #2d3748;
        }
        .conversation-list {
          scrollbar-width: thin;
          scrollbar-color: #4a5568 transparent;
        }
      `}</style>
      {/* Header */}
      <div className="p-3 border-b border-border">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-lg font-semibold text-zinc-100">Conversas</h2>
          <div className="flex items-center space-x-2">
            {/* Botão de ativar sons removido */}



            <button
              onClick={() => fetchConversations(true)}
              className="text-muted-foreground hover:text-primary p-1"
              title="Atualizar conversas"
            >
            </button>
            {canBulkClose && (
              <button
                type="button"
                onClick={openBulkCloseModal}
                className="text-muted-foreground hover:text-amber-500 p-1 transition-colors"
                title="Encerrar atendimentos em lote"
              >
                <Archive size={20} />
              </button>
            )}
            <div className="relative">
              <button
                onClick={(e) => {
                  e.preventDefault();
                  e.stopPropagation();
                  // Log removido(' Clicou nos 3 pontinhos da página Atendimento');
                  setShowMenuAtendimento(!showMenuAtendimento);
                }}
                className="text-muted-foreground hover:text-primary p-1 transition-colors"
                title="Novo atendimento"
              >
                <UserPlus size={20} />
              </button>

              {/* Menu de opções */}
              {showMenuAtendimento && (
                <div className="absolute right-0 top-full mt-1 w-48 bg-card border border-border rounded-lg shadow-lg py-1 z-50">
                  <button
                    onClick={(e) => {
                      e.stopPropagation();
                      setShowMenuAtendimento(false);
                      setModalNovoContato(true);
                    }}
                    className="conversation-action-item w-full text-left px-3 py-2 text-sm hover:bg-accent flex items-center space-x-2"
                  >
                    <User className="conversation-action-icon w-4 h-4" />
                    <span className="conversation-action-name">Novo Contato</span>
                  </button>
                  <button
                    onClick={(e) => {
                      e.stopPropagation();
                      setShowMenuAtendimento(false);
                      setModalContatoExistente(true);
                    }}
                    className="conversation-action-item w-full text-left px-3 py-2 text-sm hover:bg-accent flex items-center space-x-2"
                  >
                    <Search className="conversation-action-icon w-4 h-4" />
                    <span className="conversation-action-name">Contato Existente</span>
                  </button>
                </div>
              )}
            </div>
          </div>
        </div>

        {/* Search */}
        <div className="relative mb-4">
          <Search size={16} className="absolute left-3 top-1/2 transform -translate-y-1/2 text-muted-foreground" />
          <input
            type="text"
            placeholder="Pesquisar mensagens em conversas"
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
            className="niochat-input pl-8 w-full text-sm"
          />
          {searchTerm && (
            <button
              className="absolute right-2 top-1/2 -translate-y-1/2 text-xs text-muted-foreground hover:text-primary"
              onClick={() => setSearchTerm('')}
            >
              Limpar
            </button>
          )}
        </div>

        {/* Tabs — grade 2 colunas compacta; rótulos sem truncar */}
        <div className="grid grid-cols-2 gap-1 rounded-xl bg-[#2f3238] p-1">
          {tabs.map((tab) => {
            const isActive = activeTab === tab.id;
            let activeClass = 'bg-[#2ca7ff] text-white shadow-sm';

            if (isActive) {
              if (tab.id === 'mine') {
                activeClass = 'bg-[#2ca7ff] text-white shadow-md';
              } else if (tab.id === 'unassigned') {
                activeClass = 'bg-[#2ca7ff] text-white shadow-md';
              } else if (tab.id === 'automation') {
                activeClass = 'bg-[#2ca7ff] text-white shadow-md';
              } else if (tab.id === 'in_progress') {
                activeClass = 'bg-[#1bc47d] text-white shadow-md';
              } else if (tab.id === 'all') {
                activeClass = 'bg-[#2ca7ff] text-white shadow-md';
              }
            }

            return (
              <button
                key={tab.id}
                type="button"
                onClick={() => setActiveTab(tab.id)}
                className={`relative w-full px-1.5 py-1.5 text-[11px] font-medium rounded-md transition-all duration-200 ${
                  isActive
                  ? activeClass
                  : 'text-white/90 hover:text-white hover:bg-white/10'
                  }`}
              >
                <span className="flex items-center justify-center gap-1">
                  <span className="whitespace-nowrap">{tab.label}</span>
                  {tab.count > 0 && (
                    <span
                      className={`shrink-0 min-w-[14px] h-3.5 px-0.5 rounded-full text-[9px] leading-[14px] font-bold text-white text-center ${
                        isActive ? 'bg-[#ef4444]' : 'bg-[#ef4444]/90'
                      }`}
                    >
                      {tab.count > 9 ? '9+' : tab.count}
                    </span>
                  )}
                </span>
              </button>
            );
          })}
        </div>
      </div>

      {/* Conversation List */}
      <div
        className={`flex-1 conversation-list ${filteredConversations.length > 3 ? 'overflow-y-auto' : 'overflow-hidden'
          }`}
        style={filteredConversations.length > 3 ? {
          maxHeight: '450px' // Altura para mostrar aproximadamente 3 conversas (~150px cada com padding e bordas)
        } : {}}
      >
        {!authReady ? (
          <div className="p-3 text-center text-muted-foreground">
            {!hasInitialized ? (
              <div className="flex items-center justify-center space-x-2">
                <div className="w-4 h-4 border-2 border-primary border-t-transparent rounded-full animate-spin"></div>
                <span>Verificando autenticação...</span>
              </div>
            ) : (
              <div>
                <div className="mb-3">
                  <svg className="w-12 h-12 mx-auto text-muted-foreground mb-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z" />
                  </svg>
                  <h3 className="text-lg font-medium mb-2">Acesso Restrito</h3>
                  <p className="text-sm mb-4">Você precisa estar logado para acessar as conversas.</p>
                </div>
                <button
                  onClick={() => window.location.href = '/admin/login/'}
                  className="px-4 py-2 bg-primary text-primary-foreground rounded hover:bg-primary/90 transition-colors"
                >
                  Fazer Login
                </button>
                <p className="text-xs mt-2 text-muted-foreground">
                  Ou acesse o painel administrativo para autenticação
                </p>
              </div>
            )}
          </div>
        ) : !hasInitialized ? (
          <div className="p-3 text-center text-muted-foreground">
            <div className="flex items-center justify-center space-x-2">
              <div className="w-4 h-4 border-2 border-primary border-t-transparent rounded-full animate-spin"></div>
              <span>Carregando...</span>
            </div>
            <p className="text-xs mt-2">Buscando conversas...</p>
          </div>
        ) : filteredConversations.length === 0 ? (
          <div className="p-6 text-center">
            {activeTab === 'mine' ? (
              <div className="py-8 flex flex-col items-center">
                <h3 className="text-lg font-semibold text-foreground mb-2">
                  Nenhum atendimento ativo
                </h3>
                <p className="text-sm text-muted-foreground leading-relaxed">
                  As conversas atribuídas para você aparecerão aqui.
                </p>
              </div>
            ) : activeTab === 'in_progress' ? (
              <div className="py-8 flex flex-col items-center px-2">
                <h3 className="text-sm font-semibold text-foreground mb-2">
                  Nenhum atendimento em andamento
                </h3>
                <p className="text-xs text-muted-foreground leading-relaxed">
                  Clique em uma conversa para acompanhar o chat completo em tempo real com o cliente.
                </p>
              </div>
            ) : (
              <div className="py-4">
                <p className="text-sm text-muted-foreground">
                  Nenhuma conversa na aba "{tabs.find(t => t.id === activeTab)?.label}"
                </p>
              </div>
            )}
          </div>
        ) : (
          filteredConversations.map((conversation) => {
            const status = conversation.status || conversation.additional_attributes?.status;
            let statusBorder = '';
            const isSelected = selectedConversation?.id === conversation.id;
            const unreadCount = isSelected ? 0 : (Number(conversation.unread_count) || 0);
            const hasUnread = unreadCount > 0;

            if (status === 'snoozed') {
              statusBorder = 'status-border-ia'; // IA
            } else if (status === 'pending') {
              statusBorder = 'status-border-espera'; // Espera
            } else if (status === 'open' || !status) {
              statusBorder = 'status-border-atendimento'; // Atendimento
            }

            return (
              <div
                key={conversation.id}
                onClick={() => {
                  setConversations((prev) =>
                    prev.map((c) =>
                      c.id === conversation.id ? { ...c, unread_count: 0 } : c
                    )
                  );
                  const token = localStorage.getItem('auth_token') || localStorage.getItem('token');
                  if (token && conversation.id) {
                    axios.post(
                      `/api/conversations/${conversation.id}/mark_panel_read/`,
                      {},
                      { headers: { Authorization: `Token ${token}` } }
                    ).catch(() => {});
                  }
                  onConversationSelect({ ...conversation, unread_count: 0 });
                }}
                className={`p-2 border-b border-border border-l-2 cursor-pointer transition-all duration-200 hover:bg-accent/50 ${statusBorder} ${isSelected ? 'bg-topbar text-topbar-foreground shadow-inner' : ''
                  }`}
              >
                <div className="flex items-start space-x-2">
                  <div className="flex-shrink-0 w-8">
                    <div className={`w-8 h-8 rounded-full flex items-center justify-center overflow-hidden ${isSelected ? 'bg-white/20' : 'bg-primary/10'}`}>
                      {conversation.contact?.avatar ? (
                        <img
                          src={conversation.contact.avatar}
                          alt={conversation.contact.name}
                          className="w-full h-full object-cover"
                        />
                      ) : (
                        <User size={20} className={isSelected ? 'text-white' : 'text-primary'} />
                      )}
                    </div>
                  </div>

                  <div className="flex-1 min-w-0">
                    <div className="flex items-center justify-between">
                      <h3 className={`text-sm truncate ${isSelected ? 'text-topbar-foreground' : 'text-primary'} ${hasUnread ? 'font-bold' : 'font-medium'}`}>
                        {conversation.contact?.name || 'Contato sem nome'}
                      </h3>
                      <span className={`text-xs ${isSelected ? 'text-topbar-foreground/70' : hasUnread ? 'text-primary font-semibold' : 'text-muted-foreground'}`}>
                        {!conversation.last_message?.panel_waiting_content_hidden && conversation.last_message?.created_at
                          ? new Date(conversation.last_message.created_at).toLocaleTimeString('pt-BR', {
                            hour: '2-digit',
                            minute: '2-digit'
                          })
                          : ''}
                      </span>
                    </div>

                    {activeTab === 'in_progress' ? (
                      <p
                        className={`text-[11px] truncate mt-1 flex items-center gap-1 ${isSelected ? 'text-topbar-foreground/90' : 'text-emerald-400'}`}
                        title={`Atendente: ${getAssigneeDisplayName(conversation)}`}
                      >
                        <UserCheck size={12} className="shrink-0" />
                        <span className="truncate">
                          {getAssigneeDisplayName(conversation)}
                        </span>
                      </p>
                    ) : null}

                    <p className={`text-sm truncate ${activeTab === 'in_progress' ? 'mt-0.5' : 'mt-1'} ${isSelected ? 'text-topbar-foreground/80' : hasUnread ? 'text-foreground font-medium' : 'text-muted-foreground'}`}>
                      {(() => {
                        const msg = conversation.last_message;
                        if (!msg) return 'Nenhuma mensagem';
                        if (msg.panel_waiting_content_hidden) {
                          return 'Conteúdo oculto até atribuir o atendimento';
                        }

                        // PRIORIDADE: Mostrar o tipo de mídia na barra lateral sempre que for uma mídia
                        // (Mesmo que tenha legenda, o usuário quer ver o tipo aqui)
                        const type = msg.message_type;
                        const labels = {
                          'image': 'Você recebeu uma imagem',
                          'video': 'Você recebeu um vídeo',
                          'audio': 'Você recebeu um áudio',
                          'document': 'Você recebeu um documento',
                          'voice': 'Você recebeu uma mensagem de voz',
                          'location': '📍 Localização',
                        };
                        
                        if (labels[type]) return labels[type];

                        // Fallback: texto legado com coordenadas da IA
                        if (typeof msg.content === 'string' && /latitude\s*=/i.test(msg.content) && /longitude\s*=/i.test(msg.content)) {
                          return '📍 Localização';
                        }

                        // Fallback para mensagens interativas se o conteúdo for vazio
                        if (!msg.content || msg.content === '...') {
                          const attrs = msg.additional_attributes;
                          if (attrs?.interactive_rows?.length > 0) return '📋 Menu de Opções';
                          if (attrs?.interactive_buttons?.length > 0) return '🔘 Botões Interativos';
                        }

                        return stripAgentSignaturePreview(msg.content) || 'Nenhuma mensagem';
                      })()}
                    </p>

                  </div>
                </div>

                <div className="mt-2 flex items-center justify-between gap-2">
                  <span
                    className={`inline-flex items-center gap-1 rounded px-1.5 py-0.5 text-[10px] tabular-nums tracking-tight ${
                      isSelected
                        ? 'text-topbar-foreground/75'
                        : hasUnread
                          ? 'text-primary/90'
                          : 'text-muted-foreground'
                    }`}
                    title="Tempo desde a atribuição do atendimento"
                    data-elapsed-tick={elapsedTick}
                  >
                    <Clock size={10} className="shrink-0 opacity-70" />
                    Há {formatConversationElapsed(conversation)}
                  </span>
                  {hasUnread && (
                    <span
                      className="inline-flex h-[18px] min-w-[18px] items-center justify-center rounded-full bg-primary px-1 text-[10px] font-semibold leading-none text-primary-foreground"
                      title={`${unreadCount} mensagem${unreadCount > 1 ? 'ns' : ''} nova${unreadCount > 1 ? 's' : ''}`}
                    >
                      {unreadCount > 9 ? '9+' : unreadCount}
                    </span>
                  )}
                </div>
              </div>
            );
          })
        )}
      </div>

      {/* Modal de novo contato */}
      <Dialog open={modalNovoContato} onOpenChange={setModalNovoContato}>
        <DialogContent className="dark max-w-[min(100vw-2rem,44rem)] w-full min-w-0 gap-0 p-0 overflow-hidden">
          <DialogHeader className="px-5 pt-5 pb-3 border-b border-white/10 pr-12">
            <DialogTitle className="text-base font-semibold truncate">Novo contato</DialogTitle>
          </DialogHeader>
          <div className="px-5 py-4">
            <div
              className={
                novoContato.usarTemplate &&
                (novoContato.canal === 'whatsapp' || novoContato.canal === 'whatsapp_oficial')
                  ? 'grid grid-cols-1 items-start gap-4 sm:grid-cols-[minmax(0,1fr)_260px]'
                  : ''
              }
            >
              <div className="min-w-0 space-y-3 overflow-x-hidden">
            <div className="grid min-w-0 grid-cols-1 gap-3 sm:grid-cols-2">
              <div className="min-w-0">
                <label className="mb-1.5 block text-xs font-medium text-white/70">Nome</label>
                <input
                  type="text"
                  value={novoContato.nome}
                  onChange={(e) => setNovoContato((prev) => ({ ...prev, nome: e.target.value }))}
                  placeholder="Nome do contato"
                  className="w-full min-w-0 max-w-full rounded-lg border border-white/10 bg-white/5 px-3 py-2 text-sm text-white placeholder:text-white/35 focus:outline-none focus:ring-1 focus:ring-white/20"
                />
              </div>
              <div className="min-w-0">
                <label className="mb-1.5 block text-xs font-medium text-white/70">Telefone (com DDI)</label>
                <input
                  type="text"
                  value={novoContato.telefone}
                  onChange={(e) => setNovoContato((prev) => ({ ...prev, telefone: e.target.value }))}
                  placeholder="DDI + número"
                  className="w-full min-w-0 max-w-full rounded-lg border border-white/10 bg-white/5 px-3 py-2 text-sm text-white placeholder:text-white/35 focus:outline-none focus:ring-1 focus:ring-white/20"
                />
              </div>
            </div>

            {novoContato.nome.trim() && novoContato.telefone.trim() && (
              <div
                className="flex min-w-0 items-center gap-2.5 overflow-hidden rounded-lg border px-2.5 py-2"
                style={{ backgroundColor: '#1f1712', borderColor: '#5a3d22' }}
              >
                <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-[#EA580C]/25 text-xs font-semibold text-[#FDBA74]">
                  {novoContato.nome.trim().charAt(0).toUpperCase()}
                </div>
                <div className="min-w-0 flex-1 overflow-hidden">
                  <p className="truncate text-sm font-medium leading-tight text-white" title={novoContato.nome.trim()}>{novoContato.nome.trim()}</p>
                  <p className="truncate text-xs text-white/50" title={novoContato.telefone.trim()}>{novoContato.telefone.trim()}</p>
                </div>
                <UserPlus className="h-4 w-4 shrink-0 text-[#EA580C]/80" aria-hidden />
              </div>
            )}

            {inboxes.length > 0 && (
              <div className="min-w-0">
                <label className="mb-1.5 block text-xs font-medium text-white/70">Canal de envio</label>
                <select
                  value={novoContato.inboxId || ''}
                  onChange={(e) => {
                    const selectedInboxId = e.target.value;
                    const selectedInbox = inboxes.find((i) => i.id.toString() === selectedInboxId.toString());
                    const channel_id_value = selectedInbox?.channel_id || null;
                    setNovoContato((prev) => ({
                      ...prev,
                      inboxId: selectedInboxId,
                      canal: selectedInbox?.channel_type || prev.canal,
                      canal_id: channel_id_value,
                    }));
                    if (selectedInbox?.channel_type === 'whatsapp_oficial' && channel_id_value) {
                      buscarTemplates(channel_id_value);
                    }
                  }}
                  className={MODAL_SELECT_CLASS}
                >
                  <option value="" className={MODAL_OPTION_CLASS}>Selecione a conexão</option>
                  {inboxes.map((inbox) => (
                    <option key={inbox.id} value={inbox.id} className={MODAL_OPTION_CLASS}>
                      {(inbox.custom_name || inbox.name)} ({inbox.channel_type === 'whatsapp_oficial' ? 'WhatsApp' : inbox.channel_type}){' '}
                      {inbox.additional_attributes?.phone_number ? `(${inbox.additional_attributes.phone_number})` : ''}
                    </option>
                  ))}
                </select>
              </div>
            )}

            {(novoContato.canal === 'whatsapp' || novoContato.canal === 'whatsapp_oficial') && (
              <label className="flex cursor-pointer items-start gap-2 rounded-lg border border-white/5 bg-white/[0.02] px-2.5 py-2">
                <input
                  type="checkbox"
                  checked={novoContato.usarTemplate}
                  onChange={(e) => setNovoContato((prev) => ({
                    ...prev,
                    usarTemplate: e.target.checked,
                    templateSelecionado: e.target.checked ? prev.templateSelecionado : null,
                    mensagem: e.target.checked ? '' : prev.mensagem,
                  }))}
                  className="mt-0.5 h-3.5 w-3.5 shrink-0 accent-[#16A34A]"
                />
                <span className="text-xs leading-snug text-white/80">
                  Usar template (reabrir conversa após 24h)
                </span>
              </label>
            )}

            {novoContato.usarTemplate && (novoContato.canal === 'whatsapp' || novoContato.canal === 'whatsapp_oficial') ? (
              <div>
                <label className="mb-1.5 block text-xs font-medium text-white/70">Template</label>
                <TemplateSelectWithPreview
                  templates={templates}
                  value={novoContato.templateSelecionado || ''}
                  onChange={(name) =>
                    setNovoContato((prev) => ({ ...prev, templateSelecionado: name || null }))
                  }
                  loading={carregandoTemplates}
                  showPreview={false}
                  emptyMessage="Nenhum template aprovado. Crie em Configurações → Integrações → WhatsApp Oficial"
                />
              </div>
            ) : (
              <div>
                <label className="mb-1.5 block text-xs font-medium text-white/70">Mensagem</label>
                <textarea
                  value={novoContato.mensagem}
                  onChange={(e) => setNovoContato((prev) => ({ ...prev, mensagem: e.target.value }))}
                  placeholder="Digite a mensagem..."
                  rows={2}
                  className="w-full resize-none rounded-lg border border-white/10 bg-white/5 px-3 py-2 text-sm text-white placeholder:text-white/35 focus:outline-none focus:ring-1 focus:ring-white/20"
                />
              </div>
            )}

              </div>

              {novoContato.usarTemplate &&
                (novoContato.canal === 'whatsapp' || novoContato.canal === 'whatsapp_oficial') && (
                <aside className="min-w-0 sm:sticky sm:top-0">
                  <p className="mb-1.5 text-xs font-medium text-white/70">Prévia WhatsApp</p>
                  {findTemplateByName(templates, novoContato.templateSelecionado || '') ? (
                    <TemplateMessagePreview
                      template={findTemplateByName(templates, novoContato.templateSelecionado || '')}
                      compact
                    />
                  ) : (
                    <p className="rounded-md border border-dashed border-white/15 bg-[#d8d1ca]/10 px-2 py-6 text-center text-[10px] text-white/45">
                      Selecione um template
                    </p>
                  )}
                </aside>
              )}
            </div>

            <div className="mt-3 flex items-center justify-end gap-2 border-t border-white/10 pt-3">
              <button
                type="button"
                onClick={() => setModalNovoContato(false)}
                className="px-3 py-1.5 text-sm text-white/60 transition-colors hover:text-white"
                disabled={enviandoAtendimento}
              >
                Cancelar
              </button>
              <button
                type="button"
                onClick={handleNovoContato}
                disabled={enviandoAtendimento}
                className="rounded-lg bg-[#16A34A] px-4 py-1.5 text-sm font-medium text-white shadow-sm transition-colors hover:bg-[#15803D] disabled:opacity-50"
              >
                {enviandoAtendimento
                  ? 'Enviando...'
                  : novoContato.usarTemplate
                    ? 'Enviar template'
                    : 'Enviar'}
              </button>
            </div>
          </div>
        </DialogContent>
      </Dialog>

      {/*  Modal de contato existente */}
      <Dialog open={modalContatoExistente} onOpenChange={setModalContatoExistente}>
        <DialogContent className="dark max-w-[min(100vw-2rem,44rem)] w-full min-w-0 gap-0 p-0 overflow-hidden">
          <DialogHeader className="px-5 pt-5 pb-3 border-b border-white/10 pr-12">
            <DialogTitle className="text-base font-semibold truncate">Iniciar atendimento</DialogTitle>
          </DialogHeader>
          <div className="px-5 py-4">
            <div
              className={
                contatoExistente.usarTemplate
                  ? 'grid grid-cols-1 items-start gap-4 sm:grid-cols-[minmax(0,1fr)_260px]'
                  : ''
              }
            >
              <div className="min-w-0 space-y-3 overflow-x-hidden">
            {!contatoExistente.contato && (
            <div className="min-w-0">
              <label className="mb-1.5 block text-xs font-medium text-white/70">Buscar contato</label>
              <div className="relative min-w-0">
                <Search className="pointer-events-none absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-white/40" />
                <input
                  type="text"
                  value={contatoExistente.busca}
                  onChange={(e) => {
                    setContatoExistente(prev => ({ ...prev, busca: e.target.value }));
                    buscarContatos(e.target.value);
                  }}
                  placeholder="Nome ou telefone"
                  className="w-full min-w-0 max-w-full rounded-lg border border-white/10 bg-white/5 py-2 pl-8 pr-3 text-sm text-white placeholder:text-white/35 focus:outline-none focus:ring-1 focus:ring-white/20"
                />
              </div>
            </div>
            )}

            {contatosEncontrados.length > 0 && !contatoExistente.contato && (
              <div className="max-h-28 min-w-0 overflow-y-auto overflow-x-hidden rounded-lg border border-white/10 bg-black/20">
                {contatosEncontrados.map((contato) => (
                  <button
                    key={contato.id}
                    type="button"
                    onClick={() => {
                      setContatoExistente((prev) => ({ ...prev, contato, busca: '' }));
                      setContatosEncontrados([]);
                    }}
                    className="flex w-full min-w-0 flex-col overflow-hidden border-b border-white/5 px-2.5 py-2 text-left last:border-b-0 transition-colors hover:bg-white/5"
                  >
                    <span className="block truncate text-sm font-medium text-white" title={contato.name}>{contato.name}</span>
                    <span className="block truncate text-xs text-white/45" title={contato.phone}>{contato.phone}</span>
                  </button>
                ))}
              </div>
            )}

            {contatoExistente.contato && (
              <div
                className="flex min-w-0 items-center gap-2.5 overflow-hidden rounded-lg border px-2.5 py-2"
                style={{ backgroundColor: '#0F2918', borderColor: '#1B5E36' }}
              >
                <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-[#16A34A]/25 text-xs font-semibold text-[#86EFAC]">
                  {(contatoExistente.contato.name || '?').charAt(0).toUpperCase()}
                </div>
                <div className="min-w-0 flex-1 overflow-hidden">
                  <p className="truncate text-sm font-medium leading-tight text-white" title={contatoExistente.contato.name}>
                    {contatoExistente.contato.name}
                  </p>
                  <p className="truncate text-xs text-white/50" title={contatoExistente.contato.phone}>{contatoExistente.contato.phone}</p>
                </div>
                <button
                  type="button"
                  onClick={() => setContatoExistente((prev) => ({ ...prev, contato: null, busca: '' }))}
                  className="shrink-0 rounded p-1 text-white/40 transition-colors hover:bg-white/10 hover:text-white/80"
                  title="Trocar contato"
                >
                  <X className="h-3.5 w-3.5" />
                </button>
              </div>
            )}

            {inboxes.length > 0 && (
              <div className="min-w-0">
                <label className="mb-1.5 block text-xs font-medium text-white/70">Canal de envio</label>
                <select
                  value={contatoExistente.inboxId || ''}
                  onChange={(e) => {
                    const selectedInboxId = e.target.value;
                    const selectedInbox = inboxes.find(i => i.id.toString() === selectedInboxId.toString());
                    const channel_id_value = selectedInbox?.channel_id || null;
                    setContatoExistente(prev => ({
                      ...prev,
                      inboxId: selectedInboxId,
                      canal: selectedInbox?.channel_type || prev.canal,
                      canal_id: channel_id_value
                    }));
                    // Se inbox de whatsapp_oficial, buscar templates pelo ID do canal
                    if (selectedInbox?.channel_type === 'whatsapp_oficial' && channel_id_value) {
                      buscarTemplates(channel_id_value);
                    }
                  }}
                  className={MODAL_SELECT_CLASS}
                >
                  <option value="" className={MODAL_OPTION_CLASS}>Selecione a conexão</option>
                  {inboxes.map(inbox => (
                    <option key={inbox.id} value={inbox.id} className={MODAL_OPTION_CLASS}>
                      {(inbox.custom_name || inbox.name)} ({inbox.channel_type === 'whatsapp_oficial' ? 'WhatsApp' : inbox.channel_type}) {inbox.additional_attributes?.phone_number ? `(${inbox.additional_attributes.phone_number})` : ''}
                    </option>
                  ))}
                </select>
              </div>
            )}

            <label className="flex cursor-pointer items-start gap-2 rounded-lg border border-white/5 bg-white/[0.02] px-2.5 py-2">
              <input
                type="checkbox"
                checked={contatoExistente.usarTemplate}
                onChange={(e) => setContatoExistente(prev => ({
                  ...prev,
                  usarTemplate: e.target.checked,
                  templateSelecionado: e.target.checked ? prev.templateSelecionado : null,
                  mensagem: e.target.checked ? '' : prev.mensagem
                }))}
                className="mt-0.5 h-3.5 w-3.5 shrink-0 accent-[#16A34A]"
              />
              <span className="text-xs leading-snug text-white/80">
                Usar template (reabrir conversa após 24h)
              </span>
            </label>

            {contatoExistente.usarTemplate ? (
              <div>
                <label className="mb-1.5 block text-xs font-medium text-white/70">Template</label>
                <TemplateSelectWithPreview
                  templates={templates}
                  value={contatoExistente.templateSelecionado || ''}
                  onChange={(name) =>
                    setContatoExistente((prev) => ({ ...prev, templateSelecionado: name || null }))
                  }
                  loading={carregandoTemplates}
                  showPreview={false}
                  emptyMessage="Nenhum template aprovado. Crie em Configurações → Integrações → WhatsApp Oficial"
                />
              </div>
            ) : (
              <div>
                <label className="mb-1.5 block text-xs font-medium text-white/70">Mensagem</label>
                <textarea
                  value={contatoExistente.mensagem}
                  onChange={(e) => setContatoExistente(prev => ({ ...prev, mensagem: e.target.value }))}
                  placeholder="Digite a mensagem..."
                  rows={2}
                  className="w-full resize-none rounded-lg border border-white/10 bg-white/5 px-3 py-2 text-sm text-white placeholder:text-white/35 focus:outline-none focus:ring-1 focus:ring-white/20"
                />
              </div>
            )}

              </div>

              {contatoExistente.usarTemplate && (
                <aside className="min-w-0 sm:sticky sm:top-0">
                  <p className="mb-1.5 text-xs font-medium text-white/70">Prévia WhatsApp</p>
                  {findTemplateByName(templates, contatoExistente.templateSelecionado || '') ? (
                    <TemplateMessagePreview
                      template={findTemplateByName(templates, contatoExistente.templateSelecionado || '')}
                      compact
                    />
                  ) : (
                    <p className="rounded-md border border-dashed border-white/15 bg-[#d8d1ca]/10 px-2 py-6 text-center text-[10px] text-white/45">
                      Selecione um template
                    </p>
                  )}
                </aside>
              )}
            </div>

            <div className="mt-3 flex items-center justify-end gap-2 border-t border-white/10 pt-3">
              <button
                type="button"
                onClick={() => {
                  setModalContatoExistente(false);
                  setContatoExistente({ busca: '', contato: null, mensagem: '' });
                  setContatosEncontrados([]);
                }}
                className="px-3 py-1.5 text-sm text-white/60 transition-colors hover:text-white"
                disabled={enviandoAtendimento}
              >
                Cancelar
              </button>
              <button
                type="button"
                onClick={handleContatoExistente}
                disabled={
                  enviandoAtendimento || 
                  !contatoExistente.contato || 
                  !contatoExistente.inboxId ||
                  (!contatoExistente.usarTemplate && !contatoExistente.mensagem) ||
                  (contatoExistente.usarTemplate && !contatoExistente.templateSelecionado)
                }
                className="rounded-lg bg-[#16A34A] px-4 py-1.5 text-sm font-medium text-white shadow-sm transition-colors hover:bg-[#15803D] disabled:opacity-50"
              >
                {enviandoAtendimento ? 'Enviando...' : 'Enviar'}
              </button>
            </div>
          </div>
        </DialogContent>
      </Dialog>

      <Dialog open={showBulkCloseModal} onOpenChange={setShowBulkCloseModal}>
        <DialogContent className="max-w-md w-full gap-0 p-0 overflow-hidden">
          <DialogHeader className="px-5 pt-5 pb-3 border-b border-border">
            <DialogTitle className="text-base font-semibold">Encerrar atendimentos em lote</DialogTitle>
          </DialogHeader>
          <div className="px-5 py-4 space-y-4">
            <p className="text-sm text-muted-foreground">
              Feche vários atendimentos abertos de uma vez usando escopo e tempo de abertura.
            </p>

            <div>
              <label className="block text-sm font-medium mb-1.5">Escopo</label>
              <select
                value={bulkCloseScope}
                onChange={(e) => {
                  setBulkCloseScope(e.target.value);
                  setBulkClosePreviewCount(null);
                }}
                className="niochat-input w-full text-sm"
              >
                <option value="automation">{automationTabLabel}</option>
                <option value="waiting">Espera</option>
              </select>
            </div>

            <div>
              <label className="block text-sm font-medium mb-1.5">Tempo aberto</label>
              <select
                value={bulkCloseTimeMode}
                onChange={(e) => {
                  setBulkCloseTimeMode(e.target.value);
                  setBulkClosePreviewCount(null);
                }}
                className="niochat-input w-full text-sm mb-2"
              >
                <option value="any">Qualquer tempo</option>
                <option value="more_than">Aberto há mais de</option>
                <option value="less_than">Aberto há menos de</option>
              </select>
              {bulkCloseTimeMode !== 'any' && (
                <div className="flex items-center gap-2">
                  <input
                    type="number"
                    min="0"
                    value={bulkCloseMinutes}
                    onChange={(e) => {
                      setBulkCloseMinutes(e.target.value);
                      setBulkClosePreviewCount(null);
                    }}
                    className="niochat-input w-24 text-sm"
                  />
                  <span className="text-sm text-muted-foreground">minutos</span>
                </div>
              )}
            </div>

            {bulkClosePreviewCount != null && (
              <div className="rounded-lg border border-border bg-muted/40 px-3 py-2 text-sm">
                <span className="font-medium text-foreground">{bulkClosePreviewCount}</span>
                {' '}
                atendimento(s) serão encerrados com estes filtros.
              </div>
            )}

            {bulkCloseError && (
              <div className="rounded-lg border border-red-500/30 bg-red-500/10 px-3 py-2 text-sm text-red-500">
                {bulkCloseError}
              </div>
            )}

            <div className="flex justify-end gap-2 pt-2">
              <button
                type="button"
                onClick={() => setShowBulkCloseModal(false)}
                className="px-4 py-2 rounded-lg border border-zinc-600 bg-zinc-800 text-sm font-medium text-zinc-200 hover:bg-zinc-700 transition-colors disabled:opacity-50"
                disabled={bulkCloseLoading}
              >
                Cancelar
              </button>
              <button
                type="button"
                onClick={previewBulkClose}
                className="px-4 py-2 rounded-lg bg-sky-600 text-sm font-medium text-white hover:bg-sky-500 transition-colors disabled:opacity-50"
                disabled={bulkCloseLoading}
              >
                {bulkCloseLoading ? 'Calculando...' : 'Ver quantidade'}
              </button>
              <button
                type="button"
                onClick={executeBulkClose}
                className="px-4 py-2 rounded-lg bg-red-600 text-sm font-medium text-white hover:bg-red-500 transition-colors disabled:opacity-50"
                disabled={bulkCloseLoading}
              >
                Encerrar
              </button>
            </div>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
}, (prevProps, nextProps) => {
  // OTIMIZAÇÃO: Só re-renderizar se props essenciais mudarem
  // Não re-renderizar se apenas a conversa selecionada mudar, a menos que mude qual ID está selecionado
  return (
    prevProps.provedorId === nextProps.provedorId &&
    prevProps.user?.id === nextProps.user?.id &&
    prevProps.user?.user_type === nextProps.user?.user_type &&
    prevProps.selectedConversation?.id === nextProps.selectedConversation?.id &&
    prevProps.onConversationUpdate === nextProps.onConversationUpdate
  );
});

export default ConversationList;
