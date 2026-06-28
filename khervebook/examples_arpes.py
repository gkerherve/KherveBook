"""ARPES example using the ``peaks`` library's bundled sample data.

A self-contained companion to ``examples.py`` (Examples menu,
"Spectroscopy" category). ``peaks`` (``pip install peaks-arpes``) is the
angle-resolved photoemission toolkit from the King group at the
University of St Andrews; it ships a Diamond Light Source beamline-I05
scan, ``i05-59819.nxs``, exposed through
``peaks.core.utils.sample_data.ExampleData.dispersion()``.

The code cell loads that real dataset when ``peaks`` is installed, and
otherwise synthesises a faithful metallic band dispersion with NumPy so
the example always runs offline. It then does the two textbook ARPES
cuts — an energy distribution curve (EDC) and a momentum distribution
curve (MDC).

This module defines its own ``_md``/``_code`` helpers and exports
``ARPES_EXAMPLES`` so it merges into ``examples.py`` without a circular
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
# ARPES with the `peaks` library

[`peaks`](https://github.com/phrgab/peaks) is a Python toolkit for
**angle-resolved photoemission spectroscopy (ARPES)** from the King group
at the University of St Andrews
([arXiv:2508.04803](https://arxiv.org/abs/2508.04803)). ARPES maps the
electronic **band structure** of a crystal by recording photoemitted-
electron intensity versus binding energy and emission angle (which maps
to crystal momentum **k**) — i.e. the spectral function *A*(**k**, ω).

The library ships sample data from the **Diamond Light Source** beamline
**I05**. The canonical way to load the tutorial dispersion is:

```python
import peaks as pks
from peaks.core.utils.sample_data import ExampleData
disp = ExampleData.dispersion()   # downloads i05-59819.nxs from Zenodo
disp.plot()                        # 2-D ARPES intensity map
```

Install it with `pip install peaks-arpes`. The cell below uses that real
data when `peaks` is available, and otherwise synthesises a faithful
metallic dispersion so the example always runs.
"""


_DISPERSION = r'''
# ARPES dispersion from the `peaks` library's bundled example scan.
# peaks ships a Diamond Light Source I05 measurement, i05-59819.nxs, via
# ExampleData.dispersion(). If peaks isn't installed we synthesise a
# faithful dispersion so the example still produces a real ARPES map.
import numpy as np
import matplotlib.pyplot as plt


def load_dispersion():
    """Return (angle_deg, E_minus_EF, intensity[E, angle], source)."""
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
        return a_ax, e_ax, inten, "peaks data - Diamond I05 (i05-59819.nxs)"
    except Exception:
        rng = np.random.default_rng(0)
        theta = np.linspace(-16, 16, 220)       # emission angle (deg)
        E = np.linspace(-0.70, 0.10, 300)       # E - E_F (eV)
        TH, EE = np.meshgrid(theta, E)
        band = -0.45 + 0.0045 * TH ** 2         # parabolic band minimum
        gamma = 0.02 + 0.05 * band ** 2         # lifetime broadening
        spectral = (gamma / np.pi) / ((EE - band) ** 2 + gamma ** 2)
        fermi = 1.0 / (np.exp(EE / 0.012) + 1.0)  # Fermi-Dirac cut-off
        inten = spectral * fermi
        inten = inten / inten.max() + 0.02 * rng.random(inten.shape)
        return theta, E, inten, "synthetic dispersion (pip install peaks-arpes)"


theta, E, I, source = load_dispersion()

fig, ax = plt.subplots(figsize=(5.4, 4.3))
pm = ax.pcolormesh(theta, E, I, cmap="inferno", shading="auto")
ax.axhline(0, color="w", ls="--", lw=0.8, alpha=0.7)        # Fermi level
ax.set_xlabel(r"emission angle  $\theta_\parallel$  (deg)")
ax.set_ylabel(r"$E - E_F$  (eV)")
ax.set_title("ARPES band dispersion")
fig.colorbar(pm, ax=ax, label="intensity (arb.)")
fig.text(0.01, 0.005, source, fontsize=7, color="0.45")
fig.tight_layout()
fig
'''


_EDC_MDC = r'''
# Two standard ARPES cuts through the dispersion loaded above:
#   EDC - energy distribution curve at normal emission (theta ~ 0)
#   MDC - momentum distribution curve 50 meV below E_F
i0 = int(np.argmin(np.abs(theta)))             # column nearest theta = 0
edc = I[:, i0]
e_bottom = E[int(np.argmax(edc))]              # quasiparticle binding energy

iE = int(np.argmin(np.abs(E - (-0.05))))       # slice 50 meV below E_F
mdc = I[iE]
neg, pos = theta < 0, theta > 0
kF_neg = theta[neg][int(np.argmax(mdc[neg]))]  # band crossings = +/- k_F
kF_pos = theta[pos][int(np.argmax(mdc[pos]))]

fig, (a1, a2) = plt.subplots(1, 2, figsize=(7.4, 3.4))
a1.plot(edc, E, color="#3776ab")
a1.axhline(e_bottom, color="#e07b39", ls="--", lw=1)
a1.set_xlabel("intensity (arb.)")
a1.set_ylabel(r"$E - E_F$ (eV)")
a1.set_title("EDC at normal emission\nband bottom ~ %.0f meV" % (e_bottom * 1000))

a2.plot(theta, mdc, color="#3776ab")
for k in (kF_neg, kF_pos):
    a2.axvline(k, color="#e07b39", ls="--", lw=1)
a2.set_xlabel(r"emission angle  $\theta_\parallel$  (deg)")
a2.set_ylabel("intensity (arb.)")
a2.set_title(r"MDC 50 meV below $E_F$" + "\n"
             + r"$\theta_F \approx \pm$%.1f deg" % abs(kF_pos))
fig.tight_layout()
fig
'''


def _arpes_dispersion():
    return [_md(_INTRO), _code(_DISPERSION), _code(_EDC_MDC)]


# -- Registry --------------------------------------------------------------

ARPES_EXAMPLES = [
    # (name, category, builder)
    ("ARPES Dispersion (peaks)", "Spectroscopy", _arpes_dispersion),
]
