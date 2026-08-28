import React, { useEffect, useState } from 'react';
import { ClipboardList, LogOut, Sun, Moon, Menu, MessageCircle } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import InternalChatButton from './InternalChatButton';
import NotificationBell from './NotificationBell';
import StatusDot from './StatusDot';
import { useLanguage } from '../contexts/LanguageContext';
export default React.memo(function Topbar({ onLogout, onChangelog, onNotifications, onMenuClick }) {
  const navigate = useNavigate();
  const [theme, setTheme] = useState(() => localStorage.getItem('theme') || 'dark');
  const [isMobile, setIsMobile] = useState(false);
  const { t } = useLanguage();

  useEffect(() => {
    if (theme === 'dark') {
      document.documentElement.classList.add('dark');
    } else {
      document.documentElement.classList.remove('dark');
    }
    localStorage.setItem('theme', theme);
  }, [theme]);

  useEffect(() => {
    const checkMobile = () => setIsMobile(window.innerWidth <= 768);
    checkMobile();
    window.addEventListener('resize', checkMobile);
    return () => window.removeEventListener('resize', checkMobile);
  }, []);

  const toggleTheme = () => {
    setTheme((prev) => (prev === 'dark' ? 'light' : 'dark'));
  };

  return (
    <div className="w-full flex items-center justify-end bg-topbar text-topbar-foreground px-6 py-2 border-b border-border gap-4 relative">
      {/* Botão de menu só no mobile */}
      {isMobile && (
        <button
          className="absolute left-4 top-1/2 transform -translate-y-1/2 p-2 rounded-lg transition-colors text-topbar-foreground hover:bg-sidebar-accent hover:text-sidebar-accent-foreground md:hidden z-50"
          title={t('abrir_menu')}
          onClick={onMenuClick}
        >
          <Menu className="w-6 h-6" />
        </button>
      )}
      {/* StatusDot - Indicador de status do backend */}
      <StatusDot className="flex-shrink-0" />

      <button
        className="p-2 rounded-lg transition-colors text-topbar-foreground hover:bg-sidebar-accent hover:text-sidebar-accent-foreground"
        title={t('alternar_tema')}
        onClick={toggleTheme}
      >
        {theme === 'dark' ? <Moon className="w-5 h-5" /> : <Sun className="w-5 h-5" />}
      </button>

      {/* Botão do Chat Interno */}
      <InternalChatButton />

      <button
        className="p-2 rounded-lg transition-colors text-topbar-foreground hover:bg-sidebar-accent hover:text-sidebar-accent-foreground"
        title={t('changelog')}
        onClick={onChangelog}
      >
        <ClipboardList className="w-5 h-5" />
      </button>
      {/* Sistema de Notificações do Superadmin */}
      <NotificationBell />
      <button
        className="p-2 rounded-lg transition-colors text-topbar-foreground hover:bg-sidebar-accent hover:text-sidebar-accent-foreground"
        title={t('sair')}
        onClick={onLogout}
      >
        <LogOut className="w-5 h-5" />
      </button>
    </div>
  );
});