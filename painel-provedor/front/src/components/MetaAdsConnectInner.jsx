import { useEffect, useMemo, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { Loader2, CheckCircle2, AlertCircle } from 'lucide-react';
import { META_ADS_AUTH_MESSAGE, isAllowedTenantOriginForMeta } from '../utils/metaConnect';
import { META_APP_ID } from '../config/metaWhatsApp';

const ADS_SCOPES = [
  'ads_management',
  'ads_read',
  'business_management',
  'pages_show_list',
  'pages_read_engagement',
  'pages_manage_ads',
].join(',');

const ADS_CONFIG_ID = (import.meta.env.VITE_META_ADS_CONFIG_ID || '').trim();

function loadSdk(onReady, onFail) {
  if (window.FB && typeof window.FB.init === 'function') {
    onReady();
    return;
  }
  window.fbAsyncInit = () => {
    window.FB.init({ appId: META_APP_ID, cookie: true, xfbml: false, version: 'v21.0' });
    onReady();
  };
  if (document.getElementById('facebook-jssdk')) return;
  const js = document.createElement('script');
  js.id = 'facebook-jssdk';
  js.async = true;
  js.src = 'https://connect.facebook.net/pt_BR/sdk.js';
  js.onerror = onFail;
  document.body.appendChild(js);
}

/**
 * Popup aberto pelo Estúdio de Marketing em https://connect.../app/meta/ads-connect.
 * Faz o login do Facebook com permissões de anúncios e devolve o token só à origem do painel.
 */
export default function MetaAdsConnectInner() {
  const [searchParams] = useSearchParams();
  const tenantOrigin = useMemo(() => {
    const raw = (searchParams.get('tenant_origin') || '').trim();
    try {
      return new URL(raw).origin;
    } catch {
      return '';
    }
  }, [searchParams]);
  const tenantOk = Boolean(tenantOrigin && isAllowedTenantOriginForMeta(tenantOrigin) && window.opener);

  const [step, setStep] = useState('loading');
  const [error, setError] = useState('');

  useEffect(() => {
    if (!tenantOk) return;
    loadSdk(
      () => setStep('ready'),
      () => setStep('blocked')
    );
  }, [tenantOk]);

  const login = () => {
    setError('');
    setStep('waiting');
    const options = ADS_CONFIG_ID
      ? { config_id: ADS_CONFIG_ID }
      : { scope: ADS_SCOPES, return_scopes: true, auth_type: 'rerequest' };
    window.FB.login((response) => {
      const token = response?.authResponse?.accessToken;
      if (!token) {
        setError('Login cancelado ou sem permissão. Tente de novo e aceite as permissões de anúncios.');
        setStep('ready');
        return;
      }
      try {
        window.opener.postMessage({ type: META_ADS_AUTH_MESSAGE, accessToken: token }, tenantOrigin);
        setStep('done');
        setTimeout(() => window.close(), 1200);
      } catch {
        setError('Não foi possível devolver a conexão ao painel. Feche esta janela e tente de novo.');
        setStep('ready');
      }
    }, options);
  };

  const box = { maxWidth: 420, margin: '0 auto', textAlign: 'center', paddingTop: 48 };
  const button = {
    backgroundColor: '#1877f2',
    color: 'white',
    border: 'none',
    padding: '12px 20px',
    borderRadius: 8,
    fontWeight: 600,
    cursor: 'pointer',
    width: '100%',
    marginTop: 16,
  };

  return (
    <div
      style={{
        minHeight: '100vh',
        backgroundColor: 'var(--background, #0f172a)',
        color: 'var(--foreground, #f8fafc)',
        fontFamily: 'sans-serif',
        padding: 16,
        boxSizing: 'border-box',
      }}
    >
      <div style={box}>
        {!tenantOk && (
          <>
            <AlertCircle size={44} style={{ color: '#ef4444', marginBottom: 12 }} />
            <p>Abra esta janela pelo botão “Conectar com Facebook” do Estúdio de Marketing.</p>
          </>
        )}
        {tenantOk && step === 'loading' && (
          <>
            <Loader2 size={40} className="animate-spin" style={{ marginBottom: 12 }} />
            <p style={{ fontSize: 14 }}>Carregando o login da Meta…</p>
          </>
        )}
        {tenantOk && step === 'blocked' && (
          <>
            <AlertCircle size={44} style={{ color: '#fbbf24', marginBottom: 12 }} />
            <p style={{ fontWeight: 600 }}>O navegador bloqueou o login da Meta</p>
            <p style={{ fontSize: 13, opacity: 0.85, lineHeight: 1.5 }}>
              Desative o Escudo do Brave ou o bloqueador de anúncios para este site e recarregue a página.
            </p>
            <button type="button" style={button} onClick={() => window.location.reload()}>
              Recarregar
            </button>
          </>
        )}
        {tenantOk && (step === 'ready' || step === 'waiting') && (
          <>
            <p style={{ fontSize: 16, fontWeight: 600 }}>Conectar anúncios da Meta</p>
            <p style={{ fontSize: 13, opacity: 0.85, lineHeight: 1.5 }}>
              Entre com o Facebook que administra a conta de anúncios e a Página da empresa e aceite as permissões
              pedidas. A IA só publica depois que você confirmar no chat.
            </p>
            {error && <p style={{ fontSize: 13, color: '#f87171' }}>{error}</p>}
            <button type="button" style={button} disabled={step === 'waiting'} onClick={login}>
              {step === 'waiting' ? 'Aguardando a Meta…' : 'Entrar com Facebook'}
            </button>
          </>
        )}
        {tenantOk && step === 'done' && (
          <>
            <CheckCircle2 size={48} style={{ color: '#22c55e', marginBottom: 12 }} />
            <p>Conectado. Voltando ao painel…</p>
          </>
        )}
      </div>
      <style>{`
        @keyframes spin { from { transform: rotate(0deg); } to { transform: rotate(360deg); } }
        .animate-spin { animation: spin 1s linear infinite; }
      `}</style>
    </div>
  );
}
