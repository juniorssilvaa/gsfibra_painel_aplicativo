import React, { useState, useEffect } from 'react';
import { Card, CardContent } from "@/components/ui/card";
import { buildWebSocketUrl } from '../utils/websocketUrl';
import { buildApiPath } from '../utils/apiBaseUrl';
import {
  MessageCircle,
  Users,
  Clock,
  CheckCircle,
  TrendingUp,
  TrendingDown,
  Minus,
  Activity
} from 'lucide-react';
import axios from 'axios';
import MetricCard from './dashboard/MetricCard';
import ConversationsPieChart from './dashboard/ConversationsPieChart';
import ResponseTimeChart from './dashboard/ResponseTimeChart';
import ConversationAnalysis from './dashboard/ConversationAnalysis';

import AgentPerformanceTable from './dashboard/AgentPerformanceTable';
import RecentActivity from './dashboard/RecentActivity';
import { subscribeToCSAT, subscribeToAudit } from '../lib/supabase';

const DashboardPrincipal = ({ provedorId }) => {
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [stats, setStats] = useState({
    total_conversas: 0,
    conversas_abertas: 0,
    conversas_pendentes: 0,
    conversas_resolvidas: 0,
    conversas_em_andamento: 0,
    contatos_unicos: 0,
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
      try {
        setLoading(true);
        // Priorizar auth_token que é o padrão salvo no Login, mas aceitar token também para compatibilidade
        let token = localStorage.getItem('auth_token') || localStorage.getItem('token');

        if (!token) {
          console.error('Token não encontrado no localStorage');
          throw new Error('Token não encontrado. Faça login novamente.');
        }

        // Buscar estatísticas gerais da API real
        // Se provedorId estiver disponível, passar como parâmetro (para superadmin visualizar outros provedores)
        const statsUrl = provedorId
          ? buildApiPath(`/api/dashboard/stats/?provedor_id=${provedorId}`)
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
          console.warn('Erro ao buscar canais:', err);
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
          console.warn('Erro ao buscar tempo de resposta:', err);
        }

        setLoading(false);
      } catch (err) {
        console.error('Erro ao carregar dados do dashboard:', err);
        setError('Erro ao carregar dados do dashboard: ' + err.message);
        setLoading(false);
      }
    }

    // Executar sempre, mesmo sem provedorId (será obtido do usuário se necessário)
    fetchDashboardData();
  }, [provedorId]);

  // Buscar modo do provedor diretamente para evitar fallback incorreto no card
  useEffect(() => {
    const fetchProviderMode = async () => {
      if (!provedorId) return;
      try {
        const token = localStorage.getItem('auth_token') || localStorage.getItem('token');
        if (!token) return;
        const res = await axios.get(buildApiPath(`/api/provedores/${provedorId}/`), {
          headers: { Authorization: `Token ${token}` }
        });
        const mode = res.data?.bot_mode;
        if (mode === 'chatbot' || mode === 'ia') {
          setProviderBotMode(mode);
        }
      } catch (err) {
        console.warn('Erro ao buscar bot_mode do provedor:', err);
      }
    };
    fetchProviderMode();
  }, [provedorId]);

  // WebSocket para atualizações em tempo real
  useEffect(() => {
    if (!provedorId) return;

    const connectWebSocket = () => {
      // Priorizar auth_token que é o padrão salvo no Login, mas aceitar token também para compatibilidade
      const token = localStorage.getItem('auth_token') || localStorage.getItem('token');
      if (!token) return;

      const wsUrl = buildWebSocketUrl('/ws/conversas_dashboard/', { token });
      const websocket = new WebSocket(wsUrl);

      websocket.onopen = () => {
        console.log('WebSocket dashboard conectado');
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
        console.log('WebSocket dashboard desconectado');
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
  }, [provedorId]);

  // Atualizar dados a cada 30 segundos
  useEffect(() => {
    if (!provedorId) return;

    const interval = setInterval(async () => {
      try {
        // Priorizar auth_token que é o padrão salvo no Login, mas aceitar token também para compatibilidade
        const token = localStorage.getItem('auth_token') || localStorage.getItem('token');
        const statsUrl = provedorId
          ? buildApiPath(`/api/dashboard/stats/?provedor_id=${provedorId}`)
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
        console.error('Erro ao atualizar estatísticas:', error);
      }
    }, 30000); // 30 segundos

    return () => clearInterval(interval);
  }, [provedorId]);

  // useEffect para inicializar dados do Supabase (apenas para os 2 cards)
  useEffect(() => {
    if (provedorId) {
      fetchSupabaseStats();
      setupRealtimeSubscriptions();
    }
  }, [provedorId]);

  // Função para buscar dados de satisfação e taxa de resolução
  const fetchSupabaseStats = async () => {
    try {
      // Priorizar auth_token que é o padrão salvo no Login, mas aceitar token também para compatibilidade
      const token = localStorage.getItem('auth_token') || localStorage.getItem('token');

      // Buscar satisfação média e estatísticas do dashboard (que já tem conversas resolvidas)
      // Se provedorId estiver disponível, passar como parâmetro (para superadmin visualizar outros provedores)
      const csatStatsUrl = provedorId
        ? buildApiPath(`/api/csat/feedbacks/stats/?days=30&provedor_id=${provedorId}`)
        : buildApiPath('/api/csat/feedbacks/stats/?days=30');
      const dashboardStatsUrl = provedorId
        ? buildApiPath(`/api/dashboard/stats/?provedor_id=${provedorId}`)
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
      console.error('Erro ao buscar dados de satisfação e resolução:', error);
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
    subscribeToCSAT(provedorId, (payload) => {
      console.log('Nova avaliação CSAT recebida:', payload);
      fetchSupabaseStats();
    });

    // Subscription para Auditoria (Taxa de Resolução)
    subscribeToAudit(provedorId, (payload) => {
      console.log('Nova auditoria recebida:', payload);
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
      tempoResposta: {
        value: stats.tempo_primeira_resposta || '0min',
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
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-500"></div>
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
    <div className="w-full min-h-full space-y-6 p-6 bg-zinc-800/35">
      {/* Métricas principais */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        <MetricCard
          title="Conversas em Andamento"
          value={metrics.conversasAtivas.value}
          change={metrics.conversasAtivas.change}
          trend={metrics.conversasAtivas.trend}
          icon={MessageCircle}
        />
        <MetricCard
          title="Tempo de Primeira Resposta"
          value={metrics.tempoResposta.value}
          change={metrics.tempoResposta.change}
          trend={metrics.tempoResposta.trend}
          icon={Clock}
        />
        <MetricCard
          title="Satisfação Média"
          value={metrics.satisfacao.value}
          change={metrics.satisfacao.change}
          trend={metrics.satisfacao.trend}
          icon={TrendingUp}
        />
        <MetricCard
          title="Taxa de Resolução"
          value={metrics.taxaResolucao.value}
          change={metrics.taxaResolucao.change}
          trend={metrics.taxaResolucao.trend}
          icon={CheckCircle}
        />
      </div>

      {/* Gráficos principais */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <Card className="bg-card border-border">
          <CardContent className="p-6">
            <h3 className="text-lg font-semibold text-foreground mb-4">Status das Conversas</h3>
            <ConversationsPieChart
              data={[
                { name: 'Em Atendimento', value: stats.conversas_abertas || 0 },
                { name: 'Em Espera', value: stats.conversas_pendentes || 0 },
                { name: 'Na Automação', value: stats.conversas_ia || 0 },
                { name: 'Finalizadas', value: stats.conversas_resolvidas || 0 }
              ]}
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
                  'telegram': { name: 'Telegram', value: 0 },
                  'whatsapp': { name: 'WhatsApp', value: 0 },
                  'email': { name: 'Email', value: 0 },
                  'webchat': { name: 'Chat Web', value: 0 },
                  'instagram': { name: 'Instagram', value: 0 }
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

                return Object.values(canaisAgrupados);
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
                const demais =
                  stats.resolvidas_demais_encerramentos != null
                    ? Number(stats.resolvidas_demais_encerramentos)
                    : Math.max(0, (Number(stats.conversas_resolvidas) || 0) - porAutomacao);
                return [
                  { name: automacaoLegenda, value: porAutomacao },
                  { name: 'Demais encerramentos', value: demais }
                ];
              })()}
            />
          </CardContent>
        </Card>
      </div>

      {/* Análise de Conversas */}
      <ConversationAnalysis provedorId={provedorId} />

      {/* Tabelas e atividades */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="lg:col-span-2">
          <AgentPerformanceTable />
        </div>
        <div>
          <RecentActivity provedorId={provedorId} />
        </div>
      </div>


    </div>
  );
};

export default DashboardPrincipal;