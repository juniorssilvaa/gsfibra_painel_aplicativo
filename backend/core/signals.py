from django.db.models.signals import post_save
from django.dispatch import receiver
from django.apps import apps
from .models import Canal
import logging

logger = logging.getLogger(__name__)

@receiver(post_save, sender=Canal)
def sync_inbox_name(sender, instance, created, **kwargs):
    """
    Sincroniza o nome do Inbox quando o nome do Canal é alterado.
    """
    try:
        Inbox = apps.get_model('conversations', 'Inbox')
        
        # O prefixo padrão que usamos é "WhatsApp - "
        # Se for necessário, podemos expandir para outros tipos futuramente
        prefixo = "WhatsApp - " if instance.tipo in ['whatsapp', 'whatsapp_oficial', 'whatsapp_session'] else ""
        novo_nome_inbox = f"{prefixo}{instance.nome}"
        
        # Buscar inboxes vinculados a este canal pelo channel_id (que armazena o ID do canal)
        inboxes = Inbox.objects.filter(channel_id=str(instance.id))
        
        for inbox in inboxes:
            if inbox.name != novo_nome_inbox:
                logger.info(f"[Signal] Atualizando nome do Inbox {inbox.id} de '{inbox.name}' para '{novo_nome_inbox}'")
                inbox.name = novo_nome_inbox
                inbox.save(update_fields=['name', 'updated_at'])
                
    except Exception as e:
        logger.error(f"[Signal] Erro ao sincronizar nome do Inbox para o canal {instance.id}: {e}")
