"""AI chat providers — Claude, ChatGPT, Mistral, Ollama, Local.

Same provider set and settings scheme as KherveSheet, but speaking
plain HTTP (urllib) so no SDK packages are required. Anthropic uses
its messages API; OpenAI, Mistral and Local use the OpenAI-compatible
chat/completions shape; Ollama uses its native /api/chat.

Copyright (C) 2026 Gwilherm Kerherve

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.
"""

import json
import urllib.error
import urllib.request

from PyQt5.QtCore import QSettings

_MAX_TOKENS = 8192
_TIMEOUT = 120.0

PROVIDERS = {
    "anthropic": {
        "label": "Anthropic (Claude)",
        "api": "anthropic",
        "needs_key": True, "needs_host": False,
        "models": ["claude-sonnet-4-6", "claude-opus-4-8",
                   "claude-haiku-4-5-20251001"],
        "default_model": "claude-sonnet-4-6",
        "host": "https://api.anthropic.com",
    },
    "openai": {
        "label": "OpenAI (ChatGPT)",
        "api": "openai",
        "needs_key": True, "needs_host": False,
        "models": ["gpt-4o", "gpt-4o-mini"],
        "default_model": "gpt-4o",
        "host": "https://api.openai.com/v1",
    },
    "mistral": {
        "label": "Mistral AI",
        "api": "openai",
        "needs_key": True, "needs_host": False,
        "models": ["mistral-large-latest", "mistral-small-latest",
                   "codestral-latest"],
        "default_model": "mistral-large-latest",
        "host": "https://api.mistral.ai/v1",
    },
    "ollama": {
        "label": "Ollama (local)",
        "api": "ollama",
        "needs_key": False, "needs_host": True,
        "models": ["llama3.2", "qwen2.5-coder", "mistral"],
        "default_model": "llama3.2",
        "host": "http://localhost:11434",
    },
    "local": {
        "label": "Local AI (OpenAI-compatible)",
        "api": "openai",
        "needs_key": False, "needs_host": True,
        "models": [],
        "default_model": "",
        "host": "http://localhost:11434/v1",
    },
}

_SETTINGS = ("Kherve", "KherveBook")


# -- settings -----------------------------------------------------------

def load_config(provider: str) -> dict:
    """Provider config merged with the user's saved key/model/host."""
    s = QSettings(*_SETTINGS)
    base = PROVIDERS[provider]
    return {
        "provider": provider,
        "api": base["api"],
        "key": s.value(f"ai/key_{provider}", "") or "",
        "model": s.value(f"ai/model_{provider}",
                         base["default_model"]) or base["default_model"],
        "host": s.value(f"ai/{provider}_host", base["host"]) or base["host"],
    }


def save_config(provider: str, key: str, model: str, host: str):
    s = QSettings(*_SETTINGS)
    s.setValue(f"ai/key_{provider}", key)
    s.setValue(f"ai/model_{provider}", model)
    s.setValue(f"ai/{provider}_host", host)
    s.setValue("ai/provider", provider)


def saved_provider() -> str:
    name = QSettings(*_SETTINGS).value("ai/provider", "anthropic")
    return name if name in PROVIDERS else "anthropic"


# -- request building (pure; unit-testable) ------------------------------

def build_request(cfg: dict, system: str, history: list):
    """Return (url, headers, payload_dict) for one chat call.

    *history* is a list of {"role": "user"|"assistant", "content": str}.
    """
    api = cfg["api"]
    host = cfg["host"].rstrip("/")
    if api == "anthropic":
        url = f"{host}/v1/messages"
        headers = {
            "Content-Type": "application/json",
            "x-api-key": cfg["key"],
            "anthropic-version": "2023-06-01",
        }
        payload = {
            "model": cfg["model"],
            "max_tokens": _MAX_TOKENS,
            "system": system,
            "messages": history,
        }
    elif api == "ollama":
        url = f"{host}/api/chat"
        headers = {"Content-Type": "application/json"}
        payload = {
            "model": cfg["model"],
            "stream": False,
            "messages": [{"role": "system", "content": system}] + history,
        }
    else:                                   # openai-compatible
        url = f"{host}/chat/completions"
        headers = {"Content-Type": "application/json"}
        if cfg.get("key"):
            headers["Authorization"] = f"Bearer {cfg['key']}"
        payload = {
            "model": cfg["model"],
            "max_tokens": _MAX_TOKENS,
            "messages": [{"role": "system", "content": system}] + history,
        }
    return url, headers, payload


def parse_response(api: str, data: dict) -> str:
    if api == "anthropic":
        return "".join(b.get("text", "") for b in data.get("content", [])
                       if b.get("type") == "text")
    if api == "ollama":
        return (data.get("message") or {}).get("content", "")
    choices = data.get("choices") or [{}]
    return (choices[0].get("message") or {}).get("content", "")


def chat(cfg: dict, system: str, history: list) -> str:
    """One blocking chat call. Raises on HTTP/network errors."""
    url, headers, payload = build_request(cfg, system, history)
    req = urllib.request.Request(
        url, data=json.dumps(payload).encode("utf-8"),
        headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = ""
        try:
            detail = exc.read().decode("utf-8", "replace")[:300]
        except Exception:
            pass
        raise RuntimeError(f"HTTP {exc.code}: {detail or exc.reason}")
    return parse_response(cfg["api"], data)
