"""AI chat tests: fence parsing, request shapes, cell insertion.

No network — providers are exercised at the request-building layer.

Copyright (C) 2026 Gwilherm Kerherve

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.
"""

from khervebook import ai_providers as prov
from khervebook.ai_chat import build_system_prompt, extract_cells
from khervebook.ai_providers import (PROVIDERS, build_request,
                                     parse_response)


def test_extract_cells_kinds():
    reply = (
        "Here you go:\n"
        "```markdown\n# Title\n```\n"
        "```python\nx = 1\nx\n```\n"
        "Some prose.\n"
        "```latex\nE = mc^2\n```\n"
        "```sheet\n{\"rows\": 2, \"cols\": 1, \"data\": {}}\n```\n")
    cells = extract_cells(reply)
    assert [c["type"] for c in cells] == ["markdown", "code", "latex",
                                          "sheet"]
    assert cells[1]["source"] == "x = 1\nx"
    assert all(c["target"] is None for c in cells)     # all are new cells


def test_extract_cells_ignores_unknown_and_svg():
    assert extract_cells("```bash\nls\n```") == []
    assert extract_cells("no fences at all") == []
    # the assistant must never write a drawing; svg fences are dropped
    assert extract_cells("```svg\n<svg/>\n```") == []


def test_extract_cells_targets_existing_cell():
    cells = extract_cells("```python cell=3\ny = 9\n```")
    assert cells == [{"type": "code", "source": "y = 9", "target": 3}]
    # tolerant of phrasing
    assert extract_cells("```markdown 0\nhi\n```")[0]["target"] == 0


def test_build_request_anthropic():
    cfg = {"api": "anthropic", "key": "K", "model": "claude-sonnet-4-6",
           "host": "https://api.anthropic.com"}
    url, headers, payload = build_request(
        cfg, "SYS", [{"role": "user", "content": "hi"}])
    assert url.endswith("/v1/messages")
    assert headers["x-api-key"] == "K"
    assert payload["system"] == "SYS"
    assert payload["messages"] == [{"role": "user", "content": "hi"}]


def test_build_request_openai_style():
    for name in ("openai", "mistral", "local"):
        meta = PROVIDERS[name]
        cfg = {"api": meta["api"], "key": "K", "model": "m",
               "host": meta["host"]}
        url, headers, payload = build_request(cfg, "SYS", [])
        assert url.endswith("/chat/completions")
        assert headers["Authorization"] == "Bearer K"
        assert payload["messages"][0] == {"role": "system",
                                          "content": "SYS"}


def test_build_request_ollama():
    cfg = {"api": "ollama", "key": "", "model": "llama3.2",
           "host": "http://localhost:11434"}
    url, headers, payload = build_request(cfg, "SYS", [])
    assert url.endswith("/api/chat")
    assert payload["stream"] is False
    assert "Authorization" not in headers


def test_parse_responses():
    assert parse_response("anthropic", {"content": [
        {"type": "text", "text": "a"}, {"type": "text", "text": "b"}]}) \
        == "ab"
    assert parse_response("openai", {"choices": [
        {"message": {"content": "hi"}}]}) == "hi"
    assert parse_response("ollama", {"message": {"content": "yo"}}) == "yo"


def test_providers_refreshable_and_available():
    assert all(meta.get("refreshable") for meta in PROVIDERS.values())
    assert all(prov.is_available(name) for name in PROVIDERS)
    assert not prov.is_available("nope")


def test_fetch_models_anthropic(monkeypatch):
    monkeypatch.setattr(prov, "_get_json", lambda url, headers: {
        "data": [{"id": "claude-z"}, {"id": "claude-a"}]})
    assert prov.fetch_models("anthropic", "K") == ["claude-a", "claude-z"]


def test_fetch_models_ollama(monkeypatch):
    monkeypatch.setattr(prov, "_get_json", lambda url, headers: {
        "models": [{"name": "qwen2.5-coder"}, {"name": "llama3.2"}]})
    assert prov.fetch_models("ollama", host="http://h") == [
        "llama3.2", "qwen2.5-coder"]


def test_fetch_models_openai_filters_chat_models(monkeypatch):
    monkeypatch.setattr(prov, "_get_json", lambda url, headers: {
        "data": [{"id": "gpt-4o"}, {"id": "text-embedding-3"},
                 {"id": "o1-mini"}]})
    assert prov.fetch_models("openai", "K") == ["gpt-4o", "o1-mini"]


def test_chat_input_history_up_down(qapp):
    from khervebook.ai_chat import _ChatInput
    inp = _ChatInput()
    inp.clear_history()                       # ignore any persisted history
    inp.add_history("first message")
    inp.add_history("second message")
    inp.setPlainText("a draft")
    inp._history_prev()                        # Up -> newest
    assert inp.toPlainText() == "second message"
    inp._history_prev()                        # Up -> older
    assert inp.toPlainText() == "first message"
    inp._history_prev()                        # at oldest, stays put
    assert inp.toPlainText() == "first message"
    inp._history_next()                        # Down -> newer
    assert inp.toPlainText() == "second message"
    inp._history_next()                        # Down past newest -> the draft
    assert inp.toPlainText() == "a draft"


def test_chat_input_up_arrow_at_first_line_recalls(qapp):
    from PyQt5.QtCore import QEvent, Qt
    from PyQt5.QtGui import QKeyEvent

    from khervebook.ai_chat import _ChatInput
    inp = _ChatInput()
    inp.clear_history()
    inp.add_history("hello world")
    inp.setPlainText("")                       # empty -> on the first line
    inp.keyPressEvent(QKeyEvent(QEvent.KeyPress, Qt.Key_Up, Qt.NoModifier))
    assert inp.toPlainText() == "hello world"
    # Enter still sends.
    fired = []
    inp.send.connect(lambda: fired.append(1))
    inp.keyPressEvent(QKeyEvent(QEvent.KeyPress, Qt.Key_Return, Qt.NoModifier))
    assert fired == [1]


def test_chat_input_history_persists(qapp):
    from khervebook.ai_chat import _ChatInput
    inp = _ChatInput()
    inp.clear_history()
    inp.add_history("remembered")
    inp2 = _ChatInput()                        # a fresh input loads from settings
    assert "remembered" in inp2._history
    inp2.clear_history()                       # tidy up the shared store


def test_dock_greeting_title_and_font(qapp):
    from khervebook.ai_chat import GREETING, AIChatDock
    from khervebook.notebook import NotebookWidget
    dock = AIChatDock(NotebookWidget())
    assert "AI Assistant" in dock.title.text()
    assert "·" in dock.title.text()                    # provider · model
    assert GREETING[:24] in dock.view.toPlainText()    # greeting shown
    dock._font_pt = 10.0                               # deterministic start
    dock._change_font(+2)
    assert dock._font_pt == 12.0                       # zoom changes size
    dock._change_font(-2)                              # leave the store at 10
    dock._history = [{"role": "user", "content": "hi"}]
    dock._render_all()
    dock._clear()                                      # clears + re-greets
    assert dock._history == []
    assert GREETING[:24] in dock.view.toPlainText()


def test_settings_model_combo_lists_models(qapp):
    from khervebook.ai_chat import ApiKeyDialog
    dlg = ApiKeyDialog(provider="anthropic")
    items = [dlg.model.itemText(i) for i in range(dlg.model.count())]
    assert "claude-opus-4-8" in items and "claude-sonnet-4-6" in items
    assert dlg.model.count() >= 5                       # a real list, not 1-2
    # switching provider repopulates the dropdown
    dlg.provider.setCurrentIndex(list(PROVIDERS).index("openai"))
    openai_items = [dlg.model.itemText(i) for i in range(dlg.model.count())]
    assert "gpt-4o" in openai_items
    assert "claude-opus-4-8" not in openai_items


def test_every_provider_lists_models_or_is_local():
    for name, meta in PROVIDERS.items():
        # all but the bare "local" server ship a starter model list
        assert meta["models"] or name == "local"


def test_settings_dialog_matches_khervesheet(qapp):
    from khervebook.ai_chat import ApiKeyDialog
    dlg = ApiKeyDialog(provider="anthropic")
    assert dlg.windowTitle() == "AI Chat Settings"
    assert dlg.refresh_btn.isVisibleTo(dlg)              # ⟳ refresh present
    assert dlg.key.isVisibleTo(dlg)
    assert not dlg.host.isVisibleTo(dlg)                 # Anthropic: no host
    assert "console.anthropic.com" in dlg.help_label.text()
    assert dlg.help_group.title() == "How to get an API key"
    # Ollama: key hidden, host shown, help retitled.
    dlg.provider.setCurrentIndex(list(PROVIDERS).index("ollama"))
    assert dlg.host.isVisibleTo(dlg) and not dlg.key.isVisibleTo(dlg)
    assert dlg.help_group.title() == "How to set up"


def test_system_prompt_includes_full_cell_content(qapp):
    from khervebook.notebook import NotebookWidget
    nb = NotebookWidget()
    nb.cells[0].set_source("x = 42\nprint(x * 2)")     # full body, not a snippet
    prompt = build_system_prompt(nb)
    assert "KherveBook" in prompt
    assert "x = 42" in prompt and "print(x * 2)" in prompt
    assert "```python" in prompt
    assert "never" in prompt.lower() and "svg" in prompt.lower()


def test_system_prompt_marks_svg_unreadable(qapp):
    from khervebook.notebook import NotebookWidget
    nb = NotebookWidget()
    nb.add_cell("svg", "<svg><rect/></svg>")
    prompt = build_system_prompt(nb)
    assert "cannot read or edit" in prompt
    assert "<rect/>" not in prompt                      # svg body not exposed


def _dock(nb):
    """A dock with Auto off, for tests that apply manually."""
    from khervebook.ai_chat import AIChatDock
    dock = AIChatDock(nb)
    dock.auto_btn.setChecked(False)
    return dock


def test_insert_cells_into_notebook(qapp):
    from khervebook.notebook import NotebookWidget
    nb = NotebookWidget()
    dock = _dock(nb)
    dock._on_done("```python\ny = 2\n```\n```markdown\nhello\n```")
    assert dock.insert_btn.isVisibleTo(dock)
    n = len(nb.cells)
    dock._insert_cells()
    assert len(nb.cells) == n + 2
    assert nb.cells[-1].CELL_TYPE == "markdown"
    assert nb.cells[-2].source() == "y = 2"


def test_apply_runs_the_code(qapp):
    """Applying does the task: the code cell is executed, not just added."""
    from khervebook.notebook import NotebookWidget
    nb = NotebookWidget()
    dock = _dock(nb)
    dock._on_done("```python\nspam = 6 * 7\n```")
    dock._insert_cells()
    assert nb.kernel.namespace.get("spam") == 42        # it actually ran


def test_auto_apply_runs_on_reply(qapp):
    """With Auto on, the assistant's cells apply and run without a click."""
    from khervebook.notebook import NotebookWidget
    nb = NotebookWidget()
    dock = _dock(nb)
    dock.auto_btn.setChecked(True)
    try:
        dock._on_done("```python\nauto_ran = 99\n```")
        assert nb.kernel.namespace.get("auto_ran") == 99
        assert not dock.insert_btn.isVisible()          # nothing left to apply
    finally:
        dock.auto_btn.setChecked(False)


def test_extract_cells_preserves_indentation(qapp):
    src = "def f():\n    if True:\n        return 1\n    return 0"
    out = extract_cells(f"```python\n{src}\n```")
    assert out[0]["source"] == src                       # faithful, not mangled


def test_ai_replaces_targeted_cell_undoably(qapp):
    from khervebook.notebook import NotebookWidget
    nb = NotebookWidget()
    nb.cells[0].set_source("old = 1")
    dock = _dock(nb)
    dock._on_done("```python cell=0\nnew = 2\n```")
    n = len(nb.cells)
    dock._insert_cells()
    assert len(nb.cells) == n                           # replaced, not added
    assert nb.cells[0].source() == "new = 2"
    nb.undo()                                            # one step reverts it
    assert nb.cells[0].source() == "old = 1"


def test_ai_never_overwrites_svg_cell(qapp):
    from khervebook.notebook import NotebookWidget
    nb = NotebookWidget()
    nb.add_cell("svg", "<svg/>")
    svg_index = len(nb.cells) - 1
    dock = _dock(nb)
    # the model wrongly targets the drawing cell -> appended instead
    dock._on_done(f"```python cell={svg_index}\nz = 3\n```")
    dock._insert_cells()
    assert nb.cells[svg_index].CELL_TYPE == "svg"
    assert nb.cells[svg_index].source() == "<svg/>"     # untouched
    assert any(c.CELL_TYPE == "code" and c.source() == "z = 3"
               for c in nb.cells)
