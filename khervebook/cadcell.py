"""KherveCAD part cell — a ``.kcad`` design shown as rendered views.

KherveCAD's document is a tree that compiles 1:1 to an OpenSCAD program,
and it is PyQt5, so its own ``document`` / ``model`` modules are imported
(found by `siblings.import_package`) to rebuild that program — on the UI
thread, since its model is a QObject. OpenSCAD then renders isometric,
front and top stills on the worker thread; the cell pages through them
like a document's pages (it is the KherveTeX cell with KherveCAD's
hooks). The ``.kcad`` is held as a sidecar file, so "Open in KherveCAD"
works on the very file and each save there re-renders the views.

Without KherveCAD or OpenSCAD the cell says what is missing and keeps
the stored design untouched.

Copyright (C) 2026 Gwilherm Kerherve

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.
"""

import json
import subprocess
import tempfile
from pathlib import Path

from . import siblings
from .cells import CELL_CLASSES
from .ktexcell import KTexCell, _settings

#: (label, OpenSCAD gimbal rotation) of each still, in page order
VIEWS = (("Isometric", (55, 0, 25)), ("Front", (90, 0, 0)),
         ("Top", (0, 0, 0)))
_SIZE = "1200,800"


def load_khervecad():
    """KherveCAD's engine / document / model modules, or None."""
    pkg = siblings.import_package("khervecad", "KherveCAD", "KHERVECAD_PATH")
    if pkg is None:
        return None
    try:
        from types import SimpleNamespace
        import importlib
        return SimpleNamespace(**{m: importlib.import_module(f"khervecad.{m}")
                                  for m in ("engine", "document", "model")})
    except Exception:
        return None


def summary(path) -> str:
    """"Name — 3 objects" from the .kcad JSON alone (no KherveCAD needed)."""
    try:
        doc = json.loads(Path(path).read_text(encoding="utf-8"))
        children = (doc.get("tree") or {}).get("children") or []
        n = sum(1 for c in children if isinstance(c, dict)
                and c.get("type") != "variables")
        unit = doc.get("unit", "mm")
    except (OSError, ValueError, AttributeError):
        return Path(path).name
    return f"{Path(path).stem}  ({n} object{'s' if n != 1 else ''}, {unit})"


def render_views(openscad, scad_text, extra_args=()):
    """PNG bytes of each of VIEWS, rendered by OpenSCAD."""
    pngs = []
    with tempfile.TemporaryDirectory(prefix="khervebook_cad_") as tmp:
        scad = Path(tmp) / "part.scad"
        scad.write_text(scad_text, encoding="utf-8")
        for i, (_label, (rx, ry, rz)) in enumerate(VIEWS):
            out = Path(tmp) / f"view{i}.png"
            cmd = [openscad, "-o", str(out), f"--imgsize={_SIZE}",
                   f"--camera=0,0,0,{rx},{ry},{rz},0", "--viewall",
                   "--autocenter", "--colorscheme=Tomorrow",
                   *extra_args, str(scad)]
            run = subprocess.run(cmd, capture_output=True, text=True,
                                 timeout=300)
            if run.returncode != 0 or not out.exists():
                return None, (run.stderr or run.stdout)[-2000:]
            pngs.append(out.read_bytes())
    return pngs, ""


class CadCell(KTexCell):
    """A KherveCAD design."""

    CELL_TYPE = "cad"
    SOURCE_KEY = "kbook_cad"
    APP = "KherveCAD"
    DOC_NOUN = "KherveCAD design"
    ICON = "mdi.cube-outline"
    EXTS_TEXT = ".kcad"
    FILE_FILTER = "KherveCAD designs (*.kcad);;All files (*)"
    LOCATE_FILTER = ("KherveCAD (KherveCAD.app KherveCAD.exe KherveCAD.py "
                     "*.app *.exe *.py);;All files (*)")
    LOCATE_KEY = "apps/khervecad"
    CAN_CREATE = False
    PAGE_WORD = "View"
    HOW = {"render": "rendered by OpenSCAD — " + ", ".join(
        v for v, _ in VIEWS).lower()}

    def accepts(self, path) -> bool:
        return str(path).lower().endswith(".kcad")

    def doc_title(self, path) -> str:
        return summary(path)

    @staticmethod
    def pdf_source(path):
        return "render", Path(path)

    def busy_text(self, path) -> str:
        return "Rendering with OpenSCAD…"

    def pages_job(self, path):
        kc = load_khervecad()
        if kc is None:
            raise RuntimeError(
                "KherveCAD is not available, so the design cannot be drawn "
                "here (it is kept as it is). Install KherveCAD beside "
                "KherveBook, or set KHERVECAD_PATH to its folder.")
        openscad = kc.engine.find_openscad()
        if not openscad:
            raise RuntimeError("OpenSCAD was not found — it comes with "
                               "KherveCAD, or install it from openscad.org.")
        # Built here, on the UI thread: KherveCAD's model is a QObject.
        model = kc.model.DocumentModel()
        kc.document.load_kcad(model, str(path))
        scad = model.to_scad()
        try:
            extra = list(kc.engine.backend_args(openscad))
        except Exception:
            extra = []

        def job():
            pngs, log = render_views(openscad, scad, extra)
            return "render", pngs, log
        return job

    def app_command(self):
        return siblings.find_app("KherveCAD", "khervecad", "KherveCAD.py",
                                 "KHERVECAD_PATH",
                                 str(_settings().value(self.LOCATE_KEY, "")
                                     or ""), qt="PyQt5")

    @staticmethod
    def command_for(path):
        return siblings.app_command(path, qt="PyQt5")

    def edit_in_app(self):
        ok = super().edit_in_app()
        if ok:
            # KherveCAD does not take a file on its command line yet.
            self._hint.setText(
                f"KherveCAD is starting — open {self.document_path()} there "
                "(File ▸ Open). Each save there re-renders these views.")
        return ok

    edit_in_khervetex = edit_in_app


CELL_CLASSES["cad"] = CadCell
