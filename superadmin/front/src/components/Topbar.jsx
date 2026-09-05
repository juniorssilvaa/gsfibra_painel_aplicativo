import React, { useEffect, useState } from 'react'
import { LogOut, Bell, Moon, Sun, MessageCircle, ClipboardList } from 'lucide-react'
import StatusDot from './StatusDot'

export default function Topbar({
  onLogout,
  onChangelog,
  showInternalChat = true,
  showChangelog = true,
  showNotifications = true,
}) {
  const [theme, setTheme] = useState(() => localStorage.getItem('theme') || 'dark')

  useEffect(() => {
    if (theme === 'dark') document.documentElement.classList.add('dark')
    else document.documentElement.classList.remove('dark')
    localStorage.setItem('theme', theme)
  }, [theme])

  return (
    <header className="h-14 border-b border-border bg-topbar px-6 py-2 flex items-center justify-between">
      <div />

      <div className="flex items-center gap-4">
        <StatusDot />

        <button
          type="button"
          onClick={() => setTheme((prev) => (prev === 'dark' ? 'light' : 'dark'))}
          className="p-1 rounded-md hover:bg-muted/40"
          title="Alternar tema"
          aria-label="Alternar tema"
        >
          {theme === 'dark' ? (
            <Moon className="w-5 h-5 text-topbar-foreground" />
          ) : (
            <Sun className="w-5 h-5 text-topbar-foreground" />
          )}
        </button>

        {showInternalChat && (
          <button type="button" className="p-1 rounded-md hover:bg-muted/40" title="Chat interno" aria-label="Chat interno">
            <MessageCircle className="w-5 h-5 text-topbar-foreground/90" />
          </button>
        )}

        {showChangelog && (
          <button
            type="button"
            onClick={onChangelog}
            className="p-1 rounded-md hover:bg-muted/40"
            title="Changelog"
            aria-label="Changelog"
          >
            <ClipboardList className="w-5 h-5 text-topbar-foreground/90" />
          </button>
        )}

        {showNotifications && (
          <button className="p-1 rounded-md hover:bg-muted/40" type="button" aria-label="Notificações" title="Notificações">
            <Bell className="w-5 h-5 text-topbar-foreground/90" />
          </button>
        )}

        <button
          type="button"
          onClick={onLogout}
          className="p-1 rounded-md hover:bg-muted/40"
          title="Sair"
          aria-label="Sair"
        >
          <LogOut className="w-5 h-5 text-topbar-foreground/90" />
        </button>
      </div>
    </header>
  )
}
