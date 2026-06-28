"""The ARPES example (peaks library data) registers, runs and recovers
the band — using the synthetic fallback when `peaks` isn't installed.

Copyright (C) 2026 Gwilherm Kerherve

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.
"""


def test_arpes_example_registered_and_unique():
    from khervebook.examples import EXAMPLES
    names = [n for n, _c, _b in EXAMPLES]
    assert "ARPES Dispersion (peaks)" in names
    assert len(names) == len(set(names))            # no duplicate names
    assert "Spectroscopy" in {c for _n, c, _b in EXAMPLES}


def test_all_peaks_capabilities_have_an_example():
    """One Spectroscopy example per peaks tutorial / capability."""
    from khervebook.examples import EXAMPLES
    spectro = {n for n, c, _b in EXAMPLES if c == "Spectroscopy"}
    expected = {
        "ARPES Dispersion (peaks)",          # getting started + plotting
        "ARPES Fermi Surface (peaks)",       # constant-energy maps
        "Angle to Momentum (peaks)",         # k-conversion
        "Band Curvature (peaks)",            # data processing
        "Fermi Edge & Resolution (peaks)",   # gold fit / resolution
        "EDC Peak Fitting (peaks)",          # lmfit-style peak fitting
        "XPS Core Levels (peaks)",           # XPS
        "TR-ARPES (peaks)",                  # time-resolved
        "nanoARPES Spatial Map (peaks)",     # spatial mapping
        "Brillouin Zone (peaks)",            # structure / BZs
    }
    assert expected <= spectro, expected - spectro


def test_arpes_example_runs_and_recovers_band():
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    from khervebook.examples_arpes import _arpes_dispersion
    cells = _arpes_dispersion()
    assert [c["type"] for c in cells] == ["markdown", "code", "code"]

    ns = {}
    for cell in cells:
        if cell["type"] == "code":
            exec(cell["source"], ns)                # noqa: S102 (test fixture)

    # Synthetic path (peaks not installed): the EDC must find the band
    # bottom near -0.45 eV and the MDC the +/- k_F crossings near +/-9-10 deg.
    assert -0.50 < ns["e_bottom"] < -0.40
    assert 8.0 < abs(ns["kF_pos"]) < 11.0
    assert 8.0 < abs(ns["kF_neg"]) < 11.0
    assert ns["I"].shape == (ns["E"].size, ns["theta"].size)
    assert plt.get_fignums()                        # a figure was drawn
    plt.close("all")
