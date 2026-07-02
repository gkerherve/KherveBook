"""Built-in example notebooks (Examples menu), like KherveSheet's.

Each example is a builder returning a list of cell dicts. Loading
replaces the current notebook and runs every cell; a code cell whose
first line contains "runs continuously" is started as a live loop
instead of run once.

Copyright (C) 2026 Gwilherm Kerherve

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.
"""

import json
import re

LIVE_MARK = "runs continuously"

#: Source of the bouncing-balls live demo (shared with the welcome).
BALLS_SOURCE = (
    "# Bouncing balls — runs continuously; stop with the red button\n"
    "if 'balls_pos' not in globals():\n"
    "    _rng = np.random.default_rng(2)\n"
    "    balls_pos = _rng.uniform(0.1, 0.9, (14, 2))\n"
    "    balls_vel = _rng.uniform(-0.025, 0.025, (14, 2))\n"
    "    balls_col = _rng.uniform(0.1, 0.9, (14, 3))\n"
    "    BALL_R = 0.037\n"
    "balls_pos += balls_vel\n"
    "for _k in (0, 1):   # bounce off the walls\n"
    "    _out = ((balls_pos[:, _k] < BALL_R)\n"
    "            | (balls_pos[:, _k] > 1 - BALL_R))\n"
    "    balls_vel[_out, _k] *= -1\n"
    "for _i in range(len(balls_pos)):   # elastic ball-ball collisions\n"
    "    for _j in range(_i + 1, len(balls_pos)):\n"
    "        _d = balls_pos[_i] - balls_pos[_j]\n"
    "        _r2 = _d @ _d\n"
    "        if 0 < _r2 < (2 * BALL_R) ** 2:\n"
    "            _p = ((balls_vel[_i] - balls_vel[_j]) @ _d) / _r2\n"
    "            if _p < 0:   # only if approaching\n"
    "                balls_vel[_i] -= _p * _d\n"
    "                balls_vel[_j] += _p * _d\n"
    "fig, ax = plt.subplots(figsize=(4.2, 4.2))\n"
    "ax.scatter(balls_pos[:, 0], balls_pos[:, 1], s=250, c=balls_col)\n"
    "ax.set_xlim(0, 1); ax.set_ylim(0, 1)\n"
    "ax.set_xticks([]); ax.set_yticks([])\n"
    "fig")

#: Source of the flocking-birds (boids) live demo (shared with the welcome).
BOIDS_SOURCE = (
    "# Flocking birds (boids) — runs continuously; stop with the red button\n"
    "if 'birds_pos' not in globals():\n"
    "    _rng = np.random.default_rng(4)\n"
    "    birds_pos = _rng.uniform(0.25, 0.75, (28, 2))\n"
    "    _a = _rng.uniform(0, 2 * np.pi, 28)\n"
    "    birds_vel = 0.011 * np.c_[np.cos(_a), np.sin(_a)]\n"
    "_off = birds_pos[:, None] - birds_pos[None, :]   # pairwise offsets\n"
    "_d2 = (_off ** 2).sum(-1)\n"
    "np.fill_diagonal(_d2, np.inf)\n"
    "_nb = (_d2 < 0.15 ** 2)[..., None]               # neighbours\n"
    "_n = np.maximum(_nb.sum(1), 1)\n"
    "_sep = (_off / _d2[..., None] * (_d2 < 0.05 ** 2)[..., None]).sum(1)\n"
    "_ali = (birds_vel[None] * _nb).sum(1) / _n - birds_vel\n"
    "_coh = (birds_pos[None] * _nb).sum(1) / _n - birds_pos\n"
    "birds_vel += 1e-4 * _sep + 0.05 * _ali + 0.006 * _coh\n"
    "birds_vel += 0.004 * (0.5 - birds_pos)   # wheel about the centre\n"
    "_sp = np.hypot(*birds_vel.T)[:, None]\n"
    "birds_vel *= np.clip(_sp, 0.009, 0.013) / _sp   # keep them flying\n"
    "birds_pos = np.clip(birds_pos + birds_vel, 0.03, 0.97)\n"
    "_u = birds_vel / np.hypot(*birds_vel.T)[:, None]   # unit headings\n"
    "_w = np.c_[-_u[:, 1], _u[:, 0]]                    # wing direction\n"
    "_tri = np.stack([birds_pos + 0.030 * _u,           # beak\n"
    "                 birds_pos - 0.018 * _u + 0.013 * _w,\n"
    "                 birds_pos - 0.018 * _u - 0.013 * _w], axis=1)\n"
    "from matplotlib.collections import PolyCollection\n"
    "fig, ax = plt.subplots(figsize=(4.2, 4.2))\n"
    "ax.add_collection(PolyCollection(_tri, facecolors='#3776ab',\n"
    "                                 edgecolors='none'))\n"
    "ax.set_xlim(0, 1); ax.set_ylim(0, 1)\n"
    "ax.set_xticks([]); ax.set_yticks([])\n"
    "ax.set_aspect('equal')\n"
    "fig")


def _md(text):
    return {"type": "markdown", "source": text}


def _code(text):
    return {"type": "code", "source": text}


def _tex(text):
    return {"type": "latex", "source": text}


# -- Math -----------------------------------------------------------------

def _fft():
    return [
        _md("# FFT Spectrum\nA 50 Hz + 120 Hz signal buried in noise, "
            "recovered with `np.fft.rfft`."),
        _code(
            "fs = 1000                      # sampling rate (Hz)\n"
            "t = np.arange(0, 1, 1 / fs)\n"
            "sig = (np.sin(2 * np.pi * 50 * t)\n"
            "       + 0.5 * np.sin(2 * np.pi * 120 * t)\n"
            "       + 0.8 * np.random.default_rng(0).normal(size=t.size))\n"
            "freq = np.fft.rfftfreq(t.size, 1 / fs)\n"
            "mag = np.abs(np.fft.rfft(sig)) / t.size\n"
            "fig, (a1, a2) = plt.subplots(2, 1, figsize=(6, 4.5))\n"
            "a1.plot(t[:200], sig[:200]); a1.set_title('signal')\n"
            "a2.plot(freq, mag); a2.set_title('spectrum')\n"
            "a2.set_xlabel('Hz'); fig.tight_layout()\n"
            "fig"),
    ]


def _sympy():
    return [
        _md("# Symbolic Calculus\n`sympy` is preloaded — differentiate "
            "and integrate symbolically."),
        _code(
            "x = sympy.symbols('x')\n"
            "expr = sympy.sin(x) * sympy.exp(-x)\n"
            "print('d/dx :', sympy.diff(expr, x))\n"
            "print('∫dx  :', sympy.integrate(expr, x))\n"
            "sympy.integrate(expr, (x, 0, sympy.oo))"),
        _tex(r"\int_0^\infty \sin(x)\,e^{-x}\,dx = \frac{1}{2}"),
    ]


def _matrices():
    return [
        _md("# Matrix Operations\nEigenvalues, inverse and a linear "
            "solve with `np.linalg`."),
        _code(
            "A = np.array([[4., 2., 0.], [2., 5., 1.], [0., 1., 3.]])\n"
            "b = np.array([2., 1., 4.])\n"
            "print('det  =', np.linalg.det(A).round(3))\n"
            "print('eig  =', np.linalg.eigvalsh(A).round(3))\n"
            "print('x    =', np.linalg.solve(A, b).round(3))\n"
            "np.linalg.inv(A).round(3)"),
    ]


# -- Science --------------------------------------------------------------

def _curve_fit():
    return [
        _md("# Curve Fitting with lmfit\nFit a Gaussian to noisy data "
            "and report the parameters."),
        _code(
            "from lmfit.models import GaussianModel\n"
            "rng = np.random.default_rng(1)\n"
            "x = np.linspace(-5, 5, 120)\n"
            "y = 4.2 * np.exp(-(x - 0.8)**2 / 1.8) + rng.normal(0, 0.2,"
            " x.size)\n"
            "model = GaussianModel()\n"
            "fit = model.fit(y, model.guess(y, x=x), x=x)\n"
            "print(fit.fit_report(show_correl=False))\n"
            "fig, ax = plt.subplots()\n"
            "ax.plot(x, y, 'o', ms=4, label='data')\n"
            "ax.plot(x, fit.best_fit, 'r-', label='fit')\n"
            "ax.legend()\n"
            "fig"),
    ]


def _oscillator():
    return [
        _md("# Damped Oscillator\nIntegrating the equation of motion "
            "with `scipy.integrate.solve_ivp`:"),
        _tex(r"\ddot{x} + 2\zeta\omega_0\,\dot{x} + \omega_0^2\,x = 0"),
        _code(
            "from scipy.integrate import solve_ivp\n"
            "w0, zeta = 2 * np.pi, 0.1\n"
            "def rhs(t, s):\n"
            "    x, v = s\n"
            "    return [v, -2 * zeta * w0 * v - w0**2 * x]\n"
            "sol = solve_ivp(rhs, [0, 5], [1, 0], dense_output=True)\n"
            "t = np.linspace(0, 5, 400)\n"
            "fig, ax = plt.subplots()\n"
            "ax.plot(t, sol.sol(t)[0])\n"
            "ax.set_xlabel('t (s)'); ax.set_ylabel('x')\n"
            "ax.grid(True)\n"
            "fig"),
    ]


def _projectile():
    return [
        _md("# Projectile Motion\nRange depends on launch angle:"),
        _tex(r"x(t) = v_0\cos\theta\, t \quad\quad "
             r"y(t) = v_0\sin\theta\, t - \frac{1}{2} g t^2"),
        _code(
            "v0, g = 20.0, 9.81\n"
            "fig, ax = plt.subplots()\n"
            "for deg in (15, 30, 45, 60, 75):\n"
            "    th = np.radians(deg)\n"
            "    tf = 2 * v0 * np.sin(th) / g\n"
            "    t = np.linspace(0, tf, 100)\n"
            "    ax.plot(v0 * np.cos(th) * t,\n"
            "            v0 * np.sin(th) * t - g * t**2 / 2,\n"
            "            label=f'{deg}°')\n"
            "ax.set_xlabel('x (m)'); ax.set_ylabel('y (m)')\n"
            "ax.legend(); ax.set_ylim(bottom=0)\n"
            "fig"),
    ]


# -- Data -----------------------------------------------------------------

def _pandas():
    return [
        _md("# Pandas Quickstart\n`pd` is preloaded; the trailing "
            "DataFrame echoes like in Jupyter."),
        _code(
            "df = pd.DataFrame({\n"
            "    'element': ['C', 'N', 'O', 'Si', 'Fe'],\n"
            "    'Z': [6, 7, 8, 14, 26],\n"
            "    'mass': [12.011, 14.007, 15.999, 28.085, 55.845],\n"
            "})\n"
            "df['mass/Z'] = (df['mass'] / df['Z']).round(3)\n"
            "print(df.describe().round(2))\n"
            "df"),
        _code(
            "fig, ax = plt.subplots()\n"
            "ax.bar(df['element'], df['mass'])\n"
            "ax.set_ylabel('atomic mass')\n"
            "fig"),
    ]


def _sheet_python():
    return [
        _md("# Sheet ↔ Python\nThe grid computes `=` formulas, then "
            "publishes itself to code cells as `sheet1`."),
        {"type": "sheet", "source": json.dumps({
            "rows": 5, "cols": 2,
            "data": {"A1": "1", "B1": "=A1**2",
                     "A2": "2", "B2": "=A2**2",
                     "A3": "3", "B3": "=A3**2",
                     "A4": "4", "B4": "=A4**2",
                     "A5": "5", "B5": "=A5**2"}})},
        _code(
            "data = np.array(sheet1, dtype=float)\n"
            "fig, ax = plt.subplots()\n"
            "ax.plot(data[:, 0], data[:, 1], 'o-')\n"
            "ax.set_xlabel('A'); ax.set_ylabel('B = A²')\n"
            "fig"),
    ]


# -- Live -----------------------------------------------------------------

def _balls():
    return [
        _md("# Bouncing Balls\nElastic collisions; state persists in "
            "the kernel between frames. Stop with the red button."),
        _code(BALLS_SOURCE),
    ]


def _boids():
    return [
        _md("# Flocking Birds\nA boids flock — separation, alignment and "
            "cohesion make the triangles wheel around as one. Stop with "
            "the red button."),
        _code(BOIDS_SOURCE),
    ]


def _random_walk():
    return [
        _md("# Random Walk\nOne step per frame — watch it wander. "
            "Stop with the red button."),
        _code(
            "# Random walk — runs continuously\n"
            "if 'walk' not in globals():\n"
            "    walk = [np.zeros(2)]\n"
            "walk.append(walk[-1]\n"
            "            + np.random.default_rng(len(walk)).normal(0, 1, 2))\n"
            "path = np.array(walk[-600:])\n"
            "fig, ax = plt.subplots(figsize=(4.5, 4.5))\n"
            "ax.plot(path[:, 0], path[:, 1], lw=0.8)\n"
            "ax.plot(*path[-1], 'ro')\n"
            "ax.set_title(f'{len(walk)} steps')\n"
            "fig"),
    ]


def _life():
    return [
        _md("# Game of Life\nConway's automaton on a 60×60 torus, one "
            "generation per frame. Stop with the red button."),
        _code(
            "# Game of Life — runs continuously\n"
            "if 'life' not in globals():\n"
            "    life = (np.random.default_rng(7)\n"
            "            .random((60, 60)) < 0.25).astype(int)\n"
            "_n = sum(np.roll(np.roll(life, dr, 0), dc, 1)\n"
            "         for dr in (-1, 0, 1) for dc in (-1, 0, 1)\n"
            "         if (dr, dc) != (0, 0))\n"
            "life = ((_n == 3) | ((life == 1) & (_n == 2))).astype(int)\n"
            "fig, ax = plt.subplots(figsize=(4.5, 4.5))\n"
            "ax.imshow(life, cmap='Greens', interpolation='nearest')\n"
            "ax.set_xticks([]); ax.set_yticks([])\n"
            "fig"),
    ]


# -- LaTeX ------------------------------------------------------------------

LATEX_DOC = r"""\documentclass[12pt]{article}
\usepackage{amsmath, amssymb}
\usepackage[normalem]{ulem}
\title{\textbf{A LaTeX document in KherveBook}}
\author{Compiled with the real LaTeX engine}
\date{}
\begin{document}
\maketitle

\section*{Unnumbered sections}
A latex cell compiles a full LaTeX document and shows the typeset
pages. Use \texttt{\textbackslash section*} for sections with no
number, like this one, or \texttt{\textbackslash section} when you
want them numbered. Text can be \textbf{bold}, \textit{italic},
\underline{underlined}, \sout{struck through} or \texttt{monospaced},
with H\textsubscript{2}O subscripts and E = mc\textsuperscript{2}.

\section*{Equations}
Inline math such as $E = mc^2$, and displayed equations, numbered:
\begin{equation}
\int_{-\infty}^{\infty} e^{-x^2}\,dx = \sqrt{\pi}
\end{equation}
or aligned over several lines:
\begin{align*}
(a+b)^2 &= a^2 + 2ab + b^2 \\
\nabla \cdot \mathbf{E} &= \frac{\rho}{\varepsilon_0}
\end{align*}

\section*{Numbered items}
\begin{enumerate}
  \item Sections, numbered or not.
  \item Itemised and enumerated lists.
  \item Tables, figures, theorems --- anything LaTeX can typeset.
\end{enumerate}
\end{document}"""


def _latex_document():
    return [
        _md("# LaTeX document\nA **latex cell** compiles a whole LaTeX "
            "document with the tectonic engine and shows the typeset "
            "result. Double-click the rendered page to edit the source; "
            "the LaTeX toolbar (Section / Format / List·Env) inserts the "
            "building blocks. Run (Shift+Enter) to re-compile."),
        _tex(LATEX_DOC),
    ]


SVG_DRAWING = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 420 220">\n'
    '  <defs><linearGradient id="g" x1="0" y1="0" x2="1" y2="1">\n'
    '    <stop offset="0" stop-color="#50bea0"/>\n'
    '    <stop offset="1" stop-color="#2176c7"/></linearGradient></defs>\n'
    '  <rect x="0" y="0" width="420" height="220" fill="#f4f7fb"/>\n'
    '  <rect x="30" y="40" width="150" height="140" rx="14" fill="url(#g)"/>\n'
    '  <circle cx="300" cy="105" r="60" fill="#ed7d31" opacity="0.85"/>\n'
    '  <polygon points="300,55 332,150 268,150" fill="#fff" opacity="0.6"/>\n'
    '  <text x="36" y="205" font-size="16" fill="#2e3440">'
    'KherveBook SVG cell</text>\n'
    '</svg>')


def _svg_drawing():
    return [
        _md("# SVG drawing\nAn **SVG cell** renders a vector drawing. "
            "Paste SVG source, or draw in **KhervePaint** (the sibling "
            "paint app), save as `.svg`, and drop it onto the notebook. "
            "Double-click the drawing to edit its source."),
        {"type": "svg", "source": SVG_DRAWING},
    ]


# -- Physics ----------------------------------------------------------------

def _maxwell():
    return [
        _md("# Maxwell–Boltzmann Speeds\nSpeed distribution of a gas "
            "at three temperatures:"),
        _tex(r"f(v) = 4\pi \left(\frac{m}{2\pi k T}\right)^{3/2} "
             r"v^2 e^{-m v^2 / 2 k T}"),
        _code(
            "from scipy import constants as C\n"
            "m = 28 * C.atomic_mass            # N2\n"
            "v = np.linspace(0, 1500, 400)\n"
            "fig, ax = plt.subplots()\n"
            "for T in (100, 300, 700):\n"
            "    f = (4 * np.pi * (m / (2 * np.pi * C.k * T))**1.5\n"
            "         * v**2 * np.exp(-m * v**2 / (2 * C.k * T)))\n"
            "    ax.plot(v, f, label=f'{T} K')\n"
            "ax.set_xlabel('speed (m/s)'); ax.set_ylabel('f(v)')\n"
            "ax.legend(); ax.grid(alpha=0.3)\n"
            "fig"),
    ]


def _planck():
    return [
        _md("# Planck Blackbody\nSpectral radiance at several "
            "temperatures, with Wien's-law peaks marked."),
        _code(
            "from scipy import constants as C\n"
            "lam = np.linspace(0.05e-6, 4e-6, 600)\n"
            "fig, ax = plt.subplots()\n"
            "for T in (3000, 4500, 6000):\n"
            "    B = (2 * C.h * C.c**2 / lam**5\n"
            "         / (np.exp(C.h * C.c / (lam * C.k * T)) - 1))\n"
            "    ax.plot(lam * 1e6, B, label=f'{T} K')\n"
            "    lp = 2.897771955e-3 / T\n"
            "    ax.axvline(lp * 1e6, ls=':', color='gray', alpha=0.6)\n"
            "ax.set_xlabel('wavelength (µm)')\n"
            "ax.set_ylabel('spectral radiance')\n"
            "ax.legend(); ax.grid(alpha=0.3)\n"
            "fig"),
    ]


def _decay():
    return [
        _md("# Radioactive Decay\nDeterministic curve vs a stochastic "
            "simulation of 500 nuclei."),
        _tex(r"N(t) = N_0\, e^{-\lambda t}"),
        _code(
            "rng = np.random.default_rng(3)\n"
            "N0, lam = 500, 0.3\n"
            "t = np.linspace(0, 15, 200)\n"
            "lifetimes = rng.exponential(1 / lam, N0)\n"
            "alive = (lifetimes[None, :] > t[:, None]).sum(axis=1)\n"
            "fig, ax = plt.subplots()\n"
            "ax.plot(t, N0 * np.exp(-lam * t), 'r-', label='N0·e^{-λt}')\n"
            "ax.step(t, alive, where='post', alpha=0.7,\n"
            "        label='stochastic (500 nuclei)')\n"
            "ax.set_xlabel('t'); ax.set_ylabel('N')\n"
            "ax.legend(); ax.grid(alpha=0.3)\n"
            "fig"),
    ]


def _interference():
    return [
        _md("# Wave Interference\nTwo point sources — classic "
            "two-slit-style fringes."),
        _code(
            "x, y = np.meshgrid(np.linspace(-10, 10, 400),\n"
            "                   np.linspace(0, 14, 280))\n"
            "k = 2 * np.pi / 1.2\n"
            "r1 = np.hypot(x + 2, y); r2 = np.hypot(x - 2, y)\n"
            "z = np.cos(k * r1) + np.cos(k * r2)\n"
            "fig, ax = plt.subplots(figsize=(6, 4.2))\n"
            "im = ax.imshow(z, extent=[-10, 10, 0, 14], origin='lower',\n"
            "               cmap='RdBu', aspect='auto')\n"
            "fig.colorbar(im, ax=ax, label='amplitude')\n"
            "ax.plot([-2, 2], [0, 0], 'k^', ms=10)\n"
            "fig"),
    ]


# -- Chemistry ---------------------------------------------------------------

def _arrhenius():
    return [
        _md("# Arrhenius Plot\nRate constants vs temperature: "
            "ln k against 1/T gives −Ea/R as the slope."),
        _tex(r"k = A\, e^{-E_a / RT}"),
        _code(
            "T = np.array([300, 320, 340, 360, 380, 400.])\n"
            "k = np.array([0.012, 0.048, 0.16, 0.47, 1.22, 2.9])\n"
            "slope, icept = np.polyfit(1 / T, np.log(k), 1)\n"
            "Ea = -slope * 8.314\n"
            "print(f'Ea = {Ea / 1000:.1f} kJ/mol')\n"
            "fig, ax = plt.subplots()\n"
            "ax.plot(1 / T, np.log(k), 'o', label='data')\n"
            "ax.plot(1 / T, slope / T + icept, 'r-', label='fit')\n"
            "ax.set_xlabel('1/T (1/K)'); ax.set_ylabel('ln k')\n"
            "ax.legend(); ax.grid(alpha=0.3)\n"
            "fig"),
    ]


def _titration():
    return [
        _md("# pH Titration Curve\nStrong acid titrated with strong "
            "base; the equivalence point sits at the inflection."),
        _code(
            "Ca, Va = 0.1, 50.0          # acid: 0.1 M, 50 mL\n"
            "Cb = 0.1                     # base molarity\n"
            "Vb = np.linspace(0.01, 100, 500)\n"
            "mol_h = Ca * Va - Cb * Vb\n"
            "V = Va + Vb\n"
            "pH = np.where(mol_h > 0,\n"
            "              -np.log10(np.maximum(mol_h, 1e-12) / V),\n"
            "              14 + np.log10(np.maximum(-mol_h, 1e-12) / V))\n"
            "fig, ax = plt.subplots()\n"
            "ax.plot(Vb, pH)\n"
            "ax.axvline(50, ls=':', color='gray')\n"
            "ax.annotate('equivalence', (50, 7), xytext=(60, 7),\n"
            "            arrowprops=dict(arrowstyle='->'))\n"
            "ax.set_xlabel('base added (mL)'); ax.set_ylabel('pH')\n"
            "ax.grid(alpha=0.3)\n"
            "fig"),
    ]


# -- Biology -----------------------------------------------------------------

def _predator_prey():
    return [
        _md("# Predator–Prey (Lotka–Volterra)\nCoupled oscillations of "
            "rabbits and foxes."),
        _tex(r"\dot{x} = \alpha x - \beta x y \qquad "
             r"\dot{y} = \delta x y - \gamma y"),
        _code(
            "from scipy.integrate import solve_ivp\n"
            "a, b, d, g = 1.1, 0.4, 0.1, 0.4\n"
            "sol = solve_ivp(lambda t, s: [a*s[0] - b*s[0]*s[1],\n"
            "                              d*s[0]*s[1] - g*s[1]],\n"
            "                [0, 50], [10, 5], dense_output=True)\n"
            "t = np.linspace(0, 50, 600)\n"
            "x, y = sol.sol(t)\n"
            "fig, (a1, a2) = plt.subplots(1, 2, figsize=(8, 3.4))\n"
            "a1.plot(t, x, label='prey'); a1.plot(t, y, label='predator')\n"
            "a1.set_xlabel('t'); a1.legend(); a1.grid(alpha=0.3)\n"
            "a2.plot(x, y, lw=0.8); a2.set_xlabel('prey')\n"
            "a2.set_ylabel('predator'); a2.grid(alpha=0.3)\n"
            "fig.tight_layout()\n"
            "fig"),
    ]


def _logistic():
    return [
        _md("# Logistic Population Growth\nGrowth limited by carrying "
            "capacity K, for several starting points."),
        _tex(r"\frac{dN}{dt} = r N \left(1 - \frac{N}{K}\right)"),
        _code(
            "r, K = 0.6, 1000\n"
            "t = np.linspace(0, 15, 300)\n"
            "fig, ax = plt.subplots()\n"
            "for N0 in (10, 100, 600, 1500):\n"
            "    N = K / (1 + (K - N0) / N0 * np.exp(-r * t))\n"
            "    ax.plot(t, N, label=f'N0 = {N0}')\n"
            "ax.axhline(K, ls=':', color='gray')\n"
            "ax.set_xlabel('t'); ax.set_ylabel('N')\n"
            "ax.legend(); ax.grid(alpha=0.3)\n"
            "fig"),
    ]


# -- Materials ----------------------------------------------------------------

def _xrd():
    return [
        _md("# XRD Pattern\nSynthetic powder diffraction pattern: "
            "Gaussian peaks at Bragg angles on a noisy background."),
        _code(
            "rng = np.random.default_rng(5)\n"
            "two_theta = np.linspace(10, 90, 2000)\n"
            "peaks = [(28.4, 100), (47.3, 55), (56.1, 30), (69.1, 8),\n"
            "         (76.4, 12), (88.0, 9)]\n"
            "y = 20 + 200 / two_theta + rng.normal(0, 1.5, 2000)\n"
            "for pos, height in peaks:\n"
            "    y += height * np.exp(-(two_theta - pos)**2 / 0.06)\n"
            "fig, ax = plt.subplots(figsize=(7, 3.6))\n"
            "ax.plot(two_theta, y, lw=0.8)\n"
            "for pos, _h in peaks:\n"
            "    ax.annotate(f'{pos}°', (pos, y.max() * 0.05 + 4\n"
            "                + dict(peaks)[pos]), fontsize=7,\n"
            "                ha='center')\n"
            "ax.set_xlabel('2θ (deg)'); ax.set_ylabel('counts')\n"
            "fig"),
    ]


def _ising():
    return [
        _md("# Ising Model\nMetropolis spin flips at T just below "
            "critical — watch domains coarsen. Stop with the red "
            "button."),
        _code(
            "# Ising model — runs continuously (200 ms)\n"
            "if 'spins' not in globals():\n"
            "    _irng = np.random.default_rng(0)\n"
            "    spins = _irng.choice([-1, 1], (64, 64))\n"
            "    ISING_T = 2.2\n"
            "for _ in range(3000):    # Metropolis sweeps per frame\n"
            "    i, j = _irng.integers(0, 64, 2)\n"
            "    nb = (spins[(i+1) % 64, j] + spins[i-1, j]\n"
            "          + spins[i, (j+1) % 64] + spins[i, j-1])\n"
            "    dE = 2 * spins[i, j] * nb\n"
            "    if dE <= 0 or _irng.random() < np.exp(-dE / ISING_T):\n"
            "        spins[i, j] *= -1\n"
            "fig, ax = plt.subplots(figsize=(4.4, 4.4))\n"
            "ax.imshow(spins, cmap='coolwarm', interpolation='nearest')\n"
            "ax.set_xticks([]); ax.set_yticks([])\n"
            "ax.set_title(f'T = {ISING_T}   M = {spins.mean():+.2f}')\n"
            "fig"),
    ]


# -- Signal Processing ---------------------------------------------------------

def _butterworth():
    return [
        _md("# Butterworth Lowpass\nDesign a 4th-order filter and "
            "clean a noisy signal with `scipy.signal`."),
        _code(
            "from scipy import signal\n"
            "fs = 500\n"
            "t = np.arange(0, 2, 1 / fs)\n"
            "x = (np.sin(2 * np.pi * 5 * t)\n"
            "     + 0.6 * np.sin(2 * np.pi * 90 * t))\n"
            "b, a = signal.butter(4, 20, fs=fs)\n"
            "y = signal.filtfilt(b, a, x)\n"
            "fig, ax = plt.subplots()\n"
            "ax.plot(t, x, alpha=0.4, label='noisy')\n"
            "ax.plot(t, y, 'r', label='filtered (20 Hz)')\n"
            "ax.set_xlim(0, 1); ax.legend(); ax.grid(alpha=0.3)\n"
            "fig"),
    ]


def _peaks():
    return [
        _md("# Peak Detection\n`scipy.signal.find_peaks` with "
            "prominence filtering."),
        _code(
            "from scipy.signal import find_peaks\n"
            "rng = np.random.default_rng(4)\n"
            "x = np.linspace(0, 10, 1500)\n"
            "y = rng.normal(0, 0.08, 1500)\n"
            "for c, h, w in [(1.5, 1, .1), (3.2, 2.4, .15), (5, 1.4, .1),\n"
            "                (6.8, .8, .12), (8.6, 1.9, .2)]:\n"
            "    y += h * np.exp(-(x - c)**2 / (2 * w**2))\n"
            "idx, props = find_peaks(y, prominence=0.5)\n"
            "print('peaks at x =', x[idx].round(2))\n"
            "fig, ax = plt.subplots()\n"
            "ax.plot(x, y, lw=0.8)\n"
            "ax.plot(x[idx], y[idx], 'rv', ms=8)\n"
            "fig"),
    ]


# -- Numerical Methods -----------------------------------------------------------

def _newton():
    return [
        _md("# Newton Root Finding\nQuadratic convergence to "
            "√2 — each step doubles the correct digits."),
        _tex(r"x_{n+1} = x_n - \frac{f(x_n)}{f'(x_n)}"),
        _code(
            "f = lambda x: x**2 - 2\n"
            "df = lambda x: 2 * x\n"
            "x, steps = 3.0, [3.0]\n"
            "for _ in range(6):\n"
            "    x = x - f(x) / df(x)\n"
            "    steps.append(x)\n"
            "for i, s in enumerate(steps):\n"
            "    print(f'x{i} = {s:.15f}   err = {abs(s-2**0.5):.2e}')\n"
            "xs = np.linspace(0.5, 3.2, 200)\n"
            "fig, ax = plt.subplots()\n"
            "ax.plot(xs, f(xs)); ax.axhline(0, color='k', lw=0.6)\n"
            "ax.plot(steps, [f(s) for s in steps], 'ro-', alpha=0.6)\n"
            "fig"),
    ]


def _taylor():
    return [
        _md("# Taylor Series\nsin(x) approximated by partial sums of "
            "increasing order."),
        _tex(r"\sin x = x - \frac{x^3}{3!} + \frac{x^5}{5!} - \cdots"),
        _code(
            "import math as m\n"
            "x = np.linspace(-2 * np.pi, 2 * np.pi, 400)\n"
            "fig, ax = plt.subplots()\n"
            "ax.plot(x, np.sin(x), 'k', lw=2, label='sin')\n"
            "s = np.zeros_like(x)\n"
            "for n in range(5):\n"
            "    s += (-1)**n * x**(2*n+1) / m.factorial(2*n+1)\n"
            "    ax.plot(x, s, alpha=0.7, label=f'order {2*n+1}')\n"
            "ax.set_ylim(-2.5, 2.5); ax.legend(fontsize=8)\n"
            "ax.grid(alpha=0.3)\n"
            "fig"),
    ]


# -- Statistics -------------------------------------------------------------------

def _clt():
    return [
        _md("# Central Limit Theorem\nMeans of uniform samples become "
            "Gaussian as n grows."),
        _code(
            "rng = np.random.default_rng(0)\n"
            "fig, axes = plt.subplots(1, 3, figsize=(8.5, 2.8))\n"
            "for ax, n in zip(axes, (1, 5, 30)):\n"
            "    means = rng.random((20000, n)).mean(axis=1)\n"
            "    ax.hist(means, bins=60, density=True)\n"
            "    ax.set_title(f'n = {n}')\n"
            "fig.tight_layout()\n"
            "fig"),
    ]


def _galton():
    return [
        _md("# Galton Board\n2000 balls, 12 rows of pegs — the "
            "binomial settles into a bell curve."),
        _code(
            "rng = np.random.default_rng(1)\n"
            "rows, balls = 12, 2000\n"
            "bins = rng.integers(0, 2, (balls, rows)).sum(axis=1)\n"
            "from scipy.stats import binom\n"
            "k = np.arange(rows + 1)\n"
            "fig, ax = plt.subplots()\n"
            "ax.hist(bins, bins=np.arange(rows + 2) - 0.5,\n"
            "        rwidth=0.85, label='balls')\n"
            "ax.plot(k, balls * binom.pmf(k, rows, 0.5), 'ro-',\n"
            "        label='binomial')\n"
            "ax.set_xlabel('bin'); ax.legend()\n"
            "fig"),
    ]


# -- Finance ----------------------------------------------------------------------

def _gbm():
    return [
        _md("# Stock Price Paths\nGeometric Brownian motion: 50 "
            "simulated years of daily prices."),
        _tex(r"S_{t+\Delta t} = S_t \exp\left[(\mu - \frac{1}{2}"
             r"\sigma^2)\Delta t + \sigma\sqrt{\Delta t}\,Z\right]"),
        _code(
            "rng = np.random.default_rng(7)\n"
            "mu, sigma, dt = 0.07, 0.2, 1 / 252\n"
            "steps, n = 252, 50\n"
            "Z = rng.normal(size=(steps, n))\n"
            "S = 100 * np.exp(np.cumsum(\n"
            "    (mu - sigma**2 / 2) * dt + sigma * np.sqrt(dt) * Z,\n"
            "    axis=0))\n"
            "fig, ax = plt.subplots()\n"
            "ax.plot(S, lw=0.7, alpha=0.6)\n"
            "ax.axhline(100, color='k', ls=':')\n"
            "ax.set_xlabel('trading day'); ax.set_ylabel('price')\n"
            "ax.set_title(f'mean final: {S[-1].mean():.1f}')\n"
            "fig"),
    ]


def _var():
    return [
        _md("# Value at Risk\nHistorical-simulation VaR of a "
            "synthetic returns series."),
        _code(
            "rng = np.random.default_rng(11)\n"
            "returns = rng.standard_t(4, 2500) * 0.01\n"
            "var95 = -np.percentile(returns, 5)\n"
            "var99 = -np.percentile(returns, 1)\n"
            "print(f'1-day VaR 95%: {var95:.2%}')\n"
            "print(f'1-day VaR 99%: {var99:.2%}')\n"
            "fig, ax = plt.subplots()\n"
            "ax.hist(returns, bins=80, density=True)\n"
            "ax.axvline(-var95, color='orange', label='VaR 95%')\n"
            "ax.axvline(-var99, color='red', label='VaR 99%')\n"
            "ax.legend(); ax.set_xlabel('daily return')\n"
            "fig"),
    ]


# -- Simulations (live) --------------------------------------------------------------

def _double_pendulum():
    return [
        _md("# Double Pendulum\nChaotic motion integrated with RK4, a "
            "few substeps per frame. Stop with the red button."),
        _code(
            "# Double pendulum — runs continuously\n"
            "if 'dp_state' not in globals():\n"
            "    dp_state = np.array([2.4, 0.0, -1.0, 0.0])\n"
            "    dp_trace = []\n"
            "def _dp_rhs(s):\n"
            "    t1, w1, t2, w2 = s\n"
            "    d = t1 - t2\n"
            "    den = 2 - np.cos(d)**2\n"
            "    a1 = (-3*np.sin(t1) - np.sin(t1 - 2*t2)\n"
            "          - 2*np.sin(d)*(w2**2 + w1**2*np.cos(d))) / (2*den)\n"
            "    a2 = (2*np.sin(d)*(2*w1**2 + 2*np.cos(t1)\n"
            "          + w2**2*np.cos(d))) / (2*den)\n"
            "    return np.array([w1, a1, w2, a2])\n"
            "for _ in range(4):                  # RK4 substeps\n"
            "    h = 0.02\n"
            "    k1 = _dp_rhs(dp_state)\n"
            "    k2 = _dp_rhs(dp_state + h/2*k1)\n"
            "    k3 = _dp_rhs(dp_state + h/2*k2)\n"
            "    k4 = _dp_rhs(dp_state + h*k3)\n"
            "    dp_state = dp_state + h/6*(k1 + 2*k2 + 2*k3 + k4)\n"
            "t1, _w1, t2, _w2 = dp_state\n"
            "x1, y1 = np.sin(t1), -np.cos(t1)\n"
            "x2, y2 = x1 + np.sin(t2), y1 - np.cos(t2)\n"
            "dp_trace = (dp_trace + [(x2, y2)])[-400:]\n"
            "fig, ax = plt.subplots(figsize=(4.4, 4.4))\n"
            "tr = np.array(dp_trace)\n"
            "ax.plot(tr[:, 0], tr[:, 1], lw=0.6, color='#2176c7',\n"
            "        alpha=0.7)\n"
            "ax.plot([0, x1, x2], [0, y1, y2], 'o-', color='#c0392b',\n"
            "        ms=8, lw=2)\n"
            "ax.set_xlim(-2.2, 2.2); ax.set_ylim(-2.2, 2.2)\n"
            "ax.set_aspect('equal'); ax.set_xticks([]); ax.set_yticks([])\n"
            "fig"),
    ]


def _kepler():
    return [
        _md("# Kepler Orbit\nA planet on an eccentric orbit — faster "
            "near the star (equal areas in equal times). Stop with the "
            "red button."),
        _code(
            "# Kepler orbit — runs continuously\n"
            "if 'kp_pos' not in globals():\n"
            "    kp_pos = np.array([1.5, 0.0])\n"
            "    kp_vel = np.array([0.0, 0.65])\n"
            "    kp_trace = []\n"
            "for _ in range(6):                  # leapfrog substeps\n"
            "    h = 0.01\n"
            "    r = np.linalg.norm(kp_pos)\n"
            "    kp_vel = kp_vel - h * kp_pos / r**3\n"
            "    kp_pos = kp_pos + h * kp_vel\n"
            "kp_trace = (kp_trace + [tuple(kp_pos)])[-500:]\n"
            "fig, ax = plt.subplots(figsize=(4.4, 4.4))\n"
            "tr = np.array(kp_trace)\n"
            "ax.plot(tr[:, 0], tr[:, 1], lw=0.7, alpha=0.7)\n"
            "ax.plot(0, 0, '*', color='#f6b73c', ms=22)\n"
            "ax.plot(*kp_pos, 'o', color='#2176c7', ms=9)\n"
            "ax.set_xlim(-2, 2); ax.set_ylim(-2, 2)\n"
            "ax.set_aspect('equal'); ax.set_xticks([]); ax.set_yticks([])\n"
            "fig"),
    ]


def _mc_pi():
    return [
        _md("# Monte Carlo π\nDarts accumulate across frames; the "
            "estimate sharpens live. Stop with the red button."),
        _code(
            "# Monte Carlo pi — runs continuously\n"
            "if 'pi_in' not in globals():\n"
            "    pi_in = np.empty((0, 2)); pi_out = np.empty((0, 2))\n"
            "pts = np.random.default_rng(len(pi_in)\n"
            "                            + len(pi_out)).random((300, 2))\n"
            "hit = (pts**2).sum(axis=1) <= 1\n"
            "pi_in = np.vstack([pi_in, pts[hit]])\n"
            "pi_out = np.vstack([pi_out, pts[~hit]])\n"
            "n = len(pi_in) + len(pi_out)\n"
            "est = 4 * len(pi_in) / n\n"
            "fig, ax = plt.subplots(figsize=(4.4, 4.4))\n"
            "ax.scatter(pi_in[:, 0], pi_in[:, 1], s=2, c='#2e7d4f')\n"
            "ax.scatter(pi_out[:, 0], pi_out[:, 1], s=2, c='#c0392b')\n"
            "th = np.linspace(0, np.pi / 2, 100)\n"
            "ax.plot(np.cos(th), np.sin(th), 'k', lw=1)\n"
            "ax.set_title(f'π ≈ {est:.5f}   (n = {n})')\n"
            "ax.set_aspect('equal'); ax.set_xticks([]); ax.set_yticks([])\n"
            "fig"),
    ]


def _sir():
    return [
        _md("# SIR Epidemic\nSusceptible–Infected–Recovered dynamics "
            "for a few R₀ values."),
        _code(
            "from scipy.integrate import solve_ivp\n"
            "fig, ax = plt.subplots()\n"
            "for R0, ls in ((1.5, ':'), (2.5, '--'), (4, '-')):\n"
            "    g = 0.2; b = R0 * g\n"
            "    sol = solve_ivp(\n"
            "        lambda t, s: [-b*s[0]*s[1], b*s[0]*s[1] - g*s[1],\n"
            "                      g*s[1]],\n"
            "        [0, 80], [0.999, 0.001, 0], dense_output=True)\n"
            "    t = np.linspace(0, 80, 400)\n"
            "    ax.plot(t, sol.sol(t)[1], ls=ls, color='#c0392b',\n"
            "            label=f'I, R0={R0}')\n"
            "ax.set_xlabel('days'); ax.set_ylabel('infected fraction')\n"
            "ax.legend(); ax.grid(alpha=0.3)\n"
            "fig"),
    ]


# -- Live Data ---------------------------------------------------------------------

WEATHER_SOURCE = r'''# London weather from Open-Meteo (no API key needed).
# Hourly temperature + conditions and a 7-day forecast, drawn with
# matplotlib weather icons. Falls back to sample data when offline.
import json, urllib.request
from matplotlib.patches import Circle, Polygon

LAT, LON, DAYS = 51.5072, -0.1276, 7     # change me for another city

def code_info(c):
    table = {0: ("Clear", "sun"), 1: ("Mainly clear", "sun"),
             2: ("Partly cloudy", "partly"), 3: ("Overcast", "cloud"),
             45: ("Fog", "fog"), 48: ("Rime fog", "fog")}
    for codes, info in [((51, 53, 55, 56, 57, 61, 63, 65, 66, 67, 80,
                          81, 82), ("Rain", "rain")),
                        ((71, 73, 75, 77, 85, 86), ("Snow", "snow")),
                        ((95, 96, 99), ("Thunderstorm", "thunder"))]:
        for k in codes:
            table[k] = info
    return table.get(int(c), ("Cloudy", "cloud"))

def draw_icon(ax, cx, cy, cat, s=0.42):
    def sun(ox, oy, sc):
        for k in range(8):
            a = k * np.pi / 4
            ax.plot([ox+0.55*sc*np.cos(a), ox+0.92*sc*np.cos(a)],
                    [oy+0.55*sc*np.sin(a), oy+0.92*sc*np.sin(a)],
                    color="#f6b73c", lw=1.5, solid_capstyle="round")
        ax.add_patch(Circle((ox, oy), 0.42*sc, color="#f6b73c"))
    def cloud(ox, oy, sc):
        for dx, dy, rr in [(-0.42, 0, 0.3), (0.42, 0, 0.32),
                           (0, 0.2, 0.4), (0, -0.05, 0.5)]:
            ax.add_patch(Circle((ox+dx*sc, oy+dy*sc), rr*sc,
                                color="#9aa3ad"))
    def drops(ox, oy, sc):
        for j in range(3):
            dx = (j - 1) * 0.3 * sc
            ax.plot([ox+dx, ox+dx-0.05*sc], [oy-0.45*sc, oy-0.8*sc],
                    color="#3b82f6", lw=1.8, solid_capstyle="round")
    def flakes(ox, oy, sc):
        for j in range(3):
            ax.scatter([ox+(j-1)*0.3*sc], [oy-0.62*sc], marker="*",
                       s=70*sc, color="#7fb2e6")
    def bolt(ox, oy, sc):
        p = np.array([(0, .45), (-.22, -.02), (-.02, -.02),
                      (-.18, -.5), (.24, .1), (.04, .1)])
        ax.add_patch(Polygon(np.column_stack([ox+p[:, 0]*sc,
                                              oy+p[:, 1]*sc]),
                             closed=True, color="#f5c518"))
    if cat == "sun": sun(cx, cy, s)
    elif cat == "partly":
        sun(cx-0.28*s, cy+0.25*s, s*0.65); cloud(cx+0.1*s, cy-0.05*s, s)
    elif cat == "fog":
        cloud(cx, cy+0.12*s, s*0.9)
        for j in range(3):
            yy = cy - 0.32*s - 0.18*s*j
            ax.plot([cx-0.5*s, cx+0.5*s], [yy, yy], color="#9aa3ad",
                    lw=1.6, solid_capstyle="round")
    elif cat == "rain": cloud(cx, cy+0.12*s, s); drops(cx, cy, s)
    elif cat == "snow": cloud(cx, cy+0.12*s, s); flakes(cx, cy, s)
    elif cat == "thunder": cloud(cx, cy+0.12*s, s); bolt(cx, cy, s)
    else: cloud(cx, cy, s)

url = ("https://api.open-meteo.com/v1/forecast"
       f"?latitude={LAT}&longitude={LON}"
       "&hourly=temperature_2m,weathercode"
       "&daily=temperature_2m_max,temperature_2m_min,weathercode"
       "&current=temperature_2m,weathercode"
       f"&timezone=auto&forecast_days={DAYS}")
live, now = True, None
try:
    req = urllib.request.Request(url, headers={"User-Agent": "KherveBook"})
    with urllib.request.urlopen(req, timeout=8) as r:
        d = json.load(r)
    htime, htemp = d["hourly"]["time"], d["hourly"]["temperature_2m"]
    hcode = d["hourly"]["weathercode"]
    dday, dcode = d["daily"]["time"], d["daily"]["weathercode"]
    dmax = d["daily"]["temperature_2m_max"]
    dmin = d["daily"]["temperature_2m_min"]
    now = d["current"]["time"]
except Exception:
    live = False
    rng = np.random.default_rng(0)
    htime = [f"2025-01-01T{h % 24:02d}:00" for h in range(48)]
    htemp = (8 + 5*np.sin((np.arange(48)-9)/24*2*np.pi)
             + rng.normal(0, .5, 48)).round(1).tolist()
    hcode = [3, 3, 45, 2, 1, 0, 0, 1, 2, 2, 3, 61, 63, 61, 80, 3,
             2, 1, 0, 0, 1, 2, 3, 3] * 2
    dday = [f"day {i+1}" for i in range(DAYS)]
    dmax = (12 + rng.normal(0, 2, DAYS)).round(1).tolist()
    dmin = (5 + rng.normal(0, 2, DAYS)).round(1).tolist()
    dcode = [0, 2, 3, 61, 80, 1, 95][:DAYS]

start = 0
if now is not None:
    for i, t in enumerate(htime):
        if t <= now: start = i
        else: break
hours = [t[11:16] for t in htime[start:start+24]]
temps = [float(v) for v in htemp[start:start+24]]
hcat = [code_info(c)[1] for c in hcode[start:start+24]]

fig, (axc, axt, axf) = plt.subplots(
    3, 1, figsize=(7.8, 6.4),
    gridspec_kw={"height_ratios": [1.1, 2.6, 1.4]})
fig.suptitle(f"London weather ({LAT}, {LON})"
             + ("" if live else "  [offline sample]"),
             fontsize=12, fontweight="bold")
step = list(range(0, 24, 3))
axc.set_xlim(-0.6, len(step)-0.4); axc.set_ylim(-0.9, 1.2)
axc.set_aspect("equal"); axc.axis("off")
axc.set_title("Next 24 hours")
for j, i in enumerate(step):
    draw_icon(axc, j, 0.1, hcat[i], 0.40)
    axc.text(j, -0.7, hours[i], ha="center", fontsize=7)
    axc.text(j, 1.0, f"{temps[i]:.0f}°", ha="center", fontsize=8,
             fontweight="bold")
axt.plot(range(24), temps, "o-", ms=3, color="#ed7d31")
axt.set_xticks(range(0, 24, 3))
axt.set_xticklabels([hours[i] for i in range(0, 24, 3)])
axt.set_ylabel("°C"); axt.grid(True, alpha=0.3)
axt.set_title("Hourly temperature")
n = len(dday[:DAYS])
axf.set_xlim(-0.6, n-0.4); axf.set_ylim(-1.0, 1.3)
axf.set_aspect("equal"); axf.axis("off")
axf.set_title(f"{DAYS}-day forecast")
for i in range(n):
    draw_icon(axf, i, 0.15, code_info(dcode[i])[1], 0.42)
    axf.text(i, 1.05, f"{dmax[i]:.0f}°/{dmin[i]:.0f}°", ha="center",
             fontsize=7, fontweight="bold")
    axf.text(i, -0.8, str(dday[i])[5:], ha="center", fontsize=7)
fig.subplots_adjust(hspace=0.55, top=0.90, bottom=0.04)
fig'''


GLOBE_SOURCE = r'''# Earth globe — runs continuously (800 ms)
# Spinning 3D Earth (orthographic) with the real-time day/night
# terminator: the orange line is where sunrise/sunset is right now.
# Pure matplotlib, no geo libraries. Stop with the red button.
import math
from datetime import datetime, timezone

if 'globe_lon' not in globals():
    globe_lon, GLOBE_LAT, GLOBE_STEP = 0.0, 20.0, 12.0
now = datetime.now(timezone.utc)
doy = now.timetuple().tm_yday
hr = now.hour + now.minute / 60 + now.second / 3600
sub_lat = -23.44 * math.cos(math.radians(360 / 365 * (doy + 10)))
sub_lon = -(hr - 12) * 15
slr, sll = math.radians(sub_lat), math.radians(sub_lon)
sun = np.array([math.cos(slr)*math.cos(sll),
                math.cos(slr)*math.sin(sll), math.sin(slr)])

def ortho(lat, lon):
    la, lo = np.radians(np.asarray(lat, float)), np.radians(
        np.asarray(lon, float))
    l0, n0 = math.radians(globe_lon), math.radians(GLOBE_LAT)
    dl = lo - l0
    x = np.cos(la) * np.sin(dl)
    y = math.cos(n0)*np.sin(la) - math.sin(n0)*np.cos(la)*np.cos(dl)
    v = math.sin(n0)*np.sin(la) + math.cos(n0)*np.cos(la)*np.cos(dl)
    return x, y, v > 0

fig, ax = plt.subplots(figsize=(5.6, 5.6), facecolor="#080820")
ax.set_aspect("equal"); ax.set_xlim(-1.18, 1.18); ax.set_ylim(-1.18, 1.18)
ax.axis("off")
srng = np.random.default_rng(42)
sx, sy = srng.uniform(-1.18, 1.18, 300), srng.uniform(-1.18, 1.18, 300)
far = sx**2 + sy**2 > 1.06
ax.scatter(sx[far], sy[far], s=srng.uniform(0.1, 2.5, far.sum()),
           c="white", alpha=0.6, linewidths=0)
ax.add_patch(plt.Circle((0, 0), 1.0, fc="#14466a", ec="#2a6090", lw=1.2))
for g in range(-60, 90, 30):
    lo = np.linspace(-180, 180, 360)
    x, y, v = ortho(np.full(360, g), lo)
    x = x.copy(); x[~v] = np.nan
    ax.plot(x, y, c="white", alpha=0.12, lw=0.4)
for g in range(-150, 180, 30):
    la = np.linspace(-90, 90, 200)
    x, y, v = ortho(la, np.full(200, g))
    x = x.copy(); x[~v] = np.nan
    ax.plot(x, y, c="white", alpha=0.12, lw=0.4)

_C = [
  [(37,-9),(37,10),(33,32),(30,33),(12,44),(2,42),(-10,40),(-26,33),
   (-35,20),(-34,18),(-4,9),(5,1),(5,-5),(15,-17),(22,-17),(26,-15),
   (33,-8),(37,-9)],
  [(36,-9),(37,-5),(43,-9),(44,-1),(47,-2),(48,-5),(49,0),(51,2),
   (54,6),(56,8),(58,6),(63,5),(65,12),(68,16),(71,26),(70,28),
   (64,30),(57,40),(52,40),(48,35),(46,30),(44,28),(42,29),(41,25),
   (40,20),(38,24),(37,22),(36,15),(36,-5),(36,-9)],
  [(71,26),(72,60),(70,90),(72,120),(70,140),(66,170),(60,165),
   (55,140),(50,130),(42,132),(35,130),(30,122),(22,114),(10,106),
   (1,104),(-8,112),(-8,120),(5,105),(10,100),(8,77),(20,88),
   (22,72),(25,57),(30,48),(32,36),(36,36),(40,28),(42,29),(44,28),
   (46,30),(48,35),(52,40),(57,40),(64,30),(70,28),(71,26)],
  [(72,-165),(72,-80),(68,-60),(60,-65),(52,-56),(47,-53),(45,-62),
   (44,-67),(41,-70),(30,-81),(25,-80),(25,-90),(20,-87),(18,-88),
   (15,-84),(16,-90),(20,-105),(24,-110),(32,-117),(38,-123),
   (48,-124),(55,-130),(58,-137),(60,-147),(64,-165),(72,-165)],
  [(12,-72),(10,-76),(7,-78),(4,-77),(2,-80),(-5,-81),(-14,-76),
   (-18,-70),(-23,-70),(-35,-57),(-42,-64),(-55,-66),(-56,-68),
   (-52,-72),(-46,-76),(-40,-73),(-23,-42),(-13,-39),(-5,-35),
   (-2,-50),(2,-52),(6,-60),(8,-62),(11,-72),(12,-72)],
  [(-12,130),(-14,127),(-22,114),(-32,115),(-35,117),(-38,141),
   (-38,146),(-33,152),(-28,153),(-22,150),(-17,146),(-13,136),
   (-12,130)],
  [(76,-72),(82,-40),(82,-20),(78,-18),(76,-20),(72,-22),(68,-28),
   (65,-40),(66,-53),(69,-55),(72,-56),(76,-72)],
]
for pts in _C:
    la0, lo0 = map(list, zip(*pts))
    fla, flo = [], []
    for i in range(len(la0) - 1):
        nseg = max(3, int(abs(la0[i+1]-la0[i])
                          + abs(lo0[i+1]-lo0[i])) // 3)
        fla.extend(np.linspace(la0[i], la0[i+1], nseg,
                               endpoint=False).tolist())
        flo.extend(np.linspace(lo0[i], lo0[i+1], nseg,
                               endpoint=False).tolist())
    fla.append(la0[-1]); flo.append(lo0[-1])
    x, y, v = ortho(np.array(fla), np.array(flo))
    x, y = x.copy(), y.copy(); x[~v] = np.nan; y[~v] = np.nan
    ax.plot(x, y, c="#3aaa5a", lw=1.0, solid_capstyle="round")

N = 240
xi = np.linspace(-1, 1, N)
YI, XI = np.meshgrid(xi, xi, indexing="ij")
R2 = XI**2 + YI**2; disk = R2 <= 1.0
rho = np.sqrt(np.where(disk, R2, 0))
rho_s = np.where(rho > 1e-9, rho, 1.0)
c_a = np.arcsin(np.clip(rho, 0, 1))
n0, l0 = math.radians(GLOBE_LAT), math.radians(globe_lon)
lat_i = np.arcsin(np.clip(np.cos(c_a)*math.sin(n0)
                          + YI*np.sin(c_a)*math.cos(n0)/rho_s, -1, 1))
lon_i = l0 + np.arctan2(XI*np.sin(c_a),
                        rho_s*math.cos(n0)*np.cos(c_a)
                        - YI*math.sin(n0)*np.sin(c_a))
dot = (np.cos(lat_i)*np.cos(lon_i)*sun[0]
       + np.cos(lat_i)*np.sin(lon_i)*sun[1] + np.sin(lat_i)*sun[2])
img = np.zeros((N, N, 4))
img[:, :, 3] = np.where(disk, np.clip(-dot * 6, 0, 1) * 0.55, 0)
ax.imshow(img, extent=[-1, 1, -1, 1], interpolation="bilinear",
          origin="lower")

u = np.cross(sun, [0, 0, 1] if abs(sun[2]) < 0.999 else [1, 0, 0])
u = u / np.linalg.norm(u); w = np.cross(sun, u)
t = np.linspace(0, 2*np.pi, 400)
pts3 = np.outer(np.cos(t), u) + np.outer(np.sin(t), w)
tla = np.degrees(np.arcsin(np.clip(pts3[:, 2], -1, 1)))
tlo = np.degrees(np.arctan2(pts3[:, 1], pts3[:, 0]))
tx, ty, tv = ortho(tla, tlo)
tx = tx.copy(); tx[~tv] = np.nan
ax.plot(tx, ty, c="#ff6b35", lw=2.0, alpha=0.85)
ax.set_title(f"Earth — {now.strftime('%H:%M:%S UTC')}   "
             f"rotation {globe_lon:+.0f}°",
             color="white", fontsize=10, fontweight="bold")
globe_lon = (globe_lon + GLOBE_STEP + 180.0) % 360.0 - 180.0
fig'''


def _weather():
    return [
        _md("# London Weather (live)\nReal forecast from the free "
            "Open-Meteo API (no key): hourly temperature, conditions "
            "drawn as icons, and a 7-day outlook. Run the cell again "
            "to refresh; works offline with sample data. Change "
            "`LAT, LON` for another city."),
        _code(WEATHER_SOURCE),
    ]


def _globe():
    return [
        _md("# Earth Globe (live)\nA spinning Earth with the real-time "
            "day/night terminator — the orange line is where the sun "
            "is rising or setting *right now*. Pure matplotlib."),
        _code(GLOBE_SOURCE),
    ]


# -- Registry --------------------------------------------------------------

EXAMPLES = [
    # (name, category, builder)
    ("LaTeX Document",           "LaTeX",             _latex_document),
    ("SVG Drawing",              "Drawing",           _svg_drawing),
    ("Symbolic Calculus",        "Math",              _sympy),
    ("Matrix Operations",        "Math",              _matrices),
    ("Newton Root Finding",      "Math",              _newton),
    ("Taylor Series",            "Math",              _taylor),
    ("Projectile Motion",        "Physics",           _projectile),
    ("Damped Oscillator",        "Physics",           _oscillator),
    ("Maxwell-Boltzmann Speeds", "Physics",           _maxwell),
    ("Planck Blackbody",         "Physics",           _planck),
    ("Radioactive Decay",        "Physics",           _decay),
    ("Wave Interference",        "Physics",           _interference),
    ("Arrhenius Plot",           "Chemistry",         _arrhenius),
    ("pH Titration Curve",       "Chemistry",         _titration),
    ("Predator-Prey",            "Biology",           _predator_prey),
    ("Logistic Growth",          "Biology",           _logistic),
    ("XRD Pattern",              "Materials",         _xrd),
    ("Ising Model (live)",       "Materials",         _ising),
    ("FFT Spectrum",             "Signal Processing", _fft),
    ("Butterworth Lowpass",      "Signal Processing", _butterworth),
    ("Peak Detection",           "Signal Processing", _peaks),
    ("Curve Fitting (lmfit)",    "Statistics",        _curve_fit),
    ("Central Limit Theorem",    "Statistics",        _clt),
    ("Galton Board",             "Statistics",        _galton),
    ("Stock Price Paths",        "Finance",           _gbm),
    ("Value at Risk",            "Finance",           _var),
    ("Pandas Quickstart",        "Data",              _pandas),
    ("Sheet ↔ Python",           "Data",              _sheet_python),
    ("Bouncing Balls",           "Simulations",       _balls),
    ("Flocking Birds",           "Simulations",       _boids),
    ("Random Walk",              "Simulations",       _random_walk),
    ("Game of Life",             "Simulations",       _life),
    ("Double Pendulum",          "Simulations",       _double_pendulum),
    ("Kepler Orbit",             "Simulations",       _kepler),
    ("Monte Carlo π",            "Simulations",       _mc_pi),
    ("SIR Epidemic",             "Simulations",       _sir),
    ("London Weather (live)",    "Live Data",         _weather),
    ("Earth Globe (live)",       "Live Data",         _globe),
]

# Spreadsheet examples ported from KherveSheet (markdown + live sheet
# cell, some with a chart). Kept in their own module for file size.
from .sheet_examples import SHEET_EXAMPLES   # noqa: E402
from .examples_svg import SVG_EXAMPLES       # noqa: E402
from .examples_latex import LATEX_EXAMPLES   # noqa: E402
from .examples_js import JS_EXAMPLES         # noqa: E402
from .examples_arpes import ARPES_EXAMPLES   # noqa: E402
from .examples_arpes_bands import ARPES_BANDS_EXAMPLES        # noqa: E402
from .examples_arpes_fit import ARPES_FIT_EXAMPLES            # noqa: E402
from .examples_arpes_xps_tr import ARPES_XPS_TR_EXAMPLES      # noqa: E402
from .examples_arpes_nano_bz import ARPES_NANO_BZ_EXAMPLES    # noqa: E402
from .examples_arpes_cuts import ARPES_CUTS_EXAMPLES          # noqa: E402
from .examples_arpes_hv import ARPES_HV_EXAMPLES              # noqa: E402
from .examples_arpes_selfenergy import ARPES_SE_EXAMPLES      # noqa: E402
from .examples_xps_fit import XPS_FIT_EXAMPLES                # noqa: E402
from .examples_xps_quant import XPS_QUANT_EXAMPLES            # noqa: E402
from .examples_xps_adv import XPS_ADV_EXAMPLES                # noqa: E402
from .examples_xrd import XRD_EXAMPLES                        # noqa: E402
from .examples_xrd2 import XRD2_EXAMPLES                      # noqa: E402
from .examples_arpes_tour import ARPES_TOUR_EXAMPLES         # noqa: E402
from .examples_ftir import FTIR_EXAMPLES                     # noqa: E402
from .examples_xrd3 import XRD3_EXAMPLES                     # noqa: E402
from .examples_edx import EDX_EXAMPLES                       # noqa: E402
from .examples_eels import EELS_EXAMPLES                     # noqa: E402
from .examples_tga import TGA_EXAMPLES                       # noqa: E402
from .examples_bet import BET_EXAMPLES                       # noqa: E402
from .examples_sims import SIMS_EXAMPLES                     # noqa: E402
from .examples_nmr import NMR_EXAMPLES                       # noqa: E402

EXAMPLES += (SHEET_EXAMPLES + SVG_EXAMPLES + LATEX_EXAMPLES + JS_EXAMPLES
             + ARPES_EXAMPLES + ARPES_BANDS_EXAMPLES + ARPES_FIT_EXAMPLES
             + ARPES_XPS_TR_EXAMPLES + ARPES_NANO_BZ_EXAMPLES
             + ARPES_CUTS_EXAMPLES + ARPES_HV_EXAMPLES + ARPES_SE_EXAMPLES
             + ARPES_TOUR_EXAMPLES
             + XPS_FIT_EXAMPLES + XPS_QUANT_EXAMPLES + XPS_ADV_EXAMPLES
             + XRD_EXAMPLES + XRD2_EXAMPLES + XRD3_EXAMPLES + FTIR_EXAMPLES
             + EDX_EXAMPLES + EELS_EXAMPLES + TGA_EXAMPLES + BET_EXAMPLES
             + SIMS_EXAMPLES + NMR_EXAMPLES)

_LIVE_RE = re.compile(r"runs continuously(?:\s*\((\d+)\s*ms\))?")


def load_example(notebook, builder):
    """Replace the notebook content with the example, fully run."""
    cells = builder()
    notebook.load_json(json.dumps({"format": "kbook", "version": 1,
                                   "cells": cells}))
    live, live_ms = None, 60
    for cell in notebook.cells:
        source = cell.source()
        first = source.splitlines()[0] if source.strip() else ""
        match = _LIVE_RE.search(first)
        if live is None and match:
            live = cell
            live_ms = int(match.group(1) or 60)
        elif source.strip():
            cell.execute(notebook.kernel)
    if live is not None:
        notebook.start_loop(live, live_ms)
