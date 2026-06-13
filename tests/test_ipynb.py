"""Jupyter / Colab (.ipynb) import & export tests.

Copyright (C) 2026 Gwilherm Kerherve

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.
"""

import json

from khervebook import ipynb


def test_export_shape_is_valid_ipynb():
    items = [{"type": "code", "source": "x = 1\nx"},
             {"type": "markdown", "source": "# Title"}]
    nb = json.loads(ipynb.to_ipynb(items))
    assert nb["nbformat"] == 4
    assert nb["metadata"]["kernelspec"]["name"] == "python3"
    assert nb["cells"][0]["cell_type"] == "code"
    assert nb["cells"][0]["source"] == ["x = 1\n", "x"]
    assert nb["cells"][1]["cell_type"] == "markdown"


def test_import_jupyter_cells():
    src = json.dumps({"nbformat": 4, "nbformat_minor": 5, "metadata": {},
                      "cells": [
        {"cell_type": "code", "source": ["a = 2\n", "a"], "metadata": {},
         "outputs": [], "execution_count": 3},
        {"cell_type": "markdown", "source": "## Hello", "metadata": {}},
        {"cell_type": "raw", "source": ["verbatim"], "metadata": {}},
    ]})
    items = ipynb.from_ipynb(src)
    assert [i["type"] for i in items] == ["code", "markdown", "markdown"]
    assert items[0]["source"] == "a = 2\na"


def test_round_trip_preserves_all_cell_types_and_props():
    items = [
        {"type": "code", "source": "print(1)", "collapsed": True},
        {"type": "markdown", "source": "**bold**", "title": "Notes"},
        {"type": "latex", "source": r"E = mc^2"},
        {"type": "sheet", "source": json.dumps(
            {"sheets": [{"name": "S", "rows": 2, "cols": 2,
                         "data": {"A1": "1"}}], "active": "S"}),
         "width": 400},
    ]
    back = ipynb.from_ipynb(ipynb.to_ipynb(items))
    assert [i["type"] for i in back] == ["code", "markdown", "latex", "sheet"]
    assert back[0]["collapsed"] is True
    assert back[1]["title"] == "Notes"
    assert back[2]["source"] == r"E = mc^2"
    assert json.loads(back[3]["source"])["sheets"][0]["data"] == {"A1": "1"}
    assert back[3]["width"] == 400


def test_latex_equation_exports_as_math_markdown():
    nb = json.loads(ipynb.to_ipynb([{"type": "latex", "source": r"a^2+b^2"}]))
    body = "".join(nb["cells"][0]["source"])
    assert "$$" in body and "a^2+b^2" in body         # renders in Jupyter
    assert nb["cells"][0]["metadata"]["khervebook"]["type"] == "latex"


def test_load_ipynb_into_notebook(qapp):
    from khervebook.notebook import NotebookWidget
    nb = NotebookWidget()
    text = ipynb.to_ipynb([{"type": "markdown", "source": "# Hi"},
                           {"type": "code", "source": "1 + 1"}])
    nb.load_ipynb(text)
    assert [c.CELL_TYPE for c in nb.cells] == ["markdown", "code"]
    # And the notebook can export itself back out.
    assert "nbformat" in nb.to_ipynb()
