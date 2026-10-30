import React, { Suspense, lazy, useEffect } from 'react';
import { NavLink, useLocation, useNavigate } from 'react-router-dom';
import {
  BarChart3,
  Smartphone,
  LayoutDashboard,
  Users,
  MessageSquare,
  Workflow,
  Heart,
} from 'lucide-react';
import RelatorioEmDesenvolvimento from './RelatorioEmDesenvolvimento';

const RelatorioVisaoGeral = lazy(() => import('./RelatorioVisaoGeral'));
const RelatorioCanais = lazy(() => import('./RelatorioCanais'));
const RelatorioSatisfacao = lazy(() => import('./RelatorioSatisfacao'));

const TOP_TABS = [
  { id: 'atendentes', label: 'Atendentes' },
  { id: 'canais', label: 'Canais' },
  { id: 'satisfacao', label: 'Pesquisa de Satisfação' },
  { id: 'ligacao', label: 'Ligação' },
];

const CANAIS_NAV = [
  { id: 'total-geral', label: 'Total Geral', icon: BarChart3 },
  { id: 'disparo', label: 'Disparo', icon: Smartphone },
];

const SATISFACAO_NAV = [
  { id: 'dashboard', label: 'Dashboard', icon: LayoutDashboard },
  { id: 'atendentes', label: 'Atendentes', icon: Users },
  { id: 'respostas', label: 'Respostas', icon: MessageSquare },
  { id: 'automacao', label: 'Automação', icon: Workflow },
  { id: 'classificacao', label: 'Classificação de Atendimento', icon: Heart },
];

const TOP_IDS = new Set(TOP_TABS.map((t) => t.id));
const CANAIS_LEFT = new Set(CANAIS_NAV.map((i) => i.id));
const SATISFACAO_LEFT = new Set(SATISFACAO_NAV.map((i) => i.id));

function parseRelatorioPath(pathname) {
  const after = String(pathname || '').split('/relatorio')[1] || '';
  const segs = after.split('/').filter(Boolean);
  if (!segs.length) {
    return { top: 'atendentes', left: 'visao-geral' };
  }
  if (segs[0] === 'atendentes') {
    return { top: 'atendentes', left: 'visao-geral' };
  }
  if (segs[0] === 'canais') {
    const left = CANAIS_LEFT.has(segs[1]) ? segs[1] : 'total-geral';
    return { top: 'canais', left };
  }
  if (segs[0] === 'satisfacao') {
    const left = SATISFACAO_LEFT.has(segs[1]) ? segs[1] : 'dashboard';
    return { top: 'satisfacao', left };
  }
  if (segs[0] === 'ligacao') {
    return { top: 'ligacao', left: 'visao-geral' };
  }
  if (TOP_IDS.has(segs[0])) {
    return { top: segs[0], left: 'visao-geral' };
  }
  return { top: 'atendentes', left: 'visao-geral' };
}

function tabPath(provedorId, tabId) {
  const base = `/app/accounts/${provedorId}/relatorio`;
  if (tabId === 'atendentes') return `${base}/atendentes/visao-geral`;
  if (tabId === 'canais') return `${base}/canais/total-geral`;
  if (tabId === 'satisfacao') return `${base}/satisfacao/dashboard`;
  return `${base}/${tabId}`;
}

class RelatorioPaneError extends React.Component {
  constructor(props) {
    super(props);
    this.state = { error: null };
  }

  static getDerivedStateFromError(error) {
    return { error };
  }

  render() {
    if (this.state.error) {
      return (
        <div className="p-6 text-sm text-destructive">
          Não foi possível abrir este relatório. Recarregue a página e tente de novo.
        </div>
      );
    }
    return this.props.children;
  }
}

function LeftNav({ items, base, left }) {
  return (
    <aside className="w-56 shrink-0 border-r border-border bg-card/40 overflow-y-auto">
      <nav className="py-3 px-2 space-y-0.5">
        {items.map((item) => {
          const Icon = item.icon;
          const active = left === item.id;
          return (
            <NavLink
              key={item.id}
              to={`${base}/${item.id}`}
              end
              className={`flex items-center gap-2.5 rounded-md px-3 py-2 text-sm transition-colors ${
                active
                  ? 'bg-muted text-foreground font-medium'
                  : 'text-muted-foreground hover:bg-muted/60 hover:text-foreground'
              }`}
            >
              <Icon className="w-4 h-4 shrink-0" />
              <span className="truncate">{item.label}</span>
            </NavLink>
          );
        })}
      </nav>
    </aside>
  );
}

export default function RelatorioPage({ provedorId }) {
  const location = useLocation();
  const navigate = useNavigate();
  const { top, left } = parseRelatorioPath(location.pathname);
  const base = `/app/accounts/${provedorId}/relatorio`;

  useEffect(() => {
    if (!provedorId) return;
    if (/\/relatorio\/?$/.test(location.pathname)) {
      navigate(`${base}/atendentes/visao-geral`, { replace: true });
      return;
    }
    if (/\/relatorio\/atendentes\/?$/.test(location.pathname)) {
      navigate(`${base}/atendentes/visao-geral`, { replace: true });
      return;
    }
    if (/\/relatorio\/atendentes\/(?!visao-geral\/?$).+/.test(location.pathname)) {
      navigate(`${base}/atendentes/visao-geral`, { replace: true });
      return;
    }
    if (/\/relatorio\/visao-geral\/?$/.test(location.pathname)) {
      navigate(`${base}/atendentes/visao-geral`, { replace: true });
      return;
    }
    if (/\/relatorio\/canais\/?$/.test(location.pathname)) {
      navigate(`${base}/canais/total-geral`, { replace: true });
      return;
    }
    if (/\/relatorio\/satisfacao\/?$/.test(location.pathname)) {
      navigate(`${base}/satisfacao/dashboard`, { replace: true });
    }
  }, [location.pathname, navigate, provedorId, base]);

  const leftNav = top === 'canais'
    ? { items: CANAIS_NAV, prefix: `${base}/canais` }
    : top === 'satisfacao'
      ? { items: SATISFACAO_NAV, prefix: `${base}/satisfacao` }
      : null;

  const showVisaoGeral = top === 'atendentes';
  const showCanais = top === 'canais' && (left === 'total-geral' || left === 'disparo');
  const showSatisfacao = top === 'satisfacao' && left === 'dashboard';

  return (
    <div className="h-full w-full min-h-0 flex flex-col bg-background">
      <header className="shrink-0 border-b border-border px-6 pt-5">
        <h1 className="text-2xl font-bold text-foreground mb-4">Relatórios</h1>
        <nav className="flex flex-wrap gap-x-6">
          {TOP_TABS.map((tab) => {
            const active = top === tab.id;
            return (
              <NavLink
                key={tab.id}
                to={tabPath(provedorId, tab.id)}
                className={`relative pb-3 text-sm transition-colors ${
                  active
                    ? 'text-foreground font-medium'
                    : 'text-muted-foreground hover:text-foreground'
                }`}
              >
                {tab.label}
                {active && (
                  <span className="absolute left-0 right-0 bottom-0 h-0.5 rounded-full bg-foreground" />
                )}
              </NavLink>
            );
          })}
        </nav>
      </header>

      <div className="flex-1 min-h-0 flex">
        {leftNav && <LeftNav items={leftNav.items} base={leftNav.prefix} left={left} />}

        <div className="flex-1 min-w-0 min-h-0 overflow-y-auto">
          {showVisaoGeral ? (
            <RelatorioPaneError>
              <Suspense fallback={<div className="p-6 text-sm text-muted-foreground">Carregando relatório…</div>}>
                <RelatorioVisaoGeral provedorId={provedorId} />
              </Suspense>
            </RelatorioPaneError>
          ) : showCanais ? (
            <RelatorioPaneError>
              <Suspense fallback={<div className="p-6 text-sm text-muted-foreground">Carregando relatório…</div>}>
                <RelatorioCanais provedorId={provedorId} modo={left === 'disparo' ? 'disparo' : 'geral'} />
              </Suspense>
            </RelatorioPaneError>
          ) : showSatisfacao ? (
            <RelatorioPaneError>
              <Suspense fallback={<div className="p-6 text-sm text-muted-foreground">Carregando relatório…</div>}>
                <RelatorioSatisfacao provedorId={provedorId} />
              </Suspense>
            </RelatorioPaneError>
          ) : (
            <RelatorioEmDesenvolvimento />
          )}
        </div>
      </div>
    </div>
  );
}
