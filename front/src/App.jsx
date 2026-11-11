import React, { Suspense, lazy } from 'react'
import { Routes, Route, Navigate } from 'react-router-dom'
import axios from 'axios'
import Login from './components/Login'
import { useAuth } from './contexts/AuthContext'
import './App.css'

const ProviderAppPanel = lazy(() => import('./ProviderAppPanel'))

function isProviderAppAdmin(user) {
  const role = user?.user_type || user?.role
  return role === 'admin' && Boolean(user?.provedor || user?.provedor_id)
}

export default function App() {
  const { user, loading: authLoading, logout } = useAuth()

  const userRole = user?.user_type || user?.role || null
  const isAppAdmin = isProviderAppAdmin(user)

  React.useEffect(() => {
    if (user?.id) {
      localStorage.setItem('token', localStorage.getItem('auth_token') || '')
    }
  }, [user?.id])

  React.useEffect(() => {
    if (!user?.id) return
    let intervalId
    const ping = async () => {
      try {
        await axios.post('/api/users/ping/')
      } catch {
        /* ignore */
      }
    }
    const initialTimer = setTimeout(() => {
      ping()
      intervalId = setInterval(ping, 30000)
    }, 1000)
    return () => {
      clearTimeout(initialTimer)
      if (intervalId) clearInterval(intervalId)
    }
  }, [user?.id])

  const handleLogout = async () => {
    await logout()
    window.location.href = '/login'
  }

  if (authLoading) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="animate-pulse text-xl">Carregando...</div>
      </div>
    )
  }

  if (!user) {
    return (
      <Routes>
        <Route path="/*" element={<Login />} />
      </Routes>
    )
  }

  if (!isAppAdmin) {
    return (
      <div className="min-h-screen flex flex-col items-center justify-center gap-4 p-6 text-center">
        <p className="text-lg">
          O GSFibra é exclusivo para administradores do aplicativo do provedor.
        </p>
        <button
          type="button"
          className="rounded bg-primary px-4 py-2 text-primary-foreground"
          onClick={() => logout().then(() => { window.location.href = '/login' })}
        >
          Sair
        </button>
      </div>
    )
  }

  return (
    <Suspense fallback={<div className="p-6">Carregando…</div>}>
      <Routes>
        <Route path="/painel/*" element={<ProviderAppPanel onLogout={handleLogout} />} />
        <Route path="/login" element={<Navigate to="/painel" replace />} />
        <Route path="*" element={<Navigate to="/painel" replace />} />
      </Routes>
    </Suspense>
  )
}
