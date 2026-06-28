"""Code-editor features: line numbers, find-in-cell, thesaurus.

Copyright (C) 2026 Gwilherm Kerherve

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.
"""


def test_code_cell_has_line_numbers(qapp):
    from khervebook.cells import make_cell
    code = make_cell("code", "a = 1\nb = 2\nc = 3")
    assert code.editor._lna is not None
    assert code.editor._lna_width() > 0


def test_prose_cells_have_no_line_numbers(qapp):
    from khervebook.cells import make_cell
    assert make_cell("markdown", "# hi").editor._lna is None
    assert make_cell("latex", "x^2").editor._lna is None


def test_find_bar_selects_and_marks_misses(qapp):
    from khervebook.cells import make_cell
    cell = make_cell("code", "alpha\nbeta\nalpha")
    cell.show_find()
    assert cell._find_bar.isVisibleTo(cell)
    cell._find_bar.edit.setText("alpha")
    cell._find_bar.find(True)
    assert cell.editor.textCursor().selectedText() == "alpha"
    cell._find_bar.edit.setText("zzz")          # no match -> box flags red
    cell._find_bar.find(True)
    assert "ffd6d6" in cell._find_bar.edit.styleSheet()


def test_thesaurus_rejects_non_words_offline():
    from khervebook import thesaurus
    assert thesaurus.synonyms("") == []
    assert thesaurus.synonyms("abc123") == []   # non-alpha: never hits network
    assert thesaurus.synonyms("  ") == []


# -- interactive plots --------------------------------------------------

def test_plot_canvas_wraps_figure(qapp):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    from khervebook.plotcanvas import make_plot_widget
    fig, ax = plt.subplots()
    ax.plot([1, 2, 3], [1, 4, 9])
    w = make_plot_widget(fig)
    assert w.canvas is not None and w.toolbar is not None   # zoom/pan toolbar
    w.close_figure()


def test_code_cell_uses_live_canvas_when_interactive(qapp):
    from khervebook.cells import make_cell
    from khervebook.kernel import Kernel
    k = Kernel()
    k.interactive_figures = True
    cell = make_cell("code", "fig, ax = plt.subplots(); ax.plot([1,2,3]); fig")
    cell.execute(k)
    assert cell._plot_widgets and not cell._figure_labels    # canvas, not PNG
    # turning it off goes back to a PNG label
    k.interactive_figures = False
    cell.execute(k)
    assert cell._figure_labels and not cell._plot_widgets


def test_interactive_off_for_continuous_runs(qapp):
    from khervebook.cells import make_cell
    from khervebook.kernel import Kernel
    k = Kernel()
    k.interactive_figures = True
    cell = make_cell("code", "fig, ax = plt.subplots(); ax.plot([1]); fig")
    cell.set_looping(True)                       # animations stay PNG
    cell.execute(k)
    assert cell._figure_labels and not cell._plot_widgets


# -- JavaScript cells ---------------------------------------------------

def test_js_cell_registered_and_round_trips(qapp):
    from khervebook.jscell import JsCell
    from khervebook.notebook import NotebookWidget
    nb = NotebookWidget()
    nb.add_cell("js", "console.log('hi')")
    assert isinstance(nb.cells[-1], JsCell)
    nb2 = NotebookWidget()
    nb2.load_json(nb.to_json())
    assert nb2.cells[-1].CELL_TYPE == "js"
    assert nb2.cells[-1].source() == "console.log('hi')"


# -- syntax highlighting (svg = XML, js = JavaScript) -------------------

def _highlight_colors(cell):
    """The set of foreground colours the cell's highlighter applies.

    Headless tests must force a pass — without an event loop Qt never
    fires the highlighter's deferred rehighlight (the live app does)."""
    cell._highlighter.rehighlight()
    doc = cell.editor.document()
    colors, blk = set(), doc.firstBlock()
    while blk.isValid():
        for r in blk.layout().formats():
            colors.add(r.format.foreground().color().name())
        blk = blk.next()
    return colors


def test_svg_cell_has_xml_highlighting(qapp):
    from khervebook.svgcell import SvgCell
    from khervebook.cells import XmlHighlighter
    cell = SvgCell('<svg viewBox="0 0 10 10"><!-- note -->'
                   '<rect width="5" height="5" fill="#f00"/></svg>')
    assert isinstance(cell._highlighter, XmlHighlighter)
    colors = _highlight_colors(cell)
    assert "#0000c0" in colors        # tag names / brackets (blue)
    assert "#9a6700" in colors        # attribute names (amber)
    assert "#a31515" in colors        # attribute values (red)
    assert "#808080" in colors        # <!-- comment --> (grey)


def test_js_cell_has_javascript_highlighting(qapp):
    from khervebook.jscell import JsCell
    from khervebook.cells import JsHighlighter
    cell = JsCell("// hi\nconst n = 42;\n/* block\n comment */\n"
                  "function f() { return n; }")
    assert isinstance(cell._highlighter, JsHighlighter)
    colors = _highlight_colors(cell)
    assert "#0000c0" in colors        # keywords (blue)
    assert "#098658" in colors        # number 42 (green)
    assert "#808080" in colors        # // line + /* block */ comments (grey)


def test_js_url_slashes_are_not_a_comment(qapp):
    from khervebook.jscell import JsCell
    cell = JsCell('let u = "http://d3js.org/d3.js";')
    colors = _highlight_colors(cell)
    assert "#a31515" in colors        # the URL is one string (red)
    assert "#808080" not in colors    # the // after ':' is NOT a comment


def test_highlighter_follows_dark_theme(qapp):
    from khervebook.jscell import JsCell
    cell = JsCell("const n = 1;")
    cell._highlighter.set_dark(True)
    assert "#6f9fff" in _highlight_colors(cell)   # dark keyword blue


def test_js_to_html_wrapping():
    from khervebook.jscell import js_to_html
    bare = js_to_html("console.log(1 + 1)")
    assert "<script>" in bare and "kb_out" in bare       # console capture
    snippet = js_to_html("<canvas id='c'></canvas><script>1</script>")
    assert "<canvas" in snippet                          # html kept


def test_js_cell_execute_degrades_without_webengine(qapp):
    # In the headless test app QtWebEngine can't init; the cell must show a
    # hint label instead of crashing.
    from khervebook.cells import make_cell
    cell = make_cell("js", "console.log(1)")
    cell.execute(None)
    assert cell._web is not None or cell._fallback is not None
