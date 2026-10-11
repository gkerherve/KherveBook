"""Igor Pro XPS import: ``.itx`` text waves and tab-separated ``.dat``.

* ``.itx``: ``IGOR`` on line 1, then ``WAVES 'name'`` / ``BEGIN`` …
  ``END`` blocks, each followed by ``X SetScale/P x start,step`` giving
  its binding-energy axis. Fit traces (``bck``, ``fitresult``, ``peak``)
  are skipped.
* ``.dat``: a header row of ``[All <core level>] <sample>`` labels over
  BE / intensity columns.

Each sample becomes the sheet ``<core level><index>`` (``C1s0``, ``O1s1``
…), its points reversed to run high → low BE, and counts normalised to 1
scaled ×10000 so two-decimal storage keeps them.

Ported from KherveFittingPro ``libraries/FileMenu/Igor_Import.py``
(``import_igor_itx_file``, ``import_igor_dat_file``,
``_open_imported_excel_file``), wx-free. KherveFitting writes those
sheets as two-decimal *text*, so its sheet refresh stops before re-reading
them and the values stay cut to two decimals — `xlsxflow` replays that.
Its "Multiple files" entry imports each file as its own project, so it
has no combined format here.

Copyright (C) 2026 Gwilherm Kerherve

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.
"""

import re

import numpy as np

from . import Format
from . import xlsxflow

SAMPLE_PATTERN = r'\[All (.*?)\] (\w+)'
_FIT_TERMS = ('bck', 'fitresult', 'peak')


def _lines(path):
    with open(path, 'r', encoding='utf-8', errors='ignore') as f:
        return f.readlines()


def _scale(values):
    """×10000 when the data are normalised (max below 100)."""
    if len(values) == 0:
        return 1
    return 10000 if max(values) < 100 else 1


def _write(wb, samples, series):
    """One sheet per sample: ``f"{x:.2f}"`` text, reversed."""
    names = []
    for idx, info in enumerate(samples):
        sheet_name = f"{info['core_level']}{idx}"
        ws = wb.create_sheet(sheet_name)
        names.append(sheet_name)
        pair = series(info)
        if pair is None:            # header only, as KherveFitting leaves it
            ws.set_columns(['BE', 'Raw Data'], [], [])
            continue
        be_values, data_values = pair
        scale = _scale(data_values)
        rows = list(zip(list(be_values)[::-1], list(data_values)[::-1]))
        ws.set_columns(['BE', 'Raw Data'],
                       [f"{be:.2f}" for be, _ in rows],
                       [f"{(y * scale):.2f}" for _, y in rows])
    return names


# ---------------------------------------------------------------------------
#  .itx
# ---------------------------------------------------------------------------

def parse_itx(path):
    """``{wave name: values, wave name + '_BE': axis}``."""
    lines = _lines(path)
    if not lines or lines[0].strip() != 'IGOR':
        raise ValueError("not a valid Igor ITX file (line 1 is not IGOR)")
    waves = {}
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        if line.startswith('WAVES'):
            m = re.search(r"WAVES[/\w]*\s+'([^']+)'", line)
            if not m:
                i += 1
                continue
            wave_name = m.group(1)
            if any(t in wave_name.lower() for t in _FIT_TERMS):
                i += 1
                continue
            i += 1
            while i < len(lines) and lines[i].strip() != 'BEGIN':
                i += 1
            if i >= len(lines):
                break
            i += 1
            values = []
            while i < len(lines) and lines[i].strip() != 'END':
                try:
                    values.append(float(lines[i].strip()))
                except ValueError:
                    pass
                i += 1
            if values:
                waves[wave_name] = np.array(values)
                i += 1
                if i < len(lines):
                    scale_line = lines[i].strip()
                    if scale_line.startswith('X SetScale'):
                        sm = re.search(r'x\s+([\d.]+),([\d.]+)', scale_line)
                        if sm:
                            start, step = float(sm.group(1)), \
                                float(sm.group(2))
                            waves[f'{wave_name}_BE'] = np.arange(
                                start, start + step * len(values),
                                step)[:len(values)]
        i += 1
    return waves


def _itx_samples(waves):
    samples = []
    for wave_name in sorted(waves.keys()):
        if '_BE' in wave_name:
            continue
        m = re.search(SAMPLE_PATTERN, wave_name)
        if m:
            samples.append({'sample_name': m.group(2),
                            'core_level': m.group(1).replace(' ', ''),
                            'wave_name': wave_name})
            continue
        cm = re.search(r'([A-Z][a-z]?\d[spdf])', wave_name)
        if cm:
            core = cm.group(1)
        elif ('_V' in wave_name or 'VB' in wave_name.upper()
              or 'valence' in wave_name.lower()):
            vm = re.search(r'_V\(([\d.]+)\s+to\s+([\d.]+)\)', wave_name)
            core = (f"VB_{vm.group(1)}to{vm.group(2)}" if vm else 'VB')
        elif 'eV' in wave_name:
            em = re.search(r'([\d.]+)\s*eV', wave_name)
            core = f"{em.group(1)}eV" if em else 'Spectrum'
        else:
            core = 'Unknown'
        samples.append({
            'sample_name': wave_name.strip("'").replace('.txt', '')
                                   .replace('.itx', ''),
            'core_level': core, 'wave_name': wave_name})
    return samples


def read_itx(path):
    """Igor ITX file (.itx)."""
    waves = parse_itx(path)
    if not waves:
        raise ValueError("no valid wave data found in the file")
    samples = _itx_samples(waves)
    if not samples:
        raise ValueError("no valid sample data found in the file")

    def series(info):
        name = info['wave_name']
        data = waves[name]
        be = waves.get(f'{name}_BE')
        if be is None:
            be = np.arange(len(data))
        return be, data

    wb = xlsxflow.Workbook()
    names = _write(wb, samples, series)
    return xlsxflow.load_sheets(wb, names)


# ---------------------------------------------------------------------------
#  .dat
# ---------------------------------------------------------------------------

def sniff_dat(path):
    with open(path, 'rb') as f:
        first = f.readline(65536).decode('utf-8', 'ignore')
    return '\t' in first and re.search(SAMPLE_PATTERN, first) is not None


def read_dat(path):
    """Igor data file (.dat)."""
    lines = _lines(path)
    if not lines:
        raise ValueError("the file is empty")
    header = lines[0].strip().split('\t')
    if not re.search(SAMPLE_PATTERN, lines[0]):
        raise ValueError("no '[All <core level>] <sample>' column header — "
                         "not an Igor .dat export")

    all_data = {}
    for line in lines[1:]:
        if not line.strip():
            continue
        values = line.strip().split('\t')
        try:
            # column by column, as KherveFitting does: a bad cell leaves
            # the columns before it one value longer
            for col_idx in range(len(values)):
                all_data.setdefault(col_idx, [])
                all_data[col_idx].append(
                    float(values[col_idx]) if values[col_idx] else 0.0)
        except (ValueError, IndexError):
            continue

    samples, seen = [], set()
    for i, h in enumerate(header):
        if not h.strip():
            continue
        m = re.search(SAMPLE_PATTERN, h)
        if not m:
            continue
        sample_name = m.group(2)
        if sample_name in seen or any(t in h.lower() for t in _FIT_TERMS):
            continue
        col_values = all_data.get(i, [])
        if col_values and min(col_values) > 500:
            be_col, data_col = i, i + 1
            if data_col >= len(header) or data_col not in all_data:
                continue
        else:
            data_col = i
            be_col = None
            for j in range(i - 1, -1, -1):
                if not header[j].strip():
                    be_col = j
                    break
            if be_col is None:
                be_col = 0
        samples.append({'sample_name': sample_name,
                        'core_level': m.group(1).replace(' ', ''),
                        'data_col': data_col, 'be_col': be_col})
        seen.add(sample_name)

    if not samples:
        raise ValueError("no valid sample data found in the file")
    if not all_data:
        raise ValueError("no valid data found in the file")

    def series(info):
        if info['be_col'] not in all_data or \
                info['data_col'] not in all_data:
            return None
        return all_data[info['be_col']], all_data[info['data_col']]

    wb = xlsxflow.Workbook()
    names = _write(wb, samples, series)
    return xlsxflow.load_sheets(wb, names)


FORMATS = [
    Format("XPS", "Igor ITX (.itx)", (".itx",), read_itx, group="Igor"),
    Format("XPS", "Igor data file (.dat)", (".dat",), read_dat,
           group="Igor", sniff=sniff_dat),
]
