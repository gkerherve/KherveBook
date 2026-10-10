"""Samples panel — the notebook's sample register as a dockable side panel.

A lineage tree of the samples (children under the sample they were made
from), a form for the selected one, and the cells that use it. Every
edit goes through `NotebookWidget.edit_samples`, so it is one Ctrl+Z on
the notebook's undo stack and marks the document modified.

Copyright (C) 2026 Gwilherm Kerherve

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.
"""

import datetime

from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QColor, QFont
from PyQt5.QtWidgets import (QComboBox, QDockWidget, QFormLayout,
                             QHBoxLayout, QLabel, QLineEdit, QListWidget,
                             QListWidgetItem, QMessageBox, QPlainTextEdit,
                             QSplitter, QToolButton, QTreeWidget,
                             QTreeWidgetItem, QVBoxLayout, QWidget)

from .icons import icon
from .samples import STATUSES

#: form fields edited through a QLineEdit: (attribute, label, placeholder)
_LINE_FIELDS = (
    ("name", "Name", "e.g. TiO₂ film, anneal 500 °C"),
    ("composition", "Composition", "formula or description"),
    ("batch", "Batch", "batch / lot"),
    ("location", "Location", "fridge B, shelf 2…"),
    ("made", "Made", "YYYY-MM-DD"),
)


class _NotesEdit(QPlainTextEdit):
    """Notes commit when focus leaves, like the line fields' editingFinished."""

    def __init__(self, on_commit):
        super().__init__()
        self._on_commit = on_commit

    def focusOutEvent(self, event):
        super().focusOutEvent(event)
        self._on_commit()


class SamplesDock(QDockWidget):
    """Side panel listing and editing ``notebook.samples``."""

    def __init__(self, notebook, parent=None):
        super().__init__("Samples", parent)
        self.setObjectName("samples_dock")
        self.nb = notebook
        self._current = None            # id of the sample in the form
        self._filling = False

        body = QWidget()
        root = QVBoxLayout(body)
        root.setContentsMargins(6, 6, 6, 6)
        root.setSpacing(6)

        bar = QHBoxLayout()
        bar.setSpacing(2)
        self.search = QLineEdit()
        self.search.setPlaceholderText("Filter samples…")
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self.refresh)
        bar.addWidget(self.search, 1)
        for tip, ic, slot in (
                ("New sample", "mdi.plus", self.new_sample),
                ("New sample made from the selected one",
                 "mdi.source-branch-plus", self.new_child),
                ("Mention the selected sample in the current cell",
                 "mdi.at", self.mention_in_cell),
                ("Delete the selected sample", "mdi.delete-outline",
                 self.delete_sample)):
            b = QToolButton()
            b.setIcon(icon(ic))
            b.setToolTip(tip)
            b.setAutoRaise(True)
            b.clicked.connect(slot)
            bar.addWidget(b)
        root.addLayout(bar)

        split = QSplitter(Qt.Vertical)
        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["ID", "Name", "Status"])
        self.tree.setRootIsDecorated(True)
        self.tree.setUniformRowHeights(True)
        self.tree.currentItemChanged.connect(self._on_pick)
        split.addWidget(self.tree)

        form_host = QWidget()
        lay = QVBoxLayout(form_host)
        lay.setContentsMargins(0, 0, 0, 0)
        self.heading = QLabel("")
        self.heading.setStyleSheet("font-weight: 600; font-size: 13px;")
        lay.addWidget(self.heading)
        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignRight)
        self.fields = {}
        for key, label, hint in _LINE_FIELDS:
            edit = QLineEdit()
            edit.setPlaceholderText(hint)
            edit.editingFinished.connect(
                lambda k=key: self._commit(k, self.fields[k].text()))
            self.fields[key] = edit
            form.addRow(label, edit)
        self.status = QComboBox()
        self.status.addItems(STATUSES)
        self.status.activated.connect(
            lambda _i: self._commit("status", self.status.currentText()))
        form.addRow("Status", self.status)
        self.parents = QLineEdit()
        self.parents.setPlaceholderText("IDs it was made from, e.g. S-0001")
        self.parents.editingFinished.connect(self._commit_parents)
        form.addRow("Made from", self.parents)
        self.notes = _NotesEdit(
            lambda: self._commit("notes", self.notes.toPlainText()))
        self.notes.setPlaceholderText("Notes")
        self.notes.setFixedHeight(70)
        form.addRow("Notes", self.notes)
        lay.addLayout(form)
        self.lineage = QLabel("")
        self.lineage.setWordWrap(True)
        self.lineage.setStyleSheet("color: #5b6670;")
        lay.addWidget(self.lineage)
        lay.addWidget(QLabel("Used in"))
        self.used = QListWidget()
        self.used.itemActivated.connect(self._go_to_cell)
        self.used.itemClicked.connect(self._go_to_cell)
        lay.addWidget(self.used, 1)
        split.addWidget(form_host)
        split.setSizes([220, 380])
        root.addWidget(split, 1)
        self.setWidget(body)

        # Usage follows the text of the cells, so it refreshes (debounced)
        # whenever the notebook changes — not on every keystroke.
        self._usage_timer = QTimer(self)
        self._usage_timer.setSingleShot(True)
        self._usage_timer.setInterval(400)
        self._usage_timer.timeout.connect(self._refresh_usage)
        notebook.modified.connect(self._usage_timer.start)
        notebook.samples_changed.connect(self._on_register_changed)
        notebook.sample_requested.connect(self.reveal)
        self.refresh()

    # -- listing ------------------------------------------------------------
    def _registry(self):
        return self.nb.samples

    def refresh(self):
        """Rebuild the tree: lineage when unfiltered, a flat match list
        while the filter has text."""
        reg = self._registry()
        query = self.search.text().strip().lower()
        self.tree.blockSignals(True)
        self.tree.clear()
        items = {}

        def make(sample, parent_item):
            it = QTreeWidgetItem([sample.id, sample.name, sample.status])
            it.setData(0, Qt.UserRole, sample.id)
            if sample.status != STATUSES[0]:
                for col in range(3):
                    it.setForeground(col, QColor("#8a939c"))
                if sample.status == "discarded":
                    f = QFont()
                    f.setStrikeOut(True)
                    it.setFont(1, f)
            (parent_item.addChild(it) if parent_item is not None
             else self.tree.addTopLevelItem(it))
            items[sample.id] = it
            return it

        if query:
            for s in reg:
                hay = " ".join(str(v) for v in s.to_dict().values()).lower()
                if query in hay:
                    make(s, None)
        else:
            def grow(sid, parent_item, path):
                s = reg.get(sid)
                it = make(s, parent_item)
                for child in reg.children(sid):
                    # A sample with two parents sits under the first one
                    # listed; path guards a hand-made cycle in the file.
                    first = next((p for p in reg.get(child).parents
                                  if reg.get(p) is not None), None)
                    if first == sid and child not in path:
                        grow(child, it, path | {child})
            for sid in reg.roots():
                grow(sid, None, {sid})
            self.tree.expandAll()
        for col in range(3):
            self.tree.resizeColumnToContents(col)
        self.tree.blockSignals(False)
        if self._current in items:
            self.tree.setCurrentItem(items[self._current])
        elif self.tree.topLevelItemCount():
            self.tree.setCurrentItem(self.tree.topLevelItem(0))
        else:
            self._show(None)
        if self._current in items:
            self._show(self._current)

    def _on_register_changed(self, select):
        if select is not None:
            self._current = select
        elif self._current not in self._registry().ids():
            self._current = None
        self.refresh()

    def _on_pick(self, item, _prev=None):
        sid = item.data(0, Qt.UserRole) if item is not None else None
        self._show(sid)

    def reveal(self, sample_id):
        """Show the panel on *sample_id* (an @mention was clicked)."""
        self.show()
        self.raise_()
        if self._registry().get(sample_id) is None:
            return
        self.search.clear()
        self._current = sample_id
        self.refresh()

    # -- form -----------------------------------------------------------------
    def _show(self, sample_id):
        self._current = sample_id
        sample = self._registry().get(sample_id) if sample_id else None
        self._filling = True
        enabled = sample is not None
        for w in (*self.fields.values(), self.status, self.parents,
                  self.notes):
            w.setEnabled(enabled)
        self.heading.setText(sample.id if enabled else
                             "No sample selected — press + to add one")
        for key, edit in self.fields.items():
            edit.setText(getattr(sample, key) if enabled else "")
        self.status.setCurrentText(sample.status if enabled else STATUSES[0])
        self.parents.setText(", ".join(sample.parents) if enabled else "")
        self.notes.setPlainText(sample.notes if enabled else "")
        self._filling = False
        self._show_lineage(sample)
        self._refresh_usage()

    def _show_lineage(self, sample):
        if sample is None:
            self.lineage.setText("")
            return
        reg = self._registry()
        bits = []
        anc = reg.ancestors(sample.id)
        if anc:
            bits.append("From: " + " ← ".join(anc))
        desc = reg.descendants(sample.id)
        if desc:
            bits.append("Led to: " + ", ".join(desc))
        self.lineage.setText("\n".join(bits))

    def _refresh_usage(self):
        self.used.clear()
        if not self._current:
            return
        for cell in self.nb.sample_usage(self._current):
            idx = self.nb.cells.index(cell) + 1
            lines = cell.source().strip().splitlines()
            what = cell.title or (lines[0][:60] if lines else "")
            item = QListWidgetItem(f"Cell {idx} · {cell.CELL_TYPE}"
                                   + (f" — {what}" if what else ""))
            item.setData(Qt.UserRole, cell)
            self.used.addItem(item)
        if not self.used.count():
            hint = QListWidgetItem(f"Not mentioned yet — type @{self._current}"
                                   " in a cell")
            hint.setFlags(Qt.NoItemFlags)
            self.used.addItem(hint)

    def _go_to_cell(self, item):
        cell = item.data(Qt.UserRole)
        if cell is not None:
            self.nb.show_cell(cell)

    # -- edits ----------------------------------------------------------------
    def _commit(self, key, value):
        if self._filling or not self._current:
            return
        sid = self._current
        sample = self._registry().get(sid)
        if sample is None or getattr(sample, key) == value:
            return
        self.nb.edit_samples(lambda r: r.update(sid, **{key: value}),
                             f"Edit sample {sid}", select=sid)

    def _commit_parents(self):
        if self._filling or not self._current:
            return
        reg = self._registry()
        wanted = [p.strip() for p in self.parents.text().replace(";", ",")
                  .split(",") if p.strip()]
        unknown = [p for p in wanted if reg.get(p) is None]
        if unknown:
            self.parents.setToolTip("Not in the register: "
                                    + ", ".join(unknown))
        else:
            self.parents.setToolTip("")
        self._commit("parents", [p for p in wanted if p not in unknown])
        self._show(self._current)        # show the cleaned list

    def new_sample(self, parent_id=None):
        today = datetime.date.today().isoformat()

        def add(reg):
            parents = [parent_id] if parent_id else []
            base = reg.get(parent_id) if parent_id else None
            return reg.add(made=today, parents=parents,
                           composition=base.composition if base else "").id
        sid = self.nb.edit_samples(add, "New sample")
        if sid:
            self.fields["name"].setFocus()
        return sid

    def new_child(self):
        if self._current:
            return self.new_sample(self._current)
        return self.new_sample()

    def delete_sample(self):
        sid = self._current
        if not sid:
            return
        users = self.nb.sample_usage(sid)
        if users and QMessageBox.question(
                self, "Delete sample",
                f"{sid} is mentioned in {len(users)} cell(s). Delete it "
                "from the register anyway? (The cell text is kept.)"
        ) != QMessageBox.Yes:
            return

        def drop(reg):
            for child in reg.children(sid):
                reg.update(child, parents=[p for p in reg.get(child).parents
                                           if p != sid])
            reg.remove(sid)
        self.nb.edit_samples(drop, f"Delete sample {sid}")

    def mention_in_cell(self):
        """Insert the selected sample into the current cell: ``@S-0001``
        in prose, ``ksample("S-0001")`` in code."""
        cell, sid = self.nb.current, self._current
        if cell is None or not sid:
            return
        if cell.CELL_TYPE == "code":
            text, editor = f'ksample("{sid}")', cell.editor
        elif cell.CELL_TYPE == "note":
            text, editor = f"@{sid}", cell.rich
        elif cell.CELL_TYPE in ("markdown", "latex"):
            text, editor = f"@{sid}", cell.editor
        else:
            return
        cell.focus_editor()
        editor.insertPlainText(text)
