"""Readable previews for structured attachment formats.

A File cell shows a snippet of each attached file. Plain text and images
are handled in ``filecell`` directly; this module summarises the binary
scientific formats in the Kherve family so they are not just "binary,
kept as-is":

* ``.xlsx`` / ``.xlsm`` — Excel workbook (openpyxl): sheet list + a small
  cell grid from the first sheet.
* ``.ksheet``           — KherveSheet workbook (HDF5): sheet names + sizes.
* ``.kfit``             — KherveFitting project (HDF5): core-level names.

Each reader is best-effort and optional-dependency-safe: a missing
library or an unexpected layout simply returns ``None`` and the cell
falls back to the generic "binary file — kept as-is" note.

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

#: preview budget — keep the snippet compact in the cell.
_MAX_NAMES = 10
_MAX_ROWS = 5
_MAX_COLS = 6
_CELL_W = 12


def _text(v) -> str:
    if isinstance(v, bytes):
        return v.decode("utf-8", "replace")
    return "" if v is None else str(v)


def summarize(name: str, data: bytes):
    """Return a short multi-line text summary for a structured file, or
    None if this module can't preview it (caller falls back to a note)."""
    ext = Path(name).suffix.lower()
    try:
        if ext in (".xlsx", ".xlsm"):
            return _xlsx_summary(data)
        if ext == ".ksheet":
            return _hdf5_summary(data)
        if ext == ".kfit":
            return _hdf5_summary(data)
    except Exception:
        return None
    return None


# -- Excel -----------------------------------------------------------------

def _xlsx_summary(data: bytes):
    from openpyxl import load_workbook
    wb = load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    try:
        names = wb.sheetnames
        head = (f"Excel workbook · {len(names)} "
                f"sheet{'s' if len(names) != 1 else ''}: "
                + ", ".join(names[:_MAX_NAMES])
                + (" …" if len(names) > _MAX_NAMES else ""))
        ws = wb[wb.sheetnames[0]]
        rows = []
        for r, row in enumerate(ws.iter_rows(values_only=True)):
            if r >= _MAX_ROWS:
                break
            cells = ["" if v is None else str(v) for v in row[:_MAX_COLS]]
            rows.append("  ".join(c[:_CELL_W].ljust(_CELL_W) for c in cells))
        dims = getattr(ws, "calculate_dimension", lambda: "")()
        grid = (f"\n[{wb.sheetnames[0]}] {dims}\n" + "\n".join(rows).rstrip()
                if rows else "")
        return head + grid
    finally:
        wb.close()


# -- HDF5 (KherveSheet .ksheet and KherveFitting .kfit) --------------------

def _hdf5_summary(data: bytes):
    import h5py
    with h5py.File(io.BytesIO(data), "r") as f:
        fmt = _text(f.attrs.get("format", "")).lower()
        if fmt == "ksheet":
            return _ksheet_summary(f)
        if fmt == "kfitting":
            return _kfit_summary(f)
    return None


def _ksheet_summary(f):
    count = int(f.attrs.get("sheet_count", 0))
    parts = []
    for si in range(count):
        g = f.get(f"sheet_{si}")
        if g is None:
            continue
        nm = _text(g.attrs.get("name", f"Sheet {si + 1}"))
        rows = int(g.attrs.get("rows", 0))
        cols = int(g.attrs.get("cols", 0))
        charts = sum(1 for k in g if str(k).startswith("chart_"))
        tag = f"{nm} ({rows}×{cols}"
        tag += f", {charts} chart{'s' if charts != 1 else ''})" if charts \
            else ")"
        parts.append(tag)
    head = (f"KherveSheet workbook · {count} "
            f"sheet{'s' if count != 1 else ''}")
    body = "\n".join(parts[:_MAX_NAMES])
    if len(parts) > _MAX_NAMES:
        body += f"\n… (+{len(parts) - _MAX_NAMES} more)"
    return head + ("\n" + body if body else "")


def _kfit_summary(f):
    cl = f.get("core_levels")
    names = []
    if cl is not None:
        def _order(s):
            parts = str(s).split("_")
            return (0, int(parts[1])) if parts[-1].isdigit() else (1, str(s))
        for key in sorted(cl.keys(), key=_order):
            nm = _text(cl[key].attrs.get("name", key))
            names.append(nm)
    sample = _kfit_sample_name(f)
    head = f"KherveFitting project · {len(names)} core level" \
           f"{'s' if len(names) != 1 else ''}"
    if sample:
        head += f"  ·  {sample}"
    shown = ", ".join(names[:_MAX_NAMES])
    if len(names) > _MAX_NAMES:
        shown += f", … (+{len(names) - _MAX_NAMES} more)"
    return head + ("\n" + shown if shown else "")


def _kfit_sample_name(f):
    """Best-effort sample/file name from the project JSON (zlib blob)."""
    ds = f.get("project_json_gz")
    if ds is None:
        return ""
    try:
        raw = bytes(ds[()])
        js = json.loads(zlib.decompress(raw).decode("utf-8"))
    except Exception:
        return ""
    for key in ("SampleNames", "FilePath"):
        val = js.get(key)
        if isinstance(val, list) and val:
            return Path(_text(val[0])).name
        if isinstance(val, str) and val:
            return Path(val).name
    return ""
