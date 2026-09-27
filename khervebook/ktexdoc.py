"""KherveTeX documents without KherveTeX: the Qt-free half of the
KherveTeX document cell.

KherveTeX is a PySide6 app and PySide6 cannot share a process with
PyQt5, so nothing here imports ``khervedoc``. What the cell needs is
re-done from the file format instead:

* `new_ktexz` writes a minimal but valid ``.ktexz`` (a zip holding
  ``manifest.json`` + ``document.json``, KherveTeX's ``kdocz`` layout).
* `title_of` reads the document title (``meta.title``, or ``\\title{}``).
* `pdf_source` decides where the pages come from: KherveTeX caches
  ``<stem>.pdf`` beside the document after each compile and writes
  ``<stem>.tex`` on each save; a stale or missing PDF is recompiled from
  the ``.tex`` — or, for a document KherveTeX has never saved, from a
  LaTeX translation of the model (`importers.ktex_to_latex`).
* `compile_tex` / `render_pages` do the tectonic + PyMuPDF work.
* `find_khervetex` returns the command that launches KherveTeX.

Copyright (C) 2026 Gwilherm Kerherve

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.
"""

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

from . import siblings

KTEX_EXTS = (".ktexz", ".kdocz")

#: A PDF or .tex counts as current when it is no more than this older than
#: the document: KherveTeX writes the .ktexz and the .tex in one save, and
#: OneDrive/FAT round mtimes, so a strict ">=" would recompile needlessly.
_SLACK = 2.0

#: KherveTeX's default document settings (khervedoc.model.DocMeta), so a
#: new document opens in KherveTeX exactly as one it created itself would.
_DEFAULT_META = {
    "title": "Untitled", "author": "", "documentclass": "article",
    "class_options": "",
    "packages": ["amsmath", "amssymb", "graphicx", "multicol", "float"],
    "page_size": "A4", "margin_top_cm": 2.5, "margin_bottom_cm": 2.5,
    "margin_left_cm": 2.5, "margin_right_cm": 2.5, "body_font_pt": 12,
    "body_font_family": "default", "visual_font_family": "Georgia",
    "line_spacing": 1.0, "paragraph_indent": True, "column_count": 1,
    "frontmatter_extras": "", "preamble_extras": "",
}


def _text(s):
    return {"text": s, "marks": [], "type": "Text"}


def new_ktexz(path, title="Untitled document", author=""):
    """Write a minimal KherveTeX document to *path* and return the path."""
    meta = dict(_DEFAULT_META, title=title, author=author)
    doc = {"children": [
        {"level": 1, "children": [_text("Introduction")], "numbered": True,
         "label": None, "type": "Section"},
        {"children": [_text("Start writing here. Open this document in "
                            "KherveTeX to edit it; the notebook shows "
                            "the typeset pages.")],
         "alignment": "justify", "type": "Paragraph"},
    ], "meta": meta, "type": "Document"}
    path = Path(path)
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("manifest.json", json.dumps(
            {"format": "kdocz", "schema_version": 1, "app": "KherveTeX"},
            indent=2))
        zf.writestr("document.json", json.dumps(doc, indent=2))
    return path


def is_ktexz(path) -> bool:
    return str(path).lower().endswith(KTEX_EXTS)


def read_document(path) -> dict:
    """The ``document.json`` of a ``.ktexz``; {} when unreadable."""
    try:
        with zipfile.ZipFile(path) as zf:
            return json.loads(zf.read("document.json").decode("utf-8"))
    except Exception:
        return {}


_TITLE_RE = re.compile(r"\\title\s*(?:\[[^\]]*\])?\s*\{((?:[^{}]|\{[^{}]*\})*)\}")


def _plain(tex: str) -> str:
    """LaTeX markup in a title -> readable text."""
    tex = re.sub(r"\\[a-zA-Z]+\*?\s*", "", tex)
    tex = tex.replace("{", "").replace("}", "").replace("~", " ")
    return re.sub(r"\s+", " ", tex).strip()


def title_of(path) -> str:
    """The document's title, or its file name when it has none."""
    p = Path(path)
    title = ""
    if is_ktexz(p):
        doc = read_document(p)
        # A Title block is what the page shows; meta.title is only the
        # fallback KherveTeX typesets when the document has none.
        for block in doc.get("children") or []:
            if isinstance(block, dict) and block.get("type") == "Title":
                title = "".join(n.get("text", "") for n in
                                block.get("children") or []
                                if isinstance(n, dict)).strip()
                break
        if not title:
            title = str((doc.get("meta") or {}).get("title") or "")
        if title == "Untitled":
            title = ""
    elif p.suffix.lower() == ".tex":
        try:
            m = _TITLE_RE.search(p.read_text(encoding="utf-8",
                                             errors="replace"))
        except OSError:
            m = None
        if m:
            title = _plain(m.group(1))
    return title or p.stem


def sibling(path, ext: str) -> Path:
    p = Path(path)
    return p.with_name(p.stem + ext)


def _mtime(p: Path) -> float:
    try:
        return p.stat().st_mtime
    except OSError:
        return -1.0


def pdf_source(path):
    """Where this document's pages come from: ``("pdf", Path)`` for a
    current cached PDF, ``("tex", Path)`` for a .tex to compile, or
    ``("model", Path)`` when only the .ktexz itself is there."""
    p = Path(path)
    doc_time = _mtime(p)
    pdf = sibling(p, ".pdf")
    if pdf.exists() and _mtime(pdf) >= doc_time - _SLACK:
        return "pdf", pdf
    if p.suffix.lower() == ".tex":
        return "tex", p
    tex = sibling(p, ".tex")
    if tex.exists() and _mtime(tex) >= doc_time - _SLACK:
        return "tex", tex
    return "model", p


def compile_tex(tex_path, out_pdf=None, timeout=240):
    """Compile *tex_path* with tectonic; return ``(pdf_bytes, log)``.

    Runs in the .tex's own folder so its relative figures resolve. The
    result is also written to *out_pdf* when given — the same cache
    KherveTeX keeps, so the next look at the document is instant.
    """
    from .latexcompile import find_tectonic
    tect = find_tectonic()
    if tect is None:
        return None, "tectonic is not installed"
    tex_path = Path(tex_path)
    work = Path(tempfile.mkdtemp(prefix="khervebook-ktex-"))
    try:
        kw = dict(capture_output=True, text=True, encoding="utf-8",
                  errors="replace", timeout=timeout, cwd=str(tex_path.parent))
        if sys.platform == "win32":
            kw["creationflags"] = subprocess.CREATE_NO_WINDOW
        try:
            proc = subprocess.run([tect, "-Z", "continue-on-errors",
                                   "--outdir", str(work), str(tex_path)], **kw)
        except subprocess.TimeoutExpired:
            return None, f"tectonic timed out after {timeout}s"
        pdf = work / (tex_path.stem + ".pdf")
        if not pdf.exists():
            return None, (proc.stdout or "") + (proc.stderr or "")
        data = pdf.read_bytes()
        if out_pdf is not None:
            try:
                Path(out_pdf).write_bytes(data)
            except OSError:
                pass
        return data, ""
    finally:
        shutil.rmtree(work, ignore_errors=True)


def document_pdf(path, timeout=240):
    """The PDF bytes for a .ktexz / .tex, compiling only when needed.
    Returns ``(pdf_bytes or None, log)``."""
    kind, src = pdf_source(path)
    if kind == "pdf":
        try:
            return src.read_bytes(), ""
        except OSError as exc:
            return None, str(exc)
    cache = sibling(path, ".pdf")
    if kind == "tex":
        return compile_tex(src, cache, timeout)
    from .importers import ktex_to_latex
    try:
        tex = ktex_to_latex(str(src))
    except Exception as exc:
        return None, f"Could not read {Path(src).name}: {exc}"
    # Written beside the document, not in a temp folder, so figures the
    # document references relatively still resolve.
    tmp = Path(src).with_name(f".{Path(src).stem}.khervebook.tex")
    try:
        tmp.write_text(tex, encoding="utf-8")
        return compile_tex(tmp, cache, timeout)
    finally:
        try:
            tmp.unlink()
        except OSError:
            pass


def render_pages(pdf_bytes, dpi=110):
    """Every page of a PDF as PNG bytes (whole pages, margins kept — this
    is a document, not an equation)."""
    from .latexcompile import _pymupdf
    fitz = _pymupdf()
    zoom = dpi / 72.0
    out = []
    with fitz.open(stream=pdf_bytes, filetype="pdf") as pdf:
        for page in pdf:
            pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=False)
            out.append(pix.tobytes("png"))
    return out


# -- locating KherveTeX ----------------------------------------------------

def _mac_bundle_exe(app: Path):
    macos = app / "Contents" / "MacOS"
    preferred = macos / app.stem
    if preferred.exists():
        return preferred
    for f in sorted(macos.glob("*")) if macos.is_dir() else []:
        if f.is_file() and os.access(f, os.X_OK):
            return f
    return None


def command_for(path):
    """Launch command (without the document) for a user-chosen KherveTeX:
    a .app bundle, an executable, or the ``kherveDOC.py`` launcher."""
    p = Path(path)
    if p.suffix.lower() == ".app" and p.is_dir():
        exe = _mac_bundle_exe(p)
        return [str(exe)] if exe else None
    if p.is_file() and p.suffix.lower() == ".py":
        python = (siblings.venv_python(p.parent)
                  or siblings.python_with("PySide6"))
        return [python, str(p)] if python else None
    if p.is_file():
        return [str(p)]
    return None


def install_candidates():
    """Installed KherveTeX locations for this platform, in search order."""
    out = [Path("/Applications/KherveTeX.app"),
           Path.home() / "Applications" / "KherveTeX.app"]
    for var in ("ProgramFiles", "ProgramFiles(x86)"):
        if os.environ.get(var):
            out.append(Path(os.environ[var]) / "KherveTeX" / "KherveTeX.exe")
    if os.environ.get("LOCALAPPDATA"):
        out.append(Path(os.environ["LOCALAPPDATA"]) / "Programs"
                   / "KherveTeX" / "KherveTeX.exe")
    return out


def find_khervetex(override=""):
    """The command that launches KherveTeX, or None.

    *override* is the user's own choice ("Locate KherveTeX…"); then an
    installed app; then a source checkout's ``kherveDOC.py`` run with its
    own virtualenv (or any Python that has PySide6).
    """
    if override:
        cmd = command_for(override)
        if cmd:
            return cmd
    for c in install_candidates():
        if c.exists():
            cmd = command_for(c)
            if cmd:
                return cmd
    repo = siblings.checkout("KherveTeX", "khervedoc", "KHERVETEX_PATH")
    if repo is not None and (repo / "kherveDOC.py").exists():
        return command_for(repo / "kherveDOC.py")
    return None


def launch_detached(cmd, path):
    """Start *cmd* + *path* so it outlives KherveBook and never blocks it."""
    kw = {"cwd": str(Path(path).parent)}
    if sys.platform == "win32":
        kw["creationflags"] = (subprocess.DETACHED_PROCESS
                               | subprocess.CREATE_NEW_PROCESS_GROUP)
    else:
        kw["start_new_session"] = True
    return subprocess.Popen(list(cmd) + [str(path)],
                            stdin=subprocess.DEVNULL,
                            stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL, **kw)
