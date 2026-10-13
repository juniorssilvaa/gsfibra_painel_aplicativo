import React, { useEffect, useState } from 'react';
import { ClipboardList, Sun, Moon, Menu } from 'lucide-react';
import InternalChatButton from './InternalChatButton';
import NotificationBell from './NotificationBell';
import StatusDot from './StatusDot';
import SupportNiohubBadge from './SupportNiohubBadge';
import { useLanguage } from '../contexts/LanguageContext';
import { useAuth } from '../contexts/AuthContext';

export default React.memo(function Topbar({ onLogout, onChangelog, onNotifications, onMenuClick }) {
  const [theme, setTheme] = useState(() => localStorage.getItem('theme') || 'dark');
  const [isMobile, setIsMobile] = useState(false);
  const { t } = useLanguage();
  const { user: authUser } = useAuth();

  const supportUsername = authUser?.username || (() => {
    try {
      const raw = localStorage.getItem('user');
      if (!raw) return '';
      return JSON.parse(raw)?.username || '';
    } catch {
      return '';
    }
  })();

  useEffect(() => {
    if (theme === 'dark') {
      document.documentElement.classList.add('dark');
    } else {
      document.documentElement.classList.remove('dark');
    }
    localStorage.setItem('theme', theme);
    window.dispatchEvent(new Event('niohub-theme-change'));
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

      <div className={`flex items-center gap-4 flex-shrink-0 ${isMobile ? 'pl-12 md:pl-0' : ''}`}>
      <div className="flex items-center gap-2 flex-shrink-0" title="Estado do backend / suporte">
        <SupportNiohubBadge username={supportUsername} />
        <StatusDot className="flex-shrink-0" />
      </div>

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
        type="button"
        className="px-2 py-1.5 rounded-lg text-sm font-semibold text-nowrap transition-colors text-topbar-foreground hover:bg-sidebar-accent hover:text-sidebar-accent-foreground"
        onClick={onLogout}
      >
        {t('sair')}
      </button>
      </div>
    </div>
  );
});
