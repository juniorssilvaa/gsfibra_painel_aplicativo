import React, { useState, useEffect } from 'react';
import { CheckCircle, Bell } from 'lucide-react';
import axios from 'axios';

const NotificationModal = ({ isOpen, onClose, notification, onMarkAsRead }) => {
  const [isLoading, setIsLoading] = useState(false);

  // Marcar como visualizada
  const handleConfirmRead = async () => {
    if (!notification) return;

    try {
      setIsLoading(true);
      const token = localStorage.getItem('auth_token') || localStorage.getItem('token');
      await axios.patch(`/api/mensagens-sistema/${notification.id}/marcar-visualizada/`, {}, {
        headers: { Authorization: `Token ${token}` }
      });

      // Chamar callback para atualizar estado
      if (onMarkAsRead) {
        onMarkAsRead(notification.id);
      }

      // Fechar modal
      onClose();
    } catch (err) {
      console.error('Erro ao marcar como visualizada:', err);
    } finally {
      setIsLoading(false);
    }
  };

  // Fechar modal sem marcar como visualizada
  // A mensagem continuará aparecendo a cada 15 minutos até ser confirmada
  const handleClose = (e) => {
    e?.preventDefault();
    e?.stopPropagation();
    if (onClose) {
      onClose();
    }
  };

  // Prevenir fechamento com ESC - só fecha com botão "Fechar" ou "Confirmar Leitura"
  useEffect(() => {
    if (isOpen) {
      // Prevenir scroll do body
      document.body.style.overflow = 'hidden';
    }

    return () => {
      document.body.style.overflow = 'unset';
    };
  }, [isOpen]);

  if (!isOpen || !notification) return null;

  const renderMessageWithLinks = (text) => {
    if (!text) return null;

    const urlRegex = /((https?:\/\/|www\.)[^\s]+)/gi;
    const parts = String(text).split(urlRegex);

    return parts.map((part, index) => {
      if (!part) return null;

      const isUrl = /^(https?:\/\/|www\.)/i.test(part);
      if (!isUrl) {
        return <React.Fragment key={`text-${index}`}>{part}</React.Fragment>;
      }

      const href = part.startsWith('http') ? part : `https://${part}`;
      return (
        <a
          key={`link-${index}`}
          href={href}
          target="_blank"
          rel="noopener noreferrer"
          className="notification-link font-semibold underline underline-offset-4"
        >
          {part}
        </a>
      );
    });
  };

  return (
    <>
      {/* Overlay */}
      <div
        className="fixed inset-0 bg-background/70 backdrop-blur-sm z-[100] flex items-center justify-center p-4 animate-in fade-in duration-300"
      >
        {/* Modal */}
        <div
          className="bg-card border border-border rounded-2xl shadow-2xl max-w-2xl w-full max-h-[90vh] overflow-hidden flex flex-col animate-in zoom-in-95 duration-300"
          onClick={(e) => e.stopPropagation()}
        >
          {/* Header */}
          <div className="relative overflow-hidden p-6 border-b border-border bg-accent/20">
            
            <div className="relative flex items-center gap-4">
              <div className="flex items-center justify-center w-12 h-12 rounded-xl bg-background/70 border border-border text-muted-foreground">
                <Bell className="w-5 h-5" strokeWidth={2.2} />
              </div>
              <div>
                <h2 className="text-xl font-bold text-foreground tracking-tight">
                  Nova Notificação do Sistema
                </h2>
                <p className="text-sm text-muted-foreground font-medium">
                  Informação importante para o seu provedor
                </p>
              </div>
            </div>
          </div>

          {/* Conteúdo */}
          <div className="p-8 space-y-6 overflow-y-auto flex-1 custom-scrollbar">
            {/* Assunto */}
            <div className="space-y-2">
              <label className="text-xs font-bold uppercase tracking-widest text-muted-foreground ml-1">
                Assunto
              </label>
              <div className="bg-background/60 backdrop-blur-sm rounded-xl p-4 border border-border">
                <p className="text-lg font-semibold text-foreground leading-tight">
                  {notification.assunto}
                </p>
              </div>
            </div>

            {/* Mensagem */}
            <div className="space-y-2">
              <label className="text-xs font-bold uppercase tracking-widest text-muted-foreground ml-1">
                Conteúdo da Mensagem
              </label>
              <div className="bg-background/60 rounded-xl p-5 border border-border">
                <p className="text-foreground whitespace-pre-wrap leading-relaxed">
                  {renderMessageWithLinks(notification.mensagem)}
                </p>
              </div>
            </div>

            {/* Meta-informações em grid */}
            <div className="grid grid-cols-2 gap-4 pt-4">
              <div className="bg-background/50 p-3 rounded-lg border border-border flex flex-col">
                <span className="text-[10px] uppercase font-bold text-muted-foreground">Enviado em</span>
                <span className="text-sm text-foreground">
                  {new Date(notification.created_at).toLocaleDateString('pt-BR', { day: '2-digit', month: 'long', year: 'numeric' })}
                </span>
              </div>
              <div className="bg-background/50 p-3 rounded-lg border border-border flex flex-col">
                <span className="text-[10px] uppercase font-bold text-muted-foreground">Tipo de Alerta</span>
                <span className="text-sm text-primary capitalize bg-primary/10 px-2 py-0.5 rounded-md self-start mt-1">
                  {notification.tipo}
                </span>
              </div>
            </div>
          </div>

          {/* Footer */}
          <div className="p-6 bg-background/40 border-t border-border flex items-center justify-end gap-4">
            <button
              type="button"
              onClick={handleClose}
              className="px-5 py-2.5 rounded-xl border border-border text-muted-foreground hover:text-foreground hover:bg-accent transition-all duration-200 font-medium text-sm"
            >
              Lembrar mais tarde
            </button>
            <button
              type="button"
              onClick={handleConfirmRead}
              disabled={isLoading}
              className="group relative px-7 py-2.5 rounded-xl bg-primary font-bold text-sm text-primary-foreground hover:bg-primary/90 transition-all duration-200 disabled:opacity-50 disabled:cursor-not-allowed"
            >
              <div className="relative flex items-center gap-2">
                {isLoading ? (
                  <>
                    <div className="w-4 h-4 border-2 border-primary-foreground/30 border-t-primary-foreground rounded-full animate-spin" />
                    <span>Processando...</span>
                  </>
                ) : (
                  <>
                    <CheckCircle className="w-4 h-4" />
                    <span>Confirmar Recebimento</span>
                  </>
                )}
              </div>
            </button>
          </div>
        </div>
      </div>

      <style jsx>{`
        .notification-link {
          color: var(--primary);
        }
        .notification-link:hover {
          opacity: 0.85;
        }
        .custom-scrollbar::-webkit-scrollbar {
          width: 5px;
        }
        .custom-scrollbar::-webkit-scrollbar-track {
          background: transparent;
        }
        .custom-scrollbar::-webkit-scrollbar-thumb {
          background: color-mix(in srgb, var(--muted-foreground) 40%, transparent);
          border-radius: 10px;
        }
        .custom-scrollbar::-webkit-scrollbar-thumb:hover {
          background: color-mix(in srgb, var(--muted-foreground) 60%, transparent);
        }
      `}</style>
    </>
  );
};

export default NotificationModal; 