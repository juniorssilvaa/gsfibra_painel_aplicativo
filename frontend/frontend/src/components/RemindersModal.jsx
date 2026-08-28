import React, { useState, useEffect } from 'react';
import { 
  X, 
  Plus, 
  Trash2, 
  Clock, 
  MessageSquare, 
  Calendar,
  AlertCircle
} from 'lucide-react';
import axios from 'axios';


const RemindersModal = ({ isOpen, onClose, provedorId }) => {
  const [reminders, setReminders] = useState([]);
  const [loading, setLoading] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [contacts, setContacts] = useState([]);
  
  // Form state
  const [message, setMessage] = useState('');
  const [scheduledTime, setScheduledTime] = useState('');
  const [selectedContact, setSelectedContact] = useState('');

  useEffect(() => {
    if (isOpen) {
      fetchReminders();
      fetchContacts();
    }
  }, [isOpen]);

  const fetchReminders = async () => {
    setLoading(true);
    try {
      const token = localStorage.getItem('auth_token') || localStorage.getItem('token');
      const response = await axios.get('/api/reminders/', {
        headers: { Authorization: `Token ${token}` }
      });
      // Handle paginated response: response.data.results or fallback to response.data
      setReminders(response.data.results || response.data || []);
    } catch (error) {
      console.error('Erro ao buscar lembretes:', error);
    } finally {
      setLoading(false);
    }
  };

  const fetchContacts = async () => {
    try {
      const token = localStorage.getItem('auth_token') || localStorage.getItem('token');
      // Buscar contatos do provedor para vincular ao lembrete
      const response = await axios.get(`/api/contacts/?provedor_id=${provedorId}&page_size=1000`, {
        headers: { Authorization: `Token ${token}` }
      });
      setContacts(response.data.results || []);
    } catch (error) {
      console.error('Erro ao buscar contatos:', error);
    }
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!message || !scheduledTime) return;

    setSubmitting(true);
    try {
      const token = localStorage.getItem('auth_token') || localStorage.getItem('token');
      await axios.post('/api/reminders/', {
        message,
        scheduled_time: scheduledTime,
        contact: selectedContact || null
      }, {
        headers: { Authorization: `Token ${token}` }
      });
      
      // Reset form and refresh
      setMessage('');
      setScheduledTime('');
      setSelectedContact('');
      fetchReminders();
    } catch (error) {
      console.error('Erro ao criar lembrete:', error);
      alert('Erro ao criar lembrete. Verifique os dados.');
    } finally {
      setSubmitting(false);
    }
  };

  const handleDelete = async (id) => {
    if (!window.confirm('Tem certeza que deseja excluir este lembrete?')) return;
    
    try {
      const token = localStorage.getItem('auth_token') || localStorage.getItem('token');
      await axios.delete(`/api/reminders/${id}/`, {
        headers: { Authorization: `Token ${token}` }
      });
      setReminders(prev => prev.filter(r => r.id !== id));
    } catch (error) {
      console.error('Erro ao excluir lembrete:', error);
    }
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm p-4">
      <div className="bg-background border border-border w-full max-w-2xl rounded-xl shadow-2xl flex flex-col max-h-[90vh] text-white">
        {/* Header */}
        <div className="p-4 border-b border-border flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Clock className="w-5 h-5 text-primary" />
            <h2 className="text-lg font-bold">Meus Lembretes</h2>
          </div>
          <button onClick={onClose} className="p-2 hover:bg-accent rounded-lg transition-colors">
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Content */}
        <div className="flex-1 overflow-y-auto p-6 space-y-8">
          {/* New Reminder Form */}
          <section>
            <h3 className="text-sm font-semibold text-white/80 uppercase tracking-wider mb-4">Novo Lembrete</h3>
            <form onSubmit={handleSubmit} className="space-y-4 bg-muted/50 p-4 rounded-lg border border-border">
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div className="space-y-2">
                  <label className="text-sm font-medium text-white">Horário</label>
                  <input
                    type="datetime-local"
                    value={scheduledTime}
                    onChange={(e) => setScheduledTime(e.target.value)}
                    className="w-full p-2 bg-background border border-border rounded-lg focus:ring-1 focus:ring-border outline-none transition-all text-white"
                    required
                  />
                </div>
                <div className="space-y-2">
                  <label className="text-sm font-medium text-white">Vincular Contato (Opcional)</label>
                  <select
                    value={selectedContact}
                    onChange={(e) => setSelectedContact(e.target.value)}
                    className="w-full p-2 bg-background border border-border rounded-lg focus:ring-1 focus:ring-border outline-none transition-all text-white"
                  >
                    <option value="">Nenhum</option>
                    {contacts.map(contact => (
                      <option key={contact.id} value={contact.id}>{contact.name}</option>
                    ))}
                  </select>
                </div>
              </div>
              <div className="space-y-2">
                <label className="text-sm font-medium text-white">Mensagem / Anotação</label>
                <textarea
                  value={message}
                  onChange={(e) => setMessage(e.target.value)}
                  placeholder="Ex: Enviar orçamento para o cliente X..."
                  className="w-full p-2 bg-background border border-border rounded-lg focus:ring-2 focus:ring-primary outline-none min-h-[80px] text-white placeholder:text-white/50"
                  required
                />
              </div>
              <button
                type="submit"
                disabled={submitting}
                className="w-full py-2 bg-primary text-primary-foreground rounded-lg font-medium hover:opacity-90 transition-opacity flex items-center justify-center gap-2 disabled:opacity-50"
              >
                {submitting ? 'Criando...' : <><Plus className="w-4 h-4" /> Criar Lembrete</>}
              </button>
            </form>
          </section>

          {/* List section */}
          <section>
            <h3 className="text-sm font-semibold text-white/80 uppercase tracking-wider mb-4">Agendados</h3>
            {loading ? (
              <div className="text-center py-8 text-white/70">Carregando lembretes...</div>
            ) : reminders.length === 0 ? (
              <div className="text-center py-12 bg-muted/20 rounded-lg border border-dashed border-border text-white/70">
                <AlertCircle className="w-8 h-8 mx-auto mb-2 opacity-20" />
                <p>Nenhum lembrete agendado no momento.</p>
              </div>
            ) : (
              <div className="space-y-3">
                {reminders.map(reminder => (
                  <div key={reminder.id} className={`p-4 rounded-lg border ${reminder.is_notified ? 'bg-muted/30 border-border opacity-60' : 'bg-background border-border shadow-sm'} flex items-start justify-between group text-white`}>
                    <div className="space-y-1">
                      <div className="flex items-center gap-2 text-xs font-medium text-white/70">
                        <Calendar className="w-3 h-3" />
                        {new Date(reminder.scheduled_time).toLocaleString('pt-BR')}
                        {reminder.is_notified && <span className="bg-green-500/10 text-green-500 px-2 py-0.5 rounded-full text-[10px]">Notificado</span>}
                      </div>
                      <p className="text-sm font-medium">{reminder.message}</p>
                      {reminder.contact_name && (
                        <div className="flex items-center gap-1.5 text-xs text-primary">
                          <MessageSquare className="w-3 h-3" />
                          {reminder.contact_name}
                        </div>
                      )}
                    </div>
                    <button
                      onClick={() => handleDelete(reminder.id)}
                      className="p-2 text-white/60 hover:text-destructive transition-colors"
                    >
                      <Trash2 className="w-4 h-4" />
                    </button>
                  </div>
                ))}
              </div>
            )}
          </section>
        </div>
      </div>
    </div>
  );
};

export default RemindersModal;
