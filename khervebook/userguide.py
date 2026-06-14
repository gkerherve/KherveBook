"""The Help > User Guide window: a detailed, scrollable HTML guide.

Copyright (C) 2026 Gwilherm Kerherve

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.
"""

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (QDialog, QDialogButtonBox, QTextBrowser,
                             QVBoxLayout)

from . import APP_NAME


def _section(title, body):
    return f"<h2 style='color:#3776ab'>{title}</h2>\n{body}\n"


def _kbd(keys):
    return (f"<code style='background:#eee;padding:1px 5px;"
            f"border-radius:3px'>{keys}</code>")


GUIDE_HTML = f"""
<h1><span style='color:#3776ab'>Kherve</span><span
 style='color:#e07b39'>Book</span> &mdash; User Guide</h1>
<p>KherveBook is a computational notebook: one scrolling document that
mixes runnable <b>Python</b>, formatted <b>Markdown</b>, typeset
<b>LaTeX</b>, live <b>spreadsheets</b> and <b>drawings</b>. It is like
Jupyter, but a native desktop app, and it does more.</p>

{_section("1. Cells &mdash; the building blocks", '''
<p>A notebook is a vertical column of <b>cells</b>. Each cell has a type,
shown in its left gutter:</p>
<ul>
<li><b>Code</b> (<code>In [n]:</code>) &mdash; runs Python.</li>
<li><b>Markdown</b> (<code>md</code>) &mdash; formatted notes; renders on run.</li>
<li><b>LaTeX</b> (<code>tex</code>) &mdash; an equation or a whole document.</li>
<li><b>Sheet</b> (<code>sheet</code>) &mdash; an embedded spreadsheet.</li>
<li><b>SVG / Drawing</b> &mdash; a vector drawing (e.g. from KhervePaint).</li>
</ul>
<p>Change a cell's type with the toolbar drop-down, the <b>Cell</b> menu, or
right-click &rarr; <b>Convert To</b>. Markdown and LaTeX cells show their
rendered result after running; <b>double-click</b> the rendered view to edit
the source again.</p>
''')}

{_section("2. Running cells", f'''
<ul>
<li>{_kbd("Shift+Enter")} &mdash; run the cell and move to the next (a new
code cell is created at the end if needed).</li>
<li>{_kbd("Ctrl+Enter")} &mdash; run the cell in place.</li>
<li>Click the green <b>&#9654;</b> in the cell's left gutter, or use the
<b>Run</b> toolbar button.</li>
<li><b>Run All</b> ({_kbd("Ctrl+Shift+Enter")}) restarts the kernel and runs
every cell top to bottom.</li>
<li><b>Run Continuously</b> (the &#8635; button, or right-click) re-runs a
cell on a timer for live animations and simulations; the red <b>&#9632;</b>
stops it.</li>
</ul>
<p>Code cells share one in-process <b>kernel</b> with <code>numpy</code>
(<code>np</code>), <code>matplotlib</code> (<code>plt</code>),
<code>pandas</code> (<code>pd</code>), <code>scipy</code>, <code>sympy</code>
and <code>lmfit</code> preloaded. A trailing expression is echoed
Jupyter-style, and any matplotlib figure is shown inline.
<b>Kernel &rarr; Restart</b> clears all variables and the
<code>In [n]</code> counters.</p>
''')}

{_section("3. Markdown &amp; LaTeX", '''
<p><b>Markdown cells</b> take standard Markdown &mdash; headings, <b>bold</b>,
<i>italic</i>, lists, tables, links, code spans &mdash; plus the second
toolbar row offers formatting buttons. Commands are syntax-highlighted as
you type.</p>
<p><b>LaTeX cells</b> are dual-purpose:</p>
<ul>
<li>A bare formula (e.g. <code>\\int_0^1 x^2\\,dx</code>) renders instantly
with matplotlib mathtext.</li>
<li>A document (with <code>\\section</code>, <code>\\textbf</code>, etc.) is
compiled by the real <b>tectonic</b> LaTeX engine, showing the typeset pages.
Without tectonic installed, a lightweight text renderer is used instead.</li>
</ul>
<p>The LaTeX toolbar inserts sections, equations, lists and other building
blocks. In either editor, <b>Ctrl+/</b> toggles a comment.</p>
''')}

{_section("4. Sheet cells &amp; the Python &harr; sheet bridge", '''
<p>A <b>sheet cell</b> embeds a KherveSheet-style spreadsheet &mdash; possibly
several named sheets and plots &mdash; with one view shown at a time (pick it
from the <b>View</b> drop-down on the left, or the right-click View menu).</p>
<ul>
<li>Type a value, or an <code>=</code> formula in <b>Python</b> syntax with A1
references and <code>A1:B5</code> ranges, e.g. <code>=np.pi * A2**2</code> or
<code>=sum(B2:B4)</code>. Formulas see everything the kernel knows and
recompute live as you type.</li>
<li><b>Right-click &rarr; Create Plot</b> charts the selected range (line, bar
or scatter) as a saved plot view.</li>
<li>After a run, each grid is published to code cells as
<code>sheet1</code>, <code>sheet2</code>, &hellip;</li>
<li>The <code>ks()</code> bridge works both ways: <code>ks("A1")</code> and
<code>ks("A1:B5")</code> read a grid from Python; <code>ks("A1", value)</code>
writes a value back into the live sheet.</li>
</ul>
''')}

{_section("5. Importing &amp; drag-and-drop", '''
<p>Drag a file from the <b>file explorer</b> (or your desktop) onto the
notebook and, if recognised, it opens in a cell:</p>
<ul>
<li><b>.xlsx / .xlsm</b> Excel workbooks &rarr; a multi-sheet sheet cell.</li>
<li><b>.csv / .tsv / .txt</b> &rarr; a sheet cell.</li>
<li><b>Images</b> (.png/.jpg/&hellip;) and <b>.pdf</b> &rarr; a self-contained
drawing cell (each PDF page becomes one cell).</li>
<li><b>.ipynb</b> Jupyter/Colab notebooks, <b>.ksheet</b> workbooks,
<b>.ktex</b> KherveTeX, <b>.kdoc</b> KherveDOC, <b>.svg</b> drawings,
<b>.tex</b>, and <b>.py</b>.</li>
</ul>
<p>The <b>File</b> menu also has <b>Insert Image / PDF&hellip;</b>,
<b>Import Spreadsheet&hellip;</b> and <b>Import / Export Jupyter
(.ipynb)</b>.</p>
''')}

{_section("6. Layout: titles, columns, collapse, page mode", f'''
<ul>
<li><b>Title</b> &mdash; right-click &rarr; <i>Set Title</i> puts a heading at
the top of a cell.</li>
<li><b>Collapse</b> &mdash; minimise a long cell to its title/summary.</li>
<li><b>Columns</b> &mdash; <i>Place Beside Cell Above</i> puts two cells
side by side in one row (e.g. code next to its plot).</li>
<li><b>Resize</b> &mdash; drag the grip at a cell's bottom-right corner to set
its width/height; a sheet's grip sizes its grid.</li>
<li><b>Page Mode</b> ({_kbd("Ctrl+Shift+P")}, or the toolbar button) hides the
cell borders so the whole notebook reads as one continuous white page.</li>
</ul>
''')}

{_section("7. Examples, explorer, AI &amp; themes", '''
<ul>
<li>The <b>Examples</b> menu has 80+ ready notebooks across Physics,
Chemistry, Maths, Finance, Biology, Simulations, Live Data and the
spreadsheet topics ported from KherveSheet. Opening one replaces the current
notebook and runs it.</li>
<li>The <b>file explorer</b> (Ctrl+B) docks a tree rooted at a folder you
choose; drag files from it into cells.</li>
<li>The <b>AI Assistant</b> dock (bottom-left) chats with Claude, ChatGPT,
Mistral, Ollama or a local model and can drop its code replies straight into
cells.</li>
<li><b>View &rarr; Theme</b> switches between the light and dark themes.</li>
</ul>
''')}

{_section("8. Saving &amp; undo", f'''
<p>Documents save as <b>.kbook</b> &mdash; a plain-JSON file that round-trips
every cell, its type, title, layout, width/height, and a sheet's data. You can
also <b>export to Jupyter .ipynb</b> (a lossless round-trip).</p>
<p><b>Undo / Redo</b> ({_kbd("Ctrl+Z")} / {_kbd("Ctrl+Shift+Z")}) covers cell
structure &mdash; add, delete, move, convert, cut and paste. While you are
typing in a cell, the same keys undo text edits inside that editor first.</p>
''')}

{_section("9. Keyboard shortcuts", f'''
<table cellpadding='4' style='border-collapse:collapse'>
<tr><td>{_kbd("Shift+Enter")}</td><td>Run cell, advance</td>
    <td>{_kbd("Ctrl+Enter")}</td><td>Run cell in place</td></tr>
<tr><td>{_kbd("Ctrl+Shift+Enter")}</td><td>Run all</td>
    <td>{_kbd("Ctrl+Shift+R")}</td><td>Restart kernel</td></tr>
<tr><td>{_kbd("Ctrl+Shift+C")}</td><td>Add code cell</td>
    <td>{_kbd("Ctrl+Shift+M")}</td><td>Add markdown cell</td></tr>
<tr><td>{_kbd("Ctrl+Shift+L")}</td><td>Add LaTeX cell</td>
    <td>{_kbd("Ctrl+Shift+T")}</td><td>Add sheet cell</td></tr>
<tr><td>{_kbd("Ctrl+Shift+&uarr;/&darr;")}</td><td>Move cell</td>
    <td>{_kbd("Ctrl+Shift+D")}</td><td>Delete cell</td></tr>
<tr><td>{_kbd("Ctrl+Shift+X/O/V")}</td><td>Cut / Copy / Paste cell</td>
    <td>{_kbd("Ctrl+Z / Ctrl+Shift+Z")}</td><td>Undo / Redo</td></tr>
<tr><td>{_kbd("Ctrl+/")}</td><td>Toggle comment</td>
    <td>{_kbd("Ctrl+B")}</td><td>Toggle explorer</td></tr>
<tr><td>{_kbd("Ctrl+Shift+P")}</td><td>Page mode</td>
    <td>{_kbd("Ctrl+S")}</td><td>Save</td></tr>
</table>
''')}

<hr>
<p style='color:gray'>KherveBook by Gwilherm Kerherve &mdash; Imperial College
London. Part of the Kherve family of native scientific apps.</p>
"""


class UserGuideDialog(QDialog):
    """A scrollable, link-enabled window showing the user guide."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"{APP_NAME} — User Guide")
        self.resize(720, 640)
        layout = QVBoxLayout(self)
        browser = QTextBrowser()
        browser.setOpenExternalLinks(True)
        browser.setHtml(GUIDE_HTML)
        layout.addWidget(browser)
        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        buttons.rejected.connect(self.reject)
        buttons.accepted.connect(self.accept)
        layout.addWidget(buttons)


def show_user_guide(parent=None):
    UserGuideDialog(parent).exec_()
