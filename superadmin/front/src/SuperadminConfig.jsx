import React, { useEffect, useState } from 'react';
import { Settings, Save, Globe, Shield, Building } from 'lucide-react';
import axios from 'axios';
import { useNavigate } from 'react-router-dom';

const BILLING_WEEKDAYS = [
  { value: '0', label: 'Domingo' },
  { value: '1', label: 'Segunda-feira' },
  { value: '2', label: 'Terça-feira' },
  { value: '3', label: 'Quarta-feira' },
  { value: '4', label: 'Quinta-feira' },
  { value: '5', label: 'Sexta-feira' },
  { value: '6', label: 'Sábado' },
];

function parseBillingRunDays(raw) {
  return new Set(
    String(raw || '0,1,2,3,4,5,6')
      .split(',')
      .map((s) => s.trim())
      .filter(Boolean)
  );
}

export default function SuperadminConfig() {
  const navigate = useNavigate();
  const [config, setConfig] = useState(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');
  const [metaConnecting] = useState(false);
  const [testLoading, setTestLoading] = useState(false);

  useEffect(() => {
    async function fetchConfig() {
      setLoading(true);
      setError('');
      try {
        const token = localStorage.getItem('token');
        console.log('Buscando configurações do sistema...');
        const res = await axios.get('/api/system-config/', {
          headers: { Authorization: `Token ${token}` }
        });
        console.log('Configurações recebidas:', res.data);
        setConfig(res.data);
      } catch (e) {
        console.error('Erro ao buscar configurações:', e);
        setError('Erro ao buscar configurações do sistema: ' + (e.response?.data?.detail || e.message));
      }
      setLoading(false);
    }
    fetchConfig();
  }, []);


  const handleChange = (e) => {
    const { name, value, type, checked } = e.target;
    console.log('Campo alterado:', name, 'Valor:', value);
    setConfig((prev) => ({
      ...prev,
      [name]: type === 'checkbox' ? checked : value
    }));
  };

  const toggleBillingRunDay = (dayValue) => {
    setConfig((prev) => {
      const selected = parseBillingRunDays(prev?.billing_run_days);
      if (selected.has(dayValue)) {
        selected.delete(dayValue);
      } else {
        selected.add(dayValue);
      }
      const ordered = BILLING_WEEKDAYS.map((d) => d.value).filter((v) => selected.has(v));
      return { ...prev, billing_run_days: ordered.join(',') };
    });
  };

  const billingRunDaysSet = parseBillingRunDays(config?.billing_run_days);

  const testBillingSend = async () => {
    if (!confirm('Deseja disparar um ciclo de teste de envio de cobranças agora? (Ignora o cache diário)')) return;
    setTestLoading(true);
    try {
      const token = localStorage.getItem('token');
      const resp = await axios.post('/api/system-config/billing-whatsapp/test/', {}, {
        headers: { Authorization: `Token ${token}` }
      });
      if (resp.data.success) {
        alert(`Sucesso! Enviados: ${resp.data.sent_ok} | Falhas: ${resp.data.sent_err} | Total: ${resp.data.total}`);
      } else {
        alert('Erro: ' + (resp.data.error || resp.data.reason));
      }
    } catch (err) {
      alert('Erro ao testar: ' + err.message);
    } finally {
      setTestLoading(false);
    }
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setSaving(true);
    setError('');
    setSuccess('');
    try {
      const token = localStorage.getItem('token');
      console.log('Enviando configurações:', config);
      const res = await axios.put(`/api/system-config/1/`, config, {
        headers: { Authorization: `Token ${token}` }
      });
      console.log('Resposta do servidor:', res.data);
      setSuccess('Configurações salvas com sucesso!');
      // Atualizar o estado com a resposta do servidor
      setConfig(res.data);
    } catch (e) {
      console.error('Erro ao salvar configurações:', e);
      setError('Erro ao salvar configurações: ' + (e.response?.data?.detail || e.message));
    }
    setSaving(false);
  };

  const connectBillingMeta = () => {
    navigate('/app/meta/finalizando-superadmin');
  };

  return (
    <div className="flex-1 min-h-0 p-6 bg-background overflow-y-auto w-full">
      <div className="w-full">
        {/* Header */}
        <div className="mb-8">
          <h1 className="text-3xl font-bold text-foreground mb-2 flex items-center gap-3">
            <Settings className="w-8 h-8 text-primary" />
            Configurações do Sistema
          </h1>
          <p className="text-muted-foreground">Gerencie as configurações globais do sistema de forma centralizada</p>
        </div>

        {loading ? (
          <div className="text-center text-muted-foreground py-20">
            <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-primary mx-auto mb-4"></div>
            <p>Carregando configurações...</p>
          </div>
        ) : error ? (
          <div className="bg-red-900/20 border border-red-500/30 rounded-lg p-6 text-center">
            <p className="text-red-400 font-medium">{error}</p>
          </div>
        ) : (
          <form onSubmit={handleSubmit} className="space-y-6 w-full">
            {success && (
              <div className="bg-green-900/20 border border-green-500/30 rounded-lg p-4 text-center">
                <p className="text-green-400 font-medium">{success}</p>
              </div>
            )}

            <div className="grid grid-cols-1 xl:grid-cols-2 gap-6">
            {/* Configurações Gerais */}
            <div className="bg-card rounded-xl shadow-lg border border-border overflow-hidden">
              <div className="bg-muted px-6 py-4 border-b border-border">
                <h3 className="text-lg font-semibold text-foreground flex items-center gap-2">
                  <Globe className="w-5 h-5 text-blue-400" />
                  Configurações Gerais
                </h3>
              </div>
              <div className="p-6 space-y-4">
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  <div>
                    <label className="block font-medium mb-2 text-foreground">Nome do Sistema</label>
                    <input
                      type="text"
                      name="site_name"
                      value={config?.site_name || ''}
                      onChange={handleChange}
                      className="w-full px-4 py-3 rounded-lg bg-background border border-border text-foreground focus:ring-2 focus:ring-primary/20 focus:border-primary transition-colors"
                      placeholder="Nome do sistema"
                    />
                  </div>
                  <div>
                    <label className="block font-medium mb-2 text-foreground">E-mail de Contato</label>
                    <input
                      type="email"
                      name="contact_email"
                      value={config?.contact_email || ''}
                      onChange={handleChange}
                      className="w-full px-4 py-3 rounded-lg bg-background border border-border text-foreground focus:ring-2 focus:ring-primary/20 focus:border-primary transition-colors"
                      placeholder="contato@empresa.com"
                    />
                  </div>
                  <div>
                    <label className="block font-medium mb-2 text-foreground">Idioma Padrão</label>
                    <select
                      name="default_language"
                      value={config?.default_language || 'pt-br'}
                      onChange={handleChange}
                      className="w-full px-4 py-3 rounded-lg bg-background border border-border text-foreground focus:ring-2 focus:ring-primary/20 focus:border-primary transition-colors"
                    >
                      <option value="pt-br">Português (Brasil)</option>
                      <option value="en">English</option>
                      <option value="es">Español</option>
                    </select>
                    <p className="text-xs text-muted-foreground mt-1">pt-br</p>
                  </div>
                  <div>
                    <label className="block font-medium mb-2 text-foreground">Fuso Horário</label>
                    <select
                      name="timezone"
                      value={config?.timezone || 'America/Sao_Paulo'}
                      onChange={handleChange}
                      className="w-full px-4 py-3 rounded-lg bg-background border border-border text-foreground focus:ring-2 focus:ring-primary/20 focus:border-primary transition-colors"
                    >
                      <option value="America/Sao_Paulo">São Paulo</option>
                      <option value="America/New_York">New York</option>
                      <option value="Europe/London">London</option>
                      <option value="Asia/Tokyo">Tokyo</option>
                    </select>
                    <p className="text-xs text-muted-foreground mt-1">America/Sao_Paulo</p>
                  </div>
                </div>
              </div>
            </div>

            {/* Segurança e Limites */}
            <div className="bg-card rounded-xl shadow-lg border border-border overflow-hidden">
              <div className="bg-gradient-to-r from-orange-900/20 to-red-900/20 px-6 py-4 border-b border-border">
                <h3 className="text-lg font-semibold text-foreground flex items-center gap-2">
                  <Shield className="w-5 h-5 text-orange-400" />
                  Segurança e Limites
                </h3>
              </div>
              <div className="p-6 space-y-4">
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  <div className="flex items-center space-x-3">
                    <input
                      type="checkbox"
                      name="allow_public_signup"
                      id="allow_public_signup"
                      checked={!!config?.allow_public_signup}
                      onChange={handleChange}
                      className="w-4 h-4 text-primary bg-background border-border rounded focus:ring-primary focus:ring-2"
                    />
                    <label htmlFor="allow_public_signup" className="font-medium text-foreground">
                      Permitir Cadastro Público
                    </label>
                  </div>
                  <div>
                    <label className="block font-medium mb-2 text-foreground">Limite de Usuários por Empresa</label>
                    <input
                      type="number"
                      name="max_users_per_company"
                      value={config?.max_users_per_company || 10}
                      onChange={handleChange}
                      className="w-full px-4 py-3 rounded-lg bg-background border border-border text-foreground focus:ring-2 focus:ring-primary/20 focus:border-primary transition-colors"
                      min="1"
                      max="1000"
                    />
                  </div>
                </div>
              </div>
            </div>
            </div>

            {/* Automação de Cobrança (Canal exclusivo do Superadmin) */}
            <div className="bg-card rounded-xl shadow-lg border border-border overflow-hidden w-full">
              <div className="bg-gradient-to-r from-emerald-900/20 to-teal-900/20 px-6 py-4 border-b border-border">
                <h3 className="text-lg font-semibold text-foreground flex items-center gap-2">
                  <Building className="w-5 h-5 text-emerald-400" />
                  Canal de Cobranca Exclusivo do Superadmin
                </h3>
              </div>
              <div className="p-6 space-y-4">
                <div className="flex items-center space-x-3">
                  <input
                    type="checkbox"
                    name="billing_channel_enabled"
                    id="billing_channel_enabled"
                    checked={!!config?.billing_channel_enabled}
                    onChange={handleChange}
                    className="w-4 h-4 text-primary bg-background border-border rounded focus:ring-primary focus:ring-2"
                  />
                  <label htmlFor="billing_channel_enabled" className="font-medium text-foreground">
                    Ativar automação de cobrança
                  </label>
                </div>

                <p className="text-sm text-muted-foreground">
                  A conexão com a Meta preenche automaticamente o token, WABA ID e phone number ID do canal de cobrança.
                </p>
                <p className="text-xs text-muted-foreground rounded-md border border-border bg-muted/30 px-3 py-2">
                  Com o servidor ASGI (Daphne), a cobrança e o fechamento de conversas rodam em background no mesmo
                  processo. Opcional: <code className="text-xs">RUN_HEARTBEAT=true</code> + worker Dramatiq (evita duplicar
                  se quiser só Dramatiq). Desative o agendador embutido com{' '}
                  <code className="text-xs">DISABLE_ASGI_PERIODIC_TASKS=1</code>. Teste manual:{' '}
                  <code className="text-xs">python manage.py send_billing_reminders</code>.
                </p>

                <div className="bg-background border border-border rounded-lg p-3">
                  <div className="flex items-center justify-between mb-2">
                    <span className="text-sm font-semibold text-foreground">Status do canal</span>
                    <span className={`text-xs font-semibold px-2 py-1 rounded-full ${config?.billing_whatsapp_waba_id && config?.billing_whatsapp_phone_number_id && config?.billing_whatsapp_token ? 'bg-green-900/30 text-green-400 border border-green-500/30' : 'bg-red-900/30 text-red-400 border border-red-500/30'}`}>
                      {config?.billing_whatsapp_waba_id && config?.billing_whatsapp_phone_number_id && config?.billing_whatsapp_token ? 'Conectado' : 'Não conectado'}
                    </span>
                  </div>
                  <div className="grid grid-cols-1 md:grid-cols-3 gap-2 text-xs">
                    <div className="text-muted-foreground">
                      <span className="block font-medium text-foreground">Phone Number ID</span>
                      <span>{config?.billing_whatsapp_phone_number_id || '-'}</span>
                    </div>
                    <div className="text-muted-foreground">
                      <span className="block font-medium text-foreground">WABA ID</span>
                      <span>{config?.billing_whatsapp_waba_id || '-'}</span>
                    </div>
                    <div className="text-muted-foreground">
                      <span className="block font-medium text-foreground">Token</span>
                      <span>{config?.billing_whatsapp_token ? `${String(config.billing_whatsapp_token).slice(0, 6)}...${String(config.billing_whatsapp_token).slice(-4)}` : '-'}</span>
                    </div>
                  </div>
                </div>

                <div className="flex flex-wrap items-center gap-3">
                  <button
                    type="button"
                    onClick={connectBillingMeta}
                    className="bg-blue-600 hover:bg-blue-500 text-white px-4 py-2 rounded-lg font-semibold transition-colors"
                    disabled={metaConnecting}
                  >
                    {metaConnecting ? 'Conectando com Meta...' : 'Conectar canal via Meta Coexistence'}
                  </button>
                  <button
                    type="button"
                    onClick={testBillingSend}
                    className="bg-emerald-700 hover:bg-emerald-600 text-white px-4 py-2 rounded-lg font-semibold transition-colors flex items-center gap-2"
                    disabled={testLoading}
                  >
                    {testLoading ? 'Enviando...' : 'Testar Envio de Cobranças'}
                  </button>
                </div>

                <div className="grid grid-cols-1 lg:grid-cols-2 xl:grid-cols-4 gap-4">
                  <div className="lg:col-span-2">
                    <label className="block font-medium mb-2 text-foreground">
                      Em quais situações enviar a cobrança
                    </label>
                    <input
                      type="text"
                      name="billing_reminder_due_offsets"
                      value={config?.billing_reminder_due_offsets ?? ''}
                      onChange={handleChange}
                      placeholder="-1,0,2"
                      className="w-full px-4 py-3 rounded-lg bg-background border border-border text-foreground focus:ring-2 focus:ring-primary/20 focus:border-primary transition-colors"
                    />
                    <p className="text-xs text-muted-foreground mt-1 leading-relaxed">
                      Escreva números separados por vírgula. Para faturas <strong className="text-foreground">ainda não
                      vencidas</strong>, use zero ou números negativos: <strong className="text-foreground">-1</strong>{' '}
                      manda um dia antes do vencimento, <strong className="text-foreground">0</strong> manda no próprio
                      dia do vencimento (e também vale para “vencida hoje” quando o Asaas já marcar como vencida). Para
                      faturas <strong className="text-foreground">já vencidas</strong>, use números positivos:{' '}
                      <strong className="text-foreground">2</strong> manda quando fizer dois dias que a fatura passou do
                      vencimento. Se deixar em branco, vale a opção “dias antes (modo antigo)” logo abaixo.
                    </p>
                  </div>
                  <div>
                    <label className="block font-medium mb-2 text-foreground">
                      Tolerância após o horário (minutos)
                    </label>
                    <input
                      type="number"
                      min={0}
                      max={45}
                      name="billing_run_window_minutes"
                      value={config?.billing_run_window_minutes ?? 0}
                      onChange={handleChange}
                      className="w-full px-4 py-3 rounded-lg bg-background border border-border text-foreground focus:ring-2 focus:ring-primary/20 focus:border-primary transition-colors"
                    />
                    <p className="text-xs text-muted-foreground mt-1 leading-relaxed">
                      Use <strong className="text-foreground">0</strong> para a rotina rodar só no minuto que você
                      escolheu (ex.: 08:30 da manhã). Se colocar por exemplo <strong className="text-foreground">5</strong>, o sistema ainda pode
                      disparar até cinco minutos depois, caso o servidor esteja um pouco atrasado.
                    </p>
                  </div>
                  <div>
                    <label className="block font-medium mb-2 text-foreground">
                      Horário em que a rotina pode rodar
                    </label>
                    <input
                      type="time"
                      name="billing_run_time"
                      value={config?.billing_run_time || '09:00'}
                      onChange={handleChange}
                      className="w-full px-4 py-3 rounded-lg bg-background border border-border text-foreground focus:ring-2 focus:ring-primary/20 focus:border-primary transition-colors"
                    />
                    <p className="text-xs text-muted-foreground mt-1">
                      Com tolerância zero, o envio ocorre nesse minuto do relógio (o servidor checa cerca de uma vez por
                      minuto).
                    </p>
                  </div>
                </div>

                <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
                  <div>
                    <label className="block font-medium mb-2 text-foreground">
                      Dias antes do vencimento (modo antigo)
                    </label>
                    <input
                      type="number"
                      min="0"
                      max="30"
                      name="billing_days_before_due"
                      value={config?.billing_days_before_due ?? 3}
                      onChange={handleChange}
                      className="w-full px-4 py-3 rounded-lg bg-background border border-border text-foreground focus:ring-2 focus:ring-primary/20 focus:border-primary transition-colors"
                    />
                    <p className="text-xs text-muted-foreground mt-1">
                      Só é usado se o campo “Em quais situações enviar” estiver vazio.
                    </p>
                  </div>
                  <div>
                    <label className="block font-medium mb-2 text-foreground">
                      Intervalo entre envios (segundos)
                    </label>
                    <input
                      type="number"
                      min={0}
                      max={300}
                      name="billing_send_interval_seconds"
                      value={config?.billing_send_interval_seconds ?? 0}
                      onChange={handleChange}
                      className="w-full px-4 py-3 rounded-lg bg-background border border-border text-foreground focus:ring-2 focus:ring-primary/20 focus:border-primary transition-colors"
                    />
                    <p className="text-xs text-muted-foreground mt-1 leading-relaxed">
                      Aguarda esse tempo entre cada cliente na mesma rodada (ex.: <strong className="text-foreground">5</strong>{' '}
                      = 5 segundos entre um WhatsApp e o próximo). Use <strong className="text-foreground">0</strong> para
                      enviar em sequência sem pausa.
                    </p>
                  </div>
                </div>

                <div className="rounded-lg border border-border overflow-hidden bg-muted/10">
                  <div className="px-4 py-2.5 bg-muted/30 border-b border-border">
                    <span className="text-sm font-semibold text-foreground">Dias da semana</span>
                  </div>
                  <div className="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-7 divide-y sm:divide-y-0 sm:divide-x divide-border">
                    {BILLING_WEEKDAYS.map(({ value, label }) => (
                      <label
                        key={value}
                        htmlFor={`billing_run_day_${value}`}
                        className="flex items-center gap-3 px-4 py-3 cursor-pointer hover:bg-muted/20 transition-colors"
                      >
                        <input
                          type="checkbox"
                          id={`billing_run_day_${value}`}
                          checked={billingRunDaysSet.has(value)}
                          onChange={() => toggleBillingRunDay(value)}
                          className="w-4 h-4 shrink-0 text-primary bg-background border-border rounded focus:ring-primary focus:ring-2"
                        />
                        <span className="text-sm text-foreground">{label}</span>
                      </label>
                    ))}
                  </div>
                  <p className="px-4 py-2 text-xs text-muted-foreground border-t border-border">
                    A rotina de cobrança só roda nos dias marcados, no horário configurado acima.
                  </p>
                </div>

                <div className="grid grid-cols-1 xl:grid-cols-2 gap-4">
                <div className="rounded-lg border border-amber-500/30 bg-amber-950/10 dark:bg-amber-950/20 p-4 space-y-4">
                  <h4 className="text-base font-semibold text-foreground">
                    Bloqueio de acesso do provedor (fatura Asaas)
                  </h4>
                  <p className="text-xs text-muted-foreground leading-relaxed">
                    Quando ligado, o sistema consulta o Asaas e pode <strong className="text-foreground">suspender o
                    provedor</strong> (ele deixa de acessar o painel) se a cobrança da <strong className="text-foreground">assinatura</strong> estiver
                    atrasada conforme o número de dias abaixo. Isso roda em segundo plano cerca de <strong className="text-foreground">a cada 10 minutos</strong> e
                    também quando você usa &quot;Verificar Asaas&quot; no cadastro do provedor.
                  </p>
                  <div className="flex items-center space-x-3">
                    <input
                      type="checkbox"
                      name="billing_provedor_auto_block_enabled"
                      id="billing_provedor_auto_block_enabled"
                      checked={!!config?.billing_provedor_auto_block_enabled}
                      onChange={handleChange}
                      className="w-4 h-4 text-primary bg-background border-border rounded focus:ring-primary focus:ring-2"
                    />
                    <label htmlFor="billing_provedor_auto_block_enabled" className="font-medium text-foreground">
                      Bloquear provedor automaticamente por fatura vencida no Asaas
                    </label>
                  </div>
                  <div>
                    <label className="block text-sm font-medium mb-1 text-foreground">
                      Quantos dias após o vencimento bloquear
                    </label>
                    <input
                      type="number"
                      min={0}
                      max={365}
                      name="billing_provedor_block_min_days_late"
                      value={config?.billing_provedor_block_min_days_late ?? 4}
                      onChange={handleChange}
                      className="w-full max-w-xs px-4 py-3 rounded-lg bg-background border border-border text-foreground focus:ring-2 focus:ring-primary/20 focus:border-primary transition-colors"
                    />
                    <p className="text-xs text-muted-foreground mt-1 leading-relaxed">
                      Use <strong className="text-foreground">1</strong> para bloquear a partir do <strong className="text-foreground">primeiro dia</strong> após a data de vencimento. Use{' '}
                      <strong className="text-foreground">0</strong> para bloquear com qualquer fatura já constando como
                      vencida no Asaas. O valor <strong className="text-foreground">4</strong> mantém o comportamento antigo do sistema (antes só bloqueava com mais de três dias de atraso).
                    </p>
                  </div>
                </div>

                <div className="rounded-lg border border-border p-4 space-y-3 bg-muted/20">
                  <div className="flex items-center space-x-3">
                    <input
                      type="checkbox"
                      name="billing_whatsapp_use_template"
                      id="billing_whatsapp_use_template"
                      checked={!!config?.billing_whatsapp_use_template}
                      onChange={handleChange}
                      className="w-4 h-4 text-primary bg-background border-border rounded focus:ring-primary focus:ring-2"
                    />
                    <label htmlFor="billing_whatsapp_use_template" className="font-medium text-foreground">
                      Enviar cobrança com template Meta (Detalhes do pedido)
                    </label>
                  </div>
                  <p className="text-xs text-muted-foreground leading-relaxed">
                    Quando marcado, envia pelo template oficial do WhatsApp (Detalhes do pedido), com PDF da fatura
                    e botão PIX. Informe abaixo os nomes dos templates aprovados na Meta para fatura a vencer e vencida.
                  </p>
                  <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
                    <div>
                      <label className="block text-sm font-medium mb-1 text-foreground">Template: A Vencer</label>
                      <input
                        type="text"
                        name="billing_whatsapp_template_name"
                        value={config?.billing_whatsapp_template_name ?? 'prox_do_vencimento'}
                        onChange={handleChange}
                        className="w-full px-4 py-2 rounded-lg bg-background border border-border text-foreground"
                        placeholder="Ex: prox_do_vencimento"
                      />
                    </div>
                    <div>
                      <label className="block text-sm font-medium mb-1 text-foreground">Template: Vencida</label>
                      <input
                        type="text"
                        name="billing_whatsapp_template_name_vencida"
                        value={config?.billing_whatsapp_template_name_vencida ?? (config?.billing_whatsapp_template_name || 'fatura_atrasada')}
                        onChange={handleChange}
                        className="w-full px-4 py-2 rounded-lg bg-background border border-border text-foreground"
                        placeholder="Ex: fatura_atrasada"
                      />
                    </div>
                    <div>
                      <label className="block text-sm font-medium mb-1 text-foreground">Idioma</label>
                      <input
                        type="text"
                        name="billing_whatsapp_template_language"
                        value={config?.billing_whatsapp_template_language ?? 'pt_BR'}
                        onChange={handleChange}
                        className="w-full px-4 py-2 rounded-lg bg-background border border-border text-foreground"
                      />
                    </div>
                  </div>
                </div>
                </div>
              </div>
            </div>

            {/* Botão Salvar */}
            <div className="flex justify-end pt-6 border-t border-border mt-6">
              <button
                type="submit"
                className="bg-emerald-600 hover:bg-emerald-500 text-white px-8 py-3 rounded-lg font-bold flex items-center gap-2 transition-all disabled:opacity-50 disabled:cursor-not-allowed shadow-lg shadow-emerald-500/20"
                disabled={saving}
              >
                <Save className="w-5 h-5" />
                {saving ? 'Salvando...' : 'Salvar Configurações'}
              </button>
            </div>
          </form>
        )}
      </div>
    </div>
  );
} 