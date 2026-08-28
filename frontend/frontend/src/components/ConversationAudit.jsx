import React, { useEffect, useState } from 'react';
import { Eye, Search, Filter, Calendar, X, MessageSquare, Clock, Hash, Bot, User } from 'lucide-react';
import axios from 'axios';
import { buildMediaUrl } from '../config/environment';
import { getMessages, getAuditLogs } from '../lib/supabase';

// Importar ícones dos canais
import whatsappIcon from '../assets/whatsapp.png';
import telegramIcon from '../assets/telegram.png';
import gmailIcon from '../assets/gmail.png';
import chatBgPattern from '../assets/chat-bg-pattern.svg';
import chatBgPatternLight from '../assets/chat-bg-pattern-light.svg';

export default function ConversationAudit({ provedorId }) {
  const [conversations, setConversations] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [stats, setStats] = useState(null);
  const [searchTerm, setSearchTerm] = useState('');
  const [selectedConversation, setSelectedConversation] = useState(null);
  const [conversationDetails, setConversationDetails] = useState(null);
  const [conversationMessages, setConversationMessages] = useState([]);
  const [loadingDetails, setLoadingDetails] = useState(false);
  const [loadingMessages, setLoadingMessages] = useState(false);
  const [filters, setFilters] = useState({
    dateFrom: '',
    dateTo: ''
  });

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
    try {
      const token = localStorage.getItem('token');

      const params = new URLSearchParams({
        provedor_id: provedorId,
        conversation_closed: 'true',
        page_size: 50
      });

      if (filters.dateFrom) params.append('date_from', filters.dateFrom);
      if (filters.dateTo) params.append('date_to', filters.dateTo);

      const response = await axios.get(`/api/audit-logs/?${params}`, {
        headers: { Authorization: `Token ${token}` }
      });

      const data = response.data.results || response.data || [];

      // Enriquecer dados com informações adicionais
      const enrichedData = await Promise.all(data.map(async (conv) => {
        try {
          // Buscar mensagens do Supabase em vez da API Django
          const messages = await getMessages(conv.conversation_id, provedorId);

          // Simular dados da conversa baseado na auditoria
          const conversationData = {
            created_at: conv.created_at,
            ended_at: conv.ended_at,
            message_count: messages.length,
            status: 'closed'
          };

          // Calcular duração
          let duration = 'N/A';
          if (conversationData.created_at && conversationData.ended_at) {
            const startTime = new Date(conversationData.created_at);
            const endTime = new Date(conversationData.ended_at);
            const durationMs = endTime - startTime;
            const hours = Math.floor(durationMs / (1000 * 60 * 60));
            const minutes = Math.floor((durationMs % (1000 * 60 * 60)) / (1000 * 60));

            if (hours > 0) {
              duration = `${hours}h ${minutes}m`;
            } else {
              duration = `${minutes}m`;
            }
          } else if (conversationData.created_at) {
            const startTime = new Date(conversationData.created_at);
            const now = new Date();
            const durationMs = now - startTime;
            const hours = Math.floor(durationMs / (1000 * 60 * 60));
            const minutes = Math.floor((durationMs % (1000 * 60 * 60)) / (1000 * 60));

            if (hours > 0) {
              duration = `${hours}h ${minutes}m`;
            } else {
              duration = `${minutes}m`;
            }
          }

          // Buscar CSAT rating
          let csatRating = null;
          try {
            const csatResponse = await axios.get(`/api/csat/feedbacks/?conversation=${conv.conversation_id}`, {
              headers: { Authorization: `Token ${token}` }
            });

            const csatData = csatResponse.data.results || csatResponse.data || [];
            if (csatData.length > 0) {
              csatRating = csatData[0].rating_value;
            }
          } catch (csatError) {
            // CSAT não encontrado, usar null
          }

          // Buscar contagem de mensagens
          let messageCount = 0;
          try {
            const messagesResponse = await axios.get(`/api/messages/?conversation=${conv.conversation_id}&for_audit=1`, {
              headers: { Authorization: `Token ${token}` }
            });

            const messagesData = messagesResponse.data.results || messagesResponse.data || [];
            messageCount = messagesData.length;
          } catch (messagesError) {
            // Mensagens não encontradas, usar 0
          }

          return {
            ...conv,
            duration,
            csat_rating: csatRating,
            message_count: messageCount
          };
        } catch (error) {
          // Se não conseguir buscar dados adicionais, retornar dados originais
          return {
            ...conv,
            duration: 'N/A',
            csat_rating: null,
            message_count: 0
          };
        }
      }));

      setConversations(enrichedData);
    } catch (err) {
      console.error('ConversationAudit: Erro ao buscar conversas:', err);
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
      console.error('Erro ao buscar estatísticas:', err);
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
        console.warn('Erro ao buscar audit logs do Supabase:', auditErr);
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
            console.log(`✅ ${messages.length} mensagens encontradas diretamente do Supabase`);
          }
        } catch (err) {
          console.warn('Erro ao buscar mensagens do Supabase no frontend:', err);
        }
      }

      setConversationMessages(messages);

    } catch (err) {
      console.error('Erro ao buscar detalhes da conversa:', err);
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

  // Função para renderizar mensagens com links destacados (mesma do ChatArea)
  const renderMessageWithLinks = (text) => {
    if (!text || typeof text !== 'string') return text;

    // Regex para detectar URLs completas
    const urlRegex = /(https?:\/\/[^\s\n<>"']+|www\.[^\s\n<>"']+)/gi;

    // Dividir o texto em partes (texto e URLs)
    const parts = [];
    let lastIndex = 0;
    let match;

    urlRegex.lastIndex = 0;

    while ((match = urlRegex.exec(text)) !== null) {
      // Adicionar texto antes da URL
      if (match.index > lastIndex) {
        parts.push({ type: 'text', content: text.substring(lastIndex, match.index) });
      }

      // Adicionar a URL (remover pontuação final se houver)
      let urlContent = match[0];
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

    // Renderizar partes
    return parts.map((part, index) => {
      if (part.type === 'url') {
        // Garantir que a URL tenha protocolo
        let href = part.content;
        if (!href.startsWith('http://') && !href.startsWith('https://')) {
          href = 'https://' + href;
        }

        return (
          <a
            key={index}
            href={href}
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

  const getActionIcon = (action) => {
    if (action === 'conversation_closed_ai') {
      return <img src="/logoia.png?v=1" alt="IA" className="w-4 h-4" />;
    }
    return <User className="w-4 h-4 text-blue-600" />;
  };

  const formatDuration = (duration) => {
    if (!duration) return '-';
    if (typeof duration === 'string' && duration.includes('min')) {
      return duration;
    }
    return duration;
  };

  const filteredConversations = conversations.filter(conv => {
    if (!searchTerm) return true;
    const searchLower = searchTerm.toLowerCase();
    return (
      (conv.contact_name && conv.contact_name.toLowerCase().includes(searchLower)) ||
      (conv.user && conv.user.toLowerCase().includes(searchLower))
    );
  });

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
                  placeholder="Pesquisar por cliente ou agente..."
                  value={searchTerm}
                  onChange={(e) => setSearchTerm(e.target.value)}
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
                        <p className="text-sm">As conversas encerradas aparecerão aqui quando houver atividades.</p>
                      </td>
                    </tr>
                  )}

                  {filteredConversations.map((conv) => (
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
                          {getActionIcon(conv.action)}
                          <div className="font-medium">
                            {conv.action === 'conversation_closed_ai' ? 'Pela IA' :
                              (typeof conv.user === 'string' ? conv.user.split(' (')[0] : conv.user || 'Sistema')}
                          </div>
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
                                  conv.channel_type || 'WhatsApp'}
                          </span>
                        </div>
                      </td>
                      <td className="px-4 py-3">
                        <div className="text-sm">
                          {conv.message_count || 0} mensagens
                        </div>
                        <div className="text-xs text-muted-foreground">
                          Avaliação: <span className="text-lg">{getCSATEmoji(conv.csat_rating || null).emoji}</span>
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
                          {formatDuration(conv.conversation_duration_formatted) || '10 min'}
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>

        {/* Modal de Detalhes */}
        {selectedConversation && (
          <div
            className="fixed inset-0 bg-black/50 flex items-center justify-start z-[100] p-4 pl-[17rem] overflow-hidden"
            onClick={closeConversationModal}
          >
            <div
              className="bg-background rounded-lg shadow-xl max-w-4xl w-full max-h-[90vh] overflow-y-auto"
              onClick={(e) => e.stopPropagation()}
            >
              {/* Header do Modal */}
              <div className="flex items-center justify-between p-6 border-b">
                <h2 className="text-xl font-semibold flex items-center gap-2">
                  <MessageSquare className="w-5 h-5" />
                  Detalhes da Conversa
                </h2>
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
                        <div className="flex items-center gap-2">
                          {conversationDetails?.is_ai_closed || (!conversationDetails?.assignee && !conversationDetails?.team) ? (
                            <>
                              <img src="/logoia.png?v=1" alt="IA" className="w-5 h-5 rounded-full object-cover" onError={(e) => { e.target.style.display = 'none'; }} />
                              <span className="font-medium">Pela IA</span>
                            </>
                          ) : conversationDetails?.assignee ? (
                            <>
                              <User className="w-4 h-4 text-blue-600" />
                              <span className="font-medium">
                                {conversationDetails.assignee.first_name} {conversationDetails.assignee.last_name}
                              </span>
                            </>
                          ) : (
                            <>
                              <User className="w-4 h-4 text-gray-400" />
                              <span className="font-medium text-muted-foreground">Não atribuído</span>
                            </>
                          )}
                        </div>
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
                          className="bg-background rounded-lg p-4 max-h-96 overflow-y-auto"
                          style={{
                            // Mesmo tema de fundo do ChatArea (WhatsApp)
                            minHeight: '200px',
                            backgroundImage: `url(${chatBgPattern})`,
                            backgroundRepeat: 'no-repeat',
                            backgroundSize: 'cover',
                            backgroundPosition: 'center center'
                          }}
                        >
                          <div className="space-y-4">
                            {conversationMessages.map((message, index) => {
                              // Verificar tipos especiais de conteúdo
                              const hasImage = message.message_type === 'image' || (message.attachments && message.attachments.some(att => att.file_type === 'image'));
                              const hasVideo = message.message_type === 'video' || (message.attachments && message.attachments.some(att => att.file_type === 'video'));
                              const hasAudio = message.message_type === 'audio' || (message.attachments && message.attachments.some(att => att.file_type === 'audio'));
                              const hasDocument = message.message_type === 'document' || (message.attachments && message.attachments.some(att => att.file_type === 'file'));
                              const hasQRCode = message.message_type === 'image' && message.content && message.content.includes('QR Code PIX');
                              const hasBoleto = message.content && message.content.includes('🔗') && message.content.includes('Link do Boleto:');
                              const hasButtons = message.additional_attributes?.has_buttons && message.additional_attributes?.button_choices;

                              // Determinar se é mensagem do cliente ou do sistema (IA/agente)
                              // Usar a mesma lógica do ChatArea: is_from_customer determina o lado e a cor
                              const isCustomer = message.is_from_customer === true;

                              // Identificar se é mensagem da IA (para exibir "Sistema" ou "IA")
                              const isFromAI = !isCustomer && (
                                message.sender?.sender_type === 'ai' ||
                                message.from_ai === true ||
                                message.additional_attributes?.from_ai === true
                              );

                              return (
                                <div key={index} className={`flex ${isCustomer ? 'justify-start' : 'justify-end'}`}>
                                  <div className={`max-w-xs lg:max-w-md rounded-2xl px-4 py-3 shadow-sm ${isCustomer
                                    ? 'bg-muted text-foreground'
                                    : 'bg-blue-600 text-white'
                                    }`}>
                                    <div className="text-sm font-medium mb-1">
                                      {isCustomer
                                        ? (conversationDetails?.contact?.name || 'Cliente')
                                        : (isFromAI ? 'Sistema' : 'Agente')
                                      }
                                    </div>

                                    {/* Conteúdo da mensagem com links destacados */}
                                    <div className="text-sm whitespace-pre-wrap">
                                      {renderMessageWithLinks(message.content || message.text || 'Mensagem sem conteúdo')}
                                    </div>

                                    {/* Imagens */}
                                    {hasImage && message.file_url && (
                                      <div className="mb-2">
                                        <img
                                          src={buildMediaUrl(message.file_url)}
                                          alt="Imagem"
                                          className="max-w-full h-auto rounded-lg cursor-pointer hover:opacity-90 transition-opacity"
                                          style={{ maxHeight: '200px' }}
                                        />
                                      </div>
                                    )}

                                    {/* Vídeos */}
                                    {hasVideo && message.file_url && (
                                      <div className="mb-2">
                                        <video
                                          controls
                                          className="max-w-full h-auto rounded-lg"
                                          style={{ maxHeight: '200px' }}
                                        >
                                          <source src={buildMediaUrl(message.file_url)} type="video/mp4" />
                                          Seu navegador não suporta o elemento de vídeo.
                                        </video>
                                      </div>
                                    )}

                                    {/* Documentos/PDFs */}
                                    {hasDocument && message.file_url && (
                                      <div className="mb-2">
                                        <a
                                          href={buildMediaUrl(message.file_url)}
                                          target="_blank"
                                          rel="noopener noreferrer"
                                          className="flex items-center space-x-2 p-2 bg-black/10 rounded-lg hover:bg-black/20 transition-colors"
                                        >
                                          <svg className="w-4 h-4" fill="currentColor" viewBox="0 0 20 20">
                                            <path fillRule="evenodd" d="M4 4a2 2 0 012-2h4.586A2 2 0 0112 2.586L15.414 6A2 2 0 0116 7.414V16a2 2 0 01-2 2H6a2 2 0 01-2-2V4zm2 6a1 1 0 011-1h6a1 1 0 110 2H7a1 1 0 01-1-1zm1 3a1 1 0 100 2h6a1 1 0 100-2H7z" clipRule="evenodd" />
                                          </svg>
                                          <span className="text-sm">{message.content || 'Documento'}</span>
                                        </a>
                                      </div>
                                    )}

                                    {/* QR Codes PIX */}
                                    {hasQRCode && (
                                      <div className="mb-2 p-3 bg-green-50 dark:bg-green-900/20 rounded-lg border border-green-200 dark:border-green-800">
                                        <div className="text-sm font-medium text-green-900 dark:text-green-100 mb-2">
                                          QR Code PIX
                                        </div>
                                        <div className="text-xs text-green-700 dark:text-green-300 mb-2">
                                          Escaneie este QR code com o app do seu banco para pagar via PIX
                                        </div>
                                        {message.file_url && (
                                          <div className="bg-white p-2 rounded border">
                                            <img
                                              src={buildMediaUrl(message.file_url)}
                                              alt="QR Code PIX"
                                              className="w-24 h-24 mx-auto"
                                            />
                                          </div>
                                        )}
                                      </div>
                                    )}

                                    {/* Links de boleto */}
                                    {hasBoleto && (
                                      <div className="mb-2 p-3 bg-orange-50 dark:bg-orange-900/20 rounded-lg border border-orange-200 dark:border-orange-800">
                                        <div className="text-sm font-medium text-orange-900 dark:text-orange-100 mb-2">
                                          Boleto Bancário
                                        </div>
                                        <div className="text-xs text-orange-700 dark:text-orange-300 mb-2">
                                          Clique no link abaixo para acessar o boleto completo
                                        </div>
                                        {message.content.split('\n').map((line, index) => {
                                          if (line.includes('https://')) {
                                            return (
                                              <a
                                                key={index}
                                                href={line.trim()}
                                                target="_blank"
                                                rel="noopener noreferrer"
                                                className="block w-full px-3 py-2 bg-orange-600 text-white rounded-lg hover:bg-orange-700 transition-colors text-sm text-center"
                                              >
                                                Baixar Boleto PDF
                                              </a>
                                            );
                                          }
                                          return null;
                                        })}
                                      </div>
                                    )}

                                    {/* Botões interativos do painel de controle (has_buttons legacy) */}
                                    {hasButtons && (
                                      <div className="mt-3 space-y-2">
                                        {message.additional_attributes.button_choices.map((choice, index) => {
                                          const [nome, acao] = choice.split('|', 2);
                                          if (acao && acao.startsWith('copy:')) {
                                            const textoParaCopiar = acao.replace('copy:', '');
                                            return (
                                              <button
                                                key={index}
                                                onClick={(event) => {
                                                  navigator.clipboard.writeText(textoParaCopiar);
                                                  const btn = event.target;
                                                  const originalText = btn.textContent;
                                                  btn.textContent = 'Copiado!';
                                                  btn.className = 'w-full px-4 py-2 bg-gradient-to-r from-orange-500 to-yellow-500 hover:from-orange-600 hover:to-yellow-600 text-white rounded-lg shadow-lg hover:shadow-xl transition-all duration-200 text-sm font-medium';
                                                  setTimeout(() => {
                                                    btn.textContent = originalText;
                                                    btn.className = 'w-full px-4 py-2 bg-gradient-to-r from-blue-500 to-blue-400 hover:from-blue-600 hover:to-blue-500 text-white rounded-lg shadow-lg hover:shadow-xl transition-all duration-200 text-sm font-medium';
                                                  }, 2000);
                                                }}
                                                className="w-full px-4 py-2 bg-gradient-to-r from-blue-500 to-blue-400 hover:from-blue-600 hover:to-blue-500 text-white rounded-lg shadow-lg hover:shadow-xl transition-all duration-200 text-sm font-medium"
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
                                    {message.additional_attributes?.interactive_rows && message.additional_attributes.interactive_rows.length > 0 && (
                                      <div className="mt-3 space-y-1.5">
                                        <div className="text-[10px] font-bold text-white/70 uppercase tracking-wider mb-2">
                                          Opções da lista do menu
                                        </div>
                                        {message.additional_attributes.interactive_rows.map((row, index) => (
                                          <div
                                            key={row.id || index}
                                            className="px-3 py-2 bg-white/20 border border-white/10 rounded-lg"
                                          >
                                            <div className="text-xs font-semibold text-white">
                                              {row.title}
                                            </div>
                                            {row.description && (
                                              <div className="text-[10px] text-white/70 mt-0.5">
                                                {row.description}
                                              </div>
                                            )}
                                          </div>
                                        ))}
                                      </div>
                                    )}

                                    {/* Botões interativos do chatbot engine */}
                                    {message.additional_attributes?.interactive_buttons && message.additional_attributes.interactive_buttons.length > 0 && (
                                      <div className="mt-3 space-y-1.5">
                                        {message.additional_attributes.interactive_buttons.map((btn, index) => (
                                          <div
                                            key={btn.id || index}
                                            className="px-3 py-2 bg-white/20 border border-white/10 rounded-lg text-center"
                                          >
                                            <span className="text-xs font-bold text-white">
                                              {btn.title}
                                            </span>
                                          </div>
                                        ))}
                                      </div>
                                    )}

                                    {/* Timestamp + status (igual ao ChatArea) */}
                                    <div className={`flex items-center justify-end mt-2 text-xs ${isCustomer ? 'text-muted-foreground' : 'text-white'}`}>
                                      <span>
                                        {new Date(message.created_at || message.timestamp).toLocaleString('pt-BR', {
                                          hour: '2-digit',
                                          minute: '2-digit',
                                          day: '2-digit',
                                          month: '2-digit'
                                        })}
                                      </span>
                                      {!isCustomer &&
                                        conversationDetails?.inbox?.channel_type === 'whatsapp' &&
                                        !message.isTemporary && (
                                          <AuditMessageStatusIcon message={message} />
                                        )}
                                    </div>

                                    <div className="text-xs opacity-70 mt-1">
                                      {message.created_at ?
                                        new Date(message.created_at).toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' }) :
                                        'Horário não disponível'}
                                    </div>
                                  </div>
                                </div>
                              );
                            })}
                          </div>
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
