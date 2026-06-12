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

from PyQt5.QtGui import QIcon

try:
    import qtawesome as qta
except ImportError:          # pragma: no cover - optional dependency
    qta = None

#: Default glyph colour — dark slate, close to Jupyter's toolbar grey.
DEFAULT_COLOR = "#444444"


def icon(name: str, color: str = DEFAULT_COLOR) -> QIcon:
    """Return the qtawesome icon *name* (e.g. "mdi.play"), or a null
    icon if qtawesome is unavailable."""
    if qta is None:
        return QIcon()
    try:
        return qta.icon(name, color=color)
    except Exception:
        return QIcon()


def app_icon() -> QIcon:
    """Window/taskbar icon: a notebook glyph in Python blue."""
    return icon("mdi.notebook-outline", color="#3776ab")
