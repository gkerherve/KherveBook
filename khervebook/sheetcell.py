"""Sheet cell — an embedded KherveSheet workbook inside a notebook.

One sheet cell holds a whole workbook: several named sheets plus any
plots their formulas produce. Only one view is shown at a time; pick
it from the drop-down on the left or the right-click "View" menu.
Each grid cell may hold a value or an ``=`` formula in Python syntax,
with A1 references, A1:B5 ranges and full access to the notebook
kernel's namespace, so ``=np.pi * A2**2`` works — including variables
from code cells. Formulas recompute automatically as you type.

Adapted from KherveSheet's python_engine.

Copyright (C) 2026 Gwilherm Kerherve

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.
"""

import base64
import json
import re

from PyQt5.QtCore import QEvent, Qt, QTimer
from PyQt5.QtGui import QPixmap
from PyQt5.QtWidgets import (QComboBox, QHBoxLayout, QLabel, QLineEdit,
                             QSizePolicy, QStackedWidget, QStyledItemDelegate,
                             QTableWidget, QTableWidgetItem, QWidget)

from .cells import MONO, CELL_CLASSES, CellWidget
from .kernel import Kernel

_REF = re.compile(r"\b([A-Z]{1,2})(\d{1,3})\b")
_RANGE = re.compile(r"\b([A-Z]{1,2})(\d{1,3})\s*:\s*([A-Z]{1,2})(\d{1,3})\b")

DEFAULT_ROWS, DEFAULT_COLS = 6, 4
MAX_PASSES = 8      # formula chains resolve iteratively
TABLE_MAX_H = 420   # a tall grid scrolls inside itself past this


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


class _ViewStack(QStackedWidget):
    """Sizes to the current page, not the largest — so switching to a
    small plot view shrinks the cell instead of keeping the tall grid."""

    def sizeHint(self):
        w = self.currentWidget()
        return w.sizeHint() if w is not None else super().sizeHint()

    def minimumSizeHint(self):
        w = self.currentWidget()
        return (w.minimumSizeHint() if w is not None
                else super().minimumSizeHint())


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
    """Embedded workbook: many sheets + plots, one view shown at a time."""

    CELL_TYPE = "sheet"

    def __init__(self, source=""):
        super().__init__("")
        self.gutter.setText("sheet")
        self.editor.hide()

        self._tables = []           # one QTableWidget per sheet
        self._names = []            # parallel sheet names
        self._plot_labels = []      # QLabel per plot view (static + formula)
        self._plot_titles = []      # parallel plot-view titles
        self._static_plots = []     # (title, png bytes) imported/persisted
        self._n_static = 0          # how many leading plot views are static
        self._views = []            # [("sheet", i) | ("plot", j), ...]
        self._values = []           # last computed values, per table
        self.table = None           # active grid (None on a plot view)

        # Header: the view selector drop-down, on the left.
        header = QHBoxLayout()
        header.addWidget(QLabel("View:"))
        self.view_combo = QComboBox()
        self.view_combo.setToolTip("Choose which sheet or plot to show")
        self.view_combo.setMinimumWidth(150)
        self.view_combo.currentIndexChanged.connect(self._on_view_changed)
        header.addWidget(self.view_combo)
        header.addStretch(1)
        self.column.addLayout(header)

        # Formula bar (hidden on plot views).
        self._formula_widget = QWidget()
        bar = QHBoxLayout(self._formula_widget)
        bar.setContentsMargins(0, 0, 0, 0)
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
        self.column.addWidget(self._formula_widget)

        self.stack = _ViewStack()
        self.stack.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.column.addWidget(self.stack)

        # Recompute shortly after any edit (Excel-like live formulas).
        self._recalc_timer = QTimer(self)
        self._recalc_timer.setSingleShot(True)
        self._recalc_timer.setInterval(300)
        self._recalc_timer.timeout.connect(self.recalculate)
        self._computed_once = False

        self.set_source(source)

    # -- table factory -----------------------------------------------------
    def _make_table(self) -> QTableWidget:
        table = QTableWidget(DEFAULT_ROWS, DEFAULT_COLS)
        table.setItemDelegate(_RawDelegate(table))
        table.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        table.itemChanged.connect(self._on_item_changed)
        table.currentCellChanged.connect(self._sync_formula_bar)
        table.setContextMenuPolicy(Qt.CustomContextMenu)
        table.customContextMenuRequested.connect(
            lambda pos, t=table: self.menu_requested.emit(
                self, t.viewport().mapToGlobal(pos)))
        table.installEventFilter(self)
        return table

    def _on_item_changed(self, _item):
        self.focused.emit(self)
        self.content_changed.emit()
        self._recalc_timer.start()

    # -- compute lifecycle -------------------------------------------------
    def _notebook(self):
        w = self.parent()
        while w is not None and not hasattr(w, "kernel"):
            w = w.parent()
        return w

    def recalculate(self):
        nb = self._notebook()
        if nb is not None:
            self.execute(nb.kernel)

    def showEvent(self, event):
        super().showEvent(event)
        if not self._computed_once:
            self._recalc_timer.start()

    # -- CellWidget API ----------------------------------------------------
    def source(self) -> str:
        sheets = []
        for name, table in zip(self._names, self._tables):
            data = {}
            for r in range(table.rowCount()):
                for c in range(table.columnCount()):
                    raw = self._raw_of(table, r, c)
                    if raw:
                        data[f"{col_letter(c)}{r + 1}"] = raw
            sheets.append({"name": name, "rows": table.rowCount(),
                           "cols": table.columnCount(), "data": data})
        active = self._names[self._active_sheet()] if self._names else ""
        plots = [{"title": title,
                  "png": base64.b64encode(png).decode("ascii")}
                 for title, png in self._static_plots]
        return json.dumps({"sheets": sheets, "active": active,
                           "plots": plots})

    def set_source(self, text: str):
        # Parse into a list of sheet models (+ any persisted plots).
        models, plot_specs = [], []
        try:
            doc = json.loads(text)
            if isinstance(doc, dict) and "sheets" in doc:
                models = doc["sheets"]
                active_name = doc.get("active", "")
                plot_specs = doc.get("plots", [])
            elif isinstance(doc, dict) and "data" in doc:   # legacy single
                models = [{"name": "Sheet1", **doc}]
                active_name = "Sheet1"
            else:
                raise ValueError
        except Exception:
            # Plain text / CSV: lines as rows, tabs/commas as columns.
            lines = [ln for ln in text.splitlines() if ln.strip()]
            grid = [re.split(r"\t|,", ln) for ln in lines]
            rows = max(DEFAULT_ROWS, len(grid))
            cols = max(DEFAULT_COLS, max((len(r) for r in grid), default=0))
            data = {f"{col_letter(c)}{r + 1}": cell
                    for r, row in enumerate(grid)
                    for c, cell in enumerate(row) if cell.strip()}
            models = [{"name": "Sheet1", "rows": rows, "cols": cols,
                       "data": data}]
            active_name = "Sheet1"
        if not models:
            models = [{"name": "Sheet1", "rows": DEFAULT_ROWS,
                       "cols": DEFAULT_COLS, "data": {}}]
            active_name = "Sheet1"

        # Tear down any previous tables/plots.
        for table in self._tables:
            self.stack.removeWidget(table)
            table.deleteLater()
        for lab in self._plot_labels:
            self.stack.removeWidget(lab)
            lab.deleteLater()
        self._tables, self._names = [], []
        self._plot_labels, self._plot_titles = [], []

        for i, model in enumerate(models):
            name = str(model.get("name") or f"Sheet{i + 1}")
            table = self._make_table()
            self._populate(table, model)
            self._fit_table(table)
            self._tables.append(table)
            self._names.append(name)
            self.stack.addWidget(table)
        self.table = self._tables[0]

        # Static (imported / persisted) plot views come first.
        self._static_plots = []
        for spec in plot_specs:
            try:
                png = base64.b64decode(spec["png"])
            except Exception:
                continue
            self._static_plots.append((spec.get("title", "Plot"), png))
            self._plot_labels.append(self._make_plot_label(png))
            self._plot_titles.append(spec.get("title", "Plot"))
        self._n_static = len(self._static_plots)

        names = [n for n in self._names]
        start = names.index(active_name) if active_name in names else 0
        self._rebuild_views(select=("sheet", start))

    @staticmethod
    def _populate(table, model):
        rows = int(model.get("rows", DEFAULT_ROWS))
        cols = int(model.get("cols", DEFAULT_COLS))
        table.blockSignals(True)
        table.setRowCount(rows)
        table.setColumnCount(cols)
        table.setHorizontalHeaderLabels([col_letter(c) for c in range(cols)])
        for ref, raw in (model.get("data") or {}).items():
            m = _REF.fullmatch(ref)
            if not m:
                continue
            r, c = int(m.group(2)) - 1, letter_col(m.group(1))
            if r < rows and c < cols:
                item = QTableWidgetItem()
                item.setData(Qt.UserRole, raw)
                item.setText(raw)
                table.setItem(r, c, item)
        table.blockSignals(False)

    def execute(self, kernel):
        """Recompute every sheet, gather plots, publish grids to kernel."""
        self._computed_once = True
        kernel._seed_namespace()
        self._values = []
        all_pngs = []
        for table in self._tables:
            values, pngs = self._compute_table(table, kernel)
            self._values.append(values)
            all_pngs.extend(pngs)
        self._rebuild_plots(all_pngs)
        self._publish(kernel)

    def _compute_table(self, table, kernel):
        """Resolve one grid's formulas; return (values, [plot pngs])."""
        plt = kernel.namespace.get("plt")
        before = set(plt.get_fignums()) if plt else set()
        values, formulas = {}, {}
        for r in range(table.rowCount()):
            for c in range(table.columnCount()):
                raw = self._raw_of(table, r, c)
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
                    continue
                except Exception as exc:
                    values[rc] = f"#ERR {exc.__class__.__name__}"
                del pending[rc]
                progressed = True
            if not progressed:
                break
        for rc in pending:
            values[rc] = "#ERR circular"

        pngs, captured = [], set()
        table.blockSignals(True)
        for rc in formulas:
            raw = self._raw_of(table, *rc)
            value = values[rc]
            if Kernel._is_figure(value):
                pngs.append(Kernel._fig_png(value))
                captured.add(getattr(value, "number", None))
                values[rc] = "[plot]"
                self._set_item_of(table, rc[0], rc[1], raw, "[plot]")
            else:
                self._set_item_of(table, rc[0], rc[1], raw,
                                  format_value(value))
        table.blockSignals(False)
        if plt:
            for num in plt.get_fignums():
                if num in before:
                    continue
                if num not in captured:
                    pngs.append(Kernel._fig_png(plt.figure(num)))
                plt.close(num)
        return values, pngs

    @staticmethod
    def _eval(expr, values, blocked, namespace):
        """Evaluate one formula; empty cells read 0, pending cells retry."""
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
            if len(rows) == 1:
                return repr(rows[0])
            if all(len(row) == 1 for row in rows):
                return repr([row[0] for row in rows])
            return repr(rows)

        def sub_ref(match):
            return repr(lookup(int(match.group(2)) - 1,
                               letter_col(match.group(1))))

        py = _REF.sub(sub_ref, _RANGE.sub(sub_range, expr))
        return eval(py, namespace)   # noqa: S307

    def _publish(self, kernel):
        """Expose each sheet to code cells as sheet1, sheet2, ... globally."""
        base = self._global_sheet_base()
        for i, table in enumerate(self._tables):
            values = self._values[i] if i < len(self._values) else {}
            grid = [[values.get((r, c))
                     for c in range(table.columnCount())]
                    for r in range(table.rowCount())]
            kernel.namespace[f"sheet{base + i + 1}"] = grid
        self.gutter.setText("sheet")

    def _global_sheet_base(self) -> int:
        w = self.parent()
        while w is not None and not hasattr(w, "cells"):
            w = w.parent()
        cells = getattr(w, "cells", None)
        if not cells or self not in cells:
            return 0
        return sum(len(c._tables) for c in cells[:cells.index(self)]
                   if isinstance(c, SheetCell))

    # -- views (sheets + plots) -------------------------------------------
    def _active_sheet(self) -> int:
        kind, i = (self._views[self.view_combo.currentIndex()]
                   if self._views else ("sheet", 0))
        return i if kind == "sheet" else 0

    def _make_plot_label(self, png) -> QLabel:
        lab = QLabel()
        lab.setAlignment(Qt.AlignCenter)
        pix = QPixmap()
        pix.loadFromData(png, "PNG")
        lab.setPixmap(pix)
        self.stack.addWidget(lab)
        return lab

    def _rebuild_plots(self, pngs):
        """Refresh formula plot views, keeping static plots and selection."""
        prev = (self._views[self.view_combo.currentIndex()]
                if self._views and self.view_combo.currentIndex() >= 0
                else ("sheet", 0))
        # Drop only the formula plots (the static ones lead the list).
        for lab in self._plot_labels[self._n_static:]:
            self.stack.removeWidget(lab)
            lab.deleteLater()
        self._plot_labels = self._plot_labels[:self._n_static]
        self._plot_titles = self._plot_titles[:self._n_static]
        for k, png in enumerate(pngs):
            self._plot_labels.append(self._make_plot_label(png))
            self._plot_titles.append(f"Plot {self._n_static + k + 1}")
        if prev[0] == "plot" and prev[1] >= len(self._plot_labels):
            prev = ("sheet", self._active_sheet())
        self._rebuild_views(select=prev)

    def _rebuild_views(self, select=("sheet", 0)):
        self._views = ([("sheet", i) for i in range(len(self._tables))]
                       + [("plot", j) for j in range(len(self._plot_labels))])
        titles = list(self._names) + list(self._plot_titles)
        try:
            index = self._views.index(tuple(select))
        except ValueError:
            index = 0
        self.view_combo.blockSignals(True)
        self.view_combo.clear()
        self.view_combo.addItems(titles)
        self.view_combo.setCurrentIndex(max(0, index))
        self.view_combo.blockSignals(False)
        self._on_view_changed(self.view_combo.currentIndex())

    def _on_view_changed(self, index):
        if not self._views or index < 0:
            return
        self.stack.setCurrentIndex(index)
        kind, i = self._views[index]
        if kind == "sheet":
            self.table = self._tables[i]
            self._formula_widget.show()
            self._sync_formula_bar(self.table.currentRow(),
                                   self.table.currentColumn())
            self._fit_table(self.table)
        else:
            self.table = None
            self._formula_widget.hide()
        self.stack.updateGeometry()

    # -- right-click view menu helpers (used by NotebookWidget) -----------
    def view_titles(self):
        return [self.view_combo.itemText(k)
                for k in range(self.view_combo.count())]

    def current_view_index(self) -> int:
        return self.view_combo.currentIndex()

    def set_view_index(self, index: int):
        self.view_combo.setCurrentIndex(index)

    # -- formula bar -------------------------------------------------------
    def _sync_formula_bar(self, row, col, *_old):
        if self.table is None or row < 0 or col < 0:
            return
        self.ref_label.setText(f"{col_letter(col)}{row + 1}")
        self.formula_edit.setText(self._raw_of(self.table, row, col))

    def _commit_formula(self):
        if self.table is None:
            return
        row = max(0, self.table.currentRow())
        col = max(0, self.table.currentColumn())
        text = self.formula_edit.text()
        self._set_item_of(self.table, row, col, text, text)
        self.table.setFocus()

    # -- grid plumbing -----------------------------------------------------
    @staticmethod
    def _raw_of(table, r, c) -> str:
        item = table.item(r, c)
        if item is None:
            return ""
        raw = item.data(Qt.UserRole)
        return raw if raw is not None else item.text()

    @staticmethod
    def _set_item_of(table, r, c, raw, display):
        item = table.item(r, c)
        if item is None:
            item = QTableWidgetItem()
            table.setItem(r, c, item)
        item.setData(Qt.UserRole, raw)
        item.setText(display)

    def _raw(self, r, c) -> str:
        return self._raw_of(self.table, r, c) if self.table else ""

    def _set_item(self, r, c, raw, display):
        if self.table is not None:
            self._set_item_of(self.table, r, c, raw, display)

    @staticmethod
    def _table_height(table) -> int:
        h = table.horizontalHeader().height() + 6
        for r in range(table.rowCount()):
            h += table.rowHeight(r)
        return h

    def _fit_table(self, table):
        """Size a grid to its rows, but cap tall grids (they scroll)."""
        table.setFixedHeight(min(self._table_height(table), TABLE_MAX_H))

    def eventFilter(self, obj, event):
        try:
            if (event.type() == QEvent.FocusIn
                    and obj in getattr(self, "_tables", [])):
                self.focused.emit(self)
            return CellWidget.eventFilter(self, obj, event)
        except RuntimeError:
            return False

    # -- toolbar operations (active grid) ---------------------------------
    def add_row(self):
        if self.table is None:
            return
        self.table.insertRow(self.table.rowCount())
        self._fit_table(self.table)
        self.stack.updateGeometry()
        self.content_changed.emit()

    def add_col(self):
        if self.table is None:
            return
        self.table.insertColumn(self.table.columnCount())
        self.table.setHorizontalHeaderLabels(
            [col_letter(c) for c in range(self.table.columnCount())])
        self.content_changed.emit()

    def del_row(self):
        if self.table is None or self.table.rowCount() <= 1:
            return
        row = self.table.currentRow()
        self.table.removeRow(row if row >= 0 else self.table.rowCount() - 1)
        self._fit_table(self.table)
        self.stack.updateGeometry()
        self.content_changed.emit()

    def del_col(self):
        if self.table is None or self.table.columnCount() <= 1:
            return
        col = self.table.currentColumn()
        self.table.removeColumn(
            col if col >= 0 else self.table.columnCount() - 1)
        self.table.setHorizontalHeaderLabels(
            [col_letter(c) for c in range(self.table.columnCount())])
        self.content_changed.emit()

    def add_sheet(self):
        """Append a new blank sheet and switch to it."""
        n = len(self._tables) + 1
        name = f"Sheet{n}"
        while name in self._names:
            n += 1
            name = f"Sheet{n}"
        table = self._make_table()
        self._populate(table, {"rows": DEFAULT_ROWS, "cols": DEFAULT_COLS,
                               "data": {}})
        self._tables.append(table)
        self._names.append(name)
        self.stack.addWidget(table)
        self.table = table
        self._rebuild_views(select=("sheet", len(self._tables) - 1))
        self.content_changed.emit()


CELL_CLASSES["sheet"] = SheetCell
