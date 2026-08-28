import React, { useState, useEffect, useRef } from 'react';
import { useSearchParams } from 'react-router-dom';
import { Loader2, CheckCircle2, AlertCircle } from 'lucide-react';
import useMetaEmbeddedSignupListener from '../hooks/useMetaEmbeddedSignupListener.jsx';
import { isAllowedTenantOriginForMeta } from '../utils/metaConnect';
import { META_APP_ID, META_CONFIG_ID } from '../config/metaWhatsApp';

const MSG = {
  READY: 'META_CONNECT_INNER_READY',
  AUTH: 'META_CONNECT_AUTH',
  SUCCESS: 'META_CONNECT_SUCCESS',
  ERROR: 'META_CONNECT_ERROR',
  FINISH_REQUEST: 'META_CONNECT_FINISH_REQUEST',
  FINISH_RESULT: 'META_CONNECT_FINISH_RESULT',
};

function tenantBridge() {
  return window.opener || window.parent;
}

/**
 * Pública em https://connect.../app/meta/connect-inner (popup ou iframe).
 */
export default function MetaConnectInner() {
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
  const channelId = searchParams.get('channel_id');
  const tenantOk = Boolean(tenantOrigin && isAllowedTenantOriginForMeta(tenantOrigin));

  const [step, setStep] = useState('auth_wait');
  const [error, setError] = useState(null);
  const [resultData, setResultData] = useState(null);
  const authCodeRef = useRef(null);
  const eventDataRef = useRef(null);
  const tokenRef = useRef(null);
  const hasLaunched = useRef(false);
  const sdkLoaded = useRef(false);
  const processingRef = useRef(false);
  const tryFinalizeRef = useRef(null);

  function handleOnFinish(wabaId, eventData) {
    eventDataRef.current = { wabaId, ...eventData };
    tryFinalizeRef.current?.();
  }

  const { sendFinishToBackend } = useMetaEmbeddedSignupListener({
    providerId,
    debug: true,
    onFinish: tenantOk ? handleOnFinish : undefined,
    apiOrigin: tenantOk ? tenantOrigin : null,
  });

  async function tryFinalize() {
    if (!eventDataRef.current || !authCodeRef.current) return;
    if (processingRef.current || step === 'success') return;

    const bridge = window.opener || (window.parent !== window ? window.parent : null);
    const useParentFinish = Boolean(tenantOk && bridge && bridge !== window);

    const { wabaId, ...eventData } = eventDataRef.current;
    const code = authCodeRef.current;
    const fullPayloadData = { ...eventData, code };

    if (useParentFinish) {
      processingRef.current = true;
      setStep('processing');
      try {
        bridge.postMessage(
          {
            type: MSG.FINISH_REQUEST,
            wabaId,
            providerId,
            channelId,
            payload: fullPayloadData,
          },
          tenantOriginNorm
        );
      } catch (err) {
        processingRef.current = false;
        const msg = err.message || 'Erro ao enviar dados ao painel';
        setError(msg);
        setStep('error');
        try {
          bridge.postMessage({ type: MSG.ERROR, message: msg }, tenantOriginNorm);
        } catch (_) {
          /* ignore */
        }
      }
      return;
    }

    const token = tokenRef.current;
    if (!token) {
      setError('Token não recebido do painel.');
      setStep('error');
      return;
    }

    processingRef.current = true;
    setStep('processing');

    try {
      const response = await sendFinishToBackend(wabaId, providerId, {
        payload: fullPayloadData,
        channelId,
        authToken: token,
      });
      if (response.success) {
        setResultData(response.canal);
        setStep('success');
        const br = tenantBridge();
        if (br && tenantOk) {
          br.postMessage({ type: MSG.SUCCESS, canal: response.canal }, tenantOriginNorm);
        }
      } else {
        throw new Error(response.error || 'Erro ao processar integração');
      }
    } catch (err) {
      const msg = err.message || 'Erro';
      setError(msg);
      setStep('error');
      processingRef.current = false;
      const brErr = tenantBridge();
      if (brErr && tenantOk) {
        brErr.postMessage({ type: MSG.ERROR, message: msg }, tenantOriginNorm);
      }
    }
  }

  tryFinalizeRef.current = tryFinalize;

  function buildMetaOAuthUrl() {
    const BACKEND_URL = tenantOrigin.replace(/\/+$/, '');
    const redirectUri = encodeURIComponent(`${BACKEND_URL}/api/auth/facebook/callback/`);
    const extras = encodeURIComponent(
      JSON.stringify({
        featureType: 'whatsapp_business_app_onboarding',
        sessionInfoVersion: '3',
      })
    );
    const stateStr = `provider_${providerId}${window.location.protocol !== 'https:' ? '_local' : ''}`;
    return `https://www.facebook.com/v21.0/dialog/oauth?client_id=${META_APP_ID}&config_id=${META_CONFIG_ID}&response_type=code&redirect_uri=${redirectUri}&state=${stateStr}&extras=${extras}`;
  }

  function openMetaOAuthPopupWindow() {
    const oauthUrl = buildMetaOAuthUrl();
    const width = 600;
    const height = 700;
    const left = window.screen.width / 2 - width / 2;
    const top = window.screen.height / 2 - height / 2;
    window.open(
      oauthUrl,
      'MetaSignup',
      `width=${width},height=${height},left=${left},top=${top},scrollbars=yes,status=yes`
    );
  }

  /**
   * Brave Shields / bloqueadores costumam bloquear pedidos a facebook.com (ERR_BLOCKED_BY_CLIENT).
   * Abrir só a URL de OAuth (sem depender do JS SDK) após clique do utilizador costuma funcionar.
   */
  function launchWhatsAppSignup() {
    if (hasLaunched.current || !tokenRef.current || !tenantOk) return;
    hasLaunched.current = true;

    if (window.location.protocol === 'https:' && window.FB) {
      window.FB.login(
        (response) => {
          if (response.authResponse?.code) {
            authCodeRef.current = response.authResponse.code;
            tryFinalizeRef.current?.();
          }
        },
        {
          config_id: META_CONFIG_ID,
          response_type: 'code',
          override_default_response_type: true,
          extras: {
            setup: {},
            featureType: 'whatsapp_business_app_onboarding',
            sessionInfoVersion: '3',
          },
        }
      );
    } else {
      openMetaOAuthPopupWindow();
    }
  }

  function openOAuthFromUserClick() {
    if (!tokenRef.current || !tenantOk) return;
    openMetaOAuthPopupWindow();
  }

  useEffect(() => {
    if (!tenantOk) {
      setError('Origem do tenant inválida.');
      setStep('error');
      return;
    }

    const onMsg = (event) => {
      if (event.origin !== tenantOriginNorm) return;
      if (event.data?.type === MSG.AUTH && event.data.token) {
        tokenRef.current = event.data.token;
        setStep('waiting');
        if (authCodeRef.current && eventDataRef.current) {
          tryFinalizeRef.current?.();
        }
      }
    };
    window.addEventListener('message', onMsg);

    const br = tenantBridge();
    if (br) {
      setTimeout(() => {
        br.postMessage({ type: MSG.READY }, tenantOriginNorm);
      }, 0);
    }

    const codeFromUrl = searchParams.get('code');
    if (codeFromUrl && !authCodeRef.current) {
      authCodeRef.current = codeFromUrl;
      // Não chamar tryFinalize aqui: o token vem por postMessage do painel; antes disso o hook não tem sessão.
      if (tokenRef.current && eventDataRef.current) {
        tryFinalizeRef.current?.();
      }
    }

    const handleOAuthPopup = (event) => {
      if (event.data?.type === 'META_OAUTH_CALLBACK_COMPLETE' && event.data.code) {
        authCodeRef.current = event.data.code;
        tryFinalizeRef.current?.();
      }
    };
    window.addEventListener('message', handleOAuthPopup);

    return () => {
      window.removeEventListener('message', onMsg);
      window.removeEventListener('message', handleOAuthPopup);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps -- tryFinalize estável por closure do mount
  }, [searchParams, tenantOrigin, tenantOriginNorm, tenantOk]);

  /** Resposta do tenant após POST /whatsapp_embedded_signup_finish/ (token só no painel). */
  useEffect(() => {
    if (!tenantOk) return undefined;
    const onParent = (event) => {
      if (event.origin !== tenantOriginNorm) return;
      if (event.data?.type !== MSG.FINISH_RESULT) return;
      processingRef.current = false;
      if (event.data.ok) {
        if (event.data.canal) setResultData(event.data.canal);
        setStep('success');
      } else {
        setError(event.data.message || 'Erro ao finalizar');
        setStep('error');
      }
    };
    window.addEventListener('message', onParent);
    return () => window.removeEventListener('message', onParent);
  }, [tenantOk, tenantOriginNorm]);

  /** SDK não arrancou (Brave Shields / uBlock bloqueiam facebook.com → ERR_BLOCKED_BY_CLIENT). */
  useEffect(() => {
    if (!tenantOk || step !== 'waiting' || !tokenRef.current) return undefined;
    if (window.FB && typeof window.FB.init === 'function') return undefined;

    const t = window.setTimeout(() => {
      if (sdkLoaded.current || hasLaunched.current) return;
      setStep('browser_block');
    }, 18000);
    return () => window.clearTimeout(t);
  }, [step, tenantOk]);

  useEffect(() => {
    if (!tenantOk || step !== 'waiting' || !tokenRef.current || sdkLoaded.current || hasLaunched.current)
      return;

    if (window.location.protocol !== 'https:' && window.location.hostname === 'localhost') {
      launchWhatsAppSignup();
      return;
    }

    if (window.FB && typeof window.FB.init === 'function') {
      window.FB.init({
        appId: META_APP_ID,
        cookie: true,
        xfbml: true,
        version: 'v21.0',
      });
      sdkLoaded.current = true;
      launchWhatsAppSignup();
      return;
    }

    window.fbAsyncInit = function () {
      window.FB.init({
        appId: META_APP_ID,
        cookie: true,
        xfbml: true,
        version: 'v21.0',
      });
      sdkLoaded.current = true;
      launchWhatsAppSignup();
    };

    (function (d, s, id) {
      const fjs = d.getElementsByTagName(s)[0];
      if (d.getElementById(id)) return;
      const js = d.createElement(s);
      js.id = id;
      js.async = true;
      js.src = 'https://connect.facebook.net/pt_BR/sdk.js';
      js.onerror = () => {
        if (sdkLoaded.current) return;
        setStep('browser_block');
      };
      fjs.parentNode.insertBefore(js, fjs);
    })(document, 'script', 'facebook-jssdk');
  }, [step, tenantOk]);

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
        backgroundColor: 'var(--background, #0f172a)',
        color: 'var(--foreground, #f8fafc)',
        fontFamily: 'sans-serif',
        padding: 16,
        boxSizing: 'border-box',
      }}
    >
      <div style={{ maxWidth: 480, margin: '0 auto', textAlign: 'center' }}>
        {step === 'auth_wait' && (
          <>
            <Loader2 size={40} className="animate-spin" style={{ marginBottom: 12 }} />
            <p style={{ fontSize: 14, opacity: 0.85 }}>A aguardar o painel…</p>
          </>
        )}
        {step === 'waiting' && (
          <>
            <Loader2 size={40} className="animate-spin" style={{ marginBottom: 12 }} />
            <p style={{ fontSize: 14 }}>Conclua os passos na janela da Meta.</p>
            <p style={{ fontSize: 12, opacity: 0.75, marginTop: 16, lineHeight: 1.5 }}>
              Se nada abrir: no Brave, desative o Escudo para este site; bloqueadores também bloqueiam{' '}
              <code style={{ fontSize: 11 }}>facebook.com</code>.
            </p>
            <button
              type="button"
              onClick={openOAuthFromUserClick}
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
              Abrir login da Meta numa nova janela
            </button>
          </>
        )}
        {step === 'browser_block' && (
          <>
            <AlertCircle size={44} style={{ color: '#fbbf24', marginBottom: 12 }} />
            <p style={{ fontSize: 15, fontWeight: 600, marginBottom: 8 }}>O navegador bloqueou a Meta</p>
            <p style={{ fontSize: 13, opacity: 0.9, lineHeight: 1.55, marginBottom: 16 }}>
              Erros como <code style={{ fontSize: 11 }}>net::ERR_BLOCKED_BY_CLIENT</code> vêm do Brave (Escudo),
              extensões ou bloqueadores que impedem scripts e pedidos a <code style={{ fontSize: 11 }}>facebook.com</code>.
              Desative o Escudo para <strong>connect.niohub.com.br</strong> e volte a carregar; ou abra o login direto.
            </p>
            <button
              type="button"
              onClick={openOAuthFromUserClick}
              style={{
                backgroundColor: '#1877f2',
                color: 'white',
                border: 'none',
                padding: '12px 20px',
                borderRadius: 8,
                fontWeight: 600,
                cursor: 'pointer',
                width: '100%',
                marginBottom: 10,
              }}
            >
              Abrir login da Meta (nova janela)
            </button>
            <button
              type="button"
              onClick={() => window.location.reload()}
              style={{
                background: 'transparent',
                color: 'var(--foreground, #f8fafc)',
                border: '1px solid rgba(255,255,255,0.25)',
                padding: '10px 16px',
                borderRadius: 8,
                cursor: 'pointer',
                width: '100%',
                fontSize: 13,
              }}
            >
              Recarregar esta página
            </button>
          </>
        )}
        {step === 'processing' && (
          <>
            <Loader2 size={40} className="animate-spin" style={{ marginBottom: 12 }} />
            <p>A configurar o canal…</p>
          </>
        )}
        {step === 'success' && (
          <>
            <CheckCircle2 size={48} style={{ color: '#22c55e', marginBottom: 12 }} />
            <p>Concluído.</p>
            {resultData?.phone_number && (
              <p style={{ fontSize: 13, opacity: 0.8 }}>Número: {resultData.phone_number}</p>
            )}
          </>
        )}
        {step === 'error' && (
          <>
            <AlertCircle size={48} style={{ color: '#ef4444', marginBottom: 12 }} />
            <p>{error}</p>
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
