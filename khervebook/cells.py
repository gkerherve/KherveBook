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

from PyQt5.QtCore import QEvent, QSize, Qt, pyqtSignal
from PyQt5.QtGui import (QColor, QFont, QFontMetrics, QPixmap,
                         QSyntaxHighlighter, QTextCharFormat)
from PyQt5.QtWidgets import (QAction, QFrame, QHBoxLayout, QLabel,
                             QPlainTextEdit, QSizePolicy, QTextBrowser,
                             QToolButton, QVBoxLayout, QWidget)

from .icons import icon

MONO = QFont("Consolas", 10)


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
        super().keyPressEvent(event)

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
    focused = pyqtSignal(object)         # self

    def __init__(self, source=""):
        super().__init__()
        self.setFrameShape(QFrame.StyledPanel)
        self.setObjectName("cell")
        self.setAcceptDrops(True)
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
        content.addWidget(self._body)
        outer.addLayout(content, 1)

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
        self._body.setVisible(not self._collapsed)
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
        return d


class CodeCell(CellWidget):
    """Python cell executed by the shared kernel."""

    CELL_TYPE = "code"

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

    def __init__(self, source=""):
        super().__init__(source)
        self.gutter.setText("md")
        self.view = QTextBrowser()
        self.view.setAcceptDrops(False)      # file drops go to the cell
        self.view.setOpenExternalLinks(True)
        self.view.setFrameShape(QFrame.NoFrame)
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


class LatexCell(CellWidget):
    """LaTeX equation cell rendered with matplotlib mathtext."""

    CELL_TYPE = "latex"

    def __init__(self, source=""):
        super().__init__(source)
        self.gutter.setText("tex")
        self.view = QLabel()
        self.view.setAlignment(Qt.AlignCenter)
        self.view.hide()
        self.view.mouseDoubleClickEvent = self._edit_again
        self.column.addWidget(self.view)

    def execute(self, kernel):
        tex = self.source().strip()
        if not tex:
            return
        try:
            png = self._render(tex)
        except Exception as exc:  # bad TeX should not crash the app
            self.view.setText(f"LaTeX error: {exc}")
            self.view.setStyleSheet("color: #b71c1c;")
        else:
            pix = QPixmap()
            pix.loadFromData(png, "PNG")
            self.view.setPixmap(pix)
            self.view.setStyleSheet("")
        self.editor.hide()
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
        self.editor.show()
        self.editor.setFocus()


CELL_CLASSES = {cls.CELL_TYPE: cls
                for cls in (CodeCell, MarkdownCell, LatexCell)}


def make_cell(cell_type: str, source: str = "") -> CellWidget:
    return CELL_CLASSES.get(cell_type, CodeCell)(source)
