import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import axios from 'axios'
import {
  LayoutDashboard,
  Users,
  Bell,
  AlertTriangle,
  Settings,
  Package,
  PlugZap,
  Send,
  Plus,
  Trash2,
  KeyRound,
  ChevronsLeft,
  ChevronsRight,
  User,
  Search,
  X,
  Eye,
  EyeOff,
  History,
  Megaphone,
  Info,
  CheckCircle2,
  Home,
  Pin,
  Zap,
  Gauge,
  Wifi,
  Pencil,
  Copy,
  RefreshCw,
  Router,
  Settings2,
  UserCog,
  Building2,
  Paperclip,
  FileText,
  Calendar,
  Save,
  Palette,
  Upload,
  Headset,
  Barcode,
  ReceiptText,
  LockOpen,
  ChartColumn,
  Video,
  Activity,
  Layers,
  MonitorSmartphone,
  Menu,
  Globe,
  Clock,
  ChevronDown,
  MessageCircle,
  Phone,
  CreditCard,
  LogIn,
  CircleCheck,
} from 'lucide-react'
import {
  PieChart,
  Pie,
  Cell,
  ResponsiveContainer,
  BarChart,
  Bar,
  Line,
  ComposedChart,
  XAxis,
  YAxis,
  Tooltip,
  CartesianGrid,
} from 'recharts'
import Topbar from './components/Topbar'
import { useAuth } from './contexts/AuthContext'
import { toast } from './lib/notify'

const authHeaders = () => ({
  Authorization: `Token ${localStorage.getItem('token') || localStorage.getItem('auth_token') || ''}`,
})

const NAV = [
  ['dashboard', 'Dashboard', LayoutDashboard],
  ['clients', 'Clientes', Users],
  ['push', 'Notificações', Bell],
  ['push-sent', 'Enviadas', History],
  ['warnings', 'Comunicados', Megaphone],
  ['config', 'Aplicativo', Settings],
  ['appearance', 'Aparência', Palette],
  ['plans', 'Planos', Package],
  ['sgp', 'Integrações', PlugZap],
  ['staff', 'Usuários', UserCog],
  ['company', 'Minha Empresa', Building2],
]

const PANEL_CARD =
  'rounded-xl border border-border bg-card p-6 shadow-sm'
const PANEL_INPUT =
  'w-full rounded-lg border border-border bg-background px-3 py-2 text-sm text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring'

function SecretField({
  value,
  onChange,
  placeholder,
  readOnly = false,
  className = '',
  rightPaddingClass = 'pr-10',
  eyeClassName = 'right-2',
  children,
}) {
  const [visible, setVisible] = useState(false)
  return (
    <div className="relative">
      <input
        type={visible ? 'text' : 'password'}
        value={value}
        onChange={onChange}
        placeholder={placeholder}
        readOnly={readOnly}
        autoComplete="off"
        spellCheck={false}
        className={`${PANEL_INPUT} ${rightPaddingClass} ${className}`}
      />
      <button
        type="button"
        onClick={() => setVisible((v) => !v)}
        className={`absolute top-1/2 z-10 -translate-y-1/2 rounded p-1 text-muted-foreground hover:text-foreground ${eyeClassName}`}
        title={visible ? 'Ocultar token' : 'Mostrar token'}
        aria-label={visible ? 'Ocultar token' : 'Mostrar token'}
      >
        {visible ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
      </button>
      {children}
    </div>
  )
}
const BTN_PRIMARY =
  'inline-flex items-center justify-center gap-2 rounded-lg bg-orange-500 px-4 py-2 text-sm font-semibold text-white shadow-sm transition-colors hover:bg-orange-600'
const BTN_GHOST =
  'inline-flex items-center justify-center gap-2 rounded-lg border border-border bg-secondary px-3 py-2 text-sm text-secondary-foreground transition-colors hover:bg-muted'
const BTN_EDIT =
  'inline-flex items-center justify-center rounded-lg bg-orange-500 p-2 text-white shadow-sm transition-colors hover:bg-orange-600'
const BTN_DANGER =
  'inline-flex items-center justify-center rounded-lg bg-red-500 p-2 text-white shadow-sm transition-colors hover:bg-red-600 disabled:opacity-40'

const CHART_BLUE = '#0D70B3'
const CHART_CYAN = '#4dd0e1'
const CHART_MUTED = '#3f3f46'
const CHART_ORANGE = '#ea580c'

const FORM_TABS = new Set([])

const APP_SHORTCUTS = ['PLANOS', 'CONSUMO', 'CONTRATO ASSINADO', 'NOTA FISCAL']
const APP_TOOLS = [
  { key: 'tool_speed_test', label: 'Teste de Velocidade' },
  { key: 'tool_wifi', label: 'Meu Wi-Fi' },
  { key: 'tool_cameras', label: 'Câmeras' },
  { key: 'tool_connected_devices', label: 'Dispositivos Conectados' },
]

function formatDateTime(value) {
  if (!value) return '—'
  try {
    return new Date(value).toLocaleString('pt-BR')
  } catch {
    return '—'
  }
}

function initialLetter(name) {
  const s = (name || 'U').trim()
  return (s[0] || 'U').toUpperCase()
}

function ClientsPanel({ clients, search, setSearch, onFilter, onDelete, onSaveClient, onSendPush }) {
  const [selected, setSelected] = useState(() => new Set())
  const [manageUser, setManageUser] = useState(null)
  const [manageForm, setManageForm] = useState({ active: true, tags: '' })
  const [saving, setSaving] = useState(false)

  const allIds = clients.map((c) => c.id)
  const allSelected = allIds.length > 0 && allIds.every((id) => selected.has(id))
  const selectedClients = clients.filter((c) => selected.has(c.id))

  const toggleOne = (id) => {
    setSelected((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  const toggleAll = () => {
    setSelected((prev) => {
      if (allIds.every((id) => prev.has(id))) return new Set()
      return new Set(allIds)
    })
  }

  const openManage = (c) => {
    setManageUser(c)
    setManageForm({ active: !!c.active, tags: c.tags || '' })
  }

  const saveManage = async (e) => {
    e.preventDefault()
    if (!manageUser) return
    setSaving(true)
    try {
      await onSaveClient(manageUser.id, {
        active: manageForm.active,
        tags: manageForm.tags || '',
      })
      setManageUser(null)
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="space-y-4 p-6">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
        <div className="relative min-w-0 flex-1">
          <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
          <input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && onFilter()}
            placeholder="Buscar por nome, CPF, login…"
            className={`${PANEL_INPUT} pl-9`}
          />
        </div>
        <button type="button" onClick={onFilter} className={`${BTN_PRIMARY} shrink-0`}>
          Filtrar
        </button>
      </div>

      <div className="flex items-center justify-between rounded-xl border border-border bg-muted/40 px-4 py-3">
        <label className="flex cursor-pointer items-center gap-3">
          <input
            type="checkbox"
            checked={allSelected}
            onChange={toggleAll}
            className="h-4 w-4 rounded border-border"
          />
          <span className="text-xs font-bold uppercase tracking-wide text-muted-foreground">
            Selecionar todos da página
          </span>
        </label>
        <div className="flex flex-wrap items-center gap-2">
          {selectedClients.length > 0 && (
            <button
              type="button"
              onClick={() => onSendPush?.(selectedClients)}
              className={`${BTN_PRIMARY} text-xs`}
            >
              <Send className="h-3.5 w-3.5" />
              Enviar notificação ({selectedClients.length})
            </button>
          )}
          <span className="rounded-full border border-border bg-background px-3 py-1 text-[11px] font-bold uppercase tracking-wider text-muted-foreground">
            {clients.length} registro{clients.length === 1 ? '' : 's'}
            {selected.size > 0 ? ` · ${selected.size} selecionado${selected.size === 1 ? '' : 's'}` : ''}
          </span>
        </div>
      </div>

      <div className="space-y-4">
        {clients.map((c) => {
          const devices = c.devices || []
          const pushOk = devices.some((d) => d.push_confirmed)
          const pushAt = devices.find((d) => d.push_confirmed)?.push_confirmed_at
          return (
            <div
              key={c.id}
              className="overflow-hidden rounded-2xl border border-border bg-card shadow-sm transition-colors hover:border-primary/40"
            >
              <div className="border-b border-border p-5 sm:p-6">
                <div className="flex items-start justify-between gap-3">
                  <div className="flex min-w-0 items-start gap-3 sm:gap-4">
                    <input
                      type="checkbox"
                      checked={selected.has(c.id)}
                      onChange={() => toggleOne(c.id)}
                      className="mt-2.5 h-4 w-4 shrink-0 rounded border-border"
                    />
                    <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-muted text-sm font-bold text-foreground">
                      {initialLetter(c.name)}
                    </div>
                    <div className="min-w-0">
                      <div className="mb-1 flex flex-wrap items-center gap-2">
                        <h3 className="truncate text-base font-bold text-foreground sm:text-lg">
                          {c.name || 'Sem nome'}
                        </h3>
                        <span
                          className={`rounded-full px-2 py-0.5 text-xs font-bold uppercase ${
                            c.active
                              ? 'bg-emerald-500/15 text-emerald-500'
                              : 'bg-destructive/15 text-destructive'
                          }`}
                        >
                          {c.active ? 'Ativo' : 'Inativo'}
                        </span>
                      </div>
                      <div className="flex flex-wrap items-center gap-2 text-sm">
                        <span className="font-mono text-muted-foreground">CPF: {c.cpf}</span>
                        <button
                          type="button"
                          onClick={() => {
                            const q = c.cpf || ''
                            setSearch(q)
                            onFilter(q)
                          }}
                          className="rounded-md border border-orange-500/40 bg-orange-500/10 px-2 py-0.5 text-xs font-medium text-orange-400 hover:bg-orange-500/20"
                        >
                          Filtrar
                        </button>
                        <span className="rounded-full border border-border px-2 py-0.5 text-xs text-muted-foreground">
                          {c.devices_count ?? devices.length} dispositivo
                          {(c.devices_count ?? devices.length) === 1 ? '' : 's'}
                        </span>
                      </div>
                    </div>
                  </div>
                  <div className="flex shrink-0 items-center gap-2">
                    <span className="hidden text-xs text-muted-foreground sm:inline">
                      {c.tags || 'Sem tags'}
                    </span>
                    <button
                      type="button"
                      onClick={() => openManage(c)}
                      className="rounded-lg p-2 text-primary transition-colors hover:bg-muted"
                      title="Gerenciar cliente"
                    >
                      <Settings className="h-5 w-5" />
                    </button>
                  </div>
                </div>

                {devices.length > 0 && (
                  <div className="mt-4 flex flex-wrap gap-2">
                    {devices.map((d) => (
                      <div
                        key={d.id}
                        className="flex flex-wrap items-center gap-2 rounded-lg border border-border bg-muted/50 px-3 py-1.5 text-xs text-muted-foreground"
                      >
                        <span className="font-semibold">Sistema operacional:</span>
                        <span
                          className={`font-bold uppercase ${
                            d.platform === 'android' ? 'text-emerald-500' : 'text-primary'
                          }`}
                        >
                          {d.platform}
                        </span>
                        <span className="mx-0.5 h-3 w-px bg-border" />
                        <span className="font-semibold">Modelo:</span>
                        <span className="font-bold text-foreground">{d.model || '—'}</span>
                        <span className="mx-0.5 h-3 w-px bg-border" />
                        <span className="font-semibold text-foreground">{d.os_version || '—'}</span>
                        <span className="mx-0.5 h-3 w-px bg-border" />
                        {d.push_confirmed ? (
                          <span className="rounded bg-emerald-500/20 px-2 py-0.5 text-[11px] font-bold text-emerald-500">
                            PUSH OK
                          </span>
                        ) : (
                          <span className="rounded bg-orange-500/20 px-2 py-0.5 text-[11px] font-bold text-orange-400">
                            PUSH PENDENTE
                          </span>
                        )}
                        <span className="mx-0.5 h-3 w-px bg-border" />
                        <span>Criado: {formatDateTime(d.created_at || d.last_active)}</span>
                      </div>
                    ))}
                  </div>
                )}
              </div>

              <div className="grid grid-cols-1 border-t border-border bg-muted/20 md:grid-cols-2">
                <div className="flex items-center gap-3 border-b border-border p-5 md:border-b-0 md:border-r">
                  <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-primary/15 text-xs font-bold text-primary">
                    ID
                  </div>
                  <div>
                    <p className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
                      Cliente
                    </p>
                    <p className="font-mono text-sm text-foreground">
                      #{c.customer_id || '—'}
                    </p>
                    <p className="mt-2 text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
                      Login PPPoE
                    </p>
                    <p className="font-mono text-sm font-bold text-indigo-400">
                      {c.pppoe_login || '—'}
                    </p>
                  </div>
                </div>

                <div className="p-5">
                  <div className="mb-1 flex items-center justify-between gap-2">
                    <p className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
                      Último acesso
                    </p>
                    <span
                      className={`rounded-full px-2 py-0.5 text-[10px] font-semibold ${
                        c.is_online
                          ? 'bg-emerald-500/15 text-emerald-500'
                          : 'bg-muted text-muted-foreground'
                      }`}
                    >
                      {c.is_online ? 'Online' : 'Offline'}
                    </span>
                  </div>
                  <p className="mb-4 font-mono text-sm text-foreground">
                    {formatDateTime(c.last_active_at)}
                  </p>
                  <p className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
                    Último push
                  </p>
                  <div className="mt-1 flex flex-wrap items-center gap-2">
                    {pushOk ? (
                      <>
                        <span className="rounded-full bg-emerald-500/15 px-2 py-0.5 text-[10px] font-bold uppercase tracking-wide text-emerald-500">
                          Enviado
                        </span>
                        <span className="font-mono text-xs text-muted-foreground">
                          {formatDateTime(pushAt)}
                        </span>
                      </>
                    ) : (
                      <>
                        <span className="rounded-full bg-orange-500/15 px-2 py-0.5 text-[10px] font-bold uppercase tracking-wide text-orange-400">
                          Pendente
                        </span>
                        <span className="font-mono text-xs text-muted-foreground">—</span>
                      </>
                    )}
                  </div>
                </div>
              </div>
            </div>
          )
        })}

        {clients.length === 0 && (
          <div className="rounded-xl border border-dashed border-border py-12 text-center text-sm text-muted-foreground">
            Nenhum cliente encontrado com os filtros selecionados.
          </div>
        )}
      </div>

      {manageUser && (
        <div className="fixed inset-0 z-50 flex items-end justify-center bg-black/60 p-4 sm:items-center">
          <div className="w-full max-w-lg overflow-hidden rounded-2xl border border-border bg-card shadow-xl">
            <div className="flex items-center justify-between border-b border-border p-5">
              <h3 className="text-lg font-bold text-foreground">Gerenciar cliente</h3>
              <button
                type="button"
                onClick={() => setManageUser(null)}
                className="rounded-lg p-1 text-muted-foreground hover:bg-muted hover:text-foreground"
              >
                <X className="h-5 w-5" />
              </button>
            </div>
            <form onSubmit={saveManage} className="space-y-5 p-5">
              <p className="text-sm text-muted-foreground">
                {manageUser.name || manageUser.cpf}
              </p>
              <div className="flex items-center justify-between rounded-xl border border-border bg-muted/40 p-4">
                <div>
                  <p className="text-sm font-bold text-foreground">Status da conta</p>
                  <p className="text-xs text-muted-foreground">
                    Ative ou desative o acesso deste cliente ao app.
                  </p>
                </div>
                <button
                  type="button"
                  role="switch"
                  aria-checked={manageForm.active}
                  onClick={() => setManageForm((f) => ({ ...f, active: !f.active }))}
                  className={`relative h-6 w-11 rounded-full transition-colors ${
                    manageForm.active ? 'bg-emerald-500' : 'bg-muted-foreground/40'
                  }`}
                >
                  <span
                    className={`absolute top-0.5 left-0.5 h-5 w-5 rounded-full bg-white transition-transform ${
                      manageForm.active ? 'translate-x-5' : ''
                    }`}
                  />
                </button>
              </div>
              <div className="space-y-2">
                <label className="text-xs font-bold uppercase text-muted-foreground">
                  Tags do cliente
                </label>
                <input
                  value={manageForm.tags}
                  onChange={(e) => setManageForm((f) => ({ ...f, tags: e.target.value }))}
                  placeholder="vip, suporte, atrasado"
                  className={PANEL_INPUT}
                />
                <p className="text-[10px] text-muted-foreground">Separe as tags por vírgula.</p>
              </div>
              <div className="flex flex-wrap items-center justify-between gap-3">
                <button
                  type="button"
                  onClick={() => {
                    if (window.confirm('Excluir este cliente do app?')) {
                      onDelete(manageUser.id, { skipConfirm: true })
                      setManageUser(null)
                    }
                  }}
                  className={`${BTN_DANGER} inline-flex items-center gap-2 px-3 py-2 text-sm`}
                >
                  <Trash2 className="h-4 w-4" /> Excluir
                </button>
                <div className="flex gap-2">
                  <button type="button" onClick={() => setManageUser(null)} className={BTN_GHOST}>
                    Cancelar
                  </button>
                  <button type="submit" disabled={saving} className={BTN_PRIMARY}>
                    {saving ? 'Salvando…' : 'Salvar'}
                  </button>
                </div>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  )
}

const SEGMENT_OPTIONS = [
  { id: 'all', title: 'Todos os usuários', desc: 'Envia para todos os tokens ativos' },
  { id: 'active', title: 'Somente ativos', desc: 'Usuários com status ativo' },
  { id: 'inactive', title: 'Somente inativos', desc: 'Reengaje usuários inativos' },
  { id: 'tags', title: 'Por tags', desc: 'Informe tags separadas por vírgula' },
  { id: 'search', title: 'Busca', desc: 'Filtra por nome, e-mail ou CPF' },
]

function NotificationsPanel({
  selectedRecipients = [],
  onClearRecipients,
  onSent,
  setError,
  setMessage,
}) {
  const [form, setForm] = useState({
    title: '',
    message: '',
    type: 'info',
    image_url: '',
    link: '',
    segment_type: selectedRecipients.length ? 'selected' : 'all',
    segment_tags: '',
    segment_search: '',
    scheduled_at: '',
    save_as_template: false,
    template_name: '',
    template_id: '',
  })
  const [templates, setTemplates] = useState([])
  const [scheduled, setScheduled] = useState([])
  const [previewMode, setPreviewMode] = useState('ios')
  const [sending, setSending] = useState(false)
  const [loadingMeta, setLoadingMeta] = useState(true)

  const loadMeta = useCallback(async () => {
    setLoadingMeta(true)
    try {
      const [tRes, sRes] = await Promise.all([
        axios.get('/api/mobile-app/notification-templates/', { headers: authHeaders() }),
        axios.get('/api/mobile-app/scheduled-notifications/', { headers: authHeaders() }),
      ])
      setTemplates(tRes.data.results || tRes.data || [])
      setScheduled(sRes.data.results || sRes.data || [])
    } catch {
      /* ignore */
    } finally {
      setLoadingMeta(false)
    }
  }, [])

  useEffect(() => {
    loadMeta()
  }, [loadMeta])

  useEffect(() => {
    if (selectedRecipients.length) {
      setForm((f) => ({ ...f, segment_type: 'selected' }))
    }
  }, [selectedRecipients])

  const applyTemplate = (id) => {
    const t = templates.find((x) => String(x.id) === String(id))
    setForm((f) => ({
      ...f,
      template_id: id,
      title: t?.title || f.title,
      message: t?.body || f.message,
      type: t?.type || f.type,
      image_url: t?.image_url || f.image_url,
    }))
  }

  const deleteTemplate = async (id) => {
    if (!id || !window.confirm('Excluir este template?')) return
    await axios.delete(`/api/mobile-app/notification-templates/${id}/`, { headers: authHeaders() })
    toast.deleted('Template excluído.')
    setForm((f) => ({ ...f, template_id: '' }))
    await loadMeta()
  }

  const cancelScheduled = async (id) => {
    if (!id) return
    if (!window.confirm('Excluir este agendamento? Ele não será enviado.')) return
    try {
      try {
        await axios.delete(`/api/mobile-app/scheduled-notifications/${id}/`, { headers: authHeaders() })
      } catch {
        await axios.post(`/api/mobile-app/scheduled-notifications/${id}/cancel/`, {}, { headers: authHeaders() })
      }
      setScheduled((list) => list.filter((s) => String(s.id) !== String(id)))
      toast.deleted('Agendamento excluído.')
      await loadMeta()
    } catch (err) {
      toast.apiError(err, 'Não foi possível excluir o agendamento.')
    }
  }

  const submit = async (e) => {
    e.preventDefault()
    setError('')
    setMessage('')
    setSending(true)
    try {
      const segmentType = form.segment_type === 'search' ? 'all' : form.segment_type
      const payload = {
        title: form.title,
        message: form.message,
        type: form.type,
        link: form.link || undefined,
        image_url: form.image_url || undefined,
        segment_type: segmentType,
        segment_tags: form.segment_type === 'tags' ? form.segment_tags : undefined,
        segment_search: form.segment_type === 'search' ? form.segment_search : undefined,
        scheduled_at: form.scheduled_at || undefined,
        save_as_template: form.save_as_template,
        template_name: form.save_as_template ? form.template_name : undefined,
      }
      if (form.segment_type === 'selected') {
        payload.segment_type = 'selected'
        payload.selected_cpfs = selectedRecipients.map((c) => c.cpf).filter(Boolean).join(',')
      }

      const res = await axios.post('/api/mobile-app/admin/push/send/', payload, { headers: authHeaders() })
      if (res.data.status === 'error') {
        setError(res.data.message || 'Falha no envio')
      } else if (res.data.status === 'scheduled') {
        setMessage(res.data.message || 'Notificação agendada.')
        setForm((f) => ({
          ...f,
          title: '',
          message: '',
          image_url: '',
          link: '',
          scheduled_at: '',
          save_as_template: false,
          template_name: '',
        }))
        await loadMeta()
        onSent?.()
      } else {
        setMessage(
          `Notificação enviada. Sucesso: ${res.data.sent ?? res.data.success_count ?? 0} · Falhas: ${res.data.failed ?? res.data.failure_count ?? 0}`,
        )
        setForm((f) => ({
          ...f,
          title: '',
          message: '',
          image_url: '',
          link: '',
          scheduled_at: '',
          save_as_template: false,
          template_name: '',
        }))
        onClearRecipients?.()
        await loadMeta()
        onSent?.()
      }
    } catch (err) {
      setError(err?.response?.data?.error || err?.response?.data?.message || 'Falha ao enviar notificação')
    } finally {
      setSending(false)
    }
  }

  const previewTitle = form.title || 'Título da notificação'
  const previewBody = form.message || 'O conteúdo da sua notificação aparecerá aqui.'
  const nowLabel = new Date().toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' })

  return (
    <div className="space-y-6 p-6">
      <div className="grid grid-cols-1 gap-6 xl:grid-cols-3">
        <div className="space-y-6 xl:col-span-2">
          <form onSubmit={submit} className={`${PANEL_CARD} space-y-6`}>
            <div>
              <h2 className="text-xl font-bold text-foreground">Enviar notificação push</h2>
              <p className="mt-1 text-sm text-muted-foreground">
                Defina conteúdo, segmentação e agendamento.
              </p>
            </div>

            {selectedRecipients.length > 0 && (
              <div className="rounded-xl border border-primary/30 bg-primary/10 p-4">
                <div className="mb-3 flex items-center justify-between gap-2">
                  <div>
                    <p className="text-[10px] font-bold uppercase tracking-widest text-primary">
                      Destinatários selecionados
                    </p>
                    <p className="text-xs text-foreground">
                      {selectedRecipients.length} cliente{selectedRecipients.length === 1 ? '' : 's'} aguardando mensagem
                    </p>
                  </div>
                  <button type="button" onClick={onClearRecipients} className={`${BTN_GHOST} text-xs`}>
                    Limpar lista
                  </button>
                </div>
                <div className="flex max-h-28 flex-wrap gap-2 overflow-y-auto">
                  {selectedRecipients.map((u) => (
                    <span
                      key={u.id || u.cpf}
                      className="inline-flex items-center gap-2 rounded-lg border border-border bg-background px-2.5 py-1.5 text-xs"
                    >
                      <span className="h-1.5 w-1.5 rounded-full bg-primary" />
                      <span className="font-medium text-foreground">{u.name || u.cpf}</span>
                      <span className="font-mono text-[10px] text-muted-foreground">({u.cpf})</span>
                    </span>
                  ))}
                </div>
              </div>
            )}

            <div>
              <label className="mb-2 block text-xs font-bold uppercase tracking-wide text-muted-foreground">
                Template
              </label>
              <div className="flex flex-col gap-2 sm:flex-row">
                <select
                  value={form.template_id}
                  onChange={(e) => applyTemplate(e.target.value)}
                  className={PANEL_INPUT}
                >
                  <option value="">Nenhum template selecionado</option>
                  {templates.map((t) => (
                    <option key={t.id} value={t.id}>{t.name}</option>
                  ))}
                </select>
                {form.template_id ? (
                  <button
                    type="button"
                    onClick={() => deleteTemplate(form.template_id)}
                    className="inline-flex shrink-0 items-center justify-center gap-2 rounded-lg border border-red-500 bg-red-500/10 px-3 py-2 text-sm font-medium text-red-500 transition-colors hover:bg-red-500 hover:text-white"
                  >
                    Excluir template
                  </button>
                ) : null}
              </div>
              {loadingMeta ? (
                <p className="mt-1 text-[10px] text-muted-foreground">Carregando templates…</p>
              ) : null}
            </div>

            <div>
              <label className="mb-2 block text-xs font-bold uppercase tracking-wide text-muted-foreground">
                Título
              </label>
              <input
                required
                value={form.title}
                onChange={(e) => setForm((f) => ({ ...f, title: e.target.value }))}
                placeholder="Ex: Promoção relâmpago"
                className={PANEL_INPUT}
              />
            </div>

            <div>
              <label className="mb-2 block text-xs font-bold uppercase tracking-wide text-muted-foreground">
                Mensagem
              </label>
              <textarea
                required
                rows={4}
                value={form.message}
                onChange={(e) => setForm((f) => ({ ...f, message: e.target.value }))}
                placeholder="Conteúdo da sua notificação"
                className={`${PANEL_INPUT} resize-none`}
              />
            </div>

            <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
              <div>
                <label className="mb-2 block text-xs font-bold uppercase tracking-wide text-muted-foreground">
                  Tipo
                </label>
                <select
                  value={form.type}
                  onChange={(e) => setForm((f) => ({ ...f, type: e.target.value }))}
                  className={PANEL_INPUT}
                >
                  <option value="info">Informativo</option>
                  <option value="promo">Promocional</option>
                  <option value="warning">Aviso</option>
                </select>
              </div>
              <div>
                <label className="mb-2 block text-xs font-bold uppercase tracking-wide text-muted-foreground">
                  Imagem (opcional)
                </label>
                <input
                  type="url"
                  value={form.image_url}
                  onChange={(e) => setForm((f) => ({ ...f, image_url: e.target.value }))}
                  placeholder="https://..."
                  className={PANEL_INPUT}
                />
              </div>
            </div>

            <div>
              <label className="mb-2 block text-xs font-bold uppercase tracking-wide text-muted-foreground">
                Link (opcional)
              </label>
              <input
                value={form.link}
                onChange={(e) => setForm((f) => ({ ...f, link: e.target.value }))}
                placeholder="https://... ou deep link do app"
                className={PANEL_INPUT}
              />
            </div>

            <div>
              <label className="mb-2 block text-xs font-bold uppercase tracking-wide text-muted-foreground">
                Agendar envio
              </label>
              <div className="relative">
                <Calendar className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
                <input
                  type="datetime-local"
                  value={form.scheduled_at || ''}
                  min={(() => {
                    const d = new Date()
                    const pad = (n) => String(n).padStart(2, '0')
                    return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`
                  })()}
                  onChange={(e) => setForm((f) => ({ ...f, scheduled_at: e.target.value }))}
                  className={`${PANEL_INPUT} pl-10 [color-scheme:dark]`}
                />
              </div>
              <div className="mt-2 flex flex-wrap items-center gap-3">
                <p className="text-[10px] text-primary">
                  Deixe vazio para enviar agora. O horário segue o fuso do servidor (Brasília).
                </p>
                {form.scheduled_at ? (
                  <button
                    type="button"
                    onClick={() => setForm((f) => ({ ...f, scheduled_at: '' }))}
                    className="text-[10px] font-semibold text-muted-foreground underline hover:text-foreground"
                  >
                    Limpar agendamento
                  </button>
                ) : null}
              </div>
            </div>

            <div>
              <label className="mb-3 block text-xs font-bold uppercase tracking-wide text-muted-foreground">
                Segmentação
              </label>
              <div className="mb-3 grid grid-cols-1 gap-3 sm:grid-cols-2">
                {SEGMENT_OPTIONS.map((opt) => {
                  const active = form.segment_type === opt.id
                  return (
                    <button
                      key={opt.id}
                      type="button"
                      onClick={() => setForm((f) => ({ ...f, segment_type: opt.id }))}
                      className={`rounded-xl border p-4 text-left transition-all ${
                        active
                          ? 'border-primary bg-primary/10 text-foreground'
                          : 'border-border bg-muted/30 text-muted-foreground hover:border-primary/40'
                      }`}
                    >
                      <span className="block text-sm font-bold">{opt.title}</span>
                      <span className="mt-1 block text-xs opacity-80">{opt.desc}</span>
                    </button>
                  )
                })}
                {selectedRecipients.length > 0 && (
                  <button
                    type="button"
                    onClick={() => setForm((f) => ({ ...f, segment_type: 'selected' }))}
                    className={`rounded-xl border p-4 text-left transition-all sm:col-span-2 ${
                      form.segment_type === 'selected'
                        ? 'border-primary bg-primary/10 text-foreground'
                        : 'border-border bg-muted/30 text-muted-foreground hover:border-primary/40'
                    }`}
                  >
                    <span className="block text-sm font-bold">Clientes selecionados</span>
                    <span className="mt-1 block text-xs text-primary">
                      {selectedRecipients.length} clientes selecionados
                    </span>
                  </button>
                )}
              </div>
              {form.segment_type === 'tags' && (
                <input
                  value={form.segment_tags}
                  onChange={(e) => setForm((f) => ({ ...f, segment_tags: e.target.value }))}
                  placeholder="vip, suporte, atrasado"
                  className={PANEL_INPUT}
                />
              )}
              {form.segment_type === 'search' && (
                <input
                  value={form.segment_search}
                  onChange={(e) => setForm((f) => ({ ...f, segment_search: e.target.value }))}
                  placeholder="Nome, e-mail ou CPF"
                  className={PANEL_INPUT}
                />
              )}
            </div>

            <div className="flex flex-wrap items-center gap-3">
              <label className="flex items-center gap-2 text-sm text-foreground">
                <input
                  type="checkbox"
                  checked={form.save_as_template}
                  onChange={(e) => setForm((f) => ({ ...f, save_as_template: e.target.checked }))}
                  className="h-4 w-4 rounded border-border"
                />
                Salvar como template
              </label>
              {form.save_as_template && (
                <input
                  required
                  value={form.template_name}
                  onChange={(e) => setForm((f) => ({ ...f, template_name: e.target.value }))}
                  placeholder="Nome do template"
                  className={`${PANEL_INPUT} max-w-xs`}
                />
              )}
            </div>

            <button type="submit" disabled={sending} className={`${BTN_PRIMARY} w-full py-3`}>
              <Send className="h-4 w-4" />
              {sending ? 'Enviando…' : form.scheduled_at ? 'Agendar notificação' : 'Enviar notificação'}
            </button>
          </form>
        </div>

        <div className="space-y-6">
          {scheduled.filter((s) => s.status === 'pending').length > 0 && (
            <div className={PANEL_CARD}>
              <h3 className="mb-4 text-xs font-bold uppercase tracking-wide text-muted-foreground">
                Notificações agendadas
              </h3>
              <div className="max-h-64 space-y-3 overflow-y-auto">
                {scheduled
                  .filter((s) => s.status === 'pending')
                  .map((s) => (
                    <div key={s.id} className="rounded-lg border border-border bg-muted/40 p-3">
                      <div className="mb-2 flex items-start justify-between gap-2">
                        <h4 className="text-sm font-semibold text-foreground">{s.title}</h4>
                        <span className="rounded bg-orange-500/20 px-2 py-0.5 text-[10px] font-bold text-orange-400">
                          {s.status_display || 'Pendente'}
                        </span>
                      </div>
                      <p className="mb-2 line-clamp-2 text-xs text-muted-foreground">{s.body}</p>
                      <div className="flex items-center justify-between text-xs text-muted-foreground">
                        <span>{formatDateTime(s.scheduled_at)}</span>
                        <button
                          type="button"
                          onClick={() => cancelScheduled(s.id)}
                          className="font-semibold text-destructive hover:underline"
                        >
                          Excluir
                        </button>
                      </div>
                    </div>
                  ))}
              </div>
            </div>
          )}

          <div className={`${PANEL_CARD} flex flex-col items-center`}>
            <h3 className="mb-6 w-full text-xs font-bold uppercase tracking-widest text-muted-foreground">
              Simulador de notificação
            </h3>

            <div
              className={`relative h-[520px] w-[260px] origin-top transition-all ${
                previewMode === 'android' ? 'scale-[0.98]' : ''
              }`}
            >
              <div
                className={`absolute inset-0 border shadow-2xl ${
                  previewMode === 'ios'
                    ? 'rounded-[2.8rem] border-[#222] bg-[#0c0c0d]'
                    : 'rounded-[1.6rem] border-[#333] bg-[#111]'
                }`}
              >
                <div
                  className={`absolute overflow-hidden ${
                    previewMode === 'ios'
                      ? 'inset-[8px] rounded-[2.3rem] bg-black'
                      : 'inset-[6px] rounded-[1.2rem] bg-black'
                  }`}
                >
                  <div className="absolute inset-0 bg-gradient-to-tr from-[#050505] via-[#121820] to-[#212121]" />
                  <div className="relative z-20 flex h-10 items-center justify-between px-5 text-[10px] font-medium text-white/90">
                    <span className="font-bold">{nowLabel}</span>
                    {previewMode === 'ios' && (
                      <div className="absolute left-1/2 top-2 h-5 w-[72px] -translate-x-1/2 rounded-full bg-black" />
                    )}
                    <span className="text-[9px] opacity-70">NIOHUB</span>
                  </div>
                  <div className="relative z-10 px-3 pt-4">
                    <div
                      className={`border p-3.5 shadow-xl backdrop-blur-xl transition-all ${
                        previewMode === 'ios'
                          ? 'rounded-[1.4rem] border-white/30 bg-white/95'
                          : 'rounded-2xl border-white/10 bg-[#2a2a2e]/95'
                      }`}
                    >
                      <div className="mb-2 flex items-center justify-between">
                        <div className="flex items-center gap-2">
                          <div className="flex h-5 w-5 items-center justify-center rounded-md bg-primary text-[8px] font-bold text-primary-foreground">
                            N
                          </div>
                          <span
                            className={`text-[10px] font-semibold uppercase tracking-wide ${
                              previewMode === 'ios' ? 'text-gray-500' : 'text-white/50'
                            }`}
                          >
                            Niohub
                          </span>
                        </div>
                        <span
                          className={`text-[9px] font-bold ${
                            previewMode === 'ios' ? 'text-gray-500' : 'text-white/40'
                          }`}
                        >
                          AGORA
                        </span>
                      </div>
                      <h4
                        className={`text-[13px] font-extrabold leading-tight ${
                          previewMode === 'ios' ? 'text-gray-900' : 'text-white'
                        }`}
                      >
                        {previewTitle}
                      </h4>
                      <p
                        className={`mt-0.5 text-[12px] leading-snug ${
                          previewMode === 'ios' ? 'text-gray-700' : 'text-white/80'
                        }`}
                      >
                        {previewBody}
                      </p>
                      {form.image_url ? (
                        <div className="mt-2 overflow-hidden rounded-lg border border-black/10">
                          <img
                            src={form.image_url}
                            alt=""
                            className="h-20 w-full object-cover"
                            onError={(e) => {
                              e.currentTarget.style.display = 'none'
                            }}
                          />
                        </div>
                      ) : null}
                    </div>
                  </div>
                  {previewMode === 'ios' && (
                    <div className="absolute bottom-2 left-1/2 h-1 w-20 -translate-x-1/2 rounded-full bg-white/30" />
                  )}
                </div>
              </div>
            </div>

            <div className="mt-6 flex w-full gap-1.5 rounded-xl border border-border bg-muted/40 p-1.5">
              <button
                type="button"
                onClick={() => setPreviewMode('ios')}
                className={`flex flex-1 items-center justify-center gap-2 rounded-lg px-3 py-2 text-xs font-bold transition-all ${
                  previewMode === 'ios'
                    ? 'bg-primary text-primary-foreground shadow'
                    : 'text-muted-foreground hover:bg-muted'
                }`}
              >
                iPhone
              </button>
              <button
                type="button"
                onClick={() => setPreviewMode('android')}
                className={`flex flex-1 items-center justify-center gap-2 rounded-lg px-3 py-2 text-xs font-bold transition-all ${
                  previewMode === 'android'
                    ? 'bg-primary text-primary-foreground shadow'
                    : 'text-muted-foreground hover:bg-muted'
                }`}
              >
                Android
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}

const WARNING_TYPES = [
  {
    id: 'info',
    title: 'Informativo',
    desc: 'Use para comunicados gerais e lembretes simples.',
    icon: Info,
    color: 'bg-primary text-primary-foreground',
    active: 'border-primary bg-primary/10',
    badge: 'bg-primary/20 text-primary',
  },
  {
    id: 'success',
    title: 'Sucesso',
    desc: 'Ideal para confirmações, boas notícias e novidades.',
    icon: CheckCircle2,
    color: 'bg-emerald-500 text-white',
    active: 'border-emerald-500 bg-emerald-500/10',
    badge: 'bg-emerald-500/20 text-emerald-500',
  },
  {
    id: 'warning',
    title: 'Atenção',
    desc: 'Destaque prazos, manutenções e situações de atenção.',
    icon: AlertTriangle,
    color: 'bg-orange-500 text-white',
    active: 'border-orange-500 bg-orange-500/10',
    badge: 'bg-orange-500/20 text-orange-400',
  },
  {
    id: 'critical',
    title: 'Crítico',
    desc: 'Para alertas importantes que exigem ação imediata.',
    icon: AlertTriangle,
    color: 'bg-destructive text-destructive-foreground',
    active: 'border-destructive bg-destructive/10',
    badge: 'bg-destructive/20 text-destructive',
  },
]

function WarningsPanel({ warnings, onCreate, onDelete }) {
  const [form, setForm] = useState({
    title: '',
    message: '',
    type: 'info',
    sticky: false,
    show_home: true,
    whatsapp_enabled: false,
    whatsapp_btn: '',
  })
  const [saving, setSaving] = useState(false)

  const submit = async (e) => {
    e.preventDefault()
    setSaving(true)
    try {
      await onCreate({
        title: form.title,
        message: form.message,
        type: form.type,
        sticky: form.sticky,
        show_home: form.show_home,
        whatsapp_btn: form.whatsapp_enabled ? form.whatsapp_btn : '',
      })
      setForm({
        title: '',
        message: '',
        type: 'info',
        sticky: false,
        show_home: true,
        whatsapp_enabled: false,
        whatsapp_btn: '',
      })
    } finally {
      setSaving(false)
    }
  }

  const typeMeta = (type) => WARNING_TYPES.find((t) => t.id === type) || WARNING_TYPES[0]

  return (
    <div className="space-y-6 p-6">
      <form onSubmit={submit} className={`${PANEL_CARD} space-y-6`}>
        <div>
          <h2 className="text-xl font-bold text-foreground">Avisos In-App</h2>
          <p className="mt-1 text-sm leading-relaxed text-muted-foreground">
            Crie comunicados para aparecer diretamente no aplicativo do cliente. Você pode destacar
            avisos importantes e oferecer contato rápido pelo WhatsApp.
          </p>
        </div>

        <div className="space-y-4">
          <div>
            <label className="mb-2 block text-xs font-bold uppercase tracking-wide text-muted-foreground">
              Título
            </label>
            <input
              required
              value={form.title}
              onChange={(e) => setForm((f) => ({ ...f, title: e.target.value }))}
              placeholder="Ex: Instabilidade programada"
              className={PANEL_INPUT}
            />
          </div>
          <div>
            <label className="mb-2 block text-xs font-bold uppercase tracking-wide text-muted-foreground">
              Mensagem
            </label>
            <textarea
              required
              rows={4}
              value={form.message}
              onChange={(e) => setForm((f) => ({ ...f, message: e.target.value }))}
              placeholder="Explique o que está acontecendo e como o cliente pode proceder."
              className={`${PANEL_INPUT} resize-none`}
            />
            <p className="mt-2 text-xs text-muted-foreground">
              Recomendamos mensagens curtas, com foco na ação que o cliente precisa tomar.
            </p>
          </div>
        </div>

        <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
          <div>
            <label className="mb-4 block text-xs font-bold uppercase tracking-wide text-muted-foreground">
              Cor de destaque
            </label>
            <div className="space-y-3">
              {WARNING_TYPES.map((t) => {
                const Icon = t.icon
                const active = form.type === t.id
                return (
                  <button
                    key={t.id}
                    type="button"
                    onClick={() => setForm((f) => ({ ...f, type: t.id }))}
                    className={`flex w-full items-center rounded-xl border p-4 text-left transition-all ${
                      active ? `border-2 ${t.active}` : 'border-border bg-muted/30 hover:border-muted-foreground/40'
                    }`}
                  >
                    <div
                      className={`mr-4 flex h-8 w-8 shrink-0 items-center justify-center rounded-lg ${t.color}`}
                    >
                      <Icon className="h-5 w-5" />
                    </div>
                    <div className="min-w-0 flex-1">
                      <span className="block text-sm font-bold text-foreground">{t.title}</span>
                      <span className="mt-0.5 block text-xs text-muted-foreground">{t.desc}</span>
                    </div>
                    <span
                      className={`ml-3 h-4 w-4 shrink-0 rounded-full border-2 ${
                        active ? 'border-transparent' : 'border-border'
                      }`}
                    >
                      {active ? (
                        <span className={`block h-full w-full rounded-full ${t.color.split(' ')[0]}`} />
                      ) : null}
                    </span>
                  </button>
                )
              })}
            </div>
          </div>

          <div className="rounded-xl border border-border bg-muted/30 p-5">
            <div className="mb-5 flex items-center justify-between gap-3">
              <div className="flex min-w-0 items-center gap-3">
                <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-emerald-500 text-white">
                  <span className="text-xs font-bold">WA</span>
                </div>
                <span className="text-sm font-bold text-foreground">Botão do WhatsApp</span>
              </div>
              <button
                type="button"
                role="switch"
                aria-checked={form.whatsapp_enabled}
                onClick={() => setForm((f) => ({ ...f, whatsapp_enabled: !f.whatsapp_enabled }))}
                className={`relative h-6 w-11 shrink-0 rounded-full transition-colors ${
                  form.whatsapp_enabled ? 'bg-emerald-500' : 'bg-muted-foreground/40'
                }`}
              >
                <span
                  className={`absolute top-0.5 left-0.5 h-5 w-5 rounded-full bg-white transition-transform ${
                    form.whatsapp_enabled ? 'translate-x-5' : ''
                  }`}
                />
              </button>
            </div>

            <p className="mb-2 text-xs text-muted-foreground">
              Acrescenta um atalho direto para o suporte dentro do aviso. O cliente toca e já abre o
              chat.
            </p>
            <input
              disabled={!form.whatsapp_enabled}
              value={form.whatsapp_btn}
              onChange={(e) => setForm((f) => ({ ...f, whatsapp_btn: e.target.value }))}
              placeholder="Ex.: 5567999999999"
              className={`${PANEL_INPUT} disabled:opacity-50`}
            />

            <div className="mt-5 space-y-3 border-t border-border pt-4">
              <label className="flex cursor-pointer items-center gap-3 text-sm text-muted-foreground hover:text-foreground">
                <input
                  type="checkbox"
                  checked={form.sticky}
                  onChange={(e) => setForm((f) => ({ ...f, sticky: e.target.checked }))}
                  className="h-4 w-4 rounded border-border"
                />
                <Pin className="h-4 w-4 shrink-0 text-destructive" />
                Fixar este aviso no topo do aplicativo
              </label>
              <label className="flex cursor-pointer items-center gap-3 text-sm text-muted-foreground hover:text-foreground">
                <input
                  type="checkbox"
                  checked={form.show_home}
                  onChange={(e) => setForm((f) => ({ ...f, show_home: e.target.checked }))}
                  className="h-4 w-4 rounded border-border"
                />
                <Home className="h-4 w-4 shrink-0 text-orange-400" />
                Mostrar também na tela inicial do app
              </label>
            </div>
          </div>
        </div>

        <div className="flex justify-end border-t border-border pt-4">
          <button type="submit" disabled={saving} className={`${BTN_PRIMARY} px-8 py-3`}>
            <Megaphone className="h-4 w-4" />
            {saving ? 'Publicando…' : 'Publicar aviso'}
          </button>
        </div>
      </form>

      <div>
        <h3 className="mb-4 text-lg font-bold text-foreground">Avisos ativos</h3>
        <div className="grid gap-4">
          {warnings.map((w) => {
            const meta = typeMeta(w.type)
            return (
              <div
                key={w.id}
                className="flex flex-col gap-3 rounded-xl border border-border bg-card p-4 sm:flex-row sm:items-start sm:justify-between"
              >
                <div className="min-w-0">
                  <div className="mb-1 flex flex-wrap items-center gap-2">
                    <span className={`rounded px-2 py-0.5 text-xs font-bold uppercase ${meta.badge}`}>
                      {meta.title}
                    </span>
                    <h4 className="font-bold text-foreground">{w.title}</h4>
                  </div>
                  <p className="mb-2 text-sm text-muted-foreground">{w.message}</p>
                  <div className="flex flex-wrap gap-3 text-xs text-muted-foreground">
                    {w.sticky ? <span>Fixado</span> : null}
                    {w.show_home ? <span>Tela inicial</span> : null}
                    {w.whatsapp_btn ? <span>WhatsApp</span> : null}
                    <span>{formatDateTime(w.created_at)}</span>
                  </div>
                </div>
                <button
                  type="button"
                  onClick={() => onDelete(w.id)}
                  className={`${BTN_DANGER} shrink-0 self-start sm:self-center`}
                  title="Excluir"
                >
                  <Trash2 className="h-5 w-5" />
                </button>
              </div>
            )
          })}
          {warnings.length === 0 && (
            <p className="rounded-xl border border-dashed border-border py-8 text-center text-sm text-muted-foreground">
              Nenhum aviso ativo.
            </p>
          )}
        </div>
      </div>
    </div>
  )
}

function ToggleSwitch({ checked, onChange, activeClass = 'bg-emerald-500' }) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={!!checked}
      onClick={() => onChange(!checked)}
      className={`relative inline-flex h-6 w-11 shrink-0 items-center rounded-full transition-colors ${
        checked ? activeClass : 'bg-muted'
      }`}
    >
      <span
        className={`absolute top-0.5 left-0.5 h-5 w-5 rounded-full bg-white shadow transition-transform ${
          checked ? 'translate-x-5' : ''
        }`}
      />
    </button>
  )
}

function configPayload(form) {
  return {
    active_shortcuts: Array.isArray(form?.active_shortcuts) ? form.active_shortcuts : [],
    tool_speed_test: !!form?.tool_speed_test,
    tool_wifi: !!form?.tool_wifi,
    tool_cameras: !!form?.tool_cameras,
    tool_connected_devices: !!form?.tool_connected_devices,
    tool_auto_unlock: form?.tool_auto_unlock !== false,
    tool_faturas: form?.tool_faturas !== false,
    shortcut_wifi: !!form?.shortcut_wifi,
    speed_test_provider: form?.speed_test_provider || 'fast',
    update_warning_active: !!form?.update_warning_active,
    social_links: Array.isArray(form?.social_links) ? form.social_links : [],
  }
}

function AppConfigPanel({ configForm, setConfigForm, onSave, saving }) {
  if (!configForm) {
    return (
      <div className="p-6 text-sm text-muted-foreground">Carregando configurações…</div>
    )
  }

  const shortcuts = Array.isArray(configForm.active_shortcuts) ? configForm.active_shortcuts : []
  const activeToolsCount = APP_TOOLS.filter((t) => !!configForm[t.key]).length
  const socialCount = Array.isArray(configForm.social_links) ? configForm.social_links.length : 0

  const updateForm = (updater) => {
    setConfigForm((f) => (typeof updater === 'function' ? updater(f) : { ...f, ...updater }))
  }

  const toggleShortcut = (name) => {
    updateForm((f) => {
      const list = Array.isArray(f.active_shortcuts) ? [...f.active_shortcuts] : []
      const idx = list.indexOf(name)
      if (idx >= 0) list.splice(idx, 1)
      else list.push(name)
      return { ...f, active_shortcuts: list }
    })
  }

  const setTool = (key, value) => {
    updateForm((f) => ({ ...f, [key]: value }))
  }

  return (
    <form onSubmit={onSave} className="space-y-6 p-6">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <h2 className="text-xl font-bold text-foreground">Editar aplicativo</h2>
        <button type="submit" disabled={saving} className={`${BTN_PRIMARY} shrink-0 px-4 py-2`}>
          {saving ? 'Salvando…' : 'Salvar Alterações'}
        </button>
      </div>

      <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
        <div className={`${PANEL_CARD} relative overflow-hidden p-4`}>
          <div className="absolute top-0 right-0 h-full w-1 bg-gradient-to-b from-primary to-transparent opacity-50" />
          <h3 className="mb-1 text-[10px] font-bold tracking-wider text-muted-foreground uppercase">
            Atalhos Ativos
          </h3>
          <div className="mb-1 text-2xl font-bold text-foreground">{shortcuts.length}</div>
          <p className="text-[10px] text-muted-foreground">de {APP_SHORTCUTS.length} opções</p>
        </div>
        <div className={`${PANEL_CARD} relative overflow-hidden p-4`}>
          <div className="absolute top-0 right-0 h-full w-1 bg-gradient-to-b from-emerald-500 to-transparent opacity-50" />
          <h3 className="mb-1 text-[10px] font-bold tracking-wider text-muted-foreground uppercase">
            Ferramentas Ativas
          </h3>
          <div className="mb-1 text-2xl font-bold text-foreground">{activeToolsCount}</div>
          <p className="text-[10px] text-muted-foreground">de {APP_TOOLS.length} atalhos</p>
        </div>
        <div className={`${PANEL_CARD} relative overflow-hidden p-4`}>
          <div className="absolute top-0 right-0 h-full w-1 bg-gradient-to-b from-violet-500 to-transparent opacity-50" />
          <h3 className="mb-1 text-[10px] font-bold tracking-wider text-muted-foreground uppercase">
            Canais Sociais
          </h3>
          <div className="mb-1 text-2xl font-bold text-foreground">{socialCount}</div>
          <p className="text-[10px] text-muted-foreground">links habilitados</p>
        </div>
      </div>

      <div className={`${PANEL_CARD} rounded-2xl`}>
        <div className="mb-6 flex items-center">
          <div className="mr-4 flex h-10 w-10 items-center justify-center rounded-lg bg-muted text-yellow-500">
            <Zap className="h-6 w-6" />
          </div>
          <div>
            <h3 className="text-base font-bold text-foreground">Atalhos e ferramentas</h3>
            <p className="text-xs text-muted-foreground">
              Escolha o que os clientes veem na home e no hub de ferramentas do app.
            </p>
          </div>
        </div>

        <div className="grid grid-cols-1 gap-8 lg:grid-cols-2">
          <div>
            <h4 className="mb-4 text-[10px] font-bold text-muted-foreground uppercase">
              Atalhos rápidos{' '}
              <span className="ml-2 text-[9px] font-normal normal-case">
                Itens destacados logo ao abrir o aplicativo.
              </span>
            </h4>
            <div className="space-y-3">
              {APP_SHORTCUTS.map((name) => {
                const on = shortcuts.includes(name)
                return (
                  <div
                    key={name}
                    className="flex items-center justify-between rounded-lg border border-border bg-background/50 p-3"
                  >
                    <span className="text-xs font-bold text-foreground uppercase">
                      {name}{' '}
                      <span className="ml-1 text-[9px] font-normal text-muted-foreground">
                        VISÍVEL PARA O CLIENTE
                      </span>
                    </span>
                    <ToggleSwitch checked={on} onChange={() => toggleShortcut(name)} />
                  </div>
                )
              })}
            </div>
          </div>

          <div>
            <h4 className="mb-4 text-[10px] font-bold text-muted-foreground uppercase">
              Ferramentas{' '}
              <span className="ml-2 text-[9px] font-normal normal-case">
                Acesso rápido a recursos de suporte e diagnóstico.
              </span>
            </h4>
            <div className="space-y-3">
              <div
                className={`relative overflow-hidden rounded-2xl border p-5 transition-colors ${
                  configForm.tool_speed_test
                    ? 'border-emerald-500/40 bg-gradient-to-br from-emerald-500/15 via-card to-card shadow-[inset_0_1px_0_0_rgba(52,211,153,0.12)]'
                    : 'border-border bg-muted/20 opacity-80'
                }`}
              >
                <div className="pointer-events-none absolute -top-10 -right-8 h-28 w-28 rounded-full bg-emerald-400/10 blur-2xl" />
                <div className="relative flex items-start justify-between gap-3">
                  <div className="flex min-w-0 items-start gap-3">
                    <div
                      className={`flex h-10 w-10 shrink-0 items-center justify-center rounded-xl ${
                        configForm.tool_speed_test
                          ? 'bg-emerald-500 text-white shadow-lg shadow-emerald-500/25'
                          : 'bg-muted text-muted-foreground'
                      }`}
                    >
                      <Gauge className="h-5 w-5" />
                    </div>
                    <div className="min-w-0">
                      <p className="text-sm font-bold tracking-wide text-foreground uppercase">
                        Teste de Velocidade
                      </p>
                      <p className="mt-0.5 text-[11px] text-muted-foreground">
                        Disponível no hub de ferramentas
                      </p>
                    </div>
                  </div>
                  <ToggleSwitch
                    checked={!!configForm.tool_speed_test}
                    onChange={(v) => setTool('tool_speed_test', v)}
                  />
                </div>

                <div
                  className={`relative mt-5 border-t pt-4 transition-opacity ${
                    configForm.tool_speed_test
                      ? 'border-emerald-500/20 opacity-100'
                      : 'border-border opacity-50'
                  }`}
                >
                  <label className="mb-3 block text-[10px] font-bold tracking-wider text-muted-foreground uppercase">
                    Provedor de teste
                  </label>
                  <div className="grid grid-cols-2 gap-1.5 rounded-xl bg-background/70 p-1.5 ring-1 ring-border/80">
                    {[
                      ['fast', 'Fast.com', 'Medição leve'],
                      ['speedtest', 'Speedtest.net', 'Ookla'],
                    ].map(([value, label, hint]) => {
                      const selected = (configForm.speed_test_provider || 'fast') === value
                      return (
                        <button
                          key={value}
                          type="button"
                          disabled={!configForm.tool_speed_test}
                          onClick={() => updateForm((f) => ({ ...f, speed_test_provider: value }))}
                          className={`rounded-lg px-3 py-3 text-left transition-all disabled:cursor-not-allowed disabled:opacity-40 ${
                            selected
                              ? 'bg-primary text-primary-foreground shadow-md shadow-primary/30 ring-1 ring-primary'
                              : 'bg-transparent text-muted-foreground hover:bg-muted/60 hover:text-foreground'
                          }`}
                        >
                          <span className="block text-xs font-bold tracking-wide uppercase">{label}</span>
                          <span
                            className={`mt-0.5 block text-[10px] ${
                              selected ? 'text-primary-foreground/80' : 'text-muted-foreground'
                            }`}
                          >
                            {hint}
                          </span>
                        </button>
                      )
                    })}
                  </div>
                </div>
              </div>

              {APP_TOOLS.filter((t) => t.key !== 'tool_speed_test').map((t) => (
                <div
                  key={t.key}
                  className={`flex items-center justify-between rounded-xl border p-3.5 transition-colors ${
                    configForm[t.key]
                      ? 'border-emerald-500/35 bg-emerald-500/8'
                      : 'border-border bg-muted/20'
                  }`}
                >
                  <div>
                    <p className="text-xs font-bold tracking-wide text-foreground uppercase">{t.label}</p>
                    <p className="mt-0.5 text-[10px] text-muted-foreground">
                      Disponível no hub de ferramentas
                    </p>
                  </div>
                  <ToggleSwitch checked={!!configForm[t.key]} onChange={(v) => setTool(t.key, v)} />
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>
    </form>
  )
}


const PLAN_TYPE_LABEL = {
  FIBRA: 'Fibra Óptica',
  RADIO: 'Rádio',
  CABO: 'Cabo',
}

const EMPTY_PLAN_FORM = {
  id: null,
  name: '',
  type: 'FIBRA',
  download_speed: '100',
  upload_speed: '50',
  price: '',
  description: '',
  is_active: true,
}

function PlansPanel({ plans, onSave, onDelete }) {
  const [modalOpen, setModalOpen] = useState(false)
  const [saving, setSaving] = useState(false)
  const [form, setForm] = useState(EMPTY_PLAN_FORM)

  const openNew = () => {
    setForm({ ...EMPTY_PLAN_FORM })
    setModalOpen(true)
  }

  const openEdit = (p) => {
    setForm({
      id: p.id,
      name: p.name || '',
      type: p.type || 'FIBRA',
      download_speed: String(p.download_speed ?? ''),
      upload_speed: String(p.upload_speed ?? ''),
      price: String(p.price ?? ''),
      description: p.description || '',
      is_active: p.is_active !== false,
    })
    setModalOpen(true)
  }

  const submit = async (e) => {
    e.preventDefault()
    setSaving(true)
    try {
      await onSave({
        id: form.id,
        name: form.name,
        type: form.type,
        download_speed: Number(form.download_speed) || 0,
        upload_speed: Number(form.upload_speed) || 0,
        price: form.price || 0,
        description: form.description,
        is_active: form.is_active,
      })
      setModalOpen(false)
      setForm({ ...EMPTY_PLAN_FORM })
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="space-y-6 p-6">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h2 className="mb-1 text-xl font-bold text-foreground">Configurar Planos</h2>
          <p className="text-sm text-muted-foreground">
            Cadastre e gerencie os planos que aparecem para seus clientes no app.
          </p>
        </div>
        <button type="button" onClick={openNew} className={`${BTN_PRIMARY} shrink-0`}>
          <Plus className="h-4 w-4" />
          Novo Plano
        </button>
      </div>

      <div className="grid grid-cols-1 gap-6 md:grid-cols-2 lg:grid-cols-3">
        {plans.map((p) => (
          <div
            key={p.id}
            className="group overflow-hidden rounded-2xl border border-border bg-card shadow-sm transition-shadow hover:shadow-md"
          >
            <div className="p-6">
              <div className="mb-4 flex items-start justify-between">
                <div className="relative flex h-12 w-12 items-center justify-center rounded-xl bg-gradient-to-br from-primary/25 to-cyan-400/25 text-cyan-300 ring-1 ring-white/10">
                  <Wifi className="h-7 w-7" />
                </div>
                <div className="flex gap-2">
                  <button
                    type="button"
                    onClick={() => openEdit(p)}
                    className={BTN_EDIT}
                    title="Editar"
                  >
                    <Pencil className="h-4 w-4" />
                  </button>
                  <button
                    type="button"
                    onClick={() => onDelete(p.id)}
                    className={BTN_DANGER}
                    title="Excluir"
                  >
                    <Trash2 className="h-4 w-4" />
                  </button>
                </div>
              </div>

              <h3 className="mb-1 text-xl font-bold text-foreground">{p.name}</h3>
              <span className="mb-4 inline-block rounded bg-primary px-2 py-1 text-[10px] font-bold text-primary-foreground uppercase">
                {PLAN_TYPE_LABEL[p.type] || p.type}
              </span>

              <div className="mb-6 grid grid-cols-2 gap-4 border-y border-border py-4">
                <div>
                  <p className="text-[10px] font-bold text-muted-foreground uppercase">Download</p>
                  <p className="text-lg font-bold text-foreground">{p.download_speed} Mbps</p>
                </div>
                <div>
                  <p className="text-[10px] font-bold text-muted-foreground uppercase">Upload</p>
                  <p className="text-lg font-bold text-foreground">{p.upload_speed} Mbps</p>
                </div>
              </div>

              <div className="mb-6 text-center">
                <p className="mb-1 text-xs text-muted-foreground">Por apenas</p>
                <p className="text-3xl font-black text-foreground">
                  R$ {Number(p.price).toLocaleString('pt-BR', { minimumFractionDigits: 2 })}
                </p>
              </div>

              {p.description ? (
                <div className="rounded-lg bg-muted/40 p-3">
                  <p className="mb-1 text-[10px] font-bold text-muted-foreground uppercase">
                    Descrição (Botão Detalhes)
                  </p>
                  <p className="text-xs text-muted-foreground italic">
                    &ldquo;{String(p.description).slice(0, 100)}
                    {String(p.description).length > 100 ? '…' : ''}&rdquo;
                  </p>
                </div>
              ) : null}
            </div>
            <div className="flex items-center justify-between bg-muted/40 px-6 py-3">
              <span
                className={`text-[10px] font-bold uppercase ${
                  p.is_active !== false ? 'text-emerald-400' : 'text-red-500'
                }`}
              >
                ● {p.is_active !== false ? 'Ativo no App' : 'Inativo'}
              </span>
            </div>
          </div>
        ))}

        {plans.length === 0 && (
          <div className="col-span-full rounded-2xl border border-dashed border-border py-20 text-center">
            <Package className="mx-auto mb-4 h-16 w-16 text-muted-foreground/40" />
            <h3 className="text-lg font-bold text-foreground">Nenhum plano cadastrado</h3>
            <p className="text-muted-foreground">Comece cadastrando seu primeiro plano de internet.</p>
          </div>
        )}
      </div>

      {modalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center overflow-y-auto bg-black/70 p-4">
          <div className="w-full max-w-lg overflow-hidden rounded-2xl border border-border bg-card shadow-xl">
            <form onSubmit={submit}>
              <div className="space-y-4 p-6">
                <h3 className="text-lg font-bold text-foreground">
                  {form.id ? 'Editar Plano' : 'Novo Plano'}
                </h3>
                <div>
                  <label className="mb-1 block text-xs font-bold text-muted-foreground uppercase">
                    Nome do Plano
                  </label>
                  <input
                    required
                    value={form.name}
                    onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))}
                    placeholder="Ex: FIBRA 100 MEGA START"
                    className={PANEL_INPUT}
                  />
                </div>
                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <label className="mb-1 block text-xs font-bold text-muted-foreground uppercase">
                      Tecnologia
                    </label>
                    <select
                      value={form.type}
                      onChange={(e) => setForm((f) => ({ ...f, type: e.target.value }))}
                      className={PANEL_INPUT}
                    >
                      <option value="FIBRA">Fibra Óptica</option>
                      <option value="RADIO">Rádio</option>
                      <option value="CABO">Cabo</option>
                    </select>
                  </div>
                  <div>
                    <label className="mb-1 block text-xs font-bold text-muted-foreground uppercase">
                      Preço Mensal (R$)
                    </label>
                    <input
                      required
                      type="number"
                      step="0.01"
                      value={form.price}
                      onChange={(e) => setForm((f) => ({ ...f, price: e.target.value }))}
                      placeholder="89.90"
                      className={PANEL_INPUT}
                    />
                  </div>
                </div>
                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <label className="mb-1 block text-xs font-bold text-muted-foreground uppercase">
                      Download (Mbps)
                    </label>
                    <input
                      required
                      type="number"
                      value={form.download_speed}
                      onChange={(e) => setForm((f) => ({ ...f, download_speed: e.target.value }))}
                      className={PANEL_INPUT}
                    />
                  </div>
                  <div>
                    <label className="mb-1 block text-xs font-bold text-muted-foreground uppercase">
                      Upload (Mbps)
                    </label>
                    <input
                      required
                      type="number"
                      value={form.upload_speed}
                      onChange={(e) => setForm((f) => ({ ...f, upload_speed: e.target.value }))}
                      className={PANEL_INPUT}
                    />
                  </div>
                </div>
                <div>
                  <label className="mb-1 block text-xs font-bold text-muted-foreground uppercase">
                    Descrição (Aparece em Detalhes)
                  </label>
                  <textarea
                    rows={4}
                    value={form.description}
                    onChange={(e) => setForm((f) => ({ ...f, description: e.target.value }))}
                    placeholder="Descreva o que está incluso no plano..."
                    className={`${PANEL_INPUT} resize-none`}
                  />
                </div>
                <label className="flex cursor-pointer items-center gap-3">
                  <ToggleSwitch
                    checked={form.is_active}
                    onChange={(v) => setForm((f) => ({ ...f, is_active: v }))}
                  />
                  <span className="text-sm font-bold text-muted-foreground uppercase">Ativo no App</span>
                </label>
              </div>
              <div className="flex justify-end gap-3 bg-muted/40 px-6 py-4">
                <button
                  type="button"
                  onClick={() => setModalOpen(false)}
                  className="px-4 py-2 text-xs font-bold text-muted-foreground uppercase hover:text-foreground"
                >
                  Cancelar
                </button>
                <button type="submit" disabled={saving} className={`${BTN_PRIMARY} px-6 uppercase text-xs`}>
                  {saving ? 'Salvando…' : 'Salvar Plano'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  )
}

function SgpIntegrationPanel({ sgp, setSgp, onSaveSgp, onSaveGenie, onRotateToken, onNotify }) {
  const [sgpForm, setSgpForm] = useState({
    erp_type: 'sgp',
    sgp_url: '',
    sgp_token: '',
    sgp_app_name: '',
    app_default_team_id: '',
  })
  const [genieForm, setGenieForm] = useState({
    genieacs_url: '',
    genieacs_token: '',
  })
  const [savingSgp, setSavingSgp] = useState(false)
  const [savingGenie, setSavingGenie] = useState(false)
  const [showGatewayToken, setShowGatewayToken] = useState(false)

  useEffect(() => {
    if (!sgp) return
    setSgpForm({
      erp_type: sgp.erp_type === 'receitanet' ? 'receitanet' : 'sgp',
      sgp_url: sgp.sgp_url || '',
      sgp_token: sgp.sgp_token || '',
      sgp_app_name: sgp.sgp_app_name || '',
      app_default_team_id:
        sgp.app_default_team_id != null && sgp.app_default_team_id !== ''
          ? String(sgp.app_default_team_id)
          : '',
    })
    setGenieForm({
      genieacs_url: sgp.genieacs_url || '',
      genieacs_token: sgp.genieacs_token || '',
    })
  }, [sgp])

  if (!sgp) {
    return <div className="p-6 text-sm text-muted-foreground">Carregando integração…</div>
  }

  const isSgp = sgpForm.erp_type !== 'receitanet'

  const token = sgp.provider_token || ''
  const baseWebhook = (sgp.webhook_url || '').replace(/\?.*$/, '').replace(/\/$/, '')
  const gatewayUrl = `${baseWebhook}/?provider_id=${sgp.provedor_id}&provider_token=${token || 'SEU_TOKEN_AQUI'}&do_post=true&message_title=Aviso%20Importante`
  const gatewayJson = JSON.stringify(
    {
      url: gatewayUrl,
      method: 'POST',
      body: {
        event_type: 'new_message',
        data: { info: 'Payload opcional enviado pelo ERP' },
      },
      headers: { 'Content-Type': 'application/json' },
    },
    null,
    2,
  )

  const copyText = async (value, label = 'Copiado!') => {
    try {
      await navigator.clipboard.writeText(value)
      onNotify?.(label)
    } catch {
      onNotify?.('Não foi possível copiar.')
    }
  }

  const submitSgp = async (e) => {
    e.preventDefault()
    setSavingSgp(true)
    try {
      const payload = {
        erp_type: sgpForm.erp_type,
        sgp_url: sgpForm.sgp_url,
        sgp_token: sgpForm.sgp_token,
        app_default_team_id: sgpForm.app_default_team_id,
      }
      if (sgpForm.erp_type === 'sgp') {
        payload.sgp_app_name = sgpForm.sgp_app_name
      }
      await onSaveSgp(payload)
    } finally {
      setSavingSgp(false)
    }
  }

  const submitGenie = async (e) => {
    e.preventDefault()
    setSavingGenie(true)
    try {
      await onSaveGenie(genieForm)
    } finally {
      setSavingGenie(false)
    }
  }

  return (
    <div className="mx-auto max-w-7xl space-y-8 p-6">
      <div>
        <h1 className="text-3xl font-extrabold tracking-tight text-foreground">Integração ERP</h1>
        <p className="mt-2 text-sm text-muted-foreground">
          Configure sua integração com o seu ERP para automação e notificações.
        </p>
      </div>

      <div className="grid grid-cols-1 gap-8 lg:grid-cols-2">
        <div className={`${PANEL_CARD} rounded-2xl shadow-xl`}>
          <div className="mb-6 flex items-center">
            <div className="mr-4 flex h-10 w-10 items-center justify-center rounded-lg bg-sky-500/20 text-sky-400 ring-1 ring-sky-400/30">
              <Settings2 className="h-6 w-6" />
            </div>
            <h2 className="text-xl font-bold text-foreground">Credenciais do ERP</h2>
          </div>
          <form onSubmit={submitSgp} className="space-y-4">
            <div>
              <label className="mb-1 block text-sm font-medium text-muted-foreground">ERP</label>
              <select
                value={sgpForm.erp_type}
                onChange={(e) => setSgpForm((f) => ({ ...f, erp_type: e.target.value }))}
                className={PANEL_INPUT}
              >
                <option value="sgp">SGP</option>
                <option value="receitanet">ReceitaNet</option>
              </select>
            </div>
            <div>
              <label className="mb-1 block text-sm font-medium text-muted-foreground">URL do Host do ERP</label>
              <input
                type="url"
                value={sgpForm.sgp_url}
                onChange={(e) => setSgpForm((f) => ({ ...f, sgp_url: e.target.value }))}
                placeholder="https://erp.seuprovedor.com.br"
                className={PANEL_INPUT}
              />
            </div>
            <div>
              <label className="mb-1 block text-sm font-medium text-muted-foreground">Token do ERP (API)</label>
              <SecretField
                value={sgpForm.sgp_token}
                onChange={(e) => setSgpForm((f) => ({ ...f, sgp_token: e.target.value }))}
                placeholder="Seu token de API do ERP"
              />
            </div>
            {isSgp && (
              <div>
                <label className="mb-1 block text-sm font-medium text-muted-foreground">Nome do App no ERP</label>
                <input
                  type="text"
                  value={sgpForm.sgp_app_name}
                  onChange={(e) => setSgpForm((f) => ({ ...f, sgp_app_name: e.target.value }))}
                  placeholder="ex: app_mobile"
                  className={PANEL_INPUT}
                />
              </div>
            )}
            <div>
              <label className="mb-1 block text-sm font-medium text-muted-foreground">
                ID da equipe
              </label>
              <input
                type="number"
                min="1"
                step="1"
                value={sgpForm.app_default_team_id}
                onChange={(e) =>
                  setSgpForm((f) => ({ ...f, app_default_team_id: e.target.value }))
                }
                placeholder="Ex: 20"
                className={PANEL_INPUT}
              />
            </div>
            <button type="submit" disabled={savingSgp} className={`${BTN_PRIMARY} w-full`}>
              {savingSgp ? 'Salvando…' : 'Salvar Configurações'}
            </button>
          </form>
        </div>

        <div className={`${PANEL_CARD} rounded-2xl shadow-xl`}>
          <div className="mb-6 flex items-center">
            <div className="mr-4 flex h-10 w-10 items-center justify-center rounded-lg bg-emerald-500/20 text-emerald-400 ring-1 ring-emerald-400/30">
              <Router className="h-6 w-6" />
            </div>
            <h2 className="text-xl font-bold text-foreground">Credenciais GenieACS</h2>
          </div>
          <form onSubmit={submitGenie} className="space-y-4">
            <div>
              <label className="mb-1 block text-sm font-medium text-muted-foreground">
                URL do Host GenieACS
              </label>
              <input
                type="url"
                value={genieForm.genieacs_url}
                onChange={(e) => setGenieForm((f) => ({ ...f, genieacs_url: e.target.value }))}
                placeholder="http://tr069.seuprovedor.com.br:7557"
                className={PANEL_INPUT}
              />
            </div>
            <div>
              <label className="mb-1 block text-sm font-medium text-muted-foreground">Token (API)</label>
              <SecretField
                value={genieForm.genieacs_token}
                onChange={(e) => setGenieForm((f) => ({ ...f, genieacs_token: e.target.value }))}
                placeholder="Token da API de integração"
              />
            </div>
            <button
              type="submit"
              disabled={savingGenie}
              className="inline-flex w-full items-center justify-center gap-2 rounded-lg bg-orange-500 px-4 py-2 text-sm font-medium text-white shadow-sm transition-colors hover:bg-orange-500/90"
            >
              {savingGenie ? 'Salvando…' : 'Salvar Configurações'}
            </button>
          </form>
        </div>
      </div>

      <div className={`${PANEL_CARD} rounded-2xl shadow-xl`}>
        <div className="flex flex-col items-start justify-between gap-6 md:flex-row md:items-center">
          <div className="flex items-center">
            <div className="mr-4 flex h-12 w-12 items-center justify-center rounded-xl bg-emerald-500/20 text-emerald-500">
              <KeyRound className="h-7 w-7" />
            </div>
            <div>
              <h2 className="text-xl font-bold text-foreground">Seu Token de Integração</h2>
              <p className="mt-1 text-sm text-muted-foreground">Token de segurança para APIs externas.</p>
            </div>
          </div>

          <div className="w-full max-w-2xl flex-1">
            <div className="relative">
              <SecretField
                readOnly
                value={token || 'Nenhum token ativo'}
                className="font-mono text-sm"
                rightPaddingClass="pr-36"
                eyeClassName="right-[6.5rem]"
              >
                <button
                  type="button"
                  disabled={!token}
                  onClick={() => copyText(token, 'Token copiado!')}
                  className="absolute top-1.5 right-1.5 bottom-1.5 z-10 inline-flex items-center gap-1 rounded-lg bg-emerald-600 px-3 text-xs font-medium text-white hover:bg-emerald-500 disabled:opacity-40"
                >
                  <Copy className="h-3.5 w-3.5" />
                  Copiar
                </button>
              </SecretField>
            </div>
            <p className="mt-2 ml-1 text-[10px] text-muted-foreground">
              Gerado em: {sgp.sgp_token_created_at || '—'}
            </p>
          </div>

          <button
            type="button"
            onClick={onRotateToken}
            className="inline-flex shrink-0 items-center gap-2 rounded-xl bg-red-500 px-6 py-3 text-sm font-semibold text-white hover:bg-red-600"
          >
            <RefreshCw className="h-5 w-5" />
            Gerar Novo Token
          </button>
        </div>
      </div>

      <div className={`${PANEL_CARD} relative overflow-hidden rounded-2xl p-8 shadow-xl`}>
        <div className="pointer-events-none absolute top-0 right-0 p-8 opacity-5">
          <AlertTriangle className="h-32 w-32" />
        </div>
        <div className="mb-8 flex flex-col gap-6 md:flex-row md:items-center md:justify-between">
          <div>
            <h2 className="text-2xl font-bold text-foreground">Configuração do Gateway no ERP</h2>
            <p className="mt-1 text-muted-foreground">
              Use este modelo de JSON para configurar o gateway no modo genérico.
            </p>
          </div>
          <div className="flex shrink-0 items-center gap-2">
            <button
              type="button"
              onClick={() => setShowGatewayToken((v) => !v)}
              className="inline-flex items-center justify-center gap-2 rounded-xl border border-border bg-secondary px-4 py-3 text-sm text-secondary-foreground hover:bg-muted"
              title={showGatewayToken ? 'Ocultar token no JSON' : 'Mostrar token no JSON'}
            >
              {showGatewayToken ? <EyeOff className="h-5 w-5" /> : <Eye className="h-5 w-5" />}
            </button>
            <button
              type="button"
              onClick={() => copyText(gatewayJson, 'JSON copiado!')}
              className={`${BTN_PRIMARY} rounded-xl px-6 py-3`}
            >
              <Copy className="h-5 w-5" />
              Copiar JSON Completo
            </button>
          </div>
        </div>

        <div className="overflow-x-auto rounded-xl border border-border bg-black/40 p-6 font-mono text-sm">
          <pre className="whitespace-pre text-primary">
{`{
  "url": "`}
<span className="text-emerald-400">
              {showGatewayToken
                ? gatewayUrl
                : gatewayUrl.replace(/provider_token=[^&]*/i, 'provider_token=••••••••')}
            </span>
{`",
  "method": "POST",
  "body": {
    "event_type": "new_message",
    "data": {
      "info": "Payload opcional enviado pelo ERP"
    }
  },
  "headers": {
    "Content-Type": "application/json"
  }
}`}
          </pre>
        </div>

        <div className="mt-6 flex items-start rounded-xl border border-yellow-500/20 bg-yellow-500/10 p-4">
          <AlertTriangle className="mr-3 h-6 w-6 shrink-0 text-yellow-500" />
          <p className="text-sm text-yellow-200/80">
            O campo <code className="rounded bg-yellow-900/40 px-1">provider_token</code> no link acima é o seu
            token secreto. Certifique-se de que ele esteja correto para que as mensagens cheguem aos seus clientes.
          </p>
        </div>
      </div>
    </div>
  )
}


function StaffUsersPanel({ currentUserId, onNotify, onError }) {
  const [users, setUsers] = useState([])
  const [loading, setLoading] = useState(true)
  const [modalOpen, setModalOpen] = useState(false)
  const [saving, setSaving] = useState(false)
  const [editing, setEditing] = useState(null)
  const [form, setForm] = useState({
    username: '',
    password: '',
    email: '',
    first_name: '',
    last_name: '',
    user_type: 'admin',
    is_active: true,
  })

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const res = await axios.get('/api/mobile-app/panel/users/', { headers: authHeaders() })
      setUsers(Array.isArray(res.data) ? res.data : res.data.results || [])
    } catch (err) {
      onError?.(err?.response?.data?.error || 'Não foi possível carregar usuários.')
    } finally {
      setLoading(false)
    }
  }, [onError])

  useEffect(() => {
    load()
  }, [load])

  const openNew = () => {
    setEditing(null)
    setForm({
      username: '',
      password: '',
      email: '',
      first_name: '',
      last_name: '',
      user_type: 'admin',
      is_active: true,
    })
    setModalOpen(true)
  }

  const openEdit = (u) => {
    setEditing(u)
    setForm({
      username: u.username,
      password: '',
      email: u.email || '',
      first_name: u.first_name || '',
      last_name: u.last_name || '',
      user_type: u.user_type || 'admin',
      is_active: u.is_active !== false,
    })
    setModalOpen(true)
  }

  const submit = async (e) => {
    e.preventDefault()
    setSaving(true)
    try {
      if (editing) {
        const payload = {
          email: form.email,
          first_name: form.first_name,
          last_name: form.last_name,
          user_type: form.user_type,
          is_active: form.is_active,
        }
        if (form.password) payload.password = form.password
        const res = await axios.patch(`/api/mobile-app/panel/users/${editing.id}/`, payload, {
          headers: authHeaders(),
        })
        onNotify?.(res.data.message || 'Usuário atualizado com sucesso!')
      } else {
        const res = await axios.post(
          '/api/mobile-app/panel/users/',
          {
            username: form.username,
            password: form.password,
            email: form.email,
            first_name: form.first_name,
            last_name: form.last_name,
            user_type: form.user_type,
          },
          { headers: authHeaders() },
        )
        onNotify?.(res.data.message || 'Usuário criado com sucesso!')
      }
      setModalOpen(false)
      await load()
    } catch (err) {
      onError?.(err?.response?.data?.error || 'Falha ao salvar usuário.')
    } finally {
      setSaving(false)
    }
  }

  const remove = async (u) => {
    if (u.id === currentUserId) {
      onError?.('Você não pode excluir a própria conta.')
      return
    }
    if (!window.confirm(`Excluir o usuário "${u.username}"?`)) return
    try {
      await axios.delete(`/api/mobile-app/panel/users/${u.id}/`, { headers: authHeaders() })
      toast.deleted('Usuário excluído.')
      await load()
    } catch (err) {
      onError?.(err?.response?.data?.error || 'Falha ao excluir usuário.')
    }
  }

  const typeLabel = (t) => (t === 'agent' ? 'Atendente' : 'Administrador')

  return (
    <div className="space-y-6 p-6">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h2 className="mb-1 text-xl font-bold text-foreground">Usuários do painel</h2>
          <p className="text-sm text-muted-foreground">
            Crie e gerencie quem pode acessar o painel da sua empresa.
          </p>
        </div>
        <button type="button" onClick={openNew} className={`${BTN_PRIMARY} shrink-0`}>
          <Plus className="h-4 w-4" />
          Novo usuário
        </button>
      </div>

      <div className={`${PANEL_CARD} overflow-hidden p-0`}>
        {loading ? (
          <p className="p-6 text-sm text-muted-foreground">Carregando…</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead className="border-b border-border bg-muted/40 text-xs uppercase text-muted-foreground">
                <tr>
                  <th className="px-4 py-3 font-bold">Usuário</th>
                  <th className="px-4 py-3 font-bold">Nome</th>
                  <th className="px-4 py-3 font-bold">E-mail</th>
                  <th className="px-4 py-3 font-bold">Tipo</th>
                  <th className="px-4 py-3 font-bold">Status</th>
                  <th className="px-4 py-3 font-bold text-right">Ações</th>
                </tr>
              </thead>
              <tbody>
                {users.map((u) => (
                  <tr key={u.id} className="border-b border-border/60 last:border-0">
                    <td className="px-4 py-3 font-medium text-foreground">{u.username}</td>
                    <td className="px-4 py-3 text-muted-foreground">
                      {[u.first_name, u.last_name].filter(Boolean).join(' ') || '—'}
                    </td>
                    <td className="px-4 py-3 text-muted-foreground">{u.email || '—'}</td>
                    <td className="px-4 py-3 text-muted-foreground">{typeLabel(u.user_type)}</td>
                    <td className="px-4 py-3">
                      <span
                        className={`text-xs font-bold uppercase ${
                          u.is_active ? 'text-emerald-400' : 'text-red-500'
                        }`}
                      >
                        {u.is_active ? 'Ativo' : 'Inativo'}
                      </span>
                    </td>
                    <td className="px-4 py-3">
                      <div className="flex justify-end gap-2">
                        <button
                          type="button"
                          onClick={() => openEdit(u)}
                          className={BTN_EDIT}
                          title="Editar"
                        >
                          <Pencil className="h-4 w-4" />
                        </button>
                        <button
                          type="button"
                          onClick={() => remove(u)}
                          disabled={u.id === currentUserId}
                          className={BTN_DANGER}
                          title="Excluir"
                        >
                          <Trash2 className="h-4 w-4" />
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
                {users.length === 0 && (
                  <tr>
                    <td colSpan={6} className="px-4 py-10 text-center text-muted-foreground">
                      Nenhum usuário cadastrado ainda.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {modalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4">
          <div className="w-full max-w-lg overflow-hidden rounded-2xl border border-border bg-card shadow-xl">
            <form onSubmit={submit}>
              <div className="space-y-4 p-6">
                <h3 className="text-lg font-bold text-foreground">
                  {editing ? 'Editar usuário' : 'Novo usuário'}
                </h3>
                {!editing && (
                  <div>
                    <label className="mb-1 block text-xs font-bold text-muted-foreground uppercase">
                      Usuário
                    </label>
                    <input
                      required
                      value={form.username}
                      onChange={(e) => setForm((f) => ({ ...f, username: e.target.value }))}
                      className={PANEL_INPUT}
                      autoComplete="off"
                    />
                  </div>
                )}
                {editing && (
                  <div>
                    <label className="mb-1 block text-xs font-bold text-muted-foreground uppercase">
                      Usuário
                    </label>
                    <input readOnly value={form.username} className={`${PANEL_INPUT} opacity-70`} />
                  </div>
                )}
                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <label className="mb-1 block text-xs font-bold text-muted-foreground uppercase">
                      Nome
                    </label>
                    <input
                      value={form.first_name}
                      onChange={(e) => setForm((f) => ({ ...f, first_name: e.target.value }))}
                      className={PANEL_INPUT}
                    />
                  </div>
                  <div>
                    <label className="mb-1 block text-xs font-bold text-muted-foreground uppercase">
                      Sobrenome
                    </label>
                    <input
                      value={form.last_name}
                      onChange={(e) => setForm((f) => ({ ...f, last_name: e.target.value }))}
                      className={PANEL_INPUT}
                    />
                  </div>
                </div>
                <div>
                  <label className="mb-1 block text-xs font-bold text-muted-foreground uppercase">
                    E-mail
                  </label>
                  <input
                    type="email"
                    value={form.email}
                    onChange={(e) => setForm((f) => ({ ...f, email: e.target.value }))}
                    className={PANEL_INPUT}
                  />
                </div>
                <div>
                  <label className="mb-1 block text-xs font-bold text-muted-foreground uppercase">
                    {editing ? 'Nova senha (opcional)' : 'Senha'}
                  </label>
                  <input
                    type="password"
                    required={!editing}
                    value={form.password}
                    onChange={(e) => setForm((f) => ({ ...f, password: e.target.value }))}
                    className={PANEL_INPUT}
                    autoComplete="new-password"
                  />
                </div>
                <div>
                  <label className="mb-1 block text-xs font-bold text-muted-foreground uppercase">
                    Tipo
                  </label>
                  <select
                    value={form.user_type}
                    onChange={(e) => setForm((f) => ({ ...f, user_type: e.target.value }))}
                    className={PANEL_INPUT}
                  >
                    <option value="admin">Administrador</option>
                    <option value="agent">Atendente</option>
                  </select>
                </div>
                {editing && (
                  <label className="flex cursor-pointer items-center gap-3">
                    <ToggleSwitch
                      checked={form.is_active}
                      onChange={(v) => setForm((f) => ({ ...f, is_active: v }))}
                    />
                    <span className="text-sm font-bold text-muted-foreground uppercase">Ativo</span>
                  </label>
                )}
              </div>
              <div className="flex justify-end gap-3 bg-muted/40 px-6 py-4">
                <button
                  type="button"
                  onClick={() => setModalOpen(false)}
                  className="px-4 py-2 text-xs font-bold text-muted-foreground uppercase hover:text-foreground"
                >
                  Cancelar
                </button>
                <button type="submit" disabled={saving} className={`${BTN_PRIMARY} px-6 text-xs uppercase`}>
                  {saving ? 'Salvando…' : 'Salvar'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  )
}

const DEFAULT_PRIMARY = '#0D70B3'

const THEME_COLORS = [
  ['primary_color', 'Cor principal', 'Barra superior, botões, ícones e destaques do app.'],
  ['secondary_color', 'Cor secundária', 'Detalhes, bolhas do chat e textos sobre cards claros.'],
  ['login_bg_color', 'Fundo do login', 'Cor base do fundo da tela de login.'],
  ['login_button_color', 'Botão ENTRAR', 'Cor do botão de entrar na tela de login.'],
  ['login_text_color', 'Textos do login', 'Textos, campo de CPF e links da tela de login.'],
  ['app_bg_color', 'Fundo do app', 'Fundo das telas no modo claro. Vazio usa a mesma cor do fundo do login.'],
  ['card_color', 'Cor dos cards', 'Cards e barra inferior no modo claro. O texto escurece ou clareia sozinho.'],
]

const isHexColor = (v) => /^#[0-9A-Fa-f]{6}$/.test(v || '')

function ColorField({ label, help, value, defaultValue, onChange, onReset }) {
  const effective = isHexColor(value) ? value : isHexColor(defaultValue) ? defaultValue : '#000000'
  return (
    <div className="flex flex-col gap-2 border-b border-border px-5 py-4 last:border-b-0 sm:flex-row sm:items-center sm:justify-between sm:gap-6">
      <div className="min-w-0">
        <p className="text-xs font-bold tracking-wide text-muted-foreground uppercase">{label}</p>
        <p className="mt-1 text-xs text-muted-foreground">{help}</p>
      </div>
      <div className="flex shrink-0 items-center gap-2">
        <input
          type="color"
          value={effective}
          onChange={(e) => onChange(e.target.value.toUpperCase())}
          className="h-9 w-12 cursor-pointer rounded border border-border bg-background p-0.5"
          aria-label={label}
        />
        <input
          type="text"
          value={value}
          onChange={(e) => onChange(e.target.value.toUpperCase())}
          placeholder={isHexColor(defaultValue) ? `Padrão ${defaultValue}` : 'Padrão do app'}
          maxLength={7}
          className={`${PANEL_INPUT} w-32 font-mono`}
        />
        <button type="button" onClick={onReset} className={BTN_GHOST} title="Voltar para a cor padrão do app">
          Padrão
        </button>
      </div>
    </div>
  )
}

function LogoField({ label, help, preview, onPick, onRemove, previewBg }) {
  const inputRef = useRef(null)
  const openPicker = () => inputRef.current?.click()
  return (
    <div className="flex flex-col gap-3 border-b border-border px-5 py-4 last:border-b-0 sm:flex-row sm:items-center sm:justify-between sm:gap-6">
      <div className="min-w-0">
        <p className="text-xs font-bold tracking-wide text-muted-foreground uppercase">{label}</p>
        <p className="mt-1 text-xs text-muted-foreground">{help}</p>
      </div>
      <div className="flex shrink-0 items-center gap-3">
        <button
          type="button"
          onClick={openPicker}
          title="Clique para carregar uma imagem"
          className={`group flex h-16 w-32 items-center justify-center overflow-hidden rounded-lg border transition-colors hover:border-primary ${
            preview ? 'border-border' : 'border-dashed border-muted-foreground/50'
          }`}
          style={{ background: previewBg }}
        >
          {preview ? (
            <img src={preview} alt={label} className="max-h-14 max-w-[7.5rem] object-contain" />
          ) : (
            <span
              className="flex flex-col items-center gap-1 px-2 text-center text-[11px] opacity-80 group-hover:opacity-100"
              style={{ color: onColor(previewBg) }}
            >
              <Upload className="h-4 w-4" />
              Clique para carregar
            </span>
          )}
        </button>
        <button type="button" onClick={openPicker} className={BTN_GHOST}>
          <Upload className="h-4 w-4" />
          Carregar
        </button>
        <input
          ref={inputRef}
          type="file"
          accept="image/png,image/jpeg,image/webp"
          className="hidden"
          onChange={(e) => {
            const f = e.target.files?.[0]
            if (f) onPick(f)
            e.target.value = ''
          }}
        />
        {preview && (
          <button type="button" onClick={onRemove} className={BTN_DANGER} title="Remover logo">
            <Trash2 className="h-4 w-4" />
          </button>
        )}
      </div>
    </div>
  )
}

const hexToRgb = (hex) => {
  const n = parseInt(hex.slice(1), 16)
  return [(n >> 16) & 255, (n >> 8) & 255, n & 255]
}

const rgbToHex = (r, g, b) =>
  `#${[r, g, b].map((v) => Math.round(Math.min(255, Math.max(0, v))).toString(16).padStart(2, '0')).join('')}`.toUpperCase()

const rgba = (hex, alpha) => {
  const [r, g, b] = hexToRgb(hex)
  return `rgba(${r}, ${g}, ${b}, ${alpha})`
}

const mixHex = (a, b, t) => {
  const A = hexToRgb(a)
  const B = hexToRgb(b)
  return rgbToHex(...A.map((v, i) => v + (B[i] - v) * t))
}

// Mesmo cálculo do _shade do app (desloca a luminosidade em HSL).
function shadeHex(hex, amount) {
  const [r, g, b] = hexToRgb(hex).map((v) => v / 255)
  const max = Math.max(r, g, b)
  const min = Math.min(r, g, b)
  const l = (max + min) / 2
  const d = max - min
  let h = 0
  let s = 0
  if (d) {
    s = d / (1 - Math.abs(2 * l - 1))
    if (max === r) h = ((g - b) / d) % 6
    else if (max === g) h = (b - r) / d + 2
    else h = (r - g) / d + 4
    h *= 60
    if (h < 0) h += 360
  }
  const nl = Math.min(1, Math.max(0, l + amount))
  const c = (1 - Math.abs(2 * nl - 1)) * s
  const x = c * (1 - Math.abs(((h / 60) % 2) - 1))
  const m = nl - c / 2
  const [r1, g1, b1] =
    h < 60 ? [c, x, 0] : h < 120 ? [x, c, 0] : h < 180 ? [0, c, x] : h < 240 ? [0, x, c] : h < 300 ? [x, 0, c] : [c, 0, x]
  return rgbToHex((r1 + m) * 255, (g1 + m) * 255, (b1 + m) * 255)
}

// Mesma regra do AppBranding do app: campo vazio usa a cor de fábrica do build daquele provedor.
function previewTheme(form, defaults) {
  const pick = (v) => (isHexColor(v) ? v.toUpperCase() : null)
  const factoryPrimary = pick(defaults?.primary_color)
  const custom = pick(form?.primary_color)
  const customPrimary = custom && custom !== factoryPrimary ? custom : null
  const primary = customPrimary || factoryPrimary || DEFAULT_PRIMARY
  const factory = (key, fallback) => (customPrimary ? fallback : pick(defaults?.[key]) || fallback)
  const loginBg = pick(form?.login_bg_color) || factory('login_bg_color', shadeHex(primary, -0.22))
  return {
    primary,
    loginBg,
    loginButton: pick(form?.login_button_color) || factory('login_button_color', primary),
    loginText: pick(form?.login_text_color) || pick(defaults?.login_text_color) || '#FFFFFF',
    appBg: pick(form?.app_bg_color) || loginBg,
    card: pick(form?.card_color) || '#FFFFFF',
  }
}

// Mesmo critério do ThemeData.estimateBrightnessForColor do Flutter.
const isDarkColor = (hex) => {
  const lin = (v) => {
    const c = v / 255
    return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4
  }
  const [r, g, b] = hexToRgb(hex).map(lin)
  const luminance = 0.2126 * r + 0.7152 * g + 0.0722 * b
  return (luminance + 0.05) ** 2 <= 0.15
}
const onColor = (hex) => (isDarkColor(hex) ? '#FFFFFF' : '#1F2124')

const HOME_SHORTCUTS = [
  { ids: ['wifi', 'MEU WI-FI', 'meu_wifi'], icon: Wifi, label: 'Meu Wi-Fi' },
  { ids: ['CONSUMO', 'consumo'], icon: ChartColumn, label: 'Consumo' },
  { ids: ['cameras', 'CÂMERAS', 'cameras_cftv'], icon: Video, label: 'Câmeras' },
  { ids: ['speed_test', 'FAST TEST', 'speedtest', 'SPEED_TEST'], icon: Gauge, label: 'Teste de Velocidade' },
  { ids: ['diagnostic', 'DIAGNÓSTICO WI-FI', 'wifi_diagnostic', 'DIAGNOSTICO WI-FI'], icon: Activity, label: 'Diagnóstico' },
  { ids: ['PLANOS', 'planos'], icon: Layers, label: 'Planos' },
  {
    ids: ['contrato', 'CONTRATO', 'CONTRATO ASSINADO', 'contrato_assinado', 'CONTRATO_ASSINADO'],
    icon: FileText,
    label: 'Contrato Assinado',
  },
  { ids: ['nota_fiscal', 'NOTA FISCAL', 'notas', 'NOTAS'], icon: ReceiptText, label: 'Nota Fiscal' },
  {
    ids: ['connected_devices', 'CONNECTED_DEVICES', 'dispositivos', 'DISPOSITIVOS CONECTADOS'],
    icon: MonitorSmartphone,
    label: 'Dispositivos',
  },
]

function homeShortcuts(config) {
  if (!config) return []
  const tools = {
    speed_test: config.tool_speed_test,
    auto_unlock: config.tool_auto_unlock,
    faturas: config.tool_faturas,
    connected_devices: config.tool_connected_devices,
    wifi: config.tool_wifi,
    cameras: config.tool_cameras,
  }
  const keys = new Set([
    ...(Array.isArray(config.active_shortcuts) ? config.active_shortcuts : []),
    ...Object.keys(tools).filter((k) => tools[k]),
  ])
  return HOME_SHORTCUTS.filter((item) =>
    item.ids.some((id) => keys.has(id) || keys.has(id.toUpperCase()) || keys.has(id.toLowerCase())),
  )
}

function seededRandom(seed) {
  let s = seed >>> 0
  return () => {
    s = (s + 0x6d2b79f5) >>> 0
    let t = s
    t = Math.imul(t ^ (t >>> 15), t | 1)
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61)
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296
  }
}

// Porta do BrandLoginBackground do app (lib/widgets/brand_login_background.dart).
function paintLoginBackground(ctx, w, h, base, glow) {
  const line = mixHex(glow, '#FFFFFF', 0.35)
  const dot = mixHex(glow, '#FFFFFF', 0.45)
  const radial = (ax, ay, radius, stops) => {
    const cx = w / 2 + (ax * w) / 2
    const cy = h / 2 + (ay * h) / 2
    const g = ctx.createRadialGradient(cx, cy, 0, cx, cy, radius * Math.min(w, h))
    stops.forEach(([offset, color]) => g.addColorStop(offset, color))
    ctx.fillStyle = g
    ctx.fillRect(0, 0, w, h)
  }
  const stroke = (width, color, draw) => {
    ctx.beginPath()
    draw()
    ctx.lineWidth = width
    ctx.strokeStyle = color
    ctx.stroke()
  }

  const bg = ctx.createLinearGradient(0, 0, w, h)
  bg.addColorStop(0, base)
  bg.addColorStop(0.32, shadeHex(base, 0.07))
  bg.addColorStop(0.68, shadeHex(base, -0.03))
  bg.addColorStop(1, shadeHex(base, 0.11))
  ctx.fillStyle = bg
  ctx.fillRect(0, 0, w, h)

  radial(-0.75, -0.75, 1.0, [
    [0, rgba(shadeHex(glow, 0.08), 0.38)],
    [0.4, rgba(glow, 0.15)],
    [1, 'rgba(0,0,0,0)'],
  ])
  radial(0.15, -0.2, 0.95, [
    [0, rgba(glow, 0.22)],
    [1, 'rgba(0,0,0,0)'],
  ])
  radial(0.85, 0.95, 0.7, [
    [0, rgba(shadeHex(glow, 0.06), 0.36)],
    [0.5, rgba(glow, 0.1)],
    [1, 'rgba(0,0,0,0)'],
  ])

  const mainWave = () => {
    ctx.moveTo(0, h * 0.23)
    ctx.bezierCurveTo(w * 0.2, h * 0.34, w * 0.54, h * 0.36, w, h * 0.07)
  }
  stroke(1.5, rgba(line, 0.65), mainWave)
  ctx.filter = 'blur(10px)'
  stroke(8, rgba(shadeHex(glow, 0.06), 0.2), mainWave)
  ctx.filter = 'none'

  for (let i = 0; i < 24; i++) {
    const o = i * 4.5
    stroke(0.45, rgba(line, 0.18), () => {
      ctx.moveTo(0, h * 0.23 + o)
      ctx.bezierCurveTo(w * 0.24, h * 0.36 + o * 0.35, w * 0.59, h * 0.37 + o * 0.28, w, h * 0.07 + o * 0.2)
    })
  }

  const random = seededRandom(10)
  const circle = (x, y, r, color) => {
    ctx.beginPath()
    ctx.arc(x, y, r, 0, Math.PI * 2)
    ctx.fillStyle = color
    ctx.fill()
  }
  for (let i = 0; i < 450; i++) {
    const x = random() * w
    const y = h * 0.19 + random() * h * 0.25
    const curveY = h * (0.22 + 0.18 * Math.sin((x / w) * Math.PI))
    if (y > curveY) circle(x, y, 0.3 + random() * 1.2, rgba(dot, 0.05 + random() * 0.17))
  }

  stroke(1.2, rgba(line, 0.45), () => {
    ctx.moveTo(w * 0.52, h)
    ctx.bezierCurveTo(w * 0.68, h * 0.92, w * 0.83, h * 0.89, w, h * 0.85)
  })
  for (let i = 0; i < 20; i++) {
    const o = i * 5
    stroke(0.45, rgba(line, 0.15), () => {
      ctx.moveTo(w * 0.53, h + o)
      ctx.bezierCurveTo(w * 0.7, h * 0.94 + o * 0.18, w * 0.87, h * 0.9 + o * 0.18, w, h * 0.86 + o * 0.15)
    })
  }
  for (let i = 0; i < 180; i++) {
    const x = w * 0.55 + random() * w * 0.45
    const y = h * 0.83 + random() * h * 0.17
    circle(x, y, 0.3 + random() * 1, rgba(dot, 0.05 + random() * 0.18))
  }

  radial(0, 0, 1.0, [
    [0.4, 'rgba(0,0,0,0)'],
    [0.78, 'rgba(0,0,0,0.08)'],
    [1, 'rgba(0,0,0,0.2)'],
  ])
}

const PHONE_W = 360
const PHONE_H = 780
const PHONE_SCALE = 0.75

function LoginBackgroundCanvas({ base, glow }) {
  const ref = useRef(null)
  useEffect(() => {
    const canvas = ref.current
    if (!canvas) return
    const dpr = window.devicePixelRatio || 1
    canvas.width = PHONE_W * dpr
    canvas.height = PHONE_H * dpr
    const ctx = canvas.getContext('2d')
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
    paintLoginBackground(ctx, PHONE_W, PHONE_H, base, glow)
  }, [base, glow])
  return <canvas ref={ref} style={{ position: 'absolute', inset: 0, width: PHONE_W, height: PHONE_H }} />
}

function PhoneFrame({ background, children }) {
  return (
    <div
      className="mx-auto overflow-hidden rounded-[2rem] border-[6px] border-zinc-800 shadow-xl"
      style={{ width: PHONE_W * PHONE_SCALE + 12, height: PHONE_H * PHONE_SCALE + 12, background }}
    >
      <div
        className="relative origin-top-left overflow-hidden"
        style={{
          width: PHONE_W,
          height: PHONE_H,
          transform: `scale(${PHONE_SCALE})`,
          fontFamily: 'Roboto, "Segoe UI", system-ui, sans-serif',
        }}
      >
        {children}
      </div>
    </div>
  )
}

function PhoneStatusBar({ color }) {
  return (
    <div className="flex items-center justify-between px-5" style={{ height: 28, color, fontSize: 13, fontWeight: 600 }}>
      <span>13:40</span>
      <span className="flex items-center gap-1.5">
        <Wifi size={14} />
        <span className="relative inline-block rounded-[3px] border" style={{ width: 22, height: 11, borderColor: color }}>
          <span className="absolute inset-[1.5px] rounded-[1px]" style={{ background: color, right: 6 }} />
        </span>
      </span>
    </div>
  )
}

function LogoPlaceholder({ color, height }) {
  return (
    <div
      className="flex w-full items-center justify-center rounded-2xl border-2 border-dashed text-center"
      style={{ height, borderColor: rgba(color, 0.35), color: rgba(color, 0.75), fontSize: 14 }}
    >
      Logo padrão do app
    </div>
  )
}

function PixGlyph({ size = 30 }) {
  return (
    <svg width={size} height={size} viewBox="0 0 16 16" fill="#FFFFFF" aria-hidden="true">
      <path d="M11.917 11.71a2.046 2.046 0 0 1-1.454-.602l-2.1-2.1a.4.4 0 0 0-.551 0l-2.108 2.108a2.044 2.044 0 0 1-1.454.602h-.414l2.66 2.66c.83.83 2.177.83 3.007 0l2.667-2.668h-.253zM4.25 4.282c.55 0 1.066.214 1.454.602l2.108 2.108a.39.39 0 0 0 .552 0l2.1-2.1a2.044 2.044 0 0 1 1.453-.602h.253L9.503 1.623a2.127 2.127 0 0 0-3.007 0l-2.66 2.66h.414z" />
      <path d="m14.377 6.496-1.612-1.612a.307.307 0 0 1-.114.023h-.733c-.379 0-.75.154-1.017.422l-2.1 2.1a1.005 1.005 0 0 1-1.425 0L5.268 5.32a1.448 1.448 0 0 0-1.018-.422h-.9a.306.306 0 0 1-.109-.021L1.623 6.496c-.83.83-.83 2.177 0 3.008l1.618 1.618a.305.305 0 0 1 .108-.022h.901c.38 0 .75-.153 1.018-.421L7.375 8.57a1.034 1.034 0 0 1 1.426 0l2.1 2.1c.267.268.638.421 1.017.421h.733c.04 0 .079.01.114.024l1.612-1.612c.83-.83.83-2.178 0-3.008z" />
    </svg>
  )
}

function WhatsappGlyph({ size = 22 }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="#FFFFFF" aria-hidden="true">
      <path d="M17.47 14.38c-.3-.15-1.76-.87-2.03-.97-.27-.1-.47-.15-.67.15-.2.3-.77.97-.94 1.17-.17.2-.35.22-.65.07-.3-.15-1.26-.46-2.4-1.48-.89-.79-1.49-1.77-1.66-2.07-.17-.3-.02-.46.13-.61.13-.13.3-.35.45-.52.15-.17.2-.3.3-.5.1-.2.05-.37-.03-.52-.07-.15-.67-1.62-.92-2.22-.24-.58-.49-.5-.67-.51h-.57c-.2 0-.52.07-.79.37-.27.3-1.04 1.02-1.04 2.48s1.07 2.88 1.21 3.08c.15.2 2.1 3.2 5.08 4.49.71.31 1.26.49 1.69.63.71.23 1.36.2 1.87.12.57-.09 1.76-.72 2.01-1.41.25-.69.25-1.29.17-1.41-.07-.13-.27-.2-.57-.35zM12.05 21.5h-.01a9.4 9.4 0 0 1-4.79-1.31l-.34-.2-3.56.93.95-3.47-.22-.36a9.38 9.38 0 0 1-1.44-5c0-5.19 4.23-9.42 9.43-9.42 2.52 0 4.88.98 6.66 2.76a9.36 9.36 0 0 1 2.76 6.67c0 5.2-4.23 9.42-9.43 9.42zm8.02-17.44A11.27 11.27 0 0 0 12.05.75C5.8.75.72 5.83.72 12.08c0 2 .52 3.95 1.52 5.66L.62 23.25l5.64-1.48a11.3 11.3 0 0 0 5.79 1.47h.01c6.25 0 11.33-5.08 11.33-11.33 0-3.03-1.18-5.87-3.32-8.01z" />
    </svg>
  )
}

function LoginPreview({ theme, logo, savedUser }) {
  const text = theme.loginText
  const button = theme.loginButton
  return (
    <PhoneFrame background={theme.loginBg}>
      <LoginBackgroundCanvas base={theme.loginBg} glow={theme.primary} />
      <div className="relative flex h-full flex-col">
        <PhoneStatusBar color="#FFFFFF" />
        <div className="flex flex-col" style={{ padding: '0 24px' }}>
          <div style={{ height: 56 }} />
          <div className="flex items-center justify-center" style={{ height: 135 }}>
            {logo ? (
              <img src={logo} alt="" style={{ maxHeight: 135, maxWidth: '100%', objectFit: 'contain' }} />
            ) : (
              <LogoPlaceholder color={text} height={135} />
            )}
          </div>
          <div style={{ height: 48 }} />
          <p style={{ color: text, fontSize: 28, fontWeight: 700, lineHeight: 1.2 }}>Acesse sua conta</p>
          <div style={{ height: 12 }} />
          <p style={{ color: rgba(text, 0.92), fontSize: 17, lineHeight: 1.3 }}>Informe seu CPF ou CNPJ para começar</p>
          <div style={{ height: 34 }} />
          {savedUser ? (
            <div
              className="flex items-center bg-white"
              style={{ padding: 16, borderRadius: 16, boxShadow: '0 6px 16px rgba(0,0,0,0.12)' }}
            >
              <div
                className="flex shrink-0 items-center justify-center rounded-full text-white"
                style={{ width: 48, height: 48, background: theme.loginBg, fontSize: 18, fontWeight: 700 }}
              >
                M
              </div>
              <div className="min-w-0 flex-1" style={{ marginLeft: 16 }}>
                <p className="truncate" style={{ color: theme.loginBg, fontSize: 16, fontWeight: 700 }}>
                  MARIA DA SILVA
                </p>
                <p style={{ marginTop: 4, color: rgba(theme.loginBg, 0.75), fontSize: 14 }}>***.961.212-**</p>
              </div>
              <span style={{ padding: '0 12px', color: theme.loginBg, fontSize: 14, fontWeight: 700 }}>Trocar</span>
            </div>
          ) : (
            <div>
              <div style={{ border: `2px solid ${text}`, borderRadius: 16, padding: '20px 20px', color: text, fontSize: 18 }}>
                CPF/CNPJ
              </div>
              <div className="flex items-center" style={{ marginTop: 12 }}>
                <span style={{ width: 20, height: 20, margin: 2, border: `2px solid ${text}`, borderRadius: 6 }} />
                <span style={{ marginLeft: 8, color: text, fontSize: 15 }}>Lembrar meu CPF/CNPJ neste dispositivo</span>
              </div>
            </div>
          )}
          <div style={{ height: 38 }} />
          <div
            className="flex items-center justify-center text-white"
            style={{
              height: 58,
              borderRadius: 29,
              background: `linear-gradient(180deg, ${shadeHex(button, 0.14)} 0%, ${button} 42%, ${shadeHex(button, -0.16)} 100%)`,
              border: `1.2px solid ${rgba(shadeHex(button, 0.3), 0.55)}`,
              boxShadow: `0 10px 16px rgba(0,0,0,0.40), 0 5px 10px ${rgba(shadeHex(button, -0.3), 0.55)}`,
            }}
          >
            <LogIn size={22} />
            <span style={{ marginLeft: 10, fontSize: 18, fontWeight: 800, letterSpacing: 0.8 }}>ENTRAR</span>
          </div>
          <div style={{ height: 48 }} />
          <p className="text-center" style={{ color: text, fontSize: 16, padding: '10px 0' }}>Preciso de ajuda?</p>
          <p className="text-center" style={{ color: text, fontSize: 16, padding: '10px 0' }}>Ver planos</p>
        </div>
      </div>
    </PhoneFrame>
  )
}

/** Faixa do topo da Início onde o logo desliza; com onChange, o logo pode ser arrastado. */
function HomeLogoTrack({ position = 0, onChange, children }) {
  const trackRef = useRef(null)
  const itemRef = useRef(null)
  const drag = useRef(null)
  const pct = Math.min(100, Math.max(0, position))

  const onPointerDown = (e) => {
    if (!onChange) return
    const item = itemRef.current.getBoundingClientRect()
    drag.current = { grab: e.clientX - item.left }
    e.currentTarget.setPointerCapture(e.pointerId)
  }
  const onPointerMove = (e) => {
    if (!drag.current) return
    const track = trackRef.current.getBoundingClientRect()
    const item = itemRef.current.getBoundingClientRect()
    const free = track.width - item.width
    if (free <= 0) return
    const next = ((e.clientX - drag.current.grab - track.left) / free) * 100
    onChange(Math.round(Math.min(100, Math.max(0, next))))
  }
  const onPointerUp = () => {
    drag.current = null
  }

  return (
    <div ref={trackRef} className="min-w-0 flex-1">
      <div
        ref={itemRef}
        onPointerDown={onPointerDown}
        onPointerMove={onPointerMove}
        onPointerUp={onPointerUp}
        onPointerCancel={onPointerUp}
        title={onChange ? 'Arraste para posicionar o logo' : undefined}
        className={onChange ? 'cursor-grab rounded-lg outline-1 outline-white/40 outline-dashed active:cursor-grabbing' : ''}
        style={{
          position: 'relative',
          display: 'inline-block',
          left: `${pct}%`,
          transform: `translateX(-${pct}%)`,
          touchAction: 'none',
          userSelect: 'none',
        }}
      >
        {children}
      </div>
    </div>
  )
}

function HomePreview({ theme, logo, shortcuts, logoPosition = 0, onLogoPositionChange }) {
  const primary = theme.primary
  const bg = theme.appBg
  const card = theme.card
  const dark = isDarkColor(card)
  const onBg = onColor(bg)
  const text = dark ? '#FFFFFF' : '#000000'
  const sub = dark ? '#9E9E9E' : '#616161'
  const cardStyle = { background: card, borderRadius: 24, padding: 20 }
  const square = (radius, children) => (
    <div
      className="flex shrink-0 items-center justify-center text-white"
      style={{ width: 54, height: 54, borderRadius: radius, background: primary }}
    >
      {children}
    </div>
  )
  const infoRow = (Icon, label, value, extra) => (
    <div className="flex items-center">
      <Icon size={20} color={primary} />
      <div className="min-w-0 flex-1" style={{ marginLeft: 10 }}>
        <p style={{ color: sub, fontSize: 12, fontWeight: 700 }}>{label}</p>
        {value && (
          <div className="flex items-center" style={{ marginTop: 2 }}>
            {extra}
            <span style={{ color: text, fontSize: 15, fontWeight: 700 }}>{value}</span>
          </div>
        )}
      </div>
      {!value && <ChevronDown size={22} color={sub} />}
    </div>
  )
  const navItem = (Icon, label, selected) => {
    const color = selected ? primary : onColor(card)
    return (
      <div className="flex flex-col items-center" style={{ padding: '8px 12px', color }}>
        <Icon size={26} />
        <span style={{ marginTop: 4, fontSize: 10, fontWeight: selected ? 700 : 400 }}>{label}</span>
      </div>
    )
  }

  return (
    <PhoneFrame background={bg}>
      <div className="flex h-full flex-col" style={{ background: bg }}>
        <PhoneStatusBar color={onBg} />
        <div className="flex items-center" style={{ padding: '8px 16px' }}>
          <HomeLogoTrack position={logoPosition} onChange={onLogoPositionChange}>
            {logo ? (
              <img src={logo} alt="" draggable={false} style={{ height: 72, maxWidth: 220, objectFit: 'contain' }} />
            ) : (
              <div style={{ width: 160 }}>
                <LogoPlaceholder color={onBg} height={60} />
              </div>
            )}
          </HomeLogoTrack>
          <Bell size={28} color={onBg} style={{ margin: 8, flexShrink: 0 }} />
        </div>
        <div className="flex-1 overflow-y-auto" style={{ padding: '0 16px', scrollbarWidth: 'none' }}>
          <div style={{ height: 16 }} />
          <div style={cardStyle}>
            <div className="flex items-center">
              <div
                className="flex shrink-0 items-center justify-center"
                style={{ width: 60, height: 60, borderRadius: 16, background: primary }}
              >
                <User size={36} color="#FFFFFF" fill="#FFFFFF" />
              </div>
              <div className="min-w-0 flex-1" style={{ marginLeft: 16 }}>
                <div className="flex items-center justify-between">
                  <span
                    style={{
                      padding: '2px 8px',
                      borderRadius: 4,
                      background: dark ? 'rgba(255,255,255,0.1)' : '#EEEEEE',
                      fontSize: 10,
                      fontWeight: 700,
                    }}
                  >
                    <span style={{ color: sub }}>Contrato: </span>
                    <span style={{ color: text }}>10234</span>
                  </span>
                  <span
                    style={{
                      padding: '2px 8px',
                      borderRadius: 4,
                      background: 'rgba(76,175,80,0.2)',
                      color: '#4CAF50',
                      fontSize: 10,
                      fontWeight: 700,
                    }}
                  >
                    ATIVO
                  </span>
                </div>
                <p className="truncate" style={{ color: text, fontSize: 18, fontWeight: 700 }}>
                  MARIA DA SILVA
                </p>
              </div>
            </div>
            <div
              style={{
                marginTop: 20,
                padding: '12px 16px',
                borderRadius: 16,
                background: dark ? '#000000' : '#F5F5F5',
                border: `1px solid ${dark ? 'rgba(255,255,255,0.1)' : 'rgba(0,0,0,0.12)'}`,
              }}
            >
              <p className="truncate" style={{ color: text, fontSize: 12, fontWeight: 700 }}>FIBRA 600 MEGA</p>
              <p style={{ marginTop: 4, color: text, fontSize: 12, fontWeight: 700 }}>
                VENC. 10 <span style={{ color: dark ? 'rgba(255,255,255,0.24)' : 'rgba(0,0,0,0.26)' }}>|</span> 15/03/2024
              </p>
              <div style={{ margin: '11px 0', height: 1, background: dark ? 'rgba(255,255,255,0.1)' : 'rgba(0,0,0,0.12)' }} />
              <div className="flex items-center">
                <p className="min-w-0 flex-1 truncate" style={{ color: text, fontSize: 12, fontWeight: 700 }}>
                  RUA DAS FLORES, 123 - CENTRO
                </p>
                <ChevronDown size={22} color={text} />
              </div>
            </div>
          </div>

          <div style={{ height: 16 }} />
          <div style={cardStyle}>
            <div className="flex items-center" style={{ color: '#F57C00', fontWeight: 700, fontSize: 14 }}>
              <CircleCheck size={20} />
              <span style={{ marginLeft: 8 }}>FATURA ABERTA</span>
            </div>
            <p style={{ marginTop: 12, color: text, fontSize: 36, fontWeight: 700, lineHeight: 1.2 }}>R$ 99,90</p>
            <p style={{ color: '#9E9E9E', fontSize: 14 }}>Vencimento 10/11/2026</p>
            <div className="flex items-center" style={{ marginTop: 20, gap: 8 }}>
              <div
                className="flex flex-1 items-center justify-center text-white"
                style={{ background: primary, borderRadius: 16, padding: '12px 0', fontSize: 14, fontWeight: 700 }}
              >
                <PixGlyph />
                <span style={{ marginLeft: 8 }}>Pagar com PIX</span>
              </div>
              {square(12, <Barcode size={24} />)}
              {square(12, <CreditCard size={24} />)}
            </div>
          </div>

          <div style={{ height: 16 }} />
          <div style={cardStyle}>
            <div className="flex items-center">
              <Wifi size={24} color={primary} />
              <span style={{ marginLeft: 8, color: text, fontSize: 14, fontWeight: 700 }}>Informação da sua rede wifi</span>
            </div>
            <p style={{ marginTop: 16, color: text, fontSize: 18, fontWeight: 700 }}>MINHA_REDE_5G</p>
            <div style={{ marginTop: 16 }}>
              {infoRow(
                Router,
                'Status do modem',
                'Online',
                <span className="rounded-full" style={{ width: 8, height: 8, marginRight: 6, background: '#4CAF50' }} />,
              )}
            </div>
            <div style={{ marginTop: 12 }}>{infoRow(Globe, 'IP do modem', '100.64.12.34')}</div>
            <div style={{ marginTop: 12 }}>{infoRow(Clock, 'Modem ligado há', null)}</div>
          </div>

          <div style={{ height: 16 }} />
          <div style={cardStyle}>
            <div className="flex items-center">
              <Headset size={26} color={primary} />
              <span style={{ marginLeft: 12, color: text, fontSize: 18, fontWeight: 700, letterSpacing: 0.5 }}>Suporte</span>
            </div>
            <p style={{ marginTop: 12, color: sub, fontSize: 14, lineHeight: 1.5 }}>Fale com o Atendimento</p>
            <div className="flex items-center" style={{ marginTop: 20, gap: 12 }}>
              <div
                className="flex flex-1 items-center justify-center text-white"
                style={{ background: primary, borderRadius: 16, padding: '16px 0', fontSize: 13, fontWeight: 700 }}
              >
                <MessageCircle size={20} fill="#FFFFFF" />
                <span style={{ marginLeft: 8 }}>Falar com o suporte</span>
              </div>
              {square(16, <WhatsappGlyph />)}
              {square(16, <Phone size={22} fill="#FFFFFF" />)}
            </div>
          </div>

          {shortcuts.length > 0 && (
            <>
              <div style={{ height: 24 }} />
              <p style={{ color: onBg, fontSize: 18, fontWeight: 700 }}>Acesso Rápido</p>
              <div className="grid grid-cols-3" style={{ marginTop: 16, rowGap: 24, columnGap: 16 }}>
                {shortcuts.map(({ label, icon: Icon }) => (
                  <div key={label} className="flex flex-col items-center">
                    <div
                      className="flex items-center justify-center"
                      style={{
                        width: 70,
                        height: 70,
                        borderRadius: 20,
                        background: primary,
                        boxShadow: `0 4px 12px ${rgba(primary, 0.3)}`,
                      }}
                    >
                      <Icon size={32} color="#FFFFFF" />
                    </div>
                    <span
                      className="text-center"
                      style={{ marginTop: 8, color: onBg, fontSize: 12, fontWeight: 700, lineHeight: 1.2 }}
                    >
                      {label}
                    </span>
                  </div>
                ))}
              </div>
            </>
          )}
          <div style={{ height: 140 }} />
        </div>

        <div
          className="absolute flex items-center justify-evenly"
          style={{
            left: 16,
            right: 16,
            bottom: 48,
            height: 62,
            borderRadius: 36,
            background: rgba(card, 0.95),
            border: `1px solid ${dark ? 'rgba(255,255,255,0.1)' : 'rgba(0,0,0,0.05)'}`,
            boxShadow: '0 10px 20px rgba(0,0,0,0.2)',
          }}
        >
          {navItem(Home, 'Início', true)}
          {navItem(ReceiptText, 'Faturas', false)}
          <div style={{ width: 56 }} />
          {navItem(Headset, 'Chamado', false)}
          {navItem(Menu, 'Menu', false)}
        </div>
        <div
          className="absolute flex items-center justify-center rounded-full"
          style={{
            bottom: 62,
            left: PHONE_W / 2 - 32,
            width: 64,
            height: 64,
            background: 'linear-gradient(135deg, #66BB6A, #2E7D32)',
            border: '1px solid rgba(255,255,255,0.15)',
            boxShadow: '0 2px 0 rgba(255,255,255,0.4), 0 -4px 10px -2px rgba(0,0,0,0.2)',
          }}
        >
          <div
            className="flex items-center justify-center rounded-full"
            style={{ width: 42, height: 42, background: 'rgba(0,0,0,0.1)' }}
          >
            <LockOpen size={24} color="#FFFFFF" />
          </div>
        </div>
      </div>
    </PhoneFrame>
  )
}

function SegmentedToggle({ value, options, onChange }) {
  return (
    <div className="inline-flex rounded-lg border border-border bg-background p-0.5">
      {options.map(([key, label]) => (
        <button
          key={key}
          type="button"
          onClick={() => onChange(key)}
          className={`rounded-md px-3 py-1 text-xs font-semibold transition-colors ${
            value === key ? 'bg-primary text-primary-foreground' : 'text-muted-foreground hover:text-foreground'
          }`}
        >
          {label}
        </button>
      ))}
    </div>
  )
}

function AppearancePanel({ onNotify }) {
  const [profile, setProfile] = useState(null)
  const [form, setForm] = useState(null)
  const [files, setFiles] = useState({ logo: null })
  const [removed, setRemoved] = useState({ logo: false })
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')
  const [appConfig, setAppConfig] = useState(null)
  const [previewScreen, setPreviewScreen] = useState('login')
  const [loginVariant, setLoginVariant] = useState('first')

  const fileUrls = useMemo(
    () => ({
      logo: files.logo ? URL.createObjectURL(files.logo) : null,
    }),
    [files],
  )
  useEffect(
    () => () => Object.values(fileUrls).forEach((url) => url && URL.revokeObjectURL(url)),
    [fileUrls],
  )

  const applyProfile = (d) => {
    setProfile(d)
    setForm({
      number: d.number || '',
      primary_color: (d.primary_color || '').toUpperCase() === DEFAULT_PRIMARY ? '' : (d.primary_color || '').toUpperCase(),
      secondary_color: d.secondary_color || '',
      login_bg_color: d.login_bg_color || '',
      login_button_color: d.login_button_color || '',
      login_text_color: d.login_text_color || '',
      app_bg_color: d.app_bg_color || '',
      card_color: d.card_color || '',
      home_logo_position: Number.isFinite(d.home_logo_position) ? d.home_logo_position : 0,
    })
    setFiles({ logo: null })
    setRemoved({ logo: false })
  }

  useEffect(() => {
    let cancelled = false
    ;(async () => {
      setLoading(true)
      setError('')
      try {
        const res = await axios.get('/api/mobile-app/profiles/mine/', { headers: authHeaders() })
        if (!cancelled) applyProfile(res.data || {})
        axios
          .get('/api/mobile-app/profiles/mine-app-config/', { headers: authHeaders() })
          .then((cfg) => !cancelled && setAppConfig(cfg.data || null))
          .catch(() => {})
      } catch (err) {
        if (!cancelled) setError(err?.response?.data?.error || 'Não foi possível carregar a aparência do app.')
      } finally {
        if (!cancelled) setLoading(false)
      }
    })()
    return () => {
      cancelled = true
    }
  }, [])

  const setField = (key, value) => setForm((f) => ({ ...f, [key]: value }))
  const setLogoPosition = (value) => {
    setField('home_logo_position', value)
    setPreviewScreen('home')
  }

  const submit = async (e) => {
    e.preventDefault()
    const invalid = THEME_COLORS.find(([key]) => form[key] && !isHexColor(form[key]))
    if (invalid) {
      setError(`${invalid[1]}: use o formato #RRGGBB ou deixe vazio para usar o padrão do app.`)
      return
    }
    setSaving(true)
    setError('')
    try {
      const data = new FormData()
      data.append('number', form.number.trim())
      THEME_COLORS.forEach(([key]) => {
        const value = form[key] || ''
        data.append(key, key === 'primary_color' && !value ? DEFAULT_PRIMARY : value)
      })
      data.append('home_logo_position', String(form.home_logo_position))
      if (files.logo) data.append('logo', files.logo)
      else if (removed.logo) data.append('remove_logo', 'true')
      if (profile?.login_logo_url) data.append('remove_login_logo', 'true')
      const res = await axios.patch('/api/mobile-app/profiles/mine/', data, { headers: authHeaders() })
      applyProfile(res.data || {})
      onNotify?.('Aparência do aplicativo salva. O app aplica na próxima abertura.')
    } catch (err) {
      const d = err?.response?.data
      const first = d && typeof d === 'object' ? Object.values(d).flat()[0] : null
      setError(d?.error || first || 'Não foi possível salvar a aparência.')
    } finally {
      setSaving(false)
    }
  }

  const factoryTheme = profile?.app_default_theme || {}
  const hasFactoryTheme = isHexColor(factoryTheme.primary_color)
  const theme = previewTheme(form, factoryTheme)
  const THEME_KEY = {
    primary_color: 'primary',
    login_bg_color: 'loginBg',
    login_button_color: 'loginButton',
    login_text_color: 'loginText',
    app_bg_color: 'appBg',
    card_color: 'card',
  }
  const fieldDefault = (key) => {
    if (!hasFactoryTheme) return null
    if (!THEME_KEY[key]) return factoryTheme[key] || null
    return previewTheme({ ...form, [key]: '' }, factoryTheme)[THEME_KEY[key]]
  }
  const appLogo = fileUrls.logo || (removed.logo ? null : profile?.logo_url || null)
  const shortcuts = homeShortcuts(appConfig)

  return (
    <div className="space-y-6 p-6">
      <div>
        <h2 className="mb-1 text-xl font-bold text-foreground">Aparência do App</h2>
        <p className="text-sm text-muted-foreground">
          Contato, logos e cores do aplicativo dos seus clientes. Campos vazios usam o padrão do app.
        </p>
      </div>

      {error && (
        <div className="rounded-xl border border-destructive/30 bg-destructive/10 px-5 py-3 text-sm text-destructive">
          {error}
        </div>
      )}

      {loading && <p className="text-sm text-muted-foreground">Carregando…</p>}

      {!loading && form && (
        <form onSubmit={submit} className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_320px]">
          <div className="space-y-6">
            <div className={`${PANEL_CARD} overflow-hidden p-0`}>
              <div className="border-b border-border px-5 py-3 text-sm font-bold text-foreground">Contato de suporte</div>
              <div className="flex flex-col gap-2 px-5 py-4 sm:flex-row sm:items-center sm:justify-between sm:gap-6">
                <div className="min-w-0">
                  <p className="text-xs font-bold tracking-wide text-muted-foreground uppercase">WhatsApp de suporte</p>
                  <p className="mt-1 text-xs text-muted-foreground">
                    Usado no “Preciso de ajuda?” do login, no suporte e na tela de bloqueio.
                  </p>
                </div>
                <input
                  type="tel"
                  value={form.number}
                  onChange={(e) => setField('number', e.target.value)}
                  placeholder="(00) 00000-0000"
                  maxLength={20}
                  className={`${PANEL_INPUT} sm:max-w-xs`}
                />
              </div>
            </div>

            <div className={`${PANEL_CARD} overflow-hidden p-0`}>
              <div className="border-b border-border px-5 py-3 text-sm font-bold text-foreground">Logos</div>
              <LogoField
                label="Logo do app"
                help="Usado em todo o app: abertura, login, tela inicial e telas internas. PNG com fundo transparente."
                preview={appLogo}
                previewBg="#0A0A0A"
                onPick={(f) => {
                  setFiles((s) => ({ ...s, logo: f }))
                  setRemoved((s) => ({ ...s, logo: false }))
                }}
                onRemove={() => {
                  setFiles((s) => ({ ...s, logo: null }))
                  setRemoved((s) => ({ ...s, logo: true }))
                }}
              />
              <div className="flex flex-col gap-3 px-5 py-4 sm:flex-row sm:items-center sm:justify-between sm:gap-6">
                <div className="min-w-0">
                  <p className="text-xs font-bold tracking-wide text-muted-foreground uppercase">Posição do logo na Início</p>
                  <p className="mt-1 text-xs text-muted-foreground">
                    Escolha um lado ou arraste o logo na prévia ao lado para ajustar.
                  </p>
                </div>
                <div className="flex shrink-0 flex-col items-stretch gap-2 sm:w-64">
                  <SegmentedToggle
                    value={{ 0: 'left', 50: 'center', 100: 'right' }[form.home_logo_position] ?? ''}
                    options={[
                      ['left', 'Esquerda'],
                      ['center', 'Centro'],
                      ['right', 'Direita'],
                    ]}
                    onChange={(v) => setLogoPosition({ left: 0, center: 50, right: 100 }[v])}
                  />
                  <input
                    type="range"
                    min={0}
                    max={100}
                    value={form.home_logo_position}
                    onChange={(e) => setLogoPosition(Number(e.target.value))}
                    className="w-full accent-primary"
                    aria-label="Posição do logo"
                  />
                </div>
              </div>
            </div>

            <div className={`${PANEL_CARD} overflow-hidden p-0`}>
              <div className="border-b border-border px-5 py-3 text-sm font-bold text-foreground">Cores</div>
              {THEME_COLORS.map(([key, label, help]) => (
                <ColorField
                  key={key}
                  label={label}
                  help={help}
                  value={form[key]}
                  defaultValue={fieldDefault(key)}
                  onChange={(v) => setField(key, v)}
                  onReset={() => setField(key, '')}
                />
              ))}
            </div>

            <div className="flex justify-end">
              <button type="submit" disabled={saving} className={`${BTN_PRIMARY} px-8`}>
                <Save className="h-4 w-4" />
                {saving ? 'Salvando…' : 'Salvar aparência'}
              </button>
            </div>
          </div>

          <div className="xl:sticky xl:top-4 xl:self-start">
            <div className="mb-3 flex flex-col items-center gap-2">
              <SegmentedToggle
                value={previewScreen}
                options={[
                  ['login', 'Login'],
                  ['home', 'Início'],
                ]}
                onChange={setPreviewScreen}
              />
              {previewScreen === 'login' && (
                <SegmentedToggle
                  value={loginVariant}
                  options={[
                    ['first', 'Primeiro acesso'],
                    ['saved', 'CPF salvo'],
                  ]}
                  onChange={setLoginVariant}
                />
              )}
            </div>
            {previewScreen === 'login' ? (
              <LoginPreview theme={theme} logo={appLogo} savedUser={loginVariant === 'saved'} />
            ) : (
              <HomePreview
                theme={theme}
                logo={appLogo}
                shortcuts={shortcuts}
                logoPosition={form.home_logo_position}
                onLogoPositionChange={setLogoPosition}
              />
            )}
            {!hasFactoryTheme && (
              <p className="mx-auto mt-3 max-w-[282px] rounded-lg border border-amber-500/30 bg-amber-500/10 px-3 py-2 text-center text-[11px] text-amber-600 dark:text-amber-400">
                O app deste provedor ainda não informou as cores de fábrica. Campos vazios aparecem com cor genérica
                até o app (versão atualizada) ser aberto uma vez.
              </p>
            )}
            <p className="mx-auto mt-3 max-w-[282px] text-center text-[11px] text-muted-foreground">
              Dados de cliente fictícios. Sem logo enviado, o app usa o logo que já vem na versão publicada.
            </p>
          </div>
        </form>
      )}
    </div>
  )
}

function CompanyPanel({ onNotify, onError }) {
  const [form, setForm] = useState({
    razao_social: '',
    nome_fantasia: '',
    cnpj: '',
    vencimento_fatura: '',
    celular: '',
    email: '',
    termos: '',
    privacidade: '',
  })
  const [tab, setTab] = useState('empresa')
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')
  const [editingLegal, setEditingLegal] = useState(null)
  const [legalDraft, setLegalDraft] = useState('')

  useEffect(() => {
    let cancelled = false
    ;(async () => {
      setLoading(true)
      setError('')
      try {
        const res = await axios.get('/api/mobile-app/panel/company/', { headers: authHeaders() })
        if (cancelled) return
        const d = res.data || {}
        setForm({
          razao_social: d.razao_social || '',
          nome_fantasia: d.nome_fantasia || '',
          cnpj: d.cnpj || '',
          vencimento_fatura: (d.vencimento_fatura || '').slice(0, 10),
          celular: d.celular || '',
          email: d.email || d.email_contato || '',
          termos: d.termos || d.terms_text || '',
          privacidade: d.privacidade || d.privacy_text || '',
        })
      } catch (err) {
        if (!cancelled) setError(err?.response?.data?.error || 'Não foi possível carregar os dados.')
      } finally {
        if (!cancelled) setLoading(false)
      }
    })()
    return () => {
      cancelled = true
    }
  }, [])

  const setField = (key, value) => setForm((f) => ({ ...f, [key]: value }))

  const applyCompany = (d) => {
    setForm({
      razao_social: d.razao_social || '',
      nome_fantasia: d.nome_fantasia || '',
      cnpj: d.cnpj || '',
      vencimento_fatura: (d.vencimento_fatura || '').slice(0, 10),
      celular: d.celular || '',
      email: d.email || d.email_contato || '',
      termos: d.termos || d.terms_text || '',
      privacidade: d.privacidade || d.privacy_text || '',
    })
  }

  const submit = async (e) => {
    e.preventDefault()
    setSaving(true)
    setError('')
    try {
      const res = await axios.patch(
        '/api/mobile-app/panel/company/',
        {
          razao_social: form.razao_social,
          nome_fantasia: form.nome_fantasia,
          cnpj: form.cnpj,
          celular: form.celular,
          email: form.email,
        },
        { headers: authHeaders() },
      )
      applyCompany(res.data || {})
      onNotify?.(res.data?.message || 'Dados da empresa atualizados com sucesso!')
    } catch (err) {
      const msg = err?.response?.data?.error || 'Falha ao salvar os dados.'
      setError(msg)
      onError?.(msg)
    } finally {
      setSaving(false)
    }
  }

  const openLegal = (key) => {
    setEditingLegal(key)
    setLegalDraft(key === 'privacidade' ? form.privacidade : form.termos)
    setError('')
  }

  const saveLegal = async (e) => {
    e.preventDefault()
    if (!editingLegal) return
    setSaving(true)
    setError('')
    try {
      const payload = editingLegal === 'privacidade'
        ? { privacidade: legalDraft }
        : { termos: legalDraft }
      const res = await axios.patch('/api/mobile-app/panel/company/', payload, {
        headers: authHeaders(),
      })
      applyCompany(res.data || {})
      setEditingLegal(null)
      onNotify?.(
        editingLegal === 'privacidade'
          ? 'Política de privacidade atualizada!'
          : 'Termos de uso atualizados!',
      )
    } catch (err) {
      const msg = err?.response?.data?.error || 'Falha ao salvar os termos.'
      setError(msg)
      onError?.(msg)
    } finally {
      setSaving(false)
    }
  }

  const previewLegal = (text) => {
    const value = String(text || '').replace(/\s+/g, ' ').trim()
    if (!value) return '—'
    return value.length > 72 ? `${value.slice(0, 72)}...` : value
  }

  const legalRows = [
    {
      key: 'privacidade',
      label: 'Termos de privacidade',
      icon: Paperclip,
      tone: 'text-orange-400',
      value: form.privacidade,
    },
    {
      key: 'termos',
      label: 'Termos de uso',
      icon: FileText,
      tone: 'text-emerald-400',
      value: form.termos,
    },
  ]

  const fields = [
    ['razao_social', 'Razão Social', 'text', 'Nome jurídico da empresa', false],
    ['nome_fantasia', 'Nome Fantasia', 'text', 'Nome comercial', false],
    ['cnpj', 'CNPJ', 'text', '00.000.000/0000-00', false],
    ['email', 'E-mail', 'email', 'contato@empresa.com', false],
    ['celular', 'Número de celular', 'tel', '(00) 00000-0000', false],
    ['vencimento_fatura', 'Vencimento fatura', 'date', '', true],
  ]

  const formatVencimento = (value) => {
    if (!value) return '—'
    try {
      return new Date(`${value.slice(0, 10)}T12:00:00`).toLocaleDateString('pt-BR')
    } catch {
      return value
    }
  }

  return (
    <div className="space-y-6 p-6">
      <div>
        <h2 className="mb-1 text-xl font-bold text-foreground">Minha Empresa</h2>
        <p className="text-sm text-muted-foreground">
          {tab === 'termos'
            ? 'Termos de uso e política de privacidade exibidos no aplicativo.'
            : 'Dados cadastrais da sua empresa no Niohub.'}
        </p>
        <div className="mt-4 flex w-full max-w-xl gap-1.5 rounded-xl border border-border bg-muted/40 p-1.5">
          <button
            type="button"
            onClick={() => setTab('empresa')}
            className={`flex flex-1 items-center justify-center rounded-lg px-3 py-2.5 text-sm font-bold transition-all ${
              tab === 'empresa'
                ? 'bg-orange-500 text-white shadow'
                : 'text-muted-foreground hover:bg-muted hover:text-foreground'
            }`}
          >
            Dados da empresa
          </button>
          <button
            type="button"
            onClick={() => setTab('termos')}
            className={`flex flex-1 items-center justify-center rounded-lg px-3 py-2.5 text-sm font-bold transition-all ${
              tab === 'termos'
                ? 'bg-orange-500 text-white shadow'
                : 'text-muted-foreground hover:bg-muted hover:text-foreground'
            }`}
          >
            Termos de Uso
          </button>
        </div>
      </div>

      {error && (
        <div className="rounded-xl border border-destructive/30 bg-destructive/10 px-5 py-3 text-sm text-destructive">
          {error}
        </div>
      )}

      {loading && <p className="text-sm text-muted-foreground">Carregando…</p>}

      {!loading && tab === 'empresa' && (
        <form onSubmit={submit} className={`${PANEL_CARD} mx-auto w-full max-w-2xl space-y-0 overflow-hidden p-0`}>
          {fields.map(([key, label, type, placeholder, readOnly], idx) => (
            <div
              key={key}
              className={`flex flex-col gap-2 px-5 py-4 sm:flex-row sm:items-center sm:justify-between sm:gap-6 ${
                idx < fields.length - 1 ? 'border-b border-border' : ''
              }`}
            >
              <label
                htmlFor={readOnly ? undefined : `company-${key}`}
                className="shrink-0 text-xs font-bold tracking-wide text-muted-foreground uppercase"
              >
                {label}
              </label>
              {readOnly ? (
                <span className="text-sm font-medium text-foreground sm:text-right">
                  {formatVencimento(form[key])}
                </span>
              ) : (
                <input
                  id={`company-${key}`}
                  type={type}
                  value={form[key]}
                  onChange={(e) => setField(key, e.target.value)}
                  placeholder={placeholder}
                  required={key === 'nome_fantasia'}
                  className={`${PANEL_INPUT} sm:max-w-sm sm:text-right`}
                />
              )}
            </div>
          ))}
          <div className="flex justify-end border-t border-border bg-muted/30 px-5 py-4">
            <button type="submit" disabled={saving} className={`${BTN_PRIMARY} px-8`}>
              {saving ? 'Salvando…' : 'Salvar alterações'}
            </button>
          </div>
        </form>
      )}

      {!loading && tab === 'termos' && (
        <div>
          <h3 className="mb-4 text-lg font-bold text-foreground">Termos de Uso e Privacidade</h3>
          <div className={`${PANEL_CARD} overflow-hidden p-0`}>
            <div className="overflow-x-auto">
              <table className="w-full text-left text-sm">
                <thead className="border-b border-border bg-muted/40 text-xs font-bold text-muted-foreground uppercase">
                  <tr>
                    <th className="px-5 py-3">Termo de uso</th>
                    <th className="px-5 py-3">Tipo</th>
                    <th className="px-5 py-3">Descrição</th>
                    <th className="px-5 py-3 text-right"> </th>
                  </tr>
                </thead>
                <tbody>
                  {legalRows.map((row) => {
                    const Icon = row.icon
                    return (
                      <tr key={row.key} className="border-b border-border/60 last:border-0">
                        <td className="px-5 py-4">
                          <span className={`inline-flex items-center gap-2 font-semibold ${row.tone}`}>
                            <Icon className="h-4 w-4 shrink-0" />
                            {row.label}
                          </span>
                        </td>
                        <td className="px-5 py-4">
                          <span className="inline-flex items-center gap-2 font-medium text-emerald-400">
                            <FileText className="h-4 w-4 shrink-0" />
                            Conteúdo
                          </span>
                        </td>
                        <td className="max-w-md truncate px-5 py-4 text-muted-foreground">
                          {previewLegal(row.value)}
                        </td>
                        <td className="px-5 py-4 text-right">
                          <button
                            type="button"
                            onClick={() => openLegal(row.key)}
                            className="inline-flex items-center gap-1.5 text-sm font-semibold text-orange-400 hover:text-orange-300"
                          >
                            <Pencil className="h-4 w-4" />
                            Editar
                          </button>
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      )}

      {editingLegal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center overflow-y-auto bg-black/70 p-4">
          <form onSubmit={saveLegal} className="w-full max-w-3xl overflow-hidden rounded-2xl border border-border bg-card shadow-xl">
            <div className="flex items-center justify-between border-b border-border px-6 py-4">
              <h3 className="text-lg font-bold text-foreground">
                Editar {editingLegal === 'privacidade' ? 'termos de privacidade' : 'termos de uso'}
              </h3>
              <button
                type="button"
                onClick={() => setEditingLegal(null)}
                className="rounded-lg p-1 text-muted-foreground hover:bg-muted hover:text-foreground"
              >
                <X className="h-5 w-5" />
              </button>
            </div>
            <div className="space-y-2 p-6">
              <label htmlFor="legal-draft" className="block text-xs font-bold tracking-wide text-muted-foreground uppercase">
                Conteúdo
              </label>
              <textarea
                id="legal-draft"
                value={legalDraft}
                onChange={(e) => setLegalDraft(e.target.value)}
                rows={16}
                placeholder="Cole aqui o texto que será exibido no aplicativo..."
                className={`${PANEL_INPUT} min-h-[320px] resize-y`}
              />
            </div>
            <div className="flex justify-end gap-3 border-t border-border bg-muted/30 px-6 py-4">
              <button
                type="button"
                onClick={() => setEditingLegal(null)}
                className="px-4 py-2 text-xs font-bold text-muted-foreground uppercase hover:text-foreground"
              >
                Cancelar
              </button>
              <button type="submit" disabled={saving} className={`${BTN_PRIMARY} px-6 text-xs uppercase`}>
                {saving ? 'Salvando…' : 'Salvar'}
              </button>
            </div>
          </form>
        </div>
      )}
    </div>
  )
}

function statusBadgeClass(status) {
  if (status === 'enviado' || status === 'Enviado') return 'bg-emerald-500/15 text-emerald-500'
  if (status === 'parcial' || status === 'Parcial') return 'bg-orange-500/15 text-orange-400'
  if (status === 'falha' || status === 'Falha') return 'bg-destructive/15 text-destructive'
  return 'bg-muted text-muted-foreground'
}

function SentNotificationsPanel() {
  const [logs, setLogs] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [detail, setDetail] = useState(null)

  const load = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const res = await axios.get('/api/mobile-app/notification-logs/', {
        headers: authHeaders(),
        params: { page_size: 100 },
      })
      setLogs(res.data.results || res.data || [])
    } catch (err) {
      setError(err?.response?.data?.detail || 'Não foi possível carregar as notificações enviadas.')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    load()
  }, [load])

  // Flatten: one row per recipient (or one row for the campaign if no recipients detail)
  const rows = []
  for (const log of logs) {
    const recipients = Array.isArray(log.recipients) ? log.recipients : []
    if (recipients.length > 0) {
      for (let i = 0; i < recipients.length; i += 1) {
        const r = recipients[i]
        rows.push({
          key: `${log.id}-${i}`,
          log,
          clientName: r.name || r.login || r.cpf || 'Cliente',
          clientStatus: r.status === 'enviado' ? 'Enviado' : r.status === 'falha' ? 'Falha' : (r.status || log.status_label),
          recipient: r,
        })
      }
    } else {
      rows.push({
        key: `log-${log.id}`,
        log,
        clientName:
          log.recipients_count > 1
            ? `${log.recipients_count} destinatários`
            : 'Destinatário não identificado',
        clientStatus: log.status_label || 'Enviado',
        recipient: null,
      })
    }
  }

  return (
    <div className="space-y-4 p-6">
      <div className="flex flex-col gap-1 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <h2 className="text-xl font-bold text-foreground">Notificações enviadas</h2>
          <p className="text-sm text-muted-foreground">
            Histórico das mensagens push enviadas aos clientes.
          </p>
        </div>
        <button type="button" onClick={load} className={BTN_GHOST}>
          Atualizar
        </button>
      </div>

      {error && (
        <div className="rounded-lg border border-destructive/30 bg-destructive/10 p-3 text-sm text-destructive">
          {error}
        </div>
      )}

      <div className="overflow-hidden rounded-xl border border-border bg-card">
        <div className="overflow-x-auto">
          <table className="w-full min-w-[720px] text-left text-sm">
            <thead className="border-b border-border bg-muted/40 text-xs uppercase tracking-wide text-muted-foreground">
              <tr>
                <th className="px-4 py-3 font-medium">Hora</th>
                <th className="px-4 py-3 font-medium">Cliente</th>
                <th className="px-4 py-3 font-medium">Título</th>
                <th className="px-4 py-3 font-medium">Status</th>
                <th className="px-4 py-3 font-medium text-right">Ações</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {loading && (
                <tr>
                  <td colSpan={5} className="px-4 py-10 text-center text-muted-foreground">
                    Carregando…
                  </td>
                </tr>
              )}
              {!loading && rows.length === 0 && (
                <tr>
                  <td colSpan={5} className="px-4 py-10 text-center text-muted-foreground">
                    Nenhuma notificação enviada ainda.
                  </td>
                </tr>
              )}
              {!loading &&
                rows.map((row) => (
                  <tr key={row.key} className="hover:bg-muted/30">
                    <td className="whitespace-nowrap px-4 py-3 font-mono text-xs text-muted-foreground">
                      {formatDateTime(row.log.created_at)}
                    </td>
                    <td className="px-4 py-3">
                      <div className="font-medium text-foreground">{row.clientName}</div>
                      {row.recipient?.cpf ? (
                        <div className="font-mono text-[11px] text-muted-foreground">
                          CPF: {row.recipient.cpf}
                        </div>
                      ) : null}
                    </td>
                    <td className="max-w-[220px] truncate px-4 py-3 text-foreground">
                      {row.log.title}
                    </td>
                    <td className="px-4 py-3">
                      <span
                        className={`inline-flex rounded-full px-2.5 py-0.5 text-[11px] font-bold uppercase ${statusBadgeClass(row.clientStatus)}`}
                      >
                        {row.clientStatus}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-right">
                      <button
                        type="button"
                        onClick={() => setDetail(row)}
                        className={`${BTN_GHOST} text-xs`}
                      >
                        <Eye className="h-3.5 w-3.5" />
                        Visualizar
                      </button>
                    </td>
                  </tr>
                ))}
            </tbody>
          </table>
        </div>
      </div>

      {detail && (
        <div className="fixed inset-0 z-50 flex items-end justify-center bg-black/60 p-4 sm:items-center">
          <div className="max-h-[90vh] w-full max-w-lg overflow-y-auto rounded-2xl border border-border bg-card shadow-xl">
            <div className="flex items-center justify-between border-b border-border p-5">
              <h3 className="text-lg font-bold text-foreground">Detalhe da notificação</h3>
              <button
                type="button"
                onClick={() => setDetail(null)}
                className="rounded-lg p-1 text-muted-foreground hover:bg-muted hover:text-foreground"
              >
                <X className="h-5 w-5" />
              </button>
            </div>
            <div className="space-y-4 p-5">
              <div className="flex flex-wrap items-center gap-2">
                <span
                  className={`rounded-full px-2.5 py-0.5 text-[11px] font-bold uppercase ${statusBadgeClass(detail.clientStatus)}`}
                >
                  {detail.clientStatus}
                </span>
                <span className="text-xs text-muted-foreground">
                  {formatDateTime(detail.log.created_at)}
                </span>
              </div>

              <div>
                <p className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
                  Cliente
                </p>
                <p className="text-base font-bold text-foreground">{detail.clientName}</p>
                {detail.recipient?.cpf && (
                  <p className="font-mono text-xs text-muted-foreground">CPF: {detail.recipient.cpf}</p>
                )}
                {detail.recipient?.login && (
                  <p className="font-mono text-xs text-indigo-400">Login: {detail.recipient.login}</p>
                )}
                {detail.recipient?.customer_id && (
                  <p className="font-mono text-xs text-muted-foreground">
                    Cliente ID: #{detail.recipient.customer_id}
                  </p>
                )}
              </div>

              <div>
                <p className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
                  Título
                </p>
                <p className="font-semibold text-foreground">{detail.log.title}</p>
              </div>

              <div>
                <p className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
                  Conteúdo da mensagem
                </p>
                <p className="mt-1 whitespace-pre-wrap rounded-lg border border-border bg-muted/30 p-3 text-sm text-foreground">
                  {detail.log.body}
                </p>
              </div>

              <div className="grid grid-cols-2 gap-3 text-sm">
                <div>
                  <p className="text-[11px] font-semibold uppercase text-muted-foreground">Tipo</p>
                  <p className="text-foreground">{detail.log.notif_type || 'info'}</p>
                </div>
                <div>
                  <p className="text-[11px] font-semibold uppercase text-muted-foreground">Origem</p>
                  <p className="text-foreground">{detail.log.source || '—'}</p>
                </div>
                <div>
                  <p className="text-[11px] font-semibold uppercase text-muted-foreground">Segmento</p>
                  <p className="text-foreground">{detail.log.segment_type || 'all'}</p>
                </div>
                <div>
                  <p className="text-[11px] font-semibold uppercase text-muted-foreground">Envio geral</p>
                  <p className="text-foreground">
                    {detail.log.success_count ?? 0} ok · {detail.log.failure_count ?? 0} falhas
                  </p>
                </div>
              </div>

              {detail.recipient?.platform || detail.recipient?.model ? (
                <div>
                  <p className="text-[11px] font-semibold uppercase text-muted-foreground">Dispositivo</p>
                  <p className="text-sm text-foreground">
                    {[detail.recipient.platform, detail.recipient.model].filter(Boolean).join(' · ') || '—'}
                  </p>
                </div>
              ) : null}

              {detail.log.link ? (
                <div>
                  <p className="text-[11px] font-semibold uppercase text-muted-foreground">Link</p>
                  <a
                    href={detail.log.link}
                    target="_blank"
                    rel="noreferrer"
                    className="break-all text-sm text-primary hover:underline"
                  >
                    {detail.log.link}
                  </a>
                </div>
              ) : null}

              {detail.log.image_url ? (
                <div>
                  <p className="mb-2 text-[11px] font-semibold uppercase text-muted-foreground">Imagem</p>
                  <img
                    src={detail.log.image_url}
                    alt=""
                    className="max-h-40 rounded-lg border border-border object-cover"
                  />
                </div>
              ) : null}

              <button type="button" onClick={() => setDetail(null)} className={`${BTN_PRIMARY} w-full`}>
                Fechar
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

function StatCard({ title, value, sub }) {
  return (
    <div className={PANEL_CARD}>
      <p className="mb-2 text-xs font-medium uppercase tracking-wider text-muted-foreground">{title}</p>
      <p className="text-3xl font-bold text-foreground">{value}</p>
      {sub ? <p className="mt-1 text-sm text-muted-foreground">{sub}</p> : null}
    </div>
  )
}

function DonutCard({ title, badge, centerValue, centerLabel, data, colors, footer }) {
  const hasData = data.some((d) => Number(d.value) > 0)
  return (
    <div className={PANEL_CARD}>
      <div className="mb-4 flex items-center justify-between gap-2">
        <h3 className="text-base font-bold text-foreground">{title}</h3>
        {badge ? <span className="text-xs text-muted-foreground">{badge}</span> : null}
      </div>
      <div className="relative mx-auto h-48 w-full max-w-[220px]">
        <ResponsiveContainer width="100%" height="100%">
          <PieChart>
            <Pie
              data={hasData ? data : [{ name: 'vazio', value: 1 }]}
              dataKey="value"
              innerRadius="72%"
              outerRadius="92%"
              strokeWidth={0}
              startAngle={90}
              endAngle={-270}
            >
              {(hasData ? data : [{ name: 'vazio', value: 1 }]).map((entry, i) => (
                <Cell key={entry.name} fill={hasData ? colors[i % colors.length] : CHART_MUTED} />
              ))}
            </Pie>
          </PieChart>
        </ResponsiveContainer>
        <div className="pointer-events-none absolute inset-0 flex flex-col items-center justify-center">
          <span className="text-2xl font-bold text-foreground">{centerValue}</span>
          <span className="text-xs text-muted-foreground">{centerLabel}</span>
        </div>
      </div>
      {footer}
    </div>
  )
}

function AppDashboard({ stats }) {
  const usersPie = [
    { name: 'Ativos', value: stats.active_users || 0 },
    { name: 'Inativos', value: stats.inactive_users || 0 },
  ]
  const devicesPie = [
    { name: 'Android', value: stats.android_devices || 0 },
    { name: 'iOS', value: stats.ios_devices || 0 },
  ]
  const chart7d = (stats.chart_labels_7d || []).map((label, i) => ({
    label,
    sent: stats.chart_data_sent?.[i] || 0,
    failed: stats.chart_data_failed?.[i] || 0,
    installs: stats.chart_data_installs?.[i] || 0,
    newUsers: stats.chart_data_new_users?.[i] || 0,
  }))
  const weekFailed = (stats.chart_data_failed || []).reduce((a, b) => a + b, 0)
  const delivery = stats.delivery_rate || 0
  const growth = stats.installs_growth
  const growthLabel =
    growth == null
      ? '—'
      : `${growth > 0 ? '+' : ''}${growth}% vs semana ant.`
  const tel = stats.telemetry_7d || {}

  return (
    <div className="space-y-6 p-6">
      <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-4">
        <StatCard
          title="Downloads (7 dias)"
          value={stats.installs_7d ?? 0}
          sub={`${growthLabel} · ${stats.installs_30d ?? 0} no mês`}
        />
        <StatCard
          title="Novos clientes"
          value={stats.new_users_7d ?? 0}
          sub={`${stats.new_users_30d ?? 0} nos últimos 30 dias`}
        />
        <div className={PANEL_CARD}>
          <p className="mb-1 text-xs font-medium uppercase tracking-wider text-muted-foreground">
            Online agora
          </p>
          <p className="text-3xl font-bold text-foreground">{stats.online_users ?? 0}</p>
          <p className="mt-1 text-xs text-muted-foreground">
            Últimos 5 min · de {stats.total_users || 0} clientes
          </p>
          <div className="mt-3 max-h-24 space-y-1.5 overflow-y-auto">
            {(stats.online_now || []).length === 0 ? (
              <p className="text-xs text-muted-foreground">Ninguém online no momento</p>
            ) : (
              (stats.online_now || []).map((u) => (
                <div key={u.id} className="flex items-center justify-between gap-2 text-xs">
                  <span className="truncate font-medium text-foreground" title={u.name || u.login}>
                    {u.login}
                  </span>
                  <span className="h-1.5 w-1.5 shrink-0 rounded-full bg-emerald-500" title="Online" />
                </div>
              ))
            )}
          </div>
        </div>
        <StatCard
          title="Taxa de entrega"
          value={`${delivery}%`}
          sub={`Push · falhas: ${stats.failure_count ?? 0}`}
        />
      </div>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        <DonutCard
          title="Usuários ativos"
          badge={`${stats.active_percentage || 0}% ativos`}
          centerValue={`${stats.active_percentage || 0}%`}
          centerLabel="ativos"
          data={usersPie}
          colors={[CHART_BLUE, CHART_MUTED]}
          footer={(
            <div className="mt-4 flex justify-center gap-10">
              <div className="text-center">
                <span className="block text-sm font-bold text-foreground">{stats.active_users}</span>
                <span className="text-xs text-muted-foreground">Ativos</span>
              </div>
              <div className="text-center">
                <span className="block text-sm font-bold text-foreground">{stats.inactive_users}</span>
                <span className="text-xs text-muted-foreground">Inativos</span>
              </div>
            </div>
          )}
        />

        <div className={`lg:col-span-2 ${PANEL_CARD}`}>
          <h3 className="mb-2 text-base font-bold text-foreground">Downloads e cadastros (7 dias)</h3>
          <p className="mb-4 text-xs text-muted-foreground">
            Downloads = novos dispositivos registrados no app (proxy de instalação).
          </p>
          <div className="h-48">
            <ResponsiveContainer width="100%" height="100%">
              <ComposedChart data={chart7d} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#3f3f46" vertical={false} />
                <XAxis dataKey="label" tick={{ fill: '#a8a29e', fontSize: 10 }} axisLine={false} tickLine={false} />
                <YAxis hide allowDecimals={false} />
                <Tooltip
                  cursor={false}
                  contentStyle={{
                    background: '#27272a',
                    border: '1px solid #3f3f46',
                    borderRadius: 8,
                    color: '#fafaf9',
                  }}
                />
                <Bar
                  dataKey="installs"
                  name="Downloads"
                  fill={CHART_BLUE}
                  radius={[4, 4, 0, 0]}
                  barSize={18}
                  opacity={0.85}
                />
                <Line
                  type="monotone"
                  dataKey="newUsers"
                  name="Novos clientes"
                  stroke={CHART_ORANGE}
                  strokeWidth={2.5}
                  dot={{ r: 4, fill: CHART_ORANGE, strokeWidth: 0 }}
                  activeDot={{ r: 6 }}
                />
              </ComposedChart>
            </ResponsiveContainer>
          </div>
          <div className="mt-4 flex flex-wrap items-center gap-3">
            <span className="inline-flex items-center gap-2 rounded-full bg-muted px-3 py-1 text-xs text-muted-foreground">
              <span className="h-2.5 w-2.5 rounded-sm" style={{ background: CHART_BLUE }} />
              Downloads
            </span>
            <span className="inline-flex items-center gap-2 rounded-full bg-muted px-3 py-1 text-xs text-muted-foreground">
              <span className="h-0.5 w-3 rounded-full" style={{ background: CHART_ORANGE }} />
              <span className="h-2 w-2 rounded-full" style={{ background: CHART_ORANGE }} />
              Novos clientes
            </span>
          </div>
        </div>
      </div>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        <DonutCard
          title="Dispositivos ativos"
          badge={`${stats.total_devices || 0} total`}
          centerValue={stats.total_devices || 0}
          centerLabel="devices"
          data={devicesPie}
          colors={[CHART_BLUE, CHART_CYAN]}
          footer={(
            <div className="mt-4 space-y-2">
              <div className="flex items-center gap-2 text-sm">
                <span className="h-3 w-3 rounded-full" style={{ background: CHART_BLUE }} />
                <span className="text-foreground">Android</span>
                <span className="ml-auto text-muted-foreground">
                  {stats.android_devices || 0} · {stats.android_percentage || 0}%
                </span>
              </div>
              <div className="flex items-center gap-2 text-sm">
                <span className="h-3 w-3 rounded-full" style={{ background: CHART_CYAN }} />
                <span className="text-foreground">iOS</span>
                <span className="ml-auto text-muted-foreground">
                  {stats.ios_devices || 0} · {stats.ios_percentage || 0}%
                </span>
              </div>
            </div>
          )}
        />

        <div className={PANEL_CARD}>
          <h3 className="mb-6 text-base font-bold text-foreground">Status das notificações</h3>
          <div className="mb-4">
            <div className="mb-2 flex justify-between">
              <span className="text-sm text-foreground">Enviadas</span>
              <span className="text-sm text-muted-foreground">
                {stats.success_count || 0} · {delivery}%
              </span>
            </div>
            <div className="h-2.5 w-full rounded-full bg-muted">
              <div
                className="h-2.5 rounded-full bg-primary transition-all"
                style={{ width: `${Math.min(100, Math.max(0, delivery))}%` }}
              />
            </div>
          </div>
          <div className="mt-6">
            <div className="mb-2 flex justify-between">
              <span className="text-sm text-foreground">Falhas</span>
              <span className="text-sm text-muted-foreground">{stats.failure_count || 0}</span>
            </div>
            <div className="h-2.5 w-full rounded-full bg-muted">
              <div
                className="h-2.5 rounded-full bg-destructive/80 transition-all"
                style={{
                  width: `${
                    (stats.success_count || 0) + (stats.failure_count || 0) > 0
                      ? Math.min(
                          100,
                          Math.round(
                            ((stats.failure_count || 0) /
                              ((stats.success_count || 0) + (stats.failure_count || 0))) *
                              100,
                          ),
                        )
                      : 0
                  }%`,
                }}
              />
            </div>
          </div>
          <p className="mt-6 text-xs text-muted-foreground">
            Confirmadas: {stats.push_confirmed ?? 0} · Falhas (7 dias): {weekFailed}
          </p>
        </div>

        <div className={PANEL_CARD}>
          <h3 className="mb-6 text-base font-bold text-foreground">Modelos mais usados</h3>
          <div className="space-y-4">
            {(stats.top_models || []).length === 0 && (
              <p className="text-sm text-muted-foreground">Nenhum dado disponível</p>
            )}
            {(stats.top_models || []).map((m) => (
              <div key={m.model} className="flex items-center justify-between gap-3">
                <span className="truncate text-sm text-foreground">{m.model || 'Desconhecido'}</span>
                <span className="shrink-0 text-sm text-muted-foreground">{m.count}</span>
              </div>
            ))}
          </div>
        </div>
      </div>

      <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
        <div className={PANEL_CARD}>
          <h3 className="mb-2 text-base font-bold text-foreground">Cobertura de push</h3>
          <p className="mb-3 text-xs text-muted-foreground">Devices com token FCM</p>
          <p className="text-4xl font-bold text-primary">{stats.push_coverage || 0}%</p>
          <p className="mt-1 text-sm text-muted-foreground">
            {stats.devices_with_token || 0}/{stats.total_devices || 0}
          </p>
          <div className="mt-3 h-2.5 w-full rounded-full bg-muted">
            <div
              className="h-2.5 rounded-full bg-primary"
              style={{ width: `${Math.min(100, stats.push_coverage || 0)}%` }}
            />
          </div>
        </div>

        <div className={PANEL_CARD}>
          <h3 className="mb-2 text-base font-bold text-foreground">Aplicativos desatualizados</h3>
          <p className="mb-3 text-xs text-muted-foreground">
            Devices abaixo da versão {stats.latest_app_version || '—'}
          </p>
          <p className="text-4xl font-bold text-primary">{stats.outdated_apps ?? 0}</p>
          <p className="mt-1 text-sm text-muted-foreground">
            {stats.outdated_percentage ?? 0}% dos devices ativos
          </p>
          <div className="mt-3 h-2.5 w-full rounded-full bg-muted">
            <div
              className="h-2.5 rounded-full bg-orange-500/90"
              style={{ width: `${Math.min(100, stats.outdated_percentage || 0)}%` }}
            />
          </div>
        </div>
      </div>

      <div className={PANEL_CARD}>
        <div className="mb-4 flex items-end justify-between gap-3">
          <h3 className="text-base font-bold text-foreground">Logs recentes</h3>
          <p className="text-[11px] text-muted-foreground">Últimas 4 horas</p>
        </div>
        {(stats.recent_activity_logs || []).length === 0 ? (
          <p className="py-4 text-center text-sm text-muted-foreground">
            Nenhum log de atividade nas últimas 4 horas
          </p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[520px] text-left text-sm">
              <thead>
                <tr className="border-b border-border text-xs uppercase tracking-wider text-muted-foreground">
                  <th className="pb-3 pr-4 font-medium">Data</th>
                  <th className="pb-3 pr-4 font-medium">Usuário</th>
                  <th className="pb-3 pr-4 font-medium">Evento</th>
                  <th className="pb-3 font-medium">IP</th>
                </tr>
              </thead>
              <tbody>
                {stats.recent_activity_logs.map((row) => (
                  <tr key={row.id} className="border-b border-border/60 last:border-0">
                    <td className="py-3 pr-4 whitespace-nowrap text-muted-foreground">{row.date}</td>
                    <td className="py-3 pr-4 font-medium text-foreground">{row.user}</td>
                    <td className="py-3 pr-4 text-foreground">{row.event}</td>
                    <td className="py-3 font-mono text-xs text-muted-foreground">{row.ip}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <div className={PANEL_CARD}>
          <h3 className="mb-2 text-base font-bold text-foreground">Qualidade de rede (7 dias)</h3>
          <p className="mb-4 text-xs text-muted-foreground">
            Média da telemetria enviada pelo app (Wi‑Fi / latência).
          </p>
          {(tel.samples || 0) === 0 ? (
            <p className="text-sm text-muted-foreground">Ainda sem amostras de telemetria.</p>
          ) : (
            <div className="grid grid-cols-2 gap-4">
              <div>
                <p className="text-xs text-muted-foreground">Latência média</p>
                <p className="text-2xl font-bold text-foreground">
                  {tel.avg_latency_ms != null ? `${tel.avg_latency_ms} ms` : '—'}
                </p>
              </div>
              <div>
                <p className="text-xs text-muted-foreground">Sinal Wi‑Fi</p>
                <p className="text-2xl font-bold text-foreground">
                  {tel.avg_wifi_dbm != null ? `${tel.avg_wifi_dbm} dBm` : '—'}
                </p>
              </div>
              <div>
                <p className="text-xs text-muted-foreground">Link speed</p>
                <p className="text-2xl font-bold text-foreground">
                  {tel.avg_link_speed_mbps != null ? `${tel.avg_link_speed_mbps} Mbps` : '—'}
                </p>
              </div>
              <div>
                <p className="text-xs text-muted-foreground">Packet loss</p>
                <p className="text-2xl font-bold text-foreground">
                  {tel.avg_packet_loss != null ? `${tel.avg_packet_loss}%` : '—'}
                </p>
              </div>
              <p className="col-span-2 text-xs text-muted-foreground">{tel.samples} amostras</p>
            </div>
          )}
        </div>

        <div className={PANEL_CARD}>
          <h3 className="mb-2 text-base font-bold text-foreground">Push nos últimos 7 dias</h3>
          <p className="mb-4 text-xs text-muted-foreground">Volume enviado x falhas por dia.</p>
          <div className="h-44">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={chart7d}>
                <XAxis dataKey="label" tick={{ fill: '#a8a29e', fontSize: 10 }} axisLine={false} tickLine={false} />
                <YAxis hide />
                <Tooltip
                  cursor={false}
                  contentStyle={{
                    background: '#27272a',
                    border: '1px solid #3f3f46',
                    borderRadius: 8,
                    color: '#fafaf9',
                  }}
                />
                <Bar dataKey="sent" name="Enviadas" fill={CHART_BLUE} radius={[4, 4, 0, 0]} barSize={14} />
                <Bar dataKey="failed" name="Falhas" fill={CHART_ORANGE} radius={[4, 4, 0, 0]} barSize={14} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>
      </div>
    </div>
  )
}

function ProfilePanel({ user, onSaved, onNotify, onError }) {
  const fullNameFromUser = [user?.first_name, user?.last_name].filter(Boolean).join(' ').trim()
  const [form, setForm] = useState({
    full_name: fullNameFromUser,
    email: user?.email || '',
    phone: user?.phone || '',
    preferred_language: user?.preferred_language || 'pt-BR',
  })
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    setForm({
      full_name: [user?.first_name, user?.last_name].filter(Boolean).join(' ').trim(),
      email: user?.email || '',
      phone: user?.phone || '',
      preferred_language: user?.preferred_language || 'pt-BR',
    })
  }, [user])

  const setField = (key, value) => setForm((f) => ({ ...f, [key]: value }))

  const submit = async (e) => {
    e.preventDefault()
    setSaving(true)
    try {
      const res = await axios.patch(
        '/api/auth/me/',
        {
          full_name: form.full_name.trim(),
          email: form.email.trim(),
          phone: form.phone.trim(),
          preferred_language: form.preferred_language || 'pt-BR',
        },
        { headers: authHeaders() },
      )
      onSaved?.(res.data)
      onNotify?.('Perfil atualizado.')
    } catch (err) {
      onError?.(
        err?.response?.data?.error
        || err?.response?.data?.detail
        || 'Falha ao salvar perfil',
      )
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="w-full p-6">
      <form onSubmit={submit} className={`${PANEL_CARD} mx-auto w-full max-w-4xl space-y-6`}>
        <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <h2 className="text-lg font-bold text-foreground">Informações Pessoais</h2>
          <button type="submit" disabled={saving} className={`${BTN_PRIMARY} shrink-0 px-4`}>
            <Save className="h-4 w-4" />
            {saving ? 'Salvando…' : 'Salvar'}
          </button>
        </div>

        <div className="grid grid-cols-1 gap-5 md:grid-cols-2">
          <div>
            <label htmlFor="profile-full-name" className="mb-1.5 block text-sm text-foreground">
              Nome Completo
            </label>
            <input
              id="profile-full-name"
              type="text"
              value={form.full_name}
              onChange={(e) => setField('full_name', e.target.value)}
              className={PANEL_INPUT}
              placeholder="Seu nome"
              autoComplete="name"
            />
          </div>
          <div>
            <label htmlFor="profile-email" className="mb-1.5 block text-sm text-foreground">
              E-mail
            </label>
            <input
              id="profile-email"
              type="email"
              value={form.email}
              onChange={(e) => setField('email', e.target.value)}
              className={PANEL_INPUT}
              placeholder="seu@email.com"
              autoComplete="email"
            />
          </div>
          <div>
            <label htmlFor="profile-phone" className="mb-1.5 block text-sm text-foreground">
              Telefone
            </label>
            <input
              id="profile-phone"
              type="tel"
              value={form.phone}
              onChange={(e) => setField('phone', e.target.value)}
              className={PANEL_INPUT}
              placeholder="DDD + número"
              autoComplete="tel"
            />
          </div>
          <div>
            <label htmlFor="profile-language" className="mb-1.5 block text-sm text-foreground">
              Idioma do Sistema
            </label>
            <select
              id="profile-language"
              value={form.preferred_language}
              onChange={(e) => setField('preferred_language', e.target.value)}
              className={`${PANEL_INPUT} appearance-none bg-[length:1rem] bg-[right_0.75rem_center] bg-no-repeat pr-10`}
              style={{
                backgroundImage:
                  "url(\"data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='16' height='16' viewBox='0 0 24 24' fill='none' stroke='%23a1a1aa' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'%3E%3Cpolyline points='6 9 12 15 18 9'/%3E%3C/svg%3E\")",
              }}
            >
              <option value="pt-BR">Português</option>
              <option value="en">English</option>
              <option value="es">Español</option>
            </select>
          </div>
        </div>
      </form>
    </div>
  )
}

export default function ProviderAppPanel({ onLogout }) {
  const { user, setUser } = useAuth()
  const [tab, setTab] = useState('dashboard')
  const [isCollapsed, setIsCollapsed] = useState(() => localStorage.getItem('appPanelSidebarCollapsed') === 'true')
  const [stats, setStats] = useState(null)
  const [profile, setProfile] = useState(null)
  const [clients, setClients] = useState([])
  const [warnings, setWarnings] = useState([])
  const [plans, setPlans] = useState([])
  const [appConfig, setAppConfig] = useState(null)
  const [sgp, setSgp] = useState(null)
  const setError = useCallback((msg) => {
    if (msg) toast.error(msg)
  }, [])
  const setMessage = useCallback((msg) => {
    if (msg) toast.success(msg)
  }, [])
  const [loading, setLoading] = useState(true)
  const [search, setSearch] = useState('')
  const [pushRecipients, setPushRecipients] = useState([])

  const [planForm, setPlanForm] = useState({
    name: '',
    type: 'FIBRA',
    download_speed: 100,
    upload_speed: 50,
    price: '',
    description: '',
  })
  const [profileForm, setProfileForm] = useState(null)
  const [configForm, setConfigForm] = useState(null)
  const [configSaving, setConfigSaving] = useState(false)

  useEffect(() => {
    localStorage.setItem('appPanelSidebarCollapsed', isCollapsed ? 'true' : 'false')
  }, [isCollapsed])

  // Tema padrão alinhado ao painel de atendimento (pode ser alterado na topbar)
  useEffect(() => {
    if (!localStorage.getItem('theme')) {
      localStorage.setItem('theme', 'dark')
      document.documentElement.classList.add('dark')
    } else if (localStorage.getItem('theme') === 'dark') {
      document.documentElement.classList.add('dark')
    }
  }, [])

  const loadDashboard = useCallback(async () => {
    const res = await axios.get('/api/mobile-app/profiles/my-dashboard/', { headers: authHeaders() })
    setStats(res.data)
    if (res.data.profile) setProfile(res.data.profile)
  }, [])

  const loadMine = useCallback(async () => {
    const res = await axios.get('/api/mobile-app/profiles/mine/', { headers: authHeaders() })
    setProfile(res.data)
    setProfileForm({
      primary_color: res.data.primary_color || '#0D70B3',
      cnpj: res.data.cnpj || '',
      number: res.data.number || '',
      sgp_url: res.data.sgp_url || '',
      sgp_app_name: res.data.sgp_app_name || '',
      webhook_url: res.data.webhook_url || '',
      genieacs_url: res.data.genieacs_url || '',
      genieacs_user: res.data.genieacs_user || '',
      glass_intensity: res.data.glass_intensity ?? 82,
      glass_blur: res.data.glass_blur ?? 18,
      ambient_shadow: res.data.ambient_shadow ?? 55,
    })
    return res.data
  }, [])

  const loadClients = useCallback(async (qOverride) => {
    const q = typeof qOverride === 'string' ? qOverride : search
    const res = await axios.get('/api/mobile-app/app-users/', {
      headers: authHeaders(),
      params: q ? { q } : {},
    })
    setClients(res.data.results || res.data || [])
  }, [search])

  const loadWarnings = useCallback(async () => {
    const res = await axios.get('/api/mobile-app/warnings/', { headers: authHeaders() })
    setWarnings(res.data.results || res.data || [])
  }, [])

  const loadPlans = useCallback(async () => {
    const res = await axios.get('/api/mobile-app/plans/', { headers: authHeaders() })
    setPlans(res.data.results || res.data || [])
  }, [])

  const loadConfig = useCallback(async () => {
    const res = await axios.get('/api/mobile-app/profiles/mine-app-config/', { headers: authHeaders() })
    setAppConfig(res.data)
    setConfigForm({ ...res.data })
    return res.data
  }, [])

  const loadSgp = useCallback(async () => {
    const res = await axios.get('/api/mobile-app/panel/integrations/sgp/', { headers: authHeaders() })
    setSgp(res.data)
  }, [])

  const refresh = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      await loadDashboard()
      if (tab === 'clients') await loadClients()
      if (tab === 'warnings') await loadWarnings()
      if (tab === 'plans') await loadPlans()
      if (tab === 'config' || tab === 'profile') {
        await loadMine()
        if (tab === 'config') await loadConfig()
      }
      if (tab === 'sgp') await loadSgp()
    } catch (e) {
      const msg =
        e?.response?.data?.error ||
        e?.response?.data?.detail ||
        e.message ||
        'Erro ao carregar painel'
      setError(msg)
    } finally {
      setLoading(false)
    }
  }, [tab, loadDashboard, loadClients, loadWarnings, loadPlans, loadMine, loadConfig, loadSgp])

  useEffect(() => {
    refresh()
  }, [refresh])

  // Atualiza o dashboard periodicamente para os logs não ficarem travados
  useEffect(() => {
    if (tab !== 'dashboard') return undefined
    const id = setInterval(() => {
      loadDashboard().catch(() => {})
    }, 60_000)
    return () => clearInterval(id)
  }, [tab, loadDashboard])

  useEffect(() => {
    if (tab === 'config' && profile?.id) {
      loadConfig().catch(() => {})
    }
  }, [tab, profile?.id, loadConfig])

  const createWarning = async (data) => {
    await axios.post('/api/mobile-app/warnings/', data, { headers: authHeaders() })
    setMessage('Comunicado publicado.')
    await loadWarnings()
  }

  const deleteWarning = async (id) => {
    if (!window.confirm('Tem certeza que deseja excluir este comunicado?')) return
    await axios.delete(`/api/mobile-app/warnings/${id}/`, { headers: authHeaders() })
    toast.deleted('Comunicado excluído.')
    await loadWarnings()
  }

  const savePlan = async (data) => {
    const payload = {
      name: data.name,
      type: data.type,
      download_speed: data.download_speed,
      upload_speed: data.upload_speed,
      price: data.price || 0,
      description: data.description || '',
      is_active: data.is_active !== false,
    }
    if (data.id) {
      await axios.patch(`/api/mobile-app/plans/${data.id}/`, payload, { headers: authHeaders() })
      setMessage('Plano atualizado com sucesso!')
    } else {
      await axios.post('/api/mobile-app/plans/', payload, { headers: authHeaders() })
      setMessage('Plano criado com sucesso!')
    }
    await loadPlans()
  }

  const deletePlan = async (id) => {
    if (!window.confirm('Excluir este plano?')) return
    await axios.delete(`/api/mobile-app/plans/${id}/`, { headers: authHeaders() })
    toast.deleted('Plano excluído.')
    await loadPlans()
  }

  const deleteClient = async (id, { skipConfirm = false } = {}) => {
    if (!skipConfirm && !window.confirm('Excluir este cliente do app?')) return
    await axios.delete(`/api/mobile-app/app-users/${id}/`, { headers: authHeaders() })
    toast.deleted('Cliente excluído.')
    await loadClients()
    await loadDashboard()
  }

  const saveClient = async (id, data) => {
    await axios.patch(`/api/mobile-app/app-users/${id}/`, data, { headers: authHeaders() })
    setMessage('Cliente atualizado.')
    await loadClients()
  }

  const saveProfile = async (e) => {
    e.preventDefault()
    await axios.patch('/api/mobile-app/profiles/mine/', profileForm, { headers: authHeaders() })
    setMessage('Perfil atualizado.')
    await loadMine()
  }

  const saveConfig = async (e) => {
    e?.preventDefault?.()
    if (!configForm) return
    const payload = configPayload(configForm)
    setConfigSaving(true)
    setError('')
    try {
      const res = await axios.patch('/api/mobile-app/profiles/mine-app-config/', payload, {
        headers: authHeaders(),
      })
      setAppConfig(res.data)
      setConfigForm({ ...res.data })
      setMessage('Configurações do aplicativo salvas.')
    } catch (err) {
      setError(
        err?.response?.data?.detail
        || err?.response?.data?.error
        || 'Falha ao salvar configurações do aplicativo',
      )
    } finally {
      setConfigSaving(false)
    }
  }

  const rotateToken = async () => {
    if (!window.confirm('Isso invalidará seu token atual. Tem certeza?')) return
    const res = await axios.post('/api/mobile-app/panel/integrations/sgp/generate/', {}, {
      headers: authHeaders(),
    })
    setMessage(res.data.message || 'Novo token de integração gerado com sucesso!')
    setSgp((s) => ({
      ...(s || {}),
      provider_token: res.data.provider_token,
      sgp_token_created_at: res.data.sgp_token_created_at || res.data.created_at,
    }))
    await loadSgp()
  }

  const saveSgpCredentials = async (data) => {
    let res
    try {
      res = await axios.post(
        '/api/mobile-app/panel/integrations/sgp/credentials/',
        {
          erp_type: data.erp_type || 'sgp',
          sgp_url: data.sgp_url,
          sgp_token: data.sgp_token,
          sgp_app_name: data.sgp_app_name,
          app_default_team_id: data.app_default_team_id || null,
        },
        { headers: authHeaders() },
      )
    } catch (err) {
      toast.apiError(err, 'Não foi possível salvar as credenciais do ERP.')
      return
    }
    setMessage(res.data.message || 'Configurações atualizadas com sucesso!')
    await loadSgp()
  }

  const saveGenieCredentials = async (data) => {
    const payload = {
      genieacs_url: data.genieacs_url,
      genieacs_token: data.genieacs_token || '',
    }
    const res = await axios.post(
      '/api/mobile-app/panel/integrations/sgp/credentials/',
      payload,
      { headers: authHeaders() },
    )
    setMessage(res.data.message || 'Configurações atualizadas com sucesso!')
    setSgp((s) => ({
      ...(s || {}),
      genieacs_url: res.data.genieacs_url ?? data.genieacs_url ?? '',
      genieacs_token: res.data.genieacs_token || data.genieacs_token || '',
      has_genieacs_token: Boolean(res.data.has_genieacs_token || data.genieacs_token),
    }))
    await loadSgp()
  }

  const saveWebhook = async () => {
    const url = sgp?.webhook_url
    if (!url) return
    await axios.post(
      '/api/mobile-app/panel/integrations/sgp/webhook/',
      { webhook_url: url },
      { headers: authHeaders() },
    )
    setMessage('Webhook atualizado.')
    await loadSgp()
  }

  const inputClass = PANEL_INPUT
  const allTabs = [...NAV, ['profile', 'Perfil', User]]
  const pageTitle = allTabs.find(([k]) => k === tab)?.[1] || 'Painel'
  const pageSubtitle = 'Gerencie o aplicativo mobile dos seus clientes.'
  const isFormTab = FORM_TABS.has(tab) || tab === 'profile'

  const navBtnClass = (key) =>
    `flex w-full items-center rounded-lg transition-colors ${
      isCollapsed ? 'justify-center px-2 py-3' : 'justify-start gap-3 px-4 py-2.5'
    } ${
      tab === key
        ? 'bg-sidebar-accent font-semibold text-sidebar-accent-foreground'
        : 'text-sidebar-foreground hover:bg-sidebar-accent hover:text-sidebar-accent-foreground'
    }`

  return (
    <div className="flex h-screen bg-background text-foreground">
      <aside
        className={`z-30 flex h-full shrink-0 flex-col transition-all duration-300 ${
          isCollapsed ? 'w-14' : 'w-56'
        }`}
      >
        <div className="flex h-full flex-col border-r border-sidebar-border bg-sidebar text-sidebar-foreground">
          <div
            className={`flex flex-shrink-0 items-center border-b border-border p-4 ${
              isCollapsed ? 'justify-center' : 'justify-between'
            }`}
          >
            <img
              src="/logo.png"
              alt="NIO HUB"
              className={`h-14 w-auto max-w-[10.5rem] object-contain object-left transition-opacity duration-300 ${
                isCollapsed ? 'hidden' : 'block'
              }`}
            />
            <button
              type="button"
              onClick={() => setIsCollapsed((v) => !v)}
              className="rounded-lg p-2 transition-colors hover:bg-sidebar-accent"
              aria-label={isCollapsed ? 'Expandir sidebar' : 'Recolher sidebar'}
              title={isCollapsed ? 'Expandir' : 'Recolher'}
            >
              {isCollapsed ? <ChevronsRight className="h-5 w-5" /> : <ChevronsLeft className="h-5 w-5" />}
            </button>
          </div>

          <div className="flex min-h-0 flex-1 flex-col">
            <nav className="flex-1 overflow-x-hidden overflow-y-auto p-2">
              <div className={isCollapsed ? 'space-y-3' : 'space-y-1'}>
                {NAV.map(([key, label, Icon]) => (
                  <button
                    key={key}
                    type="button"
                    onClick={() => setTab(key)}
                    className={navBtnClass(key)}
                    title={isCollapsed ? label : undefined}
                  >
                    <Icon className="h-5 w-5 shrink-0" />
                    <span
                      className={`truncate text-sm transition-opacity duration-300 ${
                        isCollapsed ? 'hidden' : 'inline'
                      }`}
                    >
                      {label}
                    </span>
                  </button>
                ))}
              </div>
            </nav>
          </div>

          <div className="flex-shrink-0 border-t border-border p-2">
            <button
              type="button"
              onClick={() => setTab('profile')}
              className={navBtnClass('profile')}
              title={isCollapsed ? 'Perfil' : undefined}
            >
              <User className="h-5 w-5 shrink-0" />
              <span className={`transition-opacity duration-300 ${isCollapsed ? 'hidden' : 'inline'}`}>
                Perfil
              </span>
            </button>
          </div>
        </div>
      </aside>

      <div className="flex min-w-0 flex-1 flex-col overflow-hidden">
        <Topbar onLogout={onLogout} showInternalChat={false} showChangelog={false} />

        <main className="flex min-h-0 flex-1 flex-col overflow-y-auto bg-background">
        {!isFormTab && (
          <div className={`pb-0 ${tab === 'config' || tab === 'appearance' || tab === 'plans' || tab === 'sgp' || tab === 'staff' || tab === 'company' ? 'px-6 pt-4' : 'p-6'}`}>
            {tab !== 'config' && tab !== 'appearance' && tab !== 'plans' && tab !== 'sgp' && tab !== 'staff' && tab !== 'company' && (
              <div className="mb-6">
                <h1 className="text-2xl font-bold tracking-tight text-foreground">{pageTitle}</h1>
                <p className="mt-1 text-sm text-muted-foreground">{pageSubtitle}</p>
              </div>
            )}
          </div>
        )}

        {loading && !stats ? (
          <div className="p-6 text-muted-foreground">Carregando…</div>
        ) : (
          <div className={isFormTab ? 'flex flex-1 flex-col' : ''}>
            {tab === 'dashboard' && stats && <AppDashboard stats={stats} />}

            {tab === 'clients' && (
              <ClientsPanel
                clients={clients}
                search={search}
                setSearch={setSearch}
                onFilter={loadClients}
                onDelete={deleteClient}
                onSaveClient={saveClient}
                onSendPush={(selected) => {
                  setPushRecipients(selected)
                  setTab('push')
                }}
              />
            )}

            {tab === 'push' && (
              <NotificationsPanel
                selectedRecipients={pushRecipients}
                onClearRecipients={() => setPushRecipients([])}
                onSent={loadDashboard}
                setError={setError}
                setMessage={setMessage}
              />
            )}

            {tab === 'push-sent' && <SentNotificationsPanel />}

            {tab === 'warnings' && (
              <WarningsPanel
                warnings={warnings}
                onCreate={createWarning}
                onDelete={deleteWarning}
              />
            )}

            {tab === 'plans' && (
              <PlansPanel plans={plans} onSave={savePlan} onDelete={deletePlan} />
            )}

            {tab === 'config' && (
              <AppConfigPanel
                configForm={configForm}
                setConfigForm={setConfigForm}
                onSave={saveConfig}
                saving={configSaving}
              />
            )}

            {tab === 'sgp' && (
              <SgpIntegrationPanel
                sgp={sgp}
                setSgp={setSgp}
                onSaveSgp={saveSgpCredentials}
                onSaveGenie={saveGenieCredentials}
                onRotateToken={rotateToken}
                onNotify={setMessage}
              />
            )}

            {tab === 'staff' && (
              <StaffUsersPanel
                currentUserId={user?.id}
                onNotify={setMessage}
                onError={setError}
              />
            )}

            {tab === 'company' && (
              <CompanyPanel onNotify={setMessage} onError={setError} />
            )}

            {tab === 'appearance' && <AppearancePanel onNotify={setMessage} />}

            {tab === 'profile' && (
              <ProfilePanel
                user={user}
                onSaved={(data) => {
                  setUser(data)
                  try {
                    localStorage.setItem('user', JSON.stringify(data))
                  } catch {
                    /* ignore */
                  }
                }}
                onNotify={setMessage}
                onError={setError}
              />
            )}
          </div>
        )}
      </main>
      </div>
    </div>
  )
}
