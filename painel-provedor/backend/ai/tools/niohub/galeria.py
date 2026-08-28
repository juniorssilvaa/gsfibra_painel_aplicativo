"""Tools NioHub — envio de imagens da Galeria / planos em texto."""

from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

_TAG_RE = re.compile(r"\{([^{}]+)\}")

# Pedido explícito do cliente
_TEXT_HINTS = (
    "em texto",
    "por texto",
    "por escrito",
    "só texto",
    "so texto",
    "somente texto",
    "apenas texto",
    "manda texto",
    "manda em texto",
    "quero texto",
    "quero em texto",
    "lista em texto",
    "escreve os planos",
    "escreva os planos",
    "descreve os planos",
    "descreva os planos",
)
_IMAGE_HINTS = (
    "em imagem",
    "por imagem",
    "só imagem",
    "so imagem",
    "somente imagem",
    "apenas imagem",
    "manda imagem",
    "manda a imagem",
    "manda foto",
    "quero imagem",
    "quero a imagem",
    "quero foto",
    "envia a imagem",
    "envia imagem",
)

# Regra na base de conhecimento → forçar só imagem
_KB_ONLY_IMAGE = (
    "somente imagem",
    "apenas imagem",
    "só imagem",
    "so imagem",
    "somente imagens",
    "apenas imagens",
    "enviar somente imagem",
    "enviar apenas imagem",
    "enviar so imagem",
    "enviar só imagem",
    "mandar somente imagem",
    "mandar apenas imagem",
    "planos somente em imagem",
    "planos apenas em imagem",
    "planos só em imagem",
    "planos so em imagem",
)


def normalize_gallery_tag(tag: Optional[str]) -> str:
    t = (tag or "").strip()
    if t.startswith("{") and t.endswith("}") and len(t) >= 2:
        t = t[1:-1]
    return t.strip().lower()


def extract_gallery_tags(nome: str) -> List[str]:
    return [m.group(1).strip().lower() for m in _TAG_RE.finditer(nome or "") if m.group(1).strip()]


def list_gallery_tags_for_provedor(provedor) -> List[str]:
    from core.models import ProviderGalleryImage

    tags = set()
    for nome in ProviderGalleryImage.objects.filter(
        provedor=provedor, ativo=True
    ).values_list("nome", flat=True):
        tags.update(extract_gallery_tags(nome or ""))
    return sorted(tags)


def select_gallery_images(provedor, tag: Optional[str] = None) -> List[Any]:
    from core.models import ProviderGalleryImage

    qs = list(
        ProviderGalleryImage.objects.filter(provedor=provedor, ativo=True).order_by(
            "nome", "id"
        )
    )
    nt = normalize_gallery_tag(tag)
    if nt:
        needle = f"{{{nt}}}"
        selected = []
        for img in qs:
            nome = img.nome or ""
            tags = extract_gallery_tags(nome)
            if nt in tags or needle in nome.lower():
                selected.append(img)
        return selected
    return [img for img in qs if not extract_gallery_tags(img.nome or "")]


def list_planos_texto(provedor) -> str:
    try:
        from ai.prompt_base import _list_planos

        return (_list_planos(provedor) or "").strip()
    except Exception:
        return ""


def provedor_exige_somente_imagem_planos(provedor) -> bool:
    """Base de conhecimento (dados_adicionais) pede só imagem para planos."""
    kb = (getattr(provedor, "dados_adicionais", None) or "").strip().lower()
    if not kb:
        return False
    # Precisa citar planos/galeria/imagem de forma relacionada a planos
    if "plano" not in kb and "planos" not in kb and "galeria" not in kb:
        # ainda assim aceita frases genéricas de "somente imagem"
        return any(p in kb for p in _KB_ONLY_IMAGE)
    return any(p in kb for p in _KB_ONLY_IMAGE)


def detectar_pedido_formato(mensagem: str) -> Optional[str]:
    """Retorna 'texto', 'imagem' ou None."""
    msg = (mensagem or "").lower().strip()
    if not msg:
        return None
    if any(h in msg for h in _TEXT_HINTS):
        return "texto"
    if any(h in msg for h in _IMAGE_HINTS):
        return "imagem"
    return None


def _resolve_conversation(contexto, conversation_id):
    from conversations.models import Conversation

    conv_id = conversation_id
    if not conv_id and contexto and contexto.get("conversation") is not None:
        conv_id = getattr(contexto["conversation"], "id", None)
    if not conv_id:
        return None
    return (
        Conversation.objects.select_related("inbox", "contact", "inbox__provedor")
        .filter(pk=conv_id)
        .first()
    )


def _channel_phone(contexto, conv) -> Tuple[str, str]:
    from core.redis_memory_service import redis_memory_service

    channel = "wa"
    if contexto and contexto.get("canal"):
        channel = redis_memory_service.normalize_channel(contexto["canal"])
    elif conv and getattr(conv, "inbox", None):
        channel = redis_memory_service.normalize_channel(
            getattr(conv.inbox, "channel_type", None) or "wa"
        )
    phone = "unknown"
    if contexto and contexto.get("contact"):
        phone = getattr(contexto["contact"], "phone", None) or "unknown"
    elif contexto and contexto.get("contact_phone"):
        phone = contexto["contact_phone"] or "unknown"
    elif conv and getattr(conv, "contact", None):
        phone = getattr(conv.contact, "phone", None) or "unknown"
    return channel, phone


def _decidir_modo(
    *,
    provedor,
    mensagem: str,
    tem_imagem: bool,
    tem_texto: bool,
    ultimo: Optional[str],
) -> str:
    """
    Retorna 'imagem' ou 'texto'.
    Padrão: alterna quando há os dois. Nunca fica só em imagem sem regra da KB.
    """
    pedido = detectar_pedido_formato(mensagem)
    so_imagem_kb = provedor_exige_somente_imagem_planos(provedor)

    if pedido == "texto" and tem_texto:
        return "texto"
    if pedido == "imagem" and tem_imagem:
        return "imagem"
    if pedido == "texto" and not tem_texto and tem_imagem:
        return "imagem"
    if pedido == "imagem" and not tem_imagem and tem_texto:
        return "texto"

    if so_imagem_kb and tem_imagem:
        return "imagem"

    if tem_imagem and tem_texto:
        # Alterna: última imagem → texto; última texto/vazio → imagem
        if (ultimo or "").lower() == "imagem":
            return "texto"
        return "imagem"

    if tem_imagem:
        return "imagem"
    return "texto"


def _salvar_ultimo_formato(provedor, conv, contexto, modo: str) -> None:
    try:
        from core.redis_memory_service import redis_memory_service

        channel, phone = _channel_phone(contexto, conv)
        redis_memory_service.update_ai_state_sync(
            provedor.id,
            conv.id,
            {"planos_formato_ultimo": modo},
            channel,
            phone,
        )
    except Exception as e:
        logger.warning("[AI][Galeria] Não salvou planos_formato_ultimo: %s", e)


def _ler_ultimo_formato(provedor, conv, contexto) -> Optional[str]:
    try:
        from core.redis_memory_service import redis_memory_service

        channel, phone = _channel_phone(contexto, conv)
        state = redis_memory_service.get_ai_state_sync(
            provedor.id, conv.id, channel, phone
        )
        return (state or {}).get("planos_formato_ultimo")
    except Exception:
        return None


def _resposta_texto(planos: str, tag, tags_disponiveis, motivo: str) -> Dict[str, Any]:
    return {
        "success": True,
        "modo": "texto",
        "usar_texto": True,
        "enviadas": 0,
        "tag": tag or None,
        "tags_disponiveis": tags_disponiveis,
        "planos_texto": planos,
        "nota": (
            f"{motivo} "
            "OBRIGATORIO: descreva os planos por escrito usando planos_texto "
            "(ou a secao Produtos / Planos). NAO chame de novo a galeria neste turno. "
            "NAO diga que enviou imagem."
        ),
    }


def enviar_imagens_galeria(
    *,
    provedor,
    arguments=None,
    contexto=None,
    conversation_id=None,
    actions=None,
    mensagem: str = "",
    **_kw,
) -> Dict[str, Any]:
    """
    Planos: alterna imagem da Galeria e texto da aba Planos.
    Só imagem contínua se a base de conhecimento pedir.
    Cliente pedindo texto → texto; pedindo imagem → imagem.
    """
    args = arguments or {}
    raw_tag = args.get("tag") or args.get("variavel") or args.get("nome") or "planos"
    caption = (args.get("legenda") or args.get("caption") or "").strip()
    tag = normalize_gallery_tag(str(raw_tag) if raw_tag is not None else "") or "planos"
    msg = mensagem or (contexto or {}).get("mensagem") or ""

    conv = _resolve_conversation(contexto, conversation_id)
    if not conv:
        return {"success": False, "erro": "Conversa não identificada para enviar imagem."}

    tags_disponiveis = list_gallery_tags_for_provedor(provedor)
    imagens = select_gallery_images(provedor, tag=tag)
    planos = list_planos_texto(provedor)
    tem_imagem = bool(imagens)
    tem_texto = bool(planos)
    ultimo = _ler_ultimo_formato(provedor, conv, contexto)

    if not tem_imagem and not tem_texto:
        return {
            "success": False,
            "modo": None,
            "usar_texto": False,
            "enviadas": 0,
            "tag": tag,
            "tags_disponiveis": tags_disponiveis,
            "erro": (
                f"Sem imagens {{{tag}}} na Galeria e sem planos cadastrados na aba Planos. "
                "Cadastre um dos dois."
            ),
        }

    modo = _decidir_modo(
        provedor=provedor,
        mensagem=msg,
        tem_imagem=tem_imagem,
        tem_texto=tem_texto,
        ultimo=ultimo,
    )

    if modo == "texto":
        _salvar_ultimo_formato(provedor, conv, contexto, "texto")
        motivo = "Modo TEXTO (alternancia ou pedido do cliente)."
        if detectar_pedido_formato(msg) == "texto":
            motivo = "Cliente pediu os planos em TEXTO."
        elif (ultimo or "").lower() == "imagem":
            motivo = "Alternancia: na vez anterior foi imagem; agora envie em TEXTO."
        return _resposta_texto(planos, tag, tags_disponiveis, motivo)

    # modo imagem
    from core.chatbot_engine import ChatbotEngine

    enviadas: List[Dict[str, Any]] = []
    falhas: List[Dict[str, Any]] = []
    send = ChatbotEngine.send_gallery_image_agnostic_sync

    for img in imagens:
        try:
            ok, detail = send(conv, img, caption)
            item = {"id": img.id, "nome": img.nome}
            if ok:
                enviadas.append(item)
            else:
                falhas.append({**item, "erro": str(detail) if detail else "falha no envio"})
        except Exception as e:
            logger.error(
                "[AI][Galeria] Falha ao enviar id=%s: %s", getattr(img, "id", None), e, exc_info=True
            )
            falhas.append(
                {
                    "id": getattr(img, "id", None),
                    "nome": getattr(img, "nome", None),
                    "erro": str(e),
                }
            )

    if not enviadas:
        if tem_texto:
            _salvar_ultimo_formato(provedor, conv, contexto, "texto")
            return _resposta_texto(
                planos,
                tag,
                tags_disponiveis,
                "Falha ao enviar imagem; fallback para TEXTO dos planos.",
            )
        return {
            "success": False,
            "modo": "imagem",
            "usar_texto": False,
            "enviadas": 0,
            "falhas": falhas,
            "tag": tag,
            "tags_disponiveis": tags_disponiveis,
            "erro": "Falha ao enviar as imagens da Galeria e nao ha planos em texto.",
        }

    _salvar_ultimo_formato(provedor, conv, contexto, "imagem")
    so_img = provedor_exige_somente_imagem_planos(provedor)
    nota = (
        "Modo IMAGEM: as imagens JA foram enviadas. "
        "Responda com 1 frase curta (duvida/contratar). "
        "NAO liste precos/velocidades por escrito neste turno."
    )
    if so_img:
        nota = (
            "Regra da base de conhecimento: SOMENTE imagem. "
            "Imagens enviadas. So 1 frase curta; NAO descreva planos por escrito."
        )
    elif tem_texto:
        nota += (
            " Na PROXIMA vez que pedirem planos, a tool deve alternar para TEXTO "
            "(ja controlado no servidor)."
        )

    return {
        "success": True,
        "modo": "imagem",
        "usar_texto": False,
        "tag": tag,
        "tags_disponiveis": tags_disponiveis,
        "enviadas": len(enviadas),
        "imagens_enviadas": enviadas,
        "falhas": falhas,
        "nota": nota,
    }
