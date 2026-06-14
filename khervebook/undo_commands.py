"""Undo/redo commands for cell structure (add, remove, move, convert).

Each command keeps the live cell widget(s) it operates on, so undoing a
delete or a type change brings the cell back with its output intact —
the widget is detached from the layout, not destroyed. Text edits keep
their own per-editor undo and are not on this stack.

Copyright (C) 2026 Gwilherm Kerherve

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.
"""

from PyQt5.QtWidgets import QUndoCommand


class AddCellCmd(QUndoCommand):
    """Insert an already-made cell at *index* (redo) / remove it (undo)."""

    def __init__(self, nb, cell, index, text="Add cell"):
        super().__init__(text)
        self.nb, self.cell, self.index = nb, cell, index

    def redo(self):
        self.nb._attach_cell(self.cell, self.index)
        self.nb._select(self.cell, focus=True)

    def undo(self):
        self.nb._detach_cell(self.cell)


class RemoveCellCmd(QUndoCommand):
    """Remove *cell* (redo), keeping the widget so undo restores it."""

    def __init__(self, nb, cell, text="Delete cell"):
        super().__init__(text)
        self.nb, self.cell = nb, cell
        self.index = nb.cells.index(cell)

    def redo(self):
        self.nb._detach_cell(self.cell)
        if self.nb.cells:
            nxt = self.nb.cells[min(self.index, len(self.nb.cells) - 1)]
            self.nb._select(nxt, focus=True)

    def undo(self):
        self.nb._attach_cell(self.cell, self.index)
        self.nb._select(self.cell, focus=True)


class MoveCellCmd(QUndoCommand):
    """Shift *cell* by *delta* positions, invertible."""

    def __init__(self, nb, cell, delta):
        super().__init__("Move cell")
        self.nb, self.cell, self.delta = nb, cell, delta

    def redo(self):
        self._shift(self.delta)

    def undo(self):
        self._shift(-self.delta)

    def _shift(self, delta):
        cells = self.nb.cells
        i = cells.index(self.cell)
        cells.insert(i + delta, cells.pop(i))
        self.nb._relayout()
        self.nb._select(self.cell)
        self.nb.modified.emit()


class ConvertCellCmd(QUndoCommand):
    """Swap *old* for a pre-built *new*-typed cell, keeping both alive."""

    def __init__(self, nb, old, new):
        super().__init__("Change cell type")
        self.nb, self.old, self.new = nb, old, new
        self.index = nb.cells.index(old)

    def redo(self):
        self.nb._swap_cell(self.old, self.new, self.index)

    def undo(self):
        self.nb._swap_cell(self.new, self.old, self.index)


class SetSourceCmd(QUndoCommand):
    """Replace a cell's source text (e.g. an AI edit), invertible."""

    def __init__(self, nb, cell, new_source, text="Edit cell"):
        super().__init__(text)
        self.nb, self.cell = nb, cell
        self.old, self.new = cell.source(), new_source

    def redo(self):
        self.cell.set_source(self.new)
        self.nb.modified.emit()

    def undo(self):
        self.cell.set_source(self.old)
        self.nb.modified.emit()
