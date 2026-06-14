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

from PyQt5.QtCore import QSettings, QSize, Qt, QThread, pyqtSignal
from PyQt5.QtGui import QTextDocument
from PyQt5.QtWidgets import (QComboBox, QDialog, QDialogButtonBox,
                             QDockWidget, QFormLayout, QGroupBox, QHBoxLayout,
                             QLabel, QLineEdit, QMessageBox, QPlainTextEdit,
                             QPushButton, QSizePolicy, QTextBrowser,
                             QToolButton, QVBoxLayout, QWidget)

from . import ai_providers as prov
from .icons import icon


def _settings_store():
    return QSettings("Kherve", "KherveBook")

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


def _sheet_cell_summary(cell, start_n: int):
    """Describe a sheet cell by the published grid variables a code cell
    sees — sheetN, the sheet's name, size and column headers — so the
    model reads data the idiomatic way instead of guessing cell refs."""
    names = getattr(cell, "_names", []) or []
    tables = getattr(cell, "_tables", []) or []
    raw_of = getattr(cell, "_raw_of", None)
    lines = ["this sheet cell publishes these grids to code cells "
             "(each a list of rows; row 0 is the header):"]
    n = start_n
    for name, table in zip(names, tables):
        rows, cols = table.rowCount(), table.columnCount()
        header = []
        if raw_of is not None:
            header = [raw_of(table, 0, c) for c in range(min(cols, 16))]
            header = [h for h in header if h]
        cols_txt = f", columns {header}" if header else ""
        lines.append(f"  sheet{n} — name {name!r}, {rows} rows x {cols} "
                     f"cols{cols_txt}")
        n += 1
    return "\n".join(lines), len(tables)


def _notebook_listing(notebook) -> str:
    blocks, total, sheet_n = [], 0, 1
    for i, cell in enumerate(notebook.cells):
        if cell.CELL_TYPE == "svg":
            body = "(an SVG drawing — you cannot read or edit this cell)"
        elif cell.CELL_TYPE == "sheet":
            body, n_sheets = _sheet_cell_summary(cell, sheet_n)
            sheet_n += n_sheets
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
- Sheet cells publish each sheet to code cells as a variable sheet1, \
sheet2, ... — a list of rows, each row a list of cell values, header in \
row 0. THIS is the normal way to read a sheet's data. To load columns \
A and B: `rows = sheet1[1:]` (skip the header), then \
`a = [float(r[0]) for r in rows]; b = [float(r[1]) for r in rows]`, or \
build a DataFrame with `pd.DataFrame(sheet1[1:], columns=sheet1[0])`. \
The notebook listing below names the variable (sheet1, sheet2, …), the \
sheet name and the columns of every sheet — use it to pick the right \
variable (e.g. a sheet shown as "sheet5 — name 'Sheet5'" is read as \
`sheet5`). Do NOT loop ks() cell by cell; ks("A1") / ks("A1", v) is \
only for reading or writing a SINGLE cell.

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

Each applied cell is RUN immediately, so the task you are asked to do \
actually happens — do not just describe it. Every code block must be \
complete and syntactically valid Python with correct, consistent \
indentation (4 spaces, no half-indented lines), no truncation and no \
placeholders. Keep prose outside the fences brief.

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
    """Enter sends; Shift+Enter inserts a newline.

    Up/Down recall previously sent messages, shell-style — only when the
    cursor is on the first/last line, so multi-line drafts still edit
    normally. History persists across sessions via QSettings."""

    send = pyqtSignal()

    _MAX_HISTORY = 100
    _KEY = "ai/input_history"

    def __init__(self, parent=None):
        super().__init__(parent)
        stored = _settings_store().value(self._KEY, []) or []
        self._history = [str(x) for x in stored]
        self._hist_index = None        # None = editing a fresh draft
        self._draft = ""               # unsent text stashed on first recall

    def add_history(self, text: str):
        """Record a sent message and reset navigation."""
        text = text.rstrip()
        if text and (not self._history or self._history[-1] != text):
            self._history.append(text)
            self._history = self._history[-self._MAX_HISTORY:]
            _settings_store().setValue(self._KEY, self._history)
        self._hist_index = None
        self._draft = ""

    def clear_history(self):
        self._history = []
        self._hist_index = None
        self._draft = ""
        _settings_store().setValue(self._KEY, [])

    def _on_first_line(self) -> bool:
        return self.textCursor().blockNumber() == 0

    def _on_last_line(self) -> bool:
        return (self.textCursor().blockNumber()
                == self.document().blockCount() - 1)

    def _move_cursor_end(self):
        cur = self.textCursor()
        cur.movePosition(cur.End)
        self.setTextCursor(cur)

    def _history_prev(self):
        if not self._history:
            return
        if self._hist_index is None:        # entering history — save the draft
            self._draft = self.toPlainText()
            self._hist_index = len(self._history)
        if self._hist_index > 0:
            self._hist_index -= 1
            self.setPlainText(self._history[self._hist_index])
            self._move_cursor_end()

    def _history_next(self):
        if self._hist_index is None:
            return
        self._hist_index += 1
        if self._hist_index >= len(self._history):   # past newest -> draft
            self._hist_index = None
            self.setPlainText(self._draft)
        else:
            self.setPlainText(self._history[self._hist_index])
        self._move_cursor_end()

    def keyPressEvent(self, event):
        key = event.key()
        if (key in (Qt.Key_Return, Qt.Key_Enter)
                and not event.modifiers() & Qt.ShiftModifier):
            self.send.emit()
            return
        if key == Qt.Key_Up and self._on_first_line():
            self._history_prev()
            return
        if key == Qt.Key_Down and self._on_last_line():
            self._history_next()
            return
        super().keyPressEvent(event)


GREETING = (
    "Hello! I can help you build your notebook. Ask me to write or edit "
    "Python, Markdown, LaTeX or sheet cells, analyse your data, or make "
    "plots. I read every cell and can add new ones or rewrite existing "
    "ones (code, markdown, latex, sheet — never drawings); apply with one "
    "click and Ctrl+Z to undo. Set your provider (Anthropic, OpenAI, "
    "Mistral, Ollama, or Local AI) and API key via the gear icon.")

#: Example prompts shown by the ? button.
_PROMPTS = [
    "Plot a damped sine wave and label the axes.",
    "Add error handling and a docstring to cell 2.",
    "Make a 6×3 sheet of monthly sales with a Total column.",
    "Write a Markdown summary of what this notebook does.",
    "Rewrite cell 0 to vectorise the loop with NumPy.",
    "Add a LaTeX cell with the quadratic formula.",
    "Fit a Gaussian to the data in sheet1 and plot the fit.",
]


class _PromptHelpDialog(QDialog):
    """Click an example prompt to drop it into the chat input."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Example prompts")
        self.setMinimumWidth(360)
        self.chosen = None
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Try one of these — click to use it:"))
        for text in _PROMPTS:
            btn = QPushButton(text)
            btn.setStyleSheet("text-align:left; padding:6px")
            btn.clicked.connect(lambda _=False, t=text: self._pick(t))
            layout.addWidget(btn)
        close = QDialogButtonBox(QDialogButtonBox.Close)
        close.rejected.connect(self.reject)
        layout.addWidget(close)

    def _pick(self, text):
        self.chosen = text
        self.accept()


class AIChatDock(QDockWidget):
    """Bottom-left chat panel driving the notebook."""

    def __init__(self, notebook, parent=None):
        super().__init__("AI Chat", parent)
        self.setObjectName("ai_chat")
        self.setAllowedAreas(Qt.LeftDockWidgetArea | Qt.RightDockWidgetArea)
        self._notebook = notebook
        self._history = []          # neutral [{"role", "content"}]
        self._pending_cells = []
        self._worker = None
        self._font_pt = float(_settings_store().value("ai/chat_font_pt", 10.0))

        container = QWidget()
        column = QVBoxLayout(container)
        column.setContentsMargins(4, 4, 4, 4)
        column.setSpacing(4)

        # Header: "AI Assistant  provider · model"  +  A− A+ ? gear clear
        header = QHBoxLayout()
        self.title = QLabel("<b>AI Assistant</b>")
        self.title.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        header.addWidget(self.title, 1)
        for text, tip, slot in (
                ("A−", "Decrease text size", lambda: self._change_font(-1)),
                ("A+", "Increase text size", lambda: self._change_font(+1))):
            btn = QToolButton()
            btn.setText(text)
            btn.setToolTip(tip)
            btn.setAutoRaise(True)
            btn.clicked.connect(slot)
            header.addWidget(btn)
        self.auto_btn = QToolButton()
        self.auto_btn.setText("Auto")
        self.auto_btn.setCheckable(True)
        self.auto_btn.setAutoRaise(True)
        self.auto_btn.setToolTip(
            "Auto: apply and run the assistant's cells as soon as it "
            "replies, instead of waiting for the Apply button")
        self.auto_btn.setChecked(
            _settings_store().value("ai/auto_apply", False, type=bool))
        self.auto_btn.toggled.connect(
            lambda on: _settings_store().setValue("ai/auto_apply", on))
        header.addWidget(self.auto_btn)
        for icon_name, tip, slot in (
                ("mdi.help-circle-outline", "Example prompts", self._help),
                ("mdi.cog", "AI Chat settings", self._settings),
                ("mdi.delete-sweep", "Clear conversation", self._clear)):
            btn = QToolButton()
            btn.setIcon(icon(icon_name))
            btn.setToolTip(tip)
            btn.setAutoRaise(True)
            btn.clicked.connect(slot)
            header.addWidget(btn)
        column.addLayout(header)

        self.view = QTextBrowser()
        self.view.setOpenExternalLinks(False)
        self.view.setFrameShape(self.view.NoFrame)
        column.addWidget(self.view, 1)

        self.insert_btn = QPushButton("Apply && run")
        self.insert_btn.setIcon(icon("mdi.play-circle-outline"))
        self.insert_btn.hide()
        self.insert_btn.clicked.connect(self._insert_cells)
        column.addWidget(self.insert_btn)

        self.status = QLabel("")
        self.status.setWordWrap(True)
        column.addWidget(self.status)

        row = QHBoxLayout()
        self.input = _ChatInput()
        self.input.setPlaceholderText("Ask Claude to edit the notebook…")
        self.input.setFixedHeight(72)
        self.input.send.connect(self._send)
        row.addWidget(self.input, 1)
        self.send_btn = QToolButton()
        self.send_btn.setIcon(icon("mdi.send", "#27ae60"))
        self.send_btn.setToolTip("Send (Enter)")
        self.send_btn.setAutoRaise(True)
        self.send_btn.clicked.connect(self._send)
        row.addWidget(self.send_btn)
        column.addLayout(row)

        self.setWidget(container)
        self._update_title()
        self._apply_font()
        self._render_all()

    def sizeHint(self):
        return QSize(300, 600)

    # -- header / font -----------------------------------------------------
    def _update_title(self):
        cfg = prov.load_config(prov.saved_provider())
        meta = prov.PROVIDERS[cfg["provider"]]
        self.title.setText(
            f"<b>AI Assistant</b> <span style='color:#888;font-size:10px'>"
            f"{meta['label']} · {cfg['model']}</span>")

    def _change_font(self, delta: float):
        self._font_pt = max(7.0, min(24.0, self._font_pt + delta))
        _settings_store().setValue("ai/chat_font_pt", self._font_pt)
        self._apply_font()
        self._render_all()

    def _apply_font(self):
        f = self.input.font()
        f.setPointSizeF(self._font_pt)
        self.input.setFont(f)
        self.view.document().setDefaultFont(f)

    def _help(self):
        dlg = _PromptHelpDialog(self)
        if dlg.exec_() and dlg.chosen:
            self.input.setPlainText(dlg.chosen)
            self.input.setFocus()

    # -- conversation ------------------------------------------------------
    def _render_all(self):
        """Rebuild the transcript: greeting bubble, then the history."""
        self.view.clear()
        self._bubble("assistant", GREETING)
        for msg in self._history:
            self._bubble(msg["role"], msg["content"])

    def _bubble(self, role: str, text: str):
        if role == "user":
            who, color, bg = "You", "#2176c7", "#e7f0fb"
        else:
            who, color, bg = "AI", "#1f8a4c", "#eef1f4"
        self.view.append(
            f'<table width="100%" cellspacing="0" cellpadding="8" '
            f'style="margin:4px 0"><tr><td bgcolor="{bg}">'
            f'<b style="color:{color}">{who}</b>{_md_to_html(text)}'
            f'</td></tr></table>')
        self.view.verticalScrollBar().setValue(
            self.view.verticalScrollBar().maximum())

    def _append(self, role: str, text: str):
        self._bubble(role, text)

    def _send(self):
        text = self.input.toPlainText().strip()
        if not text or self._worker is not None:
            return
        name = prov.saved_provider()
        cfg = prov.load_config(name)
        if prov.PROVIDERS[name]["needs_key"] and not cfg["key"]:
            self._settings()
            cfg = prov.load_config(name)
            if not cfg["key"]:
                return
        self.input.add_history(text)        # Up/Down can recall it later
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
            self.insert_btn.setText(f"Apply && run ({', '.join(bits)})")
        self.status.setText("")
        if n and self.auto_btn.isChecked():     # do it without a click
            self._insert_cells()

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

        ran = []                            # cells to run after the macro
        nb.undo_stack.beginMacro("AI edit")
        for item in replaces:               # indices stay stable here
            cell = nb.cells[item["target"]]
            nb._select(cell)
            if cell.CELL_TYPE != item["type"]:
                nb.convert_current(item["type"])
                cell = nb.current
            nb.undo_stack.push(SetSourceCmd(nb, cell, item["source"],
                                            "AI edit"))
            ran.append(cell)
        for item in appends:
            ran.append(nb.add_cell_below(item["type"], item["source"],
                                         label="AI edit"))
        nb.undo_stack.endMacro()

        # Carry out the task: run every applied cell (code runs, text/sheet
        # render) so what the assistant proposed actually happens.
        for cell in ran:
            cell.execute(nb.kernel)

        parts = []
        if appends:
            parts.append(f"added {len(appends)}")
        if replaces:
            parts.append(f"replaced {len(replaces)}")
        self.status.setText(
            f"AI edit: {', '.join(parts) or 'nothing'} — applied and ran. "
            "Ctrl+Z undoes the edit.")
        self._pending_cells = []
        self.insert_btn.hide()

    def _settings(self):
        dlg = ApiKeyDialog(self, prov.saved_provider())
        if dlg.exec_():
            self._update_title()

    def _clear(self):
        self._history = []
        self._pending_cells = []
        self.insert_btn.hide()
        self.status.setText("")
        self._render_all()             # back to the greeting
