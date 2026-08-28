/**
 * EXEMPLO DE USO DO HOOK useMetaEmbeddedSignupListener
 * 
 * Este arquivo mostra exemplos de como usar o hook em diferentes cenários.
 */

import useMetaEmbeddedSignupListener from './useMetaEmbeddedSignupListener';

// ============================================================================
// EXEMPLO 1: Uso básico no componente Integrations
// ============================================================================

function IntegrationsExample({ provedorId }) {
  const [processingChannels, setProcessingChannels] = useState(new Set());
  const [channels, setChannels] = useState([]);
  const [toast, setToast] = useState({ show: false, message: '', type: 'info' });

  // Usar o hook
  const { sendFinishToBackend } = useMetaEmbeddedSignupListener({
    providerId: provedorId,
    debug: true, // Ativar logs de debug
    onFinish: async (wabaId, eventData) => {
      console.log('✅ WABA ID recebido:', wabaId);
      
      // 1. Colocar canal em estado "processing"
      const whatsappOficial = channels.find(c => c.tipo === 'whatsapp_oficial');
      if (whatsappOficial) {
        setProcessingChannels(prev => new Set(prev).add(whatsappOficial.id));
      }

      // 2. Exibir feedback visual
      setToast({
        show: true,
        message: 'Finalizando conexão...',
        type: 'info'
      });

      // 3. Enviar para backend usando a função helper do hook
      try {
        const response = await sendFinishToBackend(wabaId);
        
        console.log('✅ Finish processado com sucesso:', response);
        
        // 4. Remover do estado "processing" e recarregar canais
        if (response.canal?.id) {
          setProcessingChannels(prev => {
            const newSet = new Set(prev);
            newSet.delete(response.canal.id);
            return newSet;
          });
        }

        // 5. Recarregar canais para atualizar status
        // ... código para recarregar canais ...

        setToast({
          show: true,
          message: 'WhatsApp Oficial conectado com sucesso!',
          type: 'success'
        });
      } catch (error) {
        console.error('❌ Erro ao processar finish:', error);
        
        // Remover do estado "processing" em caso de erro
        const whatsappOficial = channels.find(c => c.tipo === 'whatsapp_oficial');
        if (whatsappOficial) {
          setProcessingChannels(prev => {
            const newSet = new Set(prev);
            newSet.delete(whatsappOficial.id);
            return newSet;
          });
        }

        setToast({
          show: true,
          message: `Erro: ${error.message}`,
          type: 'error'
        });
      }
    },
    onError: (error) => {
      console.error('❌ Erro no listener:', error);
      setToast({
        show: true,
        message: `Erro: ${error.message}`,
        type: 'error'
      });
    }
  });

  // ... resto do componente
}

// ============================================================================
// EXEMPLO 2: Uso com callback customizado (sem usar sendFinishToBackend)
// ============================================================================

function CustomIntegrationExample() {
  useMetaEmbeddedSignupListener({
    debug: true,
    onFinish: async (wabaId) => {
      // Implementação customizada
      const token = localStorage.getItem('token');
      const response = await fetch('/api/canais/whatsapp_embedded_signup_finish/', {
        method: 'POST',
        headers: {
          'Authorization': `Token ${token}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          waba_id: wabaId,
          provider_id: 1
        })
      });

      const data = await response.json();
      console.log('Resposta:', data);
    }
  });

  // ... resto do componente
}

// ============================================================================
// EXEMPLO 3: Uso mínimo (apenas log)
// ============================================================================

function MinimalExample() {
  useMetaEmbeddedSignupListener({
    onFinish: (wabaId) => {
      console.log('WABA ID recebido:', wabaId);
      // Fazer algo com o waba_id...
    }
  });

  // ... resto do componente
}






