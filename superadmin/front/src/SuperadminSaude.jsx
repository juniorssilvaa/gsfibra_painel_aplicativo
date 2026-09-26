import React, { useCallback, useEffect, useMemo, useState } from 'react';
import axios from 'axios';
import { Activity, RefreshCw, Search, Zap, ChevronDown, ChevronUp, Server, MessageCircle, HardDrive, AlertTriangle, Rocket } from 'lucide-react';
import { toast } from './lib/notify';

const REFRESH_MS = 60000;

const STATUS_STYLE = {
  green: { label: 'Saudável', dot: 'bg-green-500', border: 'border-green-500/40', text: 'text-green-500', chip: 'bg-green-500/10 text-green-500' },
  yellow: { label: 'Atenção', dot: 'bg-yellow-500', border: 'border-yellow-500/50', text: 'text-yellow-500', chip: 'bg-yellow-500/10 text-yellow-500' },
  red: { label: 'Crítico', dot: 'bg-red-500', border: 'border-red-500/60', text: 'text-red-500', chip: 'bg-red-500/10 text-red-500' },
};

const authHeaders = () => ({ Authorization: `Token ${localStorage.getItem('token')}` });

function timeAgo(iso) {
  if (!iso) return 'nunca';
  const diff = Math.max(0, (Date.now() - new Date(iso).getTime()) / 1000);
  if (diff < 60) return 'agora';
  if (diff < 3600) return `há ${Math.floor(diff / 60)} min`;
  if (diff < 86400) return `há ${Math.floor(diff / 3600)} h`;
  return `há ${Math.floor(diff / 86400)} dia(s)`;
}

function Metric({ icon, label, value, hint }) {
  return (
    <div className="bg-muted/50 p-3 rounded-lg border border-border">
      <p className="text-[10px] uppercase font-bold text-muted-foreground mb-1 flex items-center gap-1">{icon}{label}</p>
      <p className="text-sm font-bold text-foreground">{value}</p>
      {hint && <p className="text-[10px] text-muted-foreground mt-1">{hint}</p>}
    </div>
  );
}

function ProviderCard({ p }) {
  const [open, setOpen] = useState(false);
  const [checking, setChecking] = useState(false);
  const [live, setLive] = useState(null);
  const style = STATUS_STYLE[p.status] || STATUS_STYLE.yellow;
  const h = p.health || {};
  const conv = h.conversations || {};
  const disk = h.disk || {};
  const channels = h.channels || [];

  const runCheck = async () => {
    setChecking(true);
    try {
      const res = await axios.post(`/api/provedores/${p.id}/health-check/`, {}, { headers: authHeaders() });
      setLive(res.data);
    } catch {
      toast.error('Falha ao testar o provedor.');
    } finally {
      setChecking(false);
    }
  };

  return (
    <div className={`bg-card rounded-xl shadow-lg border-2 ${style.border} overflow-hidden`}>
      <div className="p-5">
        <div className="flex justify-between items-start gap-3">
          <div className="min-w-0">
            <div className="flex items-center gap-2">
              <span className={`w-3 h-3 rounded-full ${style.dot} shrink-0`} />
              <h3 className="font-bold text-lg text-foreground truncate">{p.nome}</h3>
            </div>
            <p className="text-xs text-muted-foreground truncate mt-0.5">{p.subdomain || 'sem subdomínio'}{p.vps ? ` · ${p.vps}` : ''}</p>
          </div>
          <span className={`text-[10px] font-bold uppercase px-2 py-1 rounded ${style.chip}`}>{style.label}</span>
        </div>

        {p.reasons.length > 0 ? (
          <ul className="mt-3 space-y-1">
            {p.reasons.map((r, i) => (
              <li key={i} className={`text-xs flex items-start gap-1.5 ${STATUS_STYLE[r.level]?.text || ''}`}>
                <AlertTriangle size={12} className="mt-0.5 shrink-0" />{r.text}
              </li>
            ))}
          </ul>
        ) : (
          <p className="mt-3 text-xs text-green-500">Tudo funcionando normalmente.</p>
        )}

        <div className="grid grid-cols-2 gap-3 mt-4">
          <Metric
            icon={<Rocket size={10} />}
            label="Versão"
            value={p.current_version || '—'}
            hint={`Canal ${p.release_channel}${p.expected_version ? ` · esperado ${p.expected_version}` : ''}`}
          />
          <Metric icon={<Activity size={10} />} label="Último sinal" value={timeAgo(p.last_seen_at)} hint={p.health ? 'com boletim' : 'só versão'} />
        </div>

        {live && (
          <div className={`mt-3 text-xs rounded-lg p-2 border ${live.ok ? 'border-green-500/40 text-green-500' : 'border-red-500/40 text-red-500'}`}>
            {live.ok
              ? `Online agora · ${live.latency_ms} ms${live.maintenance ? ' · em manutenção' : ''}`
              : `Fora do ar: ${live.error || `HTTP ${live.status_code}`}`}
          </div>
        )}

        <div className="flex gap-2 mt-4">
          <button
            onClick={runCheck}
            disabled={checking}
            className="flex-1 flex items-center justify-center gap-2 bg-primary text-white px-3 py-2 rounded-lg text-xs font-bold hover:opacity-90 disabled:opacity-60"
          >
            {checking ? <RefreshCw size={14} className="animate-spin" /> : <Zap size={14} />} Testar agora
          </button>
          <button
            onClick={() => setOpen(v => !v)}
            className="flex items-center gap-1 bg-muted text-muted-foreground px-3 py-2 rounded-lg text-xs font-bold hover:text-foreground"
          >
            Detalhes {open ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
          </button>
        </div>

        {open && (
          <div className="mt-4 space-y-3 text-xs">
            <div className="grid grid-cols-2 gap-3">
              <Metric
                icon={<MessageCircle size={10} />}
                label="Conversas"
                value={`${conv.open ?? '—'} abertas · ${conv.waiting_agent ?? '—'} na fila`}
                hint={`Última msg de cliente: ${timeAgo(conv.last_inbound_at)}`}
              />
              <Metric
                icon={<HardDrive size={10} />}
                label="Disco / Banco"
                value={disk.used_percent != null ? `${disk.used_percent}% (${disk.used_gb}/${disk.total_gb} GB)` : '—'}
                hint={h.database_mb != null ? `Banco: ${h.database_mb} MB` : null}
              />
              <Metric
                icon={<Server size={10} />}
                label="Migração Supabase"
                value={conv.pending_migration != null ? `${conv.pending_migration} pendente(s)` : '—'}
              />
              <Metric
                icon={<AlertTriangle size={10} />}
                label="Erros (1h)"
                value={h.errors_last_hour ?? '—'}
              />
            </div>

            <div>
              <p className="text-[10px] uppercase font-bold text-muted-foreground mb-1">Canais ativos</p>
              {channels.length === 0 ? (
                <p className="text-muted-foreground">Nenhum informado.</p>
              ) : (
                <ul className="space-y-1">
                  {channels.map(c => (
                    <li key={c.id} className="flex justify-between gap-2">
                      <span className="truncate">{c.nome || c.tipo} <span className="text-muted-foreground">({c.tipo}{c.somente_disparo ? ', disparo' : ''})</span></span>
                      <span className="font-mono">{c.status}</span>
                    </li>
                  ))}
                </ul>
              )}
            </div>

            {p.last_deploy && (
              <div>
                <p className="text-[10px] uppercase font-bold text-muted-foreground mb-1">Último deploy</p>
                <p>
                  {p.last_deploy.version} ({p.last_deploy.channel}) · <span className="font-mono">{p.last_deploy.status}</span> · {timeAgo(p.last_deploy.at)}
                </p>
                {p.last_deploy.message && <p className="text-red-500 mt-1">{p.last_deploy.message}</p>}
              </div>
            )}

            {(h.recent_errors || []).length > 0 && (
              <div>
                <p className="text-[10px] uppercase font-bold text-muted-foreground mb-1">Erros recentes</p>
                <ul className="space-y-1 font-mono text-[10px] text-red-400">
                  {h.recent_errors.map((e, i) => (
                    <li key={i} className="break-all">{new Date(e.at * 1000).toLocaleTimeString('pt-BR')} — {e.message}</li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

export default function SuperadminSaude() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');
  const [statusFilter, setStatusFilter] = useState('all');

  const load = useCallback(async (silent = false) => {
    if (!silent) setLoading(true);
    try {
      const res = await axios.get('/api/provedores/health-overview/', { headers: authHeaders() });
      setData(res.data);
    } catch {
      if (!silent) toast.error('Erro ao carregar a saúde dos provedores.');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
    const id = setInterval(() => load(true), REFRESH_MS);
    return () => clearInterval(id);
  }, [load]);

  const providers = useMemo(() => {
    const term = search.trim().toLowerCase();
    return (data?.providers || []).filter(p =>
      (statusFilter === 'all' || p.status === statusFilter) &&
      (!term || p.nome.toLowerCase().includes(term) || (p.subdomain || '').toLowerCase().includes(term))
    );
  }, [data, search, statusFilter]);

  const summary = data?.summary || { green: 0, yellow: 0, red: 0 };

  return (
    <div className="flex-1 p-6 bg-background overflow-y-auto">
      <div className="flex justify-between items-center mb-6 gap-4 flex-wrap">
        <div>
          <h1 className="text-3xl font-bold text-foreground mb-2 flex items-center gap-3">
            <Activity className="w-8 h-8 text-primary" />
            Saúde dos Provedores
          </h1>
          <p className="text-muted-foreground">
            Status de cada provedor pelo último boletim (enviado a cada 5 min).
            {data?.generated_at && ` Atualizado ${timeAgo(data.generated_at)}.`}
          </p>
        </div>
        <button
          onClick={() => load()}
          className="flex items-center gap-2 bg-muted text-foreground px-4 py-2 rounded-lg font-bold hover:bg-muted/70"
        >
          <RefreshCw size={16} className={loading ? 'animate-spin' : ''} /> Atualizar
        </button>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 mb-6">
        {['red', 'yellow', 'green'].map(level => (
          <button
            key={level}
            onClick={() => setStatusFilter(statusFilter === level ? 'all' : level)}
            className={`bg-card rounded-xl border-2 p-4 text-left transition ${statusFilter === level ? STATUS_STYLE[level].border : 'border-border'}`}
          >
            <p className={`text-xs font-bold uppercase ${STATUS_STYLE[level].text}`}>{STATUS_STYLE[level].label}</p>
            <p className="text-3xl font-bold text-foreground mt-1">{summary[level] || 0}</p>
          </button>
        ))}
      </div>

      <div className="relative mb-6 max-w-md">
        <Search size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" />
        <input
          value={search}
          onChange={e => setSearch(e.target.value)}
          placeholder="Buscar provedor ou subdomínio"
          className="w-full pl-9 pr-3 py-2 rounded-lg bg-card border border-border text-foreground text-sm"
        />
      </div>

      {loading && !data ? (
        <div className="flex justify-center p-12">
          <RefreshCw className="animate-spin text-primary w-8 h-8" />
        </div>
      ) : providers.length === 0 ? (
        <div className="py-12 text-center bg-card/50 rounded-xl border border-dashed border-border text-muted-foreground">
          Nenhum provedor encontrado.
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-6">
          {providers.map(p => <ProviderCard key={p.id} p={p} />)}
        </div>
      )}
    </div>
  );
}
