"""Permissões do app mobile no Superadmin / painel do provedor."""
from rest_framework import permissions

from .services import provedor_access_denied, panel_user_access_denied


class IsSuperadmin(permissions.BasePermission):
    def has_permission(self, request, view):
        user = request.user
        return bool(
            user
            and user.is_authenticated
            and (getattr(user, 'user_type', '') == 'superadmin' or user.is_superuser)
        )


class IsMobilePanelUser(permissions.BasePermission):
    """
    Superadmin OU admin de provedor (painel do app).
    Admins precisam ter provedor associado, provedor ativo e app mobile ativo.
    """

    message = 'Acesso desativado. Entre em contato com o suporte.'

    def has_permission(self, request, view):
        user = request.user
        if not user or not user.is_authenticated:
            return False
        if getattr(user, 'user_type', '') == 'superadmin' or user.is_superuser:
            return True
        from super_core.niohub_panel_auth import is_niohub_panel_user
        if is_niohub_panel_user(user) and getattr(user, 'provedor_id', None):
            return True
        if getattr(user, 'user_type', '') == 'admin' and getattr(user, 'provedor_id', None):
            denied = panel_user_access_denied(user)
            if denied:
                self.message = denied
                return False
            return True
        return False


def is_superadmin_user(user):
    return bool(
        user
        and user.is_authenticated
        and (getattr(user, 'user_type', '') == 'superadmin' or user.is_superuser)
    )


def provedor_id_for_user(user, request=None):
    """
    Superadmin pode filtrar por provedor_id/provider_id.
    Admin do painel fica preso ao próprio provedor.
    """
    if is_superadmin_user(user):
        if request is not None:
            q = (
                request.query_params.get('provedor_id')
                or request.query_params.get('provider_id')
                or (request.data.get('provedor_id') if hasattr(request, 'data') else None)
                or (request.data.get('provider_id') if hasattr(request, 'data') else None)
            )
            if q:
                try:
                    return int(q)
                except (TypeError, ValueError):
                    return None
        return None
    return getattr(user, 'provedor_id', None)
