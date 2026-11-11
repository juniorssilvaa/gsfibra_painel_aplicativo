;(function consumeAuthHandoffHash() {
  try {
    const raw = window.location.hash || ''
    const prefix = '#niochat_auth_handoff='
    if (!raw.startsWith(prefix)) return
    const token = decodeURIComponent(raw.slice(prefix.length))
    if (token) {
      localStorage.setItem('auth_token', token)
      localStorage.setItem('token', token)
    }
  } catch {
    /* ignore */
  }
  window.history.replaceState(null, '', window.location.pathname + window.location.search)
})()

import React from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App.jsx'
import ErrorBoundary from './components/ErrorBoundary.jsx'
import { BrowserRouter as Router } from 'react-router-dom'
import { AuthProvider } from './contexts/AuthContext'
import { AppToaster } from './lib/notify'

createRoot(document.getElementById('root')).render(
  <ErrorBoundary>
    <Router>
      <AuthProvider>
        <App />
        <AppToaster />
      </AuthProvider>
    </Router>
  </ErrorBoundary>
)
