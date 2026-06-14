"""Code-editor features: line numbers, find-in-cell, thesaurus.

Copyright (C) 2026 Gwilherm Kerherve

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.
"""


def test_code_cell_has_line_numbers(qapp):
    from khervebook.cells import make_cell
    code = make_cell("code", "a = 1\nb = 2\nc = 3")
    assert code.editor._lna is not None
    assert code.editor._lna_width() > 0


def test_prose_cells_have_no_line_numbers(qapp):
    from khervebook.cells import make_cell
    assert make_cell("markdown", "# hi").editor._lna is None
    assert make_cell("latex", "x^2").editor._lna is None


def test_find_bar_selects_and_marks_misses(qapp):
    from khervebook.cells import make_cell
    cell = make_cell("code", "alpha\nbeta\nalpha")
    cell.show_find()
    assert cell._find_bar.isVisibleTo(cell)
    cell._find_bar.edit.setText("alpha")
    cell._find_bar.find(True)
    assert cell.editor.textCursor().selectedText() == "alpha"
    cell._find_bar.edit.setText("zzz")          # no match -> box flags red
    cell._find_bar.find(True)
    assert "ffd6d6" in cell._find_bar.edit.styleSheet()


def test_thesaurus_rejects_non_words_offline():
    from khervebook import thesaurus
    assert thesaurus.synonyms("") == []
    assert thesaurus.synonyms("abc123") == []   # non-alpha: never hits network
    assert thesaurus.synonyms("  ") == []
