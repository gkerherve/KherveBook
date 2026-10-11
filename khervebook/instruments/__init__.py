"""Instrument data import — every file KherveFitting can import.

Each reader module in this package ports one of KherveFittingPro's
importers (``libraries/FileMenu/*_Import.py``) without wx and declares
its formats in a module-level ``FORMATS`` list. A reader takes a file
path (or several, for ``multi`` formats) and returns ``{sheet name:
core level}`` — the same core-level dicts KherveFitting builds — which
`kfitwrite` turns into a ``.kfit`` project for a KFit cell. So a file
imported here gives the project KherveFitting itself would make.

`formats()` lists them all, in the order of KherveFitting's Import menu
(technique, then vendor group); `detect()` picks the reader for a
dropped file when its extension (and, for shared extensions such as
``.txt``, its content) says which one it is.

Copyright (C) 2026 Gwilherm Kerherve

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.
"""

import importlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional, Tuple

#: reader modules, in menu order of their first technique
_MODULES = ("kratos", "phi")


@dataclass(frozen=True)
class Format:
    """One importable file type."""

    technique: str               # Import submenu: "XPS", "XRD", "FTIR"…
    label: str                   # menu text, e.g. "VGD (.vgd)"
    exts: Tuple[str, ...]        # lower-case, with the dot
    read: Callable               # path (or list of paths) -> core levels
    group: str = ""              # vendor submenu inside the technique
    #: content check for a shared extension (.txt/.csv/.dat); a format
    #: with one is only auto-detected when it returns True
    sniff: Optional[Callable] = None
    #: the reader takes a list of paths that form one project
    multi: bool = False
    #: needs a Python package that may be missing (shown in errors)
    needs: Tuple[str, ...] = field(default_factory=tuple)

    def matches(self, path) -> bool:
        name = str(path).lower()
        return any(name.endswith(e) for e in self.exts)

    @property
    def filter(self) -> str:
        globs = " ".join(f"*{e}" for e in self.exts)
        return f"{self.label} ({globs});;All files (*)"


_CACHE = None


def formats():
    """Every Format, from every reader module that imports cleanly."""
    global _CACHE
    if _CACHE is None:
        out = []
        for name in _MODULES:
            try:
                mod = importlib.import_module(f"{__name__}.{name}")
            except Exception:
                continue
            out.extend(getattr(mod, "FORMATS", []))
        _CACHE = in_menu_order(out)
    return _CACHE


def in_menu_order(fmts):
    """XPS first (as in KherveFitting's Import menu), the other
    techniques alphabetically; formats keep their order within one."""
    return sorted(fmts, key=lambda f: (f.technique != "XPS",
                                       f.technique.lower()))


def techniques():
    seen = []
    for f in formats():
        if f.technique not in seen:
            seen.append(f.technique)
    return seen


def detect(path):
    """The one Format a dropped file belongs to, or None when the file is
    not an instrument file (or could be several, e.g. a plain .csv)."""
    candidates = [f for f in formats() if f.matches(path)]
    sniffed = []
    for f in candidates:
        if f.sniff is None:
            continue
        try:
            if f.sniff(path):
                sniffed.append(f)
        except Exception:
            pass
    if len(sniffed) == 1:
        return sniffed[0]
    if sniffed:
        return None
    plain = [f for f in candidates if f.sniff is None]
    return plain[0] if len(plain) == 1 else None


class ImportFailed(Exception):
    """A reader could not make sense of a file (message is user-facing)."""


def read(fmt: Format, paths) -> dict:
    """Run *fmt*'s reader; {sheet: core level}, never empty."""
    paths = [str(p) for p in (paths if isinstance(paths, (list, tuple))
                              else [paths])]
    try:
        levels = fmt.read(paths if fmt.multi else paths[0])
    except ImportError as exc:
        need = ", ".join(fmt.needs) or str(exc)
        raise ImportFailed(f"{fmt.label} needs the Python package {need} "
                           f"(pip install {need}).") from exc
    except ImportFailed:
        raise
    except Exception as exc:
        raise ImportFailed(f"{Path(paths[0]).name} could not be read as "
                           f"{fmt.label}: {exc}") from exc
    if not levels:
        raise ImportFailed(f"No spectra found in {Path(paths[0]).name}.")
    return levels


def to_kfit(fmt: Format, paths) -> bytes:
    """Read *paths* with *fmt* and return the ``.kfit`` project bytes."""
    from . import kfitwrite
    levels = read(fmt, paths)
    first = Path(paths[0] if isinstance(paths, (list, tuple)) else paths)
    return kfitwrite.to_bytes(levels, str(first.with_suffix(".kfit")))
