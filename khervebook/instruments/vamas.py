"""VAMAS (ISO 14976, ``.vms``) import — CasaXPS and most XPS instruments.

A port of KherveFittingPro's ``libraries/FileMenu/Vamas_Import.py``
(``open_vamas_file`` -> ``build_vamas_core_levels``), wx-free, with the
sheet naming of ``libraries/FileMenu/Open.py`` (``normalize_sheet_name``,
``phi_region_base``). KherveFitting reads the file with the ``vamas``
PyPI package (0.1.1); `read_vamas` below is a self-contained parser that
gives the same header and blocks, so KherveBook needs no extra
dependency. It also handles what the package cannot: a parameter
inclusion/exclusion list (later blocks then inherit the first block's
values, as ISO 14976 says) and future-upgrade block entries.

CasaXPS peak fits stored in a block comment (``CASA region`` /
``CASA comp`` lines) are imported into the sheet's ``Fitting`` — the
answer KherveFitting's "Import peak fitting?" question defaults to. As
in KherveFitting's ``.kfit`` route, the background curve itself is not
computed here (``Bkg Y`` stays the data until a background is run).

Copyright (C) 2026 Gwilherm Kerherve

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.
"""

import re
from types import SimpleNamespace

import numpy as np

from . import Format
from .kfitwrite import core_level

#: KherveFitting's defaults (KherveFitting.py: self.photons/workfunction)
DEFAULT_PHOTONS = 1486.67
DEFAULT_WORKFUNCTION = 0.0

_IDENTIFIER = ("VAMAS Surface Chemical Analysis Standard Data Transfer "
               "Format 1988 May 4")


# ---------------------------------------------------------------------------
# Sheet naming (Open.py / Vamas_Import.py)
# ---------------------------------------------------------------------------

_SPIN_ORBIT_DIGITS = {'p': '13', 'd': '35', 'f': '57'}


def phi_region_base(name):
    """Core-level name without an instrument spin-orbit digit
    ('Fe2p3' -> 'Fe2p', 'Pt4f7' -> 'Pt4f'; 'C1s' never changes)."""
    m = re.match(r'^([A-Z][a-z]?\d[pdf])(\d)$', str(name).strip())
    if m and m.group(2) in _SPIN_ORBIT_DIGITS[m.group(1)[-1]]:
        return m.group(1)
    return name


def normalize_sheet_name(name):
    """KherveFitting's core-level name normalisation."""
    new_name = name
    lower_name = name.lower()
    if 'xps survey' in lower_name:
        new_name = 'Survey'
    elif 'survey' in lower_name:
        new_name = 'Survey'
    elif 'survey scan' in lower_name:
        new_name = 'Survey'
    elif 'wide' in lower_name:
        new_name = 'Wide'
    elif 'wide scan' in lower_name:
        new_name = 'Wide'
    elif 'su1s' in lower_name or '_su' in lower_name \
            or name.lower().endswith('_su'):
        new_name = 'Survey'
    elif any(term in lower_name for term in
             ['valence', 'valence band', 'valence scan', 'vb scan', 'vb',
              'valence band scan']):
        new_name = 'VB'
    elif any(term in lower_name for term in ['fermi', 'fermi scan']):
        new_name = 'Fermi'
    else:
        # "C 1s" -> "C1s"
        match = re.search(r'([A-Z][a-z]?)\s+(\d+[spdf])', name)
        if match:
            element, orbital = match.groups()
            new_name = f"{element}{orbital}"
        # "C1s Scan" -> "C1s"
        match = re.search(r'([A-Z][a-z]?\d+[spdf])', new_name)
        if match and len(new_name) > len(match.group(1)):
            new_name = match.group(1)

    # Preserve a sample-number suffix
    suffix_match = re.search(r'(\d+)$', name)
    if suffix_match and not re.search(r'\d+$', new_name):
        new_name = f"{new_name}{suffix_match.group(1)}"
    return new_name


def normalize_auger_and_valence_names(sheet_name):
    """'Fe LM2' -> 'Felmm', 'C KL1' -> 'Ckll', 'V.B.' -> 'VB'."""
    if re.match(r'^V\.?B\.?\s*$', sheet_name.strip(), re.IGNORECASE):
        return "VB"
    match = re.match(r'^([A-Z][a-z]?)\s+([A-Z]+\d*)$', sheet_name.strip())
    if match:
        element = match.group(1)
        auger_letters = re.sub(r'\d+', '', match.group(2)).lower()
        if len(auger_letters) >= 2:
            auger_letters += auger_letters[-1]
        return f"{element}{auger_letters}"
    return sheet_name


# ---------------------------------------------------------------------------
# ISO 14976 parser (same fields and types as the ``vamas`` package)
# ---------------------------------------------------------------------------

_SPUTTER_TECHNIQUES = ("SNMS energy spec", "FABMS", "FABMS energy spec",
                       "ISS", "SIMS", "SIMS energy spec", "SNMS")
_SPUTTER_SOURCE_TECHNIQUES = ("AES diff", "AES dir", "EDX", "ELS", "UPS",
                              "XRF")


class _Lines:
    def __init__(self, fh):
        self._it = iter(fh)

    def __call__(self):
        try:
            return next(self._it)
        except StopIteration:
            raise ValueError("the VAMAS file ends early (truncated "
                             "block)") from None

    def s(self):
        return self().strip()

    def i(self):
        return int(self())

    def f(self):
        return float(self())


def read_vamas(path):
    """``(header, blocks)`` of a VAMAS file, as SimpleNamespaces with the
    attribute names of the ``vamas`` package's VamasHeader/VamasBlock."""
    with open(path, encoding="utf-8", errors="replace") as fh:
        return _parse(_Lines(fh))


def _parse(nxt):
    h = {}
    try:
        h["format_identifier"] = nxt.s()
    except ValueError:
        raise ValueError("empty file - not a VAMAS file") from None
    if h["format_identifier"] != _IDENTIFIER:
        raise ValueError("not a VAMAS file (first line is not the ISO 14976 "
                         "format identifier)")
    h["institution_identifier"] = nxt.s()
    h["instrument_model_identifier"] = nxt.s()
    h["operator_identifier"] = nxt.s()
    h["experiment_identifier"] = nxt.s()
    h["num_lines_comment"] = nxt.i()
    h["comment"] = "\n".join(nxt.s() for _ in range(h["num_lines_comment"]))
    mode = h["experiment_mode"] = nxt.s()
    h["scan_mode"] = nxt.s()
    h["num_spectral_regions"] = h["num_analysis_positions"] = None
    h["num_discrete_x_coords_in_full_map"] = None
    h["num_discrete_y_coords_in_full_map"] = None
    if mode in ("MAP", "MAPD", "NORM", "SDP"):
        h["num_spectral_regions"] = int(nxt.s())
    if mode in ("MAP", "MAPD"):
        h["num_analysis_positions"] = nxt.i()
        h["num_discrete_x_coords_in_full_map"] = nxt.i()
        h["num_discrete_y_coords_in_full_map"] = nxt.i()
    h["num_experiment_variables"] = nxt.i()
    h["experiment_variables"] = [
        SimpleNamespace(label=nxt.s(), unit=nxt.s())
        for _ in range(h["num_experiment_variables"])]
    n_incl = h["num_entries_inclusion_exclusion"] = nxt.i()
    # positive: an inclusion list (the rest excluded); negative: exclusion
    includes = [n_incl <= 0] * 40
    for _ in range(abs(n_incl)):
        k = nxt.i() - 1                     # parameters are numbered 1..40
        if 0 <= k < 40:
            includes[k] = n_incl > 0
    h["block_params_includes"] = includes
    h["num_manually_entered_items_in_block"] = nxt.i()
    h["num_future_upgrade_experiment_entries"] = nxt.i()
    h["future_upgrade_experiment_entries"] = [
        SimpleNamespace(label=nxt.s(), unit=nxt.s())
        for _ in range(h["num_future_upgrade_experiment_entries"])]
    h["num_future_upgrade_block_entries"] = nxt.i()
    h["num_blocks"] = nxt.i()

    blocks = []
    for _ in range(h["num_blocks"]):
        first = blocks[0] if blocks else None
        blocks.append(_parse_block(nxt, h, first))
    return SimpleNamespace(**h), [SimpleNamespace(**b) for b in blocks]


def _parse_block(nxt, h, first):
    inc = [True] * 40 if first is None else h["block_params_includes"]
    fb = first or {}
    mode = h["experiment_mode"]

    def take(k, key, read):
        return read() if inc[k] else fb[key]

    b = {"x_coord": None, "y_coord": None, "sputtering_z": None,
         "sputtering_num_particles": None, "sputtering_charge": None,
         "field_view_x": None, "field_view_y": None,
         "linescan_coordinates": None, "differential_width": None,
         "sputtering_source": None}
    b["block_identifier"] = nxt.s()
    b["sample_identifier"] = nxt.s()
    for k, key in enumerate(("year", "month", "day", "hour", "minute",
                             "second")):
        b[key] = take(k, key, nxt.i)
    b["num_hours_advance_gmt"] = take(6, "num_hours_advance_gmt", nxt.f)
    if inc[7]:
        b["num_lines_block_comment"] = nxt.i()
        b["block_comment"] = "\n".join(
            nxt.s() for _ in range(b["num_lines_block_comment"]))
    else:
        b["num_lines_block_comment"] = fb["num_lines_block_comment"]
        b["block_comment"] = fb["block_comment"]
    b["technique"] = take(8, "technique", nxt.s)
    if mode in ("MAP", "MAPD"):
        b["x_coord"] = take(9, "x_coord", lambda: int(float(nxt())))
        b["y_coord"] = take(9, "y_coord", lambda: int(float(nxt())))
    b["values_exp_var"] = take(10, "values_exp_var", lambda: [
        nxt() for _ in range(h["num_experiment_variables"])])
    b["analysis_source_label"] = take(11, "analysis_source_label", nxt.s)
    if mode in ("MAPDP", "MAPSVDP", "SDP", "SDPSV") \
            or b["technique"] in _SPUTTER_TECHNIQUES:
        b["sputtering_z"] = take(12, "sputtering_z", nxt.i)
        b["sputtering_num_particles"] = take(12, "sputtering_num_particles",
                                             nxt.f)
        b["sputtering_charge"] = take(12, "sputtering_charge", nxt.f)
    b["analysis_source_characteristic_energy"] = take(
        13, "analysis_source_characteristic_energy", nxt.f)
    b["analysis_source_strength"] = take(14, "analysis_source_strength",
                                         nxt.f)
    b["analysis_source_beam_width_x"] = take(
        15, "analysis_source_beam_width_x", nxt.f)
    b["analysis_source_beam_width_y"] = take(
        15, "analysis_source_beam_width_y", nxt.f)
    if mode in ("MAP", "MAPDP", "MAPSV", "MAPSVDP", "SEM"):
        b["field_view_x"] = take(16, "field_view_x", nxt.f)
        b["field_view_y"] = take(16, "field_view_y", nxt.f)
    if mode in ("MAPSV", "MAPSVDP", "SEM"):
        b["linescan_coordinates"] = take(
            17, "linescan_coordinates",
            lambda: SimpleNamespace(**{k: nxt.i() for k in (
                "first_linescan_start_x", "first_linescan_start_y",
                "first_linescan_finish_x", "first_linescan_finish_y",
                "last_linescan_finish_x", "last_linescan_finish_y")}))
    b["analysis_source_polar_incidence_angle"] = take(
        18, "analysis_source_polar_incidence_angle", nxt.f)
    b["analysis_source_azimuth"] = take(19, "analysis_source_azimuth", nxt.f)
    b["analyzer_mode"] = take(20, "analyzer_mode", nxt.s)
    b["analyzer_pass_energy_or_retard_ratio_or_mass_res"] = take(
        21, "analyzer_pass_energy_or_retard_ratio_or_mass_res", nxt.f)
    if b["technique"] == "AES diff":
        b["differential_width"] = take(22, "differential_width", nxt.f)
    b["magnification_analyzer_transfer_lens"] = take(
        23, "magnification_analyzer_transfer_lens", nxt.f)
    b["analyzer_work_function_or_acceptance_energy"] = take(
        24, "analyzer_work_function_or_acceptance_energy", nxt.f)
    b["target_bias"] = take(25, "target_bias", nxt.f)
    b["analysis_width_x"] = take(26, "analysis_width_x", nxt.f)
    b["analysis_width_y"] = take(26, "analysis_width_y", nxt.f)
    b["analyzer_axis_take_off_polar_angle"] = take(
        27, "analyzer_axis_take_off_polar_angle", nxt.f)
    b["analyzer_axis_take_off_azimuth"] = take(
        27, "analyzer_axis_take_off_azimuth", nxt.f)
    b["species_label"] = take(28, "species_label", nxt.s)
    b["transition_or_charge_state_label"] = take(
        29, "transition_or_charge_state_label", nxt.s)
    b["charge_detected_particle"] = take(29, "charge_detected_particle",
                                         nxt.i)
    # Only REGULAR scans are supported (as in the vamas package)
    b["x_label"] = take(30, "x_label", nxt.s)
    b["x_units"] = take(30, "x_units", nxt.s)
    b["x_start"] = take(30, "x_start", nxt.f)
    b["x_step"] = take(30, "x_step", nxt.f)
    if inc[31]:
        b["num_corresponding_variables"] = nxt.i()
        variables = [(nxt.s(), nxt.s())
                     for _ in range(b["num_corresponding_variables"])]
    else:
        b["num_corresponding_variables"] = fb["num_corresponding_variables"]
        variables = [(v.label, v.unit) for v in fb["corresponding_variables"]]
    b["corresponding_variables"] = [
        SimpleNamespace(label=label, unit=unit, y_values=[], y_min=None,
                        y_max=None) for label, unit in variables]
    b["signal_mode"] = take(32, "signal_mode", nxt.s)
    b["signal_collection_time"] = take(33, "signal_collection_time", nxt.f)
    b["num_scans_to_compile_block"] = take(34, "num_scans_to_compile_block",
                                           nxt.i)
    b["signal_time_correction"] = take(35, "signal_time_correction", nxt.f)
    if mode in ("MAPDP", "MAPSVDP", "SDP", "SDPSV") \
            and b["technique"] in _SPUTTER_SOURCE_TECHNIQUES:
        b["sputtering_source"] = take(
            36, "sputtering_source",
            lambda: SimpleNamespace(
                energy=nxt.f(), beam_current=nxt.f(), width_x=nxt.f(),
                width_y=nxt.f(), polar_incidence_angle=nxt.f(),
                azimuth=nxt.f(), mode=nxt.s()))
    b["sample_normal_polar_angle_tilt"] = take(
        37, "sample_normal_polar_angle_tilt", nxt.f)
    b["sample_normal_tilt_azimuth"] = take(37, "sample_normal_tilt_azimuth",
                                           nxt.f)
    b["sample_rotation_angle"] = take(38, "sample_rotation_angle", nxt.f)
    if inc[39]:
        b["num_additional_numerical_params"] = nxt.i()
        b["additional_numerical_params"] = [
            SimpleNamespace(label=nxt.s(), unit=nxt.s(), value=nxt.f())
            for _ in range(b["num_additional_numerical_params"])]
    else:
        b["num_additional_numerical_params"] = \
            fb["num_additional_numerical_params"]
        b["additional_numerical_params"] = fb["additional_numerical_params"]
    for _ in range(h["num_future_upgrade_block_entries"]):
        nxt()
    b["num_y_values"] = nxt.i()
    cvars = b["corresponding_variables"]
    for var in cvars:
        var.y_min = nxt.f()
        var.y_max = nxt.f()
    if cvars:
        for _ in range(int(b["num_y_values"] / len(cvars))):
            for var in cvars:
                var.y_values.append(nxt.f())
    return b


# ---------------------------------------------------------------------------
# CasaXPS information and peak fits (Vamas_Import.py)
# ---------------------------------------------------------------------------

CASA_INFO_FIELDS = [
    'Casa Sample Name', 'Stage Position', 'Angle', 'FoV Position',
    'Lens Mode', 'Neutraliser', 'Charge Balance', 'Filament Current',
    'Filament Bias', 'Magnet Lens Trim Coil', 'Aperture', 'Iris Position']

#: per-sheet Experimental Description labels (block_exp_data[1:])
VAMAS_EXP_LABELS = [
    "Sample ID", "Date", "Time", "Technique", "Species & Transition",
    "Number of scans", "Source Label", "Source Energy", "Source width X",
    "Source width Y", "Pass Energy", "Work Function", "Analyzer Mode",
    "Sputtering Energy", "Sputter Time", "Sample Tilt",
    "Take-off Polar Angle", "Take-off Azimuth", "Target Bias",
    "Analysis Width X", "Analysis Width Y", "X Label", "X Units", "X Start",
    "X Step", "Num Y Values", "Num Scans", "Collection Time",
    "Time Correction", "Y Unit", "# Comment Lines", "Block Comment",
] + list(CASA_INFO_FIELDS)


def parse_casa_info_lines(comment_text):
    """Kratos/Casa informational fields of a 'Casa Info Follows' block."""
    result = {k: '' for k in CASA_INFO_FIELDS}
    if not comment_text or 'Casa Info Follows' not in comment_text:
        return result
    tail = comment_text.split('Casa Info Follows', 1)[1]
    candidate_lines = [ln.strip() for ln in tail.split('\n')
                       if ln.strip()][:15]

    for ln in candidate_lines:              # sample name: first plain line
        try:
            float(ln)
            continue
        except ValueError:
            pass
        if ln.lower().startswith(('xps', 'aes', 'uhv')):
            break
        if ':' in ln or '(' in ln or '=' in ln or ln.startswith('FoV') \
                or ln.startswith('Aperture') or ln.startswith('Iris'):
            break
        result['Casa Sample Name'] = ln
        break

    for ln in candidate_lines:
        if ln.startswith('(') and 'Angle' in ln:
            paren_end = ln.find(')')
            if paren_end != -1:
                result['Stage Position'] = ln[:paren_end + 1]
            if 'Angle:' in ln:
                result['Angle'] = ln.split('Angle:', 1)[1].strip()
        elif ln.startswith('FoV Position'):
            result['FoV Position'] = ln.split('FoV Position', 1)[1].strip()
        elif ln.startswith('Lens Mode'):
            result['Lens Mode'] = ln.split(':', 1)[1].strip() \
                if ':' in ln else ''
        elif ln.startswith('Neutraliser'):
            result['Neutraliser'] = ln.split(':', 1)[1].strip() \
                if ':' in ln else ''
        elif ln.startswith('Charge Balance'):
            for part in ln.split(':'):
                if '=' not in part:
                    continue
                key, val = part.split('=', 1)
                key, val = key.strip(), val.strip()
                if key in result:
                    result[key] = val
        elif ln.startswith('Aperture Description'):
            result['Aperture'] = ln.split(':', 1)[1].strip() \
                if ':' in ln else ''
        elif ln.startswith('Iris Position Description'):
            result['Iris Position'] = (ln.split(':', 1)[1].strip().rstrip('.')
                                       if ':' in ln else '')
    return result


def voigt_fwhm_split(fwhm, fraction):
    """(Gaussian FWHM, Lorentzian FWHM) of a Voigt of total *fwhm* and L/G
    *fraction* % (Olivero-Longbothum; Peak_Functions.voigt_fwhm_split)."""
    r = min(max(fraction / 100.0, 0.0), 0.999)
    k = 0.5346 * r + np.sqrt(0.2166 * r * r + (1.0 - r) ** 2)
    scale = fwhm / k
    return (1.0 - r) * scale, r * scale


def _parse_la_model(model_str):
    """(model, L/G, sigma, gamma) for a Casa LA(...) lineshape."""
    la_params = re.search(r'LA\(([\d.]+),\s*([\d.]+),\s*([\d.]+)\)',
                          model_str)
    if la_params:
        sigma = float(la_params.group(1))
        gamma = float(la_params.group(2))
        w_g = float(la_params.group(3))
        model = "LA*G (Area, σ/γ, γ)" if w_g > 100 else "LA (Area, σ, γ)"
        return model, 100 * sigma / (sigma + gamma), sigma, gamma
    two = re.search(r'LA\(([\d.]+),\s*([\d.]+)\)', model_str)
    if two:
        p1, p2 = float(two.group(1)), float(two.group(2))
        if p2 > 100:
            return "LA*G (Area, σ/γ, γ)", 50, p1, p1
        return "LA (Area, σ, γ)", 100 * p1 / (p1 + p2), p1, p2
    single = re.search(r'LA\((\d+)\)', model_str)
    if single:
        return "Voigt (Area)", int(single.group(1)), 0.0, 0.0
    return "LA (Area, σ, γ)", 100 * 0.6 / (0.6 + 0.4), 0.6, 0.4


def parse_casa_peak_fitting(block_comment, num_scans=1,
                            photon_energy=DEFAULT_PHOTONS,
                            transmission_data=None, collection_time=1.0,
                            core_level_name=None):
    """{'Background', 'Peaks'} from the CASA lines of a block comment, in
    KherveFitting's peak-table form, or None."""
    if "Casa Info Follows" not in block_comment:
        return None
    avg_transmission = 1.0
    if transmission_data and len(transmission_data) > 0:
        avg_transmission = np.mean(transmission_data)

    lines = block_comment.split('\n')
    casa_start = next((i + 1 for i, line in enumerate(lines)
                       if "Casa Info Follows" in line), -1)
    if casa_start == -1:
        return None

    fitting_data = {'Background': {}, 'Peaks': {}}
    peak_name_counts = {}
    for raw_line in lines[casa_start:]:
        line = raw_line.strip()
        if line.startswith('CASA region'):
            if len(line.split()) < 5:
                continue
            bg_matches = re.findall(r'\(\*([^*]+)\*\)', line)
            bg_type = bg_matches[1] if len(bg_matches) > 1 else "Shirley"
            kf_bg_type = "Shirley" if bg_type.lower() == "shirley" \
                else bg_type
            energy_match = re.search(
                r'\(\*[^*]*\*\)\s*\(\*[^*]*\*\)\s*([-+\d.eE]+)\s+([-+\d.eE]+)',
                line)
            try:
                if not energy_match:
                    raise ValueError(line)
                low_ke = float(energy_match.group(1))
                high_ke = float(energy_match.group(2))
            except (ValueError, IndexError):
                continue
            fitting_data['Background'] = {
                'Bkg Type': kf_bg_type,
                'Bkg Low': round(photon_energy - high_ke, 3),
                'Bkg High': round(photon_energy - low_ke, 3),
                'Bkg Offset Low': '0',
                'Bkg Offset High': '0',
                'Bkg Y': []}
        elif line.startswith('CASA comp'):
            name, peak = _parse_casa_comp(
                line, fitting_data, peak_name_counts, core_level_name,
                photon_energy, avg_transmission, num_scans, collection_time)
            fitting_data['Peaks'][name] = peak
    return fitting_data if (fitting_data['Background']
                            or fitting_data['Peaks']) else None


def _parse_casa_comp(line, fitting_data, peak_name_counts, core_level_name,
                     photon_energy, avg_transmission, num_scans,
                     collection_time):
    peak_matches = re.findall(r'\(\*([^*]+)\*\)', line)
    raw_peak_name = peak_matches[0] if peak_matches \
        else f"Peak_{len(fitting_data['Peaks']) + 1}"
    if raw_peak_name:                       # "C 1s" -> "C1s"
        raw_peak_name = re.sub(r'([A-Z][a-z]?)\s+(\d+[spdfghi])', r'\1\2',
                               raw_peak_name)
    if core_level_name and raw_peak_name == core_level_name:
        peak_name_counts[raw_peak_name] = \
            peak_name_counts.get(raw_peak_name, 0) + 1
        peak_name = f"{raw_peak_name} p{peak_name_counts[raw_peak_name]}"
    elif raw_peak_name in fitting_data['Peaks']:
        if raw_peak_name not in peak_name_counts:
            peak_name_counts[raw_peak_name] = 1
        peak_name_counts[raw_peak_name] += 1
        peak_name = f"{raw_peak_name} p{peak_name_counts[raw_peak_name]}"
    else:
        peak_name = raw_peak_name

    model_str = peak_matches[1] if len(peak_matches) > 1 else "GL(30)"
    model, lg_value, sigma_value, gamma_value = "GL (Area)", 30, 0.6, 0.4
    if 'SGL(' in model_str:
        m = re.search(r'SGL\((\d+)\)', model_str)
        lg_value = float(m.group(1)) if m else 30
        model = "SGL (Area)"
    elif 'GL(' in model_str:
        m = re.search(r'GL\((\d+)\)', model_str)
        lg_value = float(m.group(1)) if m else 30
        model = "GL (Area)"
    elif 'LA(' in model_str:
        model, lg_value, sigma_value, gamma_value = _parse_la_model(model_str)

    num = r'\s+([\d.e-]+)\s+([\d.e-]+)\s+([\d.e-]+)\s+(-?\d+)\s+([\d.e-]+)'
    area_match = re.search(r'Area' + num, line)
    fwhm_match = re.search(r'MFWHM' + num, line)
    pos_match = re.search(r'Position' + num, line)

    if collection_time > 0:
        correction_factor = avg_transmission * num_scans * collection_time
    else:
        correction_factor = avg_transmission * num_scans
    area_value = float(area_match.group(1)) / correction_factor \
        if area_match else 1000
    area_value = round(area_value, 2)
    if area_match:
        constrained = int(area_match.group(4))
        if constrained >= 0:
            area_constraint = (f"{chr(65 + constrained)}*"
                               f"{float(area_match.group(5))}")
        else:
            area_min = float(area_match.group(2)) \
                if float(area_match.group(2)) > 1e-19 else 1
            area_max = float(area_match.group(3)) / avg_transmission
            area_constraint = f"{area_min}:{area_max}"
    else:
        area_constraint = "1:1e7"

    pos_ke = float(pos_match.group(1)) if pos_match else 800
    position_be = photon_energy - pos_ke
    if pos_match:
        constrained = int(pos_match.group(4))
        if constrained >= 0:
            pos_constraint = f"{chr(65 + constrained)}+0.0"
        else:
            pos_be_min = photon_energy - float(pos_match.group(3))
            pos_be_max = photon_energy - float(pos_match.group(2))
            pos_constraint = f"{pos_be_min:.2f}:{pos_be_max:.2f}"
    else:
        pos_constraint = "1:1000"

    fwhm_value = round(float(fwhm_match.group(1)) if fwhm_match else 1.5, 2)
    if fwhm_match:
        constrained = int(fwhm_match.group(4))
        if constrained >= 0:
            fwhm_constraint = (f"{chr(65 + constrained)}*"
                               f"{float(fwhm_match.group(5))}")
        else:
            fwhm_constraint = f"{fwhm_match.group(2)}:{fwhm_match.group(3)}"
    else:
        fwhm_constraint = "0.3:3.5"

    if model == "Voigt (Area)":
        f_g, f_l = voigt_fwhm_split(fwhm_value, lg_value)
        sigma_value, gamma_value = round(f_g, 3), round(f_l, 3)

    if 'LA' in model:
        height = area_value / (fwhm_value * 1.5)
    else:
        height = area_value / (fwhm_value * np.sqrt(np.pi / (4 * np.log(2))))

    bkg = fitting_data['Background']
    peak = {
        'Position': position_be,
        'Height': round(height, 2),
        'FWHM': round(fwhm_value, 2),
        'L/G': lg_value,
        'Area': round(area_value, 2),
        'Sigma': sigma_value,
        'Gamma': gamma_value,
        'Skew': 0.1,
        'Fitting Model': model,
        'Bkg Type': bkg.get('Bkg Type', ''),
        'Bkg Low': bkg.get('Bkg Low', '0'),
        'Bkg High': bkg.get('Bkg High', '0'),
        'Bkg Offset Low': '0',
        'Bkg Offset High': '0',
    }
    if 'LA' in model:
        lg_constraint = "Fixed"
    else:
        lg_constraint = "Fixed" if any(x in model_str for x in
                                       ['GL(', 'SGL(']) else "5:80"
    peak['Constraints'] = {
        'Position': pos_constraint,
        'Height': "1:1e7",
        'FWHM': fwhm_constraint,
        'L/G': lg_constraint,
        'Area': area_constraint,
        'Sigma': "0.01:10" if 'LA' in model else "0.3:3",
        'Gamma': "0.01:10" if 'LA' in model else "0.3:3",
        'Skew': "0.01:2",
    }
    return peak_name, peak


def check_for_casa_fitting(blocks):
    return any("Casa Info Follows" in (b.block_comment or "")
               for b in blocks)


# ---------------------------------------------------------------------------
# Records and core levels (open_vamas_file / build_vamas_core_levels)
# ---------------------------------------------------------------------------

def _sheet_name(block, taken):
    if block.species_label.lower() == "wide" \
            or block.transition_or_charge_state_label.lower() == "none":
        raw = block.species_label
    else:
        raw = f"{block.species_label}{block.transition_or_charge_state_label}"
    raw = normalize_auger_and_valence_names(raw.replace("/", "_"))
    name = normalize_sheet_name(phi_region_base(raw))
    if name in taken:
        count = 1
        while f"{name}{count}" in taken:
            count += 1
        name = f"{name}{count}"
    taken.add(name)
    return name


def vamas_records(blocks, import_fitting=True,
                  workfunction=DEFAULT_WORKFUNCTION,
                  photons=DEFAULT_PHOTONS):
    """``(records, fitting_data)`` exactly as ``open_vamas_file`` collects
    them (one record per block with at least one scan)."""
    records, fitting_data, taken = [], {}, set()
    for i, block in enumerate(blocks, start=1):
        num_scans = block.num_scans_to_compile_block
        if num_scans == 0:
            continue
        sheet_name = _sheet_name(block, taken)

        num_points = block.num_y_values
        x_values = [block.x_start + j * block.x_step
                    for j in range(num_points)]
        if not block.corresponding_variables:
            continue
        y_values = block.corresponding_variables[0].y_values
        y_unit = block.corresponding_variables[0].unit
        collection_time = block.signal_collection_time
        if collection_time is None:
            collection_time = 1.0
        if y_unit != "c/s" and collection_time > 0:
            y_values = [y / (num_scans * collection_time) for y in y_values]
        elif y_unit != "c/s":
            y_values = [y / num_scans for y in y_values]

        if block.x_label.lower() in ("kinetic energy", "ke"):
            photon_energy = block.analysis_source_characteristic_energy
            x_values = [photon_energy - x - workfunction for x in x_values]
            x_label = "Binding Energy"
        else:
            x_label = block.x_label

        if len(block.corresponding_variables) > 1:
            raw_t = block.corresponding_variables[1].y_values
            div = num_scans * collection_time if collection_time > 0 \
                else num_scans
            transmission_data = [t / div for t in raw_t]
        else:
            div = num_scans * collection_time if collection_time > 0 \
                else num_scans
            transmission_data = [1.0 / div] * len(y_values)

        # num_y_values counts every corresponding variable: trim x to y
        n_points = min(len(x_values), len(y_values))
        x_values = x_values[:n_points]
        y_values = y_values[:n_points]
        trans_values = [transmission_data[j] if j < len(transmission_data)
                        else 1.0 for j in range(n_points)]
        div = num_scans * collection_time if collection_time > 0 \
            else num_scans
        corrected_y = [(y / abs(t)) / div
                       for y, t in zip(y_values, trans_values)]

        if import_fitting:
            casa_hv = block.analysis_source_characteristic_energy or photons
            casa = parse_casa_peak_fitting(
                block.block_comment, num_scans, casa_hv, transmission_data,
                collection_time, sheet_name)
            if casa:
                fitting_data[sheet_name] = {'Fitting':
                                            {'Peaks': casa['Peaks']}}
                if casa['Background']:
                    bkg = casa['Background']
                    bkg['Bkg X'] = x_values
                    bkg['Bkg Y'] = corrected_y
                    bkg['Recorded_Ranges'] = [(
                        0.00, 0.00, round(float(bkg.get('Bkg Low', 0.0)), 2),
                        round(float(bkg.get('Bkg High', 0.0)), 2))]
                    fitting_data[sheet_name]['Background'] = bkg

        source = getattr(block, 'sputtering_source', None)
        sputter_time = (getattr(source, 'mode', '') or '') \
            if source is not None else ''
        exp_values = [
            block.sample_identifier,
            f"{block.year}/{block.month}/{block.day}",
            f"{block.hour}:{block.minute}:{block.second}",
            block.technique,
            f"{block.species_label} {block.transition_or_charge_state_label}",
            num_scans,
            block.analysis_source_label,
            block.analysis_source_characteristic_energy,
            block.analysis_source_beam_width_x,
            block.analysis_source_beam_width_y,
            block.analyzer_pass_energy_or_retard_ratio_or_mass_res,
            block.analyzer_work_function_or_acceptance_energy,
            block.analyzer_mode,
            'N/A',          # the vamas package has no sputtering_source_energy
            sputter_time,
            block.sample_normal_polar_angle_tilt,
            block.analyzer_axis_take_off_polar_angle,
            block.analyzer_axis_take_off_azimuth,
            block.target_bias,
            block.analysis_width_x,
            block.analysis_width_y,
            block.x_label,
            block.x_units,
            block.x_start,
            block.x_step,
            block.num_y_values,
            num_scans,
            block.signal_collection_time,
            block.signal_time_correction,
            y_unit,
            block.num_lines_block_comment,
            block.block_comment,
        ]
        casa_info = parse_casa_info_lines(block.block_comment)
        exp_values.extend(casa_info.get(f, '') for f in CASA_INFO_FIELDS)
        records.append({
            'sheet_name': sheet_name, 'x_label': x_label,
            'x_values': list(x_values), 'raw_y': list(y_values),
            'corrected_y': corrected_y, 'transmission': trans_values,
            'exp_values': exp_values})
    return records, fitting_data


def build_vamas_core_levels(records, fitting_data=None):
    """{sheet: core level} for the records, with any Casa fit merged in."""
    core_levels = {}
    for rec in records:
        name = rec['sheet_name']
        cl = core_level(
            name, be_values=rec['x_values'], plot_values=rec['corrected_y'],
            raw_values=rec['raw_y'], transmission=rec['transmission'],
            experimental_info=dict(zip(VAMAS_EXP_LABELS, rec['exp_values'])))
        if fitting_data and name in fitting_data:
            cl.update(fitting_data[name])
        core_levels[name] = cl
    return core_levels


def read(path, import_fitting=True):
    """A ``.vms`` file -> {sheet name: core level}."""
    _header, blocks = read_vamas(path)
    records, fitting = vamas_records(blocks, import_fitting=import_fitting)
    if not records:
        raise ValueError("No usable spectra were found in this VAMAS file.")
    return build_vamas_core_levels(records, fitting)


FORMATS = [
    Format("XPS", "Vamas file (.vms)", (".vms",), read, group=""),
]
