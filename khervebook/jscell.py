"""JavaScript / HTML cell rendered in a Chromium web view (QtWebEngine).

For interactive web visualisations matplotlib can't do — D3, Plotly,
ECharts, canvas, three.js. The editor holds JS or an HTML+JS snippet;
running it renders the page below. Needs PyQtWebEngine; without it the
cell shows a one-line hint instead of crashing.

Copyright (C) 2026 Gwilherm Kerherve

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.
"""

import os

from PyQt5.QtWidgets import QLabel, QSizePolicy

from .cells import CELL_CLASSES, CellWidget, JsHighlighter
from .style import tokens

#: A starter JS/canvas snippet for a fresh JavaScript cell.
JS_STARTER = (
    '<canvas id="c" width="360" height="180" '
    'style="border:1px solid #ccc"></canvas>\n'
    '<script>\n'
    'const ctx = document.getElementById("c").getContext("2d");\n'
    'ctx.fillStyle = "#3776ab";\n'
    'for (let x = 0; x < 360; x++) {\n'
    '    const y = 90 + 70 * Math.sin(x / 22);\n'
    '    ctx.fillRect(x, y, 2, 2);\n'
    '}\n'
    'ctx.fillStyle = "#e07b39";\n'
    'ctx.font = "16px sans-serif";\n'
    'ctx.fillText("Hello from JavaScript", 80, 28);\n'
    '</script>')

_PAGE = ("<!DOCTYPE html><html><head><meta charset='utf-8'>"
         "<style>body{{margin:6px;font-family:system-ui,Arial,sans-serif}}"
         "#kb_out{{white-space:pre-wrap;color:#333}}</style></head>"
         "<body>{body}</body></html>")

_HTML_HINTS = ("<html", "<body", "<svg", "<canvas", "<div", "<script",
               "<table", "<h1", "<h2", "<p>", "<style", "<!doctype")


def js_to_html(src: str) -> str:
    """Turn a cell's contents into a full HTML page.

    An HTML/JS snippet (has tags) loads as-is; a bare JavaScript program
    is wrapped in a page whose ``console.log`` output shows in the cell."""
    src = src or ""
    low = src.lower()
    if any(hint in low for hint in _HTML_HINTS):
        return src if "<html" in low or "<!doctype" in low \
            else _PAGE.format(body=src)
    body = ('<pre id="kb_out"></pre><script>\n'
            'const _p=(...a)=>{document.getElementById("kb_out").textContent'
            '+=a.map(String).join(" ")+"\\n";};\n'
            'console.log=_p;console.warn=_p;console.error=_p;\n'
            'try{\n' + src + '\n}catch(e){_p("Error: "+e.message);}\n'
            '</script>')
    return _PAGE.format(body=body)


class JsCell(CellWidget):
    """A JavaScript / HTML cell rendered in a web view."""

    CELL_TYPE = "js"
    COMMENT = ("// ", "")

    def __init__(self, source=""):
        super().__init__(source)
        self.gutter.setText("js")
        self._highlighter = JsHighlighter(self.editor.document(),
                                          dark=tokens()["dark"])
        self._web = None
        self._fallback = None

    def _ensure_view(self):
        """Create the web view (or a fallback label) lazily on first run."""
        if self._web is not None or self._fallback is not None:
            return
        os.environ.setdefault("QTWEBENGINE_CHROMIUM_FLAGS", "--no-sandbox")
        try:
            from PyQt5.QtWebEngineWidgets import QWebEngineView
            self._web = QWebEngineView()
            self._web.setMinimumHeight(300)
            self._web.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            self.column.addWidget(self._web)
        except Exception:
            self._fallback = QLabel(
                "JavaScript cells need PyQtWebEngine — install it with:\n"
                "    pip install PyQtWebEngine")
            self._fallback.setWordWrap(True)
            self.column.addWidget(self._fallback)

    def execute(self, kernel):
        self._ensure_view()
        if self._web is None:
            return
        from PyQt5.QtCore import QUrl
        self._web.setHtml(js_to_html(self.source()),
                          QUrl("https://kbook.local/"))
        self._web.show()


CELL_CLASSES["js"] = JsCell
