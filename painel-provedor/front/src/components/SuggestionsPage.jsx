import React, { useCallback, useEffect, useMemo, useState } from 'react';
import axios from 'axios';
import { Lightbulb, Plus, MessageCircle, X, Send } from 'lucide-react';
import { toast } from '../lib/notify';
import { buildApiPath } from '../utils/apiBaseUrl';

const STATUS_META = {
  analise: { label: 'Em análise', dot: 'bg-sky-500' },
  desenvolvimento: { label: 'Em desenvolvimento', dot: 'bg-amber-500' },
  concluido: { label: 'Concluído', dot: 'bg-emerald-500' },
};

const COLUMNS = [
  { key: 'analise', title: 'Em análise' },
  { key: 'desenvolvimento', title: 'Em desenvolvimento' },
  { key: 'concluido', title: 'Concluído' },
];

const getAuthHeaders = () => {
  const token = localStorage.getItem('auth_token') || localStorage.getItem('token');
  return token ? { Authorization: `Token ${token}` } : {};
};

function formatDate(value) {
  if (!value) return '';
  try {
    return new Date(value).toLocaleString('pt-BR');
  } catch {
    return '';
  }
}

function SuggestionCard({ item, onOpen }) {
  return (
    <article
      role="button"
      tabIndex={0}
      onClick={() => onOpen(item)}
      onKeyDown={(e) => {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault();
          onOpen(item);
        }
      }}
      className="rounded-xl border border-border bg-card overflow-hidden p-3.5 cursor-pointer hover:border-primary/40 transition-colors text-left"
    >
      <h3 className="text-sm font-semibold text-foreground leading-snug line-clamp-2 mb-1.5">{item.title}</h3>
      <p className="text-xs text-muted-foreground line-clamp-2 mb-3">{item.description}</p>
      <div className="flex items-center justify-between gap-2 text-[11px] text-muted-foreground">
        <div className="min-w-0 flex flex-col gap-0.5">
          <span className="truncate">{item.created_by_name || 'Usuário'}</span>
          {item.created_at ? (
            <span className="truncate tabular-nums">{formatDate(item.created_at)}</span>
          ) : null}
        </div>
        <span className="inline-flex items-center gap-1 shrink-0">
          <MessageCircle className="w-3.5 h-3.5" />
          {item.comments_count || 0}
        </span>
      </div>
    </article>
  );
}

function SuggestionDetailModal({ item, onClose, onCommentAdded }) {
  const [comments, setComments] = useState([]);
  const [loading, setLoading] = useState(true);
  const [body, setBody] = useState('');
  const [saving, setSaving] = useState(false);

  const loadComments = useCallback(async () => {
    setLoading(true);
    try {
      const res = await axios.get(buildApiPath(`/api/suggestions/${item.id}/comments/`), {
        headers: getAuthHeaders(),
        skipErrorToast: true,
      });
      const raw = res.data?.results ?? res.data;
      setComments(Array.isArray(raw) ? raw : []);
    } catch (err) {
      toast.apiError(err, 'Erro ao carregar comentários.');
      setComments([]);
    } finally {
      setLoading(false);
    }
  }, [item.id]);

  useEffect(() => {
    loadComments();
  }, [loadComments]);

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!body.trim()) {
      toast.error('Escreva um comentário.');
      return;
    }
    setSaving(true);
    try {
      const res = await axios.post(
        buildApiPath(`/api/suggestions/${item.id}/comments/`),
        { body: body.trim() },
        { headers: getAuthHeaders(), skipErrorToast: true }
      );
      setComments((prev) => [...prev, res.data]);
      setBody('');
      onCommentAdded?.(item.id);
      toast.success('Comentário enviado!');
    } catch (err) {
      toast.apiError(err, 'Erro ao enviar comentário.');
    } finally {
      setSaving(false);
    }
  };

  const statusMeta = STATUS_META[item.status] || STATUS_META.analise;

  return (
    <div className="fixed inset-0 z-50 bg-black/60 flex items-center justify-center p-4 md:pl-48">
      <div className="w-full max-w-xl max-h-[85vh] rounded-xl border border-border bg-card shadow-xl flex flex-col overflow-hidden">
        <div className="flex items-start justify-between gap-3 px-5 py-4 border-b border-border shrink-0">
          <div className="min-w-0">
            <div className="flex items-center gap-2 mb-1">
              <span className={`w-2 h-2 rounded-full ${statusMeta.dot}`} />
              <span className="text-xs text-muted-foreground">{statusMeta.label}</span>
            </div>
            <h2 className="text-base font-bold text-foreground leading-snug">{item.title}</h2>
            <p className="text-xs text-muted-foreground mt-1">
              {item.created_by_name || 'Usuário'}
            </p>
          </div>
          <button type="button" onClick={onClose} className="text-muted-foreground hover:text-foreground shrink-0">
            <X className="w-5 h-5" />
          </button>
        </div>

        <div className="px-5 py-4 border-b border-border shrink-0">
          <p className="text-sm text-foreground whitespace-pre-wrap">{item.description}</p>
        </div>

        <div className="px-5 py-3 flex items-center gap-2 shrink-0 border-b border-border">
          <MessageCircle className="w-4 h-4 text-muted-foreground" />
          <span className="text-sm font-semibold text-foreground">
            Comentários ({comments.length || item.comments_count || 0})
          </span>
        </div>

        <div className="flex-1 overflow-y-auto px-5 py-3 space-y-3 min-h-[140px]">
          {loading ? (
            <p className="text-xs text-muted-foreground text-center py-6">Carregando…</p>
          ) : comments.length === 0 ? (
            <p className="text-xs text-muted-foreground text-center py-6">
              Nenhum comentário ainda. Seja o primeiro!
            </p>
          ) : (
            comments.map((c) => (
              <div key={c.id} className="rounded-lg border border-border bg-background/60 p-3">
                <div className="flex items-center justify-between gap-2 mb-1.5">
                  <span className="text-xs font-semibold text-foreground truncate">
                    {c.author_name || 'Usuário'}
                  </span>
                  <span className="text-[10px] text-muted-foreground shrink-0">{formatDate(c.created_at)}</span>
                </div>
                <p className="text-sm text-foreground whitespace-pre-wrap">{c.body}</p>
              </div>
            ))
          )}
        </div>

        <form onSubmit={handleSubmit} className="px-5 py-4 border-t border-border shrink-0 space-y-2">
          <textarea
            value={body}
            onChange={(e) => setBody(e.target.value)}
            className="w-full bg-background border border-border text-foreground px-3 py-2 rounded-lg focus:outline-none focus:ring-2 focus:ring-primary min-h-[72px] resize-y text-sm"
            placeholder="Escreva um comentário…"
            maxLength={2000}
          />
          <div className="flex justify-end">
            <button
              type="submit"
              disabled={saving || !body.trim()}
              className="inline-flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-semibold bg-primary hover:bg-primary/90 text-primary-foreground disabled:opacity-50"
            >
              <Send className="w-4 h-4" />
              {saving ? 'Enviando…' : 'Comentar'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

export default function SuggestionsPage({ provedorId }) {
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showModal, setShowModal] = useState(false);
  const [selected, setSelected] = useState(null);
  const [saving, setSaving] = useState(false);
  const [form, setForm] = useState({ title: '', description: '' });

  const fetchItems = useCallback(async () => {
    setLoading(true);
    try {
      const res = await axios.get(buildApiPath('/api/suggestions/'), {
        headers: getAuthHeaders(),
        params: provedorId ? { provedor: provedorId } : undefined,
        skipErrorToast: true,
      });
      const raw = res.data?.results ?? res.data;
      setItems(Array.isArray(raw) ? raw : []);
    } catch (err) {
      toast.apiError(err, 'Erro ao carregar sugestões.');
      setItems([]);
    } finally {
      setLoading(false);
    }
  }, [provedorId]);

  useEffect(() => {
    fetchItems();
  }, [fetchItems]);

  const byStatus = useMemo(() => {
    const map = { analise: [], desenvolvimento: [], concluido: [] };
    for (const item of items) {
      const key = map[item.status] ? item.status : 'analise';
      map[key].push(item);
    }
    return map;
  }, [items]);

  const handleCreate = async (e) => {
    e.preventDefault();
    if (!form.title.trim() || !form.description.trim()) {
      toast.error('Preencha título e descrição.');
      return;
    }
    setSaving(true);
    try {
      await axios.post(
        buildApiPath('/api/suggestions/'),
        {
          title: form.title.trim(),
          description: form.description.trim(),
          provedor: provedorId || undefined,
        },
        { headers: getAuthHeaders(), skipErrorToast: true }
      );
      toast.success('Sugestão enviada com sucesso!');
      setShowModal(false);
      setForm({ title: '', description: '' });
      fetchItems();
    } catch (err) {
      toast.apiError(err, 'Erro ao enviar sugestão.');
    } finally {
      setSaving(false);
    }
  };

  const handleCommentAdded = (suggestionId) => {
    setItems((prev) =>
      prev.map((it) =>
        it.id === suggestionId ? { ...it, comments_count: (it.comments_count || 0) + 1 } : it
      )
    );
    setSelected((cur) =>
      cur && cur.id === suggestionId
        ? { ...cur, comments_count: (cur.comments_count || 0) + 1 }
        : cur
    );
  };

  return (
    <div className="h-full w-full p-4 md:p-6 overflow-y-auto">
      <div className="max-w-7xl mx-auto">
        <div className="flex flex-wrap items-center justify-between gap-3 mb-6">
          <div className="flex items-center gap-3 min-w-0">
            <div className="w-10 h-10 rounded-xl bg-primary/15 text-primary flex items-center justify-center shrink-0">
              <Lightbulb className="w-5 h-5" />
            </div>
            <div className="min-w-0">
              <h1 className="text-xl md:text-2xl font-bold text-foreground truncate">Ideias</h1>
              <p className="text-sm text-muted-foreground">Compartilhe ideias e acompanhe o andamento</p>
            </div>
          </div>

          <div className="flex items-center gap-2 flex-wrap">
            <button
              type="button"
              onClick={() => setShowModal(true)}
              className="inline-flex items-center gap-2 bg-primary hover:bg-primary/90 text-primary-foreground px-4 py-2 rounded-lg text-sm font-semibold shadow-md"
            >
              <Plus className="w-4 h-4" />
              Nova ideia
            </button>
          </div>
        </div>

        {loading ? (
          <div className="text-muted-foreground text-sm py-16 text-center">Carregando sugestões…</div>
        ) : (
          <div className="grid gap-4 lg:grid-cols-3 items-start">
            {COLUMNS.map((col) => {
              const list = byStatus[col.key] || [];
              const meta = STATUS_META[col.key];
              return (
                <section key={col.key} className="rounded-xl border border-border bg-card/60 min-h-[280px]">
                  <header className="flex items-center justify-between px-4 py-3 border-b border-border">
                    <div className="flex items-center gap-2">
                      <span className={`w-2 h-2 rounded-full ${meta.dot}`} />
                      <h2 className="text-sm font-semibold text-foreground">{col.title}</h2>
                    </div>
                    <span className="text-xs text-muted-foreground tabular-nums">{list.length}</span>
                  </header>
                  <div className="p-3 space-y-3">
                    {list.length === 0 ? (
                      <p className="text-xs text-muted-foreground text-center py-8">Nenhuma ideia</p>
                    ) : (
                      list.map((item) => (
                        <SuggestionCard key={item.id} item={item} onOpen={setSelected} />
                      ))
                    )}
                  </div>
                </section>
              );
            })}
          </div>
        )}
      </div>

      {showModal && (
        <div className="fixed inset-0 z-50 bg-black/60 flex items-center justify-center p-4 md:pl-48">
          <div className="w-full max-w-lg rounded-xl border border-border bg-card shadow-xl">
            <div className="flex items-center justify-between px-5 py-4 border-b border-border">
              <h2 className="text-base font-bold text-foreground">Nova ideia</h2>
              <button type="button" onClick={() => setShowModal(false)} className="text-muted-foreground hover:text-foreground">
                <X className="w-5 h-5" />
              </button>
            </div>
            <form onSubmit={handleCreate} className="p-5 space-y-4">
              <div className="flex flex-col gap-1.5">
                <label className="text-sm font-semibold text-foreground">Título</label>
                <input
                  value={form.title}
                  onChange={(e) => setForm((f) => ({ ...f, title: e.target.value }))}
                  className="bg-background border border-border text-foreground px-3 py-2 rounded-lg focus:outline-none focus:ring-2 focus:ring-primary"
                  placeholder="Ex: Integração com novo ERP"
                  maxLength={200}
                  required
                />
              </div>
              <div className="flex flex-col gap-1.5">
                <label className="text-sm font-semibold text-foreground">Descrição</label>
                <textarea
                  value={form.description}
                  onChange={(e) => setForm((f) => ({ ...f, description: e.target.value }))}
                  className="bg-background border border-border text-foreground px-3 py-2 rounded-lg focus:outline-none focus:ring-2 focus:ring-primary min-h-[140px] resize-y"
                  placeholder="Descreva a ideia e o problema que ela resolve…"
                  required
                />
              </div>
              <div className="flex justify-end gap-2 pt-1">
                <button
                  type="button"
                  onClick={() => setShowModal(false)}
                  className="px-4 py-2 rounded-lg text-sm font-semibold border border-border text-foreground hover:bg-muted"
                >
                  Cancelar
                </button>
                <button
                  type="submit"
                  disabled={saving}
                  className="px-4 py-2 rounded-lg text-sm font-semibold bg-primary hover:bg-primary/90 text-primary-foreground disabled:opacity-50"
                >
                  {saving ? 'Enviando…' : 'Enviar ideia'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {selected && (
        <SuggestionDetailModal
          item={selected}
          onClose={() => setSelected(null)}
          onCommentAdded={handleCommentAdded}
        />
      )}
    </div>
  );
}
