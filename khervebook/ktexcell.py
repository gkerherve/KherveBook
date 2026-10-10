"""KherveTeX document cell — a whole KherveTeX document inside a notebook.

The cell holds one ``.ktexz`` (or a plain ``.tex``) and shows it as its
typeset pages, with a title bar and page navigation. Editing happens in
KherveTeX itself: "Edit in KherveTeX" launches it on the file and a
``QFileSystemWatcher`` on the document, its ``<stem>.tex`` and its
cached ``<stem>.pdf`` refreshes the pages whenever KherveTeX saves or
recompiles.

The document is a real file beside the notebook, stored like a File
cell's attachment (``<stem>_files/`` sidecar, relative path in the
``.kbook``), so KherveTeX edits the very file the notebook refers to and
the notebook's Git repo versions it. Until the notebook is first saved
the document lives in a private temp folder and travels base64 in the
JSON, exactly as attachments do.

KherveTeX is PySide6 and is never imported: see ``ktexdoc``.

Copyright (C) 2026 Gwilherm Kerherve

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.
"""

import json
import shutil
import tempfile
from pathlib import Path

from PyQt5.QtCore import (QFileSystemWatcher, QSettings, QThread, Qt,
                          QTimer, pyqtSignal)
from PyQt5.QtGui import QColor, QPixmap
from PyQt5.QtWidgets import (QFrame, QGraphicsDropShadowEffect, QHBoxLayout,
                             QLabel, QPushButton, QScrollArea,
                             QToolButton, QVBoxLayout, QWidget)

from . import filedialog, ktexdoc
from .cells import CELL_CLASSES, CellWidget
from .filecell import _Attachment
from .icons import icon

#: QSettings key holding the user's "Locate KherveTeX…" choice.
LOCATE_KEY = "apps/khervetex"
_DEFAULT_HEIGHT = 640
_PAGE_GAP = 14
#: Pages are rendered at this resolution and scaled down to the cell.
_DPI = 130

#: Workers outlive a deleted cell (never destroyed mid-run) — same rule as
#: the LaTeX cell's compile workers.
_WORKERS = set()


def _settings():
    return QSettings("Kherve", "KherveBook")


class _RenderWorker(QThread):
    """Run a cell's page job — compile and rasterise — off the UI thread.
    The job returns ``(kind, [png bytes] or None, log)``."""

    done = pyqtSignal(int, list, str)       # token, png pages, where from
    failed = pyqtSignal(int, str)           # token, log

    def __init__(self, token, job):
        super().__init__()
        self._token, self._job = token, job

    def run(self):
        try:
            kind, pages, log = self._job()
            if pages is None:
                self.failed.emit(self._token, log or "no pages were made")
                return
        except Exception as exc:
            self.failed.emit(self._token, str(exc))
            return
        self.done.emit(self._token, pages, kind)


class _Page(QLabel):
    """One page: scaled to the viewer's width, on a drop shadow."""

    def __init__(self, pixmap, parent=None):
        super().__init__(parent)
        self._orig = pixmap
        self.setAlignment(Qt.AlignCenter)
        self.setStyleSheet("background: white; border: 1px solid #c9ced6;")
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(14)
        shadow.setOffset(0, 2)
        shadow.setColor(QColor(0, 0, 0, 70))
        self.setGraphicsEffect(shadow)

    def fit(self, width):
        width = max(60, min(width, self._orig.width()))
        scaled = self._orig.scaledToWidth(width, Qt.SmoothTransformation)
        self.setPixmap(scaled)
        self.setFixedSize(scaled.size())


class _PageView(QScrollArea):
    """Vertical run of pages on a grey desk, like a PDF reader."""

    page_changed = pyqtSignal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.NoFrame)
        self.setObjectName("ktex_desk")
        self.setStyleSheet("#ktex_desk, #ktex_desk > QWidget > QWidget "
                           "{ background: #e6e8eb; }")
        body = QWidget()
        self._col = QVBoxLayout(body)
        self._col.setContentsMargins(18, 18, 18, 18)
        self._col.setSpacing(_PAGE_GAP)
        self._col.setAlignment(Qt.AlignHCenter | Qt.AlignTop)
        self.setWidget(body)
        self.pages = []
        self.verticalScrollBar().valueChanged.connect(self._on_scroll)

    def set_pages(self, pixmaps):
        for p in self.pages:
            p.setParent(None)
            p.deleteLater()
        self.pages = [_Page(px) for px in pixmaps]
        for p in self.pages:
            self._col.addWidget(p, 0, Qt.AlignHCenter)
        self._refit()

    def _refit(self):
        width = self.viewport().width() - 36
        for p in self.pages:
            p.fit(width)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._refit()

    def current_page(self) -> int:
        y = self.verticalScrollBar().value() + self.viewport().height() // 3
        index = 0
        for i, p in enumerate(self.pages):
            if p.y() <= y:
                index = i
        return index

    def go_to(self, index):
        if not self.pages:
            return
        index = max(0, min(index, len(self.pages) - 1))
        self.widget().adjustSize()
        self.verticalScrollBar().setValue(
            max(0, self.pages[index].y() - _PAGE_GAP))
        self.page_changed.emit(index)

    def _on_scroll(self, _value):
        self.page_changed.emit(self.current_page())


class KTexCell(CellWidget):
    """A cell showing one KherveTeX document as typeset pages.

    The class attributes and the few hook methods below are all that is
    KherveTeX-specific, so another app's paged document (KherveSlide's
    decks, `slidecell`) is a small subclass."""

    CELL_TYPE = "ktex"
    SOURCE_KEY = "kbook_ktex"
    APP = "KherveTeX"
    DOC_NOUN = "KherveTeX document"
    ICON = "mdi.file-document-outline"
    EXTS_TEXT = ".ktexz / .tex"
    FILE_FILTER = "KherveTeX documents (*.ktexz *.kdocz *.tex);;All files (*)"
    LOCATE_FILTER = ("KherveTeX (KherveTeX.app KherveTeX.exe kherveDOC.py "
                     "*.app *.exe *.py);;All files (*)")
    LOCATE_KEY = LOCATE_KEY
    CAN_CREATE = True
    PAGE_WORD = "Page"
    #: where the pages came from, for the hint under them
    HOW = {"pdf": "from KherveTeX's compiled PDF",
           "tex": "typeset from the document's .tex",
           "model": "typeset from the document"}

    # -- hooks ----------------------------------------------------------------
    def accepts(self, path) -> bool:
        return ktexdoc.is_ktexz(path) or str(path).lower().endswith(".tex")

    def doc_title(self, path) -> str:
        return ktexdoc.title_of(path)

    @staticmethod
    def pdf_source(path):
        return ktexdoc.pdf_source(path)

    @classmethod
    def pdf_for(cls, path):
        """(kind, pdf bytes or None, log) — runs on the worker thread."""
        kind, _src = cls.pdf_source(path)
        pdf, log = ktexdoc.document_pdf(path)
        return kind, pdf, log

    def pages_job(self, path):
        """Called on the UI thread; returns the callable the worker runs.
        Here: the document's PDF (cached or compiled), as PNG pages."""
        pdf_for = self.pdf_for

        def job():
            kind, pdf, log = pdf_for(path)
            if pdf is None:
                return kind, None, log or "no PDF was produced"
            return kind, ktexdoc.render_pages(pdf, _DPI), log
        return job

    def busy_text(self, path) -> str:
        kind, _src = self.pdf_source(path)
        return ("Loading pages…" if kind == "pdf" else
                "Typesetting with tectonic…  (the first run downloads "
                "LaTeX packages)")

    def app_command(self):
        return self.khervetex_command()

    @staticmethod
    def command_for(path):
        return ktexdoc.command_for(path)

    def __init__(self, source=""):
        super().__init__(source)
        self.gutter.setText(self.CELL_TYPE)
        self.editor.hide()
        self._att = None                 # the document, as an _Attachment
        self._origin = ""                # where it was inserted from
        self._doc_dir = None
        self._stem = "notebook"
        self._work = None                # temp folder while unsaved
        self._edit_path = None           # the file KherveTeX was opened on
        self._token = 0                  # newest render wins
        self._wanted_page = 0
        self._signature = None           # mtimes last rendered from
        self._pixmaps = []
        self._card = self._build_card()
        self.column.addWidget(self._card)
        self._watcher = QFileSystemWatcher(self)
        self._watcher.fileChanged.connect(self._on_disk_event)
        self._watcher.directoryChanged.connect(self._on_disk_event)
        self._debounce = QTimer(self)
        self._debounce.setSingleShot(True)
        self._debounce.setInterval(700)
        self._debounce.timeout.connect(self._on_disk_change)
        if source:
            self.set_source(source)
        self._update_header()
        self.refresh()

    # -- UI ---------------------------------------------------------------
    def _build_card(self):
        card = QWidget()
        outer = QVBoxLayout(card)
        outer.setContentsMargins(4, 4, 4, 4)
        outer.setSpacing(6)

        bar = QFrame()
        bar.setObjectName("ktex_bar")
        bar.setStyleSheet("#ktex_bar { background: #f4f6f8; border: 1px solid "
                          "#dde1e6; border-radius: 6px; }")
        head = QHBoxLayout(bar)
        head.setContentsMargins(10, 6, 6, 6)
        head.setSpacing(6)
        mark = QLabel()
        mark.setPixmap(icon(self.ICON, "#2c5d8f")
                       .pixmap(26, 26))
        head.addWidget(mark)
        names = QVBoxLayout()
        names.setSpacing(0)
        self._doc_title = QLabel("")
        self._doc_title.setStyleSheet(
            "font-size: 15px; font-weight: 600; color: #1f2933; border: none;")
        self._doc_title.setTextInteractionFlags(Qt.TextSelectableByMouse)
        names.addWidget(self._doc_title)
        self._doc_file = QLabel("")
        self._doc_file.setStyleSheet("color: #6b7580; border: none;")
        names.addWidget(self._doc_file)
        head.addLayout(names, 1)

        def tool(text, icon_name, tip, slot):
            b = QToolButton()
            b.setIcon(icon(icon_name))
            b.setToolTip(tip)
            b.setAutoRaise(True)
            if text:
                b.setText(text)
                b.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
            b.clicked.connect(slot)
            head.addWidget(b)
            return b

        self._prev_btn = tool("", "mdi.chevron-up", "Previous page",
                              lambda: self.go_to_page(self.current_page() - 1))
        self._page_label = QLabel("")
        self._page_label.setStyleSheet("color: #3d4650; border: none;")
        self._page_label.setMinimumWidth(70)
        self._page_label.setAlignment(Qt.AlignCenter)
        head.addWidget(self._page_label)
        self._next_btn = tool("", "mdi.chevron-down", "Next page",
                              lambda: self.go_to_page(self.current_page() + 1))
        sep = QFrame()
        sep.setFrameShape(QFrame.VLine)
        sep.setStyleSheet("color: #d0d5db;")
        head.addWidget(sep)
        if self.CAN_CREATE:
            tool("", "mdi.file-plus-outline", f"New {self.DOC_NOUN}",
                 self.new_document)
        tool("", "mdi.folder-open-outline",
             f"Insert an existing {self.EXTS_TEXT} file", self.choose_file)
        tool("", "mdi.refresh", "Re-read the document and its pages",
             lambda: self.refresh(force=True))
        self._edit_btn = QPushButton(f"Edit in {self.APP}")
        self._edit_btn.setIcon(icon("mdi.pencil-outline"))
        self._edit_btn.setToolTip(
            f"Open this in {self.APP} — saving there updates the cell")
        self._edit_btn.clicked.connect(self.edit_in_app)
        head.addWidget(self._edit_btn)
        outer.addWidget(bar)

        self._view = _PageView()
        self._view.setMinimumHeight(160)
        self._view.setFixedHeight(_DEFAULT_HEIGHT)
        self._view.page_changed.connect(self._show_page_number)
        outer.addWidget(self._view)

        foot = QHBoxLayout()
        self._hint = QLabel("")
        self._hint.setWordWrap(True)
        self._hint.setStyleSheet("color: #8a939c; font-style: italic;")
        foot.addWidget(self._hint, 1)
        self._locate_btn = QPushButton(f"Locate {self.APP}…")
        self._locate_btn.setIcon(icon("mdi.magnify"))
        self._locate_btn.clicked.connect(self.locate_app)
        self._locate_btn.hide()
        foot.addWidget(self._locate_btn)
        outer.addLayout(foot)
        return card

    def set_content_height(self, height):
        chrome = self._card.sizeHint().height() - self._view.height()
        self._view.setFixedHeight(max(160, int(height) - chrome)
                                  if height else _DEFAULT_HEIGHT)
        super().set_content_height(height)

    def _update_header(self):
        path = self.document_path()
        if path is None:
            self._doc_title.setText(self.DOC_NOUN)
            self._doc_file.setText(
                ("No document yet — create a new one or insert an existing "
                 if self.CAN_CREATE else "Nothing yet — insert or drop a ")
                + self.EXTS_TEXT)
        else:
            self._doc_title.setText(self.doc_title(path))
            where = (f"{self._stem}_files" if self._att and self._att.path
                     else "kept with the notebook until it is saved")
            self._doc_file.setText(f"{self._att.name}  ·  {where}")
        self._edit_btn.setEnabled(path is not None)
        self._show_page_number(self._view.current_page())

    def _show_page_number(self, index):
        n = len(self._view.pages)
        self._page_label.setText(f"{self.PAGE_WORD} {index + 1} / {n}"
                                 if n else "")
        self._prev_btn.setEnabled(n > 0 and index > 0)
        self._next_btn.setEnabled(n > 0 and index < n - 1)

    # -- pages ------------------------------------------------------------
    def current_page(self) -> int:
        return self._view.current_page()

    def page_count(self) -> int:
        return len(self._view.pages)

    def go_to_page(self, index):
        self._view.go_to(index)

    def refresh(self, force=False):
        """Render the document's pages (in the background)."""
        path = self.document_path()
        self._rewatch()
        if path is None or not path.exists():
            self._view.set_pages([])
            self._pixmaps = []
            self._signature = None
            self._hint.setText("" if path is None else
                               f"Not found: {path}")
            self._update_header()
            return
        signature = self._disk_signature()
        if not force and signature == self._signature and self._pixmaps:
            return
        self._signature = signature
        self._token += 1
        self._hint.setText(self.busy_text(path))
        try:
            job = self.pages_job(path)
        except Exception as exc:
            self._on_failed(self._token, str(exc))
            return
        worker = _RenderWorker(self._token, job)
        _WORKERS.add(worker)
        worker.done.connect(self._on_pages)
        worker.failed.connect(self._on_failed)
        worker.finished.connect(
            lambda w=worker: (_WORKERS.discard(w), w.deleteLater()))
        worker.start()
        self._update_header()

    def _on_pages(self, token, pngs, kind):
        if token != self._token:
            return
        keep = self._view.current_page() if self._pixmaps else \
            self._wanted_page
        pixmaps = []
        for png in pngs:
            px = QPixmap()
            px.loadFromData(png, "PNG")
            pixmaps.append(px)
        self._pixmaps = pixmaps
        self._view.set_pages(pixmaps)
        self._update_header()
        QTimer.singleShot(0, lambda: self._view.go_to(keep))
        n = len(pixmaps)
        how = self.HOW.get(kind, "")
        word = self.PAGE_WORD.lower() + ("s" if n != 1 else "")
        self._hint.setText(f"{n} {word} {how}.")
        self.content_changed.emit()

    def _on_failed(self, token, log):
        if token != self._token:
            return
        tail = "\n".join((log or "").strip().splitlines()[-6:])
        self._hint.setText("Could not show the pages. " + tail)

    def wait_rendered(self, timeout_ms=240000):
        """Block until the current render finishes (tests, screenshots)."""
        from PyQt5.QtCore import QCoreApplication, QElapsedTimer
        clock = QElapsedTimer()
        clock.start()
        while clock.elapsed() < timeout_ms:
            QCoreApplication.processEvents()
            busy = any(w.isRunning() for w in _WORKERS)
            if not busy and not self._debounce.isActive():
                QCoreApplication.processEvents()
                return True
            QThread.msleep(20)
        return False

    # -- the document file -------------------------------------------------
    def document_path(self):
        """The document as a file on disk (written out of memory into a
        temp folder while the notebook is unsaved), or None."""
        att = self._att
        if att is None:
            return None
        if att.path and self._doc_dir is not None:
            fp = Path(self._doc_dir) / att.path
            if fp.exists():
                return fp
        if self._work is None:
            self._work = Path(tempfile.mkdtemp(prefix="khervebook_ktex_"))
        fp = self._work / att.name
        if not fp.exists():
            data = att.current_bytes(self._doc_dir)
            if data is None:
                return None
            fp.write_bytes(data)
        return fp

    @property
    def file_name(self) -> str:
        return self._att.name if self._att else ""

    def title_text(self) -> str:
        path = self.document_path()
        return self.doc_title(path) if path else ""

    def _unique_name(self, name):
        """A name no other file in the sidecar folder already has."""
        if self._doc_dir is None:
            return name
        folder = Path(self._doc_dir) / f"{self._stem}_files"
        base, ext = Path(name).stem, "".join(Path(name).suffixes[-1:])
        candidate, n = name, 2
        while (folder / candidate).exists():
            candidate = f"{base}-{n}{ext}"
            n += 1
        return candidate

    def _set_document(self, data, name, siblings_from=None):
        old = self.document_path() if self._att else None
        self._att = _Attachment(name=self._unique_name(name), size=len(data),
                                data=data)
        if self._work is not None and old is not None:
            shutil.rmtree(self._work, ignore_errors=True)
            self._work = None
        if self._doc_dir is not None:
            # Straight into the sidecar folder: the cell refers to a real
            # file beside the notebook from the start, not only after a save.
            self._att.materialize(self._doc_dir, self._stem)
        if siblings_from is not None:
            self._carry_siblings(Path(siblings_from), self.document_path())
        self._signature = None
        self._wanted_page = 0
        self._update_header()
        self.refresh(force=True)
        self.content_changed.emit()

    @staticmethod
    def _carry_siblings(src, dst):
        """Bring the .tex / cached .pdf along when the document moves, so it
        does not need recompiling in its new home."""
        if src is None or dst is None or Path(src) == Path(dst):
            return
        src_time = ktexdoc._mtime(Path(src))
        for ext in (".tex", ".pdf"):
            a, b = ktexdoc.sibling(src, ext), ktexdoc.sibling(dst, ext)
            if not a.exists() or a.suffix == Path(src).suffix:
                continue
            # A sibling that was current for the old copy must stay current
            # for the new one, which was just written: give it a fresh
            # mtime. A stale one keeps its old time and stays stale.
            fresh = ktexdoc._mtime(a) >= src_time - ktexdoc._SLACK
            try:
                (shutil.copyfile if fresh else shutil.copy2)(a, b)
            except OSError:
                pass

    def new_document(self, title="Untitled document"):
        tmp = Path(tempfile.mkdtemp(prefix="khervebook_new_")) / "doc.ktexz"
        try:
            ktexdoc.new_ktexz(tmp, title=title)
            data = tmp.read_bytes()
        finally:
            shutil.rmtree(tmp.parent, ignore_errors=True)
        self._origin = ""
        self._set_document(data, "document.ktexz")
        return True

    def choose_file(self):
        path = filedialog.open_file(self, f"Insert a {self.DOC_NOUN}", "",
                                    self.FILE_FILTER)
        return self.attach(path) if path else False

    def attach(self, path) -> bool:
        p = Path(path)
        if not self.accepts(p):
            self._hint.setText(f"{p.name} is not a {self.DOC_NOUN} "
                               f"({self.EXTS_TEXT}).")
            return False
        try:
            data = p.read_bytes()
        except OSError:
            return False
        self._origin = str(p.resolve())
        self._set_document(data, p.name, siblings_from=p)
        return True

    # -- hand-off to the app ------------------------------------------------
    def khervetex_command(self):
        return ktexdoc.find_khervetex(str(_settings().value(
            self.LOCATE_KEY, "") or ""))

    def edit_in_app(self):
        path = self.document_path()
        if path is None:
            return False
        cmd = self.app_command()
        if cmd is None:
            self._locate_btn.show()
            self._hint.setText(
                f"{self.APP} was not found — install it, or point KherveBook "
                f"at it with “Locate {self.APP}…” (the app, its .exe, or a "
                "source checkout's launcher script).")
            return False
        try:
            ktexdoc.launch_detached(cmd, path)
        except Exception as exc:
            self._locate_btn.show()
            self._hint.setText(f"Could not start {self.APP}: {exc}")
            return False
        self._edit_path = path
        self._rewatch()
        self._hint.setText(f"Opened in {self.APP}. Save there (Ctrl+S) and "
                           "this cell updates by itself.")
        return True

    def locate_app(self):
        path = filedialog.open_file(self, f"Locate {self.APP}", "",
                                    self.LOCATE_FILTER)
        if not path:
            return False
        if self.command_for(path) is None:
            self._hint.setText(f"{Path(path).name} cannot be launched.")
            return False
        _settings().setValue(self.LOCATE_KEY, path)
        self._locate_btn.hide()
        return self.edit_in_app()

    # KherveTeX's names, kept for the cell toolbar and older callers.
    edit_in_khervetex = edit_in_app
    locate_khervetex = locate_app

    # -- watching ----------------------------------------------------------
    def _watch_targets(self):
        out = []
        for p in (self.document_path(), self._edit_path):
            if p is None:
                continue
            out += [p, ktexdoc.sibling(p, ".tex"), ktexdoc.sibling(p, ".pdf"),
                    p.parent]
        return out

    def _rewatch(self):
        """(Re)arm the watcher. Editors save by replacing the file, which
        drops it from a QFileSystemWatcher, so this runs after every event."""
        want = {str(p) for p in self._watch_targets() if p.exists()}
        have = set(self._watcher.files()) | set(self._watcher.directories())
        stale = list(have - want)
        if stale:
            self._watcher.removePaths(stale)
        new = list(want - have)
        if new:
            self._watcher.addPaths(new)

    def _disk_signature(self):
        path = self.document_path()
        if path is None:
            return None
        return tuple(ktexdoc._mtime(p) for p in (
            path, ktexdoc.sibling(path, ".tex"), ktexdoc.sibling(path, ".pdf")))

    def _on_disk_event(self, _path):
        self._debounce.start()

    def _on_disk_change(self):
        edit, doc = self._edit_path, self.document_path()
        if edit is not None and doc is not None and edit != doc \
                and edit.exists():
            # KherveTeX is still editing a copy from before the notebook
            # was saved (or moved): carry its saves over to the real file.
            if ktexdoc._mtime(edit) > ktexdoc._mtime(doc):
                try:
                    shutil.copy2(edit, doc)
                except OSError:
                    pass
                self._carry_siblings(edit, doc)
        self._sync_from_disk()
        self._rewatch()
        if self._disk_signature() != self._signature:
            self.refresh()
            self.content_changed.emit()

    def _sync_from_disk(self):
        """While the document is held in memory (unsaved notebook), the
        temp copy on disk is what KherveTeX edits: take its bytes back so
        the notebook saves the edited document, not the original."""
        att = self._att
        if att is None or att._bytes is None or self._work is None:
            return
        fp = self._work / att.name
        try:
            data = fp.read_bytes()
        except OSError:
            return
        if data != att._bytes:
            att._bytes = data
            att.size = len(data)

    # -- context / saving --------------------------------------------------
    def set_context(self, doc_dir, stem: str):
        doc_dir = Path(doc_dir) if doc_dir else None
        if doc_dir != self._doc_dir and self._att is not None:
            self._sync_from_disk()
            if self._att.path:
                # Leaving a sidecar folder (Save As): back into memory, and
                # a fresh temp copy of it rather than any older one.
                self._att.preload_for_move(self._doc_dir)
                self._work = None
        self._doc_dir = doc_dir
        self._stem = stem or "notebook"
        self._update_header()
        self._rewatch()

    def materialize(self, claimed=None):
        if self._doc_dir is None or self._att is None:
            return
        self._sync_from_disk()
        before = self.document_path()
        self._att.materialize(self._doc_dir, self._stem, claimed)
        if self._att.path:
            # The temp copy is retired (not deleted: KherveTeX may still be
            # saving to it — `_on_disk_change` carries those saves over).
            self._work = None
        after = self.document_path()
        if before is not None and after is not None and before != after:
            self._carry_siblings(before, after)
        self._update_header()
        self._rewatch()

    # -- drops -------------------------------------------------------------
    def dropEvent(self, event):
        paths = [u.toLocalFile() for u in event.mimeData().urls()
                 if u.isLocalFile()]
        for path in paths:
            if self.accepts(path):
                self.attach(path)
                event.acceptProposedAction()
                return
        if paths:
            self._hint.setText(f"This cell holds one {self.EXTS_TEXT} "
                               "file — drop other files on the notebook "
                               "background.")
        event.ignore()

    # -- persistence ---------------------------------------------------------
    def source(self) -> str:
        self._sync_from_disk()
        doc = {self.SOURCE_KEY: 1, "page": self._view.current_page()
               if self._view.pages else self._wanted_page}
        if self._att is not None:
            doc["file"] = self._att.to_dict(self._doc_dir)
        if self._origin:
            doc["origin"] = self._origin
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
        entry = doc.get("file")
        self._att = (_Attachment.from_dict(entry)
                     if isinstance(entry, dict) and entry.get("name")
                     else None)
        self._origin = str(doc.get("origin") or "")
        try:
            self._wanted_page = int(doc.get("page") or 0)
        except (TypeError, ValueError):
            self._wanted_page = 0
        self._signature = None

    def execute(self, kernel):
        self.refresh()

    def ai_summary(self) -> str:
        if self._att is None:
            return f"(an empty {self.DOC_NOUN} cell)"
        return (f"({self.DOC_NOUN} {self._att.name!r}, titled "
                f"{self.title_text()!r}, {self.page_count()} page(s) — "
                f"edited in {self.APP}, not from here)")

    def focus_editor(self):
        self._card.setFocus()


CELL_CLASSES["ktex"] = KTexCell
