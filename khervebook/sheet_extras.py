"""Enrichment assets for the ported KherveSheet examples.

Every sheet example in ``sheet_examples.py`` is grown from a bare
"markdown + sheet" pair into a small multi-cell document. This module
supplies the three extra ingredients so that file stays near the
1500-line budget:

* ``GENERIC_PLOT`` — a robust auto-chart that reads the live ``sheet1``
  grid and bars/lines its numeric columns (used when an example has no
  hand-written chart). It never raises, so it is safe in every example.
* ``DRAWINGS`` / ``drawing_for`` — a small library of flat, static SVG
  icons (rendered by the svg cell's ``QSvgRenderer``) themed by topic
  and category, so each example also carries a relevant drawing.
* ``FORMULAS`` / ``formula_for`` — the governing equation for examples
  that have one, shown in a latex cell (mathtext-safe for the no-tectonic
  fallback).

Copyright (C) 2026 Gwilherm Kerherve

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.
"""


# -- generic auto-chart -----------------------------------------------------

#: Drawn for an example that has no bespoke chart. Reads the published
#: ``sheet1`` grid, finds the numeric columns and bars (few rows) or lines
#: (many rows) them. Every parse is guarded, so it cannot raise. ``__TITLE__``
#: is substituted with the example name when the cell is built.
GENERIC_PLOT = r'''
# Auto-chart of the sheet's numeric columns (reads the live sheet1 grid).
import numpy as np
import matplotlib.pyplot as plt

grid = [list(r) for r in sheet1]
hdr = grid[0] if grid else []
rows = grid[1:] if len(grid) > 1 else []
while rows and all(c in (None, "") for c in rows[-1]):   # drop blank padding
    rows.pop()
ncol = max((len(r) for r in grid), default=0)


def _col(j):
    out = []
    for r in rows:
        try:
            out.append(float(str(r[j]).replace(",", "")))
        except Exception:
            out.append(np.nan)
    return np.array(out, dtype=float)


num = [j for j in range(ncol)
       if np.isfinite(_col(j)).sum() >= max(2, 0.4 * len(rows))]
label_j = next((j for j in range(ncol) if j not in num), None)
series = [j for j in num if j != label_j][:3] or num[:3]

fig, ax = plt.subplots(figsize=(6, 4))
if not series:
    ax.text(0.5, 0.5, "no numeric columns to chart",
            ha="center", va="center", color="0.5")
    ax.axis("off")
elif label_j is not None and len(rows) <= 16:
    labels = [str(r[label_j]) for r in rows]
    x = np.arange(len(rows))
    w = 0.8 / len(series)
    for k, j in enumerate(series):
        ax.bar(x + k * w, np.nan_to_num(_col(j)), w,
               label=str(hdr[j]) if j < len(hdr) else "")
    ax.set_xticks(x + 0.4 - w / 2)
    ax.set_xticklabels(labels, rotation=45, ha="right", fontsize=8)
    if len(series) > 1:
        ax.legend(fontsize=8)
elif label_j is None and len(series) == 1:
    ax.plot(np.arange(len(rows)), _col(series[0]), color="#3776ab")
else:
    xj = None if label_j is not None else series[0]
    ys = [j for j in series if j != xj]
    xv = np.arange(len(rows)) if xj is None else _col(xj)
    for j in ys:
        ax.plot(xv, _col(j), label=str(hdr[j]) if j < len(hdr) else "")
    if xj is not None and xj < len(hdr):
        ax.set_xlabel(str(hdr[xj]))
    ax.legend(fontsize=8)
if series:
    ax.set_title("__TITLE__")
    ax.grid(True, alpha=0.3)
fig.tight_layout()
fig
'''

#: Examples whose data is essentially text — a chart would be noise.
NO_PLOT = {"Password Generator", "Todo List", "ASCII Table"}


def generic_plot(name: str) -> str:
    """The auto-chart code with the example's name as the plot title."""
    return GENERIC_PLOT.replace("__TITLE__", str(name).replace('"', "'"))


# -- SVG drawings -----------------------------------------------------------

def _card(inner: str, w: int = 240, h: int = 150) -> str:
    return (f'<svg xmlns="http://www.w3.org/2000/svg" '
            f'viewBox="0 0 {w} {h}" width="{w}" height="{h}">'
            f'<rect width="{w}" height="{h}" rx="12" fill="#f4f7fb"/>'
            f'{inner}</svg>')


DRAWINGS = {
    "coins": _card(
        '<g stroke="#2b6cb0" stroke-width="2">'
        '<ellipse cx="80" cy="112" rx="46" ry="15" fill="#3776ab"/>'
        '<ellipse cx="80" cy="92" rx="46" ry="15" fill="#4a8fd0"/>'
        '<ellipse cx="80" cy="72" rx="46" ry="15" fill="#5fa0dd"/></g>'
        '<g fill="none" stroke="#e07b39" stroke-width="7" '
        'stroke-linecap="round" stroke-linejoin="round">'
        '<path d="M158 118 V52"/><path d="M136 74 L158 50 L180 74"/></g>'),
    "cap": _card(
        '<polygon points="120,42 202,74 120,106 38,74" fill="#3776ab"/>'
        '<path d="M72 90 V120 Q120 142 168 120 V90" fill="none" '
        'stroke="#3776ab" stroke-width="7"/>'
        '<line x1="202" y1="74" x2="202" y2="116" stroke="#e07b39" '
        'stroke-width="3"/><circle cx="202" cy="120" r="7" fill="#e07b39"/>'),
    "sigma": _card(
        '<polyline points="156,42 64,42 110,90 64,138 156,138" fill="none" '
        'stroke="#3776ab" stroke-width="10" stroke-linejoin="round" '
        'stroke-linecap="round"/>'
        '<polyline points="120,124 150,78 178,104 208,58" fill="none" '
        'stroke="#e07b39" stroke-width="4" stroke-linecap="round"/>'),
    "atom": _card(
        '<g fill="none" stroke="#3776ab" stroke-width="3">'
        '<ellipse cx="120" cy="75" rx="72" ry="28"/>'
        '<ellipse cx="120" cy="75" rx="72" ry="28" '
        'transform="rotate(60 120 75)"/>'
        '<ellipse cx="120" cy="75" rx="72" ry="28" '
        'transform="rotate(120 120 75)"/></g>'
        '<circle cx="120" cy="75" r="11" fill="#e07b39"/>'
        '<circle cx="192" cy="75" r="5" fill="#3776ab"/>'),
    "bars": _card(
        '<g fill="#3776ab"><rect x="48" y="100" width="26" height="30"/>'
        '<rect x="84" y="80" width="26" height="50"/>'
        '<rect x="120" y="58" width="26" height="72"/>'
        '<rect x="156" y="40" width="26" height="90"/></g>'
        '<polyline points="61,95 97,75 133,53 169,35" fill="none" '
        'stroke="#e07b39" stroke-width="3"/>'
        '<line x1="40" y1="130" x2="198" y2="130" stroke="#2e3440" '
        'stroke-width="2"/>'),
    "house": _card(
        '<polygon points="120,38 46,96 194,96" fill="#e07b39"/>'
        '<rect x="66" y="96" width="108" height="54" fill="#3776ab"/>'
        '<rect x="104" y="116" width="32" height="34" fill="#f4f7fb"/>'),
    "globe": _card(
        '<circle cx="120" cy="75" r="56" fill="#3776ab"/>'
        '<g fill="none" stroke="#cfe3f6" stroke-width="2">'
        '<ellipse cx="120" cy="75" rx="23" ry="56"/>'
        '<ellipse cx="120" cy="75" rx="46" ry="56"/>'
        '<line x1="64" y1="75" x2="176" y2="75"/>'
        '<path d="M74 44 H166 M74 106 H166"/></g>'),
    "news": _card(
        '<rect x="52" y="52" width="112" height="78" rx="6" fill="#3776ab"/>'
        '<rect x="62" y="62" width="46" height="32" fill="#f4f7fb"/>'
        '<g stroke="#f4f7fb" stroke-width="5" stroke-linecap="round">'
        '<line x1="116" y1="68" x2="154" y2="68"/>'
        '<line x1="116" y1="84" x2="154" y2="84"/></g>'
        '<g fill="none" stroke="#e07b39" stroke-width="4" '
        'stroke-linecap="round"><path d="M172 58 a18 18 0 0 1 18 18"/>'
        '<path d="M172 46 a30 30 0 0 1 30 30"/></g>'),
    "wave": _card(
        '<line x1="30" y1="75" x2="212" y2="75" stroke="#2e3440" '
        'stroke-width="2"/><line x1="42" y1="28" x2="42" y2="122" '
        'stroke="#2e3440" stroke-width="2"/>'
        '<path d="M42 75 C 58 24 88 24 104 75 S 150 126 166 75 S 212 24 '
        '226 75" fill="none" stroke="#3776ab" stroke-width="4"/>'),
    "parabola": _card(
        '<line x1="30" y1="125" x2="214" y2="125" stroke="#2e3440" '
        'stroke-width="2"/><line x1="42" y1="28" x2="42" y2="130" '
        'stroke="#2e3440" stroke-width="2"/>'
        '<path d="M48 120 Q120 6 206 120" fill="none" stroke="#e07b39" '
        'stroke-width="4"/>'),
    "flask": _card(
        '<path d="M106 42 V76 L74 122 Q70 134 86 134 H154 Q170 134 166 122 '
        'L134 76 V42" fill="#cfe3f6" stroke="#3776ab" stroke-width="3"/>'
        '<path d="M92 102 H148 L166 122 Q170 134 154 134 H86 Q70 134 74 122 '
        'Z" fill="#e07b39" opacity="0.85"/>'
        '<rect x="100" y="36" width="40" height="9" rx="3" fill="#3776ab"/>'),
    "heart": _card(
        '<path d="M120 132 L72 86 Q50 64 72 50 Q94 38 120 66 Q146 38 168 50 '
        'Q190 64 168 86 Z" fill="#e07b39"/>'
        '<polyline points="58,100 94,100 110,74 126,122 142,100 182,100" '
        'fill="none" stroke="#3776ab" stroke-width="4" '
        'stroke-linejoin="round"/>'),
}

#: Per-example drawing overrides (more specific than the category default).
_TOPIC = {
    "Sine / Cosine Table": "wave",
    "Projectile Table": "parabola",
    "Quadratic Solver": "parabola",
    "Periodic Table": "atom",
    "Chemistry Solutions": "flask",
    "BMI Calculator": "heart",
    "Blood Pressure Log": "heart",
    "Calorie Tracker": "heart",
    "Workout Log": "heart",
    "World Population": "globe",
    "Time Zones": "globe",
    "Distance Matrix": "globe",
    "Sales Dashboard": "bars",
    "Survey Results": "bars",
}

#: Fallback drawing per example category.
_CATEGORY = {
    "Finance": "coins", "Education": "cap", "Math": "sigma",
    "Science": "atom", "Business": "bars", "Daily Life": "house",
    "Reference": "globe", "Live Data": "news",
}


def drawing_for(name: str, category: str) -> str:
    """The SVG source of the most fitting drawing for an example."""
    key = _TOPIC.get(name) or _CATEGORY.get(category, "sigma")
    return DRAWINGS[key]


# -- governing equations (latex cell, mathtext-safe) ------------------------

FORMULAS = {
    "Compound Interest": r"A = P\,(1 + r)^{t}",
    "Mortgage Amortization":
        r"M = P\,\frac{r\,(1+r)^{n}}{(1+r)^{n} - 1}",
    "Loan Comparison":
        r"M = P\,\frac{r\,(1+r)^{n}}{(1+r)^{n} - 1}",
    "Periodic Payments":
        r"FV = P\,\frac{(1+r)^{n} - 1}{r}",
    "Stock Portfolio": r"V = \sum_{i} q_i\,p_i",
    "Tip Calculator": r"T = B \times \frac{p}{100}",
    "Fibonacci Sequence":
        r"F_n = F_{n-1} + F_{n-2}, \quad \frac{F_n}{F_{n-1}} \to \varphi",
    "Sine / Cosine Table": r"\sin^{2}\theta + \cos^{2}\theta = 1",
    "Quadratic Solver": r"x = \frac{-b \pm \sqrt{b^{2} - 4ac}}{2a}",
    "Exponential Growth": r"N(t) = N_0\,e^{k t}",
    "Matrix A + B": r"(A + B)_{ij} = A_{ij} + B_{ij}",
    "Statistics Sample":
        r"\bar{x} = \frac{1}{n}\sum_{i=1}^{n} x_i, \quad "
        r"\sigma^{2} = \frac{1}{n}\sum_{i}(x_i - \bar{x})^{2}",
    "Regression Data": r"y = m\,x + b",
    "Projectile Table":
        r"x = v_0\cos\theta\,t, \quad y = v_0\sin\theta\,t - \frac{1}{2}g t^{2}",
    "Temperature Conversion":
        r"F = \frac{9}{5}\,C + 32, \quad K = C + 273.15",
    "BMI Calculator": r"\mathrm{BMI} = \frac{m}{h^{2}}",
    "Chemistry Solutions": r"c = \frac{n}{V}",
    "Soccer League Table": r"\mathrm{Pts} = 3W + D",
}


def formula_for(name: str):
    """The latex body for an example's governing equation, or ``None``."""
    return FORMULAS.get(name)
