"""Importers for sibling Kherve formats.

Converts KherveSheet workbooks (.ksheet, HDF5) and kherveDOC
documents (.kdocz zip / .kdoc.json) into lists of KherveBook cell
dicts ({"type", "source"}), so they can be dropped into a notebook.

Copyright (C) 2026 Gwilherm Kerherve

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.
"""

import json
import zipfile
from pathlib import Path

from .sheetcell import DEFAULT_COLS, DEFAULT_ROWS, col_letter


def _text(value) -> str:
    if isinstance(value, bytes):
        return value.decode("utf-8", "replace")
    return str(value)


# -- KherveSheet (.ksheet — HDF5) ---------------------------------------

def ksheet_to_cells(path: str) -> list:
    """One sheet cell per workbook sheet, trimmed to its used range.

    Values and formula texts import as-is. KherveSheet's Excel-style
    formulas (=SUM(A:A)) and =PY cells keep their raw text — they
    show in the grid but only Python-style formulas recompute here.
    """
    import h5py     # optional dependency; ImportError -> not recognised

    cells = []
    with h5py.File(path, "r") as f:
        if _text(f.attrs.get("format", "")) != "ksheet":
            raise ValueError("not a .ksheet file")
        count = int(f.attrs.get("sheet_count", 0))
        for si in range(count):
            sg = f[f"sheet_{si}"]
            rows = int(sg.attrs.get("rows", 0))
            cols = int(sg.attrs.get("cols", 0))
            flat = sg["cells"][:]
            data, max_r, max_c = {}, -1, -1
            for idx, value in enumerate(flat[:rows * cols]):
                value = _text(value)
                if not value:
                    continue
                r, c = divmod(idx, cols)
                data[f"{col_letter(c)}{r + 1}"] = value
                max_r, max_c = max(max_r, r), max(max_c, c)
            name = _text(sg.attrs.get("name", f"sheet {si + 1}"))
            if count > 1:
                cells.append({"type": "markdown",
                              "source": f"**{name}**"})
            cells.append({"type": "sheet", "source": json.dumps({
                "rows": max(max_r + 1, DEFAULT_ROWS),
                "cols": max(max_c + 1, DEFAULT_COLS),
                "data": data})})
    return cells


# -- kherveDOC (.kdocz zip / .kdoc.json) --------------------------------

def is_kdoc(path: str) -> bool:
    name = Path(path).name.lower()
    return (name.endswith((".kdocz", ".ktexz"))
            or name.endswith((".kdoc.json", ".ktex.json")))


_MARKS = {
    "bold": "**{}**", "italic": "*{}*", "code": "`{}`",
    "strikethrough": "~~{}~~", "underline": "<u>{}</u>",
    "subscript": "<sub>{}</sub>", "superscript": "<sup>{}</sup>",
}


def kdoc_to_cells(path: str) -> list:
    """Markdown cells for prose, latex cells for display math."""
    p = Path(path)
    if p.suffix.lower() in (".kdocz", ".ktexz"):
        with zipfile.ZipFile(p) as z:
            doc = json.loads(z.read("document.json").decode("utf-8"))
    else:
        doc = json.loads(p.read_text(encoding="utf-8"))

    cells, md = [], []

    def flush():
        if md:
            cells.append({"type": "markdown",
                          "source": "\n\n".join(md)})
            md.clear()

    def inline(nodes) -> str:
        out = ""
        for n in nodes or []:
            kind = n.get("type")
            if kind == "Text":
                s = n.get("text", "")
                for mark in n.get("marks") or []:
                    s = _MARKS.get(mark, "{}").format(s)
                out += s
            elif kind == "MathInline":
                out += f"${n.get('latex', '')}$"
        return out

    def item_text(item) -> str:
        if isinstance(item, dict):
            return inline(item.get("children") or [item])
        if isinstance(item, list):
            return inline(item)
        return str(item)

    title = (doc.get("meta") or {}).get("title")

    def walk(nodes):
        for n in nodes or []:
            kind = n.get("type")
            if kind == "Section":
                # Sections sit one level under the document title.
                level = max(1, min(6, int(n.get("level", 1))
                                   + (1 if title else 0)))
                md.append("#" * level + " " + inline(n.get("children")))
            elif kind == "Paragraph":
                md.append(inline(n.get("children")))
            elif kind in ("MathBlock", "RawLatex"):
                flush()
                cells.append({"type": "latex",
                              "source": n.get("latex", "")})
            elif kind == "List":
                md.append("\n".join(
                    "- " + item_text(i) for i in n.get("items") or []))
            elif kind == "Table":
                rows = [[str(c) for c in row]
                        for row in n.get("rows") or []]
                if rows:
                    width = max(len(r) for r in rows)
                    rows = [r + [""] * (width - len(r)) for r in rows]
                    lines = ["| " + " | ".join(rows[0]) + " |",
                             "|" + "---|" * width]
                    lines += ["| " + " | ".join(r) + " |"
                              for r in rows[1:]]
                    md.append("\n".join(lines))
            elif kind == "Figure":
                src = n.get("path") or ""
                fp = Path(src)
                if fp.is_absolute() and fp.exists():
                    src = fp.as_uri()
                md.append(f"![{n.get('caption') or ''}]({src})")
            elif n.get("children"):
                walk(n["children"])

    if title:
        md.append("# " + title)
    walk(doc.get("children"))
    flush()
    return cells
