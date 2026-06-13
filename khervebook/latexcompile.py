"""Full LaTeX compilation for LaTeX cells.

A latex cell holding a document is compiled with the *tectonic* engine
(a self-contained, modern LaTeX distribution) to PDF and the pages are
rasterised with PyMuPDF — the full power of LaTeX, not a text
approximation. Anything LaTeX can typeset works: amsmath, tikz,
tables, figures, custom classes, bibliographies.

Requires the ``tectonic`` binary on PATH (or in ~/bin) and PyMuPDF
(``pip install pymupdf``). When either is missing the cell falls back
to the lightweight text renderer in latextext.py.

Copyright (C) 2026 Gwilherm Kerherve

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.
"""

import importlib.util
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

#: Minimal preamble used to wrap a fragment that has no \documentclass.
_PREAMBLE = r"""\documentclass[12pt]{article}
\usepackage{amsmath,amssymb,amsfonts,mathtools}
\usepackage{graphicx,xcolor,booktabs,array}
\usepackage[normalem]{ulem}
\usepackage[margin=2cm]{geometry}
\pagestyle{empty}
\begin{document}
%s
\end{document}
"""


def find_tectonic():
    """Locate the tectonic binary (PATH, then common install dirs)."""
    found = shutil.which("tectonic")
    if found:
        return found
    for c in (Path.home() / "bin" / "tectonic.exe",
              Path.home() / "bin" / "tectonic",
              Path.home() / ".cargo" / "bin" / "tectonic.exe",
              Path.home() / "scoop" / "shims" / "tectonic.exe"):
        if c.exists():
            return str(c)
    return None


def _have_pymupdf() -> bool:
    return (importlib.util.find_spec("fitz") is not None
            or importlib.util.find_spec("pymupdf") is not None)


def available() -> bool:
    """True if a real LaTeX compile + render is possible on this machine."""
    return find_tectonic() is not None and _have_pymupdf()


#: Commands that belong in the preamble (before \begin{document}).
_PREAMBLE_CMDS = (
    "\\documentclass", "\\usepackage", "\\RequirePackage",
    "\\usetikzlibrary", "\\geometry", "\\pagestyle", "\\pagenumbering",
    "\\setlength", "\\newcommand", "\\renewcommand", "\\providecommand",
    "\\def", "\\definecolor", "\\graphicspath", "\\title", "\\author",
    "\\date", "\\hypersetup", "\\bibliographystyle", "\\input",
)


def wrap_document(source: str) -> str:
    """Make *source* a compilable document.

    - already has \\begin{document}: used as-is.
    - has \\documentclass but no document env (a preamble + body, as
      KherveTeX often pastes): insert \\begin/\\end{document} after the
      preamble.
    - a bare fragment: wrap in a minimal article preamble.
    """
    if "\\begin{document}" in source:
        return source
    if "\\documentclass" in source:
        lines = source.split("\n")
        preamble_end = 0
        for i, line in enumerate(lines):
            s = line.strip()
            if not s or s.startswith("%") or s.startswith(_PREAMBLE_CMDS):
                preamble_end = i + 1
            else:
                break
        head = "\n".join(lines[:preamble_end])
        body = "\n".join(lines[preamble_end:])
        return f"{head}\n\\begin{{document}}\n{body}\n\\end{{document}}\n"
    return _PREAMBLE % source


def _pymupdf():
    try:
        import fitz
        return fitz
    except Exception:
        import pymupdf
        return pymupdf


def compile_to_pngs(source: str, dpi: int = 150, timeout: int = 180):
    """Compile *source* with tectonic; return (list_of_png_bytes, error).

    *error* is None on success, otherwise tectonic's log (or a short
    reason). A document that fails to produce a PDF returns ([], log).
    """
    tect = find_tectonic()
    if tect is None:
        return [], "tectonic is not installed"
    if not _have_pymupdf():
        return [], "PyMuPDF (pymupdf) is not installed"
    fitz = _pymupdf()

    workdir = Path(tempfile.mkdtemp(prefix="khervebook-tex-"))
    try:
        tex_path = workdir / "document.tex"
        tex_path.write_text(wrap_document(source), encoding="utf-8")
        kw = dict(capture_output=True, text=True, encoding="utf-8",
                  errors="replace", timeout=timeout)
        if sys.platform == "win32":
            kw["creationflags"] = subprocess.CREATE_NO_WINDOW
        try:
            proc = subprocess.run(
                [tect, "-Z", "continue-on-errors", "--outdir",
                 str(workdir), str(tex_path)], **kw)
        except subprocess.TimeoutExpired:
            return [], f"tectonic timed out after {timeout}s"

        pdf_path = workdir / "document.pdf"
        if not pdf_path.exists():
            return [], (proc.stdout or "") + (proc.stderr or "")

        pngs = []
        zoom = dpi / 72.0
        with fitz.open(pdf_path) as pdf:
            matrix = fitz.Matrix(zoom, zoom)
            for page in pdf:
                pix = page.get_pixmap(matrix=matrix, alpha=False)
                pngs.append(pix.tobytes("png"))
        return pngs, None
    finally:
        shutil.rmtree(workdir, ignore_errors=True)
