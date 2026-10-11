"""Raman spectrum import (two-column wavenumber / intensity text).

Each ``.txt`` becomes a sheet ``Raman_<file name>``; the folder import
gathers every ``.txt`` of a folder into one project (names cut to Excel's
31 characters, a clash numbered ``_1``, ``_2``…). KherveFitting writes
them to an intermediate ``.xlsx`` (``Wavenumber (cm-1) | Raw Data``) and
reads that back with ``add_core_level_Data``, so values come out rounded
to two decimals — reproduced here.

Ported from KherveFittingPro (``libraries/FileMenu/Kal_Import.py``
``import_raman_txt_file`` / ``import_multiple_raman_files``), wx-free.

Copyright (C) 2026 Gwilherm Kerherve

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.
"""

import os

from . import Format
from .kfgeneric import as_list, xlsx_sheet


def parse_raman_txt(file_path):
    """``[[wavenumber, intensity], …]`` from the first two whitespace-
    separated numbers of each line; ``#`` lines and text rows are skipped."""
    data = []
    with open(file_path, 'r', errors='ignore') as f:
        for line in f:
            if line.strip() and not line.startswith('#'):
                parts = line.strip().split()
                if len(parts) >= 2:
                    try:
                        wavenumber = float(parts[0])
                        intensity = float(parts[1])
                        data.append([wavenumber, intensity])
                    except ValueError:
                        continue
    return data


def read_file(path):
    """File (.txt): one sheet, ``Raman_<name up to the first dot>``."""
    path = str(path)
    base_filename = os.path.basename(path).split('.')[0]
    sheet_name = f"Raman_{base_filename}"
    data = parse_raman_txt(path)
    if not data:
        raise ValueError("No valid data found in the file.")
    return {sheet_name: xlsx_sheet(sheet_name, data)}


def read_folder(paths):
    """Multiple files (folder): every .txt as ``Raman_<stem>``."""
    files = []
    for p in as_list(paths):
        if os.path.isdir(p):
            files.extend(os.path.join(p, f) for f in sorted(os.listdir(p))
                         if f.lower().endswith('.txt'))
        else:
            files.append(p)

    core_levels = {}
    for file_path in files:
        base_filename = os.path.splitext(os.path.basename(file_path))[0]
        sheet_name = f"Raman_{base_filename}"
        if len(sheet_name) > 31:
            sheet_name = sheet_name[:31]
        count = 1
        original_name = sheet_name
        while sheet_name in core_levels:
            sheet_name = f"{original_name[:27]}_{count}"
            count += 1
        data = parse_raman_txt(file_path)
        if not data:
            continue
        core_levels[sheet_name] = xlsx_sheet(sheet_name, data)
    if not core_levels:
        raise ValueError("No valid data found in any of the text files.")
    return core_levels


FORMATS = [
    Format("Raman", "File (.txt)", (".txt",), read_file,
           sniff=lambda p: False),
    Format("Raman", "Multiple files (folder)", (".txt",), read_folder,
           sniff=lambda p: False, multi=True),
]
