"""EDX / EDS (energy-dispersive X-ray spectroscopy) examples.

A self-contained companion to ``examples.py`` (Examples menu, "EDX"
category). EDX/EDS records the characteristic X-rays emitted when an
electron beam ionises atoms in a sample: each element fluoresces at
fixed energies (the K, L, M lines), so an EDX spectrum is a fingerprint
for elemental identification and, via the Cliff-Lorimer ratio method,
quantitative composition. The same signal, scanned across a sample,
gives line scans and 2-D elemental maps.

The standard Python toolkit is [HyperSpy](https://hyperspy.org) with its
electron-microscopy extension [eXSpy](https://hyperspy.org/exspy/), e.g.

```python
import exspy
s = exspy.data.EDS_TEM_FePt_nanoparticles()   # bundled FePt EDS-TEM map
s.add_elements(["Fe", "Pt"])
s.get_lines_intensity()                         # peak intensities
```

Every spectrum and map below is synthesised with NumPy (characteristic
Gaussian lines on a Kramers bremsstrahlung continuum) so the examples
always run offline; where a fit is involved it is guarded so the cell
still produces a figure if ``scipy`` is unavailable.

This module defines its own ``_md``/``_code`` helpers and exports
``EDX_EXAMPLES`` so it merges into ``examples.py`` without a circular
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


# -- 1. Spectrum & element identification ---------------------------------

_SPECTRUM_INTRO = """\
# EDX spectrum & element identification

When the electron beam in an SEM/TEM ionises a core shell, the atom
relaxes by emitting an X-ray at an energy fixed by the element and the
transition: **K-alpha**, **K-beta**, **L-alpha**, ... These
*characteristic lines* sit on a smooth **bremsstrahlung** continuum —
the radiation from beam electrons decelerating in the Coulomb field of
the nuclei. **Kramers' law** approximates that continuum as
*I(E) ~ Z (E0 - E) / E*, where *E0* is the beam energy (the Duane-Hunt
limit) and *Z* the mean atomic number. Identifying the peaks against a
table of line energies is the first step of every EDX analysis.

With [HyperSpy](https://hyperspy.org) + [eXSpy](https://hyperspy.org/exspy/)
a real EDS spectrum and its lines are a couple of calls:

```python
import exspy
s = exspy.data.EDS_TEM_FePt_nanoparticles()   # FePt EDS-TEM dataset
s.add_elements(["Fe", "Pt"])
s.add_lines()                                   # tabulated line energies
s.plot(True)                                    # spectrum + line markers
```

The cell below builds a synthetic spectrum for a Fe/Ti/Si/O sample:
Gaussian characteristic lines on a Kramers continuum plus Poisson-like
noise, with every peak **labelled** by element and line.
"""


_SPECTRUM = r'''
# Synthetic EDX spectrum: characteristic Gaussian lines on a Kramers
# bremsstrahlung continuum, with each peak labelled (element + line).
# With HyperSpy/eXSpy this would be exspy.data.EDS_TEM_FePt_nanoparticles().
import numpy as np
import matplotlib.pyplot as plt

rng = np.random.default_rng(0)
source = "synthetic EDX spectrum (pip install hyperspy exspy)"

E0 = 15.0                                   # beam energy / accel. voltage (kV)
E = np.linspace(0.10, E0, 2000)             # energy axis (keV)

# Characteristic lines: (element, line label, energy keV, relative weight).
LINES = [
    ("O",  r"$K_\alpha$", 0.52, 0.55),
    ("Si", r"$K_\alpha$", 1.74, 0.70),
    ("Ti", r"$K_\alpha$", 4.51, 0.85),
    ("Ti", r"$K_\beta$",  4.93, 0.18),
    ("Fe", r"$K_\alpha$", 6.40, 1.00),
    ("Fe", r"$K_\beta$",  7.06, 0.22),
]

# --- bremsstrahlung continuum: Kramers' law  I(E) ~ Z*(E0 - E)/E ----------
Z_mean = 20.0
brem = Z_mean * np.clip(E0 - E, 0.0, None) / E
brem *= 18.0 / brem.max()                    # scale to a few counts

# --- detector resolution: Gaussian FWHM grows with energy -----------------
def fwhm_keV(energy):
    """Si(Li)-like resolution: ~130 eV at Mn Ka, broadening with E."""
    noise = 0.130 ** 2                       # electronic noise (keV^2)
    fano = 0.00358 * energy                  # Fano term (~3.58 eV^2 per keV)
    return np.sqrt(noise + fano)

spectrum = brem.copy()
for el, line, e0, w in LINES:
    sigma = fwhm_keV(e0) / 2.355
    spectrum += 100.0 * w * np.exp(-0.5 * ((E - e0) / sigma) ** 2)

# --- counting (Poisson) noise --------------------------------------------
spectrum = rng.poisson(np.clip(spectrum, 0, None)).astype(float)

fig, ax = plt.subplots(figsize=(7.2, 4.3))
ax.plot(E, spectrum, color="#3776ab", lw=0.9)
ax.plot(E, brem, color="#e07b39", lw=1.2, ls="--", label="bremsstrahlung")

ymax = spectrum.max()
for el, line, e0, w in LINES:
    pk = spectrum[int(np.argmin(np.abs(E - e0)))]
    ax.annotate(el + " " + line, xy=(e0, pk),
                xytext=(e0, pk + 0.06 * ymax + 8),
                ha="center", va="bottom", fontsize=8,
                color="#222222",
                arrowprops=dict(arrowstyle="-", color="0.6", lw=0.7))

ax.set_xlabel(r"energy (keV)")
ax.set_ylabel(r"counts")
ax.set_title(r"EDX spectrum at $E_0 = %.0f$ kV" % E0)
ax.set_ylim(0, ymax * 1.30)
ax.set_xlim(0, E0)
ax.legend(loc="upper right", frameon=False, fontsize=8)
fig.text(0.01, 0.005, source, fontsize=7, color="0.45")
fig.tight_layout()
fig
'''


def _spectrum():
    return [_md(_SPECTRUM_INTRO), _code(_SPECTRUM)]


# -- 2. Quantification (Cliff-Lorimer) ------------------------------------

_QUANT_INTRO = """\
# EDX quantification — the Cliff-Lorimer ratio method

For a thin TEM specimen the **Cliff-Lorimer** equation turns measured
peak intensities into composition without standards:

$$\\frac{C_A}{C_B} = k_{AB}\\,\\frac{I_A}{I_B}$$

where *C* are weight fractions, *I* the net (background-subtracted) peak
intensities, and *k_AB* the **k-factor** relating the two elements
(tabulated or measured against a standard). Picking one reference
element *R*, every *C_i* follows from *C_i / C_R = k_iR (I_i / I_R)* plus
the closure condition *sum(C_i) = 1*. Multiplying by 100 gives weight %.

[eXSpy](https://hyperspy.org/exspy/) does exactly this:

```python
import exspy
s = exspy.data.EDS_TEM_FePt_nanoparticles()
s.add_elements(["Fe", "Pt"])
intensities = s.get_lines_intensity()
kfactors = [1.0, 1.45]                       # Fe_Ka, Pt_La (vs Fe)
wt = s.quantification(intensities, method="CL", factors=kfactors)
```

The cell below quantifies a three-element (Fe, Ti, O) thin film from
given peak intensities and k-factors, prints a table and draws a
weight-% bar chart.
"""


_QUANT = r'''
# Cliff-Lorimer quantification: C_A/C_B = k_AB * (I_A/I_B), referenced to
# one element, closed to 100 wt%. With eXSpy this is s.quantification(...).
import numpy as np
import matplotlib.pyplot as plt

source = "synthetic Cliff-Lorimer quant (pip install hyperspy exspy)"

# Measured net peak intensities (counts) and k-factors relative to Fe.
elements = ["Fe", "Ti", "O"]
lines = [r"$K_\alpha$", r"$K_\alpha$", r"$K_\alpha$"]
I = np.array([42000.0, 18500.0, 9000.0])     # net intensities I_i
k_vs_Fe = np.array([1.00, 1.12, 2.05])       # k_iFe (Fe is the reference)

# C_i / C_Fe = k_iFe * (I_i / I_Fe);  then normalise so sum C_i = 1.
ratio_to_ref = k_vs_Fe * (I / I[0])          # C_i / C_Fe  (C_Fe term = 1)
C = ratio_to_ref / ratio_to_ref.sum()        # weight fractions
wt_pct = 100.0 * C

# Printed table.
print("Cliff-Lorimer quantification (reference = Fe)")
print("-" * 46)
print("%-4s %-9s %10s %8s %8s" % ("el", "line", "I (cts)", "k_iFe", "wt%"))
print("-" * 46)
for el, ln, ii, kk, ww in zip(elements, lines, I, k_vs_Fe, wt_pct):
    label = {r"$K_\alpha$": "Ka"}.get(ln, ln)
    print("%-4s %-9s %10.0f %8.2f %8.1f" % (el, label, ii, kk, ww))
print("-" * 46)
print("%-4s %-9s %10s %8s %8.1f" % ("sum", "", "", "", wt_pct.sum()))

fig, ax = plt.subplots(figsize=(5.6, 4.2))
colors = ["#3776ab", "#e07b39", "#50bea0"]
bars = ax.bar(elements, wt_pct, color=colors, edgecolor="0.3", width=0.6)
for b, w in zip(bars, wt_pct):
    ax.text(b.get_x() + b.get_width() / 2, w + 1.2, "%.1f%%" % w,
            ha="center", va="bottom", fontsize=9)
ax.set_ylabel(r"composition (wt%)")
ax.set_xlabel(r"element")
ax.set_title("Cliff-Lorimer quantification")
ax.set_ylim(0, wt_pct.max() * 1.20)
fig.text(0.01, 0.005, source, fontsize=7, color="0.45")
fig.tight_layout()
fig
'''


def _quant():
    return [_md(_QUANT_INTRO), _code(_QUANT)]


# -- 3. Bremsstrahlung background subtraction -----------------------------

_BACKGROUND_INTRO = """\
# Bremsstrahlung background & net peak areas

Before peaks can be quantified the **bremsstrahlung continuum** under
them must be removed. Modelling the continuum with **Kramers' law**
(*I(E) ~ Z (E0 - E) / E*, optionally times a detector-efficiency term),
fitting it to the peak-free regions of the spectrum, and subtracting it
leaves the **net characteristic intensities** — the *I_A* that feed the
Cliff-Lorimer equation.

[eXSpy](https://hyperspy.org/exspy/) models the background and integrates
the lines for you:

```python
import exspy
s = exspy.data.EDS_TEM_FePt_nanoparticles()
m = s.create_model()                          # peaks + Kramers background
m.fit_background()
intensities = s.get_lines_intensity(background_windows=...)
```

The cell below builds a two-peak spectrum (Ti and Fe) on a Kramers
continuum, fits the background to the peak-free channels with a guarded
`curve_fit`, subtracts it, and integrates the **net** peak areas.
"""


_BACKGROUND = r'''
# Model the bremsstrahlung with Kramers' law, fit it on peak-free regions,
# subtract it, and recover net peak areas. eXSpy: m.fit_background().
import numpy as np
import matplotlib.pyplot as plt

rng = np.random.default_rng(0)
source = "synthetic background fit (pip install hyperspy exspy)"

E0 = 20.0
E = np.linspace(0.20, E0, 1600)
dE = E[1] - E[0]

# --- ground-truth continuum (Kramers) + two characteristic peaks ----------
Z_true = 24.0
brem_true = Z_true * np.clip(E0 - E, 0.0, None) / E
brem_true *= 25.0 / brem_true.max()

PEAKS = [("Ti", 4.51, 0.16), ("Fe", 6.40, 0.20)]   # (el, E keV, sigma keV)
AMP = [140.0, 200.0]
spectrum = brem_true.copy()
for (el, e0, sig), a in zip(PEAKS, AMP):
    spectrum += a * np.exp(-0.5 * ((E - e0) / sig) ** 2)
spectrum = rng.poisson(np.clip(spectrum, 0, None)).astype(float)

# --- select peak-free (background) channels -------------------------------
mask = np.ones_like(E, dtype=bool)
for el, e0, sig in PEAKS:
    mask &= np.abs(E - e0) > 5.0 * sig          # exclude windows around peaks

def kramers(energy, scale, Z):
    return scale * Z * np.clip(E0 - energy, 0.0, None) / energy

# --- fit the Kramers continuum to the background channels (guarded) -------
try:
    from scipy.optimize import curve_fit
    popt, _ = curve_fit(kramers, E[mask], spectrum[mask],
                        p0=[1.0, 24.0], maxfev=20000)
except Exception:
    # Fallback: least-squares scale of the Kramers shape on the background.
    shape = np.clip(E0 - E, 0.0, None) / E
    scale = np.sum(spectrum[mask] * shape[mask]) / np.sum(shape[mask] ** 2)
    popt = [scale, 1.0]

bg = kramers(E, *popt)
net = spectrum - bg

# --- net peak areas (sum over each peak window, in counts) ----------------
print("Net peak areas after background subtraction")
print("-" * 38)
for el, e0, sig in PEAKS:
    win = np.abs(E - e0) <= 3.0 * sig
    area = float(np.sum(np.clip(net[win], 0, None)) * dE)
    print("  %-3s %s  E=%4.2f keV   area=%8.1f" % (el, "Ka", e0, area))

fig, ax = plt.subplots(figsize=(7.0, 4.3))
ax.plot(E, spectrum, color="#3776ab", lw=0.8, label="raw")
ax.plot(E, bg, color="#e07b39", lw=1.6, label="Kramers background")
ax.plot(E, np.clip(net, 0, None), color="#50bea0", lw=1.0, label="net")
for el, e0, sig in PEAKS:
    ax.axvline(e0, color="0.6", ls=":", lw=0.8)
ax.set_xlabel(r"energy (keV)")
ax.set_ylabel(r"counts")
ax.set_title(r"Bremsstrahlung subtraction ($E_0 = %.0f$ kV)" % E0)
ax.set_xlim(0, E0)
ax.legend(loc="upper right", frameon=False, fontsize=8)
fig.text(0.01, 0.005, source, fontsize=7, color="0.45")
fig.tight_layout()
fig
'''


def _background():
    return [_md(_BACKGROUND_INTRO), _code(_BACKGROUND)]


# -- 4. Line scan across an interface -------------------------------------

_LINESCAN_INTRO = """\
# EDX line scan across an interface

Scanning the beam along a line and quantifying at each point gives a
**composition profile** — the everyday way to measure interdiffusion,
coating thickness or an interface width. Across a diffusion couple the
concentration follows a smooth **sigmoid** (an error-function profile is
the solution of Fick's law for a step interface), so each element rises
or falls through the boundary while the total stays at 100 at%.

In [HyperSpy](https://hyperspy.org) a line scan is a 1-D navigation
signal and the per-element profiles come straight from the line
intensities:

```python
import exspy
ls = exspy.data.EDS_TEM_FePt_nanoparticles()  # (here a map; .isig / line)
profiles = ls.get_lines_intensity()           # one image/profile per line
```

The cell below builds a three-element (Ni, Cr, Al) profile across an
interface with sigmoid transitions and plots composition (at%) versus
position.
"""


_LINESCAN = r'''
# EDX line scan: at% vs position across a diffusion couple / interface,
# with smooth sigmoid transitions. HyperSpy: ls.get_lines_intensity().
import numpy as np
import matplotlib.pyplot as plt

rng = np.random.default_rng(0)
source = "synthetic EDX line scan (pip install hyperspy exspy)"

x = np.linspace(0.0, 2.0, 240)              # position across interface (um)

def sigmoid(pos, x0, width):
    return 1.0 / (1.0 + np.exp(-(pos - x0) / width))

# Left phase ~ Ni-rich alloy; right phase ~ NiAl-type; Cr peaks mid-interface.
x0, w = 1.0, 0.10                           # interface centre / width (um)
s = sigmoid(x, x0, w)

raw = {
    "Ni": 70.0 * (1.0 - s) + 45.0 * s,      # decreases across interface
    "Al":  8.0 * (1.0 - s) + 48.0 * s,      # increases across interface
    "Cr": 22.0 + 6.0 * np.exp(-0.5 * ((x - x0) / 0.15) ** 2),  # interface bump
}

# Add counting noise, then renormalise each point to 100 at%.
profiles = {}
for el, p in raw.items():
    profiles[el] = np.clip(p + rng.normal(0.0, 1.2, x.size), 0, None)
stack = np.vstack([profiles[e] for e in raw])
stack = 100.0 * stack / stack.sum(axis=0, keepdims=True)
for i, el in enumerate(raw):
    profiles[el] = stack[i]

fig, ax = plt.subplots(figsize=(7.0, 4.3))
colors = {"Ni": "#3776ab", "Al": "#e07b39", "Cr": "#50bea0"}
for el in raw:
    ax.plot(x, profiles[el], color=colors[el], lw=1.8, label=el + r" $K_\alpha$")
ax.axvline(x0, color="0.6", ls="--", lw=1.0)
ax.text(x0, 96, " interface", color="0.4", fontsize=8, va="top")
ax.set_xlabel(r"position ($\mu$m)")
ax.set_ylabel(r"composition (at%)")
ax.set_title("EDX line scan across an interface")
ax.set_ylim(0, 100)
ax.set_xlim(x.min(), x.max())
ax.legend(loc="center right", frameon=False, fontsize=9)
fig.text(0.01, 0.005, source, fontsize=7, color="0.45")
fig.tight_layout()
fig
'''


def _linescan():
    return [_md(_LINESCAN_INTRO), _code(_LINESCAN)]


# -- 5. Elemental mapping -------------------------------------------------

_MAP_INTRO = """\
# EDX elemental mapping

Rastering the beam over an area and forming an image from each element's
line intensity gives **elemental maps** — the picture of *where* each
element sits in the microstructure. Overlaying maps as colour channels
makes an **RGB composite** that reveals phase distribution at a glance
(e.g. precipitates in a matrix).

[eXSpy](https://hyperspy.org/exspy/) produces maps directly from an
EDS spectrum image:

```python
import exspy
si = exspy.data.EDS_TEM_FePt_nanoparticles()  # 2-D EDS spectrum image
si.add_elements(["Fe", "Pt"])
maps = si.get_lines_intensity()               # one intensity map per line
import hyperspy.api as hs
hs.plot.plot_images(maps)                      # the elemental maps
```

The cell below synthesises a microstructure — circular precipitates in a
matrix — builds three element maps (Fe, Ti, O) from it, and shows each
map plus an RGB composite.
"""


_MAP = r'''
# EDX elemental maps over a synthetic microstructure (precipitates in a
# matrix) + an RGB composite. eXSpy: si.get_lines_intensity().
import numpy as np
import matplotlib.pyplot as plt

rng = np.random.default_rng(0)
source = "synthetic EDX maps (pip install hyperspy exspy)"

N = 128
yy, xx = np.mgrid[0:N, 0:N].astype(float)

# Scatter circular precipitates across the field of view.
n_ppt = 9
cx = rng.uniform(0.10, 0.90, n_ppt) * N
cy = rng.uniform(0.10, 0.90, n_ppt) * N
cr = rng.uniform(0.05, 0.11, n_ppt) * N

ppt = np.zeros((N, N))                       # 1 inside precipitates
for x0, y0, r in zip(cx, cy, cr):
    ppt = np.maximum(ppt, np.exp(-((xx - x0) ** 2 + (yy - y0) ** 2)
                                 / (2.0 * (0.6 * r) ** 2)))
ppt = np.clip(ppt, 0, 1)
matrix = 1.0 - ppt                           # complementary matrix fraction

# Elemental maps (counts): matrix is Fe-rich, precipitates are Ti+O oxides.
def noisy(field, scale):
    img = scale * field
    img = rng.poisson(np.clip(img, 0, None)).astype(float)
    return img

maps = {
    "Fe": noisy(matrix, 220.0),
    "Ti": noisy(ppt, 180.0),
    "O":  noisy(ppt, 120.0),
}

# RGB composite: R=Fe, G=Ti, B=O, each normalised to its own max.
def norm(a):
    m = a.max()
    return a / m if m > 0 else a
rgb = np.dstack([norm(maps["Fe"]), norm(maps["Ti"]), norm(maps["O"])])

fig, axes = plt.subplots(1, 4, figsize=(11.0, 3.2))
cmaps = {"Fe": "Reds", "Ti": "Greens", "O": "Blues"}
for ax, el in zip(axes[:3], ("Fe", "Ti", "O")):
    im = ax.imshow(maps[el], cmap=cmaps[el], origin="lower")
    ax.set_title(el + r" $K_\alpha$")
    ax.set_xticks([])
    ax.set_yticks([])
    fig.colorbar(im, ax=ax, fraction=0.046, pad=0.04)

axes[3].imshow(rgb, origin="lower")
axes[3].set_title("RGB composite\n(R=Fe, G=Ti, B=O)")
axes[3].set_xticks([])
axes[3].set_yticks([])

fig.suptitle("EDX elemental maps", y=1.02)
fig.text(0.01, 0.005, source, fontsize=7, color="0.45")
fig.tight_layout()
fig
'''


def _mapping():
    return [_md(_MAP_INTRO), _code(_MAP)]


# -- Registry --------------------------------------------------------------

EDX_EXAMPLES = [
    # (name, category, builder)
    ("EDX Spectrum & Element ID (EDX)", "EDX", _spectrum),
    ("EDX Quantification (Cliff-Lorimer) (EDX)", "EDX", _quant),
    ("EDX Bremsstrahlung Background (EDX)", "EDX", _background),
    ("EDX Line Scan (EDX)", "EDX", _linescan),
    ("EDX Elemental Mapping (EDX)", "EDX", _mapping),
]
