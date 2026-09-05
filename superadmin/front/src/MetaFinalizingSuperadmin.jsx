import React, { useEffect, useRef, useState } from 'react';
import { useSearchParams, useNavigate } from 'react-router-dom';
import { Loader2, CheckCircle2, AlertCircle } from 'lucide-react';
import useMetaEmbeddedSignupListener from './hooks/useMetaEmbeddedSignupListener';
import { META_CONNECT_IFRAME_CACHE_BUSTER } from './utils/metaConnect';

const MSG = {
  READY: 'META_CONNECT_INNER_READY',
  AUTH: 'META_CONNECT_AUTH',
  SUCCESS: 'META_CONNECT_SUCCESS',
  ERROR: 'META_CONNECT_ERROR',
  FINISH_REQUEST: 'META_CONNECT_FINISH_REQUEST',
  FINISH_RESULT: 'META_CONNECT_FINISH_RESULT',
};

/**
 * Tela de finalização do Embedded Signup da Meta para o Superadmin.
 *
 * Usa o próprio domínio do Superadmin como host do MetaConnectInnerSuperadmin
 * (em vez de connect.niohub.com.br), via iframe oculto em:
 *   <domínio-superadmin>/app/meta/connect-inner
 *
 * Fluxo:
 * 1. MetaFinalizingSuperadmin carrega o iframe apontando para o próprio domínio
 * 2. O iframe (MetaConnectInnerSuperadmin) recebe o token via postMessage
 * 3. O iframe abre o popup do Facebook/Meta com state=billing_superadmin_1
 * 4. Após o usuário concluir, o meta_callback redireciona para finalizando-superadmin
 * 5. O iframe envia FINISH_REQUEST via postMessage com wabaId + payload
 * 6. Este componente chama o backend do Superadmin e responde com FINISH_RESULT
 */
export default function MetaFinalizingSuperadmin() {
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();

  const [step, setStep] = useState('waiting');
  const [error, setError] = useState(null);
  const [resultData, setResultData] = useState(null);

  const iframeRef = useRef(null);
  const [iframeKey, setIframeKey] = useState(0);
  const finishInFlightRef = useRef(false);

  const codeFromUrl = searchParams.get('code');

  // O Superadmin usa o próprio domínio como origin do iframe connect-inner
  // (não depende de VITE_META_CONNECT_ORIGIN)
  const selfOrigin = typeof window !== 'undefined' ? window.location.origin : '';

  const connectInnerUrl = React.useMemo(() => {
    if (!selfOrigin) return '';
    const u = new URL('/app/meta/connect-inner', selfOrigin);
    u.searchParams.set('tenant_origin', selfOrigin);
    u.searchParams.set('provider_id', '1');
    u.searchParams.set('channel_id', 'billing_superadmin');
    u.searchParams.set('niohub_cb', META_CONNECT_IFRAME_CACHE_BUSTER);
    return u.toString();
  }, [selfOrigin]);

  const { sendFinishToBackend } = useMetaEmbeddedSignupListener({ debug: false });

  const sendAuthToIframe = React.useCallback(() => {
    const cw = iframeRef.current?.contentWindow;
    const token = localStorage.getItem('auth_token') || localStorage.getItem('token');
    if (!cw || !token || !selfOrigin) return;
    try {
      cw.postMessage({ type: MSG.AUTH, token }, selfOrigin);
    } catch (_) {
      /* ignore */
    }
  }, [selfOrigin]);

  const scheduleAuthToIframe = React.useCallback(() => {
    sendAuthToIframe();
    setTimeout(sendAuthToIframe, 200);
    setTimeout(sendAuthToIframe, 800);
    setTimeout(sendAuthToIframe, 2000);
    setTimeout(sendAuthToIframe, 4000);
  }, [sendAuthToIframe]);

  // Ouvir postMessages do MetaConnectInnerSuperadmin (mesmo domínio)
  useEffect(() => {
    if (!selfOrigin) return undefined;

    const postFinishResultToIframe = (payload) => {
      const iw = iframeRef.current?.contentWindow;
      if (!iw) return;
      try {
        iw.postMessage({ type: MSG.FINISH_RESULT, ...payload }, selfOrigin);
      } catch (_) {
        /* ignore */
      }
    };

    const onMsg = (e) => {
      // Aceitar mensagens do mesmo domínio (iframe do connect-inner do superadmin)
      if (e.origin !== selfOrigin) return;

      if (e.data?.type === MSG.READY) {
        const token = localStorage.getItem('auth_token') || localStorage.getItem('token');
        if (e.source && token) {
          try {
            e.source.postMessage({ type: MSG.AUTH, token }, selfOrigin);
          } catch (_) {
            /* ignore */
          }
        }
      }

      if (e.data?.type === MSG.SUCCESS) {
        setResultData(e.data.canal);
        setStep('success');
      }

      if (e.data?.type === MSG.ERROR) {
        setError(e.data.message || 'Erro no fluxo Meta');
        setStep('error');
      }

      if (e.data?.type === MSG.FINISH_REQUEST) {
        if (e.source !== iframeRef.current?.contentWindow) return;
        if (finishInFlightRef.current) return;
        const { wabaId, payload } = e.data;
        if (!wabaId || !payload) return;
        finishInFlightRef.current = true;
        setStep('processing');
        void (async () => {
          try {
            const response = await sendFinishToBackend(wabaId, null, { payload });
            if (response?.success) {
              postFinishResultToIframe({ ok: true, canal: response.billing });
              setResultData(response.billing || {});
              setStep('success');
            } else {
              const msg = response?.error || 'Erro ao processar integração';
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
  }, [selfOrigin, sendFinishToBackend]);

  // Fallback: se o meta_callback redirecionou diretamente aqui com ?code=...,
  // o MetaConnectInnerSuperadmin deve ter capturado via postMessage.
  // Caso o iframe ainda não tenha recebido o código, tentar via URL.
  useEffect(() => {
    if (!codeFromUrl || finishInFlightRef.current || step === 'success') return;

    // Aguardar brevemente para dar chance ao iframe de processar via postMessage
    const t = setTimeout(async () => {
      // Verificar novamente (o iframe pode ter processado entretempos)
      if (finishInFlightRef.current || step === 'success') return;

      // Só ativar o fallback se wabaId já está no eventData do hook
      // Como não temos wabaId aqui, redirecionar para o iframe processar
      // tentando forçar o reload do iframe com o código
      setIframeKey(k => k + 1);
    }, 2000);

    return () => clearTimeout(t);
  }, [codeFromUrl, step]);

  return (
    <div
      style={{
        position: 'relative',
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        justifyContent: 'center',
        minHeight: '100vh',
        backgroundColor: 'var(--background, #0f172a)',
        color: 'var(--foreground, #f8fafc)',
        fontFamily: 'sans-serif',
        padding: '20px',
      }}
    >
      {(step === 'waiting' || step === 'processing') && (
        <>
          <div
            style={{
              backgroundColor: 'var(--card, #1e293b)',
              padding: '28px',
              borderRadius: '12px',
              boxShadow: '0 10px 25px -5px rgba(0, 0, 0, 0.3)',
              maxWidth: '560px',
              width: '100%',
              textAlign: 'center',
              border: '1px solid var(--border, rgba(255,255,255,0.1))',
            }}
          >
            <div style={{ marginBottom: '16px', display: 'flex', justifyContent: 'center' }}>
              <Loader2 size={48} className="animate-spin" style={{ color: 'var(--primary, #3b82f6)' }} />
            </div>
            <h2 style={{ fontSize: '22px', fontWeight: 'bold', marginBottom: '12px' }}>
              {step === 'processing' ? 'Configurando canal…' : 'Aguardando finalização…'}
            </h2>
            <p style={{ color: 'var(--muted-foreground, #94a3b8)', lineHeight: '1.6', marginBottom: '12px' }}>
              {step === 'processing'
                ? 'Recebemos os dados da Meta e estamos configurando o canal de cobrança.'
                : 'Conclua os passos na janela da Meta. Esta página atualizará automaticamente.'}
            </p>
            {step === 'waiting' && (
              <button
                type="button"
                onClick={() => setIframeKey((k) => k + 1)}
                style={{
                  color: 'var(--primary, #3b82f6)',
                  background: 'none',
                  border: 'none',
                  cursor: 'pointer',
                  textDecoration: 'underline',
                  fontSize: 13,
                }}
              >
                Recarregar fluxo Meta
              </button>
            )}
          </div>

          {/* iframe oculto: MetaConnectInnerSuperadmin rodando no mesmo domínio */}
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
              title="Meta connect superadmin (background)"
              src={connectInnerUrl}
              onLoad={scheduleAuthToIframe}
              style={{ width: 1, height: 1, border: 'none', display: 'block', opacity: 0 }}
              sandbox="allow-scripts allow-same-origin allow-forms allow-popups allow-popups-to-escape-sandbox allow-top-navigation-by-user-activation"
            />
          </div>
        </>
      )}

      {step === 'success' && (
        <div style={{ maxWidth: 560, width: '100%', textAlign: 'center' }}>
          <CheckCircle2 size={64} style={{ color: '#22c55e', margin: '0 auto 16px' }} />
          <h2 style={{ fontSize: '24px', fontWeight: 'bold', color: '#22c55e', marginBottom: 8 }}>
            Tudo pronto!
          </h2>
          <p style={{ color: 'var(--muted-foreground, #94a3b8)', marginBottom: 20 }}>
            Canal de cobrança conectado com sucesso.
            {resultData?.display_phone_number && ` Número: ${resultData.display_phone_number}`}
          </p>
          <button
            type="button"
            onClick={() => navigate('/admin/configuracoes')}
            style={{
              backgroundColor: '#22c55e',
              color: 'white',
              border: 'none',
              padding: '14px 24px',
              borderRadius: '6px',
              fontWeight: 'bold',
              cursor: 'pointer',
              width: '100%',
            }}
          >
            Voltar para Configurações
          </button>
        </div>
      )}

      {step === 'error' && (
        <div style={{ maxWidth: 560, width: '100%', textAlign: 'center' }}>
          <AlertCircle size={64} style={{ color: '#ef4444', margin: '0 auto 16px' }} />
          <h2 style={{ fontSize: '24px', fontWeight: 'bold', color: '#ef4444', marginBottom: 8 }}>
            Houve um problema
          </h2>
          <p style={{ color: 'var(--muted-foreground, #94a3b8)', marginBottom: 20 }}>
            {error || 'Erro ao conectar o canal.'}
          </p>
          <button
            type="button"
            onClick={() => window.location.reload()}
            style={{
              backgroundColor: '#3b82f6',
              color: 'white',
              border: 'none',
              padding: '14px 24px',
              borderRadius: '6px',
              fontWeight: 'bold',
              cursor: 'pointer',
              width: '100%',
            }}
          >
            Tentar novamente
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
