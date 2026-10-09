import React, { useState, useEffect, createContext, useContext } from 'react';
import { useNavigate, useLocation, Link } from 'react-router-dom';
import {
  MessageCircle,
  Users,
  Shield,
  Settings,
  LayoutGrid,
  Clock,
  User,
  MessagesSquare, // Ícone para Conversas
  UserCog, // Ícone para Equipes
  Notebook, // Ícone para Contatos
  Headphones, // Ícone para Atendimento
  Brain, // Ícone para Desempenho da IA
  Lightbulb, // Ícone para Sugestões
  Smile, // Ícone para CSAT
  PlugZap, // Ícone para Integrações
  ScrollText, // Ícone para Auditoria
  Bot, // Ícone para Construtor de Chatbot
  Wifi, // Ícone para Planos
  ChevronsLeft,
  ChevronsRight,
  Zap, // Ícone para Respostas Rápidas
  Image as ImageIcon,
  Globe, // Ícone para Canais
  SlidersHorizontal, // Regras de atendimento
  Sparkles, // Estúdio de Marketing
  Megaphone, // Campanhas
} from 'lucide-react';
import logo from '../assets/logo.png';
import { useLanguage } from '../contexts/LanguageContext';
import FlowIcon from './icons/FlowIcon';
import useAgentMode from '../hooks/useAgentMode';

// Context para compartilhar estado do sidebar
const SidebarContext = createContext({
  isCollapsed: false,
  setIsCollapsed: () => { }
});

export const useSidebarContext = () => useContext(SidebarContext);

const NewBadge = () => (
  <span className="inline-block align-middle ml-1.5 px-1.5 py-0.5 rounded bg-green-500 text-white text-[10px] font-bold uppercase leading-none whitespace-nowrap">
    Novo
  </span>
);

const Sidebar = React.memo(({ userRole = 'agent', userPermissions = [], mobileOpen, onClose, provedorId, onCollapseChange, onRemindersClick, isChatPage = false }) => {
  const navigate = useNavigate();
  const location = useLocation();
  const currentPath = location.pathname;
  const currentSearch = location.search;
  const resolvedProvedorId = React.useMemo(() => {
    if (provedorId) return provedorId;

    // Suporta rotas /app/accounts/:provedorId/* e /:provedorId/chat
    const accountMatch = currentPath.match(/^\/app\/accounts\/([^/]+)/);
    if (accountMatch?.[1]) return accountMatch[1];

    const chatMatch = currentPath.match(/^\/([^/]+)\/chat/);
    if (chatMatch?.[1]) return chatMatch[1];

    return null;
  }, [provedorId, currentPath]);
  const [isCollapsed, setIsCollapsed] = useState(() => {
    const saved = localStorage.getItem('sidebarCollapsed');
    return saved === 'true';
  });
  const { t } = useLanguage();
  const agentMode = useAgentMode();

  // Salvar estado no localStorage e notificar componente pai
  useEffect(() => {
    localStorage.setItem('sidebarCollapsed', isCollapsed.toString());
    if (onCollapseChange) {
      onCollapseChange(isCollapsed);
    }
  }, [isCollapsed, onCollapseChange]);

  // Função para verificar se um item do menu está ativo
  const isActive = (item) => {
    if (item?.id === 'csat' && resolvedProvedorId) {
      return currentPath.startsWith(`/app/accounts/${resolvedProvedorId}/csat`);
    }
    if (isChatPage && item.id === 'contacts') {
      const searchParams = new URLSearchParams(currentSearch);
      return searchParams.get('view') === 'contacts';
    }

    if (isChatPage && item.id === 'atendimento') {
      const searchParams = new URLSearchParams(currentSearch);
      return currentPath === `/${resolvedProvedorId}/chat` && !searchParams.get('view');
    }

    return currentPath === item.path;
  };

  // Menu base com todos os itens - Memoizado para evitar recalculação
  const menuItems = React.useMemo(() => {
    const contactsPath = isChatPage
      ? `/${resolvedProvedorId}/chat?view=contacts`
      : `/app/accounts/${resolvedProvedorId}/contacts`;

    const allMenuItems = [
      { id: 'dashboard', icon: LayoutGrid, label: t('dashboard'), path: `/app/accounts/${resolvedProvedorId}/dashboard` },
      { id: 'atendimento', icon: Headphones, label: 'Atendimento', path: `/${resolvedProvedorId}/chat` },
      { id: 'conversas', icon: MessagesSquare, label: 'Conversas', path: `/app/accounts/${resolvedProvedorId}/conversas` },
      { id: 'reminders', icon: Clock, label: 'Lembretes', path: '#', onClick: onRemindersClick },
      { id: 'contacts', icon: Notebook, label: t('contacts'), path: contactsPath, permission: 'manage_contacts' },
      { id: 'users', icon: Users, label: t('users'), path: `/app/accounts/${resolvedProvedorId}/users` },
      { id: 'teams', icon: UserCog, label: t('equipes'), path: `/app/accounts/${resolvedProvedorId}/equipes` },
      { id: 'audit', icon: ScrollText, label: t('audit'), path: `/app/accounts/${resolvedProvedorId}/audit` },
      { id: 'chatbot-builder', icon: FlowIcon, label: 'Fluxo de Atendimento', path: `/app/accounts/${resolvedProvedorId}/chatbot-manager` },
      { id: 'planos', icon: Wifi, label: t('planos'), path: `/app/accounts/${resolvedProvedorId}/planos` },
      { id: 'csat', icon: Smile, label: t('csat'), path: `/app/accounts/${resolvedProvedorId}/csat` },
      { id: 'respostas-rapidas', icon: Zap, label: 'Respostas Rápidas', path: `/app/accounts/${resolvedProvedorId}/respostas-rapidas` },
      { id: 'galeria', icon: ImageIcon, label: 'Galeria', path: `/app/accounts/${resolvedProvedorId}/galeria` },
      ...(agentMode === 'support'
        ? [{ id: 'marketing', icon: Sparkles, label: 'Estúdio de Marketing', path: `/app/accounts/${resolvedProvedorId}/marketing`, isNew: true }]
        : []),
      { id: 'canais', icon: Globe, label: 'Canais', path: `/app/accounts/${resolvedProvedorId}/canais` },
      { id: 'campanhas', icon: Megaphone, label: 'Campanhas', path: `/app/accounts/${resolvedProvedorId}/campanhas`, isNew: true },
    ];

    let items = [];
    if (userRole === 'superadmin') {
      // No painel do tenant não listar link para a app Superadmin (evita confusão com suporte niohub).
      if (isChatPage) {
        items = allMenuItems.filter(item => ['dashboard', 'atendimento', 'reminders', 'contacts'].includes(item.id));
      } else {
        items = allMenuItems;
      }
    } else if (userRole === 'admin') {
      if (isChatPage) {
        items = allMenuItems.filter(item => ['dashboard', 'atendimento', 'reminders', 'contacts'].includes(item.id));
      } else {
        items = allMenuItems;
      }
    } else if (userRole === 'agent') {
      items = allMenuItems.filter(item => {
        return ['atendimento', 'reminders', 'contacts'].includes(item.id);
      });
    } else {
      items = allMenuItems.filter(item => item.id === 'dashboard');
    }
    return items;
  }, [userRole, userPermissions, resolvedProvedorId, t, onRemindersClick, isChatPage, agentMode]);

  // Itens fixos - Memoizado
  const fixedItems = React.useMemo(() => {
    const allFixedItems = [
      { id: 'regras-atendimento', icon: SlidersHorizontal, label: t('regras_atendimento'), path: `/app/accounts/${resolvedProvedorId}/regras-atendimento` },
      { id: 'integracoes', icon: PlugZap, label: t('integracoes'), path: `/app/accounts/${resolvedProvedorId}/integracoes` },
      { id: 'dados-provedor', icon: Settings, label: t('dados_provedor'), path: `/app/accounts/${resolvedProvedorId}/dados-provedor` },
      { id: 'recovery', icon: Brain, label: t('recovery'), path: `/app/accounts/${resolvedProvedorId}/recovery`, isNew: true },
      { id: 'suggestions', icon: Lightbulb, label: t('suggestions'), path: `/app/accounts/${resolvedProvedorId}/suggestions` },
      { id: 'perfil', icon: User, label: t('perfil'), path: `/app/accounts/${resolvedProvedorId}/perfil` },
    ];

    if (userRole === 'agent') {
      return [
        { id: 'suggestions', icon: Lightbulb, label: t('suggestions'), path: `/app/accounts/${resolvedProvedorId}/suggestions` },
        { id: 'perfil', icon: User, label: t('perfil'), path: `/app/accounts/${resolvedProvedorId}/perfil` },
      ];
    }
    
    if (userRole === 'admin' && isChatPage) {
      return []; // Ocultar no modo chat conforme pedido: "não precisar mostra o botão perfil"
    }
    
    return allFixedItems;
  }, [userRole, resolvedProvedorId, t, isChatPage]);

  // Detectar se está em mobile
  const [isMobile, setIsMobile] = useState(false);
  useEffect(() => {
    const checkMobile = () => setIsMobile(window.innerWidth <= 768);
    checkMobile();
    window.addEventListener('resize', checkMobile);
    return () => window.removeEventListener('resize', checkMobile);
  }, []);

  // Componente de item do menu
  const MenuItem = ({ item, onClick }) => {
    const Icon = item.icon;
    const active = isActive(item);
    const iconSizeClass = item.id === 'chatbot-builder' ? 'w-6 h-6' : 'w-5 h-5';
    return (
      <li>
        <button
          onClick={item.onClick || onClick}
          className={`niochat-sidebar-item ${active ? 'niochat-sidebar-item-active' : ''}`}
        >
          <Icon className={iconSizeClass} />
          <span className={`flex-1 text-left ${isCollapsed ? 'hidden' : ''}`}>
            {item.label}
            {item.isNew && <NewBadge />}
          </span>
          {item.session && (
            <span className={`px-2 py-1 text-xs font-medium bg-green-500 text-white rounded-full ${isCollapsed ? 'hidden' : ''}`}>
              session
            </span>
          )}
        </button>
      </li>
    );
  };

  // Overlay para mobile
  if (isMobile) {
    return (
      <>
        <div
          className={`fixed inset-0 z-40 bg-black bg-opacity-40 transition-opacity ${mobileOpen ? 'block' : 'hidden'}`}
          onClick={onClose}
        />
        <aside
          className={`fixed top-0 left-0 z-50 h-full w-64 niochat-sidebar shadow-lg transform transition-transform duration-300 ${mobileOpen ? 'translate-x-0' : '-translate-x-full'}`}
        >
          <div className="p-4 flex items-center gap-3">
            <img
              src={logo}
              alt="NIO HUB"
              className="h-14 w-auto max-w-[calc(100%-3rem)] object-contain object-left translate-x-1"
            />
            <button className="ml-auto p-2 shrink-0" onClick={onClose} aria-label="Fechar menu">
              <span style={{ fontSize: 24, fontWeight: 'bold' }}>&times;</span>
            </button>
          </div>
          <nav className="niochat-sidebar-nav">
            <ul className="niochat-sidebar-menu">
              {menuItems.map((item) => (
                <MenuItem
                  key={item.id}
                  item={item}
                  onClick={() => { 
                    if(item.id === 'reminders') {
                      item.onClick();
                    } else {
                      navigate(item.path);
                    }
                    onClose && onClose(); 
                  }}
                />
              ))}
            </ul>
            <ul className="niochat-sidebar-menu-fixed">
              {fixedItems.map((item) => (
                <MenuItem
                  key={item.id}
                  item={item}
                  onClick={() => { 
                    if(item.id === 'reminders' && item.onClick) {
                      item.onClick();
                    } else {
                      navigate(item.path);
                    }
                    onClose && onClose(); 
                  }}
                />
              ))}
            </ul>
          </nav>
        </aside>
      </>
    );
  }

  // Desktop: sidebar fixo
  return (
    <SidebarContext.Provider value={{ isCollapsed, setIsCollapsed }}>
      <aside className={`h-full ${isCollapsed ? 'w-14' : 'w-48'} z-30 flex-shrink-0 flex flex-col transition-all duration-300`}>
        <div className={`bg-sidebar text-sidebar-foreground border-r border-sidebar-border h-full flex flex-col ${mobileOpen ? 'mobile-open' : ''}`}>
          {/* TOPO FIXO - Logo e Botão */}
          <div className={`p-4 border-b border-border flex items-center flex-shrink-0 ${isCollapsed ? 'justify-center' : 'justify-between'}`}>
            <img
              src={logo}
              alt="NIO HUB"
              className={`h-14 w-auto max-w-[7.5rem] object-contain object-left translate-x-1 transition-opacity duration-300 ${isCollapsed ? 'hidden' : 'block'}`}
            />
            <button
              onClick={() => setIsCollapsed(!isCollapsed)}
              className="p-2 rounded-lg hover:bg-sidebar-accent transition-colors"
              aria-label={isCollapsed ? 'Expandir sidebar' : 'Recolher sidebar'}
            >
              {isCollapsed ? <ChevronsRight className="w-5 h-5" /> : <ChevronsLeft className="w-5 h-5" />}
            </button>
          </div>

          {/* CENTRO FLEXÍVEL - Menu Items com scroll */}
          <div className="flex-1 flex flex-col min-h-0">
            <nav className="flex-1 overflow-y-auto overflow-x-hidden p-2">
              <div className={isCollapsed ? 'space-y-3' : 'space-y-1'}>
                {menuItems.map((item) => {
                  const Icon = item.icon;
                  return item.id === 'reminders' ? (
                    <button
                      key={item.id}
                      onClick={item.onClick}
                      className={`w-full flex items-center ${isCollapsed ? 'justify-center' : 'justify-start'} gap-3 ${isCollapsed ? 'px-2' : 'px-4'} ${isCollapsed ? 'py-3' : 'py-2'} rounded-lg transition-colors text-sidebar-foreground hover:bg-sidebar-accent hover:text-sidebar-accent-foreground`}
                      title={isCollapsed ? item.label : ''}
                    >
                      <Icon className="w-5 h-5 flex-shrink-0" />
                      <span className={`transition-opacity duration-300 ${isCollapsed ? 'hidden' : 'inline'}`}>{item.label}</span>
                    </button>
                  ) : (
                    <Link
                      key={item.path}
                      to={item.path}
                      className={`flex items-center ${isCollapsed ? 'justify-center' : 'justify-start'} gap-3 ${isCollapsed ? 'px-2' : 'px-4'} ${isCollapsed ? 'py-3' : 'py-2'} rounded-lg transition-colors ${isActive(item)
                        ? 'bg-sidebar-accent text-sidebar-accent-foreground'
                        : 'text-sidebar-foreground hover:bg-sidebar-accent hover:text-sidebar-accent-foreground'
                        }`}
                      title={isCollapsed ? item.label : ''}
                    >
                      <Icon
                        className={`${
                          item.id === 'chatbot-builder' ? 'w-6 h-6' : 'w-5 h-5'
                        } flex-shrink-0`}
                      />
                      <span className={`transition-opacity duration-300 ${isCollapsed ? 'hidden' : 'inline'}`}>
                        {item.label}
                        {item.isNew && <NewBadge />}
                      </span>
                    </Link>
                  );
                })}
              </div>
            </nav>
          </div>

          {/* RODAPÉ FIXO - Fixed Items */}
          <div className="p-2 flex-shrink-0">
            <div className={isCollapsed ? 'space-y-3' : 'space-y-1'}>
              {fixedItems.map((item) => {
                const Icon = item.icon;
                  return (
                    <Link
                      key={item.path}
                      to={item.path}
                      className={`flex items-center ${isCollapsed ? 'justify-center' : 'justify-start'} gap-3 ${isCollapsed ? 'px-2' : 'px-4'} ${isCollapsed ? 'py-3' : 'py-2'} rounded-lg transition-colors ${isActive(item)
                        ? 'bg-sidebar-accent text-sidebar-accent-foreground'
                        : 'text-sidebar-foreground hover:bg-sidebar-accent hover:text-sidebar-accent-foreground'
                        }`}
                      title={isCollapsed ? item.label : ''}
                    >
                      <Icon className="w-5 h-5 flex-shrink-0" />
                      <span className={`transition-opacity duration-300 ${isCollapsed ? 'hidden' : 'inline'}`}>
                        {item.label}
                        {item.isNew && <NewBadge />}
                      </span>
                      {item.session && (
                        <span className={`px-2 py-1 text-xs font-medium bg-green-500 text-white rounded-full ml-auto transition-opacity duration-300 ${isCollapsed ? 'hidden' : 'inline'}`}>
                          {t('session')}
                        </span>
                      )}
                    </Link>
                  );
              })}
            </div>
          </div>
        </div>
      </aside>
    </SidebarContext.Provider>
  );
});

export default Sidebar;

