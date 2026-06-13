"""LaTeX-document rendering tests.

Copyright (C) 2026 Gwilherm Kerherve

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.
"""

from khervebook.latextext import is_document, latex_to_html


def test_is_document_vs_equation():
    assert is_document(r"\section{Intro} Hello \textbf{world}")
    assert not is_document(r"E = mc^2")
    assert not is_document(r"\int_0^\infty e^{-x^2}\,dx = \frac{\sqrt\pi}{2}")


def test_converter_maps_common_commands():
    html = latex_to_html(
        r"\documentclass{article}" "\n"
        r"\section{Title}" "\n\n"
        r"Make it \textbf{bold}, \textit{italic}, \underline{u}, "
        r"\texttt{code}, H\textsubscript{2}O, x\textsuperscript{2}.")
    assert "<h2>Title</h2>" in html
    assert "<b>bold</b>" in html and "<i>italic</i>" in html
    assert "<u>u</u>" in html and "<code>code</code>" in html
    assert "<sub>2</sub>" in html and "<sup>2</sup>" in html
    assert "documentclass" not in html        # preamble dropped


def test_latex_cell_renders_document(qapp):
    from khervebook.kernel import Kernel
    from khervebook.cells import LatexCell
    cell = LatexCell(r"\section{Hi}" "\n\n" r"A \textbf{bold} word.")
    cell.execute(Kernel())
    assert cell.doc_view.isVisibleTo(cell)     # document view shown
    assert not cell.view.isVisibleTo(cell)     # not the math image
    assert "bold" in cell.doc_view.toPlainText()


def test_latex_cell_renders_equation(qapp):
    from khervebook.kernel import Kernel
    from khervebook.cells import LatexCell
    cell = LatexCell(r"E = mc^2")
    cell.execute(Kernel())
    assert cell.view.isVisibleTo(cell)         # math image shown
    assert not cell.doc_view.isVisibleTo(cell)
    assert cell.view.pixmap() is not None
