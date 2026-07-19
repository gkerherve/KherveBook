"""Round-trip a cell's content through a sibling Kherve desktop app.

Opens the cell's content in a sibling app (KhervePaint for drawings,
KhervePY for code, KherveSheet for spreadsheets) and reloads it back into
the cell whenever that app saves — by polling the shared file's
modification time (a plain ``QFileSystemWatcher`` misses the atomic
save-replace many editors do on Windows).

Each cell owns an ``AppBridge``: it supplies a *writer* that serialises
the cell to the app's native file, and a *reload* callback that reads
that file back after a save.

Copyright (C) 2026 Gwilherm Kerherve

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.
"""

import os
import subprocess
import sys
import tempfile
from pathlib import Path

from PyQt5.QtCore import QTimer
from PyQt5.QtWidgets import QMessageBox


class AppBridge:
    """Launch a sibling app on a temp file and reload the cell on save."""

    def __init__(self, cell, app_name: str, module: str, ext: str, reload_fn):
        self._cell = cell            # a QWidget, for QTimer parent + dialogs
        self._app = app_name         # e.g. "KherveSheet"
        self._module = module        # e.g. "khervesheet"
        self._ext = ext              # e.g. ".ksheet"
        self._reload = reload_fn     # callable(path) -> load the saved file
        self._timer = None
        self._tmp = None
        self._proc = None
        self._mtime = 0.0

    def _repo(self) -> Path:
        # .../Python/KherveBook/khervebook/appbridge.py -> .../Python/<app>
        return Path(__file__).resolve().parents[2] / self._app

    def available(self) -> bool:
        return (self._repo() / self._module / "__main__.py").exists()

    def open(self, writer) -> bool:
        """Serialise the cell via *writer(path)*, launch the app on it, and
        start polling for saves."""
        repo = self._repo()
        if not self.available():
            QMessageBox.information(
                self._cell, self._app,
                f"{self._app} was not found next to KherveBook "
                f"(looked in {repo}).")
            return False
        tmp = (Path(tempfile.gettempdir())
               / f"khervebook_{self._module}_{id(self._cell)}{self._ext}")
        try:
            writer(tmp)
        except Exception as exc:
            QMessageBox.warning(self._cell, self._app,
                                f"Could not prepare the file:\n{exc}")
            return False
        venv = repo / ".venv" / (
            "Scripts/python.exe" if os.name == "nt" else "bin/python")
        python = str(venv) if venv.exists() else sys.executable
        try:
            self._proc = subprocess.Popen(
                [python, "-m", self._module, str(tmp)], cwd=str(repo))
        except Exception as exc:
            QMessageBox.warning(self._cell, self._app,
                                f"Could not launch {self._app}:\n{exc}")
            return False
        self._tmp = tmp
        try:
            self._mtime = tmp.stat().st_mtime
        except OSError:
            self._mtime = 0.0
        if self._timer is None:
            self._timer = QTimer(self._cell)
            self._timer.timeout.connect(self._poll)
        self._timer.start(700)
        QMessageBox.information(
            self._cell, f"Editing in {self._app}",
            f"This is opening in {self._app}.\n\nEdit it there, then Save "
            f"(Ctrl+S) — KherveBook reloads it automatically.\n\nIf it "
            f"doesn't open on its own, use File ▸ Open on:\n{tmp}")
        return True

    def _poll(self):
        tmp = self._tmp
        if tmp is None or not tmp.exists():
            return
        try:
            mtime = tmp.stat().st_mtime
        except OSError:
            return
        if mtime > self._mtime:
            self._mtime = mtime
            try:
                self._reload(str(tmp))
            except Exception:
                pass                 # a half-written save; next tick retries
        if self._proc is not None and self._proc.poll() is not None:
            self._timer.stop()       # the app has closed
