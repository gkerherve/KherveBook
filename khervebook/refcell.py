"""References cell — a notebook's bibliography, linked to KherveRef.

The cell holds its own copies of the entries (KherveRef's reference
shape, see `refs`), so a notebook is complete on any machine. Entries
come from a DOI (looked up on doi.org / Crossref in the background), a
KherveRef library on this computer, or a dropped ``.bib``. Markdown
cells cite them as ``[@key]`` or ``[@a; @b]``, rendered as numbered (or
author–year) links that jump here; code reads them with ``kref()``.

``source`` is JSON ``{"kbook_refs": 1, "style", "library", "entries"}``;
``library`` is the linked KherveRef library folder ("" when none).

Copyright (C) 2026 Gwilherm Kerherve

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.
"""

import json
from pathlib import Path

from PyQt5.QtCore import QSettings, QSize, Qt, QThread, QUrl, pyqtSignal
from PyQt5.QtGui import (QAbstractTextDocumentLayout, QDesktopServices,
                         QPalette, QTextDocument)
from PyQt5.QtWidgets import (QApplication, QComboBox, QDialog,
                             QDialogButtonBox, QFrame, QHBoxLayout, QLabel,
                             QLineEdit, QListWidget, QListWidgetItem,
                             QPushButton, QStyle, QStyledItemDelegate,
                             QStyleOptionViewItem, QToolButton, QVBoxLayout)

from . import filedialog, refs, siblings
from .cells import CELL_CLASSES, CellWidget
from .icons import icon

LOCATE_KEY = "apps/kherveref"
#: running DOI lookups, held off the cell so deleting the cell mid-lookup
#: never destroys a live QThread
_WORKERS = set()


def _settings():
    return QSettings("Kherve", "KherveBook")


class _DoiWorker(QThread):
    found = pyqtSignal(dict)
    failed = pyqtSignal(str)

    def __init__(self, doi):
        super().__init__()
        self.doi = doi

    def run(self):
        try:
            self.found.emit(refs.lookup_doi(self.doi))
        except Exception as exc:
            self.failed.emit(str(exc) or type(exc).__name__)


class _HtmlDelegate(QStyledItemDelegate):
    """Draws an item's text as HTML (italic journals, bold years)."""

    def _doc(self, option, index):
        doc = QTextDocument()
        doc.setDefaultFont(option.font)
        doc.setHtml(index.data(Qt.DisplayRole) or "")
        doc.setTextWidth(max(100, option.rect.width() - 8))
        return doc

    def paint(self, painter, option, index):
        opt = QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)
        doc = self._doc(opt, index)
        opt.text = ""
        style = opt.widget.style() if opt.widget else QApplication.style()
        style.drawControl(QStyle.CE_ItemViewItem, opt, painter, opt.widget)
        ctx = QAbstractTextDocumentLayout.PaintContext()
        if opt.state & QStyle.State_Selected:
            ctx.palette.setColor(QPalette.Text, opt.palette.color(
                QPalette.Active, QPalette.HighlightedText))
        painter.save()
        painter.translate(opt.rect.left() + 4, opt.rect.top() + 2)
        doc.documentLayout().draw(painter, ctx)
        painter.restore()

    def sizeHint(self, option, index):
        opt = QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)
        if opt.rect.width() <= 0 and opt.widget is not None:
            opt.rect.setWidth(opt.widget.viewport().width())
        doc = self._doc(opt, index)
        return QSize(int(doc.idealWidth()), int(doc.size().height()) + 4)


class LibraryPicker(QDialog):
    """Choose references from a KherveRef library on this computer."""

    def __init__(self, parent=None, current="", taken=()):
        super().__init__(parent)
        self.setWindowTitle("Add from KherveRef")
        self.resize(720, 520)
        self._taken = set(taken)
        self._entries = []
        lay = QVBoxLayout(self)
        row = QHBoxLayout()
        row.addWidget(QLabel("Library"))
        self.library = QComboBox()
        extra = [current] if current else []
        last = QSettings("kherve", "KherveRef").value("last_library", "",
                                                      type=str)
        if last:
            extra.append(last)
        for root in refs.known_libraries(extra):
            self.library.addItem(f"{refs.library_name(root)} — {root}",
                                 str(root))
        self.library.currentIndexChanged.connect(self._load)
        row.addWidget(self.library, 1)
        browse = QPushButton("Browse…")
        browse.clicked.connect(self._browse)
        row.addWidget(browse)
        lay.addLayout(row)
        self.search = QLineEdit()
        self.search.setPlaceholderText("Search author, title, year, key…")
        self.search.textChanged.connect(self._filter)
        lay.addWidget(self.search)
        self.list = QListWidget()
        self.list.setWordWrap(True)
        lay.addWidget(self.list, 1)
        self.hint = QLabel("")
        self.hint.setStyleSheet("color: #8a939c;")
        lay.addWidget(self.hint)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok
                                   | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Ok).setText("Add Ticked")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        lay.addWidget(buttons)
        self._load()

    def root(self):
        return self.library.currentData() or ""

    def _browse(self):
        folder = filedialog.existing_directory(self, "KherveRef library")
        if not folder:
            return
        root = refs.library_root(folder)
        if root is None:
            self.hint.setText("That folder is not a KherveRef library.")
            return
        self.library.insertItem(0, f"{refs.library_name(root)} — {root}",
                                str(root))
        self.library.setCurrentIndex(0)

    def _load(self, *_):
        self._entries = refs.load_library(self.root()) if self.root() else []
        self._filter()
        if not self.library.count():
            self.hint.setText("No KherveRef library found on this computer "
                              "— Browse… to one, or add by DOI instead.")

    def _filter(self, *_):
        words = self.search.text().lower().split()
        self.list.clear()
        for e in self._entries:
            hay = " ".join([e["key"], refs.authors_text(e), e.get("title", ""),
                            refs.year(e), e.get("journal", "")]).lower()
            if not all(w in hay for w in words):
                continue
            item = QListWidgetItem(f"{refs.short_cite(e)} — "
                                   f"{e.get('title', '')}  [{e['key']}]")
            item.setData(Qt.UserRole, e)
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(Qt.Unchecked)
            if e["key"] in self._taken:
                item.setFlags(Qt.NoItemFlags)
                item.setToolTip("Already in this cell")
            self.list.addItem(item)
        self.hint.setText(f"{self.list.count()} of {len(self._entries)} "
                          "references")

    def chosen(self):
        return [self.list.item(i).data(Qt.UserRole)
                for i in range(self.list.count())
                if self.list.item(i).checkState() == Qt.Checked]


class RefCell(CellWidget):
    """The notebook's references."""

    CELL_TYPE = "ref"
    source_edited = pyqtSignal(object, str, str)

    def __init__(self, source=""):
        super().__init__(source)
        self.gutter.setText("ref")
        self.editor.hide()
        self.entries = []
        self.cite_style = "numbered"
        self.library = ""
        self._loading = False
        self._last = ""
        self._build()
        self.set_source(source)

    # -- UI ---------------------------------------------------------------
    def _build(self):
        card = QFrame()
        card.setObjectName("ref_card")
        card.setStyleSheet("#ref_card { border: 1px solid #dde3ea; "
                           "border-radius: 6px; background: #fbfcfe; }")
        lay = QVBoxLayout(card)
        lay.setContentsMargins(8, 6, 8, 8)
        head = QHBoxLayout()
        mark = QLabel()
        mark.setPixmap(icon("mdi.bookshelf", "#33506b").pixmap(22, 22))
        head.addWidget(mark)
        self.heading = QLabel("References")
        self.heading.setStyleSheet("font-weight: 600; font-size: 14px;")
        head.addWidget(self.heading)
        head.addStretch(1)
        self.style_box = QComboBox()
        for key, label in refs.STYLES:
            self.style_box.addItem(label, key)
        self.style_box.setToolTip("How references and [@key] citations "
                                  "are shown")
        self.style_box.activated.connect(
            lambda i: self.set_style(self.style_box.itemData(i)))
        head.addWidget(self.style_box)
        self.open_btn = QPushButton("Open in KherveRef")
        self.open_btn.setIcon(icon("mdi.open-in-new"))
        self.open_btn.clicked.connect(self.open_in_kherveref)
        head.addWidget(self.open_btn)
        lay.addLayout(head)

        add = QHBoxLayout()
        self.doi = QLineEdit()
        self.doi.setPlaceholderText("Paste a DOI (10.…) and press Enter")
        self.doi.returnPressed.connect(self.add_doi)
        add.addWidget(self.doi, 1)
        for text, tip, ic, slot in (
                ("Add DOI", "Look the DOI up online and add it",
                 "mdi.plus", self.add_doi),
                ("From KherveRef…", "Pick references from a KherveRef "
                 "library", "mdi.bookshelf", self.add_from_library),
                ("Import .bib…", "Add every entry of a BibTeX file",
                 "mdi.file-import-outline", self.choose_bib)):
            b = QPushButton(text)
            b.setToolTip(tip)
            b.setIcon(icon(ic))
            b.clicked.connect(slot)
            add.addWidget(b)
        lay.addLayout(add)

        self.list = QListWidget()
        self.list.setItemDelegate(_HtmlDelegate(self.list))
        self.list.setWordWrap(True)
        self.list.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.list.setVerticalScrollMode(QListWidget.ScrollPerPixel)
        self.list.itemDoubleClicked.connect(lambda _i: self.open_selected())
        lay.addWidget(self.list)

        tools = QHBoxLayout()
        for tip, ic, slot in (
                ("Move up", "mdi.arrow-up", lambda: self.move(-1)),
                ("Move down", "mdi.arrow-down", lambda: self.move(1)),
                ("Remove the selected reference", "mdi.delete-outline",
                 self.remove_selected),
                ("Open the DOI, or the PDF in the linked library",
                 "mdi.file-document-outline", self.open_selected),
                ("Copy the selected reference's [@key] citation",
                 "mdi.at", self.copy_citation),
                ("Copy all as BibTeX", "mdi.content-copy",
                 lambda: QApplication.clipboard().setText(self.bibtex())),
                ("Export all to a .bib file", "mdi.content-save-outline",
                 self.export_bib)):
            b = QToolButton()
            b.setIcon(icon(ic))
            b.setToolTip(tip)
            b.setAutoRaise(True)
            b.clicked.connect(slot)
            tools.addWidget(b)
        tools.addStretch(1)
        self.hint = QLabel("")
        self.hint.setWordWrap(True)
        self.hint.setStyleSheet("color: #8a939c;")
        tools.addWidget(self.hint, 1)
        lay.addLayout(tools)
        self.column.addWidget(card)

    def _notebook(self):
        w = self.parentWidget()
        while w is not None and not hasattr(w, "citation_index"):
            w = w.parentWidget()
        return w

    def _refresh(self):
        """Redraw the list with notebook-wide numbers."""
        nb = self._notebook()
        index = nb.citation_index() if nb is not None else {
            e["key"]: (i + 1, e) for i, e in enumerate(self.entries)}
        cited = {}
        if nb is not None:
            for cell in nb.cells:
                if cell.CELL_TYPE == "markdown":
                    for k in refs.cited_keys(cell.source()):
                        cited[k] = cited.get(k, 0) + 1
        keep = self.list.currentRow()
        self.list.clear()
        for e in self.entries:
            n = index.get(e["key"], (0, e))[0]
            label = f"[{n}]" if self.cite_style == "numbered" else ""
            note = (f' <span style="color:#8a939c">@{e["key"]}'
                    + (f" · cited {cited[e['key']]}×" if e["key"] in cited
                       else " · not cited yet") + "</span>")
            item = QListWidgetItem(f"<b>{label}</b> "
                                   f"{refs.format_entry(e, self.cite_style)}"
                                   f"<br>{note}")
            item.setData(Qt.UserRole, e["key"])
            self.list.addItem(item)
        if 0 <= keep < self.list.count():
            self.list.setCurrentRow(keep)
        self.heading.setText(f"References ({len(self.entries)})"
                             if self.entries else "References")
        if not self.entries:
            self.hint.setText("Add a DOI, pick from KherveRef or drop a "
                              ".bib; cite in Markdown as [@key].")
        self._fit()

    def _fit(self):
        self.list.doItemsLayout()
        h = sum(self.list.sizeHintForRow(i) for i in range(self.list.count()))
        self.list.setFixedHeight(max(40, h + 6))

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._fit()

    # -- edits --------------------------------------------------------------
    def _changed(self, message=""):
        self._refresh()
        if message:
            self.hint.setText(message)
        if self._loading:
            return
        new = self.source()
        if new != self._last:
            old, self._last = self._last, new
            self.source_edited.emit(self, old, new)
            self.content_changed.emit()
        nb = self._notebook()
        if nb is not None:
            nb.rerender_markdown()

    def add_entries(self, entries):
        """Add *entries*, keeping their keys unless one is taken."""
        taken = {e["key"] for e in self.entries}
        added = []
        for e in entries:
            e = refs.normalise(e)
            if e.get("doi") and any(x.get("doi", "").lower() ==
                                    e["doi"].lower() for x in self.entries):
                continue
            if not e["key"] or e["key"] in taken:
                e["key"] = refs.make_key(e, taken)
            taken.add(e["key"])
            self.entries.append(e)
            added.append(e["key"])
        if added:
            self._changed("Added " + ", ".join(f"@{k}" for k in added))
        return added

    def add_doi(self):
        text = self.doi.text().strip()
        if not text:
            return False
        if not refs.clean_doi(text):
            self.hint.setText("That does not look like a DOI (10.xxxx/…).")
            return False
        self.hint.setText(f"Looking up {refs.clean_doi(text)}…")
        worker = _DoiWorker(text)
        _WORKERS.add(worker)
        worker.found.connect(self._on_doi)
        worker.failed.connect(
            lambda msg: self.hint.setText(f"DOI lookup failed: {msg}"))
        worker.finished.connect(lambda: _WORKERS.discard(worker))
        worker.start()
        return True

    def _on_doi(self, entry):
        if self.add_entries([entry]):
            self.doi.clear()
        else:
            self.hint.setText("That reference is already here.")

    def add_from_library(self):
        dlg = LibraryPicker(self, self.library,
                            taken=[e["key"] for e in self.entries])
        if dlg.exec_() != QDialog.Accepted:
            return
        if dlg.root():
            self.library = dlg.root()
        self.add_entries(dlg.chosen())

    def link_library(self, path) -> bool:
        root = refs.library_root(path)
        if root is None:
            return False
        self.library = str(root)
        self._changed(f"Linked to the KherveRef library "
                      f"{refs.library_name(root)}")
        self.add_from_library()
        return True

    def choose_bib(self):
        path = filedialog.open_file(self, "Import BibTeX", "",
                                    "BibTeX (*.bib);;All files (*)")
        return self.import_bib(path) if path else False

    def import_bib(self, path) -> bool:
        try:
            entries = refs.parse_bibtex(Path(path).read_text(
                encoding="utf-8", errors="replace"))
        except OSError:
            return False
        if not entries:
            self.hint.setText(f"No BibTeX entries in {Path(path).name}.")
            return False
        self.add_entries(entries)
        return True

    def _selected(self):
        row = self.list.currentRow()
        return row if 0 <= row < len(self.entries) else None

    def select_key(self, key):
        for i, e in enumerate(self.entries):
            if e["key"] == key:
                self.list.setCurrentRow(i)

    def move(self, delta):
        i = self._selected()
        if i is None or not 0 <= i + delta < len(self.entries):
            return
        self.entries.insert(i + delta, self.entries.pop(i))
        self.list.setCurrentRow(i + delta)
        self._changed()
        self.list.setCurrentRow(i + delta)

    def remove_selected(self):
        i = self._selected()
        if i is not None:
            key = self.entries.pop(i)["key"]
            self._changed(f"Removed @{key} (Ctrl+Z restores it)")

    def set_style(self, style):
        if style in dict(refs.STYLES) and style != self.cite_style:
            self.cite_style = style
            self._changed()

    def copy_citation(self):
        i = self._selected()
        if i is not None:
            QApplication.clipboard().setText(f"[@{self.entries[i]['key']}]")
            self.hint.setText("Citation copied — paste it in a Markdown cell")

    def open_selected(self):
        i = self._selected()
        if i is None:
            return False
        e = self.entries[i]
        for f in e.get("files") or []:
            p = Path(self.library) / f["path"] if self.library else None
            if p is not None and p.exists():
                return QDesktopServices.openUrl(QUrl.fromLocalFile(str(p)))
        if e.get("doi"):
            return QDesktopServices.openUrl(QUrl(f"https://doi.org/"
                                                 f"{e['doi']}"))
        if e.get("url"):
            return QDesktopServices.openUrl(QUrl(e["url"]))
        return False

    def bibtex(self) -> str:
        return refs.to_bibtex(self.entries)

    def export_bib(self):
        path = filedialog.save_file(self, "Export BibTeX", "references.bib",
                                    "BibTeX (*.bib)")
        if path:
            Path(path).write_text(self.bibtex(), encoding="utf-8")
            self.hint.setText(f"Wrote {len(self.entries)} entries to "
                              f"{Path(path).name}")

    # -- KherveRef ------------------------------------------------------------
    def kherveref_command(self):
        return siblings.find_app("KherveRef", "kherveref", "KherveRef.py",
                                 "KHERVEREF_PATH",
                                 _settings().value(LOCATE_KEY, "", type=str))

    def open_in_kherveref(self):
        cmd = self.kherveref_command()
        if cmd is None:
            path = filedialog.open_file(
                self, "Locate KherveRef", "",
                "KherveRef (KherveRef.app KherveRef.exe KherveRef.py *.app "
                "*.exe *.py);;All files (*)")
            if not path or siblings.app_command(path) is None:
                self.hint.setText("KherveRef was not found — install it "
                                  "from khervetools.com.")
                return False
            _settings().setValue(LOCATE_KEY, path)
            cmd = siblings.app_command(path)
        try:
            args = [self.library] if self.library else []
            siblings.launch_detached(cmd, *args)
        except Exception as exc:
            self.hint.setText(f"Could not start KherveRef: {exc}")
            return False
        self.hint.setText("Opened KherveRef. Use “From KherveRef…” to "
                          "bring new references in.")
        return True

    # -- CellWidget API -------------------------------------------------------
    def source(self) -> str:
        return json.dumps({"kbook_refs": 1, "style": self.cite_style,
                           "library": self.library,
                           "entries": self.entries})

    def set_source(self, text: str):
        try:
            doc = json.loads(text) if (text or "").strip() else {}
        except (ValueError, TypeError):
            doc = {}
        if not isinstance(doc, dict):
            doc = {}
        self._loading = True
        try:
            self.cite_style = doc.get("style") if doc.get("style") in \
                dict(refs.STYLES) else "numbered"
            self.style_box.setCurrentIndex(self.style_box.findData(
                self.cite_style))
            self.library = str(doc.get("library") or "")
            self.entries = []
            seen = set()
            for e in doc.get("entries") or []:
                e = refs.normalise(e)
                if e["key"] and e["key"] not in seen:
                    seen.add(e["key"])
                    self.entries.append(e)
            self._refresh()
        finally:
            self._loading = False
        self._last = self.source()
        nb = self._notebook()
        if nb is not None:
            nb.rerender_markdown()

    def execute(self, kernel):
        self._refresh()

    def set_collapsed(self, on: bool):
        super().set_collapsed(on)
        if self.summary.isVisible():
            self.summary.setText(f"References ({len(self.entries)})")

    def to_markdown(self) -> str:
        lines = ["**References**", ""]
        for i, e in enumerate(self.entries, 1):
            lead = f"{i}." if self.cite_style == "numbered" else "-"
            text = refs.plain(refs.format_entry(e, self.cite_style))
            lines.append(f"{lead} {text} `[@{e['key']}]`")
        return "\n".join(lines)

    def ai_summary(self) -> str:
        return ("(References cell — cite these in markdown as [@key]; add "
                "new ones by DOI in the cell, not by rewriting it)\n"
                + self.to_markdown())

    def focus_editor(self):
        self.doi.setFocus()


CELL_CLASSES["ref"] = RefCell
