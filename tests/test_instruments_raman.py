"""Raman import (khervebook/instruments/raman.py).

Copyright (C) 2026 Gwilherm Kerherve

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.
"""

import numpy as np
import pytest

from khervebook import kfitio
from khervebook.instruments import kfitwrite, raman


def _spectrum(path):
    x = np.linspace(100, 1000, 300)
    path.write_text("#Acquired=10\nShift Intensity\n" + "".join(
        f"{a}\t{1000 * np.exp(-((a - 520.7) / 3) ** 2) + 50.123}\n"
        for a in x))
    return path


def test_single_file(tmp_path):
    levels = raman.read_file(str(_spectrum(tmp_path / "si.wafer.txt")))
    assert list(levels) == ["Raman_si"]              # up to the first dot
    s = levels["Raman_si"]
    assert len(s["B.E."]) == 300
    assert s["Raw Data"][0] == 50.12                 # two decimals
    assert s["Corrected Data"] == s["Raw Data"]
    assert s["Transmission"][0] == 1.0
    assert s["Background"]["Bkg High"] == 1000.0


def test_folder_names(tmp_path):
    for n in ("a", "b_" + "x" * 40, "b_" + "x" * 41):
        _spectrum(tmp_path / f"{n}.txt")
    (tmp_path / "empty.txt").write_text("no numbers\n")
    levels = raman.read_folder([str(tmp_path)])
    assert list(levels) == ["Raman_a", "Raman_b_" + "x" * 23,
                            "Raman_b_" + "x" * 19 + "_1"]
    assert all(len(name) <= 31 for name in levels)


def test_no_data(tmp_path):
    p = tmp_path / "x.txt"
    p.write_text("nothing\n")
    with pytest.raises(ValueError):
        raman.read_file(str(p))


def test_round_trip(tmp_path):
    levels = raman.read_file(str(_spectrum(tmp_path / "si.txt")))
    sheet = kfitio.read_bytes(kfitwrite.to_bytes(levels)).sheet("Raman_si")
    assert sheet.x_label == "Wavenumber (cm$^{-1}$)"
    assert sheet.y_label == "Intensity (a.u.)"
    assert not kfitio.is_xps_like("Raman_si")


def test_menu_only():
    assert all(not f.sniff("x.txt") for f in raman.FORMATS)
