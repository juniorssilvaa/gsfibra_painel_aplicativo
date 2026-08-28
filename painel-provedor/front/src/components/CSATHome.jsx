import React from 'react';
import { useNavigate } from 'react-router-dom';
import { Smile, Settings, ChevronRight } from 'lucide-react';

export default function CSATHome({ provedorId }) {
  const navigate = useNavigate();

  const goAvaliacoes = () => {
    navigate(`/app/accounts/${provedorId}/csat/avaliacoes`);
  };

  const goConfig = () => {
    navigate(`/app/accounts/${provedorId}/csat/configurar`);
  };

  return (
    <div className="flex-1 p-6 bg-background overflow-y-auto">
      <div className="max-w-5xl mx-auto">
        <div className="mb-6">
          <h1 className="text-3xl font-bold text-foreground mb-2">CSAT</h1>
          <p className="text-muted-foreground">
            Configure quando a pesquisa será disparada e acompanhe as avaliações.
          </p>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          <button
            type="button"
            onClick={goConfig}
            className="text-left bg-card border border-border rounded-xl p-6 shadow-sm hover:shadow transition-shadow"
          >
            <div className="flex items-start gap-4">
              <div className="w-10 h-10 rounded-lg bg-blue-600/10 flex items-center justify-center text-blue-600">
                <Settings className="w-5 h-5" />
              </div>
              <div className="flex-1">
                <div className="flex items-center gap-2 mb-2">
                  <span className="inline-flex items-center px-2 py-1 rounded-md text-xs font-semibold bg-blue-600 text-white">
                    CONFIGURAR
                  </span>
                </div>
                <div className="text-lg font-semibold text-foreground">Configurar CSAT</div>
                <div className="text-sm text-muted-foreground mt-1">
                  Defina o tempo de disparo e se o CSAT é enviado quando o bot encerrar por inatividade.
                </div>
              </div>
              <ChevronRight className="w-5 h-5 text-muted-foreground flex-shrink-0 mt-1" />
            </div>
          </button>

          <button
            type="button"
            onClick={goAvaliacoes}
            className="text-left bg-card border border-border rounded-xl p-6 shadow-sm hover:shadow transition-shadow"
          >
            <div className="flex items-start gap-4">
              <div className="w-10 h-10 rounded-lg bg-emerald-500/10 flex items-center justify-center text-emerald-500">
                <Smile className="w-5 h-5" />
              </div>
              <div className="flex-1">
                <div className="flex items-center gap-2 mb-2">
                  <span className="inline-flex items-center px-2 py-1 rounded-md text-xs font-semibold bg-emerald-500 text-white">
                    AVALIAÇÕES
                  </span>
                </div>
                <div className="text-lg font-semibold text-foreground">Avaliações do CSAT</div>
                <div className="text-sm text-muted-foreground mt-1">
                  Visualize totais, média e gráficos das avaliações recebidas.
                </div>
              </div>
              <ChevronRight className="w-5 h-5 text-muted-foreground flex-shrink-0 mt-1" />
            </div>
          </button>
        </div>
      </div>
    </div>
  );
}

