import React, { useState, useEffect } from 'react';
import { Doughnut, Bar } from 'react-chartjs-2';
import {
  Chart as ChartJS,
  CategoryScale,
  LinearScale,
  BarElement,
  Title,
  Tooltip,
  Legend,
  ArcElement,
} from 'chart.js';
import { 
  Users,
  MessageCircle,
  Wifi,
  Globe
} from 'lucide-react';
import axios from 'axios';

ChartJS.register(
  CategoryScale,
  LinearScale,
  BarElement,
  Title,
  Tooltip,
  Legend,
  ArcElement
);

const DONUT_SLICE_COLORS = ['#ea580c', '#f97316', '#fb923c', '#fdba74', '#c2410c', '#57534e'];

export default function DashboardCharts() {
  const [statsData, setStatsData] = useState({
    totalProvedores: 0,
    totalCanais: 0,
    totalUsuarios: 0,
    totalConversas: 0,
    receitaMensal: 'R$ 0,00',
    provedoresAtivos: 0,
    provedoresInativos: 0,
    canaisPorProvedor: {},
    topProvedores: []
  });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  // Buscar dados reais do dashboard
  const fetchDashboardData = async () => {
    try {
      setLoading(true);
      // Priorizar auth_token que é o padrão salvo no Login, mas aceitar token também para compatibilidade
      const token = localStorage.getItem('auth_token') || localStorage.getItem('token');
      
      // Buscar provedores
      const provedoresRes = await axios.get('/api/provedores/', {
        headers: { Authorization: `Token ${token}` }
      });
      const provedores = provedoresRes.data.results || provedoresRes.data;
      
      // Buscar canais
      const canaisRes = await axios.get('/api/canais/', {
        headers: { Authorization: `Token ${token}` }
      });
      const canais = canaisRes.data.results || canaisRes.data;
      
      // Calcular estatísticas
      const totalUsuarios = provedores.reduce((sum, p) => sum + (p.users_count || 0), 0);
      const totalConversas = provedores.reduce((sum, p) => sum + (p.conversations_count || 0), 0);
      const provedoresAtivos = provedores.filter(p => p.is_active).length;
      const provedoresInativos = provedores.length - provedoresAtivos;
      
        // Calcular canais por provedor
  const canaisPorProvedor = {};
  canais.forEach(canal => {
    const provedorId = typeof canal.provedor === 'object' ? canal.provedor.id : canal.provedor;
    const provedor = provedores.find(p => p.id === provedorId);
    const nomeProvedor = provedor ? provedor.nome : 'Provedor Desconhecido';
    canaisPorProvedor[nomeProvedor] = (canaisPorProvedor[nomeProvedor] || 0) + 1;
  });
      
      // Top provedores por usuários - INCLUIR TODOS os provedores
      const topProvedores = provedores
        .sort((a, b) => (b.users_count || 0) - (a.users_count || 0))
        .slice(0, 10); // Aumentar limite para incluir mais provedores
      
      setStatsData({
        totalProvedores: provedores.length,
        totalCanais: canais.length,
        totalUsuarios: totalUsuarios,
        totalConversas: totalConversas,
        receitaMensal: 'R$ 0,00', // Placeholder - pode ser calculado baseado em planos
        provedoresAtivos,
        provedoresInativos,
        canaisPorProvedor,
        topProvedores
      });
      
    } catch (err) {
      setError('Erro ao carregar dados do dashboard');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchDashboardData();
  }, []);

  // Dados para gráficos
  const donutChartData = {
    labels: statsData.topProvedores.map(p => p.nome || 'Sem Nome'),
    datasets: [{
      data: statsData.topProvedores.map(p => p.users_count || 0),
      backgroundColor: statsData.topProvedores.map((_, i) => DONUT_SLICE_COLORS[i % DONUT_SLICE_COLORS.length]),
      borderWidth: 0,
    }]
  };

  // Opções para gráfico de usuários
  const donutChartOptionsUsuarios = {
    responsive: true,
    maintainAspectRatio: false,
    plugins: {
      legend: {
        position: 'bottom',
        labels: {
          color: '#E5E7EB',
          padding: 20,
          usePointStyle: true,
          font: {
            size: 12
          }
        }
      },
      tooltip: {
        backgroundColor: '#1F2937',
        titleColor: '#F9FAFB',
        bodyColor: '#E5E7EB',
        borderColor: '#374151',
        borderWidth: 1,
        callbacks: {
          title: function(context) {
            return context[0].label || 'Provedor';
          },
          label: function(context) {
            const value = context.parsed;
            const total = context.dataset.data.reduce((a, b) => a + b, 0);
            const percentage = total > 0 ? Math.round((value / total) * 100) : 0;
            return `${context.label}: ${value} usuários (${percentage}%)`;
          }
        }
      }
    }
  };
  
  // Opções para gráfico de conversas
  const donutChartOptionsConversas = {
    responsive: true,
    maintainAspectRatio: false,
    plugins: {
      legend: {
        position: 'bottom',
        labels: {
          color: '#E5E7EB',
          padding: 20,
          usePointStyle: true,
          font: {
            size: 12
          }
        }
      },
      tooltip: {
        backgroundColor: '#1F2937',
        titleColor: '#F9FAFB',
        bodyColor: '#E5E7EB',
        borderColor: '#374151',
        borderWidth: 1,
        callbacks: {
          title: function(context) {
            return context[0].label || 'Provedor';
          },
          label: function(context) {
            const value = context.parsed;
            const total = context.dataset.data.reduce((a, b) => a + b, 0);
            const percentage = total > 0 ? Math.round((value / total) * 100) : 0;
            return `${context.label}: ${value} conversas (${percentage}%)`;
          }
        }
      }
    }
  };

  const statusData = {
    labels: ['Ativos', 'Inativos'],
    datasets: [{
      label: 'Provedores',
      data: [statsData.provedoresAtivos, statsData.provedoresInativos],
      backgroundColor: ['#2E7D32', '#D32F2F'],
      borderWidth: 0,
      borderRadius: 8,
    }]
  };

  const statusOptions = {
    responsive: true,
    maintainAspectRatio: false,
    plugins: {
      legend: {
        display: false
      },
      tooltip: {
        backgroundColor: '#1F2937',
        titleColor: '#F9FAFB',
        bodyColor: '#E5E7EB',
        borderColor: '#374151',
        borderWidth: 1
      }
    },
    scales: {
      y: {
        beginAtZero: true,
        grid: {
          color: '#374151'
        },
        ticks: {
          color: '#9CA3AF'
        }
      },
      x: {
        grid: {
          display: false
        },
        ticks: {
          color: '#9CA3AF'
        }
      }
    }
  };

  const channelTypeData = {
    labels: Object.keys(statsData.canaisPorProvedor),
    datasets: [{
        label: 'Canais',
      data: Object.values(statsData.canaisPorProvedor),
      backgroundColor: [...DONUT_SLICE_COLORS],
      borderWidth: 0,
      borderRadius: 8,
    }]
  };

  const channelTypeOptions = {
    responsive: true,
    maintainAspectRatio: false,
    plugins: {
      legend: {
        display: false
      },
      tooltip: {
        backgroundColor: '#1F2937',
        titleColor: '#F9FAFB',
        bodyColor: '#E5E7EB',
        borderColor: '#374151',
        borderWidth: 1
      }
    },
    scales: {
      y: {
        beginAtZero: true,
        grid: {
          color: '#374151'
        },
        ticks: {
          color: '#9CA3AF'
        }
      },
      x: {
        grid: {
          display: false
        },
        ticks: {
          color: '#9CA3AF'
        }
      }
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="text-muted-foreground">Carregando dashboard...</div>
      </div>
    );
  }

  if (error) {
  return (
      <div className="flex items-center justify-center h-64">
        <div className="text-red-500">{error}</div>
      </div>
    );
  }

  return (
    <div className="space-y-8">
      {/* Gráficos */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Top Provedores por Usuários */}
        <div className="bg-card rounded-xl shadow-lg border border-border overflow-hidden">
          <div className="bg-gradient-to-r from-orange-900/20 to-amber-900/15 px-6 py-4 border-b border-border">
            <h3 className="text-lg font-semibold text-foreground flex items-center gap-2">
              <Users className="w-5 h-5 text-orange-400" />
              Provedores por Usuários
            </h3>
          </div>
          <div className="p-6">
            <div className="h-64">
              {statsData.topProvedores.length > 0 ? (
                <Doughnut data={donutChartData} options={donutChartOptionsUsuarios} />
              ) : (
                <div className="flex items-center justify-center h-full text-muted-foreground">
                  Nenhum dado disponível
                </div>
              )}
            </div>
          </div>
        </div>

        {/* Top Provedores por Conversas */}
        <div className="bg-card rounded-xl shadow-lg border border-border overflow-hidden">
          <div className="bg-gradient-to-r from-green-900/20 to-emerald-900/20 px-6 py-4 border-b border-border">
            <h3 className="text-lg font-semibold text-foreground flex items-center gap-2">
              <MessageCircle className="w-5 h-5 text-green-400" />
              Provedores por Conversas
            </h3>
          </div>
          <div className="p-6">
            <div className="h-64">
              {statsData.topProvedores.length > 0 ? (
                <Doughnut 
                  data={{
                    ...donutChartData,
                    datasets: [{
                      ...donutChartData.datasets[0],
                      data: statsData.topProvedores.map(p => p.conversations_count || 0),
                      backgroundColor: statsData.topProvedores.map((_, i) => DONUT_SLICE_COLORS[i % DONUT_SLICE_COLORS.length])
                    }]
                  }} 
                  options={donutChartOptionsConversas} 
                />
              ) : (
                <div className="flex items-center justify-center h-full text-muted-foreground">
                  Nenhum dado disponível
                </div>
              )}
            </div>
          </div>
        </div>
      </div>

      {/* Gráficos de Barras */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Status dos Provedores */}
        <div className="bg-card rounded-xl shadow-lg border border-border overflow-hidden">
          <div className="bg-gradient-to-r from-orange-900/25 to-amber-900/20 px-6 py-4 border-b border-border">
            <h3 className="text-lg font-semibold text-foreground flex items-center gap-2">
              <Wifi className="w-5 h-5 text-orange-400" />
              Status dos Provedores
            </h3>
          </div>
          <div className="p-6">
            <div className="h-64">
              <Bar data={statusData} options={statusOptions} />
            </div>
          </div>
        </div>

        {/* Canais por Provedor */}
        <div className="bg-card rounded-xl shadow-lg border border-border overflow-hidden">
          <div className="bg-gradient-to-r from-orange-900/20 to-red-900/20 px-6 py-4 border-b border-border">
            <h3 className="text-lg font-semibold text-foreground flex items-center gap-2">
              <Globe className="w-5 h-5 text-orange-400" />
              Canais por Provedor
            </h3>
          </div>
          <div className="p-6">
            <div className="h-64">
              {Object.keys(statsData.canaisPorProvedor).length > 0 ? (
                <Bar data={channelTypeData} options={channelTypeOptions} />
              ) : (
                <div className="flex items-center justify-center h-full text-muted-foreground">
                  Nenhum canal configurado
                </div>
              )}
        </div>
        </div>
        </div>
      </div>
    </div>
  );
} 

