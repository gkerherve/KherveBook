"""Lab cell — a structured lab record: measurements, protocol steps, an
instrument run, a reaction or a safety assessment.

Modelled on kELN's blocks (KherveOS). Each kind has its own small editor;
the data, the sums (mean ± sd, mmol / equivalents / yield, molar mass
from a formula) and the Markdown export live Qt-free in `labmath`.

``source`` is JSON ``{"kbook_lab": 1, "kind": …, "data": {…}}``. Every
committed edit is reported through ``source_edited`` so the notebook can
put it on its undo stack (table edits have no editor-local undo).
Code reads a lab cell with ``klab()`` — a DataFrame for tables.

Copyright (C) 2026 Gwilherm Kerherve

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.
"""

import datetime
import getpass
import json

from PyQt5.QtCore import QSettings, Qt, pyqtSignal
from PyQt5.QtGui import QColor, QFont, QKeySequence
from PyQt5.QtWidgets import (QAbstractItemView, QApplication, QCheckBox,
                             QComboBox, QCompleter, QFormLayout, QFrame,
                             QGridLayout, QHBoxLayout, QHeaderView,
                             QInputDialog, QLabel, QLineEdit, QMessageBox,
                             QPlainTextEdit, QPushButton, QTableWidget,
                             QTableWidgetItem, QToolButton, QVBoxLayout,
                             QWidget)

from . import labmath as lm
from .cells import CELL_CLASSES, CellWidget
from .icons import icon

_KIND_ICONS = {"measurements": "mdi.table-large",
               "steps": "mdi.format-list-checks",
               "run": "mdi.chart-bell-curve",
               "reaction": "mdi.flask-round-bottom-outline",
               "safety": "mdi.shield-alert-outline"}
#: item data role marking a reaction MW filled in from the formula
_AUTO = Qt.UserRole + 1


def lab_user() -> str:
    """Who stamps a step: the name set in the app, else the login name."""
    name = QSettings("Kherve", "KherveBook").value("lab/user", "", type=str)
    if name:
        return name
    try:
        return getpass.getuser()
    except Exception:
        return ""


def _now() -> str:
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M")


def starter(kind: str) -> str:
    """The source of a new, empty lab cell of *kind*."""
    return json.dumps({"kbook_lab": 1, "kind": kind,
                       "data": lm.default_data(kind)})


def _button(text, tip, slot, ic=None):
    b = QToolButton()
    b.setText(text)
    b.setToolTip(tip)
    b.setAutoRaise(True)
    if ic:
        b.setIcon(icon(ic))
        b.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
    b.clicked.connect(slot)
    return b


class _Notes(QPlainTextEdit):
    """A small text box that commits when focus leaves."""

    committed = pyqtSignal()

    def __init__(self, placeholder, height=60):
        super().__init__()
        self.setPlaceholderText(placeholder)
        self.setFixedHeight(height)
        self._was = ""

    def setPlainText(self, text):
        super().setPlainText(text)
        self._was = text

    def focusOutEvent(self, event):
        super().focusOutEvent(event)
        if self.toPlainText() != self._was:
            self._was = self.toPlainText()
            self.committed.emit()


class _Grid(QTableWidget):
    """A table that grows to its rows (the notebook scrolls, not the
    table) and pastes tab-separated blocks from a spreadsheet."""

    pasted = pyqtSignal()

    def __init__(self, rows, cols):
        super().__init__(rows, cols)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.verticalHeader().setDefaultSectionSize(26)
        self.setEditTriggers(QAbstractItemView.AllEditTriggers)

    def fit(self):
        h = self.horizontalHeader().height() + 4
        h += sum(self.rowHeight(r) for r in range(self.rowCount()))
        if self.horizontalScrollBar().isVisible():
            h += self.horizontalScrollBar().height()
        self.setFixedHeight(max(h, 60))

    def text(self, r, c):
        it = self.item(r, c)
        return it.text() if it is not None else ""

    def keyPressEvent(self, event):
        if event.matches(QKeySequence.Paste):
            self._paste(QApplication.clipboard().text())
            return
        if event.key() in (Qt.Key_Delete, Qt.Key_Backspace) and \
                self.state() != QAbstractItemView.EditingState:
            for it in self.selectedItems():
                if it.flags() & Qt.ItemIsEditable:
                    it.setText("")
            return
        super().keyPressEvent(event)

    def _paste(self, text):
        rows = [r.split("\t") for r in text.rstrip("\n").split("\n")]
        if not rows or not text:
            return
        r0 = max(self.currentRow(), 0)
        c0 = max(self.currentColumn(), 0)
        self.blockSignals(True)
        if r0 + len(rows) > self.rowCount():
            self.setRowCount(r0 + len(rows))
        for i, row in enumerate(rows):
            for j, value in enumerate(row):
                c = c0 + j
                if c >= self.columnCount():
                    break
                it = self.item(r0 + i, c)
                if it is None:
                    it = QTableWidgetItem()
                    self.setItem(r0 + i, c, it)
                if it.flags() & Qt.ItemIsEditable:
                    it.setText(value.strip())
        self.blockSignals(False)
        self.fit()
        self.pasted.emit()


class _Editor(QWidget):
    """One kind's editor: ``data()`` / ``set_data()`` and ``changed``."""

    changed = pyqtSignal()

    def __init__(self):
        super().__init__()
        self.lay = QVBoxLayout(self)
        self.lay.setContentsMargins(0, 0, 0, 0)
        self.lay.setSpacing(4)

    def add_row(self):
        pass


# -- measurements -----------------------------------------------------------
class _Measurements(_Editor):
    def __init__(self):
        super().__init__()
        self.cols = []
        self.grid = _Grid(0, 0)
        self.grid.itemChanged.connect(self._edited)
        self.grid.pasted.connect(self._edited)
        self.grid.horizontalHeader().sectionDoubleClicked.connect(
            self.rename_column)
        self.lay.addWidget(self.grid)
        bar = QHBoxLayout()
        bar.addWidget(_button("Row", "Add a row", self.add_row, "mdi.plus"))
        bar.addWidget(_button("Column", "Add a column", self.add_column,
                              "mdi.table-column-plus-after"))
        bar.addWidget(_button("Remove", "Remove the selected rows (or the "
                              "selected column when a whole column is "
                              "selected)", self.remove, "mdi.minus"))
        bar.addStretch(1)
        hint = QLabel("Double-click a header to rename it · Ctrl+V pastes "
                      "from a spreadsheet")
        hint.setStyleSheet("color: #8a939c;")
        bar.addWidget(hint)
        self.lay.addLayout(bar)
        self.stats = QLabel("")
        self.stats.setWordWrap(True)
        self.stats.setStyleSheet("color: #33506b;")
        self.lay.addWidget(self.stats)

    def set_data(self, d):
        self.cols = [dict(c) for c in d["columns"]]
        g = self.grid
        g.blockSignals(True)
        g.clear()
        g.setColumnCount(len(self.cols))
        g.setRowCount(len(d["rows"]))
        self._headers()
        for r, row in enumerate(d["rows"]):
            for c, v in enumerate(row):
                g.setItem(r, c, QTableWidgetItem(v))
        g.blockSignals(False)
        g.fit()
        self._stats()

    def data(self):
        g = self.grid
        rows = [[g.text(r, c) for c in range(len(self.cols))]
                for r in range(g.rowCount())]
        return {"columns": [dict(c) for c in self.cols], "rows": rows}

    def _headers(self):
        self.grid.setHorizontalHeaderLabels(
            [lm.column_label(c) for c in self.cols])

    def _stats(self):
        g = self.grid
        bits = []
        for c, col in enumerate(self.cols):
            values = [g.text(r, c) for r in range(g.rowCount())]
            filled = [v for v in values if v.strip()]
            # Only a column that is all numbers gets a mean (a Sample column
            # of IDs is left alone).
            if filled and all(lm.number(v) is not None for v in filled):
                bits.append(f"<b>{lm.column_label(col)}</b>: "
                            f"{lm.stats_text(filled)}")
        self.stats.setText(" &nbsp;·&nbsp; ".join(bits))
        self.stats.setVisible(bool(bits))

    def _edited(self, *_):
        self._stats()
        self.changed.emit()

    def add_row(self):
        self.grid.setRowCount(self.grid.rowCount() + 1)
        self.grid.fit()
        self.changed.emit()

    def add_column(self):
        name, ok = QInputDialog.getText(self, "New column", "Column name:")
        if not ok or not name.strip():
            return
        unit, _ok = QInputDialog.getText(self, "New column",
                                         "Unit (optional):")
        self.cols.append({"name": name.strip(), "unit": unit.strip()})
        self.grid.setColumnCount(len(self.cols))
        self._headers()
        self.changed.emit()

    def rename_column(self, c):
        col = self.cols[c]
        name, ok = QInputDialog.getText(self, "Rename column", "Column name:",
                                        text=col["name"])
        if not ok or not name.strip():
            return
        unit, ok = QInputDialog.getText(self, "Rename column", "Unit:",
                                        text=col["unit"])
        col.update(name=name.strip(), unit=unit.strip() if ok else col["unit"])
        self._headers()
        self._edited()

    def remove(self):
        g = self.grid
        sel = g.selectionModel()
        cols = [i.column() for i in sel.selectedColumns()]
        if cols and len(self.cols) > 1:
            for c in sorted(cols, reverse=True)[:len(self.cols) - 1]:
                g.removeColumn(c)
                del self.cols[c]
        else:
            rows = sorted({i.row() for i in g.selectedIndexes()}
                          or ({g.currentRow()} - {-1}), reverse=True)
            for r in rows:
                g.removeRow(r)
        g.fit()
        self._edited()


# -- protocol steps -----------------------------------------------------------
class _Steps(_Editor):
    def __init__(self):
        super().__init__()
        self.grid = _Grid(0, 4)
        self.grid.setHorizontalHeaderLabels(["Done", "Step", "Done by", "At"])
        hh = self.grid.horizontalHeader()
        for c in (0, 2, 3):
            hh.setSectionResizeMode(c, QHeaderView.ResizeToContents)
        self.grid.itemChanged.connect(self._item_changed)
        self.grid.pasted.connect(self.changed.emit)
        self.lay.addWidget(self.grid)
        bar = QHBoxLayout()
        bar.addWidget(_button("Step", "Add a step", self.add_row, "mdi.plus"))
        bar.addWidget(_button("Remove", "Remove the selected steps",
                              self.remove, "mdi.minus"))
        bar.addStretch(1)
        self.progress = QLabel("")
        self.progress.setStyleSheet("color: #5b6670;")
        bar.addWidget(self.progress)
        self.lay.addLayout(bar)

    def _row(self, r, step):
        check = QTableWidgetItem()
        check.setFlags(Qt.ItemIsUserCheckable | Qt.ItemIsEnabled
                       | Qt.ItemIsSelectable)
        check.setCheckState(Qt.Checked if step["done"] else Qt.Unchecked)
        self.grid.setItem(r, 0, check)
        self.grid.setItem(r, 1, QTableWidgetItem(step["text"]))
        for c, key in ((2, "by"), (3, "at")):
            it = QTableWidgetItem(step[key])
            it.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
            it.setForeground(QColor("#5b6670"))
            self.grid.setItem(r, c, it)

    def set_data(self, d):
        g = self.grid
        g.blockSignals(True)
        g.setRowCount(len(d["steps"]))
        for r, step in enumerate(d["steps"]):
            self._row(r, step)
        g.blockSignals(False)
        g.fit()
        self._progress()

    def data(self):
        g = self.grid
        return {"steps": [{"text": g.text(r, 1),
                           "done": g.item(r, 0) is not None and
                           g.item(r, 0).checkState() == Qt.Checked,
                           "by": g.text(r, 2), "at": g.text(r, 3)}
                          for r in range(g.rowCount())]}

    def _item_changed(self, item):
        if item.column() == 0:
            # Ticking a step stamps who did it and when; unticking clears.
            done = item.checkState() == Qt.Checked
            g = self.grid
            g.blockSignals(True)
            g.item(item.row(), 2).setText(lab_user() if done else "")
            g.item(item.row(), 3).setText(_now() if done else "")
            g.blockSignals(False)
            g.resizeColumnsToContents()
            g.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self._progress()
        self.changed.emit()

    def _progress(self):
        steps = self.data()["steps"]
        done = sum(s["done"] for s in steps)
        self.progress.setText(f"{done} / {len(steps)} done" if steps else "")

    def add_row(self):
        r = self.grid.rowCount()
        self.grid.blockSignals(True)
        self.grid.setRowCount(r + 1)
        self._row(r, {"text": "", "done": False, "by": "", "at": ""})
        self.grid.blockSignals(False)
        self.grid.fit()
        self._progress()
        self.changed.emit()

    def remove(self):
        rows = sorted({i.row() for i in self.grid.selectedIndexes()},
                      reverse=True)
        for r in rows:
            self.grid.removeRow(r)
        self.grid.fit()
        self._progress()
        self.changed.emit()


# -- instrument run -----------------------------------------------------------
class _Run(_Editor):
    def __init__(self):
        super().__init__()
        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignRight)
        self.fields = {}
        recent = QSettings("Kherve", "KherveBook").value(
            "lab/instruments", [], type=list)
        for key, label in lm.RUN_FIELDS:
            edit = QLineEdit()
            edit.editingFinished.connect(self._commit)
            self.fields[key] = edit
            row = QHBoxLayout()
            row.addWidget(edit, 1)
            if key in ("start", "end"):
                row.addWidget(_button("Now", "Stamp the current time",
                                      lambda _=False, e=edit: self._stamp(e)))
            elif key == "file":
                row.addWidget(_button("…", "Choose the data file",
                                      self._choose_file))
            elif key == "instrument":
                edit.setCompleter(QCompleter(recent, edit))
                edit.setPlaceholderText("e.g. Kratos Axis Supra")
            elif key == "operator":
                edit.setPlaceholderText(lab_user())
            form.addRow(label, row)
        self.lay.addLayout(form)
        self.params = _Notes("Parameters — one per line, e.g. pass energy "
                             "= 20 eV", 70)
        self.notes = _Notes("Notes")
        for w in (self.params, self.notes):
            w.committed.connect(self.changed.emit)
            self.lay.addWidget(w)

    def _stamp(self, edit):
        edit.setText(_now())
        self._commit()

    def _choose_file(self):
        from . import filedialog
        name = filedialog.open_file(self, "Data file", "", "All files (*)")
        if name:
            self.fields["file"].setText(name)
            self._commit()

    def _commit(self):
        name = self.fields["instrument"].text().strip()
        if name:
            s = QSettings("Kherve", "KherveBook")
            recent = [n for n in s.value("lab/instruments", [], type=list)
                      if n != name]
            s.setValue("lab/instruments", ([name] + recent)[:20])
        self.changed.emit()

    def set_data(self, d):
        for key, edit in self.fields.items():
            edit.setText(d[key])
        self.params.setPlainText(d["params"])
        self.notes.setPlainText(d["notes"])

    def data(self):
        d = {k: e.text() for k, e in self.fields.items()}
        d.update(params=self.params.toPlainText(),
                 notes=self.notes.toPlainText())
        return d


# -- reaction ---------------------------------------------------------------
class _Reaction(_Editor):
    _COLS = [k for k, _ in lm.REACTION_COLS]

    def __init__(self):
        super().__init__()
        heads = [h for _, h in lm.REACTION_COLS] + ["→ mmol · equiv"]
        self.grid = _Grid(0, len(heads))
        self.grid.setHorizontalHeaderLabels(heads)
        # Nine columns do not fit a cell at equal widths: numbers take what
        # they need and the name takes the rest.
        hh = self.grid.horizontalHeader()
        hh.setSectionResizeMode(QHeaderView.ResizeToContents)
        hh.setSectionResizeMode(0, QHeaderView.Stretch)
        self.grid.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.grid.itemChanged.connect(self._item_changed)
        self.grid.pasted.connect(self._recompute)
        self.lay.addWidget(self.grid)
        bar = QHBoxLayout()
        bar.addWidget(_button("Row", "Add a reagent", self.add_row,
                              "mdi.plus"))
        bar.addWidget(_button("Remove", "Remove the selected rows",
                              self.remove, "mdi.minus"))
        bar.addSpacing(12)
        bar.addWidget(QLabel("Actual yield (mg)"))
        self.actual = QLineEdit()
        self.actual.setFixedWidth(90)
        self.actual.editingFinished.connect(self._recompute)
        bar.addWidget(self.actual)
        bar.addStretch(1)
        self.lay.addLayout(bar)
        self.result = QLabel("")
        self.result.setWordWrap(True)
        self.result.setStyleSheet("color: #33506b; font-weight: 600;")
        self.lay.addWidget(self.result)
        hint = QLabel("mmol comes from mass ÷ MW, or volume × density; MW "
                      "from the formula when left blank (grey). Equivalents "
                      "are relative to the limiting reactant (bold).")
        hint.setWordWrap(True)
        hint.setStyleSheet("color: #8a939c;")
        self.lay.addWidget(hint)
        self.notes = _Notes("Procedure notes")
        self.notes.committed.connect(self.changed.emit)
        self.lay.addWidget(self.notes)

    def _role_box(self, role):
        box = QComboBox()
        box.addItems(lm.ROLES)
        box.setCurrentText(role)
        box.currentTextChanged.connect(lambda _t: self._recompute())
        return box

    def _set_row(self, r, row):
        for c, key in enumerate(self._COLS):
            if key == "role":
                self.grid.setCellWidget(r, c, self._role_box(row["role"]))
            else:
                self.grid.setItem(r, c, QTableWidgetItem(row[key]))
        eq = QTableWidgetItem("")
        eq.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
        self.grid.setItem(r, len(self._COLS), eq)

    def set_data(self, d):
        g = self.grid
        g.blockSignals(True)
        g.setRowCount(len(d["rows"]))
        for r, row in enumerate(d["rows"]):
            self._set_row(r, row)
        g.blockSignals(False)
        self.actual.setText(d["actual"])
        self.notes.setPlainText(d["notes"])
        g.fit()
        self._show_calc()

    def data(self):
        g, rows = self.grid, []
        for r in range(g.rowCount()):
            row = {}
            for c, key in enumerate(self._COLS):
                if key == "role":
                    box = g.cellWidget(r, c)
                    row[key] = box.currentText() if box else "reactant"
                else:
                    it = g.item(r, c)
                    # An MW shown from the formula is not the user's value.
                    row[key] = "" if it is None or it.data(_AUTO) \
                        else it.text()
            rows.append(row)
        return {"rows": rows, "actual": self.actual.text(),
                "notes": self.notes.toPlainText()}

    def _item_changed(self, item):
        if item.column() == self._COLS.index("mw"):
            # Typed over the formula's value: it is the user's MW now.
            item.setData(_AUTO, False)
            f = item.font()
            f.setItalic(False)
            item.setFont(f)
            item.setForeground(QColor())
        self._recompute()

    def _recompute(self):
        self._show_calc()
        self.changed.emit()

    def _show_calc(self):
        d = self.data()
        calc = lm.reaction_compute(d)
        g = self.grid
        mw_c = self._COLS.index("mw")
        mmol_c = self._COLS.index("mmol")
        g.blockSignals(True)
        for r, (row, c) in enumerate(zip(d["rows"], calc["rows"])):
            mw_item = g.item(r, mw_c)
            if mw_item is not None and not row["mw"]:
                auto = lm.molar_mass(row["formula"])
                mw_item.setText(lm.fmt(auto, 6) if auto else "")
                mw_item.setData(_AUTO, True)
                f = mw_item.font()
                f.setItalic(True)
                mw_item.setFont(f)
                mw_item.setForeground(QColor("#8a939c"))
            mmol_item = g.item(r, mmol_c)
            if mmol_item is not None:
                mmol_item.setToolTip(
                    f"computed: {lm.fmt(c['mmol'])} mmol — type a value "
                    "to override" if c["mmol"] and not row["mmol"] else "")
            eq = g.item(r, len(self._COLS))
            if eq is not None:
                bits = [f"{lm.fmt(c['mmol'])} mmol"] if c["mmol"] else []
                if c["equiv"]:
                    bits.append(f"{lm.fmt(c['equiv'], 3)} eq")
                eq.setText(" · ".join(bits))
                bold = QFont()
                bold.setBold(r == calc["limiting"])
                eq.setFont(bold)
        g.blockSignals(False)
        bits = []
        if calc["limiting"] is not None:
            name = d["rows"][calc["limiting"]]["name"] or \
                f"row {calc['limiting'] + 1}"
            bits.append(f"Limiting: {name}")
        if calc["theoretical_mg"] is not None:
            bits.append(f"theoretical {lm.fmt(calc['theoretical_mg'])} mg")
        if calc["yield_pct"] is not None:
            bits.append(f"yield {calc['yield_pct']:.1f} %")
        self.result.setText(" · ".join(bits))

    def add_row(self):
        r = self.grid.rowCount()
        self.grid.blockSignals(True)
        self.grid.setRowCount(r + 1)
        self._set_row(r, {k: "" for k in self._COLS} | {"role": "reagent"})
        self.grid.blockSignals(False)
        self.grid.fit()
        self._recompute()

    def remove(self):
        for r in sorted({i.row() for i in self.grid.selectedIndexes()},
                        reverse=True):
            self.grid.removeRow(r)
        self.grid.fit()
        self._recompute()


# -- safety -------------------------------------------------------------------
class _Safety(_Editor):
    def __init__(self):
        super().__init__()
        top = QHBoxLayout()
        top.addWidget(QLabel("Risk"))
        self.risk = QComboBox()
        self.risk.addItems(lm.RISKS)
        self.risk.activated.connect(lambda _i: self._risk_changed())
        top.addWidget(self.risk)
        top.addStretch(1)
        self.lay.addLayout(top)
        self.lay.addWidget(QLabel("<b>GHS hazard pictograms</b>"))
        grid = QGridLayout()
        self.ghs = {}
        for i, (code, name) in enumerate(lm.GHS):
            box = QCheckBox(f"{code} {name}")
            box.toggled.connect(lambda _on: self.changed.emit())
            self.ghs[code] = box
            grid.addWidget(box, i // 3, i % 3)
        self.lay.addLayout(grid)
        self.lay.addWidget(QLabel("<b>Protective equipment / controls</b>"))
        ppe = QGridLayout()
        self.ppe = {}
        for i, name in enumerate(lm.PPE):
            box = QCheckBox(name)
            box.toggled.connect(lambda _on: self.changed.emit())
            self.ppe[name] = box
            ppe.addWidget(box, i // 3, i % 3)
        self.lay.addLayout(ppe)
        self.texts = {}
        for key, hint in (("hazards", "Hazards — substances, energies, "
                                      "what could go wrong"),
                          ("controls", "Controls — how each hazard is "
                                       "reduced"),
                          ("waste", "Waste and disposal")):
            box = _Notes(hint, 52)
            box.committed.connect(self.changed.emit)
            self.texts[key] = box
            self.lay.addWidget(box)

    def _risk_changed(self):
        self._paint_risk()
        self.changed.emit()

    def _paint_risk(self):
        colour = {"low": "#2e7d32", "medium": "#b26a00",
                  "high": "#c62828"}[self.risk.currentText()]
        self.risk.setStyleSheet(f"color: {colour}; font-weight: 600;")

    def set_data(self, d):
        self.risk.setCurrentText(d["risk"])
        self._paint_risk()
        for code, box in self.ghs.items():
            box.blockSignals(True)
            box.setChecked(code in d["ghs"])
            box.blockSignals(False)
        for name, box in self.ppe.items():
            box.blockSignals(True)
            box.setChecked(name in d["ppe"])
            box.blockSignals(False)
        for key, box in self.texts.items():
            box.setPlainText(d[key])

    def data(self):
        d = {"risk": self.risk.currentText(),
             "ghs": [c for c, b in self.ghs.items() if b.isChecked()],
             "ppe": [n for n, b in self.ppe.items() if b.isChecked()]}
        d.update({k: b.toPlainText() for k, b in self.texts.items()})
        return d


_EDITORS = {"measurements": _Measurements, "steps": _Steps, "run": _Run,
            "reaction": _Reaction, "safety": _Safety}


class LabCell(CellWidget):
    """A structured lab record of one kind."""

    CELL_TYPE = "lab"
    #: (self, old source, new source) after each committed edit
    source_edited = pyqtSignal(object, str, str)

    def __init__(self, source=""):
        super().__init__(source)
        self.gutter.setText("lab")
        self.editor.hide()
        self.kind = "measurements"
        self._ed = None
        self._loading = False
        card = QFrame()
        card.setObjectName("lab_card")
        card.setStyleSheet("#lab_card { border: 1px solid #dde3ea; "
                           "border-radius: 6px; background: #fbfcfe; }")
        self._card = QVBoxLayout(card)
        self._card.setContentsMargins(8, 6, 8, 8)
        head = QHBoxLayout()
        self._mark = QLabel()
        head.addWidget(self._mark)
        self._kind_box = QComboBox()
        for key, label in lm.KINDS:
            self._kind_box.addItem(label, key)
        self._kind_box.setToolTip("What this lab record is")
        self._kind_box.activated.connect(
            lambda i: self.set_kind(self._kind_box.itemData(i), ask=True))
        head.addWidget(self._kind_box)
        head.addStretch(1)
        copy_md = QPushButton("Copy as Markdown")
        copy_md.setIcon(icon("mdi.language-markdown-outline"))
        copy_md.clicked.connect(
            lambda: QApplication.clipboard().setText(self.to_markdown()))
        head.addWidget(copy_md)
        self._card.addLayout(head)
        self.column.addWidget(card)
        self._last = ""
        self.set_source(source or starter("measurements"))

    # -- kind -------------------------------------------------------------
    def _install(self, kind, data):
        if self._ed is not None:
            self._ed.setParent(None)
            self._ed.deleteLater()
        self.kind = kind
        self._ed = _EDITORS[kind]()
        self._ed.set_data(lm.normalise(kind, data))
        self._ed.changed.connect(self._on_changed)
        self._card.addWidget(self._ed)
        self._kind_box.setCurrentIndex(self._kind_box.findData(kind))
        self._mark.setPixmap(icon(_KIND_ICONS[kind], "#33506b").pixmap(22, 22))

    def set_kind(self, kind, ask=False):
        if kind == self.kind or kind not in _EDITORS:
            return
        empty = self._ed.data() == lm.normalise(self.kind,
                                                lm.default_data(self.kind))
        if ask and not empty and QMessageBox.question(
                self, "Change lab record",
                f"Turn this {lm.KIND_LABELS[self.kind]} record into "
                f"{lm.KIND_LABELS[kind]}? Its contents are replaced "
                "(Ctrl+Z brings them back).") != QMessageBox.Yes:
            self._kind_box.setCurrentIndex(self._kind_box.findData(self.kind))
            return
        self._install(kind, lm.default_data(kind))
        self._on_changed()

    def add_row(self):
        self._ed.add_row()

    def add_column(self):
        if isinstance(self._ed, _Measurements):
            self._ed.add_column()

    # -- data ---------------------------------------------------------------
    def data(self) -> dict:
        return lm.normalise(self.kind, self._ed.data())

    def _on_changed(self):
        if self._loading:
            return
        new = self.source()
        if new != self._last:
            old, self._last = self._last, new
            self.source_edited.emit(self, old, new)
            self.content_changed.emit()

    def to_markdown(self) -> str:
        return lm.to_markdown(self.kind, self.data(), self.title)

    def as_python(self):
        """What klab() returns: a DataFrame for the tables, else a dict."""
        d = self.data()
        try:
            import pandas as pd
        except Exception:
            pd = None
        if self.kind == "measurements":
            labels = [lm.column_label(c) for c in d["columns"]]
            rows = [r for r in d["rows"] if any(v.strip() for v in r)]
            if pd is None:
                return [dict(zip(labels, r)) for r in rows]
            df = pd.DataFrame(rows, columns=labels)
            for col in labels:
                filled = [v for v in df[col] if v.strip()]
                if filled and all(lm.number(v) is not None for v in filled):
                    df[col] = [lm.number(v) for v in df[col]]
            return df
        if self.kind == "steps":
            return pd.DataFrame(d["steps"]) if pd is not None else d["steps"]
        if self.kind == "reaction":
            calc = lm.reaction_compute(d)
            rows = []
            for row, c in zip(d["rows"], calc["rows"]):
                rows.append({"name": row["name"], "role": row["role"],
                             "formula": row["formula"], "mw": c["mw"],
                             "mass_mg": lm.number(row["mass"]),
                             "volume_ml": lm.number(row["volume"]),
                             "mmol": c["mmol"], "equiv": c["equiv"]})
            return pd.DataFrame(rows) if pd is not None else rows
        return dict(d)

    # -- CellWidget API -------------------------------------------------------
    def source(self) -> str:
        if self._ed is None:
            return ""
        return json.dumps({"kbook_lab": 1, "kind": self.kind,
                           "data": self.data()})

    def set_source(self, text: str):
        try:
            doc = json.loads(text) if (text or "").strip() else {}
        except (ValueError, TypeError):
            doc = {}
        if not isinstance(doc, dict):
            doc = {}
        kind = doc.get("kind") if doc.get("kind") in _EDITORS \
            else "measurements"
        self._loading = True
        try:
            self._install(kind, doc.get("data"))
        finally:
            self._loading = False
        self._last = self.source()

    def set_collapsed(self, on: bool):
        super().set_collapsed(on)
        if self.summary.isVisible():
            self.summary.setText(lm.KIND_LABELS[self.kind])

    def execute(self, kernel):
        """Nothing to run; the sums are live. Run just moves on."""

    def ai_summary(self) -> str:
        return ("(a Lab cell — edit it in the notebook, not here)\n"
                + self.to_markdown())

    def focus_editor(self):
        self._ed.setFocus()


CELL_CLASSES["lab"] = LabCell
