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


# -- launching a sibling app as its own process ----------------------------

def _bundle_exe(app: Path):
    macos = app / "Contents" / "MacOS"
    preferred = macos / app.stem
    if preferred.exists():
        return preferred
    for f in sorted(macos.glob("*")) if macos.is_dir() else []:
        if f.is_file() and os.access(f, os.X_OK):
            return f
    return None


def app_command(path, qt="PySide6"):
    """Launch command (without the document) for a chosen app: a .app
    bundle, an executable, or a source checkout's launcher script run with
    its own virtualenv (else any Python that can import *qt*)."""
    p = Path(path)
    if p.suffix.lower() == ".app" and p.is_dir():
        exe = _bundle_exe(p)
        return [str(exe)] if exe else None
    if p.is_file() and p.suffix.lower() == ".py":
        python = venv_python(p.parent) or python_with(qt)
        return [python, str(p)] if python else None
    if p.is_file():
        return [str(p)]
    return None


def app_install_candidates(app: str):
    """Where an installed Kherve app lives on this platform, in order."""
    out = [Path("/Applications") / f"{app}.app",
           Path.home() / "Applications" / f"{app}.app"]
    if os.environ.get("LOCALAPPDATA"):
        out.append(Path(os.environ["LOCALAPPDATA"]) / "Programs" / app
                   / f"{app}.exe")
    for var in ("ProgramFiles", "ProgramFiles(x86)"):
        if os.environ.get(var):
            out.append(Path(os.environ[var]) / app / f"{app}.exe")
    return out


def find_app(app: str, package: str, script: str, env_var: str = "",
             override: str = "", qt: str = "PySide6"):
    """The command that launches sibling *app*, or None: the user's own
    choice (*override*, from a "Locate…" button), an installed copy, then
    a source checkout's *script*."""
    for candidate in ([override] if override else []) + \
            app_install_candidates(app):
        if candidate and Path(candidate).exists():
            cmd = app_command(candidate, qt)
            if cmd:
                return cmd
    repo = checkout(app, package, env_var)
    if repo is not None and (repo / script).exists():
        return app_command(repo / script, qt)
    return None


def launch_detached(cmd, *args, cwd=None):
    """Start *cmd* + *args* so it outlives KherveBook and never blocks it."""
    import subprocess
    kw = {"cwd": str(cwd) if cwd else None}
    if sys.platform == "win32":
        kw["creationflags"] = (subprocess.DETACHED_PROCESS
                               | subprocess.CREATE_NEW_PROCESS_GROUP)
    else:
        kw["start_new_session"] = True
    return subprocess.Popen(list(cmd) + [str(a) for a in args],
                            stdin=subprocess.DEVNULL,
                            stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL, **kw)
