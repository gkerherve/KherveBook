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


def test_formula_error_shown(qapp):
    from khervebook.kernel import Kernel
    sheet = make_sheet(qapp, {"A1": "=1/0"})
    sheet.execute(Kernel())
    assert sheet.table.item(0, 0).text().startswith("#ERR")


def test_source_round_trip(qapp):
    sheet = make_sheet(qapp, {"A1": "x", "B2": "=A1"})
    doc = json.loads(sheet.source())
    assert doc["data"] == {"A1": "x", "B2": "=A1"}
    assert doc["rows"] == 4 and doc["cols"] == 3


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
