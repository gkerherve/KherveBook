"""Igor Pro .itx / .dat import (instruments/igor), on synthetic files in
the layout ``Igor_Import.py`` expects.

Copyright (C) 2026 Gwilherm Kerherve

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.
"""

import numpy as np
import pytest

from khervebook import kfitio
from khervebook.instruments import igor, kfitwrite


def _wave(name, values, start=None, step=None):
    out = [f"WAVES/D\t'{name}'", "BEGIN"]
    out += [f"\t{v:.6g}" for v in values]
    out.append("END")
    if start is not None:
        out.append(f"X SetScale/P x {start},{step},\"\", '{name}'; "
                   f"SetScale y 0,0,\"\", '{name}'")
    return out


def write_itx(path):
    """Two samples (one normalised), a fit trace, and a VB wave."""
    c = 0.2 + 0.5 * np.exp(-((np.arange(21) * 0.5 + 280 - 285) / 1) ** 2)
    o = 1000 + 500 * np.exp(-((np.arange(11) * 1.0 + 525 - 530) / 1) ** 2)
    lines = ["IGOR"]
    lines += _wave("[All C 1s] S1", c, 280, 0.5)
    lines += _wave("[All C 1s] S1 bck", c * 0, 280, 0.5)
    lines += _wave("[All O 1s] S2", o, 525, 1.0)
    lines += _wave("sample_V(0 to 10)", np.linspace(5, 50, 6), 0, 2)
    path.write_text("\n".join(lines) + "\n")
    return path, c, o


def write_dat(path):
    """Ni 2p: col 0 = BE (> 500) + col 1 counts; O 1s: empty-header BE in
    col 2 + counts in col 3; col 4 a fit trace."""
    be_ni = np.arange(850, 860.5, 0.5)
    be_o = np.arange(525, 535.5, 0.5)
    ni = 2000 + 10 * np.arange(len(be_ni))
    o = 0.5 + 0.01 * np.arange(len(be_o))
    header = ["[All Ni 2p] A", "", "", "[All O 1s] B", "[All O 1s] B bck"]
    rows = ["\t".join(header)]
    for i in range(len(be_ni)):
        rows.append("\t".join(f"{v:g}" for v in
                              (be_ni[i], ni[i], be_o[i], o[i], 0)))
    path.write_text("\n".join(rows) + "\n")
    return path, be_ni, ni, be_o, o


def _roundtrip(levels):
    proj = kfitio.read_bytes(kfitwrite.to_bytes(levels))
    assert proj.names == list(levels)
    return proj


def test_itx(tmp_path):
    path, c, o = write_itx(tmp_path / "run.itx")
    levels = igor.read_itx(path)
    # sorted wave names; the fit trace is skipped; "<core><index>"
    assert list(levels) == ["C1s0", "O1s1", "VB_0to102"]
    c1s = levels["C1s0"]
    assert c1s["B.E."][0] == 290.0 and c1s["B.E."][-1] == 280.0
    # max < 100: scaled x10000, written as two-decimal text
    assert c1s["Raw Data"] == [float(f"{v * 10000:.2f}") for v in c[::-1]]
    assert levels["O1s1"]["Raw Data"] == [float(f"{v:.2f}") for v in o[::-1]]
    assert "experimental_description" not in c1s
    proj = _roundtrip(levels)
    assert proj.sheet("C1s0").x[0] == 290.0


def test_itx_rejects_non_igor(tmp_path):
    bad = tmp_path / "x.itx"
    bad.write_text("not igor\n")
    with pytest.raises(ValueError, match="IGOR"):
        igor.read_itx(bad)


def test_dat(tmp_path):
    path, be_ni, ni, be_o, o = write_dat(tmp_path / "export.dat")
    assert igor.sniff_dat(path)
    levels = igor.read_dat(path)
    assert list(levels) == ["Ni2p0", "O1s1"]
    assert levels["Ni2p0"]["B.E."] == list(be_ni[::-1])
    assert levels["Ni2p0"]["Raw Data"] == [float(v) for v in ni[::-1]]
    assert levels["O1s1"]["B.E."] == list(be_o[::-1])
    assert levels["O1s1"]["Raw Data"] == pytest.approx(
        [v * 10000 for v in o[::-1]])
    _roundtrip(levels)


def test_dat_sniff(tmp_path):
    plain = tmp_path / "plain.dat"
    plain.write_text("binding_energy\tintensity\n285\t10\n")
    assert not igor.sniff_dat(plain)
    with pytest.raises(ValueError, match="Igor"):
        igor.read_dat(plain)


def test_formats():
    by_label = {f.label: f for f in igor.FORMATS}
    assert by_label["Igor ITX (.itx)"].sniff is None
    assert by_label["Igor data file (.dat)"].sniff is igor.sniff_dat
    assert all(f.group == "Igor" for f in igor.FORMATS)
