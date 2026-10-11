"""SQUID magnetometry import (Quantum Design MPMS / MPMS3 and generic CSV).

An MPMS3 ``.dat`` file is an INI-ish ``[Header]`` (``INFO,<value>,<KEY>``
lines) followed by a ``[Data]`` CSV table; an optional ``.gph`` sidecar
says which column the operator plotted on x. A CSV export is the same
table without the header, or a bare two-column x,y list. Each file
becomes one sheet — SQUID, SQUID1, … — of moment against temperature
(M(T), sorted) or field (M(H), acquisition order), with the
``SQUID_*`` keys KherveFitting's SQUID tool reads.

Ported from KherveFittingPro (``libraries/FileMenu/SQUID_Import.py``:
``parse_squid_file``, ``build_squid_sheet``, ``_import_squid_paths``
and its file / folder entry points), wx-free.

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
from .kfgeneric import expand, fail_if_empty, head_text

SCAN_MT = 'MT'   # moment vs temperature (ZFC / FC)
SCAN_MH = 'MH'   # moment vs field (hysteresis loop / isotherm)

X_LABEL_MT = "Temperature (K)"
X_LABEL_MH = "Magnetic Field (Oe)"
Y_LABEL_MOMENT = "Moment (emu)"

# Derived quantities the SQUID tool can produce, stored as 'SQUID_Quantity'.
QTY_MOMENT = 'moment'
QTY_CHI = 'chi'
QTY_INV_CHI = 'inv_chi'
QTY_CHI_T = 'chiT'

QUANTITY_LABELS = {
    QTY_MOMENT: "Moment (emu)",
    QTY_CHI: "χ (emu/mol-Oe)",
    QTY_INV_CHI: "1/χ (mol-Oe/emu)",
    QTY_CHI_T: "χT (emu K/mol-Oe)",
}


# ---------------------------------------------------------------------------
# Column matching
# ---------------------------------------------------------------------------

def _norm(name):
    """Lower-case, strip punctuation - for tolerant column-header matching."""
    return re.sub(r'[^a-z0-9]', '', str(name).lower())


# Ordered candidates: the first match wins, so the plain DC moment is preferred
# over the fixed/free-centre fit columns that MPMS3 also writes.
_TEMPERATURE_KEYS = ('temperaturek', 'sampletempk', 'temperature')
_FIELD_KEYS = ('magneticfieldoe', 'fieldoe', 'magneticfield')
_MOMENT_KEYS = ('momentemu', 'longmomentemu', 'dcmomentfixedctremu',
                'dcmomentfreectremu', 'momentemuoe', 'moment')


def _find_column(headers, candidates):
    """Index of the first header matching one of ``candidates``, else None."""
    normed = [_norm(h) for h in headers]
    for key in candidates:
        if key in normed:
            return normed.index(key)
    # Fall back to a prefix match (instruments append units we don't know)
    for key in candidates:
        for i, h in enumerate(normed):
            if h.startswith(key):
                return i
    return None


# ---------------------------------------------------------------------------
# .gph sidecar
# ---------------------------------------------------------------------------

def parse_gph(gph_path):
    """Read a MultiVu .gph plot description into ``{section: {key: value}}``."""
    sections = {}
    current = None
    with open(gph_path, 'r', errors='ignore') as f:
        for raw in f:
            line = raw.strip()
            if not line:
                continue
            if line.startswith('[') and line.endswith(']'):
                current = line[1:-1]
                sections[current] = {}
            elif current is not None and '=' in line:
                key, _, value = line.partition('=')
                sections[current][key.strip()] = value.strip()
    return sections


def _gph_axis_indices(gph_path):
    """Return ``(x_index, y_index)`` from a .gph sidecar, or ``(None, None)``.

    The indices are 0-based positions in the ``[Data]`` header row.
    """
    try:
        sections = parse_gph(gph_path)
    except Exception:
        return None, None

    def _idx(section, key):
        try:
            return int(sections.get(section, {}).get(key, ''))
        except (TypeError, ValueError):
            return None

    return _idx('X_Axis', 'itemIndex'), _idx('Y_Axis0', 'itemIndex')


# ---------------------------------------------------------------------------
# .dat / .csv parsing
# ---------------------------------------------------------------------------

def _split_header_and_rows(lines):
    """Split an MPMS file into ``(header_lines, column_names, data_rows)``.

    Files without a ``[Data]`` marker (plain CSV exports) are treated as a
    single header row followed by data.
    """
    data_at = None
    for i, line in enumerate(lines):
        if line.strip().lower() == '[data]':
            data_at = i
            break

    if data_at is None:
        header_lines = []
        start = 0
    else:
        header_lines = lines[:data_at]
        start = data_at + 1

    # Skip blank lines before the column-name row
    while start < len(lines) and not lines[start].strip():
        start += 1
    if start >= len(lines):
        return header_lines, [], []

    columns = [c.strip() for c in lines[start].split(',')]
    rows = [line.split(',') for line in lines[start + 1:] if line.strip()]
    return header_lines, columns, rows


def _parse_info_metadata(header_lines):
    """Pull the ``INFO,<value>,<KEY>`` pairs out of an MPMS header."""
    metadata = {}
    for line in header_lines:
        parts = [p.strip() for p in line.split(',')]
        if len(parts) >= 3 and parts[0].upper() == 'INFO':
            key = parts[-1]
            value = ','.join(parts[1:-1]).strip()
            if key:
                metadata[key] = value
        elif len(parts) >= 2 and parts[0].upper() in ('TITLE', 'FILEOPENTIME', 'BYAPP'):
            metadata[parts[0].upper()] = ','.join(parts[1:]).strip()
    return metadata


def _column(rows, index):
    """Extract one column as a list of floats, with None where unparseable."""
    out = []
    for row in rows:
        if index >= len(row):
            out.append(None)
            continue
        token = row[index].strip()
        try:
            out.append(float(token))
        except ValueError:
            out.append(None)
    return out


def parse_squid_file(file_path):
    """Parse an MPMS ``.dat``/``.csv`` (or generic two-column) SQUID file.

    Returns a dict with keys ``x``, ``y``, ``scan_type``, ``x_label``,
    ``y_label``, ``field_oe``, ``temperature_k``, ``metadata``, ``columns``.
    Raises ``ValueError`` when the file holds no usable data - MPMS writes a
    full header for aborted measurements, so this is a normal outcome.
    """
    with open(file_path, 'r', errors='ignore') as f:
        lines = f.read().splitlines()

    header_lines, columns, rows = _split_header_and_rows(lines)
    metadata = _parse_info_metadata(header_lines)

    if not rows:
        raise ValueError("no data rows (aborted or empty measurement)")

    t_idx = _find_column(columns, _TEMPERATURE_KEYS)
    h_idx = _find_column(columns, _FIELD_KEYS)
    m_idx = _find_column(columns, _MOMENT_KEYS)

    if m_idx is None or (t_idx is None and h_idx is None):
        # Not an MPMS table - fall back to a bare two-column x,y export
        return _parse_two_column(file_path, lines, metadata)

    temperature = _column(rows, t_idx) if t_idx is not None else None
    field = _column(rows, h_idx) if h_idx is not None else None
    moment = _column(rows, m_idx)

    # The .gph sidecar records which column the operator plotted on x
    x_from_gph = None
    for candidate in (file_path + '.gph', os.path.splitext(file_path)[0] + '.gph'):
        if os.path.exists(candidate):
            gph_x, _gph_y = _gph_axis_indices(candidate)
            if gph_x is not None:
                if gph_x == t_idx:
                    x_from_gph = SCAN_MT
                elif gph_x == h_idx:
                    x_from_gph = SCAN_MH
            break

    scan_type = x_from_gph or _infer_scan_type(temperature, field)

    if scan_type == SCAN_MT and temperature is None:
        scan_type = SCAN_MH
    if scan_type == SCAN_MH and field is None:
        scan_type = SCAN_MT

    x_raw = temperature if scan_type == SCAN_MT else field
    # The other axis is carried along so it stays row-aligned with x and y
    # through the filtering and sorting below.
    companion_raw = field if scan_type == SCAN_MT else temperature
    if companion_raw is None:
        companion_raw = [None] * len(moment)

    # Keep only rows where both axes parsed
    pairs = [(xv, yv, cv) for xv, yv, cv in zip(x_raw, moment, companion_raw)
             if xv is not None and yv is not None]
    if not pairs:
        raise ValueError("no numeric data points")

    # M(T) scans are sorted so downstream code sees a monotonic x-axis.
    # M(H) loops are left in acquisition order - sorting would destroy the
    # hysteresis branches.
    if scan_type == SCAN_MT:
        pairs.sort(key=lambda p: p[0])

    x_values = [p[0] for p in pairs]
    y_values = [p[1] for p in pairs]
    companion_values = [p[2] for p in pairs]

    def _constant(values):
        """Mean of a column when it is effectively constant, else None."""
        clean = [v for v in values or [] if v is not None]
        if not clean:
            return None
        span = max(clean) - min(clean)
        scale = max(abs(max(clean)), abs(min(clean)), 1e-12)
        return float(np.mean(clean)) if span <= 0.01 * scale else None

    # Row-aligned companion axis, so field statistics can later be taken over
    # any temperature window rather than over the whole scan.
    has_companion = any(v is not None for v in companion_values)
    companion_kept = companion_values if has_companion else None

    return {
        'x': x_values,
        'y': y_values,
        'scan_type': scan_type,
        'x_label': X_LABEL_MT if scan_type == SCAN_MT else X_LABEL_MH,
        'y_label': Y_LABEL_MOMENT,
        'field_oe': _constant(field),
        'temperature_k': _constant(temperature),
        'field_series': companion_kept if scan_type == SCAN_MT else None,
        'temperature_series': companion_kept if scan_type == SCAN_MH else None,
        'field_stats': field_statistics(field),
        'metadata': metadata,
        'columns': columns,
    }


def field_statistics(values):
    """Mean, spread, min and max of a measured field column.

    The instrument records what the magnet actually did, which is not the
    nominal setpoint: a persistent-mode magnet drifts, and a nominal zero-field
    scan sits in whatever remanent field is trapped in the coil.  Reporting all
    four numbers is what lets the user see the difference.
    """
    clean = [float(v) for v in (values or []) if v is not None and np.isfinite(v)]
    if not clean:
        return None
    array = np.asarray(clean, dtype=float)
    return {
        'mean': float(np.mean(array)),
        'std': float(np.std(array)),
        'min': float(np.min(array)),
        'max': float(np.max(array)),
        'span': float(np.max(array) - np.min(array)),
        'n': int(array.size),
    }


def _infer_scan_type(temperature, field):
    """Decide M(T) vs M(H) from which axis actually sweeps."""
    def _relative_span(values):
        clean = [v for v in values or [] if v is not None]
        if len(clean) < 2:
            return 0.0
        span = max(clean) - min(clean)
        scale = max(abs(max(clean)), abs(min(clean)), 1e-12)
        return span / scale

    return SCAN_MH if _relative_span(field) > _relative_span(temperature) else SCAN_MT


def _parse_two_column(file_path, lines, metadata):
    """Bare ``x,y`` CSV/text export with no MPMS column names.

    The abscissa is read as a temperature unless the values span a range that
    only a field sweep produces (negative values, or thousands of Oe).
    """
    data = []
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith('#') or stripped.startswith('['):
            continue
        tokens = re.split(r'[\t;,\s]+', stripped)
        if len(tokens) < 2:
            continue
        try:
            data.append((float(tokens[0]), float(tokens[1])))
        except ValueError:
            continue  # header or comment row

    if not data:
        raise ValueError("no numeric two-column data found")

    x_values = [p[0] for p in data]
    is_field = min(x_values) < -1.0 or max(x_values) > 1000.0
    scan_type = SCAN_MH if is_field else SCAN_MT
    if scan_type == SCAN_MT:
        data.sort(key=lambda p: p[0])

    return {
        'x': [p[0] for p in data],
        'y': [p[1] for p in data],
        'scan_type': scan_type,
        'x_label': X_LABEL_MT if scan_type == SCAN_MT else X_LABEL_MH,
        'y_label': Y_LABEL_MOMENT,
        'field_oe': None,
        'temperature_k': None,
        'metadata': metadata,
        'columns': [],
    }


# ---------------------------------------------------------------------------
# Sheet construction
# ---------------------------------------------------------------------------

def next_squid_sheet_name(existing_names):
    """Return the next free SQUID sheet name: SQUID, SQUID1, SQUID2, ..."""
    existing = {str(name).upper() for name in existing_names}
    if 'SQUID' not in existing:
        return 'SQUID'
    idx = 1
    while f'SQUID{idx}' in existing:
        idx += 1
    return f'SQUID{idx}'


def _branch_from_filename(file_path):
    """Guess the measurement branch (ZFC / FC / MH) from the file name."""
    name = os.path.basename(file_path).upper()
    if 'ZFC' in name:
        return 'ZFC'
    if re.search(r'\bFC\d*\b', name) or name.startswith('FC'):
        return 'FC'
    if 'MH' in name or 'HYST' in name:
        return 'MH'
    return ''


def build_squid_sheet(parsed, file_path, sheet_name):
    """Assemble the ``window.Data['Core levels'][sheet]`` entry for one scan."""
    x_values = [float(v) for v in parsed['x']]
    y_values = [float(v) for v in parsed['y']]

    branch = _branch_from_filename(file_path)
    label_bits = [branch] if branch else []
    if parsed['scan_type'] == SCAN_MT and parsed['field_oe'] is not None:
        label_bits.append(f"{parsed['field_oe']:.0f} Oe")
    elif parsed['scan_type'] == SCAN_MH and parsed['temperature_k'] is not None:
        label_bits.append(f"{parsed['temperature_k']:.0f} K")
    label = ' '.join(label_bits) or os.path.splitext(os.path.basename(file_path))[0]

    # The Curie-Weiss fit range lives in the Background entry, which is what the
    # shared vline drag handler writes to. Default to the upper half of the
    # sweep - the paramagnetic regime, where Curie-Weiss actually applies.
    x_lo, x_hi = min(x_values), max(x_values)
    default_low = x_lo + 0.5 * (x_hi - x_lo)

    stats = parsed.get('field_stats') or {}
    field_series = parsed.get('field_series')
    temperature_series = parsed.get('temperature_series')

    return {
        'Name': sheet_name,
        'B.E.': x_values,
        'Raw Data': y_values,
        # The field the magnet actually produced, per point and summarised.
        # Kept separate from the nominal setpoint so the two can be compared.
        'SQUID_Field_Series': ([float(v) if v is not None else float('nan')
                                for v in field_series] if field_series else None),
        'SQUID_Temperature_Series': ([float(v) if v is not None else float('nan')
                                      for v in temperature_series]
                                     if temperature_series else None),
        'SQUID_Field_Mean': stats.get('mean'),
        'SQUID_Field_Std': stats.get('std'),
        'SQUID_Field_Min': stats.get('min'),
        'SQUID_Field_Max': stats.get('max'),
        'SQUID_Scan_Type': parsed['scan_type'],
        'SQUID_X_Label': parsed['x_label'],
        'SQUID_Y_Label': parsed['y_label'],
        'SQUID_Quantity': QTY_MOMENT,
        'SQUID_Label': label,
        'SQUID_Branch': branch,
        'SQUID_Field_Oe': parsed['field_oe'],
        'SQUID_Temperature_K': parsed['temperature_k'],
        'SQUID_Source': os.path.basename(file_path),
        'ExperimentalInfo': _experimental_info(parsed, file_path, len(x_values)),
        'Background': {
            'Bkg Y': list(y_values),
            'Bkg Type': '',
            'Bkg Low': float(default_low),
            'Bkg High': float(x_hi),
            'Bkg Offset Low': 0,
            'Bkg Offset High': 0,
        },
    }


def _experimental_info(parsed, file_path, n_points):
    """Human-readable acquisition summary shown in the info panel."""
    metadata = parsed.get('metadata', {})
    info = {
        'Technique': 'SQUID magnetometry',
        'Source File': os.path.basename(file_path),
        'Scan Type': ('Moment vs Temperature' if parsed['scan_type'] == SCAN_MT
                      else 'Moment vs Field'),
        'Number of Points': str(n_points),
    }
    if parsed['field_oe'] is not None:
        info['Applied Field (Oe)'] = f"{parsed['field_oe']:.4g}"
    if parsed['temperature_k'] is not None:
        info['Temperature (K)'] = f"{parsed['temperature_k']:.4g}"

    for src, dst in (('SAMPLE_MATERIAL', 'Sample Material'),
                     ('SAMPLE_COMMENT', 'Sample Comment'),
                     ('SAMPLE_MASS', 'Sample Mass (mg)'),
                     ('SAMPLE_MOLECULAR_WEIGHT', 'Molecular Weight (g/mol)'),
                     ('SAMPLE_HOLDER', 'Sample Holder'),
                     ('APPNAME', 'Instrument'),
                     ('FILEOPENTIME', 'Acquired')):
        value = metadata.get(src, '')
        if value:
            info[dst] = value
    return info



# ---------------------------------------------------------------------------
# Readers
# ---------------------------------------------------------------------------

def _core_levels(file_paths):
    """``_import_squid_paths`` up to the point it writes the project."""
    core_levels = {}
    skipped = []
    for file_path in sorted(file_paths):
        try:
            parsed = parse_squid_file(file_path)
        except Exception as e:
            skipped.append(f"{os.path.basename(file_path)}: {e}")
            continue
        sheet_name = next_squid_sheet_name(core_levels.keys())
        core_levels[sheet_name] = build_squid_sheet(parsed, file_path,
                                                    sheet_name)
    return fail_if_empty(core_levels, skipped, "SQUID data")


def read_dat(paths):
    return _core_levels(expand(paths, ('.dat',)))


def read_csv(paths):
    return _core_levels(expand(paths, ('.csv', '.txt')))


def sniff_mpms(path):
    """An MultiVu .dat: a ``[Header]`` block with INFO lines, then ``[Data]``."""
    text = head_text(path, 65536)
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    if not lines or lines[0].lower() != '[header]':
        return False
    upper = text.upper()
    return '[DATA]' in upper or ('INFO,' in upper and 'APPNAME' in upper)


def sniff_csv(path):
    """A CSV whose header row names an MPMS moment column and a temperature
    or field column ("Temperature (K)", "Moment (emu)" …)."""
    if not str(path).lower().endswith(('.csv', '.txt')):
        return False
    lines = head_text(path, 16384).splitlines()
    _header, columns, _rows = _split_header_and_rows(lines)
    normed = {_norm(c) for c in columns}
    has_moment = bool(normed & {'momentemu', 'longmomentemu',
                                'dcmomentfixedctremu', 'dcmomentfreectremu'})
    has_axis = bool(normed & {'temperaturek', 'sampletempk',
                              'magneticfieldoe', 'fieldoe'})
    return has_moment and has_axis


FORMATS = [
    Format("SQUID", "File(s) (.dat) - Quantum Design MPMS", (".dat",),
           read_dat, sniff=sniff_mpms, multi=True),
    Format("SQUID", "Multiple files (folder)", (".dat",), read_dat,
           sniff=lambda p: False, multi=True),
    Format("SQUID", "CSV file(s) (.csv/.txt)", (".csv", ".txt"), read_csv,
           sniff=sniff_csv, multi=True),
    Format("SQUID", "Multiple CSV files (folder)", (".csv", ".txt"),
           read_csv, sniff=lambda p: False, multi=True),
]
