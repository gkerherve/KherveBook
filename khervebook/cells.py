"""Notebook cell widgets: code, markdown, and LaTeX.

Each cell is a frame with a type-specific editor and (for code cells)
an output area. Shift+Enter runs/renders the cell and asks the
notebook to advance to the next one.

Copyright (C) 2026 Gwilherm Kerherve

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.
"""

import io
import re

from PyQt5.QtCore import QEvent, QSize, Qt, QThread, pyqtSignal
from PyQt5.QtGui import (QColor, QFont, QFontMetrics, QPainter, QPixmap,
                         QSyntaxHighlighter, QTextCharFormat, QTextCursor,
                         QTextDocument)
from PyQt5.QtWidgets import (QAction, QFrame, QHBoxLayout, QLabel, QLineEdit,
                             QPlainTextEdit, QScrollArea, QSizePolicy,
                             QTextBrowser, QToolButton, QVBoxLayout, QWidget)

from . import hltheme, thesaurus

from .icons import icon

MONO = QFont("Consolas", 10)


class _AutoScroll(QScrollArea):
    """Sizes to its content, until a height cap is set — then it scrolls.

    Auto mode (cap None) reports the content's height as its size hint,
    so the cell is exactly as tall as it needs. With a cap, the area
    fixes to that height and the content scrolls inside it.
    """

    def __init__(self, inner, parent=None):
        super().__init__(parent)
        self.setWidget(inner)
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.NoFrame)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        # Transparent so cell content sits on the white cell card, not the
        # grey notebook background painted behind transparent widgets.
        self.viewport().setStyleSheet("background: transparent;")
        self._cap = None
        inner.installEventFilter(self)
        self._refresh()

    def set_cap(self, height):
        self._cap = max(60, int(height)) if height else None
        self.setVerticalScrollBarPolicy(
            Qt.ScrollBarAsNeeded if self._cap else Qt.ScrollBarAlwaysOff)
        self._refresh()

    @property
    def cap(self):
        return self._cap

    def _content_height(self):
        w = self.widget()
        return w.sizeHint().height() if w is not None else 0

    def _refresh(self):
        """Track content height directly so the cell height is exact."""
        h = self._content_height()
        if self._cap is not None:
            h = min(h, self._cap)
        self.setFixedHeight(h)

    def eventFilter(self, obj, event):
        if obj is self.widget() and event.type() == QEvent.LayoutRequest:
            self._refresh()
        return super().eventFilter(obj, event)


class _ResizeGrip(QWidget):
    """Thin drag handle at the bottom of a cell to cap/auto its height."""

    def __init__(self, cell):
        super().__init__(cell)
        self._cell = cell
        self.setFixedHeight(11)
        self.setCursor(Qt.SizeVerCursor)
        self.setToolTip("Drag to resize height; double-click to auto-fit")
        self._press_y = None
        self._start_h = 0
        self._hover = False

    def enterEvent(self, _event):
        self._hover = True
        self.update()

    def leaveEvent(self, _event):
        self._hover = False
        self.update()

    def paintEvent(self, _event):
        from PyQt5.QtGui import QPainter
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor("#5a6b7a") if self._hover
                         else QColor("#c4ccd4"))
        w = min(44, max(24, self.width() // 4))
        x = (self.width() - w) // 2
        y = (self.height() - 4) // 2
        painter.drawRoundedRect(x, y, w, 4, 2, 2)
        painter.end()

    def mousePressEvent(self, event):
        self._press_y = event.globalY()
        self._start_h = self._cell._resize_region_height()

    def mouseMoveEvent(self, event):
        if self._press_y is not None:
            self._cell.set_content_height(
                self._start_h + event.globalY() - self._press_y)

    def mouseReleaseEvent(self, _event):
        self._press_y = None

    def mouseDoubleClickEvent(self, _event):
        self._cell.set_content_height(None)


class _WidthGrip(QWidget):
    """Thin handle on a cell's right edge to set its width (drag), or
    double-click to fill the row again. Widening past the window scrolls
    the notebook horizontally."""

    def __init__(self, cell):
        super().__init__(cell)
        self._cell = cell
        self.setFixedWidth(11)
        self.setCursor(Qt.SizeHorCursor)
        self.setToolTip("Drag to resize width; double-click to auto")
        self._press_x = None
        self._start_w = 0
        self._hover = False

    def enterEvent(self, _event):
        self._hover = True
        self.update()

    def leaveEvent(self, _event):
        self._hover = False
        self.update()

    def paintEvent(self, _event):
        from PyQt5.QtGui import QPainter
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor("#5a6b7a") if self._hover
                         else QColor("#c4ccd4"))
        h = min(44, max(24, self.height() // 4))
        x = (self.width() - 4) // 2
        y = (self.height() - h) // 2
        painter.drawRoundedRect(x, y, 4, h, 2, 2)
        painter.end()

    def mousePressEvent(self, event):
        self._press_x = event.globalX()
        self._start_w = self._cell.width()

    def mouseMoveEvent(self, event):
        if self._press_x is not None:
            self._cell.set_content_width(
                self._start_w + event.globalX() - self._press_x)

    def mouseReleaseEvent(self, _event):
        self._press_x = None
        self._cell.resized.emit()         # relayout: align + scroll

    def mouseDoubleClickEvent(self, _event):
        self._cell.set_content_width(None)
        self._cell.resized.emit()


class PythonHighlighter(QSyntaxHighlighter):
    """Rich, colourful Python syntax highlighting for code cell editors:
    control flow, keywords, builtins, constants, decorators, def/class
    names, calls, self/cls, numbers, strings (incl. multi-line
    docstrings) and comments each get their own colour. The palette is
    a named theme from ``hltheme`` (default: follow the app theme)."""

    _CONTROL = ("if elif else for while break continue return yield pass "
                "try except finally raise with async await").split()
    _KEYWORDS = ("def class lambda import from as global nonlocal del assert "
                 "in is and or not").split()
    _CONSTANTS = "True False None Ellipsis NotImplemented".split()
    _BUILTINS = (
        "print len range list dict set tuple int float str bool bytes "
        "enumerate zip map filter sum min max abs round sorted reversed "
        "open isinstance issubclass type super object property staticmethod "
        "classmethod hasattr getattr setattr delattr callable iter next id "
        "hash repr format input all any divmod pow chr ord bin hex oct vars "
        "frozenset complex slice globals locals dir help "
        "Exception ValueError TypeError KeyError IndexError RuntimeError "
        "AttributeError ImportError OSError StopIteration ZeroDivisionError "
        "FileNotFoundError NotImplementedError").split()

    #: colour per token category, per app-theme brightness (in hltheme).
    LIGHT = hltheme.AUTO_LIGHT
    DARK = hltheme.AUTO_DARK

    #: single-line string (with r/b/f/u prefixes) and triple delimiters.
    _STRING = (r"(?<!\w)[rbfuRBFU]{0,2}"
               r"""(?:'(?:[^'\\]|\\.)*'|"(?:[^"\\]|\\.)*")""")

    def __init__(self, document, dark=False, theme=hltheme.AUTO):
        super().__init__(document)
        self._dark = dark
        self.theme = theme
        self._build_rules()

    def _fmt(self, color, bold=False, italic=False):
        f = QTextCharFormat()
        f.setForeground(QColor(color))
        if bold:
            f.setFontWeight(QFont.Bold)
        if italic:
            f.setFontItalic(True)
        return f

    @staticmethod
    def _words(words):
        return r"\b(?:%s)\b" % "|".join(words)

    def _build_rules(self):
        c = hltheme.resolve(self.theme, self._dark)
        self._rules = []            # (compiled pattern, format, capture group)

        def add(pattern, fmt, group=0):
            self._rules.append((re.compile(pattern), fmt, group))

        # Calls first so keywords/builtins repaint over them (print stays teal).
        add(r"\b([A-Za-z_]\w*)\s*(?=\()", self._fmt(c["call"]), 1)
        add(r"\bdef\s+([A-Za-z_]\w*)", self._fmt(c["defname"], bold=True), 1)
        add(r"\bclass\s+([A-Za-z_]\w*)",
            self._fmt(c["classname"], bold=True), 1)
        add(r"^\s*(@[A-Za-z_][\w.]*)", self._fmt(c["decorator"]), 1)
        add(self._words(self._BUILTINS), self._fmt(c["builtin"]))
        add(self._words(self._CONSTANTS), self._fmt(c["constant"]))
        add(self._words(self._CONTROL), self._fmt(c["control"], bold=True))
        add(self._words(self._KEYWORDS), self._fmt(c["keyword"], bold=True))
        add(r"\b(?:self|cls)\b", self._fmt(c["selfcls"], italic=True))
        add(r"\b(?:0[xXoObB][0-9a-fA-F_]+|"
            r"\d[\d_]*\.?[\d_]*(?:[eE][+-]?\d+)?j?)\b", self._fmt(c["number"]))
        add(self._STRING, self._fmt(c["string"]))
        add(r"#[^\n]*", self._fmt(c["comment"], italic=True))
        self._str_fmt = self._fmt(c["string"])

    def set_dark(self, dark: bool):
        self._dark = dark
        self._build_rules()
        self.rehighlight()

    def set_theme(self, name: str):
        self.theme = name
        self._build_rules()
        self.rehighlight()

    def highlightBlock(self, text):
        for pattern, fmt, group in self._rules:
            for m in pattern.finditer(text):
                start, end = m.span(group)
                if start >= 0:
                    self.setFormat(start, end - start, fmt)
        self._highlight_triple(text)

    def _highlight_triple(self, text):
        """Colour multi-line triple-quoted strings/docstrings across blocks
        (state 1 = inside \"\"\", state 2 = inside ''')."""
        self.setCurrentBlockState(0)
        n, i = len(text), 0
        prev = self.previousBlockState()
        if prev in (1, 2):                       # continuing an open string
            delim = '"""' if prev == 1 else "'''"
            j = text.find(delim)
            if j == -1:
                self.setFormat(0, n, self._str_fmt)
                self.setCurrentBlockState(prev)
                return
            self.setFormat(0, j + 3, self._str_fmt)
            i = j + 3
        while i < n:
            d1, d2 = text.find('"""', i), text.find("'''", i)
            if d1 == -1 and d2 == -1:
                break
            if d2 == -1 or (d1 != -1 and d1 < d2):
                start, delim, state = d1, '"""', 1
            else:
                start, delim, state = d2, "'''", 2
            end = text.find(delim, start + 3)
            if end == -1:                        # opens here, closes later
                self.setFormat(start, n - start, self._str_fmt)
                self.setCurrentBlockState(state)
                return
            self.setFormat(start, end + 3 - start, self._str_fmt)
            i = end + 3


class LatexHighlighter(QSyntaxHighlighter):
    """Highlights LaTeX commands, math, braces and comments."""

    #: (command, math, brace, comment) per background brightness.
    LIGHT = ("#0000C0", "#0b7261", "#9a6700", "#808080")
    DARK = ("#6f9fff", "#5ec8b0", "#d0a050", "#8a939c")

    def __init__(self, document, dark=False):
        super().__init__(document)
        self._build_rules(dark)

    def _build_rules(self, dark: bool):
        cmd_c, math_c, brace_c, com_c = self.DARK if dark else self.LIGHT
        self._rules = []
        # Inline math first (base tint); commands then show through it.
        math = QTextCharFormat()
        math.setForeground(QColor(math_c))
        self._rules.append((re.compile(r"(?<!\\)\$[^$]*\$"), math))
        cmd = QTextCharFormat()
        cmd.setForeground(QColor(cmd_c))
        cmd.setFontWeight(QFont.Bold)
        self._rules.append((re.compile(r"\\[a-zA-Z@]+\*?"), cmd))
        self._rules.append((re.compile(r"\\[^a-zA-Z\s]"), cmd))   # \\ \{ \%
        brace = QTextCharFormat()
        brace.setForeground(QColor(brace_c))
        self._rules.append((re.compile(r"[{}\[\]]"), brace))
        com = QTextCharFormat()                                   # wins last
        com.setForeground(QColor(com_c))
        com.setFontItalic(True)
        self._rules.append((re.compile(r"(?<!\\)%.*$"), com))

    def set_dark(self, dark: bool):
        self._build_rules(dark)
        self.rehighlight()

    def highlightBlock(self, text):
        for pattern, fmt in self._rules:
            for m in pattern.finditer(text):
                self.setFormat(m.start(), m.end() - m.start(), fmt)


class MarkdownHighlighter(QSyntaxHighlighter):
    """Highlights markdown headings, emphasis, code, links and HTML."""

    #: (heading, code, link, marker, html) per background brightness.
    LIGHT = ("#0000C0", "#A31515", "#1a6e8e", "#9a6700", "#0b7261")
    DARK = ("#6f9fff", "#e8907e", "#5ec8b0", "#d0a050", "#6ccb9e")

    def __init__(self, document, dark=False):
        super().__init__(document)
        self._build_rules(dark)

    def _build_rules(self, dark: bool):
        head_c, code_c, link_c, mark_c, html_c = (
            self.DARK if dark else self.LIGHT)
        self._rules = []
        bold = QTextCharFormat()
        bold.setFontWeight(QFont.Bold)
        self._rules.append((re.compile(r"\*\*.+?\*\*|__.+?__"), bold))
        ital = QTextCharFormat()
        ital.setFontItalic(True)
        self._rules.append(
            (re.compile(r"(?<!\*)\*(?!\*)[^*\n]+?\*(?!\*)"), ital))
        strike = QTextCharFormat()
        strike.setFontStrikeOut(True)
        self._rules.append((re.compile(r"~~.+?~~"), strike))
        code = QTextCharFormat()
        code.setForeground(QColor(code_c))
        code.setFontFamily("Consolas")
        self._rules.append((re.compile(r"`[^`]+`"), code))
        link = QTextCharFormat()
        link.setForeground(QColor(link_c))
        link.setFontUnderline(True)
        self._rules.append((re.compile(r"\[[^\]]*\]\([^)]*\)"), link))
        html = QTextCharFormat()
        html.setForeground(QColor(html_c))
        self._rules.append((re.compile(r"</?[a-zA-Z][^>]*>"), html))
        mark = QTextCharFormat()
        mark.setForeground(QColor(mark_c))
        mark.setFontWeight(QFont.Bold)
        self._rules.append((re.compile(r"^\s*([-*+]|\d+\.)\s"), mark))
        self._rules.append((re.compile(r"^\s*>\s?"), mark))
        head = QTextCharFormat()                                  # whole line
        head.setForeground(QColor(head_c))
        head.setFontWeight(QFont.Bold)
        self._rules.append((re.compile(r"^#{1,6}\s.*$"), head))

    def set_dark(self, dark: bool):
        self._build_rules(dark)
        self.rehighlight()

    def highlightBlock(self, text):
        for pattern, fmt in self._rules:
            for m in pattern.finditer(text):
                self.setFormat(m.start(), m.end() - m.start(), fmt)


def _highlight_multiline(hl, text, start_re, end_re, fmt, state):
    """Colour multi-line regions (e.g. block comments) across blocks.

    ``hl`` is the QSyntaxHighlighter; a region runs from ``start_re`` to
    ``end_re`` and continues over line breaks via block state ``state``.
    Call this last in ``highlightBlock`` so it overrides single-line rules
    inside the region."""
    hl.setCurrentBlockState(0)
    if hl.previousBlockState() == state:
        start = 0
    else:
        m = start_re.search(text)
        start = m.start() if m else -1
    while start >= 0:
        m = end_re.search(text, start)
        if m:
            length = m.end() - start
            nxt = start_re.search(text, m.end())
            new_start = nxt.start() if nxt else -1
        else:
            length = len(text) - start
            hl.setCurrentBlockState(state)
            new_start = -1
        hl.setFormat(start, length, fmt)
        start = new_start


class XmlHighlighter(QSyntaxHighlighter):
    """Highlights SVG/XML tags, attributes, values and comments."""

    #: (tag, attribute, value, comment) per background brightness.
    LIGHT = ("#0000C0", "#9a6700", "#A31515", "#808080")
    DARK = ("#6f9fff", "#d0a050", "#e8907e", "#8a939c")

    _COM_START = re.compile(r"<!--")
    _COM_END = re.compile(r"-->")

    def __init__(self, document, dark=False):
        super().__init__(document)
        self._build_rules(dark)

    def _build_rules(self, dark: bool):
        tag_c, attr_c, val_c, com_c = self.DARK if dark else self.LIGHT
        self._rules = []
        tag = QTextCharFormat()
        tag.setForeground(QColor(tag_c))
        tag.setFontWeight(QFont.Bold)
        self._rules.append((re.compile(r"</?\s*[\w:.-]+"), tag))   # <tag </tag
        self._rules.append((re.compile(r"/?>"), tag))              # > />
        attr = QTextCharFormat()
        attr.setForeground(QColor(attr_c))
        self._rules.append((re.compile(r"[\w:.-]+(?=\s*=)"), attr))
        val = QTextCharFormat()
        val.setForeground(QColor(val_c))
        self._rules.append((re.compile(r"\"[^\"]*\"|'[^']*'"), val))
        self._com_fmt = QTextCharFormat()
        self._com_fmt.setForeground(QColor(com_c))
        self._com_fmt.setFontItalic(True)

    def set_dark(self, dark: bool):
        self._build_rules(dark)
        self.rehighlight()

    def highlightBlock(self, text):
        for pattern, fmt in self._rules:
            for m in pattern.finditer(text):
                self.setFormat(m.start(), m.end() - m.start(), fmt)
        _highlight_multiline(self, text, self._COM_START, self._COM_END,
                             self._com_fmt, 1)


class JsHighlighter(QSyntaxHighlighter):
    """Highlights JavaScript (plus embedded HTML tags) for js cells."""

    _KEYWORDS = (
        "var let const function return if else for while do switch case "
        "break continue new delete typeof instanceof in of this class "
        "extends super import export default from await async yield void "
        "try catch finally throw null true false undefined").split()

    #: (keyword, number, string, comment, tag) per background brightness.
    LIGHT = ("#0000C0", "#098658", "#A31515", "#808080", "#0b7261")
    DARK = ("#6f9fff", "#6ccb9e", "#e8907e", "#8a939c", "#5ec8b0")

    _COM_START = re.compile(r"/\*")
    _COM_END = re.compile(r"\*/")

    def __init__(self, document, dark=False):
        super().__init__(document)
        self._build_rules(dark)

    def _build_rules(self, dark: bool):
        kw_c, num_c, str_c, com_c, tag_c = self.DARK if dark else self.LIGHT
        self._rules = []
        tag = QTextCharFormat()                                    # HTML tags
        tag.setForeground(QColor(tag_c))
        # A real delimiter must follow the name so `a<b` isn't seen as a tag.
        self._rules.append(
            (re.compile(r"</?[a-zA-Z][\w-]*(?=[\s/>])"), tag))
        kw = QTextCharFormat()
        kw.setForeground(QColor(kw_c))
        kw.setFontWeight(QFont.Bold)
        for word in self._KEYWORDS:
            self._rules.append((re.compile(rf"\b{word}\b"), kw))
        num = QTextCharFormat()
        num.setForeground(QColor(num_c))
        self._rules.append(
            (re.compile(r"\b0x[0-9a-fA-F]+\b|\b\d+(\.\d+)?\b"), num))
        com = QTextCharFormat()                       # // — skip URL slashes
        com.setForeground(QColor(com_c))
        com.setFontItalic(True)
        self._rules.append((re.compile(r"(?<!:)//[^\n]*"), com))
        s = QTextCharFormat()                         # strings win over the
        s.setForeground(QColor(str_c))                # rules above (last)
        self._rules.append(
            (re.compile(r"\"[^\"]*\"|'[^']*'|`[^`]*`"), s))
        self._com_fmt = QTextCharFormat()
        self._com_fmt.setForeground(QColor(com_c))
        self._com_fmt.setFontItalic(True)

    def set_dark(self, dark: bool):
        self._build_rules(dark)
        self.rehighlight()

    def highlightBlock(self, text):
        for pattern, fmt in self._rules:
            for m in pattern.finditer(text):
                self.setFormat(m.start(), m.end() - m.start(), fmt)
        _highlight_multiline(self, text, self._COM_START, self._COM_END,
                             self._com_fmt, 1)


class _FitImage(QLabel):
    """An image that always scales to fill its width (keeping aspect),
    re-fitting whenever the cell is resized — no side margins."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._orig = None
        self._last_w = -1
        self.setAlignment(Qt.AlignCenter)
        self.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Fixed)

    def set_image(self, pixmap):
        self._orig = pixmap
        self._last_w = -1
        self._rescale()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self._orig is not None and self.width() != self._last_w:
            self._rescale()

    def _rescale(self):
        if self._orig is None or self._orig.isNull():
            return
        self._last_w = self.width()
        scaled = self._orig.scaledToWidth(max(1, self.width()),
                                          Qt.SmoothTransformation)
        super().setPixmap(scaled)
        self.setFixedHeight(scaled.height())


class _LineNumberArea(QWidget):
    """Gutter that paints line numbers down the left of a code editor."""

    def __init__(self, editor):
        super().__init__(editor)
        self._editor = editor

    def sizeHint(self):
        return QSize(self._editor._lna_width(), 0)

    def paintEvent(self, event):
        self._editor._paint_line_numbers(event)


class _GrowingEdit(QPlainTextEdit):
    """Editor that grows with its content, up to MAX_ROWS lines —
    beyond that it scrolls internally instead of swallowing the page."""

    MAX_ROWS = 25
    run_requested = pyqtSignal()

    def __init__(self, text=""):
        super().__init__(text)
        self.setFont(MONO)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self._lna = None                     # line-number gutter (code cells)
        self.textChanged.connect(self._resize)
        self._resize()

    def keyPressEvent(self, event):
        if (event.key() in (Qt.Key_Return, Qt.Key_Enter)
                and event.modifiers() & Qt.ShiftModifier):
            self.run_requested.emit()
            return
        if (event.key() == Qt.Key_Slash
                and event.modifiers() & Qt.ControlModifier):
            self.toggle_comment()
            return
        if (event.key() == Qt.Key_F
                and event.modifiers() & Qt.ControlModifier):
            cell = getattr(self, "cell", None)
            if cell is not None and hasattr(cell, "show_find"):
                cell.show_find()
                return
        super().keyPressEvent(event)

    # -- line numbers ------------------------------------------------------
    def enable_line_numbers(self):
        if self._lna is not None:
            return
        self._lna = _LineNumberArea(self)
        self.blockCountChanged.connect(lambda _=0: self._update_lna_width())
        self.updateRequest.connect(self._on_update_request)
        self._update_lna_width()

    def _lna_width(self) -> int:
        digits = max(2, len(str(max(1, self.blockCount()))))
        return 12 + QFontMetrics(self.font()).horizontalAdvance("9") * digits

    def _update_lna_width(self):
        if self._lna is not None:
            self.setViewportMargins(self._lna_width(), 0, 0, 0)

    def _on_update_request(self, rect, dy):
        if self._lna is None:
            return
        if dy:
            self._lna.scroll(0, dy)
        else:
            self._lna.update(0, rect.y(), self._lna.width(), rect.height())

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self._lna is not None:
            cr = self.contentsRect()
            self._lna.setGeometry(cr.left(), cr.top(),
                                  self._lna_width(), cr.height())

    def _paint_line_numbers(self, event):
        custom = getattr(self, "_gutter_colors", None)
        if custom:                     # an explicit highlight theme's colours
            bg, fg = custom
        else:
            from .style import tokens
            t = tokens()
            bg = t["editor"]
            fg = t["icon"] if t["dark"] else t["border"]
        painter = QPainter(self._lna)
        painter.fillRect(event.rect(), QColor(bg))
        painter.setPen(QColor(fg))
        block = self.firstVisibleBlock()
        top = self.blockBoundingGeometry(block).translated(
            self.contentOffset()).top()
        height = QFontMetrics(self.font()).height()
        num = block.blockNumber()
        while block.isValid() and top <= event.rect().bottom():
            bottom = top + self.blockBoundingRect(block).height()
            if block.isVisible() and bottom >= event.rect().top():
                painter.drawText(0, int(top), self._lna.width() - 5, height,
                                 Qt.AlignRight | Qt.AlignVCenter, str(num + 1))
            block = block.next()
            top = bottom
            num += 1

    def toggle_comment(self):
        """Comment/uncomment the selected lines using the cell's syntax
        (# for Python, % for LaTeX, <!-- --> for Markdown)."""
        cell = getattr(self, "cell", None)
        prefix, suffix = getattr(cell, "COMMENT", ("# ", ""))
        p, sfx = prefix.strip(), suffix.strip()
        doc = self.document()
        cur = self.textCursor()
        first = doc.findBlock(cur.selectionStart()).blockNumber()
        last = doc.findBlock(cur.selectionEnd()).blockNumber()
        blocks = [doc.findBlockByNumber(b) for b in range(first, last + 1)]

        def commented(text):
            t = text.strip()
            return t.startswith(p) and (not sfx or t.endswith(sfx))

        non_empty = [b.text() for b in blocks if b.text().strip()]
        remove = bool(non_empty) and all(commented(t) for t in non_empty)

        def transform(text):
            indent = text[:len(text) - len(text.lstrip())]
            body = text[len(indent):]
            if remove:
                if body.startswith(prefix):
                    body = body[len(prefix):]
                elif body.startswith(p):
                    body = body[len(p):].lstrip(" ")
                if suffix and body.endswith(suffix):
                    body = body[:-len(suffix)]
                elif sfx and body.rstrip().endswith(sfx):
                    body = body[:body.rstrip().rfind(sfx)].rstrip()
            else:
                body = prefix + body + suffix
            return indent + body

        cur.beginEditBlock()
        for block in blocks:
            if not block.text().strip():
                continue
            edit = QTextCursor(block)
            edit.select(QTextCursor.LineUnderCursor)
            edit.insertText(transform(block.text()))
        cur.endEditBlock()

    def dragEnterEvent(self, event):
        # Let file drops reach the parent cell; keep text drags local.
        if event.mimeData().hasUrls():
            event.ignore()
        else:
            super().dragEnterEvent(event)

    def contextMenuEvent(self, event):
        """Standard edit menu with Run Cell, Find, and (for prose cells)
        a Synonyms submenu for the word under the cursor."""
        menu = self.createStandardContextMenu()
        cell = getattr(self, "cell", None)
        first = menu.actions()[0] if menu.actions() else None
        if cell is not None:
            run = QAction("Run Cell", menu)
            run.triggered.connect(lambda: cell.run_clicked.emit(cell))
            menu.insertAction(first, run)
            menu.insertSeparator(first)
            find = QAction("Find…", menu)
            find.setShortcut("Ctrl+F")
            find.triggered.connect(cell.show_find)
            menu.addSeparator()
            menu.addAction(find)
            if getattr(cell, "CELL_TYPE", "") in ("markdown", "latex"):
                self._add_synonyms(menu, event.pos())
            if hasattr(cell, "choose_highlight_theme"):
                self._add_highlight_themes(menu, cell)
        menu.exec_(event.globalPos())

    def _add_highlight_themes(self, menu, cell):
        """Submenu of code highlight themes; picking one restyles every
        code cell and persists app-wide."""
        sub = menu.addMenu("Highlight Theme")
        current = cell._highlighter.theme
        for name in hltheme.theme_names():
            act = sub.addAction(name)
            act.setCheckable(True)
            act.setChecked(name == current)
            act.triggered.connect(
                lambda _=False, n=name: cell.choose_highlight_theme(n))

    def _add_synonyms(self, menu, pos):
        """Add a Synonyms submenu for the word at *pos* (fetched on open)."""
        cur = self.cursorForPosition(pos)
        cur.select(QTextCursor.WordUnderCursor)
        word = cur.selectedText().strip()
        if not word.isalpha():
            return
        sub = menu.addMenu(f"Synonyms for “{word}”")
        loading = sub.addAction("Looking up…")
        loading.setEnabled(False)
        done = {"v": False}

        def populate():
            if done["v"]:
                return
            done["v"] = True
            sub.clear()
            words = thesaurus.synonyms(word)
            if not words:
                empty = sub.addAction("(no synonyms found / offline)")
                empty.setEnabled(False)
                return
            for syn in words:
                sub.addAction(
                    syn, lambda _=False, w=syn: self._replace_word(cur, w))

        sub.aboutToShow.connect(populate)

    def _replace_word(self, cursor, word):
        cursor.insertText(word)             # cursor holds the word selection

    def _resize(self):
        rows = max(1, self.document().blockCount())
        shown = min(rows, self.MAX_ROWS)
        height = QFontMetrics(self.font()).lineSpacing() * shown + 14
        self.setFixedHeight(height)
        self.setVerticalScrollBarPolicy(
            Qt.ScrollBarAsNeeded if rows > self.MAX_ROWS
            else Qt.ScrollBarAlwaysOff)


class _FindBar(QWidget):
    """A compact find-in-cell bar: term + previous/next + close, with
    wrap-around, case-insensitive matching, and incremental search."""

    def __init__(self, editor):
        super().__init__()
        self._editor = editor
        row = QHBoxLayout(self)
        row.setContentsMargins(2, 2, 2, 2)
        row.setSpacing(3)
        self.edit = QLineEdit()
        self.edit.setPlaceholderText("Find in cell…")
        self.edit.setClearButtonEnabled(True)
        self.edit.returnPressed.connect(lambda: self.find(True))
        self.edit.textChanged.connect(self._incremental)
        row.addWidget(self.edit, 1)
        for text, tip, fwd in (("▲", "Previous", False), ("▼", "Next", True)):
            btn = QToolButton()
            btn.setText(text)
            btn.setToolTip(tip)
            btn.setAutoRaise(True)
            btn.clicked.connect(lambda _=False, f=fwd: self.find(f))
            row.addWidget(btn)
        close = QToolButton()
        close.setText("✕")
        close.setToolTip("Close (Esc)")
        close.setAutoRaise(True)
        close.clicked.connect(self._close)
        row.addWidget(close)
        self.hide()

    def open(self):
        cur = self._editor.textCursor()
        if cur.hasSelection():
            self.edit.setText(cur.selectedText())
        self.show()
        self.edit.setFocus()
        self.edit.selectAll()

    def _close(self):
        self.hide()
        self._editor.setFocus()

    def _incremental(self):
        cur = self._editor.textCursor()       # search from the current match
        if cur.hasSelection():
            cur.setPosition(cur.selectionStart())
            self._editor.setTextCursor(cur)
        self.find(True)

    def find(self, forward=True):
        text = self.edit.text()
        if not text:
            self.edit.setStyleSheet("")
            return
        flags = (QTextDocument.FindFlags() if forward
                 else QTextDocument.FindBackward)
        found = self._editor.find(text, flags)
        if not found:                          # wrap around the document
            cur = self._editor.textCursor()
            cur.movePosition(QTextCursor.Start if forward
                             else QTextCursor.End)
            self._editor.setTextCursor(cur)
            found = self._editor.find(text, flags)
        self.edit.setStyleSheet("" if found else "background:#ffd6d6")

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            self._close()
            return
        super().keyPressEvent(event)


class CellWidget(QFrame):
    """Base cell: gutter label + content column inside a bordered frame."""

    CELL_TYPE = "code"
    run_requested = pyqtSignal(object)   # self — run and advance
    run_clicked = pyqtSignal(object)     # self — run in place
    stop_clicked = pyqtSignal(object)    # self — stop continuous run
    reset_clicked = pyqtSignal(object)   # self — clear this cell's state
    menu_requested = pyqtSignal(object, object)   # self, global pos
    file_dropped = pyqtSignal(str, object)        # path, self
    content_changed = pyqtSignal()       # edited (non-editor cells)
    resized = pyqtSignal()               # width changed (notebook relayout)
    focused = pyqtSignal(object)         # self

    def __init__(self, source=""):
        super().__init__()
        self.setFrameShape(QFrame.StyledPanel)
        self.setObjectName("cell")
        self.setAcceptDrops(True)
        self._manual_w = None            # user-set width (resize grip)
        outer = QHBoxLayout(self)
        outer.setContentsMargins(6, 6, 6, 6)

        # Gutter column: run + stop buttons above the In [n] label.
        gcol = QVBoxLayout()
        gcol.setSpacing(2)
        btns = QHBoxLayout()
        btns.setSpacing(0)
        self.run_btn = QToolButton()
        self.run_btn.setIcon(icon("mdi.play-circle-outline", "#27ae60"))
        self.run_btn.setIconSize(QSize(24, 24))
        self.run_btn.setToolTip("Run this cell")
        self.run_btn.setAutoRaise(True)
        self.run_btn.clicked.connect(lambda: self.run_clicked.emit(self))
        btns.addWidget(self.run_btn)
        self.stop_btn = QToolButton()
        self.stop_btn.setIcon(icon("mdi.stop-circle-outline", "#c0392b"))
        self.stop_btn.setIconSize(QSize(24, 24))
        self.stop_btn.setToolTip("Stop the continuous run")
        self.stop_btn.setAutoRaise(True)
        self.stop_btn.clicked.connect(lambda: self.stop_clicked.emit(self))
        self.stop_btn.hide()
        btns.addWidget(self.stop_btn)
        gcol.addLayout(btns)
        # A per-cell restart: clears just this cell's variables and re-runs
        # it, so a live-loop cell re-seeds without a full Kernel > Restart.
        # Hidden by default; code cells reveal it.
        self.reset_btn = QToolButton()
        self.reset_btn.setIcon(icon("mdi.restart", "#e07b39"))
        self.reset_btn.setIconSize(QSize(20, 20))
        self.reset_btn.setToolTip(
            "Restart this cell — reset its variables and re-run")
        self.reset_btn.setAutoRaise(True)
        self.reset_btn.clicked.connect(lambda: self.reset_clicked.emit(self))
        self.reset_btn.hide()
        gcol.addWidget(self.reset_btn, alignment=Qt.AlignHCenter)
        self.collapse_btn = QToolButton()
        self.collapse_btn.setIcon(icon("mdi.chevron-down"))
        self.collapse_btn.setIconSize(QSize(18, 18))
        self.collapse_btn.setToolTip("Collapse / expand this cell")
        self.collapse_btn.setAutoRaise(True)
        self.collapse_btn.clicked.connect(
            lambda: self.set_collapsed(not self._collapsed))
        gcol.addWidget(self.collapse_btn, alignment=Qt.AlignHCenter)
        self.gutter = QLabel("")
        self.gutter.setObjectName("gutter")      # themed via QSS
        self.gutter.setFont(MONO)
        self.gutter.setFixedWidth(58)
        self.gutter.setAlignment(Qt.AlignHCenter | Qt.AlignTop)
        gcol.addWidget(self.gutter)
        gcol.addStretch(1)
        outer.addLayout(gcol)

        # Content: optional title, a one-line summary (collapsed), body.
        self._collapsed = False
        self._title = ""
        self._column = False        # True: sit beside the previous cell
        content = QVBoxLayout()
        content.setSpacing(0)
        self.title_label = QLabel("")
        self.title_label.setObjectName("cell_title")
        self.title_label.setStyleSheet("font-weight: bold; font-size: 13px;")
        self.title_label.setWordWrap(True)
        self.title_label.hide()
        content.addWidget(self.title_label)
        self.summary = QLabel("")
        self.summary.setFont(MONO)
        self.summary.setStyleSheet("color: #8a939c; font-style: italic;")
        self.summary.setCursor(Qt.PointingHandCursor)
        self.summary.setToolTip("Click to expand")
        self.summary.mousePressEvent = (
            lambda _e: self.set_collapsed(False))
        self.summary.hide()
        content.addWidget(self.summary)
        self._body = QWidget()
        self.column = QVBoxLayout(self._body)
        self.column.setContentsMargins(0, 0, 0, 0)
        self.column.setSpacing(4)
        self._body_scroll = _AutoScroll(self._body)
        content.addWidget(self._body_scroll)
        self._grip = _ResizeGrip(self)            # bottom: height
        content.addWidget(self._grip)
        outer.addLayout(content, 1)
        self._wgrip = _WidthGrip(self)            # right edge: width
        outer.addWidget(self._wgrip)

        self.editor = _GrowingEdit(source)
        self.editor.cell = self
        self.editor.run_requested.connect(lambda: self.run_requested.emit(self))
        self.editor.installEventFilter(self)
        self.column.addWidget(self.editor)
        self._find_bar = None
        self._looping = False

    def show_find(self):
        """Reveal the find-in-cell bar (Ctrl+F or right-click → Find)."""
        if self._find_bar is None:
            self._find_bar = _FindBar(self.editor)
            self.column.addWidget(self._find_bar)
        self._find_bar.open()

    def focus_editor(self):
        """Show and focus this cell's primary editor. Cell types whose
        editor isn't the base plain-text one (note, file) override this."""
        self.editor.show()
        self.editor.setFocus()

    def contextMenuEvent(self, event):
        self.menu_requested.emit(self, event.globalPos())

    def set_looping(self, on: bool):
        """Show/hide the stop button while a continuous run is active."""
        self._looping = bool(on)             # loops stay PNG, never canvases
        self.stop_btn.setVisible(on)

    # -- collapse ----------------------------------------------------------
    @property
    def collapsed(self) -> bool:
        return self._collapsed

    def set_collapsed(self, on: bool):
        """Minimise the cell to its title (or a one-line summary)."""
        self._collapsed = bool(on)
        self._body_scroll.setVisible(not self._collapsed)
        self._grip.setVisible(not self._collapsed)
        # When collapsed, a title is the label; otherwise show a preview.
        show_summary = self._collapsed and not self._title
        self.summary.setVisible(show_summary)
        if show_summary:
            lines = self.source().strip().splitlines() or [""]
            first = lines[0][:90]
            more = f"   … {len(lines)} lines" if len(lines) > 1 else ""
            self.summary.setText(first + more)
        self.collapse_btn.setIcon(icon(
            "mdi.chevron-right" if self._collapsed
            else "mdi.chevron-down"))

    # -- title -------------------------------------------------------------
    @property
    def title(self) -> str:
        return self._title

    def set_title(self, text: str):
        """A title shown bold at the top of the cell (empty = none)."""
        self._title = (text or "").strip()
        self.title_label.setText(self._title)
        self.title_label.setVisible(bool(self._title))
        if self._collapsed:                 # refresh summary visibility
            self.set_collapsed(True)

    # -- manual height -----------------------------------------------------
    def _resize_region_height(self) -> int:
        """Current px height of the region the resize grip controls."""
        return self._body_scroll.height()

    def set_content_height(self, height):
        """Cap the cell body to *height* px (content scrolls), or None
        to auto-fit to the content."""
        self._body_scroll.set_cap(height)

    def content_height(self):
        return self._body_scroll.cap

    def set_content_width(self, width):
        """Fix the cell to *width* px, or None to fill the row again."""
        if width is None:
            self._manual_w = None
            self.setMinimumWidth(0)
            self.setMaximumWidth(16777215)
        else:
            self._manual_w = max(220, int(width))
            self.setFixedWidth(self._manual_w)

    def content_width(self):
        return self._manual_w

    # -- row layout --------------------------------------------------------
    @property
    def beside_previous(self) -> bool:
        """True when this cell shares a row with the cell before it."""
        return self._column

    def set_beside_previous(self, on: bool):
        self._column = bool(on)

    # -- file drops (from the explorer or the OS) ------------------------
    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dragMoveEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event):
        for url in event.mimeData().urls():
            if url.isLocalFile():
                self.file_dropped.emit(url.toLocalFile(), self)
        event.acceptProposedAction()

    def eventFilter(self, obj, event):
        try:
            if obj is self.editor and event.type() == QEvent.FocusIn:
                self.focused.emit(self)
            return super().eventFilter(obj, event)
        except RuntimeError:        # widget already deleted at shutdown
            return False

    # -- API used by NotebookWidget ------------------------------------
    def source(self) -> str:
        return self.editor.toPlainText()

    def set_source(self, text: str):
        self.editor.setPlainText(text)

    def execute(self, kernel):
        """Run/render the cell. Overridden per type."""

    def to_dict(self) -> dict:
        d = {"type": self.CELL_TYPE, "source": self.source()}
        if self._title:
            d["title"] = self._title
        if self._collapsed:
            d["collapsed"] = True
        if self._column:
            d["column"] = True
        if self.content_height():
            d["height"] = self.content_height()
        if self._manual_w:
            d["width"] = self._manual_w
        return d


class CodeCell(CellWidget):
    """Python cell executed by the shared kernel."""

    CELL_TYPE = "code"
    COMMENT = ("# ", "")             # Ctrl+/ comment syntax

    def __init__(self, source=""):
        super().__init__(source)
        self.gutter.setText("In [ ]:")
        self.editor.enable_line_numbers()    # numbered gutter for Python
        from .style import tokens
        self._highlighter = PythonHighlighter(self.editor.document(),
                                              dark=tokens()["dark"],
                                              theme=hltheme.saved_name())
        self._apply_editor_colors()
        self.output = QLabel()
        self.output.setFont(MONO)
        self.output.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.output.setWordWrap(True)
        self.output.hide()
        self.column.addWidget(self.output)
        self._figure_labels = []
        self._plot_widgets = []
        self._introduced = set()     # kernel globals this cell has created
        self.reset_btn.show()        # per-cell restart (code cells only)

    # -- highlight themes ---------------------------------------------------
    def set_highlight_theme(self, name: str):
        """Restyle this cell with highlight theme *name* (no persistence)."""
        self._highlighter.set_theme(name)
        self._apply_editor_colors()

    def choose_highlight_theme(self, name: str):
        """The user picked *name* from the right-click menu: persist it
        and restyle every code cell in the notebook."""
        hltheme.save_name(name)
        w = self.parentWidget()
        while w is not None and not hasattr(w, "cells"):
            w = w.parentWidget()
        cells = [c for c in getattr(w, "cells", [])
                 if isinstance(c, CodeCell)] or [self]
        for cell in cells:
            cell.set_highlight_theme(name)

    def _apply_editor_colors(self):
        """Give the editor (and its gutter) an explicit theme's background,
        or hand it back to the app theme's stylesheet."""
        colors = hltheme.editor_colors(self._highlighter.theme)
        if colors:
            bg, fg = colors
            self.editor.setStyleSheet(
                f"QPlainTextEdit {{ background: {bg}; color: {fg}; }}")
            comment = hltheme.resolve(self._highlighter.theme)["comment"]
            self.editor._gutter_colors = (bg, comment)
        else:
            self.editor.setStyleSheet("")
            self.editor._gutter_colors = None
        if self.editor._lna is not None:
            self.editor._lna.update()

    def execute(self, kernel):
        # Interactive (zoom/pan) canvases when the toggle is on — but never
        # for continuous runs, which stay PNG for smooth, flicker-free frames.
        interactive = (getattr(kernel, "interactive_figures", False)
                       and not self._looping)
        res = kernel.run(self.source(), interactive=interactive)
        self._introduced |= res.new_names   # remember for a per-cell restart
        self.gutter.setText(f"In [{kernel.exec_count}]:")

        text = res.stdout
        if res.result_repr:
            text += ("\n" if text and not text.endswith("\n") else "")
            text += res.result_repr
        if res.stderr:
            text += ("\n" if text else "") + res.stderr
        if res.error:
            text += ("\n" if text else "") + res.error
        self.output.setText(text.rstrip("\n"))
        self.output.setStyleSheet("color: #b71c1c;" if res.error else "")
        self.output.setVisible(bool(text.strip()))

        if res.live_figures:
            self._show_live_figures(res.live_figures)
        else:
            self._show_png_figures(res.figures)

    def _show_png_figures(self, figures):
        self._clear_plot_widgets()
        # Reuse the existing labels when the figure count is unchanged
        # so continuous runs animate without flicker or relayout.
        if len(figures) != len(self._figure_labels):
            for lab in self._figure_labels:
                lab.deleteLater()
            self._figure_labels = []
            for _png in figures:
                lab = QLabel()
                self.column.addWidget(lab)
                self._figure_labels.append(lab)
        for lab, png in zip(self._figure_labels, figures):
            pix = QPixmap()
            pix.loadFromData(png, "PNG")
            lab.setPixmap(pix)

    def _show_live_figures(self, figures):
        from .plotcanvas import make_plot_widget
        for lab in self._figure_labels:         # drop any prior PNG plots
            lab.deleteLater()
        self._figure_labels = []
        self._clear_plot_widgets()
        for fig in figures:
            w = make_plot_widget(fig, self)
            self.column.addWidget(w)
            self._plot_widgets.append(w)

    def _clear_plot_widgets(self):
        for w in self._plot_widgets:
            w.close_figure()
            w.deleteLater()
        self._plot_widgets = []

    def reset_state(self, kernel):
        """Forget the kernel globals this cell created, so the next run
        re-seeds from scratch (per-cell restart)."""
        kernel.forget(self._introduced)
        self._introduced = set()


class MarkdownCell(CellWidget):
    """Markdown cell: edit source, render on run, double-click to re-edit."""

    CELL_TYPE = "markdown"
    COMMENT = ("<!-- ", " -->")      # Ctrl+/ comment syntax

    def __init__(self, source=""):
        super().__init__(source)
        self.gutter.setText("md")
        from .style import tokens
        self._highlighter = MarkdownHighlighter(self.editor.document(),
                                                dark=tokens()["dark"])
        self.view = QTextBrowser()
        self.view.setAcceptDrops(False)      # file drops go to the cell
        self.view.setOpenExternalLinks(True)
        self.view.setFrameShape(QFrame.NoFrame)
        # Render markdown at a comfortable reading size (the app default
        # is small next to LaTeX).
        md_font = QFont()
        md_font.setPointSizeF(11.5)
        self.view.setFont(md_font)
        self.view.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.view.hide()
        self.view.mouseDoubleClickEvent = self._edit_again
        self.column.addWidget(self.view)

    def execute(self, kernel):
        self.view.document().setMarkdown(self.source())
        self.view.document().adjustSize()
        height = int(self.view.document().size().height()) + 12
        self.view.setFixedHeight(max(28, height))
        self.editor.hide()
        self.view.show()

    def _edit_again(self, _event):
        self.view.hide()
        self.editor.show()
        self.editor.setFocus()


#: Live compile workers, kept off the cells so deleting a cell mid-
#: compile never destroys a running QThread (a hard crash on Windows).
_LATEX_WORKERS = set()


class _LatexCompileWorker(QThread):
    """Compiles LaTeX off the UI thread (tectonic can take seconds)."""

    done = pyqtSignal(str, list)     # source, list[png bytes]
    failed = pyqtSignal(str, str)    # source, log

    def __init__(self, source, parent=None):
        super().__init__(parent)
        self._source = source

    def run(self):
        from .latexcompile import compile_to_pngs
        try:
            # Higher dpi so scaling up to a wide cell stays crisp.
            pngs, err = compile_to_pngs(self._source, dpi=190)
        except Exception as exc:
            self.failed.emit(self._source, str(exc))
            return
        if pngs:
            self.done.emit(self._source, pngs)
        else:
            self.failed.emit(self._source, err or "LaTeX produced no output")


class LatexCell(CellWidget):
    """LaTeX cell. A single equation renders instantly with matplotlib
    mathtext; a document compiles with the real LaTeX engine (tectonic)
    and shows the typeset pages — full LaTeX, not an approximation. When
    no engine is installed it falls back to the lightweight text view."""

    CELL_TYPE = "latex"
    COMMENT = ("% ", "")             # Ctrl+/ comment syntax

    def __init__(self, source=""):
        super().__init__(source)
        self.gutter.setText("tex")
        from .style import tokens
        self._highlighter = LatexHighlighter(self.editor.document(),
                                             dark=tokens()["dark"])
        self.view = QLabel()                 # single-equation math image
        self.view.setAlignment(Qt.AlignCenter)
        self.view.hide()
        self.view.mouseDoubleClickEvent = self._edit_again
        self.column.addWidget(self.view)
        self.doc_view = QTextBrowser()       # text fallback / error log
        self.doc_view.setAcceptDrops(False)
        self.doc_view.setOpenExternalLinks(True)
        self.doc_view.setFrameShape(QFrame.NoFrame)
        self.doc_view.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.doc_view.hide()
        self.doc_view.mouseDoubleClickEvent = self._edit_again
        self.column.addWidget(self.doc_view)
        self.status = QLabel("")             # "Compiling…" indicator
        self.status.setStyleSheet("color: #57606a; font-style: italic;")
        self.status.hide()
        self.column.addWidget(self.status)
        self.pages_box = QWidget()           # compiled PDF pages
        self._pages_layout = QVBoxLayout(self.pages_box)
        self._pages_layout.setContentsMargins(0, 0, 0, 0)
        self._pages_layout.setSpacing(8)
        self.pages_box.hide()
        self.pages_box.mouseDoubleClickEvent = self._edit_again
        self.column.addWidget(self.pages_box)
        self._page_labels = []
        self._pending = ""
        self._compiled_source = None

    def execute(self, kernel):
        from . import latexcompile
        from .latextext import is_document
        tex = self.source().strip()
        if not tex:
            return
        self.editor.hide()
        document = is_document(tex) or "\\begin{" in tex
        if document and latexcompile.available():
            self._compile(tex)
        elif document:
            self._show_html(tex)
        else:
            self._show_math(tex)

    # -- full LaTeX compile -----------------------------------------------
    def _compile(self, tex):
        if tex == self._compiled_source and self._page_labels:
            self._show_pages()                     # unchanged → reuse
            return
        self._pending = tex
        self.view.hide()
        self.doc_view.hide()
        self.pages_box.hide()
        self.status.setText("Compiling LaTeX…  "
                            "(first run downloads packages)")
        self.status.show()
        # No cell parent: the worker outlives the cell if it's deleted
        # mid-compile, and is freed when it finishes (never destroyed
        # while running). A deleted cell auto-disconnects its slots.
        worker = _LatexCompileWorker(tex)
        _LATEX_WORKERS.add(worker)
        worker.done.connect(self._on_pages)
        worker.failed.connect(self._on_error)
        worker.finished.connect(
            lambda w=worker: (_LATEX_WORKERS.discard(w), w.deleteLater()))
        worker.start()

    def _on_pages(self, source, pngs):
        if source != self._pending:                # a newer compile wins
            return
        for lab in self._page_labels:
            lab.deleteLater()
        self._page_labels = []
        for png in pngs:
            pix = QPixmap()
            pix.loadFromData(png, "PNG")
            lab = _FitImage()                 # fills the cell width
            lab.set_image(pix)
            self._pages_layout.addWidget(lab)
            self._page_labels.append(lab)
        self._compiled_source = source
        self.status.hide()
        self._show_pages()

    def _on_error(self, source, log):
        if source != self._pending:
            return
        import html as _html
        tail = "\n".join((log or "").strip().splitlines()[-30:])
        self.status.hide()
        self.pages_box.hide()
        self.view.hide()
        self.doc_view.setHtml(
            "<p style='color:#b71c1c'><b>LaTeX compile error</b> — fix "
            "the source and run again.</p><pre style='white-space:pre-wrap;"
            "color:#b71c1c'>" + _html.escape(tail) + "</pre>")
        self.doc_view.document().adjustSize()
        h = int(self.doc_view.document().size().height()) + 16
        self.doc_view.setFixedHeight(max(60, h))
        self.doc_view.show()

    def _show_pages(self):
        self.editor.hide()
        self.view.hide()
        self.doc_view.hide()
        self.status.hide()
        self.pages_box.show()

    # -- fallbacks --------------------------------------------------------
    def _show_html(self, tex):
        from .latextext import latex_to_html
        self.view.hide()
        self.pages_box.hide()
        self.doc_view.document().setHtml(latex_to_html(tex))
        self.doc_view.document().adjustSize()
        height = int(self.doc_view.document().size().height()) + 16
        self.doc_view.setFixedHeight(max(40, height))
        self.doc_view.show()

    def _show_math(self, tex):
        self.doc_view.hide()
        self.pages_box.hide()
        try:
            png = self._render(tex)
        except Exception as exc:
            # mathtext is limited; for full LaTeX wrap in an environment
            # (\begin{equation}…) or a document, which compiles instead.
            self.view.setText(f"LaTeX (mathtext) error: {exc}\n"
                              "Use \\begin{equation}…\\end{equation} or a "
                              "full document for the complete LaTeX engine.")
            self.view.setWordWrap(True)
            self.view.setStyleSheet("color: #b71c1c;")
        else:
            pix = QPixmap()
            pix.loadFromData(png, "PNG")
            self.view.setPixmap(pix)
            self.view.setStyleSheet("")
        self.view.show()

    @staticmethod
    def _render(tex: str) -> bytes:
        import matplotlib
        matplotlib.use("Agg", force=False)
        from matplotlib.figure import Figure
        from PyQt5.QtWidgets import QApplication
        if not tex.startswith("$"):
            tex = f"${tex}$"
        # Follow the theme's text colour (renders on a transparent bg).
        color = QApplication.palette().text().color().name()
        fig = Figure(figsize=(0.1, 0.1))
        fig.text(0, 0, tex, fontsize=14, color=color)
        buf = io.BytesIO()
        fig.savefig(buf, format="png", dpi=130, bbox_inches="tight",
                    transparent=True)
        return buf.getvalue()

    def _edit_again(self, _event):
        self.view.hide()
        self.doc_view.hide()
        self.pages_box.hide()
        self.editor.show()
        self.editor.setFocus()


CELL_CLASSES = {cls.CELL_TYPE: cls
                for cls in (CodeCell, MarkdownCell, LatexCell)}


def make_cell(cell_type: str, source: str = "") -> CellWidget:
    return CELL_CLASSES.get(cell_type, CodeCell)(source)
