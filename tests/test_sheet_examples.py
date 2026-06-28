"""Ported KherveSheet examples: every one loads, computes and (if it
has a chart) plots without an error.

The Examples-menu test in test_notebook.py only inspects code cells;
these examples are mostly sheet cells, so this check also scans the
grids for "#ERR" formula failures.

Copyright (C) 2026 Gwilherm Kerherve

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.
"""

import pytest

from khervebook.sheet_examples import SHEET_EXAMPLES, _xl2py


def _params():
    return [pytest.param(b, id=n) for n, _c, b in SHEET_EXAMPLES]


def test_registry_names_unique():
    names = [n for n, _c, _b in SHEET_EXAMPLES]
    assert len(names) == len(set(names))


def test_xl2py_translates_excel_formulas():
    assert _xl2py("=SUM(B2:B5)") == "=sum(B2:B5)"
    assert _xl2py("=AVERAGE(A1:A3)") == "=np.mean(A1:A3)"
    assert _xl2py("=C2/(B2^2)") == "=C2/(B2**2)"
    assert _xl2py("=B3*$B$1/4") == "=B3*B1/4"


@pytest.mark.parametrize("builder", _params())
def test_sheet_example_runs_clean(qapp, builder, monkeypatch):
    from khervebook import latexcompile
    from khervebook.examples import load_example
    from khervebook.notebook import NotebookWidget
    monkeypatch.setattr(latexcompile, "available", lambda: False)
    nb = NotebookWidget()
    load_example(nb, builder)
    nb.stop_loop()
    for cell in nb.cells:
        if cell.CELL_TYPE == "sheet":
            for name, table in zip(cell._names, cell._tables):
                for r in range(table.rowCount()):
                    for c in range(table.columnCount()):
                        item = table.item(r, c)
                        text = item.text() if item else ""
                        assert "#ERR" not in text, f"{name} {r+1},{c+1}: {text}"
        elif cell.CELL_TYPE == "code":
            text = cell.output.text()
            assert "Traceback" not in text, text
            assert "#ERR" not in text, text


def test_one_example_publishes_and_charts(qapp, monkeypatch):
    """A charted example: the sheet publishes sheet1 and the code plots it."""
    from khervebook import latexcompile
    from khervebook.examples import load_example
    from khervebook.notebook import NotebookWidget
    monkeypatch.setattr(latexcompile, "available", lambda: False)
    builder = {n: b for n, _c, b in SHEET_EXAMPLES}["Compound Interest"]
    nb = NotebookWidget()
    load_example(nb, builder)
    nb.stop_loop()
    assert "sheet1" in nb.kernel.namespace
    assert any(c.CELL_TYPE == "code" for c in nb.cells)


# -- enrichment: every sheet example also has a chart, drawing, formula ------

def test_every_sheet_example_has_drawing_and_plot():
    from khervebook.sheet_extras import NO_PLOT
    for name, _cat, build in SHEET_EXAMPLES:
        if name == "Live News Headlines":          # special live builder
            continue
        types = [c["type"] for c in build()]
        assert "svg" in types, f"{name} has no drawing"
        if name not in NO_PLOT:
            assert "code" in types, f"{name} has no chart"


def test_formula_examples_carry_a_latex_cell():
    from khervebook.sheet_extras import FORMULAS
    by_name = {n: b for n, _c, b in SHEET_EXAMPLES}
    for name in FORMULAS:
        if name in by_name:                         # all of them are sheets
            types = [c["type"] for c in by_name[name]()]
            assert "latex" in types, f"{name} lost its formula cell"


def test_generic_plot_and_drawings_resolve():
    from khervebook.sheet_extras import generic_plot, drawing_for, DRAWINGS
    assert 'set_title("Monthly Budget")' in generic_plot("Monthly Budget")
    assert drawing_for("Sine / Cosine Table", "Math") is DRAWINGS["wave"]
    assert drawing_for("anything", "Finance") is DRAWINGS["coins"]
    assert drawing_for("x", "Mystery").lstrip().startswith("<svg")  # fallback
