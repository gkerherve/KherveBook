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

from PyQt5.QtCore import QSize, Qt, pyqtSignal
from PyQt5.QtGui import (QColor, QFont, QFontMetrics, QPixmap,
                         QSyntaxHighlighter, QTextCharFormat)
from PyQt5.QtWidgets import (QAction, QFrame, QHBoxLayout, QLabel,
                             QPlainTextEdit, QSizePolicy, QTextBrowser,
                             QToolButton, QVBoxLayout)

from .icons import icon

MONO = QFont("Consolas", 10)


class PythonHighlighter(QSyntaxHighlighter):
    """Minimal Python syntax highlighting for code cell editors."""

    _KEYWORDS = (
        "def class return if elif else for while in is and or not import "
        "from as with try except finally raise lambda yield global nonlocal "
        "pass break continue None True False assert del").split()

    def __init__(self, document):
        super().__init__(document)
        self._rules = []

        kw = QTextCharFormat()
        kw.setForeground(QColor("#0000C0"))
        kw.setFontWeight(QFont.Bold)
        for word in self._KEYWORDS:
            self._rules.append((re.compile(rf"\b{word}\b"), kw))

        num = QTextCharFormat()
        num.setForeground(QColor("#098658"))
        self._rules.append((re.compile(r"\b\d+(\.\d+)?\b"), num))

        s = QTextCharFormat()
        s.setForeground(QColor("#A31515"))
        self._rules.append((re.compile(r"'[^']*'|\"[^\"]*\""), s))

        c = QTextCharFormat()
        c.setForeground(QColor("#808080"))
        c.setFontItalic(True)
        self._rules.append((re.compile(r"#.*$"), c))

    def highlightBlock(self, text):
        for pattern, fmt in self._rules:
            for m in pattern.finditer(text):
                self.setFormat(m.start(), m.end() - m.start(), fmt)


class _GrowingEdit(QPlainTextEdit):
    """Plain-text editor that grows with its content (no inner scrollbar)."""

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
        height = QFontMetrics(self.font()).lineSpacing() * rows + 14
        self.setFixedHeight(height)


class CellWidget(QFrame):
    """Base cell: gutter label + content column inside a bordered frame."""

    CELL_TYPE = "code"
    run_requested = pyqtSignal(object)   # self — run and advance
    run_clicked = pyqtSignal(object)     # self — run in place
    menu_requested = pyqtSignal(object, object)   # self, global pos
    focused = pyqtSignal(object)         # self

    def __init__(self, source=""):
        super().__init__()
        self.setFrameShape(QFrame.StyledPanel)
        self.setObjectName("cell")
        outer = QHBoxLayout(self)
        outer.setContentsMargins(6, 6, 6, 6)

        # Gutter column: a run button above the In [n] / md / tex label.
        gcol = QVBoxLayout()
        gcol.setSpacing(2)
        self.run_btn = QToolButton()
        self.run_btn.setIcon(icon("mdi.play-circle-outline", "#27ae60"))
        self.run_btn.setIconSize(QSize(26, 26))
        self.run_btn.setToolTip("Run this cell")
        self.run_btn.setAutoRaise(True)
        self.run_btn.clicked.connect(lambda: self.run_clicked.emit(self))
        gcol.addWidget(self.run_btn, alignment=Qt.AlignHCenter)
        self.gutter = QLabel("")
        self.gutter.setFont(MONO)
        self.gutter.setFixedWidth(58)
        self.gutter.setAlignment(Qt.AlignHCenter | Qt.AlignTop)
        self.gutter.setStyleSheet("color: #1565c0;")
        gcol.addWidget(self.gutter)
        gcol.addStretch(1)
        outer.addLayout(gcol)

        self.column = QVBoxLayout()
        self.column.setSpacing(4)
        outer.addLayout(self.column, 1)

        self.editor = _GrowingEdit(source)
        self.editor.cell = self
        self.editor.run_requested.connect(lambda: self.run_requested.emit(self))
        self.editor.installEventFilter(self)
        self.column.addWidget(self.editor)

    def contextMenuEvent(self, event):
        self.menu_requested.emit(self, event.globalPos())

    def eventFilter(self, obj, event):
        if obj is self.editor and event.type() == event.FocusIn:
            self.focused.emit(self)
        return super().eventFilter(obj, event)

    # -- API used by NotebookWidget ------------------------------------
    def source(self) -> str:
        return self.editor.toPlainText()

    def set_source(self, text: str):
        self.editor.setPlainText(text)

    def execute(self, kernel):
        """Run/render the cell. Overridden per type."""

    def to_dict(self) -> dict:
        return {"type": self.CELL_TYPE, "source": self.source()}


class CodeCell(CellWidget):
    """Python cell executed by the shared kernel."""

    CELL_TYPE = "code"

    def __init__(self, source=""):
        super().__init__(source)
        self.gutter.setText("In [ ]:")
        self._highlighter = PythonHighlighter(self.editor.document())
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
        for lab in self._figure_labels:
            lab.deleteLater()
        self._figure_labels = []

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

        for png in res.figures:
            pix = QPixmap()
            pix.loadFromData(png, "PNG")
            lab = QLabel()
            lab.setPixmap(pix)
            self.column.addWidget(lab)
            self._figure_labels.append(lab)


class MarkdownCell(CellWidget):
    """Markdown cell: edit source, render on run, double-click to re-edit."""

    CELL_TYPE = "markdown"

    def __init__(self, source=""):
        super().__init__(source)
        self.gutter.setText("md")
        self.view = QTextBrowser()
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
        if not tex.startswith("$"):
            tex = f"${tex}$"
        fig = Figure(figsize=(0.1, 0.1))
        fig.text(0, 0, tex, fontsize=14)
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
