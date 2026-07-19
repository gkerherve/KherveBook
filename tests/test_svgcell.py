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


def test_svg_cell_tool_api(qapp):
    """The drawing tools live in the CellToolBar and drive the cell's
    set_tool()/current_tool() API."""
    from khervebook.svgcell import SvgCell
    keys = [k for k, _icon, _tip in SvgCell.TOOLS]
    assert keys == ["select", "pen", "line", "rect", "ellipse", "text"]
    cell = SvgCell()
    cell.set_tool("pen")
    assert cell.current_tool() == "pen"


def test_svg_cell_renders_canvas_by_default(qapp):
    """A new svg cell shows a (blank) canvas straight away so it can be
    drawn on without first hitting Render."""
    from khervebook.svgcell import SvgCell
    cell = SvgCell()
    assert not cell.view.isHidden()
    assert "<svg" in cell.source()


def test_svg_cell_grid_snap_and_unit(qapp):
    from khervebook.svgcell import SvgCell
    cell = SvgCell()
    cell.set_show_grid(True)
    cell.set_snap(True)
    cell.set_grid_size(25)
    assert cell.grid_on() and cell.snap_on() and cell.grid_size() == 25


def test_svg_snap_rounds_points_to_grid(qapp):
    from PyQt5.QtCore import QPoint
    from khervebook.svgcell import SvgCell
    cell = SvgCell()
    cell.execute(None)
    surf = cell.view
    surf.resize(800, 500)
    surf.snap = True
    surf.grid_size = 25
    sx, sy = surf._to_svg(QPoint(207, 133))
    assert sx % 25 == 0 and sy % 25 == 0


def test_svg_cell_canvas_resize(qapp):
    from khervebook.svgcell import SvgCell
    cell = SvgCell()          # blank canvas 800x500
    assert cell.canvas_size() == (800, 500)
    cell.set_canvas_size(width=600)
    cell.set_canvas_size(height=400)
    assert cell.canvas_size() == (600, 400)
    assert 'viewBox="0 0 600 400"' in cell.source()
    assert 'width="600"' in cell.source() and 'height="400"' in cell.source()


def test_svg_cell_draws_shape_and_syncs_source(qapp):
    from khervebook.svgcell import SvgCell, STARTER_SVG
    from PyQt5.QtGui import QColor
    cell = SvgCell(STARTER_SVG)
    cell.execute(None)
    surf = cell.view
    surf.tool = "rect"
    surf.color = QColor("#e07b39")
    surf.stroke_width = 4
    surf._commit(surf._shape_element((50, 50), (150, 120)))
    assert "<rect" in surf.source()               # element appended to the SVG
    assert "#e07b39" in surf.source()
    assert "<rect" in cell.source()               # synced back to the editor text
    surf.undo_shape()
    assert "#e07b39" not in surf.source()          # undo removes the last shape


def test_svg_cell_coordinate_round_trip(qapp):
    from khervebook.svgcell import SvgCell, STARTER_SVG
    from PyQt5.QtCore import QPoint
    cell = SvgCell(STARTER_SVG)
    cell.execute(None)
    surf = cell.view
    surf.resize(300, 180)
    px = surf._to_px(150, 90)
    sx, sy = surf._to_svg(QPoint(int(px.x()), int(px.y())))
    assert abs(sx - 150) < 3 and abs(sy - 90) < 3


def test_svg_cell_open_in_paint_is_callable(qapp):
    from khervebook.svgcell import SvgCell
    cell = SvgCell()
    assert hasattr(cell, "open_in_paint") and callable(cell.open_in_paint)
