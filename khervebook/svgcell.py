"""SVG drawing cell — renders an SVG, e.g. one drawn in KhervePaint.

A fifth cell type next to code/markdown/latex/sheet. Paste SVG source,
or drop a .svg file (KhervePaint, the sibling paint app, saves .svg),
and the cell renders the drawing scaled to the cell width. Double-click
the drawing to edit its source again.

Copyright (C) 2026 Gwilherm Kerherve

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.
"""

from PyQt5.QtCore import QByteArray, QSize, Qt
from PyQt5.QtGui import QPainter, QPixmap
from PyQt5.QtSvg import QSvgRenderer

from .cells import CELL_CLASSES, CellWidget, _FitImage

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


class SvgCell(CellWidget):
    """Renders an SVG drawing; double-click to edit the source."""

    CELL_TYPE = "svg"
    COMMENT = ("<!-- ", " -->")           # Ctrl+/ comment syntax (XML)

    def __init__(self, source=""):
        super().__init__(source)
        self.gutter.setText("svg")
        self.view = _FitImage()           # scales the drawing to fit width
        self.view.setAlignment(Qt.AlignCenter)
        self.view.hide()
        self.view.mouseDoubleClickEvent = self._edit_again
        self.column.addWidget(self.view)

    def execute(self, kernel):
        src = self.source().strip()
        if not src:
            return
        self.editor.hide()
        pix = render_svg(src)
        if pix is None:
            self.view.setText("Invalid SVG — check the source.")
            self.view.setStyleSheet("color: #b71c1c;")
        else:
            self.view.setStyleSheet("")
            self.view.set_image(pix)
        self.view.show()

    def _edit_again(self, _event):
        self.view.hide()
        self.editor.show()
        self.editor.setFocus()


CELL_CLASSES["svg"] = SvgCell
