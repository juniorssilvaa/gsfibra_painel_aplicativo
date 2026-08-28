import React from 'react';
import { useNavigate } from 'react-router-dom';
import { ArrowLeft } from 'lucide-react';
import Integrations from './Integrations';

export default function ChannelConfigPage() {
  const navigate = useNavigate();
  const provedorId = localStorage.getItem('provedor_id');

  return (
    <div className="min-h-screen bg-background text-white overflow-y-auto">
      {/* Header Fixo */}
      <div className="sticky top-0 z-40 bg-background/80 backdrop-blur-md border-b border-white/5 p-6 flex items-center justify-between">
        <div className="flex items-center gap-4">
          <button 
            onClick={() => navigate(-1)}
            className="p-2 hover:bg-white/5 rounded-full transition-colors group"
          >
            <ArrowLeft className="w-6 h-6 text-primary group-hover:scale-110 transition-transform" />
          </button>
          <div>
            <h1 className="text-2xl font-bold bg-gradient-to-r from-white to-gray-400 bg-clip-text text-transparent">
              Configurar Canais
            </h1>
            <p className="text-sm text-gray-500">
              Centralize e gerencie todos os seus canais de comunicação em um único lugar
            </p>
          </div>
        </div>
      </div>

      <div className="p-4 md:p-8">
        <div className="max-w-6xl mx-auto">
          {/* Reutilizando o componente Integrations com o modo focado em canais */}
          <Integrations provedorId={provedorId} mode="channels" />
        </div>
      </div>
    </div>
  );
}
