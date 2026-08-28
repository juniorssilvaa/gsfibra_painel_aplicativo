import React, { useEffect, useRef, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { Loader2, CheckCircle2, AlertCircle } from 'lucide-react';
import axios from 'axios';
import { isAllowedTenantOriginForMeta, isLocalDevOrigin } from '../utils/metaConnect';

const MSG = {
  READY: 'INSTAGRAM_CONNECT_INNER_READY',
  AUTH: 'INSTAGRAM_CONNECT_AUTH',
  SUCCESS: 'INSTAGRAM_OAUTH_SUCCESS',
  ERROR: 'INSTAGRAM_OAUTH_ERROR',
};

/**
 * Bridge OAuth Instagram em connect.niohub.com.br (mesmo padrão do MetaConnectInner).
 * Obtém oauth_url do backend do tenant (credenciais Instagram no superadmin → Portainer).
 */
export default function InstagramConnectInner() {
  const [searchParams] = useSearchParams();
  const tenantOrigin = (searchParams.get('tenant_origin') || '').trim().replace(/\/+$/, '');
  const tenantOriginNorm = React.useMemo(() => {
    try {
      return new URL(tenantOrigin).origin;
    } catch {
      return tenantOrigin;
    }
  }, [tenantOrigin]);
  const providerId = searchParams.get('provider_id') || '1';
  const channelId = searchParams.get('channel_id') || '';
  const tenantOk = Boolean(tenantOrigin && isAllowedTenantOriginForMeta(tenantOrigin));

  const [step, setStep] = useState('auth_wait');
  const [error, setError] = useState(null);
  const tokenRef = useRef(null);
  const hasLaunched = useRef(false);
  const popupRef = useRef(null);

  async function launchInstagramOAuth() {
    if (hasLaunched.current || !tokenRef.current || !tenantOk || !channelId) return;
    hasLaunched.current = true;
    setStep('waiting');

    try {
      const apiBase = tenantOriginNorm.replace(/\/+$/, '');
      const response = await axios.post(
        `${apiBase}/api/canais/${channelId}/connect-instagram/`,
        {
          frontend_origin: tenantOriginNorm,
          local_dev: isLocalDevOrigin(),
        },
        { headers: { Authorization: `Token ${tokenRef.current}` } }
      );

      if (!response.data?.success || !response.data.oauth_url) {
        throw new Error(response.data?.error || 'Não foi possível iniciar OAuth do Instagram');
      }

      const popup = window.open(
        response.data.oauth_url,
        'instagram_oauth',
        'width=520,height=720,scrollbars=yes'
      );
      popupRef.current = popup;
      if (!popup) {
        throw new Error('Permita pop-ups para conectar o Instagram.');
      }
    } catch (err) {
      hasLaunched.current = false;
      const msg = err.response?.data?.error || err.message || 'Erro ao conectar Instagram';
      setError(msg);
      setStep('error');
      const bridge = window.opener || (window.parent !== window ? window.parent : null);
      if (bridge && tenantOk) {
        try {
          bridge.postMessage({ type: MSG.ERROR, message: msg }, tenantOriginNorm);
        } catch (_) {
          /* ignore */
        }
      }
    }
  }

  useEffect(() => {
    if (!tenantOk) {
      setError('Origem do tenant inválida.');
      setStep('error');
      return undefined;
    }

    const onMsg = (event) => {
      if (event.origin !== tenantOriginNorm) return;
      if (event.data?.type === MSG.AUTH && event.data.token) {
        tokenRef.current = event.data.token;
        launchInstagramOAuth();
      }
    };
    window.addEventListener('message', onMsg);

    const onOAuthResult = (event) => {
      const payload = event.data;
      if (!payload || typeof payload !== 'object') return;
      if (payload.type !== MSG.SUCCESS && payload.type !== MSG.ERROR) return;

      const allowedOrigins = [
        tenantOriginNorm,
        window.location.origin,
        'https://api.niohub.com.br',
        'https://api-local.niohub.com.br',
      ];
      if (!allowedOrigins.includes(event.origin) && event.origin !== 'null') return;

      const bridge = window.parent !== window ? window.parent : window.opener;
      if (bridge && tenantOk) {
        try {
          bridge.postMessage(payload, tenantOriginNorm);
        } catch (_) {
          /* ignore */
        }
      }

      if (payload.type === MSG.SUCCESS) {
        setStep('success');
      } else {
        setError(payload.error || 'Erro ao conectar Instagram');
        setStep('error');
      }
    };
    window.addEventListener('message', onOAuthResult);

    const bridge = window.opener || (window.parent !== window ? window.parent : null);
    if (bridge) {
      setTimeout(() => {
        bridge.postMessage({ type: MSG.READY }, tenantOriginNorm);
      }, 0);
    }

    return () => {
      window.removeEventListener('message', onMsg);
      window.removeEventListener('message', onOAuthResult);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tenantOrigin, tenantOriginNorm, tenantOk, channelId]);

  if (!tenantOk) {
    return (
      <div style={{ padding: 24, fontFamily: 'sans-serif', color: '#b91c1c' }}>
        {error || 'tenant_origin inválido.'}
      </div>
    );
  }

  return (
    <div
      style={{
        minHeight: '100vh',
        backgroundColor: '#0f172a',
        color: '#f8fafc',
        fontFamily: 'sans-serif',
        padding: 16,
        boxSizing: 'border-box',
      }}
    >
      <div style={{ maxWidth: 480, margin: '0 auto', textAlign: 'center' }}>
        {step === 'auth_wait' && (
          <>
            <Loader2 size={40} className="animate-spin" style={{ marginBottom: 12 }} />
            <p style={{ fontSize: 14, opacity: 0.85 }}>Aguardando painel do provedor…</p>
          </>
        )}
        {step === 'waiting' && (
          <>
            <Loader2 size={40} className="animate-spin" style={{ marginBottom: 12 }} />
            <p style={{ fontSize: 14 }}>Conclua o login na janela do Instagram.</p>
            <button
              type="button"
              onClick={() => {
                hasLaunched.current = false;
                launchInstagramOAuth();
              }}
              style={{
                marginTop: 12,
                fontSize: 13,
                color: '#93c5fd',
                background: 'none',
                border: 'none',
                cursor: 'pointer',
                textDecoration: 'underline',
              }}
            >
              Reabrir janela do Instagram
            </button>
          </>
        )}
        {step === 'success' && (
          <>
            <CheckCircle2 size={48} style={{ color: '#22c55e', marginBottom: 12 }} />
            <p>Instagram conectado!</p>
          </>
        )}
        {step === 'error' && (
          <>
            <AlertCircle size={48} style={{ color: '#ef4444', marginBottom: 12 }} />
            <p>{error}</p>
            <button
              type="button"
              onClick={() => window.location.reload()}
              style={{
                marginTop: 12,
                backgroundColor: '#e1306c',
                color: 'white',
                border: 'none',
                padding: '10px 18px',
                borderRadius: 6,
                cursor: 'pointer',
              }}
            >
              Tentar novamente
            </button>
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
