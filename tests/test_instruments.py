"""The instrument-import layer: registry, detection, .kfit writing, KFit
cell import / refresh, drops and the File ▸ Import Instrument Data menu.

The readers themselves are tested in tests/test_instruments_<module>.py.

Copyright (C) 2026 Gwilherm Kerherve

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.
"""

import json

import numpy as np
import pytest

from khervebook import instruments, kfitio
from khervebook.instruments import Format, kfitwrite


def _read_fake(path):
    rows = np.loadtxt(path, delimiter=",")
    name = "C1s"
    return {name: kfitwrite.core_level(name, rows[:, 0], rows[:, 1],
                                       experimental_info={"Source": "fake"})}


def _read_many(paths):
    out = {}
    for p in paths:
        levels = _read_fake(p)
        for cl in levels.values():
            name = kfitwrite.unique_name(cl["Name"], out)
            cl["Name"] = name
            out[name] = cl
    return out


FAKE = Format("XPS", "Fake (.fake)", (".fake",), _read_fake, group="Test")
FAKE_MULTI = Format("XPS", "Fake files (.fake)", (".fake",), _read_many,
                    group="Test", multi=True, sniff=lambda p: False)
SNIFFED = Format("XRD", "Sniffed text (.txt)", (".txt",), _read_fake,
                 sniff=lambda p: open(p).read(5) == "#XRD\n")
GENERIC = Format("UV-Vis", "Generic (.txt)", (".txt",), _read_fake,
                 sniff=lambda p: False)


@pytest.fixture
def fake_formats(monkeypatch):
    monkeypatch.setattr(instruments, "_CACHE", instruments.in_menu_order(
        [FAKE, FAKE_MULTI, SNIFFED, GENERIC]))
    return instruments


def _spectrum(path, header=""):
    be = np.linspace(295, 280, 31)
    y = 100 + 900 * np.exp(-((be - 285) / 0.8) ** 2)
    path.write_text(header + "\n".join(f"{a},{b}" for a, b in zip(be, y)))
    return path


def test_core_level_matches_khervefitting():
    cl = kfitwrite.core_level("O1s", [1, 2, 3, 4], [10, 20, 30],
                              raw_values=[1, 2, 3], transmission=[1, 1, 1],
                              experimental_info={"PE": 20, "X": None})
    assert cl["B.E."] == [1.0, 2.0, 3.0]          # cut to the shortest
    assert cl["Raw Data"] == [10.0, 20.0, 30.0]
    assert cl["Corrected Data"] == [1.0, 2.0, 3.0]
    assert cl["ExperimentalInfo"] == {"PE": "20", "X": ""}
    assert cl["Background"]["Bkg Low"] == 1.0
    assert kfitwrite.unique_name("O1s", {"O1s", "O1s-2"}) == "O1s-3"


def test_written_project_is_khervefitting_shaped():
    import h5py, io, zlib
    levels = {"C1s": kfitwrite.core_level("C1s", [285.12345], [0.0123456])}
    data = kfitwrite.to_bytes(levels, "/x/a.kfit")
    with h5py.File(io.BytesIO(data)) as f:
        assert f.attrs["format"] == "kfitting"
        doc = json.loads(zlib.decompress(bytes(f["project_json_gz"][()])))
        assert f["core_levels/cl_0"].attrs["name"] == "C1s"
        assert f["core_levels/cl_0/B.E."][0] == 285.12345     # lossless
    assert doc["Number of Core levels"] == 1
    assert doc["Results Table9"] == {"Peak": {}}
    cl = doc["Core levels"]["C1s"]
    assert cl["B.E."] == [285.12] and cl["Raw Data"] == [0.012346]
    assert kfitio.read_bytes(data).names == ["C1s"]


def test_detect(fake_formats, tmp_path):
    assert instruments.detect(_spectrum(tmp_path / "a.fake")) is FAKE
    assert instruments.detect(_spectrum(tmp_path / "b.txt", "#XRD\n")) \
        is SNIFFED
    assert instruments.detect(_spectrum(tmp_path / "c.txt")) is None
    assert instruments.detect(tmp_path / "d.csv") is None
    assert instruments.techniques() == ["XPS", "UV-Vis", "XRD"]


def test_read_errors_are_explained(fake_formats, tmp_path):
    bad = tmp_path / "bad.fake"
    bad.write_text("not numbers")
    with pytest.raises(instruments.ImportFailed, match="bad.fake"):
        instruments.read(FAKE, bad)


def test_drop_imports_into_kfit_cell_and_refresh(qapp, fake_formats,
                                                 tmp_path):
    from khervebook.notebook import NotebookWidget
    src = _spectrum(tmp_path / "run.fake")
    nb = NotebookWidget()
    assert nb.open_file_in_cell(str(src))
    cell = nb.cells[-1]
    assert cell.CELL_TYPE == "kfit" and cell.file_name == "run.kfit"
    sheet = cell.project().sheet("C1s")
    assert len(sheet.x) == 31 and sheet.descending
    assert "Imported 1 file as XPS" in cell._hint.text()
    # Refresh re-reads the instrument file
    _spectrum(src)
    src.write_text(src.read_text() + "\n279,5")
    assert cell.refresh()
    assert len(cell.project().sheet("C1s").x) == 32
    # it round-trips, remembering where it came from
    back = NotebookWidget()
    back.load_json(nb.to_json())
    kf = back.cells[-1]
    assert kf._imported["label"] == "Fake (.fake)"
    assert kf.project().names == ["C1s"]
    # kfit() reads it like any project
    nb.cells[0].set_source("len(kfit('C1s').x)")
    nb.cells[0].execute(nb.kernel)
    assert nb.cells[0].output.text() == "32"
    # a plain .txt still opens as a sheet
    assert nb.open_file_in_cell(str(_spectrum(tmp_path / "plain.txt")))
    assert nb.cells[-1].CELL_TYPE == "sheet"


def test_multi_import_and_undo(qapp, fake_formats, tmp_path):
    from khervebook.notebook import NotebookWidget
    paths = [str(_spectrum(tmp_path / f"r{i}.fake")) for i in range(3)]
    nb = NotebookWidget()
    assert nb.import_instrument(FAKE_MULTI, paths)
    assert nb.cells[-1].project().names == ["C1s", "C1s-2", "C1s-3"]
    nb.undo()
    assert len(nb.cells) == 1


def test_failed_import_says_why(qapp, fake_formats, tmp_path):
    from khervebook.notebook import NotebookWidget
    bad = tmp_path / "bad.fake"
    bad.write_text("garbage")
    nb = NotebookWidget()
    assert not nb.import_instrument(FAKE, [str(bad)])
    assert "could not be read" in nb.cells[-1]._hint.text()


def test_menu_mirrors_techniques(qapp, fake_formats):
    from khervebook.mainwindow import MainWindow
    win = MainWindow()
    top = [a.text() for a in win.instrument_menu.actions()]
    assert top == ["XPS", "UV-Vis", "XRD"]
    xps = win.instrument_menu.actions()[0].menu()
    test = xps.actions()[0].menu()
    assert [a.text() for a in test.actions()] == ["Fake (.fake)…",
                                                  "Fake files (.fake)…"]
    win.close()
