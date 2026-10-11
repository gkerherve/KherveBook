"""Tests for the BET isotherm reader (khervebook/instruments/bet.py).

Synthetic Micromeritics-style and bare P/P0 - quantity exports are read
into KherveFitting core levels and round-tripped through the .kfit
writer and `kfitio`.

Copyright (C) 2026 Gwilherm Kerherve

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.
"""

import io

import pytest

from khervebook import kfitio
from khervebook.instruments import bet, kfitwrite

UP = [0.05, 0.10, 0.15, 0.20, 0.25, 0.30, 0.50, 0.80, 0.99]
DOWN = [0.90, 0.70, 0.40, 0.20]


def make_micromeritics(path):
    """Relative pressure, absolute pressure (mmHg), quantity (cm3/g)."""
    lines = ["Sample: Silica SBA-15",
             "Operator: gk",
             "Analysis Adsorptive: N2",
             "Analysis Bath Temp.: 77.3 K",
             "",
             "Relative Pressure (P/Po)\tAbsolute Pressure (mmHg)\t"
             "Quantity Adsorbed (cm3/g STP)"]
    for x in UP + DOWN:
        lines.append(f"{x:.4f}\t{x * 760:.2f}\t{100 + 200 * x:.3f}")
    path.write_text("\n".join(lines) + "\n")
    return path


def make_absolute(path):
    lines = ["P0 = 760 mmHg"]
    for x in UP:
        lines.append(f"{x * 760:.3f},{50 + 100 * x:.3f}")
    path.write_text("\n".join(lines) + "\n")
    return path


def test_formats_declared():
    assert [f.technique for f in bet.FORMATS] == ["BET", "BET"]
    assert bet.FORMATS[0].label == "Isotherm file(s) (.csv/.txt/.dat)"
    assert bet.FORMATS[1].multi
    assert all(f.sniff("a.csv") is False for f in bet.FORMATS)


def test_micromeritics(tmp_path):
    levels = bet.read_file(make_micromeritics(tmp_path / "sba15.txt"))
    assert list(levels) == ["BET"]
    s = levels["BET"]
    assert s["B.E."] == UP + DOWN
    assert s["Raw Data"][0] == pytest.approx(110.0)   # last column
    assert s["BET_Branch"] == [1.0] * len(UP) + [2.0] * len(DOWN)
    assert s["BET_X_Label"] == "Relative pressure (P/P$_0$)"
    assert s["BET_Y_Label"] == "Quantity adsorbed (cm$^3$/g STP)"
    assert s["BET_Label"] == "sba15"
    assert s["BET_Source"] == "sba15"
    assert s["Fitting"] == {"Peaks": {}}
    info = s["ExperimentalInfo"]
    assert info["Technique"] == "Gas Adsorption (BET)"
    assert info["Source Sheet"] == "sba15"
    assert info["Source File"] == "sba15.txt"
    assert info["Branches"] == "adsorption + desorption"
    assert info["Sample"] == "Silica SBA-15"
    assert info["Adsorptive"] == "N2"
    assert info["Operator"] == "gk"
    assert info["P/P0 Range"] == "0.050 - 0.990"


def test_absolute_pressure_with_p0(tmp_path):
    s = bet.read_file(make_absolute(tmp_path / "abs.csv"))["BET"]
    assert s["B.E."][0] == pytest.approx(0.05)
    assert s["Raw Data"][0] == pytest.approx(55.0)
    assert s["ExperimentalInfo"]["Branches"] == "adsorption only"


def test_no_isotherm(tmp_path):
    p = tmp_path / "x.csv"
    p.write_text("\n".join(f"{i * 10},{i}" for i in range(10)))
    with pytest.raises(ValueError):
        bet.read_file(p)


def test_folder_and_roundtrip(tmp_path):
    make_micromeritics(tmp_path / "a.txt")
    make_absolute(tmp_path / "b.csv")
    (tmp_path / "readme.md").write_text("ignored")
    levels = bet.read_folder([tmp_path])
    assert list(levels) == ["BET", "BET1"]
    data = kfitwrite.to_bytes(levels)
    proj = kfitio.read_bytes(data)
    assert proj.names == ["BET", "BET1"]
    sh = proj.sheet("BET")
    assert sh.raw["BET_X_Label"] == "Relative pressure (P/P$_0$)"
    assert list(sh.x) == pytest.approx(UP + DOWN)
    import h5py
    with h5py.File(io.BytesIO(data), "r") as f:
        assert list(f["core_levels/cl_0/BET_Branch"][:])[-1] == 2.0
