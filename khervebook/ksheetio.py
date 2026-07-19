"""Minimal read/write of KherveSheet's native ``.ksheet`` (HDF5) format,
for the sheet-cell round-trip through KherveSheet.

Only the core grid is handled — each sheet's name, size and cell values /
formula texts as a flat row-major string array — matching KherveSheet's
own ``_save_to_ksheet``. Richer metadata (charts, cell formats, merges)
is ignored: enough to hand a sheet to KherveSheet and read the edited
grid back.

Copyright (C) 2026 Gwilherm Kerherve

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.
"""

import json
import re

_REF = re.compile(r"^([A-Za-z]{1,2})(\d{1,4})$")
_DEFAULT_ROWS = 40
_DEFAULT_COLS = 12


def _col_letters(c: int) -> str:
    out = ""
    c += 1
    while c:
        c, rem = divmod(c - 1, 26)
        out = chr(65 + rem) + out
    return out


def _letters_col(letters: str) -> int:
    c = 0
    for ch in letters.upper():
        c = c * 26 + (ord(ch) - 64)
    return c - 1


def _text(v) -> str:
    if isinstance(v, bytes):
        return v.decode("utf-8", "replace")
    return "" if v is None else str(v)


def write_ksheet(source, path):
    """Write a sheet-cell ``source`` (its JSON string or parsed dict) to a
    ``.ksheet`` HDF5 file KherveSheet can open."""
    import h5py
    doc = json.loads(source) if isinstance(source, str) else source
    sheets = doc.get("sheets") or [doc]
    with h5py.File(str(path), "w") as f:
        f.attrs["format"] = "ksheet"
        f.attrs["version"] = 1
        f.attrs["sheet_count"] = len(sheets)
        dt = h5py.string_dtype()
        for i, sh in enumerate(sheets):
            rows = int(sh.get("rows", _DEFAULT_ROWS))
            cols = int(sh.get("cols", _DEFAULT_COLS))
            g = f.create_group(f"sheet_{i}")
            g.attrs["name"] = str(sh.get("name") or f"Sheet{i + 1}")
            g.attrs["rows"] = rows
            g.attrs["cols"] = cols
            flat = [""] * (rows * cols)
            for ref, val in (sh.get("data") or {}).items():
                m = _REF.match(str(ref))
                if not m:
                    continue
                r, c = int(m.group(2)) - 1, _letters_col(m.group(1))
                if 0 <= r < rows and 0 <= c < cols:
                    flat[r * cols + c] = _text(val)
            g.create_dataset("cells", data=flat, dtype=dt)


def read_ksheet(path) -> dict:
    """Read a ``.ksheet`` back into a sheet-cell source dict
    ``{"sheets":[…],"active":…}``."""
    import h5py
    sheets = []
    with h5py.File(str(path), "r") as f:
        if _text(f.attrs.get("format", "")) != "ksheet":
            raise ValueError("not a .ksheet file")
        count = int(f.attrs.get("sheet_count", 0))
        for i in range(count):
            g = f.get(f"sheet_{i}")
            if g is None:
                continue
            rows = int(g.attrs.get("rows", 0))
            cols = int(g.attrs.get("cols", 0))
            name = _text(g.attrs.get("name", f"Sheet{i + 1}"))
            data = {}
            if "cells" in g and cols:
                flat = g["cells"][:]
                for idx, v in enumerate(flat[:rows * cols]):
                    v = _text(v)
                    if not v:
                        continue
                    r, c = divmod(idx, cols)
                    data[f"{_col_letters(c)}{r + 1}"] = v
            sheets.append({"name": name,
                           "rows": max(rows, _DEFAULT_ROWS),
                           "cols": max(cols, _DEFAULT_COLS), "data": data})
    if not sheets:
        sheets = [{"name": "Sheet1", "rows": _DEFAULT_ROWS,
                   "cols": _DEFAULT_COLS, "data": {}}]
    return {"sheets": sheets, "active": sheets[0]["name"]}
