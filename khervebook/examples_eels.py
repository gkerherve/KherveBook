"""EELS (electron energy-loss spectroscopy) examples.

A self-contained companion to ``examples.py`` (Examples menu, "EELS"
category). EELS measures the energy a fast electron loses on passing
through a thin specimen in a (scanning) transmission electron microscope.
The spectrum splits into the **low-loss** region — the zero-loss peak
(ZLP) and collective valence excitations (**plasmons**) — and the
**core-loss** region, where inner-shell ionisation **edges** sit on a
steep power-law background and carry both elemental and chemical-state
information in their **near-edge fine structure** (ELNES).

The standard open-source toolchain is
[HyperSpy](https://hyperspy.org/) with its EELS extension
[eXSpy](https://hyperspy.org/exspy/): e.g. ``import exspy; s =
exspy.data.EELS_MnFe()`` then ``s.remove_background()``,
``s.estimate_thickness()`` and ``s.estimate_elemental_ratio(...)``. Each
code cell mirrors that workflow but synthesises faithful spectra with
NumPy and fits them back with ``scipy`` so the example always runs
offline.

This module defines its own ``_md``/``_code`` helpers and exports
``EELS_EXAMPLES`` so it merges into ``examples.py`` without a circular
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


# -- 1. Low-loss / plasmon ------------------------------------------------

_PLASMON_INTRO = """\
# Low-loss EELS: the zero-loss peak & plasmons

The **low-loss** region of an EELS spectrum (roughly 0-50 eV) is
dominated by two features. The **zero-loss peak (ZLP)** at 0 eV is the
electrons that passed through with no measurable loss; its width sets the
energy resolution. Beyond it sit **plasmon** peaks — collective
oscillations of the valence-electron sea. For a free-electron-like solid
the **plasmon energy** is

$$E_p = \\hbar\\,\\omega_p = \\hbar\\sqrt{\\dfrac{n\\,e^2}{\\varepsilon_0\\,m}}$$

so measuring *E_p* gives the **valence-electron density** *n*. Aluminium
(*E_p* ≈ 15 eV) is the textbook case; multiple scattering produces
weaker plasmon harmonics at 2*E_p*, 3*E_p*, ...

With [HyperSpy](https://hyperspy.org/) + [eXSpy](https://hyperspy.org/exspy/)
a low-loss spectrum is loaded and inspected directly:

```python
import exspy
ll = exspy.data.EELS_low_loss()      # a bundled low-loss spectrum
ll.plot()                            # ZLP + plasmon series
ll.estimate_zero_loss_peak_centre()  # align the energy axis on the ZLP
```

Install it with `pip install exspy`. The cell below synthesises a ZLP
plus a plasmon series, locates the first plasmon and annotates its
energy *E_p*.
"""


_PLASMON = r'''
# Low-loss EELS: a zero-loss peak (ZLP) at 0 eV plus a plasmon series.
# With HyperSpy/eXSpy this would be exspy.data.EELS_low_loss(); here we
# synthesise the spectrum so the example always runs offline.
import numpy as np
import matplotlib.pyplot as plt

rng = np.random.default_rng(0)
ZLP, PLAS = "#3776ab", "#e07b39"

E = np.linspace(-5.0, 60.0, 1400)              # energy loss (eV)


def gaussian(x, amp, cen, sig):
    return amp * np.exp(-0.5 * ((x - cen) / sig) ** 2)


# Zero-loss peak: a sharp Gaussian centred on 0 eV (resolution ~ 1 eV).
zlp = gaussian(E, 1.0, 0.0, 0.45)

# Plasmon series at E_p, 2 E_p, ... (multiple scattering, decaying).
Ep_true = 15.0                                 # bulk plasmon energy (eV)
width = 3.5                                     # plasmon width (eV)
spectrum = zlp.copy()
for order, frac in enumerate([0.18, 0.05, 0.012], start=1):
    spectrum += gaussian(E, frac, order * Ep_true, width * order ** 0.5)
spectrum += 0.0008 * rng.random(E.size)        # detector noise
spectrum = np.clip(spectrum, 1e-5, None)

# Locate the first plasmon: the tallest maximum away from the ZLP.
loss = E > 6.0
idx = np.where(loss)[0]
Ep_meas = E[idx][int(np.argmax(spectrum[idx]))]

# Free-electron check: n from E_p = hbar * sqrt(n e^2 / (eps0 m)).
hbar = 1.054_571e-34                            # J s
e_chg = 1.602_177e-19                           # C
eps0 = 8.854_188e-12                            # F/m
m_e = 9.109_384e-31                             # kg
omega_p = Ep_meas * e_chg / hbar               # rad/s from E_p (eV)
n_val = omega_p ** 2 * eps0 * m_e / e_chg ** 2  # valence density (1/m^3)

fig, ax = plt.subplots(figsize=(6.0, 4.2))
ax.semilogy(E, spectrum, color=PLAS, lw=1.4)
ax.fill_between(E, 1e-5, zlp, color=PLAS, alpha=0.12)
ax.axvline(Ep_meas, color=PLAS, ls="--", lw=1.2)
ax.annotate(r"$E_p = %.1f$ eV" % Ep_meas,
            xy=(Ep_meas, spectrum[idx][int(np.argmax(spectrum[idx]))]),
            xytext=(Ep_meas + 8, 0.4), fontsize=10,
            arrowprops=dict(arrowstyle="->", color="0.4"))
ax.set_xlabel(r"energy loss (eV)")
ax.set_ylabel(r"intensity (arb., log)")
ax.set_title("Low-loss EELS: ZLP + plasmons")
ax.text(0.97, 0.95,
        r"$E_p = %.1f$ eV" % Ep_meas + "\n"
        + r"$n \approx %.1f \times 10^{28}\ \mathrm{m^{-3}}$" % (n_val / 1e28),
        transform=ax.transAxes, va="top", ha="right", fontsize=9,
        bbox=dict(boxstyle="round", fc="white", ec="0.8"))
fig.text(0.01, 0.005, "synthetic low-loss EELS (pip install exspy)",
         fontsize=7, color="0.45")
fig.tight_layout()
fig
'''


def _plasmon():
    return [_md(_PLASMON_INTRO), _code(_PLASMON)]


# -- 2. Core-loss edge & background ---------------------------------------

_COREloss_INTRO = """\
# Core-loss EELS: ionisation edge & power-law background

Above the low-loss region, inner-shell ionisation produces **edges** —
e.g. the **carbon K** edge at ≈ 284 eV — whose onset energy identifies
the element. Each edge rides on a steep **background** from the tails of
all lower-energy excitations, well described over a limited window by a
**power law**

$$I_\\mathrm{bg}(E) = A\\,E^{-r}$$

The textbook quantification recipe is: fit *A* and *r* in a **pre-edge**
window, extrapolate the background under the edge, **subtract** it, then
**integrate** the net edge intensity over an energy window past the
onset.

With [HyperSpy](https://hyperspy.org/) + [eXSpy](https://hyperspy.org/exspy/)
this is one call:

```python
import exspy
s = exspy.data.EELS_MnFe()          # bundled core-loss spectrum
s.remove_background(signal_range=(250.0, 280.0))  # power-law fit + subtract
s.plot()                            # background-subtracted edges
```

Install it with `pip install exspy`. The cell below synthesises a carbon
K edge on an `A E^{-r}` background, fits the pre-edge power law,
subtracts it and integrates the net edge.
"""


_COREloss = r'''
# Core-loss EELS: a carbon K edge on a power-law background A*E^(-r).
# With HyperSpy/eXSpy this is s.remove_background(); here we synthesise
# the spectrum and fit the pre-edge power law with scipy so it runs.
import numpy as np
import matplotlib.pyplot as plt
from scipy.optimize import curve_fit

rng = np.random.default_rng(0)
RAW, BG, NET = "#3776ab", "#e07b39", "#50bea0"

E = np.linspace(200.0, 420.0, 1200)            # energy loss (eV)


def powerlaw(e, A, r):
    return A * e ** (-r)


# True background plus a carbon K edge (~284 eV): a smooth saw-tooth
# rise that itself decays as a power law past the onset.
A_true, r_true = 4.0e9, 3.1
bg_true = powerlaw(E, A_true, r_true)
edge_onset = 284.0                             # carbon K edge (eV)
step = 1.0 / (1.0 + np.exp(-(E - edge_onset) / 2.0))
edge_true = 90.0 * step * (edge_onset / np.clip(E, edge_onset, None)) ** 3.0
spectrum = bg_true + edge_true
spectrum = spectrum * (1.0 + 0.02 * rng.standard_normal(E.size))
spectrum = np.clip(spectrum, 1e-3, None)

# Fit the power-law background in a PRE-edge window (well below 284 eV).
pre = (E >= 235.0) & (E <= 275.0)
try:
    popt, _ = curve_fit(powerlaw, E[pre], spectrum[pre],
                        p0=[A_true, r_true], maxfev=20000)
except Exception:
    popt = [A_true, r_true]
A_fit, r_fit = popt
bg_fit = powerlaw(E, A_fit, r_fit)

# Subtract the background and integrate the net edge over a window.
net = spectrum - bg_fit
win = (E >= edge_onset) & (E <= edge_onset + 50.0)
net_signal = np.clip(net, 0.0, None)
edge_integral = np.trapz(net_signal[win], E[win])    # net counts (eV.arb)

fig, ax = plt.subplots(figsize=(6.2, 4.3))
ax.plot(E, spectrum, color=RAW, lw=1.3, label="raw spectrum")
ax.plot(E, bg_fit, "--", color=BG, lw=1.6, label=r"power-law $A E^{-r}$")
ax.plot(E, net_signal, color=NET, lw=1.4, label="net edge")
ax.axvspan(235.0, 275.0, color=BG, alpha=0.08)
ax.axvspan(edge_onset, edge_onset + 50.0, color=NET, alpha=0.10)
ax.axvline(edge_onset, color="0.5", ls=":", lw=1.0)
ax.set_xlabel(r"energy loss (eV)")
ax.set_ylabel(r"intensity (arb.)")
ax.set_title("Core-loss EELS: C-K edge & background")
ax.legend(loc="upper right", frameon=False, fontsize=8)
ax.text(0.03, 0.95,
        r"C-K onset $\approx 284$ eV" + "\n"
        + r"$r = %.2f$" % r_fit + "\n"
        + r"$\int$ net $= %.2g$" % edge_integral,
        transform=ax.transAxes, va="top", fontsize=9,
        bbox=dict(boxstyle="round", fc="white", ec="0.8"))
fig.text(0.01, 0.005, "synthetic core-loss EELS (pip install exspy)",
         fontsize=7, color="0.45")
fig.tight_layout()
fig
'''


def _coreloss():
    return [_md(_COREloss_INTRO), _code(_COREloss)]


# -- 3. Thickness (log-ratio) ---------------------------------------------

_THICK_INTRO = """\
# EELS specimen thickness: the log-ratio method

The single most-used EELS measurement is **relative thickness**. Because
inelastic scattering is Poisson-distributed, the fraction of electrons
that lose *no* energy (the ZLP) versus the total tells you how many
inelastic mean free paths the beam crossed:

$$\\dfrac{t}{\\lambda} = \\ln\\!\\left(\\dfrac{I_\\mathrm{total}}{I_\\mathrm{ZLP}}\\right)$$

where *λ* is the **inelastic mean free path**. If *λ* is known (from
tables or the Malis/Iakoubovskii formulae) the absolute thickness *t* =
*λ* · (*t*/*λ*) follows. Reliable up to *t*/*λ* ≈ 3-4.

With [HyperSpy](https://hyperspy.org/) + [eXSpy](https://hyperspy.org/exspy/)
it is literally one method on a low-loss spectrum:

```python
import exspy
ll = exspy.data.EELS_low_loss()
t_over_lambda = ll.estimate_thickness()   # log-ratio t/lambda map
```

Install it with `pip install exspy`. The cell below builds a low-loss
spectrum, splits the ZLP from the inelastic tail and computes *t*/*λ*
(and *t* for an assumed *λ*).
"""


_THICK = r'''
# EELS thickness by the log-ratio method: t/lambda = ln(I_total / I_ZLP)
# from a low-loss spectrum. In HyperSpy/eXSpy this is
# ll.estimate_thickness(); here we synthesise the spectrum so it runs.
import numpy as np
import matplotlib.pyplot as plt

rng = np.random.default_rng(0)
TOTAL, ZLPC = "#3776ab", "#e07b39"

E = np.linspace(-5.0, 80.0, 1700)              # energy loss (eV)


def gaussian(x, amp, cen, sig):
    return amp * np.exp(-0.5 * ((x - cen) / sig) ** 2)


# Zero-loss peak plus a plasmon tail whose weight grows with thickness.
zlp = gaussian(E, 1.0, 0.0, 0.5)
Ep = 17.0
inel = (gaussian(E, 0.45, Ep, 4.0)
        + gaussian(E, 0.16, 2 * Ep, 6.0)
        + gaussian(E, 0.05, 3 * Ep, 8.0))
spectrum = zlp + inel + 0.0008 * rng.random(E.size)
spectrum = np.clip(spectrum, 1e-5, None)

# Integrate the ZLP (a narrow window around 0 eV) and the whole spectrum.
zlp_win = np.abs(E) <= 3.0
I_zlp = np.trapz(spectrum[zlp_win], E[zlp_win])
I_total = np.trapz(spectrum, E)

t_over_lambda = np.log(I_total / I_zlp)        # relative thickness
lam_nm = 120.0                                 # assumed mean free path (nm)
t_nm = lam_nm * t_over_lambda                  # absolute thickness (nm)

fig, ax = plt.subplots(figsize=(6.0, 4.2))
ax.plot(E, spectrum, color=TOTAL, lw=1.3, label="low-loss spectrum")
ax.fill_between(E, 0, spectrum, where=zlp_win, color=ZLPC, alpha=0.30,
                label="ZLP window")
ax.set_yscale("log")
ax.set_ylim(1e-4, 2.0)
ax.set_xlabel(r"energy loss (eV)")
ax.set_ylabel(r"intensity (arb., log)")
ax.set_title("EELS thickness (log-ratio)")
ax.legend(loc="upper right", frameon=False, fontsize=8)
ax.text(0.97, 0.55,
        r"$t/\lambda = %.2f$" % t_over_lambda + "\n"
        + r"$\lambda = %.0f$ nm" % lam_nm + "\n"
        + r"$t \approx %.0f$ nm" % t_nm,
        transform=ax.transAxes, va="top", ha="right", fontsize=9,
        bbox=dict(boxstyle="round", fc="white", ec="0.8"))
fig.text(0.01, 0.005, "synthetic low-loss EELS (pip install exspy)",
         fontsize=7, color="0.45")
fig.tight_layout()
fig
'''


def _thickness():
    return [_md(_THICK_INTRO), _code(_THICK)]


# -- 4. Quantification ----------------------------------------------------

_QUANT_INTRO = """\
# EELS quantification: composition from two edges

To turn core-loss edges into **atomic concentrations** you take the net
(background-subtracted) intensity *I_A* of each element's edge, divide by
its **partial ionisation cross-section** *σ_A* (integrated over the same
energy window and collection angle), and compare:

$$\\dfrac{N_A}{N_B} = \\dfrac{I_A / \\sigma_A}{I_B / \\sigma_B}$$

Here we quantify **boron K** (≈ 188 eV) against **nitrogen K** (≈ 401
eV) — the classic boron-nitride test case, nominally 50:50.

With [HyperSpy](https://hyperspy.org/) + [eXSpy](https://hyperspy.org/exspy/)
the cross-sections (Hartree-Slater or hydrogenic) and the ratio are built
in:

```python
import exspy
s = exspy.data.EELS_MnFe()
s.add_elements(('B', 'N'))
s.estimate_elemental_ratio('B', 'N')   # uses tabulated cross-sections
```

Install it with `pip install exspy`. The cell below synthesises B-K and
N-K edges, removes a power-law background under each, integrates the net
intensities, divides by partial cross-sections and reports at%.
"""


_QUANT = r'''
# EELS quantification: B-K and N-K edges -> composition ratio. Net edge
# intensities / partial cross-sections give N_B / N_N. In HyperSpy/eXSpy
# this is s.estimate_elemental_ratio(); here it is synthesised + fitted.
import numpy as np
import matplotlib.pyplot as plt
from scipy.optimize import curve_fit

rng = np.random.default_rng(0)
RAW, BG = "#3776ab", "#e07b39"

E = np.linspace(150.0, 480.0, 1500)            # energy loss (eV)


def powerlaw(e, A, r):
    return A * e ** (-r)


def edge(e, onset, height, decay):
    step = 1.0 / (1.0 + np.exp(-(e - onset) / 2.0))
    return height * step * (onset / np.clip(e, onset, None)) ** decay


# Background + a boron-K edge (~188 eV) and a nitrogen-K edge (~401 eV).
A_true, r_true = 6.0e8, 2.8
B_onset, N_onset = 188.0, 401.0
spectrum = (powerlaw(E, A_true, r_true)
            + edge(E, B_onset, 70.0, 3.0)
            + edge(E, N_onset, 95.0, 3.0))
spectrum = spectrum * (1.0 + 0.02 * rng.standard_normal(E.size))
spectrum = np.clip(spectrum, 1e-3, None)


def net_edge_intensity(onset, pre_lo, pre_hi, win):
    """Fit a pre-edge power law, subtract, integrate over `win` eV."""
    pre = (E >= pre_lo) & (E <= pre_hi)
    try:
        p, _ = curve_fit(powerlaw, E[pre], spectrum[pre],
                        p0=[A_true, r_true], maxfev=20000)
    except Exception:
        p = [A_true, r_true]
    net = np.clip(spectrum - powerlaw(E, *p), 0.0, None)
    w = (E >= onset) & (E <= onset + win)
    return np.trapz(net[w], E[w]), powerlaw(E, *p)


I_B, bg_B = net_edge_intensity(B_onset, 160.0, 184.0, 50.0)
I_N, bg_N = net_edge_intensity(N_onset, 360.0, 396.0, 50.0)

# Partial ionisation cross-sections (arb., as eXSpy would tabulate them).
sigma_B, sigma_N = 1.00, 1.30
ratio = (I_B / sigma_B) / (I_N / sigma_N)      # N_B / N_N
at_B = 100.0 * ratio / (1.0 + ratio)           # boron at%
at_N = 100.0 - at_B                            # nitrogen at%

fig, ax = plt.subplots(figsize=(6.2, 4.3))
ax.plot(E, spectrum, color=RAW, lw=1.3, label="raw spectrum")
ax.plot(E, bg_B, "--", color=BG, lw=1.2, alpha=0.9, label=r"power-law bg")
ax.plot(E, bg_N, "--", color=BG, lw=1.2, alpha=0.9)
ax.axvline(B_onset, color="0.5", ls=":", lw=1.0)
ax.axvline(N_onset, color="0.5", ls=":", lw=1.0)
ax.annotate("B-K", xy=(B_onset, 0.0), xytext=(B_onset + 4, spectrum.max() * 0.6),
            fontsize=9, color="0.3")
ax.annotate("N-K", xy=(N_onset, 0.0), xytext=(N_onset + 4, spectrum.max() * 0.35),
            fontsize=9, color="0.3")
ax.set_xlabel(r"energy loss (eV)")
ax.set_ylabel(r"intensity (arb.)")
ax.set_title("EELS quantification: B-K vs N-K")
ax.legend(loc="upper right", frameon=False, fontsize=8)
ax.text(0.03, 0.95,
        r"B $%.0f$ at%%" % at_B + "\n"
        + r"N $%.0f$ at%%" % at_N,
        transform=ax.transAxes, va="top", fontsize=9,
        bbox=dict(boxstyle="round", fc="white", ec="0.8"))
fig.text(0.01, 0.005, "synthetic core-loss EELS (pip install exspy)",
         fontsize=7, color="0.45")
fig.tight_layout()
fig
'''


def _quantification():
    return [_md(_QUANT_INTRO), _code(_QUANT)]


# -- 5. Fine structure (ELNES) --------------------------------------------

_ELNES_INTRO = """\
# Energy-loss near-edge structure (ELNES): white lines

The first ~30 eV of an ionisation edge — the **energy-loss near-edge
structure (ELNES)** — mirrors the unoccupied density of states and so
encodes the **chemical state**. For transition metals the *L*-edge shows
two sharp **white lines**, *L₃* and *L₂* (the *2p₃/₂* and *2p₁/₂*
spin-orbit pair), from transitions into empty *3d* states. Their
intensity ratio **L₃/L₂** rises as the *3d* shell empties, so it is a
sensitive fingerprint of **oxidation state** (e.g. Mn²⁺ vs Mn⁴⁺,
Fe²⁺ vs Fe³⁺).

With [HyperSpy](https://hyperspy.org/) + [eXSpy](https://hyperspy.org/exspy/)
the bundled Mn/Fe spectrum is the canonical demo, and white lines are
fitted as Gaussian/Lorentzian components on the edge:

```python
import exspy
s = exspy.data.EELS_MnFe()          # Mn & Fe L-edges
s.remove_background()
s.plot()                            # resolve the L3 / L2 white lines
```

Install it with `pip install exspy`. The cell below synthesises a
transition-metal *L₂,₃* doublet for **two oxidation states** with
different L₃/L₂ ratios and annotates each.
"""


_ELNES = r'''
# ELNES white lines: an L3/L2 doublet for two oxidation states. The
# L3/L2 intensity ratio tracks oxidation state. In HyperSpy/eXSpy this
# is exspy.data.EELS_MnFe() + remove_background(); synthesised here.
import numpy as np
import matplotlib.pyplot as plt

rng = np.random.default_rng(0)
LOWOX, HIGHOX = "#3776ab", "#e07b39"

E = np.linspace(625.0, 680.0, 1400)            # energy loss (eV), Mn L-edge


def lorentzian(x, amp, cen, wid):
    return amp * wid ** 2 / ((x - cen) ** 2 + wid ** 2)


def L_edge(L3_amp, L2_amp):
    """L3 + L2 white lines on a smooth arctan step continuum."""
    L3 = lorentzian(E, L3_amp, 640.0, 1.1)     # L3 (2p3/2)
    L2 = lorentzian(E, L2_amp, 651.0, 1.2)     # L2 (2p1/2)
    cont = 0.25 * (0.5 + np.arctan((E - 642.0) / 4.0) / np.pi)
    noise = 0.01 * rng.standard_normal(E.size)
    return L3 + L2 + cont + noise


# Two oxidation states: the lower one has the larger L3/L2 ratio.
spec_low = L_edge(L3_amp=1.00, L2_amp=0.34)    # e.g. Mn(II): high L3/L2
spec_high = L_edge(L3_amp=0.78, L2_amp=0.42)   # e.g. Mn(IV): lower L3/L2


def l3_l2_ratio(spec):
    """Ratio of integrated intensity in the L3 vs L2 white-line windows."""
    cont = 0.25 * (0.5 + np.arctan((E - 642.0) / 4.0) / np.pi)
    net = np.clip(spec - cont, 0.0, None)
    w3 = (E >= 636.0) & (E <= 644.0)
    w2 = (E >= 647.0) & (E <= 655.0)
    return np.trapz(net[w3], E[w3]) / np.trapz(net[w2], E[w2])


r_low = l3_l2_ratio(spec_low)
r_high = l3_l2_ratio(spec_high)

fig, ax = plt.subplots(figsize=(6.2, 4.3))
ax.plot(E, spec_low, color=LOWOX, lw=1.4,
        label=r"low ox. state ($L_3/L_2 = %.2f$)" % r_low)
ax.plot(E, spec_high + 0.4, color=HIGHOX, lw=1.4,
        label=r"high ox. state ($L_3/L_2 = %.2f$)" % r_high)
ax.axvline(640.0, color="0.6", ls=":", lw=0.9)
ax.axvline(651.0, color="0.6", ls=":", lw=0.9)
ax.annotate(r"$L_3$", xy=(640.0, 1.1), xytext=(636.5, 1.35),
            fontsize=11, color="0.3")
ax.annotate(r"$L_2$", xy=(651.0, 0.45), xytext=(653.0, 0.75),
            fontsize=11, color="0.3")
ax.set_xlabel(r"energy loss (eV)")
ax.set_ylabel(r"intensity (arb., offset)")
ax.set_title(r"ELNES white lines: $L_3/L_2$ vs oxidation state")
ax.legend(loc="upper right", frameon=False, fontsize=8)
fig.text(0.01, 0.005, "synthetic L-edge ELNES (pip install exspy)",
         fontsize=7, color="0.45")
fig.tight_layout()
fig
'''


def _elnes():
    return [_md(_ELNES_INTRO), _code(_ELNES)]


# -- Registry --------------------------------------------------------------

EELS_EXAMPLES = [
    # (name, category, builder)
    ("EELS Low-Loss / Plasmon (EELS)", "EELS", _plasmon),
    ("EELS Core-Loss Edge & Background (EELS)", "EELS", _coreloss),
    ("EELS Thickness (log-ratio) (EELS)", "EELS", _thickness),
    ("EELS Quantification (EELS)", "EELS", _quantification),
    ("EELS Fine Structure (ELNES) (EELS)", "EELS", _elnes),
]
