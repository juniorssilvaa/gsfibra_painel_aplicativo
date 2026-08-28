import React from 'react';
import { Bell, X, Check, Clock, MessageSquare } from 'lucide-react';
import { useNotifications } from '../contexts/NotificationContext';

const ReminderAlert = () => {
  const { activeReminders, dismissReminder } = useNotifications();

  if (!activeReminders || activeReminders.length === 0) return null;

  return (
    <div className="fixed bottom-6 right-6 z-[9999] flex flex-col gap-3 max-w-md w-full pointer-events-none">
      {activeReminders.map((reminder) => (
        <div 
          key={reminder.id}
          className="pointer-events-auto bg-white dark:bg-slate-900 border-2 border-primary/30 shadow-[0_8px_32px_rgba(0,0,0,0.4)] rounded-xl overflow-hidden animate-in slide-in-from-right-8 duration-500"
        >
          <div className="bg-primary/5 px-4 py-2 border-b border-border flex items-center justify-between">
            <div className="flex items-center gap-2 text-primary font-bold text-xs uppercase tracking-widest">
              <Bell className="w-3.5 h-3.5 animate-bounce" />
              Lembrete Agendado
            </div>
            <button 
              onClick={() => dismissReminder(reminder.id)}
              className="text-muted-foreground hover:text-primary transition-colors"
            >
              <X className="w-4 h-4" />
            </button>
          </div>
          
          <div className="p-4 space-y-3">
            <div className="flex items-start gap-3">
              <div className="bg-primary/10 p-2 rounded-lg">
                <Clock className="w-5 h-5 text-primary" />
              </div>
              <div className="space-y-1">
                <p className="text-sm font-semibold leading-relaxed">
                  {reminder.message}
                </p>
                {reminder.contact_name && (
                  <div className="flex items-center gap-1.5 text-xs text-muted-foreground">
                    <MessageSquare className="w-3 h-3" />
                    Cliente: <span className="text-primary font-medium">{reminder.contact_name}</span>
                  </div>
                )}
              </div>
            </div>

            <div className="flex justify-end pt-2">
              <button
                onClick={() => dismissReminder(reminder.id)}
                className="flex items-center gap-2 bg-primary text-white px-4 py-1.5 rounded-lg text-xs font-bold hover:opacity-90 transition-all active:scale-95 shadow-lg shadow-black/20"
              >
                <Check className="w-3.5 h-3.5" />
                Entendido / Marcar como Lido
              </button>
            </div>
          </div>
          
          {/* Progress bar animation */}
          <div className="h-1 bg-muted w-full overflow-hidden">
            <div className="h-full bg-primary animate-progress-shrink origin-left" style={{ animationDuration: '30s' }} />
          </div>
        </div>
      ))}
    </div>
  );
};

export default ReminderAlert;
