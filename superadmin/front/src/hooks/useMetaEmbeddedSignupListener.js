import { useEffect, useRef } from 'react';
import axios from 'axios';

/**
 * Mesmo listener do painel do provedor (FINISH_WHATSAPP_BUSINESS_APP_ONBOARDING),
 * mas o "finish" no superadmin grava no SystemConfig (billing channel).
 */
function useMetaEmbeddedSignupListener({
  onFinish,
  onError,
  debug = false,
} = {}) {
  const handlerRef = useRef(null);
  const mountedRef = useRef(true);
  const onFinishRef = useRef(onFinish);
  const onErrorRef = useRef(onError);

  useEffect(() => {
    onFinishRef.current = onFinish;
    onErrorRef.current = onError;
  }, [onFinish, onError]);

  useEffect(() => {
    mountedRef.current = true;

    const isLocalhost =
      window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1';

    const handleMessage = (event) => {
      if (!mountedRef.current) return;

      // Validação simples: em produção só aceitar facebook.com; em localhost permitir se debug.
      if (event.origin !== 'https://www.facebook.com') {
        if (!isLocalhost && !debug) return;
      }

      let payload = event.data;
      if (typeof payload === 'string') {
        try {
          payload = JSON.parse(payload);
        } catch {
          return;
        }
      }
      if (!payload || typeof payload !== 'object') return;

      const eventType = payload.event;
      if (eventType !== 'FINISH_WHATSAPP_BUSINESS_APP_ONBOARDING') return;

      const wabaId = payload.data?.waba_id;
      const phoneNumberId = payload.data?.phone_number_id;
      if (!wabaId || !phoneNumberId) return;

      try {
        onFinishRef.current?.(wabaId, {
          waba_id: wabaId,
          phone_number_id: phoneNumberId,
          raw: payload,
        });
      } catch (err) {
        try {
          onErrorRef.current?.(err);
        } catch (_) {
          /* ignore */
        }
      }
    };

    handlerRef.current = handleMessage;
    window.addEventListener('message', handleMessage);
    return () => {
      mountedRef.current = false;
      if (handlerRef.current) {
        window.removeEventListener('message', handlerRef.current);
        handlerRef.current = null;
      }
    };
  }, [debug]);

  /**
   * Finaliza o embedded signup no superadmin.
   * Espera receber `eventData.payload.code` (oauth code) vindo do connect-inner.
   */
  const sendFinishToBackend = async (wabaId, _ignored = null, eventData = null) => {
    try {
      const token =
        (eventData?.authToken ? String(eventData.authToken).trim() : '') ||
        localStorage.getItem('auth_token') ||
        localStorage.getItem('token');
      if (!token) {
        throw new Error('Token de autenticação em falta. Faça login no superadmin e repita a integração Meta.');
      }

      const code = (eventData?.payload?.code || '').toString().trim();
      if (!wabaId || !code) {
        throw new Error('Dados incompletos: waba_id/code.');
      }

      const response = await axios.post(
        '/api/system-config/billing-whatsapp/embedded-signup-finish/',
        { waba_id: String(wabaId).trim(), code },
        { headers: { Authorization: `Token ${token}` } }
      );
      return response.data;
    } catch (error) {
      const errorMsg =
        error.response?.data?.error ||
        error.response?.data?.detail ||
        error.message ||
        'Erro ao finalizar integração Meta';
      throw new Error(errorMsg);
    }
  };

  return { sendFinishToBackend };
}

export default useMetaEmbeddedSignupListener;

