"""Rich-text "Note" cell — a Word-style page you type and format directly.

Unlike the Markdown cell (edit markup, render on run), a Note cell is
WYSIWYG: the editor *is* the rendered view. A formatting toolbar drives a
QTextEdit's rich text (bold/italic/underline, headings, lists, colour,
font) and the whole thing round-trips as HTML inside the ``.kbook``.

A transparent **ink overlay** sits on top for pen annotation — freehand
strokes stored as points and re-scaled to the cell's width, so you can
scribble over the notes like on paper. The cell's ``source`` is a small
JSON blob ``{"kbook_note": 1, "html": "...", "ink": {...}}`` so both the
text and the ink travel together.

Copyright (C) 2026 Gwilherm Kerherve

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.
"""

import json

from PyQt5.QtCore import QEvent, QPointF, Qt, pyqtSignal
from PyQt5.QtGui import (QColor, QFont, QPainter, QPen, QPolygonF,
                         QTextCharFormat, QTextCursor, QTextListFormat)
from PyQt5.QtWidgets import (QColorDialog, QFrame, QHBoxLayout, QSizePolicy,
                             QTextEdit, QWidget)

from .cells import CELL_CLASSES, CellWidget

#: Starter content for a brand-new note cell.
NOTE_STARTER = json.dumps({
    "kbook_note": 1,
    "html": ("<h2>Notes</h2><p>Type here like in a word processor — "
             "use the toolbar to format text, or the pen to annotate.</p>"),
    "ink": None,
})

#: Heading level -> point size for the toolbar's paragraph styles.
_HEADING_SIZES = {0: 11, 1: 22, 2: 17, 3: 14}


class _InkOverlay(QWidget):
    """Transparent pen layer painted over the rich-text editor.

    When the pen is off the widget is click-through (text editing works
    normally); when on it captures the mouse and records freehand
    strokes. Strokes are stored in a reference coordinate space (the
    width at which they were drawn) and rescaled to the current width on
    paint, so they stay put as the cell reflows."""

    changed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.setAttribute(Qt.WA_NoSystemBackground, True)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.pen_on = False
        self.color = QColor("#c0392b")
        self.width_px = 3
        self._ref_w = 0.0            # width the strokes are defined in
        self._strokes = []           # [{color, width, pts:[(x, y), ...]}]
        self._cur = None

    # -- persistence -------------------------------------------------------
    def to_dict(self):
        if not self._strokes:
            return None
        return {"ref_w": self._ref_w, "strokes": [
            {"color": s["color"], "width": s["width"], "pts": s["pts"]}
            for s in self._strokes]}

    def from_dict(self, data):
        self._strokes = []
        self._ref_w = 0.0
        if data:
            self._ref_w = float(data.get("ref_w") or 0.0)
            for s in data.get("strokes", []):
                self._strokes.append({
                    "color": s.get("color", "#c0392b"),
                    "width": float(s.get("width", 3)),
                    "pts": [(float(x), float(y)) for x, y in s.get("pts", [])]})
        self.update()

    def clear(self):
        if self._strokes or self._cur:
            self._strokes = []
            self._cur = None
            self.update()
            self.changed.emit()

    def undo(self):
        if self._strokes:
            self._strokes.pop()
            self.update()
            self.changed.emit()

    # -- pen toggle --------------------------------------------------------
    def set_pen(self, on: bool):
        self.pen_on = bool(on)
        self.setAttribute(Qt.WA_TransparentForMouseEvents, not self.pen_on)
        if self.pen_on:
            self.raise_()
        self.setCursor(Qt.CrossCursor if self.pen_on else Qt.ArrowCursor)

    # -- geometry ----------------------------------------------------------
    def _scale(self) -> float:
        if self._ref_w and self.width():
            return self.width() / self._ref_w
        return 1.0

    # -- drawing -----------------------------------------------------------
    def mousePressEvent(self, event):
        if not self.pen_on:
            return
        if not self._ref_w:
            self._ref_w = float(self.width() or 1)
        s = 1.0 / self._scale()
        self._cur = {"color": self.color.name(), "width": self.width_px,
                     "pts": [(event.x() * s, event.y() * s)]}
        self.update()

    def mouseMoveEvent(self, event):
        if self._cur is None:
            return
        s = 1.0 / self._scale()
        self._cur["pts"].append((event.x() * s, event.y() * s))
        self.update()

    def mouseReleaseEvent(self, _event):
        if self._cur is None:
            return
        if len(self._cur["pts"]) > 1:
            self._strokes.append(self._cur)
            self.changed.emit()
        self._cur = None
        self.update()

    def paintEvent(self, _event):
        if not self._strokes and self._cur is None:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        scale = self._scale()
        for stroke in self._strokes + ([self._cur] if self._cur else []):
            pen = QPen(QColor(stroke["color"]),
                       max(1.0, stroke["width"] * scale),
                       Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
            p.setPen(pen)
            poly = QPolygonF([QPointF(x * scale, y * scale)
                              for x, y in stroke["pts"]])
            p.drawPolyline(poly)
        p.end()


class _RichEdit(QTextEdit):
    """A rich-text editor that grows to fit its content (up to a cap)."""

    MAX_HEIGHT = 6000
    focused = pyqtSignal()

    def __init__(self):
        super().__init__()
        self.setAcceptRichText(True)
        self.setFrameShape(QFrame.NoFrame)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setTabChangesFocus(False)
        f = QFont()
        f.setPointSizeF(11)
        self.setFont(f)
        self.document().documentLayout().documentSizeChanged.connect(
            lambda _=None: self._fit())
        self.textChanged.connect(self._fit)
        # A Word-style white page (dark text), regardless of app theme —
        # user-applied text colours still win via their char format.
        self.setStyleSheet("QTextEdit { background: #ffffff; "
                           "color: #1a1a1a; }")
        self._fit()

    def _fit(self):
        h = int(self.document().size().height()) + 10
        self.setFixedHeight(max(90, min(h, self.MAX_HEIGHT)))

    def focusInEvent(self, event):
        super().focusInEvent(event)
        self.focused.emit()

    def dragEnterEvent(self, event):
        # Let file drops fall through to the cell; keep rich-text drags.
        if event.mimeData().hasUrls():
            event.ignore()
        else:
            super().dragEnterEvent(event)


class NoteCell(CellWidget):
    """WYSIWYG rich-text page with an optional pen/ink annotation layer."""

    CELL_TYPE = "note"
    COMMENT = ("<!-- ", " -->")

    def __init__(self, source=""):
        super().__init__(source)
        self.gutter.setText("note")
        self.editor.hide()                     # base plain editor unused here
        self.rich = _RichEdit()
        self.rich.focused.connect(lambda: self.focused.emit(self))
        self.rich.textChanged.connect(self.content_changed.emit)
        self._stack = QWidget()                # holds editor + ink overlay
        stack_layout = QHBoxLayout(self._stack)
        stack_layout.setContentsMargins(0, 0, 0, 0)
        stack_layout.addWidget(self.rich)
        self.ink = _InkOverlay(self._stack)
        self.ink.changed.connect(self.content_changed.emit)
        # No in-cell toolbar: the formatting + pen tools live in the main
        # window's second toolbar row (CellToolBar), which follows the
        # focused cell. That keeps the cell itself just the writing page,
        # free to be resized/expanded with the cell grips.
        self.column.addWidget(self._stack)
        self.set_source(source or NOTE_STARTER)

    # -- ink overlay sizing ------------------------------------------------
    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._sync_ink_geometry()

    def _sync_ink_geometry(self):
        self.ink.setGeometry(self.rich.geometry())

    # -- pen / ink (driven by the CellToolBar) -----------------------------
    def set_pen(self, on: bool):
        self.ink.set_pen(on)
        self._sync_ink_geometry()

    def pen_active(self) -> bool:
        return self.ink.pen_on

    def pick_ink_color(self):
        col = QColorDialog.getColor(self.ink.color, self, "Pen colour")
        if col.isValid():
            self.ink.color = col

    def set_ink_width(self, width: int):
        self.ink.width_px = width

    def ink_undo(self):
        self.ink.undo()

    def ink_clear(self):
        self.ink.clear()

    # -- font (driven by the CellToolBar) ----------------------------------
    def set_font_family(self, family: str):
        self._merge(lambda fmt: fmt.setFontFamily(family))

    def set_font_size(self, points: int):
        self._merge(lambda fmt: fmt.setFontPointSize(points))

    # -- rich-text formatting (also called by the CellToolBar) -------------
    def _merge(self, apply_fn):
        """Apply a QTextCharFormat change to the selection (or caret)."""
        cur = self.rich.textCursor()
        fmt = QTextCharFormat()
        apply_fn(fmt)
        if not cur.hasSelection():
            cur.select(QTextCursor.WordUnderCursor)
        cur.mergeCharFormat(fmt)
        self.rich.mergeCurrentCharFormat(fmt)
        self.rich.setFocus()

    def _toggle(self, is_on, apply_fn):
        cur = self.rich.textCursor()
        state = not is_on(cur.charFormat())
        self._merge(lambda fmt: apply_fn(fmt, state))

    def toggle_bold(self):
        self._toggle(lambda f: f.fontWeight() > QFont.Normal,
                     lambda f, on: f.setFontWeight(
                         QFont.Bold if on else QFont.Normal))

    def toggle_italic(self):
        self._toggle(lambda f: f.fontItalic(),
                     lambda f, on: f.setFontItalic(on))

    def toggle_underline(self):
        self._toggle(lambda f: f.fontUnderline(),
                     lambda f, on: f.setFontUnderline(on))

    def toggle_strike(self):
        self._toggle(lambda f: f.fontStrikeOut(),
                     lambda f, on: f.setFontStrikeOut(on))

    def set_heading(self, level: int):
        """Style the current paragraph as Body (0) or Heading 1-3."""
        size = _HEADING_SIZES.get(level, 11)
        cur = self.rich.textCursor()
        cur.select(QTextCursor.BlockUnderCursor)
        if not cur.hasSelection():
            cur.movePosition(QTextCursor.StartOfBlock)
            cur.movePosition(QTextCursor.EndOfBlock, QTextCursor.KeepAnchor)
        fmt = QTextCharFormat()
        fmt.setFontPointSize(size)
        fmt.setFontWeight(QFont.Bold if level else QFont.Normal)
        cur.mergeCharFormat(fmt)
        self.rich.setFocus()

    def _list(self, style):
        cur = self.rich.textCursor()
        cur.createList(QTextListFormat.ListDisc if style == "bullet"
                       else QTextListFormat.ListDecimal)
        self.rich.setFocus()

    def bullet_list(self):
        self._list("bullet")

    def numbered_list(self):
        self._list("number")

    def set_align(self, alignment):
        self.rich.setAlignment(alignment)
        self.rich.setFocus()

    def pick_color(self):
        col = QColorDialog.getColor(parent=self, title="Text colour")
        if col.isValid():
            self._merge(lambda fmt: fmt.setForeground(col))

    def pick_highlight(self):
        col = QColorDialog.getColor(parent=self, title="Highlight colour")
        if col.isValid():
            self._merge(lambda fmt: fmt.setBackground(col))

    # -- source / persistence ---------------------------------------------
    def source(self) -> str:
        return json.dumps({"kbook_note": 1,
                           "html": self.rich.toHtml(),
                           "ink": self.ink.to_dict()})

    def set_source(self, text: str):
        text = text or ""
        data = None
        stripped = text.lstrip()
        if stripped.startswith("{"):
            try:
                obj = json.loads(text)
                if isinstance(obj, dict) and ("kbook_note" in obj
                                              or "html" in obj):
                    data = obj
            except (ValueError, TypeError):
                data = None
        self.rich.blockSignals(True)
        if data is not None:
            self.rich.setHtml(data.get("html", ""))
            self.ink.from_dict(data.get("ink"))
        elif "<" in text and ">" in text:      # looks like HTML
            self.rich.setHtml(text)
        else:                                   # plain text / markdown source
            self.rich.setMarkdown(text) if text.strip() else \
                self.rich.setPlainText("")
        self.rich.blockSignals(False)
        self.rich._fit()
        self._sync_ink_geometry()

    def focus_editor(self):
        self.rich.setFocus()

    def show_find(self):
        # Find operates on the rich editor, not the hidden plain one.
        from .cells import _FindBar
        if self._find_bar is None:
            self._find_bar = _FindBar(self.rich)
            self.column.addWidget(self._find_bar)
        self._find_bar.open()


CELL_CLASSES["note"] = NoteCell
