"""In-process Python execution kernel.

Runs code cells in a shared namespace (like a Jupyter kernel, but
in-process). Captures stdout/stderr, the repr of a trailing
expression, and any matplotlib figures created during execution.

Copyright (C) 2026 Gwilherm Kerherve

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.
"""

import ast
import io
import traceback
from contextlib import redirect_stderr, redirect_stdout
from dataclasses import dataclass, field


@dataclass
class ExecResult:
    """Outcome of running one code cell."""
    stdout: str = ""
    stderr: str = ""
    result_repr: str = ""          # repr of trailing expression, if any
    figures: list = field(default_factory=list)  # list of PNG bytes
    error: str = ""                # formatted traceback on failure

    @property
    def ok(self) -> bool:
        return not self.error


class Kernel:
    """Shared execution namespace for all code cells in a notebook."""

    def __init__(self):
        self.namespace = {}
        self.exec_count = 0
        self.reset()

    def reset(self):
        """Clear the namespace (Kernel > Restart)."""
        self.namespace = {"__name__": "__main__", "__builtins__": __builtins__}
        self.exec_count = 0

    def run(self, source: str) -> ExecResult:
        """Execute *source*; return captured output and figures."""
        self.exec_count += 1
        res = ExecResult()
        out, err = io.StringIO(), io.StringIO()

        # Split a trailing expression so its value is echoed, Jupyter-style.
        try:
            tree = ast.parse(source, mode="exec")
        except SyntaxError:
            res.error = traceback.format_exc(limit=0)
            return res

        trailing = None
        if tree.body and isinstance(tree.body[-1], ast.Expr):
            trailing = ast.Expression(tree.body.pop(-1).value)

        plt = self._matplotlib()
        before = set(plt.get_fignums()) if plt else set()

        try:
            with redirect_stdout(out), redirect_stderr(err):
                exec(compile(tree, "<cell>", "exec"), self.namespace)
                if trailing is not None:
                    value = eval(compile(trailing, "<cell>", "eval"),
                                 self.namespace)
                    if value is not None:
                        res.result_repr = repr(value)
        except Exception:
            res.error = traceback.format_exc()

        res.stdout = out.getvalue()
        res.stderr = err.getvalue()

        if plt:
            for num in plt.get_fignums():
                if num in before:
                    continue
                buf = io.BytesIO()
                plt.figure(num).savefig(buf, format="png", dpi=110,
                                        bbox_inches="tight")
                res.figures.append(buf.getvalue())
                plt.close(num)
        return res

    @staticmethod
    def _matplotlib():
        """Return pyplot with the Agg backend, or None if unavailable."""
        try:
            import matplotlib
            matplotlib.use("Agg", force=False)
            import matplotlib.pyplot as plt
            return plt
        except ImportError:
            return None
