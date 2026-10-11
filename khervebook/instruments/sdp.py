"""XPS International SDP (``.sdp``) binary import.

An SDP file (Spectral Data Processor v8, B. V. Crist) starts with the
magic ``XI SDP BINARY FILE`` and holds one or more spectra. Each spectrum
is found from its ``Binding Energy`` axis label: 112 bytes on come five
length-prefixed strings (original path, description, acquisition
parameters, date, source format), then a parameter block — BE start /
step / end, source energy, work function, pass energy, sweeps — and the
counts as float64. The sheet is named from the description ("C1s Scan"
-> "C1s"), else the file name, else the closest core level to the
scan's BE range (``identify_core_level_from_be``).

KherveFitting reads SDP only by drag and drop (its menu entry is
commented out, and it warns that the format is third-party and the data
not guaranteed); dropping several files makes one combined project, the
``multi`` format here.

Ported from KherveFittingPro ``libraries/FileMenu/SDP_Import.py``
(``parse_sdp_file``, ``identify_core_level_*``, ``_write_sheet``,
``_unique_sheet_name``, ``import_sdp_file``,
``import_multiple_sdp_files``), wx-free. The sheets go through
KherveFitting's intermediate workbook, replayed by `xlsxflow`.

Copyright (C) 2026 Gwilherm Kerherve

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.
"""

import os
import re
import struct

from . import Format
from . import xlsxflow

MAGIC = b'XI SDP BINARY FILE'
MAGIC_LEN = 18
BE_MARKER = b'Binding Energy'
BE_TO_META_STRINGS = 112
NUM_META_STRINGS = 5

OFF_BE_START = 0
OFF_BE_STEP = 8
OFF_BE_END = 16
OFF_Y_MIN = 24
OFF_Y_MAX = 32
OFF_SOURCE_E = 42
OFF_WORK_FN = 58
OFF_PASS_E = 66
OFF_SWEEPS = 74
OFF_FLAG = 90
OFF_DATA_COUNT = 94
OFF_DATA_START = 98

# (approximate BE, name): the primary line of each element
_CORE_LEVELS = [
    (14, "Hf4f"), (18, "Ga3d"), (22, "Ta4f"), (26, "Ge3d"), (31, "W4f"),
    (40, "Re4f"), (42, "As3d"), (49, "Mg2p"), (51, "Os4f"), (55, "Se3d"),
    (61, "Ir4f"), (69, "Br3d"), (71, "Pt4f"), (74, "Al2p"), (84, "Au4f"),
    (99, "Si2p"), (111, "Rb3d"), (118, "Tl4f"), (130, "P2p"),
    (134, "Sr3d"), (139, "Pb4f"), (142, "Gd4d"), (151, "Si2s"),
    (157, "Y3d"), (162, "S2p"), (170, "Bi4f"), (182, "Zr3d"),
    (189, "B1s"), (199, "Cl2p"), (207, "Nb3d"), (228, "Mo3d"),
    (232, "S2s"), (242, "Ar2p"), (280, "C1s"), (285, "C1s"),
    (293, "K2p"), (307, "Rh3d"), (334, "Pd3d"), (347, "Ca2p"),
    (368, "Ag3d"), (382, "U4f"), (399, "N1s"), (405, "Cd3d"),
    (412, "Sc2p"), (444, "In3d"), (459, "Ti2p"), (487, "Sn3d"),
    (517, "V2p"), (529, "O1s"), (532, "O1s"), (573, "Te3d"),
    (577, "Cr2p"), (619, "I3d"), (641, "Mn2p"), (686, "F1s"),
    (711, "Fe2p"), (726, "Cs3d"), (780, "Co2p"), (796, "Ba3d"),
    (836, "La3d"), (855, "Ni2p"), (883, "Ce3d"), (929, "Pr3d"),
    (933, "Cu2p"), (980, "Nd3d"), (1004, "Pm3d"), (1022, "Zn2p"),
    (1072, "Na1s"), (1083, "Sm3d"), (1117, "Ga2p"), (1126, "Eu3d"),
    (1186, "Gd3d"), (1220, "Tb3d"), (1296, "Dy3d"), (1351, "Ho3d"),
    (1409, "Er3d"), (1468, "Tm3d"),
]


def identify_core_level_from_be(be_start, be_end):
    """Survey (> 200 eV wide), VB (0–20 eV), or the nearest core level."""
    center = (be_start + be_end) / 2.0
    width = abs(be_start - be_end)
    if width > 200:
        return "Survey"
    if center <= 20 and width < 60:
        return "VB"
    best_name, best_dist = "Unknown", 999.0
    for be, name in _CORE_LEVELS:
        dist = abs(center - be)
        if dist < best_dist and dist < 30:
            best_dist, best_name = dist, name
    return best_name


def identify_core_level_from_description(desc):
    if not desc:
        return None
    match = re.match(r'^([A-Z][a-z]?\s*\d+[spdfgh]\d*)', desc)
    if match:
        return match.group(1).replace(' ', '')
    low = desc.lower().strip()
    if low.startswith(('survey', 'wide')):
        return 'Survey'
    if low.startswith(('vb', 'valence')):
        return 'VB'
    return None


_NAME_SUFFIXES = ['_Scan', '_scan', '_SCAN', ' Scan', ' scan',
                  '_Region', '_region', ' Region', ' region',
                  '_spe', '_SPE', '_txt', '_TXT', '_vgd', '_VGD',
                  '_vms', '_VMS', '_iso', '_ISO', '_mrs', '_MRS']

_SOURCE_SUFFIXES = ['_spe', '_SPE', '_txt', '_TXT', '_vgd', '_VGD',
                    '_vms', '_VMS', '_iso', '_ISO', '_mrs', '_MRS']


def _extract_core_level_from_filename(filename):
    if not filename:
        return None
    base = os.path.splitext(os.path.basename(filename))[0]
    for suffix in _NAME_SUFFIXES:
        if base.endswith(suffix):
            base = base[:-len(suffix)]
            break
    match = re.match(r'^([A-Z][a-z]?\s*\d+[spdfgh]\d*)', base)
    if match:
        return match.group(1).replace(' ', '')
    low = base.lower().strip()
    if low.startswith(('survey', 'wide')):
        return 'Survey'
    if low.startswith(('vb', 'valence')):
        return 'VB'
    return None


def extract_sample_name(filename):
    result = os.path.splitext(filename)[0]
    for suffix in _SOURCE_SUFFIXES:
        if result.endswith(suffix):
            result = result[:-len(suffix)]
            break
    return result.strip()


def _d(data, off):
    return struct.unpack('<d', data[off:off + 8])[0]


def parse_sdp_file(file_path):
    """``{'spectra': [...], 'metadata': {...}}`` of an SDP file."""
    with open(file_path, 'rb') as f:
        data = f.read()
    file_size = len(data)
    if len(data) < MAGIC_LEN or data[:MAGIC_LEN] != MAGIC:
        raise ValueError("not a valid SDP file: missing 'XI SDP BINARY "
                         "FILE' header")
    version = struct.unpack('<H', data[18:20])[0]
    num_declared = struct.unpack('<H', data[20:22])[0]

    be_offsets, pos = [], 0
    while True:
        pos = data.find(BE_MARKER, pos)
        if pos == -1:
            break
        be_offsets.append(pos)
        pos += 1
    if not be_offsets:
        raise ValueError("no spectrum data found in SDP file (no "
                         "'Binding Energy' markers)")

    spectra = []
    for be_off in be_offsets:
        off = be_off + BE_TO_META_STRINGS
        if off + 4 > file_size:
            continue
        meta, ok = [], True
        for _ in range(NUM_META_STRINGS):
            if off + 2 > file_size:
                ok = False
                break
            slen = struct.unpack('<H', data[off:off + 2])[0]
            if slen > 1000 or off + 2 + slen > file_size:
                ok = False
                break
            raw = data[off + 2:off + 2 + slen]
            meta.append(raw.split(b'\x00')[0]
                        .decode('ascii', errors='replace').strip())
            off += 2 + slen
        if not ok or len(meta) < NUM_META_STRINGS:
            continue

        base = off
        if base + OFF_DATA_START > file_size:
            continue
        try:
            be_start = _d(data, base + OFF_BE_START)
            be_step = _d(data, base + OFF_BE_STEP)
            be_end = _d(data, base + OFF_BE_END)
        except struct.error:
            continue
        if abs(be_start) > 5000 or abs(be_end) > 5000:
            continue
        if abs(be_step) > 100 or be_step == 0:
            continue
        try:
            source_energy = _d(data, base + OFF_SOURCE_E)
            work_fn = _d(data, base + OFF_WORK_FN)
            pass_energy = _d(data, base + OFF_PASS_E)
            sweeps = _d(data, base + OFF_SWEEPS)
        except struct.error:
            source_energy = 1486.68
            work_fn = pass_energy = sweeps = 0.0
        try:
            count = struct.unpack(
                '<I', data[base + OFF_DATA_COUNT:base + OFF_DATA_COUNT + 4])[0]
        except struct.error:
            continue
        start = base + OFF_DATA_START
        if count == 0 or count > 100000:
            continue
        if start + count * 8 > file_size:
            continue
        intensities = list(struct.unpack(f'<{count}d',
                                         data[start:start + count * 8]))
        if not intensities or all(v == 0 for v in intensities):
            continue
        valid = sum(1 for v in intensities if abs(v) < 1e12 and v == v)
        if valid < len(intensities) * 0.9:
            continue

        be_values = [be_start + i * be_step for i in range(count)]
        description = meta[1]
        core = identify_core_level_from_description(description)
        if core is None:
            core = _extract_core_level_from_filename(file_path)
        if core is None:
            core = identify_core_level_from_be(be_start, be_values[-1])
        if not (100 < source_energy < 5000):
            source_energy = 1486.68

        spectra.append({
            'be_start': be_start, 'be_step': be_step, 'be_end': be_end,
            'be_values': be_values, 'intensities': intensities,
            'num_points': count, 'core_level': core,
            'file_path': meta[0], 'description': description,
            'acq_params': meta[2], 'date': meta[3], 'format': meta[4],
            'source_energy': source_energy,
            'pass_energy': pass_energy if 0 < pass_energy < 1000 else None,
            'work_function': work_fn if 2.0 < work_fn < 8.0 else None,
            'sweeps': int(sweeps) if 0 < sweeps < 10000 else None,
        })

    if not spectra:
        raise ValueError("no valid spectrum data found in SDP file")

    sample_name = extract_sample_name(os.path.basename(file_path))
    first_desc = spectra[0].get('description', '')
    scan_label = re.compile(r'^[A-Z][a-z]?\d+[spdfgh]\d*\s+'
                            r'(Scan|Region|scan|region)', re.IGNORECASE)
    if first_desc:
        is_scan_label = bool(scan_label.match(first_desc))
        is_filename = (any(c in first_desc for c in ['\\', '/'])
                       or first_desc.endswith(('.txt', '.vms')))
        if not is_scan_label and not is_filename:
            sample_name = first_desc

    e0 = spectra[0]['source_energy']
    source_label = ("Al K-alpha Monochromated" if abs(e0 - 1486.68) < 0.5
                    else f"X-ray {e0:.2f} eV")
    return {'spectra': spectra,
            'metadata': {'file_path': file_path, 'sample_name': sample_name,
                         'version': version,
                         'num_spectra_declared': num_declared,
                         'num_spectra_actual': len(spectra),
                         'source_energy': spectra[0].get('source_energy',
                                                         1486.68),
                         'source_label': source_label,
                         'source_file': spectra[0].get('file_path', '')}}


def _basename(path):
    """``os.path.basename`` as on Windows, where KherveFitting runs: the
    stored source paths are Windows paths."""
    return re.split(r'[\\/]', path)[-1]


def _unique_sheet_name(core_level, sheet_names):
    if core_level not in sheet_names:
        return core_level
    counter = 1
    while f"{core_level}{counter}" in sheet_names:
        counter += 1
    return f"{core_level}{counter}"


def _write_sheet(ws, spec, meta, spec_idx, total):
    pairs = list(zip(spec['be_values'], spec['intensities']))
    ws.set_columns(['BE', 'Raw Data'], [round(b, 2) for b, _ in pairs],
                   [round(y, 2) for _, y in pairs])
    source_energy = spec.get('source_energy', 1486.68)
    info = {
        'Sample ID': meta['sample_name'],
        'Source File': _basename(meta.get('source_file', '')),
        'Original Path': spec.get('file_path', ''),
        'Description': spec.get('description', ''),
        'Date': spec.get('date', ''),
        'Technique': 'XPS',
        'Species & Transition': spec['core_level'],
        'Spectrum Index': str(spec_idx),
        'Total Spectra': str(total),
        'Source Label': meta.get('source_label', ''),
        'Source Energy': f"{source_energy:.2f}",
        'Pass Energy': (f"{spec['pass_energy']:.2f}"
                        if spec.get('pass_energy') else 'Unknown'),
        'Work Function': (f"{spec['work_function']:.2f}"
                          if spec.get('work_function') else 'Unknown'),
        'Sweeps': str(spec['sweeps']) if spec.get('sweeps') else 'Unknown',
        'Number of Points': str(spec['num_points']),
        'BE Start': f"{spec['be_start']:.2f}",
        'BE End': f"{spec['be_end']:.2f}",
        'BE Step': f"{abs(spec['be_step']):.4f}",
        'SDP Version': str(meta.get('version', '')),
    }
    ws.set_experimental([(k, str(v)) for k, v in info.items()])


def read_sdp(path):
    """SDP file (.sdp): every spectrum it holds."""
    parsed = parse_sdp_file(path)
    wb = xlsxflow.Workbook()
    names = []
    spectra = parsed['spectra']
    for idx, spec in enumerate(spectra):
        name = _unique_sheet_name(spec['core_level'], names)
        names.append(name)
        _write_sheet(wb.create_sheet(name), spec, parsed['metadata'], idx,
                     len(spectra))
    return xlsxflow.load_sheets(wb, names)


def read_sdp_many(paths):
    """Several SDP files as one project (KherveFitting's multi-drop)."""
    wb = xlsxflow.Workbook()
    names = []
    for path in paths:
        try:
            parsed = parse_sdp_file(path)
        except (OSError, ValueError, struct.error):
            continue
        spectra = parsed['spectra']
        for idx, spec in enumerate(spectra):
            name = _unique_sheet_name(spec['core_level'], names)
            names.append(name)
            _write_sheet(wb.create_sheet(name), spec, parsed['metadata'],
                         idx, len(spectra))
    if not names:
        raise ValueError("no SDP files could be processed")
    return xlsxflow.load_sheets(wb, names)


FORMATS = [
    Format("XPS", "SDP (.sdp)", (".sdp",), read_sdp, group="SDP"),
    Format("XPS", "SDP files (.sdp)", (".sdp",), read_sdp_many,
           group="SDP", multi=True, sniff=lambda p: False),
]
