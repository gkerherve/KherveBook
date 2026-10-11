"""MRS, VG-Microtech, ASC and CSV import (instruments/xps_text) and the
intermediate-workbook replay they share (instruments/xlsxflow).

Real ASC files are used when present (~/Downloads/TiN); the rest are
synthetic files in the layout the original parsers expect.

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
from khervebook.instruments import kfitwrite, xlsxflow, xps_text

TIN = Path.home() / "Downloads" / "TiN"


def write_mrs(path, lo=280.0, up=290.0, n=21, survey=False):
    counts = [int(1000 + 500 * np.exp(-((up - i * (up - lo) / (n - 1)
                                         - 285) / 0.8) ** 2))
              for i in range(n)]
    kind = "Auto Survey" if survey else "Data Array"
    path.write_text(
        "desc=Polymer film\r\noper=GK\r\ntime_stamp=12/05/1999 10:00\r\n"
        "scan_total=4\r\nres=3\r\nspot=200\r\n"
        f"array_size={n}\r\ndata={kind}\r\nlo_be={lo}\r\nup_be={up}\r\n"
        "!\r\n" + "\r\n".join(str(c) for c in counts) + "\r\n!\r\n")
    return path, counts


def write_vg(path, region="C 1s", start=280.0, end=290.0, n=21):
    counts = [float(f"{1000 + 10 * i:.1f}") for i in range(n)]
    path.write_text(
        "VGX900 data\n"
        f"{start} {end} {(end - start) / (n - 1)} 0 0.1 {n} 20 -1486.6\n"
        f"{region}\n" + "\n".join(str(c) for c in counts) + "\n")
    return path, counts


def write_csv(path, start=290.0, n=11):
    be = [start - 0.5 * i for i in range(n)]
    y = [100.0 + 7.25 * i for i in range(n)]
    path.write_text("\n".join(f"{b},{v}" for b, v in zip(be, y)) + "\n")
    return path, be, y


def write_asc(path, start=290.0, n=11):
    be = [start - 0.5 * i for i in range(n)]
    y = [100.123 + 7.25 * i for i in range(n)]
    path.write_text("# BE  counts\n" + "\n".join(
        f"{b:.7e}\t{v:.7e}" for b, v in zip(be, y)) + "\n")
    return path, be, y


def _roundtrip(levels):
    proj = kfitio.read_bytes(kfitwrite.to_bytes(levels))
    assert proj.names == list(levels)
    return proj


# -- MRS ----------------------------------------------------------------------

def test_mrs(tmp_path):
    path, counts = write_mrs(tmp_path / "film_O.mrs")
    levels = xps_text.read_mrs(path)
    assert list(levels) == ["O1s"]
    o = levels["O1s"]
    assert o["B.E."][0] == 290.0 and o["B.E."][-1] == 280.0   # high -> low
    assert o["B.E."][1] == pytest.approx(289.5)
    assert o["Raw Data"] == counts
    assert o["Corrected Data"] == counts and o["Transmission"] == [1.0] * 21
    assert "ExperimentalInfo" not in o   # KherveFitting skips that sheet
    proj = _roundtrip(levels)
    assert proj.sheet("O1s").descending


def test_mrs_name_quirk(tmp_path):
    # the "_SU.mrs" suffix rule never matches (upper-cased name against a
    # lower-case ".mrs"), so the first map key inside the stem wins
    path, _ = write_mrs(tmp_path / "survey_SU.mrs", 0, 1000, 101, True)
    assert list(xps_text.read_mrs(path)) == ["S2p"]
    assert xps_text.get_core_level_from_filename("x_C.mrs") == "C1s"
    assert xps_text.get_core_level_from_filename("qq.mrs") == "qq"


def test_mrs_missing_data(tmp_path):
    bad = tmp_path / "bad.mrs"
    bad.write_text("desc=nothing here\n")
    with pytest.raises(ValueError, match="data section"):
        xps_text.read_mrs(bad)


def test_mrs_many(tmp_path):
    a, ca = write_mrs(tmp_path / "s_C.mrs")
    b, cb = write_mrs(tmp_path / "t_C.mrs", 280, 300, 41)
    c, _ = write_mrs(tmp_path / "u_O.mrs")
    levels = xps_text.read_mrs_many([a, b, c, tmp_path / "skip.txt"])
    assert list(levels) == ["C1s", "C1s1", "O1s"]
    assert levels["C1s"]["Raw Data"] == ca
    assert len(levels["C1s1"]["B.E."]) == 41
    _roundtrip(levels)


# -- VG-Microtech --------------------------------------------------------------

def test_vg(tmp_path):
    path, counts = write_vg(tmp_path / "a.1")
    assert xps_text.sniff_vg(path)
    levels = xps_text.read_vg(path)
    assert list(levels) == ["C1s"]
    c = levels["C1s"]
    assert c["B.E."][0] == 280.0 and c["B.E."][-1] == 290.0
    assert c["Raw Data"] == counts
    _roundtrip(levels)


def test_vg_sniff_rejects_other_text(tmp_path):
    other = tmp_path / "data.1"
    other.write_text("hello\nworld\nfoo\nbar\n")
    assert not xps_text.sniff_vg(other)
    with pytest.raises(ValueError, match="VG-Microtech header"):
        xps_text.read_vg(other)


def test_vg_many(tmp_path):
    a, _ = write_vg(tmp_path / "a.1", "Survey", 0, 1000, 101)
    b, _ = write_vg(tmp_path / "b.1", "O 1s")
    c, _ = write_vg(tmp_path / "c.1", "O 1s")
    levels = xps_text.read_vg_many([a, b, c])
    assert list(levels) == ["Survey", "O1s", "O1s1"]
    assert len(levels["Survey"]["B.E."]) == 101
    _roundtrip(levels)


# -- ASC / CSV ----------------------------------------------------------------

def test_asc_values_stay_two_decimals(tmp_path):
    path, be, y = write_asc(tmp_path / "C1s.asc")
    levels = xps_text.read_asc(path)
    assert list(levels) == ["C1s"]
    c = levels["C1s"]
    assert c["B.E."] == [round(b, 2) for b in be]
    assert c["Raw Data"] == [float(f"{v:.2f}") for v in y]
    assert "experimental_description" not in c
    _roundtrip(levels)


def test_asc_many_full_precision(tmp_path):
    a, _, ya = write_asc(tmp_path / "C1s_sample.asc")
    b, _, _ = write_asc(tmp_path / "O1s.asc", 535)
    levels = xps_text.read_asc_many([a, b])
    # the folder import writes numbers, so the refresh re-reads them in full
    # and normalises "C1s_sample" to "C1s"
    assert list(levels) == ["C1s", "O1s"]
    assert levels["C1s"]["Raw Data"] == pytest.approx(ya)
    assert levels["C1s"]["Name"] == "C1s_sample"


@pytest.mark.skipif(not TIN.is_dir(), reason="TiN .asc files not present")
def test_real_tin_asc():
    files = sorted(TIN.glob("*.asc"))
    levels = xps_text.read_asc(files[0])
    (name, sheet), = levels.items()
    assert name == files[0].stem
    assert len(sheet["B.E."]) == 2721
    assert sheet["B.E."][0] == 1355.0 and sheet["B.E."][1] == 1354.5
    assert sheet["Raw Data"][0] == 19627.27
    many = xps_text.read_asc_many(files)
    assert list(many) == [f.stem for f in files]
    _roundtrip(many)


def test_csv(tmp_path):
    pytest.importorskip("pandas")
    path, be, y = write_csv(tmp_path / "Si2p.run1.csv")
    levels = xps_text.read_csv(path)
    assert list(levels) == ["Si2p"]                    # split('.')[0]
    assert levels["Si2p"]["B.E."] == be
    assert levels["Si2p"]["Raw Data"] == y
    header = tmp_path / "head.csv"
    header.write_text("BE,Counts\n285,10\n")
    with pytest.raises(ValueError, match="numbers"):
        xps_text.read_csv(header)
    many = xps_text.read_csv_many([path, header, write_csv(
        tmp_path / "N1s.csv")[0]])
    assert list(many) == ["Si2p1", "N1s"]     # refresh: "Si2p.run1" -> Si2p + 1
    _roundtrip(many)


def test_text_formats_are_menu_only():
    by_label = {f.label: f for f in xps_text.FORMATS}
    for label in ("ASCII (.asc)", "CSV (.csv)", "ASCII files (.asc)",
                  "CSV files (.csv)", "MRS files (.mrs)",
                  "VG-Microtech files (.1)"):
        assert by_label[label].sniff("whatever") is False
    assert by_label["MRS (.mrs)"].sniff is None
    assert by_label["MRS files (.mrs)"].multi
    assert by_label["VG-Microtech (.1)"].group == "VG-Microtech"
    assert by_label["ASCII (.asc)"].group == ""


# -- xlsxflow ------------------------------------------------------------------

def test_refresh_name_normalisation():
    r = xlsxflow.refresh_name
    assert r("C 1s Scan") == "C1s"
    assert r("O1s Region 2") == "O1s2"
    assert r("XPS survey") == "Survey"
    assert r("Wide3") == "Wide3"
    assert r("CKLL") == "CKLL"
    n = xlsxflow.normalize_sheet_name
    assert n("Valence") == "VB" and n("Fermi edge") == "Fermi"
    assert n("Ti 2p") == "Ti2p" and n("sample_su") == "Survey"


def test_rename_keeps_old_name_and_reorders():
    wb = xlsxflow.Workbook()
    for name in ("O1s", "C 1s"):
        wb.create_sheet(name).set_columns(["BE", "Raw Data"], [1.0, 2.0],
                                          [3.0, 4.0])
    levels = xlsxflow.open_xlsx(wb)
    # renamed sheets go first; their 'Name' keeps the old title
    assert list(levels) == ["C1s", "O1s"]
    assert levels["C1s"]["Name"] == "C 1s"


def test_text_cells_stop_the_refresh():
    wb = xlsxflow.Workbook()
    wb.create_sheet("C1s Scan").set_columns(["BE", "Raw Data"],
                                            ["1.00", "2.00"],
                                            ["3.456", "4.00"])
    levels = xlsxflow.open_xlsx(wb)
    assert list(levels) == ["C1s"]                 # renamed before the stop
    assert levels["C1s"]["Raw Data"] == [3.46, 4.0]


def test_invalid_sheet_name():
    with pytest.raises(ValueError, match="invalid"):
        xlsxflow.Workbook().create_sheet("a/b")


def test_detect_picks_these_readers(tmp_path, monkeypatch):
    import sys
    sys.path.insert(0, str(Path(__file__).parent))
    import test_instruments_igor as ti
    import test_instruments_scienta as ts
    from khervebook import instruments
    from khervebook.instruments import igor, scienta, sdp
    monkeypatch.setattr(instruments, "_CACHE", instruments.in_menu_order(
        scienta.FORMATS + xps_text.FORMATS + igor.FORMATS + sdp.FORMATS))

    def label(path):
        fmt = instruments.detect(path)
        return fmt and fmt.label

    assert label(ts.write_plot(tmp_path / "p.txt")) == \
        "Scienta plot file (.txt)"
    assert label(ts.write_map(tmp_path / "m.txt")) == \
        "Scienta map file (.txt)"
    assert label(write_vg(tmp_path / "a.1")[0]) == "VG-Microtech (.1)"
    assert label(write_mrs(tmp_path / "a_C.mrs")[0]) == "MRS (.mrs)"
    assert label(ti.write_dat(tmp_path / "x.dat")[0]) == \
        "Igor data file (.dat)"
    assert label(ti.write_itx(tmp_path / "x.itx")[0]) == "Igor ITX (.itx)"
    assert label(tmp_path / "Tb.SDP") == "SDP (.sdp)"
    # generic text stays with the spreadsheet cell
    assert label(write_csv(tmp_path / "a.csv")[0]) is None
    assert label(write_asc(tmp_path / "a.asc")[0]) is None
    other = tmp_path / "notes.txt"
    other.write_text("just text\n")
    assert label(other) is None
