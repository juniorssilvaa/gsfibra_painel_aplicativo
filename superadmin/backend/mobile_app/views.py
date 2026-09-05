from rest_framework import serializers, viewsets, permissions, status
from rest_framework.authentication import TokenAuthentication
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.response import Response
from rest_framework.views import APIView

from super_core.models import Provedor, User
from .models import (
    MobileActivityLog,
    MobileAppProfile,
    MobileAppUser,
    MobileDevice,
    MobileSystemSettings,
    MobileInAppWarning,
    MobilePlan,
    MobileAppConfig,
    MobileNotificationLog,
    MobileNotificationTemplate,
    MobileScheduledNotification,
)
from .permissions import IsSuperadmin, IsMobilePanelUser, is_superadmin_user, provedor_id_for_user
from .services import ensure_mobile_app_for_provedor, count_outdated_devices, mask_ip


class MobileAppProfileSerializer(serializers.ModelSerializer):
    provedor_id = serializers.IntegerField(source='provedor.id', read_only=True)
    provedor_nome = serializers.CharField(source='provedor.nome', read_only=True)
    app_users_count = serializers.SerializerMethodField()
    active_token = serializers.SerializerMethodField()
    genieacs_password = serializers.CharField(write_only=True, required=False, allow_blank=True)
    genieacs_token = serializers.CharField(required=False, allow_blank=True)
    has_genieacs_token = serializers.SerializerMethodField()
    has_genieacs_password = serializers.SerializerMethodField()

    class Meta:
        model = MobileAppProfile
        fields = (
            'id', 'provedor_id', 'provedor_nome', 'logo', 'primary_color',
            'glass_intensity', 'glass_blur', 'ambient_shadow',
            'cnpj', 'number', 'is_active', 'created_at', 'updated_at',
            'sgp_url', 'sgp_app_name', 'webhook_url', 'latest_app_version',
            'genieacs_url', 'genieacs_user', 'genieacs_password', 'genieacs_token',
            'has_genieacs_token', 'has_genieacs_password',
            'app_users_count', 'active_token',
        )
        read_only_fields = ('created_at', 'updated_at', 'active_token', 'is_active')

    def get_app_users_count(self, obj):
        return MobileAppUser.objects.filter(provedor_id=obj.provedor_id).count()

    def get_active_token(self, obj):
        t = obj.get_active_token()
        if not t:
            return None
        return f'{t[:8]}…{t[-4:]}'

    def get_has_genieacs_token(self, obj):
        return bool(obj.genieacs_token)

    def get_has_genieacs_password(self, obj):
        return bool(obj.genieacs_password)

    def update(self, instance, validated_data):
        # Só superadmin pode ligar/desligar is_active via serializer se vier no payload
        request = self.context.get('request')
        if request and not is_superadmin_user(request.user):
            validated_data.pop('is_active', None)
        for secret in ('genieacs_password', 'genieacs_token'):
            if secret in validated_data and not validated_data[secret]:
                validated_data.pop(secret)
        return super().update(instance, validated_data)


class MobileAppConfigSerializer(serializers.ModelSerializer):
    class Meta:
        model = MobileAppConfig
        fields = (
            'id', 'active_shortcuts', 'active_tools', 'social_links',
            'update_warning_active',
            'tool_faturas', 'tool_connected_devices', 'tool_speed_test',
            'tool_auto_unlock', 'tool_wifi', 'tool_cameras', 'shortcut_wifi',
            'speed_test_provider',
        )


class MobileDeviceSerializer(serializers.ModelSerializer):
    class Meta:
        model = MobileDevice
        fields = (
            'id', 'platform', 'model', 'os_version', 'app_version',
            'active', 'created_at', 'last_active',
            'push_confirmed', 'push_confirmed_at',
        )


class MobileAppUserSerializer(serializers.ModelSerializer):
    provedor_nome = serializers.CharField(source='provedor.nome', read_only=True)
    devices_count = serializers.SerializerMethodField()
    is_online = serializers.BooleanField(read_only=True)
    devices = MobileDeviceSerializer(many=True, read_only=True)

    class Meta:
        model = MobileAppUser
        fields = (
            'id', 'provedor', 'provedor_nome', 'name', 'email', 'cpf',
            'customer_id', 'pppoe_login', 'active', 'created_at',
            'last_active_at', 'is_online', 'devices_count', 'tags', 'devices',
        )
        read_only_fields = ('provedor', 'created_at')

    def get_devices_count(self, obj):
        # Usa prefetch se disponível
        devices = getattr(obj, '_prefetched_objects_cache', {}).get('devices')
        if devices is not None:
            return sum(1 for d in devices if d.active)
        return obj.devices.filter(active=True).count()


class MobileInAppWarningSerializer(serializers.ModelSerializer):
    class Meta:
        model = MobileInAppWarning
        fields = (
            'id', 'provedor', 'title', 'message', 'type', 'whatsapp_btn',
            'sticky', 'show_home', 'target_cpfs', 'target_contracts',
            'created_at', 'active',
        )
        read_only_fields = ('provedor', 'created_at')


class MobilePlanSerializer(serializers.ModelSerializer):
    class Meta:
        model = MobilePlan
        fields = (
            'id', 'provedor', 'name', 'type', 'download_speed', 'upload_speed',
            'price', 'description', 'is_active', 'created_at',
        )
        read_only_fields = ('provedor', 'created_at')


class MobileAppProfileViewSet(viewsets.ModelViewSet):
    """CRUD do perfil app — Superadmin vê todos; admin do provedor só o próprio."""
    queryset = MobileAppProfile.objects.select_related('provedor').all().order_by('-created_at')
    serializer_class = MobileAppProfileSerializer
    permission_classes = [IsMobilePanelUser]

    def get_parsers(self):
        from rest_framework.parsers import JSONParser, MultiPartParser, FormParser
        return [JSONParser(), MultiPartParser(), FormParser()]

    def get_queryset(self):
        qs = super().get_queryset()
        if is_superadmin_user(self.request.user):
            return qs
        pid = getattr(self.request.user, 'provedor_id', None)
        return qs.filter(provedor_id=pid) if pid else qs.none()

    def get_permissions(self):
        # provision / toggle / cleanup / dashboard-stats global = só superadmin
        if self.action in ('provision', 'toggle_status', 'cleanup', 'dashboard_stats', 'destroy', 'create'):
            return [IsSuperadmin()]
        return super().get_permissions()

    @action(detail=False, methods=['get'], url_path='dashboard-stats')
    def dashboard_stats(self, request):
        profiles = MobileAppProfile.objects.all()
        total = profiles.count()
        active = profiles.filter(is_active=True).count()
        return Response({
            'total_providers': total,
            'active_providers': active,
            'inactive_providers': total - active,
            'total_app_users': MobileAppUser.objects.count(),
            'total_admins': User.objects.filter(
                provedor__isnull=False,
                user_type='admin',
            ).count(),
            'total_devices': MobileDevice.objects.filter(active=True).count(),
        })

    @action(detail=False, methods=['get'], url_path='my-dashboard')
    def my_dashboard(self, request):
        """Stats completas do provedor (cards do dashboard do app)."""
        from datetime import timedelta
        from django.db.models import Avg, Count, Sum
        from django.utils import timezone

        pid = provedor_id_for_user(request.user, request)
        if not pid and is_superadmin_user(request.user):
            return Response({'error': 'provedor_id é obrigatório'}, status=400)
        if not pid:
            return Response({'error': 'Usuário sem provedor'}, status=403)

        users_qs = MobileAppUser.objects.filter(provedor_id=pid)
        total_users = users_qs.count()
        active_users = users_qs.filter(active=True).count()
        inactive_users = total_users - active_users
        active_percentage = int((active_users / total_users * 100)) if total_users else 0

        now = timezone.now()
        today = timezone.localdate()
        d7 = today - timedelta(days=6)
        d7_prev_start = today - timedelta(days=13)
        d7_prev_end = today - timedelta(days=7)
        d30 = today - timedelta(days=29)

        online_cutoff = now - timedelta(minutes=5)
        online_qs = users_qs.filter(last_active_at__gte=online_cutoff).order_by('-last_active_at')
        online_users = online_qs.count()
        online_now = []
        for u in online_qs[:12]:
            login = ''
            if u.pppoe_login:
                login = str(u.pppoe_login).split(',')[0].strip()
            online_now.append({
                'id': u.id,
                'login': login or u.name or u.cpf or '—',
                'name': u.name or '',
                'pppoe_login': u.pppoe_login or '',
                'last_active_at': u.last_active_at,
            })
        active_7d = users_qs.filter(last_active_at__gte=now - timedelta(days=7)).count()
        active_30d = users_qs.filter(last_active_at__gte=now - timedelta(days=30)).count()
        retention_7d = int((active_7d / total_users * 100)) if total_users else 0

        new_users_7d = users_qs.filter(created_at__date__gte=d7).count()
        new_users_30d = users_qs.filter(created_at__date__gte=d30).count()
        new_users_prev_7d = users_qs.filter(
            created_at__date__gte=d7_prev_start,
            created_at__date__lte=d7_prev_end,
        ).count()

        devices_qs = MobileDevice.objects.filter(provedor_id=pid)
        total_devices = devices_qs.count()
        active_devices = devices_qs.filter(active=True).count()
        android_devices = devices_qs.filter(platform='android').count()
        ios_devices = devices_qs.filter(platform='ios').count()
        devices_with_token = devices_qs.exclude(push_token__isnull=True).exclude(push_token='').count()
        push_confirmed = devices_qs.filter(push_confirmed=True).count()
        push_coverage = int((devices_with_token / total_devices * 100)) if total_devices else 0
        android_percentage = int((android_devices / total_devices * 100)) if total_devices else 0
        ios_percentage = int((ios_devices / total_devices * 100)) if total_devices else 0

        # "Downloads" ≈ novos dispositivos registrados (proxy de instalação do app)
        installs_7d = devices_qs.filter(created_at__date__gte=d7).count()
        installs_30d = devices_qs.filter(created_at__date__gte=d30).count()
        installs_prev_7d = devices_qs.filter(
            created_at__date__gte=d7_prev_start,
            created_at__date__lte=d7_prev_end,
        ).count()
        installs_growth = None
        if installs_prev_7d > 0:
            installs_growth = round(((installs_7d - installs_prev_7d) / installs_prev_7d) * 100, 1)
        elif installs_7d > 0:
            installs_growth = 100.0
        else:
            installs_growth = 0.0

        multi_device_users = (
            devices_qs.values('user_id')
            .annotate(c=Count('id'))
            .filter(c__gte=2)
            .count()
        )

        top_models = list(
            devices_qs.values('model')
            .annotate(count=Count('id'))
            .order_by('-count')[:5]
        )

        warnings_active = MobileInAppWarning.objects.filter(provedor_id=pid, active=True).count()
        plans_active = MobilePlan.objects.filter(provedor_id=pid, is_active=True).count()

        from .models import MobileNetworkTelemetry, MobileAIChatSession
        telemetry_qs = MobileNetworkTelemetry.objects.filter(
            provedor_id=pid,
            created_at__gte=now - timedelta(days=7),
        )
        telemetry_count = telemetry_qs.count()
        tel_agg = telemetry_qs.aggregate(
            avg_latency=Avg('latency'),
            avg_wifi_dbm=Avg('wifi_dbm'),
            avg_link_speed=Avg('link_speed'),
            avg_packet_loss=Avg('packet_loss'),
        )
        ai_sessions_7d = MobileAIChatSession.objects.filter(
            provedor_id=pid,
            created_at__gte=now - timedelta(days=7),
        ).count()

        try:
            profile_for_stats = MobileAppProfile.objects.get(provedor_id=pid)
            latest_app_version = profile_for_stats.latest_app_version
        except MobileAppProfile.DoesNotExist:
            profile_for_stats = None
            latest_app_version = None
        outdated_apps = count_outdated_devices(pid, latest_app_version)
        active_devices_for_outdated = devices_qs.filter(active=True).count()
        outdated_percentage = (
            int((outdated_apps / active_devices_for_outdated * 100))
            if active_devices_for_outdated
            else 0
        )

        # Logs recentes: só últimas 4h; limpa os mais antigos deste provedor
        activity_cutoff = now - timedelta(hours=4)
        MobileActivityLog.objects.filter(provedor_id=pid, created_at__lt=activity_cutoff).delete()
        activity_logs = list(
            MobileActivityLog.objects.filter(
                provedor_id=pid,
                event__in=['login', 'register'],
                created_at__gte=activity_cutoff,
            )
            .select_related('user')
            .order_by('-created_at')[:12]
        )
        recent_activity_logs = [
            {
                'id': log.id,
                'date': timezone.localtime(log.created_at).strftime('%d/%m %H:%M'),
                'user': (log.user.name if log.user and log.user.name else None) or '—',
                'event': log.display_label(),
                'ip': mask_ip(log.ip_address),
                'created_at': log.created_at,
            }
            for log in activity_logs
        ]

        logs_qs = MobileNotificationLog.objects.filter(provedor_id=pid)
        total_notifications = logs_qs.count()
        agg = logs_qs.aggregate(
            total_success=Sum('success_count'),
            total_failure=Sum('failure_count'),
        )
        success_count = agg['total_success'] or 0
        failure_count = agg['total_failure'] or 0
        total_sent = success_count + failure_count
        delivery_rate = int((success_count / total_sent * 100)) if total_sent else 0

        last = logs_qs.order_by('-created_at').first()
        recent_notifications = [
            {
                'id': n.id,
                'title': n.title,
                'body': n.body,
                'source': n.source,
                'recipients_count': n.recipients_count,
                'success_count': n.success_count,
                'failure_count': n.failure_count,
                'created_at': n.created_at,
            }
            for n in logs_qs.order_by('-created_at')[:5]
        ]

        dates = [today - timedelta(days=i) for i in range(6, -1, -1)]
        chart_labels_7d = [d.strftime('%d/%m') for d in dates]
        chart_data_sent = [0] * 7
        chart_data_failed = [0] * 7
        chart_data_installs = [0] * 7
        chart_data_new_users = [0] * 7

        recent_logs = (
            logs_qs.filter(created_at__date__gte=dates[0])
            .values('created_at__date')
            .annotate(
                daily_success=Sum('success_count'),
                daily_failure=Sum('failure_count'),
            )
        )
        logs_map = {row['created_at__date']: row for row in recent_logs}

        installs_by_day = {
            row['created_at__date']: row['c']
            for row in devices_qs.filter(created_at__date__gte=dates[0])
            .values('created_at__date')
            .annotate(c=Count('id'))
        }
        users_by_day = {
            row['created_at__date']: row['c']
            for row in users_qs.filter(created_at__date__gte=dates[0])
            .values('created_at__date')
            .annotate(c=Count('id'))
        }

        for i, date_obj in enumerate(dates):
            if date_obj in logs_map:
                chart_data_sent[i] = logs_map[date_obj]['daily_success'] or 0
                chart_data_failed[i] = logs_map[date_obj]['daily_failure'] or 0
            chart_data_installs[i] = installs_by_day.get(date_obj, 0)
            chart_data_new_users[i] = users_by_day.get(date_obj, 0)

        if profile_for_stats is not None:
            profile_data = MobileAppProfileSerializer(
                profile_for_stats, context={'request': request},
            ).data
        else:
            try:
                profile = MobileAppProfile.objects.get(provedor_id=pid)
                profile_data = MobileAppProfileSerializer(profile, context={'request': request}).data
            except MobileAppProfile.DoesNotExist:
                profile_data = None

        def _round(v, n=1):
            return round(float(v), n) if v is not None else None

        return Response({
            'provedor_id': pid,
            'profile': profile_data,
            'total_users': total_users,
            'active_users': active_users,
            'inactive_users': inactive_users,
            'active_percentage': active_percentage,
            'online_users': online_users,
            'online_now': online_now,
            'active_7d': active_7d,
            'active_30d': active_30d,
            'retention_7d': retention_7d,
            'new_users_7d': new_users_7d,
            'new_users_30d': new_users_30d,
            'new_users_prev_7d': new_users_prev_7d,
            'installs_7d': installs_7d,
            'installs_30d': installs_30d,
            'installs_prev_7d': installs_prev_7d,
            'installs_growth': installs_growth,
            'multi_device_users': multi_device_users,
            'total_devices': total_devices,
            'active_devices': active_devices,
            'android_devices': android_devices,
            'ios_devices': ios_devices,
            'android_percentage': android_percentage,
            'ios_percentage': ios_percentage,
            'devices_with_token': devices_with_token,
            'push_confirmed': push_confirmed,
            'push_coverage': push_coverage,
            'top_models': top_models,
            'warnings_active': warnings_active,
            'plans_active': plans_active,
            'ai_sessions_7d': ai_sessions_7d,
            'outdated_apps': outdated_apps,
            'outdated_percentage': outdated_percentage,
            'latest_app_version': latest_app_version,
            'recent_activity_logs': recent_activity_logs,
            'telemetry_7d': {
                'samples': telemetry_count,
                'avg_latency_ms': _round(tel_agg.get('avg_latency')),
                'avg_wifi_dbm': _round(tel_agg.get('avg_wifi_dbm'), 0),
                'avg_link_speed_mbps': _round(tel_agg.get('avg_link_speed'), 0),
                'avg_packet_loss': _round(tel_agg.get('avg_packet_loss')),
            },
            'total_notifications': total_notifications,
            'success_count': success_count,
            'failure_count': failure_count,
            'delivery_rate': delivery_rate,
            'chart_labels_7d': chart_labels_7d,
            'chart_data_sent': chart_data_sent,
            'chart_data_failed': chart_data_failed,
            'chart_data_installs': chart_data_installs,
            'chart_data_new_users': chart_data_new_users,
            'recent_notifications': recent_notifications,
            'last_notification': {
                'created_at': last.created_at,
                'source': last.source,
                'title': last.title,
            } if last else None,
        })

    @action(detail=False, methods=['get', 'patch'], url_path='mine')
    def mine(self, request):
        """Perfil do provedor do admin logado."""
        pid = getattr(request.user, 'provedor_id', None)
        if is_superadmin_user(request.user):
            pid = provedor_id_for_user(request.user, request) or pid
        if not pid:
            return Response({'error': 'Usuário sem provedor'}, status=403)
        try:
            profile = MobileAppProfile.objects.select_related('provedor').get(provedor_id=pid)
        except MobileAppProfile.DoesNotExist:
            return Response({
                'error': 'App mobile não habilitado para este provedor. Contate o suporte Niohub.',
            }, status=404)

        if request.method == 'GET':
            return Response(MobileAppProfileSerializer(profile, context={'request': request}).data)

        ser = MobileAppProfileSerializer(
            profile, data=request.data, partial=True, context={'request': request},
        )
        ser.is_valid(raise_exception=True)
        ser.save()
        return Response(ser.data)

    @action(detail=True, methods=['get', 'put', 'patch'], url_path='app-config')
    def app_config(self, request, pk=None):
        profile = self.get_object()
        return self._save_or_get_app_config(profile, request)

    @action(detail=False, methods=['get', 'put', 'patch'], url_path='mine-app-config')
    def mine_app_config(self, request):
        pid = provedor_id_for_user(request.user)
        if not pid:
            return Response({'error': 'Usuário sem provedor vinculado.'}, status=403)
        try:
            profile = MobileAppProfile.objects.get(provedor_id=pid)
        except MobileAppProfile.DoesNotExist:
            return Response({
                'error': 'App mobile não habilitado para este provedor. Contate o suporte Niohub.',
            }, status=404)
        return self._save_or_get_app_config(profile, request)

    def _save_or_get_app_config(self, profile, request):
        config, _ = MobileAppConfig.objects.get_or_create(profile=profile)
        if request.method == 'GET':
            return Response(MobileAppConfigSerializer(config).data)
        ser = MobileAppConfigSerializer(config, data=request.data, partial=True)
        ser.is_valid(raise_exception=True)
        ser.save()
        config.refresh_from_db()
        config.active_tools = [
            key
            for key, on in (
                ('speed_test', config.tool_speed_test),
                ('auto_unlock', config.tool_auto_unlock),
                ('faturas', config.tool_faturas),
                ('connected_devices', config.tool_connected_devices),
                ('wifi', config.tool_wifi),
                ('cameras', config.tool_cameras),
            )
            if on
        ]
        config.save(update_fields=['active_tools'])
        return Response(MobileAppConfigSerializer(config).data)

    @action(detail=False, methods=['post'], url_path='provision')
    def provision(self, request):
        provedor_id = request.data.get('provedor_id')
        if not provedor_id:
            return Response({'error': 'provedor_id é obrigatório'}, status=400)
        try:
            provedor = Provedor.objects.get(id=int(provedor_id))
        except (Provedor.DoesNotExist, TypeError, ValueError):
            return Response({'error': 'Provedor não encontrado'}, status=404)

        is_active = request.data.get('is_active', True)
        if isinstance(is_active, str):
            is_active = is_active.lower() in ('1', 'true', 'yes', 'on')

        profile, token, created = ensure_mobile_app_for_provedor(
            provedor,
            is_active=bool(is_active),
            create_token=True,
        )

        username = (request.data.get('username') or '').strip()
        password = (request.data.get('password') or '').strip()
        admin_user = None
        if username and password:
            if User.objects.filter(username=username).exists():
                return Response({'error': 'Nome de usuário já existe'}, status=400)
            admin_user = User.objects.create_user(
                username=username,
                password=password,
                user_type='admin',
                is_staff=True,
            )
            admin_user.provedor = provedor
            admin_user.save(update_fields=['provedor'])

        cnpj = (request.data.get('cnpj') or '').strip()
        number = (request.data.get('number') or '').strip()
        update_fields = []
        if cnpj:
            profile.cnpj = cnpj
            update_fields.append('cnpj')
        if number:
            profile.number = number
            update_fields.append('number')
        if update_fields:
            profile.save(update_fields=update_fields + ['updated_at'])

        return Response({
            'success': True,
            'created': created,
            'profile': MobileAppProfileSerializer(profile, context={'request': request}).data,
            'token': token.token if token else None,
            'admin_username': admin_user.username if admin_user else None,
        }, status=status.HTTP_201_CREATED if created else status.HTTP_200_OK)

    @action(detail=True, methods=['post'], url_path='toggle-status')
    def toggle_status(self, request, pk=None):
        profile = self.get_object()
        profile.is_active = not profile.is_active
        profile.save(update_fields=['is_active', 'updated_at'])
        return Response({
            'success': True,
            'is_active': profile.is_active,
            'provedor_id': profile.provedor_id,
        })

    @action(detail=True, methods=['post'], url_path='rotate-token')
    def rotate_token(self, request, pk=None):
        profile = self.get_object()
        tok = profile.generate_new_token()
        return Response({'success': True, 'token': tok.token})

    @action(detail=True, methods=['post'], url_path='cleanup')
    def cleanup(self, request, pk=None):
        profile = self.get_object()
        pid = profile.provedor_id
        deleted = {
            'users': MobileAppUser.objects.filter(provedor_id=pid).delete()[0],
            'devices': MobileDevice.objects.filter(provedor_id=pid).delete()[0],
            'warnings': MobileInAppWarning.objects.filter(provedor_id=pid).delete()[0],
        }
        return Response({'success': True, 'deleted': deleted})


class MobileAppUserViewSet(viewsets.ModelViewSet):
    queryset = (
        MobileAppUser.objects
        .select_related('provedor')
        .prefetch_related('devices')
        .all()
        .order_by('-created_at')
    )
    serializer_class = MobileAppUserSerializer
    permission_classes = [IsMobilePanelUser]
    filterset_fields = ['provedor']
    http_method_names = ['get', 'patch', 'put', 'delete', 'head', 'options']

    def get_queryset(self):
        qs = super().get_queryset()
        if is_superadmin_user(self.request.user):
            provedor_id = self.request.query_params.get('provedor_id')
            if provedor_id:
                qs = qs.filter(provedor_id=provedor_id)
        else:
            pid = getattr(self.request.user, 'provedor_id', None)
            qs = qs.filter(provedor_id=pid) if pid else qs.none()

        q = (self.request.query_params.get('q') or '').strip()
        if q:
            from django.db.models import Q
            qs = qs.filter(
                Q(name__icontains=q)
                | Q(cpf__icontains=q)
                | Q(email__icontains=q)
                | Q(customer_id__icontains=q)
                | Q(pppoe_login__icontains=q)
            )
        return qs

    def perform_update(self, serializer):
        instance = serializer.save()
        if instance.active is False:
            instance.devices.update(active=False)


class MobileWarningViewSet(viewsets.ModelViewSet):
    queryset = MobileInAppWarning.objects.all().order_by('-created_at')
    serializer_class = MobileInAppWarningSerializer
    permission_classes = [IsMobilePanelUser]

    def get_queryset(self):
        qs = super().get_queryset()
        if is_superadmin_user(self.request.user):
            pid = self.request.query_params.get('provedor_id')
            return qs.filter(provedor_id=pid) if pid else qs
        pid = getattr(self.request.user, 'provedor_id', None)
        return qs.filter(provedor_id=pid) if pid else qs.none()

    def perform_create(self, serializer):
        if is_superadmin_user(self.request.user):
            pid = (
                self.request.data.get('provedor_id')
                or self.request.data.get('provedor')
            )
            if not pid:
                raise serializers.ValidationError({'provedor_id': 'Obrigatório'})
            serializer.save(provedor_id=int(pid))
        else:
            serializer.save(provedor_id=self.request.user.provedor_id)


class MobilePlanViewSet(viewsets.ModelViewSet):
    queryset = MobilePlan.objects.all().order_by('price')
    serializer_class = MobilePlanSerializer
    permission_classes = [IsMobilePanelUser]

    def get_queryset(self):
        qs = super().get_queryset()
        if is_superadmin_user(self.request.user):
            pid = self.request.query_params.get('provedor_id')
            return qs.filter(provedor_id=pid) if pid else qs
        pid = getattr(self.request.user, 'provedor_id', None)
        return qs.filter(provedor_id=pid) if pid else qs.none()

    def perform_create(self, serializer):
        if is_superadmin_user(self.request.user):
            pid = self.request.data.get('provedor_id') or self.request.data.get('provedor')
            if not pid:
                raise serializers.ValidationError({'provedor_id': 'Obrigatório'})
            serializer.save(provedor_id=int(pid))
        else:
            serializer.save(provedor_id=self.request.user.provedor_id)


class MobileNotificationTemplateSerializer(serializers.ModelSerializer):
    class Meta:
        model = MobileNotificationTemplate
        fields = (
            'id', 'provedor', 'name', 'title', 'body', 'type',
            'image_url', 'created_at', 'updated_at',
        )
        read_only_fields = ('provedor', 'created_at', 'updated_at')


class MobileScheduledNotificationSerializer(serializers.ModelSerializer):
    status_display = serializers.CharField(source='get_status_display', read_only=True)

    class Meta:
        model = MobileScheduledNotification
        fields = (
            'id', 'provedor', 'title', 'body', 'type', 'image_url',
            'scheduled_at', 'status', 'status_display', 'segment_type',
            'segment_tags', 'segment_search', 'sent_count', 'failed_count',
            'created_at', 'sent_at',
        )
        read_only_fields = (
            'provedor', 'status', 'sent_count', 'failed_count',
            'created_at', 'sent_at',
        )


class MobileNotificationTemplateViewSet(viewsets.ModelViewSet):
    queryset = MobileNotificationTemplate.objects.all().order_by('-updated_at')
    serializer_class = MobileNotificationTemplateSerializer
    permission_classes = [IsMobilePanelUser]

    def get_queryset(self):
        qs = super().get_queryset()
        if is_superadmin_user(self.request.user):
            pid = self.request.query_params.get('provedor_id')
            return qs.filter(provedor_id=pid) if pid else qs
        pid = getattr(self.request.user, 'provedor_id', None)
        return qs.filter(provedor_id=pid) if pid else qs.none()

    def perform_create(self, serializer):
        pid = getattr(self.request.user, 'provedor_id', None)
        if is_superadmin_user(self.request.user):
            pid = self.request.data.get('provedor_id') or self.request.data.get('provedor') or pid
        if not pid:
            raise serializers.ValidationError({'provedor_id': 'Obrigatório'})
        serializer.save(provedor_id=int(pid), created_by=self.request.user)


class MobileScheduledNotificationViewSet(viewsets.ModelViewSet):
    queryset = MobileScheduledNotification.objects.all().order_by('scheduled_at')
    serializer_class = MobileScheduledNotificationSerializer
    permission_classes = [IsMobilePanelUser]
    # Só Token — evita 403 CSRF do SessionAuthentication em POST/DELETE no painel
    authentication_classes = [TokenAuthentication]
    http_method_names = ['get', 'post', 'patch', 'delete', 'head', 'options']

    def get_queryset(self):
        qs = super().get_queryset()
        if is_superadmin_user(self.request.user):
            pid = self.request.query_params.get('provedor_id')
            return qs.filter(provedor_id=pid) if pid else qs
        pid = getattr(self.request.user, 'provedor_id', None)
        return qs.filter(provedor_id=pid) if pid else qs.none()

    def destroy(self, request, *args, **kwargs):
        """Exclui um agendamento pendente (ou já cancelado)."""
        obj = self.get_object()
        if obj.status not in ('pending', 'cancelled'):
            return Response(
                {'error': 'Só é possível excluir agendamentos pendentes ou cancelados.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        obj.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=True, methods=['post', 'delete'], url_path='cancel')
    def cancel(self, request, pk=None):
        obj = self.get_object()
        if obj.status != 'pending':
            if obj.status == 'cancelled':
                obj.delete()
                return Response({'ok': True, 'message': 'Agendamento removido.'})
            return Response(
                {'error': 'Só é possível cancelar agendamentos pendentes.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        obj.delete()
        return Response({'ok': True, 'message': 'Agendamento cancelado.'})


class MobileNotificationLogSerializer(serializers.ModelSerializer):
    status = serializers.SerializerMethodField()
    status_label = serializers.SerializerMethodField()

    class Meta:
        model = MobileNotificationLog
        fields = (
            'id', 'source', 'title', 'body', 'recipients_count',
            'success_count', 'failure_count', 'notif_type', 'link',
            'image_url', 'segment_type', 'recipients', 'metadata',
            'created_at', 'status', 'status_label',
        )

    def get_status(self, obj):
        if obj.success_count > 0 and obj.failure_count == 0:
            return 'enviado'
        if obj.success_count > 0 and obj.failure_count > 0:
            return 'parcial'
        if obj.failure_count > 0:
            return 'falha'
        return 'enviado' if obj.recipients_count else 'vazio'

    def get_status_label(self, obj):
        return {
            'enviado': 'Enviado',
            'parcial': 'Parcial',
            'falha': 'Falha',
            'vazio': 'Sem destinatários',
        }.get(self.get_status(obj), 'Enviado')


class MobileNotificationLogViewSet(viewsets.ReadOnlyModelViewSet):
    """Lista de notificações enviadas (histórico) para o painel do provedor."""
    queryset = MobileNotificationLog.objects.all().order_by('-created_at')
    serializer_class = MobileNotificationLogSerializer
    permission_classes = [IsMobilePanelUser]

    def get_queryset(self):
        qs = super().get_queryset()
        if is_superadmin_user(self.request.user):
            pid = self.request.query_params.get('provedor_id')
            return qs.filter(provedor_id=pid) if pid else qs
        pid = getattr(self.request.user, 'provedor_id', None)
        return qs.filter(provedor_id=pid) if pid else qs.none()


class MobileAIConfigView(APIView):
    permission_classes = [IsSuperadmin]

    def get(self, request):
        settings_obj = MobileSystemSettings.get_solo()
        key = settings_obj.gemini_api_key or ''
        masked = ''
        if key:
            masked = f'{key[:4]}…{key[-4:]}' if len(key) > 8 else '••••'
        return Response({
            'gemini_api_key_configured': bool(key),
            'gemini_api_key_masked': masked,
        })

    def put(self, request):
        settings_obj = MobileSystemSettings.get_solo()
        key = request.data.get('gemini_api_key')
        if key is not None:
            settings_obj.gemini_api_key = (key or '').strip() or None
            settings_obj.save(update_fields=['gemini_api_key', 'updated_at'])
        return self.get(request)
