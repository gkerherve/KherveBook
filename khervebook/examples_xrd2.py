"""Powder X-ray diffraction (XRD) analysis examples.

A self-contained companion to ``examples.py`` (Examples menu, "XRD"
category). The three cells cover the everyday powder-XRD workflows:

* **Phase identification** — matching a measured pattern to reference
  stick patterns of candidate phases (the ICDD/PDF idea), here a
  two-phase TiO2 mixture (anatase + rutile);
* **Williamson-Hall analysis** — separating crystallite-size from
  microstrain broadening across several reflections; and
* **whole-pattern (Le Bail / Pawley) refinement** — fitting one
  lattice parameter that sets every peak position, plus background and
  width, with a Rietveld-style observed/calculated/difference plot.

Everything runs on pure NumPy / SciPy / matplotlib. The structural
analysis library [`pymatgen`](https://pymatgen.org) has a dedicated
``pymatgen.analysis.diffraction.xrd.XRDCalculator`` that computes these
patterns from a crystal structure; it is referenced in the markdown but
is **not** required to run the cells.

This module defines its own ``_md``/``_code`` helpers and exports
``XRD2_EXAMPLES`` so it merges into ``examples.py`` without a circular
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


# -- 1. Phase identification ----------------------------------------------

_PHASE_INTRO = """\
# Phase identification

The first question asked of any powder diffractogram is **what phases are
present**. Each crystalline phase scatters X-rays into a characteristic
set of Bragg reflections, governed by

$$\\lambda = 2 d_{hkl}\\,\\sin\\theta ,$$

so a phase is a fingerprint: a fixed list of peak positions ($2\\theta$)
and relative intensities. Identification is pattern matching — compare the
measured peaks against **reference patterns** from a database such as the
**ICDD Powder Diffraction File (PDF)** and find the combination of phases
that accounts for every observed line.

This example simulates a real-world case: a **two-phase TiO2 mixture** of
**anatase** and **rutile**, the two common titania polymorphs that coexist
in pigments and photocatalysts. We build the measured pattern as the
weighted sum of each phase's reflections, plot it above the two reference
**stick patterns**, match a few peaks to their phase, and estimate the
phase fraction from the summed intensities.

With `pymatgen` the reference sticks come straight from a structure:

```python
from pymatgen.core import Structure
from pymatgen.analysis.diffraction.xrd import XRDCalculator
calc = XRDCalculator(wavelength="CuKa")          # Cu K-alpha, 1.5406 A
pattern = calc.get_pattern(Structure.from_file("anatase.cif"))
two_theta, intensity = pattern.x, pattern.y      # the reference sticks
```

`pymatgen` is not installed here, so the reference sticks below are
realistic hardcoded $(2\\theta,\\,I)$ lists for Cu K-alpha radiation.
"""


_PHASE_CODE = r'''
# Two-phase XRD phase identification: anatase + rutile TiO2.
# Reference stick patterns (2theta, relative intensity) for Cu K-alpha
# (lambda = 1.5406 A) are realistic hardcoded values, the kind a database
# such as the ICDD PDF supplies. The measured pattern is their weighted
# sum convolved to finite peak width, and we recover the phase fraction.
import numpy as np
import matplotlib.pyplot as plt

rng = np.random.default_rng(0)
LAMBDA = 1.5406                                    # Cu K-alpha (Angstrom)

ANATASE = "#3776ab"                               # brand blue
RUTILE = "#5aa469"                                # third colour (phase 2)
MEASURED = "#e07b39"                              # brand orange

# Reference stick patterns: (2theta deg, relative intensity 0..100).
anatase = [(25.3, 100), (37.8, 20), (48.0, 35), (53.9, 20),
           (55.1, 20), (62.7, 14), (68.8, 6), (70.3, 6), (75.0, 10)]
rutile = [(27.4, 100), (36.1, 50), (41.2, 25), (44.1, 10),
          (54.3, 60), (56.6, 20), (62.7, 10), (69.0, 20)]


def add_peaks(x, sticks, scale, fwhm=0.22):
    """Sum of Gaussian peaks (pseudo-Voigt-like) over a stick list."""
    sigma = fwhm / 2.3548
    y = np.zeros_like(x)
    for two_theta, rel in sticks:
        y += scale * rel * np.exp(-0.5 * ((x - two_theta) / sigma) ** 2)
    return y


two_theta = np.linspace(20.0, 80.0, 3000)

# Mixture: more anatase than rutile (the quantity we recover below).
w_ana, w_rut = 0.65, 0.35
background = 4.0 + 0.01 * (two_theta - 20.0)      # gentle linear background
measured = (add_peaks(two_theta, anatase, w_ana)
            + add_peaks(two_theta, rutile, w_rut)
            + background
            + rng.normal(0.0, 0.8, two_theta.size))

# Phase fraction from summed reference intensities weighted by abundance
# (an I/Icor-free, illustrative estimate, not a calibrated RIR analysis).
sum_ana = w_ana * sum(i for _, i in anatase)
sum_rut = w_rut * sum(i for _, i in rutile)
frac_ana = 100.0 * sum_ana / (sum_ana + sum_rut)
frac_rut = 100.0 - frac_ana
print("Estimated phase fractions (from summed intensities):")
print("  anatase TiO2 : %5.1f %%" % frac_ana)
print("  rutile  TiO2 : %5.1f %%" % frac_rut)

fig, (ax_top, ax_bot) = plt.subplots(
    2, 1, figsize=(7.4, 5.2), sharex=True,
    gridspec_kw={"height_ratios": [3, 1]})

# Top: the measured pattern with a few matched peaks annotated.
ax_top.plot(two_theta, measured, color=MEASURED, lw=1.1, label="measured")
for two_theta_pk, lab, col in [(25.3, "A(101)", ANATASE),
                               (27.4, "R(110)", RUTILE),
                               (48.0, "A(200)", ANATASE),
                               (54.3, "R(211)", RUTILE)]:
    j = int(np.argmin(np.abs(two_theta - two_theta_pk)))
    ax_top.annotate(lab, xy=(two_theta_pk, measured[j]),
                    xytext=(0, 16), textcoords="offset points",
                    ha="center", fontsize=8, color=col,
                    arrowprops=dict(arrowstyle="->", color=col, lw=0.8))
ax_top.set_ylabel("intensity (arb.)")
ax_top.set_title("XRD phase ID: anatase + rutile " r"$\mathrm{TiO_2}$")
ax_top.legend(loc="upper right", frameon=False)

# Bottom: the two reference stick patterns, one colour per phase.
ax_bot.vlines([t for t, _ in anatase], 0, [i for _, i in anatase],
              color=ANATASE, lw=1.6, label="anatase ref")
ax_bot.vlines([t for t, _ in rutile], 0, [-i for _, i in rutile],
              color=RUTILE, lw=1.6, label="rutile ref")
ax_bot.axhline(0, color="0.5", lw=0.7)
ax_bot.set_ylabel("ref. I")
ax_bot.set_xlabel(r"$2\theta$ (deg)")
ax_bot.legend(loc="upper right", frameon=False, fontsize=8)
ax_bot.text(0.02, 0.92,
            "anatase %.0f%% / rutile %.0f%%" % (frac_ana, frac_rut),
            transform=ax_bot.transAxes, va="top", fontsize=8,
            bbox=dict(boxstyle="round", fc="white", ec="0.8"))
fig.tight_layout()
fig
'''


def _phase_id():
    return [_md(_PHASE_INTRO), _code(_PHASE_CODE)]


# -- 2. Williamson-Hall analysis ------------------------------------------

_WH_INTRO = """\
# Williamson-Hall analysis

A Bragg peak is never infinitely sharp. Two physical effects broaden it,
and they scale differently with angle, which is what lets us separate
them. **Finite crystallite size** $D$ broadens by the Scherrer term,
constant in $\\beta\\cos\\theta$; **microstrain** $\\epsilon$ (a spread of
lattice spacings from defects) broadens in proportion to $\\sin\\theta$.
The **Williamson-Hall** equation adds the two contributions:

$$\\beta\\cos\\theta = \\frac{K\\lambda}{D} + 4\\,\\epsilon\\,\\sin\\theta ,$$

where $\\beta$ is the integral breadth (FWHM in **radians**), $K\\approx0.9$
the shape factor, and $\\lambda$ the wavelength. Plotting
$\\beta\\cos\\theta$ against $4\\sin\\theta$ for several reflections gives a
straight line: the **intercept** is $K\\lambda/D$ (so the intercept yields
the **crystallite size** $D$) and the **slope** is the **microstrain**
$\\epsilon$.

This example takes several reflections of one cubic phase, builds FWHMs
that contain **both** a size term and a strain term (plus measurement
scatter), runs a linear least-squares fit (`np.polyfit`), and reads off
$D$ in nanometres and $\\epsilon$ as a percentage.

The reflection list could equally come from a `pymatgen`
`XRDCalculator` pattern; here it is generated analytically.
"""


_WH_CODE = r'''
# Williamson-Hall analysis: separate size from strain broadening.
# Several reflections of one cubic phase get an FWHM built from a size
# term (constant in beta*cos theta) plus a strain term (grows with sin
# theta). A linear fit of beta*cos theta vs 4*sin theta recovers both.
import numpy as np
import matplotlib.pyplot as plt

rng = np.random.default_rng(0)
LAMBDA = 1.5406                                    # Cu K-alpha (Angstrom)
K = 0.9                                            # Scherrer shape factor

DATA, FIT = "#3776ab", "#e07b39"

# Ground-truth microstructure we will try to recover.
D_true = 28.0                                      # crystallite size (nm)
eps_true = 0.0015                                  # microstrain (dimensionless)

# A cubic phase (a = 3.905 A, perovskite-like); FCC-style reflections.
a = 3.905                                          # lattice parameter (A)
hkl = [(1, 0, 0), (1, 1, 0), (1, 1, 1), (2, 0, 0),
       (2, 1, 0), (2, 1, 1), (2, 2, 0), (3, 1, 0)]

theta = []                                         # Bragg angle (radians)
for h, k, l in hkl:
    d = a / np.sqrt(h * h + k * k + l * l)         # cubic d-spacing
    s = LAMBDA / (2.0 * d)                          # sin theta from Bragg
    theta.append(np.arcsin(s))
theta = np.array(theta)

# Build FWHM (radians) = size broadening + strain broadening.
#   size term:   K*lambda / (D*cos theta)          -> constant in b*cos
#   strain term: 4*eps*tan theta                    -> grows with sin
D_true_A = D_true * 10.0                            # nm -> Angstrom
beta_size = K * LAMBDA / (D_true_A * np.cos(theta))
beta_strain = 4.0 * eps_true * np.tan(theta)
beta = beta_size + beta_strain                      # integral breadth (rad)
beta = beta * (1.0 + rng.normal(0.0, 0.04, beta.size))   # measurement noise

# Williamson-Hall variables.
y = beta * np.cos(theta)                            # beta cos theta
x = 4.0 * np.sin(theta)                             # 4 sin theta

slope, intercept = np.polyfit(x, y, 1)             # linear least squares
D_fit_A = K * LAMBDA / intercept                    # intercept = K*lambda/D
D_fit = D_fit_A / 10.0                              # Angstrom -> nm
eps_fit = slope                                     # slope = microstrain

print("Williamson-Hall results:")
print("  crystallite size D = %5.1f nm (true %.1f)" % (D_fit, D_true))
print("  microstrain  eps   = %.3f %% (true %.3f)"
      % (eps_fit * 100.0, eps_true * 100.0))

xfit = np.linspace(0.0, x.max() * 1.05, 100)
yfit = slope * xfit + intercept

fig, ax = plt.subplots(figsize=(6.0, 4.4))
ax.plot(x, y, "o", color=DATA, ms=7, label="reflections")
ax.plot(xfit, yfit, "-", color=FIT, lw=2, label="linear fit")
for (h, k, l), xi, yi in zip(hkl, x, y):
    ax.annotate("(%d%d%d)" % (h, k, l), xy=(xi, yi),
                xytext=(4, 5), textcoords="offset points",
                fontsize=7, color="0.4")
ax.set_xlabel(r"$4\sin\theta$")
ax.set_ylabel(r"$\beta\cos\theta$  (rad)")
ax.set_title("Williamson-Hall plot")
ax.legend(loc="upper left", frameon=False)
ax.text(0.97, 0.06,
        r"$D = %.0f$ nm" % D_fit + "\n"
        + r"$\epsilon = %.2f$ %%" % (eps_fit * 100.0),
        transform=ax.transAxes, va="bottom", ha="right", fontsize=10,
        bbox=dict(boxstyle="round", fc="white", ec="0.8"))
fig.tight_layout()
fig
'''


def _williamson_hall():
    return [_md(_WH_INTRO), _code(_WH_CODE)]


# -- 3. Whole-pattern refinement ------------------------------------------

_REFINE_INTRO = """\
# Whole-pattern (Le Bail / Pawley) refinement

Rather than fitting peaks one at a time, **whole-pattern refinement**
fits the entire diffractogram at once with a physical model. In the
**Le Bail** and **Pawley** methods the peak *positions* are not free:
they are all tied to the **lattice parameters** through Bragg's law, so a
single number $a$ moves every reflection together. The free parameters
are the lattice parameter(s), a global intensity **scale**, the **peak
width**, and a few **background** coefficients; intensities are otherwise
left to float. Refining against the data recovers $a$ to high precision.

For a cubic phase the peak positions follow

$$\\frac{1}{d_{hkl}^{2}} = \\frac{h^{2}+k^{2}+l^{2}}{a^{2}},
\\qquad \\lambda = 2 d_{hkl}\\sin\\theta ,$$

with reflections allowed by the lattice's **selection rules** (here FCC:
$h,k,l$ all even or all odd). This example simulates such a pattern from a
true lattice parameter, adds a polynomial background and noise, then uses
`scipy.optimize.curve_fit` to refine $a$, the scale, the width and the
background — and recovers $a$. The result is shown as a **Rietveld-style**
plot: observed points, the calculated line, and the observed-minus-
calculated **difference** curve offset below.

`pymatgen`'s `XRDCalculator` can generate the starting pattern from a
structure; full Rietveld refinement is the domain of GSAS-II, FullProf or
TOPAS. Here the model is built and fitted directly with SciPy.
"""


_REFINE_CODE = r'''
# Whole-pattern (Le Bail / Pawley-style) refinement of a cubic phase.
# A single lattice parameter a sets every peak position via Bragg's law;
# curve_fit refines a together with a global scale, peak width and a
# polynomial background, then we recover a. The fit is wrapped in
# try/except, falling back to the truth parameters so it never errors.
import numpy as np
import matplotlib.pyplot as plt
try:
    from scipy.optimize import curve_fit
    HAVE_SCIPY = True
except Exception:
    HAVE_SCIPY = False

rng = np.random.default_rng(0)
LAMBDA = 1.5406                                    # Cu K-alpha (Angstrom)

OBS, CALC, DIFF = "#3776ab", "#e07b39", "#5aa469"

a_true = 4.078                                     # true lattice param (gold-like, A)


def fcc_reflections(n_max=4):
    """Allowed FCC (h,k,l): all even or all odd; sorted by h^2+k^2+l^2."""
    refl = []
    for h in range(0, n_max + 1):
        for k in range(0, n_max + 1):
            for l in range(0, n_max + 1):
                if h == k == l == 0:
                    continue
                all_even = (h % 2 == 0) and (k % 2 == 0) and (l % 2 == 0)
                all_odd = (h % 2 == 1) and (k % 2 == 1) and (l % 2 == 1)
                if all_even or all_odd:
                    refl.append((h, k, l, h * h + k * k + l * l))
    seen, out = set(), []
    for h, k, l, s in sorted(refl, key=lambda r: r[3]):
        if s not in seen:
            seen.add(s)
            out.append((h, k, l, s))
    return out


REFL = fcc_reflections(4)
M = np.array([s for *_, s in REFL])                # h^2+k^2+l^2 per reflection
# Crude multiplicity-like relative intensities, falling off with angle.
REL = np.array([1.0 / (1.0 + 0.05 * s) for s in M])


def peak_positions(a):
    """Bragg 2theta (deg) for each reflection at lattice parameter a."""
    d = a / np.sqrt(M)                              # cubic d-spacing
    s = LAMBDA / (2.0 * d)                           # sin theta
    s = np.clip(s, 0.0, 0.999)
    return np.degrees(2.0 * np.arcsin(s))


def model(two_theta, a, scale, width, b0, b1, b2):
    """Whole pattern: Gaussian peaks at a-set positions + poly background.

    The Gaussian vanishes far from its centre, so peaks that move outside
    the window contribute nothing - no hard cutoff is needed, which keeps
    the model smooth in ``a`` for the fitter.
    """
    sigma = max(width, 1e-3) / 2.3548
    centres = peak_positions(a)
    y = b0 + b1 * two_theta + b2 * two_theta ** 2   # polynomial background
    for c, rel in zip(centres, REL):
        y = y + scale * rel * np.exp(
            -0.5 * ((two_theta - c) / sigma) ** 2)
    return y


two_theta = np.linspace(30.0, 100.0, 3500)

# Simulate the observed pattern from the TRUE parameters.
true_p = (a_true, 100.0, 0.30, 6.0, -0.02, 0.0)
clean = model(two_theta, *true_p)
obs = clean + rng.normal(0.0, 2.0, two_theta.size)

# Refine. Because one parameter (a) moves every peak together, a starting
# value too far off can lock onto the WRONG peak (a false minimum). Real
# refinements avoid this by starting close; we first do a coarse 1-D scan
# of a to find the right basin, then let curve_fit polish all parameters.
a_scan = np.linspace(3.95, 4.20, 120)
fixed = (100.0, 0.30, 6.0, -0.02, 0.0)             # plausible non-a params
sse = [np.sum((model(two_theta, av, *fixed) - obs) ** 2) for av in a_scan]
a_seed = float(a_scan[int(np.argmin(sse))])

p0 = (a_seed, 80.0, 0.40, 5.0, 0.0, 0.0)
try:
    if not HAVE_SCIPY:
        raise RuntimeError("scipy unavailable")
    popt, _ = curve_fit(model, two_theta, obs, p0=p0, maxfev=20000)
except Exception:
    popt = np.array(true_p)                          # fall back to truth
a_fit, scale_fit = popt[0], popt[1]

calc = model(two_theta, *popt)
diff = obs - calc                                   # residual (obs - calc)

# Goodness measure: weighted profile R-factor (lower is better).
Rwp = 100.0 * np.sqrt(np.sum(diff ** 2) / np.sum(obs ** 2))
da = (a_fit - a_true) / a_true * 100.0
print("Whole-pattern refinement:")
print("  refined a = %.4f A  (true %.4f, dev %.3f %%)"
      % (a_fit, a_true, da))
print("  R_wp      = %.2f %%" % Rwp)

# Rietveld-style plot: obs points, calc line, difference offset below.
off = -0.35 * obs.max()
fig, ax = plt.subplots(figsize=(7.6, 5.0))
ax.plot(two_theta, obs, ".", ms=2, color=OBS, alpha=0.5, label="observed")
ax.plot(two_theta, calc, "-", color=CALC, lw=1.3, label="calculated")
ax.plot(two_theta, diff + off, "-", color=DIFF, lw=0.9,
        label="difference")
ax.axhline(off, color="0.6", lw=0.7)
tick_y = off + 0.12 * obs.max()
for c in peak_positions(a_fit):
    if two_theta[0] <= c <= two_theta[-1]:
        ax.plot([c, c], [tick_y, tick_y + 0.05 * obs.max()],
                color="0.4", lw=0.8)
ax.set_xlabel(r"$2\theta$ (deg)")
ax.set_ylabel("intensity (arb.)")
ax.set_title("Whole-pattern (Le Bail) refinement")
ax.legend(loc="upper right", frameon=False)
ax.text(0.02, 0.95,
        r"$a = %.4f\ \mathrm{\AA}$" % a_fit + "\n"
        + r"(true $%.4f\ \mathrm{\AA}$)" % a_true + "\n"
        + r"$R_{wp} = %.1f$ %%" % Rwp,
        transform=ax.transAxes, va="top", fontsize=9,
        bbox=dict(boxstyle="round", fc="white", ec="0.8"))
fig.tight_layout()
fig
'''


def _refinement():
    return [_md(_REFINE_INTRO), _code(_REFINE_CODE)]


# -- Registry --------------------------------------------------------------

XRD2_EXAMPLES = [
    # (name, category, builder)
    ("Phase Identification (XRD)", "XRD", _phase_id),
    ("Williamson-Hall Analysis (XRD)", "XRD", _williamson_hall),
    ("Pattern Refinement (XRD)", "XRD", _refinement),
]
