"""UV-Vis, photoluminescence and spectroscopic-ellipsometry import.

Most exports are delimited text (.csv / .txt / .dat / .asc): a wavelength
column and one or more value columns under any amount of header text —
Shimadzu UVProbe, PerkinElmer Lambda .asc, JASCO, Ocean Optics, Horiba
FluoroLog. Agilent/Varian **Cary** batch .csv files (sample names on
line one, repeated ``Wavelength (nm),Abs`` headers on line two) give one
sheet per sample; J.A. Woollam ellipsometry ASCII (λ or eV, AOI, Ψ, Δ)
gives one Ellips sheet per angle plus an ``Ellips~Delta`` companion.

Sheets are UVvis, UVvis1, … / PL, PL1, … / Ellips, Ellips~Delta, …,
built by KherveFitting's ``build_generic_sheet``.

Ported from KherveFittingPro (``libraries/FileMenu/Optical_Import.py``:
``parse_optical_file``, ``parse_cary_csv``, ``_import_two_column``,
``_import_ellips_paths``), wx-free.

Copyright (C) 2026 Gwilherm Kerherve

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.
"""

import os

from . import Format
from .kfgeneric import (TECH_ELLIPS, TECH_PL, TECH_UVVIS, as_list,
                        build_generic_sheet, fail_if_empty, head_text,
                        parse_columns_file,
                        unique_sheet_name as _unique_sheet_name)


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------

def _cary_y_mode(header_token):
    """Map a Cary column header (Abs, %T, %R...) to a UVVIS_Y_Mode."""
    token = header_token.strip().upper()
    if 'T' in token and '%' in token:
        return 'transmittance'
    if 'R' in token and '%' in token:
        return 'reflectance'
    return 'absorbance'


def parse_cary_csv(file_path):
    """Parse an Agilent/Varian Cary batch .csv.

    Returns a list of {'name', 'rows', 'y_mode'} - one entry per sample pair
    of columns - or None when the file is not in the Cary layout (no repeated
    'Wavelength' header on the second line).
    """
    with open(file_path, 'r', errors='ignore') as fh:
        lines = fh.read().splitlines()
    if len(lines) < 3:
        return None
    header = [t.strip() for t in lines[1].split(',')]
    wl_cols = [i for i, t in enumerate(header)
               if t.lower().startswith(('wavelength', 'nm'))]
    if not wl_cols:
        return None

    names = [t.strip() for t in lines[0].split(',')]
    samples = []
    for col in wl_cols:
        if col + 1 >= len(header):
            continue
        name = names[col] if col < len(names) and names[col] else ''
        samples.append({'name': name, 'col': col,
                        'y_mode': _cary_y_mode(header[col + 1]),
                        'rows': []})
    if not samples:
        return None

    for line in lines[2:]:
        cells = line.split(',')
        got_any = False
        for sample in samples:
            col = sample['col']
            if col + 1 >= len(cells):
                continue
            try:
                x = float(cells[col])
                y = float(cells[col + 1])
            except ValueError:
                continue
            sample['rows'].append((x, y))
            got_any = True
        if not got_any and any(s['rows'] for s in samples):
            break                       # end of the data block: audit trail next
    samples = [s for s in samples if len(s['rows']) >= 3]
    return samples or None


def parse_optical_file(file_path):
    """Parse any supported UV-Vis / PL text export.

    Returns a list of {'name', 'rows', 'y_mode'} - several entries for a Cary
    batch file, one (with name '' and y_mode None, meaning 'infer') for
    everything the generic column parser handles.
    """
    if file_path.lower().endswith('.csv'):
        samples = parse_cary_csv(file_path)
        if samples:
            return [{'name': s['name'], 'rows': s['rows'],
                     'y_mode': s['y_mode']} for s in samples]
    rows, _meta = parse_columns_file(file_path)
    if not rows:
        return []
    return [{'name': '', 'rows': [(r[0], r[1]) for r in rows],
             'y_mode': None}]


EV_NM = 1239.84193


def _looks_like_energy_axis(x_values):
    """A 'wavelength' column that never exceeds 10 is photon energy in eV."""
    return bool(x_values) and 0.1 < max(x_values) < 10.0


def _split_ellips_columns(rows):
    """Blocks of (x, psi, delta, aoi) from parsed ellipsometry rows.

    Two columns is Ψ only; three is λ, Ψ, Δ. Four or more is the Woollam
    layout λ, AOI, Ψ, Δ when the second column is angle-like (20-90° with at
    most eight distinct values) - a multi-angle file yields one block per
    angle - otherwise λ, Ψ, Δ plus ignored extras (depolarisation etc.).
    """
    n_cols = len(rows[0])
    if n_cols == 2:
        return [([r[0] for r in rows], [r[1] for r in rows], None, None)]
    if n_cols >= 4:
        col2 = [r[1] for r in rows]
        distinct = sorted({round(v, 3) for v in col2})
        if 20.0 <= min(col2) and max(col2) <= 90.0 and len(distinct) <= 8:
            blocks = []
            for angle in distinct:
                sub = [r for r in rows if round(r[1], 3) == angle]
                blocks.append(([r[0] for r in sub], [r[2] for r in sub],
                               [r[3] for r in sub], float(angle)))
            return blocks
    return [([r[0] for r in rows], [r[1] for r in rows],
              [r[2] for r in rows], None)]


# ---------------------------------------------------------------------------
# Project building

_UVVIS_MODE_LABELS = {
    'absorbance': 'Absorbance (a.u.)',
    'transmittance': 'Transmittance (%)',
    'reflectance': 'Reflectance (%)',
}



# ---------------------------------------------------------------------------
# Project building
# ---------------------------------------------------------------------------

def _two_column(file_paths, technique, base):
    """``_import_two_column``: one sheet per spectrum. A Cary batch file
    yields several sheets, everything else one per file."""
    core_levels = {}
    skipped = []
    for file_path in sorted(file_paths):
        try:
            spectra = parse_optical_file(file_path)
        except Exception as e:
            skipped.append(f"{os.path.basename(file_path)}: {e}")
            continue
        if not spectra:
            skipped.append(f"{os.path.basename(file_path)}: no numeric data")
            continue
        for spectrum in spectra:
            rows = sorted(spectrum['rows'], key=lambda r: r[0])
            name = _unique_sheet_name(base, core_levels)
            source = (spectrum['name']
                      or os.path.splitext(os.path.basename(file_path))[0])
            sheet = build_generic_sheet(
                technique, name, [r[0] for r in rows], [r[1] for r in rows],
                source_name=source)
            # A Cary header names the ordinate outright - that beats the
            # magnitude heuristic in build_generic_sheet.
            if technique == TECH_UVVIS and spectrum.get('y_mode'):
                mode = spectrum['y_mode']
                sheet['UVVIS_Y_Mode'] = mode
                sheet['UVVIS_Y_Label'] = _UVVIS_MODE_LABELS[mode]
            core_levels[name] = sheet
    return fail_if_empty(core_levels, skipped)


def _ellips(file_paths):
    """``_import_ellips_paths``: each measured block (one per angle of
    incidence in a Woollam multi-angle file) gives an Ellips sheet (Ψ)
    and, when it carries Δ, an Ellips~Delta companion sheet."""
    core_levels = {}
    skipped = []
    for file_path in sorted(file_paths):
        try:
            rows, _meta = parse_columns_file(file_path)
        except Exception as e:
            skipped.append(f"{os.path.basename(file_path)}: {e}")
            continue
        if not rows:
            skipped.append(f"{os.path.basename(file_path)}: no numeric data")
            continue
        rows.sort(key=lambda r: r[0])
        source = os.path.splitext(os.path.basename(file_path))[0]

        for x, psi, delta, aoi in _split_ellips_columns(rows):
            if _looks_like_energy_axis(x):
                order = sorted(range(len(x)), key=lambda i: EV_NM / x[i])
                x = [EV_NM / x[i] for i in order]
                psi = [psi[i] for i in order]
                if delta is not None:
                    delta = [delta[i] for i in order]

            name = _unique_sheet_name('Ellips', core_levels)
            label = source if aoi is None else f"{source} @ {aoi:g}°"
            sheet = build_generic_sheet(TECH_ELLIPS, name, x, psi,
                                        source_name=source,
                                        extra_values=delta)
            sheet['ELLIPS_Label'] = label
            if aoi is not None:
                sheet['ELLIPS_AOI_deg'] = float(aoi)
            core_levels[name] = sheet

            if delta is not None:
                suffix = name[len('Ellips'):]
                delta_name = f'Ellips~Delta{suffix}'
                delta_sheet = build_generic_sheet(TECH_ELLIPS, delta_name, x,
                                                  delta, source_name=source)
                delta_sheet.update({
                    'ELLIPS_Y_Label': 'Δ (°)',
                    'ELLIPS_Quantity': 'delta',
                    'ELLIPS_Psi': list(psi),
                    'ELLIPS_Delta': list(delta),
                    'ELLIPS_Label': label,
                })
                if aoi is not None:
                    delta_sheet['ELLIPS_AOI_deg'] = float(aoi)
                core_levels[delta_name] = delta_sheet
    return fail_if_empty(core_levels, skipped)


def read_uvvis(paths):
    return _two_column(as_list(paths), TECH_UVVIS, 'UVvis')


def read_pl(paths):
    return _two_column(as_list(paths), TECH_PL, 'PL')


def read_ellips(paths):
    return _ellips(as_list(paths))


def sniff_uvvis(path):
    """A Cary UV-Vis batch .csv (``Wavelength (nm),Abs|%T|%R`` pairs on
    line two) or a PerkinElmer ``PE UV`` .asc."""
    lines = head_text(path).splitlines()
    if not lines:
        return False
    if str(path).lower().endswith('.asc'):
        return lines[0].strip().upper().startswith('PE UV')
    if not str(path).lower().endswith('.csv') or len(lines) < 3:
        return False
    header = [t.strip() for t in lines[1].split(',')]
    pairs = [(header[i], header[i + 1]) for i in range(len(header) - 1)
             if header[i].lower().startswith('wavelength')]
    return bool(pairs) and all(
        y.strip().upper().replace(' ', '') in ('ABS', '%T', '%R', 'A',
                                               'ABSORBANCE')
        for _x, y in pairs)


_EXTS = (".csv", ".txt", ".dat", ".asc")

FORMATS = [
    Format("UV-Vis", "File(s) (.csv/.txt) - Cary / Shimadzu / generic",
           _EXTS, read_uvvis, sniff=sniff_uvvis, multi=True),
    Format("Photoluminescence",
           "File(s) (.csv/.txt) - Horiba / Ocean / generic", _EXTS, read_pl,
           sniff=lambda p: False, multi=True),
    Format("Ellipsometry", "Ψ/Δ file(s) (.csv/.txt) - Woollam / generic",
           _EXTS, read_ellips, sniff=lambda p: False, multi=True),
]
