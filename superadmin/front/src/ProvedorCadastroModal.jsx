import React, { useEffect, useMemo, useState } from 'react';
import {
  Copy,
  Edit,
  ExternalLink,
  RefreshCw,
  X,
} from 'lucide-react';

const inputClass =
  'w-full px-3 py-2 rounded-md border border-input bg-background text-foreground text-sm placeholder:text-muted-foreground focus:border-primary/50 focus:ring-1 focus:ring-primary/25 outline-none';

const cardBtn = 'ficha-btn';
const cancelBtn = 'ficha-btn ficha-btn-cancel';
const dangerBtn = 'ficha-btn ficha-btn-danger';
const updateBtn = 'ficha-btn ficha-btn-update';
const saveBtn = 'ficha-btn ficha-btn-save';

const isInterBilling = (formOrProv) => {
  if (!formOrProv) return false;
  if ((formOrProv.billing_provider || '') === 'inter') return true;
  return String(formOrProv.asaas_subscription_id || '').startsWith('INTER-SUB-');
};

const subscriptionStatusUi = (status) => {
  const st = (status || '').toUpperCase();
  if (st === 'ACTIVE') return { label: 'Ativa', tone: 'text-emerald-700 dark:text-emerald-400', live: true };
  if (st === 'PENDING') return { label: 'Pendente', tone: 'text-sky-700 dark:text-sky-400', live: true };
  if (st === 'INACTIVE') return { label: 'Inativa', tone: 'text-amber-700 dark:text-amber-400', live: false };
  if (st === 'OVERDUE') return { label: 'Vencida', tone: 'text-red-600 dark:text-red-400', live: false };
  return { label: st || 'Sem status', tone: 'text-muted-foreground', live: false };
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
    return { label: 'Pago', tone: 'text-emerald-700 dark:text-emerald-400' };
  }
  if (status === 'OVERDUE') {
    return { label: 'Vencido', tone: 'text-red-600 dark:text-red-400' };
  }
  return { label: 'Pendente', tone: 'text-amber-700 dark:text-amber-400' };
};

const formatBrDate = (iso) => {
  if (!iso) return '—';
  const raw = String(iso).slice(0, 10);
  const [y, m, d] = raw.split('-');
  if (!y || !m || !d) return iso;
  return `${d}/${m}/${y}`;
};

const formatBrDateTime = (iso) => {
  if (!iso) return '—';
  try {
    return new Date(iso).toLocaleString('pt-BR');
  } catch {
    return iso;
  }
};

const TABS = [
  { id: 'cadastro', label: 'Cadastro' },
  { id: 'financeiro', label: 'Financeiro' },
  { id: 'plano', label: 'Plano' },
  { id: 'atualizacao', label: 'Atualização' },
];

const CADASTRO_SUBS = [
  { id: 'dados', label: 'Dados do Cliente' },
  { id: 'endereco', label: 'Endereço' },
  { id: 'solucoes', label: 'Soluções' },
  { id: 'outros', label: 'Outros' },
];

function Field({ label, required, children, hint }) {
  return (
    <div className="grid grid-cols-1 items-start gap-1 sm:grid-cols-[168px_minmax(0,1fr)] sm:gap-4 sm:items-center">
      <label className="text-[13px] text-foreground sm:pt-0">
        {label}{required ? <span className="text-primary"> *</span> : null}
      </label>
      <div className="min-w-0">
        {children}
        {hint ? <p className="mt-1 text-[11px] text-muted-foreground">{hint}</p> : null}
      </div>
    </div>
  );
}

export default function ProvedorCadastroModal({
  open,
  onClose,
  form,
  onChange,
  onSubmit,
  planoFields,
  loadingEdit,
  errorMsg,
  asaasSandbox,
  subscriptionPayments,
  loadingPayments,
  paymentEdit,
  setPaymentEdit,
  savingPayment,
  handleSavePayment,
  subscriptionEdit,
  setSubscriptionEdit,
  savingSubscription,
  handleSaveSubscription,
  handleVerifyAsaas,
  handleClearAsaasSubscription,
  handleCreateSubscription,
  handleSyncAsaas,
  openProviderAppPanel,
  openingAppPanelId,
  onApplyPromise,
  onCancelPromise,
  savingPromise,
}) {
  const [tab, setTab] = useState('cadastro');
  const [cadastroSub, setCadastroSub] = useState('dados');
  const [promiseUntil, setPromiseUntil] = useState('');
  const [promiseNote, setPromiseNote] = useState('');

  useEffect(() => {
    if (!open) return;
    setTab('cadastro');
    setCadastroSub('dados');
  }, [open, form?.id]);

  useEffect(() => {
    setPromiseUntil(form?.payment_promise_until ? String(form.payment_promise_until).slice(0, 10) : '');
    setPromiseNote(form?.payment_promise_note || '');
  }, [form?.id, form?.payment_promise_until, form?.payment_promise_note]);

  const promiseActive = Boolean(form?.payment_promise_active);
  const isActive = form?.is_active !== false;
  const inter = isInterBilling(form);

  const statusPills = useMemo(() => {
    const pills = [];
    if (promiseActive) {
      pills.push({ label: `Promessa até ${formatBrDate(form.payment_promise_until)}`, tone: 'text-amber-700 dark:text-amber-300' });
    } else if (isActive) {
      pills.push({ label: 'Ativo', tone: 'text-emerald-700 dark:text-emerald-400' });
    } else {
      pills.push({ label: 'Suspenso', tone: 'text-red-600 dark:text-red-400' });
    }
    if (form?.enable_chat) pills.push({ label: 'Chat', tone: 'text-orange-600 dark:text-orange-300' });
    if (form?.enable_mobile_app) pills.push({ label: 'App', tone: 'text-sky-700 dark:text-sky-300' });
    if (form?.enable_acs) pills.push({ label: 'ACS', tone: 'text-violet-700 dark:text-violet-300' });
    return pills;
  }, [form, promiseActive, isActive]);

  if (!open) return null;

  const tabTitle = TABS.find((t) => t.id === tab)?.label || 'Cadastro';

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-3 sm:p-6">
      <div className="ficha-provedor flex h-[92vh] w-full max-w-6xl flex-col overflow-hidden rounded-lg border border-border bg-card text-foreground shadow-2xl">
        <div className="h-1.5 shrink-0 bg-primary" />

        <div className="flex items-start justify-between gap-4 border-b border-border px-5 py-3 sm:px-6">
          <div className="min-w-0">
            <h2 className="text-lg font-semibold text-foreground">{tabTitle}</h2>
            <p className="mt-0.5 text-xs text-muted-foreground">Ficha do provedor · dados, cobrança e acesso</p>
          </div>
          <div className="flex shrink-0 items-center gap-2">
            {inter ? (
              <span className="ficha-btn hidden !px-2.5 !py-1 !text-[10px] !font-bold !uppercase sm:inline">
                Portador Inter
              </span>
            ) : form.asaas_customer_id ? (
              <span className="ficha-btn hidden !px-2.5 !py-1 !text-[10px] !font-bold !uppercase sm:inline">
                Cliente Asaas
              </span>
            ) : null}
            {form.id && (
              <button
                type="button"
                onClick={() => openProviderAppPanel(form.id)}
                disabled={openingAppPanelId === form.id}
                className="ficha-btn !px-3 !py-1 !text-[10px] !font-bold !uppercase"
              >
                {openingAppPanelId === form.id ? 'Abrindo…' : 'Painel do App'}
              </button>
            )}
            <button type="button" className="ficha-btn !p-1.5" onClick={onClose} aria-label="Fechar">
              <X className="h-5 w-5" />
            </button>
          </div>
        </div>

        <div className="border-b border-border bg-muted/50 px-5 py-3 sm:px-6">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div className="min-w-0 space-y-1">
              <p className="text-sm text-foreground">
                <span className="text-muted-foreground">Provedor ID:</span>{' '}
                <span className="font-mono font-semibold text-sky-700 dark:text-sky-300">{form.id}</span>
                {'  '}
                <span className="font-semibold uppercase tracking-wide">{form.nome || '—'}</span>
              </p>
              <p className="text-xs text-muted-foreground">
                CPF/CNPJ: <span className="font-mono text-foreground">{form.cpf_cnpj || '—'}</span>
                {form.email_contato ? <> · {form.email_contato}</> : null}
              </p>
              <p className="flex flex-wrap gap-x-3 gap-y-0.5 text-xs">
                {statusPills.map((p) => (
                  <span key={p.label} className={`font-semibold ${p.tone}`}>{p.label}</span>
                ))}
              </p>
            </div>
            <div className="text-right text-xs text-muted-foreground">
              <p>Cadastro: {formatBrDateTime(form.created_at)}</p>
              <p className="mt-0.5">
                Versão {form.current_version && form.current_version !== '1.0.0' ? form.current_version : '—'}
                {' · '}
                {(form.release_channel || 'stable') === 'beta' ? 'Beta' : form.release_channel === 'manual' ? 'Manual' : 'Estável'}
              </p>
            </div>
          </div>
        </div>

        <div className="flex flex-wrap gap-1 border-b border-border bg-muted/40 px-4 py-2 sm:px-5">
          {TABS.map((item) => {
            const active = tab === item.id;
            return (
              <button
                key={item.id}
                type="button"
                onClick={() => setTab(item.id)}
                className={`px-3.5 py-1.5 text-[13px] font-medium transition ${
                  active
                    ? 'rounded-md bg-primary text-white'
                    : 'ficha-btn !rounded-md !px-3.5 !py-1.5 !text-[13px]'
                }`}
              >
                {item.label}
              </button>
            );
          })}
        </div>

        {tab === 'cadastro' && (
          <div className="flex flex-wrap gap-1 border-b border-border bg-muted/30 px-4 py-1.5 sm:px-5">
            {CADASTRO_SUBS.map((item) => (
              <button
                key={item.id}
                type="button"
                onClick={() => setCadastroSub(item.id)}
                className={`ficha-btn !px-3 !py-1 !text-[12px] ${cadastroSub === item.id ? '!font-semibold' : ''}`}
              >
                {item.label}
              </button>
            ))}
          </div>
        )}

        <form onSubmit={onSubmit} className="flex min-h-0 flex-1 flex-col">
          <div className="min-h-0 flex-1 overflow-y-auto px-5 py-5 sm:px-7">
            {tab === 'cadastro' && cadastroSub === 'dados' && (
              <section className="space-y-4">
                <h3 className="text-sm font-semibold text-foreground">Dados</h3>
                <div className="space-y-3 rounded-lg border border-border bg-muted/40 p-4">
                  <Field label="Nome" required>
                    <input type="text" name="nome" className={inputClass} value={form.nome || ''} onChange={onChange} required />
                  </Field>
                  <Field label="CPF ou CNPJ" required>
                    <input type="text" name="cpf_cnpj" className={inputClass} value={form.cpf_cnpj || ''} onChange={onChange} required placeholder="Apenas números" />
                  </Field>
                  <Field label="Razão social">
                    <input type="text" name="company" className={inputClass} value={form.company || ''} onChange={onChange} />
                  </Field>
                  <Field label="Site oficial">
                    <input type="url" name="site_oficial" className={inputClass} value={form.site_oficial || ''} onChange={onChange} />
                  </Field>
                  <Field label="E-mail">
                    <input type="email" name="email_contato" className={inputClass} value={form.email_contato || ''} onChange={onChange} />
                  </Field>
                  <Field label="Telefone">
                    <input type="text" name="phone" className={inputClass} value={form.phone || ''} onChange={onChange} />
                  </Field>
                  <Field label="Celular">
                    <input type="text" name="mobile_phone" className={inputClass} value={form.mobile_phone || ''} onChange={onChange} />
                  </Field>
                </div>
              </section>
            )}

            {tab === 'cadastro' && cadastroSub === 'endereco' && (
              <section className="space-y-4">
                <h3 className="text-sm font-semibold text-foreground">Endereço</h3>
                <div className="space-y-3 rounded-lg border border-border bg-muted/40 p-4">
                  <Field label="CEP">
                    <input type="text" name="postal_code" className={inputClass} value={form.postal_code || ''} onChange={onChange} />
                  </Field>
                  <Field label="Logradouro">
                    <input type="text" name="endereco" className={inputClass} value={form.endereco || ''} onChange={onChange} />
                  </Field>
                  <Field label="Número">
                    <input type="text" name="address_number" className={inputClass} value={form.address_number || ''} onChange={onChange} />
                  </Field>
                  <Field label="Bairro">
                    <input type="text" name="province" className={inputClass} value={form.province || ''} onChange={onChange} />
                  </Field>
                  <Field label="Complemento">
                    <input type="text" name="complement" className={inputClass} value={form.complement || ''} onChange={onChange} />
                  </Field>
                </div>
              </section>
            )}

            {tab === 'cadastro' && cadastroSub === 'solucoes' && (
              <section className="space-y-4">
                <h3 className="text-sm font-semibold text-foreground">Soluções</h3>
                <div className="space-y-3 rounded-lg border border-border bg-muted/40 p-4">
                  {[
                    { name: 'enable_chat', title: 'Chat', hint: 'Multi-atendimento no painel do provedor' },
                    { name: 'enable_mobile_app', title: 'App Mobile', hint: 'Aplicativo do cliente' },
                    { name: 'enable_acs', title: 'ACS', hint: 'GenieACS com licença e bloqueio' },
                  ].map((item) => (
                    <label key={item.name} className="flex items-center gap-3 text-sm text-foreground">
                      <input type="checkbox" name={item.name} checked={!!form[item.name]} onChange={onChange} className="h-4 w-4 rounded border-border bg-background text-primary" />
                      <span className="min-w-[7.5rem] font-medium">{item.title}</span>
                      <span className="text-xs text-muted-foreground">{item.hint}</span>
                    </label>
                  ))}
                </div>
                {form.enable_chat && (
                  <div className="space-y-3 rounded-lg border border-border bg-muted/40 p-4">
                    <Field label="Modo de atendimento" required>
                      <select name="bot_mode" className={inputClass} value={form.bot_mode || 'ia'} onChange={onChange} required>
                        <option value="ia">Inteligência Artificial (IA)</option>
                        <option value="chatbot">Fluxo de Chatbot</option>
                      </select>
                    </Field>
                    <Field label="Modo do agente de IA" required hint="Use Suporte da Plataforma no painel que atende clientes e leads do NioHub.">
                      <select name="agent_mode" className={inputClass} value={form.agent_mode || 'isp'} onChange={onChange} required>
                        <option value="isp">Provedor de Internet (ISP)</option>
                        <option value="support">Suporte da Plataforma (NioHub)</option>
                      </select>
                    </Field>
                  </div>
                )}
              </section>
            )}

            {tab === 'cadastro' && cadastroSub === 'outros' && (
              <section className="space-y-4">
                <h3 className="text-sm font-semibold text-foreground">Outros</h3>
                <div className="space-y-3 rounded-lg border border-border bg-muted/40 p-4">
                  <Field label="Grupo">
                    <input type="text" name="group_name" className={inputClass} value={form.group_name || ''} onChange={onChange} />
                  </Field>
                  <Field label="Inscrição municipal">
                    <input type="text" name="municipal_inscription" className={inputClass} value={form.municipal_inscription || ''} onChange={onChange} />
                  </Field>
                  <Field label="Inscrição estadual">
                    <input type="text" name="state_inscription" className={inputClass} value={form.state_inscription || ''} onChange={onChange} />
                  </Field>
                  <Field label="E-mails adicionais" hint="Separados por vírgula">
                    <input type="text" name="additional_emails" className={inputClass} value={form.additional_emails || ''} onChange={onChange} />
                  </Field>
                  <Field label="Observações">
                    <textarea name="observations" rows={4} className={inputClass} value={form.observations || ''} onChange={onChange} />
                  </Field>
                </div>
              </section>
            )}

            {tab === 'plano' && <div className="rounded-lg border border-border bg-muted/40 p-4">{planoFields}</div>}

            {tab === 'atualizacao' && (
              <section className="space-y-4">
                <h3 className="text-sm font-semibold text-foreground">Canal de atualização</h3>
                <div className="space-y-3 rounded-lg border border-border bg-muted/40 p-4">
                  <Field label="Canal de release">
                    <select name="release_channel" className={inputClass} value={form.release_channel || 'stable'} onChange={onChange}>
                      <option value="beta">Beta (Atualização Automática)</option>
                      <option value="stable">Estável (Atualização Controlada)</option>
                      <option value="manual">Manual</option>
                    </select>
                  </Field>
                  <Field label="Versão atual">
                    <input
                      type="text"
                      className={`${inputClass} cursor-not-allowed text-muted-foreground`}
                      value={form.current_version && form.current_version !== '1.0.0' ? form.current_version : 'Aguardando relatório do painel'}
                      disabled
                    />
                  </Field>
                </div>
              </section>
            )}

            {tab === 'financeiro' && (
              <div className="divide-y divide-border">
                <section className="pb-5">
                  <div className="mb-3 flex items-start justify-between gap-3">
                    <div>
                      <h3 className="text-sm font-semibold text-foreground">Promessa de pagamento</h3>
                      <p className="mt-0.5 text-xs text-muted-foreground">
                        Libera o provedor suspenso até a data. Sem pagamento, o acesso bloqueia de novo.
                      </p>
                    </div>
                    {promiseActive ? (
                      <button type="button" onClick={onCancelPromise} disabled={savingPromise} className={cancelBtn}>
                        {savingPromise ? 'Cancelando…' : 'Cancelar'}
                      </button>
                    ) : null}
                  </div>
                  {promiseActive ? (
                    <dl className="grid max-w-xl grid-cols-[7.5rem_minmax(0,1fr)] gap-x-3 gap-y-1.5 text-sm">
                      <dt className="text-muted-foreground">Vigente até</dt>
                      <dd className="font-medium text-foreground">{formatBrDate(form.payment_promise_until)}</dd>
                      {form.payment_promise_note ? (
                        <>
                          <dt className="text-muted-foreground">Observação</dt>
                          <dd>{form.payment_promise_note}</dd>
                        </>
                      ) : null}
                      <dt className="text-muted-foreground">Registrada</dt>
                      <dd className="text-muted-foreground">
                        {formatBrDateTime(form.payment_promise_created_at)}
                        {form.payment_promise_created_by ? ` · ${form.payment_promise_created_by}` : ''}
                      </dd>
                    </dl>
                  ) : (
                    <div className="grid grid-cols-1 gap-3 sm:grid-cols-[10rem_minmax(0,1fr)_auto] sm:items-end">
                      <div>
                        <label className="mb-1 block text-xs text-muted-foreground">Liberar até</label>
                        <input type="date" min={todayIso()} className={inputClass} value={promiseUntil} onChange={(e) => setPromiseUntil(e.target.value)} />
                      </div>
                      <div>
                        <label className="mb-1 block text-xs text-muted-foreground">Observação</label>
                        <input type="text" maxLength={255} className={inputClass} placeholder="Ex.: combinado com o financeiro" value={promiseNote} onChange={(e) => setPromiseNote(e.target.value)} />
                      </div>
                      <button
                        type="button"
                        disabled={savingPromise || !promiseUntil}
                        onClick={() => onApplyPromise({ until: promiseUntil, note: promiseNote })}
                        className={`${saveBtn} !px-4 !py-2 !text-sm`}
                      >
                        {savingPromise ? 'Liberando…' : 'Liberar acesso'}
                      </button>
                    </div>
                  )}
                  {!isActive && !promiseActive ? (
                    <p className="mt-2 text-xs text-red-600 dark:text-red-400">Este provedor está suspenso. Informe a data para reativar até lá.</p>
                  ) : null}
                </section>

                <section className="space-y-2.5 py-5">
                  <label className="flex cursor-pointer items-center gap-2.5 text-sm text-foreground">
                    <input type="checkbox" name="notification_disabled" checked={!!form.notification_disabled} onChange={onChange} className="h-4 w-4 rounded border-border bg-background text-primary" />
                    <span>{inter ? 'Desativar notificações de cobrança' : 'Desativar notificações Asaas'}</span>
                    <span className="text-xs text-muted-foreground">não envia e-mail/SMS ao cliente</span>
                  </label>
                  <label className="flex cursor-pointer items-center gap-2.5 text-sm text-foreground">
                    <input type="checkbox" name="foreign_customer" checked={!!form.foreign_customer} onChange={onChange} className="h-4 w-4 rounded border-border bg-background text-primary" />
                    <span>Cliente estrangeiro</span>
                    <span className="text-xs text-muted-foreground">cadastro sem CPF/CNPJ brasileiro</span>
                  </label>
                </section>

                <section className="pt-5">
                  <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
                    <h3 className="text-sm font-semibold text-foreground">
                      Assinatura
                      <span className="ml-2 text-xs font-normal text-muted-foreground">
                        {inter ? 'Banco Inter' : 'Asaas'}
                        {inter ? '' : asaasSandbox ? ' · sandbox' : ' · produção'}
                      </span>
                    </h3>
                    <div className="flex flex-wrap items-center gap-1">
                      {form.asaas_subscription_id ? (
                        <>
                          <button type="button" onClick={() => handleClearAsaasSubscription(true)} disabled={loadingEdit} className={cancelBtn}>
                            {inter ? 'Cancelar no Inter' : 'Cancelar no Asaas'}
                          </button>
                          <button type="button" onClick={() => handleClearAsaasSubscription(false)} disabled={loadingEdit} className={dangerBtn}>
                            Desvincular
                          </button>
                        </>
                      ) : null}
                      <button type="button" onClick={handleVerifyAsaas} disabled={loadingEdit} className={updateBtn}>
                        {loadingEdit ? 'Atualizando…' : 'Atualizar'}
                      </button>
                    </div>
                  </div>

                  {form.asaas_subscription_id ? (
                    <>
                      {(() => {
                        const ui = subscriptionStatusUi(form.subscription_status);
                        return (
                          <div className="space-y-3">
                            <div className="flex flex-wrap items-baseline gap-x-5 gap-y-1 text-sm">
                              <span className={`font-medium ${ui.tone}`}>
                                {ui.label}
                                {ui.live ? ` · em dia no ${inter ? 'Inter' : 'Asaas'}` : ''}
                              </span>
                              <span>R$ {Number(form.subscription_value || 0).toFixed(2)}</span>
                              <span className="text-muted-foreground">{subscriptionCycleLabel(form.subscription_cycle)}</span>
                              <span className="text-muted-foreground">próx. {formatBrDate(form.subscription_next_due_date)}</span>
                              <span className="inline-flex min-w-0 items-center gap-1 font-mono text-xs text-muted-foreground">
                                <span className="truncate">{form.asaas_subscription_id}</span>
                                <button type="button" className="ficha-btn !p-1" title="Copiar ID" onClick={() => navigator.clipboard?.writeText(form.asaas_subscription_id)}>
                                  <Copy className="h-3.5 w-3.5" />
                                </button>
                              </span>
                              {!inter && !subscriptionEdit ? (
                                <button
                                  type="button"
                                  className={cardBtn}
                                  onClick={() => setSubscriptionEdit({
                                    value: form.subscription_value || '',
                                    cycle: form.subscription_cycle || 'MONTHLY',
                                    billingType: form.subscription_billing_type || 'BOLETO',
                                    nextDueDate: form.subscription_next_due_date || '',
                                    updatePendingPayments: false,
                                  })}
                                >
                                  Editar
                                </button>
                              ) : null}
                            </div>
                            {subscriptionEdit ? (
                              <div className="space-y-3 border-t border-border pt-3">
                                <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
                                  <div>
                                    <label className="mb-1 block text-xs text-muted-foreground">Valor</label>
                                    <input type="number" step="0.01" min="0.01" className={inputClass} value={subscriptionEdit.value} onChange={(e) => setSubscriptionEdit((s) => ({ ...s, value: e.target.value }))} />
                                  </div>
                                  <div>
                                    <label className="mb-1 block text-xs text-muted-foreground">Ciclo</label>
                                    <select className={inputClass} value={subscriptionEdit.cycle} onChange={(e) => setSubscriptionEdit((s) => ({ ...s, cycle: e.target.value }))}>
                                      <option value="MONTHLY">Mensal</option>
                                      <option value="BIMONTHLY">Bimestral</option>
                                      <option value="QUARTERLY">Trimestral</option>
                                      <option value="SEMIANNUALLY">Semestral</option>
                                      <option value="YEARLY">Anual</option>
                                    </select>
                                  </div>
                                  <div>
                                    <label className="mb-1 block text-xs text-muted-foreground">Pagamento</label>
                                    <select className={inputClass} value={subscriptionEdit.billingType} onChange={(e) => setSubscriptionEdit((s) => ({ ...s, billingType: e.target.value }))}>
                                      <option value="BOLETO">Boleto</option>
                                      <option value="PIX">PIX</option>
                                      <option value="CREDIT_CARD">Cartão de Crédito</option>
                                      <option value="UNDEFINED">Cliente escolhe</option>
                                    </select>
                                  </div>
                                  <div>
                                    <label className="mb-1 block text-xs text-muted-foreground">Próx. vencimento</label>
                                    <input type="date" min={todayIso()} className={inputClass} value={subscriptionEdit.nextDueDate} onChange={(e) => setSubscriptionEdit((s) => ({ ...s, nextDueDate: e.target.value }))} />
                                  </div>
                                </div>
                                <label className="flex items-center gap-2 text-xs text-foreground">
                                  <input type="checkbox" className="h-4 w-4 rounded" checked={subscriptionEdit.updatePendingPayments} onChange={(e) => setSubscriptionEdit((s) => ({ ...s, updatePendingPayments: e.target.checked }))} />
                                  Aplicar também às cobranças já geradas que estão pendentes
                                </label>
                                <div className="flex justify-end gap-1">
                                  <button type="button" onClick={() => setSubscriptionEdit(null)} disabled={savingSubscription} className={cancelBtn}>Cancelar</button>
                                  <button type="button" onClick={handleSaveSubscription} disabled={savingSubscription} className={saveBtn}>
                                    {savingSubscription ? 'Salvando…' : 'Salvar no Asaas'}
                                  </button>
                                </div>
                              </div>
                            ) : null}
                          </div>
                        );
                      })()}

                      <div className="mt-6">
                        <h4 className="mb-2 text-sm font-semibold text-foreground">
                          Cobranças
                          {subscriptionPayments.length > 0 ? (
                            <span className="ml-2 text-xs font-normal text-muted-foreground">{subscriptionPayments.length}</span>
                          ) : null}
                        </h4>
                        {loadingPayments ? (
                          <p className="py-4 text-xs text-muted-foreground">{inter ? 'Consultando cobranças Inter…' : 'Consultando Asaas…'}</p>
                        ) : subscriptionPayments.length > 0 ? (
                          <div className="max-h-96 overflow-auto">
                            <table className="w-full min-w-[36rem] text-left text-sm">
                              <thead>
                                <tr className="border-b border-border text-xs text-muted-foreground">
                                  <th className="py-2 pr-3 font-medium">Vencimento</th>
                                  <th className="py-2 pr-3 font-medium">Descrição</th>
                                  <th className="py-2 pr-3 font-medium">Valor</th>
                                  <th className="py-2 pr-3 font-medium">Tipo</th>
                                  <th className="py-2 pr-3 font-medium">Status</th>
                                  <th className="py-2 font-medium" />
                                </tr>
                              </thead>
                              <tbody>
                                {subscriptionPayments.map((payment) => {
                                  const ps = paymentStatusUi(payment.status);
                                  const canEdit = !inter && ASAAS_EDITABLE_PAYMENT.includes(payment.status);
                                  const editing = paymentEdit?.id === payment.id;
                                  return (
                                    <React.Fragment key={payment.id}>
                                      <tr className="border-b border-border/70">
                                        <td className="whitespace-nowrap py-2.5 pr-3">{formatBrDate(payment.dueDate)}</td>
                                        <td className="max-w-[16rem] truncate py-2.5 pr-3">{payment.description || payment.id}</td>
                                        <td className="whitespace-nowrap py-2.5 pr-3">R$ {payment.value}</td>
                                        <td className="py-2.5 pr-3 text-muted-foreground">{payment.billingType}</td>
                                        <td className={`whitespace-nowrap py-2.5 pr-3 font-medium ${ps.tone}`}>{ps.label}</td>
                                        <td className="py-2.5 text-right">
                                          <div className="inline-flex items-center gap-0.5">
                                            {canEdit && !editing ? (
                                              <button type="button" className="ficha-btn !p-1.5" title="Alterar valor ou vencimento" onClick={() => setPaymentEdit({ id: payment.id, value: payment.value ?? '', dueDate: payment.dueDate || '', billingType: payment.billingType || 'BOLETO', description: payment.description || '' })}>
                                                <Edit className="h-3.5 w-3.5" />
                                              </button>
                                            ) : null}
                                            {(payment.bankSlipUrl || payment.invoiceUrl) ? (
                                              <a href={payment.bankSlipUrl || payment.invoiceUrl} target="_blank" rel="noopener noreferrer" className="ficha-btn !p-1.5" title="Abrir fatura">
                                                <ExternalLink className="h-3.5 w-3.5" />
                                              </a>
                                            ) : null}
                                          </div>
                                        </td>
                                      </tr>
                                      {editing ? (
                                        <tr>
                                          <td colSpan={6} className="bg-muted/30 px-0 py-3">
                                            <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
                                              <div>
                                                <label className="mb-1 block text-xs text-muted-foreground">Valor</label>
                                                <input type="number" step="0.01" min="0.01" className={inputClass} value={paymentEdit.value} onChange={(e) => setPaymentEdit((p) => ({ ...p, value: e.target.value }))} />
                                              </div>
                                              <div>
                                                <label className="mb-1 block text-xs text-muted-foreground">Vencimento</label>
                                                <input type="date" min={todayIso()} className={inputClass} value={paymentEdit.dueDate} onChange={(e) => setPaymentEdit((p) => ({ ...p, dueDate: e.target.value }))} />
                                              </div>
                                              <div>
                                                <label className="mb-1 block text-xs text-muted-foreground">Pagamento</label>
                                                <select className={inputClass} value={paymentEdit.billingType} onChange={(e) => setPaymentEdit((p) => ({ ...p, billingType: e.target.value }))}>
                                                  <option value="BOLETO">Boleto</option>
                                                  <option value="PIX">PIX</option>
                                                  <option value="CREDIT_CARD">Cartão de Crédito</option>
                                                  <option value="UNDEFINED">Cliente escolhe</option>
                                                </select>
                                              </div>
                                            </div>
                                            <div className="mt-3 flex justify-end gap-1">
                                              <button type="button" onClick={() => setPaymentEdit(null)} disabled={savingPayment} className={cancelBtn}>Cancelar</button>
                                              <button type="button" onClick={handleSavePayment} disabled={savingPayment} className={saveBtn}>
                                                {savingPayment ? 'Salvando…' : 'Salvar no Asaas'}
                                              </button>
                                            </div>
                                          </td>
                                        </tr>
                                      ) : null}
                                    </React.Fragment>
                                  );
                                })}
                              </tbody>
                            </table>
                          </div>
                        ) : (
                          <p className="py-3 text-sm text-muted-foreground">Nenhuma cobrança nesta assinatura.</p>
                        )}
                      </div>
                    </>
                  ) : (
                    <div className="space-y-4">
                      <p className="text-sm text-muted-foreground">Nenhuma assinatura vinculada.</p>
                      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-5">
                        <div>
                          <label className="mb-1 block text-xs text-muted-foreground">Portador</label>
                          <select name="billing_provider" className={inputClass} value={form.billing_provider || 'asaas'} onChange={onChange}>
                            <option value="asaas">Asaas</option>
                            <option value="inter">Banco Inter</option>
                          </select>
                        </div>
                        <div>
                          <label className="mb-1 block text-xs text-muted-foreground">Valor</label>
                          <input type="number" name="subscription_value" className={inputClass} value={form.subscription_value} onChange={onChange} placeholder="0.00" />
                        </div>
                        <div>
                          <label className="mb-1 block text-xs text-muted-foreground">Ciclo</label>
                          <select name="subscription_cycle" className={inputClass} value={form.subscription_cycle} onChange={onChange}>
                            <option value="MONTHLY">Mensal</option>
                            <option value="QUARTERLY">Trimestral</option>
                            <option value="SEMIANNUALLY">Semestral</option>
                            <option value="YEARLY">Anual</option>
                          </select>
                        </div>
                        <div>
                          <label className="mb-1 block text-xs text-muted-foreground">1º vencimento</label>
                          <input type="date" name="subscription_next_due_date" className={inputClass} value={form.subscription_next_due_date} onChange={onChange} />
                        </div>
                        <div>
                          <label className="mb-1 block text-xs text-muted-foreground">Pagamento</label>
                          <select name="subscription_billing_type" className={inputClass} value={form.subscription_billing_type} onChange={onChange}>
                            <option value="BOLETO">Boleto</option>
                            <option value="PIX">PIX</option>
                            {!inter && <option value="CREDIT_CARD">Cartão de Crédito</option>}
                          </select>
                        </div>
                      </div>
                      {inter || form.asaas_customer_id ? (
                        <button type="button" onClick={handleCreateSubscription} disabled={loadingEdit} className={`${saveBtn} !px-4 !py-2 !text-sm`}>
                          {loadingEdit ? 'Processando…' : inter ? 'Criar assinatura no Inter' : 'Criar assinatura'}
                        </button>
                      ) : (
                        <button type="button" onClick={handleSyncAsaas} disabled={loadingEdit} className={`${updateBtn} !px-4 !py-2 !text-sm`}>
                          {loadingEdit ? 'Sincronizando…' : 'Sincronizar cliente com Asaas'}
                        </button>
                      )}
                    </div>
                  )}
                </section>
              </div>
            )}

            {errorMsg && (
              <p className="mt-4 text-sm text-red-600 dark:text-red-400">{errorMsg}</p>
            )}
          </div>

          <div className="flex shrink-0 items-center justify-end gap-3 border-t border-border bg-muted/40 px-5 py-3 sm:px-6">
            <button type="button" onClick={onClose} className={`${cancelBtn} !px-5 !py-2 !text-sm`}>
              Cancelar
            </button>
            <button type="submit" disabled={loadingEdit} className={`${saveBtn} !px-5 !py-2 !text-sm`}>
              {loadingEdit ? 'Salvando...' : 'Salvar alterações'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
