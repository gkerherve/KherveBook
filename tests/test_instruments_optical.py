"""UV-Vis / PL / ellipsometry import (khervebook/instruments/optical.py).

Copyright (C) 2026 Gwilherm Kerherve

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.
"""

import numpy as np
import pytest

from khervebook import kfitio
from khervebook.instruments import kfitwrite, optical

WL = np.arange(300, 801, 5.0)


def _cary(path):
    lines = ["SampleA,,SampleB,", "Wavelength (nm),Abs,Wavelength (nm),%T"]
    for x in WL[::-1]:
        lines.append(f"{x},{np.exp(-((x - 500) / 40) ** 2):.5f},{x},"
                     f"{80 - 30 * np.exp(-((x - 450) / 30) ** 2):.4f}")
    lines += ["", "Collection Time: 1/1/2025", "Operator,me"]
    path.write_text("\n".join(lines) + "\n")
    return path


def test_cary_batch(tmp_path):
    levels = optical.read_uvvis([str(_cary(tmp_path / "batch.csv"))])
    assert list(levels) == ["UVvis", "UVvis1"]
    a, b = levels["UVvis"], levels["UVvis1"]
    assert len(a["B.E."]) == len(WL)
    assert a["B.E."][0] == 300.0                     # sorted ascending
    assert a["UVVIS_Y_Mode"] == "absorbance"
    assert a["UVVIS_Label"] == "SampleA"
    assert b["UVVIS_Y_Mode"] == "transmittance"
    assert b["UVVIS_Y_Label"] == "Transmittance (%)"
    assert a["ExperimentalInfo"]["Technique"] == "UV-Vis Spectrum"
    assert a["Fitting"] == {"Peaks": {}}


def test_generic_and_decimal_comma(tmp_path):
    p = tmp_path / "spec.txt"
    p.write_text("Excitation=350\nWavelength\tCounts\n" + "".join(
        f"{x:.1f}".replace(".", ",") + "\t"
        + f"{x / 1000:.3f}".replace(".", ",") + "\n" for x in WL))
    s = optical.read_pl(str(p))["PL"]
    assert s["B.E."][1] == 305.0
    assert s["Raw Data"][1] == pytest.approx(0.305)
    assert s["PL_Y_Label"] == "PL Intensity (a.u.)"
    assert s["PL_Label"] == "spec"
    uv = optical.read_uvvis(str(p))["UVvis"]
    assert uv["UVVIS_Y_Mode"] == "absorbance"        # max below 5


def test_woollam_multi_angle_in_ev(tmp_path):
    ev = np.linspace(1.5, 4.5, 31)
    lines = ["VASEmethod[Ellipsometric data]", "nm"]
    for aoi in (65.0, 70.0):
        for e in ev:
            lines.append(f"{e:.4f}\t{aoi}\t{20 + e:.4f}\t{100 + 10 * e:.4f}")
    p = tmp_path / "film.dat"
    p.write_text("\n".join(lines) + "\n")
    levels = optical.read_ellips([str(p)])
    assert list(levels) == ["Ellips", "Ellips~Delta", "Ellips1",
                            "Ellips~Delta1"]
    psi = levels["Ellips"]
    assert psi["ELLIPS_AOI_deg"] == 65.0
    assert psi["ELLIPS_Label"] == "film @ 65°"
    # eV converted to nm, ascending
    assert psi["B.E."][0] == pytest.approx(1239.84193 / 4.5)
    assert psi["Raw Data"][0] == pytest.approx(24.5)
    assert psi["ELLIPS_Delta"][0] == pytest.approx(145.0)
    delta = levels["Ellips~Delta"]
    assert delta["ELLIPS_Quantity"] == "delta"
    assert delta["ELLIPS_Y_Label"] == "Δ (°)"
    assert delta["Raw Data"][0] == pytest.approx(145.0)


def test_sniff(tmp_path):
    assert optical.sniff_uvvis(_cary(tmp_path / "a.csv"))
    pe = tmp_path / "b.asc"
    pe.write_text("PE UV       SUBTECH     SPECTRUM    ASCII\n#DATA\n300\t1\n")
    assert optical.sniff_uvvis(pe)
    plain = tmp_path / "c.csv"
    plain.write_text("Wavelength,Value\n300,1\n301,2\n")
    assert not optical.sniff_uvvis(plain)


def test_no_data_raises(tmp_path):
    p = tmp_path / "x.txt"
    p.write_text("nothing here\n")
    with pytest.raises(ValueError):
        optical.read_uvvis([str(p)])


def test_round_trip(tmp_path):
    levels = optical.read_uvvis([str(_cary(tmp_path / "batch.csv"))])
    project = kfitio.read_bytes(kfitwrite.to_bytes(levels))
    sheet = project.sheet("UVvis")
    assert project.names == ["UVvis", "UVvis1"]
    assert sheet.x[0] == 300.0
    assert sheet.raw["UVVIS_X_Label"] == "Wavelength (nm)"
    assert sheet.y[40] == pytest.approx(1.0, abs=1e-4)
