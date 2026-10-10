"""Sample register, @mentions, ksample() and the Samples panel.

Copyright (C) 2026 Gwilherm Kerherve

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.
"""

import json

from khervebook.samples import SampleRegistry


def _reg():
    reg = SampleRegistry()
    a = reg.add(name="TiO2 powder")
    b = reg.add(name="Pellet", parents=[a.id])
    c = reg.add(name="Annealed pellet", parents=[b.id])
    return reg, a, b, c


def test_ids_count_up_and_never_reuse():
    reg, a, b, c = _reg()
    assert [a.id, b.id, c.id] == ["S-0001", "S-0002", "S-0003"]
    reg.remove("S-0003")
    reg.remove("S-0002")
    assert reg.next_id() == "S-0002"       # highest in use + 1
    reg.add(name="x")
    reg.add(name="y")
    reg.remove("S-0002")
    assert reg.next_id() == "S-0004"       # S-0003 still holds the top


def test_lineage_and_cycle_guard():
    reg, a, b, c = _reg()
    assert reg.ancestors(c.id) == [b.id, a.id]
    assert reg.descendants(a.id) == [b.id, c.id]
    assert reg.roots() == [a.id]
    # a sample cannot be made from its own descendant
    reg.update(a.id, parents=[c.id])
    assert reg.get(a.id).parents == []


def test_load_normalises_bad_data():
    reg = SampleRegistry()
    reg.load({"prefix": "1bad", "digits": "x",
              "items": [{"id": "S-0001", "status": "weird", "extra": 1,
                         "parents": None}, {"id": "S-0001"}, "junk"]})
    assert reg.prefix == "S" and reg.digits == 4
    assert reg.ids() == ["S-0001"]
    assert reg.get("S-0001").status == "in use"


def test_link_mentions_skips_code_and_unknown_ids():
    reg, a, _b, _c = _reg()
    md = ("Used @S-0001 and @S-0099.\n"
          "Inline `@S-0001` stays.\n"
          "```\n@S-0001\n```\n"
          "mail me@S-0001")
    out = reg.link_mentions(md).split("\n")
    assert out[0] == "Used [@S-0001](ksample:S-0001) and @S-0099."
    assert out[1] == "Inline `@S-0001` stays."
    assert out[3] == "@S-0001"
    assert out[5] == "mail me@S-0001"


def _nb_with_samples(qapp, *names):
    """A notebook whose first cell is a Samples cell holding *names*."""
    from khervebook.notebook import NotebookWidget
    nb = NotebookWidget()
    cell = nb.add_cell("samples", "", index=0)
    for name in names:
        sid = cell.new_sample()
        cell.reg.update(sid, name=name)
        cell._commit()
    return nb, cell


def test_cell_ids_usage_and_ksample(qapp):
    nb, cell = _nb_with_samples(qapp, "Film A", "Film B")
    assert cell.reg.ids() == ["S-0001", "S-0002"]
    code = nb.cells[1]
    code.set_source('s = ksample("S-0001")\ns.name')
    md = nb.add_cell("markdown", "Measured @S-0001 today.")
    nb.add_cell("markdown", "nothing here")
    # the Samples cell's own JSON is not a "use"
    assert nb.sample_usage("S-0001") == [code, md]
    code.execute(nb.kernel)
    assert code.output.text() == "'Film A'"
    nb._refresh_sample_usage()
    assert cell.grid.item(0, cell.grid.columnCount() - 1).text() == \
        "cell 2, cell 3"
    assert cell.grid.item(1, cell.grid.columnCount() - 1).text() == "—"


def test_ids_continue_across_cells(qapp):
    nb, first = _nb_with_samples(qapp, "A", "B")
    second = nb.add_cell("samples", "")
    assert second.new_sample() == "S-0003"
    assert nb.samples.ids() == ["S-0001", "S-0002", "S-0003"]


def test_table_edits_undo_and_round_trip(qapp):
    from khervebook.notebook import FORMAT_VERSION, NotebookWidget
    from khervebook.samplecell import _C
    nb, cell = _nb_with_samples(qapp, "A")
    cell.grid.item(0, _C["name"]).setText("Wafer 7")
    assert cell.reg.get("S-0001").name == "Wafer 7"
    nb.undo()
    assert cell.reg.get("S-0001").name == "A"
    nb.redo()
    child = (cell.grid.selectRow(0), cell.new_child())[1]
    assert cell.reg.get(child).parents == ["S-0001"]
    cell.grid.item(0, _C["parents"]).setText(f"{child}, S-9999")
    assert cell.reg.get("S-0001").parents == []    # cycle + unknown dropped
    doc = json.loads(nb.to_json())
    assert doc["version"] == FORMAT_VERSION and "samples" not in doc
    nb2 = NotebookWidget()
    nb2.load_json(nb.to_json())
    assert nb2.samples.get("S-0001").name == "Wafer 7"
    assert nb2.samples.get(child).parents == ["S-0001"]


def test_delete_and_status(qapp):
    from khervebook.samplecell import _C
    nb, cell = _nb_with_samples(qapp, "A", "B")
    cell.reg.update("S-0002", parents=["S-0001"])
    cell._commit()
    cell.grid.item(1, _C["status"]).setText("consumed")
    assert cell.reg.get("S-0002").status == "consumed"
    cell.grid.selectRow(0)
    cell.delete_selected()
    assert cell.reg.ids() == ["S-0002"]
    assert cell.reg.get("S-0002").parents == []
    nb.undo()
    assert cell.reg.ids() == ["S-0001", "S-0002"]


def test_mention_click_selects_row(qapp):
    from PyQt5.QtCore import QUrl
    nb, cell = _nb_with_samples(qapp, "A", "B")
    md = nb.add_cell("markdown", "See @S-0002")
    md.execute(nb.kernel)
    assert "ksample:S-0002" in md.view.document().toMarkdown()
    md.view.anchorClicked.emit(QUrl("ksample:S-0002"))
    assert cell.selected_ids() == ["S-0002"]
    assert nb.current is cell


def test_ksample_table(qapp):
    nb, cell = _nb_with_samples(qapp, "A", "B")
    cell.reg.update("S-0002", parents=["S-0001"])
    cell._commit()
    code = nb.cells[1]
    code.set_source("t = ksample()\nlist(t.index), t.loc['S-0002', 'parents']")
    code.execute(nb.kernel)
    assert code.output.text() == "(['S-0001', 'S-0002'], ['S-0001'])"


def test_old_top_level_register_becomes_a_cell(qapp):
    from khervebook.notebook import NotebookWidget
    old = {"format": "kbook", "version": 8,
           "cells": [{"type": "markdown", "source": "@S-0001"}],
           "samples": {"prefix": "S", "digits": 4,
                       "items": [{"id": "S-0001", "name": "Old"}]}}
    nb = NotebookWidget()
    nb.load_json(json.dumps(old))
    assert [c.CELL_TYPE for c in nb.cells] == ["samples", "markdown"]
    assert nb.samples.get("S-0001").name == "Old"
    # and an .ipynb exported with the register in its metadata
    meta = {"cells": [], "metadata": {"khervebook": {"samples":
                                                     old["samples"]}}}
    nb.load_ipynb(json.dumps(meta))
    assert nb.cells[0].CELL_TYPE == "samples"


def test_ipynb_keeps_the_samples_cell(qapp):
    from khervebook.notebook import NotebookWidget
    nb, cell = _nb_with_samples(qapp, "A")
    doc = json.loads(nb.to_ipynb())
    assert "| S-0001 | A |" in "".join(doc["cells"][0]["source"])
    nb2 = NotebookWidget()
    nb2.load_ipynb(nb.to_ipynb())
    assert nb2.samples.get("S-0001").name == "A"
