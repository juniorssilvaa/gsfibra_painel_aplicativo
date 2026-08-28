import { useEffect, useRef } from 'react';
import axios from 'axios';

/**
 * Escuta FINISH_WHATSAPP_BUSINESS_APP_ONBOARDING (postMessage) e expõe sendFinishToBackend.
 * Ficheiro .jsx para o Vite empacotar com o mesmo runtime de React que componentes lazy.
 *
 * @see https://developers.facebook.com/docs/whatsapp/embedded-signup/custom-flows/onboarding-business-app-users
 */
function useMetaEmbeddedSignupListener({
  onFinish,
  onError,
  providerId = null,
  debug = false,
  apiOrigin = null,
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

      if (eventType === 'FINISH_WHATSAPP_BUSINESS_APP_ONBOARDING') {
        const wabaId = payload.data?.waba_id;
        const phoneNumberId = payload.data?.phone_number_id;

        if (!wabaId || !phoneNumberId) {
          return;
        }

        if (onFinishRef.current) {
          try {
            onFinishRef.current(wabaId, {
              waba_id: wabaId,
              phone_number_id: phoneNumberId,
              raw: payload,
            });
          } catch (err) {
            if (onErrorRef.current) {
              try {
                onErrorRef.current(err);
              } catch {
                /* ignore */
              }
            }
          }
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

  const sendFinishToBackend = async (wabaId, customProviderId = null, eventData = null) => {
    try {
      let explicit = '';
      if (eventData && eventData.authToken != null && eventData.authToken !== '') {
        explicit = String(eventData.authToken).trim();
      }
      const token =
        explicit || localStorage.getItem('auth_token') || localStorage.getItem('token');
      if (!token) {
        throw new Error(
          'Token de autenticação em falta. Faça login no painel e repita a integração Meta.'
        );
      }

      let finalProviderId = customProviderId || providerId;
      if (!finalProviderId) {
        const userStr = localStorage.getItem('user');
        if (userStr) {
          try {
            const userObj = JSON.parse(userStr);
            finalProviderId = userObj.provedor_id;
          } catch {
            /* ignore */
          }
        }
        if (!finalProviderId) {
          finalProviderId = 1;
        }
      }

      const payload = {
        waba_id: wabaId,
        provider_id: finalProviderId,
        channel_id: eventData?.channelId,
      };

      if (eventData?.payload) {
        const eventPayload = eventData.payload;
        payload.phone_number_id = eventPayload.phone_number_id;
        payload.page_ids = eventPayload.page_ids;
        payload.catalog_ids = eventPayload.catalog_ids;
        payload.dataset_ids = eventPayload.dataset_ids;
        payload.business_id = eventPayload.business_id;
        payload.instagram_account_ids = eventPayload.instagram_account_ids;

        if (eventPayload.code) {
          payload.code = eventPayload.code;
        }
      }

      const base = apiOrigin ? String(apiOrigin).replace(/\/+$/, '') : '';
      const finishUrl = base
        ? `${base}/api/canais/whatsapp_embedded_signup_finish/`
        : '/api/canais/whatsapp_embedded_signup_finish/';

      const response = await axios.post(finishUrl, payload, {
        headers: {
          Authorization: `Token ${token}`,
        },
      });

      return response.data;
    } catch (error) {
      const errorMsg =
        error.response?.data?.error || error.message || 'Erro ao enviar finish para backend';
      throw new Error(errorMsg);
    }
  };

  return {
    sendFinishToBackend,
  };
}

export default useMetaEmbeddedSignupListener;
