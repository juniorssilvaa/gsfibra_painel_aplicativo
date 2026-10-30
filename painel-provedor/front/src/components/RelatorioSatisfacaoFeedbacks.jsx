import React, { useState } from 'react';
import axios from 'axios';
import { MessageCircle, X } from 'lucide-react';
import { buildApiPath } from '../utils/apiBaseUrl';
import { getMessages } from '../lib/supabase';

const CHANNEL_LABELS = {
  whatsapp: 'WhatsApp',
  whatsapp_oficial: 'WhatsApp',
  whatsapp_session: 'WhatsApp',
  telegram: 'Telegram',
  instagram: 'Instagram',
  web: 'Chat Web',
  email: 'E-mail',
};

const RATING_LABELS = {
  1: 'Péssimo',
  2: 'Ruim',
  3: 'Regular',
  4: 'Bom',
  5: 'Excelente',
};

function ratingBadgeClass(value) {
  if (value === 1) return 'bg-red-500';
  if (value === 2) return 'bg-orange-500';
  if (value === 3) return 'bg-amber-400 text-gray-900';
  if (value === 4) return 'bg-lime-500';
  if (value === 5) return 'bg-emerald-500';
  return 'bg-sky-500';
}

function authToken() {
  return localStorage.getItem('auth_token') || localStorage.getItem('token');
}

export default function RelatorioSatisfacaoFeedbacks({ provedorId, feedbacks = [], loading = false }) {
  const [selectedConversationId, setSelectedConversationId] = useState(null);
  const [conversationDetails, setConversationDetails] = useState(null);
  const [conversationMessages, setConversationMessages] = useState([]);
  const [loadingConversation, setLoadingConversation] = useState(false);
  const [selectedFeedback, setSelectedFeedback] = useState(null);

  const openConversation = async (feedback) => {
    const conversationId = feedback.conversation_id || feedback.conversation;
    if (!conversationId) return;
    setSelectedFeedback(feedback);
    setSelectedConversationId(conversationId);
    setLoadingConversation(true);
    setConversationDetails(null);
    setConversationMessages([]);
    document.body.style.overflow = 'hidden';

    try {
      const token = authToken();
      let details = null;
      try {
        const response = await axios.get(buildApiPath(`/api/conversations/${conversationId}/?for_audit=1`), {
          headers: { Authorization: `Token ${token}` },
        });
        details = response.data;
      } catch {
        details = null;
      }

      setConversationDetails(details || {
        id: conversationId,
        contact: { name: feedback.contact_name },
        inbox: { channel_type: feedback.channel_type },
      });

      let messages = details?.messages || [];
      if (!messages.length) {
        try {
          const apiMessages = await axios.get(
            buildApiPath(`/api/messages/?conversation=${conversationId}&for_audit=1`),
            { headers: { Authorization: `Token ${token}` } },
          );
          messages = apiMessages.data.results || apiMessages.data || [];
        } catch {
          messages = [];
        }
      }
      if ((!messages || !messages.length) && provedorId) {
        try {
          messages = await getMessages(conversationId, provedorId);
        } catch {
          messages = [];
        }
      }
      setConversationMessages(Array.isArray(messages) ? messages : []);
    } finally {
      setLoadingConversation(false);
    }
  };

  const closeConversation = () => {
    setSelectedConversationId(null);
    setSelectedFeedback(null);
    setConversationDetails(null);
    setConversationMessages([]);
    document.body.style.overflow = '';
  };

  return (
    <>
      <div className="rounded-xl border border-border bg-card p-5">
        <div className="mb-4 flex items-end justify-between gap-3">
          <div>
            <p className="text-[11px] font-medium uppercase tracking-[0.16em] text-muted-foreground">
              Últimos Feedbacks
            </p>
            <p className="mt-1 text-sm text-muted-foreground">
              cada cliente avaliado no período, com o histórico do atendimento
            </p>
          </div>
          {feedbacks.length > 0 && (
            <span className="text-xs text-muted-foreground tabular-nums">
              {feedbacks.length} {feedbacks.length === 1 ? 'feedback' : 'feedbacks'}
            </span>
          )}
        </div>

        {loading ? (
          <div className="flex h-32 items-center justify-center">
            <div className="h-8 w-8 animate-spin rounded-full border-b-2 border-primary" />
          </div>
        ) : feedbacks.length === 0 ? (
          <div className="py-10 text-center text-sm text-muted-foreground">
            Nenhum feedback no período selecionado.
          </div>
        ) : (
          <div className="overflow-x-auto rounded-md border border-border">
            <table className="w-full text-sm">
              <thead className="bg-muted/70 text-muted-foreground">
                <tr>
                  <th className="px-4 py-2.5 text-left font-medium">Cliente</th>
                  <th className="px-4 py-2.5 text-left font-medium">Atendente</th>
                  <th className="px-4 py-2.5 text-left font-medium">Nota</th>
                  <th className="px-4 py-2.5 text-left font-medium">Canal</th>
                  <th className="px-4 py-2.5 text-left font-medium">Data</th>
                  <th className="px-4 py-2.5" />
                </tr>
              </thead>
              <tbody>
                {feedbacks.map((feedback, index) => {
                  const rating = Number(feedback.rating_value) || 0;
                  const emoji = feedback.emoji_rating || '';
                  return (
                    <tr key={feedback.id || `${feedback.conversation_id}-${index}`} className="border-t border-border">
                      <td className="px-4 py-3">
                        <div className="flex items-center gap-3 min-w-0">
                          {feedback.contact_photo ? (
                            <img
                              src={feedback.contact_photo}
                              alt=""
                              className="h-8 w-8 rounded-full object-cover shrink-0"
                            />
                          ) : (
                            <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-muted text-xs font-semibold text-foreground">
                              {(feedback.contact_name || 'C').charAt(0).toUpperCase()}
                            </span>
                          )}
                          <span className="font-medium text-foreground truncate">
                            {feedback.contact_name || 'Cliente'}
                          </span>
                        </div>
                      </td>
                      <td className="px-4 py-3 text-muted-foreground">
                        {feedback.agent_name || 'Não identificado'}
                      </td>
                      <td className="px-4 py-3">
                        <span className="inline-flex items-center gap-1.5">
                          <span className="text-base leading-none">{emoji}</span>
                          <span className={`rounded-full px-2 py-0.5 text-xs font-semibold text-white ${ratingBadgeClass(rating)}`}>
                            {rating}/5
                          </span>
                          <span className="text-xs text-muted-foreground">
                            {RATING_LABELS[rating] || ''}
                          </span>
                        </span>
                      </td>
                      <td className="px-4 py-3 text-muted-foreground">
                        {CHANNEL_LABELS[feedback.channel_type] || feedback.channel_type || '—'}
                      </td>
                      <td className="px-4 py-3 text-muted-foreground tabular-nums whitespace-nowrap">
                        {feedback.feedback_sent_at
                          ? new Date(feedback.feedback_sent_at).toLocaleString('pt-BR')
                          : '—'}
                      </td>
                      <td className="px-4 py-3 text-right">
                        <button
                          type="button"
                          className="text-amber-400 hover:text-amber-300 text-xs font-semibold tracking-wide disabled:opacity-40"
                          onClick={() => openConversation(feedback)}
                          disabled={!feedback.conversation_id && !feedback.conversation}
                        >
                          VER
                        </button>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {selectedConversationId && (
        <div
          className="fixed inset-0 z-[100] flex items-center justify-center bg-black/50 p-4"
          onClick={closeConversation}
        >
          <div
            className="flex max-h-[90vh] w-full max-w-3xl flex-col overflow-hidden rounded-xl border border-border bg-card shadow-xl"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex shrink-0 items-center justify-between border-b border-border p-4">
              <div>
                <h2 className="flex items-center gap-2 text-lg font-semibold text-foreground">
                  <MessageCircle className="h-5 w-5" />
                  Conversa #{selectedConversationId}
                </h2>
                <p className="mt-0.5 text-sm text-muted-foreground">
                  {selectedFeedback?.contact_name || conversationDetails?.contact?.name || 'Cliente'}
                  {selectedFeedback?.agent_name ? ` · Atendente: ${selectedFeedback.agent_name}` : ''}
                </p>
              </div>
              <button type="button" onClick={closeConversation} className="rounded-lg p-2 hover:bg-muted">
                <X className="h-5 w-5" />
              </button>
            </div>

            {selectedFeedback && (
              <div className="flex shrink-0 flex-wrap items-center gap-3 border-b border-border bg-muted/30 px-4 py-3 text-sm">
                <span className="text-2xl">{selectedFeedback.emoji_rating}</span>
                <span className={`rounded-full px-2 py-0.5 text-xs font-semibold text-white ${ratingBadgeClass(Number(selectedFeedback.rating_value) || 0)}`}>
                  Nota {selectedFeedback.rating_value}/5
                </span>
                <span className="text-muted-foreground">
                  {RATING_LABELS[Number(selectedFeedback.rating_value)] || ''}
                </span>
                <span className="ml-auto text-muted-foreground">
                  {CHANNEL_LABELS[selectedFeedback.channel_type] || selectedFeedback.channel_type}
                </span>
              </div>
            )}

            <div className="min-h-0 flex-1 overflow-y-auto p-4">
              {loadingConversation ? (
                <div className="flex items-center justify-center py-16">
                  <div className="h-8 w-8 animate-spin rounded-full border-b-2 border-primary" />
                </div>
              ) : conversationMessages.length > 0 ? (
                <div className="space-y-3">
                  {conversationMessages.map((message, index) => {
                    const isCustomer = message.is_from_customer === true;
                    const content = message.content || message.text || message.body || '';
                    const createdAt = message.created_at || message.timestamp;
                    return (
                      <div key={message.id || index} className={`flex ${isCustomer ? 'justify-start' : 'justify-end'}`}>
                        <div
                          className={`max-w-[85%] rounded-2xl px-3 py-2 text-sm shadow-sm ${
                            isCustomer ? 'bg-muted text-foreground' : 'bg-sky-600 text-white'
                          }`}
                        >
                          <div className={`mb-1 text-[11px] font-medium ${isCustomer ? 'text-muted-foreground' : 'text-sky-100'}`}>
                            {isCustomer
                              ? (selectedFeedback?.contact_name || 'Cliente')
                              : (selectedFeedback?.agent_name || 'Atendente / Sistema')}
                          </div>
                          <div className="whitespace-pre-wrap break-words">
                            {content || (message.message_type ? `[${message.message_type}]` : '—')}
                          </div>
                          {createdAt && (
                            <div className={`mt-1 text-[10px] ${isCustomer ? 'text-muted-foreground' : 'text-sky-100'}`}>
                              {new Date(createdAt).toLocaleString('pt-BR')}
                            </div>
                          )}
                        </div>
                      </div>
                    );
                  })}
                </div>
              ) : (
                <div className="py-16 text-center text-muted-foreground">
                  <MessageCircle className="mx-auto mb-3 h-10 w-10 opacity-40" />
                  <p>Nenhuma mensagem encontrada para esta conversa.</p>
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </>
  );
}
