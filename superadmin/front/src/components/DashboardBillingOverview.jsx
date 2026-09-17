import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { Bar } from 'react-chartjs-2';
import { ensureChartJsRegistered } from '../lib/chartSetup';
import { ExternalLink, RefreshCw } from 'lucide-react';
import axios from 'axios';
import { Link } from 'react-router-dom';
import { STATUS_PILL, StatusPill } from './DashboardOverviewPanels';

ensureChartJsRegistered();


function formatMoney(value) {
  if (value == null || Number.isNaN(Number(value))) return '—';
  return Number(value).toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' });
}

function formatDate(iso) {
  if (!iso) return '—';
  const [y, m, d] = String(iso).split('-');
  if (!y || !m || !d) return iso;
  return `${d}/${m}/${y}`;
}

const emptyData = {
  asaas_configured: true,
  due_today: { total: 0, total_value: 0, days_window: 3, items: [] },
  due_soon: { total: 0, total_value: 0, days_window: 3, items: [] },
  subscriptions_receivable: { total_value: 0, total_count: 0, source: 'none' },
  billing_messages: { sent_ok: 0, sent_err: 0, total: 0, items: [] },
  titles_received: {
    total_value: 0,
    total_count: 0,
    today_count: 0,
    today_value: 0,
    chart: [],
    recent: [],
  },
};

export default function DashboardBillingOverview() {
  const [loading, setLoading] = useState(true);
  const [data, setData] = useState(emptyData);
  const [error, setError] = useState('');

  const fetchData = useCallback(async () => {
    try {
      setLoading(true);
      setError('');
      const token = localStorage.getItem('token') || localStorage.getItem('auth_token');
      const res = await axios.get('/api/provedores/billing-overview/', {
        headers: { Authorization: `Token ${token}` },
      });
      setData(res.data || emptyData);
      if (res.data?.error && res.data?.asaas_configured) {
        setError(res.data.error);
      }
    } catch (err) {
      console.error('Erro ao carregar cobrança de provedores:', err);
      setError('Não foi possível carregar o resumo de cobrança.');
      setData({ ...emptyData, asaas_configured: false });
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  const due = data.due_soon || data.due_today || emptyData.due_soon;
  const receivable = data.subscriptions_receivable || emptyData.subscriptions_receivable;
  const msgs = data.billing_messages || emptyData.billing_messages;
  const titles = data.titles_received || emptyData.titles_received;
  const chart = titles.chart || [];
  const daysWindow = due.days_window ?? 3;

  const chartData = useMemo(() => {
    const labels = chart.map((d) => d.label);
    return {
      labels,
      datasets: [
        {
          type: 'bar',
          label: 'Valor',
          data: chart.map((d) => d.value),
          backgroundColor: 'rgba(249, 115, 22, 0.75)',
          borderRadius: 4,
          yAxisID: 'yValue',
          order: 2,
        },
        {
          type: 'line',
          label: 'Quantidade',
          data: chart.map((d) => d.count),
          borderColor: '#1B6B3A',
          backgroundColor: '#1B6B3A',
          pointRadius: 2,
          tension: 0.3,
          yAxisID: 'yCount',
          order: 1,
        },
      ],
    };
  }, [chart]);

  const chartOptions = useMemo(
    () => ({
      responsive: true,
      maintainAspectRatio: false,
      interaction: { mode: 'index', intersect: false },
      plugins: {
        legend: {
          position: 'top',
          labels: { color: '#E5E7EB', usePointStyle: true, boxWidth: 8 },
        },
        tooltip: {
          backgroundColor: '#1F2937',
          titleColor: '#F9FAFB',
          bodyColor: '#E5E7EB',
          callbacks: {
            label: (ctx) => {
              if (ctx.dataset.yAxisID === 'yValue') {
                return `Valor: ${formatMoney(ctx.parsed.y)}`;
              }
              return `Qtd: ${ctx.parsed.y}`;
            },
          },
        },
      },
      scales: {
        x: {
          grid: { display: false },
          ticks: {
            color: '#9CA3AF',
            maxRotation: 0,
            autoSkip: true,
            maxTicksLimit: 10,
          },
        },
        yCount: {
          type: 'linear',
          position: 'left',
          beginAtZero: true,
          grid: { color: '#374151' },
          ticks: { color: '#9CA3AF', precision: 0 },
          title: { display: true, text: 'Quantidade', color: '#9CA3AF', font: { size: 11 } },
        },
        yValue: {
          type: 'linear',
          position: 'right',
          beginAtZero: true,
          grid: { drawOnChartArea: false },
          ticks: {
            color: '#9CA3AF',
            callback: (v) => Number(v).toLocaleString('pt-BR', { maximumFractionDigits: 0 }),
          },
          title: { display: true, text: 'Valor', color: '#9CA3AF', font: { size: 11 } },
        },
      },
    }),
    []
  );

  const Row = ({ label, value, accent }) => (
    <div className="flex items-center justify-between py-2.5 border-b border-border last:border-0">
      <span className="text-sm text-muted-foreground">{label}</span>
      <span className={`text-sm font-semibold tabular-nums underline decoration-primary/40 underline-offset-4 ${accent || 'text-foreground'}`}>
        {value}
      </span>
    </div>
  );

  return (
    <div className="bg-card rounded-xl shadow-lg border border-border overflow-hidden mb-8">
      <div className="px-5 pt-4 pb-0 flex justify-end">
        <button
          type="button"
          onClick={fetchData}
          disabled={loading}
          className="p-2 rounded-lg border border-border hover:bg-muted/50 text-muted-foreground hover:text-foreground transition-colors disabled:opacity-50"
          title="Atualizar"
        >
          <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
        </button>
      </div>

      <div className="px-5 pb-5 pt-2 space-y-6">
        {!data.asaas_configured && (
          <p className="text-sm text-amber-400">
            Configure o token do Asaas em Integrações para ver vencimentos e títulos.
          </p>
        )}
        {error && <p className="text-sm text-amber-400">{error}</p>}

        <div className="flex flex-wrap gap-2">
          <StatusPill color={STATUS_PILL.ochre}>
            Perto do vencimento ({loading ? '…' : due.total})
          </StatusPill>
          <StatusPill color={STATUS_PILL.forest}>
            A receber ({loading ? '…' : formatMoney(receivable.total_value)})
          </StatusPill>
          <StatusPill color={STATUS_PILL.royal}>
            Cobranças OK ({loading ? '…' : msgs.sent_ok})
          </StatusPill>
          <StatusPill color={STATUS_PILL.burgundy}>
            Falhas ({loading ? '…' : msgs.sent_err})
          </StatusPill>
          <StatusPill color={STATUS_PILL.petrol}>
            Títulos mês ({loading ? '…' : titles.total_count})
          </StatusPill>
          <StatusPill color={STATUS_PILL.purple}>
            {loading ? '…' : formatMoney(titles.total_value)}
          </StatusPill>
        </div>

        {/* Resumo */}
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-4">
          <div className="rounded-xl border border-border bg-muted/20 p-4">
            <h3 className="text-sm font-semibold text-foreground mb-3">
              Perto do vencimento ({daysWindow} dias)
            </h3>
            <p className="text-3xl font-black tabular-nums text-foreground mb-1">
              {loading ? '…' : due.total}
            </p>
            <p className="text-xs text-muted-foreground mb-3">
              {formatMoney(due.total_value)} em aberto na janela
            </p>
            <Row label="Provedores (hoje → +3 dias)" value={loading ? '…' : due.total} />
          </div>

          <div className="rounded-xl border border-border bg-muted/20 p-4">
            <h3 className="text-sm font-semibold text-foreground mb-3">Valor a receber</h3>
            <p className="text-xl font-black tabular-nums text-foreground mb-1">
              {loading ? '…' : formatMoney(receivable.total_value)}
            </p>
            <p className="text-xs text-muted-foreground mb-3">
              soma das assinaturas no Asaas
            </p>
            <Row
              label="Assinaturas ativas"
              value={loading ? '…' : receivable.total_count}
            />
          </div>

          <div className="rounded-xl border border-border bg-muted/20 p-4">
            <h3 className="text-sm font-semibold text-foreground mb-3">Mensagens de cobrança</h3>
            <p className="text-3xl font-black tabular-nums text-foreground mb-1">
              {loading ? '…' : msgs.sent_ok}
            </p>
            <p className="text-xs text-muted-foreground mb-3">enviadas hoje pelo Superadmin</p>
            <Row label="Enviadas com sucesso" value={loading ? '…' : msgs.sent_ok} accent="text-emerald-400" />
            <Row label="Falhas no envio" value={loading ? '…' : msgs.sent_err} accent="text-red-400" />
          </div>

          <div className="rounded-xl border border-border bg-muted/20 p-4">
            <h3 className="text-sm font-semibold text-foreground mb-3">Títulos / recibos</h3>
            <p className="text-xl font-black tabular-nums text-foreground mb-1">
              {loading ? '…' : formatMoney(titles.total_value)}
            </p>
            <p className="text-xs text-muted-foreground mb-3">
              {titles.total_count} título{titles.total_count === 1 ? '' : 's'} no mês
            </p>
            <Row label="Recebidos hoje" value={loading ? '…' : titles.today_count} />
            <Row label="Valor hoje" value={loading ? '…' : formatMoney(titles.today_value)} />
          </div>
        </div>

        {/* Lista perto do vencimento */}
        <div>
          <h3 className="text-sm font-semibold text-foreground mb-3">
            Provedores perto do vencimento (até {daysWindow} dias)
          </h3>
          {loading && (
            <p className="text-sm text-muted-foreground">Consultando Asaas e dados locais…</p>
          )}
          {!loading && due.total === 0 && (
            <p className="text-sm text-muted-foreground">
              Nenhum provedor com vencimento nos próximos {daysWindow} dias.
            </p>
          )}
          {!loading && due.total > 0 && (
            <div className="overflow-x-auto rounded-lg border border-border">
              <table className="w-full text-sm">
                <thead>
                  <tr className="bg-muted/30 text-left text-xs uppercase tracking-wider text-muted-foreground">
                    <th className="px-4 py-3 w-16">ID</th>
                    <th className="px-4 py-3">Provedor</th>
                    <th className="px-4 py-3">Vencimento</th>
                    <th className="px-4 py-3">Em</th>
                    <th className="px-4 py-3">Valor</th>
                    <th className="px-4 py-3">Status</th>
                    <th className="px-4 py-3 text-right">Fatura</th>
                  </tr>
                </thead>
                <tbody>
                  {(due.items || []).map((row) => {
                    const pay = row.payment || {};
                    const days = row.days_until_due;
                    const daysLabel =
                      days == null
                        ? '—'
                        : days === 0
                          ? 'Hoje'
                          : days === 1
                            ? '1 dia'
                            : `${days} dias`;
                    return (
                      <tr key={row.id} className="border-t border-border hover:bg-muted/20 transition-colors">
                        <td className="px-4 py-3">
                          <span className="font-mono text-xs font-bold tabular-nums text-primary">
                            {row.id}
                          </span>
                        </td>
                        <td className="px-4 py-3">
                          <div className="font-medium text-foreground">{row.nome}</div>
                          <Link to="/admin/provedores" className="text-xs text-primary hover:underline">
                            Ver provedor
                          </Link>
                        </td>
                        <td className="px-4 py-3 text-foreground">{formatDate(pay.dueDate)}</td>
                        <td className="px-4 py-3">
                          <StatusPill
                            color={
                              days === 0
                                ? STATUS_PILL.burgundy
                                : days === 1
                                  ? STATUS_PILL.ochre
                                  : STATUS_PILL.royal
                            }
                          >
                            {daysLabel}
                          </StatusPill>
                        </td>
                        <td className="px-4 py-3 font-medium text-foreground">{formatMoney(pay.value)}</td>
                        <td className="px-4 py-3">
                          <StatusPill color={STATUS_PILL.petrol}>
                            {pay.status || row.subscription_status || '—'}
                          </StatusPill>
                        </td>
                        <td className="px-4 py-3 text-right">
                          {pay.invoiceUrl ? (
                            <a
                              href={pay.invoiceUrl}
                              target="_blank"
                              rel="noopener noreferrer"
                              className="inline-flex items-center gap-1 text-xs text-primary hover:underline"
                            >
                              Abrir
                              <ExternalLink className="w-3 h-3" />
                            </a>
                          ) : (
                            <span className="text-xs text-muted-foreground">—</span>
                          )}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </div>

        {/* Mensagens enviadas */}
        {!loading && (msgs.items || []).length > 0 && (
          <div>
            <h3 className="text-sm font-semibold text-foreground mb-3">Cobranças enviadas hoje</h3>
            <div className="flex flex-wrap gap-2">
              {(msgs.items || []).map((m, idx) => {
                const palette = [
                  STATUS_PILL.ochre,
                  STATUS_PILL.royal,
                  STATUS_PILL.purple,
                  STATUS_PILL.forest,
                  STATUS_PILL.petrol,
                  STATUS_PILL.burgundy,
                  STATUS_PILL.gray,
                ];
                const color = m.success ? palette[idx % palette.length] : STATUS_PILL.burgundy;
                return (
                  <StatusPill
                    key={m.id}
                    color={color}
                    title={m.error_message || m.template_name}
                  >
                    {m.provedor_nome || m.phone || `#${m.id}`}
                    {m.value ? ` (${formatMoney(m.value)})` : ''}
                  </StatusPill>
                );
              })}
            </div>
          </div>
        )}

        {/* Gráfico títulos recebidos */}
        <div>
          <div className="flex flex-wrap items-baseline justify-between gap-2 mb-2">
            <div>
              <p className="text-xs text-muted-foreground">
                Total pago via título: {formatMoney(titles.total_value)} | Quantidade títulos: {titles.total_count}
              </p>
              <h3 className="text-sm font-semibold text-foreground">Títulos recebidos (mês)</h3>
            </div>
          </div>
          <div className="h-64 rounded-lg border border-border bg-muted/5 p-3">
            {loading ? (
              <div className="flex h-full items-center justify-center text-sm text-muted-foreground">
                Carregando gráfico…
              </div>
            ) : titles.total_count === 0 ? (
              <div className="flex h-full items-center justify-center text-sm text-muted-foreground">
                Nenhum título de provedor recebido neste mês.
              </div>
            ) : (
              <Bar data={chartData} options={chartOptions} />
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
