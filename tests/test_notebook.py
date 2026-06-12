"""Notebook and cell widget tests (offscreen Qt).

Copyright (C) 2026 Gwilherm Kerherve

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.
"""

import json


def test_code_cell_executes(qapp):
    from khervebook.notebook import NotebookWidget
    nb = NotebookWidget()
    cell = nb.cells[0]
    cell.set_source("x = 1  # comment\n'text'\nx + 41")
    cell.execute(nb.kernel)
    assert cell.output.text() == "42"
    assert cell.gutter.text() == "In [1]:"


def test_kbook_round_trip(qapp):
    from khervebook.notebook import NotebookWidget
    nb = NotebookWidget()
    nb.cells[0].set_source("print('hi')")
    nb.add_cell("markdown", "# Title")
    nb.add_cell("latex", r"E = mc^2")

    doc = json.loads(nb.to_json())
    assert doc["format"] == "kbook"
    assert [c["type"] for c in doc["cells"]] == ["code", "markdown", "latex"]

    nb2 = NotebookWidget()
    nb2.load_json(nb.to_json())
    assert [c.CELL_TYPE for c in nb2.cells] == ["code", "markdown", "latex"]
    assert nb2.cells[1].source() == "# Title"


def test_restart_kernel_resets_gutters(qapp):
    from khervebook.notebook import NotebookWidget
    nb = NotebookWidget()
    nb.cells[0].set_source("1 + 1")
    nb.cells[0].execute(nb.kernel)
    assert nb.cells[0].gutter.text() == "In [1]:"
    nb.restart_kernel()
    assert nb.cells[0].gutter.text() == "In [ ]:"
    assert nb.kernel.exec_count == 0
