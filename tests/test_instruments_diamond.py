"""Diamond Light Source import: NeXus XPS/XAS, B07 XPS .dat, B07 XAS text.

No Diamond files ship with the project, so each test builds a small file
in the layout KherveFittingPro's parsers expect (h5py for NeXus).

Copyright (C) 2026 Gwilherm Kerherve

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.
"""

import numpy as np
import pytest

from khervebook import kfitio
from khervebook.instruments import kfitwrite
from khervebook.instruments import diamond

h5py = pytest.importorskip("h5py")


def _roundtrip(levels):
    return kfitio.read_bytes(kfitwrite.to_bytes(levels, "x.kfit"))


# --------------------------------------------------------------------------
# File builders (also used by the parity check against KherveFittingPro)

def make_i09_xps(path, sample="Pt foil"):
    """I09 EW4000: two regions, 2-D spectrum_data (slices summed), one in
    kinetic mode, step time + iterations for counts per second."""
    be = np.linspace(80.0, 65.0, 31)
    ke = np.linspace(2000.0, 2010.0, 21)
    with h5py.File(path, "w") as f:
        e = f.create_group("entry")
        e["instrument/beamline"] = "i09"
        e["sample/name"] = sample
        e["diamond_scan/start_time"] = "2025-03-04T10:11:12"
        e["diamond_scan/entry_identifier"] = "123456"
        e["experiment_identifier"] = "si12345-1"
        g = e.create_group("Pt4f_2keV")
        g["energies"] = be
        g["spectrum_data"] = np.vstack([np.arange(31.0), np.arange(31.0)])
        g["excitation_energy"] = 2100.0
        ins = e.create_group("instrument/Pt4f_2keV")
        ins["pass_energy"] = 100.0
        ins["step_time"] = 0.5
        ins["number_of_iterations"] = 4
        ins["lens_mode"] = "Angular56"
        ins["energy_mode"] = "Binding"
        ins["acquisition_mode"] = "Swept"
        g2 = e.create_group("O1s_kin")
        g2["energies"] = ke
        g2["spectrum_data"] = np.ones(21) * 10.0
        ins2 = e.create_group("instrument/O1s_kin")
        ins2["photon_energy"] = 2540.0
        ins2["energy_mode"] = "Kinetic"
        ins2["step_time"] = 0.1
        e.create_group("ew4000")                  # a skipped group
    return path


def make_b07_xps_nxs(path):
    """B07 naming: binding_energy / spectrum, count_time, no iterations."""
    with h5py.File(path, "w") as f:
        e = f.create_group("entry1")
        e["instrument/name"] = "b07"
        g = e.create_group("C1s")
        g["binding_energy"] = np.linspace(290.0, 280.0, 11)
        g["spectrum"] = np.arange(11.0) + 1
        ins = e.create_group("instrument/C1s")
        ins["count_time"] = 0.2
        ins["photon_energy"] = 495.0
    return path


def make_i09_xas(path, kev=False):
    """I09 jenergy scan: jI0 (I0), sdc (TEY) and one fluorescence channel,
    energies written high to low."""
    energy = np.linspace(545.0, 525.0, 41)
    if kev:
        energy = energy / 1000.0
    with h5py.File(path, "w") as f:
        e = f.create_group("entry")
        e["instrument/beamline"] = "i09"
        e["instrument/polarisation/value"] = "LH"
        e["diamond_scan/scan_command"] = "scan jenergy 0.525 0.545 jI0 sdc"
        for name, data in (("jI0", np.full(41, 2.0)),
                           ("sdc", np.linspace(1.0, 5.0, 41)),
                           ("fy", np.linspace(3.0, 1.0, 41))):
            g = e.create_group(name)
            g["jenergy"] = energy
            g["data"] = data
    return path


def make_arpes(path):
    """Diamond I05 ARPES: /entry1/analyser with a data cube, angles and
    energies - plus jenergy-like groups that must not make it 'XAS'."""
    with h5py.File(path, "w") as f:
        e = f.create_group("entry1")
        a = e.create_group("analyser")
        a["data"] = np.ones((2, 5, 7))
        a["angles"] = np.linspace(-15, 15, 5)
        a["energies"] = np.linspace(20, 21, 7)
        for name in ("sdc", "jI0"):
            g = e.create_group(name)
            g["energy"] = np.arange(10.0)
            g["data"] = np.arange(10.0)
    return path


B07_DAT_NAMES = [
    "b07-1-120131_C1s_250_D2_PE20_495_XPS.dat",
    "b07-1-120132_Au4f_250_D2_PE20_495_XPS.dat",
    "b07-1-120133_C1s_250_D2_PE20_495_XPS.dat",
    "b07-1-120135_O1s_250_D2_PE20_900_XPS.dat",
    "b07-1-120134_Survey_250_D2_H2O_78min_PE50_495_XPS.dat",
]


def make_b07_dat(path, n_scans=2, start=290.0):
    be = np.linspace(start - 10, start, 11)        # written low -> high
    lines = ["\t".join(["binding_energy", "intensity"]
                       + [f"spectrum_{i + 1}" for i in range(n_scans)])]
    for i, x in enumerate(be):
        scans = [float(i + k) for k in range(n_scans)]
        values = [x, sum(scans)] + scans
        lines.append("\t".join(repr(float(v)) for v in values))
    path.write_text("\n".join(lines) + "\n")
    return path


def make_b07_xas(path, columns=3, first=2.0):
    header = ["pgm_energy", "ca18b", "ca36b", "extra"][:columns]
    lines = ["\t".join(header)]
    for i in range(20):
        row = [770.0 + i * 0.5] + [1.0] * (columns - 2) + [first + i]
        lines.append("\t".join(repr(v) for v in row))
    path.write_text("\n".join(lines) + "\n\n")
    return path


# --------------------------------------------------------------------------

def test_formats_declared():
    fmts = {(f.technique, f.label): f for f in diamond.FORMATS}
    nxs = fmts[("XPS", "NeXus (I09 / B07 / I10) (.nxs)")]
    assert nxs.group == "Diamond Light Source" and nxs.multi
    assert nxs.needs == ("h5py",) and nxs.sniff is diamond.sniff_nxs_xps
    assert fmts[("XPS", "B07 XPS (.dat)")].sniff is diamond.is_b07_xps_dat
    assert fmts[("XPS", "B07 XPS (.dat) - one or more files")].multi
    assert fmts[("XAS", "Diamond-B07 file (.txt/.dat)")].exts == (".txt",
                                                                  ".dat")
    assert fmts[("XAS", "Diamond-B07 multiple files (folder)")].multi
    assert fmts[("XAS", "Diamond I09 / B07 NeXus (.nxs)")].multi
    # multi-file entries never claim a dropped file
    assert all(not f.sniff("x.dat") for f in diamond.FORMATS
               if f.multi and f.sniff is diamond._never)


def test_nexus_xps_i09(tmp_path):
    path = make_i09_xps(tmp_path / "i09-123456.nxs")
    assert diamond.detect(path) == "XPS"
    assert diamond.sniff_nxs_xps(path) and not diamond.sniff_nxs_xas(path)
    levels = diamond.read_nxs([str(path)])
    assert list(levels) == ["O1s", "Pt4f"]          # HDF5 name order
    pt = levels["Pt4f"]
    assert len(pt["B.E."]) == 31 and pt["B.E."][0] > pt["B.E."][-1]
    # two slices summed, then / (0.5 s x 4 iterations)
    assert pt["Raw Data"][3] == pytest.approx(2 * 3.0 / 2.0)
    assert pt["Corrected Data"] == pt["Raw Data"]
    info = pt["ExperimentalInfo"]
    assert info["Sample ID"] == "Pt foil"
    assert info["Instrument"] == "Diamond I09"
    assert info["Excitation Energy"] == "2100.00"
    assert info["Pass Energy"] == "100.0"
    assert info["Number of scans"] == "4"
    assert info["Date"] == "2025-03-04"
    assert info["Lens Mode"] == "Angular56"
    o1s = levels["O1s"]
    assert o1s["B.E."][0] == pytest.approx(540.0)       # 2540 - 2000 eV
    assert o1s["Raw Data"][0] == pytest.approx(100.0)   # 10 / 0.1 s
    proj = _roundtrip(levels)
    assert [s.name for s in proj.sheets] == ["O1s", "Pt4f"]
    assert proj.sheets[0].descending


def test_nexus_xps_b07_and_rows(tmp_path):
    a = make_b07_xps_nxs(tmp_path / "a.nxs")
    b = make_b07_xps_nxs(tmp_path / "b.nxs")
    levels = diamond.read_nxs([str(a), str(b)])
    assert list(levels) == ["C1s", "C1s1"]
    cl = levels["C1s"]
    assert cl["Raw Data"][0] == pytest.approx(1 / 0.2)
    assert cl["ExperimentalInfo"]["Instrument"] == "Diamond B07"
    assert cl["ExperimentalInfo"]["Sample ID"] == "a"


def test_nexus_xas(tmp_path):
    path = make_i09_xas(tmp_path / "i09-xas.nxs", kev=True)
    assert diamond.detect(path) == "XAS"
    assert diamond.sniff_nxs_xas(path) and not diamond.sniff_nxs_xps(path)
    levels = diamond.read_nxs(str(path))
    assert list(levels) == ["XAS~O-K-fy-norm~", "XAS~O-K-fy~", "XAS~O-K~",
                            "XAS~O-K-TEY~", "XAS~O-K-I0~"]
    tey = levels["XAS~O-K~"]
    assert tey["B.E."][0] == pytest.approx(525.0)       # keV -> eV, sorted
    assert tey["B.E."] == sorted(tey["B.E."])
    assert tey["Raw Data"][0] == pytest.approx(5.0 / 2.0)
    assert tey["ExperimentalInfo"]["Signal"] == "TEY / I0 (sdc / jI0)"
    assert tey["ExperimentalInfo"]["Polarisation"] == "LH"
    proj = _roundtrip(levels)
    sheet = next(s for s in proj.sheets if s.name == "XAS~O-K~")
    assert not sheet.descending


def test_arpes_is_not_claimed(tmp_path):
    path = make_arpes(tmp_path / "i05-1.nxs")
    assert diamond.is_arpes_nexus(path)
    assert not diamond.sniff_nxs_xps(path)
    assert not diamond.sniff_nxs_xas(path)


def test_nexus_wrong_file(tmp_path):
    path = tmp_path / "empty.nxs"
    with h5py.File(path, "w") as f:
        f.create_group("entry")
    assert diamond.detect(path) is None
    with pytest.raises(ValueError):
        diamond.read_nxs([str(path)])
    junk = tmp_path / "junk.nxs"
    junk.write_bytes(b"not hdf5")
    assert not diamond.sniff_nxs_xps(junk)


def test_b07_dat_name_parsing():
    meta = diamond.parse_name(B07_DAT_NAMES[4])
    assert meta["scan"] == 120134 and meta["region"] == "Survey"
    assert (meta["temp"], meta["cond"], meta["pe"], meta["hv"]) == \
        (250, "D2", 50.0, 495)
    assert meta["label"] == "250 D2 H2O"
    metas = [diamond.parse_name(n) for n in B07_DAT_NAMES]
    rows, labels = diamond.plan_rows(metas)
    assert rows == [0, 0, 1, 2, 0]
    assert labels == ["250 D2 - 495 eV", "250 D2 - 495 eV (2)",
                      "250 D2 - 900 eV"]


def test_b07_dat_files(tmp_path):
    paths = [make_b07_dat(tmp_path / n, n_scans=2 + i)
             for i, n in enumerate(B07_DAT_NAMES)]
    assert diamond.is_b07_xps_dat(paths[0])
    assert not diamond.sniff_b07_xas(paths[0])
    levels = diamond.read_b07_dat_files([str(p) for p in paths])
    assert list(levels) == ["C1s", "Au4f", "C1s1", "Survey", "O1s2"]
    c1s = levels["C1s"]
    assert c1s["B.E."][0] == 290.0 and c1s["B.E."][-1] == 280.0
    # row i (x = 290 - i): intensity = sum of the 2 scans, averaged per scan
    assert c1s["Raw Data"][0] == pytest.approx((10 + 11) / 2)
    info = c1s["ExperimentalInfo"]
    assert info["Sample ID"] == "250 D2 - 495 eV"
    assert info["Pass Energy"] == "20" and info["Source Energy"] == "495.00"
    assert info["Number of scans"] == "2" and info["Scan"] == "120131"
    assert info["Condition"] == "250_D2"
    single = diamond.read_b07_dat(str(paths[0]))
    assert list(single) == ["C1s"]
    proj = _roundtrip(levels)
    assert len(proj.sheets) == 5 and proj.sheets[0].descending


def test_b07_dat_wrong_file(tmp_path):
    other = tmp_path / "other.dat"
    other.write_text("x\ty\n1\t2\n")
    assert not diamond.is_b07_xps_dat(other)
    with pytest.raises(ValueError):
        diamond.read_b07_dat(str(other))


def test_b07_xas_single_and_multi(tmp_path):
    dat = make_b07_xas(tmp_path / "OCP.dat", columns=3, first=2.0)
    txt = make_b07_xas(tmp_path / "Co_NEXAFS.txt", columns=4, first=4.0)
    assert diamond.sniff_b07_xas(dat) and diamond.sniff_b07_xas(txt)
    levels = diamond.read_b07_xas(str(dat))
    assert list(levels) == ["XAS~Co-L~"]
    cl = levels["XAS~Co-L~"]
    assert cl["B.E."][:2] == [770.0, 770.5]
    assert cl["Raw Data"][0] == 10000.0
    assert cl["Raw Data"][1] == 15000.0                 # 3 / 2 * 1e4
    assert cl["Corrected Data"] == cl["Raw Data"]
    assert "ExperimentalInfo" not in cl
    assert cl["Background"]["Bkg Low"] == 770.0
    multi = diamond.read_b07_xas_files([str(dat), str(txt)], edge="O-K")
    assert list(multi) == ["XAS~O-K~0", "XAS~O-K~1"]
    assert multi["XAS~O-K~1"]["Raw Data"][1] == 12500.0
    proj = _roundtrip(multi)
    assert [s.name for s in proj.sheets] == ["XAS~O-K~0", "XAS~O-K~1"]
    assert not proj.sheets[0].descending


def test_b07_xas_wrong_file(tmp_path):
    bad = tmp_path / "bad.txt"
    bad.write_text("energy\tsignal\nfoo\tbar\n")
    assert not diamond.sniff_b07_xas(bad)
    with pytest.raises(ValueError):
        diamond.read_b07_xas(str(bad))
    zero = make_b07_xas(tmp_path / "zero.dat", first=0.0)
    with pytest.raises(ValueError):
        diamond.read_b07_xas(str(zero))
    xps = make_b07_dat(tmp_path / "b07-1-1_C1s_PE20_XPS.dat")
    assert not diamond.sniff_b07_xas(xps)
    plain = tmp_path / "notes.txt"
    plain.write_text("just some notes\nwith words\n")
    assert not diamond.sniff_b07_xas(plain)
