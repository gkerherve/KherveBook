"""Undo/redo for cell structure: add, delete, move, convert, cut, paste.

The key guarantee is that undoing a delete or a type change restores
the very same widget, so a code cell's output survives.

Copyright (C) 2026 Gwilherm Kerherve

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.
"""


def _nb(qapp):
    from khervebook.notebook import NotebookWidget
    return NotebookWidget()


def test_add_cell_undo_redo(qapp):
    nb = _nb(qapp)
    n = len(nb.cells)
    cell = nb.add_cell_below("markdown", "# hi")
    assert cell in nb.cells and len(nb.cells) == n + 1
    nb.undo()
    assert cell not in nb.cells and len(nb.cells) == n
    nb.redo()
    assert cell in nb.cells and len(nb.cells) == n + 1


def test_delete_undo_restores_same_cell_with_output(qapp):
    nb = _nb(qapp)
    cell = nb.add_cell_below("code", "print('hello')")
    cell.execute(nb.kernel)
    assert "hello" in cell.output.text()
    nb.remove_current()
    assert cell not in nb.cells
    nb.undo()
    assert cell in nb.cells                      # the very same widget
    assert "hello" in cell.output.text()         # output preserved
    nb.redo()
    assert cell not in nb.cells


def test_move_cell_undo_redo(qapp):
    nb = _nb(qapp)
    a = nb.cells[0]
    nb.add_cell_below("code", "b")               # order: a, b
    nb._select(a)
    nb.move_current(1)                           # -> b, a
    assert nb.cells.index(a) == 1
    nb.undo()
    assert nb.cells.index(a) == 0
    nb.redo()
    assert nb.cells.index(a) == 1


def test_convert_cell_undo_keeps_source(qapp):
    nb = _nb(qapp)
    cell = nb.add_cell_below("code", "x = 1")
    nb.convert_current("markdown")
    assert nb.current.CELL_TYPE == "markdown"
    assert nb.current.source() == "x = 1"
    nb.undo()
    assert nb.current.CELL_TYPE == "code"
    assert nb.current is cell                     # original code cell back
    assert nb.current.source() == "x = 1"
    nb.redo()
    assert nb.current.CELL_TYPE == "markdown"


def test_paste_cell_undo(qapp):
    nb = _nb(qapp)
    nb.add_cell_below("markdown", "# title")
    nb.copy_current()
    n = len(nb.cells)
    nb.paste_cell()
    assert len(nb.cells) == n + 1
    nb.undo()
    assert len(nb.cells) == n


def test_cut_single_cell_undo(qapp):
    nb = _nb(qapp)                                # starts with one code cell
    nb._select(nb.cells[0])
    nb.cells[0].set_source("keep me")
    nb.cut_current()                             # macro: fresh cell + remove
    assert len(nb.cells) == 1 and nb.cells[0].source() == ""
    nb.undo()                                    # the whole macro, one step
    assert nb.cells[0].source() == "keep me"


def test_undo_stack_cleared_on_load(qapp):
    nb = _nb(qapp)
    nb.add_cell_below("code", "a")
    assert nb.undo_stack.canUndo()
    nb.load_json('{"cells": [{"type": "code", "source": "x"}]}')
    assert not nb.undo_stack.canUndo()


def test_cannot_undo_below_one_cell(qapp):
    nb = _nb(qapp)                               # one cell; delete is a no-op
    nb.remove_current()
    assert len(nb.cells) == 1
    assert not nb.undo_stack.canUndo()           # nothing was pushed
