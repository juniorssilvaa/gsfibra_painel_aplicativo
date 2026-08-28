import React, { useEffect, useState } from 'react';
import axios from 'axios';
import { ArrowLeft, CalendarDays, Plus, Trash2 } from 'lucide-react';
import { useNavigate } from 'react-router-dom';

function emptyHoliday() {
  return {
    id: `tmp-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
    name: '',
    date: '',
    all_day: true,
    start_time: '12:00',
    end_time: '23:59',
    active: true,
  };
}

function normalizeHoliday(item) {
  const hasTimes = Boolean(item.start_time || item.end_time);
  const allDay = item.all_day === true
    ? true
    : item.all_day === false
      ? false
      : !hasTimes;

  return {
    id: item.id,
    name: item.name || '',
    date: item.date || '',
    all_day: allDay,
    start_time: item.start_time || '12:00',
    end_time: item.end_time || '23:59',
    active: item.active !== false,
  };
}

function formatDateBr(isoDate) {
  if (!isoDate || !/^\d{4}-\d{2}-\d{2}$/.test(isoDate)) return isoDate || '—';
  const [y, m, d] = isoDate.split('-');
  return `${d}/${m}/${y}`;
}

export default function AttendanceHolidaySettings({ provedorId }) {
  const navigate = useNavigate();
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');
  const [holidays, setHolidays] = useState([]);
  const [nationalHolidays, setNationalHolidays] = useState([]);

  const authHeaders = () => ({
    Authorization: `Token ${localStorage.getItem('auth_token') || localStorage.getItem('token') || ''}`,
  });

  useEffect(() => {
    async function load() {
      setLoading(true);
      setError('');
      try {
        const res = await axios.get(`/api/provedores/${provedorId}/`, { headers: authHeaders() });
        const loaded = Array.isArray(res.data.attendance_holidays) ? res.data.attendance_holidays : [];
        setHolidays(loaded.map(normalizeHoliday));
        const nationals = Array.isArray(res.data.national_holidays) ? res.data.national_holidays : [];
        setNationalHolidays(
          nationals.map((item) => ({
            id: item.id,
            name: item.name || '',
            date: item.date || '',
            active: item.active !== false,
          }))
        );
      } catch {
        setError('Erro ao carregar feriados.');
      } finally {
        setLoading(false);
      }
    }
    if (provedorId) load();
  }, [provedorId]);

  const updateHoliday = (index, field, value) => {
    setHolidays((prev) => prev.map((item, idx) => {
      if (idx !== index) return item;
      const next = { ...item, [field]: value };
      if (field === 'all_day' && value === false) {
        next.start_time = next.start_time || '12:00';
        next.end_time = next.end_time || '23:59';
      }
      return next;
    }));
  };

  const updateNationalActive = (index, active) => {
    setNationalHolidays((prev) =>
      prev.map((item, idx) => (idx === index ? { ...item, active } : item))
    );
  };

  const addHoliday = () => setHolidays((prev) => [...prev, emptyHoliday()]);
  const removeHoliday = (index) => setHolidays((prev) => prev.filter((_, idx) => idx !== index));

  const handleSubmit = async (e) => {
    e.preventDefault();
    setSaving(true);
    setError('');
    setSuccess('');

    const sanitized = holidays
      .map((item) => {
        const base = {
          id: item.id,
          name: String(item.name || '').trim(),
          date: String(item.date || '').trim(),
          active: item.active !== false,
          all_day: item.all_day !== false,
        };
        if (!base.all_day) {
          base.start_time = String(item.start_time || '12:00').trim();
          base.end_time = String(item.end_time || '23:59').trim();
        }
        return base;
      })
      .filter((item) => item.name && item.date);

    const nationalPayload = nationalHolidays.map((item) => ({
      id: item.id,
      active: item.active !== false,
    }));

    try {
      const res = await axios.patch(
        `/api/provedores/${provedorId}/`,
        {
          attendance_holidays: sanitized,
          attendance_national_holidays: nationalPayload,
        },
        { headers: authHeaders() }
      );
      setHolidays(sanitized.map(normalizeHoliday));
      const nationals = Array.isArray(res.data.national_holidays)
        ? res.data.national_holidays
        : nationalHolidays;
      setNationalHolidays(
        nationals.map((item) => ({
          id: item.id,
          name: item.name || '',
          date: item.date || '',
          active: item.active !== false,
        }))
      );
      setSuccess('Feriados salvos com sucesso.');
    } catch {
      setError('Erro ao salvar feriados.');
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

      <div className="flex items-center gap-3 mb-6 pt-14">
        <CalendarDays className="w-8 h-8 text-primary" />
        <div>
          <h1 className="text-2xl font-bold text-foreground">Feriados e datas especiais</h1>
          <p className="text-sm text-muted-foreground">
            Cadastre datas em que o atendimento humano segue uma regra especial.
            Feriados nacionais ativos entram no cálculo da IA e do chatbot.
          </p>
        </div>
      </div>

      {error && (
        <div className="mb-4 p-3 rounded-lg bg-red-500/10 text-red-500 border border-red-500/30">{error}</div>
      )}
      {success && (
        <div className="mb-4 p-3 rounded-lg bg-emerald-500/10 text-emerald-600 border border-emerald-500/30">{success}</div>
      )}

      <form onSubmit={handleSubmit} className="space-y-6 w-full max-w-none">
        <section className="bg-card border border-border rounded-xl p-6 space-y-4 w-full">
          <div className="flex items-center justify-between gap-4">
            <div>
              <h2 className="text-lg font-semibold text-foreground">Datas especiais do provedor</h2>
              <p className="text-sm text-muted-foreground">
                Por padrão, o feriado vale o dia inteiro. Se a empresa fechar só em parte do dia
                (ex.: a partir das 12h), desative &quot;Dia inteiro&quot; e informe o horário.
              </p>
            </div>
            <button
              type="button"
              onClick={addHoliday}
              className="inline-flex items-center gap-2 px-3 py-2 rounded-lg bg-primary text-primary-foreground text-sm font-medium hover:opacity-90"
            >
              <Plus className="w-4 h-4" />
              Novo feriado
            </button>
          </div>

          {holidays.length === 0 && (
            <div className="rounded-lg border border-dashed border-border p-4 text-sm text-muted-foreground">
              Nenhum feriado cadastrado.
            </div>
          )}

          <div className="space-y-3">
            {holidays.map((item, index) => (
              <div
                key={item.id || `${item.date}-${index}`}
                className="rounded-lg border border-border p-4 space-y-3"
              >
                <div className="grid grid-cols-1 md:grid-cols-[minmax(180px,1.5fr)_160px_120px_90px_auto] gap-3 items-end">
                  <div>
                    <label className="block text-sm font-medium text-foreground mb-2">Nome</label>
                    <input
                      type="text"
                      value={item.name || ''}
                      onChange={(e) => updateHoliday(index, 'name', e.target.value)}
                      placeholder="Ex.: Aniversário da cidade"
                      className="w-full rounded-lg border border-border bg-background px-3 py-2 text-sm text-foreground"
                    />
                  </div>
                  <div>
                    <label className="block text-sm font-medium text-foreground mb-2">Data</label>
                    <input
                      type="date"
                      value={item.date || ''}
                      onChange={(e) => updateHoliday(index, 'date', e.target.value)}
                      className="w-full rounded-lg border border-border bg-background px-3 py-2 text-sm text-foreground"
                    />
                  </div>
                  <div>
                    <label className="block text-sm font-medium text-foreground mb-2">Dia inteiro</label>
                    <select
                      value={item.all_day !== false ? 'true' : 'false'}
                      onChange={(e) => updateHoliday(index, 'all_day', e.target.value === 'true')}
                      className="w-full rounded-lg border border-border bg-background px-3 py-2 text-sm text-foreground"
                    >
                      <option value="true">Sim</option>
                      <option value="false">Não</option>
                    </select>
                  </div>
                  <div>
                    <label className="block text-sm font-medium text-foreground mb-2">Ativo</label>
                    <select
                      value={item.active === false ? 'false' : 'true'}
                      onChange={(e) => updateHoliday(index, 'active', e.target.value === 'true')}
                      className="w-full rounded-lg border border-border bg-background px-3 py-2 text-sm text-foreground"
                    >
                      <option value="true">Sim</option>
                      <option value="false">Não</option>
                    </select>
                  </div>
                  <button
                    type="button"
                    onClick={() => removeHoliday(index)}
                    className="inline-flex items-center justify-center gap-2 px-3 py-2 rounded-lg bg-red-600 text-white text-sm font-medium hover:bg-red-700"
                  >
                    <Trash2 className="w-4 h-4" />
                    Remover
                  </button>
                </div>

                {item.all_day === false && (
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 max-w-md">
                    <div>
                      <label className="block text-sm font-medium text-foreground mb-2">Início do feriado</label>
                      <input
                        type="time"
                        value={item.start_time || '12:00'}
                        onChange={(e) => updateHoliday(index, 'start_time', e.target.value)}
                        className="w-full rounded-lg border border-border bg-background px-3 py-2 text-sm text-foreground"
                        required
                      />
                      <p className="text-xs text-muted-foreground mt-1">
                        A partir deste horário o atendimento humano é tratado como fora do expediente.
                      </p>
                    </div>
                    <div>
                      <label className="block text-sm font-medium text-foreground mb-2">Fim do feriado</label>
                      <input
                        type="time"
                        value={item.end_time || '23:59'}
                        onChange={(e) => updateHoliday(index, 'end_time', e.target.value)}
                        className="w-full rounded-lg border border-border bg-background px-3 py-2 text-sm text-foreground"
                        required
                      />
                      <p className="text-xs text-muted-foreground mt-1">
                        Após este horário volta a valer o horário comercial normal.
                      </p>
                    </div>
                  </div>
                )}
              </div>
            ))}
          </div>
        </section>

        <section className="bg-card border border-border rounded-xl p-6 space-y-4 w-full">
          <div>
            <h2 className="text-lg font-semibold text-foreground">Feriados nacionais</h2>
            <p className="text-sm text-muted-foreground">
              Lista oficial do ano. Você só pode ativar ou desativar.
            </p>
          </div>

          {nationalHolidays.length === 0 ? (
            <div className="rounded-lg border border-dashed border-border p-4 text-sm text-muted-foreground">
              Nenhum feriado nacional disponível.
            </div>
          ) : (
            <div className="space-y-3">
              {nationalHolidays.map((item, index) => (
                <div
                  key={item.id || `${item.date}-${index}`}
                  className="rounded-lg border border-border p-4"
                >
                  <div className="grid grid-cols-1 md:grid-cols-[minmax(180px,1.5fr)_160px_120px] gap-3 items-end">
                    <div>
                      <label className="block text-sm font-medium text-foreground mb-2">Nome</label>
                      <input
                        type="text"
                        value={item.name || ''}
                        readOnly
                        disabled
                        className="w-full rounded-lg border border-border bg-muted/40 px-3 py-2 text-sm text-foreground opacity-90 cursor-not-allowed"
                      />
                    </div>
                    <div>
                      <label className="block text-sm font-medium text-foreground mb-2">Data</label>
                      <input
                        type="text"
                        value={formatDateBr(item.date)}
                        readOnly
                        disabled
                        className="w-full rounded-lg border border-border bg-muted/40 px-3 py-2 text-sm text-foreground opacity-90 cursor-not-allowed"
                      />
                    </div>
                    <div>
                      <label className="block text-sm font-medium text-foreground mb-2">Ativo</label>
                      <select
                        value={item.active === false ? 'false' : 'true'}
                        onChange={(e) => updateNationalActive(index, e.target.value === 'true')}
                        className="w-full rounded-lg border border-border bg-background px-3 py-2 text-sm text-foreground"
                      >
                        <option value="true">Sim</option>
                        <option value="false">Não</option>
                      </select>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </section>

        <div className="flex justify-end">
          <button
            type="submit"
            disabled={saving}
            className="px-6 py-2 rounded-lg bg-primary text-primary-foreground font-medium hover:opacity-90 disabled:opacity-50"
          >
            {saving ? 'Salvando...' : 'Salvar feriados'}
          </button>
        </div>
      </form>
    </div>
  );
}
