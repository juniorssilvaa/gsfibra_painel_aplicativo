import React, { useState, useEffect, useRef } from 'react';
import { useSearchParams } from 'react-router-dom';
import { Loader2, CheckCircle2, AlertCircle } from 'lucide-react';
import { META_APP_ID, META_CONFIG_ID } from '../config/metaWhatsApp';

const MSG = {
  READY: 'META_CONNECT_INNER_READY',
  AUTH: 'META_CONNECT_AUTH',
  SUCCESS: 'META_CONNECT_SUCCESS',
  ERROR: 'META_CONNECT_ERROR',
  FINISH_REQUEST: 'META_CONNECT_FINISH_REQUEST',
  FINISH_RESULT: 'META_CONNECT_FINISH_RESULT',
};

/**
 * Versão do MetaConnectInner para o Superadmin.
 * Servido em: <domínio-superadmin>/app/meta/connect-inner
 *
 * Diferenças do connect.niohub.com.br:
 * - state = billing_superadmin_1 (para o backend reconhecer o fluxo do superadmin)
 * - tenantOrigin pode ser o próprio domínio do superadmin (sem validação de subdomínio do provedor)
 * - Comunica via postMessage com MetaFinalizingSuperadmin.jsx no mesmo domínio
 */
export default function MetaConnectInnerSuperadmin() {
  const [searchParams] = useSearchParams();
  const tenantOrigin = (searchParams.get('tenant_origin') || '').trim().replace(/\/+$/, '');
  const tenantOriginNorm = React.useMemo(() => {
    try {
      return new URL(tenantOrigin).origin;
    } catch {
      return tenantOrigin;
    }
  }, [tenantOrigin]);

  // Para o Superadmin, o tenant_origin é o próprio domínio do superadmin (ou localhost em dev)
  const tenantOk = React.useMemo(() => {
    if (!tenantOrigin) return false;
    try {
      const u = new URL(tenantOrigin);
      const host = u.hostname;
      // Aceitar localhost em dev
      if (host === 'localhost' || host === '127.0.0.1') return true;
      // Aceitar qualquer subdomínio niohub.com.br em produção
      if (host.endsWith('.niohub.com.br') || host === 'niohub.com.br') return true;
      return false;
    } catch {
      return false;
    }
  }, [tenantOrigin]);

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
            providerId: '1', // placeholder para o superadmin
            channelId: 'billing_superadmin',
            payload: fullPayloadData,
          },
          tenantOriginNorm
        );
      } catch (err) {
        processingRef.current = false;
        const msg = err.message || 'Erro ao enviar dados ao painel superadmin';
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

    // Fallback: finalizar diretamente (quando não há bridge, ex.: aba aberta diretamente)
    const token = tokenRef.current;
    if (!token) {
      setError('Token não recebido do painel superadmin.');
      setStep('error');
      return;
    }

    processingRef.current = true;
    setStep('processing');

    try {
      const response = await fetch('/api/system-config/billing-whatsapp/embedded-signup-finish/', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Token ${token}`,
        },
        body: JSON.stringify({ waba_id: String(wabaId).trim(), code }),
      });
      const data = await response.json();
      if (data.success) {
        setResultData(data.billing);
        setStep('success');
        const br = window.opener || (window.parent !== window ? window.parent : null);
        if (br && tenantOk) {
          br.postMessage({ type: MSG.SUCCESS, canal: data.billing }, tenantOriginNorm);
        }
      } else {
        throw new Error(data.error || 'Erro ao processar integração no superadmin');
      }
    } catch (err) {
      const msg = err.message || 'Erro';
      setError(msg);
      setStep('error');
      processingRef.current = false;
      const brErr = window.opener || (window.parent !== window ? window.parent : null);
      if (brErr && tenantOk) {
        brErr.postMessage({ type: MSG.ERROR, message: msg }, tenantOriginNorm);
      }
    }
  }

  tryFinalizeRef.current = tryFinalize;

  /**
   * Constrói a URL OAuth da Meta para o Superadmin.
   * Usa state=billing_superadmin_1 para que o meta_callback do backend
   * reconheça o fluxo e redirecione para /app/meta/finalizando-superadmin.
   *
   * redirect_uri aponta para https://api.niohub.com.br/api/auth/facebook/callback/
   * (mesmo endpoint do provedor, mas o backend reconhece pelo state).
   */
  function buildMetaOAuthUrl() {
    // redirect_uri registrada no Meta App Dashboard (mesmo do provedor)
    const redirectUri = encodeURIComponent('https://api.niohub.com.br/api/auth/facebook/callback/');
    const extras = encodeURIComponent(
      JSON.stringify({
        featureType: 'whatsapp_business_app_onboarding',
        sessionInfoVersion: '3',
      })
    );
    // state com prefixo billing_superadmin_ para o backend reconhecer e redirecionar corretamente
    const stateStr = `billing_superadmin_1${window.location.protocol !== 'https:' ? '_local' : ''}`;
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
      'MetaSignupSuperadmin',
      `width=${width},height=${height},left=${left},top=${top},scrollbars=yes,status=yes`
    );
  }

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
      setError('Origem do superadmin inválida.');
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

    // Avisar o MetaFinalizingSuperadmin que este iframe está pronto
    const br = window.opener || (window.parent !== window ? window.parent : null);
    if (br) {
      setTimeout(() => {
        br.postMessage({ type: MSG.READY }, tenantOriginNorm);
      }, 0);
    }

    // Se o código OAuth já estiver na URL (redirect do meta_callback)
    const codeFromUrl = searchParams.get('code');
    if (codeFromUrl && !authCodeRef.current) {
      authCodeRef.current = codeFromUrl;
      if (tokenRef.current && eventDataRef.current) {
        tryFinalizeRef.current?.();
      }
    }

    // Ouvir postMessage do popup quando o meta_callback redirecionar com META_OAUTH_CALLBACK_COMPLETE
    const handleOAuthPopup = (event) => {
      if (event.data?.type === 'META_OAUTH_CALLBACK_COMPLETE' && event.data.code) {
        authCodeRef.current = event.data.code;
        tryFinalizeRef.current?.();
      }
    };
    window.addEventListener('message', handleOAuthPopup);

    // Ouvir eventos da Meta (FINISH_WHATSAPP_BUSINESS_APP_ONBOARDING)
    const handleMetaEvent = (event) => {
      if (event.origin !== 'https://www.facebook.com') return;
      let payload = event.data;
      if (typeof payload === 'string') {
        try { payload = JSON.parse(payload); } catch { return; }
      }
      if (!payload || typeof payload !== 'object') return;
      if (payload.event !== 'FINISH_WHATSAPP_BUSINESS_APP_ONBOARDING') return;
      const wabaId = payload.data?.waba_id;
      const phoneNumberId = payload.data?.phone_number_id;
      if (!wabaId || !phoneNumberId) return;
      handleOnFinish(wabaId, {
        waba_id: wabaId,
        phone_number_id: phoneNumberId,
        raw: payload,
      });
    };
    window.addEventListener('message', handleMetaEvent);

    return () => {
      window.removeEventListener('message', onMsg);
      window.removeEventListener('message', handleOAuthPopup);
      window.removeEventListener('message', handleMetaEvent);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [searchParams, tenantOrigin, tenantOriginNorm, tenantOk]);

  // Ouvir FINISH_RESULT do MetaFinalizingSuperadmin (resposta do POST ao backend)
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
        setError(event.data.message || 'Erro ao finalizar integração');
        setStep('error');
      }
    };
    window.addEventListener('message', onParent);
    return () => window.removeEventListener('message', onParent);
  }, [tenantOk, tenantOriginNorm]);

  // Detectar bloqueio de browser (Brave Shields, uBlock, etc.)
  useEffect(() => {
    if (!tenantOk || step !== 'waiting' || !tokenRef.current) return undefined;
    if (window.FB && typeof window.FB.init === 'function') return undefined;

    const t = window.setTimeout(() => {
      if (sdkLoaded.current || hasLaunched.current) return;
      setStep('browser_block');
    }, 18000);
    return () => window.clearTimeout(t);
  }, [step, tenantOk]);

  // Carregar SDK da Meta e iniciar o fluxo
  useEffect(() => {
    if (!tenantOk || step !== 'waiting' || !tokenRef.current || sdkLoaded.current || hasLaunched.current)
      return;

    // Em desenvolvimento (localhost sem HTTPS), usar popup direto
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
    })(document, 'script', 'facebook-jssdk-superadmin');
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [step, tenantOk]);

  if (!tenantOk) {
    return (
      <div style={{ padding: 24, fontFamily: 'sans-serif', color: '#b91c1c' }}>
        {error || 'tenant_origin inválido para o Superadmin.'}
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
            <p style={{ fontSize: 14, opacity: 0.85 }}>Aguardando painel do Superadmin…</p>
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
              extensões ou bloqueadores que impedem scripts e pedidos a{' '}
              <code style={{ fontSize: 11 }}>facebook.com</code>.
              Desative o Escudo para este domínio e volte a carregar; ou abra o login direto.
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
                color: '#f8fafc',
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
            <p>Configurando canal de cobrança…</p>
          </>
        )}
        {step === 'success' && (
          <>
            <CheckCircle2 size={48} style={{ color: '#22c55e', marginBottom: 12 }} />
            <p>Canal de cobrança configurado com sucesso!</p>
            {resultData?.display_phone_number && (
              <p style={{ fontSize: 13, opacity: 0.8 }}>Número: {resultData.display_phone_number}</p>
            )}
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
                backgroundColor: '#1877f2',
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
