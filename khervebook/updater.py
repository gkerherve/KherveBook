"""Self-update from GitHub Releases.

Releases live at github.com/gkerherve/KherveBook/releases, so that is the
authoritative source: GitHub already publishes a JSON manifest for us (the
`/releases/latest` API) giving the tag name, the release notes and the exact
asset URLs — nothing has to be hosted or kept in sync by hand. The khervetools
website reads the same releases, so the two can never disagree.

    tag_name: "v0.1.137"
    assets:   KherveBook-Setup-0.1.137.exe, KherveBook-Setup.exe,
              KherveBook-0.1.137-portable.zip

An optional JSON manifest on khervetools.com is tried if GitHub cannot be
reached, so an update could be pushed from elsewhere if it ever had to be:

    {"version": "0.1.140", "windows": "https://.../KherveBook-Setup.exe"}

Applying the update runs the release's own NSIS installer in silent mode
(``/S``), so there is no wizard to click through. NSIS reads the recorded
install directory back from ``HKCU\\Software\\KherveBook\\InstallDir``, so the
upgrade lands exactly where the app already lives and keeps the Start-menu
entry, the desktop shortcut and the uninstall entry correct — which a plain
file copy would not. Because Windows will not let a running exe replace its own
files, the swap is handed to a throwaway PowerShell helper that waits for this
process to exit, runs the installer, reopens the app and deletes itself.

Copyright (C) 2026 Gwilherm Kerherve

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.
"""

import html
import json
import os
import re
import subprocess
import sys
import tempfile
import urllib.request
from pathlib import Path

from PyQt5.QtCore import QSettings, Qt, QThread, QUrl, pyqtSignal
from PyQt5.QtGui import QDesktopServices
from PyQt5.QtWidgets import (QCheckBox, QDialog, QHBoxLayout, QLabel,
                             QMessageBox, QProgressDialog, QPushButton,
                             QTextBrowser, QVBoxLayout)

from . import APP_NAME, __version__

GITHUB_REPO = "gkerherve/KherveBook"
GITHUB_LATEST_API = (
    f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest")
GITHUB_RELEASES_URL = f"https://github.com/{GITHUB_REPO}/releases"

#: Optional fallback manifest, only consulted when GitHub is unreachable.
UPDATE_MANIFEST_URL = "https://khervetools.com/khervebook_latest.json"
KHERVETOOLS_URL = "https://khervetools.com/tools/khervebook"

_SETTINGS = ("Kherve", "KherveBook")
_KEY_STARTUP = "update/check_on_startup"
_KEY_SKIP = "update/skip_version"

_TIMEOUT = 8            # seconds for the version check
_USER_AGENT = f"KherveBook/{__version__}"


# ---------------------------------------------------------------------------
#  Versions
# ---------------------------------------------------------------------------
def parse_version(text) -> tuple:
    """``"v0.1.137+a6cf9dd"`` -> ``(0, 1, 137)``; ``()`` when unparseable.

    The ``+sha`` local part is dropped: it identifies the build, not its
    ordering, and comparing it would make every commit look newer.
    """
    core = str(text or "").strip().lstrip("vV").split("+")[0]
    return tuple(int(n) for n in re.findall(r"\d+", core))


def is_newer(candidate, current) -> bool:
    """True when *candidate* orders strictly after *current*."""
    a, b = parse_version(candidate), parse_version(current)
    if not a or not b:
        return False
    width = max(len(a), len(b))
    return a + (0,) * (width - len(a)) > b + (0,) * (width - len(b))


# ---------------------------------------------------------------------------
#  Where this copy lives
# ---------------------------------------------------------------------------
def _is_frozen() -> bool:
    """True for the PyInstaller build — from source there is nothing an
    installer could sensibly replace."""
    return bool(getattr(sys, "frozen", False))


def _registered_install_dir() -> str:
    """The folder the NSIS installer last installed into, per the registry."""
    key = QSettings(r"HKEY_CURRENT_USER\Software\KherveBook",
                    QSettings.NativeFormat)
    return str(key.value("InstallDir") or "")


def _same_dir(a, b) -> bool:
    if not a or not b:
        return False
    return (os.path.normcase(os.path.normpath(a))
            == os.path.normcase(os.path.normpath(b)))


def app_exe() -> str:
    """The exe to relaunch after updating (a test override, or ourselves).

    ``KHERVEBOOK_UPDATE_TEST_EXE`` points at an installed KherveBook.exe so the
    real silent update can be exercised from a source checkout, where
    ``sys.executable`` is python.exe and there would be nothing to reopen.
    """
    override = os.environ.get("KHERVEBOOK_UPDATE_TEST_EXE", "")
    if override and os.path.exists(override):
        return override
    return sys.executable


def can_self_update() -> bool:
    """True only for an *installed* Windows copy, which is the one case where
    running the installer silently updates this very app.

    A portable unzip has no registry entry, so a silent install would quietly
    upgrade some other (or no) copy and then reopen the wrong exe — better to
    hand those users the download.
    """
    if os.name != "nt":
        return False
    if not (_is_frozen() or os.environ.get("KHERVEBOOK_UPDATE_TEST_EXE")):
        return False
    return _same_dir(_registered_install_dir(), os.path.dirname(app_exe()))


# ---------------------------------------------------------------------------
#  Release notes
# ---------------------------------------------------------------------------
def notes_to_html(body: str) -> str:
    """Render GitHub's markdown release notes as the What's New panel.

    Only the handful of constructs release notes actually use are handled —
    headings, bullets, paragraphs, bold and code. A horizontal rule ends the
    notes: what follows on the release page is download-and-run boilerplate,
    which is page furniture and obsolete now the app updates itself.
    """
    out, bullets = [], False

    def close_list():
        nonlocal bullets
        if bullets:
            out.append("</ul>")
            bullets = False

    def inline(text):
        text = html.escape(text)
        text = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", text)
        text = re.sub(r"`(.+?)`", r"<code>\1</code>", text)
        return text

    for raw in (body or "").replace("\r\n", "\n").split("\n"):
        line = raw.strip()
        if len(line) >= 3 and set(line) <= set("-*_"):
            break
        if not line:
            close_list()
            continue
        if line.startswith("#"):
            close_list()
            out.append(f"<h3>{inline(line.lstrip('#').strip())}</h3>")
            continue
        if line.startswith(("- ", "* ", "+ ")):
            if not bullets:
                out.append("<ul>")
                bullets = True
            out.append(f"<li>{inline(line[2:].strip())}</li>")
            continue
        if bullets:
            # A wrapped continuation line — fold it back onto its bullet.
            out[-1] = out[-1][:-len("</li>")] + " " + inline(line) + "</li>"
            continue
        out.append(f"<p>{inline(line)}</p>")

    close_list()
    return "\n".join(out)


# ---------------------------------------------------------------------------
#  Version check (background)
# ---------------------------------------------------------------------------
def _get(url, timeout=_TIMEOUT, accept=None):
    headers = {"User-Agent": _USER_AGENT}
    if accept:
        headers["Accept"] = accept
    request = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read()


#: Asset extensions to offer, best first, per platform.
_ASSET_EXTENSIONS = {"nt": (".exe", ".zip")}


def _pick_asset(release: dict) -> str:
    """Best installer URL for this platform, or the release page when the
    release carries nothing we recognise."""
    assets = [a for a in release.get("assets", [])
              if a.get("browser_download_url") and a.get("name")]
    for ext in _ASSET_EXTENSIONS.get(os.name, ()):
        matches = [a for a in assets if a["name"].lower().endswith(ext)]
        if matches:
            # Prefer the version-stamped installer over the stable
            # "KherveBook-Setup.exe" alias so the saved file name stays
            # meaningful, and prefer a setup over a portable zip.
            matches.sort(key=lambda a: (not re.search(r"\d+\.\d+", a["name"]),
                                        a["name"]))
            return matches[0]["browser_download_url"]
    return release.get("html_url") or GITHUB_RELEASES_URL


def check_latest() -> dict:
    """Look up the newest release. Returns a dict with either ``error`` or
    ``version`` / ``url`` / ``notes`` / ``page`` keys."""
    try:
        data = json.loads(_get(GITHUB_LATEST_API,
                               accept="application/vnd.github+json"))
        version = str(data.get("tag_name") or data.get("name") or "")
        if parse_version(version):
            return {"version": version.lstrip("vV"),
                    "url": _pick_asset(data),
                    "notes": notes_to_html(data.get("body") or ""),
                    "page": data.get("html_url") or GITHUB_RELEASES_URL}
    except Exception as exc:      # offline, rate-limited, no release yet
        github_error = exc
    else:
        github_error = ValueError("the latest release has no usable tag")

    try:
        data = json.loads(_get(UPDATE_MANIFEST_URL))
        return {"version": str(data.get("version") or ""),
                "url": data.get("windows") or data.get("url")
                or KHERVETOOLS_URL,
                "notes": notes_to_html(data.get("notes") or ""),
                "page": KHERVETOOLS_URL}
    except Exception:
        return {"error": str(github_error)}


class _CheckWorker(QThread):
    """The version lookup, off the GUI thread so a slow or dead network
    never freezes the window."""
    done = pyqtSignal(dict)

    def run(self):
        self.done.emit(check_latest())


class _DownloadWorker(QThread):
    """Stream the installer to a temp file, reporting percent complete."""
    progress = pyqtSignal(int)
    done = pyqtSignal(str, str)     # path, error ("" on success)

    def __init__(self, url, dest, parent=None):
        super().__init__(parent)
        self._url = url
        self._dest = dest
        self.cancelled = False

    def run(self):
        try:
            request = urllib.request.Request(
                self._url, headers={"User-Agent": _USER_AGENT})
            with urllib.request.urlopen(request, timeout=30) as response:
                total = int(response.headers.get("content-length") or 0)
                got = 0
                with open(self._dest, "wb") as handle:
                    while not self.cancelled:
                        chunk = response.read(1 << 20)
                        if not chunk:
                            break
                        handle.write(chunk)
                        got += len(chunk)
                        if total:
                            self.progress.emit(min(100, got * 100 // total))
            if self.cancelled:
                raise InterruptedError("cancelled")
            # A truncated installer would half-replace the app, so refuse
            # anything that did not arrive whole.
            if total and got != total:
                raise IOError(f"incomplete download ({got} of {total} bytes)")
            self.done.emit(self._dest, "")
        except Exception as exc:
            try:
                os.remove(self._dest)   # never leave a partial installer behind
            except OSError:
                pass
            self.done.emit("", str(exc))


# ---------------------------------------------------------------------------
#  Applying the update
# ---------------------------------------------------------------------------
def _ps_quote(value) -> str:
    """Quote a path for a PowerShell single-quoted literal."""
    return "'" + str(value).replace("'", "''") + "'"


def spawn_windows_updater(installer_path):
    """Write and launch the hidden helper that performs the swap.

    PowerShell rather than a .cmd: the helper runs without a console, and in
    that state cmd's ``tasklist | findstr`` pipe deadlocks. ``Wait-Process`` is
    a single primitive with no pipe and blocks properly until the app exits.
    """
    exe = app_exe()
    script = f"""$ErrorActionPreference = 'SilentlyContinue'
# Wait for KherveBook to close so Windows releases its files.
try {{ Wait-Process -Id {os.getpid()} -Timeout 180 -ErrorAction Stop }} catch {{ }}
# Silent upgrade: no wizard. NSIS reuses the recorded install directory.
try {{
    Start-Process -FilePath {_ps_quote(installer_path)} -ArgumentList '/S' -Wait
}} catch {{ }}
# Reopen KherveBook — the new build if the update took, the old one if not.
Start-Process -FilePath {_ps_quote(exe)} -WorkingDirectory {_ps_quote(os.path.dirname(exe))}
Remove-Item -LiteralPath {_ps_quote(installer_path)} -Force -ErrorAction SilentlyContinue
Remove-Item -LiteralPath $MyInvocation.MyCommand.Path -Force -ErrorAction SilentlyContinue
"""
    helper = os.path.join(tempfile.gettempdir(), "KherveBook_update.ps1")
    Path(helper).write_text(script, encoding="utf-8")
    subprocess.Popen(
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass",
         "-WindowStyle", "Hidden", "-File", helper],
        close_fds=True,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))


# ---------------------------------------------------------------------------
#  The What's New / Update dialog
# ---------------------------------------------------------------------------
class UpdateDialog(QDialog):
    """"Version N is available", the release notes, and the two choices."""

    def __init__(self, parent, version, notes, prompt):
        super().__init__(parent)
        self.setWindowTitle("Update Available")
        self.resize(620, 520)

        layout = QVBoxLayout(self)
        header = QLabel(f"<h2 style='margin:0'>{APP_NAME} {version} "
                        f"is available</h2>"
                        f"<p style='color:gray;margin-top:2px'>"
                        f"You have {__version__}.</p>")
        header.setTextFormat(Qt.RichText)
        layout.addWidget(header)

        view = QTextBrowser(self)
        view.setOpenExternalLinks(True)
        view.setHtml(notes or "<p><i>No release notes were published.</i></p>")
        layout.addWidget(view, 1)

        message = QLabel(prompt)
        message.setWordWrap(True)
        layout.addWidget(message)

        self.startup_box = QCheckBox(
            f"Check for updates when {APP_NAME} starts")
        self.startup_box.setChecked(startup_check_enabled())
        layout.addWidget(self.startup_box)

        buttons = QHBoxLayout()
        buttons.addStretch(1)
        skip = QPushButton("Skip This Version", self)
        later = QPushButton("Not Now", self)
        now = QPushButton("Update Now", self)
        now.setDefault(True)
        for button in (skip, later, now):
            buttons.addWidget(button)
        layout.addLayout(buttons)

        self.skipped = False
        skip.clicked.connect(self._skip)
        later.clicked.connect(self.reject)
        now.clicked.connect(self.accept)

    def _skip(self):
        self.skipped = True
        self.reject()

    def done(self, result):
        set_startup_check(self.startup_box.isChecked())
        super().done(result)


# ---------------------------------------------------------------------------
#  Settings
# ---------------------------------------------------------------------------
def startup_check_enabled() -> bool:
    value = QSettings(*_SETTINGS).value(_KEY_STARTUP, True)
    return value not in (False, "false", "False", 0, "0")


def set_startup_check(enabled: bool):
    QSettings(*_SETTINGS).setValue(_KEY_STARTUP, bool(enabled))


def _skipped_version() -> str:
    return str(QSettings(*_SETTINGS).value(_KEY_SKIP, "") or "")


def _set_skipped_version(version: str):
    QSettings(*_SETTINGS).setValue(_KEY_SKIP, version)


# ---------------------------------------------------------------------------
#  The controller the window talks to
# ---------------------------------------------------------------------------
class Updater:
    """Drives a check for *window*.

    ``check(silent=True)`` is the startup check: it speaks up only when there
    is something new. ``check(silent=False)`` is Help > Check for Updates,
    which also reports being up to date and connection failures.
    """

    def __init__(self, window):
        self.window = window
        self._worker = None
        self._download = None
        self._progress = None

    # -- check ---------------------------------------------------------
    def check(self, silent=True):
        if self._worker is not None and self._worker.isRunning():
            return
        self._silent = silent
        self._worker = _CheckWorker(self.window)
        self._worker.done.connect(self._checked)
        self._worker.start()

    def _checked(self, result):
        error = result.get("error")
        version = result.get("version", "")
        if error or not version:
            if not self._silent:
                QMessageBox.warning(
                    self.window, "Check for Updates",
                    "Could not check for updates.\n\nPlease check your "
                    f"internet connection and try again.\n\n{error or ''}")
            return

        if not is_newer(version, __version__):
            if not self._silent:
                QMessageBox.information(
                    self.window, "No Update Available",
                    f"You are running the latest version "
                    f"(v{__version__}).")
            return

        if self._silent and version == _skipped_version():
            return

        self._offer(result)

    # -- offer ---------------------------------------------------------
    def _offer(self, result):
        version, url = result["version"], result.get("url") or ""
        auto = can_self_update() and url.lower().endswith(".exe")
        if auto:
            prompt = (f"Update now? {APP_NAME} will download it, close, update "
                      f"itself and reopen — there is nothing to click "
                      f"through.")
        elif os.name == "nt" and not _is_frozen():
            # From source the installer would update an installed copy, not
            # this checkout — say so rather than appear to do nothing.
            prompt = (f"This copy runs from source, so it cannot update "
                      f"itself. Download the installer instead?")
        else:
            prompt = "Download it now?"

        dialog = UpdateDialog(self.window, version, result.get("notes", ""),
                              prompt)
        accepted = dialog.exec_() == QDialog.Accepted
        if dialog.skipped:
            _set_skipped_version(version)
            return
        if not accepted:
            return

        if auto:
            self._start_download(url)
        else:
            QDesktopServices.openUrl(QUrl(url or result.get("page")
                                          or GITHUB_RELEASES_URL))

    # -- download ------------------------------------------------------
    def _start_download(self, url):
        name = os.path.basename(url.split("?")[0]) or "KherveBook-Setup.exe"
        dest = os.path.join(tempfile.gettempdir(), name)

        self._progress = QProgressDialog(f"Downloading {name}…", "Cancel",
                                         0, 100, self.window)
        self._progress.setWindowTitle(f"Updating {APP_NAME}")
        self._progress.setWindowModality(Qt.ApplicationModal)
        self._progress.setAutoClose(False)
        self._progress.setValue(0)

        self._download = _DownloadWorker(url, dest, self.window)
        self._download.progress.connect(self._progress.setValue)
        self._download.done.connect(self._downloaded)
        self._progress.canceled.connect(self._cancel_download)
        self._download.start()

    def _cancel_download(self):
        if self._download is not None:
            self._download.cancelled = True

    def _downloaded(self, path, error):
        if self._progress is not None:
            self._progress.close()
            self._progress = None
        cancelled = self._download is not None and self._download.cancelled
        self._download = None
        if cancelled:
            return
        if error:
            QMessageBox.critical(
                self.window, "Update",
                f"The update could not be downloaded:\n{error}\n\n"
                f"You can download it manually from:\n{KHERVETOOLS_URL}")
            return
        try:
            spawn_windows_updater(path)
        except Exception as exc:
            QMessageBox.critical(
                self.window, "Update",
                f"The update could not be started:\n{exc}\n\n"
                f"The installer was saved to:\n{path}")
            return
        # Close KherveBook so the installer can replace its files; the helper
        # reopens it once the new build is in place.
        self.window.close()
