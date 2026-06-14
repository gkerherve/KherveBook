"""A tiny offline-tolerant thesaurus for Markdown/LaTeX cells.

Synonyms come from the free, key-less Datamuse API; on any network
failure an empty list is returned so the caller can show "(offline)".

Copyright (C) 2026 Gwilherm Kerherve

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.
"""

import json
import urllib.parse
import urllib.request


def synonyms(word: str, limit: int = 12, timeout: float = 4.0) -> list:
    """Up to *limit* synonyms for *word*, or [] if none / offline."""
    word = (word or "").strip()
    if not word or not all(c.isalpha() or c in "-'" for c in word):
        return []
    url = ("https://api.datamuse.com/words?rel_syn="
           + urllib.parse.quote(word) + f"&max={limit}")
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except Exception:
        return []
    out = []
    for item in data:
        w = item.get("word") if isinstance(item, dict) else None
        if w and w.lower() != word.lower():
            out.append(w)
    return out[:limit]
