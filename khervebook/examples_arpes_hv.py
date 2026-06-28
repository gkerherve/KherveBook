"""Photon-energy / data-product ARPES examples on ``peaks`` sample data.

A self-contained companion to ``examples.py`` (Examples menu,
"ARPES" category) and the other ``examples_arpes*`` modules.
``peaks`` (``pip install peaks-arpes``) is the angle-resolved
photoemission toolkit from the King group at the University of St
Andrews; it ships Diamond Light Source beamline-I05 scans through
``peaks.core.utils.sample_data.ExampleData`` — including a
photon-energy dependence (``ExampleData.hv_map()``, ``i05-69294.nxs``)
and nano-ARPES focus scans with and without I0 flux normalisation
(``ExampleData.nano_focus()`` / ``ExampleData.nano_focus_w_I0norm()``).

Three "data product" examples are exported here:

* **Photon-Energy Scan / kz** — a normal-emission photon-energy
  dependence; the band's periodic dispersion versus *hv* maps out the
  out-of-plane momentum *k*<sub>z</sub> (free-electron final state,
  inner potential *V*<sub>0</sub>).
* **I0 Flux Normalization** — dividing the raw ARPES intensity by the
  incident photon flux *I*<sub>0</sub> to remove beam and
  monochromator drift.
* **Constant-Energy Map Stack** — a stack of constant-energy cuts
  through a 3-D *I*(*k<sub>x</sub>*, *k<sub>y</sub>*, *E*) dataset whose
  contours evolve with binding energy.

Each code cell uses the real ``peaks`` data when the library is
installed and otherwise synthesises faithful data with NumPy so the
example always runs offline. This module defines its own
``_md``/``_code`` helpers and exports ``ARPES_HV_EXAMPLES`` so it
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


# -- 1. Photon-energy scan / kz --------------------------------------------

_HV_INTRO = """\
# ARPES photon-energy scan and *k*<sub>z</sub>

Varying the **photon energy** *hv* at normal emission changes the
photoelectron kinetic energy and therefore the **out-of-plane
momentum** *k*<sub>z</sub> being probed. In the free-electron
final-state model

> *k*<sub>z</sub> = 0.5123 · √(*E*<sub>kin</sub> · cos²θ + *V*<sub>0</sub>)

where *V*<sub>0</sub> is the **inner potential** and *E*<sub>kin</sub>
is the kinetic energy (*hv* minus the work function and binding
energy). A band that disperses along *k*<sub>z</sub> shows up as a
**periodic** modulation of its binding energy as *hv* is scanned —
the period fixes the *c*-axis lattice constant and *V*<sub>0</sub>.

[`peaks`](https://github.com/phrgab/peaks) ships a **Diamond Light
Source** beamline-**I05** photon-energy dependence:

```python
import peaks as pks
from peaks.core.utils.sample_data import ExampleData
hv = ExampleData.hv_map()                   # downloads i05-69294.nxs
hv.plot()                                   # intensity vs (hv, E)
```

Install it with `pip install peaks-arpes`. The cell below uses that real
data when `peaks` is available, and otherwise synthesises a faithful
*k*<sub>z</sub>-dispersing band so the example always runs.
"""


_HV_CODE = r'''
# ARPES photon-energy (hv) scan at normal emission -> out-of-plane k_z.
# peaks ships a Diamond Light Source I05 measurement, i05-69294.nxs, via
# ExampleData.hv_map(). If peaks isn't installed we synthesise a band whose
# normal-emission binding energy disperses periodically with k_z so the
# example still produces a real photon-energy map.
import numpy as np
import matplotlib.pyplot as plt

WORKFN = 4.5            # analyser work function (eV)
V0 = 12.0              # inner potential (eV)


def kz_from_hv(hv, E_bind):
    """Free-electron final-state out-of-plane momentum (1/Angstrom)."""
    Ekin = hv - WORKFN + E_bind          # E_bind <= 0 below E_F
    return 0.5123 * np.sqrt(np.clip(Ekin + V0, 0, None))


def load_hv_map():
    """Return (hv, E_minus_EF, intensity[E, hv], source)."""
    try:
        import peaks as pks                                  # noqa: F401
        from peaks.core.utils.sample_data import ExampleData
        d = ExampleData.hv_map()               # downloads i05-69294.nxs
        try:
            inten = np.asarray(d.pint.magnitude, dtype=float)
        except Exception:
            inten = np.asarray(d.values, dtype=float)
        e_ax = np.asarray(d["eV"].values, dtype=float)
        hv_ax = np.asarray(d["hv"].values, dtype=float)
        if inten.shape != (e_ax.size, hv_ax.size):
            inten = inten.T
        return hv_ax, e_ax, inten, "peaks data - Diamond I05 (i05-69294.nxs)"
    except Exception:
        rng = np.random.default_rng(0)
        hv = np.linspace(20.0, 100.0, 240)      # photon energy (eV)
        E = np.linspace(-0.80, 0.10, 320)       # E - E_F (eV)
        HV, EE = np.meshgrid(hv, E)
        kz = kz_from_hv(hv, 0.0)                 # k_z at the band energy
        E0, A, c = -0.35, 0.18, 3.6             # offset, amplitude, c-axis
        E_band = E0 - A * np.cos(c * kz)         # periodic k_z dispersion
        gamma = 0.05                             # lifetime broadening
        spectral = (gamma / np.pi) / ((EE - E_band[None, :]) ** 2 + gamma ** 2)
        fermi = 1.0 / (np.exp(EE / 0.012) + 1.0)  # Fermi-Dirac cut-off
        inten = spectral * fermi
        inten = inten / inten.max() + 0.02 * rng.random(inten.shape)
        return hv, E, inten, "synthetic hv scan (pip install peaks-arpes)"


hv, E, I, source = load_hv_map()

fig, ax = plt.subplots(figsize=(5.8, 4.4))
pm = ax.pcolormesh(hv, E, I, cmap="inferno", shading="auto")
ax.axhline(0, color="w", ls="--", lw=0.8, alpha=0.7)        # Fermi level
ax.set_xlabel(r"$h\nu$ (eV)")
ax.set_ylabel(r"$E - E_F$ (eV)")
ax.set_title("Photon-energy scan (normal emission)")
fig.colorbar(pm, ax=ax, label="intensity (arb.)")
fig.text(0.01, 0.005,
         r"periodic dispersion vs $h\nu$ gives $k_z$ "
         r"(free-electron final state, $V_0 = %g$ eV)" % V0,
         fontsize=7.5, color="0.45")
fig.tight_layout()
fig
'''


def _arpes_hv_scan():
    return [_md(_HV_INTRO), _code(_HV_CODE)]


# -- 2. I0 flux normalization ----------------------------------------------

_I0_INTRO = """\
# ARPES I0 flux normalization

The intensity recorded in an ARPES scan rides on top of the **incident
photon flux** *I*<sub>0</sub> — measured by a mesh or diode current —
which drifts as the monochromator and storage-ring beam move. Dividing
the raw spectrum by *I*<sub>0</sub>,

> *I*<sub>norm</sub>(*E*) = *I*<sub>raw</sub>(*E*) / *I*<sub>0</sub>(*E*)

removes that envelope and restores a flat baseline, so peak intensities
are comparable across the scan.

[`peaks`](https://github.com/phrgab/peaks) ships **Diamond Light
Source** nano-ARPES focus scans both before and after this correction:

```python
import peaks as pks
from peaks.core.utils.sample_data import ExampleData
raw = ExampleData.nano_focus()              # without I0 normalisation
norm = ExampleData.nano_focus_w_I0norm()    # divided by I0 flux
```

Install it with `pip install peaks-arpes`. The cell below synthesises a
true spectrum, multiplies it by a smooth *I*<sub>0</sub>(*E*)
throughput to make the raw measurement, then divides it back out so the
example always runs.
"""


_I0_CODE = r'''
# I0 flux normalization of an ARPES spectrum.
# I_norm = I_raw / I0 removes the incident-flux envelope (mesh/diode
# current) so peak heights are comparable. peaks ships nano-ARPES focus
# scans with and without this (ExampleData.nano_focus() vs
# .nano_focus_w_I0norm()). Here we build a true spectrum, multiply by a
# smooth I0(E) throughput to make the raw scan, then divide it back out.
import numpy as np
import matplotlib.pyplot as plt

rng = np.random.default_rng(0)
E = np.linspace(-2.0, 0.3, 600)                 # E - E_F (eV)


def lorentz(x, x0, g):
    return (g / np.pi) / ((x - x0) ** 2 + g ** 2)


# "True" spectrum: two quasiparticle peaks plus a Fermi edge.
true = (1.0 * lorentz(E, -0.35, 0.05)
        + 0.6 * lorentz(E, -1.10, 0.09)
        + 0.4 / (np.exp(E / 0.02) + 1.0)        # Fermi edge step
        + 0.05)                                  # flat background
true = true / true.max()

# Incident photon flux I0(E): a smooth broad monochromator throughput bump.
I0 = 0.6 + 0.5 * np.exp(-((E + 0.7) / 1.1) ** 2)

# Raw measured spectrum = true spectrum modulated by the flux envelope.
raw = true * I0 + 0.01 * rng.standard_normal(E.shape)

# Normalise back out the flux.
norm = raw / I0

fig, (a1, a2) = plt.subplots(1, 2, figsize=(8.2, 3.8))

a1.plot(E, raw, color="#3776ab", label="raw spectrum")
a1.set_xlabel(r"$E - E_F$ (eV)")
a1.set_ylabel("intensity (arb.)")
a1.set_title(r"raw scan modulated by $I_0$")
a1b = a1.twinx()
a1b.plot(E, I0, color="#e07b39", lw=1.4, ls="--", label=r"$I_0$ flux")
a1b.set_ylabel(r"$I_0$ flux (arb.)", color="#e07b39")
a1b.tick_params(axis="y", labelcolor="#e07b39")
h1, l1 = a1.get_legend_handles_labels()
h2, l2 = a1b.get_legend_handles_labels()
a1.legend(h1 + h2, l1 + l2, fontsize=8, loc="upper left")

a2.plot(E, norm, color="#3776ab")
a2.axhline(np.median(norm[E < -1.6]), color="#e07b39", ls="--", lw=1,
           label="restored baseline")
a2.set_xlabel(r"$E - E_F$ (eV)")
a2.set_ylabel("intensity (arb.)")
a2.set_title(r"$I_0$-normalized: $I_{raw} / I_0$")
a2.legend(fontsize=8, loc="upper left")

fig.tight_layout()
fig
'''


def _arpes_i0_norm():
    return [_md(_I0_INTRO), _code(_I0_CODE)]


# -- 3. Constant-energy map stack ------------------------------------------

_CE_INTRO = """\
# ARPES constant-energy map stack

A full ARPES measurement is a **3-D dataset** *I*(*k<sub>x</sub>*,
*k<sub>y</sub>*, *E*). Slicing it at a fixed binding energy gives a
**constant-energy (CE) map**; stacking several such maps shows how the
contours **evolve with energy**. For a parabolic band
*E*(*k*) = −0.5 + α·|*k*|² a CE cut at binding energy *E*<sub>b</sub> is
a **ring** of radius

> *r*(*E*<sub>b</sub>) = √((*E*<sub>b</sub> + 0.5) / α)

that shrinks toward the band bottom.

[`peaks`](https://github.com/phrgab/peaks) makes these stacks directly —
e.g. `peaks.plot_grid([...])` lays out CE maps at several binding
energies in a grid. The cell below builds a synthetic
*I*(*k<sub>x</sub>*, *k<sub>y</sub>*, *E*) and plots a 2×3 grid of CE
maps so the example always runs.
"""


_CE_CODE = r'''
# Constant-energy (CE) map stack from a 3-D ARPES dataset I(kx, ky, E).
# A parabolic band E(k) = -0.5 + alpha*|k|^2 gives a CE ring of radius
# r(Eb) = sqrt((Eb + 0.5)/alpha). peaks lays out such stacks with
# plot_grid([...]); here we build the cube and plot a 2x3 grid of CE maps
# so the example always runs.
import numpy as np
import matplotlib.pyplot as plt

rng = np.random.default_rng(0)
kx = np.linspace(-1.0, 1.0, 160)                # 1/Angstrom
ky = np.linspace(-1.0, 1.0, 160)
KX, KY = np.meshgrid(kx, ky)
kmag = np.hypot(KX, KY)

alpha = 1.0                                      # band curvature
band = -0.5 + alpha * kmag ** 2                 # E(k) parabolic band
gamma = 0.04                                     # energy broadening

# Six binding energies from the band bottom up to E_F.
energies = np.linspace(-0.5, 0.0, 6)

fig, axes = plt.subplots(2, 3, figsize=(8.6, 5.8))
for ax, Eb in zip(axes.ravel(), energies):
    # CE slice: Lorentzian of (Eb - E(k)) -> a ring where the band crosses Eb.
    ce = (gamma / np.pi) / ((Eb - band) ** 2 + gamma ** 2)
    ce = ce / ce.max() + 0.02 * rng.random(ce.shape)
    ax.pcolormesh(kx, ky, ce, cmap="inferno", shading="auto")
    ax.set_aspect("equal")
    ax.set_title(r"$E - E_F = %.2f$ eV" % Eb, fontsize=9)
    ax.set_xlabel(r"$k_x$ (1/$\AA$)", fontsize=8)
    ax.set_ylabel(r"$k_y$ (1/$\AA$)", fontsize=8)
    ax.tick_params(labelsize=7)

fig.suptitle("Constant-energy map stack")
fig.tight_layout()
fig
'''


def _arpes_ce_stack():
    return [_md(_CE_INTRO), _code(_CE_CODE)]


# -- Registry --------------------------------------------------------------

ARPES_HV_EXAMPLES = [
    # (name, category, builder)
    ("Photon-Energy Scan / kz (peaks)", "ARPES", _arpes_hv_scan),
    ("I0 Flux Normalization (peaks)", "ARPES", _arpes_i0_norm),
    ("Constant-Energy Map Stack (peaks)", "ARPES", _arpes_ce_stack),
]
