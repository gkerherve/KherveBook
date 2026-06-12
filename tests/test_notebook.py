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
