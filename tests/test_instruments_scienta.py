"""Scienta Omicron plot / map .txt and HDF5 map import (instruments/scienta).

Synthetic SES exports in the layout ``parse_scienta_file`` expects.

Copyright (C) 2026 Gwilherm Kerherve

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.
"""

import math

import numpy as np
import pytest

from khervebook import kfitio
from khervebook.instruments import kfitwrite, scienta

INFO = {"Lens Mode": "Transmission", "Pass Energy": "50",
        "Excitation Energy": "1486.6", "Energy Scale": "Binding",
        "Acquisition Mode": "Swept", "Energy Step": "0.1",
        "Step Time": "100", "Sample": "TiO2 film",
        "Spectrum Name": "spec", "Instrument": "R4000",
        "Location": "Lab 1", "User": "GK", "Date": "2024-05-01",
        "Time": "10:00:00"}


def _region(n, name, be, columns, sweeps=1):
    out = [f"[Region {n}]", f"Region Name={name}",
           "Dimension 1 name=Binding Energy [eV]",
           f"Dimension 1 size={len(be)}",
           "Dimension 1 scale=" + " ".join(f"{b:g}" for b in be)]
    if sweeps > 1:
        out += ["Dimension 2 name=Sweep", f"Dimension 2 size={sweeps}",
                "Dimension 2 scale=" + " ".join(str(i) for i in
                                                range(1, sweeps + 1))]
    out += ["", f"[Info {n}]", f"Region Name={name}"]
    out += [f"{k}={v}" for k, v in INFO.items()]
    out += ["", f"[Data {n}]"]
    for i, b in enumerate(be):
        out.append(f"{b:g} " + " ".join(f"{c[i]:g}" for c in columns))
    return out + [""]


def _peak(be, centre, height=1000.0):
    return 100 + height * np.exp(-((be - centre) / 0.8) ** 2)


def write_plot(path):
    """C 1s (31 points), a Valence region and a 5-point O1s region."""
    c = np.round(np.linspace(290, 287, 31), 2)
    vb = np.round(np.linspace(10, 0, 26), 2)
    o = np.array([533.0, 532.5, 532.0, 531.5, 531.0])
    lines = ["[Info]", "Number of Regions=3", "Version=1.3.1", ""]
    lines += _region(1, "C 1s fast", c, [_peak(c, 288.5)])
    lines += _region(2, "Valence Band", vb, [_peak(vb, 5, 50)])
    lines += _region(3, "O1s", o, [_peak(o, 532, 500)])
    path.write_text("\n".join(lines))
    return path


def write_map(path):
    """C1s with 3 sweeps (BE + 3 columns) and a single-sweep N 1s."""
    c = np.round(np.linspace(290, 287, 31), 2)
    n = np.round(np.linspace(402, 396, 25), 2)
    sweeps = [_peak(c, 288.5, h) for h in (900, 1000, 1100)]
    lines = ["[Info]", "Number of Regions=2", "Version=1.3.1", ""]
    lines += _region(1, "C1s_scan", c, sweeps, sweeps=3)
    lines += _region(2, "N 1s", n, [_peak(n, 399)])
    path.write_text("\n".join(lines))
    return path


def write_h5(path):
    """A Scienta Omicron HDF5 map: 4 Y positions x 41 kinetic energies."""
    h5py = pytest.importorskip("h5py")
    hv = 1486.68
    ke = np.linspace(hv - 290, hv - 286, 41)          # BE 290 -> 286
    rows = np.array([_peak(hv - ke, 288, 500 + 100 * i) for i in range(4)])
    with h5py.File(path, "w") as f:
        sd = f.create_group("acquisition/spectrum_definition")
        for k, v in {"acquisition_mode": "Image", "energy_mode": "Kinetic",
                     "lens_mode_name": "WideAngle",
                     "element_set_name": "Ti 2p_fast"}.items():
            sd[k] = v
        sd["pass_energy"] = 20.0
        sd["dwell_time"] = 0.2
        sd["acquisition_time"] = 120.0
        sl = f.create_group("acquisition/spectrum_log")
        sl["start_time"] = "2024-05-01T10:00:00"
        sl["stop_time"] = "2024-05-01T10:02:00"
        sp = f["acquisition"].create_group("spectrum")
        sp["name"] = "map1"
        d = sp.create_group("data")
        d["data"] = rows
        d["x_axis"] = ke
        d["y_axis"] = np.arange(4) * 0.5
        d["y_axis"].attrs["label"] = "Position"
        d["y_axis"].attrs["units"] = "mm"
        r = sp.create_group("data_reduced_1d")
        r["data"] = rows.sum(axis=0)
        r["x_axis"] = ke
        an = f.create_group("instrument/analyser")
        an["work_function"] = 4.5
        an["model"] = "DA30"
        an.create_group("excitation_source")["energy"] = hv
    return path, rows


def _roundtrip(levels):
    proj = kfitio.read_bytes(kfitwrite.to_bytes(levels))
    assert proj.names == list(levels)
    return proj


def test_plot_file(tmp_path):
    levels = scienta.read_plot(write_plot(tmp_path / "plot.txt"))
    assert list(levels) == ["C1s", "VB", "O1s"]
    c1s = levels["C1s"]
    assert len(c1s["B.E."]) == 31
    assert c1s["B.E."][0] == 290.0 and c1s["B.E."][-1] == 287.0
    assert c1s["Raw Data"][15] == pytest.approx(
        round(float(_peak(np.array([288.5]), 288.5)[0]), 2))
    info = c1s["ExperimentalInfo"]
    assert info["Region Name"] == "C 1s fast"       # original, not cleaned
    assert info["Species & Transition"] == "C1s"
    assert info["Sample ID"] == "TiO2 film"
    assert info["BE Start"] == "290.00" and info["Number of Points"] == "31"
    assert info["Sweeps Summed"] == "1"
    assert ["Pass Energy", "50"] in c1s["experimental_description"]
    # a region shorter than the metadata table: KherveFitting's sheet
    # re-read pads its columns with NaN down to the table's last row
    o1s = levels["O1s"]
    assert o1s["B.E."][:5] == [533.0, 532.5, 532.0, 531.5, 531.0]
    assert len(o1s["B.E."]) == len(o1s["ExperimentalInfo"])   # rows 2..23
    assert all(math.isnan(v) for v in o1s["B.E."][5:])
    assert len(o1s["Corrected Data"]) == 5
    proj = _roundtrip(levels)
    assert proj.sheet("C1s").descending
    assert proj.sheet("C1s").x[0] == 290.0


def test_plot_reader_refuses_a_map(tmp_path):
    with pytest.raises(ValueError, match="map"):
        scienta.read_plot(write_map(tmp_path / "map.txt"))
    with pytest.raises(ValueError, match="single-sweep"):
        scienta.read_map(write_plot(tmp_path / "plot.txt"))


def test_map_file_sums_sweeps(tmp_path):
    levels = scienta.read_map(write_map(tmp_path / "map.txt"))
    assert list(levels) == ["C1s", "N1s"]
    c = np.round(np.linspace(290, 287, 31), 2)
    mean = np.mean([_peak(c, 288.5, h) for h in (900, 1000, 1100)], axis=0)
    assert levels["C1s"]["Raw Data"] == pytest.approx(
        [round(v, 2) for v in mean])
    info = levels["C1s"]["ExperimentalInfo"]
    assert info["Region Name"] == "C1s"         # the proposed name
    assert info["Total Sweeps in File"] == "3"
    assert info["Sweeps Summed"] == "3"
    assert levels["N1s"]["ExperimentalInfo"]["Total Sweeps in File"] == "1"
    _roundtrip(levels)


def test_h5_map(tmp_path):
    path, rows = write_h5(tmp_path / "map.h5")
    assert scienta.sniff_h5(path)
    levels = scienta.read_h5(path)
    assert list(levels) == ["Ti2p"]
    ti = levels["Ti2p"]
    assert ti["B.E."][0] == pytest.approx(290.0)
    assert ti["B.E."][-1] == pytest.approx(286.0)
    # KE ascending -> BE flipped to run high -> low, rows reversed with it
    assert ti["Raw Data"] == pytest.approx(
        [round(v, 2) for v in rows.mean(axis=0)[::-1]], abs=0.006)
    info = ti["ExperimentalInfo"]
    assert info["Instrument"] == "DA30"
    assert info["Region Name"] == "Ti2p"
    assert info["Lens Mode"] == "WideAngle"
    assert info["Date"] == "2024-05-01" and info["Time"] == "10:00:00"
    assert info["Total Sweeps in File"] == "4"
    _roundtrip(levels)


def test_sniffs(tmp_path):
    plot = write_plot(tmp_path / "plot.txt")
    mp = write_map(tmp_path / "map.txt")
    other = tmp_path / "other.txt"
    other.write_text("285.0\t100\n284.9\t110\n")
    assert scienta.sniff_plot(plot) and not scienta.sniff_map(plot)
    assert scienta.sniff_map(mp) and not scienta.sniff_plot(mp)
    assert not scienta.sniff_plot(other) and not scienta.sniff_map(other)
    with pytest.raises(ValueError):
        scienta.read_plot(other)
    h5py = pytest.importorskip("h5py")
    plain = tmp_path / "plain.h5"
    with h5py.File(plain, "w") as f:
        f["x"] = [1, 2, 3]
    assert not scienta.sniff_h5(plain)
    assert not scienta.sniff_h5(other)


def test_clean_region_name():
    c = scienta.clean_region_name
    assert c("C 1s fast") == ("C1s", False)
    assert c("Ce_3d_2") == ("Ce3d", False)
    assert c("Survey") == ("Survey", True)
    assert c("wide scan") == ("Wide", True)
    assert c("Valence Band") == ("VB", True)
    assert c("C KLL") == ("CKLL", True)
    assert c("O1s2") == ("O1s", False)


def test_formats_registered():
    labels = {f.label: f for f in scienta.FORMATS}
    plot = labels["Scienta plot file (.txt)"]
    assert plot.group == "Scienta Omicron" and plot.technique == "XPS"
    assert plot.sniff is not None
    assert labels["Scienta HDF5 map (.h5)"].needs == ("h5py",)
