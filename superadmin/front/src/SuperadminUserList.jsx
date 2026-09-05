import React, { useEffect, useState, useRef, useMemo } from 'react';
import { Users, Building, CheckCircle, XCircle, CircleDot, Circle, Plus, MoreVertical, Edit, Trash2, KeyRound, Power, Search, ChevronLeft, ChevronRight, Hash } from 'lucide-react';
import axios from 'axios';
import ReactDOM from 'react-dom';

/** Recalcula is_online com janela de 90 s baseado em last_seen (espelha o backend). */
function _applyPresenceWindow(users) {
  const WINDOW_MS = 90_000;
  const now = Date.now();
  return users.map(u => {
    const lastSeen = u.last_seen ? new Date(u.last_seen).getTime() : null;
    const isOnline = lastSeen ? (now - lastSeen) <= WINDOW_MS : false;
    return { ...u, is_online: isOnline };
  });
}

const USERS_PAGE_SIZE = 15;

function normalizeSearchText(value) {
  return String(value || '')
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '')
    .toLowerCase()
    .trim();
}

export default function SuperadminUserList() {
  const [users, setUsers] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [showModal, setShowModal] = useState(false);
  const [provedores, setProvedores] = useState([]);
  const [filterProvedorId, setFilterProvedorId] = useState('');
  const [searchQuery, setSearchQuery] = useState('');
  const [provedorFilterSearch, setProvedorFilterSearch] = useState('');
  const [usersPage, setUsersPage] = useState(1);
  const [form, setForm] = useState({
    username: '',
    email: '',
    password: '',
    first_name: '',
    last_name: '',
    user_type: 'agent',
    is_active: true,
    provedor_id: ''
  });
  const [saving, setSaving] = useState(false);
  const [success, setSuccess] = useState('');
  const [showMenuId, setShowMenuId] = useState(null);
  const [showEditModal, setShowEditModal] = useState(false);
  const [showResetModal, setShowResetModal] = useState(false);
  const [selectedUser, setSelectedUser] = useState(null);
  const menuBtnRefs = useRef({});
  const [menuPosition, setMenuPosition] = useState({ top: 0, left: 0 });
  const [refreshKey, setRefreshKey] = useState(0); // Força re-fetch quando incrementa

  useEffect(() => {
    async function fetchUsers() {
      setLoading(true);
      setError('');
      try {
        const token = localStorage.getItem('auth_token');

        // Provedor específico: proxy direto ao tenant
        if (filterProvedorId) {
          const res = await axios.get(`/api/provedores/${filterProvedorId}/users-status/`, {
            headers: { Authorization: `Token ${token}` }
          });
          const userData = Array.isArray(res.data?.users) ? res.data.users : [];
          setUsers(_applyPresenceWindow(userData));
          setLoading(false);
          return;
        }

        // Todos os provedores: agrega em paralelo pelo backend
        const res = await axios.get('/api/provedores/all-users-status/', {
          headers: { Authorization: `Token ${token}` }
        });
        const userData = Array.isArray(res.data?.users) ? res.data.users : [];
        setUsers(_applyPresenceWindow(userData));
      } catch (e) {
        console.error('Erro ao buscar usuários:', e);
        setError('Erro ao buscar usuários.');
        setUsers([]);
      }
      setLoading(false);
    }

    fetchUsers();

    // Atualizar lista de usuários a cada 30 segundos para obter status atualizado
    const intervalId = setInterval(() => {
      fetchUsers();
    }, 30000);

    return () => clearInterval(intervalId);
  }, [success, refreshKey, filterProvedorId]);

  useEffect(() => {
    setUsersPage(1);
  }, [filterProvedorId, searchQuery]);

  const filteredProvedoresOptions = useMemo(() => {
    const q = normalizeSearchText(provedorFilterSearch);
    if (!q) return provedores;
    return provedores.filter((p) => {
      const idStr = String(p.id);
      const nome = normalizeSearchText(p.nome);
      return idStr.includes(q) || nome.includes(q);
    });
  }, [provedores, provedorFilterSearch]);

  const filteredUsers = useMemo(() => {
    const q = normalizeSearchText(searchQuery);
    if (!q) return users;
    return users.filter((u) => {
      const haystack = [
        u.username,
        u.email,
        u.first_name,
        u.last_name,
        u.user_type,
        u.provedor_nome,
        u.provedor_id != null ? String(u.provedor_id) : '',
      ]
        .map(normalizeSearchText)
        .join(' ');
      return haystack.includes(q);
    });
  }, [users, searchQuery]);

  const totalPages = Math.max(1, Math.ceil(filteredUsers.length / USERS_PAGE_SIZE));
  const safePage = Math.min(usersPage, totalPages);
  const pageStart = (safePage - 1) * USERS_PAGE_SIZE;
  const paginatedUsers = filteredUsers.slice(pageStart, pageStart + USERS_PAGE_SIZE);

  useEffect(() => {
    if (usersPage > totalPages) {
      setUsersPage(totalPages);
    }
  }, [usersPage, totalPages]);

  useEffect(() => {
    async function fetchProvedores() {
      try {
        const token = localStorage.getItem('auth_token'); // CORRIGIDO: 'auth_token'
        const res = await axios.get('/api/provedores/', {
          headers: { Authorization: `Token ${token}` }
        });
        const provedoresData = res.data.results || res.data;
        setProvedores(provedoresData);
      } catch (e) {
        console.error('Erro ao buscar provedores:', e);
        setProvedores([]);
      }
    }
    fetchProvedores();
  }, [showModal, showEditModal]);

  const handleChange = (e) => {
    const { name, value, type, checked } = e.target;
    setForm((prev) => ({
      ...prev,
      [name]: type === 'checkbox' ? checked : value
    }));
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setSaving(true);
    setError('');
    setSuccess('');
    try {
      const token = localStorage.getItem('auth_token');
      // Cria usuário
      const userRes = await axios.post('/api/users/', {
        username: form.username,
        email: form.email,
        password: form.password,
        first_name: form.first_name,
        last_name: form.last_name,
        user_type: form.user_type,
        is_active: form.is_active,
        provedor_id: form.provedor_id, // Incluir provedor_id para associação automática
      }, {
        headers: { Authorization: `Token ${token}` }
      });
      // Não é necessário criar CompanyUser manualmente - o backend já faz a associação
      console.log('Usuário criado e associado ao provedor com sucesso!');
      setSuccess('Usuário criado com sucesso!');
      setShowModal(false);
      setForm({ username: '', email: '', password: '', first_name: '', last_name: '', user_type: 'agent', is_active: true, provedor_id: '' });
    } catch (e) {
      let msg = 'Erro ao criar usuário.';
      if (e.response && e.response.data) {
        if (typeof e.response.data === 'string') msg = e.response.data;
        else if (e.response.data.detail) msg = e.response.data.detail;
        else msg += ' ' + JSON.stringify(e.response.data);
      }
      setError(msg);
    }
    setSaving(false);
  };

  // Funções de ação
  const handleOpenMenu = (userId) => (e) => {
    e.stopPropagation();
    const btn = menuBtnRefs.current[userId];
    if (btn) {
      const rect = btn.getBoundingClientRect();
      setMenuPosition({
        top: rect.bottom + window.scrollY + 4,
        left: rect.right + window.scrollX - 160 // ajusta para alinhar à direita
      });
    }
    setShowMenuId(showMenuId === userId ? null : userId);
  };
  const handleEditUser = (user) => {
    setSelectedUser({
      ...user,
      write_provedor_id: user.provedor ? String(user.provedor) : ''
    });
    setShowEditModal(true);
    setShowMenuId(null);
  };
  const handleDeleteUser = async (user) => {
    if (!window.confirm('Tem certeza que deseja excluir este usuário?')) return;
    try {
      const token = localStorage.getItem('auth_token') || localStorage.getItem('token');
      const provedorId = user.provedor_id || user.provedor;
      if (!provedorId) {
        setError('Não foi possível identificar o provedor deste usuário.');
        setShowMenuId(null);
        return;
      }
      // ID na lista é o ID no banco do provedor — enviar provedor_id para excluir no tenant
      await axios.delete(`/api/users/${user.id}/`, {
        headers: { Authorization: `Token ${token}` },
        params: { provedor_id: provedorId },
        data: { provedor_id: provedorId, username: user.username },
      });
      setSuccess('Usuário excluído com sucesso!');
      setRefreshKey((k) => k + 1);
    } catch (e) {
      const msg =
        e.response?.data?.error ||
        e.response?.data?.detail ||
        'Erro ao excluir usuário.';
      setError(typeof msg === 'string' ? msg : 'Erro ao excluir usuário.');
    }
    setShowMenuId(null);
  };
  const handleToggleActive = async (user) => {
    try {
      const token = localStorage.getItem('auth_token') || localStorage.getItem('token');
      await axios.patch(`/api/users/${user.id}/`, { is_active: !user.is_active }, {
        headers: { Authorization: `Token ${token}` }
      });
      setSuccess('Status atualizado!');
    } catch (e) {
      setError('Erro ao atualizar status.');
    }
    setShowMenuId(null);
  };
  const handleResetPassword = (user) => {
    setSelectedUser(user);
    setShowResetModal(true);
    setShowMenuId(null);
  };

  return (
    <div className="flex-1 p-6 bg-background overflow-y-auto">
      <div className="max-w-7xl mx-auto">
        <div className="mb-8 flex items-center justify-between">
          <div>
            <h1 className="text-3xl font-bold text-foreground mb-2 flex items-center">
              <Users className="w-8 h-8 mr-3" />
              Usuários do Sistema
            </h1>
            <p className="text-muted-foreground">Veja todos os usuários, provedores, status e último acesso</p>
          </div>
          <button
            className="flex items-center gap-2 bg-primary text-white px-4 py-2 rounded font-medium shadow hover:bg-primary/90"
            onClick={() => setShowModal(true)}
          >
            <Plus className="w-5 h-5" /> Criar Usuário
          </button>
        </div>

        <div className="mb-4 space-y-3 rounded-xl border border-border bg-card p-4 shadow">
          <div className="grid grid-cols-1 gap-3 lg:grid-cols-2">
            <div>
              <label className="mb-1.5 block text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                Buscar usuário
              </label>
              <div className="relative">
                <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
                <input
                  type="search"
                  placeholder="Nome, usuário, e-mail ou ID do provedor..."
                  className="w-full rounded-lg border border-border bg-background py-2.5 pl-10 pr-3 text-sm text-foreground placeholder:text-muted-foreground focus:border-primary/50 focus:outline-none focus:ring-1 focus:ring-primary/30"
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                />
              </div>
            </div>
            <div>
              <label className="mb-1.5 block text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                Filtrar por provedor (ID ou nome)
              </label>
              <div className="flex flex-col gap-2 sm:flex-row">
                <input
                  type="search"
                  placeholder="Buscar provedor por ID ou nome..."
                  className="w-full rounded-lg border border-border bg-background px-3 py-2.5 text-sm text-foreground sm:max-w-[200px]"
                  value={provedorFilterSearch}
                  onChange={(e) => setProvedorFilterSearch(e.target.value)}
                />
                <select
                  className="min-w-0 flex-1 rounded-lg border border-border bg-background px-3 py-2.5 text-sm text-foreground"
                  value={filterProvedorId}
                  onChange={(e) => setFilterProvedorId(e.target.value)}
                >
                  <option value="">Todos os provedores</option>
                  {filteredProvedoresOptions.map((p) => (
                    <option key={p.id} value={p.id}>
                      #{p.id} — {p.nome}
                    </option>
                  ))}
                </select>
              </div>
            </div>
          </div>
          <div className="flex flex-wrap items-center justify-between gap-2 text-xs text-muted-foreground">
            <span>
              {filteredUsers.length} usuário{filteredUsers.length !== 1 ? 's' : ''}
              {searchQuery ? ' (busca aplicada)' : ''}
              {filterProvedorId ? ` · provedor #${filterProvedorId}` : ''}
            </span>
            {(searchQuery || filterProvedorId || provedorFilterSearch) && (
              <button
                type="button"
                className="rounded-md border border-border px-2.5 py-1 text-xs hover:bg-muted"
                onClick={() => {
                  setSearchQuery('');
                  setFilterProvedorId('');
                  setProvedorFilterSearch('');
                }}
              >
                Limpar filtros
              </button>
            )}
          </div>
        </div>
        {loading ? (
          <div className="text-center text-muted-foreground py-10">Carregando usuários...</div>
        ) : error ? (
          <div className="text-center text-red-500 py-10">{error}</div>
        ) : (
          <div className="bg-card rounded-lg shadow p-4 overflow-x-auto">
            <table className="min-w-full divide-y divide-border">
              <thead>
                <tr>
                  <th className="px-4 py-2 text-left text-foreground font-semibold">Usuário</th>
                  <th className="px-4 py-2 text-left text-foreground font-semibold">Email</th>
                  <th className="px-4 py-2 text-left text-foreground font-semibold">Tipo</th>
                  <th className="px-4 py-2 text-left text-foreground font-semibold">Provedores</th>
                  <th className="px-4 py-2 text-center text-foreground font-semibold">Ativo</th>
                  <th className="px-4 py-2 text-center text-foreground font-semibold">Online</th>
                  <th className="px-4 py-2 text-center text-foreground font-semibold">Último acesso</th>
                  <th className="px-4 py-2 text-center text-foreground font-semibold">Ações</th>
                </tr>
              </thead>
              <tbody>
                {filteredUsers.length === 0 && (
                  <tr>
                    <td colSpan={8} className="text-center text-muted-foreground py-10">
                      {users.length === 0
                        ? 'Nenhum usuário encontrado nos provedores ativos.'
                        : 'Nenhum usuário corresponde à busca ou filtro.'}
                    </td>
                  </tr>
                )}
                {paginatedUsers.map(user => (
                  <tr key={user.id} className="hover:bg-muted/50">
                    <td className="px-4 py-2 font-semibold text-foreground">{user.username}</td>
                    <td className="px-4 py-2 text-muted-foreground">{user.email || '-'}</td>
                    <td className="px-4 py-2">
                      {user.user_type === 'agent' ? (
                        <span className="inline-flex items-center gap-1 bg-green-900/80 text-green-100 rounded px-2 py-1 text-xs font-semibold">
                          agent
                        </span>
                      ) : (
                        <span className="text-muted-foreground text-sm">{user.user_type}</span>
                      )}
                    </td>
                    <td className="px-4 py-2">
                      {user.provedor_nome || user.provedor_id ? (
                        <div className="flex flex-col gap-1">
                          <span className="inline-flex w-fit items-center gap-1 rounded bg-blue-900/80 px-2 py-1 text-xs font-semibold text-blue-100">
                            <Building className="h-3 w-3 shrink-0" />
                            <span className="max-w-[180px] truncate">{user.provedor_nome || 'Provedor'}</span>
                          </span>
                          {user.provedor_id != null && (
                            <span className="inline-flex w-fit items-center gap-1 rounded border border-white/10 bg-black/30 px-1.5 py-0.5 font-mono text-[10px] text-gray-400">
                              <Hash className="h-3 w-3" />
                              ID {user.provedor_id}
                            </span>
                          )}
                        </div>
                      ) : (
                        <span className="text-xs text-gray-400">Sem provedor</span>
                      )}
                    </td>
                    <td className="px-4 py-2 text-center">
                      {user.is_active ? (
                        <span className="inline-flex items-center gap-1 text-green-600"><CheckCircle className="w-4 h-4" /> Ativo</span>
                      ) : (
                        <span className="inline-flex items-center gap-1 text-red-600"><XCircle className="w-4 h-4" /> Inativo</span>
                      )}
                    </td>
                    <td className="px-4 py-2 text-center">
                      {user.is_online ? (
                        <span className="inline-flex items-center gap-1 text-green-600"><CircleDot className="w-4 h-4" /> Online</span>
                      ) : (
                        <span className="inline-flex items-center gap-1 text-gray-400"><Circle className="w-4 h-4" /> Offline</span>
                      )}
                    </td>
                    <td className="px-4 py-2 text-center text-muted-foreground">
                      {(user.last_seen || user.last_login) ? (() => {
                        const raw = user.last_seen || user.last_login;
                        const d = new Date(raw);
                        const label = d.toLocaleString('pt-BR', { day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit' });
                        const tip = `${user.last_seen ? 'Última atividade' : 'Último login'}: ${d.toLocaleString('pt-BR')}`;
                        return <span title={tip}>{label}</span>;
                      })() : '-'}
                    </td>
                    <td className="px-4 py-2 text-center relative">
                      <button ref={el => (menuBtnRefs.current[user.id] = el)} className="p-1 hover:bg-muted rounded" onClick={handleOpenMenu(user.id)}>
                        <MoreVertical className="w-5 h-5" />
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>

            {filteredUsers.length > 0 && (
              <div className="mt-4 flex flex-col gap-3 border-t border-border pt-4 sm:flex-row sm:items-center sm:justify-between">
                <p className="text-sm text-muted-foreground">
                  Mostrando{' '}
                  <span className="font-medium text-foreground">
                    {pageStart + 1}–{Math.min(pageStart + USERS_PAGE_SIZE, filteredUsers.length)}
                  </span>{' '}
                  de <span className="font-medium text-foreground">{filteredUsers.length}</span>
                </p>
                <div className="flex items-center gap-2">
                  <button
                    type="button"
                    disabled={safePage <= 1}
                    onClick={() => setUsersPage((p) => Math.max(1, p - 1))}
                    className="inline-flex items-center gap-1 rounded-lg border border-border px-3 py-2 text-sm font-medium text-foreground transition hover:bg-muted disabled:cursor-not-allowed disabled:opacity-40"
                  >
                    <ChevronLeft className="h-4 w-4" />
                    Anterior
                  </button>
                  <span className="min-w-[88px] text-center text-sm text-muted-foreground">
                    Página {safePage} / {totalPages}
                  </span>
                  <button
                    type="button"
                    disabled={safePage >= totalPages}
                    onClick={() => setUsersPage((p) => Math.min(totalPages, p + 1))}
                    className="inline-flex items-center gap-1 rounded-lg border border-border px-3 py-2 text-sm font-medium text-foreground transition hover:bg-muted disabled:cursor-not-allowed disabled:opacity-40"
                  >
                    Próxima
                    <ChevronRight className="h-4 w-4" />
                  </button>
                </div>
              </div>
            )}

            {/* Portal para menu de ações */}
            {showMenuId && menuBtnRefs.current[showMenuId] && ReactDOM.createPortal(
              <div
                className="bg-white border border-border rounded shadow-lg z-[9999] min-w-[160px] flex flex-col w-max fixed"
                style={{ top: menuPosition.top, left: menuPosition.left }}
              >
                <button className="flex items-center gap-2 w-full px-4 py-2 text-left hover:bg-muted" onClick={() => handleEditUser(filteredUsers.find(u => u.id === showMenuId) || users.find(u => u.id === showMenuId))}><Edit className="w-4 h-4" /> Editar</button>
                <button className="flex items-center gap-2 w-full px-4 py-2 text-left hover:bg-muted" onClick={() => handleResetPassword(filteredUsers.find(u => u.id === showMenuId) || users.find(u => u.id === showMenuId))}><KeyRound className="w-4 h-4" /> Redefinir Senha</button>
                <button className="flex items-center gap-2 w-full px-4 py-2 text-left hover:bg-muted" onClick={() => handleToggleActive(filteredUsers.find(u => u.id === showMenuId) || users.find(u => u.id === showMenuId))}><Power className="w-4 h-4" /> {(filteredUsers.find(u => u.id === showMenuId) || users.find(u => u.id === showMenuId))?.is_active ? 'Inativar' : 'Ativar'}</button>
                <button className="flex items-center gap-2 w-full px-4 py-2 text-left text-red-600 hover:bg-muted" onClick={() => handleDeleteUser(filteredUsers.find(u => u.id === showMenuId) || users.find(u => u.id === showMenuId))}><Trash2 className="w-4 h-4" /> Excluir</button>
              </div>,
              document.body
            )}
          </div>
        )}

        {/* Modal de edição de usuário */}
        {showEditModal && selectedUser && (
          <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50">
            <div className="bg-[#23272f] rounded-xl shadow-2xl p-8 w-full max-w-md relative border border-border">
              <button className="absolute top-2 right-2 text-gray-400 hover:text-white text-2xl" onClick={() => setShowEditModal(false)}>&times;</button>
              <h2 className="text-2xl font-bold mb-6 flex items-center gap-2 text-white"><Edit /> Editar Usuário</h2>
              <form onSubmit={async (e) => {
                e.preventDefault();
                setSaving(true);
                setError('');
                try {
                  const token = localStorage.getItem('auth_token');
                  
                  if (!token) {
                    setError('Sessão expirada. Faça login novamente.');
                    setSaving(false);
                    return;
                  }

                  const payload = {
                    username: selectedUser.username,
                    email: selectedUser.email,
                    first_name: selectedUser.first_name,
                    last_name: selectedUser.last_name,
                    user_type: selectedUser.user_type,
                    is_active: selectedUser.is_active,
                    write_provedor_id: selectedUser.write_provedor_id ? parseInt(selectedUser.write_provedor_id) : null,
                  };

                  const response = await axios.patch(`/api/users/${selectedUser.id}/`, payload);
                  
                  setSuccess('Usuário atualizado com sucesso!');
                  setShowEditModal(false);
                  setRefreshKey(k => k + 1);
                } catch (e) {
                  const errorMsg = e.response?.data?.error || e.response?.data?.detail || JSON.stringify(e.response?.data) || 'Erro desconhecido ao atualizar';
                  setError(`Erro ao atualizar: ${errorMsg}`);
                }
                setSaving(false);
              }} className="space-y-4">
                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <label className="block font-medium mb-1 text-gray-200">Nome</label>
                    <input type="text" value={selectedUser.first_name || ''} onChange={e => setSelectedUser({ ...selectedUser, first_name: e.target.value })} className="input w-full bg-[#181b20] text-white border border-border rounded px-3 py-2" required />
                  </div>
                  <div>
                    <label className="block font-medium mb-1 text-gray-200">Sobrenome</label>
                    <input type="text" value={selectedUser.last_name || ''} onChange={e => setSelectedUser({ ...selectedUser, last_name: e.target.value })} className="input w-full bg-[#181b20] text-white border border-border rounded px-3 py-2" required />
                  </div>
                </div>

                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <label className="block font-medium mb-1 text-gray-200">Usuário</label>
                    <input type="text" value={selectedUser.username} onChange={e => setSelectedUser({ ...selectedUser, username: e.target.value })} className="input w-full bg-[#181b20] text-white border border-border rounded px-3 py-2" required />
                  </div>
                  <div>
                    <label className="block font-medium mb-1 text-gray-200">E-mail</label>
                    <input type="email" value={selectedUser.email} onChange={e => setSelectedUser({ ...selectedUser, email: e.target.value })} className="input w-full bg-[#181b20] text-white border border-border rounded px-3 py-2" required />
                  </div>
                </div>

                <div>
                  <label className="block font-medium mb-1 text-gray-200">Tipo</label>
                  <select value={selectedUser.user_type} onChange={e => setSelectedUser({ ...selectedUser, user_type: e.target.value })} className="input w-full bg-[#181b20] text-white border border-border rounded px-3 py-2">
                    <option value="superadmin">Superadmin</option>
                    <option value="admin">Administrador</option>
                    <option value="agent">Atendente</option>
                  </select>
                </div>

                <div>
                  <label className="block font-medium mb-1 text-gray-200">Provedor</label>
                  <select 
                    value={selectedUser.write_provedor_id || ''} 
                    onChange={e => setSelectedUser({ ...selectedUser, write_provedor_id: e.target.value })} 
                    className="input w-full bg-[#181b20] text-white border border-border rounded px-3 py-2"
                  >
                    <option value="">Selecione...</option>
                    {provedores.map(p => (
                      <option key={p.id} value={p.id}>#{p.id} — {p.nome}</option>
                    ))}
                    {provedores.length === 0 && (
                      <option disabled>Carregando provedores...</option>
                    )}
                  </select>
                </div>

                <div className="flex items-center gap-2">
                  <input type="checkbox" checked={selectedUser.is_active} onChange={e => setSelectedUser({ ...selectedUser, is_active: e.target.checked })} />
                  <label className="font-medium text-gray-200">Ativo</label>
                </div>
                <div>
                  <button type="submit" className="bg-primary text-white px-6 py-2 rounded font-medium w-full mt-2 hover:bg-primary/90 transition" disabled={saving}>
                    {saving ? 'Salvando...' : 'Salvar Alterações'}
                  </button>
                </div>
              </form>
            </div>
          </div>
        )}

        {/* Modal de redefinir senha */}
        {showResetModal && selectedUser && (
          <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50">
            <div className="bg-[#23272f] rounded-xl shadow-2xl p-8 w-full max-w-md relative border border-border">
              <button className="absolute top-2 right-2 text-gray-400 hover:text-white text-2xl" onClick={() => setShowResetModal(false)}>&times;</button>
              <h2 className="text-2xl font-bold mb-6 flex items-center gap-2 text-white"><KeyRound /> Redefinir Senha</h2>
              <form onSubmit={async (e) => {
                e.preventDefault();
                setSaving(true);
                setError('');
                try {
                  const token = localStorage.getItem('token');
                  await axios.patch(`/api/users/${selectedUser.id}/`, {
                    password: selectedUser.new_password,
                  }, {
                    headers: { Authorization: `Token ${token}` }
                  });
                  setSuccess('Senha redefinida com sucesso!');
                  setShowResetModal(false);
                } catch (e) {
                  setError('Erro ao redefinir senha.');
                }
                setSaving(false);
              }} className="space-y-5">
                <div>
                  <label className="block font-medium mb-1 text-gray-200">Nova Senha</label>
                  <input type="password" value={selectedUser.new_password || ''} onChange={e => setSelectedUser({ ...selectedUser, new_password: e.target.value })} className="input w-full bg-[#181b20] text-white border border-border rounded px-3 py-2" required />
                </div>
                <div>
                  <button type="submit" className="bg-primary text-white px-6 py-2 rounded font-medium w-full mt-2 hover:bg-primary/90 transition" disabled={saving}>
                    {saving ? 'Salvando...' : 'Redefinir Senha'}
                  </button>
                </div>
              </form>
            </div>
          </div>
        )}

        {/* Modal de criação de usuário */}
        {showModal && (
          <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50">
            <div className="bg-[#23272f] rounded-xl shadow-2xl p-8 w-full max-w-md relative border border-border">
              <button className="absolute top-2 right-2 text-gray-400 hover:text-white text-2xl" onClick={() => setShowModal(false)}>&times;</button>
              <h2 className="text-2xl font-bold mb-6 flex items-center gap-2 text-white"><Plus /> Criar Novo Usuário</h2>
              {error && <div className="text-red-400 mb-2">{error}</div>}
              <form onSubmit={handleSubmit} className="space-y-4">
                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <label className="block font-medium mb-1 text-gray-200">Nome</label>
                    <input type="text" name="first_name" value={form.first_name} onChange={handleChange} className="input w-full bg-[#181b20] text-white border border-border rounded px-3 py-2" required />
                  </div>
                  <div>
                    <label className="block font-medium mb-1 text-gray-200">Sobrenome</label>
                    <input type="text" name="last_name" value={form.last_name} onChange={handleChange} className="input w-full bg-[#181b20] text-white border border-border rounded px-3 py-2" required />
                  </div>
                </div>

                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <label className="block font-medium mb-1 text-gray-200">Usuário</label>
                    <input type="text" name="username" value={form.username} onChange={handleChange} className="input w-full bg-[#181b20] text-white border border-border rounded px-3 py-2" required />
                  </div>
                  <div>
                    <label className="block font-medium mb-1 text-gray-200">E-mail</label>
                    <input type="email" name="email" value={form.email} onChange={handleChange} className="input w-full bg-[#181b20] text-white border border-border rounded px-3 py-2" required />
                  </div>
                </div>

                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <label className="block font-medium mb-1 text-gray-200">Senha</label>
                    <input type="password" name="password" value={form.password} onChange={handleChange} className="input w-full bg-[#181b20] text-white border border-border rounded px-3 py-2" required />
                  </div>
                  <div>
                    <label className="block font-medium mb-1 text-gray-200">Tipo</label>
                    <select name="user_type" value={form.user_type} onChange={handleChange} className="input w-full bg-[#181b20] text-white border border-border rounded px-3 py-2">
                      <option value="superadmin">Superadmin</option>
                      <option value="admin">Administrador</option>
                      <option value="agent">Atendente</option>
                    </select>
                  </div>
                </div>

                <div>
                  <label className="block font-medium mb-1 text-gray-200">Provedor</label>
                  <select name="provedor_id" value={form.provedor_id} onChange={handleChange} className="input w-full bg-[#181b20] text-white border border-border rounded px-3 py-2">
                    <option value="">Selecione...</option>
                    {provedores.map(provedor => (
                      <option key={provedor.id} value={provedor.id}>{provedor.nome}</option>
                    ))}
                    {provedores.length === 0 && (
                      <option disabled>Carregando provedores...</option>
                    )}
                  </select>
                </div>

                <div className="flex items-center gap-2">
                  <input type="checkbox" name="is_active" checked={form.is_active} onChange={handleChange} />
                  <label className="font-medium text-gray-200">Ativo</label>
                </div>

                <div>
                  <button type="submit" className="bg-primary text-white px-6 py-2 rounded font-medium w-full mt-2 hover:bg-primary/90 transition" disabled={saving}>
                    {saving ? 'Salvando...' : 'Criar Usuário'}
                  </button>
                </div>
              </form>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}