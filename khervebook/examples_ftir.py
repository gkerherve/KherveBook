"""FTIR (Fourier-transform infrared) spectroscopy examples.

A self-contained companion to ``examples.py`` (Examples menu, "FTIR"
category). Fourier-transform infrared spectroscopy measures how much
infrared light a sample absorbs at each **wavenumber** (cm^-1); the
pattern of absorption bands fingerprints the molecule's chemical bonds
and functional groups.

The three examples cover the everyday FTIR workflow:

* reading a spectrum and **assigning functional groups** from the
  characteristic group frequencies,
* **baseline correction** (asymmetric least squares) followed by a
  carbonyl **peak fit**, and
* **Beer-Lambert quantification** — a band-area calibration that turns
  an unknown spectrum into a concentration.

Everything is synthesised with NumPy/SciPy so the cells always run
offline. Each code cell also tries the real
[SpectroChemPy](https://www.spectrochempy.fr/) library and the
[`jcamp`](https://pypi.org/project/jcamp/) JCAMP-DX reader, falling back
to synthetic data when they (or their bundled datasets) are unavailable.

This module defines its own ``_md``/``_code`` helpers and exports
``FTIR_EXAMPLES`` so it merges into ``examples.py`` without a circular
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


# -- 1. Spectrum & functional groups --------------------------------------

_GROUPS_INTRO = """\
# FTIR spectrum & functional groups

**Fourier-transform infrared (FTIR) spectroscopy** measures the infrared
light a sample absorbs as a function of **wavenumber** (cm^-1). Each
chemical bond absorbs at a frequency set by the masses of its atoms and
the bond stiffness, so the spectrum is a fingerprint of the molecule's
**functional groups**. By convention the *x* axis runs from **high to
low** wavenumber (4000 cm^-1 on the left), and the *y* axis is either
**absorbance** (peaks up) or **% transmittance** (dips down).

The diagnostic part is the set of **group frequencies**:

| band (cm^-1) | assignment |
|---|---|
| ~3300 (broad) | O-H stretch (acid / alcohol) |
| ~3350 | N-H stretch |
| 2920 & 2850 | C-H stretch (sp3) |
| ~1715 (strong) | C=O stretch (carbonyl) |
| 1620-1680 | C=C stretch |
| 1600 / 1500 | aromatic ring |
| 1050-1250 | C-O stretch |
| < 1500 | "fingerprint" region |

Real spectra come from instruments or shared archives. Two common
sources are **[SpectroChemPy](https://www.spectrochempy.fr/)**, which
ships IR example datasets:

```python
import spectrochempy as scp
ds = scp.read("irdata/nh4y-activation.spg")   # bundled IR series
ds.plot()
```

and the **JCAMP-DX** exchange format used by the NIST Chemistry WebBook
(`.jdx` files), read with the [`jcamp`](https://pypi.org/project/jcamp/)
package:

```python
from jcamp import jcamp_readfile
d = jcamp_readfile("ethanol.jdx")
x, y = d['x'], d['y']        # wavenumber, absorbance
```

The cell below uses real data when those libraries are installed, and
otherwise synthesises the absorbance spectrum of a **carboxylic acid**
as a sum of bands at the positions above, then annotates each major band
with its functional-group assignment.
"""


_GROUPS_CODE = r'''
# FTIR absorbance spectrum of an organic molecule (a carboxylic acid),
# with every major band annotated by functional group. Uses real data
# from SpectroChemPy or a JCAMP file when available, else synthesises a
# faithful spectrum so the example always runs.
import numpy as np
import matplotlib.pyplot as plt

BLUE, ORANGE = "#3776ab", "#e07b39"
rng = np.random.default_rng(0)


def gaussian(x, c, fwhm):
    sigma = fwhm / 2.3548
    return np.exp(-0.5 * ((x - c) / sigma) ** 2)


def lorentzian(x, c, fwhm):
    hwhm = fwhm / 2.0
    return hwhm ** 2 / ((x - c) ** 2 + hwhm ** 2)


# (centre cm^-1, height, FWHM, shape, assignment) for a carboxylic acid.
# The broad O-H stretch and the sharp C=O are the diagnostic pair.
BANDS = [
    (3000, 0.55, 550, "g", "O-H stretch\n(broad, acid)"),
    (2925, 0.45, 60,  "l", "C-H stretch"),
    (2855, 0.32, 55,  "l", ""),
    (1710, 0.95, 45,  "l", "C=O stretch"),
    (1640, 0.22, 70,  "l", "C=C stretch"),
    (1455, 0.30, 60,  "l", "C-H bend"),
    (1280, 0.50, 90,  "l", "C-O stretch"),
    (1100, 0.28, 80,  "l", ""),
    (930,  0.20, 80,  "l", "O-H bend\n(fingerprint)"),
]


def load_spectrum():
    """Return (wavenumber, absorbance, source)."""
    # Try a real SpectroChemPy IR dataset first.
    try:
        import spectrochempy as scp                           # noqa: F401
        ds = scp.read("irdata/nh4y-activation.spg")
        row = ds[0] if ds.ndim > 1 else ds
        x = np.asarray(row.x.data, dtype=float).ravel()
        y = np.asarray(row.data, dtype=float).ravel()
        if x[0] < x[-1]:                       # ensure high->low order
            x, y = x[::-1], y[::-1]
        return x, y, "SpectroChemPy irdata/nh4y-activation.spg"
    except Exception:
        pass
    # Then try a JCAMP-DX file alongside this notebook.
    try:
        import os
        from jcamp import jcamp_readfile
        for name in ("spectrum.jdx", "ir.jdx", "ethanol.jdx"):
            if os.path.exists(name):
                d = jcamp_readfile(name)
                x = np.asarray(d["x"], dtype=float)
                y = np.asarray(d["y"], dtype=float)
                if x[0] < x[-1]:
                    x, y = x[::-1], y[::-1]
                return x, y, "JCAMP-DX file: " + name
    except Exception:
        pass
    # Fall back to a synthetic carboxylic-acid spectrum.
    x = np.linspace(4000.0, 400.0, 1800)
    y = np.full_like(x, 0.02)
    for c, h, w, shape, _ in BANDS:
        prof = gaussian(x, c, w) if shape == "g" else lorentzian(x, c, w)
        y = y + h * prof
    y = y + rng.normal(0.0, 0.006, x.size)     # detector noise
    return x, y, "synthetic carboxylic-acid spectrum (pip install spectrochempy)"


x, A, source = load_spectrum()

fig, ax = plt.subplots(figsize=(7.6, 4.4))
ax.plot(x, A, color=BLUE, lw=1.2)
ax.set_xlim(4000, 400)                          # IR convention: high->low
ax.set_xlabel(r"wavenumber (cm$^{-1}$)")
ax.set_ylabel("absorbance (arb.)")
ax.set_title("FTIR absorbance spectrum with functional-group assignments")

# Annotate each labelled band with its assignment.
ymax = A.max()
for c, h, w, shape, label in BANDS:
    if not label:
        continue
    j = int(np.argmin(np.abs(x - c)))
    ypk = A[j]
    ax.annotate(label, xy=(c, ypk), xytext=(c, ypk + 0.12 * ymax + 0.05),
                ha="center", va="bottom", fontsize=7.5, color=ORANGE,
                arrowprops=dict(arrowstyle="->", color=ORANGE, lw=0.9))
ax.set_ylim(top=ymax * 1.55)
fig.text(0.01, 0.005, source, fontsize=7, color="0.45")
fig.tight_layout()
fig
'''


def _ftir_groups():
    return [_md(_GROUPS_INTRO), _code(_GROUPS_CODE)]


# -- 2. Baseline correction & peak fit ------------------------------------

_BASELINE_INTRO = """\
# FTIR baseline correction & peak fit

Real FTIR spectra sit on a **sloping, drifting baseline** from light
scattering, sample thickness and instrument drift. That background
distorts peak heights and areas, so it must be removed before any
quantitative analysis. A robust, widely used method is **asymmetric
least squares (ALS)**: fit a smooth curve that is pulled towards the
*bottom* of the data (points above the baseline are weighted far less
than points below), so absorption peaks are ignored and only the
background is followed. The corrected spectrum is the raw data minus
that baseline.

With the baseline gone, the **carbonyl region** (~1650-1800 cm^-1) can
be fitted with a peak model. Here we fit the C=O band with a
**Voigt-like** profile (a pseudo-Voigt: a mix of Gaussian and
Lorentzian) using `scipy.optimize.curve_fit`, and report the fitted
**band centre** and **integrated area** — the area being the quantity
that Beer-Lambert relates to concentration (next example).

[SpectroChemPy](https://www.spectrochempy.fr/) provides the same
operations on real data — `ds.baseline(...)` and a `fit` of an IR
model — and reads JCAMP-DX archives via `scp.read_jcamp(path)`. The cell
below works on a synthetic carbonyl region with an added baseline drift
so it always runs.
"""


_BASELINE_CODE = r'''
# FTIR baseline correction (asymmetric least squares) + carbonyl peak fit.
# Synthesises a C=O region sitting on a curved baseline, removes the
# baseline with ALS, then fits the band with a pseudo-Voigt via
# scipy.optimize.curve_fit (guarded so it never errors).
import numpy as np
import matplotlib.pyplot as plt

BLUE, ORANGE, GREEN = "#3776ab", "#e07b39", "#50bea0"
rng = np.random.default_rng(0)


def pseudo_voigt(x, amp, cen, fwhm, eta):
    """Pseudo-Voigt: eta*Lorentzian + (1 - eta)*Gaussian, unit height."""
    sigma = fwhm / 2.3548
    gauss = np.exp(-0.5 * ((x - cen) / sigma) ** 2)
    hwhm = fwhm / 2.0
    lor = hwhm ** 2 / ((x - cen) ** 2 + hwhm ** 2)
    eta = min(max(eta, 0.0), 1.0)
    return amp * (eta * lor + (1.0 - eta) * gauss)


def als_baseline(y, lam=1e5, p=0.01, n_iter=10):
    """Asymmetric least squares baseline (Eilers & Boelens).

    lam = smoothness, p = asymmetry (peaks weighted ~p, valleys ~1-p).
    Pure NumPy second-difference penalty, no SciPy sparse needed.
    """
    n = y.size
    D = np.diff(np.eye(n), 2, axis=0)           # second-difference operator
    DTD = lam * (D.T @ D)
    w = np.ones(n)
    z = y.copy()
    for _ in range(n_iter):
        W = np.diag(w)
        z = np.linalg.solve(W + DTD, w * y)
        w = p * (y > z) + (1.0 - p) * (y <= z)  # asymmetric reweighting
    return z


# --- synthesise the carbonyl region on a curved baseline ----------------
x = np.linspace(1500.0, 1900.0, 400)            # cm^-1 (low->high here)
true_cen, true_area = 1715.0, 1.0
band = pseudo_voigt(x, 0.9, true_cen, 30.0, 0.6)
shoulder = pseudo_voigt(x, 0.25, 1760.0, 28.0, 0.5)
xs = (x - x.mean()) / (x.max() - x.min())
baseline_true = 0.30 + 0.20 * xs + 0.45 * xs ** 2   # curved drift
raw = band + shoulder + baseline_true + rng.normal(0.0, 0.008, x.size)

# --- correct the baseline and fit the carbonyl band ---------------------
base = als_baseline(raw, lam=1e5, p=0.01, n_iter=12)
corr = raw - base

p0 = [0.9, 1715.0, 30.0, 0.5]                   # amp, centre, FWHM, eta
try:
    from scipy.optimize import curve_fit
    popt, _ = curve_fit(pseudo_voigt, x, corr, p0=p0, maxfev=20000)
except Exception:
    popt = p0
amp_f, cen_f, fwhm_f, eta_f = popt
fwhm_f = abs(fwhm_f)
fit = pseudo_voigt(x, *popt)
area_f = np.trapz(fit, x)                        # integrated band area

fig, (a1, a2) = plt.subplots(1, 2, figsize=(8.4, 4.0))

a1.plot(x, raw, color=BLUE, lw=1.2, label="raw spectrum")
a1.plot(x, base, "--", color=ORANGE, lw=1.6, label="ALS baseline")
a1.set_xlim(1900, 1500)                          # IR convention: high->low
a1.set_xlabel(r"wavenumber (cm$^{-1}$)")
a1.set_ylabel("absorbance (arb.)")
a1.set_title("Raw spectrum + fitted baseline")
a1.legend(loc="upper right", frameon=False, fontsize=8)

a2.plot(x, corr, ".", ms=3, color=BLUE, alpha=0.5, label="baseline-corrected")
a2.plot(x, fit, "-", color=ORANGE, lw=2, label="pseudo-Voigt fit")
a2.axvline(cen_f, color=GREEN, ls=":", lw=1.2)
a2.set_xlim(1900, 1500)
a2.set_xlabel(r"wavenumber (cm$^{-1}$)")
a2.set_ylabel("absorbance (arb.)")
a2.set_title("Baseline-corrected carbonyl fit")
a2.legend(loc="upper right", frameon=False, fontsize=8)
a2.text(0.03, 0.95,
        r"$\nu_{C=O} = %.0f$ cm$^{-1}$" % cen_f + "\n"
        + r"FWHM $= %.0f$ cm$^{-1}$" % fwhm_f + "\n"
        + r"area $= %.2f$" % area_f,
        transform=a2.transAxes, va="top", fontsize=9,
        bbox=dict(boxstyle="round", fc="white", ec="0.8"))
fig.tight_layout()
fig
'''


def _ftir_baseline():
    return [_md(_BASELINE_INTRO), _code(_BASELINE_CODE)]


# -- 3. Beer-Lambert quantification ---------------------------------------

_BEER_INTRO = """\
# FTIR Beer-Lambert quantification

FTIR is quantitative through the **Beer-Lambert law**:

$$A = \\epsilon\\, l\\, c$$

the absorbance *A* of a band is proportional to the molar absorptivity
*epsilon*, the path length *l*, and the concentration *c*. Because *A*
(or, more robustly, the **integrated band area**) scales **linearly**
with concentration, a set of standards of known *c* gives a
**calibration line**; the area of an unknown then reads off its
concentration. Band **area** is preferred over peak **height** because
it is less sensitive to broadening and small baseline errors.

The workflow:

1. measure a band area for several **calibration standards** of known
   concentration,
2. fit `area = m * c + b` by least squares (`np.polyfit`) and check the
   fit quality with *R^2*,
3. measure the **unknown's** band area and invert the line to get its
   concentration.

[SpectroChemPy](https://www.spectrochempy.fr/) supports this end to end
(stacked dataset of standards, integration, and multivariate
calibration). The cell below builds a concentration series, integrates
the band for each, fits the calibration line, and predicts an unknown.
"""


_BEER_CODE = r'''
# Beer-Lambert quantification: build a concentration series whose band
# area scales linearly with c, fit the calibration line with np.polyfit,
# then predict the concentration of an unknown spectrum from its area.
import numpy as np
import matplotlib.pyplot as plt

BLUE, ORANGE, GREEN = "#3776ab", "#e07b39", "#50bea0"
rng = np.random.default_rng(0)


def gaussian(x, amp, cen, fwhm):
    sigma = fwhm / 2.3548
    return amp * np.exp(-0.5 * ((x - cen) / sigma) ** 2)


def band_area(x, y):
    """Integrated area of a band over the wavenumber grid (cm^-1)."""
    return abs(np.trapz(y, x))


# --- Beer-Lambert ground truth: A = eps * l * c -------------------------
eps, path = 0.85, 1.0                            # molar absorptivity, path
x = np.linspace(1600.0, 1850.0, 300)            # carbonyl region (cm^-1)
cen, fwhm = 1715.0, 28.0
concs = np.array([0.2, 0.4, 0.6, 0.8, 1.0])     # known concentrations (M)

# Build one spectrum per standard; peak amplitude follows Beer-Lambert.
spectra, areas = [], []
for c in concs:
    amp = eps * path * c                         # A_peak = eps*l*c
    y = gaussian(x, amp, cen, fwhm) + rng.normal(0.0, 0.004, x.size)
    spectra.append(y)
    areas.append(band_area(x, y))
areas = np.array(areas)

# --- linear calibration: area = m*c + b ---------------------------------
m, b = np.polyfit(concs, areas, 1)
fit_area = m * concs + b
ss_res = np.sum((areas - fit_area) ** 2)
ss_tot = np.sum((areas - areas.mean()) ** 2)
r2 = 1.0 - ss_res / ss_tot

# --- an "unknown" spectrum: measure its area, invert the line -----------
c_unknown_true = 0.72
amp_u = eps * path * c_unknown_true
y_unknown = gaussian(x, amp_u, cen, fwhm) + rng.normal(0.0, 0.004, x.size)
area_unknown = band_area(x, y_unknown)
c_pred = (area_unknown - b) / m                  # invert calibration

fig, (a1, a2) = plt.subplots(1, 2, figsize=(8.6, 4.0))

# Left: the concentration series, stacked with a vertical offset.
off = 0.0
for c, y in zip(concs, spectra):
    a1.plot(x, y + off, color=BLUE, lw=1.1)
    a1.text(x[0] + 5, off + y.max() * 0.5, r"$c = %.1f$ M" % c,
            fontsize=7.5, color="0.35", va="center")
    off += 0.9
a1.plot(x, y_unknown + off, color=ORANGE, lw=1.3)
a1.text(x[0] + 5, off + y_unknown.max() * 0.5, "unknown",
        fontsize=7.5, color=ORANGE, va="center")
a1.set_xlim(1850, 1600)                          # IR convention: high->low
a1.set_yticks([])
a1.set_xlabel(r"wavenumber (cm$^{-1}$)")
a1.set_ylabel("absorbance (offset)")
a1.set_title("Calibration series of spectra")

# Right: the calibration line with data, fit and the unknown projected.
a2.plot(concs, areas, "o", color=BLUE, label="standards")
c_line = np.linspace(0, 1.1, 50)
a2.plot(c_line, m * c_line + b, "-", color=ORANGE,
        label=r"fit  area $= %.2f\,c + %.2f$" % (m, b))
a2.plot([c_pred], [area_unknown], "D", color=GREEN, ms=8, label="unknown")
a2.hlines(area_unknown, 0, c_pred, color=GREEN, ls=":", lw=1)
a2.vlines(c_pred, 0, area_unknown, color=GREEN, ls=":", lw=1)
a2.set_xlim(0, 1.1)
a2.set_ylim(bottom=0)
a2.set_xlabel("concentration (M)")
a2.set_ylabel("integrated band area")
a2.set_title("Beer-Lambert calibration")
a2.legend(loc="upper left", frameon=False, fontsize=8)
a2.text(0.97, 0.05,
        r"$A = \epsilon\, l\, c$" + "\n"
        + r"$c_{pred} = %.2f$ M" % c_pred + "\n"
        + r"$R^2 = %.4f$" % r2,
        transform=a2.transAxes, va="bottom", ha="right", fontsize=9,
        bbox=dict(boxstyle="round", fc="white", ec="0.8"))
fig.tight_layout()
fig
'''


def _ftir_beer():
    return [_md(_BEER_INTRO), _code(_BEER_CODE)]


# -- Registry --------------------------------------------------------------

FTIR_EXAMPLES = [
    # (name, category, builder)
    ("FTIR Spectrum & Functional Groups (FTIR)", "FTIR", _ftir_groups),
    ("FTIR Baseline & Peak Fit (FTIR)", "FTIR", _ftir_baseline),
    ("FTIR Beer-Lambert Quantification (FTIR)", "FTIR", _ftir_beer),
]
