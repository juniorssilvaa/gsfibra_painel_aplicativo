import React, { useState, useEffect, useMemo, useCallback } from 'react';
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { Calendar } from "@/components/ui/calendar";
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  ResponsiveContainer,
  PieChart,
  Pie,
  Cell,
  Tooltip,
  LabelList,
} from 'recharts';
import axios from 'axios';
import { buildApiPath } from '@/utils/apiBaseUrl';
import { format, subDays, startOfDay } from 'date-fns';
import { ptBR } from 'date-fns/locale';
import { CalendarDays } from 'lucide-react';

const BAR_ORANGE = '#ea580c';

/** Atalhos — cores do exemplo “Contratos ativos” (texto claro; amarelo usa texto escuro p/ contraste). */
const RANGE_PRESET_BUTTONS = [
  { days: 1, label: 'Hoje', bg: '#E83E8C', fg: '#ffffff' },
  { days: 7, label: '7 dias', bg: '#007BFF', fg: '#ffffff' },
  { days: 30, label: '30 dias', bg: '#FFC107', fg: '#1f2937' },
  { days: 90, label: '90 dias', bg: '#F86C6B', fg: '#ffffff' },
];

const CHANNEL_LABELS = {
  whatsapp: 'WhatsApp',
  whatsapp_session: 'WhatsApp QR',
  whatsapp_oficial: 'WhatsApp Oficial',
  telegram: 'Telegram',
  email: 'Email',
  webchat: 'Chat Web',
  instagram: 'Instagram',
  facebook: 'Facebook'
};

const prettifyChannelName = (name) => {
  if (!name) return 'Canal';
  const normalized = String(name).toLowerCase().trim();
  if (CHANNEL_LABELS[normalized]) return CHANNEL_LABELS[normalized];
  if (normalized.includes('whatsapp') && normalized.includes('oficial')) return 'WhatsApp Oficial';
  if (normalized.includes('whatsapp') && normalized.includes('session')) return 'WhatsApp QR';
  return String(name).replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase());
};

function defaultRange() {
  const to = startOfDay(new Date());
  const from = subDays(to, 6);
  return { from, to };
}

export default function ConversationAnalysis({ provedorId }) {
  const [range, setRange] = useState(defaultRange);
  const [calendarOpen, setCalendarOpen] = useState(false);
  const [analysisData, setAnalysisData] = useState(null);
  const [loading, setLoading] = useState(false);

  const fetchAnalysisData = useCallback(async () => {
    if (!range?.from || !range?.to) return;
    try {
      setLoading(true);
      const token = localStorage.getItem('auth_token') || localStorage.getItem('token');

      if (!token) {
        throw new Error('Token não encontrado. Faça login novamente.');
      }

      const qs = new URLSearchParams({
        start_date: format(range.from, 'yyyy-MM-dd'),
        end_date: format(range.to, 'yyyy-MM-dd'),
      });
      if (provedorId) qs.set('provedor_id', String(provedorId));

      const response = await axios.get(buildApiPath(`/api/analysis/?${qs.toString()}`), {
        headers: {
          'Authorization': `Token ${token}`
        }
      });

      if (response.status === 200) {
        const apiData = response.data;

        const transformedData = {
          totalConversations: apiData.summary?.totalConversations || 0,
          channels: apiData.channelDistribution?.map(channel => ({
            name: prettifyChannelName(channel.name),
            count: channel.value,
            percentage: `${Math.round((channel.value / (apiData.summary?.totalConversations || 1)) * 100)}%`,
            color: channel.color
          })) || [],
          dailyVolume: apiData.conversationsByDay?.map(day => ({
            date: day.date,
            volume: day.conversations ?? 0,
          })) || []
        };

        setAnalysisData(transformedData);
      } else {
        setAnalysisData({
          totalConversations: 0,
          channels: [],
          dailyVolume: []
        });
      }
    } catch (error) {
      setAnalysisData({
        totalConversations: 0,
        channels: [],
        dailyVolume: []
      });
    } finally {
      setLoading(false);
    }
  }, [provedorId, range]);

  useEffect(() => {
    fetchAnalysisData();
  }, [fetchAnalysisData]);

  const data = analysisData || {
    totalConversations: 0,
    channels: [],
    dailyVolume: []
  };

  const chartRows = useMemo(
    () =>
      data.dailyVolume.map((row) => ({
        ...row,
        label: row.date,
      })),
    [data.dailyVolume]
  );

  const hasTimeline = chartRows.length > 0;
  const hasChannels = data.channels.length > 0;
  const showGlobalEmpty = !loading && !hasTimeline && !hasChannels;

  const rangeLabel =
    range?.from && range?.to
      ? `${format(range.from, 'dd/MM/yyyy', { locale: ptBR })} — ${format(range.to, 'dd/MM/yyyy', { locale: ptBR })}`
      : 'Escolha o período';

  const applyPreset = (daysInclusive) => {
    const to = startOfDay(new Date());
    const from = subDays(to, daysInclusive - 1);
    setRange({ from, to });
    setCalendarOpen(false);
  };

  return (
    <Card className="bg-card border-border overflow-hidden">
      <CardContent className="p-6">
        <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between mb-6 pb-4 border-b border-border/60">
          <h2 className="text-xl font-semibold text-foreground">Análise de Conversas</h2>
          <div className="flex items-center gap-3">
            <span className="text-muted-foreground text-sm">Total de atendimentos no período</span>
            <span className="text-3xl font-bold text-foreground tabular-nums">{data.totalConversations}</span>
          </div>
        </div>

        <div className="mb-6 flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
          <div className="space-y-2">
            <label className="block text-muted-foreground text-sm">Período (calendário)</label>
            <div className="flex flex-wrap items-center gap-2">
              <Popover open={calendarOpen} onOpenChange={setCalendarOpen}>
                <PopoverTrigger asChild>
                  <Button
                    type="button"
                    variant="outline"
                    className="min-w-[240px] justify-start gap-2 border-border bg-background text-left font-normal"
                  >
                    <CalendarDays className="h-4 w-4 shrink-0 text-primary" />
                    <span className="truncate">{rangeLabel}</span>
                  </Button>
                </PopoverTrigger>
                <PopoverContent className="w-auto p-0 bg-popover border-border" align="start">
                  <Calendar
                    mode="range"
                    locale={ptBR}
                    numberOfMonths={1}
                    selected={range}
                    onSelect={(r) => {
                      if (r) setRange(r);
                      if (r?.from && r?.to) setCalendarOpen(false);
                    }}
                    disabled={{ after: new Date() }}
                    defaultMonth={range?.from}
                  />
                </PopoverContent>
              </Popover>
              <div className="flex flex-wrap gap-2">
                {RANGE_PRESET_BUTTONS.map((p) => (
                  <Button
                    key={p.days}
                    type="button"
                    size="sm"
                    variant="ghost"
                    className="h-8 rounded-md border-0 px-3 text-sm font-medium shadow-sm hover:opacity-90 focus-visible:ring-2 focus-visible:ring-offset-2 focus-visible:ring-offset-background"
                    style={{ backgroundColor: p.bg, color: p.fg }}
                    onClick={() => applyPreset(p.days)}
                  >
                    {p.label}
                  </Button>
                ))}
              </div>
            </div>
            <p className="text-xs text-muted-foreground max-w-xl">
              O gráfico soma todo o volume de atendimento do provedor (conversas criadas no período), independentemente de estarem encerradas ou não.
            </p>
          </div>
        </div>

        {loading ? (
          <div className="flex items-center justify-center h-64">
            <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary" />
          </div>
        ) : showGlobalEmpty ? (
          <div className="flex items-center justify-center h-64 rounded-xl border border-dashed border-border bg-muted/20">
            <p className="text-muted-foreground text-sm">Nenhum dado disponível</p>
          </div>
        ) : (
          <div className="space-y-10">
            {hasTimeline && (
              <div>
                <h3 className="text-lg font-medium text-foreground mb-4">Volume no período</h3>
                <div className="w-full h-[min(420px,55vh)] min-h-[280px] rounded-xl border border-border/60 bg-background/30 p-2 sm:p-4">
                  <ResponsiveContainer width="100%" height="100%">
                    <BarChart data={chartRows} margin={{ top: 28, right: 12, left: 8, bottom: 8 }}>
                      <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" vertical={false} />
                      <XAxis
                        dataKey="label"
                        tick={{ fill: 'var(--muted-foreground)', fontSize: 11 }}
                        axisLine={{ stroke: 'var(--border)' }}
                        tickLine={false}
                      />
                      <YAxis
                        tick={{ fill: 'var(--muted-foreground)', fontSize: 11 }}
                        axisLine={false}
                        tickLine={false}
                        width={48}
                        allowDecimals={false}
                        label={{
                          value: 'Atendimentos',
                          angle: -90,
                          position: 'insideLeft',
                          fill: 'var(--muted-foreground)',
                          fontSize: 11,
                        }}
                      />
                      <Tooltip
                        cursor={false}
                        contentStyle={{
                          backgroundColor: 'var(--popover)',
                          border: '1px solid var(--border)',
                          borderRadius: '8px',
                          color: 'var(--popover-foreground)',
                        }}
                        formatter={(value) => [`${value} atendimentos`, 'Volume']}
                        labelFormatter={(label) => `Dia: ${label}`}
                      />
                      <Bar
                        dataKey="volume"
                        name="Atendimentos"
                        fill={BAR_ORANGE}
                        radius={[6, 6, 0, 0]}
                        maxBarSize={56}
                      >
                        <LabelList
                          dataKey="volume"
                          position="top"
                          fill="var(--foreground)"
                          fontSize={11}
                          formatter={(v) => (Number(v) > 0 ? v : '')}
                        />
                      </Bar>
                    </BarChart>
                  </ResponsiveContainer>
                </div>
              </div>
            )}

            {hasChannels && (
              <div>
                <h3 className="text-lg font-medium text-foreground mb-4">Conversas por Canal</h3>
                <div className="flex flex-col sm:flex-row items-start gap-4 rounded-lg border border-border/60 bg-background/40 p-4">
                  <div className="flex-shrink-0 mx-auto sm:mx-0">
                    <PieChart width={128} height={128}>
                      <Pie
                        data={data.channels}
                        dataKey="count"
                        nameKey="name"
                        cx="50%"
                        cy="50%"
                        innerRadius={28}
                        outerRadius={54}
                        paddingAngle={2}
                      >
                        {data.channels.map((entry, index) => (
                          <Cell key={`cell-${index}`} fill={entry.color} />
                        ))}
                      </Pie>
                      <Tooltip
                        contentStyle={{
                          backgroundColor: 'var(--popover)',
                          border: '1px solid var(--border)',
                          borderRadius: '8px',
                          color: 'var(--popover-foreground)',
                        }}
                        formatter={(value, name) => [`${value} conversas`, name]}
                      />
                    </PieChart>
                  </div>

                  <div className="flex-1 space-y-2 w-full min-w-0">
                    {data.channels.map((channel, index) => (
                      <div
                        key={index}
                        className="flex items-center justify-between rounded-md px-2 py-1.5 hover:bg-muted/40 transition-colors gap-2"
                      >
                        <div className="flex items-center gap-3 min-w-0">
                          <div
                            className="w-3 h-3 rounded-full shrink-0"
                            style={{ backgroundColor: channel.color }}
                          />
                          <span className="text-foreground/90 truncate">{channel.name}</span>
                        </div>
                        <div className="flex items-center gap-2 shrink-0">
                          <span className="text-foreground font-medium tabular-nums">{channel.count}</span>
                          <span className="text-muted-foreground text-sm">({channel.percentage})</span>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              </div>
            )}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
