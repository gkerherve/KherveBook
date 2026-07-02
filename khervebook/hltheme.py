"""Syntax-highlight colour themes for Python code cells.

A theme names a colour per token category (keyword, string, comment,
...) plus the editor background/foreground. "Auto (app theme)" keeps
the built-in palette that follows the app's light/dark theme; the
named themes pin a classic editor scheme regardless of the app theme.
The choice persists app-wide via QSettings and is offered in the code
editor's right-click menu.

Copyright (C) 2026 Gwilherm Kerherve

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.
"""

from PyQt5.QtCore import QSettings

_SETTINGS = ("Kherve", "KherveBook")
_KEY = "editor/highlight_theme"

#: Sentinel theme: follow the app theme with the built-in palettes.
AUTO = "Auto (app theme)"

#: Built-in token colours per app-theme brightness (VS Code-ish).
AUTO_LIGHT = {
    "keyword": "#0000ff", "control": "#af00db", "constant": "#0070c1",
    "builtin": "#267f99", "decorator": "#b5730a", "defname": "#795e26",
    "classname": "#267f99", "call": "#795e26", "selfcls": "#0e8a9c",
    "number": "#098658", "string": "#a31515", "comment": "#6e7781",
}
AUTO_DARK = {
    "keyword": "#569cd6", "control": "#c586c0", "constant": "#569cd6",
    "builtin": "#4ec9b0", "decorator": "#dcdcaa", "defname": "#dcdcaa",
    "classname": "#4ec9b0", "call": "#dcdcaa", "selfcls": "#9cdcfe",
    "number": "#b5cea8", "string": "#ce9178", "comment": "#6a9955",
}

#: Explicit themes: token colours + "bg"/"fg" restyling the editor.
THEMES = {
    "Monokai": {
        "bg": "#272822", "fg": "#f8f8f2",
        "keyword": "#f92672", "control": "#f92672", "constant": "#ae81ff",
        "builtin": "#66d9ef", "decorator": "#a6e22e", "defname": "#a6e22e",
        "classname": "#66d9ef", "call": "#a6e22e", "selfcls": "#fd971f",
        "number": "#ae81ff", "string": "#e6db74", "comment": "#75715e",
    },
    "Dracula": {
        "bg": "#282a36", "fg": "#f8f8f2",
        "keyword": "#ff79c6", "control": "#ff79c6", "constant": "#bd93f9",
        "builtin": "#8be9fd", "decorator": "#50fa7b", "defname": "#50fa7b",
        "classname": "#8be9fd", "call": "#50fa7b", "selfcls": "#ffb86c",
        "number": "#bd93f9", "string": "#f1fa8c", "comment": "#6272a4",
    },
    "One Dark": {
        "bg": "#282c34", "fg": "#abb2bf",
        "keyword": "#c678dd", "control": "#c678dd", "constant": "#d19a66",
        "builtin": "#56b6c2", "decorator": "#61afef", "defname": "#61afef",
        "classname": "#e5c07b", "call": "#61afef", "selfcls": "#e06c75",
        "number": "#d19a66", "string": "#98c379", "comment": "#5c6370",
    },
    "Nord": {
        "bg": "#2e3440", "fg": "#d8dee9",
        "keyword": "#81a1c1", "control": "#81a1c1", "constant": "#81a1c1",
        "builtin": "#88c0d0", "decorator": "#d08770", "defname": "#88c0d0",
        "classname": "#8fbcbb", "call": "#88c0d0", "selfcls": "#81a1c1",
        "number": "#b48ead", "string": "#a3be8c", "comment": "#616e88",
    },
    "Solarized Light": {
        "bg": "#fdf6e3", "fg": "#657b83",
        "keyword": "#859900", "control": "#859900", "constant": "#cb4b16",
        "builtin": "#268bd2", "decorator": "#b58900", "defname": "#268bd2",
        "classname": "#b58900", "call": "#268bd2", "selfcls": "#d33682",
        "number": "#2aa198", "string": "#2aa198", "comment": "#93a1a1",
    },
    "Solarized Dark": {
        "bg": "#002b36", "fg": "#839496",
        "keyword": "#859900", "control": "#859900", "constant": "#cb4b16",
        "builtin": "#268bd2", "decorator": "#b58900", "defname": "#268bd2",
        "classname": "#b58900", "call": "#268bd2", "selfcls": "#d33682",
        "number": "#2aa198", "string": "#2aa198", "comment": "#586e75",
    },
    "GitHub Light": {
        "bg": "#ffffff", "fg": "#24292f",
        "keyword": "#cf222e", "control": "#cf222e", "constant": "#0550ae",
        "builtin": "#8250df", "decorator": "#8250df", "defname": "#8250df",
        "classname": "#953800", "call": "#8250df", "selfcls": "#0550ae",
        "number": "#0550ae", "string": "#0a3069", "comment": "#6e7781",
    },
}


def theme_names() -> list:
    return [AUTO] + list(THEMES)


def saved_name() -> str:
    name = QSettings(*_SETTINGS).value(_KEY, AUTO)
    return name if name in THEMES else AUTO


def save_name(name: str):
    QSettings(*_SETTINGS).setValue(_KEY, name)


def resolve(name: str, dark: bool = False) -> dict:
    """Token-colour dict for theme *name* (AUTO follows the app theme)."""
    if name in THEMES:
        return THEMES[name]
    return AUTO_DARK if dark else AUTO_LIGHT


def editor_colors(name: str):
    """(background, foreground) for an explicit theme, or None when the
    editor should keep the app theme's stylesheet."""
    t = THEMES.get(name)
    return (t["bg"], t["fg"]) if t else None
