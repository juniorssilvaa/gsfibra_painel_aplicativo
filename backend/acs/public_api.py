"""
APIs públicas consultadas pelo painel ACS do provedor.

Contrato compatível com E:\\genieacs\\painel_admin (VALIDACAO_URL).
"""
from __future__ import annotations

import json
import os
import uuid

from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from .models import AcsHardwareBind, AcsLicense, AcsRelease, AcsDeploymentLog


def _validation_token_ok(request) -> bool:
    required = (os.environ.get('ACS_VALIDATION_TOKEN') or os.environ.get('VALIDACAO_TOKEN') or '').strip()
    if not required:
        return True
    token = request.headers.get('X-Validation-Token') or request.GET.get('token')
    return token == required


def _client_ip(request) -> str | None:
    forwarded = request.META.get('HTTP_X_FORWARDED_FOR', '')
    if forwarded:
        return forwarded.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR')


@require_http_methods(['GET'])
def license_status_api(request):
    if not _validation_token_ok(request):
        return JsonResponse({'ok': False, 'status': 'forbidden', 'reason': 'Token inválido.'}, status=403)

    key_raw = request.GET.get('license_key') or request.GET.get('key')
    machine_name = request.GET.get('machine_name') or 'unknown'
    hwid_hash = request.GET.get('hwid_hash') or request.GET.get('machine_name') or ''
    last_ip = request.GET.get('last_ip') or _client_ip(request)

    try:
        license_key = uuid.UUID(str(key_raw))
    except Exception:
        return JsonResponse({'ok': False, 'status': 'invalid', 'reason': 'license_key inválida.'}, status=400)

    try:
        lic = AcsLicense.objects.select_related('profile', 'profile__provedor').get(key=license_key)
    except AcsLicense.DoesNotExist:
        return JsonResponse({'ok': False, 'status': 'not_found', 'reason': 'Licença não encontrada.'}, status=404)

    profile = lic.profile
    provedor = profile.provedor
    today = timezone.localdate()

    if not profile.is_active or not provedor.is_active or provedor.status == 'suspenso':
        return JsonResponse(
            {'ok': False, 'status': 'suspended', 'reason': 'Licença não está ativa.'},
            status=403,
        )

    if lic.status != 'active':
        return JsonResponse({'ok': False, 'status': lic.status, 'reason': 'Licença não está ativa.'}, status=403)

    if lic.expiration_date and lic.expiration_date < today:
        if lic.status != 'expired':
            lic.status = 'expired'
            lic.save(update_fields=['status'])
        return JsonResponse({'ok': False, 'status': 'expired', 'reason': 'Licença expirada.'}, status=403)

    if not hwid_hash:
        return JsonResponse({'ok': False, 'status': 'invalid', 'reason': 'hwid_hash obrigatório.'}, status=400)

    existing_for_license = AcsHardwareBind.objects.filter(license=lic, status=True).exclude(hwid_hash=hwid_hash)
    if existing_for_license.exists():
        return JsonResponse(
            {'ok': False, 'status': 'bound', 'reason': 'Licença já vinculada a outra máquina.'},
            status=403,
        )

    bind = AcsHardwareBind.objects.filter(license=lic, hwid_hash=hwid_hash).first()
    if bind:
        bind.status = True
        bind.machine_name = machine_name
        bind.last_ip = last_ip
        bind.save(update_fields=['status', 'machine_name', 'last_ip', 'last_seen'])
    else:
        AcsHardwareBind.objects.create(
            profile=profile,
            license=lic,
            machine_name=machine_name,
            hwid_hash=hwid_hash,
            last_ip=last_ip,
            status=True,
        )

    return JsonResponse(
        {
            'ok': True,
            'status': 'active',
            'reason': 'OK',
            'license_key': str(lic.key),
            'expiration_date': lic.expiration_date.isoformat() if lic.expiration_date else None,
            'isp_id': provedor.id,
            'isp': {'id': provedor.id, 'name': provedor.nome},
            'max_onts': lic.max_onts,
            'update_policy': {
                'channel': profile.update_channel,
                'auto_update': profile.auto_update,
                'fixed_version': profile.fixed_version or None,
            },
        }
    )


@require_http_methods(['GET'])
def update_check_api(request):
    key_raw = request.GET.get('license_key')
    current_version = request.GET.get('current_version')
    if not all([key_raw, current_version]):
        return JsonResponse({'ok': False, 'reason': 'Parâmetros insuficientes.'}, status=400)

    try:
        lic = AcsLicense.objects.select_related('profile', 'profile__provedor').get(key=key_raw, status='active')
    except (AcsLicense.DoesNotExist, ValueError):
        return JsonResponse({'ok': False, 'reason': 'Licença inválida ou inativa.'}, status=403)

    profile = lic.profile
    if not profile.is_active or not profile.provedor.is_active:
        return JsonResponse({'ok': False, 'reason': 'Licença inválida ou inativa.'}, status=403)

    profile.last_check = timezone.now()
    profile.current_version = current_version
    profile.save(update_fields=['last_check', 'current_version'])

    if profile.fixed_version:
        target_release = AcsRelease.objects.filter(
            version=profile.fixed_version,
            channel=profile.update_channel,
            is_active=True,
        ).first()
    else:
        target_release = (
            AcsRelease.objects.filter(channel=profile.update_channel, is_active=True)
            .order_by('-created_at')
            .first()
        )

    if not target_release:
        return JsonResponse({'ok': True, 'update_available': False, 'reason': 'Nenhuma release disponível para este canal.'})

    clean_target = target_release.version.lstrip('v').lstrip('V')
    clean_current = str(current_version).lstrip('v').lstrip('V')
    update_available = clean_target != clean_current

    return JsonResponse(
        {
            'ok': True,
            'update_available': update_available,
            'release': {
                'version': target_release.version,
                'is_mandatory': target_release.is_mandatory,
                'image': target_release.image_reference,
                'checksum': target_release.checksum,
                'changelog': target_release.changelog,
            }
            if update_available
            else None,
            'policy': {
                'auto_update': profile.auto_update,
                'channel': profile.update_channel,
            },
        }
    )


@require_http_methods(['GET'])
def changelog_api(request):
    license_key = request.GET.get('license_key')
    if not license_key:
        return JsonResponse({'ok': False, 'reason': 'Licença obrigatória.'}, status=400)

    try:
        lic = AcsLicense.objects.select_related('profile').get(key=license_key, status='active')
    except (AcsLicense.DoesNotExist, ValueError):
        return JsonResponse({'ok': False, 'reason': 'Licença inválida.'}, status=403)

    if not lic.profile.is_active:
        return JsonResponse({'ok': False, 'reason': 'Licença inválida.'}, status=403)

    releases = AcsRelease.objects.filter(
        channel=lic.profile.update_channel,
        is_active=True,
    ).order_by('-created_at')[:10]

    data = []
    for r in releases:
        data.append(
            {
                'version': r.version.lstrip('v').lstrip('V'),
                'date': r.created_at.strftime('%d/%m/%Y'),
                'changelog': r.changelog,
                'is_mandatory': r.is_mandatory,
            }
        )
    return JsonResponse({'ok': True, 'releases': data})


@csrf_exempt
@require_http_methods(['POST'])
def update_report_api(request):
    try:
        payload = json.loads(request.body or b'{}')
        license_key = payload.get('license_key')
        lic = AcsLicense.objects.select_related('profile').get(key=license_key)
        AcsDeploymentLog.objects.create(
            profile=lic.profile,
            from_version=payload.get('from_version') or '',
            to_version=payload.get('to_version') or '',
            status=payload.get('status') or '',
            error_message=payload.get('error_message') or '',
            had_rollback=bool(payload.get('had_rollback', False)),
            finished_at=timezone.now(),
        )
        if payload.get('status') == 'success' and payload.get('to_version'):
            lic.profile.current_version = payload.get('to_version')
            lic.profile.save(update_fields=['current_version'])
        return JsonResponse({'ok': True})
    except Exception as exc:
        return JsonResponse({'ok': False, 'reason': str(exc)}, status=400)
