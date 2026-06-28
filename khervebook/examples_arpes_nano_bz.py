"""nanoARPES spatial-mapping and Brillouin-zone examples using ``peaks``.

A self-contained companion to ``examples.py`` (Examples menu,
"Spectroscopy" category), in the spirit of ``examples_arpes.py``.
``peaks`` (``pip install peaks-arpes``) is the angle-resolved
photoemission toolkit from the King group at the University of St
Andrews; alongside the tutorial dispersion it ships nanoARPES spatial
maps from Diamond Light Source beamline I05 and crystal-structure /
Brillouin-zone tooling.

This module holds two examples:

* **nanoARPES Spatial Map** - nanoARPES rasters a tightly focused beam
  over the sample so every (x, y) pixel carries a full photoemission
  spectrum. We map a band feature across real space and compare the
  energy distribution curves (EDCs) extracted from two regions of
  interest. The real loader uses ``ExampleData.SM()`` (the
  ``i05-1-24270_sm.nc`` spatial map); a NumPy fallback builds a two-
  domain map so it always runs offline.

* **Brillouin Zone** - pure NumPy/matplotlib geometry drawing the 2-D
  hexagonal Brillouin zone of a triangular / graphene-like lattice,
  with the high-symmetry points and a tight-binding band along the
  Gamma-K-M-Gamma path. ``peaks`` can build the real zone from a
  ``.cif`` via ``ExampleData.structure()``.

This module defines its own ``_md``/``_code`` helpers and exports
``ARPES_NANO_BZ_EXAMPLES`` so it merges into ``examples.py`` without a
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


_NANO_INTRO = """\
# nanoARPES spatial mapping with the `peaks` library

[`peaks`](https://github.com/phrgab/peaks) is a Python toolkit for
**angle-resolved photoemission spectroscopy (ARPES)** from the King group
at the University of St Andrews
([arXiv:2508.04803](https://arxiv.org/abs/2508.04803)).

**nanoARPES** focuses the synchrotron beam to a sub-micron spot and
**rasters** it across the sample, recording a full photoemission
spectrum at every (x, y) pixel. From that hyperspectral cube you can
*image* a chosen feature in real space - integrated intensity of a band,
a band position, or a spectral gap - and then pull representative
spectra out of individual spots to see how the electronic structure
changes from place to place (across domains, flakes or device regions).

`peaks` ships a Diamond Light Source beamline-**I05** spatial map. A
typical load looks like:

```python
import peaks as pks
from peaks.core.utils.sample_data import ExampleData
sm = ExampleData.SM()          # i05-1-24270_sm.nc spatial map
# (ExampleData.nano_focus() / i05-1-49292.nxs is a focused nano scan)
sm.plot()                      # spatial map of the mapped quantity
```

Install it with `pip install peaks-arpes`. The cell below uses that real
map when `peaks` is available, and otherwise synthesises a two-domain
sample so the example always runs. The **left** panel images the band
intensity across the surface (two ROI markers, A and B); the **right**
panel compares the EDC extracted at A versus B.
"""


_NANO_MAP = r'''
# nanoARPES: map a band feature across real space, then compare the
# spectra (EDCs) from two regions of interest (ROIs).
#
# peaks ships a Diamond I05 spatial map via ExampleData.SM()
# (i05-1-24270_sm.nc). If peaks isn't installed we synthesise a two-
# domain sample so the example still produces a real spatial map + EDCs.
import numpy as np
import matplotlib.pyplot as plt

rng = np.random.default_rng(0)


def load_spatial_map():
    """Return (x_um, y_um, mapq[y, x], source).

    ``mapq`` is a scalar "map quantity" per pixel (here, the intensity
    of a chosen band), already collapsed from the full spectral cube.
    """
    try:
        import peaks as pks                                   # noqa: F401
        from peaks.core.utils.sample_data import ExampleData
        sm = ExampleData.SM()                  # i05-1-24270_sm.nc
        try:
            cube = np.asarray(sm.pint.magnitude, dtype=float)
        except Exception:
            cube = np.asarray(sm.values, dtype=float)
        # Collapse any spectral/energy axes so a scalar remains per (y, x).
        while cube.ndim > 2:
            cube = cube.sum(axis=-1)
        ny, nx = cube.shape
        x = np.linspace(0.0, 40.0, nx)
        y = np.linspace(0.0, 40.0, ny)
        return x, y, cube, "peaks data - Diamond I05 (i05-1-24270_sm.nc)"
    except Exception:
        nx = ny = 80
        x = np.linspace(0.0, 40.0, nx)          # microns
        y = np.linspace(0.0, 40.0, ny)
        XX, YY = np.meshgrid(x, y)
        # Smooth diagonal boundary between a left domain and a right
        # domain, plus a brighter circular flake on the right.
        boundary = 1.0 / (1.0 + np.exp(-(XX - 20.0 - 0.25 * (YY - 20.0))))
        flake = np.exp(-(((XX - 28.0) ** 2 + (YY - 14.0) ** 2) / 18.0))
        mapq = 0.35 + 0.5 * boundary + 0.4 * flake
        mapq = mapq + 0.03 * rng.standard_normal(mapq.shape)
        return x, y, mapq, "synthetic two-domain map (pip install peaks-arpes)"


def synth_edc(E, band_center, gap):
    """A representative EDC: a Lorentzian band, optional gap, Fermi cut."""
    gamma = 0.03
    edge = band_center + gap                    # gap pushes weight down
    spec = (gamma / np.pi) / ((E - edge) ** 2 + gamma ** 2)
    fermi = 1.0 / (np.exp(E / 0.015) + 1.0)     # Fermi-Dirac cut-off
    edc = spec * fermi
    edc = edc / edc.max() + 0.02 * rng.random(edc.shape)
    return edc


x, y, mapq, source = load_spatial_map()

# Two regions of interest in real space (microns): A in the left domain,
# B in the right domain / flake. Snap to the nearest pixel.
roi_A = (10.0, 26.0)
roi_B = (28.0, 14.0)
iA = (int(np.argmin(np.abs(y - roi_A[1]))), int(np.argmin(np.abs(x - roi_A[0]))))
iB = (int(np.argmin(np.abs(y - roi_B[1]))), int(np.argmin(np.abs(x - roi_B[0]))))

# Build two EDCs that differ between the locations (B is gapped + shifted).
E = np.linspace(-0.60, 0.10, 300)               # E - E_F (eV)
edc_A = synth_edc(E, band_center=-0.18, gap=0.00)
edc_B = synth_edc(E, band_center=-0.18, gap=-0.12)

fig, (axm, axs) = plt.subplots(1, 2, figsize=(8.4, 3.8))

pm = axm.pcolormesh(x, y, mapq, cmap="viridis", shading="auto")
axm.set_aspect("equal")
axm.set_xlabel(r"x ($\mu$m)")
axm.set_ylabel(r"y ($\mu$m)")
axm.set_title("nanoARPES spatial map\n(band intensity)")
fig.colorbar(pm, ax=axm, label="intensity (arb.)", fraction=0.046, pad=0.04)
for (px, py), lab, col in ((roi_A, "A", "#e07b39"), (roi_B, "B", "#ffffff")):
    axm.plot(px, py, "o", mfc="none", mec=col, mew=1.8, ms=11)
    axm.annotate(lab, (px, py), color=col, fontsize=11, fontweight="bold",
                 xytext=(5, 5), textcoords="offset points")

axs.plot(edc_A, E, color="#3776ab", label="ROI A")
axs.plot(edc_B, E, color="#e07b39", label="ROI B")
axs.axhline(0, color="0.5", ls="--", lw=0.8)    # Fermi level
axs.set_xlabel("intensity (arb.)")
axs.set_ylabel(r"$E-E_F$ (eV)")
axs.set_title("EDCs at the two ROIs")
axs.legend(loc="lower right", fontsize=9)

fig.text(0.01, 0.005, source, fontsize=7, color="0.45")
fig.tight_layout()
fig
'''


_BZ_INTRO = """\
# The Brillouin zone of a hexagonal lattice

The **Brillouin zone (BZ)** is the primitive cell of the reciprocal
lattice - the natural "momentum-space" box in which electronic band
structure is plotted. For a 2-D **triangular / graphene-like** lattice
the first BZ is a regular **hexagon**, with the familiar high-symmetry
points: $\\Gamma$ at the centre, **K** at the corners and **M** at the
edge midpoints. ARPES band maps are taken along paths joining these
points (e.g. $\\Gamma$-M-K-$\\Gamma$).

`peaks` can build the real zone straight from a crystal structure:

```python
from peaks.core.utils.sample_data import ExampleData
struct = ExampleData.structure()   # loads a .cif crystal structure
# peaks then constructs the Brillouin zone and high-symmetry points/paths
```

The cell below needs no data at all - it is pure NumPy/matplotlib
geometry, so it always runs. The **left** panel draws the hexagonal BZ
with $\\Gamma$, **K** and **M** labelled and the $\\Gamma$-M-K-$\\Gamma$
path marked; the **right** panel plots a nearest-neighbour
tight-binding band along that path.
"""


_BZ_GEOMETRY = r'''
# Brillouin zone of a 2-D hexagonal (triangular / graphene-like) lattice.
# Pure NumPy/matplotlib geometry - always runs. peaks can build the real
# zone from a .cif via ExampleData.structure().
import numpy as np
import matplotlib.pyplot as plt

BLUE, ORANGE = "#3776ab", "#e07b39"

# Real-space lattice constant -> reciprocal lattice. For a triangular
# lattice the BZ is a hexagon; |Gamma-K| sets its size.
a = 1.0
kK = 4.0 * np.pi / (3.0 * a)                    # |Gamma -> K|
kM = 2.0 * np.pi / (np.sqrt(3.0) * a)           # |Gamma -> M|

# Six K (corner) points and six M (edge-midpoint) points.
ang_K = np.deg2rad(30.0 + 60.0 * np.arange(6))  # corners
K_pts = np.column_stack((kK * np.cos(ang_K), kK * np.sin(ang_K)))
ang_M = np.deg2rad(60.0 * np.arange(6))         # edge midpoints
M_pts = np.column_stack((kM * np.cos(ang_M), kM * np.sin(ang_M)))

# Closed hexagon outline through the K corners.
hexx = np.append(K_pts[:, 0], K_pts[0, 0])
hexy = np.append(K_pts[:, 1], K_pts[0, 1])

# High-symmetry path Gamma -> M -> K -> Gamma (one representative pair).
G = np.array([0.0, 0.0])
M = M_pts[0]
K = K_pts[0]
path_pts = [G, M, K, G]


def sample_segment(p0, p1, n):
    t = np.linspace(0.0, 1.0, n, endpoint=False)
    seg = p0[None, :] + t[:, None] * (p1 - p0)[None, :]
    return seg


# Build a dense k-path and its cumulative path coordinate.
kx, ky, kdist = [], [], [0.0]
for p0, p1 in zip(path_pts[:-1], path_pts[1:]):
    seg = sample_segment(p0, p1, 120)
    kx.extend(seg[:, 0])
    ky.extend(seg[:, 1])
    step = np.linalg.norm(p1 - p0) / 120.0
    kdist.extend(kdist[-1] + step * (1 + np.arange(seg.shape[0])))
kx = np.append(np.asarray(kx), G[0])
ky = np.append(np.asarray(ky), G[1])
kdist = np.asarray(kdist)
# Tick positions at the path vertices.
seg_len = [np.linalg.norm(path_pts[i + 1] - path_pts[i]) for i in range(3)]
vert_dist = np.concatenate(([0.0], np.cumsum(seg_len)))

# Nearest-neighbour tight-binding band on the triangular lattice.
delta = a * np.array([[1.0, 0.0],
                      [-0.5, np.sqrt(3.0) / 2.0],
                      [-0.5, -np.sqrt(3.0) / 2.0]])
t_hop = 1.0
phase = kx[:, None] * delta[:, 0][None, :] + ky[:, None] * delta[:, 1][None, :]
band = -2.0 * t_hop * np.cos(phase).sum(axis=1)

fig, (axz, axb) = plt.subplots(1, 2, figsize=(8.4, 3.8))

# -- Left: the hexagonal Brillouin zone -------------------------------
axz.plot(hexx, hexy, color=BLUE, lw=2.0, zorder=2)
axz.fill(hexx, hexy, color=BLUE, alpha=0.07, zorder=1)
axz.plot(0, 0, "o", color="black", ms=6, zorder=4)
axz.annotate(r"$\Gamma$", (0, 0), xytext=(6, 6),
             textcoords="offset points", fontsize=13)
axz.scatter(K_pts[:, 0], K_pts[:, 1], color=ORANGE, s=36, zorder=4)
axz.scatter(M_pts[:, 0], M_pts[:, 1], color=BLUE, s=30, marker="s", zorder=4)
axz.annotate("K", K_pts[0], xytext=(6, 4), textcoords="offset points",
             fontsize=12, color=ORANGE, fontweight="bold")
axz.annotate("M", M_pts[0], xytext=(6, -12), textcoords="offset points",
             fontsize=12, color=BLUE, fontweight="bold")
# Draw the Gamma-M-K-Gamma path with arrows.
for p0, p1 in zip(path_pts[:-1], path_pts[1:]):
    axz.annotate("", xy=p1, xytext=p0,
                 arrowprops=dict(arrowstyle="->", color="0.25", lw=1.6))
axz.set_aspect("equal")
axz.set_xlabel(r"$k_x$ (1/$a$)")
axz.set_ylabel(r"$k_y$ (1/$a$)")
axz.set_title("Hexagonal Brillouin zone")
lim = kK * 1.25
axz.set_xlim(-lim, lim)
axz.set_ylim(-lim, lim)

# -- Right: tight-binding band along Gamma-M-K-Gamma ------------------
axb.plot(kdist, band, color=BLUE, lw=2.0)
for vd in vert_dist:
    axb.axvline(vd, color="0.8", lw=0.8)
axb.set_xticks(vert_dist)
axb.set_xticklabels([r"$\Gamma$", "M", "K", r"$\Gamma$"])
axb.set_xlim(vert_dist[0], vert_dist[-1])
axb.set_ylabel(r"$E$ (units of $t$)")
axb.set_title("Tight-binding band\nalong the high-symmetry path")
axb.grid(True, axis="y", alpha=0.25)

fig.tight_layout()
fig
'''


def _nano_spatial_map():
    return [_md(_NANO_INTRO), _code(_NANO_MAP)]


def _brillouin_zone():
    return [_md(_BZ_INTRO), _code(_BZ_GEOMETRY)]


# -- Registry --------------------------------------------------------------

ARPES_NANO_BZ_EXAMPLES = [
    # (name, category, builder)
    ("nanoARPES Spatial Map (peaks)", "Spectroscopy", _nano_spatial_map),
    ("Brillouin Zone (peaks)", "Spectroscopy", _brillouin_zone),
]
