"""FTIR import (khervebook/instruments/ftir.py): Cary 630 / generic text,
JCAMP-DX and Nicolet/OMNIC libraries, as KherveFitting's .xlsx round trip
leaves them.

Copyright (C) 2026 Gwilherm Kerherve

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.
"""

from pathlib import Path

import numpy as np
import pytest

from khervebook import kfitio
from khervebook.instruments import ftir, kfitwrite

LIBRARY = Path("/Users/gkerherv/Documents/PycharmProjects/KherveFittingPro"
               "/FTIR Library")
WN = np.linspace(4000, 650, 200)


def _cary630(path):
    path.write_text(
        "DATATYPE     IR Spectrum\n"
        "XYUNITS      Wavenumber;PercentTransmittance\nDECIMALSYMBOL.\n"
        + "".join(f"{x:.4f}     {90 - 50 * np.exp(-((x - 1700) / 20) ** 2):.4f}\n"
                  for x in WN[::-1])
        + "Created at (UTC)=06/20/2025 14:51:06\nSampleScans=20\n")
    return path


def test_cary630(tmp_path):
    levels = ftir.read_text([str(_cary630(tmp_path / "s.txt"))])
    s = levels["FTIR"]
    assert list(levels) == ["FTIR"]
    assert len(s["B.E."]) == 200
    assert s["B.E."][0] == 650.0                     # file order kept
    assert s["Raw Data"] == [round(v, 2) for v in s["Raw Data"]]
    assert s["Corrected Data"] == s["Raw Data"]
    assert s["Transmission"] == [1.0] * 200
    assert s["FTIR_Y_Unit"] == "Transmittance (%)"
    assert s["FTIR_Detection"]["confidence"] == 1.0
    assert s["FTIR_Raw"]["y"] == s["Raw Data"]
    assert s["Background"]["Bkg Low"] == 650.0
    assert "ExperimentalInfo" not in s               # lives on its own sheet


def test_bare_csv_infers_absorbance_and_decimal_comma(tmp_path):
    a = tmp_path / "a.csv"
    a.write_text("".join(f"{x:.3f},{0.8 * np.exp(-((x - 1700) / 20) ** 2) + 0.01:.5f}\n"
                         for x in WN))
    b = tmp_path / "b.txt"
    b.write_text("DATATYPE IR\nXYUNITS Wavenumber;Absorbance\nDECIMALSYMBOL ,\n"
                 + "".join(f"{x:.2f}".replace(".", ",") + "\t0,50\n"
                           for x in WN))
    levels = ftir.read_csv([str(b), str(a)])
    assert list(levels) == ["FTIR", "FTIR1"]
    assert levels["FTIR"]["FTIR_Y_Unit"] == "Absorbance"   # a.csv first
    assert levels["FTIR"]["FTIR_Detection"]["confidence"] == 0.75
    assert levels["FTIR1"]["Raw Data"][0] == 0.5
    assert levels["FTIR1"]["B.E."][0] == 4000.0


def test_folder_reads_every_text_file(tmp_path):
    _cary630(tmp_path / "one.txt")
    _cary630(tmp_path / "two.dat")
    (tmp_path / "skip.jdx").write_text("##TITLE=x\n")
    levels = ftir.read_text_folder([str(tmp_path)])
    assert list(levels) == ["FTIR", "FTIR1"]


def test_sniff(tmp_path):
    assert ftir.sniff_cary630(_cary630(tmp_path / "a.txt"))
    p = tmp_path / "b.csv"
    p.write_text("4000,90\n3999,91\n")
    assert not ftir.sniff_cary630(p)


def _jcamp(path, ydata, yunits="TRANSMITTANCE"):
    path.write_text(
        "##TITLE=Test compound\n##JCAMP-DX=4.24\n##DATA TYPE=INFRARED SPECTRUM\n"
        "##CAS REGISTRY NO=67-64-1\n##XUNITS=1/CM\n"
        f"##YUNITS={yunits}\n##XFACTOR=1.0\n##YFACTOR=0.001\n"
        "##FIRSTX=400\n##LASTX=409\n##DELTAX=1\n##NPOINTS=10\n"
        "##XYDATA=(X++(Y..Y))\n" + ydata + "##END=\n")
    return path


def test_jcamp_affn_and_asdf(tmp_path):
    affn = _jcamp(tmp_path / "a.jdx",
                  "400 900 910 920 930 940\n405 950 960 970 980 990\n")
    # DIF/DUP compressed: 900 then +10 four times; the second line opens
    # with the check value 940 (the previous line's last point)
    asdf = _jcamp(tmp_path / "b.dx", "400 900J0V\n404 940J0W\n")
    levels = ftir.read_jcamp([str(affn), str(asdf)])
    assert list(levels) == ["FTIR", "FTIR1"]
    for s in levels.values():
        assert s["B.E."] == [float(v) for v in range(400, 410)]
        # fractional transmittance -> percent, rounded as the .xlsx does
        assert s["Raw Data"][0] == 90.0 and s["Raw Data"][-1] == 99.0
        assert s["FTIR_Y_Unit"] == "Transmittance (%)"
        assert s["FTIR_Raw"]["unit"] == "Transmittance (%)"
        assert "FTIR_Detection" not in s


@pytest.mark.skipif(not LIBRARY.is_dir(), reason="FTIR Library not present")
def test_jcamp_library_files():
    files = sorted(str(p) for p in LIBRARY.glob("*.jdx"))
    if not files:
        pytest.skip("no .jdx files")
    levels = ftir.read_jcamp(files)
    assert len(levels) == len(files)
    s = levels["FTIR"]
    assert len(s["B.E."]) > 100
    assert s["B.E."] == sorted(s["B.E."])
    assert s["FTIR_Y_Unit"] in ("Transmittance (%)", "Absorbance")


def _nicolet(folder):
    npts, nspec, stride = 50, 3, 108
    hdr = ["1024", "x", "x", "My Test Library", "x", "x", str(nspec),
           str(stride), "x", "x", "x", "x", "x", "x", str(npts), "650.0",
           "4000.0"]
    head = ("\r\n".join(hdr) + "\r\n").encode("latin-1") + b"\x1a"
    head += b"\0" * (1024 - len(head))
    recs = b""
    for k in range(nspec):
        y = (np.linspace(0, 1, npts) ** (k + 1) * 60000).astype("<u2")
        recs += y.tobytes() + b"\0" * (stride - 2 * npts)
    (folder / "LIB.LBD").write_bytes(head + recs)
    names = ["Polystyrene film", "Acetone liquid", "Ethanol absolute"]
    body = b"".join(bytes([len(n)]) + n.encode() + bytes([7]) + b"12-34-5"
                    for n in names)
    (folder / "LIB.LBT").write_bytes(b"\0" * 10 + b"\x1a" + body)
    return folder / "LIB.LBT"


def test_nicolet_library(tmp_path):
    levels = ftir.read_nicolet(str(_nicolet(tmp_path)))
    assert list(levels) == ["FTIR", "FTIR1", "FTIR2"]
    s = levels["FTIR1"]
    assert s["B.E."][0] == 650.0 and s["B.E."][-1] == 4000.0
    assert s["Raw Data"][-1] == pytest.approx(0.92)   # 60000/65535, 2 dp
    assert s["FTIR_Y_Unit"] == "Absorbance"
    assert s["FTIR_Reference"] == "Acetone liquid [My Test Library]"
    only = ftir.read_nicolet(str(tmp_path / "LIB.LBD"), selected=[2])
    assert list(only) == ["FTIR"]


def test_nicolet_without_lbd(tmp_path):
    (tmp_path / "X.LBT").write_bytes(b"\0" * 20)
    with pytest.raises(FileNotFoundError):
        ftir.read_nicolet(str(tmp_path / "X.LBT"))


def test_round_trip_axis_labels(tmp_path):
    levels = ftir.read_text([str(_cary630(tmp_path / "s.txt"))])
    levels.update({"FTIR1": ftir.read_nicolet(
        str(_nicolet(tmp_path)))["FTIR"]})
    project = kfitio.read_bytes(kfitwrite.to_bytes(levels))
    t, a = project.sheet("FTIR"), project.sheet("FTIR1")
    assert t.x_label == "Wavenumber (cm$^{-1}$)"
    assert t.y_label == "Transmittance (%)"
    assert a.y_label == "Absorbance"
    assert kfitio.x_descending("FTIR")
