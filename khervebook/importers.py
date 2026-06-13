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

import base64
import io
import json
import zipfile
from pathlib import Path

from .sheetcell import DEFAULT_COLS, DEFAULT_ROWS, col_letter


def _text(value) -> str:
    if isinstance(value, bytes):
        return value.decode("utf-8", "replace")
    return str(value)


# -- KherveSheet (.ksheet — HDF5) ---------------------------------------

def _render_ksheet_chart(chart) -> bytes:
    """Reconstruct a KherveSheet chart (series + styling) to PNG bytes.

    Charts are stored as vector definitions, not images: each chart_N
    group holds its axes attrs and series_K subgroups with x/y datasets
    and a JSON style. Replot them with matplotlib so KherveBook can show
    the plot next to the sheets.
    """
    import matplotlib
    matplotlib.use("Agg", force=False)
    import matplotlib.pyplot as plt

    a = chart.attrs
    w = int(a.get("width", 450)) / 100.0
    h = int(a.get("height", 340)) / 100.0
    fig, ax = plt.subplots(figsize=(max(3.0, w), max(2.2, h)))
    has_label = False
    for k in range(int(a.get("series_count", 0))):
        s = chart.get(f"series_{k}")
        if s is None or "x" not in s or "y" not in s:
            continue
        x, y = s["x"][:], s["y"][:]
        try:
            props = json.loads(_text(s.attrs.get("props", "{}")))
        except Exception:
            props = {}
        label = _text(s.attrs.get("label", "")) or None
        has_label = has_label or bool(label)
        ptype = _text(s.attrs.get("plot_type", "Line"))
        color = props.get("color")
        if "Bar" in ptype:
            ax.bar(x, y, color=color, label=label)
        elif "Scatter" in ptype or ("Symbol" in ptype and "Line" not in ptype):
            ax.scatter(x, y, s=float(props.get("markersize", 4)) ** 2,
                       color=props.get("markerfacecolor", color),
                       marker=props.get("marker", "o"), label=label)
        else:
            ax.plot(x, y, linestyle=props.get("linestyle", "-"),
                    linewidth=props.get("linewidth", 1.5), color=color,
                    marker=props.get("marker", "") if "Symbol" in ptype
                    else "", markersize=float(props.get("markersize", 4)),
                    markerfacecolor=props.get("markerfacecolor", color),
                    markeredgecolor=props.get("markeredgecolor", color),
                    label=label)
    if _text(a.get("title", "")):
        ax.set_title(_text(a.get("title", "")))
    ax.set_xlabel(_text(a.get("xlabel", "")))
    ax.set_ylabel(_text(a.get("ylabel", "")))
    for axis, scale in (("x", _text(a.get("xscale", "linear"))),
                        ("y", _text(a.get("yscale", "linear")))):
        try:
            (ax.set_xscale if axis == "x" else ax.set_yscale)(scale)
        except Exception:
            pass
    if a.get("grid"):
        ax.grid(True, alpha=0.3)
    if has_label and a.get("legend_visible", True):
        ax.legend(fontsize=8)
    fig.tight_layout()
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=110, bbox_inches="tight")
    plt.close(fig)
    return buf.getvalue()


def ksheet_to_cells(path: str) -> list:
    """The whole workbook as ONE multi-sheet cell: every sheet (trimmed
    to its used range) plus every chart, switchable from the cell's
    View menu.

    Values and formula texts import as-is. KherveSheet's Excel-style
    formulas (=SUM(A:A)) and =PY cells keep their raw text — they
    show in the grid but only Python-style formulas recompute here.
    """
    import h5py     # optional dependency; ImportError -> not recognised

    sheets, plots = [], []
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
            name = _text(sg.attrs.get("name", f"Sheet {si + 1}"))
            sheets.append({"name": name,
                           "rows": max(max_r + 1, DEFAULT_ROWS),
                           "cols": max(max_c + 1, DEFAULT_COLS),
                           "data": data})
            charts = sorted((k for k in sg if k.startswith("chart_")),
                            key=lambda k: int(k.split("_")[1]))
            for ck in charts:
                try:
                    png = _render_ksheet_chart(sg[ck])
                except Exception:
                    continue
                title = _text(sg[ck].attrs.get("title", "")) or "Plot"
                plots.append({"title": title,
                              "png": base64.b64encode(png).decode("ascii")})
    if not sheets:
        return []
    return [{"type": "sheet", "source": json.dumps(
        {"sheets": sheets, "active": sheets[0]["name"], "plots": plots})}]


# -- KherveTeX (.ktex / .ktexz) -> a LaTeX cell -------------------------

def is_ktex(path: str) -> bool:
    name = Path(path).name.lower()
    return name.endswith((".ktex", ".ktexz", ".ktex.json"))


#: structured-model mark -> (LaTeX prefix, suffix).
_KTEX_MARKS = {
    "bold": ("\\textbf{", "}"), "italic": ("\\textit{", "}"),
    "underline": ("\\underline{", "}"), "code": ("\\texttt{", "}"),
    "strikethrough": ("\\sout{", "}"), "smallcaps": ("\\textsc{", "}"),
    "subscript": ("\\textsubscript{", "}"),
    "superscript": ("\\textsuperscript{", "}"),
    "emph": ("\\emph{", "}"),
}
_SECTION_CMD = {1: "section", 2: "subsection", 3: "subsubsection"}


_LATEX_ESCAPE = {
    "\\": "\\textbackslash{}", "&": "\\&", "%": "\\%", "#": "\\#",
    "_": "\\_", "$": "\\$", "{": "\\{", "}": "\\}",
    "~": "\\textasciitilde{}", "^": "\\textasciicircum{}",
}


def _ktex_escape(text: str) -> str:
    return "".join(_LATEX_ESCAPE.get(ch, ch) for ch in text)


def _ktex_inline(nodes) -> str:
    out = ""
    for n in nodes or []:
        kind = n.get("type")
        if kind == "Text":
            s = _ktex_escape(n.get("text", ""))   # escape, then mark up
            for mark in n.get("marks") or []:
                pre, post = _KTEX_MARKS.get(mark, ("", ""))
                s = pre + s + post
            out += s
        elif kind == "MathInline":
            out += "$" + n.get("latex", "") + "$"  # math stays verbatim
    return out


def _ktex_item(item) -> str:
    if isinstance(item, dict):
        return _ktex_inline(item.get("children") or [item])
    if isinstance(item, list):
        return _ktex_inline(item)
    return str(item)


def _ktex_blocks(nodes, lines):
    for n in nodes or []:
        kind = n.get("type")
        if kind == "Section":
            cmd = _SECTION_CMD.get(int(n.get("level", 1)), "section")
            star = "" if n.get("numbered", True) else "*"
            lines.append(f"\\{cmd}{star}{{{_ktex_inline(n.get('children'))}}}")
            lines.append("")
        elif kind == "Paragraph":
            lines.append(_ktex_inline(n.get("children")))
            lines.append("")
        elif kind in ("MathBlock", "EquationBlock"):
            eq = n.get("latex", "")
            if n.get("numbered"):
                lines.append("\\begin{equation}\n" + eq + "\n\\end{equation}")
            else:
                lines.append("\\[ " + eq + " \\]")
            lines.append("")
        elif kind in ("RawLatex", "Raw"):
            lines.append(n.get("latex", n.get("text", "")))
            lines.append("")
        elif kind == "List":
            env = "enumerate" if n.get("ordered") else "itemize"
            lines.append("\\begin{" + env + "}")
            for item in n.get("items") or []:
                lines.append("  \\item " + _ktex_item(item))
            lines.append("\\end{" + env + "}\n")
        elif kind == "Table":
            rows = [[str(c) for c in row] for row in n.get("rows") or []]
            if rows:
                cols = max(len(r) for r in rows)
                lines.append("\\begin{tabular}{" + "l" * cols + "}")
                lines.append("\\hline")
                for row in rows:
                    row = row + [""] * (cols - len(row))
                    lines.append(" & ".join(row) + " \\\\")
                lines.append("\\hline")
                lines.append("\\end{tabular}\n")
        elif kind == "Figure":
            src = n.get("path") or ""
            lines.append("\\begin{figure}[h]\n\\centering")
            lines.append("\\includegraphics[width=0.7\\textwidth]"
                         "{" + src + "}")
            if n.get("caption"):
                lines.append("\\caption{" + n["caption"] + "}")
            lines.append("\\end{figure}\n")
        elif n.get("children"):
            _ktex_blocks(n["children"], lines)


def ktex_to_latex(path: str) -> str:
    """A KherveTeX document -> clean LaTeX source for a latex cell.

    Uses a minimal preamble (amsmath/amssymb/graphicx/ulem/geometry),
    dropping KherveTeX's extra packages (multicol, float, setspace) and
    the \\Kstroke macro that bloat the original .tex.
    """
    p = Path(path)
    if p.suffix.lower() in (".ktexz", ".kdocz"):
        with zipfile.ZipFile(p) as z:
            doc = json.loads(z.read("document.json").decode("utf-8"))
    else:
        doc = json.loads(p.read_text(encoding="utf-8"))
    meta = doc.get("meta") or {}
    cls = meta.get("documentclass") or "article"
    lines = [
        f"\\documentclass[12pt]{{{cls}}}",
        "\\usepackage{amsmath, amssymb, graphicx}",
        "\\usepackage[normalem]{ulem}",
        "\\usepackage[margin=2.5cm]{geometry}",
    ]
    title, author = meta.get("title"), meta.get("author")
    if title:
        lines.append("\\title{" + title + "}")
    if author:
        lines.append("\\author{" + author + "}")
    lines.append("\\begin{document}")
    if title:
        lines.append("\\maketitle")
    _ktex_blocks(doc.get("children"), lines)
    lines.append("\\end{document}")
    return "\n".join(lines)


def ktex_to_cells(path: str) -> list:
    """A KherveTeX document as a single latex cell (clean LaTeX)."""
    return [{"type": "latex", "source": ktex_to_latex(path)}]


# -- kherveDOC (.kdocz zip / .kdoc.json) --------------------------------

def is_kdoc(path: str) -> bool:
    name = Path(path).name.lower()
    return name.endswith((".kdocz", ".kdoc.json"))


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
