import React, { useEffect, useRef, useState } from 'react';
import { useParams, Routes, Route, Navigate, useLocation } from 'react-router-dom';
import Sidebar from './components/Sidebar';
import Topbar from './components/Topbar';
import Dashboard from './components/Dashboard';
import DashboardPrincipal from './components/DashboardPrincipal';
import ConversasDashboard from './components/ConversasDashboard';
import Contacts from './components/Contacts2';
import ConversationList from './components/ConversationList';
import ChatArea from './components/ChatArea';
import ConversationsPage from './components/ConversationsPage';
import Settings from './components/Settings';
import UserManagement from './components/UserManagement';
import TeamsPage from './components/TeamsPage';
import AuditLog from './components/AuditLog';
import ConversationRecovery from './components/ConversationRecovery';
import CompanyManagement from './components/CompanyManagement';
import Integrations from './components/Integrations';
import ProfilePage from './components/ProfilePage';
import AppearancePage from './components/AppearancePage';
import ProviderDataForm from './components/ProviderDataForm';
import ProviderScheduleForm from './components/ProviderScheduleForm';
import ChatGPTTest from './components/ChatGPTTest';
import Changelog from './components/Changelog';

export default function ProvedorAppWrapper(props) {
  const { provedorId } = useParams();
  const location = useLocation();
  const lastStatusRef = useRef(null);
  const { setWhatsappDisconnected, userRole, user, handleLogout, handleChangelog, handleNotifications, selectedConversation, setSelectedConversation, providerMenu, setProviderMenu } = props;
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [showChangelog, setShowChangelog] = useState(false);

  const localHandleChangelog = () => {
    setShowChangelog(true);
  };

  // Resetar conversa selecionada ao trocar de rota
  useEffect(() => {
    setSelectedConversation(null);
  }, [location.pathname]);

  useEffect(() => { setSidebarOpen(false); }, [location.pathname]);

  useEffect(() => {
    if (!provedorId) return;
    let interval;
    const fetchStatus = async () => {
      try {
        const token = localStorage.getItem('token');
        const res = await fetch(`/api/canais/`, {
          headers: { 'Authorization': `Token ${token}` }
        });
        const data = await res.json();
        // Buscar sessão WhatsApp (Uazapi) - whatsapp_session é o valor do banco de dados
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
        // Se der erro, não faz nada
      }
    };
    fetchStatus();
    interval = setInterval(fetchStatus, 30000);
    return () => clearInterval(interval);
  }, [provedorId, setWhatsappDisconnected]);

  // Proteção de rotas baseada no papel do usuário
  const isAdminRoute = (path) => {
    const adminRoutes = ['users', 'equipes', 'audit', 'companies', 'integracoes', 'dados-provedor', 'horario-provedor', 'chatgpt-test'];
    return adminRoutes.some(route => path.includes(route));
  };
  if (userRole === 'agent' && isAdminRoute(location.pathname)) {
    return <Navigate to={`/app/accounts/${provedorId}/conversations`} replace />;
  }

  if (user?.role === 'agent' && location.pathname.endsWith('/dashboard')) {
    return <Navigate to={`/app/accounts/${provedorId}/conversations`} replace />;
  }

  // Proteção de rota para contatos
  if (location.pathname.startsWith('/contacts') && user?.role === 'agent' && !user?.permissions?.includes('manage_contacts')) {
    return <Navigate to={`/`} />;
  }

  // if (location.pathname.startsWith('/contacts') && !user?.permissions?.includes('manage_contacts')) {
  //   return <Navigate to={`/`} />;
  // }

  if (location.pathname.startsWith('/config') && user?.role === 'agent') {
    return <Navigate to={`/`} />;
  }
  
  // CRÍTICO: Se estamos em fluxo de integração, NUNCA redirecionar para dashboard
  // Verificar se a rota atual contém /integracoes
  const isIntegrationFlow = location.pathname.includes('/integracoes');
  if (isIntegrationFlow) {
    // Não redirecionar - deixar o usuário permanecer na página de integrações
    // Retornar null para não renderizar nada (o componente pai deve renderizar as rotas)
    return null;
  }
  
  // NOTA: Este componente parece estar incompleto ou não utilizado
  // O ProvedorAppWrapper real está definido em App.jsx
  // Se este arquivo estiver sendo usado, ele deveria renderizar as rotas, não redirecionar
  // Por segurança, não redirecionar se estiver em integrações
  return null;
}