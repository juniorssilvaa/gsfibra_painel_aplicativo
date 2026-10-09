import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import axios from 'axios';
import {
  Megaphone,
  Plus,
  ArrowLeft,
  Trash2,
  Loader2,
  Upload,
  Send,
  CalendarClock,
  XCircle,
  Search,
  RefreshCw,
  Video,
  Image as ImageIcon,
  FileText,
  LayoutTemplate,
} from 'lucide-react';
import { toast } from '../lib/notify';
import { MetaTemplateCard, MetaTemplatePreview } from './MetaTemplateCard';
import { TEMPLATE_CARD_STYLES } from '../utils/metaTemplatePreview';

const STATUS_LABELS = {
  rascunho: 'Rascunho',
  agendada: 'Agendada',
  enviando: 'Enviando',
  concluida: 'Concluída',
  cancelada: 'Cancelada',
  falhou: 'Falhou',
};
const STATUS_COLORS = {
  rascunho: 'bg-muted text-muted-foreground',
  agendada: 'bg-blue-500/15 text-blue-500',
  enviando: 'bg-amber-500/15 text-amber-500',
  concluida: 'bg-green-500/15 text-green-500',
  cancelada: 'bg-muted text-muted-foreground',
  falhou: 'bg-red-500/15 text-red-500',
};
const RECIPIENT_LABELS = { pendente: 'Pendente', enviado: 'Enviado', falhou: 'Falhou', ignorado: 'Ignorado' };
const RECIPIENT_COLORS = {
  pendente: 'text-muted-foreground',
  enviado: 'text-green-500',
  falhou: 'text-red-500',
  ignorado: 'text-amber-500',
};
const EDITABLE = ['rascunho', 'agendada'];
const BASE_VARS = ['nome', 'primeiro_nome', 'telefone'];
const POLL_MS = 4000;

const inputCls = 'w-full px-3 py-2 rounded-md border border-border bg-background text-sm focus:outline-none focus:ring-2 focus:ring-primary/30';
const btnPrimary = 'inline-flex items-center justify-center gap-2 px-4 py-2 rounded-md text-sm font-medium bg-primary text-primary-foreground hover:bg-primary/90 disabled:opacity-50';
const btnMuted = 'inline-flex items-center justify-center gap-2 px-3 py-2 rounded-md text-sm bg-muted hover:bg-muted/80 disabled:opacity-50';

function authHeaders() {
  const token = localStorage.getItem('auth_token') || localStorage.getItem('token');
  return token ? { Authorization: `Token ${token}` } : {};
}

function api(method, url, provedorId, { params, data, headers } = {}) {
  return axios({
    method,
    url,
    params: { provedor_id: provedorId, ...(params || {}) },
    data,
    headers: { ...authHeaders(), ...(headers || {}) },
    skipErrorToast: true,
  });
}

function errorText(err, fallback) {
  return err?.response?.data?.error || fallback;
}

function formatDate(iso) {
  if (!iso) return '—';
  return new Date(iso).toLocaleString('pt-BR', { dateStyle: 'short', timeStyle: 'short' });
}

function ScheduleCell({ campaign: c }) {
  if (c.status === 'agendada') return formatDate(c.agendada_para);
  if (!c.agendada_para) return '—';
  if (!c.iniciada_em) return <span className="text-muted-foreground">agendada para {formatDate(c.agendada_para)}</span>;
  return `Enviada em ${formatDate(c.iniciada_em)}`;
}

function toLocalInput(iso) {
  if (!iso) return '';
  const d = new Date(iso);
  const pad = (n) => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

function renderPreview(text, vars) {
  return (text || '').replace(/\{([^{}\s]{1,60})\}/g, (m, key) => (key in vars ? vars[key] : m));
}

function StatusBadge({ status }) {
  return (
    <span className={`inline-flex px-2 py-0.5 rounded text-xs font-medium ${STATUS_COLORS[status] || ''}`}>
      {STATUS_LABELS[status] || status}
    </span>
  );
}

function Progress({ contagem }) {
  const total = contagem?.total || 0;
  const done = (contagem?.enviado || 0) + (contagem?.falhou || 0) + (contagem?.ignorado || 0);
  const pct = total ? Math.round((done / total) * 100) : 0;
  return (
    <div className="min-w-[140px]">
      <div className="h-1.5 rounded bg-muted overflow-hidden">
        <div className="h-full bg-primary transition-all" style={{ width: `${pct}%` }} />
      </div>
      <div className="text-xs text-muted-foreground mt-1">
        {contagem?.enviado || 0} enviados de {total}
        {contagem?.falhou ? ` · ${contagem.falhou} falharam` : ''}
      </div>
    </div>
  );
}

function Section({ title, step, children, disabled }) {
  return (
    <section className={`bg-card border border-border rounded-xl p-5 ${disabled ? 'opacity-60 pointer-events-none' : ''}`}>
      <h2 className="font-semibold mb-4 flex items-center gap-2">
        <span className="w-6 h-6 rounded-full bg-primary/15 text-primary text-xs flex items-center justify-center">{step}</span>
        {title}
      </h2>
      {children}
    </section>
  );
}

function CampaignList({ provedorId, onOpen, onNew }) {
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  const load = useCallback(async () => {
    try {
      const res = await api('get', '/api/campanhas/', provedorId);
      setItems(res.data.results || []);
      setError('');
    } catch (err) {
      setError(errorText(err, 'Não foi possível carregar as campanhas.'));
    } finally {
      setLoading(false);
    }
  }, [provedorId]);

  useEffect(() => {
    load();
    const timer = setInterval(load, POLL_MS * 2);
    return () => clearInterval(timer);
  }, [load]);

  const remove = async (c) => {
    if (!window.confirm(`Excluir a campanha "${c.nome}"?`)) return;
    try {
      await api('delete', `/api/campanhas/${c.id}/`, provedorId);
      toast.deleted('Campanha excluída.');
      load();
    } catch (err) {
      toast.error(errorText(err, 'Não foi possível excluir.'));
    }
  };

  return (
    <div className="p-6 w-full">
      <div className="flex items-center justify-between gap-4 mb-6">
        <h1 className="text-2xl font-bold flex items-center gap-2"><Megaphone className="w-6 h-6" /> Campanhas</h1>
        <button type="button" className={btnPrimary} onClick={onNew}><Plus className="w-4 h-4" /> Nova campanha</button>
      </div>
      {error && <div className="mb-4 p-3 rounded-md bg-red-500/10 text-red-500 text-sm">{error}</div>}
      {loading ? (
        <div className="flex justify-center py-16"><Loader2 className="w-6 h-6 animate-spin" /></div>
      ) : items.length === 0 ? (
        <div className="text-center py-16 border border-dashed border-border rounded-xl text-muted-foreground">
          Nenhuma campanha ainda. Clique em “Nova campanha” para começar.
        </div>
      ) : (
        <div className="bg-card border border-border rounded-xl overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="text-left text-muted-foreground border-b border-border">
              <tr>
                <th className="px-4 py-3 font-medium">Campanha</th>
                <th className="px-4 py-3 font-medium">Canal</th>
                <th className="px-4 py-3 font-medium">Status</th>
                <th className="px-4 py-3 font-medium">Progresso</th>
                <th className="px-4 py-3 font-medium">Agendada para</th>
                <th className="px-4 py-3" />
              </tr>
            </thead>
            <tbody>
              {items.map((c) => (
                <tr key={c.id} className="border-b border-border last:border-0 hover:bg-muted/40 cursor-pointer" onClick={() => onOpen(c.id)}>
                  <td className="px-4 py-3 font-medium">{c.nome}</td>
                  <td className="px-4 py-3">{c.canal ? `${c.canal.tipo_label} · ${c.canal.nome}` : '—'}</td>
                  <td className="px-4 py-3"><StatusBadge status={c.status} /></td>
                  <td className="px-4 py-3"><Progress contagem={c.contagem} /></td>
                  <td className="px-4 py-3"><ScheduleCell campaign={c} /></td>
                  <td className="px-4 py-3 text-right">
                    {c.status !== 'enviando' && (
                      <button
                        type="button"
                        title="Excluir"
                        className="p-2 rounded-md hover:bg-muted"
                        onClick={(e) => { e.stopPropagation(); remove(c); }}
                      >
                        <Trash2 className="w-4 h-4" />
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

function ContactPicker({ provedorId, campaignId, refreshKey, onChanged, onError }) {
  const [search, setSearch] = useState('');
  const [query, setQuery] = useState('');
  const [page, setPage] = useState(1);
  const [data, setData] = useState({ results: [], count: 0 });
  const [inCampaign, setInCampaign] = useState(() => new Set());
  const [allInfo, setAllInfo] = useState({ disponiveis: 0, marcados: 0, todosMarcados: false });
  const [loading, setLoading] = useState(false);
  const [busy, setBusy] = useState(false);
  const pageSize = 20;

  useEffect(() => {
    const t = setTimeout(() => { setQuery(search.trim()); setPage(1); }, 400);
    return () => clearTimeout(t);
  }, [search]);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    api('get', '/api/contacts/', provedorId, { params: { search: query || undefined, page, page_size: pageSize } })
      .then((res) => {
        if (cancelled) return;
        const body = res.data;
        setData(Array.isArray(body) ? { results: body, count: body.length } : { results: body.results || [], count: body.count || 0 });
      })
      .catch((err) => !cancelled && onError(errorText(err, 'Não foi possível carregar os contatos.')))
      .finally(() => !cancelled && setLoading(false));
    return () => { cancelled = true; };
  }, [provedorId, query, page, onError]);

  const pageIds = useMemo(() => data.results.map((c) => c.id).join(','), [data.results]);

  useEffect(() => {
    if (!pageIds) { setInCampaign(new Set()); return undefined; }
    let cancelled = false;
    api('get', `/api/campanhas/${campaignId}/destinatarios/`, provedorId, { params: { contatos: pageIds, busca: query || undefined } })
      .then((res) => {
        if (cancelled) return;
        setInCampaign(new Set(res.data.contato_ids || []));
        setAllInfo({
          disponiveis: res.data.disponiveis || 0,
          marcados: res.data.marcados ?? (res.data.contato_ids || []).length,
          todosMarcados: !!res.data.todos_marcados,
        });
      })
      .catch((err) => !cancelled && onError(errorText(err, 'Não foi possível verificar os contatos da campanha.')));
    return () => { cancelled = true; };
  }, [provedorId, campaignId, pageIds, query, refreshKey, onError]);

  const change = async (ids, adding) => {
    if (!ids.length) return;
    await apply({ contato_ids: ids }, adding);
  };

  const toggleAll = () => {
    if (allInfo.marcados > 0) {
      const alvo = query ? `os ${allInfo.marcados} contatos marcados da busca` : `os ${allInfo.marcados} contatos marcados`;
      if (window.confirm(`Desmarcar ${alvo}?`)) apply({ todos: true, origem: 'contato', busca: query }, false);
      return;
    }
    const qtd = allInfo.disponiveis || data.count;
    const alvo = query ? `os ${qtd} contatos da busca` : `todos os ${qtd} contatos`;
    if (window.confirm(`Marcar ${alvo}?`)) apply({ todos: true, busca: query }, true);
  };

  const someMarked = allInfo.marcados > 0 && !allInfo.todosMarcados;

  const apply = async (payload, adding) => {
    setBusy(true);
    try {
      if (adding) {
        const res = await api('post', `/api/campanhas/${campaignId}/destinatarios/`, provedorId, { data: payload });
        const { adicionados = 0, ignorados = 0, motivo_ignorados: motivo } = res.data;
        if (adicionados) toast.success(`${adicionados} contato(s) adicionado(s) à campanha.`);
        if (ignorados) toast.info(`${ignorados} contato(s) não entraram (${motivo}).`);
        if (!adicionados && !ignorados) toast.info('Esses contatos já estão na campanha.');
      } else {
        const res = await api('delete', `/api/campanhas/${campaignId}/destinatarios/`, provedorId, { data: payload });
        toast.deleted(`${res.data.removidos} contato(s) removido(s) da campanha.`);
      }
      onChanged();
    } catch (err) {
      onError(errorText(err, adding ? 'Não foi possível adicionar o contato.' : 'Não foi possível remover o contato.'));
    } finally {
      setBusy(false);
    }
  };

  const pages = Math.max(1, Math.ceil((data.count || 0) / pageSize));
  return (
    <div className="space-y-3">
      <div className="relative">
        <Search className="w-4 h-4 absolute left-3 top-2.5 text-muted-foreground" />
        <input className={`${inputCls} pl-9`} placeholder="Buscar por nome, telefone ou e-mail" value={search} onChange={(e) => setSearch(e.target.value)} />
      </div>
      <div className="border border-border rounded-md max-h-[21rem] overflow-y-auto">
        <label className="flex items-center gap-3 px-3 py-2 border-b border-border text-xs text-muted-foreground sticky top-0 bg-card">
          <input
            type="checkbox"
            ref={(el) => { if (el) el.indeterminate = someMarked; }}
            checked={allInfo.todosMarcados}
            disabled={busy || !(allInfo.disponiveis || data.count)}
            onChange={toggleAll}
          />
          Selecionar todos · {allInfo.marcados} de {allInfo.disponiveis || data.count} marcados
          {busy && <Loader2 className="w-3.5 h-3.5 animate-spin ml-auto" />}
        </label>
        {loading ? (
          <div className="flex justify-center py-6"><Loader2 className="w-5 h-5 animate-spin" /></div>
        ) : data.results.length === 0 ? (
          <div className="py-6 text-center text-sm text-muted-foreground">Nenhum contato encontrado.</div>
        ) : data.results.map((c) => (
          <label key={c.id} className={`flex items-center gap-3 px-3 py-2 border-b border-border last:border-0 hover:bg-muted/40 text-sm ${c.bloqueado_disparos ? 'opacity-60' : 'cursor-pointer'}`}>
            <input
              type="checkbox"
              checked={inCampaign.has(c.id)}
              disabled={busy || c.bloqueado_disparos}
              onChange={() => change([c.id], !inCampaign.has(c.id))}
            />
            <span className="flex-1 truncate">{c.name || 'Sem nome'}</span>
            <span className="text-muted-foreground">{c.phone || '—'}</span>
            {c.bloqueado_disparos && <span className="text-xs text-amber-500">não recebe disparos</span>}
          </label>
        ))}
      </div>
      <div className="flex items-center gap-2 text-xs text-muted-foreground">
        <button type="button" className={btnMuted} disabled={page <= 1} onClick={() => setPage((p) => p - 1)}>Anterior</button>
        Página {page} de {pages} · {data.count} contatos
        <button type="button" className={btnMuted} disabled={page >= pages} onClick={() => setPage((p) => p + 1)}>Próxima</button>
      </div>
    </div>
  );
}

function CsvImport({ provedorId, campaignId, onAdded, onError }) {
  const inputRef = useRef(null);
  const [busy, setBusy] = useState(false);

  const upload = async (file) => {
    if (!file) return;
    setBusy(true);
    const form = new FormData();
    form.append('file', file);
    try {
      const res = await api('post', `/api/campanhas/${campaignId}/destinatarios/csv/`, provedorId, { data: form });
      onAdded(res.data);
    } catch (err) {
      onError(errorText(err, 'Não foi possível importar o CSV.'));
    } finally {
      setBusy(false);
      if (inputRef.current) inputRef.current.value = '';
    }
  };

  return (
    <>
      <input ref={inputRef} type="file" accept=".csv,text/csv" className="hidden" onChange={(e) => upload(e.target.files?.[0])} />
      <button
        type="button"
        disabled={busy}
        onClick={() => inputRef.current?.click()}
        title="CSV com nome e telefone (aceita o export do Google Contatos)"
        className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs bg-primary text-primary-foreground hover:bg-primary/90 disabled:opacity-50"
      >
        {busy ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Upload className="w-3.5 h-3.5" />}
        {busy ? 'Importando...' : 'Importar lista de contatos'}
      </button>
    </>
  );
}

function CsvList({ provedorId, campaign, refreshKey, onImported, onChanged, onError }) {
  const [search, setSearch] = useState('');
  const [query, setQuery] = useState('');
  const [page, setPage] = useState(1);
  const [data, setData] = useState({ results: [], count: 0, page_size: 50 });
  const [loading, setLoading] = useState(false);
  const [busy, setBusy] = useState(false);
  const c = campaign.contagem || {};
  const total = c.total_csv || 0;
  const marcados = c.elegivel_csv || 0;

  useEffect(() => {
    const t = setTimeout(() => { setQuery(search.trim()); setPage(1); }, 400);
    return () => clearTimeout(t);
  }, [search]);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    api('get', `/api/campanhas/${campaign.id}/destinatarios/`, provedorId, { params: { origem: 'csv', busca: query || undefined, page } })
      .then((res) => !cancelled && setData(res.data))
      .catch((err) => !cancelled && onError(errorText(err, 'Não foi possível carregar a lista importada.')))
      .finally(() => !cancelled && setLoading(false));
    return () => { cancelled = true; };
  }, [provedorId, campaign.id, query, page, refreshKey, onError]);

  const run = async (method, payload, fallback) => {
    setBusy(true);
    try {
      const res = await api(method, `/api/campanhas/${campaign.id}/destinatarios/`, provedorId, { data: payload });
      onChanged();
      return res.data;
    } catch (err) {
      onError(errorText(err, fallback));
      return null;
    } finally {
      setBusy(false);
    }
  };

  const select = (payload, selecionado) => run('patch', { ...payload, selecionado }, 'Não foi possível atualizar a seleção.');

  const removeAll = async () => {
    if (!window.confirm(`Remover os ${total} contatos importados desta campanha?`)) return;
    const res = await run('delete', { todos: true, origem: 'csv' }, 'Não foi possível remover a lista.');
    if (res) toast.deleted('Lista importada removida.');
  };

  const removeOne = (r) => run('delete', { ids: [r.id] }, 'Não foi possível remover.');

  const pages = Math.max(1, Math.ceil((data.count || 0) / (data.page_size || 50)));
  const allSelected = total > 0 && marcados >= total;

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-2">
        <CsvImport provedorId={provedorId} campaignId={campaign.id} onAdded={onImported} onError={onError} />
        {total > 0 && (
          <button type="button" className="ml-auto text-xs text-red-500 hover:underline" disabled={busy} onClick={removeAll}>
            Remover lista
          </button>
        )}
      </div>
      <div className="relative">
        <Search className="w-4 h-4 absolute left-3 top-2.5 text-muted-foreground" />
        <input className={`${inputCls} pl-9`} placeholder="Buscar na lista importada" value={search} onChange={(e) => setSearch(e.target.value)} />
      </div>
      <div className="border border-border rounded-md max-h-72 overflow-y-auto">
        <label className="flex items-center gap-3 px-3 py-2 border-b border-border text-xs text-muted-foreground sticky top-0 bg-card">
          <input
            type="checkbox"
            ref={(el) => { if (el) el.indeterminate = marcados > 0 && !allSelected; }}
            checked={allSelected}
            disabled={busy || total === 0}
            onChange={() => select({ todos: true }, marcados === 0)}
          />
          Selecionar todos · {marcados} de {total} marcados
          {busy && <Loader2 className="w-3.5 h-3.5 animate-spin ml-auto" />}
        </label>
        {loading && data.results.length === 0 ? (
          <div className="flex justify-center py-6"><Loader2 className="w-5 h-5 animate-spin" /></div>
        ) : data.results.length === 0 ? (
          <div className="py-6 text-center text-sm text-muted-foreground">
            {query ? 'Nenhum contato encontrado.' : 'Nenhuma lista importada. Use "Importar lista de contatos" (CSV com nome e telefone).'}
          </div>
        ) : data.results.map((r) => (
          <div key={r.id} className="flex items-center gap-3 px-3 py-2 border-b border-border last:border-0 hover:bg-muted/40 text-sm">
            <label className="flex flex-1 min-w-0 items-center gap-3 cursor-pointer">
              <input type="checkbox" checked={r.selecionado} disabled={busy} onChange={() => select({ ids: [r.id] }, !r.selecionado)} />
              <span className="flex-1 truncate">{r.nome || 'Sem nome'}</span>
              <span className="text-muted-foreground">{r.telefone || '—'}</span>
            </label>
            <button type="button" title="Remover da lista" className="p-1 rounded hover:bg-muted" disabled={busy} onClick={() => removeOne(r)}>
              <Trash2 className="w-4 h-4" />
            </button>
          </div>
        ))}
      </div>
      <div className="flex items-center gap-2 text-xs text-muted-foreground">
        <button type="button" className={btnMuted} disabled={page <= 1} onClick={() => setPage((p) => p - 1)}>Anterior</button>
        Página {page} de {pages} · {data.count} contatos
        <button type="button" className={btnMuted} disabled={page >= pages} onClick={() => setPage((p) => p + 1)}>Próxima</button>
      </div>
    </div>
  );
}

function RecipientsTable({ provedorId, campaign, refreshKey, editable, onChanged, onError }) {
  const [status, setStatus] = useState('');
  const [page, setPage] = useState(1);
  const [data, setData] = useState({ results: [], count: 0, page_size: 50 });

  const load = useCallback(async () => {
    try {
      const res = await api('get', `/api/campanhas/${campaign.id}/destinatarios/`, provedorId, { params: { status: status || undefined, page } });
      setData(res.data);
    } catch (err) {
      onError(errorText(err, 'Não foi possível carregar os destinatários.'));
    }
  }, [provedorId, campaign.id, status, page, onError]);

  useEffect(() => { load(); }, [load, refreshKey]);

  const remove = async (payload, confirmMsg) => {
    if (confirmMsg && !window.confirm(confirmMsg)) return;
    try {
      await api('delete', `/api/campanhas/${campaign.id}/destinatarios/`, provedorId, { data: payload });
      onChanged();
    } catch (err) {
      onError(errorText(err, 'Não foi possível remover.'));
    }
  };

  const pages = Math.max(1, Math.ceil((data.count || 0) / (data.page_size || 50)));
  const c = campaign.contagem || {};

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-2 text-sm">
        {[['', `Todos (${c.total || 0})`], ['pendente', `Pendentes (${c.pendente || 0})`], ['enviado', `Enviados (${c.enviado || 0})`], ['falhou', `Falharam (${c.falhou || 0})`], ['ignorado', `Ignorados (${c.ignorado || 0})`]].map(([value, label]) => (
          <button
            key={value || 'todos'}
            type="button"
            onClick={() => { setStatus(value); setPage(1); }}
            className={`px-3 py-1.5 rounded-md text-xs ${status === value ? 'bg-primary text-primary-foreground' : 'bg-muted hover:bg-muted/80'}`}
          >
            {label}
          </button>
        ))}
        <div className="ml-auto flex items-center gap-3">
          {editable && c.total > 0 && (
            <button type="button" className="text-xs text-red-500 hover:underline" onClick={() => remove({ todos: true }, 'Remover todos os destinatários?')}>
              Remover todos
            </button>
          )}
        </div>
      </div>
      <div className="border border-border rounded-md max-h-80 overflow-y-auto">
        {data.results.length === 0 ? (
          <div className="py-6 text-center text-sm text-muted-foreground">Nenhum destinatário.</div>
        ) : (
          <table className="w-full text-sm">
            <tbody>
              {data.results.map((r) => (
                <tr key={r.id} className="border-b border-border last:border-0">
                  <td className="px-3 py-2 truncate max-w-[200px]">{r.nome || 'Sem nome'}</td>
                  <td className="px-3 py-2 text-muted-foreground">{r.telefone || (r.telegram ? 'Telegram' : '—')}</td>
                  <td className="px-3 py-2 text-xs text-muted-foreground">{r.origem === 'csv' ? 'CSV' : 'Contato'}</td>
                  <td className={`px-3 py-2 text-xs font-medium ${RECIPIENT_COLORS[r.status]}`}>
                    {RECIPIENT_LABELS[r.status]}
                    {r.erro && <div className="font-normal text-muted-foreground">{r.erro}</div>}
                  </td>
                  <td className="px-3 py-2 text-right w-10">
                    {editable && (
                      <button type="button" title="Remover" className="p-1 rounded hover:bg-muted" onClick={() => remove({ ids: [r.id] })}>
                        <Trash2 className="w-4 h-4" />
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
      {pages > 1 && (
        <div className="flex items-center gap-2 text-xs text-muted-foreground">
          <button type="button" className={btnMuted} disabled={page <= 1} onClick={() => setPage((p) => p - 1)}>Anterior</button>
          Página {page} de {pages}
          <button type="button" className={btnMuted} disabled={page >= pages} onClick={() => setPage((p) => p + 1)}>Próxima</button>
        </div>
      )}
    </div>
  );
}

const ALVO_LABELS = {
  contato: 'Contatos no sistema',
  csv: 'Lista importada (CSV)',
  todos: 'Contatos no sistema e lista importada (CSV)',
};

function usarFromPublico(publico) {
  return { contato: publico !== 'csv', csv: publico !== 'contato' };
}

function AudienceCard({ title, checked, fixed, count, onToggle, children }) {
  return (
    <div className={`h-full rounded-lg border p-4 transition-colors ${checked ? 'border-primary/60' : 'border-border'}`}>
      <label className={`text-sm font-semibold mb-3 flex items-center gap-2 ${fixed ? '' : 'cursor-pointer'}`}>
        {!fixed && <input type="checkbox" className="h-4 w-4 accent-primary" checked={checked} onChange={onToggle} />}
        {title}
        <span className="ml-auto text-xs font-normal text-muted-foreground">
          {checked ? `${count} vão receber` : 'Não vai receber'}
        </span>
      </label>
      <div className={checked ? '' : 'opacity-50'}>{children}</div>
    </div>
  );
}

function audienceCount(contagem, publico) {
  const contato = contagem?.elegivel_contato || 0;
  const csv = contagem?.elegivel_csv || 0;
  if (publico === 'contato') return contato;
  if (publico === 'csv') return csv;
  return contato + csv;
}

function fillTemplateVars(text, values) {
  return (text || '').replace(/\{\{\s*(\d+)\s*\}\}/g, (m, n) => {
    const v = values[Number(n) - 1];
    return v ? v : m;
  });
}

function TemplateGallery({ templates, onPick, allowAll = false }) {
  const [search, setSearch] = useState('');
  const term = search.trim().toLowerCase();
  const items = term ? templates.filter((t) => t.name.toLowerCase().includes(term) || (t.requisitos?.body_text || '').toLowerCase().includes(term)) : templates;
  const sorted = [...items].sort((a, b) => Number(b.requisitos?.suportado !== false) - Number(a.requisitos?.suportado !== false));

  return (
    <div className="space-y-4">
      {templates.length > 6 && (
        <div className="relative">
          <Search className="w-4 h-4 absolute left-3 top-2.5 text-muted-foreground" />
          <input className={`${inputCls} pl-9`} placeholder="Buscar template" value={search} onChange={(e) => setSearch(e.target.value)} />
        </div>
      )}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 2xl:grid-cols-4 gap-8">
        {sorted.map((t) => {
          const req = t.requisitos || {};
          const ok = allowAll || req.suportado !== false;
          return (
            <MetaTemplateCard key={`${t.name}|${t.language}`} template={t} className={ok ? '' : 'opacity-60'}>
              {ok ? (
                <div className="overlay-gallery">
                  <button type="button" className="use-btn-gallery" onClick={() => onPick(t)}>
                    {allowAll ? '✓ USAR ESTE TEXTO' : '✓ USAR ESTE MODELO'}
                  </button>
                </div>
              ) : (
                <p className="relative z-10 mt-1 px-2 text-center text-[10px] font-medium text-amber-400 leading-snug">{req.motivo}</p>
              )}
            </MetaTemplateCard>
          );
        })}
      </div>
      {sorted.length === 0 && <div className="py-6 text-center text-sm text-muted-foreground">Nenhum template encontrado.</div>}
    </div>
  );
}

const HEADER_FILE_ACCEPT = {
  IMAGE: { accept: '.jpg,.jpeg,.png,image/jpeg,image/png', label: 'imagem', hint: 'JPG ou PNG, até 5 MB' },
  VIDEO: { accept: '.mp4,.3gp,video/mp4', label: 'vídeo', hint: 'MP4, até 16 MB' },
  DOCUMENT: { accept: '.pdf,application/pdf', label: 'documento', hint: 'PDF, até 20 MB' },
};

function HeaderMediaField({ format, fileName, busy, url, onUrl, onFile, onRemove }) {
  const inputRef = useRef(null);
  const info = HEADER_FILE_ACCEPT[format] || HEADER_FILE_ACCEPT.IMAGE;
  return (
    <div className="space-y-2 text-sm">
      <span className="text-muted-foreground">{`${info.label.charAt(0).toUpperCase()}${info.label.slice(1)} do cabeçalho`}</span>
      <input
        ref={inputRef}
        type="file"
        accept={info.accept}
        className="hidden"
        onChange={(e) => { onFile(e.target.files?.[0]); e.target.value = ''; }}
      />
      {fileName ? (
        <div className="flex items-center gap-2 p-2 rounded-md border border-border bg-muted/40">
          {format === 'DOCUMENT' ? <FileText className="w-4 h-4 shrink-0" /> : format === 'VIDEO' ? <Video className="w-4 h-4 shrink-0" /> : <ImageIcon className="w-4 h-4 shrink-0" />}
          <span className="flex-1 truncate">{fileName}</span>
          {busy && <Loader2 className="w-4 h-4 animate-spin" />}
          <button type="button" className="text-xs hover:underline" onClick={() => inputRef.current?.click()}>Trocar</button>
          <button type="button" className="text-xs text-red-500 hover:underline" onClick={onRemove}>Remover</button>
        </div>
      ) : (
        <>
          <button type="button" className={`${btnMuted} w-full`} disabled={busy} onClick={() => inputRef.current?.click()}>
            {busy ? <Loader2 className="w-4 h-4 animate-spin" /> : <Upload className="w-4 h-4" />} Enviar do computador
          </button>
          <div className="text-xs text-muted-foreground text-center">{info.hint} · ou cole um link público:</div>
          <input className={inputCls} value={url} onChange={(e) => onUrl(e.target.value)} placeholder="https://..." />
        </>
      )}
    </div>
  );
}

function TemplateFields({ form, setForm, templates, loading, error, sampleVars, header }) {
  const selected = templates.find((t) => t.name === form.template_name && t.language === form.template_language)
    || templates.find((t) => t.name === form.template_name);
  const req = selected?.requisitos;
  const pick = (t) => {
    header.onReset();
    setForm((f) => ({
      ...f, template_name: t?.name || '', template_language: t?.language || '', template_variaveis: [],
      template_header_texto: '', template_header_url: '',
    }));
  };

  if (loading) {
    return <div className="flex items-center gap-2 py-6 text-sm text-muted-foreground"><Loader2 className="w-4 h-4 animate-spin" /> Carregando templates da Meta...</div>;
  }

  const bodyValues = Array.from({ length: req?.body_vars || 0 }).map((_, i) => renderPreview(form.template_variaveis[i] || '', sampleVars));
  const headerValue = renderPreview(form.template_header_texto || '', sampleVars);

  return (
    <div className="space-y-3">
      {error && <div className="p-3 rounded-md bg-red-500/10 text-red-500 text-sm">{error}</div>}
      {!error && templates.length === 0 && (
        <div className="p-3 rounded-md bg-amber-500/10 text-amber-600 text-sm">Este canal ainda não tem templates aprovados pela Meta.</div>
      )}
      {!selected && form.template_name && templates.length > 0 && (
        <div className="p-3 rounded-md bg-amber-500/10 text-amber-600 text-sm">
          O template “{form.template_name}” não está mais aprovado neste canal. Escolha outro.
        </div>
      )}
      {!req ? (
        templates.length > 0 && <TemplateGallery templates={templates} onPick={pick} />
      ) : (
        <div className="grid lg:grid-cols-[minmax(0,1fr)_380px] gap-6">
          <div className="space-y-3">
            <div className="flex items-center justify-between gap-2">
              <div className="min-w-0">
                <div className="text-xs text-muted-foreground">Template escolhido</div>
                <div className="font-mono text-sm font-bold text-primary truncate">{selected.name}</div>
              </div>
              <button type="button" className={btnMuted} onClick={() => pick(null)}>Trocar template</button>
            </div>
            {req.suportado === false && (
              <div className="p-3 rounded-md bg-amber-500/10 text-amber-600 text-sm">{req.motivo}</div>
            )}
            {req.header_text_var && (
            <label className="block text-sm">
              <span className="text-muted-foreground">Variável do cabeçalho</span>
              <input className={inputCls} value={form.template_header_texto} onChange={(e) => setForm((f) => ({ ...f, template_header_texto: e.target.value }))} placeholder="Ex.: {primeiro_nome}" />
            </label>
          )}
          {req.header_media && (
            <HeaderMediaField
              format={req.header_format}
              fileName={header.fileName}
              busy={header.busy}
              url={form.template_header_url}
              onUrl={(value) => setForm((f) => ({ ...f, template_header_url: value }))}
              onFile={header.onFile}
              onRemove={header.onRemove}
            />
          )}
          {Array.from({ length: req.body_vars }).map((_, i) => (
            <label key={i} className="block text-sm">
              <span className="text-muted-foreground">{`Valor de {{${i + 1}}}`}</span>
              <input
                className={inputCls}
                value={form.template_variaveis[i] || ''}
                placeholder={i === 0 ? 'Ex.: {primeiro_nome}' : 'Texto fixo ou {variavel}'}
                onChange={(e) => setForm((f) => {
                  const next = [...f.template_variaveis];
                  next[i] = e.target.value;
                  return { ...f, template_variaveis: next };
                })}
              />
            </label>
          ))}
          </div>
          <div>
            <div className="text-xs text-muted-foreground mb-2 text-center">Prévia</div>
            <MetaTemplatePreview
              template={selected}
              bodyText={fillTemplateVars(req.body_text, bodyValues)}
              headerText={req.header_text_var ? fillTemplateVars(req.header_text, [headerValue]) : req.header_text}
              headerImageUrl={header.previewUrl || form.template_header_url}
            />
          </div>
        </div>
      )}
    </div>
  );
}

function CampaignEditor({ provedorId, campaignId, onBack, onCreated }) {
  const [campaign, setCampaign] = useState(null);
  const [channels, setChannels] = useState([]);
  const [templates, setTemplates] = useState([]);
  const [templatesLoading, setTemplatesLoading] = useState(false);
  const [templatesError, setTemplatesError] = useState('');
  const [form, setForm] = useState({
    nome: '', canal_id: '', mensagem: '', intervalo_segundos: 5,
    template_name: '', template_language: '', template_variaveis: [], template_header_texto: '', template_header_url: '',
  });
  const [baseOpen, setBaseOpen] = useState(false);
  const [baseTemplates, setBaseTemplates] = useState([]);
  const [baseLoading, setBaseLoading] = useState(false);
  const [baseError, setBaseError] = useState('');
  const [modo, setModo] = useState('agora');
  const [usar, setUsar] = useState(() => usarFromPublico('todos'));
  const [agendadaPara, setAgendadaPara] = useState('');
  const [saving, setSaving] = useState(false);
  const [refreshKey, setRefreshKey] = useState(0);
  const [headerPending, setHeaderPending] = useState(null);
  const [headerPreview, setHeaderPreview] = useState('');
  const [headerBusy, setHeaderBusy] = useState(false);
  const headerPendingRef = useRef(null);
  const headerPreviewRef = useRef('');
  const textareaRef = useRef(null);

  const canal = useMemo(() => channels.find((c) => String(c.id) === String(form.canal_id)), [channels, form.canal_id]);
  const isTelegram = canal?.tipo === 'telegram';
  let alvo = null;
  if (isTelegram) alvo = 'contato';
  else if (usar.contato && usar.csv) alvo = 'todos';
  else if (usar.contato) alvo = 'contato';
  else if (usar.csv) alvo = 'csv';
  const editable = !campaign || EDITABLE.includes(campaign.status);
  const showError = useCallback((msg) => toast.error(msg), []);

  const applyCampaign = useCallback((c) => {
    setCampaign(c);
    setForm({
      nome: c.nome,
      canal_id: c.canal?.id || '',
      mensagem: c.mensagem || '',
      intervalo_segundos: c.intervalo_segundos,
      template_name: c.template_name || '',
      template_language: c.template_language || '',
      template_variaveis: c.template_variaveis || [],
      template_header_texto: c.template_header_texto || '',
      template_header_url: c.template_header_url || '',
    });
    if (c.agendada_para) { setModo('agendar'); setAgendadaPara(toLocalInput(c.agendada_para)); }
    setUsar(usarFromPublico(c.publico || 'todos'));
  }, []);

  const reload = useCallback(async () => {
    if (!campaignId) return;
    try {
      const res = await api('get', `/api/campanhas/${campaignId}/`, provedorId);
      setCampaign(res.data);
      setRefreshKey((k) => k + 1);
    } catch (err) {
      showError(errorText(err, 'Não foi possível carregar a campanha.'));
    }
  }, [campaignId, provedorId, showError]);

  useEffect(() => {
    api('get', '/api/campanhas/canais/', provedorId)
      .then((res) => setChannels(res.data.results || []))
      .catch((err) => showError(errorText(err, 'Não foi possível carregar os canais.')));
    if (campaignId) {
      api('get', `/api/campanhas/${campaignId}/`, provedorId)
        .then((res) => applyCampaign(res.data))
        .catch((err) => showError(errorText(err, 'Não foi possível carregar a campanha.')));
    }
  }, [provedorId, campaignId, applyCampaign, showError]);

  useEffect(() => {
    if (campaign?.status !== 'enviando') return undefined;
    const timer = setInterval(reload, POLL_MS);
    return () => clearInterval(timer);
  }, [campaign?.status, reload]);

  useEffect(() => {
    if (!canal || canal.tipo !== 'whatsapp_oficial') { setTemplates([]); return; }
    setTemplatesLoading(true);
    setTemplatesError('');
    api('get', '/api/campanhas/templates/', provedorId, { params: { canal_id: canal.id } })
      .then((res) => setTemplates(res.data.results || []))
      .catch((err) => setTemplatesError(errorText(err, 'Não foi possível listar os templates.')))
      .finally(() => setTemplatesLoading(false));
  }, [canal, provedorId]);

  const replacePreview = useCallback((blob) => {
    setHeaderPreview((prev) => {
      if (prev) URL.revokeObjectURL(prev);
      return blob ? URL.createObjectURL(blob) : '';
    });
  }, []);

  useEffect(() => () => { if (headerPreviewRef.current) URL.revokeObjectURL(headerPreviewRef.current); }, []);
  useEffect(() => { headerPreviewRef.current = headerPreview; }, [headerPreview]);

  const savedHeaderFile = campaign?.template_header_arquivo || '';
  useEffect(() => {
    if (!savedHeaderFile || !campaign?.id || headerPendingRef.current) return undefined;
    let cancelled = false;
    axios.get(`/api/campanhas/${campaign.id}/cabecalho/`, {
      params: { provedor_id: provedorId }, headers: authHeaders(), responseType: 'blob', skipErrorToast: true,
    })
      .then((res) => { if (!cancelled) replacePreview(res.data); })
      .catch(() => {});
    return () => { cancelled = true; };
  }, [savedHeaderFile, campaign?.id, provedorId, replacePreview]);

  const uploadHeader = async (campaignIdToUse, file) => {
    setHeaderBusy(true);
    const data = new FormData();
    data.append('file', file);
    try {
      const res = await api('post', `/api/campanhas/${campaignIdToUse}/cabecalho/`, provedorId, { data });
      headerPendingRef.current = null;
      setHeaderPending(null);
      setCampaign(res.data);
      setForm((f) => ({ ...f, template_header_url: '' }));
      return res.data;
    } catch (err) {
      showError(errorText(err, 'Não foi possível enviar o arquivo do cabeçalho.'));
      return null;
    } finally {
      setHeaderBusy(false);
    }
  };

  const header = {
    fileName: headerPending?.name || savedHeaderFile,
    previewUrl: headerPreview,
    busy: headerBusy,
    onFile: (file) => {
      if (!file) return;
      headerPendingRef.current = file;
      setHeaderPending(file);
      replacePreview(file);
      setForm((f) => ({ ...f, template_header_url: '' }));
      if (campaign) save({ quiet: true, headerOnly: true });
    },
    onRemove: async () => {
      headerPendingRef.current = null;
      setHeaderPending(null);
      replacePreview(null);
      if (!campaign?.template_header_arquivo) return;
      try {
        const res = await api('delete', `/api/campanhas/${campaign.id}/cabecalho/`, provedorId);
        setCampaign(res.data);
        toast.info('Arquivo do cabeçalho removido.');
      } catch (err) {
        showError(errorText(err, 'Não foi possível remover o arquivo.'));
      }
    },
    onReset: () => {
      headerPendingRef.current = null;
      setHeaderPending(null);
      replacePreview(null);
    },
  };

  const save = async (opts) => {
    const quiet = opts?.quiet === true;
    setSaving(true);
    try {
      const payload = { ...form, canal_id: form.canal_id || null };
      const res = campaign
        ? await api('patch', `/api/campanhas/${campaign.id}/`, provedorId, { data: payload })
        : await api('post', '/api/campanhas/', provedorId, { data: payload });
      applyCampaign(res.data);
      let saved = res.data;
      if (headerPendingRef.current) {
        const uploaded = await uploadHeader(res.data.id, headerPendingRef.current);
        if (uploaded) saved = uploaded;
        if (uploaded && opts?.headerOnly) toast.success('Arquivo do cabeçalho salvo.');
      }
      if (!quiet) toast.success(campaign ? 'Campanha salva.' : 'Campanha criada. Agora adicione os destinatários.');
      if (!campaign) onCreated(res.data.id);
      return saved;
    } catch (err) {
      showError(errorText(err, 'Não foi possível salvar.'));
      return null;
    } finally {
      setSaving(false);
    }
  };

  const onRecipientsAdded = (res) => {
    const parts = [`${res.adicionados} destinatário(s) adicionado(s).`];
    if (res.ignorados) parts.push(`${res.ignorados} ignorado(s) (${res.motivo_ignorados}).`);
    if (res.invalidos) parts.push(`${res.invalidos} linha(s) com telefone inválido.`);
    if (res.bloqueados) parts.push(`${res.bloqueados} contato(s) bloquearam disparos.`);
    if (res.adicionados) toast.success(parts.join(' '));
    else toast.info(parts.join(' '));
    reload();
  };

  const dispatchCampaign = async () => {
    if (!alvo) { showError('Marque qual lista vai receber a campanha.'); return; }
    const saved = await save({ quiet: true });
    if (!saved) return;
    const total = audienceCount(saved.contagem, alvo);
    let quando = null;
    if (modo === 'agendar') {
      if (!agendadaPara) { showError('Escolha o dia e o horário do disparo.'); return; }
      quando = new Date(agendadaPara).toISOString();
    }
    const msg = modo === 'agendar'
      ? `Agendar o envio para ${total} destinatário(s) em ${formatDate(quando)}?`
      : `Enviar agora para ${total} destinatário(s)?`;
    if (!window.confirm(msg)) return;
    try {
      const res = await api('post', `/api/campanhas/${saved.id}/disparar/`, provedorId, { data: { modo, agendada_para: quando, publico: alvo } });
      setCampaign(res.data);
      toast.success(modo === 'agendar' ? `Campanha agendada para ${formatDate(quando)}.` : 'Envio iniciado.');
      setRefreshKey((k) => k + 1);
    } catch (err) {
      showError(errorText(err, 'Não foi possível disparar.'));
    }
  };

  const cancel = async () => {
    if (!window.confirm('Cancelar esta campanha? Os envios pendentes não serão feitos.')) return;
    try {
      const res = await api('post', `/api/campanhas/${campaign.id}/cancelar/`, provedorId);
      setCampaign(res.data);
      toast.info('Campanha cancelada.');
      setRefreshKey((k) => k + 1);
    } catch (err) {
      showError(errorText(err, 'Não foi possível cancelar.'));
    }
  };

  const insertVar = (key) => {
    const token = `{${key}}`;
    const el = textareaRef.current;
    setForm((f) => {
      if (!el) return { ...f, mensagem: f.mensagem + token };
      const start = el.selectionStart ?? f.mensagem.length;
      const end = el.selectionEnd ?? f.mensagem.length;
      return { ...f, mensagem: f.mensagem.slice(0, start) + token + f.mensagem.slice(end) };
    });
  };

  const sampleVars = { nome: 'Maria Souza', primeiro_nome: 'Maria', telefone: '5511987654321' };
  const oficialCanal = channels.find((c) => c.tipo === 'whatsapp_oficial' && !c.problema);

  const toggleBaseTemplates = async () => {
    if (baseOpen) { setBaseOpen(false); return; }
    setBaseOpen(true);
    if (baseTemplates.length || !oficialCanal) return;
    setBaseLoading(true);
    setBaseError('');
    try {
      const res = await api('get', '/api/campanhas/templates/', provedorId, { params: { canal_id: oficialCanal.id } });
      setBaseTemplates(res.data.results || []);
    } catch (err) {
      setBaseError(errorText(err, 'Não foi possível listar os templates.'));
    } finally {
      setBaseLoading(false);
    }
  };

  const applyTemplateText = (t) => {
    const req = t.requisitos || {};
    const parts = [req.header_text, req.body_text, req.footer_text].map((s) => (s || '').trim()).filter(Boolean);
    setForm((f) => ({ ...f, mensagem: parts.join('\n\n') }));
    setBaseOpen(false);
  };

  return (
    <div className="p-6 w-full space-y-5">
      <style>{TEMPLATE_CARD_STYLES}</style>
      <div className="flex items-center gap-3">
        <button type="button" className="p-2 rounded-md hover:bg-muted" onClick={onBack} title="Voltar"><ArrowLeft className="w-5 h-5" /></button>
        <div className="flex-1">
          <h1 className="text-xl font-bold">{campaign ? campaign.nome : 'Nova campanha'}</h1>
          {campaign && (
            <div className="flex items-center gap-2 text-sm text-muted-foreground mt-1">
              <StatusBadge status={campaign.status} />
              {campaign.status === 'agendada' && <span>para {formatDate(campaign.agendada_para)}</span>}
              {campaign.iniciada_em && <span>iniciada em {formatDate(campaign.iniciada_em)}</span>}
              {campaign.concluida_em && <span>· finalizada em {formatDate(campaign.concluida_em)}</span>}
            </div>
          )}
        </div>
        {campaign && ['agendada', 'enviando'].includes(campaign.status) && (
          <button type="button" className={btnMuted} onClick={cancel}><XCircle className="w-4 h-4" /> Cancelar campanha</button>
        )}
        {campaign && <button type="button" className={btnMuted} onClick={reload} title="Atualizar"><RefreshCw className="w-4 h-4" /></button>}
      </div>

      {campaign?.erro && <div className="p-3 rounded-md bg-red-500/10 text-red-500 text-sm">{campaign.erro}</div>}

      {campaign && !editable && (
        <section className="bg-card border border-border rounded-xl p-5">
          <h2 className="font-semibold mb-3">Andamento</h2>
          <Progress contagem={campaign.contagem} />
        </section>
      )}

      <Section step={1} title="Campanha e canal" disabled={!editable}>
        <div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-4">
          <label className="block text-sm sm:col-span-2">
            <span className="text-muted-foreground">Nome da campanha</span>
            <input className={inputCls} value={form.nome} onChange={(e) => setForm((f) => ({ ...f, nome: e.target.value }))} placeholder="Ex.: Promoção de upgrade de outubro" />
          </label>
          <label className="block text-sm">
            <span className="text-muted-foreground">Canal do disparo</span>
            <select className={inputCls} value={form.canal_id} onChange={(e) => setForm((f) => ({ ...f, canal_id: e.target.value }))}>
              <option value="">Escolha o canal</option>
              {channels.map((c) => (
                <option key={c.id} value={c.id} disabled={!!c.problema}>
                  {c.tipo_label} · {c.nome}{c.problema ? ` (${c.problema})` : ''}
                </option>
              ))}
            </select>
            {channels.length === 0 && <span className="text-xs text-muted-foreground">Nenhum canal WhatsApp ou Telegram cadastrado.</span>}
          </label>
          <label className="block text-sm">
            <span className="text-muted-foreground">Intervalo entre envios (segundos)</span>
            <input type="number" min={0} max={300} className={inputCls} value={form.intervalo_segundos} onChange={(e) => setForm((f) => ({ ...f, intervalo_segundos: e.target.value }))} />
          </label>
        </div>
        {canal?.tipo === 'telegram' && (
          <p className="text-xs text-amber-600 mt-3">No Telegram só é possível enviar para contatos que já conversaram com este canal.</p>
        )}
      </Section>

      <Section step={2} title="Mensagem" disabled={!editable || !canal}>
        {canal?.tipo === 'whatsapp_oficial' ? (
          <TemplateFields form={form} setForm={setForm} templates={templates} loading={templatesLoading} error={templatesError} sampleVars={sampleVars} header={header} />
        ) : (
          <div className="space-y-3">
            {oficialCanal && (
              <div className="flex justify-end">
                <button type="button" className={btnMuted} onClick={toggleBaseTemplates}>
                  <LayoutTemplate className="w-4 h-4" /> {baseOpen ? 'Fechar templates' : 'Usar texto de um template'}
                </button>
              </div>
            )}
            {baseOpen && (
              <div className="border border-border rounded-xl p-3 space-y-2">
                {baseLoading ? (
                  <div className="flex items-center gap-2 py-4 text-sm text-muted-foreground"><Loader2 className="w-4 h-4 animate-spin" /> Carregando templates...</div>
                ) : baseError ? (
                  <div className="p-3 rounded-md bg-red-500/10 text-red-500 text-sm">{baseError}</div>
                ) : baseTemplates.length === 0 ? (
                  <div className="text-sm text-muted-foreground">Nenhum template aprovado.</div>
                ) : (
                  <TemplateGallery templates={baseTemplates} allowAll onPick={applyTemplateText} />
                )}
              </div>
            )}
            <div className="grid lg:grid-cols-2 gap-6">
              <div className="space-y-3">
                <textarea
                  ref={textareaRef}
                  rows={8}
                  className={inputCls}
                  value={form.mensagem}
                  onChange={(e) => setForm((f) => ({ ...f, mensagem: e.target.value }))}
                  placeholder="Olá {primeiro_nome}! Temos uma novidade para você..."
                />
                <div className="flex flex-wrap items-center gap-2 text-xs">
                  {BASE_VARS.map((k) => (
                    <button key={k} type="button" className="px-2 py-1 rounded bg-muted hover:bg-muted/80" onClick={() => insertVar(k)}>{`{${k}}`}</button>
                  ))}
                </div>
                {/\{\{\s*\d+\s*\}\}/.test(form.mensagem) && (
                  <div className="p-3 rounded-md bg-amber-500/10 text-amber-600 text-sm">
                    Troque {'{{1}}'}, {'{{2}}'}... por {'{primeiro_nome}'} ou um texto fixo.
                  </div>
                )}
              </div>
              <div>
                <div className="text-xs text-muted-foreground mb-1">Prévia</div>
                <div className="bg-muted rounded-md p-3 text-sm whitespace-pre-wrap min-h-[120px]">
                  {form.mensagem ? renderPreview(form.mensagem, sampleVars) : <span className="text-muted-foreground">A mensagem aparece aqui.</span>}
                </div>
              </div>
            </div>
          </div>
        )}
        <div className="mt-4 flex justify-end">
          <button type="button" className={btnPrimary} disabled={saving} onClick={save}>
            {saving && <Loader2 className="w-4 h-4 animate-spin" />} {campaign ? 'Salvar alterações' : 'Criar campanha'}
          </button>
        </div>
      </Section>

      <Section step={3} title="Destinatários" disabled={!campaign}>
        {!campaign ? (
          <p className="text-sm text-muted-foreground">Crie a campanha para adicionar os destinatários.</p>
        ) : (
          !editable ? (
            <RecipientsTable provedorId={provedorId} campaign={campaign} refreshKey={refreshKey} editable={false} onChanged={reload} onError={showError} />
          ) : (
            <div className={isTelegram ? '' : 'grid xl:grid-cols-2 gap-6 items-stretch'}>
              <AudienceCard
                title="Contatos no sistema"
                checked={isTelegram || usar.contato}
                fixed={isTelegram}
                count={campaign.contagem?.elegivel_contato || 0}
                onToggle={() => setUsar((u) => ({ ...u, contato: !u.contato }))}
              >
                <ContactPicker provedorId={provedorId} campaignId={campaign.id} refreshKey={refreshKey} onChanged={reload} onError={showError} />
              </AudienceCard>
              {!isTelegram && (
                <AudienceCard
                  title="Contatos importados (CSV)"
                  checked={usar.csv}
                  count={campaign.contagem?.elegivel_csv || 0}
                  onToggle={() => setUsar((u) => ({ ...u, csv: !u.csv }))}
                >
                  <CsvList provedorId={provedorId} campaign={campaign} refreshKey={refreshKey} onImported={onRecipientsAdded} onChanged={reload} onError={showError} />
                </AudienceCard>
              )}
            </div>
          )
        )}
      </Section>

      {editable && (
        <Section step={4} title="Envio" disabled={!campaign}>
          <div className="space-y-3 text-sm">
            <div className="text-muted-foreground">
              {alvo
                ? <>Vai para <strong className="text-foreground">{audienceCount(campaign?.contagem, alvo)}</strong> destinatário(s) · {ALVO_LABELS[alvo]}</>
                : 'Marque em Destinatários qual lista vai receber a campanha.'}
            </div>
            <label className="flex items-center gap-2">
              <input type="radio" checked={modo === 'agora'} onChange={() => setModo('agora')} /> Enviar agora
            </label>
            <label className="flex items-center gap-2">
              <input type="radio" checked={modo === 'agendar'} onChange={() => setModo('agendar')} /> Agendar dia e horário
            </label>
            {modo === 'agendar' && (
              <input type="datetime-local" className={`${inputCls} max-w-xs`} value={agendadaPara} onChange={(e) => setAgendadaPara(e.target.value)} />
            )}
            <div className="flex justify-end">
              <button type="button" className={btnPrimary} disabled={saving || !alvo || !audienceCount(campaign?.contagem, alvo)} onClick={dispatchCampaign}>
                {modo === 'agendar' ? <CalendarClock className="w-4 h-4" /> : <Send className="w-4 h-4" />}
                {modo === 'agendar' ? (campaign?.status === 'agendada' ? 'Reagendar campanha' : 'Agendar campanha') : 'Disparar agora'}
              </button>
            </div>
          </div>
        </Section>
      )}
    </div>
  );
}

export default function CampaignsPage({ provedorId }) {
  const [view, setView] = useState({ name: 'list', id: null });

  if (view.name === 'edit') {
    return (
      <CampaignEditor
        provedorId={provedorId}
        campaignId={view.id}
        onBack={() => setView({ name: 'list', id: null })}
        onCreated={(id) => setView({ name: 'edit', id })}
      />
    );
  }
  return (
    <CampaignList
      provedorId={provedorId}
      onOpen={(id) => setView({ name: 'edit', id })}
      onNew={() => setView({ name: 'edit', id: null })}
    />
  );
}
