"""Tests for the KherveTeX document cell and the KherveMol molecule cell.

Nothing here launches KherveTeX or KherveMol: the launchers are
monkeypatched and only the command they would run is checked.

Copyright (C) 2026 Gwilherm Kerherve

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.
"""

import json
import os
import stat
import time
import zipfile

import pytest

from khervebook import ktexdoc, siblings
from khervebook.cells import make_cell
from khervebook import notebook  # noqa: F401  (registers every cell type)


def _pdf(path, pages):
    fitz = pytest.importorskip("fitz")
    doc = fitz.open()
    for i in range(pages):
        page = doc.new_page()
        page.insert_text((72, 90), f"Page {i + 1}", fontsize=24)
    doc.save(str(path))
    doc.close()


def _pump(qapp, until, timeout=20.0):
    end = time.time() + timeout
    while time.time() < end:
        qapp.processEvents()
        if until():
            return True
        time.sleep(0.02)
    return until()


# -- ktexdoc (Qt-free) -------------------------------------------------------

def test_new_ktexz_is_a_valid_kdocz(tmp_path):
    path = ktexdoc.new_ktexz(tmp_path / "a.ktexz", title="My report")
    with zipfile.ZipFile(path) as zf:
        assert {"manifest.json", "document.json"} <= set(zf.namelist())
        manifest = json.loads(zf.read("manifest.json"))
        doc = json.loads(zf.read("document.json"))
    assert manifest == {"format": "kdocz", "schema_version": 1,
                        "app": "KherveTeX"}
    assert doc["type"] == "Document"
    assert doc["meta"]["documentclass"] == "article"
    assert [c["type"] for c in doc["children"]] == ["Section", "Paragraph"]
    assert ktexdoc.title_of(path) == "My report"


def test_title_prefers_title_block_and_reads_tex(tmp_path):
    p = tmp_path / "t.ktexz"
    with zipfile.ZipFile(p, "w") as zf:
        zf.writestr("document.json", json.dumps({
            "type": "Document", "meta": {"title": "meta title"},
            "children": [{"type": "Title", "children": [
                {"type": "Text", "text": "Shown title", "marks": []}]}]}))
    assert ktexdoc.title_of(p) == "Shown title"
    tex = tmp_path / "x.tex"
    tex.write_text("\\documentclass{article}\n\\title{\\textbf{Bold "
                   "Title}}\n\\begin{document}hi\\end{document}\n")
    assert ktexdoc.title_of(tex) == "Bold Title"
    (tmp_path / "y.tex").write_text("no title")
    assert ktexdoc.title_of(tmp_path / "y.tex") == "y"


def test_pdf_source_prefers_a_current_pdf(tmp_path):
    doc = ktexdoc.new_ktexz(tmp_path / "d.ktexz")
    assert ktexdoc.pdf_source(doc)[0] == "model"
    tex = tmp_path / "d.tex"
    tex.write_text("x")
    assert ktexdoc.pdf_source(doc) == ("tex", tex)
    pdf = tmp_path / "d.pdf"
    pdf.write_bytes(b"%PDF")
    assert ktexdoc.pdf_source(doc) == ("pdf", pdf)
    old = time.time() - 3600
    os.utime(pdf, (old, old))            # a stale PDF is not trusted
    os.utime(tex, (old, old))
    assert ktexdoc.pdf_source(doc)[0] == "model"


def test_render_pages(tmp_path):
    _pdf(tmp_path / "p.pdf", 3)
    pngs = ktexdoc.render_pages((tmp_path / "p.pdf").read_bytes(), dpi=40)
    assert len(pngs) == 3 and all(p[:4] == b"\x89PNG" for p in pngs)


@pytest.mark.skipif(not __import__("khervebook.latexcompile", fromlist=["x"])
                    .available(), reason="tectonic / PyMuPDF missing")
def test_compiles_tex_and_model_with_tectonic(tmp_path):
    tex = tmp_path / "paper.tex"
    tex.write_text("\\documentclass{article}\\begin{document}Hello "
                   "\\newpage World\\end{document}\n")
    pdf, log = ktexdoc.document_pdf(tex)
    assert pdf and pdf[:4] == b"%PDF", log
    assert (tmp_path / "paper.pdf").exists()        # cached like KherveTeX
    assert len(ktexdoc.render_pages(pdf, dpi=30)) == 2
    doc = ktexdoc.new_ktexz(tmp_path / "fresh.ktexz", title="Fresh")
    pdf, log = ktexdoc.document_pdf(doc)
    assert pdf and pdf[:4] == b"%PDF", log
    assert not list(tmp_path.glob(".fresh*"))       # temp .tex cleaned up


# -- locating KherveTeX -------------------------------------------------------

def _fake_app(root):
    app = root / "KherveTeX.app"
    exe = app / "Contents" / "MacOS" / "KherveTeX"
    exe.parent.mkdir(parents=True)
    exe.write_text("#!/bin/sh\n")
    exe.chmod(exe.stat().st_mode | stat.S_IEXEC)
    return app, exe


def test_find_khervetex_installed_app(tmp_path, monkeypatch):
    app, exe = _fake_app(tmp_path)
    monkeypatch.setattr(ktexdoc, "install_candidates", lambda: [app])
    assert ktexdoc.find_khervetex() == [str(exe)]


def test_find_khervetex_source_checkout(tmp_path, monkeypatch):
    repo = tmp_path / "KherveTeX"
    (repo / "khervedoc").mkdir(parents=True)
    (repo / "khervedoc" / "__init__.py").write_text("")
    (repo / "kherveDOC.py").write_text("")
    py = repo / ".venv" / "bin" / "python"
    py.parent.mkdir(parents=True)
    py.write_text("")
    monkeypatch.setattr(ktexdoc, "install_candidates", lambda: [])
    monkeypatch.setenv("KHERVETEX_PATH", str(repo))
    if os.name == "nt":
        pytest.skip("venv layout differs on Windows")
    assert ktexdoc.find_khervetex() == [str(py), str(repo / "kherveDOC.py")]


def test_find_khervetex_override_and_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(ktexdoc, "install_candidates", lambda: [])
    monkeypatch.setattr(siblings, "checkout", lambda *a, **k: None)
    assert ktexdoc.find_khervetex() is None
    exe = tmp_path / "KherveTeX.exe"
    exe.write_text("")
    assert ktexdoc.find_khervetex(str(exe)) == [str(exe)]


# -- the KherveTeX cell ---------------------------------------------------------

@pytest.fixture
def no_launch(monkeypatch):
    calls = []
    monkeypatch.setattr(ktexdoc, "launch_detached",
                        lambda cmd, path: calls.append((cmd, path)))
    return calls


def test_ktex_cell_new_document_and_round_trip(qapp, tmp_path):
    cell = make_cell("ktex")
    cell.new_document(title="Lab notes")
    assert cell.file_name == "document.ktexz"
    assert cell.title_text() == "Lab notes"
    src = json.loads(cell.source())
    assert src["kbook_ktex"] == 1 and "embed" in src["file"]  # unsaved
    again = make_cell("ktex", cell.source())
    assert again.title_text() == "Lab notes"
    cell.wait_rendered()
    again.wait_rendered()


def test_ktex_cell_lives_beside_the_notebook(qapp, tmp_path):
    from khervebook.notebook import NotebookWidget
    nb = NotebookWidget()
    nb.set_document_path(tmp_path / "book.kbook")
    cell = nb.add_cell("ktex", "")
    ktexdoc.new_ktexz(tmp_path / "src.ktexz", title="Beside")
    (tmp_path / "src.tex").write_text("\\documentclass{article}")
    assert cell.attach(str(tmp_path / "src.ktexz"))
    target = tmp_path / "book_files" / "src.ktexz"
    assert target.exists() and (tmp_path / "book_files" / "src.tex").exists()
    nb.prepare_save()
    data = json.loads(nb.to_json())
    entry = [c for c in data["cells"] if c["type"] == "ktex"][0]
    assert json.loads(entry["source"])["file"] == {
        "name": "src.ktexz", "size": target.stat().st_size,
        "path": "book_files/src.ktexz"}
    nb2 = NotebookWidget()
    nb2.load_json(nb.to_json())
    nb2.set_document_path(tmp_path / "book.kbook")
    back = [c for c in nb2.cells if c.CELL_TYPE == "ktex"][0]
    assert back.document_path() == target
    assert back.title_text() == "Beside"
    cell.wait_rendered()
    back.wait_rendered()


def test_ktex_cell_shows_pdf_pages_and_follows_changes(qapp, tmp_path):
    doc = ktexdoc.new_ktexz(tmp_path / "paper.ktexz", title="Paper")
    _pdf(tmp_path / "paper.pdf", 2)
    cell = make_cell("ktex")
    cell.set_context(tmp_path, "nb")
    assert cell.attach(str(doc))
    cell.wait_rendered()
    assert _pump(qapp, lambda: cell.page_count() == 2)
    assert cell._page_label.text() == "Page 1 / 2"
    # KherveTeX recompiles: the cached PDF next to the document changes.
    live_pdf = ktexdoc.sibling(cell.document_path(), ".pdf")
    time.sleep(1.1)
    _pdf(live_pdf, 3)
    assert _pump(qapp, lambda: cell.page_count() == 3, timeout=30)


def test_ktex_cell_insert_tex(qapp, tmp_path):
    tex = tmp_path / "note.tex"
    tex.write_text("\\documentclass{article}\\title{A tex note}"
                   "\\begin{document}\\maketitle\\end{document}")
    _pdf(tmp_path / "note.pdf", 1)
    cell = make_cell("ktex")
    assert cell.attach(str(tex))
    assert cell.title_text() == "A tex note"
    cell.wait_rendered()
    assert _pump(qapp, lambda: cell.page_count() == 1)
    assert not cell.attach(str(tmp_path / "note.pdf"))   # not a document


def test_edit_in_khervetex_launches_or_explains(qapp, tmp_path, monkeypatch,
                                               no_launch):
    cell = make_cell("ktex")
    cell.new_document()
    monkeypatch.setattr(cell, "khervetex_command", lambda: None)
    assert not cell.edit_in_khervetex()
    assert not cell._locate_btn.isHidden()
    assert "not found" in cell._hint.text()
    assert no_launch == []
    monkeypatch.setattr(cell, "khervetex_command", lambda: ["/x/KherveTeX"])
    assert cell.edit_in_khervetex()
    assert no_launch == [(["/x/KherveTeX"], cell.document_path())]
    assert str(cell.document_path()) in cell._watcher.files()
    cell.wait_rendered()


def test_unsaved_edits_reach_the_notebook(qapp, tmp_path):
    """Before the notebook is saved the document lives in a temp copy; an
    edit made there (by KherveTeX) must be what the notebook saves."""
    cell = make_cell("ktex")
    cell.new_document(title="Before")
    path = cell.document_path()
    time.sleep(1.1)
    ktexdoc.new_ktexz(path, title="After")
    assert _pump(qapp, lambda: cell.title_text() == "After"
                 and '"embed"' in cell.source(), timeout=10)
    back = make_cell("ktex", cell.source())
    assert back.title_text() == "After"
    cell.wait_rendered()
    back.wait_rendered()


def test_notebook_drop_ktexz_makes_a_document_cell(qapp, tmp_path):
    from khervebook.notebook import NotebookWidget
    nb = NotebookWidget()
    doc = ktexdoc.new_ktexz(tmp_path / "drop.ktexz", title="Dropped")
    assert nb.open_file_in_cell(str(doc))
    cell = nb.cells[-1]
    assert cell.CELL_TYPE == "ktex" and cell.title_text() == "Dropped"
    cell.wait_rendered()


# -- sibling packages ---------------------------------------------------------

def test_import_package_from_env(tmp_path, monkeypatch):
    pkg = tmp_path / "Somewhere" / "kbfakepkg"
    pkg.mkdir(parents=True)
    (pkg / "__init__.py").write_text("VALUE = 42\n")
    monkeypatch.setenv("KBFAKE_PATH", str(pkg))
    monkeypatch.setattr("sys.path", list(__import__("sys").path))
    mod = siblings.import_package("kbfakepkg", "NoSuchRepo", "KBFAKE_PATH")
    assert mod is not None and mod.VALUE == 42
    assert siblings.import_package("kbnopkg", "NoSuchRepo") is None


def test_appbridge_repo_override(qapp, tmp_path):
    from PyQt5.QtWidgets import QWidget
    from khervebook.appbridge import AppBridge
    (tmp_path / "khervemol").mkdir()
    (tmp_path / "khervemol" / "__main__.py").write_text("")
    bridge = AppBridge(QWidget(), "KherveMol", "khervemol", ".kmol",
                       lambda p: None, repo=tmp_path)
    assert bridge.available()


# -- the molecule cell --------------------------------------------------------

def _need_khervemol():
    from khervebook import molcell
    if molcell.load_khervemol() is None:
        pytest.skip("KherveMol is not available")


def test_mol_cell_builds_and_round_trips(qapp):
    _need_khervemol()
    cell = make_cell("mol")
    assert cell.build("c1ccccc1")
    assert cell.viewer.mol.formula() == "C6H6"
    assert cell.sketch.atoms                     # 2D mirror filled in
    cell.show_view(1)
    src = cell.source()
    doc = json.loads(src)
    assert doc["kbook_mol"] == 1 and doc["view"] == "2d"
    assert doc["kmol"]["format"] == "khervemol"
    back = make_cell("mol", src)
    assert back.viewer.mol.formula() == "C6H6"
    assert back.view_mode() == "2d"
    assert len(back.sketch.atoms) == len(cell.sketch.atoms)


def test_mol_cell_name_and_formula_entry(qapp):
    _need_khervemol()
    cell = make_cell("mol")
    assert cell.build("caffeine")
    assert cell.viewer.mol.formula() == "C8H10N4O2"
    other = make_cell("mol")
    if other.build("C8H10N4O2"):
        assert other.viewer.mol.formula() == "C8H10N4O2"
    assert not other.build("definitely not a molecule ((")
    assert "Could not build" in other._hint.text()


def test_mol_cell_kmol_file_round_trip(qapp, tmp_path):
    _need_khervemol()
    cell = make_cell("mol")
    cell.build("CCO")
    path = tmp_path / "m.kmol"
    cell.write_kmol(path)
    from khervemol import document
    mol, atoms2d, _bonds2d = document.load(str(path))   # KherveMol reads it
    assert mol.formula() == "C2H6O" and atoms2d
    other = make_cell("mol")
    other._reload_from_file(str(path))
    assert other.viewer.mol.formula() == "C2H6O"


def test_mol_cell_without_khervemol_keeps_its_molecule(qapp, monkeypatch):
    from khervebook import molcell
    monkeypatch.setattr(molcell, "load_khervemol", lambda: None)
    stored = {"kbook_mol": 1, "view": "3d", "query": "water",
              "kmol": {"format": "khervemol", "version": 5,
                       "mol3d": {"label": "Water", "atoms": [["O", 0, 0, 0]],
                                 "bonds": []}}}
    cell = make_cell("mol", json.dumps(stored))
    assert cell.viewer is None
    assert json.loads(cell.source())["kmol"] == stored["kmol"]
    assert cell._name.text() == "Water"
    assert not cell.open_in_khervemol()


def test_open_in_khervemol_uses_the_located_checkout(qapp, monkeypatch):
    _need_khervemol()
    from khervebook import appbridge
    opened = []
    monkeypatch.setattr(appbridge.AppBridge, "open",
                        lambda self, writer: opened.append(self._repo()))
    cell = make_cell("mol")
    cell.build("O")
    cell.open_in_khervemol()
    assert opened and (opened[0] / "khervemol" / "__init__.py").exists()


def test_notebook_drop_kmol(qapp, tmp_path):
    _need_khervemol()
    from khervebook.notebook import NotebookWidget
    src = make_cell("mol")
    src.build("CCO")
    path = tmp_path / "ethanol.kmol"
    src.write_kmol(path)
    nb = NotebookWidget()
    assert nb.open_file_in_cell(str(path))
    assert nb.cells[-1].CELL_TYPE == "mol"
    assert nb.cells[-1].viewer.mol.formula() == "C2H6O"


def test_first_save_moves_the_pdf_and_tex_along(qapp, tmp_path):
    """Inserted before the notebook had a path, the document's cached PDF
    must follow it into the sidecar folder, still current."""
    from khervebook.notebook import NotebookWidget
    src = tmp_path / "src"
    src.mkdir()
    doc = ktexdoc.new_ktexz(src / "paper.ktexz", title="Moved")
    (src / "paper.tex").write_text("\\documentclass{article}")
    _pdf(src / "paper.pdf", 1)
    nb = NotebookWidget()
    cell = nb.add_cell("ktex", "")
    cell.attach(str(doc))
    cell.wait_rendered()
    nb.set_document_path(tmp_path / "book.kbook")
    nb.prepare_save()
    side = tmp_path / "book_files"
    assert sorted(p.name for p in side.iterdir()) == [
        "paper.ktexz", "paper.pdf", "paper.tex"]
    assert ktexdoc.pdf_source(side / "paper.ktexz")[0] == "pdf"
    cell.wait_rendered()
