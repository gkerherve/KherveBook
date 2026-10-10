"""References — the Qt-free half of the References cell (KherveRef).

Entries use KherveRef's own reference shape (``.kherveref/references/
<key>.json``): ``key``, ``type`` (BibLaTeX), ``authors`` as
``[{family, given}]`` or ``[{literal}]``, ``title``, ``date``,
``journal``/``booktitle``, ``volume``, ``number``, ``pages``, ``doi``,
``url``, ``publisher``… So an entry copied from a KherveRef library, or
from a DOI, is the same thing, and a notebook stays self-contained.

KherveRef itself is PySide6 and is never imported: its libraries are
read straight from disk (as KherveTeX's ``kherveref_link`` does), and it
is launched as its own process.

Also here: a small formatter (numbered and author–year), BibTeX reading
and writing, the DOI lookup (doi.org CSL-JSON, Crossref fallback), and
``[@key]`` → numbered citation links for Markdown.

Copyright (C) 2026 Gwilherm Kerherve

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.
"""

import html
import json
import os
import re
import sys
import unicodedata
from pathlib import Path

from .samples import outside_code

LINK_SCHEME = "kref"
STYLES = (("numbered", "Numbered [1]"), ("author-year", "Author–year"))
TEXT_FIELDS = ("title", "date", "journal", "booktitle", "publisher",
               "institution", "volume", "number", "pages", "edition",
               "doi", "url", "isbn", "note", "eprint")


# -- entries ------------------------------------------------------------------
def normalise(entry) -> dict:
    """A clean entry: known text fields as strings, authors as name dicts,
    empty fields dropped (as KherveRef writes them)."""
    e = entry if isinstance(entry, dict) else {}
    out = {"key": str(e.get("key") or "").strip(),
           "type": str(e.get("type") or "article").strip() or "article"}
    for role in ("authors", "editors"):
        names = []
        for a in e.get(role) or []:
            if isinstance(a, dict):
                n = {k: str(a[k]).strip() for k in ("family", "given",
                                                    "literal") if a.get(k)}
                if n:
                    names.append(n)
            elif isinstance(a, str) and a.strip():
                names.append(parse_name(a))
        if names:
            out[role] = names
    for k in TEXT_FIELDS:
        v = e.get(k)
        if v not in (None, ""):
            out[k] = str(v).strip()
    if not out.get("date") and e.get("year"):
        out["date"] = str(e["year"]).strip()
    if e.get("files"):
        out["files"] = [f for f in e["files"] if isinstance(f, dict)
                        and f.get("path")]
    return out


def parse_name(text: str) -> dict:
    """"Family, Given" or "Given Family" -> a name dict."""
    text = " ".join(text.replace("{", "").replace("}", "").split())
    if "," in text:
        family, given = (p.strip() for p in text.split(",", 1))
        return {"family": family, "given": given} if given \
            else {"family": family}
    parts = text.split(" ")
    if len(parts) == 1:
        return {"family": parts[0]}
    return {"family": parts[-1], "given": " ".join(parts[:-1])}


def year(entry) -> str:
    m = re.match(r"\s*(\d{4})", entry.get("date", ""))
    return m.group(1) if m else ""


def _ascii(text):
    return "".join(c for c in unicodedata.normalize("NFKD", text)
                   if c.isascii() and c.isalnum()).lower()


def make_key(entry, taken=()) -> str:
    """KherveRef-style key: family name + year + first title word,
    with a/b/c… appended when it is already taken."""
    authors = entry.get("authors") or [{}]
    first = authors[0]
    family = _ascii(first.get("family") or first.get("literal") or "anon")
    words = [w for w in re.findall(r"[A-Za-z]+", entry.get("title", ""))
             if w.lower() not in {"a", "an", "the", "on", "of", "and", "in"}]
    base = f"{family or 'anon'}{year(entry)}{_ascii(words[0]) if words else ''}"
    key, n = base, 0
    while key in taken:
        key = base + "abcdefghijklmnopqrstuvwxyz"[n % 26] * (n // 26 + 1)
        n += 1
    return key


# -- formatting -----------------------------------------------------------------
def _initials(given):
    parts = re.split(r"([\s-]+)", given.strip())
    out = ""
    for p in parts:
        if not p.strip():
            continue
        if p.strip() == "-":
            out = out.rstrip() + "-"
        else:
            out += p[0] + ". "
    return out.strip()


def _name(a, inverted=True):
    if "literal" in a:
        return a["literal"]
    init = _initials(a.get("given", ""))
    if not init:
        return a.get("family", "")
    return f"{a.get('family', '')}, {init}" if inverted \
        else f"{init} {a.get('family', '')}"


def authors_text(entry, style="numbered", limit=10) -> str:
    names = [_name(a) for a in entry.get("authors") or []]
    if not names:
        return ""
    if len(names) > limit:
        names = names[:limit - 1] + ["et al."]
    if style == "numbered":
        return "; ".join(names)
    if len(names) == 1:
        return names[0]
    return ", ".join(names[:-1]) + ", & " + names[-1]


def short_cite(entry) -> str:
    """"Kerherve et al., 2023" — for author–year citations."""
    authors = entry.get("authors") or []
    fam = [a.get("family") or a.get("literal", "") for a in authors]
    who = (fam[0] if len(fam) == 1 else
           f"{fam[0]} & {fam[1]}" if len(fam) == 2 else
           f"{fam[0]} et al." if fam else entry.get("key", "?"))
    return f"{who}, {year(entry) or 'n.d.'}"


def format_entry(entry, style="numbered") -> str:
    """One reference as HTML (italics / bold as journals print them)."""
    e = {k: html.escape(v) if isinstance(v, str) else v
         for k, v in entry.items()}
    who = html.escape(authors_text(entry, style))
    title = e.get("title", "")
    venue = e.get("journal") or e.get("booktitle") or ""
    y = year(entry)
    doi = entry.get("doi", "")
    link = (f' <a href="https://doi.org/{html.escape(doi)}">'
            f'doi:{html.escape(doi)}</a>' if doi else
            f' <a href="{e["url"]}">{e["url"]}</a>' if e.get("url") else "")
    if style == "numbered":                        # ACS-like
        if who and not who.endswith("."):
            who += "."
        if title and not title.endswith((".", "?", "!")):
            title += "."
        bits = [who, title]
        tail = f"<i>{venue}</i>" if venue else e.get("publisher", "")
        if y:
            tail += f" <b>{y}</b>,"
        if e.get("volume"):
            tail += f" <i>{e['volume']}</i>"
            if e.get("number"):
                tail += f" ({e['number']})"
            tail += ","
        if e.get("pages"):
            tail += f" {e['pages']}"
        tail = tail.strip().rstrip(",")
        text = " ".join(b for b in bits + [tail] if b)
        return f"{text}.{link}" if text else link.strip()
    # author–year (APA-like)
    out = f"{who} ({y or 'n.d.'}). {title}."
    if venue:
        out += f" <i>{venue}</i>"
        if e.get("volume"):
            out += f", <i>{e['volume']}</i>"
            if e.get("number"):
                out += f"({e['number']})"
        if e.get("pages"):
            out += f", {e['pages']}"
        out += "."
    elif e.get("publisher"):
        out += f" {e['publisher']}."
    return out + link


def plain(html_text: str) -> str:
    return html.unescape(re.sub(r"<[^>]+>", "", html_text))


# -- citations in Markdown ------------------------------------------------------
_CITE = re.compile(r"\[(@[\w:.+/-]+(?:\s*[;,]\s*@[\w:.+/-]+)*)\]")


def link_citations(markdown: str, index: dict, style="numbered") -> str:
    """``[@key]`` / ``[@a; @b]`` -> numbered (or author–year) links.

    *index* maps key -> (number, entry). Unknown keys leave the whole
    bracket as typed, so a typo shows. Code is left alone."""
    if not index or "[@" not in (markdown or ""):
        return markdown

    def cite(m):
        keys = [k.strip().lstrip("@") for k in re.split(r"[;,]", m.group(1))]
        if not all(k in index for k in keys):
            return m.group()
        if style == "author-year":
            parts = [f"[{short_cite(index[k][1])}]({LINK_SCHEME}:{k})"
                     for k in keys]
            return "(" + "; ".join(parts) + ")"
        parts = [f"[{index[k][0]}]({LINK_SCHEME}:{k})" for k in keys]
        return "\\[" + ", ".join(parts) + "\\]"

    return outside_code(markdown, lambda text: _CITE.sub(cite, text))


def cited_keys(text: str):
    return [k.strip().lstrip("@") for m in _CITE.finditer(text or "")
            for k in re.split(r"[;,]", m.group(1))]


# -- BibTeX ---------------------------------------------------------------------
_BIB_TYPES = {"thesis": "phdthesis", "report": "techreport",
              "online": "misc"}


def _bib_value(v):
    return "{" + v.replace("\\", "\\\\").replace("{", "\\{")\
        .replace("}", "\\}") + "}"


def to_bibtex(entries) -> str:
    out = []
    for e in entries:
        lines = [f"@{_BIB_TYPES.get(e.get('type'), e.get('type', 'misc'))}"
                 f"{{{e['key']},"]
        names = [(f"{a['family']}, {a['given']}" if a.get("given") else
                  a.get("family") or "{" + a.get("literal", "") + "}")
                 for a in e.get("authors") or []]
        if names:
            lines.append(f"  author = {_bib_value(' and '.join(names))},")
        for k in TEXT_FIELDS:
            if k == "date" or not e.get(k):
                continue
            lines.append(f"  {k} = {_bib_value(e[k])},")
        if year(e):
            lines.append(f"  year = {{{year(e)}}},")
        lines[-1] = lines[-1].rstrip(",")
        out.append("\n".join(lines) + "\n}")
    return "\n\n".join(out) + ("\n" if out else "")


def _read_braced(text, i):
    """Text inside the brace group starting at text[i] == '{', and the
    index after it."""
    depth, j = 0, i
    while j < len(text):
        c = text[j]
        if c == "\\":
            j += 2
            continue
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return text[i + 1:j], j + 1
        j += 1
    return text[i + 1:], len(text)


def _unlatex(v):
    v = re.sub(r"\\[`'^\"~=.]\{?(\w)\}?", r"\1", v)    # accents -> letter
    v = v.replace("\\&", "&").replace("--", "–").replace("\\_", "_")
    return " ".join(v.replace("{", "").replace("}", "").split())


def parse_bibtex(text: str):
    """BibTeX / BibLaTeX -> entries. Tolerant: @string/@comment are
    skipped and a malformed entry is dropped, not fatal."""
    entries = []
    for m in re.finditer(r"@(\w+)\s*\{", text):
        kind = m.group(1).lower()
        if kind in ("string", "comment", "preamble"):
            continue
        body, _end = _read_braced(text, m.end() - 1)
        key, _, rest = body.partition(",")
        fields, i = {}, 0
        while i < len(rest):
            fm = re.compile(r"\s*([\w-]+)\s*=\s*").match(rest, i)
            if not fm:
                break
            name, i = fm.group(1).lower(), fm.end()
            if i < len(rest) and rest[i] == "{":
                value, i = _read_braced(rest, i)
            elif i < len(rest) and rest[i] == '"':
                j = rest.find('"', i + 1)
                value, i = rest[i + 1:j], (j + 1 if j >= 0 else len(rest))
            else:
                vm = re.compile(r"[^,\s]+").match(rest, i)
                value, i = (vm.group(), vm.end()) if vm else ("", i)
            fields[name] = _unlatex(value)
            cm = re.compile(r"\s*,").match(rest, i)
            i = cm.end() if cm else i
        if not key.strip():
            continue
        e = {"key": key.strip(), "type": {"phdthesis": "thesis",
                                          "mastersthesis": "thesis",
                                          "techreport": "report"}
             .get(kind, kind)}
        if fields.get("author"):
            e["authors"] = [parse_name(n) for n in
                            re.split(r"\s+and\s+", fields.pop("author"))]
        if "journaltitle" in fields:
            fields.setdefault("journal", fields.pop("journaltitle"))
        if "year" in fields and "date" not in fields:
            fields["date"] = fields.pop("year")
        e.update(fields)
        entries.append(normalise(e))
    return entries


# -- DOI lookup -------------------------------------------------------------------
_CSL_TYPES = {"article-journal": "article", "paper-conference":
              "inproceedings", "book": "book", "chapter": "incollection",
              "thesis": "thesis", "report": "report",
              "posted-content": "online", "dataset": "dataset"}


def clean_doi(text: str) -> str:
    m = re.search(r"10\.\d{4,9}/\S+", text or "")
    return m.group().rstrip(".,;)") if m else ""


def from_csl(c: dict) -> dict:
    """A CSL-JSON record (doi.org / Crossref) -> an entry."""
    def first(v):
        return (v[0] if isinstance(v, list) and v else v) or ""

    parts = ((c.get("issued") or {}).get("date-parts") or [[None]])[0]
    date = "-".join(f"{p:02d}" if i else str(p)
                    for i, p in enumerate(parts) if p)
    e = {"type": _CSL_TYPES.get(c.get("type"), "misc"),
         "authors": [{k: a[k] for k in ("family", "given", "literal")
                      if a.get(k)} for a in c.get("author") or []],
         "title": re.sub(r"<[^>]+>", "", first(c.get("title"))),
         "date": date, "volume": c.get("volume"), "number": c.get("issue"),
         "pages": (c.get("page") or "").replace("-", "–"),
         "doi": c.get("DOI"), "publisher": c.get("publisher"),
         "url": c.get("URL") if not c.get("DOI") else ""}
    venue = first(c.get("container-title"))
    e["booktitle" if e["type"] in ("inproceedings", "incollection")
      else "journal"] = venue
    return normalise(e)


def _get(url, accept):
    import ssl
    import urllib.request
    try:
        import certifi
        ctx = ssl.create_default_context(cafile=certifi.where())
    except Exception:
        ctx = ssl.create_default_context()
    req = urllib.request.Request(url, headers={
        "Accept": accept, "User-Agent": "KherveBook (mailto:"
        "khervetools@users.noreply.github.com)"})
    with urllib.request.urlopen(req, timeout=15, context=ctx) as r:
        return r.read().decode("utf-8")


def lookup_doi(doi: str) -> dict:
    """The entry for *doi* (network). Raises ValueError / OSError."""
    doi = clean_doi(doi)
    if not doi:
        raise ValueError("that does not look like a DOI (10.xxxx/…)")
    from urllib.parse import quote
    try:
        csl = json.loads(_get(f"https://doi.org/{quote(doi)}",
                              "application/vnd.citationstyles.csl+json"))
    except Exception:
        msg = json.loads(_get(f"https://api.crossref.org/works/{quote(doi)}",
                              "application/json"))
        csl = msg["message"]
        csl["DOI"] = csl.get("DOI", doi)
    entry = from_csl(csl)
    entry.setdefault("doi", doi)
    return entry


# -- KherveRef libraries ------------------------------------------------------------
def _appdata():
    if sys.platform == "win32":
        return Path(os.environ.get("APPDATA") or Path.home())
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support"
    return Path(os.environ.get("XDG_DATA_HOME")
                or Path.home() / ".local" / "share")


def library_root(path):
    """A library folder from a folder or its ``<Name>.kref`` manifest."""
    p = Path(path)
    if p.is_file() and p.suffix.lower() == ".kref":
        p = p.parent
    return p if (p / ".kherveref" / "references").is_dir() else None


def known_libraries(extra=()):
    """KherveRef libraries on this machine, most recent first."""
    found = list(extra)
    try:
        data = json.loads((_appdata() / "KherveRef" / "libraries.json")
                          .read_text(encoding="utf-8"))
        found += data.get("libraries") or []
    except (OSError, ValueError, AttributeError):
        pass
    out = []
    for p in found:
        root = library_root(p) if p else None
        if root is not None and root not in out:
            out.append(root)
    return out


def library_name(root) -> str:
    for manifest in Path(root).glob("*.kref"):
        try:
            return json.loads(manifest.read_text(encoding="utf-8"))\
                .get("name") or manifest.stem
        except (OSError, ValueError):
            return manifest.stem
    return Path(root).name


def load_library(root):
    """Every reference in a KherveRef library, by key."""
    entries = []
    folder = Path(root) / ".kherveref" / "references"
    for f in sorted(folder.glob("*.json")):
        try:
            e = normalise(json.loads(f.read_text(encoding="utf-8")))
        except (OSError, ValueError):
            continue
        if e["key"]:
            entries.append(e)
    return entries
