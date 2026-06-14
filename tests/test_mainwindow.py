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


def test_new_instance_command(window):
    import os
    import sys
    args, cwd = window._new_instance_command()
    assert args[0] == sys.executable
    if not getattr(sys, "frozen", False):
        assert args[1:] == ["-m", "khervebook"]      # launches the package
        assert os.path.isfile(os.path.join(cwd, "khervebook", "__main__.py"))


def test_recent_files_menu(window, tmp_path):
    from pathlib import Path
    window._clear_recent()
    assert window._recent_files() == []
    # saving records the file
    p = tmp_path / "demo.kbook"
    window.path = str(p)
    window.save_file()
    assert str(Path(p)) in window._recent_files()
    # the submenu lists it
    window._rebuild_recent_menu()
    assert any("demo.kbook" in a.text() for a in window.recent_menu.actions())
    # opening another notebook moves it to the front
    p2 = tmp_path / "two.kbook"
    p2.write_text(window.notebook.to_json(), encoding="utf-8")
    window._open_path(str(p2))
    assert window._recent_files()[0] == str(Path(p2))
    assert str(Path(p)) in window._recent_files()       # earlier one kept
    # reopening does not duplicate
    window._open_path(str(p2))
    assert window._recent_files().count(str(Path(p2))) == 1
    # clear empties the list
    window._clear_recent()
    assert window._recent_files() == []


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
