"""Conversation memory for the AI dock: a long window that survives a restart.

The chat used to keep every turn in a plain list and send the lot. That
reads as "unlimited memory" right up to the point where the provider
refuses the request for exceeding its context window — so a long working
session ended in an error instead of degrading. And because the list
lived only in the widget, closing KherveBook forgot the whole
conversation, however much of the analysis had been worked out in it.

So the window is large but bounded, and it is written to disk:

* ``trim()`` keeps the newest turns inside a character budget (~4 chars
  per token). Pasted screenshots are base64 and dwarf everything else, so
  their payloads are dropped from older turns *first* — losing an old
  screenshot to keep twenty turns of reasoning is the better trade.
* The result always starts on a user turn, since a history beginning
  mid-exchange is rejected by the messages APIs.
* ``save()`` / ``load()`` persist the conversation as JSON under the
  user's app-data folder, so it is still there tomorrow. Image payloads
  are not persisted — megabytes of base64 that the model rarely needs
  again — and are replaced by a note saying so.

Copyright (C) 2026 Gwilherm Kerherve

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.
"""

import json
from pathlib import Path

from PyQt5.QtCore import QSettings, QStandardPaths

_SETTINGS = ("Kherve", "KherveBook")
_KEY_BUDGET = "ai/memory_chars"

#: Characters of conversation to keep. At roughly 4 characters per token
#: this is ~100k tokens: most of a 200k-token model's window, leaving
#: room for the system prompt (the notebook listing, itself capped at
#: 20k chars) and the reply. Lower it for a small local model.
DEFAULT_BUDGET = 400_000

#: Left in place of a dropped screenshot so the turn still reads sensibly.
IMAGE_NOTE = "[image omitted to keep the conversation within memory]"


def budget() -> int:
    try:
        value = int(QSettings(*_SETTINGS).value(_KEY_BUDGET, DEFAULT_BUDGET))
    except (TypeError, ValueError):
        return DEFAULT_BUDGET
    return max(2_000, value)


def set_budget(chars: int):
    QSettings(*_SETTINGS).setValue(_KEY_BUDGET, int(chars))


def _cost(turn: dict) -> int:
    """Roughly what a turn costs the context window, in characters."""
    total = len(str(turn.get("content") or ""))
    for image in turn.get("images") or []:
        total += len(image.get("data") or "")
    return total


def _without_images(turn: dict) -> dict:
    """The same turn with its image payloads replaced by a note."""
    if not turn.get("images"):
        return turn
    text = str(turn.get("content") or "")
    stripped = dict(turn)
    stripped.pop("images", None)
    stripped["content"] = (f"{text}\n{IMAGE_NOTE}" if text else IMAGE_NOTE)
    return stripped


def trim(history, limit=None) -> list:
    """The newest turns of *history* that fit in *limit* characters.

    Older screenshots go before any text does, then whole turns from the
    oldest end. The result starts on a user turn so it is a valid
    conversation to resume from.
    """
    limit = budget() if limit is None else limit
    turns = list(history or [])

    # Shed old image payloads first — one screenshot can outweigh the
    # entire written conversation around it.
    total = sum(_cost(t) for t in turns)
    if total > limit:
        for i, turn in enumerate(turns[:-1]):      # keep the latest turn's
            if total <= limit:
                break
            if turn.get("images"):
                before = _cost(turn)
                turns[i] = _without_images(turn)
                total -= before - _cost(turns[i])

    # Then drop whole turns from the oldest end.
    while turns and sum(_cost(t) for t in turns) > limit and len(turns) > 1:
        turns.pop(0)

    # A history that opens mid-exchange is rejected by the messages APIs.
    while turns and turns[0].get("role") != "user":
        turns.pop(0)
    return turns


# ---------------------------------------------------------------------------
#  Persistence
# ---------------------------------------------------------------------------
def path() -> Path:
    """Where the conversation lives.

    GenericDataLocation plus an explicit app folder, not AppDataLocation:
    that one already folds in the application name, so it resolves
    somewhere different depending on whether QApplication has been named
    yet — and to the bare profile folder, shared with every sibling
    Kherve app, when it has not.
    """
    folder = QStandardPaths.writableLocation(
        QStandardPaths.GenericDataLocation)
    return Path(folder or ".") / "KherveBook" / "ai_conversation.json"


def save(history):
    """Write the conversation out, trimmed and without image payloads."""
    turns = [_without_images(t) for t in trim(history)]
    target = path()
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps({"version": 1, "turns": turns}),
                          encoding="utf-8")
    except (OSError, ValueError):
        pass            # a read-only or malformed profile path must not
        #                 break the chat — losing the transcript is bad,
        #                 losing the conversation you are having is worse


def load() -> list:
    """The saved conversation, or [] when there is none / it is unusable."""
    try:
        doc = json.loads(path().read_text(encoding="utf-8"))
    except (OSError, ValueError, UnicodeDecodeError):
        return []
    turns = doc.get("turns") if isinstance(doc, dict) else None
    if not isinstance(turns, list):
        return []
    clean = [t for t in turns
             if isinstance(t, dict) and t.get("role") in ("user", "assistant")]
    return trim(clean)


def forget():
    """Drop the saved conversation (the chat's Clear button)."""
    try:
        path().unlink()
    except (OSError, ValueError):
        pass
