"""Lightweight LaTeX-document -> HTML converter for LaTeX cells.

KherveBook's LaTeX cell renders a single equation as a math image
(matplotlib mathtext). When the cell instead holds *document* LaTeX —
\\documentclass, \\section, \\textbf, lists, paragraphs — we render a
best-effort formatted view rather than failing. This is not a real
LaTeX engine: it maps the common text commands to HTML so the prose
reads correctly, keeps unknown commands' arguments, and drops the
preamble. For full typesetting, use kherveDOC/KherveTeX.

Copyright (C) 2026 Gwilherm Kerherve

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.
"""

import html
import re

#: Commands/environments that mark a cell as a document (not one equation).
_DOC_SIGNALS = (
    r"\documentclass", r"\usepackage", r"\section", r"\subsection",
    r"\paragraph", r"\textbf", r"\textit", r"\emph", r"\underline",
    r"\texttt", r"\textsc", r"\begin{itemize}", r"\begin{enumerate}",
    r"\begin{document}",
)


def is_document(tex: str) -> bool:
    """True if *tex* looks like prose/document LaTeX, not one equation."""
    return any(sig in tex for sig in _DOC_SIGNALS)


def _inline_math(match) -> str:
    s = match.group(1)
    s = re.sub(r"\^\{([^}]*)\}", r"<sup>\1</sup>", s)
    s = re.sub(r"\^(\w)", r"<sup>\1</sup>", s)
    s = re.sub(r"_\{([^}]*)\}", r"<sub>\1</sub>", s)
    s = re.sub(r"_(\w)", r"<sub>\1</sub>", s)
    s = re.sub(r"\\[,;:!]", " ", s)             # thin spaces
    s = re.sub(r"\\(\w+)", r"\1", s)            # \pi -> pi, \times -> times
    return f"<i>{s}</i>"


def latex_to_html(tex: str) -> str:
    """Convert document-style LaTeX to a small HTML fragment."""
    # Drop the preamble and document wrappers.
    tex = re.sub(r"\\documentclass[^\n]*\n?", "", tex)
    tex = re.sub(r"\\usepackage[^\n]*\n?", "", tex)
    tex = tex.replace(r"\begin{document}", "").replace(r"\end{document}", "")
    tex = re.sub(r"\\(maketitle|tableofcontents)\b", "", tex)

    # A backslash literal placeholder before we strip command backslashes.
    tex = tex.replace(r"\textbackslash{}", "\x00").replace(
        r"\textbackslash", "\x00")

    tex = html.escape(tex)                       # safe; tags added below

    # Inline math: $...$ -> italic with sub/superscripts.
    tex = re.sub(r"\$(.+?)\$", _inline_math, tex, flags=re.S)

    # Sectioning.
    tex = re.sub(r"\\section\*?\{([^}]*)\}", r"<h2>\1</h2>", tex)
    tex = re.sub(r"\\subsection\*?\{([^}]*)\}", r"<h3>\1</h3>", tex)
    tex = re.sub(r"\\subsubsection\*?\{([^}]*)\}", r"<h4>\1</h4>", tex)
    tex = re.sub(r"\\paragraph\{([^}]*)\}", r"<b>\1</b> ", tex)

    # Inline text formatting (two passes catch simple nesting).
    spans = [
        (r"\\textbf\{([^{}]*)\}", r"<b>\1</b>"),
        (r"\\textit\{([^{}]*)\}", r"<i>\1</i>"),
        (r"\\emph\{([^{}]*)\}", r"<i>\1</i>"),
        (r"\\underline\{([^{}]*)\}", r"<u>\1</u>"),
        (r"\\texttt\{([^{}]*)\}", r"<code>\1</code>"),
        (r"\\sout\{([^{}]*)\}", r"<s>\1</s>"),
        (r"\\textsc\{([^{}]*)\}",
         r'<span style="font-variant:small-caps">\1</span>'),
        (r"\\textsubscript\{([^{}]*)\}", r"<sub>\1</sub>"),
        (r"\\textsuperscript\{([^{}]*)\}", r"<sup>\1</sup>"),
    ]
    for _ in range(2):
        for pattern, repl in spans:
            tex = re.sub(pattern, repl, tex)

    # Lists.
    tex = tex.replace(r"\begin{itemize}", "<ul>").replace(
        r"\end{itemize}", "</ul>")
    tex = tex.replace(r"\begin{enumerate}", "<ol>").replace(
        r"\end{enumerate}", "</ol>")
    tex = re.sub(r"\\item\s*", "<li>", tex)

    # Explicit breaks.
    tex = tex.replace(r"\\", "<br>").replace(r"\newline", "<br>")

    # Remaining one-arg commands keep their argument; bare commands drop.
    tex = re.sub(r"\\[a-zA-Z]+\*?\{([^{}]*)\}", r"\1", tex)
    tex = re.sub(r"\\[a-zA-Z]+\b\s?", "", tex)
    # LaTeX char escapes and leftover braces.
    for esc, ch in ((r"\&", "&amp;"), (r"\%", "%"), (r"\#", "#"),
                    (r"\_", "_"), (r"\$", "$")):
        tex = tex.replace(esc, ch)
    tex = tex.replace("{", "").replace("}", "").replace("\x00", "&#92;")

    # Paragraphs from blank lines.
    blocks = []
    for part in re.split(r"\n\s*\n", tex):
        part = part.strip()
        if not part:
            continue
        if part.startswith(("<h2", "<h3", "<h4", "<ul", "<ol", "<li")):
            blocks.append(part)
        else:
            blocks.append(f"<p>{part}</p>")
    return "\n".join(blocks)
