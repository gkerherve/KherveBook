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

#: Multi-line LaTeX snippets ("|" marks where the cursor lands).
LATEX_SKELETON = ("\\documentclass[12pt]{article}\n"
                  "\\usepackage{amsmath, amssymb}\n"
                  "\\begin{document}\n|\n\\end{document}")
LATEX_TITLE = ("\\title{\\textbf{|}}\n\\author{}\n\\date{}\n\\maketitle")
LATEX_ITEMIZE = ("\\begin{itemize}\n  \\item |\n  \\item \n\\end{itemize}")
LATEX_ENUMERATE = ("\\begin{enumerate}\n  \\item |\n  \\item "
                   "\n\\end{enumerate}")
LATEX_EQUATION = "\\begin{equation}\n|\n\\end{equation}"
LATEX_EQUATION_STAR = "\\begin{equation*}\n|\n\\end{equation*}"
LATEX_ALIGN = "\\begin{align}\n| &= \\\\\n  &= \n\\end{align}"
LATEX_TABLE = ("\\begin{tabular}{l l}\n\\hline\n| & \\\\\n\\hline\n"
               " & \\\\\n\\hline\n\\end{tabular}")
LATEX_FIGURE = ("\\begin{figure}[h]\n\\centering\n"
                "\\includegraphics[width=0.6\\textwidth]{|}\n"
                "\\caption{}\n\\end{figure}")

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
                 "note": self._build_note,
                 "latex": self._build_latex,
                 "sheet": self._build_sheet,
                 "svg": self._build_svg,
                 "file": self._build_file,
                 "kfit": self._build_kfit}.get(cell_type, self._build_code)
        build()

    # -- KFit (KherveFitting project) mode ------------------------------------
    def _kfit(self, method, *args):
        cell = self._notebook.current
        if cell is not None and cell.CELL_TYPE == "kfit" and hasattr(
                cell, method):
            getattr(cell, method)(*args)

    def _build_kfit(self):
        self._add("Load .kfit", "Open a KherveFitting project into this cell",
                  lambda: self._kfit("choose_file"),
                  "mdi.folder-open-outline")
        self.addSeparator()
        self._add("Plot", "Show the selected sheet as a plot",
                  lambda: self._kfit("show_plot"), "mdi.chart-bell-curve")
        self._add("Data", "Show the selected sheet as a table of numbers",
                  lambda: self._kfit("show_data"), "mdi.table")
        self.addSeparator()
        self._add("Open in KherveFitting",
                  "Edit this project in KherveFitting and reload on save",
                  lambda: self._kfit("open_in_khervefitting"),
                  "mdi.open-in-new")

    # -- note (rich text) mode ----------------------------------------------
    def _note(self, method, *args):
        """Call *method* on the focused Note cell, if it is one."""
        cell = self._notebook.current
        if cell is not None and cell.CELL_TYPE == "note" and hasattr(
                cell, method):
            getattr(cell, method)(*args)

    def _note_cell(self):
        cell = self._notebook.current
        return cell if (cell is not None and cell.CELL_TYPE == "note") \
            else None

    def _build_note(self):
        from PyQt5.QtCore import Qt
        from PyQt5.QtWidgets import QComboBox, QFontComboBox, QSpinBox

        font = QFontComboBox()
        font.setMaximumWidth(150)
        font.setToolTip("Font family")
        font.currentFontChanged.connect(
            lambda f: self._note("set_font_family", f.family()))
        self.addWidget(font)
        size = QSpinBox()
        size.setRange(6, 96)
        size.setValue(11)
        size.setToolTip("Font size")
        size.valueChanged.connect(lambda v: self._note("set_font_size", v))
        self.addWidget(size)
        heading = QComboBox()
        heading.addItems(["Body", "Heading 1", "Heading 2", "Heading 3"])
        heading.setToolTip("Paragraph style")
        heading.activated.connect(lambda i: self._note("set_heading", i))
        self.addWidget(heading)
        self.addSeparator()

        self._add("Bold", "Bold", lambda: self._note("toggle_bold"),
                  "mdi.format-bold")
        self._add("Italic", "Italic", lambda: self._note("toggle_italic"),
                  "mdi.format-italic")
        self._add("Underline", "Underline",
                  lambda: self._note("toggle_underline"),
                  "mdi.format-underline")
        self._add("Strike", "Strikethrough",
                  lambda: self._note("toggle_strike"),
                  "mdi.format-strikethrough-variant")
        self.addSeparator()
        self._add("Bullets", "Bulleted list",
                  lambda: self._note("bullet_list"),
                  "mdi.format-list-bulleted")
        self._add("Numbers", "Numbered list",
                  lambda: self._note("numbered_list"),
                  "mdi.format-list-numbered")
        for side, al in (("left", Qt.AlignLeft), ("center", Qt.AlignCenter),
                         ("right", Qt.AlignRight)):
            self._add(side.title(), f"Align {side}",
                      lambda _=False, a=al: self._note("set_align", a),
                      f"mdi.format-align-{side}")
        self.addSeparator()
        self._add("Color", "Text colour…", lambda: self._note("pick_color"),
                  "mdi.format-color-text")
        self._add("Highlight", "Highlight colour…",
                  lambda: self._note("pick_highlight"),
                  "mdi.format-color-highlight")
        self.addSeparator()

        # Pen / ink: a checkable toggle plus colour, width, undo and clear.
        cell = self._note_cell()
        pen = QAction(icon("mdi.draw"), "Pen", self)
        pen.setToolTip("Pen — write / annotate over the text")
        pen.setCheckable(True)
        pen.setChecked(bool(cell and cell.pen_active()))
        pen.toggled.connect(lambda on: self._note("set_pen", on))
        self.addAction(pen)
        self._add("Pen colour", "Pen colour…",
                  lambda: self._note("pick_ink_color"),
                  "mdi.format-color-fill")
        pen_w = QSpinBox()
        pen_w.setRange(1, 40)
        pen_w.setValue(3)
        pen_w.setToolTip("Pen width")
        pen_w.valueChanged.connect(lambda v: self._note("set_ink_width", v))
        self.addWidget(pen_w)
        self._add("Undo stroke", "Undo the last pen stroke",
                  lambda: self._note("ink_undo"), "mdi.undo")
        self._add("Clear ink", "Clear all pen strokes",
                  lambda: self._note("ink_clear"), "mdi.eraser")

    # -- file attachment mode -----------------------------------------------
    def _file(self, method):
        cell = self._notebook.current
        if cell is not None and cell.CELL_TYPE == "file" and hasattr(
                cell, method):
            getattr(cell, method)()

    def _build_file(self):
        self._add("Attach / Replace", "Choose the file to hold in the cell",
                  lambda: self._file("choose_file"), "mdi.paperclip")
        self.addSeparator()
        self._add("Open", "Open the attached file",
                  lambda: self._file("open_file"), "mdi.open-in-new")
        self._add("Save a copy", "Save the attached file elsewhere",
                  lambda: self._file("save_copy"), "mdi.content-save-outline")
        self._add("Copy reference", "Copy the kf(\"name\") code reference",
                  lambda: self._file("copy_reference"), "mdi.code-tags")

    # -- SVG (drawing) mode ---------------------------------------------------
    def _svg_cell(self):
        cell = self._notebook.current
        return cell if (cell is not None and cell.CELL_TYPE == "svg") \
            else None

    def _svg(self, method, *args):
        cell = self._svg_cell()
        if cell is not None and hasattr(cell, method):
            getattr(cell, method)(*args)

    def _build_svg(self):
        from PyQt5.QtWidgets import QActionGroup, QSpinBox
        from .svgcell import SvgCell
        cell = self._svg_cell()
        current = cell.current_tool() if cell else "select"
        group = QActionGroup(self)
        group.setExclusive(True)
        for key, icon_name, tip in SvgCell.TOOLS:
            act = QAction(icon(icon_name), key.title(), self)
            act.setToolTip(tip)
            act.setCheckable(True)
            act.setChecked(key == current)
            act.triggered.connect(
                lambda _=False, k=key: self._svg("set_tool", k))
            group.addAction(act)
            self.addAction(act)
        self.addSeparator()
        self._add("Colour", "Stroke / text colour…",
                  lambda: self._svg("pick_color"), "mdi.palette")
        width = QSpinBox()
        width.setRange(1, 40)
        width.setValue(3)
        width.setToolTip("Stroke / line width")
        width.valueChanged.connect(lambda v: self._svg("set_stroke_width", v))
        self.addWidget(width)
        self._add("Undo", "Undo the last drawn shape",
                  lambda: self._svg("undo_shape"), "mdi.undo")
        self.addSeparator()

        # Grid, snap-to-grid, grid spacing (unit) and canvas size.
        grid = QAction(icon("mdi.grid"), "Grid", self)
        grid.setToolTip("Show a grid over the canvas")
        grid.setCheckable(True)
        grid.setChecked(bool(cell and cell.grid_on()))
        grid.toggled.connect(lambda on: self._svg("set_show_grid", on))
        self.addAction(grid)
        snap = QAction(icon("mdi.magnet"), "Snap", self)
        snap.setToolTip("Snap drawing to the grid")
        snap.setCheckable(True)
        snap.setChecked(bool(cell and cell.snap_on()))
        snap.toggled.connect(lambda on: self._svg("set_snap", on))
        self.addAction(snap)
        unit = QSpinBox()
        unit.setRange(2, 500)
        unit.setValue(cell.grid_size() if cell else 20)
        unit.setPrefix("grid ")
        unit.setSuffix(" px")
        unit.setToolTip("Grid spacing (the snap unit), in px")
        unit.valueChanged.connect(lambda v: self._svg("set_grid_size", v))
        self.addWidget(unit)
        self.addSeparator()
        cw, ch = cell.canvas_size() if cell else (800, 500)
        canvas_w = QSpinBox()
        canvas_w.setRange(20, 10000)
        canvas_w.setValue(cw)
        canvas_w.setPrefix("W ")
        canvas_w.setToolTip("Canvas width (px)")
        canvas_w.valueChanged.connect(
            lambda v: self._svg("set_canvas_size", v, None))
        self.addWidget(canvas_w)
        canvas_h = QSpinBox()
        canvas_h.setRange(20, 10000)
        canvas_h.setValue(ch)
        canvas_h.setPrefix("H ")
        canvas_h.setToolTip("Canvas height (px)")
        canvas_h.valueChanged.connect(
            lambda v: self._svg("set_canvas_size", None, v))
        self.addWidget(canvas_h)
        self.addSeparator()
        self._add_menu("Shape", "Insert a ready-made SVG shape", [
            ("Rectangle", lambda: self._svg("insert_svg",
                '<rect x="60" y="60" width="160" height="110" rx="8" '
                'fill="#50bea0"/>')),
            ("Circle", lambda: self._svg("insert_svg",
                '<circle cx="140" cy="120" r="60" fill="#2176c7"/>')),
            ("Line", lambda: self._svg("insert_svg",
                '<line x1="40" y1="40" x2="260" y2="180" '
                'stroke="#333" stroke-width="3"/>')),
            ("Text", lambda: self._svg("insert_svg",
                '<text x="60" y="90" font-size="24" fill="#333">label</text>')),
            ("Curve (path)", lambda: self._svg("insert_svg",
                '<path d="M40,160 Q160,20 280,160" stroke="#c0392b" '
                'fill="none" stroke-width="3"/>')),
        ], icon_name="mdi.shape-outline")
        self._build_library_button()
        self._add("Edit source", "Edit the raw SVG source",
                  lambda: self._svg("edit_source"), "mdi.code-tags")
        self._add("Render", "Render / show the drawing (Shift+Enter)",
                  self._notebook.run_current, "mdi.eye-outline",
                  color="#27ae60")
        self.addSeparator()
        self._add("Open in KhervePaint", "Draw in the full KhervePaint app "
                  "and reload on save", self._open_svg_in_paint,
                  "mdi.draw-pen")

    def _build_library_button(self):
        """A dropdown listing KhervePaint's reusable objects, read live from
        its library folder so objects you save there appear here."""
        btn = QToolButton()
        btn.setText("Library")
        btn.setToolTip("Insert a KhervePaint library object "
                       "(reads KhervePaint's saved objects)")
        btn.setIcon(icon("mdi.shape-plus"))
        btn.setPopupMode(QToolButton.InstantPopup)
        menu = QMenu(btn)
        menu.aboutToShow.connect(lambda: self._populate_library(menu))
        btn.setMenu(menu)
        self.addWidget(btn)

    def _populate_library(self, menu):
        from . import paintlibrary
        menu.clear()
        objects = paintlibrary.list_objects()
        if not objects:
            act = menu.addAction("(no KhervePaint objects yet)")
            act.setEnabled(False)
            hint = menu.addAction("Save objects in KhervePaint to see them")
            hint.setEnabled(False)
            return
        for label, path in objects:
            menu.addAction(
                label, lambda _=False, p=path: self._svg("insert_object", p))

    def _open_svg_in_paint(self):
        cell = self._notebook.current
        if cell is not None and hasattr(cell, "open_in_paint"):
            cell.open_in_paint()

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
        self.addSeparator()
        self._add("Open in KhervePY", "Edit this code in the full KhervePY "
                  "editor and reload on save", self._open_code_in_khervepy,
                  "mdi.language-python")

    def _open_code_in_khervepy(self):
        cell = self._notebook.current
        if cell is not None and hasattr(cell, "open_in_khervepy"):
            cell.open_in_khervepy()

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
        self.addSeparator()
        self._add("Open in KherveSheet", "Edit this workbook in the full "
                  "KherveSheet app and reload on save",
                  lambda: self._sheet_op("open_in_khervesheet"),
                  "mdi.google-spreadsheet")

    # -- LaTeX mode -----------------------------------------------------------
    def _build_latex(self):
        # Math building blocks.
        for label, tip, snippet in LATEX_SNIPPETS:
            self._add(label, tip,
                      lambda _=False, s=snippet: self._insert(s))
        self.addSeparator()
        # Document structure: title and (un)numbered sections.
        self._add_menu("Section", "Title and sections", [
            ("Document skeleton", lambda: self._insert(LATEX_SKELETON)),
            ("Title block + \\maketitle", lambda: self._insert(LATEX_TITLE)),
            ("Section", lambda: self._insert("\\section{|}")),
            ("Section* (unnumbered)", lambda: self._insert("\\section*{|}")),
            ("Subsection", lambda: self._insert("\\subsection{|}")),
            ("Subsection* (unnumbered)",
             lambda: self._insert("\\subsection*{|}")),
            ("Subsubsection", lambda: self._insert("\\subsubsection{|}")),
        ], icon_name="mdi.format-header-pound")
        # Text formatting (wraps the selection).
        self._add_menu("Format", "Text formatting", [
            ("Bold", lambda: self._wrap("\\textbf{", "}")),
            ("Italic", lambda: self._wrap("\\textit{", "}")),
            ("Underline", lambda: self._wrap("\\underline{", "}")),
            ("Strikethrough", lambda: self._wrap("\\sout{", "}")),
            ("Monospace", lambda: self._wrap("\\texttt{", "}")),
            ("Small caps", lambda: self._wrap("\\textsc{", "}")),
            ("Emphasis", lambda: self._wrap("\\emph{", "}")),
        ], icon_name="mdi.format-bold")
        # Lists, equations and other environments.
        self._add_menu("List / Env", "Lists, equations, tables", [
            ("Bullet list (itemize)", lambda: self._insert(LATEX_ITEMIZE)),
            ("Numbered list (enumerate)",
             lambda: self._insert(LATEX_ENUMERATE)),
            ("List item", lambda: self._insert("\\item |")),
            ("Equation (numbered)", lambda: self._insert(LATEX_EQUATION)),
            ("Equation* (unnumbered)",
             lambda: self._insert(LATEX_EQUATION_STAR)),
            ("Aligned equations", lambda: self._insert(LATEX_ALIGN)),
            ("Table", lambda: self._insert(LATEX_TABLE)),
            ("Figure", lambda: self._insert(LATEX_FIGURE)),
        ], icon_name="mdi.format-list-numbered")
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
        self._add("Render", "Render / compile (Shift+Enter)",
                  self._notebook.run_current, "mdi.eye-outline")
