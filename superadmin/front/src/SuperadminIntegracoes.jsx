import React, { useEffect, useState } from 'react';
import { Link2, Save, Eye, EyeOff, Server, KeyRound } from 'lucide-react';
import axios from 'axios';
import { getAsaasWebhookUrl, isSuperadminLocalDev, SUPERADMIN_PRODUCTION_ORIGIN, SUPERADMIN_LOCAL_ORIGIN } from './utils/superadminAppUrl';

export default function SuperadminIntegracoes() {
  const [config, setConfig] = useState(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');
  const [showHetznerToken, setShowHetznerToken] = useState(false);
  const [showGoogleAIKey, setShowGoogleAIKey] = useState(false);
  const [showOpenAITranscriptionKey, setShowOpenAITranscriptionKey] = useState(false);
  const [showAsaasToken, setShowAsaasToken] = useState(false);
  const [showAsaasWebhookToken, setShowAsaasWebhookToken] = useState(false);
  const [showAwesomeApiToken, setShowAwesomeApiToken] = useState(false);

  useEffect(() => {
    const fetchConfig = async () => {
      setLoading(true);
      setError('');
      try {
        const token = localStorage.getItem('token');
        const res = await axios.get('/api/system-config/', {
          headers: { Authorization: `Token ${token}` },
        });
        setConfig(res.data);
      } catch (err) {
        setError(`Erro ao carregar integrações: ${err.response?.data?.detail || err.message}`);
      } finally {
        setLoading(false);
      }
    };
    fetchConfig();
  }, []);

  const updateField = (name, value) => {
    setConfig((prev) => ({ ...(prev || {}), [name]: value }));
  };

  const handleSave = async (e) => {
    e.preventDefault();
    setSaving(true);
    setError('');
    setSuccess('');
    try {
      const token = localStorage.getItem('token');
      const payload = { ...(config || {}) };
      const res = await axios.put('/api/system-config/1/', payload, {
        headers: { Authorization: `Token ${token}` },
      });
      setConfig(res.data);
      setSuccess('Integrações salvas com sucesso.');
    } catch (err) {
      setError(`Erro ao salvar integrações: ${err.response?.data?.detail || err.message}`);
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="flex-1 p-6 bg-background overflow-y-auto">
      <div className="max-w-4xl mx-auto space-y-6">
        <div>
          <h1 className="text-3xl font-bold text-foreground mb-2 flex items-center gap-3">
            <Link2 className="w-8 h-8 text-primary" />
            Integrações
          </h1>
          <p className="text-muted-foreground">
            Centralize chaves e conexões do sistema, incluindo a API da Hetzner.
          </p>
        </div>

        {loading ? (
          <div className="text-center text-muted-foreground py-16">Carregando integrações...</div>
        ) : (
          <form onSubmit={handleSave} className="space-y-6">
            {error && (
              <div className="bg-red-900/20 border border-red-500/30 text-red-400 rounded-lg p-4">
                {error}
              </div>
            )}
            {success && (
              <div className="bg-green-900/20 border border-green-500/30 text-green-400 rounded-lg p-4">
                {success}
              </div>
            )}

            <section className="bg-card border border-border rounded-xl shadow-lg p-6 space-y-4">
              <h2 className="text-lg font-semibold text-foreground flex items-center gap-2">
                <Server className="w-5 h-5 text-primary" />
                Hetzner
              </h2>
              <div>
                <label className="block text-xs font-semibold text-muted-foreground uppercase mb-2">
                  Token API Hetzner
                </label>
                <div className="relative">
                  <input
                    type={showHetznerToken ? 'text' : 'password'}
                    className="w-full px-4 py-2 pr-12 rounded bg-[#181b20] text-white border border-border"
                    value={config?.hetzner_api_token || ''}
                    onChange={(e) => updateField('hetzner_api_token', e.target.value)}
                    placeholder="Cole o token da API da Hetzner"
                  />
                  <button
                    type="button"
                    onClick={() => setShowHetznerToken((v) => !v)}
                    className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-400 hover:text-white"
                  >
                    {showHetznerToken ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                  </button>
                </div>
              </div>
            </section>

            <section className="bg-card border border-border rounded-xl shadow-lg p-6 space-y-4">
              <h2 className="text-lg font-semibold text-foreground flex items-center gap-2">
                <KeyRound className="w-5 h-5 text-primary" />
                Configurações do Google AI
              </h2>
              <div>
                <label className="block text-xs font-semibold text-muted-foreground uppercase mb-2">
                  Chave Google AI
                </label>
                <div className="relative">
                  <input
                    type={showGoogleAIKey ? 'text' : 'password'}
                    className="w-full px-4 py-2 pr-12 rounded bg-[#181b20] text-white border border-border"
                    value={config?.google_api_key || ''}
                    onChange={(e) => updateField('google_api_key', e.target.value)}
                    placeholder="Cole a chave do Google AI"
                  />
                  <button
                    type="button"
                    onClick={() => setShowGoogleAIKey((v) => !v)}
                    className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-400 hover:text-white"
                  >
                    {showGoogleAIKey ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                  </button>
                </div>
              </div>
            </section>

            <section className="bg-card border border-border rounded-xl shadow-lg p-6 space-y-4">
              <h2 className="text-lg font-semibold text-foreground flex items-center gap-2">
                <KeyRound className="w-5 h-5 text-primary" />
                Configurações de Transcrição de Áudio
              </h2>
              <div>
                <label className="block text-xs font-semibold text-muted-foreground uppercase mb-2">
                  Chave OpenAI Transcription
                </label>
                <div className="relative">
                  <input
                    type={showOpenAITranscriptionKey ? 'text' : 'password'}
                    className="w-full px-4 py-2 pr-12 rounded bg-[#181b20] text-white border border-border"
                    value={config?.openai_transcription_api_key || ''}
                    onChange={(e) => updateField('openai_transcription_api_key', e.target.value)}
                    placeholder="Cole a chave da transcrição de áudio"
                  />
                  <button
                    type="button"
                    onClick={() => setShowOpenAITranscriptionKey((v) => !v)}
                    className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-400 hover:text-white"
                  >
                    {showOpenAITranscriptionKey ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                  </button>
                </div>
              </div>
            </section>

            <section className="bg-card border border-border rounded-xl shadow-lg p-6 space-y-4">
              <h2 className="text-lg font-semibold text-foreground flex items-center gap-2">
                <KeyRound className="w-5 h-5 text-primary" />
                Configurações do Asaas
              </h2>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div>
                  <label className="block text-xs font-semibold text-muted-foreground uppercase mb-2">
                    Asaas Access Token
                  </label>
                  <div className="relative">
                    <input
                      type={showAsaasToken ? 'text' : 'password'}
                      className="w-full px-4 py-2 pr-12 rounded bg-[#181b20] text-white border border-border"
                      value={config?.asaas_access_token || ''}
                      onChange={(e) => updateField('asaas_access_token', e.target.value)}
                      placeholder="Cole o token da API do Asaas"
                    />
                    <button
                      type="button"
                      onClick={() => setShowAsaasToken((v) => !v)}
                      className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-400 hover:text-white"
                    >
                      {showAsaasToken ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                    </button>
                  </div>
                </div>
                <div>
                  <label className="block text-xs font-semibold text-muted-foreground uppercase mb-2">
                    URL do Webhook (cadastrar no Asaas)
                  </label>
                  <input
                    type="text"
                    readOnly
                    className="w-full px-4 py-2 rounded bg-[#181b20] text-emerald-300 border border-border font-mono text-sm"
                    value={getAsaasWebhookUrl()}
                  />
                  <p className="text-xs text-muted-foreground mt-1 leading-relaxed">
                    {isSuperadminLocalDev() ? (
                      <>
                        Em <strong className="text-foreground">dev local</strong>, use{' '}
                        <strong className="text-foreground">{SUPERADMIN_LOCAL_ORIGIN}</strong> no hosts/nginx e túnel
                        HTTPS se o Asaas exigir URL pública. Em produção:{' '}
                        <strong className="text-foreground">{SUPERADMIN_PRODUCTION_ORIGIN}</strong>.
                      </>
                    ) : (
                      <>
                        Cadastre no Asaas com HTTPS público ({SUPERADMIN_PRODUCTION_ORIGIN}). Não use localhost nem
                        URL do SGP.
                      </>
                    )}
                  </p>
                </div>
                <div>
                  <label className="block text-xs font-semibold text-muted-foreground uppercase mb-2">
                    Asaas Webhook Auth Token
                  </label>
                  <div className="relative">
                    <input
                      type={showAsaasWebhookToken ? 'text' : 'password'}
                      className="w-full px-4 py-2 pr-12 rounded bg-[#181b20] text-white border border-border"
                      value={config?.asaas_webhook_auth_token || ''}
                      onChange={(e) => updateField('asaas_webhook_auth_token', e.target.value)}
                      placeholder="Cole o mesmo token gerado no Asaas (Gerar Token)"
                    />
                    <button
                      type="button"
                      onClick={() => setShowAsaasWebhookToken((v) => !v)}
                      className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-400 hover:text-white"
                    >
                      {showAsaasWebhookToken ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                    </button>
                  </div>
                  <p className="text-xs text-muted-foreground mt-1 leading-relaxed">
                    Gere o token no Asaas, cole aqui e salve. Marque os eventos{' '}
                    <strong className="text-foreground">PAYMENT_RECEIVED</strong>,{' '}
                    <strong className="text-foreground">PAYMENT_CONFIRMED</strong> e{' '}
                    <strong className="text-foreground">PAYMENT_OVERDUE</strong> para liberar o acesso logo após o
                    pagamento.
                  </p>
                </div>
              </div>
              <div className="flex items-center space-x-3 pt-2">
                <input
                  type="checkbox"
                  id="asaas_sandbox"
                  checked={!!config?.asaas_sandbox}
                  onChange={(e) => updateField('asaas_sandbox', e.target.checked)}
                  className="w-4 h-4 text-primary bg-background border-border rounded focus:ring-primary focus:ring-2"
                />
                <label htmlFor="asaas_sandbox" className="text-sm font-medium text-foreground">
                  Modo Sandbox (Habilitar para usar chaves de teste do Asaas)
                </label>
              </div>
            </section>

            <section className="bg-card border border-border rounded-xl shadow-lg p-6 space-y-4">
              <h2 className="text-lg font-semibold text-foreground flex items-center gap-2">
                <KeyRound className="w-5 h-5 text-primary" />
                AwesomeAPI (cotação USD → BRL)
              </h2>
              <p className="text-sm text-muted-foreground leading-relaxed">
                Usada no <strong className="text-foreground">Meta · WhatsApp Analytics</strong> dos provedores
                para converter o gasto aproximado em Real. Cadastre a chave em{' '}
                <a
                  href="https://docs.awesomeapi.com.br/"
                  target="_blank"
                  rel="noreferrer"
                  className="text-primary underline"
                >
                  docs.awesomeapi.com.br
                </a>
                .
              </p>
              <div>
                <label className="block text-xs font-semibold text-muted-foreground uppercase mb-2">
                  API Key AwesomeAPI
                </label>
                <div className="relative">
                  <input
                    type={showAwesomeApiToken ? 'text' : 'password'}
                    className="w-full px-4 py-2 pr-12 rounded bg-[#181b20] text-white border border-border"
                    value={config?.awesomeapi_token || ''}
                    onChange={(e) => updateField('awesomeapi_token', e.target.value)}
                    placeholder="Cole a API Key da AwesomeAPI"
                  />
                  <button
                    type="button"
                    onClick={() => setShowAwesomeApiToken((v) => !v)}
                    className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-400 hover:text-white"
                  >
                    {showAwesomeApiToken ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                  </button>
                </div>
              </div>
              <div className="pt-2">
                <p className="text-xs font-semibold text-muted-foreground uppercase mb-3">
                  Tarifas WhatsApp por mensagem (USD)
                </p>
                <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                  <div>
                    <label className="block text-xs text-muted-foreground mb-1">Utility</label>
                    <input
                      type="number"
                      step="0.0001"
                      className="w-full px-4 py-2 rounded bg-[#181b20] text-white border border-border font-mono"
                      value={config?.whatsapp_rate_utility_usd ?? 0.0068}
                      onChange={(e) => updateField('whatsapp_rate_utility_usd', e.target.value)}
                    />
                  </div>
                  <div>
                    <label className="block text-xs text-muted-foreground mb-1">Marketing</label>
                    <input
                      type="number"
                      step="0.0001"
                      className="w-full px-4 py-2 rounded bg-[#181b20] text-white border border-border font-mono"
                      value={config?.whatsapp_rate_marketing_usd ?? 0.0625}
                      onChange={(e) => updateField('whatsapp_rate_marketing_usd', e.target.value)}
                    />
                  </div>
                  <div>
                    <label className="block text-xs text-muted-foreground mb-1">Authentication</label>
                    <input
                      type="number"
                      step="0.0001"
                      className="w-full px-4 py-2 rounded bg-[#181b20] text-white border border-border font-mono"
                      value={config?.whatsapp_rate_authentication_usd ?? 0.0068}
                      onChange={(e) => updateField('whatsapp_rate_authentication_usd', e.target.value)}
                    />
                  </div>
                </div>
                <p className="text-xs text-muted-foreground mt-2">
                  Usadas no Meta Analytics quando a Meta não devolve o custo oficial: volume × tarifa × cotação USD-BRL.
                </p>
              </div>
            </section>

            <div className="flex justify-end">
              <button
                type="submit"
                disabled={saving}
                className="inline-flex items-center gap-2 px-6 py-2 rounded-lg bg-primary text-white font-semibold hover:bg-primary/90 disabled:opacity-50"
              >
                <Save className="w-4 h-4" />
                {saving ? 'Salvando...' : 'Salvar Integrações'}
              </button>
            </div>
          </form>
        )}
      </div>
    </div>
  );
}
