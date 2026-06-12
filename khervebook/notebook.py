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

from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtWidgets import QScrollArea, QVBoxLayout, QWidget

from .cells import CodeCell, make_cell
from .kernel import Kernel

FORMAT_VERSION = 1


class NotebookWidget(QScrollArea):
    """Vertical list of cells with a shared execution kernel."""

    modified = pyqtSignal()

    def __init__(self):
        super().__init__()
        self.kernel = Kernel()
        self.setWidgetResizable(True)
        self._container = QWidget()
        self._layout = QVBoxLayout(self._container)
        self._layout.setAlignment(Qt.AlignTop)
        self._layout.setSpacing(6)
        self.setWidget(self._container)
        self.cells = []
        self.current = None
        self.add_cell("code")

    # -- cell management ------------------------------------------------
    def add_cell(self, cell_type: str, source: str = "", index: int = None):
        cell = make_cell(cell_type, source)
        cell.run_requested.connect(self._run_and_advance)
        cell.focused.connect(self._set_current)
        cell.editor.textChanged.connect(self.modified.emit)
        if index is None:
            index = len(self.cells)
        self.cells.insert(index, cell)
        self._layout.insertWidget(index, cell)
        self.modified.emit()
        return cell

    def remove_current(self):
        if self.current is None or len(self.cells) <= 1:
            return
        idx = self.cells.index(self.current)
        cell = self.cells.pop(idx)
        cell.deleteLater()
        self.current = self.cells[min(idx, len(self.cells) - 1)]
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
        self._layout.insertWidget(new, self.current)
        self.modified.emit()

    def _set_current(self, cell):
        self.current = cell

    # -- execution -------------------------------------------------------
    def run_current(self):
        if self.current is not None:
            self.current.execute(self.kernel)

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
        self.kernel.reset()
        for cell in self.cells:
            if isinstance(cell, CodeCell):
                cell.gutter.setText("In [ ]:")

    # -- persistence -------------------------------------------------------
    def to_json(self) -> str:
        doc = {"format": "kbook", "version": FORMAT_VERSION,
               "cells": [c.to_dict() for c in self.cells]}
        return json.dumps(doc, indent=1)

    def load_json(self, text: str):
        doc = json.loads(text)
        for cell in self.cells:
            cell.deleteLater()
        self.cells = []
        self.current = None
        self.kernel.reset()
        for item in doc.get("cells", []) or [{"type": "code", "source": ""}]:
            self.add_cell(item.get("type", "code"), item.get("source", ""))
