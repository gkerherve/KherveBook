"""Notebook templates (File ▸ New from Template) and user templates.

Copyright (C) 2026 Gwilherm Kerherve

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.
"""

import json

import pytest

from khervebook import templates


@pytest.mark.parametrize("name, _cat, builder", templates.TEMPLATES,
                         ids=[t[0] for t in templates.TEMPLATES])
def test_template_loads(qapp, name, _cat, builder):
    from khervebook.notebook import NotebookWidget
    nb = NotebookWidget()
    nb.load_json(templates.template_json(builder))
    assert nb.cells[0].CELL_TYPE == "markdown"
    assert name.split()[0] in nb.cells[0].source()
    for cell in nb.cells:
        if cell.CELL_TYPE == "code":
            compile(cell.source(), name, "exec")
        if cell.CELL_TYPE == "lab":
            # stored already in normal form: reloading changes nothing
            before = cell.source()
            cell.set_source(before)
            assert cell.source() == before


def test_solution_template_computes_masses(qapp):
    from khervebook.notebook import NotebookWidget
    nb = NotebookWidget()
    nb.load_json(templates.template_json(templates.solution_preparation))
    code = [c for c in nb.cells if c.CELL_TYPE == "code"][0]
    code.set_source(code.source() + "\nround(float(s['Mass to weigh (g)']"
                    ".iloc[0]), 4)")
    code.execute(nb.kernel)
    assert code.output.text().endswith("1.461")


def test_user_templates_round_trip(qapp, tmp_path):
    from khervebook.notebook import NotebookWidget
    nb = NotebookWidget()
    nb.cells[0].set_source("print('hello')")
    nb.edit_samples(lambda r: r.add(name="A"))
    path = templates.save_user_template("My: XPS/run", nb.to_json(),
                                        tmp_path)
    assert path.name == "My_ XPS_run.kbook"
    assert templates.user_templates(tmp_path) == [("My_ XPS_run", path)]
    doc = json.loads(path.read_text(encoding="utf-8"))
    assert "samples" not in doc                    # samples are not kept
    assert doc["cells"][0]["source"] == "print('hello')"
    assert templates.user_templates(tmp_path / "missing") == []
