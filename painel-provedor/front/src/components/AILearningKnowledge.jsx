import React, { useCallback, useEffect, useState } from 'react';
import axios from 'axios';
import { Check, Download, Pencil, Plus, Power, RotateCcw, Trash2, X } from 'lucide-react';
import { toast } from '../lib/notify';

const STATUS_TABS = [
  { id: 'suggested', label: 'Sugestões para revisar' },
  { id: 'approved', label: 'Ativos' },
  { id: 'disabled', label: 'Desativados' },
  { id: 'rejected', label: 'Rejeitados' },
];

const EMPTY_MESSAGES = {
  suggested:
    'Nenhuma sugestão aguardando revisão. Aprendizados simples entram sozinhos; só os que envolvem valores, descontos, prazos, promessas ou dados de pagamento esperam você aqui.',
  approved: 'Nenhum aprendizado ativo. Aprove sugestões ou cadastre um novo aprendizado.',
  disabled: 'Nenhum aprendizado desativado.',
  rejected: 'Nenhuma sugestão rejeitada.',
};

const EMPTY_FORM = { situation: '', answer: '', keywords: '' };

function authHeaders() {
  return { Authorization: `Token ${localStorage.getItem('token')}` };
}

function errorMessage(err, fallback) {
  return err?.response?.data?.error || fallback;
}

function LearningForm({ initial, onCancel, onSave, saving }) {
  const [form, setForm] = useState(initial || EMPTY_FORM);
  const set = (field) => (e) => setForm((prev) => ({ ...prev, [field]: e.target.value }));

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-[100] p-4">
      <div className="bg-card rounded-lg border w-full max-w-xl p-6">
        <h3 className="text-lg font-semibold text-foreground mb-4">{initial?.id ? 'Editar aprendizado' : 'Novo aprendizado'}</h3>
        <label className="block text-sm text-muted-foreground mb-1">Situação (quando a IA deve usar)</label>
        <input
          value={form.situation}
          onChange={set('situation')}
          maxLength={300}
          placeholder="Ex.: Cliente pergunta se pode pagar a fatura em lotérica"
          className="w-full mb-4 px-3 py-2 rounded-md border border-border bg-background text-foreground"
        />
        <label className="block text-sm text-muted-foreground mb-1">Como a IA deve agir</label>
        <textarea
          value={form.answer}
          onChange={set('answer')}
          maxLength={2000}
          rows={5}
          placeholder="Ex.: Informe que sim, o boleto pode ser pago em lotérica, banco ou aplicativo até o vencimento."
          className="w-full mb-4 px-3 py-2 rounded-md border border-border bg-background text-foreground"
        />
        <label className="block text-sm text-muted-foreground mb-1">Palavras-chave (separadas por vírgula)</label>
        <input
          value={form.keywords}
          onChange={set('keywords')}
          maxLength={500}
          placeholder="Ex.: lotérica, pagar, boleto, fatura"
          className="w-full mb-6 px-3 py-2 rounded-md border border-border bg-background text-foreground"
        />
        <div className="flex justify-end gap-2">
          <button type="button" onClick={onCancel} className="px-4 py-2 rounded-md border border-border text-sm">
            Cancelar
          </button>
          <button
            type="button"
            disabled={saving || !form.situation.trim() || !form.answer.trim()}
            onClick={() => onSave(form)}
            className="px-4 py-2 rounded-md bg-primary text-primary-foreground text-sm disabled:opacity-50"
          >
            {saving ? 'Salvando...' : 'Salvar'}
          </button>
        </div>
      </div>
    </div>
  );
}

function ActionButton({ onClick, title, Icon, className = '' }) {
  return (
    <button
      type="button"
      onClick={onClick}
      title={title}
      className={`flex items-center gap-1 px-2.5 py-1.5 rounded-md border border-border text-xs hover:bg-muted ${className}`}
    >
      <Icon className="w-3.5 h-3.5" />
      {title}
    </button>
  );
}

export default function AILearningKnowledge({ provedorId, counts, onChanged }) {
  const [status, setStatus] = useState('suggested');
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [editing, setEditing] = useState(null);
  const [saving, setSaving] = useState(false);

  const scope = provedorId ? { provedor_id: provedorId } : {};

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams({ status, ...(provedorId ? { provedor_id: provedorId } : {}) });
      const res = await axios.get(`/api/ai-learning/items/?${params}`, { headers: authHeaders(), skipErrorToast: true });
      setItems(res.data?.results || []);
    } catch (_) {
      setItems([]);
    } finally {
      setLoading(false);
    }
  }, [status, provedorId]);

  useEffect(() => {
    load();
  }, [load]);

  const refresh = () => {
    load();
    onChanged?.();
  };

  const update = async (item, payload, successMsg) => {
    try {
      await axios.patch(`/api/ai-learning/items/${item.id}/`, { ...payload, ...scope }, { headers: authHeaders(), skipErrorToast: true });
      toast.success(successMsg);
      refresh();
    } catch (err) {
      toast.error(errorMessage(err, 'Não foi possível atualizar o aprendizado'));
    }
  };

  const remove = async (item) => {
    if (!window.confirm('Excluir este aprendizado? A IA deixará de usá-lo.')) return;
    try {
      const params = provedorId ? `?provedor_id=${provedorId}` : '';
      await axios.delete(`/api/ai-learning/items/${item.id}/${params}`, { headers: authHeaders(), skipErrorToast: true });
      toast.success('Aprendizado excluído');
      refresh();
    } catch (err) {
      toast.error(errorMessage(err, 'Não foi possível excluir o aprendizado'));
    }
  };

  const save = async (form) => {
    setSaving(true);
    try {
      if (editing?.id) {
        await axios.patch(`/api/ai-learning/items/${editing.id}/`, { ...form, ...scope }, { headers: authHeaders(), skipErrorToast: true });
        toast.success('Aprendizado atualizado');
      } else {
        await axios.post('/api/ai-learning/items/', { ...form, ...scope }, { headers: authHeaders(), skipErrorToast: true });
        toast.success('Aprendizado cadastrado e ativo');
      }
      setEditing(null);
      refresh();
    } catch (err) {
      toast.error(errorMessage(err, 'Não foi possível salvar o aprendizado'));
    } finally {
      setSaving(false);
    }
  };

  const exportMarkdown = async () => {
    try {
      const params = provedorId ? `?provedor_id=${provedorId}` : '';
      const res = await axios.get(`/api/ai-learning/export/${params}`, {
        headers: authHeaders(),
        responseType: 'blob',
        skipErrorToast: true,
      });
      const url = URL.createObjectURL(res.data);
      const link = document.createElement('a');
      link.href = url;
      link.download = 'rag.md';
      link.click();
      URL.revokeObjectURL(url);
    } catch (_) {
      toast.error('Não foi possível exportar os aprendizados');
    }
  };

  const tabCount = (id) => (id === 'suggested' ? counts?.suggested : id === 'approved' ? counts?.approved : null);

  return (
    <div className="bg-card rounded-lg border p-4 mt-4">
      <div className="flex flex-wrap items-start justify-between gap-3 mb-3">
        <div>
          <h3 className="font-semibold text-foreground">Base de aprendizados</h3>
          <p className="text-xs text-muted-foreground">
            A cada mensagem, a IA consulta só os aprendizados ativos relacionados ao que o cliente perguntou.
            Sugestões simples são ativadas automaticamente; as sensíveis aguardam sua revisão.
          </p>
        </div>
        <div className="flex gap-2">
          <button
            type="button"
            onClick={exportMarkdown}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-md border border-border text-sm text-muted-foreground hover:text-foreground"
          >
            <Download className="w-4 h-4" /> Exportar .md
          </button>
          <button
            type="button"
            onClick={() => setEditing(EMPTY_FORM)}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-md bg-primary text-primary-foreground text-sm"
          >
            <Plus className="w-4 h-4" /> Novo aprendizado
          </button>
        </div>
      </div>

      <div className="flex flex-wrap gap-2 border-b border-border mb-4">
        {STATUS_TABS.map(({ id, label }) => {
          const count = tabCount(id);
          return (
            <button
              key={id}
              type="button"
              onClick={() => setStatus(id)}
              className={`px-3 py-2 -mb-px border-b-2 text-sm transition-colors ${
                status === id
                  ? 'border-primary text-primary'
                  : 'border-transparent text-muted-foreground hover:text-foreground'
              }`}
            >
              {label}
              {count ? ` (${count})` : ''}
            </button>
          );
        })}
      </div>

      {loading ? (
        <p className="text-sm text-muted-foreground">Carregando...</p>
      ) : items.length === 0 ? (
        <p className="text-sm text-muted-foreground">{EMPTY_MESSAGES[status]}</p>
      ) : (
        <ul className="space-y-3">
          {items.map((item) => (
            <li key={item.id} className="rounded-md border border-border p-3">
              {item.status === 'suggested' && item.review_reason && (
                <div className="inline-block mb-2 px-2 py-0.5 rounded bg-yellow-500/15 text-yellow-700 dark:text-yellow-400 text-xs">
                  Precisa de revisão: {item.review_reason.charAt(0).toLowerCase() + item.review_reason.slice(1)}
                </div>
              )}
              <div className="font-medium text-foreground">{item.situation}</div>
              <div className="text-sm text-muted-foreground mt-1 whitespace-pre-line">{item.answer}</div>
              {item.keywords && (
                <div className="flex flex-wrap gap-1 mt-2">
                  {item.keywords.split(',').map((kw) => kw.trim()).filter(Boolean).map((kw) => (
                    <span key={kw} className="px-2 py-0.5 rounded bg-muted text-xs text-muted-foreground">{kw}</span>
                  ))}
                </div>
              )}
              <div className="flex flex-wrap items-center justify-between gap-2 mt-3">
                <span className="text-xs text-muted-foreground">
                  {item.source === 'manual'
                    ? 'Cadastrado pelo provedor'
                    : item.auto_approved
                      ? 'Aprovado automaticamente pela IA'
                      : 'Sugerido pela IA'}
                  {item.status === 'approved' ? ` · usado ${item.times_used}x` : ''}
                </span>
                <div className="flex flex-wrap gap-2">
                  {(item.status === 'suggested' || item.status === 'rejected') && (
                    <ActionButton
                      title="Aprovar"
                      Icon={Check}
                      className="text-green-600"
                      onClick={() => update(item, { status: 'approved' }, 'Aprendizado aprovado: a IA já pode usar')}
                    />
                  )}
                  {item.status !== 'rejected' && (
                    <ActionButton title="Editar" Icon={Pencil} onClick={() => setEditing(item)} />
                  )}
                  {item.status === 'suggested' && (
                    <ActionButton
                      title="Rejeitar"
                      Icon={X}
                      className="text-red-500"
                      onClick={() => update(item, { status: 'rejected' }, 'Sugestão rejeitada')}
                    />
                  )}
                  {item.status === 'approved' && (
                    <ActionButton
                      title="Desativar"
                      Icon={Power}
                      onClick={() => update(item, { status: 'disabled' }, 'Aprendizado desativado')}
                    />
                  )}
                  {item.status === 'disabled' && (
                    <ActionButton
                      title="Reativar"
                      Icon={RotateCcw}
                      onClick={() => update(item, { status: 'approved' }, 'Aprendizado reativado')}
                    />
                  )}
                  {item.status !== 'suggested' && (
                    <ActionButton title="Excluir" Icon={Trash2} className="text-red-500" onClick={() => remove(item)} />
                  )}
                </div>
              </div>
            </li>
          ))}
        </ul>
      )}

      {editing && (
        <LearningForm
          initial={editing}
          saving={saving}
          onCancel={() => setEditing(null)}
          onSave={save}
        />
      )}
    </div>
  );
}
