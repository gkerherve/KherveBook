"""Toolbar icon helpers — qtawesome MDI glyphs with graceful fallback.

Same icon system as the rest of the Kherve family: themed Material
Design icons via qtawesome. When qtawesome is missing the actions
fall back to their text labels, so the app still works.

Copyright (C) 2026 Gwilherm Kerherve

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.
"""

from PyQt5.QtCore import QRectF, Qt
from PyQt5.QtGui import (QColor, QIcon, QPainter, QPainterPath, QPen,
                         QPixmap, QTransform)

try:
    import qtawesome as qta
except ImportError:          # pragma: no cover - optional dependency
    qta = None

#: Brand colours: KherveFitting-family "Python blue" + the "Book" orange.
_BOOK_BLUE = "#3776ab"
_BOOK_ORANGE = "#e07b39"

#: Glyph colour for neutral icons — set by the active theme.
DEFAULT_COLOR = "#444444"


def set_icon_color(color: str):
    """Called by style.apply_style so icons follow the theme."""
    global DEFAULT_COLOR
    DEFAULT_COLOR = color


def icon(name: str, color: str = None) -> QIcon:
    """Return the qtawesome icon *name* (e.g. "mdi.play"), or a null
    icon if qtawesome is unavailable."""
    if qta is None:
        return QIcon()
    try:
        return qta.icon(name, color=color or DEFAULT_COLOR)
    except Exception:
        return QIcon()


#: The app mark sits on a rounded square tinted from the Slate theme
#: (the default): a light slate tile with a slightly darker slate edge.
_SLATE_FILL = "#d5dbe3"
_SLATE_EDGE = "#b9c1cc"

# The letters are drawn as stroked vector paths (not text) so the mark
# renders identically on every platform and without depending on any
# system font being installed. Each glyph builder works in a unit box
# (0..1 in x and y) and is transformed into place by the caller.


def _glyph_K() -> tuple[QPainterPath, float]:
    """Uppercase K in a unit-height box. Returns (path, advance width)."""
    w = 0.82
    path = QPainterPath()
    path.moveTo(0.0, 0.0); path.lineTo(0.0, 1.0)          # stem
    path.moveTo(0.0, 0.52); path.lineTo(w, 0.0)           # upper arm
    path.moveTo(0.0, 0.52); path.lineTo(w, 1.0)           # lower arm
    return path, w


def _glyph_B() -> tuple[QPainterPath, float]:
    """Uppercase B in a unit-height box."""
    w = 0.74
    path = QPainterPath()
    path.moveTo(0.0, 0.0); path.lineTo(0.0, 1.0)          # stem
    # Top bowl.
    path.moveTo(0.0, 0.0)
    path.cubicTo(w * 1.15, 0.02, w * 1.15, 0.48, 0.0, 0.5)
    # Bottom bowl (slightly larger, as in most typefaces).
    path.moveTo(0.0, 0.5)
    path.cubicTo(w * 1.28, 0.52, w * 1.28, 0.98, 0.0, 1.0)
    return path, w


def _glyph_o(x_height: float) -> tuple[QPainterPath, float]:
    """Lowercase o as an ellipse sitting on the baseline (y=1). Its
    height is *x_height* fraction of the cap box."""
    w = 0.72
    path = QPainterPath()
    path.addEllipse(QRectF(0.0, 1.0 - x_height, w, x_height))
    return path, w


def _glyph_k(x_height: float) -> tuple[QPainterPath, float]:
    """Lowercase k: a full-height ascender stem with two short legs
    that reach up to *x_height*."""
    w = 0.66
    top = 1.0 - x_height
    path = QPainterPath()
    path.moveTo(0.0, 0.0); path.lineTo(0.0, 1.0)          # ascender stem
    path.moveTo(w, top + 0.02); path.lineTo(0.0, 0.72)    # upper leg in
    path.moveTo(0.16, 0.66); path.lineTo(w, 1.0)          # lower leg out
    return path, w


def _stroke(p: QPainter, path: QPainterPath, color: str,
            box: QRectF, weight: float):
    """Draw *path* (defined in a unit box) mapped into *box* and
    stroked in *color*. The path is transformed into device space
    first, then stroked with a uniform pen (width = *weight* of the
    box height in pixels) so vertical and horizontal strokes stay the
    same thickness even when the box isn't square."""
    t = QTransform()
    t.translate(box.x(), box.y())
    t.scale(box.width(), box.height())
    mapped = t.map(path)
    pen = QPen(QColor(color))
    pen.setWidthF(weight * box.height())
    pen.setCapStyle(Qt.RoundCap)
    pen.setJoinStyle(Qt.RoundJoin)
    p.setPen(pen)
    p.setBrush(Qt.NoBrush)
    p.drawPath(mapped)


def _paint_slate_tile(p: QPainter, s: float) -> QRectF:
    """Fill a rounded-square slate tile covering the icon, and return the
    inner rectangle the wordmark is laid out in."""
    m = s * 0.06                       # outer margin
    radius = s * 0.22                  # corner rounding
    rect = QRectF(m, m, s - 2 * m, s - 2 * m)
    p.setPen(Qt.NoPen)
    p.setBrush(QColor(_SLATE_FILL))
    p.drawRoundedRect(rect, radius, radius)
    pen = QPen(QColor(_SLATE_EDGE))
    pen.setWidthF(max(1.0, s * 0.02))
    p.setPen(pen)
    p.setBrush(Qt.NoBrush)
    p.drawRoundedRect(rect, radius, radius)
    return rect


def _paint_wordmark(p: QPainter, rect: QRectF):
    """Draw 'KBook' on a single baseline inside *rect*: a blue 'K' then
    an orange 'Book', scaled to fill the tile."""
    xh = 0.66                          # x-height as a fraction of cap box
    ink = "#000000"                    # black letters on the slate tile
    items = [(_glyph_K(), ink),
             (_glyph_B(), ink),
             (_glyph_o(xh), ink),
             (_glyph_o(xh), ink),
             (_glyph_k(xh), ink)]
    gap = 0.12
    total = sum(w for (_path, w), _c in items) + gap * (len(items) - 1)
    # Cap-height: as tall as the tile allows, but not so wide it overflows.
    pad_x, pad_y = rect.width() * 0.13, rect.height() * 0.24
    ch = min(rect.height() - 2 * pad_y, (rect.width() - 2 * pad_x) / total)
    word_w = total * ch
    x = rect.x() + (rect.width() - word_w) / 2.0
    top = rect.y() + (rect.height() - ch) / 2.0
    weight = 0.16
    for (path, gw), color in items:
        _stroke(p, path, color, QRectF(x, top, gw * ch, ch), weight)
        x += (gw + gap) * ch


def _paint_book(p: QPainter, box: QRectF):
    """Stroke a small open book (two pages meeting at a central spine)
    inside *box*, in the same black ink as the wordmark."""
    path = QPainterPath()
    # Left cover + page, then right cover + page (v grows downward; the
    # outer top corners sit a little higher than the spine, so the book
    # reads as open and seen slightly from above).
    path.moveTo(0.50, 0.16); path.lineTo(0.04, 0.05)
    path.lineTo(0.04, 0.82); path.lineTo(0.50, 0.93)
    path.moveTo(0.50, 0.16); path.lineTo(0.96, 0.05)
    path.lineTo(0.96, 0.82); path.lineTo(0.50, 0.93)
    path.moveTo(0.50, 0.16); path.lineTo(0.50, 0.93)   # spine
    # A couple of page lines per side, following each page's slant.
    path.moveTo(0.42, 0.34); path.lineTo(0.14, 0.28)
    path.moveTo(0.42, 0.54); path.lineTo(0.14, 0.48)
    path.moveTo(0.58, 0.34); path.lineTo(0.86, 0.28)
    path.moveTo(0.58, 0.54); path.lineTo(0.86, 0.48)
    _stroke(p, path, "#000000", box, weight=0.055)


def _paint_kbook(size: int) -> QPixmap:
    """Draw the KherveBook mark on a rounded slate tile: the single-line
    'KBook' wordmark above a small open book, at every size."""
    pm = QPixmap(size, size)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    s = float(size)
    rect = _paint_slate_tile(p, s)
    x, y, w, h = rect.x(), rect.y(), rect.width(), rect.height()
    _paint_wordmark(p, QRectF(x, y + h * 0.05, w, h * 0.44))   # upper half
    bw, bh = w * 0.46, h * 0.34
    _paint_book(p, QRectF(x + (w - bw) / 2.0, y + h * 0.58, bw, bh))
    p.end()
    return pm


def app_icon() -> QIcon:
    """Window/taskbar icon: the single-line 'KBook' wordmark on a
    rounded slate tile, rendered at each standard size."""
    ic = QIcon()
    for size in (16, 24, 32, 48, 64, 128, 256):
        ic.addPixmap(_paint_kbook(size))
    return ic
