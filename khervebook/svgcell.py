"""SVG drawing cell — renders an SVG and lets you draw on it.

A fifth cell type next to code/markdown/latex/sheet. Paste SVG source,
or drop a .svg file (KhervePaint, the sibling drawing app, saves .svg),
and the cell renders the drawing. A toolbar adds the usual tools — pen,
line, rectangle, ellipse, text, colour, stroke width, undo — which
append real SVG elements to the source so it always stays valid SVG.
"Open in KhervePaint" hands the drawing to the full drawing app and
reloads it when you export back to the same file.

Copyright (C) 2026 Gwilherm Kerherve

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.
"""

import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

from PyQt5.QtCore import (QByteArray, QPointF, QRectF, QSize, Qt, QTimer,
                          pyqtSignal)
from PyQt5.QtGui import QColor, QPainter, QPen, QPixmap, QPolygonF
from PyQt5.QtSvg import QSvgRenderer
from PyQt5.QtWidgets import (QColorDialog, QInputDialog, QMessageBox,
                             QSizePolicy, QWidget)

from .cells import CELL_CLASSES, CellWidget, XmlHighlighter
from .style import tokens

#: Starter SVG offered for a brand-new svg cell / the example.
STARTER_SVG = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 300 180">\n'
    '  <rect x="10" y="10" width="280" height="160" rx="12"\n'
    '        fill="#eaf1fb" stroke="#2176c7" stroke-width="2"/>\n'
    '  <circle cx="90" cy="90" r="45" fill="#50bea0"/>\n'
    '  <text x="170" y="96" font-size="22" fill="#2e3440">Hello SVG</text>\n'
    '</svg>')

#: A blank white canvas for a brand-new drawing (pick a tool and draw).
BLANK_SVG = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 800 500">\n'
    '  <rect x="0" y="0" width="800" height="500" fill="#ffffff"/>\n'
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
    pressed = pyqtSignal()           # mouse pressed (select the cell)

    #: comfortable minimum canvas so there's room to draw.
    MIN_CANVAS = 260

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
        self.show_grid = False       # draw a grid overlay
        self.snap = False            # snap drawing points to the grid
        self.grid_size = 20.0        # grid spacing, in SVG units
        policy = QSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        policy.setHeightForWidth(True)
        self.setSizePolicy(policy)
        self.setMinimumHeight(self.MIN_CANVAS)
        self.setFocusPolicy(Qt.ClickFocus)
        self.setCursor(Qt.CrossCursor)

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
        return max(self.MIN_CANVAS, int(w / max(0.2, self._aspect())))

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
        sx, sy = x + fx * w, y + fy * h
        if self.snap and self.grid_size > 0:
            sx = round(sx / self.grid_size) * self.grid_size
            sy = round(sy / self.grid_size) * self.grid_size
        return sx, sy

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
        if self.show_grid:
            self._draw_grid(p)
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

    def _draw_grid(self, p):
        """Paint a light grid (every grid_size SVG units) over the canvas."""
        x0, y0, w, h = self._vb()
        step = self.grid_size
        if step <= 0 or w <= 0 or h <= 0:
            return
        fine = QPen(QColor(0, 0, 0, 40), 0)
        bold = QPen(QColor(0, 0, 0, 80), 0)      # every 5th line, stronger
        p.setBrush(Qt.NoBrush)
        i = 0
        gx = x0 - (x0 % step)
        while gx <= x0 + w + 0.001:
            p.setPen(bold if i % 5 == 0 else fine)
            a, b = self._to_px(gx, y0), self._to_px(gx, y0 + h)
            p.drawLine(a, b)
            gx += step
            i += 1
        i = 0
        gy = y0 - (y0 % step)
        while gy <= y0 + h + 0.001:
            p.setPen(bold if i % 5 == 0 else fine)
            a, b = self._to_px(x0, gy), self._to_px(x0 + w, gy)
            p.drawLine(a, b)
            gy += step
            i += 1

    # -- mouse drawing -----------------------------------------------------
    def mousePressEvent(self, event):
        self.pressed.emit()          # focus/select the cell so its tools show
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
    """Renders and draws on an SVG. The drawing tools (select/pen/line/
    rect/ellipse/text, colour, width, undo) live in the main window's
    second toolbar row (CellToolBar) and drive this cell's methods."""

    CELL_TYPE = "svg"
    COMMENT = ("<!-- ", " -->")           # Ctrl+/ comment syntax (XML)

    #: (key, icon, tooltip) for the drawing tools, shown in the CellToolBar.
    TOOLS = (("select", "mdi.cursor-default-outline", "Select / double-click "
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
        self.view.pressed.connect(lambda: self.focused.emit(self))
        self.view.hide()
        self._paint_timer = None       # polls the KhervePaint round-trip file
        self._paint_tmp = None
        self._paint_proc = None
        self._paint_mtime = 0.0
        self.column.addWidget(self.view)
        # Show the drawing canvas straight away so there is always
        # something to draw on (a blank canvas for a new/empty cell).
        self.execute(None)

    # -- tool API (called by the CellToolBar) ------------------------------
    def set_tool(self, key: str):
        self.view.tool = key
        if self.view.isHidden():
            self.execute(None)              # render so there's a canvas
        self.focused.emit(self)

    def current_tool(self) -> str:
        return self.view.tool

    def pick_color(self):
        col = QColorDialog.getColor(self.view.color, self, "Stroke colour")
        if col.isValid():
            self.view.color = col

    def set_stroke_width(self, width: int):
        self.view.stroke_width = width

    def undo_shape(self):
        self.view.undo_shape()

    # -- grid / snap / canvas (called by the CellToolBar) ------------------
    def set_show_grid(self, on: bool):
        self.view.show_grid = bool(on)
        self.view.update()

    def grid_on(self) -> bool:
        return self.view.show_grid

    def set_snap(self, on: bool):
        self.view.snap = bool(on)

    def snap_on(self) -> bool:
        return self.view.snap

    def set_grid_size(self, size: float):
        self.view.grid_size = max(1.0, float(size))
        self.view.update()

    def grid_size(self) -> int:
        return int(self.view.grid_size)

    def canvas_size(self):
        """(width, height) of the drawing's SVG viewBox, rounded."""
        _x, _y, w, h = self.view._vb()
        return int(round(w)), int(round(h))

    def set_canvas_size(self, width=None, height=None):
        """Resize the drawing area: rewrite the SVG viewBox (and a full-page
        background rect, if any) to the new width/height."""
        if self.view.isHidden():
            self.execute(None)
        _x, _y, cw, ch = self.view._vb()
        nw = float(width) if width else cw
        nh = float(height) if height else ch
        if nw <= 0 or nh <= 0:
            return
        src = self.source()
        vb = f'viewBox="0 0 {nw:g} {nh:g}"'
        if re.search(r'viewBox="[^"]*"', src):
            src = re.sub(r'viewBox="[^"]*"', vb, src, count=1)
        else:
            src = re.sub(r'<svg\b', f'<svg {vb}', src, count=1)
        # Stretch a background rect that covers the old canvas from (0,0).
        src = re.sub(
            r'(<rect\b[^>]*\bx="0"[^>]*\by="0"[^>]*\bwidth=")[^"]*("[^>]*\b'
            r'height=")[^"]*(")',
            rf'\g<1>{nw:g}\g<2>{nh:g}\g<3>', src, count=1)
        self.set_source(src)
        self.execute(None)

    def insert_svg(self, element: str):
        """Append a ready-made SVG element (the Shape menu) and re-render."""
        if self.view.isHidden():
            self.execute(None)
        self.view._commit(element)

    def edit_source(self):
        self._edit_again()

    def insert_object(self, path):
        """Insert a KhervePaint library object (a saved .svg) into the
        drawing, placed near the top-left so it's visible."""
        from . import paintlibrary
        inner = paintlibrary.object_inner_svg(path)
        if inner:
            self.insert_svg(f'<g transform="translate(20,20)">{inner}</g>')

    def focus_editor(self):
        # Focusing an svg cell shows its canvas, not the raw source editor.
        if self.view.isHidden() and self.source().strip():
            self.execute(None)
        (self.view if not self.view.isHidden() else self.editor).setFocus()

    def execute(self, kernel):
        src = self.source().strip()
        if not src:
            src = BLANK_SVG                 # a fresh white canvas to draw on
            self.set_source(src)
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

    # -- KhervePaint round-trip --------------------------------------------
    def open_in_paint(self):
        repo = Path(__file__).resolve().parents[2] / "KhervePaint"
        if not (repo / "khervepaint" / "__main__.py").exists():
            QMessageBox.information(
                self, "KhervePaint",
                "KhervePaint was not found next to KherveBook "
                f"(looked in {repo}).")
            return
        tmp = Path(tempfile.gettempdir()) / f"khervebook_svg_{id(self)}.svg"
        tmp.write_text(self.source(), encoding="utf-8")
        venv = repo / ".venv" / (
            "Scripts/python.exe" if os.name == "nt" else "bin/python")
        python = str(venv) if venv.exists() else sys.executable
        try:
            self._paint_proc = subprocess.Popen(
                [python, "-m", "khervepaint", str(tmp)], cwd=str(repo))
        except Exception as exc:
            QMessageBox.warning(self, "KhervePaint",
                                f"Could not launch KhervePaint:\n{exc}")
            return
        # Poll the file for changes: a plain QFileSystemWatcher misses the
        # atomic save-replace many editors do on Windows, so a timer that
        # checks the modification time is far more reliable.
        self._paint_tmp = tmp
        try:
            self._paint_mtime = tmp.stat().st_mtime
        except OSError:
            self._paint_mtime = 0.0
        if self._paint_timer is None:
            self._paint_timer = QTimer(self)
            self._paint_timer.timeout.connect(self._poll_paint_file)
        self._paint_timer.start(700)
        QMessageBox.information(
            self, "Editing in KhervePaint",
            "This drawing is opening in KhervePaint.\n\nEdit it there, "
            "then Save (Ctrl+S) — KherveBook reloads it automatically.\n\n"
            "If it doesn't open on its own (older KhervePaint), use "
            "File ▸ Open on:\n" + str(tmp))

    def _poll_paint_file(self):
        """Reload the drawing when KhervePaint saves the shared file; stop
        polling once KhervePaint has closed (after a final reload)."""
        tmp = self._paint_tmp
        if tmp is None or not tmp.exists():
            return
        try:
            mtime = tmp.stat().st_mtime
        except OSError:
            return
        if mtime > self._paint_mtime:
            self._paint_mtime = mtime
            try:
                text = tmp.read_text(encoding="utf-8")
            except OSError:
                text = ""
            if "<svg" in text.lower():
                self.set_source(text)
                self.execute(None)
                self.content_changed.emit()
        if self._paint_proc is not None and self._paint_proc.poll() is not None:
            self._paint_timer.stop()       # KhervePaint closed


CELL_CLASSES["svg"] = SvgCell
