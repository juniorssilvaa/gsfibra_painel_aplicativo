import { useCallback, useEffect, useRef, useState } from 'react';
import axios from 'axios';
import {
  Megaphone,
  Plus,
  Send,
  Paperclip,
  ImagePlus,
  Trash2,
  Loader2,
  X,
  Link2,
  RefreshCw,
  Unplug,
  AlertTriangle,
  LayoutList,
  MessageSquare,
  Rocket,
  CheckCircle2,
} from 'lucide-react';
import { META_ADS_AUTH_MESSAGE, getMetaAdsConnectOrigin } from '../utils/metaConnect';
import { authHeaders, errorText } from '../utils/marketingApi';
import MarketingCampaigns from './MarketingCampaigns';

const POLL_MS = 2500;
const MAX_UPLOAD_BYTES = 8 * 1024 * 1024;
const EXPIRY_WARNING_DAYS = 7;

function screenshotName(file) {
  if (file.name && !/^image\.(png|jpe?g|gif|webp)$/i.test(file.name)) return file.name;
  const ext = (file.type.split('/')[1] || 'png').replace('jpeg', 'jpg');
  const stamp = new Date().toTimeString().slice(0, 8).replace(/:/g, '');
  return `captura-${stamp}.${ext}`;
}

function imageFilesFrom(list) {
  return Array.from(list || []).filter((f) => f && f.type?.startsWith('image/'));
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

const ACTION_DONE_STYLE = {
  applied: 'bg-emerald-500/10 text-emerald-600 border-emerald-500/30',
  running: 'bg-blue-500/10 text-blue-500 border-blue-500/30',
  error: 'bg-red-500/10 text-red-500 border-red-500/30',
  cancelled: 'bg-muted text-muted-foreground border-border',
};

function ActionCard({ action, deciding, disabled, onDecide }) {
  const isCreate = action.kind === 'create';
  if (action.status !== 'pending') {
    const label = action.status === 'applied' ? (isCreate ? 'Publicada na Meta' : 'Alterações aplicadas') : action.status_label;
    return (
      <div className={`inline-flex items-center gap-1.5 rounded-full border px-3 py-1 text-xs ${ACTION_DONE_STYLE[action.status] || ACTION_DONE_STYLE.cancelled}`}>
        {action.status === 'applied' && <CheckCircle2 className="w-3.5 h-3.5" />}
        {label}
        {action.error ? `: ${action.error}` : ''}
      </div>
    );
  }
  const confirmText = isCreate
    ? `Publicar a campanha "${action.nome}"${action.orcamento_diario ? ` com ${action.orcamento_diario} por dia` : ''} na Meta?`
    : `Aplicar as alterações na campanha "${action.nome}"?`;
  return (
    <div className="rounded-xl border border-primary/30 bg-primary/5 p-3 space-y-2 w-full max-w-md">
      <p className="text-xs text-muted-foreground">
        {isCreate ? 'Confira o resumo acima. Nada foi publicado ainda.' : 'Confira as mudanças acima. Nada foi aplicado ainda.'}
      </p>
      <div className="flex flex-wrap gap-2">
        <button
          type="button"
          disabled={disabled || deciding}
          onClick={() => window.confirm(confirmText) && onDecide(action, 'confirm')}
          className="inline-flex items-center gap-1.5 rounded-md bg-primary px-3 py-1.5 text-sm font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-50"
        >
          {deciding ? <Loader2 className="w-4 h-4 animate-spin" /> : <Rocket className="w-4 h-4" />}
          {deciding ? (isCreate ? 'Publicando…' : 'Aplicando…') : isCreate ? 'Publicar na Meta' : 'Aplicar na Meta'}
        </button>
        <button
          type="button"
          disabled={disabled || deciding}
          onClick={() => onDecide(action, 'cancel')}
          className="inline-flex items-center gap-1.5 rounded-md border border-border px-3 py-1.5 text-sm hover:bg-muted disabled:opacity-50"
        >
          <X className="w-4 h-4" /> Cancelar
        </button>
      </div>
    </div>
  );
}

function AssetThumb({ asset, className = '' }) {
  const src = useAuthImage(asset.id);
  return src ? (
    <img src={src} alt={asset.original_name || `Imagem #${asset.id}`} className={className} />
  ) : (
    <div className={`${className} flex items-center justify-center bg-muted`}>
      <Loader2 className="w-5 h-5 animate-spin text-muted-foreground" />
    </div>
  );
}

function pickDefault(current, items) {
  if (current && items.some((i) => i.id === current)) return current;
  return items.length === 1 ? items[0].id : '';
}

function MetaAdsPanel({ provedorId, onError, onStatusChange }) {
  const [status, setStatus] = useState(null);
  const [options, setOptions] = useState(null);
  const [choice, setChoice] = useState({ ad_account_id: '', page_id: '' });
  const [editing, setEditing] = useState(false);
  const [working, setWorking] = useState(false);
  const params = { provedor_id: provedorId };

  useEffect(() => {
    onStatusChange(status);
  }, [status, onStatusChange]);

  const applyOptions = useCallback((data, current) => {
    const accounts = data.ad_accounts || [];
    const pages = data.pages || [];
    setOptions({ ad_accounts: accounts, pages });
    setChoice({
      ad_account_id: pickDefault(current?.ad_account_id, accounts),
      page_id: pickDefault(current?.page_id, pages),
    });
  }, []);

  useEffect(() => {
    axios
      .get('/api/marketing/meta/', { headers: authHeaders(), params, skipErrorToast: true })
      .then((res) => setStatus(res.data))
      .catch(() => setStatus({ connected: false, ready: false }));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [provedorId]);

  const needsChoice = Boolean(status?.connected && (!status.ready || editing));

  useEffect(() => {
    if (!needsChoice || options) return;
    axios
      .get('/api/marketing/meta/options/', { headers: authHeaders(), params, skipErrorToast: true })
      .then((res) => applyOptions(res.data, status))
      .catch((err) => onError(errorText(err, 'Não foi possível listar suas contas de anúncios e Páginas.')));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [needsChoice, options]);

  useEffect(() => {
    const origin = getMetaAdsConnectOrigin();
    const onMessage = async (event) => {
      if (event.origin !== origin || event.data?.type !== META_ADS_AUTH_MESSAGE || !event.data.accessToken) return;
      setWorking(true);
      try {
        const res = await axios.post(
          '/api/marketing/meta/connect/',
          { access_token: event.data.accessToken },
          { headers: authHeaders(), params, skipErrorToast: true }
        );
        const { ad_accounts, pages, options_error, ...next } = res.data;
        setStatus(next);
        setEditing(!next.ready);
        if (ad_accounts) applyOptions({ ad_accounts, pages }, next);
        else setOptions(null);
        if (options_error) onError(options_error);
      } catch (err) {
        onError(errorText(err, 'Não foi possível conectar o Facebook.'));
      } finally {
        setWorking(false);
      }
    };
    window.addEventListener('message', onMessage);
    return () => window.removeEventListener('message', onMessage);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [provedorId, applyOptions]);

  const connect = () => {
    const url = `${getMetaAdsConnectOrigin()}/app/meta/ads-connect?tenant_origin=${encodeURIComponent(window.location.origin)}`;
    const width = 560;
    const height = 700;
    const left = window.screen.width / 2 - width / 2;
    const top = window.screen.height / 2 - height / 2;
    const popup = window.open(url, 'MetaAdsConnect', `width=${width},height=${height},left=${left},top=${top},scrollbars=yes`);
    if (!popup) onError('O navegador bloqueou a janela de login. Permita pop-ups para este site e tente de novo.');
  };

  const saveConfig = async () => {
    setWorking(true);
    try {
      const res = await axios.post('/api/marketing/meta/config/', choice, { headers: authHeaders(), params, skipErrorToast: true });
      setStatus(res.data);
      setEditing(false);
    } catch (err) {
      onError(errorText(err, 'Não foi possível salvar a conta e a Página.'));
    } finally {
      setWorking(false);
    }
  };

  const disconnect = async () => {
    if (!window.confirm('Desconectar o Facebook? As campanhas já publicadas continuam rodando na Meta.')) return;
    setWorking(true);
    try {
      const res = await axios.delete('/api/marketing/meta/', { headers: authHeaders(), params, skipErrorToast: true });
      setStatus(res.data);
      setOptions(null);
      setEditing(false);
    } catch (err) {
      onError(errorText(err, 'Não foi possível desconectar.'));
    } finally {
      setWorking(false);
    }
  };

  if (!status) return null;

  const buttonClass = 'inline-flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs bg-muted hover:bg-muted/80 disabled:opacity-50';

  if (!status.connected) {
    return (
      <div className="rounded-xl border border-amber-500/40 bg-amber-500/10 px-4 py-3 text-sm flex flex-wrap items-center gap-3">
        <Link2 className="w-4 h-4 text-amber-500" />
        <span className="flex-1 min-w-[220px]">
          {status.expired
            ? 'A conexão com o Facebook expirou. Conecte de novo para a IA voltar a publicar e analisar campanhas.'
            : 'Conecte o Facebook da empresa para a IA criar, editar e analisar campanhas na sua conta de anúncios.'}
        </span>
        <button
          type="button"
          onClick={connect}
          disabled={working}
          className="inline-flex items-center gap-2 px-4 py-2 rounded-md text-sm font-medium text-white bg-[#1877f2] hover:bg-[#166fe0] disabled:opacity-50"
        >
          {working ? <Loader2 className="w-4 h-4 animate-spin" /> : <Link2 className="w-4 h-4" />} Conectar com Facebook
        </button>
      </div>
    );
  }

  const daysLeft = status.expires_at ? (new Date(status.expires_at) - Date.now()) / 86400000 : null;
  const warnings = [];
  if (status.missing_scopes?.length) {
    warnings.push(`Faltam permissões: ${status.missing_scopes.join(', ')}. Clique em Reconectar e aceite todas.`);
  }
  if (daysLeft !== null && daysLeft <= EXPIRY_WARNING_DAYS) {
    warnings.push(
      `A conexão expira em ${new Date(status.expires_at).toLocaleDateString('pt-BR')}. Reconecte antes para a IA não parar.`
    );
  }

  return (
    <div className="rounded-xl border border-border bg-card px-4 py-3 text-sm space-y-2">
      {needsChoice ? (
        <div className="flex flex-wrap items-end gap-2">
          <label className="flex flex-col gap-1 min-w-[220px] flex-1">
            <span className="text-xs text-muted-foreground">Conta de anúncios</span>
            <select
              value={choice.ad_account_id}
              onChange={(e) => setChoice((c) => ({ ...c, ad_account_id: e.target.value }))}
              className="px-3 py-2 rounded-md border border-border bg-background text-sm"
              disabled={!options}
            >
              <option value="">{options ? 'Escolha a conta' : 'Carregando…'}</option>
              {options?.ad_accounts.map((a) => (
                <option key={a.id} value={a.id}>
                  {a.name} ({a.currency}){a.business ? ` · ${a.business}` : ''}{a.active ? '' : ' · inativa'}
                </option>
              ))}
            </select>
          </label>
          <label className="flex flex-col gap-1 min-w-[220px] flex-1">
            <span className="text-xs text-muted-foreground">Página do Facebook</span>
            <select
              value={choice.page_id}
              onChange={(e) => setChoice((c) => ({ ...c, page_id: e.target.value }))}
              className="px-3 py-2 rounded-md border border-border bg-background text-sm"
              disabled={!options}
            >
              <option value="">{options ? 'Escolha a Página' : 'Carregando…'}</option>
              {options?.pages.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.name}{p.instagram_username ? ` · Instagram @${p.instagram_username}` : ' · sem Instagram'}
                </option>
              ))}
            </select>
          </label>
          <button
            type="button"
            onClick={saveConfig}
            disabled={working || !choice.ad_account_id || !choice.page_id}
            className="px-4 py-2 rounded-md text-sm bg-primary text-primary-foreground disabled:opacity-50"
          >
            Salvar
          </button>
          {status.ready && (
            <button type="button" onClick={() => setEditing(false)} className="px-4 py-2 rounded-md text-sm bg-muted">
              Cancelar
            </button>
          )}
          {options && !options.ad_accounts.length && (
            <p className="w-full text-xs text-amber-500">
              Nenhuma conta de anúncios encontrada para este Facebook. Confira no Gerenciador de Negócios se ele tem acesso à conta.
            </p>
          )}
          {options && !options.pages.length && (
            <p className="w-full text-xs text-amber-500">
              Nenhuma Página encontrada. O Facebook conectado precisa administrar a Página da empresa.
            </p>
          )}
        </div>
      ) : (
        <div className="flex flex-wrap items-center gap-3">
          <span className="w-2 h-2 rounded-full bg-green-500" />
          <span className="flex-1 min-w-[220px]">
            Conectado como <strong>{status.fb_user_name}</strong> · Conta <strong>{status.ad_account_name}</strong> ({status.currency}) ·
            Página <strong>{status.page_name}</strong>
            {status.instagram_username
              ? ` · Instagram @${status.instagram_username}`
              : ' · sem Instagram (anúncios só no Facebook)'}
          </span>
          <div className="flex flex-wrap gap-1.5">
            <button type="button" onClick={() => setEditing(true)} disabled={working} className={buttonClass}>
              Trocar conta/Página
            </button>
            <button type="button" onClick={connect} disabled={working} className={buttonClass}>
              <RefreshCw className="w-3.5 h-3.5" /> Reconectar
            </button>
            <button type="button" onClick={disconnect} disabled={working} className={`${buttonClass} hover:text-red-500`}>
              <Unplug className="w-3.5 h-3.5" /> Desconectar
            </button>
          </div>
        </div>
      )}
      {warnings.map((w) => (
        <p key={w} className="flex items-start gap-1.5 text-xs text-amber-500">
          <AlertTriangle className="w-3.5 h-3.5 mt-0.5 shrink-0" /> {w}
        </p>
      ))}
    </div>
  );
}

export default function MarketingStudioPage({ provedorId }) {
  const [threads, setThreads] = useState([]);
  const [activeId, setActiveId] = useState(null);
  const [thread, setThread] = useState(null);
  const [input, setInput] = useState('');
  const [attachments, setAttachments] = useState([]);
  const [busy, setBusy] = useState(false);
  const [decidingId, setDecidingId] = useState(null);
  const [uploading, setUploading] = useState(0);
  const [dragOver, setDragOver] = useState(false);
  const [error, setError] = useState('');
  const [supportOnly, setSupportOnly] = useState(false);
  const [metaStatus, setMetaStatus] = useState(null);
  const [tab, setTab] = useState('chat');
  const fileRef = useRef(null);
  const bottomRef = useRef(null);
  const inputRef = useRef(null);
  const threadRequest = useRef(0);
  const openedCampaigns = useRef(false);

  const params = { provedor_id: provedorId };
  const metaReady = Boolean(metaStatus?.ready);

  useEffect(() => {
    if (metaReady && !openedCampaigns.current) {
      openedCampaigns.current = true;
      setTab('campanhas');
    }
    if (!metaReady && metaStatus) setTab('chat');
  }, [metaReady, metaStatus]);

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
    const request = ++threadRequest.current;
    try {
      const res = await axios.get(`/api/marketing/threads/${id}/`, { headers: authHeaders(), params, skipErrorToast: true });
      if (request !== threadRequest.current) return;
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
  }, [loadThreads]);

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
      return res.data;
    } catch (err) {
      setError(errorText(err, 'Não foi possível criar a conversa.'));
      return null;
    }
  };

  const deleteThread = async (id) => {
    if (!window.confirm('Apagar esta conversa? As campanhas já publicadas na Meta continuam rodando.')) return;
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

  const postMessage = async (threadId, content, referenceIds) => {
    const res = await axios.post(
      `/api/marketing/threads/${threadId}/messages/`,
      { content, reference_ids: referenceIds },
      { headers: authHeaders(), params, skipErrorToast: true }
    );
    threadRequest.current += 1;
    setThread(res.data);
    loadThreads();
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
      await postMessage(target.id, content, attachments.map((a) => a.id));
      setInput('');
      setAttachments([]);
    } catch (err) {
      setError(errorText(err, 'Não foi possível enviar a mensagem.'));
    } finally {
      setBusy(false);
    }
  };

  const decideAction = async (action, decision) => {
    if (!thread || decidingId) return;
    setDecidingId(action.id);
    setError('');
    try {
      const res = await axios.post(
        `/api/marketing/threads/${thread.id}/actions/${action.id}/`,
        { decision },
        { headers: authHeaders(), params, skipErrorToast: true }
      );
      threadRequest.current += 1;
      setThread(res.data);
      loadThreads();
    } catch (err) {
      setError(errorText(err, 'Não foi possível concluir a ação.'));
      loadThread(thread.id);
    } finally {
      setDecidingId(null);
    }
  };

  const analyzeWithAI = async (campaign, periodo, periodLabel) => {
    setTab('chat');
    setError('');
    const target = await newThread();
    if (!target) return;
    setBusy(true);
    try {
      await postMessage(
        target.id,
        `Analise a campanha "${campaign.nome}" (ID ${campaign.id}) no período: ${periodLabel.toLowerCase()} (periodo ${periodo}). ` +
          'Diga o que está funcionando, o que não está e o que você recomenda mudar.',
        []
      );
    } catch (err) {
      setError(errorText(err, 'Não foi possível pedir a análise.'));
    } finally {
      setBusy(false);
    }
  };

  const draftInChat = async (text) => {
    setTab('chat');
    await newThread();
    setInput(text);
    setTimeout(() => inputRef.current?.focus(), 50);
  };

  const editWithAI = (campaign) => draftInChat(`Quero editar a campanha "${campaign.nome}" (ID ${campaign.id}): `);

  const newCampaignWithAI = () => draftInChat('Quero criar uma nova campanha: ');

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
          <Megaphone className="w-10 h-10 text-primary mx-auto" />
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
          <Megaphone className="w-6 h-6 text-primary" />
          <div>
            <h1 className="text-xl font-bold flex items-center gap-2">
              Estúdio de Marketing
              <span className="px-2 py-0.5 rounded-md border border-green-500/40 bg-green-500/15 text-green-600 dark:text-green-400 text-xs font-semibold uppercase tracking-wide">
                Beta
              </span>
            </h1>
            <p className="text-sm text-muted-foreground">
              Crie, edite e analise campanhas na Meta com a IA. Você envia a imagem e o texto; a IA monta o público e só publica
              depois da sua confirmação.
            </p>
          </div>
        </div>
        {metaReady && (
          <div className="flex gap-1 rounded-lg bg-muted p-1">
            {[
              ['campanhas', 'Campanhas', <LayoutList key="i" className="w-4 h-4" />],
              ['chat', 'Conversas com a IA', <MessageSquare key="i" className="w-4 h-4" />],
            ].map(([key, label, icon]) => (
              <button
                key={key}
                type="button"
                onClick={() => setTab(key)}
                className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-md text-sm ${
                  tab === key ? 'bg-background shadow' : 'text-muted-foreground'
                }`}
              >
                {icon} {label}
              </button>
            ))}
          </div>
        )}
      </div>

      <div className="px-4 pt-3 md:px-6">
        <MetaAdsPanel provedorId={provedorId} onError={setError} onStatusChange={setMetaStatus} />
        {error && (
          <div className="mt-2 rounded-lg border border-red-500/40 bg-red-500/10 px-3 py-2 text-sm text-red-500 flex items-center justify-between gap-2">
            <span>{error}</span>
            <button type="button" onClick={() => setError('')}>
              <X className="w-4 h-4" />
            </button>
          </div>
        )}
      </div>

      {tab === 'campanhas' && metaReady ? (
        <MarketingCampaigns
          provedorId={provedorId}
          accountId={metaStatus.ad_account_id}
          onAnalyze={analyzeWithAI}
          onEdit={editWithAI}
          onNewCampaign={newCampaignWithAI}
          onError={setError}
        />
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
                <p className="text-sm text-muted-foreground">Ela vai como imagem do anúncio.</p>
              </div>
            )}
            <div className="flex-1 overflow-y-auto p-4 space-y-4">
              {!thread?.messages?.length && (
                <div className="h-full flex flex-col items-center justify-center text-center text-muted-foreground gap-2 px-6">
                  <Megaphone className="w-10 h-10 text-primary/60" />
                  <p className="font-medium text-foreground">Diga à IA o que você quer fazer nas suas campanhas.</p>
                  <p className="text-sm max-w-lg">
                    Por exemplo: “Crie um anúncio do plano de 500 mega para Fortaleza e Caucaia, 25 a 55 anos, R$ 30 por dia,
                    chamando no WhatsApp” ou “Como estão minhas campanhas nos últimos 7 dias?”.
                  </p>
                  <p className="text-sm max-w-lg">
                    Envie a imagem do anúncio colando com <strong>Ctrl+V</strong>, arrastando para o chat ou pelo clipe, e escreva o
                    texto que deve aparecer no anúncio. A IA mostra um resumo e só publica depois que você confirmar.
                  </p>
                </div>
              )}
              {thread?.messages?.map((m) => (
                <div key={m.id} className={`flex ${m.role === 'user' ? 'justify-end' : 'justify-start'}`}>
                  <div className={`max-w-[85%] space-y-2 ${m.role === 'user' ? 'items-end' : 'items-start'} flex flex-col`}>
                    {m.status === 'pending' ? (
                      <div className="inline-flex items-center gap-2 rounded-2xl bg-muted px-4 py-3 text-sm text-muted-foreground">
                        <Loader2 className="w-4 h-4 animate-spin" /> Trabalhando no seu pedido…
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
                    {m.action && m.status !== 'pending' && (
                      <ActionCard
                        action={m.action}
                        deciding={decidingId === m.action.id}
                        disabled={hasPending || busy || Boolean(decidingId)}
                        onDecide={decideAction}
                      />
                    )}
                    {m.assets?.length > 0 && (
                      <div className={`flex flex-wrap gap-3 ${m.role === 'user' ? 'justify-end' : ''}`}>
                        {m.assets.map((asset) => (
                          <div key={asset.id} className="w-28 text-center">
                            <AssetThumb asset={asset} className="w-28 h-28 rounded-lg border border-border object-contain bg-muted" />
                            <p className="mt-1 text-[11px] text-muted-foreground truncate">
                              #{asset.id} {asset.original_name}
                            </p>
                          </div>
                        ))}
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
                  title="Anexar imagem do anúncio (ou cole com Ctrl+V)"
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
                    hasPending
                      ? 'Aguarde a IA terminar…'
                      : 'Peça uma campanha, uma edição ou uma análise… (cole a imagem do anúncio com Ctrl+V)'
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
