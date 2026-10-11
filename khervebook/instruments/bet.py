"""Gas-adsorption isotherm import for BET / physisorption analysis.

Ported from KherveFittingPro (``libraries/FileMenu/BET_Import.py``
``parse_bet_file`` / ``build_bet_sheet``, with the generic column parser
``Optical_Import.parse_columns_file`` and the BET branch of
``KFitting_Import.build_generic_sheet``), wx-free. Micromeritics,
Quantachrome and bare P/P0 - quantity text exports become sheets BET,
BET1…; the relative-pressure column is picked by value (0..1.05), the
quantity is the last other column, and the adsorption / desorption
branches are flagged per point in ``BET_Branch``.

Copyright (C) 2026 Gwilherm Kerherve

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.
"""

import os
import re

from . import Format

TECH_BET = "BET Isotherm"
X_LABEL_RELP = "Relative pressure (P/P$_0$)"
Y_LABEL_QUANTITY = "Quantity adsorbed (cm$^3$/g STP)"

_TEXT_EXTS = ('.csv', '.txt', '.dat')


# ---------------------------------------------------------------------------
# Generic column parser (Optical_Import.parse_columns_file)
# ---------------------------------------------------------------------------

def parse_columns_file(file_path, max_columns=4):
    """``(rows, metadata)``: rows of floats of the dominant column count,
    and the ``key=value`` / ``key: value`` header lines."""
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
# Parsing
# ---------------------------------------------------------------------------

def _metadata_p0(metadata):
    """A saturation pressure from the header block, if one is quoted."""
    for key, value in metadata.items():
        norm = str(key).lower().replace(' ', '').rstrip(':')
        if norm in ('p0', 'po', 'psat') or 'saturationpressure' in norm:
            try:
                return float(str(value).split()[0].replace(',', '.'))
            except (ValueError, IndexError):
                continue
    return None


def identify_isotherm_columns(rows, metadata):
    """``(x_values, q_values)`` — relative pressure and quantity."""
    n_cols = len(rows[0])
    columns = [[r[i] for r in rows] for i in range(n_cols)]

    def is_relative(values):
        lo, hi = min(values), max(values)
        return -0.001 <= lo and hi <= 1.05 and (hi - lo) > 0.05

    rel_index = next((i for i, col in enumerate(columns)
                      if is_relative(col)), None)

    if rel_index is not None:
        x_values = columns[rel_index]
        remaining = [i for i in range(n_cols) if i != rel_index]
    else:
        p0 = _metadata_p0(metadata)
        if p0 is None:
            raise ValueError("no relative-pressure column (0..1) found and "
                             "no saturation pressure P0 in the header")
        x_values = [v / p0 for v in columns[0]]
        remaining = list(range(1, n_cols))

    if not remaining:
        raise ValueError("no quantity-adsorbed column found")
    q_values = columns[remaining[-1]]
    return x_values, q_values


def split_branches(x_values):
    """Per-point branch flags: 1 up to the maximum P/P0, 2 after it."""
    if not x_values:
        return []
    turn = max(range(len(x_values)), key=lambda i: x_values[i])
    return [1 if i <= turn else 2 for i in range(len(x_values))]


def parse_bet_file(file_path):
    """``{'x', 'q', 'branch', 'metadata'}`` of an isotherm text export."""
    rows, metadata = parse_columns_file(file_path, max_columns=6)
    if len(rows) < 3:
        raise ValueError("no numeric data rows found")

    x_values, q_values = identify_isotherm_columns(rows, metadata)

    keep = [i for i, (x, q) in enumerate(zip(x_values, q_values))
            if x is not None and q is not None and 0.0 <= x <= 1.05]
    if len(keep) < 3:
        raise ValueError("fewer than three points with 0 <= P/P0 <= 1")

    x_values = [float(x_values[i]) for i in keep]
    q_values = [float(q_values[i]) for i in keep]
    return {'x': x_values, 'q': q_values,
            'branch': split_branches(x_values), 'metadata': metadata}


# ---------------------------------------------------------------------------
# Sheet construction
# ---------------------------------------------------------------------------

def next_bet_sheet_name(existing_names):
    """Return the next free BET sheet name: BET, BET1, BET2, ..."""
    existing = {str(name).upper() for name in existing_names}
    if 'BET' not in existing:
        return 'BET'
    idx = 1
    while f'BET{idx}' in existing:
        idx += 1
    return f'BET{idx}'


def _generic_background(x_values, y_values):
    return {
        'Bkg Y': list(y_values),
        'Bkg Type': '',
        'Bkg Low': float(min(x_values)) if x_values else '',
        'Bkg High': float(max(x_values)) if x_values else '',
        'Bkg Offset Low': 0,
        'Bkg Offset High': 0,
    }


def build_generic_bet_sheet(sheet_name, x_values, y_values, source_name=''):
    """``build_generic_sheet(TECH_BET, …)`` from KFitting_Import."""
    sheet = {
        'Name': sheet_name,
        'B.E.': list(x_values),
        'Raw Data': list(y_values),
        'Background': _generic_background(x_values, y_values),
        'Fitting': {'Peaks': {}},
        'ExperimentalInfo': {
            'Technique': TECH_BET,
            'Source Sheet': source_name,
            'Number of Points': str(len(x_values)),
        },
    }
    sheet.update({
        'BET_X_Label': X_LABEL_RELP,
        'BET_Y_Label': Y_LABEL_QUANTITY,
        'BET_Label': source_name or sheet_name,
        'BET_Source': source_name,
    })
    if x_values:
        turn = max(range(len(x_values)), key=lambda i: x_values[i])
        sheet['BET_Branch'] = [1.0 if i <= turn else 2.0
                               for i in range(len(x_values))]
    return sheet


def build_bet_sheet(parsed, file_path, sheet_name):
    """The core-level entry for one isotherm."""
    source = os.path.splitext(os.path.basename(file_path))[0]
    sheet = build_generic_bet_sheet(sheet_name, parsed['x'], parsed['q'],
                                    source_name=source)
    sheet['BET_Branch'] = [float(v) for v in parsed['branch']]
    n_des = sum(1 for b in parsed['branch'] if b == 2)

    info = sheet['ExperimentalInfo']
    info['Technique'] = 'Gas Adsorption (BET)'
    info['Source File'] = os.path.basename(file_path)
    info['P/P0 Range'] = f"{min(parsed['x']):.3f} - {max(parsed['x']):.3f}"
    info['Branches'] = ('adsorption + desorption' if n_des > 1
                        else 'adsorption only')
    for src, dst in (('Sample', 'Sample'),
                     ('Analysis Adsorptive', 'Adsorptive'),
                     ('Adsorptive', 'Adsorptive'),
                     ('Analysis Bath Temp', 'Bath'),
                     ('Operator', 'Operator'), ('Instrument', 'Instrument')):
        for name, value in parsed['metadata'].items():
            if str(name).lower().replace(' ', '') \
                    == src.lower().replace(' ', '') and value:
                info[dst] = value
                break
    return sheet


# ---------------------------------------------------------------------------
# Readers
# ---------------------------------------------------------------------------

def _expand(paths, exts):
    out = []
    for p in paths:
        p = str(p)
        if os.path.isdir(p):
            out += [os.path.join(p, f) for f in os.listdir(p)
                    if f.lower().endswith(exts)]
        elif p.lower().endswith(exts):
            out.append(p)
    return sorted(out)


def _import_paths(file_paths):
    """``_import_bet_paths`` without the window: {sheet: core level}."""
    core_levels = {}
    skipped = []
    for file_path in sorted(str(p) for p in file_paths):
        try:
            parsed = parse_bet_file(file_path)
        except Exception as e:
            skipped.append(f"{os.path.basename(file_path)}: {e}")
            continue
        name = next_bet_sheet_name(core_levels.keys())
        core_levels[name] = build_bet_sheet(parsed, file_path, name)
    if not core_levels:
        raise ValueError("No valid isotherm data found."
                         + ("\n" + "\n".join(skipped) if skipped else ""))
    return core_levels


def read_file(path):
    return _import_paths([path])


def read_folder(paths):
    files = _expand(paths, _TEXT_EXTS)
    if not files:
        raise ValueError("No .csv/.txt/.dat files found.")
    return _import_paths(files)


def _never(_path):
    return False


FORMATS = [
    Format("BET", "Isotherm file(s) (.csv/.txt/.dat)", _TEXT_EXTS, read_file,
           sniff=_never),
    Format("BET", "Multiple files (folder)", _TEXT_EXTS, read_folder,
           sniff=_never, multi=True),
]
