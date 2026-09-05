import React, { useCallback, useEffect, useState } from 'react';
import axios from 'axios';
import {
  Smartphone,
  Trash2,
  Users,
  MonitorSmartphone,
  UserCog,
} from 'lucide-react';

const authHeaders = () => ({
  Authorization: `Token ${localStorage.getItem('token') || localStorage.getItem('auth_token') || ''}`,
});

export default function SuperadminAppMobile() {
  const [stats, setStats] = useState(null);
  const [contacts, setContacts] = useState([]);
  const [provedores, setProvedores] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [message, setMessage] = useState('');
  const [filterProvedor, setFilterProvedor] = useState('');
  const [search, setSearch] = useState('');

  const loadStats = useCallback(async () => {
    const res = await axios.get('/api/mobile-app/profiles/dashboard-stats/', { headers: authHeaders() });
    setStats(res.data);
  }, []);

  const loadContacts = useCallback(async () => {
    const params = {};
    if (filterProvedor) params.provedor_id = filterProvedor;
    if (search) params.q = search;
    const res = await axios.get('/api/mobile-app/app-users/', { headers: authHeaders(), params });
    setContacts(res.data.results || res.data || []);
  }, [filterProvedor, search]);

  const loadProvedores = useCallback(async () => {
    const res = await axios.get('/api/provedores/', { headers: authHeaders() });
    setProvedores(res.data.results || res.data || []);
  }, []);

  const refresh = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      await Promise.all([loadStats(), loadProvedores(), loadContacts()]);
    } catch (e) {
      setError(e?.response?.data?.error || e.message || 'Erro ao carregar');
    } finally {
      setLoading(false);
    }
  }, [loadStats, loadProvedores, loadContacts]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const deleteContact = async (id) => {
    if (!window.confirm('Excluir este cliente do app?')) return;
    await axios.delete(`/api/mobile-app/app-users/${id}/`, { headers: authHeaders() });
    setMessage('Cliente removido.');
    await loadContacts();
    await loadStats();
  };

  return (
    <div className="flex-1 p-6 bg-background overflow-y-auto">
      <div className="mb-6 flex flex-wrap items-center justify-between gap-4">
        <div>
          <h1 className="text-3xl font-bold text-foreground flex items-center gap-3">
            <Smartphone className="w-8 h-8 text-primary" />
            App Mobile
          </h1>
        </div>
      </div>

      {error && (
        <div className="mb-4 p-3 rounded-lg bg-red-500/10 text-red-400 border border-red-500/30 text-sm">{error}</div>
      )}
      {message && (
        <div className="mb-4 p-3 rounded-lg bg-green-500/10 text-green-400 border border-green-500/30 text-sm break-all">
          {message}
        </div>
      )}

      {stats && (
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 mb-6">
          {[
            {
              label: 'Clientes',
              value: stats.total_app_users,
              sub: 'No app mobile',
              icon: Users,
              tone: 'text-violet-400 bg-violet-500/15',
            },
            {
              label: 'Admins',
              value: stats.total_admins,
              sub: 'Painel do provedor',
              icon: UserCog,
              tone: 'text-amber-400 bg-amber-500/15',
            },
            {
              label: 'Dispositivos',
              value: stats.total_devices,
              sub: 'Push ativo',
              icon: MonitorSmartphone,
              tone: 'text-emerald-400 bg-emerald-500/15',
            },
          ].map((card) => (
            <div
              key={card.label}
              className="bg-card border border-border rounded-xl px-4 py-3 flex items-center gap-3"
            >
              <div className={`p-2 rounded-lg shrink-0 ${card.tone}`}>
                <card.icon className="w-4 h-4" />
              </div>
              <div className="min-w-0">
                <p className="text-[11px] uppercase tracking-wide text-muted-foreground">{card.label}</p>
                <p className="text-xl font-bold text-foreground leading-tight">{card.value ?? 0}</p>
                <p className="text-[11px] text-muted-foreground truncate">{card.sub}</p>
              </div>
            </div>
          ))}
        </div>
      )}

      {loading && !contacts.length && !stats ? (
        <div className="text-muted-foreground">Carregando…</div>
      ) : (
        <div className="space-y-4">
          <div className="bg-card border border-border rounded-xl p-4 grid grid-cols-1 md:grid-cols-3 gap-3">
            <select
              value={filterProvedor}
              onChange={(e) => setFilterProvedor(e.target.value)}
              className="hub-input w-full"
            >
              <option value="">Todos os provedores</option>
              {provedores.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.nome}
                </option>
              ))}
            </select>
            <input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Buscar nome, CPF, e-mail…"
              className="hub-input w-full"
            />
            <button
              type="button"
              onClick={loadContacts}
              className="px-4 py-2 rounded-lg bg-primary text-primary-foreground text-sm font-medium"
            >
              Filtrar
            </button>
          </div>
          <div className="bg-card border border-border rounded-xl overflow-hidden">
            <div className="px-4 py-3 border-b border-border">
              <h2 className="text-sm font-semibold text-foreground">Clientes do app</h2>
              <p className="text-xs text-muted-foreground">Usuários cadastrados no aplicativo mobile</p>
            </div>
            <table className="w-full text-left text-sm">
              <thead className="border-b border-border text-muted-foreground text-xs uppercase bg-muted/30">
                <tr>
                  <th className="px-4 py-3">Cliente</th>
                  <th className="px-4 py-3">Provedor</th>
                  <th className="px-4 py-3">Dispositivos</th>
                  <th className="px-4 py-3">Último acesso</th>
                  <th className="px-4 py-3">Ações</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {contacts.map((c) => (
                  <tr key={c.id} className="hover:bg-muted/40">
                    <td className="px-4 py-3">
                      <div className="font-medium text-foreground flex items-center gap-2">
                        <Users className="w-4 h-4 text-muted-foreground" />
                        {c.name || c.cpf}
                      </div>
                      <div className="text-xs text-muted-foreground">{c.cpf}</div>
                    </td>
                    <td className="px-4 py-3">{c.provedor_nome}</td>
                    <td className="px-4 py-3">{c.devices_count}</td>
                    <td className="px-4 py-3 text-muted-foreground text-xs">
                      {c.last_active_at
                        ? new Date(c.last_active_at).toLocaleString('pt-BR')
                        : '—'}
                      {c.is_online ? (
                        <span className="ml-2 text-green-400 font-semibold">online</span>
                      ) : null}
                    </td>
                    <td className="px-4 py-3">
                      <button
                        type="button"
                        onClick={() => deleteContact(c.id)}
                        className="p-2 rounded border border-border text-red-400 hover:bg-muted"
                      >
                        <Trash2 className="w-4 h-4" />
                      </button>
                    </td>
                  </tr>
                ))}
                {contacts.length === 0 && (
                  <tr>
                    <td colSpan={5} className="px-4 py-8 text-center text-muted-foreground">
                      Nenhum cliente encontrado.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}
