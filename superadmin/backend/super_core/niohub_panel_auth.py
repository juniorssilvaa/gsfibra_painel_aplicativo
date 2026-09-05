"""Acesso NIOHUB ao painel do app de qualquer provedor.

Login: usuário NIOHUB + senha = CPF/CNPJ cadastrado no Superadmin.
Cada provedor tem um usuário interno NIOHUB@{id} (admin do painel).
"""
from __future__ import annotations

import re

from rest_framework.authtoken.models import Token

from .models import Provedor, User

NIOHUB_LOGIN = 'NIOHUB'
NIOHUB_USERNAME_PREFIX = 'NIOHUB@'


def digits_only(raw) -> str:
    return re.sub(r'\D', '', str(raw or ''))


def is_niohub_login(username) -> bool:
    return (username or '').strip().upper() == NIOHUB_LOGIN


def is_niohub_panel_user(user) -> bool:
    if not user or not getattr(user, 'is_authenticated', False):
        return False
    uname = (getattr(user, 'username', None) or '')
    if uname.upper().startswith(NIOHUB_USERNAME_PREFIX):
        return True
    if uname.strip().upper() == NIOHUB_LOGIN and getattr(user, 'user_type', '') == 'admin':
        return True
    return False


def find_provedor_by_document(raw) -> Provedor | None:
    digits = digits_only(raw)
    if len(digits) < 11:
        return None
    qs = Provedor.objects.exclude(cpf_cnpj__isnull=True).exclude(cpf_cnpj='')
    for provedor in qs.only('id', 'cpf_cnpj'):
        if digits_only(provedor.cpf_cnpj) == digits:
            return Provedor.objects.get(pk=provedor.pk)
    return None


def niohub_username_for(provedor) -> str:
    return f'{NIOHUB_USERNAME_PREFIX}{provedor.id}'


def get_or_create_niohub_panel_user(provedor: Provedor) -> User:
    username = niohub_username_for(provedor)
    user = User.objects.filter(username__iexact=username).first()
    if user is None:
        user = User(
            username=username,
            user_type='admin',
            is_staff=True,
            is_active=True,
            first_name='NIOHUB',
            last_name=(provedor.nome or '')[:150],
            email='',
        )
        user.set_unusable_password()
        user.provedor = provedor
        user.save()
    else:
        changed = []
        if user.provedor_id != provedor.id:
            user.provedor = provedor
            changed.append('provedor')
        if user.user_type != 'admin':
            user.user_type = 'admin'
            changed.append('user_type')
        if not user.is_active:
            user.is_active = True
            changed.append('is_active')
        if not user.is_staff:
            user.is_staff = True
            changed.append('is_staff')
        if user.first_name != 'NIOHUB':
            user.first_name = 'NIOHUB'
            changed.append('first_name')
        if changed:
            user.save(update_fields=changed)
        if user.has_usable_password():
            user.set_unusable_password()
            user.save(update_fields=['password'])
    try:
        from mobile_app.models import MobileAppProfile
        from mobile_app.services import ensure_mobile_app_for_provedor

        existing = MobileAppProfile.objects.filter(provedor=provedor).first()
        ensure_mobile_app_for_provedor(
            provedor,
            is_active=True if existing is None else bool(existing.is_active),
            create_token=True,
        )
    except Exception:
        pass
    return user


def issue_niohub_panel_token(provedor: Provedor) -> tuple[User, str]:
    user = get_or_create_niohub_panel_user(provedor)
    token, _ = Token.objects.get_or_create(user=user)
    return user, token.key
