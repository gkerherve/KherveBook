# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for KherveBook — one-folder (onedir) build.

Produces ``dist/KherveBook/KherveBook.exe`` alongside a folder of the
decompressed runtime (Python, Qt, the scientific stack). Build with:

    pyinstaller packaging/KherveBook.spec --noconfirm

The window/taskbar icon is baked in from ``packaging/khervebook.ico``
(regenerate it with ``python packaging/make_icon.py`` after editing the
mark in ``khervebook/icons.py``).
"""

import os

from PyInstaller.utils.hooks import collect_all, collect_submodules

_HERE = os.path.abspath(SPECPATH)                 # packaging/
_ROOT = os.path.dirname(_HERE)                    # project root

datas, binaries, hiddenimports = [], [], []

# The whole app package (some submodules are imported lazily inside
# functions, e.g. plotcanvas / jscell — pull them all in explicitly).
hiddenimports += collect_submodules("khervebook")

# Dependencies that ship data files or dynamically-imported submodules.
for _pkg in ("qtawesome", "lmfit", "dask", "fitz", "pygit2"):
    try:
        d, b, h = collect_all(_pkg)
        datas += d
        binaries += b
        hiddenimports += h
    except Exception:
        pass   # optional dependency not installed — skip it

a = Analysis(
    [os.path.join(_ROOT, "KherveBook.py")],
    pathex=[_ROOT],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    # Trim heavy libraries the app never uses, to keep the folder smaller.
    excludes=["tkinter", "PyQt6", "PySide2", "PySide6", "PyQt5.QtQml",
              "PyQt5.QtQuick"],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,                 # onedir: binaries live in COLLECT
    name="KherveBook",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,                         # GUI app: no console window
    icon=os.path.join(_HERE, "khervebook.ico"),
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="KherveBook",                     # -> dist/KherveBook/
)
