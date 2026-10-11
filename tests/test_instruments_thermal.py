"""Tests for the thermal-analysis readers (khervebook/instruments/thermal.py).

Synthetic NETZSCH-style TGA/STA and DIL CSV exports, bare two-column
files and a TA TRIOS ``.tri`` binary (length-prefixed .NET header
strings + per-segment float32 signal arrays) are read into KherveFitting
core levels and round-tripped through the .kfit writer and `kfitio`.

Copyright (C) 2026 Gwilherm Kerherve

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.
"""

import io
import math
import struct

import numpy as np
import pytest

from khervebook import kfitio
from khervebook.instruments import kfitwrite, thermal


# ---------------------------------------------------------------------------
#  Synthetic files
# ---------------------------------------------------------------------------
def make_netzsch_tga(path, n=40):
    lines = [
        "#EXPORTTYPE:                 ,DATA ALL      ,,,,,,",
        "#INSTRUMENT:                 ,NETZSCH STA 449F3,,,,,,",
        "#SAMPLE:                     ,CaC2O4,,,,,,",
        "#SAMPLE MASS /mg:            ,10.225,,,,,,",
        "#EXO:                        ,1,,,,,,",
        ",,,,,,,",
        "##Temp./°C,Time/min,DSC/(uV/mg),Mass/%,Gas Flow/(ml/min),"
        "Sensit./(uV/mW),Segment",
    ]
    for i in range(n):
        lines.append(f"{25 + 10 * i:.3f},{i * 0.5:.4f},{-3.73e-4 * i:.4E},"
                     f"{100 - 0.5 * i:.3f},50,20,{1 + i // 20}")
    path.write_bytes(("\n".join(lines) + "\n").encode("cp1252"))
    return path


def make_bare_tga(path, n=30):
    lines = [f"{30 + 5 * i},{12.0 - 0.1 * i:.3f}" for i in range(n)]
    path.write_text("\n".join(lines) + "\n")
    return path


def make_netzsch_dil(path, n=40, column="dL/Lo"):
    lines = [
        "#FORMAT:               ,NETZSCH5",
        "#MTYPE:                ,DIL",
        "#INSTRUMENT:           ,NETZSCH DIL 402C",
        "#SAMPLE LENGTH /mm:    ,13.37",
        "#GAS 1:                ,Argon",
        f"##Temp./°C,Time/min,{column},Segment",
    ]
    for i in range(n):
        dl = 2.4e-5 * i if column == "dL/Lo" else 0.5 * i
        lines.append(f"{24 + 10 * i:.2f},{i * 0.2:.4e},{dl:.4e},1")
    path.write_bytes(("\n".join(lines) + "\n").encode("cp1252"))
    return path


def _net_string(s):
    raw = s.encode("utf-8")
    assert len(raw) < 128
    return bytes([len(raw)]) + raw


def make_tri(path, segs=(60, 80)):
    """Two-sample X3-style DSC: Time; Temperature A/B; Heat Flow A/B."""
    names = ["Time", "Temperature A", "Heat Flow A", "Temperature B",
             "Heat Flow B"]
    header = bytearray(b"TRIOSFILE\x00\x00\x00")
    for key, value in (("instrumenttype", "DSC"),
                       ("instrumentname", "X3 DSC"),
                       ("samplename", "EVOH"),
                       ("operator", "gk"),
                       ("samplepannumber", "3"),
                       ("samplepannumberb", "7"),
                       ("proceduresignals", ";".join(names)),
                       ("proceduresegments", "Ramp 10 °C/min to 200 °C")):
        header += _net_string(key) + _net_string(value)
    header += bytes(64)
    blob = bytearray(header)
    t0, temp0 = 0.0, 25.0
    for count in segs:
        t = t0 + np.arange(count) * 6.0
        temp = temp0 + np.arange(count) * 1.0
        signals = [t, temp, 0.002 + 1e-5 * np.arange(count), temp + 0.1,
                   0.003 + 1e-5 * np.arange(count)]
        for arr in signals:
            blob += struct.pack("<i", count)
            blob += np.asarray(arr, dtype="<f4").tobytes()
            blob += bytes(68)
        blob += bytes(32)
        t0 = float(t[-1]) + 1.0
        temp0 = float(temp[-1]) + 1.0
    blob += b"C:\\ProgramData\\TA Instruments\\TRIOS" + bytes(16)
    path.write_bytes(bytes(blob))
    return path


# ---------------------------------------------------------------------------
#  Formats
# ---------------------------------------------------------------------------
def test_formats_declared():
    by = {(f.technique, f.label): f for f in thermal.FORMATS}
    assert ("TGA", "File(s) (.csv/.txt/.dat)") in by
    assert ("TGA", "TA TRIOS DSC file(s) (.tri)") in by
    assert ("Dilatometry", "File(s) (.csv/.txt/.dat)") in by
    tri = by[("TGA", "TA TRIOS DSC file(s) (.tri)")]
    assert tri.sniff is None and tri.exts == (".tri",)
    for f in thermal.FORMATS:
        if f is not tri:
            assert f.sniff("x.csv") is False
    assert sum(f.multi for f in thermal.FORMATS) == 3


# ---------------------------------------------------------------------------
#  TGA
# ---------------------------------------------------------------------------
def test_tga_netzsch(tmp_path):
    p = make_netzsch_tga(tmp_path / "run.csv")
    levels = thermal.read_tga(p)
    assert list(levels) == ["TGA"]
    s = levels["TGA"]
    # time view: temperature against time
    assert s["TGA_View"] == "time"
    assert s["B.E."][:3] == [0.0, 0.5, 1.0]
    assert s["Raw Data"][:2] == [25.0, 35.0]
    assert s["TGA_X_Label"] == "Time (min)"
    assert s["TGA_Y_Label"] == "Temperature (°C)"
    assert s["TGA_Mass_Unit"] == "mg"
    assert s["TGA_Sample_Mass_mg"] == pytest.approx(10.225)
    assert s["TGA_Mass_Pct"][1] == pytest.approx(99.5)
    assert s["TGA_Mass_mg"][0] == pytest.approx(10.225)
    assert s["TGA_DSC"][1] == pytest.approx(-3.73e-4)
    assert s["TGA_DSC_Unit"] == "DSC (µV/mg)"
    assert s["TGA_Segment"][-1] == 2.0
    assert s["TGA_Exo_Up"] is True
    assert s["Background"]["Bkg Low"] == pytest.approx(0.25 * 19.5)
    info = s["ExperimentalInfo"]
    assert info["Instrument"] == "NETZSCH STA 449F3"
    assert info["Sample"] == "CaC2O4"
    assert info["Sample Mass (mg)"] == "10.225"


def test_tga_bare(tmp_path):
    s = thermal.read_tga(make_bare_tga(tmp_path / "bare.txt"))["TGA"]
    assert s["TGA_View"] == "temperature"
    assert s["B.E."][0] == 30.0
    assert s["Raw Data"][0] == pytest.approx(12.0)
    assert s["TGA_Y_Label"] == "Mass (mg)"
    assert s["TGA_Sample_Mass_mg"] == pytest.approx(12.0)
    assert "TGA_DSC" not in s and "TGA_Time_min" not in s


def test_tga_rejects_text(tmp_path):
    p = tmp_path / "notes.txt"
    p.write_text("hello\nworld\n")
    with pytest.raises(ValueError):
        thermal.read_tga(p)


def test_tga_folder(tmp_path):
    make_netzsch_tga(tmp_path / "a.csv")
    make_bare_tga(tmp_path / "b.dat")
    (tmp_path / "junk.txt").write_text("no numbers here\n")
    levels = thermal.read_tga_folder([tmp_path])
    assert list(levels) == ["TGA", "TGA1"]
    assert levels["TGA1"]["TGA_Source"] == "b.dat"


def test_tga_roundtrip(tmp_path):
    levels = thermal.read_tga(make_netzsch_tga(tmp_path / "run.csv"))
    data = kfitwrite.to_bytes(levels)
    proj = kfitio.read_bytes(data)
    sh = proj.sheet("TGA")
    assert sh.x_label == "Time (min)"
    assert sh.y_label == "Temperature (°C)"
    assert not sh.descending
    import h5py
    with h5py.File(io.BytesIO(data), "r") as f:
        dsc = f["core_levels/cl_0/TGA_DSC"][:]
    assert dsc[1] == pytest.approx(-3.73e-4)      # survives the rounding


# ---------------------------------------------------------------------------
#  TA TRIOS .tri
# ---------------------------------------------------------------------------
def test_tri_two_samples(tmp_path):
    p = make_tri(tmp_path / "evoh.tri")
    parsed = thermal.parse_tri_file(p)
    assert parsed["n_points"] == 140
    assert [s["label"] for s in parsed["samples"]] == ["A", "B"]
    levels = thermal.read_tri(p)
    assert list(levels) == ["TGA", "TGA1"]
    a, b = levels["TGA"], levels["TGA1"]
    assert len(a["B.E."]) == 140
    assert a["B.E."][0] == 25.0 and a["B.E."][-1] == 164.0
    assert a["Raw Data"][0] == pytest.approx(2.0, rel=1e-5)   # W -> mW
    assert b["Raw Data"][0] == pytest.approx(3.0, rel=1e-5)
    assert a["TGA_Signal_Kind"] == "heatflow"
    assert a["TGA_View"] == "temperature"
    assert a["TGA_Y_Label"] == "Heat Flow (mW)"
    assert a["TGA_Time_min"][1] == pytest.approx(0.1)
    assert a["TGA_Segment"][0] == 1.0 and a["TGA_Segment"][-1] == 2.0
    assert a["TGA_Label"] == "EVOH (A) [pan 3]"
    assert b["TGA_Label"] == "EVOH (B) [pan 7]"
    info = a["ExperimentalInfo"]
    assert info["Technique"] == "DSC (TA TRIOS)"
    assert info["Instrument"] == "X3 DSC"
    assert info["Operator"] == "gk"


def test_tri_bad_file(tmp_path):
    p = tmp_path / "x.tri"
    p.write_bytes(b"not a trios file" * 10)
    with pytest.raises(ValueError):
        thermal.read_tri(p)


def test_tri_folder(tmp_path):
    make_tri(tmp_path / "a.tri")
    make_tri(tmp_path / "b.tri", segs=(70,))
    levels = thermal.read_tri_folder([tmp_path])
    assert list(levels) == ["TGA", "TGA1", "TGA2", "TGA3"]
    assert len(levels["TGA2"]["B.E."]) == 70


def test_tri_roundtrip(tmp_path):
    levels = thermal.read_tri(make_tri(tmp_path / "a.tri"))
    proj = kfitio.read_bytes(kfitwrite.to_bytes(levels))
    sh = proj.sheet("TGA1")
    assert sh.x_label == "Temperature (°C)"
    assert sh.y_label == "Heat Flow (mW)"
    assert sh.y[0] == pytest.approx(3.0, rel=1e-5)


# ---------------------------------------------------------------------------
#  Dilatometry
# ---------------------------------------------------------------------------
def test_dil_netzsch(tmp_path):
    s = thermal.read_dil(make_netzsch_dil(tmp_path / "dil.csv"))["DIL"]
    assert s["B.E."][:2] == [24.0, 34.0]
    assert s["Raw Data"][1] == pytest.approx(2.4e-5)
    assert s["DIL_Y_Unit"] == "rel"
    assert s["DIL_Y_Label"] == "dL/L$_0$"
    assert s["DIL_X_Label"] == "Temperature (°C)"
    assert s["DIL_Sample_Length_mm"] == pytest.approx(13.37)
    assert s["DIL_Strain"] == s["Raw Data"]
    assert "DIL_dL_um" not in s
    assert s["DIL_Segment"][0] == 1.0
    assert s["Fitting"] == {"Peaks": {}}
    assert s["ExperimentalInfo"]["Gas"] == "Argon"


def test_dil_micron_with_length(tmp_path):
    p = make_netzsch_dil(tmp_path / "dil.txt", column="dL/µm")
    s = thermal.read_dil(p)["DIL"]
    assert s["DIL_dL_um"][2] == pytest.approx(1.0)
    assert s["Raw Data"][2] == pytest.approx(1.0 / 13370.0)
    assert s["DIL_Y_Unit"] == "rel"


def test_dil_bare_microns(tmp_path):
    p = tmp_path / "bare.dat"
    p.write_text("\n".join(f"{20 + i}\t{i * 1.5}" for i in range(20)))
    s = thermal.read_dil(p)["DIL"]
    assert s["DIL_Y_Unit"] == "um"
    assert s["DIL_Y_Label"] == "dL (µm)"
    assert s["DIL_Sample_Length_mm"] is None


def test_dil_folder_and_roundtrip(tmp_path):
    make_netzsch_dil(tmp_path / "a.csv")
    make_netzsch_dil(tmp_path / "b.csv")
    levels = thermal.read_dil_folder([tmp_path / "a.csv",
                                      tmp_path / "b.csv"])
    assert list(levels) == ["DIL", "DIL1"]
    data = kfitwrite.to_bytes(levels)
    proj = kfitio.read_bytes(data)
    assert proj.names == ["DIL", "DIL1"]
    sh = proj.sheet("DIL")
    assert sh.raw["DIL_X_Label"] == "Temperature (°C)"
    assert sh.y[1] == pytest.approx(2.4e-5)
    import h5py
    with h5py.File(io.BytesIO(data), "r") as f:
        strain = f["core_levels/cl_0/DIL_Strain"][:]
    assert strain[1] == pytest.approx(2.4e-5)
    assert not math.isnan(strain[0])
