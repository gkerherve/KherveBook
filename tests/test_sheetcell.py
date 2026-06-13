"""Sheet cell tests: formulas, kernel access, round-trip.

Copyright (C) 2026 Gwilherm Kerherve

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.
"""

import json

import pytest

from khervebook.sheetcell import col_letter, letter_col


def make_sheet(qapp, data, rows=4, cols=3):
    from khervebook.sheetcell import SheetCell
    return SheetCell(json.dumps({"rows": rows, "cols": cols, "data": data}))


def test_col_letters():
    assert col_letter(0) == "A"
    assert col_letter(25) == "Z"
    assert col_letter(26) == "AA"
    assert letter_col("AA") == 26


def test_formula_evaluation(qapp):
    from khervebook.kernel import Kernel
    sheet = make_sheet(qapp, {"A1": "3", "B1": "=A1 * 2"})
    sheet.execute(Kernel())
    assert sheet.table.item(0, 1).text() == "6"
    # The raw formula is preserved for editing and saving.
    assert sheet._raw(0, 1) == "=A1 * 2"


def test_formula_chain_and_numpy(qapp):
    from khervebook.kernel import Kernel
    sheet = make_sheet(qapp, {"A1": "2", "B1": "=A1 + 1",
                              "C1": "=np.sqrt(B1 + 1)"})
    sheet.execute(Kernel())
    assert sheet.table.item(0, 2).text() == "2"


def test_formula_sees_kernel_variables(qapp):
    from khervebook.kernel import Kernel
    k = Kernel()
    k.run("scale = 10")
    sheet = make_sheet(qapp, {"A1": "4", "B1": "=A1 * scale"})
    sheet.execute(k)
    assert sheet.table.item(0, 1).text() == "40"


def test_range_formula(qapp):
    from khervebook.kernel import Kernel
    sheet = make_sheet(qapp, {"A1": "1", "A2": "2", "A3": "3",
                              "B1": "=sum(A1:A3)",
                              "C1": "=np.mean(A1:A3)"})
    sheet.execute(Kernel())
    assert sheet.table.item(0, 1).text() == "6"
    assert sheet.table.item(0, 2).text() == "2"


def test_range_with_formula_dependency(qapp):
    from khervebook.kernel import Kernel
    sheet = make_sheet(qapp, {"A1": "2", "A2": "=A1 * 2",
                              "B1": "=sum(A1:A2)"})
    sheet.execute(Kernel())
    assert sheet.table.item(0, 1).text() == "6"


def test_grid_published_to_kernel(qapp):
    from khervebook.kernel import Kernel
    from khervebook.notebook import NotebookWidget
    import json as _json
    nb = NotebookWidget()
    nb.add_cell("sheet", _json.dumps(
        {"rows": 2, "cols": 2, "data": {"A1": "5", "B1": "=A1 + 1"}}))
    sheet = nb.cells[-1]
    sheet.execute(nb.kernel)
    assert nb.kernel.namespace["sheet1"][0][:2] == [5, 6]
    res = nb.kernel.run("sheet1[0][1] * 10")
    assert res.result_repr == "60"


def test_formula_bar_roundtrip(qapp):
    from khervebook.kernel import Kernel
    sheet = make_sheet(qapp, {"A1": "=1+1"})
    sheet.execute(Kernel())
    sheet.table.setCurrentCell(0, 0)
    assert sheet.ref_label.text() == "A1"
    assert sheet.formula_edit.text() == "=1+1"   # raw, not the value
    sheet.table.setCurrentCell(1, 1)
    sheet.formula_edit.setText("42")
    sheet._commit_formula()
    assert sheet._raw(1, 1) == "42"


def test_auto_recalc_on_edit(qapp):
    """Editing a cell recomputes formulas without pressing run."""
    import json as _json
    from PyQt5.QtWidgets import QApplication
    from khervebook.notebook import NotebookWidget
    nb = NotebookWidget()
    nb.add_cell("sheet", _json.dumps(
        {"rows": 3, "cols": 2, "data": {"A1": "3", "B1": "=A1 * 10"}}))
    sheet = nb.cells[-1]
    sheet._set_item(0, 0, "5", "5")        # itemChanged fires
    assert sheet._recalc_timer.isActive()  # edit scheduled a recalc
    sheet.recalculate()                    # what the timer will run
    assert sheet.table.item(0, 1).text() == "50"


def test_formula_plot_becomes_view(qapp):
    from khervebook.kernel import Kernel
    sheet = make_sheet(qapp, {"A1": "=plt.plot([1, 2, 3]) and plt.gcf()"})
    sheet.execute(Kernel())
    assert sheet.table.item(0, 0).text() == "[plot]"
    assert len(sheet._plot_labels) == 1
    assert not sheet._plot_labels[0].pixmap().isNull()
    # The raw formula is still there for editing.
    assert sheet._raw(0, 0).startswith("=plt.plot")


def test_formula_error_shown(qapp):
    from khervebook.kernel import Kernel
    sheet = make_sheet(qapp, {"A1": "=1/0"})
    sheet.execute(Kernel())
    assert sheet.table.item(0, 0).text().startswith("#ERR")


def test_source_round_trip(qapp):
    sheet = make_sheet(qapp, {"A1": "x", "B2": "=A1"})
    doc = json.loads(sheet.source())
    assert len(doc["sheets"]) == 1
    sheet0 = doc["sheets"][0]
    assert sheet0["data"] == {"A1": "x", "B2": "=A1"}
    assert sheet0["rows"] == 4 and sheet0["cols"] == 3


def test_multi_sheet_views_and_round_trip(qapp):
    import json as _json
    from khervebook.sheetcell import SheetCell
    src = _json.dumps({"sheets": [
        {"name": "Alpha", "rows": 3, "cols": 2, "data": {"A1": "1"}},
        {"name": "Beta", "rows": 3, "cols": 2, "data": {"A1": "2"}}],
        "active": "Beta"})
    cell = SheetCell(src)
    assert cell.view_titles() == ["Alpha", "Beta"]
    assert cell.current_view_index() == 1          # active = Beta
    assert cell._raw(0, 0) == "2"                   # Beta is the active grid
    cell.set_view_index(0)
    assert cell._raw(0, 0) == "1"                   # now Alpha
    # Two sheets publish as two grids.
    from khervebook.notebook import NotebookWidget
    nb = NotebookWidget()
    nb.add_cell("sheet", src)
    nb.cells[-1].execute(nb.kernel)
    assert nb.kernel.namespace["sheet1"][0][0] == 1
    assert nb.kernel.namespace["sheet2"][0][0] == 2
    # Round-trips both sheets.
    doc = _json.loads(cell.source())
    assert [s["name"] for s in doc["sheets"]] == ["Alpha", "Beta"]


def test_plot_becomes_a_view(qapp):
    from khervebook.kernel import Kernel
    sheet = make_sheet(qapp, {"A1": "=plt.plot([1, 2, 3]) and plt.gcf()"})
    sheet.execute(Kernel())
    titles = sheet.view_titles()
    assert "Plot 1" in titles                       # plot is a selectable view
    sheet.set_view_index(titles.index("Plot 1"))
    assert sheet.table is None                       # plot view, no grid


def test_convert_text_to_sheet(qapp):
    """Converting a text cell imports lines/commas as a grid."""
    from khervebook.sheetcell import SheetCell
    sheet = SheetCell("a,b\n1,2")
    assert sheet._raw(0, 0) == "a"
    assert sheet._raw(1, 1) == "2"


def test_sheet_in_notebook_round_trip(qapp):
    from khervebook.notebook import NotebookWidget
    nb = NotebookWidget()
    nb.add_cell("sheet", json.dumps(
        {"rows": 2, "cols": 2, "data": {"A1": "5"}}))
    nb2 = NotebookWidget()
    nb2.load_json(nb.to_json())
    assert nb2.cells[-1].CELL_TYPE == "sheet"
    assert nb2.cells[-1]._raw(0, 0) == "5"
