import { useEffect, useState } from 'react';
import { Sparkles, Network, Router, KeyRound } from 'lucide-react';
import { useNavigate, useParams } from 'react-router-dom';
import axios from 'axios';

function MetaIcon({ className, strokeWidth = 1.75 }) {
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
    if (!params.get('instagram_oauth_success') && !params.get('instagram_oauth_error')) {
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

  return (
    <div className="p-8 min-h-screen bg-background text-white overflow-y-auto">
      <div className="flex items-center gap-4 mb-2 ml-4">
        <h1 className="text-3xl font-semibold tracking-tight text-slate-100">Integrações</h1>
      </div>

      <p className="text-slate-400 mb-12 ml-12">
        {isSupportMode
          ? 'Configure o agente de IA, o Asaas (faturas da plataforma), o ERP/ACS se necessário e acompanhe o uso da API oficial da Meta.'
          : 'Configure o agente de IA, o ERP, o ACS e acompanhe o uso da API oficial da Meta.'}
      </p>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6 max-w-7xl mx-auto">
        <div
          onClick={() => navigate('agente-ia')}
          className="group relative bg-card p-8 rounded-2xl border border-white/5 hover:border-primary/50 transition-all duration-300 cursor-pointer overflow-hidden flex flex-col items-center text-center gap-4"
        >
          <div className="absolute -inset-1 bg-gradient-to-r from-primary to-orange-600 rounded-2xl blur opacity-0 group-hover:opacity-10 transition duration-300" />

          <div className="relative w-16 h-16 rounded-2xl bg-primary/10 flex items-center justify-center mb-2 group-hover:scale-110 transition-transform duration-300">
            <Sparkles className="w-8 h-8 text-primary" strokeWidth={1.75} />
          </div>

          <div className="relative">
            <h3 className="text-xl font-bold text-white mb-2 group-hover:text-primary transition-colors">
              Configurar Agente de IA
            </h3>
            <p className="text-gray-400 text-sm leading-relaxed max-w-[200px]">
              Escolha OpenAI, Gemini ou DeepSeek e use a sua própria chave de API.
            </p>
          </div>
        </div>

        {isSupportMode && (
          <div
            onClick={() => navigate('asaas')}
            className="group relative bg-card p-8 rounded-2xl border border-white/5 hover:border-primary/50 transition-all duration-300 cursor-pointer overflow-hidden flex flex-col items-center text-center gap-4"
          >
            <div className="absolute -inset-1 bg-gradient-to-r from-primary to-orange-600 rounded-2xl blur opacity-0 group-hover:opacity-10 transition duration-300" />

            <div className="relative w-16 h-16 rounded-2xl bg-primary/10 flex items-center justify-center mb-2 group-hover:scale-110 transition-transform duration-300">
              <KeyRound className="w-8 h-8 text-primary" strokeWidth={1.75} />
            </div>

            <div className="relative">
              <h3 className="text-xl font-bold text-white mb-2 group-hover:text-primary transition-colors">
                Asaas
              </h3>
              <p className="text-gray-400 text-sm leading-relaxed max-w-[200px]">
                Token da API Asaas para o agente de suporte buscar e enviar faturas dos provedores.
              </p>
            </div>
          </div>
        )}

        <div
          onClick={() => navigate('erp')}
          className="group relative bg-card p-8 rounded-2xl border border-white/5 hover:border-primary/50 transition-all duration-300 cursor-pointer overflow-hidden flex flex-col items-center text-center gap-4"
        >
          <div className="absolute -inset-1 bg-gradient-to-r from-primary to-orange-600 rounded-2xl blur opacity-0 group-hover:opacity-10 transition duration-300" />

          <div className="relative w-16 h-16 rounded-2xl bg-primary/10 flex items-center justify-center mb-2 group-hover:scale-110 transition-transform duration-300">
            <Network className="w-8 h-8 text-primary" strokeWidth={1.75} />
          </div>

          <div className="relative">
            <h3 className="text-xl font-bold text-white mb-2 group-hover:text-primary transition-colors">
              Seu ERP
            </h3>
            <p className="text-gray-400 text-sm leading-relaxed max-w-[200px]">
              Conecte seu sistema de gestão e gerencie o token de webhook de disparos.
            </p>
          </div>
        </div>

        <div
          onClick={() => navigate('acs')}
          className="group relative bg-card p-8 rounded-2xl border border-white/5 hover:border-primary/50 transition-all duration-300 cursor-pointer overflow-hidden flex flex-col items-center text-center gap-4"
        >
          <div className="absolute -inset-1 bg-gradient-to-r from-primary to-orange-600 rounded-2xl blur opacity-0 group-hover:opacity-10 transition duration-300" />

          <div className="relative w-16 h-16 rounded-2xl bg-primary/10 flex items-center justify-center mb-2 group-hover:scale-110 transition-transform duration-300">
            <Router className="w-8 h-8 text-primary" strokeWidth={1.75} />
          </div>

          <div className="relative">
            <h3 className="text-xl font-bold text-white mb-2 group-hover:text-primary transition-colors">
              NIO HUB - ACS
            </h3>
            <p className="text-gray-400 text-sm leading-relaxed max-w-[200px]">
              Conecte a API TR-069 para gerenciar ONTs/CPEs (Wi-Fi e equipamentos).
            </p>
          </div>
        </div>

        <div
          onClick={() => navigate('meta')}
          className="group relative bg-card p-8 rounded-2xl border border-white/5 hover:border-primary/50 transition-all duration-300 cursor-pointer overflow-hidden flex flex-col items-center text-center gap-4"
        >
          <div className="absolute -inset-1 bg-gradient-to-r from-primary to-orange-600 rounded-2xl blur opacity-0 group-hover:opacity-10 transition duration-300" />

          <div className="relative w-16 h-16 rounded-2xl bg-primary/10 flex items-center justify-center mb-2 group-hover:scale-110 transition-transform duration-300">
            <MetaIcon className="w-8 h-8 text-primary" strokeWidth={1.75} />
          </div>

          <div className="relative">
            <h3 className="text-xl font-bold text-white mb-2 group-hover:text-primary transition-colors">
              Meta
            </h3>
            <p className="text-gray-400 text-sm leading-relaxed max-w-[200px]">
              Analytics da API oficial: mensagens grátis, templates pagos e gasto aproximado.
            </p>
          </div>
        </div>
      </div>

      <style
        dangerouslySetInnerHTML={{
          __html: `
        .group:hover {
          box-shadow: 0 20px 40px -15px rgba(0,0,0,0.5);
        }
      `,
        }}
      />
    </div>
  );
}
