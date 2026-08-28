"""Tools ACS/TR-069 — consultar e alterar Wi-Fi (SSID/senha)."""

from __future__ import annotations

import logging
import re
from typing import Any, Dict, Optional, Tuple

from core.acs_client import ACSClient, ACSError

logger = logging.getLogger(__name__)

# Política pedida: no máximo 8 caracteres, com maiúscula, minúscula e especial.
WIFI_PASS_MAX_LEN = 8
_SPECIAL_RE = re.compile(r"[^A-Za-z0-9]")


def _acs_configured(provedor) -> bool:
    ext = getattr(provedor, "integracoes_externas", None) or {}
    return bool((ext.get("acs_url") or "").strip() and (ext.get("acs_token") or "").strip())


def _load_conversation_state(provedor, conversation_id, contexto: Optional[dict]) -> dict:
    if not conversation_id or not provedor:
        return {}
    try:
        from core.redis_memory_service import redis_memory_service

        ctx = contexto or {}
        channel = redis_memory_service.normalize_channel(ctx.get("canal") or "whatsapp")
        contact = ctx.get("contact")
        phone = ""
        if contact is not None:
            phone = getattr(contact, "phone", None) or ""
        phone = phone or ctx.get("contact_phone") or ""
        return (
            redis_memory_service.get_ai_state_sync(
                provedor.id, conversation_id, channel, phone
            )
            or {}
        )
    except Exception as exc:
        logger.warning("[ACS tool] falha ao ler estado: %s", exc)
        return {}


def _resolve_ids(
    arguments: Optional[dict],
    contexto: Optional[dict],
    state: Optional[dict] = None,
) -> Tuple[str, str]:
    args = arguments or {}
    ctx = contexto or {}
    st = state or {}
    login = (
        str(args.get("login") or args.get("pppoe") or args.get("pppoe_login") or "").strip()
        or str(st.get("pppoe_login") or st.get("servico_login") or st.get("login") or "").strip()
        or str(ctx.get("pppoe_login") or ctx.get("login_pppoe") or ctx.get("login") or "").strip()
    )
    device_id = str(
        args.get("device_id") or st.get("device_id") or ctx.get("device_id") or ""
    ).strip()
    return login, device_id


def validate_wifi_password(password: str) -> Optional[str]:
    """
    Retorna mensagem de erro se inválida, ou None se ok.
    Regra: no máximo 8 caracteres; maiúscula + minúscula + caractere especial.
    """
    pwd = str(password or "")
    if not pwd:
        return "Senha vazia."
    if len(pwd) > WIFI_PASS_MAX_LEN:
        return f"A senha deve ter no máximo {WIFI_PASS_MAX_LEN} caracteres."
    if not re.search(r"[A-Z]", pwd):
        return "A senha deve conter pelo menos uma letra maiúscula."
    if not re.search(r"[a-z]", pwd):
        return "A senha deve conter pelo menos uma letra minúscula."
    if not _SPECIAL_RE.search(pwd):
        return "A senha deve conter pelo menos um caractere especial (ex.: @ # ! $ %)."
    return None


def _slim_hosts(hosts) -> list:
    out = []
    if not isinstance(hosts, list):
        return out
    for h in hosts[:12]:
        if not isinstance(h, dict):
            continue
        out.append(
            {
                "hostname": h.get("hostname") or "",
                "ip": h.get("ip") or "",
                "mac": h.get("mac") or "",
                "interface": h.get("interface") or "",
                "status": h.get("status") or "",
            }
        )
    return out


def _slim_snapshot(data: dict) -> dict:
    return {
        "success": True,
        "device_id": data.get("device_id"),
        "serial": data.get("serial"),
        "manufacturer": data.get("manufacturer"),
        "product_class": data.get("product_class"),
        "is_online": data.get("is_online"),
        "wifi_ssid": data.get("wifi_ssid"),
        "wifi_ssid_5g": data.get("wifi_ssid_5g"),
        "wifi_pass_24": data.get("wifi_pass_24") or None,
        "wifi_pass_5g": data.get("wifi_pass_5g") or None,
        "pppoe_user": data.get("pppoe_user"),
        "wan_ip": data.get("wan_ip"),
        "rx_power": data.get("rx_power"),
        "online_hosts_count": data.get("online_hosts_count"),
        "hosts_resumo": _slim_hosts(data.get("hosts")),
        "nota": (
            "Snapshot do equipamento. Informe SSID ao cliente com suas palavras. "
            "Nao mencione ACS, TR-069 nem device_id."
        ),
    }


def _fetch_wifi(client: ACSClient, login: str, device_id: str) -> dict:
    if login and device_id:
        try:
            return client.get_wifi_by_login(login)
        except ACSError:
            return client.get_wifi_by_device_id(device_id)
    if login:
        return client.get_wifi_by_login(login)
    return client.get_wifi_by_device_id(device_id)


def _apply_wifi(client: ACSClient, login: str, device_id: str, **changes) -> dict:
    if login and device_id:
        try:
            return client.set_wifi_by_login(login, **changes)
        except ACSError:
            return client.set_wifi_by_device_id(device_id, **changes)
    if login:
        return client.set_wifi_by_login(login, **changes)
    return client.set_wifi_by_device_id(device_id, **changes)


def _need_cliente_nota() -> dict:
    return {
        "success": False,
        "erro": "Cliente ainda nao identificado ou sem login PPPoE no cadastro.",
        "precisa_cpf": True,
        "nota": (
            "Fluxo obrigatorio: 1) peca CPF/CNPJ; 2) chame buscar_cliente; "
            "3) use o pppoe_login retornado/salvo no estado; "
            "4) so entao consulte/altere o Wi-Fi. Nao peca o login PPPoE ao cliente."
        ),
    }


def consultar_wifi_acs(
    *, provedor, arguments=None, contexto=None, conversation_id=None, **_kw
) -> Dict[str, Any]:
    """Consulta SSID/status Wi-Fi do CPE via ACS."""
    if not _acs_configured(provedor):
        return {
            "success": False,
            "erro": "Integração ACS não configurada neste provedor.",
            "nota": "Não mencione ACS ao cliente. Peça para falar com o suporte humano se precisar alterar Wi-Fi.",
        }

    state = _load_conversation_state(provedor, conversation_id, contexto)
    login, device_id = _resolve_ids(arguments, contexto, state)
    if not login and not device_id:
        return _need_cliente_nota()

    client = ACSClient.from_provedor(provedor)
    try:
        data = _fetch_wifi(client, login, device_id)
        slim = _slim_snapshot(data if isinstance(data, dict) else {})
        slim["login_usado"] = login or None
        return slim
    except ACSError as exc:
        logger.warning("[ACS tool] consultar_wifi falhou login=%s: %s", login or "-", exc)
        if exc.status_code == 404:
            return {
                "success": False,
                "erro": "Nenhum equipamento encontrado para o login do cadastro.",
                "nao_encontrado": True,
                "nota": "Confirme o cadastro (CPF) com o cliente. Não mencione ACS.",
            }
        return {
            "success": False,
            "erro": str(exc),
            "nota": "Falha ao consultar o modem. Ofereça tentar de novo ou transferir para suporte.",
        }


def alterar_wifi_acs(
    *, provedor, arguments=None, contexto=None, conversation_id=None, **_kw
) -> Dict[str, Any]:
    """Altera SSID e/ou senha Wi-Fi (2.4 / 5 GHz) via ACS/TR-069."""
    if not _acs_configured(provedor):
        return {
            "success": False,
            "erro": "Integração ACS não configurada neste provedor.",
            "nota": "Não mencione ACS ao cliente. Transfira para suporte humano se precisar alterar Wi-Fi.",
        }

    args = arguments or {}
    state = _load_conversation_state(provedor, conversation_id, contexto)
    login, device_id = _resolve_ids(args, contexto, state)
    if not login and not device_id:
        return _need_cliente_nota()

    ssid_24 = args.get("ssid_24") or args.get("nome_wifi_24") or args.get("ssid")
    ssid_5 = args.get("ssid_5") or args.get("nome_wifi_5") or args.get("ssid_5g")
    pass_24 = args.get("pass_24") or args.get("senha_24") or args.get("senha_wifi_24")
    pass_5 = args.get("pass_5") or args.get("senha_5") or args.get("senha_wifi_5") or args.get("senha_5g")
    band = args.get("band")

    if ssid_24 and not ssid_5 and str(args.get("aplicar_nas_duas") or "").lower() in (
        "1",
        "true",
        "sim",
        "both",
        "ambas",
    ):
        ssid_5 = ssid_24
        band = band or "both"

    # Validar senhas antes de enviar ao ACS
    for label, pwd in (("2.4 GHz", pass_24), ("5 GHz", pass_5)):
        if pwd is None or str(pwd) == "":
            continue
        err = validate_wifi_password(str(pwd))
        if err:
            return {
                "success": False,
                "erro": f"Senha {label} inválida: {err}",
                "senha_invalida": True,
                "regra_senha": (
                    f"No máximo {WIFI_PASS_MAX_LEN} caracteres, "
                    "com letra maiúscula, minúscula e um caractere especial."
                ),
                "nota": (
                    "Peça uma nova senha ao cliente seguindo a regra "
                    f"(máx. {WIFI_PASS_MAX_LEN} caracteres, maiúscula, minúscula e especial). "
                    "Uma pergunta por mensagem."
                ),
            }

    changes = {}
    if band is not None and str(band).strip() != "":
        changes["band"] = str(band).strip()
    if ssid_24 is not None and str(ssid_24).strip() != "":
        changes["ssid_24"] = str(ssid_24).strip()
    if ssid_5 is not None and str(ssid_5).strip() != "":
        changes["ssid_5"] = str(ssid_5).strip()
    if pass_24 is not None and str(pass_24) != "":
        changes["pass_24"] = str(pass_24)
    if pass_5 is not None and str(pass_5) != "":
        changes["pass_5"] = str(pass_5)

    if not any(k in changes for k in ("ssid_24", "ssid_5", "pass_24", "pass_5")):
        return {
            "success": False,
            "erro": "Informe o novo nome (ssid_24/ssid_5) e/ou senha (pass_24/pass_5).",
            "nota": (
                "Se o cliente quer trocar o NOME: peça o novo nome e a banda (2.4, 5G ou ambas). "
                "Se quer trocar a SENHA: peça a senha (máx. 8 caracteres, maiúscula, minúscula e especial) "
                "e a banda. Uma pergunta por mensagem."
            ),
        }

    if "band" not in changes:
        has_24 = "ssid_24" in changes or "pass_24" in changes
        has_5 = "ssid_5" in changes or "pass_5" in changes
        if has_24 and has_5:
            changes["band"] = "both"
        elif has_5:
            changes["band"] = "5"
        elif has_24:
            changes["band"] = "24"

    client = ACSClient.from_provedor(provedor)
    try:
        result = _apply_wifi(client, login, device_id, **changes)
        alteracoes = {k: ("***" if k.startswith("pass_") else v) for k, v in changes.items()}
        msg = ""
        if isinstance(result, dict):
            msg = result.get("message") or ""
        return {
            "success": True,
            "enfileirado": True,
            "message": msg or "Tarefa enfileirada. Aguarde o modem processar.",
            "alteracoes": alteracoes,
            "login_usado": login or None,
            "nota": (
                "Alteração enfileirada. O modem aplica em alguns minutos. "
                "Avise o cliente para reconectar os aparelhos. Não mencione ACS/TR-069."
            ),
        }
    except ACSError as exc:
        logger.warning("[ACS tool] alterar_wifi falhou login=%s: %s", login or "-", exc)
        if exc.status_code == 404:
            return {
                "success": False,
                "erro": "Nenhum equipamento encontrado para o login do cadastro.",
                "nao_encontrado": True,
                "nota": "Confirme o CPF/cadastro. Não mencione ACS.",
            }
        if exc.status_code == 422:
            return {
                "success": False,
                "erro": str(exc),
                "sem_alteracao": True,
                "nota": (
                    "Nenhuma alteração aplicada (valores iguais ou inválidos). "
                    "Confirme o novo nome/senha com o cliente."
                ),
            }
        return {
            "success": False,
            "erro": str(exc),
            "nota": "Não foi possível alterar o Wi-Fi agora. Ofereça tentar de novo ou transferir.",
        }
