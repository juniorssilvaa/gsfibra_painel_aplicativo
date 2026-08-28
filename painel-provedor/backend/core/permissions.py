from rest_framework import permissions


class ProvedorNotSuspended(permissions.BasePermission):
    """
    Bloqueia API do painel quando o provedor está suspenso no superadmin
    (mesmo que o id local ainda esteja is_active=True).
    """

    message = 'Acesso suspenso pelo administrador do sistema.'

    def has_permission(self, request, view):
        user = getattr(request, 'user', None)
        if not user or not getattr(user, 'is_authenticated', False):
            return True

        # Tela de inadimplência ainda precisa ler status/PIX estando suspenso
        if getattr(view, 'action', None) == 'status_pagamento':
            return True

        from core.login_provedor_access import api_access_denied_message_for_user

        denied = api_access_denied_message_for_user(user)
        if denied:
            self.message = denied
            return False
        return True
