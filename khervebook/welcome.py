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
    {"type": "latex", "source":
        r"\int_0^\infty e^{-x^2}\,dx = \frac{\sqrt{\pi}}{2}"},
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
    {"type": "code", "source": (
        "# Bouncing balls — runs continuously; stop with the red button\n"
        "if 'balls_pos' not in globals():\n"
        "    _rng = np.random.default_rng(2)\n"
        "    balls_pos = _rng.uniform(0.1, 0.9, (14, 2))\n"
        "    balls_vel = _rng.uniform(-0.025, 0.025, (14, 2))\n"
        "    balls_col = _rng.uniform(0.1, 0.9, (14, 3))\n"
        "balls_pos += balls_vel\n"
        "for _k in (0, 1):\n"
        "    _out = (balls_pos[:, _k] < 0.03) | (balls_pos[:, _k] > 0.97)\n"
        "    balls_vel[_out, _k] *= -1\n"
        "fig, ax = plt.subplots(figsize=(4.2, 4.2))\n"
        "ax.scatter(balls_pos[:, 0], balls_pos[:, 1], s=250, c=balls_col)\n"
        "ax.set_xlim(0, 1); ax.set_ylim(0, 1)\n"
        "ax.set_xticks([]); ax.set_yticks([])\n"
        "fig")},
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
