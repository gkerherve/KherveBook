"""Read a KherveFitting ``.kfit`` project into plain Python data.

A ``.kfit`` is an HDF5 container (``format="kfitting"``) holding a
zlib-compressed JSON project under ``project_json_gz``, with the bulky
per-sheet arrays (``B.E.``, ``Raw Data``, ``Bkg Y``) stored losslessly as
HDF5 datasets under ``core_levels`` instead of inside the JSON.

Every sheet — whatever the technique — uses the same three keys, a
legacy of the format starting life as XPS-only:

* ``B.E.``      — the x column (2θ for XRD, wavenumber for FTIR, …)
* ``Raw Data``  — the y column
* ``Background`` — ``Bkg X`` / ``Bkg Y`` (the background curve; equal to
  the raw data until a background is defined) plus ``Bkg Low`` /
  ``Bkg High``, the fitting range
* ``Fitting`` → ``Peaks`` — one entry per fitted peak

The technique is read from the sheet *name* (``XRD1``, ``FTIR``,
``Raman``, ``TGA2``, …), which is what KherveFitting itself does; the
axis-label table below is ported from its ``Plot_Operations`` so a
KherveBook plot is labelled the way the same data is in KherveFitting.

Copyright (C) 2026 Gwilherm Kerherve

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.
"""

import io
import json
import zlib
from pathlib import Path

# ---------------------------------------------------------------------------
#  Axis labels per technique
# ---------------------------------------------------------------------------
#: (name test, x label, y label, per-sheet label key prefix). Ordered —
#: first match wins, so specific prefixes come before general ones. Ported
#: from KherveFitting's Plot_Operations._TECHNIQUE_AXES; anything that
#: matches nothing here is photoemission on a binding-energy axis.
_TECHNIQUE_AXES = (
    (lambda n: n.startswith("EDX~Plot"), "Energy (keV)", "Counts", None),
    (lambda n: n.startswith("TEM~Plot"), "Distance (nm)",
     "Intensity (a.u.)", "TEM"),
    (lambda n: n.startswith(("SEM", "TEM~Count", "TEM~Freq")),
     "Particle size (nm)", "Count", "SEM"),
    (lambda n: n.upper().startswith("FTIR"),
     "Wavenumber (cm$^{-1}$)", "Transmittance (%)", "FTIR"),
    (lambda n: n.upper().startswith("EELS"),
     "Energy Loss (eV)", "Intensity (a.u.)", None),
    (lambda n: n.upper().startswith("EIS"), "Z' (Ω)", "-Z'' (Ω)", "EIS"),
    (lambda n: n.upper().startswith("SQUID"),
     "Temperature (K)", "Moment (emu)", "SQUID"),
    (lambda n: n.upper().startswith("TGA"),
     "Temperature (°C)", "Mass (mg)", "TGA"),
    (lambda n: n.upper().startswith("XRD"), "2θ (°)",
     "Intensity (counts)", None),
    (lambda n: n.startswith("XAS"), "Photon Energy (eV)",
     "Intensity (a.u.)", None),
    (lambda n: n.startswith("RA") or "RAMAN" in n.upper()
     or n.startswith("Ra_"),
     "Wavenumber (cm$^{-1}$)", "Intensity (a.u.)", None),
)


def axis_labels(name: str, sheet: dict = None):
    """``(x label, y label)`` for a sheet, whichever technique it is.

    Techniques that vary their own axes (EIS switches between five views,
    SQUID between temperature and field, TGA between mass and heat flow)
    write the labels onto the sheet; the table entry is the fallback.
    """
    name = str(name or "")
    sheet = sheet if isinstance(sheet, dict) else {}
    for matches, x_label, y_label, key in _TECHNIQUE_AXES:
        if not matches(name):
            continue
        if key == "FTIR":
            return x_label, sheet.get("FTIR_Y_Unit") or y_label
        if key == "TEM":
            # A TEM line profile falls back to the SEM keys: those sheets
            # were built by the shared SEM writer before TEM had its own.
            return (sheet.get("TEM_X_Label") or sheet.get("SEM_X_Label")
                    or x_label,
                    sheet.get("TEM_Y_Label") or sheet.get("SEM_Y_Label")
                    or y_label)
        if key:
            return (sheet.get(f"{key}_X_Label") or x_label,
                    sheet.get(f"{key}_Y_Label") or y_label)
        return x_label, y_label
    return "Binding Energy (eV)", "Intensity (CPS)"


def is_xps_like(name: str) -> bool:
    """True when the sheet really is on a binding-energy axis.

    Peak fitting carries a pile of behaviour that only makes sense for
    photoemission — the reversed axis, eV-scale widths, the core-level
    name in the corner — and this is the one test for all of it.
    """
    name = str(name or "")
    return not any(matches(name) for matches, _x, _y, _k in _TECHNIQUE_AXES)


def x_descending(name: str) -> bool:
    """True when the x axis runs high -> low, as KherveFitting draws it.

    Binding energy does (the Avantage/Thermo convention) and so does FTIR
    wavenumber; every other technique reads left-to-right.
    """
    return is_xps_like(name) or str(name or "").upper().startswith("FTIR")


# ---------------------------------------------------------------------------
#  The data model
# ---------------------------------------------------------------------------
class KFitSheet:
    """One core level / technique sheet out of a project."""

    def __init__(self, name: str, raw: dict):
        self.name = name
        self.raw = raw if isinstance(raw, dict) else {}
        self.x = _floats(self.raw.get("B.E."))
        self.y = _floats(self.raw.get("Raw Data"))
        bkg = self.raw.get("Background")
        self.bkg = bkg if isinstance(bkg, dict) else {}
        self.background = _floats(self.bkg.get("Bkg Y"))
        self.peaks = _peaks(self.raw.get("Fitting"))

    # -- derived ---------------------------------------------------------
    @property
    def x_label(self):
        return axis_labels(self.name, self.raw)[0]

    @property
    def y_label(self):
        return axis_labels(self.name, self.raw)[1]

    @property
    def descending(self) -> bool:
        return x_descending(self.name)

    @property
    def fit_range(self):
        """``(low, high)`` x limits of the fitting region, or None.

        Peaks are only meaningful inside it — KherveFitting masks their
        fill to this range, so drawing them outside would invent signal.
        """
        low, high = self.bkg.get("Bkg Low"), self.bkg.get("Bkg High")
        try:
            low, high = float(low), float(high)
        except (TypeError, ValueError):
            return None
        return (min(low, high), max(low, high)) if high != low else None

    @property
    def has_background(self) -> bool:
        """True once a real background exists.

        Until one is calculated the key holds a copy of the raw data, so a
        plain "is it there" test would draw the background on top of the
        spectrum and call it a subtraction.
        """
        if len(self.background) != len(self.y) or not self.background:
            return False
        return self.background != self.y

    def summary(self) -> str:
        bits = [f"{len(self.x)} points"]
        if self.x:
            bits.append(f"{min(self.x):.3g}–{max(self.x):.3g}")
        if self.peaks:
            bits.append(f"{len(self.peaks)} peak"
                        f"{'s' if len(self.peaks) != 1 else ''}")
        return "  ·  ".join(bits)


class KFitProject:
    """A whole ``.kfit``: its sheets plus where it came from."""

    def __init__(self, sheets, sample="", source=""):
        self.sheets = sheets
        self.sample = sample
        self.source = source

    def __bool__(self):
        return bool(self.sheets)

    @property
    def names(self):
        return [s.name for s in self.sheets]

    def sheet(self, name):
        for s in self.sheets:
            if s.name == name:
                return s
        return self.sheets[0] if self.sheets else None


# ---------------------------------------------------------------------------
#  Reading
# ---------------------------------------------------------------------------
def _floats(values):
    """A list of floats, dropping anything that is not a finite number."""
    if values is None:
        return []
    out = []
    for v in values:
        try:
            out.append(float(v))
        except (TypeError, ValueError):
            out.append(float("nan"))
    return out


def _peaks(fitting):
    """``Fitting`` -> an ordered list of ``{"name", …params}`` dicts."""
    if not isinstance(fitting, dict):
        return []
    peaks = fitting.get("Peaks")
    if not isinstance(peaks, dict):
        return []
    out = []
    for name, params in peaks.items():
        if isinstance(params, dict):
            entry = {"name": str(name)}
            entry.update(params)
            out.append(entry)
    return out


def read_bytes(data: bytes) -> KFitProject:
    """Parse ``.kfit`` bytes. Raises ValueError if it is not one."""
    import h5py

    with h5py.File(io.BytesIO(data), "r") as f:
        fmt = f.attrs.get("format", "")
        if isinstance(fmt, bytes):
            fmt = fmt.decode("utf-8", "replace")
        if str(fmt).lower() != "kfitting":
            raise ValueError("not a KherveFitting .kfit project")
        project = _project_json(f)
        levels = project.get("Core levels")
        if not isinstance(levels, dict):
            levels = {}
        # The arrays live in HDF5, not in the JSON — merge them back so the
        # sheets below see one complete dict per core level.
        _merge_arrays(f, levels)

    sheets = [KFitSheet(name, lvl) for name, lvl in levels.items()
              if isinstance(lvl, dict)]
    return KFitProject(sheets, sample=_sample_name(project),
                       source=str(project.get("FilePath") or ""))


def read_path(path) -> KFitProject:
    return read_bytes(Path(path).read_bytes())


def _project_json(f) -> dict:
    ds = f.get("project_json_gz")
    if ds is None:
        return {}
    try:
        return json.loads(zlib.decompress(bytes(ds[()])).decode("utf-8"))
    except Exception:
        return {}


#: HDF5 dataset name -> where it belongs in the core-level dict.
_ARRAY_KEYS = {"B.E.": None, "Raw Data": None, "Bkg Y": "Background"}


def _merge_arrays(f, levels: dict):
    """Copy the HDF5 per-level arrays back over the JSON placeholders."""
    group = f.get("core_levels")
    if group is None:
        return
    for key in group:
        sub = group[key]
        name = sub.attrs.get("name", key)
        if isinstance(name, bytes):
            name = name.decode("utf-8", "replace")
        level = levels.get(str(name))
        if not isinstance(level, dict):
            continue
        for ds_name, parent in _ARRAY_KEYS.items():
            if ds_name not in sub:
                continue
            values = sub[ds_name][:].tolist()
            if parent is None:
                level[ds_name] = values
            elif isinstance(level.get(parent), dict):
                level[parent][ds_name] = values


def _sample_name(project) -> str:
    for key in ("SampleNames", "FilePath"):
        value = project.get(key) if isinstance(project, dict) else None
        if isinstance(value, list) and value:
            return Path(str(value[0])).name
        if isinstance(value, dict) and value:
            return str(next(iter(value.values())))
        if isinstance(value, str) and value:
            return Path(value).name
    return ""
