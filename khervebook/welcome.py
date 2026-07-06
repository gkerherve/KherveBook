"""Built-in welcome notebook shown on startup.

Gives a new user a pre-run example of all three cell types so the
first thing they see is what KherveBook does, not an empty window.

Copyright (C) 2026 Gwilherm Kerherve

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.
"""

import json

from .examples import BOIDS_SOURCE

#: A multi-panel matplotlib showcase for the welcome's code cell:
#: line+fill, coloured scatter, a filled contour and a 3D surface —
#: one figure, four plot kinds, using only preloaded numpy/matplotlib.
SHOWCASE_PLOT = r'''# A richer matplotlib figure: four panels, one in 3D
rng = np.random.default_rng(1)
fig = plt.figure(figsize=(9, 6.5))
fig.suptitle("One figure, four kinds of plot", fontsize=14, weight="bold")

# A damped oscillation with its decay envelope
t = np.linspace(0, 12, 500)
env = np.exp(-0.25 * t)
ax1 = fig.add_subplot(2, 2, 1)
ax1.plot(t, env * np.cos(2 * np.pi * 0.7 * t), color="#3776ab")
ax1.fill_between(t, env, -env, color="#3776ab", alpha=0.15)
ax1.set_title("Damped oscillation")
ax1.set_xlabel("t")

# A scatter coloured by distance from the origin, with a colour bar
x, y = rng.normal(size=(2, 400))
ax2 = fig.add_subplot(2, 2, 2)
sc = ax2.scatter(x, y, c=np.hypot(x, y), cmap="plasma", s=20, alpha=0.8)
fig.colorbar(sc, ax=ax2, label="radius")
ax2.set_title("Coloured scatter")

# A filled contour of a 2D field
g = np.linspace(-3, 3, 200)
X, Y = np.meshgrid(g, g)
Z = np.cos(X) * np.sin(Y) * np.exp(-(X**2 + Y**2) / 9)
ax3 = fig.add_subplot(2, 2, 3)
cf = ax3.contourf(X, Y, Z, levels=20, cmap="RdBu_r")
fig.colorbar(cf, ax=ax3)
ax3.set_title("2D field")

# The same field as a 3D surface (coarser grid)
gc = np.linspace(-3, 3, 60)
Xc, Yc = np.meshgrid(gc, gc)
Zc = np.cos(Xc) * np.sin(Yc) * np.exp(-(Xc**2 + Yc**2) / 9)
ax4 = fig.add_subplot(2, 2, 4, projection="3d")
ax4.plot_surface(Xc, Yc, Zc, cmap="viridis", linewidth=0, antialiased=True)
ax4.set_title("Same field in 3D")

fig.tight_layout()
fig'''

#: A small document-style LaTeX cell for the welcome: one unnumbered
#: section and two paragraphs. Compiles with tectonic when available,
#: otherwise the lightweight text renderer shows the same structure.
LATEX_WELCOME_DOC = r"""\documentclass[12pt]{article}
\usepackage{amsmath}
\begin{document}
\section*{Prose, not only equations}
A \textbf{latex cell} is not limited to a single equation: it can hold a
whole document with headings and paragraphs, typeset by the real
\texttt{tectonic} engine, or shown with a lightweight text renderer when
tectonic is not installed. This heading and the two paragraphs below are
one LaTeX cell; \textit{double-click} the rendered page to edit the source.

Unnumbered headings use \texttt{\textbackslash section*}, while plain
\texttt{\textbackslash section} numbers them. Prose wraps automatically and
mixes \textbf{bold}, \textit{italic} and inline mathematics such as
$E = mc^2$ in the line. Press \textbf{Shift+Enter} to re-compile, and open
the \textbf{Examples} menu under \textbf{LaTeX} for numbered equations,
lists and tables.
\end{document}"""

WELCOME_CELLS = [
    {"type": "markdown", "source": (
        '# Welcome to <span style="font-size:28px;color:#3776ab">Kherve'
        '</span><span style="font-size:28px;color:#e07b39">Book</span>\n\n'
        "A computational notebook: one document mixing **runnable Python**, "
        "*formatted text* and LaTeX equations — "
        '<span style="background-color:#fff3a0">not just like Jupyter, but '
        "more</span>: it also embeds live spreadsheets, full typeset LaTeX "
        "documents, drawings, and imported images and PDFs in the same "
        "scrolling page.\n\n"
        "- **Code cells** run Python with `numpy`, `matplotlib`, `pandas` "
        "and `scipy` preloaded (`np`, `plt`, `pd`)\n"
        "- **Markdown cells** hold formatted notes like this one\n"
        "- **LaTeX cells** render equations\n"
        "- **Sheet cells** embed a spreadsheet, two-way linked to Python\n\n"
        "Press **Shift+Enter** to run a cell and move to the next. "
        "Double-click a rendered text cell to edit it again.")},
    {"type": "code", "source": SHOWCASE_PLOT},
    {"type": "markdown", "source": (
        "## LaTeX, typeset properly\n\n"
        "**LaTeX cells** render equations instantly with matplotlib "
        "mathtext — type the maths and run. A few classics (these three "
        "rows are LaTeX cells, two of them sitting side by side):")},
    {"type": "latex", "source":
        r"\int_0^\infty e^{-x^2}\,dx = \frac{\sqrt{\pi}}{2}"},
    {"type": "latex", "source": r"e^{i\pi} + 1 = 0"},
    {"type": "latex", "source":
        r"\sum_{n=1}^{\infty} \frac{1}{n^2} = \frac{\pi^2}{6}",
        "column": True},
    {"type": "latex", "source":
        r"i\hbar\frac{\partial \Psi}{\partial t} = \hat{H}\Psi"},
    {"type": "latex", "source":
        r"\nabla \times \vec{E} = -\frac{\partial \vec{B}}{\partial t}",
        "column": True},
    {"type": "markdown", "source": (
        "And a latex cell isn't limited to one equation — it can typeset a "
        "**whole document**. Here is one with an unnumbered section and two "
        "paragraphs; it compiles with the real `tectonic` engine, or falls "
        "back to a lightweight text renderer when tectonic isn't installed:")},
    {"type": "latex", "source": LATEX_WELCOME_DOC},
    {"type": "markdown", "source": (
        "For a fuller example — numbered equations, lists and tables — see "
        "**Examples → LaTeX → LaTeX Document**. You can also drop a `.tex` "
        "or KherveTeX `.ktex` file straight onto the notebook.")},
    {"type": "markdown", "source": (
        "**Sheet cells** embed a KherveSheet-style spreadsheet with a "
        "formula bar. `=` formulas are Python with A1 refs and `A1:B5` "
        "ranges, and see everything the kernel knows — like "
        "`=np.pi * A2**2` or `=sum(B2:B4)`. After a run the grid is "
        "available to code cells as `sheet1`:")},
    {"type": "sheet", "source": json.dumps({
        "rows": 5, "cols": 3,
        "data": {"A1": "radius", "B1": "area",
                 "A2": "1", "B2": "=np.pi * A2**2",
                 "A3": "2", "B3": "=np.pi * A3**2",
                 "A4": "3", "B4": "=np.pi * A4**2",
                 "A5": "total", "B5": "=sum(B2:B4)"}})},
    {"type": "markdown", "source": (
        "…and the other way round: a **code cell reads that same grid** as "
        "`sheet1`, a list of rows with the header first. Here we pull "
        "columns A (radius) and B (area) straight out of the sheet above "
        "and plot them — edit a number in the grid, re-run, and the plot "
        "follows:")},
    {"type": "code", "source": (
        "# sheet1 is the grid above: row 0 is the header, then the data\n"
        "radius, area = [], []\n"
        "for row in sheet1[1:]:\n"
        "    try:                       # skip the 'total' row\n"
        "        radius.append(float(row[0]))\n"
        "        area.append(float(row[1]))\n"
        "    except ValueError:\n"
        "        continue\n"
        "fig, ax = plt.subplots(figsize=(5, 3.2))\n"
        "ax.bar(radius, area, width=0.5, color='#3776ab', alpha=0.35)\n"
        "ax.plot(radius, area, 'o-', color='#e07b39', lw=2)\n"
        "ax.set_xlabel('radius  (column A)')\n"
        "ax.set_ylabel('area  (column B)')\n"
        "ax.set_title('Sheet columns A and B, plotted in Python')\n"
        "fig")},
    {"type": "markdown", "source": (
        "**Live simulations** — a cell can re-run continuously "
        "(the ⟳ toolbar button, or right-click → *Run Continuously*). "
        "State lives in the kernel between frames. Press the red stop "
        "button next to the play button to pause this flock of birds:")},
    {"type": "code", "source": None},   # boids; filled below
    {"type": "markdown", "source": (
        "## Try it\n\n"
        "Click into any cell and edit it, or add a new one with the "
        "**+** button. The toolbar's second row changes with the cell "
        "type: text formatting for Markdown, run/comment/snippets for "
        "Python, and equation building blocks for LaTeX.\n\n"
        "> **Kernel → Restart** clears all variables and the `In [n]` "
        "counters. **File → Save** stores the notebook as a `.kbook` "
        "file.")},
    {"type": "code", "source": ""},
]
for _cell in WELCOME_CELLS:
    if _cell["source"] is None:
        _cell["source"] = BOIDS_SOURCE


def welcome_json() -> str:
    """The welcome notebook as a .kbook JSON string."""
    return json.dumps({"format": "kbook", "version": 1,
                       "cells": WELCOME_CELLS})


def load_welcome(notebook):
    """Load and pre-run the welcome notebook into *notebook*."""
    notebook.load_json(welcome_json())
    boids = None
    for cell in notebook.cells:
        source = cell.source()
        if source.startswith("# Flocking birds"):
            boids = cell             # started below, not run once
        elif source.strip():
            cell.execute(notebook.kernel)
    if boids is not None:
        notebook.start_loop(boids)
