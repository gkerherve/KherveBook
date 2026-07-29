"""File pickers that do not load the Windows shell into our process.

Windows' native picker (``IFileDialog``) runs Explorer's own COM code —
and every shell extension installed on the machine — inside the calling
process. A misbehaving extension therefore takes the *host* down with it:
browsing a folder synced by OneDrive/MEGAsync floods KherveBook with
``RPC_E_WRONG_THREAD`` (0x8001010e) and kills it while the dialog is
still open, losing the notebook and every unsaved cell. Nothing in
KherveBook is at fault, but it is KherveBook that dies.

Qt's own widget-based dialog does the same job without loading a single
shell extension, so that is the default on Windows. The trade-off is a
plainer dialog — no Quick Access sidebar, no cloud placeholders — so a
machine with a healthy shell can have the native one back:

    QSettings("Kherve", "KherveBook").setValue("files/native_dialogs", True)

Every file picker in the app goes through this module, because the crash
belongs to the shell, not to the cell type that happened to open it.

Copyright (C) 2026 Gwilherm Kerherve

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.
"""

import os

from PyQt5.QtCore import QSettings
from PyQt5.QtWidgets import QFileDialog

_SETTINGS = ("Kherve", "KherveBook")
_KEY = "files/native_dialogs"


def native_dialogs() -> bool:
    """Whether to use the OS picker. Off on Windows (see the module note)."""
    value = QSettings(*_SETTINGS).value(_KEY, os.name != "nt")
    return value in (True, "true", "True", 1, "1")


def set_native_dialogs(on: bool):
    QSettings(*_SETTINGS).setValue(_KEY, bool(on))


def _options(extra=0):
    opts = QFileDialog.Options(extra)
    if not native_dialogs():
        opts |= QFileDialog.DontUseNativeDialog
    return opts


def open_file(parent, caption, directory="", filter="All files (*)") -> str:
    """One existing file, or "" if the user cancelled."""
    name, _ = QFileDialog.getOpenFileName(parent, caption, directory, filter,
                                          options=_options())
    return name


def open_files(parent, caption, directory="", filter="All files (*)") -> list:
    """Several existing files, or [] if the user cancelled."""
    names, _ = QFileDialog.getOpenFileNames(parent, caption, directory, filter,
                                            options=_options())
    return names


def save_file(parent, caption, directory="", filter="All files (*)") -> str:
    """A path to write to, or "" if the user cancelled."""
    name, _ = QFileDialog.getSaveFileName(parent, caption, directory, filter,
                                          options=_options())
    return name


def existing_directory(parent, caption, directory="") -> str:
    """A folder, or "" if the user cancelled."""
    return QFileDialog.getExistingDirectory(
        parent, caption, directory,
        options=_options(QFileDialog.ShowDirsOnly))
