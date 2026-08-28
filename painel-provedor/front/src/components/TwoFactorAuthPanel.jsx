import React, { useCallback, useEffect, useState } from 'react';
import axios from 'axios';
import { AlertTriangle, RefreshCw, Save, ShieldCheck, Smartphone } from 'lucide-react';
import { publicAssetUrl } from '../utils/publicAssetUrl';

const RECOMMENDED_APPS = [
  {
    name: 'Google Authenticator',
    logo: '2fa/googleotp.webp',
    play: 'https://play.google.com/store/apps/details?id=com.google.android.apps.authenticator2',
    apple: 'https://apps.apple.com/app/google-authenticator/id388497605',
  },
  {
    name: 'Microsoft Authenticator',
    logo: '2fa/microsoftotp.webp',
    play: 'https://play.google.com/store/apps/details?id=com.azure.authenticator',
    apple: 'https://apps.apple.com/app/microsoft-authenticator/id983156458',
  },
  {
    name: 'FreeOTP Authenticator',
    logo: '2fa/freeotp.webp',
    play: 'https://play.google.com/store/apps/details?id=org.fedorahosted.freeotp',
    apple: 'https://apps.apple.com/app/freeotp-authenticator/id872559395',
  },
  {
    name: 'Authy Authenticator',
    logo: '2fa/authyotp.webp',
    play: 'https://play.google.com/store/apps/details?id=com.authy.authy',
    apple: 'https://apps.apple.com/app/authy/id494168017',
  },
];

const STORE_BADGES = {
  apple: '2fa/appstore-badge.png.png',
  play: '2fa/play-badge.png',
};

function formatDateTime(iso) {
  if (!iso) return '—';
  try {
    return new Date(iso).toLocaleString('pt-BR', {
      day: '2-digit',
      month: '2-digit',
      year: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
    });
  } catch {
    return '—';
  }
}

export default function TwoFactorAuthPanel({ username }) {
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [recreating, setRecreating] = useState(false);
  const [otpCode, setOtpCode] = useState('');
  const [message, setMessage] = useState('');
  const [messageType, setMessageType] = useState('success');
  const [setup, setSetup] = useState({
    is_active: false,
    secret_masked: '',
    qr_code: null,
    created_at: null,
    updated_at: null,
    username: '',
  });

  const authHeaders = useCallback(() => {
    const token = localStorage.getItem('auth_token') || localStorage.getItem('token');
    return token ? { Authorization: `Token ${token}` } : {};
  }, []);

  const loadSetup = useCallback(async () => {
    setLoading(true);
    try {
      const { data } = await axios.get('/api/auth/2fa/', { headers: authHeaders() });
      setSetup(data);
    } catch (err) {
      setMessageType('error');
      setMessage(err.response?.data?.error || 'Não foi possível carregar a configuração 2FA.');
    } finally {
      setLoading(false);
    }
  }, [authHeaders]);

  useEffect(() => {
    loadSetup();
  }, [loadSetup]);

  const showMsg = (type, text) => {
    setMessageType(type);
    setMessage(text);
  };

  const handleSave = async () => {
    if (!otpCode.trim()) {
      showMsg('error', 'Informe o código de 6 dígitos do aplicativo.');
      return;
    }
    setSaving(true);
    setMessage('');
    try {
      const url = setup.is_active ? '/api/auth/2fa/disable/' : '/api/auth/2fa/enable/';
      const { data } = await axios.post(url, { otp_code: otpCode.trim() }, { headers: authHeaders() });
      setSetup(data);
      setOtpCode('');
      showMsg('success', setup.is_active ? '2FA desativado com sucesso.' : '2FA ativado com sucesso.');
    } catch (err) {
      showMsg('error', err.response?.data?.error || 'Falha ao salvar configuração 2FA.');
    } finally {
      setSaving(false);
    }
  };

  const handleRecreate = async () => {
    if (!window.confirm('Gerar nova chave? O 2FA ficará inativo até confirmar o novo código no aplicativo.')) {
      return;
    }
    setRecreating(true);
    setMessage('');
    try {
      const { data } = await axios.post('/api/auth/2fa/recreate/', {}, { headers: authHeaders() });
      setSetup(data);
      setOtpCode('');
      showMsg('success', 'Nova chave gerada. Escaneie o QR code e confirme com o código OTP.');
    } catch (err) {
      showMsg('error', err.response?.data?.error || 'Falha ao recriar chave.');
    } finally {
      setRecreating(false);
    }
  };

  if (loading) {
    return (
      <div className="p-6 text-center text-muted-foreground text-sm">
        Carregando autenticação 2FA…
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <div
        className={`flex items-start gap-3 rounded-lg border px-4 py-3 ${
          setup.is_active
            ? 'border-emerald-500/40 bg-emerald-500/10 text-emerald-200'
            : 'border-amber-500/50 bg-amber-500/10 text-amber-100'
        }`}
      >
        {setup.is_active ? (
          <ShieldCheck className="w-5 h-5 shrink-0 mt-0.5" />
        ) : (
          <AlertTriangle className="w-5 h-5 shrink-0 mt-0.5" />
        )}
        <p className="text-sm font-medium">
          {setup.is_active
            ? 'Autenticação 2FA está ativa'
            : 'Autenticação 2FA está inativa'}
        </p>
      </div>

      {message && (
        <div
          className={`rounded-lg border px-3 py-2 text-sm ${
            messageType === 'success'
              ? 'border-emerald-500/40 bg-emerald-500/10 text-emerald-200'
              : 'border-red-500/40 bg-red-500/10 text-red-200'
          }`}
        >
          {message}
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        {/* Dados */}
        <div className="lg:col-span-2 rounded-xl border border-border bg-card/40 p-4 space-y-4">
          <h4 className="text-sm font-semibold text-white border-b border-border pb-2">Dados</h4>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 text-sm">
            <div>
              <label className="block text-white/60 mb-1">Usuário</label>
              <input
                readOnly
                value={setup.username || username || ''}
                className="niochat-input w-full bg-muted/30"
              />
            </div>
            <div>
              <label className="block text-white/60 mb-1">OTP Secret</label>
              <input
                readOnly
                value={setup.secret_masked || '—'}
                className="niochat-input w-full bg-muted/30 font-mono text-xs"
              />
            </div>
            <div>
              <label className="block text-white/60 mb-1">Cadastrado</label>
              <input
                readOnly
                value={formatDateTime(setup.created_at)}
                className="niochat-input w-full bg-muted/30"
              />
            </div>
            <div>
              <label className="block text-white/60 mb-1">Alterado</label>
              <input
                readOnly
                value={formatDateTime(setup.updated_at)}
                className="niochat-input w-full bg-muted/30"
              />
            </div>
            <div className="sm:col-span-2 flex items-center gap-2">
              <input
                type="checkbox"
                readOnly
                checked={setup.is_active}
                className="h-4 w-4 rounded border-border"
              />
              <span className="text-white/80">Ativo</span>
            </div>
          </div>

          <div>
            <label className="block text-sm font-medium text-white mb-1">Senha OTP</label>
            <input
              type="text"
              inputMode="numeric"
              autoComplete="one-time-code"
              maxLength={6}
              placeholder="000000"
              value={otpCode}
              onChange={(e) => setOtpCode(e.target.value.replace(/\D/g, '').slice(0, 6))}
              className="niochat-input w-full max-w-xs tracking-[0.35em] text-center font-mono text-lg"
            />
            <p className="text-xs text-white/60 mt-2">
              {setup.is_active
                ? 'Para desativar o 2FA, confirme com o código atual do aplicativo.'
                : 'Para habilitar o 2FA, escaneie o QR code e confirme a senha OTP gerada no aplicativo.'}
            </p>
          </div>

          {setup.qr_code && (
            <div>
              <label className="block text-sm font-medium text-white mb-2">QR Code</label>
              <div className="inline-block rounded-lg border border-border bg-white p-3">
                <img src={setup.qr_code} alt="QR Code 2FA" className="w-48 h-48" />
              </div>
            </div>
          )}

          <div className="flex flex-wrap gap-2 pt-2">
            <button
              type="button"
              onClick={handleSave}
              disabled={saving || recreating}
              className="inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-emerald-600 text-white hover:bg-emerald-700 disabled:opacity-50"
            >
              <Save className="w-4 h-4" />
              {saving ? 'Salvando…' : setup.is_active ? 'Desativar 2FA' : 'Salvar e ativar'}
            </button>
            <button
              type="button"
              onClick={handleRecreate}
              disabled={saving || recreating}
              className="inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-amber-600 text-white hover:bg-amber-700 disabled:opacity-50"
            >
              <RefreshCw className={`w-4 h-4 ${recreating ? 'animate-spin' : ''}`} />
              Recriar chave
            </button>
          </div>
        </div>

        {/* Aplicativos recomendados */}
        <div className="rounded-xl border border-border bg-card/40 p-4">
          <h4 className="text-sm font-semibold text-white border-b border-border pb-2 mb-3 flex items-center gap-2">
            <Smartphone className="w-4 h-4" />
            Aplicativos recomendados
          </h4>
          <ul className="space-y-4">
            {RECOMMENDED_APPS.map((app) => (
              <li key={app.name} className="flex gap-3 text-sm">
                <div className="shrink-0 w-11 h-11 rounded-xl overflow-hidden border border-border/60 bg-white shadow-sm">
                  <img
                    src={publicAssetUrl(app.logo)}
                    alt={app.name}
                    className="w-full h-full object-cover"
                    loading="lazy"
                  />
                </div>
                <div className="min-w-0 flex-1">
                  <p className="font-medium text-white mb-2 leading-tight">{app.name}</p>
                  <div className="flex flex-wrap items-center gap-2">
                    <a
                      href={app.apple}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="inline-block opacity-90 hover:opacity-100 transition-opacity"
                      title="App Store"
                    >
                      <img
                        src={publicAssetUrl(STORE_BADGES.apple)}
                        alt="Baixar na App Store"
                        className="h-8 w-auto"
                        loading="lazy"
                      />
                    </a>
                    <a
                      href={app.play}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="inline-block opacity-90 hover:opacity-100 transition-opacity"
                      title="Google Play"
                    >
                      <img
                        src={publicAssetUrl(STORE_BADGES.play)}
                        alt="Disponível no Google Play"
                        className="h-8 w-auto"
                        loading="lazy"
                      />
                    </a>
                  </div>
                </div>
              </li>
            ))}
          </ul>
        </div>
      </div>
    </div>
  );
}
