"""Thermogravimetric analysis (TGA) examples.

A self-contained companion to ``examples.py`` (Examples menu, "TGA"
category). **Thermogravimetric analysis** records a sample's mass as it
is heated at a controlled rate; the mass-versus-temperature trace and
its derivative (the **DTG**) reveal moisture loss, organic decomposition,
carbonate breakdown and the inert residue, and — run at several heating
rates — the **activation energy** of each step.

There is no standard TGA library on PyPI, so every code cell synthesises
faithful data with NumPy (smooth sigmoid mass-loss steps + detector
noise) and analyses it with NumPy/SciPy so the examples always run
offline. In a real workflow you would load the instrument's exported CSV
with **pandas** (``pd.read_csv``) instead — the markdown cells show how.

This module defines its own ``_md``/``_code`` helpers and exports
``TGA_EXAMPLES`` so it merges into ``examples.py`` without a circular
import.

Copyright (C) 2026 Gwilherm Kerherve

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.
"""


def _md(t):
    return {"type": "markdown", "source": t}


def _code(t):
    return {"type": "code", "source": t}


# -- 1. Mass loss & DTG ----------------------------------------------------

_MASSLOSS_INTRO = """\
# TGA mass loss & DTG

**Thermogravimetric analysis (TGA)** heats a sample at a constant rate and
records its **mass** continuously. As the temperature climbs, distinct
physical and chemical events each shed mass: adsorbed water leaves first,
then organics burn or pyrolyse, then carbonates and other minerals
decompose, leaving an inert **residue (ash)** at the end. On a mass-%
curve these show up as a staircase of smooth **sigmoid steps**.

The **derivative thermogravimetric (DTG)** curve, $\\mathrm{DTG} =
-\\mathrm{d}m/\\mathrm{d}T$, turns each step into a **peak**. The peak
*position* marks the temperature of fastest mass loss for that step, and
the *area* under the peak equals the step's mass loss — which makes the
DTG the standard way to separate overlapping events.

A real instrument exports the trace as a CSV; load it with **pandas**:

```python
import pandas as pd
df = pd.read_csv("tga_run.csv")            # columns: temperature, mass_pct
T = df["temperature"].to_numpy()
m = df["mass_pct"].to_numpy()
```

The cell below synthesises a four-step trace (no standard TGA Python
library exists), computes the DTG numerically, and plots both on a
**twin axis**.
"""


_MASSLOSS = r'''
# TGA mass-loss trace + its derivative (DTG).
# Synthetic data: a sum of sigmoid steps, each shedding a fixed mass %.
# With a real instrument you would pd.read_csv the exported trace instead.
import numpy as np
import matplotlib.pyplot as plt

rng = np.random.default_rng(0)
BLUE, ORANGE, GREEN = "#3776ab", "#e07b39", "#50bea0"


def sigmoid(T, T0, width):
    """Smooth 0 -> 1 step centred at T0 (width sets the sharpness)."""
    return 1.0 / (1.0 + np.exp(-(T - T0) / width))


# Each step: (centre temperature, transition width, mass lost in %).
steps = [
    (110.0, 12.0, 5.0),    # moisture / adsorbed water
    (340.0, 25.0, 30.0),   # organic decomposition
    (650.0, 22.0, 20.0),   # carbonate -> oxide + CO2
]
T = np.linspace(30.0, 900.0, 1000)         # temperature (degrees C)

mass = np.full_like(T, 100.0)              # start at 100 %
for T0, w, loss in steps:
    mass -= loss * sigmoid(T, T0, w)
mass += rng.normal(0.0, 0.05, T.size)      # microbalance noise
residue = mass[-1]                         # ash / residue at the end

# DTG = -dm/dT (positive peaks at each decomposition step). Smooth the
# trace first so the derivative isn't swamped by microbalance noise --
# real instruments low-pass the DTG the same way.
from scipy.ndimage import gaussian_filter1d
dtg = -np.gradient(gaussian_filter1d(mass, 6), T)

fig, ax1 = plt.subplots(figsize=(6.4, 4.4))
ax1.plot(T, mass, color=BLUE, lw=2, label="mass")
ax1.set_xlabel(r"temperature ($^\circ$C)")
ax1.set_ylabel(r"mass (%)", color=BLUE)
ax1.tick_params(axis="y", labelcolor=BLUE)
ax1.axhline(residue, color="0.6", ls=":", lw=1)
ax1.text(880, residue + 1.5, "residue %.0f%%" % residue,
         ha="right", fontsize=8, color="0.4")

ax2 = ax1.twinx()
ax2.plot(T, dtg, color=ORANGE, lw=1.8, label="DTG")
ax2.set_ylabel(r"DTG  $-\,\mathrm{d}m/\mathrm{d}T$  (%/$^\circ$C)",
               color=ORANGE)
ax2.tick_params(axis="y", labelcolor=ORANGE)
ax2.set_ylim(bottom=0)

# Mark each DTG peak temperature.
for T0, w, loss in steps:
    i = int(np.argmin(np.abs(T - T0)))
    ax2.plot(T[i], dtg[i], "v", color=ORANGE, ms=7)
    ax2.annotate(r"%d$^\circ$C" % round(T[i]), (T[i], dtg[i]),
                 textcoords="offset points", xytext=(0, 7),
                 ha="center", fontsize=8, color=ORANGE)

ax1.set_title("TGA mass loss with DTG overlay")
fig.tight_layout()
fig
'''


def _massloss():
    return [_md(_MASSLOSS_INTRO), _code(_MASSLOSS)]


# -- 2. Decomposition steps / composition ---------------------------------

_STEPS_INTRO = """\
# TGA decomposition steps

Because each TGA step corresponds to a known process, the **step heights**
quantify the sample's **composition**. Reading the mass plateaus before
and after every transition gives, in turn:

* the **moisture** content (low-temperature loss, ~5%),
* the **organic / volatile** fraction (combustion or pyrolysis, ~30%),
* the **carbonate** content, via the CO$_2$ released on decomposition
  (CaCO$_3 \\rightarrow$ CaO + CO$_2$, ~20%), and
* the **residue (ash)** — the non-volatile inorganic remainder.

Each step's mass-loss percentage is just the plateau-to-plateau drop. To
locate the plateaus robustly on real, noisy data you find the **DTG
minima** between peaks (the points of slowest change). With **pandas** a
real trace loads in one line:

```python
import pandas as pd
df = pd.read_csv("tga_run.csv")            # temperature, mass_pct columns
```

The cell below measures each step from the synthetic trace, annotates the
mass loss on the curve, and summarises the composition as a **stacked
bar**.
"""


_STEPS = r'''
# Quantify composition from TGA step heights and show a stacked-bar
# breakdown. Synthetic data (no standard TGA Python library); a real
# trace would come from pd.read_csv of the instrument export.
import numpy as np
import matplotlib.pyplot as plt

rng = np.random.default_rng(0)
BLUE, ORANGE, GREEN = "#3776ab", "#e07b39", "#50bea0"


def sigmoid(T, T0, width):
    return 1.0 / (1.0 + np.exp(-(T - T0) / width))


# (label, centre T, width, mass loss %).
events = [
    ("moisture", 110.0, 12.0, 5.0),
    ("organic", 340.0, 25.0, 30.0),
    (r"carbonate (CO$_2$)", 650.0, 22.0, 20.0),
]
T = np.linspace(30.0, 900.0, 1000)
mass = np.full_like(T, 100.0)
for _, T0, w, loss in events:
    mass -= loss * sigmoid(T, T0, w)
mass += rng.normal(0.0, 0.05, T.size)

# Measure each step as the drop across its transition window (here a fixed
# +/- 90 C window around the known centre; on real data use DTG minima).
labels, losses, mids = [], [], []
for name, T0, w, _ in events:
    lo = mass[np.argmin(np.abs(T - (T0 - 90)))]
    hi = mass[np.argmin(np.abs(T - (T0 + 90)))]
    labels.append(name)
    losses.append(lo - hi)
    mids.append(T0)
residue = mass[-1]

fig, (axc, axb) = plt.subplots(1, 2, figsize=(9.2, 4.3),
                               gridspec_kw={"width_ratios": [2.1, 1.0]})

# Left: mass curve with each step's loss annotated.
axc.plot(T, mass, color=BLUE, lw=2)
for name, loss, Tm in zip(labels, losses, mids):
    axc.annotate(r"%s" % name + "\n" + r"$-%.0f$%%" % loss,
                 (Tm, mass[np.argmin(np.abs(T - Tm))]),
                 textcoords="offset points", xytext=(8, 18),
                 fontsize=8, color="0.25",
                 arrowprops=dict(arrowstyle="->", color="0.6", lw=0.8))
axc.set_xlabel(r"temperature ($^\circ$C)")
axc.set_ylabel(r"mass (%)")
axc.set_title("Step-by-step mass loss")

# Right: stacked-bar composition (the four assigned fractions).
comp_labels = labels + ["residue"]
comp_vals = losses + [residue]
colors = [BLUE, ORANGE, GREEN, "0.6"]
bottom = 0.0
for val, lab, col in zip(comp_vals, comp_labels, colors):
    axb.bar(0, val, bottom=bottom, width=0.6, color=col, label=lab)
    axb.text(0, bottom + val / 2.0, "%.0f%%" % val,
             ha="center", va="center", fontsize=8,
             color="white" if col != "0.6" else "0.1")
    bottom += val
axb.set_xlim(-0.6, 0.6)
axb.set_ylim(0, 100)
axb.set_xticks([])
axb.set_ylabel(r"composition (%)")
axb.set_title("Assigned composition")
axb.legend(loc="upper center", bbox_to_anchor=(0.5, -0.05),
           frameon=False, fontsize=7.5, ncol=2)

fig.suptitle("TGA decomposition steps and composition")
fig.tight_layout()
fig
'''


def _steps():
    return [_md(_STEPS_INTRO), _code(_STEPS)]


# -- 3. Kissinger kinetics ------------------------------------------------

_KISSINGER_INTRO = """\
# TGA kinetics — Kissinger method

The **activation energy** $E_a$ of a decomposition step can be extracted
without assuming a reaction model by running the TGA at **several heating
rates** $\\beta$ (in $^\\circ$C/min) and tracking how the **DTG peak
temperature** $T_p$ shifts. Faster heating gives the reaction less time
at each temperature, so the peak moves to **higher** $T_p$.

The **Kissinger** relation makes this quantitative:

$$\\ln\\!\\left(\\frac{\\beta}{T_p^{2}}\\right)
   = -\\frac{E_a}{R}\\,\\frac{1}{T_p} + \\text{const.}$$

So a plot of $\\ln(\\beta/T_p^{2})$ versus $1000/T_p$ is a **straight
line** whose slope is $-E_a/R$. With the gas constant $R = 8.314$
J/mol/K, $E_a = -\\text{slope} \\times R$.

A real study loads each rate's trace with **pandas** and reads off its
DTG peak; here we synthesise the peak shift directly. The cell builds the
Kissinger line, fits it with `np.polyfit`, and reports $E_a$ in kJ/mol.
"""


_KISSINGER = r'''
# Kissinger kinetics: DTG peak temperature vs heating rate -> activation
# energy. Synthetic data (no standard TGA Python library); each rate's
# trace would otherwise be a separate pd.read_csv from the instrument.
import numpy as np
import matplotlib.pyplot as plt

rng = np.random.default_rng(0)
BLUE, ORANGE, GREEN = "#3776ab", "#e07b39", "#50bea0"
R = 8.314                                   # gas constant (J/mol/K)


def sigmoid(T, T0, width):
    return 1.0 / (1.0 + np.exp(-(T - T0) / width))


# Ground-truth kinetics for one decomposition step.
Ea_true = 150e3                             # activation energy (J/mol)
A = 1.0e10                                  # pre-exponential (1/s)
betas = np.array([2.0, 5.0, 10.0, 20.0, 40.0])   # heating rates (C/min)

# For each heating rate, simulate the trace and find its DTG peak T_p.
Tp = []
for beta in betas:
    # Kissinger: peak when A*R*Tp^2/(beta*Ea) * exp(-Ea/(R*Tp)) = 1.
    # Solve by scanning temperature for the DTG maximum of a model step.
    T = np.linspace(400.0, 1100.0, 4000)    # absolute temperature (K)
    beta_s = beta / 60.0                     # C/min -> K/s
    k = A * np.exp(-Ea_true / (R * T))       # Arrhenius rate constant
    # Conversion via the standard first-order integral approximation.
    integ = np.cumsum(k) * (T[1] - T[0]) / beta_s
    alpha = 1.0 - np.exp(-integ)
    dadt = np.gradient(alpha, T)             # ~ DTG shape
    Tp.append(T[int(np.argmax(dadt))])
Tp = np.array(Tp) + rng.normal(0.0, 1.0, betas.size)   # small scatter

# Kissinger coordinates.
x = 1000.0 / Tp                              # 1000 / Tp  (1/K)
y = np.log(betas / Tp ** 2)                  # ln(beta / Tp^2)

try:
    slope, intercept = np.polyfit(x, y, 1)
except Exception:
    slope, intercept = -Ea_true / R / 1000.0, 0.0
# slope is d y / d(1000/Tp); multiply by 1000 to undo the 1000 scaling.
Ea_fit = -slope * R * 1000.0                 # J/mol
xline = np.linspace(x.min() * 0.98, x.max() * 1.02, 100)

fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(9.4, 4.3))

# Left: how the peak temperature shifts with heating rate.
ax1.plot(betas, Tp - 273.15, "o-", color=BLUE)
ax1.set_xlabel(r"heating rate $\beta$ ($^\circ$C/min)")
ax1.set_ylabel(r"DTG peak $T_p$ ($^\circ$C)")
ax1.set_title("Peak shifts with heating rate")

# Right: the Kissinger plot + fitted line.
ax2.plot(x, y, "o", color=BLUE, label="data")
ax2.plot(xline, slope * xline + intercept, "-", color=ORANGE,
         lw=2, label="fit")
ax2.set_xlabel(r"$1000/T_p$ (1/K)")
ax2.set_ylabel(r"$\ln(\beta/T_p^2)$")
ax2.set_title("Kissinger plot")
ax2.legend(loc="upper right", frameon=False)
ax2.text(0.05, 0.10, r"$E_a = %.0f$ kJ/mol" % (Ea_fit / 1000.0),
         transform=ax2.transAxes, fontsize=11, color="0.15",
         bbox=dict(boxstyle="round", fc="white", ec="0.8"))

fig.suptitle("TGA kinetics by the Kissinger method")
fig.tight_layout()
fig
'''


def _kissinger():
    return [_md(_KISSINGER_INTRO), _code(_KISSINGER)]


# -- 4. TGA-DSC -----------------------------------------------------------

_TGADSC_INTRO = """\
# Simultaneous TGA-DSC

A **simultaneous thermal analyser (STA)** records mass loss (TGA) and
**heat flow (DSC)** from the *same* sample at the same time, so thermal
events can be read against the mass change directly. The DSC trace shows
whether each event is **endothermic** (absorbs heat — dehydration,
melting, carbonate decomposition) or **exothermic** (releases heat —
oxidation, combustion, crystallisation).

Aligning the two curves is the whole point: a DSC peak that lines up with
a TGA step is a *mass-losing* reaction, whereas a DSC peak with **no**
accompanying mass change (e.g. a melt or a solid-state phase transition)
flags a physical transformation. By convention here, **exothermic is
plotted up**.

Both signals come from one STA export; load it with **pandas**:

```python
import pandas as pd
df = pd.read_csv("sta_run.csv")    # temperature, mass_pct, heat_flow
```

The cell below synthesises an aligned TGA + DSC pair and plots them on a
**twin axis**, tagging each event endo/exo.
"""


_TGADSC = r'''
# Simultaneous TGA (mass) + DSC (heat flow) on a twin axis, with each
# event tagged endo/exo. Synthetic data (no standard TGA Python library);
# a real STA export would be a single pd.read_csv with both columns.
import numpy as np
import matplotlib.pyplot as plt

rng = np.random.default_rng(0)
BLUE, ORANGE, GREEN = "#3776ab", "#e07b39", "#50bea0"


def sigmoid(T, T0, width):
    return 1.0 / (1.0 + np.exp(-(T - T0) / width))


def gauss(T, T0, width, amp):
    return amp * np.exp(-0.5 * ((T - T0) / width) ** 2)


T = np.linspace(30.0, 900.0, 1000)          # temperature (degrees C)

# Mass-losing events: (centre, width, loss %, heat-flow sign + amplitude).
# sign > 0 exothermic (up), sign < 0 endothermic (down).
events = [
    ("dehydration", 110.0, 12.0, 5.0, -0.8),    # endotherm, mass loss
    ("combustion", 360.0, 28.0, 30.0, +1.6),    # exotherm, mass loss
    ("decomposition", 660.0, 22.0, 20.0, -1.1),  # endotherm, mass loss
]

mass = np.full_like(T, 100.0)
heat = np.zeros_like(T)                      # DSC heat flow (exo up)
for _, T0, w, loss, sign in events:
    mass -= loss * sigmoid(T, T0, w)
    heat += gauss(T, T0, w, sign)
# A purely physical melt: DSC endotherm with NO mass change.
heat += gauss(T, 500.0, 8.0, -0.7)
mass += rng.normal(0.0, 0.05, T.size)
heat += rng.normal(0.0, 0.01, T.size)

fig, ax1 = plt.subplots(figsize=(6.6, 4.5))
ax1.plot(T, mass, color=BLUE, lw=2)
ax1.set_xlabel(r"temperature ($^\circ$C)")
ax1.set_ylabel(r"mass (%)", color=BLUE)
ax1.tick_params(axis="y", labelcolor=BLUE)

ax2 = ax1.twinx()
ax2.plot(T, heat, color=ORANGE, lw=1.8)
ax2.axhline(0.0, color="0.7", lw=0.8)
ax2.set_ylabel(r"heat flow (W/g, exo $\uparrow$)", color=ORANGE)
ax2.tick_params(axis="y", labelcolor=ORANGE)

# Tag each DSC event endo/exo at its peak.
for name, T0, w, loss, sign in events:
    i = int(np.argmin(np.abs(T - T0)))
    tag = "exo" if sign > 0 else "endo"
    ax2.annotate("%s\n%s" % (name, tag), (T[i], heat[i]),
                 textcoords="offset points",
                 xytext=(0, 10 if sign > 0 else -22),
                 ha="center", fontsize=7.5, color="0.25")
i_melt = int(np.argmin(np.abs(T - 500.0)))
ax2.annotate("melt\nendo (no mass loss)", (T[i_melt], heat[i_melt]),
             textcoords="offset points", xytext=(0, -28),
             ha="center", fontsize=7.5, color=GREEN)

ax1.set_title("Simultaneous TGA-DSC")
fig.tight_layout()
fig
'''


def _tga_dsc():
    return [_md(_TGADSC_INTRO), _code(_TGADSC)]


# -- 5. Conversion & Arrhenius --------------------------------------------

_ARRHENIUS_INTRO = """\
# TGA conversion & Arrhenius analysis

For a single decomposition step the mass curve converts directly into the
**extent of reaction** (conversion) $\\alpha$:

$$\\alpha(T) = \\frac{m_0 - m(T)}{m_0 - m_f},$$

running from 0 (reaction not started) to 1 (complete), where $m_0$ and
$m_f$ are the masses before and after the step. The **reaction rate**
$\\mathrm{d}\\alpha/\\mathrm{d}t$ then follows from the heating rate.

Assuming first-order kinetics, $\\mathrm{d}\\alpha/\\mathrm{d}t =
k(T)\\,(1-\\alpha)$, the rate constant is $k = (\\mathrm{d}\\alpha/
\\mathrm{d}t)/(1-\\alpha)$. The **Arrhenius** law $k = A\\,e^{-E_a/RT}$
then linearises as

$$\\ln k = \\ln A - \\frac{E_a}{R}\\,\\frac{1}{T},$$

so $\\ln k$ versus $1/T$ is a straight line of slope $-E_a/R$ — a second,
single-run route to $E_a$ (gas constant $R = 8.314$ J/mol/K).

A real trace loads with **pandas** (`pd.read_csv`); here we synthesise one
step, build $\\alpha(T)$, and fit the Arrhenius line with `np.polyfit`.
"""


_ARRHENIUS = r'''
# Conversion alpha(T), reaction rate, and an Arrhenius plot for E_a.
# Synthetic single-step data (no standard TGA Python library); a real run
# would be loaded with pd.read_csv from the instrument export.
import numpy as np
import matplotlib.pyplot as plt

rng = np.random.default_rng(0)
BLUE, ORANGE, GREEN = "#3776ab", "#e07b39", "#50bea0"
R = 8.314                                    # gas constant (J/mol/K)

# Simulate one first-order decomposition step under linear heating.
Ea_true = 130e3                              # activation energy (J/mol)
A = 1.0e9                                    # pre-exponential (1/s)
beta = 10.0 / 60.0                           # heating rate 10 C/min -> K/s

T = np.linspace(450.0, 850.0, 6000)          # absolute temperature (K)
k_true = A * np.exp(-Ea_true / (R * T))
# Cumulative-trapezoid integral of k/beta gives the conversion exponent.
integ = np.concatenate(([0.0], np.cumsum(0.5 * (k_true[1:] + k_true[:-1])
                                         * np.diff(T)))) / beta
alpha_clean = 1.0 - np.exp(-integ)           # conversion 0 -> 1
alpha = np.clip(alpha_clean + rng.normal(0.0, 0.002, T.size),
                1e-5, 1 - 1e-5)

# Reaction rate and first-order rate constant from the data. A light
# smoothing of the noisy conversion keeps the numerical derivative — and
# hence the recovered rate constant — well conditioned.
win = 51
kern = np.ones(win) / win
a_s = np.convolve(alpha, kern, mode="same")
a_s[: win] = alpha_clean[: win]              # edges: fall back to clean
a_s[-win:] = alpha_clean[-win:]
dadt = np.gradient(a_s, T) * beta            # dalpha/dt  (1/s)
with np.errstate(divide="ignore", invalid="ignore"):
    k = dadt / (1.0 - a_s)                     # k = rate / (1 - alpha)

# Arrhenius fit over the well-defined middle of the step (0.1 < a < 0.9).
sel = (a_s > 0.1) & (a_s < 0.9) & (k > 0)
invT = 1.0 / T[sel]
lnk = np.log(k[sel])
try:
    slope, intercept = np.polyfit(invT, lnk, 1)
except Exception:
    slope, intercept = -Ea_true / R, np.log(A)
Ea_fit = -slope * R                           # J/mol

fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(9.4, 4.3))

# Left: conversion alpha(T) and the reaction rate.
ax1.plot(T - 273.15, alpha, color=BLUE, lw=2, label=r"$\alpha$")
ax1.set_xlabel(r"temperature ($^\circ$C)")
ax1.set_ylabel(r"conversion $\alpha$", color=BLUE)
ax1.tick_params(axis="y", labelcolor=BLUE)
axr = ax1.twinx()
axr.plot(T - 273.15, dadt, color=GREEN, lw=1.5)
axr.set_ylabel(r"rate $\mathrm{d}\alpha/\mathrm{d}t$ (1/s)", color=GREEN)
axr.tick_params(axis="y", labelcolor=GREEN)
ax1.set_title(r"Conversion $\alpha(T)$ and rate")

# Right: Arrhenius plot ln(k) vs 1/T.
ax2.plot(invT * 1000.0, lnk, "o", ms=3, color=BLUE, label="data")
ax2.plot(invT * 1000.0, slope * invT + intercept, "-", color=ORANGE,
         lw=2, label="fit")
ax2.set_xlabel(r"$1000/T$ (1/K)")
ax2.set_ylabel(r"$\ln k$")
ax2.set_title("Arrhenius plot")
ax2.legend(loc="upper right", frameon=False)
ax2.text(0.05, 0.10, r"$E_a = %.0f$ kJ/mol" % (Ea_fit / 1000.0),
         transform=ax2.transAxes, fontsize=11, color="0.15",
         bbox=dict(boxstyle="round", fc="white", ec="0.8"))

fig.suptitle("TGA conversion & Arrhenius analysis")
fig.tight_layout()
fig
'''


def _arrhenius():
    return [_md(_ARRHENIUS_INTRO), _code(_ARRHENIUS)]


# -- Registry --------------------------------------------------------------

TGA_EXAMPLES = [
    # (name, category, builder)
    ("TGA Mass Loss & DTG (TGA)", "TGA", _massloss),
    ("TGA Decomposition Steps (TGA)", "TGA", _steps),
    ("TGA Kinetics (Kissinger) (TGA)", "TGA", _kissinger),
    ("TGA-DSC (TGA)", "TGA", _tga_dsc),
    ("TGA Conversion & Arrhenius (TGA)", "TGA", _arrhenius),
]
