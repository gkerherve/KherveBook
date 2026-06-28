"""More ARPES examples built on the ``peaks`` library's sample data.

A self-contained companion to ``examples.py`` (Examples menu,
"Spectroscopy" category) and ``examples_arpes.py``. ``peaks``
(``pip install peaks-arpes``) is the angle-resolved photoemission
toolkit from the King group at the University of St Andrews; it ships
Diamond Light Source beamline-I05 scans through
``peaks.core.utils.sample_data.ExampleData`` — a Fermi-surface map
(``ExampleData.FS()``, ``i05-59818.nxs``) and a dispersion
(``ExampleData.dispersion()``, ``i05-59819.nxs``).

Three examples are exported here:

* **Fermi Surface** — a constant-energy map of the photoemission
  intensity (a Fermi-surface cut).
* **Angle to Momentum** — the angle-to-k conversion that turns an
  emission-angle axis into a parallel-momentum axis.
* **Band Curvature** — the 2-D curvature trick that sharpens faint
  bands in an ARPES dispersion.

Each code cell uses the real ``peaks`` data when the library is
installed and otherwise synthesises faithful data with NumPy so the
example always runs offline. This module defines its own
``_md``/``_code`` helpers and exports ``ARPES_BANDS_EXAMPLES`` so it
merges into ``examples.py`` without a circular import.

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


# -- 1. Fermi surface ------------------------------------------------------

_FS_INTRO = """\
# ARPES Fermi surface with the `peaks` library

A **Fermi surface** is the locus of electronic states at the Fermi
energy *E*<sub>F</sub> — in ARPES it is a *constant-energy map* of the
photoemission intensity in the (*k<sub>x</sub>*, *k<sub>y</sub>*) plane.

[`peaks`](https://github.com/phrgab/peaks) ships a **Diamond Light
Source** beamline-**I05** Fermi-surface scan. The canonical way to load
and slice it is:

```python
import peaks as pks
from peaks.core.utils.sample_data import ExampleData
fs = ExampleData.FS()                       # downloads i05-59818.nxs
cem = fs.sel(eV=slice(-0.02, 0.02)).mean("eV")   # constant-energy map
cem.plot()                                  # the Fermi surface
```

The FS data has dimensions `eV`, `theta_par` and `polar`; averaging a
thin `eV` window around *E*<sub>F</sub> gives the Fermi-surface cut.
Install it with `pip install peaks-arpes`. The cell below uses that real
data when `peaks` is available, and otherwise synthesises a faithful
circular Fermi surface so the example always runs.
"""


_FS_CODE = r'''
# ARPES Fermi-surface map from the `peaks` library's bundled FS scan.
# peaks ships a Diamond Light Source I05 measurement, i05-59818.nxs, via
# ExampleData.FS(); a constant-energy map is fs.sel(eV=slice(-0.02, 0.02))
# .mean("eV"). If peaks isn't installed we synthesise a faithful circular
# Fermi surface so the example still produces a real constant-energy map.
import numpy as np
import matplotlib.pyplot as plt


def load_fermi_surface():
    """Return (kx, ky, intensity[ky, kx], source)."""
    try:
        import peaks as pks                                  # noqa: F401
        from peaks.core.utils.sample_data import ExampleData
        fs = ExampleData.FS()                  # downloads i05-59818.nxs
        cem = fs.sel(eV=slice(-0.02, 0.02)).mean("eV")  # constant-energy map
        try:
            inten = np.asarray(cem.pint.magnitude, dtype=float)
        except Exception:
            inten = np.asarray(cem.values, dtype=float)
        kx = np.asarray(cem["theta_par"].values, dtype=float)
        ky = np.asarray(cem["polar"].values, dtype=float)
        if inten.shape != (ky.size, kx.size):
            inten = inten.T
        return kx, ky, inten, "peaks data - Diamond I05 (i05-59818.nxs)"
    except Exception:
        rng = np.random.default_rng(0)
        kx = np.linspace(-1.2, 1.2, 220)        # 1/Angstrom
        ky = np.linspace(-1.2, 1.2, 220)
        KX, KY = np.meshgrid(kx, ky)
        kmag = np.hypot(KX, KY)
        kF = 0.8                                 # Fermi wavevector
        gamma = 0.04                             # contour broadening
        # Lorentzian ring at |k| = kF plus a faint replica band.
        ring = (gamma / np.pi) / ((kmag - kF) ** 2 + gamma ** 2)
        replica = 0.25 * (gamma / np.pi) / ((kmag - 0.45) ** 2 + gamma ** 2)
        inten = ring + replica + 0.05           # low background
        inten = inten / inten.max() + 0.02 * rng.random(inten.shape)
        return kx, ky, inten, "synthetic Fermi surface (pip install peaks-arpes)"


kx, ky, I, source = load_fermi_surface()

fig, ax = plt.subplots(figsize=(5.2, 4.6))
pm = ax.pcolormesh(kx, ky, I, cmap="inferno", shading="auto")
ax.set_aspect("equal")
ax.set_xlabel(r"$k_x$ (1/$\AA$)")
ax.set_ylabel(r"$k_y$ (1/$\AA$)")
ax.set_title("Fermi surface map")
fig.colorbar(pm, ax=ax, label="intensity (arb.)")
fig.text(0.01, 0.005, source, fontsize=7, color="0.45")
fig.tight_layout()
fig
'''


def _arpes_fermi_surface():
    return [_md(_FS_INTRO), _code(_FS_CODE)]


# -- 2. Angle to momentum --------------------------------------------------

_K_INTRO = """\
# ARPES angle-to-momentum conversion

ARPES analysers record intensity versus **emission angle**, but band
structure lives in **crystal momentum** *k*. The parallel momentum of a
photoelectron is

> *k*<sub>∥</sub> = 0.5123 · √(*E*<sub>kin</sub> / eV) · sin θ&nbsp;&nbsp;
> (units of 1/Å)

where *E*<sub>kin</sub> is the photoelectron kinetic energy (the photon
energy minus the work function and binding energy, here *E*<sub>kin</sub>
≈ 16 eV) and θ is the emission angle.

[`peaks`](https://github.com/phrgab/peaks) performs this **k-conversion**
(angle-to-k) automatically — e.g. `disp.k_convert()` returns the
dispersion on a `k_par` axis. The cell below shows the same parabolic
band twice: as measured (E vs emission angle) and after converting the
angle axis to *k*<sub>∥</sub>. Note how the band narrows near normal
emission and stretches at large angle once the sin θ mapping is applied.
"""


_K_CODE = r'''
# Angle-to-momentum (k) conversion of an ARPES dispersion.
# k_par = 0.5123 * sqrt(Ekin_eV) * sin(theta) with Ekin set by the photon
# energy minus the work function. peaks does this conversion automatically
# (disp.k_convert()); here we apply it by hand to a synthetic parabolic
# band so the example always runs.
import numpy as np
import matplotlib.pyplot as plt

rng = np.random.default_rng(0)
theta = np.linspace(-16, 16, 220)               # emission angle (deg)
E = np.linspace(-0.70, 0.10, 300)               # E - E_F (eV)
TH, EE = np.meshgrid(theta, E)
band = -0.45 + 0.0045 * TH ** 2                 # parabolic band minimum
gamma = 0.02 + 0.05 * band ** 2                 # lifetime broadening
spectral = (gamma / np.pi) / ((EE - band) ** 2 + gamma ** 2)
fermi = 1.0 / (np.exp(EE / 0.012) + 1.0)        # Fermi-Dirac cut-off
I = spectral * fermi
I = I / I.max() + 0.02 * rng.random(I.shape)

# Convert the emission-angle axis to parallel momentum (1/Angstrom).
Ekin = 16.0                                      # photoelectron kinetic energy (eV)
k_par = 0.5123 * np.sqrt(Ekin) * np.sin(np.deg2rad(theta))

fig, (a1, a2) = plt.subplots(1, 2, figsize=(8.0, 3.8))

pm1 = a1.pcolormesh(theta, E, I, cmap="inferno", shading="auto")
a1.axhline(0, color="w", ls="--", lw=0.8, alpha=0.7)
a1.set_xlabel(r"emission angle  $\theta_\parallel$  (deg)")
a1.set_ylabel(r"$E - E_F$  (eV)")
a1.set_title("measured: E vs angle")
fig.colorbar(pm1, ax=a1, label="intensity (arb.)")

pm2 = a2.pcolormesh(k_par, E, I, cmap="inferno", shading="auto")
a2.axhline(0, color="w", ls="--", lw=0.8, alpha=0.7)
a2.set_xlabel(r"$k_\parallel$  (1/$\AA$)")
a2.set_ylabel(r"$E - E_F$  (eV)")
a2.set_title("converted: E vs $k_\\parallel$")
fig.colorbar(pm2, ax=a2, label="intensity (arb.)")

fig.text(0.01, 0.005, r"$k_\parallel = 0.5123\,\sqrt{E_{kin}}\,\sin\theta$,"
         r"  $E_{kin} = 16$ eV", fontsize=8, color="0.45")
fig.tight_layout()
fig
'''


def _arpes_angle_to_k():
    return [_md(_K_INTRO), _code(_K_CODE)]


# -- 3. Band curvature -----------------------------------------------------

_CURV_INTRO = """\
# ARPES band curvature (second-derivative) enhancement

Faint bands in an ARPES dispersion are often sharpened by taking a
**curvature** or **second-derivative** of the intensity — a standard
analysis trick that suppresses the smooth background and highlights peak
positions. A simple energy curvature is

> *C* = −∂²*I* / ∂*E*²&nbsp;&nbsp; (negative values clipped to zero)

so that intensity maxima (band positions) become bright ridges.

[`peaks`](https://github.com/phrgab/peaks) provides processing tools for
exactly this — **gradient** and **curvature** operators that run over the
energy or momentum axis of a dispersion. The cell below applies the
energy second-derivative by hand (`np.gradient` twice) to a synthetic
parabolic band, showing the raw dispersion next to its curvature.
"""


_CURV_CODE = r'''
# Band-curvature enhancement of an ARPES dispersion.
# C = -d2I/dE2 (np.gradient twice along the energy axis), negatives clipped.
# This standard ARPES trick sharpens faint bands; peaks ships gradient and
# curvature processing tools that do the same over a real dispersion. Here
# we build a synthetic parabolic band so the example always runs.
import numpy as np
import matplotlib.pyplot as plt

rng = np.random.default_rng(0)
theta = np.linspace(-16, 16, 220)               # emission angle (deg)
E = np.linspace(-0.70, 0.10, 300)               # E - E_F (eV)
TH, EE = np.meshgrid(theta, E)
band = -0.45 + 0.0045 * TH ** 2                 # parabolic band minimum
gamma = 0.02 + 0.05 * band ** 2                 # lifetime broadening
spectral = (gamma / np.pi) / ((EE - band) ** 2 + gamma ** 2)
fermi = 1.0 / (np.exp(EE / 0.012) + 1.0)        # Fermi-Dirac cut-off
I = spectral * fermi
I = I / I.max() + 0.02 * rng.random(I.shape)

# Second derivative along the energy axis (axis 0), then clip negatives.
dIdE = np.gradient(I, E, axis=0)
d2IdE2 = np.gradient(dIdE, E, axis=0)
curv = np.clip(-d2IdE2, 0, None)                # curvature enhancement

fig, (a1, a2) = plt.subplots(1, 2, figsize=(8.0, 3.8))

pm1 = a1.pcolormesh(theta, E, I, cmap="inferno", shading="auto")
a1.axhline(0, color="w", ls="--", lw=0.8, alpha=0.7)
a1.set_xlabel(r"emission angle  $\theta_\parallel$  (deg)")
a1.set_ylabel(r"$E - E_F$  (eV)")
a1.set_title("raw dispersion")
fig.colorbar(pm1, ax=a1, label="intensity (arb.)")

pm2 = a2.pcolormesh(theta, E, curv, cmap="viridis", shading="auto")
a2.axhline(0, color="w", ls="--", lw=0.8, alpha=0.7)
a2.set_xlabel(r"emission angle  $\theta_\parallel$  (deg)")
a2.set_ylabel(r"$E - E_F$  (eV)")
a2.set_title(r"curvature  $-\partial^2 I / \partial E^2$")
fig.colorbar(pm2, ax=a2, label="curvature (arb.)")

fig.tight_layout()
fig
'''


def _arpes_band_curvature():
    return [_md(_CURV_INTRO), _code(_CURV_CODE)]


# -- Registry --------------------------------------------------------------

ARPES_BANDS_EXAMPLES = [
    # (name, category, builder)
    ("ARPES Fermi Surface (peaks)", "Spectroscopy", _arpes_fermi_surface),
    ("Angle to Momentum (peaks)", "Spectroscopy", _arpes_angle_to_k),
    ("Band Curvature (peaks)", "Spectroscopy", _arpes_band_curvature),
]
