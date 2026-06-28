"""SIMS (secondary-ion mass spectrometry) examples.

A self-contained companion to ``examples.py`` (Examples menu, "SIMS"
category). SIMS sputters a sample with a focused primary-ion beam and
mass-analyses the **secondary ions** ejected from the surface, giving
trace-level depth profiles, mass spectra and isotope ratios.

[`pySPM`](https://github.com/scholi/pySPM) (``pip install pySPM``) is an
open-source Python toolkit for **ToF-SIMS** and scanning-probe data: it
reads Iontof ``.ITM``/``.ITA`` files, calibrates the mass axis, extracts
peaks and reconstructs depth profiles and images. The cells below
reference its API in the markdown but use **synthetic** NumPy data so the
examples always run offline.

This module defines its own ``_md``/``_code`` helpers and exports
``SIMS_EXAMPLES`` so it merges into ``examples.py`` without a circular
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


# -- 1. Depth profile -----------------------------------------------------

_DEPTH_INTRO = """\
# SIMS depth profile

A **SIMS depth profile** records secondary-ion counts while the primary
beam slowly sputters into the sample, so the time axis converts to
**depth** and the count axis tracks the **concentration** of a chosen
species. The classic example is a **boron implant in silicon**: ion
implantation buries a roughly **Gaussian** dopant distribution at a depth
set by the implant energy, and the first few nanometres show a **surface
transient** while the sputtering reaches steady state. Because the dopant
spans several decades the profile is always plotted on a **log** count
axis.

With [`pySPM`](https://github.com/scholi/pySPM) a real Iontof depth
profile is a few calls:

```python
import pySPM
ita = pySPM.ITA("implant.ita")            # ToF-SIMS depth-profile file
t, counts = ita.get_profile_by_mass(11)   # B+ at m/z = 11
depth = t * sputter_rate                   # nm, from a measured crater
```

Install it with `pip install pySPM`. The cell below synthesises a boron
implant profile (buried Gaussian + surface transient + background) so it
always runs, and annotates the fitted **peak depth**.
"""


_DEPTH_PROFILE = r'''
# Synthetic SIMS depth profile of a boron implant in silicon:
#   buried Gaussian implant + decaying surface transient + flat background.
# With pySPM this would come from ITA.get_profile_by_mass(); here it is
# synthesised so the example always runs. Plotted on a log count axis.
import numpy as np
import matplotlib.pyplot as plt

rng = np.random.default_rng(0)

depth = np.linspace(0.0, 400.0, 400)        # sputter depth (nm)

# Buried Gaussian implant (B in Si): peak depth Rp, straggle dRp.
Rp, dRp = 120.0, 35.0                        # projected range / straggle (nm)
peak_conc = 1.0e19                           # peak concentration (cm^-3)
implant = peak_conc * np.exp(-0.5 * ((depth - Rp) / dRp) ** 2)

# Surface transient: extra counts in the first few nm before steady state.
transient = 4.0e18 * np.exp(-depth / 8.0)

# Matrix background / detection floor.
background = 5.0e15

clean = implant + transient + background
# Multiplicative (counting) noise keeps the profile strictly positive.
counts = clean * rng.lognormal(mean=0.0, sigma=0.06, size=depth.size)
counts = np.clip(counts, 1.0e15, None)       # stay positive for log axis

# Peak depth from the implant region (ignore the surface transient).
buried = depth > 30.0
peak_depth = depth[buried][int(np.argmax(counts[buried]))]

fig, ax = plt.subplots(figsize=(5.8, 4.3))
ax.semilogy(depth, counts, color="#3776ab", lw=1.6, label="B in Si")
ax.axvline(peak_depth, color="#e07b39", ls="--", lw=1.4)
ax.annotate(r"implant peak $\approx$ %.0f nm" % peak_depth,
            xy=(peak_depth, counts[buried].max()),
            xytext=(peak_depth + 40.0, counts.max() * 0.5),
            color="#e07b39", fontsize=9,
            arrowprops=dict(arrowstyle="->", color="#e07b39"))
ax.set_xlabel(r"depth (nm)")
ax.set_ylabel(r"concentration (cm$^{-3}$)")
ax.set_title("SIMS depth profile: B implant in Si")
ax.set_yscale("log")
ax.set_ylim(1.0e15, 3.0e19)
ax.legend(loc="upper right", frameon=False)
fig.text(0.01, 0.005, "synthetic profile (pip install pySPM)",
         fontsize=7, color="0.45")
fig.tight_layout()
fig
'''


def _depth_profile():
    return [_md(_DEPTH_INTRO), _code(_DEPTH_PROFILE)]


# -- 2. Mass spectrum -----------------------------------------------------

_MASS_INTRO = """\
# SIMS mass spectrum

A **SIMS mass spectrum** plots secondary-ion intensity versus
**mass-to-charge ratio** *m/z*. Each element appears as a cluster of peaks
whose pattern is fixed by the **natural isotope abundances**, so the
fingerprint identifies the species. Boron is the textbook case: it has two
stable isotopes, **10B (~19.9%)** and **11B (~80.1%)**, so its doublet
shows a ~4:1 height ratio. Heavier matrix and cluster ions (here Si and
Si2) sit at higher *m/z*.

With [`pySPM`](https://github.com/scholi/pySPM) the calibrated spectrum
and its peaks come straight from the file:

```python
import pySPM
ita = pySPM.ITA("sample.ita")
masses, spectrum = ita.get_spectrum()      # calibrated m/z axis
ita.show_masses()                          # list assigned peaks
```

Install it with `pip install pySPM`. The cell below builds a synthetic
spectrum with correct B isotope ratios and labels the key peaks.
"""


_MASS_SPECTRUM = r'''
# Synthetic SIMS mass spectrum with correct isotope patterns.
# Boron doublet (10B ~19.9%, 11B ~80.1%) plus Si and Si2 cluster peaks.
# With pySPM this is ITA.get_spectrum(); here it is synthesised so the
# example always runs. Drawn as a stem plot of intensity vs m/z.
import numpy as np
import matplotlib.pyplot as plt

rng = np.random.default_rng(0)

# (m/z, relative intensity, label) for each secondary-ion peak.
peaks = [
    (10.0, 0.199, r"$^{10}$B"),     # boron-10
    (11.0, 0.801, r"$^{11}$B"),     # boron-11
    (28.0, 1.000, r"$^{28}$Si"),    # silicon-28 (matrix)
    (29.0, 0.051, r"$^{29}$Si"),    # silicon-29
    (56.0, 0.300, r"Si$_2$"),       # silicon dimer cluster
]
mz = np.array([p[0] for p in peaks])
inten = np.array([p[1] for p in peaks])
inten = inten * rng.lognormal(mean=0.0, sigma=0.02, size=inten.size)

fig, ax = plt.subplots(figsize=(6.2, 4.2))
markerline, stemlines, baseline = ax.stem(mz, inten, basefmt=" ")
plt.setp(stemlines, color="#3776ab", linewidth=1.8)
plt.setp(markerline, color="#3776ab", markersize=5)
for (m, _, lab), y in zip(peaks, inten):
    ax.annotate(lab, xy=(m, y), xytext=(0, 4),
                textcoords="offset points", ha="center",
                fontsize=9, color="#e07b39")
ax.set_xlabel(r"$m/z$")
ax.set_ylabel(r"intensity (arb.)")
ax.set_title("SIMS mass spectrum (B-doped Si)")
ax.set_xlim(5.0, 62.0)
ax.set_ylim(0.0, inten.max() * 1.18)
fig.text(0.01, 0.005, "synthetic spectrum (pip install pySPM)",
         fontsize=7, color="0.45")
fig.tight_layout()
fig
'''


def _mass_spectrum():
    return [_md(_MASS_INTRO), _code(_MASS_SPECTRUM)]


# -- 3. Isotope ratios ----------------------------------------------------

_RATIO_INTRO = """\
# SIMS isotope ratios

SIMS measures **isotope ratios** by integrating the peaks of two isotopes
of the same element and dividing the areas. Boron's two isotopes, **11B**
and **10B**, have a natural abundance ratio of about **80.1 / 19.9 = 4.03**;
a measured ratio that departs from this signals isotopic enrichment (or
instrumental mass fractionation). The peaks are integrated over a small
*m/z* window rather than read at the apex, because peak shape and detector
dead-time shift the apex.

With [`pySPM`](https://github.com/scholi/pySPM) peak areas come from the
spectrum object:

```python
import pySPM
ita = pySPM.ITA("sample.ita")
A10 = ita.get_peak_area(10)               # integrate around m/z = 10
A11 = ita.get_peak_area(11)               # integrate around m/z = 11
ratio = A11 / A10                          # 11B / 10B
```

Install it with `pip install pySPM`. The cell below builds the boron
doublet as two Gaussian peaks, integrates each, and compares the measured
**11B/10B** ratio with the natural-abundance value.
"""


_ISOTOPE_RATIO = r'''
# Synthetic boron isotope doublet; integrate each peak to get 11B / 10B and
# compare with the natural-abundance ratio. With pySPM the areas come from
# ITA.get_peak_area(); here the doublet is synthesised so it always runs.
import numpy as np
import matplotlib.pyplot as plt

rng = np.random.default_rng(0)

# Natural abundances of the two boron isotopes.
ab10, ab11 = 0.199, 0.801
natural_ratio = ab11 / ab10                  # ~4.03

mz = np.linspace(8.5, 12.5, 800)             # m/z axis around the doublet
sigma = 0.06                                 # peak width (m/z)


def gauss(x, area, cen, sig):
    """Area-normalised Gaussian peak."""
    return area / (sig * np.sqrt(2.0 * np.pi)) * np.exp(
        -0.5 * ((x - cen) / sig) ** 2)


# True peak areas proportional to abundance; add a small detection floor.
true_area10, true_area11 = ab10, ab11
spectrum = (gauss(mz, true_area10, 10.0, sigma)
            + gauss(mz, true_area11, 11.0, sigma))
spectrum = spectrum * rng.lognormal(mean=0.0, sigma=0.02, size=mz.size)
spectrum = np.clip(spectrum, 0.0, None)

# Integrate each peak over a +/- 0.3 m/z window (trapezoid rule).
def integrate(win_lo, win_hi):
    sel = (mz >= win_lo) & (mz <= win_hi)
    return np.trapz(spectrum[sel], mz[sel])


area10 = integrate(9.7, 10.3)
area11 = integrate(10.7, 11.3)
measured_ratio = area11 / area10

fig, ax = plt.subplots(figsize=(6.0, 4.2))
ax.plot(mz, spectrum, color="#3776ab", lw=1.6)
ax.fill_between(mz, spectrum, where=(mz >= 9.7) & (mz <= 10.3),
                color="#50bea0", alpha=0.5)
ax.fill_between(mz, spectrum, where=(mz >= 10.7) & (mz <= 11.3),
                color="#e07b39", alpha=0.5)
ax.annotate(r"$^{10}$B", xy=(10.0, gauss(10.0, true_area10, 10.0, sigma)),
            xytext=(0, 4), textcoords="offset points",
            ha="center", fontsize=10, color="#50bea0")
ax.annotate(r"$^{11}$B", xy=(11.0, gauss(11.0, true_area11, 11.0, sigma)),
            xytext=(0, 4), textcoords="offset points",
            ha="center", fontsize=10, color="#e07b39")
ax.set_xlabel(r"$m/z$")
ax.set_ylabel(r"intensity (arb.)")
ax.set_title("SIMS isotope ratio: $^{11}$B / $^{10}$B")
ax.text(0.03, 0.95,
        r"measured $^{11}$B/$^{10}$B $= %.2f$" % measured_ratio + "\n"
        + r"natural $= %.2f$" % natural_ratio,
        transform=ax.transAxes, va="top", fontsize=9,
        bbox=dict(boxstyle="round", fc="white", ec="0.8"))
fig.text(0.01, 0.005, "synthetic doublet (pip install pySPM)",
         fontsize=7, color="0.45")
fig.tight_layout()
fig
'''


def _isotope_ratio():
    return [_md(_RATIO_INTRO), _code(_ISOTOPE_RATIO)]


# -- 4. RSF quantification ------------------------------------------------

_RSF_INTRO = """\
# SIMS RSF quantification

Raw SIMS counts are not concentrations: ionisation efficiency varies by
orders of magnitude between elements. The standard fix is a **relative
sensitivity factor (RSF)**, calibrated from an implant standard, that
converts the dopant-to-matrix intensity ratio into concentration:

$$ C = \\mathrm{RSF} \\times \\frac{I_\\mathrm{dopant}}{I_\\mathrm{matrix}} $$

Integrating the concentration over depth then gives the **implanted dose**
in atoms cm$^{-2}$ — the quantity an implanter is specified by:

$$ \\mathrm{dose} = \\int C(z)\\,dz $$

With [`pySPM`](https://github.com/scholi/pySPM) you extract the dopant and
matrix profiles, apply your RSF, and integrate:

```python
import pySPM, numpy as np
ita = pySPM.ITA("implant.ita")
_, I_dop = ita.get_profile_by_mass(11)     # B+
_, I_mat = ita.get_profile_by_mass(30)     # Si matrix
C = RSF * I_dop / I_mat                      # cm^-3
dose = np.trapz(C, depth_cm)                 # atoms cm^-2
```

Install it with `pip install pySPM`. The cell below converts a synthetic
boron profile to concentration with an RSF and integrates it to the dose.
"""


_RSF_QUANT = r'''
# RSF quantification: convert dopant/matrix intensity to concentration via
# C = RSF * (I_dopant / I_matrix), then integrate over depth to get the
# implanted dose (atoms / cm^2). With pySPM the profiles come from
# get_profile_by_mass(); here they are synthesised so it always runs.
import numpy as np
import matplotlib.pyplot as plt

rng = np.random.default_rng(0)

depth_nm = np.linspace(0.0, 400.0, 400)      # depth (nm)
depth_cm = depth_nm * 1.0e-7                  # nm -> cm for the dose integral

# Matrix (Si) secondary-ion intensity: roughly constant counts.
I_matrix = 1.0e6 * rng.lognormal(mean=0.0, sigma=0.02, size=depth_nm.size)

# Dopant (B) intensity: buried Gaussian implant + surface transient + floor.
Rp, dRp = 120.0, 35.0                         # projected range / straggle (nm)
implant = 8.0e3 * np.exp(-0.5 * ((depth_nm - Rp) / dRp) ** 2)
transient = 3.0e3 * np.exp(-depth_nm / 8.0)
I_dopant = (implant + transient + 5.0) * rng.lognormal(
    mean=0.0, sigma=0.05, size=depth_nm.size)

# Relative sensitivity factor for B in Si (calibrated from a standard).
RSF = 2.0e22                                  # atoms cm^-3 per unit ratio

# Concentration from the intensity ratio, then the dose by integration.
conc = RSF * (I_dopant / I_matrix)            # cm^-3
conc = np.clip(conc, 1.0e15, None)            # stay positive for log axis
dose = np.trapz(conc, depth_cm)               # atoms / cm^2

peak_depth = depth_nm[int(np.argmax(implant))]

fig, ax = plt.subplots(figsize=(5.9, 4.3))
ax.semilogy(depth_nm, conc, color="#3776ab", lw=1.6, label="B in Si")
ax.axvline(peak_depth, color="#e07b39", ls="--", lw=1.2)
ax.set_xlabel(r"depth (nm)")
ax.set_ylabel(r"concentration (cm$^{-3}$)")
ax.set_title("SIMS RSF quantification: B implant dose")
ax.set_yscale("log")
ax.set_ylim(1.0e15, 1.0e20)
ax.text(0.97, 0.95,
        r"RSF $= %.0e$" % RSF + "\n"
        + r"dose $= %.2e$ cm$^{-2}$" % dose,
        transform=ax.transAxes, va="top", ha="right", fontsize=9,
        bbox=dict(boxstyle="round", fc="white", ec="0.8"))
ax.legend(loc="upper left", frameon=False)
fig.text(0.01, 0.005, "synthetic profile (pip install pySPM)",
         fontsize=7, color="0.45")
fig.tight_layout()
fig
'''


def _rsf_quant():
    return [_md(_RSF_INTRO), _code(_RSF_QUANT)]


# -- Registry --------------------------------------------------------------

SIMS_EXAMPLES = [
    # (name, category, builder)
    ("SIMS Depth Profile (SIMS)", "SIMS", _depth_profile),
    ("SIMS Mass Spectrum (SIMS)", "SIMS", _mass_spectrum),
    ("SIMS Isotope Ratios (SIMS)", "SIMS", _isotope_ratio),
    ("SIMS RSF Quantification (SIMS)", "SIMS", _rsf_quant),
]
