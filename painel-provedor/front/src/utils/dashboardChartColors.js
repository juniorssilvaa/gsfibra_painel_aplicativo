/**
 * Paletas do dashboard — cada cor é única em todo o painel (sem repetir hex).
 */

export const PIE_STATUS_COLORS = {
  'Em Atendimento': '#6366f1', // índigo (não verde)
  'Em Espera': '#facc15',
  'Na Automação': '#f43f5e',
  'Com a IA': '#f43f5e',
  Finalizadas: '#64748b',
};

export const PIE_CHANNEL_COLORS = {
  Telegram: '#38bdf8',
  WhatsApp: '#d946ef', // fúcsia (não verde)
  Email: '#84cc16',
  Instagram: '#fb7185',
  'App Mobile': '#f97316',
};

export const PIE_RESOLUTION_COLORS = {
  chatbot: '#06b6d4',
  ia: '#14b8a6',
  manual: '#e11d48',
};

/** Aplica cor fixa por nome; evita repetir no mesmo gráfico. */
export function applyPieColors(items, colorMap, paletteFallback = []) {
  const used = new Set();
  return items.map((item, index) => {
    let color = item.color || colorMap[item.name] || paletteFallback[index];
    if (!color || used.has(color)) {
      color =
        paletteFallback.find((c) => !used.has(c)) ||
        paletteFallback[index % paletteFallback.length];
    }
    used.add(color);
    return { ...item, color };
  });
}

export const ALL_DASHBOARD_PIE_COLORS = [
  ...Object.values(PIE_STATUS_COLORS),
  ...Object.values(PIE_CHANNEL_COLORS),
  ...Object.values(PIE_RESOLUTION_COLORS),
];
