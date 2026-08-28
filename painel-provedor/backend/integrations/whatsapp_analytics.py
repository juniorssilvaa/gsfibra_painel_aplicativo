"""
Proxy de analytics da Meta WhatsApp Cloud API (WABA).

Docs: https://developers.facebook.com/documentation/business-messaging/whatsapp/analytics

Campos:
- analytics              → volume diário + templates vs sessão
- pricing_analytics      → custo/volume por categoria (pode falhar sem permissão)
- conversation_analytics → fallback de custo/categorias
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

import requests
from rest_framework import permissions, status
from rest_framework.authentication import TokenAuthentication
from rest_framework.response import Response
from rest_framework.views import APIView

from core.models import Canal, Provedor
from integrations.meta_oauth import PHONE_NUMBERS_API_VERSION

logger = logging.getLogger(__name__)

PAID_PRICING_TYPES = {"REGULAR"}
FREE_PRICING_TYPES = {"FREE_CUSTOMER_SERVICE", "FREE_ENTRY_POINT"}
FREE_CONVERSATION_TYPES = {"FREE_TIER", "FREE_ENTRY_POINT"}

CATEGORY_LABELS_PT = {
    "AUTHENTICATION": "Autenticação",
    "AUTHENTICATION_INTERNATIONAL": "Autenticação internacional",
    "MARKETING": "Marketing",
    "MARKETING_LITE": "Marketing Lite",
    "UTILITY": "Utilidade",
    "SERVICE": "Serviço (janela)",
    "REFERRAL_CONVERSION": "Entrada gratuita",
    "TEMPLATES": "Templates (pagas)",
    "SESSION": "Sessão (gratuitas)",
}


def _unix(dt: datetime) -> int:
    return int(dt.timestamp())


def _parse_period(days: int) -> Tuple[int, int]:
    end = datetime.now(timezone.utc)
    start = end - timedelta(days=max(1, min(int(days or 30), 365)))
    return _unix(start), _unix(end)


def _graph_get(waba_id: str, token: str, fields: str, timeout: int = 45) -> Dict[str, Any]:
    url = f"https://graph.facebook.com/{PHONE_NUMBERS_API_VERSION}/{waba_id}"
    resp = requests.get(
        url,
        params={"fields": fields},
        headers={"Authorization": f"Bearer {token}"},
        timeout=timeout,
    )
    data: Dict[str, Any] = {}
    try:
        data = resp.json() if resp.content else {}
    except Exception:
        data = {"raw": (resp.text or "")[:500]}
    if resp.status_code >= 400:
        err = (data.get("error") or {}) if isinstance(data, dict) else {}
        msg = err.get("message") or data.get("raw") or f"HTTP {resp.status_code}"
        raise RuntimeError(msg)
    return data if isinstance(data, dict) else {}


def _flatten_nested_points(payload: Dict[str, Any], root_key: str) -> List[Dict[str, Any]]:
    root = payload.get(root_key) or {}
    rows: List[Dict[str, Any]] = []
    for block in root.get("data") or []:
        for pt in block.get("data_points") or []:
            if isinstance(pt, dict):
                rows.append(pt)
    return rows


def _flatten_messaging_points(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    root = payload.get("analytics") or {}
    return [pt for pt in (root.get("data_points") or []) if isinstance(pt, dict)]


def _series_from_messaging(points: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    series = []
    for pt in sorted(points, key=lambda p: int(p.get("start") or 0)):
        start = int(pt.get("start") or 0)
        series.append(
            {
                "start": start,
                "date": datetime.fromtimestamp(start, tz=timezone.utc).strftime("%Y-%m-%d"),
                "label": datetime.fromtimestamp(start, tz=timezone.utc).strftime("%d/%m"),
                "sent": int(pt.get("sent") or 0),
                "delivered": int(pt.get("delivered") or 0),
            }
        )
    return series


def _merge_daily_series(
    all_pts: List[Dict[str, Any]],
    tpl_pts: List[Dict[str, Any]],
    sess_pts: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    by_day: Dict[str, Dict[str, Any]] = {}

    def ensure(row: Dict[str, Any]) -> Dict[str, Any]:
        day = row["date"]
        return by_day.setdefault(
            day,
            {
                "date": day,
                "label": row["label"],
                "start": row["start"],
                "sent": 0,
                "delivered": 0,
                "templates": 0,
                "session": 0,
            },
        )

    for row in _series_from_messaging(all_pts):
        bucket = ensure(row)
        bucket["sent"] = row["sent"]
        bucket["delivered"] = row["delivered"]

    for row in _series_from_messaging(tpl_pts):
        ensure(row)["templates"] = row["sent"]

    for row in _series_from_messaging(sess_pts):
        ensure(row)["session"] = row["sent"]

    return [by_day[k] for k in sorted(by_day.keys())]


def _aggregate_pricing(points: List[Dict[str, Any]]) -> Dict[str, Any]:
    free_volume = 0
    paid_volume = 0
    total_cost = 0.0
    charged_volume = 0
    by_category: Dict[str, Dict[str, float]] = {}

    for pt in points:
        volume = int(pt.get("volume") or 0)
        cost = float(pt.get("cost") or 0)
        ptype = (pt.get("pricing_type") or "").upper()
        category = (pt.get("pricing_category") or "UNKNOWN").upper()

        total_cost += cost
        if ptype in FREE_PRICING_TYPES or category == "SERVICE":
            free_volume += volume
        elif ptype in PAID_PRICING_TYPES:
            paid_volume += volume
            charged_volume += volume
        else:
            if cost > 0:
                paid_volume += volume
                charged_volume += volume
            else:
                free_volume += volume

        bucket = by_category.setdefault(category, {"volume": 0, "cost": 0.0})
        bucket["volume"] += volume
        bucket["cost"] += cost

    return {
        "messages_free": free_volume,
        "messages_paid": paid_volume,
        "charged_volume": charged_volume,
        "approximate_cost": round(total_cost, 4),
        "by_category": _categories_list(by_category),
        "cost_available": True,
        "source": "pricing_analytics",
    }


def _aggregate_conversation(points: List[Dict[str, Any]]) -> Dict[str, Any]:
    free_volume = 0
    paid_volume = 0
    total_cost = 0.0
    charged_volume = 0
    by_category: Dict[str, Dict[str, float]] = {}
    cost_seen = False

    for pt in points:
        volume = int(pt.get("conversation") or 0)
        cost = float(pt.get("cost") or 0)
        if "cost" in pt:
            cost_seen = True
        ctype = (pt.get("conversation_type") or "").upper()
        category = (pt.get("conversation_category") or "UNKNOWN").upper()

        total_cost += cost
        if ctype in FREE_CONVERSATION_TYPES:
            free_volume += volume
        else:
            paid_volume += volume
            if cost > 0 or ctype == "REGULAR":
                charged_volume += volume

        bucket = by_category.setdefault(category, {"volume": 0, "cost": 0.0})
        bucket["volume"] += volume
        bucket["cost"] += cost

    return {
        "messages_free": free_volume,
        "messages_paid": paid_volume,
        "charged_volume": charged_volume or paid_volume,
        "approximate_cost": round(total_cost, 4),
        "by_category": _categories_list(by_category),
        "cost_available": cost_seen and total_cost > 0,
        "source": "conversation_analytics",
    }


def _categories_list(by_category: Dict[str, Dict[str, float]]) -> List[Dict[str, Any]]:
    return [
        {
            "key": key,
            "label": CATEGORY_LABELS_PT.get(key, key.replace("_", " ").title()),
            "volume": int(vals["volume"]),
            "cost": round(float(vals["cost"]), 4),
        }
        for key, vals in sorted(
            by_category.items(),
            key=lambda x: (-x[1]["cost"], -x[1]["volume"]),
        )
        if vals["volume"] or vals["cost"]
    ]


def _synthetic_categories(free: int, paid: int) -> List[Dict[str, Any]]:
    rows = []
    if paid:
        rows.append(
            {
                "key": "TEMPLATES",
                "label": CATEGORY_LABELS_PT["TEMPLATES"],
                "volume": int(paid),
                "cost": 0.0,
            }
        )
    if free:
        rows.append(
            {
                "key": "SESSION",
                "label": CATEGORY_LABELS_PT["SESSION"],
                "volume": int(free),
                "cost": 0.0,
            }
        )
    return rows


def _aggregate_messaging(points: List[Dict[str, Any]]) -> Dict[str, int]:
    sent = sum(int(p.get("sent") or 0) for p in points)
    delivered = sum(int(p.get("delivered") or 0) for p in points)
    return {"sent": sent, "delivered": delivered}


class WhatsAppAnalyticsView(APIView):
    """GET /api/whatsapp/analytics/?days=30&channel_id=optional&provedor_id=optional"""

    authentication_classes = [TokenAuthentication]
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        user = request.user
        days = request.query_params.get("days") or "30"
        try:
            days_int = int(days)
        except (TypeError, ValueError):
            days_int = 30

        channel_id = request.query_params.get("channel_id")
        provedor_id = request.query_params.get("provedor_id")

        try:
            canal = self._resolve_canal(user, channel_id, provedor_id)
        except PermissionError as exc:
            return Response({"success": False, "error": str(exc)}, status=status.HTTP_403_FORBIDDEN)
        except Canal.DoesNotExist:
            return Response(
                {
                    "success": False,
                    "error": "Nenhum canal WhatsApp Oficial conectado. Conecte em Canais.",
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        if not canal.waba_id or not canal.token:
            return Response(
                {
                    "success": False,
                    "error": "Canal sem WABA ID ou token. Reconecte o WhatsApp Oficial.",
                    "channel": {"id": canal.id, "nome": canal.nome},
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        start_ts, end_ts = _parse_period(days_int)

        pricing_summary: Optional[Dict[str, Any]] = None
        messaging_all = {"sent": 0, "delivered": 0}
        messaging_templates = {"sent": 0, "delivered": 0}
        messaging_session = {"sent": 0, "delivered": 0}
        all_pts: List[Dict[str, Any]] = []
        tpl_pts: List[Dict[str, Any]] = []
        sess_pts: List[Dict[str, Any]] = []
        cost_note: Optional[str] = None

        # 1) pricing_analytics (preferido para custo)
        try:
            pricing_fields = (
                f"pricing_analytics.start({start_ts}).end({end_ts})"
                f".granularity(DAILY)"
                f'.dimensions(["PRICING_CATEGORY","PRICING_TYPE"])'
                f'.metric_types(["COST","VOLUME"])'
            )
            pricing_raw = _graph_get(canal.waba_id, canal.token, pricing_fields)
            pricing_summary = _aggregate_pricing(_flatten_nested_points(pricing_raw, "pricing_analytics"))
        except Exception as exc:
            logger.info("[WA Analytics] pricing_analytics indisponível: %s", exc)

        # 2) conversation_analytics (fallback custo/categoria)
        if not pricing_summary or not pricing_summary.get("by_category"):
            try:
                conv_fields = (
                    f"conversation_analytics.start({start_ts}).end({end_ts})"
                    f".granularity(DAILY)"
                    f'.dimensions(["CONVERSATION_CATEGORY","CONVERSATION_TYPE"])'
                )
                conv_raw = _graph_get(canal.waba_id, canal.token, conv_fields)
                conv_summary = _aggregate_conversation(
                    _flatten_nested_points(conv_raw, "conversation_analytics")
                )
                if not pricing_summary:
                    pricing_summary = conv_summary
                elif not pricing_summary.get("by_category") and conv_summary.get("by_category"):
                    pricing_summary["by_category"] = conv_summary["by_category"]
                    if conv_summary.get("approximate_cost"):
                        pricing_summary["approximate_cost"] = conv_summary["approximate_cost"]
                        pricing_summary["cost_available"] = conv_summary.get("cost_available", False)
                        pricing_summary["source"] = "conversation_analytics"
            except Exception as exc:
                logger.info("[WA Analytics] conversation_analytics indisponível: %s", exc)

        if pricing_summary is None:
            pricing_summary = {
                "messages_free": 0,
                "messages_paid": 0,
                "charged_volume": 0,
                "approximate_cost": 0.0,
                "by_category": [],
                "cost_available": False,
                "source": "messaging",
            }
            cost_note = (
                "O gasto em dinheiro não está disponível neste token/WABA "
                "(comum em contas faturadas pelo parceiro Meta). "
                "Os volumes de mensagens abaixo vêm da API oficial."
            )

        # 3) messaging analytics + séries diárias
        try:
            msg_fields = f"analytics.start({start_ts}).end({end_ts}).granularity(DAY)"
            msg_raw = _graph_get(canal.waba_id, canal.token, msg_fields)
            all_pts = _flatten_messaging_points(msg_raw)
            messaging_all = _aggregate_messaging(all_pts)
        except Exception as exc:
            logger.warning("[WA Analytics] analytics falhou: %s", exc)

        try:
            tpl_fields = (
                f"analytics.start({start_ts}).end({end_ts}).granularity(DAY)"
                f".product_types([0])"
            )
            tpl_raw = _graph_get(canal.waba_id, canal.token, tpl_fields)
            tpl_pts = _flatten_messaging_points(tpl_raw)
            messaging_templates = _aggregate_messaging(tpl_pts)
        except Exception as exc:
            logger.warning("[WA Analytics] analytics templates falhou: %s", exc)

        try:
            sess_fields = (
                f"analytics.start({start_ts}).end({end_ts}).granularity(DAY)"
                f".product_types([2])"
            )
            sess_raw = _graph_get(canal.waba_id, canal.token, sess_fields)
            sess_pts = _flatten_messaging_points(sess_raw)
            messaging_session = _aggregate_messaging(sess_pts)
        except Exception as exc:
            logger.warning("[WA Analytics] analytics session falhou: %s", exc)

        if not pricing_summary["messages_paid"] and messaging_templates["sent"]:
            pricing_summary["messages_paid"] = messaging_templates["sent"]
        if not pricing_summary["messages_free"] and messaging_session["sent"]:
            pricing_summary["messages_free"] = messaging_session["sent"]
        if not pricing_summary.get("charged_volume"):
            pricing_summary["charged_volume"] = pricing_summary["messages_paid"]

        # Se pricing não trouxe categorias úteis (só SESSION/TEMPLATES), tenta contagem local
        cats = pricing_summary.get("by_category") or []
        only_synth = cats and all(
            (c.get("key") or "").upper() in ("TEMPLATES", "SESSION", "SERVICE") for c in cats
        )
        if not cats or only_synth:
            try:
                from integrations.whatsapp_local_template_stats import (
                    count_template_sends_by_category,
                )

                local_cats = count_template_sends_by_category(
                    canal, start_ts=start_ts, end_ts=end_ts
                )
                if local_cats:
                    pricing_summary["by_category"] = local_cats
                    local_paid = sum(int(c.get("volume") or 0) for c in local_cats)
                    if local_paid and not pricing_summary.get("messages_paid"):
                        pricing_summary["messages_paid"] = local_paid
                        pricing_summary["charged_volume"] = local_paid
            except Exception as exc:
                logger.info("[WA Analytics] contagem local por categoria falhou: %s", exc)

        if not pricing_summary.get("by_category"):
            pricing_summary["by_category"] = _synthetic_categories(
                pricing_summary["messages_free"],
                pricing_summary["messages_paid"],
            )

        if not pricing_summary.get("cost_available") and not cost_note:
            cost_note = (
                "Gasto estimado com tarifas por categoria (Utility / Marketing / Authentication) "
                "× cotação USD-BRL. A Meta não liberou pricing_analytics neste WABA."
            )

        daily = _merge_daily_series(all_pts, tpl_pts, sess_pts)

        from integrations.awesomeapi_fx import (
            compute_spend_brl,
            get_pricing_rates,
            get_usd_brl_quote,
        )

        quote = get_usd_brl_quote()
        rates = get_pricing_rates()
        spend = compute_spend_brl(
            messages_paid=int(pricing_summary["messages_paid"] or 0),
            meta_cost_usd=float(pricing_summary.get("approximate_cost") or 0),
            quote=quote,
            categories=pricing_summary.get("by_category") or [],
            rates=rates,
        )

        # Categorias enriquecidas com tarifa / USD / BRL
        by_category = spend.get("by_category") or pricing_summary.get("by_category") or []

        return Response(
            {
                "success": True,
                "period": {
                    "days": days_int,
                    "start": start_ts,
                    "end": end_ts,
                    "start_iso": datetime.fromtimestamp(start_ts, tz=timezone.utc).isoformat(),
                    "end_iso": datetime.fromtimestamp(end_ts, tz=timezone.utc).isoformat(),
                },
                "channel": {
                    "id": canal.id,
                    "nome": canal.nome,
                    "phone_number": canal.phone_number,
                    "waba_id": canal.waba_id,
                },
                "summary": {
                    "messages_free": pricing_summary["messages_free"],
                    "messages_paid": pricing_summary["messages_paid"],
                    "charged_volume": pricing_summary["charged_volume"]
                    or pricing_summary["messages_paid"],
                    "approximate_cost": pricing_summary["approximate_cost"],
                    "cost_available": bool(pricing_summary.get("cost_available")),
                    "currency_note": (
                        "Valores aproximados. Podem diferir da fatura Meta."
                        if pricing_summary.get("cost_available")
                        else (cost_note or "Estimativa por categoria × cotação do dólar.")
                    ),
                    "by_category": by_category,
                    "data_source": pricing_summary.get("source") or "messaging",
                    "spend_usd": spend.get("cost_usd"),
                    "spend_brl": spend.get("cost_brl"),
                    "spend_mode": spend.get("mode"),
                    "spend_label": spend.get("label"),
                    "usd_brl_rate": spend.get("usd_rate"),
                },
                "rates": spend.get("rates_table") or [],
                "fx": spend.get("quote"),
                "messaging": {
                    "all": messaging_all,
                    "templates_paid": messaging_templates,
                    "session_free": messaging_session,
                },
                "series": {
                    "daily": daily,
                },
            }
        )

    def _resolve_canal(self, user, channel_id, provedor_id) -> Canal:
        if channel_id:
            canal = Canal.objects.select_related("provedor").get(
                id=channel_id, tipo="whatsapp_oficial"
            )
            self._ensure_access(user, canal.provedor)
            return canal

        provedores = self._provedores_for_user(user)
        if provedor_id:
            provedores = provedores.filter(id=provedor_id)
        canal = (
            Canal.objects.filter(
                provedor__in=provedores,
                tipo="whatsapp_oficial",
                ativo=True,
            )
            .exclude(waba_id__isnull=True)
            .exclude(waba_id="")
            .exclude(token__isnull=True)
            .exclude(token="")
            .order_by("-id")
            .first()
        )
        if not canal:
            raise Canal.DoesNotExist()
        return canal

    def _provedores_for_user(self, user):
        if getattr(user, "user_type", None) == "superadmin":
            return Provedor.objects.all()
        ids = set(Provedor.objects.filter(admins=user).values_list("id", flat=True))
        if getattr(user, "provedor_id", None):
            ids.add(user.provedor_id)
        return Provedor.objects.filter(id__in=ids)

    def _ensure_access(self, user, provedor: Provedor) -> None:
        if getattr(user, "user_type", None) == "superadmin":
            return
        allowed = self._provedores_for_user(user).filter(id=provedor.id).exists()
        if not allowed:
            raise PermissionError("Sem permissão para este canal")
