import React, { useState, useEffect, useRef, useMemo } from 'react';
import { Wifi, Search, Edit, Trash2, MoreVertical, Plus, Eye, Users, MessageCircle, TrendingUp, Database, Trash, FileText, CheckCircle2, RefreshCw, Zap, KeyRound, Copy, X, Calendar, Bell, Globe2, CreditCard, ExternalLink, Smartphone, MessageSquare, ChevronsUpDown, Router, Layers } from 'lucide-react';
import axios from 'axios';
import ReactDOM from 'react-dom';
import { toast } from './lib/notify';

const FALLBACK_VPS_POOL = [];

const DEFAULT_VPS_CAPACITY = 3;
const DEFAULT_PROVIDER_DOMAIN = String(import.meta.env.VITE_PROVIDER_BASE_DOMAIN || 'niohub.com.br').trim().toLowerCase();

const readVpsPoolFromEnv = () => {
  const raw = import.meta.env.VITE_SUPERADMIN_VPS_POOL;
  if (!raw || typeof raw !== 'string') return [];
  try {
    const parsed = JSON.parse(raw);
    if (!Array.isArray(parsed)) return [];
    return parsed
      .filter((item) => item && typeof item === 'object' && item.key)
      .map((item) => ({
        key: String(item.key).trim(),
        label: String(item.label || item.key).trim(),
        api_url: String(item.api_url || '').trim(),
        max_providers: Number(item.max_providers || DEFAULT_VPS_CAPACITY),
      }))
      .filter((item) => item.key);
  } catch (error) {
    console.warn('[SuperadminProvedores] VITE_SUPERADMIN_VPS_POOL inválido, usando fallback.', error);
    return [];
  }
};

const getProviderVpsKey = (provedor) => {
  const ext = provedor?.integracoes_externas || {};
  return (
    provedor?.vps_key ||
    ext?.vps_key ||
    ext?.deployment?.vps_key ||
    ''
  );
};

/** Portador Inter: campo explícito ou ID local INTER-SUB-* */
const isInterBilling = (formOrProv) => {
  if (!formOrProv) return false;
  if ((formOrProv.billing_provider || '') === 'inter') return true;
  return String(formOrProv.asaas_subscription_id || '').startsWith('INTER-SUB-');
};

const inputClass =
  'w-full px-3.5 py-2.5 rounded-lg bg-[#14161c] text-white border border-white/[0.08] placeholder:text-gray-600 focus:border-primary/50 focus:ring-1 focus:ring-primary/25 outline-none transition';

const subscriptionStatusUi = (status) => {
  const st = (status || '').toUpperCase();
  if (st === 'ACTIVE') {
    return { label: 'Ativa', pill: 'bg-emerald-500/15 text-emerald-300 border-emerald-500/25', live: true, accent: 'from-emerald-500/20 to-emerald-600/5' };
  }
  if (st === 'PENDING') {
    return { label: 'Pendente', pill: 'bg-sky-500/15 text-sky-300 border-sky-500/25', live: true, accent: 'from-sky-500/20 to-sky-600/5' };
  }
  if (st === 'INACTIVE') {
    return { label: 'Inativa', pill: 'bg-amber-500/15 text-amber-300 border-amber-500/25', live: false, accent: 'from-amber-500/20 to-amber-600/5' };
  }
  return { label: st || 'Sem status', pill: 'bg-zinc-500/15 text-zinc-400 border-zinc-500/25', live: false, accent: 'from-zinc-500/15 to-zinc-600/5' };
};

const subscriptionCycleLabel = (cycle) => {
  const map = {
    WEEKLY: 'Semanal',
    BIWEEKLY: 'Quinzenal',
    MONTHLY: 'Mensal',
    QUARTERLY: 'Trimestral',
    SEMIANNUALLY: 'Semestral',
    YEARLY: 'Anual',
  };
  const key = (cycle || '').toUpperCase();
  return map[key] || cycle || '—';
};

const todayIso = () => new Date().toLocaleDateString('sv-SE');

const ASAAS_EDITABLE_PAYMENT = ['PENDING', 'OVERDUE'];

const paymentStatusUi = (status) => {
  if (['RECEIVED', 'RECEIVED_IN_CASH', 'CONFIRMED'].includes(status)) {
    return { label: 'Pago', pill: 'bg-emerald-500/15 text-emerald-300 border-emerald-500/20', icon: 'bg-emerald-500/10 text-emerald-400' };
  }
  if (status === 'OVERDUE') {
    return { label: 'Vencido', pill: 'bg-red-500/15 text-red-300 border-red-500/20', icon: 'bg-red-500/10 text-red-400' };
  }
  return { label: 'Pendente', pill: 'bg-amber-500/15 text-amber-300 border-amber-500/20', icon: 'bg-amber-500/10 text-amber-400' };
};

const getProviderSubdomain = (provedor) => {
  const ext = provedor?.integracoes_externas || {};
  return String(
    provedor?.subdomain ||
    ext?.subdomain ||
    ext?.tenant_subdomain ||
    ''
  ).trim().toLowerCase();
};

const normalizeSubdomainInput = (value) => {
  return String(value || '')
    .trim()
    .toLowerCase()
    .replace(/^https?:\/\//, '')
    .replace(/\/+$/, '');
};

const planLimitLabel = (base, extra) => (Number(base) > 0 ? Number(base) + (Number(extra) || 0) : 'Ilimitado');

function PlanoFields({ form, setForm, planos, usage, hasSubscription }) {
  const selected = planos.find((p) => String(p.id) === String(form.plano || ''));
  const visible = planos.filter((p) => p.ativo || String(p.id) === String(form.plano || ''));
  const fieldClass = 'w-full px-4 py-2 rounded bg-[#181b20] text-white border border-border';

  const choose = (value) => {
    const plano = planos.find((p) => String(p.id) === String(value));
    setForm((prev) => {
      const next = { ...prev, plano: value };
      if (plano && !hasSubscription) {
        next.subscription_value = plano.valor;
        next.subscription_cycle = plano.ciclo;
      }
      return next;
    });
  };

  const setNumber = (name) => (e) => {
    const value = e.target.value;
    setForm((prev) => ({ ...prev, [name]: value === '' ? '' : Math.max(0, parseInt(value, 10) || 0) }));
  };

  const usageLine = (label, used, base, extra) => {
    const limit = planLimitLabel(base, extra);
    const over = typeof limit === 'number' && used != null && used > limit;
    return (
      <div className="rounded-lg border border-border bg-[#181b20] px-3 py-2">
        <p className="text-[10px] font-bold uppercase tracking-wide text-gray-500">{label}</p>
        <p className={`text-sm font-semibold ${over ? 'text-amber-300' : 'text-white'}`}>
          {used != null ? `${used} de ${limit}` : limit}
        </p>
      </div>
    );
  };

  return (
    <div>
      <h3 className="text-lg font-semibold text-primary mb-4 flex items-center gap-2">
        <Layers className="w-5 h-5" /> Plano
      </h3>
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <div>
          <label className="block text-xs font-semibold text-gray-400 uppercase mb-1">Plano</label>
          <select className={fieldClass} value={form.plano || ''} onChange={(e) => choose(e.target.value)}>
            <option value="">Sem plano (sem limites)</option>
            {visible.map((p) => (
              <option key={p.id} value={p.id}>
                {p.nome} — R$ {Number(p.valor || 0).toFixed(2)}{p.ativo ? '' : ' (inativo)'}
              </option>
            ))}
          </select>
        </div>
        <div>
          <label className="block text-xs font-semibold text-gray-400 uppercase mb-1">Canais extras</label>
          <input type="number" min="0" className={fieldClass} value={form.canais_extras ?? 0} onChange={setNumber('canais_extras')} disabled={!selected} />
        </div>
        <div>
          <label className="block text-xs font-semibold text-gray-400 uppercase mb-1">Usuários extras</label>
          <input type="number" min="0" className={fieldClass} value={form.usuarios_extras ?? 0} onChange={setNumber('usuarios_extras')} disabled={!selected} />
        </div>
      </div>
      {selected && (
        <div className="mt-3 grid grid-cols-2 gap-3 md:max-w-md">
          {usageLine('Canais', usage?.canais, selected.max_canais, form.canais_extras)}
          {usageLine('Usuários', usage?.usuarios, selected.max_usuarios, form.usuarios_extras)}
        </div>
      )}
      <p className="mt-2 text-[11px] text-muted-foreground">
        {!selected
          ? 'Sem plano o provedor não tem limite de canais nem de usuários.'
          : hasSubscription
            ? `A assinatura atual não muda sozinha. Para cobrar R$ ${Number(selected.valor || 0).toFixed(2)}, use "Editar assinatura" em Detalhes Financeiros.`
            : 'O valor e o ciclo do plano já foram para a assinatura (Detalhes Financeiros).'}
        {usage?.error ? ` ${usage.error}` : ''}
        {' '}O canal do App Mobile não conta no limite. Extras só valem quando o recurso do plano tem limite.
      </p>
    </div>
  );
}

export default function SuperadminProvedores() {
  const [search, setSearch] = useState('');
  const [showAddModal, setShowAddModal] = useState(false);
  const [addProvedorForm, setAddProvedorForm] = useState({
    desired_id: '',
    nome: '',
    site_oficial: '',
    endereco: '',
    email_contato: '',
    bot_mode: 'ia',
    agent_mode: 'isp',
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
    billing_provider: 'asaas',
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
    vps_key: '',
    subdomain: '',
    enable_chat: true,
    enable_mobile_app: false,
    enable_acs: false,
    plano: '',
    canais_extras: 0,
    usuarios_extras: 0,
  });
  const [showEditModal, setShowEditModal] = useState(false);
  const [editProvedorForm, setEditProvedorForm] = useState({
    id: null,
    nome: '',
    site_oficial: '',
    endereco: '',
    email_contato: '',
    bot_mode: 'ia',
    agent_mode: 'isp',
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
    billing_provider: 'asaas',
    subscription_value: 0,
    subscription_cycle: 'MONTHLY',
    subscription_billing_type: 'BOLETO',
    subscription_status: '',
    subscription_next_due_date: '',
    release_channel: 'stable',
    current_version: '1.0.0',
    enable_chat: true,
    enable_mobile_app: false,
    enable_acs: false,
    plano: '',
    canais_extras: 0,
    usuarios_extras: 0,
  });
  const [planos, setPlanos] = useState([]);
  const [planUsage, setPlanUsage] = useState(null);
  const [showUpdateModal, setShowUpdateModal] = useState(false);
  const [updateForm, setUpdateForm] = useState({ channel: 'stable', version: '' });
  const [releaseJob, setReleaseJob] = useState(null);
  const [loadingEdit, setLoadingEdit] = useState(false);
  const [loadingAdd, setLoadingAdd] = useState(false);
  const [loadingUpdate, setLoadingUpdate] = useState(false);
  const [seqStatus, setSeqStatus] = useState({ db_vendor: '', max_id: 0, next_suggested: 1 });
  const [loadingSeq, setLoadingSeq] = useState(false);

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
  const [paymentEdit, setPaymentEdit] = useState(null);
  const [savingPayment, setSavingPayment] = useState(false);
  const [subscriptionEdit, setSubscriptionEdit] = useState(null);
  const [savingSubscription, setSavingSubscription] = useState(false);
  const [asaasSandbox, setAsaasSandbox] = useState(true);
  const [vpsPool, setVpsPool] = useState(FALLBACK_VPS_POOL);
  const [sortKey, setSortKey] = useState('id');
  const [sortDir, setSortDir] = useState('asc');

  // Modal token integração por provedor
  const [showTokenModal, setShowTokenModal] = useState(false);
  const [tokenProvedor, setTokenProvedor] = useState(null);
  const [tokenStatus, setTokenStatus] = useState({ configured: false, masked: '', last_used_at: null });
  const [plainToken, setPlainToken] = useState('');
  const [loadingToken, setLoadingToken] = useState(false);
  const [tokenError, setTokenError] = useState('');
  const [openingAppPanelId, setOpeningAppPanelId] = useState(null);

  const providersByVps = useMemo(() => {
    return provedoresState.reduce((acc, provedor) => {
      const key = getProviderVpsKey(provedor);
      if (!key) return acc;
      acc[key] = (acc[key] || 0) + 1;
      return acc;
    }, {});
  }, [provedoresState]);

  const normalizedVpsPool = useMemo(() => {
    if (!Array.isArray(vpsPool) || vpsPool.length === 0) return FALLBACK_VPS_POOL;
    return vpsPool.map((vps) => ({
      key: vps.key,
      label: vps.label || vps.key,
      api_url: vps.api_url || '',
      max_providers: Number(vps.max_providers || DEFAULT_VPS_CAPACITY),
      providers_count: Number(vps.providers_count || providersByVps[vps.key] || 0),
    }));
  }, [vpsPool, providersByVps]);

  const selectedVps = normalizedVpsPool.find((vps) => vps.key === addProvedorForm.vps_key) || null;
  const selectedVpsIsFull = selectedVps ? selectedVps.providers_count >= selectedVps.max_providers : false;

  const toggleSort = (key) => {
    if (sortKey === key) {
      setSortDir((d) => (d === 'asc' ? 'desc' : 'asc'));
      return;
    }
    setSortKey(key);
    setSortDir('asc');
  };

  const filteredProvedores = useMemo(() => {
    const q = search.trim().toLowerCase();
    let list = provedoresState;
    if (q) {
      list = list.filter(
        (p) =>
          String(p.id).includes(q) ||
          (p.nome || '').toLowerCase().includes(q) ||
          (p.site_oficial || '').toLowerCase().includes(q) ||
          getProviderSubdomain(p).toLowerCase().includes(q)
      );
    }
    const dir = sortDir === 'desc' ? -1 : 1;
    return [...list].sort((a, b) => {
      if (sortKey === 'vps') {
        const av = Number(a.vps_number || 0);
        const bv = Number(b.vps_number || 0);
        if (av !== bv) return (av - bv) * dir;
        return (Number(a.id) - Number(b.id)) * dir;
      }
      if (sortKey === 'vencimento') {
        const ad = a.subscription_next_due_date || '';
        const bd = b.subscription_next_due_date || '';
        if (!ad && !bd) return (Number(a.id) - Number(b.id)) * dir;
        if (!ad) return 1;
        if (!bd) return -1;
        if (ad !== bd) return ad < bd ? -1 * dir : 1 * dir;
        return (Number(a.id) - Number(b.id)) * dir;
      }
      return (Number(a.id) - Number(b.id)) * dir;
    });
  }, [provedoresState, search, sortKey, sortDir]);

  const lastProvedorId = useMemo(() => {
    if (!Array.isArray(provedoresState) || provedoresState.length === 0) return 0;
    return provedoresState.reduce((max, p) => Math.max(max, Number(p?.id || 0)), 0);
  }, [provedoresState]);

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

  const fetchIdSequenceStatus = async () => {
    try {
      const token = localStorage.getItem('token');
      const res = await axios.get('/api/provedores/id-sequence-status/', {
        headers: { Authorization: `Token ${token}` },
      });
      setSeqStatus(res.data || { db_vendor: '', max_id: 0, next_suggested: 1 });
    } catch {
      // ignore
    }
  };

  const handleResetIdSequence = async () => {
    setLoadingSeq(true);
    setErrorMsg('');
    try {
      const token = localStorage.getItem('token');
      await axios.post('/api/provedores/id-sequence-reset/', {}, {
        headers: { Authorization: `Token ${token}` },
      });
      await fetchIdSequenceStatus();
    } catch (err) {
      const msg = err?.response?.data?.error || 'Erro ao resetar o contador de IDs.';
      setErrorMsg(msg);
    } finally {
      setLoadingSeq(false);
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
    fetchIdSequenceStatus();
  }, []);

  useEffect(() => {
    if (!showUpdateModal) return undefined;
    const token = localStorage.getItem('token');
    axios.get('/api/changelog/', { headers: token ? { Authorization: `Token ${token}` } : {} })
      .then((res) => {
        const v = String(res.data?.current_version || '').trim();
        if (v) setUpdateForm((f) => ({ ...f, version: f.version || v }));
      })
      .catch(() => {
        setUpdateForm((f) => ({ ...f, version: f.version || '2.59.0' }));
      });
    return undefined;
  }, [showUpdateModal]);

  const channelTargets = useMemo(() => {
    return (provedoresState || []).filter(
      (p) => p?.is_active !== false && (p.release_channel || 'stable') === updateForm.channel
    );
  }, [provedoresState, updateForm.channel]);

  const channelWithVps = useMemo(
    () => channelTargets.filter((p) => p.vps || p.vps_id),
    [channelTargets]
  );

  useEffect(() => {
    const fetchVpsPool = async () => {
      const token = localStorage.getItem('token');
      try {
        const response = await axios.get('/api/provedores/vps-pool/', {
          headers: { Authorization: `Token ${token}` }
        });
        const data = response.data?.results || response.data || [];
        if (Array.isArray(data) && data.length > 0) {
          setVpsPool(data);
          return;
        }
      } catch (error) {
        // Endpoint ainda pode não existir nesta fase - fallback em seguida.
      }

      const envPool = readVpsPoolFromEnv();
      setVpsPool(envPool.length ? envPool : FALLBACK_VPS_POOL);
    };

    fetchVpsPool();
  }, []);

  useEffect(() => {
    axios
      .get('/api/planos/', { headers: { Authorization: `Token ${localStorage.getItem('token')}` } })
      .then((res) => setPlanos(res.data.results || res.data || []))
      .catch((err) => console.error('Erro ao carregar planos:', err));
  }, []);

  useEffect(() => {
    const fetchAsaasConfig = async () => {
      try {
        const token = localStorage.getItem('token');
        const res = await axios.get('/api/system-config/', {
          headers: { Authorization: `Token ${token}` },
        });
        setAsaasSandbox(res.data?.asaas_sandbox !== false);
      } catch {
        setAsaasSandbox(true);
      }
    };
    fetchAsaasConfig();
  }, []);

  useEffect(() => {
    if (!addProvedorForm.vps_key && normalizedVpsPool.length) {
      setAddProvedorForm((prev) => ({
        ...prev,
        vps_key: normalizedVpsPool[0].key,
      }));
    }
  }, [addProvedorForm.vps_key, normalizedVpsPool]);

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
      const enableChat = !!addProvedorForm.enable_chat;
      const enableMobileApp = !!addProvedorForm.enable_mobile_app;
      const enableAcs = !!addProvedorForm.enable_acs;

      if (!enableChat && !enableMobileApp && !enableAcs) {
        setErrorMsg('Selecione ao menos uma solução: Chat, App Mobile e/ou ACS.');
        setLoadingAdd(false);
        return;
      }

      let currentSelectedVps = null;
      let normalizedSubdomain = '';

      if (enableChat) {
        if (!addProvedorForm.vps_key) {
          setErrorMsg('Selecione uma VPS para o Chat (multi-atendimento).');
          setLoadingAdd(false);
          return;
        }

        normalizedSubdomain = normalizeSubdomainInput(addProvedorForm.subdomain);
        const expectedSuffix = `.${DEFAULT_PROVIDER_DOMAIN}`;
        const validSubdomainRegex = new RegExp(`^[a-z0-9][a-z0-9-]*\\.${DEFAULT_PROVIDER_DOMAIN.replace('.', '\\.')}$`);
        if (!normalizedSubdomain) {
          setErrorMsg('Informe o subdomínio completo deste provedor (ex.: cliente-x.niohub.com.br).');
          setLoadingAdd(false);
          return;
        }
        if (!normalizedSubdomain.endsWith(expectedSuffix) || !validSubdomainRegex.test(normalizedSubdomain)) {
          setErrorMsg(`Subdomínio inválido. Use o formato "cliente-x.${DEFAULT_PROVIDER_DOMAIN}".`);
          setLoadingAdd(false);
          return;
        }
        const alreadyExists = provedoresState.some((provedor) => getProviderSubdomain(provedor) === normalizedSubdomain);
        if (alreadyExists) {
          setErrorMsg(`O subdomínio "${normalizedSubdomain}" já está em uso por outro provedor.`);
          setLoadingAdd(false);
          return;
        }

        currentSelectedVps = normalizedVpsPool.find((vps) => vps.key === addProvedorForm.vps_key);
        if (!currentSelectedVps) {
          setErrorMsg('A VPS selecionada não é válida.');
          setLoadingAdd(false);
          return;
        }
        if (currentSelectedVps.providers_count >= currentSelectedVps.max_providers) {
          setErrorMsg(`A VPS "${currentSelectedVps.label}" já atingiu o limite de ${currentSelectedVps.max_providers} provedores.`);
          setLoadingAdd(false);
          return;
        }
      }

      const payload = { ...addProvedorForm };
      delete payload.enable_mobile_app;
      delete payload.enable_chat;
      delete payload.enable_acs;
      const desiredRaw = String(payload.desired_id || '').trim();
      if (desiredRaw) {
        const parsed = parseInt(desiredRaw, 10);
        if (!Number.isFinite(parsed) || parsed <= 0) {
          setErrorMsg('ID do provedor inválido. Use um número inteiro maior que 0.');
          setLoadingAdd(false);
          return;
        }
        payload.desired_id = parsed;
      } else {
        delete payload.desired_id;
      }
      const ext = (payload.integracoes_externas && typeof payload.integracoes_externas === 'object') ? payload.integracoes_externas : {};
      payload.integracoes_externas = {
        ...ext,
        chat_enabled: enableChat,
      };

      if (enableChat && currentSelectedVps) {
        payload.integracoes_externas = {
          ...payload.integracoes_externas,
          vps_key: currentSelectedVps.key,
          vps_label: currentSelectedVps.label,
          vps_api_url: currentSelectedVps.api_url || '',
          subdomain: normalizedSubdomain,
        };
        payload.vps = currentSelectedVps.key;
        payload.subdomain = normalizedSubdomain;
        const vpsId = parseInt(currentSelectedVps.key, 10);
        if (!Number.isNaN(vpsId)) {
          payload.vps = vpsId;
        }
      } else {
        payload.vps = null;
        payload.subdomain = null;
      }

      delete payload.vps_key;
      payload.plano = payload.plano ? Number(payload.plano) : null;
      payload.canais_extras = Number(payload.canais_extras) || 0;
      payload.usuarios_extras = Number(payload.usuarios_extras) || 0;

      // Limpar campos de data vazios para evitar erro de validação do Django
      if (!payload.subscription_next_due_date) delete payload.subscription_next_due_date;
      if (!payload.asaas_subscription_id) delete payload.asaas_subscription_id;
      if (!payload.asaas_customer_id) delete payload.asaas_customer_id;

      console.log('[DEBUG SuperadminProvedores] Criando novo provedor:', payload);

      const response = await axios.post('/api/provedores/', payload, {
        headers: { Authorization: `Token ${token}` }
      });

      console.log('[DEBUG SuperadminProvedores] Resposta da API:', response.data);

      if (enableMobileApp && response.data?.id) {
        try {
          await axios.post(
            '/api/mobile-app/profiles/provision/',
            {
              provedor_id: response.data.id,
              is_active: true,
              cnpj: addProvedorForm.cpf_cnpj || '',
              number: addProvedorForm.mobile_phone || addProvedorForm.phone || '',
            },
            { headers: { Authorization: `Token ${token}` } }
          );
        } catch (mobileErr) {
          console.error('Provedor criado, mas falhou ao habilitar App Mobile:', mobileErr);
          setErrorMsg('Provedor criado, mas não foi possível habilitar o App Mobile. Ative depois na edição.');
        }
      }

      if (enableAcs && response.data?.id) {
        try {
          await axios.post(
            '/api/acs/profiles/provision/',
            { provedor_id: response.data.id, is_active: true },
            { headers: { Authorization: `Token ${token}` } }
          );
        } catch (acsErr) {
          console.error('Provedor criado, mas falhou ao habilitar ACS:', acsErr);
          setErrorMsg((prev) => prev || 'Provedor criado, mas não foi possível habilitar o ACS. Ative depois na edição.');
        }
      }

      // Atualizar lista após criar
      const res = await axios.get('/api/provedores/', {
        headers: { Authorization: `Token ${token}` }
      });
      setProvedoresState(res.data.results || res.data);

      // Atualizar estatísticas
      await fetchStats();

      setShowAddModal(false);
      setAddProvedorForm({
        desired_id: '',
        nome: '',
        site_oficial: '',
        endereco: '',
        email_contato: '',
        bot_mode: 'ia',
        agent_mode: 'isp',
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
        vps_key: normalizedVpsPool[0]?.key || '',
        subdomain: '',
        enable_chat: true,
        enable_mobile_app: false,
        enable_acs: false,
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

  const applyAsaasVerifyResponse = (data, provedorId) => {
    setEditProvedorForm((prev) => ({
      ...prev,
      asaas_customer_id: data.asaas_customer_id || '',
      asaas_subscription_id: data.asaas_subscription_id || '',
      billing_provider:
        data.billing_provider
        || (String(data.asaas_subscription_id || '').startsWith('INTER-SUB-') ? 'inter' : prev.billing_provider),
      subscription_status: data.subscription_status || '',
      subscription_value: data.subscription_value ?? prev.subscription_value,
      subscription_cycle: data.subscription_cycle || prev.subscription_cycle,
      subscription_billing_type: data.subscription_billing_type || prev.subscription_billing_type,
      subscription_next_due_date: data.subscription_next_due_date || prev.subscription_next_due_date || '',
    }));
    if (data.asaas_subscription_id && provedorId) {
      fetchSubscriptionPayments(provedorId);
    } else {
      setSubscriptionPayments([]);
    }
    return data;
  };

  const refreshAsaasFromRemote = async (provedorId, { silent = false } = {}) => {
    const token = localStorage.getItem('token');
    const response = await axios.post(`/api/provedores/${provedorId}/verify_asaas/`, {}, {
      headers: { Authorization: `Token ${token}` },
    });
    if (!response.data?.success) {
      throw new Error(response.data?.error || 'Falha ao consultar Asaas');
    }
    const data = applyAsaasVerifyResponse(response.data, provedorId);
    const res = await axios.get('/api/provedores/', {
      headers: { Authorization: `Token ${token}` },
    });
    setProvedoresState(res.data.results || res.data);
    if (!silent && data.cleared) {
      alert('Este provedor não existe mais no Asaas. Os vínculos locais foram removidos.');
    }
    return data;
  };

  const handleEditProvedor = (provedor) => {
    setEditProvedorForm({
      id: provedor.id,
      asaas_customer_id: provedor.asaas_customer_id || '',
      nome: provedor.nome || '',
      site_oficial: provedor.site_oficial || '',
      endereco: provedor.endereco || '',
      email_contato: provedor.email_contato || '',
      bot_mode: provedor.bot_mode || 'ia',
      agent_mode: provedor.agent_mode || 'isp',
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
      billing_provider: isInterBilling(provedor) ? 'inter' : (provedor.billing_provider || 'asaas'),
      subscription_value: provedor.subscription_value || 0,
      subscription_cycle: provedor.subscription_cycle || 'MONTHLY',
      subscription_billing_type: provedor.subscription_billing_type || 'BOLETO',
      subscription_status: provedor.subscription_status || '',
      subscription_next_due_date: provedor.subscription_next_due_date || '',
      release_channel: provedor.release_channel || 'stable',
      current_version: provedor.current_version || '1.0.0',
      enable_chat: provedor.chat_enabled !== false,
      enable_mobile_app: !!provedor.mobile_app_enabled,
      enable_acs: !!provedor.acs_enabled,
      plano: provedor.plano ? String(provedor.plano) : '',
      canais_extras: provedor.canais_extras || 0,
      usuarios_extras: provedor.usuarios_extras || 0,
    });
    setSubscriptionPayments([]);
    setPaymentEdit(null);
    setSubscriptionEdit(null);
    setPlanUsage(null);
    axios
      .get(`/api/provedores/${provedor.id}/plan_usage/`, { headers: { Authorization: `Token ${localStorage.getItem('token')}` } })
      .then((res) => setPlanUsage(res.data))
      .catch((err) => console.error('Erro ao consultar uso do plano:', err));
    setShowEditModal(true);
    setMenuId(null);
    if (provedor.asaas_customer_id || provedor.asaas_subscription_id) {
      setLoadingPayments(true);
      refreshAsaasFromRemote(provedor.id, { silent: true })
        .catch((err) => {
          console.error('Erro ao sincronizar com Asaas:', err);
          if (provedor.asaas_subscription_id) {
            fetchSubscriptionPayments(provedor.id);
          }
        })
        .finally(() => setLoadingPayments(false));
    }
  };

  const fetchSubscriptionPayments = async (provedorId) => {
    setSubscriptionPayments([]);
    setLoadingPayments(true);
    try {
      const token = localStorage.getItem('token');
      const res = await axios.get(`/api/provedores/${provedorId}/subscription_payments/`, {
        headers: { Authorization: `Token ${token}` },
        params: { _t: Date.now() },
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
      
      const payload = { ...editProvedorForm };
      const enableMobileApp = !!payload.enable_mobile_app;
      const enableChat = !!payload.enable_chat;
      const enableAcs = !!payload.enable_acs;
      delete payload.enable_mobile_app;
      delete payload.enable_chat;
      delete payload.enable_acs;

      if (!enableChat && !enableMobileApp && !enableAcs) {
        setErrorMsg('Selecione ao menos uma solução: Chat, App Mobile e/ou ACS.');
        setLoadingEdit(false);
        return;
      }

      // Limpar campos de data vazios — DateField do DRF rejeita string vazia
      if (payload.subscription_next_due_date === '' || payload.subscription_next_due_date == null) {
        delete payload.subscription_next_due_date;
      }
      // Não apagar vínculo de assinatura com string vazia no save geral
      if (!payload.asaas_subscription_id) {
        delete payload.asaas_subscription_id;
      }
      if (payload.subscription_status === '' || payload.subscription_status == null) {
        delete payload.subscription_status;
      }
      // Garantir que desired_id nunca vai no payload de edição
      delete payload.desired_id;
      payload.plano = payload.plano ? Number(payload.plano) : null;
      payload.canais_extras = Number(payload.canais_extras) || 0;
      payload.usuarios_extras = Number(payload.usuarios_extras) || 0;

      // Buscar o objeto original do provedor para preservar outras integracoes
      const originalProvedor = provedoresState.find(p => p.id === payload.id);
      const ext = originalProvedor?.integracoes_externas || {};
      
      payload.integracoes_externas = {
        ...ext,
        chat_enabled: enableChat,
      };
      
      await axios.patch(`/api/provedores/${editProvedorForm.id}/`, payload, {
        headers: { Authorization: `Token ${token}` }
      });

      try {
        const wasEnabled = !!originalProvedor?.mobile_app_enabled;
        if (enableMobileApp || wasEnabled) {
          await axios.post(
            '/api/mobile-app/profiles/provision/',
            {
              provedor_id: editProvedorForm.id,
              is_active: enableMobileApp,
              cnpj: editProvedorForm.cpf_cnpj || '',
              number: editProvedorForm.mobile_phone || editProvedorForm.phone || '',
            },
            { headers: { Authorization: `Token ${token}` } }
          );
        }
      } catch (mobileErr) {
        console.error('Falha ao sincronizar App Mobile:', mobileErr);
        if (enableMobileApp) {
          setErrorMsg('Provedor salvo, mas falhou ao habilitar o App Mobile.');
        }
      }

      try {
        const wasAcsEnabled = !!originalProvedor?.acs_enabled;
        if (enableAcs || wasAcsEnabled) {
          await axios.post(
            '/api/acs/profiles/provision/',
            {
              provedor_id: editProvedorForm.id,
              is_active: enableAcs,
            },
            { headers: { Authorization: `Token ${token}` } }
          );
        }
      } catch (acsErr) {
        console.error('Falha ao sincronizar ACS:', acsErr);
        if (enableAcs) {
          setErrorMsg((prev) => prev || 'Provedor salvo, mas falhou ao habilitar o ACS.');
        }
      }

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
        toast.success('Provedor sincronizado com sucesso no Asaas.');
        
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
      } else {
        toast.apiError({ response: { data: response.data } }, 'Erro ao sincronizar cliente.');
      }
    } catch (err) {
      console.error('Erro ao sincronizar com Asaas:', err);
      toast.apiError(err, 'Erro ao sincronizar cliente. Verifique o CPF/CNPJ e outros dados.');
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
        nextDueDate: editProvedorForm.subscription_next_due_date,
        notification_disabled: editProvedorForm.notification_disabled,
        billing_provider: editProvedorForm.billing_provider || 'asaas',
        cpf_cnpj: editProvedorForm.cpf_cnpj,
        company: editProvedorForm.company,
        nome: editProvedorForm.nome,
        email_contato: editProvedorForm.email_contato,
        phone: editProvedorForm.phone,
        mobile_phone: editProvedorForm.mobile_phone,
        endereco: editProvedorForm.endereco,
        address_number: editProvedorForm.address_number,
        complement: editProvedorForm.complement,
        province: editProvedorForm.province,
        postal_code: editProvedorForm.postal_code,
      }, {
        headers: { Authorization: `Token ${token}` }
      });

      if (response.data.success) {
        const gateway = response.data.billing_provider === 'inter' ? 'Banco Inter' : 'Asaas';
        toast.success(`Assinatura criada com sucesso no ${gateway}.`);
        // Atualizar lista
        const res = await axios.get('/api/provedores/', {
          headers: { Authorization: `Token ${token}` }
        });
        setProvedoresState(res.data.results || res.data);
        
        // Preferir dados da resposta da criação (evita PATCH posterior apagar o vínculo)
        const updatedProvedor = (res.data.results || res.data).find(p => p.id === editProvedorForm.id);
        setEditProvedorForm(prev => ({
          ...prev,
          asaas_subscription_id:
            response.data.subscription_id
            || updatedProvedor?.asaas_subscription_id
            || prev.asaas_subscription_id,
          billing_provider:
            response.data.billing_provider
            || updatedProvedor?.billing_provider
            || prev.billing_provider,
          subscription_status:
            updatedProvedor?.subscription_status || prev.subscription_status || 'PENDING',
          subscription_value:
            updatedProvedor?.subscription_value ?? prev.subscription_value,
          subscription_next_due_date:
            updatedProvedor?.subscription_next_due_date || prev.subscription_next_due_date,
        }));
        fetchSubscriptionPayments(editProvedorForm.id);
      } else {
        toast.apiError(
          { response: { data: response.data } },
          'Erro ao criar assinatura. Verifique os dados.',
        );
      }
    } catch (err) {
      console.error('Erro ao criar assinatura:', err);
      toast.apiError(err, 'Erro ao criar assinatura. Verifique os dados.');
    } finally {
      setLoadingEdit(false);
    }
  };

  const handleSavePayment = async () => {
    if (!paymentEdit) return;
    setSavingPayment(true);
    try {
      const token = localStorage.getItem('token');
      const res = await axios.post(`/api/provedores/${editProvedorForm.id}/update_payment/`, {
        payment_id: paymentEdit.id,
        value: paymentEdit.value,
        dueDate: paymentEdit.dueDate,
        billingType: paymentEdit.billingType,
        description: paymentEdit.description,
      }, { headers: { Authorization: `Token ${token}` } });
      if (res.data.success) {
        const updated = res.data.payment;
        setSubscriptionPayments((prev) => prev.map((p) => (p.id === updated.id ? { ...p, ...updated } : p)));
        setPaymentEdit(null);
        toast.success('Cobrança atualizada no Asaas.');
      } else {
        toast.apiError({ response: { data: res.data } }, 'Não foi possível atualizar a cobrança.');
      }
    } catch (err) {
      toast.apiError(err, 'Não foi possível atualizar a cobrança.');
    } finally {
      setSavingPayment(false);
    }
  };

  const handleSaveSubscription = async () => {
    if (!subscriptionEdit) return;
    setSavingSubscription(true);
    try {
      const token = localStorage.getItem('token');
      const res = await axios.post(`/api/provedores/${editProvedorForm.id}/update_subscription/`, subscriptionEdit, {
        headers: { Authorization: `Token ${token}` },
      });
      if (res.data.success) {
        const fields = {
          subscription_status: res.data.subscription_status,
          subscription_value: res.data.subscription_value,
          subscription_cycle: res.data.subscription_cycle,
          subscription_billing_type: res.data.subscription_billing_type,
          subscription_next_due_date: res.data.subscription_next_due_date || '',
        };
        setEditProvedorForm((prev) => ({ ...prev, ...fields }));
        setProvedoresState((prev) => prev.map((p) => (p.id === editProvedorForm.id ? { ...p, ...fields } : p)));
        setSubscriptionEdit(null);
        toast.success(res.data.pending_updated
          ? 'Assinatura atualizada. As cobranças pendentes também foram ajustadas.'
          : 'Assinatura atualizada. Vale para as próximas cobranças.');
        if (res.data.pending_updated) fetchSubscriptionPayments(editProvedorForm.id);
      } else {
        toast.apiError({ response: { data: res.data } }, 'Não foi possível atualizar a assinatura.');
      }
    } catch (err) {
      toast.apiError(err, 'Não foi possível atualizar a assinatura.');
    } finally {
      setSavingSubscription(false);
    }
  };

  const handleVerifyAsaas = async () => {
    setLoadingEdit(true);
    setErrorMsg('');
    setSubscriptionPayments([]);

    try {
      const data = await refreshAsaasFromRemote(editProvedorForm.id);
      const { status_info } = data;
      const envLabel = (data.asaas_environment || (asaasSandbox ? 'sandbox' : 'production')) === 'sandbox'
        ? 'SANDBOX (homologação)'
        : 'PRODUÇÃO';
      if (data.cleared) {
        toast.info('Cliente/assinatura não encontrados no Asaas. Vínculos locais removidos.');
      } else if (data.billing_provider === 'inter' || String(data.asaas_subscription_id || '').startsWith('INTER-SUB-')) {
        toast.success(`Assinatura Inter atualizada — status: ${status_info?.subscription || '-'}.`);
      } else {
        toast.success(
          `Dados atualizados do Asaas (${envLabel}). Cliente: ${status_info?.customer || '-'} · Assinatura: ${status_info?.subscription || '-'}`,
        );
      }
    } catch (err) {
      console.error('Erro ao verificar status Asaas:', err);
      toast.apiError(err, 'Erro ao verificar status no Asaas.');
    } finally {
      setLoadingEdit(false);
    }
  };

  const applyLocalSubscriptionClear = () => {
    setEditProvedorForm((prev) => ({
      ...prev,
      asaas_subscription_id: '',
      billing_provider: 'asaas',
      subscription_status: '',
      subscription_value: 0,
      subscription_next_due_date: '',
    }));
    setSubscriptionPayments([]);
    setProvedoresState((prev) =>
      prev.map((p) =>
        p.id === editProvedorForm.id
          ? {
              ...p,
              asaas_subscription_id: '',
              subscription_status: '',
              subscription_value: 0,
              subscription_next_due_date: null,
            }
          : p
      )
    );
  };

  const handleClearAsaasSubscription = async (cancelOnAsaas = false) => {
    const isInter = isInterBilling(editProvedorForm);
    const envLabel = asaasSandbox ? 'SANDBOX (homologação)' : 'PRODUÇÃO';
    const subId = editProvedorForm.asaas_subscription_id || '';
    const confirmMessage = cancelOnAsaas
      ? (isInter
          ? `Cancelar cobranças abertas no Inter e remover a assinatura ${subId} no NioHub?\n\nEsta ação não pode ser desfeita.`
          : `Cancelar a assinatura ${subId} no Asaas (${envLabel}) e remover o vínculo no NioHub?\n\nEsta ação não pode ser desfeita. O cliente Asaas permanece cadastrado.`)
      : (isInter
          ? 'Remover apenas o vínculo da assinatura no NioHub?\n\nCobranças já emitidas no Inter continuam existindo.'
          : 'Remover apenas o vínculo da assinatura no NioHub?\n\nA assinatura continuará existindo no Asaas. Use isto se já cancelou manualmente lá ou o ID local está desatualizado.');

    if (!window.confirm(confirmMessage)) return;

    setLoadingEdit(true);
    setErrorMsg('');
    try {
      const token = localStorage.getItem('token');
      const res = await axios.post(
        `/api/provedores/${editProvedorForm.id}/clear_asaas_subscription/`,
        { cancel_on_asaas: cancelOnAsaas },
        { headers: { Authorization: `Token ${token}` } },
      );
      if (!res.data?.success) {
        throw new Error(res.data?.error || 'Falha ao desvincular assinatura');
      }
      applyLocalSubscriptionClear();
      toast.success(
        cancelOnAsaas
          ? 'Assinatura cancelada no gateway e vínculo removido.'
          : 'Vínculo da assinatura removido no NioHub.',
      );
    } catch (err) {
      console.error('Erro ao desvincular assinatura:', err);
      toast.apiError(err, 'Erro ao desvincular assinatura.');
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

  const handleDeploy = async (provedorId) => {
    if (!confirm('Deseja iniciar o deploy automático para este provedor?')) return;
    try {
      const token = localStorage.getItem('token');
      await axios.post(`/api/provedores/${provedorId}/deploy/`, {}, {
        headers: { Authorization: `Token ${token}` }
      });
      alert('Deploy iniciado! O status será atualizado em breve.');
    } catch (err) {
      alert(err.response?.data?.error || 'Erro ao iniciar deploy.');
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

  const openIntegrationTokenModal = async (provedor) => {
    setTokenError('');
    setPlainToken('');
    setTokenStatus({ configured: false, masked: '', last_used_at: null });
    setTokenProvedor(provedor);
    setShowTokenModal(true);
    setLoadingToken(true);
    try {
      const token = localStorage.getItem('token');
      const res = await axios.get(`/api/provedores/${provedor.id}/integration-token/`, {
        headers: { Authorization: `Token ${token}` }
      });
      setTokenStatus(res.data || { configured: false, masked: '', last_used_at: null });
    } catch (err) {
      setTokenError('Erro ao carregar status do token.');
    } finally {
      setLoadingToken(false);
    }
  };

  const rotateIntegrationToken = async () => {
    if (!tokenProvedor) return;
    if (!window.confirm(`Rotacionar o token de integração do provedor "${tokenProvedor.nome}"?\n\nIsso atualizará o token usado pelo Superadmin para falar com o tenant.`)) return;
    setTokenError('');
    setPlainToken('');
    setLoadingToken(true);
    try {
      const token = localStorage.getItem('token');
      const res = await axios.post(`/api/provedores/${tokenProvedor.id}/integration-token/rotate/`, {}, {
        headers: { Authorization: `Token ${token}` }
      });
      const newToken = res.data?.token || '';
      setPlainToken(newToken);
      // refresh status (mascarado / last_used)
      const statusRes = await axios.get(`/api/provedores/${tokenProvedor.id}/integration-token/`, {
        headers: { Authorization: `Token ${token}` }
      });
      setTokenStatus(statusRes.data || { configured: true, masked: '', last_used_at: null });
      alert(res.data?.message || 'Token rotacionado.');
    } catch (err) {
      setTokenError(err.response?.data?.error || 'Erro ao rotacionar token.');
    } finally {
      setLoadingToken(false);
    }
  };

  const openProviderAppPanel = async (provedorId) => {
    if (!provedorId) return;
    setOpeningAppPanelId(provedorId);
    setErrorMsg('');
    try {
      const token = localStorage.getItem('token') || localStorage.getItem('auth_token');
      const { data } = await axios.post(
        '/api/auth/niohub-panel/',
        { provedor_id: provedorId },
        { headers: { Authorization: `Token ${token}` } },
      );
      if (!data?.token) throw new Error('Token ausente');
      localStorage.setItem('auth_token', data.token);
      localStorage.setItem('token', data.token);
      window.location.href = '/painel';
    } catch (err) {
      setErrorMsg(err.response?.data?.error || 'Não foi possível abrir o painel do app.');
      setOpeningAppPanelId(null);
    }
  };

  const copyToClipboard = async (value) => {
    try {
      await navigator.clipboard.writeText(String(value || ''));
    } catch (e) {
      // fallback simples
      const ta = document.createElement('textarea');
      ta.value = String(value || '');
      document.body.appendChild(ta);
      ta.select();
      document.execCommand('copy');
      document.body.removeChild(ta);
    }
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

      {errorMsg && !showAddModal && !showEditModal && (
        <div className="mb-6 rounded-xl border border-red-500/25 bg-red-500/10 px-4 py-3 text-sm text-red-300">
          {errorMsg}
        </div>
      )}

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
          <button
            type="button"
            onClick={handleResetIdSequence}
            disabled={loadingSeq}
            className="flex items-center gap-2 border border-border bg-card hover:bg-muted text-foreground px-4 py-3 rounded-lg font-medium transition-colors"
            title={`Max ID: ${seqStatus.max_id} • Próximo: ${seqStatus.next_suggested} • DB: ${seqStatus.db_vendor || '?'}`}
          >
            <RefreshCw className={`w-4 h-4 ${loadingSeq ? 'animate-spin' : ''}`} />
            {loadingSeq ? 'Reparando IDs...' : 'Reparar IDs'}
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
                    <label className="block text-xs font-semibold text-gray-400 uppercase mb-1">ID do Provedor (opcional)</label>
                    <input
                      type="text"
                      name="desired_id"
                      inputMode="numeric"
                      pattern="[0-9]*"
                      className="w-full px-4 py-2 rounded bg-[#181b20] text-white border border-border"
                      value={addProvedorForm.desired_id}
                      onChange={(e) => {
                        const raw = String(e.target.value || '').replace(/[^\d]/g, '');
                        setAddProvedorForm((prev) => ({ ...prev, desired_id: raw }));
                      }}
                      placeholder={`Ex: ${lastProvedorId + 1}`}
                    />
                    <p className="mt-1 text-[11px] text-gray-400">
                      Último ID: <span className="font-mono text-white/80">{lastProvedorId || '—'}</span> • Próximo sugerido:{' '}
                      <span className="font-mono text-white/80">{(lastProvedorId || 0) + 1}</span>
                    </p>
                  </div>
                  <div>
                    <label className="block text-xs font-semibold text-gray-400 uppercase mb-1">Nome do Provedor *</label>
                    <input type="text" name="nome" className="w-full px-4 py-2 rounded bg-[#181b20] text-white border border-border" value={addProvedorForm.nome} onChange={handleAddProvedorChange} required />
                  </div>
                  <div>
                    <label className="block text-xs font-semibold text-gray-400 uppercase mb-1">CPF ou CNPJ *</label>
                    <input type="text" name="cpf_cnpj" className="w-full px-4 py-2 rounded bg-[#181b20] text-white border border-border" value={addProvedorForm.cpf_cnpj} onChange={handleAddProvedorChange} required placeholder="Apenas números" />
                  </div>
                  <div>
                    <label className="block text-xs font-semibold text-gray-400 uppercase mb-1">Subdomínio {addProvedorForm.enable_chat ? '*' : '(só Chat)'}</label>
                    <input
                      type="text"
                      name="subdomain"
                      className="w-full px-4 py-2 rounded bg-[#181b20] text-white border border-border disabled:opacity-50"
                      value={addProvedorForm.subdomain}
                      onChange={handleAddProvedorChange}
                      required={!!addProvedorForm.enable_chat}
                      disabled={!addProvedorForm.enable_chat}
                      placeholder={`cliente-x.${DEFAULT_PROVIDER_DOMAIN}`}
                    />
                    <p className="mt-1 text-[11px] text-gray-400">
                      {addProvedorForm.enable_chat
                        ? 'DNS é manual. Informe o host final já apontado para a VPS.'
                        : 'Não é necessário se o provedor usar somente App Mobile ou ACS.'}
                    </p>
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
                  <div className="md:col-span-2">
                    <p className="block text-xs font-semibold text-gray-400 uppercase mb-2">Soluções *</p>
                    <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                      <label className={`flex cursor-pointer items-start gap-3 rounded-xl border p-4 transition ${addProvedorForm.enable_chat ? 'border-primary/40 bg-primary/10' : 'border-white/10 bg-[#14161c]/50 hover:border-white/20'}`}>
                        <input
                          type="checkbox"
                          name="enable_chat"
                          checked={!!addProvedorForm.enable_chat}
                          onChange={handleAddProvedorChange}
                          className="mt-0.5 h-4 w-4 rounded border-border bg-[#181b20] text-primary focus:ring-primary/20"
                        />
                        <span>
                          <span className="flex items-center gap-2 text-sm font-semibold text-white">
                            <MessageSquare className="w-4 h-4 text-primary" />
                            Chat
                          </span>
                          <span className="block text-xs text-muted-foreground mt-1">
                            Multi-atendimento (painel + VPS + subdomínio).
                          </span>
                        </span>
                      </label>
                      <label className={`flex cursor-pointer items-start gap-3 rounded-xl border p-4 transition ${addProvedorForm.enable_mobile_app ? 'border-primary/40 bg-primary/10' : 'border-white/10 bg-[#14161c]/50 hover:border-white/20'}`}>
                        <input
                          type="checkbox"
                          name="enable_mobile_app"
                          checked={!!addProvedorForm.enable_mobile_app}
                          onChange={handleAddProvedorChange}
                          className="mt-0.5 h-4 w-4 rounded border-border bg-[#181b20] text-primary focus:ring-primary/20"
                        />
                        <span>
                          <span className="flex items-center gap-2 text-sm font-semibold text-white">
                            <Smartphone className="w-4 h-4 text-primary" />
                            App Mobile
                          </span>
                          <span className="block text-xs text-muted-foreground mt-1">
                            Aplicativo do cliente. Pode ser só App, sem Chat.
                          </span>
                        </span>
                      </label>
                      <label className={`flex cursor-pointer items-start gap-3 rounded-xl border p-4 transition ${addProvedorForm.enable_acs ? 'border-primary/40 bg-primary/10' : 'border-white/10 bg-[#14161c]/50 hover:border-white/20'}`}>
                        <input
                          type="checkbox"
                          name="enable_acs"
                          checked={!!addProvedorForm.enable_acs}
                          onChange={handleAddProvedorChange}
                          className="mt-0.5 h-4 w-4 rounded border-border bg-[#181b20] text-primary focus:ring-primary/20"
                        />
                        <span>
                          <span className="flex items-center gap-2 text-sm font-semibold text-white">
                            <Router className="w-4 h-4 text-primary" />
                            ACS
                          </span>
                          <span className="block text-xs text-muted-foreground mt-1">
                            Painel GenieACS com licença, validação e bloqueio.
                          </span>
                        </span>
                      </label>
                    </div>
                  </div>
                  {addProvedorForm.enable_chat && (
                    <>
                  <div>
                    <label className="block text-xs font-semibold text-gray-400 uppercase mb-1">Modo de Atendimento *</label>
                    <select name="bot_mode" className="w-full px-4 py-2 rounded bg-[#181b20] text-white border border-border" value={addProvedorForm.bot_mode} onChange={handleAddProvedorChange} required={!!addProvedorForm.enable_chat}>
                      <option value="ia">Inteligência Artificial (IA)</option>
                      <option value="chatbot">Fluxo de Chatbot</option>
                    </select>
                  </div>
                  <div>
                    <label className="block text-xs font-semibold text-gray-400 uppercase mb-1">Modo do Agente de IA *</label>
                    <select name="agent_mode" className="w-full px-4 py-2 rounded bg-[#181b20] text-white border border-border" value={addProvedorForm.agent_mode} onChange={handleAddProvedorChange} required={!!addProvedorForm.enable_chat}>
                      <option value="isp">Provedor de Internet (ISP)</option>
                      <option value="support">Suporte da Plataforma (NioHub)</option>
                    </select>
                    <p className="text-[11px] text-muted-foreground mt-1">
                      Use Suporte da Plataforma no painel que atende clientes e leads do NioHub.
                    </p>
                  </div>
                    </>
                  )}
                </div>
              </div>

              {/* Seção 1.5: Alocação em VPS */}
              {addProvedorForm.enable_chat && (
              <div>
                <h3 className="text-lg font-semibold text-primary mb-4 flex items-center gap-2">
                  <Database className="w-5 h-5" /> Alocação de VPS
                </h3>
                <div className="space-y-4">
                  <div>
                    <label className="block text-xs font-semibold text-gray-400 uppercase mb-1">VPS de destino *</label>
                    <select
                      name="vps_key"
                      className="w-full px-4 py-2 rounded bg-[#181b20] text-white border border-border"
                      value={addProvedorForm.vps_key}
                      onChange={handleAddProvedorChange}
                      required
                    >
                      <option value="" disabled>Selecione uma VPS</option>
                      {normalizedVpsPool.map((vps) => {
                        const isFull = vps.providers_count >= vps.max_providers;
                        return (
                          <option key={vps.key} value={vps.key} disabled={isFull}>
                            {vps.label} ({vps.providers_count}/{vps.max_providers}) {isFull ? '- LOTADA' : ''}
                          </option>
                        );
                      })}
                    </select>
                    {selectedVps && (
                      <p className={`mt-2 text-xs ${selectedVpsIsFull ? 'text-red-400' : 'text-gray-400'}`}>
                        Capacidade atual: {selectedVps.providers_count}/{selectedVps.max_providers}
                        {selectedVpsIsFull ? ' (limite atingido)' : ''}
                      </p>
                    )}
                  </div>
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                    {normalizedVpsPool.map((vps) => {
                      const isFull = vps.providers_count >= vps.max_providers;
                      return (
                        <div key={vps.key} className={`rounded-lg border p-3 ${isFull ? 'border-red-500/40 bg-red-500/10' : 'border-border bg-[#181b20]'}`}>
                          <div className="flex items-center justify-between gap-2">
                            <p className="text-sm font-semibold text-white">{vps.label}</p>
                            <span className={`text-[10px] px-2 py-0.5 rounded-full ${isFull ? 'bg-red-500/20 text-red-300' : 'bg-green-500/20 text-green-300'}`}>
                              {isFull ? 'Lotada' : 'Disponível'}
                            </span>
                          </div>
                          <p className="text-xs text-gray-400 mt-1">Chave: {vps.key}</p>
                          <p className="text-xs text-gray-300 mt-1">Provedores: {vps.providers_count}/{vps.max_providers}</p>
                        </div>
                      );
                    })}
                  </div>
                </div>
              </div>
              )}

              <PlanoFields form={addProvedorForm} setForm={setAddProvedorForm} planos={planos} usage={null} hasSubscription={false} />

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
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/70 backdrop-blur-sm">
          <div className="flex w-full max-w-4xl max-h-[92vh] flex-col overflow-hidden rounded-2xl border border-white/10 bg-[#1a1d24] shadow-2xl shadow-black/50">
            <div className="relative border-b border-white/10 bg-gradient-to-r from-[#1f232b] via-[#1a1d24] to-[#1f232b] px-6 py-5">
              <div className="flex items-start justify-between gap-4 pr-10">
                <div>
                  <p className="text-[11px] font-semibold uppercase tracking-widest text-primary/90">Provedor</p>
                  <h2 className="mt-1 text-xl font-bold text-white sm:text-2xl">
                    {editProvedorForm.nome || 'Editar provedor'}
                  </h2>
                  <p className="mt-1 text-sm text-gray-500">
                    Atualize dados, assinatura {isInterBilling(editProvedorForm) ? 'Inter' : 'Asaas'} e preferências de cobrança.
                  </p>
                </div>
                <div className="hidden shrink-0 items-center gap-2 sm:flex">
                  {isInterBilling(editProvedorForm) ? (
                    <span className="rounded-full border border-orange-500/25 bg-orange-500/10 px-3 py-1 text-[10px] font-bold uppercase tracking-wide text-orange-300">
                      Portador Inter
                    </span>
                  ) : editProvedorForm.asaas_customer_id ? (
                    <span className="rounded-full border border-emerald-500/25 bg-emerald-500/10 px-3 py-1 text-[10px] font-bold uppercase tracking-wide text-emerald-300">
                      Cliente Asaas
                    </span>
                  ) : null}
                  {editProvedorForm.id && (
                    <button
                      type="button"
                      onClick={() => openProviderAppPanel(editProvedorForm.id)}
                      disabled={openingAppPanelId === editProvedorForm.id}
                      className="rounded-full border border-primary/30 bg-primary/15 px-3 py-1 text-[10px] font-bold uppercase tracking-wide text-primary transition hover:bg-primary/25 disabled:opacity-50"
                    >
                      {openingAppPanelId === editProvedorForm.id ? 'Abrindo…' : 'Painel do App'}
                    </button>
                  )}
                </div>
              </div>
              <button
                type="button"
                className="absolute right-4 top-4 rounded-lg p-2 text-gray-400 transition hover:bg-white/10 hover:text-white"
                onClick={() => setShowEditModal(false)}
                aria-label="Fechar"
              >
                <X className="h-5 w-5" />
              </button>
            </div>

            <form onSubmit={handleSaveEdit} className="flex flex-1 flex-col overflow-hidden">
              <div className="flex-1 space-y-8 overflow-y-auto px-6 py-6 sm:px-8">
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
                  <div className="md:col-span-2">
                    <p className="block text-xs font-semibold text-gray-400 uppercase mb-2">Soluções *</p>
                    <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                      <label className={`flex cursor-pointer items-start gap-3 rounded-xl border p-4 transition ${editProvedorForm.enable_chat ? 'border-primary/40 bg-primary/10' : 'border-white/10 bg-[#14161c]/50 hover:border-white/20'}`}>
                        <input
                          type="checkbox"
                          name="enable_chat"
                          checked={!!editProvedorForm.enable_chat}
                          onChange={handleEditProvedorChange}
                          className="mt-0.5 h-4 w-4 rounded border-border bg-[#181b20] text-primary focus:ring-primary/20"
                        />
                        <span>
                          <span className="flex items-center gap-2 text-sm font-semibold text-white">
                            <MessageSquare className="w-4 h-4 text-primary" />
                            Chat
                          </span>
                          <span className="block text-xs text-muted-foreground mt-1">
                            Multi-atendimento (painel do provedor).
                          </span>
                        </span>
                      </label>
                      <label className={`flex cursor-pointer items-start gap-3 rounded-xl border p-4 transition ${editProvedorForm.enable_mobile_app ? 'border-primary/40 bg-primary/10' : 'border-white/10 bg-[#14161c]/50 hover:border-white/20'}`}>
                        <input
                          type="checkbox"
                          name="enable_mobile_app"
                          checked={!!editProvedorForm.enable_mobile_app}
                          onChange={handleEditProvedorChange}
                          className="mt-0.5 h-4 w-4 rounded border-border bg-[#181b20] text-primary focus:ring-primary/20"
                        />
                        <span>
                          <span className="flex items-center gap-2 text-sm font-semibold text-white">
                            <Smartphone className="w-4 h-4 text-primary" />
                            App Mobile
                          </span>
                          <span className="block text-xs text-muted-foreground mt-1">
                            Aplicativo do cliente.
                          </span>
                        </span>
                      </label>
                      <label className={`flex cursor-pointer items-start gap-3 rounded-xl border p-4 transition ${editProvedorForm.enable_acs ? 'border-primary/40 bg-primary/10' : 'border-white/10 bg-[#14161c]/50 hover:border-white/20'}`}>
                        <input
                          type="checkbox"
                          name="enable_acs"
                          checked={!!editProvedorForm.enable_acs}
                          onChange={handleEditProvedorChange}
                          className="mt-0.5 h-4 w-4 rounded border-border bg-[#181b20] text-primary focus:ring-primary/20"
                        />
                        <span>
                          <span className="flex items-center gap-2 text-sm font-semibold text-white">
                            <Router className="w-4 h-4 text-primary" />
                            ACS
                          </span>
                          <span className="block text-xs text-muted-foreground mt-1">
                            Painel GenieACS com licença e bloqueio.
                          </span>
                        </span>
                      </label>
                    </div>
                  </div>
                  {editProvedorForm.enable_chat && (
                    <>
                  <div>
                    <label className="block text-xs font-semibold text-gray-400 uppercase mb-1">Modo de Atendimento *</label>
                    <select name="bot_mode" className="w-full px-4 py-2 rounded bg-[#181b20] text-white border border-border" value={editProvedorForm.bot_mode} onChange={handleEditProvedorChange} required={!!editProvedorForm.enable_chat}>
                      <option value="ia">Inteligência Artificial (IA)</option>
                      <option value="chatbot">Fluxo de Chatbot</option>
                    </select>
                  </div>
                  <div>
                    <label className="block text-xs font-semibold text-gray-400 uppercase mb-1">Modo do Agente de IA *</label>
                    <select name="agent_mode" className="w-full px-4 py-2 rounded bg-[#181b20] text-white border border-border" value={editProvedorForm.agent_mode || 'isp'} onChange={handleEditProvedorChange} required={!!editProvedorForm.enable_chat}>
                      <option value="isp">Provedor de Internet (ISP)</option>
                      <option value="support">Suporte da Plataforma (NioHub)</option>
                    </select>
                    <p className="text-[11px] text-muted-foreground mt-1">
                      Use Suporte da Plataforma no painel que atende clientes e leads do NioHub.
                    </p>
                  </div>
                    </>
                  )}
                </div>
              </div>

              <PlanoFields
                form={editProvedorForm}
                setForm={setEditProvedorForm}
                planos={planos}
                usage={planUsage}
                hasSubscription={!!editProvedorForm.asaas_subscription_id}
              />

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

              {/* Seção 3: Faturamento */}
              <div>
                <h3 className="text-lg font-semibold text-primary mb-4 flex items-center gap-2">
                  <FileText className="w-5 h-5" /> Detalhes Financeiros ({isInterBilling(editProvedorForm) ? 'Inter' : 'Asaas'})
                </h3>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  <div>
                    <label className="block text-xs font-semibold text-gray-400 uppercase mb-1">
                      Nome da Empresa {isInterBilling(editProvedorForm) ? '(pagador)' : '(Asaas)'}
                    </label>
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

                  {/* Seção 4: Configurações de Update */}
                  <div className="md:col-span-2 pt-4 border-t border-border">
                    <h3 className="text-lg font-semibold text-primary mb-4 flex items-center gap-2">
                      <Zap className="w-5 h-5" /> Canal de Atualização
                    </h3>
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                      <div>
                        <label className="block text-xs font-semibold text-gray-400 uppercase mb-1">Canal de Release</label>
                        <select name="release_channel" className="w-full px-4 py-2 rounded bg-[#181b20] text-white border border-border" value={editProvedorForm.release_channel} onChange={handleEditProvedorChange}>
                          <option value="beta">Beta (Atualização Automática)</option>
                          <option value="stable">Estável (Atualização Controlada)</option>
                          <option value="manual">Manual</option>
                        </select>
                      </div>
                      <div>
                        <label className="block text-xs font-semibold text-gray-400 uppercase mb-1">Versão Atual</label>
                        <input type="text" className="w-full px-4 py-2 rounded bg-[#181b20] text-gray-500 border border-border cursor-not-allowed" value={editProvedorForm.current_version && editProvedorForm.current_version !== '1.0.0' ? editProvedorForm.current_version : 'Aguardando relatório do painel'} disabled />
                      </div>
                    </div>
                  </div>
                  
                  {/* Bloco de Assinatura */}
                  <div className="md:col-span-2 mt-2 overflow-hidden rounded-2xl border border-white/10 bg-[#14161c]/80">
                    <div className="flex items-center justify-between gap-3 border-b border-white/10 bg-gradient-to-r from-primary/10 to-transparent px-5 py-4">
                      <div className="flex items-center gap-3">
                        <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-primary/15 text-primary">
                          <CreditCard className="h-5 w-5" />
                        </div>
                        <div>
                          <h4 className="font-semibold text-white">Assinatura recorrente</h4>
                          <p className="text-xs text-gray-500">
                            {isInterBilling(editProvedorForm)
                              ? 'Portador Banco Inter — cobranças emitidas pelo Superadmin'
                              : 'Sincronizado com o Asaas em tempo real'}
                            {isInterBilling(editProvedorForm) ? (
                              <span className="ml-1.5 rounded bg-orange-500/15 px-1.5 py-0.5 text-[10px] font-semibold text-orange-300">
                                INTER
                              </span>
                            ) : asaasSandbox ? (
                              <span className="ml-1.5 rounded bg-amber-500/15 px-1.5 py-0.5 text-[10px] font-semibold text-amber-300">
                                SANDBOX
                              </span>
                            ) : (
                              <span className="ml-1.5 rounded bg-emerald-500/15 px-1.5 py-0.5 text-[10px] font-semibold text-emerald-300">
                                PRODUÇÃO
                              </span>
                            )}
                          </p>
                        </div>
                      </div>
                      <div className="flex flex-wrap items-center gap-2">
                        {editProvedorForm.asaas_subscription_id && (
                          <>
                            <button
                              type="button"
                              onClick={() => handleClearAsaasSubscription(true)}
                              disabled={loadingEdit}
                              className="inline-flex items-center gap-2 rounded-lg border border-red-500/30 bg-red-500/10 px-3 py-2 text-xs font-semibold text-red-200 transition hover:border-red-500/50 hover:bg-red-500/20 disabled:opacity-50"
                            >
                              {(isInterBilling(editProvedorForm)
                                ? 'Cancelar no Inter'
                                : 'Cancelar no Asaas')}
                            </button>
                            <button
                              type="button"
                              onClick={() => handleClearAsaasSubscription(false)}
                              disabled={loadingEdit}
                              className="inline-flex items-center gap-2 rounded-lg border border-white/10 bg-white/5 px-3 py-2 text-xs font-semibold text-gray-400 transition hover:border-white/20 hover:bg-white/10 hover:text-gray-200 disabled:opacity-50"
                              title={
                                isInterBilling(editProvedorForm)
                                  ? 'Remove só o vínculo no NioHub; cobranças abertas podem permanecer no Inter'
                                  : 'Remove só o vínculo no NioHub; a assinatura permanece no Asaas'
                              }
                            >
                              Desvincular local
                            </button>
                          </>
                        )}
                        <button
                          type="button"
                          onClick={handleVerifyAsaas}
                          disabled={loadingEdit}
                          className="inline-flex items-center gap-2 rounded-lg border border-white/10 bg-white/5 px-3 py-2 text-xs font-semibold text-gray-300 transition hover:border-primary/30 hover:bg-primary/10 hover:text-white disabled:opacity-50"
                        >
                          <RefreshCw className={`h-3.5 w-3.5 ${loadingEdit ? 'animate-spin' : ''}`} />
                          Atualizar
                        </button>
                      </div>
                    </div>

                    <div className="p-5">
                    {editProvedorForm.asaas_subscription_id ? (
                      <div className="flex flex-col gap-5">
                        {(() => {
                          const ui = subscriptionStatusUi(editProvedorForm.subscription_status);
                          return (
                            <div className={`rounded-xl border border-white/10 bg-gradient-to-br ${ui.accent} p-5`}>
                              <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
                                <div className="min-w-0 flex-1 space-y-3">
                                  <div className="flex flex-wrap items-center gap-2">
                                    <span className={`inline-flex items-center rounded-full border px-2.5 py-0.5 text-[10px] font-bold uppercase tracking-wide ${ui.pill}`}>
                                      {ui.label}
                                    </span>
                                    {ui.live && (
                                      <span className="inline-flex items-center gap-1 text-[10px] text-emerald-400/90">
                                        <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-emerald-400" />
                                        Em dia no {isInterBilling(editProvedorForm) ? 'Inter' : 'Asaas'}
                                      </span>
                                    )}
                                    <span className="inline-flex items-center rounded-full border border-white/15 px-2 py-0.5 text-[10px] font-bold uppercase tracking-wide text-gray-300">
                                      {isInterBilling(editProvedorForm) ? 'Inter' : 'Asaas'}
                                    </span>
                                  </div>
                                  <p className="text-[10px] text-gray-500">
                                    {isInterBilling(editProvedorForm)
                                      ? 'Assinatura local (cobranças emitidas no Banco Inter)'
                                      : 'ID da assinatura no Asaas (cobrança recorrente)'}
                                  </p>
                                  <div className="flex items-center gap-2 rounded-lg border border-white/10 bg-black/25 px-3 py-2">
                                    <code className="truncate text-xs text-gray-300">{editProvedorForm.asaas_subscription_id}</code>
                                    <button
                                      type="button"
                                      className="shrink-0 rounded-md p-1.5 text-gray-500 hover:bg-white/10 hover:text-white"
                                      title="Copiar ID"
                                      onClick={() => navigator.clipboard?.writeText(editProvedorForm.asaas_subscription_id)}
                                    >
                                      <Copy className="h-3.5 w-3.5" />
                                    </button>
                                  </div>
                                  <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
                                    <div className="rounded-lg border border-white/10 bg-black/20 px-3 py-2.5">
                                      <p className="text-[10px] font-bold uppercase tracking-wide text-gray-500">Valor</p>
                                      <p className="mt-0.5 text-sm font-semibold text-white">
                                        R$ {Number(editProvedorForm.subscription_value || 0).toFixed(2)}
                                      </p>
                                    </div>
                                    <div className="rounded-lg border border-white/10 bg-black/20 px-3 py-2.5">
                                      <p className="text-[10px] font-bold uppercase tracking-wide text-gray-500">Ciclo</p>
                                      <p className="mt-0.5 text-sm font-semibold text-white" title={editProvedorForm.subscription_cycle}>
                                        {subscriptionCycleLabel(editProvedorForm.subscription_cycle)}
                                      </p>
                                    </div>
                                    <div className="col-span-2 rounded-lg border border-white/10 bg-black/20 px-3 py-2.5 sm:col-span-1">
                                      <p className="text-[10px] font-bold uppercase tracking-wide text-gray-500">Próx. venc.</p>
                                      <p className="mt-0.5 text-sm font-semibold text-white">
                                        {editProvedorForm.subscription_next_due_date
                                          ? new Date(editProvedorForm.subscription_next_due_date + 'T12:00:00').toLocaleDateString('pt-BR')
                                          : '—'}
                                      </p>
                                    </div>
                                  </div>
                                  {!isInterBilling(editProvedorForm) && !subscriptionEdit && (
                                    <button
                                      type="button"
                                      onClick={() => setSubscriptionEdit({
                                        value: editProvedorForm.subscription_value || '',
                                        cycle: editProvedorForm.subscription_cycle || 'MONTHLY',
                                        billingType: editProvedorForm.subscription_billing_type || 'BOLETO',
                                        nextDueDate: editProvedorForm.subscription_next_due_date || '',
                                        updatePendingPayments: false,
                                      })}
                                      className="inline-flex items-center gap-2 rounded-lg border border-white/15 px-3 py-1.5 text-xs font-semibold text-gray-200 transition hover:border-primary/40 hover:bg-primary/10 hover:text-white"
                                    >
                                      <Edit className="h-3.5 w-3.5" /> Editar assinatura
                                    </button>
                                  )}
                                  {subscriptionEdit && (
                                    <div className="space-y-3 rounded-lg border border-primary/30 bg-black/30 p-4">
                                      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
                                        <div>
                                          <label className="mb-1 block text-[10px] font-bold uppercase tracking-wide text-gray-500">Valor</label>
                                          <input type="number" step="0.01" min="0.01" className={inputClass} value={subscriptionEdit.value}
                                            onChange={(e) => setSubscriptionEdit((s) => ({ ...s, value: e.target.value }))} />
                                        </div>
                                        <div>
                                          <label className="mb-1 block text-[10px] font-bold uppercase tracking-wide text-gray-500">Ciclo</label>
                                          <select className={inputClass} value={subscriptionEdit.cycle}
                                            onChange={(e) => setSubscriptionEdit((s) => ({ ...s, cycle: e.target.value }))}>
                                            <option value="MONTHLY">Mensal</option>
                                            <option value="BIMONTHLY">Bimestral</option>
                                            <option value="QUARTERLY">Trimestral</option>
                                            <option value="SEMIANNUALLY">Semestral</option>
                                            <option value="YEARLY">Anual</option>
                                          </select>
                                        </div>
                                        <div>
                                          <label className="mb-1 block text-[10px] font-bold uppercase tracking-wide text-gray-500">Pagamento</label>
                                          <select className={inputClass} value={subscriptionEdit.billingType}
                                            onChange={(e) => setSubscriptionEdit((s) => ({ ...s, billingType: e.target.value }))}>
                                            <option value="BOLETO">Boleto</option>
                                            <option value="PIX">PIX</option>
                                            <option value="CREDIT_CARD">Cartão de Crédito</option>
                                            <option value="UNDEFINED">Cliente escolhe</option>
                                          </select>
                                        </div>
                                        <div>
                                          <label className="mb-1 block text-[10px] font-bold uppercase tracking-wide text-gray-500">Próx. vencimento</label>
                                          <input type="date" min={todayIso()} className={inputClass} value={subscriptionEdit.nextDueDate}
                                            onChange={(e) => setSubscriptionEdit((s) => ({ ...s, nextDueDate: e.target.value }))} />
                                        </div>
                                      </div>
                                      <label className="flex items-start gap-2 text-xs text-gray-300">
                                        <input type="checkbox" className="mt-0.5" checked={subscriptionEdit.updatePendingPayments}
                                          onChange={(e) => setSubscriptionEdit((s) => ({ ...s, updatePendingPayments: e.target.checked }))} />
                                        <span>
                                          Aplicar também às cobranças já geradas que estão pendentes.
                                          <span className="block text-[11px] text-gray-500">
                                            Sem marcar, vale só para as próximas. O vencimento de faturas já geradas se altera na própria cobrança, no histórico abaixo.
                                          </span>
                                        </span>
                                      </label>
                                      <div className="flex justify-end gap-2">
                                        <button type="button" onClick={() => setSubscriptionEdit(null)} disabled={savingSubscription}
                                          className="rounded-lg px-3 py-1.5 text-xs font-semibold text-gray-400 hover:bg-white/5 hover:text-white">
                                          Cancelar
                                        </button>
                                        <button type="button" onClick={handleSaveSubscription} disabled={savingSubscription}
                                          className="inline-flex items-center gap-2 rounded-lg bg-primary px-4 py-1.5 text-xs font-bold text-white hover:bg-primary/90 disabled:opacity-50">
                                          {savingSubscription && <RefreshCw className="h-3.5 w-3.5 animate-spin" />}
                                          Salvar no Asaas
                                        </button>
                                      </div>
                                    </div>
                                  )}
                                  {!ui.live && (
                                    <p className="text-xs leading-relaxed text-amber-200/80">
                                      {isInterBilling(editProvedorForm)
                                        ? 'Assinatura Inter pendente/vencida. Atualize o status ou aguarde o pagamento.'
                                        : 'Assinatura inativa no Asaas. Atualize o status ou crie uma nova recorrência abaixo.'}
                                    </p>
                                  )}
                                </div>
                                <div className={`hidden h-14 w-14 shrink-0 items-center justify-center rounded-2xl border sm:flex ${ui.live ? 'border-emerald-500/30 bg-emerald-500/10' : 'border-amber-500/30 bg-amber-500/10'}`}>
                                  <CheckCircle2 className={`h-7 w-7 ${ui.live ? 'text-emerald-400' : 'text-amber-400'}`} />
                                </div>
                              </div>
                            </div>
                          );
                        })()}

                        <div>
                          <div className="mb-3 flex items-center justify-between">
                            <h5 className="text-xs font-bold uppercase tracking-widest text-gray-500">Histórico de cobranças</h5>
                            {subscriptionPayments.length > 0 && (
                              <span className="rounded-full bg-white/5 px-2 py-0.5 text-[10px] font-medium text-gray-400">
                                {subscriptionPayments.length} fatura{subscriptionPayments.length !== 1 ? 's' : ''}
                              </span>
                            )}
                          </div>

                          {loadingPayments ? (
                            <div className="flex flex-col items-center justify-center gap-2 rounded-xl border border-dashed border-white/10 py-10 text-gray-500">
                              <RefreshCw className="h-6 w-6 animate-spin text-primary/70" />
                              <span className="text-xs">
                                {isInterBilling(editProvedorForm)
                                  ? 'Consultando cobranças Inter...'
                                  : 'Consultando Asaas...'}
                              </span>
                            </div>
                          ) : subscriptionPayments.length > 0 ? (
                            <div className="max-h-96 space-y-2 overflow-y-auto pr-1">
                              {subscriptionPayments.map((payment) => {
                                const ps = paymentStatusUi(payment.status);
                                const canEdit = !isInterBilling(editProvedorForm) && ASAAS_EDITABLE_PAYMENT.includes(payment.status);
                                const editing = paymentEdit?.id === payment.id;
                                return (
                                  <div key={payment.id} className="space-y-2">
                                  <div
                                    className="group flex items-center justify-between gap-3 rounded-xl border border-white/[0.06] bg-[#0f1115] px-4 py-3 transition hover:border-primary/25 hover:bg-[#12151a]"
                                  >
                                    <div className="flex min-w-0 items-center gap-3">
                                      <div className={`flex h-10 w-10 shrink-0 items-center justify-center rounded-xl ${ps.icon}`}>
                                        <Calendar className="h-4 w-4" />
                                      </div>
                                      <div className="min-w-0">
                                        <p className="truncate text-sm font-medium text-white" title={payment.description || undefined}>
                                          {payment.description || `Cobrança ${payment.id}`}
                                        </p>
                                        <p className="text-xs text-gray-500">
                                          Venc. {new Date(payment.dueDate + 'T12:00:00').toLocaleDateString('pt-BR')}
                                          {' · '}R$ {payment.value} · {payment.billingType}
                                        </p>
                                      </div>
                                    </div>
                                    <div className="flex shrink-0 items-center gap-2">
                                      <span className={`rounded-md border px-2 py-0.5 text-[10px] font-bold uppercase ${ps.pill}`}>
                                        {ps.label}
                                      </span>
                                      {canEdit && !editing && (
                                        <button
                                          type="button"
                                          className="rounded-lg p-2 text-gray-400 transition hover:bg-white/10 hover:text-white"
                                          title="Alterar valor ou vencimento"
                                          onClick={() => setPaymentEdit({
                                            id: payment.id,
                                            value: payment.value ?? '',
                                            dueDate: payment.dueDate || '',
                                            billingType: payment.billingType || 'BOLETO',
                                            description: payment.description || '',
                                          })}
                                        >
                                          <Edit className="h-4 w-4" />
                                        </button>
                                      )}
                                      {(payment.bankSlipUrl || payment.invoiceUrl) && (
                                        <a
                                          href={payment.bankSlipUrl || payment.invoiceUrl}
                                          target="_blank"
                                          rel="noopener noreferrer"
                                          className="rounded-lg p-2 text-primary transition hover:bg-primary/10"
                                          title="Abrir fatura"
                                        >
                                          <ExternalLink className="h-4 w-4" />
                                        </a>
                                      )}
                                    </div>
                                  </div>
                                  {editing && (
                                    <div className="space-y-3 rounded-xl border border-primary/30 bg-black/30 p-4">
                                      <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
                                        <div>
                                          <label className="mb-1 block text-[10px] font-bold uppercase tracking-wide text-gray-500">Valor</label>
                                          <input type="number" step="0.01" min="0.01" className={inputClass} value={paymentEdit.value}
                                            onChange={(e) => setPaymentEdit((p) => ({ ...p, value: e.target.value }))} />
                                        </div>
                                        <div>
                                          <label className="mb-1 block text-[10px] font-bold uppercase tracking-wide text-gray-500">Vencimento</label>
                                          <input type="date" min={todayIso()} className={inputClass} value={paymentEdit.dueDate}
                                            onChange={(e) => setPaymentEdit((p) => ({ ...p, dueDate: e.target.value }))} />
                                        </div>
                                        <div>
                                          <label className="mb-1 block text-[10px] font-bold uppercase tracking-wide text-gray-500">Pagamento</label>
                                          <select className={inputClass} value={paymentEdit.billingType}
                                            onChange={(e) => setPaymentEdit((p) => ({ ...p, billingType: e.target.value }))}>
                                            <option value="BOLETO">Boleto</option>
                                            <option value="PIX">PIX</option>
                                            <option value="CREDIT_CARD">Cartão de Crédito</option>
                                            <option value="UNDEFINED">Cliente escolhe</option>
                                          </select>
                                        </div>
                                      </div>
                                      <div>
                                        <label className="mb-1 block text-[10px] font-bold uppercase tracking-wide text-gray-500">Descrição</label>
                                        <input type="text" maxLength={500} className={inputClass} value={paymentEdit.description}
                                          onChange={(e) => setPaymentEdit((p) => ({ ...p, description: e.target.value }))} />
                                      </div>
                                      <div className="flex justify-end gap-2">
                                        <button type="button" onClick={() => setPaymentEdit(null)} disabled={savingPayment}
                                          className="rounded-lg px-3 py-1.5 text-xs font-semibold text-gray-400 hover:bg-white/5 hover:text-white">
                                          Cancelar
                                        </button>
                                        <button type="button" onClick={handleSavePayment} disabled={savingPayment}
                                          className="inline-flex items-center gap-2 rounded-lg bg-primary px-4 py-1.5 text-xs font-bold text-white hover:bg-primary/90 disabled:opacity-50">
                                          {savingPayment && <RefreshCw className="h-3.5 w-3.5 animate-spin" />}
                                          Salvar no Asaas
                                        </button>
                                      </div>
                                    </div>
                                  )}
                                  </div>
                                );
                              })}
                            </div>
                          ) : (
                            <div className="rounded-xl border border-dashed border-white/10 py-8 text-center text-sm text-gray-500">
                              Nenhuma cobrança encontrada para esta assinatura.
                            </div>
                          )}
                        </div>
                      </div>
                    ) : (
                      <div className="space-y-5">
                        <p className="text-sm text-gray-500">
                          Nenhuma assinatura vinculada. Escolha o portador (Asaas ou Banco Inter) e configure a mensalidade.
                        </p>
                        <div>
                          <label className="mb-1.5 block text-[10px] font-bold uppercase tracking-wide text-gray-500">
                            Portador da cobrança
                          </label>
                          <select
                            name="billing_provider"
                            className={inputClass}
                            value={editProvedorForm.billing_provider || 'asaas'}
                            onChange={handleEditProvedorChange}
                          >
                            <option value="asaas">Asaas</option>
                            <option value="inter">Banco Inter</option>
                          </select>
                          <p className="mt-1 text-xs text-muted-foreground">
                            {isInterBilling(editProvedorForm)
                              ? 'O Superadmin emite a cobrança no Inter a cada ciclo (boleto + Pix).'
                              : 'O Asaas gerencia a assinatura recorrente automaticamente.'}
                          </p>
                        </div>
                        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
                          <div>
                            <label className="mb-1.5 block text-[10px] font-bold uppercase tracking-wide text-gray-500">Valor mensalidade</label>
                            <input type="number" name="subscription_value" className={inputClass} value={editProvedorForm.subscription_value} onChange={handleEditProvedorChange} placeholder="0.00" />
                          </div>
                          <div>
                            <label className="mb-1.5 block text-[10px] font-bold uppercase tracking-wide text-gray-500">Ciclo</label>
                            <select name="subscription_cycle" className={inputClass} value={editProvedorForm.subscription_cycle} onChange={handleEditProvedorChange}>
                              <option value="MONTHLY">Mensal</option>
                              <option value="QUARTERLY">Trimestral</option>
                              <option value="SEMIANNUALLY">Semestral</option>
                              <option value="YEARLY">Anual</option>
                            </select>
                          </div>
                          <div>
                            <label className="mb-1.5 block text-[10px] font-bold uppercase tracking-wide text-gray-500">1º vencimento</label>
                            <input type="date" name="subscription_next_due_date" className={inputClass} value={editProvedorForm.subscription_next_due_date} onChange={handleEditProvedorChange} />
                          </div>
                          <div>
                            <label className="mb-1.5 block text-[10px] font-bold uppercase tracking-wide text-gray-500">Pagamento</label>
                            <select name="subscription_billing_type" className={inputClass} value={editProvedorForm.subscription_billing_type} onChange={handleEditProvedorChange}>
                              <option value="BOLETO">Boleto</option>
                              <option value="PIX">PIX</option>
                              {!isInterBilling(editProvedorForm) && (
                                <option value="CREDIT_CARD">Cartão de Crédito</option>
                              )}
                            </select>
                          </div>
                        </div>
                        {isInterBilling(editProvedorForm) || editProvedorForm.asaas_customer_id ? (
                          <button
                            type="button"
                            onClick={handleCreateSubscription}
                            disabled={loadingEdit}
                            className="flex w-full items-center justify-center gap-2 rounded-xl bg-primary py-3 text-sm font-bold text-white shadow-lg shadow-primary/20 transition hover:bg-primary/90 disabled:opacity-50"
                          >
                            <TrendingUp className="h-4 w-4" />
                            {loadingEdit
                              ? 'Processando...'
                              : isInterBilling(editProvedorForm)
                                ? 'Criar assinatura no Banco Inter'
                                : 'Criar assinatura recorrente'}
                          </button>
                        ) : (
                          <button
                            type="button"
                            onClick={handleSyncAsaas}
                            disabled={loadingEdit}
                            className="flex w-full items-center justify-center gap-2 rounded-xl border border-sky-500/30 bg-sky-500/10 py-3 text-sm font-bold text-sky-200 transition hover:bg-sky-500/20 disabled:opacity-50"
                          >
                            <RefreshCw className={`h-4 w-4 ${loadingEdit ? 'animate-spin' : ''}`} />
                            {loadingEdit ? 'Sincronizando...' : 'Sincronizar cliente com Asaas'}
                          </button>
                        )}
                      </div>
                    )}
                    </div>
                  </div>

                  <div className="md:col-span-2 grid grid-cols-1 gap-3 sm:grid-cols-2">
                    <label className={`flex cursor-pointer items-start gap-3 rounded-xl border p-4 transition ${editProvedorForm.notification_disabled ? 'border-primary/40 bg-primary/10' : 'border-white/10 bg-[#14161c]/50 hover:border-white/20'}`}>
                      <input type="checkbox" name="notification_disabled" checked={editProvedorForm.notification_disabled} onChange={handleEditProvedorChange} className="mt-0.5 h-4 w-4 rounded border-border bg-[#181b20] text-primary focus:ring-primary/20" />
                      <span className="flex-1">
                        <span className="flex items-center gap-2 text-sm font-medium text-white">
                          <Bell className="h-4 w-4 text-primary" />
                          {isInterBilling(editProvedorForm)
                            ? 'Desativar notificações de cobrança'
                            : 'Desativar notificações Asaas'}
                        </span>
                        <span className="mt-1 block text-xs text-gray-500">Não envia e-mail/SMS de cobrança ao cliente.</span>
                      </span>
                    </label>
                    <label className={`flex cursor-pointer items-start gap-3 rounded-xl border p-4 transition ${editProvedorForm.foreign_customer ? 'border-primary/40 bg-primary/10' : 'border-white/10 bg-[#14161c]/50 hover:border-white/20'}`}>
                      <input type="checkbox" name="foreign_customer" checked={editProvedorForm.foreign_customer} onChange={handleEditProvedorChange} className="mt-0.5 h-4 w-4 rounded border-border bg-[#181b20] text-primary focus:ring-primary/20" />
                      <span className="flex-1">
                        <span className="flex items-center gap-2 text-sm font-medium text-white">
                          <Globe2 className="h-4 w-4 text-primary" />
                          Cliente estrangeiro
                        </span>
                        <span className="mt-1 block text-xs text-gray-500">
                          {isInterBilling(editProvedorForm)
                            ? 'Cadastro sem CPF/CNPJ brasileiro (Inter exige documento nacional).'
                            : 'Cadastro sem CPF/CNPJ brasileiro no Asaas.'}
                        </span>
                      </span>
                    </label>
                  </div>
                </div>
              </div>

              {errorMsg && (
                <div className="rounded-xl border border-red-500/25 bg-red-500/10 px-4 py-3 text-sm text-red-300">
                  {errorMsg}
                </div>
              )}
              </div>

              <div className="flex shrink-0 items-center justify-end gap-3 border-t border-white/10 bg-[#15181f]/95 px-6 py-4 backdrop-blur sm:px-8">
                <button
                  type="button"
                  onClick={() => setShowEditModal(false)}
                  className="rounded-xl px-5 py-2.5 text-sm font-semibold text-gray-400 transition hover:bg-white/5 hover:text-white"
                >
                  Cancelar
                </button>
                <button
                  type="submit"
                  className="rounded-xl bg-primary px-8 py-2.5 text-sm font-bold text-white shadow-lg shadow-primary/25 transition hover:bg-primary/90 disabled:opacity-50"
                  disabled={loadingEdit}
                >
                  {loadingEdit ? 'Salvando...' : 'Salvar alterações'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Tabela de provedores modernizada */}
      <div className="bg-card rounded-xl shadow-lg border border-border overflow-hidden">
        <div className="bg-gradient-to-r from-slate-900/20 to-gray-900/20 px-6 py-4 border-b border-border">
          <div className="flex justify-between items-center">
            <h3 className="text-lg font-semibold text-foreground flex items-center gap-2">
              <Users className="w-5 h-5 text-slate-400" />
              Lista de Provedores
            </h3>
            <button 
              onClick={() => {
                setReleaseJob(null);
                setUpdateForm((f) => ({ ...f, version: '' }));
                setShowUpdateModal(true);
              }}
              className="flex items-center gap-2 px-4 py-1.5 bg-primary/20 text-primary border border-primary/30 rounded-lg text-sm font-bold hover:bg-primary/30 transition-all shadow-sm"
            >
              <Zap className="w-4 h-4" />
              Gerenciar Atualizações
            </button>
          </div>
        </div>
        <div className="overflow-x-auto">
          <table className="min-w-full">
            <thead className="bg-muted/50">
              <tr>
                <th className="w-20 px-4 py-4 text-center text-xs font-semibold text-foreground uppercase tracking-wider">
                  <button
                    type="button"
                    onClick={() => toggleSort('id')}
                    className="inline-flex items-center justify-center gap-1 mx-auto hover:text-primary transition-colors"
                    title={sortDir === 'asc' ? 'Ordenar ID decrescente' : 'Ordenar ID 1, 2, 3…'}
                  >
                    ID
                    <ChevronsUpDown className={`w-3.5 h-3.5 ${sortKey === 'id' ? 'text-primary' : 'text-muted-foreground/70'}`} />
                  </button>
                </th>
                <th className="px-6 py-4 text-left text-xs font-semibold text-foreground uppercase tracking-wider">PROVEDOR</th>
                <th className="px-6 py-4 text-center text-xs font-semibold text-foreground uppercase tracking-wider">
                  <button
                    type="button"
                    onClick={() => toggleSort('vps')}
                    className="inline-flex items-center justify-center gap-1 mx-auto hover:text-primary transition-colors"
                    title={sortDir === 'asc' ? 'Ordenar VPS decrescente' : 'Ordenar VPS 1, 2, 3…'}
                  >
                    VPS
                    <ChevronsUpDown className={`w-3.5 h-3.5 ${sortKey === 'vps' ? 'text-primary' : 'text-muted-foreground/70'}`} />
                  </button>
                </th>
                <th className="px-6 py-4 text-center text-xs font-semibold text-foreground uppercase tracking-wider">SUBDOMÍNIO</th>
                <th className="px-6 py-4 text-center text-xs font-semibold text-foreground uppercase tracking-wider">VERSÃO / CANAL</th>
                <th className="px-6 py-4 text-center text-xs font-semibold text-foreground uppercase tracking-wider">USUÁRIOS</th>
                <th className="px-6 py-4 text-center text-xs font-semibold text-foreground uppercase tracking-wider">CONVERSAS</th>
                <th className="px-6 py-4 text-center text-xs font-semibold text-foreground uppercase tracking-wider">SOLUÇÕES</th>
                <th className="px-6 py-4 text-center text-xs font-semibold text-foreground uppercase tracking-wider">
                  <button
                    type="button"
                    onClick={() => toggleSort('vencimento')}
                    className="inline-flex items-center justify-center gap-1 mx-auto hover:text-primary transition-colors"
                    title={sortDir === 'asc' ? 'Ordenar vencimento decrescente' : 'Ordenar vencimento crescente'}
                  >
                    VENCIMENTO
                    <ChevronsUpDown className={`w-3.5 h-3.5 ${sortKey === 'vencimento' ? 'text-primary' : 'text-muted-foreground/70'}`} />
                  </button>
                </th>
                <th className="px-6 py-4 text-center text-xs font-semibold text-foreground uppercase tracking-wider">PORTADOR</th>
                <th className="px-6 py-4 text-center text-xs font-semibold text-foreground uppercase tracking-wider">STATUS</th>
                <th className="px-6 py-4 text-center text-xs font-semibold text-foreground uppercase tracking-wider">AÇÕES</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {filteredProvedores.map(provedor => (
                <tr key={provedor.id} className="hover:bg-muted/50">
                  <td className="w-20 px-4 py-4 text-center align-middle">
                    <span
                      className="inline-flex min-w-[2.75rem] items-center justify-center rounded-lg border border-sky-500/25 bg-sky-500/10 px-2.5 py-1 font-mono text-sm font-bold tabular-nums text-sky-300"
                      title={`Provedor #${provedor.id}`}
                    >
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
                    <span className="inline-flex px-2 py-1 rounded bg-muted text-xs font-semibold tabular-nums">
                      {provedor.vps_number ? `VPS ${provedor.vps_number}` : '—'}
                    </span>
                  </td>
                  <td className="px-6 py-4 text-center align-middle text-foreground">
                    <span className="inline-flex px-2 py-1 rounded bg-muted text-xs">
                      {getProviderSubdomain(provedor) || '-'}
                    </span>
                  </td>
                  <td className="px-6 py-4 text-center align-middle text-foreground">
                    <div className="flex flex-col items-center gap-1">
                      <span className="text-[10px] font-mono font-bold text-primary">
                        {provedor.current_version && provedor.current_version !== '1.0.0'
                          ? `v${provedor.current_version}`
                          : '—'}
                      </span>
                      <span className={`px-2 py-0.5 rounded-full text-[9px] font-bold uppercase ${
                        provedor.release_channel === 'beta' ? 'bg-primary/20 text-primary border border-primary/30' :
                        provedor.release_channel === 'manual' ? 'bg-orange-500/20 text-orange-400 border border-orange-500/30' :
                        'bg-blue-500/20 text-blue-400 border border-blue-500/30'
                      }`}>
                        {provedor.release_channel || 'stable'}
                      </span>
                    </div>
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
                    <div className="flex flex-wrap items-center justify-center gap-1">
                      {provedor.chat_enabled !== false && (
                        <span className="inline-flex items-center gap-0.5 px-2 py-1 rounded text-[10px] font-bold uppercase bg-orange-500/15 text-orange-300 border border-orange-500/25">
                          <MessageSquare className="w-3 h-3" /> Chat
                        </span>
                      )}
                      {provedor.mobile_app_enabled ? (
                        <span className="inline-flex items-center gap-0.5 px-2 py-1 rounded text-[10px] font-bold uppercase bg-sky-500/15 text-sky-400 border border-sky-500/25">
                          <Smartphone className="w-3 h-3" /> App
                        </span>
                      ) : null}
                      {provedor.acs_enabled ? (
                        <span className="inline-flex items-center gap-0.5 px-2 py-1 rounded text-[10px] font-bold uppercase bg-violet-500/15 text-violet-300 border border-violet-500/25">
                          <Router className="w-3 h-3" /> ACS
                        </span>
                      ) : null}
                      {provedor.chat_enabled === false && !provedor.mobile_app_enabled && !provedor.acs_enabled && (
                        <span className="text-xs text-muted-foreground">—</span>
                      )}
                    </div>
                  </td>
                  <td className="px-6 py-4 text-center align-middle">
                    {(() => {
                      const due = provedor.subscription_next_due_date;
                      if (!due) {
                        return <span className="text-xs text-muted-foreground">—</span>;
                      }
                      const [y, m, d] = String(due).split('-');
                      const label = y && m && d ? `${d}/${m}/${y}` : due;
                      const today = new Date();
                      today.setHours(0, 0, 0, 0);
                      const dueDate = new Date(`${due}T12:00:00`);
                      const diffDays = Math.round((dueDate - today) / 86400000);
                      let tone = 'bg-muted text-foreground border-border';
                      if (diffDays < 0) tone = 'bg-red-500/15 text-red-300 border-red-500/30';
                      else if (diffDays === 0) tone = 'bg-amber-500/15 text-amber-300 border-amber-500/30';
                      else if (diffDays <= 3) tone = 'bg-orange-500/15 text-orange-300 border-orange-500/30';
                      else tone = 'bg-emerald-500/15 text-emerald-300 border-emerald-500/30';
                      const hint =
                        diffDays < 0
                          ? `${Math.abs(diffDays)}d atraso`
                          : diffDays === 0
                            ? 'Hoje'
                            : diffDays === 1
                              ? 'Amanhã'
                              : `em ${diffDays}d`;
                      return (
                        <div className="flex flex-col items-center gap-0.5">
                          <span className={`inline-flex px-2.5 py-1 rounded-md text-xs font-semibold tabular-nums border ${tone}`}>
                            {label}
                          </span>
                          <span className="text-[10px] text-muted-foreground">{hint}</span>
                        </div>
                      );
                    })()}
                  </td>
                  <td className="px-6 py-4 text-center align-middle">
                    {(() => {
                      const inter = isInterBilling(provedor);
                      const hasSub = Boolean(provedor.asaas_subscription_id);
                      if (!hasSub && !provedor.billing_provider) {
                        return <span className="text-xs text-muted-foreground">—</span>;
                      }
                      return (
                        <span
                          className={`inline-flex px-2.5 py-1 rounded-full text-[10px] font-bold uppercase tracking-wide border ${
                            inter
                              ? 'bg-orange-500/15 text-orange-300 border-orange-500/30'
                              : 'bg-emerald-500/15 text-emerald-300 border-emerald-500/30'
                          }`}
                          title={inter ? 'Cobranças no Banco Inter' : 'Cobranças no Asaas'}
                        >
                          {inter ? 'Inter' : 'Asaas'}
                        </span>
                      );
                    })()}
                  </td>
                  <td className="px-6 py-4 text-center align-middle">
                    <button
                      className={`px-3 py-1 rounded-full text-xs font-semibold focus:outline-none transition-colors duration-200 ${provedor.is_active !== false ? 'bg-green-100 text-green-800' : 'bg-red-100 text-red-800'}`}
                      style={{ cursor: 'pointer' }}
                      onClick={async (e) => {
                        e.stopPropagation();
                        try {
                          const token = localStorage.getItem('token');
                          const nextActive = provedor.is_active === false;
                          await axios.patch(
                            `/api/provedores/${provedor.id}/`,
                            {
                              is_active: nextActive,
                              status: nextActive ? 'ativo' : 'suspenso',
                            },
                            { headers: { Authorization: `Token ${token}` } }
                          );
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
            className="flex items-center gap-2 w-full px-3 py-1.5 text-left hover:bg-muted text-sm text-primary"
            onClick={(e) => {
              e.stopPropagation();
              const prov = filteredProvedores.find((p) => p.id === menuId);
              setMenuId(null);
              if (prov) openProviderAppPanel(prov.id);
            }}
          >
            <Smartphone className="w-4 h-4" /> Painel do App
          </button>
          <button 
            className={`flex items-center gap-2 w-full px-3 py-1.5 text-left hover:bg-muted text-sm border-y border-border/50 ${filteredProvedores.find(p => p.id === menuId)?.asaas_customer_id ? 'text-green-500' : 'text-orange-500'}`}
            onClick={e => { e.stopPropagation(); handleSyncAsaas(menuId); setMenuId(null); }}
          >
            <Database className="w-4 h-4" /> 
            {filteredProvedores.find(p => p.id === menuId)?.asaas_customer_id ? 'Re-sincronizar Asaas' : 'Sincronizar Asaas'}
          </button>
          <button
            className="flex items-center gap-2 w-full px-3 py-1.5 text-left hover:bg-muted text-sm border-y border-border/50"
            onClick={e => {
              e.stopPropagation();
              const prov = filteredProvedores.find(p => p.id === menuId);
              if (prov) openIntegrationTokenModal(prov);
              setMenuId(null);
            }}
          >
            <KeyRound className="w-4 h-4 text-primary" /> Token Integração
          </button>
          <button className="flex items-center gap-2 w-full px-3 py-1.5 text-left hover:bg-muted text-sm" onClick={e => { e.stopPropagation(); handleEditProvedor(filteredProvedores.find(p => p.id === menuId)); setMenuId(null); }}>
            <Edit className="w-4 h-4" /> Editar
          </button>
          <button 
            className="flex items-center gap-2 w-full px-3 py-1.5 text-left bg-primary/20 hover:bg-primary/30 text-primary-foreground text-sm font-bold" 
            onClick={e => { e.stopPropagation(); handleDeploy(menuId); setMenuId(null); }}
          >
            <Plus className="w-4 h-4" /> Iniciar Deploy
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

      {/* Modal Token Integração */}
      {showTokenModal && tokenProvedor && (
        <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50 p-4">
          <div className="bg-[#23272f] rounded-xl shadow-2xl w-full max-w-lg relative border border-border">
            <button
              className="absolute top-2 right-2 text-gray-400 hover:text-white text-3xl"
              onClick={() => { setShowTokenModal(false); setTokenProvedor(null); setPlainToken(''); setTokenError(''); }}
            >
              &times;
            </button>

            <div className="p-6 border-b border-border">
              <h2 className="text-xl font-bold text-white flex items-center gap-2">
                <KeyRound className="w-5 h-5 text-primary" />
                Token de Integração
              </h2>
              <p className="text-xs text-gray-400 mt-1">
                Provedor: <span className="text-gray-200 font-semibold">{tokenProvedor.nome}</span>
              </p>
            </div>

            <div className="p-6 space-y-4">
              {tokenError && (
                <div className="text-red-300 text-sm bg-red-500/10 border border-red-500/20 rounded-lg p-3">
                  {tokenError}
                </div>
              )}

              <div className="bg-black/20 border border-white/10 rounded-lg p-4">
                <p className="text-xs text-gray-400 uppercase font-bold mb-2">Status</p>
                <div className="flex items-center justify-between gap-3">
                  <div>
                    <p className="text-sm text-white">
                      {loadingToken ? 'Carregando...' : (tokenStatus.configured ? 'Configurado' : 'Não configurado')}
                    </p>
                    <p className="text-xs text-gray-400 mt-1">
                      {tokenStatus.masked ? `Masc: ${tokenStatus.masked}` : 'Masc: -'}
                    </p>
                    <p className="text-xs text-gray-400 mt-1">
                      Último uso: {tokenStatus.last_used_at ? new Date(tokenStatus.last_used_at).toLocaleString('pt-BR') : '-'}
                    </p>
                  </div>
                  <button
                    onClick={rotateIntegrationToken}
                    disabled={loadingToken}
                    className="px-4 py-2 rounded-lg bg-primary hover:bg-primary/90 text-primary-foreground text-sm font-bold disabled:opacity-50 flex items-center gap-2"
                  >
                    <RefreshCw className={`w-4 h-4 ${loadingToken ? 'animate-spin' : ''}`} />
                    Rotacionar
                  </button>
                </div>
              </div>

              {plainToken && (
                <div className="bg-green-500/10 border border-green-500/20 rounded-lg p-4">
                  <p className="text-xs text-green-300 uppercase font-bold mb-2">Novo token (mostrado uma vez)</p>
                  <div className="flex items-center gap-2">
                    <input
                      className="flex-1 px-3 py-2 rounded bg-[#181b20] text-white border border-border font-mono text-xs"
                      value={plainToken}
                      readOnly
                    />
                    <button
                      className="px-3 py-2 rounded bg-white/10 hover:bg-white/15 text-white text-sm flex items-center gap-2"
                      onClick={() => copyToClipboard(plainToken)}
                      title="Copiar"
                    >
                      <Copy className="w-4 h-4" /> Copiar
                    </button>
                  </div>
                  <p className="text-[11px] text-green-200 mt-2">
                    O tenant será atualizado automaticamente via redeploy disparado no backend.
                  </p>
                </div>
              )}
            </div>
          </div>
        </div>
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
                <div className="bg-orange-950/30 border border-primary/30 rounded-lg p-4">
                  <h3 className="font-semibold text-foreground mb-2 flex items-center gap-2">
                    <FileText className="w-4 h-4" />
                    Logs de Auditoria
                  </h3>
                  <p className="text-muted-foreground text-xs mb-3">
                    Remove TODOS os logs de auditoria (core_auditlog) deste provedor
                  </p>
                  <button
                    onClick={() => handleExecutarLimpeza('auditlog')}
                    disabled={loadingLimpeza}
                    className="w-full bg-primary hover:bg-primary/90 text-primary-foreground py-2 px-4 rounded text-sm font-medium disabled:opacity-50 disabled:cursor-not-allowed"
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
      {/* Modal de Gestão de Atualizações */}
      {showUpdateModal && (
        <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50 p-4">
          <div className="bg-[#23272f] rounded-xl shadow-2xl w-full max-w-lg relative border border-border flex flex-col max-h-[90vh]">
            <div className="p-6 border-b border-border flex justify-between items-center shrink-0">
              <h2 className="text-xl font-bold text-white flex items-center gap-2">
                <Zap className="w-5 h-5 text-primary" />
                Liberar Nova Versão
              </h2>
              <button
                className="text-gray-400 hover:text-white text-3xl"
                onClick={() => {
                  if (loadingUpdate) return;
                  setShowUpdateModal(false);
                }}
              >
                &times;
              </button>
            </div>
            
            <div className="p-8 space-y-6 overflow-y-auto">
              <div className="bg-blue-900/10 border border-blue-500/20 p-4 rounded-lg space-y-2">
                <p className="text-sm text-blue-200">
                  Atualiza <strong>1 provedor por vez</strong>: redeploy no Portainer, espera a stack nova subir, apaga containers <strong>exited</strong> e só então segue o próximo — para não travar a VPS.
                </p>
                <p className="text-xs text-blue-200/80">
                  {updateForm.channel === 'stable'
                    ? 'Stable: puxa a versão digitada (ex. 2.59.0) e aponta :stable no registry. Para voltar todos, informe a versão anterior que o CI já publicou.'
                    : 'Beta: pull/redeploy no Portainer com :beta-prov. O CI também dispara este canal automaticamente (1 por vez).'}
                </p>
              </div>

              <div>
                <label className="block text-xs font-semibold text-gray-400 uppercase mb-2">Canal Alvo</label>
                <select 
                  className="w-full px-4 py-2 rounded bg-[#181b20] text-white border border-border"
                  value={updateForm.channel}
                  disabled={loadingUpdate}
                  onChange={(e) => setUpdateForm({...updateForm, channel: e.target.value})}
                >
                  <option value="beta">Beta (Atualização automática)</option>
                  <option value="stable">Stable (Atualização controlada)</option>
                </select>
                <p className="text-xs text-muted-foreground mt-2">
                  {channelTargets.length} provedor(es) neste canal
                  {channelTargets.length - channelWithVps.length > 0
                    ? ` · ${channelTargets.length - channelWithVps.length} sem VPS (serão ignorados)`
                    : ''}
                </p>
              </div>

              <div>
                <label className="block text-xs font-semibold text-gray-400 uppercase mb-2">Número da Versão</label>
                <input 
                  type="text" 
                  className="w-full px-4 py-2 rounded bg-[#181b20] text-white border border-border font-mono"
                  placeholder="Ex: 2.59.0"
                  value={updateForm.version}
                  disabled={loadingUpdate}
                  onChange={(e) => setUpdateForm({...updateForm, version: e.target.value})}
                />
                {updateForm.channel === 'stable' && (
                  <p className="text-xs text-muted-foreground mt-2">
                    Avançar: versão atual. Rollback: versão antiga (precisa existir no GHCR, ex. 2.58.0).
                  </p>
                )}
              </div>

              {releaseJob?.results?.length > 0 && (
                <div className="rounded-lg border border-border bg-[#181b20] p-3 space-y-1 max-h-48 overflow-y-auto">
                  {releaseJob.results.map((row) => (
                    <div key={`${row.id}-${row.status}`} className="flex justify-between text-xs gap-2">
                      <span className="text-white truncate">{row.nome}</span>
                      <span className={
                        row.status === 'success' ? 'text-emerald-400' :
                        row.status === 'no_vps' || row.status === 'no_subdomain' ? 'text-amber-400' :
                        'text-red-400'
                      }>
                        {row.status}{row.msg ? `: ${row.msg}` : ''}
                      </span>
                    </div>
                  ))}
                </div>
              )}
              {releaseJob?.promote_log && releaseJob.promote_ok === false && (
                <pre className="text-[11px] text-red-300 bg-red-950/30 border border-red-500/20 rounded p-2 overflow-auto max-h-28 whitespace-pre-wrap">
                  {releaseJob.promote_log}
                </pre>
              )}
              {releaseJob?.status && (
                <p className="text-xs text-muted-foreground">
                  Status: <span className="text-white font-mono">{releaseJob.status}</span>
                  {releaseJob.status === 'done' ? ' · redeploy Portainer' : ''}
                </p>
              )}

              <div className="pt-2">
                <button 
                  onClick={async () => {
                    const label = updateForm.channel === 'stable' ? 'STABLE (todos os clientes)' : 'BETA';
                    if (!updateForm.version.trim()) {
                      alert('Informe o número da versão.');
                      return;
                    }
                    if (!window.confirm(`Atualizar ${channelWithVps.length} provedor(es) do canal ${label} para ${updateForm.version}?`)) return;
                    setLoadingUpdate(true);
                    setReleaseJob(null);
                    const token = localStorage.getItem('token');
                    try {
                      const res = await axios.post('/api/system-updates/release/', updateForm, {
                        headers: { Authorization: `Token ${token}` }
                      });
                      const jobId = res.data?.id;
                      setReleaseJob(res.data);
                      if (!jobId) {
                        throw new Error('Release sem id');
                      }
                      const started = Date.now();
                      while (Date.now() - started < 15 * 60 * 1000) {
                        await new Promise((r) => setTimeout(r, 3000));
                        const poll = await axios.get(`/api/system-updates/${jobId}/`, {
                          headers: { Authorization: `Token ${token}` }
                        });
                        setReleaseJob(poll.data);
                        const st = poll.data?.status;
                        if (st === 'done' || st === 'failed') break;
                      }
                      const resList = await axios.get('/api/provedores/', {
                        headers: { Authorization: `Token ${token}` }
                      });
                      setProvedoresState(resList.data.results || resList.data);
                    } catch (err) {
                      alert('Erro ao processar atualização: ' + (err.response?.data?.error || err.message));
                    } finally {
                      setLoadingUpdate(false);
                    }
                  }}
                  disabled={loadingUpdate || !updateForm.version}
                  className="w-full bg-primary hover:bg-primary/90 text-primary-foreground py-3 rounded-xl font-bold transition shadow-lg flex items-center justify-center gap-2 disabled:opacity-50"
                >
                  <RefreshCw className={`w-5 h-5 ${loadingUpdate ? 'animate-spin' : ''}`} />
                  {loadingUpdate ? 'Atualizando provedores...' : 'Iniciar atualização em massa'}
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}