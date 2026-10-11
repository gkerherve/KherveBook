"""Diamond Light Source import — XPS / HAXPES and XAS (I09, B07, I10).

A wx-free port of three KherveFittingPro importers:

* ``libraries/FileMenu/Diamond_NXS_Import.py`` — NeXus ``.nxs`` written
  by GDA: XPS analyser regions (``read_xps``) and XAS ``jenergy`` scans
  (``read_xas``), one or several files as one project
  (``import_nxs_files``); which of the two a file is comes from its own
  ``detect``.
* ``libraries/FileMenu/Diamond_B07_DAT_Import.py`` — B07 XPS text exports
  (``binding_energy<TAB>intensity<TAB>spectrum_1…``), rows planned from
  the file names (``parse_name`` / ``plan_rows``).
* ``libraries/FileMenu/XAS_Import.py`` — B07 XAS text files (photon
  energy first column, signal last, normalised to 10000 at the first
  point), sheets ``XAS~<edge>~`` / ``XAS~<edge>~<n>``.

KherveFitting's questions take their default answers: counts per second
for NeXus XPS, average per scan for B07 .dat, edge "Co-L" for B07 XAS.
ARPES NeXus files (an analyser group holding ``data`` + ``angles`` +
``energies``) are left to an ARPES reader: the sniffs here refuse them.

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
from .kfitwrite import core_level
from .vamas import normalize_sheet_name, phi_region_base


# ===========================================================================
# NeXus (.nxs) — Diamond_NXS_Import.py
# ===========================================================================

# Groups under /entry that are never spectra
_SKIP_GROUPS = {'instrument', 'before_scan', 'user01', 'analyser', 'sample',
                'diamond_scan', 'notes', 'ew4000', 'keys', 'monitor'}
_XPS_PAIRS = (('energies', 'spectrum_data'), ('binding_energy', 'spectrum'),
              ('energies', 'spectrum'))
_I0_NAMES = ('jI0', 'I0', 'i0', 'iI0', 'mirror_current', 'm4c1')
_TEY_NAMES = ('sdc', 'tey', 'TEY', 'drain_current')
_XAS_ENERGY_NAMES = ('jenergy', 'energy', 'pgmenergy', 'ienergy',
                     'dcmenergy')

# Absorption edges (eV) for naming an XAS sheet from its energy range
_EDGES = [
    ('C-K', 284), ('N-K', 400), ('Ti-L', 456), ('O-K', 531), ('V-L', 513),
    ('Cr-L', 575), ('Mn-L', 640), ('F-K', 685), ('Fe-L', 707), ('Co-L', 778),
    ('Ni-L', 853), ('Cu-L', 933), ('Zn-L', 1022), ('Na-K', 1071),
    ('Mg-K', 1303), ('Al-K', 1560), ('Si-K', 1839), ('P-K', 2146),
    ('S-K', 2472), ('Cl-K', 2822), ('K-K', 3608), ('Ca-K', 4038),
    ('Ce-M', 884), ('La-M', 836), ('Ba-M', 781), ('Sr-L', 1940),
]


def _txt(value):
    if isinstance(value, bytes):
        return value.decode('utf-8', 'replace').strip()
    if isinstance(value, np.ndarray):
        flat = value.reshape(-1)
        return _txt(flat[0]) if flat.size else ''
    return str(value).strip()


def _scalar(h5, path):
    try:
        arr = np.asarray(h5[path][()]).reshape(-1)
        return float(arr[0]) if arr.size else None
    except (KeyError, TypeError, ValueError):
        return None


def _string(h5, path):
    try:
        return _txt(h5[path][()])
    except (KeyError, TypeError, ValueError):
        return ''


def _entry(h5):
    keys = list(h5.keys())
    for name in ('entry1', 'entry'):
        if name in keys:
            return name
    if not keys:
        raise ValueError("The NeXus file has no entry.")
    return keys[0]


def beamline_of(h5, entry):
    return (_string(h5, f'{entry}/instrument/beamline')
            or _string(h5, f'{entry}/instrument/name')).upper()


def _xps_regions(h5, entry):
    import h5py
    head = h5[entry]
    regions = []
    for name in head:
        if name in _SKIP_GROUPS or not isinstance(head[name], h5py.Group):
            continue
        group = head[name]
        for x_name, y_name in _XPS_PAIRS:
            if x_name in group and y_name in group:
                regions.append((name, x_name, y_name))
                break
    return regions


def _xas_channels(h5, entry):
    """{channel name: (energy array, data array)} of a jenergy-type scan."""
    import h5py
    found = {}
    for base in (entry, f'{entry}/instrument'):
        if base not in h5:
            continue
        for name, group in h5[base].items():
            if not isinstance(group, h5py.Group) or name in found \
                    or 'data' not in group:
                continue
            energy = None
            for e_name in _XAS_ENERGY_NAMES:
                if e_name in group:
                    energy = np.asarray(group[e_name][()],
                                        dtype=float).reshape(-1)
                    break
            if energy is None and f'{entry}/instrument/jenergy/value' in h5:
                energy = np.asarray(h5[f'{entry}/instrument/jenergy/value'][()],
                                    dtype=float).reshape(-1)
            data = np.asarray(group['data'][()])
            if energy is None or data.dtype.kind not in 'fiu':
                continue
            data = data.astype(float).reshape(-1)
            if data.size > 3 and energy.size == data.size:
                found[name] = (energy, data)
    return found


def detect(file_path):
    """'XPS', 'XAS' or None for a Diamond NeXus file (KherveFitting's)."""
    try:
        import h5py
        with h5py.File(file_path, 'r') as h5:
            entry = _entry(h5)
            if _xps_regions(h5, entry):
                return 'XPS'
            channels = _xas_channels(h5, entry)
            if any(n in channels for n in _TEY_NAMES) or len(channels) >= 2:
                return 'XAS'
    except Exception:
        return None
    return None


def is_arpes_nexus(file_path):
    """True for an ARPES NeXus layout (KherveFitting's ARPES importer: a
    group holding ``data`` (2-D or more) with ``angles`` and ``energies``,
    e.g. Diamond I05's /entry1/analyser)."""
    try:
        import h5py
        hits = []

        def visit(_name, obj):
            if isinstance(obj, h5py.Group) and 'data' in obj \
                    and 'angles' in obj and 'energies' in obj:
                data = obj['data']
                if isinstance(data, h5py.Dataset) and data.ndim >= 2:
                    hits.append(_name)
                    return True
            return None

        with h5py.File(file_path, 'r') as h5:
            h5.visititems(visit)
        return bool(hits)
    except Exception:
        return False


def sniff_nxs_xps(path):
    return str(path).lower().endswith('.nxs') and detect(path) == 'XPS' \
        and not is_arpes_nexus(path)


def sniff_nxs_xas(path):
    return str(path).lower().endswith('.nxs') and detect(path) == 'XAS' \
        and not is_arpes_nexus(path)


def _nxs_core_level_name(region):
    """'O1s_2keV' -> 'O1s'; anything without an orbital keeps its name."""
    m = re.search(r'([A-Z][a-z]?\d[spdf]\d?)', region)
    return normalize_sheet_name(phi_region_base(m.group(1))) if m else region


def read_xps(file_path, cps=True):
    import h5py
    records = []
    with h5py.File(file_path, 'r') as h5:
        entry = _entry(h5)
        beamline = beamline_of(h5, entry)
        sample = _string(h5, f'{entry}/sample/name')
        for region, x_name, y_name in _xps_regions(h5, entry):
            g = h5[f'{entry}/{region}']
            ins = f'{entry}/instrument/{region}'
            x = np.asarray(g[x_name][()], dtype=float).reshape(-1)
            y = np.asarray(g[y_name][()], dtype=float)
            if y.ndim > 1:                      # slices / angles: sum them
                y = y.reshape(-1, y.shape[-1]).sum(axis=0)
            n = min(x.size, y.size)
            x, y = x[:n], y[:n]

            hv = (_scalar(h5, f'{entry}/{region}/excitation_energy')
                  or _scalar(h5, f'{ins}/excitation_energy')
                  or _scalar(h5, f'{ins}/photon_energy'))
            mode = _string(h5, f'{ins}/energy_mode') or 'Binding'
            if mode.lower().startswith('kin') and hv:
                x = hv - x                       # KE -> BE
            step = (_scalar(h5, f'{ins}/step_time')
                    or _scalar(h5, f'{ins}/count_time'))
            iters = _scalar(h5, f'{ins}/number_of_iterations') or 1.0
            scale = 1.0
            if cps and step:
                scale = 1.0 / (step * iters)
            y = y * scale

            exp = {
                'Sample ID': sample if sample and sample != 'Not set' else
                os.path.splitext(os.path.basename(file_path))[0],
                'Technique': 'XPS',
                'Instrument': f"Diamond {beamline}".strip(),
                'Region Name': region,
                'Species & Transition': region,
                'Source Label': 'Synchrotron',
                'Source Energy': f"{hv:.2f}" if hv else '',
                'Excitation Energy': f"{hv:.2f}" if hv else '',
                'Pass Energy': (_txt(h5[f'{ins}/pass_energy'][()])
                                if f'{ins}/pass_energy' in h5 else ''),
                'Lens Mode': _string(h5, f'{ins}/lens_mode'),
                'Acquisition Mode': _string(h5, f'{ins}/acquisition_mode'),
                'Energy Mode': mode,
                'Step Time': f"{step:g}" if step else '',
                'Number of scans': f"{iters:g}",
                'Intensity': ('counts per second (counts / (step time x '
                              'iterations))' if scale != 1.0
                              else 'raw counts'),
                'Date': _string(h5, f'{entry}/diamond_scan/start_time')[:10],
                'Experiment': _string(h5, f'{entry}/experiment_identifier'),
                'Scan': _string(h5, f'{entry}/diamond_scan/entry_identifier'),
                'Source File': os.path.basename(file_path),
            }
            records.append({'name': _nxs_core_level_name(region), 'x': x,
                            'y': y, 'exp': exp})
    return records


def guess_edge(energy):
    """Absorption edge label for an XAS energy range ('O-K'), or ''."""
    lo, hi = float(np.nanmin(energy)), float(np.nanmax(energy))
    inside = [(abs(e - (lo + 0.2 * (hi - lo))), name) for name, e in _EDGES
              if lo - 5 <= e <= hi]
    return min(inside)[1] if inside else ''


def read_xas(file_path):
    import h5py
    with h5py.File(file_path, 'r') as h5:
        entry = _entry(h5)
        beamline = beamline_of(h5, entry)
        channels = _xas_channels(h5, entry)
        base_exp = {
            'Sample ID': os.path.splitext(os.path.basename(file_path))[0],
            'Technique': 'XAS',
            'Instrument': f"Diamond {beamline}".strip(),
            'Polarisation': _string(h5,
                                    f'{entry}/instrument/polarisation/value'),
            'Date': _string(h5, f'{entry}/diamond_scan/start_time')[:10],
            'Experiment': _string(h5, f'{entry}/experiment_identifier'),
            'Scan': _string(h5, f'{entry}/diamond_scan/entry_identifier'),
            'Scan Command': _string(h5, f'{entry}/diamond_scan/scan_command'),
            'Source File': os.path.basename(file_path),
        }
    i0_name = next((n for n in _I0_NAMES if n in channels), None)
    tey_name = next((n for n in _TEY_NAMES if n in channels), None)
    if not channels:
        return [], ''
    energy = channels[tey_name or next(iter(channels))][0]
    if np.nanmax(energy) < 20:                   # keV -> eV
        energy = energy * 1000.0
    edge = guess_edge(energy)
    order = np.argsort(energy)
    energy = energy[order]
    i0 = channels[i0_name][1][order] if i0_name else None

    def norm(sig):
        with np.errstate(divide='ignore', invalid='ignore'):
            return np.where(i0 != 0, sig / i0, np.nan)

    records = []
    label = edge or 'XAS'
    for name, (_e, data) in channels.items():
        if name == i0_name:
            continue
        data = data[order]
        tag = 'TEY' if name == tey_name else name
        if i0 is not None:
            records.append({
                'name': (f"XAS~{label}~" if name == tey_name
                         else f"XAS~{label}-{tag}-norm~"),
                'x': energy, 'y': norm(data),
                'exp': dict(base_exp, **{
                    'Signal': f'{tag} / I0 ({name} / {i0_name})',
                    'Species & Transition': label})})
        records.append({'name': f"XAS~{label}-{tag}~", 'x': energy, 'y': data,
                        'exp': dict(base_exp, **{
                            'Signal': f'{tag} raw ({name})',
                            'Species & Transition': label})})
    if i0 is not None:
        records.append({'name': f"XAS~{label}-I0~", 'x': energy, 'y': i0,
                        'exp': dict(base_exp, **{
                            'Signal': f'I0 ({i0_name})',
                            'Species & Transition': label})})
    return records, edge


def _row_name(base, row):
    """Sheet name for Sample Manager row *row* (0 = the bare name)."""
    return base if row == 0 else f"{base}{row}"


def import_nxs_files(paths, cps=True):
    """Diamond .nxs files (XPS or XAS, each detected) as one project — one
    Sample Manager row per file, in the order given. Files that are neither
    are skipped, as KherveFitting does after warning."""
    paths = [str(p) for p in paths if p]
    kinds = {p: detect(p) for p in paths}
    usable = [p for p in paths if kinds[p]]
    if not usable:
        raise ValueError("Not a Diamond XPS/XAS NeXus file (no analyser "
                         "region and no jenergy/TEY scan found): "
                         + ", ".join(os.path.basename(p) for p in paths))
    core_levels = {}
    for row, path in enumerate(usable):
        if kinds[path] == 'XPS':
            records = read_xps(path, cps=cps)
        else:
            records, _edge = read_xas(path)
        seen = {}
        for rec in records:
            # Two regions of one core level in a file (e.g. two photon
            # energies) go to the next free rows of that column
            base = rec['name']
            k = seen.get(base, 0)
            seen[base] = k + 1
            name = (_row_name(base, row + k * len(usable)) if k
                    else _row_name(base, row))
            y = np.asarray(rec['y'], dtype=float)
            ok = np.isfinite(y)
            core_levels[name] = core_level(
                name, be_values=np.asarray(rec['x'])[ok], plot_values=y[ok],
                experimental_info=rec['exp'])
    if not core_levels:
        raise ValueError("No spectra found in the selected file(s).")
    return core_levels


def read_nxs(paths):
    """Reader of the NeXus Formats (a list of paths)."""
    if isinstance(paths, (str, os.PathLike)):
        paths = [paths]
    return import_nxs_files(paths, cps=True)


# ===========================================================================
# B07 XPS text exports (.dat) — Diamond_B07_DAT_Import.py
# ===========================================================================

HEADER_X = 'binding_energy'
HEADER_Y = 'intensity'


def _natural_key(path):
    return [int(t) if t.isdigit() else t.lower()
            for t in re.split(r'(\d+)', os.path.basename(path))]


def is_b07_xps_dat(path):
    """A .dat whose first line is the binding_energy / intensity header."""
    if not str(path).lower().endswith('.dat'):
        return False
    try:
        with open(path, 'r', errors='replace') as fh:
            head = fh.readline().strip().lower().split('\t')
    except OSError:
        return False
    return len(head) >= 2 and head[0] == HEADER_X and head[1] == HEADER_Y


def parse_name(path):
    """File-name fields: scan, region, temperature, condition, pass energy,
    photon energy, and the condition tags as written."""
    stem = os.path.splitext(os.path.basename(path))[0]
    tok = stem.split('_')
    scan_nums = re.findall(r'\d+', tok[0]) if tok else []
    scan = int(scan_nums[-1]) if scan_nums else None
    region = tok[1] if len(tok) > 1 else stem
    rest = [t for t in tok[2:] if t.upper() != 'XPS']
    pe = next((float(m.group(1)) for t in rest
               for m in [re.fullmatch(r'PE(\d+(?:\.\d+)?)', t, re.I)] if m),
              None)
    nums = [int(t) for t in rest if t.isdigit()]
    temp = nums[0] if nums else None
    hv = nums[-1] if len(nums) >= 2 else None   # a lone number: temperature
    cond = next((t.upper() for t in rest if re.fullmatch(r'[Dd]\d+', t)), '')
    tags = [t for t in rest if not re.fullmatch(r'PE\d+(?:\.\d+)?', t, re.I)
            and not re.fullmatch(r'\d+min', t, re.I) and t != str(hv)]
    extra = [t for t in rest if not t.isdigit()
             and not re.fullmatch(r'[Dd]\d+', t)
             and not re.fullmatch(r'PE\d+(?:\.\d+)?', t, re.I)
             and not re.fullmatch(r'\d+min', t, re.I)]
    label = ' '.join(t for t in ([str(temp)] if temp is not None else [])
                     + ([cond] if cond else []) + extra) or stem
    return {'scan': scan, 'region': region, 'temp': temp, 'cond': cond,
            'pe': pe, 'hv': hv, 'tags': '_'.join(tags), 'label': label,
            'stem': stem}


def read_dat(path, average=False):
    """(BE descending, intensity, number of scans)."""
    data = np.genfromtxt(path, delimiter='\t', names=True, dtype=float,
                         encoding='utf-8')
    names = [n.lower() for n in data.dtype.names]
    x = np.asarray(data[data.dtype.names[names.index(HEADER_X)]], dtype=float)
    y = np.asarray(data[data.dtype.names[names.index(HEADER_Y)]], dtype=float)
    n_scans = sum(1 for n in names if n.startswith('spectrum'))
    if average and n_scans:
        y = y / n_scans
    ok = np.isfinite(x) & np.isfinite(y)
    x, y = x[ok], y[ok]
    order = np.argsort(x)[::-1]                 # descending BE
    return x[order], y[order], n_scans


def _b07_core_level_name(region):
    if region.lower().startswith('survey'):
        return 'Survey'
    m = re.search(r'([A-Z][a-z]?\d[spdf]\d?)', region)
    return normalize_sheet_name(phi_region_base(m.group(1))) if m else region


def _row_label(meta):
    return f"{meta['label']} - {meta['hv']} eV" if meta['hv'] \
        else meta['label']


def plan_rows(metas):
    """Row per file: one row per (condition, photon energy) in scan order;
    a core level already in that row starts another row. Returns (row per
    file, label per row)."""
    rows, assign = [], []
    for meta in metas:
        key = ((meta['temp'], meta['cond'], meta['hv'])
               if meta['hv'] or meta['cond'] else meta['stem'])
        name = _b07_core_level_name(meta['region'])
        target = next((i for i, r in enumerate(rows)
                       if r[0] == key and name not in r[2]), None)
        if target is None:
            repeat = sum(1 for r in rows if r[0] == key)
            label = _row_label(meta) + (f" ({repeat + 1})" if repeat else "")
            rows.append([key, label, set()])
            target = len(rows) - 1
        rows[target][2].add(name)
        assign.append(target)
    return assign, [r[1] for r in rows]


def import_b07_dat_files(paths, average=True):
    """Diamond B07 XPS .dat files as one project ({sheet: core level})."""
    paths = sorted((str(p) for p in paths if p),
                   key=lambda p: (parse_name(p)['scan'] or 0,
                                  _natural_key(p)))
    good = [p for p in paths if is_b07_xps_dat(p)]
    if not good:
        raise ValueError("Not a Diamond B07 XPS .dat file (first line must "
                         "be 'binding_energy<TAB>intensity...')")
    metas = [parse_name(p) for p in good]
    rows, labels = plan_rows(metas)
    core_levels = {}
    for path, meta, row in zip(good, metas, rows):
        x, y, n_scans = read_dat(path, average=average)
        base = _b07_core_level_name(meta['region'])
        name = base if row == 0 else f"{base}{row}"
        hv = meta['hv']
        exp = {
            'Sample ID': labels[row],
            'Technique': 'XPS',
            'Instrument': 'Diamond B07',
            'Region Name': meta['region'],
            'Species & Transition': meta['region'],
            'Source Label': 'Synchrotron',
            'Source Energy': f"{hv:.2f}" if hv else '',
            'Excitation Energy': f"{hv:.2f}" if hv else '',
            'Pass Energy': f"{meta['pe']:g}" if meta['pe'] is not None
            else '',
            'Number of scans': str(n_scans),
            'Intensity': ('average per scan (intensity / number of scans)'
                          if average
                          else 'sum of the scans (file intensity column)'),
            'Scan': str(meta['scan'] or ''),
            'Condition': meta['tags'],
            'Source File': os.path.basename(path),
        }
        core_levels[name] = core_level(name, be_values=x, plot_values=y,
                                       experimental_info=exp)
    if not core_levels:
        raise ValueError("No spectra found in the selected file(s).")
    return core_levels


def read_b07_dat(path):
    return import_b07_dat_files([path])


def read_b07_dat_files(paths):
    return import_b07_dat_files(paths)


# ===========================================================================
# B07 XAS text files (.txt / .dat) — XAS_Import.py
# ===========================================================================

#: XAS_Import._ask_edge's default answer
DEFAULT_EDGE = "Co-L"


def _parse_xas_file(file_path):
    """[[photon energy, intensity]] with intensity = raw / first raw * 1e4
    (X = first column, Y = last column, header line skipped)."""
    raw_data = []
    with open(file_path, 'r', encoding='utf-8', errors='ignore') as fh:
        lines = fh.readlines()
    for line in lines[1:]:
        line = line.strip()
        if not line:
            continue
        parts = line.split('\t')
        if len(parts) < 2:
            parts = line.split()
        if len(parts) < 2:
            continue
        try:
            raw_data.append([float(parts[0]), float(parts[-1])])
        except ValueError:
            continue
    if not raw_data:
        raise ValueError("No valid numeric data rows found in the file.")
    first_raw = raw_data[0][1]
    if first_raw == 0:
        raise ValueError("First raw intensity value is zero; cannot "
                         "normalise.")
    return [[e, (r / first_raw) * 10000] for e, r in raw_data]


def _make_sheet_name(edge_name, index=None):
    base = f"XAS~{edge_name}~" if edge_name else "XAS~"
    return base if index is None else f"{base}{index}"


def _xas_sheet(sheet_name, data):
    """The core level ``add_core_level_Data`` reads back from the sheet
    ``_write_xas_sheet`` writes (A energy, B intensity, both to 2 decimals;
    no Experimental Description column, so no ExperimentalInfo)."""
    be = [float(f"{e:.2f}") for e, _ in data]
    raw = [float(f"{v:.2f}") for _, v in data]
    cl = {'B.E.': be, 'Raw Data': raw, 'Corrected Data': list(raw),
          'Transmission': [1.0] * len(raw), 'Name': sheet_name}
    if be:
        cl['Background'] = {'Bkg Y': cl['Raw Data'], 'Bkg Type': '',
                            'Bkg Low': float(f"{min(be):.2f}"),
                            'Bkg High': float(f"{max(be):.2f}"),
                            'Bkg Offset Low': 0, 'Bkg Offset High': 0}
    return cl


def read_b07_xas(path, edge=DEFAULT_EDGE):
    """One B07 XAS file -> {'XAS~<edge>~': core level}."""
    name = _make_sheet_name(edge)
    return {name: _xas_sheet(name, _parse_xas_file(path))}


def read_b07_xas_files(paths, edge=DEFAULT_EDGE):
    """Several B07 XAS files -> sheets 'XAS~<edge>~0', '~1'… (a file that
    cannot be parsed is skipped, keeping its index unused)."""
    if isinstance(paths, (str, os.PathLike)):
        paths = [paths]
    out = {}
    for idx, path in enumerate(paths):
        name = _make_sheet_name(edge, idx)
        try:
            data = _parse_xas_file(path)
        except ValueError:
            continue
        out[name] = _xas_sheet(name, data)
    if not out:
        raise ValueError("No XAS files could be processed.")
    return out


def sniff_b07_xas(path):
    """A B07 XAS text file: a header whose first field names an energy
    (``pgm_energy``…, not binding/kinetic), then tab-separated rows of 3 or
    4 numbers starting with a photon energy (20-5000 eV). A B07 XPS .dat
    (binding_energy header) is not one."""
    p = str(path).lower()
    if not p.endswith(('.txt', '.dat')) or is_b07_xps_dat(path):
        return False
    try:
        with open(path, 'r', encoding='utf-8', errors='ignore') as fh:
            head = fh.readline()
            rows = []
            for line in fh:
                if line.strip():
                    rows.append(line.strip())
                if len(rows) >= 5:
                    break
    except OSError:
        return False
    fields = head.strip().split('\t')
    first = fields[0].strip().lower()
    if len(fields) < 2 or 'energy' not in first \
            or 'binding' in first or 'kinetic' in first:
        return False
    if not rows:
        return False
    for row in rows:
        parts = row.split('\t')
        if len(parts) not in (3, 4):
            return False
        try:
            values = [float(v) for v in parts]
        except ValueError:
            return False
        if not 20.0 <= values[0] <= 5000.0:
            return False
    return True


def _never(_path):
    """Multi-file entries are chosen from the menu, never auto-detected."""
    return False


# ===========================================================================
# Formats (KherveFitting's Import menu)
# ===========================================================================

_DLS = "Diamond Light Source"

FORMATS = [
    Format("XPS", "NeXus (I09 / B07 / I10) (.nxs)", (".nxs",), read_nxs,
           group=_DLS, sniff=sniff_nxs_xps, multi=True, needs=("h5py",)),
    Format("XPS", "B07 XPS (.dat)", (".dat",), read_b07_dat, group=_DLS,
           sniff=is_b07_xps_dat),
    Format("XPS", "B07 XPS (.dat) - one or more files", (".dat",),
           read_b07_dat_files, group=_DLS, sniff=_never, multi=True),
    Format("XAS", "Diamond-B07 file (.txt/.dat)", (".txt", ".dat"),
           read_b07_xas, sniff=sniff_b07_xas),
    Format("XAS", "Diamond-B07 multiple files (folder)", (".txt", ".dat"),
           read_b07_xas_files, sniff=_never, multi=True),
    Format("XAS", "Diamond I09 / B07 NeXus (.nxs)", (".nxs",), read_nxs,
           sniff=sniff_nxs_xas, multi=True, needs=("h5py",)),
]
