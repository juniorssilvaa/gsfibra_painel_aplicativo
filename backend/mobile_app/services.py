"""Helpers para provisionar o app mobile a partir do Provedor Niohub."""
import re

from django.db import transaction
from django.utils import timezone

from .models import (
    MobileActivityLog,
    MobileAppConfig,
    MobileAppProfile,
    MobileAppUser,
    MobileDevice,
    MobileProviderToken,
)


def sgp_contract_id(contract):
    """ID do contrato no SGP (campo real: contratoId)."""
    if not isinstance(contract, dict):
        return ''
    raw = contract.get('contratoId') or contract.get('contrato') or contract.get('id')
    if raw in (None, ''):
        return ''
    return str(raw).strip()


def sgp_pppoe_login(contract):
    """Login PPPoE/WAN. Não usar contratoCentralLogin (usuário da central)."""
    if not isinstance(contract, dict):
        return ''
    return str(
        contract.get('servico_login')
        or contract.get('pppoe_login')
        or contract.get('login')
        or ''
    ).strip()


def sgp_client_name(contract_or_payload):
    """Nome completo do cliente no JSON do SGP (razaoSocial costuma vir no contrato)."""
    if not isinstance(contract_or_payload, dict):
        return ''
    for key in (
        'razaoSocial',
        'razaosocial',
        'razao_social',
        'nomeCliente',
        'nome_cliente',
        'nome',
        'name',
    ):
        val = contract_or_payload.get(key)
        if val and str(val).strip():
            return str(val).strip()[:255]
    for c in (contract_or_payload.get('contratos') or []):
        if isinstance(c, dict):
            name = sgp_client_name(c)
            if name:
                return name
    return ''


def parse_version_tuple(version):
    """Converte '1.2.3-beta' em tupla comparável (1, 2, 3)."""
    if not version:
        return None
    parts = []
    for chunk in re.split(r'[^\d]+', str(version).strip()):
        if chunk.isdigit():
            parts.append(int(chunk))
    return tuple(parts) if parts else None


def is_app_version_outdated(device_version, latest_version):
    dv = parse_version_tuple(device_version)
    lv = parse_version_tuple(latest_version)
    if dv is None or lv is None:
        return False
    return dv < lv


def mask_ip(ip):
    """Mascara IP para exibição no painel (177.xxx / 2804:xxxx)."""
    if not ip:
        return '—'
    s = str(ip).strip()
    if ':' in s:
        # IPv6
        head = s.split(':', 1)[0]
        return f'{head}:xxxx'
    parts = s.split('.')
    if len(parts) >= 1 and parts[0]:
        return f'{parts[0]}.xxx'
    return '—'


def client_ip_from_request(request):
    if not request:
        return None
    xff = request.META.get('HTTP_X_FORWARDED_FOR')
    if xff:
        return xff.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR')


def log_mobile_activity(
    *,
    provedor,
    event,
    user=None,
    ip_address=None,
    user_agent=None,
    event_label='',
    metadata=None,
    request=None,
):
    """Registra evento de auditoria do app (best-effort)."""
    if not provedor:
        return None
    try:
        ip = ip_address
        ua = user_agent
        if request is not None:
            ip = ip or client_ip_from_request(request)
            ua = ua or (request.META.get('HTTP_USER_AGENT') or '')[:255]
        return MobileActivityLog.objects.create(
            provedor=provedor,
            user=user,
            event=event,
            event_label=event_label or '',
            ip_address=ip or None,
            user_agent=ua or None,
            metadata=metadata or {},
        )
    except Exception:
        return None


def count_outdated_devices(provedor_id, latest_version=None):
    if not latest_version:
        try:
            latest_version = (
                MobileAppProfile.objects.filter(provedor_id=provedor_id)
                .values_list('latest_app_version', flat=True)
                .first()
            )
        except Exception:
            latest_version = None
    if not latest_version:
        return 0
    lv = parse_version_tuple(latest_version)
    if lv is None:
        return 0
    outdated = 0
    for ver in (
        MobileDevice.objects.filter(provedor_id=provedor_id, active=True)
        .exclude(app_version__isnull=True)
        .exclude(app_version='')
        .values_list('app_version', flat=True)
    ):
        if is_app_version_outdated(ver, latest_version):
            outdated += 1
    return outdated


@transaction.atomic
def ensure_mobile_app_for_provedor(provedor, *, is_active=True, create_token=True):
    """
    Garante MobileAppProfile + AppConfig (+ token) para o provedor.
    Idempotente.
    """
    profile, created = MobileAppProfile.objects.get_or_create(
        provedor=provedor,
        defaults={
            'is_active': is_active,
            'cnpj': getattr(provedor, 'cpf_cnpj', None) or '',
            'number': (
                getattr(provedor, 'mobile_phone', None)
                or getattr(provedor, 'phone', None)
                or ''
            ),
        },
    )
    if not created and profile.is_active != is_active:
        profile.is_active = is_active
        profile.save(update_fields=['is_active', 'updated_at'])

    MobileAppConfig.objects.get_or_create(profile=profile)

    token = None
    if create_token and not profile.tokens.filter(is_active=True).exists():
        token = MobileProviderToken.objects.create(profile=profile)
    else:
        token = profile.tokens.filter(is_active=True).first()

    return profile, token, created


_DENIED_MSG = 'Acesso desativado. Entre em contato com o suporte.'


def app_user_access_denied(provedor, cpf) -> str | None:
    """Bloqueia cliente inativo (toggle Status da conta no painel)."""
    if not provedor or not cpf:
        return None
    cpf_limpo = re.sub(r'\D', '', str(cpf))
    if not cpf_limpo:
        return None
    qs = MobileAppUser.objects.filter(provedor=provedor).only('active', 'cpf')
    user = qs.filter(cpf=cpf_limpo).first()
    if user is None and cpf_limpo.lstrip('0'):
        user = qs.filter(cpf__in=[cpf_limpo.lstrip('0'), cpf_limpo.zfill(11)]).first()
    if user is not None and not user.active:
        return _DENIED_MSG
    return None


def app_user_access_denied_from_payload(provedor, payload) -> str | None:
    """Nega acesso por CPF, contrato ou login PPPoE presentes no payload."""
    if not provedor or not isinstance(payload, dict):
        return None
    cpf = payload.get('cpf_cnpj') or payload.get('cpfcnpj') or payload.get('cpf')
    denied = app_user_access_denied(provedor, cpf)
    if denied:
        return denied

    contract = (
        payload.get('contrato')
        or payload.get('contract_id')
        or payload.get('customer_id')
        or payload.get('contrato_id')
    )
    if contract not in (None, ''):
        user = (
            MobileAppUser.objects.filter(provedor=provedor, customer_id=str(contract).strip())
            .only('active')
            .first()
        )
        if user is not None and not user.active:
            return _DENIED_MSG

    login = (
        payload.get('login')
        or payload.get('pppoe_login')
        or payload.get('servico_login')
    )
    if login not in (None, ''):
        login_s = str(login).strip()
        user = (
            MobileAppUser.objects.filter(provedor=provedor, pppoe_login__icontains=login_s)
            .only('active')
            .first()
        )
        if user is not None and not user.active:
            return _DENIED_MSG
    return None


def provedor_access_denied(provedor) -> str | None:
    """
    GSFibra: sem controle de assinatura/suspensão — app e painel sempre liberados.
    """
    return None


def panel_user_access_denied(user) -> str | None:
    """
    GSFibra não controla assinatura/suspensão no painel.
    Mantido só por compatibilidade de imports — sempre libera.
    """
    return None


def resolve_provedor_from_provider_token(provider_token: str, *, require_active: bool = True):
    """Resolve Provedor a partir do token sk_live_* (ou sgp_token legado no profile)."""
    if not provider_token:
        return None
    tok_qs = MobileProviderToken.objects.filter(token=provider_token).select_related('profile__provedor')
    if require_active:
        tok_qs = tok_qs.filter(is_active=True, profile__is_active=True)
    tok = tok_qs.first()
    if tok:
        provedor = tok.profile.provedor
        if require_active and provedor_access_denied(provedor):
            return None
        return provedor
    profile_qs = MobileAppProfile.objects.filter(sgp_token=provider_token).select_related('provedor')
    if require_active:
        profile_qs = profile_qs.filter(is_active=True)
    profile = profile_qs.first()
    if not profile:
        return None
    if require_active and provedor_access_denied(profile.provedor):
        return None
    return profile.provedor


def update_user_activity(provedor, cpf):
    """Heartbeat online: atualiza last_active do AppUser e devices."""
    if not provedor or not cpf:
        return
    cpf_limpo = re.sub(r'\D', '', str(cpf))
    now = timezone.now()
    MobileAppUser.objects.filter(provedor=provedor, cpf=cpf_limpo, active=True).update(last_active_at=now)
    MobileDevice.objects.filter(
        user__provedor=provedor,
        user__cpf=cpf_limpo,
        active=True,
    ).update(last_active=now)
