from rest_framework import serializers, viewsets, status
from rest_framework.authentication import TokenAuthentication
from rest_framework.decorators import action
from rest_framework.response import Response

from super_core.models import Provedor
from mobile_app.permissions import IsSuperadmin
from .models import AcsDeploymentLog, AcsHardwareBind, AcsLicense, AcsProfile, AcsRelease
from .services import ensure_acs_for_provedor


class AcsProfileSerializer(serializers.ModelSerializer):
    provedor_id = serializers.IntegerField(source='provedor.id', read_only=True)
    provedor_nome = serializers.CharField(source='provedor.nome', read_only=True)
    provedor_is_active = serializers.BooleanField(source='provedor.is_active', read_only=True)
    licenses_count = serializers.SerializerMethodField()
    hardware_count = serializers.SerializerMethodField()
    active_license_key = serializers.SerializerMethodField()

    class Meta:
        model = AcsProfile
        fields = (
            'id',
            'provedor_id',
            'provedor_nome',
            'provedor_is_active',
            'is_active',
            'update_channel',
            'auto_update',
            'current_version',
            'fixed_version',
            'last_check',
            'licenses_count',
            'hardware_count',
            'active_license_key',
            'created_at',
            'updated_at',
        )
        read_only_fields = ('created_at', 'updated_at', 'current_version', 'last_check')

    def get_licenses_count(self, obj):
        return obj.licenses.count()

    def get_hardware_count(self, obj):
        return obj.hardware_binds.count()

    def get_active_license_key(self, obj):
        lic = obj.licenses.filter(status='active').order_by('-created_at').first()
        return str(lic.key) if lic else None


class AcsLicenseSerializer(serializers.ModelSerializer):
    provedor_id = serializers.IntegerField(source='profile.provedor_id', read_only=True)
    provedor_nome = serializers.CharField(source='profile.provedor.nome', read_only=True)
    hardware_count = serializers.SerializerMethodField()
    key = serializers.UUIDField(read_only=True)
    current_version = serializers.CharField(source='profile.current_version', read_only=True)
    update_channel = serializers.CharField(source='profile.update_channel', read_only=True)
    auto_update = serializers.BooleanField(source='profile.auto_update', read_only=True)
    last_check = serializers.DateTimeField(source='profile.last_check', read_only=True)
    profile_id = serializers.IntegerField(source='profile.id', read_only=True)

    class Meta:
        model = AcsLicense
        fields = (
            'id',
            'profile',
            'profile_id',
            'provedor_id',
            'provedor_nome',
            'key',
            'status',
            'expiration_date',
            'max_onts',
            'suspend_source',
            'hardware_count',
            'current_version',
            'update_channel',
            'auto_update',
            'last_check',
            'created_at',
        )
        read_only_fields = ('created_at', 'suspend_source')

    def get_hardware_count(self, obj):
        return obj.hardware_binds.count()


class AcsHardwareBindSerializer(serializers.ModelSerializer):
    provedor_id = serializers.IntegerField(source='profile.provedor_id', read_only=True)
    provedor_nome = serializers.CharField(source='profile.provedor.nome', read_only=True)
    license_key = serializers.UUIDField(source='license.key', read_only=True)
    license_status = serializers.CharField(source='license.status', read_only=True)
    current_version = serializers.CharField(source='profile.current_version', read_only=True)

    class Meta:
        model = AcsHardwareBind
        fields = (
            'id',
            'profile',
            'license',
            'provedor_id',
            'provedor_nome',
            'license_key',
            'license_status',
            'current_version',
            'machine_name',
            'hwid_hash',
            'last_ip',
            'last_seen',
            'status',
        )


class AcsReleaseSerializer(serializers.ModelSerializer):
    class Meta:
        model = AcsRelease
        fields = '__all__'


class AcsDeploymentLogSerializer(serializers.ModelSerializer):
    provedor_nome = serializers.CharField(source='profile.provedor.nome', read_only=True)

    class Meta:
        model = AcsDeploymentLog
        fields = (
            'id',
            'profile',
            'provedor_nome',
            'from_version',
            'to_version',
            'status',
            'error_message',
            'started_at',
            'finished_at',
            'had_rollback',
        )


class AcsProfileViewSet(viewsets.ModelViewSet):
    authentication_classes = [TokenAuthentication]
    permission_classes = [IsSuperadmin]
    queryset = AcsProfile.objects.select_related('provedor').all().order_by('-created_at')
    serializer_class = AcsProfileSerializer
    http_method_names = ['get', 'post', 'patch', 'head', 'options']

    @action(detail=False, methods=['get'], url_path='dashboard-stats')
    def dashboard_stats(self, request):
        profiles = AcsProfile.objects.all()
        licenses = AcsLicense.objects.all()
        return Response({
            'total_providers': profiles.count(),
            'active_providers': profiles.filter(is_active=True).count(),
            'inactive_providers': profiles.filter(is_active=False).count(),
            'active_licenses': licenses.filter(status='active').count(),
            'suspended_licenses': licenses.filter(status='suspended').count(),
            'expired_licenses': licenses.filter(status='expired').count(),
            'hardware_binds': AcsHardwareBind.objects.filter(status=True).count(),
        })

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

        max_onts = request.data.get('max_onts', 100)
        try:
            max_onts = int(max_onts)
        except (TypeError, ValueError):
            max_onts = 100

        expiration_date = request.data.get('expiration_date') or None
        profile, license_obj, created = ensure_acs_for_provedor(
            provedor,
            is_active=bool(is_active),
            create_license=True,
            expiration_date=expiration_date,
            max_onts=max_onts,
        )

        channel = (request.data.get('update_channel') or '').strip()
        if channel in dict(AcsProfile.UPDATE_CHANNELS):
            profile.update_channel = channel
            profile.save(update_fields=['update_channel', 'updated_at'])

        return Response(
            {
                'success': True,
                'created': created,
                'profile': AcsProfileSerializer(profile).data,
                'license_key': str(license_obj.key) if license_obj else None,
                'license_status': license_obj.status if license_obj else None,
            },
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )

    @action(detail=True, methods=['post'], url_path='toggle-status')
    def toggle_status(self, request, pk=None):
        profile = self.get_object()
        profile.is_active = not profile.is_active
        profile.save(update_fields=['is_active', 'updated_at'])
        from .services import sync_acs_access
        sync_acs_access(profile.provedor, profile.is_active, source='manual')
        return Response({
            'success': True,
            'is_active': profile.is_active,
            'provedor_id': profile.provedor_id,
        })


class AcsLicenseViewSet(viewsets.ModelViewSet):
    authentication_classes = [TokenAuthentication]
    permission_classes = [IsSuperadmin]
    queryset = AcsLicense.objects.select_related('profile', 'profile__provedor').all()
    serializer_class = AcsLicenseSerializer

    def create(self, request, *args, **kwargs):
        provedor_id = request.data.get('provedor_id')
        profile_id = request.data.get('profile')
        profile = None
        if profile_id:
            profile = AcsProfile.objects.filter(id=profile_id).first()
        elif provedor_id:
            profile = AcsProfile.objects.filter(provedor_id=provedor_id).first()
            if not profile:
                try:
                    provedor = Provedor.objects.get(id=int(provedor_id))
                except (Provedor.DoesNotExist, TypeError, ValueError):
                    return Response({'error': 'Provedor não encontrado'}, status=404)
                profile, _, _ = ensure_acs_for_provedor(provedor, is_active=True, create_license=False)

        if not profile:
            return Response({'error': 'Informe provedor_id ou profile'}, status=400)

        expiration_date = request.data.get('expiration_date')
        if not expiration_date:
            return Response({'error': 'expiration_date é obrigatório'}, status=400)

        max_onts = request.data.get('max_onts', 100)
        try:
            max_onts = int(max_onts)
        except (TypeError, ValueError):
            max_onts = 100

        lic = AcsLicense.objects.create(
            profile=profile,
            expiration_date=expiration_date,
            max_onts=max_onts,
            status=request.data.get('status') or 'active',
        )
        return Response(AcsLicenseSerializer(lic).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['post'], url_path='suspend')
    def suspend(self, request, pk=None):
        from django.utils import timezone

        lic = self.get_object()
        if lic.status in ('suspended', 'expired'):
            today = timezone.localdate()
            if lic.expiration_date and lic.expiration_date < today:
                lic.status = 'expired'
                lic.suspend_source = ''
            else:
                lic.status = 'active'
                lic.suspend_source = ''
        else:
            lic.status = 'suspended'
            lic.suspend_source = 'manual'
        lic.save(update_fields=['status', 'suspend_source'])
        return Response(AcsLicenseSerializer(lic).data)

    @action(detail=True, methods=['post'], url_path='activate')
    def activate(self, request, pk=None):
        from django.utils import timezone

        lic = self.get_object()
        today = timezone.localdate()
        if lic.expiration_date and lic.expiration_date < today:
            lic.status = 'expired'
            lic.suspend_source = ''
        else:
            lic.status = 'active'
            lic.suspend_source = ''
        lic.save(update_fields=['status', 'suspend_source'])
        return Response(AcsLicenseSerializer(lic).data)

    @action(detail=True, methods=['post'], url_path='unbind-hardware')
    def unbind_hardware(self, request, pk=None):
        lic = self.get_object()
        deleted, _ = AcsHardwareBind.objects.filter(license=lic).delete()
        return Response({'success': True, 'deleted': deleted})

    @action(detail=True, methods=['post'], url_path='revoke')
    def revoke(self, request, pk=None):
        lic = self.get_object()
        lic.status = 'expired'
        lic.suspend_source = 'manual'
        lic.save(update_fields=['status', 'suspend_source'])
        return Response(AcsLicenseSerializer(lic).data)


class AcsHardwareBindViewSet(viewsets.ReadOnlyModelViewSet):
    authentication_classes = [TokenAuthentication]
    permission_classes = [IsSuperadmin]
    queryset = AcsHardwareBind.objects.select_related('profile', 'profile__provedor', 'license').all()
    serializer_class = AcsHardwareBindSerializer

    @action(detail=True, methods=['post'], url_path='unbind')
    def unbind(self, request, pk=None):
        bind = self.get_object()
        AcsHardwareBind.objects.filter(license=bind.license).delete()
        return Response({'success': True})


class AcsReleaseViewSet(viewsets.ModelViewSet):
    authentication_classes = [TokenAuthentication]
    permission_classes = [IsSuperadmin]
    queryset = AcsRelease.objects.all()
    serializer_class = AcsReleaseSerializer

    @action(detail=True, methods=['post'], url_path='toggle-mandatory')
    def toggle_mandatory(self, request, pk=None):
        release = self.get_object()
        release.is_mandatory = not release.is_mandatory
        release.save(update_fields=['is_mandatory'])
        return Response(AcsReleaseSerializer(release).data)


class AcsDeploymentLogViewSet(viewsets.ReadOnlyModelViewSet):
    authentication_classes = [TokenAuthentication]
    permission_classes = [IsSuperadmin]
    queryset = AcsDeploymentLog.objects.select_related('profile', 'profile__provedor').all()
    serializer_class = AcsDeploymentLogSerializer
