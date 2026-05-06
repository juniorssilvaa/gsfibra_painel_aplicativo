import { useState, useEffect, useCallback } from 'react';
import { 
  User, 
  Search, 
  RotateCcw, 
  CheckCircle2,
  Database,
  Receipt,
  HeadphonesIcon,
  Link as LinkIcon,
  Barcode,
  QrCode,
  FileText,
  ScanLine,
  X,
  CreditCard
} from 'lucide-react';
import { Button } from './ui/button';
import { Input } from './ui/input';
import { toast } from 'sonner';
import axios from 'axios';

const SgpSidebar = ({ conversation, user, messages = [], onClose }) => {
  const [documento, setDocumento] = useState('');
  const [loading, setLoading] = useState(false);
  const [activeTab, setActiveTab] = useState('cliente');
  const [ticketType, setTicketType] = useState('');
  const [ticketDescription, setTicketDescription] = useState('');
  const [openingTicket, setOpeningTicket] = useState(false);
  const [manuallyReset, setManuallyReset] = useState(false);
  
  const [clienteData, setClienteData] = useState(null);
  const [selectedContrato, setSelectedContrato] = useState(null);
  const [faturas, setFaturas] = useState([]);
  const [loadingFaturas, setLoadingFaturas] = useState(false);

  const handleReset = () => {
    setClienteData(null);
    setDocumento('');
    setSelectedContrato(null);
    setFaturas([]);
    setActiveTab('cliente');
    setManuallyReset(true);
  };

  const provedorId = user?.provedor_id || user?.provedores_admin?.[0]?.id;

  const carregarFaturas = async (contratoId, doc) => {
    setLoadingFaturas(true);
    try {
      const token = localStorage.getItem('auth_token') || localStorage.getItem('token');
      const response = await axios.get(`/api/sgp/faturas/?contrato_id=${contratoId}&cpfcnpj=${doc}&provedor_id=${provedorId}`, {
        headers: { Authorization: `Token ${token}` }
      });
      setFaturas(response.data?.links || response.data?.faturas || []);
    } catch (error) {
      console.error('Erro faturas:', error);
    } finally {
      setLoadingFaturas(false);
    }
  };

  const buscarCliente = useCallback(async (doc) => {
    if (!doc || !provedorId) return;
    
    const docLimpo = doc.replace(/\D/g, '');
    if (docLimpo.length < 11) return;

    setLoading(true);
    try {
      const token = localStorage.getItem('auth_token') || localStorage.getItem('token');
      const response = await axios.get(`/api/sgp/consultar-cliente/?cpfcnpj=${docLimpo}&provedor_id=${provedorId}`, {
        headers: { Authorization: `Token ${token}` }
      });

      if (response.data && response.data.contratos && response.data.contratos.length > 0) {
        setClienteData(response.data);
        const primeiroContrato = response.data.contratos[0];
        setSelectedContrato(primeiroContrato);
        toast.success('Cliente encontrado no SGP!');
        
        const cId = primeiroContrato.id || primeiroContrato.id_contrato || primeiroContrato.contrato_id || primeiroContrato.contratoId || primeiroContrato.codigo;
        carregarFaturas(cId, docLimpo);
      } else {
        toast.error('Cliente não localizado no SGP.');
        setClienteData(null);
      }
    } catch (error) {
      console.error('Erro ao buscar cliente SGP:', error);
      toast.error('Ocorreu um erro ao consultar o SGP.');
    } finally {
      setLoading(false);
    }
  }, [provedorId]);

  useEffect(() => {
    setManuallyReset(false);
  }, [conversation?.id]);

  // Removida captura automática de CPF/CNPJ a pedido do usuário


  const copyToClipboard = (text, label) => {
    if(!text) return;
    navigator.clipboard.writeText(text);
    toast.success(`${label} copiado!`);
  };

  const currentFatura = faturas.length > 0 ? faturas[0] : null;

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
      console.error('Falha ao enviar interativo, tentando texto simples...', e);
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

    setLoading(true);
    const toastId = toast.loading(`Enviando ${tipo.toUpperCase()}...`);
    try {
      const token = localStorage.getItem('auth_token') || localStorage.getItem('token');
      const response = await axios.post('/api/sgp/enviar-fatura-interativa/', {
        fatura_id: faturaId,
        provedor_id: provedorId,
        conversation_id: conversation.id,
        tipo_pagamento: tipo,
        cpf_cnpj: documento || clienteData?.cpfCnpj
      }, {
        headers: { Authorization: `Token ${token}` }
      });

      if (response.data.success) {
        toast.success(`${tipo.toUpperCase()} enviado com sucesso!`, { id: toastId });
      } else {
        toast.error(response.data.error || 'Erro ao enviar fatura.', { id: toastId });
      }
    } catch (error) {
      console.error(`Erro ao enviar fatura ${tipo}:`, error);
      toast.error(error.response?.data?.error || `Erro ao enviar o ${tipo.toUpperCase()}.`, { id: toastId });
    } finally {
      setLoading(false);
    }
  };

  const handleGerarPix = (fatura) => {
    handleEnviarFaturaInterativa(fatura, 'pix');
  };

  const abrirChamado = async () => {
    const cid = selectedContrato?.id || selectedContrato?.id_contrato || selectedContrato?.contrato_id || selectedContrato?.contratoId || selectedContrato?.codigo;
    if (!cid) {
      toast.error('Nenhum contrato selecionado para abrir suporte.');
      return;
    }
    if (!ticketDescription || ticketDescription.trim().length < 5) {
      toast.error('Descreva o problema em detalhes para o chamado.');
      return;
    }
    const tipoNum = parseInt(String(ticketType).trim(), 10);
    if (ticketType === '' || ticketType === undefined || Number.isNaN(tipoNum) || tipoNum < 1) {
      toast.error('Informe o ID numérico do tipo de ocorrência no SGP.');
      return;
    }

    setOpeningTicket(true);
    try {
      const resp = await axios.post('/api/sgp/abrir-chamado/', {
        provedor_id: provedorId,
        contrato_id: cid,
        ocorrenciatipo: tipoNum,
        conteudo: ticketDescription
      }, {
        headers: { 'Authorization': `Token ${localStorage.getItem('token')}` }
      });
      toast.success('Chamado aberto com sucesso no SGP!');
      setTicketDescription('');
    } catch (err) {
      toast.error(err.response?.data?.error || 'Erro ao abrir chamado no SGP.');
    } finally {
      setOpeningTicket(false);
    }
  };

  // Se NÃO tiver cliente, exibe apenas o input
  if (!clienteData) {
    return (
      <div className="w-[320px] border-l bg-card flex flex-col h-full shadow-lg relative">
        <div className="p-4 border-b bg-muted/20">
          <div className="flex items-center gap-2 mb-4">
            <div className="w-8 h-8 rounded-lg bg-white/5 flex items-center justify-center">
              <Database className="w-4 h-4 text-muted-foreground" />
            </div>
            <h2 className="font-semibold text-sm">Acesso Rápido</h2>
          </div>
          <div className="space-y-2">
            <label className="text-xs font-semibold text-muted-foreground uppercase opacity-80">
              Buscar CPF/CNPJ
            </label>
            <div className="relative">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
              <Input 
                placeholder="Digite o documento..." 
                value={documento}
                onChange={(e) => {
                  setDocumento(e.target.value);
                  if (manuallyReset) setManuallyReset(false);
                }}
                onKeyDown={(e) => e.key === 'Enter' && buscarCliente(documento)}
                className="pl-9 h-10 w-full bg-background"
              />
              {loading && (
                <div className="absolute right-3 top-1/2 -translate-y-1/2">
                  <RotateCcw className="w-4 h-4 animate-spin text-[#10b981]" />
                </div>
              )}
            </div>
          </div>
        </div>
        <div className="flex-1 flex flex-col items-center justify-center p-8 text-center opacity-40">
           <User className="w-12 h-12 mb-3" />
           <p className="text-sm">Nenhum cliente selecionado</p>
        </div>
      </div>
    );
  }

  // Com cliente logado: Renderiza a estrutura Nativa
  return (
    <div className="w-[380px] border-l border-white/5 bg-[#1a1c23] flex h-full shadow-2xl relative">
        {/* Botão de Fechar Interno (Mobile/Desktop Quick Close) */}
        <button 
          onClick={onClose}
          className="absolute top-4 right-4 z-20 p-2 bg-white/10 text-[#f1f5f9] hover:bg-[#ef4444]/20 hover:text-[#ef4444] rounded-full transition-all shadow-md backdrop-blur-md border border-white/5"
          title="Fechar painel"
        >
          <X className="w-5 h-5" />
        </button>

         {/* BARRA LATERAL ESQUERDA (TABS) */}
         <div className="bg-[#12141a] w-[70px] min-w-[70px] h-full flex flex-col justify-start border-r border-white/5 py-4 gap-2">
           <button 
             onClick={() => setActiveTab('cliente')}
             className={`w-full h-[70px] flex flex-col gap-1 items-center justify-center transition-all ${activeTab === 'cliente' ? 'bg-[#24262d] border-l-2 border-[#10b981] text-white' : 'text-muted-foreground hover:bg-[#24262d]/50'}`}
           >
             <User className={`w-5 h-5 ${activeTab === 'cliente' ? 'text-[#10b981]' : ''}`} />
             <span className="text-[10px] font-medium">Cliente</span>
           </button>
           
           <button 
             onClick={() => setActiveTab('financeiro')}
             className={`w-full h-[70px] flex flex-col gap-1 items-center justify-center transition-all ${activeTab === 'financeiro' ? 'bg-[#24262d] border-l-2 border-[#10b981] text-white' : 'text-muted-foreground hover:bg-[#24262d]/50'}`}
           >
             <Receipt className={`w-5 h-5 ${activeTab === 'financeiro' ? 'text-[#10b981]' : ''}`} />
             <span className="text-[10px] font-medium">Financeiro</span>
           </button>
           
           <button 
             onClick={() => setActiveTab('suporte')}
             className={`w-full h-[70px] flex flex-col gap-1 items-center justify-center transition-all ${activeTab === 'suporte' ? 'bg-[#24262d] border-l-2 border-[#10b981] text-white' : 'text-muted-foreground hover:bg-[#24262d]/50'}`}
           >
             <HeadphonesIcon className={`w-5 h-5 ${activeTab === 'suporte' ? 'text-[#10b981]' : ''}`} />
             <span className="text-[10px] font-medium">Suporte</span>
           </button>
         </div>

         {/* ÁREA DE CONTEÚDO */}
         <div className="flex-1 w-[310px] h-full overflow-y-auto bg-[#1a1c23] p-4 flex flex-col">
               
               {/* === ABA CLIENTE === */}
               {activeTab === 'cliente' && (
               <div className="m-0 space-y-4 focus:outline-none flex-1 mt-0 animate-in fade-in duration-300">
                <div className="bg-[#24262d] rounded-xl p-4 shadow-sm border border-white/5">
                  <div className="flex justify-between items-center border-b border-white/10 pb-3 mb-4">
                     <span className="text-sm font-semibold text-gray-200">Cliente identificado</span>
                     <button onClick={handleReset} className="text-xs text-gray-400 hover:text-white mr-8 transition-colors">Alterar</button>
                  </div>
                  
                  {/* Nome da Integração */}
                  <div className="text-xs font-medium text-gray-300 mb-3 ml-1">sgp</div>

                  {/* Selector de Contrato */}
                  <select 
                    className="w-full bg-[#1a1c23] border border-white/10 rounded-lg p-2.5 text-sm text-gray-200 focus:outline-none mb-4 appearance-none"
                    value={selectedContrato?.id || selectedContrato?.id_contrato || selectedContrato?.contrato_id || selectedContrato?.contratoId || selectedContrato?.codigo || ''}
                    onChange={(e) => {
                      const c = clienteData.contratos.find(cnt => (cnt.id || cnt.id_contrato || cnt.contrato_id || cnt.contratoId || cnt.codigo) == e.target.value);
                      setSelectedContrato(c);
                      carregarFaturas((c.id || c.id_contrato || c.contrato_id || c.contratoId || c.codigo), documento || clienteData.cpfCnpj);
                    }}
                  >
                    {clienteData.contratos.map(c => {
                      const cId = c.id || c.id_contrato || c.contrato_id || c.contratoId || c.codigo;
                      return (
                        <option key={cId || Math.random()} value={cId}>{c.plano_nome || c.plano || c.servico || `Contrato ${cId}`}</option>
                      );
                    })}
                  </select>

                  <div className="space-y-3">
                    <div className="flex justify-between items-center border-b border-white/5 pb-2">
                       <span className="text-xs text-gray-400">Titular</span>
                       <span className="text-xs text-gray-200 font-medium text-right max-w-[150px] truncate">{clienteData.razaoSocial || clienteData.nome || selectedContrato?.razaoSocial || selectedContrato?.nomeCliente || selectedContrato?.cliente || 'Não informado'}</span>
                    </div>

                    <div className="flex justify-between items-center border-b border-white/5 pb-2">
                       <span className="text-xs text-gray-400">Plano</span>
                       <span className="text-xs text-gray-200 font-medium text-right max-w-[150px] truncate">{selectedContrato?.plano_nome || selectedContrato?.plano || selectedContrato?.servico || selectedContrato?.nomePlano || 'Não identificado'}</span>
                    </div>

                    <div className="flex justify-between items-center border-b border-white/5 pb-2">
                       <span className="text-xs text-gray-400">Documento</span>
                       <span className="text-xs text-gray-200 font-medium">{documento || clienteData.cpfCnpj || selectedContrato?.cpfCnpj || selectedContrato?.cpf || selectedContrato?.cnpj || 'Não informado'}</span>
                    </div>

                    <div className="flex justify-between items-center border-b border-white/5 pb-2">
                       <span className="text-xs text-gray-400">Status do contrato</span>
                       {selectedContrato?.contratoStatus === 1 || String(selectedContrato?.status_conexao).toLowerCase() === 'ativo' || String(selectedContrato?.status).toLowerCase() === 'ativo' ? (
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

                    <div className="flex justify-between items-center pt-1">
                       <span className="text-xs text-gray-400">Status da conexão</span>
                       {selectedContrato?.status_conexao_realtime?.status === 'online' ? (
                          <div className="bg-[#20362c] text-[#4ade80] px-2 py-0.5 rounded-full text-[10px] font-bold flex items-center gap-1.5 border border-[#4ade80]/20">
                            <div className="w-1.5 h-1.5 rounded-full bg-[#4ade80]"></div>
                            Serviço Online
                          </div>
                       ) : (
                          <div className="bg-[#362020] text-[#f87171] px-2 py-0.5 rounded-full text-[10px] font-bold flex items-center gap-1.5 border border-[#f87171]/20">
                            <div className="w-1.5 h-1.5 rounded-full bg-[#f87171]"></div>
                            Offline
                          </div>
                       )}
                    </div>
                  </div>
                </div>
               </div>
               )}

               {/* === ABA FINANCEIRO === */}
               {activeTab === 'financeiro' && (
               <div className="m-0 space-y-4 focus:outline-none flex-1 mt-0 animate-in fade-in duration-300">
                {/* Header Condensado */}
                <div className="bg-[#24262d] rounded-xl p-4 shadow-sm border border-white/5">
                  <div className="flex justify-between items-center border-b border-white/10 pb-3 mb-4">
                     <span className="text-sm font-semibold text-gray-200">Cliente identificado</span>
                     <button onClick={handleReset} className="text-xs text-gray-400 hover:text-white mr-8 transition-colors">Alterar</button>
                  </div>
                  <div className="text-xs font-medium text-gray-300 mb-3 ml-1">sgp</div>
                  <select 
                    className="w-full bg-[#1a1c23] border border-white/10 rounded-lg p-2.5 text-sm text-gray-200 focus:outline-none appearance-none"
                    value={selectedContrato?.id || selectedContrato?.id_contrato || selectedContrato?.contrato_id || selectedContrato?.contratoId || selectedContrato?.codigo || ''}
                    onChange={(e) => {
                      const c = clienteData.contratos.find(cnt => (cnt.id || cnt.id_contrato || cnt.contrato_id || cnt.contratoId || cnt.codigo) == e.target.value);
                      setSelectedContrato(c);
                      carregarFaturas((c.id || c.id_contrato || c.contrato_id || c.contratoId || c.codigo), documento || clienteData.cpfCnpj);
                    }}
                  >
                    {clienteData.contratos.map(c => {
                      const cId = c.id || c.id_contrato || c.contrato_id || c.contratoId || c.codigo;
                      return (
                        <option key={cId || Math.random()} value={cId}>{c.plano_nome || c.plano || c.servico || `Contrato ${cId}`}</option>
                      );
                    })}
                  </select>
                </div>

                {/* Card Financeiro */}
                <div className="bg-[#24262d] rounded-xl shadow-sm border border-white/5 overflow-hidden">
                  <div className="p-4 border-b border-white/10">
                     <h3 className="text-sm font-semibold text-gray-200 mb-1">Financeiro</h3>
                     <p className="text-xs text-gray-400">Última fatura em aberto</p>
                  </div>
                  
                  {loadingFaturas ? (
                    <div className="p-8 text-center"><RotateCcw className="w-6 h-6 animate-spin mx-auto text-[#10b981] opacity-50" /></div>
                  ) : !currentFatura ? (
                    <div className="p-8 text-center text-sm text-gray-400">Nenhuma fatura pendente.</div>
                  ) : (
                    <div className="p-0">
                       {/* Linha da Fatura */}
                       <div className="grid grid-cols-3 divide-x divide-white/10 bg-[#252536] border-y border-white/10">
                          <div className="p-3 text-center">
                            <span className="text-[10px] text-gray-400 block mb-1">Vencimento</span>
                            <span className="text-xs font-bold text-gray-200">
                              {(() => {
                                const d = currentFatura.vencimento_br || currentFatura.vencimento || currentFatura.data_vencimento || '';
                                if (!d || d.includes('/')) return d;
                                const parts = d.split('-');
                                return parts.length === 3 ? `${parts[2]}/${parts[1]}/${parts[0]}` : d;
                              })()}
                            </span>
                          </div>
                          <div className="p-3 text-center">
                            <span className="text-[10px] text-gray-400 block mb-1">Valor</span>
                            <span className="text-xs font-bold text-white">R$ {currentFatura.valor}</span>
                          </div>
                          <div className="p-3 flex flex-col items-center justify-center">
                            <span className="text-[10px] text-gray-400 block mb-1">Status</span>
                            <span className="bg-[#fff3cd] text-[#856404] text-[10px] px-2 py-0.5 rounded-full font-semibold border border-[#ffeeba]">
                               Em aberto
                            </span>
                          </div>
                       </div>

                       {/* Botões de Boleto */}
                       <div className="p-4 bg-[#24262d]">
                          <span className="text-[11px] text-gray-500 font-bold uppercase tracking-wider block mb-4 l-1 opacity-70">Ações de Pagamento</span>
                          <div className="grid grid-cols-2 gap-3">
                            {/* Cód Pix */}
                            <button 
                              onClick={() => handleGerarPix(currentFatura)} 
                              className="group bg-[#1a1c23] hover:bg-[#252536] transition-all duration-300 rounded-2xl flex flex-col items-center justify-center p-4 gap-2 border border-white/5 hover:border-[#10b981]/30 hover:scale-[1.02] active:scale-[0.98] shadow-sm"
                            >
                              <div className="bg-[#10b981]/10 p-2.5 rounded-xl group-hover:bg-[#10b981]/20 transition-colors">
                                <QrCode className="w-6 h-6 text-[#10b981]" />
                              </div>
                              <span className="text-[11px] font-bold text-gray-300 group-hover:text-white">Cód Pix</span>
                            </button>
  
                            {/* Cód Barras */}
                            <button 
                              onClick={() => handleEnviarFaturaInterativa(currentFatura, 'boleto')} 
                              className="group bg-[#1a1c23] hover:bg-[#252536] transition-all duration-300 rounded-2xl flex flex-col items-center justify-center p-4 gap-2 border border-white/5 hover:border-gray-500/30 hover:scale-[1.02] active:scale-[0.98] shadow-sm"
                            >
                              <div className="bg-gray-500/10 p-2.5 rounded-xl group-hover:bg-gray-500/20 transition-colors">
                                <Barcode className="w-6 h-6 text-gray-400" />
                              </div>
                              <span className="text-[11px] font-bold text-gray-300 group-hover:text-white">Boleto</span>
                            </button>
  
                            {/* Link Fatura */}
                            <button 
                              onClick={() => handleEnviarFaturaInterativa(currentFatura, 'ambos')}
                              className="group bg-[#1a1c23] hover:bg-[#252536] transition-all duration-300 rounded-2xl flex flex-col items-center justify-center p-4 gap-2 border border-white/5 hover:border-blue-500/30 hover:scale-[1.02] active:scale-[0.98] shadow-sm"
                            >
                              <div className="bg-blue-500/10 p-2.5 rounded-xl group-hover:bg-blue-500/20 transition-colors">
                                <LinkIcon className="w-6 h-6 text-blue-400" />
                              </div>
                              <span className="text-[11px] font-bold text-gray-300 group-hover:text-white">Link Fatura</span>
                            </button>
  
                            {/* PDF Fatura */}
                            <button 
                              onClick={() => toast.info('O PDF será enviado como documento no chat.')} 
                              className="group bg-[#1a1c23] hover:bg-[#252536] transition-all duration-300 rounded-2xl flex flex-col items-center justify-center p-4 gap-2 border border-white/5 hover:border-red-500/30 hover:scale-[1.02] active:scale-[0.98] shadow-sm"
                            >
                              <div className="bg-red-500/10 p-2.5 rounded-xl group-hover:bg-red-500/20 transition-colors">
                                <FileText className="w-6 h-6 text-red-500" />
                              </div>
                              <span className="text-[11px] font-bold text-gray-300 group-hover:text-white">PDF Fatura</span>
                            </button>
                          </div>
                       </div>
                    </div>
                  )}
                </div>
               </div>
               )}

               {/* === ABA SUPORTE === */}
               {activeTab === 'suporte' && (
               <div className="m-0 space-y-4 focus:outline-none flex-1 mt-0 animate-in fade-in duration-300">
                  <div className="bg-[#24262d] rounded-xl p-4 shadow-sm border border-white/5">
                   <div className="flex justify-between items-center border-b border-white/10 pb-3 mb-4">
                      <span className="text-sm font-semibold text-gray-200">Cliente identificado</span>
                      <button onClick={handleReset} className="text-xs text-gray-400 hover:text-white mr-8 transition-colors">Alterar</button>
                   </div>
                   <select 
                     className="w-full bg-[#1a1c23] border border-white/10 rounded-lg p-2.5 text-sm text-gray-200 focus:outline-none appearance-none"
                     value={selectedContrato?.id || selectedContrato?.id_contrato || selectedContrato?.contrato_id || selectedContrato?.contratoId || selectedContrato?.codigo || ''}
                     onChange={(e) => {
                       const c = clienteData.contratos.find(cnt => (cnt.id || cnt.id_contrato || cnt.contrato_id || cnt.contratoId || cnt.codigo) == e.target.value);
                       setSelectedContrato(c);
                     }}
                   >
                     {clienteData.contratos.map(c => {
                       const cId = c.id || c.id_contrato || c.contrato_id || c.contratoId || c.codigo;
                       return (
                         <option key={cId || Math.random()} value={cId}>{c.plano_nome || c.plano || c.servico || `Contrato ${cId}`}</option>
                       );
                     })}
                   </select>

                   {/* Abertura de Chamado */}
                   <div className="mt-4 pt-4 border-t border-white/10 space-y-4">
                      <span className="text-sm font-semibold text-gray-200">Abertura de Chamado</span>
                      
                      <div className="space-y-3">
                         <div className="space-y-1">
                           <label className="text-[10px] uppercase text-gray-500 font-semibold tracking-wide">Tipo de ocorrência (ID no SGP)</label>
                           <input
                             type="number"
                             min={1}
                             step={1}
                             className="w-full bg-[#1a1c23] border border-white/10 rounded-lg p-2.5 text-sm text-gray-200 focus:outline-none"
                             placeholder="Ex.: código do tipo na sua base SGP"
                             value={ticketType}
                             onChange={(e) => setTicketType(e.target.value)}
                           />
                           <p className="text-[10px] text-gray-500">Informe o código numérico cadastrado no seu SGP (sem valor fixo no sistema).</p>
                         </div>

                         <textarea
                            className="w-full h-24 bg-[#1a1c23] border border-white/10 rounded-lg p-3 text-sm text-gray-200 focus:outline-none resize-none placeholder:text-gray-500"
                            placeholder="Descreva o problema em detalhes..."
                            value={ticketDescription}
                            onChange={e => setTicketDescription(e.target.value)}
                         ></textarea>

                         <button 
                            onClick={abrirChamado}
                            disabled={openingTicket}
                            className="w-full bg-[#10b981] hover:bg-[#059669] text-white py-2.5 rounded-lg text-sm font-semibold transition-colors disabled:opacity-50"
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
