import React from 'react';

export default function RelatorioIntro({ title, description, points = [] }) {
  return (
    <section className="rounded-xl border border-border bg-card px-5 py-4 sm:px-6 sm:py-5">
      <p className="text-[11px] font-medium uppercase tracking-[0.16em] text-muted-foreground">
        {title}
      </p>
      {description ? (
        <p className="mt-2 text-sm leading-relaxed text-foreground/85 max-w-2xl">
          {description}
        </p>
      ) : null}
      {points.length > 0 && (
        <ul className="mt-4 grid overflow-hidden rounded-lg border border-border bg-border gap-px sm:grid-cols-3">
          {points.map((point) => (
            <li key={point.label} className="bg-card px-4 py-3">
              <p className="text-sm font-medium text-foreground">{point.label}</p>
              <p className="mt-1 text-xs leading-relaxed text-muted-foreground">{point.text}</p>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
