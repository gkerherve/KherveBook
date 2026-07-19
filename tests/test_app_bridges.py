"""Round-trip bridges to sibling Kherve apps (KhervePY, KherveSheet) and
the .ksheet read/write used for the sheet round-trip.

Copyright (C) 2026 Gwilherm Kerherve

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.
"""

import json


def test_ksheet_write_read_round_trip():
    import tempfile
    from pathlib import Path
    from khervebook import ksheetio
    src = json.dumps({"sheets": [
        {"name": "Data", "rows": 8, "cols": 3,
         "data": {"A1": "x", "B1": "y", "A2": "1", "B2": "=A2*2"}},
        {"name": "Notes", "rows": 5, "cols": 2, "data": {"A1": "hi"}}],
        "active": "Data"})
    tmp = Path(tempfile.mkdtemp()) / "wb.ksheet"
    ksheetio.write_ksheet(src, tmp)
    doc = ksheetio.read_ksheet(tmp)
    assert [s["name"] for s in doc["sheets"]] == ["Data", "Notes"]
    assert doc["sheets"][0]["data"]["A1"] == "x"
    assert doc["sheets"][0]["data"]["B2"] == "=A2*2"       # formula text kept
    assert doc["sheets"][1]["data"]["A1"] == "hi"


def test_ksheet_is_khervesheet_readable():
    """The file we write matches KherveSheet's schema, so KherveBook's own
    .ksheet importer (which mirrors it) can read it back."""
    import tempfile
    from pathlib import Path
    from khervebook import ksheetio, importers
    tmp = Path(tempfile.mkdtemp()) / "wb.ksheet"
    ksheetio.write_ksheet(
        {"sheets": [{"name": "S", "rows": 4, "cols": 2,
                     "data": {"A1": "1", "B1": "2"}}], "active": "S"}, tmp)
    cells = importers.ksheet_to_cells(str(tmp))
    assert cells and cells[0]["type"] == "sheet"


def test_code_cell_khervepy_reload(qapp):
    import tempfile
    from pathlib import Path
    from khervebook.notebook import NotebookWidget
    nb = NotebookWidget()
    cell = nb.add_cell_below("code", "a = 1")
    assert hasattr(cell, "open_in_khervepy")
    p = Path(tempfile.mkdtemp()) / "code.py"
    p.write_text("b = 2\nprint(b)\n")
    cell._reload_from_py(str(p))
    assert cell.source() == "b = 2\nprint(b)\n"


def test_sheet_cell_khervesheet_reload(qapp):
    import tempfile
    from pathlib import Path
    from khervebook import ksheetio
    from khervebook.notebook import NotebookWidget
    nb = NotebookWidget()
    cell = nb.add_cell_below("sheet")
    assert hasattr(cell, "open_in_khervesheet")
    tmp = Path(tempfile.mkdtemp()) / "wb.ksheet"
    ksheetio.write_ksheet(
        {"sheets": [{"name": "Sheet1", "rows": 6, "cols": 3,
                     "data": {"A1": "hello", "B2": "42"}}],
         "active": "Sheet1"}, tmp)
    cell._reload_from_ksheet(str(tmp))
    doc = json.loads(cell.source())
    data = doc["sheets"][0]["data"]
    assert data.get("A1") == "hello" and data.get("B2") == "42"


def test_app_bridge_detects_missing_app(qapp, tmp_path):
    from khervebook.appbridge import AppBridge
    from khervebook.notebook import NotebookWidget
    nb = NotebookWidget()
    bridge = AppBridge(nb.cells[0], "NoSuchApp", "nosuch", ".x",
                       lambda p: None)
    assert bridge.available() is False
