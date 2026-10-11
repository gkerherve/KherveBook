"""XPS International SDP import (instruments/sdp).

Runs on the real files in ~/Downloads/"Oxides, Rare Earth" when present,
and always on a synthetic file in the binary layout ``parse_sdp_file``
walks.

Copyright (C) 2026 Gwilherm Kerherve

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.
"""

import struct
from pathlib import Path

import pytest

from khervebook import instruments, kfitio
from khervebook.instruments import kfitwrite, sdp

REAL = Path.home() / "Downloads" / "Oxides, Rare Earth"


def _block(desc, be_start, step, counts, source=1486.6, pe=50.0):
    out = b"Binding Energy" + b"\0" * (112 - 14)
    for s in (b"C:\\data\\orig.vms", desc.encode(), b"params", b"1999",
              b"VAMAS/ISO"):
        out += struct.pack("<H", len(s) + 1) + s + b"\0"
    params = struct.pack("<ddddd", be_start, step,
                         be_start + step * (len(counts) - 1), 0, 0)
    params += b"\0\0" + struct.pack("<dddddd", source, 0, 4.5, pe, 8, 0)
    params += struct.pack("<II", 1, len(counts))
    return out + params + struct.pack(f"<{len(counts)}d", *counts)


def write_sdp(path):
    survey = [100.0 + i for i in range(301)]
    c1s = [1000.0 + 5 * i for i in range(41)]
    c1s_b = [10.0] * 21
    data = (sdp.MAGIC + struct.pack("<HH", 1, 3)
            + b"\0" * 10
            + _block("Polymer film", 1000.0, -1.0 * 1000 / 300, survey)
            + _block("C1s Scan", 295.0, -0.25, c1s)
            + _block("", 290.0, -0.5, c1s_b))
    path.write_bytes(data)
    return path, survey, c1s


def _roundtrip(levels):
    proj = kfitio.read_bytes(kfitwrite.to_bytes(levels))
    assert proj.names == list(levels)
    return proj


def test_synthetic(tmp_path):
    path, survey, c1s = write_sdp(tmp_path / "film.sdp")
    levels = sdp.read_sdp(path)
    # description "C1s Scan" -> C1s; an empty one falls back on the BE range
    assert list(levels) == ["Survey", "C1s", "C1s1"]
    assert levels["C1s"]["B.E."][0] == 295.0
    assert levels["C1s"]["B.E."][-1] == 285.0
    assert levels["C1s"]["Raw Data"] == c1s
    info = levels["Survey"]["ExperimentalInfo"]
    assert info["Sample ID"] == "Polymer film"
    assert info["Source File"] == "orig.vms"
    assert info["Source Energy"] == "1486.60"
    assert info["Pass Energy"] == "50.00" and info["Sweeps"] == "8"
    assert info["Work Function"] == "4.50"
    assert info["Total Spectra"] == "3"
    assert ["Species & Transition", "Survey"] in \
        levels["Survey"]["experimental_description"]
    _roundtrip(levels)


def test_not_sdp(tmp_path):
    bad = tmp_path / "x.sdp"
    bad.write_bytes(b"hello")
    with pytest.raises(ValueError, match="XI SDP"):
        sdp.read_sdp(bad)


def test_identify_core_level_from_be():
    assert sdp.identify_core_level_from_be(1000, 0) == "Survey"
    assert sdp.identify_core_level_from_be(15, -5) == "VB"
    assert sdp.identify_core_level_from_be(540, 525) == "O1s"
    assert sdp.identify_core_level_from_be(3000, 2990) == "Unknown"


def test_many(tmp_path):
    a, _, _ = write_sdp(tmp_path / "a.sdp")
    b, _, _ = write_sdp(tmp_path / "b.SDP")
    bad = tmp_path / "c.sdp"
    bad.write_bytes(b"junk")
    levels = sdp.read_sdp_many([a, bad, b])
    assert list(levels) == ["Survey", "C1s", "C1s1", "Survey1", "C1s2",
                            "C1s3"]
    _roundtrip(levels)


def test_uppercase_extension_matches(tmp_path):
    fmt = next(f for f in sdp.FORMATS if not f.multi)
    assert fmt.matches(tmp_path / "Tb3O7.SDP")
    assert fmt.group == "SDP" and fmt.technique == "XPS"


@pytest.mark.skipif(not REAL.is_dir(), reason="real SDP files not present")
def test_real_files():
    files = sorted(p for p in REAL.iterdir()
                   if p.suffix.lower() == ".sdp")
    assert len(files) == 12
    for path in files:
        levels = sdp.read_sdp(path)
        assert "Survey" in levels and "C1s" in levels and "O1s" in levels
        for name, cl in levels.items():
            assert cl["B.E."][0] > cl["B.E."][-1]          # high -> low
            assert len(cl["B.E."]) == len(cl["Raw Data"])
            assert cl["ExperimentalInfo"]["Species & Transition"] in name
        _roundtrip(levels)
    ce = sdp.read_sdp(REAL / "CeO2 powder 99.9%, Rare Metallics Co.sdp")
    assert list(ce) == ["Survey", "VB", "Pr3d", "Si2p", "C1s", "O1s",
                        "La3d", "Survey1"]
    assert len(ce["Survey"]["B.E."]) == 1024
    assert ce["C1s"]["B.E."][0] == 290.0 and ce["C1s"]["B.E."][-1] == 270.0
    tb = next(p for p in files if p.suffix == ".SDP")
    assert instruments.Format("XPS", "SDP (.sdp)", (".sdp",),
                              sdp.read_sdp).matches(tb)
    many = sdp.read_sdp_many(files[:2])
    assert len(many) == len(sdp.read_sdp(files[0])) + \
        len(sdp.read_sdp(files[1]))
