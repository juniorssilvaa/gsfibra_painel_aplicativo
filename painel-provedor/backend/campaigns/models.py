from django.conf import settings
from django.db import models


class Campaign(models.Model):
    STATUS_CHOICES = [
        ('rascunho', 'Rascunho'),
        ('agendada', 'Agendada'),
        ('enviando', 'Enviando'),
        ('concluida', 'Concluída'),
        ('cancelada', 'Cancelada'),
        ('falhou', 'Falhou'),
    ]

    provedor = models.ForeignKey('core.Provedor', on_delete=models.CASCADE, related_name='campanhas')
    nome = models.CharField(max_length=150)
    canal = models.ForeignKey(
        'core.Canal', on_delete=models.SET_NULL, null=True, blank=True, related_name='campanhas'
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='rascunho', db_index=True)
    mensagem = models.TextField(blank=True, default='')
    template_name = models.CharField(max_length=255, blank=True, default='')
    template_language = models.CharField(max_length=20, blank=True, default='')
    template_def = models.JSONField(default=dict, blank=True)
    template_variaveis = models.JSONField(default=list, blank=True)
    template_header_texto = models.CharField(max_length=255, blank=True, default='')
    template_header_url = models.URLField(max_length=1000, blank=True, default='')
    template_header_arquivo = models.FileField(upload_to='campanhas/', max_length=255, blank=True, default='')
    template_header_media_id = models.CharField(max_length=100, blank=True, default='')
    template_header_media_em = models.DateTimeField(null=True, blank=True)
    agendada_para = models.DateTimeField(null=True, blank=True, db_index=True)
    intervalo_segundos = models.PositiveIntegerField(default=5)
    erro = models.TextField(blank=True, default='')
    reservada_ate = models.DateTimeField(null=True, blank=True)
    criada_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='+'
    )
    iniciada_em = models.DateTimeField(null=True, blank=True)
    concluida_em = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Campanha'
        verbose_name_plural = 'Campanhas'

    def __str__(self):
        return self.nome


class CampaignRecipient(models.Model):
    STATUS_CHOICES = [
        ('pendente', 'Pendente'),
        ('enviado', 'Enviado'),
        ('falhou', 'Falhou'),
        ('ignorado', 'Ignorado'),
    ]

    campanha = models.ForeignKey(Campaign, on_delete=models.CASCADE, related_name='destinatarios')
    contato = models.ForeignKey(
        'conversations.Contact', on_delete=models.SET_NULL, null=True, blank=True, related_name='+'
    )
    nome = models.CharField(max_length=255, blank=True, default='')
    telefone = models.CharField(max_length=32, blank=True, default='')
    telegram_chat_id = models.CharField(max_length=64, blank=True, default='')
    dados = models.JSONField(default=dict, blank=True)
    origem = models.CharField(max_length=10, default='contato')
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='pendente', db_index=True)
    erro = models.CharField(max_length=500, blank=True, default='')
    external_id = models.CharField(max_length=255, blank=True, default='')
    enviado_em = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['id']
        indexes = [models.Index(fields=['campanha', 'status'])]

    def __str__(self):
        return f'{self.nome} {self.telefone}'.strip()
