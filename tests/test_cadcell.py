"""KherveCAD design cell.

Copyright (C) 2026 Gwilherm Kerherve

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.
"""

import json

import pytest

from khervebook import cadcell

#: a minimal KherveCAD document: one 10 mm cube
CUBE = {"format": "kcad", "version": 13, "global_fn": 45,
        "global_fn_on": True, "unit": "mm", "dimensions": [],
        "references": [],
        "tree": {"type": "root", "name": "Document", "visible": True,
                 "params": {}, "children": [
                     {"type": "cube", "name": "Block 10 mm", "visible": True,
                      "params": {"size": [10, 10, 10], "center": False},
                      "children": []}]}}


def _kcad(folder):
    path = folder / "block.kcad"
    path.write_text(json.dumps(CUBE))
    return path


def test_summary_needs_no_khervecad(tmp_path):
    assert cadcell.summary(_kcad(tmp_path)) == "block  (1 object, mm)"
    assert cadcell.summary(tmp_path / "missing.kcad") == "missing.kcad"


def test_missing_khervecad_is_explained(qapp, tmp_path, monkeypatch):
    monkeypatch.setattr(cadcell, "load_khervecad", lambda: None)
    cell = cadcell.CadCell("")
    assert not cell.attach(tmp_path / "x.pdf")
    assert cell.attach(str(_kcad(tmp_path)))
    assert "KherveCAD is not available" in cell._hint.text()
    assert json.loads(cell.source())["file"]["name"] == "block.kcad"


def _engine_ready():
    kc = cadcell.load_khervecad()
    return kc is not None and bool(kc.engine.find_openscad())


@pytest.mark.skipif(not _engine_ready(),
                    reason="KherveCAD checkout or OpenSCAD missing")
def test_renders_three_views(qapp, tmp_path):
    cell = cadcell.CadCell("")
    cell.attach(str(_kcad(tmp_path)))
    assert cell.wait_rendered(120000)
    assert cell.page_count() == len(cadcell.VIEWS) == 3
    assert cell._page_label.text() == "View 1 / 3"
    assert "rendered by OpenSCAD" in cell._hint.text()


def test_drop_kcad_and_open(qapp, tmp_path, monkeypatch):
    from khervebook import ktexdoc
    from khervebook.notebook import NotebookWidget
    monkeypatch.setattr(cadcell, "load_khervecad", lambda: None)
    calls = []
    monkeypatch.setattr(ktexdoc, "launch_detached",
                        lambda cmd, path: calls.append((cmd, path)))
    nb = NotebookWidget()
    assert nb.open_file_in_cell(str(_kcad(tmp_path)))
    cell = nb.cells[-1]
    assert cell.CELL_TYPE == "cad"
    monkeypatch.setattr(cell, "app_command", lambda: ["/x/KherveCAD"])
    assert cell.edit_in_app()
    assert calls == [(["/x/KherveCAD"], cell.document_path())]
    assert "File ▸ Open" in cell._hint.text()
