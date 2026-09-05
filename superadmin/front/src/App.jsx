import React, { useEffect, useState, Suspense, lazy } from 'react'
import { Routes, Route, Navigate } from 'react-router-dom'
import axios from 'axios'
import Login from './components/Login'
import Topbar from './components/Topbar'
import Changelog from './components/Changelog'
import { useAuth } from './contexts/AuthContext'

import './App.css'

const SuperadminSidebar = lazy(() => import('./SuperadminSidebar'))
const SuperadminDashboard = lazy(() => import('./SuperadminDashboard'))
const MetaFinalizingSuperadmin = lazy(() => import('./MetaFinalizingSuperadmin'))
const MetaConnectInnerSuperadmin = lazy(() => import('./components/MetaConnectInnerSuperadmin'))
const OAuthCallback = lazy(() => import('./components/OAuthCallback'))
const ProviderAppPanel = lazy(() => import('./ProviderAppPanel'))

function isProviderAppAdmin(user) {
  const role = user?.user_type || user?.role
  return role === 'admin' && Boolean(user?.provedor || user?.provedor_id)
}

export default function App() {
  const { user, loading: authLoading, logout } = useAuth()
  const [showChangelog, setShowChangelog] = useState(false)

  const userRole = user?.user_type || user?.role || null
  const isSuperadmin = userRole === 'superadmin'
  const isAppAdmin = isProviderAppAdmin(user)

  useEffect(() => {
    if (user?.id) {
      localStorage.setItem('token', localStorage.getItem('auth_token') || '')
    }
  }, [user?.id])

  useEffect(() => {
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
        <Route path="/app/meta/connect-inner" element={<Suspense fallback={null}><MetaConnectInnerSuperadmin /></Suspense>} />
        <Route path="/*" element={<Login />} />
      </Routes>
    )
  }

  if (!isSuperadmin && !isAppAdmin) {
    return (
      <div className="min-h-screen flex flex-col items-center justify-center gap-4 p-6 text-center">
        <p className="text-lg">Este acesso é exclusivo para superadministradores Niohub ou administradores do app do provedor.</p>
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

  if (isAppAdmin && !isSuperadmin) {
    return (
      <Suspense fallback={<div className="p-6">Carregando…</div>}>
        <Routes>
          <Route path="/painel/*" element={<ProviderAppPanel onLogout={handleLogout} />} />
          <Route path="*" element={<Navigate to="/painel" replace />} />
        </Routes>
      </Suspense>
    )
  }

  return (
    <Suspense fallback={<div className="p-6">Carregando...</div>}>
      <Routes>
        <Route path="/app/meta/finalizando-superadmin" element={<MetaFinalizingSuperadmin />} />
        <Route path="/app/meta/connect-inner" element={<MetaConnectInnerSuperadmin />} />
        <Route path="/oauth/callback" element={<OAuthCallback />} />
        <Route
          path="/admin/*"
          element={
            <div className="flex h-screen">
              <SuperadminSidebar onLogout={handleLogout} />
              <div className="flex flex-1 flex-col overflow-hidden">
                <Topbar onLogout={handleLogout} onChangelog={() => setShowChangelog(true)} />
                <SuperadminDashboard />
              </div>
            </div>
          }
        />
        <Route path="*" element={<Navigate to="/admin" replace />} />
      </Routes>
      <Changelog isOpen={showChangelog} onClose={() => setShowChangelog(false)} />
    </Suspense>
  )
}
