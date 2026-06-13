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


def test_continuous_run_loop(qapp):
    from khervebook.notebook import NotebookWidget
    nb = NotebookWidget()
    cell = nb.cells[0]
    cell.set_source("counter = globals().get('counter', 0) + 1\ncounter")
    nb.start_loop(cell, interval_ms=10)
    assert nb.looping
    assert cell.stop_btn.isVisibleTo(cell)      # stop appears while looping
    assert nb.kernel.namespace["counter"] == 1  # ran once on start
    nb._loop_tick()
    assert nb.kernel.namespace["counter"] == 2  # state persists per frame
    nb.stop_loop()
    assert not nb.looping
    assert not cell.stop_btn.isVisibleTo(cell)
    assert not nb._loop_timer.isActive()


def test_loop_stops_when_cell_removed(qapp):
    from khervebook.notebook import NotebookWidget
    nb = NotebookWidget()
    cell = nb.cells[0]
    nb.start_loop(cell, interval_ms=10)
    nb._set_current(cell)
    nb.cut_current()
    nb._loop_tick()
    assert not nb.looping


def test_cells_in_a_row(qapp):
    """Two cells can share a row; structure round-trips."""
    from khervebook.notebook import NotebookWidget
    nb = NotebookWidget()
    nb.cells[0].set_source("x = 1")
    latex = nb.add_cell_below("latex", "E = mc^2")
    md = nb.add_cell_below("markdown", "# notes")
    # Put the latex cell beside the code cell (one row of two).
    nb.set_cell_column(latex, True)
    assert latex.beside_previous and not md.beside_previous
    # The code+latex cells now live in one row widget, markdown in another.
    assert len(nb._rows) == 2
    assert nb._rows[0].layout().count() == 2     # code | latex
    assert nb._rows[1].layout().count() == 1     # markdown
    # First cell can never join a previous row.
    nb.set_cell_column(nb.cells[0], True)
    assert not nb.cells[0].beside_previous
    # Round-trips.
    nb2 = NotebookWidget()
    nb2.load_json(nb.to_json())
    assert nb2.cells[1].beside_previous and len(nb2._rows) == 2
    # Splitting back to its own row.
    nb2.set_cell_column(nb2.cells[1], False)
    assert len(nb2._rows) == 3


def test_cell_title_and_round_trip(qapp):
    from khervebook.notebook import NotebookWidget
    nb = NotebookWidget()
    cell = nb.cells[0]
    cell.set_source("x = 1")
    cell.set_title("Setup")
    assert cell.title_label.isVisibleTo(cell)
    assert cell.title_label.text() == "Setup"
    # Collapsed cell with a title shows the title, not the source preview.
    cell.set_collapsed(True)
    assert not cell.summary.isVisibleTo(cell)
    assert cell.title_label.isVisibleTo(cell)
    nb2 = NotebookWidget()
    nb2.load_json(nb.to_json())
    assert nb2.cells[0].title == "Setup"
    # Clearing the title removes the label.
    nb2.cells[0].set_title("")
    assert not nb2.cells[0].title_label.isVisibleTo(nb2.cells[0])


def test_collapse_cell_and_round_trip(qapp):
    from khervebook.notebook import NotebookWidget
    nb = NotebookWidget()
    cell = nb.cells[0]
    cell.set_source("line1 = 1\nline2 = 2\nline3 = 3")
    cell.set_collapsed(True)
    assert not cell._body.isVisibleTo(cell)
    assert cell.summary.isVisibleTo(cell)
    assert "line1 = 1" in cell.summary.text()
    assert "3 lines" in cell.summary.text()
    # Collapsed state survives save/load.
    nb2 = NotebookWidget()
    nb2.load_json(nb.to_json())
    assert nb2.cells[0].collapsed
    nb2.cells[0].set_collapsed(False)
    assert nb2.cells[0]._body.isVisibleTo(nb2.cells[0])


def test_manual_cell_height_caps_and_round_trips(qapp):
    from khervebook.notebook import NotebookWidget
    nb = NotebookWidget()
    nb.show()
    cell = nb.cells[0]
    cell.set_source("\n".join(f"row {i}" for i in range(40)))
    cell.set_content_height(200)
    assert cell.content_height() == 200
    assert cell._body_scroll.maximumHeight() <= 200   # never above the cap
    nb2 = NotebookWidget()
    nb2.load_json(nb.to_json())
    assert nb2.cells[0].content_height() == 200
    nb2.cells[0].set_content_height(None)        # double-click reset
    assert nb2.cells[0].content_height() is None


def test_long_editor_caps_height(qapp):
    from khervebook.cells import _GrowingEdit
    short = _GrowingEdit("x = 1")
    tall = _GrowingEdit("\n".join(f"a{i} = {i}" for i in range(80)))
    assert tall.height() < short.height() * 30   # capped, not 80 rows
    from PyQt5.QtCore import Qt
    assert tall.verticalScrollBarPolicy() == Qt.ScrollBarAsNeeded


def test_drop_files_into_cells(qapp, tmp_path):
    from khervebook.notebook import NotebookWidget
    nb = NotebookWidget()

    py = tmp_path / "script.py"
    py.write_text("x = 1\n", encoding="utf-8")
    assert nb.open_file_in_cell(str(py))
    assert nb.current.CELL_TYPE == "code"
    assert nb.current.source() == "x = 1\n"

    csv = tmp_path / "data.csv"
    csv.write_text("a,b\n1,2\n", encoding="utf-8")
    target = nb.current
    assert nb.open_file_in_cell(str(csv), target)   # converts in place
    assert nb.current.CELL_TYPE == "sheet"
    assert nb.current._raw(0, 0) == "a"
    assert nb.current._raw(1, 1) == "2"

    md = tmp_path / "notes.md"
    md.write_text("# Title", encoding="utf-8")
    assert nb.open_file_in_cell(str(md))
    assert nb.current.CELL_TYPE == "markdown"
    assert nb.current.view.isVisibleTo(nb)          # rendered on drop

    assert not nb.open_file_in_cell(str(tmp_path / "missing.py"))
    exe = tmp_path / "app.exe"
    exe.write_bytes(b"MZ")
    assert not nb.open_file_in_cell(str(exe))       # unrecognised


def test_drop_kbook_emits_open_request(qapp, tmp_path):
    from khervebook.notebook import NotebookWidget
    nb = NotebookWidget()
    kb = tmp_path / "doc.kbook"
    kb.write_text('{"cells": []}', encoding="utf-8")
    got = []
    nb.open_kbook_requested.connect(got.append)
    assert nb.open_file_in_cell(str(kb))
    assert got == [str(kb)]


def _example_params():
    from khervebook.examples import EXAMPLES
    return [pytest.param(b, id=n) for n, _c, b in EXAMPLES]


import pytest  # noqa: E402


@pytest.mark.parametrize("builder", _example_params())
def test_examples_run_clean(qapp, builder):
    """Every Examples-menu notebook loads and runs without errors."""
    from khervebook.examples import load_example
    from khervebook.notebook import NotebookWidget
    nb = NotebookWidget()
    load_example(nb, builder)
    nb.stop_loop()
    for cell in nb.cells:
        if cell.CELL_TYPE == "code":
            text = cell.output.text()
            assert "Traceback" not in text, text
            assert "#ERR" not in text, text


def test_bouncing_balls_physics(qapp):
    """Elastic collisions: kinetic energy conserved, balls stay boxed."""
    from khervebook.kernel import Kernel
    from khervebook.welcome import WELCOME_CELLS
    source = next(c["source"] for c in WELCOME_CELLS
                  if c["source"].startswith("# Bouncing balls"))
    physics = source.split("fig, ax")[0]      # skip plotting per frame
    k = Kernel()
    k.run(physics)
    ke0 = k.run("float((balls_vel ** 2).sum())").result_repr
    for _ in range(400):
        k.run(physics)
    ke1 = k.run("float((balls_vel ** 2).sum())").result_repr
    assert abs(float(ke0) - float(ke1)) < 1e-9   # elastic = no energy loss
    res = k.run("bool((balls_pos > -0.02).all() and (balls_pos < 1.02).all())")
    assert res.result_repr == "True"


def test_restart_kernel_resets_gutters(qapp):
    from khervebook.notebook import NotebookWidget
    nb = NotebookWidget()
    nb.cells[0].set_source("1 + 1")
    nb.cells[0].execute(nb.kernel)
    assert nb.cells[0].gutter.text() == "In [1]:"
    nb.restart_kernel()
    assert nb.cells[0].gutter.text() == "In [ ]:"
    assert nb.kernel.exec_count == 0
