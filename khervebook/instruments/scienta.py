"""Scienta Omicron (SES) XPS import: plot and map ``.txt``, HDF5 ``.h5``.

A SES text export is an INI-like file — ``[Info]`` with ``Number of
Regions=``, then per region ``[Region n]`` (name, energy scale,
``Dimension 2`` = sweeps for a map), ``[Info n]`` (acquisition metadata)
and ``[Data n]`` (BE + one column per sweep). Each region becomes one
sheet named after its cleaned region name (``clean_region_name``: "C 1s
fast" -> "C1s", "Valence" -> "VB", "C KLL" -> "CKLL"), with the region
metadata as its Experimental Description.

A *map* file (several sweeps per region) and the Scienta HDF5 map are
imported the way KherveFitting's preview window does it with its default
button, "SUM & Import": every sweep averaged into one spectrum per
region, the proposed (cleaned) region names kept, and no ``~Map`` sheet
("Save Maps" is off by default). Binning, dropping sweeps and keeping the
2-D map need that window and are not offered here.

Ported from KherveFittingPro ``libraries/FileMenu/Scienta_Import.py``
(``parse_scienta_file``, ``parse_region``, ``clean_region_name``,
``parse_h5_scienta_file``, ``ScientaMapPreviewWindow.on_sum_sweeps``,
``finalize_scienta_import``, ``write_sheet_data``), wx-free. The sheets
go through KherveFitting's intermediate workbook, replayed by `xlsxflow`.

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


# ---------------------------------------------------------------------------
#  Names
# ---------------------------------------------------------------------------

_SUFFIXES = [
    '_fast2', '_fast', '_slow', '_quick', '_scan', '_Scan', '_SCAN',
    ' fast2', ' fast', ' slow', ' quick', ' scan', ' Scan', ' SCAN',
    '_region', '_Region', '_REGION', ' region', ' Region', ' REGION',
    '_spectrum', '_Spectrum', ' spectrum', ' Spectrum',
]

_AUGER = [
    r'([A-Z][a-z]?)\s*(KLL\d*)', r'([A-Z][a-z]?)\s*(LMM\d*)',
    r'([A-Z][a-z]?)\s*(MNN\d*)', r'([A-Z][a-z]?)\s*(MVV\d*)',
    r'([A-Z][a-z]?)\s*(MNV\d*)', r'([A-Z][a-z]?)\s*(NOO\d*)',
    r'([A-Z][a-z]?)\s*(KL\d+)', r'([A-Z][a-z]?)\s*(LM\d+)',
    r'([A-Z][a-z]?)\s*(MN\d+)',
]

_CORE = [
    r'^([A-Z][a-z]?)\s+(\d+[spdfgh])(\d*)$',
    r'^([A-Z][a-z]?)_(\d+[spdfgh])(\d*)$',
    r'^([A-Z][a-z]?)\s+(\d+[spdfgh])\s+(\d+)$',
    r'^([A-Z][a-z]?)_(\d+[spdfgh])_(\d+)$',
]


def clean_region_name(region_name):
    """``(clean name, is_special)`` for a Scienta region name."""
    name = region_name.strip()
    for suffix in _SUFFIXES:
        if name.endswith(suffix):
            name = name[:-len(suffix)]
            break
    name = name.strip()
    lower_name = name.lower()

    if any(x in lower_name for x in ['survey', 'wide scan', 'wide']):
        return ('Survey', True) if 'survey' in lower_name else ('Wide', True)
    if any(x in lower_name for x in ['valence band', 'valence_band',
                                     'valenceband', 'valence']):
        return 'VB', True
    if 'fermi' in lower_name:
        return 'Fermi', True

    for pattern in _AUGER:
        match = re.match(pattern, name, re.IGNORECASE)
        if match:
            return f"{match.group(1)}{match.group(2).upper()}", True

    for pattern in _CORE:
        match = re.match(pattern, name)
        if match:
            return f"{match.group(1)}{match.group(2)}", False

    match = re.match(r'^([A-Z][a-z]?\d+[spdfgh])(\d*)$', name)
    if match:
        return match.group(1), False

    base_match = re.match(r'^(.+?)(\d*)$', name)
    if base_match and base_match.group(1):
        return base_match.group(1).strip(), False
    return name, False


# ---------------------------------------------------------------------------
#  Text file
# ---------------------------------------------------------------------------

def _read_text(path):
    raw = open(path, 'rb').read()
    try:
        return raw.decode('utf-8')
    except UnicodeDecodeError:
        return raw.decode('latin-1')


def parse_region(lines, region_num):
    """One ``[Region n]`` / ``[Info n]`` / ``[Data n]`` group, or None."""
    region = {'name': '', 'be_values': None, 'sweeps': 1,
              'sweep_scale': None, 'data_2d': None, 'intensities': None,
              'metadata': {}}
    region_header = f'[Region {region_num}]'
    info_header = f'[Info {region_num}]'
    data_header = f'[Data {region_num}]'

    i = 0
    while i < len(lines):
        line = lines[i].strip()
        if line == region_header:
            i += 1
            while i < len(lines) and not lines[i].strip().startswith('['):
                rl = lines[i].strip()
                if rl.startswith('Region Name='):
                    region['name'] = rl.split('=')[1]
                elif rl.startswith('Dimension 1 size='):
                    region['dim1_size'] = int(rl.split('=')[1])
                elif rl.startswith('Dimension 1 scale='):
                    region['be_values'] = np.array(
                        [float(x) for x in rl.split('=')[1].split()])
                elif rl.startswith('Dimension 2 size='):
                    region['sweeps'] = int(rl.split('=')[1])
                elif rl.startswith('Dimension 2 scale='):
                    region['sweep_scale'] = np.array(
                        [int(x) for x in rl.split('=')[1].split()])
                i += 1
        elif line == info_header:
            i += 1
            while i < len(lines) and not lines[i].strip().startswith('['):
                il = lines[i].strip()
                if '=' in il:
                    key, value = il.split('=', 1)
                    region['metadata'][key] = value
                i += 1
        elif line == data_header:
            i += 1
            rows = []
            while (i < len(lines) and not lines[i].strip().startswith('[')
                   and lines[i].strip()):
                dl = lines[i].strip()
                if dl:
                    rows.append([float(x) for x in dl.split()])
                i += 1
            if rows:
                arr = np.array(rows)
                if arr.shape[1] == 2:
                    region['be_values'] = arr[:, 0]
                    region['intensities'] = arr[:, 1]
                    region['sweeps'] = 1
                else:
                    if region['be_values'] is None:
                        region['be_values'] = arr[:, 0]
                    region['data_2d'] = arr[:, 1:].T
        else:
            i += 1

    if region['data_2d'] is not None or region['intensities'] is not None:
        return region
    return None


def parse_scienta_file(file_path):
    """All regions of a SES ``.txt`` export."""
    lines = _read_text(file_path).split('\n')
    result = {'num_regions': 0, 'version': '', 'regions': [],
              'file_path': file_path, 'is_map': False}
    i = 0
    while i < len(lines):
        if lines[i].strip() == '[Info]':
            i += 1
            while i < len(lines) and not lines[i].strip().startswith('['):
                il = lines[i].strip()
                if il.startswith('Number of Regions='):
                    result['num_regions'] = int(il.split('=')[1])
                elif il.startswith('Version='):
                    result['version'] = il.split('=')[1]
                i += 1
            break
        i += 1

    for n in range(1, result['num_regions'] + 1):
        region = parse_region(lines, n)
        if region:
            result['regions'].append(region)
            if region.get('sweeps', 1) > 1 and \
                    region.get('data_2d') is not None:
                result['is_map'] = True
    return result


def _head(path, size=65536):
    with open(path, 'rb') as f:
        return f.read(size).decode('latin-1')


def _is_ses(text):
    return ('[Info]' in text and 'Number of Regions=' in text
            and '[Region 1]' in text)


def _is_map_text(text):
    return any(int(m) > 1 for m in
               re.findall(r'^\s*Dimension 2 size=\s*(\d+)', text, re.M))


def sniff_plot(path):
    text = _head(path)
    return _is_ses(text) and not _is_map_text(text)


def sniff_map(path):
    text = _head(path)
    return _is_ses(text) and _is_map_text(text)


# ---------------------------------------------------------------------------
#  Sheets (finalize_scienta_import / write_sheet_data)
# ---------------------------------------------------------------------------

def _experimental(region, sheet_name):
    be_values = region['be_values']
    md = region['metadata']
    info = {
        'Sample ID': md.get('Sample', ''),
        'Spectrum Name': md.get('Spectrum Name', ''),
        'Region Name': region['name'],
        'Instrument': md.get('Instrument', ''),
        'Location': md.get('Location', ''),
        'User': md.get('User', ''),
        'Date': md.get('Date', ''),
        'Time': md.get('Time', ''),
        'Technique': 'XPS',
        'Species & Transition': sheet_name,
        'Excitation Energy': md.get('Excitation Energy', ''),
        'Pass Energy': md.get('Pass Energy', ''),
        'Energy Scale': md.get('Energy Scale', ''),
        'Lens Mode': md.get('Lens Mode', ''),
        'Acquisition Mode': md.get('Acquisition Mode', ''),
        'Energy Step': md.get('Energy Step', ''),
        'Step Time': md.get('Step Time', ''),
        'Number of Points': str(len(be_values)),
        'BE Start': f"{be_values[0]:.2f}",
        'BE End': f"{be_values[-1]:.2f}",
    }
    if 'total_sweeps' in region:
        info['Total Sweeps in File'] = str(region.get('total_sweeps', 1))
    if 'num_sweeps_summed' in region:
        info['Sweeps Summed'] = str(region.get('num_sweeps_summed', 1))
    if region.get('dropped_sweeps'):
        info['Dropped Sweeps'] = ', '.join(map(str, region['dropped_sweeps']))
    return [(k, str(v)) for k, v in info.items()]


def finalize(regions):
    """``finalize_scienta_import`` (summed, no map sheets) -> levels."""
    wb = xlsxflow.Workbook()
    sheet_names = []
    for region in regions:
        sheet_base, _special = clean_region_name(region['name'])
        sheet_name = sheet_base
        counter = 1
        while sheet_name in sheet_names:
            sheet_name = f"{sheet_base}{counter}"
            counter += 1
        sheet_names.append(sheet_name)

        if region['intensities'] is None:
            raise ValueError(f"region {region['name']!r} has no spectrum")
        pairs = list(zip(region['be_values'], region['intensities']))
        ws = wb.create_sheet(sheet_name)
        ws.set_columns(['BE', 'Raw Data'],
                       [round(float(b), 2) for b, _ in pairs],
                       [round(float(y), 2) for _, y in pairs])
        ws.set_experimental(_experimental(region, sheet_name))
    if not sheet_names:
        raise ValueError("no regions with data")
    return xlsxflow.load_sheets(wb, sheet_names)


def _sum_regions(regions):
    """The preview window's "SUM & Import" with its proposed names."""
    out = []
    for region in regions:
        proposed, _ = clean_region_name(region['name'])
        name = (proposed or region['name']).strip() or region['name']
        if region.get('data_2d') is None:
            out.append({'name': name, 'be_values': region['be_values'],
                        'intensities': region['intensities'],
                        'metadata': region['metadata'],
                        'num_sweeps_summed': 1, 'total_sweeps': 1,
                        'dropped_sweeps': []})
            continue
        valid = list(range(region['sweeps']))
        data = region['data_2d'][valid, :]
        out.append({'name': name, 'be_values': region['be_values'],
                    'intensities': np.sum(data, axis=0) / len(valid),
                    'metadata': region['metadata'],
                    'num_sweeps_summed': len(valid),
                    'total_sweeps': region['sweeps'],
                    'dropped_sweeps': []})
    return out


def read_plot(path):
    """Scienta Omicron plot file (.txt): one spectrum per region."""
    text = _head(path)
    if not _is_ses(text):
        raise ValueError("not a Scienta SES text export (no [Info] / "
                         "[Region 1] header)")
    parsed = parse_scienta_file(path)
    if parsed['is_map']:
        raise ValueError("this file contains map data (multiple sweeps) — "
                         "import it as a Scienta Map file")
    regions = [{'name': r['name'], 'be_values': r['be_values'],
                'intensities': r['intensities'], 'metadata': r['metadata'],
                'num_sweeps_summed': 1, 'total_sweeps': 1,
                'dropped_sweeps': []} for r in parsed['regions']]
    return finalize(regions)


def read_map(path):
    """Scienta Omicron map file (.txt): sweeps averaged per region."""
    text = _head(path)
    if not _is_ses(text):
        raise ValueError("not a Scienta SES text export (no [Info] / "
                         "[Region 1] header)")
    parsed = parse_scienta_file(path)
    if not parsed['is_map']:
        raise ValueError("this file contains single-sweep data — import it "
                         "as a Scienta Plot file")
    return finalize(_sum_regions(parsed['regions']))


# ---------------------------------------------------------------------------
#  HDF5 map
# ---------------------------------------------------------------------------

def _h5str(v):
    v = v[()] if hasattr(v, 'shape') or hasattr(v, 'dtype') else v
    if isinstance(v, bytes):
        return v.decode('utf-8', errors='replace')
    return str(v)


def parse_h5_scienta_file(file_path):
    """The datasets of a Scienta Omicron HDF5 file, BE high -> low."""
    import h5py

    with h5py.File(file_path, 'r') as f:
        sd = f['acquisition/spectrum_definition']
        acq_mode = _h5str(sd['acquisition_mode'])
        energy_mode = _h5str(sd['energy_mode'])
        lens_mode = _h5str(sd['lens_mode_name'])
        pass_energy = float(sd['pass_energy'][()])
        dwell_time = float(sd['dwell_time'][()])
        acq_time = float(sd['acquisition_time'][()])
        element_set = _h5str(sd['element_set_name'])
        sl = f['acquisition/spectrum_log']
        start_time = _h5str(sl['start_time'])
        stop_time = _h5str(sl['stop_time'])
        name = _h5str(f['acquisition/spectrum']['name'])
        source_energy = float(
            f['instrument/analyser/excitation_source']['energy'][()])
        analyser = f['instrument/analyser']
        work_function = float(analyser['work_function'][()])
        instrument_model = _h5str(analyser['model'])

        grp = f['acquisition/spectrum/data']
        data_2d = grp['data'][()]
        x_axis = grp['x_axis'][()]
        y_axis = grp['y_axis'][()]
        label = grp['y_axis'].attrs.get('label', b'Y')
        y_label = label.decode() if isinstance(label, bytes) else str(label)
        units = grp['y_axis'].attrs.get('units', b'')
        y_unit = units.decode() if isinstance(units, bytes) else str(units)
        red = f['acquisition/spectrum/data_reduced_1d']
        data_1d = red['data'][()]

    ke_values = np.array(x_axis, dtype=float)
    be_values = source_energy - ke_values
    if be_values[0] < be_values[-1]:
        be_values = be_values[::-1]
        ke_values = ke_values[::-1]
        data_2d = data_2d[:, ::-1]
        data_1d = data_1d[::-1]

    return {'file_path': file_path, 'name': name,
            'element_set': element_set,
            'source_energy': round(source_energy, 4),
            'pass_energy': round(pass_energy, 2),
            'work_function': round(work_function, 4),
            'lens_mode': lens_mode, 'acq_mode': acq_mode,
            'energy_mode': energy_mode, 'dwell_time': dwell_time,
            'acq_time': acq_time, 'start_time': start_time,
            'stop_time': stop_time, 'instrument_model': instrument_model,
            'be_values': be_values, 'ke_values': ke_values,
            'y_axis': y_axis, 'y_label': y_label, 'y_unit': y_unit,
            'data_2d': np.array(data_2d, dtype=float),
            'data_1d': np.array(data_1d, dtype=float), 'is_map': True}


def sniff_h5(path):
    with open(path, 'rb') as f:
        if f.read(8) != b'\x89HDF\r\n\x1a\n':
            return False
    import h5py
    with h5py.File(path, 'r') as f:
        return ('acquisition/spectrum_definition' in f
                and 'instrument/analyser' in f
                and 'acquisition/spectrum/data' in f)


def _source_label(e):
    if abs(e - 21.218) < 0.05:
        return 'He I (UPS)'
    if abs(e - 40.814) < 0.05:
        return 'He II (UPS)'
    if abs(e - 1486.68) < 0.1:
        return 'Al K-alpha'
    if abs(e - 1253.6) < 0.1:
        return 'Mg K-alpha'
    return f"Photon {e:.3f} eV"


def read_h5(path):
    """Scienta HDF5 map (.h5): the Y positions averaged into one spectrum."""
    try:
        ok = sniff_h5(path)
    except OSError:
        ok = False
    if not ok:
        raise ValueError("not a Scienta Omicron HDF5 file (no acquisition/"
                         "spectrum_definition group)")
    h = parse_h5_scienta_file(path)
    base_name = os.path.splitext(os.path.basename(path))[0]
    n_y = h['data_2d'].shape[0]
    core, _ = clean_region_name(h['element_set'])
    if not core:
        core = base_name
    st = h['start_time']
    metadata = {
        'Sample': h['element_set'],
        'Spectrum Name': h['name'],
        'Instrument': h['instrument_model'],
        'Location': '', 'User': '',
        'Date': st[:10] if st else '',
        'Time': st[11:] if len(st) > 10 else '',
        'Technique': 'UPS' if h['source_energy'] < 100 else 'XPS',
        'Excitation Energy': f"{h['source_energy']:.3f}",
        'Source Label': _source_label(h['source_energy']),
        'Pass Energy': f"{h['pass_energy']:.2f}",
        'Work Function': f"{h['work_function']:.4f}",
        'Lens Mode': h['lens_mode'],
        'Acquisition Mode': h['acq_mode'],
        'Energy Mode': h['energy_mode'],
        'Energy Scale': 'Binding',
        'Energy Step': f"{abs(float(h['be_values'][1]) - float(h['be_values'][0])):.4f}",
        'Step Time': f"{h['dwell_time']:.4f}",
        'Start Time': st,
        'Stop Time': h['stop_time'],
        'Y Axis Label': h['y_label'],
        'Y Axis Unit': h['y_unit'],
        'Y Axis Start': f"{h['y_axis'][0]:.4f}",
        'Y Axis End': f"{h['y_axis'][-1]:.4f}",
        'Y Axis Points': str(n_y),
    }
    region = {'name': core, 'be_values': h['be_values'], 'sweeps': n_y,
              'data_2d': h['data_2d'], 'intensities': None,
              'metadata': metadata}
    return finalize(_sum_regions([region]))


FORMATS = [
    Format("XPS", "Scienta map file (.txt)", (".txt",), read_map,
           group="Scienta Omicron", sniff=sniff_map),
    Format("XPS", "Scienta plot file (.txt)", (".txt",), read_plot,
           group="Scienta Omicron", sniff=sniff_plot),
    Format("XPS", "Scienta HDF5 map (.h5)", (".h5", ".hdf5"), read_h5,
           group="Scienta Omicron", sniff=sniff_h5, needs=("h5py",)),
]
