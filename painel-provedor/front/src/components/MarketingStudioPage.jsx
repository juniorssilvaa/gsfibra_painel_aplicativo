import { useCallback, useEffect, useRef, useState } from 'react';
import axios from 'axios';
import {
  Sparkles,
  Plus,
  Send,
  Paperclip,
  Download,
  Star,
  Wand2,
  ImagePlus,
  Trash2,
  Loader2,
  KeyRound,
  X,
  MessageSquare,
  Images,
} from 'lucide-react';

const FORMAT_LABELS = { quadrado: 'Quadrado', story: 'Story', paisagem: 'Paisagem' };
const MODE_LABELS = { sistema: 'Texto pelo sistema', ia: 'Texto pela IA' };
const POLL_MS = 2500;
const MAX_UPLOAD_BYTES = 8 * 1024 * 1024;

function screenshotName(file) {
  if (file.name && !/^image\.(png|jpe?g|gif|webp)$/i.test(file.name)) return file.name;
  const ext = (file.type.split('/')[1] || 'png').replace('jpeg', 'jpg');
  const stamp = new Date().toTimeString().slice(0, 8).replace(/:/g, '');
  return `captura-${stamp}.${ext}`;
}

function imageFilesFrom(list) {
  return Array.from(list || []).filter((f) => f && f.type?.startsWith('image/'));
}

function authHeaders() {
  const token = localStorage.getItem('auth_token') || localStorage.getItem('token');
  return token ? { Authorization: `Token ${token}` } : {};
}

function errorText(err, fallback) {
  return err?.response?.data?.error || fallback;
}

function useAuthImage(assetId) {
  const [src, setSrc] = useState(null);
  useEffect(() => {
    if (!assetId) return undefined;
    let url = null;
    let cancelled = false;
    axios
      .get(`/api/marketing/assets/${assetId}/image/`, {
        headers: authHeaders(),
        responseType: 'blob',
        skipErrorToast: true,
      })
      .then((res) => {
        if (cancelled) return;
        url = URL.createObjectURL(res.data);
        setSrc(url);
      })
      .catch(() => {});
    return () => {
      cancelled = true;
      if (url) URL.revokeObjectURL(url);
    };
  }, [assetId]);
  return src;
}

function AssetThumb({ asset, className = '' }) {
  const src = useAuthImage(asset.id);
  return src ? (
    <img src={src} alt={asset.original_name || `Arte #${asset.id}`} className={className} />
  ) : (
    <div className={`${className} flex items-center justify-center bg-muted`}>
      <Loader2 className="w-5 h-5 animate-spin text-muted-foreground" />
    </div>
  );
}

async function downloadAsset(asset) {
  const res = await axios.get(`/api/marketing/assets/${asset.id}/image/`, {
    headers: authHeaders(),
    params: { download: 1 },
    responseType: 'blob',
  });
  const url = URL.createObjectURL(res.data);
  const link = document.createElement('a');
  link.href = url;
  link.download = `arte-${asset.id}.${asset.kind === 'reference' ? 'png' : 'jpg'}`;
  link.click();
  URL.revokeObjectURL(url);
}

function CreativeCard({ asset, onToggleApproved, onAdjust, onUseAsReference }) {
  return (
    <div className="rounded-xl border border-border bg-card overflow-hidden w-full max-w-[340px]">
      <AssetThumb asset={asset} className="w-full max-h-[420px] object-contain bg-black/40" />
      <div className="p-3 space-y-2">
        <div className="flex flex-wrap gap-1.5 text-[11px]">
          <span className="px-2 py-0.5 rounded bg-muted text-muted-foreground">#{asset.id}</span>
          {asset.formato && (
            <span className="px-2 py-0.5 rounded bg-muted text-muted-foreground">{FORMAT_LABELS[asset.formato] || asset.formato}</span>
          )}
          {asset.modo_texto && (
            <span className="px-2 py-0.5 rounded bg-muted text-muted-foreground">{MODE_LABELS[asset.modo_texto] || asset.modo_texto}</span>
          )}
          {asset.plano_nome && <span className="px-2 py-0.5 rounded bg-primary/15 text-primary">{asset.plano_nome}</span>}
        </div>
        {asset.modo_texto === 'ia' && (
          <p className="text-[11px] text-amber-500">Textos desenhados pela IA: confira preço e escrita antes de usar.</p>
        )}
        <div className="flex flex-wrap gap-1.5">
          <button
            type="button"
            onClick={() => downloadAsset(asset)}
            className="inline-flex items-center gap-1 px-2.5 py-1.5 rounded-md text-xs bg-muted hover:bg-muted/80"
          >
            <Download className="w-3.5 h-3.5" /> Baixar
          </button>
          <button
            type="button"
            onClick={() => onToggleApproved(asset)}
            className={`inline-flex items-center gap-1 px-2.5 py-1.5 rounded-md text-xs ${
              asset.approved ? 'bg-yellow-500/20 text-yellow-500' : 'bg-muted hover:bg-muted/80'
            }`}
          >
            <Star className={`w-3.5 h-3.5 ${asset.approved ? 'fill-current' : ''}`} /> {asset.approved ? 'Aprovada' : 'Aprovar'}
          </button>
          {onAdjust && (
            <button
              type="button"
              onClick={() => onAdjust(asset)}
              className="inline-flex items-center gap-1 px-2.5 py-1.5 rounded-md text-xs bg-muted hover:bg-muted/80"
            >
              <Wand2 className="w-3.5 h-3.5" /> Ajustar
            </button>
          )}
          {onUseAsReference && (
            <button
              type="button"
              onClick={() => onUseAsReference(asset)}
              className="inline-flex items-center gap-1 px-2.5 py-1.5 rounded-md text-xs bg-muted hover:bg-muted/80"
            >
              <ImagePlus className="w-3.5 h-3.5" /> Referência
            </button>
          )}
        </div>
      </div>
    </div>
  );
}

function EngineSettings({ provedorId, status, onSaved }) {
  const [open, setOpen] = useState(false);
  const [provider, setProvider] = useState(status?.extra_provider || 'openai');
  const [apiKey, setApiKey] = useState('');
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');

  const save = async (remove = false) => {
    setSaving(true);
    setError('');
    try {
      const res = await axios.post(
        '/api/marketing/settings/',
        remove ? { remove: true } : { image_provider: provider, image_api_key: apiKey },
        { headers: authHeaders(), params: { provedor_id: provedorId }, skipErrorToast: true }
      );
      setApiKey('');
      setOpen(false);
      onSaved(res.data);
    } catch (err) {
      setError(errorText(err, 'Não foi possível salvar a chave.'));
    } finally {
      setSaving(false);
    }
  };

  if (!status) return null;
  const engineName = status.provider === 'gemini' ? 'Gemini' : 'OpenAI';

  if (status.agent_key_supports_images) {
    return (
      <div className="rounded-xl border border-border bg-card px-4 py-3 text-sm flex items-center gap-3">
        <KeyRound className="w-4 h-4 text-muted-foreground" />
        <span>
          Imagens geradas com {engineName} usando a mesma chave do Agente de IA (Integrações). Para trocar, altere a chave lá.
        </span>
      </div>
    );
  }

  return (
    <div
      className={`rounded-xl border px-4 py-3 text-sm ${
        status.available ? 'border-border bg-card' : 'border-amber-500/40 bg-amber-500/10'
      }`}
    >
      <div className="flex flex-wrap items-center gap-3">
        <KeyRound className={`w-4 h-4 ${status.available ? 'text-muted-foreground' : 'text-amber-500'}`} />
        <span className="flex-1 min-w-[200px]">
          {status.available
            ? `Seu Agente de IA não gera imagens, então as artes usam a chave ${engineName} cadastrada aqui.`
            : 'Para gerar artes, cadastre uma chave OpenAI ou Gemini para imagens. O modelo do seu agente de IA não gera imagens.'}
        </span>
        <button type="button" onClick={() => setOpen((v) => !v)} className="px-3 py-1.5 rounded-md text-xs bg-muted hover:bg-muted/80">
          {open ? 'Fechar' : status.has_extra_key ? 'Trocar chave de imagem' : 'Usar outra chave para imagens'}
        </button>
      </div>
      {open && (
        <div className="mt-3 flex flex-wrap items-center gap-2">
          <select
            value={provider}
            onChange={(e) => setProvider(e.target.value)}
            className="px-3 py-2 rounded-md border border-border bg-background text-sm"
          >
            <option value="openai">OpenAI (gpt-image-1)</option>
            <option value="gemini">Gemini (imagem)</option>
          </select>
          <input
            type="password"
            value={apiKey}
            onChange={(e) => setApiKey(e.target.value)}
            placeholder={status.has_extra_key ? 'Deixe vazio para manter a chave atual' : 'Cole a chave da API'}
            className="flex-1 min-w-[220px] px-3 py-2 rounded-md border border-border bg-background text-sm"
            autoComplete="off"
          />
          <button
            type="button"
            disabled={saving}
            onClick={() => save(false)}
            className="px-3 py-2 rounded-md text-sm bg-primary text-primary-foreground disabled:opacity-50"
          >
            Salvar
          </button>
          {status.has_extra_key && (
            <button type="button" disabled={saving} onClick={() => save(true)} className="px-3 py-2 rounded-md text-sm bg-muted">
              Remover chave extra
            </button>
          )}
          {error && <p className="w-full text-xs text-red-500">{error}</p>}
        </div>
      )}
    </div>
  );
}

function ApprovedGallery({ provedorId, onToggleApproved, refreshKey }) {
  const [items, setItems] = useState(null);
  useEffect(() => {
    axios
      .get('/api/marketing/assets/', {
        headers: authHeaders(),
        params: { provedor_id: provedorId, approved: 1 },
        skipErrorToast: true,
      })
      .then((res) => setItems(res.data.results || []))
      .catch(() => setItems([]));
  }, [provedorId, refreshKey]);

  if (items === null) return <div className="p-8 text-center text-muted-foreground">Carregando artes…</div>;
  if (!items.length) {
    return (
      <div className="p-8 text-center text-muted-foreground">
        Nenhuma arte aprovada ainda. Aprove as artes que quiser usar nos anúncios clicando na estrela.
      </div>
    );
  }
  return (
    <div className="p-4 grid gap-4 grid-cols-1 sm:grid-cols-2 xl:grid-cols-3">
      {items.map((asset) => (
        <CreativeCard key={asset.id} asset={asset} onToggleApproved={onToggleApproved} />
      ))}
    </div>
  );
}

export default function MarketingStudioPage({ provedorId }) {
  const [view, setView] = useState('chat');
  const [threads, setThreads] = useState([]);
  const [activeId, setActiveId] = useState(null);
  const [thread, setThread] = useState(null);
  const [engine, setEngine] = useState(null);
  const [input, setInput] = useState('');
  const [attachments, setAttachments] = useState([]);
  const [busy, setBusy] = useState(false);
  const [uploading, setUploading] = useState(0);
  const [dragOver, setDragOver] = useState(false);
  const [error, setError] = useState('');
  const [galleryKey, setGalleryKey] = useState(0);
  const [supportOnly, setSupportOnly] = useState(false);
  const fileRef = useRef(null);
  const bottomRef = useRef(null);
  const inputRef = useRef(null);

  const params = { provedor_id: provedorId };

  const loadThreads = useCallback(async () => {
    try {
      const res = await axios.get('/api/marketing/threads/', { headers: authHeaders(), params, skipErrorToast: true });
      setThreads(res.data.results || []);
      return res.data.results || [];
    } catch (err) {
      if (err?.response?.data?.code === 'support_only') setSupportOnly(true);
      else setError(errorText(err, 'Não foi possível carregar o Estúdio.'));
      return [];
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [provedorId]);

  const loadThread = useCallback(async (id) => {
    if (!id) return;
    try {
      const res = await axios.get(`/api/marketing/threads/${id}/`, { headers: authHeaders(), params, skipErrorToast: true });
      setThread(res.data);
    } catch (err) {
      setError(errorText(err, 'Não foi possível abrir a conversa.'));
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [provedorId]);

  useEffect(() => {
    loadThreads().then((list) => {
      if (list.length) setActiveId(list[0].id);
    });
    axios
      .get('/api/marketing/settings/', { headers: authHeaders(), params, skipErrorToast: true })
      .then((res) => setEngine(res.data))
      .catch(() => {});
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [provedorId]);

  useEffect(() => {
    setThread(null);
    loadThread(activeId);
  }, [activeId, loadThread]);

  const hasPending = Boolean(thread?.messages?.some((m) => m.status === 'pending'));

  useEffect(() => {
    if (!hasPending || !activeId) return undefined;
    const timer = setInterval(() => loadThread(activeId), POLL_MS);
    return () => clearInterval(timer);
  }, [hasPending, activeId, loadThread]);

  useEffect(() => {
    if (!hasPending && thread) loadThreads();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [hasPending]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [thread?.messages?.length, hasPending]);

  const newThread = async () => {
    try {
      const res = await axios.post('/api/marketing/threads/', {}, { headers: authHeaders(), params, skipErrorToast: true });
      setThreads((prev) => [res.data, ...prev]);
      setActiveId(res.data.id);
      setView('chat');
      return res.data;
    } catch (err) {
      setError(errorText(err, 'Não foi possível criar a conversa.'));
      return null;
    }
  };

  const deleteThread = async (id) => {
    if (!window.confirm('Apagar esta conversa? As artes aprovadas continuam salvas.')) return;
    try {
      await axios.delete(`/api/marketing/threads/${id}/`, { headers: authHeaders(), params, skipErrorToast: true });
      const rest = threads.filter((t) => t.id !== id);
      setThreads(rest);
      if (activeId === id) setActiveId(rest[0]?.id || null);
    } catch (err) {
      setError(errorText(err, 'Não foi possível apagar a conversa.'));
    }
  };

  const uploadFiles = async (files) => {
    const all = Array.from(files || []);
    const images = imageFilesFrom(all);
    if (fileRef.current) fileRef.current.value = '';
    if (!images.length) {
      if (all.length) setError('Envie apenas imagens (PNG, JPG ou WEBP).');
      return;
    }
    const tooBig = images.filter((f) => f.size > MAX_UPLOAD_BYTES);
    const valid = images.filter((f) => f.size <= MAX_UPLOAD_BYTES);
    if (tooBig.length) setError('Imagem acima de 8 MB não pode ser enviada.');
    if (!valid.length) return;

    setUploading((n) => n + valid.length);
    try {
      let target = thread || (activeId ? { id: activeId } : null);
      if (!target) target = await newThread();
      if (!target) return;
      for (const file of valid) {
        const name = screenshotName(file);
        const form = new FormData();
        form.append('file', file, name);
        form.append('thread_id', target.id);
        try {
          const res = await axios.post('/api/marketing/assets/upload/', form, {
            headers: authHeaders(),
            params,
            skipErrorToast: true,
          });
          setAttachments((prev) => [...prev, res.data]);
        } catch (err) {
          setError(errorText(err, `Não foi possível enviar ${name}.`));
        }
      }
    } finally {
      setUploading((n) => Math.max(0, n - valid.length));
      inputRef.current?.focus();
    }
  };

  const onPaste = (e) => {
    const images = imageFilesFrom(e.clipboardData?.files);
    if (!images.length) return;
    e.preventDefault();
    uploadFiles(images);
  };

  const onDragOver = (e) => {
    if (!Array.from(e.dataTransfer?.types || []).includes('Files')) return;
    e.preventDefault();
    if (!dragOver) setDragOver(true);
  };

  const onDragLeave = (e) => {
    if (e.currentTarget.contains(e.relatedTarget)) return;
    setDragOver(false);
  };

  const onDrop = (e) => {
    if (!e.dataTransfer?.files?.length) return;
    e.preventDefault();
    setDragOver(false);
    uploadFiles(e.dataTransfer.files);
  };

  const send = async () => {
    const content = input.trim();
    if ((!content && !attachments.length) || busy || hasPending || uploading) return;
    setBusy(true);
    setError('');
    let target = thread || (activeId ? { id: activeId } : null);
    if (!target) target = await newThread();
    if (!target) {
      setBusy(false);
      return;
    }
    try {
      const res = await axios.post(
        `/api/marketing/threads/${target.id}/messages/`,
        { content, reference_ids: attachments.map((a) => a.id) },
        { headers: authHeaders(), params, skipErrorToast: true }
      );
      setThread(res.data);
      setInput('');
      setAttachments([]);
      loadThreads();
    } catch (err) {
      setError(errorText(err, 'Não foi possível enviar a mensagem.'));
    } finally {
      setBusy(false);
    }
  };

  const toggleApproved = async (asset) => {
    try {
      const res = await axios.patch(
        `/api/marketing/assets/${asset.id}/`,
        { approved: !asset.approved },
        { headers: authHeaders(), params, skipErrorToast: true }
      );
      setThread((prev) =>
        prev
          ? {
              ...prev,
              messages: prev.messages.map((m) => ({
                ...m,
                assets: m.assets.map((a) => (a.id === asset.id ? { ...a, approved: res.data.approved } : a)),
              })),
            }
          : prev
      );
      setGalleryKey((k) => k + 1);
    } catch (err) {
      setError(errorText(err, 'Não foi possível atualizar a arte.'));
    }
  };

  const adjust = (asset) => {
    setInput(`Ajuste a arte #${asset.id}: `);
    inputRef.current?.focus();
  };

  const useAsReference = (asset) => {
    setAttachments((prev) => (prev.some((a) => a.id === asset.id) ? prev : [...prev, asset]));
    inputRef.current?.focus();
  };

  const onKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      send();
    }
  };

  if (supportOnly) {
    return (
      <div className="h-full flex items-center justify-center bg-background text-foreground p-6">
        <div className="max-w-md text-center space-y-3">
          <Sparkles className="w-10 h-10 text-primary mx-auto" />
          <h1 className="text-xl font-bold">Estúdio de Marketing</h1>
          <p className="text-sm text-muted-foreground">
            Esta função está disponível apenas no painel em modo suporte.
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="h-full flex flex-col bg-background text-foreground">
      <div className="border-b border-border px-4 py-3 md:px-6 flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-3">
          <Sparkles className="w-6 h-6 text-primary" />
          <div>
            <h1 className="text-xl font-bold flex items-center gap-2">
              Estúdio de Marketing
              <span className="px-2 py-0.5 rounded-md border border-green-500/40 bg-green-500/15 text-green-600 dark:text-green-400 text-xs font-semibold uppercase tracking-wide">
                Beta
              </span>
            </h1>
            <p className="text-sm text-muted-foreground">
              Peça à IA artes para seus anúncios com base nos seus planos e no estilo que você quiser.
            </p>
          </div>
        </div>
        <div className="flex gap-1 rounded-lg bg-muted p-1">
          <button
            type="button"
            onClick={() => setView('chat')}
            className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-md text-sm ${view === 'chat' ? 'bg-background shadow' : 'text-muted-foreground'}`}
          >
            <MessageSquare className="w-4 h-4" /> Conversas
          </button>
          <button
            type="button"
            onClick={() => setView('gallery')}
            className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-md text-sm ${view === 'gallery' ? 'bg-background shadow' : 'text-muted-foreground'}`}
          >
            <Images className="w-4 h-4" /> Artes aprovadas
          </button>
        </div>
      </div>

      <div className="px-4 pt-3 md:px-6">
        <EngineSettings provedorId={provedorId} status={engine} onSaved={setEngine} />
        {error && (
          <div className="mt-2 rounded-lg border border-red-500/40 bg-red-500/10 px-3 py-2 text-sm text-red-500 flex items-center justify-between gap-2">
            <span>{error}</span>
            <button type="button" onClick={() => setError('')}>
              <X className="w-4 h-4" />
            </button>
          </div>
        )}
      </div>

      {view === 'gallery' ? (
        <div className="flex-1 overflow-y-auto">
          <ApprovedGallery provedorId={provedorId} onToggleApproved={toggleApproved} refreshKey={galleryKey} />
        </div>
      ) : (
        <div className="flex-1 min-h-0 flex gap-4 p-4 md:px-6">
          <aside className="hidden md:flex w-64 shrink-0 flex-col rounded-xl border border-border bg-card overflow-hidden">
            <button
              type="button"
              onClick={newThread}
              className="m-3 inline-flex items-center justify-center gap-2 px-3 py-2 rounded-lg bg-primary text-primary-foreground text-sm"
            >
              <Plus className="w-4 h-4" /> Nova conversa
            </button>
            <ul className="flex-1 overflow-y-auto px-2 pb-2 space-y-1">
              {threads.map((t) => (
                <li key={t.id} className="group flex items-center">
                  <button
                    type="button"
                    onClick={() => setActiveId(t.id)}
                    className={`flex-1 text-left truncate px-3 py-2 rounded-md text-sm ${
                      t.id === activeId ? 'bg-primary/15 text-primary' : 'hover:bg-muted'
                    }`}
                  >
                    {t.title}
                  </button>
                  <button
                    type="button"
                    onClick={() => deleteThread(t.id)}
                    className="p-1.5 opacity-0 group-hover:opacity-100 text-muted-foreground hover:text-red-500"
                    title="Apagar conversa"
                  >
                    <Trash2 className="w-3.5 h-3.5" />
                  </button>
                </li>
              ))}
            </ul>
          </aside>

          <section
            className="relative flex-1 min-w-0 flex flex-col rounded-xl border border-border bg-card overflow-hidden"
            onPaste={onPaste}
            onDragOver={onDragOver}
            onDragLeave={onDragLeave}
            onDrop={onDrop}
          >
            {dragOver && (
              <div className="absolute inset-0 z-20 flex flex-col items-center justify-center gap-2 rounded-xl border-2 border-dashed border-primary bg-background/85 text-center pointer-events-none">
                <ImagePlus className="w-10 h-10 text-primary" />
                <p className="font-medium">Solte a imagem aqui</p>
                <p className="text-sm text-muted-foreground">Ela vai como exemplo de arte ou logo para a IA.</p>
              </div>
            )}
            <div className="flex-1 overflow-y-auto p-4 space-y-4">
              {!thread?.messages?.length && (
                <div className="h-full flex flex-col items-center justify-center text-center text-muted-foreground gap-2 px-6">
                  <Sparkles className="w-10 h-10 text-primary/60" />
                  <p className="font-medium text-foreground">Diga à IA como você quer a arte.</p>
                  <p className="text-sm max-w-lg">
                    Por exemplo: qual plano divulgar, o formato (feed ou story), cores, estilo, se tem pessoas ou não e a chamada.
                    A IA usa os planos e preços cadastrados no painel.
                  </p>
                  <p className="text-sm max-w-lg">
                    Para mostrar exemplos de artes que você gosta, tire um print e cole aqui com <strong>Ctrl+V</strong>, arraste a
                    imagem para o chat ou use o clipe. A logo também vai por aqui.
                  </p>
                </div>
              )}
              {thread?.messages?.map((m) => (
                <div key={m.id} className={`flex ${m.role === 'user' ? 'justify-end' : 'justify-start'}`}>
                  <div className={`max-w-[85%] space-y-2 ${m.role === 'user' ? 'items-end' : 'items-start'} flex flex-col`}>
                    {m.status === 'pending' ? (
                      <div className="inline-flex items-center gap-2 rounded-2xl bg-muted px-4 py-3 text-sm text-muted-foreground">
                        <Loader2 className="w-4 h-4 animate-spin" /> Trabalhando no seu pedido… artes levam até um minuto.
                      </div>
                    ) : (
                      m.content && (
                        <div
                          className={`rounded-2xl px-4 py-3 text-sm whitespace-pre-wrap ${
                            m.role === 'user'
                              ? 'bg-primary text-primary-foreground'
                              : m.status === 'error'
                                ? 'bg-red-500/10 text-red-500 border border-red-500/30'
                                : 'bg-muted text-foreground'
                          }`}
                        >
                          {m.content}
                        </div>
                      )
                    )}
                    {m.assets?.length > 0 && (
                      <div className={`flex flex-wrap gap-3 ${m.role === 'user' ? 'justify-end' : ''}`}>
                        {m.assets.map((asset) =>
                          asset.kind === 'reference' ? (
                            <div key={asset.id} className="w-28 text-center">
                              <AssetThumb asset={asset} className="w-28 h-28 rounded-lg border border-border object-contain bg-muted" />
                              <p className="mt-1 text-[11px] text-muted-foreground truncate">#{asset.id} {asset.original_name}</p>
                            </div>
                          ) : (
                            <CreativeCard
                              key={asset.id}
                              asset={asset}
                              onToggleApproved={toggleApproved}
                              onAdjust={adjust}
                              onUseAsReference={useAsReference}
                            />
                          )
                        )}
                      </div>
                    )}
                  </div>
                </div>
              ))}
              <div ref={bottomRef} />
            </div>

            <div className="border-t border-border p-3 space-y-2">
              {(attachments.length > 0 || uploading > 0) && (
                <div className="flex flex-wrap gap-2">
                  {attachments.map((a) => (
                    <div key={a.id} className="relative">
                      <AssetThumb asset={a} className="w-16 h-16 rounded-md border border-border object-cover" />
                      <button
                        type="button"
                        onClick={() => setAttachments((prev) => prev.filter((x) => x.id !== a.id))}
                        className="absolute -top-1.5 -right-1.5 rounded-full bg-background border border-border p-0.5"
                      >
                        <X className="w-3 h-3" />
                      </button>
                      <span className="absolute bottom-0 left-0 right-0 text-center text-[10px] bg-black/60 text-white rounded-b-md">#{a.id}</span>
                    </div>
                  ))}
                  {uploading > 0 && (
                    <div className="w-16 h-16 rounded-md border border-dashed border-border flex flex-col items-center justify-center gap-1 text-[10px] text-muted-foreground">
                      <Loader2 className="w-4 h-4 animate-spin" />
                      Enviando…
                    </div>
                  )}
                </div>
              )}
              <div className="flex items-end gap-2">
                <input
                  ref={fileRef}
                  type="file"
                  accept="image/*"
                  multiple
                  className="hidden"
                  onChange={(e) => uploadFiles(e.target.files)}
                />
                <button
                  type="button"
                  onClick={() => fileRef.current?.click()}
                  className="p-2.5 rounded-lg bg-muted hover:bg-muted/80"
                  title="Anexar logo ou exemplo de arte (ou cole um print com Ctrl+V)"
                >
                  <Paperclip className="w-5 h-5" />
                </button>
                <textarea
                  ref={inputRef}
                  value={input}
                  onChange={(e) => setInput(e.target.value)}
                  onKeyDown={onKeyDown}
                  rows={2}
                  placeholder={
                    hasPending ? 'Aguarde a IA terminar…' : 'Descreva a arte ou o ajuste que você quer… (cole prints de exemplo com Ctrl+V)'
                  }
                  className="flex-1 resize-none rounded-lg border border-border bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary/40"
                />
                <button
                  type="button"
                  onClick={send}
                  disabled={busy || hasPending || uploading > 0 || (!input.trim() && !attachments.length)}
                  className="p-2.5 rounded-lg bg-primary text-primary-foreground disabled:opacity-50"
                  title="Enviar"
                >
                  {busy ? <Loader2 className="w-5 h-5 animate-spin" /> : <Send className="w-5 h-5" />}
                </button>
              </div>
            </div>
          </section>
        </div>
      )}
    </div>
  );
}
