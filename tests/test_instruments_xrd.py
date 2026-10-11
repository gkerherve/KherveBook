"""Tests for the XRD instrument readers (khervebook/instruments/xrd.py).

Synthetic .xrdml, Bruker RAW v3/v4 and 2θ text files are built in the
layouts the parsers expect, read into KherveFitting core levels and
round-tripped through the .kfit writer and `kfitio`.

Copyright (C) 2026 Gwilherm Kerherve

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.
"""

import io
import struct

import numpy as np
import pytest

from khervebook import kfitio
from khervebook.instruments import kfitwrite, xrd

NS = "http://www.xrdml.com/XRDMeasurement/1.5"


# ---------------------------------------------------------------------------
#  Synthetic files
# ---------------------------------------------------------------------------
def make_xrdml(path, n=101, scans=2, list_positions=False):
    counts = " ".join(str(100 + i) for i in range(n))
    body = []
    for s in range(scans):
        if list_positions and s == 0:
            pos = ("<listPositions>"
                   + " ".join(f"{20 + 0.1 * i:.4f}" for i in range(n))
                   + "</listPositions>")
        else:
            pos = (f"<startPosition>{10 + s}</startPosition>"
                   f"<endPosition>{20 + s}</endPosition>")
        body.append(
            "<scan><dataPoints>"
            f'<positions axis="2Theta" unit="deg">{pos}</positions>'
            '<positions axis="Omega" unit="deg"><startPosition>5'
            "</startPosition><endPosition>10</endPosition></positions>"
            f'<counts unit="counts">{counts}</counts>'
            "</dataPoints></scan>")
    text = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        f'<xrdMeasurements xmlns="{NS}"><xrdMeasurement>'
        "<usedWavelength intended=\"K-Alpha 1\">"
        "<kAlpha1 unit=\"Angstrom\">1.5405980</kAlpha1>"
        "<kAlpha2 unit=\"Angstrom\">1.5444260</kAlpha2>"
        "<ratioKAlpha2KAlpha1>0.5000</ratioKAlpha2KAlpha1>"
        "</usedWavelength>"
        "<incidentBeamPath><xRayTube><anodeMaterial>Cu</anodeMaterial>"
        "</xRayTube></incidentBeamPath>"
        + "".join(body) + "</xrdMeasurement></xrdMeasurements>")
    path.write_text(text, encoding="utf-8")
    return path


def make_raw_v3(path, n=200, start=5.0, step=0.02):
    head = bytearray(712)
    head[0:7] = b"RAW1.01"
    struct.pack_into("<I", head, 12, 1)
    head[608:610] = b"CU"
    struct.pack_into("<d", head, 624, 1.540598)
    struct.pack_into("<d", head, 632, 1.544426)
    struct.pack_into("<d", head, 648, 0.5)
    rng = bytearray(304)
    struct.pack_into("<I", rng, 0, 304)
    struct.pack_into("<I", rng, 4, n)
    struct.pack_into("<d", rng, 16, start)
    struct.pack_into("<d", rng, 176, step)
    struct.pack_into("<I", rng, 256, 0)
    counts = (np.arange(n, dtype="<f4") + 10.0).tobytes()
    path.write_bytes(bytes(head) + bytes(rng) + counts)
    return path


def make_raw_v4(path, n=300, start=10.0, step=0.025):
    head = bytearray(1024)
    head[0:7] = b"RAW4.00"
    struct.pack_into("<I", head, 64, n)
    struct.pack_into("<I", head, 128, n)
    head[420:422] = b"Cu"
    head[600:606] = b"2Theta"
    struct.pack_into("<d", head, 644, start)
    struct.pack_into("<d", head, 720, step)
    struct.pack_into("<d", head, 800, step)
    struct.pack_into("<d", head, 880, 1.540598)
    counts = (np.linspace(1, 500, n).astype("<f4")).tobytes()
    path.write_bytes(bytes(head) + counts)
    return path


def make_text(path, n=50, three=True, header="Rigaku ASC export\n"):
    lines = [header.rstrip("\n")] if header else []
    for i in range(n):
        tth = 60 - 0.5 * i               # descending: the reader sorts
        if three:
            lines.append(f"{tth:.2f} {i * 2.0:.1f} {1000 + i:.1f}")
        else:
            lines.append(f"{tth:.2f},{1000 + i:.1f}")
    path.write_text("\n".join(lines) + "\n")
    return path


# ---------------------------------------------------------------------------
#  Tests
# ---------------------------------------------------------------------------
def test_formats_declared():
    labels = {(f.technique, f.label): f for f in xrd.FORMATS}
    assert all(f.technique == "XRD" for f in xrd.FORMATS)
    xrdml = next(f for f in xrd.FORMATS if ".xrdml" in f.exts
                 and not f.multi)
    assert xrdml.sniff is None
    raw = next(f for f in xrd.FORMATS if f.exts == (".raw",))
    assert raw.sniff is xrd.sniff_bruker_raw
    text = next(f for f in xrd.FORMATS if ".csv" in f.exts)
    assert text.sniff("anything") is False
    folder = next(f for f in xrd.FORMATS if f.multi)
    assert folder.sniff("x") is False
    assert len(labels) == len(xrd.FORMATS)


def test_xrdml_two_scans(tmp_path):
    p = make_xrdml(tmp_path / "quartz.xrdml")
    levels = xrd.read_file(p)
    assert list(levels) == ["XRD", "XRD1"]
    s0 = levels["XRD"]
    assert len(s0["B.E."]) == 101
    assert s0["B.E."][0] == pytest.approx(10.0)
    assert s0["B.E."][-1] == pytest.approx(20.0)
    assert levels["XRD1"]["B.E."][0] == pytest.approx(11.0)
    assert s0["Raw Data"][:3] == [100.0, 101.0, 102.0]
    assert s0["XRD_Label"] == "quartz - scan 1"
    assert levels["XRD1"]["XRD_Label"] == "quartz - scan 2"
    assert s0["XRD_Source"] == "quartz.xrdml"
    assert s0["XRD_Wavelength"] == repr(1.540598)
    assert s0["XRD_Wavelength2"] == repr(1.544426)
    assert s0["XRD_Ka2_Ratio"] == repr(0.5)
    assert s0["XRD_Anode"] == "Cu"
    assert s0["XRD_TwoTheta"] == s0["B.E."]
    info = s0["ExperimentalInfo"]
    assert info["Technique"] == "XRD (powder diffraction)"
    assert info["Step (°)"] == "0.10000"
    assert s0["Background"]["Bkg Low"] == pytest.approx(10.0)


def test_xrdml_list_positions(tmp_path):
    p = make_xrdml(tmp_path / "l.xrdml", scans=1, list_positions=True)
    levels = xrd.read_file(p)
    assert list(levels) == ["XRD"]
    assert levels["XRD"]["XRD_Label"] == "l"
    assert levels["XRD"]["B.E."][1] == pytest.approx(20.1)


def test_bruker_raw_v3(tmp_path):
    p = make_raw_v3(tmp_path / "a.raw")
    assert xrd.sniff_bruker_raw(p)
    levels = xrd.read_file(p)
    s = levels["XRD"]
    assert len(s["B.E."]) == 200
    assert s["B.E."][0] == pytest.approx(5.0)
    assert s["B.E."][-1] == pytest.approx(5.0 + 0.02 * 199)
    assert s["Raw Data"][0] == 10.0
    assert s["XRD_Anode"] == "Cu"
    assert float(s["XRD_Wavelength"]) == pytest.approx(1.540598)


def test_bruker_raw_v4(tmp_path):
    p = make_raw_v4(tmp_path / "b.raw")
    assert xrd.sniff_bruker_raw(p)
    s = xrd.read_file(p)["XRD"]
    assert len(s["B.E."]) == 300
    assert s["B.E."][0] == pytest.approx(10.0)
    assert s["B.E."][1] - s["B.E."][0] == pytest.approx(0.025)
    assert s["Raw Data"][-1] == pytest.approx(500.0)
    assert s["XRD_Anode"] == "Cu"


def test_sniff_rejects_other_raw(tmp_path):
    p = tmp_path / "thermo.raw"
    p.write_bytes(b"\x01\xa1Finnigan" + bytes(100))
    assert not xrd.sniff_bruker_raw(p)
    with pytest.raises(ValueError):
        xrd.read_file(p)


def test_text_three_columns_uses_last(tmp_path):
    p = make_text(tmp_path / "r.asc")
    s = xrd.read_file(p)["XRD"]
    assert len(s["B.E."]) == 50
    assert s["B.E."] == sorted(s["B.E."])
    assert s["B.E."][0] == pytest.approx(35.5)
    assert s["Raw Data"][0] == pytest.approx(1049.0)
    # Cu Kα1 default fills Kα2 in
    assert s["XRD_Wavelength2"] == repr(1.544426)
    assert "XRD_Anode" not in s


def test_text_two_columns_csv(tmp_path):
    p = make_text(tmp_path / "r.csv", three=False, header="2theta,I")
    s = xrd.read_file(p)["XRD"]
    assert s["Raw Data"][-1] == pytest.approx(1000.0)


def test_text_too_short(tmp_path):
    p = tmp_path / "x.txt"
    p.write_text("1 2\n3 4\n")
    with pytest.raises(ValueError):
        xrd.read_file(p)


def test_folder(tmp_path):
    make_xrdml(tmp_path / "a.xrdml", scans=1)
    make_raw_v3(tmp_path / "b.raw")
    make_text(tmp_path / "c.xy")
    make_text(tmp_path / "ignored.csv")      # not in the folder extensions
    levels = xrd.read_folder([tmp_path])
    assert list(levels) == ["XRD", "XRD1", "XRD2"]
    assert [levels[k]["XRD_Source"] for k in levels] == \
        ["a.xrdml", "b.raw", "c.xy"]


def test_roundtrip_kfit(tmp_path):
    levels = xrd.read_file(make_xrdml(tmp_path / "q.xrdml"))
    data = kfitwrite.to_bytes(levels, str(tmp_path / "q.kfit"))
    proj = kfitio.read_bytes(data)
    assert proj.names == ["XRD", "XRD1"]
    sh = proj.sheet("XRD")
    assert sh.x_label == "2θ (°)"
    assert sh.y_label == "Intensity (counts)"
    assert not sh.descending
    assert len(sh.x) == 101
    assert sh.raw["XRD_Wavelength"] == repr(1.540598)
    import h5py
    with h5py.File(io.BytesIO(data), "r") as f:
        g = f["core_levels/cl_0"]
        assert "XRD_TwoTheta" in g and "XRD_Intensity" in g
