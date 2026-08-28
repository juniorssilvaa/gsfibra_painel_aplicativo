import { hasHumanAssignee } from './conversationAssignment';

const PROVIDER_ADMIN_ROLES = ['admin', 'company_admin', 'provedor_admin'];

/** Admin do provedor (pode supervisionar atendimentos de outros agentes). */
export function isProviderAdminUser(user) {
  if (!user) return false;
  const role = user.role || user.user_type || '';
  if (PROVIDER_ADMIN_ROLES.includes(role)) return true;
  if (user.user_type === 'admin') return true;
  return Array.isArray(user.provedores_admin) && user.provedores_admin.length > 0;
}

export function getAssigneeDisplayName(conversation) {
  const a = conversation?.assignee;
  if (!a) return 'Sem atendente';
  const full = [a.first_name, a.last_name].filter(Boolean).join(' ').trim();
  return full || a.first_name || a.username || a.email || 'Atendente';
}

/**
 * Admin na aba Em andamento visualizando atendimento de outro agente (somente leitura + tempo real).
 */
export function isSupervisorMonitoring(conversation, user, activeTab) {
  if (activeTab !== 'in_progress') return false;
  if (!isProviderAdminUser(user)) return false;
  if (!hasHumanAssignee(conversation)) return false;

  const assigneeId = conversation.assignee?.id ?? conversation.assignee_id;
  const userId = user?.id;
  if (assigneeId == null || userId == null) return false;

  return String(assigneeId) !== String(userId);
}
