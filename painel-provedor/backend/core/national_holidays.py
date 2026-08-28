"""Feriados nacionais brasileiros (calendário fixo + móveis via Páscoa).

O provedor só liga/desliga; nome e data não são editáveis.
Por padrão todos ficam ativos.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any, Dict, List, Optional, Union

# Feriados oficiais + pontos facultativos amplamente observados no atendimento.
NATIONAL_HOLIDAY_DEFS: List[Dict[str, Any]] = [
    {'id': 'confraternizacao', 'name': 'Confraternização Universal', 'month': 1, 'day': 1},
    {'id': 'carnaval_segunda', 'name': 'Carnaval (segunda-feira)', 'easter_offset': -48},
    {'id': 'carnaval', 'name': 'Carnaval', 'easter_offset': -47},
    {'id': 'sexta_santa', 'name': 'Sexta-feira Santa', 'easter_offset': -2},
    {'id': 'tiradentes', 'name': 'Tiradentes', 'month': 4, 'day': 21},
    {'id': 'trabalho', 'name': 'Dia do Trabalho', 'month': 5, 'day': 1},
    {'id': 'corpus_christi', 'name': 'Corpus Christi', 'easter_offset': 60},
    {'id': 'independencia', 'name': 'Independência do Brasil', 'month': 9, 'day': 7},
    {'id': 'aparecida', 'name': 'Nossa Senhora Aparecida', 'month': 10, 'day': 12},
    {'id': 'finados', 'name': 'Finados', 'month': 11, 'day': 2},
    {'id': 'proclamacao', 'name': 'Proclamação da República', 'month': 11, 'day': 15},
    {'id': 'consciencia_negra', 'name': 'Dia da Consciência Negra', 'month': 11, 'day': 20},
    {'id': 'natal', 'name': 'Natal', 'month': 12, 'day': 25},
]

_NATIONAL_IDS = {item['id'] for item in NATIONAL_HOLIDAY_DEFS}


def easter_sunday(year: int) -> date:
    """Algoritmo gregoriano anônimo (Meeus/Jones/Butcher)."""
    a = year % 19
    b = year // 100
    c = year % 100
    d = b // 4
    e = b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i = c // 4
    k = c % 4
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    month = (h + l - 7 * m + 114) // 31
    day = ((h + l - 7 * m + 114) % 31) + 1
    return date(year, month, day)


def _date_for_def(defn: Dict[str, Any], year: int) -> date:
    if 'easter_offset' in defn:
        return easter_sunday(year) + timedelta(days=int(defn['easter_offset']))
    return date(year, int(defn['month']), int(defn['day']))


def parse_national_holiday_settings(raw: Union[str, list, dict, None]) -> Dict[str, bool]:
    """
    Normaliza overrides do provedor para {id: active}.
    Ausência do id = ativo (padrão).
    """
    if not raw:
        return {}
    if isinstance(raw, str):
        import json
        try:
            raw = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            return {}

    result: Dict[str, bool] = {}
    if isinstance(raw, dict):
        for key, value in raw.items():
            sid = str(key).strip()
            if sid in _NATIONAL_IDS:
                result[sid] = value is not False
        return result

    if isinstance(raw, list):
        for item in raw:
            if not isinstance(item, dict):
                continue
            sid = str(item.get('id') or '').strip()
            if sid not in _NATIONAL_IDS:
                continue
            result[sid] = item.get('active', True) is not False
    return result


def sanitize_national_holiday_settings(raw: Union[str, list, dict, None]) -> List[Dict[str, Any]]:
    """Persiste id + active para todos os feriados nacionais conhecidos (quando há payload)."""
    if raw is None or raw == [] or raw == {}:
        return []
    overrides = parse_national_holiday_settings(raw)
    return [
        {'id': defn['id'], 'active': overrides.get(defn['id'], True)}
        for defn in NATIONAL_HOLIDAY_DEFS
    ]


def resolve_national_holidays(
    settings_raw: Union[str, list, dict, None] = None,
    year: Optional[int] = None,
) -> List[Dict[str, Any]]:
    """Lista resolvida do ano (nome/data fixos + active do provedor)."""
    if year is None:
        year = date.today().year
    overrides = parse_national_holiday_settings(settings_raw)
    items: List[Dict[str, Any]] = []
    for defn in NATIONAL_HOLIDAY_DEFS:
        hid = defn['id']
        d = _date_for_def(defn, year)
        items.append({
            'id': hid,
            'name': defn['name'],
            'date': d.isoformat(),
            'active': overrides.get(hid, True),
            'all_day': True,
            'source': 'national',
            'locked': True,
        })
    items.sort(key=lambda x: x['date'])
    return items


def national_holiday_on_date(
    settings_raw: Union[str, list, dict, None],
    target: date,
) -> Optional[Dict[str, Any]]:
    """Retorna feriado nacional ativo na data, se houver."""
    for item in resolve_national_holidays(settings_raw, year=target.year):
        if item.get('active') is False:
            continue
        if item.get('date') == target.isoformat():
            return item
    return None
