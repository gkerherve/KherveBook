"""Powder-XRD import: PANalytical .xrdml, Bruker .raw, Rigaku/text 2θ.

Ported from KherveFittingPro (``libraries/XRD/XRD_FileFormats.py``
``read_xrdml`` / ``read_bruker_raw`` / ``read_text_xy`` and
``libraries/FileMenu/XRD_Import.py`` ``build_xrd_sheet`` /
``_import_xrd_paths``), wx-free. Each scan becomes a sheet named XRD,
XRD1, XRD2… — the name is how KherveFitting (and `kfitio`) recognise a
2θ sheet — carrying the lossless ``XRD_`` copies and the wavelengths
(as strings, so the project's two-decimal rounding cannot touch them).

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

ANODE_WAVELENGTHS = {
    'Cu': (1.5405980, 1.5444260), 'Co': (1.7889960, 1.7928350),
    'Cr': (2.2897600, 2.2936520), 'Fe': (1.9360420, 1.9399730),
    'Mo': (0.7093190, 0.7135900), 'Ag': (0.5594075, 0.5638250),
}

# libraries/XRD/XRD_Pattern.py
CU_KA1 = 1.5405980
CU_KA2 = 1.5444260
KA2_RATIO = 0.5

TEXT_EXTENSIONS = ('.asc', '.xy', '.txt', '.csv', '.dat', '.uxd')
#: what KherveFitting's "Multiple files (folder)" picks up
XRD_EXTENSIONS = ('.xrdml', '.raw', '.asc', '.xy', '.uxd')


def _scan_dict(two_theta, intensity, wavelength=None, wavelength2=None,
               ka2_ratio=None, anode='', meta=None):
    two_theta = np.asarray(two_theta, dtype=float)
    intensity = np.asarray(intensity, dtype=float)
    sel = np.isfinite(two_theta) & np.isfinite(intensity)
    return {'two_theta': two_theta[sel], 'intensity': intensity[sel],
            'wavelength': wavelength, 'wavelength2': wavelength2,
            'ka2_ratio': ka2_ratio, 'anode': anode, 'meta': meta or {}}


# ------------------------------------------------------------------- xrdml

def _parse_xml(path):
    """KherveFitting parses with defusedxml; without it, refuse any DTD
    (entity expansion is the risk) and use the standard library."""
    try:
        import defusedxml.ElementTree as ET
        return ET.parse(path)
    except ImportError:
        pass
    import xml.etree.ElementTree as ET
    with open(path, 'rb') as fh:
        head = fh.read()
    if b'<!DOCTYPE' in head or b'<!ENTITY' in head:
        raise ValueError('XRDML with a DTD is not accepted')
    return ET.ElementTree(ET.fromstring(head))


def read_xrdml(path):
    tree = _parse_xml(path)
    root = tree.getroot()
    ns = ({'x': root.tag.split('}')[0].strip('{')}
          if root.tag.startswith('{') else {})

    def find(elem, tag):
        return elem.find(f'x:{tag}', ns) if ns else elem.find(tag)

    def findall(elem, tag):
        return (elem.findall(f'.//x:{tag}', ns) if ns
                else elem.findall(f'.//{tag}'))

    wavelength = wavelength2 = ratio = None
    anode = ''
    for used in findall(root, 'usedWavelength'):
        ka1 = find(used, 'kAlpha1')
        ka2 = find(used, 'kAlpha2')
        rat = find(used, 'ratioKAlpha2KAlpha1')
        if ka1 is not None:
            wavelength = float(ka1.text)
        if ka2 is not None:
            wavelength2 = float(ka2.text)
        if rat is not None:
            ratio = float(rat.text)
        break
    for tube in findall(root, 'xRayTube'):
        anode_el = find(tube, 'anodeMaterial')
        if anode_el is not None and anode_el.text:
            anode = anode_el.text.strip()
        break

    scans = []
    for datapoints in findall(root, 'dataPoints'):
        counts_el = None
        for tag in ('counts', 'intensities'):
            counts_el = find(datapoints, tag)
            if counts_el is not None and counts_el.text:
                break
        if counts_el is None or not counts_el.text:
            continue
        counts = np.array(counts_el.text.split(), dtype=float)
        start = end = None
        for positions in (datapoints.findall('x:positions', ns) if ns
                          else datapoints.findall('positions')):
            if positions.get('axis') == '2Theta':
                s = find(positions, 'startPosition')
                e = find(positions, 'endPosition')
                lst = find(positions, 'listPositions')
                if lst is not None and lst.text:
                    tth = np.array(lst.text.split(), dtype=float)
                    if len(tth) == len(counts):
                        start, end = None, None
                        scans.append(_scan_dict(tth, counts, wavelength,
                                                wavelength2, ratio, anode,
                                                {'source': 'xrdml'}))
                        break
                if s is not None and e is not None:
                    start, end = float(s.text), float(e.text)
        if start is not None and end is not None and len(counts) > 1:
            tth = np.linspace(start, end, len(counts))
            scans.append(_scan_dict(tth, counts, wavelength, wavelength2,
                                    ratio, anode, {'source': 'xrdml'}))
    return scans


# ---------------------------------------------------------------- Bruker raw

def read_bruker_raw(path):
    with open(path, 'rb') as fh:
        blob = fh.read()
    magic = blob[:7]
    if magic.startswith(b'RAW1.01'):
        return _read_raw_v3(blob)
    if magic.startswith(b'RAW4'):
        return _read_raw_v4(blob)
    if magic.startswith(b'RAW'):
        return _read_raw_v4(blob)      # heuristic fallback for v1/v2
    raise ValueError('Not a Bruker RAW file')


def _read_raw_v3(blob):
    """Bruker/Siemens RAW version 3 ('RAW1.01')."""
    range_cnt = struct.unpack_from('<I', blob, 12)[0]
    anode = blob[608:610].decode('ascii', 'replace').strip('\x00 ') \
        .capitalize()
    ka1 = struct.unpack_from('<d', blob, 624)[0]
    ka2 = struct.unpack_from('<d', blob, 632)[0]
    ratio = struct.unpack_from('<d', blob, 648)[0]
    if not (0.4 < ka1 < 3.0):
        ka1, ka2, ratio = (ANODE_WAVELENGTHS.get(anode or 'Cu', (None, None))
                           + (0.5,))
    pos = 712
    scans = []
    for _ in range(max(range_cnt, 1)):
        if pos + 304 > len(blob):
            break
        header_len = struct.unpack_from('<I', blob, pos)[0]
        steps = struct.unpack_from('<I', blob, pos + 4)[0]
        start_2th = struct.unpack_from('<d', blob, pos + 16)[0]
        step_size = struct.unpack_from('<d', blob, pos + 176)[0]
        supp = struct.unpack_from('<I', blob, pos + 256)[0]
        data_off = pos + header_len + supp
        if not (0 < steps < 2_000_000) or data_off + 4 * steps > len(blob):
            break
        counts = np.frombuffer(blob, dtype='<f4', count=steps,
                               offset=data_off)
        tth = start_2th + step_size * np.arange(steps)
        scans.append(_scan_dict(tth, counts.astype(float), ka1, ka2, ratio,
                                anode, {'source': 'bruker_raw_v3'}))
        pos = data_off + 4 * steps
    if not scans:
        raise ValueError('Could not read RAW v3 ranges')
    return scans


def _read_raw_v4(blob):
    """Bruker RAW version 4 - the format is undocumented, so this reader
    locates the trailing float32 count block heuristically and pulls the
    start angle / step size doubles from the header."""
    size = len(blob)

    # 1) candidate point counts: u32 values that occur >= 2 times in the
    # header
    counts_candidates = {}
    header_limit = min(size, 4096)
    for off in range(0, header_limit - 4):
        val = struct.unpack_from('<I', blob, off)[0]
        if 50 <= val <= 2_000_000 and val * 4 < size:
            counts_candidates.setdefault(val, 0)
            counts_candidates[val] += 1

    def counts_block_ok(npts):
        offset = size - 4 * npts
        if offset < 256:
            return None
        arr = np.frombuffer(blob, dtype='<f4', count=npts, offset=offset)
        as_float = arr.astype(float)
        if not np.all(np.isfinite(as_float)):
            return None
        if as_float.min() < -1.0 or as_float.max() > 1e8 \
                or as_float.max() <= 0:
            return None
        return as_float

    # pick the LARGEST repeated candidate whose trailing block is valid —
    # small u32s (256, 512...) are common in headers, the data block is not
    npts = counts = None
    repeated = sorted((v for v, reps in counts_candidates.items()
                       if reps >= 2), reverse=True)
    for val in repeated:
        arr = counts_block_ok(val)
        if arr is not None:
            npts, counts = val, arr
            break
    if counts is None:
        for val in sorted(counts_candidates, reverse=True):
            arr = counts_block_ok(val)
            if arr is not None:
                npts, counts = val, arr
                break
    if counts is None:
        raise ValueError('RAW4: could not locate the intensity block')

    data_off = size - 4 * npts

    # 2) start / step doubles from the header region
    doubles = []
    for off in range(0, min(data_off, 4096) - 8):
        val = struct.unpack_from('<d', blob, off)[0]
        if np.isfinite(val):
            doubles.append((off, val))

    def is_wavelength_like(value):
        for ka1_w, ka2_w in ANODE_WAVELENGTHS.values():
            if abs(value - ka1_w) < 5e-3 or abs(value - ka2_w) < 5e-3:
                return True
        return False

    # primary anchor: the '2Theta' axis record stores the start angle as a
    # double 44 bytes after the axis name
    start = step = None
    axis_idx = blob.find(b'2Theta')
    if 0 < axis_idx < data_off - 52:
        cand = struct.unpack_from('<d', blob, axis_idx + 44)[0]
        if np.isfinite(cand) and 0.0 < cand <= 175.0 \
                and not is_wavelength_like(cand):
            start = cand

    step_cands = [v for _, v in doubles if 1e-4 < v < 0.5]
    start_cands = [v for _, v in doubles
                   if 1.0 <= v <= 170.0 and not is_wavelength_like(v)]
    if start is None:
        best_votes = -1
        for st in start_cands:
            votes = start_cands.count(st)
            if votes > best_votes:
                start, best_votes = st, votes
    if start is not None:
        best_votes = -1
        for sp in step_cands:
            end = start + sp * (npts - 1)
            if start + 1.0 < end <= 180.0:
                votes = step_cands.count(sp)
                if votes > best_votes:
                    step, best_votes = sp, votes
    if start is None or step is None:
        raise ValueError('RAW4: could not determine the 2theta axis')

    anode = 'Cu'
    for sym in ANODE_WAVELENGTHS:
        if sym.encode() in blob[400:520]:
            anode = sym
            break
    ka1, ka2 = ANODE_WAVELENGTHS.get(anode, ANODE_WAVELENGTHS['Cu'])
    # wavelengths are often stored explicitly as doubles - use them if
    # present
    for _, val in doubles:
        if abs(val - ka1) < 5e-4:
            ka1 = val
        elif ka2 and abs(val - ka2) < 5e-4:
            ka2 = val
    tth = start + step * np.arange(npts)
    return [_scan_dict(tth, counts, ka1, ka2, 0.5, anode,
                       {'source': 'bruker_raw_v4'})]


# ------------------------------------------------------------------ text/CSV

def read_text_xy(path):
    """Two-or-three column text (.asc/.xy/.txt/.csv/.dat). Column 1 = 2θ.
    With 3+ columns the LAST column is used as intensity (e.g. Rigaku .ASC
    exports 2theta / processed / raw counts)."""
    rows = []
    numeric = re.compile(r'^[\s,;]*[-+0-9.eE]')
    with open(path, 'r', encoding='utf-8', errors='replace') as fh:
        for line in fh:
            if not numeric.match(line):
                continue
            parts = re.split(r'[\s,;]+', line.strip())
            try:
                vals = [float(p) for p in parts if p != '']
            except ValueError:
                continue
            if len(vals) >= 2:
                rows.append(vals)
    if len(rows) < 5:
        raise ValueError('No numeric two-column data found')
    n_cols = min(len(r) for r in rows)
    arr = np.array([r[:n_cols] for r in rows], dtype=float)
    tth = arr[:, 0]
    intensity = arr[:, -1] if n_cols >= 3 else arr[:, 1]
    order = np.argsort(tth)
    return [_scan_dict(tth[order], intensity[order],
                       meta={'source': 'text', 'n_columns': n_cols})]


def read_xrd_file(path):
    ext = os.path.splitext(path)[1].lower()
    if ext == '.xrdml':
        return read_xrdml(path)
    if ext == '.raw':
        return read_bruker_raw(path)
    if ext in TEXT_EXTENSIONS:
        return read_text_xy(path)
    with open(path, 'rb') as fh:
        head = fh.read(64)
    if head.startswith(b'RAW'):
        return read_bruker_raw(path)
    if b'xrdMeasurement' in head or head.lstrip().startswith(b'<?xml'):
        return read_xrdml(path)
    return read_text_xy(path)


# ---------------------------------------------------------------------------
# Sheet construction (libraries/FileMenu/XRD_Import.py)
# ---------------------------------------------------------------------------

def next_xrd_sheet_name(existing_names):
    """Return the next free XRD sheet name: XRD, XRD1, XRD2, ..."""
    existing = {str(name).upper() for name in existing_names}
    if 'XRD' not in existing:
        return 'XRD'
    idx = 1
    while f'XRD{idx}' in existing:
        idx += 1
    return f'XRD{idx}'


def build_xrd_sheet(scan, file_path, sheet_name, scan_index=0, n_scans=1):
    """The core-level entry for one scan: x = 2θ (degrees), y = counts."""
    tth = np.asarray(scan['two_theta'], dtype=float)
    counts = np.asarray(scan['intensity'], dtype=float)

    x_values = [float(v) for v in tth]
    y_values = [float(v) for v in counts]

    base = os.path.splitext(os.path.basename(file_path))[0]
    label = base if n_scans == 1 else f"{base} - scan {scan_index + 1}"

    wavelength = scan.get('wavelength') or CU_KA1
    wavelength2 = scan.get('wavelength2')
    ka2_ratio = scan.get('ka2_ratio')
    if wavelength2 is None and abs(wavelength - CU_KA1) < 5e-3:
        wavelength2, ka2_ratio = CU_KA2, KA2_RATIO

    info = {
        'Technique': 'XRD (powder diffraction)',
        'Source File': os.path.basename(file_path),
        'Number of Points': str(len(x_values)),
        '2θ Range (°)': f"{tth.min():.3f} - {tth.max():.3f}",
        'Step (°)': (f"{float(np.median(np.diff(tth))):.5f}"
                     if len(tth) > 1 else ''),
        'Wavelength Kα1 (Å)': f"{wavelength:.6f}",
    }
    if scan.get('anode'):
        info['Anode'] = scan['anode']
    if wavelength2:
        info['Wavelength Kα2 (Å)'] = f"{wavelength2:.6f}"
        info['Kα2/Kα1 Ratio'] = f"{ka2_ratio or 0:.3f}"

    sheet = {
        'Name': sheet_name,
        'B.E.': x_values,
        'Raw Data': y_values,
        'XRD_Label': label,
        'XRD_Source': os.path.basename(file_path),
        'ExperimentalInfo': info,
        'Background': {
            'Bkg Y': list(y_values),
            'Bkg Type': '',
            'Bkg Low': float(tth.min()),
            'Bkg High': float(tth.max()),
            'Bkg Offset Low': 0,
            'Bkg Offset High': 0,
        },
    }
    # Lossless copies; wavelengths as strings (the project rounds floats).
    sheet['XRD_TwoTheta'] = x_values
    sheet['XRD_Intensity'] = y_values
    sheet['XRD_Wavelength'] = repr(float(wavelength))
    if wavelength2:
        sheet['XRD_Wavelength2'] = repr(float(wavelength2))
        sheet['XRD_Ka2_Ratio'] = repr(float(ka2_ratio or 0.0))
    if scan.get('anode'):
        sheet['XRD_Anode'] = scan['anode']
    return sheet


# ---------------------------------------------------------------------------
# Readers
# ---------------------------------------------------------------------------

def _expand(paths, exts):
    """The files to import: folders are listed (KherveFitting's folder
    import), then only *exts* are kept, sorted."""
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
    """``_import_xrd_paths`` without the window: {sheet: core level}."""
    core_levels = {}
    skipped = []
    for file_path in sorted(file_paths):
        try:
            scans = read_xrd_file(file_path)
        except Exception as e:
            skipped.append(f"{os.path.basename(file_path)}: {e}")
            continue
        for i, scan in enumerate(scans):
            if len(scan['two_theta']) < 5:
                continue
            sheet_name = next_xrd_sheet_name(core_levels.keys())
            core_levels[sheet_name] = build_xrd_sheet(
                scan, file_path, sheet_name, i, len(scans))
    if not core_levels:
        raise ValueError("No valid XRD data found."
                         + ("\n" + "\n".join(skipped) if skipped else ""))
    return core_levels


def read_file(path):
    """One XRD file (any supported format) -> {sheet: core level}."""
    return _import_paths([str(path)])


def read_folder(paths):
    """Every XRD file among *paths* (or in a folder) as one project."""
    files = _expand(paths, XRD_EXTENSIONS)
    if not files:
        raise ValueError("No .xrdml/.raw/.asc/.xy/.uxd files found.")
    return _import_paths(files)


def sniff_bruker_raw(path):
    """Bruker/Siemens RAW magic: 'RAW ' (v1), 'RAW2', 'RAW1.01' (v3),
    'RAW4.00' (v4) — a .raw from any other vendor does not start so."""
    with open(path, 'rb') as fh:
        head = fh.read(8)
    return re.match(rb'RAW[ 0-9]', head) is not None


def _never(_path):
    return False


FORMATS = [
    Format("XRD", "PANalytical XRDML (.xrdml)", (".xrdml",), read_file),
    Format("XRD", "Bruker RAW (.raw)", (".raw",), read_file,
           sniff=sniff_bruker_raw),
    Format("XRD", "2θ / intensity text (.asc/.xy/.csv/.txt/.dat/.uxd)",
           TEXT_EXTENSIONS, read_file, sniff=_never),
    Format("XRD", "Multiple files (folder)", XRD_EXTENSIONS, read_folder,
           sniff=_never, multi=True),
]
