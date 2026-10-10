"""KherveSlide deck cell — a slide deck shown as its slides.

KherveSlide (PySide6, never imported) saves a deck as ``<stem>.kslide``
JSON and writes the Beamer source beside it as ``<stem>.tex`` on every
save. The cell is the KherveTeX document cell with KherveSlide's hooks:
it holds the ``.kslide`` (sidecar file, like an attachment), shows the
slides from ``<stem>.pdf`` when current or else compiles ``<stem>.tex``
with tectonic, and "Edit in KherveSlide" opens the deck there; each save
re-renders the slides.

A deck that has never been saved by KherveSlide has no ``.tex`` yet, so
it cannot be typeset here — the cell says so.

Copyright (C) 2026 Gwilherm Kerherve

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.
"""

import json
from pathlib import Path

from . import ktexdoc, siblings
from .cells import CELL_CLASSES
from .ktexcell import KTexCell, _settings


def is_kslide(path) -> bool:
    return str(path).lower().endswith(".kslide")


def deck_title(path) -> str:
    try:
        deck = json.loads(Path(path).read_text(encoding="utf-8"))
        title = str(deck.get("title") or "").strip()
        n = len(deck.get("slides") or [])
    except (OSError, ValueError, AttributeError):
        return Path(path).name
    name = title or Path(path).stem
    return f"{name}  ({n} slide{'s' if n != 1 else ''})"


class SlideCell(KTexCell):
    """A KherveSlide deck."""

    CELL_TYPE = "slide"
    SOURCE_KEY = "kbook_slide"
    APP = "KherveSlide"
    DOC_NOUN = "KherveSlide deck"
    ICON = "mdi.presentation"
    EXTS_TEXT = ".kslide"
    FILE_FILTER = "KherveSlide decks (*.kslide);;All files (*)"
    LOCATE_FILTER = ("KherveSlide (KherveSlide.app KherveSlide.exe "
                     "KherveSlide.py *.app *.exe *.py);;All files (*)")
    LOCATE_KEY = "apps/kherveslide"
    CAN_CREATE = False
    HOW = {"pdf": "from the deck's exported PDF",
           "tex": "typeset from the Beamer .tex KherveSlide writes"}

    def accepts(self, path) -> bool:
        return is_kslide(path)

    def doc_title(self, path) -> str:
        return deck_title(path)

    @staticmethod
    def pdf_source(path):
        p = Path(path)
        doc_time = ktexdoc._mtime(p)
        for ext, kind in ((".pdf", "pdf"), (".tex", "tex")):
            f = ktexdoc.sibling(p, ext)
            if f.exists() and ktexdoc._mtime(f) >= doc_time - ktexdoc._SLACK:
                return kind, f
        return "model", p

    @classmethod
    def pdf_for(cls, path):
        kind, src = cls.pdf_source(path)
        if kind == "pdf":
            return kind, src.read_bytes(), ""
        if kind == "tex":
            pdf, log = ktexdoc.compile_tex(src, src.with_suffix(".pdf"))
            return kind, pdf, log
        return kind, None, ("This deck has no current Beamer .tex beside "
                            "it. Open it in KherveSlide and save once "
                            "(Ctrl+S) — the slides then appear here.")

    def app_command(self):
        return siblings.find_app("KherveSlide", "kherveslide",
                                 "KherveSlide.py", "KHERVESLIDE_PATH",
                                 str(_settings().value(self.LOCATE_KEY, "")
                                     or ""))

    @staticmethod
    def command_for(path):
        return siblings.app_command(path)


CELL_CLASSES["slide"] = SlideCell
