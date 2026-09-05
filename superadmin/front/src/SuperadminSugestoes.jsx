import React, { useCallback, useEffect, useMemo, useState } from 'react';
import axios from 'axios';
import { Lightbulb, MessageCircle, X } from 'lucide-react';

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

function getAuthHeaders() {
  const token = localStorage.getItem('token') || localStorage.getItem('auth_token');
  return token ? { Authorization: `Token ${token}` } : {};
}

function formatDate(value) {
  if (!value) return '';
  try {
    return new Date(value).toLocaleString('pt-BR');
  } catch {
    return '';
  }
}

function SuggestionCommentsModal({ item, onClose }) {
  const [comments, setComments] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    let cancelled = false;
    (async () => {
      setLoading(true);
      setError('');
      try {
        const res = await axios.get(`/api/suggestions/${item.id}/comments/`, {
          headers: getAuthHeaders(),
        });
        const raw = res.data?.results ?? res.data;
        if (!cancelled) setComments(Array.isArray(raw) ? raw : []);
      } catch {
        if (!cancelled) {
          setError('Erro ao carregar comentários.');
          setComments([]);
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [item.id]);

  const statusMeta = STATUS_META[item.status] || STATUS_META.analise;

  return (
    <div className="fixed inset-0 z-50 bg-black/60 flex items-center justify-center p-4">
      <div className="w-full max-w-xl max-h-[85vh] rounded-xl border border-border bg-card shadow-xl flex flex-col overflow-hidden">
        <div className="flex items-start justify-between gap-3 px-5 py-4 border-b border-border shrink-0">
          <div className="min-w-0">
            <div className="flex items-center gap-2 mb-1">
              <span className={`w-2 h-2 rounded-full ${statusMeta.dot}`} />
              <span className="text-xs text-muted-foreground">{statusMeta.label}</span>
            </div>
            <h2 className="text-base font-bold text-foreground leading-snug">{item.title}</h2>
            <p className="text-xs text-muted-foreground mt-1 truncate">
              {item.created_by_name || item.author_name || 'Usuário'}
              {item.provedor_nome ? ` · ${item.provedor_nome}` : ''}
              {item.created_at ? ` · ${formatDate(item.created_at)}` : ''}
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
          ) : error ? (
            <p className="text-xs text-red-400 text-center py-6">{error}</p>
          ) : comments.length === 0 ? (
            <p className="text-xs text-muted-foreground text-center py-6">Nenhum comentário</p>
          ) : (
            comments.map((c) => (
              <div key={c.id} className="rounded-lg border border-border bg-background/60 p-3">
                <div className="flex items-center justify-between gap-2 mb-1.5">
                  <span className="text-xs font-semibold text-foreground truncate">
                    {c.author_name || 'Usuário'}
                    {c.provedor_nome ? (
                      <span className="font-normal text-muted-foreground"> · {c.provedor_nome}</span>
                    ) : null}
                  </span>
                  <span className="text-[10px] text-muted-foreground shrink-0">{formatDate(c.created_at)}</span>
                </div>
                <p className="text-sm text-foreground whitespace-pre-wrap">{c.body}</p>
              </div>
            ))
          )}
        </div>
      </div>
    </div>
  );
}

function SuggestionCard({ item, onDragStart, onOpenComments }) {
  return (
    <article
      draggable
      onDragStart={(e) => onDragStart(e, item)}
      className="rounded-xl border border-border bg-card overflow-hidden p-3.5 cursor-grab active:cursor-grabbing hover:border-orange-500/40 transition-colors"
    >
      <h3 className="text-sm font-semibold text-foreground leading-snug line-clamp-2 mb-1.5">
        {item.title}
      </h3>
      <p className="text-xs text-muted-foreground line-clamp-3 mb-3">{item.description}</p>
      <div className="flex items-center justify-between gap-2 text-[11px] text-muted-foreground">
        <div className="min-w-0 flex flex-col gap-0.5">
          <span className="truncate">{item.created_by_name || item.author_name || 'Usuário'}</span>
          {item.created_at ? (
            <span className="truncate tabular-nums">{formatDate(item.created_at)}</span>
          ) : null}
        </div>
        <button
          type="button"
          onClick={(e) => {
            e.stopPropagation();
            onOpenComments(item);
          }}
          onMouseDown={(e) => e.stopPropagation()}
          className="inline-flex items-center gap-1 shrink-0 hover:text-orange-400 transition-colors"
          title="Ver comentários"
        >
          <MessageCircle className="w-3.5 h-3.5" />
          {item.comments_count || 0}
        </button>
      </div>
    </article>
  );
}

export default function SuperadminSugestoes() {
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [draggingId, setDraggingId] = useState(null);
  const [dragOverStatus, setDragOverStatus] = useState(null);
  const [savingId, setSavingId] = useState(null);
  const [selected, setSelected] = useState(null);

  const fetchItems = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const res = await axios.get('/api/suggestions/', {
        headers: getAuthHeaders(),
      });
      const raw = res.data?.results ?? res.data;
      setItems(Array.isArray(raw) ? raw : []);
    } catch {
      setError('Erro ao carregar sugestões.');
      setItems([]);
    } finally {
      setLoading(false);
    }
  }, []);

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

  const updateStatus = async (item, nextStatus) => {
    if (!item || !nextStatus || item.status === nextStatus) return;
    const prevStatus = item.status;
    setSavingId(item.id);
    setItems((prev) =>
      prev.map((it) => (it.id === item.id ? { ...it, status: nextStatus } : it))
    );
    try {
      const res = await axios.patch(
        `/api/suggestions/${item.id}/`,
        { status: nextStatus },
        { headers: getAuthHeaders() }
      );
      setItems((prev) => prev.map((it) => (it.id === item.id ? { ...it, ...res.data } : it)));
    } catch {
      setItems((prev) =>
        prev.map((it) => (it.id === item.id ? { ...it, status: prevStatus } : it))
      );
      setError('Falha ao atualizar status. Tente novamente.');
    } finally {
      setSavingId(null);
    }
  };

  const handleDragStart = (e, item) => {
    setDraggingId(item.id);
    e.dataTransfer.setData('text/plain', String(item.id));
    e.dataTransfer.effectAllowed = 'move';
  };

  const handleDragEnd = () => {
    setDraggingId(null);
    setDragOverStatus(null);
  };

  const handleDragOver = (e, status) => {
    e.preventDefault();
    e.dataTransfer.dropEffect = 'move';
    setDragOverStatus(status);
  };

  const handleDrop = (e, status) => {
    e.preventDefault();
    const id = Number(e.dataTransfer.getData('text/plain') || draggingId);
    setDragOverStatus(null);
    setDraggingId(null);
    const item = items.find((it) => it.id === id);
    if (!item) return;
    updateStatus(item, status);
  };

  return (
    <div className="flex-1 p-4 md:p-6 overflow-y-auto">
      <div className="max-w-7xl mx-auto">
        <div className="flex items-center gap-3 mb-6">
          <div className="w-10 h-10 rounded-xl bg-orange-500/15 text-orange-400 flex items-center justify-center shrink-0">
            <Lightbulb className="w-5 h-5" />
          </div>
          <div className="min-w-0">
            <h1 className="text-xl md:text-2xl font-bold text-foreground truncate">Ideias</h1>
            <p className="text-sm text-muted-foreground">
              Arraste as sugestões entre as colunas para mudar o status
            </p>
          </div>
        </div>

        {error && <div className="mb-4 text-sm text-red-400">{error}</div>}

        {loading ? (
          <div className="text-muted-foreground text-sm py-16 text-center">Carregando sugestões…</div>
        ) : (
          <div className="grid gap-4 lg:grid-cols-3 items-start" onDragEnd={handleDragEnd}>
            {COLUMNS.map((col) => {
              const list = byStatus[col.key] || [];
              const meta = STATUS_META[col.key];
              const isOver = dragOverStatus === col.key;
              return (
                <section
                  key={col.key}
                  onDragOver={(e) => handleDragOver(e, col.key)}
                  onDragLeave={() => setDragOverStatus((s) => (s === col.key ? null : s))}
                  onDrop={(e) => handleDrop(e, col.key)}
                  className={`rounded-xl border min-h-[280px] transition-colors ${
                    isOver
                      ? 'border-orange-500 bg-orange-500/10'
                      : 'border-border bg-card/60'
                  }`}
                >
                  <header className="flex items-center justify-between px-4 py-3 border-b border-border">
                    <div className="flex items-center gap-2">
                      <span className={`w-2 h-2 rounded-full ${meta.dot}`} />
                      <h2 className="text-sm font-semibold text-foreground">{col.title}</h2>
                    </div>
                    <span className="text-xs text-muted-foreground tabular-nums">{list.length}</span>
                  </header>
                  <div className="p-3 space-y-3 min-h-[200px]">
                    {list.length === 0 ? (
                      <p className="text-xs text-muted-foreground text-center py-8">
                        {isOver ? 'Solte aqui' : 'Nenhuma ideia'}
                      </p>
                    ) : (
                      list.map((item) => (
                        <div
                          key={item.id}
                          className={
                            savingId === item.id || draggingId === item.id
                              ? 'opacity-60'
                              : ''
                          }
                        >
                          <SuggestionCard
                            item={item}
                            onDragStart={handleDragStart}
                            onOpenComments={setSelected}
                          />
                        </div>
                      ))
                    )}
                  </div>
                </section>
              );
            })}
          </div>
        )}
      </div>

      {selected && (
        <SuggestionCommentsModal item={selected} onClose={() => setSelected(null)} />
      )}
    </div>
  );
}
