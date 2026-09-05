import React, { useState, useEffect } from 'react';
import axios from 'axios';
import { Server, Plus, Edit, Trash2, ShieldCheck, Activity, Globe, Save, X, ExternalLink, RefreshCw } from 'lucide-react';
import { toast } from './lib/notify';

export default function SuperadminVps() {
  const [vpsList, setVpsList] = useState([]);
  const [hetznerServers, setHetznerServers] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showModal, setShowModal] = useState(false);
  const [isEditing, setIsEditing] = useState(false);
  const [currentVps, setCurrentVps] = useState({
    id: null,
    name: '',
    api_url: '',
    portainer_api_key: '',
    endpoint_id: 1,
    max_capacity: 3,
    is_active: true
  });
  const [activeTab, setActiveTab] = useState('list'); // 'list' | 'registry'
  const [registryConfig, setRegistryConfig] = useState({
    github_username: '',
    github_pat: '',
    admin_webhook_secret: ''
  });
  const [loadingConfig, setLoadingConfig] = useState(false);

  const fetchVps = async () => {
    setLoading(true);
    try {
      const token = localStorage.getItem('token');
      const res = await axios.get('/api/vps-servers/', {
        headers: { Authorization: `Token ${token}` }
      });
      const list = res.data.results || res.data || [];
      setVpsList([...list].sort((a, b) => Number(a.id) - Number(b.id)));
      
      // Também buscar da Hetzner para sugestão
      const poolRes = await axios.get('/api/provedores/vps-pool/', {
        headers: { Authorization: `Token ${token}` }
      });
      const unregistered = poolRes.data.filter(v => !v.is_registered);
      setHetznerServers(unregistered);
    } catch (error) {
      console.error('Erro ao buscar VPS:', error);
      toast.error('Erro ao carregar lista de servidores.');
    } finally {
      setLoading(false);
    }
  };

  const fetchConfig = async () => {
    try {
      const token = localStorage.getItem('token');
      const res = await axios.get('/api/system-config/', {
        headers: { Authorization: `Token ${token}` }
      });
      // A SystemConfigView retorna o payload direto + o campo 'id'
      if (res.data) {
        setRegistryConfig({
          github_username: res.data.github_username || '',
          github_pat: res.data.github_pat || '',
          admin_webhook_secret: res.data.ADMIN_WEBHOOK_SECRET || ''
        });
      }
    } catch (err) {
      console.error('Erro ao buscar config:', err);
    }
  };

  useEffect(() => {
    fetchVps();
    fetchConfig();
  }, []);

  const handleSaveConfig = async () => {
    setLoadingConfig(true);
    try {
      const token = localStorage.getItem('token');
      
      // Enviamos as configurações atuais + as novas do GitHub
      // Primeiro buscamos o que já existe para não sobrescrever outros campos (como hetzner_token)
      const resCurrent = await axios.get('/api/system-config/', {
        headers: { Authorization: `Token ${token}` }
      });
      
      const currentPayload = resCurrent.data || {};
      delete currentPayload.id;

      const newPayload = {
        ...currentPayload,
        github_username: registryConfig.github_username,
        github_pat: registryConfig.github_pat,
        ADMIN_WEBHOOK_SECRET: registryConfig.admin_webhook_secret
      };

      // A SystemConfigView usa PUT para criar ou atualizar o primeiro registro
      await axios.put('/api/system-config/', newPayload, {
        headers: { Authorization: `Token ${token}` }
      });
      
      toast.success('Configurações do Registry salvas com sucesso!');
    } catch (err) {
      console.error('Erro ao salvar config:', err);
      toast.error('Erro ao salvar configurações do Registry.');
    } finally {
      setLoadingConfig(false);
    }
  };

  const handleOpenModal = (vps = null) => {
    if (vps) {
      setCurrentVps(vps);
      setIsEditing(true);
    } else {
      setCurrentVps({
        id: null,
        name: '',
        api_url: '',
        portainer_api_key: '',
        endpoint_id: 1,
        max_capacity: 3,
        is_active: true
      });
      setIsEditing(false);
    }
    setShowModal(true);
  };

  const handleSave = async (e) => {
    e.preventDefault();
    try {
      const token = localStorage.getItem('token');
      const data = { ...currentVps };
      
      if (isEditing) {
        await axios.put(`/api/vps-servers/${data.id}/`, data, {
          headers: { Authorization: `Token ${token}` }
        });
        toast.success('Servidor atualizado com sucesso!');
      } else {
        await axios.post('/api/vps-servers/', data, {
          headers: { Authorization: `Token ${token}` }
        });
        toast.success('Servidor cadastrado com sucesso!');
      }
      setShowModal(false);
      fetchVps();
    } catch (error) {
      toast.error('Erro ao salvar servidor.');
    }
  };

  const handleDelete = async (id) => {
    if (!window.confirm('Tem certeza que deseja excluir este servidor?')) return;
    try {
      const token = localStorage.getItem('token');
      await axios.delete(`/api/vps-servers/${id}/`, {
        headers: { Authorization: `Token ${token}` }
      });
      toast.success('Servidor excluído.');
      fetchVps();
    } catch (error) {
      toast.error('Erro ao excluir servidor.');
    }
  };

  const handleRegisterHetzner = (h) => {
    setCurrentVps({
      ...currentVps,
      name: h.label.replace(' (Hetzner - Não Cadastrada)', ''),
      api_url: `https://${h.api_url}:9443`
    });
    setIsEditing(false);
    setShowModal(true);
  };

  return (
    <div className="flex-1 p-6 bg-background overflow-y-auto">
      <div className="flex justify-between items-center mb-8">
        <div>
          <h1 className="text-3xl font-bold text-foreground mb-2 flex items-center gap-3">
            <Server className="w-8 h-8 text-primary" />
            Infraestrutura
          </h1>
          <p className="text-muted-foreground">Gerencie servidores VPS e configurações globais de Registry</p>
        </div>
        <div className="flex gap-2">
          <button 
            onClick={() => setActiveTab('list')}
            className={`px-4 py-2 rounded-lg font-bold transition flex items-center gap-2 ${activeTab === 'list' ? 'bg-primary text-white' : 'bg-muted text-gray-400 hover:text-white'}`}
          >
            <Server size={18} /> Servidores
          </button>
          <button 
            onClick={() => setActiveTab('registry')}
            className={`px-4 py-2 rounded-lg font-bold transition flex items-center gap-2 ${activeTab === 'registry' ? 'bg-primary text-white' : 'bg-muted text-gray-400 hover:text-white'}`}
          >
            <Globe size={18} /> Configurar Registry
          </button>
        </div>
      </div>

      {activeTab === 'list' ? (
        <>
          <div className="flex justify-end mb-6">
            <button 
              onClick={() => handleOpenModal()}
              className="flex items-center gap-2 bg-green-600 text-white px-4 py-2 rounded-lg font-bold hover:bg-green-700 transition shadow-lg"
            >
              <Plus size={20} /> Cadastrar Nova VPS
            </button>
          </div>

          {loading ? (
            <div className="flex justify-center p-12">
              <RefreshCw className="animate-spin text-primary w-8 h-8" />
            </div>
          ) : (
            <div className="space-y-8">
          {/* VPS Cadastradas */}
          <section>
            <h2 className="text-xl font-bold mb-4 flex items-center gap-2 text-white">
              <ShieldCheck className="text-green-500" /> Servidores Ativos
            </h2>
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
              {vpsList.map(vps => (
                <div key={vps.id} className="bg-card rounded-xl shadow-lg border border-border overflow-hidden transition-all hover:shadow-xl group">
                  <div className="p-5">
                    <div className="flex justify-between items-start mb-4">
                      <div className="flex items-center gap-3">
                        <div className="p-2 rounded-lg bg-primary/10 border border-primary/20">
                          <Server className="text-primary" size={24} />
                        </div>
                        <div>
                          <h3 className="font-bold text-lg text-white">
                            {vps.display_number ? `VPS ${vps.display_number}` : vps.name}
                          </h3>
                          {vps.display_number && vps.name && vps.name !== `VPS ${vps.display_number}` ? (
                            <p className="text-[10px] text-muted-foreground font-mono">{vps.name}</p>
                          ) : null}
                          <p className="text-xs text-muted-foreground flex items-center gap-1">
                            <Globe size={12} /> {vps.api_url}
                          </p>
                        </div>
                      </div>
                      <div className="flex gap-2">
                        <button onClick={() => handleOpenModal(vps)} className="p-2 text-gray-400 hover:text-white hover:bg-muted rounded-lg transition">
                          <Edit size={16} />
                        </button>
                        <button onClick={() => handleDelete(vps.id)} className="p-2 text-gray-400 hover:text-red-500 hover:bg-red-500/10 rounded-lg transition">
                          <Trash2 size={16} />
                        </button>
                      </div>
                    </div>

                    <div className="grid grid-cols-2 gap-4 mt-4">
                      <div className="bg-muted/50 p-3 rounded-lg border border-border">
                        <p className="text-[10px] uppercase font-bold text-muted-foreground mb-1">Capacidade</p>
                        <div className="flex items-end justify-between">
                          <p className="text-lg font-bold text-white">{vps.providers_count || 0}/{vps.max_capacity}</p>
                          <span className="text-[10px] text-primary">Provedores</span>
                        </div>
                        <div className="w-full bg-background h-1.5 rounded-full mt-2 overflow-hidden">
                          <div 
                            className="bg-primary h-full transition-all duration-500" 
                            style={{ width: `${Math.min(100, ((vps.providers_count || 0) / vps.max_capacity) * 100)}%` }}
                          />
                        </div>
                      </div>
                      <div className="bg-muted/50 p-3 rounded-lg border border-border">
                        <p className="text-[10px] uppercase font-bold text-muted-foreground mb-1">Status Portainer</p>
                        <div className="flex items-center gap-2 text-green-500">
                          <Activity size={16} />
                          <span className="text-xs font-bold uppercase tracking-wider">Online</span>
                        </div>
                        <p className="text-[10px] text-muted-foreground mt-2">ID Endpoint: {vps.endpoint_id}</p>
                      </div>
                    </div>
                  </div>
                </div>
              ))}
              {vpsList.length === 0 && (
                <div className="col-span-full py-12 text-center bg-card/50 rounded-xl border border-dashed border-border text-muted-foreground">
                  Nenhuma VPS cadastrada no banco de dados.
                </div>
              )}
            </div>
          </section>

          {/* Sugestões da Hetzner */}
          {hetznerServers.length > 0 && (
            <section>
              <h2 className="text-xl font-bold mb-4 flex items-center gap-2 text-white">
                <ExternalLink className="text-blue-500" /> Servidores na Hetzner (Pendente Cadastro)
              </h2>
              <div className="bg-card/30 rounded-xl border border-border overflow-hidden">
                <table className="w-full text-left">
                  <thead className="bg-muted/50 text-xs uppercase font-bold text-muted-foreground border-b border-border">
                    <tr>
                      <th className="px-6 py-4 text-white">Nome na Hetzner</th>
                      <th className="px-6 py-4 text-white">IP Público</th>
                      <th className="px-6 py-4 text-white">Ação</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-border text-sm">
                    {hetznerServers.map(h => (
                      <tr key={h.key} className="hover:bg-muted/30 transition">
                        <td className="px-6 py-4 font-medium text-white">{h.label.replace(' (Hetzner - Não Cadastrada)', '')}</td>
                        <td className="px-6 py-4 text-muted-foreground font-mono">{h.api_url}</td>
                        <td className="px-6 py-4">
                          <button 
                            onClick={() => handleRegisterHetzner(h)}
                            className="text-primary hover:text-white bg-primary/10 hover:bg-primary px-3 py-1 rounded-md transition font-bold text-xs flex items-center gap-1"
                          >
                            <Plus size={14} /> Cadastrar para Deploy
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </section>
          )}
          </div>
        )}
      </>
      ) : (
        <div className="max-w-2xl mx-auto mt-8">
          <div className="bg-card rounded-2xl shadow-2xl border border-border overflow-hidden">
            <div className="bg-gradient-to-r from-primary/10 to-transparent p-8 border-b border-border">
              <h2 className="text-2xl font-bold text-white flex items-center gap-3">
                <Globe className="text-primary w-8 h-8" />
                Configurações do Registry GitHub
              </h2>
              <p className="text-muted-foreground mt-2">
                Estas credenciais serão usadas para configurar automaticamente o acesso aos repositórios privados em todas as VPSs cadastradas.
              </p>
            </div>
            
            <div className="p-8 space-y-6">
              <div className="bg-blue-500/10 border border-blue-500/20 p-4 rounded-xl flex gap-4 items-start">
                <ShieldCheck className="text-blue-400 shrink-0 mt-1" size={24} />
                <p className="text-sm text-blue-200">
                  O Superadmin verificará se a VPS possui a registry <strong>ghcr.io</strong> configurada antes de cada deploy. Se não possuir, ele a criará usando os dados abaixo.
                </p>
              </div>

              <div className="space-y-4">
                <div>
                  <label className="block text-xs font-bold uppercase tracking-wider mb-2 text-gray-400">GitHub Username</label>
                  <input 
                    type="text" 
                    className="w-full px-4 py-3 rounded-lg bg-[#181b20] text-white border border-border focus:ring-2 focus:ring-primary/50 outline-none transition"
                    value={registryConfig.github_username}
                    onChange={e => setRegistryConfig({...registryConfig, github_username: e.target.value})}
                    placeholder="Seu usuário do GitHub (ex: juniorssilvaa)"
                  />
                </div>
                <div>
                  <label className="block text-xs font-bold uppercase tracking-wider mb-2 text-gray-400">Personal Access Token (PAT)</label>
                  <input 
                    type="password" 
                    className="w-full px-4 py-3 rounded-lg bg-[#181b20] text-white border border-border focus:ring-2 focus:ring-primary/50 outline-none transition"
                    value={registryConfig.github_pat}
                    onChange={e => setRegistryConfig({...registryConfig, github_pat: e.target.value})}
                    placeholder="ghp_xxxxxxxxxxxxxxxxxxxx"
                  />
                  <p className="text-[10px] text-gray-500 mt-2">
                    Crie um token com a permissão <code>read:packages</code> no GitHub.
                  </p>
                </div>

                <div className="pt-4 border-t border-border">
                  <label className="block text-xs font-bold uppercase tracking-wider mb-2 text-gray-400">Webhook Secret (Segurança de Integração)</label>
                  <input 
                    type="text" 
                    className="w-full px-4 py-3 rounded-lg bg-[#181b20] text-white border border-border focus:ring-2 focus:ring-primary/50 outline-none transition"
                    value={registryConfig.admin_webhook_secret}
                    onChange={e => setRegistryConfig({...registryConfig, admin_webhook_secret: e.target.value})}
                    placeholder="Chave secreta para validar comunicações entre Provedor e Superadmin"
                  />
                  <p className="text-[10px] text-gray-500 mt-2">
                    Esta chave será enviada automaticamente para o arquivo <code>.env</code> dos provedores para validar webhooks e registros de canal.
                  </p>
                </div>
              </div>

              <div className="pt-4">
                <button
                  onClick={handleSaveConfig}
                  disabled={loadingConfig}
                  className="w-full bg-primary text-white py-4 rounded-xl font-bold hover:bg-primary/80 transition flex items-center justify-center gap-2 shadow-xl shadow-primary/20 disabled:opacity-50"
                >
                  {loadingConfig ? <RefreshCw className="animate-spin" size={20} /> : <Save size={20} />}
                  Salvar Configurações do Registry
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Modal de Cadastro/Edição */}
      {showModal && (
        <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50 p-4">
          <div className="bg-[#23272f] rounded-xl shadow-2xl p-8 w-full max-w-xl relative border border-border animate-in fade-in zoom-in duration-200">
            <button className="absolute top-4 right-4 text-gray-400 hover:text-white" onClick={() => setShowModal(false)}><X size={24} /></button>
            <h2 className="text-2xl font-bold mb-2 text-white">{isEditing ? 'Editar Servidor' : 'Cadastrar Servidor VPS'}</h2>
            <p className="text-muted-foreground text-sm mb-6">Configure o acesso ao Portainer desta VPS</p>
            
            <form onSubmit={handleSave} className="grid grid-cols-1 md:grid-cols-2 gap-5">
              <div className="md:col-span-2">
                <label className="block text-xs font-bold uppercase tracking-wider mb-2 text-gray-400">Nome do Servidor</label>
                <input 
                  type="text" 
                  className="w-full px-4 py-3 rounded-lg bg-[#181b20] text-white border border-border focus:ring-2 focus:ring-primary/50 outline-none transition"
                  value={currentVps.name}
                  onChange={e => setCurrentVps({...currentVps, name: e.target.value})}
                  placeholder="Ex: VPS Produção 01"
                  required 
                />
              </div>
              <div className="md:col-span-2">
                <label className="block text-xs font-bold uppercase tracking-wider mb-2 text-gray-400">URL da API do Portainer (com porta)</label>
                <input 
                  type="url" 
                  className="w-full px-4 py-3 rounded-lg bg-[#181b20] text-white border border-border focus:ring-2 focus:ring-primary/50 outline-none transition"
                  value={currentVps.api_url}
                  onChange={e => setCurrentVps({...currentVps, api_url: e.target.value})}
                  placeholder="Ex: https://123.45.67.89:9443"
                  required 
                />
              </div>
              <div>
                <label className="block text-xs font-bold uppercase tracking-wider mb-2 text-gray-400">Token de API (Portainer)</label>
                <input 
                  type="password" 
                  className="w-full px-4 py-3 rounded-lg bg-[#181b20] text-white border border-border focus:ring-2 focus:ring-primary/50 outline-none transition"
                  value={currentVps.portainer_api_key}
                  onChange={e => setCurrentVps({...currentVps, portainer_api_key: e.target.value})}
                  placeholder="Seu token do Portainer"
                  required 
                />
              </div>
              <div>
                <label className="block text-xs font-bold uppercase tracking-wider mb-2 text-gray-400">Endpoint ID</label>
                <input 
                  type="number" 
                  className="w-full px-4 py-3 rounded-lg bg-[#181b20] text-white border border-border focus:ring-2 focus:ring-primary/50 outline-none transition"
                  value={currentVps.endpoint_id}
                  onChange={e => setCurrentVps({...currentVps, endpoint_id: parseInt(e.target.value)})}
                  required 
                />
              </div>
              <div>
                <label className="block text-xs font-bold uppercase tracking-wider mb-2 text-gray-400">Capacidade Máxima</label>
                <input 
                  type="number" 
                  className="w-full px-4 py-3 rounded-lg bg-[#181b20] text-white border border-border focus:ring-2 focus:ring-primary/50 outline-none transition"
                  value={currentVps.max_capacity}
                  onChange={e => setCurrentVps({...currentVps, max_capacity: parseInt(e.target.value)})}
                  required 
                />
              </div>
              <div className="flex items-center gap-3 pt-6">
                <input 
                  type="checkbox" 
                  checked={currentVps.is_active}
                  onChange={e => setCurrentVps({...currentVps, is_active: e.target.checked})}
                  className="w-5 h-5 rounded border-border text-primary"
                />
                <label className="font-medium text-gray-200">Servidor Ativo</label>
              </div>

              <div className="md:col-span-2 pt-4">
                <button
                  type="submit"
                  className="w-full bg-primary text-white py-3 rounded-lg font-bold hover:bg-primary/80 transition flex items-center justify-center gap-2 shadow-lg shadow-primary/20"
                >
                  <Save size={20} /> {isEditing ? 'Salvar Alterações' : 'Concluir Cadastro'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
