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
                             QDockWidget, QFormLayout, QGroupBox, QHBoxLayout,
                             QLabel, QLineEdit, QMessageBox, QPlainTextEdit,
                             QPushButton, QTextBrowser, QToolButton,
                             QVBoxLayout, QWidget)

from . import ai_providers as prov
from .icons import icon

#: One fenced block: an info string (language + optional "cell=N"
#: target) then the body up to the closing fence.
_FENCE = re.compile(r"```[ \t]*([^\r\n`]*)\r?\n(.*?)```", re.S)

_KIND = {"python": "code", "py": "code", "md": "markdown",
         "markdown": "markdown", "tex": "latex", "latex": "latex",
         "sheet": "sheet"}

#: How much of each cell to show the model, and a total cap.
_MAX_CELL_CHARS = 4000
_MAX_TOTAL_CHARS = 20000


def extract_cells(text: str) -> list:
    """Fenced blocks in a reply -> cell dicts {type, source, target}.

    The info string after the fence picks the language; an optional
    number (e.g. ```python cell=3) targets an existing cell to replace.
    Unknown languages (svg, bash, json, ...) are ignored."""
    cells = []
    for info, body in _FENCE.findall(text or ""):
        tokens = info.strip().split()
        if not tokens:
            continue
        lang = tokens[0].lower()
        if lang not in _KIND:           # svg / drawing and others: skip
            continue
        target = None
        for tok in tokens[1:]:
            m = re.search(r"\d+", tok)
            if m:
                target = int(m.group())
                break
        cells.append({"type": _KIND[lang], "source": body.strip("\n"),
                      "target": target})
    return cells


def _notebook_listing(notebook) -> str:
    blocks, total = [], 0
    for i, cell in enumerate(notebook.cells):
        if cell.CELL_TYPE == "svg":
            body = "(an SVG drawing — you cannot read or edit this cell)"
        else:
            body = cell.source()
            if len(body) > _MAX_CELL_CHARS:
                body = body[:_MAX_CELL_CHARS] + "\n… (truncated)"
        block = f"=== Cell [{i}] ({cell.CELL_TYPE}) ===\n{body}"
        total += len(block)
        if total > _MAX_TOTAL_CHARS and blocks:
            blocks.append(f"… ({len(notebook.cells) - i} more cells omitted)")
            break
        blocks.append(block)
    return "\n".join(blocks) if blocks else "(empty notebook)"


def build_system_prompt(notebook) -> str:
    return f"""\
You are the AI assistant inside KherveBook, a Jupyter-style desktop \
notebook. The editable cell types are: code (Python), markdown, latex \
(one display equation, no $ delimiters) and sheet (a small \
spreadsheet, JSON {{"rows", "cols", "data": {{"A1": "value or \
=python formula"}}}}). There is also an svg "drawing" cell that you \
must NEVER create or modify.

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
sheet2, ... (lists of rows). ks("A1") reads a sheet from Python and \
ks("A1", value) writes back.

READING: the full current notebook is included below — read it to \
understand and reason about the user's existing code in any cell.

WRITING: reply with each cell you want as ONE fenced block.
- To ADD a new cell, tag it with just the language: ```python, \
```markdown, ```latex or ```sheet.
- To REPLACE an existing cell, add its index from the listing, e.g. \
```python cell=3 — keep the same language unless the user wants the \
type changed.
- You may read and write code, markdown, latex and sheet cells. \
Never emit an svg cell.
Make every block self-contained and runnable; keep prose outside the \
fences brief.

Current notebook ({len(notebook.cells)} cells):
{_notebook_listing(notebook)}"""


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
    """AI Chat Settings — provider, model (with live refresh), API key and
    (for local servers) host, plus how-to-get-a-key help. Mirrors the
    KherveSheet dialog."""

    _HELP = {
        "anthropic": (
            "To get an API key:\n"
            "1. Go to console.anthropic.com\n"
            "2. Sign up or log in\n"
            "3. Navigate to API Keys in the left sidebar\n"
            '4. Click "Create Key" and copy the key (starts with sk-ant-)\n'
            "5. Add credit to your account under Billing"),
        "openai": (
            "To get an API key:\n"
            "1. Go to platform.openai.com\n"
            "2. Sign up or log in\n"
            "3. Navigate to API Keys in the left sidebar\n"
            '4. Click "Create new secret key" and copy it (starts with sk-)\n'
            "5. Add credit under Billing > Payment methods"),
        "mistral": (
            "To get an API key:\n"
            "1. Go to console.mistral.ai\n"
            "2. Sign up or log in\n"
            "3. Navigate to API Keys\n"
            '4. Click "Create new key" and copy it\n'
            "5. Add credit under Billing"),
        "ollama": (
            "Ollama runs locally — no API key needed.\n"
            "1. Download and install from ollama.com\n"
            '2. Run "ollama pull <model>" to download a model\n'
            "   (e.g. ollama pull llama3.2, ollama pull qwen2.5-coder)\n"
            "3. The server starts automatically on localhost:11434\n"
            "4. Use the Refresh button (⟳) to see available models"),
        "local": (
            "Connect to any OpenAI-compatible local server.\n"
            "Works with LM Studio, llama.cpp, LocalAI, Ollama\n"
            "(OpenAI mode), text-generation-webui, and others.\n\n"
            "1. Start your local server\n"
            "2. Enter the server URL below (e.g. http://localhost:1234/v1)\n"
            "3. Click Refresh (⟳) to see available models\n"
            "4. No API key is needed for most local servers"),
    }

    def __init__(self, parent=None, provider=None):
        super().__init__(parent)
        self.setWindowTitle("AI Chat Settings")
        self.setMinimumWidth(440)
        form = QFormLayout(self)

        self.provider = QComboBox()
        for name, meta in prov.PROVIDERS.items():
            label = meta["label"]
            if not prov.is_available(name):
                label += "  — not installed"
            self.provider.addItem(label, name)
        form.addRow("Provider:", self.provider)

        self.model = QComboBox()
        self.model.setEditable(True)
        model_row = QHBoxLayout()
        model_row.addWidget(self.model, 1)
        self.refresh_btn = QToolButton()
        self.refresh_btn.setText("⟳")
        self.refresh_btn.setToolTip("Refresh model list from the server")
        self.refresh_btn.clicked.connect(self._refresh_models)
        model_row.addWidget(self.refresh_btn)
        form.addRow("Model:", model_row)

        self.key = QLineEdit()
        self.key.setEchoMode(QLineEdit.Password)
        self.key_label = QLabel("API Key:")
        form.addRow(self.key_label, self.key)

        self.host = QLineEdit()
        self.host_label = QLabel("Ollama Host:")
        form.addRow(self.host_label, self.host)

        self.help_group = QGroupBox("How to get an API key")
        help_layout = QVBoxLayout(self.help_group)
        self.help_label = QLabel()
        self.help_label.setWordWrap(True)
        font = self.help_label.font()
        font.setPointSize(max(font.pointSize() - 1, 7))
        self.help_label.setFont(font)
        self.help_label.setStyleSheet(
            "color:#555; background:transparent; padding:2px;")
        help_layout.addWidget(self.help_label)
        form.addRow(self.help_group)

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

    def _name(self) -> str:
        return self.provider.currentData()

    def _load_provider(self):
        name = self._name()
        meta = prov.PROVIDERS[name]
        cfg = prov.load_config(name)
        self.model.blockSignals(True)
        self.model.clear()
        self.model.addItems(meta["models"])
        self.model.setCurrentText(cfg["model"])
        self.model.blockSignals(False)

        self.key_label.setVisible(meta["needs_key"])
        self.key.setVisible(meta["needs_key"])
        self.key.setText(cfg["key"])
        self.key.setPlaceholderText(
            {"anthropic": "sk-ant-...", "openai": "sk-..."}.get(name, ""))

        self.host_label.setVisible(meta["needs_host"])
        self.host.setVisible(meta["needs_host"])
        if meta["needs_host"]:
            self.host.setText(cfg["host"])
            self.host.setPlaceholderText(meta["host"])
            self.host_label.setText(
                "Server URL:" if name == "local" else "Ollama Host:")

        self.refresh_btn.setVisible(meta.get("refreshable", False))
        self.help_label.setText(self._HELP.get(name, ""))
        self.help_group.setTitle(
            "How to set up" if name in ("ollama", "local")
            else "How to get an API key")

    def _refresh_models(self):
        name = self._name()
        try:
            models = prov.fetch_models(name, self.key.text().strip(),
                                       self.host.text().strip())
        except Exception as exc:
            QMessageBox.warning(self, "Refresh failed", str(exc))
            return
        current = self.model.currentText()
        self.model.blockSignals(True)
        self.model.clear()
        self.model.addItems(models)
        if current in models:
            self.model.setCurrentText(current)
        self.model.blockSignals(False)

    def accept(self):
        name = self._name()
        prov.save_config(
            name, self.key.text().strip(), self.model.currentText().strip(),
            self.host.text().strip() or prov.PROVIDERS[name]["host"])
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
            "Ask about your notebook, or for analysis, plots or whole "
            "notebooks. The assistant reads every cell and can add new "
            "cells or rewrite existing ones (code, markdown, latex, "
            "sheet — never drawings); apply with one click.")
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
            nb = self._notebook
            edits = sum(1 for it in self._pending_cells
                        if it.get("target") is not None
                        and 0 <= it["target"] < len(nb.cells)
                        and nb.cells[it["target"]].CELL_TYPE != "svg")
            adds = n - edits
            bits = []
            if adds:
                bits.append(f"add {adds}")
            if edits:
                bits.append(f"replace {edits}")
            self.insert_btn.setText(
                f"Apply to notebook ({', '.join(bits)})")
        self.status.setText("")

    def _on_failed(self, message: str):
        self.status.setText(f"⚠ {message}")

    def _on_finished(self):
        self.send_btn.setEnabled(True)
        if self._worker is not None:
            self._worker.deleteLater()
            self._worker = None

    def _insert_cells(self):
        """Apply the pending blocks: replace targeted cells (never an svg
        drawing), append the rest, as one undo step."""
        from .undo_commands import SetSourceCmd
        nb = self._notebook
        replaces, appends = [], []
        for item in self._pending_cells:
            t = item.get("target")
            if (t is not None and 0 <= t < len(nb.cells)
                    and nb.cells[t].CELL_TYPE != "svg"):
                replaces.append(item)
            else:
                appends.append(item)

        nb.undo_stack.beginMacro("AI edit")
        for item in replaces:               # indices stay stable here
            cell = nb.cells[item["target"]]
            nb._select(cell)
            if cell.CELL_TYPE != item["type"]:
                nb.convert_current(item["type"])
                cell = nb.current
            nb.undo_stack.push(SetSourceCmd(nb, cell, item["source"],
                                            "AI edit"))
            if item["type"] in ("markdown", "latex", "sheet"):
                cell.execute(nb.kernel)
        for item in appends:
            cell = nb.add_cell_below(item["type"], item["source"],
                                     label="AI edit")
            if item["type"] in ("markdown", "latex", "sheet"):
                cell.execute(nb.kernel)
        nb.undo_stack.endMacro()

        parts = []
        if appends:
            parts.append(f"added {len(appends)}")
        if replaces:
            parts.append(f"replaced {len(replaces)}")
        self.status.setText(
            f"AI edit: {', '.join(parts) or 'nothing'} — review and run "
            "the code cells. Ctrl+Z undoes it.")
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
