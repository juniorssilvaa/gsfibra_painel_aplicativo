/** Conversa com atendente humano atribuído (após Atender). */
export function hasHumanAssignee(conv) {
  if (!conv?.assignee) return false;
  return Boolean(
    conv.assignee.id ||
    conv.assignee.username ||
    conv.assignee.email
  );
}

/**
 * Bloqueia envio em Automação ou Espera até o atendente clicar em Atender.
 * Superadmin pode responder sem atribuição.
 */
export function isReplyBlockedUntilAssignment(conversation, user) {
  if (!conversation) return false;
  if (user?.user_type === 'superadmin') return false;
  return !hasHumanAssignee(conversation);
}
