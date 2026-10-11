"""Build and write a KherveFitting ``.kfit`` project from imported data.

The importers in this package end where KherveFitting's own direct
importers end: a dict ``{sheet name: core level}`` of the same
core-level dicts KherveFitting builds. This module wraps it in the
project structure (``Init_Measurement_Data``) and writes the HDF5
container exactly as KherveFitting's ``write_kfitting`` does, so the
file opens in KherveFitting unchanged and KherveBook's KFit cell reads
it with `kfitio`.

Ported from KherveFittingPro (``libraries/ConfigFile.py``
``build_core_level_Data`` / ``Init_Measurement_Data`` and
``libraries/FileMenu/KFitting_IO.py`` ``write_kfitting``), wx-free.

Copyright (C) 2026 Gwilherm Kerherve

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.
"""

import io
import json
import math
import zlib

import numpy as np


def core_level(sheet_name, be_values, plot_values, raw_values=None,
               transmission=None, experimental_info=None):
    """One sheet, as KherveFitting's ``build_core_level_Data`` makes it.

    Mind its column mapping, reproduced on purpose: *plot_values* — the
    (transmission-corrected) trace that is plotted and fitted — lands in
    ``'Raw Data'``; *raw_values*, the uncorrected counts, in
    ``'Corrected Data'``. Every column is cut to the shortest.
    """
    be_values = list(be_values)
    plot_values = list(plot_values)
    raw_values = list(raw_values) if raw_values is not None \
        else list(plot_values)
    transmission = (list(transmission) if transmission is not None
                    else [1.0] * len(plot_values))
    n = min(len(be_values), len(plot_values), len(raw_values),
            len(transmission))
    be_values = [float(v) for v in be_values[:n]]
    cl = {"Name": sheet_name,
          "B.E.": be_values,
          "Raw Data": [float(v) for v in plot_values[:n]],
          "Corrected Data": [float(v) for v in raw_values[:n]],
          "Transmission": [float(v) for v in transmission[:n]]}
    if experimental_info:
        cl["ExperimentalInfo"] = {
            str(k): "" if v is None else str(v).strip()
            for k, v in experimental_info.items()}
    if be_values:
        cl["Background"] = {"Bkg Y": list(cl["Raw Data"]), "Bkg Type": "",
                            "Bkg Low": float(min(be_values)),
                            "Bkg High": float(max(be_values)),
                            "Bkg Offset Low": 0, "Bkg Offset High": 0}
    return cl


def unique_name(name, taken):
    """*name*, or name-2, name-3… when the project already has it."""
    base, n, out = name, 2, name
    while out in taken:
        out = f"{base}-{n}"
        n += 1
    return out


def project(core_levels: dict, file_path="") -> dict:
    """The full ``window.Data`` structure around *core_levels*."""
    data = {"FilePath": str(file_path),
            "Number of Core levels": len(core_levels),
            "Core levels": dict(core_levels)}
    for i in range(10):
        data[f"Results Table{i}"] = {"Peak": {}}
    return data


def _round_keep_small(value, places=2):
    value = float(value)
    if not math.isfinite(value):
        return value
    a = abs(value)
    if a == 0 or a >= 1:
        return round(value, places)
    return round(value, max(places, 4 - int(math.floor(math.log10(a)))))


def serializable(obj, places=2):
    """KherveFitting's ``convert_to_serializable_and_round``: floats to two
    decimals (five significant figures below 1), arrays to lists."""
    if isinstance(obj, (bool, np.bool_)):
        return bool(obj)
    if isinstance(obj, (float, np.floating)):
        return _round_keep_small(obj, places)
    if isinstance(obj, (int, np.integer)):
        return int(obj)
    if isinstance(obj, np.ndarray):
        return [serializable(v, places) for v in obj.tolist()]
    if isinstance(obj, (list, tuple)):
        return [serializable(v, places) for v in obj]
    if isinstance(obj, dict):
        return {str(k): serializable(v, places) for k, v in obj.items()}
    return obj


def _lossless_keys(cl):
    """Arrays written to HDF5 instead of only the rounded JSON copy."""
    keys = ["B.E.", "Raw Data", "Corrected Data", "Transmission"]
    for prefix in ("TGA_", "EIS_", "XRD_", "TEM_", "AFM_", "DIL_", "BET_",
                   "EELS_"):
        keys += [k for k in cl if k.startswith(prefix)]
    return keys


def _floats(values):
    if values is None:
        return None
    try:
        arr = np.asarray(values, dtype=np.float64)
    except (TypeError, ValueError):
        return None
    return arr if arr.ndim == 1 and arr.size else None


def to_bytes(core_levels: dict, file_path="") -> bytes:
    """The ``.kfit`` file for *core_levels*, as bytes."""
    import h5py
    data = project(core_levels, file_path)
    text = json.dumps(serializable(data))
    buf = io.BytesIO()
    with h5py.File(buf, "w") as f:
        f.attrs["format"] = "kfitting"
        f.attrs["version"] = 1
        f.attrs["application"] = "KherveFitting"
        f.create_dataset("project_json_gz", data=np.frombuffer(
            zlib.compress(text.encode("utf-8"), 6), dtype=np.uint8))
        grp = f.create_group("core_levels")
        for i, (name, cl) in enumerate(core_levels.items()):
            if not isinstance(cl, dict):
                continue
            sg = grp.create_group(f"cl_{i}")
            sg.attrs["name"] = str(name)
            for key in _lossless_keys(cl):
                arr = _floats(cl.get(key))
                if arr is not None:
                    sg.create_dataset(key, data=arr, compression="gzip")
            bkg = cl.get("Background")
            if isinstance(bkg, dict):
                arr = _floats(bkg.get("Bkg Y"))
                if arr is not None:
                    sg.create_dataset("Bkg Y", data=arr, compression="gzip")
    return buf.getvalue()


def write(core_levels: dict, path) -> None:
    from pathlib import Path
    Path(path).write_bytes(to_bytes(core_levels, str(path)))
