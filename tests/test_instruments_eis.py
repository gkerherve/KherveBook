"""EIS import (khervebook/instruments/eis.py): SMaRT CSV, bare and polar
tables, the SMaRT binary .dat, the folder de-duplication and the .kfit
round trip.

Copyright (C) 2026 Gwilherm Kerherve

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.
"""

import numpy as np
import pytest

from khervebook import instruments, kfitio
from khervebook.instruments import eis, kfitwrite

F = np.logspace(6, -1, 30)
Z = 10 + 100 / (1 + 1j * 2 * np.pi * F * 100e-6)


def _smart_csv(path):
    lines = ["Exported SMaRT Impedance Data",
             "Experiment start time,01/02/2025 10:00", "",
             "Sweep Number,Point,Frequency (Hz),Z' Real (Ohm),"
             "Z'' Imag (Ohm),Temperature (°C)"]
    for s in (1, 2):
        for i in range(30):
            lines.append(f"{s},{i},{F[i]:.7g},{Z[i].real * s:.7g},"
                         f"{Z[i].imag * s:.7g},{25 + 10 * s}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def _smart_dat(path):
    rec = np.zeros(60, dtype=eis._DAT_DTYPE)
    rec['sweep'] = [0] * 30 + [1] * 30
    rec['frequency'] = np.tile(F, 2)
    rec['zreal'] = np.tile(Z.real, 2)
    rec['zimag'] = np.tile(Z.imag, 2)
    rec['temperature_c'] = 300.0
    path.write_bytes(b"SMaRT_Data" + b"\0" * 52 + rec.tobytes() + b"\0\0")
    return path


def test_smart_csv_sweeps(tmp_path):
    levels = eis.read_files([str(_smart_csv(tmp_path / "run.csv"))])
    assert list(levels) == ["EIS", "EIS1"]
    s = levels["EIS1"]
    assert len(s["B.E."]) == 30
    assert s["B.E."][0] == pytest.approx(2 * Z[0].real, rel=1e-6)
    # y is -Z''
    assert s["Raw Data"][-1] == pytest.approx(-2 * Z[-1].imag, rel=1e-6)
    assert s["EIS_Frequency"][0] == pytest.approx(F[0], rel=1e-6)
    assert s["EIS_Sweep"] == 2
    assert s["EIS_View"] == "nyquist"
    assert s["EIS_Temperature_C"] == pytest.approx(45)
    assert s["EIS_Label"] == "run - sweep 2 (45 °C)"
    assert s["ExperimentalInfo"]["Acquired"] == "01/02/2025 10:00"
    for key in ("EIS_Zreal", "EIS_Zimag", "EIS_Zmod", "EIS_Phase"):
        assert len(s[key]) == 30


def test_bare_table_and_polar(tmp_path):
    bare = tmp_path / "bare.txt"
    rows = [f"{F[i]:.7g}\t{Z[i].real:.7g}\t{-Z[i].imag:.7g}"
            for i in range(30)] * 2
    bare.write_text("\n".join(rows))
    levels = eis.read_files(str(bare))
    assert list(levels) == ["EIS", "EIS1"]       # split on the restart
    # a mostly-positive third column is already -Z''
    assert min(levels["EIS"]["Raw Data"]) >= 0

    polar = tmp_path / "polar.csv"
    polar.write_text("freq,Zmod (Ohm),Phase (deg)\n" + "".join(
        f"{F[i]},{abs(Z[i])},{np.degrees(np.angle(Z[i]))}\n"
        for i in range(30)))
    s = eis.read_files([str(polar)])["EIS"]
    assert s["B.E."][5] == pytest.approx(Z[5].real, rel=1e-9)


def test_binary_dat_and_folder_dedup(tmp_path):
    _smart_dat(tmp_path / "run.dat")
    _smart_csv(tmp_path / "run.csv")
    levels = eis.read_files([str(tmp_path / "run.dat")])
    assert list(levels) == ["EIS", "EIS1"]
    assert levels["EIS"]["EIS_Sweep"] == 1
    assert levels["EIS"]["ExperimentalInfo"]["File Format"] == \
        "SMaRT binary (.dat)"
    # The folder import keeps the .dat and drops its .csv twin.
    folder = eis.read_folder([str(tmp_path)])
    assert list(folder) == ["EIS", "EIS1"]
    assert {s["EIS_Source"] for s in folder.values()} == {"run.dat"}


def test_wrong_file(tmp_path):
    p = tmp_path / "x.csv"
    p.write_text("a,b\nhello,world\n")
    with pytest.raises(ValueError):
        eis.read_files([str(p)])


def test_sniff(tmp_path):
    assert eis.sniff(_smart_csv(tmp_path / "a.csv"))
    assert eis.sniff(_smart_dat(tmp_path / "a.dat"))
    plain = tmp_path / "plain.csv"
    plain.write_text("x,y\n1,2\n3,4\n5,6\n")
    assert not eis.sniff(plain)
    named = tmp_path / "named.csv"
    named.write_text("Frequency (Hz),Zre (Ohm),Zim (Ohm)\n1e5,10,-1\n1e4,20,-5\n")
    assert eis.sniff(named)


def test_round_trip_axis_labels(tmp_path):
    levels = eis.read_files([str(_smart_csv(tmp_path / "run.csv"))])
    project = kfitio.read_bytes(kfitwrite.to_bytes(levels))
    sheet = project.sheet("EIS")
    assert project.names == ["EIS", "EIS1"]
    assert sheet.x_label == "Z' (Ω)"
    assert sheet.y_label == "-Z'' (Ω)"
    assert sheet.y[3] == pytest.approx(-Z[3].imag, rel=1e-6)


def test_formats_registered():
    fmt = eis.FORMATS[0]
    assert fmt.technique == "EIS" and fmt.multi
    with pytest.raises(instruments.ImportFailed):
        instruments.read(fmt, ["/nonexistent/file.csv"])
