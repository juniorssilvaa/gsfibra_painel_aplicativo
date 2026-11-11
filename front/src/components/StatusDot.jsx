import useBackendStatus from '../hooks/useBackendStatus';

const StatusDot = ({ className = '' }) => {
  const { status } = useBackendStatus();

  const getStatusConfig = () => {
    switch (status) {
      case 'online':
        return {
          iconColor: 'text-[#22c55e]',
          borderColor: 'border-[#22c55e]',
          isRotating: false,
        };
      case 'connecting':
        return {
          iconColor: 'text-yellow-500',
          borderColor: 'border-yellow-500',
          isRotating: true,
        };
      case 'offline':
      default:
        return {
          iconColor: 'text-[#ef4444]',
          borderColor: 'border-[#ef4444]',
          isRotating: true,
        };
    }
  };

  const getTooltip = () => {
    switch (status) {
      case 'online':
        return 'Backend online';
      case 'connecting':
        return 'Reconectando ao backend...';
      case 'offline':
      default:
        return 'Backend offline';
    }
  };

  const config = getStatusConfig();

  return (
    <div
      className={`p-2 rounded-lg transition-colors text-topbar-foreground hover:bg-sidebar-accent hover:text-sidebar-accent-foreground relative flex items-center justify-center flex-shrink-0 ${className}`}
      title={getTooltip()}
      aria-label={getTooltip()}
      role="status"
      aria-live="polite"
    >
      {status === 'online' && (
        <div className={`absolute w-5 h-5 rounded-full border-2 ${config.borderColor} animate-pulse`} />
      )}

      <svg
        className={`w-5 h-5 ${config.iconColor} transition-colors duration-300 ${config.isRotating ? 'animate-spin' : ''}`}
        fill="none"
        stroke="currentColor"
        viewBox="0 0 24 24"
      >
        <path
          strokeLinecap="round"
          strokeLinejoin="round"
          strokeWidth={2}
          d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"
        />
      </svg>
    </div>
  );
};

export default StatusDot;
