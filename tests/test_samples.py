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


def test_notebook_round_trip_and_usage(qapp):
    from khervebook.notebook import NotebookWidget, FORMAT_VERSION
    nb = NotebookWidget()
    nb.edit_samples(lambda r: r.add(name="Film A").id, "New sample")
    nb.cells[0].set_source('s = ksample("S-0001")\ns.name')
    md = nb.add_cell("markdown", "Measured @S-0001 today.")
    nb.add_cell("markdown", "nothing here")

    assert nb.sample_usage("S-0001") == [nb.cells[0], md]
    nb.cells[0].execute(nb.kernel)
    assert nb.cells[0].output.text() == "'Film A'"

    doc = json.loads(nb.to_json())
    assert doc["version"] == FORMAT_VERSION
    assert doc["samples"]["items"][0]["name"] == "Film A"

    nb2 = NotebookWidget()
    nb2.load_json(nb.to_json())
    assert nb2.samples.get("S-0001").name == "Film A"
    # a fresh document has no register, and writes none
    nb2.load_json('{"cells": []}')
    assert len(nb2.samples) == 0
    assert "samples" not in json.loads(nb2.to_json())


def test_ksample_table(qapp):
    from khervebook.notebook import NotebookWidget
    nb = NotebookWidget()
    nb.edit_samples(lambda r: r.add(name="A"))
    nb.edit_samples(lambda r: r.add(name="B", parents=["S-0001"]))
    nb.cells[0].set_source("t = ksample()\nlist(t.index), t.loc['S-0002', 'parents']")
    nb.cells[0].execute(nb.kernel)
    assert nb.cells[0].output.text() == "(['S-0001', 'S-0002'], ['S-0001'])"


def test_sample_edits_are_undoable(qapp):
    from khervebook.notebook import NotebookWidget
    nb = NotebookWidget()
    nb.edit_samples(lambda r: r.add(name="A"), "New sample")
    nb.edit_samples(lambda r: r.update("S-0001", name="B"))
    assert nb.samples.get("S-0001").name == "B"
    nb.undo()
    assert nb.samples.get("S-0001").name == "A"
    nb.undo()
    assert len(nb.samples) == 0
    nb.redo()
    assert nb.samples.get("S-0001").name == "A"
    # a no-op edit pushes nothing
    count = nb.undo_stack.count()
    nb.edit_samples(lambda r: r.update("S-0001", name="A"))
    assert nb.undo_stack.count() == count


def test_markdown_link_click_reaches_panel(qapp):
    from PyQt5.QtCore import QUrl
    from khervebook.notebook import NotebookWidget
    from khervebook.samplesdock import SamplesDock
    nb = NotebookWidget()
    dock = SamplesDock(nb)
    nb.edit_samples(lambda r: r.add(name="A").id)
    nb.edit_samples(lambda r: r.add(name="B").id)
    md = nb.add_cell("markdown", "See @S-0002")
    md.execute(nb.kernel)
    assert "ksample:S-0002" in md.view.document().toMarkdown()
    md.view.anchorClicked.emit(QUrl("ksample:S-0002"))
    assert dock.heading.text() == "S-0002"
    assert dock.used.item(0).data(256) is md      # Qt.UserRole


def test_panel_edits_and_mention(qapp):
    from khervebook.notebook import NotebookWidget
    from khervebook.samplesdock import SamplesDock
    nb = NotebookWidget()
    dock = SamplesDock(nb)
    sid = dock.new_sample()
    dock.fields["name"].setText("Wafer 7")
    dock.fields["name"].editingFinished.emit()
    assert nb.samples.get(sid).name == "Wafer 7"
    child = dock.new_child()
    assert nb.samples.get(child).parents == [sid]
    assert dock.tree.topLevelItem(0).child(0).text(0) == child
    nb._select(nb.cells[0])
    dock.mention_in_cell()
    assert nb.cells[0].source() == f'ksample("{child}")'
    dock._show(sid)
    dock.parents.setText(f"{child}, S-9999")
    dock.parents.editingFinished.emit()
    assert nb.samples.get(sid).parents == []      # cycle + unknown dropped


def test_ipynb_keeps_the_register(qapp):
    from khervebook.notebook import NotebookWidget
    nb = NotebookWidget()
    nb.edit_samples(lambda r: r.add(name="A"))
    nb2 = NotebookWidget()
    nb2.load_ipynb(nb.to_ipynb())
    assert nb2.samples.get("S-0001").name == "A"
