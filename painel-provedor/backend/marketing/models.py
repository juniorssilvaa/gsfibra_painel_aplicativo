from django.contrib.auth import get_user_model
from django.db import models

from core.models import Plano, Provedor

User = get_user_model()


class MarketingThread(models.Model):
    """Conversa do dono do provedor com a IA de marketing."""
    provedor = models.ForeignKey(Provedor, on_delete=models.CASCADE, related_name='marketing_threads')
    title = models.CharField(max_length=200, default='Nova conversa')
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='+')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'marketing_threads'
        ordering = ['-updated_at']

    def __str__(self):
        return f"MarketingThread {self.id} {self.title[:40]}"


class MarketingMessage(models.Model):
    ROLE_CHOICES = [('user', 'Usuário'), ('assistant', 'IA')]
    STATUS_CHOICES = [('done', 'Concluída'), ('pending', 'Processando'), ('error', 'Erro')]

    thread = models.ForeignKey(MarketingThread, on_delete=models.CASCADE, related_name='messages')
    role = models.CharField(max_length=10, choices=ROLE_CHOICES)
    content = models.TextField(blank=True, default='')
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='done')
    # user: referências anexadas; assistant: artes geradas no turno.
    asset_ids = models.JSONField(default=list, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'marketing_messages'
        ordering = ['id']

    def __str__(self):
        return f"MarketingMessage {self.id} [{self.role}/{self.status}]"


class MarketingAsset(models.Model):
    """Imagem do Estúdio: arte gerada pela IA ou referência enviada pelo dono (logo, arte antiga)."""
    KIND_CHOICES = [('creative', 'Arte gerada'), ('reference', 'Referência')]

    provedor = models.ForeignKey(Provedor, on_delete=models.CASCADE, related_name='marketing_assets')
    thread = models.ForeignKey(
        MarketingThread, on_delete=models.SET_NULL, null=True, blank=True, related_name='assets'
    )
    kind = models.CharField(max_length=10, choices=KIND_CHOICES)
    image = models.BinaryField()
    # Modo "sistema": arte sem os textos, para reaplicar textos/logo sem gerar outra imagem.
    base_image = models.BinaryField(null=True, blank=True)
    mime_type = models.CharField(max_length=50, default='image/jpeg')
    width = models.PositiveIntegerField(default=0)
    height = models.PositiveIntegerField(default=0)
    formato = models.CharField(max_length=20, blank=True, default='')
    modo_texto = models.CharField(max_length=10, blank=True, default='')
    prompt = models.TextField(blank=True, default='')
    # Textos, cor e logo usados; ajustes herdam o que não for informado de novo.
    textos = models.JSONField(default=dict, blank=True)
    plano = models.ForeignKey(Plano, on_delete=models.SET_NULL, null=True, blank=True, related_name='+')
    parent = models.ForeignKey('self', on_delete=models.SET_NULL, null=True, blank=True, related_name='versions')
    original_name = models.CharField(max_length=200, blank=True, default='')
    descricao = models.TextField(blank=True, default='', help_text='Descrição visual da referência, lida pela IA do chat')
    engine = models.CharField(max_length=60, blank=True, default='')
    approved = models.BooleanField(default=False)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='+')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'marketing_assets'
        indexes = [
            models.Index(fields=['provedor', 'kind', 'created_at'], name='mkt_asset_prov_kind_idx'),
        ]

    def __str__(self):
        return f"MarketingAsset {self.id} [{self.kind}]"
