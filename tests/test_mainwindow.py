"""MainWindow, toolbars and welcome-notebook tests (offscreen Qt).

Copyright (C) 2026 Gwilherm Kerherve

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.
"""

import pytest


@pytest.fixture()
def window(qapp):
    from khervebook.mainwindow import MainWindow
    win = MainWindow()
    yield win
    win.notebook.kernel.reset()


def test_welcome_notebook_loaded_and_run(window):
    types = [c.CELL_TYPE for c in window.notebook.cells]
    assert "markdown" in types and "latex" in types
    code = [c for c in window.notebook.cells if c.CELL_TYPE == "code"]
    # The plot example ran and produced a figure.
    assert any(c._figure_labels for c in code)
    assert window.dirty is False


def test_cell_type_conversion(window):
    nb = window.notebook
    cell = nb.add_cell_below("code", "# hello")
    nb.convert_current("markdown")
    assert nb.current.CELL_TYPE == "markdown"
    assert nb.current.source() == "# hello"


def test_cut_copy_paste_cell(window):
    nb = window.notebook
    cell = nb.add_cell_below("markdown", "copy me")
    nb.copy_current()
    nb.paste_cell()
    assert nb.current.CELL_TYPE == "markdown"
    assert nb.current.source() == "copy me"
    n = len(nb.cells)
    nb.cut_current()
    assert len(nb.cells) == n - 1


def test_cell_toolbar_follows_cell_type(window):
    nb = window.notebook
    nb.add_cell_below("markdown")
    texts = [a.text() for a in window.cell_toolbar.actions()]
    assert "Bold" in texts
    nb.add_cell_below("latex")
    texts = [a.text() for a in window.cell_toolbar.actions()]
    assert "√" in texts
    nb.add_cell_below("code")
    texts = [a.text() for a in window.cell_toolbar.actions()]
    assert "Comment" in texts


def test_markdown_wrap_bold(window):
    from PyQt5.QtGui import QTextCursor
    nb = window.notebook
    cell = nb.add_cell_below("markdown", "hello")
    cur = cell.editor.textCursor()
    cur.select(QTextCursor.Document)
    cell.editor.setTextCursor(cur)
    window.cell_toolbar._wrap("**", "**")
    assert cell.source() == "**hello**"


def test_code_comment_toggle(window):
    nb = window.notebook
    cell = nb.add_cell_below("code", "a = 1")
    window.cell_toolbar._toggle_comment()
    assert cell.source() == "# a = 1"
    window.cell_toolbar._toggle_comment()
    assert cell.source() == "a = 1"


def test_latex_insert_places_cursor(window):
    nb = window.notebook
    cell = nb.add_cell_below("latex", "")
    window.cell_toolbar._insert(r"\frac{|}{}")
    assert cell.source() == r"\frac{}{}"
    cell.editor.textCursor().insertText("a")
    assert cell.source() == r"\frac{a}{}"
