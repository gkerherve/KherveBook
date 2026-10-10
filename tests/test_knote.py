"""KherveNote .knote import.

Copyright (C) 2026 Gwilherm Kerherve

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.
"""

import base64
import json
import zipfile
from pathlib import Path

import pytest

from khervebook import knote

# 1x1 transparent PNG
PNG = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlE"
                       "QVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg==")

NOTE = {
    "format": 1,
    "meta": {"title": "XPS lecture", "speaker": "Dr Smith",
             "date": "10 October 2026", "started": "2026-10-10T09:00:00"},
    "summary": "Core levels and chemical shifts.",
    "sections": [
        {"title": "", "blocks": [{"kind": "typed", "text": "Before start"}]},
        {"title": "Theory", "t": 60, "blocks": [
            {"kind": "typed", "text": "Binding energy is key",
             "marks": [[0, 15, "b"], [18, 3, "i"]]},
            {"kind": "important", "text": "Shirley background"},
            {"kind": "question", "text": "Why spin-orbit?"},
            {"kind": "heading", "text": "Peaks", "level": 2},
            {"kind": "item", "text": "C 1s", "numbered": True},
            {"kind": "item", "text": "O 1s", "numbered": True},
            {"kind": "item", "text": "sub", "level": 1},
            {"kind": "image", "text": "Spectrum", "path": "assets/a.png"},
            {"kind": "typed", "text": "after the picture"},
            {"kind": "attachment", "text": "slides.pdf",
             "path": "assets/slides.pdf"},
        ]},
    ],
    "transcript": [{"t": 75, "text": "Good morning"},
                   {"t": 3725.5, "text": "Thank you"},
                   {"t": 80, "text": "  "}],
    "attachments": [{"path": "assets/slides.pdf", "name": "slides.pdf"}],
}


def _write(folder):
    path = folder / "lecture.knote"
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("note.json", json.dumps(NOTE))
        zf.writestr("assets/a.png", PNG)
        zf.writestr("assets/slides.pdf", b"%PDF-1.4 fake")
    return path


def test_marks_and_clock():
    assert knote.marked("Binding energy is key",
                        [[0, 15, "b"], [18, 3, "i"]]) == \
        "**Binding energy** is *key*"
    assert knote.marked("ab", [[0, 2, "b"], [0, 1, "i"]]) == "***a*b**"
    assert knote.clock(NOTE, 3725.5) == "10:02:05"
    assert knote.clock({}, 75) == "0:01:15"


def test_to_cells(qapp, tmp_path):
    cells = knote.to_cells(_write(tmp_path))
    kinds = [c["type"] for c in cells]
    assert kinds == ["markdown", "markdown", "markdown", "svg", "markdown",
                     "file", "markdown"]
    assert cells[0]["source"].startswith("# XPS lecture")
    assert "**Speaker:** Dr Smith" in cells[0]["source"]
    theory = cells[2]["source"]
    assert theory.startswith("## Theory\n\n**Binding energy** is *key*")
    assert "> **Key point:** Shirley background" in theory
    assert "### Peaks\n\n1. C 1s\n2. O 1s\n   - sub" in theory
    assert cells[3]["title"] == "Spectrum"
    files = json.loads(cells[5]["source"])["files"]
    assert [f["name"] for f in files] == ["slides.pdf"]      # not twice
    speech = cells[6]
    assert speech["collapsed"] and speech["title"] == "What was said"
    assert "**09:01:15** Good morning" in speech["source"]
    assert speech["source"].count("**") == 4                 # blank skipped


def test_drop_imports_as_one_undo_step(qapp, tmp_path):
    from khervebook.notebook import NotebookWidget
    nb = NotebookWidget()
    assert nb.open_file_in_cell(str(_write(tmp_path)))
    assert len(nb.cells) == 8
    assert nb.cells[-1].collapsed and nb.cells[-1].title == "What was said"
    assert nb.cells[6].CELL_TYPE == "file"
    nb.undo()
    assert len(nb.cells) == 1


REAL = sorted((Path.home() / "Documents" / "KherveNote").glob("*.knote"))


@pytest.mark.skipif(not REAL, reason="no KherveNote notes on this machine")
@pytest.mark.parametrize("path", REAL, ids=[p.stem for p in REAL])
def test_real_notes_import(qapp, path):
    cells = knote.to_cells(path)
    assert cells and cells[0]["source"].startswith("# ")
