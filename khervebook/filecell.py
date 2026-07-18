"""File attachment cell — hold a file inside a notebook and use it from code.

A File cell carries a real file alongside the notebook so a code (or
JavaScript) cell can open it. Storage is **hybrid**:

* Small files (<= ``EMBED_LIMIT``) are embedded base64 in the ``.kbook``
  itself, so the notebook stays a single portable document.
* Larger files are written to a sidecar ``<stem>_files/`` folder beside
  the ``.kbook`` (which is already the notebook's per-document Git repo,
  so attachments are versioned and pushed with it) and only a relative
  path is stored in the document.

Either way, a code cell reaches the file by name through the kernel
helper ``kf("data.csv")``, which returns an absolute path on disk —
embedded files are extracted to a temp file on demand — so
``open(kf("data.csv"))`` or ``pd.read_csv(kf("data.csv"))`` just works.

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
from PyQt5.QtGui import QDesktopServices
from PyQt5.QtWidgets import (QApplication, QFileDialog, QHBoxLayout, QLabel,
                             QPushButton, QSizePolicy, QVBoxLayout, QWidget)

from .cells import CELL_CLASSES, CellWidget
from .icons import icon

#: Files up to this size are embedded in the .kbook; larger ones go to
#: the sidecar folder. 256 KiB keeps notebooks small while covering most
#: scripts, small datasets, configs and images.
EMBED_LIMIT = 256 * 1024

#: extension -> Material Design icon for the file chip.
_ICONS = {
    ".csv": "mdi.file-delimited-outline", ".tsv": "mdi.file-delimited-outline",
    ".xlsx": "mdi.file-excel-outline", ".xls": "mdi.file-excel-outline",
    ".json": "mdi.code-json", ".py": "mdi.language-python",
    ".js": "mdi.language-javascript", ".txt": "mdi.file-document-outline",
    ".md": "mdi.language-markdown", ".pdf": "mdi.file-pdf-box",
    ".png": "mdi.file-image-outline", ".jpg": "mdi.file-image-outline",
    ".jpeg": "mdi.file-image-outline", ".gif": "mdi.file-image-outline",
    ".zip": "mdi.folder-zip-outline", ".h5": "mdi.database-outline",
    ".npy": "mdi.database-outline", ".dat": "mdi.file-table-outline",
}


def _human_size(n: int) -> str:
    size = float(n)
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024 or unit == "GB":
            return f"{size:.0f} {unit}" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} GB"


class FileCell(CellWidget):
    """A cell that holds an attached file, referenced from code by name."""

    CELL_TYPE = "file"

    def __init__(self, source=""):
        super().__init__(source)
        self.gutter.setText("file")
        self.editor.hide()                     # base plain editor unused here
        self._name = ""
        self._size = 0
        self._bytes = None                     # in-memory contents, if loaded
        self._path = None                      # relative sidecar path, if any
        self._doc_dir = None                   # notebook folder
        self._stem = "notebook"
        self._temp = None                      # extracted temp file, if any
        self._card = self._build_card()
        self.column.addWidget(self._card)
        self.setAcceptDrops(True)
        if source:
            self.set_source(source)
        self._refresh()

    # -- UI ----------------------------------------------------------------
    def _build_card(self) -> QWidget:
        card = QWidget()
        outer = QVBoxLayout(card)
        outer.setContentsMargins(4, 4, 4, 4)
        outer.setSpacing(4)

        top = QHBoxLayout()
        top.setSpacing(8)
        self._icon = QLabel()
        self._icon.setFixedSize(QSize(40, 40))
        top.addWidget(self._icon)
        meta = QVBoxLayout()
        meta.setSpacing(0)
        self._name_lbl = QLabel("No file attached")
        self._name_lbl.setStyleSheet("font-weight: bold; font-size: 13px;")
        self._name_lbl.setTextInteractionFlags(Qt.TextSelectableByMouse)
        meta.addWidget(self._name_lbl)
        self._sub_lbl = QLabel("")
        self._sub_lbl.setStyleSheet("color: #8a939c;")
        meta.addWidget(self._sub_lbl)
        top.addLayout(meta, 1)
        outer.addLayout(top)

        btns = QHBoxLayout()
        btns.setSpacing(4)
        self._attach_btn = QPushButton("Attach file…")
        self._attach_btn.setIcon(icon("mdi.paperclip"))
        self._attach_btn.clicked.connect(self.choose_file)
        btns.addWidget(self._attach_btn)
        self._open_btn = QPushButton("Open")
        self._open_btn.setIcon(icon("mdi.open-in-new"))
        self._open_btn.clicked.connect(self.open_file)
        btns.addWidget(self._open_btn)
        self._save_btn = QPushButton("Save a copy…")
        self._save_btn.setIcon(icon("mdi.content-save-outline"))
        self._save_btn.clicked.connect(self.save_copy)
        btns.addWidget(self._save_btn)
        self._copy_btn = QPushButton("Copy code reference")
        self._copy_btn.setIcon(icon("mdi.code-tags"))
        self._copy_btn.clicked.connect(self.copy_reference)
        btns.addWidget(self._copy_btn)
        btns.addStretch(1)
        outer.addLayout(btns)

        self._hint = QLabel("")
        self._hint.setStyleSheet("color: #57606a; font-style: italic;")
        self._hint.setWordWrap(True)
        self._hint.setTextInteractionFlags(Qt.TextSelectableByMouse)
        outer.addWidget(self._hint)
        return card

    def _refresh(self):
        has = bool(self._name)
        ext = Path(self._name).suffix.lower()
        self._icon.setPixmap(
            icon(_ICONS.get(ext, "mdi.file-outline")).pixmap(40, 40))
        for b in (self._open_btn, self._save_btn, self._copy_btn):
            b.setEnabled(has)
        if not has:
            self._name_lbl.setText("No file attached")
            self._sub_lbl.setText("")
            self._hint.setText("Drag a file here, or click “Attach file…”. "
                               "The file travels inside the notebook and can "
                               "be opened from a code cell.")
            self._attach_btn.setText("Attach file…")
            return
        self._attach_btn.setText("Replace…")
        self._name_lbl.setText(self._name)
        where = "in the notebook folder" if self._path else "embedded"
        self._sub_lbl.setText(f"{_human_size(self._size)}  ·  stored {where}")
        ref = json.dumps(self._name)
        self._hint.setText(
            f"Use  kf({ref})  in a code cell for its path — e.g.  "
            f"open(kf({ref}))  or  pd.read_csv(kf({ref})).")

    # -- attaching ---------------------------------------------------------
    def choose_file(self):
        name, _ = QFileDialog.getOpenFileName(self, "Attach file", "",
                                              "All files (*)")
        if name:
            self.attach(name)

    def attach(self, path: str):
        """Read *path* into the cell (embedded until the notebook is saved,
        when large files move to the sidecar folder)."""
        p = Path(path)
        try:
            data = p.read_bytes()
        except OSError:
            return False
        self._name = p.name
        self._size = len(data)
        self._bytes = data
        self._path = None
        self._drop_temp()
        self._refresh()
        self.content_changed.emit()
        return True

    # -- context (set by the notebook once its path is known) --------------
    def set_context(self, doc_dir, stem: str):
        doc_dir = Path(doc_dir) if doc_dir else None
        # Moving to a new folder (Save As): pull the bytes in so the file
        # gets rewritten into the new sidecar folder on the next save.
        if (self._path and self._bytes is None and self._doc_dir is not None
                and doc_dir != self._doc_dir):
            old = self._doc_dir / self._path
            if old.exists():
                try:
                    self._bytes = old.read_bytes()
                    self._path = None
                except OSError:
                    pass
        self._doc_dir = doc_dir
        self._stem = stem or "notebook"
        self._refresh()

    def _files_dir(self):
        if self._doc_dir is None:
            return None
        return self._doc_dir / f"{self._stem}_files"

    def materialize(self):
        """On save: write a large attachment out to the sidecar folder and
        keep only its relative path; small files stay embedded."""
        if not self._name or self._doc_dir is None:
            return
        data = self._current_bytes()
        if data is None:
            return
        if len(data) > EMBED_LIMIT:
            files_dir = self._files_dir()
            files_dir.mkdir(parents=True, exist_ok=True)
            (files_dir / self._name).write_bytes(data)
            self._path = f"{self._stem}_files/{self._name}"
            self._bytes = None                 # free memory; read from disk
        else:
            self._path = None
            self._bytes = data
        self._refresh()

    # -- resolving to a real path (for the kernel's kf helper) -------------
    def _current_bytes(self):
        if self._bytes is not None:
            return self._bytes
        if self._path and self._doc_dir is not None:
            fp = self._doc_dir / self._path
            if fp.exists():
                try:
                    return fp.read_bytes()
                except OSError:
                    return None
        return None

    def resolved_path(self):
        """Absolute path to the attached file on disk (extracting an
        embedded file to a temp location if needed), or None."""
        if not self._name:
            return None
        if self._path and self._doc_dir is not None:
            fp = self._doc_dir / self._path
            if fp.exists():
                return str(fp)
        data = self._current_bytes()
        if data is None:
            return None
        if self._temp is None or not Path(self._temp).exists():
            tmp_dir = Path(tempfile.mkdtemp(prefix="khervebook_files_"))
            tmp = tmp_dir / self._name
            tmp.write_bytes(data)
            self._temp = str(tmp)
        return self._temp

    def _drop_temp(self):
        if self._temp:
            try:
                shutil.rmtree(Path(self._temp).parent, ignore_errors=True)
            except Exception:
                pass
            self._temp = None

    @property
    def file_name(self) -> str:
        return self._name

    # -- actions -----------------------------------------------------------
    def open_file(self):
        path = self.resolved_path()
        if path:
            QDesktopServices.openUrl(QUrl.fromLocalFile(path))

    def save_copy(self):
        if not self._name:
            return
        dest, _ = QFileDialog.getSaveFileName(self, "Save a copy",
                                              self._name, "All files (*)")
        if not dest:
            return
        data = self._current_bytes()
        if data is not None:
            Path(dest).write_bytes(data)

    def copy_reference(self):
        if not self._name:
            return
        ref = json.dumps(self._name)
        QApplication.clipboard().setText(f"kf({ref})")

    # -- drops -------------------------------------------------------------
    def dropEvent(self, event):
        for url in event.mimeData().urls():
            if url.isLocalFile():
                self.attach(url.toLocalFile())
                break
        event.acceptProposedAction()

    # -- source / persistence ---------------------------------------------
    def source(self) -> str:
        doc = {"kbook_file": 1, "name": self._name, "size": self._size}
        if self._path:
            doc["path"] = self._path
        else:
            data = self._current_bytes()
            if data is not None:
                doc["embed"] = base64.b64encode(data).decode("ascii")
        return json.dumps(doc)

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
        self._name = doc.get("name", "")
        self._size = int(doc.get("size", 0))
        self._path = doc.get("path")
        self._bytes = None
        if "embed" in doc:
            try:
                self._bytes = base64.b64decode(doc["embed"])
                self._size = self._size or len(self._bytes)
            except Exception:
                self._bytes = None
        self._drop_temp()
        self._refresh()

    def focus_editor(self):
        self._card.setFocus()


CELL_CLASSES["file"] = FileCell
