"""Lab cell: lab maths, the five record kinds, klab(), undo and export.

Copyright (C) 2026 Gwilherm Kerherve

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.
"""

import json

import pytest

from khervebook import labmath as lm


@pytest.mark.parametrize("formula, mass", [
    ("H2O", 18.015), ("NaCl", 58.44), ("Ca(OH)2", 74.092),
    ("CuSO4·5H2O", 249.68), ("C6H12O6", 180.156), ("Fe2(SO4)3", 399.858),
])
def test_molar_mass(formula, mass):
    assert lm.molar_mass(formula) == pytest.approx(mass, abs=0.02)


@pytest.mark.parametrize("bad", ["", "Xx2", "H2O)", "(H2O", "2"])
def test_molar_mass_rejects_nonsense(bad):
    assert lm.molar_mass(bad) is None


def test_numbers_and_stats():
    assert lm.number("2,5 mg") == 2.5
    assert lm.number("abc") is None
    n, mean, sd = lm.stats(["1", "2", "3", "", "x"])
    assert (n, mean) == (3, 2.0) and sd == pytest.approx(1.0)
    assert lm.stats_text(["4"]) == "4 (n=1)"


def test_reaction_compute():
    data = {"rows": [
        {"name": "benzaldehyde", "role": "reactant", "formula": "C7H6O",
         "mass": "", "volume": "1.02", "density": "1.04"},     # 10 mmol
        {"name": "acetone", "role": "reactant", "formula": "C3H6O",
         "mass": "1162"},                                        # 20 mmol
        {"name": "NaOH", "role": "catalyst", "mw": "40", "mmol": "2"},
        {"name": "dibenzalacetone", "role": "product",
         "formula": "C17H14O"},
    ], "actual": "1171.5"}
    calc = lm.reaction_compute(data)
    rows = calc["rows"]
    assert rows[0]["mmol"] == pytest.approx(10.0, rel=1e-3)
    assert calc["limiting"] == 0
    assert rows[1]["equiv"] == pytest.approx(2.0, rel=1e-3)
    assert rows[2]["equiv"] == pytest.approx(0.2, rel=1e-3)
    assert calc["theoretical_mg"] == pytest.approx(2343, rel=1e-3)
    assert calc["yield_pct"] == pytest.approx(50.0, rel=1e-2)


def test_normalise_coerces_junk():
    d = lm.normalise("measurements", {"columns": [{"name": "x"}],
                                      "rows": [["1", "extra"], "bad"]})
    assert d == {"columns": [{"name": "x", "unit": ""}],
                 "rows": [["1"], [""]]}
    s = lm.normalise("safety", {"ghs": ["GHS02", "nope"], "risk": "huge"})
    assert s["ghs"] == ["GHS02"] and s["risk"] == "low"
    for kind, _label in lm.KINDS:
        assert lm.normalise(kind, None) == lm.default_data(kind)


def _nb(qapp):
    from khervebook.notebook import NotebookWidget
    return NotebookWidget()


def test_measurements_table_and_klab(qapp):
    from khervebook.labcell import starter
    nb = _nb(qapp)
    cell = nb.add_cell("lab", starter("measurements"))
    g = cell._ed.grid
    for r, (s, v) in enumerate([("S-0001", "1.0"), ("S-0002", "2.0"),
                                ("S-0003", "3.0")]):
        g.item(r, 0).setText(s)
        g.item(r, 1).setText(v)
    assert "2 ± 1 (n=3)" in cell._ed.stats.text()
    assert "Sample" not in cell._ed.stats.text()     # IDs are not averaged
    nb.cells[0].set_source("df = klab()\nfloat(df['Value'].sum())")
    nb.cells[0].execute(nb.kernel)
    assert nb.cells[0].output.text() == "6.0"
    # its sample IDs count as usage of those samples
    nb.edit_samples(lambda r: r.add(name="a"))
    assert nb.sample_usage("S-0001") == [cell]


def test_paste_extends_rows(qapp):
    from PyQt5.QtWidgets import QApplication
    from khervebook.labcell import starter
    nb = _nb(qapp)
    cell = nb.add_cell("lab", starter("measurements"))
    g = cell._ed.grid
    g.setCurrentCell(0, 0)
    g._paste("a\t1\nb\t2\nc\t3\nd\t4\n")
    assert g.rowCount() == 4
    assert cell.data()["rows"][3] == ["d", "4"]
    assert QApplication.instance() is not None


def test_steps_are_stamped(qapp):
    from PyQt5.QtCore import Qt
    from khervebook.labcell import starter
    nb = _nb(qapp)
    cell = nb.add_cell("lab", starter("steps"))
    g = cell._ed.grid
    g.item(0, 1).setText("Weigh 2 g TiO2")
    g.item(0, 0).setCheckState(Qt.Checked)
    step = cell.data()["steps"][0]
    assert step["done"] and step["by"] and step["at"]
    g.item(0, 0).setCheckState(Qt.Unchecked)
    assert cell.data()["steps"][0]["by"] == ""


def test_reaction_cell_fills_mw_from_formula(qapp):
    from khervebook.labcell import starter
    nb = _nb(qapp)
    cell = nb.add_cell("lab", starter("reaction"))
    g = cell._ed.grid
    cols = [k for k, _ in lm.REACTION_COLS]
    g.item(0, cols.index("formula")).setText("H2O")
    assert g.item(0, cols.index("mw")).text() == "18.015"
    assert cell.data()["rows"][0]["mw"] == ""          # auto, not stored
    g.item(0, cols.index("mass")).setText("180.15")
    assert g.item(0, len(cols)).text() == "10 mmol · 1 eq"
    g.item(0, cols.index("mw")).setText("18")          # user override
    assert cell.data()["rows"][0]["mw"] == "18"


def test_lab_edits_undo_and_round_trip(qapp):
    from khervebook.labcell import starter
    nb = _nb(qapp)
    cell = nb.add_cell("lab", starter("measurements"))
    cell.set_title("Hardness")
    before = cell.source()
    cell._ed.grid.item(0, 1).setText("42")
    assert json.loads(cell.source())["data"]["rows"][0][1] == "42"
    nb.undo()
    assert cell.source() == before
    nb.redo()
    assert json.loads(cell.source())["data"]["rows"][0][1] == "42"
    nb.cells[0].set_source('float(klab("Hardness")["Value"][0])')
    nb.cells[0].execute(nb.kernel)
    assert nb.cells[0].output.text() == "42.0"

    nb2 = _nb(qapp)
    nb2.load_json(nb.to_json())
    lab = [c for c in nb2.cells if c.CELL_TYPE == "lab"][0]
    assert lab.source() == cell.source() and lab.title == "Hardness"


def test_kind_switch_and_bad_source(qapp):
    from khervebook.labcell import LabCell
    cell = LabCell("not json")
    assert cell.kind == "measurements"
    cell.set_kind("safety")
    assert cell.kind == "safety"
    cell._ed.ghs["GHS05"].setChecked(True)
    assert "GHS05 Corrosive" in cell.to_markdown()


def test_ipynb_export_shows_markdown(qapp):
    from khervebook.labcell import starter
    nb = _nb(qapp)
    nb.add_cell("lab", starter("run"))
    doc = json.loads(nb.to_ipynb())
    lab = doc["cells"][1]
    assert lab["metadata"]["khervebook"]["type"] == "lab"
    assert "Instrument Run" in "".join(lab["source"])
    nb2 = _nb(qapp)
    nb2.load_ipynb(nb.to_ipynb())
    assert nb2.cells[1].CELL_TYPE == "lab" and nb2.cells[1].kind == "run"
