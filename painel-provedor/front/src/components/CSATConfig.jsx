import React, { useEffect, useState } from 'react';
import axios from 'axios';
import { Clock, MessageCircle, ArrowLeft } from 'lucide-react';
import { useNavigate } from 'react-router-dom';

export default function CSATConfig({ provedorId }) {
  const navigate = useNavigate();
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');

  const [delayValue, setDelayValue] = useState(2);
  const [delayUnit, setDelayUnit] = useState('minutos'); // minutos | horas | dias

  const [sendOnBotInactivity, setSendOnBotInactivity] = useState(true);

  const [enforceMinInterval, setEnforceMinInterval] = useState(true);
  const [minIntervalValue, setMinIntervalValue] = useState(24);
  const [minIntervalUnit, setMinIntervalUnit] = useState('horas'); // horas | dias

  const authHeaders = () => ({
    Authorization: `Token ${localStorage.getItem('auth_token') || localStorage.getItem('token') || ''}`,
  });

  const unitToMinutes = (value, unit) => {
    const v = Number(value);
    if (!Number.isFinite(v) || v <= 0) return 0;
    if (unit === 'horas') return Math.round(v * 60);
    if (unit === 'dias') return Math.round(v * 24 * 60);
    return Math.round(v);
  };

  const unitToHours = (value, unit) => {
    const v = Number(value);
    if (!Number.isFinite(v) || v <= 0) return 0;
    if (unit === 'dias') return Math.round(v * 24);
    return Math.round(v);
  };

  const ToggleSwitch = ({ checked, onChange, label }) => {
    return (
      <button
        type="button"
        role="switch"
        aria-checked={checked}
        onClick={() => onChange(!checked)}
        className={[
          'relative inline-flex items-center h-6 w-11 rounded-full transition-colors',
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
  };

  useEffect(() => {
    async function load() {
      setLoading(true);
      setError('');
      setSuccess('');
      try {
        const res = await axios.get('/api/provedores/', { headers: authHeaders() });
        const prov = res.data?.results?.find((p) => String(p.id) === String(provedorId)) || res.data?.results?.[0];
        if (prov) {
          const dMin = Number.isFinite(Number(prov.csat_delay_minutes)) ? Number(prov.csat_delay_minutes) : 2;
          setDelayValue(dMin > 0 ? dMin : 2);
          setDelayUnit('minutos');

          const enabled = typeof prov.csat_send_on_bot_inactivity_closure === 'boolean'
            ? prov.csat_send_on_bot_inactivity_closure
            : true;
          setSendOnBotInactivity(enabled);

          const enforce = typeof prov.csat_enforce_min_interval === 'boolean'
            ? prov.csat_enforce_min_interval
            : true;
          setEnforceMinInterval(enforce);

          const minH = Number.isFinite(Number(prov.csat_min_interval_hours)) ? Number(prov.csat_min_interval_hours) : 24;
          setMinIntervalValue(minH > 0 ? minH : 24);
          setMinIntervalUnit('horas');
        }
      } catch (e) {
        setError('Erro ao carregar configuração do CSAT.');
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

    try {
      const delayMin = unitToMinutes(delayValue, delayUnit);
      const minHours = unitToHours(minIntervalValue, minIntervalUnit);
      await axios.patch(
        `/api/provedores/${provedorId}/`,
        {
          csat_delay_minutes: delayMin > 0 ? delayMin : 2,
          csat_send_on_bot_inactivity_closure: sendOnBotInactivity,
          csat_enforce_min_interval: enforceMinInterval,
          csat_min_interval_hours: minHours > 0 ? minHours : 24,
        },
        { headers: authHeaders() }
      );
      setSuccess('Configuração do CSAT salva com sucesso.');
    } catch (e) {
      setError('Erro ao salvar configuração do CSAT.');
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="flex-1 p-6 bg-background overflow-y-auto relative">
      <div className="max-w-3xl mx-auto">
        <button
          type="button"
          onClick={() => navigate(`/app/accounts/${provedorId}/regras-atendimento`)}
          className="absolute left-6 top-6 px-4 py-2 rounded-lg bg-primary text-primary-foreground hover:opacity-90 transition-opacity inline-flex items-center gap-2"
        >
          <ArrowLeft className="w-4 h-4" />
          Voltar
        </button>

        <div className="mb-6 pt-14">
          <h1 className="text-3xl font-bold text-foreground mb-2">Configurar CSAT</h1>
          <p className="text-muted-foreground">
            Ajuste quando a pesquisa será disparada e se o bot deve enviar o CSAT ao encerrar por inatividade.
          </p>
        </div>

        <div className="bg-card border border-border rounded-xl shadow-sm p-6">
          {loading ? (
            <div className="text-muted-foreground">Carregando...</div>
          ) : (
            <form onSubmit={handleSubmit} className="space-y-6">
              <div className="space-y-2">
                <div className="flex items-center gap-2">
                  <Clock className="w-5 h-5 text-primary" />
                  <label className="text-sm font-semibold text-foreground">Tempo do disparo após resolução</label>
                </div>
                <div className="flex gap-3">
                  <input
                    type="number"
                    min={1}
                    step={1}
                    value={delayValue}
                    onChange={(e) => setDelayValue(Number(e.target.value))}
                    className="flex-1 px-3 py-2 border border-border rounded-lg bg-background text-foreground focus:outline-none focus:ring-2 focus:ring-primary/40"
                  />
                  <select
                    value={delayUnit}
                    onChange={(e) => setDelayUnit(e.target.value)}
                    className="w-[160px] px-3 py-2 border border-border rounded-lg bg-background text-foreground focus:outline-none focus:ring-2 focus:ring-primary/40"
                  >
                    <option value="minutos">Minutos</option>
                    <option value="horas">Horas</option>
                    <option value="dias">Dias</option>
                  </select>
                </div>
                <div className="text-xs text-muted-foreground">
                  Usado para agendar a pesquisa quando o CSAT é disparado automaticamente após encerramento (ex.: fechamento por bot).
                </div>
              </div>

              <div className="space-y-2">
                <div className="flex items-center justify-between gap-3">
                  <div className="flex items-center gap-2">
                    <MessageCircle className="w-5 h-5 text-primary" />
                    <div className="text-sm font-semibold text-foreground">
                      Enviar CSAT no encerramento por inatividade do bot
                    </div>
                  </div>
                  <ToggleSwitch
                    checked={sendOnBotInactivity}
                    onChange={setSendOnBotInactivity}
                    label="Enviar CSAT no encerramento por inatividade"
                  />
                </div>
                <div className="text-xs text-muted-foreground">
                  Se desligado, o bot e a IA não disparam a pesquisa ao encerrar automaticamente
                  (inatividade, encerramento pela IA, nós de fechamento do chatbot).
                </div>
              </div>

              <div className="space-y-2 pt-2">
                <div className="flex items-center justify-between gap-3">
                  <div className="text-sm font-semibold text-foreground">
                    Intervalo mínimo entre envios de CSAT
                  </div>
                  <ToggleSwitch
                    checked={enforceMinInterval}
                    onChange={setEnforceMinInterval}
                    label="Intervalo mínimo entre envios"
                  />
                </div>
                <div className="text-xs text-muted-foreground">
                  Se ativado, o sistema não envia um novo CSAT se o cliente já tiver sido avaliado dentro do intervalo configurado.
                </div>

                {enforceMinInterval && (
                  <div className="flex gap-3">
                    <input
                      type="number"
                      min={1}
                      step={1}
                      value={minIntervalValue}
                      onChange={(e) => setMinIntervalValue(Number(e.target.value))}
                      className="flex-1 px-3 py-2 border border-border rounded-lg bg-background text-foreground focus:outline-none focus:ring-2 focus:ring-primary/40"
                    />
                    <select
                      value={minIntervalUnit}
                      onChange={(e) => setMinIntervalUnit(e.target.value)}
                      className="w-[160px] px-3 py-2 border border-border rounded-lg bg-background text-foreground focus:outline-none focus:ring-2 focus:ring-primary/40"
                    >
                      <option value="horas">Horas</option>
                      <option value="dias">Dias</option>
                    </select>
                  </div>
                )}
              </div>

              {error && <div className="text-sm text-red-400">{error}</div>}
              {success && <div className="text-sm text-emerald-400">{success}</div>}

              <div className="flex justify-end gap-3">
                <button
                  type="submit"
                  disabled={saving}
                  className="px-4 py-2 rounded-lg bg-primary text-primary-foreground disabled:opacity-50"
                >
                  {saving ? 'Salvando...' : 'Salvar'}
                </button>
              </div>
            </form>
          )}
        </div>
      </div>
    </div>
  );
}

