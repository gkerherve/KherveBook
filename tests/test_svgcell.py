"""SVG cell tests: rendering, round-trip, drop and KhervePaint files.

Copyright (C) 2026 Gwilherm Kerherve

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.
"""

_SVG = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 60">'
        '<rect width="100" height="60" fill="#50bea0"/></svg>')


def test_render_svg_returns_pixmap(qapp):
    from khervebook.svgcell import render_svg
    pix = render_svg(_SVG)
    assert pix is not None and not pix.isNull()
    assert render_svg("not an svg at all") is None


def test_svg_cell_executes_and_shows(qapp):
    from khervebook.svgcell import SvgCell
    cell = SvgCell(_SVG)
    cell.execute(None)
    assert cell.view.isVisibleTo(cell)
    assert not cell.editor.isVisibleTo(cell)


def test_svg_cell_registered_and_round_trips(qapp):
    from khervebook.notebook import NotebookWidget
    nb = NotebookWidget()
    nb.add_cell("svg", _SVG)
    assert nb.cells[-1].CELL_TYPE == "svg"
    nb2 = NotebookWidget()
    nb2.load_json(nb.to_json())
    assert nb2.cells[-1].CELL_TYPE == "svg"
    assert nb2.cells[-1].source() == _SVG


def test_drop_svg_file_makes_svg_cell(qapp, tmp_path):
    from khervebook.notebook import NotebookWidget
    nb = NotebookWidget()
    f = tmp_path / "drawing.svg"
    f.write_text(_SVG, encoding="utf-8")
    assert nb.open_file_in_cell(str(f))
    assert nb.current.CELL_TYPE == "svg"
    assert nb.current.view.isVisibleTo(nb)        # rendered on drop
