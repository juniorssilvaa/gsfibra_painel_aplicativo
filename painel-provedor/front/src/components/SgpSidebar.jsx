import { useState, useEffect, useCallback, useRef } from 'react';
import {
  User,
  RotateCcw,
  HeadphonesIcon,
  Barcode,
  QrCode,
  Wifi,
  ChevronsLeft,
  ChevronsRight,
  X,
  Check,
  Pencil,
  Globe,
  MessageCircle,
  Eye,
  EyeOff,
} from 'lucide-react';
import { toast } from '../lib/notify';
import axios from 'axios';
import {
  CONVERSATION_ACTION_BTN_BASE,
  paymentActionStyle,
} from '../constants/conversationActionButtons';
import whatsappIcon from '../assets/whatsapp.png';
import instagramIcon from '../assets/instagram.png';
import telegramIcon from '../assets/telegram.png';
import gmailIcon from '../assets/gmail.png';
import appMobileIcon from '../assets/app-mobile.png';
import inicioIconUrl from '../assets/sidepanel/inicio.png';
import financeiroIconUrl from '../assets/sidepanel/financeiro.png';

const maskIcon = (src) => {
  const mask = `url(${src}) center / contain no-repeat`;
  const MaskIcon = ({ className = '' }) => (
    <span aria-hidden="true" className={`inline-block bg-current ${className}`} style={{ WebkitMask: mask, mask }} />
  );
  return MaskIcon;
};
const CHANNEL_META = {
  whatsapp: { label: 'WhatsApp', img: whatsappIcon },
  whatsapp_oficial: { label: 'WhatsApp Oficial', img: whatsappIcon },
  instagram: { label: 'Instagram', img: instagramIcon },
  telegram: { label: 'Telegram', img: telegramIcon },
  email: { label: 'E-mail', img: gmailIcon },
  app_mobile: { label: 'App', img: appMobileIcon },
  webchat: { label: 'Chat Web', Icon: Globe },
  facebook: { label: 'Facebook', Icon: MessageCircle },
};

const InicioIcon = maskIcon(inicioIconUrl);
const FinanceiroIcon = maskIcon(financeiroIconUrl);

const sgpTabClass = (active) =>
  `w-full flex items-center justify-center px-2 py-3 rounded-lg transition-colors ${
    active
      ? 'bg-sidebar-accent text-sidebar-accent-foreground'
      : 'text-sidebar-foreground hover:bg-sidebar-accent hover:text-sidebar-accent-foreground'
  }`;

const SGP_CARD = 'bg-card rounded-xl p-4 shadow-sm border border-border';
const SGP_CARD_HEADER = 'flex justify-between items-center border-b border-border pb-3 mb-4';
const SGP_TITLE = 'text-sm font-semibold text-foreground';
const SGP_MUTED = 'text-xs text-muted-foreground';
const SGP_VALUE = 'text-xs font-medium text-foreground';
const SGP_SELECT =
  'w-full bg-background border border-input rounded-lg p-2.5 text-sm text-foreground shadow-sm focus:outline-none focus:ring-2 focus:ring-primary/25 appearance-none';
const SGP_INPUT =
  'w-full bg-background border border-input rounded-lg px-2.5 py-2 text-sm text-foreground shadow-sm focus:outline-none focus:ring-2 focus:ring-primary/25 placeholder:text-muted-foreground [&:-webkit-autofill]:shadow-[inset_0_0_0_1000px_var(--background)] [&:-webkit-autofill]:[-webkit-text-fill-color:var(--foreground)] [&:-webkit-autofill]:[caret-color:var(--foreground)]';
const SGP_ROW = 'flex justify-between items-center border-b border-border/70 pb-2';
const SGP_PAY_ACTION_BTN = `${CONVERSATION_ACTION_BTN_BASE} w-full justify-center h-9`;
const SGP_PRIMARY_BTN =
  'w-full bg-primary text-primary-foreground hover:opacity-90 py-2.5 rounded-lg text-sm font-semibold shadow-sm transition-opacity disabled:opacity-50';
const SGP_SECONDARY_BTN =
  'w-full border border-border bg-background hover:bg-muted text-foreground py-2 rounded-lg text-xs font-semibold transition-colors disabled:opacity-50';
const SGP_SPINNER = 'w-6 h-6 animate-spin mx-auto text-primary opacity-60';

const getContratoId = (c) =>
  c?.contratoId || c?.id || c?.id_contrato || c?.contrato_id || c?.codigo || '';

const getPlanoNome = (c) =>
  c?.plano_nome ||
  c?.servico_plano ||
  c?.planointernet ||
  c?.planoInternet ||
  c?.nomePlano ||
  c?.plano ||
  c?.servico ||
  '';

const getPppoeLogin = (c) => {
  for (const key of ['servico_login', 'pppoe_login', 'login', 'usuario', 'usuario_pppoe', 'login_pppoe', 'user']) {
    const val = c?.[key];
    if (val !== undefined && val !== null && String(val).trim()) return String(val).trim();
  }
  return '';
};

const cleanAddrPart = (value) => {
  const text = value == null ? '' : String(value).trim();
  if (!text || ['none', 'null', 'undefined'].includes(text.toLowerCase())) return '';
  return text;
};

const getContratoEnderecoCurto = (c) => {
  if (!c) return '';
  const tipo = cleanAddrPart(c.endereco_tipo_logradouro);
  const rua = cleanAddrPart(c.endereco_logradouro || c.logradouro || c.rua);
  const numero = cleanAddrPart(c.endereco_numero || c.numero);
  const ruaLinha = [tipo, rua].filter(Boolean).join(' ');
  if (ruaLinha) return [ruaLinha, numero].filter(Boolean).join(', ');
  return cleanAddrPart(c.endereco_bairro || c.bairro || c.endereco_cidade || c.cidade);
};

const parseFaturaVencimento = (fatura) => {
  const raw = fatura?.vencimento_br || fatura?.vencimento || fatura?.data_vencimento || '';
  const text = String(raw || '').trim();
  if (!text) return null;
  if (text.includes('/')) {
    const [d, m, y] = text.split('/');
    const date = new Date(Number(y), Number(m) - 1, Number(d));
    return Number.isNaN(date.getTime()) ? null : date;
  }
  if (text.includes('-')) {
    const [y, m, d] = text.split('-');
    const date = new Date(Number(y), Number(m) - 1, Number(d));
    return Number.isNaN(date.getTime()) ? null : date;
  }
  return null;
};

const getFaturaStatusKind = (fatura) => {
  const label = String(fatura?.status_label || fatura?.status || '').toLowerCase();
  if (label.includes('atraso') || label.includes('vencid') || label.includes('overdue')) return 'atraso';
  const venc = parseFaturaVencimento(fatura);
  if (venc) {
    const today = new Date();
    today.setHours(0, 0, 0, 0);
    venc.setHours(0, 0, 0, 0);
    if (venc < today) return 'atraso';
  }
  if (!label || label.includes('aberto')) return 'aberto';
  return 'outro';
};

const formatDateTime = (iso) => {
  if (!iso) return '—';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return '—';
  return d.toLocaleString('pt-BR', { day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit' });
};

const authHeaders = () => ({
  Authorization: `Token ${localStorage.getItem('auth_token') || localStorage.getItem('token')}`,
});

const ConnectionBadge = ({ status, loading }) => {
  if (loading) {
    return (
      <div className="flex items-center gap-1.5 text-[10px] text-muted-foreground">
        <RotateCcw className="h-3 w-3 animate-spin" />
        Verificando...
      </div>
    );
  }

  const connection = status?.connection;
  if (connection === 'online') {
    return (
      <div className="bg-[#20362c] text-[#4ade80] px-2 py-0.5 rounded-full text-[10px] font-bold flex items-center gap-1.5 border border-[#4ade80]/20">
        <div className="w-1.5 h-1.5 rounded-full bg-[#4ade80]" />
        {status?.label || 'Serviço Online'}
      </div>
    );
  }
  if (connection === 'manutencao') {
    return (
      <div className="bg-[#362e20] text-[#fbbf24] px-2 py-0.5 rounded-full text-[10px] font-bold flex items-center gap-1.5 border border-[#fbbf24]/20">
        <div className="w-1.5 h-1.5 rounded-full bg-[#fbbf24]" />
        {status?.label || 'Manutenção'}
      </div>
    );
  }
  if (connection === 'unknown') {
    return (
      <div className="bg-muted text-muted-foreground px-2 py-0.5 rounded-full text-[10px] font-bold flex items-center gap-1.5 border border-border">
        <div className="w-1.5 h-1.5 rounded-full bg-muted-foreground" />
        {status?.label || 'Indisponível'}
      </div>
    );
  }
  return (
    <div className="bg-[#362020] text-[#f87171] px-2 py-0.5 rounded-full text-[10px] font-bold flex items-center gap-1.5 border border-[#f87171]/20">
      <div className="w-1.5 h-1.5 rounded-full bg-[#f87171]" />
      {status?.label || 'Offline'}
    </div>
  );
};

const StatusPill = ({ ok, okLabel, badLabel }) => (
  ok ? (
    <div className="bg-[#20362c] text-[#4ade80] px-2 py-0.5 rounded-full text-[10px] font-bold flex items-center gap-1.5 border border-[#4ade80]/20">
      <div className="w-1.5 h-1.5 rounded-full bg-[#4ade80]" />
      {okLabel}
    </div>
  ) : (
    <div className="bg-[#362020] text-[#f87171] px-2 py-0.5 rounded-full text-[10px] font-bold flex items-center gap-1.5 border border-[#f87171]/20">
      <div className="w-1.5 h-1.5 rounded-full bg-[#f87171]" />
      {badLabel}
    </div>
  )
);

const TagEditor = ({ tags, onChange, placeholder }) => {
  const [value, setValue] = useState('');
  const add = () => {
    const tag = value.trim();
    if (!tag) return;
    if (!tags.some((t) => t.toLowerCase() === tag.toLowerCase())) onChange([...tags, tag]);
    setValue('');
  };
  return (
    <div className="space-y-2">
      {tags.length > 0 && (
        <div className="flex flex-wrap gap-1.5">
          {tags.map((tag) => (
            <span key={tag} className="inline-flex items-center gap-1 bg-primary/10 text-primary border border-primary/25 rounded-full px-2 py-0.5 text-[11px] font-medium">
              {tag}
              <button type="button" onClick={() => onChange(tags.filter((t) => t !== tag))} className="hover:text-destructive" title="Remover tag">
                <X className="w-3 h-3" />
              </button>
            </span>
          ))}
        </div>
      )}
      <input
        className={SGP_INPUT}
        placeholder={placeholder}
        value={value}
        onChange={(e) => setValue(e.target.value)}
        onKeyDown={(e) => { if (e.key === 'Enter') { e.preventDefault(); add(); } }}
        onBlur={add}
      />
    </div>
  );
};

const SgpSidebar = ({
  conversation,
  user,
  messages = [],
  expanded = true,
  onToggleExpanded,
  onConversationUpdate,
  billingSource = 'sgp',
  contactName,
  onSaveContactName,
  contactNameNeedsEdit = false,
}) => {
  const isAsaas = billingSource === 'asaas';
  const apiBase = isAsaas ? '/api/asaas-support' : '/api/sgp';
  const [documento, setDocumento] = useState('');
  const [loading, setLoading] = useState(false);
  const [activeTab, setActiveTab] = useState(() => localStorage.getItem('niochat_sidePanelTab') || 'inicio');
  const [ticketType, setTicketType] = useState('');
  const [tiposOcorrencia, setTiposOcorrencia] = useState(null);
  const [loadingTipos, setLoadingTipos] = useState(false);
  const [ticketDescription, setTicketDescription] = useState('');
  const [openingTicket, setOpeningTicket] = useState(false);

  const [clienteData, setClienteData] = useState(null);
  const [selectedContrato, setSelectedContrato] = useState(null);
  const [faturas, setFaturas] = useState([]);
  const [selectedFaturaId, setSelectedFaturaId] = useState(null);
  const [asaasClientes, setAsaasClientes] = useState(null);
  const [loadingFaturas, setLoadingFaturas] = useState(false);
  const [loadingConexao, setLoadingConexao] = useState(false);

  const rootRef = useRef(null);

  useEffect(() => {
    if (!expanded || typeof onToggleExpanded !== 'function') return undefined;
    const handlePointerDown = (e) => {
      if (window.matchMedia('(min-width: 1536px)').matches) return;
      if (rootRef.current && !rootRef.current.contains(e.target)) onToggleExpanded();
    };
    document.addEventListener('mousedown', handlePointerDown);
    return () => document.removeEventListener('mousedown', handlePointerDown);
  }, [expanded, onToggleExpanded]);

  const [panelInfo, setPanelInfo] = useState(null);
  const [contactForm, setContactForm] = useState({ email: '', anotacoes: '' });
  const [editingName, setEditingName] = useState(null);
  const [savingName, setSavingName] = useState(false);

  useEffect(() => {
    setEditingName(null);
  }, [conversation?.id]);

  const [wifiData, setWifiData] = useState(null);
  const [wifiError, setWifiError] = useState('');
  const [loadingWifi, setLoadingWifi] = useState(false);
  const [savingWifi, setSavingWifi] = useState(false);
  const [showPasswords, setShowPasswords] = useState(false);
  const [wifiForm, setWifiForm] = useState({ ssid_24: '', pass_24: '', ssid_5: '', pass_5: '' });

  const handleReset = () => {
    setClienteData(null);
    setDocumento('');
    setSelectedContrato(null);
    setFaturas([]);
    setSelectedFaturaId(null);
    setAsaasClientes(null);
    setWifiData(null);
    setWifiError('');
    setTicketType('');
    setTiposOcorrencia(null);
    setActiveTab('cliente');
  };

  const provedorId = user?.provedor_id || user?.provedores_admin?.[0]?.id;

  useEffect(() => {
    if (isAsaas && (activeTab === 'suporte' || activeTab === 'wifi')) {
      setActiveTab('cliente');
    }
  }, [isAsaas, activeTab]);

  useEffect(() => {
    localStorage.setItem('niochat_sidePanelTab', activeTab);
  }, [activeTab]);

  const selectTab = (tab) => {
    setActiveTab(tab);
    if (!expanded && typeof onToggleExpanded === 'function') onToggleExpanded();
  };

  // === Aba Início: contato + atendimento ===
  const applyPanelInfo = (data) => {
    setPanelInfo(data);
    setContactForm({
      email: data?.contact?.email || '',
      anotacoes: data?.contact?.anotacoes || '',
    });
  };

  useEffect(() => {
    setPanelInfo(null);
    if (!conversation?.id) return;
    let cancelled = false;
    axios
      .get(`/api/conversations/${conversation.id}/panel-info/`, { headers: authHeaders() })
      .then((res) => { if (!cancelled) applyPanelInfo(res.data); })
      .catch(() => {});
    return () => { cancelled = true; };
  }, [conversation?.id, conversation?.assignee?.id]);

  const savePanelInfo = async (payload) => {
    if (!conversation?.id) return;
    try {
      const res = await axios.post(`/api/conversations/${conversation.id}/panel-info/`, payload, { headers: authHeaders() });
      applyPanelInfo(res.data);
    } catch (e) {
      toast.apiError(e, 'Não foi possível salvar.');
    }
  };

  const saveContactField = (field) => {
    const current = panelInfo?.contact?.[field] || '';
    if ((contactForm[field] || '') === current) return;
    savePanelInfo({ contact: { [field]: contactForm[field] } });
  };

  // === SGP / Asaas ===
  const verificarConexao = useCallback(async (contratoId) => {
    if (isAsaas || !contratoId || !provedorId) return null;
    setLoadingConexao(true);
    try {
      const response = await axios.get(
        `/api/sgp/verifica-acesso/?contrato_id=${contratoId}&provedor_id=${provedorId}`,
        { headers: authHeaders() },
      );
      return response.data;
    } catch (error) {
      return { connection: 'unknown', label: 'Indisponível' };
    } finally {
      setLoadingConexao(false);
    }
  }, [provedorId, isAsaas]);

  const carregarFaturas = async (contratoId, doc, prefetched = null) => {
    if (Array.isArray(prefetched)) {
      setFaturas(prefetched);
      setSelectedFaturaId(prefetched[0]?.fatura || prefetched[0]?.id || null);
      return;
    }
    if (isAsaas) {
      setFaturas([]);
      setSelectedFaturaId(null);
      return;
    }
    setLoadingFaturas(true);
    try {
      const response = await axios.get(`/api/sgp/faturas/?contrato_id=${contratoId}&cpfcnpj=${doc}&provedor_id=${provedorId}`, {
        headers: authHeaders()
      });
      const list = response.data?.links || response.data?.faturas || [];
      setFaturas(list);
      setSelectedFaturaId(list[0]?.fatura || list[0]?.id || null);
    } catch (error) {
    } finally {
      setLoadingFaturas(false);
    }
  };

  const selecionarContrato = useCallback(async (contrato, doc, prefetchedFaturas = null) => {
    if (!contrato) return;
    const cId = getContratoId(contrato);
    setSelectedContrato({
      ...contrato,
      plano_nome: getPlanoNome(contrato) || contrato.plano_nome,
    });
    setWifiData(null);
    setWifiError('');
    await carregarFaturas(cId, doc, prefetchedFaturas);
    if (isAsaas) return;
    const conexao = await verificarConexao(cId);
    if (conexao) {
      setSelectedContrato((prev) =>
        prev && getContratoId(prev) === cId
          ? { ...prev, status_conexao_realtime: conexao }
          : prev,
      );
      setClienteData((prev) => {
        if (!prev?.contratos) return prev;
        return {
          ...prev,
          contratos: prev.contratos.map((c) =>
            getContratoId(c) === cId ? { ...c, status_conexao_realtime: conexao } : c,
          ),
        };
      });
    }
  }, [verificarConexao, isAsaas, provedorId]);

  const buscarCliente = useCallback(async (doc, customerId = null) => {
    if (!doc || !provedorId) return;

    const docLimpo = doc.replace(/\D/g, '');
    if (docLimpo.length < 11) {
      toast.error('Informe um CPF ou CNPJ válido.');
      return;
    }

    setLoading(true);
    setAsaasClientes(null);
    try {
      const params = new URLSearchParams({
        cpfcnpj: docLimpo,
        provedor_id: String(provedorId),
      });
      if (conversation?.id) params.set('conversation_id', String(conversation.id));
      if (customerId) params.set('customer_id', String(customerId));
      const response = await axios.get(`${apiBase}/consultar-cliente/?${params}`, {
        headers: authHeaders()
      });

      if (response.data?.precisa_escolher_cliente && Array.isArray(response.data.clientes)) {
        setAsaasClientes(response.data.clientes);
        setClienteData(null);
        toast.info('Há mais de um cliente com este documento. Escolha um.');
        return;
      }

      if (response.data && response.data.contratos && response.data.contratos.length > 0) {
        setClienteData(response.data);
        setAsaasClientes(null);
        const primeiroContrato = response.data.contratos[0];
        await selecionarContrato(
          { ...primeiroContrato, plano_nome: getPlanoNome(primeiroContrato) || primeiroContrato.plano_nome },
          docLimpo,
          isAsaas ? (response.data.faturas || []) : null,
        );
        toast.success('Cliente encontrado!');
      } else {
        toast.error('Cliente não localizado.');
        setClienteData(null);
      }
    } catch (error) {
      const msg =
        error?.response?.data?.error ||
        'Ocorreu um erro ao consultar o cliente.';
      toast.error(msg);
    } finally {
      setLoading(false);
    }
  }, [provedorId, selecionarContrato, apiBase, isAsaas, conversation?.id]);

  useEffect(() => {
    setClienteData(null);
    setDocumento('');
    setSelectedContrato(null);
    setFaturas([]);
    setSelectedFaturaId(null);
    setAsaasClientes(null);
    setWifiData(null);
    setWifiError('');
    setTicketDescription('');
    setTicketType('');
    setTiposOcorrencia(null);
  }, [conversation?.id]);

  const currentFatura =
    faturas.find((f) => String(f.fatura || f.id) === String(selectedFaturaId)) ||
    (faturas.length > 0 ? faturas[0] : null);

  const handleEnviarFaturaInterativa = async (fatura, tipo = 'pix') => {
    if (!fatura || !conversation?.id || !provedorId) {
      toast.error('Dados insuficientes para enviar a fatura.');
      return;
    }

    const faturaId = fatura.fatura || fatura.id;
    if (!faturaId) {
      toast.error('ID da fatura não localizado.');
      return;
    }

    const contratoId = getContratoId(selectedContrato);
    if (!isAsaas && !contratoId) {
      toast.error('Selecione o contrato antes de enviar a fatura.');
      return;
    }

    setLoading(true);
    const toastId = toast.loading(`Enviando ${tipo.toUpperCase()}...`);
    try {
      const payload = {
        fatura_id: faturaId,
        payment_id: faturaId,
        provedor_id: provedorId,
        conversation_id: conversation.id,
        tipo_pagamento: tipo,
        cpf_cnpj: documento || clienteData?.cpfCnpj,
      };
      if (contratoId) payload.contrato_id = contratoId;

      const response = await axios.post(`${apiBase}/enviar-fatura-interativa/`, payload, {
        headers: authHeaders()
      });

      if (response.data.success) {
        toast.success(`${tipo.toUpperCase()} enviado com sucesso!`, { id: toastId });
      } else {
        toast.error(response.data.error || 'Erro ao enviar fatura.', { id: toastId });
      }
    } catch (error) {
      toast.apiError(error, `Erro ao enviar o ${tipo.toUpperCase()}.`, { id: toastId });
    } finally {
      setLoading(false);
    }
  };

  const handleGerarPix = (fatura) => {
    handleEnviarFaturaInterativa(fatura, 'pix');
  };

  const abrirChamado = async () => {
    const cid = getContratoId(selectedContrato);
    if (!cid) {
      toast.error('Nenhum contrato selecionado para abrir suporte.');
      return;
    }
    if (!ticketType) {
      toast.error('Selecione o tipo de chamado.');
      return;
    }
    if (!ticketDescription || ticketDescription.trim().length < 5) {
      toast.error('Descreva o problema em detalhes para o chamado.');
      return;
    }

    setOpeningTicket(true);
    try {
      const resp = await axios.post('/api/sgp/abrir-chamado/', {
        provedor_id: provedorId,
        contrato_id: cid,
        ocorrenciatipo: ticketType,
        conteudo: ticketDescription,
        conversation_id: conversation?.id,
      }, {
        headers: authHeaders()
      });
      const protocolo = resp?.data?.protocolo;
      toast.success(
        protocolo
          ? `Chamado aberto! Protocolo: ${protocolo}`
          : 'Chamado aberto com sucesso!'
      );
      setTicketDescription('');
      setTicketType('');
      if (protocolo && conversation && typeof onConversationUpdate === 'function') {
        onConversationUpdate({
          ...conversation,
          additional_attributes: {
            ...(conversation.additional_attributes || {}),
            protocolo,
            protocol_source: 'sgp',
          },
        });
      }
    } catch (err) {
      toast.apiError(err, 'Erro ao abrir chamado.');
    } finally {
      setOpeningTicket(false);
    }
  };

  const carregarTiposOcorrencia = useCallback(async () => {
    if (!provedorId) return;
    setLoadingTipos(true);
    try {
      const resp = await axios.post('/api/sgp/tipos-ocorrencia/', {
        provedor_id: provedorId,
        cpfcnpj: documento || clienteData?.cpfCnpj || selectedContrato?.cpfCnpj || '',
        contrato_id: getContratoId(selectedContrato),
      }, { headers: authHeaders(), skipErrorToast: true });
      setTiposOcorrencia(resp?.data?.tipos || []);
    } catch (err) {
      setTiposOcorrencia([]);
      toast.error('Não foi possível carregar os tipos de chamado.');
    } finally {
      setLoadingTipos(false);
    }
  }, [provedorId, documento, clienteData, selectedContrato]);

  useEffect(() => {
    if (activeTab === 'suporte' && expanded && clienteData && !isAsaas && tiposOcorrencia === null && !loadingTipos) {
      carregarTiposOcorrencia();
    }
  }, [activeTab, expanded, clienteData, isAsaas, tiposOcorrencia, loadingTipos, carregarTiposOcorrencia]);

  // === Aba Wifi (ACS) ===
  const pppoeLogin = getPppoeLogin(selectedContrato);

  const consultarWifi = useCallback(async () => {
    if (!pppoeLogin || !provedorId) return;
    setLoadingWifi(true);
    setWifiError('');
    try {
      const params = new URLSearchParams({ provedor_id: String(provedorId), login: pppoeLogin });
      const res = await axios.get(`/api/acs/wifi/?${params}`, { headers: authHeaders(), skipErrorToast: true });
      const data = res.data || {};
      setWifiData(data);
      setWifiForm({
        ssid_24: data.wifi_ssid || '',
        pass_24: data.wifi_pass_24 || '',
        ssid_5: data.wifi_ssid_5g || '',
        pass_5: data.wifi_pass_5g || '',
      });
    } catch (e) {
      setWifiData(null);
      const status = e?.response?.status;
      const apiMsg = e?.response?.data?.error || '';
      const semAcesso = status === 403 || (status === 404 && !/não configurada/i.test(apiMsg));
      const msg = semAcesso
        ? 'Sem permissão para acessar o modem.'
        : apiMsg || 'Não foi possível consultar o equipamento.';
      setWifiError(msg);
      toast.error(msg);
    } finally {
      setLoadingWifi(false);
    }
  }, [pppoeLogin, provedorId]);

  useEffect(() => {
    if (activeTab === 'wifi' && expanded && clienteData && pppoeLogin && !wifiData && !wifiError && !loadingWifi) {
      consultarWifi();
    }
  }, [activeTab, expanded, clienteData, pppoeLogin, wifiData, wifiError, loadingWifi, consultarWifi]);

  const salvarWifi = async () => {
    const changes = {};
    if (wifiForm.ssid_24 && wifiForm.ssid_24 !== (wifiData?.wifi_ssid || '')) changes.ssid_24 = wifiForm.ssid_24;
    if (wifiForm.pass_24 && wifiForm.pass_24 !== (wifiData?.wifi_pass_24 || '')) changes.pass_24 = wifiForm.pass_24;
    if (wifiForm.ssid_5 && wifiForm.ssid_5 !== (wifiData?.wifi_ssid_5g || '')) changes.ssid_5 = wifiForm.ssid_5;
    if (wifiForm.pass_5 && wifiForm.pass_5 !== (wifiData?.wifi_pass_5g || '')) changes.pass_5 = wifiForm.pass_5;
    if (Object.keys(changes).length === 0) {
      toast.info('Nenhuma alteração para aplicar.');
      return;
    }
    if ([changes.pass_24, changes.pass_5].some((p) => p !== undefined && p.length < 8)) {
      toast.error('A senha do Wi-Fi deve ter pelo menos 8 caracteres.');
      return;
    }
    if (!window.confirm('Aplicar a alteração no Wi-Fi do cliente? Os aparelhos conectados podem cair e precisar reconectar.')) return;

    setSavingWifi(true);
    try {
      await axios.post('/api/acs/wifi/', { provedor_id: provedorId, login: pppoeLogin, ...changes }, { headers: authHeaders() });
      toast.success('Alteração enviada ao equipamento. Pode levar alguns instantes para aplicar.');
      setWifiData((prev) => ({
        ...(prev || {}),
        ...(changes.ssid_24 ? { wifi_ssid: changes.ssid_24 } : {}),
        ...(changes.pass_24 ? { wifi_pass_24: changes.pass_24 } : {}),
        ...(changes.ssid_5 ? { wifi_ssid_5g: changes.ssid_5 } : {}),
        ...(changes.pass_5 ? { wifi_pass_5g: changes.pass_5 } : {}),
      }));
    } catch (e) {
      toast.apiError(e, 'Não foi possível alterar o Wi-Fi.');
    } finally {
      setSavingWifi(false);
    }
  };

  // === Blocos reutilizados ===
  const renderContratoSelect = (className, withFaturas = true) => (
    <select
      className={`${SGP_SELECT} ${className || ''}`}
      value={getContratoId(selectedContrato)}
      onChange={(e) => {
        const c = clienteData.contratos.find((cnt) => String(getContratoId(cnt)) === String(e.target.value));
        selecionarContrato(
          c,
          documento || clienteData.cpfCnpj,
          withFaturas && isAsaas ? (clienteData.faturas || faturas) : null,
        );
      }}
    >
      {clienteData.contratos.map((c) => {
        const cId = getContratoId(c);
        const planoLabel = getPlanoNome(c);
        const endereco = getContratoEnderecoCurto(c);
        return (
          <option key={cId || Math.random()} value={cId}>
            {isAsaas
              ? (planoLabel || `Cliente ${cId}`)
              : (endereco ? `Contrato ${cId} - ${endereco}` : `Contrato ${cId}`)}
          </option>
        );
      })}
    </select>
  );

  const renderClienteHeader = (selectClass) => (
    <div className={SGP_CARD}>
      <div className={SGP_CARD_HEADER}>
        <span className={SGP_TITLE}>Cliente identificado</span>
        <button onClick={handleReset} className={`${SGP_MUTED} hover:text-foreground transition-colors`}>Alterar</button>
      </div>
      {renderContratoSelect(selectClass)}
    </div>
  );

  const renderIdentificar = () => (
    <div className={SGP_CARD}>
      <div className={SGP_CARD_HEADER}>
        <span className={SGP_TITLE}>Cliente não identificado</span>
      </div>
      <label className={`${SGP_MUTED} block mb-2`}>Informe o CPF / CNPJ</label>
      <input
        id="sgp-document-search"
        name="sgp-document-search"
        autoComplete="off"
        className={`${SGP_INPUT} mb-3`}
        value={documento}
        onChange={(e) => setDocumento(e.target.value)}
        onKeyDown={(e) => e.key === 'Enter' && buscarCliente(documento)}
      />
      <button type="button" onClick={() => buscarCliente(documento)} disabled={loading} className={SGP_PRIMARY_BTN}>
        {loading ? 'Buscando...' : 'Identificar cliente'}
      </button>
      {asaasClientes?.length ? (
        <div className="w-full space-y-2 text-left mt-4">
          <p className="text-xs font-semibold text-foreground mb-2">Escolha o cliente Asaas</p>
          {asaasClientes.map((c) => (
            <button
              key={c.id}
              type="button"
              onClick={() => buscarCliente(documento, c.id)}
              className="w-full text-left rounded-lg border border-border bg-card p-3 hover:bg-muted/60 transition-colors"
            >
              <div className="text-sm font-medium text-foreground truncate">{c.nome || c.id}</div>
              <div className="text-[11px] text-muted-foreground truncate">{c.email || c.cpf_cnpj || c.id}</div>
            </button>
          ))}
        </div>
      ) : null}
    </div>
  );

  const renderContatoCard = () => {
    const contact = panelInfo?.contact || {};
    const name = (contactName && contactName.trim()) || contact.name || conversation?.contact?.name || 'Contato';
    const phone = contact.phone || conversation?.contact?.phone || '';
    const avatar = contact.avatar || conversation?.contact?.avatar;
    const submitName = async () => {
      if (!onSaveContactName || savingName) return;
      setSavingName(true);
      const ok = await onSaveContactName(editingName || '');
      setSavingName(false);
      if (ok) setEditingName(null);
    };
    return (
      <div className={SGP_CARD}>
        <div className="flex items-center gap-3 border-b border-border pb-3 mb-3">
          <div className="w-14 h-14 rounded-lg bg-muted flex items-center justify-center overflow-hidden shrink-0">
            {avatar ? <img src={avatar} alt="" className="w-full h-full object-cover" /> : <User className="w-6 h-6 text-muted-foreground" />}
          </div>
          <div className="min-w-0 flex-1">
            {editingName !== null ? (
              <div className="flex items-center gap-1">
                <input
                  className={`${SGP_INPUT} py-1`}
                  value={editingName}
                  onChange={(e) => setEditingName(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter') submitName();
                    if (e.key === 'Escape') setEditingName(null);
                  }}
                  maxLength={255}
                  autoFocus
                  disabled={savingName}
                  placeholder="Nome do cliente"
                />
                <button
                  type="button"
                  onClick={submitName}
                  disabled={savingName}
                  className="p-1 rounded-md text-primary hover:bg-muted disabled:opacity-50"
                  title="Salvar nome"
                >
                  <Check className="w-4 h-4" />
                </button>
                <button
                  type="button"
                  onClick={() => setEditingName(null)}
                  disabled={savingName}
                  className="p-1 rounded-md text-muted-foreground hover:bg-muted hover:text-foreground disabled:opacity-50"
                  title="Cancelar"
                >
                  <X className="w-4 h-4" />
                </button>
              </div>
            ) : (
              <div className="flex items-start gap-1">
                <p className="text-sm font-semibold text-foreground break-words min-w-0">{name}</p>
                {onSaveContactName && (
                  <button
                    type="button"
                    onClick={() => setEditingName(contactNameNeedsEdit ? '' : name)}
                    className="p-0.5 mt-0.5 rounded-md text-muted-foreground hover:text-foreground hover:bg-muted shrink-0"
                    title="Editar nome do contato"
                  >
                    <Pencil className="w-3 h-3" />
                  </button>
                )}
              </div>
            )}
            <p className={SGP_MUTED}>{phone}</p>
            {contactNameNeedsEdit && editingName === null && onSaveContactName && (
              <p className="text-[10px] text-amber-600 dark:text-amber-400">Defina um nome com o lápis</p>
            )}
          </div>
        </div>
        <div className="space-y-3">
          <div>
            <label className={`${SGP_MUTED} block mb-1`}>E-mail</label>
            <input
              className={SGP_INPUT}
              type="email"
              value={contactForm.email}
              onChange={(e) => setContactForm((f) => ({ ...f, email: e.target.value }))}
              onBlur={() => saveContactField('email')}
            />
          </div>
          <div>
            <label className={`${SGP_MUTED} block mb-1`}>Tags do cliente</label>
            <TagEditor
              tags={contact.tags || []}
              placeholder="Adicionar tag e Enter"
              onChange={(tags) => savePanelInfo({ contact: { tags } })}
            />
          </div>
          <div>
            <label className={`${SGP_MUTED} block mb-1`}>Anotações</label>
            <textarea
              className={`${SGP_INPUT} h-20 resize-none`}
              placeholder="Clique para adicionar anotações..."
              value={contactForm.anotacoes}
              onChange={(e) => setContactForm((f) => ({ ...f, anotacoes: e.target.value }))}
              onBlur={() => saveContactField('anotacoes')}
            />
          </div>
        </div>
      </div>
    );
  };

  const hasClienteTabs = !isAsaas;

  return (
    <div ref={rootRef} className="bg-background flex flex-row-reverse h-full relative">
      <div className="bg-sidebar text-sidebar-foreground w-14 min-w-14 h-full flex flex-col justify-start border-l border-sidebar-border p-2 space-y-3">
        <button
          onClick={onToggleExpanded}
          className={sgpTabClass(false)}
          title={expanded ? 'Recolher painel' : 'Expandir painel'}
        >
          {expanded ? <ChevronsRight className="w-5 h-5" /> : <ChevronsLeft className="w-5 h-5" />}
        </button>

        {[
          { id: 'inicio', label: 'Início', Icon: InicioIcon, show: true, iconClass: 'w-7 h-7' },
          { id: 'cliente', label: 'Cliente', Icon: User, show: true },
          { id: 'financeiro', label: 'Financeiro', Icon: FinanceiroIcon, show: true },
          { id: 'suporte', label: 'Suporte', Icon: HeadphonesIcon, show: hasClienteTabs },
          { id: 'wifi', label: 'Wifi', Icon: Wifi, show: hasClienteTabs },
        ].filter((t) => t.show).map(({ id, label, Icon, iconClass = 'w-5 h-5' }) => (
          <button
            key={id}
            onClick={() => selectTab(id)}
            className={sgpTabClass(expanded && activeTab === id)}
            title={label}
          >
            <Icon className={`${iconClass} flex-shrink-0`} />
          </button>
        ))}
      </div>

      {expanded && (
        <div className="absolute right-full top-0 z-40 shadow-2xl 2xl:static 2xl:shadow-none w-[310px] h-full overflow-y-auto bg-background border-l border-border p-4 flex flex-col">

          {/* === ABA INÍCIO === */}
          {activeTab === 'inicio' && (
            <div className="space-y-4 flex-1 animate-in fade-in duration-300">
              {renderContatoCard()}
              <div className={SGP_CARD}>
                <div className={SGP_CARD_HEADER}>
                  <span className={SGP_TITLE}>Atendimento</span>
                </div>
                <div className="space-y-3">
                  <div className={SGP_ROW}>
                    <span className={SGP_MUTED}>Iniciado em</span>
                    <span className={SGP_VALUE}>{formatDateTime(panelInfo?.conversation?.created_at || conversation?.created_at)}</span>
                  </div>
                  <div className={SGP_ROW}>
                    <span className={SGP_MUTED}>Protocolo</span>
                    <span className={`${SGP_VALUE} text-right max-w-[160px] truncate tracking-wide`}>
                      {conversation?.additional_attributes?.protocolo || conversation?.protocolo || '—'}
                      {conversation?.additional_attributes?.protocol_source === 'sgp' && (
                        <span className="ml-1 text-[10px] font-normal text-muted-foreground">(SGP)</span>
                      )}
                    </span>
                  </div>
                  <div className={SGP_ROW}>
                    <span className={SGP_MUTED}>Canal</span>
                    {(() => {
                      const type = panelInfo?.conversation?.channel_type || conversation?.inbox?.channel_type;
                      const meta = CHANNEL_META[type] || { label: type || 'Canal', Icon: MessageCircle };
                      const inboxName = panelInfo?.conversation?.channel;
                      return (
                        <div className="flex flex-col items-end min-w-0 max-w-[170px]">
                          <span className={`${SGP_VALUE} flex items-center gap-1.5`}>
                            {meta.img ? (
                              <img src={meta.img} alt="" className="w-4 h-4 object-contain shrink-0" />
                            ) : (
                              <meta.Icon className="w-4 h-4 text-muted-foreground shrink-0" />
                            )}
                            <span className="truncate">{meta.label}</span>
                          </span>
                          {inboxName && inboxName !== meta.label && (
                            <span className="text-[11px] text-muted-foreground truncate max-w-full">{inboxName}</span>
                          )}
                        </div>
                      );
                    })()}
                  </div>
                  <div className={SGP_ROW}>
                    <span className={SGP_MUTED}>Atendente</span>
                    <span className={`${SGP_VALUE} text-right max-w-[160px] truncate`}>{panelInfo?.conversation?.assignee || 'Sem atendente'}</span>
                  </div>
                  <div>
                    <label className={`${SGP_MUTED} block mb-1`}>Tags do atendimento</label>
                    <TagEditor
                      tags={panelInfo?.conversation?.tags || []}
                      placeholder="Adicionar tag e Enter"
                      onChange={(tags) => savePanelInfo({ conversation: { tags } })}
                    />
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* === ABA CLIENTE === */}
          {activeTab === 'cliente' && (
            <div className="space-y-4 flex-1 animate-in fade-in duration-300">
              {!clienteData ? renderIdentificar() : (
                <div className={SGP_CARD}>
                  <div className={SGP_CARD_HEADER}>
                    <span className={SGP_TITLE}>Cliente identificado</span>
                    <button onClick={handleReset} className={`${SGP_MUTED} hover:text-foreground transition-colors`}>Alterar</button>
                  </div>

                  {renderContratoSelect('mb-4')}

                  <div className="space-y-3">
                    <div className={`${SGP_ROW} gap-3`}>
                      <span className={`${SGP_MUTED} shrink-0`}>Titular</span>
                      <span className={`${SGP_VALUE} text-right max-w-[170px] break-words`}>{clienteData.razaoSocial || clienteData.nome || selectedContrato?.razaoSocial || selectedContrato?.nomeCliente || selectedContrato?.cliente || 'Não informado'}</span>
                    </div>

                    <div className={SGP_ROW}>
                      <span className={SGP_MUTED}>{isAsaas ? 'Produto' : 'Plano'}</span>
                      <span className={`${SGP_VALUE} text-right max-w-[150px] truncate`}>{getPlanoNome(selectedContrato) || 'Não identificado'}</span>
                    </div>

                    <div className={SGP_ROW}>
                      <span className={SGP_MUTED}>Documento</span>
                      <span className={SGP_VALUE}>{documento || clienteData.cpfCnpj || selectedContrato?.cpfCnpj || selectedContrato?.cpf || selectedContrato?.cnpj || 'Não informado'}</span>
                    </div>

                    <div className={SGP_ROW}>
                      <span className={SGP_MUTED}>{isAsaas ? 'Status' : 'Status do contrato'}</span>
                      {selectedContrato?.contratoStatus === 1 || String(selectedContrato?.contratoStatusDisplay || '').toLowerCase() === 'ativo' || String(selectedContrato?.status).toLowerCase() === 'ativo' ? (
                        <div className="bg-[#20362c] text-[#4ade80] px-2 py-0.5 rounded-full text-[10px] font-bold flex items-center gap-1.5 border border-[#4ade80]/20">
                          <div className="w-1.5 h-1.5 rounded-full bg-[#4ade80]"></div>
                          Ativo
                        </div>
                      ) : (
                        <div className="bg-[#362020] text-[#f87171] px-2 py-0.5 rounded-full text-[10px] font-bold flex items-center gap-1.5 border border-[#f87171]/20">
                          <div className="w-1.5 h-1.5 rounded-full bg-[#f87171]"></div>
                          Inativo
                        </div>
                      )}
                    </div>

                    {!isAsaas && (
                      <div className="flex justify-between items-center pt-1">
                        <span className={SGP_MUTED}>Status da conexão</span>
                        <ConnectionBadge
                          status={selectedContrato?.status_conexao_realtime}
                          loading={loadingConexao}
                        />
                      </div>
                    )}
                  </div>
                </div>
              )}
            </div>
          )}

          {/* === ABA FINANCEIRO === */}
          {activeTab === 'financeiro' && (
            <div className="space-y-4 flex-1 animate-in fade-in duration-300">
              {!clienteData ? renderIdentificar() : (
                <>
                  {renderClienteHeader('mb-3')}

                  <div className={`${SGP_CARD} overflow-hidden p-0`}>
                    <div className="p-4 border-b border-border">
                      <h3 className={`${SGP_TITLE} mb-1`}>Financeiro</h3>
                      <p className={SGP_MUTED}>
                        {faturas.length > 1 ? 'Faturas em aberto' : 'Última fatura em aberto'}
                      </p>
                      {faturas.length > 1 && (
                        <select
                          className={`${SGP_SELECT} mt-3`}
                          value={selectedFaturaId || ''}
                          onChange={(e) => setSelectedFaturaId(e.target.value)}
                        >
                          {faturas.map((f) => {
                            const fid = f.fatura || f.id;
                            const venc = f.vencimento_br || f.vencimento || '';
                            return (
                              <option key={fid} value={fid}>
                                {venc ? `${venc} — ` : ''}R$ {f.valor} ({fid})
                              </option>
                            );
                          })}
                        </select>
                      )}
                    </div>

                    {loadingFaturas ? (
                      <div className="p-8 text-center"><RotateCcw className={SGP_SPINNER} /></div>
                    ) : !currentFatura ? (
                      <div className={`p-8 text-center text-sm ${SGP_MUTED}`}>Nenhuma fatura pendente.</div>
                    ) : (
                      <div className="p-0">
                        <div className="grid grid-cols-3 divide-x divide-border bg-muted/50 border-y border-border">
                          <div className="p-3 text-center">
                            <span className={`text-[10px] ${SGP_MUTED} block mb-1`}>Vencimento</span>
                            <span className="text-xs font-bold text-foreground">
                              {(() => {
                                const d = currentFatura.vencimento_br || currentFatura.vencimento || currentFatura.data_vencimento || '';
                                if (!d || d.includes('/')) return d;
                                const parts = d.split('-');
                                return parts.length === 3 ? `${parts[2]}/${parts[1]}/${parts[0]}` : d;
                              })()}
                            </span>
                          </div>
                          <div className="p-3 text-center">
                            <span className={`text-[10px] ${SGP_MUTED} block mb-1`}>Valor</span>
                            <span className="text-xs font-bold text-foreground">R$ {currentFatura.valor}</span>
                          </div>
                          <div className="p-3 flex flex-col items-center justify-center">
                            <span className={`text-[10px] ${SGP_MUTED} block mb-1`}>Status</span>
                            {(() => {
                              const kind = getFaturaStatusKind(currentFatura);
                              if (kind === 'atraso') {
                                return (
                                  <span className="bg-red-600 text-white text-[10px] px-2.5 py-1 rounded-md font-bold leading-tight text-center inline-flex flex-col items-center justify-center min-w-[3.25rem]">
                                    <span>Em</span>
                                    <span>atraso</span>
                                  </span>
                                );
                              }
                              if (kind === 'aberto') {
                                return (
                                  <span className="bg-yellow-400 text-yellow-950 text-[10px] px-2.5 py-1 rounded-md font-bold leading-tight text-center inline-flex flex-col items-center justify-center min-w-[3.25rem]">
                                    <span>Em</span>
                                    <span>aberto</span>
                                  </span>
                                );
                              }
                              return (
                                <span className="bg-muted text-foreground text-[10px] px-2 py-0.5 rounded-md font-bold">
                                  {currentFatura.status_label}
                                </span>
                              );
                            })()}
                          </div>
                        </div>

                        <div className="p-4 bg-card">
                          <span className="text-[11px] text-muted-foreground font-bold uppercase tracking-wider block mb-4">
                            Ações de Pagamento
                          </span>
                          <div className="flex flex-col gap-2">
                            <button
                              type="button"
                              onClick={() => handleGerarPix(currentFatura)}
                              className={SGP_PAY_ACTION_BTN}
                              style={paymentActionStyle('pix')}
                            >
                              <QrCode className="w-4 h-4 shrink-0" />
                              <span className="text-nowrap">Código do PIX</span>
                            </button>

                            <button
                              type="button"
                              onClick={() => handleEnviarFaturaInterativa(currentFatura, 'boleto')}
                              className={SGP_PAY_ACTION_BTN}
                              style={paymentActionStyle('boleto')}
                            >
                              <Barcode className="w-4 h-4 shrink-0" />
                              <span className="text-nowrap">Boleto</span>
                            </button>
                          </div>
                        </div>
                      </div>
                    )}
                  </div>
                </>
              )}
            </div>
          )}

          {/* === ABA SUPORTE === */}
          {hasClienteTabs && activeTab === 'suporte' && (
            <div className="space-y-4 flex-1 animate-in fade-in duration-300">
              {!clienteData ? renderIdentificar() : (
                <div className={SGP_CARD}>
                  <div className={SGP_CARD_HEADER}>
                    <span className={SGP_TITLE}>Cliente identificado</span>
                    <button onClick={handleReset} className={`${SGP_MUTED} hover:text-foreground transition-colors`}>Alterar</button>
                  </div>
                  {renderContratoSelect('', false)}

                  <div className="flex justify-between items-center pt-3">
                    <span className={SGP_MUTED}>Status da conexão</span>
                    <ConnectionBadge status={selectedContrato?.status_conexao_realtime} loading={loadingConexao} />
                  </div>

                  <div className="mt-4 pt-4 border-t border-border space-y-4">
                    <span className={SGP_TITLE}>Abertura de Chamado</span>

                    <div className="space-y-3">
                      <div>
                        <label className={`${SGP_MUTED} block mb-1`}>Tipo de chamado</label>
                        <select
                          className={SGP_SELECT}
                          value={ticketType}
                          onChange={e => setTicketType(e.target.value)}
                          disabled={loadingTipos}
                        >
                          <option value="">
                            {loadingTipos ? 'Carregando tipos...' : 'Selecione o tipo de chamado'}
                          </option>
                          {(tiposOcorrencia || []).map((t) => (
                            <option key={t.codigo} value={String(t.codigo)}>{t.descricao}</option>
                          ))}
                        </select>
                        {!loadingTipos && Array.isArray(tiposOcorrencia) && tiposOcorrencia.length === 0 && (
                          <button type="button" onClick={carregarTiposOcorrencia} className={`${SGP_MUTED} hover:text-foreground mt-1 underline`}>
                            Tentar carregar novamente
                          </button>
                        )}
                      </div>

                      <textarea
                        className={`${SGP_INPUT} h-24 resize-none`}
                        placeholder="Descreva o problema em detalhes..."
                        value={ticketDescription}
                        onChange={e => setTicketDescription(e.target.value)}
                      />

                      <button
                        onClick={abrirChamado}
                        disabled={openingTicket}
                        className={SGP_PRIMARY_BTN}
                      >
                        {openingTicket ? 'Abrindo chamado...' : 'Abrir chamado'}
                      </button>
                    </div>
                  </div>
                </div>
              )}
            </div>
          )}

          {/* === ABA WIFI (ACS) === */}
          {hasClienteTabs && activeTab === 'wifi' && (
            <div className="space-y-4 flex-1 animate-in fade-in duration-300">
              {!clienteData ? renderIdentificar() : (
                <>
                  {renderClienteHeader('')}

                  <div className={SGP_CARD}>
                    <div className={SGP_CARD_HEADER}>
                      <span className={SGP_TITLE}>Equipamento</span>
                      {pppoeLogin && (
                        <button onClick={consultarWifi} disabled={loadingWifi} className={`${SGP_MUTED} hover:text-foreground transition-colors flex items-center gap-1`}>
                          <RotateCcw className={`w-3 h-3 ${loadingWifi ? 'animate-spin' : ''}`} /> Atualizar
                        </button>
                      )}
                    </div>

                    {!pppoeLogin ? (
                      <p className={SGP_MUTED}>Este contrato não tem login PPPoE cadastrado; não é possível localizar o equipamento.</p>
                    ) : loadingWifi && !wifiData ? (
                      <div className="p-6 text-center"><RotateCcw className={SGP_SPINNER} /></div>
                    ) : wifiError ? (
                      <div className="space-y-3">
                        <p className="text-xs text-destructive">{wifiError}</p>
                        <button type="button" onClick={consultarWifi} className={SGP_SECONDARY_BTN}>Tentar novamente</button>
                      </div>
                    ) : wifiData ? (
                      <div className="space-y-3">
                        <div className={SGP_ROW}>
                          <span className={SGP_MUTED}>Status</span>
                          <StatusPill ok={Boolean(wifiData.is_online)} okLabel="Online" badLabel="Offline" />
                        </div>
                        {(wifiData.manufacturer || wifiData.product_class) && (
                          <div className={SGP_ROW}>
                            <span className={SGP_MUTED}>Modelo</span>
                            <span className={`${SGP_VALUE} text-right max-w-[160px] truncate`}>{[wifiData.manufacturer, wifiData.product_class].filter(Boolean).join(' ')}</span>
                          </div>
                        )}
                        <div className={SGP_ROW}>
                          <span className={SGP_MUTED}>Sinal óptico</span>
                          <span className={SGP_VALUE}>{wifiData.rx_power != null && wifiData.rx_power !== '' ? `${wifiData.rx_power} dBm` : '—'}</span>
                        </div>
                        <div className={SGP_ROW}>
                          <span className={SGP_MUTED}>IP WAN</span>
                          <span className={SGP_VALUE}>{wifiData.wan_ip || '—'}</span>
                        </div>
                        <div className={SGP_ROW}>
                          <span className={SGP_MUTED}>Login PPPoE</span>
                          <span className={`${SGP_VALUE} text-right max-w-[160px] truncate`}>{wifiData.pppoe_user || pppoeLogin}</span>
                        </div>
                        <div className="flex justify-between items-center">
                          <span className={SGP_MUTED}>Aparelhos conectados</span>
                          <span className={SGP_VALUE}>{wifiData.online_hosts_count ?? (Array.isArray(wifiData.hosts) ? wifiData.hosts.length : '—')}</span>
                        </div>
                        {Array.isArray(wifiData.hosts) && wifiData.hosts.length > 0 && (
                          <ul className="space-y-1 max-h-32 overflow-y-auto">
                            {wifiData.hosts.slice(0, 20).map((h, i) => (
                              <li key={h.mac || i} className="flex justify-between gap-2 text-[11px]">
                                <span className="truncate text-foreground">{h.hostname || h.mac || 'Aparelho'}</span>
                                <span className="text-muted-foreground shrink-0">{h.ip || ''}</span>
                              </li>
                            ))}
                          </ul>
                        )}
                      </div>
                    ) : null}
                  </div>

                  {pppoeLogin && wifiData && (
                    <div className={SGP_CARD}>
                      <div className={SGP_CARD_HEADER}>
                        <span className={SGP_TITLE}>Rede Wi-Fi</span>
                        <button onClick={() => setShowPasswords((v) => !v)} className={`${SGP_MUTED} hover:text-foreground transition-colors flex items-center gap-1`}>
                          {showPasswords ? <EyeOff className="w-3 h-3" /> : <Eye className="w-3 h-3" />}
                          {showPasswords ? 'Ocultar senhas' : 'Mostrar senhas'}
                        </button>
                      </div>
                      <div className="space-y-3">
                        {[
                          ['ssid_24', 'Nome da rede 2.4 GHz', 'text'],
                          ['pass_24', 'Senha 2.4 GHz', 'password'],
                          ['ssid_5', 'Nome da rede 5 GHz', 'text'],
                          ['pass_5', 'Senha 5 GHz', 'password'],
                        ].map(([field, label, type]) => (
                          <div key={field}>
                            <label className={`${SGP_MUTED} block mb-1`}>{label}</label>
                            <input
                              className={SGP_INPUT}
                              type={type === 'password' && !showPasswords ? 'password' : 'text'}
                              value={wifiForm[field]}
                              onChange={(e) => setWifiForm((f) => ({ ...f, [field]: e.target.value }))}
                            />
                          </div>
                        ))}
                        <button type="button" onClick={salvarWifi} disabled={savingWifi} className={SGP_PRIMARY_BTN}>
                          {savingWifi ? 'Aplicando...' : 'Salvar alterações do Wi-Fi'}
                        </button>
                      </div>
                    </div>
                  )}
                </>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
};

export default SgpSidebar;
