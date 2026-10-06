from ai.context.conversation_context import build_conversation_context
from ai.context.customer_context import build_customer_context
from ai.context.provider_context import build_provider_runtime_hints


def build_full_context_blocks(
    *,
    provedor,
    conversation_state=None,
    conversation_id=None,
    contact_phone="unknown",
    channel="wa",
    ai_conversation_id="",
    has_ai_interaction: bool = False,
    conversation=None,
) -> str:
    from ai.context import conversation_context, customer_context, provider_context
    from conversations.protocol_service import get_conversation_protocol, get_protocol_source

    from conversations.ad_referral import ad_origin_for_prompt

    protocolo = None
    protocol_source = None
    origem_anuncio = None
    conv = conversation
    if conv is None and conversation_id:
        try:
            from conversations.models import Conversation

            conv = Conversation.objects.filter(pk=conversation_id).first()
        except Exception:
            conv = None
    if conv is not None:
        try:
            protocolo = get_conversation_protocol(conv)
            protocol_source = get_protocol_source(conv)
        except Exception:
            pass
        origem_anuncio = ad_origin_for_prompt(conv)

    conv_ctx = build_conversation_context(
        provedor=provedor,
        conversation_state=conversation_state,
        conversation_id=conversation_id,
        contact_phone=contact_phone,
        channel=channel,
        ai_conversation_id=ai_conversation_id,
        protocolo=protocolo,
        protocol_source=protocol_source,
        informar_protocolo_primeira_resposta=not has_ai_interaction and bool(protocolo),
        origem_anuncio=origem_anuncio,
    )
    cust = build_customer_context(conversation_state)
    hints = build_provider_runtime_hints(provedor)
    agent_mode = (getattr(provedor, "agent_mode", None) or "isp").strip().lower()

    blocks = [
        conversation_context.as_prompt_block(conv_ctx),
        customer_context.as_prompt_block(cust),
        provider_context.as_prompt_block(
            hints,
            has_ai_interaction=has_ai_interaction,
            agent_mode=agent_mode,
        ),
    ]
    return "\n\n".join(b for b in blocks if b)


__all__ = [
    "build_conversation_context",
    "build_customer_context",
    "build_provider_runtime_hints",
    "build_full_context_blocks",
]
