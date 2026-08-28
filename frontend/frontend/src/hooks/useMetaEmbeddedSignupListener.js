import { useEffect, useRef } from 'react';
import axios from 'axios';

/**
 * Hook para escutar eventos FINISH_WHATSAPP_BUSINESS_APP_ONBOARDING da Meta
 * 
 * Conforme documentação oficial:
 * https://developers.facebook.com/docs/whatsapp/embedded-signup/custom-flows/onboarding-business-app-users
 * 
 * @param {Object} options - Opções de configuração
 * @param {Function} options.onFinish - Callback chamado quando o evento é recebido (recebe waba_id)
 * @param {Function} options.onError - Callback chamado em caso de erro
 * @param {number} options.providerId - ID do provedor (opcional, será extraído do token se não fornecido)
 * @param {boolean} options.debug - Ativar logs de debug (padrão: false)
 * 
 * @example
 * useMetaEmbeddedSignupListener({
 *   onFinish: (wabaId) => {
 *     console.log('WABA ID recebido:', wabaId);
 *     // Enviar para backend...
 *   },
 *   onError: (error) => {
 *     console.error('Erro:', error);
 *   },
 *   debug: true
 * });
 */
function useMetaEmbeddedSignupListener({ 
  onFinish, 
  onError, 
  providerId = null,
  debug = false 
} = {}) {
  const handlerRef = useRef(null);
  const mountedRef = useRef(true);
  const onFinishRef = useRef(onFinish);
  const onErrorRef = useRef(onError);

  // Atualizar refs sempre que as funções mudarem
  useEffect(() => {
    onFinishRef.current = onFinish;
    onErrorRef.current = onError;
  }, [onFinish, onError]);

  useEffect(() => {
    mountedRef.current = true;

    // Validar origem permitida do evento
    const allowedOrigins = [
      'https://www.facebook.com',
      'https://web.facebook.com',
      'https://staticxx.facebook.com',
      'https://facebook.com',
      'https://business.facebook.com',
      'https://meta.com',
      'https://www.meta.com'
    ];

    // Em desenvolvimento, também aceitar localhost (para testes)
    const isLocalhost = window.location.hostname === 'localhost' || 
                        window.location.hostname === '127.0.0.1';

    // Handler para eventos postMessage
    const handleMessage = (event) => {
      if (!mountedRef.current) return;

      // Validar origem do evento por segurança
      if (event.origin !== "https://www.facebook.com") {
        // Em localhost permitimos outras origens para facilitar testes se o debug estiver ON
        if (!isLocalhost && !debug) return;
      }

      let payload = event.data;

      // Caso venha como string (comum em eventos da Meta)
      if (typeof payload === "string") {
        try {
          payload = JSON.parse(payload);
        } catch {
          return;
        }
      }

      if (!payload || typeof payload !== "object") return;

      // 🚨 CORREÇÃO DEFINITIVA: O campo correto é payload.event
      const eventType = payload.event; 

      if (eventType === "FINISH_WHATSAPP_BUSINESS_APP_ONBOARDING") {
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
              raw: payload
            });
          } catch (error) {
            // Erro no callback onFinish
          }
        }
      }
    };

    // Salvar referência do handler para cleanup
    handlerRef.current = handleMessage;

    // Adicionar listener
    window.addEventListener('message', handleMessage);

    // Cleanup: remover listener quando componente desmontar
    return () => {
      mountedRef.current = false;
      if (handlerRef.current) {
        window.removeEventListener('message', handlerRef.current);
        handlerRef.current = null;
      }
    };
  }, [debug]); // Apenas debug como dependência, onFinish e onError usam refs

  // Função helper para enviar dados do evento para o backend
  const sendFinishToBackend = async (wabaId, customProviderId = null, eventData = null) => {
    try {
      // Priorizar auth_token que é o padrão salvo no Login, mas aceitar token também para compatibilidade
      const token = localStorage.getItem('auth_token') || localStorage.getItem('token');
      if (!token) {
        throw new Error('Token não encontrado no localStorage');
      }

      // Determinar provider_id
      let finalProviderId = customProviderId || providerId;
      if (!finalProviderId) {
        // Tentar obter do localStorage
        const userStr = localStorage.getItem('user');
        if (userStr) {
          try {
            const userObj = JSON.parse(userStr);
            finalProviderId = userObj.provedor_id;
          } catch (e) {
            // Não foi possível extrair provider_id do localStorage
          }
        }
        // Fallback para 1 se não encontrar
        if (!finalProviderId) {
          finalProviderId = 1;
        }
      }

      // Preparar payload com todos os dados do evento
      const payload = {
        waba_id: wabaId,
        provider_id: finalProviderId,
        channel_id: eventData?.channelId
      };

      // Se eventData foi fornecido, incluir todos os dados do payload do evento
      if (eventData?.payload) {
        const eventPayload = eventData.payload;
        payload.phone_number_id = eventPayload.phone_number_id;
        payload.page_ids = eventPayload.page_ids;
        payload.catalog_ids = eventPayload.catalog_ids;
        payload.dataset_ids = eventPayload.dataset_ids;
        payload.business_id = eventPayload.business_id;
        payload.instagram_account_ids = eventPayload.instagram_account_ids;
        
        // 🚨 ADICIONAR O CODE AQUI (Caso tenha sido passado pelo componente)
        if (eventPayload.code) {
          payload.code = eventPayload.code;
        }
      }

      const response = await axios.post(
        '/api/canais/whatsapp_embedded_signup_finish/',
        payload,
        {
          headers: {
            Authorization: `Token ${token}`
          }
        }
      );

      return response.data;
    } catch (error) {
      const errorMsg = error.response?.data?.error || error.message || 'Erro ao enviar finish para backend';
      throw new Error(errorMsg);
    }
  };

  return {
    sendFinishToBackend
  };
}

export default useMetaEmbeddedSignupListener;

