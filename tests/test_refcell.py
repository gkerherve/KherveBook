"""References cell: formatting, BibTeX, KherveRef libraries, citations.

Copyright (C) 2026 Gwilherm Kerherve

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.
"""

import json

from khervebook import refs

ENTRY = {"key": "bagarinao2023nanostructured", "type": "article",
         "authors": [{"family": "Bagarinao", "given": "Katherine Develos"},
                     {"family": "Kerherve", "given": "Gwilherm"}],
         "title": "Nanostructured LSC Thin Film Electrodes",
         "date": "2023-05-19", "journal": "ECS Transactions",
         "volume": "111", "number": "6", "pages": "731–736",
         "doi": "10.1149/11106.0731ecst"}


def test_format_styles():
    num = refs.plain(refs.format_entry(ENTRY, "numbered"))
    assert num.startswith("Bagarinao, K. D.; Kerherve, G. Nanostructured")
    assert "ECS Transactions 2023, 111 (6), 731–736." in num
    ay = refs.plain(refs.format_entry(ENTRY, "author-year"))
    assert ay.startswith("Bagarinao, K. D., & Kerherve, G. (2023).")
    assert refs.short_cite(ENTRY) == "Bagarinao & Kerherve, 2023"


def test_bibtex_round_trip():
    bib = refs.to_bibtex([refs.normalise(ENTRY)])
    assert "author = {Bagarinao, Katherine Develos and Kerherve, Gwilherm}" \
        in bib
    back = refs.parse_bibtex(bib)[0]
    assert back["key"] == ENTRY["key"]
    assert back["authors"] == ENTRY["authors"]
    assert back["date"] == "2023" and back["doi"] == ENTRY["doi"]


def test_parse_messy_bibtex():
    text = r"""@string{x = "y"}
    @Article{smith99,
      author = "John Smith and Doe, Jane",
      title = {The {XPS} of Caf\'e},
      journaltitle = {Surf. Sci.}, year = 1999, pages = {1--9}
    }
    @misc{,}"""
    (e,) = refs.parse_bibtex(text)
    assert e["authors"] == [{"family": "Smith", "given": "John"},
                            {"family": "Doe", "given": "Jane"}]
    assert e["title"] == "The XPS of Cafe"
    assert e["journal"] == "Surf. Sci." and e["pages"] == "1–9"


def test_csl_and_keys():
    e = refs.from_csl({"type": "article-journal", "DOI": "10.1/abc",
                       "title": ["On the <i>XPS</i> of gold"],
                       "author": [{"family": "Müller", "given": "Anna"}],
                       "issued": {"date-parts": [[2021, 3]]},
                       "container-title": ["J. Phys."], "page": "10-12"})
    assert e["date"] == "2021-03" and e["pages"] == "10–12"
    assert e["title"] == "On the XPS of gold"
    assert refs.make_key(e) == "muller2021xps"
    assert refs.make_key(e, {"muller2021xps"}) == "muller2021xpsa"
    assert refs.clean_doi("https://doi.org/10.1000/abc.") == "10.1000/abc"


def test_link_citations():
    index = {"a": (1, ENTRY), "b": (2, ENTRY)}
    md = "See [@a; @b] and [@zz], `[@a]` too."
    out = refs.link_citations(md, index)
    assert out.startswith("See \\[[1](kref:a), [2](kref:b)\\] and [@zz]")
    assert out.endswith("`[@a]` too.")
    ay = refs.link_citations("[@a]", index, "author-year")
    assert ay == "([Bagarinao & Kerherve, 2023](kref:a))"


def _library(tmp_path):
    root = tmp_path / "REF Library"
    (root / ".kherveref" / "references").mkdir(parents=True)
    (root / "REF Library.kref").write_text(json.dumps(
        {"app": "KherveRef", "format": 2, "name": "My refs"}))
    (root / ".kherveref" / "references" / f"{ENTRY['key']}.json")\
        .write_text(json.dumps(ENTRY))
    return root


def test_reads_kherveref_library(tmp_path, monkeypatch):
    # not this machine's own KherveRef list
    monkeypatch.setattr(refs, "_appdata", lambda: tmp_path / "appdata")
    root = _library(tmp_path)
    assert refs.library_root(root / "REF Library.kref") == root
    assert refs.library_name(root) == "My refs"
    assert refs.load_library(root)[0]["title"] == ENTRY["title"]
    assert refs.known_libraries([str(root), str(tmp_path)]) == [root]


def test_cell_citations_and_kref(qapp):
    from khervebook.notebook import NotebookWidget
    nb = NotebookWidget()
    md = nb.add_cell("markdown", "Films as in [@bagarinao2023nanostructured].")
    ref = nb.add_cell("ref", "")
    ref.add_entries([ENTRY, dict(ENTRY, key="other", doi="10.9/x")])
    md.execute(nb.kernel)
    assert "kref:bagarinao2023nanostructured" in \
        md.view.document().toMarkdown()
    assert "cited 1×" in ref.list.item(0).text()
    nb.cells[0].set_source("t = kref()\nlist(t.index), t.loc['other', 'year']")
    nb.cells[0].execute(nb.kernel)
    assert nb.cells[0].output.text() == \
        "(['bagarinao2023nanostructured', 'other'], '2023')"
    # duplicates by DOI are skipped; taken keys get a suffix
    assert ref.add_entries([ENTRY]) == []
    assert ref.add_entries([dict(ENTRY, doi="")]) == \
        ["bagarinao2023nanostructured" + "a"]


def test_cell_undo_and_round_trip(qapp):
    from khervebook.notebook import NotebookWidget
    nb = NotebookWidget()
    ref = nb.add_cell("ref", "")
    ref.add_entries([ENTRY])
    ref.set_style("author-year")
    ref.list.setCurrentRow(0)
    ref.remove_selected()
    assert ref.entries == []
    nb.undo()
    assert ref.entries[0]["key"] == ENTRY["key"]
    nb.undo()
    assert ref.cite_style == "numbered"
    nb2 = NotebookWidget()
    nb2.load_json(nb.to_json())
    assert nb2.cells[1].entries == ref.entries


def test_drop_bib_and_kref(qapp, tmp_path, monkeypatch):
    from khervebook.notebook import NotebookWidget
    from khervebook import refcell
    bib = tmp_path / "x.bib"
    bib.write_text(refs.to_bibtex([refs.normalise(ENTRY)]))
    nb = NotebookWidget()
    assert nb.open_file_in_cell(str(bib))
    assert nb.cells[-1].CELL_TYPE == "ref"
    assert nb.cells[-1].entries[0]["key"] == ENTRY["key"]
    monkeypatch.setattr(refcell.RefCell, "add_from_library",
                        lambda self: None)
    root = _library(tmp_path)
    nb2 = NotebookWidget()
    assert nb2.open_file_in_cell(str(root / "REF Library.kref"))
    assert nb2.cells[-1].library == str(root)


def test_doi_lookup_runs_off_thread(qapp, monkeypatch):
    import time
    from khervebook import refcell
    monkeypatch.setattr(refs, "lookup_doi", lambda doi: dict(ENTRY))
    cell = refcell.RefCell("")
    cell.doi.setText("doi: 10.1149/11106.0731ecst")
    assert cell.add_doi()
    deadline = time.time() + 5
    while not cell.entries and time.time() < deadline:
        qapp.processEvents()
        time.sleep(0.01)
    assert cell.entries[0]["key"] == ENTRY["key"]
    assert cell.doi.text() == ""
