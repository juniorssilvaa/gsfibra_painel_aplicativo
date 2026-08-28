import React, { useState, useEffect, useRef } from 'react';
import { Wifi, Search, Edit, Trash2, MoreVertical, Plus, Eye, Users, MessageCircle, TrendingUp, Database, Trash, FileText, CheckCircle2, RefreshCw } from 'lucide-react';
import axios from 'axios';
import ReactDOM from 'react-dom';

export default function SuperadminProvedores() {
  const [search, setSearch] = useState('');
  const [showAddModal, setShowAddModal] = useState(false);
  const [addProvedorForm, setAddProvedorForm] = useState({
    nome: '',
    site_oficial: '',
    endereco: '',
    email_contato: '',
    bot_mode: 'ia',
    // Campos Asaas
    cpf_cnpj: '',
    phone: '',
    mobile_phone: '',
    address_number: '',
    complement: '',
    province: '',
    postal_code: '',
    group_name: '',
    company: '',
    municipal_inscription: '',
    state_inscription: '',
    observations: '',
    additional_emails: '',
    notification_disabled: false,
    foreign_customer: false,
    // Campos Assinatura Asaas (Setup Automático)
    subscription_value: 0,
    subscription_cycle: 'MONTHLY',
    subscription_billing_type: 'BOLETO',
    subscription_next_due_date: '',
    // Outros campos existentes (mantidos para compatibilidade)
    redes_sociais: {},
    nome_agente_ia: '',
    estilo_personalidade: '',
    modo_falar: '',
    uso_emojis: '',
    personalidade: '',
    taxa_adesao: '',
    inclusos_plano: '',
    multa_cancelamento: '',
    tipo_conexao: '',
    prazo_instalacao: '',
    documentos_necessarios: '',
  });
  const [showEditModal, setShowEditModal] = useState(false);
  const [editProvedorForm, setEditProvedorForm] = useState({
    id: null,
    nome: '',
    site_oficial: '',
    endereco: '',
    email_contato: '',
    bot_mode: 'ia',
    // Campos Asaas
    cpf_cnpj: '',
    phone: '',
    mobile_phone: '',
    address_number: '',
    complement: '',
    province: '',
    postal_code: '',
    group_name: '',
    company: '',
    municipal_inscription: '',
    state_inscription: '',
    observations: '',
    additional_emails: '',
    notification_disabled: false,
    foreign_customer: false,
    // Campos Assinatura Asaas
    asaas_subscription_id: '',
    subscription_value: 0,
    subscription_cycle: 'MONTHLY',
    subscription_billing_type: 'BOLETO',
    subscription_status: '',
    subscription_next_due_date: '',
  });
  const [loadingEdit, setLoadingEdit] = useState(false);
  const [loadingAdd, setLoadingAdd] = useState(false);

  const [errorMsg, setErrorMsg] = useState('');
  const [provedoresState, setProvedoresState] = useState([]);
  const [menuId, setMenuId] = useState(null);
  const [menuPosition, setMenuPosition] = useState({ top: 0, left: 0 });
  const menuBtnRefs = useRef({});
  const [statsData, setStatsData] = useState({
    totalProvedores: 0,
    receitaMensal: 'R$ 0,00',
    totalUsuarios: 0,
    totalConversas: 0
  });

  // Estados para modais de limpeza
  const [showLimpezaModal, setShowLimpezaModal] = useState(false);
  const [provedorLimpeza, setProvedorLimpeza] = useState(null);
  const [loadingLimpeza, setLoadingLimpeza] = useState(false);
  const [limpezaResult, setLimpezaResult] = useState(null);
  const [subscriptionPayments, setSubscriptionPayments] = useState([]);
  const [loadingPayments, setLoadingPayments] = useState(false);

  const filteredProvedores = provedoresState.filter(p =>
    p.nome.toLowerCase().includes(search.toLowerCase()) ||
    p.site_oficial?.toLowerCase().includes(search.toLowerCase())
  );

  // Buscar estatísticas detalhadas
  const fetchStats = async () => {
    try {
      const token = localStorage.getItem('token');

      // Buscar provedores
      const provedoresRes = await axios.get('/api/provedores/', {
        headers: { Authorization: `Token ${token}` }
      });
      const provedores = provedoresRes.data.results || provedoresRes.data;

      // Calcular totais dos provedores
      const totalUsuarios = provedores.reduce((sum, p) => sum + (p.users_count || 0), 0);
      const totalConversas = provedores.reduce((sum, p) => sum + (p.conversations_count || 0), 0);

      setStatsData({
        totalProvedores: provedores.length,
        receitaMensal: 'R$ 0,00', // Placeholder - pode ser calculado baseado em planos
        totalUsuarios: totalUsuarios,
        totalConversas: totalConversas
      });

    } catch (err) {
      console.error('Erro ao buscar estatísticas:', err);
    }
  };

  // Buscar provedores reais do backend ao carregar
  useEffect(() => {
    const fetchProvedores = async () => {
      try {
        const token = localStorage.getItem('token');
        const res = await axios.get('/api/provedores/', {
          headers: { Authorization: `Token ${token}` }
        });
        setProvedoresState(res.data.results || res.data);
      } catch (err) {
        console.error('Erro ao carregar provedores:', err);
        setProvedoresState([]);
      }
    };

    fetchProvedores();
    fetchStats();
  }, []);

  const handleAddProvedorChange = (e) => {
    const { name, value, type, checked } = e.target;
    setAddProvedorForm(prev => ({
      ...prev,
      [name]: type === 'checkbox' ? checked : value
    }));
  };

  const handleAddProvedor = async (e) => {
    e.preventDefault();
    setLoadingAdd(true);
    setErrorMsg('');

    try {
      const token = localStorage.getItem('token');
      console.log('[DEBUG SuperadminProvedores] Criando novo provedor:', addProvedorForm);

      const response = await axios.post('/api/provedores/', addProvedorForm, {
        headers: { Authorization: `Token ${token}` }
      });

      console.log('[DEBUG SuperadminProvedores] Resposta da API:', response.data);

      // Atualizar lista após criar
      const res = await axios.get('/api/provedores/', {
        headers: { Authorization: `Token ${token}` }
      });
      setProvedoresState(res.data.results || res.data);

      // Atualizar estatísticas
      await fetchStats();

      setShowAddModal(false);
      setAddProvedorForm({
        nome: '',
        site_oficial: '',
        endereco: '',
        email_contato: '',
        bot_mode: 'ia',
        cpf_cnpj: '',
        phone: '',
        mobile_phone: '',
        address_number: '',
        complement: '',
        province: '',
        postal_code: '',
        group_name: '',
        company: '',
        municipal_inscription: '',
        state_inscription: '',
        observations: '',
        additional_emails: '',
        notification_disabled: false,
        foreign_customer: false,
        subscription_value: 0,
        subscription_cycle: 'MONTHLY',
        subscription_billing_type: 'BOLETO',
        subscription_next_due_date: '',
        redes_sociais: {},
        nome_agente_ia: '',
        estilo_personalidade: '',
        modo_falar: '',
        uso_emojis: '',
        personalidade: '',
        taxa_adesao: '',
        inclusos_plano: '',
        multa_cancelamento: '',
        tipo_conexao: '',
        prazo_instalacao: '',
        documentos_necessarios: '',
      });
    } catch (err) {
      console.error('[DEBUG SuperadminProvedores] Erro ao criar provedor:', err);
      console.error('[DEBUG SuperadminProvedores] Resposta de erro:', err.response?.data);
      setErrorMsg('Erro ao criar provedor. Verifique os dados e tente novamente.');
    }
    setLoadingAdd(false);
  };

  const handleEditProvedorChange = (e) => {
    const { name, value, type, checked } = e.target;
    setEditProvedorForm(prev => ({
      ...prev,
      [name]: type === 'checkbox' ? checked : value
    }));
  };

  const handleEditProvedor = (provedor) => {
    setEditProvedorForm({
      id: provedor.id,
      nome: provedor.nome || '',
      site_oficial: provedor.site_oficial || '',
      endereco: provedor.endereco || '',
      email_contato: provedor.email_contato || '',
      bot_mode: provedor.bot_mode || 'ia',
      cpf_cnpj: provedor.cpf_cnpj || '',
      phone: provedor.phone || '',
      mobile_phone: provedor.mobile_phone || '',
      address_number: provedor.address_number || '',
      complement: provedor.complement || '',
      province: provedor.province || '',
      postal_code: provedor.postal_code || '',
      group_name: provedor.group_name || '',
      company: provedor.company || '',
      municipal_inscription: provedor.municipal_inscription || '',
      state_inscription: provedor.state_inscription || '',
      observations: provedor.observations || '',
      additional_emails: provedor.additional_emails || '',
      notification_disabled: provedor.notification_disabled || false,
      foreign_customer: provedor.foreign_customer || false,
      // Subscription Data
      asaas_subscription_id: provedor.asaas_subscription_id || '',
      subscription_value: provedor.subscription_value || 0,
      subscription_cycle: provedor.subscription_cycle || 'MONTHLY',
      subscription_billing_type: provedor.subscription_billing_type || 'BOLETO',
      subscription_status: provedor.subscription_status || '',
      subscription_next_due_date: provedor.subscription_next_due_date || '',
    });
    setSubscriptionPayments([]); // Limpar antes de carregar
    if (provedor.asaas_subscription_id) {
      fetchSubscriptionPayments(provedor.id);
    }
    setShowEditModal(true);
    setMenuId(null);
  };

  const fetchSubscriptionPayments = async (provedorId) => {
    setLoadingPayments(true);
    try {
      const token = localStorage.getItem('token');
      const res = await axios.get(`/api/provedores/${provedorId}/subscription_payments/`, {
        headers: { Authorization: `Token ${token}` }
      });
      if (res.data.success) {
        setSubscriptionPayments(res.data.data);
      }
    } catch (err) {
      console.error('Erro ao buscar cobranças:', err);
    } finally {
      setLoadingPayments(false);
    }
  };

  const handleSaveEdit = async (e) => {
    e.preventDefault();
    setLoadingEdit(true);
    setErrorMsg('');

    try {
      const token = localStorage.getItem('token');
      await axios.patch(`/api/provedores/${editProvedorForm.id}/`, editProvedorForm, {
        headers: { Authorization: `Token ${token}` }
      });

      // Atualizar lista
      const res = await axios.get('/api/provedores/', {
        headers: { Authorization: `Token ${token}` }
      });
      setProvedoresState(res.data.results || res.data);

      setShowEditModal(false);
      alert('Provedor atualizado com sucesso!');
    } catch (err) {
      console.error('Erro ao editar provedor:', err);
      setErrorMsg('Erro ao atualizar provedor. Verifique os dados.');
    } finally {
      setLoadingEdit(false);
    }
  };

  const handleSyncAsaas = async () => {
    setLoadingEdit(true);
    setErrorMsg('');

    try {
      const token = localStorage.getItem('token');
      const response = await axios.post(`/api/provedores/${editProvedorForm.id}/sync_asaas/`, editProvedorForm, {
        headers: { Authorization: `Token ${token}` }
      });

      if (response.data.success) {
        alert('Provedor sincronizado com sucesso no Asaas!');
        
        // Atualizar lista
        const res = await axios.get('/api/provedores/', {
          headers: { Authorization: `Token ${token}` }
        });
        setProvedoresState(res.data.results || res.data);

        // Atualizar form de edição com o novo ID do cliente Asaas
        setEditProvedorForm(prev => ({
          ...prev,
          asaas_customer_id: response.data.customer_id
        }));
      }
    } catch (err) {
      console.error('Erro ao sincronizar com Asaas:', err);
      setErrorMsg(err.response?.data?.error || 'Erro ao sincronizar cliente. Verifique o CPF/CNPJ e outros dados.');
    } finally {
      setLoadingEdit(false);
    }
  };

  const handleCreateSubscription = async (e) => {
    e.preventDefault();
    setLoadingEdit(true);
    setErrorMsg('');

    try {
      const token = localStorage.getItem('token');
      const response = await axios.post(`/api/provedores/${editProvedorForm.id}/create_subscription/`, {
        value: editProvedorForm.subscription_value,
        cycle: editProvedorForm.subscription_cycle,
        billingType: editProvedorForm.subscription_billing_type,
        nextDueDate: editProvedorForm.subscription_next_due_date, // Novo campo necessário
      }, {
        headers: { Authorization: `Token ${token}` }
      });

      if (response.data.success) {
        alert('Assinatura criada com sucesso!');
        // Atualizar lista
        const res = await axios.get('/api/provedores/', {
          headers: { Authorization: `Token ${token}` }
        });
        setProvedoresState(res.data.results || res.data);
        
        // Atualizar form de edição com o novo status
        const updatedProvedor = (res.data.results || res.data).find(p => p.id === editProvedorForm.id);
        if (updatedProvedor) {
          setEditProvedorForm(prev => ({
            ...prev,
            asaas_subscription_id: updatedProvedor.asaas_subscription_id,
            subscription_status: updatedProvedor.subscription_status
          }));
        }
      }
    } catch (err) {
      console.error('Erro ao criar assinatura:', err);
      setErrorMsg(err.response?.data?.error || 'Erro ao criar assinatura. Verifique os dados.');
    } finally {
      setLoadingEdit(false);
    }
  };

  const handleVerifyAsaas = async () => {
    setLoadingEdit(true);
    setErrorMsg('');

    try {
      const token = localStorage.getItem('token');
      const response = await axios.post(`/api/provedores/${editProvedorForm.id}/verify_asaas/`, {}, {
        headers: { Authorization: `Token ${token}` }
      });

      if (response.data.success) {
        const { status_info, asaas_customer_id, asaas_subscription_id, subscription_status } = response.data;
        
        // Atualizar lista local
        const res = await axios.get('/api/provedores/', {
          headers: { Authorization: `Token ${token}` }
        });
        setProvedoresState(res.data.results || res.data);

        // Atualizar form de edição
        setEditProvedorForm(prev => ({
          ...prev,
          asaas_customer_id,
          asaas_subscription_id,
          subscription_status
        }));

        alert(`Verificação concluída.\nCliente: ${status_info.customer}\nAssinatura: ${status_info.subscription}`);
      }
    } catch (err) {
      console.error('Erro ao verificar status Asaas:', err);
      setErrorMsg('Erro ao verificar status no Asaas.');
    } finally {
      setLoadingEdit(false);
    }
  };

  const handleAlterarStatus = async (provedorId, novoStatus) => {
    const statusLabels = {
      'ativo': 'Ativo',
      'suspenso': 'Suspenso'
    };

    if (!window.confirm(`Tem certeza que deseja alterar o status para "${statusLabels[novoStatus]}"?`)) return;

    try {
      const token = localStorage.getItem('token');
      await axios.patch(`/api/provedores/${provedorId}/`, {
        status: novoStatus
      }, {
        headers: { Authorization: `Token ${token}` }
      });

      // Atualizar lista
      setProvedoresState(prev => prev.map(p =>
        p.id === provedorId ? { ...p, status: novoStatus } : p
      ));

      alert(`Status alterado para "${statusLabels[novoStatus]}" com sucesso!`);

    } catch (err) {
      alert('Erro ao alterar status do provedor!');
    }
  };

  const handleDeleteProvedor = async (id) => {
    if (!confirm('Tem certeza que deseja excluir este provedor?')) return;

    try {
      const token = localStorage.getItem('token');
      await axios.delete(`/api/provedores/${id}/`, {
        headers: { Authorization: `Token ${token}` }
      });

      // Atualizar lista após excluir
      const res = await axios.get('/api/provedores/', {
        headers: { Authorization: `Token ${token}` }
      });
      setProvedoresState(res.data.results || res.data);

      // Atualizar estatísticas
      await fetchStats();
    } catch (err) {
      alert('Erro ao excluir provedor!');
    }
  };

  // Função para abrir modal de limpeza
  const handleOpenLimpezaModal = (provedor) => {
    setProvedorLimpeza(provedor);
    setShowLimpezaModal(true);
    setMenuId(null); // Fechar menu de ações
  };

  // Função para executar limpeza
  const handleExecutarLimpeza = async (tipo) => {
    if (!provedorLimpeza) return;

    let confirmacao = '';
    let endpoint = '';

    if (tipo === 'banco') {
      confirmacao = `Tem certeza que deseja LIMPAR COMPLETAMENTE o banco de dados do provedor "${provedorLimpeza.nome}"?\n\n⚠️ ATENÇÃO: Esta ação removerá TODAS as conversas, mensagens e contatos deste provedor e NÃO PODE SER DESFEITA!`;
      endpoint = `/api/provedores/${provedorLimpeza.id}/limpar_banco_dados/`;
    } else if (tipo === 'redis') {
      confirmacao = `Tem certeza que deseja limpar o Redis do provedor "${provedorLimpeza.nome}"?\n\n⚠️ ATENÇÃO: Esta ação removerá todas as chaves de cache e memória deste provedor!`;
      endpoint = `/api/provedores/${provedorLimpeza.id}/limpar_redis/`;
    } else if (tipo === 'auditlog') {
      confirmacao = `Tem certeza que deseja limpar TODOS os logs de auditoria (core_auditlog) do provedor "${provedorLimpeza.nome}"?\n\n⚠️ ATENÇÃO: Esta ação removerá TODOS os registros de auditoria deste provedor e NÃO PODE SER DESFEITA!`;
      endpoint = `/api/provedores/${provedorLimpeza.id}/limpar_auditlog/`;
    }

    if (!window.confirm(confirmacao)) return;

    setLoadingLimpeza(true);
    setLimpezaResult(null);

    try {
      const token = localStorage.getItem('token');

      const response = await axios.post(endpoint, {}, {
        headers: { Authorization: `Token ${token}` }
      });

      setLimpezaResult({
        success: true,
        message: response.data.message,
        details: response.data
      });

      // Atualizar estatísticas após limpeza
      fetchStats();

    } catch (error) {
      setLimpezaResult({
        success: false,
        message: error.response?.data?.error || 'Erro ao executar limpeza',
        details: error.response?.data
      });
    } finally {
      setLoadingLimpeza(false);
    }
  };

  const handleClick = (e) => {
    if (menuId && !menuBtnRefs.current[menuId]?.contains(e.target)) {
      setMenuId(null);
    }
  };

  useEffect(() => {
    document.addEventListener('click', handleClick);
    return () => document.removeEventListener('click', handleClick);
  }, [menuId]);

  const handleOpenMenu = (provedorId) => (e) => {
    e.stopPropagation();
    const button = e.currentTarget;
    const rect = button.getBoundingClientRect();

    // Calcular se o modal vai caber na tela
    const modalHeight = 200; // Altura estimada do modal
    const windowHeight = window.innerHeight;
    const spaceBelow = windowHeight - rect.bottom;
    const spaceAbove = rect.top;

    let topPosition;
    if (spaceBelow < modalHeight && spaceAbove > modalHeight) {
      // Se não cabe embaixo, posiciona acima do botão
      topPosition = rect.top + window.scrollY - modalHeight - 10;
    } else {
      // Posiciona abaixo, mas mais para cima
      topPosition = rect.bottom + window.scrollY - 80;
    }

    setMenuPosition({
      top: topPosition,
      left: rect.left + window.scrollX - 200 // Move 200px para a esquerda
    });
    setMenuId(provedorId === menuId ? null : provedorId);
  };

  return (
    <div className="flex-1 p-6 bg-background overflow-y-auto">
      {/* Header */}
      {/* Header elegante */}
      <div className="mb-8">
        <h1 className="text-3xl font-bold text-foreground mb-2 flex items-center gap-3">
          <Wifi className="w-8 h-8 text-primary" />
          Gerenciamento de Provedores
        </h1>
        <p className="text-muted-foreground">Gerencie provedores de internet e seus dados de forma centralizada</p>
      </div>

      {/* Cards de estatísticas removidos */}

      {/* Busca e botão adicionar modernizado */}
      <div className="bg-card rounded-xl shadow-lg border border-border overflow-hidden mb-6">
        <div className="bg-gradient-to-r from-slate-900/20 to-gray-900/20 px-6 py-4 border-b border-border">
          <h3 className="text-lg font-semibold text-foreground flex items-center gap-2">
            <Search className="w-5 h-5 text-slate-400" />
            Gerenciar Provedores
          </h3>
        </div>
        <div className="p-6 flex items-center gap-4">
          <div className="relative flex-1">
            <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 text-muted-foreground w-4 h-4" />
            <input
              type="text"
              placeholder="Buscar provedores por nome, slug ou domínio..."
              value={search}
              onChange={e => setSearch(e.target.value)}
              className="w-full pl-10 pr-4 py-3 rounded-lg bg-background border border-border text-foreground focus:ring-2 focus:ring-primary/20 focus:border-primary transition-colors"
            />
          </div>
          <button
            className="flex items-center gap-2 bg-primary hover:bg-primary/90 text-white px-6 py-3 rounded-lg font-medium transition-colors shadow-lg"
            onClick={() => setShowAddModal(true)}
          >
            <Plus className="w-4 h-4" /> Adicionar Provedor
          </button>
        </div>
      </div>

      {/* Modal de adicionar provedor */}
      {showAddModal && (
        <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50 p-4">
          <div className="bg-[#23272f] rounded-xl shadow-2xl w-full max-w-4xl relative border border-border flex flex-col max-h-[90vh]">
            <div className="p-6 border-b border-border flex justify-between items-center">
              <h2 className="text-2xl font-bold text-white">Adicionar Novo Provedor</h2>
              <button className="text-gray-400 hover:text-white text-3xl" onClick={() => setShowAddModal(false)}>&times;</button>
            </div>
            
            <form onSubmit={handleAddProvedor} className="flex-1 overflow-y-auto p-8 space-y-8">
              {/* Seção 1: Dados Básicos */}
              <div>
                <h3 className="text-lg font-semibold text-primary mb-4 flex items-center gap-2">
                  <Eye className="w-5 h-5" /> Informações Básicas
                </h3>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  <div>
                    <label className="block text-xs font-semibold text-gray-400 uppercase mb-1">Nome do Provedor *</label>
                    <input type="text" name="nome" className="w-full px-4 py-2 rounded bg-[#181b20] text-white border border-border" value={addProvedorForm.nome} onChange={handleAddProvedorChange} required />
                  </div>
                  <div>
                    <label className="block text-xs font-semibold text-gray-400 uppercase mb-1">CPF ou CNPJ *</label>
                    <input type="text" name="cpf_cnpj" className="w-full px-4 py-2 rounded bg-[#181b20] text-white border border-border" value={addProvedorForm.cpf_cnpj} onChange={handleAddProvedorChange} required placeholder="Apenas números" />
                  </div>
                  <div>
                    <label className="block text-xs font-semibold text-gray-400 uppercase mb-1">Site Oficial</label>
                    <input type="url" name="site_oficial" className="w-full px-4 py-2 rounded bg-[#181b20] text-white border border-border" value={addProvedorForm.site_oficial} onChange={handleAddProvedorChange} />
                  </div>
                  <div>
                    <label className="block text-xs font-semibold text-gray-400 uppercase mb-1">E-mail de Contato</label>
                    <input type="email" name="email_contato" className="w-full px-4 py-2 rounded bg-[#181b20] text-white border border-border" value={addProvedorForm.email_contato} onChange={handleAddProvedorChange} />
                  </div>
                  <div>
                    <label className="block text-xs font-semibold text-gray-400 uppercase mb-1">Telefone Celular</label>
                    <input type="text" name="mobile_phone" className="w-full px-4 py-2 rounded bg-[#181b20] text-white border border-border" value={addProvedorForm.mobile_phone} onChange={handleAddProvedorChange} />
                  </div>
                  <div>
                    <label className="block text-xs font-semibold text-gray-400 uppercase mb-1">Modo de Atendimento *</label>
                    <select name="bot_mode" className="w-full px-4 py-2 rounded bg-[#181b20] text-white border border-border" value={addProvedorForm.bot_mode} onChange={handleAddProvedorChange} required>
                      <option value="ia">Inteligência Artificial (IA)</option>
                      <option value="chatbot">Fluxo de Chatbot</option>
                    </select>
                  </div>
                </div>
              </div>

              {/* Seção 2: Endereço */}
              <div>
                <h3 className="text-lg font-semibold text-primary mb-4 flex items-center gap-2">
                  <Database className="w-5 h-5" /> Localização
                </h3>
                <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                  <div>
                    <label className="block text-xs font-semibold text-gray-400 uppercase mb-1">CEP</label>
                    <input type="text" name="postal_code" className="w-full px-4 py-2 rounded bg-[#181b20] text-white border border-border" value={addProvedorForm.postal_code} onChange={handleAddProvedorChange} />
                  </div>
                  <div className="md:col-span-2">
                    <label className="block text-xs font-semibold text-gray-400 uppercase mb-1">Logradouro (Endereço)</label>
                    <input type="text" name="endereco" className="w-full px-4 py-2 rounded bg-[#181b20] text-white border border-border" value={addProvedorForm.endereco} onChange={handleAddProvedorChange} />
                  </div>
                  <div>
                    <label className="block text-xs font-semibold text-gray-400 uppercase mb-1">Número</label>
                    <input type="text" name="address_number" className="w-full px-4 py-2 rounded bg-[#181b20] text-white border border-border" value={addProvedorForm.address_number} onChange={handleAddProvedorChange} />
                  </div>
                  <div>
                    <label className="block text-xs font-semibold text-gray-400 uppercase mb-1">Bairro</label>
                    <input type="text" name="province" className="w-full px-4 py-2 rounded bg-[#181b20] text-white border border-border" value={addProvedorForm.province} onChange={handleAddProvedorChange} />
                  </div>
                  <div>
                    <label className="block text-xs font-semibold text-gray-400 uppercase mb-1">Complemento</label>
                    <input type="text" name="complement" className="w-full px-4 py-2 rounded bg-[#181b20] text-white border border-border" value={addProvedorForm.complement} onChange={handleAddProvedorChange} />
                  </div>
                </div>
              </div>

              {/* Seção 3: Faturamento / Asaas */}
              <div>
                <h3 className="text-lg font-semibold text-primary mb-4 flex items-center gap-2">
                  <FileText className="w-5 h-5" /> Detalhes Financeiros (Asaas)
                </h3>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  <div>
                    <label className="block text-xs font-semibold text-gray-400 uppercase mb-1">Nome da Empresa (Asaas)</label>
                    <input type="text" name="company" className="w-full px-4 py-2 rounded bg-[#181b20] text-white border border-border" value={addProvedorForm.company} onChange={handleAddProvedorChange} />
                  </div>
                  <div>
                    <label className="block text-xs font-semibold text-gray-400 uppercase mb-1">Grupo</label>
                    <input type="text" name="group_name" className="w-full px-4 py-2 rounded bg-[#181b20] text-white border border-border" value={addProvedorForm.group_name} onChange={handleAddProvedorChange} />
                  </div>
                  <div>
                    <label className="block text-xs font-semibold text-gray-400 uppercase mb-1">Inscrição Estadual</label>
                    <input type="text" name="state_inscription" className="w-full px-4 py-2 rounded bg-[#181b20] text-white border border-border" value={addProvedorForm.state_inscription} onChange={handleAddProvedorChange} />
                  </div>
                  <div>
                    <label className="block text-xs font-semibold text-gray-400 uppercase mb-1">Inscrição Municipal</label>
                    <input type="text" name="municipal_inscription" className="w-full px-4 py-2 rounded bg-[#181b20] text-white border border-border" value={addProvedorForm.municipal_inscription} onChange={handleAddProvedorChange} />
                  </div>
                  <div className="md:col-span-2">
                    <label className="block text-xs font-semibold text-gray-400 uppercase mb-1">E-mails Adicionais (separados por vírgula)</label>
                    <input type="text" name="additional_emails" className="w-full px-4 py-2 rounded bg-[#181b20] text-white border border-border" value={addProvedorForm.additional_emails} onChange={handleAddProvedorChange} />
                  </div>
                  <div className="flex items-center gap-6 md:col-span-2 py-2">
                    <label className="flex items-center gap-2 cursor-pointer group">
                      <input type="checkbox" name="notification_disabled" checked={addProvedorForm.notification_disabled} onChange={handleAddProvedorChange} className="w-4 h-4 rounded border-border bg-[#181b20] text-primary focus:ring-primary/20" />
                      <span className="text-sm text-gray-300 group-hover:text-white transition-colors">Desativar Notificações Asaas</span>
                    </label>
                    <label className="flex items-center gap-2 cursor-pointer group">
                      <input type="checkbox" name="foreign_customer" checked={addProvedorForm.foreign_customer} onChange={handleAddProvedorChange} className="w-4 h-4 rounded border-border bg-[#181b20] text-primary focus:ring-primary/20" />
                      <span className="text-sm text-gray-300 group-hover:text-white transition-colors">Cliente Estrangeiro</span>
                    </label>
                  </div>
                  <div className="md:col-span-2">
                    <label className="block text-xs font-semibold text-gray-400 uppercase mb-1">Observações</label>
                    <textarea name="observations" rows="2" className="w-full px-4 py-2 rounded bg-[#181b20] text-white border border-border" value={addProvedorForm.observations} onChange={handleAddProvedorChange}></textarea>
                  </div>
                  
                  {/* Bloco de Assinatura Automática */}
                  <div className="md:col-span-2 mt-4 p-4 border border-primary/20 bg-primary/5 rounded-xl">
                    <h4 className="font-semibold text-white mb-4 flex items-center gap-2">
                      <TrendingUp className="w-4 h-4 text-primary" />
                      Setup Automático de Assinatura
                    </h4>
                    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
                      <div>
                        <label className="block text-[10px] font-bold text-gray-400 uppercase mb-1">Valor Mensal (R$)</label>
                        <input type="number" name="subscription_value" className="w-full px-3 py-1.5 rounded bg-[#131517] text-white border border-border focus:border-primary" value={addProvedorForm.subscription_value} onChange={handleAddProvedorChange} />
                      </div>
                      <div>
                        <label className="block text-[10px] font-bold text-gray-400 uppercase mb-1">Ciclo</label>
                        <select name="subscription_cycle" className="w-full px-3 py-1.5 rounded bg-[#131517] text-white border border-border focus:border-primary" value={addProvedorForm.subscription_cycle} onChange={handleAddProvedorChange}>
                          <option value="WEEKLY">Semanal</option>
                          <option value="BIWEEKLY">Quinzenal</option>
                          <option value="MONTHLY">Mensal</option>
                          <option value="YEARLY">Anual</option>
                        </select>
                      </div>
                      <div>
                        <label className="block text-[10px] font-bold text-gray-400 uppercase mb-1">Pagamento</label>
                        <select name="subscription_billing_type" className="w-full px-3 py-1.5 rounded bg-[#131517] text-white border border-border focus:border-primary" value={addProvedorForm.subscription_billing_type} onChange={handleAddProvedorChange}>
                          <option value="BOLETO">Boleto</option>
                          <option value="CREDIT_CARD">Cartão de Crédito</option>
                          <option value="PIX">PIX</option>
                        </select>
                      </div>
                      <div>
                        <label className="block text-[10px] font-bold text-gray-400 uppercase mb-1">1º Vencimento</label>
                        <input type="date" name="subscription_next_due_date" className="w-full px-3 py-1.5 rounded bg-[#131517] text-white border border-border focus:border-primary" value={addProvedorForm.subscription_next_due_date} onChange={handleAddProvedorChange} />
                      </div>
                    </div>
                  </div>
                </div>
              </div>

              {errorMsg && <div className="text-red-400 text-sm bg-red-400/10 p-3 rounded-lg border border-red-400/20">{errorMsg}</div>}
              
              <div className="flex justify-end gap-3 pt-4 sticky bottom-0 bg-[#23272f] pb-2">
                <button type="button" onClick={() => setShowAddModal(false)} className="px-6 py-2 rounded-lg font-bold text-gray-400 hover:bg-white/5 transition">Cancelar</button>
                <button type="submit" className="bg-primary text-white px-8 py-2 rounded-lg font-bold hover:bg-primary/80 transition shadow-lg disabled:opacity-50" disabled={loadingAdd}>
                  {loadingAdd ? 'Adicionando...' : 'Adicionar Provedor'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Modal de editar provedor */}
      {showEditModal && (
        <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50 p-4">
          <div className="bg-[#23272f] rounded-xl shadow-2xl w-full max-w-4xl relative border border-border flex flex-col max-h-[90vh]">
            <div className="p-6 border-b border-border flex justify-between items-center">
              <h2 className="text-2xl font-bold text-white">Editar Provedor</h2>
              <button className="text-gray-400 hover:text-white text-3xl" onClick={() => setShowEditModal(false)}>&times;</button>
            </div>
            
            <form onSubmit={handleSaveEdit} className="flex-1 overflow-y-auto p-8 space-y-8">
              {/* Seção 1: Dados Básicos */}
              <div>
                <h3 className="text-lg font-semibold text-primary mb-4 flex items-center gap-2">
                  <Eye className="w-5 h-5" /> Informações Básicas
                </h3>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  <div>
                    <label className="block text-xs font-semibold text-gray-400 uppercase mb-1">Nome do Provedor *</label>
                    <input type="text" name="nome" className="w-full px-4 py-2 rounded bg-[#181b20] text-white border border-border" value={editProvedorForm.nome} onChange={handleEditProvedorChange} required />
                  </div>
                  <div>
                    <label className="block text-xs font-semibold text-gray-400 uppercase mb-1">CPF ou CNPJ *</label>
                    <input type="text" name="cpf_cnpj" className="w-full px-4 py-2 rounded bg-[#181b20] text-white border border-border" value={editProvedorForm.cpf_cnpj} onChange={handleEditProvedorChange} required placeholder="Apenas números" />
                  </div>
                  <div>
                    <label className="block text-xs font-semibold text-gray-400 uppercase mb-1">Site Oficial</label>
                    <input type="url" name="site_oficial" className="w-full px-4 py-2 rounded bg-[#181b20] text-white border border-border" value={editProvedorForm.site_oficial} onChange={handleEditProvedorChange} />
                  </div>
                  <div>
                    <label className="block text-xs font-semibold text-gray-400 uppercase mb-1">E-mail de Contato</label>
                    <input type="email" name="email_contato" className="w-full px-4 py-2 rounded bg-[#181b20] text-white border border-border" value={editProvedorForm.email_contato} onChange={handleEditProvedorChange} />
                  </div>
                  <div>
                    <label className="block text-xs font-semibold text-gray-400 uppercase mb-1">Telefone Celular</label>
                    <input type="text" name="mobile_phone" className="w-full px-4 py-2 rounded bg-[#181b20] text-white border border-border" value={editProvedorForm.mobile_phone} onChange={handleEditProvedorChange} />
                  </div>
                  <div>
                    <label className="block text-xs font-semibold text-gray-400 uppercase mb-1">Modo de Atendimento *</label>
                    <select name="bot_mode" className="w-full px-4 py-2 rounded bg-[#181b20] text-white border border-border" value={editProvedorForm.bot_mode} onChange={handleEditProvedorChange} required>
                      <option value="ia">Inteligência Artificial (IA)</option>
                      <option value="chatbot">Fluxo de Chatbot</option>
                    </select>
                  </div>
                </div>
              </div>

              {/* Seção 2: Endereço */}
              <div>
                <h3 className="text-lg font-semibold text-primary mb-4 flex items-center gap-2">
                  <Database className="w-5 h-5" /> Localização
                </h3>
                <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                  <div>
                    <label className="block text-xs font-semibold text-gray-400 uppercase mb-1">CEP</label>
                    <input type="text" name="postal_code" className="w-full px-4 py-2 rounded bg-[#181b20] text-white border border-border" value={editProvedorForm.postal_code} onChange={handleEditProvedorChange} />
                  </div>
                  <div className="md:col-span-2">
                    <label className="block text-xs font-semibold text-gray-400 uppercase mb-1">Logradouro (Endereço)</label>
                    <input type="text" name="endereco" className="w-full px-4 py-2 rounded bg-[#181b20] text-white border border-border" value={editProvedorForm.endereco} onChange={handleEditProvedorChange} />
                  </div>
                  <div>
                    <label className="block text-xs font-semibold text-gray-400 uppercase mb-1">Número</label>
                    <input type="text" name="address_number" className="w-full px-4 py-2 rounded bg-[#181b20] text-white border border-border" value={editProvedorForm.address_number} onChange={handleEditProvedorChange} />
                  </div>
                  <div>
                    <label className="block text-xs font-semibold text-gray-400 uppercase mb-1">Bairro</label>
                    <input type="text" name="province" className="w-full px-4 py-2 rounded bg-[#181b20] text-white border border-border" value={editProvedorForm.province} onChange={handleEditProvedorChange} />
                  </div>
                  <div>
                    <label className="block text-xs font-semibold text-gray-400 uppercase mb-1">Complemento</label>
                    <input type="text" name="complement" className="w-full px-4 py-2 rounded bg-[#181b20] text-white border border-border" value={editProvedorForm.complement} onChange={handleEditProvedorChange} />
                  </div>
                </div>
              </div>

              {/* Seção 3: Faturamento / Asaas */}
              <div>
                <h3 className="text-lg font-semibold text-primary mb-4 flex items-center gap-2">
                  <FileText className="w-5 h-5" /> Detalhes Financeiros (Asaas)
                </h3>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  <div>
                    <label className="block text-xs font-semibold text-gray-400 uppercase mb-1">Nome da Empresa (Asaas)</label>
                    <input type="text" name="company" className="w-full px-4 py-2 rounded bg-[#181b20] text-white border border-border" value={editProvedorForm.company} onChange={handleEditProvedorChange} />
                  </div>
                  <div>
                    <label className="block text-xs font-semibold text-gray-400 uppercase mb-1">Grupo</label>
                    <input type="text" name="group_name" className="w-full px-4 py-2 rounded bg-[#181b20] text-white border border-border" value={editProvedorForm.group_name} onChange={handleEditProvedorChange} />
                  </div>
                  <div className="md:col-span-2">
                    <label className="block text-xs font-semibold text-gray-400 uppercase mb-1">E-mails Adicionais (separados por vírgula)</label>
                    <input type="text" name="additional_emails" className="w-full px-4 py-2 rounded bg-[#181b20] text-white border border-border" value={editProvedorForm.additional_emails} onChange={handleEditProvedorChange} />
                  </div>
                  
                  {/* Bloco de Assinatura */}
                  <div className="md:col-span-2 mt-4 p-4 border border-primary/20 bg-primary/5 rounded-xl">
                    <h4 className="font-semibold text-white mb-4 flex items-center gap-2">
                      <TrendingUp className="w-4 h-4 text-primary" />
                      Gestão de Assinatura (Recorrência)
                    </h4>
                    
                    {editProvedorForm.asaas_subscription_id ? (
                      <div className="flex flex-col gap-4">
                        <div className="bg-green-500/10 border border-green-500/20 p-4 rounded-lg flex justify-between items-center">
                          <div>
                            <p className="text-sm font-bold text-green-400">Assinatura Ativa: {editProvedorForm.asaas_subscription_id}</p>
                            <p className="text-xs text-gray-400 mt-1">Status: <span className="uppercase">{editProvedorForm.subscription_status}</span></p>
                            <p className="text-xs text-gray-400">Valor: R$ {editProvedorForm.subscription_value} ({editProvedorForm.subscription_cycle})</p>
                          </div>
                          <CheckCircle2 className="w-8 h-8 text-green-500" />
                        </div>
                        <button 
                          type="button" 
                          onClick={handleVerifyAsaas} 
                          className="flex items-center justify-center gap-2 text-xs text-gray-400 hover:text-white transition-colors"
                          disabled={loadingEdit}
                        >
                          <RefreshCw className={`w-3 h-3 ${loadingEdit ? 'animate-spin' : ''}`} />
                          Verificar/Atualizar Status no Asaas
                        </button>

                        {/* Histórico de Cobranças */}
                        <div className="mt-6 border-t border-border/30 pt-4">
                          <h5 className="text-[10px] font-bold text-gray-500 uppercase mb-3 tracking-wider">Histórico de Cobranças</h5>
                          
                          {loadingPayments ? (
                            <div className="py-4 flex flex-col items-center justify-center gap-2 text-gray-500">
                              <RefreshCw className="w-5 h-5 animate-spin" />
                              <span className="text-xs">Carregando faturas...</span>
                            </div>
                          ) : subscriptionPayments.length > 0 ? (
                            <div className="space-y-2 max-h-60 overflow-y-auto pr-1 scrollbar-thin scrollbar-thumb-white/10">
                              {subscriptionPayments.map(payment => (
                                <div key={payment.id} className="flex items-center justify-between p-3 rounded-lg bg-black/20 border border-white/5 hover:border-primary/30 transition-colors">
                                  <div className="flex items-center gap-3">
                                    <div className={`p-2 rounded-full ${
                                      payment.status === 'RECEIVED' || payment.status === 'RECEIVED_IN_CASH' || payment.status === 'CONFIRMED' 
                                      ? 'bg-green-500/10 text-green-500' 
                                      : payment.status === 'OVERDUE' 
                                      ? 'bg-red-500/10 text-red-500'
                                      : 'bg-yellow-500/10 text-yellow-501'
                                    }`}>
                                      <FileText className="w-4 h-4" />
                                    </div>
                                    <div>
                                      <p className="text-sm font-semibold text-white">
                                        Vencimento: {new Date(payment.dueDate).toLocaleDateString('pt-BR')}
                                      </p>
                                      <p className="text-[10px] text-gray-500">
                                        R$ {payment.value} • {payment.billingType}
                                      </p>
                                    </div>
                                  </div>
                                  <div className="flex items-center gap-3">
                                    <span className={`text-[9px] font-bold px-2 py-0.5 rounded uppercase ${
                                      payment.status === 'RECEIVED' || payment.status === 'RECEIVED_IN_CASH' || payment.status === 'CONFIRMED' 
                                      ? 'bg-green-500/20 text-green-400' 
                                      : payment.status === 'OVERDUE' 
                                      ? 'bg-red-500/20 text-red-400' 
                                      : 'bg-yellow-500/20 text-yellow-400'
                                    }`}>
                                      {payment.status === 'RECEIVED' || payment.status === 'RECEIVED_IN_CASH' || payment.status === 'CONFIRMED' ? 'Pago' : 
                                       payment.status === 'OVERDUE' ? 'Vencido' : 'Pendente'}
                                    </span>
                                    {(payment.bankSlipUrl || payment.invoiceUrl) && (
                                      <a 
                                        href={payment.bankSlipUrl || payment.invoiceUrl} 
                                        target="_blank" 
                                        rel="noopener noreferrer" 
                                        className="p-1.5 hover:bg-white/10 rounded-lg transition-colors text-primary"
                                        title="Ver Boleto/Fatura"
                                      >
                                        <Database className="w-4 h-4" />
                                      </a>
                                    )}
                                  </div>
                                </div>
                              ))}
                            </div>
                          ) : (
                            <div className="py-4 text-center text-xs text-gray-500 italic">
                              Nenhuma cobrança encontrada para esta assinatura.
                            </div>
                          )}
                        </div>
                      </div>
                    ) : (
                      <div className="space-y-4">
                        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
                          <div>
                            <label className="block text-[10px] font-bold text-gray-500 uppercase mb-1">Valor Mensalidade</label>
                            <input type="number" name="subscription_value" className="w-full px-3 py-2 rounded bg-[#13151a] text-white border border-border" value={editProvedorForm.subscription_value} onChange={handleEditProvedorChange} placeholder="0.00" />
                          </div>
                          <div>
                            <label className="block text-[10px] font-bold text-gray-500 uppercase mb-1">Ciclo</label>
                            <select name="subscription_cycle" className="w-full px-3 py-2 rounded bg-[#13151a] text-white border border-border" value={editProvedorForm.subscription_cycle} onChange={handleEditProvedorChange}>
                              <option value="MONTHLY">Mensal</option>
                              <option value="QUARTERLY">Trimestral</option>
                              <option value="SEMIANNUALLY">Semestral</option>
                              <option value="YEARLY">Anual</option>
                            </select>
                          </div>
                          <div>
                            <label className="block text-[10px] font-bold text-gray-500 uppercase mb-1">Vencimento Inicial</label>
                            <input type="date" name="subscription_next_due_date" className="w-full px-3 py-2 rounded bg-[#13151a] text-white border border-border" value={editProvedorForm.subscription_next_due_date} onChange={handleEditProvedorChange} />
                          </div>
                          <div>
                            <label className="block text-[10px] font-bold text-gray-500 uppercase mb-1">Meio de Pagamento</label>
                            <select name="subscription_billing_type" className="w-full px-3 py-2 rounded bg-[#13151a] text-white border border-border" value={editProvedorForm.subscription_billing_type} onChange={handleEditProvedorChange}>
                              <option value="BOLETO">Boleto</option>
                              <option value="PIX">PIX</option>
                              <option value="CREDIT_CARD">Cartão de Crédito</option>
                            </select>
                          </div>
                        </div>
                        {editProvedorForm.asaas_customer_id ? (
                          <button 
                            type="button" 
                            onClick={handleCreateSubscription}
                            disabled={loadingEdit}
                            className="w-full bg-primary hover:bg-primary/80 text-white py-2 rounded-lg font-bold transition shadow-lg disabled:opacity-50"
                          >
                            {loadingEdit ? 'Processando...' : 'Criar Assinatura Recorrente'}
                          </button>
                        ) : (
                          <button 
                            type="button" 
                            onClick={handleSyncAsaas}
                            disabled={loadingEdit}
                            className="w-full bg-blue-600 hover:bg-blue-700 text-white py-2 rounded-lg font-bold transition shadow-lg disabled:opacity-50 flex items-center justify-center gap-2"
                          >
                            <RefreshCw className={`w-4 h-4 ${loadingEdit ? 'animate-spin' : ''}`} />
                            {loadingEdit ? 'Sincronizando...' : 'Sincronizar Cliente com Asaas'}
                          </button>
                        )}
                      </div>
                    )}
                  </div>

                  <div className="flex items-center gap-6 md:col-span-2 py-2">
                    <label className="flex items-center gap-2 cursor-pointer group">
                      <input type="checkbox" name="notification_disabled" checked={editProvedorForm.notification_disabled} onChange={handleEditProvedorChange} className="w-4 h-4 rounded border-border bg-[#181b20] text-primary focus:ring-primary/20" />
                      <span className="text-sm text-gray-300 group-hover:text-white transition-colors">Desativar Notificações Asaas</span>
                    </label>
                    <label className="flex items-center gap-2 cursor-pointer group">
                      <input type="checkbox" name="foreign_customer" checked={editProvedorForm.foreign_customer} onChange={handleEditProvedorChange} className="w-4 h-4 rounded border-border bg-[#181b20] text-primary focus:ring-primary/20" />
                      <span className="text-sm text-gray-300 group-hover:text-white transition-colors">Cliente Estrangeiro</span>
                    </label>
                  </div>
                </div>
              </div>

              {errorMsg && <div className="text-red-400 text-sm bg-red-400/10 p-3 rounded-lg border border-red-400/20">{errorMsg}</div>}
              
              <div className="flex justify-end gap-3 pt-4 sticky bottom-0 bg-[#23272f] pb-2">
                <button type="button" onClick={() => setShowEditModal(false)} className="px-6 py-2 rounded-lg font-bold text-gray-400 hover:bg-white/5 transition">Cancelar</button>
                <button type="submit" className="bg-primary text-white px-8 py-2 rounded-lg font-bold hover:bg-primary/80 transition shadow-lg disabled:opacity-50" disabled={loadingEdit}>
                  {loadingEdit ? 'Salvando...' : 'Salvar Alterações'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Tabela de provedores modernizada */}
      <div className="bg-card rounded-xl shadow-lg border border-border overflow-hidden">
        <div className="bg-gradient-to-r from-slate-900/20 to-gray-900/20 px-6 py-4 border-b border-border">
          <h3 className="text-lg font-semibold text-foreground flex items-center gap-2">
            <Users className="w-5 h-5 text-slate-400" />
            Lista de Provedores
          </h3>
        </div>
        <div className="overflow-x-auto">
          <table className="min-w-full">
            <thead className="bg-muted/50">
              <tr>
                <th className="px-6 py-4 text-center text-xs font-semibold text-foreground uppercase tracking-wider">ID</th>
                <th className="px-6 py-4 text-left text-xs font-semibold text-foreground uppercase tracking-wider">PROVEDOR</th>
                <th className="px-6 py-4 text-center text-xs font-semibold text-foreground uppercase tracking-wider">CANAL</th>
                <th className="px-6 py-4 text-center text-xs font-semibold text-foreground uppercase tracking-wider">USUÁRIOS</th>
                <th className="px-6 py-4 text-center text-xs font-semibold text-foreground uppercase tracking-wider">CONVERSAS</th>
                <th className="px-6 py-4 text-center text-xs font-semibold text-foreground uppercase tracking-wider">MODO</th>
                <th className="px-6 py-4 text-center text-xs font-semibold text-foreground uppercase tracking-wider">STATUS</th>
                <th className="px-6 py-4 text-center text-xs font-semibold text-foreground uppercase tracking-wider">AÇÕES</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {filteredProvedores.map(provedor => (
                <tr key={provedor.id} className="hover:bg-muted/50">
                  <td className="px-6 py-4 text-center align-middle">
                    <span className="inline-flex items-center justify-center w-8 h-8 bg-blue-100 text-blue-800 rounded-full text-sm font-semibold">
                      {provedor.id}
                    </span>
                  </td>
                  <td className="px-6 py-4 min-w-[220px] align-middle">
                    <div className="flex items-center gap-3">
                      <div className="w-10 h-10 rounded-full bg-blue-900 flex items-center justify-center">
                        <Wifi className="w-5 h-5 text-white" />
                      </div>
                      <div>
                        <div className="font-semibold text-card-foreground">{provedor.nome}</div>
                        <div className="text-xs text-muted-foreground">{provedor.site_oficial || provedor.email_contato}</div>
                      </div>
                    </div>
                  </td>
                  <td className="px-6 py-4 text-center align-middle text-foreground">
                    {provedor.channels_count || 0}
                  </td>
                  <td className="px-6 py-4 text-center align-middle text-foreground">
                    {provedor.users_count || 0}
                  </td>
                  <td className="px-6 py-4 text-center align-middle">
                    <span className="inline-flex items-center gap-1 justify-center w-full text-foreground">
                      <MessageCircle className="w-4 h-4 text-muted-foreground" />
                      {provedor.conversations_count?.toLocaleString('pt-BR') || 0}
                    </span>
                  </td>
                  <td className="px-6 py-4 text-center align-middle">
                    <span className={`px-2 py-1 rounded text-[10px] font-bold uppercase ${provedor.bot_mode === 'ia' ? 'bg-purple-100 text-purple-700' : 'bg-blue-100 text-blue-700'}`}>
                      {provedor.bot_mode === 'ia' ? 'IA' : 'Chatbot'}
                    </span>
                  </td>
                  <td className="px-6 py-4 text-center align-middle">
                    <button
                      className={`px-3 py-1 rounded-full text-xs font-semibold focus:outline-none transition-colors duration-200 ${provedor.is_active !== false ? 'bg-green-100 text-green-800' : 'bg-red-100 text-red-800'}`}
                      style={{ cursor: 'pointer' }}
                      onClick={async (e) => {
                        e.stopPropagation();
                        try {
                          const token = localStorage.getItem('token');
                          await axios.patch(`/api/provedores/${provedor.id}/`, { is_active: !provedor.is_active }, {
                            headers: { Authorization: `Token ${token}` }
                          });
                          // Atualizar lista após toggle
                          const res = await axios.get('/api/provedores/', {
                            headers: { Authorization: `Token ${token}` }
                          });
                          setProvedoresState(res.data.results || res.data);
                        } catch (err) {
                          alert('Erro ao alterar status do provedor!');
                        }
                      }}
                    >
                      {provedor.is_active !== false ? 'Ativo' : 'Suspenso'}
                    </button>
                  </td>
                  <td className="px-6 py-4 text-center align-middle relative" style={{ overflow: 'visible' }}>
                    <button ref={el => (menuBtnRefs.current[provedor.id] = el)} className="p-1 hover:bg-muted rounded" onClick={handleOpenMenu(provedor.id)}>
                      <MoreVertical className="w-5 h-5" />
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {/* Menu de ações */}
      {menuId && menuBtnRefs.current[menuId] && ReactDOM.createPortal(
        <div
          className="bg-card border rounded shadow z-[9999] min-w-[170px] flex flex-col w-max fixed"
          style={{ top: menuPosition.top, left: menuPosition.left }}
        >
          <button className="flex items-center gap-2 w-full px-3 py-1.5 text-left hover:bg-muted text-sm" onClick={e => { e.stopPropagation(); handleEditProvedor(filteredProvedores.find(p => p.id === menuId)); setMenuId(null); }}>
            <Eye className="w-4 h-4 text-blue-400" /> Ver Detalhes
          </button>
          <button 
            className={`flex items-center gap-2 w-full px-3 py-1.5 text-left hover:bg-muted text-sm border-y border-border/50 ${filteredProvedores.find(p => p.id === menuId)?.asaas_customer_id ? 'text-green-500' : 'text-orange-500'}`}
            onClick={e => { e.stopPropagation(); handleSyncAsaas(menuId); setMenuId(null); }}
          >
            <Database className="w-4 h-4" /> 
            {filteredProvedores.find(p => p.id === menuId)?.asaas_customer_id ? 'Re-sincronizar Asaas' : 'Sincronizar Asaas'}
          </button>
          <button className="flex items-center gap-2 w-full px-3 py-1.5 text-left hover:bg-muted text-sm" onClick={e => { e.stopPropagation(); handleEditProvedor(filteredProvedores.find(p => p.id === menuId)); setMenuId(null); }}>
            <Edit className="w-4 h-4" /> Editar
          </button>
          <div className="border-t border-border my-1"></div>
          <button className="flex items-center gap-2 w-full px-3 py-1.5 text-left text-orange-600 hover:bg-muted text-sm" onClick={e => { e.stopPropagation(); handleOpenLimpezaModal(filteredProvedores.find(p => p.id === menuId)); setMenuId(null); }}>
            <Database className="w-4 h-4" /> Limpeza de Dados
          </button>
          <button className="flex items-center gap-2 w-full px-3 py-1.5 text-left text-red-600 hover:bg-muted text-sm" onClick={e => { e.stopPropagation(); handleDeleteProvedor(menuId); setMenuId(null); }}>
            <Trash2 className="w-4 h-4" /> Excluir
          </button>
        </div>,
        document.body
      )}

      {/* Modal de Limpeza de Dados */}
      {showLimpezaModal && provedorLimpeza && (
        <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50">
          <div className="bg-[#23272f] rounded-xl shadow-2xl p-8 w-full max-w-lg relative border border-border">
            <button className="absolute top-2 right-2 text-gray-400 hover:text-white text-2xl" onClick={() => { setShowLimpezaModal(false); setProvedorLimpeza(null); setLimpezaResult(null); }}>&times;</button>

            <h2 className="text-2xl font-bold mb-6 text-white flex items-center gap-3">
              <Database className="w-6 h-6 text-orange-500" />
              Limpeza de Dados - {provedorLimpeza.nome}
            </h2>

            <div className="space-y-6">
              <div className="bg-orange-900/20 border border-orange-500/30 rounded-lg p-4">
                <p className="text-orange-200 text-sm">
                  ⚠️ <strong>ATENÇÃO:</strong> As ações de limpeza são irreversíveis e podem afetar o funcionamento do sistema.
                </p>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                {/* Limpeza do Banco de Dados */}
                <div className="bg-red-900/20 border border-red-500/30 rounded-lg p-4">
                  <h3 className="font-semibold text-red-200 mb-2 flex items-center gap-2">
                    <Database className="w-4 h-4" />
                    Banco de Dados
                  </h3>
                  <p className="text-red-300 text-xs mb-3">
                    Remove TODAS as conversas, mensagens e contatos deste provedor
                  </p>
                  <button
                    onClick={() => handleExecutarLimpeza('banco')}
                    disabled={loadingLimpeza}
                    className="w-full bg-red-600 hover:bg-red-700 text-white py-2 px-4 rounded text-sm font-medium disabled:opacity-50 disabled:cursor-not-allowed"
                  >
                    {loadingLimpeza ? 'Executando...' : 'Limpar Banco de Dados'}
                  </button>
                </div>

                {/* Limpeza do Redis */}
                <div className="bg-yellow-900/20 border border-yellow-500/30 rounded-lg p-4">
                  <h3 className="font-semibold text-yellow-200 mb-2 flex items-center gap-2">
                    <Trash className="w-4 h-4" />
                    Cache Redis
                  </h3>
                  <p className="text-yellow-300 text-xs mb-3">
                    Remove todas as chaves de cache e memória deste provedor
                  </p>
                  <button
                    onClick={() => handleExecutarLimpeza('redis')}
                    disabled={loadingLimpeza}
                    className="w-full bg-gradient-to-r from-orange-400 to-yellow-400 hover:from-orange-500 hover:to-yellow-500 text-white py-2 px-4 rounded text-sm font-medium disabled:opacity-50 disabled:cursor-not-allowed shadow-lg hover:shadow-xl transition-all duration-200"
                  >
                    {loadingLimpeza ? 'Executando...' : 'Limpar Redis'}
                  </button>
                </div>

                {/* Limpeza de Logs de Auditoria */}
                <div className="bg-purple-900/20 border border-purple-500/30 rounded-lg p-4">
                  <h3 className="font-semibold text-purple-200 mb-2 flex items-center gap-2">
                    <FileText className="w-4 h-4" />
                    Logs de Auditoria
                  </h3>
                  <p className="text-purple-300 text-xs mb-3">
                    Remove TODOS os logs de auditoria (core_auditlog) deste provedor
                  </p>
                  <button
                    onClick={() => handleExecutarLimpeza('auditlog')}
                    disabled={loadingLimpeza}
                    className="w-full bg-purple-600 hover:bg-purple-700 text-white py-2 px-4 rounded text-sm font-medium disabled:opacity-50 disabled:cursor-not-allowed"
                  >
                    {loadingLimpeza ? 'Executando...' : 'Limpar Auditoria'}
                  </button>
                </div>
              </div>

              {/* Resultado da operação */}
              {limpezaResult && (
                <div className={`rounded-lg p-4 border ${limpezaResult.success
                  ? 'bg-green-900/20 border-green-500/30 text-green-200'
                  : 'bg-red-900/20 border-red-500/30 text-red-200'
                  }`}>
                  <h4 className="font-semibold mb-2">
                    {limpezaResult.success ? '✅ Sucesso!' : '❌ Erro!'}
                  </h4>
                  <p className="text-sm">{limpezaResult.message}</p>
                  {limpezaResult.details && (
                    <details className="mt-2">
                      <summary className="cursor-pointer text-xs opacity-70">Ver detalhes</summary>
                      <pre className="text-xs mt-2 opacity-70 overflow-auto">
                        {JSON.stringify(limpezaResult.details, null, 2)}
                      </pre>
                    </details>
                  )}
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
} 