import React, { useState, useEffect } from 'react';
import { Chart as ChartJS, CategoryScale, LinearScale, PointElement, LineElement, Title, Tooltip, Legend, ArcElement, BarElement } from 'chart.js';
import { Line, Doughnut, Bar } from 'react-chartjs-2';
import { MessageCircle, TrendingUp, Users, ArrowLeft, Eye, X, User } from 'lucide-react';
import axios from 'axios';
import { useNavigate } from 'react-router-dom';
import { getMessages } from '../lib/supabase';

// Registrar componentes do Chart.js
ChartJS.register(
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  Title,
  Tooltip,
  Legend,
  ArcElement,
  BarElement,
);

const RATING_LABELS = {
  1: 'Muito insatisfeito',
  2: 'Insatisfeito',
  3: 'Neutro',
  4: 'Satisfeito',
  5: 'Muito satisfeito',
};

const CHANNEL_LABELS = {
  whatsapp: 'WhatsApp',
  whatsapp_oficial: 'WhatsApp',
  whatsapp_session: 'WhatsApp',
  telegram: 'Telegram',
  instagram: 'Instagram',
  web: 'Web Chat',
  email: 'Email',
};

export default function CSATDashboard({ provedorId }) {
  const navigate = useNavigate();
  // Estado para dados CSAT (sem mock data)
  const [csatData, setCsatData] = useState({
    total_feedbacks: 0,
    average_rating: 0,
    satisfaction_rate: 0,
    rating_distribution: [],
    channel_distribution: [],
    daily_stats: [],
    agent_ranking: [],
    recent_feedbacks: []
  });
  
  const [loading, setLoading] = useState(true);
  const [timeFilter, setTimeFilter] = useState(30);
  const [temporalTab, setTemporalTab] = useState('ranking'); // ranking | evolucao
  const [selectedConversationId, setSelectedConversationId] = useState(null);
  const [conversationDetails, setConversationDetails] = useState(null);
  const [conversationMessages, setConversationMessages] = useState([]);
  const [loadingConversation, setLoadingConversation] = useState(false);
  const [selectedFeedback, setSelectedFeedback] = useState(null);

  // Carregar dados do CSAT
  useEffect(() => {
    fetchCSATData();
  }, [timeFilter, provedorId]);

  const fetchCSATData = async () => {
    try {
      setLoading(true);
      const token = localStorage.getItem('token');
      const url = provedorId 
        ? `/api/csat/feedbacks/stats/?days=${timeFilter}&provedor_id=${provedorId}`
        : `/api/csat/feedbacks/stats/?days=${timeFilter}`;
      const response = await axios.get(url, {
        headers: { Authorization: `Token ${token}` }
      });
      // Garantir que todas as propriedades existam com valores padrão
      setCsatData({
        total_feedbacks: response.data?.total_feedbacks || 0,
        average_rating: response.data?.average_rating || 0,
        satisfaction_rate: response.data?.satisfaction_rate || 0,
        rating_distribution: Array.isArray(response.data?.rating_distribution) 
          ? response.data.rating_distribution 
          : [],
        channel_distribution: Array.isArray(response.data?.channel_distribution) 
          ? response.data.channel_distribution 
          : [],
        daily_stats: Array.isArray(response.data?.daily_stats) 
          ? response.data.daily_stats 
          : [],
        agent_ranking: Array.isArray(response.data?.agent_ranking)
          ? response.data.agent_ranking
          : [],
        recent_feedbacks: Array.isArray(response.data?.recent_feedbacks) 
          ? response.data.recent_feedbacks 
          : []
      });
    } catch (error) {
      // Manter dados vazios em caso de erro
      setCsatData({
        total_feedbacks: 0,
        average_rating: 0,
        satisfaction_rate: 0,
        rating_distribution: [],
        channel_distribution: [],
        daily_stats: [],
        agent_ranking: [],
        recent_feedbacks: []
      });
    } finally {
      setLoading(false);
    }
  };

  const openConversationModal = async (feedback) => {
    const conversationId = feedback.conversation_id || feedback.conversation;
    if (!conversationId) return;
    setSelectedFeedback(feedback);
    setSelectedConversationId(conversationId);
    setLoadingConversation(true);
    setConversationDetails(null);
    setConversationMessages([]);
    document.body.style.overflow = 'hidden';

    try {
      const token = localStorage.getItem('token');
      let details = null;
      try {
        const response = await axios.get(`/api/conversations/${conversationId}/?for_audit=1`, {
          headers: { Authorization: `Token ${token}` },
        });
        details = response.data;
      } catch (err) {
      }

      setConversationDetails(details || {
        id: conversationId,
        contact: { name: feedback.contact_name },
        inbox: { channel_type: feedback.channel_type },
      });

      let messages = details?.messages || [];
      if (!messages.length) {
        try {
          const apiMessages = await axios.get(
            `/api/messages/?conversation=${conversationId}&for_audit=1`,
            { headers: { Authorization: `Token ${token}` } }
          );
          messages = apiMessages.data.results || apiMessages.data || [];
        } catch (_) {
          /* fallback supabase abaixo */
        }
      }
      if ((!messages || !messages.length) && provedorId) {
        try {
          messages = await getMessages(conversationId, provedorId);
        } catch (_) {
          messages = [];
        }
      }
      setConversationMessages(Array.isArray(messages) ? messages : []);
    } finally {
      setLoadingConversation(false);
    }
  };

  const closeConversationModal = () => {
    setSelectedConversationId(null);
    setSelectedFeedback(null);
    setConversationDetails(null);
    setConversationMessages([]);
    document.body.style.overflow = '';
  };

  const ratingBadgeClass = (value) => {
    if (value === 1) return 'bg-[#EF4444]';
    if (value === 2) return 'bg-[#F97316]';
    if (value === 3) return 'bg-[#FACC15] text-gray-900';
    if (value === 4) return 'bg-[#22C55E]';
    return 'bg-[#22D3EE] text-gray-900';
  };

  // Configuração do gráfico de rosca (Distribuição das Avaliações)
  // Mapear os dados do backend para garantir ordem correta (rating 1-5)
  const ratingOrder = [1, 2, 3, 4, 5]; // Ordem fixa dos ratings
  const ratingColors = {
    1: '#EF4444', // Vermelho para 😡 Muito insatisfeito
    2: '#F97316', // Laranja/âmbar para 😕 Insatisfeito
    3: '#FACC15', // Amarelo para 😐 Neutro
    4: '#22C55E', // Verde para 🙂 Satisfeito
    5: '#22D3EE', // Azul/ciano premium para 🤩 Muito satisfeito
  };
  const ratingLabels = {
    1: '😡 Muito insatisfeito',
    2: '😕 Insatisfeito',
    3: '😐 Neutro',
    4: '🙂 Satisfeito',
    5: '🤩 Muito satisfeito',
  };

  // Criar um mapa dos dados do backend por rating_value
  const distributionMap = {};
  (csatData.rating_distribution || []).forEach(item => {
    const rating = item.rating_value || item.emoji_rating;
    // Se rating for emoji, converter para número
    const emojiToNumber = { '😡': 1, '😕': 2, '😐': 3, '🙂': 4, '🤩': 5 };
    const ratingValue = typeof rating === 'string' && emojiToNumber[rating] ? emojiToNumber[rating] : rating;
    if (ratingValue >= 1 && ratingValue <= 5) {
      distributionMap[ratingValue] = item.count || 0;
    }
  });

  // Garantir que os dados estejam na ordem correta (1-5)
  const chartData = ratingOrder.map(rating => distributionMap[rating] || 0);
  const chartLabels = ratingOrder.map(rating => ratingLabels[rating]);
  const chartColors = ratingOrder.map(rating => ratingColors[rating]);

  const doughnutData = {
    labels: chartLabels,
    datasets: [
      {
        data: chartData,
        backgroundColor: chartColors,
        borderWidth: 0,
      },
    ],
  };

  const doughnutOptions = {
    responsive: true,
    maintainAspectRatio: false,
    plugins: {
      legend: {
        position: 'bottom',
        labels: {
          padding: 20,
          usePointStyle: true,
          pointStyle: 'circle',
          color: '#E5E7EB', // Cor do texto da legenda
          font: {
            size: 12,
          },
        },
      },
    },
  };

  // Configuração do gráfico de linha (Evolução Temporal)
  const lineData = {
    labels: (csatData.daily_stats || []).map(item => {
      const date = new Date(item.day);
      return `${date.getDate().toString().padStart(2, '0')}/${(date.getMonth() + 1).toString().padStart(2, '0')}`;
    }),
    datasets: [
      {
        label: 'Satisfação Média',
        data: (csatData.daily_stats || []).map(item => item.avg_rating || 0),
        borderColor: '#10b981',
        backgroundColor: 'rgba(16, 185, 129, 0.1)',
        tension: 0.4,
        fill: true,
        borderWidth: 2,
        pointRadius: 3,
        pointHoverRadius: 5,
        pointBackgroundColor: '#10b981',
        pointBorderColor: '#10b981',
        pointBorderWidth: 0,
      },
    ],
  };

  const lineOptions = {
    responsive: true,
    maintainAspectRatio: false,
    plugins: {
      legend: {
        display: false,
      },
      tooltip: {
        mode: 'index',
        intersect: false,
        backgroundColor: 'rgba(0, 0, 0, 0.8)',
        titleColor: '#ffffff',
        bodyColor: '#ffffff',
        borderColor: '#10b981',
        borderWidth: 1,
        cornerRadius: 6,
        callbacks: {
          label: function(context) {
            return `Satisfação: ${context.parsed.y.toFixed(1)}/5.0`;
          }
        }
      },
    },
    scales: {
      y: {
        beginAtZero: true,
        max: 5,
        ticks: {
          stepSize: 1,
          color: '#9CA3AF',
        },
        grid: {
          color: 'rgba(156, 163, 175, 0.15)',
        },
      },
      x: {
        ticks: {
          color: '#9CA3AF',
          maxRotation: 0,
          autoSkip: true,
          maxTicksLimit: 8,
        },
        grid: {
          display: false,
        },
      }
    },
    interaction: {
      mode: 'index',
      intersect: false,
    },
    elements: {
      line: {
        tension: 0.4
      }
    }
  };

  const rankingSlice = (csatData.agent_ranking || []).slice(0, 8);
  const rankingMedals = ['🥇', '🥈', '🥉'];
  const rankingBarData = {
    labels: rankingSlice.map((a) => a.name),
    datasets: [
      {
        label: 'Nota média',
        data: rankingSlice.map((a) => a.avg_rating),
        backgroundColor: rankingSlice.map((_, i) => {
          if (i === 0) return '#FBBF24';
          if (i === 1) return '#94A3B8';
          if (i === 2) return '#D97706';
          return '#22C55E';
        }),
        borderRadius: 8,
        borderSkipped: false,
        maxBarThickness: 42,
      },
    ],
  };

  const rankingMedalPlugin = {
    id: 'rankingMedal',
    afterDatasetsDraw(chart) {
      const meta = chart.getDatasetMeta(0);
      if (!meta?.data?.length) return;
      const { ctx } = chart;
      meta.data.forEach((bar, index) => {
        if (index > 2) return;
        const { x, y } = bar.getProps(['x', 'y'], true);
        const value = rankingSlice[index]?.avg_rating;
        ctx.save();
        ctx.textAlign = 'center';
        ctx.textBaseline = 'bottom';
        ctx.font = '18px "Segoe UI Emoji", "Apple Color Emoji", sans-serif';
        ctx.fillText(rankingMedals[index], x, y - 18);
        if (value != null) {
          ctx.font = '600 11px Inter, system-ui, sans-serif';
          ctx.fillStyle = '#E5E7EB';
          ctx.fillText(Number(value).toFixed(1), x, y - 4);
        }
        ctx.restore();
      });
    },
  };

  const rankingBarOptions = {
    responsive: true,
    maintainAspectRatio: false,
    layout: {
      padding: { top: 36 },
    },
    plugins: {
      legend: { display: false },
      tooltip: {
        backgroundColor: 'rgba(0, 0, 0, 0.85)',
        callbacks: {
          label: (ctx) => {
            const item = rankingSlice[ctx.dataIndex];
            const avg = Number(ctx.parsed.y || 0).toFixed(1);
            const n = item?.total_feedbacks || 0;
            return `Média ${avg}/5 · ${n} avaliação${n === 1 ? '' : 'ões'}`;
          },
        },
      },
    },
    scales: {
      y: {
        beginAtZero: true,
        max: 5,
        ticks: { stepSize: 1, color: '#9CA3AF' },
        grid: { color: 'rgba(156, 163, 175, 0.12)' },
      },
      x: {
        ticks: {
          color: '#E5E7EB',
          font: { size: 11 },
          maxRotation: 25,
          minRotation: 0,
          autoSkip: true,
        },
        grid: { display: false },
      },
    },
  };

  const hasRanking = rankingSlice.length > 0;
  const hasDaily = (csatData.daily_stats || []).length > 0;
  const hasTemporalData = hasRanking || hasDaily;

  // Configuração do gráfico de barras (Canais)
  const barData = {
    labels: (csatData.channel_distribution || []).map(item => {
      const channelNames = {
        'whatsapp': 'WhatsApp',
        'telegram': 'Telegram',
        'web': 'Web Chat',
        'email': 'Email'
      };
      return channelNames[item.channel_type] || item.channel_type || 'Desconhecido';
    }),
    datasets: [
      {
        label: 'Feedbacks por canal',
        data: (csatData.channel_distribution || []).map(item => item.count || 0),
        backgroundColor: [
          '#22c55e', // Verde para WhatsApp
          '#3b82f6', // Azul para Telegram
          '#8b5cf6', // Roxo para Web
          '#f59e0b', // Laranja para Email
        ],
        borderRadius: 4,
      },
    ],
  };

  const barOptions = {
    responsive: true,
    maintainAspectRatio: false,
    plugins: {
      legend: {
        display: false,
      },
    },
    scales: {
      y: {
        beginAtZero: true,
        ticks: {
          stepSize: 1,
        },
      },
    },
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

  return (
    <div className="flex-1 p-6 bg-background overflow-y-auto relative">
      <div className="max-w-7xl mx-auto">
        {/* Header */}
        <button
          type="button"
          onClick={() => navigate(`/app/accounts/${provedorId}/csat`)}
          className="absolute left-0 top-0 px-4 py-2 rounded-lg bg-primary text-primary-foreground hover:opacity-90 transition-opacity inline-flex items-center gap-2"
        >
          <ArrowLeft className="w-4 h-4" />
          Voltar
        </button>

        <div className="mb-6 pt-14">
          <h1 className="text-3xl font-bold text-foreground mb-2">CSAT - Satisfação do Cliente</h1>
          <p className="text-muted-foreground">
            Acompanhe a satisfação dos seus clientes através das avaliações coletadas automaticamente.
          </p>
        </div>

        {/* Filtro de Período */}
        <div className="mb-6">
          <select
            value={timeFilter}
            onChange={(e) => setTimeFilter(parseInt(e.target.value))}
            className="px-4 py-2 border border-border rounded-lg bg-background text-foreground focus:outline-none focus:ring-2 focus:ring-blue-500"
          >
            <option value={7}>Últimos 7 dias</option>
            <option value={30}>Últimos 30 dias</option>
            <option value={90}>Últimos 90 dias</option>
          </select>
        </div>

        {/* Cards de Métricas */}
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-8 mb-8">
          {/* Satisfação Média */}
          <div className="bg-card p-6 rounded-lg border border-border">
            <div className="flex items-center gap-3 mb-2">
              <span className="text-lg">😊</span>
              <span className="text-sm font-medium text-muted-foreground">Satisfação Média</span>
            </div>
            <div className="text-3xl font-bold text-foreground">
              {csatData.average_rating}
            </div>
            <div className="text-sm text-muted-foreground">
              de 5.0 pontos
            </div>
          </div>

          {/* Total Avaliações */}
          <div className="bg-card p-6 rounded-lg border border-border">
            <div className="flex items-center gap-3 mb-2">
              <MessageCircle className="w-5 h-5 text-blue-500" />
              <span className="text-sm font-medium text-muted-foreground">Total de Avaliações</span>
            </div>
            <div className="text-3xl font-bold text-foreground">
              {csatData.total_feedbacks}
            </div>
            <div className="text-sm text-muted-foreground">
              nos últimos {timeFilter} dias
            </div>
          </div>

          {/* Taxa de Satisfação */}
          <div className="bg-card p-6 rounded-lg border border-border">
            <div className="flex items-center gap-3 mb-2">
              <TrendingUp className="w-5 h-5 text-green-500" />
              <span className="text-sm font-medium text-muted-foreground">Taxa de Satisfação</span>
            </div>
            <div className="text-3xl font-bold text-foreground">
              {csatData.satisfaction_rate}%
            </div>
            <div className="text-sm text-muted-foreground">
              clientes satisfeitos
            </div>
          </div>
        </div>

        {/* Gráficos */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-8 mb-8">
          {/* Distribuição das Avaliações */}
          <div className="bg-card p-6 rounded-lg border border-border">
            <h3 className="text-lg font-semibold mb-4 text-foreground">Distribuição das Avaliações</h3>
            <div className="h-80">
              {loading ? (
                <div className="flex items-center justify-center h-full">
                  <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600"></div>
                </div>
              ) : csatData.rating_distribution.length > 0 ? (
                <Doughnut data={doughnutData} options={doughnutOptions} />
              ) : (
                <div className="flex items-center justify-center h-full text-muted-foreground">
                  <div className="text-center">
                    <MessageCircle className="w-12 h-12 mx-auto mb-3 text-muted-foreground/50" />
                    <p>Nenhuma avaliação encontrada</p>
                  </div>
                </div>
              )}
            </div>
          </div>

          {/* Ranking e Evolução dos Atendentes */}
          <div className="bg-card p-6 rounded-lg border border-border">
            <div className="flex items-center justify-between gap-3 mb-4 flex-wrap">
              <h3 className="text-lg font-semibold text-foreground">Evolução dos Atendentes</h3>
              {hasTemporalData && (
                <div className="flex rounded-lg border border-border overflow-hidden text-xs">
                  <button
                    type="button"
                    onClick={() => setTemporalTab('ranking')}
                    className={`px-3 py-1.5 transition-colors ${
                      temporalTab === 'ranking'
                        ? 'bg-primary text-primary-foreground'
                        : 'bg-background text-muted-foreground hover:text-foreground'
                    }`}
                  >
                    Ranking
                  </button>
                  <button
                    type="button"
                    onClick={() => setTemporalTab('evolucao')}
                    className={`px-3 py-1.5 transition-colors ${
                      temporalTab === 'evolucao'
                        ? 'bg-primary text-primary-foreground'
                        : 'bg-background text-muted-foreground hover:text-foreground'
                    }`}
                  >
                    Evolução
                  </button>
                </div>
              )}
            </div>
            <div className="h-80">
              {loading ? (
                <div className="flex items-center justify-center h-full">
                  <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600"></div>
                </div>
              ) : !hasTemporalData ? (
                <div className="flex items-center justify-center h-full text-muted-foreground">
                  <div className="text-center">
                    <TrendingUp className="w-12 h-12 mx-auto mb-3 text-muted-foreground/50" />
                    <p>Nenhum dado de atendente encontrado</p>
                    <p className="text-sm mt-1">As avaliações CSAT por atendente aparecerão aqui.</p>
                  </div>
                </div>
              ) : temporalTab === 'ranking' && hasRanking ? (
                <div className="h-full">
                  <Bar
                    data={rankingBarData}
                    options={rankingBarOptions}
                    plugins={[rankingMedalPlugin]}
                  />
                </div>
              ) : temporalTab === 'ranking' && !hasRanking && hasDaily ? (
                <Line data={lineData} options={lineOptions} />
              ) : hasDaily ? (
                <Line data={lineData} options={lineOptions} />
              ) : hasRanking ? (
                <Bar
                  data={rankingBarData}
                  options={rankingBarOptions}
                  plugins={[rankingMedalPlugin]}
                />
              ) : null}
            </div>
          </div>
        </div>

        {/* Feedbacks por Canal */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-8 mb-8">
          <div className="bg-card p-6 rounded-lg border border-border">
            <h3 className="text-lg font-semibold mb-4 text-foreground">Feedbacks por Canal</h3>
            <div className="h-80">
              {loading ? (
                <div className="flex items-center justify-center h-full">
                  <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600"></div>
                </div>
              ) : csatData.channel_distribution.length > 0 ? (
                <Bar data={barData} options={barOptions} />
              ) : (
                <div className="flex items-center justify-center h-full text-muted-foreground">
                  <div className="text-center">
                    <Users className="w-12 h-12 mx-auto mb-3 text-muted-foreground/50" />
                    <p>Nenhum dado de canal encontrado</p>
                  </div>
                </div>
              )}
            </div>
          </div>

          {/* Últimos Feedbacks */}
          <div className="bg-card p-6 rounded-lg border border-border">
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-lg font-semibold text-foreground">Últimos Feedbacks</h3>
              {csatData.recent_feedbacks && csatData.recent_feedbacks.length > 3 && (
                <span className="text-xs text-muted-foreground bg-muted px-2 py-1 rounded">
                  {csatData.recent_feedbacks.length} feedbacks • Role para ver mais
                </span>
              )}
            </div>
            <div className="space-y-3 max-h-80 overflow-y-auto pr-2" style={{
              scrollbarWidth: 'thin',
              scrollbarColor: '#9CA3AF #E5E7EB'
            }}>
              {loading ? (
                <div className="flex items-center justify-center h-32">
                  <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600"></div>
                </div>
              ) : (csatData.recent_feedbacks && Array.isArray(csatData.recent_feedbacks) && csatData.recent_feedbacks.length > 0) ? (
                (csatData.recent_feedbacks || []).map((feedback, index) => {
                  const rating = Number(feedback.rating_value) || 0;
                  const emoji = feedback.emoji_rating || '😐';
                  const channelLabel = CHANNEL_LABELS[feedback.channel_type] || feedback.channel_type || 'Canal';
                  return (
                  <div key={feedback.id || index} className="flex items-start gap-3 p-4 bg-background rounded border border-border">
                    <div className="flex-shrink-0">
                      {feedback.contact_photo ? (
                        <img 
                          src={feedback.contact_photo} 
                          alt={feedback.contact_name}
                          className="w-10 h-10 rounded-full object-cover"
                        />
                      ) : (
                        <div className="w-10 h-10 rounded-full bg-gray-500 flex items-center justify-center">
                          <span className="text-white text-sm font-medium">
                            {(feedback.contact_name || 'C').charAt(0).toUpperCase()}
                          </span>
                        </div>
                      )}
                    </div>
                    
                    <div className="flex-1 min-w-0">
                      <div className="flex items-start justify-between gap-3 mb-2">
                        <div className="min-w-0">
                          <div className="font-medium text-foreground truncate">
                            {feedback.contact_name || 'Cliente'}
                          </div>
                          <div className="text-sm text-muted-foreground flex items-center gap-1.5 mt-0.5">
                            <User className="w-3.5 h-3.5 shrink-0" />
                            <span className="truncate">
                              Atendente: {feedback.agent_name || 'Não identificado'}
                            </span>
                          </div>
                          <div className="text-xs text-muted-foreground mt-1">
                            #{feedback.conversation_id || feedback.conversation} · {channelLabel}
                            {feedback.feedback_sent_at
                              ? ` · ${new Date(feedback.feedback_sent_at).toLocaleString('pt-BR')}`
                              : ''}
                          </div>
                        </div>
                        <div className="flex flex-col items-end gap-1 shrink-0">
                          <div className="flex items-center gap-2">
                            <span className="text-2xl leading-none" title={RATING_LABELS[rating] || ''}>
                              {emoji}
                            </span>
                            <span className={`px-2.5 py-1 text-sm font-semibold text-white rounded-full ${ratingBadgeClass(rating)}`}>
                              {rating}/5
                            </span>
                          </div>
                          <span className="text-[11px] text-muted-foreground">
                            {RATING_LABELS[rating] || 'Avaliação'}
                          </span>
                        </div>
                      </div>
                      {feedback.original_message && feedback.original_message !== 'Sem mensagem' && (
                        <div className="text-sm text-muted-foreground bg-muted/50 p-2 rounded mb-2 line-clamp-2">
                          {`"${feedback.original_message}"`}
                        </div>
                      )}
                      <button
                        type="button"
                        onClick={() => openConversationModal(feedback)}
                        disabled={!feedback.conversation_id && !feedback.conversation}
                        className="inline-flex items-center gap-1.5 text-xs font-medium px-3 py-1.5 rounded-md bg-primary text-primary-foreground hover:opacity-90 disabled:opacity-50 disabled:cursor-not-allowed"
                      >
                        <Eye className="w-3.5 h-3.5" />
                        Ver conversa
                      </button>
                    </div>
                  </div>
                  );
                })
              ) : (
                <div className="flex items-center justify-center h-32 text-muted-foreground">
                  <div className="text-center">
                    <MessageCircle className="w-12 h-12 mx-auto mb-3 text-muted-foreground/50" />
                    <p>Nenhum feedback recente encontrado</p>
                    <p className="text-sm">Os feedbacks dos clientes aparecerão aqui quando coletados.</p>
                  </div>
                </div>
              )}
            </div>
          </div>
        </div>
      </div>

      {/* Modal ver conversa completa */}
      {selectedConversationId && (
        <div
          className="fixed inset-0 bg-black/50 flex items-center justify-center z-[100] p-4"
          onClick={closeConversationModal}
        >
          <div
            className="bg-background rounded-lg shadow-xl max-w-3xl w-full max-h-[90vh] overflow-hidden flex flex-col border border-border"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-center justify-between p-4 border-b border-border shrink-0">
              <div>
                <h2 className="text-lg font-semibold text-foreground flex items-center gap-2">
                  <MessageCircle className="w-5 h-5" />
                  Conversa #{selectedConversationId}
                </h2>
                <p className="text-sm text-muted-foreground mt-0.5">
                  {selectedFeedback?.contact_name || conversationDetails?.contact?.name || 'Cliente'}
                  {selectedFeedback?.agent_name ? ` · Atendente: ${selectedFeedback.agent_name}` : ''}
                </p>
              </div>
              <button
                type="button"
                onClick={closeConversationModal}
                className="p-2 hover:bg-muted rounded-lg transition-colors"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            {selectedFeedback && (
              <div className="px-4 py-3 border-b border-border bg-muted/30 flex flex-wrap items-center gap-3 text-sm shrink-0">
                <span className="text-2xl">{selectedFeedback.emoji_rating}</span>
                <span className={`px-2 py-0.5 text-xs font-semibold text-white rounded-full ${ratingBadgeClass(Number(selectedFeedback.rating_value) || 0)}`}>
                  Nota {selectedFeedback.rating_value}/5
                </span>
                <span className="text-muted-foreground">
                  {RATING_LABELS[Number(selectedFeedback.rating_value)] || ''}
                </span>
                <span className="text-muted-foreground ml-auto">
                  {CHANNEL_LABELS[selectedFeedback.channel_type] || selectedFeedback.channel_type}
                </span>
              </div>
            )}

            <div className="flex-1 overflow-y-auto p-4 min-h-0">
              {loadingConversation ? (
                <div className="flex items-center justify-center py-16">
                  <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600" />
                </div>
              ) : conversationMessages.length > 0 ? (
                <div className="space-y-3">
                  {conversationMessages.map((message, index) => {
                    const isCustomer = message.is_from_customer === true;
                    const content = message.content || message.text || message.body || '';
                    const createdAt = message.created_at || message.timestamp;
                    return (
                      <div
                        key={message.id || index}
                        className={`flex ${isCustomer ? 'justify-start' : 'justify-end'}`}
                      >
                        <div
                          className={`max-w-[85%] rounded-2xl px-3 py-2 text-sm shadow-sm ${
                            isCustomer
                              ? 'bg-muted text-foreground'
                              : 'bg-blue-600 text-white'
                          }`}
                        >
                          <div className={`text-[11px] mb-1 font-medium ${isCustomer ? 'text-muted-foreground' : 'text-blue-100'}`}>
                            {isCustomer
                              ? (selectedFeedback?.contact_name || 'Cliente')
                              : (selectedFeedback?.agent_name || 'Atendente / Sistema')}
                          </div>
                          <div className="whitespace-pre-wrap break-words">
                            {content || (message.message_type ? `[${message.message_type}]` : '—')}
                          </div>
                          {createdAt && (
                            <div className={`text-[10px] mt-1 ${isCustomer ? 'text-muted-foreground' : 'text-blue-100'}`}>
                              {new Date(createdAt).toLocaleString('pt-BR')}
                            </div>
                          )}
                        </div>
                      </div>
                    );
                  })}
                </div>
              ) : (
                <div className="text-center py-16 text-muted-foreground">
                  <MessageCircle className="w-10 h-10 mx-auto mb-3 opacity-40" />
                  <p>Nenhuma mensagem encontrada para esta conversa.</p>
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}