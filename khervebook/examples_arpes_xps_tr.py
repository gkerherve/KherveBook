"""XPS core-level and time-resolved ARPES examples using ``peaks``.

A self-contained companion to ``examples.py`` (Examples menu,
"Spectroscopy" category) and a sibling of ``examples_arpes.py``.
``peaks`` (``pip install peaks-arpes``) is the angle-resolved
photoemission / photoelectron-spectroscopy toolkit from the King group
at the University of St Andrews
([arXiv:2508.04803](https://arxiv.org/abs/2508.04803)). Besides ARPES
dispersions it ships an X-ray photoelectron-spectroscopy (XPS) survey
through ``ExampleData.xps()`` and a time-resolved ARPES pump-probe scan
on graphene through ``ExampleData.tr_arpes()``.

Each code cell loads the real ``peaks`` dataset when the library is
installed and otherwise synthesises a faithful spectrum / map with NumPy
so the example always runs offline. The XPS cell builds a spin-orbit
doublet on an inelastic background, computes an iterative Shirley
background and subtracts it. The TR-ARPES cell builds a transient
population above the Fermi level that turns on at ``t0`` and decays
exponentially, then fits the decay constant.

This module defines its own ``_md``/``_code`` helpers and exports
``ARPES_XPS_TR_EXAMPLES`` so it merges into ``examples.py`` without a
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


# -- 1. XPS core levels ----------------------------------------------------

_XPS_INTRO = """\
# XPS core levels with the `peaks` library

**X-ray photoelectron spectroscopy (XPS)** probes the *core* levels of a
solid: a soft-X-ray photon (Al K-alpha, 1486.6 eV, or a synchrotron) ejects
a core electron, and the kinetic energy spectrum maps to **binding energy**
(BE = h-nu - KE - phi). Each element has a fingerprint set of core lines, so
XPS is the workhorse for surface chemical analysis.

Two features dominate a core-level region:

- **Spin-orbit doublets.** A level with orbital momentum *l > 0* splits into
  *j = l +/- 1/2*. For a *p* level (e.g. Ti `2p`) this gives `2p3/2` and
  `2p1/2` with a fixed splitting and a **2:1** area ratio (degeneracy
  *2j+1*); *d* levels give 3:2, *f* levels 4:3.
- **Inelastic background.** Electrons that scatter on the way out pile up on
  the high-BE side of every peak. The standard correction is a **Shirley
  background**, where the background under a point is proportional to the
  total peak area at *lower* binding energy (higher kinetic energy).

[`peaks`](https://github.com/phrgab/peaks) ships an XPS survey and helpers
to identify which lines fall in a given window:

```python
import peaks as pks
from peaks.core.utils.sample_data import ExampleData
spectrum = ExampleData.xps().DOS()     # XPS survey, intensity vs BE
spectrum.plot()

from peaks import xps
xps.CoreLevels.by_element(['Ti', 'Se'], hv=200)   # lines for TiSe2 at hv=200 eV
xps.CoreLevels.plot(['Ti', 'Se'], ax=ax, hv=200)  # overlay markers on a spectrum
```

Install it with `pip install peaks-arpes`. The cell below uses that real
survey when `peaks` is available, and always synthesises a Ti `2p`
spin-orbit doublet so it can demonstrate a full **Shirley background**
subtraction offline. Note the XPS convention: **binding energy increases to
the left**.
"""


_XPS_CODE = r'''
# XPS Ti 2p core-level region: a spin-orbit doublet on an inelastic
# background, with an iterative Shirley background subtraction.
#
# peaks ships an XPS survey via ExampleData.xps().DOS(); we plot it as a
# reference when available, but the doublet + Shirley analysis below is
# fully synthetic so the cell always runs offline.
import numpy as np
import matplotlib.pyplot as plt


def voigt_peak(x, x0, amp, sigma, gamma):
    """Pseudo-Voigt: linear mix of a Gaussian and a Lorentzian."""
    g = np.exp(-0.5 * ((x - x0) / sigma) ** 2)
    l = 1.0 / (1.0 + ((x - x0) / gamma) ** 2)
    return amp * (0.7 * g + 0.3 * l)


def shirley_background(be, y, n_iter=12):
    """Iterative Shirley background on a BE axis (low index = low BE).

    B(E) rises toward HIGHER binding energy in proportion to the peak
    area at lower BE. We sort to increasing BE, integrate the
    background-subtracted signal cumulatively, and iterate. Bounded loop,
    never raises.
    """
    order = np.argsort(be)
    e = np.asarray(be, dtype=float)[order]
    s = np.asarray(y, dtype=float)[order]
    i_lo, i_hi = s[0], s[-1]                 # endpoint intensities
    bg = np.linspace(i_lo, i_hi, e.size)     # straight-line seed
    for _ in range(int(np.clip(n_iter, 8, 20))):
        diff = np.clip(s - bg, 0.0, None)
        csum = np.cumsum(diff)               # area at lower BE
        total = csum[-1]
        if total <= 0:
            break
        bg = i_lo + (i_hi - i_lo) * csum / total
    out = np.empty_like(bg)
    out[order] = bg                          # restore caller's ordering
    return out


# Optional: show the real peaks XPS survey alongside, if installed.
survey = None
try:
    import peaks as pks                                       # noqa: F401
    from peaks.core.utils.sample_data import ExampleData
    spec = ExampleData.xps().DOS()
    sx = np.asarray(spec["eV"].values, dtype=float)
    try:
        sy = np.asarray(spec.pint.magnitude, dtype=float)
    except Exception:
        sy = np.asarray(spec.values, dtype=float)
    survey = (sx, sy, "peaks XPS survey (ExampleData.xps())")
except Exception:
    survey = None

# Synthetic Ti 2p region on a binding-energy axis (eV).
BE = np.linspace(450.0, 470.0, 600)
be32, be12 = 458.5, 464.2                # 2p3/2 and 2p1/2 positions
doublet = (voigt_peak(BE, be32, 2.0, 0.55, 0.55)       # 2p3/2
           + voigt_peak(BE, be12, 1.0, 0.65, 0.65))    # 2p1/2 (2:1 area)

# Inelastic background that rises toward higher BE (step under each peak).
from math import erf as _erf
bg_true = 0.15 + 0.55 * 0.5 * (1.0 + np.vectorize(_erf)((BE - be32) / 2.5))
rng = np.random.default_rng(7)
raw = doublet + bg_true + 0.01 * rng.standard_normal(BE.size)

# Iterative Shirley background and the subtracted doublet.
shirley = shirley_background(BE, raw, n_iter=12)
sub = raw - shirley

fig, ax = plt.subplots(figsize=(6.2, 4.4))
ax.plot(BE, raw, color="#3776ab", lw=1.3, label="raw spectrum")
ax.plot(BE, shirley, color="#888888", lw=1.2, ls="--", label="Shirley background")
ax.plot(BE, sub, color="#e07b39", lw=1.4, label="background subtracted")
ax.fill_between(BE, sub, 0, color="#e07b39", alpha=0.12)

# Annotate the two spin-orbit components on the subtracted doublet.
for x0, lbl in ((be32, r"$2p_{3/2}$"), (be12, r"$2p_{1/2}$")):
    yk = sub[int(np.argmin(np.abs(BE - x0)))]
    ax.annotate(lbl, xy=(x0, yk), xytext=(x0, yk + 0.35),
                ha="center", fontsize=11,
                arrowprops=dict(arrowstyle="->", color="0.3", lw=0.9))

ax.set_xlabel("binding energy (eV)")
ax.set_ylabel("intensity (arb.)")
ax.set_title(r"XPS Ti $2p$ doublet + Shirley background")
ax.invert_xaxis()                       # XPS: BE increases to the LEFT
ax.legend(loc="upper left", fontsize=8, framealpha=0.9)
note = survey[2] if survey else "synthetic Ti 2p (pip install peaks-arpes)"
fig.text(0.01, 0.005, note, fontsize=7, color="0.45")
fig.tight_layout()
fig
'''


def _xps_core_levels():
    return [_md(_XPS_INTRO), _code(_XPS_CODE)]


# -- 2. Time-resolved ARPES ------------------------------------------------

_TR_INTRO = """\
# Time-resolved ARPES with the `peaks` library

**Time-resolved ARPES (TR-ARPES)** adds a femtosecond *pump-probe* delay axis
to a normal ARPES measurement. A pump pulse excites the electrons out of
equilibrium; a delayed probe pulse takes an ARPES snapshot. Scanning the
**pump-probe delay** films the electrons relaxing back, so TR-ARPES is *the*
way to watch transient populations and hot-carrier dynamics in the time
domain.

The signature observable is **population above the Fermi level**. In
equilibrium those states are empty (Fermi-Dirac cut-off at *E_F*); the pump
transiently fills them, the excess turns on sharply at the pump-probe overlap
*t0*, and then **decays exponentially** with a characteristic time *tau* set
by electron-phonon / electron-electron scattering.

[`peaks`](https://github.com/phrgab/peaks) ships a real TR-ARPES dataset:

```python
import peaks as pks
from peaks.core.utils.sample_data import ExampleData
tr = ExampleData.tr_arpes()    # '029 Gr.zip', TR-ARPES on graphene
tr.plot()                      # has energy, angle and a delay dimension
```

Install it with `pip install peaks-arpes`. The cell below uses that real scan
when `peaks` is available, and otherwise synthesises a transient population
above *E_F* that turns on at *t0* (error-function) and decays with
*tau ~ 0.5 ps*. It then shows the difference map *I(t) - I(t<0)* and fits the
integrated population above *E_F* to an exponential decay.
"""


_TR_CODE = r'''
# TR-ARPES transient population above E_F: a 2D (energy, delay) map and an
# exponential-decay fit of the integrated above-E_F population.
#
# peaks ships a real graphene TR-ARPES scan via ExampleData.tr_arpes();
# we use it when present, otherwise synthesise the pump-probe response so
# the cell always runs offline.
import numpy as np
import matplotlib.pyplot as plt
from scipy.optimize import curve_fit
from scipy.special import erf


def load_tr_arpes():
    """Return (E_minus_EF, delay_ps, I[E, delay], source).

    I is an energy-vs-delay map; the synthetic fallback models a
    base Fermi-Dirac edge plus a pump-induced population above E_F that
    turns on at t0 and decays exponentially.
    """
    try:
        import peaks as pks                                   # noqa: F401
        from peaks.core.utils.sample_data import ExampleData
        d = ExampleData.tr_arpes()         # '029 Gr.zip' graphene scan
        try:
            arr = np.asarray(d.pint.magnitude, dtype=float)
        except Exception:
            arr = np.asarray(d.values, dtype=float)
        e_ax = np.asarray(d["eV"].values, dtype=float)
        # Find the delay coordinate by name, collapse any angle axis.
        dname = next((c for c in getattr(d, "dims", [])
                      if "delay" in str(c).lower() or str(c).lower()
                      in ("t", "time")), None)
        t_ax = np.asarray(d[dname].values, dtype=float)
        ax_e = list(d.dims).index("eV")
        ax_t = list(d.dims).index(dname)
        other = [i for i in range(arr.ndim) if i not in (ax_e, ax_t)]
        if other:
            arr = arr.mean(axis=tuple(other))
            ax_e = 0 if ax_e < ax_t else 1
            ax_t = 1 - ax_e
        m = np.moveaxis(arr, (ax_e, ax_t), (0, 1))
        return e_ax, t_ax, m, "peaks TR-ARPES (ExampleData.tr_arpes(), graphene)"
    except Exception:
        E = np.linspace(-0.4, 0.4, 240)            # E - E_F (eV)
        t = np.linspace(-1.0, 3.0, 200)            # pump-probe delay (ps)
        EE, TT = np.meshgrid(E, t, indexing="ij")
        kT = 0.025                                  # base electronic temperature
        base = 1.0 / (np.exp(EE / kT) + 1.0)        # equilibrium Fermi-Dirac
        t0, tau, sigma = 0.0, 0.5, 0.12             # turn-on, decay, IRF width
        turn_on = 0.5 * (1.0 + erf((TT - t0) / (np.sqrt(2.0) * sigma)))
        decay = np.exp(-np.clip(TT - t0, 0.0, None) / tau)
        excited = np.exp(-np.clip(EE, 0.0, None) / 0.08)   # above-E_F weight
        transient = 0.8 * excited * turn_on * decay
        rng = np.random.default_rng(3)
        inten = base + transient + 0.01 * rng.standard_normal(EE.shape)
        return E, t, inten, "synthetic TR-ARPES (pip install peaks-arpes)"


def expdecay(t, A, tau, c):
    return A * np.exp(-np.clip(t, 0.0, None) / tau) + c


E, t, I, source = load_tr_arpes()

# Difference map I(t) - I(t<0): subtract the mean of the pre-t0 frames.
pre = t < (t.min() + 0.2 * (t.max() - t.min()))
I0 = I[:, pre].mean(axis=1, keepdims=True) if pre.any() else I[:, :1]
diff = I - I0

# Integrated population above E_F (sum over E > 0) vs delay.
above = E > 0
pop = diff[above].sum(axis=0)
pop = pop / (np.max(np.abs(pop)) + 1e-12)

# Exponential-decay fit; fall back to guess params if curve_fit fails.
t_fit = t[t >= 0]
p_fit = pop[t >= 0]
p0 = [float(np.max(p_fit)) if p_fit.size else 1.0, 0.5, 0.0]
try:
    popt, _ = curve_fit(expdecay, t_fit, p_fit, p0=p0, maxfev=8000)
except Exception:
    popt = p0
tau_fit = float(popt[1])

vmax = float(np.max(np.abs(diff)))
fig, (a1, a2) = plt.subplots(1, 2, figsize=(8.2, 3.7))

pm = a1.pcolormesh(t, E, diff, cmap="RdBu_r", shading="auto",
                   vmin=-vmax, vmax=vmax)
a1.axhline(0, color="k", ls="--", lw=0.8, alpha=0.7)        # E_F
a1.set_xlabel("delay (ps)")
a1.set_ylabel(r"$E - E_F$ (eV)")
a1.set_title(r"difference map $I(t) - I(t<0)$")
fig.colorbar(pm, ax=a1, label=r"$\Delta$ intensity (arb.)")

a2.plot(t, pop, ".", ms=3, color="#3776ab", label="above $E_F$")
tt = np.linspace(max(0.0, t.min()), t.max(), 300)
a2.plot(tt, expdecay(tt, *popt), color="#e07b39", lw=1.6,
        label=r"fit $\tau = %.2f$ ps" % tau_fit)
a2.axvline(0, color="0.6", ls=":", lw=1)
a2.set_xlabel("delay (ps)")
a2.set_ylabel(r"population above $E_F$ (norm.)")
a2.set_title(r"transient decay, $\tau \approx %.2f$ ps" % tau_fit)
a2.legend(loc="upper right", fontsize=8)

fig.text(0.01, 0.005, source, fontsize=7, color="0.45")
fig.tight_layout()
fig
'''


def _tr_arpes():
    return [_md(_TR_INTRO), _code(_TR_CODE)]


# -- Registry --------------------------------------------------------------

ARPES_XPS_TR_EXAMPLES = [
    # (name, category, builder)
    ("XPS Core Levels (peaks)", "Spectroscopy", _xps_core_levels),
    ("TR-ARPES (peaks)", "Spectroscopy", _tr_arpes),
]
