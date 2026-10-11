"""KherveFitting's intermediate-workbook import path, without the workbook.

Many KherveFitting importers do not build their sheets directly: they
write an ``.xlsx`` (B.E. in column A, counts in B, optional corrected
counts / transmission in C / D, and an "Experimental Description"
key/value table in column AX), then read it back. What a project ends up
holding is therefore whatever that round trip makes of the columns:

1. ``add_core_level_Data`` (``libraries/ConfigFile.py``) reads each sheet
   — values cut to two decimals, a header row skipped, rows with an empty
   A or B dropped — plus the AX table as ``ExperimentalInfo``;
2. ``refresh_sheets`` (``libraries/FileMenu/Save.py``) then normalises the
   sheet names ("C 1s Scan" -> "C1s"), re-reads columns A and B at full
   precision into ``'B.E.'`` / ``'Raw Data'`` and adds the
   ``experimental_description`` pair list.

`Workbook` stands in for the file: importers fill it with the cells their
KherveFitting counterpart writes (numbers *or* strings — several write
``f"{x:.2f}"`` text, which makes step 2 stop early, exactly as it does in
KherveFitting), and `open_xlsx` / `load_sheets` replay the two steps.

Copyright (C) 2026 Gwilherm Kerherve

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.
"""

import math
import re

#: column AX, where the importers put the Experimental Description table
EXP_COL = 50


def _empty(v):
    if v is None:
        return True
    if isinstance(v, str):
        return v == ""
    try:
        return math.isnan(v)
    except TypeError:
        return False


class Sheet:
    """One worksheet: columns of cells (row 1 first) + the AX table."""

    def __init__(self, name):
        self.name = name
        self.cols = {}          # 1-based column -> list of cells, row 1 first

    def set_column(self, col, cells):
        self.cols[col] = list(cells)

    def set_columns(self, header, *columns):
        """Header row + data columns A, B, … (row 2 onward)."""
        for i, (head, values) in enumerate(zip(header, columns), start=1):
            self.cols[i] = [head] + list(values)

    def set_experimental(self, items, col=EXP_COL):
        """KherveFitting's ``Experimental Description`` key/value block."""
        items = list(items.items() if isinstance(items, dict) else items)
        self.cols[col] = ["Experimental Description"] + [k for k, _ in items]
        self.cols[col + 1] = [None] + [v for _, v in items]

    # -- reading, as openpyxl / pandas see it -------------------------------
    @property
    def max_row(self):
        n = 0
        for cells in self.cols.values():
            for i in range(len(cells) - 1, -1, -1):
                if not _empty(cells[i]):
                    n = max(n, i + 1)
                    break
        return n

    @property
    def max_col(self):
        used = [c for c, cells in self.cols.items()
                if any(not _empty(v) for v in cells)]
        return max(used) if used else 0

    def cell(self, row, col):
        cells = self.cols.get(col, [])
        v = cells[row - 1] if 0 < row <= len(cells) else None
        return None if _empty(v) else v


class Workbook:
    """Sheets in creation order."""

    def __init__(self):
        self.sheets = []

    @property
    def sheetnames(self):
        return [s.name for s in self.sheets]

    def create_sheet(self, name):
        name = str(name)
        if not name:
            raise ValueError("a sheet needs a name")
        bad = set(name) & set('\\/*?:[]')
        if bad:  # openpyxl refuses these
            raise ValueError(f"invalid character(s) {''.join(sorted(bad))!r} "
                             f"in sheet name {name!r}")
        sheet = Sheet(name)
        self.sheets.append(sheet)
        return sheet

    def __getitem__(self, name):
        for s in self.sheets:
            if s.name == name:
                return s
        raise KeyError(name)


# ---------------------------------------------------------------------------
#  libraries/ConfigFile.py — add_core_level_Data (XPS-style sheets)
# ---------------------------------------------------------------------------

def _f2(v):
    return float(f"{v:.2f}")


def add_core_level(sheet: Sheet) -> dict:
    """The core level ``add_core_level_Data`` reads out of *sheet*."""
    be_values, raw_data, corrected, transmission = [], [], [], []
    for r in range(2, sheet.max_row + 1):
        be_val, raw_val = sheet.cell(r, 1), sheet.cell(r, 2)
        if be_val is None or raw_val is None:
            continue
        try:
            # appended one by one, as KherveFitting does: a bad B leaves
            # its A behind
            be_values.append(float(be_val))
            raw_data.append(float(raw_val))
            c = sheet.cell(r, 3)
            corrected.append(float(c) if c is not None else float(raw_val))
            t = sheet.cell(r, 4)
            transmission.append(float(t) if t is not None else 1.0)
        except (ValueError, TypeError):
            continue

    info = {}
    exp_col = None
    for col in range(40, min(61, sheet.max_col + 1)):
        v = sheet.cell(1, col)
        if v is not None and "Experimental Description" in str(v):
            exp_col = col
            break
    if exp_col:
        for r in range(2, sheet.max_row + 1):
            key = sheet.cell(r, exp_col)
            if key is not None and str(key).strip():
                val = sheet.cell(r, exp_col + 1)
                info[str(key).strip()] = (str(val).strip()
                                          if val is not None else "")

    cl = {"B.E.": [_f2(v) for v in be_values],
          "Raw Data": [_f2(v) for v in raw_data],
          "Corrected Data": [_f2(v) for v in corrected],
          "Transmission": [_f2(v) for v in transmission],
          "Name": sheet.name}
    if info:
        cl["ExperimentalInfo"] = info
    if be_values:
        cl["Background"] = {"Bkg Y": cl["Raw Data"], "Bkg Type": "",
                            "Bkg Low": _f2(min(be_values)),
                            "Bkg High": _f2(max(be_values)),
                            "Bkg Offset Low": 0, "Bkg Offset High": 0}
    return cl


# ---------------------------------------------------------------------------
#  libraries/FileMenu/Save.py — refresh_sheets
# ---------------------------------------------------------------------------

_SKIP = ("results table", "experimental description")


def refresh_name(old_name):
    """The sheet-name normalisation ``refresh_sheets`` applies."""
    new_name = old_name
    lower_name = old_name.lower()
    if 'survey' in lower_name:
        new_name = 'Survey'
    elif 'wide' in lower_name:
        new_name = 'Wide'
    else:
        match = re.search(r'([A-Z][a-z]?)\s+(\d+[spdf])', old_name)
        if match:
            element, orbital = match.groups()
            new_name = f"{element}{orbital}"
        match = re.search(r'([A-Z][a-z]?\d+[spdf])', new_name)
        if match and len(new_name) > len(match.group(1)):
            new_name = match.group(1)
    suffix_match = re.search(r'(\d+)$', old_name)
    if suffix_match and not re.search(r'\d+$', new_name):
        new_name = f"{new_name}{suffix_match.group(1)}"
    return new_name


def normalize_sheet_name(name):
    """``libraries/FileMenu/Open.py: normalize_sheet_name``."""
    new_name = name
    lower_name = name.lower()
    if 'xps survey' in lower_name:
        new_name = 'Survey'
    elif 'survey' in lower_name:
        new_name = 'Survey'
    elif 'wide' in lower_name:
        new_name = 'Wide'
    elif 'su1s' in lower_name or '_su' in lower_name:
        new_name = 'Survey'
    elif any(term in lower_name for term in
             ['valence', 'valence band', 'valence scan', 'vb scan', 'vb',
              'valence band scan']):
        new_name = 'VB'
    elif any(term in lower_name for term in ['fermi', 'fermi scan']):
        new_name = 'Fermi'
    else:
        match = re.search(r'([A-Z][a-z]?)\s+(\d+[spdf])', name)
        if match:
            element, orbital = match.groups()
            new_name = f"{element}{orbital}"
        match = re.search(r'([A-Z][a-z]?\d+[spdf])', new_name)
        if match and len(new_name) > len(match.group(1)):
            new_name = match.group(1)
    suffix_match = re.search(r'(\d+)$', name)
    if suffix_match and not re.search(r'\d+$', new_name):
        new_name = f"{new_name}{suffix_match.group(1)}"
    return new_name


class _Stop(Exception):
    """refresh_sheets hit an error; KherveFitting keeps Data as it was."""


def _column(sheet, col):
    """``pd.read_excel(sheet).iloc[:, col - 1].tolist()`` (header = row 1)."""
    if sheet.max_col < col:
        raise _Stop("no such column")
    return [sheet.cell(r, col) for r in range(2, sheet.max_row + 1)]


def refresh(levels: dict, wb: Workbook) -> dict:
    """``refresh_sheets`` on a freshly imported project; returns the new
    ``Core levels`` dict (renamed keys first, as KherveFitting rebuilds
    it). An error part-way leaves the levels as they were at that point,
    as in KherveFitting (which then also keeps the project as .xlsx)."""
    names = [n for n in wb.sheetnames if n.lower() not in _SKIP]
    changes = {}
    for old in names:
        new = refresh_name(old)
        if new != old:
            changes[old] = new

    titles = list(wb.sheetnames)
    if changes:
        for old, new in changes.items():
            if old in titles and new not in titles:
                titles[titles.index(old)] = new
        renamed = {}
        for old, new in changes.items():
            if old in levels:
                renamed[new] = levels[old]
        for name in levels:
            if name not in changes and name not in renamed:
                renamed[name] = levels[name]
        levels = renamed
    # the sheet objects under their (possibly new) titles
    by_title = dict(zip(titles, wb.sheets))
    names = [n for n in titles if n.lower() not in _SKIP]

    try:
        for name in names:
            if name not in levels:
                levels[name] = add_core_level(by_title[name])
        for name in set(levels) - set(names):
            del levels[name]

        for name in names:
            if '~Map' in name or name not in levels:
                continue
            sheet = by_title[name]
            be = _column(sheet, 1)
            raw = _column(sheet, 2)
            new_be = []
            for v in be:
                if isinstance(v, str):
                    # "284.50" + 0: KherveFitting's TypeError ends the refresh
                    raise _Stop("text cells")
                new_be.append(float("nan") if v is None else float(v) + 0)
            levels[name]["B.E."] = new_be
            levels[name]["Raw Data"] = [
                float("nan") if v is None else
                (v if isinstance(v, str) else float(v)) for v in raw]

        for name in names:
            if 'experimental_description' in levels[name]:
                continue
            sheet = by_title[name]
            if sheet.max_col < EXP_COL + 1:
                continue        # usecols=[49, 50] out of range: skipped
            pairs = []
            for r in range(1, sheet.max_row + 1):
                k, v = sheet.cell(r, EXP_COL), sheet.cell(r, EXP_COL + 1)
                if k is None or v is None:
                    continue
                k, v = str(k).strip(), str(v).strip()
                if k and v:
                    pairs.append([k, v])
            if pairs:
                levels[name]['experimental_description'] = pairs
    except _Stop:
        pass
    return levels


# ---------------------------------------------------------------------------
#  The two ways an importer hands its workbook over
# ---------------------------------------------------------------------------

def load_sheets(wb: Workbook, sheet_names) -> dict:
    """An importer calling ``add_core_level_Data`` on *sheet_names* itself
    and then ``refresh_sheets`` (Scienta, SDP, Igor)."""
    levels = {}
    for name in sheet_names:
        levels[name] = add_core_level(wb[name])
    return refresh(levels, wb)


_XPS_A = ('BE', 'B.E.', 'BINDING')
_XPS_B = ('RAW DATA', 'CORRECTED DATA', 'INTENSITY')


def _valid(sheet: Sheet) -> bool:
    """``open_xlsx_file``'s header check, for the XPS sheets imported here."""
    if re.match(r'^Sheet\d+$', sheet.name, re.IGNORECASE):
        return False
    if sheet.max_row == 0 or sheet.max_col < 2:
        return False
    a = str(sheet.cell(1, 1)).strip().upper()
    b = str(sheet.cell(1, 2)).strip().upper()
    if any(k in a for k in _XPS_A) and any(k in b for k in _XPS_B):
        return True
    if ('WAVENUMBER' in a or 'CM-1' in a) and ('RAW DATA' in b
                                              or 'INTENSITY' in b):
        return True
    if 'ENERGY' in a and ('INTENSITY' in b or 'RAW DATA' in b):
        return True
    try:  # a sheet named after another technique passes on its name
        from ..kfitio import is_xps_like
        return not is_xps_like(sheet.name)
    except Exception:
        return False


def open_xlsx(wb: Workbook) -> dict:
    """``open_xlsx_file`` on a workbook an importer just saved (MRS,
    VG-Microtech, ASC, CSV): header-checked sheets read, then refreshed."""
    levels = {}
    for sheet in wb.sheets:
        if sheet.name.lower() in _SKIP or not _valid(sheet):
            continue
        levels[sheet.name] = add_core_level(sheet)
    if not levels:
        raise ValueError("no valid sheets")
    return refresh(levels, wb)
