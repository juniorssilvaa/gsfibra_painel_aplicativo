import React from 'react';
import { 
  MessageCircle, 
  Users, 
  Shield, 
  Settings, 
  Crown,
  LayoutGrid,
  Clock,
  User,
  Plug
} from 'lucide-react';
import { Link, useLocation } from 'react-router-dom';

const Sidebar = () => {
  const location = useLocation();

  const menuItems = [
    { icon: <LayoutGrid className="w-5 h-5" />, label: 'Dashboard', path: '/app/dashboard' },
    { icon: <MessageCircle className="w-5 h-5" />, label: 'Atendimento', path: '/app/atendimento' },
    { icon: <Users className="w-5 h-5" />, label: 'Contatos', path: '/app/contatos' },
    { icon: <Shield className="w-5 h-5" />, label: 'Equipes', path: '/app/equipes' },
    { icon: <Clock className="w-5 h-5" />, label: 'Horário', path: '/app/horario' },
    { icon: <Plug className="w-5 h-5" />, label: 'Integrações', path: '/app/integracoes' },
    { icon: <Settings className="w-5 h-5" />, label: 'Configurações', path: '/app/config' },
  ];

  return (
    <aside className="flex flex-col justify-between h-screen bg-slate-900 text-slate-100 fixed left-0 top-0 w-64 border-r border-slate-800">
      
      {/* --- Parte superior: logo e menus --- */}
      <div className="flex flex-col flex-1 mt-6 overflow-y-auto">
        <div className="mb-8 text-center">
          <Link to="/app/dashboard" className="flex justify-center items-center">
            <Crown className="w-6 h-6 text-yellow-400 mr-2" />
            <span className="text-lg font-bold">NIO HUB</span>
          </Link>
        </div>

        <nav className="flex flex-col gap-1 px-4">
          {menuItems.map((item, index) => {
            const isActive = location.pathname === item.path;
            return (
              <Link
                key={index}
                to={item.path}
                className={`flex items-center gap-3 px-3 py-2 rounded-md transition-colors ${
                  isActive
                    ? 'bg-slate-800 text-white'
                    : 'text-slate-400 hover:bg-slate-800 hover:text-white'
                }`}
              >
                {item.icon}
                <span className="text-sm">{item.label}</span>
              </Link>
            );
          })}
        </nav>
      </div>

      {/* --- Rodapé fixo --- */}
      <div className="border-t border-slate-800 p-4 text-xs text-slate-400">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <User className="w-4 h-4 text-slate-500" />
            <span>Perfil</span>
          </div>
          <span className="text-slate-500">v2.23.3</span>
        </div>
      </div>
    </aside>
  );
};

export default Sidebar;
