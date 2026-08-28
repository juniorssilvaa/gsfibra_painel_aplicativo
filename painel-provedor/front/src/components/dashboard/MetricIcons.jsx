import React from 'react';

/**
 * Ícones SVG próprios para cartões de métrica — traço mais forte, cantos arredondados,
 * opcionalmente preenchimento suave (currentColor). Escaláveis via className (ex.: w-7 h-7).
 */
const cn = (base, className) => [base, className].filter(Boolean).join(' ');

export function MetricIconChatBubble({ className }) {
  return (
    <svg
      className={cn('shrink-0', className)}
      width="24"
      height="24"
      viewBox="0 0 24 24"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      aria-hidden
    >
      <path
        opacity="0.14"
        d="M5.5 5.5h13a2.5 2.5 0 012.5 2.5v6.5a2.5 2.5 0 01-2.5 2.5h-4.2l-4.8 3.2v-3.2H5.5a2.5 2.5 0 01-2.5-2.5V8a2.5 2.5 0 012.5-2.5z"
        fill="currentColor"
      />
      <path
        d="M5.5 5.5h13a2.5 2.5 0 012.5 2.5v6.5a2.5 2.5 0 01-2.5 2.5h-4.2l-4.8 3.2v-3.2H5.5a2.5 2.5 0 01-2.5-2.5V8a2.5 2.5 0 012.5-2.5z"
        stroke="currentColor"
        strokeWidth="1.65"
        strokeLinejoin="round"
      />
      <path
        d="M9 10.25h.01M12 10.25h.01M15 10.25h.01"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
      />
    </svg>
  );
}

export function MetricIconUsersGroup({ className }) {
  return (
    <svg
      className={cn('shrink-0', className)}
      width="24"
      height="24"
      viewBox="0 0 24 24"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      aria-hidden
    >
      <circle cx="9" cy="8" r="2.75" stroke="currentColor" strokeWidth="1.65" />
      <path
        d="M4 18.5v-.5c0-2.05 1.66-3.75 3.75-3.75h2.5c2.09 0 3.75 1.7 3.75 3.75v.5"
        stroke="currentColor"
        strokeWidth="1.65"
        strokeLinecap="round"
      />
      <circle cx="16" cy="9" r="2.25" stroke="currentColor" strokeWidth="1.65" />
      <path
        d="M14.5 21h5v-.35c0-1.65-1.2-3.05-2.8-3.35"
        stroke="currentColor"
        strokeWidth="1.65"
        strokeLinecap="round"
      />
    </svg>
  );
}

export function MetricIconTrendRising({ className }) {
  const gid = React.useId().replace(/:/g, '');
  return (
    <svg
      className={cn('shrink-0', className)}
      width="24"
      height="24"
      viewBox="0 0 24 24"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      aria-hidden
    >
      <defs>
        <linearGradient id={`${gid}-area`} x1="4" y1="20" x2="18" y2="6" gradientUnits="userSpaceOnUse">
          <stop stopColor="currentColor" stopOpacity="0.28" />
          <stop offset="1" stopColor="currentColor" stopOpacity="0.02" />
        </linearGradient>
      </defs>
      <path
        d="M3 17.5 L8.5 12 L12 15 L19.5 7"
        stroke="currentColor"
        strokeWidth="1.85"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <path
        d="M3 17.5 L8.5 12 L12 15 L19.5 7 L19.5 17.5 L3 17.5 Z"
        fill={`url(#${gid}-area)`}
      />
      <path
        d="M17 5.5h4.5V10"
        stroke="currentColor"
        strokeWidth="1.85"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

export function MetricIconBadgeCheck({ className }) {
  return (
    <svg
      className={cn('shrink-0', className)}
      width="24"
      height="24"
      viewBox="0 0 24 24"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      aria-hidden
    >
      <circle
        cx="12"
        cy="12"
        r="9"
        fill="currentColor"
        fillOpacity="0.1"
        stroke="currentColor"
        strokeWidth="1.65"
      />
      <path
        d="M9.1 12.2l1.7 1.7 4.1-4.1"
        stroke="currentColor"
        strokeWidth="1.85"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

export function MetricIconClock({ className }) {
  return (
    <svg
      className={cn('shrink-0', className)}
      width="24"
      height="24"
      viewBox="0 0 24 24"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      aria-hidden
    >
      <circle
        cx="12"
        cy="12"
        r="9"
        fill="currentColor"
        fillOpacity="0.08"
        stroke="currentColor"
        strokeWidth="1.65"
      />
      <path
        d="M12 8.25V12l3 2"
        stroke="currentColor"
        strokeWidth="1.85"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}
