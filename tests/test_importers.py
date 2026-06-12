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
    assert len(cells) == 1                  # single sheet -> no header
    assert cells[0]["type"] == "sheet"
    doc = json.loads(cells[0]["source"])
    assert doc["data"]["A1"] == "x"
    assert doc["data"]["B2"] == "=A2*2"     # formula text preserved
    assert doc["rows"] == 6                 # trimmed to used range


def test_ksheet_multi_sheet_names(tmp_path):
    from khervebook.importers import ksheet_to_cells
    path = tmp_path / "book.ksheet"
    make_ksheet(path, [("Alpha", 5, 3, {(0, 0): "1"}),
                       ("Beta", 5, 3, {(0, 0): "2"})])
    cells = ksheet_to_cells(str(path))
    types = [c["type"] for c in cells]
    assert types == ["markdown", "sheet", "markdown", "sheet"]
    assert "Alpha" in cells[0]["source"]
    assert "Beta" in cells[2]["source"]


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
