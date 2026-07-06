"""Package the built app into a setup.exe and a portable .zip.

Assumes the PyInstaller one-folder build already exists at
``dist/KherveBook`` (run ``pyinstaller packaging/KherveBook.spec
--noconfirm`` first). Produces, in ``dist/``:

* ``KherveBook-Setup-<version>.exe`` — an NSIS per-user installer
  (Start Menu + Desktop shortcuts, uninstaller). Needs ``makensis``.
* ``KherveBook-<version>-portable.zip`` — the same folder zipped, for
  people who would rather copy-and-run than install.

    python packaging/build_installer.py

Copyright (C) 2026 Gwilherm Kerherve

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.
"""

import os
import re
import shutil
import subprocess
import sys
import zipfile

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
_DIST = os.path.join(_ROOT, "dist")
_APPDIR = os.path.join(_DIST, "KherveBook")


def _version() -> str:
    """The numeric app version (``0.1.N``), dropping the +sha suffix
    that would be illegal in a filename / VIProductVersion."""
    if _ROOT not in sys.path:
        sys.path.insert(0, _ROOT)
    from khervebook._version import get_version
    return re.match(r"[0-9.]+", get_version()).group(0)


def _find_makensis() -> str | None:
    exe = shutil.which("makensis")
    if exe:
        return exe
    for base in (os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"),
                 os.environ.get("ProgramFiles", r"C:\Program Files")):
        cand = os.path.join(base, "NSIS", "makensis.exe")
        if os.path.isfile(cand):
            return cand
    return None


def build_zip(version: str) -> str:
    """Zip dist/KherveBook so its top-level entry is ``KherveBook/``."""
    out = os.path.join(_DIST, f"KherveBook-{version}-portable.zip")
    if os.path.exists(out):
        os.remove(out)
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED,
                         compresslevel=6) as zf:
        for root, _dirs, files in os.walk(_APPDIR):
            for name in files:
                full = os.path.join(root, name)
                arc = os.path.join("KherveBook",
                                   os.path.relpath(full, _APPDIR))
                zf.write(full, arc)
    return out


def build_installer(version: str) -> str:
    makensis = _find_makensis()
    if makensis is None:
        raise SystemExit(
            "makensis not found — install NSIS (https://nsis.sourceforge.io) "
            "or add it to PATH.")
    out = os.path.join(_DIST, f"KherveBook-Setup-{version}.exe")
    cmd = [
        makensis,
        f"/DAPP_VERSION={version}",
        f"/DSRC_DIR={_APPDIR}",
        f"/DOUT_FILE={out}",
        f"/DLICENSE_FILE={os.path.join(_ROOT, 'LICENSE')}",
        f"/DICON_FILE={os.path.join(_HERE, 'khervebook.ico')}",
        os.path.join(_HERE, "installer.nsi"),
    ]
    subprocess.run(cmd, check=True)
    return out


def main():
    if not os.path.isfile(os.path.join(_APPDIR, "KherveBook.exe")):
        raise SystemExit(
            "dist/KherveBook/KherveBook.exe not found — run "
            "`pyinstaller packaging/KherveBook.spec --noconfirm` first.")
    version = _version()
    print(f"KherveBook {version}")
    zip_path = build_zip(version)
    print("wrote", zip_path,
          f"({os.path.getsize(zip_path) / 1e6:.0f} MB)")
    exe_path = build_installer(version)
    print("wrote", exe_path,
          f"({os.path.getsize(exe_path) / 1e6:.0f} MB)")


if __name__ == "__main__":
    main()
