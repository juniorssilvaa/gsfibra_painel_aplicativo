import React, { useState, useEffect, useMemo } from 'react';
import { toast } from '../lib/notify';
import { usePageNotify } from '../lib/usePageNotify';
import { MoreVertical, CheckCircle, AlertCircle, Tag, Mail, Phone, User, ChevronDown, Download, Plus, X, MessageCircle, Globe, Search, Smartphone } from 'lucide-react';
import { Badge } from './ui/badge';
import axios from 'axios';
import whatsappIcon from '../assets/whatsapp.png';
import telegramIcon from '../assets/telegram.png';
import gmailIcon from '../assets/gmail.png';
import instagramIcon from '../assets/instagram.png';
import { isValidWhatsAppPhone, normalizeWhatsAppPhone, WHATSAPP_PHONE_ERROR } from '../utils/phoneWhatsApp';

const actions = [
  { value: '', label: '--------' },
  { value: 'delete', label: 'Excluir' }
];

export default function Contacts({ provedorId }) {
  const { showSuccess, showError, showDeleted } = usePageNotify();
  const [selected, setSelected] = useState([]);
  const [action, setAction] = useState('');
  const [showModal, setShowModal] = useState(false);
  const [showEditModal, setShowEditModal] = useState(false);
  const [editingContact, setEditingContact] = useState(null);
  const [novoContato, setNovoContato] = useState({ nome: '', telefone: '', canal: 'WhatsApp', email: '' });
  const [contatos, setContatos] = useState([]);
  const [pagination, setPagination] = useState({ next: null, previous: null, count: 0 });
  const [searchTerm, setSearchTerm] = useState('');
  const [filterBloqueados, setFilterBloqueados] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    const delayDebounceFn = setTimeout(() => {
      fetchContacts();
    }, 500);

    return () => clearTimeout(delayDebounceFn);
  }, [provedorId, searchTerm]);

  async function fetchContacts(urlToFetch = null) {
    setLoading(true);
    setError('');
    try {
      const token = localStorage.getItem('auth_token') || localStorage.getItem('token');
      let url = urlToFetch;

      if (!url) {
        url = provedorId
          ? `/api/contacts/?provedor_id=${provedorId}&page_size=100`
          : '/api/contacts/?page_size=100';

        if (searchTerm.trim()) {
          url += `&search=${encodeURIComponent(searchTerm.trim())}`;
        }
      }

      const res = await axios.get(url, {
        headers: { Authorization: `Token ${token}` }
      });

      const contactsData = res.data.results || res.data;
      setContatos(contactsData);

      if (res.data.results) {
        setPagination({
          next: res.data.next,
          previous: res.data.previous,
          count: res.data.count
        });
      }
    } catch (err) {
      setError('Erro ao carregar contatos');
      setContatos([]);
    } finally {
      setLoading(false);
    }
  }

  // Função para limpar telefone (remover @s.whatsapp.net)
  const cleanPhone = (phone) => {
    if (!phone) return '';
    return phone.replace('@s.whatsapp.net', '').replace('@lid', '');
  };

  // Função para exportar CSV
  const exportCSV = () => {
    if (contatos.length === 0) {
      toast.error('Não há contatos para exportar');
      return;
    }

    const header = ['Nome', 'Email', 'Telefone', 'Canal', 'Último Contato', 'Status'];
    const rows = contatos.map(c => [
      c.name || '',
      c.email || '',
      cleanPhone(c.phone || ''),
      c.inbox?.channel_type || '',
      c.updated_at ? new Date(c.updated_at).toLocaleDateString('pt-BR') : '',
      'Ativo' // Status padrão
    ]);
    const csv = [header, ...rows].map(r => r.join(',')).join('\n');
    const blob = new Blob([csv], { type: 'text/csv' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'contatos.csv';
    a.click();
    URL.revokeObjectURL(url);
  };

  const importCSV = async (file) => {
    if (!file) return;
    try {
      const token = localStorage.getItem('auth_token') || localStorage.getItem('token');
      if (!token) {
        toast.error('Sua sessão expirou. Faça login novamente para importar contatos.');
        return;
      }

      const form = new FormData();
      form.append('file', file);
      if (provedorId) form.append('provedor_id', String(provedorId));

      const res = await axios.post('/api/contacts/import-csv/', form, {
        headers: {
          Authorization: `Token ${token}`,
          'Content-Type': 'multipart/form-data'
        }
      });

      const { created, updated, skipped, errors } = res.data || {};
      const errCount = Array.isArray(errors) ? errors.length : 0;
      toast.success(`Importação concluída.\nCriados: ${created || 0}\nAtualizados: ${updated || 0}\nIgnorados: ${skipped || 0}\nErros: ${errCount}`);
      await fetchContacts();
    } catch (err) {
      const msg =
        err.response?.data?.error ||
        err.response?.data?.detail ||
        err.message ||
        'Erro ao importar CSV';
      toast.error(`Erro ao importar CSV: ${msg}`);
    }
  };

  // Função para adicionar novo contato
  const handleNovoContato = async (e) => {
    e.preventDefault();
    try {
      const token = localStorage.getItem('token');

      const phone = normalizeWhatsAppPhone(novoContato.telefone);
      if (!isValidWhatsAppPhone(phone)) {
        toast.error(WHATSAPP_PHONE_ERROR);
        return;
      }

      // Mapear os campos do frontend para o formato esperado pelo backend
      const contactData = {
        name: novoContato.nome.trim() || 'Sem nome',
        phone,
        email: (novoContato.email || '').trim() || null
      };
      if (provedorId) contactData.provedor = parseInt(provedorId, 10);

      const res = await axios.post('/api/contacts/', contactData, {
        headers: { Authorization: `Token ${token}` }
      });

      setContatos(prev => [...prev, res.data]);
      setShowModal(false);
      setNovoContato({ nome: '', telefone: '', canal: 'WhatsApp', email: '' });
      showSuccess('Contato criado com sucesso!');
    } catch (err) {
      toast.apiError(err, 'Erro ao criar contato.');
    }
  };

  // Função para excluir contatos selecionados (executada apenas ao clicar em "Ir")
  const handleDeleteContacts = async () => {
    if (selected.length === 0) {
      toast.error('Selecione pelo menos um contato para excluir.');
      return;
    }
    if (action !== 'delete') {
      toast.error('Selecione a ação "Excluir" no dropdown antes de clicar em "Ir".');
      return;
    }
    if (!window.confirm('Tem certeza que deseja excluir os contatos selecionados?')) return;
    try {
      const token = localStorage.getItem('auth_token') || localStorage.getItem('token');
      if (!token) {
        toast.error('Sua sessão expirou. Faça login novamente.');
        return;
      }

      const res = await axios.post('/api/contacts/bulk-delete/', { ids: selected }, {
        headers: { Authorization: `Token ${token}` }
      });

      const deletedIds = new Set(selected);
      setContatos(prev => prev.filter(c => !deletedIds.has(c.id)));
      setSelected([]);
      setAction('');
      const notFound = Array.isArray(res.data?.not_found) ? res.data.not_found.length : 0;
      showDeleted(notFound ? `Contatos excluídos. (${notFound} não encontrados)` : 'Contatos excluídos com sucesso!');
    } catch (err) {
      const msg =
        err.response?.data?.error ||
        err.response?.data?.detail ||
        err.message ||
        'Erro ao excluir contatos.';
      showError(`Erro ao excluir contatos: ${msg}`);
    }
  };

  // Função para executar ação ao clicar em "Ir"
  const handleExecuteAction = () => {
    if (selected.length === 0) {
      toast.error('Selecione pelo menos um contato.');
      return;
    }
    if (action === 'delete') {
      handleDeleteContacts();
    } else if (action === '') {
      toast.error('Selecione uma ação no dropdown.');
    }
  };

  // Função para editar contato
  const handleEditContact = async (e) => {
    e.preventDefault();
    if (!editingContact) return;

    try {
      const token = localStorage.getItem('auth_token') || localStorage.getItem('token');
      await axios.patch(`/api/contacts/${editingContact.id}/`, {
        name: editingContact.name,
        email: editingContact.email,
        phone: editingContact.phone,
        additional_attributes: {
          sender_lid: editingContact.sender_lid
        }
      }, {
        headers: { Authorization: `Token ${token}` }
      });

      // Atualizar lista de contatos
      setContatos(prev => prev.map(c =>
        c.id === editingContact.id ? {
          ...c,
          name: editingContact.name,
          email: editingContact.email,
          phone: editingContact.phone,
          additional_attributes: {
            ...c.additional_attributes,
            sender_lid: editingContact.sender_lid
          }
        } : c
      ));

      setShowEditModal(false);
      setEditingContact(null);
      showSuccess('Contato atualizado com sucesso!');
    } catch (err) {
      showError('Erro ao atualizar contato. Tente novamente.');
    }
  };

  // Função para abrir modal de edição
  const openEditModal = (contato) => {
    setEditingContact({
      id: contato.id,
      name: contato.name || '',
      email: contato.email || '',
      phone: contato.phone || '',
      sender_lid: contato.additional_attributes?.sender_lid || ''
    });
    setShowEditModal(true);
  };

  // Função para toggle de bloqueio para atendimento
  const handleToggleBlockAtender = async (contactId, currentValue) => {
    try {
      const token = localStorage.getItem('token');
      const res = await axios.patch(`/api/contacts/${contactId}/toggle-block-atender/`, {}, {
        headers: { Authorization: `Token ${token}` }
      });

      // Atualizar estado local
      setContatos(prev => prev.map(c =>
        c.id === contactId ? { ...c, bloqueado_atender: res.data.bloqueado_atender } : c
      ));

      showSuccess(res.data.message || 'Bloqueio de atendimento atualizado.');
    } catch (err) {
      showError('Erro ao alterar bloqueio de atendimento');
    }
  };


  const toggleSelect = (id) => {
    setSelected((prev) => prev.includes(id) ? prev.filter(s => s !== id) : [...prev, id]);
  };

  // Filtrar contatos por busca (nome ou número) e por bloqueio
  const filteredContatos = useMemo(() => {
    let filtered = contatos;

    // Filtrar por bloqueio primeiro
    if (filterBloqueados) {
      filtered = filtered.filter(contato => contato.bloqueado_atender === true);
    }

    // Depois filtrar por busca
    if (searchTerm.trim()) {
      const searchLower = searchTerm.toLowerCase().trim();
      filtered = filtered.filter(contato => {
        const name = (contato.name || '').toLowerCase();
        const phone = cleanPhone(contato.phone || '').toLowerCase();
        const email = (contato.email || '').toLowerCase();
        return name.includes(searchLower) || phone.includes(searchLower) || email.includes(searchLower);
      });
    }

    return filtered;
  }, [contatos, searchTerm, filterBloqueados]);

  const selectAll = () => {
    const allFilteredIds = filteredContatos.map(c => c.id);
    const allSelected = allFilteredIds.every(id => selected.includes(id));
    if (allSelected) {
      setSelected(prev => prev.filter(id => !allFilteredIds.includes(id)));
    } else {
      setSelected(prev => [...new Set([...prev, ...allFilteredIds])]);
    }
  };

  // Componente do canal com logo
  const CanalDisplay = ({ canal }) => {
    if (canal === 'whatsapp' || canal === 'whatsapp_oficial') {
      return (
        <div className="flex flex-col items-center gap-1">
          <img src={whatsappIcon} alt="WhatsApp" className="w-6 h-6" />
          <span className="text-xs text-muted-foreground">WhatsApp</span>
        </div>
      );
    }

    if (canal === 'telegram') {
      return (
        <div className="flex flex-col items-center gap-1">
          <img src={telegramIcon} alt="Telegram" className="w-6 h-6" />
          <span className="text-xs text-muted-foreground">Telegram</span>
        </div>
      );
    }

    if (canal === 'email') {
      return (
        <div className="flex flex-col items-center gap-1">
          <img src={gmailIcon} alt="Gmail" className="w-6 h-6" />
          <span className="text-xs text-muted-foreground">Gmail</span>
        </div>
      );
    }

    if (canal === 'webchat') {
      return (
        <div className="flex flex-col items-center gap-1">
          <Globe className="w-6 h-6 text-cyan-500" />
          <span className="text-xs text-muted-foreground">Web</span>
        </div>
      );
    }

    if (canal === 'instagram') {
      return (
        <div className="flex flex-col items-center gap-1">
          <img src={instagramIcon} alt="Instagram" className="w-6 h-6" />
          <span className="text-xs text-muted-foreground">Instagram</span>
        </div>
      );
    }

    if (canal === 'app_mobile') {
      return (
        <div className="flex flex-col items-center gap-1">
          <Smartphone className="w-6 h-6 text-orange-500" />
          <span className="text-xs text-muted-foreground">App</span>
        </div>
      );
    }

    return (
      <div className="flex flex-col items-center gap-1">
        <MessageCircle className="w-6 h-6 text-muted-foreground" />
        <span className="text-xs text-muted-foreground">Outro</span>
      </div>
    );
  };

  if (loading) {
    return (
      <div className="p-6">
        <div className="flex items-center justify-center h-64">
          <div className="text-muted-foreground">Carregando contatos...</div>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="p-6">
        <div className="flex items-center justify-center h-64">
          <div className="text-red-500">{error}</div>
        </div>
      </div>
    );
  }

  return (
    <div className="p-6">
      {/* Barra de ações */}
      <div className="flex items-center mb-4 gap-2 flex-wrap">
        <select
          className="border rounded px-2 py-1 text-sm bg-background text-white border-input"
          value={action}
          onChange={e => setAction(e.target.value)}
        >
          {actions.map(a => <option key={a.value} value={a.value} className="bg-background text-white">{a.label}</option>)}
        </select>
        <button
          onClick={handleExecuteAction}
          className="bg-primary text-primary-foreground px-3 py-1 rounded text-sm font-medium hover:bg-primary/90"
        >
          Ir
        </button>
        <span className="ml-2 text-xs text-muted-foreground">{selected.length} de {filteredContatos.length} selecionado(s)</span>
        <div className="flex-1" />
        {/* Campo de busca */}
        <div className="relative flex items-center">
          <Search className="absolute left-2 w-4 h-4 text-muted-foreground" />
          <input
            type="text"
            placeholder="Buscar por nome, telefone ou email..."
            value={searchTerm}
            onChange={e => setSearchTerm(e.target.value)}
            className="pl-8 pr-3 py-1 border rounded text-sm bg-background w-64 text-white border-input"
          />
        </div>
        {/* Filtro de bloqueados */}
        <label className="flex items-center gap-2 cursor-pointer px-3 py-1 border rounded text-sm bg-background hover:bg-muted transition-colors">
          <input
            type="checkbox"
            checked={filterBloqueados}
            onChange={e => setFilterBloqueados(e.target.checked)}
            className="rounded border-gray-300"
          />
          <span className="text-sm text-foreground whitespace-nowrap">Apenas bloqueados</span>
        </label>
        <button onClick={() => setShowModal(true)} className="flex items-center gap-1 bg-gradient-to-r from-orange-500 to-yellow-500 hover:from-orange-600 hover:to-yellow-600 text-white px-3 py-1 rounded text-sm font-medium shadow-lg hover:shadow-xl transition-all duration-200">
          <Plus className="w-4 h-4" /> Novo Contato
        </button>
        <button onClick={exportCSV} className="flex items-center gap-1 bg-gradient-to-r from-blue-500 to-blue-400 hover:from-blue-600 hover:to-blue-500 text-white px-3 py-1 rounded text-sm font-medium shadow-lg hover:shadow-xl transition-all duration-200">
          <Download className="w-4 h-4" /> Exportar CSV
        </button>
        <label className="flex items-center gap-1 bg-gradient-to-r from-orange-400 to-yellow-400 hover:from-orange-500 hover:to-yellow-500 text-white px-3 py-1 rounded text-sm font-medium cursor-pointer shadow-lg hover:shadow-xl transition-all duration-200">
          <Download className="w-4 h-4 rotate-180" /> Importar CSV
          <input
            type="file"
            accept=".csv,text/csv"
            className="hidden"
            onChange={(e) => {
              const f = e.target.files?.[0];
              // permitir importar o mesmo arquivo novamente
              e.target.value = '';
              importCSV(f);
            }}
          />
        </label>
      </div>

      {/* Modal Novo Contato */}
      {showModal && (
        <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50">
          <div className="bg-card p-6 rounded-lg shadow-lg w-full max-w-md relative">
            <button onClick={() => setShowModal(false)} className="absolute top-2 right-2 text-red-500 hover:text-red-600 transition-colors"><X /></button>
            <h2 className="text-lg font-bold mb-4">Novo Contato</h2>
            <form onSubmit={handleNovoContato} className="flex flex-col gap-3">
              <label className="text-sm font-medium text-white">Nome
                <input required className="mt-1 w-full border rounded px-2 py-1 bg-background text-white" value={novoContato.nome} onChange={e => setNovoContato({ ...novoContato, nome: e.target.value })} />
              </label>
              <label className="text-sm font-medium text-white">Telefone
                <input required className="mt-1 w-full border rounded px-2 py-1 bg-background text-white" value={novoContato.telefone} onChange={e => setNovoContato({ ...novoContato, telefone: e.target.value })} placeholder="DDI + número" />
              </label>
              <label className="text-sm font-medium text-white">Email (opcional)
                <input type="email" className="mt-1 w-full border rounded px-2 py-1 bg-background text-white" value={novoContato.email} onChange={e => setNovoContato({ ...novoContato, email: e.target.value })} placeholder="email@exemplo.com" />
              </label>
              <label className="text-sm font-medium text-white">Canal
                <select className="mt-1 w-full border rounded px-2 py-1 bg-background text-white" value={novoContato.canal} onChange={e => setNovoContato({ ...novoContato, canal: e.target.value })}>
                  <option value="whatsapp">WhatsApp</option>
                  <option value="telegram">Telegram</option>
                  <option value="email">Email</option>
                  <option value="webchat">Web Site</option>
                </select>
              </label>
              <button type="submit" className="bg-gradient-to-r from-orange-500 to-yellow-500 hover:from-orange-600 hover:to-yellow-600 text-white px-3 py-1 rounded text-sm font-medium mt-2 shadow-lg hover:shadow-xl transition-all duration-200">Salvar</button>
            </form>
          </div>
        </div>
      )}
      {/* Modal Editar Contato */}
      {showEditModal && editingContact && (
        <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50">
          <div className="bg-card p-6 rounded-lg shadow-lg w-full max-w-md relative">
            <button onClick={() => setShowEditModal(false)} className="absolute top-2 right-2 text-red-500 hover:text-red-600 transition-colors"><X /></button>
            <h2 className="text-lg font-bold mb-4">Editar Contato</h2>
            <form onSubmit={handleEditContact} className="flex flex-col gap-3">
              <label className="text-sm font-medium text-white">Nome
                <input required className="mt-1 w-full border rounded px-2 py-1 bg-background text-white" value={editingContact.name} onChange={e => setEditingContact({ ...editingContact, name: e.target.value })} />
              </label>
              <label className="text-sm font-medium text-white">Email
                <input className="mt-1 w-full border rounded px-2 py-1 bg-background text-white" value={editingContact.email} onChange={e => setEditingContact({ ...editingContact, email: e.target.value })} />
              </label>
              <label className="text-sm font-medium text-white">Telefone
                <input className="mt-1 w-full border rounded px-2 py-1 bg-background text-white" value={editingContact.phone} onChange={e => setEditingContact({ ...editingContact, phone: e.target.value })} />
              </label>
              <label className="text-sm font-medium text-white">Sender LID
                <input className="mt-1 w-full border rounded px-2 py-1 bg-background text-white" value={editingContact.sender_lid} onChange={e => setEditingContact({ ...editingContact, sender_lid: e.target.value })} placeholder="249666566365270@lid" />
              </label>
              <button type="submit" className="bg-gradient-to-r from-blue-500 to-blue-400 hover:from-blue-600 hover:to-blue-500 text-white px-3 py-1 rounded text-sm font-medium mt-2 shadow-lg hover:shadow-xl transition-all duration-200">Salvar Edição</button>
            </form>
          </div>
        </div>
      )}

      {/* Tabela de contatos */}
      <div className="overflow-x-auto rounded-lg shadow bg-card">
        <table className="min-w-full divide-y divide-border">
          <thead className="bg-muted">
            <tr>
              <th className="px-4 py-3 w-12">
                <input
                  type="checkbox"
                  checked={selected.length === filteredContatos.length && filteredContatos.length > 0}
                  onChange={selectAll}
                  className="rounded border-gray-300"
                />
              </th>
              <th className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wider text-white">NOME</th>
              <th className="px-4 py-3 text-center text-xs font-semibold uppercase tracking-wider text-white">CONTATO</th>
              <th className="px-4 py-3 text-center text-xs font-semibold uppercase tracking-wider text-white">CANAL</th>
              <th className="px-4 py-3 text-center text-xs font-semibold uppercase tracking-wider whitespace-nowrap text-white">ÚLTIMO CONTATO</th>
              <th className="px-4 py-3 text-center text-xs font-semibold uppercase tracking-wider text-white">ATENDER</th>
              <th className="px-4 py-3 text-center text-xs font-semibold uppercase tracking-wider w-16"></th>
            </tr>
          </thead>
          <tbody className="divide-y divide-border">
            {filteredContatos.length === 0 ? (
              <tr>
                <td colSpan="7" className="px-4 py-8 text-center text-muted-foreground">
                  {searchTerm ? 'Nenhum contato encontrado com os critérios de busca' : 'Nenhum contato encontrado'}
                </td>
              </tr>
            ) : (
              filteredContatos.map(contato => (
                <tr key={contato.id} className="hover:bg-muted/50 transition-colors">
                  <td className="px-4 py-3">
                    <input
                      type="checkbox"
                      checked={selected.includes(contato.id)}
                      onChange={() => toggleSelect(contato.id)}
                      className="rounded border-gray-300"
                    />
                  </td>
                  <td className="px-4 py-3">
                    <div className="text-sm text-white">
                      {contato.name || 'Sem nome'}
                    </div>
                  </td>
                  <td className="px-4 py-3">
                    <div className="flex flex-col gap-1 items-center">
                      {contato.phone && (
                        <div className="text-sm text-white">
                          {cleanPhone(contato.phone)}
                        </div>
                      )}
                      {contato.email && (
                        <div className="text-xs text-muted-foreground">
                          {contato.email}
                        </div>
                      )}
                    </div>
                  </td>
                  <td className="px-4 py-3">
                    <div className="flex justify-center">
                      <CanalDisplay canal={contato.inbox?.channel_type || ''} />
                    </div>
                  </td>
                  <td className="px-4 py-3 text-center text-xs text-muted-foreground whitespace-nowrap">
                    {contato.updated_at ? new Date(contato.updated_at).toLocaleDateString('pt-BR') : '-'}
                  </td>
                  <td className="px-4 py-3">
                    <div className="flex justify-center">
                      <button
                        onClick={() => handleToggleBlockAtender(contato.id, contato.bloqueado_atender)}
                        className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors focus:outline-none focus:ring-2 focus:ring-offset-2 ${!contato.bloqueado_atender
                          ? 'bg-green-500'
                          : 'bg-red-700'
                          }`}
                        role="switch"
                        aria-checked={!contato.bloqueado_atender}
                        title={contato.bloqueado_atender ? 'Contato bloqueado - IA não responde' : 'Contato ativo - IA pode responder'}
                      >
                        <span
                          className={`inline-block h-4 w-4 transform rounded-full bg-white transition-transform ${!contato.bloqueado_atender
                            ? 'translate-x-6'
                            : 'translate-x-1'
                            }`}
                        />
                      </button>
                    </div>
                  </td>
                  <td className="px-4 py-3">
                    <button
                      onClick={() => openEditModal(contato)}
                      className="text-muted-foreground hover:text-foreground"
                    >
                      <MoreVertical className="w-4 h-4" />
                    </button>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      {/* Paginação */}
      {pagination.count > 0 && (
        <div className="flex items-center justify-between mt-4 px-2">
          <div className="text-sm text-muted-foreground">
            Mostrando <span className="font-medium">{contatos.length}</span> de <span className="font-medium">{pagination.count}</span> contatos
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={() => fetchContacts(pagination.previous)}
              disabled={!pagination.previous}
              className={`px-3 py-1 rounded text-sm font-medium transition-colors ${!pagination.previous
                ? 'bg-muted text-muted-foreground cursor-not-allowed'
                : 'bg-primary text-primary-foreground hover:bg-primary/90'
                }`}
            >
              Anterior
            </button>
            <button
              onClick={() => fetchContacts(pagination.next)}
              disabled={!pagination.next}
              className={`px-3 py-1 rounded text-sm font-medium transition-colors ${!pagination.next
                ? 'bg-muted text-muted-foreground cursor-not-allowed'
                : 'bg-primary text-primary-foreground hover:bg-primary/90'
                }`}
            >
              Próxima
            </button>
          </div>
        </div>
      )}
    </div>
  );
} 