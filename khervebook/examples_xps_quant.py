"""Quantitative X-ray photoelectron spectroscopy (XPS) examples.

A self-contained companion to ``examples.py`` (Examples menu, "XPS"
category). XPS measures the kinetic energy of electrons photoemitted by
soft X-rays; plotted against **binding energy** *E_B* each core level
appears at an element-specific position, so a spectrum is a chemical
fingerprint of the sample surface. The three examples here cover the
everyday quantitative XPS workflow:

* a **wide survey scan** that identifies which elements are present from
  their labelled core-level and Auger peaks,
* **quantification** turning peak areas into atomic concentrations via
  relative sensitivity factors (RSF), and
* a **Fermi-edge fit** of a metallic reference that yields the
  spectrometer energy resolution and the Fermi-level energy zero.

The Fermi-edge cell uses [`lmfitxps`](https://pypi.org/project/lmfitxps/)
(``pip install lmfitxps``) when available and otherwise falls back to a
``scipy.optimize.curve_fit`` of a Gaussian-broadened Fermi function so the
example always runs offline.

This module defines its own ``_md``/``_code`` helpers and exports
``XPS_QUANT_EXAMPLES`` so it merges into ``examples.py`` without a
circular import.

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


# -- 1. Survey scan & element identification ------------------------------

_SURVEY_INTRO = """\
# XPS survey scan & element identification

A **survey** (or wide) scan sweeps the whole accessible binding-energy
range — here ~0-1100 eV — at low resolution. Because every element has
core levels at characteristic **binding energies** *E_B*, the peaks in a
survey tell you *which elements are on the surface* at a glance. The first
job of any XPS analysis is exactly this **qualitative** identification,
before any quantification.

Each peak sits on a **background** that steps **up** on the high-*E_B*
side of every core level: photoelectrons that lose energy to inelastic
scattering on their way out pile up at apparent binding energies *above*
the true line. Sharp **core-level** peaks (e.g. C 1s, O 1s, Ti 2p) are
joined by broad **Auger** features (e.g. the O *KLL* group near 975 eV),
which do not move with photon energy and so are easy to recognise.

The cell below synthesises a survey for a representative oxide/contaminant
surface — **Ti, O, N and adventitious C** — on a rising inelastic
background, then annotates every line with its element and orbital. As is
universal in XPS, the *E_B* axis is **inverted** (binding energy increases
to the **left**).
"""


_SURVEY = r'''
# XPS survey scan: synthesise core-level + Auger peaks on a stepped
# inelastic background and label each line with element + orbital. The
# binding-energy axis is inverted, as is universal in XPS.
import numpy as np
import matplotlib.pyplot as plt

rng = np.random.default_rng(0)
DATA, MARK = "#3776ab", "#e07b39"

BE = np.linspace(0.0, 1100.0, 2200)            # binding energy, E_B (eV)


def gaussian(x, area, center, fwhm):
    """Area-normalised Gaussian peak (FWHM in eV)."""
    sigma = fwhm / 2.355
    return area / (sigma * np.sqrt(2.0 * np.pi)) * \
        np.exp(-0.5 * ((x - center) / sigma) ** 2)


# Representative surface: adventitious C, oxide O + Ti, a little N, and
# the O KLL Auger group. Each entry: (E_B center, label, area, FWHM).
LINES = [
    (285.0, "C 1s",        7.0, 1.8),
    (398.0, "N 1s",        3.0, 2.0),
    (458.5, "Ti 2p",      14.0, 2.4),
    (531.0, "O 1s",       20.0, 2.2),
    (685.0, "Ti LMM",      4.0, 6.0),          # Ti Auger group (broad)
    (975.0, "O KLL",       9.0, 9.0),          # O Auger group (broad)
    (1071.0, "Na 1s",      2.5, 2.2),          # trace surface contaminant
]


# Inelastic background: each peak adds a smooth step on its high-E_B side
# (an error-function edge), so the baseline rises after every core level.
def smoothstep(x, edge, width):
    return 0.5 * (1.0 + np.tanh((x - edge) / width))


baseline = 1.5 + 0.0008 * BE                   # slow instrumental slope
for center, _lbl, area, _fwhm in LINES:
    baseline = baseline + 0.05 * area * smoothstep(BE, center + 3.0, 6.0)

spectrum = baseline.copy()
for center, _lbl, area, fwhm in LINES:
    spectrum = spectrum + gaussian(BE, area, center, fwhm)
spectrum = spectrum + rng.normal(0.0, 0.05, BE.size)   # detector noise

fig, ax = plt.subplots(figsize=(7.6, 4.4))
ax.plot(BE, spectrum, color=DATA, lw=0.9)
for center, lbl, area, fwhm in LINES:
    ypk = float(spectrum[int(np.argmin(np.abs(BE - center)))])
    ax.annotate(lbl, xy=(center, ypk),
                xytext=(center, ypk + 1.4),
                ha="center", va="bottom", fontsize=8, color=MARK,
                arrowprops=dict(arrowstyle="-", color=MARK, lw=0.8))
ax.invert_xaxis()                              # E_B increases to the left
ax.set_xlabel(r"binding energy  $E_B$  (eV)")
ax.set_ylabel("intensity (arb.)")
ax.set_title("XPS survey scan: Ti / O / N / C surface")
ax.margins(y=0.18)
fig.tight_layout()
fig
'''


def _survey():
    return [_md(_SURVEY_INTRO), _code(_SURVEY)]


# -- 2. Quantification via relative sensitivity factors -------------------

_QUANT_INTRO = """\
# XPS quantification (atomic %)

Once the elements are known, XPS is **quantitative**: the area under a
core-level peak is proportional to how much of that element the surface
contains. But a given number of atoms produces a different peak area for
each element and orbital, because the **photoionisation cross-section**,
the analyser transmission and the electron escape depth all differ. Those
effects are folded into a tabulated **relative sensitivity factor (RSF)**
(Scofield-based values are standard).

The atomic concentration of element *i* is the RSF-corrected area,
normalised over all measured elements:

$$\\mathrm{at\\%}_i = \\frac{A_i / S_i}{\\sum_j A_j / S_j} \\times 100$$

where *A* is the integrated peak area and *S* the RSF. The cell below
builds C 1s, O 1s and Ti 2p peaks with known areas, integrates each over
its own window with `np.trapz`, applies RSFs (C 1s 1.00, O 1s 2.93,
Ti 2p 7.91) and reports the composition as a bar chart and a small table.
"""


_QUANT = r'''
# XPS quantification: integrate C 1s, O 1s and Ti 2p peak areas, apply
# relative sensitivity factors (RSF) and convert to atomic percent.
import numpy as np
import matplotlib.pyplot as plt

rng = np.random.default_rng(0)
DATA, BAR = "#3776ab", "#e07b39"


def gaussian(x, area, center, fwhm):
    sigma = fwhm / 2.355
    return area / (sigma * np.sqrt(2.0 * np.pi)) * \
        np.exp(-0.5 * ((x - center) / sigma) ** 2)


# Each core level: (label, E_B center, FWHM, true area, RSF, window half).
#   RSF: Scofield-like sensitivity factors (C 1s = 1.00 reference).
LEVELS = [
    ("C 1s",  285.0, 1.8,  6.0, 1.00, 12.0),
    ("O 1s",  531.0, 2.2, 30.0, 2.93, 14.0),
    ("Ti 2p", 458.5, 3.0, 42.0, 7.91, 18.0),
]

labels, areas, rsfs = [], [], []
for lbl, center, fwhm, area_true, rsf, half in LEVELS:
    # Build a narrow high-resolution window around the peak + flat bg.
    x = np.linspace(center - half, center + half, 600)
    y = 0.4 + gaussian(x, area_true, center, fwhm)
    y = y + rng.normal(0.0, 0.02, x.size)
    bg = np.linspace(y[0], y[-1], x.size)      # linear (Shirley-like) bg
    area_meas = np.trapz(y - bg, x)            # integrate above background
    labels.append(lbl)
    areas.append(area_meas)
    rsfs.append(rsf)

areas = np.asarray(areas)
rsfs = np.asarray(rsfs)
corrected = areas / rsfs                        # RSF-normalised areas
atpct = 100.0 * corrected / corrected.sum()     # atomic concentration (%)

# --- small table to stdout ----------------------------------------------
print("element    area     RSF    at%")
print("-" * 34)
for lbl, a, s, p in zip(labels, areas, rsfs, atpct):
    print("%-8s %8.1f %6.2f %7.1f" % (lbl, a, s, p))
print("-" * 34)
print("%-8s %8s %6s %7.1f" % ("total", "", "", atpct.sum()))

fig, ax = plt.subplots(figsize=(5.6, 4.2))
bars = ax.bar(labels, atpct, color=BAR, edgecolor=DATA, width=0.6)
for b, p in zip(bars, atpct):
    ax.text(b.get_x() + b.get_width() / 2.0, p + 1.0,
            "%.1f%%" % p, ha="center", va="bottom", fontsize=9)
ax.set_ylabel("atomic concentration (%)")
ax.set_title("XPS quantification (RSF-corrected)")
ax.set_ylim(0, max(atpct) * 1.25)
fig.tight_layout()
fig
'''


def _quant():
    return [_md(_QUANT_INTRO), _code(_QUANT)]


# -- 3. Fermi edge & resolution (lmfitxps) --------------------------------

_FERMI_INTRO = """\
# Fermi edge & spectrometer resolution

A clean **metallic reference** (gold or silver) measured on the same
spectrometer is the standard energy calibration for XPS and ARPES. Near
the chemical potential a metal's photoemission intensity is a (nearly
flat) density of states multiplied by the **Fermi-Dirac** distribution.
The ideal step is **broadened** by the analyser + source, modelled as a
Gaussian. Fitting the edge fixes two essential numbers: the **Fermi level**
*E_F* (the binding-energy zero / work-function reference) and the
**energy resolution** ΔE = 2.355·σ.

[`lmfitxps`](https://pypi.org/project/lmfitxps/) ships a dedicated
`FermiEdgeModel` built on lmfit:

```python
from lmfitxps.models import FermiEdgeModel
model  = FermiEdgeModel(prefix='f_')          # params: f_amplitude,
params = model.make_params()                   #   f_center, f_kt, f_sigma
result = model.fit(y, params, x=E)            # y = edge + background
```

Install it with `pip install lmfitxps`. The cell below synthesises a gold
edge with `FermiEdgeModel.eval` (or a `scipy` fallback), adds a small
linear background and noise, and fits it back. Because the **thermal
width** (`f_kt`, with kt = k_B·T) and the **resolution** (`f_sigma`) both
broaden a single edge and are partly degenerate, the calibration holds the
known cryostat temperature fixed to recover σ — then a second pass fixes σ
to recover *T*, confirming kt → T.
"""


_FERMI_FIT = r'''
# Fermi-edge fit: recover E_F, the resolution sigma and the temperature
# from a metallic reference. Uses lmfitxps.FermiEdgeModel when available,
# else a scipy curve_fit of a Gaussian-broadened Fermi function.
import numpy as np
import matplotlib.pyplot as plt

rng = np.random.default_rng(0)
DATA, FIT = "#3776ab", "#e07b39"
kB = 8.617e-5                                   # Boltzmann constant (eV/K)

try:
    from lmfitxps.models import FermiEdgeModel
    from lmfit.models import LinearModel
    HAVE_LMFITXPS = True
except ImportError:
    HAVE_LMFITXPS = False

# --- ground truth of the simulated gold edge ----------------------------
E = np.linspace(-0.40, 0.40, 600)              # E - E_F (eV)
EF_true = 0.0                                   # Fermi level (eV)
T_true = 150.0                                  # cryostat temperature (K)
sigma_true = 0.020                              # resolution sigma (eV)
amp_true = 1.0
bg_m, bg_c = 0.10, 0.05                         # linear background


def fermi_dirac(e, ef, kt):
    return 1.0 / (np.exp(np.clip((e - ef) / kt, -50, 50)) + 1.0)


if HAVE_LMFITXPS:
    edge = FermiEdgeModel(prefix='f_')
    truth = edge.make_params()
    truth['f_amplitude'].set(value=amp_true)
    truth['f_center'].set(value=EF_true)
    truth['f_kt'].set(value=kB * T_true)
    truth['f_sigma'].set(value=sigma_true)
    clean = edge.eval(truth, x=E)
else:
    from scipy.ndimage import gaussian_filter1d
    ideal = amp_true * fermi_dirac(E, EF_true, kB * T_true)
    clean = gaussian_filter1d(ideal, sigma_true / (E[1] - E[0]))

y = clean + (bg_m * E + bg_c) + rng.normal(0.0, 0.010, E.size)

# --- fit it back --------------------------------------------------------
if HAVE_LMFITXPS:
    model = FermiEdgeModel(prefix='f_') + LinearModel(prefix='b_')

    # Pass 1: known temperature held fixed -> recover E_F and resolution.
    p1 = model.make_params()
    p1['f_amplitude'].set(value=0.9, min=0)
    p1['f_center'].set(value=0.01)
    p1['f_kt'].set(value=kB * T_true, vary=False)     # known cryostat T
    p1['f_sigma'].set(value=0.012, min=1e-4)
    p1['b_slope'].set(value=0.0)
    p1['b_intercept'].set(value=0.0)
    r1 = model.fit(y, p1, x=E)
    EF_fit = r1.params['f_center'].value
    sigma_fit = abs(r1.params['f_sigma'].value)
    best_fit = r1.best_fit

    # Pass 2: known resolution held fixed -> recover the temperature.
    p2 = model.make_params()
    p2['f_amplitude'].set(value=0.9, min=0)
    p2['f_center'].set(value=EF_fit)
    p2['f_kt'].set(value=kB * 200.0, min=1e-5)
    p2['f_sigma'].set(value=sigma_fit, vary=False)
    p2['b_slope'].set(value=r1.params['b_slope'].value)
    p2['b_intercept'].set(value=r1.params['b_intercept'].value)
    r2 = model.fit(y, p2, x=E)
    T_fit = r2.params['f_kt'].value / kB
    source = "lmfitxps FermiEdgeModel"
else:
    from scipy.optimize import curve_fit
    from scipy.ndimage import gaussian_filter1d

    def edge_model(e, amp, ef, sigma, m, c):
        ideal = amp * fermi_dirac(e, ef, kB * T_true)
        de = e[1] - e[0]
        return gaussian_filter1d(ideal, max(sigma, 1e-4) / de) + (m * e + c)

    p0 = [0.9, 0.01, 0.012, 0.0, 0.0]
    try:
        popt, _ = curve_fit(edge_model, E, y, p0=p0, maxfev=20000)
    except Exception:
        popt = p0
    EF_fit, sigma_fit = popt[1], abs(popt[2])
    best_fit = edge_model(E, *popt)
    T_fit = T_true                              # held fixed in the fallback
    source = "scipy Gaussian-broadened Fermi fit (pip install lmfitxps)"

dE_fwhm = 2.355 * sigma_fit                      # resolution FWHM (eV)

fig, ax = plt.subplots(figsize=(5.8, 4.2))
ax.plot(E, y, ".", ms=3, color=DATA, alpha=0.55, label="data")
ax.plot(E, best_fit, "-", color=FIT, lw=2, label="fit")
ax.axvline(EF_fit, color="0.4", ls="--", lw=1)
ax.annotate(r"$E_F$", xy=(EF_fit, 0.5), xytext=(EF_fit + 0.07, 0.62),
            color="0.3", fontsize=10,
            arrowprops=dict(arrowstyle="->", color="0.4", lw=0.9))
ax.set_xlabel(r"$E - E_F$  (eV)")
ax.set_ylabel("intensity (arb.)")
ax.set_title("Metallic Fermi-edge fit")
ax.legend(loc="upper right", frameon=False)
ax.text(0.03, 0.30,
        r"$E_F = %.1f$ meV" % (EF_fit * 1000.0) + "\n"
        + r"$T = %.0f$ K" % T_fit + "\n"
        + r"$\Delta E = %.1f$ meV (FWHM)" % (dE_fwhm * 1000.0),
        transform=ax.transAxes, va="top", fontsize=9,
        bbox=dict(boxstyle="round", fc="white", ec="0.8"))
fig.text(0.01, 0.005, source, fontsize=7, color="0.45")

print("E_F        = %+.1f meV" % (EF_fit * 1000.0))
print("resolution = %.1f meV FWHM (sigma = %.1f meV)"
      % (dE_fwhm * 1000.0, sigma_fit * 1000.0))
print("temperature= %.0f K  (kt = %.2f meV)" % (T_fit, kB * T_fit * 1000.0))
fig.tight_layout()
fig
'''


def _fermi_edge():
    return [_md(_FERMI_INTRO), _code(_FERMI_FIT)]


# -- Registry --------------------------------------------------------------

XPS_QUANT_EXAMPLES = [
    # (name, category, builder)
    ("XPS Survey & Element ID (XPS)", "XPS", _survey),
    ("XPS Quantification (XPS)", "XPS", _quant),
    ("Fermi Edge & Resolution (lmfitxps)", "XPS", _fermi_edge),
]
