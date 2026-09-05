"""Versão do produto (CHANGELOG.json / VERSION) usada no Superadmin."""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, Optional

from django.conf import settings

logger = logging.getLogger(__name__)

_FALLBACK = "2.59.0"


def _candidate_roots() -> list[Path]:
    base = Path(settings.BASE_DIR)
    return [
        base.parent.parent,  # repo root (superadmin/backend → niohub)
        base.parent,
        base,
        Path(__file__).resolve().parents[4],
    ]


def read_changelog() -> Optional[Dict[str, Any]]:
    for root in _candidate_roots():
        path = root / "CHANGELOG.json"
        try:
            if path.is_file():
                with path.open(encoding="utf-8") as fh:
                    data = json.load(fh)
                if isinstance(data, dict):
                    return data
        except Exception as exc:
            logger.warning("Falha ao ler changelog %s: %s", path, exc)
    return None


def read_app_version() -> str:
    data = read_changelog()
    if data:
        ver = str(data.get("current_version") or "").strip()
        if ver and ver.lower() != "unreleased":
            return ver
    for root in _candidate_roots():
        path = root / "VERSION"
        try:
            if path.is_file():
                ver = path.read_text(encoding="utf-8").strip()
                if ver:
                    return ver
        except Exception:
            continue
    return _FALLBACK
