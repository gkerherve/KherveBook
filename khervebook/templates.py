"""Notebook templates — File ▸ New from Template.

Ready-made lab notebooks, after kELN's templates (KherveOS): each is a
list of cells — headings, Lab records (steps, runs, measurements,
reactions, safety) and code that reads them with ``klab()`` — dated
today. A user's own notebooks can be saved as templates too; they live
as plain ``.kbook`` files in the per-user templates folder and appear
under "My Templates".

Copyright (C) 2026 Gwilherm Kerherve

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.
"""

import datetime
import json
import re
from pathlib import Path

from . import labmath as lm


def _md(text):
    return {"type": "markdown", "source": text.strip("\n")}


def _code(text, title=""):
    d = {"type": "code", "source": text.strip("\n")}
    if title:
        d["title"] = title
    return d


def _lab(kind, title="", **data):
    full = lm.default_data(kind)
    full.update(data)
    d = {"type": "lab", "source": json.dumps(
        {"kbook_lab": 1, "kind": kind, "data": lm.normalise(kind, full)})}
    if title:
        d["title"] = title
    return d


def _steps(*texts):
    return [{"text": t, "done": False, "by": "", "at": ""} for t in texts]


def _cols(*specs):
    return [{"name": n, "unit": u} for n, u in specs]


def _rows(n, width):
    return [[""] * width for _ in range(n)]


def _header(title, aim):
    today = datetime.date.today().isoformat()
    return _md(f"# {title}\n\n**Date:** {today}  \n**Aim:** {aim}")


def _samples():
    """An empty Samples cell: add the samples, cite them as @S-0001."""
    return {"type": "samples", "title": "Samples",
            "source": json.dumps({"kbook_samples": 1, "items": []})}


# -- built-in templates -------------------------------------------------------
def xps_session():
    return [
        _header("XPS session", "chemical state of the surface"),
        _samples(),
        _lab("run", "Acquisition", instrument="", method="Survey + "
             "high-resolution core levels",
             params="Source = Al Kα monochromatic\nPass energy (survey) = "
                    "160 eV\nPass energy (regions) = 20 eV\nCharge "
                    "neutraliser = on\nSpot size = "),
        _lab("measurements", "Samples and regions",
             columns=_cols(("Sample", ""), ("Regions", ""),
                           ("C 1s ref", "eV"), ("Comment", "")),
             rows=_rows(3, 4)),
        _md("## Analysis\nDrop the `.kfit` project in below (a KFit cell) "
            "and compare the fitted components here."),
        _code("# kfit('C1s').frame() gives the fitted components as a table\n"
              "runs = klab('Samples and regions')\nruns", "Overview"),
    ]


def organic_synthesis():
    return [
        _header("Organic synthesis", "target compound and route"),
        _samples(),
        _lab("safety", "Risk assessment", ppe=["Lab coat", "Safety glasses",
                                               "Gloves", "Fume hood"]),
        _lab("reaction", "Reaction"),
        _lab("steps", "Procedure", steps=_steps(
            "Charge the flask with the limiting reagent and solvent",
            "Add the reagents; note temperature and time",
            "Monitor by TLC until complete",
            "Work-up: quench, extract, dry, concentrate",
            "Purify (column / recrystallisation)",
            "Weigh the product; enter the actual yield above")),
        _md("## Characterisation\nNMR, IR, MS, melting point — attach the "
            "spectra in a File cell."),
    ]


def tga_run():
    return [
        _header("TGA run", "mass loss and decomposition steps"),
        _samples(),
        _lab("run", "Run", method="Ramp 10 °C/min to 800 °C",
             params="Atmosphere = N2, 50 mL/min\nPan = alumina\n"
                    "Initial mass (mg) = "),
        _lab("measurements", "Mass-loss steps",
             columns=_cols(("Step", ""), ("Onset", "°C"), ("End", "°C"),
                           ("Mass loss", "%")), rows=_rows(3, 4)),
        _code("steps = klab('Mass-loss steps')\n"
              "print('total mass loss:', steps['Mass loss (%)'].sum(), '%')\n"
              "steps", "Summary"),
    ]


def xrd_measurement():
    return [
        _header("XRD measurement", "phase identification"),
        _samples(),
        _lab("run", "Scan", method="θ–2θ, 10–80°",
             params="Radiation = Cu Kα (1.5406 Å)\nStep = 0.02°\n"
                    "Time per step (s) = \nSlits = "),
        _lab("measurements", "Peaks",
             columns=_cols(("2θ", "°"), ("FWHM", "°"), ("hkl", ""),
                           ("Phase", "")), rows=_rows(4, 4)),
        _code("import numpy as np\n"
              "p = klab('Peaks').dropna(subset=['2θ (°)', 'FWHM (°)'])\n"
              "lam, K = 0.15406, 0.9            # nm, Scherrer constant\n"
              "beta = np.radians(p['FWHM (°)'])\n"
              "theta = np.radians(p['2θ (°)'] / 2)\n"
              "p['d (nm)'] = lam / (2 * np.sin(theta))\n"
              "p['crystallite (nm)'] = K * lam / (beta * np.cos(theta))\n"
              "p", "d-spacing and Scherrer size"),
    ]


def solution_preparation():
    return [
        _header("Solution preparation", "stock solution"),
        _lab("safety", "Hazards", ppe=["Lab coat", "Safety glasses",
                                       "Gloves"]),
        _lab("measurements", "Solutions",
             columns=_cols(("Solute", ""), ("MW", "g/mol"),
                           ("Concentration", "mol/L"), ("Volume", "mL")),
             rows=[["NaCl", "58.44", "0.1", "250"], ["", "", "", ""]]),
        _code("s = klab('Solutions').dropna(subset=['MW (g/mol)'])\n"
              "s['Mass to weigh (g)'] = (s['MW (g/mol)'] * "
              "s['Concentration (mol/L)'] * s['Volume (mL)'] / 1000)\n"
              "s", "Masses to weigh"),
        _lab("steps", "Preparation", steps=_steps(
            "Weigh the solute", "Dissolve in ~80 % of the volume",
            "Transfer to the volumetric flask and make up to the mark",
            "Label: name, concentration, date, initials")),
    ]


def calibration_log():
    return [
        _header("Calibration log", "instrument calibration against "
                "standards"),
        _lab("run", "Instrument"),
        _lab("measurements", "Standards",
             columns=_cols(("Standard", ""), ("Nominal", ""),
                           ("Measured", "")),
             rows=_rows(5, 3)),
        _code("import numpy as np\n"
              "c = klab('Standards').dropna(subset=['Nominal', 'Measured'])\n"
              "slope, offset = np.polyfit(c['Measured'], c['Nominal'], 1)\n"
              "plt.plot(c['Measured'], c['Nominal'], 'o')\n"
              "x = np.linspace(c['Measured'].min(), c['Measured'].max())\n"
              "plt.plot(x, slope * x + offset, '-')\n"
              "plt.xlabel('measured'); plt.ylabel('nominal')\n"
              "print(f'nominal = {slope:.5g} × measured + {offset:.5g}')",
              "Calibration fit"),
    ]


def thin_film_deposition():
    return [
        _header("Thin-film deposition", "film growth"),
        _samples(),
        _lab("safety", "Hazards"),
        _lab("run", "Deposition", method="",
             params="Base pressure (mbar) = \nWorking pressure (mbar) = \n"
                    "Gas = \nPower (W) = \nSubstrate temperature (°C) = \n"
                    "Time (min) = "),
        _lab("steps", "Procedure", steps=_steps(
            "Clean substrates (solvent sonication)", "Load and pump down",
            "Pre-sputter / condition the target", "Deposit",
            "Cool and vent; unload and label the samples")),
        _lab("measurements", "Thickness",
             columns=_cols(("Sample", ""), ("Thickness", "nm"),
                           ("Rate", "nm/min")), rows=_rows(3, 3)),
    ]


def instrument_maintenance():
    return [
        _header("Instrument maintenance", "service record"),
        _lab("run", "Instrument", method="Maintenance"),
        _lab("safety", "Hazards", hazards="Isolate power / vacuum / "
             "high voltage before opening the instrument"),
        _lab("steps", "Work done", steps=_steps(
            "Describe the fault or the scheduled task",
            "Isolate and make safe", "Replace / clean / adjust",
            "Test and return to service")),
        _lab("measurements", "Parts",
             columns=_cols(("Part", ""), ("Part no.", ""), ("Qty", "")),
             rows=_rows(2, 3)),
    ]


def risk_assessment():
    return [
        _header("Risk assessment", "the activity being assessed"),
        _lab("safety", "Assessment"),
        _md("## Emergency\n- First aid: \n- Spill procedure: \n"
            "- Contacts: "),
        _lab("steps", "Sign-off", steps=_steps(
            "Read and understood by the operator",
            "Reviewed by the supervisor")),
    ]


def literature_note():
    return [
        _header("Literature note", "what the paper shows and why it "
                "matters here"),
        _md("## Reference\nAuthors, *Title*, Journal **vol**, pages "
            "(year). DOI: \n\n## Key points\n- \n\n## Methods worth "
            "reusing\n- \n\n## Open questions\n- "),
    ]


#: (name, category, builder)
TEMPLATES = [
    ("XPS session", "Measurements", xps_session),
    ("TGA run", "Measurements", tga_run),
    ("XRD measurement", "Measurements", xrd_measurement),
    ("Calibration log", "Measurements", calibration_log),
    ("Organic synthesis", "Chemistry", organic_synthesis),
    ("Solution preparation", "Chemistry", solution_preparation),
    ("Thin-film deposition", "Materials", thin_film_deposition),
    ("Instrument maintenance", "Lab routine", instrument_maintenance),
    ("Risk assessment", "Lab routine", risk_assessment),
    ("Literature note", "Office", literature_note),
]


def template_json(builder) -> str:
    from .notebook import FORMAT_VERSION
    return json.dumps({"format": "kbook", "version": FORMAT_VERSION,
                       "cells": builder()})


# -- user templates -------------------------------------------------------------
def user_dir() -> Path:
    from PyQt5.QtCore import QStandardPaths
    base = QStandardPaths.writableLocation(QStandardPaths.AppDataLocation)
    return Path(base or Path.home() / ".khervebook") / "templates"


def user_templates(folder=None):
    """[(name, path)] of the user's saved templates, by name."""
    folder = Path(folder) if folder else user_dir()
    if not folder.is_dir():
        return []
    return sorted(((p.stem, p) for p in folder.glob("*.kbook")),
                  key=lambda t: t[0].lower())


def save_user_template(name: str, kbook_json: str, folder=None) -> Path:
    """Write the notebook as a template. Samples cells are kept but
    emptied — a template describes the work, not one occasion's samples."""
    folder = Path(folder) if folder else user_dir()
    folder.mkdir(parents=True, exist_ok=True)
    safe = re.sub(r'[\\/:*?"<>|]+', "_", name).strip() or "Template"
    doc = json.loads(kbook_json)
    doc.pop("samples", None)
    for cell in doc.get("cells") or []:
        if cell.get("type") == "samples":
            try:
                reg = json.loads(cell.get("source") or "{}")
            except ValueError:
                reg = {}
            reg["items"] = []
            cell["source"] = json.dumps(reg)
    path = folder / f"{safe}.kbook"
    path.write_text(json.dumps(doc, indent=1), encoding="utf-8")
    return path
