"""Importer tests: .ksheet workbooks and kherveDOC documents.

Copyright (C) 2026 Gwilherm Kerherve

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.
"""

import json
import zipfile

import pytest


def make_ksheet(path, sheets):
    """Write a minimal .ksheet (KherveSheet HDF5 layout)."""
    h5py = pytest.importorskip("h5py")
    with h5py.File(path, "w") as f:
        f.attrs["format"] = "ksheet"
        f.attrs["version"] = 1
        f.attrs["sheet_count"] = len(sheets)
        for i, (name, rows, cols, grid) in enumerate(sheets):
            sg = f.create_group(f"sheet_{i}")
            sg.attrs["name"] = name
            sg.attrs["rows"] = rows
            sg.attrs["cols"] = cols
            flat = [grid.get((r, c), "")
                    for r in range(rows) for c in range(cols)]
            sg.create_dataset("cells", data=flat,
                              dtype=h5py.string_dtype())


def test_ksheet_import(tmp_path):
    from khervebook.importers import ksheet_to_cells
    path = tmp_path / "book.ksheet"
    make_ksheet(path, [("Data", 50, 10,
                        {(0, 0): "x", (0, 1): "y",
                         (1, 0): "1", (1, 1): "=A2*2"})])
    cells = ksheet_to_cells(str(path))
    assert len(cells) == 1                  # whole workbook = one cell
    assert cells[0]["type"] == "sheet"
    doc = json.loads(cells[0]["source"])
    sheet0 = doc["sheets"][0]
    assert sheet0["name"] == "Data"
    assert sheet0["data"]["A1"] == "x"
    assert sheet0["data"]["B2"] == "=A2*2"  # formula text preserved
    assert sheet0["rows"] == 6              # trimmed to used range


def make_ksheet_with_chart(path):
    """A .ksheet with one sheet and one line chart (series x/y + style)."""
    h5py = pytest.importorskip("h5py")
    import numpy as np
    with h5py.File(path, "w") as f:
        f.attrs["format"] = "ksheet"
        f.attrs["sheet_count"] = 1
        sg = f.create_group("sheet_0")
        sg.attrs["name"] = "Data"
        sg.attrs["rows"] = 5
        sg.attrs["cols"] = 2
        sg.create_dataset("cells", data=["x", "y", "1", "2", "2", "4"]
                          + [""] * 4, dtype=h5py.string_dtype())
        chart = sg.create_group("chart_0")
        chart.attrs["title"] = "My Chart"
        chart.attrs["xlabel"] = "x"
        chart.attrs["ylabel"] = "y"
        chart.attrs["series_count"] = 1
        s0 = chart.create_group("series_0")
        s0.attrs["label"] = "line"
        s0.attrs["plot_type"] = "Line"
        s0.attrs["props"] = '{"color": "#4472c4", "linewidth": 2.0}'
        s0.create_dataset("x", data=np.array([1.0, 2.0, 3.0]))
        s0.create_dataset("y", data=np.array([1.0, 4.0, 9.0]))


def test_ksheet_chart_imports_as_plot(tmp_path, qapp):
    from khervebook.importers import ksheet_to_cells
    path = tmp_path / "chart.ksheet"
    make_ksheet_with_chart(path)
    cells = ksheet_to_cells(str(path))
    doc = json.loads(cells[0]["source"])
    assert [p["title"] for p in doc["plots"]] == ["My Chart"]
    assert doc["plots"][0]["png"]                       # rendered, non-empty
    # The sheet cell exposes the chart as a selectable plot view.
    from khervebook.sheetcell import SheetCell
    cell = SheetCell(cells[0]["source"])
    assert "My Chart" in cell.view_titles()
    assert cell._n_static == 1
    # And it survives a .kbook round-trip.
    from khervebook.notebook import NotebookWidget
    nb = NotebookWidget()
    nb.add_cell("sheet", cells[0]["source"])
    nb2 = NotebookWidget()
    nb2.load_json(nb.to_json())
    assert "My Chart" in nb2.cells[-1].view_titles()


def test_ksheet_multi_sheet_single_cell(tmp_path):
    from khervebook.importers import ksheet_to_cells
    path = tmp_path / "book.ksheet"
    make_ksheet(path, [("Alpha", 5, 3, {(0, 0): "1"}),
                       ("Beta", 5, 3, {(0, 0): "2"})])
    cells = ksheet_to_cells(str(path))
    assert len(cells) == 1                  # both sheets in ONE cell
    doc = json.loads(cells[0]["source"])
    assert [s["name"] for s in doc["sheets"]] == ["Alpha", "Beta"]


KDOC = {
    "type": "Document",
    "meta": {"title": "Demo"},
    "children": [
        {"type": "Section", "level": 1, "children": [
            {"type": "Text", "text": "Intro", "marks": []}]},
        {"type": "Paragraph", "children": [
            {"type": "Text", "text": "Einstein wrote ", "marks": []},
            {"type": "MathInline", "latex": "E = mc^2"},
            {"type": "Text", "text": "bold", "marks": ["bold"]}]},
        {"type": "MathBlock", "latex": r"\int e^{-x^2} dx"},
        {"type": "Paragraph", "children": [
            {"type": "Text", "text": "After.", "marks": []}]},
    ],
}


def test_ktex_to_latex(tmp_path):
    from khervebook.importers import ktex_to_latex, ktex_to_cells, is_ktex
    model = {
        "type": "Document",
        "meta": {"title": "My Paper", "author": "Me",
                 "packages": ["multicol", "float", "setspace"]},
        "children": [
            {"type": "Section", "level": 1, "numbered": False,
             "children": [{"type": "Text", "text": "Intro", "marks": []}]},
            {"type": "Paragraph", "children": [
                {"type": "Text", "text": "Bold ", "marks": []},
                {"type": "Text", "text": "word", "marks": ["bold"]},
                {"type": "Text", "text": " and 100% & $5.", "marks": []},
                {"type": "MathInline", "latex": "x^2"}]},
            {"type": "MathBlock", "latex": r"\int x\,dx", "numbered": True},
        ],
    }
    path = tmp_path / "doc.ktex.json"
    path.write_text(json.dumps(model), encoding="utf-8")
    assert is_ktex(str(path))
    tex = ktex_to_latex(str(path))
    # Clean minimal preamble, no KherveTeX bloat.
    assert "\\documentclass" in tex
    assert "multicol" not in tex and "Kstroke" not in tex
    assert "\\section*{Intro}" in tex            # unnumbered
    assert "\\textbf{word}" in tex
    assert "100\\% \\& \\$5" in tex              # special chars escaped
    assert "\\begin{equation}" in tex
    cells = ktex_to_cells(str(path))
    assert cells[0]["type"] == "latex"


def test_kdoc_json_import(tmp_path):
    from khervebook.importers import kdoc_to_cells
    path = tmp_path / "demo.kdoc.json"
    path.write_text(json.dumps(KDOC), encoding="utf-8")
    cells = kdoc_to_cells(str(path))
    assert [c["type"] for c in cells] == ["markdown", "latex", "markdown"]
    md = cells[0]["source"]
    assert "# Demo" in md and "## Intro" in md   # sections under title
    assert "$E = mc^2$" in md and "**bold**" in md
    assert cells[1]["source"] == r"\int e^{-x^2} dx"


def test_kdocz_import(tmp_path):
    from khervebook.importers import kdoc_to_cells
    path = tmp_path / "demo.kdocz"
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("manifest.json",
                   '{"format": "kdocz", "schema_version": 1}')
        z.writestr("document.json", json.dumps(KDOC))
    cells = kdoc_to_cells(str(path))
    assert cells[1] == {"type": "latex", "source": r"\int e^{-x^2} dx"}


def test_drop_ksheet_and_kdoc_into_notebook(qapp, tmp_path):
    pytest.importorskip("h5py")
    from khervebook.notebook import NotebookWidget
    nb = NotebookWidget()
    ks = tmp_path / "b.ksheet"
    make_ksheet(ks, [("Data", 4, 2, {(0, 0): "7"})])
    assert nb.open_file_in_cell(str(ks))
    assert nb.current.CELL_TYPE == "sheet"
    assert nb.current._raw(0, 0) == "7"

    kd = tmp_path / "d.kdoc.json"
    kd.write_text(json.dumps(KDOC), encoding="utf-8")
    assert nb.open_file_in_cell(str(kd))
    assert "latex" in [c.CELL_TYPE for c in nb.cells]
