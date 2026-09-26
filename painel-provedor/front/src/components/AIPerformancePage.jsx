import React, { useCallback, useEffect, useState } from 'react';
import axios from 'axios';
import { Brain, RefreshCw, Lightbulb, CheckCircle, ArrowRightLeft, UserX } from 'lucide-react';
import AILearningKnowledge from './AILearningKnowledge';
import ConversationRecovery from './ConversationRecovery';

const TABS = [
  { id: 'learning', label: 'Aprendizado da IA', Icon: Brain },
  { id: 'recovery', label: 'Recuperador de conversas', Icon: RefreshCw },
];

const PERIODS = [
  { id: 'today', label: 'Hoje' },
  { id: '7d', label: '7 dias' },
  { id: '30d', label: '30 dias' },
];

const OUTCOME_LABELS = {
  ai_transferred: 'IA transferiu',
  agent_took_over: 'Atendente assumiu',
};

const CHANNEL_LABELS = {
  whatsapp: 'WhatsApp',
  whatsapp_oficial: 'WhatsApp Oficial',
  instagram: 'Instagram',
  telegram: 'Telegram',
  email: 'E-mail',
  app_mobile: 'App',
  webchat: 'Webchat',
};

function formatDateTime(iso) {
  if (!iso) return '—';
  const date = new Date(iso);
  return Number.isNaN(date.getTime())
    ? '—'
    : date.toLocaleString('pt-BR', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' });
}

function MetricCard({ label, Icon, color, value, hint }) {
  const empty = value === null || value === undefined;
  return (
    <div className="bg-card rounded-lg border p-4">
      <div className="flex items-center gap-2">
        <Icon className={`w-5 h-5 ${color}`} />
        <span className="text-sm text-muted-foreground">{label}</span>
      </div>
      <div className={`text-2xl font-bold mt-2 ${empty ? 'text-muted-foreground' : 'text-foreground'}`}>
        {empty ? '—' : value}
      </div>
      {hint && <div className="text-xs text-muted-foreground mt-1">{hint}</div>}
    </div>
  );
}

function AILearningTab({ provedorId }) {
  const [period, setPeriod] = useState('today');
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError(false);
    try {
      const token = localStorage.getItem('token');
      const params = new URLSearchParams({ period });
      if (provedorId) params.set('provedor_id', provedorId);
      const res = await axios.get(`/api/ai-learning/metrics/?${params}`, {
        headers: { Authorization: `Token ${token}` },
        skipErrorToast: true,
      });
      setData(res.data);
    } catch (_) {
      setError(true);
    } finally {
      setLoading(false);
    }
  }, [period, provedorId]);

  useEffect(() => {
    load();
  }, [load]);

  const rate = data?.ai_resolution_rate;
  const metrics = [
    {
      label: 'Atendimentos analisados',
      Icon: Brain,
      color: 'text-blue-500',
      value: data?.analyzed,
      hint: rate !== null && rate !== undefined ? `${rate}% resolvidos só pela IA` : null,
    },
    {
      label: 'Aprendizados sugeridos',
      Icon: Lightbulb,
      color: 'text-yellow-500',
      value: data?.suggested,
      hint: 'Aguardando sua revisão',
    },
    {
      label: 'Aprendizados aprovados',
      Icon: CheckCircle,
      color: 'text-green-500',
      value: data?.approved,
      hint: 'Ativos para a IA',
    },
    {
      label: 'Transferências da IA',
      Icon: ArrowRightLeft,
      color: 'text-orange-500',
      value: data?.ai_transfers,
      hint: 'A IA passou para um humano',
    },
    {
      label: 'Correções dos atendentes',
      Icon: UserX,
      color: 'text-red-500',
      value: data?.agent_corrections,
      hint: 'Atendente assumiu da IA',
    },
  ];

  const reasons = data?.top_transfer_reasons || [];
  const candidates = data?.recent_candidates || [];

  return (
    <div>
      <div className="mb-6 flex flex-wrap items-start justify-between gap-4">
        <div>
          <h2 className="text-xl font-semibold text-foreground mb-1 flex items-center gap-2">
            Aprendizado da IA
            <span className="px-2 py-0.5 rounded-md border border-green-500/40 bg-green-500/15 text-green-600 dark:text-green-400 text-xs font-semibold uppercase tracking-wide">
              Beta
            </span>
          </h2>
          <p className="text-muted-foreground">
            Acompanhe o que a IA aprende com os atendimentos do seu provedor: padrões identificados, correções dos
            atendentes e os aprendizados aprovados por você.
          </p>
        </div>
        <div className="flex items-center gap-2">
          {PERIODS.map(({ id, label }) => (
            <button
              key={id}
              type="button"
              onClick={() => setPeriod(id)}
              className={`px-3 py-1.5 rounded-md text-sm border transition-colors ${
                period === id
                  ? 'bg-primary text-primary-foreground border-primary'
                  : 'border-border text-muted-foreground hover:text-foreground'
              }`}
            >
              {label}
            </button>
          ))}
          <button
            type="button"
            onClick={load}
            title="Atualizar"
            className="p-2 rounded-md border border-border text-muted-foreground hover:text-foreground"
          >
            <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
          </button>
        </div>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-4 mb-6">
        {metrics.map((m) => (
          <MetricCard key={m.label} {...m} value={loading && !data ? null : m.value} />
        ))}
      </div>

      {error ? (
        <div className="bg-card rounded-lg border p-8 text-center text-sm text-muted-foreground">
          Não foi possível carregar as métricas de aprendizado. Tente atualizar.
        </div>
      ) : data && data.analyzed === 0 ? (
        <div className="bg-card rounded-lg border p-8 text-center">
          <Brain className="w-10 h-10 mx-auto mb-3 text-muted-foreground/60" />
          <h3 className="text-lg font-semibold text-foreground mb-1">Nenhum atendimento analisado no período</h3>
          <p className="text-sm text-muted-foreground max-w-lg mx-auto">
            Os atendimentos encerrados são analisados automaticamente a cada 10 minutos. Os números aparecem aqui
            conforme a IA e a equipe atendem.
          </p>
        </div>
      ) : data ? (
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
          <div className="bg-card rounded-lg border p-4">
            <h3 className="font-semibold text-foreground mb-3">Principais motivos de transferência</h3>
            {reasons.length === 0 ? (
              <p className="text-sm text-muted-foreground">Nenhuma transferência da IA no período.</p>
            ) : (
              <ul className="space-y-2">
                {reasons.map(({ reason, count }) => (
                  <li key={reason} className="flex items-start justify-between gap-3 text-sm">
                    <span className="text-foreground">{reason}</span>
                    <span className="shrink-0 font-semibold text-orange-500">{count}</span>
                  </li>
                ))}
              </ul>
            )}
          </div>

          <div className="bg-card rounded-lg border p-4 lg:col-span-2">
            <h3 className="font-semibold text-foreground mb-1">Atendimentos para aprendizado</h3>
            <p className="text-xs text-muted-foreground mb-3">
              Onde a IA precisou de ajuda humana. A IA analisa esses atendimentos e sugere aprendizados para você
              aprovar.
            </p>
            {candidates.length === 0 ? (
              <p className="text-sm text-muted-foreground">Nenhum atendimento com ajuda humana no período.</p>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="text-left text-muted-foreground border-b border-border">
                      <th className="py-2 pr-3 font-medium">Encerrado</th>
                      <th className="py-2 pr-3 font-medium">Contato</th>
                      <th className="py-2 pr-3 font-medium">Canal</th>
                      <th className="py-2 pr-3 font-medium">Resultado</th>
                      <th className="py-2 font-medium">Motivo</th>
                    </tr>
                  </thead>
                  <tbody>
                    {candidates.map((c) => (
                      <tr key={c.conversation_id} className="border-b border-border/50 last:border-0">
                        <td className="py-2 pr-3 whitespace-nowrap text-muted-foreground">{formatDateTime(c.closed_at)}</td>
                        <td className="py-2 pr-3 text-foreground">{c.contact_name}</td>
                        <td className="py-2 pr-3 text-muted-foreground">{CHANNEL_LABELS[c.channel_type] || c.channel_type || '—'}</td>
                        <td className="py-2 pr-3">
                          <span className={c.outcome === 'ai_transferred' ? 'text-orange-500' : 'text-red-500'}>
                            {OUTCOME_LABELS[c.outcome] || c.outcome}
                          </span>
                        </td>
                        <td className="py-2 text-muted-foreground">{c.transfer_reason || '—'}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </div>
      ) : null}

      <AILearningKnowledge
        provedorId={provedorId}
        counts={{ suggested: data?.suggested, approved: data?.approved }}
        onChanged={load}
      />
    </div>
  );
}

export default function AIPerformancePage({ provedorId }) {
  const [activeTab, setActiveTab] = useState('learning');

  return (
    <div className="p-6">
      <div className="mb-6">
        <h1 className="text-3xl font-bold text-foreground mb-2">Desempenho da IA</h1>
        <p className="text-muted-foreground">
          Métricas do aprendizado da IA e recuperação de conversas do seu provedor.
        </p>
      </div>

      <div className="flex gap-2 border-b border-border mb-6">
        {TABS.map(({ id, label, Icon }) => (
          <button
            key={id}
            type="button"
            onClick={() => setActiveTab(id)}
            className={`flex items-center gap-2 px-4 py-2 -mb-px border-b-2 text-sm font-medium transition-colors ${
              activeTab === id
                ? 'border-primary text-primary'
                : 'border-transparent text-muted-foreground hover:text-foreground'
            }`}
          >
            <Icon className="w-4 h-4" />
            {label}
          </button>
        ))}
      </div>

      {activeTab === 'learning' ? (
        <AILearningTab provedorId={provedorId} />
      ) : (
        <ConversationRecovery provedorId={provedorId} embedded />
      )}
    </div>
  );
}
