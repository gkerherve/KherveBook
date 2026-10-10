"""Import a KherveNote ``.knote`` (lecture / meeting notes) as cells.

A ``.knote`` is a zip: ``note.json`` plus ``assets/`` (pictures,
recordings, attached documents). The note is sections of blocks —
typed text, key points, questions, headings, list items, pictures and
attachments, with inline bold/italic/underline marks — and a separate
Speech transcript of timed lines. KherveNote is PySide6; this reads the
format directly (after its ``model.Note.plain_text``), Qt-free.

The import gives a title cell, one Markdown cell per section, an SVG
cell per picture, a File cell holding the attached documents, and the
speech as a collapsed "What was said" cell, each line stamped with its
time of day.

Copyright (C) 2026 Gwilherm Kerherve

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.
"""

import base64
import datetime
import json
import zipfile
from pathlib import PurePosixPath

_MIME = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
         ".gif": "image/gif", ".bmp": "image/bmp", ".webp": "image/webp"}
_MARK = {"b": ("**", "**"), "i": ("*", "*"), "u": ("<u>", "</u>")}


def is_knote(path) -> bool:
    return str(path).lower().endswith(".knote")


def read(path):
    """(note dict, {asset path: bytes}) from a .knote zip."""
    with zipfile.ZipFile(path) as zf:
        note = json.loads(zf.read("note.json").decode("utf-8"))
        assets = {n: zf.read(n) for n in zf.namelist()
                  if n.startswith("assets/") and not n.endswith("/")}
    if not isinstance(note, dict):
        raise ValueError("not a KherveNote note")
    return note, assets


def clock(note, t) -> str:
    """Seconds since the session started -> "HH:MM:SS" time of day (or
    the elapsed time when the start is unknown)."""
    try:
        t = float(t)
    except (TypeError, ValueError):
        return ""
    try:
        start = datetime.datetime.fromisoformat(
            (note.get("meta") or {}).get("started", ""))
        return (start + datetime.timedelta(seconds=t)).strftime("%H:%M:%S")
    except (ValueError, TypeError):
        return str(datetime.timedelta(seconds=int(t)))


def marked(text, marks) -> str:
    """Apply KherveNote's ``[[start, length, "b"|"i"|"u"], …]`` as
    Markdown. Spans are opened/closed at their edges, innermost last."""
    if not marks:
        return text
    opens, closes = {}, {}
    for m in marks:
        try:
            start, length, kind = int(m[0]), int(m[1]), m[2]
        except (TypeError, ValueError, IndexError):
            continue
        if kind not in _MARK or length <= 0:
            continue
        # Markdown emphasis cannot end on a space: pull the edges in.
        seg = text[start:start + length]
        lead = len(seg) - len(seg.lstrip())
        trail = len(seg) - len(seg.rstrip())
        a, b = start + lead, start + length - trail
        if a >= b:
            continue
        opens.setdefault(a, []).append(kind)
        closes.setdefault(b, []).insert(0, kind)
    out = []
    for i in range(len(text) + 1):
        out += [_MARK[k][1] for k in closes.get(i, [])]
        out += [_MARK[k][0] for k in opens.get(i, [])]
        if i < len(text):
            out.append(text[i])
    return "".join(out)


def _block_md(note, b, numbering):
    kind = b.get("kind", "typed")
    text = marked(str(b.get("text") or ""), b.get("marks"))
    if kind != "item":
        numbering.clear()
    if kind == "heading":
        level = 3 if int(b.get("level") or 2) <= 2 else 4
        return "#" * level + " " + text
    if kind == "item":
        level = max(0, min(3, int(b.get("level") or 0)))
        indent = "   " * level
        if b.get("numbered"):
            numbering[level] = numbering.get(level, 0) + 1
            for deeper in [k for k in numbering if k > level]:
                del numbering[deeper]
            return f"{indent}{numbering[level]}. {text}"
        return f"{indent}- {text}"
    if kind == "important":
        return f"> **Key point:** {text}"
    if kind == "question":
        return f"> **Question:** {text}"
    if kind == "transcript":
        when = clock(note, b.get("t"))
        return f"> *{when}* — {text}" if when else f"> {text}"
    if kind == "attachment":
        return f"📎 *{text or PurePosixPath(b.get('path', '')).name}*"
    return text


def _join(lines):
    """Blank lines between blocks, but consecutive list items stay a list."""
    out = []
    for i, line in enumerate(lines):
        if i and not (_is_item(line) and _is_item(lines[i - 1])):
            out.append("")
        out.append(line)
    return "\n".join(out)


def _is_item(line):
    s = line.lstrip()
    return s.startswith("- ") or (s[:1].isdigit() and ". " in s[:5])


def to_cells(path) -> list:
    """The .knote as KherveBook cell dicts."""
    from .importers import image_to_svg
    note, assets = read(path)
    meta = note.get("meta") or {}
    title = str(meta.get("title") or PurePosixPath(str(path)).stem)
    head = [f"# {title}"]
    facts = [f"**{label}:** {meta[k]}" for k, label in
             (("speaker", "Speaker"), ("date", "Date"), ("place", "Place"))
             if meta.get(k)]
    if facts:
        head.append("  \n".join(facts))
    if note.get("summary"):
        head.append("## Summary\n\n" + str(note["summary"]).strip())
    cells = [{"type": "markdown", "source": "\n\n".join(head)}]

    files = []
    for section in note.get("sections") or []:
        lines, numbering = [], {}
        if section.get("title"):
            lines.append(f"## {section['title']}")
        for b in section.get("blocks") or []:
            if b.get("kind") == "image" and b.get("path") in assets:
                if lines:
                    cells.append({"type": "markdown",
                                  "source": _join(lines)})
                    lines = []
                ext = PurePosixPath(b["path"]).suffix.lower()
                cell = {"type": "svg", "source": image_to_svg(
                    assets[b["path"]], _MIME.get(ext, "image/png"))}
                if b.get("text"):
                    cell["title"] = str(b["text"])
                cells.append(cell)
                continue
            if b.get("kind") == "attachment" and b.get("path") in assets:
                files.append((b.get("text") or
                              PurePosixPath(b["path"]).name, b["path"]))
            lines.append(_block_md(note, b, numbering))
        if lines:
            cells.append({"type": "markdown", "source": _join(lines)})

    for att in note.get("attachments") or []:
        if isinstance(att, dict) and att.get("path") in assets and \
                att["path"] not in {p for _n, p in files}:
            files.append((att.get("name") or
                          PurePosixPath(att["path"]).name, att["path"]))
    if files:
        cells.append({"type": "file", "title": "Attached documents",
                      "source": json.dumps({"kbook_files": 1, "files": [
                          {"name": name, "size": len(assets[p]),
                           "embed": base64.b64encode(assets[p])
                           .decode("ascii")} for name, p in files]})})

    speech = [ln for ln in note.get("transcript") or []
              if isinstance(ln, dict) and str(ln.get("text", "")).strip()]
    if speech:
        body = "\n\n".join(f"**{clock(note, ln.get('t'))}** "
                           f"{str(ln['text']).strip()}" for ln in speech)
        cells.append({"type": "markdown", "title": "What was said",
                      "collapsed": True,
                      "source": "## What was said\n\n" + body})
    return cells
