import React, { useEffect, useRef, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { Loader2, CheckCircle2, AlertCircle } from 'lucide-react';
import axios from 'axios';
import { getApiBaseUrl } from '../utils/apiBaseUrl';

const MetaFinalizingSuperadmin = () => {
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();

  const [step, setStep] = useState('waiting');
  const [error, setError] = useState(null);
  const [resultData, setResultData] = useState(null);

  const authCodeRef = useRef(null);
  const wabaIdRef = useRef(null);
  const processingRef = useRef(false);
  const launchedRef = useRef(false);

  const META_APP_ID = '713538217881661';
  const META_CONFIG_ID = '1888449245359692';

  const finalizeBillingChannel = async () => {
    if (processingRef.current || step === 'success') return;
    if (!authCodeRef.current || !wabaIdRef.current) return;

    const token = localStorage.getItem('auth_token') || localStorage.getItem('token');
    if (!token) {
      setError('Token não encontrado. Faça login novamente.');
      setStep('error');
      return;
    }

    processingRef.current = true;
    setStep('processing');
    setError(null);

    try {
      const response = await axios.post(
        '/api/system-config/billing-whatsapp/embedded-signup-finish/',
        {
          waba_id: wabaIdRef.current,
          code: authCodeRef.current,
        },
        {
          headers: { Authorization: `Token ${token}` }
        }
      );

      if (!response.data?.success) {
        throw new Error(response.data?.error || 'Erro ao finalizar integração.');
      }

      setResultData(response.data?.billing || {});
      setStep('success');
    } catch (err) {
      setError(err.response?.data?.error || err.message || 'Erro ao finalizar integração.');
      setStep('error');
      processingRef.current = false;
    }
  };

  const launchSignup = () => {
    if (launchedRef.current) return;
    launchedRef.current = true;

    const baseUrl = getApiBaseUrl() || import.meta.env.VITE_API_URL || 'https://api.niohub.com.br';
    const backendUrl = baseUrl.replace(/\/+$/, '');
    const redirectUri = encodeURIComponent(`${backendUrl}/api/auth/facebook/callback/`);
    const extras = encodeURIComponent(JSON.stringify({
      featureType: 'whatsapp_business_app_onboarding',
      sessionInfoVersion: '3'
    }));
    const stateStr = `billing_superadmin_${Date.now()}`;
    const oauthUrl = `https://www.facebook.com/v21.0/dialog/oauth?client_id=${META_APP_ID}&config_id=${META_CONFIG_ID}&response_type=code&redirect_uri=${redirectUri}&state=${stateStr}&extras=${extras}`;

    if (window.location.protocol === 'https:' && window.FB?.login) {
      window.FB.login((response) => {
        if (response?.authResponse?.code) {
          authCodeRef.current = response.authResponse.code;
          finalizeBillingChannel();
        }
      }, {
        config_id: META_CONFIG_ID,
        response_type: 'code',
        override_default_response_type: true,
        extras: {
          setup: {},
          featureType: 'whatsapp_business_app_onboarding',
          sessionInfoVersion: '3'
        }
      });
      return;
    }

    const width = 600;
    const height = 700;
    const left = window.screen.width / 2 - width / 2;
    const top = window.screen.height / 2 - height / 2;
    window.open(
      oauthUrl,
      'MetaBillingSignup',
      `width=${width},height=${height},left=${left},top=${top},scrollbars=yes,status=yes`
    );
  };

  useEffect(() => {
    const codeFromUrl = searchParams.get('code');
    if (codeFromUrl && !authCodeRef.current) {
      authCodeRef.current = codeFromUrl;
      finalizeBillingChannel();
    }

    const parsePayload = (data) => {
      if (!data) return null;
      if (typeof data === 'string') {
        try {
          return JSON.parse(data);
        } catch {
          return null;
        }
      }
      return typeof data === 'object' ? data : null;
    };

    const handleMessage = (event) => {
      if (event.data?.type === 'META_OAUTH_CALLBACK_COMPLETE' && event.data?.code) {
        authCodeRef.current = event.data.code;
        finalizeBillingChannel();
        return;
      }

      const payload = parsePayload(event.data);
      if (!payload) return;

      const eventName = payload?.event;
      const isFinishEvent = eventName === 'FINISH_WHATSAPP_BUSINESS_APP_ONBOARDING' || eventName === 'FINISH' || eventName === 'WA_EMBEDDED_SIGNUP_FINISH';
      if (!isFinishEvent) return;

      const wabaId = payload?.data?.waba_id || payload?.waba_id || payload?.data?.wabaId || payload?.wabaId;
      if (!wabaId) return;

      wabaIdRef.current = wabaId;
      finalizeBillingChannel();
    };

    window.addEventListener('message', handleMessage);

    const loadSdkAndLaunch = () => {
      if (window.location.protocol !== 'https:') {
        launchSignup();
        return;
      }

      if (window.FB?.login) {
        launchSignup();
        return;
      }

      window.fbAsyncInit = function () {
        window.FB.init({
          appId: META_APP_ID,
          cookie: true,
          xfbml: true,
          version: 'v21.0'
        });
        launchSignup();
      };

      if (!document.getElementById('facebook-jssdk')) {
        const js = document.createElement('script');
        js.id = 'facebook-jssdk';
        js.src = 'https://connect.facebook.net/pt_BR/sdk.js';
        document.body.appendChild(js);
      }
    };

    const timer = setTimeout(loadSdkAndLaunch, 300);
    return () => {
      clearTimeout(timer);
      window.removeEventListener('message', handleMessage);
    };
  }, [searchParams]);

  return (
    <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', minHeight: '100vh', backgroundColor: 'var(--background)', color: 'var(--foreground)', fontFamily: 'sans-serif', padding: '20px' }}>
      <div style={{ backgroundColor: 'var(--card)', padding: '40px', borderRadius: '12px', boxShadow: '0 10px 25px -5px rgba(0, 0, 0, 0.3)', maxWidth: '550px', width: '100%', textAlign: 'center', border: '1px solid var(--border)' }}>
        {step === 'waiting' && (
          <>
            <div style={{ marginBottom: '20px', display: 'flex', justifyContent: 'center' }}>
              <Loader2 size={60} className="animate-spin" style={{ color: 'var(--primary)' }} />
            </div>
            <h2 style={{ fontSize: '24px', fontWeight: 'bold', marginBottom: '16px' }}>Aguardando finalização...</h2>
            <p style={{ color: 'var(--muted-foreground)', lineHeight: '1.6', marginBottom: '24px' }}>
              Conclua os passos na janela da Meta. Esta página atualizará automaticamente.
            </p>
          </>
        )}

        {step === 'processing' && (
          <>
            <Loader2 size={60} className="animate-spin" style={{ color: 'var(--nc-accent, #fbbf24)', margin: '0 auto 20px' }} />
            <h2 style={{ fontSize: '24px', fontWeight: 'bold', marginBottom: '16px' }}>Configurando canal de cobrança...</h2>
            <p style={{ color: 'var(--muted-foreground)' }}>Processando dados recebidos da Meta.</p>
          </>
        )}

        {step === 'success' && (
          <>
            <CheckCircle2 size={64} style={{ color: '#22c55e', margin: '0 auto 20px' }} />
            <h2 style={{ fontSize: '28px', fontWeight: 'bold', marginBottom: '8px', color: '#22c55e' }}>Tudo pronto!</h2>
            <p style={{ color: 'var(--muted-foreground)', marginBottom: '24px' }}>
              Canal de cobrança conectado com sucesso.
            </p>
            <div style={{ textAlign: 'left', backgroundColor: 'var(--background)', padding: '24px', borderRadius: '8px', fontSize: '15px', marginBottom: '24px', border: '1px solid var(--border)' }}>
              <div><strong style={{ color: 'var(--muted-foreground)', width: '150px', display: 'inline-block' }}>WABA ID:</strong> {resultData?.waba_id}</div>
              <div><strong style={{ color: 'var(--muted-foreground)', width: '150px', display: 'inline-block' }}>Phone Number ID:</strong> {resultData?.phone_number_id}</div>
              <div><strong style={{ color: 'var(--muted-foreground)', width: '150px', display: 'inline-block' }}>Número:</strong> {resultData?.display_phone_number || '-'}</div>
            </div>
            <button
              onClick={() => navigate('/superadmin/configuracoes')}
              style={{ backgroundColor: '#22c55e', color: 'white', border: 'none', padding: '14px 24px', borderRadius: '6px', fontWeight: 'bold', width: '100%' }}
            >
              Voltar para Configurações
            </button>
          </>
        )}

        {step === 'error' && (
          <>
            <AlertCircle size={60} style={{ color: '#ef4444', margin: '0 auto 20px' }} />
            <h2 style={{ fontSize: '24px', fontWeight: 'bold', marginBottom: '16px', color: '#ef4444' }}>Houve um problema</h2>
            <div style={{ backgroundColor: 'rgba(239, 68, 68, 0.1)', padding: '16px', borderRadius: '8px', color: '#f87171', marginBottom: '24px' }}>
              {error}
            </div>
            <button
              onClick={() => { launchedRef.current = false; setStep('waiting'); launchSignup(); }}
              style={{ backgroundColor: '#1877f2', color: 'white', border: 'none', padding: '12px 24px', borderRadius: '6px', width: '100%' }}
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
};

export default MetaFinalizingSuperadmin;
