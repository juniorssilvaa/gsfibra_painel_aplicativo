import React, { useState, useEffect, useRef } from 'react';
import axios from 'axios';
import { Zap, Pencil, Trash2, X, Search } from 'lucide-react';

const getAuthHeaders = () => {
    const token = localStorage.getItem('auth_token') || localStorage.getItem('token');
    return token ? { Authorization: `Token ${token}` } : {};
};

const API_BASE = import.meta.env.VITE_API_URL || '/api';
export default function RespostasRapidas({ provedorId: propProvedorId }) {
    const [respostas, setRespostas] = useState([]);
    const [loading, setLoading] = useState(true);
    const [search, setSearch] = useState('');
    const [showModal, setShowModal] = useState(false);
    const [editando, setEditando] = useState(null); // null = criar, objeto = editar
    const [form, setForm] = useState({ titulo: '', conteudo: '' });
    const [salvando, setSalvando] = useState(false);
    const [deletandoId, setDeletandoId] = useState(null);
    const [error, setError] = useState('');

    const provedorId = propProvedorId || (() => {
        try {
            const stored = localStorage.getItem('user_data');
            if (stored) {
                const u = JSON.parse(stored);
                return u?.provedor_id || u?.provedores_admin?.[0]?.id;
            }
        } catch { }
        return null;
    })();

    const fetchRespostas = async () => {
        setLoading(true);
        try {
            const params = {};
            if (provedorId) params.provedor = provedorId;
            const res = await axios.get(`${API_BASE}/respostas-rapidas/`, {
                headers: getAuthHeaders(),
                params,
            });
            setRespostas(res.data?.results ?? res.data ?? []);
        } catch (e) {
            setError('Erro ao carregar respostas rápidas.');
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => { fetchRespostas(); }, []);

    const filtered = respostas.filter(r =>
        r.titulo.toLowerCase().includes(search.toLowerCase()) ||
        r.conteudo.toLowerCase().includes(search.toLowerCase())
    );

    const openCreate = () => {
        setEditando(null);
        setForm({ titulo: '', conteudo: '' });
        setShowModal(true);
    };

    const openEdit = (r) => {
        setEditando(r);
        setForm({ titulo: r.titulo, conteudo: r.conteudo });
        setShowModal(true);
    };

    const handleSave = async (e) => {
        e.preventDefault();
        if (!form.titulo.trim() || !form.conteudo.trim()) return;
        setSalvando(true);
        setError('');
        try {
            const payload = { ...form };
            if (provedorId) payload.provedor = provedorId;
            if (editando) {
                await axios.patch(`${API_BASE}/respostas-rapidas/${editando.id}/`, payload, { headers: getAuthHeaders() });
            } else {
                await axios.post(`${API_BASE}/respostas-rapidas/`, payload, { headers: getAuthHeaders() });
            }
            setShowModal(false);
            fetchRespostas();
        } catch (e) {
            setError('Erro ao salvar. Verifique os dados.');
        } finally {
            setSalvando(false);
        }
    };

    const handleDelete = async (id) => {
        if (!window.confirm('Deseja excluir esta resposta rápida?')) return;
        setDeletandoId(id);
        try {
            await axios.delete(`${API_BASE}/respostas-rapidas/${id}/`, { headers: getAuthHeaders() });
            fetchRespostas();
        } catch {
            setError('Erro ao excluir.');
        } finally {
            setDeletandoId(null);
        }
    };

    return (
        <div className="p-6 max-w-4xl mx-auto">
            {/* Header */}
            <div className="flex items-center justify-between mb-8">
                <div className="flex items-center gap-3">
                    <div className="flex items-center justify-center text-muted-foreground">
                        <Zap className="w-6 h-6" strokeWidth={1.5} />
                    </div>
                    <div>
                        <h1 className="text-2xl font-black text-foreground tracking-tight">Respostas Rápidas</h1>
                        <p className="text-sm text-muted-foreground">Digite / no chat para usar</p>
                    </div>
                </div>
                <button
                    onClick={openCreate}
                    className="px-4 py-2 bg-primary hover:bg-primary/90 text-primary-foreground rounded-xl font-semibold text-sm transition-colors border border-primary/60"
                >
                    Nova Resposta
                </button>
            </div>

            {/* Search */}
            <div className="relative mb-6">
                <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" strokeWidth={1.5} />
                <input
                    type="text"
                    placeholder="Buscar por título ou conteúdo…"
                    value={search}
                    onChange={e => setSearch(e.target.value)}
                    className="w-full pl-10 pr-4 py-2.5 bg-card border border-border rounded-xl text-sm text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-primary/30"
                />
            </div>

            {error && (
                <div className="mb-4 p-3 rounded-xl bg-red-500/10 border border-red-500/20 text-red-400 text-sm">{error}</div>
            )}

            {/* List */}
            {loading ? (
                <div className="flex items-center justify-center py-20">
                    <div className="w-8 h-8 border-2 border-blue-500 border-t-transparent rounded-full animate-spin" />
                </div>
            ) : filtered.length === 0 ? (
                <div className="text-center py-20 text-muted-foreground">
                    <Zap className="w-12 h-12 mx-auto mb-3 opacity-50" strokeWidth={1.5} />
                    <p className="font-medium">Nenhuma resposta encontrada.</p>
                    <p className="text-sm mt-1">Clique em "Nova Resposta" para começar.</p>
                </div>
            ) : (
                <div className="space-y-3">
                    {filtered.map(r => (
                        <div key={r.id} className="bg-card border border-border rounded-2xl p-4 flex items-start gap-4 group hover:bg-muted transition-colors">
                            <div className="flex items-center justify-center text-muted-foreground flex-shrink-0 mt-0.5">
                                <Zap className="w-5 h-5" strokeWidth={1.5} />
                            </div>
                            <div className="flex-1 min-w-0">
                                <div className="flex items-center gap-2 mb-1">
                                    <span className="font-bold text-foreground text-sm">{r.titulo}</span>
                                    <span className="text-[10px] text-muted-foreground bg-muted px-2 py-0.5 rounded-full font-mono">/{r.titulo.toLowerCase()}</span>
                                </div>
                                <p className="text-sm text-muted-foreground line-clamp-2 leading-relaxed">{r.conteudo}</p>
                            </div>
                            <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                                <button
                                    onClick={() => openEdit(r)}
                                    className="p-2 rounded-lg hover:bg-muted text-muted-foreground hover:text-foreground transition-colors"
                                >
                                    <Pencil className="w-4 h-4" strokeWidth={1.5} />
                                </button>
                                <button
                                    onClick={() => handleDelete(r.id)}
                                    disabled={deletandoId === r.id}
                                    className="p-2 rounded-lg hover:bg-red-500/10 text-muted-foreground hover:text-red-400 transition-colors disabled:opacity-50"
                                >
                                    <Trash2 className="w-4 h-4" strokeWidth={1.5} />
                                </button>
                            </div>
                        </div>
                    ))}
                </div>
            )}

            {/* Modal */}
            {showModal && (
                <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm p-4">
                    <div className="bg-card border border-border/80 rounded-3xl p-6 w-full max-w-lg shadow-2xl">
                        <div className="flex items-center justify-between mb-5">
                            <h2 className="text-2xl font-extrabold text-foreground tracking-tight">
                                {editando ? 'Editar Resposta' : 'Nova Resposta Rápida'}
                            </h2>
                            <button onClick={() => setShowModal(false)} className="p-1.5 rounded-lg hover:bg-muted text-muted-foreground">
                                <X className="w-5 h-5" strokeWidth={1.5} />
                            </button>
                        </div>

                        {error && (
                            <div className="mb-4 p-3 rounded-xl bg-red-500/10 border border-red-500/20 text-red-400 text-sm">{error}</div>
                        )}

                        <form onSubmit={handleSave} className="space-y-4">
                            <div>
                                <label className="block text-xs font-bold text-muted-foreground uppercase tracking-widest mb-1.5">
                                    Título / Atalho
                                </label>
                                <input
                                    type="text"
                                    placeholder="Ex: Fatura, Saudação, Horário"
                                    value={form.titulo}
                                    onChange={e => setForm(f => ({ ...f, titulo: e.target.value }))}
                                    required
                                    className="w-full px-4 py-2.5 bg-background border border-border rounded-xl text-sm text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-primary/30"
                                />
                                <p className="text-xs text-muted-foreground mt-1">No chat, o atendente digitará <span className="font-mono text-primary">/{form.titulo || 'atalho'}</span></p>
                            </div>

                            <div>
                                <label className="block text-xs font-bold text-muted-foreground uppercase tracking-widest mb-1.5">
                                    Conteúdo da Mensagem
                                </label>
                                <textarea
                                    placeholder="Olá! Sua fatura vence no dia..."
                                    value={form.conteudo}
                                    onChange={e => setForm(f => ({ ...f, conteudo: e.target.value }))}
                                    required
                                    rows={5}
                                    className="w-full px-4 py-2.5 bg-background border border-border rounded-xl text-sm text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-primary/30 resize-none"
                                />
                            </div>

                            <div className="flex gap-3 pt-4 border-t border-border/70">
                                <button
                                    type="button"
                                    onClick={() => setShowModal(false)}
                                    className="flex-1 py-2.5 rounded-xl border border-border text-muted-foreground hover:bg-muted text-sm font-semibold transition-colors"
                                >
                                    Cancelar
                                </button>
                                <button
                                    type="submit"
                                    disabled={salvando}
                                    className="flex-1 py-2.5 rounded-xl bg-primary hover:bg-primary/90 text-primary-foreground text-sm font-bold transition-colors disabled:opacity-50"
                                >
                                    {salvando
                                        ? <div className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin" />
                                        : 'Salvar'
                                    }
                                </button>
                            </div>
                        </form>
                    </div>
                </div>
            )}
        </div>
    );
}
