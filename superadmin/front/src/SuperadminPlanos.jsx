import React, { useEffect, useState } from 'react';
import axios from 'axios';
import { Layers, Plus, Edit, Trash2, X, Save, RefreshCw, MessageCircle, Users, Wifi } from 'lucide-react';
import { toast } from './lib/notify';

const CICLOS = [
  { value: 'MONTHLY', label: 'Mensal' },
  { value: 'QUARTERLY', label: 'Trimestral' },
  { value: 'SEMIANNUALLY', label: 'Semestral' },
  { value: 'YEARLY', label: 'Anual' },
];

const EMPTY = {
  id: null,
  nome: '',
  descricao: '',
  valor: '',
  ciclo: 'MONTHLY',
  max_canais: 0,
  max_usuarios: 0,
  ativo: true,
  ordem: 0,
};

const inputClass =
  'w-full px-3.5 py-2.5 rounded-lg bg-[#14161c] text-white border border-white/[0.08] placeholder:text-gray-600 focus:border-primary/50 focus:ring-1 focus:ring-primary/25 outline-none transition';

const authHeaders = () => ({ Authorization: `Token ${localStorage.getItem('token')}` });

const formatLimit = (value) => (Number(value) > 0 ? value : 'Ilimitado');

const cicloLabel = (ciclo) => CICLOS.find((c) => c.value === ciclo)?.label || ciclo;

const formatMoney = (value) => Number(value || 0).toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' });

export default function SuperadminPlanos() {
  const [planos, setPlanos] = useState([]);
  const [loading, setLoading] = useState(true);
  const [form, setForm] = useState(null);
  const [saving, setSaving] = useState(false);

  const fetchPlanos = async () => {
    setLoading(true);
    try {
      const res = await axios.get('/api/planos/', { headers: authHeaders() });
      setPlanos(res.data.results || res.data || []);
    } catch (err) {
      toast.apiError(err, 'Erro ao carregar os planos.');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchPlanos();
  }, []);

  const setField = (name, value) => setForm((f) => ({ ...f, [name]: value }));

  const handleSave = async (e) => {
    e.preventDefault();
    setSaving(true);
    try {
      const data = {
        ...form,
        valor: form.valor === '' ? 0 : form.valor,
        max_canais: Number(form.max_canais) || 0,
        max_usuarios: Number(form.max_usuarios) || 0,
        ordem: Number(form.ordem) || 0,
      };
      if (form.id) {
        await axios.put(`/api/planos/${form.id}/`, data, { headers: authHeaders() });
        toast.success('Plano atualizado. Os provedores deste plano recebem os novos limites.');
      } else {
        await axios.post('/api/planos/', data, { headers: authHeaders() });
        toast.success('Plano criado.');
      }
      setForm(null);
      fetchPlanos();
    } catch (err) {
      toast.apiError(err, 'Erro ao salvar o plano.');
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async (plano) => {
    if (!window.confirm(`Excluir o plano "${plano.nome}"?`)) return;
    try {
      await axios.delete(`/api/planos/${plano.id}/`, { headers: authHeaders() });
      toast.deleted('Plano excluído.');
      fetchPlanos();
    } catch (err) {
      toast.apiError(err, 'Erro ao excluir o plano.');
    }
  };

  return (
    <div className="flex-1 p-6 bg-background overflow-y-auto">
      <div className="flex flex-wrap justify-between items-center gap-4 mb-8">
        <div>
          <h1 className="text-3xl font-bold text-foreground mb-2 flex items-center gap-3">
            <Layers className="w-8 h-8 text-primary" />
            Planos
          </h1>
          <p className="text-muted-foreground">
            Mensalidade e quantos canais e usuários cada provedor pode ter. O canal do App Mobile não conta no limite.
          </p>
        </div>
        <button
          type="button"
          onClick={() => setForm({ ...EMPTY })}
          className="flex items-center gap-2 bg-primary text-white px-4 py-2 rounded-lg font-bold hover:bg-primary/90 transition shadow-lg"
        >
          <Plus size={20} /> Novo plano
        </button>
      </div>

      {loading ? (
        <div className="flex justify-center p-12">
          <RefreshCw className="animate-spin text-primary w-8 h-8" />
        </div>
      ) : planos.length === 0 ? (
        <div className="py-12 text-center bg-card/50 rounded-xl border border-dashed border-border text-muted-foreground">
          Nenhum plano cadastrado. Crie o primeiro em "Novo plano".
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 2xl:grid-cols-4 gap-6">
          {planos.map((plano) => (
            <div
              key={plano.id}
              className={`bg-card rounded-xl shadow-lg border border-border p-5 flex flex-col gap-4 ${plano.ativo ? '' : 'opacity-60'}`}
            >
              <div className="flex justify-between items-start gap-3">
                <div className="min-w-0">
                  <div className="flex items-center gap-2">
                    <h3 className="font-bold text-lg text-white truncate">{plano.nome}</h3>
                    {!plano.ativo && (
                      <span className="rounded-full border border-zinc-500/30 px-2 py-0.5 text-[10px] font-bold uppercase text-zinc-400">Inativo</span>
                    )}
                  </div>
                  <p className="text-2xl font-bold text-primary mt-1">
                    {formatMoney(plano.valor)}
                    <span className="text-xs font-normal text-muted-foreground"> / {cicloLabel(plano.ciclo).toLowerCase()}</span>
                  </p>
                </div>
                <div className="flex gap-1 shrink-0">
                  <button type="button" title="Editar" onClick={() => setForm({ ...plano })} className="p-2 text-gray-400 hover:text-white hover:bg-muted rounded-lg transition">
                    <Edit size={16} />
                  </button>
                  <button type="button" title="Excluir" onClick={() => handleDelete(plano)} className="p-2 text-gray-400 hover:text-red-500 hover:bg-red-500/10 rounded-lg transition">
                    <Trash2 size={16} />
                  </button>
                </div>
              </div>
              {plano.descricao && <p className="text-sm text-muted-foreground whitespace-pre-line">{plano.descricao}</p>}
              <div className="grid grid-cols-3 gap-3 mt-auto">
                <div className="bg-muted/50 p-3 rounded-lg border border-border">
                  <p className="text-[10px] uppercase font-bold text-muted-foreground mb-1 flex items-center gap-1"><MessageCircle size={12} /> Canais</p>
                  <p className="text-lg font-bold text-white">{formatLimit(plano.max_canais)}</p>
                </div>
                <div className="bg-muted/50 p-3 rounded-lg border border-border">
                  <p className="text-[10px] uppercase font-bold text-muted-foreground mb-1 flex items-center gap-1"><Users size={12} /> Usuários</p>
                  <p className="text-lg font-bold text-white">{formatLimit(plano.max_usuarios)}</p>
                </div>
                <div className="bg-muted/50 p-3 rounded-lg border border-border">
                  <p className="text-[10px] uppercase font-bold text-muted-foreground mb-1 flex items-center gap-1"><Wifi size={12} /> Provedores</p>
                  <p className="text-lg font-bold text-white">{plano.provedores_count || 0}</p>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}

      {form && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4">
          <form onSubmit={handleSave} className="w-full max-w-lg rounded-2xl border border-border bg-card p-6 shadow-2xl space-y-4">
            <div className="flex items-center justify-between">
              <h2 className="text-xl font-bold text-white">{form.id ? 'Editar plano' : 'Novo plano'}</h2>
              <button type="button" onClick={() => setForm(null)} className="p-2 text-gray-400 hover:text-white rounded-lg">
                <X size={18} />
              </button>
            </div>
            <div>
              <label className="mb-1.5 block text-[10px] font-bold uppercase tracking-wide text-gray-500">Nome</label>
              <input className={inputClass} value={form.nome} onChange={(e) => setField('nome', e.target.value)} placeholder="Ex.: Básico" required />
            </div>
            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="mb-1.5 block text-[10px] font-bold uppercase tracking-wide text-gray-500">Valor</label>
                <input type="number" step="0.01" min="0" className={inputClass} value={form.valor} onChange={(e) => setField('valor', e.target.value)} placeholder="0,00" />
              </div>
              <div>
                <label className="mb-1.5 block text-[10px] font-bold uppercase tracking-wide text-gray-500">Ciclo</label>
                <select className={inputClass} value={form.ciclo} onChange={(e) => setField('ciclo', e.target.value)}>
                  {CICLOS.map((c) => <option key={c.value} value={c.value}>{c.label}</option>)}
                </select>
              </div>
              <div>
                <label className="mb-1.5 block text-[10px] font-bold uppercase tracking-wide text-gray-500">Canais</label>
                <input type="number" min="0" className={inputClass} value={form.max_canais} onChange={(e) => setField('max_canais', e.target.value)} />
              </div>
              <div>
                <label className="mb-1.5 block text-[10px] font-bold uppercase tracking-wide text-gray-500">Usuários</label>
                <input type="number" min="0" className={inputClass} value={form.max_usuarios} onChange={(e) => setField('max_usuarios', e.target.value)} />
              </div>
            </div>
            <p className="text-xs text-muted-foreground">Use 0 para ilimitado.</p>
            <div>
              <label className="mb-1.5 block text-[10px] font-bold uppercase tracking-wide text-gray-500">Descrição (opcional)</label>
              <textarea rows={3} className={inputClass} value={form.descricao} onChange={(e) => setField('descricao', e.target.value)} />
            </div>
            <div className="flex items-center justify-between gap-4">
              <label className="flex items-center gap-2 text-sm text-gray-300">
                <input type="checkbox" checked={form.ativo} onChange={(e) => setField('ativo', e.target.checked)} />
                Ativo (aparece para escolher no provedor)
              </label>
              <div className="flex items-center gap-2">
                <label className="text-[10px] font-bold uppercase tracking-wide text-gray-500">Ordem</label>
                <input type="number" min="0" className={`${inputClass} w-20`} value={form.ordem} onChange={(e) => setField('ordem', e.target.value)} />
              </div>
            </div>
            <div className="flex justify-end gap-2 pt-2">
              <button type="button" onClick={() => setForm(null)} className="px-4 py-2 rounded-lg text-sm font-semibold text-gray-400 hover:bg-white/5 hover:text-white">
                Cancelar
              </button>
              <button type="submit" disabled={saving} className="inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-primary text-white text-sm font-bold hover:bg-primary/90 disabled:opacity-50">
                {saving ? <RefreshCw size={16} className="animate-spin" /> : <Save size={16} />} Salvar
              </button>
            </div>
          </form>
        </div>
      )}
    </div>
  );
}
