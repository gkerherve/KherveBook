"""EIS (electrochemical impedance spectroscopy) import.

Solartron/SMaRT "Exported SMaRT Impedance Data" CSVs, bare CSV/text
tables from any rig (columns matched by name: ``Frequency (Hz), Z'
(Ohm), Z'' (Ohm)``, ``freq,Zre,Zim``, ``f,|Z|,phase``…) and the binary
SMaRT ``.dat`` written beside the CSV. Each sweep becomes its own
Nyquist sheet — EIS, EIS1, EIS2, … — with x = Z', y = -Z'' and the full
trace kept in ``EIS_*`` keys (written losslessly to the .kfit).

Ported from KherveFittingPro (``libraries/FileMenu/EIS_Import.py``:
``parse_eis_file``, ``build_eis_sheet``, ``_import_eis_paths`` and the
folder import's .dat/.csv de-duplication), wx-free.

Copyright (C) 2026 Gwilherm Kerherve

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.
"""

import os
import re
import struct

import numpy as np

from . import Format
from .kfgeneric import as_list, fail_if_empty, head_text

X_LABEL_NYQUIST = "Z' (Ω)"
Y_LABEL_NYQUIST = "-Z'' (Ω)"
VIEW_NYQUIST = 'nyquist'        # -Z'' vs Z', the as-imported spectrum
PREFIX_NYQUIST = 'EIS'

# Delimiters tried, in order, when the file declares none.
_DELIMITERS = (',', ';', '\t')

# The binary SMaRT layout.  Offsets are into one record; the file is a plain
# stream of these behind _DAT_HEADER bytes of preamble.  Nothing in the file
# declares them, so they were read off a CSV/.dat pair of the same measurement.
_DAT_MAGIC = b'SMaRT_Data'
_DAT_HEADER = 62
_DAT_RECORD = 84
_DAT_DTYPE = np.dtype({
    'names': ['sweep', 'point', 'timestamp', 'frequency', 'ac_level',
              'dc_level', 'temperature_k', 'temperature_c', 'setpoint_k',
              'zreal', 'zimag'],
    'formats': ['<u2', '<u2', '<f8', '<f8', '<f8',
                '<f8', '<f8', '<f8', '<f8',
                '<f8', '<f8'],
    'offsets': [4, 6, 12, 20, 28, 36, 44, 52, 60, 68, 76],
    'itemsize': _DAT_RECORD,
})


# ---------------------------------------------------------------------------
# Column matching
# ---------------------------------------------------------------------------

def _norm(name):
    """Lower-case, strip punctuation - for tolerant column-header matching.

    Impedance headers are written every possible way (``Z'``, ``Zre``,
    ``Re(Z)``, ``Z real``), and the primes and brackets carry no information
    once the position is known, so they go.
    """
    return re.sub(r'[^a-z0-9]', '', str(name).lower())


def _find_column(headers, predicate):
    """Index of the first header for which ``predicate(normalised)`` is true."""
    for i, header in enumerate(headers):
        if predicate(_norm(header)):
            return i
    return None


def _is_real_header(h):
    """True for a normalised header naming the real part of the impedance."""
    if 'imag' in h or h.startswith('zim') or h.startswith('imz'):
        return False
    return (h.startswith('zreal') or h.startswith('zre') or
            h.startswith('rez') or h.startswith('realz') or
            h in ('z', 'zprime') or 'impedancereal' in h)


def _is_imag_header(h):
    """True for a normalised header naming the imaginary part."""
    return (h.startswith('zimag') or h.startswith('zim') or
            h.startswith('imz') or h.startswith('imagz') or
            h == 'zdoubleprime' or 'impedanceimag' in h)


def identify_columns(headers):
    """Map a column-name row onto the quantities the EIS tool understands.

    Returns a dict of name -> column index (or None), plus ``negated_imag``:
    True when the file already stores -Z'' (a header written ``-Z''``), so the
    values must not be negated a second time.
    """
    found = {
        'frequency': _find_column(
            headers, lambda h: h.startswith('freq') or h in ('f', 'fhz', 'hz')),
        'zreal': _find_column(headers, _is_real_header),
        'zimag': _find_column(headers, _is_imag_header),
        'zmod': _find_column(
            headers, lambda h: h.startswith('zmod') or h.startswith('zmag') or
            h in ('modz', 'absz', 'magnitude') or 'impedancemagnitude' in h),
        'phase': _find_column(headers, lambda h: h.startswith('phase') or
                              h in ('theta', 'deg', 'phasedeg')),
        'sweep': _find_column(headers, lambda h: h.startswith('sweep') or
                              h.startswith('cycle') or h.startswith('scan')),
        'temperature': _find_column(headers, lambda h: h.startswith('temp')),
        'time': _find_column(headers, lambda h: h.startswith('time')),
    }

    # A column headed "-Z'' (Ohm)" holds the already-negated value; treating it
    # as Z'' would flip every arc below the axis.
    found['negated_imag'] = False
    if found['zimag'] is not None:
        text = str(headers[found['zimag']]).strip()
        found['negated_imag'] = text.startswith('-') or text.startswith('−')

    return found


# ---------------------------------------------------------------------------
# CSV reading
# ---------------------------------------------------------------------------

def _read_lines(file_path):
    """Read an EIS export as text, tolerating the usual cp1252 degree signs."""
    for encoding in ('utf-8-sig', 'cp1252'):
        try:
            with open(file_path, 'r', encoding=encoding) as f:
                return f.read().splitlines()
        except UnicodeDecodeError:
            continue
    with open(file_path, 'r', errors='replace') as f:
        return f.read().splitlines()


def _pick_delimiter(lines):
    """Choose the field separator: the one appearing most on the data rows."""
    counts = {d: max((line.count(d) for line in lines[:200]), default=0)
              for d in _DELIMITERS}
    best = max(counts, key=counts.get)
    return best if counts[best] else ','


def _is_numeric_row(tokens):
    """True when the row's first two non-empty fields both parse as numbers."""
    numeric = [t for t in tokens[:3] if t.strip()]
    if len(numeric) < 2:
        return False
    try:
        float(numeric[0])
        float(numeric[1])
    except ValueError:
        return False
    return True


def split_metadata_and_table(lines, delimiter):
    """Split an EIS export into ``(metadata, column_names, data_rows)``.

    The table starts at the first row whose leading fields are numbers; the
    column names are the last non-empty row above it.  Everything above that is
    free-text metadata - the SMaRT export's title and start time, for instance.
    """
    first_data = None
    for i, line in enumerate(lines):
        if _is_numeric_row(line.split(delimiter)):
            first_data = i
            break

    if first_data is None:
        return {}, [], []

    header_row = None
    for i in range(first_data - 1, -1, -1):
        if lines[i].strip(delimiter + ' \t'):
            header_row = i
            break

    columns = []
    if header_row is not None:
        columns = [c.strip() for c in lines[header_row].lstrip('#').split(delimiter)]
        # A bare CSV starts at row 0 and its "header" is really the first point
        if _is_numeric_row(columns):
            columns = []
            header_row = None

    metadata = {}
    for line in lines[:header_row if header_row is not None else first_data]:
        if not line.strip():
            continue
        parts = [p.strip() for p in line.split(delimiter) if p.strip()]
        if len(parts) >= 2:
            metadata[parts[0].rstrip(':').strip()] = parts[1]
        elif ':' in parts[0]:
            key, _, value = parts[0].partition(':')
            if value.strip():
                metadata[key.strip()] = value.strip()

    rows = [line.split(delimiter) for line in lines[first_data:]
            if _is_numeric_row(line.split(delimiter))]
    return metadata, columns, rows


def _column(rows, index):
    """Extract one column as a numpy float array, NaN where unparseable."""
    out = np.full(len(rows), np.nan)
    if index is None:
        return out
    for i, row in enumerate(rows):
        if index < len(row):
            try:
                out[i] = float(row[index].strip())
            except ValueError:
                pass
    return out


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------

def _split_sweeps(sweep_column, n_rows):
    """Group row indices into sweeps.

    With a sweep/cycle column the grouping is read off it directly.  Without
    one - most bare CSVs - a repeat is detected from the frequency column by
    the caller, so here a missing column simply means one sweep.
    """
    if sweep_column is None or not np.isfinite(sweep_column).any():
        return [np.arange(n_rows)]

    groups, start = [], 0
    for i in range(1, n_rows):
        if sweep_column[i] != sweep_column[start]:
            groups.append(np.arange(start, i))
            start = i
    groups.append(np.arange(start, n_rows))
    return groups


def _split_on_frequency_restart(frequency):
    """Split a sweep-less table wherever the frequency sweep starts over.

    A rig that writes one long CSV for a whole loop marks each new spectrum
    only by going back to the top of the frequency list, so a step back
    *towards* the first frequency by more than a decade starts a new sweep.
    """
    n = frequency.size
    if n < 4:
        return [np.arange(n)]

    descending = frequency[0] > frequency[min(3, n - 1)]
    groups, start = [], 0
    for i in range(1, n):
        if not (np.isfinite(frequency[i]) and np.isfinite(frequency[i - 1])):
            continue
        went_back = (frequency[i] > frequency[i - 1] * 10.0 if descending
                     else frequency[i] < frequency[i - 1] / 10.0)
        if went_back:
            groups.append(np.arange(start, i))
            start = i
    groups.append(np.arange(start, n))
    return [g for g in groups if g.size >= 3] or [np.arange(n)]


def _sweep_dict(frequency, zreal, zimag, temperature, index, label_index):
    """One spectrum, cleaned of unusable points."""
    keep = (np.isfinite(frequency) & np.isfinite(zreal) & np.isfinite(zimag) &
            (frequency > 0))
    if keep.sum() < 3:
        return None

    temperature = temperature[keep] if temperature is not None else None
    mean_temperature = None
    if temperature is not None and np.isfinite(temperature).any():
        mean_temperature = float(np.nanmean(temperature))

    return {
        'frequency': frequency[keep],
        'zreal': zreal[keep],
        'zimag': zimag[keep],
        'temperature': temperature,
        'temperature_c': mean_temperature,
        'sweep': int(index) if index is not None else label_index + 1,
    }


def parse_eis_csv(file_path):
    """Parse an EIS CSV export into a list of sweep dicts.

    Each sweep carries ``frequency``, ``zreal``, ``zimag`` (all numpy arrays,
    Z'' signed as the instrument measured it), ``temperature_c`` and ``sweep``.

    Raises ``ValueError`` when the file holds no usable impedance table.
    """
    lines = _read_lines(file_path)
    delimiter = _pick_delimiter(lines)
    metadata, columns, rows = split_metadata_and_table(lines, delimiter)

    if not rows:
        raise ValueError("no numeric data rows found")

    if columns:
        found = identify_columns(columns)
    else:
        # Bare three-column export: frequency, Z', Z''
        found = {'frequency': 0, 'zreal': 1, 'zimag': 2, 'zmod': None,
                 'phase': None, 'sweep': None, 'temperature': None,
                 'time': None, 'negated_imag': False}

    if found['frequency'] is None:
        raise ValueError("no frequency column found")

    frequency = _column(rows, found['frequency'])

    if found['zreal'] is not None and found['zimag'] is not None:
        zreal = _column(rows, found['zreal'])
        zimag = _column(rows, found['zimag'])
        if found['negated_imag']:
            zimag = -zimag
        elif not columns:
            # A headerless three-column export says nothing about the sign
            # convention, and -Im(Z) is at least as common as Im(Z) - it is
            # what a DRT tool asks for.  A capacitive spectrum has Im(Z) < 0
            # nearly everywhere, so a third column that is mostly positive is
            # already negated and negating it again would put every arc below
            # the axis.
            finite = zimag[np.isfinite(zimag)]
            if finite.size and np.median(finite) > 0:
                zimag = -zimag
    elif found['zmod'] is not None and found['phase'] is not None:
        # Polar export: the phase is in degrees on every rig we have seen, but
        # a column that never leaves +-pi is radians.
        modulus = _column(rows, found['zmod'])
        phase = _column(rows, found['phase'])
        finite = phase[np.isfinite(phase)]
        radians = phase if (finite.size and np.nanmax(np.abs(finite)) <= 3.2) \
            else np.radians(phase)
        zreal = modulus * np.cos(radians)
        zimag = modulus * np.sin(radians)
    else:
        raise ValueError("no Z'/Z'' or |Z|/phase column pair found")

    temperature = (_column(rows, found['temperature'])
                   if found['temperature'] is not None else None)
    sweep_column = (_column(rows, found['sweep'])
                    if found['sweep'] is not None else None)

    if sweep_column is not None:
        groups = _split_sweeps(sweep_column, len(rows))
    else:
        groups = _split_on_frequency_restart(frequency)

    sweeps = []
    for i, group in enumerate(groups):
        index = (int(sweep_column[group[0]])
                 if sweep_column is not None and np.isfinite(sweep_column[group[0]])
                 else None)
        sweep = _sweep_dict(frequency[group], zreal[group], zimag[group],
                            temperature[group] if temperature is not None else None,
                            index, i)
        if sweep is not None:
            sweeps.append(sweep)

    if not sweeps:
        raise ValueError("no sweep held three or more usable points")

    for sweep in sweeps:
        sweep['metadata'] = metadata
    return sweeps


def parse_smart_dat(file_path):
    """Parse the binary SMaRT .dat companion of an impedance CSV.

    The record layout is undocumented; it was recovered from a .dat/.csv pair of
    the same run, and every field below reproduces its CSV column exactly.  The
    .dat is worth reading in preference to the CSV because it keeps full double
    precision, where the export rounds to seven significant figures.
    """
    with open(file_path, 'rb') as f:
        raw = f.read()

    if not raw.startswith(_DAT_MAGIC):
        raise ValueError("not a SMaRT binary impedance file")

    n_records = (len(raw) - _DAT_HEADER) // _DAT_RECORD
    if n_records < 3:
        raise ValueError("fewer than three impedance points")

    records = np.frombuffer(raw, dtype=_DAT_DTYPE, count=n_records,
                            offset=_DAT_HEADER)

    frequency = np.asarray(records['frequency'], dtype=float)
    zreal = np.asarray(records['zreal'], dtype=float)
    zimag = np.asarray(records['zimag'], dtype=float)
    temperature = np.asarray(records['temperature_c'], dtype=float)
    sweep_column = np.asarray(records['sweep'], dtype=float)

    sweeps = []
    for i, group in enumerate(_split_sweeps(sweep_column, n_records)):
        # The binary counts sweeps from zero where the CSV export counts from
        # one; match the export so the two agree sweep for sweep.
        sweep = _sweep_dict(frequency[group], zreal[group], zimag[group],
                            temperature[group], int(sweep_column[group[0]]) + 1, i)
        if sweep is not None:
            sweeps.append(sweep)

    if not sweeps:
        raise ValueError("no sweep held three or more usable points")

    # The trailing bytes after the last whole record hold no impedance point.
    for sweep in sweeps:
        sweep['metadata'] = {'Format': 'SMaRT binary (.dat)'}
    return sweeps


def parse_eis_file(file_path):
    """Parse any supported EIS file into a list of sweep dicts.

    The binary reader is tried first on a .dat, and a .dat that turns out to be
    text (some rigs use the extension for a tab-separated table) falls through
    to the CSV reader.
    """
    if os.path.splitext(file_path)[1].lower() == '.dat':
        try:
            return parse_smart_dat(file_path)
        except (ValueError, struct.error):
            pass
    return parse_eis_csv(file_path)


# ---------------------------------------------------------------------------
# Sheet construction
# ---------------------------------------------------------------------------

def next_eis_sheet_name(existing_names, prefix=PREFIX_NYQUIST):
    """The next free sheet name in one family: EIS, EIS1, EIS2, ...

    ``prefix`` picks the family - 'EIS' for a measured sweep, 'EIS~DRT' for a
    distribution of relaxation times, and so on.  Names are compared
    case-insensitively, as sheet names are throughout.
    """
    existing = {str(name).upper() for name in existing_names}
    if prefix.upper() not in existing:
        return prefix
    idx = 1
    while f'{prefix}{idx}'.upper() in existing:
        idx += 1
    return f'{prefix}{idx}'


def build_eis_sheet(sweep, file_path, sheet_name, n_sweeps=1):
    """Assemble the ``window.Data['Core levels'][sheet]`` entry for one sweep.

    The sheet is the Nyquist view: x = Z', y = -Z''.  Points stay in
    acquisition order (high frequency first) rather than being sorted by Z',
    because a Nyquist curve doubles back on itself whenever an inductive tail
    or a second arc overlaps, and sorting would zig-zag the line through it.
    """
    frequency = np.asarray(sweep['frequency'], dtype=float)
    zreal = np.asarray(sweep['zreal'], dtype=float)
    zimag = np.asarray(sweep['zimag'], dtype=float)

    x_values = [float(v) for v in zreal]
    y_values = [float(-v) for v in zimag]

    modulus = np.hypot(zreal, zimag)
    phase = np.degrees(np.arctan2(zimag, zreal))

    base = os.path.splitext(os.path.basename(file_path))[0]
    label = base if n_sweeps == 1 else f"{base} - sweep {sweep['sweep']}"
    if sweep.get('temperature_c') is not None:
        label += f" ({sweep['temperature_c']:.0f} °C)"

    # The selection range lives in the Background entry, which is what the
    # shared vline drag handler writes to. Default to the whole arc, since the
    # intercepts the tool measures are usually wanted across all of it.
    x_lo, x_hi = min(x_values), max(x_values)

    sheet = {
        'Name': sheet_name,
        'B.E.': x_values,
        'Raw Data': y_values,
        'EIS_View': VIEW_NYQUIST,
        'EIS_X_Label': X_LABEL_NYQUIST,
        'EIS_Y_Label': Y_LABEL_NYQUIST,
        'EIS_Label': label,
        'EIS_Sweep': int(sweep['sweep']),
        'EIS_Source': os.path.basename(file_path),
        'ExperimentalInfo': _experimental_info(sweep, file_path, len(x_values)),
        'Background': {
            'Bkg Y': list(y_values),
            'Bkg Type': '',
            'Bkg Low': float(x_lo),
            'Bkg High': float(x_hi),
            'Bkg Offset Low': 0,
            'Bkg Offset High': 0,
        },
    }

    if sweep.get('temperature_c') is not None:
        sheet['EIS_Temperature_C'] = float(sweep['temperature_c'])

    # Every trace is kept row for row alongside the two on the axes: the tool
    # needs the frequency to label the intercepts and to fit an equivalent
    # circuit, and the Bode view is derived from these.  Keys are prefixed EIS_
    # so KFitting_IO stores them losslessly - one sweep spans milliohms to
    # megaohms and hertz to megahertz, and the .json rounding would flatten both.
    sheet['EIS_Frequency'] = [float(v) for v in frequency]
    sheet['EIS_Zreal'] = x_values
    sheet['EIS_Zimag'] = [float(v) for v in zimag]
    sheet['EIS_Zmod'] = [float(v) for v in modulus]
    sheet['EIS_Phase'] = [float(v) for v in phase]
    if sweep.get('temperature') is not None:
        sheet['EIS_Temperature'] = [float(v) for v in sweep['temperature']]

    return sheet


def _experimental_info(sweep, file_path, n_points):
    """Human-readable acquisition summary shown in the info panel."""
    frequency = np.asarray(sweep['frequency'], dtype=float)
    zreal = np.asarray(sweep['zreal'], dtype=float)

    info = {
        'Technique': 'EIS (impedance spectroscopy)',
        'Source File': os.path.basename(file_path),
        'Sweep': str(sweep['sweep']),
        'Number of Points': str(n_points),
        'Frequency Range (Hz)': f"{frequency.min():.4g} - {frequency.max():.4g}",
        "Z' Range (Ω)": f"{zreal.min():.4g} - {zreal.max():.4g}",
    }
    if sweep.get('temperature_c') is not None:
        info['Temperature (°C)'] = f"{sweep['temperature_c']:.2f}"

    for src, dst in (('Experiment start time', 'Acquired'),
                     ('Format', 'File Format'),
                     ('Instrument', 'Instrument'),
                     ('Sample', 'Sample')):
        for name, value in (sweep.get('metadata') or {}).items():
            if _norm(name) == _norm(src) and value:
                info[dst] = value
                break
    return info



# ---------------------------------------------------------------------------
# Readers
# ---------------------------------------------------------------------------

_EXTENSIONS = ('.csv', '.txt', '.dat', '.z')


def _core_levels(file_paths):
    """``_import_eis_paths`` up to the point it writes the project."""
    core_levels = {}
    skipped = []
    for file_path in sorted(file_paths):
        try:
            sweeps = parse_eis_file(file_path)
        except Exception as e:
            skipped.append(f"{os.path.basename(file_path)}: {e}")
            continue
        for sweep in sweeps:
            sheet_name = next_eis_sheet_name(core_levels.keys())
            core_levels[sheet_name] = build_eis_sheet(sweep, file_path,
                                                      sheet_name, len(sweeps))
    return fail_if_empty(core_levels, skipped, "EIS data")


def read_files(paths):
    """File(s): every chosen file, its sweeps as EIS, EIS1, …"""
    return _core_levels(as_list(paths))


def _folder_files(paths):
    """A folder's EIS files, with the .csv twin of a .dat dropped (the .dat
    keeps full precision). Plain files in *paths* are taken as the folder's
    listing."""
    found = []
    for p in as_list(paths):
        if os.path.isdir(p):
            found.extend(os.path.join(p, f) for f in os.listdir(p)
                         if f.lower().endswith(_EXTENSIONS))
        elif p.lower().endswith(_EXTENSIONS):
            found.append(p)
    found = sorted(found, key=os.path.basename)
    binaries = {os.path.splitext(os.path.basename(f))[0].lower()
                for f in found if f.lower().endswith('.dat')}
    found = [f for f in found if f.lower().endswith('.dat')
             or os.path.splitext(os.path.basename(f))[0].lower()
             not in binaries]
    if not found:
        raise ValueError("No .csv/.txt/.dat files found in the selected folder.")
    return found


def read_folder(paths):
    """Multiple files (folder): as above, .dat preferred over its .csv."""
    return _core_levels(_folder_files(paths))


def sniff(path):
    """A SMaRT binary, a SMaRT CSV export, or a table whose header names a
    frequency column and both impedance parts."""
    lower = str(path).lower()
    with open(path, 'rb') as fh:
        start = fh.read(len(_DAT_MAGIC))
    if lower.endswith('.dat') and start == _DAT_MAGIC:
        return True
    if lower.endswith('.z'):
        return True
    text = head_text(path)
    if 'smart impedance' in text.lower():
        return True
    lines = text.splitlines()[:60]
    delimiter = _pick_delimiter(lines)
    for i, line in enumerate(lines):
        if _is_numeric_row(line.split(delimiter)):
            header = next((lines[j] for j in range(i - 1, -1, -1)
                           if lines[j].strip(delimiter + ' \t')), None)
            if header is None:
                return False
            cols = [c.strip() for c in header.lstrip('#').split(delimiter)]
            found = identify_columns(cols)
            return (found['frequency'] is not None
                    and found['zreal'] is not None
                    and found['zimag'] is not None
                    and _norm(cols[found['zreal']]) != 'z')
    return False


FORMATS = [
    Format("EIS", "File(s) (.csv/.txt/.dat)", _EXTENSIONS, read_files,
           sniff=sniff, multi=True),
    Format("EIS", "Multiple files (folder)", _EXTENSIONS, read_folder,
           sniff=lambda p: False, multi=True),
]
