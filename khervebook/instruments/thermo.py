"""Thermo Scientific XPS files: VGD, AVG and Avantage workbooks.

Ported from KherveFittingPro's ``libraries/FileMenu/VGD_Import.py``,
``AVG_Import.py`` and ``Avantage_Import.py`` (with the helpers they call:
``MRS_Import.extract_acquisition_parameters``, ``ConfigFile.
add_core_level_Data`` and the Smart background of ``Peak_Functions``),
wx-free. Each reader returns ``{sheet name: core level}`` — the same
dicts KherveFitting ends up with for that file:

* VGD (OLE2 binary) takes KherveFitting's direct-to-.kfit route: full
  precision, KE -> BE with the source energy, counts divided by
  periods x dwell time. An area scan gives a ``<core>~Map`` sheet (one
  ``Y<n>`` column per pixel) plus the ``<core>`` average spectrum.
* AVG (DataSpace text export) and Avantage (.xlsx/.xls) go through an
  intermediate workbook in KherveFitting, which is read back by
  ``add_core_level_Data``; that round trip (2-decimal rounding, sheet-name
  de-duplication, the Experimental Description column) is reproduced
  here without writing a file (see `thermo_avantage`, which also holds
  the Avantage reader — split out to keep both modules small).

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
from .kfitwrite import core_level as _core_level
from .thermo_avantage import (_sheet_core_level, _xl_title, read_avantage,
                              read_avantage_files, sniff_avantage)


def _source_label(source_energy):
    return ("Al K-alpha Monochromated" if abs(source_energy - 1486.68) < 0.1
            else f"X-ray {source_energy:.2f} eV")


# ---------------------------------------------------------------------------
# VGD — Thermo / VG Scienta binary (OLE2 compound file)
# ---------------------------------------------------------------------------

_PROP_STREAM = '\x05Q5nw4m3lIjudbfwyAayojlptCa'


def extract_vgd_core_level_name(filename):
    """'O1s Scan.VGD' -> 'O1s', 'Ni2p core level.VGD' -> 'Ni2p'."""
    base_name = os.path.splitext(filename)[0]
    suffixes = [
        '_Scan', '_scan', '_SCAN', ' Scan', ' scan', ' SCAN',
        '_Region', '_region', '_REGION', ' Region', ' region', ' REGION',
        '_core level', '_Core Level', '_Core level',
        ' core level', ' Core Level', ' Core level',
        '_spectrum', '_Spectrum', ' spectrum', ' Spectrum']
    result = base_name
    for suffix in suffixes:
        if result.endswith(suffix):
            result = result[:-len(suffix)]
            break
    match = re.match(r'^([A-Z][a-z]?\d+[spdfgh]\d*)[\s_]', result + ' ')
    if match:
        result = match.group(1)
    return result.strip()


def _meta_str(value):
    if not value:
        return ""
    if isinstance(value, bytes):
        value = value.decode("latin-1", "replace")
    return str(value).split('\x00')[0]


def parse_vgd_file(file_path):
    """Read a .vgd: intensities, KE axis and acquisition parameters."""
    import olefile
    if not olefile.isOleFile(str(file_path)):
        raise ValueError(f"{os.path.basename(str(file_path))} is not a VGD "
                         f"file (not an OLE2 compound document).")
    ole = olefile.OleFileIO(str(file_path))
    try:
        for stream in ('VGData', 'VGDataAxes', 'VGSpaceAxes', _PROP_STREAM):
            if not ole.exists(stream):
                raise ValueError(f"not a VGD file (no {stream!r} stream)")
        md = ole.get_metadata()
        metadata = {
            'title': _meta_str(md.title) if md.title else "Unknown",
            'subject': _meta_str(md.subject),
            'author': _meta_str(md.author),
            'create_time': str(md.create_time) if md.create_time else "",
            'saved_time': (str(md.last_saved_time)
                           if md.last_saved_time else ""),
        }
        return parse_vgd_streams(
            ole.openstream('VGData').read(),
            ole.openstream('VGDataAxes').read(),
            ole.openstream('VGSpaceAxes').read(),
            ole.openstream(_PROP_STREAM).read(),
            metadata)
    finally:
        ole.close()


def parse_vgd_streams(vgdata, data_axes, space_axes, prop_data, metadata):
    """The stream-decoding half of KherveFitting's ``parse_vgd_file``."""
    total_points = len(vgdata) // 8
    num_spectra = 1
    points_per_spectrum = total_points
    is_area_scan = False
    n_x = n_y = n_ke = None

    if len(data_axes) >= 8:
        ndims = struct.unpack('<i', data_axes[4:8])[0]
        if ndims == 3 and len(data_axes) >= 56:
            # Innermost first: KE points, X pixels, Y pixels.
            n_ke = struct.unpack('<i', data_axes[12:16])[0] + 1
            n_x = struct.unpack('<i', data_axes[28:32])[0] + 1
            n_y = struct.unpack('<i', data_axes[44:48])[0] + 1
            if n_ke * n_x * n_y == total_points:
                is_area_scan = True
                points_per_spectrum = n_ke
                num_spectra = n_x * n_y
        elif ndims <= 2 and len(data_axes) >= 32:
            dim1 = struct.unpack('<i', data_axes[12:16])[0] + 1
            dim2 = struct.unpack('<i', data_axes[28:32])[0] + 1
            if dim1 * dim2 == total_points and dim2 > 1:
                num_spectra = dim2
                points_per_spectrum = dim1

    all_intensities = np.frombuffer(vgdata[:total_points * 8],
                                    dtype='<f8').tolist()

    if is_area_scan:
        arr = np.array(all_intensities).reshape(n_y, n_x, n_ke)
        intensities = [arr[y, x, :].tolist()
                       for y in range(n_y) for x in range(n_x)]
    elif num_spectra > 1:
        intensities = [all_intensities[s * points_per_spectrum:
                                       (s + 1) * points_per_spectrum]
                       for s in range(num_spectra)]
    else:
        intensities = all_intensities

    ke_start = (struct.unpack('<d', space_axes[30:38])[0]
                if len(space_axes) >= 46 else None)
    ke_step = (struct.unpack('<d', space_axes[38:46])[0]
               if len(space_axes) >= 46 else None)

    x_start = x_step = y_start = y_step = None
    if is_area_scan and len(space_axes) >= 132:
        x_start = struct.unpack('<d', space_axes[73:81])[0]
        x_step = struct.unpack('<d', space_axes[81:89])[0]
        y_start = struct.unpack('<d', space_axes[116:124])[0]
        y_step = struct.unpack('<d', space_axes[124:132])[0]

    source_energy = None
    for i in range(0, len(prop_data) - 4, 4):
        val = struct.unpack('<f', prop_data[i:i + 4])[0]
        if 1480 < val < 1490:
            source_energy = val
            break
    if source_energy is None:
        source_energy = 1486.68

    pass_energy = pe_offset = None
    for i in range(0, len(prop_data) - 4, 4):
        val = struct.unpack('<f', prop_data[i:i + 4])[0]
        if val in [10.0, 20.0, 35.0, 50.0, 100.0, 160.0, 200.0]:
            pass_energy = val
            pe_offset = i
            break

    dwell_time = None
    if pe_offset is not None and pe_offset + 12 <= len(prop_data):
        dwell_time = struct.unpack('<f', prop_data[pe_offset + 8:
                                                   pe_offset + 12])[0]
        if not (0.001 < dwell_time < 10.0):
            dwell_time = None

    periods = None
    if pe_offset is not None and pe_offset >= 32:
        periods = struct.unpack('<i', prop_data[pe_offset - 32:
                                                pe_offset - 28])[0]
        if not (1 <= periods <= 1000):
            periods = None

    work_fn = None
    if pe_offset is not None and pe_offset + 20 <= len(prop_data):
        work_fn = struct.unpack('<f', prop_data[pe_offset + 16:
                                                pe_offset + 20])[0]
        if not (3.0 < work_fn < 6.0):
            work_fn = None

    # Transmission-function coefficients: floats 8 bytes apart, the first
    # ('a') typically 4.0-4.5.
    txf_coeffs = []
    for start in range(3100, min(3800, len(prop_data) - 32), 4):
        val = struct.unpack('<f', prop_data[start:start + 4])[0]
        if 4.0 < val < 4.5:
            vals, valid = [], True
            for j in range(4):
                off = start + j * 8
                if off + 4 <= len(prop_data):
                    vals.append(struct.unpack('<f',
                                              prop_data[off:off + 4])[0])
                else:
                    valid = False
                    break
            if valid and len(vals) == 4 and 0.5 < vals[1] < 1.0:
                txf_coeffs = vals
                break

    return {
        'intensities': intensities,
        'ke_start': ke_start,
        'ke_step': ke_step,
        'num_points': points_per_spectrum,
        'total_points': total_points,
        'num_spectra': num_spectra,
        'is_area_scan': is_area_scan,
        'n_x': n_x,
        'n_y': n_y,
        'x_start': x_start,
        'x_step': x_step,
        'y_start': y_start,
        'y_step': y_step,
        'source_energy': source_energy,
        'txf_coeffs': txf_coeffs,
        'pass_energy': pass_energy,
        'work_fn': work_fn,
        'dwell_time': dwell_time,
        'periods': periods,
        'metadata': dict(metadata),
    }


def calculate_vgd_data(parsed_data, spectrum_index=0):
    """BE axis, counts/(periods x dwell) and the 'transmission' factor."""
    num_spectra = parsed_data.get('num_spectra', 1)
    if num_spectra > 1:
        intensities = parsed_data['intensities'][spectrum_index]
    else:
        intensities = parsed_data['intensities']

    ke_start = parsed_data['ke_start']
    ke_step = parsed_data['ke_step']
    num_points = parsed_data['num_points']
    source_energy = parsed_data['source_energy']
    if ke_start is None or ke_step is None:
        raise ValueError("VGD file has no kinetic-energy axis")
    if num_points < 1:
        raise ValueError("VGD file holds no data points")

    ke_values = [ke_start + i * ke_step for i in range(num_points)]
    be_values = [source_energy - ke for ke in ke_values]
    be_start, be_end = be_values[0], be_values[-1]
    be_step = (be_end - be_start) / (num_points - 1) if num_points > 1 else 0

    dwell_time = parsed_data.get('dwell_time')
    periods = parsed_data.get('periods')
    txf_valid = True
    if dwell_time and periods and dwell_time > 0 and periods > 0:
        factor = periods * dwell_time
        corrected_data = [v / factor for v in intensities]
        transmission_values = [factor] * num_points
    else:
        corrected_data = list(intensities)
        transmission_values = [1.0] * num_points
        txf_valid = False

    return {
        'be_values': be_values,
        'ke_values': ke_values,
        'transmission_values': transmission_values,
        'corrected_data': corrected_data,
        'intensities': list(intensities),
        'be_start': be_start,
        'be_end': be_end,
        'be_step': be_step,
        'txf_valid': txf_valid,
    }


def vgd_spectrum_metadata(parsed_data, calc_data, core_level, base_name,
                          spectrum_idx, num_spectra, is_area_scan):
    meta = parsed_data['metadata']
    source_energy = parsed_data['source_energy']
    created = meta['create_time'].split() if meta['create_time'] else []
    saved = meta['saved_time'].split() if meta['saved_time'] else []
    p = parsed_data
    return {
        'Sample ID': meta['subject'] if meta['subject'] else base_name,
        'Title': meta['title'],
        'Author': meta['author'],
        'Date Created': created[0] if created else '',
        'Time Created': created[1] if len(created) > 1 else '',
        'Date Saved': saved[0] if saved else '',
        'Time Saved': saved[1] if len(saved) > 1 else '',
        'Technique': 'XPS',
        'Species & Transition': core_level,
        'Spectrum Index': str(spectrum_idx),
        'Total Spectra': str(num_spectra),
        'Area Scan': 'Yes' if is_area_scan else 'No',
        'Source Label': _source_label(source_energy),
        'Source Energy': f"{source_energy:.2f}",
        'Pass Energy': (f"{p['pass_energy']:.2f}" if p['pass_energy']
                        else 'Unknown'),
        'Work Function': f"{p['work_fn']:.2f}" if p['work_fn'] else 'Unknown',
        'Dwell Time': (f"{p['dwell_time']:.4f}" if p['dwell_time']
                       else 'Unknown'),
        'Periods': str(p['periods']) if p['periods'] else 'Unknown',
        'Number of Points': str(p['num_points']),
        'BE Start': f"{calc_data['be_start']:.2f}",
        'BE End': f"{calc_data['be_end']:.2f}",
        'BE Step': f"{abs(calc_data['be_step']):.4f}",
        'KE Start': f"{p['ke_start']:.2f}" if p['ke_start'] else 'Unknown',
        'KE Step': f"{p['ke_step']:.4f}" if p['ke_step'] else 'Unknown',
        'TXF Applied': 'Yes' if calc_data['txf_valid'] else 'No',
        'TXF Coefficients': (', '.join(f"{c:.6f}" for c in p['txf_coeffs'])
                             if p['txf_coeffs'] else 'N/A'),
    }


def vgd_map_pixel_data(parsed_data):
    """(first spectrum's calc, [n_pixels, n_ke] corrected intensities)."""
    first = calculate_vgd_data(parsed_data, 0)
    arr = np.asarray(parsed_data['intensities'], dtype=np.float64)
    dwell = parsed_data.get('dwell_time')
    periods = parsed_data.get('periods')
    if dwell and periods and dwell > 0 and periods > 0:
        arr = arr / (periods * dwell)
    return first, arr


def _vgd_unique_name(base, taken):
    """'C1s' -> 'C1s', 'C1s1', 'C1s2', ... (KherveFitting's VGD naming)."""
    if base not in taken:
        return base
    counter = 1
    while f"{base}{counter}" in taken:
        counter += 1
    return f"{base}{counter}"


def build_vgd_map_metadata(parsed_data, first_calc, core_level, base_name):
    meta = parsed_data['metadata']
    n_x, n_y = parsed_data['n_x'], parsed_data['n_y']
    x_step = parsed_data.get('x_step') or 0.0
    y_step = parsed_data.get('y_step') or 0.0
    source_energy = parsed_data['source_energy']
    return {
        'Sample ID': meta['subject'] if meta['subject'] else base_name,
        'Title': meta['title'],
        'Author': meta['author'],
        'Technique': 'XPS',
        'Core Level': core_level,
        'Map Kind': 'XY',
        'X Pixels': str(n_x),
        'Y Pixels': str(n_y),
        'X Step (um)': f"{x_step:.4f}",
        'Y Step (um)': f"{y_step:.4f}",
        'X Extent (um)': f"{(n_x - 1) * x_step:.2f}",
        'Y Extent (um)': f"{(n_y - 1) * y_step:.2f}",
        'Number of Sweeps': str(n_x * n_y),
        'Source Label': _source_label(source_energy),
        'Source Energy': f"{source_energy:.2f}",
        'Pass Energy': (f"{parsed_data['pass_energy']:.2f}"
                        if parsed_data['pass_energy'] else 'Unknown'),
        'Number of Points': str(parsed_data['num_points']),
        'BE Start': f"{first_calc['be_start']:.2f}",
        'BE End': f"{first_calc['be_end']:.2f}",
    }


def build_vgd_average_metadata(parsed_data, first_calc, core_level,
                               base_name, map_sheet_name, n_pixels):
    """No map keys on purpose: the average is a plain, fittable sheet."""
    meta = parsed_data['metadata']
    source_energy = parsed_data['source_energy']
    return {
        'Sample ID': meta['subject'] if meta['subject'] else base_name,
        'Title': meta['title'],
        'Author': meta['author'],
        'Technique': 'XPS',
        'Core Level': core_level,
        'Source Label': _source_label(source_energy),
        'Source Energy': f"{source_energy:.2f}",
        'Pass Energy': (f"{parsed_data['pass_energy']:.2f}"
                        if parsed_data['pass_energy'] else 'Unknown'),
        'Number of Points': str(parsed_data['num_points']),
        'BE Start': f"{first_calc['be_start']:.2f}",
        'BE End': f"{first_calc['be_end']:.2f}",
        'Source Map': map_sheet_name,
        'Description': f"Average of all {n_pixels} pixels of "
                       f"{map_sheet_name}",
    }


def build_vgd_spectrum_core_level(parsed_data, spectrum_idx, sheet_name,
                                  core_level, base_name, num_spectra,
                                  is_area_scan):
    calc = calculate_vgd_data(parsed_data, spectrum_idx)
    return _core_level(
        sheet_name,
        be_values=calc['be_values'],
        plot_values=calc['corrected_data'],
        raw_values=calc['intensities'],
        transmission=calc['transmission_values'],
        experimental_info=vgd_spectrum_metadata(
            parsed_data, calc, core_level, base_name, spectrum_idx,
            num_spectra, is_area_scan))


def build_vgd_xy_map_core_levels(parsed_data, core_level, base_name,
                                 existing_names):
    """'<core>~Map' (Y1..Yn pixel columns, p = y * n_x + x) + '<core>'
    average spectrum, for a 3-D area scan."""
    n_x, n_y = parsed_data['n_x'], parsed_data['n_y']
    n_pixels = n_x * n_y
    first, pixels = vgd_map_pixel_data(parsed_data)
    n = min(len(first['be_values']), pixels.shape[1])
    pixels = pixels[:, :n]
    be_values = [float(v) for v in first['be_values'][:n]]

    map_name = _vgd_unique_name(f"{core_level}~Map", existing_names)
    avg_name = _vgd_unique_name(core_level, set(existing_names) | {map_name})

    map_cl = {
        'Name': map_name,
        'B.E.': be_values,
        '_Map_type': 'vgd_xy',
        '_num_sweeps': n_pixels,
        '_core_level': core_level,
        '_n_x': n_x,
        '_n_y': n_y,
        '_x_step': float(parsed_data.get('x_step') or 0.0),
        '_y_step': float(parsed_data.get('y_step') or 0.0),
        'ExperimentalInfo': build_vgd_map_metadata(parsed_data, first,
                                                   core_level, base_name),
    }
    for p in range(n_pixels):
        map_cl[f'Y{p + 1}'] = pixels[p].tolist()
    if be_values:
        map_cl['Background'] = {
            'Bkg Type': '',
            'Bkg Low': float(min(be_values)),
            'Bkg High': float(max(be_values)),
            'Bkg Offset Low': 0,
            'Bkg Offset High': 0,
        }

    avg_cl = _core_level(
        avg_name, be_values=be_values, plot_values=pixels.mean(axis=0),
        experimental_info=build_vgd_average_metadata(
            parsed_data, first, core_level, base_name, map_name, n_pixels))
    return [(map_name, map_cl), (avg_name, avg_cl)]


def build_vgd_core_levels(parsed_data, core_level, base_name,
                          existing_names):
    """Every (name, core level) a single VGD file contributes."""
    num_spectra = parsed_data.get('num_spectra', 1)
    is_area_scan = parsed_data.get('is_area_scan', False)
    if is_area_scan:
        return build_vgd_xy_map_core_levels(parsed_data, core_level,
                                            base_name, existing_names)
    taken = set(existing_names)
    built = []
    for idx in range(num_spectra):
        sheet_name = _vgd_unique_name(core_level, taken)
        taken.add(sheet_name)
        built.append((sheet_name, build_vgd_spectrum_core_level(
            parsed_data, idx, sheet_name, core_level, base_name,
            num_spectra, is_area_scan)))
    return built


def _vgd_levels_into(levels, path):
    parsed = parse_vgd_file(path)
    fname = os.path.basename(str(path))
    base_name = os.path.splitext(fname)[0]
    meta = parsed['metadata']
    core_level = extract_vgd_core_level_name(fname)
    if (parsed.get('is_area_scan') and not core_level and meta['title']
            and meta['title'] != "Unknown"):
        core_level = meta['title'].replace(' ', '_')
    for name, cl in build_vgd_core_levels(parsed, core_level, base_name,
                                          list(levels)):
        levels[name] = cl


def read_vgd(path):
    """One .vgd -> its sheets (KherveFitting 'VGD file (.vgd)')."""
    levels = {}
    _vgd_levels_into(levels, path)
    return levels


def read_vgd_files(paths):
    """Several .vgd into one project (KherveFitting 'VGD Multiple files').
    A file that fails is skipped, as KherveFitting does."""
    levels, errors = {}, []
    for path in paths:
        try:
            _vgd_levels_into(levels, path)
        except ImportError:
            raise
        except Exception as exc:
            errors.append(f"{os.path.basename(str(path))}: {exc}")
    if not levels:
        raise ValueError("No VGD files could be processed"
                         + (f" ({'; '.join(errors)})" if errors else ""))
    return levels


# ---------------------------------------------------------------------------
# AVG — DataSpace ASCII export
# ---------------------------------------------------------------------------

def extract_avg_core_level_name(filename):
    """'Ti2p Snap.avg' -> 'Ti2p', 'O1s_Scan.avg' -> 'O1s'."""
    base_name = os.path.splitext(filename)[0]
    suffixes = [
        '_Snap', '_snap', '_SNAP', ' Snap', ' snap', ' SNAP',
        '_Scan', '_scan', '_SCAN', ' Scan', ' scan', ' SCAN',
        '_Region', '_region', '_REGION', ' Region', ' region', ' REGION',
        '_core level', '_Core Level', '_Core level',
        ' core level', ' Core Level', ' Core level',
        '_spectrum', '_Spectrum', ' spectrum', ' Spectrum']
    result = base_name
    for suffix in suffixes:
        if result.endswith(suffix):
            result = result[:-len(suffix)]
            break
    match = re.match(r'^([A-Z][a-z]?\d+[spdfgh]\d*)[\s_]', result + ' ')
    if match:
        result = match.group(1)
    return result.strip()


def _get_bstr(line):
    m = re.search(r"VT_BSTR\s*=\s*'([^']*)'", line)
    return m.group(1) if m else ''


def _get_r4(line):
    m = re.search(r'VT_R4\s*=\s*([\d.eE+\-]+)', line)
    return float(m.group(1)) if m else None


def _get_i4(line):
    m = re.search(r'VT_I4\s*=\s*(\d+)', line)
    return int(m.group(1)) if m else None


def _get_date(line):
    m = re.search(r'VT_DATE\s*=\s*(.+)', line)
    return m.group(1).strip() if m else ''


def parse_avg_file(file_path):
    """Header properties, energy axis, optional second axis, spectra."""
    with open(file_path, 'r', encoding='latin-1') as fh:
        lines = fh.readlines()

    metadata = {
        'title': '', 'subject': '', 'author': '', 'created': '', 'saved': '',
        'instrument': '', 'source_energy': 1486.68, 'pass_energy': None,
        'work_function': None, 'acq_time': None, 'periods': None,
        'txf_coeffs': [], 'lens_mode': '',
    }
    energy_axis = {'ke_start': None, 'ke_step': None, 'num_points': None}
    second_axis = None
    spectra = []
    current_spectrum = []
    in_data_block = False
    num_spectra_expected = 1
    txf_coeff_list = []

    for line in lines:
        s = line.rstrip()
        if 'DS_EXT_SUPROPID_TITLE' in s:
            metadata['title'] = _get_bstr(s)
        elif 'DS_EXT_SUPROPID_SUBJECT' in s:
            metadata['subject'] = _get_bstr(s)
        elif 'DS_EXT_SUPROPID_AUTHOR' in s:
            metadata['author'] = _get_bstr(s)
        elif 'DS_EXT_SUPROPID_CREATED' in s:
            metadata['created'] = _get_date(s)
        elif 'DS_EXT_SUPROPID_SAVED' in s:
            metadata['saved'] = _get_date(s)
        elif 'DS_GEPROPID_INSTRUMENT' in s:
            metadata['instrument'] = _get_bstr(s)
        elif 'DS_SOPROPID_ENERGY' in s:
            v = _get_r4(s)
            if v is not None:
                metadata['source_energy'] = v
        elif 'DS_ANPROPID_PASS' in s:
            v = _get_r4(s)
            if v is not None:
                metadata['pass_energy'] = v
        elif 'DS_ANPROPID_WORK_FTN' in s:
            v = _get_r4(s)
            if v is not None:
                metadata['work_function'] = v
        elif 'DS_ACPROPID_ACQ_TIME' in s:
            v = _get_r4(s)
            if v is not None:
                metadata['acq_time'] = v
        elif 'DS_ACPROPID_PERIODS' in s:
            v = _get_i4(s)
            if v is not None:
                metadata['periods'] = v
        elif 'DS_ANPROPID_LENS_MODE_NAME' in s:
            metadata['lens_mode'] = _get_bstr(s)
        elif 'DS_ANPROPID_TXFN_COEFF[' in s:
            v = _get_r4(s)
            if v is not None:
                txf_coeff_list.append(v)
        elif s.strip().startswith('$DATAAXES='):
            pass
        elif s.strip().startswith('$SPACEAXES='):
            pass
        elif re.match(r'\s+\d+=\s+[\d.\-]+,', s):
            # N= start, width, numPoints, axisType, linear, symbol, unit, label
            m = re.match(
                r'\s+(\d+)=\s+([\d.\-]+),\s+([\d.\-]+),\s+(\d+),\s+'
                r'(\w+),\s+\w+,\s+\'([^\']*)\',\s+\'([^\']*)\',\s+'
                r'\'([^\']*)\'', s)
            if m:
                if m.group(5) == 'ENERGY':
                    energy_axis['ke_start'] = float(m.group(2))
                    energy_axis['ke_step'] = float(m.group(3))
                    energy_axis['num_points'] = int(m.group(4))
                else:
                    num_spectra_expected = int(m.group(4))
                    second_axis = {'label': m.group(8), 'unit': m.group(7),
                                   'axis_type': m.group(5), 'values': []}
        elif s.startswith('$AXISVALUE=') and second_axis is not None:
            vm = re.search(r'VALUE=([\d.\-]+)', s)
            sm = re.search(r'SPACEAXIS=(\d+)', s)
            if vm and sm and int(sm.group(1)) == 1:
                second_axis['values'].append(float(vm.group(1)))
        elif s.startswith('$DATA='):
            if current_spectrum:
                spectra.append(current_spectrum)
            current_spectrum = []
            in_data_block = True
        elif in_data_block and s.startswith('LIST@'):
            parts = s.split('=', 1)
            if len(parts) == 2:
                for v in re.findall(r'[\d.\-+eE]+', parts[1]):
                    try:
                        current_spectrum.append(float(v))
                    except ValueError:
                        pass

    if current_spectrum:
        spectra.append(current_spectrum)
    metadata['txf_coeffs'] = txf_coeff_list
    if second_axis is None:
        num_spectra_expected = max(1, len(spectra))

    return {
        'metadata': metadata,
        'energy_axis': energy_axis,
        'second_axis': second_axis,
        'spectra': spectra,
        'num_spectra': len(spectra) if spectra else num_spectra_expected,
    }


def calculate_avg_data(parsed, spectrum_index=0):
    ea = parsed['energy_axis']
    meta = parsed['metadata']
    ke_start, ke_step = ea['ke_start'], ea['ke_step']
    num_points = ea['num_points']
    if ke_start is None or ke_step is None or not num_points:
        raise ValueError("AVG file has no ENERGY space axis")
    source_energy = meta['source_energy']

    raw = (parsed['spectra'][spectrum_index]
           if spectrum_index < len(parsed['spectra']) else [])
    raw = list(raw[:num_points])
    while len(raw) < num_points:
        raw.append(0.0)

    ke_values = [ke_start + i * ke_step for i in range(num_points)]
    be_values = [source_energy - ke for ke in ke_values]
    be_start, be_end = be_values[0], be_values[-1]
    be_step = (be_end - be_start) / (num_points - 1) if num_points > 1 else 0.0

    acq_time, periods = meta.get('acq_time'), meta.get('periods')
    if acq_time and periods and acq_time > 0 and periods > 0:
        factor = acq_time * periods
        corrected = [v / factor for v in raw]
        transmission = [factor] * num_points
        txf_valid = True
    else:
        corrected = list(raw)
        transmission = [1.0] * num_points
        txf_valid = False

    return {
        'be_values': be_values, 'ke_values': ke_values,
        'raw_intensities': raw, 'corrected_data': corrected,
        'transmission_values': transmission, 'be_start': be_start,
        'be_end': be_end, 'be_step': be_step, 'txf_valid': txf_valid,
    }


def avg_sheet_metadata(core_level, calc_data, parsed, spectrum_index,
                       base_name):
    """The Experimental Description block ``_write_sheet`` writes."""
    meta = parsed['metadata']
    ea = parsed['energy_axis']
    source_energy = meta['source_energy']
    created = meta['created'].split() if meta['created'] else []
    saved = meta['saved'].split() if meta['saved'] else []
    info = {
        'Sample ID': meta['subject'] if meta['subject'] else base_name,
        'Title': meta['title'],
        'Author': meta['author'],
        'Date Created': created[0] if created else '',
        'Time Created': created[1] if len(created) > 1 else '',
        'Date Saved': saved[0] if saved else '',
        'Time Saved': saved[1] if len(saved) > 1 else '',
        'Instrument': meta['instrument'],
        'Lens Mode': meta['lens_mode'],
        'Technique': 'XPS',
        'Species & Transition': core_level,
        'Spectrum Index': str(spectrum_index),
        'Total Spectra': str(parsed['num_spectra']),
        'Source Label': _source_label(source_energy),
        'Source Energy': f"{source_energy:.2f}",
        'Pass Energy': (f"{meta['pass_energy']:.2f}"
                        if meta['pass_energy'] is not None else 'Unknown'),
        'Work Function': (f"{meta['work_function']:.2f}"
                          if meta['work_function'] is not None
                          else 'Unknown'),
        'Acq Time (s)': (f"{meta['acq_time']:.4f}"
                         if meta['acq_time'] is not None else 'Unknown'),
        'Periods': (str(meta['periods']) if meta['periods'] is not None
                    else 'Unknown'),
        'Number of Points': str(ea['num_points']),
        'BE Start': f"{calc_data['be_start']:.2f}",
        'BE End': f"{calc_data['be_end']:.2f}",
        'BE Step': f"{abs(calc_data['be_step']):.4f}",
        'KE Start': (f"{ea['ke_start']:.2f}"
                     if ea['ke_start'] is not None else 'Unknown'),
        'KE Step': (f"{ea['ke_step']:.4f}"
                    if ea['ke_step'] is not None else 'Unknown'),
        'TXF Applied': 'Yes' if calc_data['txf_valid'] else 'No',
        'TXF Coefficients': (', '.join(f"{c:.6f}" for c in meta['txf_coeffs'])
                             if meta['txf_coeffs'] else 'N/A'),
    }
    second = parsed.get('second_axis')
    if second and spectrum_index < len(second['values']):
        info[f"{second['label']} ({second['unit']})"] = \
            f"{second['values'][spectrum_index]:.4f}"
    return info


def _avg_sheet(sheet_name, core_level, parsed, idx, base_name):
    calc = calculate_avg_data(parsed, idx)
    rows = [(round(be, 2), round(c, 2), round(r, 2), round(t, 2))
            for be, c, r, t in zip(calc['be_values'], calc['corrected_data'],
                                   calc['raw_intensities'],
                                   calc['transmission_values'])]
    info = avg_sheet_metadata(core_level, calc, parsed, idx, base_name)
    return _sheet_core_level(sheet_name, rows, list(info.items()))


def _check_avg(path, parsed):
    if parsed['energy_axis']['ke_start'] is None or not parsed['spectra']:
        raise ValueError(f"{os.path.basename(str(path))} is not a Thermo "
                         f"AVG file (no ENERGY axis or $DATA block).")


def read_avg(path):
    """One .avg -> a sheet per spectrum: Ti2p, Ti2p1, Ti2p2, ..."""
    fname = os.path.basename(str(path))
    base_name = os.path.splitext(fname)[0]
    core_level = extract_avg_core_level_name(fname)
    parsed = parse_avg_file(path)
    _check_avg(path, parsed)
    levels = {}
    for idx in range(parsed['num_spectra']):
        name = core_level if idx == 0 else f"{core_level}{idx}"
        name = _xl_title(list(levels), name)
        levels[name] = _avg_sheet(name, core_level, parsed, idx, base_name)
    return levels


def read_avg_files(paths):
    """Several .avg into one project (KherveFitting 'AVG Multiple files');
    a file that fails is skipped."""
    levels, errors = {}, []
    for path in paths:
        try:
            fname = os.path.basename(str(path))
            base_name = os.path.splitext(fname)[0]
            core_level = extract_avg_core_level_name(fname)
            parsed = parse_avg_file(path)
            _check_avg(path, parsed)
            for idx in range(parsed['num_spectra']):
                candidate = core_level if idx == 0 else f"{core_level}{idx}"
                if candidate not in levels:
                    name = candidate
                else:
                    counter = 1
                    while f"{core_level}{counter}" in levels:
                        counter += 1
                    name = f"{core_level}{counter}"
                name = _xl_title(list(levels), name)
                levels[name] = _avg_sheet(name, core_level, parsed, idx,
                                          base_name)
        except Exception as exc:
            errors.append(f"{os.path.basename(str(path))}: {exc}")
    if not levels:
        raise ValueError("No AVG files could be processed"
                         + (f" ({'; '.join(errors)})" if errors else ""))
    return levels


def _never(_path):
    return False


FORMATS = [
    Format("XPS", "Avantage (.xlsx, .xls)", (".xlsx", ".xls"), read_avantage,
           group="Thermo", sniff=sniff_avantage),
    Format("XPS", "Avantage files (.xlsx, .xls)", (".xlsx", ".xls"),
           read_avantage_files, group="Thermo", sniff=_never, multi=True),
    Format("XPS", "VGD (.vgd)", (".vgd",), read_vgd, group="Thermo",
           needs=("olefile",)),
    Format("XPS", "VGD files (.vgd)", (".vgd",), read_vgd_files,
           group="Thermo", sniff=_never, multi=True, needs=("olefile",)),
    Format("XPS", "AVG (.avg)", (".avg",), read_avg, group="Thermo"),
    Format("XPS", "AVG files (.avg)", (".avg",), read_avg_files,
           group="Thermo", sniff=_never, multi=True),
]
