import React, { useEffect, useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { LogIn, LogOut, Activity, Plus, Edit, Trash, MessageCircle, UserPlus, Settings, X } from "lucide-react";
import { format } from "date-fns";
import axios from "axios";
import { buildApiPath } from "@/utils/apiBaseUrl";

const HUMAN_ACTIONS = {
  login: 'entrou no sistema',
  logout: 'saiu do sistema',
  conversation_closed_ai: 'finalizou uma conversa com automação',
  conversation_closed_agent: 'finalizou uma conversa',
  conversation_closed_manual: 'finalizou uma conversa',
  conversation_closed_timeout: 'teve conversa finalizada por timeout',
  conversation_assigned: 'atribuiu uma conversa',
  create: 'criou um item no sistema',
  edit: 'editou um item no sistema',
  delete: 'excluiu um item do sistema',
  contact_created: 'adicionou um contato'
};

const extractUserName = (activity) => {
  if (typeof activity.user === 'string' && activity.user.trim()) {
    const userMatch = activity.user.match(/^([^(]+)/);
    return (userMatch ? userMatch[1] : activity.user).trim();
  }
  if (activity.user_name) return activity.user_name;
  return 'Usuário';
};

const getActivityType = (activity) => {
  const action = (activity.action || '').toLowerCase();
  if (action.includes('login')) return 'login';
  if (action.includes('logout')) return 'logout';
  if (action.includes('conversation_closed')) return 'encerramento';
  if (action.includes('create') || action.includes('contact_created')) return 'criacao';
  return 'outros';
};

const getBadgeStyle = (type) => {
  switch (type) {
    case 'login':
      return 'bg-emerald-500/15 text-emerald-300 border-emerald-500/30';
    case 'logout':
      return 'bg-amber-500/15 text-amber-300 border-amber-500/30';
    case 'encerramento':
      return 'bg-blue-500/15 text-blue-300 border-blue-500/30';
    case 'criacao':
      return 'bg-violet-500/15 text-violet-300 border-violet-500/30';
    default:
      return 'bg-zinc-500/15 text-zinc-300 border-zinc-500/30';
  }
};

const getBadgeLabel = (type) => {
  switch (type) {
    case 'login':
      return 'Login';
    case 'logout':
      return 'Logout';
    case 'encerramento':
      return 'Encerramento';
    case 'criacao':
      return 'Criação';
    default:
      return 'Atividade';
  }
};

export default function RecentActivity({ provedorId }) {
  const [activities, setActivities] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    async function fetchActivityData() {
      if (!provedorId) {
        setLoading(false);
        return;
      }
      
      try {
        // Priorizar auth_token que é o padrão salvo no Login, mas aceitar token também para compatibilidade
        const token = localStorage.getItem('auth_token') || localStorage.getItem('token');
        
        // Buscar logs de auditoria/atividade - buscar mais logs para garantir que pegamos login/logout
        const response = await axios.get(buildApiPath(`/api/audit-logs/?limit=120&provedor_id=${provedorId}`), {
          headers: {
            'Authorization': `Token ${token}`,
            'Content-Type': 'application/json'
          }
        });
        const data = response.data;
        const allActivities = data.results || data || [];

        const relevantActions = Object.keys(HUMAN_ACTIONS);
        const filteredActivities = allActivities
          .filter((activity) => {
            const action = (activity.action || '').toLowerCase();
            if (relevantActions.some((act) => action.includes(act))) return true;
            const detailsRaw = typeof activity.details === 'string'
              ? activity.details
              : JSON.stringify(activity.details || {});
            const details = detailsRaw.toLowerCase();
            return (
              details.includes('login') ||
              details.includes('logout') ||
              details.includes('conversa') ||
              details.includes('contato') ||
              details.includes('canal')
            );
          })
          .sort((a, b) => {
            const timeA = new Date(a.timestamp || a.created_at || a.event_at || 0);
            const timeB = new Date(b.timestamp || b.created_at || b.event_at || 0);
            return timeB - timeA;
          })
          .slice(0, 20);

        setActivities(filteredActivities);
        
        setLoading(false);
      } catch (error) {
        console.error('Erro ao buscar atividades:', error);
        setActivities([]);
        setLoading(false);
      }
    }

    fetchActivityData();
  }, [provedorId]);

  const getActivityIcon = (activity) => {
    const action = (activity.action || '').toLowerCase();
    
    // Converter details para string se for objeto
    let details = activity.details;
    if (typeof details === 'object') {
      details = JSON.stringify(details);
    }
    details = (details || '').toLowerCase();
    
    // Verificar primeiro se é um evento de login nos detalhes ou action
    if (details.includes('login bem-sucedido') || details.includes('tentativa de login') || 
        details.includes('usuário:') && details.includes('login') || action === 'login') {
      return <LogIn className="w-4 h-4 text-emerald-400" />;
    }
    
    // Verificar se é um evento de logout nos detalhes ou action
    if (details.includes('logout') || details.includes('saiu') || action === 'logout') {
      return <LogOut className="w-4 h-4 text-red-400" />;
    }
    
    switch (action) {
      case 'login':
        return <LogIn className="w-4 h-4 text-emerald-400" />;
      case 'logout':
        return <LogOut className="w-4 h-4 text-amber-400" />;
      case 'create':
        if (details.includes('usuário criado')) {
          return <UserPlus className="w-4 h-4 text-blue-400" />;
        } else if (details.includes('conversa')) {
          return <MessageCircle className="w-4 h-4 text-blue-400" />;
        } else if (details.includes('provedor') || details.includes('equipe') || details.includes('canal') || details.includes('empresa')) {
          return <Plus className="w-4 h-4 text-green-400" />;
        }
        return <Plus className="w-4 h-4 text-blue-400" />;
      case 'edit':
        if (details.includes('configuração')) {
          return <Settings className="w-4 h-4 text-yellow-400" />;
        }
        return <Edit className="w-4 h-4 text-yellow-400" />;
      case 'delete':
        return <Trash className="w-4 h-4 text-red-400" />;

      case 'contact_created':
        return <UserPlus className="w-4 h-4 text-purple-400" />;
      default:
        return <Activity className="w-4 h-4 text-gray-400" />;
    }
  };

  const getActivityText = (activity) => {
    const action = (activity.action || '').toLowerCase();
    const userName = extractUserName(activity);
    
    // Tentar extrair detalhes específicos da atividade
    let details = activity.details;
    if (typeof details === 'object') {
      details = JSON.stringify(details);
    }
    details = details || '';
    
    // Verificar se há informações de login nos detalhes (case insensitive)
    if (details.toLowerCase().includes('login bem-sucedido') || details.toLowerCase().includes('tentativa de login')) {
      const userNameMatch = details.match(/usuário:\s*(\w+)/i);
      const loginUser = userNameMatch ? userNameMatch[1] : userName;
      return `${loginUser} entrou no sistema`;
    }
    
    // Verificar se há informações de logout nos detalhes (case insensitive)
    if (details.toLowerCase().includes('logout') || details.toLowerCase().includes('saiu')) {
      const userNameMatch = details.match(/usuário:\s*(\w+)/i);
      const logoutUser = userNameMatch ? userNameMatch[1] : userName;
      return `${logoutUser} saiu do sistema`;
    }
    
    switch (action) {
      case 'login':
        return `${userName} entrou no sistema`;
      case 'logout':
        return `${userName} saiu do sistema`;
      case 'create':
        // Tentar extrair o que foi criado dos detalhes
        if (details.includes('Usuário criado')) {
          const match = details.match(/Usuário criado: (\w+)/);
          const createdUser = match ? match[1] : 'usuário';
          return `${userName} criou o usuário ${createdUser}`;
        } else if (details.includes('Equipe criada') || details.includes('equipe criada')) {
          const match = details.match(/[Ee]quipe criada: (.+)/);
          const teamName = match ? match[1] : 'equipe';
          return `${userName} criou a equipe ${teamName}`;
        } else if (details.includes('Equipe excluída') || details.includes('equipe excluída')) {
          const match = details.match(/[Ee]quipe excluída: (.+)/);
          const teamName = match ? match[1] : 'equipe';
          return `${userName} excluiu a equipe ${teamName}`;
        } else if (details.includes('Contato criado')) {
          return `${userName} adicionou um novo contato`;
        } else if (details.includes('Empresa criada')) {
          const match = details.match(/Empresa criada: (.+)/);
          const companyName = match ? match[1] : 'empresa';
          return `${userName} criou a empresa ${companyName}`;
        } else if (details.includes('Provedor criado')) {
          const match = details.match(/Provedor criado: (.+)/);
          const providerName = match ? match[1] : 'provedor';
          return `${userName} criou o provedor ${providerName}`;
        } else if (details.includes('Canal criado')) {
          const match = details.match(/Canal criado: (.+)/);
          const channelName = match ? match[1] : 'canal';
          return `${userName} criou o canal ${channelName}`;
        }
        return `${userName} criou um item no sistema`;
      case 'delete':
        if (details.includes('Usuário excluído') || details.includes('Usuário removido')) {
          const match = details.match(/Usuário (?:excluído|removido): (\w+)/);
          const deletedUser = match ? match[1] : 'usuário';
          return `${userName} excluiu o usuário ${deletedUser}`;
        } else if (details.includes('Equipe excluída') || details.includes('Equipe removida')) {
          const match = details.match(/Equipe (?:excluída|removida): (.+)/);
          const teamName = match ? match[1] : 'equipe';
          return `${userName} excluiu a equipe ${teamName}`;
        } else if (details.includes('Conversa removida')) {
          return `${userName} excluiu uma conversa`;
        } else if (details.includes('Contato removido')) {
          return `${userName} excluiu um contato`;
        } else if (details.includes('Empresa excluída')) {
          const match = details.match(/Empresa excluída: (.+)/);
          const companyName = match ? match[1] : 'empresa';
          return `${userName} excluiu a empresa ${companyName}`;
        }
        return `${userName} excluiu um item do sistema`;
      case 'contact_created':
        const contactName = activity.contact_name || 'cliente';
        return `${userName} adicionou o contato ${contactName}`;
      default:
        if (HUMAN_ACTIONS[action]) {
          return `${userName} ${HUMAN_ACTIONS[action]}`;
        }
        if (action.includes('conversation_closed')) {
          return `${userName} finalizou uma conversa`;
        }
        if (action.includes('logout')) {
          return `${userName} saiu do sistema`;
        }
        if (action.includes('login')) {
          return `${userName} entrou no sistema`;
        }
        return `${userName} executou ${action || 'ação no sistema'}`;
    }
  };

  if (loading) {
    return (
      <Card className="nc-card">
        <CardContent className="p-6">
          <div className="flex items-center justify-center h-32">
            <div className="animate-spin rounded-full h-6 w-6 border-b-2 border-blue-500"></div>
          </div>
        </CardContent>
      </Card>
    );
  }

  return (
    <Card className="bg-card border-border">
      <CardHeader className="pb-2">
        <CardTitle className="text-sm text-foreground flex items-center gap-2">
          <Activity className="w-4 h-4 text-primary" />
          Atividade Recente
        </CardTitle>
      </CardHeader>
      <CardContent>
        {activities.length === 0 ? (
          <div className="h-[160px] flex items-center justify-center text-muted-foreground text-sm">
            Nenhuma atividade recente
          </div>
        ) : (
          <div className="space-y-2 max-h-[300px] overflow-y-auto">
            {activities.map((activity) => (
              <div key={activity.id} className="flex items-center gap-3 p-2 rounded-md bg-muted border border-border">
                <div className="shrink-0">{getActivityIcon(activity)}</div>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 mb-0.5">
                    <span
                      className={`inline-flex items-center rounded-full border px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide ${getBadgeStyle(getActivityType(activity))}`}
                    >
                      {getBadgeLabel(getActivityType(activity))}
                    </span>
                  </div>
                  <div className="text-sm text-foreground">
                    {getActivityText(activity)}
                  </div>
                  <div className="text-xs text-muted-foreground">
                    {activity.timestamp || activity.created_at || activity.event_at
                      ? format(new Date(activity.timestamp || activity.created_at || activity.event_at), "dd/MM/yyyy HH:mm")
                      : "-"
                    }
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  );
}