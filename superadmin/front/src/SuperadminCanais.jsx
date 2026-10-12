import React, { useState, useEffect, useCallback } from 'react';
import { Search, Plus, Edit, Trash2, Wifi, Globe, Facebook, MessageCircle, Mail, Send, Instagram, RefreshCw, Smartphone } from 'lucide-react';
import axios from 'axios';

const TIPO_VISUAL = {
  whatsapp: { Icon: MessageCircle, color: 'text-green-500', bg: 'bg-green-600' },
  whatsapp_oficial: { Icon: MessageCircle, color: 'text-green-500', bg: 'bg-green-600' },
  whatsapp_cloud: { Icon: MessageCircle, color: 'text-green-500', bg: 'bg-green-600' },
  whatsapp_session: { Icon: MessageCircle, color: 'text-green-500', bg: 'bg-green-600' },
  telegram: { Icon: Send, color: 'text-sky-500', bg: 'bg-sky-500' },
  email: { Icon: Mail, color: 'text-red-500', bg: 'bg-red-500' },
  website: { Icon: Globe, color: 'text-primary', bg: 'bg-primary' },
  webchat: { Icon: Globe, color: 'text-primary', bg: 'bg-primary' },
  instagram: { Icon: Instagram, color: 'text-pink-500', bg: 'bg-gradient-to-tr from-yellow-500 via-pink-500 to-purple-600' },
  facebook: { Icon: Facebook, color: 'text-blue-600', bg: 'bg-blue-600' },
  app_mobile: { Icon: Smartphone, color: 'text-violet-500', bg: 'bg-violet-600' },
};

function CanalAvatar({ canal, live }) {
  const visual = TIPO_VISUAL[canal.tipo] || TIPO_VISUAL.whatsapp;
  const { Icon } = visual;
  const foto = live?.profile_picture || canal.dados_extras?.profile_picture_url || canal.dados_extras?.profilePicUrl;
  const [fotoFalhou, setFotoFalhou] = useState(false);

  useEffect(() => setFotoFalhou(false), [foto]);

  if (!foto || fotoFalhou) {
    return (
      <div className="w-10 h-10 rounded-full bg-muted border border-border flex items-center justify-center flex-shrink-0">
        <Icon className={`w-5 h-5 ${visual.color}`} />
      </div>
    );
  }
  return (
    <div className="relative w-10 h-10 flex-shrink-0">
      <img
        src={foto}
        alt={canal.nome}
        className="w-10 h-10 rounded-full object-cover border border-border"
        onError={() => setFotoFalhou(true)}
      />
      <span className={`absolute -bottom-1 -right-1 w-5 h-5 rounded-full ${visual.bg} border-2 border-card flex items-center justify-center`}>
        <Icon className="w-3 h-3 text-white" />
      </span>
    </div>
  );
}

function StatusConexao({ live, carregando }) {
  if (!live) {
    return (
      <span className="px-3 py-1 rounded-full text-xs font-semibold bg-muted text-muted-foreground">
        {carregando ? 'Verificando...' : 'Sem informação'}
      </span>
    );
  }
  if (live.connected === true) {
    return (
      <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-semibold bg-green-100 text-green-800">
        <span className="w-2 h-2 rounded-full bg-green-500" /> Conectado
      </span>
    );
  }
  if (live.connected === false) {
    return (
      <span
        className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-semibold bg-red-100 text-red-800"
        title={live.error || ''}
      >
        <span className="w-2 h-2 rounded-full bg-red-500" /> Desconectado
      </span>
    );
  }
  return (
    <span
      className="px-3 py-1 rounded-full text-xs font-semibold bg-amber-100 text-amber-800"
      title={live.error || ''}
    >
      Indisponível
    </span>
  );
}

export default function SuperadminCanais() {
  const [search, setSearch] = useState('');
  const [showAddModal, setShowAddModal] = useState(false);
  const [canais, setCanais] = useState([]);
  const [provedores, setProvedores] = useState([]);
  const [loading, setLoading] = useState(false);
  const [errorMsg, setErrorMsg] = useState('');
  const [liveStatus, setLiveStatus] = useState({});
  const [loadingLive, setLoadingLive] = useState(false);
  const [addCanalForm, setAddCanalForm] = useState({
    tipo: 'telegram',
    nome: '',
    ativo: true,
    provedor: '',
    // WhatsApp
    instance_id: '',
    api_key: '',
    // Telegram
    api_id: '',
    api_hash: '',
    app_title: '',
    short_name: '',
    verification_code: '',
    phone_number: '',
    // Email
    email: '',
    smtp_host: '',
    smtp_port: '',
    // Website
    url: '',
    // Extras
    dados_extras: {}
  });

  const tipoIcons = {
    whatsapp: <MessageCircle className="w-5 h-5 text-green-500" />,
    whatsapp_oficial: <MessageCircle className="w-5 h-5 text-green-500" />,
    whatsapp_cloud: <MessageCircle className="w-5 h-5 text-green-500" />,
    whatsapp_session: <MessageCircle className="w-5 h-5 text-green-500" />,
    telegram: <Send className="w-5 h-5 text-sky-500" />,
    email: <Mail className="w-5 h-5 text-red-500" />,
    website: <Globe className="w-5 h-5 text-primary" />,
    instagram: <Instagram className="w-5 h-5 text-pink-500" />,
    facebook: <Facebook className="w-5 h-5 text-blue-600" />
  };

  const tipoLabels = {
    whatsapp: 'WhatsApp',
    whatsapp_oficial: 'WhatsApp Oficial',
    whatsapp_cloud: 'WhatsApp Cloud',
    whatsapp_session: 'WhatsApp',
    telegram: 'Telegram',
    email: 'E-mail',
    website: 'Website',
    instagram: 'Instagram',
    facebook: 'Facebook',
  };

  // Buscar canais e provedores
  useEffect(() => {
    const fetchData = async () => {
      try {
        const token = localStorage.getItem('token');

        // Buscar canais
        const canaisRes = await axios.get('/api/canais/', {
          headers: { Authorization: `Token ${token}` }
        });
        setCanais(canaisRes.data.results || canaisRes.data);

        // Buscar provedores
        const provedoresRes = await axios.get('/api/provedores/', {
          headers: { Authorization: `Token ${token}` }
        });
        setProvedores(provedoresRes.data.results || provedoresRes.data);

      } catch (err) {
        console.error('Erro ao carregar dados:', err);
        setErrorMsg('Erro ao carregar canais e provedores');
      }
    };

    fetchData();
  }, []);

  const fetchLiveStatus = useCallback(async (refresh = false) => {
    setLoadingLive(true);
    try {
      const token = localStorage.getItem('token');
      const res = await axios.get('/api/canais/live-status/', {
        headers: { Authorization: `Token ${token}` },
        params: refresh ? { refresh: 1 } : undefined,
      });
      setLiveStatus(res.data?.status || {});
    } catch (err) {
      console.error('Erro ao consultar status dos canais:', err);
    } finally {
      setLoadingLive(false);
    }
  }, []);

  useEffect(() => {
    fetchLiveStatus();
  }, [fetchLiveStatus]);

  const handleAddCanalChange = (e) => {
    const { name, value, type, checked } = e.target;
    setAddCanalForm(prev => ({
      ...prev,
      [name]: type === 'checkbox' ? checked : value
    }));
  };

  const handleAddCanal = async (e) => {
    e.preventDefault();
    setLoading(true);
    setErrorMsg('');

    try {
      const token = localStorage.getItem('token');
      const response = await axios.post('/api/canais/', addCanalForm, {
        headers: { Authorization: `Token ${token}` }
      });

      // Adicionar novo canal à lista
      setCanais(prev => [...prev, response.data]);

      // Limpar formulário e fechar modal
      setAddCanalForm({
        tipo: 'telegram',
        nome: '',
        ativo: true,
        provedor: '',
        instance_id: '',
        api_key: '',
        api_id: '',
        api_hash: '',
        app_title: '',
        short_name: '',
        verification_code: '',
        phone_number: '',
        email: '',
        smtp_host: '',
        smtp_port: '',
        url: '',
        dados_extras: {}
      });
      setShowAddModal(false);

    } catch (err) {
      setErrorMsg(err.response?.data?.error || 'Erro ao criar canal');
    } finally {
      setLoading(false);
    }
  };

  const handleDeleteCanal = async (canalId) => {
    if (!window.confirm('Tem certeza que deseja excluir este canal?')) return;

    try {
      const token = localStorage.getItem('token');
      await axios.delete(`/api/canais/${canalId}/`, {
        headers: { Authorization: `Token ${token}` }
      });

      // Remover canal da lista
      setCanais(prev => prev.filter(c => c.id !== canalId));

    } catch (err) {
      alert('Erro ao excluir canal!');
    }
  };

  const filteredCanais = canais.filter(canal => {
    const searchLower = search.toLowerCase();
    // O provedor pode vir como objeto completo ou como ID
    const provedorId = typeof canal.provedor === 'object' ? canal.provedor.id : canal.provedor;
    const provedor = provedores.find(p => p.id === provedorId);
    return (
      canal.nome?.toLowerCase().includes(searchLower) ||
      tipoLabels[canal.tipo]?.toLowerCase().includes(searchLower) ||
      provedor?.nome?.toLowerCase().includes(searchLower) ||
      canal.email?.toLowerCase().includes(searchLower) ||
      canal.url?.toLowerCase().includes(searchLower)
    );
  });

  return (
    <div className="flex-1 p-6 bg-background overflow-y-auto">
      {/* Header */}
      <div className="mb-8">
        <h1 className="text-3xl font-bold text-foreground mb-2">
          Gerenciamento de Canais
        </h1>
        <p className="text-muted-foreground">Gerencie canais de comunicação dos provedores</p>
      </div>

      {/* Busca e botão adicionar */}
      <div className="bg-card rounded-lg p-4 mb-4 flex items-center gap-4 shadow">
        <div className="relative flex-1">
          <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 text-muted-foreground w-4 h-4" />
          <input
            type="text"
            placeholder="Buscar canais..."
            value={search}
            onChange={e => setSearch(e.target.value)}
            className="pl-10 pr-4 py-2 rounded bg-background border w-full"
          />
        </div>
        <button
          className="flex items-center gap-2 border border-border px-4 py-2 rounded font-medium text-sm text-foreground hover:bg-muted disabled:opacity-60"
          onClick={() => fetchLiveStatus(true)}
          disabled={loadingLive}
          title="Consultar novamente a Meta"
        >
          <RefreshCw className={`w-4 h-4 ${loadingLive ? 'animate-spin' : ''}`} />
          {loadingLive ? 'Verificando...' : 'Atualizar status'}
        </button>
        <button
          className="flex items-center gap-2 bg-primary text-white px-4 py-2 rounded font-medium text-sm"
          onClick={() => setShowAddModal(true)}
        >
          <Plus className="w-4 h-4" /> Adicionar Canal
        </button>
      </div>

      {/* Modal de adicionar canal */}
      {showAddModal && (
        <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50">
          <div className="bg-[#23272f] rounded-xl shadow-2xl p-8 w-full max-w-2xl relative border border-border max-h-[90vh] overflow-y-auto">
            <button className="absolute top-2 right-2 text-gray-400 hover:text-white text-2xl" onClick={() => setShowAddModal(false)}>&times;</button>
            <h2 className="text-2xl font-bold mb-6 text-white">Adicionar Canal</h2>

            <form onSubmit={handleAddCanal} className="space-y-5">
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div>
                  <label className="block font-medium mb-1 text-gray-200">Tipo de Canal *</label>
                  <select
                    name="tipo"
                    className="w-full px-4 py-2 rounded bg-[#181b20] text-white border border-border"
                    value={addCanalForm.tipo}
                    onChange={handleAddCanalChange}
                    required
                  >
                    {Object.entries(tipoLabels).map(([value, label]) => (
                      <option key={value} value={value}>{label}</option>
                    ))}
                  </select>
                </div>

                <div>
                  <label className="block font-medium mb-1 text-gray-200">Provedor *</label>
                  <select
                    name="provedor"
                    className="w-full px-4 py-2 rounded bg-[#181b20] text-white border border-border"
                    value={addCanalForm.provedor}
                    onChange={handleAddCanalChange}
                    required
                  >
                    <option value="">Selecione um provedor</option>
                    {provedores.map(provedor => (
                      <option key={provedor.id} value={provedor.id}>{provedor.nome}</option>
                    ))}
                  </select>
                </div>

                <div>
                  <label className="block font-medium mb-1 text-gray-200">Nome do Canal</label>
                  <input
                    type="text"
                    name="nome"
                    className="w-full px-4 py-2 rounded bg-[#181b20] text-white border border-border"
                    value={addCanalForm.nome}
                    onChange={handleAddCanalChange}
                  />
                </div>

                <div className="flex items-center">
                  <input
                    type="checkbox"
                    name="ativo"
                    id="ativo"
                    className="mr-2"
                    checked={addCanalForm.ativo}
                    onChange={handleAddCanalChange}
                  />
                  <label htmlFor="ativo" className="text-gray-200">Canal Ativo</label>
                </div>
              </div>

              {/* Campos específicos por tipo */}
              {addCanalForm.tipo === 'whatsapp' && (
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  <div>
                    <label className="block font-medium mb-1 text-gray-200">Instance ID</label>
                    <input
                      type="text"
                      name="instance_id"
                      className="w-full px-4 py-2 rounded bg-[#181b20] text-white border border-border"
                      value={addCanalForm.instance_id}
                      onChange={handleAddCanalChange}
                    />
                  </div>
                  <div>
                    <label className="block font-medium mb-1 text-gray-200">API Key</label>
                    <input
                      type="text"
                      name="api_key"
                      className="w-full px-4 py-2 rounded bg-[#181b20] text-white border border-border"
                      value={addCanalForm.api_key}
                      onChange={handleAddCanalChange}
                    />
                  </div>
                </div>
              )}

              {addCanalForm.tipo === 'telegram' && (
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  <div>
                    <label className="block font-medium mb-1 text-gray-200">API ID</label>
                    <input
                      type="text"
                      name="api_id"
                      className="w-full px-4 py-2 rounded bg-[#181b20] text-white border border-border"
                      value={addCanalForm.api_id}
                      onChange={handleAddCanalChange}
                    />
                  </div>
                  <div>
                    <label className="block font-medium mb-1 text-gray-200">API Hash</label>
                    <input
                      type="text"
                      name="api_hash"
                      className="w-full px-4 py-2 rounded bg-[#181b20] text-white border border-border"
                      value={addCanalForm.api_hash}
                      onChange={handleAddCanalChange}
                    />
                  </div>
                  <div>
                    <label className="block font-medium mb-1 text-gray-200">Phone Number</label>
                    <input
                      type="text"
                      name="phone_number"
                      className="w-full px-4 py-2 rounded bg-[#181b20] text-white border border-border"
                      value={addCanalForm.phone_number}
                      onChange={handleAddCanalChange}
                    />
                  </div>
                </div>
              )}

              {addCanalForm.tipo === 'email' && (
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  <div>
                    <label className="block font-medium mb-1 text-gray-200">E-mail</label>
                    <input
                      type="email"
                      name="email"
                      className="w-full px-4 py-2 rounded bg-[#181b20] text-white border border-border"
                      value={addCanalForm.email}
                      onChange={handleAddCanalChange}
                    />
                  </div>
                  <div>
                    <label className="block font-medium mb-1 text-gray-200">SMTP Host</label>
                    <input
                      type="text"
                      name="smtp_host"
                      className="w-full px-4 py-2 rounded bg-[#181b20] text-white border border-border"
                      value={addCanalForm.smtp_host}
                      onChange={handleAddCanalChange}
                    />
                  </div>
                  <div>
                    <label className="block font-medium mb-1 text-gray-200">SMTP Port</label>
                    <input
                      type="text"
                      name="smtp_port"
                      className="w-full px-4 py-2 rounded bg-[#181b20] text-white border border-border"
                      value={addCanalForm.smtp_port}
                      onChange={handleAddCanalChange}
                    />
                  </div>
                </div>
              )}

              {addCanalForm.tipo === 'website' && (
                <div>
                  <label className="block font-medium mb-1 text-gray-200">URL</label>
                  <input
                    type="url"
                    name="url"
                    className="w-full px-4 py-2 rounded bg-[#181b20] text-white border border-border"
                    value={addCanalForm.url}
                    onChange={handleAddCanalChange}
                  />
                </div>
              )}

              {errorMsg && <div className="text-red-400 text-sm mb-2">{errorMsg}</div>}

              <button
                type="submit"
                className="w-full bg-primary text-white py-2 rounded font-bold hover:bg-primary/80 transition"
                disabled={loading}
              >
                {loading ? 'Criando...' : 'Criar Canal'}
              </button>
            </form>
          </div>
        </div>
      )}

      {/* Tabela de canais */}
      <div className="bg-card rounded-lg shadow overflow-x-auto">
        <table className="min-w-full">
          <thead className="bg-muted">
            <tr>
              <th className="px-6 py-3 text-left text-xs font-semibold text-foreground uppercase">CANAL</th>
              <th className="px-6 py-3 text-left text-xs font-semibold text-foreground uppercase">PROVEDOR</th>
              <th className="px-6 py-3 text-center text-xs font-semibold text-foreground uppercase">TIPO</th>
              <th className="px-6 py-3 text-center text-xs font-semibold text-foreground uppercase">STATUS</th>
              <th className="px-6 py-3 text-center text-xs font-semibold text-foreground uppercase">CRIADO EM</th>
              <th className="px-6 py-3 text-center text-xs font-semibold text-foreground uppercase">AÇÕES</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-border">
            {filteredCanais.map(canal => {
              // O provedor pode vir como objeto completo ou como ID
              const provedorId = typeof canal.provedor === 'object' ? canal.provedor.id : canal.provedor;
              const provedor = provedores.find(p => p.id === provedorId);
              const live = liveStatus[String(canal.id)];
              return (
                <tr key={canal.id} className="hover:bg-muted/50">
                  <td className="px-6 py-4 min-w-[240px] align-middle">
                    <div className="flex items-center gap-3">
                      <CanalAvatar canal={canal} live={live} />
                      <div>
                        <div className="font-semibold text-card-foreground">
                          {canal.nome || live?.display_name || tipoLabels[canal.tipo] || canal.tipo}
                        </div>
                        <div className="text-xs text-muted-foreground font-mono">
                          {canal.tipo === 'instagram'
                            ? (canal.dados_extras?.instagram_username
                              ? `@${canal.dados_extras.instagram_username}`
                              : '—')
                            : (canal.phone_number || canal.email || canal.url || '—')}
                        </div>
                        {canal.waba_id && (
                          <div className="text-[10px] text-muted-foreground/60 font-mono mt-0.5">
                            ID: {canal.waba_id}
                          </div>
                        )}
                        {canal.tipo === 'instagram' && (canal.dados_extras?.instagram_user_id || canal.dados_extras?.instagram_webhook_account_id) && (
                          <div className="text-[10px] text-muted-foreground/60 font-mono mt-0.5">
                            IG ID: {canal.dados_extras.instagram_user_id || canal.dados_extras.instagram_webhook_account_id}
                          </div>
                        )}
                      </div>
                    </div>
                  </td>
                  <td className="px-6 py-4 text-left align-middle">
                    <div className="flex items-center gap-2">
                      <Wifi className="w-4 h-4 text-muted-foreground" />
                      <span className="text-sm text-foreground">{provedor?.nome || 'Provedor não encontrado'}</span>
                    </div>
                  </td>
                  <td className="px-6 py-4 text-center align-middle">
                    <span className="inline-flex items-center gap-1 px-2 py-1 rounded-full text-xs font-medium bg-green-900/30 text-green-400 border border-green-700/30">
                      {tipoIcons[canal.tipo] || <MessageCircle className="w-4 h-4" />}
                      <span>{tipoLabels[canal.tipo] || canal.tipo}</span>
                    </span>
                  </td>
                  <td className="px-6 py-4 text-center align-middle">
                    <StatusConexao live={live} carregando={loadingLive} />
                  </td>
                  <td className="px-6 py-4 text-center align-middle text-sm text-muted-foreground">
                    {new Date(canal.created_at).toLocaleDateString('pt-BR')}
                  </td>
                  <td className="px-6 py-4 text-center align-middle">
                    <div className="flex items-center justify-center gap-2">
                      <button className="p-1 hover:bg-muted rounded text-blue-600">
                        <Edit className="w-4 h-4" />
                      </button>
                      <button
                        className="p-1 hover:bg-muted rounded text-red-600"
                        onClick={() => handleDeleteCanal(canal.id)}
                      >
                        <Trash2 className="w-4 h-4" />
                      </button>
                    </div>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>

        {filteredCanais.length === 0 && (
          <div className="text-center py-8 text-muted-foreground">
            {search ? 'Nenhum canal encontrado para esta busca.' : 'Nenhum canal cadastrado ainda.'}
          </div>
        )}
      </div>
    </div>
  );
}