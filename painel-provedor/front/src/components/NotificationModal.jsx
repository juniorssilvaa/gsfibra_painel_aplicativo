import React, { useState, useEffect } from 'react';
import { CheckCircle, Bell, ExternalLink } from 'lucide-react';
import axios from 'axios';

function normalizeHotspots(raw) {
  if (!Array.isArray(raw)) return [];
  return raw
    .map((h) => {
      const url = String(h?.url || '').trim();
      if (!url) return null;
      const x = Math.max(0, Math.min(100, Number(h.x) || 0));
      const y = Math.max(0, Math.min(100, Number(h.y) || 0));
      const w = Math.max(1, Math.min(100 - x, Number(h.w) || 10));
      const hgt = Math.max(1, Math.min(100 - y, Number(h.h) || 10));
      return {
        x,
        y,
        w,
        h: hgt,
        url: url.startsWith('http') ? url : `https://${url}`,
        label: String(h.label || '').trim() || 'Abrir link',
      };
    })
    .filter(Boolean);
}

function normalizeCtaLinks(raw) {
  if (!Array.isArray(raw)) return [];
  return raw
    .map((c) => {
      const url = String(c?.url || '').trim();
      if (!url) return null;
      return {
        label: String(c.label || '').trim() || 'Abrir link',
        url: url.startsWith('http') ? url : `https://${url}`,
      };
    })
    .filter(Boolean);
}

const NotificationModal = ({ isOpen, onClose, notification, onMarkAsRead }) => {
  const [isLoading, setIsLoading] = useState(false);

  const handleConfirmRead = async () => {
    if (!notification) return;

    try {
      setIsLoading(true);
      const token = localStorage.getItem('auth_token') || localStorage.getItem('token');
      await axios.patch(`/api/mensagens-sistema/${notification.id}/marcar-visualizada/`, {}, {
        headers: { Authorization: `Token ${token}` }
      });

      if (onMarkAsRead) {
        onMarkAsRead(notification.id);
      }

      onClose();
    } catch (err) {
    } finally {
      setIsLoading(false);
    }
  };

  const handleClose = (e) => {
    e?.preventDefault();
    e?.stopPropagation();
    if (onClose) {
      onClose();
    }
  };

  useEffect(() => {
    if (isOpen) {
      document.body.style.overflow = 'hidden';
    }

    return () => {
      document.body.style.overflow = 'unset';
    };
  }, [isOpen]);

  if (!isOpen || !notification) return null;

  const imagemUrl = String(notification.imagem_url || '').trim();
  const hotspots = normalizeHotspots(notification.hotspots);
  const ctaLinks = normalizeCtaLinks(notification.cta_links);
  const hasImage = Boolean(imagemUrl);
  const hasText = Boolean(String(notification.mensagem || '').trim());

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
      <div
        className="fixed inset-0 bg-background/70 backdrop-blur-sm z-[100] flex items-center justify-center p-4 animate-in fade-in duration-300"
      >
        <div
          className={`bg-card border border-border rounded-2xl shadow-2xl w-full max-h-[90vh] overflow-hidden flex flex-col animate-in zoom-in-95 duration-300 ${
            hasImage ? 'max-w-3xl' : 'max-w-2xl'
          }`}
          onClick={(e) => e.stopPropagation()}
        >
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

          <div className="p-6 md:p-8 space-y-5 overflow-y-auto flex-1 custom-scrollbar">
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

            {hasImage && (
              <div className="space-y-2">
                <label className="text-xs font-bold uppercase tracking-widest text-muted-foreground ml-1">
                  Imagem
                </label>
                <div className="relative w-full overflow-hidden rounded-xl border border-border bg-background">
                  <img
                    src={imagemUrl}
                    alt={notification.assunto || 'Aviso do sistema'}
                    className="block w-full h-auto select-none"
                    draggable={false}
                  />
                  {hotspots.map((spot, idx) => (
                    <a
                      key={`hotspot-${idx}`}
                      href={spot.url}
                      target="_blank"
                      rel="noopener noreferrer"
                      title={spot.label}
                      aria-label={spot.label}
                      className="absolute z-10 rounded-md focus:outline-none focus:ring-2 focus:ring-primary/70"
                      style={{
                        left: `${spot.x}%`,
                        top: `${spot.y}%`,
                        width: `${spot.w}%`,
                        height: `${spot.h}%`,
                      }}
                    />
                  ))}
                </div>
                {hotspots.length > 0 && (
                  <p className="text-xs text-muted-foreground">
                    Clique nas áreas da imagem para abrir os links.
                  </p>
                )}
              </div>
            )}

            {ctaLinks.length > 0 && (
              <div className="flex flex-wrap gap-2">
                {ctaLinks.map((cta, idx) => (
                  <a
                    key={`cta-${idx}`}
                    href={cta.url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-primary text-primary-foreground text-sm font-semibold hover:bg-primary/90 transition-colors"
                  >
                    <ExternalLink className="w-4 h-4" />
                    {cta.label}
                  </a>
                ))}
              </div>
            )}

            {hasText && (
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
            )}

            <div className="grid grid-cols-2 gap-4 pt-2">
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
