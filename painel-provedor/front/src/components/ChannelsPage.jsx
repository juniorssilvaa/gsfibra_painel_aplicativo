import React from 'react';
import { Settings, Copy } from 'lucide-react';
import { useNavigate } from 'react-router-dom';

const ChannelsPage = () => {
  const navigate = useNavigate();

  return (
    <div className="p-8 min-h-screen bg-background text-foreground overflow-y-auto">
      <div className="flex items-center gap-4 mb-2 ml-4">
        <h1 className="text-3xl font-semibold tracking-tight text-foreground">Cadastrar canais</h1>
      </div>

      <p className="text-muted-foreground mb-12 ml-12">
        Integre suas redes sociais para ter uma comunicação total com seu cliente, em um só local!
      </p>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6 max-w-7xl mx-auto">
        <div
          onClick={() => navigate('configurar')}
          className="group relative bg-card p-8 rounded-2xl border border-border hover:shadow transition-shadow cursor-pointer overflow-hidden flex flex-col items-center text-center gap-4"
        >
          <div className="w-14 h-14 rounded-xl bg-cyan-500 text-white flex items-center justify-center shadow-sm group-hover:scale-105 transition-transform duration-300">
            <Settings className="w-7 h-7" strokeWidth={2.5} />
          </div>

          <div>
            <h3 className="text-xl font-bold text-foreground mb-2">Configurar canal</h3>
            <p className="text-muted-foreground text-sm leading-relaxed max-w-[200px]">
              Gerencie e conecte novos canais de comunicação como WhatsApp, Telegram e outros.
            </p>
          </div>
        </div>

        <div
          onClick={() => navigate('templates')}
          className="group relative bg-card p-8 rounded-2xl border border-border hover:shadow transition-shadow cursor-pointer overflow-hidden flex flex-col items-center text-center gap-4"
        >
          <div className="w-14 h-14 rounded-xl bg-pink-500 text-white flex items-center justify-center shadow-sm group-hover:scale-105 transition-transform duration-300">
            <Copy className="w-7 h-7" strokeWidth={2.5} />
          </div>

          <div>
            <h3 className="text-xl font-bold text-foreground mb-2">Modelo de mensagem</h3>
            <p className="text-muted-foreground text-sm leading-relaxed max-w-[200px]">
              Crie modelos para cobrança com botões interativos. Na aba Modelos há opções prontas para começar mais rápido.
            </p>
          </div>
        </div>
      </div>
    </div>
  );
};

export default ChannelsPage;
