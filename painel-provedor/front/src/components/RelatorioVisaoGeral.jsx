import React, { useCallback, useEffect, useMemo, useState } from 'react';
import axios from 'axios';
import { format, startOfDay, subDays } from 'date-fns';
import {
  Chart as ChartJS,
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  Filler,
  Tooltip,
  Legend,
} from 'chart.js';
import { Line } from 'react-chartjs-2';
import { Download, Filter, Search, X } from 'lucide-react';
import { buildApiPath } from '../utils/apiBaseUrl';
import RelatorioIntro from './RelatorioIntro';
import { describeVolumeTrend, downloadRelatorioPdf, seriesValuesForKey } from '../utils/exportRelatorioPdf';

ChartJS.register(CategoryScale, LinearScale, PointElement, LineElement, Filler, Tooltip, Legend);

const CHART_COLORS = [
  '#2dd4bf',
  '#a3e635',
  '#38bdf8',
  '#f43f5e',
  '#f59e0b',
  '#a78bfa',
  '#fb923c',
  '#94a3b8',
];

function defaultRange() {
  const to = startOfDay(new Date());
  return { from: subDays(to, 6), to };
}

function colorForAgent(id, index) {
  if (id === 'automacao') return '#2dd4bf';
  if (id === 'nao_atribuido') return '#94a3b8';
  return CHART_COLORS[index % CHART_COLORS.length];
}

function initials(name) {
  const parts = String(name || '')
    .trim()
    .split(/\s+/)
    .filter(Boolean);
  if (!parts.length) return '?';
  return parts.slice(0, 2).map((p) => p[0]).join('').toUpperCase();
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

export default function RelatorioVisaoGeral({ provedorId }) {
  const initial = defaultRange();
  const [fromDate, setFromDate] = useState(toInputDate(initial.from));
  const [toDate, setToDate] = useState(toInputDate(initial.to));
  const [appliedFrom, setAppliedFrom] = useState(fromDate);
  const [appliedTo, setAppliedTo] = useState(toDate);
  const [filterOpen, setFilterOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [data, setData] = useState({ agents: [], series: [], totals: { tma: '00:00:00', media: 0, total: 0 } });
  const [hiddenIds, setHiddenIds] = useState([]);
  const [sort, setSort] = useState({ key: 'name', dir: 'asc' });
  const [detailAgent, setDetailAgent] = useState(null);
  const [exporting, setExporting] = useState(false);

  const fetchReport = useCallback(async (start, end) => {
    if (!start || !end) return;
    try {
      setLoading(true);
      setError('');
      const token = localStorage.getItem('auth_token') || localStorage.getItem('token');
      if (!token) throw new Error('Faça login novamente.');
      const qs = new URLSearchParams({ start_date: start, end_date: end });
      if (provedorId) qs.set('provedor_id', String(provedorId));
      const res = await axios.get(buildApiPath(`/api/relatorios/atendentes/visao-geral/?${qs}`), {
        headers: { Authorization: `Token ${token}` },
      });
      setData({
        agents: res.data?.agents || [],
        series: res.data?.series || [],
        totals: res.data?.totals || { tma: '00:00:00', media: 0, total: 0 },
      });
    } catch (err) {
      setError(err.response?.data?.error || 'Não foi possível carregar o relatório.');
      setData({ agents: [], series: [], totals: { tma: '00:00:00', media: 0, total: 0 } });
    } finally {
      setLoading(false);
    }
  }, [provedorId]);

  useEffect(() => {
    fetchReport(appliedFrom, appliedTo);
  }, [appliedFrom, appliedTo, fetchReport]);

  const coloredAgents = useMemo(
    () => (data.agents || []).map((agent, index) => ({
      ...agent,
      color: colorForAgent(agent.id, index),
    })),
    [data.agents],
  );

  const visibleColored = useMemo(
    () => coloredAgents.filter((a) => !hiddenIds.includes(a.id)),
    [coloredAgents, hiddenIds],
  );

  const sortedAgents = useMemo(() => {
    const rows = [...visibleColored];
    const { key, dir } = sort;
    const factor = dir === 'asc' ? 1 : -1;
    rows.sort((a, b) => {
      const va = a[key];
      const vb = b[key];
      if (key === 'name' || key === 'tma' || key === 'percent') {
        return String(va).localeCompare(String(vb), 'pt-BR') * factor;
      }
      return (Number(va) - Number(vb)) * factor;
    });
    return rows;
  }, [visibleColored, sort]);

  const toggleSort = (key) => {
    setSort((prev) =>
      prev.key === key ? { key, dir: prev.dir === 'asc' ? 'desc' : 'asc' } : { key, dir: key === 'name' ? 'asc' : 'desc' },
    );
  };

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

  const toggleHidden = (id) => {
    setHiddenIds((prev) => (prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]));
  };

  const exportPdf = async () => {
    if (!sortedAgents.length || exporting) return;
    try {
      setExporting(true);
      const totals = data.totals || {};
      const analyses = sortedAgents.map((agent) => {
        const trend = describeVolumeTrend(seriesValuesForKey(data.series, agent.id));
        return {
          name: agent.name,
          color: agent.color,
          text: `${agent.name} encerrou ${agent.total} atendimento(s), ${agent.percent}% do total da empresa. TMA ${agent.tma}, média diária ${agent.media}. Este atendente ${trend.text}.`,
        };
      });
      await downloadRelatorioPdf({
        title: 'Relatório de atendentes',
        periodFrom: appliedFrom,
        periodTo: appliedTo,
        kpis: [
          { label: 'Total', value: totals.total ?? 0 },
          { label: 'Média', value: totals.media ?? 0 },
          { label: 'T.M.A', value: totals.tma || '00:00:00' },
          { label: 'Atendentes', value: sortedAgents.length },
        ],
        intro: 'O gráfico colorido mostra os encerramentos de cada atendente no período. A leitura abaixo indica se o volume de cada um aumentou, diminuiu ou ficou estável na segunda metade do intervalo.',
        chart: {
          labels: (data.series || []).map((row) => row.label),
          datasets: sortedAgents.map((agent) => ({
            label: agent.name,
            data: (data.series || []).map((row) => Number(row[agent.id] || 0)),
            borderColor: agent.color,
            backgroundColor: `${agent.color}55`,
          })),
        },
        table: {
          title: 'Desempenho por atendente',
          columns: [
            { header: 'Atendente', key: 'name' },
            { header: '%', key: 'percent' },
            { header: 'T.M.A', key: 'tma' },
            { header: 'Média', key: 'media' },
            { header: 'Total', key: 'total' },
          ],
          rows: sortedAgents.map((a) => ({
            name: a.name,
            percent: `${a.percent}%`,
            tma: a.tma,
            media: a.media,
            total: a.total,
          })),
        },
        analyses,
        filename: `relatorio-atendentes-${appliedFrom}-${appliedTo}.pdf`,
      });
    } catch (err) {
      setError('Não foi possível gerar o PDF do relatório.');
    } finally {
      setExporting(false);
    }
  };

  const detailSeries = useMemo(() => {
    if (!detailAgent) return [];
    return (data.series || []).map((row) => ({
      label: row.label,
      total: Number(row[detailAgent.id] || 0),
    }));
  }, [detailAgent, data.series]);

  const chartData = useMemo(() => ({
    labels: (data.series || []).map((row) => row.label),
    datasets: visibleColored.map((agent) => ({
      label: agent.name,
      data: (data.series || []).map((row) => Number(row[agent.id] || 0)),
      borderColor: agent.color,
      backgroundColor: `${agent.color}55`,
      fill: true,
      tension: 0.35,
      pointRadius: 2,
      borderWidth: 2,
    })),
  }), [data.series, visibleColored]);

  const chartOptions = useMemo(() => ({
    responsive: true,
    maintainAspectRatio: false,
    interaction: { mode: 'index', intersect: false },
    plugins: {
      legend: {
        labels: { color: '#a1a1aa', boxWidth: 12, font: { size: 11 } },
      },
      tooltip: { enabled: true },
    },
    scales: {
      x: {
        ticks: { color: '#a1a1aa' },
        grid: { color: 'rgba(255,255,255,0.06)' },
      },
      y: {
        beginAtZero: true,
        ticks: { color: '#a1a1aa', precision: 0 },
        grid: { color: 'rgba(255,255,255,0.06)' },
      },
    },
  }), []);

  return (
    <div className="p-6 space-y-4">
      <div>
        <h1 className="text-2xl font-bold text-foreground">Visão geral</h1>
      </div>

      <RelatorioIntro
        title="Relatório de atendentes"
        description="Desempenho da equipe pelos atendimentos encerrados no período."
        points={[
          { label: 'Volume', text: 'Quantos atendimentos cada pessoa encerrou.' },
          { label: 'Média por dia', text: 'Média diária de cada atendente no intervalo.' },
          { label: 'Participação', text: 'Percentual de cada um no total da empresa.' },
        ]}
      />

      <div className="flex flex-wrap items-center gap-2">
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
          Pesquisar
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
                <p className="text-xs text-muted-foreground mb-2">Exibir no gráfico e na tabela</p>
                <div className="space-y-2 max-h-64 overflow-y-auto">
                  {coloredAgents.length === 0 && (
                    <p className="text-sm text-muted-foreground">Nenhum atendente no período.</p>
                  )}
                  {coloredAgents.map((agent) => (
                    <label key={agent.id} className="flex items-center gap-2 text-sm cursor-pointer">
                      <input
                        type="checkbox"
                        checked={!hiddenIds.includes(agent.id)}
                        onChange={() => toggleHidden(agent.id)}
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
            className="inline-flex h-9 items-center gap-2 rounded-md border border-input bg-background px-3 text-sm hover:bg-muted disabled:opacity-50"
            onClick={exportPdf}
            disabled={!sortedAgents.length || exporting}
          >
            <Download className="w-4 h-4" />
            {exporting ? 'Gerando PDF…' : 'Baixar PDF'}
          </button>
        </div>
      </div>

      <p className="text-xs text-muted-foreground">
        de {appliedFrom.split('-').reverse().join('/')} até {appliedTo.split('-').reverse().join('/')}
      </p>

      <div className="rounded-xl border border-border bg-card p-4">
        {loading ? (
          <div className="flex items-center justify-center h-72">
            <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary" />
          </div>
        ) : error ? (
          <div className="flex items-center justify-center h-72 text-sm text-destructive">{error}</div>
        ) : (
          <>
            <div style={{ height: 320 }}>
              <Line data={chartData} options={chartOptions} />
            </div>

            <div className="mt-4 overflow-x-auto rounded-md border border-border">
              <table className="w-full text-sm">
                <thead className="bg-muted/70 text-muted-foreground">
                  <tr>
                    <th className="text-left font-medium px-4 py-2.5 cursor-pointer" onClick={() => toggleSort('name')}>
                      ATENDENTE {sort.key === 'name' ? (sort.dir === 'asc' ? '↑' : '↓') : ''}
                    </th>
                    <th className="text-left font-medium px-4 py-2.5 cursor-pointer" onClick={() => toggleSort('percent')}>%</th>
                    <th className="text-left font-medium px-4 py-2.5 cursor-pointer" onClick={() => toggleSort('tma')}>T.M.A</th>
                    <th className="text-left font-medium px-4 py-2.5 cursor-pointer" onClick={() => toggleSort('media')}>MÉDIA</th>
                    <th className="text-left font-medium px-4 py-2.5 cursor-pointer" onClick={() => toggleSort('total')}>TOTAL</th>
                    <th className="px-4 py-2.5" />
                  </tr>
                </thead>
                <tbody>
                  {sortedAgents.length === 0 && (
                    <tr>
                      <td colSpan={6} className="px-4 py-10 text-center text-muted-foreground">
                        Nenhum atendimento encerrado neste período.
                      </td>
                    </tr>
                  )}
                  {sortedAgents.map((agent) => (
                    <tr key={agent.id} className="border-t border-border">
                      <td className="px-4 py-3">
                        <div className="flex items-center gap-3">
                          <span
                            className="w-9 h-9 rounded-full flex items-center justify-center text-[11px] font-semibold text-white"
                            style={{ background: agent.color }}
                          >
                            {initials(agent.name)}
                          </span>
                          <span className="font-medium text-foreground">{agent.name}</span>
                        </div>
                      </td>
                      <td className="px-4 py-3 text-foreground">{agent.percent}</td>
                      <td className="px-4 py-3 text-foreground tabular-nums">{agent.tma}</td>
                      <td className="px-4 py-3 text-foreground tabular-nums">{agent.media}</td>
                      <td className="px-4 py-3 text-foreground tabular-nums">{agent.total}</td>
                      <td className="px-4 py-3 text-right">
                        <button
                          type="button"
                          className="text-amber-400 hover:text-amber-300 text-xs font-semibold tracking-wide"
                          onClick={() => setDetailAgent(agent)}
                        >
                          VER
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
                {sortedAgents.length > 0 && (
                  <tfoot>
                    <tr className="border-t border-border bg-muted/40">
                      <td className="px-4 py-3" />
                      <td className="px-4 py-3" />
                      <td className="px-4 py-3 tabular-nums text-foreground">{data.totals.tma}</td>
                      <td className="px-4 py-3 tabular-nums text-foreground">{data.totals.media}</td>
                      <td className="px-4 py-3 tabular-nums text-foreground">{data.totals.total}</td>
                      <td />
                    </tr>
                  </tfoot>
                )}
              </table>
            </div>
          </>
        )}
      </div>

      {detailAgent && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4" onClick={() => setDetailAgent(null)}>
          <div
            className="w-full max-w-lg rounded-xl border border-border bg-card p-5 shadow-xl"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-lg font-semibold">{detailAgent.name}</h2>
              <button type="button" className="p-1 rounded hover:bg-muted" onClick={() => setDetailAgent(null)}>
                <X className="w-4 h-4" />
              </button>
            </div>
            <div className="grid grid-cols-3 gap-2 text-sm mb-4">
              <div className="rounded-md border border-border p-3">
                <div className="text-xs text-muted-foreground">Participação</div>
                <div className="font-semibold">{detailAgent.percent}%</div>
              </div>
              <div className="rounded-md border border-border p-3">
                <div className="text-xs text-muted-foreground">T.M.A</div>
                <div className="font-semibold tabular-nums">{detailAgent.tma}</div>
              </div>
              <div className="rounded-md border border-border p-3">
                <div className="text-xs text-muted-foreground">Total</div>
                <div className="font-semibold tabular-nums">{detailAgent.total}</div>
              </div>
            </div>
            <table className="w-full text-sm">
              <thead>
                <tr className="text-muted-foreground">
                  <th className="text-left py-1">Dia</th>
                  <th className="text-right py-1">Encerrados</th>
                </tr>
              </thead>
              <tbody>
                {detailSeries.map((row) => (
                  <tr key={row.label} className="border-t border-border">
                    <td className="py-1.5">{row.label}</td>
                    <td className="py-1.5 text-right tabular-nums">{row.total}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}
