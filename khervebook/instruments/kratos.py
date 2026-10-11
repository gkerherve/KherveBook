"""Kratos ``.kal`` XPS import.

A Kratos ``.kal`` is a text export of a Kratos/ESCApe acquisition: blocks
split on ``Dataset filename``, each with ``key = value`` metadata, an
``Ordinate values = {…}`` list of counts and the analyser's
``Transmission Function Object (ke,t)``. Every spectrum becomes one sheet:
binding energy from the kinetic-energy scan (Al Kα 1486.67 eV), counts
divided by the interpolated transmission.

Ported from KherveFittingPro ``libraries/FileMenu/Kal_Import.py``
(``parse_kal_file`` + ``build_kal_core_levels``), with the helpers it
borrows from ``Vamas_Import.py`` (``extract_transmission_data``,
``parse_casa_info_lines``) and ``Open.py`` (``normalize_sheet_name``),
wx-free. The Raman importer that shares that file is not here.

Copyright (C) 2026 Gwilherm Kerherve

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.
"""

import re

import numpy as np

from . import Format
from .kfitwrite import core_level

PHOTON_ENERGY = 1486.67

CASA_INFO_FIELDS = [
    'Casa Sample Name', 'Stage Position', 'Angle', 'FoV Position',
    'Lens Mode', 'Neutraliser', 'Charge Balance', 'Filament Current',
    'Filament Bias', 'Magnet Lens Trim Coil', 'Aperture', 'Iris Position',
]

# Metadata fields of every sheet's Experimental Description, in order.
KAL_FIELDS = [
    'Sample ID', 'Date', 'Time', 'Technique', 'Species & Transition',
    'Number of scans', 'Source Label', 'Source Energy', 'Source width X',
    'Source width Y', 'Pass Energy', 'Work Function', 'Analyzer Mode',
    'Sputtering Energy', 'Sputter Time', 'Sample Tilt',
    'Take-off Polar Angle', 'Take-off Azimuth',
    'Target Bias', 'Analysis Width X', 'Analysis Width Y', 'X Label',
    'X Units', 'X Start', 'X Step', 'Num Y Values', 'Num Scans',
    'Collection Time', 'Time Correction', 'Y Unit', '# Comment Lines',
    'Block Comment',
] + list(CASA_INFO_FIELDS)


# ---------------------------------------------------------------------------
# Shared helpers (ported from Vamas_Import.py / Open.py)
# ---------------------------------------------------------------------------

def parse_casa_info_lines(comment_text):
    """Kratos/Casa fields from a 'Casa Info Follows' comment block."""
    result = {k: '' for k in CASA_INFO_FIELDS}
    if not comment_text or 'Casa Info Follows' not in comment_text:
        return result

    tail = comment_text.split('Casa Info Follows', 1)[1]
    candidate_lines = [ln.strip() for ln in tail.split('\n')
                       if ln.strip()][:15]

    # Sample Name: first non-numeric, non-structured line.
    for ln in candidate_lines:
        try:
            float(ln)
            continue
        except ValueError:
            pass
        if ln.lower().startswith(('xps', 'aes', 'uhv')):
            break
        if ':' in ln or '(' in ln or '=' in ln or ln.startswith('FoV') \
                or ln.startswith('Aperture') or ln.startswith('Iris'):
            break
        result['Casa Sample Name'] = ln
        break

    for ln in candidate_lines:
        if ln.startswith('(') and 'Angle' in ln:
            paren_end = ln.find(')')
            if paren_end != -1:
                result['Stage Position'] = ln[:paren_end + 1]
            if 'Angle:' in ln:
                result['Angle'] = ln.split('Angle:', 1)[1].strip()
        elif ln.startswith('FoV Position'):
            result['FoV Position'] = ln.split('FoV Position', 1)[1].strip()
        elif ln.startswith('Lens Mode'):
            result['Lens Mode'] = (ln.split(':', 1)[1].strip()
                                   if ':' in ln else '')
        elif ln.startswith('Neutraliser'):
            result['Neutraliser'] = (ln.split(':', 1)[1].strip()
                                     if ':' in ln else '')
        elif ln.startswith('Charge Balance'):
            for part in ln.split(':'):
                if '=' not in part:
                    continue
                key, val = part.split('=', 1)
                key, val = key.strip(), val.strip()
                if key in result:
                    result[key] = val
        elif ln.startswith('Aperture Description'):
            result['Aperture'] = (ln.split(':', 1)[1].strip()
                                  if ':' in ln else '')
        elif ln.startswith('Iris Position Description'):
            result['Iris Position'] = (ln.split(':', 1)[1].strip().rstrip('.')
                                       if ':' in ln else '')
    return result


def extract_transmission_data(block):
    """(ke, transmission) arrays from a block's transmission function, or
    (None, None) when the block has none."""
    if 'Transmission Function Object (ke,t)' in block:
        trans_section = block.split(
            'Transmission Function Object (ke,t)')[1].split(
            'Dataset filename')[0]
        ke_line = trans_section.split(
            'Transmission Function Kinetic Energy =')[1].split('\n')[0]
        ke_str = ke_line.strip().strip('{}').strip()
        ke_trans = np.array([float(x.strip()) for x in ke_str.split(',')])

        val_line = trans_section.split(
            'Transmission Function Value          =')[1].split('\n')[0]
        val_str = val_line.strip().strip('{}').strip()
        trans_values = np.array([float(x.strip())
                                 for x in val_str.split(',')])
        return ke_trans, trans_values
    return None, None


def _interp_extrapolate(x, xp, fp):
    """scipy ``interp1d(xp, fp, kind='linear', bounds_error=False,
    fill_value='extrapolate')(x)`` in numpy: linear inside, the end
    segments' lines continued outside."""
    xp = np.asarray(xp, dtype=float)
    fp = np.asarray(fp, dtype=float)
    order = np.argsort(xp, kind='mergesort')
    xp, fp = xp[order], fp[order]
    x = np.asarray(x, dtype=float)
    if xp.size == 1:
        return np.full_like(x, fp[0])
    # The segment each x falls in (clipped to the first/last one), then
    # the straight line through it — exactly interp1d's evaluation.
    idx = np.clip(np.searchsorted(xp, x, side='left'), 1, xp.size - 1)
    lo, hi = idx - 1, idx
    x_lo, x_hi = xp[lo], xp[hi]
    y_lo, y_hi = fp[lo], fp[hi]
    slope = (y_hi - y_lo) / (x_hi - x_lo)
    return slope * (x - x_lo) + y_lo


def normalize_sheet_name(name):
    """KherveFitting's core-level name normalisation (``Open.py``)."""
    new_name = name
    lower_name = name.lower()
    if 'xps survey' in lower_name:
        new_name = 'Survey'
    elif 'survey' in lower_name:
        new_name = 'Survey'
    elif 'wide' in lower_name:
        new_name = 'Wide'
    elif 'su1s' in lower_name or '_su' in lower_name \
            or name.lower().endswith('_su'):
        new_name = 'Survey'
    elif any(term in lower_name for term in
             ['valence', 'valence band', 'valence scan', 'vb scan', 'vb',
              'valence band scan']):
        new_name = 'VB'
    elif any(term in lower_name for term in ['fermi', 'fermi scan']):
        new_name = 'Fermi'
    else:
        # "C 1s" -> "C1s"
        match = re.search(r'([A-Z][a-z]?)\s+(\d+[spdf])', name)
        if match:
            element, orbital = match.groups()
            new_name = f"{element}{orbital}"
        # "C1s Scan" -> "C1s"
        match = re.search(r'([A-Z][a-z]?\d+[spdf])', new_name)
        if match and len(new_name) > len(match.group(1)):
            new_name = match.group(1)

    # Preserve a sample-number suffix
    suffix_match = re.search(r'(\d+)$', name)
    if suffix_match and not re.search(r'\d+$', new_name):
        new_name = f"{new_name}{suffix_match.group(1)}"
    return new_name


# ---------------------------------------------------------------------------
# .kal
# ---------------------------------------------------------------------------

def _ordinate_string(block):
    return block.split('Ordinate values')[1].split('=')[1].split(
        '}')[0].strip().strip('{').strip()


def parse_kal_file(file_path):
    """One dict per spectrum: 'sample_id', 'name', 'id', 'metadata' and
    'data' (BE / Corrected Data / Raw Data / Transmission arrays).

    A spectrum without a transmission function is skipped, as in
    KherveFitting.
    """
    with open(file_path, 'r', encoding='utf-8', errors='replace') as f:
        content = f.read()

    blocks = content.split('Dataset filename')
    spectra = []

    # Kratos records the sample position once per position, not per region.
    current_sample_id = "Unknown"
    current_sample_tilt = ''

    for block in blocks:
        for line in block.split('\n'):
            if 'Stage Position Name' in line:
                current_sample_id = line.split('=')[1].strip()
            elif 'Stage X Rotation' in line:
                current_sample_tilt = line.split('=')[1].strip()

        if 'Ordinate values' not in block or 'Object name' not in block:
            continue

        object_name_line = next((line for line in block.split('\n')
                                 if 'Object name' in line), None)
        if not object_name_line:
            continue

        name_parts = object_name_line.split('=')[1].strip().split('/')
        name = name_parts[0].strip()
        spectrum_id = name_parts[1].strip() if len(name_parts) > 1 else ""

        if 'Sample Position' in name or 'Counter' in name:
            continue

        metadata = {
            'Sample ID': current_sample_id,
            'Date': '',
            'Time': '',
            'Technique': 'XPS',
            'Species & Transition': '',
            'Number of scans': '',
            'Source Label': 'Al mono',
            'Source Energy': '1486.6',
            'Source width X': '1E+37',
            'Source width Y': '1E+37',
            'Pass Energy': '',
            'Work Function': '1E+37',
            'Analyzer Mode': 'FAT',
            'Sputtering Energy': 'N/A',
            'Sputter Time': '',
            'Sample Tilt': current_sample_tilt,
            'Take-off Polar Angle': '1E+37',
            'Take-off Azimuth': '1E+37',
            'Target Bias': '1E+37',
            'Analysis Width X': '1E+37',
            'Analysis Width Y': '1E+37',
            'X Label': '',
            'X Units': '',
            'X Start': '',
            'X Step': '',
            'Num Y Values': '',
            'Num Scans': '',
            'Collection Time': '',
            'Time Correction': '1E+37',
            'Y Unit': 'd',
            '# Comment Lines': '0',
            'Block Comment': '',
        }

        for line in block.split('\n'):
            line = line.strip()
            if 'Date Acquired' in line:
                parts = line.split('=')[1].strip().split()
                if len(parts) >= 2:
                    metadata['Date'] = parts[0]
                    metadata['Time'] = parts[1]
            elif 'Chemical symbol or formula' in line:
                metadata['species'] = line.split('=')[1].strip()
            elif 'Transition or charge state' in line:
                metadata['transition'] = line.split('=')[1].strip()
            elif '# Sweeps completed' in line:
                num_scans = line.split('=')[1].strip()
                metadata['Number of scans'] = num_scans
                metadata['Num Scans'] = num_scans
            elif 'Pass energy' in line:
                metadata['Pass Energy'] = line.split('=')[1].strip()
            elif 'Abscissa label' in line:
                metadata['X Label'] = line.split('=')[1].strip()
            elif 'Abscissa units' in line:
                metadata['X Units'] = line.split('=')[1].strip()
            elif 'Spectrum scan start' in line:
                metadata['X Start'] = line.split('=')[1].split(
                    'eV')[0].strip()
            elif 'Spectrum scan step size' in line:
                metadata['X Step'] = line.split('=')[1].split(
                    'eV')[0].strip()
            elif 'Dwell time' in line:
                metadata['Collection Time'] = line.split('=')[1].replace(
                    'seconds', '').strip()

        if 'species' in metadata and 'transition' in metadata:
            metadata['Species & Transition'] = \
                f"{metadata['species']} {metadata['transition']}"
            metadata.pop('species')
            metadata.pop('transition')

        try:
            metadata['Num Y Values'] = str(
                len(_ordinate_string(block).split(',')))
        except Exception:
            pass

        comment_lines = []
        in_comment = False
        for line in block.split('\n'):
            if 'Casa Info Follows' in line:
                in_comment = True
                comment_lines.append(line.strip())
            elif in_comment and line.strip():
                comment_lines.append(line.strip())
        if comment_lines:
            metadata['# Comment Lines'] = str(len(comment_lines))
            metadata['Block Comment'] = '"' + '\n'.join(comment_lines) + '"'

        metadata.update(parse_casa_info_lines('\n'.join(comment_lines)))

        ke_trans, trans_values = extract_transmission_data(block)
        if ke_trans is not None and trans_values is not None:
            start_ke = float(metadata['X Start'])
            step = float(metadata['X Step'])
            raw_data = np.array([float(x.strip()) for x in
                                 _ordinate_string(block).split(',')])
            num_points = len(raw_data)
            ke_values = np.linspace(start_ke,
                                    start_ke + (num_points - 1) * step,
                                    num_points)
            be_values = PHOTON_ENERGY - ke_values
            transmission = _interp_extrapolate(ke_values, ke_trans,
                                               trans_values)
            corrected_data = raw_data / transmission
            spectra.append({
                'sample_id': current_sample_id,
                'name': name,
                'data': {'BE': be_values,
                         'Corrected Data': corrected_data,
                         'Raw Data': raw_data,
                         'Transmission': transmission},
                'metadata': metadata,
                'id': spectrum_id,
            })
    return spectra


def build_kal_core_levels(spectra):
    """{sheet: core level} for parsed .kal spectra, as KherveFitting builds
    them (sheet names normalised, repeats numbered ``C1s1``, ``C1s2``…)."""
    core_levels = {}
    for info in spectra:
        base = normalize_sheet_name(info['name'].replace(' ', ''))
        sheet_name = base
        if sheet_name in core_levels:
            count = 1
            while f"{base}{count}" in core_levels:
                count += 1
            sheet_name = f"{base}{count}"
        df = info['data']
        metadata = info['metadata']
        core_levels[sheet_name] = core_level(
            sheet_name,
            be_values=df['BE'],
            plot_values=df['Corrected Data'],
            raw_values=df['Raw Data'],
            transmission=df['Transmission'],
            experimental_info={f: metadata.get(f, '') for f in KAL_FIELDS},
        )
    return core_levels


def read_kal(path):
    """Kratos ``.kal`` -> {sheet: core level}."""
    try:
        spectra = parse_kal_file(path)
    except (IndexError, ValueError) as exc:
        raise ValueError(f"not a readable Kratos .kal file ({exc})") from exc
    if not spectra:
        raise ValueError("no Kratos spectra (with a transmission function) "
                         "found in this file")
    return build_kal_core_levels(spectra)


FORMATS = [
    Format(technique="XPS", group="Kratos", label="Kratos (.kal)",
           exts=(".kal",), read=read_kal),
]
