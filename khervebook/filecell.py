"""File attachment cell — hold one or more files in a notebook and use
them from code.

A File cell carries real files alongside the notebook so a code (or
JavaScript) cell can open them, and shows a preview of each: readable
files (text, CSV, images) get a snippet or thumbnail; anything else is
still kept verbatim, just not previewed. Storage is **hybrid**, per
file:

* Small files (<= ``EMBED_LIMIT``) are embedded base64 in the ``.kbook``
  itself, so the notebook stays a single portable document.
* Larger files are written to a sidecar ``<stem>_files/`` folder beside
  the ``.kbook`` (which is already the notebook's per-document Git repo,
  so attachments are versioned and pushed with it) and only a relative
  path is stored in the document.

Either way a code cell reaches a file by name through the kernel helper
``kf("data.csv")``, which returns an absolute path on disk — embedded
files are extracted to a temp file on demand — so ``open(kf("data.csv"))``
or ``pd.read_csv(kf("data.csv"))`` just works.

Copyright (C) 2026 Gwilherm Kerherve

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.
"""

import base64
import json
import shutil
import tempfile
from pathlib import Path

from PyQt5.QtCore import QSize, Qt, QUrl
from PyQt5.QtGui import QDesktopServices, QPixmap
from PyQt5.QtWidgets import (QApplication, QComboBox, QFileDialog, QFrame,
                             QHBoxLayout, QLabel, QPushButton, QSizePolicy,
                             QToolButton, QVBoxLayout, QWidget)

from .cells import CELL_CLASSES, CellWidget, MONO
from .icons import icon

#: Files up to this size are embedded in the .kbook; larger ones go to
#: the sidecar folder. 256 KiB keeps notebooks small while covering most
#: scripts, small datasets, configs and images.
EMBED_LIMIT = 256 * 1024

#: How much of a text file to show in the preview snippet.
_PREVIEW_LINES = 6
_PREVIEW_CHARS = 500

#: extension -> Material Design icon for the file chip.
_ICONS = {
    ".csv": "mdi.file-delimited-outline", ".tsv": "mdi.file-delimited-outline",
    ".xlsx": "mdi.file-excel-outline", ".xls": "mdi.file-excel-outline",
    ".json": "mdi.code-json", ".py": "mdi.language-python",
    ".js": "mdi.language-javascript", ".txt": "mdi.file-document-outline",
    ".md": "mdi.language-markdown", ".pdf": "mdi.file-pdf-box",
    ".png": "mdi.file-image-outline", ".jpg": "mdi.file-image-outline",
    ".jpeg": "mdi.file-image-outline", ".gif": "mdi.file-image-outline",
    ".bmp": "mdi.file-image-outline", ".svg": "mdi.file-image-outline",
    ".zip": "mdi.folder-zip-outline", ".h5": "mdi.database-outline",
    ".npy": "mdi.database-outline", ".dat": "mdi.file-table-outline",
}

#: sentinel: this attachment's structured preview hasn't been computed yet.
_UNSET = object()

_IMAGE_EXT = {".png", ".jpg", ".jpeg", ".gif", ".bmp"}
_TEXT_EXT = {".txt", ".csv", ".tsv", ".py", ".js", ".md", ".json", ".dat",
             ".log", ".xml", ".yaml", ".yml", ".ini", ".cfg", ".tex",
             ".html", ".css", ".c", ".cpp", ".h", ".r", ".m", ".sh"}


def _human_size(n: int) -> str:
    size = float(n)
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024 or unit == "GB":
            return f"{size:.0f} {unit}" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} GB"


class _Attachment:
    """One held file: its name/size plus either in-memory bytes or a
    relative path into the sidecar folder."""

    def __init__(self, name="", size=0, data=None, path=None):
        self.name = name
        self.size = size
        self._bytes = data                 # in-memory contents, if loaded
        self.path = path                   # relative sidecar path, if any
        self._temp = None                  # extracted temp file, if any
        self.preview = _UNSET              # cached structured preview

    # -- bytes / resolution ------------------------------------------------
    def current_bytes(self, doc_dir):
        if self._bytes is not None:
            return self._bytes
        if self.path and doc_dir is not None:
            fp = Path(doc_dir) / self.path
            if fp.exists():
                try:
                    return fp.read_bytes()
                except OSError:
                    return None
        return None

    def resolved_path(self, doc_dir):
        """Absolute path on disk (extracting an embedded file to a temp
        file if needed), or None."""
        if self.path and doc_dir is not None:
            fp = Path(doc_dir) / self.path
            if fp.exists():
                return str(fp)
        data = self.current_bytes(doc_dir)
        if data is None:
            return None
        if self._temp is None or not Path(self._temp).exists():
            tmp_dir = Path(tempfile.mkdtemp(prefix="khervebook_files_"))
            tmp = tmp_dir / self.name
            tmp.write_bytes(data)
            self._temp = str(tmp)
        return self._temp

    def drop_temp(self):
        if self._temp:
            shutil.rmtree(Path(self._temp).parent, ignore_errors=True)
            self._temp = None

    def preload_for_move(self, old_dir):
        """Pull bytes into memory before the notebook folder changes, so a
        Save As can rewrite the file into the new sidecar folder."""
        if self.path and self._bytes is None and old_dir is not None:
            old = Path(old_dir) / self.path
            if old.exists():
                try:
                    self._bytes = old.read_bytes()
                    self.path = None
                except OSError:
                    pass

    def materialize(self, doc_dir, stem):
        """Large files -> sidecar folder (path only); small stay embedded."""
        data = self.current_bytes(doc_dir)
        if data is None:
            return
        if len(data) > EMBED_LIMIT:
            files_dir = Path(doc_dir) / f"{stem}_files"
            files_dir.mkdir(parents=True, exist_ok=True)
            (files_dir / self.name).write_bytes(data)
            self.path = f"{stem}_files/{self.name}"
            self._bytes = None             # free memory; read from disk
        else:
            self.path = None
            self._bytes = data

    def to_dict(self, doc_dir):
        d = {"name": self.name, "size": self.size}
        if self.path:
            d["path"] = self.path
        else:
            data = self.current_bytes(doc_dir)
            if data is not None:
                d["embed"] = base64.b64encode(data).decode("ascii")
        return d

    @classmethod
    def from_dict(cls, d):
        item = cls(name=d.get("name", ""), size=int(d.get("size", 0)),
                   path=d.get("path"))
        if "embed" in d:
            try:
                item._bytes = base64.b64decode(d["embed"])
                item.size = item.size or len(item._bytes)
            except Exception:
                item._bytes = None
        return item


class FileCell(CellWidget):
    """A cell that holds one or more attached files, referenced from code
    by name via ``kf("name")``, each with a small preview."""

    CELL_TYPE = "file"

    def __init__(self, source=""):
        super().__init__(source)
        self.gutter.setText("file")
        self.editor.hide()                     # base plain editor unused here
        self._items = []                       # list[_Attachment]
        self._doc_dir = None                   # notebook folder
        self._stem = "notebook"
        self._card = self._build_card()
        self.column.addWidget(self._card)
        self.setAcceptDrops(True)
        if source:
            self.set_source(source)
        self._rebuild()

    # -- UI shell ----------------------------------------------------------
    def _build_card(self) -> QWidget:
        card = QWidget()
        outer = QVBoxLayout(card)
        outer.setContentsMargins(4, 4, 4, 4)
        outer.setSpacing(6)

        header = QHBoxLayout()
        header.setSpacing(8)
        self._count_lbl = QLabel("Attachments")
        self._count_lbl.setStyleSheet("font-weight: bold; font-size: 13px;")
        header.addWidget(self._count_lbl)
        header.addStretch(1)
        add = QPushButton("Add files…")
        add.setIcon(icon("mdi.paperclip"))
        add.clicked.connect(self.choose_file)
        header.addWidget(add)
        outer.addLayout(header)

        self._list = QWidget()
        self._list_layout = QVBoxLayout(self._list)
        self._list_layout.setContentsMargins(0, 0, 0, 0)
        self._list_layout.setSpacing(6)
        outer.addWidget(self._list)

        self._hint = QLabel("")
        self._hint.setStyleSheet("color: #57606a; font-style: italic;")
        self._hint.setWordWrap(True)
        self._hint.setTextInteractionFlags(Qt.TextSelectableByMouse)
        outer.addWidget(self._hint)
        return card

    def _rebuild(self):
        """Repaint the file list from self._items."""
        while self._list_layout.count():
            item = self._list_layout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()
        for att in self._items:
            self._list_layout.addWidget(self._build_row(att))
        n = len(self._items)
        self._count_lbl.setText(
            "No files attached" if n == 0
            else f"{n} attached file{'s' if n != 1 else ''}")
        if n == 0:
            self._hint.setText(
                "Drag files here, or click “Add files…”. Files travel inside "
                "the notebook and can be opened from a code cell.")
        else:
            self._hint.setText(
                'Use  kf("name")  in a code cell for a file\'s path — e.g.  '
                'pd.read_csv(kf("data.csv")).')

    def _build_row(self, att: "_Attachment") -> QWidget:
        row = QFrame()
        row.setFrameShape(QFrame.StyledPanel)
        row.setStyleSheet(
            "QFrame { border: 1px solid palette(mid); border-radius: 6px; }")
        lay = QVBoxLayout(row)
        lay.setContentsMargins(8, 6, 8, 6)
        lay.setSpacing(4)

        top = QHBoxLayout()
        top.setSpacing(8)
        ext = Path(att.name).suffix.lower()
        ic = QLabel()
        ic.setPixmap(icon(_ICONS.get(ext, "mdi.file-outline")).pixmap(28, 28))
        ic.setFixedSize(QSize(30, 30))
        ic.setStyleSheet("border: none;")
        top.addWidget(ic)
        meta = QVBoxLayout()
        meta.setSpacing(0)
        name = QLabel(att.name)
        name.setStyleSheet("border: none; font-weight: bold;")
        name.setTextInteractionFlags(Qt.TextSelectableByMouse)
        meta.addWidget(name)
        where = "in the notebook folder" if att.path else "embedded"
        sub = QLabel(f"{_human_size(att.size)}  ·  stored {where}")
        sub.setStyleSheet("border: none; color: #8a939c;")
        meta.addWidget(sub)
        top.addLayout(meta, 1)
        for tip, icon_name, slot in (
                ("Open", "mdi.open-in-new", lambda: self._open(att)),
                ("Save a copy…", "mdi.content-save-outline",
                 lambda: self._save_copy(att)),
                ("Copy kf() reference", "mdi.code-tags",
                 lambda: self._copy_ref(att)),
                ("Remove", "mdi.delete-outline", lambda: self._remove(att))):
            b = QToolButton()
            b.setIcon(icon(icon_name))
            b.setToolTip(tip)
            b.setAutoRaise(True)
            b.setStyleSheet("QToolButton { border: none; }")
            b.clicked.connect(lambda _=False, s=slot: s())
            top.addWidget(b)
        lay.addLayout(top)

        preview = self._preview_widget(att)
        if preview is not None:
            lay.addWidget(preview)
        return row

    # -- previews ----------------------------------------------------------
    def _preview_widget(self, att: "_Attachment"):
        data = att.current_bytes(self._doc_dir)
        ext = Path(att.name).suffix.lower()
        if data is None:
            return self._preview_note("(stored in the notebook folder)")
        if ext in _IMAGE_EXT:
            pix = QPixmap()
            if pix.loadFromData(data) and not pix.isNull():
                lbl = QLabel()
                lbl.setStyleSheet("border: none;")
                lbl.setPixmap(pix.scaled(
                    220, 140, Qt.KeepAspectRatio, Qt.SmoothTransformation))
                return lbl
        text = self._as_text(data, ext)
        if text is not None:
            snippet = self._snippet(text)
            return self._mono_label(snippet or "(empty file)")
        # Structured scientific formats (xlsx / ksheet / kfit): a browsable
        # preview with a selector for each sheet / core level.
        from . import filepreview
        if att.preview is _UNSET:
            att.preview = filepreview.describe(att.name, data)
        if att.preview:
            return self._structured_preview(att.preview)
        return self._preview_note("binary file — kept as-is (not previewed)")

    def _structured_preview(self, desc) -> QWidget:
        box = QWidget()
        v = QVBoxLayout(box)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(3)
        header = QLabel(desc.get("header", ""))
        header.setStyleSheet("border: none; color: #57606a;")
        v.addWidget(header)
        parts = desc.get("parts") or []
        body = self._mono_label("")
        if not parts:
            body.setText("(no readable content)")
        else:
            if len(parts) > 1:
                combo = QComboBox()
                for p in parts:
                    combo.addItem(p.get("name", "?"))
                combo.setToolTip("Choose a sheet / core level to read")
                combo.setStyleSheet(
                    "QComboBox { border: 1px solid palette(mid); "
                    "border-radius: 4px; padding: 2px 6px; }")
                combo.currentIndexChanged.connect(
                    lambda i: body.setText(parts[i].get("text", "")
                                           if 0 <= i < len(parts) else ""))
                row = QHBoxLayout()
                row.setContentsMargins(0, 0, 0, 0)
                row.addWidget(combo)
                row.addStretch(1)
                v.addLayout(row)
            body.setText(parts[0].get("text", ""))
        v.addWidget(body)
        return box

    @staticmethod
    def _snippet(text: str) -> str:
        lines = text.splitlines()[:_PREVIEW_LINES]
        snippet = "\n".join(lines)[:_PREVIEW_CHARS]
        if len(text) > len(snippet):
            snippet += "\n…"
        return snippet

    @staticmethod
    def _mono_label(text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setFont(MONO)
        lbl.setStyleSheet(
            "border: none; background: palette(base); padding: 4px;")
        lbl.setTextInteractionFlags(Qt.TextSelectableByMouse)
        lbl.setWordWrap(False)
        return lbl

    @staticmethod
    def _preview_note(text):
        lbl = QLabel(text)
        lbl.setStyleSheet("border: none; color: #8a939c; font-style: italic;")
        return lbl

    @staticmethod
    def _as_text(data: bytes, ext: str):
        """Decode *data* as text if it looks textual, else None."""
        probe = data[:4096]
        if b"\x00" in probe and ext not in _TEXT_EXT:
            return None
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError:
            if ext not in _TEXT_EXT:
                return None
            try:
                text = data.decode("latin-1")
            except Exception:
                return None
        # Mostly-printable check for extensions we don't already trust.
        if ext not in _TEXT_EXT:
            sample = text[:2000]
            printable = sum(c.isprintable() or c in "\r\n\t" for c in sample)
            if sample and printable / len(sample) < 0.85:
                return None
        return text

    # -- attaching ---------------------------------------------------------
    def choose_file(self):
        names, _ = QFileDialog.getOpenFileNames(self, "Attach files", "",
                                                "All files (*)")
        added = False
        for name in names:
            added = self.attach(name) or added
        return added

    def attach(self, path: str):
        """Read *path* into the cell (embedded until the notebook is saved,
        when large files move to the sidecar folder). Re-attaching a name
        that already exists replaces it."""
        p = Path(path)
        try:
            data = p.read_bytes()
        except OSError:
            return False
        att = _Attachment(name=p.name, size=len(data), data=data)
        self._items = [a for a in self._items if a.name != p.name]
        self._items.append(att)
        self._rebuild()
        self.content_changed.emit()
        return True

    def _remove(self, att: "_Attachment"):
        att.drop_temp()
        self._items = [a for a in self._items if a is not att]
        self._rebuild()
        self.content_changed.emit()

    # -- context (set by the notebook once its path is known) --------------
    def set_context(self, doc_dir, stem: str):
        doc_dir = Path(doc_dir) if doc_dir else None
        if doc_dir != self._doc_dir:
            for att in self._items:        # Save As: keep bytes across move
                att.preload_for_move(self._doc_dir)
        self._doc_dir = doc_dir
        self._stem = stem or "notebook"
        self._rebuild()

    def materialize(self):
        """On save: externalise each large attachment to the sidecar folder."""
        if self._doc_dir is None:
            return
        for att in self._items:
            att.materialize(self._doc_dir, self._stem)
        self._rebuild()

    # -- resolving (for the kernel's kf helper) ----------------------------
    def resolved_path(self, name: str = None):
        """Absolute path of the attachment *name* (or the first file when
        *name* is None), or None."""
        for att in self._items:
            if name is None or att.name == name:
                return att.resolved_path(self._doc_dir)
        return None

    @property
    def file_names(self):
        return [att.name for att in self._items]

    @property
    def file_name(self) -> str:            # first file, for summaries
        return self._items[0].name if self._items else ""

    # -- per-file actions --------------------------------------------------
    def _open(self, att):
        path = att.resolved_path(self._doc_dir)
        if path:
            QDesktopServices.openUrl(QUrl.fromLocalFile(path))

    def _save_copy(self, att):
        dest, _ = QFileDialog.getSaveFileName(self, "Save a copy",
                                              att.name, "All files (*)")
        if not dest:
            return
        data = att.current_bytes(self._doc_dir)
        if data is not None:
            Path(dest).write_bytes(data)

    def _copy_ref(self, att):
        QApplication.clipboard().setText(f"kf({json.dumps(att.name)})")

    # Kept for the CellToolBar buttons (act on the first / all files).
    def open_file(self):
        if self._items:
            self._open(self._items[0])

    def save_copy(self):
        if self._items:
            self._save_copy(self._items[0])

    def copy_reference(self):
        if self._items:
            self._copy_ref(self._items[0])

    # -- drops -------------------------------------------------------------
    def dropEvent(self, event):
        for url in event.mimeData().urls():
            if url.isLocalFile():
                self.attach(url.toLocalFile())
        event.acceptProposedAction()

    # -- source / persistence ---------------------------------------------
    def source(self) -> str:
        return json.dumps({"kbook_files": 1,
                           "files": [a.to_dict(self._doc_dir)
                                     for a in self._items]})

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
        for att in self._items:
            att.drop_temp()
        if "files" in doc:                     # current multi-file format
            self._items = [_Attachment.from_dict(d) for d in doc["files"]
                           if isinstance(d, dict) and d.get("name")]
        elif doc.get("name"):                  # legacy single-file format
            self._items = [_Attachment.from_dict(doc)]
        else:
            self._items = []
        self._rebuild()

    def focus_editor(self):
        self._card.setFocus()


CELL_CLASSES["file"] = FileCell
