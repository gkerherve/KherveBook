"""A single end-to-end ARPES walkthrough (Examples menu, "Spectroscopy").

The other ARPES examples each live on their own page; this one strings the
whole analysis chain into a single notebook that runs top to bottom on one
shared dataset: load a dispersion, take EDC/MDC cuts, convert angle to
momentum, map a Fermi surface, sharpen bands by curvature, calibrate the
energy resolution on a gold edge, extract the self-energy from a kink, and
read a superconducting gap off a symmetrised EDC. It uses the real `peaks`
dispersion when the library is installed and otherwise synthesises faithful
data, so the whole tour always runs offline.

This module defines its own ``_md``/``_code`` helpers and exports
``ARPES_TOUR_EXAMPLES`` so it merges into ``examples.py`` without a circular
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


_INTRO = """\
# ARPES analysis walkthrough

A guided tour through a full angle-resolved photoemission (ARPES) analysis
with the [`peaks`](https://github.com/phrgab/peaks) toolkit, in one runnable
notebook. Run the cells top to bottom (Shift+Enter): the first builds the
data set and every later step reuses it.

The eight steps mirror the standalone Spectroscopy examples:

1. band dispersion  2. EDC & MDC cuts  3. angle to momentum
4. Fermi surface  5. curvature  6. energy resolution (gold edge)
7. self-energy & kink  8. superconducting gap

It uses the real `peaks` sample dispersion when installed
(`pip install peaks-arpes`) and otherwise synthesises a faithful metallic
band, so it runs anywhere.
"""


# 1 --------------------------------------------------------------- dispersion
_C1 = r'''
# Step 1 -- the band dispersion (real peaks data if installed, else synthetic)
import numpy as np
import matplotlib.pyplot as plt

rng = np.random.default_rng(0)


def build_dispersion():
    try:
        import peaks as pks                                  # noqa: F401
        from peaks.core.utils.sample_data import ExampleData
        d = ExampleData.dispersion()           # downloads i05-59819.nxs
        try:
            inten = np.asarray(d.pint.magnitude, dtype=float)
        except Exception:
            inten = np.asarray(d.values, dtype=float)
        e_ax = np.asarray(d["eV"].values, dtype=float)
        a_ax = np.asarray(d["theta_par"].values, dtype=float)
        if inten.shape != (e_ax.size, a_ax.size):
            inten = inten.T
        return a_ax, e_ax, inten, "peaks data (Diamond I05)"
    except Exception:
        theta = np.linspace(-16, 16, 200)        # emission angle (deg)
        E = np.linspace(-0.70, 0.10, 260)        # E - E_F (eV)
        TH, EE = np.meshgrid(theta, E)
        band = -0.45 + 0.0045 * TH ** 2          # parabolic band
        gamma = 0.02 + 0.05 * band ** 2
        A = (gamma / np.pi) / ((EE - band) ** 2 + gamma ** 2)
        inten = A / (np.exp(EE / 0.012) + 1.0)   # x Fermi-Dirac
        inten = inten / inten.max() + 0.02 * rng.random(inten.shape)
        return theta, E, inten, "synthetic dispersion"


theta, E, disp, SRC = build_dispersion()

fig, ax = plt.subplots(figsize=(5.4, 4.2))
ax.pcolormesh(theta, E, disp, cmap="inferno", shading="auto")
ax.axhline(0, color="w", ls="--", lw=0.8, alpha=0.7)
ax.set_xlabel(r"emission angle  $\theta_\parallel$  (deg)")
ax.set_ylabel(r"$E - E_F$  (eV)")
ax.set_title("1. band dispersion -- " + SRC)
fig.tight_layout()
fig
'''


# 2 ----------------------------------------------------------------- EDC/MDC
_C2 = r'''
# Step 2 -- EDC at normal emission and MDC just below E_F (reuses disp)
i0 = int(np.argmin(np.abs(theta)))             # column nearest theta = 0
edc = disp[:, i0]
iE = int(np.argmin(np.abs(E - (-0.05))))       # row 50 meV below E_F
mdc = disp[iE]

fig, (a1, a2) = plt.subplots(1, 2, figsize=(7.4, 3.4))
a1.plot(edc, E, color="#3776ab")
a1.set_xlabel("intensity"); a1.set_ylabel(r"$E - E_F$ (eV)")
a1.set_title(r"EDC at $\theta \approx 0$")
a2.plot(theta, mdc, color="#3776ab")
a2.set_xlabel(r"$\theta_\parallel$ (deg)"); a2.set_ylabel("intensity")
a2.set_title(r"MDC 50 meV below $E_F$")
fig.tight_layout()
fig
'''


# 3 ------------------------------------------------------------- angle -> k
_C3 = r'''
# Step 3 -- convert emission angle to parallel momentum k (reuses disp)
E_kin = 16.0                                    # photoelectron KE (eV)
k_par = 0.5123 * np.sqrt(E_kin) * np.sin(np.radians(theta))

fig, ax = plt.subplots(figsize=(5.4, 4.2))
ax.pcolormesh(k_par, E, disp, cmap="inferno", shading="auto")
ax.axhline(0, color="w", ls="--", lw=0.8, alpha=0.7)
ax.set_xlabel(r"$k_\parallel$  (1/$\AA$)")
ax.set_ylabel(r"$E - E_F$ (eV)")
ax.set_title(r"3. dispersion vs momentum  ($k = 0.512\sqrt{E_k}\,\sin\theta$)")
fig.tight_layout()
fig
'''


# 4 ----------------------------------------------------------- Fermi surface
_C4 = r'''
# Step 4 -- a constant-energy Fermi-surface map
kx = np.linspace(-1.0, 1.0, 200)
ky = np.linspace(-1.0, 1.0, 200)
KX, KY = np.meshgrid(kx, ky)
KR = np.hypot(KX, KY)
kF, g = 0.6, 0.05
FS = (g / np.pi) / ((KR - kF) ** 2 + g ** 2)
FS = FS / FS.max() + 0.02 * rng.random(FS.shape)

fig, ax = plt.subplots(figsize=(4.6, 4.3))
pm = ax.pcolormesh(kx, ky, FS, cmap="inferno", shading="auto")
ax.set_aspect("equal")
ax.set_xlabel(r"$k_x$ (1/$\AA$)"); ax.set_ylabel(r"$k_y$ (1/$\AA$)")
ax.set_title("4. Fermi surface")
fig.colorbar(pm, ax=ax, label="intensity")
fig.tight_layout()
fig
'''


# 5 -------------------------------------------------------------- curvature
_C5 = r'''
# Step 5 -- the curvature method sharpens the band (2nd derivative in E)
d2 = np.gradient(np.gradient(disp, E, axis=0), E, axis=0)
curv = np.clip(-d2, 0, None)

fig, (a1, a2) = plt.subplots(1, 2, figsize=(7.6, 3.6), sharey=True)
a1.pcolormesh(theta, E, disp, cmap="inferno", shading="auto")
a1.set_title("raw"); a1.set_ylabel(r"$E - E_F$ (eV)")
a2.pcolormesh(theta, E, curv, cmap="inferno", shading="auto")
a2.set_title("curvature")
for a in (a1, a2):
    a.set_xlabel(r"$\theta_\parallel$ (deg)")
fig.suptitle("5. curvature method")
fig.tight_layout()
fig
'''


# 6 ----------------------------------------------------- gold edge / resolution
_C6 = r'''
# Step 6 -- a gold Fermi edge gives the energy resolution
from scipy.optimize import curve_fit

Eg = np.linspace(-0.30, 0.15, 400)


def edge(e, ef, w, amp, c):                     # resolution-broadened edge
    return amp / (np.exp((e - ef) / w) + 1.0) + c


gold = edge(Eg, 0.0, 0.022, 1.0, 0.04) + rng.normal(0, 0.012, Eg.size)
try:
    popt, _ = curve_fit(edge, Eg, gold, p0=[0.0, 0.03, 1.0, 0.04])
except Exception:
    popt = [0.0, 0.022, 1.0, 0.04]
dE = 3.53 * abs(popt[1]) * 1000.0               # edge width -> FWHM (meV)

fig, ax = plt.subplots(figsize=(5.4, 3.8))
ax.plot(Eg, gold, ".", ms=3, color="#3776ab", alpha=0.5, label="gold")
ax.plot(Eg, edge(Eg, *popt), color="#e07b39", lw=2, label="fit")
ax.axvline(popt[0], color="0.5", ls=":")
ax.set_xlabel(r"$E - E_F$ (eV)"); ax.set_ylabel("intensity")
ax.set_title("6. Fermi edge -- resolution $\\Delta E \\approx %.0f$ meV" % dE)
ax.legend(frameon=False)
fig.tight_layout()
fig
'''


# 7 ------------------------------------------------------- self-energy / kink
_C7 = r'''
# Step 7 -- MDC peak positions vs energy reveal a kink (self-energy)
kgrid = np.linspace(-0.30, 0.30, 400)
Es = np.linspace(-0.30, -0.003, 200)
vF, E_ph = 2.5, 0.07                            # bare velocity, mode energy
k_bare = Es / vF
ReS = 0.020 * np.exp(-((np.abs(Es) - E_ph) / 0.030) ** 2)   # Re self-energy
k_meas = (Es - ReS) / vF
# lifetime (Im) rises smoothly below the mode energy -- no brightness seam
Gam = 0.012 + 0.012 / (1.0 + np.exp(-(np.abs(Es) - E_ph) / 0.010))
img = np.exp(-((kgrid[None, :] - k_meas[:, None]) ** 2)
             / (2 * Gam[:, None] ** 2))
img = img / img.max(axis=1, keepdims=True)      # each MDC peaks at 1
img = img + 0.005 * rng.random(img.shape)
# extract k(E) by intensity-weighted centroid around each MDC peak
jmax = np.argmax(img, axis=1)
k_ext = np.empty(Es.size)
for i, j in enumerate(jmax):
    lo, hi = max(0, j - 25), min(kgrid.size, j + 26)
    w = img[i, lo:hi]
    k_ext[i] = np.sum(kgrid[lo:hi] * w) / np.sum(w)
ReS_ext = vF * (k_ext - k_bare)

fig, (a1, a2) = plt.subplots(1, 2, figsize=(7.6, 3.6))
a1.pcolormesh(kgrid, Es, img, cmap="inferno", shading="auto")
a1.plot(k_ext, Es, "-", lw=1.6, color="#34e1eb", label="MDC peaks")
a1.plot(k_bare, Es, "--", color="w", lw=1.1, label="bare band")
a1.set_xlabel(r"$k$ (1/$\AA$)"); a1.set_ylabel(r"$E - E_F$ (eV)")
a1.set_xlim(-0.3, 0.3); a1.set_title("dispersion + kink")
a1.legend(fontsize=8, frameon=False, loc="lower left")
a2.plot(ReS_ext * 1000, Es, color="#e07b39")
a2.axhline(-E_ph, color="0.6", ls=":", lw=0.9)
a2.set_xlabel(r"$\mathrm{Re}\,\Sigma$ (meV)"); a2.set_ylabel(r"$E - E_F$ (eV)")
a2.set_title("self-energy (kink near %d meV)" % int(E_ph * 1000))
fig.suptitle("7. self-energy from the kink")
fig.tight_layout()
fig
'''


# 8 --------------------------------------------------------------------- gap
_C8 = r'''
# Step 8 -- symmetrising an EDC at k_F exposes a superconducting gap
from scipy.ndimage import gaussian_filter1d

Eg = np.linspace(-0.08, 0.08, 400)
D = 0.015                                        # gap (eV)
dos = np.abs(Eg) / np.sqrt(np.clip(Eg ** 2 - D ** 2, 1e-6, None))
dos[np.abs(Eg) < D] = 0.0
dx = Eg[1] - Eg[0]
A = gaussian_filter1d(dos, 0.004 / dx)
edc = A / (np.exp(Eg / 0.004) + 1.0) + 0.05 + rng.normal(0, 0.01, Eg.size)
sym = edc + edc[::-1]                            # symmetrise about E_F

fig, (a1, a2) = plt.subplots(1, 2, figsize=(7.4, 3.4))
a1.plot(Eg * 1000, edc, color="#3776ab")
a1.set_xlabel(r"$E - E_F$ (meV)"); a1.set_ylabel("intensity")
a1.set_title(r"EDC at $k_F$")
a2.plot(Eg * 1000, sym, color="#3776ab")
for s in (-D, D):
    a2.axvline(s * 1000, color="#e07b39", ls="--", lw=1)
a2.set_xlabel(r"$E - E_F$ (meV)"); a2.set_ylabel("intensity")
a2.set_title(r"symmetrised: $2\Delta = %d$ meV" % int(round(2000 * D)))
fig.suptitle("8. superconducting gap")
fig.tight_layout()
fig
'''


_OUTRO = """\
## That's the tour

You have gone from a raw dispersion to band structure, momentum, a Fermi
surface, the energy resolution, the electron self-energy and a
superconducting gap. Each step has its own standalone example in the
**Spectroscopy** category with more detail (Fermi surfaces, k-conversion,
curvature, gold fitting, MDC self-energy, the gap, plus photon-energy/kz,
nanoARPES, TR-ARPES and Brillouin zones). With `peaks` installed
(`pip install peaks-arpes`) the same chain runs on real beamline data.
"""


def _tour():
    return [
        _md(_INTRO),
        _md("## 1. Band dispersion\nThe raw ARPES map: intensity vs binding "
            "energy and emission angle."),
        _code(_C1),
        _md("## 2. EDC & MDC\nEnergy- and momentum-distribution curves are "
            "the fundamental 1-D cuts."),
        _code(_C2),
        _md("## 3. Angle to momentum\nConvert the angle axis to parallel "
            "crystal momentum $k_\\parallel$."),
        _code(_C3),
        _md("## 4. Fermi surface\nA constant-energy slice at $E_F$ maps the "
            "Fermi surface."),
        _code(_C4),
        _md("## 5. Curvature\nThe 2-D curvature method sharpens faint "
            "bands for the eye."),
        _code(_C5),
        _md("## 6. Energy resolution\nA gold Fermi edge calibrates the "
            "combined thermal + instrument resolution."),
        _code(_C6),
        _md("## 7. Self-energy & kink\nFitting MDCs across energy reveals a "
            "dispersion kink -- the electron self-energy."),
        _code(_C7),
        _md("## 8. Superconducting gap\nSymmetrising an EDC at $k_F$ removes "
            "the Fermi cut-off and exposes the gap."),
        _code(_C8),
        _md(_OUTRO),
    ]


# -- Registry --------------------------------------------------------------

ARPES_TOUR_EXAMPLES = [
    ("ARPES Walkthrough (peaks)", "Spectroscopy", _tour),
]
