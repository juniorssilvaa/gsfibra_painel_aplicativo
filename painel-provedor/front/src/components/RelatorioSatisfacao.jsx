import React, { useCallback, useEffect, useMemo, useState } from 'react';
import axios from 'axios';
import { format, startOfDay, subDays } from 'date-fns';
import {
  Chart as ChartJS,
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  BarElement,
  ArcElement,
  Filler,
  Tooltip,
  Legend,
} from 'chart.js';
import { Line, Bar, Doughnut } from 'react-chartjs-2';
import { Filter, Plus, Search } from 'lucide-react';
import { buildApiPath } from '../utils/apiBaseUrl';
import RelatorioStatStrip, { formatStatInt } from './RelatorioStatStrip';
import RelatorioSatisfacaoFeedbacks from './RelatorioSatisfacaoFeedbacks';

ChartJS.register(
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  BarElement,
  ArcElement,
  Filler,
  Tooltip,
  Legend,
);

const RATING_COLORS = {
  1: '#ef4444',
  2: '#f43f5e',
  3: '#f59e0b',
  4: '#84cc16',
  5: '#22c55e',
  0: '#22d3ee',
};

const AGENT_COLORS = [
  '#22c55e',
  '#2dd4bf',
  '#0d9488',
  '#38bdf8',
  '#a78bfa',
  '#f59e0b',
  '#fb7185',
  '#94a3b8',
];

function defaultRange() {
  const to = startOfDay(new Date());
  return { from: subDays(to, 6), to };
}

function toInputDate(value) {
  try {
    return format(value, 'yyyy-MM-dd');
  } catch {
    return '';
  }
}

function parseInputDate(value) {
  if (!value) return null;
  const [y, m, d] = value.split('-').map(Number);
  if (!y || !m || !d) return null;
  return startOfDay(new Date(y, m - 1, d));
}

function pct(part, total) {
  if (!total) return 0;
  return Math.round((Number(part) / Number(total)) * 10000) / 100;
}

function formatPct(value) {
  return `${Number(value || 0).toFixed(2).replace('.', ',')}%`;
}

const percentLabelsPlugin = {
  id: 'relatorioPercentLabels',
  afterDatasetsDraw(chart) {
    const { ctx } = chart;
    ctx.save();
    chart.data.datasets.forEach((dataset, di) => {
      const meta = chart.getDatasetMeta(di);
      if (!meta || meta.hidden) return;
      meta.data.forEach((el, i) => {
        const raw = Number(dataset.data[i] || 0);
        if (raw < 7) return;
        const props = el.getProps(['x', 'y', 'base'], true);
        const x = props.x;
        const y = (props.y + props.base) / 2;
        ctx.fillStyle = '#f8fafc';
        ctx.font = '600 10px Inter, system-ui, sans-serif';
        ctx.textAlign = 'center';
        ctx.textBaseline = 'middle';
        ctx.fillText(formatPct(raw), x, y);
      });
    });
    ctx.restore();
  },
};

export default function RelatorioSatisfacao({ provedorId }) {
  const initial = defaultRange();
  const [fromDate, setFromDate] = useState(toInputDate(initial.from));
  const [toDate, setToDate] = useState(toInputDate(initial.to));
  const [appliedFrom, setAppliedFrom] = useState(fromDate);
  const [appliedTo, setAppliedTo] = useState(toDate);
  const [filterOpen, setFilterOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [data, setData] = useState({
    total_feedbacks: 0,
    average_rating: 0,
    satisfaction_rate: 0,
    question: '',
    daily: [],
    rating_labels: [],
    by_agent: [],
    recent_feedbacks: [],
  });
  const [hiddenAgents, setHiddenAgents] = useState([]);

  const fetchReport = useCallback(async (start, end) => {
    if (!start || !end) return;
    try {
      setLoading(true);
      setError('');
      const token = localStorage.getItem('auth_token') || localStorage.getItem('token');
      if (!token) throw new Error('Faça login novamente.');
      const qs = new URLSearchParams({ start_date: start, end_date: end });
      if (provedorId) qs.set('provedor_id', String(provedorId));
      const res = await axios.get(buildApiPath(`/api/relatorios/satisfacao/?${qs}`), {
        headers: { Authorization: `Token ${token}` },
      });
      setData({
        total_feedbacks: res.data?.total_feedbacks || 0,
        average_rating: res.data?.average_rating || 0,
        satisfaction_rate: res.data?.satisfaction_rate || 0,
        question: res.data?.question || '',
        daily: res.data?.daily || [],
        rating_labels: res.data?.rating_labels || [],
        by_agent: res.data?.by_agent || [],
        recent_feedbacks: res.data?.recent_feedbacks || [],
      });
      setHiddenAgents([]);
    } catch (err) {
      setError(err.response?.data?.error || 'Não foi possível carregar a pesquisa de satisfação.');
      setData({
        total_feedbacks: 0,
        average_rating: 0,
        satisfaction_rate: 0,
        question: '',
        daily: [],
        rating_labels: [],
        by_agent: [],
        recent_feedbacks: [],
      });
    } finally {
      setLoading(false);
    }
  }, [provedorId]);

  useEffect(() => {
    fetchReport(appliedFrom, appliedTo);
  }, [appliedFrom, appliedTo, fetchReport]);

  const onSearch = () => {
    const from = parseInputDate(fromDate);
    const to = parseInputDate(toDate);
    if (!from || !to || from > to) {
      setError('Informe um período válido.');
      return;
    }
    setAppliedFrom(fromDate);
    setAppliedTo(toDate);
  };

  const agents = useMemo(
    () => (data.by_agent || []).map((agent, index) => ({
      ...agent,
      color: AGENT_COLORS[index % AGENT_COLORS.length],
    })),
    [data.by_agent],
  );

  const visibleAgents = useMemo(
    () => agents.filter((a) => !hiddenAgents.includes(a.name)),
    [agents, hiddenAgents],
  );

  const ratings = data.rating_labels || [];
  const ratingTotal = ratings.reduce((sum, r) => sum + Number(r.count || 0), 0);
  const excellent = ratings.find((r) => Number(r.value) === 5);

  const lineData = useMemo(() => ({
    labels: (data.daily || []).map((row) => row.label),
    datasets: [
      {
        label: 'Primeira pergunta',
        data: (data.daily || []).map((row) => Number(row.count || 0)),
        borderColor: '#2dd4bf',
        backgroundColor: 'rgba(45, 212, 191, 0.35)',
        fill: true,
        tension: 0.4,
        pointRadius: 0,
        borderWidth: 2,
      },
      {
        label: 'Segunda pergunta',
        data: (data.daily || []).map(() => 0),
        borderColor: '#a3e635',
        backgroundColor: 'rgba(163, 230, 53, 0.25)',
        fill: true,
        tension: 0.4,
        pointRadius: 0,
        borderWidth: 1,
      },
    ],
  }), [data.daily]);

  const lineOptions = useMemo(() => ({
    responsive: true,
    maintainAspectRatio: false,
    interaction: { mode: 'index', intersect: false },
    plugins: {
      legend: {
        position: 'top',
        align: 'end',
        labels: { color: '#a1a1aa', boxWidth: 10, usePointStyle: true, pointStyle: 'circle', font: { size: 11 } },
      },
    },
    scales: {
      x: { ticks: { color: '#a1a1aa' }, grid: { color: 'rgba(255,255,255,0.06)' } },
      y: {
        beginAtZero: true,
        ticks: { color: '#a1a1aa', precision: 0 },
        grid: { color: 'rgba(255,255,255,0.06)' },
      },
    },
  }), []);

  const stackedByAgent = useMemo(() => ({
    labels: visibleAgents.map((a) => a.name),
    datasets: (ratings.length ? ratings : []).map((rating) => ({
      label: `${rating.label} ${rating.emoji || ''}`.trim(),
      data: visibleAgents.map((agent) => pct(agent.ratings?.[rating.value] || 0, agent.total)),
      backgroundColor: RATING_COLORS[rating.value] || '#64748b',
      stack: 'notas',
      borderWidth: 0,
    })),
  }), [visibleAgents, ratings]);

  const stackedByRating = useMemo(() => ({
    labels: ratings.map((r) => `${r.label} ${r.emoji || ''}`.trim()),
    datasets: visibleAgents.map((agent) => ({
      label: agent.name,
      data: ratings.map((rating) => pct(agent.ratings?.[rating.value] || 0, rating.count)),
      backgroundColor: agent.color,
      stack: 'agentes',
      borderWidth: 0,
    })),
  }), [visibleAgents, ratings]);

  const stackedOptions = useMemo(() => ({
    responsive: true,
    maintainAspectRatio: false,
    plugins: {
      legend: {
        position: 'right',
        labels: { color: '#a1a1aa', boxWidth: 10, usePointStyle: true, pointStyle: 'rectRounded', font: { size: 11 } },
      },
      tooltip: {
        callbacks: {
          label: (ctx) => `${ctx.dataset.label}: ${formatPct(ctx.parsed.y)}`,
        },
      },
    },
    scales: {
      x: {
        stacked: true,
        ticks: { color: '#a1a1aa', maxRotation: 40, minRotation: 0 },
        grid: { display: false },
      },
      y: {
        stacked: true,
        min: 0,
        max: 100,
        ticks: { color: '#a1a1aa', callback: (v) => `${v}` },
        grid: { color: 'rgba(255,255,255,0.06)' },
      },
    },
  }), []);

  const doughnutData = useMemo(() => ({
    labels: ratings.map((r) => `${r.label} ${r.emoji || ''}`.trim()),
    datasets: [{
      data: ratings.map((r) => Number(r.count || 0)),
      backgroundColor: ratings.map((r) => RATING_COLORS[r.value] || '#64748b'),
      borderWidth: 0,
      cutout: '68%',
    }],
  }), [ratings]);

  const topSlice = useMemo(() => {
    if (!ratingTotal) return { label: '—', pct: 0, color: '#22c55e' };
    const best = [...ratings].sort((a, b) => Number(b.count) - Number(a.count))[0];
    return {
      label: best?.label || '',
      pct: pct(best?.count || 0, ratingTotal),
      color: RATING_COLORS[best?.value] || '#22c55e',
    };
  }, [ratings, ratingTotal]);

  const doughnutOptions = useMemo(() => ({
    responsive: true,
    maintainAspectRatio: false,
    plugins: {
      legend: { display: false },
      tooltip: {
        callbacks: {
          label: (ctx) => `${ctx.label}: ${formatPct(pct(ctx.parsed, ratingTotal))}`,
        },
      },
    },
  }), [ratingTotal]);

  const doughnutCenterPlugin = useMemo(() => ({
    id: 'relatorioDonutCenter',
    afterDraw(chart) {
      const { ctx, chartArea } = chart;
      if (!chartArea) return;
      ctx.save();
      ctx.fillStyle = '#e5e7eb';
      ctx.font = '700 22px Inter, system-ui, sans-serif';
      ctx.textAlign = 'center';
      ctx.textBaseline = 'middle';
      ctx.fillText(`${Number(topSlice.pct || 0).toFixed(1)}%`, (chartArea.left + chartArea.right) / 2, (chartArea.top + chartArea.bottom) / 2);
      ctx.restore();
    },
  }), [topSlice.pct]);

  return (
    <div className="p-6 space-y-4">
      <h1 className="text-2xl font-bold text-foreground">Pesquisa de Satisfação</h1>

      <div className="flex flex-wrap items-center gap-2">
        <select
          className="h-9 min-w-[180px] rounded-md border border-input bg-background px-3 text-sm text-foreground"
          defaultValue="padrao"
        >
          <option value="padrao">Pesquisa padrão</option>
        </select>
        <input
          type="date"
          value={fromDate}
          onChange={(e) => setFromDate(e.target.value)}
          className="h-9 rounded-md border border-input bg-background px-3 text-sm text-foreground"
        />
        <span className="text-sm text-muted-foreground">até</span>
        <input
          type="date"
          value={toDate}
          onChange={(e) => setToDate(e.target.value)}
          className="h-9 rounded-md border border-input bg-background px-3 text-sm text-foreground"
        />
        <button
          type="button"
          className="inline-flex h-9 items-center gap-2 rounded-md bg-sky-600 px-3 text-sm font-medium text-white hover:bg-sky-500"
          onClick={onSearch}
        >
          <Search className="w-4 h-4" />
          Procurar
        </button>
        <div className="ml-auto flex items-center gap-2">
          <div className="relative">
            <button
              type="button"
              className="inline-flex h-9 items-center gap-2 rounded-md border border-input bg-background px-3 text-sm hover:bg-muted"
              onClick={() => setFilterOpen((v) => !v)}
            >
              <Filter className="w-4 h-4" />
              Filtrar
            </button>
            {filterOpen && (
              <div className="absolute right-0 z-20 mt-2 w-64 rounded-md border border-border bg-popover p-3 shadow-lg">
                <p className="text-xs text-muted-foreground mb-2">Atendentes no gráfico</p>
                <div className="space-y-2 max-h-64 overflow-y-auto">
                  {agents.length === 0 && (
                    <p className="text-sm text-muted-foreground">Nenhum atendente no período.</p>
                  )}
                  {agents.map((agent) => (
                    <label key={agent.name} className="flex items-center gap-2 text-sm cursor-pointer">
                      <input
                        type="checkbox"
                        checked={!hiddenAgents.includes(agent.name)}
                        onChange={() => setHiddenAgents((prev) => (
                          prev.includes(agent.name) ? prev.filter((x) => x !== agent.name) : [...prev, agent.name]
                        ))}
                      />
                      <span className="w-2 h-2 rounded-full shrink-0" style={{ background: agent.color }} />
                      <span className="truncate">{agent.name}</span>
                    </label>
                  ))}
                </div>
              </div>
            )}
          </div>
          <button
            type="button"
            className="inline-flex h-9 items-center gap-2 rounded-md border border-input bg-background px-3 text-sm text-muted-foreground"
            disabled
          >
            <Plus className="w-4 h-4" />
            Novo dashboard
          </button>
        </div>
      </div>

      {loading ? (
        <div className="flex items-center justify-center h-72">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary" />
        </div>
      ) : error ? (
        <div className="flex items-center justify-center h-40 text-sm text-destructive">{error}</div>
      ) : (
        <>
          <RelatorioStatStrip
            columns={4}
            items={[
              { label: 'Respostas', value: formatStatInt(data.total_feedbacks), hint: 'no período' },
              { label: 'Média', value: Number(data.average_rating || 0).toFixed(2).replace('.', ','), hint: 'escala de 1 a 5' },
              { label: 'Satisfação', value: `${Number(data.satisfaction_rate || 0).toFixed(1).replace('.', ',')}%`, hint: 'Bom e Excelente' },
              { label: 'Excelente', value: formatStatInt(excellent?.count), hint: 'nota 5' },
            ]}
          />

          <div className="rounded-xl border border-border bg-card p-5">
            <div className="mb-4">
              <p className="text-[11px] font-medium uppercase tracking-[0.16em] text-muted-foreground">Respostas no período</p>
              <p className="mt-1 text-sm text-muted-foreground">{formatStatInt(data.total_feedbacks)} respostas</p>
            </div>
            <div style={{ height: 280 }}>
              <Line data={lineData} options={lineOptions} />
            </div>
          </div>

          <div>
            <h2 className="text-base font-semibold text-foreground">Primeira pergunta</h2>
            <p className="text-sm text-muted-foreground mt-1 leading-relaxed">
              {data.question || 'Como você avalia o atendimento de @atendente_nome?'}
            </p>
          </div>

          <div className="grid grid-cols-1 xl:grid-cols-5 gap-4">
            <div className="xl:col-span-3 rounded-xl border border-border bg-card p-5">
              <div className="mb-4">
                <p className="text-[11px] font-medium uppercase tracking-[0.16em] text-muted-foreground">Notas por atendente</p>
                <p className="mt-1 text-sm text-muted-foreground">distribuição das avaliações recebidas</p>
              </div>
              <div style={{ height: 280 }}>
                {visibleAgents.length ? (
                  <Bar data={stackedByAgent} options={stackedOptions} plugins={[percentLabelsPlugin]} />
                ) : (
                  <div className="h-full flex items-center justify-center text-sm text-muted-foreground">
                    Sem notas no período.
                  </div>
                )}
              </div>
            </div>

            <div className="xl:col-span-2 rounded-xl border border-border bg-card p-5">
              <div className="mb-4">
                <p className="text-[11px] font-medium uppercase tracking-[0.16em] text-muted-foreground">Total geral</p>
                <p className="mt-1 text-sm text-muted-foreground">participação de cada nota</p>
              </div>
              <div className="flex flex-col items-center">
                <div style={{ height: 200, width: '100%' }}>
                  <Doughnut data={doughnutData} options={doughnutOptions} plugins={[doughnutCenterPlugin]} />
                </div>
                <div className="mt-3 w-full grid grid-cols-2 gap-x-3 gap-y-1 text-xs text-muted-foreground">
                  {ratings.map((r) => (
                    <div key={r.value} className="flex items-center gap-1.5">
                      <span className="h-2 w-2 rounded-full shrink-0" style={{ background: RATING_COLORS[r.value] }} />
                      <span className="truncate">
                        {r.label} {r.emoji} ({formatPct(pct(r.count, ratingTotal))})
                      </span>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          </div>

          <div className="rounded-xl border border-border bg-card p-5">
            <div className="mb-4">
              <p className="text-[11px] font-medium uppercase tracking-[0.16em] text-muted-foreground">Notas por avaliação</p>
              <p className="mt-1 text-sm text-muted-foreground">participação de cada atendente na nota</p>
            </div>
            <div style={{ height: 280 }}>
              {visibleAgents.length ? (
                <Bar data={stackedByRating} options={stackedOptions} plugins={[percentLabelsPlugin]} />
              ) : (
                <div className="h-full flex items-center justify-center text-sm text-muted-foreground">
                  Sem notas no período.
                </div>
              )}
            </div>
          </div>

          <RelatorioSatisfacaoFeedbacks
            provedorId={provedorId}
            feedbacks={data.recent_feedbacks || []}
            loading={loading}
          />
        </>
      )}
    </div>
  );
}
