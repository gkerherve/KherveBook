"""Powder X-ray diffraction (XRD) examples.

A self-contained companion to ``examples.py`` (Examples menu, "XRD"
category). Three examples are exported here, all built with pure
NumPy/SciPy/matplotlib so they run offline:

* **Powder XRD Pattern** — simulate a powder diffractogram for an FCC
  metal from Bragg's law, the cubic d-spacing relation and the FCC
  selection rules, with Lorentz-polarisation weighting and pseudo-Voigt
  peaks; the strongest reflections are labelled by their (hkl).
* **Peak Indexing & Lattice** — from a set of observed peak positions,
  recover the d-spacings, index the reflections from the sin^2(theta)
  ratios, identify the lattice type (FCC vs BCC) and refine the cubic
  lattice parameter a by least squares.
* **Scherrer Crystallite Size** — show how a reflection broadens as the
  crystallite size shrinks (Scherrer equation), then recover the size
  from the measured peak width.

Materials-science toolkits such as **pymatgen** can compute the same
patterns from a crystal structure
(``pymatgen.analysis.diffraction.xrd.XRDCalculator``); pymatgen is only
referenced in the markdown, never imported. This module defines its own
``_md``/``_code`` helpers and exports ``XRD_EXAMPLES`` so it merges into
``examples.py`` without a circular import.

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


# -- 1. Powder XRD pattern -------------------------------------------------

_PATTERN_INTRO = """\
# Powder XRD pattern of an FCC metal

A **powder X-ray diffractogram** records scattered intensity versus the
scattering angle 2θ. Sharp **Bragg peaks** appear where

> λ = 2 *d* sin θ  &nbsp;&nbsp;(**Bragg's law**)

with the Cu Kα wavelength λ = 1.5406 Å. For a **cubic** crystal the
plane spacing of the (*hkl*) reflection is

> 1 / *d*² = (*h*² + *k*² + *l*²) / *a*²

so each reflection sits at 2θ = 2·arcsin( λ·√(*h*²+*k*²+*l*²) / (2 *a*) ).
Not every (*hkl*) is allowed — the **structure factor** of a
**face-centred cubic** lattice vanishes unless *h*, *k*, *l* are **all
even or all odd**. The relative peak height scales as

> *I* ∝ *m*<sub>hkl</sub> · |*F*|² · LP(θ)

with the multiplicity *m*<sub>hkl</sub> and the **Lorentz-polarisation**
factor LP = (1 + cos²2θ) / (sin²θ · cosθ).

The cell below builds the pattern for **copper** (FCC, *a* = 3.615 Å)
from scratch and labels the strongest peaks by their (*hkl*).

With [`pymatgen`](https://pymatgen.org) the same pattern comes straight
from a crystal structure:

```python
from pymatgen.analysis.diffraction.xrd import XRDCalculator
pattern = XRDCalculator(wavelength="CuKa").get_pattern(structure)
```
"""


_PATTERN_CODE = r'''
# Simulate a powder XRD pattern for an FCC metal (copper) from first
# principles: Bragg's law + cubic d-spacing + FCC selection rules, with
# Lorentz-polarisation weighting and pseudo-Voigt peak shapes.
# (pymatgen's XRDCalculator does this from a crystal structure.)
import numpy as np
import matplotlib.pyplot as plt

rng = np.random.default_rng(0)

wavelength = 1.5406          # Cu K-alpha (Angstrom)
a = 3.615                    # copper lattice parameter (Angstrom)
two_theta_min, two_theta_max = 20.0, 100.0

# Approximate reflection multiplicities for a cubic lattice.
MULT = {(1, 1, 1): 8, (2, 0, 0): 6, (2, 2, 0): 12, (3, 1, 1): 24,
        (2, 2, 2): 8, (4, 0, 0): 6, (3, 3, 1): 24, (4, 2, 0): 24,
        (4, 2, 2): 24, (5, 1, 1): 24, (3, 3, 3): 8, (4, 4, 0): 12}


def fcc_allowed(h, k, l):
    """FCC selection rule: h, k, l all even OR all odd."""
    parities = {h % 2, k % 2, l % 2}
    return len(parities) == 1


def multiplicity(h, k, l):
    key = tuple(sorted((h, k, l), reverse=True))
    return MULT.get(key, 8)


# Enumerate allowed reflections, collapsing those with the same s = h^2+k^2+l^2
# (they coincide in 2theta for a cubic lattice).
hmax = 4
seen = {}
for h in range(0, hmax + 1):
    for k in range(0, hmax + 1):
        for l in range(0, hmax + 1):
            s = h * h + k * k + l * l
            if s == 0 or not fcc_allowed(h, k, l):
                continue
            arg = wavelength * np.sqrt(s) / (2 * a)
            if arg >= 1.0:
                continue
            tt = 2 * np.degrees(np.arcsin(arg))
            if not (two_theta_min <= tt <= two_theta_max):
                continue
            if s not in seen:
                seen[s] = (tt, (h, k, l))

reflections = []
for s, (tt, hkl) in sorted(seen.items()):
    theta = np.radians(tt / 2)
    lp = (1 + np.cos(np.radians(tt)) ** 2) / (np.sin(theta) ** 2 * np.cos(theta))
    inten = multiplicity(*hkl) * lp        # constant |F|^2 absorbed into scale
    reflections.append((tt, inten, hkl))

scale = max(r[1] for r in reflections)
reflections = [(tt, 100.0 * inten / scale, hkl) for tt, inten, hkl in reflections]


def pseudo_voigt(x, x0, fwhm, eta=0.5):
    """Normalised pseudo-Voigt (eta*Lorentzian + (1-eta)*Gaussian)."""
    sigma = fwhm / (2 * np.sqrt(2 * np.log(2)))
    gauss = np.exp(-(x - x0) ** 2 / (2 * sigma ** 2))
    gamma = fwhm / 2
    lorentz = gamma ** 2 / ((x - x0) ** 2 + gamma ** 2)
    return eta * lorentz + (1 - eta) * gauss


x = np.linspace(two_theta_min, two_theta_max, 4000)
fwhm = 0.3                                   # peak width (deg)
y = 2.0 + 0.004 * (x - two_theta_min)        # gentle sloping background
for tt, inten, hkl in reflections:
    y = y + inten * pseudo_voigt(x, tt, fwhm)
y = y + rng.normal(0, 0.6, x.size)           # counting noise

fig, ax = plt.subplots(figsize=(7.6, 4.2))
ax.plot(x, y, color="#3776ab", lw=1.0)
# Label the strongest reflections by (hkl).
strong = sorted(reflections, key=lambda r: r[1], reverse=True)[:6]
for tt, inten, hkl in strong:
    ax.annotate("(%d%d%d)" % hkl, xy=(tt, inten + 2),
                xytext=(tt, inten + 14), ha="center", fontsize=8,
                color="#e07b39",
                arrowprops=dict(arrowstyle="-", color="#e07b39", lw=0.8))
ax.set_xlabel(r"$2\theta$ (deg)")
ax.set_ylabel("intensity (arb.)")
ax.set_title(r"Powder XRD: Cu (FCC, $a=3.615$ $\AA$), Cu K$\alpha$")
ax.set_xlim(two_theta_min, two_theta_max)
fig.text(0.01, 0.005, r"$\lambda = 1.5406$ $\AA$;  $I \propto m\,|F|^2\,$LP",
         fontsize=7, color="0.45")
fig.tight_layout()
fig
'''


def _xrd_pattern():
    return [_md(_PATTERN_INTRO), _code(_PATTERN_CODE)]


# -- 2. Peak indexing and lattice ------------------------------------------

_INDEX_INTRO = """\
# Indexing a cubic pattern and refining the lattice parameter

Given a list of **observed peak positions** 2θ, the goal is to assign
each peak its (*hkl*) index, decide the lattice type and extract the
**lattice parameter** *a*. The recipe for a cubic phase:

1. **d-spacing** from Bragg's law: *d* = λ / (2 sin θ).
2. Form **sin²θ** for every peak. For a cubic crystal
   sin²θ ∝ (*h*² + *k*² + *l*²), so the ratios
   sin²θ / sin²θ<sub>min</sub> are integers equal to the ratios of
   *s* = *h*² + *k*² + *l*².
3. The **sequence of allowed *s*** fingerprints the lattice:
   FCC gives *s* = 3, 4, 8, 11, 12, 16, … (the all-even/all-odd set),
   BCC gives *s* = 2, 4, 6, 8, 10, … (*h*+*k*+*l* even).
4. With (*hkl*) assigned, **refine** *a* by least squares from
   *a* = λ·√*s* / (2 sin θ).

The cell below generates peaks for a known cubic phase, indexes them
from the sin²θ ratios, identifies the lattice type and reports the
refined *a*. ([`pymatgen`](https://pymatgen.org)'s `XRDCalculator`
indexes patterns directly from a structure.)
"""


_INDEX_CODE = r'''
# Index an observed cubic powder pattern and refine the lattice parameter.
# Steps: d-spacing (Bragg) -> sin^2(theta) -> ratios give s = h^2+k^2+l^2 ->
# the allowed-s sequence identifies FCC vs BCC -> least-squares a.
import numpy as np
import matplotlib.pyplot as plt

wavelength = 1.5406          # Cu K-alpha (Angstrom)

# --- Generate "observed" peaks for a known FCC phase (a = 4.05 A, like Al).
a_true = 4.05
fcc_s = [3, 4, 8, 11, 12, 16, 19, 20]        # allowed s for FCC
obs_2theta = []
for s in fcc_s:
    arg = wavelength * np.sqrt(s) / (2 * a_true)
    if arg < 1.0:
        tt = 2 * np.degrees(np.arcsin(arg))
        if tt <= 120.0:
            obs_2theta.append(tt)
obs_2theta = np.array(obs_2theta)

# --- Index from sin^2(theta) ratios.
theta = np.radians(obs_2theta / 2)
d = wavelength / (2 * np.sin(theta))          # Bragg d-spacings
sin2 = np.sin(theta) ** 2
ratios = sin2 / sin2.min()                    # = s / s_min

# Candidate lattices and their allowed s-sequences.
LATTICE_S = {
    "FCC": [3, 4, 8, 11, 12, 16, 19, 20, 24, 27],
    "BCC": [2, 4, 6, 8, 10, 12, 14, 16, 18, 20],
    "SC":  [1, 2, 3, 4, 5, 6, 8, 9, 10, 11],
}
# s integers from the ratios use s_min as the first allowed value of each
# candidate; the lattice whose predicted ratios best match wins.
best = None
for name, seq in LATTICE_S.items():
    pred = np.array(seq[:len(ratios)], dtype=float)
    pred = pred / pred[0]
    err = np.mean((pred - ratios) ** 2)
    if best is None or err < best[0]:
        best = (err, name, seq)
_, lattice, seq = best
s_vals = np.array(seq[:len(obs_2theta)])

# Recover (hkl) for each s (smallest indices that give h^2+k^2+l^2 = s).
def hkl_for_s(s):
    for h in range(0, 6):
        for k in range(h, 6):
            for l in range(k, 6):
                if h * h + k * k + l * l == s:
                    return (l, k, h)
    return (0, 0, 0)

hkls = [hkl_for_s(s) for s in s_vals]

# --- Least-squares lattice parameter from a = lambda*sqrt(s)/(2 sin theta).
a_each = wavelength * np.sqrt(s_vals) / (2 * np.sin(theta))
a_fit = float(np.mean(a_each))                # equal-weight least squares

print("indexed peaks (FCC phase, a_true = %.3f A):" % a_true)
for tt, dd, s, hkl in zip(obs_2theta, d, s_vals, hkls):
    print("  2theta=%6.2f  d=%.4f A  s=%2d  (%d%d%d)" % (tt, dd, s, *hkl))
print("lattice type: %s   refined a = %.4f A" % (lattice, a_fit))

# --- Plot the pattern with hkl labels and the refined a annotated.
def pseudo_voigt(x, x0, fwhm, eta=0.5):
    sigma = fwhm / (2 * np.sqrt(2 * np.log(2)))
    gauss = np.exp(-(x - x0) ** 2 / (2 * sigma ** 2))
    gamma = fwhm / 2
    lorentz = gamma ** 2 / ((x - x0) ** 2 + gamma ** 2)
    return eta * lorentz + (1 - eta) * gauss

x = np.linspace(obs_2theta.min() - 5, obs_2theta.max() + 5, 4000)
y = np.ones_like(x) * 1.0
for tt in obs_2theta:
    y = y + 100.0 * pseudo_voigt(x, tt, 0.3)

fig, ax = plt.subplots(figsize=(7.6, 4.2))
ax.plot(x, y, color="#3776ab", lw=1.0)
for tt, hkl in zip(obs_2theta, hkls):
    ax.annotate("(%d%d%d)" % hkl, xy=(tt, 100), xytext=(tt, 116),
                ha="center", fontsize=8, color="#e07b39")
ax.set_xlabel(r"$2\theta$ (deg)")
ax.set_ylabel("intensity (arb.)")
ax.set_title("Indexed cubic pattern")
ax.text(0.97, 0.95, "lattice: %s\n$a = %.4f$ $\\AA$" % (lattice, a_fit),
        transform=ax.transAxes, ha="right", va="top", fontsize=10,
        bbox=dict(boxstyle="round", fc="white", ec="#3776ab"))
ax.set_ylim(0, 130)
fig.tight_layout()
fig
'''


def _xrd_indexing():
    return [_md(_INDEX_INTRO), _code(_INDEX_CODE)]


# -- 3. Scherrer crystallite size ------------------------------------------

_SCHERRER_INTRO = """\
# Scherrer crystallite size from peak broadening

Nanoscale crystallites broaden Bragg peaks. The **Scherrer equation**
relates the size *D* to the peak width:

> *D* = *K* λ / (β cos θ)

with the shape factor *K* ≈ 0.9, β the **integral/full-width-at-half-
maximum in radians**, and θ in radians. Smaller crystallites → broader
peaks. Inverting it gives the FWHM expected for a given size,

> β = *K* λ / (*D* cos θ),

which is how the cell below simulates the **same reflection** at three
crystallite sizes (50, 15 and 5 nm). It then takes one broadened peak,
measures its FWHM (a Gaussian fit with SciPy, falling back to a direct
half-maximum estimate) and feeds it back through Scherrer to **recover
the size**.

**Caveat:** measured broadening also contains an **instrumental**
contribution; a real analysis subtracts the instrument width (e.g.
β² = β²<sub>obs</sub> − β²<sub>instr</sub>) before applying Scherrer.
([`pymatgen`](https://pymatgen.org) models the ideal pattern; size
broadening is added on top.)
"""


_SCHERRER_CODE = r'''
# Scherrer broadening: simulate one reflection at three crystallite sizes
# (beta = K*lambda/(D*cos theta)), then recover D from a measured FWHM.
import numpy as np
import matplotlib.pyplot as plt

rng = np.random.default_rng(0)

wavelength = 1.5406          # Cu K-alpha (Angstrom)
K = 0.9                      # Scherrer shape factor
two_theta0 = 43.3           # a Cu-like (111) reflection (deg)
theta0 = np.radians(two_theta0 / 2)


def scherrer_fwhm_deg(D_nm):
    """FWHM (deg) for a crystallite of size D (nm) via Scherrer."""
    lam_nm = wavelength / 10.0               # Angstrom -> nm
    beta_rad = K * lam_nm / (D_nm * np.cos(theta0))
    return np.degrees(beta_rad)


def gaussian(x, amp, x0, fwhm, bg):
    sigma = fwhm / (2 * np.sqrt(2 * np.log(2)))
    return amp * np.exp(-(x - x0) ** 2 / (2 * sigma ** 2)) + bg


x = np.linspace(two_theta0 - 6, two_theta0 + 6, 2000)
sizes = [50, 15, 5]                          # nm
colors = ["#3776ab", "#e07b39", "#4a9a4a"]

fig, (a1, a2) = plt.subplots(1, 2, figsize=(8.4, 3.8))

# --- Left: the same reflection at three crystallite sizes.
for D, c in zip(sizes, colors):
    fwhm = scherrer_fwhm_deg(D)
    y = gaussian(x, 100.0, two_theta0, fwhm, 0.0)
    a1.plot(x, y, color=c, lw=1.4,
            label=r"$D=%d$ nm,  FWHM=%.2f$^\circ$" % (D, fwhm))
a1.set_xlabel(r"$2\theta$ (deg)")
a1.set_ylabel("intensity (arb.)")
a1.set_title("Same reflection, varying size")
a1.legend(fontsize=8)

# --- Right: measure FWHM of one broadened peak and recover D.
D_meas = 8.0                                 # the (unknown) true size, nm
fwhm_true = scherrer_fwhm_deg(D_meas)
y_meas = gaussian(x, 100.0, two_theta0, fwhm_true, 2.0)
y_meas = y_meas + rng.normal(0, 1.2, x.size)

fwhm_fit = fwhm_true
try:
    from scipy.optimize import curve_fit
    p0 = [y_meas.max() - 2.0, two_theta0, fwhm_true, 2.0]
    popt, _ = curve_fit(gaussian, x, y_meas, p0=p0, maxfev=10000)
    fwhm_fit = abs(popt[2])
except Exception:
    # Direct half-maximum width if SciPy is unavailable.
    base = np.median(y_meas)
    half = base + (y_meas.max() - base) / 2
    above = np.where(y_meas >= half)[0]
    if above.size >= 2:
        fwhm_fit = x[above[-1]] - x[above[0]]

# Recover D from the measured FWHM via Scherrer.
beta_rad = np.radians(fwhm_fit)
lam_nm = wavelength / 10.0
D_recovered = K * lam_nm / (beta_rad * np.cos(theta0))

a2.plot(x, y_meas, color="0.55", lw=0.8, label="measured")
a2.plot(x, gaussian(x, y_meas.max() - 2.0, two_theta0, fwhm_fit, 2.0),
        color="#e07b39", lw=1.6, label="fit")
a2.set_xlabel(r"$2\theta$ (deg)")
a2.set_ylabel("intensity (arb.)")
a2.set_title("Recover size from FWHM")
a2.legend(fontsize=8)
a2.text(0.04, 0.95,
        "FWHM = %.2f$^\\circ$\n$D \\approx$ %.1f nm\n(true %.0f nm)"
        % (fwhm_fit, D_recovered, D_meas),
        transform=a2.transAxes, ha="left", va="top", fontsize=9,
        bbox=dict(boxstyle="round", fc="white", ec="#3776ab"))

print("measured FWHM = %.3f deg  ->  D = %.2f nm (true %.0f nm)"
      % (fwhm_fit, D_recovered, D_meas))
fig.text(0.01, 0.005, r"$D = K\lambda/(\beta\cos\theta)$,  $K=0.9$",
         fontsize=7, color="0.45")
fig.tight_layout()
fig
'''


def _xrd_scherrer():
    return [_md(_SCHERRER_INTRO), _code(_SCHERRER_CODE)]


# -- Registry --------------------------------------------------------------

XRD_EXAMPLES = [
    # (name, category, builder)
    ("Powder XRD Pattern (XRD)", "XRD", _xrd_pattern),
    ("Peak Indexing & Lattice (XRD)", "XRD", _xrd_indexing),
    ("Scherrer Crystallite Size (XRD)", "XRD", _xrd_scherrer),
]
