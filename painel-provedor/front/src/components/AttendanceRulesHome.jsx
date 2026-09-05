import React from 'react';
import { useNavigate } from 'react-router-dom';
import { ChevronRight, Clock3, CalendarDays, SlidersHorizontal, Settings2 } from 'lucide-react';

const cards = [
  {
    key: 'horario-comercial',
    icon: Clock3,
    iconClass: 'bg-sky-500 text-white',
    badge: 'HORÁRIOS',
    badgeClass: 'bg-sky-500 text-white',
    title: 'Horário comercial',
    description: 'Configure os horários padrão do provedor e, se quiser, horários específicos por equipe.',
  },
  {
    key: 'automacao',
    icon: SlidersHorizontal,
    iconClass: 'bg-violet-600 text-white',
    badge: 'AUTOMAÇÃO',
    badgeClass: 'bg-violet-600 text-white',
    title: 'Automação por horário',
    description: 'Defina quando a IA ou o chatbot entram automaticamente em ação conforme o expediente.',
  },
  {
    key: 'feriados',
    icon: CalendarDays,
    iconClass: 'bg-amber-500 text-white',
    badge: 'FERIADOS',
    badgeClass: 'bg-amber-500 text-white',
    title: 'Feriados e datas especiais',
    description: 'Feriados nacionais (só ativar/desativar) e datas especiais do provedor, usados pela IA e pelo chatbot.',
  },
  {
    key: 'geral',
    icon: Settings2,
    iconClass: 'bg-emerald-500 text-white',
    badge: 'GERAL',
    badgeClass: 'bg-emerald-500 text-white',
    title: 'Configurações gerais',
    description: 'Contrato suspenso, horário após comprovante, filtro de mensagens e nome do bot.',
  },
];

export default function AttendanceRulesHome({ provedorId }) {
  const navigate = useNavigate();

  const goTo = (key) => {
    navigate(`/app/accounts/${provedorId}/regras-atendimento/${key}`);
  };

  return (
    <div className="flex-1 min-h-0 w-full p-6 overflow-y-auto">
      <div className="w-full max-w-none">
        <div className="mb-6">
          <h1 className="text-3xl font-bold text-foreground mb-2">Regras de Atendimento</h1>
          <p className="text-muted-foreground">
            Organize horários, feriados e comportamentos automáticos da IA e do chatbot.
          </p>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          {cards.map((card) => {
            const Icon = card.icon;
            return (
              <button
                key={card.key}
                type="button"
                onClick={() => goTo(card.key)}
                className="text-left bg-card border border-border rounded-xl p-6 shadow-sm hover:shadow transition-shadow"
              >
                <div className="flex items-start gap-4">
                  <div className={`w-11 h-11 rounded-lg flex items-center justify-center shadow-sm ${card.iconClass}`}>
                    <Icon className="w-5 h-5" strokeWidth={2.5} />
                  </div>
                  <div className="flex-1">
                    <div className="flex items-center gap-2 mb-2">
                      <span className={`inline-flex items-center px-2 py-1 rounded-md text-xs font-semibold ${card.badgeClass}`}>
                        {card.badge}
                      </span>
                    </div>
                    <div className="text-lg font-semibold text-foreground">{card.title}</div>
                    <div className="text-sm text-muted-foreground mt-1">
                      {card.description}
                    </div>
                  </div>
                  <ChevronRight className="w-5 h-5 text-muted-foreground flex-shrink-0 mt-1" />
                </div>
              </button>
            );
          })}
        </div>
      </div>
    </div>
  );
}
