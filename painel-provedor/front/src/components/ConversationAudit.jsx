import React, { useEffect, useState } from 'react';
import { Eye, Search, Filter, Calendar, X, MessageSquare, Clock, Hash, Bot, User, Smartphone } from 'lucide-react';
import axios from 'axios';
import { getMessages, getAuditLogs } from '../lib/supabase';

// Importar ícones dos canais
import whatsappIcon from '../assets/whatsapp.png';
import telegramIcon from '../assets/telegram.png';
import gmailIcon from '../assets/gmail.png';
import chatBgPattern from '../assets/modo_dark.png';
import chatBgPatternLight from '../assets/modo_claro.png';
import { useTheme } from '../hooks/useTheme';
import AuditChatMessage from './AuditChatMessage';

const PAGE_SIZE = 50;

const toLocalDateInput = (date) => {
  const pad = (n) => String(n).padStart(2, '0');
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`;
};

const computeDuration = (createdAt, endedAt) => {
  if (!createdAt) return 'N/A';
  const durationMs = (endedAt ? new Date(endedAt) : new Date()) - new Date(createdAt);
  if (!Number.isFinite(durationMs) || durationMs < 0) return 'N/A';
  const hours = Math.floor(durationMs / (1000 * 60 * 60));
  const minutes = Math.floor((durationMs % (1000 * 60 * 60)) / (1000 * 60));
  return hours > 0 ? `${hours}h ${minutes}m` : `${minutes}m`;
};

export default function ConversationAudit({ provedorId }) {
  const isDarkTheme = useTheme();
  const [conversations, setConversations] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [stats, setStats] = useState(null);
  const [searchTerm, setSearchTerm] = useState('');
  const [appliedSearch, setAppliedSearch] = useState('');
  const [selectedConversation, setSelectedConversation] = useState(null);
  const [conversationDetails, setConversationDetails] = useState(null);
  const [conversationMessages, setConversationMessages] = useState([]);
  const [loadingDetails, setLoadingDetails] = useState(false);
  const [loadingMessages, setLoadingMessages] = useState(false);
  const [filters, setFilters] = useState(() => ({
    dateFrom: toLocalDateInput(new Date(Date.now() - 30 * 24 * 60 * 60 * 1000)),
    dateTo: toLocalDateInput(new Date())
  }));
  const [page, setPage] = useState(1);
  const [metrics, setMetrics] = useState({});

  // Ícones de status de mensagem (igual ao ChatArea)
  const AuditMessageStatusIcon = ({ message }) => {
    const status = message.additional_attributes?.last_status;
    const readAt = message.additional_attributes?.read_at;
    const deliveredAt = message.additional_attributes?.delivered_at;
    const sentAt = message.additional_attributes?.sent_at;

    let currentStatus = status;
    if (readAt || status === 'read') {
      currentStatus = 'read';
    } else if (deliveredAt || status === 'delivered') {
      currentStatus = 'delivered';
    } else if (sentAt || status === 'sent') {
      currentStatus = 'sent';
    }

    if (!currentStatus && !message.isTemporary && (message.external_id || message.additional_attributes?.external_id)) {
      currentStatus = 'sent';
    }

    // READ: 2 tickets azul forte
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

    // DELIVERED: 2 tickets cinza neutro
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
            <path
              d="M0.5 5.5L3 8L7 4"
              stroke="#D1D5DB"
              strokeWidth="2.2"
              strokeLinecap="round"
              strokeLinejoin="round"
              fill="none"
            />
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

    // SENT: 1 ticket cinza
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

  useEffect(() => {
    if (provedorId) {
      fetchConversations();
      fetchStats();
    }
  }, [provedorId]);

  const fetchConversations = async () => {
    setLoading(true);
    setError('');
    const term = searchTerm.trim();
    try {
      const token = localStorage.getItem('token');

      const params = new URLSearchParams({
        provedor_id: provedorId,
        conversation_closed: 'true',
        page_size: 50
      });

      if (filters.dateFrom) params.append('date_from', filters.dateFrom);
      if (filters.dateTo) params.append('date_to', filters.dateTo);
      if (term) params.append('search', term);

      const response = await axios.get(`/api/audit-logs/?${params}`, {
        headers: { Authorization: `Token ${token}` }
      });

      const data = response.data.results || response.data || [];

      setConversations(data.map(conv => ({ ...conv, duration: computeDuration(conv.created_at, conv.ended_at) })));
      setAppliedSearch(term);
      setPage(1);
    } catch (err) {
      setError('Erro ao carregar conversas encerradas');
      setConversations([]);
    } finally {
      setLoading(false);
    }
  };

  const fetchStats = async () => {
    try {
      const token = localStorage.getItem('token');
      const response = await axios.get(`/api/audit-logs/conversation_stats/?provedor_id=${provedorId}`, {
        headers: { Authorization: `Token ${token}` }
      });
      setStats(response.data);
    } catch (err) {
    }
  };

  const fetchConversationDetails = async (conversationId) => {
    setLoadingDetails(true);
    setLoadingMessages(true);
    try {
      const token = localStorage.getItem('token');

      // Buscar dados completos da conversa do endpoint que busca do Supabase
      const response = await axios.get(`/api/conversations/${conversationId}/?for_audit=1`, {
        headers: { Authorization: `Token ${token}` }
      });

      const conversationData = response.data;

      // Verificar se a conversa foi fechada pela IA
      // Buscar TODOS os audit logs da conversa APENAS do Supabase (SEM fallback para banco local)
      try {
        // Buscar APENAS do Supabase (sem fallback)
        const auditData = await getAuditLogs(provedorId, {
          conversation_id: conversationId
        });

        let auditLogs = [];

        // Se encontrou no Supabase, usar esses dados
        if (auditData && auditData.length > 0) {
          // Filtrar apenas logs desta conversa específica
          auditLogs = auditData.filter(log =>
            log.conversation_id === parseInt(conversationId) ||
            log.conversation_id === conversationId
          );
        }
        // NÃO fazer fallback para API Django - usar apenas Supabase

        const aiClosedLog = auditLogs.find(log => log.action === 'conversation_closed_ai');
        if (aiClosedLog) {
          conversationData.is_ai_closed = true;
        } else if (!conversationData.assignee && !conversationData.team) {
          // Se não tem assignee nem team, provavelmente foi pela IA
          conversationData.is_ai_closed = true;
        }
      } catch (auditErr) {
        // Se não conseguir buscar audit log, verificar se não tem assignee
        if (!conversationData.assignee && !conversationData.team) {
          conversationData.is_ai_closed = true;
        }
      }

      // Calcular duração da conversa
      if (conversationData.created_at && conversationData.ended_at) {
        const startTime = new Date(conversationData.created_at);
        const endTime = new Date(conversationData.ended_at);
        const durationMs = endTime - startTime;
        const hours = Math.floor(durationMs / (1000 * 60 * 60));
        const minutes = Math.floor((durationMs % (1000 * 60 * 60)) / (1000 * 60));

        if (hours > 0) {
          conversationData.duration = `${hours}h ${minutes}m`;
        } else {
          conversationData.duration = `${minutes}m`;
        }
      } else if (conversationData.created_at) {
        const startTime = new Date(conversationData.created_at);
        const now = new Date();
        const durationMs = now - startTime;
        const hours = Math.floor(durationMs / (1000 * 60 * 60));
        const minutes = Math.floor((durationMs % (1000 * 60 * 60)) / (1000 * 60));

        if (hours > 0) {
          conversationData.duration = `${hours}h ${minutes}m`;
        } else {
          conversationData.duration = `${minutes}m`;
        }
      } else {
        conversationData.duration = 'N/A';
      }

      // Mapear dados do CSAT corretamente
      if (conversationData.csat && conversationData.csat.rating_value) {
        conversationData.csat_rating = conversationData.csat.rating_value;
      }

      setConversationDetails(conversationData);

      // Verificar se há mensagens no response do backend
      let messages = conversationData.messages || [];

      // Se não há mensagens do backend, buscar diretamente do Supabase
      if (!messages || messages.length === 0) {
        try {
          messages = await getMessages(conversationId, provedorId);
          if (messages && messages.length > 0) {
          }
        } catch (err) {
        }
      }

      setConversationMessages(messages);

    } catch (err) {
      setConversationDetails(null);
      setConversationMessages([]);
    } finally {
      setLoadingDetails(false);
      setLoadingMessages(false);
    }
  };

  const openConversationModal = (conversationId) => {
    setSelectedConversation(conversationId);
    fetchConversationDetails(conversationId);
    // Prevenir scroll do body quando o modal está aberto
    document.body.style.overflow = 'hidden';
  };

  const closeConversationModal = () => {
    setSelectedConversation(null);
    setConversationDetails(null);
    setConversationMessages([]);
    // Restaurar scroll do body quando o modal fecha
    document.body.style.overflow = '';
  };

  const getChannelIcon = (channelType) => {
    switch (channelType) {
      case 'whatsapp':
        return <img src={whatsappIcon} alt="WhatsApp" className="w-4 h-4" />;
      case 'telegram':
        return <img src={telegramIcon} alt="Telegram" className="w-4 h-4" />;
      case 'email':
        return <img src={gmailIcon} alt="Email" className="w-4 h-4" />;
      case 'app_mobile':
        return <Smartphone className="w-4 h-4 text-orange-500" />;
      default:
        return <img src={whatsappIcon} alt="WhatsApp" className="w-4 h-4" />;
    }
  };

  const getActionBadge = (action) => {
    if (action === 'conversation_closed_ai') {
      return 'bg-purple-100 text-purple-800';
    }
    return 'bg-blue-100 text-blue-800';
  };

  const getClosedBy = (conv) => {
    if (!conv) return { type: 'system', name: 'Sistema' };
    if (conv.closed_by_type) return { type: conv.closed_by_type, name: conv.closed_by_name || 'Sistema' };
    if (conv.action === 'conversation_closed_ai') return { type: 'ai', name: 'IA' };
    if (typeof conv.user === 'string' && conv.user) return { type: 'agent', name: conv.user.split(' (')[0] };
    return { type: 'system', name: 'Sistema' };
  };

  const renderClosedByIcon = (type, size = 'w-4 h-4') => {
    if (type === 'ai') {
      return <img src="/logoia.png?v=1" alt="IA" className={`${size} rounded-full object-cover`} />;
    }
    if (type === 'chatbot') return <Bot className={`${size} text-purple-600`} />;
    if (type === 'agent') return <User className={`${size} text-blue-600`} />;
    return <User className={`${size} text-gray-400`} />;
  };

  const formatDuration = (duration) => {
    if (!duration) return '-';
    if (typeof duration === 'string' && duration.includes('min')) {
      return duration;
    }
    return duration;
  };

  const filteredConversations = conversations.filter(conv => {
    const term = searchTerm.trim();
    if (!term || term === appliedSearch) return true;
    const searchLower = term.toLowerCase();
    const digits = term.replace(/\D/g, '');
    const phoneKey = digits.length >= 8 ? digits.slice(-8) : digits;
    return (
      (conv.contact_name && conv.contact_name.toLowerCase().includes(searchLower)) ||
      (conv.user && conv.user.toLowerCase().includes(searchLower)) ||
      (conv.closed_by_name && conv.closed_by_name.toLowerCase().includes(searchLower)) ||
      (phoneKey.length >= 4 && conv.contact_phone && String(conv.contact_phone).includes(phoneKey)) ||
      (digits && String(conv.conversation_id) === digits)
    );
  });

  const totalPages = Math.max(1, Math.ceil(filteredConversations.length / PAGE_SIZE));
  const currentPage = Math.min(page, totalPages);
  const pageStart = (currentPage - 1) * PAGE_SIZE;
  const pagedConversations = filteredConversations.slice(pageStart, pageStart + PAGE_SIZE);
  const pageIdsKey = pagedConversations.map(c => c.conversation_id).filter(Boolean).join(',');

  useEffect(() => {
    const missing = [...new Set(pageIdsKey.split(',').filter(id => id && !(id in metrics)))];
    if (!missing.length || !provedorId) return;
    let cancelled = false;
    const token = localStorage.getItem('token');
    axios.get('/api/audit-logs/conversation_metrics/', {
      params: { provedor_id: provedorId, ids: missing.join(',') },
      headers: { Authorization: `Token ${token}` }
    }).then(res => {
      if (cancelled) return;
      setMetrics(prev => ({ ...prev, ...(res.data?.metrics || {}) }));
    }).catch(() => {
      if (cancelled) return;
      setMetrics(prev => {
        const next = { ...prev };
        missing.forEach(id => { next[id] = { message_count: null, csat_rating: null }; });
        return next;
      });
    });
    return () => { cancelled = true; };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pageIdsKey, provedorId]);

  const getCSATEmoji = (csatRating) => {
    // Mapear rating CSAT para emoji e texto
    const emojiMap = {
      1: { emoji: '😡', text: 'Péssimo' },
      2: { emoji: '😕', text: 'Ruim' },
      3: { emoji: '😐', text: 'Regular' },
      4: { emoji: '🙂', text: 'Bom' },
      5: { emoji: '🤩', text: 'Excelente' }
    };

    if (!csatRating) return { emoji: '-', text: 'Não avaliado' };

    const rating = emojiMap[csatRating];
    return rating || { emoji: '-', text: 'Não avaliado' };
  };

  if (!provedorId) {
    return (
      <div className="flex-1 p-6 bg-background">
        <div className="text-center text-muted-foreground">
          ID do provedor não fornecido
        </div>
      </div>
    );
  }

  // Tratamento de erro global
  if (error) {
    return (
      <div className="flex-1 p-6 bg-background">
        <div className="text-center text-red-600">
          <h2 className="text-xl font-semibold mb-2">Erro ao carregar auditoria</h2>
          <p className="text-sm">{error}</p>
          <button
            onClick={() => {
              setError('');
              fetchConversations();
            }}
            className="mt-4 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700"
          >
            Tentar novamente
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className={`flex-1 p-6 bg-background ${selectedConversation ? 'overflow-hidden' : 'overflow-y-auto'}`}>
      <div className="max-w-7xl mx-auto w-full">
        {/* Header */}
        <div className="mb-6">
          <h1 className="text-3xl font-bold text-foreground mb-2">Auditoria do Sistema</h1>
          <p className="text-muted-foreground">
            Veja todas as conversas encerradas no sistema, incluindo quem as encerrou e detalhes.
          </p>
        </div>

        {/* Estatísticas */}
        {stats && (
          <div className="grid grid-cols-1 md:grid-cols-4 gap-4 mb-6">
            <div className="bg-card p-6 rounded-lg border">
              <div className="text-2xl font-bold text-foreground mb-1">
                {stats.total_closed || 0}
              </div>
              <div className="text-sm text-muted-foreground">Total Encerradas</div>
            </div>
            <div className="bg-card p-6 rounded-lg border">
              <div className="text-2xl font-bold text-blue-600 mb-1">
                {stats.closed_by_agent || 0}
              </div>
              <div className="text-sm text-muted-foreground">Por Agentes</div>
            </div>
            <div className="bg-card p-6 rounded-lg border">
              <div className="text-2xl font-bold text-purple-600 mb-1">
                {stats.closed_by_ai || 0}
              </div>
              <div className="text-sm text-muted-foreground">Pela IA</div>
            </div>
            <div className="bg-card p-6 rounded-lg border">
              <div className="text-2xl font-bold text-green-600 mb-1">
                {stats.percentage_ai_resolved ? `${stats.percentage_ai_resolved.toFixed(0)}%` : '0%'}
              </div>
              <div className="text-sm text-muted-foreground">Taxa IA</div>
            </div>
          </div>
        )}

        {/* Filtros */}
        <div className="bg-card p-4 rounded-lg border mb-6">
          <div className="flex flex-col md:flex-row gap-4 items-center">
            <div className="flex-1">
              <div className="relative">
                <Search className="w-4 h-4 absolute left-3 top-1/2 transform -translate-y-1/2 text-muted-foreground" />
                <input
                  type="text"
                  placeholder="Pesquisar por cliente, telefone, agente ou nº da conversa..."
                  value={searchTerm}
                  onChange={(e) => setSearchTerm(e.target.value)}
                  onKeyDown={(e) => { if (e.key === 'Enter') fetchConversations(); }}
                  className="w-full pl-10 pr-4 py-2 border rounded-lg bg-background focus:outline-none focus:ring-2 focus:ring-blue-500"
                />
              </div>
            </div>
            <div className="flex gap-2">
              <input
                type="date"
                value={filters.dateFrom}
                onChange={(e) => setFilters(prev => ({ ...prev, dateFrom: e.target.value }))}
                className="px-3 py-2 border rounded-lg bg-background"
              />
              <input
                type="date"
                value={filters.dateTo}
                onChange={(e) => setFilters(prev => ({ ...prev, dateTo: e.target.value }))}
                className="px-3 py-2 border rounded-lg bg-background"
              />
              <button
                onClick={fetchConversations}
                className="px-4 py-2 bg-gradient-to-r from-blue-500 to-blue-400 hover:from-blue-600 hover:to-blue-500 text-white rounded-lg shadow-lg hover:shadow-xl transition-all duration-200"
              >
                Filtrar
              </button>
            </div>
          </div>
        </div>

        {/* Tabela */}
        <div className="bg-card rounded-lg border overflow-hidden">
          {loading && (
            <div className="p-8 text-center">
              <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600 mx-auto"></div>
              <p className="mt-2 text-muted-foreground">Carregando conversas...</p>
            </div>
          )}

          {error && (
            <div className="p-8 text-center text-red-500">
              {error}
            </div>
          )}

          {!loading && !error && (
            <div className="overflow-x-auto">
              <table className="w-full">
                <thead className="bg-muted">
                  <tr>
                    <th className="px-4 py-3 text-left text-sm font-medium text-muted-foreground">Cliente</th>
                    <th className="px-4 py-3 text-left text-sm font-medium text-muted-foreground">Agente</th>
                    <th className="px-4 py-3 text-left text-sm font-medium text-muted-foreground">Data/Hora</th>
                    <th className="px-4 py-3 text-left text-sm font-medium text-muted-foreground">Canais</th>
                    <th className="px-4 py-3 text-left text-sm font-medium text-muted-foreground">Detalhes</th>
                    <th className="px-4 py-3 text-left text-sm font-medium text-muted-foreground">Duração</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-border">
                  {filteredConversations.length === 0 && (
                    <tr>
                      <td colSpan={6} className="px-4 py-12 text-center text-muted-foreground">
                        <MessageSquare className="w-12 h-12 mx-auto mb-3 text-muted-foreground/50" />
                        <p className="text-lg font-medium">Nenhuma conversa encerrada encontrada</p>
                        <p className="text-sm">
                          {appliedSearch
                            ? `Nenhum atendimento de "${appliedSearch}" no período selecionado.`
                            : 'Nenhum atendimento encerrado no período selecionado.'}
                        </p>
                      </td>
                    </tr>
                  )}

                  {pagedConversations.map((conv) => (
                    <tr
                      key={conv.id}
                      className="hover:bg-muted/50 cursor-pointer transition-colors"
                      onClick={() => openConversationModal(conv.conversation_id)}
                    >
                      <td className="px-4 py-3">
                        <div className="flex items-center gap-3">
                          {conv.contact_photo && conv.channel_type === 'whatsapp' ? (
                            <img
                              src={conv.contact_photo}
                              alt={conv.contact_name || 'Cliente'}
                              className="w-8 h-8 rounded-full object-cover border border-border"
                              onError={(e) => {
                                e.target.style.display = 'none';
                              }}
                            />
                          ) : (
                            <div className="w-8 h-8 rounded-full bg-muted flex items-center justify-center">
                              <span className="text-xs font-medium text-muted-foreground">
                                {(conv.contact_name || 'C').charAt(0).toUpperCase()}
                              </span>
                            </div>
                          )}
                          <div>
                            <div className="font-medium text-foreground">
                              {conv.contact_name || 'Cliente'}
                            </div>
                            <div className="text-sm text-muted-foreground">
                              Conversa #{conv.conversation_id}
                            </div>
                          </div>
                        </div>
                      </td>
                      <td className="px-4 py-3">
                        <div className="flex items-center gap-2">
                          {renderClosedByIcon(getClosedBy(conv).type)}
                          <div className="font-medium">{getClosedBy(conv).name}</div>
                        </div>
                      </td>
                      <td className="px-4 py-3">
                        <div className="text-sm">
                          {new Date(conv.timestamp).toLocaleDateString('pt-BR')}
                        </div>
                        <div className="text-xs text-muted-foreground">
                          {new Date(conv.timestamp).toLocaleTimeString('pt-BR')}
                        </div>
                      </td>
                      <td className="px-4 py-3">
                        <div className="flex items-center gap-2">
                          {getChannelIcon(conv.channel_type)}
                          <span className="text-sm capitalize">
                            {conv.channel_type === 'whatsapp' ? 'WhatsApp' :
                              conv.channel_type === 'telegram' ? 'Telegram' :
                                conv.channel_type === 'email' ? 'Email' :
                                  conv.channel_type === 'app_mobile' ? 'App Mobile' :
                                  conv.channel_type || 'WhatsApp'}
                          </span>
                        </div>
                      </td>
                      <td className="px-4 py-3">
                        <div className="text-sm">
                          {metrics[conv.conversation_id]
                            ? `${metrics[conv.conversation_id].message_count ?? '-'} mensagens`
                            : '… mensagens'}
                        </div>
                        <div className="text-xs text-muted-foreground">
                          Avaliação: <span className="text-lg">{getCSATEmoji(metrics[conv.conversation_id]?.csat_rating || null).emoji}</span>
                        </div>
                        <div className="text-xs text-muted-foreground">
                          {conv.resolution_type === 'ai_resolved' ? 'IA resolveu automaticamente' :
                            conv.resolution_type === 'problem_solved' ? 'Problema resolvido com sucesso' :
                              conv.resolution_type === 'client_ended' ? 'Cliente encerrou a conversa' :
                                conv.resolution_type === 'finalized_after_confirmation' ? 'Finalizado pela IA após confirmação do cliente' :
                                  'Conversa finalizada'}
                        </div>
                      </td>
                      <td className="px-4 py-3">
                        <div className="text-sm font-medium">
                          {formatDuration(conv.duration)}
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          {!loading && !error && filteredConversations.length > 0 && (
            <div className="flex flex-col sm:flex-row items-center justify-between gap-3 px-4 py-3 border-t text-sm text-muted-foreground">
              <span>
                Mostrando {pageStart + 1}–{pageStart + pagedConversations.length} de {filteredConversations.length} atendimento{filteredConversations.length === 1 ? '' : 's'}
              </span>
              {totalPages > 1 && (
                <div className="flex items-center gap-2">
                  <button
                    onClick={() => setPage(p => Math.max(1, Math.min(p, totalPages) - 1))}
                    disabled={currentPage <= 1}
                    className="px-3 py-1.5 border rounded-lg bg-background hover:bg-muted disabled:opacity-40 disabled:cursor-not-allowed"
                  >
                    Anterior
                  </button>
                  <span className="px-2 text-foreground">{currentPage} / {totalPages}</span>
                  <button
                    onClick={() => setPage(p => Math.min(totalPages, p + 1))}
                    disabled={currentPage >= totalPages}
                    className="px-3 py-1.5 border rounded-lg bg-background hover:bg-muted disabled:opacity-40 disabled:cursor-not-allowed"
                  >
                    Próxima
                  </button>
                </div>
              )}
            </div>
          )}
        </div>

        {/* Modal de Detalhes */}
        {selectedConversation && (
          <div
            className="fixed inset-0 bg-black/50 flex items-center justify-center z-[100] p-4 overflow-hidden"
            onClick={closeConversationModal}
          >
            <div
              className="bg-background rounded-lg shadow-xl max-w-4xl w-full max-h-[90vh] overflow-y-auto"
              onClick={(e) => e.stopPropagation()}
            >
              {/* Header do Modal */}
              <div className="flex items-center justify-between p-6 border-b">
                <h2 className="text-xl font-semibold">Detalhes da Conversa</h2>
                <button
                  onClick={closeConversationModal}
                  className="p-2 hover:bg-muted rounded-lg transition-colors"
                >
                  <X className="w-5 h-5" />
                </button>
              </div>

              {/* Conteúdo do Modal */}
              <div className="p-6">
                {loadingDetails ? (
                  <div className="text-center py-8">
                    <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600 mx-auto"></div>
                    <p className="mt-2 text-muted-foreground">Carregando detalhes...</p>
                  </div>
                ) : (
                  <div className="space-y-6">
                    {/* Informações Básicas */}
                    <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
                      <div className="bg-muted/50 p-4 rounded-lg">
                        <div className="text-sm text-muted-foreground mb-1">Cliente</div>
                        <div className="font-medium">
                          {conversationDetails?.contact?.name || 'Cliente'}
                        </div>
                      </div>
                      <div className="bg-muted/50 p-4 rounded-lg">
                        <div className="text-sm text-muted-foreground mb-1">Agente</div>
                        {(() => {
                          const row = conversations.find((c) => c.conversation_id === selectedConversation);
                          const assignee = conversationDetails?.assignee;
                          const closedBy = row
                            ? getClosedBy(row)
                            : assignee
                              ? { type: 'agent', name: `${assignee.first_name || ''} ${assignee.last_name || ''}`.trim() || assignee.username }
                              : conversationDetails?.is_ai_closed
                                ? { type: 'ai', name: 'IA' }
                                : { type: 'system', name: 'Sistema' };
                          return (
                            <div className="flex items-center gap-2">
                              {renderClosedByIcon(closedBy.type, 'w-5 h-5')}
                              <span className="font-medium">{closedBy.name}</span>
                            </div>
                          );
                        })()}
                      </div>
                      <div className="bg-muted/50 p-4 rounded-lg">
                        <div className="text-sm text-muted-foreground mb-1">Duração</div>
                        <div className="font-medium">
                          {conversationDetails?.duration || 'Calculando...'}
                        </div>
                      </div>
                      <div className="bg-muted/50 p-4 rounded-lg">
                        <div className="text-sm text-muted-foreground mb-1">Avaliação</div>
                        <div className="font-medium text-2xl">
                          {getCSATEmoji(conversationDetails?.csat_rating || null).emoji}
                        </div>
                        <div className="text-xs text-muted-foreground">
                          {getCSATEmoji(conversationDetails?.csat_rating || null).text}
                        </div>
                      </div>
                    </div>

                    {/* Informações da Conversa */}
                    <div className="bg-muted/50 p-4 rounded-lg">
                      <div className="flex items-center gap-2 mb-3">
                        {getChannelIcon(conversationDetails?.inbox?.channel_type)}
                        <span className="font-medium">
                          {conversationDetails?.inbox?.channel_type === 'whatsapp' ? 'WhatsApp' :
                            conversationDetails?.inbox?.channel_type === 'telegram' ? 'Telegram' :
                              conversationDetails?.inbox?.channel_type === 'email' ? 'Email' :
                                conversationDetails?.inbox?.channel_type === 'app_mobile' ? 'App Mobile' :
                                conversationDetails?.inbox?.channel_type || 'WhatsApp'}
                        </span>
                        <span className="text-sm text-muted-foreground ml-auto">
                          Início: {conversationDetails?.created_at ?
                            new Date(conversationDetails.created_at).toLocaleString('pt-BR') :
                            'Data não disponível'}
                        </span>
                      </div>
                    </div>

                    {/* Histórico da Conversa */}
                    <div className="bg-muted/50 p-4 rounded-lg">
                      <div className="flex items-center gap-2 mb-4">
                        <MessageSquare className="w-5 h-5" />
                        <h3 className="font-semibold">Histórico da Conversa</h3>
                        <span className="text-sm text-muted-foreground ml-auto">
                          {conversationMessages.length} mensagens
                        </span>
                      </div>

                      {loadingMessages ? (
                        <div className="text-center py-8">
                          <div className="animate-spin rounded-full h-6 w-6 border-b-2 border-blue-600 mx-auto"></div>
                          <p className="mt-2 text-sm text-muted-foreground">Carregando mensagens...</p>
                        </div>
                      ) : conversationMessages.length > 0 ? (
                        <div
                          className="rounded-lg px-4 pt-4 h-[60vh] min-h-[320px] overflow-y-auto overflow-x-hidden"
                          style={{
                            backgroundColor: isDarkTheme ? '#0b141a' : '#ffffff',
                            backgroundImage: `url(${isDarkTheme ? chatBgPattern : chatBgPatternLight})`,
                            backgroundRepeat: 'no-repeat',
                            backgroundSize: 'cover',
                            backgroundPosition: 'center center'
                          }}
                        >
                          {conversationMessages.map((message, index) => (
                            <AuditChatMessage
                              key={message.id || index}
                              message={message}
                              conversationId={conversationDetails?.id}
                              channelType={conversationDetails?.inbox?.channel_type}
                              chatbotName={conversationDetails?.inbox?.provedor?.chatbot_name || 'Assistente virtual'}
                              statusIcon={
                                !message.is_from_customer &&
                                conversationDetails?.inbox?.channel_type === 'whatsapp' &&
                                !message.isTemporary ? (
                                  <AuditMessageStatusIcon message={message} />
                                ) : null
                              }
                            />
                          ))}
                        </div>
                      ) : (
                        <div className="text-center py-8 text-muted-foreground">
                          <MessageSquare className="w-12 h-12 mx-auto mb-3 text-muted-foreground/50" />
                          <p>Nenhuma mensagem encontrada para esta conversa.</p>
                        </div>
                      )}
                    </div>
                  </div>
                )}
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
