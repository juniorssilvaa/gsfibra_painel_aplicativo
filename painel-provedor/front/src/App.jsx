import React, { useState, useEffect, useRef, Suspense, lazy } from 'react';
import { Routes, Route, Navigate } from 'react-router-dom';
import axios from 'axios';
import { AlertTriangle } from 'lucide-react';

import LoadingBar from './components/ui/LoadingBar';
import Login from './components/Login';
import BlockedScreen from './components/BlockedScreen';
import SuperadminHandoffRedirect from './components/SuperadminHandoffRedirect';
import { useAuth } from './contexts/AuthContext';
import useSessionTimeout from './hooks/useSessionTimeout.jsx';
import { APP_VERSION } from './config/version';
import { effectiveProvedorFromUser } from './utils/effectiveProvedorId';
import { PROVEDOR_PAYMENT_BLOCKED_EVENT } from './utils/provedorPaymentBlock';

import './App.css';

const ProvedorAppWrapper = lazy(() => import('./painel-provedor/ProvedorAppWrapper'));
const MetaFinalizing = lazy(() => import('./components/MetaFinalizing'));
const MetaConnectInner = lazy(() => import('./components/MetaConnectInner'));
const MetaAdsConnectInner = lazy(() => import('./components/MetaAdsConnectInner'));
const InstagramFinalizing = lazy(() => import('./components/InstagramFinalizing'));
const InstagramConnectInner = lazy(() => import('./components/InstagramConnectInner'));
const OAuthCallback = lazy(() => import('./components/OAuthCallback'));
const Changelog = lazy(() => import('./components/Changelog'));
const UserStatusManager = lazy(() => import('./components/UserStatusManager'));
const ConversationsPage = lazy(() => import('./components/ConversationsPage'));
const GlobalIncomingVoiceCallHost = lazy(() => import('./components/GlobalIncomingVoiceCallHost'));

class VoiceCallHostSafe extends React.Component {
  constructor(props) {
    super(props);
    this.state = { failed: false, errorKey: 0 };
    this._recoverTimer = null;
  }

  static getDerivedStateFromError() {
    return { failed: true };
  }

  componentDidCatch(err) {
    console.error('[VoiceCallHost] erro no popup de voz:', err);
    // Não deixa o host morto para sempre — remonta após o crash (ex.: bug pontual de render).
    if (this._recoverTimer) clearTimeout(this._recoverTimer);
    this._recoverTimer = setTimeout(() => {
      this.setState((s) => ({ failed: false, errorKey: s.errorKey + 1 }));
    }, 300);
  }

  componentWillUnmount() {
    if (this._recoverTimer) clearTimeout(this._recoverTimer);
  }

  render() {
    if (this.state.failed) return null;
    return <GlobalIncomingVoiceCallHost key={this.state.errorKey} user={this.props.user} />;
  }
}

export default function App() {
  const { user, loading: authLoading, logout, refresh } = useAuth();
  const [showChangelog, setShowChangelog] = useState(false);
  const [pendingChangelogVersion, setPendingChangelogVersion] = useState(APP_VERSION);
  const [whatsappDisconnected, setWhatsappDisconnected] = useState(false);
  const [isBlocked, setIsBlocked] = useState(false);
  const [billingChecked, setBillingChecked] = useState(false);
  const [resolvingProvider, setResolvingProvider] = useState(false);
  const providerResolvedRef = useRef(false);

  const { startTimeout } = useSessionTimeout(user);

  const userRole = user?.user_type || user?.role || null;
  const changelogStorageKey = user?.id ? `last_seen_changelog_version:${user.id}` : 'last_seen_changelog_version';

  // Auto-bloqueio mid-session: 403 do middleware dispara a tela de bloqueio (não o toast).
  useEffect(() => {
    const onPaymentBlocked = () => setIsBlocked(true);
    window.addEventListener(PROVEDOR_PAYMENT_BLOCKED_EVENT, onPaymentBlocked);
    return () => window.removeEventListener(PROVEDOR_PAYMENT_BLOCKED_EVENT, onPaymentBlocked);
  }, []);

  useEffect(() => {
    if (!user?.id) {
      setIsBlocked(false);
      setBillingChecked(false);
      return;
    }

    startTimeout();

    const checkChangelogVersion = async () => {
      try {
        const response = await axios.get('/api/changelog/', { skipErrorToast: true });
        const currentVersion = response.data?.current_version || APP_VERSION;
        const lastSeenVersion = localStorage.getItem(changelogStorageKey);

        setPendingChangelogVersion(currentVersion);
        if (lastSeenVersion !== currentVersion) {
          setShowChangelog(true);
        }
      } catch (error) {
        const lastSeenVersion = localStorage.getItem(changelogStorageKey);
        setPendingChangelogVersion(APP_VERSION);
        if (lastSeenVersion !== APP_VERSION) {
          setShowChangelog(true);
        }
      }
    };
    checkChangelogVersion();

    if (userRole === 'superadmin') {
      setBillingChecked(true);
      return undefined;
    }

    let cancelled = false;
    const checkBilling = async () => {
      try {
        const response = await axios.get('/api/provedores/status_pagamento/', {
          skipErrorToast: true,
        });
        if (!cancelled && response.data?.blocked) {
          setIsBlocked(true);
        }
      } catch (error) {
        // status_pagamento é isento; falha de rede não libera o painel por engano.
      } finally {
        if (!cancelled) setBillingChecked(true);
      }
    };

    checkBilling();
    // Revalida periodicamente (auto-bloqueio Asaas pode ocorrer com a sessão aberta).
    const interval = setInterval(checkBilling, 60_000);
    return () => {
      cancelled = true;
      clearInterval(interval);
    };
  }, [user?.id, userRole, startTimeout, changelogStorageKey]);

  useEffect(() => {
    if (!user?.id) return;

    let timer;

    const ping = async () => {
      try {
        await axios.post('/api/users/ping/', null, { skipErrorToast: true });
      } catch (err) {
      }
    };

    const initialTimer = setTimeout(() => {
      ping();
      timer = setInterval(ping, 30000);
    }, 1000);

    return () => {
      clearTimeout(initialTimer);
      if (timer) clearInterval(timer);
    };
  }, [user?.id]);

  // Quando o user está autenticado mas sem provedor_id, tentar refresh /me/ UMA VEZ
  // Evita loop infinito: rota * não pode redirecionar para /login quando user existe
  useEffect(() => {
    if (!user) return;
    if (effectiveProvedorFromUser(user)) return;
    if (providerResolvedRef.current) return;
    providerResolvedRef.current = true;
    setResolvingProvider(true);
    refresh().then(updated => {
      const pid = updated ? effectiveProvedorFromUser(updated) : null;
      setResolvingProvider(false);
      if (!pid) {
        // niohub sem provedor: o backend acabou de criar um Provedor mínimo —
        // aguardar 2s e recarregar a página (o /me/ já devolve o id novo)
        const isNiohub = String(updated?.username || user?.username || '').toLowerCase() === 'niohub';
        if (isNiohub) {
          setTimeout(() => window.location.reload(), 2000);
        } else {
          // Utilizador comum sem provedor → logout limpo
          logout().then(() => { window.location.href = '/login'; });
        }
      }
    });
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [user]);

  const handleLogout = async () => {
    await logout();
    window.location.href = '/login';
  };

  if (authLoading || resolvingProvider || (user && userRole !== 'superadmin' && !billingChecked && !isBlocked)) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="animate-pulse text-xl">Carregando...</div>
      </div>
    );
  }

  if (!user) {
    return (
      <Suspense fallback={<LoadingBar />}>
        <Routes>
          <Route path="/app/meta/connect-inner" element={<MetaConnectInner />} />
          <Route path="/app/meta/ads-connect" element={<MetaAdsConnectInner />} />
          <Route path="/app/instagram/connect-inner" element={<InstagramConnectInner />} />
          <Route path="/*" element={<Login />} />
        </Routes>
      </Suspense>
    );
  }

  if (isBlocked) {
    return <BlockedScreen onLogout={handleLogout} />;
  }

  // niohub = suporte no tenant (admin); não usar fluxo de handoff do Superadmin
  const isNiohubSupport = String(user?.username || '').toLowerCase() === 'niohub';
  if (userRole === 'superadmin' && !isNiohubSupport) {
    return (
      <Suspense fallback={<LoadingBar />}>
        <Routes>
          <Route path="/oauth/callback" element={<OAuthCallback />} />
          <Route path="*" element={<SuperadminHandoffRedirect />} />
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
    );
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
          <Route path="/app/instagram/finalizando" element={<InstagramFinalizing />} />
          <Route path="/app/instagram/connect-inner" element={<InstagramConnectInner />} />
          <Route path="/app/meta/ads-connect" element={<MetaAdsConnectInner />} />
          <Route path="/oauth/callback" element={<OAuthCallback />} />

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
            (() => {
              const pid = effectiveProvedorFromUser(user);
              // Se pid ainda for null mas user existe, o useEffect acima já cuida do refresh/logout
              // Não redirecionar para /login (causaria loop infinito com user autenticado)
              if (!pid) return <LoadingBar />;
              return userRole === 'agent'
                ? <Navigate to={`/${pid}/chat`} replace />
                : <Navigate to={`/app/accounts/${pid}/dashboard`} replace />;
            })()
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
        {user ? (
          <Suspense fallback={null}>
            <VoiceCallHostSafe user={user} />
          </Suspense>
        ) : null}
      </Suspense>
    </>
  );
}
