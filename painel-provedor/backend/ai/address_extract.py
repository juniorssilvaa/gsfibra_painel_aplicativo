"""Extração de CEP, coordenadas e logradouro de textos livres do cliente."""
from __future__ import annotations

import logging
import re
from typing import Optional, Tuple
from urllib.parse import unquote

logger = logging.getLogger(__name__)

_CEP_FORMATADO = re.compile(r"(?<![\d.])(\d{2})\.?(\d{3})\s?-\s?(\d{3})(?![\d])")
_CEP_ROTULADO = re.compile(r"\bcep\b\W{0,3}(\d{2})\.?(\d{3})-?(\d{3})(?!\d)", re.I)
_COORD_ROTULADA_LAT = re.compile(r"\blat(?:itude)?\s*[=:]\s*(-?\d{1,2}(?:[.,]\d+)?)", re.I)
_COORD_ROTULADA_LNG = re.compile(r"\b(?:lng|lon|long|longitude)\s*[=:]\s*(-?\d{1,3}(?:[.,]\d+)?)", re.I)
_COORD_PAR = re.compile(r"(?<![\d.])(-?\d{1,2}\.\d{4,})\s*[,;]?\s*(-?\d{1,3}\.\d{4,})(?![\d])")
_MAPS_LINK = re.compile(
    r"https?://(?:maps\.app\.goo\.gl|goo\.gl/maps|(?:www\.)?google\.[a-z.]+/maps|maps\.google\.[a-z.]+)[^\s<>\"']*",
    re.I,
)
_COORD_LUGAR = re.compile(r"!3d(-?\d{1,2}\.\d+)!4d(-?\d{1,3}\.\d+)")
_COORD_ARROBA = re.compile(r"@(-?\d{1,2}\.\d+),(-?\d{1,3}\.\d+)")
_COORD_PARAM = re.compile(r"[?&/](?:q|query|ll|center|destination|search)[=/](-?\d{1,2}\.\d+),\s*\+?(-?\d{1,3}\.\d+)")
_TIPO_LOGRADOURO = re.compile(
    r"^(?:rua|r\.|avenida|av\.?|travessa|tv\.?|alameda|al\.?|rodovia|rod\.?|estrada|est\.?|"
    r"pra[cç]a|p[cç]\.?|largo|vila|via)(?:\s+|$)",
    re.I,
)


def extrair_cep(texto) -> Optional[str]:
    """Retorna o CEP (8 dígitos) encontrado no texto, ou None."""
    if not texto:
        return None
    texto = str(texto)
    m = _CEP_ROTULADO.search(texto) or _CEP_FORMATADO.search(texto)
    if not m:
        return None
    return "".join(m.groups())


def _coord_valida(lat: str, lng: str) -> Optional[Tuple[str, str]]:
    try:
        la = float(lat.replace(",", "."))
        lo = float(lng.replace(",", "."))
    except ValueError:
        return None
    if not (-90 <= la <= 90 and -180 <= lo <= 180) or (la == 0 and lo == 0):
        return None
    return lat.replace(",", "."), lng.replace(",", ".")


def extrair_coordenadas(texto) -> Optional[Tuple[str, str]]:
    """Retorna (lat, lng) de pin, link de mapa ou par 'lat, lng' no texto, ou None."""
    if not texto:
        return None
    texto = str(texto)
    lat_m = _COORD_ROTULADA_LAT.search(texto)
    lng_m = _COORD_ROTULADA_LNG.search(texto)
    if lat_m and lng_m:
        coords = _coord_valida(lat_m.group(1), lng_m.group(1))
        if coords:
            return coords
    for m in _COORD_PAR.finditer(texto):
        coords = _coord_valida(m.group(1), m.group(2))
        if coords:
            return coords
    return None


def _coords_de_url(url: str) -> Optional[Tuple[str, str]]:
    url = unquote(unquote(url or ""))
    for padrao in (_COORD_LUGAR, _COORD_ARROBA, _COORD_PARAM):
        m = padrao.search(url)
        if m:
            coords = _coord_valida(m.group(1), m.group(2))
            if coords:
                return coords
    return None


def coordenadas_de_link_maps(texto) -> Optional[Tuple[str, str]]:
    """Coordenadas de um link do Google Maps no texto; links curtos são abertos para ler o destino."""
    if not texto:
        return None
    for m in _MAPS_LINK.finditer(str(texto)):
        url = m.group(0).rstrip(").,;!?")
        coords = _coords_de_url(url)
        if coords:
            return coords
        try:
            import requests

            r = requests.get(url, allow_redirects=True, timeout=8, headers={"User-Agent": "Mozilla/5.0"})
            for destino in [r.url] + [h.headers.get("Location", "") for h in r.history]:
                coords = _coords_de_url(destino)
                if coords:
                    return coords
            corpo = unquote(r.text[:300000])
            for padrao in (_COORD_LUGAR, re.compile(r"center=(-?\d{1,2}\.\d+),(-?\d{1,3}\.\d+)")):
                achado = padrao.search(corpo)
                if achado:
                    coords = _coord_valida(achado.group(1), achado.group(2))
                    if coords:
                        return coords
        except Exception as e:
            logger.warning("[viabilidade] nao foi possivel abrir link do Google Maps: %s", e)
    return None


def numero_imovel(texto) -> str:
    """Somente o número da casa/prédio (primeiro número do texto); vazio se não houver."""
    m = re.search(r"\d+", str(texto or ""))
    return m.group(0) if m else ""


def limpar_logradouro(texto) -> str:
    """Reduz um endereço livre ao nome da rua: sem CEP, número e demais partes."""
    if not texto:
        return ""
    s = _CEP_ROTULADO.sub(" ", str(texto))
    s = _CEP_FORMATADO.sub(" ", s)
    s = re.split(r"[,\n;]| - ", s)[0].strip()
    sem_numero = re.sub(r"\s+(?:n[º°o.]?\s*)?\d+[a-z]?\s*$", "", s, flags=re.I)
    if logradouro_sem_tipo(sem_numero):
        s = sem_numero
    return re.sub(r"\s{2,}", " ", s).strip(" -.")


def logradouro_sem_tipo(logradouro: str) -> str:
    """Remove o tipo do logradouro (Rua, Av., Travessa...) para busca mais ampla."""
    return _TIPO_LOGRADOURO.sub("", (logradouro or "").strip()).strip()
