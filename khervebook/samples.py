"""Sample register — the notebook's lab samples, their lineage and usage.

Ported in spirit from kELN (KherveOS's electronic lab notebook): every
sample gets a stable ID (``S-0001`` — a prefix plus a zero-padded
counter), a few descriptive fields, a status, and optional *parents*, so
"annealed from S-0003" forms a lineage tree. The register travels inside
the ``.kbook`` as a top-level ``"samples"`` object.

A cell *uses* a sample when its text names the ID (``@S-0001`` in prose,
``ksample("S-0001")`` in code); `usage` finds those cells, and
`link_mentions` turns ``@S-0001`` in Markdown into a clickable link.

Qt-free so it is testable on its own and reusable by the kernel.

Copyright (C) 2026 Gwilherm Kerherve

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.
"""

import re
from dataclasses import asdict, dataclass, field, fields

#: The statuses a sample moves through (kELN's set).
STATUSES = ("in use", "consumed", "discarded")
#: URL scheme of a rendered @mention link.
LINK_SCHEME = "ksample"

DEFAULT_PREFIX = "S"
DEFAULT_DIGITS = 4


def outside_code(markdown: str, fn) -> str:
    """Apply *fn* to the prose of *markdown* only — fenced blocks and
    `inline code` pass through untouched."""
    out, fenced = [], False
    for line in markdown.split("\n"):
        if line.lstrip().startswith(("```", "~~~")):
            fenced = not fenced
            out.append(line)
            continue
        if fenced:
            out.append(line)
            continue
        # Odd-numbered pieces of a split on backticks are code spans.
        parts = line.split("`")
        for i in range(0, len(parts), 2):
            parts[i] = fn(parts[i])
        out.append("`".join(parts))
    return "\n".join(out)


@dataclass
class Sample:
    id: str
    name: str = ""
    composition: str = ""
    batch: str = ""
    location: str = ""
    made: str = ""                       # ISO date, as typed
    status: str = "in use"
    parents: list = field(default_factory=list)
    notes: str = ""

    @classmethod
    def from_dict(cls, d: dict) -> "Sample":
        """Normalise a stored sample: unknown keys dropped, strings kept
        as strings, so a hand-edited .kbook never breaks the register."""
        known = {f.name for f in fields(cls)}
        clean = {k: v for k, v in (d or {}).items() if k in known}
        sample = cls(id=str(clean.pop("id", "")).strip())
        for k, v in clean.items():
            if k == "parents":
                v = [str(p).strip() for p in (v or []) if str(p).strip()]
            else:
                v = "" if v is None else str(v)
            setattr(sample, k, v)
        if sample.status not in STATUSES:
            sample.status = STATUSES[0]
        return sample

    def to_dict(self) -> dict:
        return asdict(self)

    def label(self) -> str:
        return f"{self.id} — {self.name}" if self.name else self.id


class SampleRegistry:
    """The ordered list of samples, with ID allocation and lineage."""

    def __init__(self, prefix=DEFAULT_PREFIX, digits=DEFAULT_DIGITS):
        self.prefix = prefix
        self.digits = digits
        self.items = []

    # -- lookup -------------------------------------------------------------
    def __len__(self):
        return len(self.items)

    def __iter__(self):
        return iter(self.items)

    def get(self, sample_id):
        for s in self.items:
            if s.id == sample_id:
                return s
        return None

    def ids(self):
        return [s.id for s in self.items]

    # -- editing --------------------------------------------------------------
    def next_id(self) -> str:
        """The next free ID: one past the highest counter in use, so a
        deleted sample's ID is never handed to a different sample."""
        pat = re.compile(rf"^{re.escape(self.prefix)}-(\d+)$")
        top = 0
        for s in self.items:
            m = pat.match(s.id)
            if m:
                top = max(top, int(m.group(1)))
        return f"{self.prefix}-{top + 1:0{self.digits}d}"

    def add(self, **values) -> Sample:
        sample = Sample.from_dict({**values, "id": self.next_id()})
        self.items.append(sample)
        return sample

    def update(self, sample_id, **values):
        sample = self.get(sample_id)
        if sample is None:
            raise KeyError(sample_id)
        merged = Sample.from_dict({**sample.to_dict(), **values,
                                   "id": sample_id})
        # A sample cannot descend from itself or from its own descendants.
        bad = {sample_id} | set(self.descendants(sample_id))
        merged.parents = [p for p in merged.parents if p not in bad]
        self.items[self.items.index(sample)] = merged
        return merged

    def remove(self, sample_id):
        self.items = [s for s in self.items if s.id != sample_id]

    # -- lineage --------------------------------------------------------------
    def children(self, sample_id):
        return [s.id for s in self.items if sample_id in s.parents]

    def ancestors(self, sample_id):
        """Every sample *sample_id* was made from, nearest first."""
        out, todo = [], list(getattr(self.get(sample_id), "parents", []))
        while todo:
            p = todo.pop(0)
            if p in out or p == sample_id:
                continue
            out.append(p)
            todo.extend(getattr(self.get(p), "parents", []))
        return out

    def descendants(self, sample_id):
        out, todo = [], self.children(sample_id)
        while todo:
            c = todo.pop(0)
            if c in out or c == sample_id:
                continue
            out.append(c)
            todo.extend(self.children(c))
        return out

    def roots(self):
        """Samples with no parent present in the register (tree tops)."""
        ids = set(self.ids())
        return [s.id for s in self.items
                if not any(p in ids for p in s.parents)]

    # -- persistence ----------------------------------------------------------
    def to_dict(self) -> dict:
        return {"prefix": self.prefix, "digits": self.digits,
                "items": [s.to_dict() for s in self.items]}

    def load(self, data):
        data = data if isinstance(data, dict) else {}
        prefix = str(data.get("prefix") or DEFAULT_PREFIX).strip()
        self.prefix = prefix if re.fullmatch(r"[A-Za-z][\w]*", prefix) \
            else DEFAULT_PREFIX
        try:
            self.digits = max(1, min(8, int(data.get("digits",
                                                     DEFAULT_DIGITS))))
        except (TypeError, ValueError):
            self.digits = DEFAULT_DIGITS
        seen, items = set(), []
        for d in data.get("items") or []:
            if not isinstance(d, dict):
                continue
            s = Sample.from_dict(d)
            if s.id and s.id not in seen:
                seen.add(s.id)
                items.append(s)
        self.items = items

    def clear(self):
        self.load({})

    # -- mentions -------------------------------------------------------------
    def id_pattern(self):
        """Regex matching any ID of this register's shape, as a whole word."""
        return re.compile(rf"(?<![\w-]){re.escape(self.prefix)}-\d+(?![\w-])")

    def mentioned(self, text: str):
        """The registered sample IDs named in *text*, in first-seen order."""
        known = set(self.ids())
        out = []
        for m in self.id_pattern().finditer(text or ""):
            if m.group() in known and m.group() not in out:
                out.append(m.group())
        return out

    def usage(self, cells):
        """{sample id: [cell, ...]} — the cells whose source names it."""
        found = {}
        for cell in cells:
            for sid in self.mentioned(cell.source()):
                found.setdefault(sid, []).append(cell)
        return found

    def link_mentions(self, markdown: str) -> str:
        """``@S-0001`` -> a ``ksample:`` Markdown link, outside code spans
        and fenced blocks, for registered IDs only (an unknown ID stays
        plain text, so a typo reads as a typo)."""
        known = set(self.ids())
        if not known or "@" not in (markdown or ""):
            return markdown
        pat = re.compile(rf"(?<![\w@])@({re.escape(self.prefix)}-\d+)"
                         r"(?![\w-])")

        def link(m):
            sid = m.group(1)
            if sid not in known:
                return m.group()
            return f"[@{sid}]({LINK_SCHEME}:{sid})"

        return outside_code(markdown, lambda text: pat.sub(link, text))

    def summary_text(self) -> str:
        """A compact listing (for the AI assistant's view of the notebook)."""
        lines = []
        for s in self.items:
            bits = [s.label()]
            for k in ("composition", "batch", "location", "made"):
                v = getattr(s, k)
                if v:
                    bits.append(f"{k}: {v}")
            if s.status != STATUSES[0]:
                bits.append(s.status)
            if s.parents:
                bits.append("from " + ", ".join(s.parents))
            lines.append("; ".join(bits))
        return "\n".join(lines)
