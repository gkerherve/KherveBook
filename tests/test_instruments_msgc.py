"""MS / GC import (khervebook/instruments/msgc.py).

Copyright (C) 2026 Gwilherm Kerherve

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.
"""

import numpy as np
import pytest

from khervebook import kfitio
from khervebook.instruments import kfitwrite, msgc

MSP = ("Name: Benzene\nMW: 78\nNum Peaks: 4\n50 100; 51 200; 77 300; 78 999;\n"
       "\nName: Toluene\nNum Peaks: 3\n65 120\n91 999\n92 600\n")


def _labsolutions(path):
    t = np.arange(0, 600, 0.5)
    path.write_text(
        "[Header]\nApplication Name,LabSolutions\n"
        "[Peak Table(Detector A)]\nPeak#,R.Time\n1,2.5\n"
        "[Chromatogram (Detector A-Ch1)]\nInterval(msec),500\n"
        "R.Time (sec)\tIntensity\n"
        + "".join(f"{x}\t{np.exp(-((x - 300) / 5) ** 2) * 1e4:.3f}\n"
                  for x in t) + "[Footer]\n")
    return path


def test_msp_records_as_sticks(tmp_path):
    p = tmp_path / "lib.msp"
    p.write_text(MSP)
    levels = msgc.read_ms([str(p)])
    assert list(levels) == ["MS", "MS1"]
    benzene = levels["MS"]
    assert benzene["MS_Label"] == "Benzene"
    assert len(benzene["B.E."]) == 12                # 3 points per stick
    assert benzene["B.E."][:3] == pytest.approx([49.99, 50.0, 50.01])
    assert benzene["Raw Data"][:3] == [0.0, 100.0, 0.0]
    assert levels["MS1"]["MS_Label"] == "Toluene"
    assert levels["MS1"]["MS_X_Label"] == "m/z"


def test_profile_spectrum_kept(tmp_path):
    p = tmp_path / "profile.txt"
    mz = np.linspace(10, 20, 500)
    p.write_text("".join(f"{x} {np.exp(-((x - 15) / 0.1) ** 2)}\n"
                         for x in mz))
    s = msgc.read_ms(str(p))["MS"]
    assert len(s["B.E."]) == 500                     # span 10: not sticks
    assert s["MS_Label"] == "profile"


def test_labsolutions_seconds_to_minutes(tmp_path):
    levels = msgc.read_gc([str(_labsolutions(tmp_path / "run.txt"))])
    s = levels["GC"]
    assert len(s["B.E."]) == 1200                    # only the section
    assert s["B.E."][-1] == pytest.approx(599.5 / 60)
    assert max(s["Raw Data"]) == pytest.approx(1e4)
    assert s["GC_X_Label"] == "Retention time (min)"


def test_generic_chromatograms(tmp_path):
    a = tmp_path / "a.csv"
    a.write_text("Time (min),Signal\n" + "".join(
        f"{x:.2f},{x * 2:.2f}\n" for x in np.arange(0, 10, 0.1)))
    b = tmp_path / "b.txt"
    b.write_text("".join(f"{x:.2f}\t{x:.2f}\n" for x in np.arange(0, 5, 0.1)))
    levels = msgc.read_gc([str(b), str(a)])
    assert list(levels) == ["GC", "GC1"]
    assert levels["GC"]["GC_Label"] == "a"           # sorted by path


def test_sniffs(tmp_path):
    assert msgc.sniff_gc(_labsolutions(tmp_path / "x.txt"))
    p = tmp_path / "y.txt"
    p.write_text("1 2\n3 4\n")
    assert not msgc.sniff_gc(p)
    assert msgc.sniff_ms("lib.MSP") and not msgc.sniff_ms("x.csv")


def test_no_data(tmp_path):
    p = tmp_path / "empty.msp"
    p.write_text("Name: nothing\n")
    with pytest.raises(ValueError):
        msgc.read_ms([str(p)])


def test_round_trip(tmp_path):
    p = tmp_path / "lib.msp"
    p.write_text(MSP)
    levels = msgc.read_ms([str(p)])
    levels.update(msgc.read_gc([str(_labsolutions(tmp_path / "run.txt"))]))
    project = kfitio.read_bytes(kfitwrite.to_bytes(levels))
    assert project.names == ["MS", "MS1", "GC"]
    assert project.sheet("MS").y[1] == 100.0
    assert project.sheet("GC").raw["GC_Y_Label"] == "Signal (a.u.)"
