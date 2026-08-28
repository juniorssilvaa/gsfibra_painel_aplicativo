import React, { useState, useEffect, useRef } from 'react';
import { useSearchParams, useNavigate } from 'react-router-dom';
import { Loader2, CheckCircle2, AlertCircle } from 'lucide-react';
import useMetaEmbeddedSignupListener from '../hooks/useMetaEmbeddedSignupListener.jsx';
import { getBackendAbsoluteBase } from '../utils/apiBaseUrl';
import {
  getMetaConnectOrigin,
  shouldUseMetaConnectIframe,
  META_CONNECT_IFRAME_CACHE_BUSTER,
} from '../utils/metaConnect';
import { META_APP_ID, META_CONFIG_ID } from '../config/metaWhatsApp';

const META_CONNECT_MSG = {
  READY: 'META_CONNECT_INNER_READY',
  AUTH: 'META_CONNECT_AUTH',
  SUCCESS: 'META_CONNECT_SUCCESS',
  ERROR: 'META_CONNECT_ERROR',
  /** iframe connect → tenant: pedido para concluir o signup (API com token só no tenant) */
  FINISH_REQUEST: 'META_CONNECT_FINISH_REQUEST',
  /** tenant → iframe: resultado do POST /whatsapp_embedded_signup_finish/ */
  FINISH_RESULT: 'META_CONNECT_FINISH_RESULT',
};

/**
 * SDK Meta em iframe oculto (origem connect). Evita popup-in-popup; o diálogo da Meta abre à parte.
 * O iframe não é exibido — só mantém o bridge de token e o FB.login.
 */
function MetaFinalizingWithConnectIframe() {
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const iframeRef = useRef(null);
  const [iframeKey, setIframeKey] = useState(0);
  const rawProviderId = searchParams.get('provider_id');
  const user = JSON.parse(localStorage.getItem('user') || '{}');
  const userProviderId = user.provedor_id || user.provedor?.id;
  
  const providerId = (rawProviderId && rawProviderId !== 'null' && rawProviderId !== 'undefined') 
    ? rawProviderId 
    : (userProviderId || '1');
  const channelId = searchParams.get('channel_id') || '';

  const [step, setStep] = useState('waiting');
  const [error, setError] = useState(null);
  const [resultData, setResultData] = useState(null);
  const finishInFlightRef = useRef(false);

  const { sendFinishToBackend } = useMetaEmbeddedSignupListener({
    providerId,
    debug: false,
    apiOrigin: null,
  });

  const connectOrigin = getMetaConnectOrigin();
  const connectOriginNorm = React.useMemo(
    () => (connectOrigin ? new URL(connectOrigin).origin : ''),
    [connectOrigin]
  );

  const connectInnerUrl = React.useMemo(() => {
    if (!connectOrigin) return '';
    const u = new URL('/app/meta/connect-inner', connectOrigin);
    u.searchParams.set('tenant_origin', window.location.origin);
    u.searchParams.set('provider_id', providerId);
    if (channelId) u.searchParams.set('channel_id', channelId);
    u.searchParams.set('niohub_cb', META_CONNECT_IFRAME_CACHE_BUSTER);
    return u.toString();
  }, [channelId, connectOrigin, providerId]);

  const sendAuthToIframe = React.useCallback(() => {
    const cw = iframeRef.current?.contentWindow;
    const token = localStorage.getItem('auth_token') || localStorage.getItem('token');
    if (!cw || !token || !connectOriginNorm) return;
    try {
      cw.postMessage({ type: META_CONNECT_MSG.AUTH, token }, connectOriginNorm);
    } catch (_) {
      /* ignore */
    }
  }, [connectOriginNorm]);

  const scheduleAuthToIframe = React.useCallback(() => {
    sendAuthToIframe();
    setTimeout(sendAuthToIframe, 200);
    setTimeout(sendAuthToIframe, 800);
    setTimeout(sendAuthToIframe, 2000);
    setTimeout(sendAuthToIframe, 4000);
  }, [sendAuthToIframe]);

  useEffect(() => {
    if (!connectOrigin) return undefined;

    const postFinishResultToIframe = (payload) => {
      const iw = iframeRef.current?.contentWindow;
      if (!iw) return;
      try {
        iw.postMessage({ type: META_CONNECT_MSG.FINISH_RESULT, ...payload }, connectOriginNorm);
      } catch (_) {
        /* ignore */
      }
    };

    const onMsg = (e) => {
      if (e.origin !== connectOriginNorm) return;
      if (e.data?.type === META_CONNECT_MSG.READY) {
        const token = localStorage.getItem('auth_token') || localStorage.getItem('token');
        if (e.source && token) {
          e.source.postMessage({ type: META_CONNECT_MSG.AUTH, token }, connectOriginNorm);
        }
      }
      if (e.data?.type === META_CONNECT_MSG.SUCCESS) {
        setResultData(e.data.canal);
        setStep('success');
      }
      if (e.data?.type === META_CONNECT_MSG.ERROR) {
        setError(e.data.message || 'Erro no fluxo Meta');
        setStep('error');
      }
      if (e.data?.type === META_CONNECT_MSG.FINISH_REQUEST) {
        if (e.source !== iframeRef.current?.contentWindow) return;
        if (finishInFlightRef.current) return;
        const { wabaId, providerId: reqPid, channelId: reqCid, payload } = e.data;
        if (!wabaId || !payload) return;
        finishInFlightRef.current = true;
        void (async () => {
          try {
            const response = await sendFinishToBackend(wabaId, reqPid || providerId, {
              payload,
              channelId: reqCid || channelId || undefined,
            });
            if (response.success) {
              postFinishResultToIframe({ ok: true, canal: response.canal });
              setResultData(response.canal);
              setStep('success');
            } else {
              const msg = response.error || 'Erro ao processar integração';
              postFinishResultToIframe({ ok: false, message: msg });
              setError(msg);
              setStep('error');
            }
          } catch (err) {
            const msg = err.message || 'Erro ao finalizar integração Meta';
            postFinishResultToIframe({ ok: false, message: msg });
            setError(msg);
            setStep('error');
          } finally {
            finishInFlightRef.current = false;
          }
        })();
      }
    };

    window.addEventListener('message', onMsg);
    return () => window.removeEventListener('message', onMsg);
  }, [channelId, connectOrigin, connectOriginNorm, providerId, sendFinishToBackend]);

  if (!connectOrigin || !connectInnerUrl) {
    return (
      <div style={{ padding: 24 }}>
        <AlertCircle className="inline" /> VITE_META_CONNECT_ORIGIN não configurado.
      </div>
    );
  }

  return (
    <div
      style={{
        position: 'relative',
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        justifyContent: 'center',
        minHeight: '100vh',
        backgroundColor: 'var(--background)',
        color: 'var(--foreground)',
        fontFamily: 'sans-serif',
        padding: '20px',
      }}
    >
      {step === 'waiting' && (
        <>
          <div
            style={{
              backgroundColor: 'var(--card)',
              padding: '28px',
              borderRadius: '12px',
              boxShadow: '0 10px 25px -5px rgba(0, 0, 0, 0.3)',
              maxWidth: '560px',
              width: '100%',
              textAlign: 'center',
              border: '1px solid var(--border)',
            }}
          >
            <div style={{ marginBottom: '16px', display: 'flex', justifyContent: 'center' }}>
              <Loader2 size={48} className="animate-spin" style={{ color: 'var(--primary)' }} />
            </div>
            <h2 style={{ fontSize: '22px', fontWeight: 'bold', marginBottom: '12px' }}>Aguardando finalização...</h2>
            <p style={{ color: 'var(--muted-foreground)', lineHeight: '1.6', marginBottom: '12px' }}>
              O fluxo seguro corre em segundo plano em{' '}
              <strong>{connectOrigin.replace(/^https?:\/\//, '')}</strong>. Quando a janela da Meta abrir, conclua o
              cadastro incorporado lá — esta página atualiza sozinha ao terminar.
            </p>
            <p style={{ color: 'var(--muted-foreground)', fontSize: 12, lineHeight: 1.5, marginBottom: '12px' }}>
              Brave / bloqueadores: se a consola mostrar <code style={{ fontSize: 11 }}>ERR_BLOCKED_BY_CLIENT</code> em
              pedidos a facebook.com, desative o Escudo (ou exceções) para este domínio e para{' '}
              {connectOrigin.replace(/^https?:\/\//, '')}.
            </p>
            <button
              type="button"
              onClick={() => setIframeKey((k) => k + 1)}
              style={{
                color: 'var(--primary)',
                background: 'none',
                border: 'none',
                cursor: 'pointer',
                textDecoration: 'underline',
                fontSize: 13,
              }}
            >
              Recarregar fluxo Meta
            </button>
          </div>
          {/* iframe invisível: mesmo comportamento (SDK + postMessage), sem caixa branca na UI */}
          <div
            aria-hidden="true"
            style={{
              position: 'absolute',
              width: 1,
              height: 1,
              margin: -1,
              padding: 0,
              border: 0,
              overflow: 'hidden',
              clipPath: 'inset(50%)',
              whiteSpace: 'nowrap',
            }}
          >
            <iframe
              key={iframeKey}
              ref={iframeRef}
              title="Meta connect (background)"
              src={connectInnerUrl}
              onLoad={scheduleAuthToIframe}
              style={{ width: 1, height: 1, border: 'none', display: 'block', opacity: 0 }}
              sandbox="allow-scripts allow-same-origin allow-forms allow-popups allow-popups-to-escape-sandbox allow-top-navigation-by-user-activation"
            />
          </div>
        </>
      )}

      {step === 'success' && (
        <div style={{ marginTop: 24, maxWidth: 560, width: '100%', textAlign: 'center' }}>
          <CheckCircle2 size={64} style={{ color: '#22c55e', margin: '0 auto 16px' }} />
          <h2 style={{ fontSize: '24px', fontWeight: 'bold', color: '#22c55e', marginBottom: 8 }}>Tudo pronto</h2>
          <p style={{ color: 'var(--muted-foreground)', marginBottom: 20 }}>
            WhatsApp Oficial ligado.
            {resultData?.phone_number && ` Número: ${resultData.phone_number}`}
          </p>
          <button
            type="button"
            onClick={() => navigate(`/app/accounts/${providerId}/integracoes`)}
            style={{
              backgroundColor: '#22c55e',
              color: 'white',
              border: 'none',
              padding: '14px 24px',
              borderRadius: '6px',
              fontWeight: 'bold',
              width: '100%',
            }}
          >
            Voltar para Integrações
          </button>
        </div>
      )}

      {step === 'error' && (
        <div style={{ marginTop: 24, maxWidth: 560, width: '100%', textAlign: 'center' }}>
          <AlertCircle size={48} style={{ color: '#ef4444', marginBottom: 12 }} />
          <p style={{ color: '#f87171' }}>{error}</p>
          <button
            type="button"
            onClick={() => window.location.reload()}
            style={{ marginTop: 12, backgroundColor: '#1877f2', color: 'white', border: 'none', padding: '12px 24px', borderRadius: 6 }}
          >
            Recarregar
          </button>
        </div>
      )}

      <style>{`
        @keyframes spin { from { transform: rotate(0deg); } to { transform: rotate(360deg); } }
        .animate-spin { animation: spin 1s linear infinite; }
      `}</style>
    </div>
  );
}

/** Fluxo legacy: SDK no mesmo host que o painel. */
function MetaFinalizingInline() {
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const rawProviderId = searchParams.get('provider_id');
  const user = JSON.parse(localStorage.getItem('user') || '{}');
  const userProviderId = user.provedor_id || user.provedor?.id;
  
  const providerId = (rawProviderId && rawProviderId !== 'null' && rawProviderId !== 'undefined') 
    ? rawProviderId 
    : (userProviderId || '1');
  const channelId = searchParams.get('channel_id');

  const [step, setStep] = useState('waiting');
  const [error, setError] = useState(null);
  const [resultData, setResultData] = useState(null);
  const authCodeRef = useRef(null);
  const eventDataRef = useRef(null);
  const hasLaunched = useRef(false);
  const sdkLoaded = useRef(false);
  const processingRef = useRef(false);

  const hasToken = localStorage.getItem('auth_token') || localStorage.getItem('token');

  const { sendFinishToBackend } = useMetaEmbeddedSignupListener({
    providerId,
    debug: true,
    onFinish: hasToken ? handleOnFinish : undefined,
  });

  function handleOnFinish(wabaId, eventData) {
    eventDataRef.current = { wabaId, ...eventData };
    tryFinalize();
  }

  async function tryFinalize() {
    const token = localStorage.getItem('auth_token') || localStorage.getItem('token');
    if (!token) {
      setError('Token não encontrado. Faça login novamente.');
      setStep('error');
      return;
    }

    if (!eventDataRef.current || !authCodeRef.current) {
      return;
    }

    if (processingRef.current || step === 'success') return;

    const { wabaId, ...eventData } = eventDataRef.current;
    const code = authCodeRef.current;

    processingRef.current = true;
    setStep('processing');

    try {
      const fullPayloadData = { ...eventData, code };

      const response = await sendFinishToBackend(wabaId, providerId, { payload: fullPayloadData, channelId });

      if (response.success) {
        setResultData(response.canal);
        setStep('success');
      } else {
        throw new Error(response.error || 'Erro ao processar integração');
      }
    } catch (err) {
      setError(err.message);
      setStep('error');
      processingRef.current = false;
    }
  }

  function launchWhatsAppSignup() {
    if (hasLaunched.current) return;
    hasLaunched.current = true;
    const BACKEND_URL = getBackendAbsoluteBase();
    const redirectUri = encodeURIComponent(`${BACKEND_URL}/api/auth/facebook/callback/`);

    const extras = encodeURIComponent(
      JSON.stringify({
        featureType: 'whatsapp_business_app_onboarding',
        sessionInfoVersion: '3',
      })
    );
    const stateStr = `provider_${providerId}${window.location.protocol !== 'https:' ? '_local' : ''}`;
    const oauthUrl = `https://www.facebook.com/v21.0/dialog/oauth?client_id=${META_APP_ID}&config_id=${META_CONFIG_ID}&response_type=code&redirect_uri=${redirectUri}&state=${stateStr}&extras=${extras}`;

    if (window.location.protocol === 'https:' && window.FB) {
      window.FB.login(
        (response) => {
          if (response.authResponse?.code) {
            authCodeRef.current = response.authResponse.code;
            tryFinalize();
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
      const width = 600;
      const height = 700;
      const left = window.screen.width / 2 - width / 2;
      const top = window.screen.height / 2 - height / 2;
      window.open(oauthUrl, 'MetaSignup', `width=${width},height=${height},left=${left},top=${top},scrollbars=yes,status=yes`);
    }
  }

  useEffect(() => {
    const codeFromUrl = searchParams.get('code');
    if (codeFromUrl && !authCodeRef.current) {
      authCodeRef.current = codeFromUrl;
      tryFinalize();
    }

    const handleCallbackMessage = (event) => {
      if (event.data?.type === 'META_OAUTH_CALLBACK_COMPLETE' && event.data.code) {
        authCodeRef.current = event.data.code;
        tryFinalize();
      }
    };
    window.addEventListener('message', handleCallbackMessage);

    const initAndLaunch = () => {
      if (sdkLoaded.current || hasLaunched.current) return;

      if (window.location.protocol !== 'https:' && window.location.hostname === 'localhost') {
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
        js.src = 'https://connect.facebook.net/pt_BR/sdk.js';
        fjs.parentNode.insertBefore(js, fjs);
      })(document, 'script', 'facebook-jssdk');
    };

    const timer = setTimeout(initAndLaunch, 500);
    return () => {
      clearTimeout(timer);
      window.removeEventListener('message', handleCallbackMessage);
    };
  }, [searchParams]);

  return (
    <div
      style={{
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        justifyContent: 'center',
        minHeight: '100vh',
        backgroundColor: 'var(--background)',
        color: 'var(--foreground)',
        fontFamily: 'sans-serif',
        padding: '20px',
      }}
    >
      <div
        style={{
          backgroundColor: 'var(--card)',
          padding: '40px',
          borderRadius: '12px',
          boxShadow: '0 10px 25px -5px rgba(0, 0, 0, 0.3)',
          maxWidth: '550px',
          width: '100%',
          textAlign: 'center',
          border: '1px solid var(--border)',
        }}
      >
        {step === 'waiting' && (
          <>
            <div style={{ marginBottom: '20px', display: 'flex', justifyContent: 'center' }}>
              <Loader2 size={60} className="animate-spin" style={{ color: 'var(--primary)' }} />
            </div>
            <h2 style={{ fontSize: '24px', fontWeight: 'bold', marginBottom: '16px' }}>Aguardando finalização...</h2>
            <p style={{ color: 'var(--muted-foreground)', lineHeight: '1.6', marginBottom: '24px' }}>
              Por favor, conclua os passos na janela da Meta que foi aberta. Esta página atualizará automaticamente ao
              terminar.
            </p>
            <div
              style={{
                fontSize: '12px',
                color: 'var(--muted-foreground)',
                borderTop: '1px solid var(--border)',
                paddingTop: '16px',
              }}
            >
              Janela não abriu?{' '}
              <button
                type="button"
                onClick={() => {
                  hasLaunched.current = false;
                  launchWhatsAppSignup();
                }}
                style={{
                  color: 'var(--primary)',
                  background: 'none',
                  border: 'none',
                  cursor: 'pointer',
                  textDecoration: 'underline',
                }}
              >
                Clique aqui para tentar novamente
              </button>
            </div>
          </>
        )}

        {step === 'processing' && (
          <>
            <Loader2 size={60} className="animate-spin" style={{ color: 'var(--nc-accent, #fbbf24)', margin: '0 auto 20px' }} />
            <h2 style={{ fontSize: '24px', fontWeight: 'bold', marginBottom: '16px' }}>Configurando Canal...</h2>
            <p style={{ color: 'var(--muted-foreground)' }}>Recebemos os dados da Meta e estamos vinculando sua conta.</p>
          </>
        )}

        {step === 'success' && (
          <>
            <CheckCircle2 size={64} style={{ color: '#22c55e', margin: '0 auto 20px' }} />
            <h2 style={{ fontSize: '28px', fontWeight: 'bold', marginBottom: '8px', color: '#22c55e' }}>Tudo Pronto!</h2>
            <p style={{ color: 'var(--muted-foreground)', marginBottom: '24px' }}>Seu WhatsApp Oficial foi conectado com sucesso.</p>

            <div
              style={{
                textAlign: 'left',
                backgroundColor: 'var(--background)',
                padding: '24px',
                borderRadius: '8px',
                fontSize: '15px',
                marginBottom: '32px',
                border: '1px solid var(--border)',
              }}
            >
              <div>
                <strong style={{ color: 'var(--muted-foreground)', width: '140px', display: 'inline-block' }}>Número:</strong>{' '}
                <span style={{ color: 'var(--primary)', fontWeight: 'bold' }}>{resultData?.phone_number}</span>
              </div>
              <div>
                <strong style={{ color: 'var(--muted-foreground)', width: '140px', display: 'inline-block' }}>Status:</strong>{' '}
                <span style={{ color: 'var(--nc-success, #22c55e)' }}>{resultData?.status?.toUpperCase()}</span>
              </div>
              <div>
                <strong style={{ color: 'var(--muted-foreground)', width: '140px', display: 'inline-block' }}>WABA ID:</strong>{' '}
                {resultData?.waba_id}
              </div>
            </div>

            <button
              type="button"
              onClick={() => navigate(`/app/accounts/${providerId}/integracoes`)}
              style={{
                backgroundColor: '#22c55e',
                color: 'white',
                border: 'none',
                padding: '14px 24px',
                borderRadius: '6px',
                fontWeight: 'bold',
                width: '100%',
              }}
            >
              Voltar para Integrações
            </button>
          </>
        )}

        {step === 'error' && (
          <>
            <AlertCircle size={60} style={{ color: '#ef4444', margin: '0 auto 20px' }} />
            <h2 style={{ fontSize: '24px', fontWeight: 'bold', marginBottom: '16px', color: '#ef4444' }}>Houve um problema</h2>
            <div
              style={{
                backgroundColor: 'rgba(239, 68, 68, 0.1)',
                padding: '16px',
                borderRadius: '8px',
                color: '#f87171',
                marginBottom: '24px',
              }}
            >
              {error}
            </div>
            <button
              type="button"
              onClick={() => {
                hasLaunched.current = false;
                setStep('waiting');
                launchWhatsAppSignup();
              }}
              style={{ backgroundColor: '#1877f2', color: 'white', border: 'none', padding: '12px 24px', borderRadius: '6px', width: '100%' }}
            >
              Tentar Novamente
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

export default function MetaFinalizing() {
  return shouldUseMetaConnectIframe() ? <MetaFinalizingWithConnectIframe /> : <MetaFinalizingInline />;
}
