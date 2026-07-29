"""The shared file pickers must keep the Windows shell out of process.

Copyright (C) 2026 Gwilherm Kerherve

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.
"""

import pytest
from PyQt5.QtWidgets import QFileDialog

from khervebook import filedialog


@pytest.fixture(autouse=True)
def _clean_setting(qapp):
    """Each test starts from the shipped default, not the dev's registry."""
    from PyQt5.QtCore import QSettings
    settings = QSettings("Kherve", "KherveBook")
    had = settings.contains("files/native_dialogs")
    before = settings.value("files/native_dialogs")
    settings.remove("files/native_dialogs")
    yield
    if had:
        settings.setValue("files/native_dialogs", before)
    else:
        settings.remove("files/native_dialogs")


def test_windows_defaults_to_qts_own_dialog(monkeypatch):
    """The native picker loads every shell extension into our process; one
    misbehaving one (OneDrive) crashes KherveBook with COM 0x8001010e."""
    monkeypatch.setattr(filedialog.os, "name", "nt")
    assert not filedialog.native_dialogs()
    assert filedialog._options() & QFileDialog.DontUseNativeDialog


def test_other_platforms_keep_the_native_dialog(monkeypatch):
    monkeypatch.setattr(filedialog.os, "name", "posix")
    assert filedialog.native_dialogs()
    assert not filedialog._options() & QFileDialog.DontUseNativeDialog


def test_the_setting_can_bring_the_native_dialog_back(monkeypatch):
    monkeypatch.setattr(filedialog.os, "name", "nt")
    filedialog.set_native_dialogs(True)
    assert filedialog.native_dialogs()
    assert not filedialog._options() & QFileDialog.DontUseNativeDialog
    filedialog.set_native_dialogs(False)
    assert not filedialog.native_dialogs()


def test_existing_directory_keeps_its_own_flag(monkeypatch):
    monkeypatch.setattr(filedialog.os, "name", "nt")
    opts = filedialog._options(QFileDialog.ShowDirsOnly)
    assert opts & QFileDialog.ShowDirsOnly
    assert opts & QFileDialog.DontUseNativeDialog


@pytest.mark.parametrize("func, qt_name, result", [
    ("open_file", "getOpenFileName", ("/tmp/a.kfit", "")),
    ("open_files", "getOpenFileNames", (["/tmp/a", "/tmp/b"], "")),
    ("save_file", "getSaveFileName", ("/tmp/out.kbook", "")),
])
def test_pickers_pass_options_and_unwrap_the_result(monkeypatch, func,
                                                    qt_name, result):
    seen = {}

    def fake(parent, caption, directory, filt, options=None):
        seen.update(caption=caption, options=options)
        return result

    monkeypatch.setattr(filedialog.os, "name", "nt")
    monkeypatch.setattr(QFileDialog, qt_name, fake)
    got = getattr(filedialog, func)(None, "Pick")
    assert got == result[0]
    assert seen["caption"] == "Pick"
    assert seen["options"] & QFileDialog.DontUseNativeDialog


def test_cancelling_returns_an_empty_value(monkeypatch):
    monkeypatch.setattr(QFileDialog, "getOpenFileName",
                        lambda *a, **k: ("", ""))
    monkeypatch.setattr(QFileDialog, "getOpenFileNames",
                        lambda *a, **k: ([], ""))
    assert filedialog.open_file(None, "Pick") == ""
    assert filedialog.open_files(None, "Pick") == []


def test_no_cell_opens_the_shell_picker_directly():
    """Every picker goes through the helper — the crash belongs to the
    shell, not to whichever cell type happened to open the dialog."""
    from pathlib import Path

    package = Path(filedialog.__file__).parent
    offenders = []
    for module in sorted(package.glob("*.py")):
        if module.name == "filedialog.py":
            continue
        text = module.read_text(encoding="utf-8")
        for call in ("QFileDialog.getOpenFileName",
                     "QFileDialog.getOpenFileNames",
                     "QFileDialog.getSaveFileName",
                     "QFileDialog.getExistingDirectory"):
            if call in text:
                offenders.append(f"{module.name}: {call}")
    assert not offenders, offenders
