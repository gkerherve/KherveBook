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


def test_excel_style_functions(qapp):
    from khervebook.kernel import Kernel
    sheet = make_sheet(qapp, {
        "A1": "10", "A2": "20", "A3": "30",
        "B1": "=SUM(A1:A3)", "B2": "=AVERAGE(A1:A3)",
        "B3": '=IF(A1>15,"big","small")',
        "C1": "=ROUND(AVERAGE(A1:A3),0)",
        "C2": '=CONCAT("n=",COUNT(A1:A3))'})
    sheet.execute(Kernel())
    assert sheet.table.item(0, 1).text() == "60"        # SUM
    assert sheet.table.item(1, 1).text() == "20"        # AVERAGE
    assert sheet.table.item(2, 1).text() == "small"     # IF (10 > 15 false)
    assert sheet.table.item(0, 2).text() == "20"        # ROUND(AVERAGE,0)
    assert sheet.table.item(1, 2).text() == "n=3"       # CONCAT + COUNT


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


def test_grid_resize_and_round_trip(qapp):
    """The resize grip resizes the grid; the height round-trips."""
    import json as _json
    from khervebook.notebook import NotebookWidget
    from khervebook.sheetcell import COL_W, ROW_H
    nb = NotebookWidget()
    nb.add_cell("sheet", _json.dumps(
        {"sheets": [{"name": "S", "rows": 30, "cols": 2, "data": {}}],
         "active": "S"}))
    sheet = nb.cells[-1]
    sheet.execute(nb.kernel)
    # Compact defaults.
    assert sheet.table.columnWidth(0) == COL_W
    assert sheet.table.rowHeight(0) == ROW_H
    # Resizing sets the grid height directly.
    sheet.set_content_height(120)
    assert sheet.table.height() == 120
    assert sheet.content_height() == 120
    # Round-trips through .kbook.
    nb2 = NotebookWidget()
    nb2.load_json(nb.to_json())
    s2 = nb2.cells[-1]
    s2.execute(nb2.kernel)
    assert s2.content_height() == 120
    assert s2.table.height() == 120
    # Double-click reset -> auto-fit.
    s2.set_content_height(None)
    assert s2.content_height() is None


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


# -- plot from selection (right-click) ---------------------------------

def _sheet_in_nb(qapp, data, rows=5, cols=3):
    from khervebook.notebook import NotebookWidget
    nb = NotebookWidget()
    nb.add_cell("sheet", json.dumps({"rows": rows, "cols": cols,
                                     "data": data}))
    sheet = nb.cells[-1]
    sheet.execute(nb.kernel)
    return nb, sheet


def test_plot_selection_creates_static_plot(qapp):
    nb, sheet = _sheet_in_nb(qapp, {"A1": "1", "A2": "2", "A3": "3",
                                    "B1": "2", "B2": "4", "B3": "6"})
    sheet.plot_selection("line")                 # no selection -> whole grid
    assert sheet._n_static == 1
    assert "Chart 1" in sheet.view_titles()
    assert not sheet._plot_labels[0].pixmap().isNull()
    # The created chart persists through a .kbook round-trip.
    from khervebook.notebook import NotebookWidget
    nb2 = NotebookWidget()
    nb2.load_json(nb.to_json())
    assert "Chart 1" in nb2.cells[-1].view_titles()


def test_plot_selection_uses_selected_range(qapp):
    from PyQt5.QtWidgets import QTableWidgetSelectionRange
    nb, sheet = _sheet_in_nb(qapp, {"A1": "x", "B1": "y",
                                    "A2": "1", "B2": "10",
                                    "A3": "2", "B3": "20"})
    sheet.table.setRangeSelected(
        QTableWidgetSelectionRange(0, 0, 2, 1), True)
    assert sheet.has_selection()
    sheet.plot_selection("bar")
    assert sheet._n_static == 1
    assert "Chart 1" in sheet.view_titles()


def test_formula_and_created_plots_coexist(qapp):
    nb, sheet = _sheet_in_nb(qapp, {
        "A1": "1", "A2": "2", "A3": "3",
        "C1": "=plt.plot([1, 2, 3]) and plt.gcf()"})
    assert "Plot 1" in sheet.view_titles()       # formula plot
    sheet.plot_selection("line")                 # add a static chart
    titles = sheet.view_titles()
    assert "Chart 1" in titles and "Plot 1" in titles
    # Re-running keeps the static chart and refreshes the formula plot.
    sheet.execute(nb.kernel)
    titles = sheet.view_titles()
    assert "Chart 1" in titles and "Plot 1" in titles


# -- ks() writes back into a sheet (Python -> sheet) -------------------

def test_ks_writes_value_into_sheet(qapp):
    nb, sheet = _sheet_in_nb(qapp, {"A1": "radius"})
    res = nb.kernel.run('ks("A2", 99)')
    assert res.ok
    assert sheet.table.item(1, 0).text() == "99"       # live grid updated
    assert nb.kernel.namespace["sheet1"][1][0] == 99    # snapshot updated
    # A written value reads straight back.
    assert nb.kernel.run('ks("A2")').result_repr == "99"


def test_ks_set_writes_a_column(qapp):
    nb, sheet = _sheet_in_nb(qapp, {"A1": "x"})
    res = nb.kernel.run('ks_set("A2:A4", [10, 20, 30])')
    assert res.ok
    assert sheet.table.item(1, 0).text() == "10"
    assert sheet.table.item(2, 0).text() == "20"
    assert sheet.table.item(3, 0).text() == "30"


def test_ks_writes_string_and_reports_bad_ref(qapp):
    nb, sheet = _sheet_in_nb(qapp, {"A1": "1"})
    nb.kernel.run('ks("B1", "hello")')
    assert sheet.table.item(0, 1).text() == "hello"
    # Writing before any sheet has published errors cleanly.
    from khervebook.kernel import Kernel
    k = Kernel()
    res = k.run('ks("A1", 5)')
    assert not res.ok and "run the sheet cell first" in res.error
