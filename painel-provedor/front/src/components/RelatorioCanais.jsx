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
import { Download, Filter, Maximize2, MessageCircle, Search, Send } from 'lucide-react';
import { buildApiPath } from '../utils/apiBaseUrl';
import RelatorioStatStrip, { formatStatInt } from './RelatorioStatStrip';
import RelatorioIntro from './RelatorioIntro';
import { describeVolumeTrend, downloadRelatorioPdf, seriesValuesForKey } from '../utils/exportRelatorioPdf';

ChartJS.register(CategoryScale, LinearScale, PointElement, LineElement, Filler, Tooltip, Legend);

const CHART_COLORS = [
  '#38bdf8',
  '#a3e635',
  '#2dd4bf',
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

function formatBrDate(iso) {
  return String(iso || '').split('-').reverse().join('/');
}

function ChannelTypeIcon({ tipo }) {
  const t = String(tipo || '').toLowerCase();
  if (t.includes('telegram')) {
    return (
      <span className="inline-flex h-7 w-7 items-center justify-center rounded-full bg-sky-500 text-white" title="Telegram">
        <Send className="h-3.5 w-3.5" />
      </span>
    );
  }
  if (t.includes('instagram')) {
    return (
      <span className="inline-flex h-7 w-7 items-center justify-center rounded-full bg-fuchsia-500 text-white" title="Instagram">
        <MessageCircle className="h-3.5 w-3.5" />
      </span>
    );
  }
  return (
    <span className="inline-flex h-7 w-7 items-center justify-center rounded-full bg-emerald-500 text-white" title="WhatsApp">
      <MessageCircle className="h-3.5 w-3.5" />
    </span>
  );
}

export default function RelatorioCanais({ provedorId, modo = 'geral' }) {
  const initial = defaultRange();
  const [fromDate, setFromDate] = useState(toInputDate(initial.from));
  const [toDate, setToDate] = useState(toInputDate(initial.to));
  const [appliedFrom, setAppliedFrom] = useState(fromDate);
  const [appliedTo, setAppliedTo] = useState(toDate);
  const [filterOpen, setFilterOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [data, setData] = useState({ channels: [], series: [], totals: {} });
  const [hiddenIds, setHiddenIds] = useState([]);
  const [exporting, setExporting] = useState(false);

  const title = modo === 'disparo' ? 'Disparo' : 'Total Geral';

  const fetchReport = useCallback(async (start, end) => {
    if (!start || !end) return;
    try {
      setLoading(true);
      setError('');
      const token = localStorage.getItem('auth_token') || localStorage.getItem('token');
      if (!token) throw new Error('Faça login novamente.');
      const qs = new URLSearchParams({
        start_date: start,
        end_date: end,
        modo: modo === 'disparo' ? 'disparo' : 'geral',
      });
      if (provedorId) qs.set('provedor_id', String(provedorId));
      const res = await axios.get(buildApiPath(`/api/relatorios/canais/?${qs}`), {
        headers: { Authorization: `Token ${token}` },
      });
      setData({
        channels: res.data?.channels || [],
        series: res.data?.series || [],
        totals: res.data?.totals || {},
      });
      setHiddenIds([]);
    } catch (err) {
      setError(err.response?.data?.error || 'Não foi possível carregar o relatório de canais.');
      setData({ channels: [], series: [], totals: {} });
    } finally {
      setLoading(false);
    }
  }, [provedorId, modo]);

  useEffect(() => {
    fetchReport(appliedFrom, appliedTo);
  }, [appliedFrom, appliedTo, fetchReport]);

  const coloredChannels = useMemo(
    () => (data.channels || []).map((channel, index) => ({
      ...channel,
      color: CHART_COLORS[index % CHART_COLORS.length],
    })),
    [data.channels],
  );

  const visibleChannels = useMemo(
    () => coloredChannels.filter((c) => !hiddenIds.includes(c.id)),
    [coloredChannels, hiddenIds],
  );

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
    if (!visibleChannels.length || exporting) return;
    try {
      setExporting(true);
      const totals = data.totals || {};
      const analyses = visibleChannels.map((channel) => {
        const trend = describeVolumeTrend(seriesValuesForKey(data.series, channel.id));
        return {
          name: channel.name,
          color: channel.color,
          text: `${channel.name} (${channel.tipo_label}) encerrou ${channel.total} atendimento(s), ${channel.percent}% do volume. ${channel.clientes} cliente(s), ${channel.recebidas} recebidas e ${channel.enviadas} enviadas. Este canal ${trend.text}.`,
        };
      });
      await downloadRelatorioPdf({
        title: modo === 'disparo' ? 'Relatório de canais — Disparo' : 'Relatório de canais — Total geral',
        periodFrom: appliedFrom,
        periodTo: appliedTo,
        kpis: [
          { label: 'Atendimentos', value: totals.total ?? 0 },
          { label: 'Clientes', value: totals.clientes ?? 0 },
          { label: 'Recebidas', value: totals.recebidas ?? 0 },
          { label: 'Enviadas', value: totals.enviadas ?? 0 },
        ],
        intro: 'O gráfico colorido mostra os encerramentos de cada canal. A leitura abaixo indica se o volume aumentou, diminuiu ou ficou estável na segunda metade do período.',
        chart: {
          labels: (data.series || []).map((row) => row.label),
          datasets: visibleChannels.map((channel) => ({
            label: channel.name,
            data: (data.series || []).map((row) => Number(row[channel.id] || 0)),
            borderColor: channel.color,
            backgroundColor: `${channel.color}55`,
          })),
        },
        table: {
          title: 'Desempenho por canal',
          columns: [
            { header: 'Canal', key: 'name' },
            { header: 'Tipo', key: 'tipo' },
            { header: 'Clientes', key: 'clientes' },
            { header: '%', key: 'percent' },
            { header: 'Total', key: 'total' },
          ],
          rows: visibleChannels.map((c) => ({
            name: c.name,
            tipo: c.tipo_label,
            clientes: c.clientes,
            percent: `${c.percent}%`,
            total: c.total,
          })),
        },
        analyses,
        filename: `relatorio-canais-${modo}-${appliedFrom}-${appliedTo}.pdf`,
      });
    } catch (err) {
      setError('Não foi possível gerar o PDF do relatório.');
    } finally {
      setExporting(false);
    }
  };

  const toggleFullscreen = () => {
    const el = document.documentElement;
    if (!document.fullscreenElement) {
      el.requestFullscreen?.();
    } else {
      document.exitFullscreen?.();
    }
  };

  const chartData = useMemo(() => ({
    labels: (data.series || []).map((row) => row.label),
    datasets: visibleChannels.map((channel) => ({
      label: channel.name,
      data: (data.series || []).map((row) => Number(row[channel.id] || 0)),
      borderColor: channel.color,
      backgroundColor: `${channel.color}55`,
      fill: true,
      tension: 0.4,
      pointRadius: 0,
      borderWidth: 2,
    })),
  }), [data.series, visibleChannels]);

  const chartOptions = useMemo(() => ({
    responsive: true,
    maintainAspectRatio: false,
    interaction: { mode: 'index', intersect: false },
    plugins: {
      legend: {
        position: 'top',
        align: 'end',
        labels: { color: '#a1a1aa', boxWidth: 10, usePointStyle: true, pointStyle: 'circle', font: { size: 11 } },
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

  const totals = data.totals || {};

  return (
    <div className="p-6 space-y-4">
      <div className="flex items-start justify-between gap-3">
        <h1 className="text-2xl font-bold text-foreground">{title}</h1>
        <button
          type="button"
          className="inline-flex h-8 items-center gap-1.5 rounded-full border border-border px-3 text-xs text-muted-foreground hover:bg-muted"
          onClick={toggleFullscreen}
        >
          <Maximize2 className="h-3.5 w-3.5" />
          Tela cheia
        </button>
      </div>

      <RelatorioIntro
        title="Relatório de canais"
        description="Performance de cada canal de atendimento no período filtrado."
        points={[
          { label: 'Encerrados', text: 'Total de atendimentos fechados em cada canal.' },
          { label: 'Origem', text: 'Se o atendimento começou pelo cliente ou pela empresa.' },
          { label: 'Participação', text: 'Percentual do canal no volume geral.' },
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
                  {coloredChannels.length === 0 && (
                    <p className="text-sm text-muted-foreground">Nenhum canal no período.</p>
                  )}
                  {coloredChannels.map((channel) => (
                    <label key={channel.id} className="flex items-center gap-2 text-sm cursor-pointer">
                      <input
                        type="checkbox"
                        checked={!hiddenIds.includes(channel.id)}
                        onChange={() => toggleHidden(channel.id)}
                      />
                      <span className="w-2 h-2 rounded-full shrink-0" style={{ background: channel.color }} />
                      <span className="truncate">{channel.name}</span>
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
            disabled={!visibleChannels.length || exporting}
          >
            <Download className="w-4 h-4" />
            {exporting ? 'Gerando PDF…' : 'Baixar PDF'}
          </button>
        </div>
      </div>

      <p className="text-xs text-muted-foreground">
        de {formatBrDate(appliedFrom)} até {formatBrDate(appliedTo)}
      </p>

      <RelatorioStatStrip
        items={[
          { label: 'Atendimentos', value: formatStatInt(totals.total) },
          { label: 'Clientes', value: formatStatInt(totals.clientes) },
          { label: 'Recebidas', value: formatStatInt(totals.recebidas) },
          { label: 'Enviadas', value: formatStatInt(totals.enviadas) },
          { label: 'Templates', value: formatStatInt(totals.templates) },
        ]}
      />

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
                    <th className="text-left font-medium px-4 py-2.5">Canal</th>
                    <th className="text-left font-medium px-4 py-2.5">Tipo</th>
                    <th className="text-right font-medium px-4 py-2.5">Cliente</th>
                    <th className="text-right font-medium px-4 py-2.5">Empresa</th>
                    <th className="text-right font-medium px-4 py-2.5">Recebidas</th>
                    <th className="text-right font-medium px-4 py-2.5">Enviadas</th>
                    <th className="text-right font-medium px-4 py-2.5">Templates</th>
                    <th className="text-right font-medium px-4 py-2.5">%</th>
                    <th className="text-right font-medium px-4 py-2.5">Total</th>
                  </tr>
                </thead>
                <tbody>
                  {visibleChannels.length === 0 && (
                    <tr>
                      <td colSpan={9} className="px-4 py-10 text-center text-muted-foreground">
                        Nenhum atendimento encerrado neste período.
                      </td>
                    </tr>
                  )}
                  {visibleChannels.map((channel) => (
                    <tr key={channel.id} className="border-t border-border">
                      <td className="px-4 py-3 font-medium text-foreground">{channel.name}</td>
                      <td className="px-4 py-3">
                        <ChannelTypeIcon tipo={channel.tipo} />
                      </td>
                      <td className="px-4 py-3 text-right tabular-nums">{channel.clientes}</td>
                      <td className="px-4 py-3 text-right tabular-nums">{channel.empresa}</td>
                      <td className="px-4 py-3 text-right tabular-nums">{channel.recebidas}</td>
                      <td className="px-4 py-3 text-right tabular-nums">{channel.enviadas}</td>
                      <td className="px-4 py-3 text-right tabular-nums">{channel.templates}</td>
                      <td className="px-4 py-3 text-right tabular-nums">{channel.percent}</td>
                      <td className="px-4 py-3 text-right tabular-nums font-medium">{channel.total}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
