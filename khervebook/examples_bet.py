"""BET / gas-adsorption examples using synthetic isotherm data.

A self-contained companion to ``examples.py`` (Examples menu, "BET"
category). Gas physisorption is the workhorse for **surface area** and
**porosity** of powders and porous solids: a nitrogen isotherm at 77 K
(quantity adsorbed versus relative pressure *P/P0*) is reduced through
the classic textbook analyses --- **BET** surface area, the **Langmuir**
monolayer model, **BJH** pore-size distribution and the **t-plot** for
micropores.

The de-facto open-source toolkit for this is
[`pyGAPS`](https://github.com/pauliacomi/pyGAPS) (Iacomi & Llewellyn),
whose API is referenced in the markdown of each example, e.g.::

    import pygaps
    import pygaps.characterisation as pgc
    area = pgc.area_BET(isotherm)            # BET surface area
    lang = pgc.area_langmuir(isotherm)       # Langmuir surface area
    psd  = pgc.psd_mesoporous(isotherm)      # BJH pore-size distribution
    tpl  = pgc.t_plot(isotherm)              # t-plot micropore analysis

The data here are **synthetic** (faithful type-IV / type-I shapes built
with NumPy and a fixed seed) so every example runs offline without
pyGAPS installed, while the reductions use the same equations pyGAPS
applies to real measurements.

This module defines its own ``_md``/``_code`` helpers and exports
``BET_EXAMPLES`` so it merges into ``examples.py`` without a circular
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


# -- 1. N2 adsorption isotherm --------------------------------------------

_ISOTHERM_INTRO = """\
# N2 adsorption isotherm at 77 K

A **physisorption isotherm** records the quantity of gas a solid takes
up as a function of **relative pressure** *P/P0* at constant temperature
--- for nitrogen the standard is **77 K** (liquid-N2 boiling point). A
**type-IV** isotherm (IUPAC) is the signature of a **mesoporous**
material: a low-pressure knee where the first monolayer forms, a gentle
rise as further layers build up, and a steep step near *P/P0* ~ 0.4-0.8
from **capillary condensation** inside the pores. On the way back down
the desorption branch lags the adsorption branch, leaving a **hysteresis
loop** whose shape encodes the pore geometry.

With [`pyGAPS`](https://github.com/pauliacomi/pyGAPS) a measured
isotherm is a first-class object you can plot and analyse:

```python
import pygaps
isotherm = pygaps.PointIsotherm(
    pressure=p_rel, loading=quantity,
    material='sample', adsorbate='N2', temperature=77)
isotherm.plot()                      # both branches with hysteresis
```

Install it with `pip install pygaps`. The cell below synthesises a
faithful type-IV N2 isotherm --- adsorption and desorption branches with
a realistic hysteresis loop --- so the example always runs offline.
"""


_ISOTHERM = r'''
# Synthetic type-IV N2 isotherm at 77 K with an adsorption branch and a
# desorption branch (capillary-condensation hysteresis). With pyGAPS a
# real isotherm would be a PointIsotherm object; here we build both
# branches with NumPy so the example always runs.
import numpy as np
import matplotlib.pyplot as plt

rng = np.random.default_rng(0)

ADS, DES, ACC = "#3776ab", "#e07b39", "#50bea0"

# Relative-pressure grid P/P0 from ~0 to ~1.
p = np.linspace(0.001, 0.995, 240)


def bet_loading(pr, Wm, c):
    """BET multilayer quantity adsorbed (cm^3/g STP) vs relative pressure."""
    return Wm * c * pr / ((1.0 - pr) * (1.0 + (c - 1.0) * pr))


# Monolayer capacity (cm^3/g STP) and BET constant for the base multilayer.
Wm_true, c_true = 95.0, 120.0
base = bet_loading(p, Wm_true, c_true)

# Capillary condensation: a smooth step centred at p_c on the way up.
p_c_ads, width = 0.62, 0.05
step = 150.0 / (1.0 + np.exp(-(p - p_c_ads) / width))
ads = base + step
ads += rng.normal(0.0, 0.6, p.size)            # measurement noise

# Desorption branch retraces at lower pressure -> H1 hysteresis loop.
p_c_des = 0.50                                  # emptying lags filling
step_des = 150.0 / (1.0 + np.exp(-(p - p_c_des) / width))
des = base + step_des
des += rng.normal(0.0, 0.6, p.size)
des = np.maximum(des, ads)                      # desorption sits above ads

fig, ax = plt.subplots(figsize=(5.8, 4.4))
ax.plot(p, ads, "-o", ms=2.5, color=ADS, label="adsorption")
ax.plot(p, des, "-s", ms=2.5, color=DES, mfc="none", label="desorption")
ax.fill_between(p, ads, des, color=ACC, alpha=0.18)
ax.axvspan(0.05, 0.30, color="0.85", alpha=0.4)   # BET linear region
ax.set_xlabel(r"relative pressure  $P/P_0$")
ax.set_ylabel(r"quantity adsorbed (cm$^3$/g STP)")
ax.set_title("Type-IV N$_2$ isotherm at 77 K")
ax.legend(loc="upper left", frameon=False)
ax.text(0.97, 0.05, "hysteresis loop", transform=ax.transAxes,
        ha="right", va="bottom", fontsize=8, color="0.4")
fig.tight_layout()
fig
'''


def _n2_isotherm():
    return [_md(_ISOTHERM_INTRO), _code(_ISOTHERM)]


# -- 2. BET surface area --------------------------------------------------

_BET_INTRO = """\
# BET specific surface area

The **Brunauer-Emmett-Teller (BET)** method turns an N2 isotherm into a
**specific surface area**. Its transform

$$\\frac{1}{W\\,(P_0/P - 1)} = \\frac{1}{W_m c} + \\frac{c-1}{W_m c}\\,
\\frac{P}{P_0}$$

is **linear** in *P/P0* over the restricted range *P/P0* ~ 0.05-0.30. A
straight-line fit gives a **slope** and **intercept**; together they
yield the **monolayer capacity** *Wm* = 1 / (slope + intercept). The
specific surface area then follows from how much area one monolayer of
molecules covers:

$$S = \\frac{W_m}{M}\\,N_A\\,\\sigma,\\qquad \\sigma_{N_2}=0.162~\\mathrm{nm}^2$$

with *N_A* = 6.022e23 the Avogadro constant and sigma the N2
cross-sectional area.

With [`pyGAPS`](https://github.com/pauliacomi/pyGAPS) this is a single
call that even picks the valid linear range for you:

```python
import pygaps.characterisation as pgc
result = pgc.area_BET(isotherm)
print(result['area'])                # BET area in m^2/g
```

Install it with `pip install pygaps`. The cell below builds the BET plot,
fits the linear region, and reports the surface area in m^2/g.
"""


_BET = r'''
# BET surface area: the transform 1/[W*(P0/P - 1)] is linear in P/P0 over
# ~0.05-0.30. Fit it, get the monolayer capacity Wm from slope+intercept,
# then S = (Wm/M)*N_A*sigma. With pyGAPS this is pgc.area_BET(isotherm);
# here we synthesise an isotherm and reduce it so it always runs.
import numpy as np
import matplotlib.pyplot as plt

rng = np.random.default_rng(0)

DATA, FIT = "#3776ab", "#e07b39"

# Physical constants and N2 parameters.
N_A = 6.022e23                  # Avogadro constant (1/mol)
sigma = 0.162e-18              # N2 cross-section (m^2 per molecule)
V_molar = 22414.0             # molar volume at STP (cm^3/mol)

# Synthetic isotherm: quantity adsorbed W (cm^3/g STP) vs P/P0.
p = np.linspace(0.02, 0.45, 120)
Wm_true, c_true = 95.0, 120.0


def bet_loading(pr, Wm, c):
    return Wm * c * pr / ((1.0 - pr) * (1.0 + (c - 1.0) * pr))


W = bet_loading(p, Wm_true, c_true)
W += rng.normal(0.0, 0.4, p.size)

# BET transform y = 1 / [W * (P0/P - 1)] = 1 / [W * (1/p - 1)].
y = 1.0 / (W * (1.0 / p - 1.0))

# Restrict to the standard BET linear region 0.05 <= P/P0 <= 0.30.
mask = (p >= 0.05) & (p <= 0.30)
px, py = p[mask], y[mask]

try:
    slope, intercept = np.polyfit(px, py, 1)
except Exception:
    slope, intercept = 1.0 / Wm_true, 0.0

# Monolayer capacity and BET constant from slope + intercept.
Wm = 1.0 / (slope + intercept)            # cm^3/g STP
c_bet = 1.0 + slope / intercept if intercept else float("nan")

# Specific surface area S = (Wm / V_molar) * N_A * sigma  [m^2/g].
# Wm/V_molar is mol of monolayer gas per gram of solid.
S_bet = (Wm / V_molar) * N_A * sigma

fit_line = slope * px + intercept

fig, ax = plt.subplots(figsize=(5.8, 4.3))
ax.plot(p, y, ".", ms=4, color="0.7", label="all points")
ax.plot(px, py, "o", ms=5, color=DATA, label="BET region (0.05-0.30)")
ax.plot(px, fit_line, "-", color=FIT, lw=2, label="linear fit")
ax.set_xlabel(r"relative pressure  $P/P_0$")
ax.set_ylabel(r"$1/[\,W\,(P_0/P - 1)\,]$")
ax.set_title("BET plot")
ax.legend(loc="upper left", frameon=False, fontsize=8)
ax.text(0.97, 0.05,
        r"$W_m = %.1f$ cm$^3$/g" % Wm + "\n"
        + r"$S_{BET} = %.0f$ m$^2$/g" % S_bet,
        transform=ax.transAxes, ha="right", va="bottom", fontsize=9,
        bbox=dict(boxstyle="round", fc="white", ec="0.8"))
fig.tight_layout()
fig
'''


def _bet_area():
    return [_md(_BET_INTRO), _code(_BET)]


# -- 3. Langmuir isotherm -------------------------------------------------

_LANGMUIR_INTRO = """\
# Langmuir isotherm

The **Langmuir model** is the simplest adsorption isotherm: a single
**monolayer** on a uniform surface with no adsorbate-adsorbate
interaction. It describes **type-I** (microporous) uptake well. In its
loading form,

$$n = \\frac{n_m\\,K\\,P}{1 + K\\,P},$$

with *n_m* the **monolayer capacity** and *K* the affinity constant.
Rearranged it is **linear**,

$$\\frac{P}{n} = \\frac{1}{n_m K} + \\frac{P}{n_m},$$

so a plot of *P/n* versus *P* has slope 1/*n_m* and intercept
1/(*n_m K*).

With [`pyGAPS`](https://github.com/pauliacomi/pyGAPS) the Langmuir
surface area is one call:

```python
import pygaps.characterisation as pgc
result = pgc.area_langmuir(isotherm)
print(result['area'], result['langmuir_const'])
```

Install it with `pip install pygaps`. The cell below fits the linear
*P/n*-versus-*P* form and reports the monolayer capacity.
"""


_LANGMUIR = r'''
# Langmuir isotherm fit (monolayer): n = nm*K*P/(1+K*P). The linear form
# P/n = 1/(nm*K) + P/nm gives nm from the slope. With pyGAPS this is
# pgc.area_langmuir(isotherm); here we synthesise type-I data and fit it
# back so it always runs.
import numpy as np
import matplotlib.pyplot as plt

rng = np.random.default_rng(0)

DATA, FIT, ACC = "#3776ab", "#e07b39", "#50bea0"

# Synthetic type-I (microporous) isotherm.
p = np.linspace(0.01, 0.95, 120)         # relative pressure P/P0
nm_true, K_true = 140.0, 35.0            # capacity (cm^3/g), affinity


def langmuir(pr, nm, K):
    return nm * K * pr / (1.0 + K * pr)


n = langmuir(p, nm_true, K_true)
n += rng.normal(0.0, 1.2, p.size)
n = np.clip(n, 1e-3, None)

# Linear form: P/n vs P -> slope = 1/nm, intercept = 1/(nm*K).
y = p / n
try:
    slope, intercept = np.polyfit(p, y, 1)
except Exception:
    slope, intercept = 1.0 / nm_true, 1.0 / (nm_true * K_true)

nm = 1.0 / slope                         # monolayer capacity (cm^3/g STP)
K_fit = slope / intercept if intercept else float("nan")

fit_line = slope * p + intercept
n_fit = langmuir(p, nm, K_fit)

fig, (a1, a2) = plt.subplots(1, 2, figsize=(8.2, 3.8))

a1.plot(p, n, ".", ms=4, color=DATA, alpha=0.6, label="data")
a1.plot(p, n_fit, "-", color=FIT, lw=2, label="Langmuir fit")
a1.axhline(nm, color=ACC, ls="--", lw=1)
a1.set_xlabel(r"relative pressure  $P/P_0$")
a1.set_ylabel(r"quantity adsorbed (cm$^3$/g STP)")
a1.set_title("Langmuir isotherm")
a1.legend(loc="lower right", frameon=False, fontsize=8)

a2.plot(p, y, ".", ms=4, color=DATA, alpha=0.6, label="data")
a2.plot(p, fit_line, "-", color=FIT, lw=2, label="linear fit")
a2.set_xlabel(r"relative pressure  $P/P_0$")
a2.set_ylabel(r"$P/n$")
a2.set_title("Langmuir linear form")
a2.text(0.97, 0.05,
        r"$n_m = %.0f$ cm$^3$/g" % nm + "\n"
        + r"$K = %.1f$" % K_fit,
        transform=a2.transAxes, ha="right", va="bottom", fontsize=9,
        bbox=dict(boxstyle="round", fc="white", ec="0.8"))
a2.legend(loc="upper left", frameon=False, fontsize=8)
fig.tight_layout()
fig
'''


def _langmuir():
    return [_md(_LANGMUIR_INTRO), _code(_LANGMUIR)]


# -- 4. BJH pore-size distribution ----------------------------------------

_BJH_INTRO = """\
# BJH pore-size distribution

The **Barrett-Joyner-Halenda (BJH)** method converts the **desorption**
branch of a mesopore isotherm into a **pore-size distribution**. Its
physical core is the **Kelvin equation**: vapour condenses (or
evaporates) inside a pore at a relative pressure set by the pore radius,

$$\\ln\\!\\frac{P}{P_0} = -\\frac{2\\gamma V_m}{r_K R T}\\cos\\theta,$$

so each pressure step on the branch maps to a **pore diameter**, and the
volume desorbed over that step gives the pore volume in that size bin.
The result is usually plotted as **dV/d(log D)** versus pore diameter;
the peak marks the **dominant pore size**.

With [`pyGAPS`](https://github.com/pauliacomi/pyGAPS) the BJH analysis is
one call:

```python
import pygaps.characterisation as pgc
result = pgc.psd_mesoporous(isotherm, psd_model='BJH', branch='des')
# result['pore_widths'], result['pore_distribution']  ->  dV/dlogD
```

Install it with `pip install pygaps`. The cell below synthesises a BJH
distribution from a Kelvin-equation idea and annotates the dominant pore
size in nm.
"""


_BJH = r'''
# BJH pore-size distribution from the desorption branch (Kelvin-equation
# idea): each P/P0 maps to a pore diameter, the volume change gives the
# bin volume, plotted as dV/d(logD). With pyGAPS this is
# pgc.psd_mesoporous(isotherm, psd_model='BJH'); here we synthesise the
# distribution so it always runs.
import numpy as np
import matplotlib.pyplot as plt

rng = np.random.default_rng(0)

DATA, ACC = "#3776ab", "#50bea0"

# Pore-diameter axis (nm), log-spaced as in a real PSD.
D = np.logspace(np.log10(1.5), np.log10(60.0), 200)   # nm
logD = np.log10(D)


def lognormal_peak(d, center, sigma, amp):
    """A log-normal mode in pore diameter -> dV/d(logD)."""
    return amp * np.exp(-0.5 * ((np.log10(d) - np.log10(center)) / sigma) ** 2)

# Two mesopore populations: a dominant ~6 nm mode and a broad ~20 nm mode.
dvdlogd = (lognormal_peak(D, 6.0, 0.12, 0.85)
           + lognormal_peak(D, 22.0, 0.22, 0.30))
dvdlogd += rng.normal(0.0, 0.01, D.size)
dvdlogd = np.clip(dvdlogd, 0.0, None)

# Dominant pore size = position of the maximum of the distribution.
i_peak = int(np.argmax(dvdlogd))
d_peak = D[i_peak]

# Cumulative pore volume (integral of dV/dlogD over logD) for context.
cum = np.cumsum(dvdlogd * np.gradient(logD))

fig, ax = plt.subplots(figsize=(5.9, 4.3))
ax.plot(D, dvdlogd, "-", color=DATA, lw=2, label=r"$dV/d(\log D)$")
ax.fill_between(D, dvdlogd, color=DATA, alpha=0.12)
ax.axvline(d_peak, color=ACC, ls="--", lw=1.4)
ax.set_xscale("log")
ax.set_xlabel(r"pore diameter (nm)")
ax.set_ylabel(r"$dV/d(\log D)$  (cm$^3$/g)")
ax.set_title("BJH pore-size distribution")
ax.legend(loc="upper right", frameon=False, fontsize=8)
ax.text(0.03, 0.95,
        r"dominant pore $\approx %.1f$ nm" % d_peak,
        transform=ax.transAxes, va="top", fontsize=9,
        bbox=dict(boxstyle="round", fc="white", ec="0.8"))
fig.tight_layout()
fig
'''


def _bjh():
    return [_md(_BJH_INTRO), _code(_BJH)]


# -- 5. t-plot micropore analysis -----------------------------------------

_TPLOT_INTRO = """\
# t-plot micropore analysis

The **t-plot** (de Boer) separates **micropore** filling from
**multilayer** adsorption on the external surface. Instead of plotting
the quantity adsorbed against *P/P0*, it is plotted against the
**statistical thickness** *t* of the adsorbed film --- the average number
of molecular layers expressed in nm --- via a reference equation such as
**Harkins-Jura**:

$$t(P/P_0) = \\left[\\frac{13.99}{0.034 - \\log_{10}(P/P_0)}\\right]^{1/2}
~\\mathrm{nm}.$$

On a non-microporous solid the plot is a straight line through the
origin. **Micropores** fill at low *t* and add an extra uptake, so the
high-*t* linear region has a positive **intercept** --- proportional to
the **micropore volume** --- while its **slope** gives the **external
surface area**.

With [`pyGAPS`](https://github.com/pauliacomi/pyGAPS) the t-plot is one
call:

```python
import pygaps.characterisation as pgc
result = pgc.t_plot(isotherm, thickness_model='Harkins/Jura')
print(result['results'])     # micropore volume + external area per region
```

Install it with `pip install pygaps`. The cell below builds the t-plot,
fits its high-*t* linear region, and annotates the micropore volume and
external surface area.
"""


_TPLOT = r'''
# t-plot micropore analysis: quantity adsorbed vs statistical thickness t
# (Harkins-Jura). The high-t linear region's intercept gives the
# micropore volume and its slope the external surface area. With pyGAPS
# this is pgc.t_plot(isotherm); here we synthesise the data so it always
# runs.
import numpy as np
import matplotlib.pyplot as plt

rng = np.random.default_rng(0)

DATA, FIT, ACC = "#3776ab", "#e07b39", "#50bea0"

N_A = 6.022e23                 # Avogadro constant (1/mol)
V_molar = 22414.0            # molar volume at STP (cm^3/mol)
# Liquid-N2 conversion: 1 cm^3 STP of N2 -> liquid volume (cm^3).
liq_factor = 0.0015468       # cm^3 liquid per cm^3 STP


def harkins_jura(pr):
    """Statistical thickness t (nm) from relative pressure (Harkins-Jura)."""
    return np.sqrt(13.99 / (0.034 - np.log10(pr)))


# Relative-pressure grid and its statistical thickness.
p = np.linspace(0.05, 0.80, 140)
t = harkins_jura(p)                       # nm

# Synthetic micropore + external-surface uptake:
#   micropore fills fast at low t (saturating), then a linear multilayer
#   build-up on the external surface vs t.
ext_slope_true = 22.0                     # cm^3/g per nm (external area)
micro_plateau = 60.0                      # micropore uptake plateau
Q = (micro_plateau * (1.0 - np.exp(-t / 0.18))
     + ext_slope_true * t)
Q += rng.normal(0.0, 0.6, p.size)

# Fit the high-t linear region (t > 0.5 nm): slope -> external area,
# intercept -> micropore volume.
mask = t > 0.5
tx, qx = t[mask], Q[mask]
try:
    slope, intercept = np.polyfit(tx, qx, 1)
except Exception:
    slope, intercept = ext_slope_true, micro_plateau

# External surface area S_ext = slope * (1e-9 m/nm wrong-unit guard):
# slope is cm^3/g STP per nm; convert via liquid density to area.
# S_ext [m^2/g] = slope[cm^3 STP/g/nm] * 1e9 nm/m * liq_factor[cm^3/cm^3]
#                 / 0.354 nm (N2 layer thickness)  -- compact form below.
t_layer = 0.354                          # one N2 layer thickness (nm)
S_ext = slope / t_layer * liq_factor * 1e3   # m^2/g (compact estimate)

# Micropore volume from the intercept (liquid N2 volume).
V_micro = max(intercept, 0.0) * liq_factor   # cm^3/g

fit_line = slope * tx + intercept

fig, ax = plt.subplots(figsize=(5.9, 4.3))
ax.plot(t, Q, ".", ms=4, color=DATA, alpha=0.6, label="data")
ax.plot(tx, fit_line, "-", color=FIT, lw=2, label="high-$t$ linear fit")
ax.axhline(intercept, color=ACC, ls="--", lw=1)
ax.set_xlabel(r"statistical thickness  $t$ (nm)")
ax.set_ylabel(r"quantity adsorbed (cm$^3$/g STP)")
ax.set_title("t-plot (Harkins-Jura)")
ax.legend(loc="upper left", frameon=False, fontsize=8)
ax.text(0.97, 0.05,
        r"$V_{micro} = %.4f$ cm$^3$/g" % V_micro + "\n"
        + r"$S_{ext} = %.0f$ m$^2$/g" % S_ext,
        transform=ax.transAxes, ha="right", va="bottom", fontsize=9,
        bbox=dict(boxstyle="round", fc="white", ec="0.8"))
fig.tight_layout()
fig
'''


def _tplot():
    return [_md(_TPLOT_INTRO), _code(_TPLOT)]


# -- Registry --------------------------------------------------------------

BET_EXAMPLES = [
    # (name, category, builder)
    ("N2 Adsorption Isotherm (BET)", "BET", _n2_isotherm),
    ("BET Surface Area (BET)", "BET", _bet_area),
    ("Langmuir Isotherm (BET)", "BET", _langmuir),
    ("BJH Pore Size (BET)", "BET", _bjh),
    ("t-plot Micropore (BET)", "BET", _tplot),
]
