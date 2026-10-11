"""VAMAS (.vms) import: parser, sheet naming, Casa fits, .kfit round trip.

Copyright (C) 2026 Gwilherm Kerherve

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.
"""

from pathlib import Path

import pytest

from khervebook import kfitio
from khervebook.instruments import Format, kfitwrite
from khervebook.instruments import vamas

HOME = Path.home()
PT4F = (HOME / "Documents/PycharmProjects/KherveFittingPro/Data-Examples"
        / "zz Metals/Metal Pt/Pt4f.vms")
CR2O3_FIT = HOME / ("Documents/PycharmProjects/KherveFitting/DATA/UKSAF/"
                    "Cr2O3 for O 1s fitting.vms")
WORKSHOP = HOME / "Downloads/Workshop_SO and Multiplet.vms"
TIO2_MAP = HOME / "Downloads/Charge Correction TiO2.vms"


def _block(species, transition, *, x_label="Kinetic Energy", start=1000.0,
           step=0.5, ys=(100.0, 200.0, 300.0, 200.0), unit="d",
           trans=None, comment=(), scans=2, dwell=0.1, hv=1486.6):
    """One NORM-mode VAMAS block, every parameter present."""
    lines = ["Block", "Sample A", "2024", "5", "17", "13", "45", "7", "0",
             str(len(comment)), *comment, "XPS", "0", "Al", str(hv), "0",
             "0", "0", "54.7", "0", "FAT", "20", "1", "4.5", "0", "0", "0",
             "0", "0", species, transition, "-1", x_label, "eV", str(start),
             str(step)]
    nvar = 2 if trans else 1
    lines += [str(nvar), "counts", unit]
    if trans:
        lines += ["Transmission", "d"]
    lines += ["pulse counting", str(dwell), str(scans), "0", "0", "0", "0",
              "0"]
    values = []
    for i, y in enumerate(ys):
        values.append(y)
        if trans:
            values.append(trans[i])
    lines.append(str(len(values)))
    lines += ["0", "1e9"] * nvar
    lines += [repr(float(v)) for v in values]
    return lines


def _vms(path, blocks):
    head = [vamas._IDENTIFIER, "Inst", "Model", "Op", "Exp", "1",
            "header comment", "NORM", "REGULAR", str(len(blocks)), "1",
            "Exp Variable", "d", "0", "0", "0", "0", str(len(blocks))]
    lines = head + [ln for b in blocks for ln in b] + ["end of experiment"]
    path.write_text("\n".join(lines) + "\n")
    return path


def _roundtrip(levels):
    return kfitio.read_bytes(kfitwrite.to_bytes(levels, "x.kfit"))


# --------------------------------------------------------------------------

def test_format_declared():
    (fmt,) = vamas.FORMATS
    assert isinstance(fmt, Format)
    assert fmt.technique == "XPS" and fmt.group == ""
    assert fmt.label == "Vamas file (.vms)" and fmt.exts == (".vms",)
    assert fmt.sniff is None and not fmt.multi and fmt.needs == ()
    assert fmt.matches("A/B/C.VMS")


def test_sheet_names():
    assert vamas.normalize_auger_and_valence_names("Fe LM2") == "Felmm"
    assert vamas.normalize_auger_and_valence_names("C KL1") == "Ckll"
    assert vamas.normalize_auger_and_valence_names("V.B.") == "VB"
    assert vamas.phi_region_base("Fe2p3") == "Fe2p"
    assert vamas.phi_region_base("C1s") == "C1s"
    assert vamas.normalize_sheet_name("C 1s") == "C1s"
    assert vamas.normalize_sheet_name("Su1s") == "Survey"
    assert vamas.normalize_sheet_name("Valence") == "VB"


def test_synthetic_file(tmp_path):
    path = _vms(tmp_path / "s.vms", [
        _block("C", "1s"),
        _block("C", "1s", trans=(2.0, 2.0, 4.0, 4.0)),
        _block("Wide", "none", x_label="Binding Energy", start=1100.0,
               step=-1.0, unit="c/s"),
        _block("O", "1s", scans=0),                 # 0 scans: skipped
    ])
    levels = vamas.read(path)
    assert list(levels) == ["C1s", "C1s1", "Wide"]

    c1s = levels["C1s"]
    # kinetic -> binding with the block's photon energy, x runs high -> low
    assert c1s["B.E."] == pytest.approx([486.6, 486.1, 485.6, 485.1])
    # counts / (scans * dwell), plotted trace corrected by transmission
    assert c1s["Corrected Data"] == pytest.approx([500, 1000, 1500, 1000])
    assert c1s["Transmission"] == pytest.approx([5.0] * 4)
    assert c1s["Raw Data"] == pytest.approx([500, 1000, 1500, 1000])
    info = c1s["ExperimentalInfo"]
    assert info["Sample ID"] == "Sample A"
    assert info["Date"] == "2024/5/17" and info["Time"] == "13:45:7"
    assert info["Source Energy"] == "1486.6"
    assert info["Pass Energy"] == "20.0"
    assert info["Species & Transition"] == "C 1s"
    assert info["Sputtering Energy"] == "N/A"
    assert info["Y Unit"] == "d"
    assert len(info) == len(vamas.VAMAS_EXP_LABELS)

    # second channel = transmission: x trimmed to the counts
    c1s1 = levels["C1s1"]
    assert len(c1s1["B.E."]) == 4
    assert c1s1["Transmission"] == pytest.approx([10, 10, 20, 20])
    assert c1s1["Raw Data"] == pytest.approx([250, 500, 375, 250])

    wide = levels["Wide"]
    assert wide["B.E."] == [1100.0, 1099.0, 1098.0, 1097.0]
    assert wide["Corrected Data"] == [100.0, 200.0, 300.0, 200.0]

    proj = _roundtrip(levels)
    assert [s.name for s in proj.sheets] == ["C1s", "C1s1", "Wide"]
    sheet = proj.sheets[0]
    assert sheet.descending
    assert sheet.y == pytest.approx(c1s["Raw Data"])


def test_casa_fit(tmp_path):
    comment = ["Casa Info Follows CasaXPS", "0", "0", "0", "0",
               "CASA region (*C 1s*) (*Shirley*) 996 1003 0 2 0 0 0 0 0 0",
               "CASA comp (*C 1s*) (*GL(30)*) Area 1000 0 1e20 -1 1 "
               "MFWHM 1.2 0.5 3 -1 1 Position 1001.6 995 1004 -1 1",
               "CASA comp (*C 1s*) (*LA(1.53,243)*) Area 500 0 1e20 0 0.5 "
               "MFWHM 1.4 0.5 3 0 1 Position 1000.0 995 1004 0 1"]
    path = _vms(tmp_path / "fit.vms", [_block("C", "1s", comment=comment)])
    levels = vamas.read(path)
    cl = levels["C1s"]
    peaks = cl["Fitting"]["Peaks"]
    assert list(peaks) == ["C1s p1", "C1s p2"]
    p1 = peaks["C1s p1"]
    assert p1["Position"] == pytest.approx(485.0)
    assert p1["Fitting Model"] == "GL (Area)" and p1["L/G"] == 30.0
    assert p1["Area"] == pytest.approx(round(1000 / (5.0 * 2 * 0.1), 2))
    assert p1["Constraints"]["L/G"] == "Fixed"
    p2 = peaks["C1s p2"]
    assert p2["Fitting Model"] == "LA*G (Area, σ/γ, γ)"
    assert p2["Constraints"]["Area"] == "A*0.5"
    bkg = cl["Background"]
    assert bkg["Bkg Type"] == "Shirley"
    assert (bkg["Bkg Low"], bkg["Bkg High"]) == (483.6, 490.6)
    assert bkg["Recorded_Ranges"] == [(0.0, 0.0, 483.6, 490.6)]
    sheet = _roundtrip(levels).sheets[0]
    assert [p["name"] for p in sheet.peaks] == ["C1s p1", "C1s p2"]
    assert not sheet.has_background             # curve not computed yet

    nofit = vamas.read(path, import_fitting=False)
    assert "Fitting" not in nofit["C1s"]


def test_rejects_other_files(tmp_path):
    bad = tmp_path / "x.vms"
    bad.write_text("hello\n1 2\n")
    with pytest.raises(ValueError):
        vamas.read(bad)
    trunc = tmp_path / "t.vms"
    full = _vms(tmp_path / "full.vms", [_block("C", "1s")]).read_text()
    trunc.write_text("\n".join(full.splitlines()[:40]))
    with pytest.raises(ValueError):
        vamas.read(trunc)


def test_inclusion_list_inherits_first_block(tmp_path):
    """A parameter inclusion list (here: only the comment, parameter 8, is
    written for later blocks) - the rest comes from the first block."""
    b1 = _block("C", "1s")
    head = [vamas._IDENTIFIER, "I", "M", "O", "E", "0", "NORM", "REGULAR",
            "2", "1", "Exp Variable", "d", "1", "8", "0", "0", "0", "2"]
    b2 = ["Block 2", "Sample B", "1", "comment line", "4"]
    b2 += ["0", "1e9"] + ["10.0", "20.0", "30.0", "40.0"]
    path = tmp_path / "incl.vms"
    path.write_text("\n".join(head + b1 + b2 + ["end of experiment"]) + "\n")
    header, blocks = vamas.read_vamas(path)
    assert blocks[1].block_comment == "comment line"
    assert blocks[1].species_label == "C"
    assert blocks[1].corresponding_variables[0].y_values == [10, 20, 30, 40]
    assert blocks[0].corresponding_variables[0].y_values[0] == 100.0


# --------------------------------------------------------------------------
# Real files (skipped when absent)

def _need(path):
    if not path.exists():
        pytest.skip(f"{path.name} not on this machine")


def test_real_pt4f():
    _need(PT4F)
    levels = vamas.read(PT4F)
    assert list(levels) == ["Pt4f"]
    cl = levels["Pt4f"]
    assert len(cl["B.E."]) == len(cl["Raw Data"]) > 100
    assert cl["B.E."][0] > cl["B.E."][-1]
    assert 60 < min(cl["B.E."]) < 80
    assert cl["ExperimentalInfo"]["Technique"] == "XPS"
    proj = _roundtrip(levels)
    assert proj.sheets[0].name == "Pt4f"
    assert proj.sheets[0].x == pytest.approx(cl["B.E."], abs=1e-9)


def test_real_casa_fits():
    for path in (CR2O3_FIT, WORKSHOP):
        if not path.exists():
            continue
        levels = vamas.read(path)
        fitted = [n for n, cl in levels.items() if "Fitting" in cl]
        assert fitted
        proj = _roundtrip(levels)
        assert any(s.peaks for s in proj.sheets)
        return
    pytest.skip("no Casa-fitted VAMAS file on this machine")


def test_real_map_mode():
    _need(TIO2_MAP)
    levels = vamas.read(TIO2_MAP)
    assert list(levels)[:6] == ["Wide", "Ti2s", "Ti2p", "VB", "C1s",
                                "TiLMM"]
    assert all(len(cl["B.E."]) == len(cl["Raw Data"])
               for cl in levels.values())
