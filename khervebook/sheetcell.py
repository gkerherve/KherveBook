"""Sheet cell — a KherveSheet-style spreadsheet grid inside a notebook.

A fourth cell type next to code/markdown/latex: an editable grid
whose cells may hold values or ``=`` formulas. Formulas use Python
syntax, can reference grid cells A1-style and see the notebook
kernel's namespace, so ``=np.pi * A2**2`` works — including
variables defined in code cells. Running the cell (gutter button /
Shift+Enter) recomputes all formulas, mirroring how markdown and
latex cells render on run.

Adapted from KherveSheet's python_engine, scaled down to one grid.

Copyright (C) 2026 Gwilherm Kerherve

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.
"""

import json
import re

from PyQt5.QtCore import QEvent, Qt, QTimer
from PyQt5.QtGui import QPixmap
from PyQt5.QtWidgets import (QHBoxLayout, QLabel, QLineEdit, QSizePolicy,
                             QStyledItemDelegate, QTableWidget,
                             QTableWidgetItem)

from .cells import MONO, CELL_CLASSES, CellWidget
from .kernel import Kernel

_REF = re.compile(r"\b([A-Z]{1,2})(\d{1,3})\b")
_RANGE = re.compile(r"\b([A-Z]{1,2})(\d{1,3})\s*:\s*([A-Z]{1,2})(\d{1,3})\b")

DEFAULT_ROWS, DEFAULT_COLS = 6, 4
MAX_PASSES = 8      # formula chains resolve iteratively


def col_letter(c: int) -> str:
    """0 -> A, 25 -> Z, 26 -> AA."""
    out = ""
    c += 1
    while c:
        c, rem = divmod(c - 1, 26)
        out = chr(ord("A") + rem) + out
    return out


def letter_col(s: str) -> int:
    c = 0
    for ch in s:
        c = c * 26 + (ord(ch) - ord("A") + 1)
    return c - 1


def parse_value(text: str):
    """Numeric if it looks numeric, else the string itself."""
    try:
        f = float(text)
        return int(f) if f.is_integer() else f
    except (TypeError, ValueError):
        return text


def format_value(value) -> str:
    if isinstance(value, float):
        return f"{value:g}"
    return str(value)


class _RawDelegate(QStyledItemDelegate):
    """Edit the raw text (formula) while the grid displays the result."""

    def setEditorData(self, editor, index):
        raw = index.data(Qt.UserRole)
        editor.setText(raw if raw is not None else (index.data() or ""))

    def setModelData(self, editor, model, index):
        text = editor.text()
        model.setData(index, text, Qt.UserRole)
        model.setData(index, text, Qt.DisplayRole)   # raw until next run


class SheetCell(CellWidget):
    """Spreadsheet cell: values and =formulas over the shared kernel."""

    CELL_TYPE = "sheet"

    def __init__(self, source=""):
        super().__init__("")
        self.gutter.setText("sheet")
        self.editor.hide()

        # Formula bar: selected ref + raw content, like KherveSheet.
        bar = QHBoxLayout()
        self.ref_label = QLabel("A1")
        self.ref_label.setFont(MONO)
        self.ref_label.setFixedWidth(40)
        bar.addWidget(self.ref_label)
        self.formula_edit = QLineEdit()
        self.formula_edit.setFont(MONO)
        self.formula_edit.setPlaceholderText(
            "value or =formula  (Python; A1 refs, A1:B5 ranges)")
        self.formula_edit.returnPressed.connect(self._commit_formula)
        bar.addWidget(self.formula_edit)
        self.column.addLayout(bar)

        self.table = QTableWidget(DEFAULT_ROWS, DEFAULT_COLS)
        self.table.setItemDelegate(_RawDelegate(self.table))
        self.table.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.table.itemChanged.connect(lambda _item: self.focused.emit(self))
        self.table.currentCellChanged.connect(self._sync_formula_bar)
        self.table.installEventFilter(self)
        self.column.addWidget(self.table)
        self._figure_labels = []        # plots produced by formulas
        self._refresh_headers()
        self._fit_height()

        # Excel-like behaviour: recompute shortly after any edit.
        self._recalc_timer = QTimer(self)
        self._recalc_timer.setSingleShot(True)
        self._recalc_timer.setInterval(300)
        self._recalc_timer.timeout.connect(self.recalculate)
        self.table.itemChanged.connect(
            lambda _item: self._recalc_timer.start())
        self._computed_once = False

        if source:
            self.set_source(source)

    def _notebook(self):
        w = self.parent()
        while w is not None and not hasattr(w, "kernel"):
            w = w.parent()
        return w

    def recalculate(self):
        """Recompute against the owning notebook's kernel, if any."""
        nb = self._notebook()
        if nb is not None:
            self.execute(nb.kernel)

    def showEvent(self, event):
        super().showEvent(event)
        # Loaded notebooks show computed values without a manual run.
        if not self._computed_once:
            self._recalc_timer.start()

    # -- CellWidget API ----------------------------------------------------
    def source(self) -> str:
        data = {}
        for r in range(self.table.rowCount()):
            for c in range(self.table.columnCount()):
                raw = self._raw(r, c)
                if raw:
                    data[f"{col_letter(c)}{r + 1}"] = raw
        return json.dumps({"rows": self.table.rowCount(),
                           "cols": self.table.columnCount(),
                           "data": data})

    def set_source(self, text: str):
        try:
            doc = json.loads(text)
            rows = int(doc.get("rows", DEFAULT_ROWS))
            cols = int(doc.get("cols", DEFAULT_COLS))
            data = doc.get("data", {})
        except Exception:
            # Converting a text cell: import lines as rows, tabs/commas
            # as columns.
            lines = [ln for ln in text.splitlines() if ln.strip()]
            grid = [re.split(r"\t|,", ln) for ln in lines]
            rows = max(DEFAULT_ROWS, len(grid))
            cols = max(DEFAULT_COLS, max((len(r) for r in grid), default=0))
            data = {f"{col_letter(c)}{r + 1}": cell
                    for r, row in enumerate(grid)
                    for c, cell in enumerate(row) if cell.strip()}
        self.table.blockSignals(True)
        self.table.setRowCount(rows)
        self.table.setColumnCount(cols)
        self.table.clearContents()
        for ref, raw in data.items():
            m = _REF.fullmatch(ref)
            if not m:
                continue
            r, c = int(m.group(2)) - 1, letter_col(m.group(1))
            self._set_item(r, c, raw, raw)
        self.table.blockSignals(False)
        self._refresh_headers()
        self._fit_height()

    def execute(self, kernel):
        """Recompute every =formula against the kernel namespace, then
        publish the grid into the namespace as sheet1/sheet2/..."""
        self._computed_once = True
        kernel._seed_namespace()
        plt = kernel.namespace.get("plt")
        before = set(plt.get_fignums()) if plt else set()
        values, formulas = {}, {}
        for r in range(self.table.rowCount()):
            for c in range(self.table.columnCount()):
                raw = self._raw(r, c)
                if not raw:
                    continue
                if raw.lstrip().startswith("="):
                    formulas[(r, c)] = raw.lstrip()[1:]
                else:
                    values[(r, c)] = parse_value(raw)

        pending = dict(formulas)
        for _ in range(MAX_PASSES):
            if not pending:
                break
            progressed = False
            for rc, expr in list(pending.items()):
                blocked = set(pending) - {rc}
                try:
                    values[rc] = self._eval(expr, values, blocked,
                                            kernel.namespace)
                except KeyError:
                    continue            # depends on a not-yet-computed cell
                except Exception as exc:
                    values[rc] = f"#ERR {exc.__class__.__name__}"
                del pending[rc]
                progressed = True
            if not progressed:
                break
        for rc in pending:
            values[rc] = "#ERR circular"

        # Figures: trailing Figure values and any pyplot figures a
        # formula created both display below the grid, like code cells.
        pngs, captured = [], set()
        self.table.blockSignals(True)
        for rc, expr in formulas.items():
            raw = self._raw(*rc)
            value = values[rc]
            if Kernel._is_figure(value):
                pngs.append(Kernel._fig_png(value))
                captured.add(getattr(value, "number", None))
                values[rc] = "[plot]"
                self._set_item(rc[0], rc[1], raw, "[plot]")
            else:
                self._set_item(rc[0], rc[1], raw, format_value(value))
        self.table.blockSignals(False)
        if plt:
            for num in plt.get_fignums():
                if num in before:
                    continue
                if num not in captured:
                    pngs.append(Kernel._fig_png(plt.figure(num)))
                plt.close(num)
        self._show_figures(pngs)
        self._publish(kernel, values)

    def _show_figures(self, pngs):
        if len(pngs) != len(self._figure_labels):
            for lab in self._figure_labels:
                lab.deleteLater()
            self._figure_labels = []
            for _png in pngs:
                lab = QLabel()
                self.column.addWidget(lab)
                self._figure_labels.append(lab)
        for lab, png in zip(self._figure_labels, pngs):
            pix = QPixmap()
            pix.loadFromData(png, "PNG")
            lab.setPixmap(pix)

    @staticmethod
    def _eval(expr, values, blocked, namespace):
        """Evaluate one formula. *blocked* cells (still-pending
        formulas) raise KeyError so the pass loop retries later;
        empty cells read as 0."""
        def lookup(r, c):
            if (r, c) in blocked:
                raise KeyError((r, c))
            return values.get((r, c), 0)

        def sub_range(match):
            r1, r2 = sorted((int(match.group(2)), int(match.group(4))))
            c1, c2 = sorted((letter_col(match.group(1)),
                             letter_col(match.group(3))))
            rows = [[lookup(r, c) for c in range(c1, c2 + 1)]
                    for r in range(r1 - 1, r2)]
            if len(rows) == 1:                  # single row -> flat list
                return repr(rows[0])
            if all(len(row) == 1 for row in rows):   # single column
                return repr([row[0] for row in rows])
            return repr(rows)

        def sub_ref(match):
            return repr(lookup(int(match.group(2)) - 1,
                               letter_col(match.group(1))))

        py = _REF.sub(sub_ref, _RANGE.sub(sub_range, expr))
        return eval(py, namespace)   # noqa: S307

    def _publish(self, kernel, values):
        """Expose the computed grid to code cells (sheet1, sheet2, ...)."""
        name = self._kernel_name()
        self.gutter.setText(name)
        grid = [[values.get((r, c)) for c in range(self.table.columnCount())]
                for r in range(self.table.rowCount())]
        kernel.namespace[name] = grid

    def _kernel_name(self) -> str:
        """sheetN by document order among the notebook's sheet cells."""
        w = self.parent()
        while w is not None and not hasattr(w, "cells"):
            w = w.parent()
        cells = getattr(w, "cells", None)
        if cells and self in cells:
            n = 1 + sum(1 for c in cells[:cells.index(self)]
                        if isinstance(c, SheetCell))
        else:
            n = 1
        return f"sheet{n}"

    # -- formula bar -------------------------------------------------------
    def _sync_formula_bar(self, row, col, *_old):
        if row < 0 or col < 0:
            return
        self.ref_label.setText(f"{col_letter(col)}{row + 1}")
        self.formula_edit.setText(self._raw(row, col))

    def _commit_formula(self):
        row, col = self.table.currentRow(), self.table.currentColumn()
        if row < 0 or col < 0:
            row, col = 0, 0
        text = self.formula_edit.text()
        self._set_item(row, col, text, text)
        self.table.setFocus()

    # -- grid plumbing -------------------------------------------------------
    def _raw(self, r, c) -> str:
        item = self.table.item(r, c)
        if item is None:
            return ""
        raw = item.data(Qt.UserRole)
        return raw if raw is not None else item.text()

    def _set_item(self, r, c, raw, display):
        item = self.table.item(r, c)
        if item is None:
            item = QTableWidgetItem()
            self.table.setItem(r, c, item)
        item.setData(Qt.UserRole, raw)
        item.setText(display)

    def _refresh_headers(self):
        self.table.setHorizontalHeaderLabels(
            [col_letter(c) for c in range(self.table.columnCount())])

    def _fit_height(self):
        h = self.table.horizontalHeader().height() + 6
        for r in range(self.table.rowCount()):
            h += self.table.rowHeight(r)
        self.table.setFixedHeight(h)

    def eventFilter(self, obj, event):
        try:
            if (obj is getattr(self, "table", None)
                    and event.type() == QEvent.FocusIn):
                self.focused.emit(self)
            return super().eventFilter(obj, event)
        except RuntimeError:        # widget already deleted at shutdown
            return False

    # -- toolbar operations ---------------------------------------------------
    def add_row(self):
        self.table.insertRow(self.table.rowCount())
        self._fit_height()

    def add_col(self):
        self.table.insertColumn(self.table.columnCount())
        self._refresh_headers()

    def del_row(self):
        if self.table.rowCount() > 1:
            self.table.removeRow(self.table.currentRow()
                                 if self.table.currentRow() >= 0
                                 else self.table.rowCount() - 1)
            self._fit_height()

    def del_col(self):
        if self.table.columnCount() > 1:
            self.table.removeColumn(self.table.currentColumn()
                                    if self.table.currentColumn() >= 0
                                    else self.table.columnCount() - 1)
            self._refresh_headers()


CELL_CLASSES["sheet"] = SheetCell
