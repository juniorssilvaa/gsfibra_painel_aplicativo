import React, { useEffect, useState } from 'react';
import axios from 'axios';
import { ArrowLeft, Clock3 } from 'lucide-react';
import { useNavigate } from 'react-router-dom';

function ToggleSwitch({ checked, onChange, label }) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      onClick={() => onChange(!checked)}
      className={[
        'relative inline-flex items-center h-6 w-11 rounded-full transition-colors flex-shrink-0',
        checked ? 'bg-emerald-500' : 'bg-red-600',
      ].join(' ')}
    >
      <span
        className={[
          'inline-block h-5 w-5 transform rounded-full bg-white transition-transform duration-200',
          checked ? 'translate-x-5' : 'translate-x-1',
        ].join(' ')}
      />
      <span className="sr-only">{label}</span>
    </button>
  );
}

export default function AttendanceAutomationSettings({ provedorId }) {
  const navigate = useNavigate();
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');
  const [enabled, setEnabled] = useState(false);
  const [mode, setMode] = useState('outside_business_hours');
  const [applyHolidays, setApplyHolidays] = useState(true);
  const [fallbackTeamId, setFallbackTeamId] = useState('');
  const [teams, setTeams] = useState([]);

  const authHeaders = () => ({
    Authorization: `Token ${localStorage.getItem('auth_token') || localStorage.getItem('token') || ''}`,
  });

  useEffect(() => {
    async function load() {
      setLoading(true);
      setError('');
      try {
        const [provRes, teamsRes] = await Promise.all([
          axios.get(`/api/provedores/${provedorId}/`, { headers: authHeaders() }),
          axios.get('/api/teams/', { headers: authHeaders() }),
        ]);
        const prov = provRes.data;
        setEnabled(Boolean(prov.automation_schedule_enabled));
        setMode(prov.automation_schedule_mode || 'outside_business_hours');
        setApplyHolidays(prov.automation_schedule_apply_holidays ?? true);
        setFallbackTeamId(
          prov.automation_schedule_fallback_team
            ? String(prov.automation_schedule_fallback_team)
            : ''
        );
        const teamList = Array.isArray(teamsRes.data?.results)
          ? teamsRes.data.results
          : Array.isArray(teamsRes.data)
            ? teamsRes.data
            : [];
        setTeams(teamList.filter((t) => t.is_active !== false && String(t.name || '').toUpperCase() !== 'IA'));
      } catch {
        setError('Erro ao carregar configurações de automação.');
      } finally {
        setLoading(false);
      }
    }
    if (provedorId) load();
  }, [provedorId]);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setSaving(true);
    setError('');
    setSuccess('');

    if (enabled && mode === 'inside_business_hours' && !fallbackTeamId) {
      setError('Selecione a equipe que receberá os atendimentos quando a automação estiver desligada.');
      setSaving(false);
      return;
    }

    try {
      await axios.patch(
        `/api/provedores/${provedorId}/`,
        {
          automation_schedule_enabled: enabled,
          automation_schedule_mode: mode,
          automation_schedule_apply_holidays: applyHolidays,
          automation_schedule_fallback_team:
            mode === 'inside_business_hours' && fallbackTeamId
              ? Number(fallbackTeamId)
              : null,
        },
        { headers: authHeaders() }
      );
      setSuccess('Automação por horário salva com sucesso.');
    } catch {
      setError('Erro ao salvar configurações de automação.');
    } finally {
      setSaving(false);
    }
  };

  if (loading) {
    return <div className="p-6 text-muted-foreground">Carregando...</div>;
  }

  return (
    <div className="flex-1 min-h-0 w-full p-6 overflow-y-auto relative">
      <button
        type="button"
        onClick={() => navigate(`/app/accounts/${provedorId}/regras-atendimento`)}
        className="absolute left-6 top-6 px-4 py-2 rounded-lg bg-primary text-primary-foreground hover:opacity-90 transition-opacity inline-flex items-center gap-2"
      >
        <ArrowLeft className="w-4 h-4" />
        Voltar
      </button>

      <div className="mb-6 pt-14">
        <h1 className="text-2xl font-bold text-foreground">Automação por horário</h1>
        <p className="text-sm text-muted-foreground mt-1">
          Controle quando a IA ou o chatbot podem responder automaticamente com base no horário comercial.
        </p>
      </div>

      {error && (
        <div className="mb-4 p-3 rounded-lg bg-red-500/10 text-red-500 border border-red-500/30">{error}</div>
      )}
      {success && (
        <div className="mb-4 p-3 rounded-lg bg-emerald-500/10 text-emerald-600 border border-emerald-500/30">{success}</div>
      )}

      <form onSubmit={handleSubmit} className="space-y-6 w-full max-w-none">
        <section className="bg-card border border-border rounded-xl p-6 space-y-6 w-full">
          <div className="flex items-start justify-between gap-4">
            <div className="flex-1">
              <div className="flex items-center gap-2 mb-1">
                <Clock3 className="w-5 h-5 text-violet-400" strokeWidth={2.5} />
                <h2 className="text-lg font-semibold text-foreground">Ativar agenda automática</h2>
              </div>
              <p className="text-sm text-muted-foreground">
                Quando ativado, o sistema usa o horário comercial do provedor para decidir se a
                automação fica ligada ou desligada.
              </p>
            </div>
            <ToggleSwitch
              checked={enabled}
              onChange={setEnabled}
              label="Ativar automação por horário"
            />
          </div>

          {enabled && (
            <>
              <div>
                <label className="block text-sm font-medium text-foreground mb-2">
                  Quando a automação deve funcionar
                </label>
                <select
                  value={mode}
                  onChange={(e) => setMode(e.target.value)}
                  className="w-full max-w-2xl rounded-lg border border-border bg-background px-3 py-2 text-sm text-foreground"
                >
                  <option value="outside_business_hours">Fora do horário comercial</option>
                  <option value="inside_business_hours">Dentro do horário comercial</option>
                </select>
                <p className="text-xs text-muted-foreground mt-2">
                  {mode === 'inside_business_hours'
                    ? 'A IA/chatbot responde só no expediente. Fora do horário, os atendimentos vão para a equipe selecionada abaixo.'
                    : 'Exemplo comum: deixar humanos atenderem durante o expediente e ativar IA/chatbot apenas quando a empresa estiver fechada.'}
                </p>
              </div>

              {mode === 'inside_business_hours' && (
                <div className="border-t border-border pt-4">
                  <label className="block text-sm font-medium text-foreground mb-2">
                    Equipe para receber atendimentos fora do horário
                  </label>
                  <select
                    value={fallbackTeamId}
                    onChange={(e) => setFallbackTeamId(e.target.value)}
                    required
                    className="w-full max-w-2xl rounded-lg border border-border bg-background px-3 py-2 text-sm text-foreground"
                  >
                    <option value="">Selecione uma equipe</option>
                    {teams.map((team) => (
                      <option key={team.id} value={String(team.id)}>
                        {team.name}
                      </option>
                    ))}
                  </select>
                  <p className="text-xs text-muted-foreground mt-2">
                    Quando a automação estiver desligada (fora do expediente ou em feriado), todos os
                    novos atendimentos caem nesta equipe.
                  </p>
                  {teams.length === 0 && (
                    <p className="text-xs text-amber-500 mt-2">
                      Nenhuma equipe ativa encontrada. Cadastre uma equipe antes de salvar.
                    </p>
                  )}
                </div>
              )}

              <div className="flex items-start justify-between gap-4 border-t border-border pt-4">
                <div className="flex-1">
                  <h3 className="text-base font-medium text-foreground mb-1">
                    Considerar feriados cadastrados
                  </h3>
                  <p className="text-sm text-muted-foreground">
                    Se ligado, os feriados nacionais ativos e as datas especiais do provedor também
                    entram no cálculo automático da automação.
                  </p>
                </div>
                <ToggleSwitch
                  checked={applyHolidays}
                  onChange={setApplyHolidays}
                  label="Considerar feriados cadastrados"
                />
              </div>
            </>
          )}
        </section>

        <div className="flex justify-end">
          <button
            type="submit"
            disabled={saving}
            className="px-6 py-2 rounded-lg bg-primary text-primary-foreground font-medium hover:opacity-90 disabled:opacity-50"
          >
            {saving ? 'Salvando...' : 'Salvar automação'}
          </button>
        </div>
      </form>
    </div>
  );
}
