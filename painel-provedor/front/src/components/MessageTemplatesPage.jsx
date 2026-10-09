import React, { useState, useEffect, useCallback } from 'react';
import { toast } from '../lib/notify';
import { useNavigate } from 'react-router-dom';
import axios from 'axios';
import { 
  ArrowLeft, 
  Plus, 
  Trash2, 
  MessageSquare, 
  Search, 
  Filter, 
  Eye, 
  CheckCircle2,
  Check,
  XCircle, 
  Clock, 
  AlertCircle,
  Layout,
  FileText,
  Send,
  Copy,
  MessageCircle,
  ChevronDown,
  ChevronUp,
} from 'lucide-react';
import { useLanguage } from '../contexts/LanguageContext';
import {
  normalizeWhatsAppBodyForMeta,
  META_ORDER_DETAILS_BUTTON_TEXT,
  extractVariableNumbers,
  replaceVariablesWithExamples,
  buildBodyTextExamples,
  buildHeaderTextExamples,
  buildDefaultVariableSamples,
  inferVariableSampleExample,
  collectTemplateVariableNumbers,
  sanitizeMetaTemplateUrl,
  buildMetaUrlButtonExample,
  isMetaFlaggedTemplateUrl,
  normalizeDynamicTemplateUrl,
  validateDynamicTemplateUrl,
} from '../utils/whatsappTemplateBody';
import { MetaTemplateCard, PreviewActionButton } from './MetaTemplateCard';
import {
  TEMPLATE_CARD_STYLES,
  getOrderDetailsPreviewActionButtons,
  orderDetailsPaymentFlags,
} from '../utils/metaTemplatePreview';

const HEADER_MEDIA_TYPES = ['image', 'video', 'document'];

function headerModeFromForm(header) {
  const t = (header?.type || 'none').toLowerCase();
  if (t === 'text') return 'text';
  if (HEADER_MEDIA_TYPES.includes(t)) return t;
  return 'none';
}

function applyHeaderMode(header, mode) {
  const base = {
    type: 'none',
    text: '',
    media_id: '',
    media_link: '',
    has_variables: false,
    file: null,
    ...(header || {}),
  };
  if (mode === 'none') {
    return { ...base, type: 'none', text: '', file: null };
  }
  if (mode === 'text') {
    return { ...base, type: 'text', file: null };
  }
  if (HEADER_MEDIA_TYPES.includes(mode)) {
    return {
      ...base,
      type: mode,
      text: '',
      file: base.type === mode ? base.file : null,
    };
  }
  return base;
}

const META_TEMPLATE_NAME_MAX = 512;

/** Mesma regra do backend para o nome enviado à Meta (minúsculas, _ ). */
function sanitizeTemplateName(raw) {
  return (raw || '')
    .toLowerCase()
    .replace(/[áàâãä]/g, 'a')
    .replace(/[éèêë]/g, 'e')
    .replace(/[íìîï]/g, 'i')
    .replace(/[óòôõö]/g, 'o')
    .replace(/[úùûü]/g, 'u')
    .replace(/[ç]/g, 'c')
    .replace(/[^a-z0-9]/g, '_')
    .replace(/_{2,}/g, '_')
    .replace(/^_|_$/g, '');
}

/** Sufixo _p{id} igual ao `finalize_template_name_for_canal` no backend. */
function metaTemplateNameForProvedor(cleanBase, provedorId) {
  if (!cleanBase) return '';
  if (provedorId == null || provedorId === '') return cleanBase;
  const pid = Number(provedorId);
  if (Number.isNaN(pid)) return cleanBase;
  const suffix = `_p${pid}`;
  if (cleanBase.endsWith(suffix)) return cleanBase;
  let combined = `${cleanBase}${suffix}`;
  if (combined.length > META_TEMPLATE_NAME_MAX) {
    const room = META_TEMPLATE_NAME_MAX - suffix.length;
    const trimmed = cleanBase.slice(0, Math.max(0, room)).replace(/_+$/g, '');
    combined = `${trimmed}${suffix}`;
  }
  return combined;
}

/** Meta devolve `last_updated_time` (epoch s); API pode expor outros nomes. */
function formatTemplateLastUpdated(template) {
  const raw =
    template?.last_updated_datetime ||
    template?.last_updated_time ||
    template?.lastUpdatedTime;
  if (raw == null || raw === '') return 'Não disponível';
  let ms;
  if (typeof raw === 'number') {
    ms = raw > 1e12 ? raw : raw * 1000;
  } else {
    const s = String(raw).trim();
    ms = /^\d+$/.test(s) ? Number(s) * 1000 : Date.parse(raw);
  }
  if (Number.isNaN(ms)) return 'Não disponível';
  return new Date(ms).toLocaleString('pt-BR');
}

function defaultLinkButton() {
  return {
    buttonText: '',
    tipo: 'link',
    urlType: 'static',
    url: '',
    urlSample: '',
    txtMode: false,
    phone: '',
  };
}

function ensureLinkButtons(buttons) {
  const next = [...(buttons || [])];
  while (next.length < 2) {
    next.push(defaultLinkButton());
  }
  return next.slice(0, 2);
}

function buildLinkButtonsForMeta(linkButtons) {
  const out = [];
  for (const item of ensureLinkButtons(linkButtons)) {
    const text = (item.buttonText || '').trim();
    if (!text) continue;

    if (item.tipo === 'phone') {
      const raw = (item.phone || '').trim();
      if (!raw) continue;
      const digits = raw.replace(/\s/g, '');
      const phone_number = digits.startsWith('+') ? digits : `+${digits.replace(/^\+/, '')}`;
      out.push({ type: 'PHONE_NUMBER', text, phone_number });
      continue;
    }

    let url = sanitizeMetaTemplateUrl((item.url || '').trim());
    if (!url) continue;
    if (item.urlType === 'dynamic') {
      url = normalizeDynamicTemplateUrl(url);
    }

    url = sanitizeMetaTemplateUrl(url);
    const btn = { type: 'URL', text, url };
    if (item.urlType === 'dynamic' || /\{\{\s*1\s*\}\}/.test(url)) {
      let sample = (item.urlSample || '').trim();
      // A Meta não aceita query string após {{1}} no template.
      // Se o provedor quiser abrir em TXT (?txt=1), isso é aplicado no envio do disparo (parâmetro do botão),
      // não na URL do template nem na URL de exemplo.
      if (item.urlType === 'dynamic' && item.txtMode && sample) {
        sample = sample.replace(/[?&]txt=1\b/gi, '').replace(/[?&]$/g, '');
      }
      // Se não informou amostra, monta a URL completa com UUID de exemplo
      if (!sample && item.urlType === 'dynamic') {
        sample = url.replace(/\{\{\s*1\s*\}\}/g, 'e988ed73-c16e-4c3f-96ad-3db2e10d9631');
      }
      btn.example = buildMetaUrlButtonExample(url, sample);
    }
    // Config interna: no envio, anexar ?txt=1 após o ID (não vai para a Meta)
    if (item.urlType === 'dynamic' && item.txtMode) {
      btn._niohub_txt_mode = true;
    }
    out.push(btn);
  }
  return out;
}

/** Ação do template no modal de criação: none | order_details | buttons | link */
function buildButtonsForMetaSubmit(templateForm) {
  const action = templateForm.templateAction || 'none';
  if (action === 'none') return [];
  if (action === 'order_details') {
    return [{ type: 'ORDER_DETAILS', text: META_ORDER_DETAILS_BUTTON_TEXT }];
  }
  if (action === 'link') {
    return buildLinkButtonsForMeta(templateForm.linkButtons);
  }
  if (action === 'buttons') {
    return ensureQuickReplyButtons(templateForm.buttons).filter((b) => b.text);
  }
  return [];
}

function ensureQuickReplyButtons(buttons) {
  const next = [...(buttons || [])];
  while (next.length < 3) {
    next.push({ type: 'QUICK_REPLY', text: '' });
  }
  return next.slice(0, 3).map((btn) => ({
    type: 'QUICK_REPLY',
    text: (btn.text || btn.title || '').trim(),
  }));
}

function getGalleryPreviewButtons(item) {
  if (item.has_pix) {
    const buttons = [];
    if (item.has_pix) buttons.push({ text: 'Copiar Chave Pix', kind: 'copy' });
    if (item.has_barcode) buttons.push({ text: 'Copiar código de barras', kind: 'copy' });
    return buttons;
  }
  if (item.templateAction === 'link' && item.linkButtons?.length) {
    return item.linkButtons.map((b) => ({ text: b.buttonText || 'Link', kind: 'link' }));
  }
  return [];
}

function galleryVariableSamples(item) {
  if (item.variableSamples) return item.variableSamples;
  return buildDefaultVariableSamples(item.body);
}

function getCreateModalPreviewButtons(templateForm) {
  const action = templateForm.templateAction || 'none';
  if (action === 'none') return [];
  if (action === 'order_details') {
    return getOrderDetailsPreviewActionButtons(templateForm.orderDetailsType);
  }
  if (action === 'link') {
    return buildLinkButtonsForMeta(templateForm.linkButtons).map((b) => ({
      text: b.text || 'Link',
      kind: 'link',
    }));
  }
  if (action === 'buttons') {
    return ensureQuickReplyButtons(templateForm.buttons)
      .filter((b) => b.text)
      .map((b) => ({ text: b.text, kind: 'copy' }));
  }
  return [];
}

export default function MessageTemplatesPage() {
  const { t } = useLanguage();
  const navigate = useNavigate();
  
  // States
  const [channels, setChannels] = useState([]);
  const [selectedChannel, setSelectedChannel] = useState(null);
  const [templates, setTemplates] = useState([]);
  const [loading, setLoading] = useState(true);
  const [loadingTemplates, setLoadingTemplates] = useState(false);
  const [activeTab, setActiveTab] = useState('templates'); // 'templates' ou 'gallery'
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [creatingTemplate, setCreatingTemplate] = useState(false);
  const [selectedTemplate, setSelectedTemplate] = useState(null);
  const [showDispatchModal, setShowDispatchModal] = useState(false);
  const [gatewayConfigJson, setGatewayConfigJson] = useState('');
  const [mensagemConfigJson, setMensagemConfigJson] = useState('');
  const [loadingDispatchConfig, setLoadingDispatchConfig] = useState(false);
  const [copiedWhich, setCopiedWhich] = useState(null);
  
  const [templateForm, setTemplateForm] = useState({
    name: '',
    category: 'UTILITY',
    language: 'pt_BR',
    variable_type: 'number',
    body: { text: '', has_variables: false },
    header: { type: 'none', text: '', media_id: '', media_link: '', has_variables: false, file: null },
    footer: { text: '', has_variables: false },
    buttons: [],
    templateAction: 'none',
    orderDetailsType: 'pix_boleto',
    linkButtons: [defaultLinkButton(), defaultLinkButton()],
  });
  const [linkSectionOpen, setLinkSectionOpen] = useState([true, false]);
  const [variableSamples, setVariableSamples] = useState({});

  const syncVariableSamples = (bodyText, prevSamples = variableSamples) => {
    const nums = extractVariableNumbers(bodyText);
    const next = { ...prevSamples };
    nums.forEach((n) => {
      if (!(next[n]?.example ?? '').toString().trim()) {
        next[n] = { example: inferVariableSampleExample(bodyText, n) };
      }
    });
    Object.keys(next).forEach((key) => {
      if (!nums.includes(parseInt(key, 10))) delete next[parseInt(key, 10)];
    });
    return next;
  };

  const resetTemplateForm = () => {
    setTemplateForm({
      name: '',
      category: 'UTILITY',
      language: 'pt_BR',
      variable_type: 'number',
      body: { text: '', has_variables: false },
      header: { type: 'none', text: '', media_id: '', media_link: '', has_variables: false, file: null },
      footer: { text: '', has_variables: false },
      buttons: [],
      templateAction: 'none',
      orderDetailsType: 'pix_boleto',
      linkButtons: [defaultLinkButton(), defaultLinkButton()],
    });
    setLinkSectionOpen([true, false]);
    setVariableSamples({});
  };

  const galleryStyles = TEMPLATE_CARD_STYLES;

  // Gallery Templates Data
  const GALLERY_TEMPLATES = [
    {
      id: 'gal_1',
      name: 'Pagamento próximo do vencimento',
      category: 'Conversas de utilidade',
      badge: 'Detalhes de pedido',
      body: 'Olá, {{1}}.\nVocê tem um pagamento no valor de {{2}} cuja data de vencimento é {{3}}.\nPara sua comodidade, anexamos uma cópia da sua fatura.',
      has_pdf: true,
      has_pix: true,
      has_barcode: true,
      variableSamples: {
        1: { example: 'Nome Cliente' },
        2: { example: '70,00' },
        3: { example: '13/06/2026' },
      },
    },
    {
      id: 'gal_2',
      name: 'Lembrete de pagamento',
      category: 'Conversas de utilidade',
      badge: 'Detalhes de pedido',
      body:
        'Lembrete de pagamento\n\nPrezado(a) {{1}},\n\nInformamos que sua fatura vence em {{2}}.\n\nPara evitar a interrupção dos serviços, realize o pagamento até a data de vencimento. Caso o pagamento já tenha sido efetuado, desconsidere esta mensagem.',
      has_pdf: true,
      has_pix: true,
      has_barcode: false,
      variableSamples: {
        1: { example: 'Nome Cliente' },
        2: { example: '13/06/2026' },
      },
    },
    {
      id: 'gal_3',
      name: 'O pagamento vence em breve',
      category: 'Conversas de utilidade',
      badge: 'Detalhes de pedido',
      body: 'Olá! Seu pagamento vence em breve. Cliente: {{1}}. Data de vencimento: {{2}}. Se você já pagou, ignore esta mensagem.',
      has_pdf: true,
      has_pix: true,
      has_barcode: false,
      variableSamples: {
        1: { example: 'Nome Cliente' },
        2: { example: '13/06/2026' },
      },
    },
    {
      id: 'gal_4',
      name: 'Pagamento recebido',
      category: 'Conversas de utilidade',
      badge: 'Mensagem modelo',
      body:
        'Olá, {{1}}, o pagamento da sua fatura {{2}} de {{3}} foi recebido com sucesso. Sua data de pagamento foi {{4}}. Obrigado!',
      has_pdf: false,
      has_pix: false,
      has_barcode: false,
      templateAction: 'link',
      linkButtons: [
        {
          buttonText: 'Recibo',
          tipo: 'link',
          urlType: 'dynamic',
          url: 'https://www.example.com/recibo/{{1}}',
        },
      ],
      variableSamples: {
        1: { example: 'nome' },
        2: { example: '5466' },
        3: { example: 'R$100,00' },
        4: { example: '17/05/2026' },
      },
      footerText: '',
    },
  ];

  // Load WhatsApp Official Channels
  useEffect(() => {
    const fetchChannels = async () => {
      try {
        const token = localStorage.getItem('auth_token') || localStorage.getItem('token');
        const response = await axios.get('/api/canais/', { headers: { Authorization: `Token ${token}` } });
        const channelsList = Array.isArray(response.data) ? response.data : response.data.results || [];
        const waOfficialChannels = channelsList.filter(c => c.tipo === 'whatsapp_oficial');
        setChannels(waOfficialChannels);
        if (waOfficialChannels.length > 0) {
          setSelectedChannel(waOfficialChannels[0]);
          loadTemplates(waOfficialChannels[0]);
        } else { setLoading(false); }
      } catch (error) { setLoading(false); }
    };
    fetchChannels();
  }, []);

  const loadTemplates = async (channel) => {
    if (!channel) return;
    setLoadingTemplates(true);
    try {
      const token = localStorage.getItem('auth_token') || localStorage.getItem('token');
      const response = await axios.get(`/api/canais/${channel.id}/message-templates/`, { headers: { Authorization: `Token ${token}` } });
      const d = response.data;
      const list = Array.isArray(d) ? d : (d?.templates ?? d?.data ?? []);
      setTemplates(Array.isArray(list) ? list : []);
    } catch (error) { /* silenciado */ } finally { setLoadingTemplates(false); setLoading(false); }
  };

  const handleChannelChange = (channelId) => {
    const channel = channels.find(c => c.id === parseInt(channelId));
    if (channel) { setSelectedChannel(channel); loadTemplates(channel); }
  };


  const handleUseGalleryTemplate = (item) => {
    const bodyText = item.body;
    const action = item.templateAction || (item.has_pix ? 'order_details' : 'none');
    setVariableSamples(galleryVariableSamples(item));
    setTemplateForm({
      name: item.name.toLowerCase().replace(/[^a-z0-9_]/g, '_'),
      category: 'UTILITY',
      language: 'pt_BR',
      variable_type: 'number',
      body: { text: bodyText, has_variables: true },
      header: {
        type: item.has_pdf ? 'document' : 'none',
        text: item.has_pdf ? 'Documento anexado' : '',
        media_id: '',
        media_link: '',
        has_variables: false,
        file: null,
      },
      footer: {
        text: item.footerText != null ? item.footerText : 'Atendimento Automático',
        has_variables: false,
      },
      buttons: [],
      templateAction: action,
      orderDetailsType: item.has_pix ? 'pix_boleto' : 'none',
      linkButtons:
        action === 'link'
          ? ensureLinkButtons(item.linkButtons || [{ buttonText: 'Recibo', tipo: 'link', urlType: 'dynamic', url: '' }])
          : ensureLinkButtons([]),
    });
    if (action === 'link') {
      setLinkSectionOpen([true, false]);
    }
    setShowCreateModal(true);
  };

  const translateRejectionReason = (reason) => {
    if (!reason || reason === 'NONE') return null;
    const value = typeof reason === 'object' ? (reason.message || reason.reason || '') : String(reason);
    if (!value || value === 'NONE') return null;
    const translations = {
      INVALID_FORMAT: 'Formato inválido',
      MISLEADING_CONTENT: 'Conteúdo enganoso',
      INCORRECT_CATEGORY: 'Categoria incorreta — a Meta classifica este conteúdo de outra forma (ex.: Marketing em vez de Utilidade)',
      POLICY_VIOLATION: 'Violação de política',
      SPAM: 'Spam',
      SCAM: 'Possível golpe / phishing',
      ABUSIVE_CONTENT: 'Conteúdo abusivo',
      PROMOTIONAL: 'Conteúdo promocional (use Marketing)',
    };
    return translations[value] || value;
  };

  const handleGenerateDispatchCode = async (template) => {
    if (!selectedChannel) {
      toast.error('Selecione um canal antes de gerar o código.');
      return;
    }
    setSelectedTemplate(template);
    setLoadingDispatchConfig(true);
    setCopiedWhich(null);
    setShowDispatchModal(true);
    setGatewayConfigJson('');
    setMensagemConfigJson('');
    try {
      const token = localStorage.getItem('auth_token') || localStorage.getItem('token');
      const response = await axios.post(
        `/api/canais/${selectedChannel.id}/message-templates-dispatch-config/`,
        { template },
        { headers: { Authorization: `Token ${token}` } }
      );
      if (response.data?.success) {
        setGatewayConfigJson(response.data.gateway_config_json || '');
        setMensagemConfigJson(response.data.mensagem_config_json || '');
      } else {
        setShowDispatchModal(false);
        toast.error(response.data?.error || 'Não foi possível gerar o código.');
      }
    } catch (error) {
      setShowDispatchModal(false);
      const errMsg =
        error.response?.data?.error || error.message || 'Erro ao gerar código para o SGP.';
      toast.error(errMsg);
    } finally {
      setLoadingDispatchConfig(false);
    }
  };

  const copyText = async (text, which) => {
    if (!text) return;
    try {
      await navigator.clipboard.writeText(text);
    } catch {
      const textarea = document.createElement('textarea');
      textarea.value = text;
      document.body.appendChild(textarea);
      textarea.select();
      document.execCommand('copy');
      document.body.removeChild(textarea);
    }
    setCopiedWhich(which);
    setTimeout(() => setCopiedWhich(null), 2500);
  };

  if (loading) return <div className="flex items-center justify-center min-h-[400px]"><div className="animate-spin rounded-full h-12 w-12 border-t-2 border-b-2 border-primary"></div></div>;

  return (
    <div className="max-w-7xl mx-auto p-4 sm:p-6 lg:p-8 space-y-8 animate-in fade-in duration-500">
      <style>{galleryStyles}</style>

      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div className="flex items-center gap-4">
          <button onClick={() => navigate(-1)} className="p-2 rounded-xl bg-card border border-border hover:bg-muted transition-colors"><ArrowLeft className="w-5 h-5 text-muted-foreground" /></button>
          <div><h1 className="text-3xl font-bold text-foreground">Modelos de Mensagem</h1><p className="text-muted-foreground">Gerencie seus templates do WhatsApp Oficial</p></div>
        </div>
        <button onClick={() => { resetTemplateForm(); setShowCreateModal(true); }} className="flex items-center justify-center gap-2 bg-primary hover:bg-primary/90 text-primary-foreground px-6 py-3 rounded-xl font-bold shadow-lg shadow-primary/20 transition-all hover:scale-[1.02] active:scale-[0.98]"><Plus className="w-5 h-5" /> Novo Modelo</button>
      </div>

      {/* Tabs */}
      <div className="flex flex-col md:flex-row items-center justify-between gap-4 bg-card/50 p-2 rounded-2xl border border-border backdrop-blur-sm">
        <div className="flex bg-muted/50 p-1 rounded-xl w-full md:w-auto">
          <button onClick={() => setActiveTab('templates')} className={`flex items-center gap-2 px-6 py-2 rounded-lg text-sm font-semibold transition-all ${activeTab === 'templates' ? 'bg-card text-primary shadow-sm' : 'text-muted-foreground hover:text-foreground'}`}>
            <img className="w-4 h-4" src={`https://img.icons8.com/material-outlined/24/${activeTab === 'templates' ? 'ff9127' : 'ffffff'}/list.png`} alt="templates" /> 
            Templates
          </button>
          <button onClick={() => setActiveTab('gallery')} className={`flex items-center gap-2 px-6 py-2 rounded-lg text-sm font-semibold transition-all ${activeTab === 'gallery' ? 'bg-card text-primary shadow-sm' : 'text-muted-foreground hover:text-foreground'}`}>
            <img className="w-4 h-4" src={`https://img.icons8.com/material-outlined/24/${activeTab === 'gallery' ? 'ff9127' : 'ffffff'}/dashboard-layout.png`} alt="modelos" /> 
            Modelos
          </button>
        </div>
        <div className="flex items-center gap-3 w-full md:w-auto pr-2">
          <span className="text-sm font-medium text-muted-foreground whitespace-nowrap">Canal:</span>
          <select value={selectedChannel?.id || ''} onChange={(e) => handleChannelChange(e.target.value)} className="bg-background border border-border text-foreground px-4 py-2 rounded-xl focus:outline-none focus:ring-2 focus:ring-primary/50 transition-all min-w-[200px]">{channels.map(c => <option key={c.id} value={c.id}>{c.nome || c.tipo}</option>)}</select>
        </div>
      </div>

      {/* Content Area */}
      {activeTab === 'templates' ? (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-8">
          {loadingTemplates ? (
            <div className="col-span-full py-20 flex flex-col items-center gap-4">
              <div className="animate-spin rounded-full h-10 w-10 border-t-2 border-b-2 border-primary"></div>
              <p className="text-gray-500 font-bold animate-pulse uppercase tracking-widest text-xs">Sincronizando com a Meta...</p>
            </div>
          ) : templates.length > 0 ? (
            templates.map((template, idx) => {
              const key =
                template.id != null
                  ? String(template.id)
                  : `${template.name}-${template.language}-${idx}`;
              return (
                <MetaTemplateCard key={key} template={template}>
                  {template.status === 'REJECTED' && translateRejectionReason(template.rejected_reason) && (
                    <p className="relative z-10 mt-1 px-2 text-center text-[10px] font-medium text-red-400 leading-snug">
                      Motivo Meta: {translateRejectionReason(template.rejected_reason)}
                    </p>
                  )}

                  <div className="relative z-10 mt-3 flex items-center justify-between gap-2 border-t border-white/10 pt-3">
                    <div className="flex flex-col gap-0.5 min-w-0">
                      <span className="text-[8px] font-bold uppercase tracking-tighter text-orange-500">
                        Última atualização
                      </span>
                      <div className="flex items-center gap-1.5 text-[10px] font-bold text-orange-500">
                        <Clock className="h-3 w-3 shrink-0 text-orange-500" />
                        <span className="truncate">{formatTemplateLastUpdated(template)}</span>
                      </div>
                    </div>
                    <div className="flex items-center gap-1">
                      <button
                        type="button"
                        onClick={() => handleGenerateDispatchCode(template)}
                        className="rounded-lg bg-blue-600 px-3 py-2 text-center text-[10px] font-bold leading-tight text-white shadow-sm transition-all hover:bg-blue-700 active:scale-[0.98] sm:text-xs"
                      >
                        Gerar código para disparos
                      </button>
                      <button
                        type="button"
                        className="rounded-lg p-2 text-red-600 transition-all hover:bg-red-600/15 hover:text-red-500 active:scale-90"
                        title="Excluir na Meta (em breve)"
                      >
                        <Trash2 className="h-4 w-4" strokeWidth={2.25} />
                      </button>
                    </div>
                  </div>
                </MetaTemplateCard>
              );
            })
          ) : (
            <div className="col-span-full py-20 flex flex-col items-center gap-4 bg-card/10 rounded-3xl border border-dashed border-white/10">
              <div className="p-4 bg-muted rounded-full"><MessageCircle className="w-8 h-8 text-muted-foreground" /></div>
              <div className="text-center">
                <h3 className="text-lg font-bold text-foreground uppercase tracking-tight">Nenhum template ativo</h3>
                <p className="text-sm text-muted-foreground mt-1">Sua lista de templates para este canal está vazia.</p>
              </div>
            </div>
          )}
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-8">
          {GALLERY_TEMPLATES.map((item) => (
            <div key={item.id} className="template-card">
              <div className="overlay-gallery"><button onClick={() => handleUseGalleryTemplate(item)} className="use-btn-gallery">✓ USAR ESTE MODELO</button></div>
              <div className="template-title text-gray-200">{item.category}</div>
              <div className="badge">{item.badge}</div>
              <div className="wa-card-custom">
                <div className="wa-header-custom"><img className="w-4 h-4" src="https://upload.wikimedia.org/wikipedia/commons/6/6b/WhatsApp.svg" />{item.name}</div>
                <div className="wa-body-custom">
                  <div className="box-custom">
                    {item.has_pix && (
                      <div className="top-info-custom">Nº da cobrança: 72418</div>
                    )}
                    {item.has_pdf && (
                      <div className="bg-[#f2f3f5] m-2 border border-[#d9dce0] rounded-md p-3 flex items-center justify-between">
                        <div className="flex items-center gap-3">
                          <img className="w-8" src="https://cdn.icon-icons.com/icons2/2107/PNG/512/file_type_pdf_icon_130274.png" alt="PDF Icon" />
                          <div>
                            <div className="attach-title-custom">Documento anexado</div>
                            <div className="attach-sub-custom">Anexo</div>
                          </div>
                        </div>
                        <div className="download-icon-custom"><img className="w-4 h-4" src="https://img.icons8.com/material-outlined/24/22b15d/download--v1.png" alt="download" /></div>
                      </div>
                    )}
                    {item.has_pix && (
                    <div className="payment-custom">
                      <div className="payment-title-custom">
                        <span>Pagar com</span>
                        <div className="flex gap-2 items-center">
                          {item.has_barcode && <div className="w-[17px] h-[17px] bg-black rounded-[2px]" style={{ background: 'repeating-linear-gradient(to right, #000 0px, #000 2px, #fff 2px, #fff 3px)' }}></div>}
                          {item.has_pix && <img className="w-[26px] h-[26px] object-contain" src="https://logospng.org/download/pix/logo-pix-icone-1024.png" alt="Pix" />}
                        </div>
                      </div>
                      <div className="total-custom"><span>Total</span><span>R$ 129,90</span></div>
                    </div>
                    )}
                    <div className="message-custom">
                      {replaceVariablesWithExamples(item.body, galleryVariableSamples(item))}
                    </div>
                  </div>
                  {getGalleryPreviewButtons(item).map((btn, bi) => (
                    <PreviewActionButton key={bi} btn={btn} />
                  ))}
                </div>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Create Modal (Minimal Example) */}
      {showCreateModal && (
        <div className="fixed inset-0 bg-black/80 backdrop-blur-sm flex items-center justify-center z-[70] p-4">
          <div className="bg-[#2a2a2a] rounded-xl shadow-2xl w-full max-w-[1200px] max-h-[95vh] overflow-hidden flex flex-col border border-white/5">
            <div className="p-4 flex items-center justify-between border-b border-white/5 bg-[#252525]">
              <h2 className="text-lg font-bold text-gray-200">Criar Template a partir do Modelo</h2>
              <button onClick={() => { setShowCreateModal(false); resetTemplateForm(); }} className="text-gray-500 hover:text-white"><XCircle className="w-6 h-6" /></button>
            </div>
            <div className="p-8 flex-1 overflow-y-auto custom-scrollbar">
                <div className="grid grid-cols-1 lg:grid-cols-12 gap-10">
                  {/* Left: Preview & Instructions (Col-4) - FIXED/STICKY */}
                  <div className="lg:col-span-4 space-y-6 lg:sticky lg:top-0 lg:self-start">
                    <div>
                      <h3 className="text-xl font-bold text-gray-200">Acompanhe o layout do template</h3>
                      <p className="text-sm text-gray-400 mt-2">Preencha o formulário, de acordo com suas preferências, e acompanhe como ficará sua mensagem modelo</p>
                    </div>
                    <div className="bg-[#e5ddd5] rounded-3xl p-8 shadow-inner relative overflow-hidden min-h-[550px] flex flex-col items-center justify-start pt-12 border border-white/10">
                       {/* WhatsApp Background Pattern (Subtle) */}
                       <div className="absolute inset-0 opacity-[0.03] pointer-events-none" style={{ backgroundImage: 'url("https://user-images.githubusercontent.com/15075759/28719144-86dc0f70-73b1-11e7-911d-60d70fcded21.png")' }}></div>
                       
                       {/* WhatsApp Card */}
                       <div className="wa-card-custom w-full max-w-[340px] shadow-2xl relative z-10">
                          <div className="wa-header-custom py-3 px-4">
                            <img className="w-5 h-5" src="https://upload.wikimedia.org/wikipedia/commons/6/6b/WhatsApp.svg" alt="WA" />
                            <span className="truncate font-bold tracking-tight">
                              {metaTemplateNameForProvedor(
                                sanitizeTemplateName(templateForm.name),
                                selectedChannel?.provedor?.id
                              ) || sanitizeTemplateName(templateForm.name) || 'Pagamento próximo do vencimento'}
                            </span>
                          </div>
                          <div className="wa-body-custom p-1 bg-[#e1f3fb]/20">
                            <div className="box-custom shadow-sm border border-black/5">
                              {templateForm.header.type === 'text' &&
                                (templateForm.header.text || '').trim() && (
                                  <div className="wa-header-text-custom">
                                    {replaceVariablesWithExamples(
                                      templateForm.header.text,
                                      variableSamples
                                    )}
                                  </div>
                                )}
                              {HEADER_MEDIA_TYPES.includes(templateForm.header.type) && (
                                <div className="bg-[#f2f3f5] m-2 border border-[#d9dce0] rounded-lg p-4 flex items-center justify-between">
                                  <div className="flex items-center gap-4">
                                    <img
                                      className="w-9"
                                      src={
                                        templateForm.header.type === 'document'
                                          ? 'https://cdn.icon-icons.com/icons2/2107/PNG/512/file_type_pdf_icon_130274.png'
                                          : 'https://img.icons8.com/fluency/48/image.png'
                                      }
                                      alt=""
                                    />
                                    <div>
                                      <div className="text-[13px] font-bold text-gray-800 leading-tight">
                                        {templateForm.header.type === 'document'
                                          ? 'Documento anexado'
                                          : templateForm.header.type === 'video'
                                            ? 'Vídeo no cabeçalho'
                                            : 'Imagem no cabeçalho'}
                                      </div>
                                      <div className="text-[11px] text-gray-500 uppercase tracking-tighter">
                                        {templateForm.header.file?.name || 'Arquivo de exemplo'}
                                      </div>
                                    </div>
                                  </div>
                                </div>
                              )}
                              {templateForm.templateAction === 'order_details' && (() => {
                                const { showPix, showBoleto } = orderDetailsPaymentFlags(
                                  templateForm.orderDetailsType
                                );
                                return (
                                  <>
                                    <div className="top-info-custom">Nº da cobrança: 19726</div>
                                    <div className="payment-custom">
                                      <div className="payment-title-custom">
                                        <span>Pagar com</span>
                                        <div className="flex gap-2 items-center">
                                          {showBoleto && (
                                            <div
                                              className="w-[17px] h-[17px] rounded-[2px]"
                                              style={{
                                                background:
                                                  'repeating-linear-gradient(to right, #000 0px, #000 2px, #fff 2px, #fff 3px)',
                                              }}
                                            />
                                          )}
                                          {showPix && (
                                            <img
                                              className="w-[26px] h-[26px] object-contain"
                                              src="https://logospng.org/download/pix/logo-pix-icone-1024.png"
                                              alt="Pix"
                                            />
                                          )}
                                        </div>
                                      </div>
                                      <div className="total-custom">
                                        <span>Total</span>
                                        <span>R$ 129,90</span>
                                      </div>
                                    </div>
                                  </>
                                );
                              })()}

                              <div className="message-custom text-[13px] px-4 pb-5 leading-relaxed text-gray-800 font-medium">
                                {replaceVariablesWithExamples(
                                  templateForm.body.text || 'Preencha o texto principal da mensagem',
                                  variableSamples
                                )}
                              </div>
                              {(templateForm.footer?.text || '').trim() ? (
                                <div className="border-t border-[#d7d7d7] bg-[#ececec] px-4 py-2 text-center text-[11px] text-gray-500">
                                  {templateForm.footer.text}
                                </div>
                              ) : null}
                            </div>
                            
                            {getCreateModalPreviewButtons(templateForm).length > 0 && (
                              <div className="mt-2 space-y-1.5 px-1 pb-1">
                                {getCreateModalPreviewButtons(templateForm).map((btn, bi) => (
                                  <PreviewActionButton
                                    key={bi}
                                    btn={btn}
                                    className="py-2.5 text-[13px] bg-white/90 backdrop-blur-sm shadow-sm"
                                  />
                                ))}
                              </div>
                            )}
                          </div>
                       </div>
                    </div>
                  </div>

                  {/* Right: Detailed Form (Col-8) */}
                  <div className="lg:col-span-8 space-y-6 bg-[#252525]/50 p-6 rounded-2xl border border-white/5">
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-x-6 gap-y-4">
                      <div className="space-y-2">
                        <label className="text-xs font-bold text-gray-400">Nome do template</label>
                        <input type="text" value={templateForm.name} onChange={(e) => setTemplateForm({...templateForm, name: e.target.value})} placeholder="Digite o nome..." className="w-full bg-[#3a3a3a] border border-white/5 p-3 rounded-lg text-white outline-none focus:border-primary transition-all" />
                        {selectedChannel?.provedor?.id != null && sanitizeTemplateName(templateForm.name) && (
                          <p className="text-[11px] text-gray-500 mt-1">
                            Nome enviado à Meta:{' '}
                            <span className="text-gray-300 font-mono">
                              {metaTemplateNameForProvedor(
                                sanitizeTemplateName(templateForm.name),
                                selectedChannel.provedor.id
                              )}
                            </span>
                          </p>
                        )}
                      </div>
                      <div className="space-y-2">
                        <label className="text-xs font-bold text-gray-400">Tipo de Template</label>
                        <select className="w-full bg-[#3a3a3a] border border-white/5 p-3 rounded-lg text-white outline-none focus:border-primary transition-all">
                          <option>Nenhum</option>
                          <option>Início de atendimento</option>
                          <option>Disparo</option>
                        </select>
                      </div>
                      <div className="space-y-2">
                        <label className="text-xs font-bold text-gray-400">Canal</label>
                        <select 
                          value={selectedChannel?.id || ''} 
                          onChange={(e) => {
                            const chan = channels.find(c => c.id === parseInt(e.target.value));
                            setSelectedChannel(chan);
                          }}
                          className="w-full bg-[#3a3a3a] border border-white/5 p-3 rounded-lg text-white outline-none focus:border-primary transition-all"
                        >
                          <option value="">Selecione um canal</option>
                          {channels.map(channel => (
                            <option key={channel.id} value={channel.id}>{channel.nome}</option>
                          ))}
                        </select>
                      </div>
                      <div className="space-y-2">
                        <label className="text-xs font-bold text-gray-400">Categoria</label>
                        <select className="w-full bg-[#3a3a3a] border border-white/5 p-3 rounded-lg text-white outline-none focus:border-primary transition-all">
                          <option>Conversas de utilidade</option>
                          <option>Conversas de autenticação</option>
                          <option>Conversas de marketing</option>
                        </select>
                      </div>
                      <div className="space-y-2">
                        <label className="text-xs font-bold text-gray-400">Idioma</label>
                        <select className="w-full bg-[#3a3a3a] border border-white/5 p-3 rounded-lg text-white outline-none focus:border-primary transition-all">
                          <option value="pt_BR">Portugues (BR)</option>
                          <option value="en_US">Inglês (US)</option>
                        </select>
                      </div>
                    </div>

                    <div className="pt-4 border-t border-white/5">
                      <h4 className="text-lg font-bold text-gray-200">Conteúdo</h4>
                      <p className="mt-1 text-xs text-gray-500 leading-relaxed">
                        Adicione cabeçalho, corpo e rodapé. A Meta analisa variáveis e conteúdo antes de aprovar o modelo.
                      </p>
                      <div className="mt-4 space-y-5">
                        <div className="space-y-2">
                          <label className="text-xs font-bold text-gray-400">
                            Amostra de mídia no cabeçalho{' '}
                            <span className="text-gray-600 font-normal">Opcional</span>
                          </label>
                          <select
                            value={headerModeFromForm(templateForm.header)}
                            onChange={(e) => {
                              const mode = e.target.value;
                              setTemplateForm({
                                ...templateForm,
                                header: applyHeaderMode(templateForm.header, mode),
                              });
                            }}
                            className="w-full bg-[#3a3a3a] border border-white/5 p-3 rounded-lg text-white"
                          >
                            <option value="none">Nenhum</option>
                            <option value="text">Texto</option>
                            <option value="image">Imagem</option>
                            <option value="video">Vídeo</option>
                            <option value="document">Documento</option>
                          </select>
                        </div>

                        {headerModeFromForm(templateForm.header) === 'text' && (
                          <div className="space-y-2">
                            <div className="flex items-center justify-between gap-2">
                              <label className="text-xs font-bold text-gray-400">
                                Cabeçalho <span className="text-gray-600 font-normal">Opcional</span>
                              </label>
                              <button
                                type="button"
                                onClick={() => {
                                  const ht = templateForm.header.text || '';
                                  const nums = extractVariableNumbers(ht);
                                  const nextNum = nums.length ? Math.max(...nums) + 1 : 1;
                                  const headerText = `${ht}{{${nextNum}}}`.slice(0, 60);
                                  setVariableSamples((prev) =>
                                    syncVariableSamples(
                                      `${headerText} ${templateForm.body.text}`,
                                      prev
                                    )
                                  );
                                  setTemplateForm({
                                    ...templateForm,
                                    header: { ...templateForm.header, text: headerText },
                                  });
                                }}
                                className="bg-[#3a3a3a] text-xs font-bold text-gray-300 px-3 py-1 rounded-md border border-white/10 hover:text-white transition-colors shrink-0"
                              >
                                + Variável
                              </button>
                            </div>
                            <input
                              type="text"
                              maxLength={60}
                              value={templateForm.header.text || ''}
                              onChange={(e) => {
                                const headerText = e.target.value.slice(0, 60);
                                setVariableSamples((prev) =>
                                  syncVariableSamples(
                                    `${headerText} ${templateForm.body.text}`,
                                    prev
                                  )
                                );
                                setTemplateForm({
                                  ...templateForm,
                                  header: { ...templateForm.header, text: headerText },
                                });
                              }}
                              placeholder="Linha curta no cabeçalho (máx. 60 caracteres)"
                              className="w-full bg-[#3a3a3a] border border-white/5 p-3 rounded-lg text-white"
                            />
                            <p className="text-[10px] text-gray-500 text-right">
                              {(templateForm.header.text || '').length}/60
                            </p>
                          </div>
                        )}

                        {HEADER_MEDIA_TYPES.includes(headerModeFromForm(templateForm.header)) && (
                          <div className="space-y-2">
                            <label className="text-xs font-bold text-gray-400">
                              Arquivo de exemplo do cabeçalho{' '}
                              <span className="text-gray-600 font-normal">Obrigatório na Meta</span>
                            </label>
                            <div className="flex flex-wrap items-center gap-3">
                              <input
                                type="file"
                                id="template-media-upload"
                                className="hidden"
                                accept={
                                  templateForm.header.type === 'document'
                                    ? 'application/pdf'
                                    : templateForm.header.type === 'video'
                                      ? 'video/*'
                                      : 'image/*'
                                }
                                onChange={(e) => {
                                  const file = e.target.files?.[0];
                                  if (!file) return;
                                  setTemplateForm({
                                    ...templateForm,
                                    header: {
                                      ...templateForm.header,
                                      type: headerModeFromForm(templateForm.header),
                                      file,
                                    },
                                  });
                                }}
                              />
                              <button
                                type="button"
                                onClick={() => document.getElementById('template-media-upload')?.click()}
                                className="bg-[#3a3a3a] text-gray-300 px-4 py-2 rounded-lg text-sm font-bold border border-white/10 hover:text-white transition-all"
                              >
                                {templateForm.header.file ? 'Trocar arquivo' : 'Selecionar arquivo'}
                              </button>
                              {templateForm.header.file && (
                                <div className="flex items-center gap-2 bg-primary/10 border border-primary/20 px-3 py-1.5 rounded-lg">
                                  <span className="text-[11px] text-primary font-bold uppercase">
                                    {templateForm.header.type}
                                  </span>
                                  <span className="text-[11px] text-gray-400 truncate max-w-[140px]">
                                    {templateForm.header.file.name}
                                  </span>
                                  <button
                                    type="button"
                                    onClick={() =>
                                      setTemplateForm({
                                        ...templateForm,
                                        header: {
                                          ...applyHeaderMode(templateForm.header, templateForm.header.type),
                                          file: null,
                                        },
                                      })
                                    }
                                    className="text-red-500 hover:text-red-400"
                                  >
                                    <Trash2 className="w-3 h-3" />
                                  </button>
                                </div>
                              )}
                            </div>
                          </div>
                        )}

                        <div className="space-y-2">
                        <div className="flex items-center justify-between">
                          <label className="text-xs font-bold text-gray-400 uppercase">Corpo da mensagem</label>

                          <button 
                            onClick={() => {
                              const nums = extractVariableNumbers(templateForm.body.text);
                              const nextNum = nums.length ? Math.max(...nums) + 1 : 1;
                              const text = `${templateForm.body.text} {{${nextNum}}}`;
                              setVariableSamples((prev) => syncVariableSamples(text, prev));
                              setTemplateForm({
                                ...templateForm,
                                body: { ...templateForm.body, text },
                              });
                            }}
                            className="bg-[#3a3a3a] text-xs font-bold text-gray-300 px-3 py-1 rounded-md border border-white/10 hover:text-white transition-colors"
                          >
                            + Variável
                          </button>
                        </div>
                        <textarea
                          rows={4}
                          value={templateForm.body.text}
                          onChange={(e) => {
                            const text = e.target.value;
                            setVariableSamples((prev) => syncVariableSamples(text, prev));
                            setTemplateForm({
                              ...templateForm,
                              body: { ...templateForm.body, text },
                            });
                          }}
                          className="w-full bg-[#3a3a3a] border border-white/5 p-4 rounded-lg text-white outline-none focus:border-primary"
                        />
                        
                        {/* Variables Sample List - Dynamic based on text */}
                        <div className="space-y-3 bg-[#1a1a1a] p-4 rounded-xl border border-white/5">
                          {collectTemplateVariableNumbers(templateForm.header.text, templateForm.body.text).map((num) => (
                            <div key={num} className="flex items-center gap-4">
                              <span className="text-gray-500 font-bold w-10 shrink-0">{`{{${num}}}`}</span>
                              <div className="flex-1 space-y-1">
                                <label className="text-[10px] text-gray-500 uppercase font-bold">
                                  Texto de exemplo (enviado à Meta)
                                </label>
                                <input
                                  type="text"
                                  value={variableSamples[num]?.example ?? ''}
                                  onChange={(e) => {
                                    setVariableSamples({
                                      ...variableSamples,
                                      [num]: { example: e.target.value },
                                    });
                                  }}
                                  placeholder={`Ex.: ${inferVariableSampleExample(templateForm.body.text, num)}`}
                                  className="w-full bg-[#2a2a2a] border border-white/5 p-2 rounded-lg text-sm text-white"
                                />
                              </div>
                            </div>
                          ))}
                          {collectTemplateVariableNumbers(templateForm.header.text, templateForm.body.text).length === 0 && (
                            <p className="text-xs text-gray-500 italic text-center py-2">
                              Nenhuma variável adicionada ainda.
                            </p>
                          )}
                        </div>
                        </div>
                      </div>
                    </div>

                    <div className="grid grid-cols-2 gap-6 pt-4">
                        <div className="space-y-2">
                          <label className="text-xs font-bold text-gray-400">
                            Ação <span className="text-gray-600 ml-1">Opcional</span>
                          </label>
                          <select
                            value={templateForm.templateAction || 'none'}
                            onChange={(e) => {
                              const templateAction = e.target.value;
                              const next = { ...templateForm, templateAction };
                              if (templateAction === 'buttons') {
                                next.buttons = ensureQuickReplyButtons(templateForm.buttons);
                              }
                              if (templateAction === 'link') {
                                next.linkButtons = ensureLinkButtons(templateForm.linkButtons);
                                setLinkSectionOpen([true, false]);
                              }
                              setTemplateForm(next);
                            }}
                            className="w-full bg-[#3a3a3a] border border-white/5 p-3 rounded-lg text-white"
                          >
                            <option value="none">Nenhuma ação</option>
                            <option value="order_details">Detalhes de pedido</option>
                            <option value="buttons">Botões</option>
                            <option value="link">Link</option>
                          </select>
                        </div>
                        <div className="space-y-2">
                          <label className="text-xs font-bold text-gray-400">Rodapé <span className="text-gray-600 ml-1">Opcional</span></label>
                          <input 
                            type="text" 
                            value={templateForm.footer?.text || ''}
                            onChange={(e) => setTemplateForm({...templateForm, footer: { ...templateForm.footer, text: e.target.value }})}
                            className="w-full bg-[#3a3a3a] border border-white/5 p-3 rounded-lg text-white" 
                            placeholder="Texto de rodapé..." 
                          />
                        </div>
                    </div>

                    {templateForm.templateAction === 'order_details' && (
                      <div className="space-y-4 pt-2">
                        <div className="bg-amber-500/10 border border-amber-500/30 p-4 rounded-xl flex gap-3">
                          <AlertCircle className="w-5 h-5 text-amber-400 shrink-0 mt-0.5" />
                          <p className="text-xs text-amber-100/90 leading-relaxed">
                            Para utilizar o recurso Order Details no WhatsApp, é necessário que essa
                            funcionalidade esteja habilitada em sua conta da Meta. Caso essa opção não
                            esteja disponível, recomendamos entrar em contato com o suporte da Meta ou
                            aguardar a liberação do recurso para sua conta.
                          </p>
                        </div>
                        <div className="space-y-2">
                          <label className="text-xs font-bold text-gray-400">
                            Tipo de detalhes do pedido
                          </label>
                          <select
                            value={templateForm.orderDetailsType || 'pix_boleto'}
                            onChange={(e) =>
                              setTemplateForm({
                                ...templateForm,
                                orderDetailsType: e.target.value,
                              })
                            }
                            className="w-full bg-[#3a3a3a] border border-white/5 p-3 rounded-lg text-white"
                          >
                            <option value="pix">Pix</option>
                            <option value="boleto">Código de barras</option>
                            <option value="pix_boleto">Pix / Código de barras</option>
                          </select>
                        </div>
                      </div>
                    )}

                    {templateForm.templateAction === 'buttons' && (
                      <div className="grid grid-cols-1 md:grid-cols-2 gap-4 pt-2">
                        {[0, 1, 2].map((index) => {
                          const labels = ['Primeiro botão', 'Segundo botão', 'Terceiro botão'];
                          const value =
                            templateForm.buttons?.[index]?.text ||
                            templateForm.buttons?.[index]?.title ||
                            '';
                          return (
                            <div
                              key={index}
                              className={`space-y-2 ${index === 2 ? 'md:col-span-2' : ''}`}
                            >
                              <label className="text-xs font-bold text-gray-400">
                                {labels[index]}
                                {index > 0 && (
                                  <span className="text-gray-600 ml-1">Opcional</span>
                                )}
                              </label>
                              <input
                                type="text"
                                maxLength={25}
                                value={value}
                                onChange={(e) => {
                                  const buttons = ensureQuickReplyButtons(templateForm.buttons);
                                  buttons[index] = {
                                    type: 'QUICK_REPLY',
                                    text: e.target.value,
                                  };
                                  setTemplateForm({ ...templateForm, buttons });
                                }}
                                placeholder={
                                  index === 0
                                    ? 'Ex.: Falar com atendente'
                                    : 'Texto do botão'
                                }
                                className="w-full bg-[#3a3a3a] border border-white/5 p-3 rounded-lg text-white"
                              />
                            </div>
                          );
                        })}
                      </div>
                    )}

                    {templateForm.templateAction === 'link' && (
                      <div className="space-y-3 pt-2">
                        {[0, 1].map((index) => {
                          const optional = index === 1;
                          const link = ensureLinkButtons(templateForm.linkButtons)[index];
                          const open = linkSectionOpen[index] ?? index === 0;
                          const updateLink = (patch) => {
                            const linkButtons = ensureLinkButtons(templateForm.linkButtons);
                            linkButtons[index] = { ...linkButtons[index], ...patch };
                            setTemplateForm({ ...templateForm, linkButtons });
                          };
                          return (
                            <div
                              key={index}
                              className="rounded-lg border border-white/10 bg-[#1f1f1f] overflow-hidden"
                            >
                              <button
                                type="button"
                                onClick={() => {
                                  const next = [...linkSectionOpen];
                                  next[index] = !open;
                                  setLinkSectionOpen(next);
                                }}
                                className="w-full flex items-center justify-between px-4 py-3 bg-[#2a2a2a] text-left"
                              >
                                <span className="text-sm font-bold text-gray-200">
                                  Link {index + 1}
                                  {optional && (
                                    <span className="text-gray-500 font-normal ml-2">Opcional</span>
                                  )}
                                </span>
                                {open ? (
                                  <ChevronUp className="w-4 h-4 text-gray-400" />
                                ) : (
                                  <ChevronDown className="w-4 h-4 text-gray-400" />
                                )}
                              </button>
                              {open && (
                                <div className="p-4 space-y-4">
                                  <div className="space-y-2">
                                    <label className="text-xs font-bold text-gray-400">
                                      Texto do botão
                                    </label>
                                    <input
                                      type="text"
                                      maxLength={25}
                                      value={link.buttonText || ''}
                                      onChange={(e) => updateLink({ buttonText: e.target.value })}
                                      className="w-full bg-[#3a3a3a] border border-white/5 p-3 rounded-lg text-white"
                                    />
                                  </div>
                                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                                    <div className="space-y-2">
                                      <label className="text-xs font-bold text-gray-400">Tipo</label>
                                      <select
                                        value={link.tipo || 'link'}
                                        onChange={(e) => updateLink({ tipo: e.target.value })}
                                        className="w-full bg-[#3a3a3a] border border-white/5 p-3 rounded-lg text-white"
                                      >
                                        <option value="link">Link</option>
                                        <option value="phone">Telefone</option>
                                      </select>
                                    </div>
                                    {link.tipo === 'phone' ? (
                                      <div className="space-y-2">
                                        <label className="text-xs font-bold text-gray-400">
                                          Telefone
                                        </label>
                                        <input
                                          type="tel"
                                          value={link.phone || ''}
                                          onChange={(e) => updateLink({ phone: e.target.value })}
                                          placeholder="+5511999999999"
                                          className="w-full bg-[#3a3a3a] border border-white/5 p-3 rounded-lg text-white"
                                        />
                                      </div>
                                    ) : (
                                      <>
                                        <div className="space-y-2">
                                          <label className="text-xs font-bold text-gray-400">
                                            Tipo de URL
                                          </label>
                                          <select
                                            value={link.urlType || 'static'}
                                            onChange={(e) =>
                                              updateLink({ urlType: e.target.value })
                                            }
                                            className="w-full bg-[#3a3a3a] border border-white/5 p-3 rounded-lg text-white"
                                          >
                                            <option value="static">Estático</option>
                                            <option value="dynamic">Dinâmico</option>
                                          </select>
                                        </div>
                                        <div className="space-y-2 md:col-span-2">
                                          <label className="text-xs font-bold text-gray-400">
                                            Link
                                          </label>
                                          <input
                                            type="url"
                                            value={link.url || ''}
                                            onChange={(e) => updateLink({ url: e.target.value })}
                                            placeholder={
                                              link.urlType === 'dynamic'
                                                ? 'https://seudominio.com.br/caminho/{{1}}'
                                                : 'https://seudominio.com.br/caminho'
                                            }
                                            className="w-full bg-[#3a3a3a] border border-white/5 p-3 rounded-lg text-white"
                                          />
                                          {link.urlType === 'dynamic' && (
                                            <div className="space-y-1 text-[11px] text-gray-500">
                                              <p>
                                                Parte fixa + {'{{1}}'} no final. Ex.:{' '}
                                                <span className="font-mono text-gray-400">
                                                  https://seudominio.com.br/public/contato/validacao/{'{{1}}'}
                                                </span>
                                              </p>
                                              <p>
                                                No disparo, o Niohub preenche {'{{1}}'} com o sufixo
                                                (ex.: <span className="font-mono">e988ed73-…</span> ou{' '}
                                                <span className="font-mono">uuid/print/assinado</span>).
                                                Se o SGP mandar a URL completa, o Niohub remove a parte
                                                fixa desta URL. A parte fixa precisa ser o prefixo real
                                                do link. Nada pode vir depois de {'{{1}}'} no template.
                                              </p>
                                            </div>
                                          )}
                                          {isMetaFlaggedTemplateUrl(link.url) && (
                                            <p className="text-[11px] text-amber-400">
                                              Use o domínio real do seu sistema (ex.: link do recibo no SGP).
                                              Domínios como exemplo.com são bloqueados pela Meta.
                                            </p>
                                          )}
                                        </div>
                                        {link.urlType === 'dynamic' && (
                                          <div className="space-y-2 md:col-span-2">
                                            <div className="flex items-center justify-between gap-3">
                                              <label className="text-xs font-bold text-gray-400">
                                                URL da amostra (Meta)
                                              </label>
                                              <label className="flex items-center gap-2 text-[11px] text-gray-400 select-none">
                                                <input
                                                  type="checkbox"
                                                  checked={!!link.txtMode}
                                                  onChange={(e) => updateLink({ txtMode: e.target.checked })}
                                                />
                                                Abrir recibo como TXT (?txt=1) no envio
                                              </label>
                                            </div>
                                            <input
                                              type="url"
                                              value={link.urlSample || ''}
                                              onChange={(e) => updateLink({ urlSample: e.target.value })}
                                              placeholder="https://seudominio.com.br/caminho/e988ed73-c16e-4c3f-96ad-3db2e10d9631"
                                              className="w-full bg-[#3a3a3a] border border-white/5 p-3 rounded-lg text-white"
                                            />
                                            <p className="text-[11px] text-gray-500">
                                              Exemplo completo (com um ID de teste) para a Meta aprovar o botão dinâmico.
                                            </p>
                                            <div className="space-y-1 text-[11px] text-amber-400/90">
                                              <p>
                                                A Meta exige que a URL do template termine exatamente em {'{{1}}'} (sem nada depois).
                                              </p>
                                              <p>
                                                Se o template for sobre “validar contato / confirmar WhatsApp”, prefera categoria{' '}
                                                <strong>Marketing</strong> — em Utilidade a Meta costuma rejeitar esse tipo de texto.
                                              </p>
                                            </div>
                                          </div>
                                        )}
                                      </>
                                    )}
                                  </div>
                                </div>
                              )}
                            </div>
                          );
                        })}
                      </div>
                    )}

                    <button 
                      disabled={creatingTemplate}
                      onClick={async () => {
                        if (!selectedChannel) { toast.error('Selecione um canal antes de enviar.'); return; }
                        if (!templateForm.body.text) { toast.error('O corpo da mensagem é obrigatório.'); return; }
                        
                        // Validação básica de obrigatoriedade
                        const bodyText = templateForm.body.text.trim();
                        if (bodyText.length < 5) {
                          toast.error('O texto da mensagem é muito curto.');
                          return;
                        }
                        
                        setCreatingTemplate(true);
                        try {
                          const token = localStorage.getItem('auth_token') || localStorage.getItem('token');
                          
                          // 1. Limpar nome (backend acrescenta sufixo _p{provedor_id} ao enviar à Meta)
                          const cleanName = sanitizeTemplateName(templateForm.name);
                          
                          // 2. Normalizar variáveis (Meta: não no início/fim do template)
                          const { text: finalText, warnings: bodyWarnings } = normalizeWhatsAppBodyForMeta(
                            templateForm.body.text
                          );
                          if (bodyWarnings.length > 0) {
                          }

                          // 3. Montar Componentes para a Meta com Exemplos (Samples)
                          const bodyComponent = {
                            type: 'BODY',
                            text: finalText
                          };

                          const varNums = collectTemplateVariableNumbers(templateForm.header.text, finalText);
                          const missingExamples = varNums.filter(
                            (n) => !(variableSamples[n]?.example ?? '').toString().trim()
                          );
                          if (missingExamples.length > 0) {
                            toast.error(
                              `Preencha o texto de exemplo para ${missingExamples.map((n) => `{{${n}}}`).join(', ')}.`
                            );
                            setCreatingTemplate(false);
                            return;
                          }
                          const bodyExamples = buildBodyTextExamples(finalText, variableSamples);
                          if (bodyExamples) {
                            bodyComponent.example = bodyExamples;
                          }

                          const components = [];

                          const mediaHeaderTypes = ['document', 'image', 'video'];
                          if (
                            mediaHeaderTypes.includes(templateForm.header.type) &&
                            !templateForm.header.file
                          ) {
                            toast.error(
                              'Selecione um arquivo de exemplo para o cabeçalho (PDF para documento, imagem ou vídeo).'
                            );
                            setCreatingTemplate(false);
                            return;
                          }

                          const headerText = (templateForm.header.text || '').trim();
                          if (templateForm.header.type === 'text' && headerText) {
                            if (headerText.length > 60) {
                              toast.error('O cabeçalho deve ter no máximo 60 caracteres.');
                              setCreatingTemplate(false);
                              return;
                            }
                            const headerComp = {
                              type: 'HEADER',
                              format: 'TEXT',
                              text: headerText,
                            };
                            const headerExamples = buildHeaderTextExamples(
                              headerText,
                              variableSamples
                            );
                            if (headerExamples) headerComp.example = headerExamples;
                            const missingHeader = extractVariableNumbers(headerText).filter(
                              (n) => !(variableSamples[n]?.example ?? '').toString().trim()
                            );
                            if (missingHeader.length) {
                              toast.error(
                                `Preencha o exemplo do cabeçalho para ${missingHeader.map((n) => `{{${n}}}`).join(', ')}.`
                              );
                              setCreatingTemplate(false);
                              return;
                            }
                            components.push(headerComp);
                          } else if (HEADER_MEDIA_TYPES.includes(templateForm.header.type)) {
                            components.push({
                              type: 'HEADER',
                              format: templateForm.header.type.toUpperCase(),
                            });
                          }

                          components.push(bodyComponent);

                          if (templateForm.footer.text) {
                            components.push({ type: 'FOOTER', text: templateForm.footer.text });
                          }

                          if (templateForm.templateAction === 'buttons') {
                            const quickReplies = buildButtonsForMetaSubmit(templateForm);
                            if (!quickReplies.length || !quickReplies[0]?.text) {
                              toast.error('Preencha o texto do primeiro botão.');
                              setCreatingTemplate(false);
                              return;
                            }
                          }

                          if (templateForm.templateAction === 'link') {
                            const link1 = ensureLinkButtons(templateForm.linkButtons)[0];
                            if (!(link1.buttonText || '').trim()) {
                              toast.error('Preencha o texto do botão no Link 1.');
                              setCreatingTemplate(false);
                              return;
                            }
                            if (link1.tipo === 'phone') {
                              if (!(link1.phone || '').trim()) {
                                toast.error('Informe o telefone no Link 1.');
                                setCreatingTemplate(false);
                                return;
                              }
                            } else if (!(link1.url || '').trim()) {
                              toast.error('Informe a URL no Link 1.');
                              setCreatingTemplate(false);
                              return;
                            }
                            if (link1.tipo !== 'phone' && (link1.urlType || 'static') === 'dynamic') {
                              const urlErr = validateDynamicTemplateUrl(link1.url);
                              if (urlErr) {
                                toast.error(urlErr);
                                setCreatingTemplate(false);
                                return;
                              }
                              // Normalizar no form para o usuário ver {{1}} no final
                              const normalized = normalizeDynamicTemplateUrl(link1.url);
                              if (normalized !== (link1.url || '').trim()) {
                                setTemplateForm((prev) => {
                                  const links = ensureLinkButtons(prev.linkButtons);
                                  links[0] = { ...links[0], url: normalized };
                                  return { ...prev, linkButtons: links };
                                });
                              }
                              if (!(link1.urlSample || '').trim()) {
                                toast.error(
                                  'Preencha a URL da amostra (Meta) com um exemplo completo, ex.: https://seudominio.com.br/caminho/e988ed73-c16e-4c3f-96ad-3db2e10d9631'
                                );
                                setCreatingTemplate(false);
                                return;
                              }
                            }
                            const metaLinks = buildButtonsForMetaSubmit(templateForm);
                            if (!metaLinks.length) {
                              toast.error('Configure o Link 1 corretamente antes de enviar.');
                              setCreatingTemplate(false);
                              return;
                            }
                          }

                          const allButtons = buildButtonsForMetaSubmit(templateForm);
                          if (allButtons.length > 0) {
                            components.push({ type: 'BUTTONS', buttons: allButtons });
                          }

                          const formData = new FormData();
                          formData.append('name', cleanName);
                          formData.append('category', templateForm.category === 'UTILITY' ? 'UTILITY' : 
                                      templateForm.category === 'MARKETING' ? 'MARKETING' : 'AUTHENTICATION');
                          formData.append('language', templateForm.language);
                          formData.append('components', JSON.stringify(components));
                          
                          if (templateForm.header.file) {
                            formData.append('media_file', templateForm.header.file);
                          }
                          
                          await axios.post(`/api/canais/${selectedChannel.id}/message-templates/`, formData, {
                            headers: { 
                              Authorization: `Token ${token}`,
                              'Content-Type': 'multipart/form-data'
                            }
                          });
                          
                          setShowCreateModal(false);
                          resetTemplateForm();
                          loadTemplates(selectedChannel);
                          toast.success('Template enviado com sucesso para aprovação!');
                        } catch (error) {
                          const errMsg =
                            error.response?.data?.error
                            || error.response?.data?.message
                            || (typeof error.response?.data === 'string' ? error.response.data : null)
                            || 'Verifique os campos e tente novamente.';
                          toast.error(`Erro ao enviar: ${typeof errMsg === 'string' ? errMsg : errMsg?.message || 'Verifique os campos e tente novamente.'}`);
                        } finally {
                          setCreatingTemplate(false);
                        }
                      }}
                      className={`w-full ${creatingTemplate ? 'bg-gray-600 cursor-not-allowed' : 'bg-[#ff8a00] hover:bg-[#e67e00]'} text-white py-4 rounded-xl font-bold shadow-lg shadow-orange-500/20 transition-all uppercase tracking-widest text-sm flex items-center justify-center gap-2`}
                    >
                      {creatingTemplate ? (
                        <>
                          <div className="animate-spin rounded-full h-4 w-4 border-t-2 border-b-2 border-white"></div>
                          Enviando...
                        </>
                      ) : 'Enviar para Aprovação'}
                    </button>
                  </div>
                </div>
            </div>
          </div>
        </div>
      )}

      {showDispatchModal && (
        <div className="fixed inset-0 z-[80] flex items-center justify-center bg-black/80 p-4 backdrop-blur-sm">
          <div className="flex max-h-[90vh] w-full max-w-3xl flex-col overflow-hidden rounded-2xl border border-white/10 bg-[#2a2a2a] shadow-2xl">
            <div className="flex items-center justify-between border-b border-white/10 bg-[#252525] px-5 py-4">
              <div>
                <h2 className="text-lg font-bold text-gray-100">Código para o SGP</h2>
                <p className="mt-1 text-xs text-gray-400">
                  Dois JSONs: <span className="font-semibold text-gray-300">Gateway</span> no HTTP Genérico e{' '}
                  <span className="font-semibold text-gray-300">Mensagem</span> no modelo de cobrança.
                </p>
              </div>
              <button
                type="button"
                onClick={() => {
                  setShowDispatchModal(false);
                  setCopiedWhich(null);
                }}
                className="text-gray-500 transition-colors hover:text-white"
              >
                <XCircle className="h-6 w-6" />
              </button>
            </div>

            <div className="flex-1 space-y-4 overflow-y-auto p-5 custom-scrollbar">
              {loadingDispatchConfig ? (
                <div className="flex flex-col items-center gap-3 py-12">
                  <div className="h-10 w-10 animate-spin rounded-full border-b-2 border-t-2 border-primary" />
                  <p className="text-sm text-gray-400">Gerando token e JSONs…</p>
                </div>
              ) : (
                <>
                  <div className="space-y-2">
                    <div className="flex items-center justify-between gap-2">
                      <p className="text-sm font-semibold text-gray-200">1. Gateway (HTTP Genérico)</p>
                      <button
                        type="button"
                        disabled={!gatewayConfigJson}
                        onClick={() => copyText(gatewayConfigJson, 'gateway')}
                        className={`flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs font-bold text-white transition-all disabled:cursor-not-allowed disabled:opacity-50 ${
                          copiedWhich === 'gateway' ? 'bg-green-600' : 'bg-blue-600 hover:bg-blue-700'
                        }`}
                      >
                        {copiedWhich === 'gateway' ? <Check className="h-3.5 w-3.5" /> : <Copy className="h-3.5 w-3.5" />}
                        {copiedWhich === 'gateway' ? 'Copiado!' : 'Copiar Gateway'}
                      </button>
                    </div>
                    <textarea
                      readOnly
                      value={gatewayConfigJson}
                      rows={8}
                      className="w-full resize-none rounded-xl border border-white/10 bg-[#1a1a1a] p-4 font-mono text-[11px] leading-relaxed text-green-300 focus:outline-none focus:ring-2 focus:ring-blue-500/50"
                      spellCheck={false}
                    />
                  </div>

                  <div className="space-y-2">
                    <div className="flex items-center justify-between gap-2">
                      <p className="text-sm font-semibold text-gray-200">2. Mensagem (modelo de cobrança)</p>
                      <button
                        type="button"
                        disabled={!mensagemConfigJson}
                        onClick={() => copyText(mensagemConfigJson, 'mensagem')}
                        className={`flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs font-bold text-white transition-all disabled:cursor-not-allowed disabled:opacity-50 ${
                          copiedWhich === 'mensagem' ? 'bg-green-600' : 'bg-blue-600 hover:bg-blue-700'
                        }`}
                      >
                        {copiedWhich === 'mensagem' ? <Check className="h-3.5 w-3.5" /> : <Copy className="h-3.5 w-3.5" />}
                        {copiedWhich === 'mensagem' ? 'Copiado!' : 'Copiar Mensagem'}
                      </button>
                    </div>
                    <textarea
                      readOnly
                      value={mensagemConfigJson}
                      rows={12}
                      className="w-full resize-none rounded-xl border border-white/10 bg-[#1a1a1a] p-4 font-mono text-[11px] leading-relaxed text-green-300 focus:outline-none focus:ring-2 focus:ring-blue-500/50"
                      spellCheck={false}
                    />
                  </div>
                </>
              )}
            </div>

            <div className="flex flex-wrap items-center justify-end gap-3 border-t border-white/10 bg-[#252525] px-5 py-4">
              <button
                type="button"
                onClick={() => {
                  setShowDispatchModal(false);
                  setCopiedWhich(null);
                }}
                className="rounded-lg px-4 py-2 text-sm font-semibold text-gray-400 transition-colors hover:text-white"
              >
                Fechar
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
