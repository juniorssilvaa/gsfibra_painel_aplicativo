from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import permissions
from core.models import Provedor, SystemConfig


def _resolve_provedor(request):
    user = request.user
    provedor = None
    tenant_provedor_id = getattr(request, "tenant_provedor_id", None)

    if tenant_provedor_id:
        provedor = Provedor.objects.filter(id=tenant_provedor_id, is_active=True).first()

    if not provedor and hasattr(user, 'provedor') and user.provedor:
        provedor = user.provedor
    elif not provedor and hasattr(user, 'provedor_id') and user.provedor_id:
        provedor = Provedor.objects.filter(id=user.provedor_id).first()

    if not provedor:
        provedor = Provedor.objects.filter(admins=user).first()

    if not provedor and getattr(user, 'user_type', None) == 'superadmin':
        provedor = Provedor.objects.first()

    if not provedor:
        from core.support_account import fallback_provedor_for_niohub

        provedor = fallback_provedor_for_niohub(user)

    return provedor


def _get_system_config():
    return SystemConfig.objects.filter(key='system_config').first() or SystemConfig.objects.first()


def _provider_config_payload(provedor):
    agent_mode = (getattr(provedor, 'agent_mode', None) or 'isp').strip().lower()
    payload = {
        'id': provedor.id,
        'nome': provedor.nome,
        'chatbot_mode': provedor.bot_mode == 'chatbot',
        'bot_mode': provedor.bot_mode,
        'agent_mode': agent_mode,
        'support_transfer_notify_phone': getattr(
            provedor, 'support_transfer_notify_phone', None
        ) or '',
        'is_active': provedor.is_active,
    }
    if agent_mode == 'support':
        cfg = _get_system_config()
        payload['asaas_access_token'] = (getattr(cfg, 'asaas_access_token', None) or '') if cfg else ''
        raw_sandbox = getattr(cfg, 'asaas_sandbox', True) if cfg else True
        if isinstance(raw_sandbox, str):
            payload['asaas_sandbox'] = raw_sandbox.strip().lower() in ('1', 'true', 'yes', 'on')
        else:
            payload['asaas_sandbox'] = bool(raw_sandbox) if raw_sandbox is not None else True
        payload['asaas_configured'] = bool((payload.get('asaas_access_token') or '').strip())
    return payload


class ProviderConfigView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        provedor = _resolve_provedor(request)
        if not provedor:
            return Response({'error': 'Provider not found'}, status=404)
        return Response(_provider_config_payload(provedor))

    def patch(self, request):
        """Atualiza campos do modo suporte (notificação e token Asaas)."""
        provedor = _resolve_provedor(request)
        if not provedor:
            return Response({'error': 'Provider not found'}, status=404)

        agent_mode = (getattr(provedor, 'agent_mode', None) or 'isp').strip().lower()
        update_fields = []
        phone = request.data.get('support_transfer_notify_phone')
        if phone is not None:
            import re
            provedor.support_transfer_notify_phone = re.sub(r'\D', '', str(phone))[:30]
            update_fields.append('support_transfer_notify_phone')

        if update_fields:
            provedor.save(update_fields=update_fields)

        asaas_token = request.data.get('asaas_access_token')
        asaas_sandbox = request.data.get('asaas_sandbox')
        wants_asaas = asaas_token is not None or asaas_sandbox is not None
        if wants_asaas:
            if agent_mode != 'support':
                return Response(
                    {'error': 'Token Asaas só pode ser configurado no modo suporte da plataforma.'},
                    status=403,
                )
            cfg = _get_system_config()
            if not cfg:
                cfg = SystemConfig.objects.create(key='system_config')
            cfg_fields = []
            if asaas_token is not None:
                cfg.asaas_access_token = str(asaas_token).strip()
                cfg_fields.append('asaas_access_token')
            if asaas_sandbox is not None:
                if isinstance(asaas_sandbox, str):
                    cfg.asaas_sandbox = asaas_sandbox.strip().lower() in ('1', 'true', 'yes', 'on')
                else:
                    cfg.asaas_sandbox = bool(asaas_sandbox)
                cfg_fields.append('asaas_sandbox')
            if cfg_fields:
                cfg.save(update_fields=cfg_fields)

        return Response(_provider_config_payload(provedor))
