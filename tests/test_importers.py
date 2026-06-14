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


def test_ksheet_py_cell_becomes_code(tmp_path):
    from khervebook.importers import ksheet_to_cells
    path = tmp_path / "py.ksheet"
    make_ksheet(path, [("Data", 5, 2, {
        (0, 0): "radius", (0, 1): "3",
        (1, 0): "=PY\nimport numpy as np\nnp.pi * ks(\"B1\")**2"})])
    cells = ksheet_to_cells(str(path))
    assert [c["type"] for c in cells] == ["sheet", "code"]
    code = cells[1]["source"]
    body = code.split("\n", 1)[1]            # drop the "# … cell A2" header
    assert not body.lstrip().startswith("=PY")   # marker stripped from code
    assert "import numpy" in body
    assert 'ks("B1")' in code                # ks() call preserved
    assert code.startswith("# KherveSheet =PY cell A2")
    # The =PY cell is pulled out of the grid.
    doc = json.loads(cells[0]["source"])
    assert "A2" not in doc["sheets"][0]["data"]
    assert doc["sheets"][0]["data"]["B1"] == "3"


def test_ksheet_py_cell_reads_its_own_sheet(tmp_path):
    """A =PY cell on the 2nd sheet must read that sheet, not sheet1."""
    from khervebook.importers import ksheet_to_cells
    path = tmp_path / "multi.ksheet"
    make_ksheet(path, [
        ("Notes", 4, 3, {(0, 0): "intro"}),
        ("Data", 5, 3, {(0, 0): "x", (1, 0): "5", (2, 0): "6",
                        (0, 2): "=PY\nimport numpy as np\n"
                                "np.sum(ks('A2:A3'))"}),
    ])
    code = next(c["source"] for c in ksheet_to_cells(str(path))
                if c["type"] == "code")
    assert "ks('Sheet2!A2:A3')" in code      # rewritten to the Data sheet
    assert "ks('A2:A3')" not in code


def test_ksheet_single_sheet_py_not_rewritten(tmp_path):
    from khervebook.importers import ksheet_to_cells
    path = tmp_path / "single.ksheet"
    make_ksheet(path, [
        ("Data", 5, 3, {(0, 0): "x", (1, 0): "5", (2, 0): "6",
                        (0, 2): "=PY\nks('A2:A3')"}),
    ])
    code = next(c["source"] for c in ksheet_to_cells(str(path))
                if c["type"] == "code")
    assert "ks('A2:A3')" in code             # one sheet -> sheet1, left bare
    assert "Sheet1!" not in code


def test_ksheet_py_reads_real_data_after_import(qapp, tmp_path):
    """End to end: the rewritten =PY cell sees the numbers, not zeros."""
    from khervebook.importers import ksheet_to_cells
    from khervebook.notebook import NotebookWidget
    path = tmp_path / "xps.ksheet"
    make_ksheet(path, [
        ("Notes", 4, 3, {(0, 0): "intro"}),
        ("Data", 5, 2, {(0, 0): "BE", (1, 0): "530.1", (2, 0): "530.2",
                        (1, 1): "=PY\nlist(ks('A2:A3'))"}),
    ])
    nb = NotebookWidget()
    for item in ksheet_to_cells(str(path)):
        cell = nb.add_cell_below(item["type"], item["source"])
        if item["type"] == "sheet":
            cell.execute(nb.kernel)
    code = [c for c in nb.cells
            if c.CELL_TYPE == "code" and "ks(" in c.source()][0]
    code.execute(nb.kernel)
    assert "530.1" in code.output.text() and "0.0, 0.0" not in code.output.text()


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


# -- images and PDFs ----------------------------------------------------

def make_png(path, w=8, h=6, color="#ff0000"):
    from PyQt5.QtGui import QColor, QImage
    img = QImage(w, h, QImage.Format_RGB32)
    img.fill(QColor(color))
    img.save(str(path), "PNG")


def test_image_to_svg_embeds_bytes_and_size(qapp, tmp_path):
    from khervebook.importers import image_to_svg
    png = tmp_path / "p.png"
    make_png(png, 8, 6)
    svg = image_to_svg(png.read_bytes(), "image/png")
    assert svg.startswith("<svg") and svg.endswith("</svg>")
    assert 'data:image/png;base64,' in svg
    assert 'width="8"' in svg and 'height="6"' in svg   # read from QImage


def test_image_to_cells_is_one_svg_cell(qapp, tmp_path):
    from khervebook.importers import image_to_cells
    png = tmp_path / "p.png"
    make_png(png)
    cells = image_to_cells(str(png))
    assert len(cells) == 1 and cells[0]["type"] == "svg"
    assert "base64" in cells[0]["source"]


def test_drop_image_makes_rendered_svg_cell(qapp, tmp_path):
    from khervebook.notebook import NotebookWidget
    nb = NotebookWidget()
    png = tmp_path / "pic.png"
    make_png(png)
    assert nb.open_file_in_cell(str(png))
    assert nb.current.CELL_TYPE == "svg"
    assert nb.current.view.isVisibleTo(nb)              # rendered on drop
    # Survives a .kbook round-trip with the image still embedded.
    nb2 = NotebookWidget()
    nb2.load_json(nb.to_json())
    assert "base64" in nb2.cells[-1].source()


def make_pdf(path, pages=2):
    fitz = pytest.importorskip("fitz")
    doc = fitz.open()
    for _ in range(pages):
        doc.new_page(width=200, height=300)
    doc.save(str(path))
    doc.close()


def test_pdf_to_cells_one_per_page(qapp, tmp_path):
    pytest.importorskip("fitz")
    from khervebook.importers import pdf_to_cells
    pdf = tmp_path / "doc.pdf"
    make_pdf(pdf, pages=2)
    cells = pdf_to_cells(str(pdf))
    assert len(cells) == 2
    assert all(c["type"] == "svg" for c in cells)
    assert all("base64" in c["source"] for c in cells)


def test_drop_pdf_makes_svg_cells(qapp, tmp_path):
    pytest.importorskip("fitz")
    from khervebook.notebook import NotebookWidget
    nb = NotebookWidget()
    pdf = tmp_path / "doc.pdf"
    make_pdf(pdf, pages=2)
    assert nb.open_file_in_cell(str(pdf))
    svg_cells = [c for c in nb.cells if c.CELL_TYPE == "svg"]
    assert len(svg_cells) == 2
    assert svg_cells[-1].view.isVisibleTo(nb)           # rendered on drop


# -- Excel .xlsx ------------------------------------------------------

def make_xlsx(path):
    openpyxl = pytest.importorskip("openpyxl")
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Data"
    ws["A1"], ws["B1"] = "x", "y"
    ws["A2"], ws["B2"] = 1, 10
    ws["A3"], ws["B3"] = 2, 20
    ws["A4"], ws["B4"] = "Total", "=SUM(B2:B3)"
    ws2 = wb.create_sheet("Notes")
    ws2["A1"] = "hello"
    wb.save(str(path))


def test_xlsx_to_cells_multi_sheet(qapp, tmp_path):
    from khervebook.importers import xlsx_to_cells
    path = tmp_path / "book.xlsx"
    make_xlsx(path)
    cells = xlsx_to_cells(str(path))
    assert len(cells) == 1 and cells[0]["type"] == "sheet"
    doc = json.loads(cells[0]["source"])
    assert [s["name"] for s in doc["sheets"]] == ["Data", "Notes"]
    data = doc["sheets"][0]["data"]
    assert data["A1"] == "x" and data["B2"] == "10"
    # No Excel-cached value -> the SUM formula is translated to Python.
    assert data["B4"] == "=sum(B2:B3)"
    assert doc["sheets"][1]["data"]["A1"] == "hello"


def test_xlsx_formula_recomputes_in_sheet(qapp, tmp_path):
    from khervebook.kernel import Kernel
    from khervebook.importers import xlsx_to_cells
    from khervebook.sheetcell import SheetCell
    path = tmp_path / "sums.xlsx"
    make_xlsx(path)
    cells = xlsx_to_cells(str(path))
    sheet = SheetCell(cells[0]["source"])
    sheet.execute(Kernel())
    assert sheet.table.item(3, 1).text() == "30"        # B4 = sum(B2:B3)


def test_drop_xlsx_makes_computed_sheet_cell(qapp, tmp_path):
    pytest.importorskip("openpyxl")
    from khervebook.notebook import NotebookWidget
    nb = NotebookWidget()
    path = tmp_path / "drop.xlsx"
    make_xlsx(path)
    assert nb.open_file_in_cell(str(path))
    assert nb.current.CELL_TYPE == "sheet"
    assert nb.current._raw(0, 0) == "x"
    # executed on import, so the formula already shows its value
    assert nb.current.table.item(3, 1).text() == "30"
    # survives a .kbook round-trip
    nb2 = NotebookWidget()
    nb2.load_json(nb.to_json())
    assert nb2.cells[-1].CELL_TYPE == "sheet"


def test_xlsx_data_value_starting_with_equals(qapp, tmp_path):
    """A text cell that literally starts with '=' must not error."""
    openpyxl = pytest.importorskip("openpyxl")
    from khervebook.kernel import Kernel
    from khervebook.importers import xlsx_to_cells
    from khervebook.sheetcell import SheetCell
    wb = openpyxl.Workbook()
    ws = wb.active
    ws["A1"] = "=not a formula"          # stored as text in Excel
    ws["A1"].data_type = "s"
    path = tmp_path / "eq.xlsx"
    wb.save(str(path))
    sheet = SheetCell(xlsx_to_cells(str(path))[0]["source"])
    sheet.execute(Kernel())
    assert "#ERR" not in sheet.table.item(0, 0).text()
