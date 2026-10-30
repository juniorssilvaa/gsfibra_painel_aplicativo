import React from 'react';

export function formatStatInt(value) {
  return Number(value || 0).toLocaleString('pt-BR');
}

/**
 * Faixa de métricas do relatório: um painel, colunas iguais, número como hierarquia.
 * Sem ícone colorido, sem tile pastel.
 */
export default function RelatorioStatStrip({ items = [], columns = 5 }) {
  const gridClass = columns === 4
    ? 'grid-cols-2 lg:grid-cols-4'
    : 'grid-cols-2 sm:grid-cols-3 xl:grid-cols-5';

  return (
    <section className="overflow-hidden rounded-xl border border-border bg-border">
      <dl className={`grid gap-px ${gridClass}`}>
        {items.map((item) => (
          <div
            key={item.label}
            className="bg-card px-5 py-4 sm:px-6 sm:py-5 min-h-[96px] flex flex-col justify-center"
          >
            <dt className="text-[11px] font-medium uppercase tracking-[0.16em] text-muted-foreground">
              {item.label}
            </dt>
            <dd className="mt-2.5 text-[1.75rem] font-semibold tabular-nums tracking-tight text-foreground leading-none">
              {item.value}
            </dd>
            {item.hint ? (
              <p className="mt-2 text-xs text-muted-foreground">{item.hint}</p>
            ) : null}
          </div>
        ))}
      </dl>
    </section>
  );
}
