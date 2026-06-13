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
from PyQt5.QtGui import (QColor, QFont, QFontMetrics, QPixmap,
                         QSyntaxHighlighter, QTextCharFormat, QTextCursor)
from PyQt5.QtWidgets import (QAction, QFrame, QHBoxLayout, QLabel,
                             QPlainTextEdit, QScrollArea, QSizePolicy,
                             QTextBrowser, QToolButton, QVBoxLayout, QWidget)

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
    """Minimal Python syntax highlighting for code cell editors."""

    _KEYWORDS = (
        "def class return if elif else for while in is and or not import "
        "from as with try except finally raise lambda yield global nonlocal "
        "pass break continue None True False assert del").split()

    #: (keyword, number, string, comment) per background brightness.
    LIGHT = ("#0000C0", "#098658", "#A31515", "#808080")
    DARK = ("#6f9fff", "#6ccb9e", "#e8907e", "#8a939c")

    def __init__(self, document, dark=False):
        super().__init__(document)
        self._build_rules(dark)

    def _build_rules(self, dark: bool):
        kw_c, num_c, str_c, com_c = self.DARK if dark else self.LIGHT
        self._rules = []

        kw = QTextCharFormat()
        kw.setForeground(QColor(kw_c))
        kw.setFontWeight(QFont.Bold)
        for word in self._KEYWORDS:
            self._rules.append((re.compile(rf"\b{word}\b"), kw))

        num = QTextCharFormat()
        num.setForeground(QColor(num_c))
        self._rules.append((re.compile(r"\b\d+(\.\d+)?\b"), num))

        s = QTextCharFormat()
        s.setForeground(QColor(str_c))
        self._rules.append((re.compile(r"'[^']*'|\"[^\"]*\""), s))

        c = QTextCharFormat()
        c.setForeground(QColor(com_c))
        c.setFontItalic(True)
        self._rules.append((re.compile(r"#.*$"), c))

    def set_dark(self, dark: bool):
        self._build_rules(dark)
        self.rehighlight()

    def highlightBlock(self, text):
        for pattern, fmt in self._rules:
            for m in pattern.finditer(text):
                self.setFormat(m.start(), m.end() - m.start(), fmt)


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
        super().keyPressEvent(event)

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
        """Standard edit menu with a "Run Cell" entry on top."""
        menu = self.createStandardContextMenu()
        cell = getattr(self, "cell", None)
        if cell is not None:
            run = QAction("Run Cell", menu)
            run.triggered.connect(lambda: cell.run_clicked.emit(cell))
            first = menu.actions()[0] if menu.actions() else None
            menu.insertAction(first, run)
            menu.insertSeparator(first)
        menu.exec_(event.globalPos())

    def _resize(self):
        rows = max(1, self.document().blockCount())
        shown = min(rows, self.MAX_ROWS)
        height = QFontMetrics(self.font()).lineSpacing() * shown + 14
        self.setFixedHeight(height)
        self.setVerticalScrollBarPolicy(
            Qt.ScrollBarAsNeeded if rows > self.MAX_ROWS
            else Qt.ScrollBarAlwaysOff)


class CellWidget(QFrame):
    """Base cell: gutter label + content column inside a bordered frame."""

    CELL_TYPE = "code"
    run_requested = pyqtSignal(object)   # self — run and advance
    run_clicked = pyqtSignal(object)     # self — run in place
    stop_clicked = pyqtSignal(object)    # self — stop continuous run
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

    def contextMenuEvent(self, event):
        self.menu_requested.emit(self, event.globalPos())

    def set_looping(self, on: bool):
        """Show/hide the stop button while a continuous run is active."""
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
        from .style import tokens
        self._highlighter = PythonHighlighter(self.editor.document(),
                                              dark=tokens()["dark"])
        self.output = QLabel()
        self.output.setFont(MONO)
        self.output.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.output.setWordWrap(True)
        self.output.hide()
        self.column.addWidget(self.output)
        self._figure_labels = []

    def execute(self, kernel):
        res = kernel.run(self.source())
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

        # Reuse the existing labels when the figure count is unchanged
        # so continuous runs animate without flicker or relayout.
        if len(res.figures) != len(self._figure_labels):
            for lab in self._figure_labels:
                lab.deleteLater()
            self._figure_labels = []
            for _png in res.figures:
                lab = QLabel()
                self.column.addWidget(lab)
                self._figure_labels.append(lab)
        for lab, png in zip(self._figure_labels, res.figures):
            pix = QPixmap()
            pix.loadFromData(png, "PNG")
            lab.setPixmap(pix)


class MarkdownCell(CellWidget):
    """Markdown cell: edit source, render on run, double-click to re-edit."""

    CELL_TYPE = "markdown"
    COMMENT = ("<!-- ", " -->")      # Ctrl+/ comment syntax

    def __init__(self, source=""):
        super().__init__(source)
        self.gutter.setText("md")
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
