"""The Qt-free half of the Lab cell: its kinds, data and arithmetic.

A Lab cell holds one structured lab record, after kELN's blocks
(KherveOS): a **measurements** table (mean ± sd per column), **protocol
steps** stamped with who did each and when, an **instrument run**, a
**reaction** table (mmol, equivalents and yield from masses, volumes and
formulas) and a **safety** assessment. This module normalises each
kind's stored data, does the sums and writes the Markdown used by the
.ipynb export and the AI assistant, so all of it is testable without Qt.

Copyright (C) 2026 Gwilherm Kerherve

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.
"""

import math
import re

#: (key, menu label) of every kind, in menu order.
KINDS = (("measurements", "Measurements"),
         ("steps", "Protocol Steps"),
         ("run", "Instrument Run"),
         ("reaction", "Reaction"),
         ("safety", "Safety"))
KIND_LABELS = dict(KINDS)

ROLES = ("reactant", "reagent", "catalyst", "solvent", "product")
RISKS = ("low", "medium", "high")
GHS = (("GHS01", "Explosive"), ("GHS02", "Flammable"),
       ("GHS03", "Oxidising"), ("GHS04", "Gas under pressure"),
       ("GHS05", "Corrosive"), ("GHS06", "Acute toxicity"),
       ("GHS07", "Harmful / irritant"), ("GHS08", "Health hazard"),
       ("GHS09", "Environment"))
PPE = ("Lab coat", "Safety glasses", "Gloves", "Face shield", "Fume hood",
       "Respirator")
RUN_FIELDS = (("instrument", "Instrument"), ("method", "Method"),
              ("operator", "Operator"), ("start", "Start"), ("end", "End"),
              ("file", "Data file"))
#: reaction table columns: (key, header)
REACTION_COLS = (("name", "Name"), ("role", "Role"), ("formula", "Formula"),
                 ("mw", "MW (g/mol)"), ("mass", "Mass (mg)"),
                 ("volume", "Vol (mL)"), ("density", "ρ (g/mL)"),
                 ("mmol", "mmol"))

# Standard atomic weights (IUPAC, abridged), H to U.
_WEIGHTS = """
H 1.008 He 4.0026 Li 6.94 Be 9.0122 B 10.81 C 12.011 N 14.007 O 15.999
F 18.998 Ne 20.180 Na 22.990 Mg 24.305 Al 26.982 Si 28.085 P 30.974
S 32.06 Cl 35.45 Ar 39.948 K 39.098 Ca 40.078 Sc 44.956 Ti 47.867
V 50.942 Cr 51.996 Mn 54.938 Fe 55.845 Co 58.933 Ni 58.693 Cu 63.546
Zn 65.38 Ga 69.723 Ge 72.630 As 74.922 Se 78.971 Br 79.904 Kr 83.798
Rb 85.468 Sr 87.62 Y 88.906 Zr 91.224 Nb 92.906 Mo 95.95 Tc 98
Ru 101.07 Rh 102.91 Pd 106.42 Ag 107.87 Cd 112.41 In 114.82 Sn 118.71
Sb 121.76 Te 127.60 I 126.90 Xe 131.29 Cs 132.91 Ba 137.33 La 138.91
Ce 140.12 Pr 140.91 Nd 144.24 Pm 145 Sm 150.36 Eu 151.96 Gd 157.25
Tb 158.93 Dy 162.50 Ho 164.93 Er 167.26 Tm 168.93 Yb 173.05 Lu 174.97
Hf 178.49 Ta 180.95 W 183.84 Re 186.21 Os 190.23 Ir 192.22 Pt 195.08
Au 196.97 Hg 200.59 Tl 204.38 Pb 207.2 Bi 208.98 Po 209 At 210 Rn 222
Fr 223 Ra 226 Ac 227 Th 232.04 Pa 231.04 U 238.03 D 2.014
""".split()
ATOMIC_WEIGHTS = {_WEIGHTS[i]: float(_WEIGHTS[i + 1])
                  for i in range(0, len(_WEIGHTS), 2)}

_TOKEN = re.compile(r"([A-Z][a-z]?)|(\d+(?:\.\d+)?)|([(\[])|([)\]])")


def molar_mass(formula: str):
    """g/mol of a formula like ``CuSO4·5H2O`` or ``Ca(OH)2``, else None."""
    text = (formula or "").strip()
    if not text:
        return None
    total = 0.0
    # Hydrates and adducts: "CuSO4·5H2O", "CuSO4.5H2O", "CuSO4*5H2O".
    for part in re.split(r"[·.*•]", text.replace(" ", "")):
        if not part:
            continue
        m = re.match(r"^(\d+(?:\.\d+)?)(?=[A-Z(\[])", part)
        mult = float(m.group(1)) if m else 1.0
        if m:
            part = part[m.end():]
        mass = _group_mass(part)
        if mass is None:
            return None
        total += mult * mass
    return round(total, 3) if total else None


def _group_mass(text):
    stack = [0.0]
    pos = 0
    last = None                    # mass of the last atom/group, for counts
    while pos < len(text):
        m = _TOKEN.match(text, pos)
        if not m:
            return None
        pos = m.end()
        el, num, opening, closing = m.groups()
        if el:
            if el not in ATOMIC_WEIGHTS:
                return None
            last = ATOMIC_WEIGHTS[el]
            stack[-1] += last
        elif num:
            if last is None:
                return None
            stack[-1] += last * (float(num) - 1)
            last = None
        elif opening:
            stack.append(0.0)
            last = None
        elif closing:
            if len(stack) < 2:
                return None
            last = stack.pop()
            stack[-1] += last
    return stack[0] if len(stack) == 1 else None


def number(text):
    """A float from a cell's text ("1.5", "2,5", "3e-2", "12 mg"), or None."""
    if isinstance(text, (int, float)) and not isinstance(text, bool):
        return float(text) if math.isfinite(text) else None
    m = re.match(r"^\s*([-+]?(?:\d+(?:[.,]\d*)?|[.,]\d+)(?:[eE][-+]?\d+)?)",
                 str(text or ""))
    if not m:
        return None
    try:
        return float(m.group(1).replace(",", "."))
    except ValueError:
        return None


def stats(values):
    """(n, mean, sample sd) over the numeric values; sd None when n < 2."""
    xs = [v for v in (number(x) for x in values) if v is not None]
    n = len(xs)
    if not n:
        return 0, None, None
    mean = sum(xs) / n
    sd = (math.sqrt(sum((x - mean) ** 2 for x in xs) / (n - 1))
          if n > 1 else None)
    return n, mean, sd


def fmt(value, digits=4):
    """Compact significant-figure formatting for computed numbers."""
    if value is None:
        return ""
    if value == 0:
        return "0"
    return f"{value:.{digits}g}"


def stats_text(values) -> str:
    n, mean, sd = stats(values)
    if not n:
        return ""
    if sd is None:
        return f"{fmt(mean)} (n=1)"
    return f"{fmt(mean)} ± {fmt(sd, 2)} (n={n})"


# -- reaction -------------------------------------------------------------
def reaction_compute(data: dict) -> dict:
    """Per-row mw/mmol/equiv and the yield of a reaction table.

    mmol comes from the typed mmol, else mass (mg) / MW, else volume
    (mL) × density (g/mL) × 1000 / MW. The limiting reagent is the
    reactant with the fewest mmol; equivalents are relative to it. The
    theoretical yield assumes 1:1 to the first product row.
    """
    rows = data.get("rows") or []
    out = []
    for r in rows:
        mw = number(r.get("mw")) or molar_mass(r.get("formula"))
        mmol = number(r.get("mmol"))
        if mmol is None and mw:
            mass = number(r.get("mass"))
            vol, rho = number(r.get("volume")), number(r.get("density"))
            if mass is not None:
                mmol = mass / mw
            elif vol is not None and rho is not None:
                mmol = vol * rho * 1000.0 / mw
        out.append({"mw": mw, "mmol": mmol, "equiv": None})
    reactants = [i for i, r in enumerate(rows)
                 if r.get("role", "reactant") == "reactant"
                 and out[i]["mmol"]]
    limiting = min(reactants, key=lambda i: out[i]["mmol"]) \
        if reactants else None
    if limiting is not None:
        base = out[limiting]["mmol"]
        for i, r in enumerate(rows):
            if r.get("role") != "product" and out[i]["mmol"]:
                out[i]["equiv"] = out[i]["mmol"] / base
    theo = pct = None
    product = next((i for i, r in enumerate(rows)
                    if r.get("role") == "product"), None)
    if limiting is not None and product is not None and out[product]["mw"]:
        theo = out[limiting]["mmol"] * out[product]["mw"]       # mg
        actual = number(data.get("actual"))
        if actual is not None and theo:
            pct = 100.0 * actual / theo
    return {"rows": out, "limiting": limiting, "product": product,
            "theoretical_mg": theo, "yield_pct": pct}


# -- data -----------------------------------------------------------------
def default_data(kind: str) -> dict:
    if kind == "measurements":
        return {"columns": [{"name": "Sample", "unit": ""},
                            {"name": "Value", "unit": ""}],
                "rows": [["", ""] for _ in range(3)]}
    if kind == "steps":
        return {"steps": [{"text": "", "done": False, "by": "", "at": ""}]}
    if kind == "run":
        d = {k: "" for k, _ in RUN_FIELDS}
        d.update(params="", notes="")
        return d
    if kind == "reaction":
        return {"rows": [_reaction_row("reactant"), _reaction_row("reagent"),
                         _reaction_row("product")],
                "actual": "", "notes": ""}
    if kind == "safety":
        return {"hazards": "", "ghs": [], "ppe": [], "risk": "low",
                "controls": "", "waste": ""}
    raise KeyError(kind)


def _reaction_row(role):
    row = {k: "" for k, _ in REACTION_COLS}
    row["role"] = role
    return row


def _s(v):
    return "" if v is None else str(v)


def normalise(kind: str, data) -> dict:
    """*data* coerced into *kind*'s shape; missing parts take defaults."""
    d = data if isinstance(data, dict) else {}
    base = default_data(kind)
    if kind == "measurements":
        cols = [{"name": _s(c.get("name")), "unit": _s(c.get("unit"))}
                for c in d.get("columns") or [] if isinstance(c, dict)]
        if not cols:
            return base
        rows = []
        for r in d.get("rows") or []:
            r = [_s(v) for v in (r if isinstance(r, list) else [])]
            rows.append((r + [""] * len(cols))[:len(cols)])
        return {"columns": cols, "rows": rows}
    if kind == "steps":
        steps = [{"text": _s(s.get("text")), "done": bool(s.get("done")),
                  "by": _s(s.get("by")), "at": _s(s.get("at"))}
                 for s in d.get("steps") or [] if isinstance(s, dict)]
        return {"steps": steps or base["steps"]}
    if kind == "run":
        return {k: _s(d.get(k)) for k in base}
    if kind == "reaction":
        rows = []
        for r in d.get("rows") or []:
            if isinstance(r, dict):
                row = {k: _s(r.get(k)) for k, _ in REACTION_COLS}
                if row["role"] not in ROLES:
                    row["role"] = "reactant"
                rows.append(row)
        return {"rows": rows or base["rows"], "actual": _s(d.get("actual")),
                "notes": _s(d.get("notes"))}
    if kind == "safety":
        codes = {c for c, _ in GHS}
        return {"hazards": _s(d.get("hazards")),
                "ghs": [c for c in d.get("ghs") or [] if c in codes],
                "ppe": [p for p in d.get("ppe") or [] if p in PPE],
                "risk": d.get("risk") if d.get("risk") in RISKS else "low",
                "controls": _s(d.get("controls")), "waste": _s(d.get("waste"))}
    raise KeyError(kind)


def column_label(col: dict) -> str:
    return f"{col['name']} ({col['unit']})" if col.get("unit") else col["name"]


# -- markdown -------------------------------------------------------------
def _md_cell(v):
    return _s(v).replace("|", "\\|").replace("\n", " ")


def _md_table(headers, rows):
    lines = ["| " + " | ".join(_md_cell(h) for h in headers) + " |",
             "|" + "---|" * len(headers)]
    lines += ["| " + " | ".join(_md_cell(v) for v in r) + " |" for r in rows]
    return "\n".join(lines)


def to_markdown(kind: str, data: dict, title: str = "") -> str:
    """A readable Markdown rendering of the record."""
    data = normalise(kind, data)
    head = f"**{title or KIND_LABELS.get(kind, kind)}**"
    if kind == "measurements":
        cols = data["columns"]
        rows = [r for r in data["rows"] if any(v.strip() for v in r)]
        body = _md_table([column_label(c) for c in cols], rows)
        summary = [stats_text([r[i] for r in rows]) for i in range(len(cols))]
        if any(summary):
            body += "\n| " + " | ".join(
                _md_cell(s or "") for s in summary) + " |"
        return f"{head}\n\n{body}"
    if kind == "steps":
        lines = []
        for i, s in enumerate(data["steps"], 1):
            mark = "x" if s["done"] else " "
            stamp = f" — {s['by']}, {s['at']}" if s["done"] and s["by"] else ""
            lines.append(f"{i}. [{mark}] {s['text']}{stamp}")
        return head + "\n\n" + "\n".join(lines)
    if kind == "run":
        lines = [f"- **{label}:** {data[k]}" for k, label in RUN_FIELDS
                 if data[k]]
        for k in ("params", "notes"):
            if data[k].strip():
                lines.append(f"- **{k.capitalize()}:**\n\n  "
                             + data[k].strip().replace("\n", "\n  "))
        return head + "\n\n" + "\n".join(lines)
    if kind == "reaction":
        calc = reaction_compute(data)
        rows = []
        for r, c in zip(data["rows"], calc["rows"]):
            rows.append([r["name"], r["role"], r["formula"], fmt(c["mw"]),
                         r["mass"], r["volume"], fmt(c["mmol"]),
                         fmt(c["equiv"], 3)])
        body = _md_table(["Name", "Role", "Formula", "MW", "Mass (mg)",
                          "Vol (mL)", "mmol", "equiv"], rows)
        if calc["theoretical_mg"] is not None:
            body += f"\n\nTheoretical yield: {fmt(calc['theoretical_mg'])} mg"
            if calc["yield_pct"] is not None:
                body += (f"; actual {data['actual']} mg "
                         f"({calc['yield_pct']:.1f} %)")
        if data["notes"].strip():
            body += "\n\n" + data["notes"].strip()
        return f"{head}\n\n{body}"
    if kind == "safety":
        names = dict(GHS)
        lines = [f"- **Risk:** {data['risk']}"]
        if data["ghs"]:
            lines.append("- **GHS:** " + ", ".join(
                f"{c} {names[c]}" for c in data["ghs"]))
        if data["ppe"]:
            lines.append("- **PPE:** " + ", ".join(data["ppe"]))
        for k in ("hazards", "controls", "waste"):
            if data[k].strip():
                lines.append(f"- **{k.capitalize()}:** {data[k].strip()}")
        return head + "\n\n" + "\n".join(lines)
    return head
