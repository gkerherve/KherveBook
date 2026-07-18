"""Jupyter / Google Colab notebook (.ipynb) import and export.

Colab notebooks are ordinary .ipynb files, so one conversion handles
both. KherveBook code and markdown cells map directly to Jupyter
code/markdown. latex and sheet cells have no Jupyter equivalent, so
they export as markdown (a $$…$$ block, a ```latex fence, or a table)
but carry their original type and source in the cell's metadata under
"khervebook" — a KherveBook → .ipynb → KherveBook round-trip is
therefore lossless, while the file still opens cleanly in Jupyter and
Colab.

Copyright (C) 2026 Gwilherm Kerherve

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.
"""

import json
import re

from .latextext import is_document

_REF = re.compile(r"^([A-Z]{1,2})(\d{1,3})$")
#: KherveBook per-cell properties carried through .ipynb metadata.
_PROPS = ("title", "collapsed", "column", "width", "height")


def _split(text: str) -> list:
    """Source string -> Jupyter's list-of-lines (newlines kept)."""
    return text.splitlines(keepends=True) or [""]


def _join(source) -> str:
    """Jupyter source (list or string) -> a single string."""
    return "".join(source) if isinstance(source, list) else (source or "")


def _sheet_markdown(src: str) -> str:
    """Render a sheet cell's active grid as a markdown table (display)."""
    try:
        from .sheetcell import col_letter, letter_col
        doc = json.loads(src)
        sheets = doc.get("sheets") or [doc]
        active = doc.get("active")
        sheet = next((s for s in sheets if s.get("name") == active),
                     sheets[0])
        rows, cols = int(sheet.get("rows", 0)), int(sheet.get("cols", 0))
        grid = [["" for _ in range(cols)] for _ in range(rows)]
        for ref, raw in (sheet.get("data") or {}).items():
            m = _REF.match(ref)
            if not m:
                continue
            r, c = int(m.group(2)) - 1, letter_col(m.group(1))
            if 0 <= r < rows and 0 <= c < cols:
                grid[r][c] = str(raw)
        header = "| " + " | ".join(col_letter(c) for c in range(cols)) + " |"
        sep = "|" + "---|" * max(cols, 1)
        body = "\n".join("| " + " | ".join(row) + " |" for row in grid)
        return f"{header}\n{sep}\n{body}"
    except Exception:
        return "```\n" + src + "\n```"


# -- export ----------------------------------------------------------------

def _cell_to_ipynb(item: dict) -> dict:
    t = item.get("type", "code")
    src = item.get("source", "")
    meta = {}
    props = {k: item[k] for k in _PROPS if item.get(k)}
    if props:
        meta["khervebook"] = props
    if t == "code":
        return {"cell_type": "code", "metadata": meta,
                "execution_count": None, "outputs": [],
                "source": _split(src)}
    if t == "markdown":
        return {"cell_type": "markdown", "metadata": meta,
                "source": _split(src)}
    # Other cell types (latex/sheet/note/svg/js/file) have no Jupyter
    # equivalent: render a readable markdown display and keep the original
    # type + source in metadata so a round-trip is lossless.
    kb = meta.setdefault("khervebook", {})
    kb["type"] = t
    kb["source"] = src
    body = _display_body(t, src)
    return {"cell_type": "markdown", "metadata": meta, "source": _split(body)}


def _note_markdown(src: str) -> str:
    """A Note cell's HTML as a markdown display block (Jupyter renders it)."""
    try:
        doc = json.loads(src)
        if isinstance(doc, dict) and "html" in doc:
            return doc["html"]
    except (ValueError, TypeError):
        pass
    return src


def _file_markdown(src: str) -> str:
    try:
        doc = json.loads(src)
        name = doc.get("name") if isinstance(doc, dict) else None
    except (ValueError, TypeError):
        name = None
    return f"📎 **Attached file:** `{name}`" if name else "📎 Attached file"


def _display_body(t: str, src: str) -> str:
    if t == "latex":
        return ("```latex\n" + src + "\n```" if is_document(src)
                else "$$\n" + src.strip() + "\n$$")
    if t == "sheet":
        return _sheet_markdown(src)
    if t == "note":
        return _note_markdown(src)
    if t == "file":
        return _file_markdown(src)
    if t == "js":
        return "```javascript\n" + src + "\n```"
    if t == "svg":
        return src if src.lstrip().startswith("<svg") else "```\n" + src + "\n```"
    return "```\n" + src + "\n```"


def to_ipynb(items: list) -> str:
    """Serialise KherveBook cell dicts to a Jupyter/Colab .ipynb string."""
    doc = {
        "cells": [_cell_to_ipynb(it) for it in items],
        "metadata": {
            "kernelspec": {"display_name": "Python 3",
                           "language": "python", "name": "python3"},
            "language_info": {"name": "python"},
        },
        "nbformat": 4,
        "nbformat_minor": 5,
    }
    return json.dumps(doc, indent=1)


# -- import ----------------------------------------------------------------

def from_ipynb(text: str) -> list:
    """Parse a .ipynb (Jupyter or Colab) into KherveBook cell dicts."""
    nb = json.loads(text)
    items = []
    for cell in nb.get("cells", []):
        meta = cell.get("metadata") or {}
        kb = meta.get("khervebook") or {}
        if kb.get("type") in ("latex", "sheet", "note", "svg", "js",
                              "file") and "source" in kb:
            item = {"type": kb["type"], "source": kb["source"]}
        else:
            ct = cell.get("cell_type", "code")
            item = {"type": "code" if ct == "code" else "markdown",
                    "source": _join(cell.get("source", ""))}
        for k in _PROPS:
            if k in kb:
                item[k] = kb[k]
        items.append(item)
    return items
