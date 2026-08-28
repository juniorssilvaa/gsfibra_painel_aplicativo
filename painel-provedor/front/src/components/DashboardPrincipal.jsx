import React, { useState, useEffect, useMemo } from 'react';
import { Card, CardContent } from "@/components/ui/card";
import { buildAuthenticatedWebSocketUrl } from '../utils/websocketUrl';
import { buildApiPath } from '../utils/apiBaseUrl';
import {
  MetricIconChatBubble,
  MetricIconUsersGroup,
  MetricIconTrendRising,
  MetricIconBadgeCheck,
} from './dashboard/MetricIcons';
import axios from 'axios';
import MetricCard from './dashboard/MetricCard';
import ConversationsPieChart from './dashboard/ConversationsPieChart';
import ResponseTimeChart from './dashboard/ResponseTimeChart';
import ConversationAnalysis from './dashboard/ConversationAnalysis';
import {
  applyPieColors,
  PIE_CHANNEL_COLORS,
  PIE_RESOLUTION_COLORS,
  PIE_STATUS_COLORS,
} from '../utils/dashboardChartColors';

import WaitingQueueSLA from './dashboard/WaitingQueueSLA';
import RecentActivity from './dashboard/RecentActivity';
import { subscribeToCSAT, subscribeToAudit } from '../lib/supabase';
import { useAuth } from '../contexts/AuthContext';
import { parseRouteProvedorId, effectiveProvedorFromUser } from '../utils/effectiveProvedorId';

const DashboardPrincipal = ({ provedorId }) => {
  const { user } = useAuth();
  const effectivePid = useMemo(
    () => parseRouteProvedorId(provedorId) ?? effectiveProvedorFromUser(user),
    [provedorId, user]
  );
  const [loading, setLoading] = useState(!effectivePid);
  const [error, setError] = useState(effectivePid ? '' : 'Provedor não identificado. Faça login novamente.');
  const [stats, setStats] = useState({
    total_conversas: 0,
    conversas_abertas: 0,
    conversas_pendentes: 0,
    conversas_resolvidas: 0,
    conversas_em_andamento: 0,
    contatos_unicos: 0,
    contatos_bloqueados_atender: 0,
    contatos_bloqueados_disparos: 0,
    mensagens_30_dias: 0,
    tempo_medio_resposta: '0min',
    tempo_primeira_resposta: '0min',
    taxa_resolucao: '0%',
    satisfacao_media: '0.0',
    midias_30_dias: 0,
    autoatendimentos_30_dias: 0,
    status_presenca: '',
    resolvidas_automacao_ia: 0,
    resolvidas_demais_encerramentos: 0,
    resolvidas_encerrado_manual: 0,
    bot_mode: 'ia'
  });
  const [providerBotMode, setProviderBotMode] = useState(null);
  const [canais, setCanais] = useState([]);
  const [responseTimeData, setResponseTimeData] = useState([]);
  const [ws, setWs] = useState(null);

  // Estados para dados do Supabase (apenas para os 2 cards específicos)
  const [supabaseStats, setSupabaseStats] = useState({
    satisfacao_media: '0.0',
    taxa_resolucao: '0%'
  });


  useEffect(() => {
    async function fetchDashboardData() {
      if (!effectivePid) return;
      try {
        setLoading(true);
        // Priorizar auth_token que é o padrão salvo no Login, mas aceitar token também para compatibilidade
        let token = localStorage.getItem('auth_token') || localStorage.getItem('token');

        if (!token) {
          throw new Error('Token não encontrado. Faça login novamente.');
        }

        // Buscar estatísticas gerais da API real
        // Rota válida ou utilizador (ex.: niohub) — nunca enviar provedor_id=null
        const statsUrl = effectivePid
          ? buildApiPath(`/api/dashboard/stats/?provedor_id=${effectivePid}`)
          : buildApiPath('/api/dashboard/stats/');

        // Garantir que o token está sendo enviado - usar axios com header explícito
        // O interceptor do axios já adiciona o token, mas vamos garantir que está correto
        const statsResponse = await axios.get(statsUrl, {
          headers: {
            'Authorization': `Token ${token}`
          }
        });

        const statsData = statsResponse.data;
        setStats(statsData.stats || statsData);

        // Buscar dados dos canais
        try {
          const canaisResponse = await axios.get(buildApiPath('/api/canais/'), {
            headers: {
              'Authorization': `Token ${token}`
            }
          });

          const canaisData = canaisResponse.data;
          setCanais(canaisData.results || canaisData || []);
        } catch (err) {
        }

        // Buscar dados de tempo de resposta por hora
        try {
          const responseTimeResponse = await axios.get(buildApiPath('/api/dashboard/response-time-hourly/'), {
            headers: {
              'Authorization': `Token ${token}`
            }
          });

          const responseTimeData = responseTimeResponse.data;
          setResponseTimeData(responseTimeData);
        } catch (err) {
        }

        setLoading(false);
      } catch (err) {
        setError('Erro ao carregar dados do dashboard: ' + err.message);
        setLoading(false);
      }
    }

    fetchDashboardData();
  }, [effectivePid]);

  // Buscar modo do provedor diretamente para evitar fallback incorreto no card
  useEffect(() => {
    const fetchProviderMode = async () => {
      if (!effectivePid) return;
      try {
        const token = localStorage.getItem('auth_token') || localStorage.getItem('token');
        if (!token) return;
        const res = await axios.get(buildApiPath(`/api/provedores/${effectivePid}/`), {
          headers: { Authorization: `Token ${token}` }
        });
        const mode = res.data?.bot_mode;
        if (mode === 'chatbot' || mode === 'ia') {
          setProviderBotMode(mode);
        }
      } catch (err) {
      }
    };
    fetchProviderMode();
  }, [effectivePid]);

  // WebSocket para atualizações em tempo real
  useEffect(() => {
    if (!effectivePid) return;

    const connectWebSocket = async () => {
      // Priorizar auth_token que é o padrão salvo no Login, mas aceitar token também para compatibilidade
      const token = localStorage.getItem('auth_token') || localStorage.getItem('token');
      if (!token) return;

      const wsUrl = await buildAuthenticatedWebSocketUrl('/ws/conversas_dashboard/', { token });
      const websocket = new WebSocket(wsUrl);

      websocket.onopen = () => {
        setWs(websocket);
      };

      websocket.onmessage = (event) => {
        const data = JSON.parse(event.data);

        // Atualizar estatísticas em tempo real
        if (data.type === 'dashboard_update') {
          setStats(prevStats => ({
            ...prevStats,
            ...data.stats
          }));
        }
      };

      websocket.onclose = () => {
        setWs(null);
        // Reconectar após 5 segundos
        setTimeout(connectWebSocket, 5000);
      };

      websocket.onerror = (error) => {
        // CORREÇÃO DE SEGURANÇA: Não expor token em logs
        // O erro pode conter a URL com token, mas não vamos logá-la
      };
    };

    connectWebSocket();

    return () => {
      if (ws) {
        ws.close();
      }
    };
  }, [effectivePid]);

  // Atualizar dados a cada 30 segundos
  useEffect(() => {
    if (!effectivePid) return;

    const interval = setInterval(async () => {
      try {
        // Priorizar auth_token que é o padrão salvo no Login, mas aceitar token também para compatibilidade
        const token = localStorage.getItem('auth_token') || localStorage.getItem('token');
        const statsUrl = effectivePid
          ? buildApiPath(`/api/dashboard/stats/?provedor_id=${effectivePid}`)
          : buildApiPath('/api/dashboard/stats/');
        const response = await axios.get(statsUrl, {
          headers: {
            'Authorization': `Token ${token}`
          }
        });

        if (response.status === 200) {
          const data = response.data;
          setStats(data.stats || data);
        }
      } catch (error) {
      }
    }, 30000); // 30 segundos

    return () => clearInterval(interval);
  }, [effectivePid]);

  // useEffect para inicializar dados do Supabase (apenas para os 2 cards)
  useEffect(() => {
    if (effectivePid) {
      fetchSupabaseStats();
      setupRealtimeSubscriptions();
    }
  }, [effectivePid]);

  // Função para buscar dados de satisfação e taxa de resolução
  const fetchSupabaseStats = async () => {
    try {
      // Priorizar auth_token que é o padrão salvo no Login, mas aceitar token também para compatibilidade
      const token = localStorage.getItem('auth_token') || localStorage.getItem('token');

      // Buscar satisfação média e estatísticas do dashboard (que já tem conversas resolvidas)
      const csatStatsUrl = effectivePid
        ? buildApiPath(`/api/csat/feedbacks/stats/?days=30&provedor_id=${effectivePid}`)
        : buildApiPath('/api/csat/feedbacks/stats/?days=30');
      const dashboardStatsUrl = effectivePid
        ? buildApiPath(`/api/dashboard/stats/?provedor_id=${effectivePid}`)
        : buildApiPath('/api/dashboard/stats/');

      const [csatResponse, dashboardStatsResponse] = await Promise.all([
        axios.get(csatStatsUrl, {
          headers: { Authorization: `Token ${token}` }
        }),
        axios.get(dashboardStatsUrl, {
          headers: { Authorization: `Token ${token}` }
        })
      ]);

      const csatData = csatResponse.data;
      // Formatar average_rating para ter 1 casa decimal (igual ao CSAT Dashboard)
      const averageRating = csatData.average_rating
        ? parseFloat(csatData.average_rating).toFixed(1)
        : '0.0';

      // Calcular taxa de resolução baseada nas conversas resolvidas do dashboard
      const dashboardStats = dashboardStatsResponse.data;
      const conversasResolvidas = dashboardStats.conversas_resolvidas || 0;
      const totalConversas = dashboardStats.total_conversas || 0;

      // Taxa de resolução = (conversas resolvidas / total de conversas) * 100
      const resolutionRate = totalConversas > 0
        ? Math.round((conversasResolvidas / totalConversas) * 100)
        : 0;

      setSupabaseStats({
        satisfacao_media: averageRating.toString(),
        taxa_resolucao: `${resolutionRate}%`
      });
    } catch (error) {
      // Manter valores padrão em caso de erro
      setSupabaseStats({
        satisfacao_media: '0.0',
        taxa_resolucao: '0%'
      });
    }
  };

  // Configurar Realtime subscriptions (apenas para os 2 cards)
  const setupRealtimeSubscriptions = () => {
    // Subscription para CSAT (Satisfação Média)
    subscribeToCSAT(effectivePid, (payload) => {
      fetchSupabaseStats();
    });

    // Subscription para Auditoria (Taxa de Resolução)
    subscribeToAudit(effectivePid, (payload) => {
      fetchSupabaseStats();
    });
  };

  // Função para traduzir tipos de canal
  const getChannelDisplayName = (channelType) => {
    // Normalizar tipos de WhatsApp
    if (channelType === 'whatsapp_session' || channelType === 'whatsapp_oficial' || channelType === 'whatsapp') {
      return 'WhatsApp';
    }

    const channelNames = {
      'whatsapp': 'WhatsApp',
      'telegram': 'Telegram',
      'email': 'Email',
      'webchat': 'Chat Web',
      'facebook': 'Facebook',
      'instagram': 'Instagram'
    };
    return channelNames[channelType] || channelType?.charAt(0).toUpperCase() + channelType?.slice(1) || 'Outros';
  };

  // Remover channelData mockado - usar apenas dados reais da API

  // Dados reais do banco de dados
  const effectiveBotMode = providerBotMode || stats.bot_mode || 'ia';
  const isChatbotMode = effectiveBotMode === 'chatbot';
  const automacaoTitulo = isChatbotMode ? 'Resolvidas pelo Chatbot' : 'Resolvidas pela IA';
  const automacaoLegenda = isChatbotMode ? 'Chatbot' : 'IA';

  const metrics = React.useMemo(() => {
    return {
      conversasAtivas: {
        value: (stats.conversas_abertas || 0) + (stats.conversas_pendentes || 0) + (stats.conversas_ia || 0),
        change: '0%',
        trend: 'neutral'
      },
      contatosBloqueados: {
        value: (stats.contatos_bloqueados_atender || 0) + (stats.contatos_bloqueados_disparos || 0),
        subtitle: `Atender: ${stats.contatos_bloqueados_atender || 0} • Disparos: ${stats.contatos_bloqueados_disparos || 0}`,
        change: '0%',
        trend: 'neutral'
      },
      satisfacao: {
        value: supabaseStats.satisfacao_media || '0.0',
        change: '0%', // Não mostrar mudança percentual para satisfação média
        // Verde se >= 4.0 (bom), neutro se >= 2.5 (regular), vermelho se < 2.5 (ruim)
        trend: (() => {
          const rating = parseFloat(supabaseStats.satisfacao_media || '0.0');
          if (rating >= 4.0) return 'up';      // Bom - verde
          if (rating >= 2.5) return 'neutral'; // Regular - neutro
          return 'down';                        // Ruim - vermelho
        })()
      },
      taxaResolucao: {
        value: supabaseStats.taxa_resolucao || '0%',
        change: '0%',
        trend: 'neutral'
      }
    };
  }, [stats, supabaseStats]);

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary"></div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="bg-red-100 border border-red-400 text-red-700 px-4 py-3 rounded">
        {error}
      </div>
    );
  }

  return (
    <div className="w-full min-h-full space-y-6 p-6 bg-background">
      {/* Métricas principais */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        <MetricCard
          title="Conversas em Andamento"
          value={metrics.conversasAtivas.value}
          change={metrics.conversasAtivas.change}
          trend={metrics.conversasAtivas.trend}
          icon={MetricIconChatBubble}
        />
        <MetricCard
          title="Contatos Bloqueados"
          value={metrics.contatosBloqueados.value}
          change={metrics.contatosBloqueados.change}
          trend={metrics.contatosBloqueados.trend}
          icon={MetricIconUsersGroup}
          subtitle={metrics.contatosBloqueados.subtitle}
        />
        <MetricCard
          title="Satisfação Média"
          value={metrics.satisfacao.value}
          change={metrics.satisfacao.change}
          trend={metrics.satisfacao.trend}
          icon={MetricIconTrendRising}
        />
        <MetricCard
          title="Taxa de Resolução"
          value={metrics.taxaResolucao.value}
          change={metrics.taxaResolucao.change}
          trend={metrics.taxaResolucao.trend}
          icon={MetricIconBadgeCheck}
        />
      </div>

      {/* Gráficos principais */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <Card className="bg-card border-border">
          <CardContent className="p-6">
            <h3 className="text-lg font-semibold text-foreground mb-4">Status das Conversas</h3>
            <ConversationsPieChart
              data={applyPieColors(
                [
                  { name: 'Em Atendimento', value: stats.conversas_abertas || 0 },
                  { name: 'Em Espera', value: stats.conversas_pendentes || 0 },
                  { name: isChatbotMode ? 'Na Automação' : 'Com a IA', value: stats.conversas_ia || 0 },
                  { name: 'Finalizadas', value: stats.conversas_resolvidas || 0 },
                ],
                PIE_STATUS_COLORS,
                Object.values(PIE_STATUS_COLORS)
              )}
            />
          </CardContent>
        </Card>

        <Card className="bg-card border-border">
          <CardContent className="p-6">
            <h3 className="text-lg font-semibold text-foreground mb-4">Canais de Atendimento</h3>
            <ConversationsPieChart
              data={(() => {
                // Definir todos os tipos de canais disponíveis
                const canaisAgrupados = {
                  telegram: { name: 'Telegram', value: 0 },
                  whatsapp: { name: 'WhatsApp', value: 0 },
                  email: { name: 'Email', value: 0 },
                  instagram: { name: 'Instagram', value: 0 },
                  app_mobile: { name: 'App Mobile', value: 0 },
                };

                // Preencher com valores reais
                (stats.canais || []).forEach(canal => {
                  let tipoNormalizado = canal.inbox__channel_type;
                  if (tipoNormalizado === 'whatsapp_session' || tipoNormalizado === 'whatsapp_oficial' || tipoNormalizado === 'whatsapp') {
                    tipoNormalizado = 'whatsapp';
                  }

                  if (canaisAgrupados[tipoNormalizado]) {
                    canaisAgrupados[tipoNormalizado].value += (canal.total || 0);
                  }
                });

                return applyPieColors(
                  Object.values(canaisAgrupados),
                  PIE_CHANNEL_COLORS,
                  Object.values(PIE_CHANNEL_COLORS)
                );
              })()}
            />
          </CardContent>
        </Card>

        <Card className="bg-card border-border">
          <CardContent className="p-6">
            <h3 className="text-lg font-semibold text-foreground mb-4">{automacaoTitulo}</h3>
            <ConversationsPieChart
              data={(() => {
                const porAutomacao = Number(stats.resolvidas_automacao_ia) || 0;
                const manual =
                  stats.resolvidas_encerrado_manual != null
                    ? Number(stats.resolvidas_encerrado_manual)
                    : Number(stats.resolvidas_demais_encerramentos) || 0;
                const resColors = {
                  [automacaoLegenda]: isChatbotMode
                    ? PIE_RESOLUTION_COLORS.chatbot
                    : PIE_RESOLUTION_COLORS.ia,
                  'Encerrado manualmente': PIE_RESOLUTION_COLORS.manual,
                };
                return applyPieColors(
                  [
                    { name: automacaoLegenda, value: porAutomacao },
                    { name: 'Encerrado manualmente', value: manual },
                  ],
                  resColors,
                  Object.values(PIE_RESOLUTION_COLORS)
                );
              })()}
            />
          </CardContent>
        </Card>
      </div>

      {/* Análise de Conversas */}
      <ConversationAnalysis provedorId={effectivePid} />

      {/* Fila de espera SLA e atividades */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="lg:col-span-2">
          <WaitingQueueSLA provedorId={effectivePid} />
        </div>
        <div>
          <RecentActivity provedorId={effectivePid} />
        </div>
      </div>


    </div>
  );
};

export default DashboardPrincipal;