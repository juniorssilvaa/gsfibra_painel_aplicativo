import React, { useState, useEffect, useCallback } from 'react';
import { Plus, Pencil, Trash2, Check, X, Wifi, ArrowDownUp, DollarSign, GripVertical, ToggleLeft, ToggleRight } from 'lucide-react';

export default function PlanosPage({ provedorId }) {
    const [planos, setPlanos] = useState([]);
    const [loading, setLoading] = useState(true);
    const [showModal, setShowModal] = useState(false);
    const [editingPlano, setEditingPlano] = useState(null);
    const [formData, setFormData] = useState({
        nome: '', velocidade_download: '',
        preco: '', ativo: true, ordem: 0
    });

    const token = localStorage.getItem('auth_token');
    const headers = { 'Authorization': `Token ${token}`, 'Content-Type': 'application/json' };

    const fetchPlanos = useCallback(async () => {
        setLoading(true);
        try {
            const res = await fetch(`/api/planos/?provedor=${provedorId}`, { headers });
            if (res.ok) {
                const data = await res.json();
                setPlanos(data.results || data);
            }
        } catch (err) {
            console.error('Erro ao buscar planos:', err);
        } finally {
            setLoading(false);
        }
    }, [provedorId]);

    useEffect(() => { fetchPlanos(); }, [fetchPlanos]);

    const openCreate = () => {
        setEditingPlano(null);
        setFormData({ nome: '', velocidade_download: '', preco: '', ativo: true, ordem: 0 });
        setShowModal(true);
    };

    const openEdit = (plano) => {
        setEditingPlano(plano);
        setFormData({
            nome: plano.nome,
            velocidade_download: plano.velocidade_download || '',
            preco: plano.preco, ativo: plano.ativo, ordem: plano.ordem || 0
        });
        setShowModal(true);
    };

    const handleSave = async () => {
        const body = { ...formData, provedor: parseInt(provedorId) };
        const url = editingPlano ? `/api/planos/${editingPlano.id}/` : '/api/planos/';
        const method = editingPlano ? 'PUT' : 'POST';
        try {
            const res = await fetch(url, { method, headers, body: JSON.stringify(body) });
            if (res.ok) {
                setShowModal(false);
                fetchPlanos();
            }
        } catch (err) {
            console.error('Erro ao salvar plano:', err);
        }
    };

    const handleDelete = async (id) => {
        if (!confirm('Tem certeza que deseja excluir este plano?')) return;
        try {
            await fetch(`/api/planos/${id}/`, { method: 'DELETE', headers });
            fetchPlanos();
        } catch (err) {
            console.error('Erro ao excluir plano:', err);
        }
    };

    const toggleAtivo = async (plano) => {
        try {
            await fetch(`/api/planos/${plano.id}/`, {
                method: 'PATCH', headers,
                body: JSON.stringify({ ativo: !plano.ativo })
            });
            fetchPlanos();
        } catch (err) {
            console.error('Erro ao atualizar status:', err);
        }
    };

    return (
        <div className="p-6 max-w-6xl mx-auto">
            {/* Header */}
            <div className="flex items-center justify-between mb-6">
                <div>
                    <h1 className="text-2xl font-bold text-foreground flex items-center gap-2">
                        <Wifi className="w-7 h-7 text-primary" />
                        Planos de Internet
                    </h1>
                    <p className="text-muted-foreground text-sm mt-1">
                        Gerencie os planos de internet oferecidos aos seus clientes
                    </p>
                </div>
                <button
                    onClick={openCreate}
                    className="flex items-center gap-2 px-4 py-2.5 bg-primary text-primary-foreground rounded-lg hover:bg-primary/90 transition-colors font-medium shadow-sm"
                >
                    <Plus className="w-4 h-4" />
                    Novo Plano
                </button>
            </div>

            {/* Grid de planos */}
            {loading ? (
                <div className="flex items-center justify-center py-20">
                    <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary"></div>
                </div>
            ) : planos.length === 0 ? (
                <div className="text-center py-20 bg-card rounded-xl border border-border">
                    <Wifi className="w-12 h-12 text-muted-foreground mx-auto mb-3 opacity-40" />
                    <p className="text-muted-foreground text-lg font-medium">Nenhum plano cadastrado</p>
                    <p className="text-muted-foreground text-sm mt-1">Clique em "Novo Plano" para começar</p>
                </div>
            ) : (
                <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
                    {planos.map(plano => (
                        <div
                            key={plano.id}
                            className={`relative bg-card rounded-xl border transition-all duration-200 hover:shadow-lg group ${plano.ativo ? 'border-border hover:border-primary/40' : 'border-border/50 opacity-60'
                                }`}
                        >
                            {/* Status badge */}
                            <div className="absolute top-3 right-3">
                                <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium ${plano.ativo
                                    ? 'bg-emerald-500/10 text-emerald-500 border border-emerald-500/20'
                                    : 'bg-red-500/10 text-red-400 border border-red-500/20'
                                    }`}>
                                    {plano.ativo ? 'Ativo' : 'Inativo'}
                                </span>
                            </div>

                            <div className="p-5">
                                {/* Nome do plano */}
                                <h3 className="text-lg font-semibold text-foreground pr-16 mb-1">{plano.nome}</h3>
                                {/* Descrição */}
                                {plano.velocidade_download && (
                                    <p className="text-sm text-muted-foreground mb-4">{plano.velocidade_download}</p>
                                )}

                                {/* Preço */}
                                <div className="flex items-center gap-2 mb-4">
                                    <DollarSign className="w-5 h-5 text-amber-400" />
                                    <span className="text-2xl font-bold text-foreground">
                                        R$ {parseFloat(plano.preco).toFixed(2)}
                                    </span>
                                    <span className="text-xs text-muted-foreground">/mês</span>
                                </div>

                                {/* Ações */}
                                <div className="flex items-center gap-2 pt-3 border-t border-border">
                                    <button
                                        onClick={() => toggleAtivo(plano)}
                                        className="flex items-center gap-1.5 px-3 py-1.5 text-xs rounded-md hover:bg-muted transition-colors text-muted-foreground"
                                        title={plano.ativo ? 'Desativar' : 'Ativar'}
                                    >
                                        {plano.ativo ? <ToggleRight className="w-4 h-4 text-emerald-500" /> : <ToggleLeft className="w-4 h-4" />}
                                        {plano.ativo ? 'Desativar' : 'Ativar'}
                                    </button>
                                    <div className="flex-1" />
                                    <button
                                        onClick={() => openEdit(plano)}
                                        className="p-2 rounded-md hover:bg-muted transition-colors text-muted-foreground hover:text-foreground"
                                        title="Editar"
                                    >
                                        <Pencil className="w-4 h-4" />
                                    </button>
                                    <button
                                        onClick={() => handleDelete(plano.id)}
                                        className="p-2 rounded-md hover:bg-destructive/10 transition-colors text-muted-foreground hover:text-destructive"
                                        title="Excluir"
                                    >
                                        <Trash2 className="w-4 h-4" />
                                    </button>
                                </div>
                            </div>
                        </div>
                    ))}
                </div>
            )}

            {/* Modal de criação/edição */}
            {showModal && (
                <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm">
                    <div className="bg-card rounded-xl border border-border shadow-2xl w-full max-w-lg mx-4 overflow-hidden">
                        <div className="flex items-center justify-between px-6 py-4 border-b border-border">
                            <h2 className="text-lg font-semibold text-foreground">
                                {editingPlano ? 'Editar Plano' : 'Novo Plano'}
                            </h2>
                            <button onClick={() => setShowModal(false)} className="p-1 hover:bg-muted rounded-md transition-colors">
                                <X className="w-5 h-5 text-muted-foreground" />
                            </button>
                        </div>
                        <div className="p-6 space-y-4">
                            <div>
                                <label className="block text-sm font-medium text-foreground mb-1">Nome do Plano *</label>
                                <input
                                    type="text" value={formData.nome}
                                    onChange={e => setFormData({ ...formData, nome: e.target.value })}
                                    className="w-full px-3 py-2 bg-background border border-border rounded-lg text-foreground focus:outline-none focus:ring-2 focus:ring-primary/50"
                                    placeholder="Ex: Fibra 300 Mega"
                                />
                            </div>
                            <div>
                                <label className="block text-sm font-medium text-foreground mb-1">Descrição do Plano</label>
                                <textarea
                                    value={formData.velocidade_download}
                                    onChange={e => setFormData({ ...formData, velocidade_download: e.target.value })}
                                    className="w-full px-3 py-2 bg-background border border-border rounded-lg text-foreground focus:outline-none focus:ring-2 focus:ring-primary/50"
                                    rows={3}
                                    placeholder="Ex: Plano ideal para navegação e redes sociais..."
                                />
                            </div>
                            <div className="grid grid-cols-2 gap-4">
                                <div>
                                    <label className="block text-sm font-medium text-foreground mb-1">Preço (R$) *</label>
                                    <input
                                        type="number" step="0.01" value={formData.preco}
                                        onChange={e => setFormData({ ...formData, preco: e.target.value })}
                                        className="w-full px-3 py-2 bg-background border border-border rounded-lg text-foreground focus:outline-none focus:ring-2 focus:ring-primary/50"
                                        placeholder="99.90"
                                    />
                                </div>
                                <div>
                                    <label className="block text-sm font-medium text-foreground mb-1">Ordem</label>
                                    <input
                                        type="number" value={formData.ordem}
                                        onChange={e => setFormData({ ...formData, ordem: parseInt(e.target.value) || 0 })}
                                        className="w-full px-3 py-2 bg-background border border-border rounded-lg text-foreground focus:outline-none focus:ring-2 focus:ring-primary/50"
                                        placeholder="0"
                                    />
                                </div>
                            </div>
                            <div className="flex items-center gap-2">
                                <input
                                    type="checkbox" checked={formData.ativo}
                                    onChange={e => setFormData({ ...formData, ativo: e.target.checked })}
                                    className="rounded border-border"
                                    id="plano-ativo"
                                />
                                <label htmlFor="plano-ativo" className="text-sm text-foreground">Plano ativo</label>
                            </div>
                        </div>
                        <div className="flex items-center justify-end gap-3 px-6 py-4 border-t border-border bg-muted/30">
                            <button
                                onClick={() => setShowModal(false)}
                                className="px-4 py-2 text-sm font-medium text-muted-foreground hover:text-foreground transition-colors"
                            >
                                Cancelar
                            </button>
                            <button
                                onClick={handleSave}
                                disabled={!formData.nome || !formData.preco}
                                className="flex items-center gap-2 px-4 py-2 bg-primary text-primary-foreground rounded-lg hover:bg-primary/90 transition-colors text-sm font-medium disabled:opacity-50 disabled:cursor-not-allowed"
                            >
                                <Check className="w-4 h-4" />
                                {editingPlano ? 'Salvar' : 'Criar Plano'}
                            </button>
                        </div>
                    </div>
                </div>
            )}
        </div>
    );
}
