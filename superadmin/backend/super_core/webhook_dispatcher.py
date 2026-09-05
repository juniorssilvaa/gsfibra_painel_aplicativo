"""
Webhook Dispatcher - Superadmin Central

Recebe eventos da Meta (WhatsApp Cloud + Instagram) em uma única URL:
    POST https://api.niohub.com.br/api/webhook/whatsapp-cloud/

Identifica o provedor pelo waba_id / phone_number_id (WhatsApp) ou
instagram_user_id (Instagram) e encaminha o payload para o tenant.

Fluxo:
1. Meta POST → validar assinatura → retornar 200 imediatamente
2. Background thread → lookup provedor → forward POST para o tenant
"""
import json
import hmac
import hashlib
import logging
import os
import threading
import requests

from django.http import JsonResponse, HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.conf import settings
from django.utils import timezone

from .models import Canal

logger = logging.getLogger(__name__)


def _webhook_app_secrets() -> list[str]:
    """Secrets usados na validação X-Hub-Signature-256 (Facebook + Instagram Login)."""
    secrets: list[str] = []
    for key in ('FACEBOOK_APP_SECRET', 'INSTAGRAM_APP_SECRET'):
        secret = (getattr(settings, key, None) or os.environ.get(key) or '').strip()
        if secret and secret not in secrets:
            secrets.append(secret)
    return secrets


def _verify_signature(body: bytes, signature: str) -> bool:
    """Valida X-Hub-Signature-256 da Meta."""
    if not signature or not signature.startswith("sha256="):
        logger.warning("[Dispatcher] Assinatura ausente ou formato inválido: %r", signature)
        return False
    secrets = _webhook_app_secrets()
    if not secrets:
        logger.error("[Dispatcher] FACEBOOK_APP_SECRET / INSTAGRAM_APP_SECRET não configurados.")
        return False
    received = signature.replace("sha256=", "")
    for app_secret in secrets:
        expected = hmac.new(
            app_secret.encode('utf-8'),
            body,
            hashlib.sha256,
        ).hexdigest()
        if hmac.compare_digest(received, expected):
            return True
    logger.warning(
        "[Dispatcher] Assinatura HMAC não confere (testados %s secret(s), body=%d bytes).",
        len(secrets),
        len(body),
    )
    return False


def _norm_graph_id(v) -> str | None:
    """Normaliza IDs da Meta (Graph devolve int ou str) para string consistente com o CharField."""
    if v is None:
        return None
    s = str(v).strip()
    return s or None


def _collect_phone_number_ids_from_value(value: dict) -> set[str]:
    """Recolhe phone_number_id em estruturas comuns dos webhooks WhatsApp Cloud."""
    ids: set[str] = set()
    if not isinstance(value, dict):
        return ids
    meta = value.get("metadata") or {}
    pid = _norm_graph_id(meta.get("phone_number_id"))
    if pid:
        ids.add(pid)
    pid = _norm_graph_id(value.get("phone_number_id"))
    if pid:
        ids.add(pid)
    for msg in value.get("messages") or []:
        if not isinstance(msg, dict):
            continue
        mm = msg.get("metadata") or {}
        pid = _norm_graph_id(mm.get("phone_number_id"))
        if pid:
            ids.add(pid)
    for st in value.get("statuses") or []:
        if not isinstance(st, dict):
            continue
        sm = st.get("metadata") or {}
        pid = _norm_graph_id(sm.get("phone_number_id"))
        if pid:
            ids.add(pid)
    return ids


def _extract_identifiers(data: dict) -> list[dict]:
    """
    Extrai todos os pares (waba_id, phone_number_id) presentes no payload.
    Retorna lista para suportar múltiplos entries no mesmo POST.
    """
    identifiers = []
    for entry in data.get("entry", []):
        waba_id = _norm_graph_id(entry.get("id"))
        phone_ids: set[str] = set()
        for change in entry.get("changes", []):
            value = change.get("value", {})
            if isinstance(value, dict):
                phone_ids |= _collect_phone_number_ids_from_value(value)
        identifiers.append({
            "waba_id": waba_id,
            "phone_number_ids": sorted(phone_ids),
        })
    return identifiers


def _instagram_ids_from_dados_extras(extras: dict | None) -> set[str]:
    extras = extras or {}
    ids: set[str] = set()
    for key in ('instagram_user_id', 'instagram_webhook_account_id'):
        value = _norm_graph_id(extras.get(key))
        if value:
            ids.add(value)
    return ids


def _extract_instagram_account_ids(data: dict) -> list[str]:
    """Extrai IG account ids (entry.id) do payload object=instagram."""
    seen: list[str] = []
    for entry in data.get('entry') or []:
        ig_id = _norm_graph_id(entry.get('id'))
        if ig_id and ig_id not in seen:
            seen.append(ig_id)
    return seen


def _build_provider_webhook_url(subdomain: str) -> str:
    """
    Constrói a URL do webhook do provedor a partir do subdomain.

    subdomain armazenado no Provedor é o domínio completo do tenant:
        ex. "e-tech.niohub.com.br"

    O backend do provedor responde no mesmo host (Traefik roteia /api/):
        https://e-tech.niohub.com.br/api/webhook/whatsapp-cloud/

    Se o subdomain não contiver ponto é tratado como label:
        "e-tech" → https://e-tech.niohub.com.br/api/webhook/whatsapp-cloud/
    """
    subdomain = subdomain.strip().lower().rstrip('/')
    if '.' not in subdomain:
        base_domain = getattr(settings, 'SUBDOMAIN_PRIMARY_DOMAINS', ['niohub.com.br'])
        if isinstance(base_domain, (list, tuple)):
            base_domain = base_domain[0]
        subdomain = f"{subdomain}.{base_domain}"
    return f"https://{subdomain}/api/webhook/whatsapp-cloud/"


def _find_provider_url(waba_id: str, phone_number_ids: list) -> str | None:
    """
    Busca o subdomain do provedor no banco do superadmin.
    Prioridade: phone_number_id > waba_id
    """
    canal = None
    waba_s = _norm_graph_id(waba_id) or ""
    phone_strs = [_norm_graph_id(p) for p in (phone_number_ids or [])]
    phone_strs = [p for p in phone_strs if p]

    base_qs = Canal.objects.filter(tipo="whatsapp_oficial").select_related("provedor")

    # 1. Tentar pelo phone_number_id (mais específico), canal ativo
    if phone_strs:
        canal = base_qs.filter(phone_number_id__in=phone_strs, ativo=True).first()
        if not canal:
            canal = base_qs.filter(phone_number_id__in=phone_strs).first()

    # 2. Fallback: tentar pelo waba_id (Graph pode enviar int; DB guarda como texto)
    if not canal and waba_s:
        canal = base_qs.filter(waba_id=waba_s, ativo=True).first()
        if not canal:
            canal = base_qs.filter(waba_id=waba_s).first()

    if canal and canal.provedor and canal.provedor.subdomain:
        url = _build_provider_webhook_url(canal.provedor.subdomain)
        logger.info(
            f"[Dispatcher] Provedor encontrado: {canal.provedor.nome} → {url} "
            f"(waba_id={waba_id}, phone_ids={phone_number_ids})"
        )
        return url

    logger.warning(
        f"[Dispatcher] Nenhum canal/provedor com subdomain encontrado para "
        f"waba_id={waba_id} phone_ids={phone_number_ids}"
    )
    return None


def upsert_instagram_canal(
    provedor,
    *,
    instagram_user_id: str,
    instagram_username: str = '',
    tenant_canal_id=None,
    canal_nome: str = 'Instagram',
    profile_picture_url: str = '',
):
    """
    Cria ou actualiza canal Instagram no superadmin para roteamento de webhooks.
    Reutilizado pelo channel-register (tenant) e pelo callback OAuth central.
    """
    instagram_user_id = _norm_graph_id(instagram_user_id) or ''
    if not instagram_user_id:
        raise ValueError('instagram_user_id é obrigatório')

    canal = Canal.objects.filter(
        provedor=provedor,
        tipo='instagram',
        dados_extras__instagram_user_id=instagram_user_id,
    ).first()
    if not canal and tenant_canal_id is not None:
        canal = Canal.objects.filter(
            provedor=provedor,
            tipo='instagram',
            dados_extras__tenant_canal_id=tenant_canal_id,
        ).first()
    if not canal:
        orphans = [
            c for c in Canal.objects.filter(provedor=provedor, tipo='instagram', ativo=True)
            if not _instagram_ids_from_dados_extras(c.dados_extras)
        ]
        if len(orphans) == 1:
            canal = orphans[0]
        elif tenant_canal_id is not None:
            for candidate in Canal.objects.filter(provedor=provedor, tipo='instagram'):
                if str((candidate.dados_extras or {}).get('tenant_canal_id') or '') == str(tenant_canal_id):
                    canal = candidate
                    break

    created = canal is None
    if created:
        canal = Canal(provedor=provedor, tipo='instagram', nome=canal_nome or 'Instagram')
    elif canal_nome:
        canal.nome = canal_nome

    dados_extras_update = {
        'instagram_user_id': instagram_user_id,
        'instagram_username': instagram_username,
        'tenant_canal_id': tenant_canal_id,
    }
    if profile_picture_url:
        dados_extras_update['profile_picture_url'] = profile_picture_url

    existing_extras = canal.dados_extras or {}
    existing_extras.update({k: v for k, v in dados_extras_update.items() if v not in (None, '')})
    canal.dados_extras = existing_extras
    canal.ativo = True
    canal.save()
    return canal, created


def _bind_instagram_webhook_id(canal: Canal, ig_account_id: str) -> None:
    """Persiste entry.id do webhook quando difere do user_id OAuth."""
    ig_account_id = _norm_graph_id(ig_account_id) or ''
    if not ig_account_id:
        return
    extras = dict(canal.dados_extras or {})
    known = _instagram_ids_from_dados_extras(extras)
    if ig_account_id in known:
        return
    extras['instagram_webhook_account_id'] = ig_account_id
    if not extras.get('instagram_user_id'):
        extras['instagram_user_id'] = ig_account_id
    canal.dados_extras = extras
    canal.save(update_fields=['dados_extras', 'updated_at'])
    logger.info(
        '[Dispatcher] Canal Instagram %s vinculado ao webhook ig_id=%s (provedor=%s)',
        canal.id,
        ig_account_id,
        canal.provedor.nome if canal.provedor else '?',
    )


def _find_provider_url_for_instagram(ig_account_ids: list[str]) -> str | None:
    """Busca tenant pelo instagram_user_id registado no channel-register."""
    if not ig_account_ids:
        return None
    targets = set(ig_account_ids)
    canais = list(Canal.objects.filter(tipo='instagram', ativo=True).select_related('provedor'))
    for canal in canais:
        if not canal.provedor or not canal.provedor.subdomain:
            continue
        known = _instagram_ids_from_dados_extras(canal.dados_extras)
        if known & targets:
            url = _build_provider_webhook_url(canal.provedor.subdomain)
            logger.info(
                '[Dispatcher] Provedor Instagram encontrado: %s → %s (ig_ids=%s, canal=%s)',
                canal.provedor.nome,
                url,
                sorted(targets),
                canal.id,
            )
            return url

    orphans = [c for c in canais if not _instagram_ids_from_dados_extras(c.dados_extras)]
    if len(orphans) == 1 and ig_account_ids:
        canal = orphans[0]
        if canal.provedor and canal.provedor.subdomain:
            _bind_instagram_webhook_id(canal, ig_account_ids[0])
            url = _build_provider_webhook_url(canal.provedor.subdomain)
            logger.info(
                '[Dispatcher] Provedor Instagram (auto-vínculo): %s → %s ig_id=%s canal=%s',
                canal.provedor.nome,
                url,
                ig_account_ids[0],
                canal.id,
            )
            return url

    known_channels = [
        {
            'canal_id': c.id,
            'provedor': c.provedor.nome if c.provedor else None,
            'instagram_user_id': (c.dados_extras or {}).get('instagram_user_id'),
            'instagram_webhook_account_id': (c.dados_extras or {}).get('instagram_webhook_account_id'),
        }
        for c in canais
    ]
    logger.warning(
        '[Dispatcher] Nenhum canal/provedor Instagram para ig_ids=%s. Canais activos: %s',
        ig_account_ids,
        known_channels,
    )
    return None


def _forward_to_provider(provider_url: str, raw_body: bytes, headers: dict):
    """
    Encaminha o payload original para o provedor.
    Executado em background thread para não bloquear a resposta para a Meta.
    """
    try:
        forward_headers = {
            "Content-Type": "application/json",
        }
        # Repassa a assinatura original para que o provedor também possa validar
        if "X-Hub-Signature-256" in headers:
            forward_headers["X-Hub-Signature-256"] = headers["X-Hub-Signature-256"]
        if "X-Hub-Signature" in headers:
            forward_headers["X-Hub-Signature"] = headers["X-Hub-Signature"]

        resp = requests.post(
            provider_url,
            data=raw_body,
            headers=forward_headers,
            timeout=15,
            verify=True
        )
        logger.info(f"[Dispatcher] Forward para {provider_url} → HTTP {resp.status_code}")
    except requests.exceptions.Timeout:
        logger.warning(f"[Dispatcher] Timeout ao encaminhar para {provider_url}")
    except Exception as e:
        logger.error(f"[Dispatcher] Erro ao encaminhar para {provider_url}: {e}")


def _dispatch_webhook_payload(data: dict, raw_body: bytes, req_headers: dict) -> None:
    """Encaminha payload WhatsApp ou Instagram para o(s) tenant(s) correto(s)."""
    obj_type = data.get('object')
    forwarded: set[str] = set()

    if obj_type == 'whatsapp_business_account':
        for ident in _extract_identifiers(data):
            url = _find_provider_url(ident['waba_id'], ident['phone_number_ids'])
            if url and url not in forwarded:
                forwarded.add(url)
                _forward_to_provider(url, raw_body, req_headers)
            elif not url:
                logger.warning(
                    '[Dispatcher] Provedor WhatsApp não encontrado waba_id=%s phone_ids=%s',
                    ident['waba_id'],
                    ident['phone_number_ids'],
                )
        return

    if obj_type == 'instagram':
        ig_ids = _extract_instagram_account_ids(data)
        url = _find_provider_url_for_instagram(ig_ids)
        if url:
            _forward_to_provider(url, raw_body, req_headers)
        elif ig_ids:
            logger.warning('[Dispatcher] Provedor Instagram não encontrado ig_ids=%s', ig_ids)
        else:
            logger.warning('[Dispatcher] Payload Instagram sem entry.id')
        return

    logger.info('[Dispatcher] object ignorado: %r', obj_type)


@csrf_exempt
@require_http_methods(["GET", "POST"])
def whatsapp_dispatcher(request):
    """
    Endpoint central de webhook da Meta.

    GET  → Verificação (challenge) do webhook
    POST → Receber eventos e encaminhar para o provedor correto
    """
    # ─── GET: Verificação do webhook ───────────────────────────────────────────
    if request.method == "GET":
        # A Meta usa hub.mode / hub.verify_token / hub.challenge; proxies ou clientes
        # antigos podem enviar hub_mode / hub_verify_token / hub_challenge.
        mode = (request.GET.get("hub.mode") or request.GET.get("hub_mode") or "").strip()
        token = (request.GET.get("hub.verify_token") or request.GET.get("hub_verify_token") or "").strip()
        challenge = request.GET.get("hub.challenge") or request.GET.get("hub_challenge") or ""

        if mode.lower() != "subscribe":
            logger.warning("[Dispatcher] GET webhook: mode inválido (%r)", mode)
            return JsonResponse({"error": "Invalid mode"}, status=403)

        expected_token = (getattr(settings, "WHATSAPP_WEBHOOK_VERIFY_TOKEN", None) or "").strip()
        if not expected_token:
            logger.error(
                "[Dispatcher] WHATSAPP_WEBHOOK_VERIFY_TOKEN vazio no settings — "
                "verificação do webhook impossível."
            )
            return JsonResponse({"error": "Verification failed"}, status=403)

        if token != expected_token:
            logger.warning(
                "[Dispatcher] GET webhook: verify_token não confere (esperado len=%s recebido len=%s).",
                len(expected_token),
                len(token),
            )
            return JsonResponse({"error": "Verification failed"}, status=403)

        return HttpResponse(str(challenge), content_type="text/plain", status=200)

    # ─── POST: Receber eventos ──────────────────────────────────────────────────
    raw_body = request.body
    signature = (
        request.headers.get('X-Hub-Signature-256') or
        request.headers.get('X-Hub-Signature', '')
    )
    is_dev = getattr(settings, 'DEBUG', False)
    skip_sig = os.environ.get('SKIP_WEBHOOK_SIGNATURE', '').lower() in ('1', 'true', 'yes')

    # Validar assinatura
    if skip_sig:
        logger.warning("[Dispatcher] SKIP_WEBHOOK_SIGNATURE=true — validação desactivada!")
    elif signature:
        if not _verify_signature(raw_body, signature):
            if not is_dev:
                return JsonResponse({"error": "Invalid signature"}, status=403)
            logger.warning("[Dispatcher] Assinatura inválida mas DEBUG=True — a continuar.")
    else:
        if not is_dev:
            logger.warning("[Dispatcher] POST sem assinatura rejeitado.")
            return JsonResponse({"error": "Missing signature"}, status=403)

    # ─── ACK imediato para a Meta ──────────────────────────────────────────────
    # A Meta exige resposta em poucos segundos. Respondemos aqui e
    # processamos o forward em background para não ter timeout.
    try:
        data = json.loads(raw_body)
    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON"}, status=400)

    obj_type = data.get('object')
    if obj_type not in ('whatsapp_business_account', 'instagram'):
        return JsonResponse({"status": "ignored", "object": obj_type}, status=200)

    req_headers = dict(request.headers)

    def dispatch():
        _dispatch_webhook_payload(data, raw_body, req_headers)

    thread = threading.Thread(target=dispatch, daemon=True)
    thread.start()

    return JsonResponse({"status": "ok"}, status=200)


@csrf_exempt
def dispatcher_status(request):
    """
    GET /api/webhook/whatsapp-cloud/status/
    Lista todos os canais WhatsApp registados e as URLs de destino.
    Protegido por ADMIN_WEBHOOK_SECRET no header X-Admin-Secret.
    """
    if request.method != "GET":
        return JsonResponse({"error": "Method not allowed"}, status=405)

    secret = request.headers.get("X-Admin-Secret", "")
    expected = getattr(settings, "ADMIN_WEBHOOK_SECRET", "")
    if not expected or secret != expected:
        return JsonResponse({"error": "Unauthorized"}, status=403)

    canais = Canal.objects.filter(
        tipo__in=('whatsapp_oficial', 'instagram'),
        ativo=True,
    ).select_related('provedor').order_by('provedor__nome', 'tipo', 'nome')

    result = []
    for c in canais:
        subdomain = c.provedor.subdomain if c.provedor else None
        webhook_url = _build_provider_webhook_url(subdomain) if subdomain else None
        extras = c.dados_extras or {}
        item = {
            "canal_id": c.id,
            "canal_nome": c.nome,
            "tipo": c.tipo,
            "provedor": c.provedor.nome if c.provedor else None,
            "subdomain": subdomain,
            "webhook_destino": webhook_url,
        }
        if c.tipo == 'whatsapp_oficial':
            item.update({
                "waba_id": c.waba_id,
                "phone_number_id": c.phone_number_id,
                "phone_number": c.phone_number,
            })
        else:
            item.update({
                "instagram_user_id": extras.get('instagram_user_id'),
                "instagram_username": extras.get('instagram_username'),
                "tenant_canal_id": extras.get('tenant_canal_id'),
            })
        result.append(item)

    return JsonResponse({"canais": result, "total": len(result)})


@csrf_exempt
def provider_channel_register(request):
    """
    Endpoint chamado pelo painel do provedor quando um canal WhatsApp
    é conectado. Salva o waba_id e phone_number_id no superadmin para
    que o dispatcher saiba para onde encaminhar os webhooks.

    POST /api/webhooks/provider/channel-register/
    Body:
    {
        "secret": "<ADMIN_WEBHOOK_SECRET>",
        "provedor_id": 7,
        "waba_id": "3052659568268187",
        "phone_number_id": "123456789",
        "phone_number": "+55 94 3198-1266",
        "canal_nome": "DISPARO",
        "tipo": "whatsapp_oficial"
    }
    """
    if request.method != "POST":
        return JsonResponse({"error": "Method not allowed"}, status=405)

    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON"}, status=400)

    provedor_id = data.get("provedor_id")
    waba_id = data.get("waba_id", "").strip()
    phone_number_id = data.get("phone_number_id", "").strip()
    phone_number = data.get("phone_number", "").strip()
    canal_nome = data.get("canal_nome", "WhatsApp").strip()
    tipo = data.get("tipo", "whatsapp_oficial").strip()
    profile_picture_url = data.get("profile_picture_url", "").strip()
    business_name = data.get("business_name", "").strip()
    instagram_user_id = data.get("instagram_user_id", "").strip()
    instagram_username = data.get("instagram_username", "").strip()
    tenant_canal_id = data.get("tenant_canal_id")

    if tipo == "instagram":
        if not provedor_id or not instagram_user_id:
            return JsonResponse(
                {"error": "provedor_id e instagram_user_id são obrigatórios para Instagram"},
                status=400,
            )
    elif not provedor_id or not waba_id:
        return JsonResponse({"error": "provedor_id e waba_id são obrigatórios"}, status=400)

    try:
        from .models import Provedor
        provedor = Provedor.objects.get(id=provedor_id)
    except Provedor.DoesNotExist:
        return JsonResponse({"error": "Provedor não encontrado"}, status=404)

    # Validar token (Bearer) com fallback para secret legado
    auth = request.headers.get("Authorization", "")
    bearer = ""
    if auth.lower().startswith("bearer "):
        bearer = auth.split(" ", 1)[1].strip()

    provider_token = (provedor.integration_token or "").strip()
    if not provider_token:
        logger.error("[ChannelRegister] Provedor sem integration_token configurado.")
        return JsonResponse({"error": "Server misconfigured"}, status=500)

    if not bearer or bearer != provider_token:
        logger.warning("[ChannelRegister] Bearer token inválido recebido.")
        return JsonResponse({"error": "Unauthorized"}, status=403)

    provedor.integration_token_last_used_at = timezone.now()
    provedor.save(update_fields=["integration_token_last_used_at"])

    if tipo == "instagram":
        try:
            canal, created = upsert_instagram_canal(
                provedor,
                instagram_user_id=instagram_user_id,
                instagram_username=instagram_username,
                tenant_canal_id=tenant_canal_id,
                canal_nome=canal_nome,
                profile_picture_url=profile_picture_url,
            )
        except ValueError as exc:
            return JsonResponse({"error": str(exc)}, status=400)

        action = "criado" if created else "atualizado"
        logger.info(
            f"[ChannelRegister] Canal Instagram {action}: {canal.nome} "
            f"(provedor={provedor.nome}, ig_id={instagram_user_id})"
        )
        return JsonResponse({
            "status": "ok",
            "canal_id": canal.id,
            "action": action,
        })

    # Montar dados_extras com perfil do WhatsApp
    dados_extras_update = {}
    if profile_picture_url:
        dados_extras_update["profile_picture_url"] = profile_picture_url
        dados_extras_update["profilePicUrl"] = profile_picture_url
    if business_name:
        dados_extras_update["business_name"] = business_name

    # Criar ou atualizar o canal no superadmin
    canal, created = Canal.objects.update_or_create(
        provedor=provedor,
        tipo=tipo,
        waba_id=waba_id,
        defaults={
            "nome": canal_nome,
            "phone_number": phone_number,
            "phone_number_id": phone_number_id,
            "ativo": True,
        }
    )

    # Mesclar dados_extras sem sobrescrever campos existentes
    if dados_extras_update:
        existing_extras = canal.dados_extras or {}
        existing_extras.update(dados_extras_update)
        canal.dados_extras = existing_extras
        canal.save(update_fields=["dados_extras"])

    action = "criado" if created else "atualizado"
    logger.info(
        f"[ChannelRegister] Canal {action}: {canal_nome} "
        f"(provedor={provedor.nome}, waba_id={waba_id})"
    )

    return JsonResponse({
        "status": "ok",
        "canal_id": canal.id,
        "action": action
    })
