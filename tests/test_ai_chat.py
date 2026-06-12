"""AI chat tests: fence parsing, request shapes, cell insertion.

No network — providers are exercised at the request-building layer.

Copyright (C) 2026 Gwilherm Kerherve

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.
"""

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


def test_extract_cells_ignores_unknown_languages():
    assert extract_cells("```bash\nls\n```") == []
    assert extract_cells("no fences at all") == []


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


def test_system_prompt_mentions_notebook(qapp):
    from khervebook.notebook import NotebookWidget
    nb = NotebookWidget()
    nb.cells[0].set_source("x = 42")
    prompt = build_system_prompt(nb)
    assert "KherveBook" in prompt
    assert "x = 42" in prompt
    assert "```python" in prompt


def test_insert_cells_into_notebook(qapp):
    from khervebook.ai_chat import AIChatDock
    from khervebook.notebook import NotebookWidget
    nb = NotebookWidget()
    dock = AIChatDock(nb)
    dock._on_done("```python\ny = 2\n```\n```markdown\nhello\n```")
    assert dock.insert_btn.isVisibleTo(dock)
    n = len(nb.cells)
    dock._insert_cells()
    assert len(nb.cells) == n + 2
    assert nb.cells[-1].CELL_TYPE == "markdown"
    assert nb.cells[-2].source() == "y = 2"
