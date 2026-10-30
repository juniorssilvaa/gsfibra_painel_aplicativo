import { ArrowLeft } from 'lucide-react';
import { Navigate, useNavigate } from 'react-router-dom';
import Integrations from './Integrations';
import { useBotMode } from '../hooks/useAgentMode';

const SECTIONS = {
  ai: {
    title: 'Configurar Agente de IA',
    subtitle: 'Escolha o provedor (OpenAI, Gemini ou DeepSeek) e use a sua própria chave',
    mode: 'ai',
  },
  erp: {
    title: 'Seu ERP',
    subtitle: 'Configure a integração com o sistema de gestão e o webhook de disparos',
    mode: 'erp',
  },
  acs: {
    title: 'NIO HUB - ACS',
    subtitle: 'URL e token Bearer da API de gerenciamento remoto de ONTs/CPEs (TR-069)',
    mode: 'acs',
  },
  asaas: {
    title: 'Asaas',
    subtitle: 'Token da API Asaas para o agente de suporte enviar faturas da plataforma',
    mode: 'asaas',
  },
};

export default function IntegrationSettingsPage({ provedorId, section = 'ai' }) {
  const navigate = useNavigate();
  const botMode = useBotMode();
  const config = SECTIONS[section] || SECTIONS.ai;

  if (section === 'ai' && botMode && botMode !== 'ia') {
    return <Navigate to={`/app/accounts/${provedorId}/integracoes`} replace />;
  }

  return (
    <div className="min-h-screen bg-background text-white overflow-y-auto">
      <div className="sticky top-0 z-40 bg-background/80 backdrop-blur-md border-b border-white/5 p-6 flex items-center justify-between">
        <div className="flex items-center gap-4">
          <button
            type="button"
            onClick={() => navigate(-1)}
            className="p-2 hover:bg-white/5 rounded-full transition-colors group"
          >
            <ArrowLeft className="w-6 h-6 text-primary group-hover:scale-110 transition-transform" />
          </button>
          <div>
            <h1 className="text-2xl font-bold bg-gradient-to-r from-white to-gray-400 bg-clip-text text-transparent">
              {config.title}
            </h1>
            <p className="text-sm text-gray-500">{config.subtitle}</p>
          </div>
        </div>
      </div>

      <div className="p-4 md:p-8">
        <div className="max-w-3xl mx-auto">
          <Integrations provedorId={provedorId} mode={config.mode} />
        </div>
      </div>
    </div>
  );
}
