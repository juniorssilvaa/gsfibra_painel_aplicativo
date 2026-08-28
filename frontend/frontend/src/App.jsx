import React, { useState, useEffect, Suspense, lazy } from 'react';
import { Routes, Route, Navigate } from 'react-router-dom';
import axios from 'axios';
import { io } from 'socket.io-client';
import { AlertTriangle } from 'lucide-react';

import LoadingBar from './components/ui/LoadingBar';
import Login from './components/Login';
import Topbar from './components/Topbar';
import BlockedScreen from './components/BlockedScreen';
import { useAuth } from './contexts/AuthContext';
import useSessionTimeout from './hooks/useSessionTimeout.jsx';
import { APP_VERSION } from './config/version';

import './App.css';

// Lazy loading components
const SuperadminSidebar = lazy(() => import('./components/SuperadminSidebar'));
const SuperadminDashboard = lazy(() => import('./components/SuperadminDashboard'));
const ProvedorAppWrapper = lazy(() => import('./components/ProvedorAppWrapper'));
const MetaFinalizing = lazy(() => import('./components/MetaFinalizing'));
const MetaFinalizingSuperadmin = lazy(() => import('./components/MetaFinalizingSuperadmin'));
const OAuthCallback = lazy(() => import('./components/OAuthCallback'));
const Changelog = lazy(() => import('./components/Changelog'));
const UserStatusManager = lazy(() => import('./components/UserStatusManager'));
const ConversationsPage = lazy(() => import('./components/ConversationsPage'));

/* =====================================================
   HELPERS
===================================================== */

const isMetaFinalizingPath = (pathname) =>
  pathname === '/app/meta/finalizando' ||
  pathname.startsWith('/app/meta/finalizando');

/* =====================================================
   APP
===================================================== */

export default function App() {
  // ✅ CONSUMIR APENAS - não decidir nada sobre auth
  const { user, loading: authLoading, logout } = useAuth();
  const [showChangelog, setShowChangelog] = useState(false);
  const [pendingChangelogVersion, setPendingChangelogVersion] = useState(APP_VERSION);
  const [whatsappDisconnected, setWhatsappDisconnected] = useState(false);
  const [isBlocked, setIsBlocked] = useState(false);
  const [checkingBilling, setCheckingBilling] = useState(false);

  const { startTimeout } = useSessionTimeout(user);

  // Extrair dados do usuário (sem acessar localStorage)
  const userRole = user?.user_type || user?.role || null;
  const provedorId = user?.provedor_id || null;
  const changelogStorageKey = user?.id ? `last_seen_changelog_version:${user.id}` : 'last_seen_changelog_version';

  // Iniciar timeout de sessão quando usuário estiver logado
  useEffect(() => {
    if (user?.id) {
      startTimeout();

      // Verificar versão do Changelog de forma determinística (por usuário)
      const checkChangelogVersion = async () => {
        try {
          const response = await axios.get('/api/changelog/');
          const currentVersion = response.data?.current_version || APP_VERSION;
          const lastSeenVersion = localStorage.getItem(changelogStorageKey);

          setPendingChangelogVersion(currentVersion);
          if (lastSeenVersion !== currentVersion) {
            setShowChangelog(true);
          }
        } catch (error) {
          // Fallback local para manter funcionamento mesmo sem API
          const lastSeenVersion = localStorage.getItem(changelogStorageKey);
          setPendingChangelogVersion(APP_VERSION);
          if (lastSeenVersion !== APP_VERSION) {
            setShowChangelog(true);
          }
        }
      };
      checkChangelogVersion();

      // Verificar inadimplência do provedor (apenas usuários não-superadmin)
      if (userRole !== 'superadmin' && !checkingBilling) {
        const checkBilling = async () => {
          setCheckingBilling(true);
          try {
            const response = await axios.get('/api/provedores/status_pagamento/');
            if (response.data.blocked) {
              setIsBlocked(true);
            }
          } catch (error) {
            console.error('[BILLING] Erro ao verificar status:', error);
          } finally {
            setCheckingBilling(false);
          }
        };
        checkBilling();
      }
    }
  }, [user?.id, userRole, startTimeout, changelogStorageKey]);

  /* =====================================================
     WEBSOCKET (SÓ DEPOIS DO AUTH)
  ===================================================== */

  useEffect(() => {
    if (!user) return;

    const evoInstance = localStorage.getItem('evoInstance');
    if (!evoInstance) return;

    const socket = io(`wss://evo.niohub.com.br/${evoInstance}`, {
      transports: ['websocket'],
    });

    return () => socket.disconnect();
  }, [user]);

  /* =====================================================
     PRESENÇA (PING)
  ===================================================== */

  useEffect(() => {
    if (!user?.id) return;

    let timer;

    const ping = async () => {
      try {
        const token = localStorage.getItem('auth_token');
        console.debug('[APP] Ping iniciado', {
          userId: user.id,
          tokenExists: !!token,
          tokenPrefix: token?.substring(0, 10)
        });
        await axios.post('/api/users/ping/');
        console.debug('[APP] Ping bem-sucedido', { userId: user.id });
      } catch (err) {
        console.error('[APP] Ping falhou', {
          userId: user.id,
          status: err.response?.status,
          error: err.response?.data
        });
      }
    };

    // Delay inicial para garantir que o token está estável após login
    const initialTimer = setTimeout(() => {
      ping();
      timer = setInterval(ping, 30000);
    }, 1000);

    return () => {
      clearTimeout(initialTimer);
      if (timer) clearInterval(timer);
    };
  }, [user?.id]);

  /* =====================================================
     LOGOUT
  ===================================================== */

  const handleLogout = async () => {
    await logout();
    window.location.href = '/login';
  };

  /* =====================================================
     LOADING
  ===================================================== */

  if (authLoading) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="animate-pulse text-xl">Carregando...</div>
      </div>
    );
  }

  /* =====================================================
     NÃO AUTENTICADO
  ===================================================== */

  if (!user) {
    return (
      <Routes>
        <Route path="/*" element={<Login />} />
      </Routes>
    );
  }

  /* =====================================================
     ROTAS
  ===================================================== */

  if (isBlocked) {
    return <BlockedScreen onLogout={handleLogout} />;
  }

  return (
    <>
      {whatsappDisconnected && (
        <div className="fixed inset-0 bg-white/90 z-50 flex items-center justify-center">
          <div className="p-10 bg-white rounded-xl text-center">
            <AlertTriangle className="mx-auto mb-4 text-red-600" size={48} />
            <h3 className="text-xl font-bold mb-2">WhatsApp desconectado</h3>
            <button
              onClick={() => window.location.reload()}
              className="mt-4 bg-red-600 text-white px-6 py-2 rounded"
            >
              Reconectar
            </button>
          </div>
        </div>
      )}

      <Suspense fallback={<LoadingBar />}>
        <Routes>
          <Route path="/app/meta/finalizando" element={<MetaFinalizing />} />
          <Route path="/app/meta/finalizando-superadmin" element={<MetaFinalizingSuperadmin />} />
          <Route path="/oauth/callback" element={<OAuthCallback />} />

          {userRole === 'superadmin' && (
            <Route path="/superadmin/*" element={
              <div className="flex h-screen">
                <SuperadminSidebar onLogout={handleLogout} />
                <div className="flex-1 flex flex-col overflow-hidden">
                  <Topbar onLogout={handleLogout} onChangelog={() => setShowChangelog(true)} />
                  <SuperadminDashboard />
                </div>
              </div>
            } />
          )}

          <Route path="/:provedorId/chat" element={
            <ConversationsPage user={user} />
          } />

          <Route path="/app/accounts/:provedorId/*" element={
            <ProvedorAppWrapper
              user={user}
              userRole={userRole}
              handleLogout={handleLogout}
              setWhatsappDisconnected={setWhatsappDisconnected}
            />
          } />

          <Route path="*" element={
            userRole === 'superadmin'
              ? <Navigate to="/superadmin" replace />
              : (userRole === 'agent' 
                  ? <Navigate to={`/${user.provedor_id}/chat`} replace />
                  : <Navigate to={`/app/accounts/${user.provedor_id}/dashboard`} replace />
                )
          } />
        </Routes>

        <Changelog
          isOpen={showChangelog}
          onClose={() => {
            setShowChangelog(false);
            localStorage.setItem(changelogStorageKey, pendingChangelogVersion || APP_VERSION);
          }}
        />
        <UserStatusManager user={user} />
      </Suspense>
    </>
  );
}
