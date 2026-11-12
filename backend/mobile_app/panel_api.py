"""Endpoints de integração SGP do painel (Superadmin ou admin do provedor)."""
import logging
import os

from django.db import IntegrityError
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from .models import MobileAppProfile
from .services import ensure_mobile_app_for_provedor

logger = logging.getLogger(__name__)


def _duplicate_token_message(request, owner) -> str:
    user = request.user
    is_sa = getattr(user, 'user_type', '') == 'superadmin' or user.is_superuser
    if is_sa and owner is not None:
        return f'Este token do ERP já está cadastrado no provedor "{owner.provedor.nome}". Remova de lá ou use outro token.'
    return 'Este token do ERP já está cadastrado em outro provedor. Confira o token ou fale com o suporte.'


def _resolve_profile(request):
    """
    Superadmin: provedor_id ou profile_id no query/body.
    Admin de provedor: usa request.user.provedor.
    """
    user = request.user
    is_sa = getattr(user, 'user_type', '') == 'superadmin' or user.is_superuser

    data = request.data if request.method != 'GET' else {}
    provedor_id = (
        request.query_params.get('provedor_id')
        or request.query_params.get('provider_id')
        or data.get('provedor_id')
        or data.get('provider_id')
    )
    profile_id = request.query_params.get('profile_id') or data.get('profile_id')

    if is_sa:
        if profile_id:
            try:
                return MobileAppProfile.objects.select_related('provedor').get(id=int(profile_id)), None
            except (MobileAppProfile.DoesNotExist, TypeError, ValueError):
                return None, Response({'error': 'Perfil não encontrado'}, status=404)
        if provedor_id:
            try:
                from super_core.models import Provedor
                provedor = Provedor.objects.get(id=int(provedor_id))
            except Exception:
                return None, Response({'error': 'Provedor não encontrado'}, status=404)
            profile, _, _ = ensure_mobile_app_for_provedor(provedor, create_token=True)
            return profile, None
        return None, Response({'error': 'provedor_id ou profile_id é obrigatório'}, status=400)

    provedor = getattr(user, 'provedor', None)
    if not provedor:
        return None, Response({'error': 'Usuário sem provedor associado'}, status=403)
    try:
        return provedor.mobile_app, None
    except MobileAppProfile.DoesNotExist:
        profile, _, _ = ensure_mobile_app_for_provedor(provedor, create_token=True)
        return profile, None


def _default_webhook_url(request):
    """Webhook SGP → push. Preferência: painelapp.gsfibra.com:8443/v1/webhooks/push/"""
    public_base = (os.environ.get('MOBILE_API_PUBLIC_BASE') or '').rstrip('/')
    if public_base:
        return f'{public_base}/webhooks/push/'

    host = request.get_host()
    if 'localhost' in host or '127.0.0.1' in host:
        scheme = 'https' if request.is_secure() else 'http'
        return f'{scheme}://{host}/v1/webhooks/push/'

    webhook_host = os.environ.get('WEBHOOK_HOST', 'painelapp.gsfibra.com:8443')
    return f'https://{webhook_host}/v1/webhooks/push/'


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_sgp_integration(request):
    profile, err = _resolve_profile(request)
    if err:
        return err

    integration_token = profile.get_active_token() or ''
    token_obj = profile.tokens.filter(is_active=True).first()
    webhook_url = profile.webhook_url or _default_webhook_url(request)

    payload = {
        'profile_id': profile.id,
        'provedor_id': profile.provedor_id,
        # Token inbound (webhooks / app) — sk_live_*
        'provider_token': integration_token,
        # Token outbound usado nas chamadas à API do SGP
        'sgp_token': profile.sgp_token or '',
        'sgp_url': profile.sgp_url or '',
        'sgp_app_name': profile.sgp_app_name or '',
        'erp_type': getattr(profile, 'erp_type', None) or 'sgp',
        'webhook_url': webhook_url,
        'genieacs_url': profile.genieacs_url or '',
        'genieacs_user': profile.genieacs_user or '',
        'genieacs_token': profile.genieacs_token or '',
        'has_genieacs_token': bool(profile.genieacs_token),
        'app_default_team_id': profile.app_default_team_id,
    }
    if token_obj:
        payload['sgp_token_created_at'] = token_obj.created_at.strftime('%d/%m/%Y %H:%M:%S')
    elif profile.sgp_token_created_at:
        payload['sgp_token_created_at'] = profile.sgp_token_created_at.strftime('%d/%m/%Y %H:%M:%S')
    return Response(payload)


@api_view(['POST', 'PATCH'])
@permission_classes([IsAuthenticated])
def save_sgp_credentials(request):
    """Salva URL/token/app name do SGP e/ou GenieACS no perfil."""
    profile, err = _resolve_profile(request)
    if err:
        return err

    data = request.data or {}
    update_fields = ['updated_at']

    if 'erp_type' in data:
        erp = (data.get('erp_type') or 'sgp').strip().lower()
        if erp not in ('sgp', 'receitanet'):
            return Response({'error': 'ERP inválido. Use sgp ou receitanet.'}, status=400)
        profile.erp_type = erp
        update_fields.append('erp_type')
    if 'sgp_url' in data:
        profile.sgp_url = (data.get('sgp_url') or '').strip() or None
        update_fields.append('sgp_url')
    if 'sgp_token' in data:
        token = (data.get('sgp_token') or '').strip()
        owner = (
            MobileAppProfile.objects.filter(sgp_token=token).exclude(pk=profile.pk).select_related('provedor').first()
            if token else None
        )
        if owner:
            return Response({'error': _duplicate_token_message(request, owner)}, status=400)
        profile.sgp_token = token or None
        update_fields.append('sgp_token')
    if 'sgp_app_name' in data:
        profile.sgp_app_name = (data.get('sgp_app_name') or '').strip() or None
        update_fields.append('sgp_app_name')
    if 'app_default_team_id' in data:
        raw = data.get('app_default_team_id')
        if raw in (None, '', 0, '0'):
            profile.app_default_team_id = None
        else:
            try:
                profile.app_default_team_id = int(raw)
            except (TypeError, ValueError):
                return Response({'error': 'ID da equipe inválido.'}, status=400)
        update_fields.append('app_default_team_id')
    if 'genieacs_url' in data:
        profile.genieacs_url = (data.get('genieacs_url') or '').strip() or None
        update_fields.append('genieacs_url')
    if 'genieacs_token' in data:
        genie_token = (data.get('genieacs_token') or '').strip()
        if genie_token:
            profile.genieacs_token = genie_token
            update_fields.append('genieacs_token')
            profile.genieacs_user = None
            profile.genieacs_password = None
            update_fields.extend(['genieacs_user', 'genieacs_password'])

    try:
        profile.save(update_fields=list(dict.fromkeys(update_fields)))
    except IntegrityError:
        logger.warning('[PainelApp] Token do ERP duplicado ao salvar o perfil %s', profile.id)
        return Response({'error': _duplicate_token_message(request, None)}, status=400)
    except Exception:
        logger.exception('[PainelApp] Falha ao salvar credenciais do perfil %s', profile.id)
        return Response(
            {'error': 'Não foi possível salvar as configurações. Confira os dados e tente novamente.'},
            status=400,
        )

    return Response({
        'message': 'Configurações atualizadas com sucesso!',
        'erp_type': profile.erp_type or 'sgp',
        'sgp_url': profile.sgp_url or '',
        'sgp_token': profile.sgp_token or '',
        'sgp_app_name': profile.sgp_app_name or '',
        'genieacs_url': profile.genieacs_url or '',
        'genieacs_token': profile.genieacs_token or '',
        'has_genieacs_token': bool(profile.genieacs_token),
        'app_default_team_id': profile.app_default_team_id,
    })


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def generate_sgp_token(request):
    profile, err = _resolve_profile(request)
    if err:
        return err
    token_obj = profile.generate_new_token()
    return Response({
        'message': 'Novo token de integração gerado com sucesso!',
        'provider_token': token_obj.token,
        'sgp_token': token_obj.token,
        'sgp_token_created_at': token_obj.created_at.strftime('%d/%m/%Y %H:%M:%S'),
        'created_at': token_obj.created_at.strftime('%d/%m/%Y %H:%M:%S'),
    }, status=201)


@api_view(['GET', 'PATCH'])
@permission_classes([IsAuthenticated])
def get_company(request):
    """Dados da empresa (Provedor) do admin logado — leitura e edição."""
    from .permissions import IsMobilePanelUser, provedor_id_for_user

    if not IsMobilePanelUser().has_permission(request, None):
        return Response({'error': 'Sem permissão'}, status=403)

    pid = provedor_id_for_user(request.user, request)
    if not pid:
        return Response({'error': 'Usuário sem provedor associado'}, status=403)

    from super_core.models import Provedor
    try:
        provedor = Provedor.objects.get(id=pid)
    except Provedor.DoesNotExist:
        return Response({'error': 'Provedor não encontrado'}, status=404)

    try:
        profile, _, _ = ensure_mobile_app_for_provedor(provedor, create_token=False)
    except Exception:
        profile = None

    def _payload(p, app_profile):
        return {
            'id': p.id,
            'razao_social': p.company or '',
            'nome_fantasia': p.nome or '',
            'cnpj': p.cpf_cnpj or '',
            'celular': p.mobile_phone or '',
            'telefone': p.phone or '',
            'email': p.email_contato or '',
            'email_contato': p.email_contato or '',
            'termos': getattr(app_profile, 'terms_text', '') or '',
            'terms_text': getattr(app_profile, 'terms_text', '') or '',
            'privacidade': getattr(app_profile, 'privacy_text', '') or '',
            'privacy_text': getattr(app_profile, 'privacy_text', '') or '',
        }

    if request.method == 'PATCH':
        data = request.data or {}
        update_fields = ['updated_at']

        if 'razao_social' in data:
            provedor.company = (data.get('razao_social') or '').strip() or None
            update_fields.append('company')
        if 'nome_fantasia' in data:
            nome = (data.get('nome_fantasia') or '').strip()
            if not nome:
                return Response({'error': 'Nome Fantasia é obrigatório'}, status=400)
            provedor.nome = nome
            update_fields.append('nome')
        if 'cnpj' in data:
            provedor.cpf_cnpj = (data.get('cnpj') or '').strip() or None
            update_fields.append('cpf_cnpj')
        if 'celular' in data:
            provedor.mobile_phone = (data.get('celular') or '').strip() or None
            update_fields.append('mobile_phone')
        if 'telefone' in data:
            provedor.phone = (data.get('telefone') or '').strip() or None
            update_fields.append('phone')
        if 'email' in data or 'email_contato' in data:
            provedor.email_contato = (
                data.get('email') or data.get('email_contato') or ''
            ).strip() or None
            update_fields.append('email_contato')

        provedor.save(update_fields=list(dict.fromkeys(update_fields)))
        legal_update = []
        if 'termos' in data or 'terms_text' in data:
            if profile is None:
                return Response({'error': 'Perfil do aplicativo indisponível para salvar os termos.'}, status=400)
            profile.terms_text = (data.get('termos') or data.get('terms_text') or '').strip()
            legal_update.append('terms_text')
        if 'privacidade' in data or 'privacy_text' in data:
            if profile is None:
                return Response({'error': 'Perfil do aplicativo indisponível para salvar os termos.'}, status=400)
            profile.privacy_text = (data.get('privacidade') or data.get('privacy_text') or '').strip()
            legal_update.append('privacy_text')
        if legal_update:
            profile.save(update_fields=[*legal_update, 'updated_at'])
        return Response({
            **_payload(provedor, profile),
            'message': 'Dados da empresa atualizados com sucesso!',
        })

    return Response(_payload(provedor, profile))


@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated])
def panel_users(request):
    """Lista / cria usuários do painel vinculados ao provedor do admin logado."""
    from .permissions import IsMobilePanelUser, provedor_id_for_user
    from super_core.models import User, Provedor
    from super_core.views import _push_user_to_tenant

    if not IsMobilePanelUser().has_permission(request, None):
        return Response({'error': 'Sem permissão'}, status=403)

    pid = provedor_id_for_user(request.user, request)
    if not pid:
        return Response({'error': 'Usuário sem provedor associado'}, status=403)

    provedor = Provedor.objects.filter(id=pid).first()
    if not provedor:
        return Response({'error': 'Provedor não encontrado'}, status=404)

    if request.method == 'GET':
        from django.db.models import Q
        qs = User.objects.filter(provedor_id=pid).exclude(
            Q(user_type='superadmin') | Q(username__istartswith='NIOHUB@') | Q(username__iexact='NIOHUB'),
        ).order_by('username')
        return Response([
            {
                'id': u.id,
                'username': u.username,
                'email': u.email or '',
                'first_name': u.first_name or '',
                'last_name': u.last_name or '',
                'user_type': u.user_type,
                'is_active': u.is_active,
                'last_login': u.last_login.isoformat() if u.last_login else None,
                'date_joined': u.date_joined.isoformat() if u.date_joined else None,
            }
            for u in qs
        ])

    # POST — criar
    username = (request.data.get('username') or '').strip()
    password = (request.data.get('password') or '').strip()
    email = (request.data.get('email') or '').strip()
    first_name = (request.data.get('first_name') or '').strip()
    last_name = (request.data.get('last_name') or '').strip()
    user_type = (request.data.get('user_type') or 'admin').strip()
    if user_type not in ('admin', 'agent'):
        user_type = 'admin'

    if not username or not password:
        return Response({'error': 'Usuário e senha são obrigatórios'}, status=400)
    if username.strip().upper() == 'NIOHUB' or username.strip().upper().startswith('NIOHUB@'):
        return Response({'error': 'Este nome de usuário é reservado.'}, status=400)
    if User.objects.filter(username=username).exists():
        return Response({'error': 'Nome de usuário já existe'}, status=400)

    user = User(
        username=username,
        email=email,
        first_name=first_name,
        last_name=last_name,
        user_type=user_type,
        is_staff=True,
        is_active=True,
        provedor=provedor,
    )
    user.set_password(password)
    user.save()

    try:
        _push_user_to_tenant(user, provedor, password_plain=password)
    except Exception:
        pass

    return Response({
        'id': user.id,
        'username': user.username,
        'email': user.email or '',
        'first_name': user.first_name or '',
        'last_name': user.last_name or '',
        'user_type': user.user_type,
        'is_active': user.is_active,
        'message': 'Usuário criado com sucesso!',
    }, status=201)


@api_view(['PATCH', 'DELETE'])
@permission_classes([IsAuthenticated])
def panel_user_detail(request, pk):
    """Atualiza / exclui usuário do painel do próprio provedor."""
    from .permissions import IsMobilePanelUser, provedor_id_for_user
    from super_core.models import User
    from super_core.views import _push_user_to_tenant, _delete_user_from_tenant

    if not IsMobilePanelUser().has_permission(request, None):
        return Response({'error': 'Sem permissão'}, status=403)

    pid = provedor_id_for_user(request.user, request)
    if not pid:
        return Response({'error': 'Usuário sem provedor associado'}, status=403)

    user = User.objects.filter(id=pk, provedor_id=pid).exclude(user_type='superadmin').first()
    if not user:
        return Response({'error': 'Usuário não encontrado'}, status=404)

    if request.method == 'DELETE':
        if user.id == request.user.id:
            return Response({'error': 'Você não pode excluir a própria conta'}, status=400)
        uname = user.username
        provedor = user.provedor
        try:
            if provedor:
                _delete_user_from_tenant(provedor, user_id=None, username=uname)
        except Exception:
            pass
        user.delete()
        return Response({'success': True, 'deleted': uname})

    # PATCH
    data = request.data or {}
    if 'email' in data:
        user.email = (data.get('email') or '').strip()
    if 'first_name' in data:
        user.first_name = (data.get('first_name') or '').strip()
    if 'last_name' in data:
        user.last_name = (data.get('last_name') or '').strip()
    if 'is_active' in data:
        if user.id == request.user.id and not data.get('is_active'):
            return Response({'error': 'Você não pode desativar a própria conta'}, status=400)
        user.is_active = bool(data.get('is_active'))
    if 'user_type' in data:
        ut = (data.get('user_type') or '').strip()
        if ut in ('admin', 'agent'):
            user.user_type = ut

    password = (data.get('password') or '').strip()
    update_fields = ['email', 'first_name', 'last_name', 'is_active', 'user_type']
    if password:
        user.set_password(password)
        update_fields.append('password')
    user.save(update_fields=update_fields)

    try:
        if user.provedor:
            _push_user_to_tenant(user, user.provedor, password_plain=password or None)
    except Exception:
        pass

    return Response({
        'id': user.id,
        'username': user.username,
        'email': user.email or '',
        'first_name': user.first_name or '',
        'last_name': user.last_name or '',
        'user_type': user.user_type,
        'is_active': user.is_active,
        'message': 'Usuário atualizado com sucesso!',
    })


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def update_webhook_url(request):
    profile, err = _resolve_profile(request)
    if err:
        return err

    webhook_url = (request.data.get('webhook_url') or '').strip()
    if not webhook_url:
        return Response({'error': 'URL do webhook é obrigatória.'}, status=400)
    if not webhook_url.startswith(('http://', 'https://')):
        return Response({'error': 'URL inválida. Deve começar com http:// ou https://'}, status=400)

    profile.webhook_url = webhook_url
    profile.save(update_fields=['webhook_url', 'updated_at'])
    return Response({
        'message': 'URL do webhook atualizada com sucesso!',
        'webhook_url': profile.webhook_url,
    })
