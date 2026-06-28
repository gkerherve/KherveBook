"""The XPS (lmfitxps) and XRD example sets register and are physically sane.

Execution of every example (loads + runs all code cells without error) is
covered by tests/test_notebook.py::test_examples_run_clean, which is
parametrised over the whole EXAMPLES registry.

Copyright (C) 2026 Gwilherm Kerherve

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.
"""

import pytest


def test_xps_examples_registered():
    from khervebook.examples import EXAMPLES
    names = [n for n, _c, _b in EXAMPLES]
    assert len(names) == len(set(names))            # no duplicate names
    xps = {n for n, c, _b in EXAMPLES if c == "XPS"}
    assert {
        "Spin-Orbit Doublet (lmfitxps)",
        "Shirley vs Tougaard (lmfitxps)",
        "Chemical-State Fit (lmfitxps)",
        "XPS Survey & Element ID (XPS)",
        "Fermi Edge & Resolution (lmfitxps)",
        "XPS Depth Profile (XPS)",
        "Angle-Resolved XPS (XPS)",
        "Auger Parameter / Wagner Plot (XPS)",
    } <= xps


def test_xrd_examples_registered():
    from khervebook.examples import EXAMPLES
    xrd = {n for n, c, _b in EXAMPLES if c == "XRD"}
    assert {
        "Powder XRD Pattern (XRD)",
        "Peak Indexing & Lattice (XRD)",
        "Scherrer Crystallite Size (XRD)",
        "Phase Identification (XRD)",
        "Williamson-Hall Analysis (XRD)",
        "Pattern Refinement (XRD)",
    } <= xrd


def test_ftir_examples_registered():
    from khervebook.examples import EXAMPLES
    ftir = {n for n, c, _b in EXAMPLES if c == "FTIR"}
    assert {
        "FTIR Spectrum & Functional Groups (FTIR)",
        "FTIR Baseline & Peak Fit (FTIR)",
        "FTIR Beer-Lambert Quantification (FTIR)",
    } <= ftir


def test_doublet_partner_sits_at_higher_binding_energy():
    """Guards the Au 4f example's physics: the weaker spin-orbit partner
    (4f5/2) must lie at HIGHER binding energy than 4f7/2. lmfitxps places
    the partner at center - soc, so the example uses a negative soc."""
    np = pytest.importorskip("numpy")
    try:
        from lmfitxps.models import ConvGaussianDoniachDublett
    except ImportError:
        pytest.skip("lmfitxps not installed")
    from scipy.signal import find_peaks
    m = ConvGaussianDoniachDublett(prefix="d_")
    p = m.make_params()
    p["d_center"].set(84.0); p["d_amplitude"].set(1000.0); p["d_sigma"].set(0.2)
    p["d_gamma"].set(0.02); p["d_gaussian_sigma"].set(0.3)
    p["d_soc"].set(-3.67)                # negative => partner at higher BE
    p["d_height_ratio"].set(0.75); p["d_fct_coster_kronig"].set(1.0)
    x = np.linspace(78, 94, 4000)
    y = m.eval(p, x=x)
    pk, _ = find_peaks(y, height=y.max() * 0.2)
    pos, h = x[pk], y[pk]
    assert len(pos) == 2
    tall, weak = pos[h.argmax()], pos[h.argmin()]
    assert abs(tall - 84.0) < 0.3        # 4f7/2 (intense) at 84 eV
    assert weak > tall + 3.0             # 4f5/2 (weaker) at higher BE
