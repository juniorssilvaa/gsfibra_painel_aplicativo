import React, { useState, useEffect } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import axios from 'axios';
import { motion, AnimatePresence } from 'framer-motion';
import {
    Bot, Plus, Play, Trash2, Edit3,
    Search, Calendar, MessageSquare, ChevronRight,
    X, Check, AlertCircle, Layout, Share2
} from 'lucide-react';
import logo from '../assets/logo.png';
import { useLanguage } from '../contexts/LanguageContext';

const ChatbotManager = () => {
    const { t } = useLanguage();
    const { provedorId } = useParams();
    const navigate = useNavigate();
    const [flows, setFlows] = useState([]);
    const [loading, setLoading] = useState(true);
    const [searchQuery, setSearchQuery] = useState('');
    const [isCreateModalOpen, setIsCreateModalOpen] = useState(false);
    const [isEditModalOpen, setIsEditModalOpen] = useState(false);
    const [newFlowName, setNewFlowName] = useState('');
    const [editingFlow, setEditingFlow] = useState(null);
    const [isCreating, setIsCreating] = useState(false);
    const [isSaving, setIsSaving] = useState(false);
    const [channels, setChannels] = useState([]);
    const [selectedChannel, setSelectedChannel] = useState('');

    useEffect(() => {
        fetchFlows();
        fetchChannels();
    }, [provedorId]);

    const fetchChannels = async () => {
        try {
            const response = await axios.get(`/api/canais/?provedor=${provedorId}`);
            setChannels(response.data.results || response.data || []);
        } catch (error) {
            console.error('Erro ao buscar canais:', error);
        }
    };

    const fetchFlows = async () => {
        setLoading(true);
        try {
            const response = await axios.get(`/api/chatbot-flows/?provedor=${provedorId}`);
            const data = Array.isArray(response.data) ? response.data : (response.data.results || []);
            setFlows(data);
        } catch (error) {
            console.error('Erro ao buscar fluxos:', error);
        } finally {
            setLoading(false);
        }
    };

    const handleCreateFlow = async (e) => {
        e.preventDefault();
        if (!newFlowName.trim()) return;

        setIsCreating(true);
        try {
            const initialNodes = [{
                id: 'node_' + Date.now(),
                type: 'start',
                position: { x: 250, y: 150 },
                data: { label: 'Início do Chatbot' }
            }];

            const response = await axios.post('/api/chatbot-flows/', {
                name: newFlowName,
                provedor: provedorId,
                canal: selectedChannel || null,
                nodes: initialNodes,
                edges: []
            });

            setIsCreateModalOpen(false);
            setNewFlowName('');
            setSelectedChannel('');
            navigate(`/app/accounts/${provedorId}/chatbot-builder/${response.data.id}`);
        } catch (error) {
            console.error('Erro ao criar fluxo:', error);
            alert('Erro ao criar fluxo de chatbot.');
        } finally {
            setIsCreating(false);
        }
    };

    const handleDeleteFlow = async (id, e) => {
        e.stopPropagation();
        if (!window.confirm('Tem certeza que deseja excluir este fluxo?')) return;

        try {
            await axios.delete(`/api/chatbot-flows/${id}/`);
            setFlows(flows.filter(f => f.id !== id));
        } catch (error) {
            console.error('Erro ao excluir fluxo:', error);
            alert('Erro ao excluir fluxo.');
        }
    };

    const handleEditClick = (flow, e) => {
        e.stopPropagation();
        setEditingFlow(flow);
        setNewFlowName(flow.name);
        setSelectedChannel(flow.canal || '');
        setIsEditModalOpen(true);
    };

    const handleUpdateFlow = async (e) => {
        e.preventDefault();
        if (!newFlowName.trim() || !editingFlow) return;

        setIsSaving(true);
        try {
            const response = await axios.patch(`/api/chatbot-flows/${editingFlow.id}/`, {
                name: newFlowName,
                canal: selectedChannel || null
            });

            setFlows(flows.map(f => f.id === editingFlow.id ? response.data : f));
            setIsEditModalOpen(false);
            setEditingFlow(null);
            setNewFlowName('');
            setSelectedChannel('');
        } catch (error) {
            console.error('Erro ao atualizar fluxo:', error);
            alert('Erro ao atualizar nome do fluxo.');
        } finally {
            setIsSaving(false);
        }
    };

    const filteredFlows = flows.filter(flow =>
        flow.name.toLowerCase().includes(searchQuery.toLowerCase())
    );

    const formatDate = (dateString) => {
        return new Date(dateString).toLocaleDateString('pt-BR', {
            day: '2-digit',
            month: '2-digit',
            year: 'numeric',
            hour: '2-digit',
            minute: '2-digit'
        });
    };

    return (
        <div className="flex flex-col h-full bg-background overflow-hidden">
            {/* Header */}
            <div className="px-6 py-6 bg-white/80 dark:bg-background/80 backdrop-blur-md border-b border-border relative z-50">

                <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 relative z-10">
                    <div className="flex items-center gap-4">
                        <div className="w-12 h-12 rounded-2xl bg-white/10 flex items-center justify-center shadow-lg border border-white/20 backdrop-blur-sm">
                            <img src={logo} alt="Logo" className="w-8 h-8 object-contain" />
                        </div>
                        <div>
                            <h1 className="text-2xl font-bold text-foreground">{t('gestor_chatbot')}</h1>
                            <p className="text-muted-foreground text-sm">Crie e gerencie fluxos de atendimento automatizados</p>
                        </div>
                    </div>

                    <div className="flex flex-wrap gap-3">
                        <button
                            onClick={() => {
                                const input = document.createElement('input');
                                input.type = 'file';
                                input.accept = '.json';
                                input.onchange = async (e) => {
                                    const file = e.target.files[0];
                                    if (!file) return;
                                    
                                    const formData = new FormData();
                                    formData.append('file', file);
                                    formData.append('provedor', provedorId);

                                    try {
                                        setIsCreating(true);
                                        const response = await axios.post('/api/chatbot-flows/import_flow/', formData, {
                                            headers: { 'Content-Type': 'multipart/form-data' }
                                        });
                                        setFlows(prev => [response.data, ...prev]);
                                        alert('Fluxo importado com sucesso!');
                                    } catch (error) {
                                        console.error('Erro ao importar fluxo:', error);
                                        alert('Erro ao importar fluxo. Verifique o arquivo JSON.');
                                    } finally {
                                        setIsCreating(false);
                                    }
                                };
                                input.click();
                            }}
                            disabled={isCreating}
                            className="flex items-center justify-center gap-2 px-6 py-3 bg-card text-foreground font-bold rounded-xl transition-colors border border-border hover:bg-muted disabled:opacity-60"
                        >
                            <Share2 size={20} className="rotate-180" />
                            {t('importar_fluxo') || 'Importar Fluxo'}
                        </button>

                        <button
                            onClick={() => {
                                setNewFlowName('');
                                setIsCreateModalOpen(true);
                            }}
                            className="flex items-center justify-center gap-2 px-6 py-3 bg-emerald-600 hover:bg-emerald-500 text-white font-bold rounded-xl transition-colors border border-emerald-700/60"
                        >
                            <Plus size={20} />
                            {t('criar_novo_fluxo')}
                        </button>
                    </div>
                </div>
            </div>

            {/* Content Area */}
            <div className="flex-1 overflow-y-auto p-6">
                <div className="max-w-6xl mx-auto space-y-6">
                    {/* Search and Filters */}
                    <div className="relative">
                        <Search className="absolute left-4 top-1/2 -translate-y-1/2 text-muted-foreground w-5 h-5" />
                        <input
                            type="text"
                            placeholder={t('buscar_fluxos')}
                            value={searchQuery}
                            onChange={(e) => setSearchQuery(e.target.value)}
                            className="w-full pl-12 pr-4 py-4 bg-card border border-border rounded-2xl focus:ring-2 focus:ring-blue-500 outline-none transition-all shadow-sm"
                        />
                    </div>

                    {loading ? (
                        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
                            {[1, 2, 3].map(i => (
                                <div key={i} className="h-48 bg-card animate-pulse rounded-3xl border border-border"></div>
                            ))}
                        </div>
                    ) : filteredFlows.length > 0 ? (
                        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
                            {filteredFlows.map((flow) => (
                                <motion.div
                                    key={flow.id}
                                    layout
                                    initial={{ opacity: 0, y: 20 }}
                                    animate={{ opacity: 1, y: 0 }}
                                    whileHover={{ y: -2 }}
                                    onClick={() => navigate(`/app/accounts/${provedorId}/chatbot-builder/${flow.id}`)}
                                    className="group relative bg-card border border-border rounded-3xl p-6 hover:border-primary/50 transition-colors cursor-pointer overflow-hidden"
                                >
                                    <div className="absolute top-0 right-0 w-32 h-32 bg-primary/5 rounded-full blur-2xl -mr-16 -mt-16 group-hover:bg-primary/10 transition-colors"></div>

                                    <div className="flex justify-between items-start mb-4 relative z-10">
                                        <div className="p-3 rounded-2xl bg-muted group-hover:bg-primary group-hover:text-white transition-colors duration-200">
                                            <Layout size={24} />
                                        </div>
                                        <div className="flex gap-2">
                                            <button
                                                onClick={(e) => handleEditClick(flow, e)}
                                                className="p-2 text-muted-foreground hover:text-blue-500 hover:bg-blue-500/10 rounded-xl transition-all"
                                                title={t('editar')}
                                            >
                                                <Edit3 size={18} />
                                            </button>
                                            <button
                                                onClick={(e) => handleDeleteFlow(flow.id, e)}
                                                className="p-2 text-muted-foreground hover:text-red-500 hover:bg-red-500/10 rounded-xl transition-all"
                                                title={t('deletar')}
                                            >
                                                <Trash2 size={18} />
                                            </button>
                                        </div>
                                    </div>

                                    <h3 className="text-lg font-bold text-foreground mb-2 group-hover:text-primary transition-colors">
                                        {flow.name}
                                    </h3>

                                    <div className="space-y-3 relative z-10">
                                        <div className="flex items-center gap-2 text-xs text-muted-foreground">
                                            <MessageSquare size={14} />
                                            <span>{flow.nodes?.length || 0} {t('blocos_no_fluxo')}</span>
                                        </div>
                                        <div className="flex items-center gap-2 text-xs text-muted-foreground">
                                            <Calendar size={14} />
                                            <span>{t('atualizado_em')} {formatDate(flow.updated_at)}</span>
                                        </div>
                                        {flow.canal_nome && (
                                            <div className="flex items-center gap-2 text-xs font-medium text-primary bg-primary/10 px-2 py-1 rounded-lg w-fit">
                                                <Check size={12} />
                                                <span>{flow.canal_nome}</span>
                                            </div>
                                        )}
                                    </div>

                                    <div className="mt-6 pt-4 border-t border-border flex items-center justify-between group-hover:border-primary/30 transition-colors text-primary font-bold text-sm">
                                        <span>{t('abrir_no_editor')}</span>
                                        <ChevronRight size={18} className="transform group-hover:translate-x-1 transition-transform" />
                                    </div>
                                </motion.div>
                            ))}
                        </div>
                    ) : (
                        <div className="flex flex-col items-center justify-center py-20 text-center bg-card rounded-3xl border border-dashed border-border p-10">
                            <div className="w-20 h-20 bg-muted rounded-full flex items-center justify-center mb-6 text-muted-foreground">
                                <Bot size={40} />
                            </div>
                            <h3 className="text-xl font-bold text-foreground mb-2">{t('nenhum_fluxo_encontrado')}</h3>
                            <p className="text-muted-foreground max-w-sm mb-8">
                                {searchQuery ? `Não encontramos fluxos com o nome "${searchQuery}"` : "Você ainda não criou nenhum fluxo de chatbot para este provedor."}
                            </p>
                            {!searchQuery && (
                                <button
                                    onClick={() => {
                                        setNewFlowName('');
                                        setIsCreateModalOpen(true);
                                    }}
                                    className="px-8 py-3 bg-emerald-600 hover:bg-emerald-500 text-white font-bold rounded-xl transition-colors border border-emerald-700/60"
                                >
                                    Começar agora
                                </button>
                            )}
                        </div>
                    )}
                </div>
            </div>

            {/* Create Flow Modal */}
            <AnimatePresence>
                {isCreateModalOpen && (
                    <div className="fixed inset-0 z-[100] flex items-center justify-center p-4">
                        <motion.div
                            initial={{ opacity: 0 }}
                            animate={{ opacity: 1 }}
                            exit={{ opacity: 0 }}
                            onClick={() => setIsCreateModalOpen(false)}
                            className="fixed inset-0 bg-black/60 backdrop-blur-sm"
                        />
                        <motion.div
                            initial={{ opacity: 0, scale: 0.9, y: 20 }}
                            animate={{ opacity: 1, scale: 1, y: 0 }}
                            exit={{ opacity: 0, scale: 0.9, y: 20 }}
                            className="relative w-full max-w-md bg-card border border-border rounded-3xl shadow-2xl overflow-hidden"
                            onClick={e => e.stopPropagation()}
                        >
                            <div className="px-8 py-6 border-b border-border bg-muted/30">
                                <div className="flex items-center justify-between">
                                    <h2 className="text-xl font-bold flex items-center gap-2">
                                        <Plus className="text-blue-500" />
                                        {t('novo_fluxo')}
                                    </h2>
                                    <button
                                        onClick={() => setIsCreateModalOpen(false)}
                                        className="p-2 hover:bg-muted rounded-xl transition-all"
                                    >
                                        <X size={20} />
                                    </button>
                                </div>
                            </div>

                            <form onSubmit={handleCreateFlow} className="p-8 space-y-6">
                                <div className="space-y-2">
                                    <label className="text-sm font-bold text-muted-foreground ml-1 uppercase tracking-wider">
                                        {t('nome_do_fluxo')}
                                    </label>
                                    <input
                                        autoFocus
                                        type="text"
                                        placeholder="Ex: Suporte Técnico, Vendas, FAQ..."
                                        value={newFlowName}
                                        onChange={(e) => setNewFlowName(e.target.value)}
                                        className="w-full px-5 py-4 bg-muted/30 border border-border rounded-2xl focus:ring-2 focus:ring-blue-500 outline-none transition-all font-medium text-lg"
                                        required
                                    />
                                </div>

                                <div className="space-y-2">
                                    <label className="text-sm font-bold text-muted-foreground ml-1 uppercase tracking-wider">
                                        {t('canal_vinculado') || 'Canal Vinculado'}
                                    </label>
                                    <select
                                        value={selectedChannel}
                                        onChange={(e) => setSelectedChannel(e.target.value)}
                                        className="w-full px-5 py-4 bg-muted/30 border border-border rounded-2xl focus:ring-2 focus:ring-blue-500 outline-none transition-all font-medium text-lg shadow-inner text-foreground"
                                    >
                                        <option value="">{t('selecione_um_canal') || 'Selecione um Canal'}</option>
                                        {channels.map(channel => (
                                            <option key={channel.id} value={channel.id}>
                                                {channel.nome} ({channel.tipo})
                                            </option>
                                        ))}
                                    </select>
                                    <p className="text-xs text-muted-foreground ml-1">
                                        Opcional. Se selecionado, este fluxo só responderá neste canal.
                                    </p>
                                </div>

                                <div className="flex gap-3 pt-2">
                                    <button
                                        type="button"
                                        onClick={() => setIsCreateModalOpen(false)}
                                        className="flex-1 py-4 font-bold text-muted-foreground hover:bg-muted rounded-2xl transition-all"
                                    >
                                        {t('cancelar')}
                                    </button>
                                    <button
                                        type="submit"
                                        disabled={isCreating || !newFlowName.trim()}
                                        className="flex-[2] py-4 bg-blue-600 hover:bg-blue-500 disabled:opacity-50 text-white font-bold rounded-2xl transition-all shadow-lg shadow-blue-500/20 active:scale-95 flex items-center justify-center gap-2"
                                    >
                                        {isCreating ? (
                                            <div className="w-5 h-5 border-2 border-white border-t-transparent rounded-full animate-spin" />
                                        ) : (
                                            <>
                                                <Check size={20} />
                                                {t('criar_e_editar')}
                                            </>
                                        )}
                                    </button>
                                </div>
                            </form>
                        </motion.div>
                    </div>
                )}
            </AnimatePresence>

            {/* Edit Flow Modal */}
            <AnimatePresence>
                {isEditModalOpen && (
                    <div className="fixed inset-0 z-[100] flex items-center justify-center p-4">
                        <motion.div
                            initial={{ opacity: 0 }}
                            animate={{ opacity: 1 }}
                            exit={{ opacity: 0 }}
                            onClick={() => setIsEditModalOpen(false)}
                            className="fixed inset-0 bg-black/60 backdrop-blur-sm"
                        />
                        <motion.div
                            initial={{ opacity: 0, scale: 0.9, y: 20 }}
                            animate={{ opacity: 1, scale: 1, y: 0 }}
                            exit={{ opacity: 0, scale: 0.9, y: 20 }}
                            className="relative w-full max-w-md bg-card border border-border rounded-3xl shadow-2xl overflow-hidden"
                            onClick={e => e.stopPropagation()}
                        >
                            <div className="px-8 py-6 border-b border-border bg-muted/30">
                                <div className="flex items-center justify-between">
                                    <h2 className="text-xl font-bold flex items-center gap-2">
                                        <Edit3 className="text-blue-500" />
                                        {t('editar_fluxo') || 'Editar Fluxo'}
                                    </h2>
                                    <button
                                        onClick={() => setIsEditModalOpen(false)}
                                        className="p-2 hover:bg-muted rounded-xl transition-all"
                                    >
                                        <X size={20} />
                                    </button>
                                </div>
                            </div>

                            <form onSubmit={handleUpdateFlow} className="p-8 space-y-6">
                                <div className="space-y-2">
                                    <label className="text-sm font-bold text-muted-foreground ml-1 uppercase tracking-wider">
                                        {t('nome_do_fluxo')}
                                    </label>
                                    <input
                                        autoFocus
                                        type="text"
                                        placeholder="Ex: Suporte Técnico, Vendas, FAQ..."
                                        value={newFlowName}
                                        onChange={(e) => setNewFlowName(e.target.value)}
                                        className="w-full px-5 py-4 bg-muted/30 border border-border rounded-2xl focus:ring-2 focus:ring-blue-500 outline-none transition-all font-medium text-lg"
                                        required
                                    />
                                </div>

                                <div className="space-y-2">
                                    <label className="text-sm font-bold text-muted-foreground ml-1 uppercase tracking-wider">
                                        {t('canal_vinculado') || 'Canal Vinculado'}
                                    </label>
                                    <select
                                        value={selectedChannel}
                                        onChange={(e) => setSelectedChannel(e.target.value)}
                                        className="w-full px-5 py-4 bg-muted/30 border border-border rounded-2xl focus:ring-2 focus:ring-blue-500 outline-none transition-all font-medium text-lg shadow-inner text-foreground"
                                    >
                                        <option value="">{t('selecione_um_canal') || 'Selecione um Canal'}</option>
                                        {channels.map(channel => (
                                            <option key={channel.id} value={channel.id}>
                                                {channel.nome} ({channel.tipo})
                                            </option>
                                        ))}
                                    </select>
                                </div>

                                <div className="flex gap-3 pt-2">
                                    <button
                                        type="button"
                                        onClick={() => setIsEditModalOpen(false)}
                                        className="flex-1 py-4 font-bold text-muted-foreground hover:bg-muted rounded-2xl transition-all"
                                    >
                                        {t('cancelar')}
                                    </button>
                                    <button
                                        type="submit"
                                        disabled={isSaving || !newFlowName.trim()}
                                        className="flex-[2] py-4 bg-blue-600 hover:bg-blue-500 disabled:opacity-50 text-white font-bold rounded-2xl transition-all shadow-lg shadow-blue-500/20 active:scale-95 flex items-center justify-center gap-2"
                                    >
                                        {isSaving ? (
                                            <div className="w-5 h-5 border-2 border-white border-t-transparent rounded-full animate-spin" />
                                        ) : (
                                            <>
                                                <Check size={20} />
                                                {t('salvar') || 'Salvar'}
                                            </>
                                        )}
                                    </button>
                                </div>
                            </form>
                        </motion.div>
                    </div>
                )}
            </AnimatePresence>
        </div>
    );
};

export default ChatbotManager;
