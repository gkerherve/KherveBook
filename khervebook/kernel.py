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
import re
import sys
import threading
import time
import traceback
from contextlib import redirect_stderr, redirect_stdout
from dataclasses import dataclass, field

_KS_REF = re.compile(r"^([A-Za-z]{1,2})(\d{1,4})$")
_KS_RANGE = re.compile(r"^([A-Za-z]{1,2})(\d{1,4}):([A-Za-z]{1,2})(\d{1,4})$")


def _ks_col(letters: str) -> int:
    c = 0
    for ch in letters.upper():
        c = c * 26 + (ord(ch) - 64)
    return c - 1


def _ks_letters(c: int) -> str:
    out = ""
    c += 1
    while c:
        c, rem = divmod(c - 1, 26)
        out = chr(65 + rem) + out
    return out


def _np_compat(np):
    """Bridge names NumPy 2.0 renamed or removed, in both directions, so
    older scientific code — e.g. imported XPS analysis using np.trapz,
    np.NaN or np.float_ — keeps running on a modern NumPy (and vice
    versa)."""
    import warnings
    with warnings.catch_warnings():       # probing legacy names may warn
        warnings.simplefilter("ignore")
        for new, old in (("trapezoid", "trapz"), ("isin", "in1d"),
                         ("vstack", "row_stack"), ("prod", "product"),
                         ("cumprod", "cumproduct"), ("all", "alltrue"),
                         ("any", "sometrue"), ("round", "round_")):
            if hasattr(np, new) and not hasattr(np, old):
                setattr(np, old, getattr(np, new))
            elif hasattr(np, old) and not hasattr(np, new):
                setattr(np, new, getattr(np, old))
        for alias, target in (("NaN", "nan"), ("NAN", "nan"), ("Inf", "inf"),
                              ("Infinity", "inf"), ("PINF", "inf"),
                              ("float_", "float64"),
                              ("complex_", "complex128"),
                              ("unicode_", "str_"), ("bool8", "bool_"),
                              ("object0", "object_")):
            if not hasattr(np, alias) and hasattr(np, target):
                setattr(np, alias, getattr(np, target))
        if not hasattr(np, "NINF"):
            try:
                np.NINF = -np.inf
            except Exception:
                pass


_UNSET = object()


def make_ks(kernel):
    """Build ks(ref[, value]): the two-way Python <-> sheet bridge.

    Read: ``ks("A1")`` / ``ks("A1:B5")`` reads sheet1 (the first sheet
    cell); a ``"Sheet2!A1"`` ref reads that numbered sheet. A single
    cell returns its value; a range returns a NumPy array (or list of
    lists). Write: ``ks("A1", value)`` pushes a value back into the live
    grid (single cell only), so a code cell can fill a sheet."""
    namespace = kernel.namespace

    def _grid(name):
        grid = namespace.get(name)
        if grid is None:
            raise NameError(
                f"{name} is not available yet — run the sheet cell first")
        return grid

    def _at(grid, r, c):
        if 0 <= r < len(grid) and 0 <= c < len(grid[r]):
            v = grid[r][c]
            return 0 if v is None else v
        return 0

    def ks(ref, value=_UNSET):
        ref = str(ref).strip()
        name = "sheet1"
        if "!" in ref:
            sheet, _, ref = ref.partition("!")
            sheet = sheet.strip().strip("'\"").lower().replace(" ", "")
            name = sheet if sheet.startswith("sheet") else "sheet1"
        if value is not _UNSET:
            writer = getattr(kernel, "sheet_writers", {}).get(name)
            if writer is None:
                raise NameError(
                    f"{name} cannot be written yet — run the sheet cell first")
            return writer(ref, value)
        grid = _grid(name)
        m = _KS_RANGE.match(ref)
        if m:
            r1, c1 = int(m.group(2)) - 1, _ks_col(m.group(1))
            r2, c2 = int(m.group(4)) - 1, _ks_col(m.group(3))
            r1, r2 = sorted((r1, r2))
            c1, c2 = sorted((c1, c2))
            rows = [[_at(grid, r, c) for c in range(c1, c2 + 1)]
                    for r in range(r1, r2 + 1)]
            # A single row or column collapses to a 1-D vector (numeric ->
            # NumPy array, else the raw list) — matching KherveSheet.
            flat = None
            if len(rows) == 1:
                flat = rows[0]
            elif all(len(x) == 1 for x in rows):
                flat = [x[0] for x in rows]
            try:
                import numpy as np
                if flat is not None:
                    try:
                        return np.array(flat, dtype=float)
                    except (TypeError, ValueError):
                        return flat
                try:
                    return np.array(rows, dtype=float)
                except (TypeError, ValueError):
                    return rows
            except Exception:
                return flat if flat is not None else rows
        m = _KS_REF.match(ref)
        if m:
            return _at(grid, int(m.group(2)) - 1, _ks_col(m.group(1)))
        raise ValueError(f"bad cell reference: {ref!r}")

    def ks_set(ref, value):
        """Write a value back into a sheet — a scalar to one cell, a 1-D
        sequence down a column / across a row, or a scalar filling a range
        (the KherveSheet ks_set contract)."""
        ref = str(ref).strip()
        name = "sheet1"
        if "!" in ref:
            sheet, _, ref = ref.partition("!")
            sheet = sheet.strip().strip("'\"").lower().replace(" ", "")
            name = sheet if sheet.startswith("sheet") else "sheet1"
        writer = getattr(kernel, "sheet_writers", {}).get(name)
        if writer is None:
            raise NameError(
                f"{name} cannot be written yet — run the sheet cell first")
        rng = _KS_RANGE.match(ref)
        if not rng:
            return writer(ref, value)
        r1, c1 = int(rng.group(2)) - 1, _ks_col(rng.group(1))
        r2, c2 = int(rng.group(4)) - 1, _ks_col(rng.group(3))
        r1, r2 = sorted((r1, r2))
        c1, c2 = sorted((c1, c2))
        seq = None
        if hasattr(value, "__iter__") and not isinstance(value, (str, bytes)):
            seq = list(value)
        targets = [(r, c) for r in range(r1, r2 + 1)
                   for c in range(c1, c2 + 1)]
        for i, (r, c) in enumerate(targets):
            v = seq[i] if seq is not None and i < len(seq) else (
                value if seq is None else 0)
            writer(f"{_ks_letters(c)}{r + 1}", v)
        return value

    return ks, ks_set


@dataclass
class ExecResult:
    """Outcome of running one code cell."""
    stdout: str = ""
    stderr: str = ""
    result_repr: str = ""          # repr of trailing expression, if any
    figures: list = field(default_factory=list)  # list of PNG bytes
    live_figures: list = field(default_factory=list)  # live mpl Figures
    error: str = ""                # formatted traceback on failure

    @property
    def ok(self) -> bool:
        return not self.error


class Kernel:
    """Shared execution namespace for all code cells in a notebook."""

    #: Max seconds a cell may run before it is aborted. Guards against
    #: infinite loops freezing the app. Set to 0/None to disable.
    DEFAULT_TIMEOUT = 30.0

    def __init__(self):
        self.namespace = {}
        self.exec_count = 0
        self.timeout = self.DEFAULT_TIMEOUT
        #: user preference: embed live, zoom/pan-able figures (set by the
        #: "Interactive plots" toggle) instead of static PNGs. Survives a
        #: kernel restart, so it lives outside reset().
        self.interactive_figures = False
        self.reset()

    def reset(self):
        """Clear the namespace (Kernel > Restart)."""
        self.namespace = {"__name__": "__main__", "__builtins__": __builtins__}
        self.exec_count = 0
        self._seeded = False
        #: name -> writer(ref, value); registered by each live sheet cell so
        #: ``ks("A1", value)`` can push values back into the grid.
        self.sheet_writers = {}

    def _seed_namespace(self):
        """Pre-import the usual scientific stack on the first run.

        Lazy so that opening the app stays fast; missing optional
        libraries (pandas, scipy) are silently skipped.
        """
        if self._seeded:
            return
        self._seeded = True
        g = self.namespace
        import math
        g["math"] = math
        try:
            import numpy as np
            _np_compat(np)        # bridge NumPy 1.x <-> 2.0 renamed names
            g["np"] = np
            g["numpy"] = np
        except Exception:
            pass
        plt = self._matplotlib()
        if plt is not None:
            g["plt"] = plt
        try:
            import pandas as pd
            g["pd"] = pd
            g["pandas"] = pd
        except Exception:
            pass
        # The wider scientific stack, whatever is installed.
        for mod in ("scipy", "lmfit", "sympy"):
            try:
                g[mod] = __import__(mod)
            except Exception:
                pass
        # Dask for parallel / larger-than-memory compute: dask, plus the
        # da (array) and dd (dataframe) aliases, mirroring np / pd.
        try:
            import dask
            g["dask"] = dask
            import dask.array as _da
            g["da"] = _da
            import dask.dataframe as _dd
            g["dd"] = _dd
        except Exception:
            pass
        # KherveSheet-style grid accessors for imported =PY cells: ks("A1")
        # reads (and ks("A1", v) / ks_set write) a sheet cell's grid
        # (sheet1, sheet2, ...). xl and cell are aliases of ks.
        ks_fn, ks_set_fn = make_ks(self)
        g["ks"] = ks_fn
        g["xl"] = ks_fn
        g["cell"] = ks_fn
        g["ks_set"] = ks_set_fn

    def run(self, source: str, interactive: bool = False) -> ExecResult:
        """Execute *source*; return captured output and figures.

        When *interactive*, figures are returned as live matplotlib
        ``Figure`` objects (res.live_figures) for an embedded Qt canvas
        with a zoom/pan toolbar; otherwise as static PNG bytes."""
        self.exec_count += 1
        self._seed_namespace()
        res = ExecResult()
        out, err = io.StringIO(), io.StringIO()

        def _emit_figure(fig):
            if interactive:
                res.live_figures.append(fig)
            else:
                res.figures.append(self._fig_png(fig))

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

        def _exec_and_eval():
            exec(compile(tree, "<cell>", "exec"), self.namespace)
            if trailing is not None:
                return eval(compile(trailing, "<cell>", "eval"),
                            self.namespace)
            return None

        value = None
        try:
            with redirect_stdout(out), redirect_stderr(err):
                value = self._call_with_timeout(_exec_and_eval)
        except TimeoutError as exc:
            res.error = f"TimeoutError: {exc}"
        except Exception:
            res.error = traceback.format_exc()

        res.stdout = out.getvalue()
        res.stderr = err.getvalue()

        if value is not None and not res.error:
            if self._is_figure(value):
                # Captured by the new-figure sweep below if it is a live
                # pyplot figure; otherwise (bare Figure()) render it here.
                if not (plt and getattr(value, "number", None)
                        in plt.get_fignums()):
                    _emit_figure(value)
            else:
                png = self._to_png(value, plt)
                if png is not None:
                    res.figures.append(png)
                else:
                    res.result_repr = repr(value)

        if plt:
            for num in plt.get_fignums():
                if num in before:
                    continue
                fig = plt.figure(num)
                _emit_figure(fig)
                # Drop it from pyplot's registry. The Figure object lives on
                # (held by res when interactive) for embedding in a canvas.
                plt.close(num)
        return res

    def _call_with_timeout(self, fn):
        """Run *fn* on the calling thread with a timeout guard.

        A watchdog thread sets a flag after ``self.timeout`` seconds, and
        a ``sys.settrace`` hook checks that flag at every Python line,
        raising ``TimeoutError`` cleanly from pure-Python context.

        This is safe because the code runs on the calling (main) thread
        and the exception is raised at a Python line boundary, never
        inside C code — unlike ``PyThreadState_SetAsyncExc`` it cannot
        corrupt the stack. The trade-off: a single long-running C call
        (e.g. a huge numpy operation) is only interrupted once it
        returns to Python.
        """
        timeout = self.timeout
        if not timeout or timeout <= 0:
            return fn()

        deadline = time.monotonic() + timeout
        expired = False

        def _watchdog():
            nonlocal expired
            remaining = deadline - time.monotonic()
            if remaining > 0:
                threading.Event().wait(remaining)
            expired = True

        def _trace(frame, event, arg):
            if expired:
                raise TimeoutError(
                    f"execution exceeded {timeout:g} s — possible "
                    "infinite loop. Increase the limit or fix the code.")
            return _trace

        wd = threading.Thread(target=_watchdog, daemon=True)
        wd.start()
        old_trace = sys.gettrace()
        sys.settrace(_trace)
        try:
            return fn()
        finally:
            sys.settrace(old_trace)
            expired = True  # stop watchdog early

    # -- rich output -----------------------------------------------------
    @staticmethod
    def _fig_png(fig) -> bytes:
        """Render a matplotlib figure to PNG bytes."""
        buf = io.BytesIO()
        fig.savefig(buf, format="png", dpi=110, bbox_inches="tight")
        return buf.getvalue()

    @staticmethod
    def _is_figure(value) -> bool:
        try:
            from matplotlib.figure import Figure
            return isinstance(value, Figure)
        except Exception:
            return False

    @classmethod
    def _to_png(cls, value, plt) -> bytes | None:
        """Convert an image-like trailing value to PNG bytes, else None.

        Accepts raw PNG/JPEG bytes, a PIL image, or a NumPy H×W×3/4
        uint8 array. (Figures are handled separately in run().)
        """
        if isinstance(value, (bytes, bytearray)):
            head = bytes(value[:4])
            if head.startswith(b"\x89PNG") or head.startswith(b"\xff\xd8"):
                return bytes(value)
            return None
        try:
            from PIL import Image
            if isinstance(value, Image.Image):
                buf = io.BytesIO()
                value.convert("RGBA").save(buf, format="PNG")
                return buf.getvalue()
        except Exception:
            pass
        try:
            import numpy as np
            if (isinstance(value, np.ndarray) and value.ndim == 3
                    and value.shape[2] in (3, 4) and plt):
                buf = io.BytesIO()
                plt.imsave(buf, value.astype(np.uint8), format="png")
                return buf.getvalue()
        except Exception:
            pass
        return None

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
