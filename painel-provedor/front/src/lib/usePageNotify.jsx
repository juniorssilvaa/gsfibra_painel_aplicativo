import { useCallback } from 'react';
import { toast } from './notify.jsx';

/**
 * Hook de compatibilidade — todas as notificações usam o AppToaster global.
 * Mesmo padrão visual (AppNotifyCard) em todo o painel.
 */
export function usePageNotify() {
  const showSuccess = useCallback((message) => toast.success(message), []);
  const showError = useCallback((message) => toast.error(message), []);
  const showInfo = useCallback((message) => toast.info(message), []);
  const showDeleted = useCallback((message) => toast.deleted(message), []);

  return {
    showSuccess,
    showError,
    showInfo,
    showDeleted,
    host: null,
  };
}
