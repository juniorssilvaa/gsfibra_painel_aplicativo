import React, { useEffect, useState, useCallback } from 'react';
import axios from 'axios';
import { ArrowLeft, Clock } from 'lucide-react';
import { useNavigate } from 'react-router-dom';

const DIAS_SEMANA = [
  'Domingo', 'Segunda-feira', 'Terça-feira', 'Quarta-feira', 'Quinta-feira', 'Sexta-feira', 'Sábado'
];

function horarioPadrao() {
  return DIAS_SEMANA.map(dia => ({ dia, periodos: [] }));
}

function parseHorarios(raw) {
  if (!raw) return horarioPadrao();
  try {
    const data = typeof raw === 'string' ? JSON.parse(raw) : raw;
    return Array.isArray(data) && data.length ? data : horarioPadrao();
  } catch {
    return horarioPadrao();
  }
}

export default function ProviderScheduleForm({ provedorId: provedorIdProp }) {
  const navigate = useNavigate();
  const [horarios, setHorarios] = useState(horarioPadrao());
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [success, setSuccess] = useState('');
  const [error, setError] = useState('');
  const [provedorId, setProvedorId] = useState(provedorIdProp || null);
  const [teams, setTeams] = useState([]);
  const [selectedTarget, setSelectedTarget] = useState('global');
  const [teamUsesGlobal, setTeamUsesGlobal] = useState(true);
  const [now, setNow] = useState(new Date());
  const timezone = 'America/Belem';

  useEffect(() => {
    const interval = setInterval(() => setNow(new Date()), 1000);
    return () => clearInterval(interval);
  }, []);

  const authHeaders = () => ({
    Authorization: `Token ${localStorage.getItem('auth_token') || localStorage.getItem('token')}`,
  });

  const loadHorariosForTarget = useCallback((target, provId, teamsList) => {
    if (target === 'global') {
      return axios.get('/api/provedores/', { headers: authHeaders() }).then((res) => {
        const prov = res.data?.results?.find((p) => String(p.id) === String(provId))
          || res.data?.results?.[0];
        if (prov) {
          setHorarios(parseHorarios(prov.horarios_atendimento));
          setTeamUsesGlobal(true);
        }
      });
    }
    const team = teamsList.find((t) => String(t.id) === String(target));
    if (team) {
      const custom = team.horarios_atendimento;
      const hasCustom = custom && (typeof custom === 'string' ? custom.trim() : JSON.stringify(custom).length > 2);
      setTeamUsesGlobal(!hasCustom);
      setHorarios(hasCustom ? parseHorarios(custom) : horarioPadrao());
    }
    return Promise.resolve();
  }, []);

  useEffect(() => {
    async function fetchData() {
      setLoading(true);
      setError('');
      try {
        const [provRes, teamsRes] = await Promise.all([
          axios.get('/api/provedores/', { headers: authHeaders() }),
          axios.get('/api/teams/', { headers: authHeaders() }),
        ]);

        const prov = provedorIdProp
          ? provRes.data?.results?.find((p) => String(p.id) === String(provedorIdProp))
          : provRes.data?.results?.[0];

        if (prov) {
          setProvedorId(prov.id);
        }

        const teamsList = (teamsRes.data?.results || teamsRes.data || [])
          .filter((t) => t.is_active !== false)
          .sort((a, b) => (a.name || '').localeCompare(b.name || ''));
        setTeams(teamsList);

        await loadHorariosForTarget('global', prov?.id || provedorIdProp, teamsList);
      } catch {
        setError('Erro ao carregar horários.');
      }
      setLoading(false);
    }
    fetchData();
  }, [provedorIdProp, loadHorariosForTarget]);

  const handleTargetChange = async (e) => {
    const value = e.target.value;
    setSelectedTarget(value);
    setSuccess('');
    setError('');
    setLoading(true);
    try {
      await loadHorariosForTarget(value, provedorId, teams);
    } catch {
      setError('Erro ao carregar horários da equipe.');
    }
    setLoading(false);
  };

  const handleAddPeriodo = (diaIdx) => {
    setHorarios((prev) => prev.map((h, i) =>
      i === diaIdx ? { ...h, periodos: [...h.periodos, { inicio: '', fim: '' }] } : h
    ));
  };

  const handlePeriodoChange = (diaIdx, periodoIdx, campo, valor) => {
    setHorarios((prev) => prev.map((h, i) =>
      i === diaIdx ? {
        ...h,
        periodos: h.periodos.map((p, j) =>
          j === periodoIdx ? { ...p, [campo]: valor } : p
        ),
      } : h
    ));
  };

  const handleRemovePeriodo = (diaIdx, periodoIdx) => {
    setHorarios((prev) => prev.map((h, i) =>
      i === diaIdx ? { ...h, periodos: h.periodos.filter((_, j) => j !== periodoIdx) } : h
    ));
  };

  const handleCopiarAcima = (diaIdx) => {
    if (diaIdx === 0) return;
    setHorarios((prev) => prev.map((h, i) =>
      i === diaIdx ? { ...h, periodos: [...prev[diaIdx - 1].periodos] } : h
    ));
  };

  const handleUseGlobalSchedule = async () => {
    if (selectedTarget === 'global') return;
    setSaving(true);
    setError('');
    setSuccess('');
    try {
      await axios.patch(
        `/api/teams/${selectedTarget}/`,
        { horarios_atendimento: null },
        { headers: authHeaders() }
      );
      setTeamUsesGlobal(true);
      setHorarios(horarioPadrao());
      setSuccess('Esta equipe passou a usar o horário padrão do provedor.');
    } catch {
      setError('Erro ao restaurar horário padrão.');
    }
    setSaving(false);
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setSaving(true);
    setSuccess('');
    setError('');
    if (!provedorId && selectedTarget === 'global') {
      setError('Provedor não encontrado. Tente recarregar a página.');
      setSaving(false);
      return;
    }
    try {
      const payload = { horarios_atendimento: JSON.stringify(horarios) };
      if (selectedTarget === 'global') {
        await axios.patch(`/api/provedores/${provedorId}/`, payload, {
          headers: authHeaders(),
        });
        setSuccess('Horário padrão do provedor salvo com sucesso!');
      } else {
        await axios.patch(`/api/teams/${selectedTarget}/`, payload, {
          headers: authHeaders(),
        });
        setTeamUsesGlobal(false);
        setSuccess('Horário da equipe salvo com sucesso!');
      }
    } catch {
      setError('Erro ao salvar horários.');
    }
    setSaving(false);
  };

  const selectedTeam = teams.find((t) => String(t.id) === String(selectedTarget));

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
      <div className="flex items-center gap-3 mb-6 pt-14">
        <Clock className="w-8 h-8 text-primary" />
        <div>
          <h1 className="text-2xl font-bold text-foreground">Horário comercial</h1>
          <p className="text-sm text-muted-foreground">
            Configure os horários padrão do provedor e, se quiser, horários específicos por equipe.
          </p>
        </div>
      </div>

      {loading ? (
        <div className="text-muted-foreground">Carregando...</div>
      ) : (
        <form onSubmit={handleSubmit} className="space-y-6 w-full max-w-none">
          {success && (
            <div className="p-3 rounded-lg bg-emerald-500/10 text-emerald-600 border border-emerald-500/30">
              {success}
            </div>
          )}
          {error && (
            <div className="p-3 rounded-lg bg-red-500/10 text-red-500 border border-red-500/30">
              {error}
            </div>
          )}

          <section className="bg-card border border-border rounded-xl p-6 w-full">
            <div className="font-semibold text-foreground mb-2">Horário atual</div>
            <div className="flex items-center gap-3 flex-wrap">
              <Clock className="w-6 h-6 text-primary" />
              <span className="text-2xl font-bold text-foreground">
                {now.toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit', hour12: false, timeZone: timezone })}
              </span>
              <span className="text-foreground text-base">
                {now.toLocaleDateString('pt-BR', { weekday: 'long', day: '2-digit', month: '2-digit', year: 'numeric', timeZone: timezone })}
              </span>
              <span className="text-muted-foreground text-base">{timezone}</span>
            </div>
          </section>

          <section className="bg-card border border-border rounded-xl p-6 space-y-6 w-full">
            <div>
              <h2 className="text-lg font-semibold text-foreground mb-4">Horários de funcionamento</h2>
              <label className="text-sm font-medium text-foreground" htmlFor="schedule-target">
                Configurar horário de
              </label>
              <select
                id="schedule-target"
                value={selectedTarget}
                onChange={handleTargetChange}
                className="mt-2 w-full max-w-2xl h-10 rounded-md border border-input bg-background px-3 text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-ring"
                disabled={loading || saving}
              >
                <option value="global">Padrão do provedor (todas as equipes sem horário próprio)</option>
                {teams.map((team) => (
                  <option key={team.id} value={String(team.id)}>
                    Equipe: {team.name}
                    {team.usa_horario_provedor ? ' (usa padrão)' : ' (horário próprio)'}
                  </option>
                ))}
              </select>
              {selectedTarget !== 'global' && (
                <div className="flex flex-col sm:flex-row sm:items-center gap-2 text-sm mt-3">
                  <p className="text-muted-foreground flex-1">
                    {teamUsesGlobal
                      ? `A equipe ${selectedTeam?.name || ''} ainda não tem horário próprio — ao salvar, ela deixa de usar só o padrão.`
                      : `Horário exclusivo da equipe ${selectedTeam?.name || ''}. Comercial e suporte podem ter turnos diferentes.`}
                  </p>
                  {!teamUsesGlobal && (
                    <button
                      type="button"
                      onClick={handleUseGlobalSchedule}
                      disabled={saving}
                      className="text-xs px-3 py-1.5 rounded-md border border-border bg-muted text-foreground hover:bg-muted/80 shrink-0"
                    >
                      Usar horário padrão
                    </button>
                  )}
                </div>
              )}
            </div>

            <div className="text-muted-foreground">
              Configure os dias e horários de atendimento.
              <span className="block text-xs text-muted-foreground mt-1">
                Fuso horário: {timezone}. No chatbot, ao transferir para uma equipe, vale o horário dela (ou o padrão, se não houver).
              </span>
            </div>

            {horarios.map((dia, diaIdx) => (
              <div key={dia.dia} className="border-b border-border pb-4 last:border-b-0 last:pb-0">
                <div className="flex items-center justify-between mb-2">
                  <span className="font-semibold text-lg text-foreground">{dia.dia}</span>
                  <div className="flex gap-2">
                    {diaIdx > 0 && (
                      <button
                        type="button"
                        className="text-xs px-3 py-1 rounded bg-muted text-muted-foreground hover:bg-muted/80 border border-border"
                        onClick={() => handleCopiarAcima(diaIdx)}
                      >
                        Copiar horário acima
                      </button>
                    )}
                    <button
                      type="button"
                      className="text-xs px-3 py-1 rounded bg-gradient-to-r from-orange-500 to-yellow-500 hover:from-orange-600 hover:to-yellow-600 text-white shadow-lg hover:shadow-xl transition-all duration-200"
                      onClick={() => handleAddPeriodo(diaIdx)}
                    >
                      + Novo período
                    </button>
                  </div>
                </div>
                {dia.periodos.length === 0 && (
                  <div className="text-muted-foreground text-sm ml-2">Loja fechada.</div>
                )}
                {dia.periodos.map((periodo, periodoIdx) => (
                  <div key={periodoIdx} className="flex items-center gap-2 mb-2 ml-2 flex-wrap">
                    <input
                      type="time"
                      value={periodo.inicio}
                      onChange={(e) => handlePeriodoChange(diaIdx, periodoIdx, 'inicio', e.target.value)}
                      className="input bg-background text-foreground border border-border rounded px-2 py-1"
                      required
                    />
                    <span className="text-muted-foreground">até</span>
                    <input
                      type="time"
                      value={periodo.fim}
                      onChange={(e) => handlePeriodoChange(diaIdx, periodoIdx, 'fim', e.target.value)}
                      className="input bg-background text-foreground border border-border rounded px-2 py-1"
                      required
                    />
                    <button
                      type="button"
                      className="text-xs px-2 py-1 rounded bg-red-600 hover:bg-red-700 text-white"
                      onClick={() => handleRemovePeriodo(diaIdx, periodoIdx)}
                    >
                      Remover
                    </button>
                  </div>
                ))}
              </div>
            ))}
          </section>

          <div className="flex justify-end">
            <button
              type="submit"
              className="bg-primary text-primary-foreground px-6 py-2 rounded-lg font-medium hover:opacity-90 transition"
              disabled={saving || loading || (selectedTarget === 'global' && !provedorId)}
            >
              {saving ? 'Salvando...' : 'Salvar'}
            </button>
          </div>
        </form>
      )}
    </div>
  );
}
