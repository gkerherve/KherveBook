"""Find the sibling Kherve apps KherveBook embeds or hands work to.

Two kinds of neighbour:

* **Embedded packages** (KherveMol): a PyQt5 package imported into this
  process so its widgets sit inside a cell. `import_package` puts the
  package's checkout on ``sys.path`` — from an environment variable, the
  PyInstaller bundle, or a sibling checkout — and returns the module, or
  None so the cell can say what is missing instead of crashing.
* **External apps** (KherveTeX): a separate program, never imported —
  KherveTeX is PySide6, which cannot share a process with PyQt5. The
  `find_*` helpers return the command line that launches it.

Copyright (C) 2026 Gwilherm Kerherve

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.
"""

import importlib
import os
import shutil
import sys
from pathlib import Path

#: .../Python/KherveBook — this checkout's root.
_REPO = Path(__file__).resolve().parents[1]


def _search_roots():
    """Folders that may hold sibling checkouts, most specific first."""
    return [_REPO.parent,                              # beside KherveBook
            Path.home() / "Documents" / "PycharmProjects",
            Path.home() / "PycharmProjects"]


def checkout(repo_name: str, package: str, env_var: str = ""):
    """The root of a sibling source checkout holding *package*, or None.

    *env_var*, when set, names the checkout (or the package folder itself)
    and wins over the guesses.
    """
    candidates = []
    if env_var and os.environ.get(env_var):
        p = Path(os.environ[env_var]).expanduser()
        candidates.append(p.parent if p.name == package else p)
    frozen = getattr(sys, "_MEIPASS", None)
    if frozen:
        candidates.append(Path(frozen))
    candidates += [root / repo_name for root in _search_roots()]
    for c in candidates:
        if (c / package / "__init__.py").exists():
            return c
    return None


def import_package(package: str, repo_name: str, env_var: str = ""):
    """Import an embedded sibling package, or return None when it is absent
    or fails to import (a broken sibling must not take KherveBook down)."""
    try:
        return importlib.import_module(package)
    except ImportError:
        pass
    root = checkout(repo_name, package, env_var)
    if root is None:
        return None
    # Appended, not prepended: the sibling's top-level names (its tests/,
    # packaging/) must never shadow KherveBook's own.
    if str(root) not in sys.path:
        sys.path.append(str(root))
    try:
        return importlib.import_module(package)
    except Exception:
        return None


def venv_python(repo: Path):
    """The checkout's own virtualenv interpreter, if it has one."""
    for rel in ("Scripts/python.exe", "bin/python"):
        p = Path(repo) / ".venv" / rel
        if p.exists():
            return str(p)
    return None


def python_with(module: str):
    """A Python interpreter that can import *module* (for a source-checkout
    app with no virtualenv of its own), or None."""
    import subprocess
    seen = []
    for exe in (sys.executable if not getattr(sys, "frozen", False) else None,
                shutil.which("python3"), shutil.which("python"),
                shutil.which("py")):
        if not exe or exe in seen:
            continue
        seen.append(exe)
        try:
            ok = subprocess.run([exe, "-c", f"import {module}"],
                                capture_output=True, timeout=20).returncode
        except Exception:
            continue
        if ok == 0:
            return exe
    return None
