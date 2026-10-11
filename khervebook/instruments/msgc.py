"""Mass-spectrometry and gas-chromatography import.

Mass spectra: two-column m/z / intensity text (MassHunter, Xcalibur,
LabSolutions spectrum exports — a centroided list is drawn as sticks)
and NIST ``.msp`` libraries, one sheet per record named after the
compound. Chromatograms: two-column time / signal text (ChemStation,
OpenLab, Chromeleon ASCII) and Shimadzu LabSolutions sectioned ``.txt``
exports, where only the ``[Chromatogram …]`` section is read; a time
axis in seconds is converted to minutes.

Sheets are MS, MS1, … and GC, GC1, …, built by KherveFitting's
``build_generic_sheet``.

Ported from KherveFittingPro (``libraries/FileMenu/MSGC_Import.py``:
``parse_ms_file``, ``parse_msp``, ``parse_gc_file``,
``_import_ms_paths``, ``_import_gc_paths``), wx-free.

Copyright (C) 2026 Gwilherm Kerherve

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.
"""

import os
import re

from . import Format
from .kfgeneric import (TECH_GC, TECH_MS, as_list, build_generic_sheet,
                        fail_if_empty, head_text, parse_columns_file,
                        unique_sheet_name as _unique_sheet_name)


# ---------------------------------------------------------------------------
# Mass-spectrum parsing
# ---------------------------------------------------------------------------

def parse_msp(file_path, max_spectra=50):
    """Parse a NIST .msp library file.

    Returns [{'name', 'rows'}] - one entry per record - or an empty list when
    the file carries no 'Num Peaks:' records at all.
    """
    spectra = []
    name, expecting, rows = '', 0, []
    with open(file_path, 'r', errors='ignore') as fh:
        for raw_line in fh:
            line = raw_line.strip()
            lower = line.lower()
            if lower.startswith('name:'):
                if rows:
                    spectra.append({'name': name, 'rows': rows})
                    if len(spectra) >= max_spectra:
                        return spectra
                name = line.partition(':')[2].strip()
                expecting, rows = 0, []
            elif lower.startswith('num peaks:'):
                try:
                    expecting = int(line.partition(':')[2].strip())
                except ValueError:
                    expecting = 0
            elif expecting and line:
                # Peak lines: 'mz int; mz int;' or 'mz int' or 'mz,int'
                for pair in re.split(r'[;\n]+', line):
                    tokens = [t for t in re.split(r'[\s,:]+', pair.strip())
                              if t]
                    if len(tokens) >= 2:
                        try:
                            rows.append((float(tokens[0]), float(tokens[1])))
                        except ValueError:
                            pass
    if rows:
        spectra.append({'name': name, 'rows': rows})
    return spectra


def _sticks_to_profile(rows):
    """A centroided stick list drawn as a line joins peak tips diagonally.
    Anchor every stick to zero on both sides so the spectrum draws as the
    familiar stick plot whatever the plot style."""
    profile = []
    for mz, intensity in sorted(rows):
        profile.append((mz - 0.01, 0.0))
        profile.append((mz, intensity))
        profile.append((mz + 0.01, 0.0))
    return profile


def parse_ms_file(file_path):
    """[{'name', 'rows'}] for any supported mass-spectrum file."""
    if file_path.lower().endswith('.msp'):
        spectra = parse_msp(file_path)
        return [{'name': s['name'],
                 'rows': _sticks_to_profile(s['rows'])} for s in spectra]
    rows, _meta = parse_columns_file(file_path, max_columns=2)
    if not rows:
        return []
    rows = [(r[0], r[1]) for r in rows]
    # A centroided export (far fewer points than the m/z span, all
    # non-negative) reads better as sticks.
    span = max(r[0] for r in rows) - min(r[0] for r in rows)
    if span > 10 and len(rows) < 0.8 * span:
        rows = _sticks_to_profile(rows)
    return [{'name': '', 'rows': rows}]


# ---------------------------------------------------------------------------
# Chromatogram parsing
# ---------------------------------------------------------------------------

def parse_gc_file(file_path):
    """(rows, in_seconds) for a chromatogram text file.

    Handles the Shimadzu LabSolutions sectioned layout by keeping only the
    '[Chromatogram ...]' section when one exists.
    """
    with open(file_path, 'r', errors='ignore') as fh:
        text = fh.read()

    in_seconds = False
    match = re.search(r'^\[Chromatogram[^\]]*\]\s*$(.*?)(?=^\[|\Z)', text,
                      re.MULTILINE | re.DOTALL | re.IGNORECASE)
    if match:
        section = match.group(1)
        in_seconds = bool(re.search(r'\(sec\)|Time\s*\(s\)', section,
                                    re.IGNORECASE))
        rows = []
        for line in section.splitlines():
            tokens = [t for t in re.split(r'[\t;,\s]+', line.strip()) if t]
            if len(tokens) >= 2:
                try:
                    rows.append((float(tokens[0]), float(tokens[1])))
                except ValueError:
                    pass
    else:
        parsed, _meta = parse_columns_file(file_path, max_columns=2)
        rows = [(r[0], r[1]) for r in parsed]
        header = text[:2000]
        in_seconds = bool(re.search(r'\(sec\)|Time\s*\(s\)', header,
                                    re.IGNORECASE))

    if not rows:
        return [], False
    if not in_seconds and len(rows) > 2:
        # No unit declared: a run longer than 200 'minutes' with sub-10-ms
        # sampling is a seconds axis in disguise.
        span = rows[-1][0] - rows[0][0]
        step = span / max(len(rows) - 1, 1)
        in_seconds = span > 200 and step < 0.05
    if in_seconds:
        rows = [(t / 60.0, y) for t, y in rows]
    return rows, in_seconds



# ---------------------------------------------------------------------------
# Readers
# ---------------------------------------------------------------------------

def read_ms(paths):
    """``_import_ms_paths``: every spectrum of every file, MS, MS1, …"""
    core_levels = {}
    skipped = []
    for file_path in sorted(as_list(paths)):
        try:
            spectra = parse_ms_file(file_path)
        except Exception as e:
            skipped.append(f"{os.path.basename(file_path)}: {e}")
            continue
        if not spectra:
            skipped.append(f"{os.path.basename(file_path)}: no numeric data")
            continue
        for spectrum in spectra:
            rows = sorted(spectrum['rows'], key=lambda r: r[0])
            name = _unique_sheet_name('MS', core_levels)
            source = (spectrum['name']
                      or os.path.splitext(os.path.basename(file_path))[0])
            core_levels[name] = build_generic_sheet(
                TECH_MS, name, [r[0] for r in rows], [r[1] for r in rows],
                source_name=source)
    return fail_if_empty(core_levels, skipped)


def read_gc(paths):
    """``_import_gc_paths``: one chromatogram per file, GC, GC1, …"""
    core_levels = {}
    skipped = []
    for file_path in sorted(as_list(paths)):
        try:
            rows, _secs = parse_gc_file(file_path)
        except Exception as e:
            skipped.append(f"{os.path.basename(file_path)}: {e}")
            continue
        if not rows:
            skipped.append(f"{os.path.basename(file_path)}: no numeric data")
            continue
        rows.sort(key=lambda r: r[0])
        name = _unique_sheet_name('GC', core_levels)
        source = os.path.splitext(os.path.basename(file_path))[0]
        core_levels[name] = build_generic_sheet(
            TECH_GC, name, [r[0] for r in rows], [r[1] for r in rows],
            source_name=source)
    return fail_if_empty(core_levels, skipped)


def sniff_ms(path):
    """Only a NIST .msp library is recognised on sight."""
    return str(path).lower().endswith('.msp')


def sniff_gc(path):
    """A Shimadzu LabSolutions export: a ``[Chromatogram …]`` section."""
    return re.search(r'^\[Chromatogram[^\]]*\]\s*$', head_text(path, 262144),
                     re.MULTILINE | re.IGNORECASE) is not None


FORMATS = [
    Format("MS", "Mass spectrum file(s) (.csv/.txt/.msp)",
           (".csv", ".txt", ".dat", ".asc", ".msp"), read_ms,
           sniff=sniff_ms, multi=True),
    Format("GC", "Chromatogram file(s) (.csv/.txt) - LabSolutions / generic",
           (".csv", ".txt", ".dat", ".asc"), read_gc, sniff=sniff_gc,
           multi=True),
]
