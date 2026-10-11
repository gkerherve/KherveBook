"""PHI (Physical Electronics) XPS import: ``.spe`` spectra and ``.pro``
depth profiles.

Both are a plain-text ``SOFH`` … ``EOFH`` header (acquisition settings, the
``SpectralRegDef:`` regions, the ``IntensityCalCoeff`` transmission
coefficients) followed by binary intensities:

* ``.spe`` — one block per region, float32 (VersaProbe III) or float64
  after the header (X-tool), or float64 at the very end of the file
  (Quantum 2000); the layout is detected from the data.
* ``.pro`` — float32 counts/second, region-major / cycle-minor (all
  sputter cycles of the first region, then the second…); one sheet per
  region and cycle (``C1s``, ``C1s1``, ``C1s2``…), as KherveFitting does.

Intensities are divided by PHI's analyser transmission
``T = PE * (a² / (a² + (KE/PE)²))^b``.

Ported from KherveFittingPro ``libraries/FileMenu/SPE_Import.py``
(``open_spe_file`` split into pure functions, ``build_spe_core_levels``)
and ``PRO_Import.py`` (``open_pro_file``, ``build_pro_core_levels``),
wx-free. ``.sxi`` images are not here: they become an image map, not a
spectrum.

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
from .kfitwrite import core_level
from .kratos import normalize_sheet_name

_SPIN_ORBIT_DIGITS = {'p': '13', 'd': '35', 'f': '57'}


def phi_region_base(name):
    """'Fe2p3' (PHI's 2p3/2 window) -> 'Fe2p'; 'C1s', 'O1s' unchanged.

    In KherveFitting a trailing digit is the sample row, so only a digit
    that is a valid j label for that orbital (p: 1,3  d: 3,5  f: 5,7) is
    dropped.
    """
    m = re.match(r'^([A-Z][a-z]?\d[pdf])(\d)$', str(name).strip())
    if m and m.group(2) in _SPIN_ORBIT_DIGITS[m.group(1)[-1]]:
        return m.group(1)
    return name


def phi_transmission(ke, pass_energy, a, b):
    """PHI analyser transmission (MultiPak's law, CasaXPS's 'Transmission'):

        T = PE * ( a^2 / (a^2 + (KE/PE)^2) )^b

    with a, b from IntensityCalCoeff; ``a * KE^-b`` without a pass energy.
    """
    ke = np.maximum(np.asarray(ke, dtype=float), 1.0)
    try:
        pe = float(pass_energy)
    except (TypeError, ValueError):
        pe = 0.0
    if not pe > 0:
        return a * np.power(ke, -b)
    r = ke / pe
    return pe * np.power(a * a / (a * a + r * r), b)


def sniff_phi(path):
    """A PHI binary file starts with its ``SOFH`` text header, which
    declares the ``SpectralRegDef`` regions."""
    try:
        with open(path, 'rb') as f:
            head = f.read(65536)
    except OSError:
        return False
    return b'SOFH' in head[:64] and b'SpectralRegDef' in head


# ---------------------------------------------------------------------------
# .spe
# ---------------------------------------------------------------------------

def parse_spe_header(content, file_path=""):
    """The SOFH…EOFH header of an .spe: regions, calibration and metadata.

    Returns a dict with 'a', 'b', 'source_energy', 'instrument',
    'regions' and 'metadata'.
    """
    header_match = re.search(rb'SOFH(.*?)EOFH', content, re.DOTALL)
    if not header_match:
        raise ValueError("Cannot find header section (SOFH...EOFH)")
    header_text = header_match.group(1).decode('utf-8', errors='ignore')
    header_lines = [line.strip() for line in header_text.strip().split('\n')]

    # Intensity calibration (transmission) coefficients
    a, b = 31.826, 0.229
    for line in header_lines:
        if 'IntensityCalCoeff:' in line:
            try:
                _, coeffs = line.split(':', 1)
                parts = coeffs.strip().split()
                if len(parts) >= 2:
                    a = float(parts[0])
                    b = float(parts[1])
            except Exception:
                pass
            break

    source_energy = 1486.6
    for line in header_lines:
        if 'XraySource:' in line:
            if 'Al' in line:
                source_energy = 1486.6
            elif 'Mg' in line:
                source_energy = 1253.6
            for part in line.split():
                try:
                    val = float(part)
                except ValueError:
                    continue
                if 1200 < val < 1600:
                    source_energy = val
                    break
            break

    instrument_model = "Unknown"
    for line in header_lines:
        if 'InstrumentModel:' in line:
            instrument_model = line.split(':', 1)[1].strip()
            break

    # Active regions: SpectralRegDef: (not the Full / 2: variants)
    regions = []
    for line in header_lines:
        if line.startswith('SpectralRegDef:') and 'Full' not in line \
                and '2:' not in line:
            parts = line.split()
            if len(parts) >= 9:
                region = {
                    'number': int(parts[1]),
                    'name': parts[3],
                    'atomic_number': (int(parts[4])
                                      if parts[4].lstrip('-').isdigit()
                                      else 0),
                    'num_points': int(parts[5]),
                    'step': float(parts[6]),
                    'start_energy': float(parts[7]),
                    'end_energy': float(parts[8]),
                    # field 12: pass energy (eV)
                    'pass_energy': (float(parts[12]) if len(parts) > 12 and
                                    parts[12].replace('.', '', 1).isdigit()
                                    else None),
                }
                if region['name'] == 'Su1s':
                    region['name'] = 'Survey'
                regions.append(region)
    if not regions:
        raise ValueError("No spectral regions found in file")

    metadata = {
        'Sample ID': os.path.basename(file_path),
        'Date': '1970/1/1',
        'Time': '0:0:0',
        'Technique': 'XPS',
        'Instrument': instrument_model,
        'Species & Transition': '',
        'Number of scans': '1',
        'Source Label': 'Al' if source_energy > 1400 else 'Mg',
        'Source Energy': str(source_energy),
        'Source width X': '100',
        'Source width Y': '100',
        'Pass Energy': '224',
        'Work Function': '4.339',
        'Analyzer Mode': 'FAT',
        'Sputtering Energy': 'N/A',
        'Take-off Polar Angle': '1E+37',
        'Take-off Azimuth': '1E+37',
        'Target Bias': '1E+37',
        'Analysis Width X': '1E+37',
        'Analysis Width Y': '1E+37',
        'X Label': 'Kinetic Energy',
        'X Units': 'eV',
        'X Start': '',
        'X Step': '',
        'Num Y Values': '',
        'Num Scans': '1',
        'Collection Time': '0.16',
        'Time Correction': '1E+37',
        'Y Unit': 'd',
        '# Comment Lines': '0',
        'Block Comment': '',
    }
    for line in header_lines:
        if 'FileDateTime:' in line:
            parts = line.split(':', 1)[1].strip().split()
            if len(parts) >= 2:
                metadata['Date'] = parts[0]
                metadata['Time'] = parts[1]
        elif 'FileDate:' in line:
            metadata['Date'] = line.split(':', 1)[1].strip().replace(' ', '/')
        elif 'PassEnergy:' in line:
            try:
                metadata['Pass Energy'] = line.split(':', 1)[1].strip(
                ).split()[0]
            except IndexError:
                pass
        elif 'AnalyserWorkFcn:' in line or 'WorkFunction:' in line:
            try:
                metadata['Work Function'] = line.split(':', 1)[1].strip(
                ).split()[0]
            except IndexError:
                pass
        elif 'AnalyserMode:' in line:
            metadata['Analyzer Mode'] = line.split(':', 1)[1].strip()
        elif 'XrayBeamDiameter:' in line:
            try:
                size = line.split(':', 1)[1].strip().split()[0]
                metadata['Source width X'] = size
                metadata['Source width Y'] = size
            except IndexError:
                pass
        elif 'Comments:' in line:
            metadata['Block Comment'] = line.split(':', 1)[1].strip()
            metadata['# Comment Lines'] = '1'

    return {'a': a, 'b': b, 'source_energy': source_energy,
            'instrument': instrument_model, 'regions': regions,
            'metadata': metadata}


def _try_offset_standard(binary_data, first_region, bytes_per_val):
    """Offset of the first region for data right after the header
    (VersaProbe float32 / X-tool float64), or None."""
    fmt = '<f' if bytes_per_val == 4 else '<d'
    num_points = first_region['num_points']
    max_offset = len(binary_data) - num_points * bytes_per_val
    if max_offset < 0:
        return None
    max_offset = min(2000, max_offset)

    for offset in range(0, max_offset + 1, 2):
        values = []
        valid = True
        for i in range(min(20, num_points)):
            pos = offset + i * bytes_per_val
            if pos + bytes_per_val > len(binary_data):
                valid = False
                break
            val = struct.unpack(fmt, binary_data[pos:pos + bytes_per_val])[0]
            if not (1 < val < 1e8):
                valid = False
                break
            values.append(val)
        if valid and len(values) >= 10 and max(values) - min(values) > 1:
            all_valid = True
            for i in range(num_points):
                pos = offset + i * bytes_per_val
                if pos + bytes_per_val > len(binary_data):
                    all_valid = False
                    break
                val = struct.unpack(fmt,
                                    binary_data[pos:pos + bytes_per_val])[0]
                if not (0 <= val < 1e8):
                    all_valid = False
                    break
            if all_valid:
                return offset
    return None


def _try_quantum2000(binary_data, first_region, total_points):
    """Offset for Quantum 2000 files: float64 data at the END, or None."""
    expected_size = total_points * 8
    if expected_size > len(binary_data):
        return None
    offset = len(binary_data) - expected_size
    num_points = first_region['num_points']
    values = []
    for i in range(min(20, num_points)):
        pos = offset + i * 8
        val = struct.unpack('<d', binary_data[pos:pos + 8])[0]
        if not (0 < val < 1e8):
            return None
        values.append(val)
    if len(values) >= 10 and max(values) - min(values) > 1:
        return offset
    return None


def find_spe_data(binary_data, regions):
    """(bytes per value, offset of the first region) for an .spe's binary
    section: float32, then float64 after the header, then float64 at the
    end."""
    for nbytes in (4, 8):
        offset = _try_offset_standard(binary_data, regions[0], nbytes)
        if offset is not None:
            return nbytes, offset
    total_points = sum(r['num_points'] for r in regions)
    offset = _try_quantum2000(binary_data, regions[0], total_points)
    if offset is not None:
        return 8, offset
    raise ValueError("Could not detect data format or find valid data offset")


def decode_spe_records(content, file_path=""):
    """One record per readable region: 'sheet_name', 'energy' (BE),
    'corrected' (counts / transmission) and 'exp'."""
    hdr = parse_spe_header(content, file_path)
    regions, metadata = hdr['regions'], hdr['metadata']
    binary_data = content[content.find(b'EOFH') + 4:]
    bytes_per_val, first_offset = find_spe_data(binary_data, regions)
    fmt = '<f' if bytes_per_val == 4 else '<d'

    region_offsets = []
    current = first_offset
    for region in regions:
        region_offsets.append(current)
        current += region['num_points'] * bytes_per_val

    records = []
    for i, region in enumerate(regions):
        sheet_name = phi_region_base(region['name'])
        num_points = region['num_points']
        offset = region_offsets[i]

        intensity_values = []
        valid_count = 0
        for j in range(num_points):
            pos = offset + j * bytes_per_val
            if pos + bytes_per_val <= len(binary_data):
                val = struct.unpack(fmt,
                                    binary_data[pos:pos + bytes_per_val])[0]
                if 0 <= val < 1e8:
                    intensity_values.append(val)
                    valid_count += 1
                else:
                    intensity_values.append(0.0)
            else:
                intensity_values.append(0.0)

        # Skip regions with mostly invalid data (< 50 % valid)
        if valid_count < num_points * 0.5:
            continue
        if len(intensity_values) < num_points:
            intensity_values.extend([0.0] * (num_points - len(intensity_values)))

        sheet_name = sheet_name[:31]
        region_metadata = metadata.copy()
        region_metadata['Species & Transition'] = region['name']
        region_metadata['X Start'] = f"{region['start_energy']:.2f}"
        region_metadata['X Step'] = f"{region['step']:.4f}"
        region_metadata['Num Y Values'] = str(num_points)

        energy_values = np.linspace(region['start_energy'],
                                    region['end_energy'], num_points)
        ke_values = np.maximum(hdr['source_energy'] - energy_values, 1.0)
        transmission = phi_transmission(
            ke_values, region.get('pass_energy') or metadata.get('Pass Energy'),
            hdr['a'], hdr['b'])
        corrected = np.array(intensity_values) / transmission
        records.append({'sheet_name': sheet_name, 'energy': energy_values,
                        'corrected': corrected, 'exp': region_metadata})

    if not records:
        raise ValueError("No valid data regions found in file")
    return records


def build_spe_core_levels(records):
    """{sheet: core level}: no separate raw / transmission column, so both
    fall back to the corrected trace / 1.0, as KherveFitting's reader
    does. A repeated sheet name keeps the last region, as there."""
    return {
        rec['sheet_name']: core_level(
            rec['sheet_name'],
            be_values=rec['energy'],
            plot_values=rec['corrected'],
            experimental_info=rec['exp'],
        )
        for rec in records
    }


def read_spe(path):
    """PHI ``.spe`` -> {sheet: core level}."""
    with open(path, 'rb') as f:
        content = f.read()
    return build_spe_core_levels(decode_spe_records(content, path))


# ---------------------------------------------------------------------------
# .pro depth profile
# ---------------------------------------------------------------------------

def _parse_pro_header(content):
    """(header lines, {key: first value}) from the SOFH…EOFH block."""
    hm = re.search(rb'SOFH(.*?)EOFH', content, re.DOTALL)
    if not hm:
        raise ValueError("Not a valid PHI file: missing SOFH...EOFH header")
    text = hm.group(1).decode('latin-1', errors='ignore')
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    hdr = {}
    for ln in lines:
        if ':' in ln:
            key, val = ln.split(':', 1)
            hdr.setdefault(key.strip(), val.strip())
    return lines, hdr


def _extract_regions(header_lines):
    """The profile's regions from the plain ``SpectralRegDef:`` lines:
    <n> <?> <name> <Z> <npts> <step> <be_start> <be_end> <inner_lo>
    <inner_hi> <coll_time> <pass_energy> <mode>."""
    regions = []
    for ln in header_lines:
        if not ln.startswith('SpectralRegDef:'):
            continue
        if ln.split(':', 1)[0] != 'SpectralRegDef':
            continue
        p = ln.split()
        if len(p) < 13:
            continue
        try:
            regions.append({
                'name': p[3],
                'atomic_number': int(p[4]) if p[4].lstrip('-').isdigit()
                else 0,
                'npts': int(p[5]),
                'step': float(p[6]),
                'be_start': float(p[7]),
                'be_end': float(p[8]),
                'coll_time': float(p[11]),
                'pass_energy': float(p[12]),
            })
        except (ValueError, IndexError):
            continue
    return regions


def _find_data_offset(binary, regions, cycles):
    """Byte offset of the first spectrum float in the post-EOFH section:
    the first offset where the first region is a strong positive signal
    and the whole region-major / cycle-minor layout fits, leaving only the
    trailer (record tail + two float32 tables per region per cycle)."""
    total = cycles * sum(r['npts'] for r in regions)
    tot_bytes = total * 4
    max_trailer = 512 + 8 * len(regions) * cycles
    n0 = regions[0]['npts']
    limit = len(binary) - tot_bytes
    if limit < 0:
        raise ValueError("PHI .pro binary section too small for declared "
                         "regions/cycles")
    for off in range(0, limit + 1, 2):
        ok = True
        for k in range(n0):
            v = struct.unpack_from('<f', binary, off + 4 * k)[0]
            if not (1.0 < v < 1e7):
                ok = False
                break
        if not ok:
            continue
        for k in range(n0, total):
            v = struct.unpack_from('<f', binary, off + 4 * k)[0]
            if not (0.0 <= v < 1e7):
                ok = False
                break
        if ok and 0 <= len(binary) - (off + tot_bytes) <= max_trailer:
            return off
    raise ValueError("Could not locate spectral data in PHI .pro file")


def _read_blocks(binary, start, regions, cycles):
    """[(region, cycle, c/s values)] in storage order."""
    off = start
    blocks = []
    for r in regions:
        for c in range(cycles):
            vals = list(struct.unpack_from('<%df' % r['npts'], binary, off))
            off += r['npts'] * 4
            blocks.append((r, c, vals))
    return blocks


def decode_pro_records(content, file_path=""):
    """One record per region × cycle: 'sheet_name', 'be', 'corrected',
    'raw_counts', 'transmission', 'exp' (plus the sample name)."""
    header_lines, hdr = _parse_pro_header(content)
    regions = _extract_regions(header_lines)
    if not regions:
        raise ValueError("No active spectral regions (SpectralRegDef) found")

    try:
        cycles = int(float(hdr.get('NoDPDataCyc', '1')))
    except (ValueError, TypeError):
        cycles = 1
    cycles = max(cycles, 1)

    source_energy = 1486.6
    for tok in hdr.get('XraySource', '').split():
        try:
            val = float(tok)
        except ValueError:
            continue
        if 100 < val < 6000:
            source_energy = val
            break
    source_label = 'Al' if source_energy > 1400 else 'Mg'

    cal_a, cal_b = 78.797, 0.629  # VersaProbe III defaults
    cal = hdr.get('IntensityCalCoeff', '')
    if cal:
        try:
            parts = cal.split()
            cal_a, cal_b = float(parts[0]), float(parts[1])
        except (ValueError, IndexError):
            pass

    work_fn = '4.397'
    wf = hdr.get('AnalyserWorkFcn', '')
    if wf:
        work_fn = wf.split()[0]

    instrument = hdr.get('InstrumentModel', 'PHI')
    operator = hdr.get('Operator', '')
    analyzer_mode = hdr.get('AnalyserMode', 'FAT')
    sputter_energy = hdr.get('SputterEnergy', 'N/A')
    date_raw = hdr.get('FileDate', '')
    date_str = date_raw.replace(' ', '/') if date_raw else ''
    beam = hdr.get('XrayBeamDiameter', '220').split()[0]

    sample_name = None
    for ln in header_lines:
        if ln.startswith('SpatialAreaDesc:'):
            parts = ln.split(':', 1)[1].strip().split(None, 1)
            if len(parts) == 2:
                sample_name = parts[1].strip()
            break
    if not sample_name:
        sample_name = os.path.splitext(os.path.basename(file_path))[0]

    binary = content[content.find(b'EOFH') + 4:]
    start = _find_data_offset(binary, regions, cycles)
    blocks = _read_blocks(binary, start, regions, cycles)

    records = []
    sheet_names = []
    for region, cycle, cs_values in blocks:
        base = normalize_sheet_name(phi_region_base(region['name']))
        sheet_name = base
        count = 1
        while sheet_name in sheet_names:
            sheet_name = f"{base}{count}"
            count += 1
        sheet_names.append(sheet_name)

        npts = region['npts']
        be = np.linspace(region['be_start'], region['be_end'], npts)
        # counts = (counts / second) x collection time, as PHI's VAMAS has
        raw_counts = np.array(cs_values, dtype=float) * region['coll_time']
        transmission = phi_transmission(source_energy - be,
                                        region['pass_energy'], cal_a, cal_b)
        corrected = raw_counts / transmission

        exp = {
            'Sample ID': sample_name,
            'Date': date_str,
            'Time': '0:0:0',
            'Technique': 'XPS',
            'Species & Transition': region['name'],
            'Number of scans': '1',
            'Source Label': source_label,
            'Source Energy': f"{source_energy:.1f}",
            'Source width X': beam,
            'Source width Y': beam,
            'Pass Energy': f"{region['pass_energy']:.0f}",
            'Work Function': work_fn,
            'Analyzer Mode': analyzer_mode,
            'Sputtering Energy': sputter_energy,
            'Sputter Time': str(cycle),
            'Sample Tilt': '',
            'Take-off Polar Angle': '1E+37',
            'Take-off Azimuth': '1E+37',
            'Target Bias': '1E+37',
            'Analysis Width X': '1E+37',
            'Analysis Width Y': '1E+37',
            'X Label': 'Binding Energy',
            'X Units': 'eV',
            'X Start': f"{region['be_start']:.2f}",
            'X Step': f"{region['step']:.4f}",
            'Num Y Values': str(npts),
            'Num Scans': '1',
            'Collection Time': f"{region['coll_time']:.3f}",
            'Time Correction': '1E+37',
            'Y Unit': 'd',
            '# Comment Lines': '1',
            'Block Comment': (f"PHI .pro depth profile - {region['name']} "
                              f"cycle {cycle}"),
            'Depth Cycle': str(cycle),
            'Instrument': instrument,
            'Operator': operator,
        }
        records.append({'sheet_name': sheet_name, 'be': be,
                        'corrected': corrected, 'raw_counts': raw_counts,
                        'transmission': transmission, 'exp': exp,
                        'sample_name': sample_name})
    if not records:
        raise ValueError("No spectra were imported")
    return records


def build_pro_core_levels(records):
    """{sheet: core level} for decoded .pro blocks."""
    return {
        rec['sheet_name']: core_level(
            rec['sheet_name'],
            be_values=rec['be'],
            plot_values=rec['corrected'],
            raw_values=rec['raw_counts'],
            transmission=rec['transmission'],
            experimental_info=rec['exp'],
        )
        for rec in records
    }


def read_pro(path):
    """PHI ``.pro`` depth profile -> {sheet: core level}."""
    with open(path, 'rb') as f:
        content = f.read()
    return build_pro_core_levels(decode_pro_records(content, path))


FORMATS = [
    Format(technique="XPS", group="Phi", label="PHI (.spe)",
           exts=(".spe",), read=read_spe, sniff=sniff_phi),
    Format(technique="XPS", group="Phi", label="PHI depth profile (.pro)",
           exts=(".pro",), read=read_pro, sniff=sniff_phi),
]
