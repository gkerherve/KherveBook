"""Read the sibling KhervePaint app's reusable-object library.

KhervePaint saves reusable objects as standalone ``.svg`` files in a
per-user folder (``objects_dir()`` in its ``library.py``). KherveBook
reads that *same* folder live, so any object you save in KhervePaint
shows up here — the two stay linked without importing across projects.

Copyright (C) 2026 Gwilherm Kerherve

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.
"""

import os
import re
from pathlib import Path

from PyQt5.QtCore import QStandardPaths


def objects_dir() -> Path:
    """The folder KhervePaint stores its library objects in.

    Mirrors KhervePaint's ``library.objects_dir()``: the
    ``KHERVEPAINT_OBJECTS_DIR`` override wins; otherwise the app-data
    location for the *KhervePaint* application (not KherveBook)."""
    override = os.environ.get("KHERVEPAINT_OBJECTS_DIR")
    if override:
        return Path(override)
    if os.name == "nt":
        appdata = os.environ.get("APPDATA")
        if appdata:
            return Path(appdata) / "KhervePaint" / "objects"
    base = QStandardPaths.writableLocation(QStandardPaths.AppDataLocation)
    if base:
        # Swap our own app-data leaf ("KherveBook") for KhervePaint's.
        return Path(base).with_name("KhervePaint") / "objects"
    return Path.home() / ".khervepaint" / "objects"


def list_objects():
    """[(label, path), …] for every object anywhere under the library,
    sorted; nested folders show as ``Folder / name``. Empty if the
    library folder is missing (KhervePaint never ran / no objects yet)."""
    root = objects_dir()
    if not root.is_dir():
        return []
    out = []
    for p in sorted(root.rglob("*.svg"), key=lambda q: str(q).lower()):
        rel = p.parent.relative_to(root)
        prefix = "" if str(rel) == "." else " / ".join(rel.parts) + " / "
        out.append((prefix + p.stem, p))
    return out


def object_inner_svg(path) -> str:
    """The drawable inner XML of an object SVG (between <svg…> and </svg>),
    ready to be wrapped in a <g> and appended to another SVG."""
    try:
        text = Path(path).read_text(encoding="utf-8")
    except OSError:
        return ""
    m = re.search(r"<svg\b[^>]*>(.*)</svg>", text, re.S | re.I)
    return (m.group(1).strip() if m else "").strip()
