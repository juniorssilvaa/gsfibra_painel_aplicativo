/** Laranja padrão Niohub (#EA580C) — enviar/gravar e demais CTAs laranja (não usar no botão SGP). */
export const NIOHUB_BRAND_ORANGE = '#EA580C';

export const CHAT_ORANGE_SEND_BTN =
  'p-2 text-white rounded-xl shadow-md transition-all hover:opacity-90 active:scale-95 disabled:opacity-50 disabled:cursor-not-allowed';

export function chatOrangeSendStyle() {
  return { backgroundColor: NIOHUB_BRAND_ORANGE };
}

/** Botões Salvar (confirmar) — verde forte */
export const CHAT_SAVE_BTN =
  'rounded-lg text-white font-semibold hover:opacity-90 disabled:opacity-50 disabled:cursor-not-allowed';

export function chatSaveStyle() {
  return { backgroundColor: '#16A34A' };
}

/** Botões de ação da conversa: fundo sólido, cores por significado da ação. */
export const CONVERSATION_ACTION_BTN_BASE =
  'h-8 rounded-md border-0 px-3 text-xs font-semibold shadow-sm hover:opacity-90 transition-opacity inline-flex items-center gap-1.5 disabled:opacity-50 disabled:cursor-not-allowed focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-offset-2 focus-visible:ring-offset-background';

export const CONVERSATION_ACTION_COLORS = {
  atender: { bg: '#16A34A', fg: '#ffffff' },
  transferir: { bg: '#2563EB', fg: '#ffffff' },
  encerrar: { bg: '#DC2626', fg: '#ffffff' },
  sgp: { bg: '#EA580C', fg: '#ffffff' },
  sgpAtivo: { bg: '#C2410C', fg: '#ffffff' },
};

export function conversationActionStyle(kind) {
  const c = CONVERSATION_ACTION_COLORS[kind] || CONVERSATION_ACTION_COLORS.atender;
  return { backgroundColor: c.bg, color: c.fg };
}

/** Ações de pagamento no painel SGP — mesmo padrão visual dos botões da conversa. */
export const PAYMENT_ACTION_COLORS = {
  pix: { bg: '#16A34A', fg: '#ffffff' },
  boleto: { bg: '#475569', fg: '#ffffff' },
  linkFatura: { bg: '#2563EB', fg: '#ffffff' },
  pdfFatura: { bg: '#DC2626', fg: '#ffffff' },
};

export function paymentActionStyle(kind) {
  const c = PAYMENT_ACTION_COLORS[kind] || PAYMENT_ACTION_COLORS.pix;
  return { backgroundColor: c.bg, color: c.fg };
}
