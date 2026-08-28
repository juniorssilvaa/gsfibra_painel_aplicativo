import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { Loader2, CheckCircle2, AlertCircle } from 'lucide-react';
import {
  getMetaConnectOrigin,
  shouldUseMetaConnectIframe,
  META_CONNECT_IFRAME_CACHE_BUSTER,
  isLocalDevOrigin,
  isInstagramOAuthMessageOrigin,
} from '../utils/metaConnect';

const MSG = {
  READY: 'INSTAGRAM_CONNECT_INNER_READY',
  AUTH: 'INSTAGRAM_CONNECT_AUTH',
  SUCCESS: 'INSTAGRAM_OAUTH_SUCCESS',
  ERROR: 'INSTAGRAM_OAUTH_ERROR',
};

const pageShellStyle = {
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
};

const cardStyle = {
  backgroundColor: 'var(--card)',
  padding: '28px',
  borderRadius: '12px',
  boxShadow: '0 10px 25px -5px rgba(0, 0, 0, 0.3)',
  maxWidth: '560px',
  width: '100%',
  textAlign: 'center',
  border: '1px solid var(--border)',
};

function InstagramWaitingCard({ bridgeHost, onReload, inlineMode = false }) {
  const hostLabel = bridgeHost ? bridgeHost.replace(/^https?:\/\//, '') : 'connect.niohub.com.br';

  return (
    <div style={cardStyle}>
      <div style={{ marginBottom: '16px', display: 'flex', justifyContent: 'center' }}>
        <Loader2 size={48} className="animate-spin" style={{ color: 'var(--primary)' }} />
      </div>
      <h2 style={{ fontSize: '22px', fontWeight: 'bold', marginBottom: '12px' }}>
        Aguardando finalização...
      </h2>
      {inlineMode ? (
        <p style={{ color: 'var(--muted-foreground)', lineHeight: '1.6', marginBottom: '12px' }}>
          Uma janela do Instagram deve abrir para autorizar o acesso. Conclua o login lá — esta página
          atualiza sozinha ao terminar.
        </p>
      ) : (
        <p style={{ color: 'var(--muted-foreground)', lineHeight: '1.6', marginBottom: '12px' }}>
          O fluxo seguro corre em segundo plano em <strong>{hostLabel}</strong>. Quando a janela do
          Instagram abrir, conclua o login lá — esta página atualiza sozinha ao terminar.
        </p>
      )}
      <p style={{ color: 'var(--muted-foreground)', fontSize: 12, lineHeight: 1.5, marginBottom: '12px' }}>
        Brave / bloqueadores: permita pop-ups para este site
        {!inlineMode && hostLabel ? ` e para ${hostLabel}` : ''}. Se a janela não abrir, desative o
        Escudo ou adicione exceções.
      </p>
      {onReload && (
        <button
          type="button"
          onClick={onReload}
          style={{
            color: 'var(--primary)',
            background: 'none',
            border: 'none',
            cursor: 'pointer',
            textDecoration: 'underline',
            fontSize: 13,
          }}
        >
          Recarregar fluxo Instagram
        </button>
      )}
    </div>
  );
}

function InstagramSuccessPanel({ onContinue }) {
  return (
    <div style={{ marginTop: 24, maxWidth: 560, width: '100%', textAlign: 'center' }}>
      <CheckCircle2 size={64} style={{ color: '#22c55e', margin: '0 auto 16px' }} />
      <h2 style={{ fontSize: '24px', fontWeight: 'bold', color: '#22c55e', marginBottom: 8 }}>
        Instagram conectado
      </h2>
      <p style={{ color: 'var(--muted-foreground)', marginBottom: 20 }}>
        Redirecionando para Configurar Canais…
      </p>
      {onContinue && (
        <button
          type="button"
          onClick={onContinue}
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
          Voltar para Configurar Canais
        </button>
      )}
    </div>
  );
}

function InstagramErrorPanel({ error, onRetry }) {
  return (
    <div style={{ marginTop: 24, maxWidth: 560, width: '100%', textAlign: 'center' }}>
      <AlertCircle size={48} style={{ color: '#ef4444', marginBottom: 12 }} />
      <p style={{ color: '#f87171' }}>{error}</p>
      {onRetry && (
        <button
          type="button"
          onClick={onRetry}
          style={{
            marginTop: 12,
            backgroundColor: '#e1306c',
            color: 'white',
            border: 'none',
            padding: '12px 24px',
            borderRadius: 6,
          }}
        >
          Tentar novamente
        </button>
      )}
    </div>
  );
}

function useInstagramOAuthCompletion({ providerId, channelId, navigate }) {
  const channelsPath = `/app/accounts/${providerId}/canais/configurar`;
  const completedRef = useRef(false);

  const finishSuccess = useCallback(
    (resolvedChannelId) => {
      if (completedRef.current) return;
      completedRef.current = true;
      const cid = resolvedChannelId || channelId;
      navigate(`${channelsPath}?instagram_oauth_success=1&channel_id=${cid}`, { replace: true });
    },
    [channelId, channelsPath, navigate]
  );

  return { finishSuccess, channelsPath, completedRef };
}

function useInstagramChannelPolling({ channelId, onConnected, enabled }) {
  useEffect(() => {
    if (!enabled || !channelId) return undefined;

    const token = localStorage.getItem('auth_token') || localStorage.getItem('token');
    if (!token) return undefined;

    let cancelled = false;
    const check = async () => {
      try {
        const { default: axios } = await import('axios');
        const res = await axios.get(`/api/canais/${channelId}/`, {
          headers: { Authorization: `Token ${token}` },
        });
        const ch = res.data;
        const extras = ch?.dados_extras || {};
        const status = ch?.state || ch?.status;
        if (!cancelled && extras.instagram_user_id && status === 'connected') {
          onConnected();
        }
      } catch (_) {
        /* ignore */
      }
    };

    check();
    const interval = setInterval(check, 2000);
    return () => {
      cancelled = true;
      clearInterval(interval);
    };
  }, [channelId, enabled, onConnected]);
}

function InstagramFinalizingWithConnectIframe() {
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const iframeRef = useRef(null);
  const [iframeKey, setIframeKey] = useState(0);

  const rawProviderId = searchParams.get('provider_id');
  const user = JSON.parse(localStorage.getItem('user') || '{}');
  const userProviderId = user.provedor_id || user.provedor?.id;
  const providerId =
    rawProviderId && rawProviderId !== 'null' && rawProviderId !== 'undefined'
      ? rawProviderId
      : userProviderId || '1';
  const channelId = searchParams.get('channel_id') || '';

  const [step, setStep] = useState('waiting');
  const [error, setError] = useState(null);

  const { finishSuccess, completedRef } = useInstagramOAuthCompletion({
    providerId,
    channelId,
    navigate,
  });

  const connectOrigin = getMetaConnectOrigin();
  const connectOriginNorm = useMemo(
    () => (connectOrigin ? new URL(connectOrigin).origin : ''),
    [connectOrigin]
  );

  const connectInnerUrl = useMemo(() => {
    if (!connectOrigin) return '';
    const u = new URL('/app/instagram/connect-inner', connectOrigin);
    u.searchParams.set('tenant_origin', window.location.origin);
    u.searchParams.set('provider_id', providerId);
    if (channelId) u.searchParams.set('channel_id', channelId);
    u.searchParams.set('niohub_cb', META_CONNECT_IFRAME_CACHE_BUSTER);
    return u.toString();
  }, [channelId, connectOrigin, providerId]);

  const sendAuthToIframe = useCallback(() => {
    const cw = iframeRef.current?.contentWindow;
    const token = localStorage.getItem('auth_token') || localStorage.getItem('token');
    if (!cw || !token || !connectOriginNorm) return;
    try {
      cw.postMessage({ type: MSG.AUTH, token }, connectOriginNorm);
    } catch (_) {
      /* ignore */
    }
  }, [connectOriginNorm]);

  const scheduleAuthToIframe = useCallback(() => {
    sendAuthToIframe();
    setTimeout(sendAuthToIframe, 200);
    setTimeout(sendAuthToIframe, 800);
    setTimeout(sendAuthToIframe, 2000);
  }, [sendAuthToIframe]);

  const allowedMessageOrigins = useMemo(() => {
    return new Set([
      connectOriginNorm,
      window.location.origin,
      'https://api.niohub.com.br',
      'https://api-local.niohub.com.br',
    ]);
  }, [connectOriginNorm]);

  const onConnected = useCallback(() => {
    if (completedRef.current) return;
    setStep('success');
    setTimeout(() => finishSuccess(), 800);
  }, [completedRef, finishSuccess]);

  useInstagramChannelPolling({
    channelId,
    onConnected,
    enabled: step === 'waiting' && Boolean(channelId),
  });

  useEffect(() => {
    if (!connectOrigin) return undefined;

    const onMsg = (e) => {
      const payload = e.data;
      const isOAuth =
        payload?.type === MSG.SUCCESS ||
        payload?.type === MSG.ERROR ||
        payload?.type === 'INSTAGRAM_OAUTH_SUCCESS' ||
        payload?.type === 'INSTAGRAM_OAUTH_ERROR';

      if (isOAuth) {
        if (
          !allowedMessageOrigins.has(e.origin) &&
          !isInstagramOAuthMessageOrigin(e.origin)
        ) {
          return;
        }
      } else if (!allowedMessageOrigins.has(e.origin)) {
        return;
      }

      if (e.data?.type === MSG.READY) {
        const token = localStorage.getItem('auth_token') || localStorage.getItem('token');
        if (e.source && token) {
          e.source.postMessage({ type: MSG.AUTH, token }, connectOriginNorm);
        }
      }
      if (payload?.type === MSG.SUCCESS || payload?.type === 'INSTAGRAM_OAUTH_SUCCESS') {
        setStep('success');
        setTimeout(() => finishSuccess(payload.channel_id), 1200);
      }
      if (payload?.type === MSG.ERROR || payload?.type === 'INSTAGRAM_OAUTH_ERROR') {
        setError(
          payload.error_detail
            ? `${payload.message || payload.error || 'Erro'}: ${payload.error_detail}`
            : payload.message || payload.error || 'Erro ao conectar Instagram'
        );
        setStep('error');
      }
    };

    window.addEventListener('message', onMsg);
    return () => window.removeEventListener('message', onMsg);
  }, [allowedMessageOrigins, connectOrigin, connectOriginNorm, finishSuccess]);

  if (!connectOrigin || !connectInnerUrl) {
    return (
      <div style={{ padding: 24 }}>
        <AlertCircle className="inline" /> VITE_META_CONNECT_ORIGIN não configurado.
      </div>
    );
  }

  const reloadFlow = () => {
    completedRef.current = false;
    setStep('waiting');
    setError(null);
    setIframeKey((k) => k + 1);
  };

  return (
    <div style={pageShellStyle}>
      {step === 'waiting' && (
        <>
          <InstagramWaitingCard bridgeHost={connectOrigin} onReload={reloadFlow} />
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
              title="Instagram connect (background)"
              src={connectInnerUrl}
              onLoad={scheduleAuthToIframe}
              style={{ width: 1, height: 1, border: 'none', display: 'block', opacity: 0 }}
              sandbox="allow-scripts allow-same-origin allow-forms allow-popups allow-popups-to-escape-sandbox allow-top-navigation-by-user-activation"
            />
          </div>
        </>
      )}
      {step === 'success' && <InstagramSuccessPanel />}
      {step === 'error' && <InstagramErrorPanel error={error} onRetry={reloadFlow} />}
      <style>{`
        @keyframes spin { from { transform: rotate(0deg); } to { transform: rotate(360deg); } }
        .animate-spin { animation: spin 1s linear infinite; }
      `}</style>
    </div>
  );
}

function InstagramFinalizingInline() {
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const channelId = searchParams.get('channel_id') || '';
  const rawProviderId = searchParams.get('provider_id');
  const user = JSON.parse(localStorage.getItem('user') || '{}');
  const providerId =
    rawProviderId && rawProviderId !== 'null'
      ? rawProviderId
      : user.provedor_id || user.provedor?.id || '1';

  const [step, setStep] = useState('waiting');
  const [error, setError] = useState(null);
  const launched = useRef(false);

  const { finishSuccess, completedRef } = useInstagramOAuthCompletion({
    providerId,
    channelId,
    navigate,
  });

  const onConnected = useCallback(() => {
    if (completedRef.current) return;
    setStep('success');
    setTimeout(() => finishSuccess(), 800);
  }, [completedRef, finishSuccess]);

  useInstagramChannelPolling({
    channelId,
    onConnected,
    enabled: step === 'waiting' && Boolean(channelId),
  });

  const launchOAuth = useCallback(() => {
    const token = localStorage.getItem('auth_token') || localStorage.getItem('token');
    if (!token) {
      setError('Token não encontrado. Faça login novamente.');
      setStep('error');
      return;
    }

    import('axios').then(({ default: axios }) => {
      axios
        .post(
          `/api/canais/${channelId}/connect-instagram/`,
          {
            frontend_origin: window.location.origin,
            local_dev: isLocalDevOrigin(),
          },
          { headers: { Authorization: `Token ${token}` } }
        )
        .then((res) => {
          if (!res.data?.oauth_url) {
            throw new Error(res.data?.error || 'Erro ao iniciar OAuth');
          }
          const popup = window.open(
            res.data.oauth_url,
            'instagram_oauth',
            'width=520,height=720,scrollbars=yes'
          );
          if (!popup) {
            throw new Error('Permita pop-ups para conectar o Instagram.');
          }
        })
        .catch((err) => {
          setError(err.response?.data?.error || err.message);
          setStep('error');
        });
    });
  }, [channelId]);

  useEffect(() => {
    if (launched.current || !channelId) return;
    launched.current = true;
    launchOAuth();

    const onOAuth = (event) => {
      const payload = event.data;
      if (!payload || typeof payload !== 'object') return;
      if (
        payload.type !== 'INSTAGRAM_OAUTH_SUCCESS' &&
        payload.type !== 'INSTAGRAM_OAUTH_ERROR'
      ) {
        return;
      }
      if (!isInstagramOAuthMessageOrigin(event.origin)) return;

      if (payload.type === 'INSTAGRAM_OAUTH_SUCCESS') {
        setStep('success');
        setTimeout(() => finishSuccess(payload.channel_id), 1200);
      }
      if (payload.type === 'INSTAGRAM_OAUTH_ERROR') {
        setError(
          payload.error_detail
            ? `${payload.error || 'Erro'}: ${payload.error_detail}`
            : payload.error || 'Erro ao conectar Instagram'
        );
        setStep('error');
      }
    };
    window.addEventListener('message', onOAuth);
    return () => window.removeEventListener('message', onOAuth);
  }, [channelId, finishSuccess, launchOAuth]);

  const retry = () => {
    completedRef.current = false;
    launched.current = false;
    setStep('waiting');
    setError(null);
    launchOAuth();
  };

  return (
    <div style={pageShellStyle}>
      {step === 'waiting' && (
        <InstagramWaitingCard inlineMode onReload={retry} />
      )}
      {step === 'success' && <InstagramSuccessPanel />}
      {step === 'error' && <InstagramErrorPanel error={error} onRetry={retry} />}
      <style>{`
        @keyframes spin { from { transform: rotate(0deg); } to { transform: rotate(360deg); } }
        .animate-spin { animation: spin 1s linear infinite; }
      `}</style>
    </div>
  );
}

export default function InstagramFinalizing() {
  return shouldUseMetaConnectIframe() ? (
    <InstagramFinalizingWithConnectIframe />
  ) : (
    <InstagramFinalizingInline />
  );
}
