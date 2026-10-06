"""Modo mockup: prints reais do app colados sem alteração dentro de celulares desenhados pelo sistema."""
from __future__ import annotations

import io
from typing import Dict, List, Tuple

from PIL import Image, ImageDraw, ImageFilter, ImageOps

MAX_SCREENS = 3
PHONE_HEIGHT_RATIO = 2.05
BODY_COLOR = (17, 17, 19, 255)
EDGE_COLOR = (82, 82, 91, 255)

# Área livre (frações da arte) onde os celulares entram quando a IA de imagem escreve os textos.
IA_PHONE_BOXES: Dict[str, Tuple[float, float, float, float]] = {
    'quadrado': (0.50, 0.06, 0.97, 0.96),
    'paisagem': (0.52, 0.05, 0.98, 0.97),
    'story': (0.08, 0.28, 0.92, 0.78),
}


def side_layout(formato: str) -> bool:
    """Quadrado e paisagem: celulares à direita e textos à esquerda. Story: celulares no meio."""
    return formato in ('quadrado', 'paisagem')


def box_from_fractions(size: Tuple[int, int], fractions: Tuple[float, float, float, float]) -> Tuple[int, int, int, int]:
    w, h = size
    x0, y0, x1, y1 = fractions
    return int(w * x0), int(h * y0), int(w * x1), int(h * y1)


def _rounded_mask(size: Tuple[int, int], radius: int) -> Image.Image:
    mask = Image.new('L', size, 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, size[0] - 1, size[1] - 1), radius=radius, fill=255)
    return mask


def phone(screen_bytes: bytes, width: int) -> Image.Image:
    width = max(width, 60)
    height = int(width * PHONE_HEIGHT_RATIO)
    bezel = max(4, int(width * 0.035))
    radius = int(width * 0.16)
    body = Image.new('RGBA', (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(body)
    draw.rounded_rectangle(
        (0, 0, width - 1, height - 1), radius=radius, fill=BODY_COLOR,
        outline=EDGE_COLOR, width=max(2, int(width * 0.008)),
    )
    screen_size = (width - 2 * bezel, height - 2 * bezel)
    shot = Image.open(io.BytesIO(screen_bytes)).convert('RGB')
    shot = ImageOps.fit(shot, screen_size, Image.LANCZOS, centering=(0.5, 0.0))
    body.paste(shot, (bezel, bezel), _rounded_mask(screen_size, max(4, radius - bezel)))
    return body


def _shadow(item: Image.Image) -> Image.Image:
    blur = max(6, int(item.width * 0.06))
    pad = blur * 3
    alpha = Image.new('L', (item.width + 2 * pad, item.height + 2 * pad), 0)
    alpha.paste(item.getchannel('A').point(lambda a: int(a * 0.6)), (pad, pad))
    alpha = alpha.filter(ImageFilter.GaussianBlur(blur))
    shadow = Image.new('RGBA', alpha.size, (0, 0, 0, 255))
    shadow.putalpha(alpha)
    return shadow


def _paste(canvas: Image.Image, item: Image.Image, x: int, y: int) -> None:
    shadow = _shadow(item)
    pad = (shadow.width - item.width) // 2
    offset = int(item.width * 0.04)
    canvas.alpha_composite(shadow, (max(0, x - pad), max(0, y - pad + offset)))
    canvas.alpha_composite(item, (x, y))


def place_phones(canvas: Image.Image, screens: List[bytes], box: Tuple[int, int, int, int]) -> Image.Image:
    """Desenha 1 a 3 celulares com os prints dentro da área box (x0, y0, x1, y1)."""
    screens = [s for s in screens if s][:MAX_SCREENS]
    canvas = canvas.convert('RGBA')
    if not screens:
        return canvas
    x0, y0, x1, y1 = box
    bw, bh = max(1, x1 - x0), max(1, y1 - y0)
    n = len(screens)
    back_scale = 0.86
    overlap = 0.72

    front_h = bh * (0.98 if n == 1 else 0.94)
    front_w = front_h / PHONE_HEIGHT_RATIO
    back_w = front_w * back_scale
    if n == 1:
        total_w = front_w
    elif n == 2:
        total_w = back_w * overlap + front_w
    else:
        total_w = 2 * back_w * overlap + front_w
    shrink = min(1.0, bw / total_w)
    front_w, back_w = int(front_w * shrink), int(back_w * shrink)
    front_h = int(front_w * PHONE_HEIGHT_RATIO)
    back_h = int(back_w * PHONE_HEIGHT_RATIO)

    left = x0 + int((bw - total_w * shrink) / 2)
    front_y = y0 + (bh - front_h) // 2
    back_y = front_y + int((front_h - back_h) * 0.25)

    if n == 1:
        _paste(canvas, phone(screens[0], front_w), left, front_y)
    elif n == 2:
        _paste(canvas, phone(screens[1], back_w), left, back_y)
        _paste(canvas, phone(screens[0], front_w), left + int(back_w * overlap), front_y)
    else:
        front_x = left + int(back_w * overlap)
        _paste(canvas, phone(screens[1], back_w), left, back_y)
        _paste(canvas, phone(screens[2], back_w), front_x + front_w - int(back_w * (1 - overlap)), back_y)
        _paste(canvas, phone(screens[0], front_w), front_x, front_y)
    return canvas
