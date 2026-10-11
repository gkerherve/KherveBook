"""SQUID import (khervebook/instruments/squid.py): MPMS .dat with its
.gph sidecar, CSV loops, bare two-column text and the .kfit round trip.

Copyright (C) 2026 Gwilherm Kerherve

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.
"""

import numpy as np
import pytest

from khervebook import kfitio
from khervebook.instruments import kfitwrite, squid

COLS = ("Comment,Time Stamp (sec),Temperature (K),Magnetic Field (Oe),"
        "Moment (emu),M. Std. Err. (emu)\n")
T = np.linspace(300, 2, 40)
M = 1e-3 / T + 1e-6


def _mpms(path):
    hdr = ("[Header]\nTITLE,Test\nINFO,PNCO0.3,SAMPLE_MATERIAL\n"
           "INFO,12.5,SAMPLE_MASS\nINFO,MPMS3,APPNAME\n[Data]\n")
    body = "".join(f",{1000 + i},{T[i]},{1000 + 0.1 * i},{M[i]:.6e},1e-9\n"
                   for i in range(40))
    path.write_text(hdr + COLS + body)
    return path


def _loop(path):
    h = np.concatenate([np.linspace(-5e4, 5e4, 30),
                        np.linspace(5e4, -5e4, 30)])
    path.write_text(COLS + "".join(
        f",{i},5.0,{h[i]},{np.tanh(h[i] / 1e4) * 1e-4:.6e},0\n"
        for i in range(60)))
    return path


def test_mpms_dat(tmp_path):
    p = _mpms(tmp_path / "ZFC_1000Oe.dat")
    levels = squid.read_dat([str(p)])
    s = levels["SQUID"]
    assert list(levels) == ["SQUID"]
    assert s["SQUID_Scan_Type"] == "MT"
    assert s["B.E."] == sorted(s["B.E."])            # M(T) is sorted
    assert s["B.E."][0] == pytest.approx(2.0)
    assert s["Raw Data"][0] == pytest.approx(M[-1], rel=1e-5)
    assert s["SQUID_Branch"] == "ZFC"
    assert s["SQUID_Field_Mean"] == pytest.approx(1001.95)
    assert len(s["SQUID_Field_Series"]) == 40
    assert s["SQUID_Label"].startswith("ZFC")
    assert s["ExperimentalInfo"]["Sample Material"] == "PNCO0.3"
    assert s["ExperimentalInfo"]["Instrument"] == "MPMS3"
    assert s["Background"]["Bkg Low"] == pytest.approx(151.0)


def test_gph_picks_the_axis(tmp_path):
    p = _mpms(tmp_path / "run.dat")
    (tmp_path / "run.dat.gph").write_text(
        "[X_Axis]\nitemIndex=3\n[Y_Axis0]\nitemIndex=4\n")
    s = squid.read_dat(str(p))["SQUID"]
    assert s["SQUID_Scan_Type"] == "MH"
    assert s["SQUID_X_Label"] == "Magnetic Field (Oe)"


def test_csv_loop_and_two_column(tmp_path):
    _loop(tmp_path / "MH_5K.csv")
    (tmp_path / "bare.txt").write_text(
        "# T M\n" + "".join(f"{T[i]} {M[i]}\n" for i in range(40)))
    levels = squid.read_csv([str(tmp_path)])           # folder form
    assert list(levels) == ["SQUID", "SQUID1"]
    loop = levels["SQUID"]
    assert loop["SQUID_Scan_Type"] == "MH"
    assert loop["B.E."][0] == pytest.approx(-5e4)     # acquisition order
    assert loop["SQUID_Temperature_K"] == pytest.approx(5.0)
    assert loop["SQUID_Branch"] == "MH"
    assert levels["SQUID1"]["SQUID_Scan_Type"] == "MT"


def test_sniffs(tmp_path):
    assert squid.sniff_mpms(_mpms(tmp_path / "a.dat"))
    assert squid.sniff_csv(_loop(tmp_path / "b.csv"))
    plain = tmp_path / "c.csv"
    plain.write_text("x,y\n1,2\n")
    assert not squid.sniff_csv(plain)
    other = tmp_path / "d.dat"
    other.write_text("1 2\n3 4\n")
    assert not squid.sniff_mpms(other)


def test_empty_file_raises(tmp_path):
    p = tmp_path / "aborted.dat"
    p.write_text("[Header]\nINFO,x,APPNAME\n[Data]\n" + COLS)
    with pytest.raises(ValueError):
        squid.read_dat([str(p)])


def test_round_trip(tmp_path):
    levels = squid.read_dat([str(_mpms(tmp_path / "ZFC.dat"))])
    levels.update({"SQUID1": squid.read_csv(
        [str(_loop(tmp_path / "MH.csv"))])["SQUID"]})
    project = kfitio.read_bytes(kfitwrite.to_bytes(levels))
    mt, mh = project.sheet("SQUID"), project.sheet("SQUID1")
    assert (mt.x_label, mt.y_label) == ("Temperature (K)", "Moment (emu)")
    assert mh.x_label == "Magnetic Field (Oe)"
    # moments of 1e-5 emu survive (lossless B.E./Raw Data)
    assert mt.y[0] == pytest.approx(M[-1], rel=1e-5)
