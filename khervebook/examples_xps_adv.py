"""Advanced XPS technique examples (depth profile, ARXPS, Auger parameter).

A self-contained companion to ``examples.py`` (Examples menu, "XPS"
category). The three examples cover everyday quantitative X-ray
photoelectron spectroscopy beyond a single survey scan:

* **Sputter depth profiling** — Ar+ ion etching peels the sample layer
  by layer while XPS tracks the atomic concentration of each element,
  revealing the depth distribution of a native-oxide/contamination
  stack.
* **Angle-resolved XPS (ARXPS)** — a non-destructive overlayer-thickness
  measurement: the substrate signal is attenuated through the overlayer
  following Beer-Lambert, so the overlayer/substrate intensity ratio
  versus emission angle yields the thickness.
* **Auger parameter / Wagner plot** — chemical-state identification from
  the modified Auger parameter, which is immune to surface-charging
  shifts.

Every code cell uses only NumPy, matplotlib and (where a fit is needed)
``scipy.optimize.curve_fit`` so each example always runs offline. The
module top level is standard-library only; the scientific imports live
inside the code cells.

This module defines its own ``_md``/``_code`` helpers and exports
``XPS_ADV_EXAMPLES`` so it merges into ``examples.py`` without a circular
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


# -- 1. Sputter depth profile ---------------------------------------------

_DEPTH_INTRO = """\
# XPS sputter depth profiling

A single XPS measurement only probes the top few nanometres of a sample
(the photoelectron escape depth). To see how composition changes with
**depth**, the surface is eroded in steps with an **Ar+ ion gun** and a
spectrum is recorded after each etch — *sputter depth profiling*. Plotting
the **atomic concentration** of every element against sputter time (or, via
the known etch rate, against **etch depth**) reveals the layer structure.

A very common stack on an air-exposed metal is:

1. a thin **adventitious carbon / contamination** layer at the very top,
2. a **native oxide** rich in oxygen, and
3. the **metal substrate** *M* underneath.

The cell below models this trilayer. Each element's concentration follows a
smooth **sigmoid** transition between layers (interfaces are never perfectly
sharp because of mixing and the finite information depth), with a little
detector noise added. The total is renormalised to 100 % at every point,
exactly as a real *atomic %* depth profile is reported.
"""


_DEPTH_PROFILE = r'''
# XPS Ar+ sputter depth profile of a native-oxide / contamination stack on
# a metal. Each element's atomic % follows a smooth sigmoid across each
# interface; the columns are renormalised to 100 % at every depth, as in a
# real quantified profile.
import numpy as np
import matplotlib.pyplot as plt

rng = np.random.default_rng(0)

etch_rate = 0.5                         # nm per minute of Ar+ sputtering
t = np.linspace(0.0, 20.0, 400)        # sputter time (min)
depth = etch_rate * t                  # etch depth (nm)


def sigmoid(x, x0, w):
    """Smooth 0->1 step centred at x0 with transition width w."""
    return 1.0 / (1.0 + np.exp(-(x - x0) / w))


# Layer boundaries in etch depth (nm) and interface widths.
d_c_ox = 1.5                           # carbon -> oxide interface
d_ox_m = 5.0                           # oxide  -> metal interface
w = 0.6                                # interface broadening (nm)

# Carbon contamination: high at the surface, gone after the first interface.
C = 60.0 * (1.0 - sigmoid(depth, d_c_ox, w))

# Oxygen: low under the carbon, peaks in the oxide, falls into the metal.
O = 55.0 * sigmoid(depth, d_c_ox, w) * (1.0 - sigmoid(depth, d_ox_m, w))

# Metal M: traces near the surface, rises to bulk through the oxide.
M = 90.0 * sigmoid(depth, d_ox_m - 1.5, 1.1) + 8.0 * sigmoid(depth, d_c_ox, w)

# Detector noise, then renormalise to atomic % (each column sums to 100).
stack = np.vstack([C, O, M]).astype(float)
stack += rng.normal(0.0, 1.2, stack.shape)
stack = np.clip(stack, 0.0, None)
stack = 100.0 * stack / stack.sum(axis=0, keepdims=True)
C, O, M = stack

fig, ax = plt.subplots(figsize=(6.2, 4.3))
ax.stackplot(depth, C, O, M,
             labels=["C 1s (contamination)", "O 1s (oxide)", "M 2p (metal)"],
             colors=["#7a7a7a", "#e07b39", "#3776ab"], alpha=0.85)

# Annotate the three layer regions along the depth axis.
ax.axvline(d_c_ox, color="0.25", ls="--", lw=0.9)
ax.axvline(d_ox_m, color="0.25", ls="--", lw=0.9)
ax.text(d_c_ox / 2, 92, "contamination", ha="center", fontsize=8, color="0.15")
ax.text((d_c_ox + d_ox_m) / 2, 92, "native oxide", ha="center", fontsize=8,
        color="0.15")
ax.text((d_ox_m + depth.max()) / 2, 92, "metal\nsubstrate", ha="center",
        fontsize=8, color="white")

ax.set_xlim(depth.min(), depth.max())
ax.set_ylim(0, 100)
ax.set_xlabel("etch depth (nm)   [%.1f nm/min Ar+]" % etch_rate)
ax.set_ylabel("atomic concentration (%)")
ax.set_title("XPS sputter depth profile")
ax.legend(loc="center right", frameon=False, fontsize=8)

# Secondary axis: the raw experimental quantity, sputter time.
secax = ax.secondary_xaxis(
    "top", functions=(lambda d: d / etch_rate, lambda s: s * etch_rate))
secax.set_xlabel("sputter time (min)")

fig.tight_layout()
fig
'''


def _depth_profile():
    return [_md(_DEPTH_INTRO), _code(_DEPTH_PROFILE)]


# -- 2. Angle-resolved XPS (ARXPS) ----------------------------------------

_ARXPS_INTRO = """\
# Angle-resolved XPS (ARXPS): overlayer thickness

ARXPS measures **overlayer thickness non-destructively** by tilting the
sample instead of sputtering it. Photoelectrons leaving at an emission angle
$\\theta$ from the surface normal travel a longer path through the overlayer,
$d/\\cos\\theta$, so the buried **substrate** signal is attenuated following
the Beer-Lambert law:

$$I_{sub} \\propto \\exp\\!\\left(-\\frac{d}{\\lambda\\cos\\theta}\\right),
\\qquad
I_{over} \\propto 1 - \\exp\\!\\left(-\\frac{d}{\\lambda\\cos\\theta}\\right)$$

where $d$ is the overlayer thickness and $\\lambda$ is the inelastic mean
free path (IMFP) of the photoelectrons (a few nm). At **grazing emission**
(large $\\theta$) the path lengthens, the substrate is suppressed and the
measurement becomes **more surface sensitive**.

Taking the **overlayer/substrate intensity ratio** cancels the instrument
factors, leaving the textbook **Strohmeier** expression:

$$\\frac{I_{over}}{I_{sub}}
= \\exp\\!\\left(\\frac{d}{\\lambda\\cos\\theta}\\right) - 1.$$

The cell below synthesises this ratio versus angle with noise and fits it
with `scipy.optimize.curve_fit` to recover $d$, using a known IMFP
$\\lambda$.
"""


_ARXPS_FIT = r'''
# ARXPS overlayer-thickness fit. The overlayer/substrate intensity ratio
# follows the Strohmeier form exp(d / (lambda*cos(theta))) - 1; we make
# noisy data at a known true thickness and fit it back with scipy so the
# example always runs.
import numpy as np
import matplotlib.pyplot as plt
from scipy.optimize import curve_fit

rng = np.random.default_rng(0)

lam = 2.5                              # inelastic mean free path lambda (nm)
d_true = 3.2                           # true overlayer thickness (nm)

theta_deg = np.linspace(0.0, 75.0, 24)   # emission angle from normal (deg)
theta = np.radians(theta_deg)


def ratio_model(theta_rad, d):
    """Overlayer/substrate intensity ratio (Strohmeier); lambda is known."""
    return np.exp(d / (lam * np.cos(theta_rad))) - 1.0


clean = ratio_model(theta, d_true)
# Multiplicative + additive noise, as in a real intensity ratio.
ratio = clean * (1.0 + rng.normal(0.0, 0.05, theta.size)) \
    + rng.normal(0.0, 0.03, theta.size)
ratio = np.clip(ratio, 1e-3, None)

# Fit for the thickness d. Fall back to the initial guess if the fit fails.
try:
    popt, _ = curve_fit(ratio_model, theta, ratio, p0=[1.0], maxfev=20000)
    d_fit = float(popt[0])
except Exception:
    d_fit = 1.0

theta_fine = np.radians(np.linspace(0.0, 75.0, 300))
fit_curve = ratio_model(theta_fine, d_fit)

fig, ax = plt.subplots(figsize=(6.0, 4.3))
ax.plot(theta_deg, ratio, "o", ms=5, color="#3776ab", label="data")
ax.plot(np.degrees(theta_fine), fit_curve, "-", color="#e07b39", lw=2,
        label="Strohmeier fit")
ax.set_xlabel(r"emission angle  $\theta$  (deg from normal)")
ax.set_ylabel(r"intensity ratio  $I_{over}/I_{sub}$")
ax.set_title("Angle-resolved XPS overlayer thickness")
ax.legend(loc="upper left", frameon=False)
ax.annotate("more surface sensitive\nat grazing angles",
            xy=(70, ratio_model(np.radians(70), d_fit)),
            xytext=(38, ratio_model(np.radians(70), d_fit) * 0.85),
            fontsize=8, color="0.3", ha="center",
            arrowprops=dict(arrowstyle="->", color="0.5", lw=0.9))
ax.text(0.03, 0.62,
        r"$\lambda = %.1f$ nm (known)" % lam + "\n"
        + r"recovered $d = %.2f$ nm" % d_fit + "\n"
        + r"(true $d = %.2f$ nm)" % d_true,
        transform=ax.transAxes, va="top", fontsize=9,
        bbox=dict(boxstyle="round", fc="white", ec="0.8"))
fig.tight_layout()
fig
'''


def _arxps():
    return [_md(_ARXPS_INTRO), _code(_ARXPS_FIT)]


# -- 3. Auger parameter / Wagner plot -------------------------------------

_WAGNER_INTRO = """\
# Auger parameter & the Wagner plot

The chemical state of an element shifts both its **photoelectron** binding
energy $E_B$ and the **kinetic energy** of its sharpest **Auger** line.
Combining them gives the **modified Auger parameter**:

$$\\alpha' = E_B(\\text{photoelectron}) + E_K(\\text{Auger}).$$

Because $\\alpha'$ adds a binding energy to a kinetic energy, any rigid
**charge-referencing error** (which shifts both energy scales by the same
amount in opposite directions) **cancels exactly**. That makes $\\alpha'$ a
robust, reference-free fingerprint of chemical state — invaluable for
insulators that charge under X-rays.

A **Wagner (chemical-state) plot** puts photoelectron binding energy on the
*x*-axis (increasing to the left, by convention) and Auger kinetic energy on
the *y*-axis. Each chemical state is one point. Lines of **constant** $\\alpha'$
satisfy $E_K = \\alpha' - E_B$, i.e. **diagonals of slope -1**. The cell
below plots three states of a metal (metallic, oxide, hydroxide) and the
$\\alpha'$ grid lines they fall on.
"""


_WAGNER_PLOT = r'''
# Wagner chemical-state plot. Several chemical states of one element are
# placed by their photoelectron binding energy (x) and Auger kinetic
# energy (y); constant-Auger-parameter lines are diagonals of slope -1
# (E_K = alpha' - E_B).
import numpy as np
import matplotlib.pyplot as plt

# Representative chemical states: (label, E_B photoelectron, E_K Auger) in eV.
states = [
    ("metal",     1021.8, 988.7),
    ("oxide",     1022.6, 985.8),
    ("hydroxide", 1023.5, 984.0),
]
labels = [s[0] for s in states]
EB = np.array([s[1] for s in states])     # photoelectron binding energy (eV)
EK = np.array([s[2] for s in states])     # Auger kinetic energy (eV)
alpha = EB + EK                            # modified Auger parameter alpha'

fig, ax = plt.subplots(figsize=(6.0, 4.6))

# Constant-alpha' grid: E_K = alpha' - E_B  (diagonals of slope -1).
eb_lo, eb_hi = EB.min() - 1.2, EB.max() + 1.2
ek_lo, ek_hi = EK.min() - 1.6, EK.max() + 1.6
a_lines = np.arange(np.floor(alpha.min()) - 1, np.ceil(alpha.max()) + 2, 1.0)
eb_line = np.array([eb_lo, eb_hi])
for a in a_lines:
    ek_line = a - eb_line
    ax.plot(eb_line, ek_line, color="0.8", lw=0.8, zorder=1)
    # Label each diagonal where it leaves the top of the plotting window.
    eb_at_top = a - ek_hi
    if eb_lo <= eb_at_top <= eb_hi:
        ax.text(eb_at_top, ek_hi, r"$\alpha'=%.0f$" % a, fontsize=7,
                color="0.5", ha="center", va="bottom", rotation=-45)

# The measured chemical states.
ax.scatter(EB, EK, s=70, color="#3776ab", zorder=3, edgecolor="white")
for lab, x, y, a in zip(labels, EB, EK, alpha):
    ax.annotate(r"%s ($\alpha'=%.1f$)" % (lab, a), xy=(x, y),
                xytext=(6, 6), textcoords="offset points",
                fontsize=9, color="#e07b39", zorder=4)

ax.set_xlim(eb_hi, eb_lo)              # binding energy increases to the left
ax.set_ylim(ek_lo, ek_hi)
ax.set_xlabel(r"photoelectron binding energy  $E_B$  (eV)")
ax.set_ylabel(r"Auger kinetic energy  $E_K$  (eV)")
ax.set_title(r"Wagner plot: $\alpha' = E_B + E_K$")
fig.tight_layout()
fig
'''


def _wagner():
    return [_md(_WAGNER_INTRO), _code(_WAGNER_PLOT)]


# -- Registry --------------------------------------------------------------

XPS_ADV_EXAMPLES = [
    # (name, category, builder)
    ("XPS Depth Profile (XPS)", "XPS", _depth_profile),
    ("Angle-Resolved XPS (XPS)", "XPS", _arxps),
    ("Auger Parameter / Wagner Plot (XPS)", "XPS", _wagner),
]
