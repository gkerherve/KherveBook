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
        _tex(r"x(t) = v_0\cos\theta\, t \qquad "
             r"y(t) = v_0\sin\theta\, t - \tfrac{1}{2} g t^2"),
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


# -- Registry --------------------------------------------------------------

EXAMPLES = [
    # (name, category, builder)
    ("FFT Spectrum",            "Math",    _fft),
    ("Symbolic Calculus",       "Math",    _sympy),
    ("Matrix Operations",       "Math",    _matrices),
    ("Curve Fitting (lmfit)",   "Science", _curve_fit),
    ("Damped Oscillator",       "Science", _oscillator),
    ("Projectile Motion",       "Science", _projectile),
    ("Pandas Quickstart",       "Data",    _pandas),
    ("Sheet ↔ Python",          "Data",    _sheet_python),
    ("Bouncing Balls",          "Live",    _balls),
    ("Random Walk",             "Live",    _random_walk),
    ("Game of Life",            "Live",    _life),
]


def load_example(notebook, builder):
    """Replace the notebook content with the example, fully run."""
    cells = builder()
    notebook.load_json(json.dumps({"format": "kbook", "version": 1,
                                   "cells": cells}))
    live = None
    for cell in notebook.cells:
        source = cell.source()
        first = source.splitlines()[0] if source.strip() else ""
        if live is None and LIVE_MARK in first:
            live = cell
        elif source.strip():
            cell.execute(notebook.kernel)
    if live is not None:
        notebook.start_loop(live)
