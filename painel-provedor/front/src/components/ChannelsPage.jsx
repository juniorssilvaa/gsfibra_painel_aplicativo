import React from 'react';
import { 
  MessageSquare, 
  Send, 
  Facebook, 
  Instagram, 
  MessageCircle, 
  Users,
  ArrowLeft,
  Settings,
  Copy
} from 'lucide-react';
import { useNavigate } from 'react-router-dom';

const ChannelsPage = () => {
  const navigate = useNavigate();



  return (
    <div className="p-8 min-h-screen bg-background text-white overflow-y-auto">
      {/* Header com botão voltar */}
      <div className="flex items-center gap-4 mb-2 ml-4">
        <h1 className="text-3xl font-semibold tracking-tight text-slate-100">Cadastrar canais</h1>
      </div>
      
      <p className="text-slate-400 mb-12 ml-12">
        Integre suas redes sociais para ter uma comunicação total com seu cliente, em um só local!
      </p>

      {/* Grid de Canais */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6 max-w-7xl mx-auto">
        <div 
          onClick={() => navigate('configurar')}
          className="group relative bg-card p-8 rounded-2xl border border-white/5 hover:border-primary/50 transition-all duration-300 cursor-pointer overflow-hidden flex flex-col items-center text-center gap-4"
        >
          {/* Background Glow */}
          <div className="absolute -inset-1 bg-gradient-to-r from-primary to-orange-600 rounded-2xl blur opacity-0 group-hover:opacity-10 transition duration-300" />
          
          <div className="relative w-16 h-16 bg-primary/10 rounded-2xl flex items-center justify-center mb-2 group-hover:scale-110 transition-transform duration-300">
            <Settings className="w-8 h-8 text-primary" />
          </div>
          
          <div className="relative">
            <h3 className="text-xl font-bold text-white mb-2 group-hover:text-primary transition-colors">
              Configurar canal
            </h3>
            <p className="text-gray-400 text-sm leading-relaxed max-w-[200px]">
              Gerencie e conecte novos canais de comunicação como WhatsApp, Telegram e outros.
            </p>
          </div>
        </div>

        {/* Card Modelo de Mensagem */}
        <div 
          onClick={() => navigate('templates')}
          className="group relative bg-card p-8 rounded-2xl border border-white/5 hover:border-primary/50 transition-all duration-300 cursor-pointer overflow-hidden flex flex-col items-center text-center gap-4"
        >
          {/* Background Glow */}
          <div className="absolute -inset-1 bg-gradient-to-r from-primary to-orange-600 rounded-2xl blur opacity-0 group-hover:opacity-10 transition duration-300" />
          
          <div className="relative w-16 h-16 bg-primary/10 rounded-2xl flex items-center justify-center mb-2 group-hover:scale-110 transition-transform duration-300">
            <Copy className="w-8 h-8 text-primary" />
          </div>
          
          <div className="relative">
            <h3 className="text-xl font-bold text-white mb-2 group-hover:text-primary transition-colors flex items-center justify-center gap-2 flex-wrap">
              Modelo de mensagem
              <span className="text-[10px] font-bold uppercase tracking-wider text-primary bg-primary/15 px-2 py-0.5 rounded-md border border-primary/30">
                Beta
              </span>
            </h3>
            <p className="text-gray-400 text-sm leading-relaxed max-w-[200px]">
              Crie modelos para cobrança com botões interativos. Na aba Modelos há opções prontas para começar mais rápido.
            </p>
          </div>
        </div>
      </div>

      <style dangerouslySetInnerHTML={{ __html: `
        .group:hover {
          box-shadow: 0 20px 40px -15px rgba(0,0,0,0.5);
        }
      `}} />
    </div>
  );
};

export default ChannelsPage;
