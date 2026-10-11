"""Thermal analysis import: TGA / STA CSV, TA TRIOS DSC .tri, dilatometry.

Ported from KherveFittingPro (``libraries/FileMenu/TGA_Import.py``
``parse_tga_file`` / ``build_tga_sheet``, ``TRI_Import.py``
``parse_tri_file`` / ``build_dsc_sheet`` and ``DIL_Import.py``
``parse_dil_file`` / ``build_dil_sheet``), wx-free. TGA and DSC runs
become sheets TGA, TGA1… (the DSC .tri files share the TGA / DSC plot
mode, as in KherveFitting's TGA menu); dilatometer runs become DIL,
DIL1…. Every trace is kept under ``TGA_`` / ``DIL_`` keys, which the
``.kfit`` writer stores losslessly (DSC and dL/L0 signals are far below
the project's two-decimal rounding).

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

X_LABEL_TEMPERATURE = "Temperature (°C)"
X_LABEL_TIME = "Time (min)"
Y_LABEL_TEMPERATURE = "Temperature (°C)"
Y_LABEL_MASS_MG = "Mass (mg)"
Y_LABEL_MASS_PCT = "Mass (%)"
Y_LABEL_HEATFLOW = "Heat Flow (mW)"
Y_LABEL_STRAIN = "dL/L$_0$"
Y_LABEL_MICRON = "dL (µm)"

# How a TGA sheet is plotted, stored per sheet as 'TGA_View'.
VIEW_TIME = 'time'
VIEW_TEMPERATURE = 'temperature'

_DELIMITERS = (',', ';', '\t')
_TEXT_EXTS = ('.csv', '.txt', '.dat')


# ===========================================================================
#  TGA / STA CSV  (TGA_Import.py)
# ===========================================================================

def _norm(name):
    """Lower-case, strip punctuation - for tolerant column-header matching."""
    return re.sub(r'[^a-z0-9]', '', str(name).lower())


def _find_column(headers, predicate):
    for i, header in enumerate(headers):
        if predicate(_norm(header)):
            return i
    return None


def _mass_unit(header):
    text = str(header).lower()
    if '%' in text:
        return '%'
    if 'mg' in text:
        return 'mg'
    return None


def identify_columns(headers):
    """Map a column-name row onto temperature/time/mass/dsc/… indices."""
    found = {
        'temperature': _find_column(headers, lambda h: h.startswith('temp')),
        'time': _find_column(headers, lambda h: h.startswith('time')),
        'dsc': _find_column(headers, lambda h: h.startswith('dsc') or
                            h.startswith('heatflow') or h.startswith('hf')),
        'sensitivity': _find_column(headers,
                                    lambda h: h.startswith('sensit')),
        'segment': _find_column(headers, lambda h: h.startswith('segment')),
    }
    found['mass'] = _find_column(
        headers, lambda h: h.startswith('mass') or h.startswith('weight') or
        h == 'tg' or h.startswith('tgmg') or h.startswith('tg'))
    found['mass_unit'] = (_mass_unit(headers[found['mass']])
                          if found['mass'] is not None else None)
    return found


def _is_numeric_row(tokens):
    numeric = [t for t in tokens[:2] if t.strip()]
    if len(numeric) < 2:
        return False
    try:
        float(numeric[0])
        float(numeric[1])
    except ValueError:
        return False
    return True


def _pick_delimiter(lines):
    for line in lines:
        if line.upper().startswith('#SEPARATOR'):
            declared = line.split(',', 1)[-1].strip().upper()
            if declared.startswith('COMMA'):
                return ','
            if declared.startswith('SEMICOLON'):
                return ';'
            if declared.startswith('TAB'):
                return '\t'
    counts = {d: max((line.count(d) for line in lines[:200]), default=0)
              for d in _DELIMITERS}
    best = max(counts, key=counts.get)
    return best if counts[best] else ','


def split_metadata_and_table(lines, delimiter):
    """``(metadata, column_names, data_rows)`` of a NETZSCH-style export."""
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
        raw = lines[header_row].lstrip('#')
        columns = [c.strip() for c in raw.split(delimiter)]
        if _is_numeric_row(columns):
            columns = []
            header_row = None

    metadata = _parse_metadata(
        lines[:header_row if header_row is not None else first_data],
        delimiter)

    rows = []
    for line in lines[first_data:]:
        tokens = line.split(delimiter)
        if _is_numeric_row(tokens):
            rows.append(tokens)
    return metadata, columns, rows


def _parse_metadata(header_lines, delimiter):
    metadata = {}
    for line in header_lines:
        if not line.strip():
            continue
        parts = [p.strip() for p in line.split(delimiter)]
        key = parts[0].lstrip('#').rstrip(':').strip()
        value = next((p for p in parts[1:] if p), '')
        if key and value:
            metadata[key] = value
    return metadata


def _column(rows, index):
    out = []
    for row in rows:
        if index is None or index >= len(row):
            out.append(None)
            continue
        try:
            out.append(float(row[index].strip()))
        except ValueError:
            out.append(None)
    return out


def _metadata_float(metadata, *keys):
    for key in keys:
        for name, value in metadata.items():
            if _norm(name) == _norm(key):
                try:
                    return float(str(value).replace(',', '.'))
                except ValueError:
                    continue
    return None


def _pretty_dsc_label(header):
    """'DSC/(uV/mg)' -> 'DSC (µV/mg)'"""
    text = str(header).strip().replace('uV', 'µV')
    match = re.match(r'^([^/(]+)[/ ]*\(?([^)]*)\)?$', text)
    if match and match.group(2):
        return f"{match.group(1).strip()} ({match.group(2).strip()})"
    return text


def _read_lines(file_path):
    """NETZSCH writes cp1252 ('Temp./°C'), so UTF-8 first, then cp1252."""
    for encoding in ('utf-8-sig', 'cp1252'):
        try:
            with open(file_path, 'r', encoding=encoding) as f:
                return f.read().splitlines()
        except UnicodeDecodeError:
            continue
    with open(file_path, 'r', errors='replace') as f:
        return f.read().splitlines()


def parse_tga_file(file_path):
    """Parse a TGA/STA CSV export (see KherveFitting's TGA_Import)."""
    lines = _read_lines(file_path)
    delimiter = _pick_delimiter(lines)
    metadata, columns, rows = split_metadata_and_table(lines, delimiter)
    if not rows:
        raise ValueError("no numeric data rows found")

    if columns:
        found = identify_columns(columns)
    else:
        found = {'temperature': 0, 'mass': 1, 'time': None, 'dsc': None,
                 'sensitivity': None, 'segment': None, 'mass_unit': None}

    if found['temperature'] is None:
        found['temperature'] = 0
    if found['mass'] is None:
        raise ValueError("no mass / TG column found")

    temperature = _column(rows, found['temperature'])
    mass = _column(rows, found['mass'])
    time_min = (_column(rows, found['time'])
                if found['time'] is not None else None)
    dsc = _column(rows, found['dsc']) if found['dsc'] is not None else None
    sensitivity = (_column(rows, found['sensitivity'])
                   if found['sensitivity'] is not None else None)
    segment = (_column(rows, found['segment'])
               if found['segment'] is not None else None)

    keep = [i for i, (t, m) in enumerate(zip(temperature, mass))
            if t is not None and m is not None]
    if not keep:
        raise ValueError("no rows with both a temperature and a mass")

    def _select(values):
        if values is None:
            return None
        picked = [values[i] for i in keep]
        return picked if any(v is not None for v in picked) else None

    temperature = [temperature[i] for i in keep]
    mass = [mass[i] for i in keep]
    time_min = _select(time_min)
    dsc = _select(dsc)
    sensitivity = _select(sensitivity)
    segment = _select(segment)

    sample_mass_mg = _metadata_float(metadata, 'SAMPLE MASS /mg',
                                     'Sample mass', 'Sample Mass (mg)',
                                     'Mass', 'Initial mass')

    mass_unit = found.get('mass_unit')
    if mass_unit is None:
        mass_unit = '%' if (0 <= min(mass) and max(mass) <= 110 and
                            abs(mass[0] - 100.0) < 5.0) else 'mg'

    exo_flag = _metadata_float(metadata, 'EXO')
    exo_up = True if exo_flag is None else exo_flag != 0

    if mass_unit == '%':
        mass_pct = mass
        mass_mg = ([v * sample_mass_mg / 100.0 for v in mass]
                   if sample_mass_mg else None)
    else:
        mass_mg = mass
        reference = sample_mass_mg or mass[0]
        mass_pct = ([v * 100.0 / reference for v in mass]
                    if reference else None)
        if sample_mass_mg is None:
            sample_mass_mg = mass[0]

    return {
        'temperature': temperature,
        'mass_mg': mass_mg,
        'mass_pct': mass_pct,
        'time_min': time_min,
        'dsc': dsc,
        'sensitivity': sensitivity,
        'segment': segment,
        'dsc_unit': (_pretty_dsc_label(columns[found['dsc']])
                     if found['dsc'] is not None and columns
                     else 'DSC (µV/mg)'),
        'sample_mass_mg': sample_mass_mg,
        'exo_up': exo_up,
        'metadata': metadata,
        'columns': columns,
    }


def next_tga_sheet_name(existing_names):
    """Return the next free TGA sheet name: TGA, TGA1, TGA2, ..."""
    existing = {str(name).upper() for name in existing_names}
    if 'TGA' not in existing:
        return 'TGA'
    idx = 1
    while f'TGA{idx}' in existing:
        idx += 1
    return f'TGA{idx}'


def build_tga_sheet(parsed, file_path, sheet_name):
    """The core-level entry for one TGA run (time view when the file has a
    time column, else mass against temperature)."""
    time_min = parsed['time_min']
    temperature = [float(v) for v in parsed['temperature']]

    if parsed['mass_mg'] is not None:
        mass = [float(v) for v in parsed['mass_mg']]
        mass_label, mass_unit = Y_LABEL_MASS_MG, 'mg'
    else:
        mass = [float(v) for v in parsed['mass_pct']]
        mass_label, mass_unit = Y_LABEL_MASS_PCT, '%'

    if time_min is not None:
        view = VIEW_TIME
        x_values = [float(v) for v in time_min]
        y_values = temperature
        x_label, y_label, y_unit = X_LABEL_TIME, Y_LABEL_TEMPERATURE, '°C'
    else:
        view = VIEW_TEMPERATURE
        x_values = temperature
        y_values = mass
        x_label, y_label, y_unit = X_LABEL_TEMPERATURE, mass_label, mass_unit

    label = os.path.splitext(os.path.basename(file_path))[0]
    x_lo, x_hi = min(x_values), max(x_values)
    span = x_hi - x_lo

    sheet = {
        'Name': sheet_name,
        'B.E.': x_values,
        'Raw Data': y_values,
        'TGA_View': view,
        'TGA_X_Label': x_label,
        'TGA_Y_Label': y_label,
        'TGA_Y_Unit': y_unit,
        'TGA_Mass_Label': mass_label,
        'TGA_Mass_Unit': mass_unit,
        'TGA_Normalised': False,
        'TGA_Label': label,
        'TGA_Source': os.path.basename(file_path),
        'TGA_Sample_Mass_mg': parsed['sample_mass_mg'],
        'TGA_DSC_Unit': parsed['dsc_unit'],
        'TGA_Exo_Up': bool(parsed['exo_up']),
        'ExperimentalInfo': _tga_info(parsed, file_path, len(x_values)),
        'Background': {
            'Bkg Y': list(y_values),
            'Bkg Type': '',
            'Bkg Low': float(x_lo + 0.25 * span),
            'Bkg High': float(x_lo + 0.75 * span),
            'Bkg Offset Low': 0,
            'Bkg Offset High': 0,
        },
    }
    for key, values in (('TGA_Temperature', parsed['temperature']),
                        ('TGA_DSC', parsed['dsc']),
                        ('TGA_Time_min', parsed['time_min']),
                        ('TGA_Sensitivity', parsed['sensitivity']),
                        ('TGA_Segment', parsed['segment']),
                        ('TGA_Mass_mg', parsed['mass_mg']),
                        ('TGA_Mass_Pct', parsed['mass_pct'])):
        if values is not None:
            sheet[key] = [float(v) if v is not None else float('nan')
                          for v in values]
    return sheet


def _tga_info(parsed, file_path, n_points):
    metadata = parsed.get('metadata', {})
    temperature = parsed['temperature']
    info = {
        'Technique': 'TGA / STA',
        'Source File': os.path.basename(file_path),
        'Number of Points': str(n_points),
        'Temperature Range (°C)':
            f"{min(temperature):.1f} - {max(temperature):.1f}",
    }
    if parsed['sample_mass_mg']:
        info['Sample Mass (mg)'] = f"{parsed['sample_mass_mg']:g}"
    if parsed['dsc'] is not None:
        info['DSC Signal'] = parsed['dsc_unit']
    for src, dst in (('INSTRUMENT', 'Instrument'),
                     ('SAMPLE', 'Sample'),
                     ('IDENTITY', 'Identity'),
                     ('MATERIAL', 'Material'),
                     ('DATE/TIME', 'Acquired'),
                     ('OPERATOR', 'Operator'),
                     ('LABORATORY', 'Laboratory'),
                     ('TYPE OF CRUCIBLE', 'Crucible'),
                     ('REFERENCE', 'Reference'),
                     ('RANGE', 'Programme'),
                     ('CORR. FILE', 'Correction File')):
        for name, value in metadata.items():
            if _norm(name) == _norm(src) and value:
                info[dst] = value
                break
    return info


# ===========================================================================
#  TA TRIOS DSC .tri  (TRI_Import.py)
# ===========================================================================

# TRIOS stores heat flow in W; DSC is read in mW.
_HEATFLOW_W_TO_MW = 1000.0
# Bytes between two consecutive signal arrays inside one segment.
_HEADER_GAP = 68
# The raw signal block sits ahead of the analysis objects.
_ANALYSIS_MARKER = b'ProgramData\\TA Instruments\\TRIOS'


def _read_7bit(data, pos):
    """A .NET BinaryReader 7-bit-encoded length -> (value, pos)."""
    result = 0
    shift = 0
    while True:
        b = data[pos]
        pos += 1
        result |= (b & 0x7F) << shift
        if not (b & 0x80):
            break
        shift += 7
    return result, pos


def _read_string_after(data, key):
    p = data.find(key)
    if p < 0:
        return None
    try:
        ln, pos = _read_7bit(data, p + len(key))
    except IndexError:
        return None
    if not (0 <= ln <= 4096) or pos + ln > len(data):
        return None
    return data[pos:pos + ln].decode('utf-8', 'replace')


def _walk_header_strings(data, max_tokens=200):
    start = data.find(b'instrumenttype')
    if start < 0:
        return []
    pos = max(0, start - 1)
    tokens = []
    for _ in range(max_tokens):
        try:
            ln, p = _read_7bit(data, pos)
        except IndexError:
            break
        if not (0 <= ln <= 512) or p + ln > len(data):
            break
        chunk = data[p:p + ln]
        try:
            s = chunk.decode('utf-8')
        except UnicodeDecodeError:
            break
        if ln and not any(32 <= c < 127 for c in chunk):
            break
        tokens.append(s)
        pos = p + ln
    return tokens


def _tri_metadata(data):
    meta = {}
    for key in ('instrumenttype', 'instrumentname', 'instrumentserialnumber',
                'companyname', 'rundate', 'operator', 'project', 'samplename',
                'comments', 'pantype', 'procedurename'):
        value = _read_string_after(data, key.encode('ascii'))
        if value:
            meta[key] = value

    signals = _read_string_after(data, b'proceduresignals')
    meta['_signals'] = ([s.strip() for s in signals.split(';') if s.strip()]
                        if signals else [])

    segments = _read_string_after(data, b'proceduresegments')
    if segments:
        meta['proceduresegments'] = segments

    tokens = _walk_header_strings(data)
    pans = {}
    for i in range(len(tokens) - 1):
        if tokens[i] in ('samplepannumber', 'samplepannumberb',
                         'samplepannumberc'):
            pans[tokens[i]] = tokens[i + 1]
    meta['_pans'] = pans
    return meta


def _read_array_at(data, pos, exact_n=None):
    n = len(data)
    if pos + 4 > n:
        return None
    count = struct.unpack_from('<i', data, pos)[0]
    if exact_n is not None:
        if count != exact_n:
            return None
    elif not (2 <= count <= 5_000_000):
        return None
    end = pos + 4 + count * 4
    if end > n:
        return None
    arr = np.frombuffer(data, dtype='<f4', count=count, offset=pos + 4)
    if not np.all(np.isfinite(arr)) or np.max(np.abs(arr)) > 1e7:
        return None
    return arr


def _is_time_like(arr):
    if arr is None or arr.size < 50:
        return False
    d = np.diff(arr)
    if not np.all(d > 0):
        return False
    median = np.median(d)
    return median > 0 and bool(np.all(np.abs(d - median)
                                      < 0.5 * median + 1e-6))


def _read_signal_block(data, n_signals):
    """``(columns, seg_sizes)`` of the raw signal block, or None."""
    if n_signals < 2:
        return None

    marker = data.find(_ANALYSIS_MARKER)
    limit = marker if marker > 0 else len(data)

    anchor = None
    for pos in range(0, min(limit, 500_000)):
        arr = _read_array_at(data, pos)
        if arr is not None and abs(arr[0]) < 0.5 and _is_time_like(arr):
            anchor = pos
            break
    if anchor is None:
        return None

    columns = [[] for _ in range(n_signals)]
    seg_sizes = []
    pos = anchor
    seen = 0
    while pos is not None and pos < limit and seen < 10_000:
        time_arr = _read_array_at(data, pos)
        if not _is_time_like(time_arr):
            break
        count = time_arr.size
        stride = count * 4 + 4 + _HEADER_GAP

        seg = []
        for i in range(n_signals):
            arr = _read_array_at(data, pos + i * stride, exact_n=count)
            if arr is None:
                seg = None
                break
            seg.append(arr)
        if seg is None:
            break

        for i in range(n_signals):
            columns[i].append(seg[i])
        seg_sizes.append(count)
        seen += 1
        last_time = float(seg[0][-1])

        search_from = pos + n_signals * stride
        nxt = None
        for q in range(search_from, min(search_from + 400_000, limit)):
            candidate = _read_array_at(data, q)
            if _is_time_like(candidate) and abs(candidate[0] - last_time) < 5.0:
                nxt = q
                break
        pos = nxt

    if not seen:
        return None
    columns = [np.concatenate(col) if col else np.array([])
               for col in columns]
    return columns, seg_sizes


_SAMPLE_RE = re.compile(r'^(.*?)\s+([A-Z])$')


def _sample_channels(names):
    heatflow = {}
    temperature = {}
    for i, name in enumerate(names):
        low = name.lower()
        m = _SAMPLE_RE.match(name)
        letter = m.group(2) if m else ''
        if low.startswith('heat flow'):
            heatflow[letter] = i
        elif low.startswith('temperature') and letter:
            temperature[letter] = i

    shared_temp = None
    for i, name in enumerate(names):
        if name.lower() in ('temperature', 'sample temperature',
                            'tzero temperature'):
            shared_temp = i
            break

    channels = []
    for letter in sorted(heatflow):
        t_index = temperature.get(letter, shared_temp)
        if t_index is None:
            continue
        channels.append({'label': letter, 'temperature_index': t_index,
                         'heatflow_index': heatflow[letter]})
    return channels


def _time_index(names):
    for i, name in enumerate(names):
        if name.strip().lower() == 'time':
            return i
    return None


def parse_tri_file(file_path):
    """Parse a TA TRIOS ``.tri`` DSC file (see KherveFitting's TRI_Import)."""
    with open(file_path, 'rb') as f:
        data = f.read()

    meta = _tri_metadata(data)
    names = meta.get('_signals') or []
    if len(names) < 2:
        raise ValueError("no signal list in the file header")

    block = _read_signal_block(data, len(names))
    if block is None:
        raise ValueError("could not locate the raw signal block")
    columns, seg_sizes = block

    channels = _sample_channels(names)
    if not channels:
        raise ValueError("no Heat Flow / Temperature channel pair found")

    time_idx = _time_index(names)
    time_col = columns[time_idx] if time_idx is not None else None
    npoints = columns[channels[0]['heatflow_index']].size

    time_min = None
    if time_col is not None and time_col.size == npoints:
        time_min = [float(v) / 60.0 for v in time_col]

    segment = []
    for seg_id, size in enumerate(seg_sizes, start=1):
        segment.extend([seg_id] * size)
    if len(segment) != npoints:
        segment = None

    samples = []
    for ch in channels:
        temperature = columns[ch['temperature_index']]
        heat_flow = columns[ch['heatflow_index']]
        if temperature.size != npoints or heat_flow.size != npoints:
            continue
        samples.append({'label': ch['label'],
                        'temperature': [float(v) for v in temperature],
                        'heat_flow': [float(v) for v in heat_flow]})
    if not samples:
        raise ValueError("signal channels have mismatched lengths")

    return {'metadata': meta, 'time_min': time_min, 'segment': segment,
            'samples': samples, 'n_points': npoints}


def _sample_display_name(meta, label):
    base = (meta.get('samplename') or '').strip()
    pans = meta.get('_pans') or {}
    pan_key = {'A': 'samplepannumber', 'B': 'samplepannumberb',
               'C': 'samplepannumberc'}.get(label)
    pan = pans.get(pan_key) if pan_key else None
    parts = [p for p in (base, f"({label})" if label else '') if p]
    name = ' '.join(parts) if parts else (label or 'DSC')
    if pan:
        name += f" [pan {pan}]"
    return name


def build_dsc_sheet(parsed, sample, file_path, sheet_name):
    """The core-level entry for one DSC sample: heat flow vs temperature."""
    meta = parsed['metadata']
    temperature = sample['temperature']
    heat_flow = [v * _HEATFLOW_W_TO_MW for v in sample['heat_flow']]
    label = _sample_display_name(meta, sample['label'])

    x_lo, x_hi = min(temperature), max(temperature)
    span = x_hi - x_lo

    sheet = {
        'Name': sheet_name,
        'B.E.': list(temperature),
        'Raw Data': list(heat_flow),
        'TGA_View': VIEW_TEMPERATURE,
        'TGA_Signal_Kind': 'heatflow',
        'TGA_X_Label': X_LABEL_TEMPERATURE,
        'TGA_Y_Label': Y_LABEL_HEATFLOW,
        'TGA_Y_Unit': 'mW',
        'TGA_Mass_Label': Y_LABEL_HEATFLOW,
        'TGA_Mass_Unit': 'mW',
        'TGA_Normalised': False,
        'TGA_Label': label,
        'TGA_Source': os.path.basename(file_path),
        'TGA_Sample_Mass_mg': None,
        'TGA_DSC_Unit': 'Heat Flow (mW)',
        'TGA_HeatFlow_Unit': 'mW',
        'TGA_Exo_Up': True,
        'ExperimentalInfo': _dsc_info(parsed, sample, file_path),
        'Background': {
            'Bkg Y': list(heat_flow),
            'Bkg Type': '',
            'Bkg Low': float(x_lo + 0.25 * span),
            'Bkg High': float(x_lo + 0.75 * span),
            'Bkg Offset Low': 0,
            'Bkg Offset High': 0,
        },
    }
    sheet['TGA_Temperature'] = list(temperature)
    sheet['TGA_HeatFlow'] = list(heat_flow)
    if parsed['time_min'] is not None:
        sheet['TGA_Time_min'] = list(parsed['time_min'])
    if parsed.get('segment') is not None:
        sheet['TGA_Segment'] = [float(v) for v in parsed['segment']]
    return sheet


def _dsc_info(parsed, sample, file_path):
    meta = parsed['metadata']
    temperature = sample['temperature']
    info = {
        'Technique': 'DSC (TA TRIOS)',
        'Source File': os.path.basename(file_path),
        'Number of Points': str(parsed['n_points']),
        'Temperature Range (°C)':
            f"{min(temperature):.1f} - {max(temperature):.1f}",
        'Sample': _sample_display_name(meta, sample['label']),
    }
    for src, dst in (('instrumentname', 'Instrument'),
                     ('instrumentserialnumber', 'Serial'),
                     ('samplename', 'Material'),
                     ('rundate', 'Acquired'),
                     ('operator', 'Operator'),
                     ('companyname', 'Laboratory'),
                     ('pantype', 'Pan'),
                     ('proceduresegments', 'Programme')):
        value = meta.get(src)
        if value:
            info[dst] = value
    return info


# ===========================================================================
#  Dilatometry  (DIL_Import.py)
# ===========================================================================

def identify_dil_columns(headers):
    """temperature/time/length/segment indices plus ``length_unit``."""
    found = {
        'temperature': _find_column(headers, lambda h: h.startswith('temp')),
        'time': _find_column(headers, lambda h: h.startswith('time')),
        'segment': _find_column(headers, lambda h: h.startswith('segment')),
    }
    found['length'] = _find_column(
        headers, lambda h: h.startswith(('dllo', 'dll0', 'dl', 'deltal',
                                         'dimensionchange', 'strain',
                                         'shrinkage', 'expansion')))
    unit = None
    if found['length'] is not None:
        text = str(headers[found['length']]).lower()
        if 'lo' in text.replace(' ', '') or 'l0' in text.replace(' ', '') \
                or 'strain' in text:
            unit = 'rel'
        elif '%' in text:
            unit = 'percent'
        elif 'µm' in text or 'um' in text or 'micro' in text:
            unit = 'um'
        elif 'mm' in text:
            unit = 'mm'
    found['length_unit'] = unit
    return found


def parse_dil_file(file_path):
    """Parse a dilatometer CSV/TXT/DAT export (see DIL_Import)."""
    lines = _read_lines(file_path)
    delimiter = _pick_delimiter(lines)
    metadata, columns, rows = split_metadata_and_table(lines, delimiter)
    if not rows:
        raise ValueError("no numeric data rows found")

    if columns:
        found = identify_dil_columns(columns)
    else:
        found = {'temperature': 0, 'length': 1, 'time': None,
                 'segment': None, 'length_unit': None}

    if found['temperature'] is None:
        found['temperature'] = 0
    if found['length'] is None:
        raise ValueError("no dL/L0 / dL / strain column found")

    temperature = _column(rows, found['temperature'])
    length = _column(rows, found['length'])
    time_min = (_column(rows, found['time'])
                if found['time'] is not None else None)
    segment = (_column(rows, found['segment'])
               if found['segment'] is not None else None)

    keep = [i for i, (t, v) in enumerate(zip(temperature, length))
            if t is not None and v is not None]
    if not keep:
        raise ValueError("no rows with both a temperature and a length "
                         "change")

    def _select(values):
        if values is None:
            return None
        picked = [values[i] for i in keep]
        return picked if any(v is not None for v in picked) else None

    temperature = [temperature[i] for i in keep]
    length = [length[i] for i in keep]
    time_min = _select(time_min)
    segment = _select(segment)

    sample_length_mm = _metadata_float(
        metadata, 'SAMPLE LENGTH /mm', 'Sample length', 'Sample Length (mm)',
        'L0', 'Lo', 'Initial length')

    unit = found['length_unit']
    if unit is None:
        unit = 'rel' if max(abs(v) for v in length) < 0.5 else 'um'

    strain = None
    dl_um = None
    if unit == 'rel':
        strain = length
    elif unit == 'percent':
        strain = [v / 100.0 for v in length]
    elif unit == 'um':
        dl_um = length
        if sample_length_mm:
            strain = [v / (sample_length_mm * 1000.0) for v in length]
    elif unit == 'mm':
        dl_um = [v * 1000.0 for v in length]
        if sample_length_mm:
            strain = [v / sample_length_mm for v in length]

    return {'temperature': temperature, 'strain': strain, 'dl_um': dl_um,
            'time_min': time_min, 'segment': segment,
            'sample_length_mm': sample_length_mm, 'metadata': metadata,
            'columns': columns}


def next_dil_sheet_name(existing_names):
    """Return the next free DIL sheet name: DIL, DIL1, DIL2, ..."""
    existing = {str(name).upper() for name in existing_names}
    if 'DIL' not in existing:
        return 'DIL'
    idx = 1
    while f'DIL{idx}' in existing:
        idx += 1
    return f'DIL{idx}'


def build_dil_sheet(parsed, file_path, sheet_name):
    """The core-level entry for one run: dL/L0 (or dL) vs temperature."""
    temperature = [float(v) for v in parsed['temperature']]
    if parsed['strain'] is not None:
        y_values = [float(v) for v in parsed['strain']]
        y_label, y_unit = Y_LABEL_STRAIN, 'rel'
    else:
        y_values = [float(v) for v in parsed['dl_um']]
        y_label, y_unit = Y_LABEL_MICRON, 'um'

    label = os.path.splitext(os.path.basename(file_path))[0]
    sheet = {
        'Name': sheet_name,
        'B.E.': temperature,
        'Raw Data': y_values,
        'Fitting': {'Peaks': {}},
        'DIL_X_Label': X_LABEL_TEMPERATURE,
        'DIL_Y_Label': y_label,
        'DIL_Y_Unit': y_unit,
        'DIL_Label': label,
        'DIL_Source': os.path.basename(file_path),
        'DIL_Sample_Length_mm': parsed['sample_length_mm'],
        'ExperimentalInfo': _dil_info(parsed, file_path, len(temperature)),
        'Background': {
            'Bkg Y': list(y_values),
            'Bkg Type': '',
            'Bkg Low': float(min(temperature)),
            'Bkg High': float(max(temperature)),
            'Bkg Offset Low': 0,
            'Bkg Offset High': 0,
        },
    }
    for key, values in (('DIL_Temperature', parsed['temperature']),
                        ('DIL_Strain', parsed['strain']),
                        ('DIL_dL_um', parsed['dl_um']),
                        ('DIL_Time_min', parsed['time_min']),
                        ('DIL_Segment', parsed['segment'])):
        if values is not None:
            sheet[key] = [float(v) if v is not None else float('nan')
                          for v in values]
    return sheet


def _dil_info(parsed, file_path, n_points):
    metadata = parsed.get('metadata', {})
    temperature = parsed['temperature']
    info = {
        'Technique': 'Dilatometry',
        'Source File': os.path.basename(file_path),
        'Number of Points': str(n_points),
        'Temperature Range (°C)':
            f"{min(temperature):.1f} - {max(temperature):.1f}",
    }
    if parsed['sample_length_mm']:
        info['Sample Length (mm)'] = f"{parsed['sample_length_mm']:g}"
    for src, dst in (('INSTRUMENT', 'Instrument'),
                     ('SAMPLE', 'Sample'),
                     ('IDENTITY', 'Identity'),
                     ('MATERIAL', 'Material'),
                     ('MEASMODE', 'Measurement Mode'),
                     ('DATE/TIME', 'Acquired'),
                     ('OPERATOR', 'Operator'),
                     ('LABORATORY', 'Laboratory'),
                     ('GAS 1', 'Gas'),
                     ('RANGE', 'Programme'),
                     ('CORR. FILE', 'Correction File')):
        for name, value in metadata.items():
            if _norm(name) == _norm(src) and value:
                info[dst] = value
                break
    return info


# ===========================================================================
#  Readers
# ===========================================================================

def _expand(paths, exts):
    """Folders are listed (KherveFitting's folder import), then only *exts*
    are kept, sorted."""
    out = []
    for p in paths:
        p = str(p)
        if os.path.isdir(p):
            out += [os.path.join(p, f) for f in os.listdir(p)
                    if f.lower().endswith(exts)]
        elif p.lower().endswith(exts):
            out.append(p)
    return sorted(out)


def _import(file_paths, what, one_file):
    """The ``_import_*_paths`` loop: failing files are skipped, an empty
    result is an error. *one_file(path, taken)* -> [(name, sheet)]."""
    core_levels = {}
    skipped = []
    for file_path in sorted(str(p) for p in file_paths):
        try:
            sheets = one_file(file_path, core_levels)
        except Exception as e:
            skipped.append(f"{os.path.basename(file_path)}: {e}")
            continue
        core_levels.update(sheets)
    if not core_levels:
        raise ValueError(f"No valid {what} data found."
                         + ("\n" + "\n".join(skipped) if skipped else ""))
    return core_levels


def _tga_one(path, taken):
    parsed = parse_tga_file(path)
    name = next_tga_sheet_name(taken.keys())
    return {name: build_tga_sheet(parsed, path, name)}


def _tri_one(path, taken):
    parsed = parse_tri_file(path)
    out = {}
    for sample in parsed['samples']:
        name = next_tga_sheet_name(list(taken.keys()) + list(out))
        out[name] = build_dsc_sheet(parsed, sample, path, name)
    return out


def _dil_one(path, taken):
    parsed = parse_dil_file(path)
    name = next_dil_sheet_name(taken.keys())
    return {name: build_dil_sheet(parsed, path, name)}


def read_tga(path):
    return _import([path], "TGA", _tga_one)


def read_tga_folder(paths):
    files = _expand(paths, _TEXT_EXTS)
    if not files:
        raise ValueError("No .csv/.txt/.dat files found.")
    return _import(files, "TGA", _tga_one)


def read_tri(path):
    return _import([path], "DSC", _tri_one)


def read_tri_folder(paths):
    files = _expand(paths, ('.tri',))
    if not files:
        raise ValueError("No .tri files found.")
    return _import(files, "DSC", _tri_one)


def read_dil(path):
    return _import([path], "dilatometry", _dil_one)


def read_dil_folder(paths):
    files = _expand(paths, _TEXT_EXTS)
    if not files:
        raise ValueError("No .csv/.txt/.dat files found.")
    return _import(files, "dilatometry", _dil_one)


def _never(_path):
    return False


FORMATS = [
    Format("TGA", "File(s) (.csv/.txt/.dat)", _TEXT_EXTS, read_tga,
           sniff=_never),
    Format("TGA", "Multiple files (folder)", _TEXT_EXTS, read_tga_folder,
           sniff=_never, multi=True),
    Format("TGA", "TA TRIOS DSC file(s) (.tri)", (".tri",), read_tri),
    Format("TGA", "Multiple .tri files (folder)", (".tri",), read_tri_folder,
           sniff=_never, multi=True),
    Format("Dilatometry", "File(s) (.csv/.txt/.dat)", _TEXT_EXTS, read_dil,
           sniff=_never),
    Format("Dilatometry", "Multiple files (folder)", _TEXT_EXTS,
           read_dil_folder, sniff=_never, multi=True),
]
