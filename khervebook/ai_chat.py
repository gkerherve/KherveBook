"""AI chat dock — talk to Claude/ChatGPT/Mistral/Ollama about the
notebook and insert the cells they propose.

Ported in spirit from KherveSheet's ai_chat: same provider set,
settings dialog and QSettings scheme. KherveBook's unit is the cell,
so instead of tool calls the assistant answers with fenced blocks
(```python / ```markdown / ```latex / ```sheet) which the Insert
button turns into real cells.

Copyright (C) 2026 Gwilherm Kerherve

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.
"""

import re

from PyQt5.QtCore import QThread, Qt, pyqtSignal
from PyQt5.QtGui import QTextDocument
from PyQt5.QtWidgets import (QComboBox, QDialog, QDialogButtonBox,
                             QDockWidget, QFormLayout, QHBoxLayout, QLabel,
                             QLineEdit, QPlainTextEdit, QPushButton,
                             QTextBrowser, QToolButton, QVBoxLayout, QWidget)

from . import ai_providers as prov
from .icons import icon

_FENCE = re.compile(
    r"```[ \t]*(python|markdown|md|latex|tex|sheet)[ \t]*\r?\n(.*?)```",
    re.S | re.I)

_KIND = {"python": "code", "md": "markdown", "markdown": "markdown",
         "tex": "latex", "latex": "latex", "sheet": "sheet"}


def extract_cells(text: str) -> list:
    """Fenced blocks in an assistant reply -> cell dicts, in order."""
    cells = []
    for lang, body in _FENCE.findall(text or ""):
        cells.append({"type": _KIND[lang.lower()],
                      "source": body.strip("\n")})
    return cells


def build_system_prompt(notebook) -> str:
    outline = []
    for i, cell in enumerate(notebook.cells):
        first = (cell.source().strip().splitlines() or [""])[0]
        outline.append(f"  [{i}] {cell.CELL_TYPE}: {first[:70]}")
    return f"""\
You are the AI assistant inside KherveBook, a Jupyter-style desktop \
notebook mixing four cell types: code (Python), markdown, latex \
(one display equation, no $ delimiters) and sheet (a small \
spreadsheet, JSON {{"rows", "cols", "data": {{"A1": "value or \
=python formula"}}}}).

YOUR PRIMARY SKILL is writing excellent, complete, runnable Python \
for code cells. Key facts about the kernel:
- One persistent namespace shared by all code cells.
- Preloaded: math, np/numpy, plt (matplotlib, Agg), pd/pandas, \
scipy, lmfit, sympy. Import anything else you need.
- The value of a cell's LAST line (if an expression) is displayed: \
numbers/strings echo, a matplotlib Figure embeds as a plot — end \
plotting cells with `fig`.
- A code cell whose first line contains "runs continuously" can be \
looped for animations; keep per-frame state in globals().
- Sheet cells publish their computed grid to code cells as sheet1, \
sheet2, ... (lists of rows).

When you create or modify notebook content, output each cell as ONE \
fenced block in document order, choosing the right language tag: \
```python, ```markdown, ```latex or ```sheet. The user inserts them \
with one click, so make every block self-contained and runnable. \
Keep prose outside the fences brief.

Current notebook ({len(notebook.cells)} cells):
{chr(10).join(outline)}"""


def _md_to_html(text: str) -> str:
    doc = QTextDocument()
    doc.setMarkdown(text)
    html = doc.toHtml()
    m = re.search(r"<body[^>]*>(.*)</body>", html, re.S)
    return m.group(1) if m else html


class AIWorker(QThread):
    done = pyqtSignal(str)
    failed = pyqtSignal(str)

    def __init__(self, cfg, system, history, parent=None):
        super().__init__(parent)
        self._args = (cfg, system, list(history))

    def run(self):
        try:
            self.done.emit(prov.chat(*self._args))
        except Exception as exc:
            self.failed.emit(str(exc))


class ApiKeyDialog(QDialog):
    """Provider / API key / host / model settings (gear button)."""

    def __init__(self, parent=None, provider=None):
        super().__init__(parent)
        self.setWindowTitle("AI settings")
        form = QFormLayout(self)
        self.provider = QComboBox()
        for name, meta in prov.PROVIDERS.items():
            self.provider.addItem(meta["label"], name)
        form.addRow("Provider:", self.provider)
        self.key = QLineEdit()
        self.key.setEchoMode(QLineEdit.Password)
        form.addRow("API key:", self.key)
        self.host = QLineEdit()
        form.addRow("Host:", self.host)
        self.model = QComboBox()
        self.model.setEditable(True)
        form.addRow("Model:", self.model)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok
                                   | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        form.addRow(buttons)

        self.provider.currentIndexChanged.connect(self._load_provider)
        start = provider or prov.saved_provider()
        self.provider.setCurrentIndex(
            max(0, list(prov.PROVIDERS).index(start)))
        self._load_provider()

    def _load_provider(self):
        name = self.provider.currentData()
        meta = prov.PROVIDERS[name]
        cfg = prov.load_config(name)
        self.key.setText(cfg["key"])
        self.key.setEnabled(meta["needs_key"])
        self.host.setText(cfg["host"])
        self.host.setEnabled(meta["needs_host"])
        self.model.clear()
        self.model.addItems(meta["models"])
        self.model.setCurrentText(cfg["model"])

    def accept(self):
        prov.save_config(self.provider.currentData(),
                         self.key.text().strip(),
                         self.model.currentText().strip(),
                         self.host.text().strip())
        super().accept()


class _ChatInput(QPlainTextEdit):
    """Enter sends; Shift+Enter inserts a newline."""

    send = pyqtSignal()

    def keyPressEvent(self, event):
        if (event.key() in (Qt.Key_Return, Qt.Key_Enter)
                and not event.modifiers() & Qt.ShiftModifier):
            self.send.emit()
            return
        super().keyPressEvent(event)


class AIChatDock(QDockWidget):
    """Bottom-left chat panel driving the notebook."""

    def __init__(self, notebook, parent=None):
        super().__init__("AI Assistant", parent)
        self.setObjectName("ai_chat")
        self._notebook = notebook
        self._history = []          # neutral [{"role", "content"}]
        self._pending_cells = []
        self._worker = None

        container = QWidget()
        column = QVBoxLayout(container)
        column.setContentsMargins(4, 4, 4, 4)
        column.setSpacing(4)

        header = QHBoxLayout()
        self.provider_combo = QComboBox()
        for name, meta in prov.PROVIDERS.items():
            self.provider_combo.addItem(meta["label"], name)
        self.provider_combo.setCurrentIndex(
            list(prov.PROVIDERS).index(prov.saved_provider()))
        self.provider_combo.currentIndexChanged.connect(
            self._remember_provider)
        header.addWidget(self.provider_combo, 1)
        gear = QToolButton()
        gear.setIcon(icon("mdi.cog-outline"))
        gear.setToolTip("AI settings (provider, API key, model)")
        gear.setAutoRaise(True)
        gear.clicked.connect(self._settings)
        header.addWidget(gear)
        clear = QToolButton()
        clear.setIcon(icon("mdi.broom"))
        clear.setToolTip("Clear the conversation")
        clear.setAutoRaise(True)
        clear.clicked.connect(self._clear)
        header.addWidget(clear)
        column.addLayout(header)

        self.view = QTextBrowser()
        self.view.setOpenExternalLinks(False)
        self.view.setPlaceholderText(
            "Ask for analysis, plots or whole notebooks — replies "
            "arrive as ready-to-insert cells.")
        column.addWidget(self.view, 1)

        self.insert_btn = QPushButton("Insert cells into notebook")
        self.insert_btn.setIcon(icon("mdi.tray-arrow-down"))
        self.insert_btn.hide()
        self.insert_btn.clicked.connect(self._insert_cells)
        column.addWidget(self.insert_btn)

        self.status = QLabel("")
        self.status.setWordWrap(True)
        column.addWidget(self.status)

        row = QHBoxLayout()
        self.input = _ChatInput()
        self.input.setPlaceholderText("Ask the AI…  (Enter sends)")
        self.input.setFixedHeight(64)
        self.input.send.connect(self._send)
        row.addWidget(self.input, 1)
        self.send_btn = QToolButton()
        self.send_btn.setIcon(icon("mdi.send", "#27ae60"))
        self.send_btn.setToolTip("Send")
        self.send_btn.clicked.connect(self._send)
        row.addWidget(self.send_btn)
        column.addLayout(row)

        self.setWidget(container)

    def _remember_provider(self, _index):
        from PyQt5.QtCore import QSettings
        QSettings("Kherve", "KherveBook").setValue(
            "ai/provider", self.provider_combo.currentData())

    # -- conversation ------------------------------------------------------
    def _append(self, role: str, text: str):
        if role == "user":
            self.view.append(
                f'<p><b style="color:#2176c7">You</b></p>{_md_to_html(text)}')
        else:
            self.view.append(
                f'<p><b style="color:#27ae60">AI</b></p>{_md_to_html(text)}')
        self.view.verticalScrollBar().setValue(
            self.view.verticalScrollBar().maximum())

    def _send(self):
        text = self.input.toPlainText().strip()
        if not text or self._worker is not None:
            return
        name = self.provider_combo.currentData()
        cfg = prov.load_config(name)
        if prov.PROVIDERS[name]["needs_key"] and not cfg["key"]:
            self._settings()
            cfg = prov.load_config(name)
            if not cfg["key"]:
                return
        self.input.clear()
        self._append("user", text)
        self._history.append({"role": "user", "content": text})
        self.status.setText(f"Thinking… ({cfg['model']})")
        self.send_btn.setEnabled(False)
        system = build_system_prompt(self._notebook)
        self._worker = AIWorker(cfg, system, self._history, self)
        self._worker.done.connect(self._on_done)
        self._worker.failed.connect(self._on_failed)
        self._worker.finished.connect(self._on_finished)
        self._worker.start()

    def _on_done(self, text: str):
        self._history.append({"role": "assistant", "content": text})
        self._append("assistant", text)
        self._pending_cells = extract_cells(text)
        n = len(self._pending_cells)
        self.insert_btn.setVisible(n > 0)
        if n:
            self.insert_btn.setText(
                f"Insert {n} cell{'s' if n > 1 else ''} into notebook")
        self.status.setText("")

    def _on_failed(self, message: str):
        self.status.setText(f"⚠ {message}")

    def _on_finished(self):
        self.send_btn.setEnabled(True)
        if self._worker is not None:
            self._worker.deleteLater()
            self._worker = None

    def _insert_cells(self):
        nb = self._notebook
        for item in self._pending_cells:
            cell = nb.add_cell_below(item["type"], item["source"])
            if item["type"] in ("markdown", "latex"):
                cell.execute(nb.kernel)
        self.status.setText(
            f"Inserted {len(self._pending_cells)} cell(s) — review and "
            "run the code cells.")
        self._pending_cells = []
        self.insert_btn.hide()

    def _settings(self):
        dlg = ApiKeyDialog(self, self.provider_combo.currentData())
        if dlg.exec_():
            self.provider_combo.setCurrentIndex(
                list(prov.PROVIDERS).index(prov.saved_provider()))

    def _clear(self):
        self._history = []
        self._pending_cells = []
        self.insert_btn.hide()
        self.view.clear()
        self.status.setText("")
