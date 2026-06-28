"""ARPES data-operation examples built on the ``peaks`` library's ideas.

A self-contained companion to ``examples.py`` (Examples menu,
"Spectroscopy" category) alongside ``examples_arpes.py`` and
``examples_arpes_bands.py``. ``peaks`` (``pip install peaks-arpes``) is
the angle-resolved photoemission toolkit from the King group at the
University of St Andrews; beyond loading Diamond Light Source beamline-
I05 scans it offers data operations on a dispersion or map.

Three operations are exported here:

* **Data Symmetrisation** — fold a map about a high-symmetry point and
  average to improve statistics and reveal symmetry.
* **Arbitrary & Radial Cuts** — extract a straight-line cut between two
  points and radial cuts from the centre of a constant-energy map.
* **Angle-Integrated DOS** — integrate a dispersion over the angle axis
  to approximate the density of states.

Each code cell synthesises faithful data with NumPy (fixed seed) so the
example always runs offline, mirroring the real ``peaks`` operations.
This module defines its own ``_md``/``_code`` helpers and exports
``ARPES_CUTS_EXAMPLES`` so it merges into ``examples.py`` without a
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


# -- 1. Data symmetrisation ------------------------------------------------

_SYM_INTRO = """\
# ARPES data symmetrisation with the `peaks` library

ARPES maps are often **symmetrised** about a high-symmetry point or plane
— folding the intensity onto itself and averaging the two halves. Because
the underlying band structure must respect the crystal symmetry, the two
sides carry the *same* signal but *independent* noise, so averaging them

> *I*<sub>sym</sub>(*k*) = ½ · [ *I*(*k*) + *I*(−*k*) ]

improves the statistics (√2 in signal-to-noise) and restores the
expected symmetry when the raw scan is lopsided from detector gradients
or sample alignment.

[`peaks`](https://github.com/phrgab/peaks) provides symmetrisation
operations that fold a dispersion or map about a chosen centre. The cell
below builds a parabolic band that has been made **asymmetric** in the
angle/momentum axis by a smooth intensity gradient, then symmetrises it
by flipping along that axis (`np.flip`) and averaging — showing the raw
and symmetrised maps side by side.
"""


_SYM_CODE = r'''
# ARPES data symmetrisation: fold a dispersion about k = 0 and average.
# I_sym(k) = 0.5 * (I(k) + I(-k)), implemented with np.flip along the
# angle axis. The raw map is deliberately asymmetric (a smooth intensity
# gradient across the angle axis), as can happen from detector response
# or alignment; peaks provides symmetrisation operations that do this on
# real data. Here a synthetic band keeps the example offline.
import numpy as np
import matplotlib.pyplot as plt

rng = np.random.default_rng(0)
ang = np.linspace(-16, 16, 221)                 # emission angle (deg), symmetric grid
E = np.linspace(-0.70, 0.10, 300)               # E - E_F (eV)
AA, EE = np.meshgrid(ang, E)
band = -0.45 + 0.0045 * AA ** 2                 # parabolic band minimum
gamma = 0.02 + 0.05 * band ** 2                 # lifetime broadening
spectral = (gamma / np.pi) / ((EE - band) ** 2 + gamma ** 2)
fermi = 1.0 / (np.exp(EE / 0.012) + 1.0)        # Fermi-Dirac cut-off
clean = spectral * fermi
clean = clean / clean.max()

# Make the map asymmetric across the angle axis (smooth left/right gradient)
# and add noise: this is the "raw" measurement we want to symmetrise.
gradient = 1.0 + 0.4 * np.tanh(AA / 5.0)        # angle-dependent intensity gain
I_raw = clean * gradient + 0.03 * rng.random(clean.shape)

# Symmetrise about the centre of the angle axis: average with its mirror.
I_sym = 0.5 * (I_raw + np.flip(I_raw, axis=1))

vmax = max(I_raw.max(), I_sym.max())
fig, (a1, a2) = plt.subplots(1, 2, figsize=(8.0, 3.8), sharey=True)

pm1 = a1.pcolormesh(ang, E, I_raw, cmap="inferno", shading="auto", vmax=vmax)
a1.axvline(0, color="w", ls=":", lw=0.8, alpha=0.6)
a1.axhline(0, color="w", ls="--", lw=0.8, alpha=0.7)
a1.set_xlabel(r"emission angle  $\theta_\parallel$  (deg)")
a1.set_ylabel(r"$E - E_F$  (eV)")
a1.set_title("raw (asymmetric)")
fig.colorbar(pm1, ax=a1, label="intensity (arb.)")

pm2 = a2.pcolormesh(ang, E, I_sym, cmap="inferno", shading="auto", vmax=vmax)
a2.axvline(0, color="w", ls=":", lw=0.8, alpha=0.6)
a2.axhline(0, color="w", ls="--", lw=0.8, alpha=0.7)
a2.set_xlabel(r"emission angle  $\theta_\parallel$  (deg)")
a2.set_title(r"symmetrised  $\frac{1}{2}[I(k)+I(-k)]$")
fig.colorbar(pm2, ax=a2, label="intensity (arb.)")

fig.text(0.01, 0.005, "symmetrising averages independent noise: "
         "better statistics and restored symmetry", fontsize=8, color="0.45")
fig.tight_layout()
fig
'''


def _arpes_symmetrise():
    return [_md(_SYM_INTRO), _code(_SYM_CODE)]


# -- 2. Arbitrary & radial cuts --------------------------------------------

_CUTS_INTRO = """\
# Arbitrary & radial cuts through an ARPES map

Beyond axis-aligned EDCs and MDCs, ARPES analysis routinely takes
**arbitrary line cuts** through a 2-D map — an intensity profile along a
straight line between two points (*P*<sub>0</sub> → *P*<sub>1</sub>) — and
**radial cuts** that fan out from the map centre at chosen angles. These
sample the spectral function along directions that need not line up with
the measurement axes.

[`peaks`](https://github.com/phrgab/peaks) supports this kind of slicing
— `.sel` for axis-aligned slices, plus arbitrary and radial cut
extraction — on its Fermi-surface maps. The cell below builds a circular
Fermi-surface map and uses `scipy.ndimage.map_coordinates` to
**interpolate** the intensity along (a) an arbitrary line and (b) several
radial lines from the centre, then plots the extracted profiles versus
distance along each cut.
"""


_CUTS_CODE = r'''
# Arbitrary and radial cuts through a constant-energy ARPES map.
# scipy.ndimage.map_coordinates interpolates intensity along any path:
#   - an arbitrary straight line P0 -> P1
#   - several radial lines from the map centre at a few angles
# peaks offers arbitrary/radial cut extraction on real maps; here a
# synthetic Fermi-surface ring keeps the example offline.
import numpy as np
import matplotlib.pyplot as plt
from scipy.ndimage import map_coordinates

rng = np.random.default_rng(0)
kx = np.linspace(-1.2, 1.2, 241)                # 1/Angstrom
ky = np.linspace(-1.2, 1.2, 241)
KX, KY = np.meshgrid(kx, ky)
kmag = np.hypot(KX, KY)
kF = 0.8                                         # Fermi wavevector
gamma = 0.05                                     # contour broadening
ring = (gamma / np.pi) / ((kmag - kF) ** 2 + gamma ** 2)
I = ring + 0.05 + 0.03 * rng.random(ring.shape)  # ring + background + noise
I = I / I.max()


def k_to_index(kxq, kyq):
    """Map physical (kx, ky) to fractional (row, col) indices for sampling."""
    col = (np.asarray(kxq) - kx[0]) / (kx[-1] - kx[0]) * (kx.size - 1)
    row = (np.asarray(kyq) - ky[0]) / (ky[-1] - ky[0]) * (ky.size - 1)
    return np.vstack([row, col])


def sample_line(p0, p1, n=240):
    """Intensity profile along the straight segment p0 -> p1 (k-space)."""
    t = np.linspace(0.0, 1.0, n)
    kxq = p0[0] + t * (p1[0] - p0[0])
    kyq = p0[1] + t * (p1[1] - p0[1])
    prof = map_coordinates(I, k_to_index(kxq, kyq), order=1, mode="nearest")
    dist = t * np.hypot(p1[0] - p0[0], p1[1] - p0[1])
    return kxq, kyq, dist, prof


brand = ["#3776ab", "#e07b39"]

# (a) one arbitrary cut between two points.
P0, P1 = (-1.05, -0.65), (1.05, 0.75)
ax_kx, ax_ky, ax_d, ax_prof = sample_line(P0, P1)

# (b) several radial cuts from the centre out to the edge.
rmax = 1.15
angles = np.deg2rad([0.0, 45.0, 90.0])
radials = []
for a in angles:
    p1 = (rmax * np.cos(a), rmax * np.sin(a))
    radials.append(sample_line((0.0, 0.0), p1))

fig, (a1, a2) = plt.subplots(1, 2, figsize=(8.4, 4.0))

pm = a1.pcolormesh(kx, ky, I, cmap="inferno", shading="auto")
a1.set_aspect("equal")
a1.plot(ax_kx, ax_ky, color=brand[1], lw=2.0, label="arbitrary cut")
rad_colors = ["#3776ab", "#7fb3d5", "#1b4f72"]
for (rkx, rky, rd, rp), c, a in zip(radials, rad_colors, angles):
    a1.plot(rkx, rky, color=c, lw=1.8,
            label=r"radial %d$\degree$" % int(round(np.rad2deg(a))))
a1.plot(0, 0, "o", color="w", ms=4)
a1.set_xlabel(r"$k_x$ (1/$\AA$)")
a1.set_ylabel(r"$k_y$ (1/$\AA$)")
a1.set_title("Fermi surface with cuts")
a1.legend(fontsize=7, loc="upper left", framealpha=0.85)
fig.colorbar(pm, ax=a1, label="intensity (arb.)")

a2.plot(ax_d, ax_prof, color=brand[1], lw=2.0, label="arbitrary cut")
for (rkx, rky, rd, rp), c, a in zip(radials, rad_colors, angles):
    a2.plot(rd, rp, color=c, lw=1.8,
            label=r"radial %d$\degree$" % int(round(np.rad2deg(a))))
a2.set_xlabel(r"distance along cut  (1/$\AA$)")
a2.set_ylabel("intensity (arb.)")
a2.set_title("extracted intensity profiles")
a2.legend(fontsize=7, loc="upper right", framealpha=0.85)

fig.tight_layout()
fig
'''


def _arpes_cuts():
    return [_md(_CUTS_INTRO), _code(_CUTS_CODE)]


# -- 3. Angle-integrated DOS -----------------------------------------------

_DOS_INTRO = """\
# Angle-integrated density of states with the `peaks` library

Integrating an ARPES dispersion over its **angle (momentum) axis**
collapses the 2-D map *I*(*E*, θ) into a single spectrum *N*(*E*) — an
**angle-integrated** energy distribution that approximates the
**density of states** (DOS),

> *N*(*E*) = ∫ *I*(*E*, θ) d θ.

Because it sums over all emission angles, the band *onset* shows up as a
rise in *N*(*E*) and the **Fermi level** as a sharp cut-off, even where a
single EDC at one angle would be weak.

[`peaks`](https://github.com/phrgab/peaks) exposes this directly as
`.DOS()`, which integrates a dispersion over the angle axis. The cell
below builds a Lorentzian-on-a-parabola band with a Fermi-Dirac cut-off,
integrates it over angle to get the angle-integrated DOS, and compares it
to a single EDC taken at normal emission.
"""


_DOS_CODE = r'''
# Angle-integrated DOS from an ARPES dispersion.
# N(E) = integral over the angle axis of I(E, angle) -> approximates the
# density of states. peaks exposes this as disp.DOS(); here we integrate a
# synthetic band (Lorentzian about a parabola, with a Fermi-Dirac cut-off)
# over angle and compare it to a single EDC at normal emission.
import numpy as np
import matplotlib.pyplot as plt

rng = np.random.default_rng(0)
ang = np.linspace(-16, 16, 221)                 # emission angle (deg)
E = np.linspace(-0.70, 0.10, 300)               # E - E_F (eV)
AA, EE = np.meshgrid(ang, E)
band = -0.45 + 0.0045 * AA ** 2                 # parabolic band minimum
gamma = 0.02 + 0.05 * band ** 2                 # lifetime broadening
spectral = (gamma / np.pi) / ((EE - band) ** 2 + gamma ** 2)
fermi = 1.0 / (np.exp(EE / 0.012) + 1.0)        # Fermi-Dirac cut-off
I = spectral * fermi
I = I / I.max() + 0.02 * rng.random(I.shape)

# Angle-integrated DOS: integrate over the angle axis (axis 1).
dos = np.trapz(I, ang, axis=1)
dos = dos / dos.max()

# A single EDC at normal emission for comparison.
i0 = int(np.argmin(np.abs(ang)))
edc = I[:, i0]
edc = edc / edc.max()

fig, (a1, a2) = plt.subplots(1, 2, figsize=(8.2, 3.9))

pm = a1.pcolormesh(ang, E, I, cmap="inferno", shading="auto")
a1.axhline(0, color="w", ls="--", lw=0.8, alpha=0.7)        # Fermi level
a1.set_xlabel(r"emission angle  $\theta_\parallel$  (deg)")
a1.set_ylabel(r"$E - E_F$  (eV)")
a1.set_title("dispersion  $I(E,\\theta)$")
fig.colorbar(pm, ax=a1, label="intensity (arb.)")

a2.plot(dos, E, color="#3776ab", lw=2.0, label=r"angle-integrated DOS")
a2.plot(edc, E, color="#e07b39", lw=1.5, ls="--", label="EDC at normal emission")
a2.axhline(0, color="0.4", ls=":", lw=1.0)                  # Fermi level
a2.set_xlabel("intensity (arb.)")
a2.set_ylabel(r"$E - E_F$  (eV)")
a2.set_title(r"$N(E) = \int I(E,\theta)\, d\theta$")
a2.legend(fontsize=8, loc="lower right", framealpha=0.85)

fig.text(0.01, 0.005, "band onset appears as a rise; Fermi level as a cut-off",
         fontsize=8, color="0.45")
fig.tight_layout()
fig
'''


def _arpes_dos():
    return [_md(_DOS_INTRO), _code(_DOS_CODE)]


# -- Registry --------------------------------------------------------------

ARPES_CUTS_EXAMPLES = [
    # (name, category, builder)
    ("Data Symmetrization (peaks)", "Spectroscopy", _arpes_symmetrise),
    ("Arbitrary & Radial Cuts (peaks)", "Spectroscopy", _arpes_cuts),
    ("Angle-Integrated DOS (peaks)", "Spectroscopy", _arpes_dos),
]
