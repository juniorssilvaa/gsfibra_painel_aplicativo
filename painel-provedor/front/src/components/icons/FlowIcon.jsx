import React from 'react';

/** Ícone de fluxo (3 nós) — Fluxo de Atendimento */
export default function FlowIcon({ className = 'w-5 h-5', ...props }) {
  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      className={className}
      aria-hidden="true"
      focusable="false"
      {...props}
    >
      <path d="M7.5 7.5L12 16.5" />
      <path d="M16.5 7.5L12 16.5" />
      <path d="M7.5 7.5H16.5" />
      <circle cx="7.5" cy="7.5" r="2" />
      <circle cx="16.5" cy="7.5" r="2" />
      <circle cx="12" cy="16.5" r="2" />
    </svg>
  );
}
