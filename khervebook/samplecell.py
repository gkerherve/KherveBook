"""Samples cell — the notebook's sample register, kept in the document.

A table of samples (after kELN's register, KherveOS): an ID such as
``S-0001`` that is never reused, name, composition, batch, location,
date made, status, the samples it was made from (lineage) and notes,
plus a computed "Used in" column listing the cells that name it. The
data model is `samples.SampleRegistry`; this is its editor.

The notebook's register is every Samples cell together
(`NotebookWidget.samples`), so ``@S-0001`` in Markdown, ``ksample()`` in
code and sample IDs in Lab tables all resolve against it, and a new ID
continues from the highest one in the whole notebook.

``source`` is JSON ``{"kbook_samples": 1, "prefix", "digits", "items"}``.
Each committed edit is reported through ``source_edited`` for undo.

Copyright (C) 2026 Gwilherm Kerherve

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.
"""

import datetime
import json

from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QColor, QFont
from PyQt5.QtWidgets import (QApplication, QComboBox, QFrame, QHBoxLayout,
                             QHeaderView, QLabel, QLineEdit, QPushButton,
                             QStyledItemDelegate, QTableWidgetItem,
                             QVBoxLayout)

from .cells import CELL_CLASSES, CellWidget
from .icons import icon
from .labcell import _Grid
from .samples import STATUSES, Sample, SampleRegistry

#: (attribute, header) of the editable columns, in order
COLUMNS = (("id", "ID"), ("name", "Name"), ("composition", "Composition"),
           ("batch", "Batch"), ("location", "Location"), ("made", "Made"),
           ("status", "Status"), ("parents", "Made from"),
           ("notes", "Notes"))
USED = len(COLUMNS)             # the computed "Used in" column
_C = {key: i for i, (key, _h) in enumerate(COLUMNS)}


class _StatusDelegate(QStyledItemDelegate):
    """Status is plain text in the table, picked from a list when edited
    — no widget per row to go stale when the table is redrawn."""

    def createEditor(self, parent, _option, _index):
        box = QComboBox(parent)
        box.addItems(STATUSES)
        box.activated.connect(lambda _i: self.commitData.emit(box))
        return box

    def setEditorData(self, editor, index):
        editor.setCurrentText(index.data() or STATUSES[0])

    def setModelData(self, editor, model, index):
        model.setData(index, editor.currentText())


class SamplesCell(CellWidget):
    """A table of lab samples."""

    CELL_TYPE = "samples"
    source_edited = pyqtSignal(object, str, str)

    def __init__(self, source=""):
        super().__init__(source)
        self.gutter.setText("smp")
        self.editor.hide()
        self.reg = SampleRegistry()
        self._loading = False
        self._last = ""
        self._build()
        self.set_source(source)

    # -- UI ---------------------------------------------------------------
    def _build(self):
        card = QFrame()
        card.setObjectName("smp_card")
        card.setStyleSheet("#smp_card { border: 1px solid #dde3ea; "
                           "border-radius: 6px; background: #fbfcfe; }")
        lay = QVBoxLayout(card)
        lay.setContentsMargins(8, 6, 8, 8)
        head = QHBoxLayout()
        mark = QLabel()
        mark.setPixmap(icon("mdi.flask-outline", "#33506b").pixmap(22, 22))
        head.addWidget(mark)
        self.heading = QLabel("Samples")
        self.heading.setStyleSheet("font-weight: 600; font-size: 14px;")
        head.addWidget(self.heading)
        self.filter = QLineEdit()
        self.filter.setPlaceholderText("Filter…")
        self.filter.setClearButtonEnabled(True)
        self.filter.setMaximumWidth(220)
        self.filter.textChanged.connect(self._apply_filter)
        head.addStretch(1)
        head.addWidget(self.filter)
        for text, tip, ic, slot in (
                ("New", "Add a sample", "mdi.plus", self.new_sample),
                ("New from selected", "Add a sample made from the selected "
                 "one (annealed, cut, coated…)", "mdi.source-branch-plus",
                 self.new_child),
                ("Copy @ID", "Copy the selected sample's @mention, to paste "
                 "in a Markdown cell", "mdi.at", self.copy_mention),
                ("Delete", "Delete the selected samples", "mdi.delete-outline",
                 self.delete_selected)):
            b = QPushButton(text)
            b.setToolTip(tip)
            b.setIcon(icon(ic))
            b.clicked.connect(slot)
            head.addWidget(b)
        lay.addLayout(head)

        self.grid = _Grid(0, USED + 1)
        self.grid.setHorizontalHeaderLabels([h for _k, h in COLUMNS]
                                            + ["Used in"])
        hh = self.grid.horizontalHeader()
        hh.setSectionResizeMode(QHeaderView.ResizeToContents)
        # Every column shows its whole text; Notes takes what is left.
        hh.setSectionResizeMode(_C["notes"], QHeaderView.Stretch)
        hh.setMinimumSectionSize(60)
        self.grid.setItemDelegateForColumn(_C["status"],
                                           _StatusDelegate(self.grid))
        self.grid.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.grid.itemChanged.connect(self._item_changed)
        self.grid.pasted.connect(self._from_table)
        self.grid.cellDoubleClicked.connect(self._double_clicked)
        lay.addWidget(self.grid)
        self.hint = QLabel("")
        self.hint.setWordWrap(True)
        self.hint.setStyleSheet("color: #8a939c;")
        lay.addWidget(self.hint)
        self.column.addWidget(card)

    def _notebook(self):
        w = self.parentWidget()
        while w is not None and not hasattr(w, "sample_usage"):
            w = w.parentWidget()
        return w

    # -- table <-> register ---------------------------------------------------
    def _fill(self):
        """Draw the register into the table (signals off)."""
        g = self.grid
        g.blockSignals(True)
        # Emptying first closes any open editor with its row.
        g.setRowCount(0)
        g.setRowCount(len(self.reg))
        for r, s in enumerate(self.reg):
            for key, c in _C.items():
                value = ", ".join(s.parents) if key == "parents" \
                    else getattr(s, key)
                it = QTableWidgetItem(value)
                if key == "id":
                    it.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
                    bold = QFont()
                    bold.setBold(True)
                    it.setFont(bold)
                    it.setToolTip(self._lineage(s.id))
                if s.status != STATUSES[0]:
                    it.setForeground(QColor("#8a939c"))
                g.setItem(r, c, it)
            used = QTableWidgetItem("")
            used.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
            used.setForeground(QColor("#5b6670"))
            g.setItem(r, USED, used)
        g.blockSignals(False)
        g.fit()
        self.heading.setText(f"Samples ({len(self.reg)})" if len(self.reg)
                             else "Samples")
        self.refresh_usage()
        self._apply_filter()

    def _lineage(self, sid):
        reg = self._whole()
        bits = []
        anc = reg.ancestors(sid)
        if anc:
            bits.append("Made from: " + " ← ".join(anc))
        desc = reg.descendants(sid)
        if desc:
            bits.append("Led to: " + ", ".join(desc))
        return "\n".join(bits)

    def _whole(self):
        """The whole notebook's register (lineage can cross cells)."""
        nb = self._notebook()
        return nb.samples if nb is not None else self.reg

    def refresh_usage(self):
        """Recompute the "Used in" column from the other cells' text."""
        nb = self._notebook()
        usage = nb.sample_usage_map() if nb is not None else {}
        g = self.grid
        g.blockSignals(True)
        for r, s in enumerate(self.reg):
            cells = usage.get(s.id, [])
            text = ", ".join(f"cell {nb.cells.index(c) + 1}" for c in cells) \
                if nb is not None else ""
            it = g.item(r, USED)
            if it is not None:
                it.setText(text or "—")
                it.setToolTip("Double-click to go there" if cells else
                              f"Not mentioned yet — type @{s.id} in a cell")
        g.blockSignals(False)

    def _from_table(self, *_):
        """Read the edited table back into the register and commit."""
        if self._loading:
            return
        g = self.grid
        known = set(self._whole().ids()) | set(self.reg.ids())
        for r, s in enumerate(list(self.reg)):
            values = {}
            for key, c in _C.items():
                if key == "id":
                    continue
                if key == "parents":
                    wanted = [p.strip() for p in g.text(r, c).replace(";", ",")
                              .split(",") if p.strip()]
                    values[key] = [p for p in wanted if p in known]
                else:
                    values[key] = g.text(r, c)
            self.reg.update(s.id, **values)
        self._commit()

    def _item_changed(self, item):
        self._from_table()

    def _commit(self, message=""):
        self._fill()
        if message:
            self.hint.setText(message)
        new = self.source()
        if new != self._last:
            old, self._last = self._last, new
            self.source_edited.emit(self, old, new)
            self.content_changed.emit()
            nb = self._notebook()
            if nb is not None:
                nb.rerender_markdown()

    def _apply_filter(self, *_):
        words = self.filter.text().lower().split()
        for r, s in enumerate(self.reg):
            hay = " ".join(str(v) for v in s.to_dict().values()).lower()
            self.grid.setRowHidden(r, not all(w in hay for w in words))
        self.grid.fit()

    # -- actions --------------------------------------------------------------
    def _next_id(self):
        """One past the highest counter in the whole notebook."""
        whole = SampleRegistry(self.reg.prefix, self.reg.digits)
        whole.items = list(self._whole()) + list(self.reg)
        return whole.next_id()

    def new_sample(self, parent_id=None):
        base = self._whole().get(parent_id) if parent_id else None
        sid = self._next_id()
        self.reg.items.append(Sample.from_dict(
            {"id": sid, "made": datetime.date.today().isoformat(),
             "parents": [parent_id] if parent_id else [],
             "composition": base.composition if base else ""}))
        self._commit(f"Added {sid} — type its name in the table")
        row = len(self.reg) - 1
        self.grid.setCurrentCell(row, _C["name"])
        return sid

    def selected_ids(self):
        rows = sorted({i.row() for i in self.grid.selectedIndexes()}
                      or ({self.grid.currentRow()} - {-1}))
        return [self.reg.items[r].id for r in rows if r < len(self.reg)]

    def new_child(self):
        ids = self.selected_ids()
        return self.new_sample(ids[0] if ids else None)

    def delete_selected(self):
        ids = self.selected_ids()
        if not ids:
            return
        for sid in ids:
            for s in self.reg:
                if sid in s.parents:
                    s.parents = [p for p in s.parents if p != sid]
            self.reg.remove(sid)
        self._commit("Deleted " + ", ".join(ids) + " (Ctrl+Z restores)")

    def copy_mention(self):
        ids = self.selected_ids()
        if ids:
            QApplication.clipboard().setText(" ".join(f"@{i}" for i in ids))
            self.hint.setText("Copied — paste it in a Markdown cell")

    def select_id(self, sid):
        for r, s in enumerate(self.reg):
            if s.id == sid:
                self.filter.clear()
                self.grid.selectRow(r)
                return True
        return False

    def _double_clicked(self, row, col):
        if col != USED or row >= len(self.reg):
            return
        nb = self._notebook()
        cells = nb.sample_usage(self.reg.items[row].id) if nb else []
        if cells:
            nb.show_cell(cells[0])

    def add_row(self):
        self.new_sample()

    # -- CellWidget API -------------------------------------------------------
    def source(self) -> str:
        return json.dumps({"kbook_samples": 1, **self.reg.to_dict()})

    def set_source(self, text: str):
        try:
            doc = json.loads(text) if (text or "").strip() else {}
        except (ValueError, TypeError):
            doc = {}
        self._loading = True
        try:
            self.reg.load(doc if isinstance(doc, dict) else {})
            self._fill()
        finally:
            self._loading = False
        self._last = self.source()

    def execute(self, kernel):
        self.refresh_usage()

    def set_collapsed(self, on: bool):
        super().set_collapsed(on)
        if self.summary.isVisible():
            self.summary.setText(f"Samples ({len(self.reg)}): "
                                 + ", ".join(self.reg.ids()[:8]))

    def to_markdown(self) -> str:
        rows = ["| ID | Name | Composition | Status | Made from |",
                "|---|---|---|---|---|"]
        for s in self.reg:
            rows.append(f"| {s.id} | {s.name} | {s.composition} | {s.status}"
                        f" | {', '.join(s.parents)} |")
        return "**Samples**\n\n" + "\n".join(rows)

    def ai_summary(self) -> str:
        return ("(Samples cell — cite a sample as @ID in markdown, "
                "ksample(\"ID\") in code; ksample() is a DataFrame of all. "
                "Edit it in the notebook, not here)\n"
                + (self.reg.summary_text() or "(no samples yet)"))

    def focus_editor(self):
        self.grid.setFocus()


CELL_CLASSES["samples"] = SamplesCell
