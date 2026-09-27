"""Molecule cell — KherveMol's 3D viewer and 2D sketcher inside a notebook.

KherveMol is PyQt5 like KherveBook, so unlike KherveTeX it is embedded
for real: the cell hosts KherveMol's own ``Viewer3D`` (ball-and-stick,
orbit, build) and ``Editor2D`` (skeletal sketcher), switched by a
3D / 2D toggle, over KherveMol's shared ``model.Molecule``.

The molecule is stored **inside** the ``.kbook`` in KherveMol's own
``.kmol`` JSON (``document.mol_to_dict`` + the sketch graph), so a cell
is a complete molecule that "Open in KherveMol" can hand over as a
``.kmol`` file and read back on save.

KherveMol is found by `siblings.import_package` (``KHERVEMOL_PATH``, the
frozen bundle, or a sibling checkout). Without it the cell says so and
keeps its stored molecule untouched, so opening a notebook on a machine
without KherveMol never loses anything.

Copyright (C) 2026 Gwilherm Kerherve

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.
"""

import json
import re
from pathlib import Path

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (QButtonGroup, QFrame, QHBoxLayout, QLabel,
                             QLineEdit, QPushButton, QScrollArea,
                             QSizePolicy, QStackedWidget, QToolButton,
                             QVBoxLayout, QWidget)

from . import siblings
from .cells import CELL_CLASSES, CellWidget
from .icons import icon

_DEFAULT_HEIGHT = 440
#: Extra room while the building tools are shown, so they do not squeeze
#: the view itself.
_TOOLS_HEIGHT = 190
_FORMULA_RE = re.compile(r"^(?:[A-Z][a-z]?\d*)+$")


def load_khervemol():
    """The KherveMol modules the cell needs, as a namespace, or None."""
    pkg = siblings.import_package("khervemol", "KherveMol", "KHERVEMOL_PATH")
    if pkg is None:
        return None
    try:
        from types import SimpleNamespace
        import importlib
        mods = {name: importlib.import_module(f"khervemol.{name}")
                for name in ("document", "entries", "compounds", "rdkit_io",
                             "viewer3d", "editor2d", "model")}
        return SimpleNamespace(root=Path(pkg.__file__).resolve().parents[1],
                               **mods)
    except Exception:
        return None


def _subscript(formula: str) -> str:
    return re.sub(r"\d", lambda m: "₀₁₂₃₄₅₆₇₈₉"[int(m.group())], formula)


class MolCell(CellWidget):
    """A molecule drawn with KherveMol, kept in the notebook."""

    CELL_TYPE = "mol"

    def __init__(self, source=""):
        super().__init__(source)
        self.gutter.setText("mol")
        self.editor.hide()
        self._km = load_khervemol()
        self._raw = {}              # the stored document, kept verbatim
        self._query = ""            # last name / SMILES / formula built
        self._bridge = None
        self._loading = False
        self._card = self._build_card()
        self.column.addWidget(self._card)
        if source:
            self.set_source(source)
        self._update_header()

    # -- UI ---------------------------------------------------------------
    def _build_card(self):
        card = QWidget()
        outer = QVBoxLayout(card)
        outer.setContentsMargins(4, 4, 4, 4)
        outer.setSpacing(6)

        bar = QFrame()
        bar.setObjectName("mol_bar")
        bar.setStyleSheet("#mol_bar { background: #f2f7f6; border: 1px solid "
                          "#d5e3e0; border-radius: 6px; }"
                          "#mol_bar QToolButton { padding: 3px 7px; "
                          "border: 1px solid transparent; border-radius: 4px; }"
                          "#mol_bar QToolButton:checked { background: #d3ebe6; "
                          "border-color: #9fcfc5; color: #11594d; "
                          "font-weight: 600; }")
        rows = QVBoxLayout(bar)
        rows.setContentsMargins(10, 6, 6, 6)
        rows.setSpacing(4)
        head = QHBoxLayout()
        head.setSpacing(6)
        rows.addLayout(head)
        mark = QLabel()
        mark.setPixmap(icon("mdi.molecule", "#1f8a78").pixmap(26, 26))
        head.addWidget(mark)
        names = QVBoxLayout()
        names.setSpacing(0)
        self._name = QLabel("")
        self._name.setStyleSheet("font-size: 15px; font-weight: 600; "
                                 "color: #1f2933; border: none;")
        names.addWidget(self._name)
        self._formula = QLabel("")
        self._formula.setStyleSheet("color: #5b6670; border: none;")
        names.addWidget(self._formula)
        head.addLayout(names, 1)
        entry_row = QHBoxLayout()
        entry_row.setSpacing(6)

        self._entry = QLineEdit()
        self._entry.setPlaceholderText("Name, SMILES or formula — e.g. "
                                       "caffeine, c1ccccc1, C2H6O")
        self._entry.returnPressed.connect(self.build_from_entry)
        entry_row.addWidget(self._entry, 1)
        build = QPushButton("Build")
        build.setIcon(icon("mdi.hammer-wrench"))
        build.clicked.connect(self.build_from_entry)
        entry_row.addWidget(build)
        self._build_btn = build

        self._mode = QButtonGroup(self)
        for i, (text, tip) in enumerate((("3D", "Ball-and-stick 3D view"),
                                         ("2D", "Skeletal 2D sketch"))):
            b = QToolButton()
            b.setText(text)
            b.setToolTip(tip)
            b.setCheckable(True)
            b.setChecked(i == 0)
            b.setMinimumWidth(34)
            self._mode.addButton(b, i)
            head.addWidget(b)
        self._mode.buttonClicked[int].connect(self.show_view)
        self._tools_btn = QToolButton()
        self._tools_btn.setIcon(icon("mdi.tools"))
        self._tools_btn.setToolTip("Show the 3D building tools")
        self._tools_btn.setCheckable(True)
        self._tools_btn.toggled.connect(self._show_tools)
        head.addWidget(self._tools_btn)
        self._open_btn = QPushButton("Open in KherveMol")
        self._open_btn.setIcon(icon("mdi.open-in-new"))
        self._open_btn.setToolTip("Edit in KherveMol; saving there updates "
                                  "this cell")
        self._open_btn.clicked.connect(self.open_in_khervemol)
        head.addWidget(self._open_btn)
        rows.addLayout(entry_row)
        outer.addWidget(bar)

        self._stack = QStackedWidget()
        self._stack.setFixedHeight(_DEFAULT_HEIGHT)
        outer.addWidget(self._stack)
        self.viewer = self.sketch = None
        if self._km is not None:
            try:
                self.viewer = self._km.viewer3d.Viewer3D()
                self.sketch = self._km.editor2d.Editor2D()
            except Exception as exc:          # a broken KherveMol checkout
                self._km, self.viewer, self.sketch = None, None, None
                self._broken = str(exc)
        if self.viewer is not None:
            # The building tools are wider than a narrow cell; they scroll
            # sideways rather than pushing the whole notebook wider.
            holder = QScrollArea()
            holder.setFrameShape(QFrame.NoFrame)
            holder.setWidgetResizable(True)
            holder.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
            holder.setWidget(self.viewer)
            for w in (self.viewer.status, getattr(self.sketch, "status", None)):
                if w is not None:
                    w.setSizePolicy(QSizePolicy.Ignored,
                                    QSizePolicy.Preferred)
            self._stack.addWidget(holder)
            self._stack.addWidget(self.sketch)
            self.viewer.structure_changed.connect(self._on_edited_3d)
            self.viewer.view_changed.connect(self._on_edited)
            self.viewer.molecule_changed.connect(self._update_header)
            self.sketch.changed.connect(self._on_edited)
            self._show_tools(False)
        else:
            why = getattr(self, "_broken", "")
            missing = QLabel(
                "KherveMol is not available, so this molecule cannot be "
                "drawn here. Install KherveMol beside KherveBook (or set "
                "KHERVEMOL_PATH to its folder) and reopen the notebook — "
                "the molecule stored in this cell is kept as it is."
                + (f"\n\n{why}" if why else ""))
            missing.setWordWrap(True)
            missing.setAlignment(Qt.AlignCenter)
            missing.setStyleSheet("color: #8a5a00; background: #fff8e6; "
                                  "border: 1px dashed #e0c070; padding: 18px;")
            self._stack.addWidget(missing)
            self._stack.setFixedHeight(140)
            for w in (self._entry, self._build_btn, self._open_btn,
                      self._tools_btn, *self._mode.buttons()):
                w.setEnabled(False)

        self._hint = QLabel("")
        self._hint.setWordWrap(True)
        self._hint.setStyleSheet("color: #8a939c; font-style: italic;")
        outer.addWidget(self._hint)
        return card

    def _show_tools(self, on):
        """Viewer3D's building rows (palette, colours, crystal, animation)
        are a whole app's worth of controls; the cell shows the view and
        its orbit/zoom bar, and only reveals the rest on request."""
        if self.viewer is None:
            return
        root = self.viewer.layout()
        for i in range(root.count()):
            item = root.itemAt(i)
            if i < 3 or item.layout() is None:
                continue                  # view bar, the view, the status
            lay = item.layout()
            for j in range(lay.count()):
                w = lay.itemAt(j).widget()
                if w is not None:
                    w.setVisible(on)
        self._stack.setFixedHeight(self._view_height()
                                   + (_TOOLS_HEIGHT if on else 0))
        if on:
            # the viewer hides rows that do not apply (crystal, animation)
            self.viewer.set_molecule(self.viewer.mol)
            self._sync_after_tools()

    def _sync_after_tools(self):
        for attr in ("_sync_crystal_controls", "_sync_anim_controls",
                     "_sync_group_controls"):
            fn = getattr(self.viewer, attr, None)
            if fn is not None:
                try:
                    fn()
                except Exception:
                    pass

    def _view_height(self):
        return getattr(self, "_inner_h", None) or _DEFAULT_HEIGHT

    def show_view(self, index):
        if self.viewer is None:
            return
        index = 1 if index in (1, "2d") else 0
        self._stack.setCurrentIndex(index)
        self._mode.button(index).setChecked(True)
        self._tools_btn.setEnabled(index == 0)
        if index == 1 and self._tools_btn.isChecked():
            self._tools_btn.setChecked(False)
        self.content_changed.emit()

    def view_mode(self) -> str:
        return "2d" if self._stack.currentIndex() == 1 else "3d"

    def set_content_height(self, height):
        # The resize grip sizes the whole body; the view takes what the
        # header and hint leave, so dragging the grip grows the molecule.
        tools = _TOOLS_HEIGHT if self._tools_btn.isChecked() else 0
        chrome = self._card.sizeHint().height() - self._stack.height()
        self._inner_h = (max(200, int(height) - chrome - tools)
                         if height else None)
        if self.viewer is not None:
            self._stack.setFixedHeight(self._view_height() + tools)
        super().set_content_height(height)

    def _update_header(self):
        mol = self.viewer.mol if self.viewer is not None else None
        if mol is None:
            m = (self._raw.get("mol3d") or {})
            label = m.get("label") or m.get("name") or "Molecule"
            self._name.setText(label if self._raw else "Molecule (KherveMol)")
            self._formula.setText("")
            return
        if not mol.atoms:
            self._name.setText("Molecule (KherveMol)")
            self._formula.setText("Type a name, SMILES or formula and press "
                                  "Build — or draw in the 2D sketch")
            return
        label = mol.label if mol.label not in (None, "", "custom") \
            else (self._query or "Molecule")
        self._name.setText(str(label))
        formula = mol.formula()
        self._formula.setText(
            f"{_subscript(formula)}  ·  {len(mol.atoms)} atoms, "
            f"{len(mol.bonds)} bonds" if formula else "")

    # -- building ---------------------------------------------------------
    def build(self, text) -> bool:
        """Build a molecule from a library name, a formula or SMILES."""
        km = self._km
        text = (text or "").strip()
        if km is None or not text:
            return False
        mol, err = None, ""
        try:
            mol = km.entries.build("compound", text)
        except Exception:
            pass
        if mol is None and _FORMULA_RE.match(text) and \
                any(ch.isdigit() for ch in text):
            try:
                keys = km.compounds.by_formula(text)
            except Exception:
                keys = []
            if keys:
                mol = km.entries.build("compound", keys[0])
        if mol is None:
            try:
                mol = km.entries.build("smiles", text)
            except Exception as exc:
                err = str(exc.args[0] if getattr(exc, "args", None) else exc)
        if mol is None:
            self._hint.setText(f"Could not build “{text}”: "
                               f"{err or 'not a known name, formula or SMILES'}")
            return False
        self._query = text
        self._set_molecule(mol, sketch=None)
        self._hint.setText("Drag to orbit, wheel to zoom; drag an atom to "
                           "bend a bond. 2D shows the skeletal formula.")
        self.content_changed.emit()
        return True

    def build_from_entry(self):
        return self.build(self._entry.text())

    def build_from_sketch(self):
        """The 2D sketch -> a 3D model (needs RDKit, as in KherveMol)."""
        km = self._km
        if km is None or not self.sketch.atoms:
            return False
        if not km.rdkit_io.available():
            self._hint.setText("Building 3D from the sketch needs RDKit.")
            return False
        smiles = km.rdkit_io.smiles_from_structure(self.sketch.atoms,
                                                   self.sketch.bonds)
        return bool(smiles) and self.build(smiles)

    def _set_molecule(self, mol, sketch):
        self._loading = True
        try:
            self.viewer.set_molecule(mol)
            if sketch is None:
                sketch = self._sketch_of(mol)
            self.sketch.set_structure(*sketch)
        finally:
            self._loading = False
        if self._tools_btn.isChecked():
            self._sync_after_tools()
        else:
            self._show_tools(False)
        self._update_header()

    def _sketch_of(self, mol):
        """The 2D skeletal form of a 3D molecule — RDKit's clean depiction
        when available, else a projection with explicit H dropped (what
        KherveMol's own window does)."""
        km = self._km
        if not mol.atoms or mol.notes or len(mol.atoms) > 400:
            return [], []
        if not mol.crystal and km.rdkit_io.available():
            try:
                smiles = km.rdkit_io.smiles_from_structure(mol.atoms, mol.bonds)
                if smiles:
                    a2, b2 = km.rdkit_io.sketch_from_smiles(smiles)
                    if a2:
                        return a2, b2
            except Exception:
                pass
        keep = [i for i, a in enumerate(mol.atoms)
                if mol.crystal or a[0] != "H"]
        remap = {old: new for new, old in enumerate(keep)}
        atoms = []
        for i in keep:
            a = mol.atoms[i]
            px, py, _d = km.model._proj(a[1], a[2], a[3], mol.az, mol.el)
            atoms.append([a[0], px * 46.0, py * 46.0])
        bonds = [[remap[i], remap[j], o] for i, j, o in mol.bonds
                 if i in remap and j in remap]
        return atoms, bonds

    def _on_edited_3d(self):
        if self._loading:
            return
        self.sketch.set_structure(*self._sketch_of(self.viewer.mol))
        self._on_edited()

    def _on_edited(self):
        if self._loading:
            return
        self._update_header()
        self.content_changed.emit()

    # -- KherveMol round trip ---------------------------------------------
    def to_kmol(self) -> dict:
        """The cell as a KherveMol ``.kmol`` document."""
        if self.viewer is None:
            return dict(self._raw)
        km = self._km
        return {"format": "khervemol",
                "version": km.document.FORMAT_VERSION,
                "mol3d": km.document.mol_to_dict(self.viewer.mol),
                "sketch2d": {"atoms": [list(a) for a in self.sketch.atoms],
                             "bonds": [list(b) for b in self.sketch.bonds]}}

    def load_kmol(self, data: dict):
        self._raw = dict(data or {})
        if self.viewer is None or not data:
            self._update_header()
            return
        km = self._km
        mol = km.document.mol_from_dict(data.get("mol3d", {}))
        if mol.crystal:
            mol.rebuild()
        sk = data.get("sketch2d") or {}
        self._set_molecule(mol, (sk.get("atoms", []), sk.get("bonds", [])))

    def write_kmol(self, path):
        Path(path).write_text(json.dumps(self.to_kmol(), indent=1),
                              encoding="utf-8")

    def _reload_from_file(self, path):
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        self.load_kmol(data)
        self.content_changed.emit()

    def open_in_khervemol(self):
        if self._km is None:
            return False
        from .appbridge import AppBridge
        if self._bridge is None:
            self._bridge = AppBridge(self, "KherveMol", "khervemol", ".kmol",
                                     self._reload_from_file,
                                     repo=self._km.root)
        return self._bridge.open(self.write_kmol)

    # -- persistence -------------------------------------------------------
    def source(self) -> str:
        return json.dumps({"kbook_mol": 1, "kmol": self.to_kmol(),
                           "view": self.view_mode(), "query": self._query})

    def set_source(self, text: str):
        text = (text or "").strip()
        if not text.startswith("{"):
            return
        try:
            doc = json.loads(text)
        except (ValueError, TypeError):
            return
        if not isinstance(doc, dict):
            return
        self._query = str(doc.get("query") or "")
        self._entry.setText(self._query)
        kmol = doc.get("kmol") if "kbook_mol" in doc else doc
        self.load_kmol(kmol if isinstance(kmol, dict) else {})
        self.show_view(doc.get("view") or "3d")

    def execute(self, kernel):
        if self._entry.text().strip() and \
                self._entry.text().strip() != self._query:
            self.build_from_entry()

    def ai_summary(self) -> str:
        mol = self.viewer.mol if self.viewer is not None else None
        if mol is None or not mol.atoms:
            return "(a KherveMol molecule cell, empty)"
        return (f"(KherveMol molecule {self._name.text()!r}, formula "
                f"{mol.formula()}, {len(mol.atoms)} atoms — drawn in "
                "KherveMol, not editable from here)")

    def focus_editor(self):
        self._entry.setFocus()


CELL_CLASSES["mol"] = MolCell
