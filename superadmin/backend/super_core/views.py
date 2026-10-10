from rest_framework import viewsets, permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.authtoken.models import Token
from rest_framework.decorators import api_view, permission_classes as permission_classes_decorator, action
from django.contrib.auth import authenticate
from django.utils import timezone
from django.conf import settings
from django.db import connection
import secrets
from .models import Provedor, Canal, User, Company, AuditLog, MensagemSistema, BillingTemplate, SystemConfig, VpsServer, SystemUpdate, Plano
from .billing_send_service import run_billing_send_cycle
from rest_framework import serializers
import logging

logger = logging.getLogger(__name__)


def _admin_webhook_secret_ok(secret: str) -> bool:
    """Aceita secret do SystemConfig ou do .env (dev local costuma divergir)."""
    provided = (secret or '').strip()
    if not provided:
        return False
    config = SystemConfig.objects.first()
    from_payload = ''
    if config and isinstance(config.payload, dict):
        from_payload = (config.payload.get('ADMIN_WEBHOOK_SECRET') or '').strip()
    from_env = (getattr(settings, 'ADMIN_WEBHOOK_SECRET', None) or '').strip()
    return provided in {s for s in (from_payload, from_env) if s}


# ---------------------------
# Asaas (billing) integration
# ---------------------------
from integrations.asaas_config import coerce_bool, get_asaas_access_token, get_asaas_base_url, is_asaas_sandbox
from integrations.asaas_entity import (
    asaas_customer_is_active,
    asaas_entity_is_removed,
    asaas_payment_is_active,
    asaas_subscription_is_active,
    confirm_payments_on_asaas,
    filter_active_asaas_payments,
)
from integrations.asaas_notifications import apply_provedor_notification_settings


def _get_asaas_access_token() -> str:
    return get_asaas_access_token()


def _asaas_headers() -> dict:
    token = _get_asaas_access_token()
    if not token:
        return {}
    return {
        'Content-Type': 'application/json',
        'access_token': token,  # Asaas padrão: header access_token
    }


def _asaas_base_url() -> str:
    return get_asaas_base_url()


def _asaas_request(method: str, path: str, *, params=None, json=None, timeout: int = 12):
    import requests

    headers = _asaas_headers()
    if not headers:
        raise RuntimeError('Asaas access token não configurado em SystemConfig (asaas_access_token).')

    base = _asaas_base_url()
    url = f"{base}{path}"
    logger.debug(
        "[Asaas] %s %s (sandbox=%s)",
        method.upper(),
        url,
        is_asaas_sandbox(),
    )
    resp = requests.request(method.upper(), url, headers=headers, params=params, json=json, timeout=timeout)
    if not resp.ok:
        body = ''
        try:
            body = resp.text[:800]
        except Exception:
            body = ''
        raise RuntimeError(f"Asaas HTTP {resp.status_code}: {body}")
    try:
        return resp.json()
    except Exception:
        return {}


def _normalize_cpf_cnpj(raw: str) -> str:
    import re
    return re.sub(r'\\D+', '', raw or '').strip()


def _asaas_http_status_from_error(exc: Exception) -> int | None:
    import re
    match = re.search(r'HTTP (\d+)', str(exc))
    return int(match.group(1)) if match else None


def _asaas_fetch_payment_by_id(payment_id: str) -> dict | None:
    pid = (payment_id or '').strip()
    if not pid:
        return None
    try:
        data = _asaas_request('GET', f'/payments/{pid}')
    except RuntimeError as exc:
        code = _asaas_http_status_from_error(exc)
        if code == 404 or asaas_entity_is_removed(code, str(exc)):
            return None
        raise
    return data if asaas_payment_is_active(data) else None


def _asaas_confirm_payments(payments: list | None, *, max_items: int = 50) -> list:
    return confirm_payments_on_asaas(payments, _asaas_fetch_payment_by_id, max_items=max_items)


ASAAS_BILLING_TYPES = ('BOLETO', 'PIX', 'CREDIT_CARD', 'UNDEFINED')
ASAAS_CYCLES = ('WEEKLY', 'BIWEEKLY', 'MONTHLY', 'BIMONTHLY', 'QUARTERLY', 'SEMIANNUALLY', 'YEARLY')
ASAAS_PAYMENT_EDITABLE = ('PENDING', 'OVERDUE')


def _asaas_error_text(exc: Exception) -> str:
    """Mensagem legível a partir de 'Asaas HTTP 400: {"errors": [...]}'."""
    import json

    raw = str(exc)
    _, _, body = raw.partition(': ')
    try:
        errors = json.loads(body).get('errors') or []
        descriptions = [str(e.get('description') or '').strip() for e in errors if isinstance(e, dict)]
        text = ' '.join(d for d in descriptions if d)
        if text:
            return text
    except (ValueError, AttributeError):
        pass
    return raw


def _parse_iso_date(raw):
    from datetime import date

    try:
        return date.fromisoformat(str(raw or '').strip()[:10])
    except ValueError:
        return None


def _parse_money(raw):
    try:
        value = round(float(str(raw).replace(',', '.')), 2)
    except (TypeError, ValueError):
        return None
    return value if value > 0 else None


def _asaas_payment_summary(p: dict) -> dict:
    return {
        'id': p.get('id'),
        'description': (p.get('description') or '').strip(),
        'dueDate': p.get('dueDate'),
        'value': p.get('value'),
        'netValue': p.get('netValue'),
        'status': p.get('status'),
        'billingType': p.get('billingType'),
        'confirmedDate': p.get('confirmedDate'),
        'paymentDate': p.get('paymentDate'),
        'invoiceUrl': p.get('invoiceUrl'),
        'bankSlipUrl': p.get('bankSlipUrl'),
        'provider': 'asaas',
    }


def _asaas_delete_subscription(subscription_id: str) -> None:
    """Exclui assinatura no Asaas. 404 = já removida (ok)."""
    sub_id = (subscription_id or '').strip()
    if not sub_id:
        return
    try:
        _asaas_request('DELETE', f'/subscriptions/{sub_id}')
    except RuntimeError as exc:
        code = _asaas_http_status_from_error(exc)
        if code == 404 or asaas_entity_is_removed(code, str(exc)):
            logger.info('[Asaas] Assinatura %s já inexistente no Asaas.', sub_id)
            return
        raise


def _compute_days_late(due_date_iso: str) -> int:
    """
    Asaas retorna datas como YYYY-MM-DD. Se inválido, retorna 0.
    """
    if not due_date_iso:
        return 0
    try:
        from datetime import date
        y, m, d = [int(x) for x in str(due_date_iso).split('-')[:3]]
        due = date(y, m, d)
        today = timezone.localdate()
        return max(0, (today - due).days)
    except Exception:
        return 0


def _should_auto_block_from_config() -> tuple[bool, int]:
    """
    Lê do SystemConfig.payload:
    - billing_provedor_auto_block_enabled (bool)
    - billing_provedor_block_min_days_late (int, default 4)
    """
    config = SystemConfig.objects.first()
    payload = (config.payload or {}) if config else {}
    enabled = bool(payload.get('billing_provedor_auto_block_enabled', False))
    try:
        min_days = int(payload.get('billing_provedor_block_min_days_late', 4))
    except Exception:
        min_days = 4
    min_days = max(0, min(365, min_days))
    return enabled, min_days

class UserSerializer(serializers.ModelSerializer):
    provedor_nome = serializers.SerializerMethodField()
    provedor_is_active = serializers.SerializerMethodField()
    provedor_status = serializers.SerializerMethodField()
    mobile_app_is_active = serializers.SerializerMethodField()
    write_provedor_id = serializers.IntegerField(write_only=True, required=False, allow_null=True)
    # Exposto no /auth/me/ para o painel do app do provedor (login compartilhado Niohub)
    provedor_id = serializers.IntegerField(required=False, allow_null=True)
    # Não usar exclude=['password'] junto com este campo — o DRF 3.15+ levanta AssertionError.
    password = serializers.CharField(write_only=True, required=False, allow_blank=True, trim_whitespace=False)

    class Meta:
        model = User
        fields = (
            'id',
            'username',
            'email',
            'first_name',
            'last_name',
            'is_staff',
            'is_active',
            'is_superuser',
            'date_joined',
            'last_login',
            'user_type',
            'provedor',
            'provedor_nome',
            'provedor_is_active',
            'provedor_status',
            'mobile_app_is_active',
            'write_provedor_id',
            'provedor_id',
            'password',
            'is_online',
            'last_seen',
            'permissions',
            'session_timeout',
            'phone',
            'preferred_language',
        )
        read_only_fields = ('date_joined', 'last_login')

    def to_representation(self, instance):
        data = super().to_representation(instance)
        from .niohub_panel_auth import NIOHUB_LOGIN, is_niohub_panel_user
        if is_niohub_panel_user(instance):
            data['username'] = NIOHUB_LOGIN
            data['niohub_support'] = True
        else:
            data['niohub_support'] = False
        return data

    def get_provedor_nome(self, obj):
        return obj.provedor.nome if obj.provedor else None

    def get_provedor_is_active(self, obj):
        if not obj.provedor:
            return None
        return bool(obj.provedor.is_active)

    def get_provedor_status(self, obj):
        return obj.provedor.status if obj.provedor else None

    def get_mobile_app_is_active(self, obj):
        if not obj.provedor:
            return None
        try:
            return bool(obj.provedor.mobile_app.is_active)
        except Exception:
            return False

    def _sync_panel_bootstrap_secret(self, user, plain_password: str):
        """Guarda senha em claro (encriptada) no Provedor para o Portainer usar no deploy."""
        if not plain_password or not getattr(user, 'provedor_id', None):
            return
        from .models import Provedor
        from .panel_bootstrap_crypto import encrypt_bootstrap

        prov = Provedor.objects.filter(id=user.provedor_id).first()
        if not prov:
            return
        prov.panel_bootstrap_password_ciphertext = encrypt_bootstrap(plain_password)
        prov.save(update_fields=['panel_bootstrap_password_ciphertext'])

    def update(self, instance, validated_data):
        password_plain = validated_data.pop('password', None)
        provedor_id = validated_data.pop('write_provedor_id', -1)
        alt_pid = validated_data.pop('provedor_id', None)
        if provedor_id == -1 and alt_pid is not None:
            provedor_id = alt_pid
        if provedor_id != -1:
            if provedor_id:
                try:
                    instance.provedor = Provedor.objects.get(id=provedor_id)
                except Provedor.DoesNotExist:
                    pass
            else:
                instance.provedor = None
        instance = super().update(instance, validated_data)
        if password_plain:
            instance.set_password(password_plain)
            instance.save(update_fields=['password'])
            self._sync_panel_bootstrap_secret(instance, password_plain)
        return instance

    def create(self, validated_data):
        password_plain = validated_data.pop('password', None) or None
        provedor_id = validated_data.pop('write_provedor_id', None)
        if provedor_id is None:
            provedor_id = validated_data.pop('provedor_id', None)

        user = User(**validated_data)
        if password_plain:
            user.set_password(password_plain)
        else:
            user.set_unusable_password()
        user.save()

        if provedor_id:
            try:
                user.provedor = Provedor.objects.get(id=provedor_id)
                user.save(update_fields=['provedor'])
            except Provedor.DoesNotExist:
                pass

        if password_plain:
            self._sync_panel_bootstrap_secret(user, password_plain)
        return user

def _vps_number_map(context) -> dict:
    cached = context.get('vps_numbers') if isinstance(context, dict) else None
    if cached is not None:
        return cached
    ids = list(VpsServer.objects.order_by('id').values_list('id', flat=True))
    mapping = {vid: idx + 1 for idx, vid in enumerate(ids)}
    if isinstance(context, dict):
        context['vps_numbers'] = mapping
    return mapping


class VpsServerSerializer(serializers.ModelSerializer):
    providers_count = serializers.SerializerMethodField()
    display_number = serializers.SerializerMethodField()
    
    class Meta:
        model = VpsServer
        fields = '__all__'
        
    def get_providers_count(self, obj):
        return obj.provedores.count()

    def get_display_number(self, obj):
        return _vps_number_map(self.context).get(obj.id)

class ProvedorSerializer(serializers.ModelSerializer):
    users_count = serializers.SerializerMethodField()
    conversations_count = serializers.SerializerMethodField()
    vps_name = serializers.ReadOnlyField(source='vps.name')
    vps_number = serializers.SerializerMethodField()
    integration_token_configured = serializers.SerializerMethodField()
    integration_token_last_used_at = serializers.DateTimeField(read_only=True)
    desired_id = serializers.IntegerField(write_only=True, required=False, allow_null=True)
    mobile_app_enabled = serializers.SerializerMethodField()
    chat_enabled = serializers.SerializerMethodField()
    acs_enabled = serializers.SerializerMethodField()
    plano_nome = serializers.ReadOnlyField(source='plano.nome')
    limites = serializers.SerializerMethodField()

    class Meta:
        model = Provedor
        exclude = ('panel_bootstrap_password_ciphertext', 'integration_token')

    def get_limites(self, obj):
        return obj.plan_limits()

    def get_users_count(self, obj):
        try:
            return User.objects.filter(provedor=obj).count()
        except:
            return 0

    def get_conversations_count(self, obj):
        # Atualmente não temos acesso direto à tabela de conversas de cada provedor
        # Isso pode ser integrado depois. Por enquanto, retornamos 0 para o painel não quebrar.
        return 0

    def get_vps_number(self, obj):
        if not getattr(obj, 'vps_id', None):
            return None
        return _vps_number_map(self.context).get(obj.vps_id)

    def get_integration_token_configured(self, obj):
        return bool((getattr(obj, 'integration_token', '') or '').strip())

    def get_mobile_app_enabled(self, obj):
        try:
            return bool(obj.mobile_app.is_active)
        except Exception:
            return False

    def get_chat_enabled(self, obj):
        ext = obj.integracoes_externas if isinstance(obj.integracoes_externas, dict) else {}
        if 'chat_enabled' in ext:
            return bool(ext.get('chat_enabled'))
        # Cadastros antigos: assumem chat (multi-atendimento)
        return True

    def get_acs_enabled(self, obj):
        try:
            return bool(obj.acs.is_active)
        except Exception:
            return False

    def update(self, instance, validated_data):
        validated_data.pop('desired_id', None)
        return super().update(instance, validated_data)

    def create(self, validated_data):
        """
        Permite que o Superadmin escolha um ID específico (ex.: pular 4 e criar direto 5),
        útil em migrações onde o ID legado precisa ser preservado.
        """
        desired_id = validated_data.pop('desired_id', None)
        if desired_id is not None:
            try:
                desired_id = int(desired_id)
            except Exception:
                raise serializers.ValidationError({"desired_id": "ID inválido."})
            if desired_id <= 0:
                raise serializers.ValidationError({"desired_id": "ID deve ser maior que 0."})
            if Provedor.objects.filter(id=desired_id).exists():
                raise serializers.ValidationError({"desired_id": "Este ID já está em uso."})

            instance = Provedor(**validated_data)
            instance.id = desired_id
            instance.save(force_insert=True)

            # Realinhar a sequence para evitar colisões em futuros inserts automáticos.
            from django.db import connection
            try:
                with connection.cursor() as cursor:
                    cursor.execute(
                        "SELECT setval("
                        "pg_get_serial_sequence('super_core_provedor','id'), "
                        "(SELECT GREATEST(COALESCE(MAX(id), 0), %s) FROM super_core_provedor), "
                        "true"
                        ")",
                        [desired_id],
                    )
            except Exception:
                # Não bloquear criação por falha de setval (ex.: banco não é postgres).
                pass

            return instance

        return super().create(validated_data)

class CanalSerializer(serializers.ModelSerializer):
    class Meta:
        model = Canal
        fields = '__all__'

class CompanySerializer(serializers.ModelSerializer):
    class Meta:
        model = Company
        fields = '__all__'

class AuditLogSerializer(serializers.ModelSerializer):
    class Meta:
        model = AuditLog
        fields = '__all__'

class MensagemSistemaSerializer(serializers.ModelSerializer):
    provedores_count = serializers.SerializerMethodField()
    provedores_detalhados = serializers.SerializerMethodField()
    visualizacoes_detalhadas = serializers.SerializerMethodField()

    class Meta:
        model = MensagemSistema
        fields = [
            'id', 'assunto', 'mensagem', 'imagem_url', 'hotspots', 'cta_links',
            'provedores', 'tipo',
            'visivel_para_agentes', 'visualizacoes', 'visualizacoes_count',
            'provedores_count', 'provedores_detalhados', 'visualizacoes_detalhadas',
            'created_at', 'updated_at',
        ]
        read_only_fields = [
            'id', 'visualizacoes', 'visualizacoes_count',
            'provedores_count', 'provedores_detalhados', 'visualizacoes_detalhadas',
            'created_at', 'updated_at',
        ]

    def get_provedores_count(self, obj):
        provedores = obj.provedores if isinstance(obj.provedores, list) else []
        return len(provedores)

    def _visualizacoes_map(self, obj):
        return obj.visualizacoes if isinstance(obj.visualizacoes, dict) else {}

    def _provedor_foi_visualizado(self, visualizacoes: dict, provedor_id: int) -> bool:
        pid = str(provedor_id)
        if pid in visualizacoes:
            return True
        for key, dados in visualizacoes.items():
            if not isinstance(dados, dict):
                continue
            if str(dados.get('provedor_id') or '') == pid:
                return True
            if str(key).startswith(f'{pid}:'):
                return True
        return False

    def _primeira_leitura_provedor(self, visualizacoes: dict, provedor_id: int):
        pid = str(provedor_id)
        candidatos = []
        entry = visualizacoes.get(pid)
        if isinstance(entry, dict):
            candidatos.append(entry)
        for key, dados in visualizacoes.items():
            if not isinstance(dados, dict):
                continue
            if str(dados.get('provedor_id') or '') == pid or str(key).startswith(f'{pid}:'):
                candidatos.append(dados)
        if not candidatos:
            return None
        candidatos.sort(key=lambda d: d.get('visualized_at') or d.get('timestamp') or '')
        return candidatos[0]

    def get_provedores_detalhados(self, obj):
        visualizacoes = self._visualizacoes_map(obj)
        provedores = []
        for provedor_id in (obj.provedores or []):
            try:
                pid = int(provedor_id)
            except (TypeError, ValueError):
                continue
            provedor = Provedor.objects.filter(id=pid).first()
            leitura = self._primeira_leitura_provedor(visualizacoes, pid)
            provedores.append({
                'id': pid,
                'nome': provedor.nome if provedor else f'Provedor {pid}',
                'visualizado': leitura is not None,
                'visualized_at': (leitura or {}).get('visualized_at') or (leitura or {}).get('timestamp'),
                'user_name': (leitura or {}).get('user_name') or (leitura or {}).get('username') or '',
            })
        return provedores

    def get_visualizacoes_detalhadas(self, obj):
        visualizacoes = self._visualizacoes_map(obj)
        detalhes = []
        for key, dados in visualizacoes.items():
            if not isinstance(dados, dict):
                continue
            timestamp = dados.get('visualized_at') or dados.get('timestamp')
            provedor_id = dados.get('provedor_id')
            provedor_nome = dados.get('provedor_nome') or ''
            if not provedor_nome and provedor_id:
                p = Provedor.objects.filter(id=provedor_id).first()
                if p:
                    provedor_nome = p.nome
            if not provedor_nome and ':' in str(key):
                try:
                    pid = int(str(key).split(':', 1)[0])
                    p = Provedor.objects.filter(id=pid).first()
                    if p:
                        provedor_nome = p.nome
                except (TypeError, ValueError):
                    pass
            detalhes.append({
                'user_id': dados.get('user_id'),
                'username': dados.get('user_name') or dados.get('username') or 'Usuário',
                'provedor_id': provedor_id,
                'provedor_nome': provedor_nome or 'Provedor',
                'timestamp': timestamp,
            })
        detalhes.sort(key=lambda d: d.get('timestamp') or '', reverse=True)
        return detalhes

class BillingTemplateSerializer(serializers.ModelSerializer):
    class Meta:
        model = BillingTemplate
        fields = '__all__'

class SystemConfigSerializer(serializers.ModelSerializer):
    class Meta:
        model = SystemConfig
        fields = '__all__'

class SystemUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = SystemUpdate
        fields = '__all__'

class SystemUpdateViewSet(viewsets.ModelViewSet):
    queryset = SystemUpdate.objects.all().order_by('-release_date')
    serializer_class = SystemUpdateSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_permissions(self):
        if self.action == 'release':
            return [permissions.AllowAny()]
        return super().get_permissions()

    @action(detail=False, methods=['post'])
    def release(self, request):
        from .services.app_version import read_app_version
        from .services.release_service import queue_release, request_has_ci_token

        user = getattr(request, 'user', None)
        is_user = bool(user and getattr(user, 'is_authenticated', False))
        is_ci = request_has_ci_token(request)
        if not is_user and not is_ci:
            return Response({'error': 'Não autorizado'}, status=status.HTTP_401_UNAUTHORIZED)

        channel = (request.data.get('channel') or '').strip().lower()
        version = (request.data.get('version') or '').strip() or read_app_version()
        if channel not in ('beta', 'stable'):
            return Response(
                {'error': 'Canal inválido. Use beta ou stable.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if not version:
            return Response({'error': 'Versão obrigatória'}, status=status.HTTP_400_BAD_REQUEST)

        running = SystemUpdate.objects.filter(
            status__in=[SystemUpdate.STATUS_PENDING, SystemUpdate.STATUS_RUNNING]
        ).exists()
        if running:
            return Response(
                {'error': 'Já existe uma atualização em andamento. Aguarde terminar.'},
                status=status.HTTP_409_CONFLICT,
            )

        source = 'ci' if is_ci and not is_user else 'ui'
        providers = Provedor.objects.filter(release_channel=channel, is_active=True)
        preview = {
            'total': providers.count(),
            'with_vps': providers.exclude(vps_id=None).count(),
            'without_vps': providers.filter(vps_id=None).count(),
        }
        update = queue_release(
            channel=channel,
            version=version,
            source=source,
            description=f'Release {version} no canal {channel} ({source})',
        )
        return Response(
            {
                'success': True,
                'queued': True,
                'id': update.id,
                'status': update.status,
                'version': update.version,
                'channel': update.channel,
                'preview': preview,
            },
            status=status.HTTP_202_ACCEPTED,
        )

class LoginView(APIView):
    permission_classes = [permissions.AllowAny]
    def post(self, request):
        username = request.data.get('username')
        password = request.data.get('password')

        from .niohub_panel_auth import (
            digits_only,
            find_provedor_by_document,
            is_niohub_login,
            issue_niohub_panel_token,
        )

        if is_niohub_login(username):
            provedor = find_provedor_by_document(password)
            if provedor:
                _user, token_key = issue_niohub_panel_token(provedor)
                return Response({'token': token_key})
            doc = digits_only(password)
            if len(doc) in (11, 14):
                return Response(
                    {'error': 'CNPJ/CPF não encontrado para nenhum provedor.'},
                    status=status.HTTP_401_UNAUTHORIZED,
                )
            user = authenticate(username=username, password=password)
        else:
            user = authenticate(username=username, password=password)

        if not user:
            return Response({'error': 'Invalid credentials'}, status=status.HTTP_401_UNAUTHORIZED)

        # Provedor suspenso OU app mobile INATIVO: bloqueia admin do painel
        if getattr(user, 'user_type', '') == 'admin' and getattr(user, 'provedor_id', None):
            from mobile_app.services import panel_user_access_denied
            denied = panel_user_access_denied(user)
            if denied:
                return Response({'error': denied}, status=status.HTTP_403_FORBIDDEN)

        if not user.is_active:
            return Response(
                {'error': 'Acesso desativado. Entre em contato com o suporte.'},
                status=status.HTTP_403_FORBIDDEN,
            )

        token, _ = Token.objects.get_or_create(user=user)
        return Response({'token': token.key})


class NiohubPanelAccessView(APIView):
    """Superadmin abre o painel do app de um provedor (mesmo acesso NIOHUB + CNPJ)."""
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        user = request.user
        if not (getattr(user, 'user_type', '') == 'superadmin' or user.is_superuser):
            return Response({'error': 'Apenas superadmin.'}, status=status.HTTP_403_FORBIDDEN)

        from .niohub_panel_auth import find_provedor_by_document, issue_niohub_panel_token

        provedor_id = request.data.get('provedor_id') or request.data.get('provider_id')
        provedor = None
        if provedor_id:
            try:
                provedor = Provedor.objects.get(id=int(provedor_id))
            except (Provedor.DoesNotExist, TypeError, ValueError):
                return Response({'error': 'Provedor não encontrado.'}, status=status.HTTP_404_NOT_FOUND)
        else:
            provedor = find_provedor_by_document(
                request.data.get('cpf_cnpj') or request.data.get('password')
            )
        if not provedor:
            return Response(
                {'error': 'Informe provedor_id ou o CPF/CNPJ cadastrado.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        _panel_user, token_key = issue_niohub_panel_token(provedor)
        return Response({
            'token': token_key,
            'provedor_id': provedor.id,
            'provedor_nome': provedor.nome,
        })

class UserMeView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        user = request.user
        from .niohub_panel_auth import is_niohub_panel_user
        if (
            getattr(user, 'user_type', '') == 'admin'
            and getattr(user, 'provedor_id', None)
            and not is_niohub_panel_user(user)
        ):
            from mobile_app.services import panel_user_access_denied
            denied = panel_user_access_denied(user)
            if denied:
                return Response({'error': denied}, status=status.HTTP_403_FORBIDDEN)
        serializer = UserSerializer(user)
        return Response(serializer.data)

    def patch(self, request):
        """Atualiza dados pessoais da própria conta (perfil)."""
        user = request.user
        from .niohub_panel_auth import is_niohub_panel_user
        if (
            getattr(user, 'user_type', '') == 'admin'
            and getattr(user, 'provedor_id', None)
            and not is_niohub_panel_user(user)
        ):
            from mobile_app.services import panel_user_access_denied
            denied = panel_user_access_denied(user)
            if denied:
                return Response({'error': denied}, status=status.HTTP_403_FORBIDDEN)

        data = request.data if isinstance(request.data, dict) else {}
        full_name = (data.get('full_name') or data.get('nome_completo') or '').strip()
        if full_name:
            parts = full_name.split(None, 1)
            user.first_name = parts[0][:150]
            user.last_name = (parts[1] if len(parts) > 1 else '')[:150]
        else:
            if 'first_name' in data:
                user.first_name = (data.get('first_name') or '').strip()[:150]
            if 'last_name' in data:
                user.last_name = (data.get('last_name') or '').strip()[:150]

        if 'email' in data:
            user.email = (data.get('email') or '').strip()[:254]
        if 'phone' in data or 'telefone' in data:
            user.phone = (data.get('phone') or data.get('telefone') or '').strip()[:30] or None
        if 'preferred_language' in data or 'idioma' in data:
            lang = (data.get('preferred_language') or data.get('idioma') or 'pt-BR').strip()
            if lang not in ('pt-BR', 'en', 'es'):
                lang = 'pt-BR'
            user.preferred_language = lang

        user.save()
        return Response(UserSerializer(user).data)

@api_view(['GET'])
@permission_classes_decorator([permissions.AllowAny])
def changelog_view(request):
    """Retorna o conteúdo do CHANGELOG.json (mesma fonte do painel)."""
    from .services.app_version import read_app_version, read_changelog

    data = read_changelog()
    if data:
        return Response(data)
    return Response({'versions': [], 'current_version': read_app_version()})

@api_view(['GET', 'POST'])
@permission_classes_decorator([permissions.AllowAny])
def ping_view(request):
    return Response({'status': 'pong'})

@api_view(['GET'])
@permission_classes_decorator([permissions.AllowAny])
def health_view(request):
    return Response({'status': 'healthy'})


@api_view(['GET'])
@permission_classes_decorator([permissions.IsAuthenticated])
def users_status_view(request):
    """
    GET /api/users/status/
    Retorna lista de utilizadores com status de presença online.
    Usado pelo frontend SuperadminUserList para indicar quem está online.
    """
    from django.utils import timezone as tz
    from datetime import timedelta

    presence_window = timedelta(seconds=90)
    now = tz.now()

    users = User.objects.all().only(
        'id', 'username', 'email', 'is_online', 'last_seen'
    )

    result = []
    for u in users:
        last_seen = getattr(u, 'last_seen', None)
        is_online = bool(getattr(u, 'is_online', False))
        if last_seen and (now - last_seen) <= presence_window:
            is_online = True
        result.append({
            'id': u.id,
            'username': u.username,
            'is_online': is_online,
            'last_seen': last_seen.isoformat() if last_seen else None,
        })

    return Response({'users': result})

import threading
import requests
import logging

logger = logging.getLogger(__name__)


def _generate_provider_integration_token() -> str:
    # ~43 chars URL-safe; bom equilíbrio entre segurança e usabilidade.
    return secrets.token_urlsafe(32)

def _sync_niohub_in_tenant(provedor):
    """
    Chama o endpoint do tenant para ligar o utilizador niohub ao Provedor correcto.
    Deve ser chamado após criar um novo Provedor no superadmin.
    """
    try:
        subdomain = getattr(provedor, 'subdomain', None) or ''
        if not subdomain:
            logger.warning(f"[sync-niohub] Provedor id={provedor.id} sem subdomain — a saltar.")
            return

        provider_token = (getattr(provedor, 'integration_token', '') or '').strip()
        if not provider_token:
            logger.warning("[sync-niohub] Token não configurado — a saltar.")
            return

        url = f"https://{subdomain.rstrip('/')}/api/webhooks/admin/sync-niohub/"
        payload = {"provedor_id": provedor.id}
        headers = {"Authorization": f"Bearer {provider_token}"}
        resp = requests.post(url, json=payload, headers=headers, timeout=10)
        if resp.ok:
            logger.info(f"[sync-niohub] niohub sincronizado em {subdomain} → provedor_id={provedor.id}")
        else:
            logger.warning(f"[sync-niohub] Resposta inesperada de {subdomain}: {resp.status_code} {resp.text[:200]}")
    except Exception as exc:
        logger.warning(f"[sync-niohub] Erro ao sincronizar niohub no tenant: {exc}")


def _sync_bot_mode_to_tenant(provedor):
    """Envia bot_mode e agent_mode ao tenant via webhook provider-status."""
    try:
        subdomain = (getattr(provedor, 'subdomain', None) or '').strip()
        if not subdomain:
            return
        token = (getattr(provedor, 'integration_token', '') or '').strip()
        if not token:
            return
        url = f"https://{subdomain.rstrip('/')}/api/webhooks/admin/provider-status/"
        payload = {
            "provedor_id": provedor.id,
            "is_active": provedor.is_active,
            "status": getattr(provedor, 'status', '') or '',
            "bot_mode": provedor.bot_mode,
            "agent_mode": getattr(provedor, 'agent_mode', None) or 'isp',
        }
        headers = {"Authorization": f"Bearer {token}"}
        resp = requests.post(url, json=payload, headers=headers, timeout=10)
        if resp.ok:
            logger.info(
                "[sync-bot-mode] bot_mode=%s agent_mode=%s enviado ao tenant %s (HTTP %s)",
                provedor.bot_mode,
                payload['agent_mode'],
                subdomain,
                resp.status_code,
            )
        else:
            logger.warning(
                "[sync-bot-mode] Falha ao enviar bot_mode ao tenant %s: %s %s",
                subdomain, resp.status_code, resp.text[:200],
            )
    except Exception as exc:
        logger.warning("[sync-bot-mode] Erro: %s", exc)


def _tenant_admin_url(provedor, path: str):
    """URL de um webhook admin no painel do provedor (TENANT_WEBHOOK_BASE_URL só vale em DEBUG para localhost)."""
    import os

    local_base = (os.environ.get('TENANT_WEBHOOK_BASE_URL') or '').strip().rstrip('/')
    if local_base and any(
        h in local_base.lower()
        for h in ('://127.0.0.1', '://localhost', '://0.0.0.0')
    ):
        from django.conf import settings as dj_settings
        if not getattr(dj_settings, 'DEBUG', False):
            local_base = ''
    if local_base:
        return f"{local_base}/api/webhooks/admin/{path}/"
    provider_subdomain = (provedor.subdomain or '').strip()
    if not provider_subdomain:
        return None
    if '.' not in provider_subdomain:
        provider_subdomain = f'{provider_subdomain}.niohub.com.br'
    return f"https://{provider_subdomain.rstrip('/')}/api/webhooks/admin/{path}/"


def _push_plan_limits_to_tenant(provedor_id):
    """Envia plano e limites (plano + extras) ao painel do provedor."""
    provedor = Provedor.objects.select_related('plano').filter(id=provedor_id).first()
    if not provedor:
        return
    token = (provedor.integration_token or '').strip()
    url = _tenant_admin_url(provedor, 'plan-limits')
    if not token or not url:
        logger.info('[plan-limits] Provedor %s sem token/subdomínio — o heartbeat aplica depois.', provedor_id)
        return
    try:
        resp = requests.post(
            url,
            json={'provedor_id': provedor.id, **provedor.plan_limits()},
            headers={'Authorization': f'Bearer {token}'},
            timeout=10,
        )
        if resp.ok:
            logger.info('[plan-limits] Limites enviados ao provedor %s', provedor_id)
        else:
            logger.warning('[plan-limits] Provedor %s respondeu HTTP %s: %s', provedor_id, resp.status_code, resp.text[:200])
    except Exception as exc:
        logger.warning('[plan-limits] Falha ao enviar limites ao provedor %s: %s', provedor_id, exc)


def push_plan_limits_async(provedor_ids):
    def _run():
        for pid in provedor_ids:
            _push_plan_limits_to_tenant(pid)

    threading.Thread(target=_run, daemon=True).start()


def notify_provider_panel(provedor_id, is_active, status_text, block_reason=None):
    try:
        provedor = Provedor.objects.filter(id=provedor_id).first()
        if not provedor:
            return

        provider_token = (provedor.integration_token or '').strip()
        if not provider_token:
            logger.warning("[provider-status] Token não configurado no provedor %s.", provedor_id)
            return

        url = _tenant_admin_url(provedor, 'provider-status')
        if not url:
            logger.warning("Webhook do provedor não configurado (subdomain ausente).")
            return

        payload = {
            'provedor_id': provedor_id,
            'is_active': bool(is_active),
            'status': status_text,
        }
        if not is_active:
            payload['block_reason'] = (
                block_reason
                or 'Sua fatura está em atraso. Efetue o pagamento para reativar o acesso ao painel.'
            )
        else:
            payload['block_reason'] = ''

        headers = {'Authorization': f'Bearer {provider_token}'}

        response = requests.post(url, json=payload, headers=headers, timeout=15)
        response.raise_for_status()
        logger.info(
            '[provider-status] Tenant atualizado provedor=%s is_active=%s',
            provedor_id,
            is_active,
        )
    except Exception as e:
        logger.error(
            '[provider-status] Falha ao notificar tenant do provedor %s: %s',
            provedor_id,
            e,
        )


class TenantBillingStatusView(APIView):
    """
    O tenant (painel do provedor) chama este endpoint com Bearer integration_token
    para obter fatura em atraso e PIX usando o Asaas configurado no Superadmin.
    """

    permission_classes = [permissions.AllowAny]
    authentication_classes = []

    def get(self, request):
        auth = (request.headers.get('Authorization') or '').strip()
        low = auth.lower()
        if not low.startswith('bearer '):
            return Response({'error': 'Unauthorized'}, status=401)
        token = auth[7:].strip()
        if not token:
            return Response({'error': 'Unauthorized'}, status=401)

        provedor = Provedor.objects.filter(integration_token=token).first()
        if not provedor:
            return Response({'error': 'Unauthorized'}, status=401)

        provedor.integration_token_last_used_at = timezone.now()
        provedor.save(update_fields=['integration_token_last_used_at'])

        if provedor.is_active:
            return Response({'blocked': False, 'reason': None, 'payment': None, 'pix': None})

        reason_default = (
            'Sua fatura está em atraso. '
            'Efetue o pagamento para reativar o acesso ao painel.'
        )
        overdue_payment = None
        pix_data = None
        is_inter = (
            (provedor.billing_provider or '') == Provedor.BILLING_PROVIDER_INTER
            or (provedor.asaas_subscription_id or '').startswith('INTER-SUB-')
        )

        if is_inter:
            from .models import InterBillingCharge

            charge = (
                InterBillingCharge.objects.filter(
                    provedor=provedor,
                    status__in=[InterBillingCharge.STATUS_OVERDUE, InterBillingCharge.STATUS_PENDING],
                )
                .order_by('data_vencimento')
                .first()
            )
            if charge:
                overdue_payment = {
                    'id': charge.codigo_solicitacao,
                    'value': float(charge.valor),
                    'dueDate': charge.data_vencimento.isoformat() if charge.data_vencimento else None,
                    'invoiceUrl': '',
                    'description': f'Cobrança Inter {charge.seu_numero}',
                }
                if charge.pix_copia_cola:
                    pix_data = {
                        'encodedImage': '',
                        'payload': charge.pix_copia_cola,
                        'expirationDate': overdue_payment.get('dueDate'),
                    }
        else:
            sub_id = (provedor.asaas_subscription_id or '').strip()
            if sub_id:
                try:
                    data = _asaas_request(
                        'GET',
                        '/payments',
                        params={'subscription': sub_id, 'status': 'OVERDUE', 'limit': 1},
                    )
                    items = _asaas_confirm_payments(data.get('data') or [], max_items=5)
                    overdue_payment = items[0] if items else None
                except Exception as exc:
                    logger.warning(
                        '[tenant-billing-status] provedor=%s Asaas overdue fetch failed: %s',
                        provedor.id,
                        exc,
                    )

            payment_id = (overdue_payment or {}).get('id')
            if payment_id:
                try:
                    pix_data = _asaas_request('GET', f'/payments/{payment_id}/pixQrCode')
                except Exception as exc:
                    logger.warning(
                        '[tenant-billing-status] provedor=%s PIX fetch failed: %s',
                        provedor.id,
                        exc,
                    )

        payment_payload = None
        if overdue_payment:
            payment_payload = {
                'id': overdue_payment.get('id'),
                'value': overdue_payment.get('value'),
                'dueDate': overdue_payment.get('dueDate'),
                'invoiceUrl': overdue_payment.get('invoiceUrl'),
                'description': overdue_payment.get('description'),
            }

        return Response(
            {
                'blocked': True,
                'reason': reason_default,
                'payment': payment_payload,
                'pix': pix_data if isinstance(pix_data, dict) else None,
            }
        )


class PlanoSerializer(serializers.ModelSerializer):
    provedores_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = Plano
        fields = [
            'id', 'nome', 'descricao', 'valor', 'ciclo', 'max_canais', 'max_usuarios',
            'ativo', 'ordem', 'provedores_count', 'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']

    def validate_nome(self, value):
        value = (value or '').strip()
        if not value:
            raise serializers.ValidationError('Informe o nome do plano.')
        return value

    def validate_ciclo(self, value):
        value = (value or 'MONTHLY').upper()
        if value not in ASAAS_CYCLES:
            raise serializers.ValidationError('Ciclo inválido.')
        return value

    def validate_valor(self, value):
        if value is not None and value < 0:
            raise serializers.ValidationError('O valor não pode ser negativo.')
        return value


class IsSuperadminOrReadOnly(permissions.BasePermission):
    def has_permission(self, request, view):
        if not (request.user and request.user.is_authenticated):
            return False
        if request.method in permissions.SAFE_METHODS:
            return True
        return getattr(request.user, 'user_type', '') == 'superadmin'


class PlanoViewSet(viewsets.ModelViewSet):
    serializer_class = PlanoSerializer
    permission_classes = [IsSuperadminOrReadOnly]
    pagination_class = None

    def get_queryset(self):
        from django.db.models import Count

        return Plano.objects.annotate(provedores_count=Count('provedores'))

    def perform_update(self, serializer):
        before = serializer.instance
        old_limits = (before.max_canais, before.max_usuarios, before.nome)
        plano = serializer.save()
        if (plano.max_canais, plano.max_usuarios, plano.nome) != old_limits:
            push_plan_limits_async(list(plano.provedores.values_list('id', flat=True)))

    def destroy(self, request, *args, **kwargs):
        plano = self.get_object()
        em_uso = plano.provedores.count()
        if em_uso:
            return Response(
                {'error': f'Este plano está em uso por {em_uso} provedor(es). Desative-o em vez de excluir.'},
                status=400,
            )
        return super().destroy(request, *args, **kwargs)


class ProvedorViewSet(viewsets.ModelViewSet):
    queryset = Provedor.objects.select_related('mobile_app', 'acs', 'plano').all()
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = ProvedorSerializer

    @action(detail=False, methods=['get'], url_path='asaas-overdue',
            permission_classes=[permissions.IsAuthenticated])
    def asaas_overdue(self, request):
        """
        GET /api/provedores/asaas-overdue/
        Provedores com fatura OVERDUE no Asaas (consulta em lote na API).
        """
        from .asaas_overdue_dashboard import get_provedores_asaas_overdue

        data = get_provedores_asaas_overdue()
        status_code = 200 if data.get('asaas_configured') else 503
        return Response(data, status=status_code)

    @action(detail=False, methods=['get'], url_path='billing-overview',
            permission_classes=[permissions.IsAuthenticated])
    def billing_overview(self, request):
        """
        GET /api/provedores/billing-overview/
        Vencimentos no dia, mensagens de cobrança enviadas e títulos recebidos.
        """
        from .billing_dashboard import get_billing_overview

        data = get_billing_overview()
        status_code = 200 if data.get('asaas_configured') else 503
        return Response(data, status=status_code)

    @action(detail=False, methods=['get'], url_path='id-sequence-status',
            permission_classes=[permissions.IsAuthenticated])
    def id_sequence_status(self, request):
        """
        Retorna status do contador/sequence de super_core_provedor.id (apenas no DB do Superadmin).
        """
        max_id = Provedor.objects.order_by('-id').values_list('id', flat=True).first() or 0
        return Response({
            'db_vendor': connection.vendor,
            'max_id': int(max_id),
            'next_suggested': int(max_id) + 1,
        })

    @action(detail=False, methods=['get'], url_path='health-overview',
            permission_classes=[permissions.IsAuthenticated])
    def health_overview(self, request):
        """GET /api/provedores/health-overview/ — painel de saúde (verde/amarelo/vermelho) por provedor."""
        if getattr(request.user, 'user_type', '') != 'superadmin' and not request.user.is_superuser:
            return Response({'error': 'Forbidden'}, status=403)
        from .services.provider_health import health_overview
        return Response(health_overview())

    @action(detail=True, methods=['post'], url_path='health-check',
            permission_classes=[permissions.IsAuthenticated])
    def health_check(self, request, pk=None):
        """POST /api/provedores/{id}/health-check/ — consulta /api/health/ do tenant agora."""
        if getattr(request.user, 'user_type', '') != 'superadmin' and not request.user.is_superuser:
            return Response({'error': 'Forbidden'}, status=403)
        from .services.provider_health import live_check
        return Response(live_check(self.get_object()))

    @action(detail=False, methods=['post'], url_path='id-sequence-reset',
            permission_classes=[permissions.IsAuthenticated])
    def id_sequence_reset(self, request):
        """
        Alinha a sequence do PK (id) para MAX(id)+1 no Postgres do Superadmin.
        """
        user = getattr(request, 'user', None)
        if not user or getattr(user, 'user_type', '') != 'superadmin':
            return Response({'error': 'Forbidden'}, status=403)

        max_id = Provedor.objects.order_by('-id').values_list('id', flat=True).first() or 0
        target_next = int(max_id) + 1

        if connection.vendor != 'postgresql':
            return Response({
                'success': False,
                'error': 'DB não é PostgreSQL; reset de sequence não aplicável.',
                'db_vendor': connection.vendor,
                'max_id': int(max_id),
                'next_suggested': target_next,
            }, status=400)

        # Define o próximo valor da sequence para MAX(id)+1 (sem risco de colisão)
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT setval("
                "pg_get_serial_sequence('super_core_provedor','id'), "
                "%s, "
                "false"
                ")",
                [target_next],
            )

        return Response({
            'success': True,
            'max_id': int(max_id),
            'next_now': target_next,
        })
    
    @action(detail=False, methods=['get'], url_path='lookup-by-subdomain',
            permission_classes=[permissions.AllowAny])
    def lookup_by_subdomain(self, request):
        """
        Retorna o provedor_id correspondente a um subdomínio.
        Usado pelo tenant para descobrir o seu próprio id sem depender de variáveis de ambiente.

        GET /api/provedores/lookup-by-subdomain/?subdomain=cliente.niohub.com.br&secret=...
        """
        secret = request.query_params.get('secret', '')
        if not _admin_webhook_secret_ok(secret):
            return Response({'error': 'Não autorizado.'}, status=401)

        subdomain = (request.query_params.get('subdomain') or '').strip().lower()
        if not subdomain:
            return Response({'error': 'Parâmetro subdomain obrigatório.'}, status=400)

        # Aceita tanto FQDN ("cliente.niohub.com.br") quanto apenas slug ("cliente")
        # Evita __icontains para não retornar o provedor errado.
        slug = subdomain.split('.', 1)[0]
        provedor = Provedor.objects.filter(subdomain__iexact=subdomain).first()
        if not provedor and slug:
            provedor = (
                Provedor.objects.filter(subdomain__iexact=slug).first()
                or Provedor.objects.filter(subdomain__istartswith=f"{slug}.").first()
            )

        if not provedor:
            return Response({'error': 'Provedor não encontrado para este subdomínio.'}, status=404)

        return Response({
            'provedor_id': provedor.id,
            'nome': provedor.nome,
            'subdomain': provedor.subdomain,
            # Devolvemos o integration_token para que tenants sem SUPERADMIN_PROVIDER_TOKEN
            # possam auto-recuperar a credencial sem redeploy.
            'integration_token': (provedor.integration_token or '').strip(),
            'is_active': provedor.is_active,
            'subscription_status': provedor.subscription_status or '',
            'status': provedor.status or '',
        })

    @action(detail=False, methods=['get'], url_path='lookup-by-provedor-id',
            permission_classes=[permissions.AllowAny])
    def lookup_by_provedor_id(self, request):
        """
        Retorna credenciais do tenant pelo id do provedor (dev local / fallback sem SUBDOMAIN).

        GET /api/provedores/lookup-by-provedor-id/?provedor_id=6&secret=...
        """
        secret = request.query_params.get('secret', '')
        if not _admin_webhook_secret_ok(secret):
            return Response({'error': 'Não autorizado.'}, status=401)

        raw_pid = request.query_params.get('provedor_id')
        try:
            provedor_id = int(raw_pid)
        except (TypeError, ValueError):
            return Response({'error': 'provedor_id inválido'}, status=400)

        provedor = Provedor.objects.filter(id=provedor_id).first()
        if not provedor:
            return Response({'error': 'Provedor não encontrado'}, status=404)

        return Response({
            'provedor_id': provedor.id,
            'nome': provedor.nome,
            'subdomain': provedor.subdomain,
            'integration_token': (provedor.integration_token or '').strip(),
            'is_active': provedor.is_active,
            'subscription_status': provedor.subscription_status or '',
            'status': provedor.status or '',
        })

    @action(detail=False, methods=['get'], url_path='billing-block-config',
            permission_classes=[permissions.AllowAny])
    def billing_block_config(self, request):
        """
        Configuração de auto-bloqueio por Asaas (para tenants sincronizarem regras).

        GET /api/provedores/billing-block-config/?secret=...
        """
        secret = request.query_params.get('secret', '')
        config = SystemConfig.objects.first()
        payload = (config.payload or {}) if config else {}
        expected_secret = (payload.get('ADMIN_WEBHOOK_SECRET') or '')

        if not expected_secret or secret != expected_secret:
            return Response({'error': 'Não autorizado.'}, status=401)

        try:
            min_days = int(payload.get('billing_provedor_block_min_days_late', 4))
        except (TypeError, ValueError):
            min_days = 4

        return Response({
            'billing_provedor_auto_block_enabled': bool(payload.get('billing_provedor_auto_block_enabled', False)),
            'billing_provedor_block_min_days_late': max(0, min(365, min_days)),
        })

    @action(detail=False, methods=['get'], url_path='vps-pool')
    def vps_pool(self, request):
        try:
            config = SystemConfig.objects.first()
            if not config:
                logger.warning("SystemConfig nao encontrado ao buscar VPS Pool.")
                return Response([], status=200)
            
            token = config.payload.get('hetzner_api_token')
            if not token:
                logger.warning("Token da Hetzner (hetzner_api_token) nao encontrado no SystemConfig.")
                return Response([], status=200)
                
            headers = {"Authorization": f"Bearer {token}"}
            # Log para debug (mascarado)
            masked_token = token[:6] + "..." + token[-4:] if token else "None"
            logger.info(f"Buscando servidores na Hetzner...")
            
            # 1. Pegar VPS cadastradas no nosso banco
            registered_vps = VpsServer.objects.filter(is_active=True)
            vps_list = []
            for v in registered_vps:
                vps_list.append({
                    "key": str(v.id),
                    "label": f"{v.name}",
                    "api_url": v.api_url,
                    "max_providers": v.max_capacity,
                    "is_registered": True
                })

            # 2. Pegar da Hetzner (para sugestão)
            response = requests.get("https://api.hetzner.cloud/v1/servers", headers=headers, timeout=10)
            if response.status_code == 200:
                servers = response.json().get('servers', [])
                # Pegar IPs das VPS cadastradas para não duplicar
                registered_ips = [v.api_url.split('//')[-1].split(':')[0] for v in registered_vps]
                
                for s in servers:
                    ip = s.get('public_net', {}).get('ipv4', {}).get('ip', '')
                    if ip not in registered_ips:
                        vps_list.append({
                            "key": f"hetzner-{s.get('id')}",
                            "label": f"{s.get('name')} (Hetzner - Não Cadastrada)",
                            "api_url": ip,
                            "max_providers": 3,
                            "is_registered": False
                        })
            
            logger.info(f"VPS Pool carregado: {len(vps_list)} servidores (Cadastrados + Hetzner).")
            return Response(vps_list)
        except Exception as e:
            logger.error(f"Erro ao buscar VPS na Hetzner: {e}")
            return Response([], status=200)

    def perform_update(self, serializer):
        instance = self.get_object()
        old_status = instance.status
        old_active = instance.is_active
        old_bot_mode = instance.bot_mode
        old_agent_mode = getattr(instance, 'agent_mode', 'isp')
        old_plan = (instance.plano_id, instance.canais_extras, instance.usuarios_extras)

        updated_instance = serializer.save()

        if (updated_instance.plano_id, updated_instance.canais_extras, updated_instance.usuarios_extras) != old_plan:
            push_plan_limits_async([updated_instance.id])

        if updated_instance.asaas_customer_id and updated_instance.notification_disabled:
            try:
                self._asaas_apply_notifications(updated_instance, {}, updated_instance.asaas_customer_id)
            except Exception as exc:
                logger.warning(
                    "[Asaas] Falha ao propagar notification_disabled no save do provedor %s: %s",
                    updated_instance.id,
                    exc,
                )

        new_status = updated_instance.status
        new_active = updated_instance.is_active
        new_bot_mode = updated_instance.bot_mode
        new_agent_mode = getattr(updated_instance, 'agent_mode', 'isp')

        if old_status != new_status or old_active != new_active:
            # Espelha is_active no perfil do app mobile (bloqueia clientes)
            try:
                from mobile_app.models import MobileAppProfile
                MobileAppProfile.objects.filter(provedor_id=updated_instance.id).update(
                    is_active=bool(new_active),
                )
            except Exception as exc:
                logger.warning(
                    '[mobile_app] Falha ao sincronizar is_active do perfil app provedor %s: %s',
                    updated_instance.id,
                    exc,
                )
            try:
                from acs.services import sync_acs_access
                sync_acs_access(updated_instance, bool(new_active), source='billing')
            except Exception as exc:
                logger.warning(
                    '[acs] Falha ao sincronizar licenças ACS provedor %s: %s',
                    updated_instance.id,
                    exc,
                )
            thread = threading.Thread(
                target=notify_provider_panel,
                args=(updated_instance.id, new_active, new_status),
                daemon=True,
            )
            thread.start()

        if old_bot_mode != new_bot_mode or old_agent_mode != new_agent_mode:
            thread = threading.Thread(
                target=_sync_bot_mode_to_tenant,
                args=(updated_instance,),
                daemon=True,
            )
            thread.start()

    def perform_create(self, serializer):
        vps_id = self.request.data.get('vps')
        if vps_id and str(vps_id).startswith('hetzner-'):
            raise serializers.ValidationError({"vps": "Esta VPS da Hetzner ainda não foi cadastrada no sistema. Por favor, cadastre-a primeiro na aba de Servidores."})
        instance = serializer.save()
        if not (instance.integration_token or '').strip():
            instance.integration_token = _generate_provider_integration_token()
            instance.save(update_fields=['integration_token'])
        # Após criar o Provedor, sincronizar niohub no tenant (liga-o ao Provedor correcto)
        thread = threading.Thread(target=_sync_niohub_in_tenant, args=(instance,), daemon=True)
        thread.start()
        if instance.plano_id:
            push_plan_limits_async([instance.id])

    def _require_superadmin(self, request):
        user = getattr(request, 'user', None)
        if not user or getattr(user, 'user_type', '') != 'superadmin':
            raise PermissionError('Forbidden')

    def _asaas_build_customer_payload(self, provedor: Provedor, incoming: dict) -> dict:
        """
        Monta payload de customer do Asaas com os campos mais comuns do form do Superadmin.
        """
        name = (incoming.get('company') or incoming.get('nome') or provedor.nome or '').strip()
        cpf_cnpj = _normalize_cpf_cnpj(incoming.get('cpf_cnpj') or provedor.cpf_cnpj or '')
        email = (incoming.get('email_contato') or provedor.email_contato or '').strip()
        phone = (incoming.get('phone') or provedor.phone or '').strip()
        mobile = (incoming.get('mobile_phone') or provedor.mobile_phone or '').strip()
        postal_code = (incoming.get('postal_code') or provedor.postal_code or '').strip()
        address_number = (incoming.get('address_number') or provedor.address_number or '').strip()
        complement = (incoming.get('complement') or provedor.complement or '').strip()
        province = (incoming.get('province') or provedor.province or '').strip()

        payload = {
            'name': name or provedor.nome,
        }
        if cpf_cnpj:
            payload['cpfCnpj'] = cpf_cnpj
        if email:
            payload['email'] = email
        if phone:
            payload['phone'] = phone
        if mobile:
            payload['mobilePhone'] = mobile
        if postal_code:
            payload['postalCode'] = postal_code
        if address_number:
            payload['addressNumber'] = address_number
        if complement:
            payload['complement'] = complement
        if province:
            payload['province'] = province
        # Campos opcionais usados em alguns cadastros
        if incoming.get('observations') or provedor.observations:
            payload['observations'] = (incoming.get('observations') or provedor.observations or '').strip()
        if incoming.get('foreign_customer') is True or provedor.foreign_customer:
            payload['foreignCustomer'] = True
        if self._notification_disabled_for(provedor, incoming):
            payload['notificationDisabled'] = True
        return payload

    def _notification_disabled_for(self, provedor: Provedor, incoming: dict | None = None) -> bool:
        incoming = incoming or {}
        if 'notification_disabled' in incoming:
            return coerce_bool(incoming.get('notification_disabled'), default=False)
        return bool(provedor.notification_disabled)

    def _persist_notification_disabled_from_incoming(self, provedor: Provedor, incoming: dict) -> None:
        if 'notification_disabled' not in incoming:
            return
        provedor.notification_disabled = self._notification_disabled_for(provedor, incoming)
        provedor.save(update_fields=['notification_disabled'])

    def _clear_provedor_asaas_links(self, provedor: Provedor) -> None:
        provedor.asaas_customer_id = None
        self._clear_provedor_asaas_subscription(provedor, save=False)
        provedor.save(update_fields=[
            'asaas_customer_id',
            'asaas_subscription_id',
            'subscription_status',
            'subscription_value',
            'subscription_cycle',
            'subscription_billing_type',
            'subscription_next_due_date',
        ])

    def _clear_provedor_asaas_subscription(self, provedor: Provedor, *, save: bool = True) -> None:
        provedor.asaas_subscription_id = None
        provedor.subscription_status = ''
        provedor.subscription_value = 0
        provedor.subscription_cycle = 'MONTHLY'
        provedor.subscription_billing_type = 'BOLETO'
        provedor.subscription_next_due_date = None
        if save:
            provedor.save(update_fields=[
                'asaas_subscription_id',
                'subscription_status',
                'subscription_value',
                'subscription_cycle',
                'subscription_billing_type',
                'subscription_next_due_date',
            ])

    def _asaas_apply_notifications(self, provedor: Provedor, incoming: dict, customer_id: str) -> None:
        if not self._notification_disabled_for(provedor, incoming):
            return
        customer_payload = self._asaas_build_customer_payload(provedor, incoming)
        res = apply_provedor_notification_settings(
            customer_id,
            notification_disabled=True,
            customer_payload=customer_payload,
        )
        if res.get('customer_removed'):
            logger.warning(
                "[Asaas] Cliente %s excluído no Asaas — removendo vínculos locais do provedor %s",
                customer_id,
                provedor.id,
            )
            self._clear_provedor_asaas_links(provedor)
            return
        if not res.get('success'):
            logger.warning(
                "[Asaas] Falha ao desativar notificações do cliente %s: %s",
                customer_id,
                res.get('error'),
            )

    def _asaas_find_or_create_customer(self, provedor: Provedor, incoming: dict) -> str:
        """
        Retorna customer_id do Asaas (cria ou atualiza).
        Estratégia:
        - se provedor.asaas_customer_id existe -> PATCH
        - senão tenta buscar por cpfCnpj (se tiver) -> usa primeiro
        - senão cria novo
        """
        customer_payload = self._asaas_build_customer_payload(provedor, incoming)
        existing_id = (provedor.asaas_customer_id or '').strip()

        if existing_id:
            _asaas_request('PUT', f"/customers/{existing_id}", json=customer_payload)
            self._asaas_apply_notifications(provedor, incoming, existing_id)
            return existing_id

        cpf_cnpj = customer_payload.get('cpfCnpj')
        if cpf_cnpj:
            data = _asaas_request('GET', "/customers", params={'cpfCnpj': cpf_cnpj, 'limit': 10})
            items = data.get('data') or []
            if items:
                cid = items[0].get('id')
                if cid:
                    # tenta atualizar para garantir dados recentes
                    try:
                        _asaas_request('PUT', f"/customers/{cid}", json=customer_payload)
                    except Exception:
                        pass
                    self._asaas_apply_notifications(provedor, incoming, cid)
                    return cid

        created = _asaas_request('POST', "/customers", json=customer_payload)
        cid = created.get('id')
        if not cid:
            raise RuntimeError('Asaas não retornou customer.id')
        self._asaas_apply_notifications(provedor, incoming, cid)
        return cid

    def _asaas_fetch_subscription_status(self, subscription_id: str) -> dict:
        sub = _asaas_request('GET', f"/subscriptions/{subscription_id}")
        return sub or {}

    def _asaas_fetch_overdue_payment(self, subscription_id: str) -> dict | None:
        """
        Busca 1 cobrança em atraso da assinatura.
        """
        data = _asaas_request('GET', "/payments", params={'subscription': subscription_id, 'status': 'OVERDUE', 'limit': 10})
        items = _asaas_confirm_payments(data.get('data') or [], max_items=10)
        return items[0] if items else None

    def _apply_billing_block_if_needed(self, provedor: Provedor, *, has_overdue: bool, days_late: int, subscription_status: str | None):
        enabled, min_days = _should_auto_block_from_config()
        if not enabled:
            return

        def _sync_mobile_app(active: bool):
            try:
                from mobile_app.models import MobileAppProfile
                MobileAppProfile.objects.filter(provedor_id=provedor.id).update(is_active=bool(active))
            except Exception:
                pass

        def _sync_acs(active: bool):
            try:
                from acs.services import sync_acs_access
                sync_acs_access(provedor, bool(active), source='billing')
            except Exception:
                pass

        # Bloqueia quando em atraso e passou do threshold
        if has_overdue and days_late >= min_days:
            if provedor.is_active or provedor.status != 'suspenso':
                provedor.is_active = False
                provedor.status = 'suspenso'
                provedor.subscription_status = (subscription_status or provedor.subscription_status or 'OVERDUE')
                provedor.save(update_fields=['is_active', 'status', 'subscription_status'])
                _sync_mobile_app(False)
                _sync_acs(False)
                reason = (
                    f'Acesso suspenso: fatura vencida há {days_late} dia(s) '
                    f'(limite: {min_days} dia(s) após o vencimento). '
                    'Regularize o pagamento para reativar o acesso.'
                )
                try:
                    import threading
                    threading.Thread(
                        target=notify_provider_panel,
                        args=(provedor.id, False, 'suspenso'),
                        kwargs={'block_reason': reason},
                        daemon=True,
                    ).start()
                except Exception:
                    pass
            return

        # Se não há atraso e a assinatura está ativa, reabilita apenas quando o bloqueio aparenta ser financeiro.
        # (Evita desfazer suspensão manual sem sinal de billing.)
        if (not has_overdue) and (subscription_status or '').upper() == 'ACTIVE':
            if (not provedor.is_active) and provedor.status == 'suspenso' and (provedor.subscription_status or '').upper() in ('OVERDUE', 'INACTIVE', 'CANCELLED', 'PENDING'):
                provedor.is_active = True
                provedor.status = 'ativo'
                provedor.subscription_status = 'ACTIVE'
                provedor.save(update_fields=['is_active', 'status', 'subscription_status'])
                _sync_mobile_app(True)
                _sync_acs(True)
                try:
                    import threading
                    threading.Thread(
                        target=notify_provider_panel,
                        args=(provedor.id, True, 'ativo'),
                        daemon=True,
                    ).start()
                except Exception:
                    pass

    @action(detail=True, methods=['post'], url_path='sync_asaas')
    def sync_asaas(self, request, pk=None):
        """
        POST /api/provedores/<id>/sync_asaas/
        Cria/atualiza customer no Asaas e grava asaas_customer_id.
        """
        try:
            self._require_superadmin(request)
        except PermissionError:
            return Response({'error': 'Forbidden'}, status=403)

        provedor = self.get_object()
        incoming = request.data if isinstance(request.data, dict) else {}
        try:
            self._persist_notification_disabled_from_incoming(provedor, incoming)
            customer_id = self._asaas_find_or_create_customer(provedor, incoming)
            if (provedor.asaas_customer_id or '').strip() != customer_id:
                provedor.asaas_customer_id = customer_id
                provedor.save(update_fields=['asaas_customer_id'])
            self._asaas_apply_notifications(provedor, incoming, customer_id)
            return Response({'success': True, 'customer_id': customer_id})
        except Exception as exc:
            return Response({'success': False, 'error': str(exc)}, status=400)

    @action(detail=True, methods=['post'], url_path='create_subscription')
    def create_subscription(self, request, pk=None):
        """
        POST /api/provedores/<id>/create_subscription/
        Body: { value, cycle, billingType, nextDueDate, billing_provider?: 'asaas'|'inter' }
        """
        try:
            self._require_superadmin(request)
        except PermissionError:
            return Response({'error': 'Forbidden'}, status=403)

        provedor = self.get_object()
        payload = request.data if isinstance(request.data, dict) else {}

        try:
            self._persist_notification_disabled_from_incoming(provedor, payload)

            provider = (
                str(
                    payload.get('billing_provider')
                    or payload.get('billingProvider')
                    or provedor.billing_provider
                    or 'asaas'
                )
                .strip()
                .lower()
            )
            if provider not in (Provedor.BILLING_PROVIDER_ASAAS, Provedor.BILLING_PROVIDER_INTER):
                return Response(
                    {'success': False, 'error': 'billing_provider inválido (asaas|inter)'},
                    status=400,
                )

            if provider == Provedor.BILLING_PROVIDER_INTER:
                from .inter_billing_service import create_inter_subscription

                return Response(create_inter_subscription(provedor, payload))

            customer_id = (provedor.asaas_customer_id or '').strip()
            if not customer_id:
                customer_id = self._asaas_find_or_create_customer(provedor, payload)
                provedor.asaas_customer_id = customer_id
                provedor.save(update_fields=['asaas_customer_id'])

            notify_off = self._notification_disabled_for(provedor, payload)
            if notify_off:
                self._asaas_apply_notifications(provedor, payload, customer_id)

            value = payload.get('value') or provedor.subscription_value
            cycle = (payload.get('cycle') or provedor.subscription_cycle or 'MONTHLY').upper()
            billing_type = (payload.get('billingType') or provedor.subscription_billing_type or 'BOLETO').upper()
            next_due_date = payload.get('nextDueDate') or (
                provedor.subscription_next_due_date.isoformat() if provedor.subscription_next_due_date else None
            )
            if not next_due_date:
                return Response({'success': False, 'error': 'nextDueDate é obrigatório'}, status=400)

            sub_payload = {
                'customer': customer_id,
                'value': float(value) if value is not None else 0,
                'cycle': cycle,
                'billingType': billing_type,
                'nextDueDate': str(next_due_date),
            }
            if notify_off:
                sub_payload['notificationDisabled'] = True
            created = _asaas_request('POST', "/subscriptions", json=sub_payload)
            sub_id = created.get('id')
            if not sub_id:
                raise RuntimeError('Asaas não retornou subscription.id')

            if notify_off:
                self._asaas_apply_notifications(provedor, payload, customer_id)

            provedor.billing_provider = Provedor.BILLING_PROVIDER_ASAAS
            provedor.asaas_subscription_id = sub_id
            provedor.subscription_value = sub_payload['value']
            provedor.subscription_cycle = cycle
            provedor.subscription_billing_type = billing_type
            try:
                from datetime import date

                y, m, d = [int(x) for x in str(next_due_date).split('-')[:3]]
                provedor.subscription_next_due_date = date(y, m, d)
            except Exception:
                pass
            provedor.subscription_status = created.get('status') or provedor.subscription_status or 'PENDING'
            provedor.save(
                update_fields=[
                    'billing_provider',
                    'asaas_subscription_id',
                    'subscription_value',
                    'subscription_cycle',
                    'subscription_billing_type',
                    'subscription_next_due_date',
                    'subscription_status',
                ]
            )
            return Response({'success': True, 'subscription_id': sub_id, 'billing_provider': 'asaas'})
        except Exception as exc:
            return Response({'success': False, 'error': str(exc)}, status=400)

    @action(detail=True, methods=['post'], url_path='verify_asaas')
    def verify_asaas(self, request, pk=None):
        """
        POST /api/provedores/<id>/verify_asaas/
        Consulta o Asaas em tempo real. Se cliente/assinatura não existir (404), limpa IDs locais.
        """
        try:
            self._require_superadmin(request)
        except PermissionError:
            return Response({'error': 'Forbidden'}, status=403)

        provedor = self.get_object()
        try:
            # Portador Inter: não consultar/limpar via Asaas
            if (
                (provedor.billing_provider or '') == Provedor.BILLING_PROVIDER_INTER
                or (provedor.asaas_subscription_id or '').startswith('INTER-SUB-')
            ):
                from .billing_auto_block import sync_provedor_billing_block
                from .inter_billing_service import (
                    list_inter_payments_for_provedor,
                    sync_open_inter_charges_from_api,
                )

                try:
                    sync_open_inter_charges_from_api(provedor)
                except Exception as exc:
                    logger.warning('[AsaasVerify] Sync Inter provedor=%s: %s', provedor.id, exc)
                try:
                    sync_provedor_billing_block(provedor)
                except Exception as exc:
                    logger.warning('[AsaasVerify] AutoBlock Inter provedor=%s: %s', provedor.id, exc)
                provedor.refresh_from_db()

                return Response({
                    'success': True,
                    'billing_provider': 'inter',
                    'cleared': False,
                    'asaas_customer_id': provedor.asaas_customer_id,
                    'asaas_subscription_id': provedor.asaas_subscription_id,
                    'subscription_status': provedor.subscription_status,
                    'subscription_value': provedor.subscription_value,
                    'subscription_cycle': provedor.subscription_cycle,
                    'subscription_billing_type': provedor.subscription_billing_type,
                    'subscription_next_due_date': (
                        provedor.subscription_next_due_date.isoformat()
                        if provedor.subscription_next_due_date
                        else None
                    ),
                    'status_info': {
                        'customer': 'inter_local',
                        'subscription': (provedor.subscription_status or 'PENDING').lower(),
                    },
                    'payments': list_inter_payments_for_provedor(provedor),
                })

            changes = False
            cleared = False
            status_info = {'customer': 'not_checked', 'subscription': 'not_checked'}
            customer_id = (provedor.asaas_customer_id or '').strip()
            subscription_id = (provedor.asaas_subscription_id or '').strip()

            if customer_id:
                try:
                    cust = _asaas_request('GET', f'/customers/{customer_id}')
                    if not asaas_customer_is_active(cust):
                        logger.warning(
                            '[AsaasVerify] Cliente %s excluído no Asaas (deleted=true). Limpando.',
                            customer_id,
                        )
                        self._clear_provedor_asaas_links(provedor)
                        customer_id = ''
                        subscription_id = ''
                        status_info['customer'] = 'deleted_locally'
                        status_info['subscription'] = 'deleted_locally'
                        cleared = True
                        changes = True
                    else:
                        status_info['customer'] = 'active'
                except RuntimeError as exc:
                    code = _asaas_http_status_from_error(exc)
                    if code == 404 or asaas_entity_is_removed(code, str(exc)):
                        logger.warning('[AsaasVerify] Cliente %s indisponível no Asaas. Limpando.', customer_id)
                        self._clear_provedor_asaas_links(provedor)
                        customer_id = ''
                        subscription_id = ''
                        status_info['customer'] = 'deleted_locally'
                        status_info['subscription'] = 'deleted_locally'
                        cleared = True
                        changes = True
                    else:
                        raise

            if customer_id and subscription_id:
                try:
                    sub = self._asaas_fetch_subscription_status(subscription_id)
                    if not asaas_subscription_is_active(sub):
                        logger.warning(
                            '[AsaasVerify] Assinatura %s removida/inativa no Asaas. Limpando vínculo local.',
                            subscription_id,
                        )
                        self._clear_provedor_asaas_subscription(provedor)
                        subscription_id = ''
                        status_info['subscription'] = 'deleted_locally'
                        cleared = True
                        changes = True
                    else:
                        subscription_status = (sub.get('status') or provedor.subscription_status or 'PENDING')
                        if provedor.subscription_status != subscription_status:
                            provedor.subscription_status = subscription_status
                            changes = True
                        if sub.get('value') is not None and provedor.subscription_value != sub.get('value'):
                            provedor.subscription_value = sub.get('value')
                            changes = True
                        if sub.get('cycle') and provedor.subscription_cycle != sub.get('cycle'):
                            provedor.subscription_cycle = sub.get('cycle')
                            changes = True
                        if sub.get('billingType') and provedor.subscription_billing_type != sub.get('billingType'):
                            provedor.subscription_billing_type = sub.get('billingType')
                            changes = True
                        next_due = sub.get('nextDueDate')
                        if next_due:
                            try:
                                from datetime import date
                                y, m, d = [int(x) for x in str(next_due).split('-')[:3]]
                                new_due = date(y, m, d)
                                if provedor.subscription_next_due_date != new_due:
                                    provedor.subscription_next_due_date = new_due
                                    changes = True
                            except Exception:
                                pass
                        status_info['subscription'] = subscription_status.lower()

                        overdue_payment = self._asaas_fetch_overdue_payment(subscription_id)
                        days_late = _compute_days_late((overdue_payment or {}).get('dueDate'))
                        self._apply_billing_block_if_needed(
                            provedor,
                            has_overdue=bool(overdue_payment),
                            days_late=days_late,
                            subscription_status=subscription_status,
                        )
                        if not overdue_payment and (subscription_status or '').upper() == 'ACTIVE':
                            if (provedor.subscription_status or '').upper() == 'OVERDUE':
                                provedor.subscription_status = 'ACTIVE'
                                changes = True
                except RuntimeError as exc:
                    code = _asaas_http_status_from_error(exc)
                    if code == 404 or asaas_entity_is_removed(code, str(exc)):
                        logger.warning('[AsaasVerify] Assinatura %s indisponível no Asaas. Limpando.', subscription_id)
                        self._clear_provedor_asaas_subscription(provedor)
                        subscription_id = ''
                        status_info['subscription'] = 'deleted_locally'
                        cleared = True
                        changes = True
                    else:
                        raise

            if changes:
                provedor.save()

            return Response({
                'success': True,
                'cleared': cleared,
                'status_info': status_info,
                'asaas_environment': 'sandbox' if is_asaas_sandbox() else 'production',
                'asaas_customer_id': provedor.asaas_customer_id,
                'asaas_subscription_id': provedor.asaas_subscription_id,
                'subscription_status': provedor.subscription_status,
                'subscription_value': provedor.subscription_value,
                'subscription_cycle': provedor.subscription_cycle,
                'subscription_billing_type': provedor.subscription_billing_type,
                'subscription_next_due_date': (
                    provedor.subscription_next_due_date.isoformat()
                    if provedor.subscription_next_due_date else None
                ),
            })
        except Exception as exc:
            return Response({'success': False, 'error': str(exc)}, status=400)

    @action(detail=True, methods=['post'], url_path='clear_asaas_subscription')
    def clear_asaas_subscription(self, request, pk=None):
        """
        Remove vínculo local da assinatura (Asaas ou Inter).
        Body opcional: { "cancel_on_asaas": true } — cancela no gateway antes de limpar.
        """
        try:
            self._require_superadmin(request)
        except PermissionError:
            return Response({'error': 'Forbidden'}, status=403)

        provedor = self.get_object()
        payload = request.data if isinstance(request.data, dict) else {}
        cancel_on_asaas = coerce_bool(payload.get('cancel_on_asaas'), default=False)
        subscription_id = (provedor.asaas_subscription_id or '').strip()
        had_subscription = bool(subscription_id)
        cancelled_on_asaas = False
        is_inter = (
            (provedor.billing_provider or '') == Provedor.BILLING_PROVIDER_INTER
            or subscription_id.startswith('INTER-SUB-')
        )

        if is_inter:
            from .inter_billing_service import clear_inter_subscription

            try:
                clear_inter_subscription(provedor, cancel_open_charges=cancel_on_asaas)
            except Exception as exc:
                return Response({'success': False, 'error': str(exc)}, status=400)
            return Response({
                'success': True,
                'cleared': had_subscription,
                'cancelled_on_asaas': cancel_on_asaas,
                'billing_provider': 'inter',
            })

        if cancel_on_asaas and subscription_id:
            try:
                _asaas_delete_subscription(subscription_id)
                cancelled_on_asaas = True
            except Exception as exc:
                return Response({
                    'success': False,
                    'error': f'Falha ao cancelar assinatura no Asaas: {exc}',
                }, status=400)

        if had_subscription:
            self._clear_provedor_asaas_subscription(provedor)

        return Response({
            'success': True,
            'cleared': had_subscription,
            'cancelled_on_asaas': cancelled_on_asaas,
            'asaas_environment': 'sandbox' if is_asaas_sandbox() else 'production',
            'asaas_customer_id': provedor.asaas_customer_id,
            'billing_provider': 'asaas',
        })

    @action(detail=True, methods=['get'], url_path='subscription_payments')
    def subscription_payments(self, request, pk=None):
        """Lista cobranças da assinatura (Asaas ou Inter conforme portador)."""
        try:
            self._require_superadmin(request)
        except PermissionError:
            return Response({'error': 'Forbidden'}, status=403)

        provedor = self.get_object()
        if (
            (provedor.billing_provider or '') == Provedor.BILLING_PROVIDER_INTER
            or (provedor.asaas_subscription_id or '').startswith('INTER-SUB-')
        ):
            from .inter_billing_service import list_inter_payments_for_provedor

            return Response({
                'success': True,
                'data': list_inter_payments_for_provedor(provedor),
                'provider': 'inter',
            })

        subscription_id = (provedor.asaas_subscription_id or '').strip()
        customer_id = (provedor.asaas_customer_id or '').strip()
        if not subscription_id and not customer_id:
            return Response({'success': True, 'data': []})

        params = {'limit': 50}
        if subscription_id:
            params['subscription'] = subscription_id
        elif customer_id:
            params['customer'] = customer_id

        try:
            data = _asaas_request('GET', '/payments', params=params)
        except RuntimeError as exc:
            if _asaas_http_status_from_error(exc) == 404:
                return Response({'success': True, 'data': []})
            return Response({'success': False, 'error': str(exc)}, status=400)

        payments = [_asaas_payment_summary(p) for p in _asaas_confirm_payments(data.get('data') or [], max_items=50)]
        return Response({'success': True, 'data': payments, 'provider': 'asaas'})

    @staticmethod
    def _is_inter_billing(provedor: Provedor) -> bool:
        return (
            (provedor.billing_provider or '') == Provedor.BILLING_PROVIDER_INTER
            or (provedor.asaas_subscription_id or '').startswith('INTER-SUB-')
        )

    @action(detail=True, methods=['get'], url_path='plan_usage')
    def plan_usage(self, request, pk=None):
        """GET /api/provedores/<id>/plan_usage/ — limites do plano + canais/usuários em uso no painel."""
        provedor = self.get_object()
        data = {**provedor.plan_limits(), 'canais': None, 'usuarios': None, 'sincronizado': None}
        token = (provedor.integration_token or '').strip()
        url = _tenant_admin_url(provedor, 'plan-limits')
        if not token or not url:
            data['error'] = 'Painel do provedor ainda não implantado.'
            return Response(data)
        try:
            resp = requests.get(
                url,
                params={'provedor_id': provedor.id},
                headers={'Authorization': f'Bearer {token}'},
                timeout=8,
            )
            if not resp.ok:
                data['error'] = f'O painel respondeu HTTP {resp.status_code}.'
                return Response(data)
            tenant = resp.json() or {}
        except Exception as exc:
            logger.warning('[plan-usage] Provedor %s: %s', provedor.id, exc)
            data['error'] = 'Não foi possível consultar o painel do provedor.'
            return Response(data)
        data['canais'] = tenant.get('canais')
        data['usuarios'] = tenant.get('usuarios')
        data['sincronizado'] = (
            tenant.get('max_canais') == data['max_canais']
            and tenant.get('max_usuarios') == data['max_usuarios']
        )
        if not data['sincronizado']:
            push_plan_limits_async([provedor.id])
        return Response(data)

    @action(detail=True, methods=['post'], url_path='update_payment')
    def update_payment(self, request, pk=None):
        """
        POST /api/provedores/<id>/update_payment/
        Body: { payment_id, value, dueDate, billingType?, description? }
        Altera uma cobrança aguardando pagamento ou vencida (PUT /v3/payments/{id}).
        """
        try:
            self._require_superadmin(request)
        except PermissionError:
            return Response({'error': 'Forbidden'}, status=403)

        provedor = self.get_object()
        if self._is_inter_billing(provedor):
            return Response({'success': False, 'error': 'Cobranças do Banco Inter não são editadas por aqui.'}, status=400)

        payload = request.data if isinstance(request.data, dict) else {}
        payment_id = str(payload.get('payment_id') or '').strip()
        if not payment_id:
            return Response({'success': False, 'error': 'Informe a cobrança.'}, status=400)

        try:
            current = _asaas_request('GET', f'/payments/{payment_id}')
        except RuntimeError as exc:
            return Response({'success': False, 'error': _asaas_error_text(exc)}, status=400)

        customer_id = (provedor.asaas_customer_id or '').strip()
        subscription_id = (provedor.asaas_subscription_id or '').strip()
        if not (
            (customer_id and current.get('customer') == customer_id)
            or (subscription_id and current.get('subscription') == subscription_id)
        ):
            return Response({'success': False, 'error': 'Esta cobrança não pertence a este provedor.'}, status=403)
        if current.get('deleted') or current.get('status') not in ASAAS_PAYMENT_EDITABLE:
            return Response({
                'success': False,
                'error': 'Só é possível alterar cobranças aguardando pagamento ou vencidas.',
            }, status=400)

        value = _parse_money(payload.get('value', current.get('value')))
        if value is None:
            return Response({'success': False, 'error': 'Informe um valor maior que zero.'}, status=400)
        due = _parse_iso_date(payload.get('dueDate') or current.get('dueDate'))
        if due is None:
            return Response({'success': False, 'error': 'Data de vencimento inválida.'}, status=400)
        if due < timezone.localdate():
            return Response({'success': False, 'error': 'O vencimento não pode ser uma data passada.'}, status=400)
        billing_type = str(payload.get('billingType') or current.get('billingType') or 'BOLETO').upper()
        if billing_type not in ASAAS_BILLING_TYPES:
            return Response({'success': False, 'error': 'Forma de pagamento inválida.'}, status=400)

        body = {'billingType': billing_type, 'value': value, 'dueDate': due.isoformat()}
        if 'description' in payload:
            body['description'] = str(payload.get('description') or '').strip()[:500]

        try:
            updated = _asaas_request('PUT', f'/payments/{payment_id}', json=body)
        except RuntimeError as exc:
            logger.warning('[Asaas] Falha ao atualizar cobrança %s do provedor %s: %s', payment_id, provedor.id, exc)
            return Response({'success': False, 'error': _asaas_error_text(exc)}, status=400)
        return Response({'success': True, 'payment': _asaas_payment_summary(updated or {**current, **body})})

    @action(detail=True, methods=['post'], url_path='update_subscription')
    def update_subscription(self, request, pk=None):
        """
        POST /api/provedores/<id>/update_subscription/
        Body: { value?, cycle?, billingType?, nextDueDate?, description?, updatePendingPayments? }
        Altera a recorrência (PUT /v3/subscriptions/{id}). Cobranças já geradas só mudam com updatePendingPayments.
        """
        try:
            self._require_superadmin(request)
        except PermissionError:
            return Response({'error': 'Forbidden'}, status=403)

        provedor = self.get_object()
        if self._is_inter_billing(provedor):
            return Response({'success': False, 'error': 'Assinaturas do Banco Inter não são editadas por aqui.'}, status=400)
        subscription_id = (provedor.asaas_subscription_id or '').strip()
        if not subscription_id:
            return Response({'success': False, 'error': 'Este provedor não tem assinatura no Asaas.'}, status=400)

        payload = request.data if isinstance(request.data, dict) else {}
        body = {}
        if payload.get('value') not in (None, ''):
            value = _parse_money(payload.get('value'))
            if value is None:
                return Response({'success': False, 'error': 'Informe um valor maior que zero.'}, status=400)
            body['value'] = value
        if payload.get('cycle'):
            cycle = str(payload['cycle']).upper()
            if cycle not in ASAAS_CYCLES:
                return Response({'success': False, 'error': 'Ciclo inválido.'}, status=400)
            body['cycle'] = cycle
        if payload.get('billingType'):
            billing_type = str(payload['billingType']).upper()
            if billing_type not in ASAAS_BILLING_TYPES:
                return Response({'success': False, 'error': 'Forma de pagamento inválida.'}, status=400)
            body['billingType'] = billing_type
        if payload.get('nextDueDate'):
            due = _parse_iso_date(payload['nextDueDate'])
            if due is None:
                return Response({'success': False, 'error': 'Data do próximo vencimento inválida.'}, status=400)
            if due < timezone.localdate():
                return Response({'success': False, 'error': 'O próximo vencimento não pode ser uma data passada.'}, status=400)
            body['nextDueDate'] = due.isoformat()
        if 'description' in payload:
            body['description'] = str(payload.get('description') or '').strip()[:500]
        if not body:
            return Response({'success': False, 'error': 'Nada para alterar.'}, status=400)
        body['updatePendingPayments'] = coerce_bool(payload.get('updatePendingPayments'), default=False)

        try:
            sub = _asaas_request('PUT', f'/subscriptions/{subscription_id}', json=body) or {}
        except RuntimeError as exc:
            logger.warning('[Asaas] Falha ao atualizar assinatura %s do provedor %s: %s', subscription_id, provedor.id, exc)
            return Response({'success': False, 'error': _asaas_error_text(exc)}, status=400)

        provedor.subscription_value = sub.get('value', body.get('value', provedor.subscription_value))
        provedor.subscription_cycle = sub.get('cycle') or body.get('cycle') or provedor.subscription_cycle
        provedor.subscription_billing_type = (
            sub.get('billingType') or body.get('billingType') or provedor.subscription_billing_type
        )
        next_due = _parse_iso_date(sub.get('nextDueDate') or body.get('nextDueDate'))
        if next_due:
            provedor.subscription_next_due_date = next_due
        if sub.get('status'):
            provedor.subscription_status = sub['status']
        provedor.save(update_fields=[
            'subscription_value',
            'subscription_cycle',
            'subscription_billing_type',
            'subscription_next_due_date',
            'subscription_status',
        ])
        return Response({
            'success': True,
            'subscription_status': provedor.subscription_status,
            'subscription_value': provedor.subscription_value,
            'subscription_cycle': provedor.subscription_cycle,
            'subscription_billing_type': provedor.subscription_billing_type,
            'subscription_next_due_date': (
                provedor.subscription_next_due_date.isoformat() if provedor.subscription_next_due_date else None
            ),
            'pending_updated': body['updatePendingPayments'],
        })

    @action(detail=True, methods=['get'], url_path='integration-token')
    def integration_token_status(self, request, pk=None):
        provedor = self.get_object()
        token = (provedor.integration_token or '').strip()
        masked = ''
        if token:
            masked = f"{token[:4]}...{token[-4:]}"
        return Response({
            'configured': bool(token),
            'masked': masked,
            'last_used_at': provedor.integration_token_last_used_at,
        })

    @action(detail=True, methods=['post'], url_path='integration-token/rotate')
    def rotate_integration_token(self, request, pk=None):
        provedor = self.get_object()
        token = _generate_provider_integration_token()
        provedor.integration_token = token
        provedor.integration_token_last_used_at = None
        provedor.save(update_fields=['integration_token', 'integration_token_last_used_at'])
        # Aplicar imediatamente no tenant via redeploy (env SUPERADMIN_PROVIDER_TOKEN)
        if provedor.vps_id:
            def _redeploy():
                try:
                    from .services.portainer_service import PortainerService
                    service = PortainerService(provedor.vps)
                    service.deploy_provider_stack(provedor)
                    logger.info(f"[integration-token] Redeploy disparado para provedor id={provedor.id}")
                except Exception as exc:
                    logger.warning(f"[integration-token] Falha ao redeploy provedor id={provedor.id}: {exc}")
            threading.Thread(target=_redeploy, daemon=True).start()

        return Response({
            'token': token,
            'message': 'Token de integração rotacionado. Redeploy do tenant disparado para aplicar.',
        })

    @action(detail=True, methods=['post'], url_path='deploy')
    def deploy(self, request, pk=None):
        instance = self.get_object()
        if not instance.vps:
            return Response({"error": "Nenhuma VPS vinculada a este provedor."}, status=400)
        
        def run_deploy():
            try:
                from .services.portainer_service import PortainerService
                from .services.tenant_maintenance import begin_tenant_maintenance, set_tenant_maintenance_when_ready
                instance.status = 'deploying'
                instance.save()
                
                service = PortainerService(instance.vps)
                previous_boot = begin_tenant_maintenance(instance)
                success = False
                try:
                    success = service.deploy_provider_stack(instance)
                finally:
                    set_tenant_maintenance_when_ready(instance, previous_boot if success else None)
                
                if success:
                    instance.status = 'ativo'
                    try:
                        from .services.app_version import read_app_version
                        instance.current_version = read_app_version()
                        instance.last_update = timezone.now()
                    except Exception:
                        pass
                else:
                    instance.status = 'erro_deploy'
                instance.save()
            except Exception as e:
                logger.error(f"Erro no deploy thread: {e}")
                instance.status = 'erro_deploy'
                instance.save()

        thread = threading.Thread(target=run_deploy)
        thread.daemon = True
        thread.start()
        
        return Response({"message": "Deploy iniciado com sucesso!"})

    @action(detail=True, methods=['get'], url_path='users-status')
    def users_status(self, request, pk=None):
        """
        GET /api/provedores/<id>/users-status/
        Proxy seguro: busca status dos usuários diretamente no tenant via webhook Bearer.
        """
        import requests as _req

        provedor = self.get_object()
        subdomain = (provedor.subdomain or '').strip()
        if not subdomain:
            return Response({'error': 'Provedor sem subdomain configurado'}, status=400)
        if '.' not in subdomain:
            subdomain = f"{subdomain}.niohub.com.br"

        token = (provedor.integration_token or '').strip()
        if not token:
            return Response({'error': 'Provedor sem token de integração configurado'}, status=400)

        url = f"https://{subdomain}/api/webhooks/admin/users-status/?provedor_id={provedor.id}"
        try:
            resp = _req.get(url, headers={'Authorization': f'Bearer {token}'}, timeout=12)
            if resp.ok:
                return Response(resp.json())
            return Response({'error': 'Tenant respondeu erro', 'status_code': resp.status_code, 'body': resp.text[:300]}, status=502)
        except Exception as exc:
            return Response({'error': f'Falha ao contactar tenant: {exc}'}, status=502)

    @action(detail=False, methods=['get'], url_path='all-users-status')
    def all_users_status(self, request):
        """
        GET /api/provedores/all-users-status/
        Agrega em paralelo os usuários de TODOS os provedores ativos, chamando o
        webhook /api/webhooks/admin/users-status/ de cada tenant.
        Retorna: { users: [...], provedores_ok: [...], provedores_err: [...] }
        """
        import requests as _req
        from concurrent.futures import ThreadPoolExecutor, as_completed

        provedores = Provedor.objects.filter(is_active=True).only(
            'id', 'nome', 'subdomain', 'integration_token'
        )

        def _fetch_one(prov):
            subdomain = (prov.subdomain or '').strip()
            token = (prov.integration_token or '').strip()
            if not subdomain or not token:
                return prov.id, prov.nome, [], f'sem subdomain ou token'
            if '.' not in subdomain:
                subdomain = f"{subdomain}.niohub.com.br"
            url = f"https://{subdomain}/api/webhooks/admin/users-status/?provedor_id={prov.id}"
            try:
                resp = _req.get(url, headers={'Authorization': f'Bearer {token}'}, timeout=10)
                if resp.ok:
                    data = resp.json()
                    users = data.get('users') or []
                    # Sempre usar o nome real do provedor conforme cadastrado no superadmin.
                    # O tenant pode ter um placeholder genérico (ex: "Provedor 9") no banco local.
                    for u in users:
                        u['provedor_nome'] = prov.nome
                        u['provedor_id'] = prov.id
                    return prov.id, prov.nome, users, None
                return prov.id, prov.nome, [], f'HTTP {resp.status_code}'
            except Exception as exc:
                return prov.id, prov.nome, [], str(exc)

        all_users = []
        provedores_ok = []
        provedores_err = []

        provedor_list = list(provedores)
        with ThreadPoolExecutor(max_workers=min(len(provedor_list) or 1, 10)) as pool:
            futures = {pool.submit(_fetch_one, p): p for p in provedor_list}
            for future in as_completed(futures):
                pid, pnome, users, err = future.result()
                if err:
                    provedores_err.append({'id': pid, 'nome': pnome, 'error': err})
                else:
                    provedores_ok.append({'id': pid, 'nome': pnome, 'count': len(users)})
                    all_users.extend(users)

        return Response({
            'users': all_users,
            'total': len(all_users),
            'provedores_ok': provedores_ok,
            'provedores_err': provedores_err,
        })

class VpsServerViewSet(viewsets.ModelViewSet):
    queryset = VpsServer.objects.all()
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = VpsServerSerializer

class CanalViewSet(viewsets.ModelViewSet):
    queryset = Canal.objects.all().select_related('provedor')
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = CanalSerializer

    def get_queryset(self):
        qs = super().get_queryset()
        provedor_id = self.request.query_params.get('provedor_id')
        if provedor_id:
            try:
                qs = qs.filter(provedor_id=int(provedor_id))
            except ValueError:
                pass
        return qs

    @action(detail=False, methods=['post'], url_path='resync-dispatcher',
            permission_classes=[permissions.IsAuthenticated])
    def resync_dispatcher(self, request):
        """
        Puxa os canais WhatsApp Oficial de um provedor (tenant) e regista-os
        no superadmin para que o dispatcher saiba rotear webhooks.

        POST /api/canais/resync-dispatcher/
        Body: { "provedor_id": 2 }
        """
        import requests as req_lib

        provedor_id = request.data.get('provedor_id')
        if not provedor_id:
            return Response({'error': 'provedor_id é obrigatório'}, status=400)

        try:
            provedor = Provedor.objects.get(id=int(provedor_id))
        except (Provedor.DoesNotExist, ValueError):
            return Response({'error': 'Provedor não encontrado'}, status=404)

        # Construir URL do tenant
        subdomain = (provedor.subdomain or '').strip()
        if not subdomain:
            return Response({'error': 'Provedor sem subdomain configurado'}, status=400)

        if '.' not in subdomain:
            subdomain = f"{subdomain}.niohub.com.br"

        tenant_api = f"https://{subdomain}/api"

        # Token de integração por provedor (Bearer)
        provider_token = (getattr(provedor, 'integration_token', '') or '').strip()
        if not provider_token:
            return Response({'error': 'Provedor sem token de integração configurado'}, status=400)

        # Pedir ao tenant que faça push dos seus canais para o superadmin
        # O tenant expõe POST /api/canais/push-to-superadmin/ protegido por token (ou secret legado).
        synced = []
        errors = []
        try:
            payload = {}
            headers = {"Authorization": f"Bearer {provider_token}"}

            resp = req_lib.post(
                f"{tenant_api}/canais/push-to-superadmin/",
                json=payload,
                headers=headers,
                timeout=15,
            )
            if resp.status_code == 200:
                data = resp.json()
                synced = data.get('synced', [])
            else:
                errors.append(f"Tenant respondeu HTTP {resp.status_code}: {resp.text[:200]}")
                logger.warning(f"[resync_dispatcher] {errors[-1]}")
        except Exception as exc:
            errors.append(str(exc))
            logger.error(f"[resync_dispatcher] Erro ao contactar tenant {tenant_api}: {exc}")

        return Response({
            'synced': synced,
            'total': len(synced),
            'errors': errors,
            'tenant_api': tenant_api,
        })

class CompanyViewSet(viewsets.ModelViewSet):
    queryset = Company.objects.all()
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = CompanySerializer

def _push_user_to_tenant(user, provedor, password_plain=None):
    """
    Envia o utilizador para o banco do tenant (provedor) via webhook.
    Executado em thread daemon para não bloquear o request.
    """
    import threading
    import requests as _req

    def _do_push():
        try:
            subdomain = (getattr(provedor, 'subdomain', '') or '').strip()
            if not subdomain:
                logger.warning(f"[push-user] Provedor id={provedor.id} sem subdomain.")
                return
            if '.' not in subdomain:
                subdomain = f"{subdomain}.niohub.com.br"

            provider_token = (getattr(provedor, 'integration_token', '') or '').strip()
            if not provider_token:
                logger.warning("[push-user] Token de integração não configurado.")
                return

            payload = {
                "provedor_id": provedor.id,
                "username": user.username,
                "email": user.email or '',
                "first_name": getattr(user, 'first_name', '') or '',
                "last_name": getattr(user, 'last_name', '') or '',
                "user_type": getattr(user, 'user_type', 'admin') or 'admin',
            }
            if password_plain:
                payload["password"] = password_plain
            headers = {"Authorization": f"Bearer {provider_token}"}

            url = f"https://{subdomain}/api/webhooks/admin/upsert-user/"
            resp = _req.post(url, json=payload, headers=headers, timeout=10)
            if resp.ok:
                if provider_token:
                    provedor.integration_token_last_used_at = timezone.now()
                    provedor.save(update_fields=['integration_token_last_used_at'])
                logger.info(f"[push-user] Utilizador '{user.username}' enviado para {subdomain}: {resp.json()}")
            else:
                logger.warning(f"[push-user] Falha ao enviar para {subdomain}: HTTP {resp.status_code} {resp.text[:200]}")
        except Exception as exc:
            logger.error(f"[push-user] Erro: {exc}")

    threading.Thread(target=_do_push, daemon=True).start()


def _delete_user_from_tenant(provedor, *, user_id=None, username=None) -> dict:
    """
    Exclui utilizador no banco do tenant (síncrono).
    Retorna dict com ok, status_code, error, body.
    """
    import requests as _req

    subdomain = (getattr(provedor, 'subdomain', '') or '').strip()
    if not subdomain:
        return {'ok': False, 'error': 'Provedor sem subdomain configurado'}
    if '.' not in subdomain:
        subdomain = f"{subdomain}.niohub.com.br"

    provider_token = (getattr(provedor, 'integration_token', '') or '').strip()
    if not provider_token:
        return {'ok': False, 'error': 'Provedor sem token de integração'}

    payload = {'provedor_id': provedor.id}
    if user_id is not None:
        payload['user_id'] = user_id
    if username:
        payload['username'] = username

    url = f"https://{subdomain}/api/webhooks/admin/delete-user/"
    try:
        resp = _req.post(
            url,
            json=payload,
            headers={'Authorization': f'Bearer {provider_token}'},
            timeout=15,
        )
        if resp.ok:
            provedor.integration_token_last_used_at = timezone.now()
            provedor.save(update_fields=['integration_token_last_used_at'])
            try:
                body = resp.json()
            except Exception:
                body = {}
            logger.info(
                "[delete-user] Tenant %s excluiu user_id=%s username=%s",
                subdomain,
                user_id,
                username,
            )
            return {'ok': True, 'status_code': resp.status_code, 'body': body}
        return {
            'ok': False,
            'status_code': resp.status_code,
            'error': (resp.text or '')[:300],
        }
    except Exception as exc:
        logger.error("[delete-user] Erro ao contactar tenant %s: %s", subdomain, exc)
        return {'ok': False, 'error': str(exc)}


class UserViewSet(viewsets.ModelViewSet):
    queryset = User.objects.all().select_related('provedor')
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = UserSerializer

    def get_queryset(self):
        qs = super().get_queryset()
        provedor_id = self.request.query_params.get('provedor_id')
        if provedor_id:
            try:
                qs = qs.filter(provedor_id=int(provedor_id))
            except ValueError:
                pass
        from django.db.models import Q
        return qs.exclude(Q(username__istartswith='NIOHUB@') | Q(username__iexact='NIOHUB'))

    def perform_create(self, serializer):
        user = serializer.save()
        provedor = getattr(user, 'provedor', None)
        if provedor:
            password_plain = (self.request.data.get('password') or '').strip()
            _push_user_to_tenant(user, provedor, password_plain=password_plain or None)

    def perform_update(self, serializer):
        old_provedor_id = serializer.instance.provedor_id
        user = serializer.save()
        provedor = getattr(user, 'provedor', None)
        if provedor:
            password_plain = (self.request.data.get('password') or '').strip()
            _push_user_to_tenant(user, provedor, password_plain=password_plain or None)

    def destroy(self, request, *args, **kwargs):
        """
        Exclui usuário no tenant (banco do provedor) e, se existir, no superadmin.

        A lista de usuários vem dos tenants (IDs locais do provedor). O ID na URL
        é o ID no banco do provedor — NÃO o ID do superadmin. Por isso é obrigatório
        enviar provedor_id (query ou body) para encaminhar ao webhook do tenant.
        """
        pk = kwargs.get('pk')
        provedor_id = (
            request.query_params.get('provedor_id')
            or request.data.get('provedor_id')
        )
        username = (request.data.get('username') or request.query_params.get('username') or '').strip()

        try:
            tenant_user_id = int(pk)
        except (TypeError, ValueError):
            return Response({'error': 'ID de usuário inválido'}, status=400)

        # Caminho clássico: usuário só no superadmin (sem provedor_id)
        if provedor_id in (None, ''):
            local_user = User.objects.filter(pk=tenant_user_id).first()
            if not local_user:
                return Response(
                    {
                        'error': 'Usuário não encontrado. Para usuários de provedor, envie provedor_id.',
                    },
                    status=404,
                )
            if local_user.is_superuser or getattr(local_user, 'user_type', '') == 'superadmin':
                return Response({'error': 'Não é permitido excluir superadmin'}, status=403)
            if local_user.provedor_id:
                tenant_result = _delete_user_from_tenant(
                    local_user.provedor,
                    user_id=None,
                    username=local_user.username,
                )
                if not tenant_result.get('ok') and tenant_result.get('status_code') != 404:
                    return Response(
                        {
                            'error': tenant_result.get('error') or 'Falha ao excluir no banco do provedor',
                            'tenant_status': tenant_result.get('status_code'),
                        },
                        status=502,
                    )
            uname = local_user.username
            local_user.delete()
            return Response({'success': True, 'deleted': uname})

        try:
            provedor_id_int = int(provedor_id)
        except (TypeError, ValueError):
            return Response({'error': 'provedor_id inválido'}, status=400)

        provedor = Provedor.objects.filter(id=provedor_id_int).first()
        if not provedor:
            return Response({'error': 'Provedor não encontrado'}, status=404)

        tenant_result = _delete_user_from_tenant(
            provedor,
            user_id=tenant_user_id,
            username=username or None,
        )

        # Cópia no superadmin (mesmo username + provedor) — IDs são diferentes entre bancos
        if username:
            User.objects.filter(username=username, provedor_id=provedor.id).exclude(
                user_type='superadmin',
            ).delete()

        if not tenant_result.get('ok'):
            return Response(
                {
                    'error': tenant_result.get('error') or 'Falha ao excluir no banco do provedor',
                    'tenant_status': tenant_result.get('status_code'),
                },
                status=502 if tenant_result.get('status_code') != 404 else 404,
            )

        return Response({
            'success': True,
            'tenant': True,
            'provedor_id': provedor.id,
            'deleted_id': tenant_user_id,
            'username': username or (tenant_result.get('body') or {}).get('username'),
        })

class AuditLogViewSet(viewsets.ModelViewSet):
    queryset = AuditLog.objects.all()
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = AuditLogSerializer

class MensagemSistemaViewSet(viewsets.ModelViewSet):
    queryset = MensagemSistema.objects.all()
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = MensagemSistemaSerializer

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        mensagem = self._create_and_dispatch(serializer)
        out = self.get_serializer(mensagem).data
        entregas = getattr(self, '_last_entregas', None)
        if entregas is not None:
            out['entregas'] = entregas
        headers = self.get_success_headers(out)
        return Response(out, status=status.HTTP_201_CREATED, headers=headers)

    def _create_and_dispatch(self, serializer):
        from .system_message_dispatch import dispatch_system_message_to_tenants

        provedores_raw = self.request.data.get('provedores', [])
        visivel = self.request.data.get('visivel_para_agentes', True)
        clean_ids = []
        for pid in provedores_raw or []:
            try:
                clean_ids.append(int(pid))
            except (TypeError, ValueError):
                continue

        mensagem = serializer.save(
            provedores=clean_ids,
            visivel_para_agentes=bool(visivel),
            visualizacoes={},
            visualizacoes_count=0,
        )
        self._last_entregas = dispatch_system_message_to_tenants(mensagem, clean_ids)
        return mensagem


class ProviderHeartbeatView(APIView):
    """
    Tenant informa a versão que está rodando.
    POST /api/webhooks/provider/heartbeat/
    Header: Authorization: Bearer <integration_token>
    Body: { "version": "2.59.0" }
    """

    permission_classes = [permissions.AllowAny]
    authentication_classes = []

    def post(self, request):
        auth = (request.headers.get('Authorization') or '').strip()
        if not auth.lower().startswith('bearer '):
            return Response({'error': 'Unauthorized'}, status=401)
        token = auth[7:].strip()
        if not token:
            return Response({'error': 'Unauthorized'}, status=401)

        provedor = Provedor.objects.filter(integration_token=token).first()
        if not provedor:
            return Response({'error': 'Unauthorized'}, status=401)

        version = str(request.data.get('version') or '').strip()[:50]
        if not version:
            return Response({'error': 'version obrigatória'}, status=400)

        provedor.current_version = version
        provedor.integration_token_last_used_at = timezone.now()
        provedor.save(update_fields=['current_version', 'integration_token_last_used_at', 'updated_at'])

        health = request.data.get('health')
        if isinstance(health, dict):
            from .models import ProvedorHealth
            ProvedorHealth.objects.update_or_create(
                provedor=provedor,
                defaults={'reported_at': provedor.integration_token_last_used_at, 'data': health},
            )
        return Response({'ok': True, 'current_version': version, 'plano': provedor.plan_limits()})


class ProviderFxUsdBrlView(APIView):
    """
    Cotação USD-BRL (AwesomeAPI) para o painel do provedor (Meta Analytics).
    GET /api/webhooks/provider/fx/usd-brl/
    Header: Authorization: Bearer <integration_token>
    """

    permission_classes = [permissions.AllowAny]
    authentication_classes = []

    def get(self, request):
        auth = (request.headers.get('Authorization') or '').strip()
        if not auth.lower().startswith('bearer '):
            return Response({'error': 'Unauthorized'}, status=401)
        token = auth[7:].strip()
        if not token:
            return Response({'error': 'Unauthorized'}, status=401)

        provedor = Provedor.objects.filter(integration_token=token).first()
        if not provedor:
            return Response({'error': 'Unauthorized'}, status=401)

        provedor.integration_token_last_used_at = timezone.now()
        provedor.save(update_fields=['integration_token_last_used_at'])

        from .awesomeapi_fx import fetch_usd_brl, get_whatsapp_message_rates

        rates = get_whatsapp_message_rates()
        quote = fetch_usd_brl()
        if not quote:
            return Response(
                {
                    'success': False,
                    'error': 'Não foi possível obter cotação USD-BRL. Verifique a AwesomeAPI.',
                    'rates': rates,
                },
                status=502,
            )

        return Response({'success': True, 'quote': quote, 'rates': rates})


class SystemMessageReadReceiptView(APIView):
    """
    Tenant notifica o Superadmin quando um usuário leu o aviso.
    POST /api/webhooks/provider/system-message-read/
    Header: Authorization: Bearer <integration_token>
    Body: superadmin_message_id, user_id, user_name, visualized_at, provedor_nome?
    """

    permission_classes = [permissions.AllowAny]
    authentication_classes = []

    def post(self, request):
        auth = (request.headers.get('Authorization') or '').strip()
        low = auth.lower()
        if not low.startswith('bearer '):
            return Response({'error': 'Unauthorized'}, status=401)
        token = auth[7:].strip()
        if not token:
            return Response({'error': 'Unauthorized'}, status=401)

        provedor = Provedor.objects.filter(integration_token=token).first()
        if not provedor:
            return Response({'error': 'Unauthorized'}, status=401)

        provedor.integration_token_last_used_at = timezone.now()
        provedor.save(update_fields=['integration_token_last_used_at'])

        try:
            message_id = int(request.data.get('superadmin_message_id'))
        except (TypeError, ValueError):
            return Response({'error': 'superadmin_message_id inválido'}, status=400)

        mensagem = MensagemSistema.objects.filter(id=message_id).first()
        if not mensagem:
            return Response({'error': 'Mensagem não encontrada'}, status=404)

        destinos = []
        for pid in (mensagem.provedores or []):
            try:
                destinos.append(int(pid))
            except (TypeError, ValueError):
                continue
        if provedor.id not in destinos:
            return Response({'error': 'Provedor não é destinatário desta mensagem'}, status=403)

        user_id = request.data.get('user_id')
        try:
            user_id = int(user_id) if user_id is not None else None
        except (TypeError, ValueError):
            user_id = None

        user_name = (request.data.get('user_name') or '').strip() or 'Usuário'
        provedor_nome = (request.data.get('provedor_nome') or '').strip() or provedor.nome
        visualized_at = (request.data.get('visualized_at') or '').strip()
        if not visualized_at:
            visualized_at = timezone.now().isoformat()

        # Chave por provedor+usuário (permite vários leitores no mesmo provedor)
        key = f"{provedor.id}:{user_id}" if user_id is not None else str(provedor.id)
        visualizacoes = dict(mensagem.visualizacoes or {})
        if key not in visualizacoes:
            visualizacoes[key] = {
                'provedor_id': provedor.id,
                'provedor_nome': provedor_nome,
                'user_id': user_id,
                'user_name': user_name,
                'visualized_at': visualized_at,
            }
            mensagem.visualizacoes = visualizacoes
            mensagem.visualizacoes_count = len(visualizacoes)
            mensagem.save(update_fields=['visualizacoes', 'visualizacoes_count', 'updated_at'])

        return Response({
            'success': True,
            'message_id': mensagem.id,
            'provedor_id': provedor.id,
            'visualizacoes_count': mensagem.visualizacoes_count,
        })

class BillingTemplateViewSet(viewsets.ModelViewSet):
    queryset = BillingTemplate.objects.all()
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = BillingTemplateSerializer

class SystemConfigView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, pk=None):
        config = SystemConfig.objects.first()
        if not config:
            return Response({})
        data = config.payload or {}
        data['id'] = config.id
        return Response(data)

    def put(self, request, pk=None):
        config = SystemConfig.objects.first()
        if not config:
            config = SystemConfig.objects.create(payload={})
        
        data = request.data.copy()
        data.pop('id', None)
        config.payload = data
        config.save()
        
        response_data = config.payload
        response_data['id'] = config.id
        return Response(response_data)


@api_view(['GET'])
@permission_classes_decorator([permissions.AllowAny])
def operator_app_legal(request):
    """Política de Privacidade e Termos de Uso do app dos atendentes (público)."""
    config = SystemConfig.objects.first()
    payload = (config.payload if config and isinstance(config.payload, dict) else {}) or {}
    return Response({
        'privacy_policy': payload.get('operator_app_privacy_text') or '',
        'terms_of_use': payload.get('operator_app_terms_text') or '',
        'updated_at': config.updated_at.isoformat() if config else None,
    })


def _get_system_config_singleton_sa() -> SystemConfig:
    config = SystemConfig.objects.first()
    if not config:
        config = SystemConfig.objects.create(payload={})
    if not isinstance(config.payload, dict):
        config.payload = {}
    return config


def _meta_exchange_code_for_token(code: str) -> str:
    """
    Troca o code do Embedded Signup por access_token.

    IMPORTANTE: No Embedded Signup da Meta NÃO se usa redirect_uri na troca de token.
    Enviar redirect_uri causa HTTP 400 — só é necessário em OAuth clássico.
    Requer FACEBOOK_APP_SECRET no ambiente do superadmin.
    """
    import requests

    app_id = '713538217881661'
    app_secret = (getattr(settings, 'FACEBOOK_APP_SECRET', '') or '').strip()
    if not app_secret:
        raise RuntimeError('FACEBOOK_APP_SECRET não configurado no superadmin.')

    url = 'https://graph.facebook.com/v21.0/oauth/access_token'
    params = {
        'client_id': app_id,
        'client_secret': app_secret,
        'code': code,
        # redirect_uri OMITIDO intencionalmente: Embedded Signup não usa redirect_uri na troca
    }
    resp = requests.get(url, params=params, timeout=20)
    if not resp.ok:
        err_body = ''
        try:
            err_body = resp.json().get('error', {}).get('message', resp.text[:300])
        except Exception:
            err_body = resp.text[:300]
        logger.error("[billing-meta-finish] Erro na troca de token: HTTP %s | %s", resp.status_code, err_body)
        raise RuntimeError(f"Falha ao trocar code por token (HTTP {resp.status_code}): {err_body}")
    data = {}
    try:
        data = resp.json()
    except Exception:
        data = {}
    token = (data.get('access_token') or '').strip()
    if not token:
        raise RuntimeError('Meta não retornou access_token.')
    return token


def _meta_fetch_phone_number_from_waba(waba_id: str, access_token: str) -> dict:
    import requests

    url = f'https://graph.facebook.com/v21.0/{waba_id}/phone_numbers'
    params = {
        'fields': 'id,display_phone_number,verified_name',
        'access_token': access_token,
        'limit': 50,
    }
    resp = requests.get(url, params=params, timeout=20)
    if not resp.ok:
        raise RuntimeError(f"Falha ao buscar phone numbers do WABA (HTTP {resp.status_code}).")
    payload = resp.json() if resp.content else {}
    rows = payload.get('data') or []
    if not rows:
        raise RuntimeError('Nenhum phone number encontrado no WABA.')
    first = rows[0] or {}
    return {
        'phone_number_id': first.get('id') or '',
        'display_phone_number': first.get('display_phone_number') or '',
        'verified_name': first.get('verified_name') or '',
    }


class BillingWhatsAppEmbeddedSignupFinishView(APIView):
    """
    Finaliza o Embedded Signup do canal de cobrança no SUPERADMIN.
    Grava token e IDs no SystemConfig.payload.
    """
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        user = getattr(request, 'user', None)
        if not user or getattr(user, 'user_type', '') != 'superadmin':
            return Response({'success': False, 'error': 'Acesso negado'}, status=403)

        waba_id = (request.data.get('waba_id') or '').strip()
        code = (request.data.get('code') or '').strip()
        if not waba_id or not code:
            return Response({'success': False, 'error': 'waba_id e code são obrigatórios'}, status=400)

        # redirect_uri não é usado no Embedded Signup — omitido intencionalmente
        try:
            access_token = _meta_exchange_code_for_token(code)
            phone_data = _meta_fetch_phone_number_from_waba(waba_id, access_token)
        except Exception as exc:
            logger.warning("[billing-meta-finish] erro: %s", exc)
            return Response({'success': False, 'error': str(exc)}, status=400)

        config = _get_system_config_singleton_sa()
        payload = config.payload or {}
        payload['billing_whatsapp_token'] = access_token
        payload['billing_whatsapp_waba_id'] = waba_id
        payload['billing_whatsapp_phone_number_id'] = phone_data.get('phone_number_id')
        payload['billing_channel_enabled'] = True
        config.payload = payload
        config.save(update_fields=['payload', 'updated_at'])

        return Response({
            'success': True,
            'billing': {
                'waba_id': waba_id,
                'phone_number_id': phone_data.get('phone_number_id', ''),
                'display_phone_number': phone_data.get('display_phone_number', ''),
                'verified_name': phone_data.get('verified_name', ''),
            }
        })

class BillingWhatsAppTestView(APIView):
    """
    Endpoint para disparar o ciclo de cobrança manualmente (botão de teste).
    """
    def post(self, request):
        user = getattr(request, 'user', None)
        if not user or getattr(user, 'user_type', '') != 'superadmin':
            return Response({'success': False, 'error': 'Acesso negado'}, status=403)

        try:
            res = run_billing_send_cycle(force=True)
            return Response(res)
        except Exception as exc:
            import traceback
            traceback.print_exc()
            return Response({'success': False, 'error': str(exc)}, status=500)
class BillingWhatsAppTemplatesView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        config = SystemConfig.objects.first()
        payload = (config.payload or {}) if config else {}
        
        token = payload.get('billing_whatsapp_token')
        waba_id = payload.get('billing_whatsapp_waba_id')
        
        if not token or not waba_id:
            return Response({'success': False, 'error': 'WhatsApp não configurado.'}, status=400)
            
        import requests
        url = f"https://graph.facebook.com/v21.0/{waba_id}/message_templates"
        headers = {'Authorization': f'Bearer {token}'}
        
        try:
            resp = requests.get(url, headers=headers, params={'limit': 100}, timeout=15)
            if resp.ok:
                data = resp.json()
                return Response({'success': True, 'data': data.get('data', [])})
            return Response({'success': False, 'error': resp.text}, status=resp.status_code)
        except Exception as e:
            return Response({'success': False, 'error': str(e)}, status=500)
