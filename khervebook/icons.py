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


#: Below this pixel size the icon shows the compact "KB" monogram;
#: at or above it the stacked "K" over "Book" wordmark is legible.
_STACK_THRESHOLD = 40

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


def _word_width(glyphs, gap: float) -> float:
    return sum(w for _, w in glyphs) + gap * (len(glyphs) - 1)


def _paint_monogram(p: QPainter, s: float):
    """Compact mark for small sizes: a blue 'KB'."""
    kp, kw = _glyph_K()
    bp, bw = _glyph_B()
    gap = 0.22
    total = kw + gap + bw
    h = s * 0.58
    top = (s - h) / 2.0
    left = (s - total * h) / 2.0
    weight = 0.15
    _stroke(p, kp, _BOOK_BLUE, QRectF(left, top, kw * h, h), weight)
    _stroke(p, bp, _BOOK_BLUE,
            QRectF(left + (kw + gap) * h, top, bw * h, h), weight)


def _paint_stacked(p: QPainter, s: float):
    """Full wordmark for larger sizes: a big blue 'K' over orange
    'Book'."""
    # Big K on top (Kherve blue).
    kp, kw = _glyph_K()
    kh = s * 0.50
    ktop = s * 0.06
    _stroke(p, kp, _BOOK_BLUE,
            QRectF((s - kw * kh) / 2.0, ktop, kw * kh, kh), 0.15)

    # "Book" underneath (Book orange).
    xh = 0.66                          # x-height as a fraction of cap box
    glyphs = [_glyph_B(), _glyph_o(xh), _glyph_o(xh), _glyph_k(xh)]
    gap = 0.16
    total = _word_width(glyphs, gap)
    wh = s * 0.30                      # cap-height of the word
    wtop = s * 0.63
    left = (s - total * wh) / 2.0
    weight = 0.17
    x = left
    for path, gw in glyphs:
        _stroke(p, path, _BOOK_ORANGE, QRectF(x, wtop, gw * wh, wh), weight)
        x += (gw + gap) * wh


def _paint_kbook(size: int) -> QPixmap:
    """Draw the KherveBook mark: 'KB' when small, a stacked 'K' over
    'Book' when large enough for the wordmark to read."""
    pm = QPixmap(size, size)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    s = float(size)
    if size < _STACK_THRESHOLD:
        _paint_monogram(p, s)
    else:
        _paint_stacked(p, s)
    p.end()
    return pm


def app_icon() -> QIcon:
    """Window/taskbar icon: the KherveBook wordmark. Small renderings
    get the 'KB' monogram; larger ones get the stacked 'K' / 'Book'."""
    ic = QIcon()
    for size in (16, 24, 32, 48, 64, 128, 256):
        ic.addPixmap(_paint_kbook(size))
    return ic
