"""XPS curve-fitting examples using the ``lmfitxps`` library.

A self-contained companion to ``examples.py`` (Examples menu, "XPS"
category). [`lmfitxps`](https://pypi.org/project/lmfitxps/) is an
add-on to `lmfit` for **X-ray photoelectron spectroscopy (XPS)**: it
ships the line shapes and inelastic backgrounds that quantitative core-
level analysis needs, in particular

* ``ConvGaussianDoniachSinglett`` / ``ConvGaussianDoniachDublett`` -
  the **Doniach-Sunjic** asymmetric line shape convolved with a
  Gaussian (the instrument + phonon broadening), as a singlet or a
  spin-orbit doublet, and
* ``shirley_calculate`` / ``tougaard_calculate`` - the two standard
  **inelastic backgrounds** subtracted before peak areas are measured.

Each code cell uses the real ``lmfitxps`` API when the library is
installed and otherwise still synthesises faithful data with NumPy so
the example always runs offline (it just skips the fit and notes
``pip install lmfitxps``).

This module defines its own ``_md``/``_code`` helpers and exports
``XPS_FIT_EXAMPLES`` so it merges into ``examples.py`` without a
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


# -- 1. Spin-orbit doublet -------------------------------------------------

_DOUBLET_INTRO = """\
# Spin-orbit doublet (lmfitxps)

A core level with orbital angular momentum *l* > 0 is split by the
**spin-orbit interaction** into a doublet: the *j = l + 1/2* and
*j = l - 1/2* components. The Au **4f** level is the workhorse XPS
reference - it appears as $4f_{7/2}$ and $4f_{5/2}$ peaks separated by a
fixed **spin-orbit splitting** of about 3.67 eV, with a degeneracy-fixed
**branching ratio** of 0.75 (the (2j+1) ratio 8 : 6 = 4f₅/₂ : 4f₇/₂ ⇒
4f₇/₂ carries the larger share).

In a *metal* the photoemission line is not symmetric. The sudden core
hole couples to the conduction electrons, which can absorb arbitrarily
small energies, dragging a tail toward higher binding energy. This is
the **Doniach-Sunjic** line shape, governed by an asymmetry parameter
*alpha* (here the Doniach `gamma`). The measured peak is that
intrinsically asymmetric Lorentzian-like shape **convolved with a
Gaussian** for the spectrometer and phonon broadening.

[`lmfitxps`](https://pypi.org/project/lmfitxps/) gives this as a single
`lmfit` model:

```python
from lmfitxps.models import ConvGaussianDoniachDublett
from lmfit.models import LinearModel
peak  = ConvGaussianDoniachDublett(prefix='d_')
model = peak + LinearModel(prefix='bg_')      # + linear background
result = model.fit(y, params, x=binding_energy)
```

The doublet model ties the two spin-orbit components together: one
`d_amplitude`, `d_sigma` (Lorentzian width), `d_gamma` (asymmetry) and
`d_gaussian_sigma`, plus `d_soc` (the splitting) and `d_height_ratio`
(the branching ratio). Because the splitting and the ratio are **fixed
atomic constants**, we hold them with `vary=False` and let the fit find
the position, widths and intensity. The cell below synthesises an Au 4f
doublet, fits it back, and reports the $4f_{7/2}$ binding energy and
FWHM with a residual strip beneath.
"""


_DOUBLET_FIT = r'''
# Spin-orbit doublet fit: a metallic Au 4f doublet with the Doniach-Sunjic
# line shape (asymmetric, convolved with a Gaussian) on a linear background.
# With lmfitxps this is ConvGaussianDoniachDublett + LinearModel; the data
# are synthesised from the same model and fitted back so it always runs.
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.gridspec import GridSpec

DATA, FIT, PEAK, BG = "#3776ab", "#e07b39", "#2a9d4a", "#9467bd"

try:
    from lmfitxps.models import ConvGaussianDoniachDublett
    from lmfit.models import LinearModel
    HAVE = True
except ImportError:
    HAVE = False

# --- binding-energy axis and ground-truth Au 4f doublet ------------------
x = np.linspace(80.0, 92.0, 450)              # binding energy (eV)
rng = np.random.default_rng(0)

# Known atomic constants for Au 4f: splitting 3.67 eV, branching 0.75.
SOC_TRUE, RATIO_TRUE = 3.67, 0.75
CEN_TRUE = 84.0                               # 4f_7/2 binding energy (eV)
bg_intercept_true, bg_slope_true = 200.0, 6.0
noise = 30.0

if HAVE:
    _peak = ConvGaussianDoniachDublett(prefix='d_')
    t = _peak.make_params()
    t['d_amplitude'].set(value=5000.0)
    t['d_sigma'].set(value=0.25)              # Lorentzian width
    t['d_gamma'].set(value=0.05)              # Doniach asymmetry
    t['d_gaussian_sigma'].set(value=0.30)     # instrument broadening
    t['d_center'].set(value=CEN_TRUE)
    # lmfitxps puts the partner at center - soc; negate so the weaker
    # 4f_5/2 sits at HIGHER binding energy than 4f_7/2 (correct for 4f).
    t['d_soc'].set(value=-SOC_TRUE)
    t['d_height_ratio'].set(value=RATIO_TRUE)
    t['d_fct_coster_kronig'].set(value=1.0)
    bg_true = bg_intercept_true + bg_slope_true * (x - x[0])
    y = _peak.eval(t, x=x) + bg_true + rng.normal(0.0, noise, x.size)
    source = "synthetic Au 4f doublet, fitted with lmfitxps"
else:
    # Faithful fallback: two asymmetric peaks (Lorentzian + a tail) so the
    # figure is realistic even without lmfitxps; we just skip the fit.
    def _asym(e, amp, cen, w, asym):
        lor = amp * w ** 2 / ((e - cen) ** 2 + w ** 2)
        tail = amp * asym * np.exp(-(e - cen) / 0.8) * (e > cen)
        return lor + tail
    bg_true = bg_intercept_true + bg_slope_true * (x - x[0])
    y = (_asym(x, 5000.0, CEN_TRUE, 0.45, 0.15)
         + _asym(x, 5000.0 * RATIO_TRUE, CEN_TRUE + SOC_TRUE, 0.45, 0.15)
         + bg_true + rng.normal(0.0, noise, x.size))
    source = "synthetic Au 4f doublet (pip install lmfitxps to fit)"

# --- fit: free position/widths/intensity; fix the atomic constants -------
if HAVE:
    full = ConvGaussianDoniachDublett(prefix='d_') + LinearModel(prefix='bg_')
    p = full.make_params()
    p['d_amplitude'].set(value=4000.0, min=0)
    p['d_sigma'].set(value=0.30, min=0.02, max=2.0)
    p['d_gamma'].set(value=0.05, min=0.0, max=0.5)
    p['d_gaussian_sigma'].set(value=0.30, min=0.05, max=2.0)
    p['d_center'].set(value=84.2, min=83.0, max=85.0)
    p['d_soc'].set(value=-SOC_TRUE, vary=False)         # fixed splitting
    p['d_height_ratio'].set(value=RATIO_TRUE, vary=False)   # fixed ratio
    p['d_fct_coster_kronig'].set(value=1.0, vary=False)
    p['bg_intercept'].set(value=200.0)
    p['bg_slope'].set(value=6.0)
    result = full.fit(y, p, x=x)
    best = result.best_fit
    comps = result.eval_components(x=x)
    peak_curve, bg_curve = comps['d_'], comps['bg_']
    cen_fit = result.params['d_center'].value
    # Total FWHM from the model's reported Gaussian + Lorentzian widths.
    g = result.params['d_gaussian_fwhm'].value
    lo = result.params['d_lorentzian_fwhm_p1'].value
    fwhm = 0.5346 * lo + np.sqrt(0.2166 * lo ** 2 + g ** 2)  # Voigt approx.
    resid = y - best
else:
    best = y.copy()
    bg_curve = bg_true
    peak_curve = y - bg_true
    cen_fit, fwhm = CEN_TRUE, float("nan")
    resid = np.zeros_like(y)

# --- plot: spectrum + components on top, residual strip below ------------
fig = plt.figure(figsize=(6.0, 5.2), constrained_layout=True)
gs = GridSpec(2, 1, height_ratios=[4, 1], hspace=0.08, figure=fig)
ax = fig.add_subplot(gs[0])
axr = fig.add_subplot(gs[1], sharex=ax)

ax.plot(x, y, ".", ms=3, color=DATA, alpha=0.55, label="data")
ax.plot(x, best, "-", color=FIT, lw=2, label="total fit")
ax.plot(x, peak_curve + bg_curve, "-", color=PEAK, lw=1.3, label="Au 4f")
ax.plot(x, bg_curve, "--", color=BG, lw=1.2, label="background")
ax.axvline(cen_fit, color="0.55", ls=":", lw=0.9)
ax.set_ylabel("intensity (counts)")
ax.set_title("Au 4f spin-orbit doublet (Doniach-Sunjic)")
ax.legend(loc="upper left", frameon=False, fontsize=8)
ann = r"$4f_{7/2}\ E_B = %.2f$ eV" % cen_fit
if np.isfinite(fwhm):
    ann += "\n" + r"FWHM $= %.2f$ eV" % fwhm
ax.text(0.97, 0.95, ann, transform=ax.transAxes, va="top", ha="right",
        fontsize=9, bbox=dict(boxstyle="round", fc="white", ec="0.8"))
ax.invert_xaxis()                              # binding energy to the left
plt.setp(ax.get_xticklabels(), visible=False)

axr.axhline(0, color="0.6", lw=0.8)
axr.plot(x, resid, ".", ms=2.5, color=DATA, alpha=0.6)
axr.set_xlabel(r"binding energy  $E_B$  (eV)")
axr.set_ylabel("resid.")
# axr shares x with ax, which is already inverted — don't invert twice.

fig.text(0.01, 0.005, source, fontsize=7, color="0.45")
fig
'''


def _doublet():
    return [_md(_DOUBLET_INTRO), _code(_DOUBLET_FIT)]


# -- 2. Shirley vs Tougaard background ------------------------------------

_BG_INTRO = """\
# Shirley vs Tougaard background (lmfitxps)

Before a core-level **peak area** can be measured it must be separated
from the **inelastic background** - the secondary electrons that lost
energy on the way out and pile up on the high-binding-energy side of
every peak. Two recipes dominate XPS:

* **Shirley** - an *iterative* background where the step at each energy
  is proportional to the peak area still *above* it at lower binding
  energy. It needs no physical parameters, just the two endpoints, and
  is the everyday default for well-separated lines.
* **Tougaard** - a *physical* background built from the **universal
  inelastic cross-section** *B·E / (C + E²)²* (the two-parameter form
  here, `tb`/`tc`). It models the real loss tail, so it handles broad
  or overlapping structure better but is more sensitive to where the
  fit window ends.

[`lmfitxps`](https://pypi.org/project/lmfitxps/) computes both as static
arrays from the raw data:

```python
from lmfitxps.backgrounds import shirley_calculate, tougaard_calculate
shirley = shirley_calculate(x, y, tol=1e-6, maxit=50)
tougaard, B = tougaard_calculate(x, y, tb=2866, tc=1643)  # returns (bg, B)
```

The choice matters: the two backgrounds subtract a **different amount**,
so the integrated peak area - and therefore any quantification - shifts
between them. The cell below puts one core level on a realistic loss
tail, overlays both backgrounds, and reports how much the peak **area**
changes when you switch from Shirley to Tougaard.
"""


_BG_FIT = r'''
# Shirley vs Tougaard: one core level on an inelastic loss tail. Compute
# both static backgrounds with lmfitxps, overlay them on the raw data, then
# subtract each and compare the integrated peak AREA. Data are synthesised
# (a Doniach-Sunjic peak + an exponential loss tail) so it always runs.
import numpy as np
import matplotlib.pyplot as plt

DATA, SH, TO = "#3776ab", "#e07b39", "#2a9d4a"

try:
    from lmfitxps.models import ConvGaussianDoniachSinglett
    from lmfitxps.backgrounds import shirley_calculate, tougaard_calculate
    HAVE = True
except ImportError:
    HAVE = False

# --- O 1s-like core level on a rising inelastic background ---------------
x = np.linspace(525.0, 545.0, 450)            # binding energy (eV)
rng = np.random.default_rng(0)
CEN = 531.0

if HAVE:
    _pk = ConvGaussianDoniachSinglett(prefix='p_')
    t = _pk.make_params()
    t['p_amplitude'].set(value=10000.0)
    t['p_sigma'].set(value=0.45)
    t['p_gamma'].set(value=0.03)
    t['p_gaussian_sigma'].set(value=0.45)
    t['p_center'].set(value=CEN)
    sig = _pk.eval(t, x=x)
else:
    sig = 10000.0 * 0.45 ** 2 / ((x - CEN) ** 2 + 0.45 ** 2)

# Each photoelectron seeds a tail to higher binding energy: convolve the
# clean peak with a one-sided exponential loss function.
loss = np.exp(-np.maximum(x - x[0], 0.0) / 8.0)
tail = np.convolve(sig, loss, mode="full")[:x.size]
tail = tail / tail.max() * 1500.0
y = sig + 250.0 + tail + rng.normal(0.0, 25.0, x.size)

# --- both backgrounds ----------------------------------------------------
if HAVE:
    shirley = np.asarray(shirley_calculate(x, y, tol=1e-6, maxit=50))
    tougaard, _B = tougaard_calculate(x, y, tb=2866, tc=1643, tcd=1, td=1)
    tougaard = np.asarray(tougaard)
    note = "synthetic O 1s on a loss tail, backgrounds via lmfitxps"
else:
    # Endpoint baselines as a stand-in when lmfitxps is unavailable.
    shirley = np.linspace(y[0], y[-1], x.size)
    tougaard = np.full_like(x, y.min())
    note = "synthetic O 1s on a loss tail (pip install lmfitxps)"

peak_sh = np.clip(y - shirley, 0.0, None)
peak_to = np.clip(y - tougaard, 0.0, None)
area_sh = float(np.trapz(peak_sh, x))
area_to = float(np.trapz(peak_to, x))
pct = 100.0 * (area_to - area_sh) / area_sh

# --- plot: raw + both backgrounds (left); subtracted peaks (right) -------
fig, (a1, a2) = plt.subplots(1, 2, figsize=(8.4, 4.2))

a1.plot(x, y, ".", ms=3, color=DATA, alpha=0.5, label="data")
a1.plot(x, shirley, "-", color=SH, lw=1.8, label="Shirley")
a1.plot(x, tougaard, "-", color=TO, lw=1.8, label="Tougaard")
a1.set_xlabel(r"binding energy  $E_B$  (eV)")
a1.set_ylabel("intensity (counts)")
a1.set_title("Raw spectrum + backgrounds")
a1.legend(loc="upper right", frameon=False, fontsize=8)
a1.invert_xaxis()

a2.fill_between(x, 0, peak_sh, color=SH, alpha=0.25)
a2.plot(x, peak_sh, "-", color=SH, lw=1.6, label="Shirley peak")
a2.plot(x, peak_to, "-", color=TO, lw=1.6, label="Tougaard peak")
a2.set_xlabel(r"binding energy  $E_B$  (eV)")
a2.set_ylabel("intensity (counts)")
a2.set_title("Background-subtracted peak")
a2.legend(loc="upper right", frameon=False, fontsize=8)
a2.text(0.03, 0.95,
        r"$A_{Sh} = %.3g$" % area_sh + "\n"
        + r"$A_{To} = %.3g$" % area_to + "\n"
        + r"$\Delta A = %+.1f\%%$" % pct,
        transform=a2.transAxes, va="top", fontsize=9,
        bbox=dict(boxstyle="round", fc="white", ec="0.8"))
a2.invert_xaxis()

fig.text(0.01, 0.005, note, fontsize=7, color="0.45")
fig.tight_layout()
fig
'''


def _backgrounds():
    return [_md(_BG_INTRO), _code(_BG_FIT)]


# -- 3. Chemical-state fit ------------------------------------------------

_CHEM_INTRO = """\
# Chemical-state fit (lmfitxps)

The power of XPS is **chemical sensitivity**: the same core level shifts
to higher binding energy as the atom's local charge increases. The C
**1s** region of an oxidised polymer or contaminated surface is the
textbook case - one envelope hides several **chemical states** whose
small **chemical shifts** report the bonding:

| component | bond            | $E_B$ (eV) |
|-----------|-----------------|-----------|
| C-C       | hydrocarbon     | 284.8     |
| C-O       | alcohol / ether | 286.3     |
| C=O       | carbonyl        | 287.9     |
| O-C=O     | carboxyl / ester| 289.0     |

Quantification means fitting the envelope as a **sum of components** -
one [`lmfitxps`](https://pypi.org/project/lmfitxps/)
`ConvGaussianDoniachSinglett` per state - on a background, then reading
each component's **area fraction**:

```python
from lmfitxps.models import ConvGaussianDoniachSinglett
from lmfit.models import LinearModel
model = (ConvGaussianDoniachSinglett(prefix='cc_')
         + ConvGaussianDoniachSinglett(prefix='co_')
         + ... + LinearModel(prefix='bg_'))
result = model.fit(y, params, x=binding_energy)
```

Each peak's centre is constrained to a narrow window around its expected
shift; the areas then come from integrating the fitted components
(`result.eval_components`). The cell below synthesises a four-component C
1s envelope, fits it, fills each component, and reports the four area
fractions (%).
"""


_CHEM_FIT = r'''
# Chemical-state fit: a C 1s envelope as four ConvGaussianDoniachSinglett
# components (C-C, C-O, C=O, O-C=O) on a linear background. Data are
# synthesised from the summed model and fitted back; area fractions come
# from integrating the fitted components. Always runs (skips fit if no lib).
import numpy as np
import matplotlib.pyplot as plt

DATA, FIT = "#3776ab", "#e07b39"
# C-C, C-O, C=O, O-C=O component colours.
COLORS = ["#3776ab", "#2a9d4a", "#e07b39", "#9467bd"]
LABELS = [r"C$-$C", r"C$-$O", r"C$=$O", r"O$-$C$=$O"]
PREFS = ["cc_", "co_", "cdo_", "ocdo_"]
CENTERS = [284.8, 286.3, 287.9, 289.0]        # chemical-shift positions (eV)
AMPS = [10000.0, 3000.0, 2000.0, 2500.0]      # ground-truth intensities

try:
    from lmfitxps.models import ConvGaussianDoniachSinglett
    from lmfit.models import LinearModel
    from lmfit import Parameters
    HAVE = True
except ImportError:
    HAVE = False

x = np.linspace(281.0, 293.0, 550)            # binding energy (eV)
rng = np.random.default_rng(0)
bg_intercept_true, bg_slope_true = 150.0, 8.0

if HAVE:
    # Build the summed truth model and evaluate it.
    model = None
    truth = Parameters()
    for pf, c, a in zip(PREFS, CENTERS, AMPS):
        pk = ConvGaussianDoniachSinglett(prefix=pf)
        model = pk if model is None else model + pk
        truth.add(pf + "amplitude", value=a)
        truth.add(pf + "sigma", value=0.30)
        truth.add(pf + "gamma", value=0.01)
        truth.add(pf + "gaussian_sigma", value=0.35)
        truth.add(pf + "center", value=c)
    bg_true = bg_intercept_true + bg_slope_true * (x - x[0])
    y = model.eval(truth, x=x) + bg_true + rng.normal(0.0, 30.0, x.size)
    source = "synthetic C 1s envelope, fitted with lmfitxps"
else:
    def _peak(e, amp, cen, w):
        return amp * w ** 2 / ((e - cen) ** 2 + w ** 2)
    bg_true = bg_intercept_true + bg_slope_true * (x - x[0])
    y = bg_true + rng.normal(0.0, 30.0, x.size)
    for c, a in zip(CENTERS, AMPS):
        y = y + _peak(x, a, c, 0.45)
    source = "synthetic C 1s envelope (pip install lmfitxps to fit)"

# --- fit: each centre pinned near its expected chemical shift ------------
if HAVE:
    full = None
    for pf in PREFS:
        m = ConvGaussianDoniachSinglett(prefix=pf)
        full = m if full is None else full + m
    full = full + LinearModel(prefix="bg_")
    p = full.make_params()
    for pf, c, a in zip(PREFS, CENTERS, AMPS):
        p[pf + "amplitude"].set(value=a * 0.8, min=0)
        p[pf + "sigma"].set(value=0.30, min=0.05, max=1.0)
        p[pf + "gamma"].set(value=0.01, min=0.0, max=0.2)
        p[pf + "gaussian_sigma"].set(value=0.35, min=0.10, max=1.0)
        p[pf + "center"].set(value=c, min=c - 0.5, max=c + 0.5)
    p["bg_intercept"].set(value=150.0)
    p["bg_slope"].set(value=8.0)
    result = full.fit(y, p, x=x)
    best = result.best_fit
    comps = result.eval_components(x=x)
    bg_curve = comps["bg_"]
    peaks = [comps[pf] for pf in PREFS]
    centers_fit = [result.params[pf + "center"].value for pf in PREFS]
else:
    best = y.copy()
    bg_curve = bg_true
    peaks = [np.clip(_peak(x, a, c, 0.45), 0, None)
             for c, a in zip(CENTERS, AMPS)]
    centers_fit = CENTERS

# Area fractions from integrating the fitted components.
areas = [float(np.trapz(pk, x)) for pk in peaks]
total_area = sum(areas) if sum(areas) else 1.0
fracs = [100.0 * ar / total_area for ar in areas]

# --- plot: data + total + filled components ------------------------------
fig, ax = plt.subplots(figsize=(6.4, 4.6))
ax.plot(x, y, ".", ms=3, color=DATA, alpha=0.45, label="data")
ax.plot(x, best, "-", color=FIT, lw=2, label="total fit")
ax.plot(x, bg_curve, "--", color="0.5", lw=1.1, label="background")
for pk, col, lab, cf, fr in zip(peaks, COLORS, LABELS, centers_fit, fracs):
    ax.fill_between(x, bg_curve, bg_curve + pk, color=col, alpha=0.30)
    ax.plot(x, bg_curve + pk, "-", color=col, lw=1.2,
            label="%s  %.0f%%" % (lab, fr))
ax.set_xlabel(r"binding energy  $E_B$  (eV)")
ax.set_ylabel("intensity (counts)")
ax.set_title(r"C $1s$ chemical-state fit")
ax.legend(loc="upper left", frameon=False, fontsize=8)
ax.invert_xaxis()                              # binding energy to the left
fig.text(0.01, 0.005, source, fontsize=7, color="0.45")
fig.tight_layout()
fig
'''


def _chemical():
    return [_md(_CHEM_INTRO), _code(_CHEM_FIT)]


# -- Registry --------------------------------------------------------------

XPS_FIT_EXAMPLES = [
    # (name, category, builder)
    ("Spin-Orbit Doublet (lmfitxps)", "XPS", _doublet),
    ("Shirley vs Tougaard (lmfitxps)", "XPS", _backgrounds),
    ("Chemical-State Fit (lmfitxps)", "XPS", _chemical),
]
