import React, { useEffect, useState } from 'react'
import { LogOut, Moon, Sun } from 'lucide-react'
import StatusDot from './StatusDot'

export default function Topbar({ onLogout }) {
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
