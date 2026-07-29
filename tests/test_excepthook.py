"""An exception in a slot must be reported, not abort the process.

Copyright (C) 2026 Gwilherm Kerherve

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.
"""

import io
import sys

import pytest

from khervebook import app


@pytest.fixture
def hook():
    """A hook writing to a buffer, with the real one restored after."""
    log = io.StringIO()
    before = sys.excepthook
    yield app.install_excepthook(log, report=False), log
    sys.excepthook = before


def _raise(hook_fn, exc):
    try:
        raise exc
    except type(exc):
        hook_fn(*sys.exc_info())


def test_the_traceback_reaches_the_crash_log(hook):
    hook_fn, log = hook
    _raise(hook_fn, ValueError("a .kfit went wrong"))
    text = log.getvalue()
    assert "ValueError" in text
    assert "a .kfit went wrong" in text
    assert "test_excepthook.py" in text      # the frame it came from


def test_install_replaces_the_default_hook():
    before = sys.excepthook
    try:
        app.install_excepthook(io.StringIO(), report=False)
        # PyQt5 aborts the process unless an excepthook takes precedence.
        assert sys.excepthook is not sys.__excepthook__
    finally:
        sys.excepthook = before


def test_keyboard_interrupt_still_falls_through(hook, monkeypatch):
    hook_fn, log = hook
    called = []
    monkeypatch.setattr(sys, "__excepthook__",
                        lambda *a: called.append(a))
    _raise(hook_fn, KeyboardInterrupt())
    assert called
    assert log.getvalue() == ""


def test_a_closed_stream_does_not_re_raise(hook):
    hook_fn, log = hook
    log.close()
    _raise(hook_fn, ValueError("boom"))      # must not raise


def test_repeating_faults_are_reported_once(monkeypatch):
    """A method throwing on every repaint must not stack up dialogs."""
    shown = []
    monkeypatch.setattr(app, "_show", lambda text: shown.append(text))
    before = sys.excepthook
    try:
        hook_fn = app.install_excepthook(io.StringIO(), report=True)
        for _ in range(20):
            _raise(hook_fn, ValueError("same fault"))
        assert len(shown) == 1
    finally:
        sys.excepthook = before


def test_distinct_faults_are_each_reported_up_to_the_cap(monkeypatch):
    shown = []
    monkeypatch.setattr(app, "_show", lambda text: shown.append(text))
    before = sys.excepthook
    try:
        hook_fn = app.install_excepthook(io.StringIO(), report=True)
        for i in range(app._MAX_DIALOGS + 4):
            _raise(hook_fn, ValueError(f"fault {i}"))
        assert len(shown) == app._MAX_DIALOGS
    finally:
        sys.excepthook = before
