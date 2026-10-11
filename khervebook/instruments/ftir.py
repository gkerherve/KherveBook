"""FTIR import: Cary 630 / generic text, JCAMP-DX and Nicolet libraries.

- Agilent Cary 630 (MicroLab Expert) ``.txt``/``.csv`` exports — a
  ``DATATYPE`` / ``XYUNITS`` / ``DECIMALSYMBOL`` header, the data, then
  ``key=value`` footer lines — and any bare two-column (wavenumber,
  intensity) text. The ordinate unit comes from ``XYUNITS`` or, failing
  that, is inferred from the data.
- JCAMP-DX ``.jdx``/``.dx`` (AFFN or ASDF-compressed ``##XYDATA``, or
  ``##XYPOINTS`` / ``##PEAK TABLE`` pairs).
- Nicolet / Thermo OMNIC search libraries (``.lbd`` + its ``.lbt`` /
  ``.lbp`` / ``.lbg`` siblings): every reference spectrum, as absorbance.

KherveFitting imports all of these through an intermediate ``.xlsx``
(``Wavenumber (cm-1) | Raw Data`` sheets FTIR, FTIR1, …) that it reads
back with ``add_core_level_Data`` — values rounded to two decimals — and
then tags with the ordinate (``FTIR_Y_Unit``, ``FTIR_Raw``…). The sheets
here are what that read-back produces.

Ported from KherveFittingPro (``libraries/FileMenu/FTIR_Import.py``,
``JCAMP_Import.py`` ``parse_jcamp`` / ``import_jcamp_file``,
``NicoletLibrary_Import.py`` ``parse_nicolet_library`` /
``_import_selected`` and ``libraries/ToolsMenu/FTIR_Engine.py``
``detect_y_unit`` / ``validate_values``), wx-free.

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
from .kfgeneric import as_list, expand, fail_if_empty, head_text, xlsx_sheet

# Y-unit strings as stored in the sheet data (read by the plot code).
Y_UNIT_TRANSMITTANCE = "Transmittance (%)"
Y_UNIT_ABSORBANCE = "Absorbance"


# ---------------------------------------------------------------------------
# Ordinate units (FTIR_Engine)
# ---------------------------------------------------------------------------

U_T_PCT = "Transmittance (%)"
U_T_FRAC = "Transmittance (fraction)"
U_ABSORBANCE = "Absorbance"
U_R_PCT = "Reflectance (%)"
U_KM = "Kubelka-Munk"
U_ARB = "Intensity (a.u.)"

ALL_UNITS = (U_T_PCT, U_T_FRAC, U_ABSORBANCE, U_R_PCT, U_KM, U_ARB)

# Units whose bands point *down* (a transmittance-like ordinate)
_DOWNWARD = (U_T_PCT, U_T_FRAC, U_R_PCT)

def detect_y_unit(y_values):
    """Guess the ordinate unit from the shape of the data.

    Returns ``(unit, confidence, reason)`` with confidence in 0-1.  Anything
    below ~0.7 should be confirmed by the user rather than assumed - a wrong
    guess here silently corrupts every later number.
    """
    y = np.asarray([v for v in np.asarray(y_values, dtype=float).ravel()
                    if np.isfinite(v)], dtype=float)
    if y.size == 0:
        return U_ARB, 0.0, "No finite data points."

    lo, hi = float(np.min(y)), float(np.max(y))
    span = hi - lo
    if span <= 0:
        return U_ARB, 0.0, "Spectrum is flat."

    median = float(np.median(y))
    # Where the baseline sits inside the data range: transmittance-like data
    # rests near the top (most of the spectrum is "no absorption"),
    # absorbance-like data rests near the bottom.
    baseline_pos = (median - lo) / span

    if hi > 150 or lo < -1.5:
        # Far outside every calibrated ordinate.  Single-beam intensity,
        # counts, or an already-broken conversion.
        return (U_ARB, 0.9,
                f"Values span {lo:.4g} to {hi:.4g}, outside any calibrated "
                f"ordinate (%T is 0-100, absorbance roughly 0-4).")

    if 0.0 <= lo and hi <= 110.0 and hi > 5.0:
        if baseline_pos > 0.6:
            return (U_T_PCT, 0.9,
                    f"0-100 range with the baseline near the top "
                    f"({100 * baseline_pos:.0f}% of the range): percent "
                    f"transmittance.")
        return (U_T_PCT, 0.45,
                "0-100 range, but the baseline sits low - could be percent "
                "transmittance of a very absorbing sample, or an absorbance "
                "spectrum on an unusual scale.")

    if hi <= 1.05 and lo >= -0.05:
        if baseline_pos > 0.6:
            return (U_T_FRAC, 0.8,
                    "0-1 range with a high baseline: transmittance as a "
                    "fraction.")
        return (U_ABSORBANCE, 0.75,
                "0-1 range with a low baseline and upward bands: absorbance.")

    if hi <= 6.0 and lo >= -0.5 and baseline_pos < 0.5:
        return (U_ABSORBANCE, 0.8,
                f"Range {lo:.3g} to {hi:.3g} with a low baseline and upward "
                f"bands: absorbance.")

    return (U_ARB, 0.3,
            f"Range {lo:.4g} to {hi:.4g} does not match any expected "
            f"ordinate cleanly.")


def validate_values(y_values, unit):
    """Sanity-check data against the unit it claims to be in.

    Returns a list of human-readable warnings (empty if all is well).
    """
    y = np.asarray(y_values, dtype=float)
    y = y[np.isfinite(y)]
    warnings = []
    if y.size == 0:
        return ["Spectrum contains no finite values."]
    lo, hi = float(np.min(y)), float(np.max(y))

    if unit == U_T_PCT:
        if hi > 110:
            warnings.append(f"Maximum is {hi:.4g} %T - above the 0-100 range. "
                            f"The data may not be percent transmittance.")
        if lo < -1:
            warnings.append(f"Minimum is {lo:.4g} %T - negative transmittance "
                            f"is unphysical.")
    elif unit == U_T_FRAC:
        if hi > 1.1 or lo < -0.05:
            warnings.append(f"Range {lo:.4g} to {hi:.4g} is outside the 0-1 "
                            f"fractional transmittance range.")
    elif unit == U_R_PCT:
        if hi > 110 or lo < -1:
            warnings.append(f"Range {lo:.4g} to {hi:.4g} is outside the "
                            f"0-100 %R range.")
    elif unit == U_ABSORBANCE:
        if lo < -0.5:
            warnings.append(f"Minimum absorbance is {lo:.4g}. Strongly "
                            f"negative absorbance usually means the ordinate "
                            f"was mis-identified, or the background is "
                            f"stronger than the sample single beam.")
        if hi > 6:
            warnings.append(f"Maximum absorbance is {hi:.4g}; above ~3 the "
                            f"detector is normally saturated and band shapes "
                            f"are not quantitative.")
    return warnings


class ConversionError(ValueError):
    """Raised when a requested ordinate conversion is not physically defined."""


# ---------------------------------------------------------------------------


def infer_y_unit(y_values):
    """``(unit, confidence, reason)`` for a spectrum with no unit header."""
    if not y_values:
        return Y_UNIT_TRANSMITTANCE, 0.0, "No data."
    return detect_y_unit(y_values)


# ---------------------------------------------------------------------------
# Cary 630 / generic text
# ---------------------------------------------------------------------------

def parse_ftir_txt(file_path):
    """
    Parse an FTIR text file (Agilent Cary 630 MicroLab export or generic
    two-column data).

    Returns (data, y_unit, metadata):
        data     : list of (wavenumber, intensity) tuples
        y_unit   : Y_UNIT_TRANSMITTANCE or Y_UNIT_ABSORBANCE
        metadata : dict of header/footer key-value pairs
    """
    data = []
    metadata = {}
    y_unit = Y_UNIT_TRANSMITTANCE
    unit_declared = False
    decimal_symbol = '.'

    with open(file_path, 'r', errors='ignore') as f:
        for raw_line in f:
            line = raw_line.strip()
            if not line or line.startswith('#'):
                continue

            # Split on tabs, semicolons, whitespace (and commas, unless the
            # comma is the decimal symbol)
            if decimal_symbol == ',':
                tokens = re.split(r'[\t;\s]+', line)
            else:
                tokens = re.split(r'[\t;,\s]+', line)

            # Try to read a data point from the first two tokens
            if len(tokens) >= 2:
                t0, t1 = tokens[0], tokens[1]
                if decimal_symbol == ',':
                    t0, t1 = t0.replace(',', '.'), t1.replace(',', '.')
                try:
                    x_val = float(t0)
                    y_val = float(t1)
                    data.append((x_val, y_val))
                    continue
                except ValueError:
                    pass

            # Footer metadata lines: key=value
            if '=' in line:
                key, _, value = line.partition('=')
                metadata[key.strip()] = value.strip()
                continue

            # Header lines: DATATYPE / XYUNITS / DECIMALSYMBOL
            upper = line.upper()
            if upper.startswith('XYUNITS'):
                units = line.split(None, 1)[1] if len(line.split(None, 1)) > 1 else ''
                metadata['XYUNITS'] = units.strip()
                if 'ABSORB' in units.upper():
                    y_unit = Y_UNIT_ABSORBANCE
                    unit_declared = True
                elif 'TRANSMIT' in units.upper():
                    y_unit = Y_UNIT_TRANSMITTANCE
                    unit_declared = True
            elif upper.startswith('DECIMALSYMBOL'):
                parts = line.split(None, 1)
                if len(parts) > 1 and parts[1].strip() == ',':
                    decimal_symbol = ','
                metadata['DECIMALSYMBOL'] = decimal_symbol
            elif upper.startswith('DATATYPE'):
                parts = line.split(None, 1)
                metadata['DATATYPE'] = parts[1].strip() if len(parts) > 1 else ''

    # Bare CSV/text exports declare no units - infer them from the data shape.
    if data and not unit_declared:
        y_unit, confidence, reason = infer_y_unit([pt[1] for pt in data])
        metadata['Y Units'] = f"{y_unit} (inferred from data)"
        metadata['Y Unit Confidence'] = f"{confidence:.0%}"
        metadata['Y Unit Reason'] = reason
        metadata['_y_unit_confidence'] = confidence
        metadata['_y_unit_reason'] = reason
    elif unit_declared:
        metadata['_y_unit_confidence'] = 1.0
        metadata['_y_unit_reason'] = "Declared in the file header (XYUNITS)."

    return data, y_unit, metadata


def _next_ftir_sheet_name(existing_names):
    """Return the next free FTIR sheet name: FTIR, FTIR1, FTIR2, ..."""
    existing = {name.upper() for name in existing_names}
    if 'FTIR' not in existing:
        return 'FTIR'
    idx = 1
    while f'FTIR{idx}' in existing:
        idx += 1
    return f'FTIR{idx}'



# ---------------------------------------------------------------------------
# JCAMP-DX
# ---------------------------------------------------------------------------
_SQZ = {'@': 0, 'A': 1, 'B': 2, 'C': 3, 'D': 4, 'E': 5, 'F': 6, 'G': 7,
        'H': 8, 'I': 9,
        'a': -1, 'b': -2, 'c': -3, 'd': -4, 'e': -5, 'f': -6, 'g': -7,
        'h': -8, 'i': -9}
_DIF = {'%': 0, 'J': 1, 'K': 2, 'L': 3, 'M': 4, 'N': 5, 'O': 6, 'P': 7,
        'Q': 8, 'R': 9,
        'j': -1, 'k': -2, 'l': -3, 'm': -4, 'n': -5, 'o': -6, 'p': -7,
        'q': -8, 'r': -9}
_DUP = {'S': 1, 'T': 2, 'U': 3, 'V': 4, 'W': 5, 'X': 6, 'Y': 7, 'Z': 8,
        's': 9}

_TOKEN_START = set(_SQZ) | set(_DIF) | set(_DUP)


def _tokenize_asdf(line):
    """Split one ASDF/AFFN data line into number tokens. A new token starts at
    whitespace/comma, at a +/- sign, or at any SQZ/DIF/DUP pseudo-digit."""
    tokens = []
    current = ""
    for ch in line:
        if ch in ' \t,;':
            if current:
                tokens.append(current)
                current = ""
        elif ch in '+-' or ch in _TOKEN_START:
            if current:
                tokens.append(current)
            current = ch
        else:  # digit, '.', 'E' exponent etc.
            current += ch
    if current:
        tokens.append(current)
    return tokens


def _decode_token_number(first_digit, rest):
    """Build the integer value from a pseudo-digit start plus trailing digits."""
    digits = str(abs(first_digit)) + rest
    value = int(digits) if digits else 0
    return -value if first_digit < 0 else value


def _decode_xydata_lines(lines):
    """Decode ##XYDATA=(X++(Y..Y)) lines (AFFN or ASDF-compressed).

    Returns (x_starts, y_rows, dif_row_flags) where each y_rows[i] is the list
    of ordinates for that line and dif_row_flags[i] says whether the line's
    values continue a DIF sequence (first value = check value)."""
    all_y = []
    x_starts = []
    row_starts_in_dif = []

    prev_line_ended_in_dif = False
    last_y = None

    for line in lines:
        tokens = _tokenize_asdf(line)
        if not tokens:
            continue
        try:
            x_start = float(tokens[0])
        except ValueError:
            continue

        row_y = []
        in_dif = False
        last_diff = 0
        first_value_of_line = True

        for tok in tokens[1:]:
            c = tok[0]
            if c in _DUP:
                count = _decode_token_number(_DUP[c], tok[1:])
                # Repeat the previous action (count - 1) more times
                for _ in range(max(0, count - 1)):
                    if in_dif:
                        last_y = last_y + last_diff
                    row_y.append(last_y)
            elif c in _DIF:
                last_diff = _decode_token_number(_DIF[c], tok[1:])
                last_y = (last_y if last_y is not None else 0) + last_diff
                row_y.append(last_y)
                in_dif = True
            elif c in _SQZ:
                last_y = _decode_token_number(_SQZ[c], tok[1:])
                row_y.append(last_y)
                in_dif = False
            else:
                try:
                    last_y = float(tok)
                except ValueError:
                    continue
                row_y.append(last_y)
                in_dif = False

            if first_value_of_line:
                first_value_of_line = False

        x_starts.append(x_start)
        all_y.append(row_y)
        row_starts_in_dif.append(prev_line_ended_in_dif)
        prev_line_ended_in_dif = in_dif

    return x_starts, all_y, row_starts_in_dif


def parse_jcamp(file_path):
    """Parse a JCAMP-DX infrared file.

    Returns dict with keys: x (np.array, cm-1, ascending), y (np.array),
    y_unit ('Transmittance (%)' or 'Absorbance'), title, cas, state, origin,
    molform. Raises ValueError on unusable files."""
    headers = {}
    data_lines = []
    data_mode = None  # 'XYDATA' | 'XYPOINTS'

    with open(file_path, 'r', errors='ignore') as f:
        for raw in f:
            line = raw.rstrip('\n').rstrip('\r')
            # strip inline comments  $$ ...
            if '$$' in line:
                line = line.split('$$')[0]
            if not line.strip():
                continue
            if line.startswith('##'):
                key, _, value = line[2:].partition('=')
                key = key.strip().upper().replace(' ', '')
                value = value.strip()
                if key == 'XYDATA':
                    data_mode = 'XYDATA'
                    data_lines = []
                elif key in ('XYPOINTS', 'PEAKTABLE'):
                    data_mode = 'XYPOINTS'
                    data_lines = []
                elif key == 'END':
                    break
                else:
                    headers[key] = value
            elif data_mode:
                data_lines.append(line)

    if not data_lines:
        raise ValueError("No spectral data table found (##XYDATA / ##XYPOINTS)")

    x_factor = float(headers.get('XFACTOR', 1.0) or 1.0)
    y_factor = float(headers.get('YFACTOR', 1.0) or 1.0)

    if data_mode == 'XYPOINTS':
        xs, ys = [], []
        for line in data_lines:
            numbers = re.findall(r'[+-]?\d+\.?\d*(?:[eE][+-]?\d+)?', line)
            for i in range(0, len(numbers) - 1, 2):
                xs.append(float(numbers[i]))
                ys.append(float(numbers[i + 1]))
        x = np.array(xs) * x_factor
        y = np.array(ys) * y_factor
    else:
        x_starts, y_rows, dif_flags = _decode_xydata_lines(data_lines)
        n_expected = None
        try:
            n_expected = int(headers.get('NPOINTS', ''))
        except ValueError:
            pass

        # Collect ordinates, dropping the X-sequence check value that starts
        # every line which continues a DIF sequence
        ys = []
        kept_rows = []
        for i, row in enumerate(y_rows):
            if dif_flags[i] and row:
                row = row[1:]
            kept_rows.append(row)
            ys.extend(row)

        y = np.array(ys, dtype=float) * y_factor

        # Abscissae: prefer the exact FIRSTX/LASTX grid (immune to the
        # ambiguity of what a DIF line's X value refers to); fall back to
        # per-line reconstruction from the line X values.
        first_x = headers.get('FIRSTX', '')
        last_x = headers.get('LASTX', '')
        if first_x and last_x and n_expected and len(y) == n_expected and n_expected > 1:
            x = np.linspace(float(first_x), float(last_x), n_expected)
        else:
            try:
                delta_x = float(headers.get('DELTAX', ''))
            except ValueError:
                delta_x = None
            xs = []
            for i, row in enumerate(kept_rows):
                if not row:
                    continue
                x0 = x_starts[i] * x_factor
                if dif_flags[i]:
                    # Line X belongs to the check value (previous line's last point)
                    if delta_x is not None:
                        x0 += delta_x
                if delta_x is None:
                    if i + 1 < len(x_starts):
                        delta_here = (x_starts[i + 1] - x_starts[i]) * x_factor / len(y_rows[i])
                    else:
                        delta_here = xs[-1] - xs[-2] if len(xs) >= 2 else 0
                else:
                    delta_here = delta_x
                for j in range(len(row)):
                    xs.append(x0 + j * delta_here)
            x = np.array(xs, dtype=float)

        if n_expected and abs(len(y) - n_expected) > max(2, 0.01 * n_expected):
            print(f"JCAMP warning: decoded {len(y)} points, header says {n_expected}")

    if len(x) < 2:
        raise ValueError("Fewer than 2 data points decoded")

    # --- X units -> cm-1 ---
    x_units = headers.get('XUNITS', '1/CM').upper()
    if 'MICROMETER' in x_units or 'MICRON' in x_units:
        with np.errstate(divide='ignore'):
            x = 10000.0 / x
    # NANOMETERS occasionally appears for NIR
    elif 'NANOMETER' in x_units:
        with np.errstate(divide='ignore'):
            x = 1.0e7 / x

    # --- Y units ---
    y_units = headers.get('YUNITS', '').upper()
    if 'ABSORBANCE' in y_units:
        y_unit = Y_UNIT_ABSORBANCE
    else:
        y_unit = Y_UNIT_TRANSMITTANCE
        if 'TRANSMITTANCE' in y_units and np.nanmax(y) <= 1.5:
            y = y * 100.0  # fractional transmittance -> %

    # Sort ascending in wavenumber and drop non-finite points
    good = np.isfinite(x) & np.isfinite(y)
    x, y = x[good], y[good]
    order = np.argsort(x)
    x, y = x[order], y[order]

    return {
        'x': x,
        'y': y,
        'y_unit': y_unit,
        'title': headers.get('TITLE', os.path.splitext(os.path.basename(file_path))[0]),
        'cas': headers.get('CASREGISTRYNO', ''),
        'state': headers.get('STATE', ''),
        'origin': headers.get('ORIGIN', ''),
        'molform': headers.get('MOLFORM', ''),
    }


# ---------------------------------------------------------------------------
# Nicolet / OMNIC libraries
# ---------------------------------------------------------------------------

_XOR_KEY = 0x4C           # a common old-Nicolet .LBT text-obfuscation key
_CAS_RE = re.compile(r'^\d{1,7}-\d{2}-\d$')

def _resolve_lbd(path):
    """Given any library member, return the path of the sibling .LBD data file.

    Extensions are matched case-insensitively (instruments write LBD or lbd)."""
    root, ext = os.path.splitext(path)
    if ext.lower() == '.lbd':
        return path
    for cand_ext in ('.LBD', '.lbd', '.Lbd'):
        cand = root + cand_ext
        if os.path.exists(cand):
            return cand
    # Last resort: case-insensitive directory scan
    base = os.path.basename(root).lower()
    folder = os.path.dirname(path) or '.'
    for fn in os.listdir(folder):
        stem, e = os.path.splitext(fn)
        if e.lower() == '.lbd' and stem.lower() == base:
            return os.path.join(folder, fn)
    return None


def _parse_header_fields(raw, total_size):
    """Parse the ASCII header block into geometry fields (no codec detection).

    ``total_size`` is the full .LBD size in bytes; it may differ from
    ``len(raw)`` when only the header chunk was read (the fast folder scan).
    Returns a dict without a ``codec`` key, or raises ValueError."""
    end = raw.find(b'\x1a')
    end = end if 0 < end < 16384 else 1024
    lines = [ln.strip() for ln in raw[:end].decode('latin-1', 'ignore').split('\r\n')]

    def as_int(i):
        return int(float(lines[i]))

    def as_float(i):
        return float(lines[i])

    try:
        blk = as_int(0)
        npoints = as_int(14)
        fx, lx = as_float(15), as_float(16)
        f6, f7 = as_int(6), as_int(7)
    except (IndexError, ValueError):
        raise ValueError("Unrecognised library header")

    if npoints < 8 or not np.isfinite(fx) or not np.isfinite(lx):
        raise ValueError("Implausible library header (npoints/wavenumbers)")

    data_size = total_size - blk
    fields = [f for f in (f6, f7) if f and f > 0]
    if not fields:
        raise ValueError("No record-geometry fields in header")

    # stride must be able to hold at least the spectrum; nspec is the other field.
    wide = [f for f in fields if f >= 2 * npoints]
    if wide:
        stride = min(wide)
    else:
        narrow = [f for f in fields if f >= npoints]
        if not narrow:
            raise ValueError("No field large enough to hold a spectrum")
        stride = min(narrow)
    others = [f for f in fields if f != stride]
    nspec = others[0] if others else data_size // stride
    if nspec < 1 or nspec * stride > data_size:
        nspec = data_size // stride
    if nspec < 1:
        raise ValueError("No spectra found")

    title = lines[3] if len(lines) > 3 else ''
    return dict(blk=blk, title=title.strip(), npoints=npoints, fx=fx, lx=lx,
                stride=stride, nspec=nspec)


def _parse_header(raw):
    """Parse the ASCII header block. Returns a dict or raises ValueError."""
    meta = _parse_header_fields(raw, len(raw))
    meta['codec'] = _detect_codec(raw, meta['blk'], meta['npoints'],
                                  meta['stride'])
    return meta


def _detect_codec(raw, blk, npoints, stride):
    """Decide the ordinate encoding from the record geometry (see module docstring)."""
    ratio = stride / npoints
    trailer = stride - 2 * npoints
    if ratio < 1.5:
        return 'u8'
    if ratio >= 3.5 and stride >= 4 * npoints:
        f = np.frombuffer(raw[blk:blk + 4 * npoints], '<f4').astype(float)
        if f.size == npoints and np.all(np.isfinite(f)) and np.nanmax(np.abs(f)) < 1e4:
            return 'f32LE'
        return 'u16LE' if 0 <= trailer <= 64 else 'planBE'
    if 0 <= trailer <= 64:
        return 'u16LE'
    return 'planBE'


def _decode_record(raw, meta, i):
    """Return the raw ordinate array for spectrum ``i`` (no rescaling)."""
    n = meta['npoints']
    base = meta['blk'] + i * meta['stride']
    rec = raw[base:base + meta['stride']]
    codec = meta['codec']
    if codec == 'u8':
        return np.frombuffer(rec[:n], np.uint8).astype(float)
    if codec == 'u16LE':
        return np.frombuffer(rec[:2 * n], '<u2').astype(float)
    if codec == 'f32LE':
        return np.frombuffer(rec[:4 * n], '<f4').astype(float)
    # planBE: [n high bytes][n low bytes], big-endian 16-bit
    hi = np.frombuffer(rec[:n], np.uint8).astype(float)
    lo = np.frombuffer(rec[n:2 * n], np.uint8).astype(float)
    return hi * 256.0 + lo


def _ordinate(raw, meta, i):
    """Absorbance array for spectrum ``i``, rescaled to a nominal 0..1 for the
    integer codecs (which store per-spectrum full-scale values); float codecs
    are already physical absorbance and are passed through unchanged."""
    y = _decode_record(raw, meta, i)
    if meta['codec'] == 'u8':
        return y / 255.0
    if meta['codec'] in ('u16LE', 'planBE'):
        return y / 65535.0
    return y  # f32LE - real absorbance


# ---------------------------------------------------------------------------
# Compound names (sibling .LBT)
# ---------------------------------------------------------------------------

def _fields_length_prefixed(buf):
    """Walk a text region as consecutive [len byte][ASCII bytes] fields.

    Used by the libraries that store variable-length fields (most .LBT files,
    clear or XOR-0x4C obfuscated)."""
    fields = []
    i, n = 0, len(buf)
    while i < n:
        length = buf[i]
        if 2 <= length <= 90 and i + 1 + length <= n:
            chunk = buf[i + 1:i + 1 + length]
            if all(32 <= c < 127 for c in chunk):
                fields.append(chunk.decode('latin-1'))
                i += 1 + length
                continue
        i += 1
    return fields


def _fields_ff_marked(buf):
    """Read the printable run that follows each 0xFF marker.

    Some 2000s Thermo libraries store the record text as a fixed-width,
    space-padded field introduced by a 0xFF byte (e.g. sea010d, sea274). The
    length-prefixed walker mis-parses those because a leading capital letter
    (0x41-0x5A) looks like a valid length byte and eats the first character."""
    fields = []
    i, n = 0, len(buf)
    while i < n:
        if buf[i] == 0xFF:
            j = i + 1
            while j < n and 32 <= buf[j] < 127:
                j += 1
            run = buf[i + 1:j].decode('latin-1').strip()
            if len(run) >= 3:
                fields.append(run)
            i = j
        else:
            i += 1
    return fields


def _name_quality(s):
    """Score how much a field looks like a compound name (0..~1.3).

    Rewards letters and spaces; penalises low character diversity (padding
    runs like 'llllAF'), very short strings, digit-heavy codes and bare CAS
    numbers - i.e. the CAS / catalog / index fields that sit beside the name.
    """
    s = s.strip()
    if len(s) < 5 or _CAS_RE.match(s):
        return 0.0
    alpha = sum(c.isalpha() for c in s)
    digit = sum(c.isdigit() for c in s)
    vowels = sum(c in 'aeiouAEIOU' for c in s)
    letters = [c for c in s if c.isalpha()]
    # Random-case codes (e.g. "gDGkDeRB") flip case on nearly every letter;
    # real names ("Piperylene", "PICHLOROHYDRIN") do not.
    case_flips = sum(1 for a, b in zip(letters, letters[1:])
                     if a.isupper() != b.isupper())
    score = alpha / len(s) + (0.3 if ' ' in s else 0.0)
    if len(set(s)) / len(s) < 0.35:          # repetitive padding/garbage
        score *= 0.15
    if digit / len(s) > 0.4:                  # catalog / index code
        score *= 0.3
    if alpha < 3 or vowels == 0:              # needs some letters and a vowel
        score *= 0.3
    if letters and case_flips / len(letters) > 0.35:   # random-case gibberish
        score *= 0.2
    return score


def _load_names(lbd_path, nspec):
    """Best-effort compound names from the sibling .LBT, in spectrum order.

    A .LBT record is a run of length-prefixed fields (compound name, CAS #,
    catalog #, ...); older Nicolet libraries XOR the text with 0x4C, the 2000s
    Thermo ones store it in clear. We flatten every field, group them into
    ``nspec`` records and keep the column that looks most like compound names.
    Returns a list of length ``nspec``; entries we cannot recover are '' and
    the caller substitutes a generic label. If the whole extraction looks like
    garbage (unknown obfuscation) every entry is ''.
    """
    root = os.path.splitext(lbd_path)[0]
    lbt = None
    for e in ('.LBT', '.lbt', '.Lbt'):
        if os.path.exists(root + e):
            lbt = root + e
            break
    if not lbt:
        return [''] * nspec

    try:
        raw = open(lbt, 'rb').read()
    except OSError:
        return [''] * nspec
    end = raw.find(b'\x1a')
    body = raw[end + 1:] if end > 0 else raw[1024:]

    def best_column(fields):
        """Group length-prefixed fields into nspec records and return the
        (score, names) of the phase that looks most like a name column."""
        # Drop blank / letterless padding and code fields so the records line
        # up on a clean period (some libraries pad every record with several
        # empty fixed-width fields).
        fields = [f.strip() for f in fields if any(c.isalpha() for c in f)]
        # Skip leading padding / header junk so record 0 starts at the first
        # real name - otherwise every name is shifted onto the next spectrum.
        first = next((j for j, f in enumerate(fields) if _name_quality(f) >= 0.5),
                     0)
        fields = fields[first:]
        if len(fields) < 0.7 * nspec:
            return 0.0, None
        k = min(max(1, round(len(fields) / nspec)), 8)
        best_s, best_c = 0.0, None
        for start in range(k):
            col = fields[start::k][:nspec]
            if len(col) < 0.7 * nspec:
                continue
            s = sum(_name_quality(x) for x in col) / len(col)
            if s > best_s:
                best_s, best_c = s, col
        return best_s, best_c

    # Libraries differ in how the .LBT stores text (length-prefixed vs fixed
    # width behind a 0xFF marker) and older ones XOR the bytes with a per-library
    # key (0x4C, 0xC3, ...). Auto-derive candidate keys by assuming the most
    # common byte in the record region is a space (0x20), then try every reading
    # and keep whichever produces the best-scoring name column.
    from collections import Counter
    common = [b for b, _ in Counter(b for b in body if b).most_common(4)]
    # 0x00 = clear text; 0x4C/0xC3 = keys seen in the wild; the rest are derived
    # by assuming the commonest byte is a padded space (works when records are
    # space-padded, which is where the fixed known keys do not already apply).
    keys = list(dict.fromkeys([0x00, _XOR_KEY, 0xC3] + [b ^ 0x20 for b in common]))

    best_score, best_names = 0.0, None
    for key in keys:
        buf = body if key == 0 else bytes(b ^ key for b in body)
        for fields in (_fields_length_prefixed(buf), _fields_ff_marked(buf)):
            score, names = best_column(fields)
            if score > best_score:
                best_score, best_names = score, names

    if best_names is None or best_score < 0.5:
        return [''] * nspec

    # Blank out low-quality entries (padding/garbage records) rather than
    # showing a bogus label; real names score ~0.9+.
    names = [s.strip() if _name_quality(s) >= 0.35 else '' for s in best_names]
    names += [''] * (nspec - len(names))
    return names[:nspec]


# ---------------------------------------------------------------------------
# Public parse entry point
# ---------------------------------------------------------------------------

def parse_nicolet_library(path):
    """Parse a Nicolet/Thermo library. Returns a dict:

        title    : library title from the header
        npoints  : points per spectrum
        x        : np.array of wavenumbers (cm-1, ascending)
        nspec    : number of reference spectra
        names    : list[str] compound names (may contain '' placeholders)
        get_y    : callable(i) -> absorbance np.array for spectrum i
        lbd_path : the resolved .LBD file
        codec    : ordinate encoding tag (diagnostic)

    Raises ValueError / FileNotFoundError on unusable input.
    """
    lbd = _resolve_lbd(path)
    if not lbd:
        raise FileNotFoundError(
            "No .LBD data file found next to this library. The spectra live in "
            "the sibling .LBD file - keep the whole library set together.")

    raw = open(lbd, 'rb').read()
    meta = _parse_header(raw)
    x = np.linspace(meta['fx'], meta['lx'], meta['npoints'])
    names = _load_names(lbd, meta['nspec'])

    def get_y(i):
        return _ordinate(raw, meta, i)

    return dict(title=meta['title'] or os.path.splitext(os.path.basename(lbd))[0],
                npoints=meta['npoints'], x=x, nspec=meta['nspec'],
                names=names, get_y=get_y, lbd_path=lbd, codec=meta['codec'])


def _safe_ref(name, idx):
    return name if name else f"Spectrum {idx + 1}"



# ---------------------------------------------------------------------------
# Sheets
# ---------------------------------------------------------------------------

def _tag(sheet, y_unit, confidence=1.0, reason=""):
    """``_tag_ftir_units`` on one read-back sheet. Where KherveFitting
    would ask the user to confirm an uncertain ordinate (confidence below
    0.8), its dialog's default — the guess — is kept."""
    sheet['FTIR_Y_Unit'] = y_unit
    sheet['FTIR_Input_Unit'] = y_unit
    sheet['FTIR_Raw'] = {'x': list(sheet.get('B.E.', [])),
                         'y': list(sheet.get('Raw Data', [])),
                         'unit': y_unit}
    sheet['FTIR_Detection'] = {'guess': y_unit, 'confidence': confidence,
                               'reason': reason}
    warnings = validate_values(sheet['FTIR_Raw']['y'], y_unit)
    if warnings:
        sheet['FTIR_Warnings'] = warnings
    return sheet


def _text_files(file_paths):
    """``_import_ftir_paths``: one FTIR sheet per file."""
    core_levels = {}
    skipped = []
    for file_path in file_paths:
        try:
            data, y_unit, metadata = parse_ftir_txt(file_path)
        except Exception as e:
            skipped.append(f"{os.path.basename(file_path)}: {e}")
            continue
        if not data:
            skipped.append(f"{os.path.basename(file_path)}: no valid data")
            continue
        sheet_name = _next_ftir_sheet_name(core_levels)
        core_levels[sheet_name] = _tag(
            xlsx_sheet(sheet_name, data), y_unit,
            metadata.get('_y_unit_confidence', 1.0),
            metadata.get('_y_unit_reason', ''))
    return fail_if_empty(core_levels, skipped, "FTIR data")


def read_text(paths):
    """File(s) (.txt) - Agilent Cary 630 / generic."""
    return _text_files(sorted(as_list(paths)))


def read_text_folder(paths):
    """Multiple files (folder): every .txt/.csv/.dat."""
    return _text_files(expand(paths, ('.txt', '.csv', '.dat')))


def read_csv(paths):
    """CSV file(s) (.csv)."""
    return _text_files(sorted(as_list(paths)))


def read_csv_folder(paths):
    """Multiple CSV files (folder)."""
    return _text_files(expand(paths, ('.csv',)))


def read_jcamp(paths):
    """``import_jcamp_file``: one FTIR sheet per JCAMP-DX file."""
    core_levels = {}
    skipped = []
    for fp in sorted(as_list(paths)):
        try:
            spec = parse_jcamp(fp)
        except Exception as e:
            skipped.append(f"{os.path.basename(fp)}: {e}")
            continue
        sheet_name = _next_ftir_sheet_name(core_levels)
        sheet = xlsx_sheet(sheet_name, zip(spec['x'].tolist(),
                                           spec['y'].tolist()))
        y_unit = spec['y_unit']
        sheet['FTIR_Y_Unit'] = y_unit
        sheet['FTIR_Input_Unit'] = y_unit
        sheet['FTIR_Raw'] = {'x': list(sheet.get('B.E.', [])),
                             'y': list(sheet.get('Raw Data', [])),
                             'unit': y_unit}
        core_levels[sheet_name] = sheet
    return fail_if_empty(core_levels, skipped, "JCAMP-DX data")


def read_nicolet(path, selected=None):
    """``_import_selected``: the library's reference spectra as FTIR,
    FTIR1, … in absorbance. KherveFitting asks which to import; here it is
    every spectrum (or the indices in *selected*)."""
    lib = parse_nicolet_library(str(path))
    if selected is None:
        selected = range(lib['nspec'])
    x = lib['x'].tolist()
    reason = "Nicolet/OMNIC library reference (absorbance)."
    core_levels = {}
    for idx in selected:
        y = np.asarray(lib['get_y'](idx), dtype=float)
        good = np.isfinite(y)
        data = list(zip(x, y.tolist())) if good.all() else \
            [(xi, yi) for xi, yi, g in zip(x, y.tolist(), good) if g]
        if not data:
            continue
        sheet_name = _next_ftir_sheet_name(core_levels)
        sheet = _tag(xlsx_sheet(sheet_name, data), Y_UNIT_ABSORBANCE, 1.0,
                     reason)
        name = lib['names'][idx].strip()
        sheet['FTIR_Reference'] = f"{_safe_ref(name, idx)} [{lib['title']}]"
        core_levels[sheet_name] = sheet
    if not core_levels:
        raise ValueError("No valid spectra to import.")
    return core_levels


def sniff_cary630(path):
    """A Cary 630 MicroLab export: ``DATATYPE`` and ``XYUNITS`` header lines."""
    keys = [ln.strip().split(None, 1)[0].upper()
            for ln in head_text(path, 2048).splitlines()[:12] if ln.strip()]
    return 'DATATYPE' in keys and 'XYUNITS' in keys


FORMATS = [
    Format("FTIR", "File(s) (.txt) - Agilent Cary 630 / generic",
           (".txt", ".csv", ".dat"), read_text, sniff=sniff_cary630,
           multi=True),
    Format("FTIR", "Multiple files (folder)", (".txt", ".csv", ".dat"),
           read_text_folder, sniff=lambda p: False, multi=True),
    Format("FTIR", "CSV file(s) (.csv)", (".csv",), read_csv,
           sniff=lambda p: False, multi=True),
    Format("FTIR", "Multiple CSV files (folder)", (".csv",), read_csv_folder,
           sniff=lambda p: False, multi=True),
    Format("FTIR", "JCAMP-DX file(s) (.jdx/.dx)", (".jdx", ".dx", ".jcm"),
           read_jcamp, multi=True),
    Format("FTIR", "Nicolet/OMNIC library (.lbd/.lbt/.lbp)",
           (".lbd", ".lbt", ".lbp", ".lbg"), read_nicolet),
]
