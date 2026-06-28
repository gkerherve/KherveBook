"""Nuclear magnetic resonance (NMR) examples.

A self-contained companion to ``examples.py`` (Examples menu, "NMR"
category). ``nmrglue`` (``pip install nmrglue``) is the standard Python
toolkit for reading and processing NMR data from Bruker, Varian/Agilent,
NMRPipe, Sparky and JCAMP-DX files; the markdown cells point at its API
(e.g. ``dic, data = ng.bruker.read(path)``) for working with real
spectra.

Every code cell here synthesises faithful data with NumPy and processes
it with SciPy so the examples always run offline, with or without
``nmrglue`` installed. The five examples cover the everyday 1-D and 2-D
NMR workflow:

* a **1H NMR spectrum** built from Lorentzian multiplets with realistic
  J-coupling and 3:2:1 integration (ethanol),
* an **FID -> spectrum** pipeline (apodisation + FFT),
* **peak picking & integration** to relative proton counts,
* a **T1 inversion-recovery** fit, and
* a synthetic **2D COSY** correlation map.

This module defines its own ``_md``/``_code`` helpers and exports
``NMR_EXAMPLES`` so it merges into ``examples.py`` without a circular
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


# -- 1. 1H NMR spectrum ----------------------------------------------------

_PROTON_INTRO = """\
# 1H NMR spectrum

A **proton (1H) NMR spectrum** plots signal intensity against **chemical
shift** in parts per million (ppm), with the axis running **high to low**
(left to right) by convention. Each chemically distinct set of protons
gives a peak at its own shift; neighbouring protons split that peak into a
**multiplet** by *J*-coupling (the n+1 rule), and the **integrated area**
under each multiplet is proportional to the number of protons.

**Ethanol** (CH3-CH2-OH) is the textbook example:

| group | shift (ppm) | multiplicity | protons |
|-------|-------------|--------------|---------|
| CH3   | 1.2         | triplet      | 3       |
| CH2   | 3.7         | quartet      | 2       |
| OH    | 2.6         | singlet      | 1       |

so the integrals come out **3:2:1**.

With [`nmrglue`](https://www.nmrglue.com/) a real Bruker dataset is two
lines, and the ppm axis comes from the spectrometer parameters:

```python
import nmrglue as ng
dic, data = ng.bruker.read("path/to/ethanol/1")   # raw Bruker data
udic = ng.bruker.guess_udic(dic, data)
uc = ng.fileiobase.uc_from_udic(udic)
ppm = uc.ppm_scale()                                # chemical-shift axis
```

The cell below synthesises the ethanol spectrum from Lorentzian
multiplets so it always runs.
"""


_PROTON = r'''
# 1H NMR spectrum of ethanol, built from Lorentzian multiplets.
# Each group is a set of equally spaced Lorentzians (J-coupling) whose
# relative line heights follow Pascal's triangle (the n+1 rule) and whose
# total area equals the proton count, giving the textbook 3:2:1 integrals.
# With nmrglue a real Bruker FID would be read and Fourier transformed.
import math
import numpy as np
import matplotlib.pyplot as plt

rng = np.random.default_rng(0)
SIG, ACC, INT = "#3776ab", "#e07b39", "#50bea0"

ppm = np.linspace(0.0, 6.0, 6000)      # chemical-shift axis (ppm)
J_ppm = 0.018                          # J-coupling spacing in ppm units
HW = 0.006                             # Lorentzian half-width (ppm)


def lorentzian(x, x0, hw):
    """Unit-area Lorentzian centred at x0 with half-width hw."""
    return (hw / np.pi) / ((x - x0) ** 2 + hw ** 2)


def multiplet(x, centre, n_lines, area):
    """A J-coupled multiplet: n_lines Lorentzians, Pascal-weighted,
    total integral = area (so area encodes the proton count)."""
    weights = np.array([math.comb(n_lines - 1, k)
                        for k in range(n_lines)], dtype=float)
    weights /= weights.sum()
    offsets = (np.arange(n_lines) - (n_lines - 1) / 2.0) * J_ppm
    y = np.zeros_like(x)
    for w, off in zip(weights, offsets):
        y += area * w * lorentzian(x, centre + off, HW)
    return y


# (centre ppm, multiplicity, label, integral = proton count)
groups = [
    (1.20, 3, r"CH$_3$ (triplet)", 3.0),
    (3.70, 4, r"CH$_2$ (quartet)", 2.0),
    (2.60, 1, "OH (singlet)", 1.0),
]

spectrum = np.zeros_like(ppm)
for centre, n_lines, _label, area in groups:
    spectrum += multiplet(ppm, centre, n_lines, area)
spectrum += 0.002 * rng.standard_normal(ppm.size)   # baseline noise

# Numerically integrate each group to confirm the 3:2:1 ratio.
dx = ppm[1] - ppm[0]
integrals = []
for centre, _n, _label, _area in groups:
    sel = np.abs(ppm - centre) < 0.30
    integrals.append(np.trapz(spectrum[sel], ppm[sel]))
integrals = np.array(integrals)
ratio = integrals / integrals.min()                 # normalise to OH = 1

fig, ax = plt.subplots(figsize=(7.4, 4.3))
ax.plot(ppm, spectrum, color=SIG, lw=1.1)
ax.axhline(0, color="0.75", lw=0.7)
for (centre, _n, label, _area), r in zip(groups, ratio):
    ymax = spectrum[np.abs(ppm - centre) < 0.30].max()
    ax.annotate(label, xy=(centre, ymax), xytext=(centre, ymax + 6),
                ha="center", fontsize=8, color=ACC)
    ax.annotate(r"$\int = %.0f$H" % round(r), xy=(centre, 0),
                xytext=(centre, -3.2), ha="center", fontsize=8, color=INT)
ax.set_xlabel(r"chemical shift $\delta$ (ppm)")
ax.set_ylabel("intensity (arb.)")
ax.set_title(r"$^1$H NMR of ethanol  (integrals %d : %d : %d)"
             % tuple(int(round(r)) for r in ratio))
ax.set_ylim(-5, spectrum.max() * 1.18)
ax.invert_xaxis()                                   # ppm decreases L -> R
fig.tight_layout()
fig
'''


def _proton_nmr():
    return [_md(_PROTON_INTRO), _code(_PROTON)]


# -- 2. FID to spectrum ----------------------------------------------------

_FID_INTRO = """\
# FID to spectrum

NMR is measured in the **time domain**: after the radio-frequency pulse the
nuclei precess and induce a decaying signal in the coil, the **free
induction decay (FID)**. Each chemically distinct spin contributes a
decaying complex exponential at its own frequency; the **transverse
relaxation time** *T2* sets how fast it decays (and hence the linewidth).

The spectrum is obtained by

1. **apodisation** — multiplying the FID by a window (here an exponential,
   "line broadening") to improve signal-to-noise, then
2. a **fast Fourier transform (FFT)** to the frequency domain.

With [`nmrglue`](https://www.nmrglue.com/) the same pipeline runs on real
data:

```python
import nmrglue as ng
dic, fid = ng.bruker.read("path/to/expt/1")
fid = ng.proc_base.em(fid, lb=0.3)        # exponential apodisation
spec = ng.proc_base.fft(fid)              # FFT to the frequency domain
spec = ng.proc_autophase.autops(spec, "acme")   # automatic phasing
```

The cell below builds a three-line FID, apodises it and FFTs it, showing
the time-domain signal and the resulting spectrum side by side.
"""


_FID = r'''
# FID -> spectrum: sum of decaying complex exponentials, exponential
# apodisation, then FFT. This mirrors ng.proc_base.em + ng.proc_base.fft
# on a Bruker FID, but on synthetic data so it always runs.
import numpy as np
import matplotlib.pyplot as plt

rng = np.random.default_rng(0)
SIG, ACC = "#3776ab", "#e07b39"

n = 4096
sw = 5000.0                              # spectral width (Hz)
dt = 1.0 / sw                            # dwell time (s)
t = np.arange(n) * dt                    # acquisition time axis (s)

# Three resonances: (frequency Hz, amplitude, T2 decay s).
lines = [(-1200.0, 1.0, 0.30),
         (200.0, 0.7, 0.22),
         (1500.0, 0.5, 0.16)]

fid = np.zeros(n, dtype=complex)
for freq, amp, t2 in lines:
    fid += amp * np.exp(2j * np.pi * freq * t) * np.exp(-t / t2)
fid += (rng.standard_normal(n) + 1j * rng.standard_normal(n)) * 0.01

# Exponential apodisation ("line broadening"): emphasise early, high-S/N
# points and taper the noisy tail before the transform.
lb = 5.0                                 # line broadening (Hz)
window = np.exp(-np.pi * lb * t)
fid_apod = fid * window

# FFT to the frequency domain; fftshift puts 0 Hz in the centre.
spec = np.fft.fftshift(np.fft.fft(fid_apod))
freq = np.fft.fftshift(np.fft.fftfreq(n, d=dt))      # frequency axis (Hz)
mag = np.abs(spec)

fig, (a1, a2) = plt.subplots(1, 2, figsize=(8.0, 3.6))
a1.plot(t * 1e3, fid.real, color=SIG, lw=0.8, label="FID (real)")
a1.plot(t * 1e3, np.abs(fid), color=ACC, lw=1.0, label="envelope")
a1.set_xlabel("time (ms)")
a1.set_ylabel("signal")
a1.set_title("Free induction decay")
a1.legend(loc="upper right", frameon=False, fontsize=8)

a2.plot(freq, mag, color=SIG, lw=1.0)
a2.set_xlabel("frequency (Hz)")
a2.set_ylabel("intensity")
a2.set_title("Spectrum (apodised + FFT)")
a2.invert_xaxis()                        # NMR frequency axis decreases L->R
fig.tight_layout()
fig
'''


def _fid_to_spectrum():
    return [_md(_FID_INTRO), _code(_FID)]


# -- 3. Peak picking & integration ----------------------------------------

_PICK_INTRO = """\
# NMR peak picking & integration

Quantitative 1-D NMR has two routine steps:

* **peak picking** — find local maxima that rise above a noise
  **threshold**, giving the chemical shifts of the resonances, and
* **integration** — sum the area under each peak's region; because every
  proton contributes equally, the **relative integrals** give the **proton
  ratio** between groups.

[`nmrglue`](https://www.nmrglue.com/) has both built in:

```python
import nmrglue as ng
peaks = ng.peakpick.pick(data, pthres=threshold)   # table of peaks
area = data[lo:hi].sum()                            # region integral
```

The cell below synthesises a four-group spectrum, picks the peaks above a
threshold, shades each integration region and reports the relative proton
counts.
"""


_PICK = r'''
# Peak picking + integration. Find maxima above a noise threshold, then
# integrate a window around each to get relative proton counts. With
# nmrglue: ng.peakpick.pick(data, pthres=thr). Synthetic so it always runs.
import numpy as np
import matplotlib.pyplot as plt
from scipy.signal import find_peaks

rng = np.random.default_rng(0)
SIG, ACC, SHADE = "#3776ab", "#e07b39", "#50bea0"

ppm = np.linspace(0.0, 8.0, 8000)
HW = 0.012


def lorentzian(x, x0, hw, area):
    return area * (hw / np.pi) / ((x - x0) ** 2 + hw ** 2)


# (centre ppm, relative area = proton count)
groups = [(7.30, 5.0),     # aromatic, 5H
          (3.60, 2.0),     # CH2, 2H
          (2.10, 3.0),     # CH3, 3H
          (1.20, 3.0)]     # CH3, 3H

spectrum = np.zeros_like(ppm)
for centre, area in groups:
    spectrum += lorentzian(ppm, centre, HW, area)
spectrum += 0.6 * rng.standard_normal(ppm.size)   # baseline noise

# Peak picking: maxima above a noise-based threshold.
noise = np.std(spectrum[(ppm > 5.0) & (ppm < 6.5)])
threshold = 8.0 * noise
idx, _props = find_peaks(spectrum, height=threshold, distance=200)
peak_ppm = ppm[idx]
peak_int = spectrum[idx]

# Integrate a fixed window about each picked peak -> relative proton count.
dx = ppm[1] - ppm[0]
half_window = 0.30
areas = []
for c in peak_ppm:
    sel = np.abs(ppm - c) < half_window
    areas.append(np.trapz(spectrum[sel], ppm[sel]))
areas = np.array(areas)
protons = areas / areas.min()           # normalise to the smallest group

fig, ax = plt.subplots(figsize=(7.6, 4.3))
ax.plot(ppm, spectrum, color=SIG, lw=0.9)
ax.axhline(threshold, color=ACC, ls="--", lw=1.0, label="threshold")
for c, h, p in zip(peak_ppm, peak_int, protons):
    sel = np.abs(ppm - c) < half_window
    ax.fill_between(ppm[sel], spectrum[sel], color=SHADE, alpha=0.35)
    ax.plot(c, h, "v", color=ACC, ms=7)
    ax.annotate(r"%.1f ppm" % c, xy=(c, h), xytext=(c, h + 6),
                ha="center", fontsize=8, color=ACC)
    ax.annotate(r"%.0f H" % round(p), xy=(c, 0), xytext=(c, -7),
                ha="center", fontsize=8, color=SHADE)
ax.set_xlabel(r"chemical shift $\delta$ (ppm)")
ax.set_ylabel("intensity (arb.)")
ax.set_title("Peak picking & integration  (ratio %s)"
             % " : ".join("%d" % round(p) for p in protons))
ax.set_ylim(-12, spectrum.max() * 1.18)
ax.legend(loc="upper left", frameon=False, fontsize=8)
ax.invert_xaxis()                        # ppm decreases L -> R
fig.tight_layout()
fig
'''


def _peak_picking():
    return [_md(_PICK_INTRO), _code(_PICK)]


# -- 4. T1 relaxation ------------------------------------------------------

_T1_INTRO = """\
# T1 relaxation (inversion recovery)

The **longitudinal (spin-lattice) relaxation time** *T1* governs how fast
the magnetisation returns to equilibrium along the field after a pulse. The
standard measurement is **inversion recovery**: a 180 deg pulse inverts the
magnetisation, a variable delay $\\tau$ lets it relax, and a 90 deg pulse
reads it out. The peak intensity follows

$$M(\\tau) = M_0\\,(1 - 2\\,e^{-\\tau / T_1}).$$

The signal starts negative (inverted), passes through a **null** at
$\\tau = T_1 \\ln 2$, and recovers to $+M_0$. Fitting the
$(\\tau, M)$ points recovers *T1*.

With [`nmrglue`](https://www.nmrglue.com/) you read the pseudo-2-D
experiment, integrate the peak in each row to build the recovery curve, and
fit it:

```python
import nmrglue as ng
dic, data = ng.bruker.read("path/to/ir_experiment")
M = data[:, lo:hi].sum(axis=1)          # peak integral vs delay tau
```

The cell below fits a synthetic inversion-recovery dataset with
`scipy.optimize.curve_fit` to recover *T1*.
"""


_T1 = r'''
# T1 inversion recovery: fit M(tau) = M0 * (1 - 2*exp(-tau/T1)) to recover
# the spin-lattice relaxation time. With nmrglue the M values would be peak
# integrals from each row of a pseudo-2D experiment; here data are synthetic.
import numpy as np
import matplotlib.pyplot as plt
from scipy.optimize import curve_fit

rng = np.random.default_rng(0)
DATA, FIT = "#3776ab", "#e07b39"

M0_true = 1.0
T1_true = 0.85                           # true relaxation time (s)

tau = np.array([0.01, 0.05, 0.1, 0.2, 0.35, 0.5, 0.75,
                1.0, 1.5, 2.0, 3.0, 5.0])         # delays (s)


def recovery(t, M0, T1):
    return M0 * (1.0 - 2.0 * np.exp(-t / T1))


M = recovery(tau, M0_true, T1_true) + rng.normal(0.0, 0.03, tau.size)

# Fit to recover M0 and T1; guard curve_fit so the cell always runs.
p0 = [1.0, 1.0]
try:
    popt, _ = curve_fit(recovery, tau, M, p0=p0, maxfev=20000)
except Exception:
    popt = p0
M0_fit, T1_fit = popt
T1_fit = abs(T1_fit)
tau_null = T1_fit * np.log(2.0)          # zero-crossing delay

tt = np.linspace(0.0, tau.max(), 400)
fit_curve = recovery(tt, *popt)

fig, ax = plt.subplots(figsize=(6.4, 4.3))
ax.axhline(0, color="0.75", lw=0.7)
ax.plot(tau, M, "o", color=DATA, ms=6, label="data")
ax.plot(tt, fit_curve, "-", color=FIT, lw=2, label="fit")
ax.axvline(tau_null, color="0.5", ls=":", lw=1.0)
ax.set_xlabel(r"recovery delay $\tau$ (s)")
ax.set_ylabel(r"peak intensity $M(\tau)$")
ax.set_title(r"Inversion recovery: $M = M_0(1 - 2e^{-\tau/T_1})$")
ax.legend(loc="lower right", frameon=False)
ax.text(0.04, 0.92,
        r"$T_1 = %.2f$ s" % T1_fit + "\n"
        + r"null at $\tau = T_1\ln 2 = %.2f$ s" % tau_null,
        transform=ax.transAxes, va="top", fontsize=9,
        bbox=dict(boxstyle="round", fc="white", ec="0.8"))
fig.tight_layout()
fig
'''


def _t1_relaxation():
    return [_md(_T1_INTRO), _code(_T1)]


# -- 5. 2D COSY ------------------------------------------------------------

_COSY_INTRO = """\
# 2D COSY

**COSY (COrrelation SpectroscopY)** is the workhorse 2-D experiment for
connecting protons that are *J*-coupled to one another. Both axes are
chemical shift in ppm. The map has

* **diagonal peaks** ($\\delta_1 = \\delta_2$) — the ordinary 1-D spectrum
  along the diagonal, and
* **cross-peaks** off the diagonal — a symmetric pair at
  $(\\delta_A, \\delta_B)$ and $(\\delta_B, \\delta_A)$ for every pair of
  **coupled** spins.

Reading the cross-peaks back to the diagonal traces out the coupling
network (e.g. the CH3-CH2 connectivity in ethanol).

With [`nmrglue`](https://www.nmrglue.com/) a real COSY is read, processed
per dimension and contoured:

```python
import nmrglue as ng
dic, data = ng.bruker.read("path/to/cosy")
data = ng.proc_base.fft(ng.proc_base.em(data))     # process each dimension
ppm_x = uc_x.ppm_scale(); ppm_y = uc_y.ppm_scale()
```

The cell below synthesises a COSY map (diagonal + symmetric cross-peaks)
and draws it with both ppm axes inverted.
"""


_COSY = r'''
# Synthetic 2D COSY: diagonal peaks plus symmetric cross-peaks for each
# pair of coupled spins, drawn as a contour map with both ppm axes
# inverted. With nmrglue this 2D array would come from ng.bruker.read +
# per-dimension processing; here it is built analytically so it always runs.
import numpy as np
import matplotlib.pyplot as plt

SIG, ACC = "#3776ab", "#e07b39"

shifts = np.array([1.20, 3.70, 2.60])    # CH3, CH2, OH (ppm)
# Coupled pairs (indices into `shifts`): CH3 <-> CH2.
couplings = [(0, 1)]

ppm = np.linspace(0.5, 4.5, 400)         # shared chemical-shift grid (ppm)
X, Y = np.meshgrid(ppm, ppm)
W = 0.05                                  # peak width (ppm)


def peak2d(x0, y0, amp):
    return amp * np.exp(-((X - x0) ** 2 + (Y - y0) ** 2) / (2.0 * W ** 2))


Z = np.zeros_like(X)
for s in shifts:                         # diagonal peaks
    Z += peak2d(s, s, 1.0)
for i, j in couplings:                    # symmetric cross-peaks
    Z += peak2d(shifts[i], shifts[j], 0.8)
    Z += peak2d(shifts[j], shifts[i], 0.8)

fig, ax = plt.subplots(figsize=(5.4, 5.0))
levels = np.linspace(0.08, 1.0, 10)
cs = ax.contour(X, Y, Z, levels=levels, cmap="viridis", linewidths=0.9)
ax.plot(ppm, ppm, color="0.7", ls="--", lw=0.8)      # diagonal guide
for i, j in couplings:                                # annotate one cross-peak
    ax.annotate("cross-peak", xy=(shifts[i], shifts[j]),
                xytext=(shifts[i] - 0.9, shifts[j] + 0.4),
                fontsize=8, color=ACC,
                arrowprops=dict(arrowstyle="->", color=ACC, lw=1.0))
ax.set_xlabel(r"$\delta_2$ (ppm)")
ax.set_ylabel(r"$\delta_1$ (ppm)")
ax.set_title("2D COSY correlation map")
ax.set_aspect("equal")
ax.invert_xaxis()                        # both ppm axes decrease outward
ax.invert_yaxis()
fig.colorbar(cs, ax=ax, label="intensity (arb.)", shrink=0.85)
fig.tight_layout()
fig
'''


def _cosy_2d():
    return [_md(_COSY_INTRO), _code(_COSY)]


# -- Registry --------------------------------------------------------------

NMR_EXAMPLES = [
    # (name, category, builder)
    ("1H NMR Spectrum (NMR)", "NMR", _proton_nmr),
    ("FID to Spectrum (NMR)", "NMR", _fid_to_spectrum),
    ("NMR Peak Picking & Integration (NMR)", "NMR", _peak_picking),
    ("T1 Relaxation (NMR)", "NMR", _t1_relaxation),
    ("2D COSY (NMR)", "NMR", _cosy_2d),
]
