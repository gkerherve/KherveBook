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

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (QSizePolicy, QStyledItemDelegate, QTableWidget,
                             QTableWidgetItem)

from .cells import CELL_CLASSES, CellWidget

_REF = re.compile(r"\b([A-Z]{1,2})(\d{1,3})\b")

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

        self.table = QTableWidget(DEFAULT_ROWS, DEFAULT_COLS)
        self.table.setItemDelegate(_RawDelegate(self.table))
        self.table.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.table.itemChanged.connect(lambda _item: self.focused.emit(self))
        self.table.installEventFilter(self)
        self.column.addWidget(self.table)
        self._refresh_headers()
        self._fit_height()

        if source:
            self.set_source(source)

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
        """Recompute every =formula against the kernel namespace."""
        kernel._seed_namespace()
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
                try:
                    values[rc] = self._eval(expr, values, kernel.namespace)
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

        self.table.blockSignals(True)
        for rc, expr in formulas.items():
            raw = self._raw(*rc)
            self._set_item(rc[0], rc[1], raw, format_value(values[rc]))
        self.table.blockSignals(False)

    @staticmethod
    def _eval(expr, values, namespace):
        def sub(match):
            r = int(match.group(2)) - 1
            c = letter_col(match.group(1))
            return repr(values[(r, c)])      # KeyError -> retry next pass
        return eval(_REF.sub(sub, expr), namespace)   # noqa: S307

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
        if (obj is getattr(self, "table", None)
                and event.type() == event.FocusIn):
            self.focused.emit(self)
        return super().eventFilter(obj, event)

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
