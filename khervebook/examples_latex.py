"""LaTeX example notebooks for the Examples menu.

A self-contained set of LaTeX cells for KherveBook: several display
equations (rendered instantly by matplotlib mathtext) and a couple of
full LaTeX documents (typeset by the tectonic engine when present, or
shown through the lightweight HTML fallback otherwise). Each builder
returns a list of cell dicts — a markdown heading plus one or more
latex cells — mirroring the structure of ``examples.py`` and
``sheet_examples.py`` without importing their private helpers.

Copyright (C) 2026 Gwilherm Kerherve

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.
"""


def _md(t):
    return {"type": "markdown", "source": t}


def _tex(t):
    return {"type": "latex", "source": t}


# -- Equation sets ----------------------------------------------------------
# Each source is a single display equation as a bare string (no $ and no
# \[ \] delimiters) so the latex cell renders it with matplotlib mathtext.

def _maxwell_equations():
    return [
        _md("# Maxwell's Equations\nThe four equations of classical "
            "electromagnetism, in differential form (SI units). Each "
            "**latex cell** renders a single display equation instantly "
            "with matplotlib mathtext — double-click a rendered equation "
            "to edit its source, then run (Shift+Enter)."),
        _tex(r"\nabla \cdot \vec{E} = \frac{\rho}{\varepsilon_0}"),
        _tex(r"\nabla \cdot \vec{B} = 0"),
        _tex(r"\nabla \times \vec{E} = "
             r"-\frac{\partial \vec{B}}{\partial t}"),
        _tex(r"\nabla \times \vec{B} = \mu_0 \vec{J} "
             r"+ \mu_0 \varepsilon_0 \frac{\partial \vec{E}}{\partial t}"),
    ]


def _schrodinger():
    return [
        _md("# The Schrödinger Equation\nThe time-dependent Schrödinger "
            "equation governs how a quantum state evolves, alongside its "
            "time-independent eigenvalue form."),
        _tex(r"i\hbar\frac{\partial}{\partial t}\Psi = "
             r"-\frac{\hbar^2}{2m}\nabla^2\Psi + V\Psi"),
        _tex(r"\hat{H}\psi = E\psi"),
    ]


def _famous_identities():
    return [
        _md("# Three Famous Results\nEuler's identity ties together five "
            "fundamental constants; Einstein's mass-energy relation; and "
            "the Gaussian integral, a cornerstone of probability and "
            "statistical mechanics."),
        _tex(r"e^{i\pi} + 1 = 0"),
        _tex(r"E^2 = (pc)^2 + (m c^2)^2"),
        _tex(r"\int_{-\infty}^{\infty} e^{-x^2}\, dx = \sqrt{\pi}"),
    ]


def _fourier_transform():
    return [
        _md("# Fourier & Taylor\nThe continuous Fourier transform "
            "decomposes a signal into frequencies, and the Taylor series "
            "expands a smooth function as a power series about a point."),
        _tex(r"\hat{f}(\xi) = \int_{-\infty}^{\infty} f(x)\, "
             r"e^{-2\pi i x \xi}\, dx"),
        _tex(r"f(x) = \sum_{n=0}^{\infty} "
             r"\frac{f^{(n)}(a)}{n!}(x-a)^n"),
    ]


def _fluid_dynamics():
    return [
        _md("# Fluid Dynamics\nThe Navier-Stokes momentum equation for an "
            "incompressible viscous fluid, with the continuity equation "
            "expressing conservation of mass."),
        _tex(r"\rho\left(\frac{\partial \vec{u}}{\partial t} "
             r"+ \vec{u}\cdot\nabla\vec{u}\right) = "
             r"-\nabla p + \mu \nabla^2 \vec{u} + \vec{f}"),
        _tex(r"\frac{\partial \rho}{\partial t} "
             r"+ \nabla \cdot (\rho \vec{u}) = 0"),
    ]


def _probability():
    return [
        _md("# Probability & Inequalities\nBayes' theorem updates a "
            "belief in light of evidence; the Cauchy-Schwarz inequality "
            "bounds an inner product by the product of norms."),
        _tex(r"P(A \mid B) = "
             r"\frac{P(B \mid A)\, P(A)}{P(B)}"),
        _tex(r"\left| \langle x, y \rangle \right| "
             r"\leq \|x\|\, \|y\|"),
    ]


# -- Document examples ------------------------------------------------------
# Full \documentclass...\end{document} sources. With tectonic installed
# these typeset properly; without it the latex cell renders them through
# the offline HTML fallback (latextext.latex_to_html), which handles
# sections, text formatting and inline $...$ math — so these avoid
# displayed \[ \] and align environments.

INTRO_DOC = r"""\documentclass[12pt]{article}
\usepackage{amsmath, amssymb}
\title{\textbf{Writing with LaTeX cells}}
\author{KherveBook}
\date{}
\begin{document}
\maketitle

\section*{What a document cell does}
A \textbf{latex cell} that holds a full document --- one that begins
with \texttt{documentclass} and \texttt{begin document} --- is typeset
by the LaTeX engine and shown as finished pages. Without the engine
installed, KherveBook falls back to a lightweight reader that still
formats the prose. Double-click the rendered view to edit the source,
then run with Shift+Enter to refresh.

\section*{Formatting prose}
Text can be \textbf{bold}, \textit{italic}, \underline{underlined} or
\texttt{monospaced}. Use \texttt{section*} for unnumbered headings like
these, or \texttt{section} when you want them numbered. Inline
mathematics sits between dollar signs: the area of a circle is
$A = \pi r^2$, energy and mass relate through $E = mc^2$, and a wave
has frequency $f = 1 / T$.

\section*{When to reach for it}
Use document cells for explanatory write-ups, derivations and notes
that mix headings, paragraphs and a little inline math --- the prose
companions to your code and equation cells.
\end{document}"""


def _latex_intro_document():
    return [
        _md("# LaTeX Document — Intro\nA **latex cell** can hold a whole "
            "LaTeX document, not just one equation. With the `tectonic` "
            "engine it typesets real pages; otherwise it falls back to a "
            "formatted text view. Double-click the rendered page to edit "
            "the source."),
        _tex(INTRO_DOC),
    ]


PHYSICS_DOC = r"""\documentclass[12pt]{article}
\usepackage{amsmath, amssymb}
\title{\textbf{A page of physics}}
\author{KherveBook}
\date{}
\begin{document}
\maketitle

\section*{Mechanics}
Newton's second law states that force equals the rate of change of
momentum, $F = m a$ for constant mass. The kinetic energy of a body is
$E_k = \frac{1}{2} m v^2$, and the period of a simple pendulum grows
with its length $L$ as $T = 2\pi \sqrt{L / g}$.

\section*{Thermodynamics}
For an ideal gas the state variables obey $p V = n R T$. Entropy and
the number of microstates are linked by Boltzmann's relation
$S = k_B \ln \Omega$, one of the deepest results in physics.

\section*{Relativity}
A moving clock runs slow by the Lorentz factor $\gamma$, and the total
energy of a particle is $E = \gamma m c^2$. In the rest frame this
reduces to the famous $E = mc^2$.

\section*{Closing note}
Each paragraph above mixes \textbf{prose} with inline math such as
$\hbar$, $\nabla$ and $\int$ --- exactly what a document-style latex
cell is for.
\end{document}"""


def _physics_notes_document():
    return [
        _md("# LaTeX Document — Physics Notes\nA longer **latex "
            "document** mixing prose and inline `$...$` math across "
            "several sections. It typesets with `tectonic` when "
            "available, and reads cleanly through the offline fallback "
            "otherwise."),
        _tex(PHYSICS_DOC),
    ]


# -- Registry ---------------------------------------------------------------

LATEX_EXAMPLES = [
    # (name, category, builder)
    ("Maxwell's Equations",     "LaTeX", _maxwell_equations),
    ("Schrödinger Equation",    "LaTeX", _schrodinger),
    ("Famous Identities",       "LaTeX", _famous_identities),
    ("Fourier & Taylor",        "LaTeX", _fourier_transform),
    ("Fluid Dynamics",          "LaTeX", _fluid_dynamics),
    ("Probability & Bounds",    "LaTeX", _probability),
    ("LaTeX Doc — Intro",       "LaTeX", _latex_intro_document),
    ("LaTeX Doc — Physics",     "LaTeX", _physics_notes_document),
]
