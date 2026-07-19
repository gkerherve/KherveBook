"""Runtime-derived version string.

The version is `0.1.{commit_count}+{short_sha}`, where commit_count comes
from `git rev-list --count HEAD` so it monotonically bumps on every
commit without anyone having to edit a constant. Frozen (PyInstaller)
builds never ship a `.git` folder, so the build script writes the
resolved string to a `VERSION` file next to this one and bundles it —
`get_version()` checks that first. Only a source checkout with neither
a bundled VERSION file nor .git falls back to ``_FALLBACK``.

Copyright (C) 2026 Gwilherm Kerherve

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.
"""

import subprocess
from functools import lru_cache
from pathlib import Path

_FALLBACK = "0.1.0"


@lru_cache(maxsize=1)
def get_version() -> str:
    bundled = Path(__file__).resolve().parent / "VERSION"
    if bundled.is_file():
        version = bundled.read_text(encoding="utf-8").strip()
        if version:
            return version
    root = Path(__file__).resolve().parent.parent
    if not (root / ".git").exists():
        return _FALLBACK
    try:
        count = subprocess.check_output(
            ["git", "rev-list", "--count", "HEAD"],
            cwd=root, stderr=subprocess.DEVNULL,
        ).strip().decode()
        sha = subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=root, stderr=subprocess.DEVNULL,
        ).strip().decode()
    except (subprocess.CalledProcessError, FileNotFoundError, OSError):
        return _FALLBACK
    return f"0.1.{count}+{sha}" if count and sha else _FALLBACK
