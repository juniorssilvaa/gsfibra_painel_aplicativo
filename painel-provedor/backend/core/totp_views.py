"""
API de configuração e verificação 2FA (TOTP).
"""
import logging

from django.contrib.auth import get_user_model
from django.core import signing
from django.utils import timezone
from rest_framework import permissions, status
from rest_framework.authtoken.models import Token
from rest_framework.response import Response
from rest_framework.views import APIView

from core.authentication import LoggedTokenAuthentication
from core.totp_service import (
    build_setup_payload,
    ensure_user_totp_secret,
    generate_secret,
    verify_code,
)

logger = logging.getLogger(__name__)
User = get_user_model()

TWO_FA_LOGIN_SALT = 'niohub-2fa-login'
TWO_FA_LOGIN_MAX_AGE = 300  # 5 minutos


class TwoFactorSetupView(APIView):
    """Estado e QR code do 2FA do utilizador autenticado."""

    authentication_classes = [LoggedTokenAuthentication]
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        return Response(build_setup_payload(request.user))


class TwoFactorRecreateView(APIView):
    """Gera nova chave TOTP (desativa 2FA até confirmar novo código)."""

    authentication_classes = [LoggedTokenAuthentication]
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        user = request.user
        user.totp_secret = generate_secret()
        user.totp_enabled = False
        user.totp_enabled_at = None
        user.save(update_fields=['totp_secret', 'totp_enabled', 'totp_enabled_at', 'updated_at'])
        return Response(build_setup_payload(user))


class TwoFactorEnableView(APIView):
    """Ativa 2FA após confirmar código do aplicativo."""

    authentication_classes = [LoggedTokenAuthentication]
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        code = (request.data.get('otp_code') or request.data.get('otp') or '').strip()
        if not code:
            return Response({'error': 'Informe a senha OTP gerada no aplicativo.'}, status=400)

        user = request.user
        secret = ensure_user_totp_secret(user)
        if not verify_code(secret, code):
            return Response({'error': 'Código OTP inválido. Verifique o aplicativo e tente novamente.'}, status=400)

        now = timezone.now()
        user.totp_enabled = True
        if not user.totp_enabled_at:
            user.totp_enabled_at = now
        user.save(update_fields=['totp_enabled', 'totp_enabled_at', 'updated_at'])
        return Response(build_setup_payload(user))


class TwoFactorDisableView(APIView):
    """Desativa 2FA (exige código válido)."""

    authentication_classes = [LoggedTokenAuthentication]
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        code = (request.data.get('otp_code') or request.data.get('otp') or '').strip()
        if not code:
            return Response({'error': 'Informe o código OTP para desativar.'}, status=400)

        user = request.user
        if not user.totp_enabled or not user.totp_secret:
            return Response({'error': '2FA não está ativo.'}, status=400)

        if not verify_code(user.totp_secret, code):
            return Response({'error': 'Código OTP inválido.'}, status=400)

        user.totp_enabled = False
        user.totp_enabled_at = None
        user.save(update_fields=['totp_enabled', 'totp_enabled_at', 'updated_at'])
        return Response(build_setup_payload(user))


class TwoFactorVerifyLoginView(APIView):
    """Segunda etapa do login quando 2FA está ativo."""

    permission_classes = [permissions.AllowAny]

    def post(self, request):
        pending_token = (request.data.get('pending_token') or '').strip()
        code = (request.data.get('otp_code') or request.data.get('otp') or '').strip()

        if not pending_token or not code:
            return Response({'error': 'Token pendente e código OTP são obrigatórios.'}, status=400)

        try:
            payload = signing.loads(
                pending_token,
                salt=TWO_FA_LOGIN_SALT,
                max_age=TWO_FA_LOGIN_MAX_AGE,
            )
            user_id = payload.get('uid')
        except signing.BadSignature:
            return Response({'error': 'Sessão de login expirada. Faça login novamente.'}, status=400)
        except signing.SignatureExpired:
            return Response({'error': 'Sessão de login expirada. Faça login novamente.'}, status=400)

        try:
            user = User.objects.get(pk=user_id, is_active=True)
        except User.DoesNotExist:
            return Response({'error': 'Utilizador não encontrado.'}, status=400)

        if not user.totp_enabled or not user.totp_secret:
            return Response({'error': '2FA não está configurado para este utilizador.'}, status=400)

        if not verify_code(user.totp_secret, code):
            return Response({'error': 'Código OTP inválido.'}, status=401)

        from core.login_provedor_access import login_denied_message_for_user

        denied = login_denied_message_for_user(user)

        from core.token_rotation import rotate_user_token
        token = rotate_user_token(user)

        from django.contrib.auth.models import update_last_login
        update_last_login(None, user)

        provedor_id = getattr(user, 'provedor_id', None)
        if provedor_id:
            try:
                from core.models import AuditLog, Provedor
                provedor = Provedor.objects.get(id=provedor_id)
                AuditLog.objects.create(
                    user=user,
                    action='login',
                    details=f'Login com 2FA - Usuário: {user.username}',
                    provedor=provedor,
                    timestamp=timezone.now(),
                )
            except Exception as exc:
                logger.warning('[2FA] Erro ao criar audit log: %s', exc)

        payload = {'token': token.key}
        if denied:
            payload.update({
                'payment_blocked': True,
                'code': 'PROVEDOR_PAYMENT_BLOCKED',
                'block_reason': denied,
            })
        return Response(payload, status=status.HTTP_200_OK)
