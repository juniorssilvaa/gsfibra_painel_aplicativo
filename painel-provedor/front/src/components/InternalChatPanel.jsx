import React, { useState, useEffect, useRef, useContext, useMemo } from 'react';
import { createPortal } from 'react-dom';
import { Avatar, AvatarFallback, AvatarImage } from './ui/avatar';
import { Input } from './ui/input';
import useOnlineUsers from '../hooks/useOnlineUsers';
import { NotificationContext } from '../contexts/NotificationContext';
import PrivateChatSidebar from './PrivateChatSidebar';
import {
  MessageCircle,
  Search,
  X,
  GripHorizontal,
  Users,
} from 'lucide-react';
import axios from 'axios';

const API_BASE = '/api';
const PANEL_POS_KEY = 'internal_chat_panel_position';
const PANEL_MARGIN = 8;
const PANEL_WIDTH = 860;
const PANEL_HEIGHT = 620;

const getAuthToken = () =>
  localStorage.getItem('auth_token') || localStorage.getItem('token');

const getUserName = (user) =>
  `${user?.first_name || ''} ${user?.last_name || ''}`.trim() || user?.username || 'Usuário';

const getUserInitials = (user) => {
  const name = getUserName(user);
  return name.split(' ').map((n) => n[0]).join('').toUpperCase().slice(0, 2);
};

const formatMessageTime = (iso) => {
  if (!iso) return '';
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return '';
  const now = new Date();
  const isToday =
    date.getDate() === now.getDate() &&
    date.getMonth() === now.getMonth() &&
    date.getFullYear() === now.getFullYear();
  if (isToday) {
    return date.toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' });
  }
  return date.toLocaleDateString('pt-BR', { day: '2-digit', month: '2-digit' });
};

const formatLastSeen = (iso, isOnline) => {
  if (isOnline) return 'Online';
  if (!iso) return 'Offline';
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return 'Offline';
  const diffMin = Math.floor((Date.now() - date.getTime()) / 60000);
  if (diffMin < 1) return 'Visto agora';
  if (diffMin < 60) return `Visto há ${diffMin} min`;
  const diffH = Math.floor(diffMin / 60);
  if (diffH < 24) return `Visto há ${diffH}h`;
  return `Visto em ${date.toLocaleDateString('pt-BR', { day: '2-digit', month: '2-digit' })}`;
};

const InternalChatPanel = ({ isOpen, onClose }) => {
  const [users, setUsers] = useState([]);
  const [currentUser, setCurrentUser] = useState(null);
  const [selectedUser, setSelectedUser] = useState(null);
  const [searchTerm, setSearchTerm] = useState('');
  const [loading, setLoading] = useState(false);
  const [panelPosition, setPanelPosition] = useState(null);

  const panelRef = useRef(null);
  const panelDragRef = useRef({
    active: false,
    startX: 0,
    startY: 0,
    originX: 0,
    originY: 0,
  });

  const notificationContext = useContext(NotificationContext);
  const { internalChatUnreadByUser } = notificationContext;

  let isUserOnline = () => false;
  try {
    const onlineUsersHook = useOnlineUsers();
    isUserOnline = onlineUsersHook.isUserOnline || (() => false);
  } catch (_) {}

  const resolveOnline = (user) =>
    Boolean(isUserOnline(user.id) || user.is_online);

  const getPanelSize = () => {
    const el = panelRef.current;
    if (el) {
      const rect = el.getBoundingClientRect();
      return { width: rect.width, height: rect.height };
    }
    return {
      width: PANEL_WIDTH,
      height: Math.min(PANEL_HEIGHT, window.innerHeight - 88),
    };
  };

  const clampPanelPosition = (x, y) => {
    const { width, height } = getPanelSize();
    return {
      x: Math.min(Math.max(PANEL_MARGIN, x), window.innerWidth - width - PANEL_MARGIN),
      y: Math.min(Math.max(PANEL_MARGIN, y), window.innerHeight - height - PANEL_MARGIN),
    };
  };

  const getDefaultPanelPosition = () => {
    const { width, height } = getPanelSize();
    return clampPanelPosition(window.innerWidth - width - 16, window.innerHeight - height - 16);
  };

  const persistPanelPosition = (pos) => {
    try {
      localStorage.setItem(PANEL_POS_KEY, JSON.stringify(pos));
    } catch (_) {}
  };

  const handlePanelHeaderPointerDown = (e) => {
    if (e.button !== 0) return;
    e.preventDefault();
    const current = panelPosition || getDefaultPanelPosition();
    if (!panelPosition) setPanelPosition(current);
    panelDragRef.current = {
      active: true,
      startX: e.clientX,
      startY: e.clientY,
      originX: current.x,
      originY: current.y,
    };
    document.body.style.userSelect = 'none';
    document.body.style.cursor = 'grabbing';
  };

  const endPanelDrag = () => {
    if (!panelDragRef.current.active) return;
    panelDragRef.current.active = false;
    document.body.style.userSelect = '';
    document.body.style.cursor = '';
    setPanelPosition((pos) => {
      if (pos) persistPanelPosition(pos);
      return pos;
    });
  };

  const loadUsers = async () => {
    try {
      setLoading(true);
      const token = getAuthToken();
      if (!token) {
        setUsers([]);
        return;
      }
      const response = await axios.get(`${API_BASE}/users/my_provider_users/`, {
        headers: { Authorization: `Token ${token}` },
      });
      setUsers(response.data.users || []);
    } catch (error) {
      setUsers([]);
    } finally {
      setLoading(false);
    }
  };

  const loadCurrentUser = async () => {
    try {
      const token = getAuthToken();
      const response = await axios.get('/api/auth/me/', {
        headers: { Authorization: `Token ${token}` },
      });
      setCurrentUser(response.data);
    } catch (error) {
      setCurrentUser(null);
    }
  };

  useEffect(() => {
    if (!isOpen) return;
    loadUsers();
    loadCurrentUser();
    const interval = setInterval(loadUsers, 30000);
    return () => clearInterval(interval);
  }, [isOpen]);

  // Atualizar dados do contato selecionado (online / last_seen) sem recriar objeto a cada render
  useEffect(() => {
    if (!selectedUser?.id || users.length === 0) return;
    const fresh = users.find((u) => u.id === selectedUser.id);
    if (!fresh) return;
    if (
      fresh.last_seen !== selectedUser.last_seen ||
      Boolean(fresh.is_online) !== Boolean(selectedUser.is_online) ||
      fresh.last_message_preview !== selectedUser.last_message_preview ||
      fresh.last_message_at !== selectedUser.last_message_at
    ) {
      setSelectedUser(fresh);
    }
  }, [users, selectedUser?.id]);

  useEffect(() => {
    if (!isOpen) return;
    let saved = null;
    try {
      const raw = localStorage.getItem(PANEL_POS_KEY);
      if (raw) saved = JSON.parse(raw);
    } catch (_) {}
    if (saved && typeof saved.x === 'number' && typeof saved.y === 'number') {
      setPanelPosition(clampPanelPosition(saved.x, saved.y));
      return;
    }
    setPanelPosition(null);
    const frame = requestAnimationFrame(() => setPanelPosition(getDefaultPanelPosition()));
    return () => cancelAnimationFrame(frame);
  }, [isOpen]);

  useEffect(() => {
    const onPointerMove = (e) => {
      if (!panelDragRef.current.active) return;
      const dx = e.clientX - panelDragRef.current.startX;
      const dy = e.clientY - panelDragRef.current.startY;
      setPanelPosition(
        clampPanelPosition(
          panelDragRef.current.originX + dx,
          panelDragRef.current.originY + dy
        )
      );
    };
    window.addEventListener('pointermove', onPointerMove);
    window.addEventListener('pointerup', endPanelDrag);
    window.addEventListener('pointercancel', endPanelDrag);
    return () => {
      window.removeEventListener('pointermove', onPointerMove);
      window.removeEventListener('pointerup', endPanelDrag);
      window.removeEventListener('pointercancel', endPanelDrag);
      document.body.style.userSelect = '';
      document.body.style.cursor = '';
    };
  }, []);

  useEffect(() => {
    if (!isOpen || !panelPosition) return;
    const onResize = () => {
      setPanelPosition((pos) => (pos ? clampPanelPosition(pos.x, pos.y) : pos));
    };
    window.addEventListener('resize', onResize);
    return () => window.removeEventListener('resize', onResize);
  }, [isOpen, panelPosition]);

  const filteredUsers = useMemo(() => {
    const term = searchTerm.trim().toLowerCase();
    const list = users.filter((user) => {
      if (user.id === currentUser?.id) return false;
      if (!term) return true;
      const haystack = `${getUserName(user)} ${user.username || ''}`.toLowerCase();
      return haystack.includes(term);
    });

    return list.sort((a, b) => {
      const aOnline = resolveOnline(a);
      const bOnline = resolveOnline(b);
      if (aOnline !== bOnline) return aOnline ? -1 : 1;
      const aUnread = (a.unread_count || internalChatUnreadByUser?.[a.id] || 0) > 0;
      const bUnread = (b.unread_count || internalChatUnreadByUser?.[b.id] || 0) > 0;
      if (aUnread !== bUnread) return aUnread ? -1 : 1;
      const aTime = a.last_message_at ? new Date(a.last_message_at).getTime() : 0;
      const bTime = b.last_message_at ? new Date(b.last_message_at).getTime() : 0;
      if (aTime !== bTime) return bTime - aTime;
      return getUserName(a).localeCompare(getUserName(b), 'pt-BR');
    });
  }, [users, searchTerm, currentUser?.id, internalChatUnreadByUser]);

  const onlineCount = filteredUsers.filter((u) => resolveOnline(u)).length;

  if (!isOpen) return null;

  const panelStyle = panelPosition
    ? { left: panelPosition.x, top: panelPosition.y }
    : { right: 16, bottom: 16 };

  const panel = (
    <div
      ref={panelRef}
      style={panelStyle}
      className="fixed z-[200] flex h-[min(620px,calc(100vh-4rem))] max-h-[calc(100vh-4rem)] w-[min(860px,calc(100vw-2rem))] flex-col overflow-hidden rounded-xl border border-border bg-card shadow-2xl"
      role="dialog"
      aria-label="Chat interno da equipe"
    >
      {/* Barra superior — arrastar */}
      <div
        className="flex shrink-0 cursor-grab items-center justify-between border-b border-border bg-card px-3 py-2 active:cursor-grabbing select-none"
        onPointerDown={handlePanelHeaderPointerDown}
      >
        <div className="flex items-center gap-2 min-w-0">
          <GripHorizontal className="h-4 w-4 shrink-0 text-muted-foreground/70" />
          <MessageCircle className="h-4 w-4 text-primary shrink-0" />
          <span className="text-sm font-semibold text-foreground truncate">Conversas</span>
        </div>
        <button
          type="button"
          onClick={onClose}
          onPointerDown={(e) => e.stopPropagation()}
          className="rounded-md p-1.5 text-muted-foreground hover:bg-muted hover:text-foreground"
          title="Fechar"
        >
          <X className="h-4 w-4" />
        </button>
      </div>

      <div className="flex min-h-0 flex-1">
        {/* Coluna esquerda — lista de usuários */}
        <div className="flex w-[220px] sm:w-[240px] shrink-0 flex-col border-r border-border bg-card/95">
          <div className="shrink-0 border-b border-border p-2.5">
            <div className="relative">
              <Search className="pointer-events-none absolute left-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
              <Input
                value={searchTerm}
                onChange={(e) => setSearchTerm(e.target.value)}
                placeholder="Pesquisar ou começar..."
                className="h-9 pl-8 text-sm bg-background/80"
              />
            </div>
          </div>

          <div className="min-h-0 flex-1 overflow-y-auto">
            {loading ? (
              <div className="flex h-32 items-center justify-center">
                <div className="h-8 w-8 animate-spin rounded-full border-b-2 border-primary" />
              </div>
            ) : filteredUsers.length === 0 ? (
              <div className="flex flex-col items-center justify-center px-4 py-10 text-center">
                <Users className="mb-3 h-10 w-10 text-muted-foreground/40" />
                <p className="text-sm text-muted-foreground">Nenhum usuário encontrado</p>
              </div>
            ) : (
              filteredUsers.map((user) => {
                const online = resolveOnline(user);
                const unread =
                  user.unread_count ||
                  internalChatUnreadByUser?.[user.id] ||
                  0;
                const isActive = selectedUser?.id === user.id;
                const lastSeenLabel = formatLastSeen(user.last_seen, online);
                const lastMsgPreview = (user.last_message_preview || '').trim();

                return (
                  <button
                    key={user.id}
                    type="button"
                    onClick={() => setSelectedUser(user)}
                    className={`flex w-full items-center gap-3 border-b border-border/60 px-3 py-2.5 text-left transition-colors ${
                      isActive
                        ? 'bg-primary/15'
                        : 'hover:bg-muted/60'
                    }`}
                  >
                    <div className="relative shrink-0">
                      <Avatar className="h-11 w-11">
                        <AvatarImage src={user.avatar} />
                        <AvatarFallback className="bg-muted text-xs font-semibold">
                          {getUserInitials(user)}
                        </AvatarFallback>
                      </Avatar>
                      <span
                        className={`absolute bottom-0 right-0 h-3 w-3 rounded-full border-2 border-card ${
                          online ? 'bg-green-500' : 'bg-[#ef4444]'
                        }`}
                      />
                    </div>

                    <div className="min-w-0 flex-1">
                      <div className="flex items-start justify-between gap-2">
                        <span className="truncate text-sm font-medium text-foreground">
                          {getUserName(user)}
                        </span>
                        <span className="shrink-0 text-[10px] text-muted-foreground">
                          {formatMessageTime(user.last_message_at)}
                        </span>
                      </div>
                      <div className="mt-0.5 flex items-center justify-between gap-2">
                        <p className="truncate text-xs text-muted-foreground">
                          {online ? (
                            <span className="text-green-500">Online</span>
                          ) : (
                            lastSeenLabel
                          )}
                        </p>
                        {unread > 0 && (
                          <span className="flex h-5 min-w-[20px] shrink-0 items-center justify-center rounded-full bg-[#ef4444] px-1.5 text-[10px] font-bold leading-none text-white shadow-[0_0_4px_rgba(239,68,68,0.85)]">
                            {unread > 9 ? '9+' : unread}
                          </span>
                        )}
                      </div>
                      {!!lastMsgPreview && (
                        <p className="mt-0.5 truncate text-[11px] text-muted-foreground/80">
                          {lastMsgPreview}
                        </p>
                      )}
                    </div>
                  </button>
                );
              })
            )}
          </div>
        </div>

        {/* Coluna direita — conversa */}
        <div className="flex min-w-0 flex-1 flex-col bg-background">
          <PrivateChatSidebar
            embedded
            isOpen
            selectedUser={selectedUser}
            currentUser={currentUser}
            onClose={() => setSelectedUser(null)}
          />
        </div>
      </div>
    </div>
  );

  return createPortal(panel, document.body);
};

export default InternalChatPanel;
