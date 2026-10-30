import { useEffect, useState } from 'react';
import { Sparkles, Network, Router, KeyRound } from 'lucide-react';
import { useNavigate, useParams } from 'react-router-dom';
import axios from 'axios';

function MetaIcon({ className, strokeWidth = 2.5 }) {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={strokeWidth}
      strokeLinecap="round"
      strokeLinejoin="round"
      className={className}
      aria-hidden="true"
    >
      <path d="M6.5 10.5c1.2-3.2 2.8-5 4.3-5 1.8 0 2.7 2.2 4.2 6.5 1.2 3.4 2.2 5 3.5 5 1.2 0 2.3-1.5 3.5-4.5" />
      <path d="M2 11.5c1.3 3.2 2.6 5 4 5 1.6 0 2.6-2.1 4-6.5C11.2 6.8 12.2 5 13.7 5" />
    </svg>
  );
}

export default function IntegrationsPage() {
  const navigate = useNavigate();
  const { provedorId } = useParams();
  const [agentMode, setAgentMode] = useState('isp');

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const bounceToChannels = [
      'instagram_oauth_success',
      'instagram_oauth_error',
      'oauth_success',
      'oauth_error',
      'whatsapp_connected',
      'code',
    ].some((key) => params.get(key));
    if (!bounceToChannels) {
      return;
    }
    const pid = provedorId || '1';
    navigate(`/app/accounts/${pid}/canais/configurar?${params.toString()}`, { replace: true });
  }, [navigate, provedorId]);

  useEffect(() => {
    const token = localStorage.getItem('auth_token') || localStorage.getItem('token');
    if (!token) return;
    axios
      .get('/api/provider/config/', { headers: { Authorization: `Token ${token}` } })
      .then((res) => setAgentMode((res.data?.agent_mode || 'isp').toLowerCase()))
      .catch(() => {});
  }, []);

  const isSupportMode = agentMode === 'support';

  const cards = [
    {
      key: 'agente-ia',
      icon: Sparkles,
      iconClass: 'bg-fuchsia-500 text-white',
      title: 'Configurar Agente de IA',
      description: 'Escolha OpenAI, Gemini ou DeepSeek e use a sua própria chave de API.',
      path: 'agente-ia',
    },
    ...(isSupportMode
      ? [
          {
            key: 'asaas',
            icon: KeyRound,
            iconClass: 'bg-teal-500 text-white',
            title: 'Asaas',
            description:
              'Token da API Asaas para o agente de suporte buscar e enviar faturas dos provedores.',
            path: 'asaas',
          },
        ]
      : []),
    {
      key: 'erp',
      icon: Network,
      iconClass: 'bg-blue-600 text-white',
      title: 'Seu ERP',
      description: 'Conecte seu sistema de gestão e gerencie o token de webhook de disparos.',
      path: 'erp',
    },
    {
      key: 'acs',
      icon: Router,
      iconClass: 'bg-lime-500 text-white',
      title: 'NIO HUB - ACS',
      description: 'Conecte a API TR-069 para gerenciar ONTs/CPEs (Wi-Fi e firmware).',
      path: 'acs',
    },
    {
      key: 'meta',
      icon: MetaIcon,
      iconClass: 'bg-rose-500 text-white',
      title: 'Meta',
      description: 'Analytics da API oficial: mensagens grátis, templates pagos e gasto aproximado.',
      path: 'meta',
    },
  ];

  return (
    <div className="p-8 min-h-screen bg-background text-foreground overflow-y-auto">
      <div className="flex items-center gap-4 mb-2 ml-4">
        <h1 className="text-3xl font-semibold tracking-tight text-foreground">Integrações</h1>
      </div>

      <p className="text-muted-foreground mb-12 ml-12">
        {isSupportMode
          ? 'Configure o agente de IA, o Asaas (faturas da plataforma), o ERP/ACS se necessário e acompanhe o uso da API oficial da Meta.'
          : 'Configure o agente de IA, o ERP, o ACS e acompanhe o uso da API oficial da Meta.'}
      </p>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6 max-w-7xl mx-auto">
        {cards.map((card) => {
          const Icon = card.icon;
          return (
            <div
              key={card.key}
              onClick={() => navigate(card.path)}
              className="group relative bg-card p-8 rounded-2xl border border-border hover:shadow transition-shadow cursor-pointer overflow-hidden flex flex-col items-center text-center gap-4"
            >
              <div
                className={`w-14 h-14 rounded-xl flex items-center justify-center shadow-sm group-hover:scale-105 transition-transform duration-300 ${card.iconClass}`}
              >
                <Icon className="w-7 h-7" strokeWidth={2.5} />
              </div>

              <div>
                <h3 className="text-xl font-bold text-foreground mb-2">{card.title}</h3>
                <p className="text-muted-foreground text-sm leading-relaxed max-w-[200px]">
                  {card.description}
                </p>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
