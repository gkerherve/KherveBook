"""File explorer side panel.

A dockable tree of the working folder so you can see your notebooks
and data while you work. Double-clicking a .kbook opens it; other
notebook-ish files (.py, .ipynb, .csv, ...) are shown for context.

Copyright (C) 2026 Gwilherm Kerherve

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.
"""

from pathlib import Path

from PyQt5.QtCore import QDir, pyqtSignal
from PyQt5.QtWidgets import QDockWidget, QFileSystemModel, QTreeView


class FileExplorer(QDockWidget):
    """Dockable file tree rooted at the current notebook's folder."""

    open_requested = pyqtSignal(str)    # absolute path of a .kbook

    #: Files surfaced in the tree; everything else is greyed out.
    FILTERS = ["*.kbook", "*.ipynb", "*.py", "*.csv", "*.txt", "*.md"]

    def __init__(self, parent=None):
        super().__init__("Files", parent)
        self.setObjectName("file_explorer")

        self._model = QFileSystemModel(self)
        self._model.setNameFilters(self.FILTERS)
        self._model.setNameFilterDisables(True)    # grey, don't hide

        self._tree = QTreeView()
        self._tree.setModel(self._model)
        self._tree.setHeaderHidden(True)
        for col in range(1, self._model.columnCount()):
            self._tree.hideColumn(col)             # name column only
        self._tree.setAnimated(True)
        self._tree.doubleClicked.connect(self._on_double_click)
        self.setWidget(self._tree)

        self.set_root(QDir.homePath())

    def set_root(self, folder: str):
        """Point the tree at *folder* (e.g. the opened file's folder)."""
        self._model.setRootPath(folder)
        self._tree.setRootIndex(self._model.index(folder))

    def show_file(self, path: str):
        """Re-root to the file's folder and select it."""
        p = Path(path)
        self.set_root(str(p.parent))
        idx = self._model.index(str(p))
        if idx.isValid():
            self._tree.setCurrentIndex(idx)

    def _on_double_click(self, index):
        path = self._model.filePath(index)
        if self._model.isDir(index):
            return                                  # tree expands itself
        if path.lower().endswith(".kbook"):
            self.open_requested.emit(path)
