"""Application entry: QApplication setup, crash log, Fusion style.

Copyright (C) 2026 Gwilherm Kerherve

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.
"""

import faulthandler
import sys
import traceback
import tempfile
from pathlib import Path

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QApplication

CRASH_LOG = Path(tempfile.gettempdir()) / "khervebook_crash.log"

#: How many distinct errors to raise a dialog for. A method that throws on
#: every repaint would otherwise put a modal box in front of the user
#: dozens of times a second; the log still records every one.
_MAX_DIALOGS = 5


def install_excepthook(log=None, report=True):
    """Turn an unhandled exception into a report instead of a dead process.

    PyQt5 calls ``qFatal()`` — and so ``abort()`` — when a Python
    exception escapes a slot, which kills KherveBook outright: no
    traceback, no chance to save, and nothing in the crash log, since
    faulthandler only records *native* faults. An installed excepthook
    takes precedence over that abort, so one bad signal handler costs the
    user an error message rather than the notebook they were writing.
    """
    seen, shown = set(), []

    def hook(exc_type, exc, tb):
        if issubclass(exc_type, KeyboardInterrupt):
            sys.__excepthook__(exc_type, exc, tb)
            return
        text = "".join(traceback.format_exception(exc_type, exc, tb))
        for stream in (log, sys.stderr):
            try:
                stream.write(text + "\n")
                stream.flush()
            except Exception:
                pass                    # a closed console must not re-raise
        # Dedupe on where it was raised, so a repeating fault is reported
        # once however often it fires.
        key = (exc_type.__name__, str(exc),
               tb.tb_frame.f_code.co_filename if tb else "")
        if not report or key in seen or len(shown) >= _MAX_DIALOGS:
            seen.add(key)
            return
        seen.add(key)
        shown.append(key)
        _show(text)

    sys.excepthook = hook
    return hook


def _show(text: str):
    """Report *text* in a dialog, if there is a live GUI to show it in."""
    from PyQt5.QtWidgets import QMessageBox

    if QApplication.instance() is None:
        return
    try:
        box = QMessageBox()
        box.setIcon(QMessageBox.Warning)
        box.setWindowTitle("KherveBook — something went wrong")
        box.setText("KherveBook hit an error and skipped that action.\n\n"
                    "Your notebook is still open — save it, then send this "
                    "report so it can be fixed.")
        box.setInformativeText(text.strip().splitlines()[-1][:300])
        box.setDetailedText(f"{text}\nFull log: {CRASH_LOG}")
        box.exec_()
    except Exception:
        pass                            # reporting must never crash the app


def main():
    crash_file = open(CRASH_LOG, "w")
    faulthandler.enable(file=crash_file)     # native faults (access violations)
    install_excepthook(crash_file)           # Python exceptions in slots

    # Must be set before the QApplication so JavaScript cells can later
    # embed a QtWebEngine view (harmless if PyQtWebEngine isn't installed).
    QApplication.setAttribute(Qt.AA_ShareOpenGLContexts)
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    app.setApplicationName("KherveBook")

    from .style import apply_style
    apply_style(app)

    from .mainwindow import MainWindow
    win = MainWindow()
    win.show()
    sys.exit(app.exec_())
