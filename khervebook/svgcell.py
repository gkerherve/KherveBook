"""SVG drawing cell — renders an SVG and lets you draw on it.

A fifth cell type next to code/markdown/latex/sheet. Paste SVG source,
or drop a .svg file (KherveScribe, the sibling drawing app, saves .svg),
and the cell renders the drawing. A toolbar adds the usual tools — pen,
line, rectangle, ellipse, text, colour, stroke width, undo — which
append real SVG elements to the source so it always stays valid SVG.
"Open in KherveScribe" hands the drawing to the full drawing app and
reloads it when you export back to the same file.

Copyright (C) 2026 Gwilherm Kerherve

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.
"""

import os
import subprocess
import sys
import tempfile
from pathlib import Path

from PyQt5.QtCore import (QByteArray, QFileSystemWatcher, QPointF, QRectF,
                          QSize, Qt, pyqtSignal)
from PyQt5.QtGui import QColor, QPainter, QPen, QPixmap, QPolygonF
from PyQt5.QtSvg import QSvgRenderer
from PyQt5.QtWidgets import (QColorDialog, QHBoxLayout, QInputDialog,
                             QMessageBox, QSizePolicy, QSpinBox, QToolButton,
                             QWidget)

from .cells import CELL_CLASSES, CellWidget, XmlHighlighter
from .icons import icon
from .style import tokens

#: Starter SVG offered for a brand-new svg cell / the example.
STARTER_SVG = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 300 180">\n'
    '  <rect x="10" y="10" width="280" height="160" rx="12"\n'
    '        fill="#eaf1fb" stroke="#2176c7" stroke-width="2"/>\n'
    '  <circle cx="90" cy="90" r="45" fill="#50bea0"/>\n'
    '  <text x="170" y="96" font-size="22" fill="#2e3440">Hello SVG</text>\n'
    '</svg>')


def render_svg(src: str, scale: int = 2):
    """SVG string -> QPixmap (rendered at *scale*x), or None if invalid."""
    renderer = QSvgRenderer(QByteArray(src.encode("utf-8")))
    if not renderer.isValid():
        return None
    size = renderer.defaultSize()
    if size.width() <= 0 or size.height() <= 0:
        size = QSize(400, 300)
    pix = QPixmap(size.width() * scale, size.height() * scale)
    pix.fill(Qt.transparent)
    painter = QPainter(pix)
    renderer.render(painter)
    painter.end()
    return pix


def _xml_escape(text: str) -> str:
    return (text.replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;"))


class _SvgDrawSurface(QWidget):
    """Renders the SVG (fit to width) and draws new elements onto it.

    Each completed shape is appended to the SVG source as a real element,
    so the source remains valid SVG and round-trips through .kbook."""

    changed = pyqtSignal()           # source modified by a drawing action
    edit_requested = pyqtSignal()    # double-click while the Select tool is on

    def __init__(self, parent=None):
        super().__init__(parent)
        self._src = ""
        self._renderer = None
        self.tool = "select"
        self.color = QColor("#2176c7")
        self.stroke_width = 3
        self._start = None
        self._cur = None
        self._pen_pts = []
        self._added = []             # appended element strings, for undo
        policy = QSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        policy.setHeightForWidth(True)
        self.setSizePolicy(policy)
        self.setMinimumHeight(80)

    # -- source ------------------------------------------------------------
    def set_svg(self, src: str):
        self._src = src or ""
        r = QSvgRenderer(QByteArray(self._src.encode("utf-8")))
        self._renderer = r if r.isValid() else None
        self.updateGeometry()
        self.update()

    def source(self) -> str:
        return self._src

    # -- geometry ----------------------------------------------------------
    def _vb(self):
        if self._renderer is None:
            return 0.0, 0.0, 100.0, 100.0
        vb = self._renderer.viewBoxF()
        if vb.width() > 0 and vb.height() > 0:
            return vb.x(), vb.y(), vb.width(), vb.height()
        sz = self._renderer.defaultSize()
        return 0.0, 0.0, float(sz.width() or 100), float(sz.height() or 100)

    def _aspect(self) -> float:
        _, _, w, h = self._vb()
        return (w / h) if h else 1.6

    def hasHeightForWidth(self):
        return True

    def heightForWidth(self, w):
        return max(80, int(w / max(0.2, self._aspect())))

    def sizeHint(self):
        w = self.width() or 400
        return QSize(w, self.heightForWidth(w))

    def _fit_rect(self) -> QRectF:
        w, h, ar = self.width(), self.height(), self._aspect()
        rw, rh = w, int(w / ar)
        if rh > h:
            rh, rw = h, int(h * ar)
        return QRectF((w - rw) / 2, 0, rw, rh)

    def _to_svg(self, pos):
        r = self._fit_rect()
        x, y, w, h = self._vb()
        fx = (pos.x() - r.x()) / r.width() if r.width() else 0
        fy = (pos.y() - r.y()) / r.height() if r.height() else 0
        return x + fx * w, y + fy * h

    def _to_px(self, sx, sy) -> QPointF:
        r = self._fit_rect()
        x, y, w, h = self._vb()
        return QPointF(r.x() + (sx - x) / w * r.width(),
                       r.y() + (sy - y) / h * r.height())

    def _scale(self) -> float:
        r = self._fit_rect()
        _, _, w, _ = self._vb()
        return r.width() / w if w else 1.0

    # -- painting ----------------------------------------------------------
    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        rect = self._fit_rect()
        if self._renderer is not None:
            self._renderer.render(p, rect)
        else:
            p.drawText(self.rect(), Qt.AlignCenter,
                       "Invalid SVG — edit the source.")
        if self.tool != "select" and (self._start or len(self._pen_pts) > 1):
            pen = QPen(self.color, max(1.0, self.stroke_width * self._scale()),
                       Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
            p.setPen(pen)
            p.setBrush(Qt.NoBrush)
            if self.tool == "pen" and len(self._pen_pts) > 1:
                p.drawPolyline(QPolygonF(
                    [self._to_px(x, y) for x, y in self._pen_pts]))
            elif self._start and self._cur:
                a, b = self._to_px(*self._start), self._to_px(*self._cur)
                if self.tool == "line":
                    p.drawLine(a, b)
                elif self.tool == "rect":
                    p.drawRect(QRectF(a, b).normalized())
                elif self.tool == "ellipse":
                    p.drawEllipse(QRectF(a, b).normalized())
        p.end()

    # -- mouse drawing -----------------------------------------------------
    def mousePressEvent(self, event):
        if self.tool == "select" or self._renderer is None:
            return
        sx, sy = self._to_svg(event.pos())
        if self.tool == "pen":
            self._pen_pts = [(sx, sy)]
        elif self.tool == "text":
            text, ok = QInputDialog.getText(self, "Add text", "Text:")
            if ok and text:
                self._commit(
                    f'<text x="{sx:.1f}" y="{sy:.1f}" '
                    f'font-size="{max(8, self.stroke_width * 5)}" '
                    f'fill="{self.color.name()}">{_xml_escape(text)}</text>')
        else:
            self._start = self._cur = (sx, sy)
        self.update()

    def mouseMoveEvent(self, event):
        if self.tool == "select":
            return
        sx, sy = self._to_svg(event.pos())
        if self.tool == "pen" and self._pen_pts:
            self._pen_pts.append((sx, sy))
            self.update()
        elif self._start:
            self._cur = (sx, sy)
            self.update()

    def mouseReleaseEvent(self, _event):
        if self.tool == "select":
            return
        if self.tool == "pen" and len(self._pen_pts) > 1:
            d = "M " + " L ".join(f"{x:.1f} {y:.1f}" for x, y in self._pen_pts)
            self._commit(
                f'<path d="{d}" fill="none" stroke="{self.color.name()}" '
                f'stroke-width="{self.stroke_width}" stroke-linecap="round" '
                f'stroke-linejoin="round"/>')
        elif self._start and self._cur:
            element = self._shape_element(self._start, self._cur)
            if element:
                self._commit(element)
        self._pen_pts, self._start, self._cur = [], None, None
        self.update()

    def mouseDoubleClickEvent(self, _event):
        if self.tool == "select":
            self.edit_requested.emit()

    def _shape_element(self, a, b):
        (x1, y1), (x2, y2) = a, b
        col, w = self.color.name(), self.stroke_width
        if self.tool == "line":
            return (f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" '
                    f'y2="{y2:.1f}" stroke="{col}" stroke-width="{w}" '
                    f'stroke-linecap="round"/>')
        x, y = min(x1, x2), min(y1, y2)
        ww, hh = abs(x2 - x1), abs(y2 - y1)
        if ww < 1 and hh < 1:
            return None
        if self.tool == "rect":
            return (f'<rect x="{x:.1f}" y="{y:.1f}" width="{ww:.1f}" '
                    f'height="{hh:.1f}" fill="none" stroke="{col}" '
                    f'stroke-width="{w}"/>')
        if self.tool == "ellipse":
            return (f'<ellipse cx="{x + ww / 2:.1f}" cy="{y + hh / 2:.1f}" '
                    f'rx="{ww / 2:.1f}" ry="{hh / 2:.1f}" fill="none" '
                    f'stroke="{col}" stroke-width="{w}"/>')
        return None

    def _commit(self, element):
        idx = self._src.rfind("</svg>")
        if idx == -1:
            new = self._src + "\n" + element
        else:
            new = self._src[:idx] + "  " + element + "\n" + self._src[idx:]
        self._added.append(element)
        self.set_svg(new)
        self.changed.emit()

    def undo_shape(self):
        if not self._added:
            return
        element = self._added.pop()
        self.set_svg(self._src.replace("  " + element + "\n", "", 1))
        self.changed.emit()


class SvgCell(CellWidget):
    """Renders and draws on an SVG; toolbar tools edit the source live."""

    CELL_TYPE = "svg"
    COMMENT = ("<!-- ", " -->")           # Ctrl+/ comment syntax (XML)

    _TOOLS = (("select", "mdi.cursor-default-outline", "Select / double-click "
               "the drawing to edit its source"),
              ("pen", "mdi.draw", "Freehand pen"),
              ("line", "mdi.vector-line", "Line"),
              ("rect", "mdi.rectangle-outline", "Rectangle"),
              ("ellipse", "mdi.ellipse-outline", "Ellipse"),
              ("text", "mdi.format-text", "Text"))

    def __init__(self, source=""):
        super().__init__(source)
        self.gutter.setText("svg")
        self._highlighter = XmlHighlighter(self.editor.document(),
                                           dark=tokens()["dark"])
        self.view = _SvgDrawSurface()
        self.view.changed.connect(self._on_drawn)
        self.view.edit_requested.connect(self._edit_again)
        self.view.hide()
        self._tool_buttons = {}
        self._watcher = None
        self.column.insertWidget(0, self._build_toolbar())
        self.column.addWidget(self.view)

    def _build_toolbar(self) -> QWidget:
        bar = QWidget()
        row = QHBoxLayout(bar)
        row.setContentsMargins(0, 0, 0, 2)
        row.setSpacing(2)
        for key, icon_name, tip in self._TOOLS:
            btn = QToolButton()
            btn.setIcon(icon(icon_name))
            btn.setToolTip(tip)
            btn.setCheckable(True)
            btn.setAutoRaise(True)
            btn.setChecked(key == "select")
            btn.clicked.connect(lambda _=False, k=key: self._set_tool(k))
            row.addWidget(btn)
            self._tool_buttons[key] = btn
        self._color_btn = QToolButton()
        self._color_btn.setToolTip("Stroke / text colour")
        self._color_btn.setAutoRaise(True)
        self._color_btn.clicked.connect(self._pick_color)
        self._refresh_color_btn()
        row.addWidget(self._color_btn)
        self._width_spin = QSpinBox()
        self._width_spin.setRange(1, 40)
        self._width_spin.setValue(3)
        self._width_spin.setToolTip("Stroke width")
        self._width_spin.valueChanged.connect(
            lambda v: setattr(self.view, "stroke_width", v))
        row.addWidget(self._width_spin)
        undo = QToolButton()
        undo.setIcon(icon("mdi.undo"))
        undo.setToolTip("Undo last drawn shape")
        undo.setAutoRaise(True)
        undo.clicked.connect(self.view.undo_shape)
        row.addWidget(undo)
        row.addStretch(1)
        edit = QToolButton()
        edit.setIcon(icon("mdi.code-tags"))
        edit.setToolTip("Edit the SVG source")
        edit.setAutoRaise(True)
        edit.clicked.connect(self._edit_again)
        row.addWidget(edit)
        scribe = QToolButton()
        scribe.setIcon(icon("mdi.draw-pen"))
        scribe.setToolTip("Open in KherveScribe (the full drawing app)")
        scribe.setAutoRaise(True)
        scribe.clicked.connect(self.open_in_scribe)
        row.addWidget(scribe)
        return bar

    def _set_tool(self, key):
        self.view.tool = key
        for k, btn in self._tool_buttons.items():
            btn.setChecked(k == key)
        if key != "select" and self.view.isHidden():
            self.execute(None)              # render so there's a canvas to draw on

    def _pick_color(self):
        col = QColorDialog.getColor(self.view.color, self, "Stroke colour")
        if col.isValid():
            self.view.color = col
            self._refresh_color_btn()

    def _refresh_color_btn(self):
        self._color_btn.setStyleSheet(
            f"QToolButton{{background:{self.view.color.name()};"
            f"border:1px solid #888;border-radius:3px;min-width:20px;"
            f"min-height:18px}}")

    def execute(self, kernel):
        src = self.source().strip()
        if not src:
            return
        self.editor.hide()
        self.view.set_svg(src)
        self.view.show()

    def _on_drawn(self):
        """A drawing tool changed the SVG: sync it back to the editor."""
        self.editor.blockSignals(True)
        self.editor.setPlainText(self.view.source())
        self.editor.blockSignals(False)
        self.content_changed.emit()

    def _edit_again(self, _event=None):
        self.view.hide()
        self.editor.show()
        self.editor.setFocus()

    # -- KherveScribe round-trip -------------------------------------------
    def open_in_scribe(self):
        repo = Path(__file__).resolve().parents[2] / "KhervePaint"
        if not (repo / "khervescribe" / "__main__.py").exists():
            QMessageBox.information(
                self, "KherveScribe",
                "KherveScribe was not found next to KherveBook "
                f"(looked in {repo}).")
            return
        tmp = Path(tempfile.gettempdir()) / f"khervebook_svg_{id(self)}.svg"
        tmp.write_text(self.source(), encoding="utf-8")
        venv = repo / ".venv" / (
            "Scripts/python.exe" if os.name == "nt" else "bin/python")
        python = str(venv) if venv.exists() else sys.executable
        try:
            subprocess.Popen([python, "-m", "khervescribe", str(tmp)],
                             cwd=str(repo))
        except Exception as exc:
            QMessageBox.warning(self, "KherveScribe",
                                f"Could not launch KherveScribe:\n{exc}")
            return
        if self._watcher is None:
            self._watcher = QFileSystemWatcher(self)
            self._watcher.fileChanged.connect(self._on_scribe_saved)
        self._watcher.addPath(str(tmp))
        QMessageBox.information(
            self, "Editing in KherveScribe",
            "A copy of this drawing was written to:\n\n" + str(tmp) +
            "\n\nIn KherveScribe: Open that file, edit it, then Export "
            "as SVG back to the same path — it will reload here.")

    def _on_scribe_saved(self, path):
        try:
            text = Path(path).read_text(encoding="utf-8")
        except Exception:
            return
        if "<svg" in text.lower():
            self.set_source(text)
            self.execute(None)
            self.content_changed.emit()
        if path not in self._watcher.files():   # some saves replace the file
            self._watcher.addPath(path)


CELL_CLASSES["svg"] = SvgCell
