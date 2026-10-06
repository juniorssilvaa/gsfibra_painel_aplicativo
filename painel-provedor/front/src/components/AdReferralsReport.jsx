import { useCallback, useEffect, useState } from 'react';
import axios from 'axios';
import { Megaphone, MousePointerClick, Users, UserPlus, ExternalLink, RefreshCw } from 'lucide-react';
import { Card, CardContent } from '@/components/ui/card';
import MetricCard from './dashboard/MetricCard';

function formatNumber(value) {
  return new Intl.NumberFormat('pt-BR').format(Number(value) || 0);
}

function formatDateTime(iso) {
  if (!iso) return '—';
  const date = new Date(iso);
  return Number.isNaN(date.getTime())
    ? '—'
    : date.toLocaleString('pt-BR', { dateStyle: 'short', timeStyle: 'short' });
}

function AdThumbnail({ url }) {
  const [broken, setBroken] = useState(false);
  if (!url || broken) {
    return (
      <div className="h-12 w-12 shrink-0 rounded-lg border border-border bg-muted flex items-center justify-center">
        <Megaphone className="h-5 w-5 text-muted-foreground" />
      </div>
    );
  }
  return (
    <img
      src={url}
      alt=""
      onError={() => setBroken(true)}
      className="h-12 w-12 shrink-0 rounded-lg border border-border object-cover"
    />
  );
}

export default function AdReferralsReport({ provedorId, days }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError(false);
    try {
      const token = localStorage.getItem('auth_token') || localStorage.getItem('token');
      const res = await axios.get('/api/ad-referrals/report/', {
        params: { days, provedor_id: provedorId },
        headers: token ? { Authorization: `Token ${token}` } : {},
        skipErrorToast: true,
      });
      setData(res.data);
    } catch (_) {
      setError(true);
    } finally {
      setLoading(false);
    }
  }, [days, provedorId]);

  useEffect(() => {
    load();
  }, [load]);

  const summary = data?.summary || {};
  const ads = data?.ads || [];
  const valueOf = (key) => (loading && !data ? '—' : formatNumber(summary[key]));

  return (
    <Card className="bg-card border-border">
      <CardContent className="p-6 space-y-5">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <h3 className="text-lg font-semibold text-foreground">Anúncios · Clique para WhatsApp</h3>
            <p className="text-sm text-muted-foreground">
              Clientes que iniciaram conversa clicando em um anúncio ou publicação da Meta
            </p>
          </div>
          <button
            type="button"
            onClick={load}
            disabled={loading}
            className="p-2 rounded-lg bg-muted hover:bg-muted/80 transition disabled:opacity-50"
            title="Atualizar"
          >
            <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
          </button>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
          <MetricCard title="Entradas por anúncio" value={valueOf('entries')} icon={MousePointerClick} color="text-blue-500" />
          <MetricCard title="Contatos" value={valueOf('contacts')} subtitle="únicos" icon={Users} color="text-green-500" />
          <MetricCard title="Contatos novos" value={valueOf('new_contacts')} subtitle="primeiro contato" icon={UserPlus} color="text-orange-500" />
          <MetricCard title="Anúncios" value={valueOf('ads')} subtitle="com entradas" icon={Megaphone} color="text-yellow-500" />
        </div>

        {error ? (
          <div className="rounded-xl border border-border p-6 text-center text-sm text-muted-foreground">
            Não foi possível carregar as entradas por anúncio. Tente atualizar.
          </div>
        ) : !loading && ads.length === 0 ? (
          <div className="rounded-xl border border-border p-6 text-center text-sm text-muted-foreground">
            Nenhuma conversa vinda de anúncio no período. As entradas passam a ser registradas quando o cliente
            clica em um anúncio de Clique para WhatsApp do seu número oficial.
          </div>
        ) : ads.length > 0 ? (
          <div className="overflow-x-auto rounded-xl border border-border">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-border bg-muted/30 text-left text-muted-foreground">
                  <th className="px-4 py-3 font-semibold">Anúncio</th>
                  <th className="px-4 py-3 font-semibold">Entradas</th>
                  <th className="px-4 py-3 font-semibold">Contatos</th>
                  <th className="px-4 py-3 font-semibold">Novos</th>
                  <th className="px-4 py-3 font-semibold">Última entrada</th>
                </tr>
              </thead>
              <tbody>
                {ads.map((ad) => (
                  <tr key={ad.source_id || ad.headline} className="border-b border-border/60 last:border-0">
                    <td className="px-4 py-3">
                      <div className="flex items-center gap-3 min-w-[240px]">
                        <AdThumbnail url={ad.thumbnail_url} />
                        <div className="min-w-0">
                          <p className="font-medium text-foreground truncate max-w-[360px]">
                            {ad.headline || (ad.source_type === 'post' ? 'Publicação' : 'Anúncio sem título')}
                          </p>
                          <p className="text-xs text-muted-foreground flex items-center gap-2">
                            <span>{ad.source_type === 'post' ? 'Publicação' : 'Anúncio'} {ad.source_id}</span>
                            {ad.source_url && (
                              <a
                                href={ad.source_url}
                                target="_blank"
                                rel="noopener noreferrer"
                                className="inline-flex items-center gap-1 text-primary hover:underline"
                              >
                                abrir <ExternalLink className="h-3 w-3" />
                              </a>
                            )}
                          </p>
                        </div>
                      </div>
                    </td>
                    <td className="px-4 py-3 font-semibold text-foreground">{formatNumber(ad.entries)}</td>
                    <td className="px-4 py-3 text-foreground">{formatNumber(ad.contacts)}</td>
                    <td className="px-4 py-3 text-foreground">{formatNumber(ad.new_contacts)}</td>
                    <td className="px-4 py-3 text-muted-foreground">{formatDateTime(ad.last_entry_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : null}
      </CardContent>
    </Card>
  );
}
