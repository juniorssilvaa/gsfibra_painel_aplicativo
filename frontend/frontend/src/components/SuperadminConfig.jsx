import React, { useEffect, useState } from 'react';
import { Settings, Save, Eye, EyeOff, Globe, Shield, Zap, Building, Mic } from 'lucide-react';
import axios from 'axios';
import { useNavigate } from 'react-router-dom';

export default function SuperadminConfig() {
  const navigate = useNavigate();
  const [config, setConfig] = useState(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');
  const [showGoogleAIKey, setShowGoogleAIKey] = useState(false);
  const [showOpenAITranscriptionKey, setShowOpenAITranscriptionKey] = useState(false);
  const [showAsaasKey, setShowAsaasKey] = useState(false);
  const [showAsaasWebhookKey, setShowAsaasWebhookKey] = useState(false);
  const [metaConnecting] = useState(false);
  const [templatesLoading, setTemplatesLoading] = useState(false);
  const [billingTemplates, setBillingTemplates] = useState([]);
  const [newTemplate, setNewTemplate] = useState({
    name: '',
    category: 'UTILITY',
    language: 'pt_BR',
    header_text: '',
    body_text: '',
    footer_text: '',
  });
  const [variableSamples, setVariableSamples] = useState({});

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

  const fetchBillingTemplates = async () => {
    setTemplatesLoading(true);
    setError('');
    try {
      const token = localStorage.getItem('token') || localStorage.getItem('auth_token');
      const res = await axios.get('/api/system-config/billing-whatsapp/templates/', {
        headers: { Authorization: `Token ${token}` }
      });
      setBillingTemplates(res.data?.templates || []);
    } catch (e) {
      setError(e.response?.data?.error || e.message || 'Erro ao listar templates.');
    } finally {
      setTemplatesLoading(false);
    }
  };

  const createBillingTemplate = async () => {
    setError('');
    setSuccess('');
    if (!newTemplate.name || !newTemplate.body_text) {
      setError('Preencha nome e corpo do template.');
      return;
    }
    try {
      const extractVariables = (text) => {
        if (!text) return [];
        const matches = [...text.matchAll(/\{\{(\d+)\}\}/g)];
        return [...new Set(matches.map((m) => Number(m[1])))]
          .filter((n) => Number.isInteger(n) && n > 0)
          .sort((a, b) => a - b);
      };

      const toNamedFormat = (text, vars) => {
        let out = text || '';
        vars.forEach((num) => {
          const rgx = new RegExp(`\\{\\{${num}\\}\\}`, 'g');
          out = out.replace(rgx, `{{var_${num}}}`);
        });
        return out;
      };

      const bodyVars = extractVariables(newTemplate.body_text);
      const namedExamples = bodyVars.map((num) => ({
        param_name: `var_${num}`,
        example: variableSamples[num]?.example || `exemplo_${num}`,
      }));

      const components = [];
      if (newTemplate.header_text?.trim()) {
        components.push({
          type: 'HEADER',
          format: 'TEXT',
          text: newTemplate.header_text.trim(),
        });
      }

      const bodyComponent = {
        type: 'BODY',
        text: toNamedFormat(newTemplate.body_text, bodyVars),
      };
      if (namedExamples.length > 0) {
        bodyComponent.example = { body_text_named_params: namedExamples };
      }
      components.push(bodyComponent);

      if (newTemplate.footer_text?.trim()) {
        components.push({
          type: 'FOOTER',
          text: newTemplate.footer_text.trim(),
        });
      }

      const token = localStorage.getItem('token') || localStorage.getItem('auth_token');
      await axios.post('/api/system-config/billing-whatsapp/templates/', {
        name: newTemplate.name,
        category: newTemplate.category,
        language: newTemplate.language,
        body_text: newTemplate.body_text,
        parameter_format: 'named',
        components,
      }, {
        headers: { Authorization: `Token ${token}` }
      });
      setSuccess('Template criado e enviado para aprovação da Meta.');
      setNewTemplate((prev) => ({ ...prev, name: '', header_text: '', body_text: '', footer_text: '' }));
      setVariableSamples({});
      fetchBillingTemplates();
    } catch (e) {
      setError(e.response?.data?.error || e.message || 'Erro ao criar template.');
    }
  };

  const deleteBillingTemplate = async (templateId) => {
    if (!templateId) return;
    try {
      const token = localStorage.getItem('token') || localStorage.getItem('auth_token');
      await axios.delete(`/api/system-config/billing-whatsapp/templates/${encodeURIComponent(templateId)}/`, {
        headers: { Authorization: `Token ${token}` }
      });
      setSuccess('Template removido com sucesso.');
      fetchBillingTemplates();
    } catch (e) {
      setError(e.response?.data?.error || e.message || 'Erro ao remover template.');
    }
  };

  return (
    <div className="flex-1 min-h-0 p-6 bg-background overflow-y-auto">
      <div className="max-w-4xl mx-auto">
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
          <form onSubmit={handleSubmit} className="space-y-6">
            {success && (
              <div className="bg-green-900/20 border border-green-500/30 rounded-lg p-4 text-center">
                <p className="text-green-400 font-medium">{success}</p>
              </div>
            )}

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

            {/* Configurações do Google AI */}
            <div className="bg-card rounded-xl shadow-lg border border-border overflow-hidden">
              <div className="bg-muted px-6 py-4 border-b border-border">
                <h3 className="text-lg font-semibold text-foreground flex items-center gap-2">
                  <Zap className="w-5 h-5 text-green-400" />
                  Configurações do Google AI
                </h3>
              </div>
              <div className="p-6 space-y-4">
                <div>
                  <label className="block font-medium mb-2 text-foreground">Chave da API Google AI</label>
                  <div className="relative">
                    <input
                      type={showGoogleAIKey ? "text" : "password"}
                      name="google_api_key"
                      value={config?.google_api_key || ''}
                      onChange={handleChange}
                      className="w-full px-4 py-3 pr-12 rounded-lg bg-background border border-border text-foreground focus:ring-2 focus:ring-primary/20 focus:border-primary transition-colors"
                      placeholder="AIza..."
                    />
                    <button
                      type="button"
                      onClick={() => setShowGoogleAIKey(!showGoogleAIKey)}
                      className="absolute right-3 top-1/2 transform -translate-y-1/2 text-muted-foreground hover:text-foreground transition-colors"
                    >
                      {showGoogleAIKey ? <EyeOff className="w-5 h-5" /> : <Eye className="w-5 h-5" />}
                    </button>
                  </div>
                  <p className="text-sm text-muted-foreground mt-2">
                    Chave da API do Google AI para geração de respostas automáticas.
                    Se não fornecida, será usada a variável de ambiente GOOGLE_API_KEY.
                  </p>
                </div>
              </div>
            </div>

            {/* Configurações de Transcrição de Áudio */}
            <div className="bg-card rounded-xl shadow-lg border border-border overflow-hidden">
              <div className="bg-gradient-to-r from-purple-900/20 to-pink-900/20 px-6 py-4 border-b border-border">
                <h3 className="text-lg font-semibold text-foreground flex items-center gap-2">
                  <Mic className="w-5 h-5 text-purple-400" />
                  Configurações de Transcrição de Áudio
                </h3>
              </div>
              <div className="p-6 space-y-4">
                <div>
                  <label className="block font-medium mb-2 text-foreground">
                    Chave da API OpenAI (somente para transcrição de áudio)
                  </label>
                  <div className="relative">
                    <input
                      type={showOpenAITranscriptionKey ? "text" : "password"}
                      name="openai_transcription_api_key"
                      value={config?.openai_transcription_api_key || ''}
                      onChange={handleChange}
                      className="w-full px-4 py-3 pr-12 rounded-lg bg-background border border-border text-foreground focus:ring-2 focus:ring-primary/20 focus:border-primary transition-colors"
                      placeholder="sk-..."
                    />
                    <button
                      type="button"
                      onClick={() => setShowOpenAITranscriptionKey(!showOpenAITranscriptionKey)}
                      className="absolute right-3 top-1/2 transform -translate-y-1/2 text-muted-foreground hover:text-foreground transition-colors"
                    >
                      {showOpenAITranscriptionKey ? <EyeOff className="w-5 h-5" /> : <Eye className="w-5 h-5" />}
                    </button>
                  </div>
                  <p className="text-sm text-muted-foreground mt-2">
                    Chave da API OpenAI exclusivamente para converter mensagens de áudio em texto (speech-to-text).
                    Esta chave <strong className="text-foreground">NÃO será usada</strong> para geração de respostas ao cliente.
                    As respostas continuam sendo geradas pelo Google Gemini em 100% dos casos.
                  </p>
                </div>
              </div>
            </div>

            {/* Configurações do Asaas */}
            <div className="bg-card rounded-xl shadow-lg border border-border overflow-hidden">
              <div className="bg-gradient-to-r from-blue-900/20 to-indigo-900/20 px-6 py-4 border-b border-border">
                <h3 className="text-lg font-semibold text-foreground flex items-center gap-2">
                  <Building className="w-5 h-5 text-blue-400" />
                  Configurações do Asaas
                </h3>
              </div>
              <div className="p-6 space-y-4">
                <div>
                  <label className="block font-medium mb-2 text-foreground">Asaas Access Token</label>
                  <div className="relative">
                    <input
                      type={showAsaasKey ? "text" : "password"}
                      name="asaas_access_token"
                      value={config?.asaas_access_token || ''}
                      onChange={handleChange}
                      className="w-full px-4 py-3 pr-12 rounded-lg bg-background border border-border text-foreground focus:ring-2 focus:ring-primary/20 focus:border-primary transition-colors"
                      placeholder="$..."
                    />
                    <button
                      type="button"
                      onClick={() => setShowAsaasKey(!showAsaasKey)}
                      className="absolute right-3 top-1/2 transform -translate-y-1/2 text-muted-foreground hover:text-foreground transition-colors"
                    >
                      {showAsaasKey ? <EyeOff className="w-5 h-5" /> : <Eye className="w-5 h-5" />}
                    </button>
                  </div>
                  <p className="text-sm text-muted-foreground mt-2">
                    Token de acesso da API do Asaas para faturamento global e criação de clientes.
                  </p>
                </div>

                <div>
                  <label className="block font-medium mb-2 text-foreground">Token de autenticação do Webhook Asaas</label>
                  <div className="relative">
                    <input
                      type={showAsaasWebhookKey ? "text" : "password"}
                      name="asaas_webhook_auth_token"
                      value={config?.asaas_webhook_auth_token || ''}
                      onChange={handleChange}
                      className="w-full px-4 py-3 pr-12 rounded-lg bg-background border border-border text-foreground focus:ring-2 focus:ring-primary/20 focus:border-primary transition-colors"
                      placeholder="whsec_..."
                    />
                    <button
                      type="button"
                      onClick={() => setShowAsaasWebhookKey(!showAsaasWebhookKey)}
                      className="absolute right-3 top-1/2 transform -translate-y-1/2 text-muted-foreground hover:text-foreground transition-colors"
                    >
                      {showAsaasWebhookKey ? <EyeOff className="w-5 h-5" /> : <Eye className="w-5 h-5" />}
                    </button>
                  </div>
                  <p className="text-sm text-muted-foreground mt-2">
                    Token configurado no painel do Asaas para autenticar chamadas no endpoint de webhook.
                  </p>
                </div>

                <div className="flex items-center space-x-3 pt-2">
                  <input
                    type="checkbox"
                    name="asaas_sandbox"
                    id="asaas_sandbox"
                    checked={!!config?.asaas_sandbox}
                    onChange={handleChange}
                    className="w-4 h-4 text-primary bg-background border-border rounded focus:ring-primary focus:ring-2"
                  />
                  <label htmlFor="asaas_sandbox" className="font-medium text-foreground">
                    Modo Sandbox (Ambiente de Teste)
                  </label>
                </div>

              </div>
            </div>

            {/* Automação de Cobrança (Canal exclusivo do Superadmin) */}
            <div className="bg-card rounded-xl shadow-lg border border-border overflow-hidden">
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
                    onClick={fetchBillingTemplates}
                    className="bg-slate-700 hover:bg-slate-600 text-white px-4 py-2 rounded-lg font-semibold transition-colors"
                    disabled={templatesLoading}
                  >
                    {templatesLoading ? 'Carregando templates...' : 'Listar templates da Meta'}
                  </button>
                </div>

                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  <div>
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
                </div>

                <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
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
                      minuto, então pode ser no começo ou no fim dos 60 segundos, por exemplo 08:30).
                    </p>
                  </div>
                  <div>
                    <label className="block font-medium mb-2 text-foreground">
                      Dias da semana em que pode rodar (0 = domingo até 6 = sábado)
                    </label>
                    <input
                      type="text"
                      name="billing_run_days"
                      value={config?.billing_run_days || '0,1,2,3,4,5,6'}
                      onChange={handleChange}
                      className="w-full px-4 py-3 rounded-lg bg-background border border-border text-foreground focus:ring-2 focus:ring-primary/20 focus:border-primary transition-colors"
                      placeholder="0,1,2,3,4,5,6"
                    />
                  </div>
                </div>

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
                    Quando marcado, tenta enviar pelo modelo oficial do WhatsApp (nome padrão cobranca_order), com PDF de
                    boleto ou fatura quando existir. Se não houver PDF aceito, tenta a tela de pagamento com PIX. Se
                    ainda assim não der, usa os textos que você escreveu mais abaixo.
                  </p>
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                    <div>
                      <label className="block text-sm font-medium mb-1 text-foreground">Nome do template</label>
                      <input
                        type="text"
                        name="billing_whatsapp_template_name"
                        value={config?.billing_whatsapp_template_name ?? 'cobranca_order'}
                        onChange={handleChange}
                        className="w-full px-4 py-2 rounded-lg bg-background border border-border text-foreground"
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

                <div>
                  <label className="block font-medium mb-2 text-foreground">Mensagem para fatura a vencer</label>
                  <textarea
                    name="billing_template_due_soon"
                    value={config?.billing_template_due_soon || ''}
                    onChange={handleChange}
                    rows={3}
                    className="w-full px-4 py-3 rounded-lg bg-background border border-border text-foreground focus:ring-2 focus:ring-primary/20 focus:border-primary transition-colors"
                  />
                </div>

                <div>
                  <label className="block font-medium mb-2 text-foreground">Mensagem para fatura vencida</label>
                  <textarea
                    name="billing_template_overdue"
                    value={config?.billing_template_overdue || ''}
                    onChange={handleChange}
                    rows={3}
                    className="w-full px-4 py-3 rounded-lg bg-background border border-border text-foreground focus:ring-2 focus:ring-primary/20 focus:border-primary transition-colors"
                  />
                </div>

                <p className="text-sm text-muted-foreground">
                  Variaveis suportadas: <code>{'{{nome}}'}</code>, <code>{'{{provedor}}'}</code>,{' '}
                  <code>{'{{marca}}'}</code> (igual ao provedor), <code>{'{{sistema}}'}</code> (nome do site, ex. NIO
                  HUB), <code>{'{{valor}}'}</code>, <code>{'{{vencimento}}'}</code> (ISO),{' '}
                  <code>{'{{vencimento_br}}'}</code> (DD/MM/AAAA), <code>{'{{fatura_id}}'}</code>
                </p>

                <div className="pt-4 border-t border-border space-y-3">
                  <h4 className="text-base font-semibold text-foreground">Templates oficiais da Meta (canal de cobrança)</h4>
                  <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                    <input
                      type="text"
                      placeholder="Nome do template (ex: cobranca_vencida)"
                      value={newTemplate.name}
                      onChange={(e) => setNewTemplate((prev) => ({ ...prev, name: e.target.value }))}
                      className="w-full px-4 py-3 rounded-lg bg-background border border-border text-foreground"
                    />
                    <select
                      value={newTemplate.category}
                      onChange={(e) => setNewTemplate((prev) => ({ ...prev, category: e.target.value }))}
                      className="w-full px-4 py-3 rounded-lg bg-background border border-border text-foreground"
                    >
                      <option value="UTILITY">UTILITY</option>
                      <option value="MARKETING">MARKETING</option>
                      <option value="AUTHENTICATION">AUTHENTICATION</option>
                    </select>
                    <input
                      type="text"
                      placeholder="Idioma (ex: pt_BR)"
                      value={newTemplate.language}
                      onChange={(e) => setNewTemplate((prev) => ({ ...prev, language: e.target.value }))}
                      className="w-full px-4 py-3 rounded-lg bg-background border border-border text-foreground"
                    />
                  </div>
                  <textarea
                    rows={2}
                    placeholder="Cabeçalho (opcional, texto curto)"
                    value={newTemplate.header_text}
                    onChange={(e) => setNewTemplate((prev) => ({ ...prev, header_text: e.target.value }))}
                    className="w-full px-4 py-3 rounded-lg bg-background border border-border text-foreground"
                  />
                  <textarea
                    rows={3}
                    placeholder="Corpo do template oficial da Meta (use {{1}}, {{2}}, ...)"
                    value={newTemplate.body_text}
                    onChange={(e) => setNewTemplate((prev) => ({ ...prev, body_text: e.target.value }))}
                    className="w-full px-4 py-3 rounded-lg bg-background border border-border text-foreground"
                  />
                  {(() => {
                    const matches = [...(newTemplate.body_text || '').matchAll(/\{\{(\d+)\}\}/g)];
                    const vars = [...new Set(matches.map((m) => Number(m[1])))]
                      .filter((n) => Number.isInteger(n) && n > 0)
                      .sort((a, b) => a - b);

                    if (!vars.length) return null;
                    return (
                      <div className="space-y-2 border border-border rounded-lg p-3 bg-background/40">
                        <p className="text-sm font-semibold text-foreground">Variáveis do template</p>
                        <p className="text-xs text-muted-foreground">
                          Informe o que cada variável representa e um exemplo (enviado para validação da Meta).
                        </p>
                        {vars.map((num) => (
                          <div key={num} className="grid grid-cols-1 md:grid-cols-3 gap-2">
                            <div className="text-xs text-foreground flex items-center font-semibold">
                              {`{{${num}}}`}
                            </div>
                            <input
                              type="text"
                              placeholder="Descrição (ex: Nome do cliente)"
                              value={variableSamples[num]?.description || ''}
                              onChange={(e) => setVariableSamples((prev) => ({
                                ...prev,
                                [num]: { ...(prev[num] || {}), description: e.target.value }
                              }))}
                              className="w-full px-3 py-2 rounded-lg bg-background border border-border text-foreground text-sm"
                            />
                            <input
                              type="text"
                              placeholder="Exemplo (ex: João)"
                              value={variableSamples[num]?.example || ''}
                              onChange={(e) => setVariableSamples((prev) => ({
                                ...prev,
                                [num]: { ...(prev[num] || {}), example: e.target.value }
                              }))}
                              className="w-full px-3 py-2 rounded-lg bg-background border border-border text-foreground text-sm"
                            />
                          </div>
                        ))}
                      </div>
                    );
                  })()}
                  <textarea
                    rows={2}
                    placeholder="Rodapé (opcional)"
                    value={newTemplate.footer_text}
                    onChange={(e) => setNewTemplate((prev) => ({ ...prev, footer_text: e.target.value }))}
                    className="w-full px-4 py-3 rounded-lg bg-background border border-border text-foreground"
                  />
                  <button
                    type="button"
                    onClick={createBillingTemplate}
                    className="bg-emerald-600 hover:bg-emerald-500 text-white px-4 py-2 rounded-lg font-semibold transition-colors"
                  >
                    Criar template na Meta
                  </button>

                  <div className="space-y-2">
                    {(billingTemplates || []).map((tpl) => (
                      <div key={`${tpl.id || tpl.name}:${tpl.language}`} className="flex items-center justify-between bg-background border border-border rounded-lg px-3 py-2">
                        <div className="text-sm text-foreground">
                          <span className="font-semibold">{tpl.name}</span> - {tpl.language} - {tpl.status || 'UNKNOWN'}
                        </div>
                        <button
                          type="button"
                          onClick={() => deleteBillingTemplate(tpl.id || `${tpl.name}:${tpl.language}`)}
                          className="text-red-400 hover:text-red-300 text-sm font-semibold"
                        >
                          Excluir
                        </button>
                      </div>
                    ))}
                    {!billingTemplates?.length && (
                      <p className="text-sm text-muted-foreground">Nenhum template carregado ainda.</p>
                    )}
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