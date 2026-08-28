import React from 'react';
import { Bug } from 'lucide-react';

/**
 * Indicador verde ao lado do status do backend quando o suporte Niohub está logado.
 */
export default function SupportNiohubBadge({ username }) {
  if (!username || String(username).toLowerCase() !== 'niohub') {
    return null;
  }
  return (
    <div
      className="p-2 rounded-lg text-green-500 bg-green-500/10 border border-green-500/30 flex-shrink-0"
      title="Acesso suporte Niohub"
      aria-label="Acesso suporte Niohub"
    >
      <Bug className="w-5 h-5 animate-pulse" />
    </div>
  );
}
