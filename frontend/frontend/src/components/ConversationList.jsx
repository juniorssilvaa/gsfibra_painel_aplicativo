import React, { useState, useEffect, useRef, useMemo, memo } from 'react';
import { Search, Filter, MoreHorizontal, User, Clock, Tag, MoreVertical, UserPlus } from 'lucide-react';
import axios from 'axios';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from './ui/dialog';
import { buildWebSocketUrl } from '../utils/websocketUrl';
import { useNotifications } from '../contexts/NotificationContext';

const ConversationList = memo(({ onConversationSelect, selectedConversation, provedorId, onConversationUpdate, user }) => {
  const { painelWsConnected } = useNotifications();

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
  const userPermissions = useMemo(() => user?.permissions || [], [user]);
  const userRole = useMemo(() => user?.role || user?.user_type || '', [user]);
  const isProviderAdmin = useMemo(() => {
    return ['admin', 'company_admin', 'provedor_admin'].includes(userRole);
  }, [userRole]);
  const [hasInitialized, setHasInitialized] = useState(false);
  const [wsConnected, setWsConnected] = useState(false);
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
      console.error('Erro ao buscar inboxes:', error);
    } finally {
      setCarregandoInboxes(false);
    }
  };

  // Removido prompt de desbloqueio (UX simplificada)
  useEffect(() => { }, [authReady]);

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

      console.log('Total de templates retornados:', templatesList.length);
      console.log('Templates (primeiros 3):', templatesList.slice(0, 3));

      // Filtrar apenas templates aprovados (case-insensitive para segurança)
      const templatesAprovados = templatesList.filter(t =>
        t.status && t.status.toUpperCase() === 'APPROVED'
      );

      setTemplates(templatesAprovados);

      console.log('Templates aprovados encontrados:', templatesAprovados.length, 'de', templatesList.length);

      if (templatesAprovados.length === 0 && templatesList.length > 0) {
        console.warn('Há templates mas nenhum está aprovado. Status dos templates:',
          templatesList.map(t => ({ name: t.name, status: t.status }))
        );
      }
    } catch (error) {
      console.error('Erro ao buscar templates:', error);
      console.error('Detalhes do erro:', error.response?.data);
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
        console.log('Canal WhatsApp para templates encontrado:', canalWhatsApp.id);
        setNovoContato(prev => ({ ...prev, canal_id: canalWhatsApp.id }));
        setContatoExistente(prev => ({ ...prev, canal_id: canalWhatsApp.id }));
        buscarTemplates(canalWhatsApp.id);
      } else {
        console.warn('Nenhum canal WhatsApp ativo encontrado para templates');
        setTemplates([]);
      }
    } catch (error) {
      console.error('Erro ao buscar canal WhatsApp:', error);
      setTemplates([]);
    }
  };

  //  Função para criar atendimento com novo contato
  const handleNovoContato = async () => {
    if (!novoContato.nome || !novoContato.telefone) {
      alert('Por favor, preencha nome e telefone');
      return;
    }

    // Se usar template, não precisa de mensagem
    if (!novoContato.usarTemplate && !novoContato.mensagem) {
      alert('Por favor, digite uma mensagem ou selecione um template');
      return;
    }

    // Se usar template, deve ter template selecionado
    if (novoContato.usarTemplate && !novoContato.templateSelecionado) {
      alert('Por favor, selecione um template');
      return;
    }

    const telefoneFormatado = novoContato.telefone.replace(/\D/g, '');
    if (!telefoneFormatado.startsWith('55') || telefoneFormatado.length < 12) {
      alert('Telefone deve começar com 55 e ter pelo menos 12 dígitos');
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
          alert('Template não encontrado');
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
          alert('Template enviado com sucesso! A conversa aparecerá no painel em instantes.');
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

      alert('Atendimento criado com sucesso! Aparecerá no painel em instantes.');
      setNovoContato({ nome: '', telefone: '', canal: 'whatsapp', mensagem: '', usarTemplate: false, templateSelecionado: null, canalId: null });
      setModalNovoContato(false);

      // Recarregar conversas
      setTimeout(() => fetchConversations(true), 1000);

    } catch (error) {
      // Tratar erro traduzido do backend
      const errorMessage = error.response?.data?.error || error.response?.data?.detail || error.message;
      alert('Erro ao enviar mensagem: ' + errorMessage);
    } finally {
      setEnviandoAtendimento(false);
    }
  };

  //  Função para criar atendimento com contato existente
  const handleContatoExistente = async () => {
    if (!contatoExistente.contato) {
      alert('Por favor, selecione um contato');
      return;
    }

    if (!contatoExistente.usarTemplate && !contatoExistente.mensagem) {
      alert('Por favor, digite uma mensagem ou selecione um template');
      return;
    }

    // Se usar template, deve ter template selecionado
    if (contatoExistente.usarTemplate && !contatoExistente.templateSelecionado) {
      alert('Por favor, selecione um template');
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
          alert('Template não encontrado');
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
          alert('Template enviado com sucesso! A conversa aparecerá no painel em instantes.');
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

      alert('Atendimento criado com contato existente! Aparecerá no painel em instantes.');
      setContatoExistente({ busca: '', contato: null, mensagem: '', usarTemplate: false, templateSelecionado: null, canalId: null });
      setModalContatoExistente(false);
      setContatosEncontrados([]);

      // Recarregar conversas
      setTimeout(() => fetchConversations(true), 1000);

    } catch (error) {
      // Erro ao enviar para contato existente
      const errorMessage = error.response?.data?.error || error.response?.data?.detail || error.message;
      alert('Erro ao enviar mensagem: ' + errorMessage);
    } finally {
      setEnviandoAtendimento(false);
    }
  };

  // Ref para verificar se o componente está montado
  const isMounted = useRef(true);
  const wsRef = useRef(null);
  const retryTimeoutRef = useRef(null);

  // Cleanup quando o componente desmontar
  useEffect(() => {
    isMounted.current = true;

    return () => {
      isMounted.current = false;
      if (wsRef.current) {
        wsRef.current.close();
      }
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
          page_size: '500', // Aumentado para garantir que novos atendimentos apareçam
          ordering: '-last_message_at',
          include_bot: 'true',
          _t: new Date().getTime().toString() // Cache bust
        });

        if (provedorId) {
          params.append('provedor_id', provedorId);
        }

        const res = await axios.get(`/api/conversations/?${params.toString()}`, {
          headers: { Authorization: `Token ${token}` }
        });

        if (!isMounted.current) return;

        const conversationsData = res.data.results || res.data || [];

        const closedStatuses = ['closed', 'encerrada', 'resolved', 'finalizada'];
        const activeConversations = conversationsData.filter(conv => {
          const status = conv.status || conv.additional_attributes?.status;
          const isClosed = closedStatuses.includes(status);

          if (isClosed && selectedConversation?.id === conv.id) {
            if (onConversationUpdate) {
              onConversationUpdate(null);
            }
            localStorage.removeItem('selectedConversation');
          }

          return !isClosed;
        });

        if (selectedConversation) {
          const selectedStillExists = activeConversations.some(c => c.id === selectedConversation.id);
          const selectedStatus = selectedConversation.status || selectedConversation.additional_attributes?.status;

          if (!selectedStillExists || closedStatuses.includes(selectedStatus)) {
            if (onConversationUpdate) {
              onConversationUpdate(null);
            }
            localStorage.removeItem('selectedConversation');
          }
        }

        // Lógica de som removida (centralizada no NotificationContext)

        setConversations(activeConversations);
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

  const selectedConversationRef = useRef(selectedConversation);
  const onConversationUpdateRef = useRef(onConversationUpdate);

  useEffect(() => {
    selectedConversationRef.current = selectedConversation;
  }, [selectedConversation]);

  useEffect(() => {
    onConversationUpdateRef.current = onConversationUpdate;
  }, [onConversationUpdate]);

  // WebSocket para atualização em tempo real
  useEffect(() => {
    if (!provedorId || !authReady || !isMounted.current) {
      return;
    }

    // O WebSocket agora é gerenciado pelo NotificationContext (painelWsConnected)
    // Este componente apenas ouve as atualizações de estado e reage aos eventos se necessário
    // No entanto, ainda precisamos dos handlers de onmessage para atualizar a lista local.
    // Para manter a estabilidade, vamos mover a conexão para o Context e usar os eventos de lá.
    // Por enquanto, vamos apenas garantir que a conexão aqui não caia ao trocar conversas.

    const connectWebSocket = () => {
      // Priorizar auth_token que é o padrão salvo no Login, mas aceitar token também para compatibilidade
      const token = localStorage.getItem('auth_token') || localStorage.getItem('token');
      if (!token) return;

      const wsUrl = buildWebSocketUrl(`/ws/painel/${provedorId}/`, { token });
      const ws = new WebSocket(wsUrl);
      wsRef.current = ws;

      const wsTimeout = setTimeout(() => {
        // Log removido('Timeout do WebSocket');
        setWsConnected(false);
      }, 5000);

      ws.onopen = () => {
        clearTimeout(wsTimeout);
        setWsConnected(true);
      };

      ws.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);

          // CORREÇÃO: Tratar evento de conversa fechada ANTES de outros eventos
          if (data.type === 'conversation_event' &&
            (data.event_type === 'conversation_closed' || data.event_type === 'conversation_ended')) {
            const closedConversationId = data.conversation_id;

            // Remover conversa fechada do estado imediatamente
            setConversations(prevConversations => {
              const filtered = prevConversations.filter(conv => {
                const status = conv.status || conv.additional_attributes?.status;
                const closedStatuses = ['closed', 'encerrada', 'resolved', 'finalizada'];
                // Remover se for a conversa específica ou se tiver status fechado
                return conv.id !== closedConversationId && !closedStatuses.includes(status);
              });
              return filtered;
            });

            // Se a conversa fechada estava selecionada, limpar seleção IMEDIATAMENTE
            if (selectedConversationRef.current?.id === closedConversationId) {
              if (onConversationUpdateRef.current) {
                // Passar null para limpar a seleção
                onConversationUpdateRef.current(null);
              }
              // Limpar localStorage também
              localStorage.removeItem('selectedConversation');
            }

            // Recarregar lista silenciosamente para evitar piscar "Carregando..."
            setTimeout(() => fetchConversations(false), 300);
            return;
          }

          // Processar todos os tipos de eventos relacionados a conversas
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
            data.event_type === 'message' ||
            data.event_type === 'chat_message' ||
            data.event_type === 'messages';

          if (isConversationEvent || isMessageEvent) {
            // Piscar favicon conforme o tipo de evento (som centralizado no NotificationContext)
            try {
              if (isMessageEvent) {
                startBlinkingFavicon();
              } else if (isConversationEvent) {
                startBlinkingFavicon();
              }
            } catch (_) { }

            setNewMessageNotification(true);
            setTimeout(() => setNewMessageNotification(false), 3000);

            // SEMPRE recarregar a lista de conversas quando houver evento de nova conversa ou nova mensagem
            // Isso garante que a lista seja atualizada mesmo se o payload não contiver a conversa completa
            if (isMounted.current) {
              // Tentar atualização instantânea se tivermos a conversa no evento
              const convAtualizada = data.conversation || (data.data && data.data.conversation) || data.payload || data.conversation_data;
              if (convAtualizada && convAtualizada.id) {
                setConversations(prev => {
                  const previousConversation = prev.find(c => c.id === convAtualizada.id);
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
                    }
                    : convAtualizada;
                  const listaSemAntiga = prev.filter(c => c.id !== convAtualizada.id);
                  // Adicionar no início da lista e ordenar por última mensagem
                  const novaLista = [mergedConversation, ...listaSemAntiga];
                  return novaLista.sort((a, b) => {
                    const timeA = a.last_message?.created_at || a.updated_at || a.created_at || 0;
                    const timeB = b.last_message?.created_at || b.updated_at || b.created_at || 0;
                    return new Date(timeB) - new Date(timeA);
                  });
                });
                
                if (onConversationUpdateRef.current) {
                  onConversationUpdateRef.current(convAtualizada);
                }
              }

              // SEMPRE recarregar para garantir que a lista esteja atualizada
              // Limpar timeout anterior se existir para evitar múltiplas chamadas
              if (fetchTimeoutRef.current) {
                clearTimeout(fetchTimeoutRef.current);
                fetchTimeoutRef.current = null;
              }

              // Usar um pequeno delay para evitar múltiplas chamadas simultâneas
              // Mas garantir que sempre execute
              fetchTimeoutRef.current = setTimeout(() => {
                if (isMounted.current) {
                  fetchConversations(false);
                  fetchTimeoutRef.current = null;
                }
              }, 200);
            }
          }
        } catch (error) {
          // CORREÇÃO DE SEGURANÇA: Não expor detalhes do erro
          // Silenciar erro para não expor informações sensíveis
        }
      };

      ws.onclose = (event) => {
        clearTimeout(wsTimeout);
        setWsConnected(false);

        // Códigos que indicam erro permanente (não tentar reconectar)
        // 4001 = Unauthorized, 4003 = Forbidden
        const permanentErrorCodes = [4001, 4003];

        if (permanentErrorCodes.includes(event.code)) {
          // Erro de permissão ou autenticação - não tentar reconectar
          return;
        }

        // Tentar reconectar em 3 segundos apenas se não foi erro permanente
        if (isMounted.current && authReady) {
          setTimeout(connectWebSocket, 3000);
        }
      };

      ws.onerror = (error) => {
        // CORREÇÃO DE SEGURANÇA: Não expor token em logs
        // O erro pode conter a URL com token, mas não vamos logá-la
        clearTimeout(wsTimeout);
        setWsConnected(false);
      };
    };

    connectWebSocket();

    return () => {
      if (wsRef.current) {
        wsRef.current.close();
        wsRef.current = null;
      }
    };
  }, [provedorId, authReady]);

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

  // Conversas são atualizadas via WebSocket do painel (tempo real)
  // Não é necessário polling - o WebSocket já envia conversation_event quando há mudanças

  const hasHumanAssignee = (conversation) => {
    if (!conversation?.assignee) return false;
    return Boolean(
      conversation.assignee.id ||
      conversation.assignee.username ||
      conversation.assignee.email
    );
  };

  const isClosedStatus = (status) => {
    return ['closed', 'encerrada', 'resolved', 'finalizada'].includes(status);
  };

  const getConversationStatus = (conversation) => {
    return conversation?.status || conversation?.additional_attributes?.status || '';
  };

  const getWaitingForAgent = (conversation) => {
    if (typeof conversation?.waiting_for_agent === 'boolean') return conversation.waiting_for_agent;
    if (typeof conversation?.additional_attributes?.waiting_for_agent === 'boolean') {
      return conversation.additional_attributes.waiting_for_agent;
    }
    return null;
  };

  const isWaitingConversation = (conversation) => {
    const status = getConversationStatus(conversation);
    if (isClosedStatus(status)) return false;
    if (hasHumanAssignee(conversation)) return false;

    const waitingForAgent = getWaitingForAgent(conversation);
    return status === 'pending' || waitingForAgent === true;
  };

  const isAutomationConversation = (conversation) => {
    const status = getConversationStatus(conversation);
    if (isClosedStatus(status)) return false;
    if (hasHumanAssignee(conversation)) return false;

    const waitingForAgent = getWaitingForAgent(conversation);
    // Permitir fallback por status quando a flag não vier no payload.
    return waitingForAgent === false || status === 'snoozed' || status === 'chatbot';
  };

  const isVisibleInWaitingTab = (conversation) => {
    if (hasHumanAssignee(conversation)) return false;

    const assignedUser = conversation.additional_attributes?.assigned_user;
    const assignedTeam = conversation.additional_attributes?.assigned_team;
    const currentUserId = user?.id != null ? String(user.id) : null;
    const currentTeamId = user?.team?.id != null ? String(user.team.id) : null;

    // Se há destino explícito de transferência, só mostra para o destinatário.
    if (assignedUser?.id != null) {
      return currentUserId != null && String(assignedUser.id) === currentUserId;
    }
    if (assignedTeam?.id != null) {
      return currentTeamId != null && String(assignedTeam.id) === currentTeamId;
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

    const canViewAutomationConversations =
      isProviderAdmin ||
      userPermissions.includes('view_ai_conversations') ||
      userPermissions.includes('view_chatbot_conversations');

    // Aba Na Automação para admin do provedor (ou com permissão explícita).
    if (canViewAutomationConversations) {
      tabs.push({
        id: 'automation',
        label: 'Automação',
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
    }

    return filtered;
  }, [conversations, activeTab, user]);

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

  useEffect(() => {
    if (!conversationsListFetchedRef.current || !selectedConversation?.id) return;
    const sid = String(selectedConversation.id);
    const stillInActiveTab = tabFilteredConversations.some((c) => String(c.id) === sid);
    if (!stillInActiveTab) {
      onConversationUpdate?.(null);
    }
  }, [tabFilteredConversations, selectedConversation?.id, onConversationUpdate]);

  return (
    <div className="w-64 flex-shrink-0 border-r border-border bg-background flex flex-col h-full">
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
      <div className="p-4 border-b border-border">
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

        {/* Tabs */}
        <div className="flex gap-1 rounded-full bg-[#2f3238] p-1">
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
              } else if (tab.id === 'all') {
                activeClass = 'bg-[#2ca7ff] text-white shadow-md';
              }
            }

            return (
              <button
                key={tab.id}
                onClick={() => setActiveTab(tab.id)}
                className={`relative flex-1 min-w-0 px-2 py-1.5 text-[11px] font-medium rounded-full transition-all duration-200 ${isActive
                  ? activeClass
                  : 'text-white/90 hover:text-white hover:bg-white/10'
                  }`}
              >
                <span className="flex items-center justify-center gap-1 min-w-0">
                  <span className="whitespace-nowrap">{tab.label}</span>
                </span>
                {tab.count > 0 && (
                  <span className={`absolute -top-1 -right-1 min-w-[16px] h-4 px-1 rounded-full text-[10px] leading-4 font-bold text-white text-center ${isActive ? 'bg-[#ef4444]' : 'bg-[#ef4444]/90'}`}>
                    {tab.count}
                  </span>
                )}
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
                onClick={() => onConversationSelect(conversation)}
                className={`p-3 border-b border-border border-l-4 cursor-pointer transition-all duration-200 hover:bg-accent/50 ${statusBorder} ${selectedConversation?.id === conversation.id ? 'bg-topbar text-topbar-foreground shadow-inner' : ''
                  }`}
              >
                <div className="flex items-start space-x-3 pb-8">
                  <div className="flex-shrink-0 relative w-10">
                    <div className={`w-10 h-10 rounded-full flex items-center justify-center overflow-hidden ${selectedConversation?.id === conversation.id ? 'bg-white/20' : 'bg-primary/10'}`}>
                      {conversation.contact?.avatar ? (
                        <img
                          src={conversation.contact.avatar}
                          alt={conversation.contact.name}
                          className="w-full h-full object-cover"
                        />
                      ) : (
                        <User size={20} className={selectedConversation?.id === conversation.id ? 'text-white' : 'text-primary'} />
                      )}
                    </div>
                    <div className="absolute left-0 top-11">
                      <span className={`inline-flex items-center px-2 py-1 rounded-full text-xs whitespace-nowrap ${selectedConversation?.id === conversation.id ? 'bg-white/20 text-white' : 'bg-gray-600 text-white'}`}>
                        <Clock size={12} className="mr-1" />
                        Há {(() => {
                          const agora = new Date();
                          const inicio = new Date(conversation.created_at);
                          const diffMs = agora - inicio;
                          const diffMinutos = Math.floor(diffMs / (1000 * 60));
                          const diffHoras = Math.floor(diffMinutos / 60);
                          const diffDias = Math.floor(diffHoras / 24);

                          if (diffDias > 0) {
                            return `${diffDias} dia${diffDias > 1 ? 's' : ''}`;
                          } else if (diffHoras > 0) {
                            return `${diffHoras}h ${diffMinutos % 60}min`;
                          } else {
                            return `${diffMinutos} min`;
                          }
                        })()}
                      </span>
                    </div>
                  </div>

                  <div className="flex-1 min-w-0">
                    <div className="flex items-center justify-between">
                      <h3 className={`text-sm font-medium truncate ${selectedConversation?.id === conversation.id ? 'text-topbar-foreground' : 'text-primary'}`}>
                        {conversation.contact?.name || 'Contato sem nome'}
                      </h3>
                      <span className={`text-xs ${selectedConversation?.id === conversation.id ? 'text-topbar-foreground/70' : 'text-muted-foreground'}`}>
                        {!conversation.last_message?.panel_waiting_content_hidden && conversation.last_message?.created_at
                          ? new Date(conversation.last_message.created_at).toLocaleTimeString('pt-BR', {
                            hour: '2-digit',
                            minute: '2-digit'
                          })
                          : ''}
                      </span>
                    </div>

                    <p className={`text-sm truncate mt-1 ${selectedConversation?.id === conversation.id ? 'text-topbar-foreground/80' : 'text-muted-foreground'}`}>
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
                          'voice': 'Você recebeu uma mensagem de voz'
                        };
                        
                        if (labels[type]) return labels[type];

                        // Fallback para mensagens interativas se o conteúdo for vazio
                        if (!msg.content || msg.content === '...') {
                          const attrs = msg.additional_attributes;
                          if (attrs?.interactive_rows?.length > 0) return '📋 Menu de Opções';
                          if (attrs?.interactive_buttons?.length > 0) return '🔘 Botões Interativos';
                        }

                        return msg.content || 'Nenhuma mensagem';
                      })()}
                    </p>

                  </div>
                </div>
              </div>
            );
          })
        )}
      </div>

      {/*  Modal de novo contato */}
      <Dialog open={modalNovoContato} onOpenChange={setModalNovoContato}>
        <DialogContent className="max-w-md w-full">
          <DialogHeader>
            <DialogTitle>Novo Contato</DialogTitle>
          </DialogHeader>
          <div className="space-y-4">
            <div>
              <label className="block text-sm font-medium mb-2 text-white">Nome do Contato</label>
              <input
                type="text"
                value={novoContato.nome}
                onChange={(e) => setNovoContato(prev => ({ ...prev, nome: e.target.value }))}
                placeholder="Digite o nome do contato"
                className="w-full px-3 py-2 border border-input rounded-lg focus:outline-none focus:ring-2 focus:ring-ring text-white bg-background/50"
              />
            </div>

            <div>
              <label className="block text-sm font-medium mb-2 text-white">Telefone (com 55)</label>
              <input
                type="text"
                value={novoContato.telefone}
                onChange={(e) => setNovoContato(prev => ({ ...prev, telefone: e.target.value }))}
                placeholder="5511999999999"
                className="w-full px-3 py-2 border border-input rounded-lg focus:outline-none focus:ring-2 focus:ring-ring text-white bg-background/50"
              />
            </div>


            {/* Seleção de Inbox Específico */}
            {inboxes.length > 0 && (
              <div>
                <label className="block text-sm font-medium mb-2 text-white">Canal Específico (Conexão)</label>
                <select
                  value={novoContato.inboxId || ''}
                  onChange={(e) => {
                    const selectedInboxId = e.target.value;
                    const selectedInbox = inboxes.find(i => i.id.toString() === selectedInboxId.toString());
                    const channel_id_value = selectedInbox?.channel_id || null;
                    setNovoContato(prev => ({
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
                  className="w-full px-3 py-2 border border-input rounded-lg focus:outline-none focus:ring-2 focus:ring-ring text-white bg-background/50"
                >
                  <option value="">Selecione a conexão</option>
                  {inboxes
                    .map(inbox => (
                      <option key={inbox.id} value={inbox.id}>
                        {(inbox.custom_name || inbox.name)} ({inbox.channel_type === 'whatsapp_oficial' ? 'WhatsApp' : inbox.channel_type}) {inbox.additional_attributes?.phone_number ? `(${inbox.additional_attributes.phone_number})` : ''}
                      </option>
                    ))}
                </select>
                {inboxes.length === 0 && (
                  <p className="text-xs text-destructive mt-1">Nenhuma conexão ativa encontrada.</p>
                )}
              </div>
            )}

            {(novoContato.canal === 'whatsapp' || novoContato.canal === 'whatsapp_oficial') && (
              <div>
                <label className="flex items-center space-x-2 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={novoContato.usarTemplate}
                    onChange={(e) => setNovoContato(prev => ({
                      ...prev,
                      usarTemplate: e.target.checked,
                      templateSelecionado: e.target.checked ? prev.templateSelecionado : null,
                      mensagem: e.target.checked ? '' : prev.mensagem
                    }))}
                    className="w-4 h-4"
                  />
                  <span className="text-sm font-medium text-white">Usar template de mensagem (para iniciar conversa após 24h)</span>
                </label>
              </div>
            )}

            {novoContato.usarTemplate && (novoContato.canal === 'whatsapp' || novoContato.canal === 'whatsapp_oficial') ? (
              <div>
                <label className="block text-sm font-medium mb-2 text-white">Template</label>
                {carregandoTemplates ? (
                  <div className="text-sm text-muted-foreground">Carregando templates...</div>
                ) : templates.length > 0 ? (
                  <select
                    value={novoContato.templateSelecionado || ''}
                    onChange={(e) => setNovoContato(prev => ({ ...prev, templateSelecionado: e.target.value }))}
                    className="w-full px-3 py-2 border border-input rounded-lg focus:outline-none focus:ring-2 focus:ring-ring text-white bg-background/50"
                  >
                    <option value="" className="bg-background text-white">Selecione um template</option>
                    {templates.map((template, index) => (
                      <option key={template.id || template.name || `template-${index}`} value={template.name} className="bg-background text-white">
                        {template.name} ({template.language || 'pt_BR'})
                      </option>
                    ))}
                  </select>
                ) : (
                  <div className="text-sm text-muted-foreground">
                    Nenhum template aprovado encontrado. Crie templates em Configurações → Integrações → WhatsApp Oficial
                  </div>
                )}
              </div>
            ) : (
              <div>
                <label className="block text-sm font-medium mb-2 text-white">Mensagem</label>
                <textarea
                  value={novoContato.mensagem}
                  onChange={(e) => setNovoContato(prev => ({ ...prev, mensagem: e.target.value }))}
                  placeholder="Digite a mensagem a ser enviada"
                  rows={3}
                  className="w-full px-3 py-2 border border-input rounded-lg focus:outline-none focus:ring-2 focus:ring-ring resize-none text-white bg-background/50"
                />
              </div>
            )}

            <div className="flex items-center justify-end space-x-2 pt-4">
              <button
                onClick={() => setModalNovoContato(false)}
                className="px-4 py-2 text-muted-foreground hover:text-primary transition-colors"
                disabled={enviandoAtendimento}
              >
                Cancelar
              </button>
              <button
                onClick={handleNovoContato}
                disabled={enviandoAtendimento}
                className="px-4 py-2 bg-primary text-primary-foreground rounded-lg hover:bg-primary/90 transition-colors disabled:opacity-50"
              >
                {enviandoAtendimento
                  ? 'Enviando...'
                  : novoContato.usarTemplate
                    ? 'Enviar Template'
                    : 'Enviar Mensagem'}
              </button>
            </div>
          </div>
        </DialogContent>
      </Dialog>

      {/*  Modal de contato existente */}
      <Dialog open={modalContatoExistente} onOpenChange={setModalContatoExistente}>
        <DialogContent className="max-w-md w-full">
          <DialogHeader>
            <DialogTitle>Contato Existente</DialogTitle>
          </DialogHeader>
          <div className="space-y-4">
            <div>
              <label className="block text-sm font-medium mb-2 text-white">Buscar Contato</label>
              <input
                type="text"
                value={contatoExistente.busca}
                onChange={(e) => {
                  setContatoExistente(prev => ({ ...prev, busca: e.target.value }));
                  buscarContatos(e.target.value);
                }}
                placeholder="Digite nome ou telefone"
                className="w-full px-3 py-2 border border-input rounded-lg focus:outline-none focus:ring-2 focus:ring-ring text-white bg-background/50"
              />
            </div>

            {/* Lista de contatos encontrados */}
            {contatosEncontrados.length > 0 && (
              <div className="max-h-40 overflow-y-auto border border-border rounded-lg">
                {contatosEncontrados.map(contato => (
                  <button
                    key={contato.id}
                    onClick={() => setContatoExistente(prev => ({ ...prev, contato }))}
                    className={`w-full text-left p-3 hover:bg-accent transition-colors border-b last:border-b-0 ${contatoExistente.contato?.id === contato.id ? 'bg-accent' : ''
                      }`}
                  >
                    <div className="font-medium">{contato.name}</div>
                    <div className="text-sm text-muted-foreground">{contato.phone}</div>
                  </button>
                ))}
              </div>
            )}

            {/* Contato selecionado */}
            {contatoExistente.contato && (
              <div className="p-3 bg-accent rounded-lg">
                <div className="font-medium">Contato Selecionado:</div>
                <div className="text-sm">{contatoExistente.contato.name} - {contatoExistente.contato.phone}</div>
              </div>
            )}

            {/* Seleção de Inbox para Contato Existente */}
            {inboxes.length > 0 && (
              <div>
                <label className="block text-sm font-medium mb-2 text-white">Canal de Envio</label>
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
                  className="w-full px-3 py-2 border border-input rounded-lg focus:outline-none focus:ring-2 focus:ring-ring text-white bg-background/50"
                >
                  <option value="">Selecione a conexão</option>
                  {inboxes.map(inbox => (
                    <option key={inbox.id} value={inbox.id}>
                      {(inbox.custom_name || inbox.name)} ({inbox.channel_type === 'whatsapp_oficial' ? 'WhatsApp' : inbox.channel_type}) {inbox.additional_attributes?.phone_number ? `(${inbox.additional_attributes.phone_number})` : ''}
                    </option>
                  ))}
                </select>
              </div>
            )}

            <div>
              <label className="flex items-center space-x-2 cursor-pointer">
                <input
                  type="checkbox"
                  checked={contatoExistente.usarTemplate}
                  onChange={(e) => setContatoExistente(prev => ({
                    ...prev,
                    usarTemplate: e.target.checked,
                    templateSelecionado: e.target.checked ? prev.templateSelecionado : null,
                    mensagem: e.target.checked ? '' : prev.mensagem
                  }))}
                  className="w-4 h-4"
                />
                <span className="text-sm font-medium text-white">Usar template de mensagem (para iniciar conversa após 24h)</span>
              </label>
            </div>

            {contatoExistente.usarTemplate ? (
              <div>
                <label className="block text-sm font-medium mb-2 text-white">Template</label>
                {carregandoTemplates ? (
                  <div className="text-sm text-muted-foreground">Carregando templates...</div>
                ) : templates.length > 0 ? (
                  <select
                    value={contatoExistente.templateSelecionado || ''}
                    onChange={(e) => setContatoExistente(prev => ({ ...prev, templateSelecionado: e.target.value }))}
                    className="w-full px-3 py-2 border border-input rounded-lg focus:outline-none focus:ring-2 focus:ring-ring text-white bg-background/50"
                  >
                    <option value="" className="bg-background text-white">Selecione um template</option>
                    {templates.map((template, index) => (
                      <option key={template.id || template.name || `template-${index}`} value={template.name} className="bg-background text-white">
                        {template.name} ({template.language || 'pt_BR'})
                      </option>
                    ))}
                  </select>
                ) : (
                  <div className="text-sm text-muted-foreground">
                    Nenhum template aprovado encontrado. Crie templates em Configurações → Integrações → WhatsApp Oficial
                  </div>
                )}
              </div>
            ) : (
              <div>
                <label className="block text-sm font-medium mb-2 text-white">Mensagem</label>
                <textarea
                  value={contatoExistente.mensagem}
                  onChange={(e) => setContatoExistente(prev => ({ ...prev, mensagem: e.target.value }))}
                  placeholder="Digite a mensagem a ser enviada"
                  rows={3}
                  className="w-full px-3 py-2 border border-input rounded-lg focus:outline-none focus:ring-2 focus:ring-ring resize-none text-white bg-background/50"
                />
              </div>
            )}

            <div className="flex items-center justify-end space-x-2 pt-4">
              <button
                onClick={() => {
                  setModalContatoExistente(false);
                  setContatoExistente({ busca: '', contato: null, mensagem: '' });
                  setContatosEncontrados([]);
                }}
                className="px-4 py-2 text-muted-foreground hover:text-primary transition-colors"
                disabled={enviandoAtendimento}
              >
                Cancelar
              </button>
              <button
                onClick={handleContatoExistente}
                disabled={
                  enviandoAtendimento || 
                  !contatoExistente.contato || 
                  !contatoExistente.inboxId || // Canal obrigatório
                  (!contatoExistente.usarTemplate && !contatoExistente.mensagem) || // Mensagem obrigatória se não usar template
                  (contatoExistente.usarTemplate && !contatoExistente.templateSelecionado) // Template obrigatório se selecionado
                }
                className="px-4 py-2 bg-primary text-primary-foreground rounded-lg hover:bg-primary/90 transition-colors disabled:opacity-50"
              >
                {enviandoAtendimento ? 'Enviando...' : 'Enviar Mensagem'}
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
    prevProps.selectedConversation?.id === nextProps.selectedConversation?.id &&
    prevProps.onConversationUpdate === nextProps.onConversationUpdate
  );
});

export default ConversationList;
