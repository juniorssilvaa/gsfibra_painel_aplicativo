const CLOSED_STATUSES = ['closed', 'encerrada', 'resolved', 'finalizada', 'closing'];

export function getConversationStatus(conversation) {
  return conversation?.status || conversation?.additional_attributes?.status || '';
}

export function hasHumanAssignee(conversation) {
  if (!conversation) return false;
  if (conversation.assignee_id) return true;
  const assignee = conversation.assignee;
  if (!assignee) return false;
  return Boolean(assignee.id || assignee.username || assignee.email);
}

export function getWaitingForAgent(conversation) {
  if (typeof conversation?.waiting_for_agent === 'boolean') return conversation.waiting_for_agent;
  if (typeof conversation?.additional_attributes?.waiting_for_agent === 'boolean') {
    return conversation.additional_attributes.waiting_for_agent;
  }
  return null;
}

export function isClosedConversation(conversation) {
  return CLOSED_STATUSES.includes(getConversationStatus(conversation));
}

/**
 * Fila humana (aba Espera).
 * Exclusivo da aba Automação / Com a IA: nunca listar nas duas.
 */
export function isWaitingConversation(conversation) {
  if (!conversation || isClosedConversation(conversation)) return false;
  if (hasHumanAssignee(conversation)) return false;

  const waitingForAgent = getWaitingForAgent(conversation);
  if (waitingForAgent === true) return true;
  if (waitingForAgent === false) return false;
  // Fallback legado quando a flag não vem no payload
  return getConversationStatus(conversation) === 'pending';
}

/**
 * Atendimento pelo robô (aba Automação / Com a IA).
 * Exclusivo da fila humana: waiting_for_agent=true nunca entra aqui.
 */
export function isAutomationConversation(conversation) {
  if (!conversation || isClosedConversation(conversation)) return false;
  if (hasHumanAssignee(conversation)) return false;

  const waitingForAgent = getWaitingForAgent(conversation);
  if (waitingForAgent === true) return false;
  if (waitingForAgent === false) return true;
  // Fallback legado quando a flag não vem no payload
  const status = getConversationStatus(conversation);
  return status === 'snoozed' || status === 'chatbot';
}

export function isAssignedToUser(conversation, userId) {
  if (!conversation || userId == null) return false;
  const assigneeId = conversation.assignee?.id ?? conversation.assignee_id;
  if (!assigneeId) return false;
  return parseInt(assigneeId, 10) === parseInt(userId, 10);
}

/**
 * Som de notificação do painel: atendimento atribuído ao usuário ou fila de espera.
 * Não toca enquanto o cliente está só na automação/robô.
 */
export function shouldPlayPanelNotificationSound(conversation, userId) {
  if (!conversation) return false;
  if (isAssignedToUser(conversation, userId)) return true;
  if (isWaitingConversation(conversation)) return true;
  if (isAutomationConversation(conversation)) return false;
  return false;
}

export function resolveConversationFromWsEvent(data) {
  return (
    data?.conversation ||
    data?.data?.conversation ||
    data?.payload?.conversation ||
    data?.data?.data?.conversation ||
    null
  );
}
