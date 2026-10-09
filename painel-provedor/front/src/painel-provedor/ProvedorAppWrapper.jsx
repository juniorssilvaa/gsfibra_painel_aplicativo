import React, { useEffect, useRef, useState, Suspense, lazy } from 'react';
import { useParams, Routes, Route, Navigate, useLocation, useNavigate } from 'react-router-dom';
import Sidebar from '../components/Sidebar';
import Topbar from '../components/Topbar';
import LoadingBar from '../components/ui/LoadingBar';
import Changelog from '../components/Changelog';
import RemindersModal from '../components/RemindersModal';
import { parseRouteProvedorId, getEffectiveProvedorId } from '../utils/effectiveProvedorId';
import { useAuth } from '../contexts/AuthContext';

// Lazy loading components
const DashboardPrincipal = lazy(() => import('../components/DashboardPrincipal'));
const ConversasDashboard = lazy(() => import('../components/ConversasDashboard'));
const Contacts = lazy(() => import('../components/Contacts2'));
const ConversationsPage = lazy(() => import('../components/ConversationsPage'));
const Settings = lazy(() => import('../components/Settings'));
const UserManagement = lazy(() => import('../components/UserManagement'));
const TeamsPage = lazy(() => import('../components/TeamsPage'));
const ConversationAudit = lazy(() => import('../components/ConversationAudit'));
const AIPerformancePage = lazy(() => import('../components/AIPerformancePage'));
const MarketingStudioPage = lazy(() => import('../components/MarketingStudioPage'));
const CampaignsPage = lazy(() => import('../components/CampaignsPage'));
const SuggestionsPage = lazy(() => import('../components/SuggestionsPage'));
const CompanyManagement = lazy(() => import('../components/CompanyManagement'));
const CSATDashboard = lazy(() => import('../components/CSATDashboard'));
const CSATHome = lazy(() => import('../components/CSATHome'));
const CSATConfig = lazy(() => import('../components/CSATConfig'));
const ChatbotManager = lazy(() => import('../components/ChatbotManager'));
const ChatbotBuilder = lazy(() => import('../components/ChatbotBuilder'));
const PlanosPage = lazy(() => import('../components/PlanosPage'));
const RespostasRapidas = lazy(() => import('../components/RespostasRapidas'));
const GaleriaPage = lazy(() => import('../components/GaleriaPage'));
const IntegrationsPage = lazy(() => import('../components/IntegrationsPage'));
const IntegrationSettingsPage = lazy(() => import('../components/IntegrationSettingsPage'));
const MetaAnalyticsDashboard = lazy(() => import('../components/MetaAnalyticsDashboard'));
const ChannelsPage = lazy(() => import('../components/ChannelsPage'));
const ChannelConfigPage = lazy(() => import('../components/ChannelConfigPage'));
const ProfilePage = lazy(() => import('../components/ProfilePage'));
const MessageTemplatesPage = lazy(() => import('../components/MessageTemplatesPage'));
const AppearancePage = lazy(() => import('../components/AppearancePage'));
const ProviderDataForm = lazy(() => import('../components/ProviderDataForm'));
const ProviderScheduleForm = lazy(() => import('../components/ProviderScheduleForm'));
const AttendanceRulesHome = lazy(() => import('../components/AttendanceRulesHome'));
const AttendanceRulesSettings = lazy(() => import('../components/AttendanceRulesSettings'));
const AttendanceAutomationSettings = lazy(() => import('../components/AttendanceAutomationSettings'));
const AttendanceHolidaySettings = lazy(() => import('../components/AttendanceHolidaySettings'));

export default function ProvedorAppWrapper({ user: propUser, userRole, handleLogout, setWhatsappDisconnected }) {
  const { provedorId: provedorIdParam } = useParams();
  const location = useLocation();
  const navigate = useNavigate();
  const lastStatusRef = useRef(null);
  const refreshingRef = useRef(false);

  // Usar user do contexto (actualizado pelo refresh) em vez de apenas a prop
  const { user: authUser, refresh } = useAuth();
  const user = authUser || propUser;

  const resolvedProvedorId = React.useMemo(
    () => getEffectiveProvedorId(provedorIdParam, user),
    [provedorIdParam, user]
  );

  // Se o provedor não foi resolvido (base antiga / niohub sem FK), forçar refresh /me/
  // O backend persiste o provedor_id na FK ao responder → próxima renderização terá o id correcto
  useEffect(() => {
    if (resolvedProvedorId != null) return;
    if (refreshingRef.current) return;
    refreshingRef.current = true;
    refresh().then(updated => {
      refreshingRef.current = false;
      if (!updated) return;
      const pid = getEffectiveProvedorId(provedorIdParam, updated);
      if (!pid) return;
      const badPrefix = `/app/accounts/${provedorIdParam}`;
      const goodPrefix = `/app/accounts/${pid}`;
      if (location.pathname.startsWith(badPrefix)) {
        navigate(
          `${location.pathname.replace(badPrefix, goodPrefix)}${location.search || ''}`,
          { replace: true }
        );
      } else {
        navigate(`/app/accounts/${pid}/dashboard`, { replace: true });
      }
    });
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Corrigir URL quando provedorIdParam inválido mas resolvedProvedorId já conhecido
  useEffect(() => {
    if (resolvedProvedorId == null || provedorIdParam == null || provedorIdParam === '') return;
    const routeNum = parseRouteProvedorId(provedorIdParam);
    if (routeNum === resolvedProvedorId) return;
    const prefix = `/app/accounts/${provedorIdParam}`;
    if (!location.pathname.startsWith(prefix)) return;
    const nextPath = `${location.pathname.replace(prefix, `/app/accounts/${resolvedProvedorId}`)}${location.search || ''}`;
    const currentFull = `${location.pathname}${location.search || ''}`;
    if (nextPath !== currentFull) {
      navigate(nextPath, { replace: true });
    }
  }, [provedorIdParam, resolvedProvedorId, location.pathname, location.search, navigate]);

  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [sidebarCollapsed, setSidebarCollapsed] = useState(() => {
    const saved = localStorage.getItem('sidebarCollapsed');
    return saved === 'true';
  });
  const [showChangelog, setShowChangelog] = useState(false);
  const [showRemindersModal, setShowRemindersModal] = useState(false);
  const [selectedConversation, setSelectedConversation] = useState(null);

  useEffect(() => {
    setSidebarOpen(false);
  }, [location.pathname]);

  // Monitorar status do WhatsApp
  useEffect(() => {
    if (!resolvedProvedorId) return;
    let interval;
    const fetchStatus = async () => {
      try {
        const token = localStorage.getItem('auth_token');
        if (!token) return;
        const res = await fetch(`/api/canais/`, {
          headers: { 'Authorization': `Token ${token}` }
        });
        const data = await res.json();
        const whatsappSession = (data.results || data).find(c => c.tipo === 'whatsapp_session' && c.dados_extras?.instance_id);
        if (whatsappSession) {
          const statusRes = await fetch(`/api/whatsapp/session/status/${whatsappSession.id}/`, {
            method: 'POST',
            headers: { 'Authorization': `Token ${token}` }
          });
          const statusData = await statusRes.json();
          if (statusData.status === 'connected' && statusData.loggedIn) {
            lastStatusRef.current = 'connected';
          }
          if (
            (lastStatusRef.current === 'connected' && (statusData.status === 'disconnected' || !statusData.loggedIn)) ||
            (lastStatusRef.current === null && (statusData.status === 'disconnected' || !statusData.loggedIn))
          ) {
            setWhatsappDisconnected(true);
            lastStatusRef.current = 'disconnected';
          }
        }
      } catch (e) {
        // Silenciar erros
      }
    };
    fetchStatus();
    interval = setInterval(fetchStatus, 30000);
    return () => clearInterval(interval);
  }, [resolvedProvedorId, setWhatsappDisconnected]);

  // Proteção de rotas baseada no papel do usuário
  const isAdminRoute = (path) => {
    const adminRoutes = ['dashboard', 'users', 'equipes', 'audit', 'companies', 'integracoes', 'dados-provedor', 'horario-provedor', 'regras-atendimento', 'marketing', 'campanhas'];
    return adminRoutes.some(route => path.includes(route));
  };

  // Enquanto aguarda o refresh do provedor, mostrar loading
  if (resolvedProvedorId == null) {
    return <LoadingBar />;
  }

  if (userRole === 'agent' && isAdminRoute(location.pathname)) {
    return <Navigate to={`/${resolvedProvedorId}/chat`} replace />;
  }

  const handleChangelog = () => {
    setShowChangelog(true);
  };

  const handleNotifications = () => {
    // Placeholder
  };

  return (
    <div className="fixed inset-0 bg-background text-foreground flex overflow-hidden w-full">
      <Sidebar
        userRole={userRole}
        userPermissions={user?.permissions || []}
        provedorId={resolvedProvedorId}
        mobileOpen={sidebarOpen}
        onClose={() => setSidebarOpen(false)}
        onCollapseChange={setSidebarCollapsed}
        onRemindersClick={() => setShowRemindersModal(true)}
      />
      <div className="flex-1 flex flex-col overflow-hidden min-w-0 w-full h-full">
        <Topbar
          onLogout={handleLogout}
          onChangelog={handleChangelog}
          onNotifications={handleNotifications}
          onMenuClick={() => setSidebarOpen(true)}
        />
        <div className="flex-1 overflow-y-auto w-full overflow-x-hidden min-h-0 relative">
          <div className="w-full h-full">
            <Suspense fallback={<LoadingBar />}>
              <Routes>
                <Route path="dashboard" element={<DashboardPrincipal provedorId={resolvedProvedorId} />} />
                <Route path="conversas" element={<ConversasDashboard provedorId={resolvedProvedorId} />} />
                <Route path="conversas-dashboard" element={<ConversasDashboard provedorId={resolvedProvedorId} />} />
                <Route path="contacts" element={<Contacts provedorId={resolvedProvedorId} />} />
                <Route path="reports" element={<DashboardPrincipal provedorId={resolvedProvedorId} />} />
                <Route path="settings" element={<Settings provedorId={resolvedProvedorId} />} />
                <Route path="users" element={<UserManagement provedorId={resolvedProvedorId} />} />
                <Route path="equipes" element={<TeamsPage />} />
                <Route path="audit" element={<ConversationAudit provedorId={resolvedProvedorId} />} />
                <Route path="recovery" element={<AIPerformancePage provedorId={resolvedProvedorId} />} />
                <Route path="marketing" element={<MarketingStudioPage provedorId={resolvedProvedorId} />} />
                <Route path="suggestions" element={<SuggestionsPage provedorId={resolvedProvedorId} />} />
                <Route path="companies" element={<CompanyManagement provedorId={resolvedProvedorId} />} />
                <Route path="csat" element={<CSATHome provedorId={resolvedProvedorId} />} />
                <Route path="csat/avaliacoes" element={<CSATDashboard provedorId={resolvedProvedorId} />} />
                <Route path="csat/configurar" element={<CSATConfig provedorId={resolvedProvedorId} />} />
                <Route path="chatbot-manager" element={<ChatbotManager />} />
                <Route path="chatbot-builder" element={<ChatbotBuilder />} />
                <Route path="chatbot-builder/:flowId" element={<ChatbotBuilder />} />
                <Route path="planos" element={<PlanosPage provedorId={resolvedProvedorId} />} />
                <Route path="respostas-rapidas" element={<RespostasRapidas provedorId={resolvedProvedorId} />} />
                <Route path="galeria" element={<GaleriaPage provedorId={resolvedProvedorId} />} />
                <Route path="integracoes" element={<IntegrationsPage />} />
                <Route
                  path="integracoes/agente-ia"
                  element={<IntegrationSettingsPage provedorId={resolvedProvedorId} section="ai" />}
                />
                <Route
                  path="integracoes/erp"
                  element={<IntegrationSettingsPage provedorId={resolvedProvedorId} section="erp" />}
                />
                <Route
                  path="integracoes/acs"
                  element={<IntegrationSettingsPage provedorId={resolvedProvedorId} section="acs" />}
                />
                <Route
                  path="integracoes/asaas"
                  element={<IntegrationSettingsPage provedorId={resolvedProvedorId} section="asaas" />}
                />
                <Route path="integracoes/meta" element={<MetaAnalyticsDashboard />} />
                <Route path="canais" element={<ChannelsPage />} />
                <Route path="canais/configurar" element={<ChannelConfigPage />} />
                <Route path="canais/templates" element={<MessageTemplatesPage provedorId={resolvedProvedorId} />} />
                <Route path="campanhas" element={<CampaignsPage provedorId={resolvedProvedorId} />} />
                <Route path="perfil" element={<ProfilePage provedorId={resolvedProvedorId} />} />
                <Route path="aparencia" element={<AppearancePage provedorId={resolvedProvedorId} />} />
                <Route path="dados-provedor" element={<ProviderDataForm provedorId={resolvedProvedorId} />} />
                <Route path="horario-provedor" element={<Navigate to="regras-atendimento/horario-comercial" replace />} />
                <Route path="regras-atendimento" element={<AttendanceRulesHome provedorId={resolvedProvedorId} />} />
                <Route path="regras-atendimento/horario-comercial" element={<ProviderScheduleForm provedorId={resolvedProvedorId} />} />
                <Route path="regras-atendimento/automacao" element={<AttendanceAutomationSettings provedorId={resolvedProvedorId} />} />
                <Route path="regras-atendimento/feriados" element={<AttendanceHolidaySettings provedorId={resolvedProvedorId} />} />
                <Route path="regras-atendimento/geral" element={<AttendanceRulesSettings provedorId={resolvedProvedorId} />} />
                <Route path="contrato-suspenso" element={<Navigate to="regras-atendimento/geral" replace />} />
                <Route path="conversations" element={<Navigate to={`/${resolvedProvedorId}/chat`} replace />} />
                <Route path="*" element={<Navigate to={`/app/accounts/${resolvedProvedorId}/dashboard`} replace />} />
              </Routes>
            </Suspense>
          </div>
        </div>
      </div>
      <Changelog isOpen={showChangelog} onClose={() => setShowChangelog(false)} />
      <RemindersModal
        isOpen={showRemindersModal}
        onClose={() => setShowRemindersModal(false)}
        provedorId={resolvedProvedorId}
      />
    </div>
  );
}
