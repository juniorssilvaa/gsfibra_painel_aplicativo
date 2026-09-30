"""
URLs assinadas de curta duração para mídia local.

<img>/<audio>/<video> não enviam Authorization — HMAC na query é o caminho seguro.
"""
from __future__ import annotations

import hashlib
import hmac
import logging
import time
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from django.conf import settings

logger = logging.getLogger(__name__)

# Paths locais que exigem assinatura
_PROTECTED_PREFIXES = (
    "/api/media/messages/",
    "/api/media/private_chat/",
    "/api/media/provider-gallery/",
    "/api/media/proxy/",
    "/media/private_chat/",
    "/media/messages/",
)


def media_signed_url_ttl() -> int:
    return int(getattr(settings, "MEDIA_SIGNED_URL_TTL", 86400))


def media_signed_url_ttl_external() -> int:
    """TTL maior para entrega externa (ex.: WhatsApp/Meta buscando galeria)."""
    return int(getattr(settings, "MEDIA_SIGNED_URL_TTL_EXTERNAL", 604800))


def media_require_signed_url() -> bool:
    return bool(getattr(settings, "MEDIA_REQUIRE_SIGNED_URL", True))


def _signing_key() -> bytes:
    raw = (getattr(settings, "SECRET_KEY", "") or "").encode("utf-8")
    # Derivação estável para não reutilizar a chave crua em mais de um contexto
    return hmac.new(raw, b"niohub-media-url-v1", hashlib.sha256).digest()


def is_local_media_path(path: str) -> bool:
    if not path:
        return False
    normalized = path.split("?", 1)[0]
    if not normalized.startswith("/"):
        normalized = f"/{normalized}"
    return any(normalized.startswith(prefix) for prefix in _PROTECTED_PREFIXES)


def _canonical_path(path: str) -> str:
    """Normaliza path para assinatura (sem query, leading slash, sem trailing slash)."""
    if "://" in path:
        p = urlparse(path).path or "/"
    else:
        p = path.split("?", 1)[0]
    if not p.startswith("/"):
        p = f"/{p}"
    if len(p) > 1 and p.endswith("/"):
        p = p.rstrip("/")
    return p


def _sign(path: str, expires: int) -> str:
    msg = f"{path}\n{expires}".encode("utf-8")
    return hmac.new(_signing_key(), msg, hashlib.sha256).hexdigest()


def sign_media_url(url_or_path: str, ttl: int | None = None) -> str:
    """
    Anexa expires+sig a um path/URL de mídia local.
    URLs externas http(s) são devolvidas sem alteração.
    """
    if not url_or_path:
        return url_or_path

    # Absoluta externa (não-local)
    if url_or_path.startswith("http://") or url_or_path.startswith("https://"):
        parsed = urlparse(url_or_path)
        if not is_local_media_path(parsed.path):
            return url_or_path
        path = _canonical_path(parsed.path)
        expires = int(time.time()) + int(ttl if ttl is not None else media_signed_url_ttl())
        sig = _sign(path, expires)
        query = dict(parse_qsl(parsed.query, keep_blank_values=True))
        query["expires"] = str(expires)
        query["sig"] = sig
        out_path = f"{path}/" if path.startswith("/api/media/") else path
        return urlunparse(
            (
                parsed.scheme,
                parsed.netloc,
                out_path,
                "",
                urlencode(query),
                "",
            )
        )

    path = _canonical_path(url_or_path)
    if not is_local_media_path(path):
        return url_or_path

    expires = int(time.time()) + int(ttl if ttl is not None else media_signed_url_ttl())
    sig = _sign(path, expires)
    # Preservar outros query params (ex.: url= no proxy)
    existing_q = ""
    if "?" in url_or_path:
        existing_q = url_or_path.split("?", 1)[1]
    query = dict(parse_qsl(existing_q, keep_blank_values=True))
    query.pop("sig", None)
    query.pop("expires", None)
    query["expires"] = str(expires)
    query["sig"] = sig
    # Rotas Django /api/media/.../ exigem trailing slash na URL pública
    out_path = f"{path}/" if path.startswith("/api/media/") else path
    return f"{out_path}?{urlencode(query)}"


def verify_media_signature(path: str, expires: str | int | None, sig: str | None) -> bool:
    if not media_require_signed_url():
        return True
    if not expires or not sig:
        return False
    try:
        exp = int(expires)
    except (TypeError, ValueError):
        return False
    if exp < int(time.time()):
        return False
    canonical = _canonical_path(path)
    expected = _sign(canonical, exp)
    return hmac.compare_digest(expected, str(sig))


def sign_private_chat_url(file_url: str) -> str:
    """
    Assina mídia do chat interno sempre na rota /api/media/private_chat/<arquivo>/.
    /media/ nem sempre é roteado ao Django (proxy pode servir o front no lugar).
    """
    if not file_url:
        return file_url
    path = urlparse(file_url).path if "://" in file_url else file_url.split("?", 1)[0]
    legacy = "/media/private_chat/"
    if not path.startswith("/"):
        path = f"/{path}"
    if path.startswith(legacy):
        name = path[len(legacy):].strip("/")
        if name and "/" not in name:
            return sign_media_url(f"/api/media/private_chat/{name}")
    return sign_media_url(file_url)


def verify_request_media_signature(request, path: str | None = None) -> bool:
    """Valida expires/sig da query do request para o path servido."""
    canonical = _canonical_path(path or request.path)
    return verify_media_signature(
        canonical,
        request.GET.get("expires"),
        request.GET.get("sig"),
    )


def user_may_access_conversation_media(user, conversation) -> bool:
    """ACL: usuário do mesmo provedor (ou superadmin) pode ver mídia da conversa."""
    if not user or not getattr(user, "is_authenticated", False):
        return False
    if getattr(user, "user_type", None) == "superadmin" or getattr(user, "is_superuser", False):
        return True

    try:
        conv_provedor_id = getattr(getattr(conversation, "inbox", None), "provedor_id", None)
        if not conv_provedor_id and getattr(conversation, "inbox", None):
            provedor = getattr(conversation.inbox, "provedor", None)
            conv_provedor_id = getattr(provedor, "id", None)
    except Exception:
        conv_provedor_id = None

    if not conv_provedor_id:
        return False

    user_provedor_id = getattr(user, "provedor_id", None)
    if user_provedor_id and int(user_provedor_id) == int(conv_provedor_id):
        return True

    if hasattr(user, "provedores_admin") and user.provedores_admin.filter(id=conv_provedor_id).exists():
        return True

    # Agente via equipe
    try:
        from core.models import TeamMember

        return TeamMember.objects.filter(
            user=user, team__provedor_id=conv_provedor_id
        ).exists()
    except Exception:
        return False


def user_may_access_private_chat_file(user, filename: str) -> bool:
    """ACL: só sender/recipient da mensagem privada com aquele arquivo."""
    if not user or not getattr(user, "is_authenticated", False):
        return False
    if getattr(user, "user_type", None) == "superadmin" or getattr(user, "is_superuser", False):
        return True
    try:
        from conversations.models import PrivateMessage
        from django.db.models import Q

        needle = filename
        return PrivateMessage.objects.filter(
            Q(file_url__icontains=needle) | Q(file_url__endswith=needle),
        ).filter(Q(sender=user) | Q(recipient=user)).exists()
    except Exception as exc:
        logger.debug("ACL private chat media: %s", exc)
        return False
