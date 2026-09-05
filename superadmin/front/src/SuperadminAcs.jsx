import React, { useCallback, useEffect, useMemo, useState } from 'react';
import axios from 'axios';
import {
  Router,
  KeyRound,
  Monitor,
  PauseCircle,
  PlayCircle,
  ShieldOff,
  Copy,
  Plus,
  Unlink,
  Box,
  Terminal,
  Pencil,
} from 'lucide-react';

const authHeaders = () => ({
  Authorization: `Token ${localStorage.getItem('token') || localStorage.getItem('auth_token') || ''}`,
});

const statusUi = (status) => {
  if (status === 'active') {
    return { label: 'Ativa', pill: 'bg-emerald-500/15 text-emerald-300 border-emerald-500/25' };
  }
  if (status === 'suspended') {
    return { label: 'Suspensa', pill: 'bg-amber-500/15 text-amber-300 border-amber-500/25' };
  }
  return { label: 'Expirada', pill: 'bg-red-500/15 text-red-300 border-red-500/25' };
};

const defaultExpiration = () => {
  const d = new Date();
  d.setFullYear(d.getFullYear() + 1);
  return d.toISOString().slice(0, 10);
};

const emptyRelease = {
  version: '',
  channel: 'stable',
  image_reference: '',
  changelog: '',
  is_active: true,
  is_mandatory: false,
};

export default function SuperadminAcs() {
  const [tab, setTab] = useState('licenses');
  const [stats, setStats] = useState(null);
  const [licenses, setLicenses] = useState([]);
  const [hardware, setHardware] = useState([]);
  const [profiles, setProfiles] = useState([]);
  const [releases, setReleases] = useState([]);
  const [logs, setLogs] = useState([]);
  const [provedores, setProvedores] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [message, setMessage] = useState('');
  const [filterProvedor, setFilterProvedor] = useState('');
  const [showCreate, setShowCreate] = useState(false);
  const [showRelease, setShowRelease] = useState(false);
  const [editingRelease, setEditingRelease] = useState(null);
  const [saving, setSaving] = useState(false);
  const [form, setForm] = useState({
    provedor_id: '',
    expiration_date: defaultExpiration(),
    max_onts: 100,
  });
  const [releaseForm, setReleaseForm] = useState(emptyRelease);

  const loadAll = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const headers = { headers: authHeaders() };
      const [statsRes, licRes, hwRes, provRes, profRes, relRes, logRes] = await Promise.all([
        axios.get('/api/acs/profiles/dashboard-stats/', headers),
        axios.get('/api/acs/licenses/', headers),
        axios.get('/api/acs/hardware/', headers),
        axios.get('/api/provedores/', headers),
        axios.get('/api/acs/profiles/', headers),
        axios.get('/api/acs/releases/', headers),
        axios.get('/api/acs/deployment-logs/', headers),
      ]);
      setStats(statsRes.data);
      setLicenses(licRes.data.results || licRes.data || []);
      setHardware(hwRes.data.results || hwRes.data || []);
      setProvedores(provRes.data.results || provRes.data || []);
      setProfiles(profRes.data.results || profRes.data || []);
      setReleases(relRes.data.results || relRes.data || []);
      setLogs(logRes.data.results || logRes.data || []);
    } catch (e) {
      setError(e?.response?.data?.error || e.message || 'Erro ao carregar ACS');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadAll();
  }, [loadAll]);

  const filteredLicenses = useMemo(() => {
    if (!filterProvedor) return licenses;
    return licenses.filter((l) => String(l.provedor_id) === String(filterProvedor));
  }, [licenses, filterProvedor]);

  const filteredHardware = useMemo(() => {
    if (!filterProvedor) return hardware;
    return hardware.filter((h) => String(h.provedor_id) === String(filterProvedor));
  }, [hardware, filterProvedor]);

  const filteredProfiles = useMemo(() => {
    if (!filterProvedor) return profiles;
    return profiles.filter((p) => String(p.provedor_id) === String(filterProvedor));
  }, [profiles, filterProvedor]);

  const filteredLogs = useMemo(() => {
    if (!filterProvedor) return logs;
    const names = new Set(
      profiles.filter((p) => String(p.provedor_id) === String(filterProvedor)).map((p) => p.provedor_nome),
    );
    return logs.filter((l) => names.has(l.provedor_nome));
  }, [logs, profiles, filterProvedor]);

  const copyKey = async (key) => {
    try {
      await navigator.clipboard.writeText(String(key));
      setMessage(`Licença copiada: ${key}`);
    } catch {
      setError('Não foi possível copiar a chave.');
    }
  };

  const createLicense = async (e) => {
    e.preventDefault();
    if (!form.provedor_id) {
      setError('Selecione o provedor.');
      return;
    }
    setSaving(true);
    setError('');
    try {
      const res = await axios.post('/api/acs/licenses/', form, { headers: authHeaders() });
      setMessage(`Licença gerada: ${res.data.key}`);
      setShowCreate(false);
      setForm({ provedor_id: '', expiration_date: defaultExpiration(), max_onts: 100 });
      await loadAll();
    } catch (err) {
      setError(err?.response?.data?.error || 'Falha ao gerar licença.');
    } finally {
      setSaving(false);
    }
  };

  const suspendLicense = async (lic) => {
    if (lic.status === 'expired' || lic.status === 'suspended') {
      await axios.post(`/api/acs/licenses/${lic.id}/activate/`, {}, { headers: authHeaders() });
    } else {
      await axios.post(`/api/acs/licenses/${lic.id}/suspend/`, {}, { headers: authHeaders() });
    }
    await loadAll();
  };

  const revokeLicense = async (id) => {
    if (!window.confirm('Revogar esta licença? O painel ACS deste provedor perde o acesso até reativar.')) return;
    await axios.post(`/api/acs/licenses/${id}/revoke/`, {}, { headers: authHeaders() });
    await loadAll();
  };

  const unbindHardware = async (id) => {
    if (!window.confirm('Desvincular esta máquina? O provedor poderá subir o ACS em outro servidor com a mesma licença.')) return;
    await axios.post(`/api/acs/hardware/${id}/unbind/`, {}, { headers: authHeaders() });
    setMessage('Máquina desvinculada. A licença está livre para outro servidor.');
    await loadAll();
  };

  const unbindLicenseHardware = async (lic) => {
    if (!window.confirm(`Desvincular todas as máquinas da licença de ${lic.provedor_nome}?`)) return;
    await axios.post(`/api/acs/licenses/${lic.id}/unbind-hardware/`, {}, { headers: authHeaders() });
    setMessage('Hardware desvinculado. O provedor pode registrar outra máquina.');
    await loadAll();
  };

  const saveProfileUpdate = async (profile, patch) => {
    await axios.patch(`/api/acs/profiles/${profile.id}/`, patch, { headers: authHeaders() });
    await loadAll();
  };

  const saveRelease = async (e) => {
    e.preventDefault();
    setSaving(true);
    setError('');
    try {
      if (editingRelease?.id) {
        await axios.patch(`/api/acs/releases/${editingRelease.id}/`, releaseForm, { headers: authHeaders() });
        setMessage(`Release v${releaseForm.version} atualizada.`);
      } else {
        await axios.post('/api/acs/releases/', releaseForm, { headers: authHeaders() });
        setMessage(`Release v${releaseForm.version} publicada.`);
      }
      setShowRelease(false);
      setEditingRelease(null);
      setReleaseForm(emptyRelease);
      await loadAll();
    } catch (err) {
      setError(err?.response?.data?.error || err?.response?.data?.detail || 'Falha ao salvar release.');
    } finally {
      setSaving(false);
    }
  };

  const toggleMandatory = async (release) => {
    await axios.post(`/api/acs/releases/${release.id}/toggle-mandatory/`, {}, { headers: authHeaders() });
    await loadAll();
  };

  const tabs = [
    { id: 'licenses', label: 'Licenças' },
    { id: 'hardware', label: 'Hardware' },
    { id: 'releases', label: 'Releases' },
    { id: 'logs', label: 'Logs de update' },
  ];

  return (
    <div className="flex-1 p-6 bg-background overflow-y-auto">
      <div className="mb-6 flex flex-wrap items-center justify-between gap-4">
        <div>
          <h1 className="text-3xl font-bold text-foreground flex items-center gap-3">
            <Router className="w-8 h-8 text-primary" />
            ACS
          </h1>
        </div>
        <div className="flex gap-2">
          {tab === 'releases' ? (
            <button
              type="button"
              onClick={() => {
                setEditingRelease(null);
                setReleaseForm(emptyRelease);
                setShowRelease(true);
              }}
              className="inline-flex items-center gap-2 rounded-lg bg-primary px-4 py-2 text-sm font-medium text-primary-foreground"
            >
              <Plus className="w-4 h-4" />
              Nova release
            </button>
          ) : (
            <button
              type="button"
              onClick={() => setShowCreate(true)}
              className="inline-flex items-center gap-2 rounded-lg bg-primary px-4 py-2 text-sm font-medium text-primary-foreground"
            >
              <Plus className="w-4 h-4" />
              Nova licença
            </button>
          )}
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
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3 mb-6">
          {[
            { label: 'Provedores ACS', value: stats.total_providers, sub: `${stats.active_providers ?? 0} ativos` },
            { label: 'Licenças ativas', value: stats.active_licenses, sub: 'Acesso liberado' },
            { label: 'Suspensas / expiradas', value: (stats.suspended_licenses || 0) + (stats.expired_licenses || 0), sub: `${stats.suspended_licenses ?? 0} suspensas · ${stats.expired_licenses ?? 0} expiradas` },
            { label: 'Máquinas vinculadas', value: stats.hardware_binds, sub: 'Hardware bind' },
          ].map((card) => (
            <div key={card.label} className="bg-card border border-border rounded-xl px-4 py-3">
              <p className="text-[11px] uppercase tracking-wide text-muted-foreground">{card.label}</p>
              <p className="text-xl font-bold text-foreground leading-tight">{card.value ?? 0}</p>
              <p className="text-[11px] text-muted-foreground truncate">{card.sub}</p>
            </div>
          ))}
        </div>
      )}

      <div className="bg-card border border-border rounded-xl p-4 mb-4 flex flex-wrap gap-3 items-center">
        <select
          value={filterProvedor}
          onChange={(e) => setFilterProvedor(e.target.value)}
          className="hub-input w-full md:w-64"
        >
          <option value="">Todos os provedores</option>
          {provedores.map((p) => (
            <option key={p.id} value={p.id}>
              {p.nome}
            </option>
          ))}
        </select>
        <div className="flex flex-wrap gap-2">
          {tabs.map((t) => (
            <button
              key={t.id}
              type="button"
              onClick={() => setTab(t.id)}
              className={`px-4 py-2 rounded-lg text-sm font-medium ${tab === t.id ? 'bg-primary text-primary-foreground' : 'bg-muted text-foreground'}`}
            >
              {t.label}
            </button>
          ))}
        </div>
      </div>

      {loading ? (
        <div className="text-muted-foreground">Carregando…</div>
      ) : tab === 'licenses' ? (
        <div className="space-y-4">
          <div className="bg-card border border-border rounded-xl overflow-x-auto">
            <table className="w-full text-left text-sm min-w-[960px]">
              <thead className="border-b border-border text-muted-foreground text-xs uppercase bg-muted/30">
                <tr>
                  <th className="px-4 py-3">Provedor</th>
                  <th className="px-4 py-3">Chave</th>
                  <th className="px-4 py-3">Versão / canal</th>
                  <th className="px-4 py-3">Status</th>
                  <th className="px-4 py-3">Validade</th>
                  <th className="px-4 py-3">ONTs</th>
                  <th className="px-4 py-3">Ações</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {filteredLicenses.map((lic) => {
                  const ui = statusUi(lic.status);
                  return (
                    <tr key={lic.id} className="hover:bg-muted/40">
                      <td className="px-4 py-3">
                        <div className="font-medium text-foreground">{lic.provedor_nome}</div>
                        <div className="text-[11px] text-muted-foreground">
                          {lic.auto_update ? 'Auto-update ligado' : 'Auto-update desligado'}
                          {lic.last_check ? ` · visto ${new Date(lic.last_check).toLocaleString('pt-BR')}` : ' · ainda não checou'}
                        </div>
                      </td>
                      <td className="px-4 py-3">
                        <code className="text-xs text-primary break-all">{lic.key}</code>
                      </td>
                      <td className="px-4 py-3">
                        <span className="inline-flex items-center gap-1 rounded border border-border px-2 py-0.5 text-xs">
                          v{lic.current_version || '—'}
                        </span>
                        <span className="ml-2 text-[11px] uppercase text-muted-foreground">{lic.update_channel}</span>
                      </td>
                      <td className="px-4 py-3">
                        <span className={`inline-flex px-2 py-0.5 rounded-full text-[11px] font-semibold border ${ui.pill}`}>
                          {ui.label}
                        </span>
                      </td>
                      <td className="px-4 py-3 text-muted-foreground">
                        {lic.expiration_date
                          ? new Date(`${lic.expiration_date}T00:00:00`).toLocaleDateString('pt-BR')
                          : '—'}
                      </td>
                      <td className="px-4 py-3">{lic.max_onts}</td>
                      <td className="px-4 py-3">
                        <div className="flex items-center gap-1">
                          <button type="button" title="Copiar chave" onClick={() => copyKey(lic.key)} className="p-2 rounded border border-border hover:bg-muted">
                            <Copy className="w-4 h-4" />
                          </button>
                          <button
                            type="button"
                            title={lic.status === 'active' ? 'Suspender' : 'Reativar'}
                            onClick={() => suspendLicense(lic)}
                            className="p-2 rounded border border-border hover:bg-muted"
                          >
                            {lic.status === 'active' ? <PauseCircle className="w-4 h-4 text-amber-400" /> : <PlayCircle className="w-4 h-4 text-emerald-400" />}
                          </button>
                          <button
                            type="button"
                            title="Desvincular máquina"
                            onClick={() => unbindLicenseHardware(lic)}
                            className="p-2 rounded border border-border hover:bg-muted text-amber-400"
                          >
                            <Unlink className="w-4 h-4" />
                          </button>
                          <button type="button" title="Revogar" onClick={() => revokeLicense(lic.id)} className="p-2 rounded border border-border hover:bg-muted text-red-400">
                            <ShieldOff className="w-4 h-4" />
                          </button>
                        </div>
                      </td>
                    </tr>
                  );
                })}
                {filteredLicenses.length === 0 && (
                  <tr>
                    <td colSpan={7} className="px-4 py-8 text-center text-muted-foreground">
                      Nenhuma licença ACS. Gere uma chave para o provedor.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>

          <div className="bg-card border border-border rounded-xl overflow-x-auto">
            <div className="px-4 py-3 border-b border-border">
              <h2 className="text-sm font-semibold">Governança de update por provedor</h2>
              <p className="text-xs text-muted-foreground">Canal, auto-update e versão travada — o painel ACS consulta isso a cada poucos minutos.</p>
            </div>
            <table className="w-full text-left text-sm min-w-[720px]">
              <thead className="border-b border-border text-muted-foreground text-xs uppercase bg-muted/30">
                <tr>
                  <th className="px-4 py-3">Provedor</th>
                  <th className="px-4 py-3">Versão instalada</th>
                  <th className="px-4 py-3">Canal</th>
                  <th className="px-4 py-3">Auto-update</th>
                  <th className="px-4 py-3">Versão travada</th>
                  <th className="px-4 py-3">Última checagem</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {filteredProfiles.map((p) => (
                  <tr key={p.id} className="hover:bg-muted/40">
                    <td className="px-4 py-3 font-medium">{p.provedor_nome}</td>
                    <td className="px-4 py-3">v{p.current_version || '—'}</td>
                    <td className="px-4 py-3">
                      <select
                        value={p.update_channel}
                        onChange={(e) => saveProfileUpdate(p, { update_channel: e.target.value })}
                        className="hub-input py-1 text-xs"
                      >
                        <option value="stable">stable</option>
                        <option value="beta">beta</option>
                        <option value="lts">lts</option>
                      </select>
                    </td>
                    <td className="px-4 py-3">
                      <button
                        type="button"
                        onClick={() => saveProfileUpdate(p, { auto_update: !p.auto_update })}
                        className={`px-2 py-1 rounded text-[11px] font-semibold border ${p.auto_update ? 'bg-emerald-500/15 text-emerald-300 border-emerald-500/25' : 'bg-muted text-muted-foreground border-border'}`}
                      >
                        {p.auto_update ? 'Ligado' : 'Desligado'}
                      </button>
                    </td>
                    <td className="px-4 py-3">
                      <input
                        defaultValue={p.fixed_version || ''}
                        placeholder="ex.: 1.2.6"
                        className="hub-input py-1 text-xs w-28"
                        onBlur={(e) => {
                          const next = e.target.value.trim();
                          if (next !== (p.fixed_version || '')) {
                            saveProfileUpdate(p, { fixed_version: next });
                          }
                        }}
                      />
                    </td>
                    <td className="px-4 py-3 text-xs text-muted-foreground">
                      {p.last_check ? new Date(p.last_check).toLocaleString('pt-BR') : 'Ainda não checou'}
                    </td>
                  </tr>
                ))}
                {filteredProfiles.length === 0 && (
                  <tr>
                    <td colSpan={6} className="px-4 py-6 text-center text-muted-foreground">Nenhum perfil ACS.</td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </div>
      ) : tab === 'hardware' ? (
        <div className="bg-card border border-border rounded-xl overflow-x-auto">
          <table className="w-full text-left text-sm min-w-[980px]">
            <thead className="border-b border-border text-muted-foreground text-xs uppercase bg-muted/30">
              <tr>
                <th className="px-4 py-3">Provedor</th>
                <th className="px-4 py-3">Licença</th>
                <th className="px-4 py-3">Nome da máquina</th>
                <th className="px-4 py-3">HWID</th>
                <th className="px-4 py-3">Último IP</th>
                <th className="px-4 py-3">Visto em</th>
                <th className="px-4 py-3">Status</th>
                <th className="px-4 py-3">Ações</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {filteredHardware.map((h) => (
                <tr key={h.id} className="hover:bg-muted/40">
                  <td className="px-4 py-3">
                    <div className="font-medium">{h.provedor_nome}</div>
                    <div className="text-[11px] text-muted-foreground">v{h.current_version || '—'}</div>
                  </td>
                  <td className="px-4 py-3">
                    <code className="text-[11px] text-muted-foreground">{String(h.license_key || '').slice(0, 8)}…</code>
                  </td>
                  <td className="px-4 py-3">
                    <div className="flex items-center gap-2">
                      <Monitor className="w-4 h-4 text-muted-foreground" />
                      {h.machine_name || '—'}
                    </div>
                  </td>
                  <td className="px-4 py-3">
                    <code className="text-[11px] break-all">{h.hwid_hash}</code>
                  </td>
                  <td className="px-4 py-3 text-muted-foreground">{h.last_ip || '—'}</td>
                  <td className="px-4 py-3 text-xs text-muted-foreground">
                    {h.last_seen ? new Date(h.last_seen).toLocaleString('pt-BR') : '—'}
                  </td>
                  <td className="px-4 py-3">
                    <span className={`inline-flex px-2 py-0.5 rounded-full text-[11px] font-semibold border ${h.status ? 'bg-emerald-500/15 text-emerald-300 border-emerald-500/25' : 'bg-red-500/15 text-red-300 border-red-500/25'}`}>
                      {h.status ? 'Ativo' : 'Inativo'}
                    </span>
                  </td>
                  <td className="px-4 py-3">
                    <button
                      type="button"
                      onClick={() => unbindHardware(h.id)}
                      className="inline-flex items-center gap-1 p-2 rounded border border-border hover:bg-muted text-amber-400"
                      title="Liberar a licença para outro servidor"
                    >
                      <Unlink className="w-4 h-4" />
                      Desvincular
                    </button>
                  </td>
                </tr>
              ))}
              {filteredHardware.length === 0 && (
                <tr>
                  <td colSpan={8} className="px-4 py-8 text-center text-muted-foreground">
                    Nenhuma máquina vinculada. O bind aparece quando o painel ACS valida a licença.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      ) : tab === 'releases' ? (
        <div className="bg-card border border-border rounded-xl overflow-x-auto">
          <table className="w-full text-left text-sm min-w-[860px]">
            <thead className="border-b border-border text-muted-foreground text-xs uppercase bg-muted/30">
              <tr>
                <th className="px-4 py-3">Versão</th>
                <th className="px-4 py-3">Canal</th>
                <th className="px-4 py-3">Imagem / tag</th>
                <th className="px-4 py-3">Status</th>
                <th className="px-4 py-3">Publicada</th>
                <th className="px-4 py-3">Ações</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {releases.map((r) => (
                <tr key={r.id} className="hover:bg-muted/40">
                  <td className="px-4 py-3">
                    <div className="flex items-center gap-2 font-semibold">
                      <Box className="w-4 h-4 text-primary" />
                      v{r.version}
                    </div>
                  </td>
                  <td className="px-4 py-3 uppercase text-xs">{r.channel}</td>
                  <td className="px-4 py-3"><code className="text-xs text-muted-foreground">{r.image_reference || '—'}</code></td>
                  <td className="px-4 py-3">
                    <div className="flex flex-wrap gap-1">
                      <span className={`px-2 py-0.5 rounded-full text-[11px] border ${r.is_active ? 'bg-emerald-500/15 text-emerald-300 border-emerald-500/25' : 'bg-muted text-muted-foreground border-border'}`}>
                        {r.is_active ? 'Ativa' : 'Inativa'}
                      </span>
                      {r.is_mandatory ? (
                        <span className="px-2 py-0.5 rounded-full text-[11px] border bg-red-500/15 text-red-300 border-red-500/25">Obrigatória</span>
                      ) : null}
                    </div>
                  </td>
                  <td className="px-4 py-3 text-xs text-muted-foreground">
                    {r.created_at ? new Date(r.created_at).toLocaleString('pt-BR') : '—'}
                  </td>
                  <td className="px-4 py-3">
                    <div className="flex gap-1">
                      <button
                        type="button"
                        title="Editar"
                        className="p-2 rounded border border-border hover:bg-muted"
                        onClick={() => {
                          setEditingRelease(r);
                          setReleaseForm({
                            version: r.version || '',
                            channel: r.channel || 'stable',
                            image_reference: r.image_reference || '',
                            changelog: r.changelog || '',
                            is_active: !!r.is_active,
                            is_mandatory: !!r.is_mandatory,
                          });
                          setShowRelease(true);
                        }}
                      >
                        <Pencil className="w-4 h-4" />
                      </button>
                      <button
                        type="button"
                        onClick={() => toggleMandatory(r)}
                        className={`px-2 py-1 rounded text-[11px] font-semibold border ${r.is_mandatory ? 'bg-red-500/15 text-red-300 border-red-500/25' : 'border-border'}`}
                      >
                        {r.is_mandatory ? 'Obrigatória' : 'Marcar obrigatória'}
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
              {releases.length === 0 && (
                <tr>
                  <td colSpan={6} className="px-4 py-8 text-center text-muted-foreground">
                    Nenhuma release. Publique uma versão para o painel ACS consultar.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      ) : (
        <div className="bg-card border border-border rounded-xl overflow-x-auto">
          <table className="w-full text-left text-sm min-w-[800px]">
            <thead className="border-b border-border text-muted-foreground text-xs uppercase bg-muted/30">
              <tr>
                <th className="px-4 py-3">Provedor</th>
                <th className="px-4 py-3">De</th>
                <th className="px-4 py-3">Para</th>
                <th className="px-4 py-3">Status</th>
                <th className="px-4 py-3">Quando</th>
                <th className="px-4 py-3">Resultado</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {filteredLogs.map((log) => (
                <tr key={log.id} className="hover:bg-muted/40">
                  <td className="px-4 py-3 font-medium">{log.provedor_nome}</td>
                  <td className="px-4 py-3 text-xs">v{log.from_version || '—'}</td>
                  <td className="px-4 py-3 text-xs">v{log.to_version || '—'}</td>
                  <td className="px-4 py-3">
                    <span className={`px-2 py-0.5 rounded-full text-[11px] border ${log.status === 'success' ? 'bg-emerald-500/15 text-emerald-300 border-emerald-500/25' : 'bg-red-500/15 text-red-300 border-red-500/25'}`}>
                      {log.status || '—'}
                    </span>
                    {log.error_message ? <div className="text-[11px] text-red-400 mt-1 max-w-xs">{log.error_message}</div> : null}
                  </td>
                  <td className="px-4 py-3 text-xs text-muted-foreground">
                    {log.finished_at || log.started_at
                      ? new Date(log.finished_at || log.started_at).toLocaleString('pt-BR')
                      : '—'}
                  </td>
                  <td className="px-4 py-3 text-xs">
                    {log.had_rollback ? 'Rollback' : log.status === 'success' ? 'Limpo' : '—'}
                  </td>
                </tr>
              ))}
              {filteredLogs.length === 0 && (
                <tr>
                  <td colSpan={6} className="px-4 py-8 text-center text-muted-foreground">
                    <Terminal className="w-8 h-8 mx-auto mb-2 opacity-50" />
                    Nenhum log de implantação. Aparece quando o ACS reporta um update.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      )}

      {showCreate && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4">
          <form onSubmit={createLicense} className="w-full max-w-md rounded-xl border border-border bg-card p-5 space-y-4">
            <h2 className="text-lg font-semibold text-foreground flex items-center gap-2">
              <KeyRound className="w-5 h-5 text-primary" />
              Gerar licença ACS
            </h2>
            <div>
              <label className="block text-xs font-semibold text-muted-foreground uppercase mb-1">Provedor</label>
              <select
                value={form.provedor_id}
                onChange={(e) => setForm((p) => ({ ...p, provedor_id: e.target.value }))}
                className="hub-input w-full"
                required
              >
                <option value="">Selecione…</option>
                {provedores.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.nome}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label className="block text-xs font-semibold text-muted-foreground uppercase mb-1">Validade</label>
              <input
                type="date"
                value={form.expiration_date}
                onChange={(e) => setForm((p) => ({ ...p, expiration_date: e.target.value }))}
                className="hub-input w-full"
                required
              />
            </div>
            <div>
              <label className="block text-xs font-semibold text-muted-foreground uppercase mb-1">Limite de ONTs</label>
              <input
                type="number"
                min="1"
                value={form.max_onts}
                onChange={(e) => setForm((p) => ({ ...p, max_onts: Number(e.target.value) }))}
                className="hub-input w-full"
              />
            </div>
            <div className="flex justify-end gap-2 pt-2">
              <button type="button" onClick={() => setShowCreate(false)} className="px-4 py-2 rounded-lg border border-border">
                Cancelar
              </button>
              <button type="submit" disabled={saving} className="px-4 py-2 rounded-lg bg-primary text-primary-foreground">
                {saving ? 'Gerando…' : 'Gerar'}
              </button>
            </div>
          </form>
        </div>
      )}

      {showRelease && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4">
          <form onSubmit={saveRelease} className="w-full max-w-lg rounded-xl border border-border bg-card p-5 space-y-4">
            <h2 className="text-lg font-semibold text-foreground flex items-center gap-2">
              <Box className="w-5 h-5 text-primary" />
              {editingRelease ? 'Editar release' : 'Nova release'}
            </h2>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="block text-xs font-semibold text-muted-foreground uppercase mb-1">Versão</label>
                <input
                  value={releaseForm.version}
                  onChange={(e) => setReleaseForm((p) => ({ ...p, version: e.target.value }))}
                  className="hub-input w-full"
                  placeholder="1.2.6"
                  required
                />
              </div>
              <div>
                <label className="block text-xs font-semibold text-muted-foreground uppercase mb-1">Canal</label>
                <select
                  value={releaseForm.channel}
                  onChange={(e) => setReleaseForm((p) => ({ ...p, channel: e.target.value }))}
                  className="hub-input w-full"
                >
                  <option value="stable">stable</option>
                  <option value="beta">beta</option>
                  <option value="lts">lts</option>
                </select>
              </div>
            </div>
            <div>
              <label className="block text-xs font-semibold text-muted-foreground uppercase mb-1">Imagem / tag</label>
              <input
                value={releaseForm.image_reference}
                onChange={(e) => setReleaseForm((p) => ({ ...p, image_reference: e.target.value }))}
                className="hub-input w-full"
                placeholder="v1.2.6"
              />
            </div>
            <div>
              <label className="block text-xs font-semibold text-muted-foreground uppercase mb-1">Changelog</label>
              <textarea
                value={releaseForm.changelog}
                onChange={(e) => setReleaseForm((p) => ({ ...p, changelog: e.target.value }))}
                className="hub-input w-full min-h-[90px]"
              />
            </div>
            <label className="flex items-center gap-2 text-sm">
              <input
                type="checkbox"
                checked={!!releaseForm.is_active}
                onChange={(e) => setReleaseForm((p) => ({ ...p, is_active: e.target.checked }))}
              />
              Ativa (provedores do canal recebem a notificação)
            </label>
            <label className="flex items-center gap-2 text-sm">
              <input
                type="checkbox"
                checked={!!releaseForm.is_mandatory}
                onChange={(e) => setReleaseForm((p) => ({ ...p, is_mandatory: e.target.checked }))}
              />
              Update obrigatório
            </label>
            <p className="text-xs text-muted-foreground">
              O painel ACS consulta o Superadmin e aplica a política do canal. Obrigatória força a atualização.
            </p>
            <div className="flex justify-end gap-2 pt-2">
              <button
                type="button"
                onClick={() => {
                  setShowRelease(false);
                  setEditingRelease(null);
                }}
                className="px-4 py-2 rounded-lg border border-border"
              >
                Cancelar
              </button>
              <button type="submit" disabled={saving} className="px-4 py-2 rounded-lg bg-primary text-primary-foreground">
                {saving ? 'Salvando…' : 'Salvar'}
              </button>
            </div>
          </form>
        </div>
      )}
    </div>
  );
}
