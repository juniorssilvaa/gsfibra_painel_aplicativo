import { useCallback, useEffect, useMemo, useState } from 'react';
import axios from 'axios';
import { ArrowLeft, RefreshCw, AlertTriangle, MessageCircle, Layers, BadgeDollarSign, Hash } from 'lucide-react';
import { useNavigate, useParams } from 'react-router-dom';
import {
  ResponsiveContainer,
  AreaChart,
  Area,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
} from 'recharts';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import MetricCard from './dashboard/MetricCard';
import ConversationsPieChart from './dashboard/ConversationsPieChart';
import AdReferralsReport from './AdReferralsReport';
import { applyPieColors, ALL_DASHBOARD_PIE_COLORS } from '../utils/dashboardChartColors';

const PERIODS = [
  { days: 7, label: '7 dias' },
  { days: 30, label: '30 dias' },
  { days: 90, label: '90 dias' },
];

/** Cores fortes alinhadas ao dashboard principal */
const META_PIE_FREE_PAID = {
  Gratuitas: '#14b8a6',
  'Pagas (templates)': '#f97316',
};

const META_PIE_CATEGORY = {
  'Templates (pagas)': '#f97316',
  'Sessão (gratuitas)': '#14b8a6',
  Marketing: '#d946ef',
  Utilidade: '#38bdf8',
  Autenticação: '#f43f5e',
  'Autenticação internacional': '#e11d48',
  'Serviço (janela)': '#6366f1',
  'Marketing Lite': '#fb7185',
  'Entrada gratuita': '#84cc16',
};

function formatNumber(value) {
  return new Intl.NumberFormat('pt-BR').format(Number(value) || 0);
}

function formatMoney(value, currency = 'USD') {
  return new Intl.NumberFormat('pt-BR', {
    style: 'currency',
    currency,
    minimumFractionDigits: 2,
    maximumFractionDigits: currency === 'BRL' ? 2 : 4,
  }).format(Number(value) || 0);
}

function LineTooltip({ active, payload, label }) {
  if (!active || !payload?.length) return null;
  return (
    <div
      className="rounded-lg px-3 py-2 text-xs shadow-lg"
      style={{
        backgroundColor: 'rgba(15, 23, 42, 0.95)',
        border: '1px solid #1f2a44',
        color: '#cbd5e1',
      }}
    >
      {label ? <p className="mb-1.5 font-medium text-slate-300">{label}</p> : null}
      {payload.map((entry) => (
        <div key={entry.name} className="flex items-center gap-2 py-0.5">
          <span className="h-2.5 w-2.5 rounded-full" style={{ background: entry.color }} />
          <span className="text-slate-400">{entry.name}:</span>
          <span className="font-semibold text-foreground">{formatNumber(entry.value)}</span>
        </div>
      ))}
    </div>
  );
}

export default function MetaAnalyticsDashboard() {
  const navigate = useNavigate();
  const { provedorId } = useParams();
  const [days, setDays] = useState(30);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [data, setData] = useState(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const token = localStorage.getItem('auth_token') || localStorage.getItem('token');
      const res = await axios.get('/api/whatsapp/analytics/', {
        params: { days, provedor_id: provedorId },
        headers: token ? { Authorization: `Token ${token}` } : {},
      });
      if (!res.data?.success) {
        throw new Error(res.data?.error || 'Falha ao carregar analytics');
      }
      setData(res.data);
    } catch (err) {
      setError(
        err?.response?.data?.error ||
          err?.message ||
          'Não foi possível carregar os dados da Meta'
      );
      setData(null);
    } finally {
      setLoading(false);
    }
  }, [days, provedorId]);

  useEffect(() => {
    load();
  }, [load]);

  const summary = data?.summary || {};
  const messaging = data?.messaging || {};
  const categories = summary.by_category || [];
  const daily = data?.series?.daily || [];
  const spendBrl = summary.spend_brl;
  const spendUsd = summary.spend_usd;
  const usdRate = summary.usd_brl_rate;
  const fx = data?.fx;

  const pieFreePaid = useMemo(
    () =>
      applyPieColors(
        [
          { name: 'Gratuitas', value: Number(summary.messages_free) || 0 },
          { name: 'Pagas (templates)', value: Number(summary.messages_paid) || 0 },
        ],
        META_PIE_FREE_PAID,
        Object.values(META_PIE_FREE_PAID)
      ),
    [summary.messages_free, summary.messages_paid]
  );

  const pieCategory = useMemo(() => {
    const useMoney = categories.some(
      (c) => Number(c.cost_brl) > 0 || Number(c.cost_usd) > 0 || Number(c.cost) > 0
    );
    return applyPieColors(
      categories.map((c) => ({
        name: c.label,
        value: useMoney
          ? Number(c.cost_brl) || Number(c.cost_usd) || Number(c.cost) || 0
          : Number(c.volume) || 0,
      })),
      META_PIE_CATEGORY,
      ALL_DASHBOARD_PIE_COLORS
    );
  }, [categories]);

  const ratesTable = data?.rates || [];

  return (
    <div className="min-h-screen bg-background text-foreground overflow-y-auto">
      <div className="sticky top-0 z-40 border-b border-border bg-background/80 backdrop-blur-md px-4 py-4 md:px-6 flex flex-wrap items-center justify-between gap-4">
        <div className="flex items-center gap-4">
          <button
            type="button"
            onClick={() => navigate(-1)}
            className="p-2 hover:bg-muted rounded-full transition-colors group"
          >
            <ArrowLeft className="w-6 h-6 text-primary group-hover:scale-110 transition-transform" />
          </button>
          <div>
            <h1 className="text-2xl font-bold text-foreground">Meta · WhatsApp Analytics</h1>
            <p className="text-sm text-muted-foreground">
              Mensagens gratuitas, templates pagos e tendência no período
            </p>
          </div>
        </div>

        <div className="flex items-center gap-2">
          {PERIODS.map((p) => (
            <button
              key={p.days}
              type="button"
              onClick={() => setDays(p.days)}
              className={`px-3 py-1.5 rounded-lg text-sm font-medium transition ${
                days === p.days
                  ? 'bg-primary text-primary-foreground'
                  : 'bg-muted text-muted-foreground hover:bg-muted/80'
              }`}
            >
              {p.label}
            </button>
          ))}
          <button
            type="button"
            onClick={load}
            disabled={loading}
            className="p-2 rounded-lg bg-muted hover:bg-muted/80 transition disabled:opacity-50"
            title="Atualizar"
          >
            <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
          </button>
        </div>
      </div>

      <div className="w-full min-h-full space-y-6 p-6">
        {data?.channel && (
          <div className="rounded-xl border border-border bg-card px-4 py-3 text-sm text-muted-foreground flex flex-wrap gap-x-6 gap-y-1 items-center">
            <span>
              Canal:{' '}
              <strong className="text-foreground">{data.channel.nome || 'WhatsApp Oficial'}</strong>
            </span>
            {data.channel.phone_number && (
              <span>
                Número: <strong className="text-foreground">{data.channel.phone_number}</strong>
              </span>
            )}
            <span className="text-xs opacity-70">WABA {data.channel.waba_id}</span>
            {usdRate ? (
              <span className="ml-auto text-xs text-emerald-400/90">
                USD → BRL {Number(usdRate).toFixed(4)}
                {fx?.pct_change != null ? ` (${fx.pct_change}%)` : ''}
                {fx?.create_date ? ` · ${fx.create_date}` : ''}
              </span>
            ) : null}
          </div>
        )}

        {error && (
          <div className="rounded-xl border border-amber-500/30 bg-amber-500/10 px-4 py-3 flex gap-3 text-amber-100">
            <AlertTriangle className="w-5 h-5 shrink-0 mt-0.5" />
            <div>
              <p className="font-medium">Não foi possível carregar o dashboard</p>
              <p className="text-sm text-amber-200/80 mt-1">{error}</p>
            </div>
          </div>
        )}

        {loading && !data && (
          <div className="text-center text-muted-foreground py-16">Carregando analytics da Meta…</div>
        )}

        {data && (
          <>
            {/* Métricas — mesmo padrão do dashboard principal */}
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
              <MetricCard
                title="Mensagens Gratuitas"
                value={formatNumber(summary.messages_free)}
                subtitle="sessão"
                icon={MessageCircle}
                color="text-green-500"
              />
              <MetricCard
                title="Mensagens Pagas"
                value={formatNumber(summary.messages_paid)}
                subtitle="templates"
                icon={Layers}
                color="text-orange-500"
              />
              <MetricCard
                title="Quantidade Cobrada"
                value={formatNumber(summary.charged_volume)}
                subtitle="volume"
                icon={Hash}
                color="text-purple-500"
              />
              <MetricCard
                title="Gasto Aproximado (R$)"
                value={
                  spendBrl != null && spendBrl !== ''
                    ? formatMoney(spendBrl, 'BRL')
                    : '—'
                }
                subtitle={
                  spendUsd != null
                    ? `${formatMoney(spendUsd, 'USD')}${usdRate ? ` · dólar ${Number(usdRate).toFixed(4)}` : ''}`
                    : summary.spend_label || 'cotação'
                }
                icon={BadgeDollarSign}
                color="text-green-500"
              />
            </div>

            {/* Tarifas por categoria */}
            <Card className="bg-card border-border">
              <CardContent className="p-6">
                <h3 className="text-lg font-semibold text-foreground mb-1">
                  Tarifas por categoria (USD / mensagem)
                </h3>
                <p className="text-sm text-muted-foreground mb-4">
                  Volume × tarifa × cotação do dólar = gasto estimado em R$
                </p>
                <div className="overflow-x-auto rounded-xl border border-border">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="border-b border-border bg-muted/30 text-left text-muted-foreground">
                        <th className="px-4 py-3 font-semibold">Categoria</th>
                        <th className="px-4 py-3 font-semibold">Tarifa</th>
                        <th className="px-4 py-3 font-semibold">Moeda</th>
                        <th className="px-4 py-3 font-semibold">Msgs</th>
                        <th className="px-4 py-3 font-semibold">USD</th>
                        <th className="px-4 py-3 font-semibold">R$</th>
                        <th className="px-4 py-3 font-semibold">Vigência</th>
                      </tr>
                    </thead>
                    <tbody>
                      {(ratesTable.length
                        ? ratesTable.map((r) => {
                            const cat = categories.find((c) => c.key === r.key) || {};
                            return {
                              ...r,
                              volume: cat.volume || 0,
                              cost_usd: cat.cost_usd,
                              cost_brl: cat.cost_brl,
                            };
                          })
                        : categories
                      ).map((row) => (
                        <tr key={row.key || row.label} className="border-b border-border/60 last:border-0">
                          <td className="px-4 py-3 font-medium text-foreground">
                            {row.label || row.key}
                          </td>
                          <td className="px-4 py-3 font-mono text-foreground">
                            {Number(row.rate_usd ?? 0).toLocaleString('pt-BR', {
                              minimumFractionDigits: 4,
                              maximumFractionDigits: 4,
                            })}
                          </td>
                          <td className="px-4 py-3 text-muted-foreground">{row.currency || 'USD'}</td>
                          <td className="px-4 py-3 text-foreground">{formatNumber(row.volume || 0)}</td>
                          <td className="px-4 py-3 font-mono text-foreground">
                            {row.cost_usd != null ? formatMoney(row.cost_usd, 'USD') : '—'}
                          </td>
                          <td className="px-4 py-3 font-mono text-emerald-400">
                            {row.cost_brl != null ? formatMoney(row.cost_brl, 'BRL') : '—'}
                          </td>
                          <td className="px-4 py-3 text-muted-foreground">
                            {row.vigencia || 'período correspondente'}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </CardContent>
            </Card>

            {/* Pizzas sempre acima do gráfico de linha */}
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
              <Card className="bg-card border-border">
                <CardContent className="p-6">
                  <h3 className="text-lg font-semibold text-foreground mb-4">
                    Gratuitas × Pagas
                  </h3>
                  <ConversationsPieChart data={pieFreePaid} />
                </CardContent>
              </Card>

              <Card className="bg-card border-border">
                <CardContent className="p-6">
                  <h3 className="text-lg font-semibold text-foreground mb-4">
                    Gasto por Categoria (R$)
                  </h3>
                  <ConversationsPieChart data={pieCategory} />
                </CardContent>
              </Card>
            </div>

            {/* Tendência diária */}
            <Card className="bg-card border-border">
              <CardHeader className="pb-2">
                <CardTitle className="text-lg font-semibold text-foreground">
                  Tendência de Envios
                </CardTitle>
                <p className="text-sm text-muted-foreground font-normal">
                  Mensagens por dia · total, templates e sessão
                </p>
              </CardHeader>
              <CardContent>
                <div className="mb-3 flex flex-wrap gap-x-5 gap-y-2 text-sm">
                  <div className="flex items-center gap-2">
                    <div className="h-3 w-3 rounded-full" style={{ background: '#6366f1' }} />
                    <span className="font-medium text-foreground">Total</span>
                  </div>
                  <div className="flex items-center gap-2">
                    <div className="h-3 w-3 rounded-full" style={{ background: '#f97316' }} />
                    <span className="font-medium text-foreground">Templates</span>
                  </div>
                  <div className="flex items-center gap-2">
                    <div className="h-3 w-3 rounded-full" style={{ background: '#14b8a6' }} />
                    <span className="font-medium text-foreground">Sessão</span>
                  </div>
                </div>
                <div className="h-[300px]">
                  {daily.length === 0 ? (
                    <div className="flex h-full items-center justify-center text-muted-foreground">
                      Nenhum dado disponível
                    </div>
                  ) : (
                    <ResponsiveContainer width="100%" height="100%">
                      <AreaChart data={daily} margin={{ top: 10, right: 10, left: 0, bottom: 0 }}>
                        <defs>
                          <linearGradient id="metaGradTotal" x1="0" y1="0" x2="0" y2="1">
                            <stop offset="0%" stopColor="#6366f1" stopOpacity={0.45} />
                            <stop offset="100%" stopColor="#6366f1" stopOpacity={0.05} />
                          </linearGradient>
                        </defs>
                        <CartesianGrid stroke="var(--border)" />
                        <XAxis
                          dataKey="label"
                          stroke="var(--muted-foreground)"
                          tickLine={false}
                          axisLine={{ stroke: 'var(--border)' }}
                          fontSize={11}
                          minTickGap={24}
                        />
                        <YAxis
                          stroke="var(--muted-foreground)"
                          tickLine={false}
                          axisLine={{ stroke: 'var(--border)' }}
                          fontSize={11}
                          width={40}
                        />
                        <Tooltip content={<LineTooltip />} />
                        <Area
                          type="monotone"
                          dataKey="sent"
                          name="Total"
                          stroke="#6366f1"
                          fill="url(#metaGradTotal)"
                          strokeWidth={2.5}
                        />
                        <Line
                          type="monotone"
                          dataKey="templates"
                          name="Templates"
                          stroke="#f97316"
                          strokeWidth={2.5}
                          dot={false}
                          activeDot={{ r: 4 }}
                        />
                        <Line
                          type="monotone"
                          dataKey="session"
                          name="Sessão"
                          stroke="#14b8a6"
                          strokeWidth={2.5}
                          dot={false}
                          activeDot={{ r: 4 }}
                        />
                      </AreaChart>
                    </ResponsiveContainer>
                  )}
                </div>
              </CardContent>
            </Card>

            <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
              <Card className="bg-card border-border">
                <CardContent className="p-4">
                  <p className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                    Todas · enviadas
                  </p>
                  <p className="mt-1 text-xl font-bold text-foreground">
                    {formatNumber(messaging.all?.sent)}
                  </p>
                </CardContent>
              </Card>
              <Card className="bg-card border-border border-orange-500/30 bg-orange-500/5">
                <CardContent className="p-4">
                  <p className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                    Templates · entregues
                  </p>
                  <p className="mt-1 text-xl font-bold text-foreground">
                    {formatNumber(messaging.templates_paid?.delivered)}
                  </p>
                </CardContent>
              </Card>
              <Card className="bg-card border-border border-green-500/30 bg-green-500/5">
                <CardContent className="p-4">
                  <p className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                    Sessão · entregues
                  </p>
                  <p className="mt-1 text-xl font-bold text-foreground">
                    {formatNumber(messaging.session_free?.delivered)}
                  </p>
                </CardContent>
              </Card>
            </div>

            {summary.spend_label ? (
              <p className="text-xs text-muted-foreground">
                {summary.spend_label}
                {summary.currency_note ? ` · ${summary.currency_note}` : ''}
              </p>
            ) : summary.currency_note ? (
              <p className="text-xs text-muted-foreground">{summary.currency_note}</p>
            ) : null}
          </>
        )}

        <AdReferralsReport provedorId={provedorId} days={days} />
      </div>
    </div>
  );
}
