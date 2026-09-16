import React, { useState, useEffect } from 'react';
import { Send, Users, Eye, EyeOff, CheckCircle, AlertCircle, Building, MessageCircle } from 'lucide-react';
import axios from 'axios';

export default function SuperadminMensagem() {
  const [provedores, setProvedores] = useState([]);
  const [selectedProvedores, setSelectedProvedores] = useState([]);
  const [mensagem, setMensagem] = useState('');
  const [assunto, setAssunto] = useState('');
  const [imagemUrl, setImagemUrl] = useState('');
  const [hotspots, setHotspots] = useState([]);
  const [ctaLinks, setCtaLinks] = useState([]);
  const [loading, setLoading] = useState(false);
  const [mensagensEnviadas, setMensagensEnviadas] = useState([]);
  const [loadingMensagens, setLoadingMensagens] = useState(false);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');
  const [visivelParaAgentes, setVisivelParaAgentes] = useState(true);

  // Buscar provedores disponíveis
  const fetchProvedores = async () => {
    try {
      const token = localStorage.getItem('token');
      const response = await axios.get('/api/provedores/', {
        headers: { Authorization: `Token ${token}` }
      });
      setProvedores(response.data.results || response.data);
    } catch (err) {
      console.error('Erro ao buscar provedores:', err);
      setError('Erro ao carregar provedores');
    }
  };

  // Buscar mensagens enviadas
  const fetchMensagensEnviadas = async () => {
    try {
      setLoadingMensagens(true);
      const token = localStorage.getItem('token');
      const response = await axios.get('/api/mensagens-sistema/', {
        headers: { Authorization: `Token ${token}` }
      });
      setMensagensEnviadas(response.data.results || response.data);
    } catch (err) {
      console.error('Erro ao buscar mensagens:', err);
      setMensagensEnviadas([]);
    } finally {
      setLoadingMensagens(false);
    }
  };

  useEffect(() => {
    fetchProvedores();
    fetchMensagensEnviadas();
    // Atualiza confirmações de leitura periodicamente
    const interval = setInterval(fetchMensagensEnviadas, 30000);
    return () => clearInterval(interval);
  }, []);

  const formatDateTime = (raw) => {
    if (!raw) return null;
    const d = new Date(raw);
    if (Number.isNaN(d.getTime())) return null;
    return d.toLocaleString('pt-BR', {
      day: '2-digit',
      month: '2-digit',
      year: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    });
  };

  // Selecionar/deselecionar provedor
  const toggleProvedor = (provedorId) => {
    setSelectedProvedores(prev => 
      prev.includes(provedorId) 
        ? prev.filter(id => id !== provedorId)
        : [...prev, provedorId]
    );
  };

  // Selecionar todos os provedores
  const selectAllProvedores = () => {
    setSelectedProvedores(provedores.map(p => p.id));
  };

  // Deselecionar todos os provedores
  const deselectAllProvedores = () => {
    setSelectedProvedores([]);
  };

  const handleEnviarMensagem = async (e) => {
    e.preventDefault();
    
    if (!assunto.trim()) {
      setError('O assunto é obrigatório');
      return;
    }

    const imagem = imagemUrl.trim();
    if (!mensagem.trim() && !imagem) {
      setError('Informe a mensagem e/ou a URL da imagem');
      return;
    }
    
    if (selectedProvedores.length === 0) {
      setError('Selecione pelo menos um provedor');
      return;
    }

    const cleanHotspots = hotspots
      .map((h) => ({
        x: Number(h.x) || 0,
        y: Number(h.y) || 0,
        w: Number(h.w) || 10,
        h: Number(h.h) || 10,
        url: String(h.url || '').trim(),
        label: String(h.label || '').trim() || 'Abrir link',
      }))
      .filter((h) => h.url);

    const cleanCtas = ctaLinks
      .map((c) => ({
        label: String(c.label || '').trim() || 'Abrir link',
        url: String(c.url || '').trim(),
      }))
      .filter((c) => c.url);

    try {
      setLoading(true);
      setError('');
      
      const token = localStorage.getItem('token');
      const response = await axios.post('/api/mensagens-sistema/', {
        assunto: assunto.trim(),
        mensagem: mensagem.trim(),
        imagem_url: imagem,
        hotspots: cleanHotspots,
        cta_links: cleanCtas,
        provedores: selectedProvedores,
        tipo: 'notificacao',
        visivel_para_agentes: visivelParaAgentes
      }, {
        headers: { Authorization: `Token ${token}` }
      });

      const entregas = response.data?.entregas || [];
      const falhas = entregas.filter((e) => e && e.ok === false);
      if (falhas.length > 0) {
        const detalhe = falhas
          .map((f) => `#${f.provedor_id}: ${f.error || 'falha na entrega'}`)
          .join(' · ');
        setError(`Mensagem registrada, mas não chegou a ${falhas.length} provedor(es): ${detalhe}`);
        setSuccess('');
      } else {
        setSuccess('Mensagem enviada com sucesso!');
        setError('');
        setAssunto('');
        setMensagem('');
        setImagemUrl('');
        setHotspots([]);
        setCtaLinks([]);
        setSelectedProvedores([]);
        setVisivelParaAgentes(true);
      }
      
      fetchMensagensEnviadas();
      
      setTimeout(() => setSuccess(''), 3000);
      
    } catch (err) {
      console.error('Erro ao enviar mensagem:', err);
      setError('Erro ao enviar mensagem. Tente novamente.');
    } finally {
      setLoading(false);
    }
  };

  // Marcar mensagem como visualizada
  const handleMarcarVisualizada = async (mensagemId) => {
    try {
      const token = localStorage.getItem('token');
      await axios.patch(`/api/mensagens-sistema/${mensagemId}/marcar-visualizada/`, {}, {
        headers: { Authorization: `Token ${token}` }
      });
      
      // Atualizar lista de mensagens
      fetchMensagensEnviadas();
    } catch (err) {
      console.error('Erro ao marcar como visualizada:', err);
    }
  };

  return (
    <div className="flex-1 p-6 bg-background overflow-y-auto">
      {/* Header */}
      <div className="mb-8">
        <h1 className="text-3xl font-bold text-foreground mb-2 flex items-center gap-3">
          <MessageCircle className="w-8 h-8 text-primary" />
          Sistema de Mensagens
        </h1>
        <p className="text-muted-foreground">
          Envie mensagens e notificações para os administradores dos provedores
        </p>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
        {/* Formulário de Envio */}
        <div className="bg-card rounded-xl shadow-lg border border-border overflow-hidden">
          <div className="bg-gradient-to-r from-blue-900/20 to-cyan-900/20 px-6 py-4 border-b border-border">
            <h3 className="text-lg font-semibold text-foreground flex items-center gap-2">
              <Send className="w-5 h-5 text-blue-400" />
              Enviar Nova Mensagem
            </h3>
          </div>
          
          <form onSubmit={handleEnviarMensagem} className="p-6 space-y-6">
            {/* Seleção de Provedores */}
            <div>
              <label className="block font-medium mb-3 text-foreground">
                Selecionar Provedores Destinatários
              </label>
              
              <div className="flex gap-2 mb-3">
                <button
                  type="button"
                  onClick={selectAllProvedores}
                  className="px-3 py-1 text-xs bg-gradient-to-r from-blue-500 to-blue-400 hover:from-blue-600 hover:to-blue-500 text-white rounded shadow-lg hover:shadow-xl transition-all duration-200"
                >
                  Selecionar Todos
                </button>
                <button
                  type="button"
                  onClick={deselectAllProvedores}
                  className="px-3 py-1 text-xs bg-gray-600 text-white rounded hover:bg-gray-700 transition-colors"
                >
                  Desmarcar Todos
                </button>
              </div>
              
              <div className="max-h-48 overflow-y-auto border border-border rounded-lg p-3 bg-background">
                {provedores.map(provedor => (
                  <label key={provedor.id} className="flex items-center gap-3 p-2 hover:bg-muted rounded cursor-pointer">
                    <input
                      type="checkbox"
                      checked={selectedProvedores.includes(provedor.id)}
                      onChange={() => toggleProvedor(provedor.id)}
                      className="rounded text-primary focus:ring-primary"
                    />
                    <div className="flex items-center gap-2">
                      <Building className="w-4 h-4 text-muted-foreground" />
                      <span className="text-sm font-medium">{provedor.nome}</span>
                      <span className="text-xs text-muted-foreground">
                        ({provedor.users_count || 0} usuários)
                      </span>
                    </div>
                  </label>
                ))}
              </div>
              
              <p className="text-xs text-muted-foreground mt-2">
                {selectedProvedores.length} provedor(es) selecionado(s)
              </p>
            </div>

            {/* Assunto */}
            <div>
              <label className="block font-medium mb-2 text-foreground">
                Assunto *
              </label>
              <input
                type="text"
                value={assunto}
                onChange={(e) => setAssunto(e.target.value)}
                placeholder="Digite o assunto da mensagem..."
                className="w-full px-4 py-3 rounded-lg bg-background border border-border text-foreground focus:ring-2 focus:ring-primary/20 focus:border-primary transition-colors"
                required
              />
            </div>

            {/* Mensagem */}
            <div>
              <label className="block font-medium mb-2 text-foreground">
                Mensagem {imagemUrl.trim() ? '(opcional se houver imagem)' : '*'}
              </label>
              <textarea
                value={mensagem}
                onChange={(e) => setMensagem(e.target.value)}
                placeholder="Digite sua mensagem aqui..."
                rows={5}
                className="w-full px-4 py-3 rounded-lg bg-background border border-border text-foreground focus:ring-2 focus:ring-primary/20 focus:border-primary transition-colors resize-none"
                required={!imagemUrl.trim()}
              />
            </div>

            {/* Imagem do aviso */}
            <div className="space-y-3 rounded-xl border border-border bg-muted/10 p-4">
              <div>
                <label className="block font-medium mb-2 text-foreground">
                  URL da imagem (banner)
                </label>
                <input
                  type="url"
                  value={imagemUrl}
                  onChange={(e) => setImagemUrl(e.target.value)}
                  placeholder="https://cdn.exemplo.com/aviso.png"
                  className="w-full px-4 py-3 rounded-lg bg-background border border-border text-foreground focus:ring-2 focus:ring-primary/20 focus:border-primary transition-colors"
                />
                <p className="text-xs text-muted-foreground mt-1">
                  Use uma URL pública da imagem. Depois marque áreas clicáveis (ex.: botão Play Store).
                </p>
              </div>

              {imagemUrl.trim() && (
                <div className="rounded-lg border border-border overflow-hidden bg-background">
                  <img src={imagemUrl.trim()} alt="Prévia" className="w-full h-auto max-h-64 object-contain" />
                </div>
              )}

              <div>
                <div className="flex items-center justify-between mb-2">
                  <label className="font-medium text-foreground text-sm">
                    Áreas clicáveis na imagem (% da largura/altura)
                  </label>
                  <button
                    type="button"
                    onClick={() =>
                      setHotspots((prev) => [
                        ...prev,
                        { x: 10, y: 70, w: 35, h: 12, url: '', label: 'Play Store' },
                      ])
                    }
                    className="text-xs px-2 py-1 rounded bg-primary text-primary-foreground"
                  >
                    + Área
                  </button>
                </div>
                {hotspots.length === 0 ? (
                  <p className="text-xs text-muted-foreground">
                    Ex.: Play Store em x=10 y=75 w=38 h=14 — App Store ao lado.
                  </p>
                ) : (
                  <div className="space-y-2">
                    {hotspots.map((h, idx) => (
                      <div key={idx} className="grid grid-cols-12 gap-1.5 items-center">
                        {['x', 'y', 'w', 'h'].map((key) => (
                          <input
                            key={key}
                            type="number"
                            min={0}
                            max={100}
                            value={h[key]}
                            onChange={(e) => {
                              const v = e.target.value;
                              setHotspots((prev) =>
                                prev.map((item, i) => (i === idx ? { ...item, [key]: v } : item))
                              );
                            }}
                            className="col-span-1 px-1 py-1.5 text-xs rounded border border-border bg-background"
                            title={key.toUpperCase()}
                            placeholder={key}
                          />
                        ))}
                        <input
                          type="text"
                          value={h.label}
                          onChange={(e) => {
                            const v = e.target.value;
                            setHotspots((prev) =>
                              prev.map((item, i) => (i === idx ? { ...item, label: v } : item))
                            );
                          }}
                          placeholder="Label"
                          className="col-span-3 px-2 py-1.5 text-xs rounded border border-border bg-background"
                        />
                        <input
                          type="url"
                          value={h.url}
                          onChange={(e) => {
                            const v = e.target.value;
                            setHotspots((prev) =>
                              prev.map((item, i) => (i === idx ? { ...item, url: v } : item))
                            );
                          }}
                          placeholder="https://play.google.com/..."
                          className="col-span-4 px-2 py-1.5 text-xs rounded border border-border bg-background"
                        />
                        <button
                          type="button"
                          onClick={() => setHotspots((prev) => prev.filter((_, i) => i !== idx))}
                          className="col-span-1 text-xs text-red-400 hover:text-red-300"
                        >
                          ✕
                        </button>
                      </div>
                    ))}
                  </div>
                )}
              </div>

              <div>
                <div className="flex items-center justify-between mb-2">
                  <label className="font-medium text-foreground text-sm">
                    Botões abaixo da imagem (opcional)
                  </label>
                  <button
                    type="button"
                    onClick={() =>
                      setCtaLinks((prev) => [...prev, { label: 'Baixar app', url: '' }])
                    }
                    className="text-xs px-2 py-1 rounded bg-primary text-primary-foreground"
                  >
                    + Botão
                  </button>
                </div>
                {ctaLinks.map((c, idx) => (
                  <div key={idx} className="flex gap-2 mb-2">
                    <input
                      type="text"
                      value={c.label}
                      onChange={(e) => {
                        const v = e.target.value;
                        setCtaLinks((prev) =>
                          prev.map((item, i) => (i === idx ? { ...item, label: v } : item))
                        );
                      }}
                      placeholder="Label"
                      className="w-1/3 px-2 py-1.5 text-xs rounded border border-border bg-background"
                    />
                    <input
                      type="url"
                      value={c.url}
                      onChange={(e) => {
                        const v = e.target.value;
                        setCtaLinks((prev) =>
                          prev.map((item, i) => (i === idx ? { ...item, url: v } : item))
                        );
                      }}
                      placeholder="https://..."
                      className="flex-1 px-2 py-1.5 text-xs rounded border border-border bg-background"
                    />
                    <button
                      type="button"
                      onClick={() => setCtaLinks((prev) => prev.filter((_, i) => i !== idx))}
                      className="text-xs text-red-400"
                    >
                      ✕
                    </button>
                  </div>
                ))}
              </div>
            </div>

            {/* Opções de Visibilidade */}
            <div className="bg-muted/10 p-4 rounded-xl border border-border/50 space-y-3">
              <label className="flex items-center gap-3 cursor-pointer group">
                <div className="relative inline-flex items-center cursor-pointer">
                  <input
                    type="checkbox"
                    checked={visivelParaAgentes}
                    onChange={(e) => setVisivelParaAgentes(e.target.checked)}
                    className="sr-only peer"
                  />
                  <div className="w-11 h-6 bg-gray-600 peer-focus:outline-none rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-gray-300 after:border after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-blue-600 shadow-inner"></div>
                </div>
                <div className="flex flex-col">
                  <span className="text-sm font-semibold text-foreground group-hover:text-primary transition-colors">
                    Exibir para Atendentes
                  </span>
                  <span className="text-xs text-muted-foreground">
                    Se desmarcado, apenas os administradores do provedor receberão este aviso.
                  </span>
                </div>
              </label>
            </div>

            {/* Botão Enviar */}
            <button
              type="submit"
              disabled={loading || selectedProvedores.length === 0}
              className="w-full bg-primary hover:bg-primary/90 disabled:bg-muted disabled:cursor-not-allowed text-white py-3 px-6 rounded-lg font-medium transition-colors shadow-lg flex items-center justify-center gap-2"
            >
              {loading ? (
                <>
                  <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-white"></div>
                  Enviando...
                </>
              ) : (
                <>
                  <Send className="w-4 h-4" />
                  Enviar Mensagem
                </>
              )}
            </button>

            {/* Mensagens de erro/sucesso */}
            {error && (
              <div className="bg-red-900/20 border border-red-500/30 rounded-lg p-3">
                <p className="text-red-300 text-sm flex items-center gap-2">
                  <AlertCircle className="w-4 h-4" />
                  {error}
                </p>
              </div>
            )}
            
            {success && (
              <div className="bg-green-900/20 border border-green-500/30 rounded-lg p-3">
                <p className="text-green-300 text-sm flex items-center gap-2">
                  <CheckCircle className="w-4 h-4" />
                  {success}
                </p>
              </div>
            )}
          </form>
        </div>

        {/* Lista de Mensagens Enviadas */}
        <div className="bg-card rounded-xl shadow-lg border border-border overflow-hidden">
          <div className="bg-gradient-to-r from-green-900/20 to-emerald-900/20 px-6 py-4 border-b border-border">
            <h3 className="text-lg font-semibold text-foreground flex items-center gap-2">
              <MessageCircle className="w-5 h-5 text-green-400" />
              Mensagens Enviadas
            </h3>
          </div>
          
          <div className="p-6">
            {loadingMensagens ? (
              <div className="flex items-center justify-center h-32">
                <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary"></div>
              </div>
            ) : mensagensEnviadas.length === 0 ? (
              <div className="text-center text-muted-foreground py-8">
                <MessageCircle className="w-12 h-12 mx-auto mb-3 opacity-50" />
                <p>Nenhuma mensagem enviada ainda</p>
              </div>
            ) : (
              <div className="space-y-4 max-h-96 overflow-y-auto">
                {mensagensEnviadas.map(mensagem => (
                  <div key={mensagem.id} className="border border-border rounded-lg p-4 bg-background/50">
                    <div className="flex items-start justify-between mb-3">
                      <h4 className="font-semibold text-foreground">{mensagem.assunto}</h4>
                      <span className="text-xs text-muted-foreground">
                        {new Date(mensagem.created_at).toLocaleDateString('pt-BR')}
                      </span>
                    </div>
                    
                    <p className="text-sm text-muted-foreground mb-3 line-clamp-2">
                      {mensagem.mensagem}
                    </p>
                    
                    <div className="space-y-3">
                      {/* Estatísticas */}
                      <div className="flex items-center justify-between text-xs">
                        <span className="text-muted-foreground">
                          {mensagem.provedores_count || 0} provedor(es)
                        </span>
                        <span className="text-muted-foreground flex items-center gap-1">
                          {mensagem.visivel_para_agentes ? (
                            <><Users className="w-3 h-3" /> Todos</>
                          ) : (
                            <><Building className="w-3 h-3" /> Apenas Admins</>
                          )}
                        </span>
                        <span className="text-muted-foreground">
                          {mensagem.visualizacoes_count || 0} visualizada(s)
                        </span>
                      </div>
                      
                      {/* Lista de provedores com status e data/hora da leitura */}
                      <div className="space-y-2">
                        <p className="text-xs font-medium text-foreground">Provedores:</p>
                        <div className="grid grid-cols-1 gap-2">
                          {(mensagem.provedores_detalhados || []).length === 0 ? (
                            <span className="text-xs text-muted-foreground">Nenhum destinatário listado</span>
                          ) : (
                            mensagem.provedores_detalhados.map(provedor => {
                              const lidoEm = formatDateTime(provedor.visualized_at);
                              return (
                                <div
                                  key={provedor.id}
                                  className="flex items-center justify-between gap-2 text-xs border border-border/40 rounded-md px-2 py-1.5 bg-background/40"
                                >
                                  <span className="text-foreground font-medium truncate">
                                    {provedor.nome}
                                  </span>
                                  {provedor.visualizado ? (
                                    <span
                                      className="text-green-500 flex items-center gap-1 shrink-0"
                                      title={provedor.user_name ? `Lido por ${provedor.user_name}` : 'Lido'}
                                    >
                                      <Eye className="w-3 h-3" />
                                      <span>{lidoEm || 'Confirmado'}</span>
                                    </span>
                                  ) : (
                                    <span className="text-orange-500 flex items-center gap-1 shrink-0">
                                      <EyeOff className="w-3 h-3" />
                                      Pendente
                                    </span>
                                  )}
                                </div>
                              );
                            })
                          )}
                        </div>
                      </div>
                      
                      {/* Detalhes das visualizações (usuário + data/hora, como último acesso) */}
                      {mensagem.visualizacoes_detalhadas?.length > 0 && (
                        <div className="space-y-2">
                          <p className="text-xs font-medium text-foreground">Confirmado por:</p>
                          <div className="space-y-1">
                            {mensagem.visualizacoes_detalhadas.map((visualizacao, index) => (
                              <div
                                key={index}
                                className="text-xs flex items-center gap-1.5 border border-green-500/20 rounded-md px-2 py-1.5 bg-green-950/20"
                              >
                                <CheckCircle className="w-3 h-3 text-green-500 shrink-0" />
                                <span className="font-semibold text-green-400">{visualizacao.username}</span>
                                <span className="text-muted-foreground truncate">
                                  ({visualizacao.provedor_nome || 'Sem Provedor'})
                                </span>
                                <span className="text-muted-foreground ml-auto shrink-0 tabular-nums">
                                  {formatDateTime(visualizacao.timestamp) || 'Data não disponível'}
                                </span>
                              </div>
                            ))}
                          </div>
                        </div>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
} 