import React, { useState, useEffect, useRef, useCallback } from 'react';
import { useSearchParams, useNavigate } from 'react-router-dom';
import { Loader2, CheckCircle2, AlertCircle, ExternalLink } from 'lucide-react';
import useMetaEmbeddedSignupListener from '../hooks/useMetaEmbeddedSignupListener.js';
import { getApiBaseUrl } from '../utils/apiBaseUrl';
import axios from 'axios';

const MetaFinalizing = () => {
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const providerId = searchParams.get('provider_id') || '1';
  const channelId = searchParams.get('channel_id');

  const [step, setStep] = useState('waiting');
  const [error, setError] = useState(null);
  const [resultData, setResultData] = useState(null);
  const authCodeRef = useRef(null);
  const eventDataRef = useRef(null);
  const hasLaunched = useRef(false);
  const sdkLoaded = useRef(false);
  const processingRef = useRef(false);

  // IDs da Meta
  const META_APP_ID = '713538217881661';
  const CONFIG_ID = '1888449245359692';

  // Verificar se há token antes de usar o hook
  const hasToken = localStorage.getItem('auth_token') || localStorage.getItem('token');

  // 1. O hook usa as funções declaradas abaixo (hoisted)
  const { sendFinishToBackend } = useMetaEmbeddedSignupListener({
    providerId,
    debug: true,
    onFinish: hasToken ? handleOnFinish : undefined
  });

  // 2. Funções declaradas (hoisted)
  function handleOnFinish(wabaId, eventData) {
    eventDataRef.current = { wabaId, ...eventData };
    tryFinalize();
  }

  async function tryFinalize() {
    // Verificar se há token antes de prosseguir
    const token = localStorage.getItem('auth_token') || localStorage.getItem('token');
    if (!token) {
      setError('Token não encontrado. Faça login novamente.');
      setStep('error');
      return;
    }

    // Só prosseguimos se tivermos AMBOS: o evento FINISH (waba_id) e o CODE do OAuth
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

  const launchWhatsAppSignup = () => {
    if (hasLaunched.current) return;
    hasLaunched.current = true;
    // redirect_uri deve ser a URL do backend onde a Meta redireciona com o code (deve estar no Meta App Dashboard)
    const baseUrl = getApiBaseUrl() || import.meta.env.VITE_API_URL || 'https://api.niohub.com.br';
    const BACKEND_URL = baseUrl.replace(/\/+$/, '');
    const redirectUri = encodeURIComponent(`${BACKEND_URL}/api/auth/facebook/callback/`);

    const extras = encodeURIComponent(JSON.stringify({
      featureType: "whatsapp_business_app_onboarding",
      sessionInfoVersion: "3"
    }));
    const stateStr = `provider_${providerId}${window.location.protocol !== 'https:' ? '_local' : ''}`;
    const oauthUrl = `https://www.facebook.com/v21.0/dialog/oauth?client_id=${META_APP_ID}&config_id=${CONFIG_ID}&response_type=code&redirect_uri=${redirectUri}&state=${stateStr}&extras=${extras}`;

    if (window.location.protocol === 'https:' && window.FB) {
      window.FB.login((response) => {
        if (response.authResponse?.code) {
          authCodeRef.current = response.authResponse.code;
          tryFinalize(); // 🆕 Tenta finalizar agora que temos o code
        }
      }, {
        config_id: CONFIG_ID,
        response_type: 'code',
        override_default_response_type: true,
        extras: {
          setup: {},
          featureType: "whatsapp_business_app_onboarding",
          sessionInfoVersion: "3"
        }
      });
    } else {
      const width = 600;
      const height = 700;
      const left = window.screen.width / 2 - width / 2;
      const top = window.screen.height / 2 - height / 2;
      window.open(oauthUrl, 'MetaSignup', `width=${width},height=${height},left=${left},top=${top},scrollbars=yes,status=yes`);
    }
  };

  useEffect(() => {
    // 1. Tentar capturar o code da URL
    const codeFromUrl = searchParams.get('code');
    if (codeFromUrl && !authCodeRef.current) {
      authCodeRef.current = codeFromUrl;
      tryFinalize();
    }

    // 2. Escutar mensagem do popup caso ele tenha sido redirecionado para o callback do backend
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
          version: 'v21.0'
        });
        sdkLoaded.current = true;
        launchWhatsAppSignup();
      };

      (function (d, s, id) {
        var js, fjs = d.getElementsByTagName(s)[0];
        if (d.getElementById(id)) return;
        js = d.createElement(s); js.id = id;
        js.src = "https://connect.facebook.net/pt_BR/sdk.js";
        fjs.parentNode.insertBefore(js, fjs);
      }(document, 'script', 'facebook-jssdk'));
    };

    const timer = setTimeout(initAndLaunch, 500);
    return () => {
      clearTimeout(timer);
      window.removeEventListener('message', handleCallbackMessage);
    };
  }, [searchParams]); // Adicionar searchParams como dependência

  return (
    <div style={{
      display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center',
      minHeight: '100vh', backgroundColor: 'var(--background)', color: 'var(--foreground)', fontFamily: 'sans-serif', padding: '20px'
    }}>
      <div style={{
        backgroundColor: 'var(--card)', padding: '40px', borderRadius: '12px',
        boxShadow: '0 10px 25px -5px rgba(0, 0, 0, 0.3)', maxWidth: '550px', width: '100%', textAlign: 'center',
        border: '1px solid var(--border)'
      }}>

        {step === 'waiting' && (
          <>
            <div style={{ marginBottom: '20px', display: 'flex', justifyContent: 'center' }}>
              <Loader2 size={60} className="animate-spin" style={{ color: 'var(--primary)' }} />
            </div>
            <h2 style={{ fontSize: '24px', fontWeight: 'bold', marginBottom: '16px' }}>
              Aguardando finalização...
            </h2>
            <p style={{ color: 'var(--muted-foreground)', lineHeight: '1.6', marginBottom: '24px' }}>
              Por favor, conclua os passos na janela da Meta que foi aberta.
              Esta página atualizará automaticamente ao terminar.
            </p>
            <div style={{ fontSize: '12px', color: 'var(--muted-foreground)', borderTop: '1px solid var(--border)', paddingTop: '16px' }}>
              Janela não abriu? <button onClick={() => { hasLaunched.current = false; launchWhatsAppSignup(); }} style={{ color: 'var(--primary)', background: 'none', border: 'none', cursor: 'pointer', textDecoration: 'underline' }}>Clique aqui para tentar novamente</button>
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

            <div style={{ textAlign: 'left', backgroundColor: 'var(--background)', padding: '24px', borderRadius: '8px', fontSize: '15px', marginBottom: '32px', border: '1px solid var(--border)' }}>
              <div><strong style={{ color: 'var(--muted-foreground)', width: '140px', display: 'inline-block' }}>Número:</strong> <span style={{ color: 'var(--primary)', fontWeight: 'bold' }}>{resultData?.phone_number}</span></div>
              <div><strong style={{ color: 'var(--muted-foreground)', width: '140px', display: 'inline-block' }}>Status:</strong> <span style={{ color: 'var(--nc-success, #22c55e)' }}>{resultData?.status?.toUpperCase()}</span></div>
              <div><strong style={{ color: 'var(--muted-foreground)', width: '140px', display: 'inline-block' }}>WABA ID:</strong> {resultData?.waba_id}</div>
            </div>

            <button onClick={() => navigate(`/app/accounts/${providerId}/integracoes`)} style={{ backgroundColor: '#22c55e', color: 'white', border: 'none', padding: '14px 24px', borderRadius: '6px', fontWeight: 'bold', width: '100%' }}>
              Voltar para Integrações
            </button>
          </>
        )}

        {step === 'error' && (
          <>
            <AlertCircle size={60} style={{ color: '#ef4444', margin: '0 auto 20px' }} />
            <h2 style={{ fontSize: '24px', fontWeight: 'bold', marginBottom: '16px', color: '#ef4444' }}>Houve um problema</h2>
            <div style={{ backgroundColor: 'rgba(239, 68, 68, 0.1)', padding: '16px', borderRadius: '8px', color: '#f87171', marginBottom: '24px' }}>{error}</div>
            <button onClick={() => { hasLaunched.current = false; setStep('waiting'); launchWhatsAppSignup(); }} style={{ backgroundColor: '#1877f2', color: 'white', border: 'none', padding: '12px 24px', borderRadius: '6px', width: '100%' }}>
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
};

export default MetaFinalizing;
