"""Mode-specific cell toolbar.

A second toolbar row whose contents follow the focused cell's type:
Markdown cells get text-formatting tools (headings, emphasis, lists,
alignment, colour, highlight), code cells get Python editing tools
(run, comment, indent, snippets) and LaTeX cells get equation
building blocks (fractions, scripts, operators, Greek letters).

Copyright (C) 2026 Gwilherm Kerherve

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.
"""

from PyQt5.QtCore import QSize
from PyQt5.QtGui import QTextCursor
from PyQt5.QtWidgets import (QAction, QColorDialog, QMenu, QToolBar,
                             QToolButton)

from .icons import icon

#: LaTeX building blocks: (toolbar label, tooltip, snippet).
#: "|" in the snippet marks where the cursor should land.
LATEX_SNIPPETS = [
    ("a⁄b", "Fraction", r"\frac{|}{}"),
    ("√",  "Square root", r"\sqrt{|}"),
    ("xⁿ", "Superscript", r"^{|}"),
    ("xₙ", "Subscript", r"_{|}"),
    ("Σ",  "Sum", r"\sum_{i=1}^{n} |"),
    ("∫",  "Integral", r"\int_{a}^{b} | \, dx"),
    ("lim", "Limit", r"\lim_{x \to \infty} |"),
]

GREEK = ("alpha beta gamma delta epsilon theta lambda mu pi rho sigma "
         "tau phi chi psi omega Gamma Delta Theta Lambda Pi Sigma Phi "
         "Psi Omega").split()

OPERATORS = [
    ("±", r"\pm"), ("×", r"\times"), ("·", r"\cdot"), ("÷", r"\div"),
    ("≤", r"\leq"), ("≥", r"\geq"), ("≠", r"\neq"), ("≈", r"\approx"),
    ("→", r"\rightarrow"), ("∂", r"\partial"), ("∇", r"\nabla"),
    ("∞", r"\infty"),
]

#: Ready-to-insert Python snippets for code cells.
PY_SNIPPETS = {
    "Imports (numpy, matplotlib)":
        "import numpy as np\nimport matplotlib.pyplot as plt\n",
    "Line plot":
        "x = np.linspace(0, 2 * np.pi, 200)\n"
        "plt.plot(x, np.sin(x))\n"
        "plt.xlabel('x'); plt.ylabel('sin(x)')\n"
        "plt.gcf()",
    "Histogram":
        "data = np.random.normal(size=1000)\n"
        "plt.hist(data, bins=30)\n"
        "plt.gcf()",
    "Define a function":
        "def my_func(x):\n    return x * 2\n",
    "DataFrame preview":
        "df = pd.DataFrame({'x': range(5), 'y': range(5)})\ndf",
}


class CellToolBar(QToolBar):
    """Toolbar whose actions adapt to the focused cell's type."""

    def __init__(self, notebook, parent=None):
        super().__init__("Cell tools", parent)
        self.setMovable(False)
        self.setIconSize(QSize(32, 32))
        self._notebook = notebook
        self.set_mode("code")

    # -- mode switching ---------------------------------------------------
    def set_mode(self, cell_type: str):
        self.clear()
        build = {"markdown": self._build_markdown,
                 "latex": self._build_latex,
                 "sheet": self._build_sheet}.get(cell_type, self._build_code)
        build()

    # -- editor helpers ---------------------------------------------------
    def _editor(self):
        cell = self._notebook.current
        return cell.editor if cell is not None else None

    def _wrap(self, before: str, after: str, placeholder: str = "text"):
        """Wrap the selection (or *placeholder*) in before/after."""
        ed = self._editor()
        if ed is None:
            return
        cur = ed.textCursor()
        sel = cur.selectedText() or placeholder
        cur.insertText(before + sel + after)
        # Leave the wrapped text selected so chained styles compose.
        cur.setPosition(cur.position() - len(after) - len(sel))
        cur.setPosition(cur.position() + len(sel), QTextCursor.KeepAnchor)
        ed.setTextCursor(cur)
        ed.setFocus()

    def _insert(self, snippet: str):
        """Insert *snippet*, placing the cursor at the "|" marker."""
        ed = self._editor()
        if ed is None:
            return
        back = 0
        if "|" in snippet:
            back = len(snippet) - snippet.index("|") - 1
            snippet = snippet.replace("|", "", 1)
        cur = ed.textCursor()
        cur.insertText(snippet)
        cur.setPosition(cur.position() - back)
        ed.setTextCursor(cur)
        ed.setFocus()

    def _selected_blocks(self, cursor):
        doc = self._editor().document()
        start = doc.findBlock(cursor.selectionStart()).blockNumber()
        end = doc.findBlock(cursor.selectionEnd()).blockNumber()
        return start, end

    def _apply_per_line(self, fn):
        """Rewrite each selected line through *fn(line) -> line*."""
        ed = self._editor()
        if ed is None:
            return
        doc = ed.document()
        cur = ed.textCursor()
        s, e = self._selected_blocks(cur)
        cur.beginEditBlock()
        for bn in range(s, e + 1):
            block = doc.findBlockByNumber(bn)
            edit = QTextCursor(block)
            edit.select(QTextCursor.LineUnderCursor)
            edit.insertText(fn(block.text()))
        cur.endEditBlock()
        ed.setFocus()

    # -- action helpers ----------------------------------------------------
    def _add(self, text, tip, slot, icon_name=None, color=None):
        act = QAction(text, self)
        if icon_name:
            act.setIcon(icon(icon_name, color) if color else icon(icon_name))
        act.setToolTip(tip)
        act.triggered.connect(slot)
        self.addAction(act)
        return act

    def _add_menu(self, text, tip, entries, icon_name=None):
        """Add a dropdown button; *entries* is [(label, slot), ...]."""
        btn = QToolButton()
        btn.setText(text)
        btn.setToolTip(tip)
        if icon_name:
            btn.setIcon(icon(icon_name))
        btn.setPopupMode(QToolButton.InstantPopup)
        menu = QMenu(btn)
        for label, slot in entries:
            menu.addAction(label).triggered.connect(
                lambda _=False, s=slot: s())
        btn.setMenu(menu)
        self.addWidget(btn)

    # -- markdown mode ------------------------------------------------------
    def _build_markdown(self):
        self._add_menu("H", "Heading level", [
            (f"H{n}  {'#' * n} heading", lambda n=n: self._apply_per_line(
                lambda ln, n=n: "#" * n + " " + ln.lstrip("# ")))
            for n in (1, 2, 3)
        ], icon_name="mdi.format-header-pound")
        self._add("Bold", "Bold (**text**)",
                  lambda: self._wrap("**", "**"), "mdi.format-bold")
        self._add("Italic", "Italic (*text*)",
                  lambda: self._wrap("*", "*"), "mdi.format-italic")
        self._add("Strike", "Strikethrough (~~text~~)",
                  lambda: self._wrap("~~", "~~"),
                  "mdi.format-strikethrough-variant")
        self._add("Code", "Inline code (`text`)",
                  lambda: self._wrap("`", "`", "code"), "mdi.code-tags")
        self.addSeparator()
        self._add("Bullets", "Bulleted list",
                  lambda: self._apply_per_line(lambda ln: "- " + ln),
                  "mdi.format-list-bulleted")
        self._add("Numbers", "Numbered list",
                  lambda: self._apply_per_line(lambda ln: "1. " + ln),
                  "mdi.format-list-numbered")
        self._add("Quote", "Block quote",
                  lambda: self._apply_per_line(lambda ln: "> " + ln),
                  "mdi.format-quote-close")
        self._add("Link", "Insert a link",
                  lambda: self._insert("[text](|https://)"),
                  "mdi.link-variant")
        self.addSeparator()
        for side in ("left", "center", "right"):
            self._add(side.title(), f"Align {side}",
                      lambda _=False, s=side: self._wrap(
                          f'<p align="{s}">', "</p>"),
                      f"mdi.format-align-{side}")
        self.addSeparator()
        self._add("Color", "Text colour…", self._pick_color,
                  "mdi.format-color-text")
        self._add("Highlight", "Highlight…", self._pick_highlight,
                  "mdi.format-color-highlight")
        self._add("Comment", "Comment out — <!-- … --> (Ctrl+/)",
                  self._editor_comment, "mdi.comment-text-outline")
        self.addSeparator()
        self._add("Render", "Render the cell (Shift+Enter)",
                  self._notebook.run_current, "mdi.eye-outline")

    def _editor_comment(self):
        cell = self._notebook.current
        if cell is not None:
            cell.editor.toggle_comment()

    def _pick_color(self):
        color = QColorDialog.getColor(parent=self.window(),
                                      title="Text colour")
        if color.isValid():
            self._wrap(f'<span style="color:{color.name()}">', "</span>")

    def _pick_highlight(self):
        color = QColorDialog.getColor(parent=self.window(),
                                      title="Highlight colour")
        if color.isValid():
            self._wrap(
                f'<span style="background-color:{color.name()}">', "</span>")

    # -- code (Python) mode --------------------------------------------------
    def _build_code(self):
        self._add("Run", "Run the cell (Shift+Enter)",
                  self._notebook.run_current, "mdi.play", color="#27ae60")
        self.addSeparator()
        self._add("Comment", "Toggle line comments",
                  self._toggle_comment, "mdi.comment-text-outline")
        self._add("Indent", "Indent selected lines",
                  lambda: self._apply_per_line(lambda ln: "    " + ln),
                  "mdi.format-indent-increase")
        self._add("Dedent", "Dedent selected lines",
                  lambda: self._apply_per_line(self._dedent_line),
                  "mdi.format-indent-decrease")
        self.addSeparator()
        self._add_menu("Snippets", "Insert a code snippet",
                       [(name, lambda b=body: self._insert(b))
                        for name, body in PY_SNIPPETS.items()],
                       icon_name="mdi.code-braces")

    @staticmethod
    def _dedent_line(ln):
        for pre in ("    ", "\t", "   ", "  ", " "):
            if ln.startswith(pre):
                return ln[len(pre):]
        return ln

    def _toggle_comment(self):
        ed = self._editor()
        if ed is None:
            return
        doc = ed.document()
        s, e = self._selected_blocks(ed.textCursor())
        lines = [doc.findBlockByNumber(bn).text() for bn in range(s, e + 1)]
        non_empty = [ln for ln in lines if ln.strip()]
        commented = non_empty and all(
            ln.lstrip().startswith("#") for ln in non_empty)
        if commented:
            self._apply_per_line(
                lambda ln: ln.replace("# ", "", 1) if "# " in ln
                else ln.replace("#", "", 1) if "#" in ln else ln)
        else:
            self._apply_per_line(lambda ln: ("# " + ln) if ln.strip() else ln)

    # -- sheet mode -----------------------------------------------------------
    def _sheet_op(self, name):
        cell = self._notebook.current
        if cell is not None and hasattr(cell, name):
            getattr(cell, name)()

    def _build_sheet(self):
        self._add("Run", "Recompute all =formulas (Shift+Enter)",
                  self._notebook.run_current, "mdi.play", color="#27ae60")
        self.addSeparator()
        self._add("Add row", "Add a row",
                  lambda: self._sheet_op("add_row"),
                  "mdi.table-row-plus-after")
        self._add("Add column", "Add a column",
                  lambda: self._sheet_op("add_col"),
                  "mdi.table-column-plus-after")
        self._add("Delete row", "Delete the selected row",
                  lambda: self._sheet_op("del_row"), "mdi.table-row-remove")
        self._add("Delete column", "Delete the selected column",
                  lambda: self._sheet_op("del_col"),
                  "mdi.table-column-remove")
        self.addSeparator()
        self._add("Add sheet", "Add another sheet to this workbook cell",
                  lambda: self._sheet_op("add_sheet"),
                  "mdi.table-plus")

    # -- LaTeX mode -----------------------------------------------------------
    def _build_latex(self):
        for label, tip, snippet in LATEX_SNIPPETS:
            self._add(label, tip,
                      lambda _=False, s=snippet: self._insert(s))
        self.addSeparator()
        self._add_menu("αβγ", "Greek letters",
                       [(f"{name}  (\\{name})",
                         lambda n=name: self._insert("\\" + n + " "))
                        for name in GREEK])
        self._add_menu("±≤∞", "Operators and symbols",
                       [(f"{sym}  ({cmd})",
                         lambda c=cmd: self._insert(c + " "))
                        for sym, cmd in OPERATORS])
        self.addSeparator()
        self._add("Comment", "Comment out — % (Ctrl+/)",
                  self._editor_comment, "mdi.comment-text-outline")
        self._add("Render", "Render the equation (Shift+Enter)",
                  self._notebook.run_current, "mdi.eye-outline")
