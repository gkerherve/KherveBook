"""PHI .spe / .pro import (khervebook.instruments.phi).

No real PHI files ship with the repo, so they are built here with struct
in the layouts KherveFitting's ``open_spe_file`` / ``open_pro_file``
decode: a SOFH…EOFH text header, a zero-filled record directory, then the
intensities (float32 / float64 after the header, float64 at the end for
Quantum 2000; float32 c/s region-major / cycle-minor for .pro).

Copyright (C) 2026 Gwilherm Kerherve

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.
"""

import struct

import numpy as np
import pytest

from khervebook import kfitio
from khervebook.instruments import kfitwrite, phi

A, B = 29.443, 0.222

# (n, name, Z, npts, step, start, end, coll_time, pass energy)
SPE_REGIONS = [
    (1, "Su1s", -1, 40, 1.0, 1100.0, 1061.0, 0.05, 224.0),
    (2, "C1s", 6, 25, 0.1, 295.0, 292.6, 0.2, 55.0),
    (3, "Fe2p3", 26, 30, 0.2, 715.0, 709.2, 0.2, 55.0),
]


def _regdef(r):
    n, name, z, npts, step, start, end, ct, pe = r
    return (f"SpectralRegDef: {n} {n} {name} {z} {npts} {step} {start} "
            f"{end} {start + 1} {end - 1} {ct} {pe:.1f} FAT")


def _header(extra, regions):
    lines = ["SOFH",
             "Platform: Windows",
             "FileType: SPE",
             "InstrumentModel: PHI 5000 VersaProbe III",
             "FileDate: 2024 03 05",
             "XraySource: Al 1486.6 25W",
             "AnalyserWorkFcn: 4.212 eV",
             "AnalyserMode: FAT",
             "XrayBeamDiameter: 100.0 um",
             "SpatialAreaDesc: 1 Wafer B, spot 2",
             f"IntensityCalCoeff: {A} {B}",
             "Operator: gk"] + list(extra)
    lines += [_regdef(r) for r in regions]
    # the *Full / *2 variants are not acquired regions
    lines += ["SpectralRegDefFull: 9 9 O1s 8 10 0.1 540 530 0 0 0.1 55 FAT",
              "SpectralRegDef2: 9 9 O1s 8 10 0.1 540 530 0 0 0.1 55 FAT",
              "EOFH"]
    return ("\r\n".join(lines) + "\r\n").encode("latin-1")


def _counts(npts, base):
    return [base + 7.0 * k + (k % 3) for k in range(npts)]


def make_spe(path, kind="versaprobe"):
    blocks = [_counts(r[3], 500.0 * (i + 1)) for i, r in
              enumerate(SPE_REGIONS)]
    flat = [v for b in blocks for v in b]
    if kind == "versaprobe":
        body = bytes(40) + struct.pack(f"<{len(flat)}f", *flat)
    elif kind == "xtool":
        body = bytes(40) + struct.pack(f"<{len(flat)}d", *flat)
    else:  # quantum 2000: float64 at the very end
        body = bytes(2100) + struct.pack(f"<{len(flat)}d", *flat)
    path.write_bytes(_header(["Comments: test acquisition"], SPE_REGIONS)
                     + body)
    return path, blocks


@pytest.mark.parametrize("kind", ["versaprobe", "xtool", "quantum2000"])
def test_spe_variants(tmp_path, kind):
    p, blocks = make_spe(tmp_path / "s.spe", kind)
    levels = phi.read_spe(str(p))
    assert list(levels) == ["Survey", "C1s", "Fe2p"]

    c1s = levels["C1s"]
    assert len(c1s["B.E."]) == 25
    assert c1s["B.E."][0] == pytest.approx(295.0)
    assert c1s["B.E."][-1] == pytest.approx(292.6)
    t = phi.phi_transmission(1486.6 - np.array(c1s["B.E."]), 55.0, A, B)
    assert c1s["Raw Data"] == pytest.approx(list(np.array(blocks[1]) / t),
                                            rel=1e-6)
    # no separate raw / transmission column in an .spe sheet
    assert c1s["Corrected Data"] == c1s["Raw Data"]
    assert c1s["Transmission"] == [1.0] * 25

    info = c1s["ExperimentalInfo"]
    assert info["Species & Transition"] == "C1s"
    assert info["Instrument"] == "PHI 5000 VersaProbe III"
    assert info["Date"] == "2024/03/05"
    assert info["Work Function"] == "4.212"
    assert info["Source width X"] == "100.0"
    assert info["X Start"] == "295.00" and info["X Step"] == "0.1000"
    assert info["Num Y Values"] == "25"
    assert info["Block Comment"] == "test acquisition"
    assert info["Sample ID"] == "s.spe"
    assert levels["Fe2p"]["ExperimentalInfo"]["Species & Transition"] \
        == "Fe2p3"


def test_phi_transmission_casa_values():
    # CasaXPS on a VersaProbe III file: O1s T = 51.53, C1s T = 49.97
    t = phi.phi_transmission([1486.6 - 531.0, 1486.6 - 285.0], 55, A, B)
    assert t == pytest.approx([51.53, 49.97], abs=0.1)


def test_spe_kfit_roundtrip(tmp_path):
    p, _ = make_spe(tmp_path / "s.spe")
    levels = phi.read_spe(str(p))
    proj = kfitio.read_bytes(kfitwrite.to_bytes(levels))
    assert proj.names == list(levels)
    assert proj.sheets[1].y == pytest.approx(levels["C1s"]["Raw Data"])


PRO_REGIONS = [
    (1, "C1s", 6, 20, 0.1, 290.0, 288.1, 0.5, 55.0),
    (2, "Fe2p3", 26, 15, 0.2, 712.0, 709.2, 0.25, 55.0),
]
CYCLES = 3


def make_pro(path):
    blocks = []
    for i, r in enumerate(PRO_REGIONS):
        for c in range(CYCLES):
            blocks.append(_counts(r[3], 200.0 * (i + 1) + 50.0 * c))
    flat = [v for b in blocks for v in b]
    # spectra, then sputter-time + intensity tables, then a record tail
    tables = [float(k) for k in range(2 * len(PRO_REGIONS) * CYCLES)]
    body = (bytes(64) + struct.pack(f"<{len(flat)}f", *flat)
            + struct.pack(f"<{len(tables)}f", *tables) + bytes(100))
    head = _header([f"NoDPDataCyc: {CYCLES}", "SputterEnergy: 2000",
                    "FileDesc: profile"], PRO_REGIONS)
    path.write_bytes(head + body)
    return path, blocks


def test_pro_depth_profile(tmp_path):
    p, blocks = make_pro(tmp_path / "depth.pro")
    levels = phi.read_pro(str(p))
    assert list(levels) == ["C1s", "C1s1", "C1s2", "Fe2p", "Fe2p1", "Fe2p2"]

    c1 = levels["C1s1"]                 # C1s, cycle 1
    assert len(c1["B.E."]) == 20
    assert c1["B.E."][0] == pytest.approx(290.0)
    assert c1["B.E."][-1] == pytest.approx(288.1)
    raw = np.array(blocks[1]) * 0.5     # c/s x collection time
    assert c1["Corrected Data"] == pytest.approx(list(raw), rel=1e-6)
    t = phi.phi_transmission(1486.6 - np.array(c1["B.E."]), 55.0, A, B)
    assert c1["Transmission"] == pytest.approx(list(t))
    assert c1["Raw Data"] == pytest.approx(list(raw / t), rel=1e-6)

    info = c1["ExperimentalInfo"]
    assert info["Sample ID"] == "Wafer B, spot 2"
    assert info["Sputter Time"] == "1" and info["Depth Cycle"] == "1"
    assert info["Sputtering Energy"] == "2000"
    assert info["Collection Time"] == "0.500"
    assert info["Pass Energy"] == "55"
    assert info["Source Energy"] == "1486.6"
    assert info["Operator"] == "gk"
    assert info["Block Comment"] == "PHI .pro depth profile - C1s cycle 1"

    fe = levels["Fe2p2"]
    assert fe["Corrected Data"][0] == pytest.approx(blocks[5][0] * 0.25)
    assert fe["ExperimentalInfo"]["Species & Transition"] == "Fe2p3"


def test_pro_kfit_roundtrip(tmp_path):
    p, _ = make_pro(tmp_path / "depth.pro")
    levels = phi.read_pro(str(p))
    proj = kfitio.read_bytes(kfitwrite.to_bytes(levels))
    assert proj.names == list(levels)
    assert proj.sheets[4].x == pytest.approx(levels["Fe2p1"]["B.E."])


def test_sniff_and_errors(tmp_path):
    spe, _ = make_spe(tmp_path / "s.spe")
    pro, _ = make_pro(tmp_path / "d.pro")
    assert phi.sniff_phi(str(spe)) and phi.sniff_phi(str(pro))

    # a Princeton WinSpec .spe / a qmake .pro are not PHI files
    other = tmp_path / "ccd.spe"
    other.write_bytes(bytes(4100))
    qmake = tmp_path / "app.pro"
    qmake.write_text("QT += widgets\nSOURCES += main.cpp\n")
    assert not phi.sniff_phi(str(other))
    assert not phi.sniff_phi(str(qmake))
    with pytest.raises(ValueError):
        phi.read_spe(str(other))
    with pytest.raises(ValueError):
        phi.read_pro(str(qmake))


def test_format_entries():
    spe, pro = phi.FORMATS
    assert (spe.technique, spe.group, spe.exts) == ("XPS", "Phi", (".spe",))
    assert (pro.technique, pro.group, pro.exts) == ("XPS", "Phi", (".pro",))
    assert spe.sniff is phi.sniff_phi and pro.sniff is phi.sniff_phi
