"""Kratos .kal import (khervebook.instruments.kratos).

No real .kal ships with the repo, so the files are built here in the
layout KherveFitting's ``parse_kal_file`` reads.

Copyright (C) 2026 Gwilherm Kerherve

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.
"""

import numpy as np
import pytest

from khervebook import kfitio
from khervebook.instruments import kfitwrite, kratos

TRANS_KE = [1000.0, 1200.0, 1400.0]
TRANS_T = [0.5, 0.65, 0.7]


def _spectrum(name, start_ke, step, counts, transmission=True,
              casa=True):
    lines = [
        "Dataset filename = sample.kal",
        f"Object name = {name}",
        "Date Acquired = 2024-03-05 14:22:01",
        "Chemical symbol or formula = " + name.split('/')[0].split()[0],
        "Transition or charge state = "
        + (name.split('/')[0].split()[1]
           if len(name.split('/')[0].split()) > 1 else ""),
        "# Sweeps completed = 4",
        "Pass energy = 20",
        "Abscissa label = Kinetic Energy",
        "Abscissa units = eV",
        f"Spectrum scan start = {start_ke} eV",
        f"Spectrum scan step size = {step} eV",
        "Dwell time = 0.1 seconds",
        "Ordinate values = {" + ", ".join(f"{c:g}" for c in counts) + "}",
    ]
    if transmission:
        lines += [
            "Transmission Function Object (ke,t)",
            "Transmission Function Kinetic Energy = {"
            + ", ".join(f"{v:g}" for v in TRANS_KE) + "}",
            "Transmission Function Value          = {"
            + ", ".join(f"{v:g}" for v in TRANS_T) + "}",
        ]
    if casa:
        lines += [
            "Casa Info Follows",
            "Wafer A",
            "(12.5, 3.0) Angle: 0",
            "Lens Mode: Hybrid",
            "Charge Balance = 2.5 V: Filament Current = 0.4 A",
        ]
    return "\n".join(lines) + "\n"


def make_kal(path):
    c1s = [100 + 10 * i for i in range(30)]
    survey = [500 + (i % 7) * 3 for i in range(60)]
    text = (
        "Dataset filename = sample.kal\n"
        "Object name = Sample Position 1 / 1\n"
        "Stage Position Name = Pos 1\n"
        "Stage X Rotation = 45\n"
        + _spectrum("C 1s / 2", 1186.67, 0.1, c1s)
        + _spectrum("Wide Survey / 3", 1000.0, 10.0, survey, casa=False)
        + _spectrum("C 1s Scan / 4", 1186.67, 0.1, c1s)
        # no transmission function: KherveFitting skips it
        + _spectrum("O 1s / 5", 950.0, 0.1, c1s, transmission=False)
        + "Dataset filename = sample.kal\n"
        "Object name = Sample Position 2 / 6\n"
        "Stage Position Name = Pos 2\n"
        "Stage X Rotation = 30\n"
        + _spectrum("N 1s / 7", 1086.67, 0.2, c1s[:20])
    )
    path.write_text(text)
    return path


def test_kal_sheets_and_values(tmp_path):
    levels = kratos.read_kal(str(make_kal(tmp_path / "s.kal")))
    assert list(levels) == ["C1s", "Survey", "C1s1", "N1s"]

    c1s = levels["C1s"]
    assert len(c1s["B.E."]) == 30
    assert c1s["B.E."][0] == pytest.approx(1486.67 - 1186.67)
    # KE ascending -> BE descending
    assert c1s["B.E."][0] > c1s["B.E."][-1]
    ke = 1486.67 - np.array(c1s["B.E."])
    t = np.interp(ke, TRANS_KE, TRANS_T)
    assert c1s["Transmission"] == pytest.approx(list(t))
    # inverted mapping: plotted (corrected) trace in 'Raw Data'
    assert c1s["Corrected Data"][:3] == [100.0, 110.0, 120.0]
    assert c1s["Raw Data"] == pytest.approx(
        list(np.array(c1s["Corrected Data"]) / t))

    info = c1s["ExperimentalInfo"]
    assert list(info) == kratos.KAL_FIELDS
    assert info["Sample ID"] == "Pos 1"
    assert info["Sample Tilt"] == "45"
    assert info["Species & Transition"] == "C 1s"
    assert info["Date"] == "2024-03-05" and info["Time"] == "14:22:01"
    assert info["Pass Energy"] == "20"
    assert info["Num Y Values"] == "30"
    assert info["Collection Time"] == "0.1"
    assert info["Casa Sample Name"] == "Wafer A"
    assert info["Stage Position"] == "(12.5, 3.0)"
    assert info["Lens Mode"] == "Hybrid"
    assert info["Charge Balance"] == "2.5 V"
    assert info["# Comment Lines"] == "5"

    assert levels["N1s"]["ExperimentalInfo"]["Sample ID"] == "Pos 2"
    assert levels["N1s"]["ExperimentalInfo"]["Sample Tilt"] == "30"
    assert levels["Survey"]["ExperimentalInfo"]["Casa Sample Name"] == ""


def test_transmission_extrapolates(tmp_path):
    levels = kratos.read_kal(str(make_kal(tmp_path / "s.kal")))
    t = levels["Survey"]["Transmission"]
    # KE 1000…1590: beyond 1400 the last segment's line continues
    slope = (TRANS_T[2] - TRANS_T[1]) / (TRANS_KE[2] - TRANS_KE[1])
    assert t[-1] == pytest.approx(TRANS_T[2] + slope * (1590 - 1400))


def test_interp_matches_scipy():
    interpolate = pytest.importorskip("scipy.interpolate")
    xp = [5.0, 1.0, 3.0, 9.0]
    fp = [2.0, 0.5, 1.0, 7.0]
    x = np.linspace(-3, 14, 57)
    ref = interpolate.interp1d(xp, fp, kind="linear", bounds_error=False,
                               fill_value="extrapolate")(x)
    assert kratos._interp_extrapolate(x, xp, fp) == pytest.approx(ref)


def test_kfit_roundtrip(tmp_path):
    levels = kratos.read_kal(str(make_kal(tmp_path / "s.kal")))
    proj = kfitio.read_bytes(kfitwrite.to_bytes(levels))
    assert proj.names == list(levels)
    sheet = proj.sheets[0]
    assert sheet.x == pytest.approx(levels["C1s"]["B.E."], abs=1e-9)
    assert sheet.y == pytest.approx(levels["C1s"]["Raw Data"])


def test_not_a_kal(tmp_path):
    p = tmp_path / "x.kal"
    p.write_text("hello\nworld\n")
    with pytest.raises(ValueError):
        kratos.read_kal(str(p))


def test_format_entry():
    (fmt,) = kratos.FORMATS
    assert (fmt.technique, fmt.group, fmt.exts) == ("XPS", "Kratos",
                                                    (".kal",))
    assert fmt.sniff is None and not fmt.multi
