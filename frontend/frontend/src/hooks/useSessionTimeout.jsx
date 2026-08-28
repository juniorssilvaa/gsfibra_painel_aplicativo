import { useRef, useCallback } from 'react';
import axios from 'axios';

const useSessionTimeout = (user) => {
  // Hooks devem ser chamados sempre, antes de qualquer retorno condicional.
  const timeoutRef = useRef(null);
  const warningTimeoutRef = useRef(null);
  const sessionTimeoutRef = useRef(30); // valor padrão de 30 minutos

  const isClient = typeof window !== 'undefined';

  // Buscar timeout configurado do usuário
  const fetchUserSessionTimeout = useCallback(async () => {
    if (!isClient) return 30;

    // Se o usuário já foi passado e tem o timeout, usar direto
    if (user?.session_timeout) {
      sessionTimeoutRef.current = user.session_timeout;
      return user.session_timeout;
    }
    
    try {
      const token = localStorage.getItem('auth_token') || localStorage.getItem('token');
      if (token) {
        // Usar axios com header explícito e flag para evitar loops de logout
        const response = await axios.get('/api/auth/me/', {
          headers: { Authorization: `Token ${token}` },
          __skip401Logout: true
        });
        const userSessionTimeout = response.data.session_timeout || 30;
        sessionTimeoutRef.current = userSessionTimeout;
        return userSessionTimeout;
      }
    } catch (error) {
      // Se falhar na busca, tenta ler do objeto 'user' no localStorage como backup
      try {
        const savedUser = JSON.parse(localStorage.getItem('user'));
        if (savedUser && savedUser.session_timeout) {
          sessionTimeoutRef.current = savedUser.session_timeout;
          return savedUser.session_timeout;
        }
      } catch (e) {}
    }
    return sessionTimeoutRef.current; // mantém o valor atual se falhar
  }, [user, isClient]);

  const resetTimeout = useCallback(() => {
    if (!isClient) return;
    
    // Limpar timeouts anteriores
    if (timeoutRef.current) {
      clearTimeout(timeoutRef.current);
    }
    if (warningTimeoutRef.current) {
      clearTimeout(warningTimeoutRef.current);
    }

    const timeoutMinutes = sessionTimeoutRef.current;
    
    // Se o timeout for 0 ou negativo, desativar o timeout automático
    if (timeoutMinutes <= 0) return;

    const timeoutMs = timeoutMinutes * 60 * 1000;

    // Definir novo timeout para logout automático
    timeoutRef.current = setTimeout(() => {
      // Fazer logout automático - Limpar tudo consistentemente
      const keysToClear = ['auth_token', 'token', 'user', 'selectedConversation', 'unread_messages_by_user', 'internal_chat_unread_count'];
      keysToClear.forEach(key => localStorage.removeItem(key));
      
      alert('Sua sessão expirou por inatividade. Você será redirecionado para a página de login.');
      window.location.href = '/login';
    }, timeoutMs);

    // Definir timeout de aviso (30 segundos antes do logout para timeouts maiores que 1 minuto)
    if (timeoutMinutes > 1) {
      const warningTime = timeoutMs - 30000; // 30 segundos antes
      warningTimeoutRef.current = setTimeout(() => {
        // Mostrar aviso de timeout
        alert(`Sua sessão expirará em 30 segundos por inatividade. Realize alguma ação para continuar.`);
      }, warningTime);
    } else if (timeoutMinutes === 1) {
      // Para timeout de 1 minuto, mostrar aviso após 30 segundos
      warningTimeoutRef.current = setTimeout(() => {
        // Mostrar aviso de timeout
        alert(`Sua sessão expirará em 30 segundos por inatividade. Realize alguma ação para continuar.`);
      }, 30 * 1000);
    }
  }, [isClient]);

  const startTimeout = useCallback(() => {
    if (!isClient) return;

    fetchUserSessionTimeout().then(() => {
      resetTimeout();

      const events = ['mousedown', 'mousemove', 'keypress', 'scroll', 'touchstart', 'click', 'keydown'];
      events.forEach((event) => {
        document.addEventListener(event, resetTimeout, true);
      });

      return () => {
        if (timeoutRef.current) {
          clearTimeout(timeoutRef.current);
        }
        if (warningTimeoutRef.current) {
          clearTimeout(warningTimeoutRef.current);
        }
        events.forEach((event) => {
          document.removeEventListener(event, resetTimeout, true);
        });
      };
    });
  }, [isClient, fetchUserSessionTimeout, resetTimeout]);

  const updateTimeout = useCallback(async () => {
    if (!isClient) return;
    await fetchUserSessionTimeout();
    resetTimeout();
  }, [isClient, fetchUserSessionTimeout, resetTimeout]);

  return { startTimeout, updateTimeout };
};

export default useSessionTimeout;