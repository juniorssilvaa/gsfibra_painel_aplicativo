import React, { useState, useEffect, useRef } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import axios from 'axios';
import { motion, AnimatePresence } from 'framer-motion';
import {
    Bot, Plus, Share2, Play, MousePointer2, Save,
    ArrowLeft, Settings, Trash2, MessageSquare,
    Zap, GitBranch, Database, Globe, X, Check,
    GripVertical, Info, Send, User, ChevronRight, List,
    Eye, EyeOff, Wifi, XCircle, ChevronDown, ChevronUp, Clock, Image as LucideImage
} from 'lucide-react';
import { useLanguage } from '../contexts/LanguageContext';

const NODE_TYPES = {
    start: { label: 'Início', color: 'text-slate-400', icon: Play },
    message: { label: 'Mensagem', color: 'text-slate-400', icon: MessageSquare },
    sgp: { label: 'Consulta SGP', color: 'text-slate-400', icon: Database },
    planos: { label: 'Planos de Internet', color: 'text-slate-400', icon: Wifi },
    menu: { label: 'Lista Interativa (WhatsApp)', color: 'text-slate-400', icon: List },
    galeria: { label: 'Galeria', color: 'text-slate-400', icon: LucideImage },
    transfer: { label: 'Transferir Atendimento', color: 'text-slate-400', icon: Share2 },
    close: { label: 'Encerrar Atendimento', color: 'text-slate-400', icon: XCircle },
};

/** Largura fixa do cartão no canvas (arestas SVG usam o mesmo valor). */
const NODE_CARD_WIDTH = 280;

const ChatbotBuilder = () => {
    const { t } = useLanguage();
    const { provedorId, flowId } = useParams();
    const navigate = useNavigate();
    const [loading, setLoading] = useState(false);
    const [currentFlow, setCurrentFlow] = useState(null);
    const [isSaving, setIsSaving] = useState(false);
    const [selectedNode, setSelectedNode] = useState(null);
    const [isEditorOpen, setIsEditorOpen] = useState(false);
    const canvasRef = useRef(null);

    // Flow State
    const [nodes, setNodes] = useState([]);
    const [edges, setEdges] = useState([]);

    // Connection State
    const [isConnecting, setIsConnecting] = useState(false);
    const [connectionSource, setConnectionSource] = useState(null);
    const [connectionSourceHandle, setConnectionSourceHandle] = useState(null);
    const [mousePos, setMousePos] = useState({ x: 0, y: 0 });
    const [hoveredNodeId, setHoveredNodeId] = useState(null);
    const [hoveredEdgeId, setHoveredEdgeId] = useState(null);

    // Simulator State
    const [showSimulator, setShowSimulator] = useState(false);
    const [simMessages, setSimMessages] = useState([]);
    const [currentNodeId, setCurrentNodeId] = useState(null);

    // Canvas & Context Menu State
    const [canvasOffset, setCanvasOffset] = useState({ x: 0, y: 0 });
    const [canvasZoom, setCanvasZoom] = useState(1);
    const [isPanning, setIsPanning] = useState(false);
    const [contextMenu, setContextMenu] = useState({ show: false, x: 0, y: 0, type: null, targetId: null });
    const [availableTeams, setAvailableTeams] = useState([]);
    const [availablePlanos, setAvailablePlanos] = useState([]);
    const [galleryImages, setGalleryImages] = useState([]);

    useEffect(() => {
        const fetchFlowData = async () => {
            console.log("Iniciando carregamento de fluxo:", flowId || 'primeiro disponível');
            setLoading(true);
            try {
                let flow;
                if (flowId) {
                    const response = await axios.get(`/api/chatbot-flows/${flowId}/`);
                    flow = response.data;
                } else {
                    const response = await axios.get(`/api/chatbot-flows/?provedor=${provedorId}`);
                    const flows = Array.isArray(response.data) ? response.data : (response.data.results || []);
                    if (flows.length > 0) {
                        flow = flows[0];
                    }
                }

                if (flow) {
                    console.log("Fluxo carregado:", flow.id, "Nodes:", flow.nodes?.length);
                    setCurrentFlow(flow);
                    setNodes(flow.nodes || []);
                    setEdges(flow.edges || []);
                } else {
                    console.log("Nenhum fluxo encontrado.");
                    // Se não houver fluxo e estivermos no builder sem ID, talvez redirecionar para o manager em breve
                }
            } catch (error) {
                console.error('Erro ao buscar fluxo:', error);
            } finally {
                setLoading(false);
            }
        };

        const fetchTeams = async () => {
            try {
                const response = await axios.get(`/api/teams/?provedor=${provedorId}`);
                const teams = Array.isArray(response.data) ? response.data : (response.data.results || []);
                setAvailableTeams(teams);
            } catch (error) {
                console.error('Erro ao buscar equipes:', error);
            }
        };

        const fetchPlanos = async () => {
            try {
                const response = await axios.get(`/api/planos/?provedor=${provedorId}`);
                const planos = Array.isArray(response.data) ? response.data : (response.data.results || []);
                setAvailablePlanos(planos.filter(p => p.ativo));
            } catch (error) {
                console.error('Erro ao buscar planos:', error);
            }
        };

        const fetchGalleryImages = async () => {
            try {
                const response = await axios.get(`/api/provider-gallery/?provedor=${provedorId}`);
                const images = Array.isArray(response.data) ? response.data : (response.data.results || []);
                setGalleryImages(images);
            } catch (error) {
                console.error('Erro ao buscar galeria:', error);
            }
        };

        if (provedorId) {
            fetchFlowData();
            fetchTeams();
            fetchPlanos();
            fetchGalleryImages();
        }
    }, [provedorId, flowId]);

    const handleCreateFlow = async () => {
        setLoading(true);
        try {
            // First check if one already exists to avoid duplication
            const existing = await axios.get(`/api/chatbot-flows/?provedor=${provedorId}`);
            const flows = Array.isArray(existing.data) ? existing.data : (existing.data.results || []);

            if (flows.length > 0) {
                const flow = flows[0];
                setCurrentFlow(flow);
                setNodes(flow.nodes || []);
                setEdges(flow.edges || []);
                setLoading(false);
                return;
            }

            const initialNodes = [{
                id: 'node_' + Date.now(),
                type: 'start',
                position: { x: 250, y: 150 },
                data: { label: 'Início do Chatbot' }
            }];
            const response = await axios.post('/api/chatbot-flows/', {
                name: 'Novo Fluxo de Chatbot',
                provedor: provedorId,
                nodes: initialNodes,
                edges: []
            });
            console.log("Fluxo criado com ID:", response.data.id);
            setCurrentFlow(response.data);
            setNodes(initialNodes);
            setEdges([]);
        } catch (error) {
            console.error('Erro ao criar fluxo:', error);
            alert('Erro ao criar fluxo de chatbot.');
        } finally {
            setLoading(false);
        }
    };

    const handleSaveFlow = async () => {
        if (!currentFlow) return;
        setIsSaving(true);
        try {
            console.log("Salvando fluxo ID:", currentFlow.id, "Nodes:", nodes.length, "Edges:", edges.length);
            console.log("Edges a salvar:", JSON.stringify(edges.map(e => ({ id: e.id, source: e.source, target: e.target, sourceHandle: e.sourceHandle })), null, 2));
            const response = await axios.put(`/api/chatbot-flows/${currentFlow.id}/`, {
                id: currentFlow.id,
                name: currentFlow.name,
                provedor: currentFlow.provedor,
                nodes: nodes,
                edges: edges
            });
            setCurrentFlow(response.data);
            setNodes(response.data.nodes || []);
            setEdges(response.data.edges || []);
            alert('Fluxo salvo com sucesso!');
        } catch (error) {
            console.error('Erro ao salvar fluxo:', error);
            alert('Erro ao salvar o fluxo.');
        } finally {
            setIsSaving(false);
        }
    };

    const addNode = (type, pos = null) => {
        const spawnPos = pos || { x: 300 - canvasOffset.x, y: 200 - canvasOffset.y };
        const newNode = {
            id: 'node_' + Date.now(),
            type,
            position: spawnPos,
            data: {
                label: NODE_TYPES[type].label,
                content: '',
                buttons: []
            }
        };
        setNodes(curr => [...curr, newNode]);
        setSelectedNode(newNode.id);
        setIsEditorOpen(true);
        setContextMenu({ show: false, x: 0, y: 0, type: null, targetId: null });
    };

    const updateNodePosition = (id, delta) => {
        setNodes(curr => curr.map(n => n.id === id ? {
            ...n,
            position: { x: n.position.x + delta.x, y: n.position.y + delta.y }
        } : n));
    };

    const updateNodeData = (id, data) => {
        setNodes(curr => curr.map(n => n.id === id ? { ...n, data: { ...n.data, ...data } } : n));
    };

    const deleteNode = (id) => {
        setNodes(curr => curr.filter(n => n.id !== id));
        setEdges(curr => curr.filter(e => e.source !== id && e.target !== id));
        if (selectedNode === id) {
            setSelectedNode(null);
            setIsEditorOpen(false);
        }
    };

    // Connection Handlers

    const startConnection = (e, nodeId, handleId = null) => {
        e.stopPropagation();
        setIsConnecting(true);
        setConnectionSource(nodeId);
        setConnectionSourceHandle(handleId);
        const rect = canvasRef.current.getBoundingClientRect();
        setMousePos({
            x: (e.clientX - rect.left - canvasOffset.x) / canvasZoom,
            y: (e.clientY - rect.top - canvasOffset.y) / canvasZoom
        });
    };

    const finalizeConnection = (targetId) => {
        if (isConnecting && connectionSource && connectionSource != targetId) {
            const exists = edges.some(e =>
                e.source == connectionSource &&
                e.target == targetId &&
                e.sourceHandle == connectionSourceHandle
            );
            if (!exists) {
                setEdges(prev => [...prev, {
                    id: `edge_${Date.now()}`,
                    source: connectionSource,
                    target: targetId,
                    sourceHandle: connectionSourceHandle
                }]);
            }
        }
        setIsConnecting(false);
        setConnectionSource(null);
        setConnectionSourceHandle(null);
    };

    const deleteEdge = (edgeId) => {
        setEdges(curr => curr.filter(e => e.id !== edgeId));
        setContextMenu({ show: false, x: 0, y: 0, type: null, targetId: null });
    };

    const handleCanvasContextMenu = (e) => {
        e.preventDefault();
        const rect = canvasRef.current.getBoundingClientRect();
        setContextMenu({
            show: true,
            x: e.clientX - rect.left,
            y: e.clientY - rect.top,
            type: 'canvas',
            targetId: null
        });
        setSelectedNode(null);
        setIsEditorOpen(false);
    };

    const handleCanvasMouseDown = (e) => {
        if (e.button === 0) {
            setIsPanning(true);
            setContextMenu({ show: false, x: 0, y: 0 });
        }
    };

    const handleCanvasMouseMove = (e) => {
        const rect = canvasRef.current.getBoundingClientRect();
        const x = e.clientX - rect.left;
        const y = e.clientY - rect.top;

        if (isPanning) {
            setCanvasOffset(prev => ({
                x: prev.x + e.movementX,
                y: prev.y + e.movementY
            }));
            return;
        }

        if (isConnecting) {
            setMousePos({
                x: (x - canvasOffset.x) / canvasZoom,
                y: (y - canvasOffset.y) / canvasZoom
            });
        }
    };

    const handleCanvasMouseUp = (e) => {
        setIsPanning(false);
        if (isConnecting && connectionSource) {
            // If released on empty canvas, show menu to create new node
            const rect = canvasRef.current.getBoundingClientRect();
            setContextMenu({
                show: true,
                x: e.clientX - rect.left,
                y: e.clientY - rect.top,
                type: 'connection',
                targetId: connectionSource,
                sourceHandle: connectionSourceHandle
            });
        }
        setIsConnecting(false);
        setConnectionSource(null);
    };

    // Simulator Logic
    const startSimulator = () => {
        const startNode = nodes.find(n => n.type === 'start');
        if (!startNode) {
            alert('Adicione um bloco de Início para testar.');
            return;
        }
        setSimMessages([{ role: 'system', content: 'Simulador Iniciado' }]);
        setCurrentNodeId(startNode.id);
        setShowSimulator(true);
        processNextStep(startNode.id);
    };
    const processNextStep = (nodeId, buttonId = null) => {
        let nextEdge = edges.find(e => e.source === nodeId && e.sourceHandle === buttonId);

        // Fallback RESTRITO (como no backend)
        if (!nextEdge) {
            const edgesFromCurrent = edges.filter(e => e.source === nodeId);
            if (edgesFromCurrent.length === 1) {
                // Se houver apenas uma saída, seguimos ela (compatibilidade)
                nextEdge = edgesFromCurrent[0];
            } else if (!buttonId) {
                // Se for texto simples, procurar aresta sem handle
                nextEdge = edgesFromCurrent.find(e => !e.sourceHandle);
            }
        }

        if (!nextEdge) {
            setSimMessages(prev => [...prev, { role: 'bot', content: 'Fim do fluxo (sem mais conexões).' }]);
            return;
        }

        const nextNode = nodes.find(n => n.id === nextEdge.target);
        if (nextNode) {
            setTimeout(() => {
                if (nextNode.type === 'message') {
                    const buttons = nextNode.data.buttons || [];
                    setSimMessages(prev => [...prev, {
                        role: 'bot',
                        content: nextNode.data.content || '...',
                        buttons: buttons
                    }]);

                    // Sempre atualizar o nó atual no simulador
                    setCurrentNodeId(nextNode.id);

                    // Se não tiver botões, continua automaticamente após um delay
                    if (buttons.length === 0) {
                        processNextStep(nextNode.id);
                    }
                } else if (nextNode.type === 'menu' || nextNode.type === 'planos') {
                    const rows = nextNode.data.rows || [];
                    setSimMessages(prev => [...prev, {
                        role: 'bot',
                        content: nextNode.data.content || '...',
                        menu: {
                            buttonText: nextNode.data.buttonText,
                            sectionTitle: nextNode.data.sectionTitle,
                            headerText: nextNode.data.headerText,
                            footerText: nextNode.data.footerText,
                            rows: rows
                        }
                    }]);
                    setCurrentNodeId(nextNode.id);
                } else if (nextNode.type === 'transfer') {
                    setSimMessages(prev => [...prev, {
                        role: 'bot',
                        content: nextNode.data.content || '...',
                    }]);
                    if (nextNode.data.transferMode === 'choice') {
                        setSimMessages(prev => [...prev, {
                            role: 'system',
                            content: 'Simulando: Listando equipes para o usuário escolher...'
                        }]);
                    } else {
                        setSimMessages(prev => [...prev, {
                            role: 'system',
                            content: `Simulando: Transferência direta para equipe ID ${nextNode.data.teamId || '(não selecionada)'}. Atendimento Encerrado.`
                        }]);
                    }
                    setCurrentNodeId(nextNode.id);
                    // Não chama processNextStep pois transfer é terminal
                } else if (nextNode.type === 'close') {
                    setSimMessages(prev => [...prev, {
                        role: 'bot',
                        content: nextNode.data.content || 'Atendimento encerrado.',
                    }]);
                    setSimMessages(prev => [...prev, {
                        role: 'system',
                        content: 'Simulando: Atendimento Finalizado.'
                    }]);
                    setCurrentNodeId(nextNode.id);
                    // Terminal
                } else {
                    setSimMessages(prev => [...prev, { role: 'system', content: `Executando: ${nextNode.data.label}` }]);
                    setCurrentNodeId(nextNode.id);
                    processNextStep(nextNode.id);
                }
            }, 800);
        }
    };

    const Node = ({ node }) => {
        const TypeConfig = NODE_TYPES[node.type] || NODE_TYPES.message;
        const isSelected = selectedNode === node.id;

        return (
            <motion.div
                drag
                dragMomentum={false}
                onDrag={(e, info) => {
                    updateNodePosition(node.id, info.delta);
                }}
                initial={false}
                style={{
                    position: 'absolute',
                    top: node.position.y,
                    left: node.position.x,
                    width: NODE_CARD_WIDTH,
                    x: 0,
                    y: 0
                }}
                onMouseUp={(e) => {
                    if (isConnecting) {
                        e.stopPropagation();
                        finalizeConnection(node.id);
                    }
                }}
                onMouseDown={(e) => {
                    e.stopPropagation();
                }}
                onClick={(e) => {
                    e.stopPropagation();
                    setSelectedNode(node.id);
                    setIsEditorOpen(false);
                }}
                onMouseEnter={() => setHoveredNodeId(node.id)}
                onMouseLeave={() => setHoveredNodeId(curr => (curr === node.id ? null : curr))}
                className={`group flex flex-col bg-card border border-border rounded-2xl transition-all cursor-move z-20 ${isSelected ? 'ring-2 ring-primary border-primary' : 'hover:border-accent/50'
                    }`}
            >
                {/* Header do Nó */}
                <div className="relative flex items-start gap-2.5 p-3 border-b border-border bg-card rounded-t-2xl text-foreground">
                    {/* Input Point (Left) — alinhado ao centro vertical do cabeçalho */}
                    <div className="absolute -left-1.5 top-1/2 -translate-y-1/2 w-3 h-3 bg-muted border-2 border-card rounded-full z-30" />
                    <div className={`${TypeConfig.color} shrink-0 mt-0.5`}>
                        <TypeConfig.icon size={20} strokeWidth={1.5} />
                    </div>
                    <div className="flex flex-col flex-1 min-w-0 pr-1">
                        <span className="text-[10px] font-black uppercase tracking-widest text-muted-foreground leading-tight">
                            {TypeConfig.label}
                        </span>
                        <span className="text-[11px] font-bold text-foreground mt-1 break-words whitespace-normal leading-snug">
                            {node.data.label || 'Nó sem título'}
                        </span>
                    </div>

                    <div className="flex items-center gap-1">
                        <button
                            onClick={(e) => {
                                e.stopPropagation();
                                updateNodeData(node.id, { isCollapsed: !node.data.isCollapsed });
                                setSelectedNode(node.id);
                            }}
                            className="p-1.5 hover:bg-muted rounded-lg text-muted-foreground hover:text-foreground transition-all"
                            title={node.data.isCollapsed ? "Expandir bloco" : "Recolher bloco"}
                        >
                            {node.data.isCollapsed ? <ChevronDown size={14} /> : <ChevronUp size={14} />}
                        </button>

                        <button
                            onClick={(e) => {
                                e.stopPropagation();
                                setSelectedNode(node.id);
                                setIsEditorOpen(true);
                            }}
                            className="p-1.5 hover:bg-muted rounded-lg text-primary hover:text-primary/80 transition-all"
                            title="Abrir Editor"
                        >
                            <Eye size={14} />
                        </button>

                        <button
                            onClick={(e) => { e.stopPropagation(); deleteNode(node.id); }}
                            className="opacity-0 group-hover:opacity-100 p-1.5 bg-red-500/10 hover:bg-red-500 text-red-500 hover:text-white rounded-xl transition-all"
                        >
                            <Trash2 size={14} />
                        </button>
                    </div>

                    {/* Output Point (General) - Apenas se não tiver botões ou for start/api. Transferir e Close são terminais. */}
                    {(!node.data.buttons || node.data.buttons.length === 0) && (!node.data.rows || node.data.rows.length === 0) && node.type !== 'transfer' && node.type !== 'close' && node.type !== 'planos' && (
                        <div
                            onMouseDown={(e) => startConnection(e, node.id, null)}
                            className="absolute -right-2 top-1/2 -translate-y-1/2 w-4 h-4 rounded-full bg-primary border-2 border-card hover:scale-110 transition-transform cursor-crosshair z-30"
                        />
                    )}
                </div>

                {/* Botões do Nó (Para Branching) */}
                {
                    !node.data.isCollapsed && (node.data.buttons || []).map((btn, bidx) => (
                        <div key={btn.id} className="relative px-3 py-1.5 border-b border-border last:border-0 group/btn">
                            <div className="bg-background border border-border rounded-lg px-3 py-1.5 text-[10px] font-bold text-primary uppercase tracking-widest truncate">
                                {btn.title}
                            </div>
                            {/* Dot por botão */}
                            <div
                                onMouseDown={(e) => startConnection(e, node.id, btn.id)}
                                className="absolute -right-2 top-1/2 -translate-y-1/2 w-4 h-4 rounded-full bg-primary border-2 border-card hover:scale-110 transition-transform cursor-crosshair z-30"
                            />
                        </div>
                    ))
                }

                {/* Itens do Menu (Para Branching) */}
                {
                    !node.data.isCollapsed && (node.data.rows || []).map((row, ridx) => (
                        <div key={row.id} className="relative px-3 py-1.5 border-b border-border last:border-0 group/row">
                            <div className={`bg-background border border-border rounded-lg px-3 py-1.5 text-[10px] font-bold truncate ${node.type === 'planos' ? 'text-cyan-400' : 'text-emerald-400'}`}>
                                {row.title}
                                {row.description && <span className="text-muted-foreground ml-1">— {row.description}</span>}
                            </div>
                            {/* Dot por item */}
                            <div
                                onMouseDown={(e) => startConnection(e, node.id, row.id)}
                                className={`absolute -right-2 top-1/2 -translate-y-1/2 w-4 h-4 rounded-full border-2 border-card hover:scale-110 transition-transform cursor-crosshair z-30 ${node.type === 'planos' ? 'bg-cyan-500' : 'bg-emerald-500'}`}
                            />
                        </div>
                    ))
                }

                {/* Conteúdo Preview (Opcional) */}
                {
                    !node.data.isCollapsed && node.data.content && (
                        <div className="p-4 pt-2">
                            <p className="text-[10px] text-muted-foreground line-clamp-2 bg-background/30 p-2 rounded-lg italic border border-border/50">
                                "{node.data.content}"
                            </p>
                        </div>
                    )
                }
            </motion.div >
        );
    };

    if (loading) {
        return (
            <div className="flex h-full items-center justify-center bg-background">
                <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-primary"></div>
            </div>
        );
    }

    return (
        <div className="flex flex-col h-full bg-background overflow-hidden">
            {/* Top Toolbar */}
            <div className="flex items-center justify-between px-6 py-4 bg-white/80 dark:bg-background/80 backdrop-blur-md border-b border-slate-200 dark:border-border shadow-sm z-50">
                <div className="flex items-center gap-4">
                    <button
                        onClick={() => navigate(`/app/accounts/${provedorId}/chatbot-manager`)}
                        className="p-2 hover:bg-muted rounded-xl transition-all text-muted-foreground hover:text-foreground"
                        title="Voltar para Gestão"
                    >
                        <ArrowLeft size={20} />
                    </button>
                    <div className="h-6 w-px bg-border mx-1" />
                    <div className="text-foreground/70 dark:text-[#888888]">
                        <Bot size={28} strokeWidth={1.5} />
                    </div>
                    <div>
                        <h1 className="text-xl font-bold text-slate-800 dark:text-white leading-none tracking-tight">
                            Chatbot
                        </h1>
                        <p className="text-[10px] text-muted-foreground font-bold uppercase tracking-widest mt-1">
                            {currentFlow?.name || t('fluxo_principal')}
                        </p>
                    </div>
                </div>

                <div className="flex items-center gap-3">
                    {currentFlow && (
                        <>
                            <div className="flex bg-slate-100 dark:bg-slate-800 p-1 rounded-xl border border-slate-200 dark:border-slate-700 mr-2">
                                <button
                                    onClick={async () => {
                                        try {
                                            const res = await axios.get(`/api/chatbot-flows/${currentFlow.id}/export_flow/`, {
                                                responseType: 'blob'
                                            });
                                            const url = window.URL.createObjectURL(new Blob([res.data]));
                                            const link = document.createElement('a');
                                            link.href = url;
                                            link.setAttribute('download', `flow_${currentFlow.id}.json`);
                                            document.body.appendChild(link);
                                            link.click();
                                            document.body.removeChild(link);
                                        } catch (error) {
                                            console.error('Erro ao exportar:', error);
                                            alert('Erro ao exportar fluxo.');
                                        }
                                    }}
                                    className="p-2 hover:bg-white dark:hover:bg-slate-700 rounded-lg text-slate-600 dark:text-slate-400 hover:text-blue-500 transition-all"
                                    title="Exportar Fluxo (JSON)"
                                >
                                    <Share2 size={18} />
                                </button>
                                <button
                                    onClick={() => {
                                        const input = document.createElement('input');
                                        input.type = 'file';
                                        input.accept = '.json';
                                        input.onchange = (e) => {
                                            const file = e.target.files[0];
                                            if (!file) return;
                                            const reader = new FileReader();
                                            reader.onload = (event) => {
                                                try {
                                                    const json = JSON.parse(event.target.result);
                                                    if (json.nodes && json.edges) {
                                                        if (window.confirm('Deseja importar este fluxo? Isso substituirá o layout atual no editor (você deve salvar para persistir).')) {
                                                            setNodes(json.nodes);
                                                            setEdges(json.edges);
                                                            alert('Fluxo importado para o editor! Clique em Salvar para confirmar no banco de dados.');
                                                        }
                                                    } else {
                                                        alert('Formato de arquivo inválido.');
                                                    }
                                                } catch (err) {
                                                    alert('Erro ao ler arquivo JSON.');
                                                }
                                            };
                                            reader.readAsText(file);
                                        };
                                        input.click();
                                    }}
                                    className="p-2 hover:bg-white dark:hover:bg-slate-700 rounded-lg text-slate-600 dark:text-slate-400 hover:text-green-500 transition-all"
                                    title="Importar Layout (JSON)"
                                >
                                    <Plus size={18} />
                                </button>
                            </div>

                            <button
                                onClick={handleSaveFlow}
                                disabled={isSaving}
                                className={`flex items-center gap-2 px-6 py-2 text-sm font-bold rounded-xl transition-all border border-border ${isSaving ? 'bg-muted text-muted-foreground' : 'bg-emerald-600 text-white hover:bg-emerald-500'
                                    }`}
                            >
                                <Save size={16} />
                                {isSaving ? 'Salvando...' : 'Salvar Fluxo'}
                            </button>
                        </>
                    )}

                    <button
                        onClick={startSimulator}
                        className="flex items-center gap-2 px-6 py-2 text-sm font-bold bg-amber-500 text-white rounded-xl hover:bg-amber-400 transition-all border border-amber-600/60"
                    >
                        <Play size={16} />
                        Testar
                    </button>
                </div>
            </div>

            <div className="flex-1 flex flex-col overflow-hidden relative">
                {!currentFlow ? (
                    <div className="flex-1 flex items-center justify-center p-6">
                        <motion.div
                            initial={{ opacity: 0, y: 20 }}
                            animate={{ opacity: 1, y: 0 }}
                            className="max-w-md w-full p-10 bg-white dark:bg-slate-800 rounded-3xl border border-slate-200 dark:border-slate-700 shadow-2xl text-center"
                        >
                            <div className="w-20 h-20 mx-auto mb-8 text-slate-600 dark:text-slate-400 flex items-center justify-center">
                                <Bot size={64} strokeWidth={1.5} />
                            </div>
                            <h2 className="text-3xl font-black text-slate-800 dark:text-white mb-4 uppercase italic">
                                Vamos automatizar?
                            </h2>
                            <p className="text-slate-600 dark:text-slate-400 mb-10 text-sm leading-relaxed">
                                Clique abaixo para iniciar o seu primeiro fluxo de chatbot.
                            </p>
                            <button
                                onClick={handleCreateFlow}
                                className="w-full py-4 bg-blue-600 hover:bg-blue-700 text-white font-black uppercase tracking-widest text-sm rounded-2xl transition-all shadow-lg shadow-blue-500/30 hover:shadow-xl hover:-translate-y-1"
                            >
                                Criar Novo Fluxo
                            </button>
                        </motion.div>
                    </div>
                ) : (
                    <div className="flex flex-1 min-h-0 w-full flex-row overflow-hidden relative">
                        {/* Context Menu */}
                        <AnimatePresence>
                            {contextMenu.show && (
                                <motion.div
                                    initial={{ opacity: 0, scale: 0.95 }}
                                    animate={{ opacity: 1, scale: 1 }}
                                    exit={{ opacity: 0, scale: 0.95 }}
                                    style={{
                                        position: 'absolute',
                                        top: contextMenu.y,
                                        left: contextMenu.x,
                                        zIndex: 100
                                    }}
                                    className="w-56 bg-background/95 backdrop-blur-xl border border-border/50 rounded-2xl shadow-2xl p-2"
                                >
                                    {contextMenu.type === 'edge' ? (
                                        <button
                                            onClick={() => deleteEdge(contextMenu.targetId)}
                                            className="w-full flex items-center gap-3 p-2.5 hover:bg-red-500/20 rounded-xl transition-all text-left group"
                                        >
                                            <div className="p-1.5 rounded-lg text-white bg-red-500 shadow-sm group-hover:scale-110 transition-transform">
                                                <Trash2 size={14} />
                                            </div>
                                            <span className="text-sm font-bold text-red-100 group-hover:text-red-50">Excluir Linha</span>
                                        </button>
                                    ) : (
                                        <>
                                            <h3 className="text-[10px] font-black uppercase tracking-widest text-slate-500 p-2 mb-1">Adicionar Bloco</h3>
                                            {Object.entries(NODE_TYPES).map(([type, config]) => (
                                                <button
                                                    key={type}
                                                    onClick={() => {
                                                        const spawnPos = {
                                                            x: contextMenu.x - canvasOffset.x - 120,
                                                            y: contextMenu.y - canvasOffset.y - 23
                                                        };
                                                        const newNodeId = 'node_' + Date.now();
                                                        const newNode = {
                                                            id: newNodeId,
                                                            type,
                                                            position: spawnPos,
                                                            data: {
                                                                label: NODE_TYPES[type].label,
                                                                content: '',
                                                                buttons: [],
                                                                buttonText: (type === 'menu' || type === 'planos') ? 'Ver Opções' : '',
                                                                sectionTitle: type === 'menu' ? 'Selecione uma opção' : (type === 'planos' ? 'Nossos Planos' : ''),
                                                                headerText: type === 'menu' ? 'MENU' : (type === 'planos' ? 'PLANOS' : ''),
                                                                footerText: (type === 'menu' || type === 'planos') ? 'Clique para selecionar' : '',
                                                                rows: type === 'menu' ? [{ id: 'row_' + Date.now(), title: 'Opção 1', description: '', teamId: '' }] : (type === 'planos' ? availablePlanos.map(p => ({ id: 'plano_' + p.id, title: p.nome, description: `${p.velocidade_download}Mbps - R$ ${p.preco}` })) : []),
                                                                galleryImageId: type === 'galeria' ? '' : undefined,
                                                                galleryImageUrl: type === 'galeria' ? '' : undefined,
                                                                maxInvalidAttempts: type === 'menu' ? 3 : undefined,
                                                                invalidOptionMessage: type === 'menu' ? 'Opção inválida. Por favor, selecione uma opção do menu.' : undefined,
                                                                maxInvalidAttemptsMessage: type === 'menu' ? 'Não consegui identificar a opção informada. Vou seguir com o atendimento humano.' : undefined,
                                                                maxInvalidAction: type === 'menu' ? 'repeat_menu' : undefined,
                                                                maxInvalidActionTeamId: type === 'menu' ? '' : undefined,
                                                                ...(type === 'planos' ? { useDynamicPlanos: true } : {})
                                                            }
                                                        };
                                                        setNodes(prev => [...prev, newNode]);
                                                        if (contextMenu.type === 'connection' && contextMenu.targetId) {
                                                            setEdges(prev => [...prev, {
                                                                id: `edge_${Date.now()}`,
                                                                source: contextMenu.targetId,
                                                                target: newNodeId,
                                                                sourceHandle: contextMenu.sourceHandle
                                                            }]);
                                                        }
                                                        setSelectedNode(newNodeId);
                                                        setIsEditorOpen(true);
                                                        setContextMenu({ show: false, x: 0, y: 0, type: null, targetId: null });
                                                    }}
                                                    className="w-full flex items-center gap-3 p-2.5 hover:bg-white/5 rounded-xl transition-all text-left group"
                                                >
                                                    <div className={`${config.color} group-hover:scale-110 transition-transform`}>
                                                        <config.icon size={20} strokeWidth={1.5} />
                                                    </div>
                                                    <span className="text-sm font-bold text-slate-300 group-hover:text-white">{config.label}</span>
                                                </button>
                                            ))}
                                        </>
                                    )}
                                </motion.div>
                            )}
                        </AnimatePresence>

                        {/* Canvas */}
                        <div
                            ref={canvasRef}
                            onMouseDown={handleCanvasMouseDown}
                            onMouseMove={handleCanvasMouseMove}
                            onMouseUp={handleCanvasMouseUp}
                            onContextMenu={handleCanvasContextMenu}
                            className={`flex-1 min-w-0 min-h-0 overflow-hidden relative select-none bg-[linear-gradient(180deg,#2b313c_0%,#262c36_100%)] ${isPanning ? 'cursor-grabbing' : 'cursor-grab'}`}
                            onClick={() => {
                                setContextMenu({ show: false, x: 0, y: 0, type: null, targetId: null });
                            }}
                        >
                            {/* Grid Background */}
                            <div className="absolute inset-0 bg-[radial-gradient(circle,rgba(148,163,184,0.28)_1.3px,transparent_1.3px)] [background-size:30px_30px] opacity-45" />

                            <div
                                style={{
                                    transform: `translate(${canvasOffset.x}px, ${canvasOffset.y}px) scale(${canvasZoom})`,
                                    transformOrigin: '0 0'
                                }}
                                className="absolute top-0 left-0"
                            >
                                {/* SVG Layer for Edges */}
                                <svg
                                    className="absolute top-0 left-0 pointer-events-none z-10 overflow-visible"
                                    style={{ width: '1px', height: '1px' }}
                                >
                                    {edges.map((edge) => {
                                        // Usar comparação solta (==) para IDs caso haja mistura de string/int
                                        const sourceNode = nodes.find(n => n.id == edge.source);
                                        const targetNode = nodes.find(n => n.id == edge.target);

                                        if (!sourceNode || !targetNode) return null;

                                        // Side-to-side connections
                                        const x1 = sourceNode.position.x + NODE_CARD_WIDTH;
                                        const x2 = targetNode.position.x - 5;
                                        const y2 = targetNode.position.y + 40; // centro do cabeçalho (input à esquerda)

                                        // Calcular y1 baseado no sourceHandle
                                        let y1 = sourceNode.position.y + 40; // saída padrão: centro vertical do cabeçalho

                                        if (edge.sourceHandle && !sourceNode.data.isCollapsed) {
                                            if (sourceNode.data.buttons) {
                                                const bidx = sourceNode.data.buttons.findIndex(b => b.id == edge.sourceHandle);
                                                if (bidx !== -1) {
                                                    y1 = sourceNode.position.y + 53 + (bidx * 45) + 22;
                                                }
                                            }
                                            if (sourceNode.data.rows) {
                                                const ridx = sourceNode.data.rows.findIndex(r => r.id == edge.sourceHandle);
                                                if (ridx !== -1) {
                                                    const btnOffset = (sourceNode.data.buttons?.length || 0) * 45;
                                                    y1 = sourceNode.position.y + 53 + btnOffset + (ridx * 45) + 22;
                                                }
                                            }
                                        }

                                        const isRelatedToNode =
                                            (selectedNode && (edge.source == selectedNode || edge.target == selectedNode)) ||
                                            (hoveredNodeId && (edge.source == hoveredNodeId || edge.target == hoveredNodeId));
                                        const isEdgeAlert = hoveredEdgeId === edge.id || (contextMenu.type === 'edge' && contextMenu.targetId === edge.id);
                                        const edgeStroke = isEdgeAlert ? '#ef4444' : isRelatedToNode ? '#22c55e' : '#8b949e';

                                        return (
                                            <g key={edge.id}>
                                                {/* Hit area for context menu */}
                                                <path
                                                    d={`M ${x1} ${y1} C ${x1 + 100} ${y1}, ${x2 - 100} ${y2}, ${x2} ${y2}`}
                                                    fill="none"
                                                    stroke="transparent"
                                                    strokeWidth="20"
                                                    className="pointer-events-auto cursor-pointer"
                                                    onMouseEnter={() => setHoveredEdgeId(edge.id)}
                                                    onMouseLeave={() => setHoveredEdgeId(curr => (curr === edge.id ? null : curr))}
                                                    onContextMenu={(e) => {
                                                        e.preventDefault();
                                                        e.stopPropagation();
                                                        const rect = canvasRef.current.getBoundingClientRect();
                                                        setContextMenu({
                                                            show: true,
                                                            x: e.clientX - rect.left,
                                                            y: e.clientY - rect.top,
                                                            type: 'edge',
                                                            targetId: edge.id
                                                        });
                                                    }}
                                                />
                                                {/* Visible line - usando amarelo puro e maior espessura */}
                                                <path
                                                    d={`M ${x1} ${y1} C ${x1 + 100} ${y1}, ${x2 - 100} ${y2}, ${x2} ${y2}`}
                                                    fill="none"
                                                    stroke={edgeStroke}
                                                    strokeWidth="2.5"
                                                    strokeDasharray="8 6"
                                                    className="opacity-100 pointer-events-none"
                                                />
                                                <circle cx={x2} cy={y2} r="3.5" fill={edgeStroke} className="pointer-events-none" />
                                            </g>
                                        );
                                    })}

                                    {isConnecting && connectionSource && (() => {
                                        const sNode = nodes.find(n => n.id == connectionSource);
                                        if (!sNode) return null;

                                        let sy = sNode.position.y + 40;
                                        if (connectionSourceHandle && !sNode.data.isCollapsed) {
                                            if (sNode.data.buttons) {
                                                const bidx = sNode.data.buttons.findIndex(b => b.id == connectionSourceHandle);
                                                if (bidx !== -1) sy = sNode.position.y + 53 + (bidx * 45) + 22;
                                            }
                                            if (sNode.data.rows) {
                                                const ridx = sNode.data.rows.findIndex(r => r.id == connectionSourceHandle);
                                                if (ridx !== -1) {
                                                    const btnO = (sNode.data.buttons?.length || 0) * 45;
                                                    sy = sNode.position.y + 53 + btnO + (ridx * 45) + 22;
                                                }
                                            }
                                        }

                                        return (
                                            <path
                                                d={`M ${sNode.position.x + NODE_CARD_WIDTH} ${sy} 
                                                    C ${sNode.position.x + 340} ${sy},
                                                      ${mousePos.x - 50} ${mousePos.y}, ${mousePos.x} ${mousePos.y}`}
                                                fill="none"
                                                stroke="#8b949e"
                                                strokeWidth="2.5"
                                                strokeDasharray="8 6"
                                                className="opacity-100 pointer-events-none"
                                            />
                                        );
                                    })()}
                                </svg>

                                {nodes.map(node => (
                                    <Node key={node.id} node={node} />
                                ))}
                            </div>

                        </div>

                        {/* Painel de propriedades: coluna à direita (não empilha sob o card no canvas) */}
                        <AnimatePresence>
                            {selectedNode && isEditorOpen && (
                                <motion.aside
                                    initial={{ x: 28, opacity: 0 }}
                                    animate={{ x: 0, opacity: 1 }}
                                    exit={{ x: 28, opacity: 0 }}
                                    transition={{ type: 'spring', stiffness: 380, damping: 32 }}
                                    onMouseDown={(e) => e.stopPropagation()}
                                    onClick={(e) => e.stopPropagation()}
                                    className="flex w-[min(22rem,100%)] sm:w-96 shrink-0 flex-col border-l border-border bg-card z-50 h-full max-h-full shadow-[-12px_0_32px_-8px_rgba(0,0,0,0.18)] dark:shadow-[-12px_0_40px_-8px_rgba(0,0,0,0.45)]"
                                >
                                    <div className="px-4 py-3 border-b border-border flex items-center justify-between gap-2 bg-muted/25 shrink-0">
                                        <div className="min-w-0">
                                            <h3 className="font-semibold text-[9px] uppercase tracking-widest text-muted-foreground">Bloco</h3>
                                            <p className="text-sm font-bold text-foreground truncate pr-2">
                                                {nodes.find(n => n.id === selectedNode)?.data?.label || NODE_TYPES[nodes.find(n => n.id === selectedNode)?.type]?.label || 'Propriedades'}
                                            </p>
                                        </div>
                                        <button
                                            onClick={() => { setSelectedNode(null); setIsEditorOpen(false); }}
                                            className="p-2 rounded-lg text-muted-foreground hover:bg-muted hover:text-foreground transition-colors shrink-0"
                                            type="button"
                                            aria-label="Fechar editor"
                                        >
                                            <X size={18} />
                                        </button>
                                    </div>

                                    <div className="px-4 py-4 space-y-5 flex-1 min-h-0 overflow-y-auto overscroll-contain">
                                        <div>
                                            <div className="flex items-center justify-between mb-3">
                                                <label className="block text-[10px] font-semibold text-muted-foreground uppercase tracking-widest">Nome do Bloco (Apelido)</label>
                                                <div className="flex items-center gap-2">
                                                    <span className="text-[9px] font-medium text-muted-foreground bg-muted px-2 py-0.5 rounded-md border border-border">Identificação</span>
                                                </div>
                                            </div>
                                            <input
                                                type="text"
                                                value={nodes.find(n => n.id === selectedNode)?.data.label || ''}
                                                onChange={(e) => updateNodeData(selectedNode, { label: e.target.value })}
                                                placeholder="Ex: Menu Principal, Boas-vindas"
                                                className="w-full bg-background border border-border rounded-lg px-4 py-3 text-sm outline-none text-foreground font-medium placeholder:text-muted-foreground placeholder:font-normal focus:ring-2 focus:ring-primary/35 focus:border-primary"
                                            />
                                            <p className="text-[9px] text-muted-foreground mt-2 px-0.5">Este nome serve para você se organizar no canvas.</p>
                                        </div>

                                        {/* Configurações de Inatividade (Global do Fluxo - no bloco Início) */}
                                        {nodes.find(n => n.id === selectedNode)?.type === 'start' && (
                                            <div className="p-4 bg-muted/25 border border-border rounded-xl space-y-4">
                                                <div className="flex items-center gap-2">
                                                    <Clock size={16} className="text-muted-foreground shrink-0" />
                                                    <label className="text-[10px] font-semibold text-muted-foreground uppercase tracking-widest">Inatividade Global do Fluxo</label>
                                                </div>

                                                <div className="grid grid-cols-2 gap-4">
                                                    <div>
                                                        <label className="block text-[10px] font-semibold text-muted-foreground uppercase tracking-widest mb-2">Tempo (Minutos)</label>
                                                        <input
                                                            type="number"
                                                            min="1"
                                                            value={nodes.find(n => n.id === selectedNode)?.data.globalInactivityTime || ''}
                                                            onChange={(e) => updateNodeData(selectedNode, { globalInactivityTime: e.target.value })}
                                                            placeholder="Ex: 5"
                                                            className="w-full bg-background border border-border rounded-lg px-3 py-2.5 text-xs font-medium outline-none text-foreground focus:ring-2 focus:ring-primary/35 focus:border-primary"
                                                        />
                                                    </div>

                                                    <div>
                                                        <label className="block text-[10px] font-semibold text-muted-foreground uppercase tracking-widest mb-2">Ação</label>
                                                        <select
                                                            value={nodes.find(n => n.id === selectedNode)?.data.globalTimeoutAction || 'nothing'}
                                                            onChange={(e) => updateNodeData(selectedNode, { globalTimeoutAction: e.target.value })}
                                                            className="w-full bg-background border border-border rounded-lg px-3 py-2.5 text-xs font-medium outline-none text-foreground focus:ring-2 focus:ring-primary/35 focus:border-primary"
                                                        >
                                                            <option value="nothing">Nenhuma</option>
                                                            <option value="transfer">Transferir</option>
                                                            <option value="close">Encerrar</option>
                                                        </select>
                                                    </div>
                                                </div>
                                                {(nodes.find(n => n.id === selectedNode)?.data.globalTimeoutAction || 'nothing') === 'transfer' && (
                                                    <div>
                                                        <label className="block text-[10px] font-semibold text-muted-foreground uppercase tracking-widest mb-2">
                                                            Mensagem ao transferir por inatividade
                                                        </label>
                                                        <textarea
                                                            rows={3}
                                                            value={nodes.find(n => n.id === selectedNode)?.data.globalTimeoutTransferMessage || ''}
                                                            onChange={(e) => updateNodeData(selectedNode, { globalTimeoutTransferMessage: e.target.value })}
                                                            placeholder={'Ex.: Você ficou sem responder e foi encaminhado para {nome_equipe}.'}
                                                            className="w-full bg-background border border-border rounded-lg px-3 py-2.5 text-xs outline-none text-foreground focus:ring-2 focus:ring-primary/35 focus:border-primary resize-y"
                                                        />
                                                        <p className="text-[9px] text-muted-foreground mt-1.5">
                                                            Deixe em branco para usar o texto padrão. Use <span className="font-mono">{'{nome_equipe}'}</span> ou <span className="font-mono">{'{team_name}'}</span> onde quiser o nome da equipe.
                                                        </p>
                                                    </div>
                                                )}
                                                <p className="text-[9px] text-muted-foreground italic">
                                                    Vale para todo o fluxo. Para a equipe na transferência por inatividade, defina
                                                    &quot;Equipe (timeout)&quot; em cada opção do menu interativo quando fizer sentido; senão o sistema tenta inferir pelo caminho do fluxo.
                                                </p>
                                            </div>
                                        )}

                                        {/* Campos básicos específicos por tipo */}
                                        {(nodes.find(n => n.id === selectedNode)?.type === 'message' || nodes.find(n => n.id === selectedNode)?.type === 'menu') && (
                                            <div>
                                                <label className="block text-[10px] font-black text-slate-400 uppercase tracking-widest mb-3">CONTEÚDO DA MENSAGEM</label>
                                                <textarea
                                                    rows={6}
                                                    value={nodes.find(n => n.id === selectedNode)?.data.content || ''}
                                                    onChange={(e) => updateNodeData(selectedNode, { content: e.target.value })}
                                                    placeholder="Olá! Como posso te ajudar hoje?"
                                                    className="w-full bg-slate-50 dark:bg-background border-2 border-slate-100 dark:border-border rounded-2xl px-5 py-4 text-sm focus:border-primary transition-all outline-none text-slate-800 dark:text-white resize-none font-bold placeholder:font-normal"
                                                />
                                            </div>
                                        )}

                                        {nodes.find(n => n.id === selectedNode)?.type === 'message' && (
                                            <div>
                                                <div className="flex items-center justify-between mb-4">
                                                    <label className="block text-[10px] font-black text-slate-400 uppercase tracking-widest">Botões Interativos (Meta)</label>
                                                    <span className="text-[10px] font-bold text-slate-400">{(nodes.find(n => n.id === selectedNode)?.data.buttons || []).length}/3</span>
                                                </div>

                                                <div className="space-y-3">
                                                    {(nodes.find(n => n.id === selectedNode)?.data.buttons || []).map((btn, idx) => (
                                                        <div key={idx} className="flex gap-2">
                                                            <input
                                                                type="text"
                                                                value={btn.title}
                                                                placeholder="Título do botão"
                                                                maxLength={20}
                                                                onChange={(e) => {
                                                                    const currentButtons = [...(nodes.find(n => n.id === selectedNode)?.data.buttons || [])];
                                                                    currentButtons[idx].title = e.target.value;
                                                                    updateNodeData(selectedNode, { buttons: currentButtons });
                                                                }}
                                                                className="flex-1 bg-white dark:bg-background border border-slate-200 dark:border-border rounded-xl px-4 py-3 text-xs font-bold outline-none focus:border-primary"
                                                            />
                                                            <button
                                                                onClick={() => {
                                                                    const currentButtons = (nodes.find(n => n.id === selectedNode)?.data.buttons || []).filter((_, i) => i !== idx);
                                                                    updateNodeData(selectedNode, { buttons: currentButtons });
                                                                }}
                                                                className="p-3 text-red-500 hover:bg-red-50 dark:hover:bg-red-900/20 rounded-xl transition-colors"
                                                            >
                                                                <Trash2 size={16} />
                                                            </button>
                                                        </div>
                                                    ))}

                                                    {(nodes.find(n => n.id === selectedNode)?.data.buttons || []).length < 3 && (
                                                        <button
                                                            onClick={() => {
                                                                const currentButtons = [...(nodes.find(n => n.id === selectedNode)?.data.buttons || [])];
                                                                currentButtons.push({ id: 'btn_' + Date.now(), title: 'Novo Botão' });
                                                                updateNodeData(selectedNode, { buttons: currentButtons });
                                                            }}
                                                            className="w-full py-3 border-2 border-dashed border-slate-200 dark:border-border rounded-2xl text-slate-400 hover:text-primary hover:border-primary transition-all font-bold text-xs flex items-center justify-center gap-2"
                                                        >
                                                            <Plus size={16} />
                                                            Adicionar Botão
                                                        </button>
                                                    )}
                                                </div>
                                            </div>
                                        )}

                                        {nodes.find(n => n.id === selectedNode)?.type === 'menu' && (
                                            <div className="space-y-6">
                                                <div className="p-4 bg-muted/20 border border-border rounded-xl">
                                                    <p className="text-[10px] text-muted-foreground font-semibold uppercase tracking-widest mb-1.5">Dica — Lista no WhatsApp</p>
                                                    <p className="text-xs text-muted-foreground leading-relaxed">
                                                        Este bloco cria uma lista interativa. Ideal para menus com mais de 3 opções (limite de botões).
                                                    </p>
                                                </div>

                                                <div>
                                                    <label className="block text-[10px] font-black text-slate-400 uppercase tracking-widest mb-3">Cabeçalho (Header)</label>
                                                    <input
                                                        type="text"
                                                        value={nodes.find(n => n.id === selectedNode)?.data.headerText || ''}
                                                        onChange={(e) => updateNodeData(selectedNode, { headerText: e.target.value })}
                                                        placeholder="Ex: MENU"
                                                        maxLength={60}
                                                        className="w-full bg-white dark:bg-background border border-slate-200 dark:border-border rounded-xl px-4 py-3 text-xs font-bold outline-none focus:border-primary"
                                                    />
                                                </div>

                                                <div>
                                                    <label className="block text-[10px] font-black text-slate-400 uppercase tracking-widest mb-3">Conteúdo da Mensagem (Body)</label>
                                                    <textarea
                                                        rows={4}
                                                        value={nodes.find(n => n.id === selectedNode)?.data.content || ''}
                                                        onChange={(e) => updateNodeData(selectedNode, { content: e.target.value })}
                                                        placeholder="Escolha a opção desejada:"
                                                        className="w-full bg-slate-50 dark:bg-background border-2 border-slate-100 dark:border-border rounded-2xl px-5 py-4 text-sm focus:border-primary transition-all outline-none text-slate-800 dark:text-white resize-none font-bold placeholder:font-normal"
                                                    />
                                                </div>

                                                <div>
                                                    <label className="block text-[10px] font-black text-slate-400 uppercase tracking-widest mb-3">Rodapé (Footer)</label>
                                                    <input
                                                        type="text"
                                                        value={nodes.find(n => n.id === selectedNode)?.data.footerText || ''}
                                                        onChange={(e) => updateNodeData(selectedNode, { footerText: e.target.value })}
                                                        placeholder="Ex: Clique na lista abaixo..."
                                                        maxLength={60}
                                                        className="w-full bg-white dark:bg-background border border-slate-200 dark:border-border rounded-xl px-4 py-3 text-xs font-bold outline-none focus:border-primary"
                                                    />
                                                </div>

                                                <div className="pt-4 border-t border-slate-100 dark:border-slate-800">
                                                    <label className="block text-[10px] font-black text-slate-400 uppercase tracking-widest mb-3">Texto do Botão da Lista</label>
                                                    <input
                                                        type="text"
                                                        value={nodes.find(n => n.id === selectedNode)?.data.buttonText || ''}
                                                        onChange={(e) => updateNodeData(selectedNode, { buttonText: e.target.value })}
                                                        placeholder="Ex: Abrir Menu"
                                                        maxLength={20}
                                                        className="w-full bg-white dark:bg-background border border-slate-200 dark:border-border rounded-xl px-4 py-3 text-xs font-bold outline-none focus:border-primary"
                                                    />
                                                </div>

                                                <div>
                                                    <label className="block text-[10px] font-black text-slate-400 uppercase tracking-widest mb-3">Título da Seção</label>
                                                    <input
                                                        type="text"
                                                        value={nodes.find(n => n.id === selectedNode)?.data.sectionTitle || ''}
                                                        onChange={(e) => updateNodeData(selectedNode, { sectionTitle: e.target.value })}
                                                        placeholder="Ex: Selecione uma opção"
                                                        maxLength={24}
                                                        className="w-full bg-white dark:bg-background border border-slate-200 dark:border-border rounded-xl px-4 py-3 text-xs font-bold outline-none focus:border-primary"
                                                    />
                                                </div>

                                                <div>
                                                    <div className="flex items-center justify-between mb-4">
                                                        <label className="block text-[10px] font-black text-slate-400 uppercase tracking-widest">Opções do Menu</label>
                                                        <span className="text-[10px] font-bold text-slate-400">{(nodes.find(n => n.id === selectedNode)?.data.rows || []).length}/10</span>
                                                    </div>

                                                    <div className="space-y-4">
                                                        {(nodes.find(n => n.id === selectedNode)?.data.rows || []).map((row, idx) => (
                                                            <div key={idx} className="p-4 bg-muted/20 border border-border rounded-xl space-y-3">
                                                                <div className="flex justify-between items-center gap-2">
                                                                    <input
                                                                        type="text"
                                                                        value={row.title}
                                                                        placeholder="Título da opção"
                                                                        maxLength={24}
                                                                        onChange={(e) => {
                                                                            const currentRows = [...(nodes.find(n => n.id === selectedNode)?.data.rows || [])];
                                                                            currentRows[idx].title = e.target.value;
                                                                            updateNodeData(selectedNode, { rows: currentRows });
                                                                        }}
                                                                        className="flex-1 bg-white dark:bg-background border border-slate-200 dark:border-border rounded-xl px-4 py-2 text-xs font-bold outline-none focus:border-primary"
                                                                    />
                                                                    <button
                                                                        onClick={() => {
                                                                            const currentRows = (nodes.find(n => n.id === selectedNode)?.data.rows || []).filter((_, i) => i !== idx);
                                                                            updateNodeData(selectedNode, { rows: currentRows });
                                                                        }}
                                                                        className="p-2 text-red-500 hover:bg-red-50 dark:hover:bg-red-900/20 rounded-lg transition-colors"
                                                                    >
                                                                        <Trash2 size={14} />
                                                                    </button>
                                                                </div>
                                                                <input
                                                                    type="text"
                                                                    value={row.description || ''}
                                                                    placeholder="Descrição (opcional)"
                                                                    maxLength={72}
                                                                    onChange={(e) => {
                                                                        const currentRows = [...(nodes.find(n => n.id === selectedNode)?.data.rows || [])];
                                                                        currentRows[idx].description = e.target.value;
                                                                        updateNodeData(selectedNode, { rows: currentRows });
                                                                    }}
                                                                    className="w-full bg-white dark:bg-background border border-slate-200 dark:border-border rounded-xl px-4 py-2 text-[10px] font-medium outline-none focus:border-primary"
                                                                />
                                                                <div>
                                                                    <label className="block text-[9px] font-bold text-slate-500 uppercase tracking-wider mb-1">Equipe (timeout / roteamento)</label>
                                                                    <select
                                                                        value={row.teamId != null && row.teamId !== '' ? String(row.teamId) : ''}
                                                                        onChange={(e) => {
                                                                            const currentRows = [...(nodes.find(n => n.id === selectedNode)?.data.rows || [])];
                                                                            currentRows[idx].teamId = e.target.value || '';
                                                                            updateNodeData(selectedNode, { rows: currentRows });
                                                                        }}
                                                                        className="w-full bg-white dark:bg-background border border-slate-200 dark:border-border rounded-xl px-3 py-2 text-[10px] font-bold outline-none focus:border-primary"
                                                                    >
                                                                        <option value="">Inferir pelo fluxo (padrão)</option>
                                                                        {availableTeams.filter(team => team?.is_active !== false).map(team => (
                                                                            <option key={team.id} value={team.id}>{team.name}</option>
                                                                        ))}
                                                                    </select>
                                                                    <p className="text-[8px] text-slate-500 mt-1">Usada na transferência por inatividade global e como prioridade sobre inferência automática.</p>
                                                                </div>
                                                            </div>
                                                        ))}

                                                        {(nodes.find(n => n.id === selectedNode)?.data.rows || []).length < 10 && (
                                                            <button
                                                                onClick={() => {
                                                                    const currentRows = [...(nodes.find(n => n.id === selectedNode)?.data.rows || [])];
                                                                    currentRows.push({
                                                                        id: 'row_' + Date.now(),
                                                                        title: 'Nova Opção',
                                                                        description: '',
                                                                        teamId: ''
                                                                    });
                                                                    updateNodeData(selectedNode, { rows: currentRows });
                                                                }}
                                                                className="w-full py-3 border-2 border-dashed border-slate-200 dark:border-border rounded-2xl text-slate-400 hover:text-primary hover:border-primary transition-all font-bold text-xs flex items-center justify-center gap-2"
                                                            >
                                                                <Plus size={16} />
                                                                Adicionar Opção
                                                            </button>
                                                        )}
                                                    </div>
                                                </div>

                                                <div className="pt-4 border-t border-slate-100 dark:border-slate-800 space-y-4">
                                                    <div className="p-4 bg-muted/20 border border-border rounded-xl space-y-3">
                                                        <label className="block text-[10px] font-black text-slate-400 uppercase tracking-widest">Tentativas para opção inválida</label>
                                                        <input
                                                            type="number"
                                                            min={1}
                                                            max={10}
                                                            value={nodes.find(n => n.id === selectedNode)?.data.maxInvalidAttempts ?? 3}
                                                            onChange={(e) => {
                                                                const parsed = Number(e.target.value);
                                                                const safeValue = Number.isFinite(parsed) ? Math.min(10, Math.max(1, parsed)) : 3;
                                                                updateNodeData(selectedNode, { maxInvalidAttempts: safeValue });
                                                            }}
                                                            className="w-full bg-white dark:bg-background border border-slate-200 dark:border-border rounded-xl px-4 py-2 text-xs font-bold outline-none focus:border-primary"
                                                        />
                                                        <p className="text-[9px] text-slate-500">Após atingir esse limite, o sistema executa a ação configurada abaixo.</p>
                                                    </div>

                                                    <div>
                                                        <label className="block text-[10px] font-black text-slate-400 uppercase tracking-widest mb-2">Mensagem para opção inválida</label>
                                                        <input
                                                            type="text"
                                                            value={nodes.find(n => n.id === selectedNode)?.data.invalidOptionMessage || ''}
                                                            onChange={(e) => updateNodeData(selectedNode, { invalidOptionMessage: e.target.value })}
                                                            placeholder="Ex: Opção inválida. Escolha um item da lista."
                                                            maxLength={180}
                                                            className="w-full bg-white dark:bg-background border border-slate-200 dark:border-border rounded-xl px-4 py-3 text-xs font-medium outline-none focus:border-primary"
                                                        />
                                                    </div>

                                                    <div>
                                                        <label className="block text-[10px] font-black text-slate-400 uppercase tracking-widest mb-2">Mensagem ao atingir o limite</label>
                                                        <input
                                                            type="text"
                                                            value={nodes.find(n => n.id === selectedNode)?.data.maxInvalidAttemptsMessage || ''}
                                                            onChange={(e) => updateNodeData(selectedNode, { maxInvalidAttemptsMessage: e.target.value })}
                                                            placeholder="Ex: Vou te direcionar para atendimento humano."
                                                            maxLength={180}
                                                            className="w-full bg-white dark:bg-background border border-slate-200 dark:border-border rounded-xl px-4 py-3 text-xs font-medium outline-none focus:border-primary"
                                                        />
                                                    </div>

                                                    <div className="p-4 bg-muted/20 border border-border rounded-xl space-y-3">
                                                        <label className="block text-[10px] font-black text-slate-400 uppercase tracking-widest">Ação ao atingir o limite</label>
                                                        <select
                                                            value={
                                                                (() => {
                                                                    const action = nodes.find(n => n.id === selectedNode)?.data.maxInvalidAction;
                                                                    return action === 'transfer_choice' ? 'repeat_menu' : (action || 'repeat_menu');
                                                                })()
                                                            }
                                                            onChange={(e) => updateNodeData(selectedNode, { maxInvalidAction: e.target.value === 'transfer_choice' ? 'repeat_menu' : e.target.value })}
                                                            className="w-full bg-white dark:bg-background border border-slate-200 dark:border-border rounded-xl px-4 py-3 text-xs font-bold outline-none focus:border-primary"
                                                        >
                                                            <option value="repeat_menu">Reenviar o menu</option>
                                                            <option value="transfer_direct">Transferir para equipe específica</option>
                                                        </select>

                                                        {nodes.find(n => n.id === selectedNode)?.data.maxInvalidAction === 'transfer_direct' && (
                                                            <select
                                                                value={nodes.find(n => n.id === selectedNode)?.data.maxInvalidActionTeamId || ''}
                                                                onChange={(e) => updateNodeData(selectedNode, { maxInvalidActionTeamId: e.target.value })}
                                                                className="w-full bg-white dark:bg-background border border-slate-200 dark:border-border rounded-xl px-4 py-3 text-xs font-bold outline-none focus:border-primary"
                                                            >
                                                                <option value="">Selecione a equipe</option>
                                                                {availableTeams.filter(team => team?.is_active !== false).map(team => (
                                                                    <option key={team.id} value={team.id}>{team.name}</option>
                                                                ))}
                                                            </select>
                                                        )}
                                                    </div>

                                                    <div className="flex items-center justify-between p-4 bg-muted/20 border border-border rounded-xl">
                                                        <div className="flex flex-col gap-1">
                                                            <span className="text-[10px] font-black text-slate-400 uppercase tracking-widest">Encerrar Atendimento</span>
                                                            <span className="text-[9px] text-slate-500 font-medium">Fecha a conversa automaticamente após o envio</span>
                                                        </div>
                                                        <button
                                                            onClick={() => updateNodeData(selectedNode, { autoClose: !(nodes.find(n => n.id === selectedNode)?.data.autoClose || false) })}
                                                            className={`w-12 h-6 rounded-full transition-all relative ${nodes.find(n => n.id === selectedNode)?.data.autoClose ? 'bg-primary' : 'bg-slate-300 dark:bg-slate-700'}`}
                                                        >
                                                            <div className={`absolute top-1 w-4 h-4 bg-white rounded-full transition-all ${nodes.find(n => n.id === selectedNode)?.data.autoClose ? 'left-7' : 'left-1'}`} />
                                                        </button>
                                                    </div>

                                                    {nodes.find(n => n.id === selectedNode)?.data.autoClose && (
                                                        <div className="animate-in fade-in slide-in-from-top-2 duration-300">
                                                            <label className="block text-[10px] font-black text-slate-400 uppercase tracking-widest mb-2">Mensagem de Encerramento (Opcional)</label>
                                                            <textarea
                                                                value={nodes.find(n => n.id === selectedNode)?.data.closingMessage || ''}
                                                                onChange={(e) => updateNodeData(selectedNode, { closingMessage: e.target.value })}
                                                                placeholder="Ex: Obrigado! Atendimento finalizado por aqui."
                                                                rows={2}
                                                                className="w-full bg-muted/20 dark:bg-background border border-slate-200 dark:border-border rounded-2xl px-4 py-3 text-xs font-bold outline-none focus:border-primary transition-all resize-none"
                                                            />
                                                        </div>
                                                    )}
                                                </div>
                                            </div>
                                        )}

                                        {nodes.find(n => n.id === selectedNode)?.type === 'galeria' && (
                                            <div className="space-y-5">
                                                <div className="p-4 bg-muted/20 border border-border rounded-xl">
                                                    <p className="text-[10px] text-muted-foreground font-semibold uppercase tracking-widest mb-1.5">Bloco Galeria</p>
                                                    <p className="text-xs text-muted-foreground leading-relaxed">
                                                        Selecione uma imagem da galeria do provedor para enviar ao cliente e seguir para o próximo bloco.
                                                    </p>
                                                </div>

                                                <div>
                                                    <label className="block text-[10px] font-black text-slate-400 uppercase tracking-widest mb-2">Imagem da galeria</label>
                                                    <select
                                                        value={nodes.find(n => n.id === selectedNode)?.data.galleryImageId || ''}
                                                        onChange={(e) => {
                                                            const imageId = e.target.value;
                                                            const selected = galleryImages.find(img => String(img.id) === String(imageId));
                                                            updateNodeData(selectedNode, {
                                                                galleryImageId: imageId,
                                                                galleryImageUrl: selected?.image_url || ''
                                                            });
                                                        }}
                                                        className="w-full bg-white dark:bg-background border border-slate-200 dark:border-border rounded-xl px-4 py-3 text-xs font-bold outline-none focus:border-primary"
                                                    >
                                                        <option value="">Selecione uma imagem</option>
                                                        {galleryImages.map(img => (
                                                            <option key={img.id} value={img.id}>{img.nome}</option>
                                                        ))}
                                                    </select>
                                                </div>

                                                <div>
                                                    <label className="block text-[10px] font-black text-slate-400 uppercase tracking-widest mb-2">Legenda (opcional)</label>
                                                    <textarea
                                                        rows={3}
                                                        value={nodes.find(n => n.id === selectedNode)?.data.content || ''}
                                                        onChange={(e) => updateNodeData(selectedNode, { content: e.target.value })}
                                                        placeholder="Ex: Confira nosso cartão de planos."
                                                        className="w-full bg-muted/20 dark:bg-background border border-slate-200 dark:border-border rounded-2xl px-4 py-3 text-xs font-medium outline-none focus:border-primary resize-none"
                                                    />
                                                </div>

                                                {nodes.find(n => n.id === selectedNode)?.data.galleryImageUrl && (
                                                    <div className="rounded-xl overflow-hidden border border-border bg-card">
                                                        <img
                                                            src={nodes.find(n => n.id === selectedNode)?.data.galleryImageUrl}
                                                            alt="Prévia da galeria"
                                                            className="w-full h-44 object-cover"
                                                        />
                                                    </div>
                                                )}
                                            </div>
                                        )}

                                        {nodes.find(n => n.id === selectedNode)?.type === 'sgp' && (() => {
                                            const sgpNode = nodes.find(n => n.id === selectedNode);
                                            const sgpAction = sgpNode?.data.sgpAction || 'consultar_cliente';
                                            const SGP_ENDPOINTS = [
                                                { value: 'consultar_cliente', label: 'Consultar Cliente (CPF/CNPJ)', input: 'cpf', desc: 'Retorna dados e contratos do cliente. Variáveis: {{nome}}, {{contratos}}' },
                                                { value: 'verifica_acesso', label: 'Verificar Acesso (Contrato)', input: 'contrato', desc: 'Verifica status da conexão do contrato. Variável: {{status_acesso}}' },
                                                { value: 'listar_contratos', label: 'Listar Contratos (Cliente ID)', input: 'cliente_id', desc: 'Lista todos os contratos do cliente. Variável: {{contratos}}' },
                                                { value: 'listar_titulos', label: 'Enviar 2 Via Fatura', input: 'cpf', desc: 'Lista faturas seguindo a nova priorização. Variável: {{titulos}}' },
                                                { value: 'liberar_por_confianca', label: 'Liberar por Confiança (Contrato)', input: 'contrato', desc: 'Faz liberação por promessa de pagamento. Variável: {{sucesso}}' },
                                                { value: 'criar_chamado', label: 'Criar Chamado Técnico (Contrato)', input: 'contrato', desc: 'Abre chamado no SGP. Variável: {{protocolo}}' },
                                                { value: 'listar_manutencoes', label: 'Listar Manutenções (CPF)', input: 'cpf', desc: 'Lista manutenções na área do cliente. Variável: {{manutencoes}}' },
                                            ];
                                            const selectedEndpoint = SGP_ENDPOINTS.find(e => e.value === sgpAction) || SGP_ENDPOINTS[0];
                                            return (
                                                <div className="space-y-5">
                                                    <div className="p-4 bg-purple-50 dark:bg-purple-900/10 border border-purple-100 dark:border-purple-800/30 rounded-2xl">
                                                        <p className="text-[10px] text-purple-700 dark:text-purple-400 font-bold uppercase tracking-widest mb-1">Bloco SGP</p>
                                                        <p className="text-[10px] text-purple-700/70 dark:text-purple-400/70 leading-relaxed">
                                                            Este bloco consulta a API do seu SGP e salva o resultado no contexto do fluxo, disponível nos próximos blocos.
                                                        </p>
                                                    </div>

                                                    <div>
                                                        <label className="block text-[10px] font-black text-slate-400 uppercase tracking-widest mb-3">Endpoint / Ação</label>
                                                        <select
                                                            value={sgpAction}
                                                            onChange={(e) => updateNodeData(selectedNode, { sgpAction: e.target.value })}
                                                            className="w-full bg-slate-50 dark:bg-slate-900 border-2 border-slate-200 dark:border-slate-700 rounded-2xl px-4 py-3 text-xs font-bold outline-none focus:border-purple-500 transition-all text-slate-800 dark:text-white"
                                                        >
                                                            {SGP_ENDPOINTS.map(ep => (
                                                                <option key={ep.value} value={ep.value}>{ep.label}</option>
                                                            ))}
                                                        </select>
                                                    </div>

                                                    <div>
                                                        <label className="block text-[10px] font-black text-slate-400 uppercase tracking-widest mb-2">
                                                            Variável de Entrada: <span className="text-purple-500 font-black">&#123;&#123;{selectedEndpoint.input}&#125;&#125;</span>
                                                        </label>
                                                        <input
                                                            type="text"
                                                            value={sgpNode?.data.inputVar || selectedEndpoint.input}
                                                            onChange={(e) => updateNodeData(selectedNode, { inputVar: e.target.value })}
                                                            placeholder={`Nome da variável (ex: ${selectedEndpoint.input})`}
                                                            className="w-full bg-slate-50 dark:bg-slate-900 border-2 border-slate-200 dark:border-slate-700 rounded-2xl px-4 py-3 text-xs font-bold outline-none focus:border-purple-500 transition-all"
                                                        />
                                                        <p className="text-[9px] text-slate-400 mt-1 px-1 italic">Nome da variável de contexto que será usada como entrada.</p>
                                                    </div>

                                                    <div>
                                                        <label className="block text-[10px] font-black text-slate-400 uppercase tracking-widest mb-2">Mensagem de Erro (opcional)</label>
                                                        <input
                                                            type="text"
                                                            value={sgpNode?.data.errorMessage || ''}
                                                            onChange={(e) => updateNodeData(selectedNode, { errorMessage: e.target.value })}
                                                            placeholder="Ex: Cliente não encontrado no sistema."
                                                            className="w-full bg-slate-50 dark:bg-slate-900 border-2 border-slate-200 dark:border-slate-700 rounded-2xl px-4 py-3 text-xs font-bold outline-none focus:border-purple-500 transition-all"
                                                        />
                                                    </div>

                                                    {sgpAction === 'criar_chamado' && (
                                                        <>
                                                            <div>
                                                                <label className="block text-[10px] font-black text-slate-400 uppercase tracking-widest mb-2">Tipo de ocorrência (ID no SGP) <span className="text-red-500">*</span></label>
                                                                <input
                                                                    type="number"
                                                                    min={1}
                                                                    step={1}
                                                                    value={
                                                                        sgpNode?.data.ocorrenciatipo !== undefined && sgpNode?.data.ocorrenciatipo !== ''
                                                                            ? String(sgpNode.data.ocorrenciatipo)
                                                                            : ''
                                                                    }
                                                                    onChange={(e) => updateNodeData(selectedNode, { ocorrenciatipo: e.target.value })}
                                                                    placeholder="Ex: 5 (código cadastrado no seu SGP)"
                                                                    className="w-full bg-slate-50 dark:bg-slate-900 border-2 border-slate-200 dark:border-slate-700 rounded-2xl px-4 py-3 text-xs font-bold outline-none focus:border-purple-500 transition-all"
                                                                />
                                                                <p className="text-[9px] text-slate-400 mt-1 px-1 italic">Obrigatório. Informe o código do tipo de ocorrência no seu SGP (sem valor padrão no sistema).</p>
                                                            </div>
                                                            <div>
                                                                <label className="block text-[10px] font-black text-slate-400 uppercase tracking-widest mb-2">Descrição do Chamado (Conteúdo)</label>
                                                                <textarea
                                                                    rows={3}
                                                                    value={sgpNode?.data.content || ''}
                                                                    onChange={(e) => updateNodeData(selectedNode, { content: e.target.value })}
                                                                    placeholder="Ex: Cliente solicita suporte técnico via WhatsApp."
                                                                    className="w-full bg-slate-50 dark:bg-slate-900 border-2 border-slate-200 dark:border-slate-700 rounded-2xl px-4 py-3 text-xs font-bold outline-none focus:border-purple-500 transition-all resize-none"
                                                                />
                                                                <p className="text-[9px] text-slate-400 mt-1 px-1 italic">Texto que será enviado como descrição do chamado no SGP.</p>
                                                            </div>
                                                        </>
                                                    )}

                                                    {sgpAction === 'listar_titulos' && (
                                                        <div>
                                                            <label className="block text-[10px] font-black text-slate-400 uppercase tracking-widest mb-2 text-purple-500">Método de Pagamento</label>
                                                            <select
                                                                value={sgpNode?.data.paymentMethod || 'ambos'}
                                                                onChange={(e) => updateNodeData(selectedNode, { paymentMethod: e.target.value })}
                                                                className="w-full bg-slate-50 dark:bg-slate-900 border-2 border-slate-200 dark:border-slate-700 rounded-2xl px-4 py-3 text-xs font-bold outline-none focus:border-purple-500 transition-all text-slate-800 dark:text-white"
                                                            >
                                                                <option value="ambos">Ambos (PIX e Boleto)</option>
                                                                <option value="pix">Apenas PIX</option>
                                                                <option value="boleto">Apenas Boleto</option>
                                                            </select>
                                                            <p className="text-[9px] text-slate-400 mt-1 px-1 italic text-purple-400/80">Escolha qual método será enviado para o cliente.</p>
                                                        </div>
                                                    )}

                                                    {(sgpAction === 'listar_titulos' || sgpAction === 'criar_chamado' || sgpAction === 'liberar_por_confianca') && (
                                                        <div className="space-y-4">
                                                            <div>
                                                                <label className="block text-[10px] font-black text-slate-400 uppercase tracking-widest mb-2 text-purple-500">Mensagem de Sucesso</label>
                                                                <textarea
                                                                    value={sgpNode?.data.successMessage || ''}
                                                                    onChange={(e) => updateNodeData(selectedNode, { successMessage: e.target.value })}
                                                                    placeholder={
                                                                        sgpAction === 'criar_chamado' ? "Ex: Chamado aberto! Seu protocolo é {protocolo}." :
                                                                            sgpAction === 'liberar_por_confianca' ? "Ex: Liberado por {liberado_dias} dias! Protocolo: {protocolo}" :
                                                                                "Ex: Segue abaixo as opções para pagamento da sua fatura."
                                                                    }
                                                                    rows={3}
                                                                    className="w-full bg-slate-50 dark:bg-slate-900 border-2 border-slate-200 dark:border-slate-700 rounded-2xl px-4 py-3 text-xs font-bold outline-none focus:border-purple-500 transition-all resize-none"
                                                                />
                                                                <p className="text-[9px] text-slate-400 mt-1 px-1 italic">
                                                                    {sgpAction === 'criar_chamado' ? "Será enviada após a criação. Use {protocolo}." :
                                                                        sgpAction === 'liberar_por_confianca' ? "Será enviada após a liberação. Use {liberado_dias} e {protocolo}." :
                                                                            "Será enviada após o envio do pagamento."
                                                                    }
                                                                </p>
                                                            </div>

                                                            {sgpAction === 'liberar_por_confianca' && (
                                                                <div className="animate-in fade-in slide-in-from-top-2 duration-300">
                                                                    <label className="block text-[10px] font-black text-red-500 uppercase tracking-widest mb-2">Mensagem de Limite Atingido</label>
                                                                    <textarea
                                                                        value={sgpNode?.data.limitReachedMessage || ''}
                                                                        onChange={(e) => updateNodeData(selectedNode, { limitReachedMessage: e.target.value })}
                                                                        placeholder="Ex: Ops! Você já utilizou sua liberação este mês. Por favor, realize o pagamento para normalizar seu sinal."
                                                                        rows={2}
                                                                        className="w-full bg-slate-50 dark:bg-slate-900 border-2 border-red-200 dark:border-red-900/30 rounded-2xl px-4 py-3 text-xs font-bold outline-none focus:border-red-500 transition-all resize-none text-slate-800 dark:text-white"
                                                                    />
                                                                    <p className="text-[9px] text-red-400 mt-1 px-1 italic">Será enviada caso o SGP retorne que o limite de liberações foi atingido.</p>
                                                                </div>
                                                            )}

                                                            {sgpAction !== 'criar_chamado' && (
                                                                <>
                                                                    <div className="flex items-center justify-between p-4 bg-slate-50 dark:bg-slate-900/50 border-2 border-slate-200 dark:border-slate-800 rounded-2xl">
                                                                        <div className="flex flex-col gap-1">
                                                                            <span className="text-[10px] font-black text-slate-400 uppercase tracking-widest">Encerrar Atendimento</span>
                                                                            <span className="text-[9px] text-slate-500 font-medium">Fecha a conversa automaticamente após o envio</span>
                                                                        </div>
                                                                        <button
                                                                            onClick={() => updateNodeData(selectedNode, { autoClose: !(sgpNode?.data.autoClose || false) })}
                                                                            className={`w-12 h-6 rounded-full transition-all relative ${sgpNode?.data.autoClose ? 'bg-purple-600' : 'bg-slate-300 dark:bg-slate-700'}`}
                                                                        >
                                                                            <div className={`absolute top-1 w-4 h-4 bg-white rounded-full transition-all ${sgpNode?.data.autoClose ? 'left-7' : 'left-1'}`} />
                                                                        </button>
                                                                    </div>

                                                                    {sgpNode?.data.autoClose && (
                                                                        <div className="animate-in fade-in slide-in-from-top-2 duration-300">
                                                                            <label className="block text-[10px] font-black text-purple-500 uppercase tracking-widest mb-2">Mensagem de Encerramento (Opcional)</label>
                                                                            <textarea
                                                                                value={sgpNode?.data.closingMessage || ''}
                                                                                onChange={(e) => updateNodeData(selectedNode, { closingMessage: e.target.value })}
                                                                                placeholder="Ex: Atendimento finalizado. Qualquer dúvida estamos à disposição!"
                                                                                rows={2}
                                                                                className="w-full bg-slate-50 dark:bg-slate-900 border-2 border-slate-200 dark:border-slate-700 rounded-2xl px-4 py-3 text-xs font-bold outline-none focus:border-purple-500 transition-all resize-none"
                                                                            />
                                                                        </div>
                                                                    )}
                                                                </>
                                                            )}
                                                        </div>
                                                    )}

                                                    <div className="p-3 bg-slate-100 dark:bg-slate-900 rounded-xl border border-slate-200 dark:border-slate-700">
                                                        <p className="text-[9px] font-black text-slate-500 uppercase tracking-widest mb-1">Resultado disponível:</p>
                                                        <p className="text-[9px] text-purple-500 font-bold">{selectedEndpoint.desc}</p>
                                                    </div>
                                                </div>
                                            );
                                        })()}

                                        {nodes.find(n => n.id === selectedNode)?.type === 'planos' && (
                                            <div className="space-y-6">
                                                <div className="p-4 bg-cyan-50 dark:bg-cyan-900/10 border border-cyan-100 dark:border-cyan-800/30 rounded-2xl">
                                                    <p className="text-[10px] text-cyan-600 dark:text-cyan-400 font-bold uppercase tracking-widest mb-1">Bloco Planos</p>
                                                    <p className="text-[10px] text-cyan-700/70 dark:text-cyan-400/70 leading-relaxed">
                                                        Este bloco envia os planos de internet cadastrados como uma <b>Lista Interativa do WhatsApp</b>. O cliente poderá selecionar um plano.
                                                    </p>
                                                </div>

                                                <div>
                                                    <label className="block text-[10px] font-black text-slate-400 uppercase tracking-widest mb-3">Cabeçalho (Header)</label>
                                                    <input
                                                        type="text"
                                                        value={nodes.find(n => n.id === selectedNode)?.data.headerText || ''}
                                                        onChange={(e) => updateNodeData(selectedNode, { headerText: e.target.value })}
                                                        placeholder="Ex: PLANOS"
                                                        maxLength={60}
                                                        className="w-full bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-700 rounded-xl px-4 py-3 text-xs font-bold outline-none focus:border-cyan-500"
                                                    />
                                                </div>

                                                <div>
                                                    <label className="block text-[10px] font-black text-slate-400 uppercase tracking-widest mb-3">Mensagem (Body)</label>
                                                    <textarea
                                                        rows={4}
                                                        value={nodes.find(n => n.id === selectedNode)?.data.content || ''}
                                                        onChange={(e) => updateNodeData(selectedNode, { content: e.target.value })}
                                                        placeholder="Confira nossos planos de internet:"
                                                        className="w-full bg-slate-50 dark:bg-slate-900 border-2 border-slate-100 dark:border-slate-700 rounded-2xl px-5 py-4 text-sm focus:border-cyan-500 transition-all outline-none text-slate-800 dark:text-white resize-none font-bold placeholder:font-normal"
                                                    />
                                                </div>

                                                <div>
                                                    <label className="block text-[10px] font-black text-slate-400 uppercase tracking-widest mb-3">Rodapé (Footer)</label>
                                                    <input
                                                        type="text"
                                                        value={nodes.find(n => n.id === selectedNode)?.data.footerText || ''}
                                                        onChange={(e) => updateNodeData(selectedNode, { footerText: e.target.value })}
                                                        placeholder="Ex: Selecione o plano desejado"
                                                        maxLength={60}
                                                        className="w-full bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-700 rounded-xl px-4 py-3 text-xs font-bold outline-none focus:border-cyan-500"
                                                    />
                                                </div>

                                                <div className="pt-4 border-t border-slate-100 dark:border-slate-800">
                                                    <label className="block text-[10px] font-black text-slate-400 uppercase tracking-widest mb-3">Texto do Botão da Lista</label>
                                                    <input
                                                        type="text"
                                                        value={nodes.find(n => n.id === selectedNode)?.data.buttonText || ''}
                                                        onChange={(e) => updateNodeData(selectedNode, { buttonText: e.target.value })}
                                                        placeholder="Ex: Ver Planos"
                                                        maxLength={20}
                                                        className="w-full bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-700 rounded-xl px-4 py-3 text-xs font-bold outline-none focus:border-cyan-500"
                                                    />
                                                </div>

                                                <div>
                                                    <label className="block text-[10px] font-black text-slate-400 uppercase tracking-widest mb-3">Título da Seção</label>
                                                    <input
                                                        type="text"
                                                        value={nodes.find(n => n.id === selectedNode)?.data.sectionTitle || ''}
                                                        onChange={(e) => updateNodeData(selectedNode, { sectionTitle: e.target.value })}
                                                        placeholder="Ex: Nossos Planos"
                                                        maxLength={24}
                                                        className="w-full bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-700 rounded-xl px-4 py-3 text-xs font-bold outline-none focus:border-cyan-500"
                                                    />
                                                </div>

                                                <div>
                                                    <div className="flex items-center justify-between mb-4">
                                                        <label className="block text-[10px] font-black text-slate-400 uppercase tracking-widest">Planos (itens da lista)</label>
                                                        <span className="text-[10px] font-bold text-slate-400">{(nodes.find(n => n.id === selectedNode)?.data.rows || []).length}/10</span>
                                                    </div>

                                                    <button
                                                        onClick={() => {
                                                            const planosRows = availablePlanos.map(p => ({
                                                                id: 'plano_' + p.id,
                                                                title: p.nome,
                                                                description: `${p.velocidade_download}Mbps - R$ ${p.preco}`
                                                            }));
                                                            updateNodeData(selectedNode, { rows: planosRows });
                                                        }}
                                                        className="w-full mb-4 py-3 border-2 border-dashed border-cyan-300 dark:border-cyan-700 rounded-2xl text-cyan-500 hover:text-cyan-400 hover:border-cyan-400 transition-all font-bold text-xs flex items-center justify-center gap-2"
                                                    >
                                                        <Wifi size={16} />
                                                        Sincronizar Planos Cadastrados
                                                    </button>

                                                    <div className="space-y-4">
                                                        {(nodes.find(n => n.id === selectedNode)?.data.rows || []).map((row, idx) => (
                                                            <div key={idx} className="p-4 bg-slate-50 dark:bg-slate-900/50 border border-slate-200 dark:border-slate-700 rounded-2xl space-y-3">
                                                                <div className="flex justify-between items-center gap-2">
                                                                    <input
                                                                        type="text"
                                                                        value={row.title}
                                                                        placeholder="Nome do plano"
                                                                        maxLength={24}
                                                                        onChange={(e) => {
                                                                            const currentRows = [...(nodes.find(n => n.id === selectedNode)?.data.rows || [])];
                                                                            currentRows[idx].title = e.target.value;
                                                                            updateNodeData(selectedNode, { rows: currentRows });
                                                                        }}
                                                                        className="flex-1 bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-700 rounded-xl px-4 py-2 text-xs font-bold outline-none focus:border-cyan-500"
                                                                    />
                                                                    <button
                                                                        onClick={() => {
                                                                            const currentRows = (nodes.find(n => n.id === selectedNode)?.data.rows || []).filter((_, i) => i !== idx);
                                                                            updateNodeData(selectedNode, { rows: currentRows });
                                                                        }}
                                                                        className="p-2 text-red-500 hover:bg-red-50 dark:hover:bg-red-900/20 rounded-lg transition-colors"
                                                                    >
                                                                        <Trash2 size={14} />
                                                                    </button>
                                                                </div>
                                                                <input
                                                                    type="text"
                                                                    value={row.description || ''}
                                                                    placeholder="Ex: 100Mbps - R$ 99,90"
                                                                    maxLength={72}
                                                                    onChange={(e) => {
                                                                        const currentRows = [...(nodes.find(n => n.id === selectedNode)?.data.rows || [])];
                                                                        currentRows[idx].description = e.target.value;
                                                                        updateNodeData(selectedNode, { rows: currentRows });
                                                                    }}
                                                                    className="w-full bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-700 rounded-xl px-4 py-2 text-[10px] font-medium outline-none focus:border-cyan-500"
                                                                />
                                                            </div>
                                                        ))}
                                                    </div>
                                                </div>
                                            </div>
                                        )}

                                        {nodes.find(n => n.id === selectedNode)?.type === 'transfer' && (
                                            <div className="space-y-6">
                                                <div className="p-4 bg-orange-50 dark:bg-orange-900/10 border border-orange-100 dark:border-orange-800/30 rounded-2xl text-xs text-orange-700 dark:text-orange-400">
                                                    <p className="font-bold uppercase tracking-widest mb-1">Transferência</p>
                                                    <p>Este bloco encerra o atendimento automático e transfere para um humano.</p>
                                                </div>

                                                <div>
                                                    <label className="block text-[10px] font-black text-slate-400 uppercase tracking-widest mb-3">Modo de Transferência</label>
                                                    <select
                                                        value={nodes.find(n => n.id === selectedNode)?.data.transferMode || 'choice'}
                                                        onChange={(e) => updateNodeData(selectedNode, { transferMode: e.target.value })}
                                                        className="w-full bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-700 rounded-xl px-4 py-3 text-xs font-bold outline-none focus:border-blue-500"
                                                    >
                                                        <option value="choice">Cliente Escolhe a Equipe</option>
                                                        <option value="direct">Transferir Direto p/ Equipe</option>
                                                    </select>
                                                </div>

                                                {nodes.find(n => n.id === selectedNode)?.data.transferMode === 'direct' && (
                                                    <div>
                                                        <label className="block text-[10px] font-black text-slate-400 uppercase tracking-widest mb-3">Equipe de Destino</label>
                                                        <select
                                                            value={nodes.find(n => n.id === selectedNode)?.data.teamId || ''}
                                                            onChange={(e) => updateNodeData(selectedNode, { teamId: e.target.value })}
                                                            className="w-full bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-700 rounded-xl px-4 py-3 text-xs font-bold outline-none focus:border-blue-500"
                                                        >
                                                            <option value="">Selecione uma equipe...</option>
                                                            {availableTeams.map(team => (
                                                                <option key={team.id} value={team.id}>{team.name}</option>
                                                            ))}
                                                        </select>
                                                    </div>
                                                )}

                                                <div>
                                                    <label className="block text-[10px] font-black text-slate-400 uppercase tracking-widest mb-3">Mensagem antes de transferir</label>
                                                    <textarea
                                                        rows={3}
                                                        value={nodes.find(n => n.id === selectedNode)?.data.content || ''}
                                                        onChange={(e) => updateNodeData(selectedNode, { content: e.target.value })}
                                                        placeholder="Ex: Aguarde um momento, estamos te transferindo..."
                                                        className="w-full bg-slate-50 dark:bg-background border-2 border-slate-100 dark:border-border rounded-2xl px-5 py-4 text-sm focus:border-primary transition-all outline-none text-slate-800 dark:text-white resize-none font-bold"
                                                    />
                                                </div>
                                            </div>
                                        )}

                                        {nodes.find(n => n.id === selectedNode)?.type === 'close' && (
                                            <div className="space-y-6">
                                                <div className="p-4 bg-red-50 dark:bg-red-900/10 border border-red-100 dark:border-red-800/30 rounded-2xl text-xs text-red-700 dark:text-red-400">
                                                    <p className="font-bold uppercase tracking-widest mb-1">Encerrar Atendimento</p>
                                                    <p>Este bloco finaliza o atendimento automático e move a conversa para o status de encerrada.</p>
                                                </div>

                                                <div>
                                                    <label className="block text-[10px] font-black text-slate-400 uppercase tracking-widest mb-3">Mensagem de Despedida</label>
                                                    <textarea
                                                        rows={3}
                                                        value={nodes.find(n => n.id === selectedNode)?.data.content || ''}
                                                        onChange={(e) => updateNodeData(selectedNode, { content: e.target.value })}
                                                        placeholder="Ex: Obrigado pelo contato! Atendimento encerrado."
                                                        className="w-full bg-slate-50 dark:bg-slate-900 border-2 border-slate-100 dark:border-slate-700 rounded-2xl px-5 py-4 text-sm focus:border-red-500 transition-all outline-none text-slate-800 dark:text-white resize-none font-bold"
                                                    />
                                                </div>
                                            </div>
                                        )}

                                        <div className="p-4 bg-muted/20 border border-border rounded-xl">
                                            <div className="flex items-center gap-2 mb-2 text-muted-foreground">
                                                <Zap size={16} />
                                                <span className="text-[10px] font-semibold uppercase tracking-widest">Motor de Fluxo</span>
                                            </div>
                                            <p className="text-xs text-muted-foreground leading-relaxed">
                                                Este bloco será executado automaticamente quando o usuário chegar nesta etapa do fluxo.
                                            </p>
                                        </div>
                                    </div>

                                    <div className="px-4 py-3 border-t border-border bg-muted/10 shrink-0">
                                        <button
                                            type="button"
                                            onClick={() => deleteNode(selectedNode)}
                                            className="w-full flex items-center justify-center gap-2 py-2.5 rounded-lg border border-border bg-background text-destructive hover:bg-destructive/10 text-[11px] font-semibold uppercase tracking-widest transition-colors"
                                        >
                                            <Trash2 size={15} />
                                            Remover bloco
                                        </button>
                                    </div>
                                </motion.aside>
                            )
                            }
                        </AnimatePresence>
                    </div>
                )}
            </div>

            {/* Simulator Modal */}
            <AnimatePresence>
                {showSimulator && (
                    <motion.div
                        initial={{ opacity: 0 }}
                        animate={{ opacity: 1 }}
                        exit={{ opacity: 0 }}
                        className="fixed inset-0 bg-slate-900/60 backdrop-blur-md z-[100] flex items-center justify-center p-4"
                    >
                        <motion.div
                            initial={{ scale: 0.9, y: 20 }}
                            animate={{ scale: 1, y: 0 }}
                            className="bg-white dark:bg-background w-full max-w-lg h-[600px] rounded-[2.5rem] shadow-2xl flex flex-col overflow-hidden border border-slate-200 dark:border-border"
                        >
                            {/* Simulator Header */}
                            <div className="p-6 bg-slate-50 dark:bg-background/50 border-b border-slate-100 dark:border-border flex items-center justify-between">
                                <div className="flex items-center gap-3">
                                    <div className="w-10 h-10 bg-emerald-100 dark:bg-emerald-900/30 rounded-full flex items-center justify-center text-emerald-600">
                                        <Bot size={20} />
                                    </div>
                                    <div>
                                        <h3 className="font-black text-xs uppercase tracking-widest text-slate-800 dark:text-white">Simulador</h3>
                                        <p className="text-[10px] text-emerald-500 font-bold">Fluxo Ativo</p>
                                    </div>
                                </div>
                                <button onClick={() => setShowSimulator(false)} className="p-2 hover:bg-slate-200 dark:hover:bg-slate-700 rounded-xl transition-colors">
                                    <X size={20} className="text-slate-500" />
                                </button>
                            </div>

                            {/* Chat Messages */}
                            <div className="flex-1 overflow-y-auto p-6 space-y-4 bg-slate-50/30 dark:bg-background/30">
                                {simMessages.map((msg, i) => (
                                    <motion.div
                                        key={i}
                                        initial={{ opacity: 0, x: msg.role === 'bot' ? -10 : 10 }}
                                        animate={{ opacity: 1, x: 0 }}
                                        className={`flex ${msg.role === 'bot' ? 'justify-start' : 'justify-center'}`}
                                    >
                                        {msg.role === 'system' ? (
                                            <div className="px-4 py-1.5 bg-slate-200 dark:bg-slate-700 rounded-full text-[10px] font-black text-slate-500 uppercase tracking-widest">
                                                {msg.content}
                                            </div>
                                        ) : (
                                            <div className="max-w-[80%] space-y-3">
                                                <div className="p-4 bg-white dark:bg-slate-700 rounded-2xl shadow-sm border border-slate-100 dark:border-slate-600 text-sm text-slate-700 dark:text-slate-200 font-medium">
                                                    {msg.content}
                                                </div>
                                                {msg.menu && (
                                                    <div className="flex flex-col gap-2">
                                                        <div className="bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-600 rounded-xl overflow-hidden shadow-sm">
                                                            {msg.menu.headerText && (
                                                                <div className="p-3 border-b border-slate-100 dark:border-slate-700 bg-slate-50/50 dark:bg-slate-900/30 text-[10px] font-black uppercase tracking-widest text-slate-400">
                                                                    {msg.menu.headerText}
                                                                </div>
                                                            )}
                                                            <div className="p-4 text-sm text-slate-700 dark:text-slate-200 font-medium leading-relaxed">
                                                                {msg.content}
                                                            </div>
                                                            {msg.menu.footerText && (
                                                                <div className="px-4 pb-3 text-[10px] text-slate-400 font-medium italic">
                                                                    {msg.menu.footerText}
                                                                </div>
                                                            )}
                                                            <div className="p-2.5 bg-emerald-50/50 dark:bg-emerald-900/10 border-t border-slate-100 dark:border-slate-800">
                                                                <div className="flex items-center justify-center gap-2 py-1.5 bg-white dark:bg-slate-800 border border-emerald-100 dark:border-emerald-900/50 rounded-lg shadow-sm">
                                                                    <List size={14} className="text-emerald-500" />
                                                                    <span className="text-[11px] font-bold text-emerald-600 dark:text-emerald-400">
                                                                        {msg.menu.buttonText || 'Ver Opções'}
                                                                    </span>
                                                                </div>
                                                            </div>
                                                        </div>

                                                        {/* Preview of rows in simulator */}
                                                        <div className="bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-600 rounded-xl overflow-hidden shadow-md mt-1 animate-in slide-in-from-top-2">
                                                            <div className="p-3 bg-slate-50 dark:bg-slate-900/50 border-b border-slate-100 dark:border-slate-700 text-[10px] font-bold text-slate-500 uppercase tracking-tight">
                                                                {msg.menu.sectionTitle || 'Opções'}
                                                            </div>
                                                            {msg.menu.rows.map(row => (
                                                                <button
                                                                    key={row.id}
                                                                    onClick={() => {
                                                                        setSimMessages(prev => [...prev, { role: 'user', content: row.title }]);
                                                                        processNextStep(currentNodeId, row.id);
                                                                    }}
                                                                    className="w-full p-3 hover:bg-blue-50 dark:hover:bg-blue-900/20 text-left border-b border-slate-100 dark:border-slate-700 last:border-0 transition-colors"
                                                                >
                                                                    <p className="text-xs font-bold text-blue-600 dark:text-blue-400">{row.title}</p>
                                                                    {row.description && <p className="text-[10px] text-slate-400 mt-0.5">{row.description}</p>}
                                                                </button>
                                                            ))}
                                                        </div>
                                                    </div>
                                                )}

                                                {msg.buttons && msg.buttons.length > 0 && (
                                                    <div className="flex flex-col gap-2">
                                                        {msg.buttons.map(btn => (
                                                            <button
                                                                key={btn.id}
                                                                onClick={() => {
                                                                    setSimMessages(prev => [...prev, { role: 'user', content: btn.title }]);
                                                                    processNextStep(currentNodeId, btn.id);
                                                                }}
                                                                className="w-full py-3 bg-white dark:bg-slate-800 hover:bg-blue-50 dark:hover:bg-blue-900/20 border border-slate-200 dark:border-slate-600 rounded-xl text-xs font-black text-blue-600 uppercase tracking-widest transition-all shadow-sm"
                                                            >
                                                                {btn.title}
                                                            </button>
                                                        ))}
                                                    </div>
                                                )}
                                            </div>
                                        )}
                                    </motion.div>
                                ))}
                            </div>

                            {/* Simulator Footer */}
                            <div className="p-6 bg-white dark:bg-slate-800 border-t border-slate-100 dark:border-slate-700">
                                <div className="flex gap-2">
                                    <button
                                        onClick={startSimulator}
                                        className="flex-1 py-4 bg-slate-100 dark:bg-slate-900 text-slate-600 dark:text-slate-400 font-black text-xs uppercase tracking-widest rounded-2xl hover:bg-slate-200 transition-all"
                                    >
                                        Reiniciar
                                    </button>
                                    <button className="flex-1 py-4 bg-blue-600 text-white font-black text-xs uppercase tracking-widest rounded-2xl opacity-50 cursor-not-allowed">
                                        Responder
                                    </button>
                                </div>
                            </div>
                        </motion.div>
                    </motion.div>
                )}
            </AnimatePresence>
        </div >
    );
};

export default ChatbotBuilder;
