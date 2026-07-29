"""Tests for reading, plotting and holding a KherveFitting .kfit project.

The fixtures are synthesised rather than copied from KherveFitting so the
suite runs without that repo checked out next door.

Copyright (C) 2026 Gwilherm Kerherve

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.
"""

import json
import zlib

import numpy as np
import pytest

from khervebook import kfitio, kfitmodels
from khervebook.kfitcell import KFitCell

h5py = pytest.importorskip("h5py")


def _peak(name="C1s A", position=284.8, height=1000.0, fwhm=1.2,
          model="GL (Area)", **extra):
    sigma = fwhm / (2 * np.sqrt(2 * np.log(2)))
    peak = {"Position": position, "Height": height, "FWHM": fwhm,
            "L/G": 30.0, "Area": height * sigma * np.sqrt(2 * np.pi),
            "Sigma": 0.5, "Gamma": 0.5, "Skew": 0.0,
            "Fitting Model": model}
    peak.update(extra)
    return name, peak


def make_kfit(path, sheets):
    """Write a minimal but real .kfit: JSON project + HDF5 arrays.

    *sheets* is ``[(name, x, y, background, {peak name: params})]``.
    """
    levels = {}
    for name, x, y, background, peaks in sheets:
        levels[name] = {
            "Name": name, "B.E.": list(x), "Raw Data": list(y),
            "Background": {"Bkg Type": "Shirley", "Bkg X": list(x),
                           "Bkg Y": list(background),
                           "Bkg Low": float(min(x)),
                           "Bkg High": float(max(x))},
            "Fitting": {"Peaks": dict(peaks)} if peaks else {},
        }
    project = {"FilePath": str(path), "Number of Core levels": len(levels),
               "Core levels": levels, "SampleNames": {}}
    blob = zlib.compress(json.dumps(project).encode("utf-8"))
    with h5py.File(path, "w") as f:
        f.attrs["application"] = "KherveFitting"
        f.attrs["format"] = "kfitting"
        f.attrs["version"] = 1
        group = f.create_group("core_levels")
        for i, (name, x, y, background, _p) in enumerate(sheets):
            sub = group.create_group(f"core_level_{i}")
            sub.attrs["name"] = name
            sub.create_dataset("B.E.", data=np.asarray(x, dtype=float))
            sub.create_dataset("Raw Data", data=np.asarray(y, dtype=float))
            sub.create_dataset("Bkg Y",
                               data=np.asarray(background, dtype=float))
        f.create_dataset("project_json_gz",
                         data=np.frombuffer(blob, dtype=np.uint8))
    return path


@pytest.fixture
def xps_kfit(tmp_path):
    x = np.linspace(280.0, 292.0, 240)
    background = np.full_like(x, 500.0)
    y = background + 1000 * np.exp(-4 * np.log(2) * ((x - 284.8) / 1.2) ** 2)
    return make_kfit(tmp_path / "sample.kfit",
                     [("C1s", x, y, background, dict([_peak()])),
                      ("Survey", x, y, y, {})])


# -- reading ---------------------------------------------------------------
def test_reads_every_sheet_with_its_arrays(xps_kfit):
    project = kfitio.read_path(xps_kfit)
    assert project.names == ["C1s", "Survey"]
    c1s = project.sheet("C1s")
    assert len(c1s.x) == 240 and len(c1s.y) == 240
    assert len(c1s.peaks) == 1 and c1s.peaks[0]["name"] == "C1s A"


def test_a_non_kfit_file_is_rejected(tmp_path):
    path = tmp_path / "not.kfit"
    with h5py.File(path, "w") as f:
        f.attrs["format"] = "ksheet"
    with pytest.raises(ValueError):
        kfitio.read_path(path)


def test_background_equal_to_the_raw_data_is_not_a_background(xps_kfit):
    """Until one is calculated the key holds a copy of the spectrum, so a
    plain presence test would draw the raw data over itself."""
    project = kfitio.read_path(xps_kfit)
    assert project.sheet("C1s").has_background
    assert not project.sheet("Survey").has_background


# -- techniques ------------------------------------------------------------
@pytest.mark.parametrize("name, x_label, descending", [
    ("C1s", "Binding Energy (eV)", True),
    ("Fe2p1", "Binding Energy (eV)", True),
    ("XRD2", "2θ (°)", False),
    ("FTIR", "Wavenumber (cm$^{-1}$)", True),
    ("Raman", "Wavenumber (cm$^{-1}$)", False),
    ("EELS1", "Energy Loss (eV)", False),
    ("TGA", "Temperature (°C)", False),
    ("SQUID3", "Temperature (K)", False),
    ("XAS", "Photon Energy (eV)", False),
    ("EDX~Plot1", "Energy (keV)", False),
])
def test_axis_labels_and_direction_follow_the_sheet_name(name, x_label,
                                                         descending):
    assert kfitio.axis_labels(name)[0] == x_label
    assert kfitio.x_descending(name) is descending


def test_a_sheet_overrides_its_own_axis_labels():
    """EIS and TGA switch between views, so they write the labels onto the
    sheet; the technique table is only the fallback."""
    sheet = {"TGA_X_Label": "Time (min)", "TGA_Y_Label": "Mass (%)"}
    assert kfitio.axis_labels("TGA1", sheet) == ("Time (min)", "Mass (%)")
    assert kfitio.axis_labels("TGA1", {})[0] == "Temperature (°C)"


# -- lineshapes ------------------------------------------------------------
@pytest.mark.parametrize("model", [
    "GL (Area)", "SGL (Area)", "GL (Height)", "SGL (Height)",
    "Voigt (Area)", "Pseudo-Voigt (Area)", "LA (Area, σ, γ)",
    "A*GL (Area, a, b)", "A*SGL (Area, a, b)",
])
def test_each_model_peaks_at_its_stored_position(model):
    x = np.linspace(280.0, 290.0, 1001)
    _name, peak = _peak(position=284.8, model=model)
    curve = kfitmodels.peak_curve(x, peak)
    assert curve is not None
    assert x[int(np.argmax(curve))] == pytest.approx(284.8, abs=0.05)


def test_gl_area_reproduces_the_stored_height():
    """The stored Area and Height describe the same peak — if the area
    normalisation is wrong the curve is right-shaped but wrong-sized."""
    x = np.linspace(280.0, 290.0, 2001)
    _name, peak = _peak(height=1234.0, fwhm=1.4)
    curve = kfitmodels.peak_curve(x, peak)
    assert curve.max() == pytest.approx(1234.0, rel=0.01)


def test_an_unknown_model_is_reported_not_guessed():
    _name, peak = _peak(model="TLA (A, μ, α, Wg)")
    assert kfitmodels.peak_curve(np.linspace(0, 10, 50), peak) is None
    assert not kfitmodels.is_supported(peak)


def test_non_spectral_fits_are_listed_separately():
    assert "D-parameter" in kfitmodels.NON_SPECTRAL
    assert "Curie-Weiss" in kfitmodels.NON_SPECTRAL


# -- the cell --------------------------------------------------------------
def test_cell_loads_a_project_and_lists_its_sheets(qapp, xps_kfit):
    cell = KFitCell()
    assert cell.attach(str(xps_kfit))
    assert [cell._sheet_box.itemText(i)
            for i in range(cell._sheet_box.count())] == ["C1s", "Survey"]
    assert cell.current_sheet().name == "C1s"


def test_cell_table_has_a_column_per_curve(qapp, xps_kfit):
    cell = KFitCell()
    cell.attach(str(xps_kfit))
    model = cell._table.model()
    headers = [model.headerData(i, 1) for i in range(model.columnCount())]
    assert headers == ["Binding Energy (eV)", "Intensity (CPS)",
                       "Background", "C1s A", "Envelope"]
    assert model.rowCount() == 240


def test_cell_plots_every_sheet_including_ones_without_peaks(qapp, xps_kfit):
    cell = KFitCell()
    cell.attach(str(xps_kfit))
    assert cell._plot is not None
    cell._sheet_box.setCurrentIndex(1)          # Survey: no fitted peaks
    assert cell._plot is not None
    assert "No fitted peaks" in cell._hint.text()


def test_cell_round_trips_through_the_kbook_source(qapp, xps_kfit):
    cell = KFitCell()
    cell.attach(str(xps_kfit))
    cell._sheet_box.setCurrentIndex(1)
    cell.show_data()
    restored = KFitCell(cell.source())
    assert restored.current_sheet().name == "Survey"
    assert restored._tabs.currentIndex() == 1
    assert restored._att.name == "sample.kfit"


def test_a_large_project_moves_to_the_sidecar_folder(qapp, xps_kfit,
                                                     tmp_path):
    """Anything over the embed limit is written beside the notebook so the
    .kbook stays small and Git versions the project itself."""
    from khervebook import filecell

    cell = KFitCell()
    cell.attach(str(xps_kfit))
    cell.set_context(tmp_path, "notes")
    cell.materialize()
    doc = json.loads(cell.source())
    if xps_kfit.stat().st_size > filecell.EMBED_LIMIT:
        assert doc["file"]["path"] == "notes_files/sample.kfit"
        assert (tmp_path / "notes_files" / "sample.kfit").exists()
    else:
        assert "embed" in doc["file"]


def test_an_empty_cell_says_what_to_do(qapp):
    cell = KFitCell()
    assert cell.current_sheet() is None
    assert "Load .kfit" in cell._hint.text()


def test_a_project_that_cannot_be_read_reports_it(qapp, tmp_path):
    broken = tmp_path / "broken.kfit"
    broken.write_bytes(b"not an HDF5 file at all")
    cell = KFitCell()
    cell.attach(str(broken))
    assert cell.current_sheet() is None
    assert cell._hint.text()          # the parse error, not an empty cell
