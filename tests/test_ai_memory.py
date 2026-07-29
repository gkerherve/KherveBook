"""The AI dock's conversation memory: a long window that survives a restart.

Copyright (C) 2026 Gwilherm Kerherve

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.
"""

import json

import pytest

from khervebook import ai_memory


@pytest.fixture(autouse=True)
def _own_store(tmp_path, monkeypatch):
    """Keep the tests off the developer's real saved conversation."""
    target = tmp_path / "ai_conversation.json"
    monkeypatch.setattr(ai_memory, "path", lambda: target)
    return target


def _turns(n, size=10):
    """n alternating turns, each *size* characters of content."""
    return [{"role": "user" if i % 2 == 0 else "assistant",
             "content": f"{i}" * size} for i in range(n)]


# -- the window ------------------------------------------------------------
def test_a_short_conversation_is_kept_whole():
    history = _turns(6)
    assert ai_memory.trim(history, limit=10_000) == history


def test_the_oldest_turns_go_when_the_budget_is_exceeded():
    history = _turns(20, size=100)
    kept = ai_memory.trim(history, limit=500)
    assert len(kept) < len(history)
    assert kept[-1] == history[-1]              # the newest always survives
    assert sum(len(t["content"]) for t in kept) <= 500


def test_the_window_always_starts_on_a_user_turn():
    """A history opening mid-exchange is rejected by the messages APIs."""
    history = _turns(21, size=100)
    kept = ai_memory.trim(history, limit=450)
    assert kept[0]["role"] == "user"


def test_the_default_budget_is_generous():
    """'A lot of memory' — ~100k tokens, not a handful of turns."""
    assert ai_memory.DEFAULT_BUDGET >= 200_000
    history = _turns(200, size=500)             # 100k chars of conversation
    assert ai_memory.trim(history, limit=ai_memory.DEFAULT_BUDGET) == history


def test_the_budget_is_configurable(qapp):
    before = ai_memory.budget()
    try:
        ai_memory.set_budget(5_000)
        assert ai_memory.budget() == 5_000
    finally:
        ai_memory.set_budget(before)


def test_a_nonsense_budget_falls_back(qapp, monkeypatch):
    monkeypatch.setattr(ai_memory.QSettings, "value",
                        lambda *a, **k: "not a number")
    assert ai_memory.budget() == ai_memory.DEFAULT_BUDGET


# -- images ----------------------------------------------------------------
def _with_image(text, kb=40):
    return {"role": "user", "content": text,
            "images": [{"media_type": "image/png", "data": "A" * (kb * 1024)}]}


def test_old_screenshots_are_dropped_before_any_text():
    """One pasted screenshot outweighs the whole written conversation, so
    evicting turns first would throw away the reasoning to keep a picture."""
    history = ([_with_image("here is the plot")]
               + _turns(8, size=50)
               + [{"role": "user", "content": "and now?"}])
    kept = ai_memory.trim(history, limit=2_000)

    assert len(kept) == len(history)            # every turn survived
    assert not kept[0].get("images")            # but the payload did not
    assert "here is the plot" in kept[0]["content"]
    assert ai_memory.IMAGE_NOTE in kept[0]["content"]


def test_the_newest_turns_image_is_kept():
    """Dropping the image the user just pasted would answer the wrong
    question."""
    history = _turns(4, size=50) + [_with_image("what is this?", kb=1)]
    kept = ai_memory.trim(history, limit=3_000)
    assert kept[-1].get("images")


# -- persistence -----------------------------------------------------------
def test_a_conversation_survives_a_restart(_own_store):
    history = [{"role": "user", "content": "fit the Fe2p"},
               {"role": "assistant", "content": "here is the code"}]
    ai_memory.save(history)
    assert ai_memory.load() == history


def test_image_payloads_are_not_written_to_disk(_own_store):
    """Megabytes of base64 in the profile folder, rarely wanted again."""
    ai_memory.save([_with_image("look")])
    raw = _own_store.read_text(encoding="utf-8")
    assert "AAAA" not in raw
    assert _own_store.stat().st_size < 4096
    assert ai_memory.IMAGE_NOTE in ai_memory.load()[0]["content"]


def test_what_is_saved_is_already_within_the_window(_own_store, qapp):
    before = ai_memory.budget()
    try:
        ai_memory.set_budget(2_000)
        ai_memory.save(_turns(400, size=100))
        assert sum(len(t["content"]) for t in ai_memory.load()) <= 2_000
    finally:
        ai_memory.set_budget(before)


def test_no_saved_conversation_is_not_an_error(_own_store):
    assert ai_memory.load() == []


def test_a_corrupt_file_is_ignored_not_raised(_own_store):
    _own_store.parent.mkdir(parents=True, exist_ok=True)
    _own_store.write_text("{ not json", encoding="utf-8")
    assert ai_memory.load() == []


def test_junk_turns_are_filtered_out(_own_store):
    _own_store.parent.mkdir(parents=True, exist_ok=True)
    _own_store.write_text(json.dumps({"version": 1, "turns": [
        {"role": "user", "content": "keep me"},
        {"role": "system", "content": "not a chat turn"},
        "a bare string",
    ]}), encoding="utf-8")
    assert ai_memory.load() == [{"role": "user", "content": "keep me"}]


def test_forget_clears_the_saved_conversation(_own_store):
    ai_memory.save([{"role": "user", "content": "hello"}])
    ai_memory.forget()
    assert ai_memory.load() == []
    ai_memory.forget()                          # already gone: still fine


def test_saving_into_an_unwritable_place_does_not_break_the_chat(monkeypatch):
    monkeypatch.setattr(ai_memory, "path",
                        lambda: __import__("pathlib").Path("\0bad/x.json"))
    ai_memory.save([{"role": "user", "content": "hi"}])   # must not raise
    assert ai_memory.load() == []


# -- the dock uses it ------------------------------------------------------
def test_the_dock_restores_and_stores_the_conversation(qapp, _own_store):
    from khervebook.ai_chat import AIChatDock
    from khervebook.notebook import NotebookWidget

    ai_memory.save([{"role": "user", "content": "earlier question"},
                    {"role": "assistant", "content": "earlier answer"}])

    dock = AIChatDock(NotebookWidget())
    assert [t["content"] for t in dock._history] == ["earlier question",
                                                     "earlier answer"]

    dock._on_done("a fresh answer")
    assert ai_memory.load()[-1]["content"] == "a fresh answer"

    dock._clear()
    assert dock._history == []
    assert ai_memory.load() == []
