import React, { useMemo, useState, useEffect } from 'react';
import { Doughnut, Pie } from 'react-chartjs-2';
import {
  Chart as ChartJS,
  ArcElement,
  Tooltip,
  Legend,
} from 'chart.js';
import axios from 'axios';
import { STATUS_PILL } from './DashboardOverviewPanels';

ChartJS.register(ArcElement, Tooltip, Legend);

const PIE_COLORS = [
  STATUS_PILL.ochre,
  STATUS_PILL.royal,
  STATUS_PILL.purple,
  STATUS_PILL.forest,
  STATUS_PILL.petrol,
  STATUS_PILL.burgundy,
  STATUS_PILL.gray,
  '#c2410c',
  '#ea580c',
  '#f97316',
];

const basePieOptions = {
  responsive: true,
  maintainAspectRatio: false,
  plugins: {
    legend: {
      position: 'bottom',
      labels: {
        color: '#a8a29e',
        padding: 14,
        usePointStyle: true,
        pointStyle: 'circle',
        font: { size: 11 },
      },
    },
    tooltip: {
      backgroundColor: '#27272a',
      titleColor: '#fafaf9',
      bodyColor: '#e7e5e4',
      borderColor: '#3f3f46',
      borderWidth: 1,
    },
  },
};

function ChartCard({ title, children }) {
  return (
    <div className="bg-card rounded-xl shadow-lg border border-border overflow-hidden">
      <div className="px-5 py-3.5 border-b border-border">
        <h3 className="text-sm font-semibold text-foreground">{title}</h3>
      </div>
      <div className="p-5">
        <div className="h-64">{children}</div>
      </div>
    </div>
  );
}

function EmptyState({ text }) {
  return (
    <div className="flex h-full items-center justify-center text-sm text-muted-foreground">
      {text}
    </div>
  );
}

export default function DashboardCharts() {
  const [statsData, setStatsData] = useState({
    provedoresAtivos: 0,
    provedoresInativos: 0,
    canaisPorProvedor: {},
    topProvedores: [],
  });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    const fetchDashboardData = async () => {
      try {
        setLoading(true);
        const token = localStorage.getItem('auth_token') || localStorage.getItem('token');

        const [provedoresRes, canaisRes] = await Promise.all([
          axios.get('/api/provedores/', { headers: { Authorization: `Token ${token}` } }),
          axios.get('/api/canais/', { headers: { Authorization: `Token ${token}` } }),
        ]);

        const provedores = provedoresRes.data.results || provedoresRes.data || [];
        const canais = canaisRes.data.results || canaisRes.data || [];

        const canaisPorProvedor = {};
        canais.forEach((canal) => {
          const provedorId = typeof canal.provedor === 'object' ? canal.provedor.id : canal.provedor;
          const provedor = provedores.find((p) => p.id === provedorId);
          const nomeProvedor = provedor ? provedor.nome : 'Provedor Desconhecido';
          canaisPorProvedor[nomeProvedor] = (canaisPorProvedor[nomeProvedor] || 0) + 1;
        });

        const topProvedores = [...provedores]
          .sort((a, b) => (b.users_count || 0) - (a.users_count || 0))
          .slice(0, 8);

        setStatsData({
          provedoresAtivos: provedores.filter((p) => p.is_active).length,
          provedoresInativos: provedores.filter((p) => !p.is_active).length,
          canaisPorProvedor,
          topProvedores,
        });
      } catch (err) {
        console.error('Erro ao buscar dados do dashboard:', err);
        setError('Erro ao carregar gráficos');
      } finally {
        setLoading(false);
      }
    };

    fetchDashboardData();
  }, []);

  const usersPie = useMemo(() => {
    const items = statsData.topProvedores.filter((p) => (p.users_count || 0) > 0);
    return {
      labels: items.map((p) => p.nome || 'Sem Nome'),
      datasets: [{
        data: items.map((p) => p.users_count || 0),
        backgroundColor: items.map((_, i) => PIE_COLORS[i % PIE_COLORS.length]),
        borderWidth: 2,
        borderColor: '#27272a',
      }],
    };
  }, [statsData.topProvedores]);

  const conversasPie = useMemo(() => {
    const items = [...statsData.topProvedores]
      .filter((p) => (p.conversations_count || 0) > 0)
      .sort((a, b) => (b.conversations_count || 0) - (a.conversations_count || 0))
      .slice(0, 8);
    return {
      labels: items.map((p) => p.nome || 'Sem Nome'),
      datasets: [{
        data: items.map((p) => p.conversations_count || 0),
        backgroundColor: items.map((_, i) => PIE_COLORS[i % PIE_COLORS.length]),
        borderWidth: 2,
        borderColor: '#27272a',
      }],
    };
  }, [statsData.topProvedores]);

  const statusPie = useMemo(() => ({
    labels: ['Ativos', 'Inativos'],
    datasets: [{
      data: [statsData.provedoresAtivos, statsData.provedoresInativos],
      backgroundColor: [STATUS_PILL.royal, STATUS_PILL.gray],
      borderWidth: 2,
      borderColor: '#27272a',
    }],
  }), [statsData.provedoresAtivos, statsData.provedoresInativos]);

  const canaisPie = useMemo(() => {
    const entries = Object.entries(statsData.canaisPorProvedor)
      .sort((a, b) => b[1] - a[1])
      .slice(0, 8);
    return {
      labels: entries.map(([nome]) => nome),
      datasets: [{
        data: entries.map(([, count]) => count),
        backgroundColor: entries.map((_, i) => PIE_COLORS[i % PIE_COLORS.length]),
        borderWidth: 2,
        borderColor: '#27272a',
      }],
    };
  }, [statsData.canaisPorProvedor]);

  const usersOptions = useMemo(() => ({
    ...basePieOptions,
    plugins: {
      ...basePieOptions.plugins,
      tooltip: {
        ...basePieOptions.plugins.tooltip,
        callbacks: {
          label: (ctx) => {
            const total = ctx.dataset.data.reduce((a, b) => a + b, 0) || 1;
            const value = ctx.parsed;
            const percentage = Math.round((value / total) * 100);
            return `${ctx.label}: ${value} usuários (${percentage}%)`;
          },
        },
      },
    },
  }), []);

  const conversasOptions = useMemo(() => ({
    ...basePieOptions,
    plugins: {
      ...basePieOptions.plugins,
      tooltip: {
        ...basePieOptions.plugins.tooltip,
        callbacks: {
          label: (ctx) => {
            const total = ctx.dataset.data.reduce((a, b) => a + b, 0) || 1;
            const value = ctx.parsed;
            const percentage = Math.round((value / total) * 100);
            return `${ctx.label}: ${value} conversas (${percentage}%)`;
          },
        },
      },
    },
  }), []);

  const statusOptions = useMemo(() => ({
    ...basePieOptions,
    plugins: {
      ...basePieOptions.plugins,
      tooltip: {
        ...basePieOptions.plugins.tooltip,
        callbacks: {
          label: (ctx) => {
            const total = ctx.dataset.data.reduce((a, b) => a + b, 0) || 1;
            const value = ctx.parsed;
            const percentage = Math.round((value / total) * 100);
            return `${ctx.label}: ${value} (${percentage}%)`;
          },
        },
      },
    },
  }), []);

  const canaisOptions = useMemo(() => ({
    ...basePieOptions,
    plugins: {
      ...basePieOptions.plugins,
      tooltip: {
        ...basePieOptions.plugins.tooltip,
        callbacks: {
          label: (ctx) => {
            const total = ctx.dataset.data.reduce((a, b) => a + b, 0) || 1;
            const value = ctx.parsed;
            const percentage = Math.round((value / total) * 100);
            return `${ctx.label}: ${value} canais (${percentage}%)`;
          },
        },
      },
    },
  }), []);

  if (loading) {
    return (
      <div className="flex items-center justify-center h-48 text-muted-foreground text-sm">
        Carregando gráficos…
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex items-center justify-center h-48 text-red-400 text-sm">{error}</div>
    );
  }

  const hasUsers = usersPie.datasets[0].data.some((v) => v > 0);
  const hasConversas = conversasPie.datasets[0].data.some((v) => v > 0);
  const hasStatus = statusPie.datasets[0].data.some((v) => v > 0);
  const hasCanais = canaisPie.datasets[0].data.length > 0;

  return (
    <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
      <ChartCard title="Provedores por usuários">
        {hasUsers ? (
          <Doughnut data={usersPie} options={usersOptions} />
        ) : (
          <EmptyState text="Nenhum usuário para exibir" />
        )}
      </ChartCard>

      <ChartCard title="Provedores por conversas">
        {hasConversas ? (
          <Doughnut data={conversasPie} options={conversasOptions} />
        ) : (
          <EmptyState text="Nenhuma conversa para exibir" />
        )}
      </ChartCard>

      <ChartCard title="Status dos provedores">
        {hasStatus ? (
          <Pie data={statusPie} options={statusOptions} />
        ) : (
          <EmptyState text="Nenhum provedor cadastrado" />
        )}
      </ChartCard>

      <ChartCard title="Canais por provedor">
        {hasCanais ? (
          <Pie data={canaisPie} options={canaisOptions} />
        ) : (
          <EmptyState text="Nenhum canal configurado" />
        )}
      </ChartCard>
    </div>
  );
}
