"""MainWindow shell: menus, toolbar, file I/O for .kbook documents.

Copyright (C) 2026 Gwilherm Kerherve

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.
"""

from pathlib import Path

from PyQt5.QtCore import QSize, Qt
from PyQt5.QtWidgets import (QAction, QComboBox, QFileDialog, QMainWindow,
                             QMessageBox, QToolBar)

from . import APP_NAME, __version__
from .celltoolbar import CellToolBar
from .explorer import FileExplorer
from .icons import app_icon, icon
from .notebook import NotebookWidget

FILE_FILTER = "KherveBook notebook (*.kbook);;All files (*)"


class MainWindow(QMainWindow):

    def __init__(self):
        super().__init__()
        self.notebook = NotebookWidget()
        self.notebook.modified.connect(self._mark_dirty)
        self.setCentralWidget(self.notebook)
        self.path = None
        self.dirty = False
        self.setWindowIcon(app_icon())
        self.explorer = FileExplorer(self)
        self.explorer.open_requested.connect(self._open_path)
        self.addDockWidget(Qt.LeftDockWidgetArea, self.explorer)
        self._build_menus()
        self._build_toolbar()
        self.notebook.current_changed.connect(self._on_current_cell)
        self.statusBar().showMessage(f"{APP_NAME} v{__version__}")
        self.resize(1000, 750)
        self._load_welcome()
        self._update_title()

    def _load_welcome(self):
        """Open with a pre-run example so a new user sees what the
        app does instead of an empty window."""
        from .welcome import load_welcome
        try:
            load_welcome(self.notebook)
        except Exception:
            pass    # an empty notebook is a fine fallback
        self.dirty = False

    # -- UI scaffolding ---------------------------------------------------
    def _build_menus(self):
        m = self.menuBar()
        f = m.addMenu("&File")
        f.addAction(self._act("&New", "Ctrl+N", self.new_file))
        f.addAction(self._act("&Open...", "Ctrl+O", self.open_file))
        f.addAction(self._act("&Save", "Ctrl+S", self.save_file))
        f.addAction(self._act("Save &As...", "Ctrl+Shift+S", self.save_as))
        f.addSeparator()
        f.addAction(self._act("E&xit", "Ctrl+Q", self.close))

        c = m.addMenu("&Cell")
        c.addAction(self._act("Add &Code Cell", "Ctrl+Shift+C",
                              lambda: self.notebook.add_cell("code")))
        c.addAction(self._act("Add &Markdown Cell", "Ctrl+Shift+M",
                              lambda: self.notebook.add_cell("markdown")))
        c.addAction(self._act("Add &LaTeX Cell", "Ctrl+Shift+L",
                              lambda: self.notebook.add_cell("latex")))
        c.addAction(self._act("Add &Sheet Cell", "Ctrl+Shift+T",
                              lambda: self.notebook.add_cell("sheet")))
        c.addSeparator()
        c.addAction(self._act("&Run Cell", "Ctrl+Return",
                              self.notebook.run_current))
        c.addAction(self._act("Run &All", "Ctrl+Shift+Return",
                              self.notebook.run_all))
        c.addSeparator()
        c.addAction(self._act("Cu&t Cell", "Ctrl+Shift+X",
                              self.notebook.cut_current))
        c.addAction(self._act("C&opy Cell", "Ctrl+Shift+O",
                              self.notebook.copy_current))
        c.addAction(self._act("&Paste Cell Below", "Ctrl+Shift+V",
                              self.notebook.paste_cell))
        c.addSeparator()
        c.addAction(self._act("Move Cell &Up", "Ctrl+Shift+Up",
                              lambda: self.notebook.move_current(-1)))
        c.addAction(self._act("Move Cell &Down", "Ctrl+Shift+Down",
                              lambda: self.notebook.move_current(1)))
        c.addAction(self._act("&Delete Cell", "Ctrl+Shift+D",
                              self.notebook.remove_current))

        k = m.addMenu("&Kernel")
        k.addAction(self._act("&Restart Kernel", "Ctrl+Shift+R",
                              self.notebook.restart_kernel))

        v = m.addMenu("&View")
        toggle = self.explorer.toggleViewAction()
        toggle.setText("&File Explorer")
        toggle.setShortcut("Ctrl+B")
        v.addAction(toggle)

        h = m.addMenu("&Help")
        h.addAction(self._act("&About", None, self._about))

    #: (label, type-key) pairs for the Jupyter-style cell-type selector.
    CELL_TYPES = [("Code", "code"), ("Markdown", "markdown"),
                  ("LaTeX", "latex"), ("Sheet", "sheet")]

    def _build_toolbar(self):
        """Jupyter-style main toolbar: file/cell ops, run, cell type."""
        nb = self.notebook
        tb = QToolBar("Main")
        tb.setMovable(False)
        tb.setIconSize(QSize(32, 32))
        self.addToolBar(tb)

        tb.addAction(self._act("Save", None, self.save_file,
                               "mdi.content-save",
                               "Save the notebook (Ctrl+S)"))
        tb.addSeparator()
        tb.addAction(self._act("Add cell", None,
                               lambda: nb.add_cell_below("code"),
                               "mdi.plus", "Insert a code cell below"))
        tb.addAction(self._act("Cut", None, nb.cut_current,
                               "mdi.content-cut", "Cut the selected cell"))
        tb.addAction(self._act("Copy", None, nb.copy_current,
                               "mdi.content-copy", "Copy the selected cell"))
        tb.addAction(self._act("Paste", None, nb.paste_cell,
                               "mdi.content-paste", "Paste the cell below"))
        tb.addSeparator()
        tb.addAction(self._act("Up", None, lambda: nb.move_current(-1),
                               "mdi.arrow-up", "Move the cell up"))
        tb.addAction(self._act("Down", None, lambda: nb.move_current(1),
                               "mdi.arrow-down", "Move the cell down"))
        tb.addSeparator()
        tb.addAction(self._act("Run", None, nb.run_current,
                               "mdi.play", "Run the selected cell "
                               "(Shift+Enter runs and advances)",
                               color="#27ae60"))
        tb.addAction(self._act("Restart", None, nb.restart_kernel,
                               "mdi.refresh", "Restart the kernel "
                               "(clears all variables)"))
        tb.addAction(self._act("Run all", None, nb.run_all,
                               "mdi.fast-forward",
                               "Restart and run every cell"))
        tb.addSeparator()

        self.cell_type_combo = QComboBox()
        for label, _key in self.CELL_TYPES:
            self.cell_type_combo.addItem(label)
        self.cell_type_combo.setToolTip("Change the selected cell's type")
        self.cell_type_combo.activated.connect(
            lambda i: nb.convert_current(self.CELL_TYPES[i][1]))
        tb.addWidget(self.cell_type_combo)

        # Second row: tools specific to the focused cell's type.
        self.addToolBarBreak()
        self.cell_toolbar = CellToolBar(nb, self)
        self.addToolBar(self.cell_toolbar)

    def _on_current_cell(self, cell):
        """Follow the focused cell: type selector + contextual toolbar."""
        if cell is None:
            return
        self.cell_toolbar.set_mode(cell.CELL_TYPE)
        for i, (_label, key) in enumerate(self.CELL_TYPES):
            if key == cell.CELL_TYPE:
                self.cell_type_combo.blockSignals(True)
                self.cell_type_combo.setCurrentIndex(i)
                self.cell_type_combo.blockSignals(False)
                break

    def _act(self, text, shortcut, slot, icon_name=None, tip=None,
             color=None):
        action = QAction(text, self)
        if icon_name:
            action.setIcon(icon(icon_name, color) if color
                           else icon(icon_name))
        if shortcut:
            action.setShortcut(shortcut)
        if tip:
            action.setToolTip(tip)
        action.triggered.connect(slot)
        return action

    # -- file I/O -----------------------------------------------------------
    def new_file(self):
        if not self._confirm_discard():
            return
        self.notebook.load_json('{"cells": []}')
        self.path = None
        self.dirty = False
        self._update_title()

    def open_file(self):
        name, _ = QFileDialog.getOpenFileName(self, "Open notebook",
                                              "", FILE_FILTER)
        if name:
            self._open_path(name)

    def _open_path(self, name: str):
        if not self._confirm_discard():
            return
        try:
            self.notebook.load_json(Path(name).read_text(encoding="utf-8"))
        except Exception as exc:
            QMessageBox.critical(self, APP_NAME, f"Could not open file:\n{exc}")
            return
        self.path = name
        self.dirty = False
        self.explorer.show_file(name)
        self._update_title()

    def save_file(self):
        if self.path is None:
            self.save_as()
            return
        Path(self.path).write_text(self.notebook.to_json(), encoding="utf-8")
        self.dirty = False
        self.explorer.show_file(self.path)
        self._update_title()

    def save_as(self):
        name, _ = QFileDialog.getSaveFileName(self, "Save notebook",
                                              "", FILE_FILTER)
        if not name:
            return
        if not name.lower().endswith(".kbook"):
            name += ".kbook"
        self.path = name
        self.save_file()

    def closeEvent(self, event):
        if self._confirm_discard():
            event.accept()
        else:
            event.ignore()

    def _confirm_discard(self) -> bool:
        if not self.dirty:
            return True
        ret = QMessageBox.question(
            self, APP_NAME, "Save changes to the current notebook?",
            QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel)
        if ret == QMessageBox.Save:
            self.save_file()
            return not self.dirty or self.path is not None
        return ret == QMessageBox.Discard

    def _mark_dirty(self):
        if not self.dirty:
            self.dirty = True
            self._update_title()

    def _update_title(self):
        name = Path(self.path).name if self.path else "Untitled"
        star = "*" if self.dirty else ""
        self.setWindowTitle(f"{star}{name} — {APP_NAME} v{__version__}")

    def _about(self):
        QMessageBox.about(
            self, f"About {APP_NAME}",
            f"<b>{APP_NAME}</b> v{__version__}<br>"
            "Jupyter-inspired computational notebook: Python, Markdown "
            "and LaTeX cells in one document.<br><br>"
            "Copyright © 2026 Gwilherm Kerherve — GPL-3.0")
