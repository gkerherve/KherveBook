"""ARPES curve-fitting examples using the ``peaks`` library.

A self-contained companion to ``examples.py`` (Examples menu,
"ARPES" category). ``peaks`` (``pip install peaks-arpes``) is the
angle-resolved photoemission toolkit from the King group at the
University of St Andrews; alongside the raw dispersion data it bundles
fitting models for the two everyday ARPES quantitative analyses:

* a **Fermi-edge fit** that extracts the Fermi level *E_F* and the
  experimental **energy resolution** from a gold reference spectrum, and
* an **energy-distribution-curve (EDC) fit** that resolves overlapping
  quasiparticle peaks into Lorentzian components on a background.

Each code cell uses the real ``peaks`` API when the library is installed
and otherwise synthesises faithful data with NumPy and fits it back with
``scipy.optimize.curve_fit`` so the example always runs offline.

This module defines its own ``_md``/``_code`` helpers and exports
``ARPES_FIT_EXAMPLES`` so it merges into ``examples.py`` without a
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


# -- 1. Fermi edge & resolution -------------------------------------------

_FERMI_INTRO = """\
# Fermi edge & energy resolution

A **gold reference** measured at the same photon energy and temperature as
the sample is the standard ARPES calibration. Gold is a simple metal, so
near the chemical potential its photoemission intensity is just a (nearly
linear) density of states multiplied by the **Fermi-Dirac** distribution.
The measured edge is that ideal step **broadened** by the spectrometer +
beamline, modelled as a Gaussian. Fitting it gives two numbers every
ARPES analysis needs: the **Fermi level** *E_F* (the energy zero) and the
**energy resolution** ΔE (the Gaussian FWHM).

With [`peaks`](https://github.com/phrgab/peaks) the bundled gold scan and
its dedicated fit are one call each:

```python
import peaks as pks
from peaks.core.utils.sample_data import ExampleData
gold = ExampleData.gold_reference()          # i05-59853.nxs
result = gold.fit_gold()                      # LinearDosFermiModel:
#   linear DOS x Gaussian-broadened Fermi function + constant background
EF  = result['fermi_center']                  # Fermi level (eV)
dE  = result['resolution']                    # energy resolution (eV FWHM)
```

Install it with `pip install peaks-arpes`. The cell below builds a gold
Fermi edge at a known temperature *T*, then fits it back with
`scipy.optimize.curve_fit` to recover *E_F* and the resolution ΔE. (As in
a real calibration *T* is held at the measured cryostat value, since the
thermal width and the resolution broaden the edge the same way and cannot
both be fitted from one curve.)
"""


_FERMI_FIT = r'''
# Fermi-edge fit: recover the Fermi level and the energy resolution from a
# gold reference. With peaks installed this is gold.fit_gold(); here we
# synthesise the edge and fit it back with scipy so it always runs.
import numpy as np
import matplotlib.pyplot as plt
from scipy.optimize import curve_fit
from scipy.ndimage import gaussian_filter1d

try:
    import peaks as pks                                      # noqa: F401
    from peaks.core.utils.sample_data import ExampleData
    gold = ExampleData.gold_reference()        # i05-59853.nxs
    res = gold.fit_gold()                       # LinearDosFermiModel
    E = np.asarray(gold["eV"].values, dtype=float)
    counts = np.asarray(gold.values, dtype=float).ravel()
    source = "peaks data - Diamond I05 gold reference (i05-59853.nxs)"
except Exception:
    source = "synthetic gold Fermi edge (pip install peaks-arpes)"
    rng = np.random.default_rng(0)
    kB = 8.617e-5                              # Boltzmann constant (eV/K)
    E = np.linspace(-0.30, 0.15, 400)          # E - E_F (eV)

    # --- true (ground-truth) parameters of the simulated edge -----------
    EF_true = 0.0                              # Fermi level (eV)
    T_true = 30.0                              # temperature (K)
    sigma_true = 0.02                          # resolution sigma (eV)
    dos_a, dos_b = -1.8, 1.0                   # linear DOS  a*E + b
    bg_true = 0.05                             # flat background

    def fermi_dirac(e, ef, kt):
        return 1.0 / (np.exp(np.clip((e - ef) / kt, -50, 50)) + 1.0)

    ideal = (dos_a * E + dos_b) * fermi_dirac(E, EF_true, kB * T_true)
    # Gaussian broadening (energy resolution) via gaussian_filter1d.
    dE_grid = E[1] - E[0]
    broadened = gaussian_filter1d(ideal, sigma_true / dE_grid)
    clean = broadened + bg_true
    counts = clean + rng.normal(0.0, 0.02, E.size)   # detector noise


# Model: linear DOS x Gaussian-broadened Fermi function + background.
# The temperature is the known cryostat reading (held fixed) - the way
# real Fermi-edge calibrations are done, since the thermal width and the
# resolution are otherwise degenerate. The fit recovers E_F and sigma.
kB = 8.617e-5                                  # eV/K
T_known = 30.0                                 # measurement temperature (K)


def fermi_edge(e, EF, sigma, a, b, bg):
    """Gold edge intensity: (a*e + b) * FD(e, EF, T_known) * Gauss(sigma)."""
    kt = kB * T_known
    ideal = (a * e + b) / (np.exp(np.clip((e - EF) / kt, -50, 50)) + 1.0)
    de = e[1] - e[0]
    return gaussian_filter1d(ideal, max(sigma, 1e-4) / de) + bg


# Initial guess near the expected values so curve_fit always converges.
p0 = [0.0, 0.02, -1.8, 1.0, 0.05]
try:
    popt, _ = curve_fit(fermi_edge, E, counts, p0=p0, maxfev=20000)
except Exception:
    popt = p0
EF_fit, sigma_fit, a_fit, b_fit, bg_fit = popt
sigma_fit = abs(sigma_fit)
dE_fwhm = 2.355 * sigma_fit                    # resolution FWHM

fit_curve = fermi_edge(E, *popt)

fig, ax = plt.subplots(figsize=(5.6, 4.2))
ax.plot(E, counts, ".", ms=3, color="#3776ab", alpha=0.6, label="data")
ax.plot(E, fit_curve, "-", color="#e07b39", lw=2, label="fit")
ax.axvline(EF_fit, color="0.4", ls="--", lw=1)
ax.set_xlabel(r"$E - E_F$ (eV)")
ax.set_ylabel("intensity")
ax.set_title("Gold Fermi-edge fit")
ax.legend(loc="upper right", frameon=False)
ax.text(0.03, 0.30,
        r"$E_F = %.1f$ meV" % (EF_fit * 1000.0) + "\n"
        + r"$T = %.0f$ K (fixed)" % T_known + "\n"
        + r"$\Delta E = %.1f$ meV (FWHM)" % (dE_fwhm * 1000.0),
        transform=ax.transAxes, va="top", fontsize=9,
        bbox=dict(boxstyle="round", fc="white", ec="0.8"))
fig.text(0.01, 0.005, source, fontsize=7, color="0.45")
fig.tight_layout()
fig
'''


def _fermi_edge():
    return [_md(_FERMI_INTRO), _code(_FERMI_FIT)]


# -- 2. EDC peak fitting --------------------------------------------------

_EDC_INTRO = """\
# EDC peak fitting

An **energy distribution curve (EDC)** is a vertical cut through an ARPES
map at fixed momentum: intensity versus binding energy. Quasiparticle
states show up as peaks whose **positions** give the band energies and
whose **widths** report the lifetime. When two bands sit close together
the peaks overlap, so the quantitative answer comes from a **fit**: a
smooth background plus one **Lorentzian** per state.

[`peaks`](https://github.com/phrgab/peaks) composes lmfit-style models and
fits them straight onto the data array:

```python
from peaks.core.fitting.models import (
    LorentzianModel, LinearModel, GaussianConvolvedFitModel)
model  = LinearModel() + LorentzianModel(prefix='p0_') \\
                       + LorentzianModel(prefix='p1_')
params = model.make_params()
result = edc.fit(model, params)
print(result['p0_center'], result['p1_center'])   # peak energies (eV)

# or, for a single peak, the one-liner:
edc.quick_fit.lorentzian(independent_var='eV')
```

Install it with `pip install peaks-arpes`. The cell below builds a
two-peak EDC and fits a linear background + two Lorentzians with
`scipy.optimize.curve_fit`, then reports both peak centres.
"""


_EDC_FIT = r'''
# EDC peak fit: resolve two overlapping quasiparticle peaks on a linear
# background. With peaks this is a composite LorentzianModel fit; here we
# synthesise the EDC and fit it back with scipy so it always runs.
import numpy as np
import matplotlib.pyplot as plt
from scipy.optimize import curve_fit

DATA, FIT = "#3776ab", "#e07b39"


def lorentzian(e, amp, cen, wid):
    """Area-normalised Lorentzian (HWHM = wid)."""
    return amp * (wid ** 2) / ((e - cen) ** 2 + wid ** 2)


def linear(e, m, c):
    return m * e + c


def edc_model(e, m, c, a0, x0, w0, a1, x1, w1):
    return (linear(e, m, c)
            + lorentzian(e, a0, x0, w0)
            + lorentzian(e, a1, x1, w1))


try:
    import peaks as pks                                      # noqa: F401
    from peaks.core.utils.sample_data import ExampleData
    from peaks.core.fitting.models import (                 # noqa: F401
        LorentzianModel, LinearModel, GaussianConvolvedFitModel)
    disp = ExampleData.dispersion()            # i05-59819.nxs
    edc_xr = disp.sel(theta_par=0, method="nearest")
    E = np.asarray(edc_xr["eV"].values, dtype=float)
    edc = np.asarray(edc_xr.values, dtype=float).ravel()
    source = "peaks data - Diamond I05 EDC (i05-59819.nxs)"
except Exception:
    source = "synthetic two-peak EDC (pip install peaks-arpes)"
    rng = np.random.default_rng(0)
    E = np.linspace(-0.55, 0.05, 350)          # E - E_F (eV)

    # --- true parameters: linear background + two Lorentzian peaks -------
    m_true, c_true = 0.6, 0.55                  # background slope/offset
    a0_true, x0_true, w0_true = 1.0, -0.35, 0.04
    a1_true, x1_true, w1_true = 0.7, -0.12, 0.03
    clean = edc_model(E, m_true, c_true,
                      a0_true, x0_true, w0_true,
                      a1_true, x1_true, w1_true)
    edc = clean + rng.normal(0.0, 0.03, E.size)


# Initial guess near the peaks so curve_fit always converges.
p0 = [0.6, 0.55, 1.0, -0.35, 0.04, 0.7, -0.12, 0.03]
try:
    popt, _ = curve_fit(edc_model, E, edc, p0=p0, maxfev=20000)
except Exception:
    popt = p0
m_f, c_f, a0_f, x0_f, w0_f, a1_f, x1_f, w1_f = popt

total = edc_model(E, *popt)
bg = linear(E, m_f, c_f)
peak0 = bg + lorentzian(E, a0_f, x0_f, w0_f)
peak1 = bg + lorentzian(E, a1_f, x1_f, w1_f)

fig, ax = plt.subplots(figsize=(5.8, 4.2))
ax.plot(E, edc, ".", ms=3, color=DATA, alpha=0.5, label="data")
ax.plot(E, total, "-", color=DATA, lw=2, label="total fit")
ax.plot(E, peak0, "--", color=FIT, lw=1.4, label="peak 1")
ax.plot(E, peak1, "--", color=FIT, lw=1.4, label="peak 2")
for xc in (x0_f, x1_f):
    ax.axvline(xc, color="0.6", ls=":", lw=0.9)
ax.set_xlabel(r"$E - E_F$ (eV)")
ax.set_ylabel("intensity")
ax.set_title("EDC two-peak Lorentzian fit")
ax.legend(loc="upper left", frameon=False, fontsize=8)
ax.text(0.97, 0.95,
        r"$E_1 = %.0f$ meV" % (x0_f * 1000.0) + "\n"
        + r"$E_2 = %.0f$ meV" % (x1_f * 1000.0),
        transform=ax.transAxes, va="top", ha="right", fontsize=9,
        bbox=dict(boxstyle="round", fc="white", ec="0.8"))
fig.text(0.01, 0.005, source, fontsize=7, color="0.45")
fig.tight_layout()
fig
'''


def _edc_fit():
    return [_md(_EDC_INTRO), _code(_EDC_FIT)]


# -- Registry --------------------------------------------------------------

ARPES_FIT_EXAMPLES = [
    # (name, category, builder)
    ("Fermi Edge & Resolution (peaks)", "ARPES", _fermi_edge),
    ("EDC Peak Fitting (peaks)", "ARPES", _edc_fit),
]
