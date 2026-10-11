"""Shared pieces of KherveFitting's technique importers, wx-free.

The UV-Vis / PL / ellipsometry / MS / GC importers all end in
KherveFitting's ``build_generic_sheet``; the FTIR and Raman importers go
through an intermediate ``.xlsx`` that ``add_core_level_Data`` reads
back. Both are reproduced here so every reader module gives the sheet
KherveFitting itself would make.

Ported from KherveFittingPro (``libraries/FileMenu/KFitting_Import.py``
``build_generic_sheet`` / ``_unique_sheet_name``,
``libraries/FileMenu/Optical_Import.py`` ``parse_columns_file`` and
``libraries/ConfigFile.py`` ``add_core_level_Data``).

Copyright (C) 2026 Gwilherm Kerherve

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.
"""

import math
import os
import re

TECH_UVVIS = "UV-Vis Spectrum"
TECH_PL = "Photoluminescence"
TECH_ELLIPS = "Ellipsometry (Ψ)"
TECH_MS = "Mass Spectrum"
TECH_GC = "Gas Chromatogram"


# ---------------------------------------------------------------------------
#  Paths
# ---------------------------------------------------------------------------
def as_list(paths):
    """A reader's argument as a list of path strings."""
    if isinstance(paths, (list, tuple)):
        return [str(p) for p in paths]
    return [str(paths)]


def expand(paths, extensions):
    """Every file of *paths*, with folders replaced by their files ending in
    one of *extensions* (sorted, non-recursive) — KherveFitting's "Multiple
    files (folder)" imports take a folder, KherveBook may hand one over."""
    out = []
    for p in as_list(paths):
        if os.path.isdir(p):
            out.extend(os.path.join(p, f) for f in sorted(os.listdir(p))
                       if f.lower().endswith(tuple(extensions))
                       and os.path.isfile(os.path.join(p, f)))
        else:
            out.append(p)
    return out


def stem(path):
    return os.path.splitext(os.path.basename(path))[0]


def head_text(path, size=4096):
    """The first *size* bytes of a file as text (for sniffing)."""
    with open(path, "rb") as fh:
        return fh.read(size).decode("latin-1", "ignore")


def fail_if_empty(core_levels, skipped, what="data"):
    """KherveFitting's "No valid … found" popup, as an exception."""
    if not core_levels:
        detail = ("\n" + "\n".join(skipped)) if skipped else ""
        raise ValueError(f"No valid {what} found.{detail}")
    return core_levels


# ---------------------------------------------------------------------------
#  Sheet naming / generic sheet
# ---------------------------------------------------------------------------
def unique_sheet_name(base, used):
    """base, base1, base2, ... - whichever is free (case-insensitively)."""
    taken = {str(name).upper() for name in used}
    if base.upper() not in taken:
        return base
    idx = 1
    while f"{base}{idx}".upper() in taken:
        idx += 1
    return f"{base}{idx}"


def _generic_background(x_values, y_values):
    return {
        'Bkg Y': list(y_values),
        'Bkg Type': '',
        'Bkg Low': float(min(x_values)) if x_values else '',
        'Bkg High': float(max(x_values)) if x_values else '',
        'Bkg Offset Low': 0,
        'Bkg Offset High': 0,
    }


def build_generic_sheet(technique, sheet_name, x_values, y_values,
                        source_name='', extra_values=None):
    """KherveFitting's ``build_generic_sheet`` for the optical, MS and GC
    techniques (the only ones these readers build)."""
    x_values = list(x_values)
    y_values = list(y_values)
    sheet = {
        'Name': sheet_name,
        'B.E.': list(x_values),
        'Raw Data': list(y_values),
        'Background': _generic_background(x_values, y_values),
        'Fitting': {'Peaks': {}},
        'ExperimentalInfo': {
            'Technique': technique,
            'Source Sheet': source_name,
            'Number of Points': str(len(x_values)),
        },
    }
    if technique == TECH_UVVIS:
        as_percent = bool(y_values) and max(y_values) > 5.0
        sheet.update({
            'UVVIS_X_Label': 'Wavelength (nm)',
            'UVVIS_Y_Label': ('Transmittance (%)' if as_percent
                              else 'Absorbance (a.u.)'),
            'UVVIS_Y_Mode': 'transmittance' if as_percent else 'absorbance',
            'UVVIS_Label': source_name or sheet_name,
            'UVVIS_Source': source_name,
        })
    elif technique == TECH_PL:
        sheet.update({
            'PL_X_Label': 'Wavelength (nm)',
            'PL_Y_Label': 'PL Intensity (a.u.)',
            'PL_Label': source_name or sheet_name,
            'PL_Source': source_name,
        })
    elif technique == TECH_ELLIPS:
        sheet.update({
            'ELLIPS_X_Label': 'Wavelength (nm)',
            'ELLIPS_Y_Label': 'Ψ (°)',
            'ELLIPS_Quantity': 'psi',
            'ELLIPS_Psi': list(y_values),
            'ELLIPS_Label': source_name or sheet_name,
            'ELLIPS_Source': source_name,
        })
        if extra_values:
            sheet['ELLIPS_Delta'] = [float(v) for v in extra_values]
    elif technique == TECH_MS:
        sheet.update({
            'MS_X_Label': 'm/z',
            'MS_Y_Label': 'Intensity (a.u.)',
            'MS_Label': source_name or sheet_name,
            'MS_Source': source_name,
        })
    elif technique == TECH_GC:
        sheet.update({
            'GC_X_Label': 'Retention time (min)',
            'GC_Y_Label': 'Signal (a.u.)',
            'GC_Label': source_name or sheet_name,
            'GC_Source': source_name,
        })
    return sheet


# ---------------------------------------------------------------------------
#  Delimited text
# ---------------------------------------------------------------------------
def parse_columns_file(file_path, max_columns=4):
    """Read a delimited text file into numeric columns.

    Returns ``(rows, metadata)``: ``rows`` holds tuples of floats, all of
    the most common numeric column count in the file; ``metadata`` maps
    any ``key=value`` / ``key: value`` header lines.
    """
    counted = {}
    metadata = {}
    decimal_comma = None

    with open(file_path, 'r', errors='ignore') as fh:
        for raw_line in fh:
            line = raw_line.strip()
            if not line or line.startswith(('#', '//', ';;')):
                continue

            if not line[0].isdigit() and line[0] not in '+-.':
                for sep in ('=', ':'):
                    if sep in line:
                        key, _, value = line.partition(sep)
                        if key.strip():
                            metadata[key.strip()] = value.strip()
                        break
                continue

            if decimal_comma is None:
                decimal_comma = ('.' not in line
                                 and re.search(r'\d,\d', line) is not None
                                 and re.search(r'[\t; ]', line) is not None)

            candidate = line.replace(',', '.') if decimal_comma else line
            splitter = r'[\t;\s]+' if decimal_comma else r'[\t;,\s]+'
            tokens = [t for t in re.split(splitter, candidate) if t]

            values = []
            for token in tokens[:max_columns]:
                try:
                    values.append(float(token))
                except ValueError:
                    values = []
                    break
            if len(values) >= 2:
                counted.setdefault(len(values), []).append(tuple(values))

    if not counted:
        return [], metadata
    n_cols = max(counted, key=lambda n: len(counted[n]))
    return counted[n_cols], metadata


# ---------------------------------------------------------------------------
#  The .xlsx round trip (FTIR, Raman)
# ---------------------------------------------------------------------------
def _round2(value):
    return float(f"{value:.2f}")


def xlsx_sheet(sheet_name, data):
    """The core level ``add_core_level_Data`` reads back from a two-column
    ``Wavenumber (cm-1) | Raw Data`` sheet written with *data* — values
    rounded to two decimals, Corrected Data = Raw Data, Transmission 1.0.
    A row whose cell would read back empty (NaN, inf) is skipped, as there;
    every value goes through openpyxl's ``"%.16g"`` cell text first, so a
    tie such as 63.254999999999995 rounds as KherveFitting's 63.255 does."""
    be_values, raw_data = [], []
    for x, y in data:
        try:
            x, y = float(x), float(y)
        except (TypeError, ValueError):
            continue
        if not (math.isfinite(x) and math.isfinite(y)):
            continue          # openpyxl writes NaN/inf as an empty cell
        # openpyxl stores a float as "%.16g", which is what is read back.
        be_values.append(float("%.16g" % x))
        raw_data.append(float("%.16g" % y))

    cl = {
        'B.E.': [_round2(v) for v in be_values],
        'Raw Data': [_round2(v) for v in raw_data],
        'Corrected Data': [_round2(v) for v in raw_data],
        'Transmission': [_round2(1.0) for _ in raw_data],
        'Name': sheet_name,
    }
    if be_values:
        cl['Background'] = {
            'Bkg Y': list(cl['Raw Data']),
            'Bkg Type': '',
            'Bkg Low': _round2(min(be_values)),
            'Bkg High': _round2(max(be_values)),
            'Bkg Offset Low': 0,
            'Bkg Offset High': 0,
        }
    return cl
