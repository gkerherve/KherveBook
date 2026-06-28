"""Powder-XRD examples (advanced techniques), part three.

A self-contained companion to ``examples.py`` (Examples menu, "XRD"
category) with six more powder X-ray-diffraction worked examples beyond
the first six. Each is a textbook analysis from a synchrotron or
laboratory diffraction lab:

* **Debye-Scherrer rings** — a 2-D area-detector image of concentric
  diffraction rings, azimuthally integrated to the 1-D *I*(2θ) pattern
  (the job pyFAI does on real data).
* **Residual stress** — the sin²ψ method: peak position shifts with
  sample tilt; the slope of *d* (or 2θ) versus sin²ψ gives the stress.
* **Texture pole figure** — a stereographic pole figure of diffracted
  intensity versus sample orientation, revealing preferred orientation.
* **Thermal expansion** — the lattice parameter from a peak position at
  several temperatures; the slope of *a*(*T*) is the expansion
  coefficient α.
* **Pair distribution function** — total-scattering *S*(*Q*) Fourier
  transformed to the PDF *G*(*r*), peaks at nearest-neighbour distances.
* **Quantitative phase (RIR)** — weight fractions of a two-phase mixture
  from strongest-peak intensity ratios via reference intensity ratios.

Every code cell synthesises faithful data with NumPy so the example
always runs offline (Cu Kα, λ = 1.5406 Å; Bragg λ = 2 *d* sinθ; cubic
1/*d*² = (*h*²+*k*²+*l*²)/*a*²), and any scipy fit is guarded so the
cell never errors.

This module defines its own ``_md``/``_code`` helpers and exports
``XRD3_EXAMPLES`` so it merges into ``examples.py`` without a circular
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


# -- 1. Debye-Scherrer rings ----------------------------------------------

_RINGS_INTRO = """\
# Debye-Scherrer rings & azimuthal integration

On a powder sample the randomly oriented crystallites send each Bragg
reflection out as a **cone** of half-angle 2θ about the incident beam.
A flat **area detector** records each cone as a concentric **ring** — the
Debye-Scherrer pattern. The ring radius grows with 2θ:

$$r = D\\,\\tan 2\\theta$$

for a sample-to-detector distance *D*. Reducing this 2-D image to the
familiar 1-D powder pattern *I*(2θ) means **azimuthally integrating** —
averaging intensity around each ring (over the angle φ).

On real synchrotron data this is the job of
[**pyFAI**](https://pyfai.readthedocs.io), the fast azimuthal-integration
library:

```python
import pyFAI
ai = pyFAI.load("calibration.poni")   # detector geometry + wavelength
two_theta, I = ai.integrate1d(image, 1000, unit="2th_deg")
```

The cell below synthesises a ring image with NumPy (Cu Kα, λ = 1.5406 Å)
and integrates it the same way — binning every pixel by its 2θ and
averaging — to recover the powder pattern.
"""


_RINGS = r'''
# Synthetic 2-D area-detector image of Debye-Scherrer rings, then a
# from-scratch azimuthal integration to the 1-D powder pattern I(2theta) -
# exactly what pyFAI.integrate1d does on a real detector frame.
import numpy as np
import matplotlib.pyplot as plt

rng = np.random.default_rng(0)

lam = 1.5406          # Cu K-alpha wavelength (Angstrom)
a = 5.431             # cubic lattice parameter (Angstrom), Si-like
D = 120.0             # sample-to-detector distance (mm)

# Allowed cubic reflections (diamond: h,k,l all even or all odd, etc.).
hkl = [(1, 1, 1), (2, 2, 0), (3, 1, 1), (4, 0, 0), (3, 3, 1), (4, 2, 2)]
two_theta_peaks = []
for h, k, l in hkl:
    d = a / np.sqrt(h * h + k * k + l * l)        # cubic d-spacing
    s = lam / (2.0 * d)                            # sin(theta)
    if s < 1.0:
        two_theta_peaks.append(2.0 * np.degrees(np.arcsin(s)))
two_theta_peaks = np.array(two_theta_peaks)
r_peaks = D * np.tan(np.radians(two_theta_peaks))  # ring radii (mm)

# Build the detector image: pixel grid centred on the beam.
npx = 400
extent = 70.0                                       # +/- mm from centre
xs = np.linspace(-extent, extent, npx)
XX, YY = np.meshgrid(xs, xs)
R = np.sqrt(XX ** 2 + YY ** 2)                      # radius of every pixel
image = np.zeros_like(R)
for r0 in r_peaks:
    image += np.exp(-((R - r0) ** 2) / (2.0 * 0.8 ** 2))  # Gaussian ring
image += 0.05 * rng.random(image.shape)            # detector noise

# Azimuthal integration: bin every pixel by its 2theta and average.
two_theta_px = np.degrees(np.arctan2(R, D))
edges = np.linspace(0, two_theta_px.max(), 400)
which = np.digitize(two_theta_px.ravel(), edges)
flat = image.ravel()
prof = np.array([flat[which == i].mean() if np.any(which == i) else 0.0
                 for i in range(1, edges.size)])
centres = 0.5 * (edges[:-1] + edges[1:])

fig, (a1, a2) = plt.subplots(1, 2, figsize=(8.2, 3.8))
a1.imshow(image, cmap="inferno", origin="lower",
          extent=[-extent, extent, -extent, extent])
a1.set_xlabel("detector x (mm)")
a1.set_ylabel("detector y (mm)")
a1.set_title("Debye-Scherrer rings")

a2.plot(centres, prof, color="#3776ab", lw=1.4)
for tt in two_theta_peaks:
    a2.axvline(tt, color="#e07b39", ls="--", lw=0.8, alpha=0.7)
a2.set_xlabel(r"$2\theta$ (deg)")
a2.set_ylabel("intensity (arb.)")
a2.set_title("azimuthally integrated pattern")
a2.set_xlim(0, two_theta_peaks.max() + 8)
fig.tight_layout()
fig
'''


def _rings():
    return [_md(_RINGS_INTRO), _code(_RINGS)]


# -- 2. Residual stress (sin^2 psi) ---------------------------------------

_STRESS_INTRO = """\
# Residual stress — the sin²ψ method

A diffraction peak is a built-in **strain gauge**: residual stress in a
material changes the lattice spacing, and that change depends on how the
sample is **tilted** by an angle ψ relative to the diffraction vector. In
the standard **sin²ψ method** the *d*-spacing (or 2θ) measured for one
reflection varies linearly with sin²ψ:

$$d(\\psi) = d_0\\left[1 + \\frac{1+\\nu}{E}\\,\\sigma\\,\\sin^2\\psi\\right]$$

with Young's modulus *E* and Poisson ratio ν the elastic constants. Fit a
straight line to *d* (or 2θ) versus sin²ψ and the **slope** gives the
residual **stress** σ — a tensile (positive) stress opens the spacing as
the sample tilts, a compressive one closes it.

The cell below synthesises *d*(ψ) for a known stress, converts to 2θ via
Bragg's law (Cu Kα), fits the line, and reads the stress back.
"""


_STRESS = r'''
# Residual-stress sin^2(psi) method: synthesise d(psi) for a known stress,
# convert to 2theta via Bragg, fit 2theta vs sin^2(psi) linearly, and
# recover the stress (MPa). polyfit is guarded so the cell never errors.
import numpy as np
import matplotlib.pyplot as plt

rng = np.random.default_rng(0)

lam = 1.5406          # Cu K-alpha (Angstrom)
E = 210.0e3           # Young's modulus (MPa), steel-like
nu = 0.30             # Poisson ratio
d0 = 1.1702           # strain-free d-spacing (Angstrom), Fe (211)-like
sigma_true = -250.0   # true residual stress (MPa), compressive

psi = np.radians(np.array([0, 15, 25, 35, 45, 55]))   # tilt angles
s2 = np.sin(psi) ** 2

# d-spacing vs tilt, then Bragg's law lambda = 2 d sin(theta).
d = d0 * (1.0 + ((1.0 + nu) / E) * sigma_true * s2)
two_theta = 2.0 * np.degrees(np.arcsin(lam / (2.0 * d)))
two_theta += rng.normal(0.0, 0.005, two_theta.size)    # measurement noise

# Linear fit of 2theta vs sin^2(psi); convert the slope back to stress.
try:
    slope, intercept = np.polyfit(s2, two_theta, 1)
except Exception:
    slope, intercept = 0.0, float(two_theta.mean())

# d/d(s2) of Bragg gives the strain slope; chain to stress via the
# elastic prefactor (1+nu)/E.  d(2theta)/d(s2) -> d-strain -> sigma.
theta0 = np.radians(intercept / 2.0)
# strain slope  d(d)/d(s2) / d0  from the 2theta slope (rad):
dstrain_ds2 = -0.5 * np.radians(slope) / np.tan(theta0)
sigma_fit = dstrain_ds2 * E / (1.0 + nu)

xx = np.linspace(0, s2.max() * 1.05, 100)
fig, ax = plt.subplots(figsize=(5.8, 4.2))
ax.plot(s2, two_theta, "o", color="#3776ab", ms=7, label="measured")
ax.plot(xx, slope * xx + intercept, "-", color="#e07b39", lw=2,
        label="linear fit")
ax.set_xlabel(r"$\sin^2\psi$")
ax.set_ylabel(r"$2\theta$ (deg)")
ax.set_title(r"Residual stress by the $\sin^2\psi$ method")
ax.legend(loc="best", frameon=False)
ax.text(0.04, 0.18,
        r"$\sigma = %.0f$ MPa" % sigma_fit + "\n"
        + r"(true $%.0f$ MPa)" % sigma_true,
        transform=ax.transAxes, va="bottom", fontsize=10,
        bbox=dict(boxstyle="round", fc="white", ec="0.8"))
fig.tight_layout()
fig
'''


def _stress():
    return [_md(_STRESS_INTRO), _code(_STRESS)]


# -- 3. Texture pole figure -----------------------------------------------

_POLE_INTRO = """\
# Texture pole figure

In a textured polycrystal the grains are **not** randomly oriented — some
crystal directions line up preferentially (think rolled metal sheet). A
**pole figure** maps this: for a chosen reflection it plots the diffracted
intensity as a function of sample orientation, projected
**stereographically** onto a disc. The radial coordinate is the tilt χ
(centre = surface normal, rim = in-plane) and the angle is the azimuth φ.

A **random** powder gives a flat, featureless disc. **Preferred
orientation** shows up as bright **maxima** — poles — whose positions tell
you which crystallographic directions cluster along which sample
directions.

The cell below builds a pole figure with two intensity maxima (a typical
fibre-plus-rolling texture) and draws it as a polar contour map.
"""


_POLE = r'''
# Texture pole figure: diffracted intensity vs sample orientation drawn as
# a stereographic (polar) contour map.  Two intensity maxima stand for
# preferred orientation against a weak random background.
import numpy as np
import matplotlib.pyplot as plt

rng = np.random.default_rng(0)

# Polar sampling grid: phi = azimuth, chi = tilt from the surface normal.
phi = np.radians(np.linspace(0, 360, 180))
chi = np.radians(np.linspace(0, 90, 90))
PHI, CHI = np.meshgrid(phi, chi)

# Stereographic radius for the projection (centre = normal, rim = in-plane)
r_proj = np.tan(CHI / 2.0)


def pole(phi0, chi0, width, height):
    """A Gaussian texture pole at azimuth phi0, tilt chi0 (degrees)."""
    p0, c0 = np.radians(phi0), np.radians(chi0)
    dphi = np.angle(np.exp(1j * (PHI - p0)))      # wrapped azimuth diff
    return height * np.exp(-(dphi ** 2 + (CHI - c0) ** 2) / (2.0 * width ** 2))


# Two preferred-orientation maxima + a faint random background.
intensity = (1.0
             + pole(40, 30, 0.28, 6.0)
             + pole(220, 55, 0.32, 4.0)
             + 0.05 * rng.random(PHI.shape))

fig = plt.figure(figsize=(5.4, 4.6))
ax = fig.add_subplot(111, projection="polar")
pm = ax.contourf(PHI, r_proj, intensity, levels=24, cmap="inferno")
ax.set_yticklabels([])                             # radius = stereographic
ax.set_title(r"(111) pole figure - preferred orientation", pad=16)
fig.colorbar(pm, ax=ax, label="intensity (arb.)", pad=0.10, shrink=0.8)
fig.tight_layout()
fig
'''


def _pole():
    return [_md(_POLE_INTRO), _code(_POLE)]


# -- 4. Thermal expansion -------------------------------------------------

_THERMAL_INTRO = """\
# Thermal expansion from peak shift

Heat a crystal and it expands: the lattice parameter *a* grows, every
*d*-spacing grows with it, and by Bragg's law each diffraction peak
**shifts to lower 2θ**. Measuring one peak across a temperature series
turns the diffractometer into a dilatometer. The lattice parameter is
very nearly linear in temperature, so

$$a(T) = a_0\\,[1 + \\alpha\\,(T - T_0)]$$

and the **slope** of *a* versus *T* gives the **linear thermal-expansion
coefficient** α (in units of 10⁻⁶ K⁻¹).

The cell below synthesises a single cubic peak (Cu Kα) measured at several
temperatures, extracts *a* from each peak position, fits *a*(*T*), and
reports α.
"""


_THERMAL = r'''
# Thermal expansion: a single cubic peak measured vs temperature shifts to
# lower 2theta as the lattice grows.  Recover a(T) from each peak via Bragg
# and fit the slope for the expansion coefficient alpha.  polyfit guarded.
import numpy as np
import matplotlib.pyplot as plt

rng = np.random.default_rng(0)

lam = 1.5406          # Cu K-alpha (Angstrom)
hkl = (2, 2, 0)       # the monitored cubic reflection
h, k, l = hkl
a0 = 4.0500           # lattice parameter at T0 (Angstrom), Al-like
T0 = 300.0            # reference temperature (K)
alpha_true = 23.1e-6  # true linear expansion coefficient (1/K), Al

T = np.array([300, 400, 500, 600, 700, 800], dtype=float)   # temps (K)
a_T = a0 * (1.0 + alpha_true * (T - T0))                     # true a(T)

# Bragg's law: each a(T) -> d -> 2theta for the (220) peak.
d_T = a_T / np.sqrt(h * h + k * k + l * l)
two_theta = 2.0 * np.degrees(np.arcsin(lam / (2.0 * d_T)))
two_theta += rng.normal(0.0, 0.004, two_theta.size)         # noise

# Invert the measured 2theta back to a, then fit a vs T.
d_meas = lam / (2.0 * np.sin(np.radians(two_theta / 2.0)))
a_meas = d_meas * np.sqrt(h * h + k * k + l * l)
try:
    slope, intercept = np.polyfit(T, a_meas, 1)
except Exception:
    slope, intercept = 0.0, float(a_meas.mean())
alpha_fit = slope / intercept            # (da/dT)/a ~ alpha

fig, (a1, a2) = plt.subplots(1, 2, figsize=(8.2, 3.8))
a1.plot(T, two_theta, "o-", color="#3776ab", ms=6)
a1.set_xlabel(r"temperature $T$ (K)")
a1.set_ylabel(r"$2\theta$ (deg)")
a1.set_title(r"(220) peak shift, $2\theta$ vs $T$")

tt = np.linspace(T.min(), T.max(), 100)
a2.plot(T, a_meas, "o", color="#3776ab", ms=7, label="from peak")
a2.plot(tt, slope * tt + intercept, "-", color="#e07b39", lw=2,
        label="linear fit")
a2.set_xlabel(r"temperature $T$ (K)")
a2.set_ylabel(r"lattice parameter $a$ ($\mathrm{\AA}$)")
a2.set_title("thermal expansion")
a2.legend(loc="best", frameon=False)
a2.text(0.05, 0.80,
        r"$\alpha = %.1f \times 10^{-6}\,\mathrm{K^{-1}}$" % (alpha_fit * 1e6),
        transform=a2.transAxes, fontsize=10,
        bbox=dict(boxstyle="round", fc="white", ec="0.8"))
fig.tight_layout()
fig
'''


def _thermal():
    return [_md(_THERMAL_INTRO), _code(_THERMAL)]


# -- 5. Pair distribution function ----------------------------------------

_PDF_INTRO = """\
# Pair distribution function (PDF)

Beyond the Bragg peaks, **total scattering** captures the diffuse signal
too, and its Fourier transform reveals the **local** structure directly in
real space. The reduced total-scattering structure function *S*(*Q*) − 1
(with *Q* = 4π sinθ/λ) transforms to the **pair distribution function**
*G*(*r*) by a sine transform:

$$G(r) = \\frac{2}{\\pi}\\int_0^{Q_{\\max}} Q\\,[S(Q) - 1]\\,\\sin(Qr)\\,dQ$$

*G*(*r*) is a histogram of **interatomic distances**: each peak sits at a
nearest-neighbour, next-nearest-neighbour, … separation, and its area
counts the neighbours in that shell. PDF analysis (e.g. **PDFgui** /
**diffpy**) works for crystalline *and* amorphous or nanostructured
materials, where Bragg analysis alone falls short.

The cell below builds an oscillatory *S*(*Q*) and sine-transforms it to a
*G*(*r*) with peaks at a few coordination-shell distances.
"""


_PDF = r'''
# Pair distribution function: build a total-scattering S(Q) whose
# oscillations encode a set of interatomic distances, then sine-Fourier-
# transform to the PDF G(r). Peaks in G(r) sit at the coordination shells.
import numpy as np
import matplotlib.pyplot as plt

rng = np.random.default_rng(0)

# Coordination shells (Angstrom) and their relative weights.
shells = np.array([2.50, 3.55, 4.35, 5.00])       # nearest-neighbour radii
weights = np.array([1.00, 0.60, 0.45, 0.30])

Q = np.linspace(0.5, 20.0, 1600)                  # momentum transfer (1/Ang)

# F(Q) = Q[S(Q)-1] is a damped sum of sine waves, one per shell distance.
FQ = np.zeros_like(Q)
for r0, w in zip(shells, weights):
    FQ += w * np.sin(Q * r0) * np.exp(-(Q * 0.045) ** 2)
SQ = 1.0 + FQ / Q                                  # the structure function
SQ += rng.normal(0.0, 0.01, Q.size)               # counting noise

# Sine Fourier transform F(Q) -> G(r) = (2/pi) integral Q[S-1] sin(Qr) dQ.
r = np.linspace(0.5, 8.0, 800)
dQ = Q[1] - Q[0]
Gr = (2.0 / np.pi) * (np.sin(np.outer(r, Q)) * FQ).sum(axis=1) * dQ

fig, (a1, a2) = plt.subplots(1, 2, figsize=(8.4, 3.8))
a1.plot(Q, SQ, color="#3776ab", lw=0.9)
a1.axhline(1.0, color="0.6", ls=":", lw=0.8)
a1.set_xlabel(r"$Q$ (1/$\mathrm{\AA}$)")
a1.set_ylabel(r"$S(Q)$")
a1.set_title("total-scattering structure function")

a2.plot(r, Gr, color="#50bea0", lw=1.6)
for r0 in shells:
    a2.axvline(r0, color="#e07b39", ls="--", lw=0.8, alpha=0.7)
a2.set_xlabel(r"$r$ ($\mathrm{\AA}$)")
a2.set_ylabel(r"$G(r)$")
a2.set_title("pair distribution function")
fig.tight_layout()
fig
'''


def _pdf():
    return [_md(_PDF_INTRO), _code(_PDF)]


# -- 6. Quantitative phase analysis (RIR) ---------------------------------

_RIR_INTRO = """\
# Quantitative phase analysis — the RIR method

A diffraction pattern from a **mixture** is the sum of each phase's
pattern, scaled by how much of that phase is present. The quick,
standardless route to **weight fractions** is the **reference intensity
ratio (RIR)**, also written *I/I*꜀ — the ratio of a phase's strongest peak
to that of corundum (α-Al₂O₃) in a 50:50 mixture, tabulated in the powder
diffraction file. For two phases the weight fraction of phase 1 is

$$X_1 = \\frac{I_1 / \\mathrm{RIR}_1}{I_1/\\mathrm{RIR}_1 + I_2/\\mathrm{RIR}_2}$$

using the measured strongest-peak intensities *I*₁, *I*₂. A high RIR means
a strong scatterer, so its intensity over-counts and must be divided down.

The cell below builds a two-phase pattern (Cu Kα) from a known mixture,
measures each phase's strongest peak, applies the RIRs, and reports the
recovered weight percentages.
"""


_RIR = r'''
# Quantitative phase analysis by reference intensity ratios (RIR / I/Icor):
# build a two-phase powder pattern, measure each phase's strongest peak,
# and convert the intensity ratio to weight fractions.
import numpy as np
import matplotlib.pyplot as plt

rng = np.random.default_rng(0)

lam = 1.5406          # Cu K-alpha (Angstrom)


def cubic_peaks(a, hkls):
    """2theta positions (deg) for cubic reflections at lattice param a."""
    out = []
    for h, k, l in hkls:
        d = a / np.sqrt(h * h + k * k + l * l)
        s = lam / (2.0 * d)
        if s < 1.0:
            out.append(2.0 * np.degrees(np.arcsin(s)))
    return np.array(out)


# Two cubic phases with their reference intensity ratios (I/Icorundum).
hkl_a = [(1, 1, 1), (2, 0, 0), (2, 2, 0)]          # phase A reflections
hkl_b = [(1, 1, 0), (2, 0, 0), (2, 1, 1)]          # phase B reflections
tt_a = cubic_peaks(3.615, hkl_a)                   # phase A (Cu-like, fcc)
tt_b = cubic_peaks(2.866, hkl_b)                   # phase B (Fe-like, bcc)
rir_a, rir_b = 4.0, 2.5                            # tabulated RIRs

# Known mixture (ground truth) -> measured strongest-peak intensities.
wt_a_true, wt_b_true = 0.65, 0.35
scale_a = wt_a_true * rir_a
scale_b = wt_b_true * rir_b
rel_a = np.array([1.00, 0.46, 0.20])               # relative peak heights
rel_b = np.array([1.00, 0.30, 0.55])

two_theta = np.linspace(20, 90, 2000)
pattern = np.zeros_like(two_theta)


def add_peaks(centres, heights, scale):
    for c, hgt in zip(centres, heights):
        pattern[:] += scale * hgt * np.exp(
            -((two_theta - c) ** 2) / (2.0 * 0.18 ** 2))


add_peaks(tt_a, rel_a, scale_a)
add_peaks(tt_b, rel_b, scale_b)
pattern += 0.02 * rng.random(pattern.size)         # background noise

# Measure each phase's strongest peak height from the pattern.
def peak_height(centre):
    i = int(np.argmin(np.abs(two_theta - centre)))
    lo, hi = max(0, i - 12), min(two_theta.size, i + 12)
    return pattern[lo:hi].max()


I_a = peak_height(tt_a[0])
I_b = peak_height(tt_b[0])

# RIR weight fractions: X1 = (I1/RIR1) / sum(Ii/RIRi).
qa, qb = I_a / rir_a, I_b / rir_b
wt_a = qa / (qa + qb)
wt_b = qb / (qa + qb)

fig, ax = plt.subplots(figsize=(7.8, 4.2))
ax.plot(two_theta, pattern, color="#3776ab", lw=1.0)
for c in tt_a:
    ax.axvline(c, color="#e07b39", ls="--", lw=0.8, alpha=0.6)
for c in tt_b:
    ax.axvline(c, color="#50bea0", ls="--", lw=0.8, alpha=0.6)
ax.plot([], [], color="#e07b39", ls="--", label="phase A")
ax.plot([], [], color="#50bea0", ls="--", label="phase B")
ax.set_xlabel(r"$2\theta$ (deg)")
ax.set_ylabel("intensity (arb.)")
ax.set_title("two-phase mixture - quantitative phase by RIR")
ax.legend(loc="upper right", frameon=False)
ax.text(0.03, 0.95,
        r"phase A: %.0f wt%%  (true %.0f)" % (100 * wt_a, 100 * wt_a_true)
        + "\n"
        + r"phase B: %.0f wt%%  (true %.0f)" % (100 * wt_b, 100 * wt_b_true),
        transform=ax.transAxes, va="top", fontsize=9,
        bbox=dict(boxstyle="round", fc="white", ec="0.8"))
fig.tight_layout()
fig
'''


def _rir():
    return [_md(_RIR_INTRO), _code(_RIR)]


# -- Registry --------------------------------------------------------------

XRD3_EXAMPLES = [
    # (name, category, builder)
    ("Debye-Scherrer Rings (XRD)", "XRD", _rings),
    ("Residual Stress (XRD)", "XRD", _stress),
    ("Texture Pole Figure (XRD)", "XRD", _pole),
    ("Thermal Expansion (XRD)", "XRD", _thermal),
    ("Pair Distribution Function (XRD)", "XRD", _pdf),
    ("Quantitative Phase (RIR) (XRD)", "XRD", _rir),
]
