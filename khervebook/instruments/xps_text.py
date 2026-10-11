"""Plain-text XPS imports: MRS, VG-Microtech ``.1``, generic ASC and CSV.

* **MRS** (``.mrs``, Physical Electronics): ``array_size=``, ``lo_be=`` /
  ``up_be=`` and the counts between ``!`` marks; the sheet is named from
  the file name (``get_core_level_from_filename``).
* **VG-Microtech** (``.1``): line 2 holds start / end / step / … / points
  / pass energy / photon energy, line 3 the region name, then one count
  per line.
* **ASC** and **CSV**: two columns, binding energy and intensity; the
  sheet is named after the file. Both are menu-only — KherveBook opens a
  dropped ``.csv`` / ``.txt`` as a spreadsheet.

Each family also has KherveFitting's "Multiple files (folder)" import,
here a ``multi`` format: several files into one project, one sheet each,
the way its "One Combined File" answer names them.

Ported from KherveFittingPro ``libraries/FileMenu/MRS_Import.py``,
``VGMicrotech_Import.py`` and ``XPS_ASC_CSV_Import.py`` (and ``Open.py``
``normalize_sheet_name``), wx-free. They all write an intermediate
workbook that KherveFitting then opens; `xlsxflow` replays that.

Copyright (C) 2026 Gwilherm Kerherve

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.
"""

import os
import re

import numpy as np

from . import Format
from . import xlsxflow
from .xlsxflow import normalize_sheet_name


def _text(path, errors='ignore'):
    raw = open(path, 'rb').read()
    try:
        return raw.decode('utf-8')
    except UnicodeDecodeError:
        return raw.decode('latin-1', errors=errors)


# ---------------------------------------------------------------------------
#  MRS
# ---------------------------------------------------------------------------

_MRS_LEVELS = {
    'C': 'C1s', 'N': 'N1s', 'O': 'O1s', 'F': 'F1s', 'S': 'S2p',
    'CL': 'Cl2p', 'BR': 'Br3d', 'I': 'I3d', 'SI': 'Si2p', 'P': 'P2p',
    'B': 'B1s', 'LI': 'Li1s', 'NA': 'Na1s', 'K': 'K2p', 'CA': 'Ca2p',
    'MG': 'Mg2p', 'AL': 'Al2p', 'TI': 'Ti2p', 'V': 'V2p', 'CR': 'Cr2p',
    'MN': 'Mn2p', 'FE': 'Fe2p', 'CO': 'Co2p', 'NI': 'Ni2p', 'CU': 'Cu2p',
    'ZN': 'Zn2p', 'GA': 'Ga3d', 'GE': 'Ge3d', 'AS': 'As3d', 'SE': 'Se3d',
    'RB': 'Rb3d', 'SR': 'Sr3d', 'Y': 'Y3d', 'ZR': 'Zr3d', 'NB': 'Nb3d',
    'MO': 'Mo3d', 'RU': 'Ru3d', 'RH': 'Rh3d', 'PD': 'Pd3d', 'AG': 'Ag3d',
    'CD': 'Cd3d', 'IN': 'In3d', 'SN': 'Sn3d', 'SB': 'Sb3d', 'TE': 'Te3d',
    'CS': 'Cs3d', 'BA': 'Ba3d', 'LA': 'La3d', 'CE': 'Ce3d', 'HF': 'Hf4f',
    'TA': 'Ta4f', 'W': 'W4f', 'RE': 'Re4f', 'OS': 'Os4f', 'IR': 'Ir4f',
    'PT': 'Pt4f', 'AU': 'Au4f', 'HG': 'Hg4f', 'PB': 'Pb4f', 'BI': 'Bi4f',
    'TH': 'Th4f', 'U': 'U4f', 'SU': 'Survey', 'VB': 'VB',
}


def get_core_level_from_filename(filename):
    """KherveFitting's MRS sheet name for *filename*.

    Its ``_SUFFIX.mrs`` pattern is matched against the upper-cased name,
    so it never fires; the name falls through to the first map key found
    anywhere in the stem ("C" first) — reproduced as is.
    """
    base_name = os.path.basename(filename)
    match = re.search(r'_([A-Z]+)\.mrs$', base_name.upper())
    if match:
        suffix = match.group(1)
        return _MRS_LEVELS.get(suffix, suffix)
    stem = os.path.splitext(base_name)[0]
    for key, value in _MRS_LEVELS.items():
        if key in stem.upper():
            return value
    return stem


_MRS_PATTERNS = [
    r'array_size=(\d+).*?data=Data Array.*?lo_be=([0-9.-]+).*?'
    r'up_be=([0-9.-]+).*?!(.*?)!',
    r'array_size=(\d+).*?data=Auto Survey.*?lo_be=([0-9.-]+).*?'
    r'up_be=([0-9.-]+).*?!(.*?)!',
    r'array_size=(\d+).*?lo_be=([0-9.-]+).*?up_be=([0-9.-]+).*?!(.*?)!',
]

_MRS_PATTERNS_COMBINED = [
    r'array_size=(\d+).*?(?:data=Data Array|data=Auto Survey).*?'
    r'lo_be=([0-9.-]+).*?up_be=([0-9.-]+).*?!(.*?)!',
    _MRS_PATTERNS[2],
]


def _mrs_spectrum(content, patterns):
    """``(be_values, counts)`` or None when the data section is missing."""
    match = None
    for pattern in patterns:
        match = re.search(pattern, content, re.DOTALL)
        if match:
            break
    if not match:
        return None
    be_start = float(match.group(2))
    be_end = float(match.group(3))
    values = []
    for line in match.group(4).strip().split('\n'):
        line = line.strip()
        if line and line.isdigit():
            values.append(int(line))
    if not values:
        return [], []
    n = len(values)
    step = (be_end - be_start) / (n - 1) if n > 1 else 0
    return [be_end - i * step for i in range(n)], values


def read_mrs(path):
    """MRS data file (.mrs) — KherveFitting's Import ▸ MRS ▸ Data file."""
    content = _text(path)
    sheet_name = get_core_level_from_filename(path)
    if "_" in sheet_name:
        core = sheet_name.split("_")[1]
        if core.lower() in ["c1s", "o1s", "n1s", "s2p", "su", "vb"]:
            sheet_name = "Survey" if core.lower() == "su" else core.upper()

    spectrum = _mrs_spectrum(content, _MRS_PATTERNS)
    if spectrum is None:
        raise ValueError("could not locate the data section (array_size= "
                         "… lo_be= … up_be= … !counts!)")
    be_values, counts = spectrum
    if not counts:
        raise ValueError("no valid data found in the MRS file")

    wb = xlsxflow.Workbook()
    ws = wb.create_sheet(sheet_name)
    ws.set_columns(["Binding Energy (eV)", "Raw Data"], be_values, counts)
    return xlsxflow.open_xlsx(wb)


def read_mrs_many(paths):
    """Several MRS files as one project (the "One Combined File" import)."""
    wb = xlsxflow.Workbook()
    processed = 0
    for path in paths:
        if not str(path).lower().endswith('.mrs'):
            continue
        try:
            content = _text(path)
            sheet_name = get_core_level_from_filename(
                os.path.basename(path))
            original, suffix = sheet_name, 1
            while sheet_name in wb.sheetnames:
                sheet_name = f"{original}{suffix}"
                suffix += 1
            ws = wb.create_sheet(sheet_name)
            spectrum = _mrs_spectrum(content, _MRS_PATTERNS_COMBINED)
            if spectrum and spectrum[1]:
                be_values, counts = spectrum
                ws.set_columns(["Binding Energy (eV)", "Corrected Data",
                                "Raw Data", "Transmission"],
                               be_values, counts, counts,
                               [1.0] * len(counts))
                processed += 1
        except (OSError, ValueError):
            continue
    if not processed:
        raise ValueError("no valid data found in any MRS file")
    return xlsxflow.open_xlsx(wb)


# ---------------------------------------------------------------------------
#  VG-Microtech .1
# ---------------------------------------------------------------------------

def _vg_parse(path):
    lines = _text(path).splitlines(True)
    if len(lines) < 3:
        raise ValueError("too short for a VG-Microtech .1 file")
    header = lines[1].strip().split()
    try:
        params = {
            'be_start': float(header[0]), 'be_end': float(header[1]),
            'energy_step': float(header[2]), 'unknown': float(header[3]),
            'dwell_time': float(header[4]), 'num_points': int(header[5]),
            'pass_energy': float(header[6]),
            'photon_energy': abs(float(header[7])),
        }
    except (IndexError, ValueError):
        raise ValueError("line 2 is not a VG-Microtech header (start end "
                         "step … points pass-energy photon-energy)")
    measurement_type = lines[2].strip()
    counts = []
    for line in lines[3:]:
        if line.strip():
            try:
                counts.append(float(line.strip()))
            except ValueError:
                continue
    n = params['num_points']
    if len(counts) > n:
        counts = counts[:n]
    be_values = np.linspace(params['be_start'], params['be_end'], n)
    return params, measurement_type, be_values, counts


def sniff_vg(path):
    with open(path, 'rb') as f:
        head = f.read(4096).decode('latin-1')
    lines = head.splitlines()
    if len(lines) < 4:
        return False
    tokens = lines[1].split()
    if len(tokens) < 8:
        return False
    try:
        [float(t) for t in tokens[:8]]
        int(tokens[5])
        float(lines[3].strip())
    except ValueError:
        return False
    return bool(lines[2].strip())


def _vg_sheet(ws, be_values, counts):
    n = min(len(be_values), len(counts))
    ws.set_columns(["Binding Energy (eV)", "Corrected Data", "Raw Data",
                    "Transmission"],
                   [float(b) for b in be_values[:n]], counts[:n],
                   counts[:n], [1.0] * n)


def read_vg(path):
    """VG-Microtech file (.1)."""
    _params, measurement_type, be_values, counts = _vg_parse(path)
    wb = xlsxflow.Workbook()
    ws = wb.create_sheet(normalize_sheet_name(measurement_type))
    _vg_sheet(ws, be_values, counts)
    return xlsxflow.open_xlsx(wb)


def read_vg_many(paths):
    """Several VG-Microtech files as one project ("One Combined File")."""
    wb = xlsxflow.Workbook()
    wb.create_sheet("Experimental description")
    processed = 0
    for path in paths:
        if not str(path).endswith('.1'):
            continue
        try:
            _params, measurement_type, be_values, counts = _vg_parse(path)
            sheet_name = normalize_sheet_name(measurement_type)
            if sheet_name in wb.sheetnames:
                count = 1
                while f"{sheet_name}{count}" in wb.sheetnames:
                    count += 1
                sheet_name = f"{sheet_name}{count}"
            ws = wb.create_sheet(sheet_name)
            _vg_sheet(ws, be_values, counts)
            processed += 1
        except (OSError, ValueError):
            continue
    if not processed:
        raise ValueError("no valid data found in any VG-Microtech file")
    return xlsxflow.open_xlsx(wb)


# ---------------------------------------------------------------------------
#  Generic ASC / CSV
# ---------------------------------------------------------------------------

def _asc_rows(path):
    data = []
    for line in _text(path).splitlines():
        if line.strip() and not line.startswith('#'):
            if ';' in line:
                parts = line.strip().split(';')
            elif ',' in line:
                parts = line.strip().split(',')
            else:
                parts = line.strip().split()
            if len(parts) >= 2:
                try:
                    data.append([float(parts[0]), float(parts[1])])
                except ValueError:
                    continue
    return data


def read_asc(path):
    """XPS ASCII file (.asc): binding energy and intensity columns.

    KherveFitting writes these cells as two-decimal *text*, so its sheet
    refresh stops early and the values stay cut to two decimals.
    """
    data = _asc_rows(path)
    if not data:
        raise ValueError("no valid data found in the file (two numeric "
                         "columns expected)")
    wb = xlsxflow.Workbook()
    ws = wb.create_sheet(os.path.basename(path).split('.')[0])
    ws.set_columns(["BE", "Raw Data"], [f"{b:.2f}" for b, _ in data],
                   [f"{y:.2f}" for _, y in data])
    return xlsxflow.open_xlsx(wb)


def _folder_sheet_name(wb, path):
    sheet_name = os.path.splitext(os.path.basename(path))[0]
    if len(sheet_name) > 31:
        sheet_name = sheet_name[:31]
    count, original = 1, sheet_name
    while sheet_name in wb.sheetnames:
        sheet_name = f"{original[:27]}_{count}"
        count += 1
    return sheet_name


def read_asc_many(paths):
    """Several ASC files as one project (the folder import)."""
    wb = xlsxflow.Workbook()
    for path in paths:
        if not str(path).lower().endswith('.asc'):
            continue
        sheet_name = _folder_sheet_name(wb, path)
        data = _asc_rows(path)
        if not data:
            continue
        ws = wb.create_sheet(sheet_name)
        ws.set_columns(["BE", "Raw Data"], [b for b, _ in data],
                       [y for _, y in data])
    if not wb.sheets:
        raise ValueError("no valid data found in any of the ASC files")
    return xlsxflow.open_xlsx(wb)


def _csv_rows(path):
    import pandas as pd
    df = pd.read_csv(path, delimiter=',', header=None)
    if df.shape[1] < 2:
        for sep in [';', '\t', ' ']:
            test_df = pd.read_csv(path, delimiter=sep, header=None)
            if test_df.shape[1] >= 2:
                df = test_df
                break
    if df.shape[1] < 2:
        raise ValueError("the CSV file must contain at least two columns "
                         "(BE and intensity)")
    data = df.iloc[:, :2].values
    if len(data) == 0:
        raise ValueError("no valid data found in the file")
    try:
        return [(float(b), float(y)) for b, y in data]
    except (TypeError, ValueError):
        raise ValueError("the first two columns must be numbers only "
                         "(no header row)")


def read_csv(path):
    """XPS CSV file (.csv): binding energy and intensity columns."""
    data = _csv_rows(path)
    wb = xlsxflow.Workbook()
    ws = wb.create_sheet(os.path.basename(path).split('.')[0])
    ws.set_columns(["Binding Energy (eV)", "Raw Data"],
                   [b for b, _ in data], [y for _, y in data])
    return xlsxflow.open_xlsx(wb)


def read_csv_many(paths):
    """Several CSV files as one project (the folder import)."""
    wb = xlsxflow.Workbook()
    for path in paths:
        if not str(path).lower().endswith('.csv'):
            continue
        sheet_name = _folder_sheet_name(wb, path)
        try:
            data = _csv_rows(path)
        except ImportError:
            raise
        except Exception:
            continue
        ws = wb.create_sheet(sheet_name)
        ws.set_columns(["Binding Energy (eV)", "Raw Data"],
                       [b for b, _ in data], [y for _, y in data])
    if not wb.sheets:
        raise ValueError("no valid data found in any of the CSV files")
    return xlsxflow.open_xlsx(wb)


def _never(_path):
    return False


FORMATS = [
    Format("XPS", "MRS (.mrs)", (".mrs",), read_mrs, group="MRS"),
    Format("XPS", "MRS files (.mrs)", (".mrs",), read_mrs_many,
           group="MRS", multi=True, sniff=_never),
    Format("XPS", "VG-Microtech (.1)", (".1",), read_vg,
           group="VG-Microtech", sniff=sniff_vg),
    Format("XPS", "VG-Microtech files (.1)", (".1",), read_vg_many,
           group="VG-Microtech", multi=True, sniff=_never),
    Format("XPS", "ASCII (.asc)", (".asc",), read_asc, sniff=_never),
    Format("XPS", "ASCII files (.asc)", (".asc",), read_asc_many,
           multi=True, sniff=_never),
    Format("XPS", "CSV (.csv)", (".csv",), read_csv, sniff=_never,
           needs=("pandas",)),
    Format("XPS", "CSV files (.csv)", (".csv",), read_csv_many,
           multi=True, sniff=_never, needs=("pandas",)),
]
