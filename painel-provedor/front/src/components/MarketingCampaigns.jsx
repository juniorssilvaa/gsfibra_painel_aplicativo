import { useCallback, useEffect, useState } from 'react';
import axios from 'axios';
import {
  BarChart3,
  ChevronDown,
  ChevronUp,
  ExternalLink,
  Loader2,
  Pause,
  Pencil,
  Play,
  Plus,
  RefreshCw,
  AlertTriangle,
  ImageOff,
} from 'lucide-react';
import { authHeaders, errorText } from '../utils/marketingApi';

const PERIOD_OPTIONS = [
  ['hoje', 'Hoje'],
  ['ontem', 'Ontem'],
  ['7d', 'Últimos 7 dias'],
  ['14d', 'Últimos 14 dias'],
  ['30d', 'Últimos 30 dias'],
  ['90d', 'Últimos 90 dias'],
  ['maximo', 'Todo o período'],
];

const STATUS = {
  ACTIVE: ['Ativa', 'bg-green-500/15 text-green-600 dark:text-green-400 border-green-500/30'],
  PAUSED: ['Pausada', 'bg-muted text-muted-foreground border-border'],
  CAMPAIGN_PAUSED: ['Campanha pausada', 'bg-muted text-muted-foreground border-border'],
  ADSET_PAUSED: ['Conjunto pausado', 'bg-muted text-muted-foreground border-border'],
  IN_PROCESS: ['Em análise', 'bg-blue-500/15 text-blue-500 border-blue-500/30'],
  PENDING_REVIEW: ['Em análise', 'bg-blue-500/15 text-blue-500 border-blue-500/30'],
  PREAPPROVED: ['Pré-aprovado', 'bg-blue-500/15 text-blue-500 border-blue-500/30'],
  WITH_ISSUES: ['Com problema', 'bg-amber-500/15 text-amber-500 border-amber-500/30'],
  PENDING_BILLING_INFO: ['Pagamento pendente', 'bg-amber-500/15 text-amber-500 border-amber-500/30'],
  DISAPPROVED: ['Reprovado', 'bg-red-500/15 text-red-500 border-red-500/30'],
};

const OBJECTIVES = {
  OUTCOME_ENGAGEMENT: 'Engajamento',
  OUTCOME_TRAFFIC: 'Tráfego',
  OUTCOME_LEADS: 'Cadastros',
  OUTCOME_SALES: 'Vendas',
  OUTCOME_AWARENESS: 'Reconhecimento',
  OUTCOME_APP_PROMOTION: 'Promoção de app',
  MESSAGES: 'Mensagens',
  LINK_CLICKS: 'Tráfego',
  CONVERSIONS: 'Conversões',
  REACH: 'Alcance',
  BRAND_AWARENESS: 'Reconhecimento',
  POST_ENGAGEMENT: 'Engajamento',
  LEAD_GENERATION: 'Cadastros',
};

const CTAS = {
  WHATSAPP_MESSAGE: 'Enviar mensagem no WhatsApp',
  MESSAGE_PAGE: 'Enviar mensagem',
  LEARN_MORE: 'Saiba mais',
  SIGN_UP: 'Cadastre-se',
  CONTACT_US: 'Fale conosco',
  SUBSCRIBE: 'Assinar',
  SHOP_NOW: 'Comprar',
  GET_OFFER: 'Ver oferta',
};

function money(value, currency) {
  if (value === undefined || value === null) return '—';
  return new Intl.NumberFormat('pt-BR', { style: 'currency', currency: currency || 'BRL' }).format(value);
}

function count(value) {
  return value === undefined || value === null ? '—' : Number(value).toLocaleString('pt-BR');
}

function shortDate(iso) {
  if (!iso) return '';
  const [y, m, d] = iso.split('-');
  return `${d}/${m}/${y}`;
}

function result(m) {
  if (m.conversas_iniciadas !== undefined) {
    return { label: 'Conversas', value: m.conversas_iniciadas, cost: m.custo_por_conversas_iniciadas, costLabel: 'Custo por conversa' };
  }
  if (m.cliques_no_link !== undefined) {
    return { label: 'Cliques no link', value: m.cliques_no_link, cost: m.custo_por_cliques_no_link, costLabel: 'Custo por clique' };
  }
  return null;
}

function StatusBadge({ status }) {
  const [label, cls] = STATUS[status] || [status || '—', 'bg-muted text-muted-foreground border-border'];
  return <span className={`px-2 py-0.5 rounded-md border text-[11px] font-medium whitespace-nowrap ${cls}`}>{label}</span>;
}

const DELIVERY_COLORS = {
  veiculando: ['bg-green-500', 'text-green-600 dark:text-green-400'],
  em_analise: ['bg-blue-500', 'text-blue-500'],
  agendada: ['bg-blue-500', 'text-blue-500'],
  com_problema: ['bg-amber-500', 'text-amber-500'],
  pagamento: ['bg-amber-500', 'text-amber-500'],
  reprovada: ['bg-red-500', 'text-red-500'],
  bloqueada: ['bg-red-500', 'text-red-500'],
};

function Delivery({ delivery }) {
  if (!delivery) return <Metric label="Veiculação" value="—" />;
  const [dot, text] = DELIVERY_COLORS[delivery.codigo] || ['bg-muted-foreground', 'text-muted-foreground'];
  return (
    <div className="min-w-0" title={delivery.detalhe || delivery.rotulo}>
      <p className="text-[11px] text-muted-foreground truncate">Veiculação</p>
      <p className={`text-sm font-semibold truncate inline-flex items-center gap-1.5 max-w-full ${text}`}>
        <span className={`w-2 h-2 rounded-full shrink-0 ${dot}`} />
        <span className="truncate">{delivery.rotulo}</span>
      </p>
      {delivery.detalhe && <p className="text-[10px] text-muted-foreground line-clamp-2">{delivery.detalhe}</p>}
    </div>
  );
}

function Metric({ label, value }) {
  return (
    <div className="min-w-0">
      <p className="text-[11px] text-muted-foreground truncate">{label}</p>
      <p className="text-sm font-semibold truncate">{value}</p>
    </div>
  );
}

function AdCard({ ad, currency }) {
  const [imgFailed, setImgFailed] = useState(false);
  const m = ad.metricas || {};
  const res = result(m);
  return (
    <div className="rounded-lg border border-border bg-background overflow-hidden flex flex-col">
      {ad.imagem && !imgFailed ? (
        <img
          src={ad.imagem}
          alt={ad.titulo || ad.nome}
          className="w-full aspect-square object-cover bg-muted"
          loading="lazy"
          referrerPolicy="no-referrer"
          onError={() => setImgFailed(true)}
        />
      ) : (
        <div className="w-full aspect-square flex items-center justify-center bg-muted text-muted-foreground">
          <ImageOff className="w-8 h-8" />
        </div>
      )}
      <div className="p-3 space-y-2 flex-1 flex flex-col">
        <div className="flex items-start justify-between gap-2">
          <p className="text-xs text-muted-foreground truncate" title={ad.nome}>{ad.nome}</p>
          <StatusBadge status={ad.status} />
        </div>
        {ad.problema && (
          <p className="flex items-start gap-1 text-[11px] text-amber-500">
            <AlertTriangle className="w-3.5 h-3.5 mt-px shrink-0" /> {ad.problema}
          </p>
        )}
        {ad.titulo && <p className="text-sm font-semibold leading-snug">{ad.titulo}</p>}
        {ad.texto && <p className="text-xs text-muted-foreground whitespace-pre-line line-clamp-4">{ad.texto}</p>}
        {ad.botao && (
          <p className="text-[11px] text-primary">Botão: {CTAS[ad.botao] || ad.botao}</p>
        )}
        <div className="mt-auto pt-2 grid grid-cols-3 gap-2 border-t border-border">
          <Metric label="Investido" value={money(m.gasto, currency)} />
          <Metric label="Alcance" value={count(m.alcance)} />
          <Metric label={res?.label || 'Cliques'} value={count(res ? res.value : m.cliques)} />
        </div>
      </div>
    </div>
  );
}

function CampaignCard({ campaign, currency, accountId, busy, onAnalyze, onEdit, onToggle }) {
  const [open, setOpen] = useState(false);
  const m = campaign.metricas || {};
  const res = result(m);
  const isActive = campaign.status === 'ACTIVE';
  const canToggle = ['ACTIVE', 'PAUSED'].includes(campaign.status);
  const managerUrl = `https://adsmanager.facebook.com/adsmanager/manage/campaigns?act=${String(accountId || '').replace('act_', '')}&selected_campaign_ids=${campaign.id}`;
  const budget = campaign.orcamento
    ? `${campaign.orcamento}${campaign.orcamento_tipo === 'diario' ? '/dia' : ' no total'}${campaign.orcamento_nivel === 'conjunto' ? ' (no conjunto)' : ''}`
    : 'Sem orçamento definido';
  const period = [campaign.inicio && `Início ${shortDate(campaign.inicio)}`, campaign.fim && `Fim ${shortDate(campaign.fim)}`]
    .filter(Boolean)
    .join(' · ');

  return (
    <div className="rounded-xl border border-border bg-card">
      <div className="p-4 space-y-3">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="min-w-0 flex-1">
            <div className="flex flex-wrap items-center gap-2">
              <h3 className="font-semibold truncate max-w-full" title={campaign.nome}>{campaign.nome}</h3>
              <StatusBadge status={campaign.status} />
            </div>
            <p className="text-xs text-muted-foreground mt-1">
              {OBJECTIVES[campaign.objetivo] || campaign.objetivo} · {budget}
              {period ? ` · ${period}` : ''}
            </p>
          </div>
          <div className="flex flex-wrap gap-1.5">
            <button
              type="button"
              onClick={() => onAnalyze(campaign)}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs bg-primary/15 text-primary hover:bg-primary/25"
            >
              <BarChart3 className="w-3.5 h-3.5" /> Analisar com IA
            </button>
            <button
              type="button"
              onClick={() => onEdit(campaign)}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs bg-muted hover:bg-muted/80"
            >
              <Pencil className="w-3.5 h-3.5" /> Editar com IA
            </button>
            {canToggle && (
              <button
                type="button"
                disabled={busy}
                onClick={() => onToggle(campaign)}
                className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs bg-muted hover:bg-muted/80 disabled:opacity-50"
              >
                {busy ? (
                  <Loader2 className="w-3.5 h-3.5 animate-spin" />
                ) : isActive ? (
                  <Pause className="w-3.5 h-3.5" />
                ) : (
                  <Play className="w-3.5 h-3.5" />
                )}
                {isActive ? 'Pausar' : 'Ativar'}
              </button>
            )}
            <a
              href={managerUrl}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs bg-muted hover:bg-muted/80"
              title="Abrir no Gerenciador de Anúncios da Meta"
            >
              <ExternalLink className="w-3.5 h-3.5" /> Gerenciador
            </a>
          </div>
        </div>

        <div className="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-7 gap-3 rounded-lg bg-muted/40 px-3 py-2">
          <Delivery delivery={campaign.veiculacao} />
          <Metric label="Investido" value={money(m.gasto, currency)} />
          <Metric label="Alcance" value={count(m.alcance)} />
          <Metric label="Impressões" value={count(m.impressoes)} />
          <Metric label="CTR" value={m['ctr_%'] !== undefined ? `${m['ctr_%'].toLocaleString('pt-BR')}%` : '—'} />
          <Metric label={res?.label || 'Cliques'} value={count(res ? res.value : m.cliques)} />
          <Metric label={res?.costLabel || 'Custo por clique'} value={money(res ? res.cost : m.cpc, currency)} />
        </div>

        {campaign.anuncios.length > 0 && (
          <button
            type="button"
            onClick={() => setOpen((v) => !v)}
            className="inline-flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground"
          >
            {open ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
            {open ? 'Ocultar anúncios' : `Ver anúncios (${campaign.anuncios.length})`}
          </button>
        )}
      </div>
      {open && (
        <div className="border-t border-border p-4 grid gap-3 grid-cols-1 sm:grid-cols-2 xl:grid-cols-3">
          {campaign.anuncios.map((ad) => (
            <AdCard key={ad.id} ad={ad} currency={currency} />
          ))}
        </div>
      )}
    </div>
  );
}

export default function MarketingCampaigns({ provedorId, accountId, onAnalyze, onEdit, onNewCampaign, onError }) {
  const [periodo, setPeriodo] = useState('30d');
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [loadError, setLoadError] = useState('');
  const [busyId, setBusyId] = useState(null);

  const load = useCallback(async () => {
    setLoading(true);
    setLoadError('');
    try {
      const res = await axios.get('/api/marketing/meta/campaigns/', {
        headers: authHeaders(),
        params: { provedor_id: provedorId, periodo },
        skipErrorToast: true,
      });
      setData(res.data);
    } catch (err) {
      setLoadError(errorText(err, 'Não foi possível carregar as campanhas da Meta.'));
    } finally {
      setLoading(false);
    }
  }, [provedorId, periodo]);

  useEffect(() => {
    load();
  }, [load]);

  const toggle = async (campaign) => {
    const activate = campaign.status !== 'ACTIVE';
    const question = activate
      ? `Ativar a campanha "${campaign.nome}"? Ela volta a gastar o orçamento${campaign.orcamento ? ` de ${campaign.orcamento}` : ''}.`
      : `Pausar a campanha "${campaign.nome}"? Os anúncios param de rodar até você ativar de novo.`;
    if (!window.confirm(question)) return;
    setBusyId(campaign.id);
    try {
      await axios.post(
        `/api/marketing/meta/campaigns/${campaign.id}/status/`,
        { status: activate ? 'ACTIVE' : 'PAUSED' },
        { headers: authHeaders(), params: { provedor_id: provedorId }, skipErrorToast: true }
      );
      await load();
    } catch (err) {
      onError(errorText(err, 'Não foi possível alterar a campanha.'));
    } finally {
      setBusyId(null);
    }
  };

  const periodLabel = PERIOD_OPTIONS.find(([key]) => key === periodo)?.[1] || periodo;
  const currency = data?.moeda || 'BRL';
  const total = data?.total || {};
  const totalResult = result(total);

  return (
    <div className="flex-1 min-h-0 overflow-y-auto p-4 md:px-6 space-y-4">
      <div className="flex flex-wrap items-center gap-2">
        <select
          value={periodo}
          onChange={(e) => setPeriodo(e.target.value)}
          className="px-3 py-2 rounded-md border border-border bg-background text-sm"
        >
          {PERIOD_OPTIONS.map(([key, label]) => (
            <option key={key} value={key}>
              {label}
            </option>
          ))}
        </select>
        <button
          type="button"
          onClick={load}
          disabled={loading}
          className="inline-flex items-center gap-1.5 px-3 py-2 rounded-md text-sm bg-muted hover:bg-muted/80 disabled:opacity-50"
        >
          <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} /> Atualizar
        </button>
        <div className="flex-1" />
        <button
          type="button"
          onClick={onNewCampaign}
          className="inline-flex items-center gap-1.5 px-4 py-2 rounded-md text-sm bg-primary text-primary-foreground"
        >
          <Plus className="w-4 h-4" /> Nova campanha com IA
        </button>
      </div>

      {loadError && (
        <div className="rounded-lg border border-red-500/40 bg-red-500/10 px-3 py-2 text-sm text-red-500 flex flex-wrap items-center justify-between gap-2">
          <span>{loadError}</span>
          <button type="button" onClick={load} className="underline">
            Tentar de novo
          </button>
        </div>
      )}

      {!data && loading && (
        <div className="py-16 flex flex-col items-center gap-2 text-muted-foreground">
          <Loader2 className="w-8 h-8 animate-spin" />
          <p className="text-sm">Buscando suas campanhas na Meta…</p>
        </div>
      )}

      {data && (
        <>
          <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3">
            {[
              ['Investido', money(total.gasto, currency)],
              ['Alcance', count(total.alcance)],
              ['Impressões', count(total.impressoes)],
              ['Cliques no link', count(total.cliques_no_link)],
              ['Conversas iniciadas', count(total.conversas_iniciadas)],
              [totalResult?.costLabel || 'Custo por resultado', money(totalResult?.cost, currency)],
            ].map(([label, value]) => (
              <div key={label} className="rounded-xl border border-border bg-card px-4 py-3">
                <p className="text-xs text-muted-foreground">{label}</p>
                <p className="text-lg font-bold">{value}</p>
              </div>
            ))}
          </div>
          <p className="text-xs text-muted-foreground">
            Resultados de: {periodLabel.toLowerCase()} · {data.campanhas.length} campanha(s) na conta
          </p>

          {data.campanhas.length === 0 ? (
            <div className="rounded-xl border border-dashed border-border p-10 text-center space-y-3">
              <p className="font-medium">Nenhuma campanha nesta conta de anúncios ainda.</p>
              <button
                type="button"
                onClick={onNewCampaign}
                className="inline-flex items-center gap-1.5 px-4 py-2 rounded-md text-sm bg-primary text-primary-foreground"
              >
                <Plus className="w-4 h-4" /> Criar a primeira campanha com a IA
              </button>
            </div>
          ) : (
            <div className="space-y-3">
              {data.campanhas.map((c) => (
                <CampaignCard
                  key={c.id}
                  campaign={c}
                  currency={currency}
                  accountId={accountId}
                  busy={busyId === c.id}
                  onAnalyze={(campaign) => onAnalyze(campaign, periodo, periodLabel)}
                  onEdit={onEdit}
                  onToggle={toggle}
                />
              ))}
            </div>
          )}
        </>
      )}
    </div>
  );
}
