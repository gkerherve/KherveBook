"""NotebookWidget — a scrollable column of cells sharing one kernel.

Handles add/remove/move/run of cells and (de)serialisation to the
JSON-based .kbook document format.

Copyright (C) 2026 Gwilherm Kerherve

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.
"""

import json
from pathlib import Path

from PyQt5.QtCore import Qt, QTimer, pyqtSignal
from PyQt5.QtWidgets import (QHBoxLayout, QInputDialog, QMenu, QScrollArea,
                             QSizePolicy, QVBoxLayout, QWidget)

from .cells import CodeCell, make_cell
from .kernel import Kernel
from . import sheetcell                  # noqa: F401  (registers "sheet")

# v4: cells gained "height" (v3: title/column, v2: collapsed).
FORMAT_VERSION = 4

#: extension -> cell type for files dropped onto the notebook.
DROP_TYPES = {
    ".py": "code",
    ".md": "markdown", ".markdown": "markdown",
    ".tex": "latex",
    ".csv": "sheet", ".tsv": "sheet", ".txt": "sheet", ".dat": "sheet",
    ".png": "image", ".jpg": "image", ".jpeg": "image",
    ".gif": "image", ".bmp": "image",
    ".kbook": "kbook",
    ".ksheet": "ksheet",                  # KherveSheet workbook
    ".kdocz": "kdoc", ".ktexz": "kdoc",   # kherveDOC document
}
_MAX_DROP_BYTES = 2_000_000


class NotebookWidget(QScrollArea):
    """Vertical list of cells with a shared execution kernel."""

    modified = pyqtSignal()
    current_changed = pyqtSignal(object)   # the newly focused cell
    open_kbook_requested = pyqtSignal(str)  # a .kbook was dropped

    def __init__(self):
        super().__init__()
        self.kernel = Kernel()
        self.setAcceptDrops(True)
        self.setWidgetResizable(True)
        self._container = QWidget()
        self._layout = QVBoxLayout(self._container)
        self._layout.setAlignment(Qt.AlignTop)
        self._layout.setSpacing(6)
        self.setWidget(self._container)
        self.cells = []
        self._rows = []                     # row container widgets
        self._suspend_layout = False
        self.current = None
        self._clipboard = None              # dict from a cut/copied cell
        self._loop_cell = None              # cell being run continuously
        self._loop_timer = QTimer(self)
        self._loop_timer.timeout.connect(self._loop_tick)
        self.add_cell("code")

    # -- cell management ------------------------------------------------
    def add_cell(self, cell_type: str, source: str = "", index: int = None):
        cell = make_cell(cell_type, source)
        cell.run_requested.connect(self._run_and_advance)
        cell.run_clicked.connect(self.run_cell)
        cell.stop_clicked.connect(lambda _cell: self.stop_loop())
        cell.menu_requested.connect(self._show_cell_menu)
        cell.file_dropped.connect(self.open_file_in_cell)
        cell.focused.connect(self._set_current)
        cell.editor.textChanged.connect(self.modified.emit)
        cell.content_changed.connect(self.modified.emit)
        if index is None:
            index = len(self.cells)
        self.cells.insert(index, cell)
        self._relayout()
        self.modified.emit()
        return cell

    def _relayout(self):
        """Rebuild the layout, grouping consecutive 'column' cells into
        one horizontal row. self.cells stays the flat document order."""
        if self._suspend_layout:
            return
        self._container.setUpdatesEnabled(False)
        for cell in self.cells:             # detach so row deletes are safe
            cell.setParent(None)
        while self._layout.count():         # clear rows AND any stretch
            item = self._layout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()
        self._rows = []
        i, n = 0, len(self.cells)
        while i < n:
            group = [self.cells[i]]
            j = i + 1
            while j < n and self.cells[j].beside_previous:
                group.append(self.cells[j])
                j += 1
            row = QWidget()
            row.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Maximum)
            hbox = QHBoxLayout(row)
            hbox.setContentsMargins(0, 0, 0, 0)
            hbox.setSpacing(6)
            for c in group:
                hbox.addWidget(c, 1)
            self._layout.addWidget(row)
            self._rows.append(row)
            i = j
        self._layout.addStretch(1)          # absorb extra space, not rows
        self._container.setUpdatesEnabled(True)

    def set_cell_column(self, cell, on: bool):
        """Place *cell* beside the previous one (same row), or on its own."""
        if on and self.cells.index(cell) == 0:
            return                          # the first cell starts a row
        cell.set_beside_previous(on)
        self._relayout()
        self.modified.emit()

    def remove_current(self):
        if self.current is None or len(self.cells) <= 1:
            return
        idx = self.cells.index(self.current)
        self.cells.pop(idx)
        self.current = None
        self._relayout()                    # deletes the removed cell's row
        self._set_current(self.cells[min(idx, len(self.cells) - 1)])
        self.current.editor.setFocus()
        self.modified.emit()

    def move_current(self, delta: int):
        if self.current is None:
            return
        idx = self.cells.index(self.current)
        new = idx + delta
        if not 0 <= new < len(self.cells):
            return
        self.cells.insert(new, self.cells.pop(idx))
        self._relayout()
        self.modified.emit()

    def _set_current(self, cell):
        if cell is self.current:
            return
        old, self.current = self.current, cell
        for w in (old, cell):
            if w is not None:
                w.setProperty("current", w is cell)
                w.style().unpolish(w)
                w.style().polish(w)
        self.current_changed.emit(cell)

    def add_cell_below(self, cell_type: str, source: str = ""):
        """Insert a cell after the current one (Jupyter's '+') and focus it."""
        idx = (self.cells.index(self.current) + 1
               if self.current in self.cells else len(self.cells))
        cell = self.add_cell(cell_type, source, idx)
        # Select explicitly — focus events alone can lag or be absent.
        self._set_current(cell)
        cell.editor.setFocus()
        return cell

    # -- cell clipboard / conversion --------------------------------------
    def copy_current(self):
        if self.current is not None:
            self._clipboard = self.current.to_dict()

    def cut_current(self):
        if self.current is None:
            return
        self.copy_current()
        if len(self.cells) == 1:
            # Cutting the only cell leaves a fresh empty code cell.
            self.add_cell("code")
        self.remove_current()

    def paste_cell(self):
        if not self._clipboard:
            return
        self.add_cell_below(self._clipboard.get("type", "code"),
                            self._clipboard.get("source", ""))

    def convert_current(self, cell_type: str):
        """Change the current cell's type, keeping its source."""
        cell = self.current
        if cell is None or cell.CELL_TYPE == cell_type:
            return
        idx = self.cells.index(cell)
        source = cell.source()
        col, title = cell.beside_previous, cell.title
        self.cells.pop(idx)
        cell.deleteLater()
        new = self.add_cell(cell_type, source, idx)
        new.set_beside_previous(col)        # keep its place in the row
        new.set_title(title)
        self._relayout()
        self.current = None
        self._set_current(new)
        new.editor.setFocus()

    # -- execution -------------------------------------------------------
    def run_current(self):
        if self.current is not None:
            self.current.execute(self.kernel)

    def run_cell(self, cell):
        """Run *cell* in place (gutter button / context menu)."""
        self._set_current(cell)
        cell.execute(self.kernel)

    # -- continuous run ---------------------------------------------------
    def start_loop(self, cell=None, interval_ms: int = 60):
        """Re-run *cell* (default: current) every *interval_ms* —
        for live simulations and animations. One cell loops at a time."""
        cell = cell or self.current
        if cell is None:
            return
        self.stop_loop()
        self._loop_cell = cell
        cell.set_looping(True)
        cell.execute(self.kernel)
        self._loop_timer.start(interval_ms)

    def stop_loop(self):
        self._loop_timer.stop()
        if self._loop_cell is not None:
            self._loop_cell.set_looping(False)
            self._loop_cell = None

    @property
    def looping(self) -> bool:
        return self._loop_cell is not None

    def _loop_tick(self):
        cell = self._loop_cell
        if cell is None or cell not in self.cells:
            self.stop_loop()
            return
        cell.execute(self.kernel)

    def _show_cell_menu(self, cell, global_pos):
        """Right-click menu with the per-cell operations."""
        self._set_current(cell)
        menu = QMenu(self)
        menu.addAction("Run Cell", lambda: self.run_cell(cell))
        if cell is self._loop_cell:
            menu.addAction("Stop Continuous Run", self.stop_loop)
        else:
            menu.addAction("Run Continuously",
                           lambda: self.start_loop(cell))
        menu.addAction("Expand Cell" if cell.collapsed else "Collapse Cell",
                       lambda: cell.set_collapsed(not cell.collapsed))
        menu.addAction("Edit Title…" if cell.title else "Set Title…",
                       lambda: self._set_cell_title(cell))
        if isinstance(cell, sheetcell.SheetCell):
            view_menu = menu.addMenu("View")
            for k, title in enumerate(cell.view_titles()):
                act = view_menu.addAction(title)
                act.setCheckable(True)
                act.setChecked(k == cell.current_view_index())
                act.triggered.connect(
                    lambda _=False, i=k: cell.set_view_index(i))
            view_menu.addSeparator()
            view_menu.addAction("Add Sheet", cell.add_sheet)
        menu.addSeparator()
        menu.addAction("Cut Cell", self.cut_current)
        menu.addAction("Copy Cell", self.copy_current)
        menu.addAction("Paste Cell Below", self.paste_cell)
        conv = menu.addMenu("Convert To")
        for label, key in (("Code", "code"), ("Markdown", "markdown"),
                           ("LaTeX", "latex"), ("Sheet", "sheet")):
            if key != cell.CELL_TYPE:
                conv.addAction(label,
                               lambda k=key: self.convert_current(k))
        menu.addSeparator()
        menu.addAction("Move Up", lambda: self.move_current(-1))
        menu.addAction("Move Down", lambda: self.move_current(1))
        idx = self.cells.index(cell)
        if cell.beside_previous:
            menu.addAction("Move to Own Row",
                           lambda: self.set_cell_column(cell, False))
        elif idx > 0:
            menu.addAction("Place Beside Cell Above",
                           lambda: self.set_cell_column(cell, True))
        menu.addSeparator()
        menu.addAction("Delete Cell", self.remove_current)
        menu.exec_(global_pos)

    def _set_cell_title(self, cell):
        text, ok = QInputDialog.getText(
            self, "Cell title", "Title (leave empty to remove):",
            text=cell.title)
        if ok:
            cell.set_title(text)
            self.modified.emit()

    def _run_and_advance(self, cell):
        cell.execute(self.kernel)
        idx = self.cells.index(cell)
        if idx + 1 == len(self.cells):
            self.add_cell("code")
        nxt = self.cells[idx + 1]
        nxt.editor.show()
        nxt.editor.setFocus()
        self.ensureWidgetVisible(nxt)

    def run_all(self):
        self.kernel.reset()
        for cell in self.cells:
            cell.execute(self.kernel)

    def restart_kernel(self):
        self.stop_loop()
        self.kernel.reset()
        for cell in self.cells:
            if isinstance(cell, CodeCell):
                cell.gutter.setText("In [ ]:")

    # -- file drops ---------------------------------------------------------
    def open_file_in_cell(self, path: str, cell=None) -> bool:
        """Load a recognised file into *cell* (or a new cell at the end).

        .py -> code, .md -> markdown, .tex -> latex, tabular text ->
        sheet, images -> markdown image, .kbook -> open the notebook.
        Returns False for unrecognised or unreadable files.
        """
        from . import importers
        p = Path(path)
        kind = DROP_TYPES.get(p.suffix.lower())
        if kind is None and importers.is_kdoc(str(p)):
            kind = "kdoc"                  # .kdoc.json double suffix
        if kind is None or not p.is_file():
            return False
        if kind == "kbook":
            self.open_kbook_requested.emit(str(p))
            return True
        if kind in ("ksheet", "kdoc"):
            try:
                importer = (importers.ksheet_to_cells if kind == "ksheet"
                            else importers.kdoc_to_cells)
                items = importer(str(p))
            except Exception:
                return False
            if not items:
                return False
            if cell is not None:
                self._set_current(cell)
            for item in items:
                new = self.add_cell_below(item["type"], item["source"])
                if item["type"] in ("markdown", "latex"):
                    new.execute(self.kernel)
            self.modified.emit()
            return True
        if kind == "image":
            kind, source = "markdown", f"![{p.name}]({p.as_uri()})"
        else:
            try:
                if p.stat().st_size > _MAX_DROP_BYTES:
                    return False
                source = p.read_text(encoding="utf-8", errors="replace")
            except OSError:
                return False

        if cell is None:
            cell = self.add_cell_below(kind, source)
        else:
            self._set_current(cell)
            if cell.CELL_TYPE != kind:
                self.convert_current(kind)
                cell = self.current
            cell.set_source(source)
        # Render text content immediately; code/sheet wait for the user
        # (their run executes, which a drop should not do by itself).
        if kind in ("markdown", "latex"):
            cell.execute(self.kernel)
        self.modified.emit()
        return True

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dragMoveEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event):
        """Files dropped on empty notebook space append new cells."""
        for url in event.mimeData().urls():
            if url.isLocalFile():
                self.open_file_in_cell(url.toLocalFile())
        event.acceptProposedAction()

    # -- persistence -------------------------------------------------------
    def to_json(self) -> str:
        doc = {"format": "kbook", "version": FORMAT_VERSION,
               "cells": [c.to_dict() for c in self.cells]}
        return json.dumps(doc, indent=1)

    def load_json(self, text: str):
        self.stop_loop()
        doc = json.loads(text)
        self._suspend_layout = True         # one relayout at the end
        for cell in self.cells:
            cell.deleteLater()
        self.cells = []
        self.current = None
        self.kernel.reset()
        for item in doc.get("cells", []) or [{"type": "code", "source": ""}]:
            cell = self.add_cell(item.get("type", "code"),
                                 item.get("source", ""))
            if item.get("title"):
                cell.set_title(item["title"])
            if item.get("collapsed"):
                cell.set_collapsed(True)
            if item.get("column"):
                cell.set_beside_previous(True)
            if item.get("height"):
                cell.set_content_height(item["height"])
        self._suspend_layout = False
        self._relayout()
