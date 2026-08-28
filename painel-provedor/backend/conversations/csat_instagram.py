"""CSAT via Instagram Messaging (template button + postback)."""
import logging

from conversations.csat_whatsapp import CSAT_LIST_ROWS, build_csat_list_body

logger = logging.getLogger(__name__)


def send_csat_instagram(csat_request) -> bool:
    """Envia pesquisa CSAT no Instagram (2 templates — máx. 3 botões cada)."""
    try:
        from core.models import Canal
        from integrations.instagram_send import send_instagram_button_template, send_instagram_text

        conversation = csat_request.conversation
        contact = csat_request.contact
        provedor = csat_request.provedor
        inbox = conversation.inbox if conversation else None

        canal = None
        if inbox and inbox.channel_id and inbox.channel_id != 'default':
            try:
                canal = Canal.objects.get(
                    id=inbox.channel_id,
                    provedor=provedor,
                    tipo='instagram',
                    ativo=True,
                )
            except (Canal.DoesNotExist, ValueError, TypeError):
                canal = None
        if not canal:
            canal = Canal.objects.filter(
                provedor=provedor,
                tipo='instagram',
                ativo=True,
            ).first()
        if not canal or not canal.token:
            logger.error(
                '[CSAT][Instagram] Canal não encontrado request=%s provedor=%s',
                csat_request.id,
                provedor.id,
            )
            return False

        contact_attrs = (contact.additional_attributes or {}) if contact else {}
        recipient = contact_attrs.get('instagram_scoped_id') or (contact.phone if contact else None)
        if not recipient:
            logger.error('[CSAT][Instagram] Contato sem IGSID request=%s', csat_request.id)
            return False

        body = build_csat_list_body(
            contact.name if contact else 'Cliente',
            provedor.nome or 'nossa equipe',
        )
        ok_intro, _, err_intro = send_instagram_text(canal, str(recipient), body)
        if not ok_intro:
            logger.warning('[CSAT][Instagram] Intro falhou request=%s: %s', csat_request.id, err_intro)
            return False

        batch1 = [
            {'id': row['id'], 'title': row['title'][:20]}
            for row in CSAT_LIST_ROWS[:3]
        ]
        ok1, _, err1 = send_instagram_button_template(
            canal,
            str(recipient),
            'Escolha sua nota:',
            msg_btns=batch1,
        )
        if not ok1:
            logger.warning('[CSAT][Instagram] Template 1 falhou request=%s: %s', csat_request.id, err1)
            return False

        batch2 = [
            {'id': row['id'], 'title': row['title'][:20]}
            for row in CSAT_LIST_ROWS[3:]
        ]
        ok2, _, err2 = send_instagram_button_template(
            canal,
            str(recipient),
            'Ou escolha:',
            msg_btns=batch2,
        )
        if not ok2:
            logger.warning('[CSAT][Instagram] Template 2 falhou request=%s: %s', csat_request.id, err2)
            return False

        logger.info(
            '[CSAT][Instagram] Pesquisa enviada request=%s conversa=%s',
            csat_request.id,
            conversation.id,
        )
        return True
    except Exception as exc:
        logger.error('[CSAT][Instagram] Erro ao enviar: %s', exc, exc_info=True)
        return False
