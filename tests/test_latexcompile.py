"""Full-LaTeX compilation tests (tectonic + PyMuPDF).

The compile tests skip when tectonic / PyMuPDF are not installed (e.g.
on CI); the display/fallback logic is tested without an engine.

Copyright (C) 2026 Gwilherm Kerherve

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.
"""

import io

import pytest

from khervebook import latexcompile


def _png_bytes():
    import matplotlib
    matplotlib.use("Agg", force=False)
    from matplotlib.figure import Figure
    fig = Figure(figsize=(1, 1))
    fig.add_subplot().plot([0, 1], [0, 1])
    buf = io.BytesIO()
    fig.savefig(buf, format="png")
    return buf.getvalue()


def test_wrap_document_full_passthrough():
    src = r"\documentclass{article}\begin{document}Hi\end{document}"
    assert latexcompile.wrap_document(src) == src


def test_wrap_document_inserts_document_env():
    # \documentclass + body, no \begin{document} (KherveTeX-style paste).
    src = "\\documentclass{article}\n\\usepackage{amsmath}\n\\section{A}\nText."
    out = latexcompile.wrap_document(src)
    assert "\\begin{document}" in out and "\\end{document}" in out
    # The section is in the body, after \begin{document}.
    assert out.index("\\begin{document}") < out.index("\\section{A}")


def test_wrap_document_wraps_fragment():
    out = latexcompile.wrap_document(r"E = mc^2")
    assert "\\documentclass" in out and "E = mc^2" in out


@pytest.mark.skipif(not latexcompile.available(),
                    reason="tectonic / PyMuPDF not installed")
def test_compile_real_document():
    src = (r"\documentclass{article}\usepackage{amsmath}"
           r"\begin{document}"
           r"\section{Test} $\int_0^1 x\,dx = \tfrac12$"
           r"\end{document}")
    pngs, err = latexcompile.compile_to_pngs(src, dpi=120)
    assert err is None
    assert len(pngs) >= 1 and pngs[0][:4] == b"\x89PNG"


def test_compile_reports_error():
    if not latexcompile.available():
        pytest.skip("no engine")
    pngs, err = latexcompile.compile_to_pngs(
        r"\documentclass{article}\begin{document}\undefinedcmd")
    assert not pngs and err               # no PDF, error log returned


def test_latex_cell_shows_compiled_pages(qapp):
    from khervebook.cells import LatexCell
    cell = LatexCell(r"\section{Hi}")
    cell._pending = r"\section{Hi}"
    cell._on_pages(r"\section{Hi}", [_png_bytes(), _png_bytes()])
    assert cell.pages_box.isVisibleTo(cell)
    assert len(cell._page_labels) == 2
    assert not cell.view.isVisibleTo(cell)


def test_latex_cell_stale_compile_ignored(qapp):
    from khervebook.cells import LatexCell
    cell = LatexCell(r"\section{New}")
    cell._pending = r"\section{New}"
    cell._on_pages(r"\section{Old}", [_png_bytes()])   # stale source
    assert not cell._page_labels                        # ignored


def test_latex_cell_compile_error_shown(qapp):
    from khervebook.cells import LatexCell
    cell = LatexCell(r"\section{X}")
    cell._pending = r"\section{X}"
    cell._on_error(r"\section{X}", "! Undefined control sequence.\nl.3 \\foo")
    assert cell.doc_view.isVisibleTo(cell)
    assert "compile error" in cell.doc_view.toPlainText().lower()
