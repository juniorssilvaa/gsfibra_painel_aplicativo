import React, { useState, useRef, useEffect, useCallback, Suspense, lazy, useMemo } from 'react';
import { useParams, useNavigate, useLocation } from 'react-router-dom';
import axios from 'axios';
import { ArrowLeft, Sun, Moon, ClipboardList, User } from 'lucide-react';
import ConversationList from './ConversationList';
import InternalChatButton from './InternalChatButton';
import NotificationBell from './NotificationBell';
import StatusDot from './StatusDot';
import SupportNiohubBadge from './SupportNiohubBadge';
import Sidebar from './Sidebar';
import RemindersModal from './RemindersModal';
import ChatArea from './ChatArea';
import { consumeResumeAfterUpdate } from './MaintenanceGate';
import { useAuth } from '../contexts/AuthContext';
import { getEffectiveProvedorId } from '../utils/effectiveProvedorId';
import { isSupervisorMonitoring } from '../utils/conversationSupervision';
import { useLanguage } from '../contexts/LanguageContext';
import logoImage from '../assets/logo.png';
import logoMini from '../assets/logo.png'; // Usar o mesmo logo por enquanto

const Contacts = lazy(() => import('./Contacts2'));
const Changelog = lazy(() => import('./Changelog'));
const UserStatusManager = lazy(() => import('./UserStatusManager'));

const ConversationsPage = ({ selectedConversation: propSelectedConversation, setSelectedConversation: propSetSelectedConversation, provedorId: propProvedorId, user: propUser }) => {
  const { provedorId: urlProvedorId } = useParams();
  const navigate = useNavigate();
  const location = useLocation();
  const { logout, user: authUser } = useAuth();
  const { t } = useLanguage();
  const isContactsView = React.useMemo(() => {
    const searchParams = new URLSearchParams(location.search);
    return searchParams.get('view') === 'contacts';
  }, [location.search]);

  const [theme, setTheme] = useState(() => localStorage.getItem('theme') || 'dark');
  const [showChangelog, setShowChangelog] = useState(false);
  const [showReminders, setShowReminders] = useState(false);
  const [isSidebarCollapsed, setIsSidebarCollapsed] = useState(() => localStorage.getItem('sidebarCollapsed') === 'true');

  useEffect(() => {
    if (theme === 'dark') {
      document.documentElement.classList.add('dark');
    } else {
      document.documentElement.classList.remove('dark');
    }
    localStorage.setItem('theme', theme);
    window.dispatchEvent(new Event('niohub-theme-change'));
  }, [theme]);

  const toggleTheme = () => {
    setTheme((prev) => (prev === 'dark' ? 'light' : 'dark'));
  };

  const handleLogout = () => {
    logout();
    navigate('/login');
  };

  const [internalSelectedConversation, setInternalSelectedConversation] = useState(null);
  const [listActiveTab, setListActiveTab] = useState('mine');
  
  // Usar props se existirem, senão usar estado interno
  const selectedConversation = propSelectedConversation !== undefined ? propSelectedConversation : internalSelectedConversation;
  const setSelectedConversation = propSetSelectedConversation || setInternalSelectedConversation;

  const refreshConversationsRef = useRef(null);
  const [localUser, setLocalUser] = useState(null);
  const [loadingUser, setLoadingUser] = useState(!propUser);
  
  // Usar o usuário da prop se disponível, senão local ou contexto (niohub /me com provedor resolvido)
  const user = propUser || localUser || authUser;
  const provedorId = useMemo(
    () => getEffectiveProvedorId(propProvedorId || urlProvedorId, user),
    [propProvedorId, urlProvedorId, user]
  );

  const supervisorMode = useMemo(
    () => isSupervisorMonitoring(selectedConversation, user, listActiveTab),
    [selectedConversation, user, listActiveTab]
  );

  const handleListActiveTabChange = useCallback((tabId) => {
    setListActiveTab(tabId || 'mine');
  }, []);
  
  // Buscar dados do usuário logado se não vier por prop
  useEffect(() => {
    if (propUser) {
      setLoadingUser(false);
      return;
    }

    const fetchUser = async () => {
      try {
        const token = localStorage.getItem('auth_token') || localStorage.getItem('token');
        if (token) {
          const response = await axios.get('/api/auth/me/', {
            headers: { Authorization: `Token ${token}` }
          });
          setLocalUser(response.data);
        }
      } catch (error) {
      } finally {
        setLoadingUser(false);
      }
    };
    
    fetchUser();
  }, [propUser]);

  useEffect(() => {
    const handlePermissionsUpdate = () => {
      // Se tiver propUser, o App.jsx deve lidar com isso, mas vamos atualizar o local por garantia
      const token = localStorage.getItem('auth_token') || localStorage.getItem('token');
      if (token) {
        axios.get('/api/auth/me/', {
          headers: { Authorization: `Token ${token}` }
        }).then(res => setLocalUser(res.data));
      }
    };

    window.addEventListener('userPermissionsUpdated', handlePermissionsUpdate);
    return () => {
      window.removeEventListener('userPermissionsUpdated', handlePermissionsUpdate);
    };
  }, []);

  // Não restaurar chat do localStorage: ao atualizar a página ou voltar do dashboard,
  // o atendimento começa sem conversa aberta. Exceção: reload automático pós-atualização
  // do sistema, que reabre a conversa em que o atendente estava.
  useEffect(() => {
    localStorage.removeItem('selectedConversation');
    const resumeId = consumeResumeAfterUpdate()?.conversationId;
    if (!resumeId) return;
    axios.get(`/api/conversations/${resumeId}/`, { skipErrorToast: true })
      .then(({ data }) => {
        if (!data?.id) return;
        const status = data.status || data.additional_attributes?.status;
        if (['closed', 'encerrada', 'resolved', 'finalizada'].includes(status)) return;
        setSelectedConversation(data);
        localStorage.setItem('selectedConversation', JSON.stringify(data));
      })
      .catch(() => {});
  }, []);

  // Ao sair da tela de atendimento ou abrir Contatos, limpar a conversa aberta
  useEffect(() => {
    if (isContactsView) {
      setSelectedConversation(null);
      localStorage.removeItem('selectedConversation');
    }
  }, [isContactsView, setSelectedConversation]);

  useEffect(() => {
    return () => {
      setSelectedConversation(null);
      localStorage.removeItem('selectedConversation');
    };
  }, [setSelectedConversation]);

  const handleConversationClose = useCallback(() => {
    setSelectedConversation(null);
    localStorage.removeItem('selectedConversation');
    // Recarregar lista de conversas
    if (refreshConversationsRef.current) {
      refreshConversationsRef.current();
    }
  }, [setSelectedConversation]);

  const handleConversationUpdate = useCallback((refreshFunction) => {
    // CORREÇÃO: Se recebeu null, limpar seleção
    if (refreshFunction === null) {
      setSelectedConversation(null);
      localStorage.removeItem('selectedConversation');
      // Forçar atualização da lista de conversas
      if (refreshConversationsRef.current) {
        refreshConversationsRef.current();
      }
      return;
    }
    
    // Se recebeu uma função, armazenar para uso posterior
    if (typeof refreshFunction === 'function') {
      refreshConversationsRef.current = refreshFunction;
    } 
    // LOG DE DEBUG PARA RASTREAR TROCAS AUTOMÁTICAS (REFRESH)
    if (refreshFunction && typeof refreshFunction === 'object') {
       const incomingId = String(refreshFunction.id);
       const currentId = selectedConversation ? String(selectedConversation.id) : null;
       
       const status = refreshFunction.status || refreshFunction.additional_attributes?.status;
       const closedStatuses = ['closed', 'encerrada', 'resolved', 'finalizada'];

       if (closedStatuses.includes(status)) {
         if (currentId === incomingId) {
           setSelectedConversation(null);
           localStorage.removeItem('selectedConversation');
         }
       } else {
         // SÓ ATUALIZAR SE OS IDs FORAREM IDÊNTICOS
         // Isso impede que mensagens de outros contatos troquem a sua tela atual
         if (currentId === incomingId) {
           setSelectedConversation(refreshFunction);
           localStorage.setItem('selectedConversation', JSON.stringify(refreshFunction));
         } else {
           // NÃO FAZER NADA com a seleção se os IDs não batem
           // apenas o refresh da lista abaixo cuidará de subir o contato no menu lateral
         }
       }
    }
    
    // Forçar atualização da lista de conversas para refletir nova mensagem e nova ordem
    if (refreshConversationsRef.current) {
      refreshConversationsRef.current();
    }
  }, [selectedConversation, setSelectedConversation]);

  if (loadingUser) {
    return (
      <div className="flex-1 flex items-center justify-center bg-background h-screen">
        <div className="text-center">
          <div className="w-12 h-12 border-4 border-primary border-t-transparent rounded-full animate-spin mx-auto mb-4" />
          <p className="text-muted-foreground">Carregando dados do usuário...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="flex h-screen w-screen overflow-hidden bg-background">
      {/* Sidebar dedicada para Agente */}
      <Sidebar 
        userRole={user?.user_type || 'agent'} 
        userPermissions={user?.permissions || []}
        provedorId={provedorId}
        onCollapseChange={(collapsed) => setIsSidebarCollapsed(collapsed)}
        onRemindersClick={() => setShowReminders(true)}
        isChatPage={true}
      />

      <div className="flex flex-col flex-1 min-w-0 transition-all duration-300">
        {/* Barra de Topo Padronizada (Igual ao Dashboard) */}
        <div className="w-full flex items-center justify-end bg-topbar text-topbar-foreground px-6 py-2 border-b border-border relative z-10">
          <div className="flex items-center gap-4 flex-shrink-0">
            <div className="flex items-center gap-2 flex-shrink-0" title="Estado do backend / suporte">
              <SupportNiohubBadge username={user?.username} />
              <StatusDot className="flex-shrink-0" />
            </div>

            <button
              className="p-2 rounded-lg transition-colors text-topbar-foreground hover:bg-sidebar-accent"
              title={t('alternar_tema')}
              onClick={toggleTheme}
            >
              {theme === 'dark' ? <Moon className="w-5 h-5" /> : <Sun className="w-5 h-5" />}
            </button>

            <InternalChatButton />

            <button
              className="p-2 rounded-lg transition-colors text-topbar-foreground hover:bg-sidebar-accent"
              title={t('changelog')}
              onClick={() => setShowChangelog(true)}
            >
              <ClipboardList className="w-5 h-5" />
            </button>

            <NotificationBell />

            <button
              type="button"
              className="px-2 py-1.5 rounded-lg text-sm font-semibold text-nowrap transition-colors text-topbar-foreground hover:bg-sidebar-accent hover:text-sidebar-accent-foreground"
              onClick={handleLogout}
            >
              {t('sair')}
            </button>
          </div>
        </div>

        <div className="flex h-full overflow-hidden min-w-0">
          {isContactsView ? (
            <div className="flex-1 min-w-0 h-full overflow-y-auto">
              <Suspense fallback={<div className="flex-1 flex items-center justify-center bg-background h-screen"><div className="w-12 h-12 border-4 border-primary border-t-transparent rounded-full animate-spin" /></div>}>
                <Contacts provedorId={provedorId} />
              </Suspense>
            </div>
          ) : (
            <>
              <ConversationList
                onConversationSelect={(conversation) => {
                  setSelectedConversation(conversation);
                  // Salvar no localStorage
                  localStorage.setItem('selectedConversation', JSON.stringify(conversation));
                }}
                selectedConversation={selectedConversation}
                provedorId={provedorId}
                onConversationUpdate={handleConversationUpdate}
                onActiveTabChange={handleListActiveTabChange}
                user={user}
              />
              {selectedConversation ? (
                  <ChatArea
                    conversation={selectedConversation}
                    onConversationClose={handleConversationClose}
                    onConversationUpdate={handleConversationUpdate}
                    user={user}
                    supervisorMode={supervisorMode}
                  />
              ) : (
                <div className="flex-1 flex items-center justify-center bg-background">
                  <div className="text-center max-w-md mx-auto px-4">
                    {/* Logo do NioChat */}
                    <div className="mb-6">
                      <img 
                        src={logoImage}
                        alt="NioChat Logo"
                        className="w-32 h-32 mx-auto object-contain"
                      />
                    </div>
                    
                    {/* Texto principal */}
                    <p className="text-base text-foreground mb-2">
                      Selecione uma conversa para iniciar o atendimento
                    </p>
                    
                    {/* Texto explicativo */}
                    <p className="text-sm text-muted-foreground leading-relaxed">
                      Os atendimentos em andamento aparecerão aqui.
                    </p>
                  </div>
                </div>
              )}
            </>
          )}
        </div>
      </div>
      <Suspense fallback={null}>
        <Changelog isOpen={showChangelog} onClose={() => setShowChangelog(false)} />
      </Suspense>
      <RemindersModal isOpen={showReminders} onClose={() => setShowReminders(false)} provedorId={provedorId} />
    </div>
  );
};

const ConversationsPageWrapper = (props) => {
  return (
    <Suspense fallback={<div className="flex h-screen items-center justify-center bg-background"><div className="w-12 h-12 border-4 border-primary border-t-transparent rounded-full animate-spin" /></div>}>
      <ConversationsPage {...props} />
    </Suspense>
  );
};

export default ConversationsPageWrapper;
