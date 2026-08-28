import React, { useEffect, useMemo, useRef, useState } from 'react';
import axios from 'axios';
import { SlidersHorizontal, ArrowLeft, ShieldAlert, Receipt, Filter, FileText } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import InvoiceCardMessagePreview, {
  INVOICE_PREVIEW_SAMPLES,
  renderInvoiceTemplatePreview,
} from './InvoiceCardMessagePreview';

const DEFAULT_BLOCKED_TICKET_MESSAGE =
  'Seu contrato está atualmente *suspenso*. Não é possível abrir chamados técnicos nessa situação.';

const DEFAULT_INVOICE_CARD_MESSAGE =
  '*Vencimento:* {{vencimento}}\n{{valores_texto}}\n\n{{instrucoes}}';

const INVOICE_TEMPLATE_VARS = [
  { key: '{{vencimento}}', desc: 'Data de vencimento' },
  { key: '{{valor}}', desc: 'Valor a cobrar (com multa/juros se houver)' },
  { key: '{{valor_original}}', desc: 'Valor original da fatura' },
  { key: '{{multa}}', desc: 'Valor da multa' },
  { key: '{{juros}}', desc: 'Valor dos juros' },
  { key: '{{valores_texto}}', desc: 'Bloco pronto (valor ou detalhe de atraso)' },
  { key: '{{instrucoes}}', desc: 'Passo a passo PIX/boleto (automático)' },
  { key: '{{fatura_id}}', desc: 'Número da fatura' },
  { key: '{{nome_cliente}}', desc: 'Nome do cliente' },
  { key: '{{nome_provedor}}', desc: 'Nome do provedor' },
];

export default function AttendanceRulesSettings({ provedorId }) {
  const navigate = useNavigate();
  const invoiceTextareaRef = useRef(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');
  const [allowWhenSuspended, setAllowWhenSuspended] = useState(false);
  const [blockMessage, setBlockMessage] = useState('');
  const [sendFinancialMenu, setSendFinancialMenu] = useState(false);
  const [autoResolveEnabled, setAutoResolveEnabled] = useState(false);
  const [autoResolveKeywords, setAutoResolveKeywords] = useState('');
  const [chatbotName, setChatbotName] = useState('');
  const [invoiceIntroTemplate, setInvoiceIntroTemplate] = useState('');
  const [provedorNome, setProvedorNome] = useState('');

  const authHeaders = () => ({
    Authorization: `Token ${localStorage.getItem('auth_token') || localStorage.getItem('token') || ''}`,
  });

  const ToggleSwitch = ({ checked, onChange, label }) => (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      onClick={() => onChange(!checked)}
      className={[
        'relative inline-flex items-center h-6 w-11 rounded-full transition-colors flex-shrink-0',
        checked ? 'bg-emerald-500' : 'bg-red-600',
      ].join(' ')}
    >
      <span
        className={[
          'inline-block h-5 w-5 transform rounded-full bg-white transition-transform duration-200',
          checked ? 'translate-x-5' : 'translate-x-1',
        ].join(' ')}
      />
      <span className="sr-only">{label}</span>
    </button>
  );

  useEffect(() => {
    async function load() {
      setLoading(true);
      setError('');
      try {
        const res = await axios.get(`/api/provedores/${provedorId}/`, { headers: authHeaders() });
        const prov = res.data;
        setAllowWhenSuspended(Boolean(prov.allow_ticket_when_contract_suspended));
        setBlockMessage(prov.suspended_contract_ticket_message || '');
        setSendFinancialMenu(Boolean(prov.send_financial_menu_after_suspended_block));
        setAutoResolveEnabled(Boolean(prov.auto_resolve_keyword_filter_enabled));
        setAutoResolveKeywords(prov.auto_resolve_keywords || '');
        setChatbotName(prov.chatbot_name || '');
        setInvoiceIntroTemplate(prov.invoice_intro_message_template || '');
        setProvedorNome(prov.nome || '');
      } catch {
        setError('Erro ao carregar regras de atendimento.');
      } finally {
        setLoading(false);
      }
    }
    if (provedorId) load();
  }, [provedorId]);

  const invoicePreviewSamples = useMemo(
    () => ({
      ...INVOICE_PREVIEW_SAMPLES,
      nome_provedor: provedorNome || INVOICE_PREVIEW_SAMPLES.nome_provedor,
    }),
    [provedorNome]
  );

  const invoicePreviewBody = useMemo(() => {
    const tpl = (invoiceIntroTemplate || '').trim() || DEFAULT_INVOICE_CARD_MESSAGE;
    return renderInvoiceTemplatePreview(tpl, invoicePreviewSamples);
  }, [invoiceIntroTemplate, invoicePreviewSamples]);

  const insertInvoiceVariable = (variable) => {
    const el = invoiceTextareaRef.current;
    const current = invoiceIntroTemplate || '';
    if (!el) {
      setInvoiceIntroTemplate(current + variable);
      return;
    }
    const start = el.selectionStart ?? current.length;
    const end = el.selectionEnd ?? current.length;
    const next = current.slice(0, start) + variable + current.slice(end);
    setInvoiceIntroTemplate(next);
    requestAnimationFrame(() => {
      el.focus();
      const pos = start + variable.length;
      el.setSelectionRange(pos, pos);
    });
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setSaving(true);
    setError('');
    setSuccess('');
    try {
      await axios.patch(
        `/api/provedores/${provedorId}/`,
        {
          allow_ticket_when_contract_suspended: allowWhenSuspended,
          suspended_contract_ticket_message: blockMessage.trim(),
          send_financial_menu_after_suspended_block: sendFinancialMenu,
          auto_resolve_keyword_filter_enabled: autoResolveEnabled,
          auto_resolve_keywords: autoResolveKeywords.trim(),
          chatbot_name: chatbotName.trim().slice(0, 80),
          invoice_intro_message_template: invoiceIntroTemplate.trim(),
        },
        { headers: authHeaders() }
      );
      setSuccess('Regras salvas com sucesso.');
    } catch {
      setError('Erro ao salvar regras.');
    } finally {
      setSaving(false);
    }
  };

  if (loading) {
    return <div className="p-6 text-muted-foreground">Carregando...</div>;
  }

  const blockWhenSuspended = !allowWhenSuspended;

  return (
    <div className="flex-1 min-h-0 w-full p-6 overflow-y-auto relative">
      <button
        type="button"
        onClick={() => navigate(`/app/accounts/${provedorId}/regras-atendimento`)}
        className="absolute left-6 top-6 px-4 py-2 rounded-lg bg-primary text-primary-foreground hover:opacity-90 transition-opacity inline-flex items-center gap-2"
      >
        <ArrowLeft className="w-4 h-4" />
        Voltar
      </button>

      <div className="flex items-center gap-3 mb-6 pt-14">
        <SlidersHorizontal className="w-8 h-8 text-primary" />
        <h1 className="text-2xl font-bold text-foreground">Configurações gerais</h1>
      </div>
      {error && (
        <div className="mb-4 p-3 rounded-lg bg-red-500/10 text-red-500 border border-red-500/30">{error}</div>
      )}
      {success && (
        <div className="mb-4 p-3 rounded-lg bg-emerald-500/10 text-emerald-600 border border-emerald-500/30">{success}</div>
      )}

      <form onSubmit={handleSubmit} className="space-y-6 w-full max-w-none">
        <section className="bg-card border border-border rounded-xl p-6 space-y-6 w-full">
          <div className="flex items-center justify-between gap-2 border-b border-border pb-4">
            <h2 className="text-lg font-semibold text-foreground">Identidade do chatbot</h2>
          </div>

          <div>
            <label className="block text-sm font-medium text-foreground mb-2">
              Nome do chatbot
            </label>
            <input
              type="text"
              maxLength={80}
              value={chatbotName}
              onChange={(e) => setChatbotName(e.target.value)}
              placeholder="Ex.: Nanet Atendimento"
              className="w-full max-w-xl rounded-lg border border-border bg-background px-3 py-2 text-sm text-foreground"
            />
            <p className="text-xs text-muted-foreground mt-2 leading-relaxed">
              Esse nome aparece no canto superior esquerdo das mensagens automáticas do bot
              em todos os canais (WhatsApp, Telegram, Instagram, etc.). Deixe em branco para
              não exibir nome.
            </p>
          </div>
        </section>

        <section className="bg-card border border-border rounded-xl p-6 space-y-6 w-full">
          <div className="flex items-center justify-between gap-2 border-b border-border pb-4">
            <div className="flex items-center gap-2">
              <FileText className="w-5 h-5 text-emerald-400" strokeWidth={2.5} />
              <h2 className="text-lg font-semibold text-foreground">Texto do card da fatura</h2>
            </div>
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-12 gap-8">
            <div className="lg:col-span-7 space-y-4">
              <div>
                <h3 className="text-base font-medium text-foreground mb-1">
                  Mensagem dentro do card de pagamento (WhatsApp Oficial)
                </h3>
                <p className="text-sm text-muted-foreground leading-relaxed">
                  Monte o texto do card da Meta enviado pela IA ou chatbot. Acompanhe à direita
                  como ficará para o cliente. Deixe em branco para usar o padrão do sistema.
                </p>
              </div>

              <textarea
                ref={invoiceTextareaRef}
                rows={12}
                value={invoiceIntroTemplate}
                onChange={(e) => setInvoiceIntroTemplate(e.target.value)}
                placeholder="Deixe em branco para usar a frase padrão."
                className="w-full rounded-lg border border-border bg-background px-3 py-2 text-sm text-foreground font-mono"
              />

              <div>
                <p className="text-xs text-muted-foreground mb-2">
                  Clique para inserir no texto. Use *texto* para negrito.
                </p>
                <div className="flex flex-wrap gap-2">
                  {INVOICE_TEMPLATE_VARS.map((v) => (
                    <button
                      key={v.key}
                      type="button"
                      title={v.desc}
                      onClick={() => insertInvoiceVariable(v.key)}
                      className="rounded-md border border-border bg-muted/40 px-2.5 py-1 text-xs font-mono text-foreground hover:bg-primary/15 hover:border-primary/40 transition-colors"
                    >
                      {v.key}
                    </button>
                  ))}
                </div>
              </div>

              <div className="rounded-lg border border-border/60 bg-muted/40 px-3 py-2">
                <p className="text-xs font-medium text-muted-foreground mb-1">
                  Texto padrão (se o campo ficar vazio):
                </p>
                <p className="text-sm text-foreground whitespace-pre-wrap font-mono">
                  {DEFAULT_INVOICE_CARD_MESSAGE}
                </p>
              </div>
            </div>

            <div className="lg:col-span-5 lg:sticky lg:top-4 lg:self-start space-y-3">
              <div>
                <h3 className="text-lg font-semibold text-foreground">Acompanhe o layout</h3>
                <p className="text-sm text-muted-foreground mt-1">
                  Prévia com dados de exemplo — igual ao card que o cliente recebe.
                </p>
              </div>
              <InvoiceCardMessagePreview
                bodyText={invoicePreviewBody}
                title="Fatura"
                faturaId={invoicePreviewSamples.fatura_id}
                total={invoicePreviewSamples.valor}
                footer={invoicePreviewSamples.nome_provedor}
                showPix
                showBoleto={false}
              />
            </div>
          </div>
        </section>

        <section className="bg-card border border-border rounded-xl p-6 space-y-6 w-full">
          <div className="flex items-center justify-between gap-2 border-b border-border pb-4">
            <div className="flex items-center gap-2">
              <ShieldAlert className="w-5 h-5 text-amber-400" strokeWidth={2.5} />
              <h2 className="text-lg font-semibold text-foreground">Contrato suspenso</h2>
            </div>
            <span className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
              (beta)
            </span>
          </div>

          <div className="flex items-start justify-between gap-4">
            <div className="flex-1">
              <h3 className="text-base font-medium text-foreground mb-1">
                Bloquear abertura de chamado com contrato suspenso
              </h3>
              <p className="text-sm text-muted-foreground">
                {blockWhenSuspended
                  ? 'Ligado (recomendado): clientes suspensos não abrem chamado no fluxo (ex.: Suporte, Sem internet). Você pode personalizar a mensagem abaixo.'
                  : 'Desligado: clientes com contrato suspenso podem seguir no fluxo e abrir chamado normalmente.'}
              </p>
            </div>
            <ToggleSwitch
              checked={blockWhenSuspended}
              onChange={(value) => setAllowWhenSuspended(!value)}
              label="Bloquear chamado com contrato suspenso"
            />
          </div>

          {blockWhenSuspended && (
            <div className="space-y-6">
              <div>
                <label className="block text-sm font-medium text-foreground mb-2">
                  Mensagem enviada ao cliente quando o chamado for bloqueado
                </label>
                <textarea
                  rows={5}
                  value={blockMessage}
                  onChange={(e) => setBlockMessage(e.target.value)}
                  placeholder="Deixe em branco para usar a frase padrão abaixo."
                  className="w-full rounded-lg border border-border bg-background px-3 py-2 text-sm text-foreground"
                />
                <p className="text-xs text-muted-foreground mt-2">
                  Use *texto* para negrito no WhatsApp.
                </p>
                <div className="mt-3 rounded-lg border border-border/60 bg-muted/40 px-3 py-2">
                  <p className="text-xs font-medium text-muted-foreground mb-1">Frase padrão (se o campo ficar vazio):</p>
                  <p className="text-sm text-foreground whitespace-pre-wrap">{DEFAULT_BLOCKED_TICKET_MESSAGE}</p>
                </div>
              </div>

              <div className="pt-4 border-t border-border flex items-start justify-between gap-4">
                <div className="flex-1">
                  <div className="flex items-center gap-2 mb-1">
                    <Receipt className="w-4 h-4 text-emerald-400" strokeWidth={2.5} />
                    <h3 className="text-base font-medium text-foreground">
                      Enviar menu financeiro após a mensagem de bloqueio
                    </h3>
                  </div>
                  <p className="text-sm text-muted-foreground">
                    {sendFinancialMenu
                      ? 'Ligado: após avisar que o chamado não pode ser aberto, o cliente recebe o menu financeiro do seu fluxo (2ª via, Pix/Boleto, liberação por confiança, etc.).'
                      : 'Desligado: apenas a mensagem de bloqueio é enviada.'}
                  </p>
                </div>
                <ToggleSwitch
                  checked={sendFinancialMenu}
                  onChange={setSendFinancialMenu}
                  label="Enviar menu financeiro após bloqueio"
                />
              </div>
            </div>
          )}
        </section>

        <section className="bg-card border border-border rounded-xl p-6 space-y-6 w-full">
          <div className="flex items-center justify-between gap-2 border-b border-border pb-4">
            <div className="flex items-center gap-2">
              <Filter className="w-5 h-5 text-sky-400" strokeWidth={2.5} />
              <h2 className="text-lg font-semibold text-foreground">Filtro</h2>
            </div>
            <span className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
              (beta)
            </span>
          </div>

          <div className="flex items-start justify-between gap-4">
            <div className="flex-1">
              <h3 className="text-base font-medium text-foreground mb-1">
                Não reabrir atendimento em mensagens automáticas
              </h3>
              <p className="text-sm text-muted-foreground leading-relaxed">
                Quando o chatbot já encerrou o atendimento e o gateway NioHub dispara
                uma mensagem automática, o atendimento permanece fechado se o texto
                contiver algum termo que você configurar abaixo.
              </p>
            </div>
            <ToggleSwitch
              checked={autoResolveEnabled}
              onChange={setAutoResolveEnabled}
              label="Filtro de mensagens automáticas"
            />
          </div>

          {autoResolveEnabled && (
            <div>
              <label className="block text-sm font-medium text-foreground mb-2">
                Termos do filtro (um por linha)
              </label>
              <textarea
                rows={8}
                value={autoResolveKeywords}
                onChange={(e) => setAutoResolveKeywords(e.target.value)}
                placeholder={'Ex.: pagamento\nrecebemos'}
                className="w-full rounded-lg border border-border bg-background px-3 py-2 text-sm text-foreground font-mono"
              />
              <p className="text-xs text-muted-foreground mt-2 leading-relaxed">
                Informe palavras ou trechos de texto, um por linha. Não precisa ser a
                mensagem inteira — basta aparecer em qualquer parte do texto enviado
                (sem diferenciar maiúsculas).
              </p>
            </div>
          )}
        </section>

        <div className="flex justify-end">
          <button
            type="submit"
            disabled={saving}
            className="px-6 py-2 rounded-lg bg-primary text-primary-foreground font-medium hover:opacity-90 disabled:opacity-50"
          >
            {saving ? 'Salvando...' : 'Salvar regras'}
          </button>
        </div>
      </form>
    </div>
  );
}
