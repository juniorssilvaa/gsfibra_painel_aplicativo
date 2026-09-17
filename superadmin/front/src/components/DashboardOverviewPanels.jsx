import React, { useMemo } from 'react';
import { Link } from 'react-router-dom';
import { Doughnut } from 'react-chartjs-2';
import { ensureChartJsRegistered } from '../lib/chartSetup';

ensureChartJsRegistered();

/** Paleta sólida dos pills "Contratos ativos" (Status Geral). */
export const STATUS_PILL = {
  burgundy: '#8B1E3F',
  royal: '#1E4DB7',
  ochre: '#A67C2D',
  purple: '#5B2C8A',
  gray: '#4A4A4A',
  forest: '#1B6B3A',
  petrol: '#1A5F6B',
};

function pct(part, total) {
  if (!total || total <= 0) return 0;
  return Math.min(100, Math.round((part / total) * 100));
}

export function StatusPill({ color, children, title }) {
  return (
    <span
      title={title}
      className="inline-flex items-center rounded-full px-3 py-1 text-xs font-semibold text-white shadow-sm whitespace-nowrap"
      style={{ backgroundColor: color }}
    >
      {children}
    </span>
  );
}

function MetricRow({ label, value, hint }) {
  return (
    <div className="flex items-baseline justify-between gap-4 py-2.5 border-b border-border last:border-0">
      <div className="min-w-0">
        <p className="text-sm text-foreground/90">{label}</p>
        {hint ? <p className="text-[11px] text-muted-foreground mt-0.5">{hint}</p> : null}
      </div>
      <span className="text-base font-semibold tabular-nums text-foreground underline decoration-primary/40 underline-offset-4 shrink-0">
        {value}
      </span>
    </div>
  );
}

function LegendDot({ color, label, value }) {
  return (
    <div className="flex items-center gap-2 text-xs text-muted-foreground">
      <span className="h-2 w-2 rounded-full shrink-0" style={{ backgroundColor: color }} />
      <span className="truncate">{label}</span>
      <span className="ml-auto font-semibold tabular-nums text-foreground">{value}</span>
    </div>
  );
}

function MiniPie({ labels, values, colors }) {
  const data = useMemo(
    () => ({
      labels,
      datasets: [{
        data: values,
        backgroundColor: colors,
        borderWidth: 2,
        borderColor: '#27272a',
      }],
    }),
    [labels, values, colors]
  );

  const options = useMemo(
    () => ({
      responsive: true,
      maintainAspectRatio: false,
      cutout: '58%',
      plugins: {
        legend: { display: false },
        tooltip: {
          backgroundColor: '#27272a',
          titleColor: '#fafaf9',
          bodyColor: '#e7e5e4',
          borderColor: '#3f3f46',
          borderWidth: 1,
        },
      },
    }),
    []
  );

  const hasData = values.some((v) => v > 0);
  if (!hasData) {
    return (
      <div className="h-36 flex items-center justify-center text-xs text-muted-foreground">
        Sem dados
      </div>
    );
  }

  return (
    <div className="h-36">
      <Doughnut data={data} options={options} />
    </div>
  );
}

function PanelShell({ title, subtitle, action, children }) {
  return (
    <section className="overflow-hidden rounded-xl border border-border bg-card shadow-lg">
      <div className="px-5 py-4 border-b border-border flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <h2 className="text-lg font-bold tracking-tight text-foreground">{title}</h2>
          {subtitle ? (
            <p className="text-sm text-muted-foreground mt-0.5">{subtitle}</p>
          ) : null}
        </div>
        {action}
      </div>
      <div className="px-5 py-5">{children}</div>
    </section>
  );
}

export function DashboardSystemPanel({ statsData, provedores = [] }) {
  const ativos = useMemo(() => provedores.filter((p) => p.is_active).length, [provedores]);
  const inativos = Math.max(0, (statsData.totalProvedores || 0) - ativos);
  const mediaUsuarios = statsData.totalProvedores
    ? Math.round((statsData.totalUsuarios || 0) / statsData.totalProvedores)
    : 0;
  const mediaConversas = statsData.totalProvedores
    ? Math.round((statsData.totalConversas || 0) / statsData.totalProvedores)
    : 0;

  return (
    <PanelShell
      title="Status Geral"
      subtitle="Provedores, usuários e conversas da plataforma"
    >
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        <div className="lg:col-span-4 space-y-4">
          <div>
            <p className="text-xs uppercase tracking-wider text-muted-foreground mb-1">Provedores</p>
            <p className="text-4xl font-black tabular-nums text-foreground leading-none">
              {statsData.totalProvedores}
            </p>
            <p className="text-xs text-muted-foreground mt-2">
              {pct(ativos, statsData.totalProvedores)}% ativos no sistema
            </p>
          </div>
          <MiniPie
            labels={['Ativos', 'Inativos']}
            values={[ativos, inativos]}
            colors={[STATUS_PILL.royal, STATUS_PILL.gray]}
          />
          <div className="space-y-2 pt-1">
            <LegendDot color={STATUS_PILL.royal} label="Ativos" value={ativos} />
            <LegendDot color={STATUS_PILL.gray} label="Inativos" value={inativos} />
          </div>
          <div className="flex flex-wrap gap-2 pt-1">
            <StatusPill color={STATUS_PILL.ochre}>
              Usuários ({statsData.totalUsuarios})
            </StatusPill>
            <StatusPill color={STATUS_PILL.petrol}>
              Conversas ({(statsData.totalConversas || 0).toLocaleString('pt-BR')})
            </StatusPill>
            <StatusPill color={STATUS_PILL.forest}>
              Média {mediaUsuarios} users
            </StatusPill>
            <StatusPill color={STATUS_PILL.purple}>
              Média {mediaConversas} conv.
            </StatusPill>
          </div>
        </div>

        <div className="lg:col-span-8 rounded-xl border border-border bg-muted/20 px-4 py-2">
          <MetricRow
            label="Provedores no sistema"
            value={statsData.totalProvedores}
            hint="Total cadastrado"
          />
          <MetricRow
            label="Receita mensal (assinaturas)"
            value={statsData.receitaMensal}
            hint="Agregado de planos"
          />
          <MetricRow
            label="Usuários dos provedores"
            value={statsData.totalUsuarios}
            hint="Soma users_count"
          />
          <MetricRow
            label="Conversas na plataforma"
            value={(statsData.totalConversas || 0).toLocaleString('pt-BR')}
            hint="Soma conversations_count"
          />
        </div>
      </div>
    </PanelShell>
  );
}

export function DashboardAppMobilePanel({ appStats }) {
  const totalProv = appStats.total_providers ?? 0;
  const ativos = appStats.active_providers ?? 0;
  const inativos = appStats.inactive_providers ?? 0;
  const users = appStats.total_app_users ?? 0;
  const devices = appStats.total_devices ?? 0;
  const admins = appStats.total_admins ?? 0;
  const pushPct = pct(devices, Math.max(users, 1));

  return (
    <PanelShell
      title="App Mobile"
      subtitle="Adoção do aplicativo do cliente por provedor"
      action={
        <Link
          to="/admin/app-mobile"
          className="text-sm font-medium text-primary hover:underline"
        >
          Gerenciar →
        </Link>
      }
    >
      <div className="grid grid-cols-1 gap-6">
        <div className="grid grid-cols-2 gap-4 items-center">
          <div className="space-y-3">
            <div className="rounded-xl border border-border bg-muted/20 p-4">
              <p className="text-xs text-muted-foreground mb-1">Clientes no app</p>
              <p className="text-3xl font-black tabular-nums text-foreground">{users}</p>
            </div>
            <div className="rounded-xl border border-border bg-muted/20 p-4">
              <p className="text-xs text-muted-foreground mb-1">Dispositivos push</p>
              <p className="text-3xl font-black tabular-nums text-foreground">{devices}</p>
              <p className="text-[11px] text-muted-foreground mt-1">{pushPct}% cobertura</p>
            </div>
          </div>
          <div>
            <MiniPie
              labels={['Apps ativos', 'Apps inativos']}
              values={[ativos, inativos]}
              colors={[STATUS_PILL.forest, STATUS_PILL.burgundy]}
            />
            <div className="space-y-1.5 mt-2">
              <LegendDot color={STATUS_PILL.forest} label="Ativos" value={ativos} />
              <LegendDot color={STATUS_PILL.burgundy} label="Inativos" value={inativos} />
            </div>
          </div>
        </div>

        <div className="rounded-xl border border-border bg-muted/20 px-4 py-2">
          <MetricRow label="Provedores com app configurado" value={totalProv} />
          <MetricRow label="Apps ativos" value={ativos} hint="Liberados para o cliente" />
          <MetricRow
            label="Apps inativos"
            value={inativos}
            hint={inativos > 0 ? 'Requer atenção' : 'Nenhum parado'}
          />
          <MetricRow label="Admins de painel com provedor" value={admins} />
          <MetricRow label="Dispositivos com push registrado" value={devices} />
        </div>

        <div className="flex flex-wrap gap-2">
          <StatusPill color={STATUS_PILL.ochre}>Clientes ({users})</StatusPill>
          <StatusPill color={STATUS_PILL.royal}>Admins ({admins})</StatusPill>
          <StatusPill color={STATUS_PILL.petrol}>Devices ({devices})</StatusPill>
          <StatusPill color={STATUS_PILL.forest}>Apps ativos ({ativos})</StatusPill>
          {inativos > 0 && (
            <StatusPill color={STATUS_PILL.burgundy}>Inativos ({inativos})</StatusPill>
          )}
          <StatusPill color={STATUS_PILL.purple}>Provedores ({totalProv})</StatusPill>
        </div>
      </div>
    </PanelShell>
  );
}

export function DashboardAcsPanel({ acsStats }) {
  const totalProv = acsStats.total_providers ?? 0;
  const ativos = acsStats.active_providers ?? 0;
  const licAtivas = acsStats.active_licenses ?? 0;
  const licSusp = acsStats.suspended_licenses ?? 0;
  const licExp = acsStats.expired_licenses ?? 0;
  const problem = licSusp + licExp;
  const binds = acsStats.hardware_binds ?? 0;
  const licTotal = licAtivas + problem || 1;
  const health = pct(licAtivas, licTotal);

  return (
    <PanelShell
      title="ACS"
      subtitle="Saúde das licenças e hardware bind dos provedores"
      action={
        <Link to="/admin/acs" className="text-sm font-medium text-primary hover:underline">
          Gerenciar →
        </Link>
      }
    >
      <div className="grid grid-cols-1 gap-6">
        <div className="grid grid-cols-2 gap-4 items-center">
          <div>
            <p className="text-xs uppercase tracking-wider text-muted-foreground mb-1">
              Saúde das licenças
            </p>
            <p className="text-4xl font-black tabular-nums text-foreground leading-none">{health}%</p>
            <p className="text-xs text-muted-foreground mt-2">
              {licAtivas} ativas · {problem} com problema
            </p>
          </div>
          <div>
            <MiniPie
              labels={['Ativas', 'Suspensas', 'Expiradas']}
              values={[licAtivas, licSusp, licExp]}
              colors={[STATUS_PILL.forest, STATUS_PILL.ochre, STATUS_PILL.burgundy]}
            />
          </div>
        </div>

        <div className="space-y-2">
          <LegendDot color={STATUS_PILL.forest} label="Ativas" value={licAtivas} />
          <LegendDot color={STATUS_PILL.ochre} label="Suspensas" value={licSusp} />
          <LegendDot color={STATUS_PILL.burgundy} label="Expiradas" value={licExp} />
        </div>

        <div className="rounded-xl border border-border bg-muted/20 px-4 py-2">
          <MetricRow label="Provedores com ACS" value={totalProv} hint={`${ativos} perfis ativos`} />
          <MetricRow label="Licenças ativas" value={licAtivas} hint="Acesso liberado no painel" />
          <MetricRow
            label="Suspensas / expiradas"
            value={problem}
            hint={`${licSusp} suspensas · ${licExp} expiradas`}
          />
          <MetricRow label="Máquinas vinculadas" value={binds} hint="Hardware bind ativo" />
        </div>

        <div className="flex flex-wrap gap-2">
          <StatusPill color={STATUS_PILL.forest}>Liberadas ({licAtivas})</StatusPill>
          <StatusPill color={STATUS_PILL.ochre}>Suspensas ({licSusp})</StatusPill>
          <StatusPill color={STATUS_PILL.burgundy}>Expiradas ({licExp})</StatusPill>
          <StatusPill color={STATUS_PILL.purple}>Binds ({binds})</StatusPill>
          <StatusPill color={STATUS_PILL.royal}>Provedores ({totalProv})</StatusPill>
          <StatusPill color={STATUS_PILL.petrol}>Ativos ({ativos})</StatusPill>
        </div>
      </div>
    </PanelShell>
  );
}

export default function DashboardOverviewPanels({ statsData, provedores, appStats, acsStats }) {
  return (
    <div className="space-y-6 mb-8">
      <DashboardSystemPanel statsData={statsData} provedores={provedores} />
      <div className="grid grid-cols-1 xl:grid-cols-2 gap-6">
        <DashboardAppMobilePanel appStats={appStats} />
        <DashboardAcsPanel acsStats={acsStats} />
      </div>
    </div>
  );
}
