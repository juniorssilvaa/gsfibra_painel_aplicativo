import { useState, useEffect, useCallback } from 'react';
import { 
  User, 
  Search, 
  RotateCcw, 
  CheckCircle2,
  Database,
  Receipt,
  HeadphonesIcon,
  Barcode,
  QrCode,
  ScanLine,
  X,
  CreditCard
} from 'lucide-react';
import { Button } from './ui/button';
import { Input } from './ui/input';
import { toast } from '../lib/notify';
import axios from 'axios';
import {
  CONVERSATION_ACTION_BTN_BASE,
  paymentActionStyle,
} from '../constants/conversationActionButtons';

const sgpTabClass = (active) =>
  `w-full h-[70px] flex flex-col gap-1 items-center justify-center transition-all ${
    active
      ? 'bg-card text-foreground border-l-2 border-emerald-500 shadow-sm dark:bg-[#24262d]'
      : 'text-muted-foreground hover:bg-muted/70 dark:hover:bg-[#24262d]/50'
  }`;

const SGP_CARD =
  'bg-card rounded-xl p-4 shadow-md border border-border dark:border-white/5 dark:bg-[#24262d]';
const SGP_CARD_HEADER =
  'flex justify-between items-center border-b border-border pb-3 mb-4 dark:border-white/10';
const SGP_TITLE = 'text-sm font-semibold text-foreground';
const SGP_MUTED = 'text-xs text-muted-foreground';
const SGP_VALUE = 'text-xs font-medium text-foreground';
const SGP_SELECT =
  'w-full bg-background border border-input rounded-lg p-2.5 text-sm text-foreground shadow-sm focus:outline-none focus:ring-2 focus:ring-emerald-500/25 appearance-none dark:bg-[#1a1c23] dark:border-white/10 dark:text-gray-200';
const SGP_ROW =
  'flex justify-between items-center border-b border-border/70 pb-2 dark:border-white/5';
const SGP_PAY_ACTION_BTN = `${CONVERSATION_ACTION_BTN_BASE} w-full justify-center h-9`;

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

const SgpSidebar = ({
  conversation,
  user,
  messages = [],
  onClose,
  onConversationUpdate,
  billingSource = 'sgp',
}) => {
  const isAsaas = billingSource === 'asaas';
  const apiBase = isAsaas ? '/api/asaas-support' : '/api/sgp';
  const sourceName = isAsaas ? 'Asaas' : 'SGP';

  const [documento, setDocumento] = useState('');
  const [loading, setLoading] = useState(false);
  const [activeTab, setActiveTab] = useState('cliente');
  const [ticketType, setTicketType] = useState('1'); // Padrão
  const [ticketDescription, setTicketDescription] = useState('');
  const [openingTicket, setOpeningTicket] = useState(false);
  const [manuallyReset, setManuallyReset] = useState(false);
  
  const [clienteData, setClienteData] = useState(null);
  const [selectedContrato, setSelectedContrato] = useState(null);
  const [faturas, setFaturas] = useState([]);
  const [selectedFaturaId, setSelectedFaturaId] = useState(null);
  const [asaasClientes, setAsaasClientes] = useState(null);
  const [loadingFaturas, setLoadingFaturas] = useState(false);
  const [loadingConexao, setLoadingConexao] = useState(false);

  const handleReset = () => {
    setClienteData(null);
    setDocumento('');
    setSelectedContrato(null);
    setFaturas([]);
    setSelectedFaturaId(null);
    setAsaasClientes(null);
    setActiveTab('cliente');
    setManuallyReset(true);
  };

  const provedorId = user?.provedor_id || user?.provedores_admin?.[0]?.id;

  useEffect(() => {
    if (isAsaas && activeTab === 'suporte') {
      setActiveTab('cliente');
    }
  }, [isAsaas, activeTab]);

  const verificarConexao = useCallback(async (contratoId) => {
    if (isAsaas || !contratoId || !provedorId) return null;
    setLoadingConexao(true);
    try {
      const token = localStorage.getItem('auth_token') || localStorage.getItem('token');
      const response = await axios.get(
        `/api/sgp/verifica-acesso/?contrato_id=${contratoId}&provedor_id=${provedorId}`,
        { headers: { Authorization: `Token ${token}` } },
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
      const token = localStorage.getItem('auth_token') || localStorage.getItem('token');
      const response = await axios.get(`/api/sgp/faturas/?contrato_id=${contratoId}&cpfcnpj=${doc}&provedor_id=${provedorId}`, {
        headers: { Authorization: `Token ${token}` }
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
    if (docLimpo.length < 11) return;

    setLoading(true);
    setAsaasClientes(null);
    try {
      const token = localStorage.getItem('auth_token') || localStorage.getItem('token');
      const params = new URLSearchParams({
        cpfcnpj: docLimpo,
        provedor_id: String(provedorId),
      });
      if (conversation?.id) params.set('conversation_id', String(conversation.id));
      if (customerId) params.set('customer_id', String(customerId));
      const response = await axios.get(`${apiBase}/consultar-cliente/?${params}`, {
        headers: { Authorization: `Token ${token}` }
      });

      if (response.data?.precisa_escolher_cliente && Array.isArray(response.data.clientes)) {
        setAsaasClientes(response.data.clientes);
        setClienteData(null);
        toast.info('Há mais de um cliente Asaas com este documento. Escolha um.');
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
        toast.success(`Cliente encontrado no ${sourceName}!`);
      } else {
        toast.error(`Cliente não localizado no ${sourceName}.`);
        setClienteData(null);
      }
    } catch (error) {
      const msg =
        error?.response?.data?.error ||
        `Ocorreu um erro ao consultar o ${sourceName}.`;
      toast.error(msg);
    } finally {
      setLoading(false);
    }
  }, [provedorId, selecionarContrato, apiBase, isAsaas, sourceName, conversation?.id]);

  useEffect(() => {
    setManuallyReset(false);
  }, [conversation?.id]);

  // Removida captura automática de CPF/CNPJ a pedido do usuário


  const copyToClipboard = (text, label) => {
    if(!text) return;
    navigator.clipboard.writeText(text);
    toast.success(`${label} copiado!`);
  };

  const currentFatura =
    faturas.find((f) => String(f.fatura || f.id) === String(selectedFaturaId)) ||
    (faturas.length > 0 ? faturas[0] : null);

  const enviarParaChat = async (mensagem) => {
    if (!conversation?.id) {
       toast.error('Nenhuma conversa ativa para enviar a mensagem.');
       return;
    }
    const token = localStorage.getItem('auth_token') || localStorage.getItem('token');
    const toastId = toast.loading('Enviando mensagem...');
    try {
      const payload = {
        conversation_id: conversation.id,
        content: mensagem
      };
      await axios.post('/api/messages/send_text/', payload, {
        headers: { Authorization: `Token ${token}` }
      });
      toast.success('Enviado com sucesso no chat!', { id: toastId });
    } catch (e) {
      toast.error(e.response?.data?.error_message || e.response?.data?.error || 'Erro ao enviar mensagem no chat.', { id: toastId });
    }
  };

  const enviarInterativoParaChat = async (mensagem, botoes, header = null, footer = null, messageType = 'interactive', orderDetails = null) => {
    if (!conversation?.id) {
       toast.error('Nenhuma conversa ativa para enviar a mensagem.');
       return;
    }
    const token = localStorage.getItem('auth_token') || localStorage.getItem('token');
    const toastId = toast.loading('Enviando PIX...');
    try {
      const payload = {
        conversation_id: conversation.id,
        content: mensagem,
        buttons: botoes,
        header: header,
        footer: footer,
        message_type: messageType,
        order_details: orderDetails
      };
      await axios.post('/api/messages/send_interactive/', payload, {
        headers: { Authorization: `Token ${token}` }
      });
      toast.success('PIX enviado com sucesso!', { id: toastId });
    } catch (e) {
      try {
        await axios.post('/api/messages/send_text/', {
          conversation_id: conversation.id,
          content: `${header ? '*' + header + '*\n\n' : ''}${mensagem}`
        }, {
          headers: { Authorization: `Token ${token}` }
        });
        toast.success('Enviado como texto (sem botões)', { id: toastId });
      } catch (err) {
        toast.error('Erro ao enviar mensagem no chat.', { id: toastId });
      }
    }
  };

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
      const token = localStorage.getItem('auth_token') || localStorage.getItem('token');
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
        headers: { Authorization: `Token ${token}` }
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
        headers: { 'Authorization': `Token ${localStorage.getItem('token')}` }
      });
      const protocolo = resp?.data?.protocolo;
      toast.success(
        protocolo
          ? `Chamado aberto no SGP! Protocolo: ${protocolo}`
          : 'Chamado aberto com sucesso no SGP!'
      );
      setTicketDescription('');
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
      toast.apiError(err, 'Erro ao abrir chamado no SGP.');
    } finally {
      setOpeningTicket(false);
    }
  };

  // Se NÃO tiver cliente, exibe apenas o input
  if (!clienteData) {
    return (
      <div className="w-[320px] border-l border-border bg-card flex flex-col h-full shadow-lg relative">
        <div className="p-4 border-b border-border bg-muted/20">
          <div className="flex items-center gap-2 mb-4">
            <div className="w-8 h-8 rounded-lg bg-muted flex items-center justify-center dark:bg-white/5">
              <Database className="w-4 h-4 text-muted-foreground" />
            </div>
            <h2 className="font-semibold text-sm text-foreground">Acesso Rápido</h2>
          </div>
          <div className="space-y-2">
            <label className="text-xs font-semibold text-muted-foreground uppercase">
              Buscar CPF/CNPJ
            </label>
            <div className="relative">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
              <Input
                id="sgp-document-search"
                placeholder="Digite o documento..."
                value={documento}
                onChange={(e) => {
                  setDocumento(e.target.value);
                  if (manuallyReset) setManuallyReset(false);
                }}
                onKeyDown={(e) => e.key === 'Enter' && buscarCliente(documento)}
                className="niochat-input pl-9 h-10 w-full"
              />
              {loading && (
                <div className="absolute right-3 top-1/2 -translate-y-1/2">
                  <RotateCcw className="w-4 h-4 animate-spin text-[#10b981]" />
                </div>
              )}
            </div>
          </div>
        </div>
        <div className="flex-1 flex flex-col items-center justify-center p-8 text-center text-muted-foreground">
           {asaasClientes?.length ? (
             <div className="w-full space-y-2 text-left">
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
           ) : (
             <>
               <User className="w-12 h-12 mb-3 opacity-60" />
               <p className="text-sm text-foreground/70">Nenhum cliente selecionado</p>
             </>
           )}
        </div>
      </div>
    );
  }

  // Com cliente logado: Renderiza a estrutura Nativa
  return (
    <div className="w-[380px] border-l border-border bg-muted/40 flex h-full shadow-xl relative dark:bg-[#1a1c23] dark:border-white/5">
        <button
          onClick={onClose}
          className="absolute top-4 right-4 z-20 p-2 bg-card text-muted-foreground hover:bg-destructive/10 hover:text-destructive rounded-full transition-all shadow-md border border-border"
          title="Fechar painel"
        >
          <X className="w-5 h-5" />
        </button>

         <div className="bg-muted/80 w-[70px] min-w-[70px] h-full flex flex-col justify-start border-r border-border py-4 gap-2 dark:bg-[#12141a] dark:border-white/5">
           <button onClick={() => setActiveTab('cliente')} className={sgpTabClass(activeTab === 'cliente')}>
             <User className={`w-5 h-5 ${activeTab === 'cliente' ? 'text-emerald-600 dark:text-[#10b981]' : ''}`} />
             <span className="text-[10px] font-medium">Cliente</span>
           </button>

           <button onClick={() => setActiveTab('financeiro')} className={sgpTabClass(activeTab === 'financeiro')}>
             <Receipt className={`w-5 h-5 ${activeTab === 'financeiro' ? 'text-emerald-600 dark:text-[#10b981]' : ''}`} />
             <span className="text-[10px] font-medium">Financeiro</span>
           </button>

           {!isAsaas && (
             <button onClick={() => setActiveTab('suporte')} className={sgpTabClass(activeTab === 'suporte')}>
               <HeadphonesIcon className={`w-5 h-5 ${activeTab === 'suporte' ? 'text-emerald-600 dark:text-[#10b981]' : ''}`} />
               <span className="text-[10px] font-medium">Suporte</span>
             </button>
           )}
         </div>

         <div className="flex-1 w-[310px] h-full overflow-y-auto bg-muted/30 p-4 flex flex-col dark:bg-[#1a1c23]">
               
               {/* === ABA CLIENTE === */}
               {activeTab === 'cliente' && (
               <div className="m-0 space-y-4 focus:outline-none flex-1 mt-0 animate-in fade-in duration-300">
                <div className={SGP_CARD}>
                  <div className={SGP_CARD_HEADER}>
                     <span className={SGP_TITLE}>Cliente identificado</span>
                     <button onClick={handleReset} className={`${SGP_MUTED} hover:text-foreground mr-8 transition-colors`}>Alterar</button>
                  </div>

                  <select
                    className={`${SGP_SELECT} mb-4`}
                    value={getContratoId(selectedContrato)}
                    onChange={(e) => {
                      const c = clienteData.contratos.find((cnt) => getContratoId(cnt) == e.target.value);
                      selecionarContrato(
                        c,
                        documento || clienteData.cpfCnpj,
                        isAsaas ? (clienteData.faturas || faturas) : null,
                      );
                    }}
                  >
                    {clienteData.contratos.map((c) => {
                      const cId = getContratoId(c);
                      const planoLabel = getPlanoNome(c);
                      return (
                        <option key={cId || Math.random()} value={cId}>
                          {isAsaas
                            ? (planoLabel || `Cliente ${cId}`)
                            : (planoLabel ? `${planoLabel} — Contrato ${cId}` : `Contrato ${cId}`)}
                        </option>
                      );
                    })}
                  </select>

                  <div className="space-y-3">
                    <div className={SGP_ROW}>
                       <span className={SGP_MUTED}>Titular</span>
                       <span className={`${SGP_VALUE} text-right max-w-[150px] truncate`}>{clienteData.razaoSocial || clienteData.nome || selectedContrato?.razaoSocial || selectedContrato?.nomeCliente || selectedContrato?.cliente || 'Não informado'}</span>
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
               </div>
               )}

               {/* === ABA FINANCEIRO === */}
               {activeTab === 'financeiro' && (
               <div className="m-0 space-y-4 focus:outline-none flex-1 mt-0 animate-in fade-in duration-300">
                {/* Header Condensado */}
                <div className={SGP_CARD}>
                  <div className={SGP_CARD_HEADER}>
                     <span className={SGP_TITLE}>Cliente identificado</span>
                     <button onClick={handleReset} className={`${SGP_MUTED} hover:text-foreground mr-8 transition-colors`}>Alterar</button>
                  </div>
                  <select
                    className={`${SGP_SELECT} mb-3`}
                    value={getContratoId(selectedContrato)}
                    onChange={(e) => {
                      const c = clienteData.contratos.find((cnt) => getContratoId(cnt) == e.target.value);
                      selecionarContrato(
                        c,
                        documento || clienteData.cpfCnpj,
                        isAsaas ? (clienteData.faturas || faturas) : null,
                      );
                    }}
                  >
                    {clienteData.contratos.map((c) => {
                      const cId = getContratoId(c);
                      const planoLabel = getPlanoNome(c);
                      return (
                        <option key={cId || Math.random()} value={cId}>
                          {isAsaas
                            ? (planoLabel || `Cliente ${cId}`)
                            : (planoLabel ? `${planoLabel} — Contrato ${cId}` : `Contrato ${cId}`)}
                        </option>
                      );
                    })}
                  </select>
                </div>

                <div className={`${SGP_CARD} overflow-hidden p-0`}>
                  <div className="p-4 border-b border-border dark:border-white/10">
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
                    <div className="p-8 text-center"><RotateCcw className="w-6 h-6 animate-spin mx-auto text-emerald-600 opacity-50 dark:text-[#10b981]" /></div>
                  ) : !currentFatura ? (
                    <div className={`p-8 text-center text-sm ${SGP_MUTED}`}>Nenhuma fatura pendente.</div>
                  ) : (
                    <div className="p-0">
                       <div className="grid grid-cols-3 divide-x divide-border bg-muted/50 border-y border-border dark:divide-white/10 dark:bg-[#252536] dark:border-white/10">
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
                            <span className="bg-amber-100 text-amber-900 text-[10px] px-2 py-0.5 rounded-full font-semibold border border-amber-200 dark:bg-[#fff3cd] dark:text-[#856404] dark:border-[#ffeeba]">
                               {currentFatura.status_label || 'Em aberto'}
                            </span>
                          </div>
                       </div>

                       <div className="p-4 bg-card dark:bg-[#24262d]">
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
               </div>
               )}

               {/* === ABA SUPORTE === */}
               {!isAsaas && activeTab === 'suporte' && (
               <div className="m-0 space-y-4 focus:outline-none flex-1 mt-0 animate-in fade-in duration-300">
                  <div className={SGP_CARD}>
                   <div className={SGP_CARD_HEADER}>
                      <span className={SGP_TITLE}>Cliente identificado</span>
                      <button onClick={handleReset} className={`${SGP_MUTED} hover:text-foreground mr-8 transition-colors`}>Alterar</button>
                   </div>
                   <select
                     className={SGP_SELECT}
                     value={getContratoId(selectedContrato)}
                     onChange={(e) => {
                       const c = clienteData.contratos.find((cnt) => getContratoId(cnt) == e.target.value);
                       selecionarContrato(c, documento || clienteData.cpfCnpj);
                     }}
                   >
                     {clienteData.contratos.map((c) => {
                       const cId = getContratoId(c);
                       const planoLabel = getPlanoNome(c);
                       return (
                         <option key={cId || Math.random()} value={cId}>
                           {planoLabel ? `${planoLabel} — Contrato ${cId}` : `Contrato ${cId}`}
                         </option>
                       );
                     })}
                   </select>

                   {/* Abertura de Chamado */}
                   <div className="mt-4 pt-4 border-t border-border space-y-4 dark:border-white/10">
                      <span className={SGP_TITLE}>Abertura de Chamado</span>

                      <div className="space-y-3">
                         <select
                            className={SGP_SELECT}
                            value={ticketType}
                            onChange={e => setTicketType(e.target.value)}
                         >
                            <option value="1">Sem acesso à internet</option>
                            <option value="2">Serviço com lentidão</option>
                            <option value="3">Dúvidas financeiras</option>
                            <option value="4">Outros problemas</option>
                         </select>

                         <textarea
                            className="w-full h-24 bg-background border border-input rounded-lg p-3 text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-emerald-500/25 resize-none placeholder:text-muted-foreground dark:bg-[#1a1c23] dark:border-white/10 dark:text-gray-200"
                            placeholder="Descreva o problema em detalhes..."
                            value={ticketDescription}
                            onChange={e => setTicketDescription(e.target.value)}
                         />

                         <button
                            onClick={abrirChamado}
                            disabled={openingTicket}
                            className="w-full bg-emerald-600 hover:bg-emerald-700 text-white py-2.5 rounded-lg text-sm font-semibold shadow-sm transition-colors disabled:opacity-50"
                          >
                            {openingTicket ? 'Abrindo chamado...' : 'Abrir chamado'}
                         </button>
                      </div>
                   </div>
                  </div>
               </div>
               )}
         </div>
    </div>
  );
};

export default SgpSidebar;
