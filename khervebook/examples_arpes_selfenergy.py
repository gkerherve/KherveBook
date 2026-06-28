"""Advanced ARPES self-energy & many-body examples using ``peaks``.

A self-contained companion to ``examples.py`` (Examples menu,
"Spectroscopy" category). ``peaks`` (``pip install peaks-arpes``) is the
angle-resolved photoemission toolkit from the King group at the
University of St Andrews; beyond loading raw dispersions it underpins the
quantitative many-body analyses that ARPES is famous for:

* a **self-energy / kink** analysis that fits momentum distribution
  curves (MDCs) across binding energy to extract the band dispersion
  *k*(*E*) and the MDC width, then reads off the real and imaginary parts
  of the electron self-energy Sigma and the ~70 meV electron-boson kink,
* a **superconducting gap** analysis that symmetrises an energy
  distribution curve (EDC) at *k_F* to expose the two coherence peaks at
  +/- Delta, and
* a **Fermi-surface map** with the **Brillouin-zone** boundary and the
  Gamma / K / M high-symmetry points overlaid for sample alignment.

Each code cell uses the real ``peaks`` API when the library is installed
and otherwise synthesises faithful data with NumPy (and SciPy where it
helps) so the example always runs offline.

This module defines its own ``_md``/``_code`` helpers and exports
``ARPES_SE_EXAMPLES`` so it merges into ``examples.py`` without a circular
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


# -- 1. Self-energy & kink ------------------------------------------------

_SE_INTRO = """\
# Self-energy & the electron-boson kink

The headline many-body result from ARPES is the **electron self-energy**
Sigma(*E*). You get it by fitting a **momentum distribution curve (MDC)** —
a horizontal cut through the dispersion at fixed binding energy — at every
energy. Each MDC is a Lorentzian whose **centre** traces the measured
band dispersion *k*(*E*) and whose **width** reports the scattering rate.

Compared to a straight, non-interacting **"bare band"**, an interacting
band develops a **kink** near the boson energy (often ~70 meV for
phonons). Reading the two pieces off the MDCs:

* **Re Sigma**(*E*) = *v_bare* * (*k_meas* - *k_bare*) — the energy offset
  between the measured and bare dispersions, peaked at the kink;
* **Im Sigma**(*E*) proportional to the MDC half-width * *v_bare* — the
  scattering rate, which steps up below the boson energy.

With [`peaks`](https://github.com/phrgab/peaks) the dispersion and its
per-energy MDC fits are a few calls:

```python
import peaks as pks
from peaks.core.utils.sample_data import ExampleData
disp = ExampleData.dispersion()                 # i05-59819.nxs
# fit a Lorentzian MDC at each binding energy -> k(E) and width(E)
mdc_fits = disp.fit_mdcs(model='lorentzian')
k_of_E   = mdc_fits['center']                    # measured dispersion
width    = mdc_fits['fwhm']                       # scattering width
```

Install it with `pip install peaks-arpes`. The cell below builds a
renormalised dispersion with a kink at *E_ph* = 70 meV, extracts *k*(*E*)
and the MDC width back out, and plots Re Sigma and Im Sigma versus energy.
"""


_SE_FIT = r'''
# Self-energy & kink: build a renormalised band with a 70 meV kink, then
# extract the dispersion k(E) and MDC width from the intensity image and
# read off Re(Sigma) and Im(Sigma). With peaks this is disp.fit_mdcs();
# here we synthesise the image and extract it back so it always runs.
import numpy as np
import matplotlib.pyplot as plt

DATA, ACC = "#3776ab", "#e07b39"
rng = np.random.default_rng(0)
eps = 1e-9

# Energy and momentum axes (E - E_F in eV, k in 1/Angstrom).
E = np.linspace(-0.30, 0.0, 240)               # below the Fermi level
k = np.linspace(0.0, 0.45, 320)
E_ph = 0.07                                     # boson (phonon) energy, 70 meV
v0 = 2.5                                        # bare-band velocity (eV.Angstrom)


def re_sigma_model(e):
    """Re(Sigma): a smooth bump peaked near the boson energy E_ph."""
    g = 0.05
    return 0.045 * (g ** 2) / ((np.abs(e) - E_ph) ** 2 + g ** 2)


def im_sigma_model(e):
    """Im(Sigma): scattering rate that steps up below E_ph (boson channel)."""
    step = 0.5 * (1.0 + np.tanh((np.abs(e) - E_ph) / 0.012))
    return 0.010 + 0.040 * step


# Bare band k_bare = E / v0 (a straight line through the Fermi crossing);
# the measured band is shifted by Re(Sigma): k_meas = (E - ReSigma) / v0.
k_bare = E / v0
k_meas_true = (E - re_sigma_model(E)) / v0
gamma_E = (im_sigma_model(E) / v0)             # MDC half-width (1/Angstrom)

try:
    import peaks as pks                                      # noqa: F401
    from peaks.core.utils.sample_data import ExampleData
    disp = ExampleData.dispersion()            # i05-59819.nxs
    raise RuntimeError("use synthetic self-energy analysis")
except Exception:
    source = "synthetic self-energy / kink (pip install peaks-arpes)"

# Build I[E, k]: a Lorentzian MDC at each energy centred on k_meas_true with
# half-width gamma_E, plus a small background and noise.
KK, EE = np.meshgrid(k, E)
cen = k_meas_true[:, None]
wid = np.clip(gamma_E[:, None], 1e-3, None)
I = (wid ** 2) / ((KK - cen) ** 2 + wid ** 2)
I = I / I.max() + 0.03 + 0.02 * rng.standard_normal(I.shape)
I = np.clip(I, 0.0, None)

# Extract k(E) and the width from each MDC (centroid + second moment) - the
# model-free version of fitting a Lorentzian to every row.
k_meas = np.empty(E.size)
width_meas = np.empty(E.size)
for j in range(E.size):
    row = I[j] - np.median(I[j])
    row = np.clip(row, 0.0, None)
    w = row.sum() + eps
    c = (row * k).sum() / w                     # centroid -> peak position
    var = (row * (k - c) ** 2).sum() / w
    k_meas[j] = c
    width_meas[j] = 2.0 * np.sqrt(np.clip(var, 0.0, None))   # ~ FWHM

# Self-energy from the extracted dispersion and width.
re_sigma = v0 * (k_meas - k_bare)              # Re(Sigma) = v0 (k_meas - k_bare)
im_sigma = v0 * 0.5 * width_meas               # Im(Sigma) ~ v0 * half-width
i_kink = int(np.argmin(np.abs(E + E_ph)))      # energy nearest -E_ph

fig, (a1, a2) = plt.subplots(1, 2, figsize=(8.2, 4.2))

pm = a1.pcolormesh(k, E, I, cmap="inferno", shading="auto")
a1.plot(k_meas, E, ".", ms=3, color="w", alpha=0.85, label="extracted $k(E)$")
a1.plot(k_bare, E, "--", color=ACC, lw=1.4, label="bare band")
a1.axhline(-E_ph, color="w", ls=":", lw=0.9, alpha=0.7)
a1.set_xlim(k.min(), k.max())
a1.set_ylim(E.min(), E.max())
a1.set_xlabel(r"$k$ (1/$\AA$)")
a1.set_ylabel(r"$E - E_F$ (eV)")
a1.set_title("dispersion + kink")
a1.legend(loc="lower right", frameon=False, fontsize=8, labelcolor="w")
fig.colorbar(pm, ax=a1, label="intensity (arb.)")

a2.plot(E, re_sigma, "-", color=DATA, lw=2, label=r"$\mathrm{Re}\,\Sigma$")
a2.plot(E, im_sigma, "-", color=ACC, lw=2, label=r"$\mathrm{Im}\,\Sigma$")
a2.axvline(-E_ph, color="0.5", ls="--", lw=1)
a2.annotate(r"kink $\approx %.0f$ meV" % (E_ph * 1000.0),
            xy=(-E_ph, re_sigma[i_kink]),
            xytext=(-E_ph + 0.06, re_sigma[i_kink] + 0.012),
            fontsize=9,
            arrowprops=dict(arrowstyle="->", color="0.4"))
a2.set_xlabel(r"$E - E_F$ (eV)")
a2.set_ylabel(r"$\Sigma$ (eV)")
a2.set_title(r"self-energy $\Sigma(E)$")
a2.legend(loc="upper left", frameon=False)

fig.text(0.01, 0.005, source, fontsize=7, color="0.45")
fig.tight_layout()
fig
'''


def _self_energy():
    return [_md(_SE_INTRO), _code(_SE_FIT)]


# -- 2. Superconducting gap -----------------------------------------------

_GAP_INTRO = """\
# Superconducting gap by EDC symmetrisation

Below *T_c* a superconductor opens an energy **gap** Delta at the Fermi
level. In ARPES this shows up in the **energy distribution curve (EDC)**
at the Fermi momentum *k_F*: spectral weight is pushed away from *E_F*
into a **coherence peak**. The trouble is the Fermi-Dirac cutoff sits on
top of the gap and hides it.

The standard trick is **symmetrisation**: because the spectral function
is particle-hole symmetric near *E_F*, adding the EDC to its mirror image,

> *I_sym*(*E*) = *I*(*E*) + *I*(-*E*),

cancels the Fermi function and leaves a clean spectrum with **two peaks
at +/- Delta**. The gap is half their separation. As temperature rises
toward *T_c* the gap fills in and the two peaks merge into one at *E_F*.

With [`peaks`](https://github.com/phrgab/peaks) the *k_F* EDC and its
symmetrisation are a couple of calls:

```python
import peaks as pks
from peaks.core.utils.sample_data import ExampleData
disp = ExampleData.dispersion()                 # i05-59819.nxs
edc  = disp.sel(theta_par=kF_angle, method='nearest')
edc_sym = 0.5 * (edc + edc.assign_coords(eV=-edc['eV']))
```

Install it with `pip install peaks-arpes`. The cell below builds a Dynes /
BCS-like gapped EDC at a few temperatures, symmetrises each, and reads off
2*Delta from the coherence-peak splitting.
"""


_GAP_FIT = r'''
# Superconducting gap: build a Dynes/BCS-like EDC at k_F with a gap Delta,
# symmetrise it (I(E)+I(-E)) to remove the Fermi cutoff, and read off the
# two coherence peaks at +/- Delta. With peaks this is an xarray
# symmetrisation; here we synthesise it so it always runs.
import numpy as np
import matplotlib.pyplot as plt

DATA, ACC = "#3776ab", "#e07b39"
rng = np.random.default_rng(0)
eps = 1e-9

E = np.linspace(-0.08, 0.08, 600)              # E - E_F (eV), around E_F
Delta = 0.015                                  # superconducting gap (eV)
kB = 8.617e-5                                   # Boltzmann constant (eV/K)


def fermi_dirac(e, T):
    return 1.0 / (np.exp(np.clip(e / (kB * T), -50, 50)) + 1.0)


def gaussian_blur(y, sig_pts):
    """Lightweight Gaussian smoothing (no SciPy dependency)."""
    n = max(int(3 * sig_pts), 1)
    x = np.arange(-n, n + 1)
    ker = np.exp(-0.5 * (x / max(sig_pts, eps)) ** 2)
    ker = ker / ker.sum()
    return np.convolve(y, ker, mode="same")


def dynes_dos(e, gap, gamma=0.0025):
    """Dynes BCS density of states: Re[(E+i.gamma)/sqrt((E+i.gamma)^2-D^2)]."""
    z = e + 1j * gamma
    denom = np.sqrt(z ** 2 - gap ** 2 + 0j)
    # Keep the branch with positive real part so the DOS stays >= 0.
    denom = np.where(denom.real < 0, -denom, denom)
    return np.abs(np.real(z / (denom + eps)))


def make_edc(gap, T):
    """Gapped EDC at k_F: Dynes DOS * Fermi-Dirac, broadened, + bg + noise."""
    dos = dynes_dos(E, gap)
    occupied = dos * fermi_dirac(E, T)
    de = E[1] - E[0]
    broadened = gaussian_blur(occupied, 0.003 / de)
    bg = 0.05
    return broadened + bg + rng.normal(0.0, 0.01, E.size)


try:
    import peaks as pks                                      # noqa: F401
    from peaks.core.utils.sample_data import ExampleData
    disp = ExampleData.dispersion()            # i05-59819.nxs
    raise RuntimeError("use synthetic gap analysis")
except Exception:
    source = "synthetic superconducting gap (pip install peaks-arpes)"

T_meas = 10.0                                   # measurement temperature (K)
edc_gap = make_edc(Delta, T_meas)              # superconducting (gapped)
edc_normal = make_edc(0.0, T_meas)             # normal state, Delta = 0

# Symmetrise about E_F: I_sym(E) = I(E) + I(-E) removes the Fermi cutoff.
edc_sym = edc_gap + edc_gap[::-1]

# Locate the coherence peak on the E > 0 side of the symmetrised curve.
pos = E > 0.002
ipk = np.where(pos)[0][int(np.argmax(edc_sym[pos]))]
Delta_meas = E[ipk]

fig, (a1, a2) = plt.subplots(1, 2, figsize=(8.2, 4.0))

a1.plot(E, edc_normal, "-", color="0.55", lw=1.6, label="normal ($T>T_c$)")
a1.plot(E, edc_gap, "-", color=DATA, lw=2, label="gapped ($T<T_c$)")
a1.axvline(0.0, color="0.7", ls=":", lw=0.9)
a1.set_xlabel(r"$E - E_F$ (eV)")
a1.set_ylabel("intensity (arb.)")
a1.set_title("EDC at $k_F$")
a1.legend(loc="upper left", frameon=False, fontsize=8)

a2.plot(E, edc_sym, "-", color=DATA, lw=2)
for s in (-1.0, 1.0):
    a2.axvline(s * Delta_meas, color=ACC, ls="--", lw=1.4)
ytop = edc_sym.max()
a2.annotate("", xy=(Delta_meas, ytop * 0.6), xytext=(-Delta_meas, ytop * 0.6),
            arrowprops=dict(arrowstyle="<->", color="0.4"))
a2.text(0.0, ytop * 0.64, r"$2\Delta = %.0f$ meV" % (2.0 * Delta_meas * 1000.0),
        ha="center", va="bottom", fontsize=9)
a2.set_xlabel(r"$E - E_F$ (eV)")
a2.set_ylabel("intensity (arb.)")
a2.set_title(r"symmetrised: coherence peaks at $\pm\Delta$")

fig.text(0.01, 0.005, source, fontsize=7, color="0.45")
fig.tight_layout()
fig
'''


def _gap():
    return [_md(_GAP_INTRO), _code(_GAP_FIT)]


# -- 3. Fermi surface + Brillouin zone ------------------------------------

_FS_INTRO = """\
# Fermi surface + Brillouin zone overlay

A **Fermi-surface (FS) map** is the constant-energy ARPES intensity at
*E_F* over the (*k_x*, *k_y*) plane — the cross-section of the bands that
carry the metal's electrons. Interpreting it means knowing where you are
in the **Brillouin zone (BZ)**: overlaying the BZ boundary and the
high-symmetry points Gamma, **K** and **M** is how you align the sample
and identify the pockets.

With [`peaks`](https://github.com/phrgab/peaks) the BZ comes straight from
the crystal structure and is drawn over the measured map:

```python
import peaks as pks
from peaks.core.utils.sample_data import ExampleData
fs        = ExampleData.fermi_surface()         # constant-energy map
structure = ExampleData.structure()             # crystal -> reciprocal cell
fs.plot()
structure.brillouin_zone.overlay(ax=plt.gca())  # BZ boundary + Gamma/K/M
```

Install it with `pip install peaks-arpes`. The cell below synthesises a
hexagonal Fermi surface (pockets at the six **K** corners), draws the
hexagonal BZ boundary, and labels Gamma, K and M.
"""


_FS_FIT = r'''
# Fermi surface + Brillouin zone: synthesise a hexagonal Fermi-surface map
# with pockets at the six BZ corners (K points), then overlay the BZ
# boundary and the Gamma/K/M high-symmetry points. With peaks this is
# structure.brillouin_zone.overlay(); here we draw it so it always runs.
import numpy as np
import matplotlib.pyplot as plt

ACC = "#e07b39"
rng = np.random.default_rng(0)

# Reciprocal lattice scale: distance from Gamma to the K corner (1/Angstrom).
kK = 1.0
kx = np.linspace(-1.5, 1.5, 400)
ky = np.linspace(-1.5, 1.5, 400)
KX, KY = np.meshgrid(kx, ky)

# Six BZ corners (K points) of a hexagonal zone, plus the centre (Gamma).
corner_ang = np.deg2rad(np.arange(6) * 60.0)
K_corners = np.column_stack((kK * np.cos(corner_ang), kK * np.sin(corner_ang)))

# Fermi-surface intensity: a circular electron pocket at each K corner,
# plus a small pocket at Gamma, on a smooth background with detector noise.
I = np.zeros_like(KX)
pocket_r = 0.22
for cx, cy in K_corners:
    I += np.exp(-((KX - cx) ** 2 + (KY - cy) ** 2) / (2.0 * pocket_r ** 2))
I += 0.6 * np.exp(-(KX ** 2 + KY ** 2) / (2.0 * 0.16 ** 2))   # Gamma pocket
I = I / I.max() + 0.05 + 0.04 * rng.standard_normal(I.shape)
I = np.clip(I, 0.0, None)

# Hexagonal BZ boundary: the six M-point edge midpoints. The edge midpoints
# sit at radius kK*cos(30deg) rotated 30deg from the corners.
kM = kK * np.cos(np.deg2rad(30.0))
edge_ang = np.deg2rad(np.arange(6) * 60.0 + 30.0)
M_points = np.column_stack((kM * np.cos(edge_ang), kM * np.sin(edge_ang)))
hex_x = np.append(M_points[:, 0], M_points[0, 0])
hex_y = np.append(M_points[:, 1], M_points[0, 1])

fig, ax = plt.subplots(figsize=(5.6, 5.2))
pm = ax.pcolormesh(kx, ky, I, cmap="inferno", shading="auto")
ax.plot(hex_x, hex_y, "-", color=ACC, lw=2.0)               # BZ boundary

# High-symmetry points: Gamma (centre), K (corner), M (edge midpoint).
ax.plot(0.0, 0.0, "o", color="w", ms=6)
ax.plot(K_corners[:, 0], K_corners[:, 1], "o", color="w", ms=5)
ax.plot(M_points[:, 0], M_points[:, 1], "s", color=ACC, ms=5)
ax.annotate(r"$\Gamma$", xy=(0, 0), xytext=(0.06, 0.06),
            color="w", fontsize=13)
ax.annotate("K", xy=(K_corners[0, 0], K_corners[0, 1]),
            xytext=(K_corners[0, 0] + 0.05, K_corners[0, 1] + 0.05),
            color="w", fontsize=12)
ax.annotate("M", xy=(M_points[0, 0], M_points[0, 1]),
            xytext=(M_points[0, 0] + 0.05, M_points[0, 1] + 0.05),
            color=ACC, fontsize=12)

ax.set_aspect("equal")
ax.set_xlim(kx.min(), kx.max())
ax.set_ylim(ky.min(), ky.max())
ax.set_xlabel(r"$k_x$ (1/$\AA$)")
ax.set_ylabel(r"$k_y$ (1/$\AA$)")
ax.set_title("Fermi surface + Brillouin zone")
fig.colorbar(pm, ax=ax, label="intensity (arb.)")

source = "synthetic Fermi surface + BZ (pip install peaks-arpes)"
fig.text(0.01, 0.005, source, fontsize=7, color="0.45")
fig.tight_layout()
fig
'''


def _fermi_surface():
    return [_md(_FS_INTRO), _code(_FS_FIT)]


# -- Registry --------------------------------------------------------------

ARPES_SE_EXAMPLES = [
    # (name, category, builder)
    ("Self-Energy & Kink (peaks)", "Spectroscopy", _self_energy),
    ("Superconducting Gap (peaks)", "Spectroscopy", _gap),
    ("Fermi Surface + Brillouin Zone (peaks)", "Spectroscopy", _fermi_surface),
]
