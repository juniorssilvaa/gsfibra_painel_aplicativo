import React, { useCallback, useEffect, useState } from 'react';
import { AlertTriangle, ExternalLink, RefreshCw } from 'lucide-react';
import axios from 'axios';
import { Link } from 'react-router-dom';

function formatMoney(value) {
  if (value == null || Number.isNaN(Number(value))) return '—';
  return Number(value).toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' });
}

function formatDate(iso) {
  if (!iso) return '—';
  const [y, m, d] = String(iso).split('-');
  if (!y || !m || !d) return iso;
  return `${d}/${m}/${y}`;
}

export default function DashboardAsaasOverdue() {
  const [loading, setLoading] = useState(true);
  const [data, setData] = useState({ total: 0, items: [], total_value: 0, asaas_configured: true });
  const [error, setError] = useState('');

  const fetchOverdue = useCallback(async () => {
    try {
      setLoading(true);
      setError('');
      const token = localStorage.getItem('token');
      const res = await axios.get('/api/provedores/asaas-overdue/', {
        headers: { Authorization: `Token ${token}` },
      });
      setData(res.data || { total: 0, items: [] });
      if (res.data?.error && res.data?.asaas_configured) {
        setError(res.data.error);
      }
    } catch (err) {
      console.error('Erro ao carregar inadimplentes Asaas:', err);
      setError('Não foi possível consultar o Asaas.');
      setData({ total: 0, items: [], asaas_configured: false });
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchOverdue();
  }, [fetchOverdue]);

  const total = data.total ?? 0;
  const items = data.items || [];

  return (
    <div className="bg-card rounded-xl shadow-lg border border-border overflow-hidden mb-8">
      <div className="bg-gradient-to-r from-red-950/50 to-orange-950/40 px-5 py-4 border-b border-border">
        <div className="flex flex-wrap items-center justify-between gap-4">
          <div className="flex items-center gap-3">
            <div className="p-2 rounded-lg bg-red-500/15 border border-red-500/25">
              <AlertTriangle className="w-6 h-6 text-red-400" />
            </div>
            <div>
              <p className="text-sm text-muted-foreground">Cobrança Asaas</p>
              <h2 className="text-xl font-bold text-foreground">Provedores em atraso</h2>
            </div>
          </div>
          <div className="flex items-center gap-4">
            <div className="text-right">
              <p className="text-3xl font-black tabular-nums text-red-400">{loading ? '…' : total}</p>
              <p className="text-xs text-muted-foreground">
                {total === 1 ? 'provedor com fatura vencida' : 'provedores com fatura vencida'}
              </p>
            </div>
            {data.total_value > 0 && (
              <div className="text-right border-l border-border pl-4">
                <p className="text-lg font-semibold text-foreground">{formatMoney(data.total_value)}</p>
                <p className="text-xs text-muted-foreground">valor em aberto</p>
              </div>
            )}
            <button
              type="button"
              onClick={fetchOverdue}
              disabled={loading}
              className="p-2 rounded-lg border border-border hover:bg-muted/50 text-muted-foreground hover:text-foreground transition-colors disabled:opacity-50"
              title="Atualizar"
            >
              <RefreshCw className={`w-5 h-5 ${loading ? 'animate-spin' : ''}`} />
            </button>
          </div>
        </div>
      </div>

      <div className="p-5">
        {!data.asaas_configured && (
          <p className="text-sm text-amber-400">
            Configure o token do Asaas em Integrações para ver os provedores em atraso.
          </p>
        )}
        {error && (
          <p className="text-sm text-amber-400 mb-3">{error}</p>
        )}
        {loading && (
          <p className="text-sm text-muted-foreground">Consultando faturas vencidas no Asaas…</p>
        )}
        {!loading && total === 0 && data.asaas_configured && !error && (
          <p className="text-sm text-muted-foreground">Nenhum provedor com pagamento em atraso no Asaas.</p>
        )}
        {!loading && total > 0 && (
          <div className="overflow-x-auto rounded-lg border border-border">
            <table className="w-full text-sm">
              <thead>
                <tr className="bg-muted/30 text-left text-xs uppercase tracking-wider text-muted-foreground">
                  <th className="px-4 py-3 w-16">ID</th>
                  <th className="px-4 py-3">Provedor</th>
                  <th className="px-4 py-3">Vencimento</th>
                  <th className="px-4 py-3">Atraso</th>
                  <th className="px-4 py-3">Valor</th>
                  <th className="px-4 py-3">Painel</th>
                  <th className="px-4 py-3 text-right">Fatura</th>
                </tr>
              </thead>
              <tbody>
                {items.map((row) => {
                  const pay = row.payment;
                  const daysLate = row.days_late ?? pay?.days_late ?? 0;
                  const invoiceUrl = pay?.invoiceUrl;
                  return (
                    <tr
                      key={row.id}
                      className="border-t border-border hover:bg-muted/20 transition-colors"
                    >
                      <td className="px-4 py-3">
                        <span className="font-mono text-xs font-bold tabular-nums text-sky-300">
                          {row.id}
                        </span>
                      </td>
                      <td className="px-4 py-3">
                        <div className="font-medium text-foreground">{row.nome}</div>
                        <div className="text-xs text-muted-foreground">
                          {(row.subscription_status || '').toUpperCase() === 'OVERDUE'
                            ? 'Assinatura OVERDUE'
                            : row.source === 'local_status'
                              ? 'Status local (sem cobrança na consulta)'
                              : 'Fatura vencida'}
                          {!row.is_active && (
                            <span className="ml-2 text-red-400">· suspenso</span>
                          )}
                        </div>
                      </td>
                      <td className="px-4 py-3 text-foreground">{formatDate(pay?.dueDate)}</td>
                      <td className="px-4 py-3">
                        <span
                          className={`inline-flex rounded-md px-2 py-0.5 text-xs font-semibold ${
                            daysLate >= 4
                              ? 'bg-red-500/15 text-red-300'
                              : 'bg-amber-500/15 text-amber-300'
                          }`}
                        >
                          {daysLate} {daysLate === 1 ? 'dia' : 'dias'}
                        </span>
                      </td>
                      <td className="px-4 py-3 font-medium text-foreground">
                        {formatMoney(pay?.value)}
                      </td>
                      <td className="px-4 py-3">
                        <Link
                          to="/admin/provedores"
                          className="text-xs text-primary hover:underline"
                        >
                          Ver provedor
                        </Link>
                      </td>
                      <td className="px-4 py-3 text-right">
                        {invoiceUrl ? (
                          <a
                            href={invoiceUrl}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="inline-flex items-center gap-1 text-xs text-primary hover:underline"
                          >
                            Abrir
                            <ExternalLink className="w-3 h-3" />
                          </a>
                        ) : (
                          <span className="text-xs text-muted-foreground">—</span>
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
