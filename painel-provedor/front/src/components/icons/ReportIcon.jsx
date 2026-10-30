import React from 'react';

/** Relatório: barras crescentes com linha de tendência. */
export default function ReportIcon({ className = 'w-5 h-5', ...props }) {
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
      <path d="M4 20V13" />
      <path d="M9 20V9" />
      <path d="M14 20V5" />
      <path d="M3 17 20 6" />
      <path d="M14 6h6v6" />
    </svg>
  );
}
