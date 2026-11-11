"""
ACS (GenieACS) no Superadmin Niohub.

O painel do provedor ACS valida a licença em /api/license/status
(mesmo contrato do painel_admin em E:\\genieacs).
"""
import uuid

from django.db import models


class AcsProfile(models.Model):
    """Habilita o ACS para o provedor (espelha o antigo ISP do painel_admin)."""

    UPDATE_CHANNELS = (
        ('stable', 'Stable'),
        ('beta', 'Beta'),
        ('lts', 'LTS'),
    )

    provedor = models.OneToOneField(
        'super_core.Provedor',
        on_delete=models.CASCADE,
        related_name='acs',
    )
    is_active = models.BooleanField(default=True)
    update_channel = models.CharField(max_length=20, choices=UPDATE_CHANNELS, default='stable')
    auto_update = models.BooleanField(default=True)
    current_version = models.CharField(max_length=50, blank=True, default='')
    fixed_version = models.CharField(max_length=50, blank=True, default='')
    last_check = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Perfil ACS'
        verbose_name_plural = 'Perfis ACS'

    def __str__(self):
        return f'ACS — {self.provedor.nome}'


class AcsLicense(models.Model):
    STATUS_CHOICES = (
        ('active', 'Ativa'),
        ('suspended', 'Suspensa'),
        ('expired', 'Expirada'),
    )
    SUSPEND_SOURCES = (
        ('', '—'),
        ('manual', 'Manual'),
        ('billing', 'Faturamento / bloqueio do provedor'),
    )

    profile = models.ForeignKey(AcsProfile, on_delete=models.CASCADE, related_name='licenses')
    key = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='active')
    expiration_date = models.DateField(verbose_name='Validade')
    max_onts = models.IntegerField(default=100)
    suspend_source = models.CharField(max_length=20, choices=SUSPEND_SOURCES, blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Licença ACS'
        verbose_name_plural = 'Licenças ACS'
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.profile.provedor.nome} — {self.key}'


class AcsHardwareBind(models.Model):
    profile = models.ForeignKey(AcsProfile, on_delete=models.CASCADE, related_name='hardware_binds')
    license = models.ForeignKey(AcsLicense, on_delete=models.CASCADE, related_name='hardware_binds')
    machine_name = models.CharField(max_length=200)
    hwid_hash = models.CharField(max_length=255, unique=True)
    last_ip = models.GenericIPAddressField(null=True, blank=True)
    last_seen = models.DateTimeField(auto_now=True)
    status = models.BooleanField(default=True)

    class Meta:
        verbose_name = 'Hardware ACS'
        verbose_name_plural = 'Hardwares ACS'
        ordering = ['-last_seen']

    def __str__(self):
        return f'{self.machine_name} ({self.profile.provedor.nome})'


class AcsRelease(models.Model):
    CHANNELS = (
        ('stable', 'Stable'),
        ('beta', 'Beta'),
        ('lts', 'LTS'),
    )
    version = models.CharField(max_length=50)
    channel = models.CharField(max_length=20, choices=CHANNELS, default='stable')
    is_active = models.BooleanField(default=True)
    is_mandatory = models.BooleanField(default=False)
    changelog = models.TextField(blank=True, default='')
    image_reference = models.CharField(max_length=255, blank=True, default='')
    checksum = models.CharField(max_length=255, blank=True, default='')
    min_db_version = models.IntegerField(default=1)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Release ACS'
        verbose_name_plural = 'Releases ACS'
        unique_together = ('version', 'channel')
        ordering = ['-created_at']

    def __str__(self):
        return f'v{self.version} ({self.channel})'


class AcsDeploymentLog(models.Model):
    profile = models.ForeignKey(AcsProfile, on_delete=models.CASCADE, related_name='deployment_logs')
    from_version = models.CharField(max_length=50, blank=True, default='')
    to_version = models.CharField(max_length=50, blank=True, default='')
    status = models.CharField(max_length=20, default='')
    error_message = models.TextField(blank=True, default='')
    started_at = models.DateTimeField(auto_now_add=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    had_rollback = models.BooleanField(default=False)

    class Meta:
        verbose_name = 'Log de implantação ACS'
        verbose_name_plural = 'Logs de implantação ACS'
        ordering = ['-started_at']
