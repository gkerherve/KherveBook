"""MainWindow shell: menus, toolbar, file I/O for .kbook documents.

Copyright (C) 2026 Gwilherm Kerherve

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.
"""

from pathlib import Path

from PyQt5.QtWidgets import (QAction, QFileDialog, QMainWindow, QMessageBox,
                             QToolBar)

from . import APP_NAME, __version__
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
        self._build_menus()
        self._build_toolbar()
        self.statusBar().showMessage(f"{APP_NAME} v{__version__}")
        self.resize(1000, 750)
        self._update_title()

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
        c.addSeparator()
        c.addAction(self._act("&Run Cell", "Ctrl+Return",
                              self.notebook.run_current))
        c.addAction(self._act("Run &All", "Ctrl+Shift+Return",
                              self.notebook.run_all))
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

        h = m.addMenu("&Help")
        h.addAction(self._act("&About", None, self._about))

    def _build_toolbar(self):
        tb = QToolBar("Main")
        tb.setMovable(False)
        self.addToolBar(tb)
        tb.addAction(self._act("+Code", None,
                               lambda: self.notebook.add_cell("code")))
        tb.addAction(self._act("+Markdown", None,
                               lambda: self.notebook.add_cell("markdown")))
        tb.addAction(self._act("+LaTeX", None,
                               lambda: self.notebook.add_cell("latex")))
        tb.addSeparator()
        tb.addAction(self._act("Run", None, self.notebook.run_current))
        tb.addAction(self._act("Run All", None, self.notebook.run_all))

    def _act(self, text, shortcut, slot):
        action = QAction(text, self)
        if shortcut:
            action.setShortcut(shortcut)
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
        if not self._confirm_discard():
            return
        name, _ = QFileDialog.getOpenFileName(self, "Open notebook",
                                              "", FILE_FILTER)
        if not name:
            return
        try:
            self.notebook.load_json(Path(name).read_text(encoding="utf-8"))
        except Exception as exc:
            QMessageBox.critical(self, APP_NAME, f"Could not open file:\n{exc}")
            return
        self.path = name
        self.dirty = False
        self._update_title()

    def save_file(self):
        if self.path is None:
            self.save_as()
            return
        Path(self.path).write_text(self.notebook.to_json(), encoding="utf-8")
        self.dirty = False
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
