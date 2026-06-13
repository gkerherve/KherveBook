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

from .examples import BALLS_SOURCE

WELCOME_CELLS = [
    {"type": "markdown", "source": (
        '# Welcome to <span style="font-size:28px;color:#3776ab">Kherve'
        '</span><span style="font-size:28px;color:#e07b39">Book</span>\n\n'
        "A computational notebook: one document mixing **runnable Python**, "
        "*formatted text* and LaTeX equations — "
        '<span style="background-color:#fff3a0">just like Jupyter</span>, '
        "but a native desktop app.\n\n"
        "- **Code cells** run Python with `numpy`, `matplotlib`, `pandas` "
        "and `scipy` preloaded (`np`, `plt`, `pd`)\n"
        "- **Markdown cells** hold formatted notes like this one\n"
        "- **LaTeX cells** render equations\n\n"
        "Press **Shift+Enter** to run a cell and move to the next. "
        "Double-click a rendered text cell to edit it again.")},
    {"type": "code", "source": (
        "x = np.linspace(0, 5, 100)\n"
        "y = x ** 2\n"
        "\n"
        "fig = plt.figure()\n"
        "axes = fig.add_axes([0.1, 0.1, 0.8, 0.8])\n"
        "axes.plot(x, y, 'r')\n"
        "axes.set_xlabel('x')\n"
        "axes.set_ylabel('y')\n"
        "axes.set_title('title')\n"
        "fig")},
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
        "And a whole **LaTeX document** — sections, numbered equations, "
        "tables, figures — compiles with the real `tectonic` engine and "
        "shows the typeset pages. See **Examples → LaTeX → LaTeX "
        "Document**. You can also drop a `.tex` or KherveTeX `.ktex` "
        "file straight onto the notebook.")},
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
        "**Live simulations** — a cell can re-run continuously "
        "(the ⟳ toolbar button, or right-click → *Run Continuously*). "
        "State lives in the kernel between frames. Press the red stop "
        "button next to the play button to pause these bouncing balls:")},
    {"type": "code", "source": None},   # balls; filled below
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
        _cell["source"] = BALLS_SOURCE


def welcome_json() -> str:
    """The welcome notebook as a .kbook JSON string."""
    return json.dumps({"format": "kbook", "version": 1,
                       "cells": WELCOME_CELLS})


def load_welcome(notebook):
    """Load and pre-run the welcome notebook into *notebook*."""
    notebook.load_json(welcome_json())
    balls = None
    for cell in notebook.cells:
        source = cell.source()
        if source.startswith("# Bouncing balls"):
            balls = cell             # started below, not run once
        elif source.strip():
            cell.execute(notebook.kernel)
    if balls is not None:
        notebook.start_loop(balls)
