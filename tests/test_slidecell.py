"""KherveSlide deck cell (a KherveTeX-cell subclass).

Copyright (C) 2026 Gwilherm Kerherve

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.
"""

import json
import os
import time

import pytest

from khervebook import ktexdoc


def _deck(folder, slides=3, title="Group meeting"):
    path = folder / "talk.kslide"
    path.write_text(json.dumps({"type": "Deck", "title": title,
                                "slides": [{"type": "Slide", "objects": [],
                                            "title": f"S{i}"}
                                           for i in range(slides)]}))
    return path


def _pdf(path, pages):
    fitz = pytest.importorskip("fitz")
    doc = fitz.open()
    for i in range(pages):
        doc.new_page(width=400, height=300).insert_text((40, 60), f"{i}")
    doc.save(str(path))
    doc.close()


def test_deck_from_its_pdf(qapp, tmp_path):
    from khervebook.slidecell import SlideCell
    src = _deck(tmp_path)
    _pdf(tmp_path / "talk.pdf", 3)
    cell = SlideCell("")
    assert not cell.attach(tmp_path / "talk.pdf")      # only decks
    assert cell.attach(str(src))
    assert cell.wait_rendered()
    assert cell.page_count() == 3
    assert cell.title_text() == "Group meeting  (3 slides)"
    assert "exported PDF" in cell._hint.text()
    # round trip keeps the deck (embedded while the notebook is unsaved)
    back = SlideCell(cell.source())
    assert json.loads(back.source())["file"]["name"] == "talk.kslide"
    back.wait_rendered()


def test_stale_or_missing_tex_explains(qapp, tmp_path):
    from khervebook.slidecell import SlideCell
    src = _deck(tmp_path)
    tex = tmp_path / "talk.tex"
    tex.write_text("old")
    old = time.time() - 3600
    os.utime(tex, (old, old))               # older than the deck: stale
    kind, _ = SlideCell.pdf_source(src)
    assert kind == "model"
    cell = SlideCell("")
    cell.attach(str(src))
    cell.wait_rendered()
    assert "save once" in cell._hint.text()


def test_edit_in_kherveslide(qapp, tmp_path, monkeypatch):
    from khervebook.slidecell import SlideCell
    calls = []
    monkeypatch.setattr(ktexdoc, "launch_detached",
                        lambda cmd, path: calls.append((cmd, path)))
    cell = SlideCell("")
    cell.attach(str(_deck(tmp_path)))
    monkeypatch.setattr(cell, "app_command", lambda: None)
    assert not cell.edit_in_app()
    assert "KherveSlide was not found" in cell._hint.text()
    monkeypatch.setattr(cell, "app_command", lambda: ["/x/KherveSlide"])
    assert cell.edit_in_app()
    assert calls == [(["/x/KherveSlide"], cell.document_path())]
    cell.wait_rendered()


def test_drop_kslide_makes_slide_cell(qapp, tmp_path):
    from khervebook.notebook import NotebookWidget
    nb = NotebookWidget()
    assert nb.open_file_in_cell(str(_deck(tmp_path)))
    cell = nb.cells[-1]
    assert cell.CELL_TYPE == "slide" and cell.file_name == "talk.kslide"
    assert json.loads(cell.source())["kbook_slide"] == 1
    cell.wait_rendered()
