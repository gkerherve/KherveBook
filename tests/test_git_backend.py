"""Tests for the per-notebook Git backend.

Copyright (C) 2026 Gwilherm Kerherve

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.
"""

import pytest

from khervebook import git_backend as gb

pytestmark = pytest.mark.skipif(
    not gb.is_available(), reason="pygit2 not installed")


def _write(path, source):
    path.write_text(source, encoding="utf-8")


def test_init_creates_dev_branch(tmp_path):
    d = tmp_path / "docs"
    assert gb.init_repo(d) is True
    assert (d / ".git").exists()
    # First commit lands on dev, not master.
    f = d / "Book1.kbook"
    _write(f, '{"cells": []}')
    oid = gb.commit_all(d, "feat: first", file_stem="Book1")
    assert oid
    assert gb.current_branch(d) == "dev"


def test_commit_detects_no_change(tmp_path):
    d = tmp_path / "docs"
    gb.init_repo(d)
    f = d / "Book1.kbook"
    _write(f, '{"cells": []}')
    assert gb.commit_all(d, "one", file_stem="Book1")
    # No file change -> no new commit.
    assert gb.commit_all(d, "again", file_stem="Book1") is None


def test_history_and_diff(tmp_path):
    d = tmp_path / "docs"
    gb.init_repo(d)
    f = d / "Book1.kbook"
    _write(f, '{"cells": []}')
    gb.commit_all(d, "feat: first snapshot", file_stem="Book1")
    _write(f, '{"cells": [{"type": "code", "source": "print(1)"}]}')
    oid2 = gb.commit_all(d, "feat: add a cell", file_stem="Book1")

    hist = gb.history_detailed(d, file_stem="Book1")
    assert [h["subject"] for h in hist] == [
        "feat: add a cell", "feat: first snapshot"]

    diff = gb.diff_for_commit(d, oid2)
    assert "print(1)" in diff


def test_stem_filter_isolates_notebooks(tmp_path):
    d = tmp_path / "docs"
    gb.init_repo(d)
    a = d / "Book1.kbook"
    b = d / "Other.kbook"
    _write(a, "a")
    _write(b, "b")
    gb.commit_all(d, "add Book1", file_stem="Book1")
    # A commit staged for Book1 must not carry Other.kbook along.
    hist = gb.history_detailed(d, file_stem="Other")
    assert hist == []


def test_branch_lifecycle(tmp_path):
    d = tmp_path / "docs"
    gb.init_repo(d)
    _write(d / "Book1.kbook", '{"cells": []}')
    gb.commit_all(d, "init", file_stem="Book1")

    ok, _ = gb.create_branch(d, "feature-x")
    assert ok
    names = {b["name"] for b in gb.list_branches(d)}
    assert {"dev", "feature-x"} <= names

    ok, _ = gb.switch_branch(d, "feature-x")
    assert ok
    assert gb.current_branch(d) == "feature-x"

    # Cannot delete the current branch.
    ok, _ = gb.delete_branch(d, "feature-x")
    assert not ok
    gb.switch_branch(d, "dev")
    ok, _ = gb.delete_branch(d, "feature-x")
    assert ok


def test_restore_rolls_files_back(tmp_path):
    d = tmp_path / "docs"
    gb.init_repo(d)
    f = d / "Book1.kbook"
    _write(f, "first")
    oid1 = gb.commit_all(d, "first", file_stem="Book1")
    _write(f, "second")
    gb.commit_all(d, "second", file_stem="Book1")

    ok, _ = gb.restore_to_commit(d, oid1)
    assert ok
    assert f.read_text(encoding="utf-8") == "first"


def test_remotes_roundtrip(tmp_path):
    d = tmp_path / "docs"
    gb.init_repo(d)
    assert gb.get_remotes(d) == []
    assert gb.set_remote(d, "origin", "https://example.com/repo.git")
    assert gb.get_remotes(d) == [
        ("origin", "https://example.com/repo.git")]
    assert gb.set_remote(d, "origin", "https://example.com/other.git")
    assert gb.get_remotes(d) == [
        ("origin", "https://example.com/other.git")]
    assert gb.remove_remote(d, "origin")
    assert gb.get_remotes(d) == []


def test_nested_repo_is_not_created(tmp_path):
    """A notebook saved inside an existing repo commits to that repo
    rather than nesting a second .git under it."""
    outer = tmp_path / "outer"
    gb.init_repo(outer)
    inner = outer / "sub"
    inner.mkdir()
    gb.init_repo(inner)          # should be a no-op (enclosing repo found)
    assert not (inner / ".git").exists()
