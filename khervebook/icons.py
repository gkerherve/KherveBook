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

from PyQt5.QtCore import QPointF, QRectF, Qt
from PyQt5.QtGui import QColor, QIcon, QPainter, QPen, QPixmap

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


def _paint_kbook(size: int) -> QPixmap:
    """Draw the KherveBook mark: a book (blue cover, orange spine) + a K."""
    pm = QPixmap(size, size)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    p.setPen(Qt.NoPen)
    s = float(size)
    r = s * 0.07
    top, height = s * 0.13, s * 0.74
    # Orange spine (the binding) on the left.
    p.setBrush(QColor(_BOOK_ORANGE))
    p.drawRoundedRect(QRectF(s * 0.17, top, s * 0.18, height), r, r)
    # Blue cover overlapping to the right.
    cover = QRectF(s * 0.30, top, s * 0.53, height)
    p.setBrush(QColor(_BOOK_BLUE))
    p.drawRoundedRect(cover, r, r)
    # A thin page line where the spine meets the cover.
    p.fillRect(QRectF(s * 0.315, top, s * 0.012, height),
               QColor(255, 255, 255, 150))
    # A bold white K, drawn as strokes so it renders without a font.
    pen = QPen(QColor("#ffffff"))
    pen.setWidthF(s * 0.10)
    pen.setCapStyle(Qt.RoundCap)
    pen.setJoinStyle(Qt.RoundJoin)
    p.setPen(pen)
    x0, x1 = s * 0.46, s * 0.71          # stem x, arm-end x
    yt, ym, yb = s * 0.28, s * 0.50, s * 0.72
    p.drawLine(QPointF(x0, yt), QPointF(x0, yb))      # stem
    p.drawLine(QPointF(x0, ym), QPointF(x1, yt))      # upper arm
    p.drawLine(QPointF(x0, ym), QPointF(x1, yb))      # lower arm
    p.end()
    return pm


def app_icon() -> QIcon:
    """Window/taskbar icon: the KherveBook 'K book' mark."""
    ic = QIcon()
    for size in (16, 24, 32, 48, 64, 128, 256):
        ic.addPixmap(_paint_kbook(size))
    return ic
