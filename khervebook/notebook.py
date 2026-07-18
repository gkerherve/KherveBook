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
                             QSizePolicy, QUndoStack, QVBoxLayout, QWidget)

from .cells import CodeCell, make_cell
from .kernel import Kernel
from .undo_commands import (AddCellCmd, ConvertCellCmd, MoveCellCmd,
                            RemoveCellCmd)
from . import sheetcell                  # noqa: F401  (registers "sheet")
from . import svgcell                    # noqa: F401  (registers "svg")
from . import jscell                     # noqa: F401  (registers "js")
from . import notecell                   # noqa: F401  (registers "note")
from . import filecell                   # noqa: F401  (registers "file")

# v5: "note" (rich text + pen) and "file" (attachments) cell types.
# v4: cells gained "height" (v3: title/column, v2: collapsed).
FORMAT_VERSION = 5

#: extension -> cell type for files dropped onto the notebook.
DROP_TYPES = {
    ".py": "code",
    ".md": "markdown", ".markdown": "markdown",
    ".tex": "latex",
    ".csv": "sheet", ".tsv": "sheet", ".txt": "sheet", ".dat": "sheet",
    ".xlsx": "xlsx", ".xlsm": "xlsx",     # Excel workbook -> sheet cell
    ".svg": "svg",                        # KhervePaint / any SVG drawing
    ".png": "image", ".jpg": "image", ".jpeg": "image",
    ".gif": "image", ".bmp": "image",
    ".pdf": "pdf",                        # rendered page-by-page to SVG
    ".kbook": "kbook",
    ".ksheet": "ksheet",                  # KherveSheet workbook
    ".kdocz": "kdoc",                     # kherveDOC document -> markdown
    ".ktex": "ktex", ".ktexz": "ktex",    # KherveTeX document -> latex
    ".ipynb": "ipynb",                    # Jupyter / Colab notebook
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
        self.setObjectName("notebook_scroll")   # the grey-bg scroll area
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
        self._page_mode = False             # continuous borderless page
        #: the notebook's own .kbook path once saved (set by MainWindow) —
        #: File cells resolve their sidecar folder relative to it.
        self.document_path = None
        self.current = None
        # Let code cells resolve attached files by name via kf("...").
        self.kernel.file_lookup = self._resolve_file
        self._clipboard = None              # dict from a cut/copied cell
        self._loop_cell = None              # cell being run continuously
        self._loop_timer = QTimer(self)
        self._loop_timer.timeout.connect(self._loop_tick)
        #: structural undo (add/remove/move/convert); text edits use the
        #: editor's own undo. Cleared whenever a document is loaded.
        self.undo_stack = QUndoStack(self)
        self.undo_stack.setUndoLimit(100)
        self.add_cell("code")

    # -- cell management ------------------------------------------------
    def _make_cell(self, cell_type: str, source: str = ""):
        """Create a wired-up cell widget without placing it in the layout."""
        cell = make_cell(cell_type, source)
        cell.run_requested.connect(self._run_and_advance)
        cell.run_clicked.connect(self.run_cell)
        cell.stop_clicked.connect(lambda _cell: self.stop_loop())
        cell.reset_clicked.connect(self.reset_cell)
        cell.menu_requested.connect(self._show_cell_menu)
        cell.file_dropped.connect(self.open_file_in_cell)
        cell.focused.connect(self._set_current)
        cell.editor.textChanged.connect(self.modified.emit)
        cell.content_changed.connect(self.modified.emit)
        cell.resized.connect(self._on_cell_resized)
        if isinstance(cell, filecell.FileCell) and self.document_path:
            p = Path(self.document_path)
            cell.set_context(p.parent, p.stem)
        return cell

    def _attach_cell(self, cell, index: int):
        """Place a (new or restored) live cell into the document at index.
        _relayout re-parents it into a row, which makes it visible again."""
        self.cells.insert(index, cell)
        self._apply_page_mode(cell)
        self._relayout()
        self.modified.emit()

    def _orphan(self, cell):
        """Pull a cell out of the document but keep the widget alive so an
        undo can restore it (with its output). setParent(None) detaches it
        from the row _relayout is about to delete without destroying it."""
        if cell is self.current:
            self.current = None
        if cell in self.cells:
            self.cells.remove(cell)
        cell.setParent(None)

    def _detach_cell(self, cell):
        self._orphan(cell)
        self._relayout()
        self.modified.emit()

    def _swap_cell(self, out, into, index: int):
        """Replace *out* with *into* at *index* (cell-type conversion)."""
        self._orphan(out)
        self.cells.insert(index, into)
        self._apply_page_mode(into)
        self._relayout()
        self._select(into, focus=True)
        self.modified.emit()

    def _select(self, cell, focus: bool = False):
        self._set_current(cell)
        if focus and cell is not None:
            cell.focus_editor()

    def add_cell(self, cell_type: str, source: str = "", index: int = None):
        """Create and place a cell directly (not undoable; used on load,
        examples, run-and-advance and the initial cell)."""
        cell = self._make_cell(cell_type, source)
        if index is None:
            index = len(self.cells)
        self._attach_cell(cell, index)
        return cell

    # -- undo / redo (structural) -----------------------------------------
    def undo(self):
        self.stop_loop()
        if self.undo_stack.canUndo():
            self.undo_stack.undo()

    def redo(self):
        self.stop_loop()
        if self.undo_stack.canRedo():
            self.undo_stack.redo()

    # -- page (continuous) mode -------------------------------------------
    @property
    def page_mode(self) -> bool:
        return self._page_mode

    def set_page_mode(self, on: bool):
        """Continuous page: cells lose their borders and the gaps close,
        so the notebook reads as one long page regardless of cell type."""
        self._page_mode = bool(on)
        self._layout.setSpacing(0 if self._page_mode else 6)
        self.setProperty("pageMode", self._page_mode)
        self.style().unpolish(self)
        self.style().polish(self)
        for cell in self.cells:
            self._apply_page_mode(cell)

    def _apply_page_mode(self, cell):
        cell.setProperty("pageMode", self._page_mode)
        cell.style().unpolish(cell)
        cell.style().polish(cell)

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
        max_w = 0
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
            if len(group) == 1 and group[0].content_width():
                # A custom-width cell sits at that width, left-aligned;
                # if it is wider than the viewport the notebook scrolls.
                hbox.addWidget(group[0], 0)
                hbox.addStretch(1)
                max_w = max(max_w, group[0].content_width())
            else:
                for c in group:
                    hbox.addWidget(c, 1)
            self._layout.addWidget(row)
            self._rows.append(row)
            i = j
        self._layout.addStretch(1)          # absorb extra space, not rows
        # Let the container exceed the viewport so a wide cell scrolls.
        self._container.setMinimumWidth(max_w)
        self._container.setUpdatesEnabled(True)

    def _on_cell_resized(self):
        self._relayout()
        self.modified.emit()

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
        self.undo_stack.push(RemoveCellCmd(self, self.current))

    def move_current(self, delta: int):
        if self.current is None:
            return
        idx = self.cells.index(self.current)
        if not 0 <= idx + delta < len(self.cells):
            return
        self.undo_stack.push(MoveCellCmd(self, self.current, delta))

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

    def add_cell_below(self, cell_type: str, source: str = "",
                       label: str = "Add cell"):
        """Insert a cell after the current one (Jupyter's '+'), undoably."""
        idx = (self.cells.index(self.current) + 1
               if self.current in self.cells else len(self.cells))
        cell = self._make_cell(cell_type, source)
        self.undo_stack.push(AddCellCmd(self, cell, idx, label))
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
            # Cutting the only cell leaves a fresh empty code cell —
            # add-then-remove as one undo step.
            self.undo_stack.beginMacro("Cut cell")
            self.add_cell_below("code", label="Cut cell")
            self.undo_stack.push(RemoveCellCmd(self, self.cells[0], "Cut cell"))
            self.undo_stack.endMacro()
        else:
            self.undo_stack.push(RemoveCellCmd(self, self.current, "Cut cell"))

    def paste_cell(self):
        if not self._clipboard:
            return
        self.add_cell_below(self._clipboard.get("type", "code"),
                            self._clipboard.get("source", ""),
                            label="Paste cell")

    def convert_current(self, cell_type: str):
        """Change the current cell's type, keeping its source (undoable)."""
        cell = self.current
        if cell is None or cell.CELL_TYPE == cell_type:
            return
        new = self._make_cell(cell_type, cell.source())
        new.set_beside_previous(cell.beside_previous)   # keep its place/heading
        new.set_title(cell.title)
        if cell.collapsed:
            new.set_collapsed(True)
        self.undo_stack.push(ConvertCellCmd(self, cell, new))

    # -- execution -------------------------------------------------------
    def run_current(self):
        if self.current is not None:
            self.current.execute(self.kernel)

    def run_cell(self, cell):
        """Run *cell* in place (gutter button / context menu)."""
        self._set_current(cell)
        cell.execute(self.kernel)

    def reset_cell(self, cell):
        """Restart a single cell: drop the kernel globals it created and
        re-run it, without touching the rest of the namespace. Lets a
        live-loop cell (e.g. the boids) re-seed after an edit without a
        full Kernel > Restart. A looping cell keeps looping."""
        if not hasattr(cell, "reset_state"):
            return
        self._set_current(cell)
        cell.reset_state(self.kernel)
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
        if hasattr(cell, "reset_state"):
            menu.addAction("Restart This Cell",
                           lambda: self.reset_cell(cell))
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
            sel = " from Selection" if cell.has_selection() else ""
            plot_menu = menu.addMenu(f"Create Plot{sel}")
            for label, k in (("Line", "line"), ("Bar", "bar"),
                             ("Scatter", "scatter")):
                plot_menu.addAction(
                    label, lambda kind=k: cell.plot_selection(kind))
        menu.addSeparator()
        menu.addAction("Cut Cell", self.cut_current)
        menu.addAction("Copy Cell", self.copy_current)
        menu.addAction("Paste Cell Below", self.paste_cell)
        conv = menu.addMenu("Convert To")
        for label, key in (("Code", "code"), ("Markdown", "markdown"),
                           ("Note", "note"), ("LaTeX", "latex"),
                           ("Sheet", "sheet"), ("SVG", "svg"),
                           ("JavaScript", "js"), ("File", "file")):
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
        nxt.focus_editor()
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
        # A file dropped onto a File cell always attaches to it, whatever
        # its type — that is how the cell holds an arbitrary file.
        if isinstance(cell, filecell.FileCell) and p.is_file():
            self._set_current(cell)
            ok = cell.attach(str(p))
            if ok:
                self.modified.emit()
            return ok
        kind = DROP_TYPES.get(p.suffix.lower())
        if kind is None and importers.is_ktex(str(p)):
            kind = "ktex"                  # .ktex.json double suffix
        elif kind is None and importers.is_kdoc(str(p)):
            kind = "kdoc"                  # .kdoc.json double suffix
        if kind is None or not p.is_file():
            return False
        if kind == "kbook":
            self.open_kbook_requested.emit(str(p))
            return True
        if kind in ("ksheet", "kdoc", "ktex", "ipynb", "image", "pdf",
                    "xlsx"):
            try:
                if kind == "ipynb":
                    from . import ipynb
                    items = ipynb.from_ipynb(
                        p.read_text(encoding="utf-8"))
                else:
                    importer = {"ksheet": importers.ksheet_to_cells,
                                "kdoc": importers.kdoc_to_cells,
                                "ktex": importers.ktex_to_cells,
                                "image": importers.image_to_cells,
                                "pdf": importers.pdf_to_cells,
                                "xlsx": importers.xlsx_to_cells}[kind]
                    items = importer(str(p))
            except Exception:
                return False
            if not items:
                return False
            if cell is not None:
                self._set_current(cell)
            self.undo_stack.beginMacro(f"Import {p.name}")
            for item in items:
                new = self.add_cell_below(item["type"], item["source"],
                                          label=f"Import {p.name}")
                if item["type"] in ("markdown", "latex", "svg", "sheet"):
                    new.execute(self.kernel)
            self.undo_stack.endMacro()
            self.modified.emit()
            return True
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
        if kind in ("markdown", "latex", "svg"):
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

    # -- attached files (File cells) ---------------------------------------
    def set_document_path(self, path):
        """Tell the notebook where its .kbook lives so File cells can find
        their sidecar folder and code cells can resolve kf('name')."""
        self.document_path = str(path) if path else None
        p = Path(path) if path else None
        doc_dir = p.parent if p else None
        stem = p.stem if p else "notebook"
        self.kernel.notebook_dir = doc_dir
        for cell in self.cells:
            if isinstance(cell, filecell.FileCell):
                cell.set_context(doc_dir, stem)

    def prepare_save(self):
        """Before writing the .kbook, materialise large attachments into the
        sidecar folder (small ones stay embedded)."""
        if self.document_path is None:
            return
        self.set_document_path(self.document_path)
        for cell in self.cells:
            if isinstance(cell, filecell.FileCell):
                cell.materialize()

    def _resolve_file(self, name: str):
        """kf('name') -> absolute path of a File cell's attachment, or None."""
        for cell in self.cells:
            if isinstance(cell, filecell.FileCell) and cell.file_name == name:
                return cell.resolved_path()
        return None

    # -- persistence -------------------------------------------------------
    def to_json(self) -> str:
        doc = {"format": "kbook", "version": FORMAT_VERSION,
               "cells": [c.to_dict() for c in self.cells]}
        return json.dumps(doc, indent=1)

    def load_json(self, text: str):
        self._apply_cells(json.loads(text).get("cells", []))

    def load_ipynb(self, text: str):
        """Replace the notebook with an imported Jupyter/Colab .ipynb."""
        from . import ipynb
        self._apply_cells(ipynb.from_ipynb(text))

    def to_ipynb(self) -> str:
        """Serialise the notebook to a Jupyter/Colab .ipynb string."""
        from . import ipynb
        return ipynb.to_ipynb([c.to_dict() for c in self.cells])

    def _apply_cells(self, items):
        self.stop_loop()
        self.undo_stack.clear()             # can't undo across a load
        self._suspend_layout = True         # one relayout at the end
        for cell in self.cells:
            cell.deleteLater()
        self.cells = []
        self.current = None
        self.kernel.reset()
        for item in (items or [{"type": "code", "source": ""}]):
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
            if item.get("width"):
                cell.set_content_width(item["width"])
        self._suspend_layout = False
        self._relayout()
