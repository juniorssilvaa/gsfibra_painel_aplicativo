"""Modo "sistema": aplica textos exatos e logo sobre a arte gerada (o preço nunca passa pela IA de imagem)."""
from __future__ import annotations

import io
import re
from pathlib import Path
from typing import List, Optional, Tuple

from PIL import Image, ImageDraw, ImageFont

from marketing import mockup

FONT_DIR = Path(__file__).resolve().parent / 'fonts'
FONT_BOLD = FONT_DIR / 'Montserrat-ExtraBold.ttf'
FONT_SEMIBOLD = FONT_DIR / 'Montserrat-SemiBold.ttf'
DEFAULT_ACCENT = '#FFD400'
_HEX = re.compile(r'^#?([0-9a-fA-F]{6})$')


def parse_color(value: Optional[str], default: str = DEFAULT_ACCENT) -> Tuple[int, int, int]:
    match = _HEX.match((value or '').strip()) or _HEX.match(default)
    raw = match.group(1)
    return int(raw[0:2], 16), int(raw[2:4], 16), int(raw[4:6], 16)


def _font(path: Path, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(path), max(size, 10))


def _wrap(draw: ImageDraw.ImageDraw, text: str, font, max_w: int, max_lines: int) -> Optional[List[str]]:
    lines: List[str] = []
    current = ''
    for word in text.split():
        trial = f'{current} {word}'.strip()
        if draw.textlength(trial, font=font) <= max_w:
            current = trial
            continue
        if current:
            lines.append(current)
        current = word
        if draw.textlength(current, font=font) > max_w:
            return None
    if current:
        lines.append(current)
    return lines if len(lines) <= max_lines else None


def _fit(draw, text: str, path: Path, size: int, max_w: int, max_lines: int):
    """Reduz a fonte até o texto caber na largura e no número de linhas."""
    while size > 12:
        font = _font(path, size)
        lines = _wrap(draw, text, font, max_w, max_lines)
        if lines:
            return font, lines
        size = int(size * 0.9)
    font = _font(path, 12)
    return font, _wrap(draw, text, font, max_w, 99) or [text]


def _paste_logo(canvas: Image.Image, logo_bytes: bytes, margin: int) -> None:
    logo = Image.open(io.BytesIO(logo_bytes)).convert('RGBA')
    w, h = canvas.size
    max_w, max_h = int(w * 0.26), int(h * 0.12)
    scale = min(max_w / logo.width, max_h / logo.height)
    logo = logo.resize((max(1, int(logo.width * scale)), max(1, int(logo.height * scale))), Image.LANCZOS)
    canvas.alpha_composite(logo, (margin, margin))


def compose(
    image: Image.Image,
    *,
    titulo: str = '',
    destaque: str = '',
    preco: str = '',
    chamada: str = '',
    rodape: str = '',
    cor_destaque: Optional[str] = None,
    logo_bytes: Optional[bytes] = None,
    telas: Optional[List[bytes]] = None,
    formato: str = '',
) -> Image.Image:
    canvas = image.convert('RGBA')
    w, h = canvas.size
    base = w if h >= w else int(h * 1.1)
    margin = int(w * 0.06)
    side = bool(telas) and mockup.side_layout(formato)
    max_w = int(w * 0.48) - margin if side else w - 2 * margin
    below_logo = int(h * 0.17) if logo_bytes else margin
    accent = parse_color(cor_destaque)
    white = (255, 255, 255)
    draw = ImageDraw.Draw(canvas)

    spec = [
        (titulo, FONT_SEMIBOLD, int(base * 0.055), 2, white),
        (destaque, FONT_BOLD, int(base * 0.13), 1, white),
        (preco, FONT_BOLD, int(base * 0.085), 1, accent),
        (chamada, FONT_SEMIBOLD, int(base * 0.045), 2, white),
        (rodape, FONT_SEMIBOLD, int(base * 0.032), 2, (225, 225, 225)),
    ]
    blocks = []
    for text, path, size, max_lines, color in spec:
        text = (text or '').strip()
        if not text:
            continue
        font, lines = _fit(draw, text, path, size, max_w, max_lines)
        ascent, descent = font.getmetrics()
        blocks.append((lines, font, color, ascent + descent))

    gap = int(base * 0.018)
    total = sum(len(lines) * lh for lines, _, _, lh in blocks) + gap * max(0, len(blocks) - 1)
    top = max((h - total) // 2, below_logo) if side else h - margin - total

    if blocks:
        if side:
            fade_end = int(w * 0.62)
            shade = Image.new('L', (w, 1), 0)
            for x in range(fade_end):
                shade.putpixel((x, 0), int(215 * (1 - x / fade_end)))
        else:
            fade_start = max(0, top - int(base * 0.22))
            shade = Image.new('L', (1, h), 0)
            for y in range(fade_start, h):
                progress = min(1.0, (y - fade_start) / max(1, top - fade_start + int(base * 0.05)))
                shade.putpixel((0, y), int(215 * progress))
        overlay = Image.new('RGBA', (w, h), (0, 0, 0, 0))
        overlay.putalpha(shade.resize((w, h)))
        canvas = Image.alpha_composite(canvas, overlay)

    if telas:
        if side:
            box = (int(w * 0.5), margin, w - int(margin * 0.6), h - margin)
        else:
            box = (margin, below_logo, w - margin, (top - 2 * gap) if blocks else h - margin)
        canvas = mockup.place_phones(canvas, telas, box)

    if blocks:
        draw = ImageDraw.Draw(canvas)
        y = top
        stroke = max(1, int(base * 0.002))
        for lines, font, color, line_h in blocks:
            for line in lines:
                draw.text((margin, y), line, font=font, fill=color, stroke_width=stroke, stroke_fill=(0, 0, 0))
                y += line_h
            y += gap

    if logo_bytes:
        _paste_logo(canvas, logo_bytes, margin)
    return canvas.convert('RGB')
