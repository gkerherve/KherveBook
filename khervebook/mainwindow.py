"""MainWindow shell: menus, toolbar, file I/O for .kbook documents.

Copyright (C) 2026 Gwilherm Kerherve

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.
"""

from datetime import datetime
from pathlib import Path

from PyQt5.QtCore import QSettings, QSize, Qt, QThread, QTimer, pyqtSignal
from PyQt5.QtWidgets import (QAction, QActionGroup, QApplication, QComboBox,
                             QFileDialog, QInputDialog, QMainWindow,
                             QMessageBox, QToolBar)

from . import examples, git_backend, style, updater

from . import APP_NAME, __version__
from .celltoolbar import CellToolBar
from .explorer import FileExplorer
from .icons import app_icon, icon
from .notebook import NotebookWidget

FILE_FILTER = "KherveBook notebook (*.kbook);;All files (*)"


class _GitNetworkWorker(QThread):
    """Run pull / push on a background thread so the GUI doesn't lock
    up for the duration of a libgit2 network round-trip. Without this,
    saving or pulling against an unreachable remote freezes the window
    for 30+ seconds (Windows shows it as "Not Responding") — to the
    user that reads as a crash, even though it's just blocked I/O on
    the main thread.

    The worker emits `finished_with` carrying (operation, success,
    message). The caller decides how to surface that — status bar,
    message box, etc.
    """
    finished_with = pyqtSignal(str, bool, str)  # op, ok, msg

    def __init__(self, op, repo_dir, remote_name="origin"):
        super().__init__()
        self._op = op   # "pull" or "push"
        self._repo_dir = repo_dir
        self._remote = remote_name

    def run(self):
        try:
            if self._op == "pull":
                ok, msg = git_backend.pull(self._repo_dir, self._remote)
            elif self._op == "push":
                ok, msg = git_backend.push(self._repo_dir, self._remote)
            else:
                ok, msg = False, f"Unknown git op: {self._op!r}"
        except Exception as exc:  # pragma: no cover — defensive
            ok, msg = False, f"{self._op} crashed: {exc}"
        self.finished_with.emit(self._op, ok, msg)


class MainWindow(QMainWindow):

    def __init__(self):
        super().__init__()
        self.notebook = NotebookWidget()
        self.notebook.modified.connect(self._mark_dirty)
        self.setCentralWidget(self.notebook)
        self.path = None
        self.dirty = False
        self._git_worker = None
        self._pending_commit_msg = None
        self.setWindowIcon(app_icon())
        self.explorer = FileExplorer(self)
        self.explorer.open_requested.connect(self._open_path)
        self.addDockWidget(Qt.LeftDockWidgetArea, self.explorer)
        from .ai_chat import AIChatDock
        self.ai_chat = AIChatDock(self.notebook, self)
        self.addDockWidget(Qt.LeftDockWidgetArea, self.ai_chat)
        self.splitDockWidget(self.explorer, self.ai_chat, Qt.Vertical)
        self._build_menus()
        self._build_toolbar()
        self.notebook.current_changed.connect(self._on_current_cell)
        self.notebook.open_kbook_requested.connect(self._open_path)
        self.statusBar().showMessage(f"{APP_NAME} v{__version__}")
        self.setMinimumSize(900, 620)
        self._load_welcome()
        self._update_title()
        # Restore window size + dock layout, or open large by default.
        # geometry_v2: the old key pinned everyone to a small default;
        # a fresh key lets the bigger default take effect once.
        settings = QSettings("Kherve", "KherveBook")
        geometry = settings.value("win/geometry_v2")
        state = settings.value("win/state")
        if geometry:
            self.restoreGeometry(geometry)
        else:
            self._open_at_default_size()
        if state:
            self.restoreState(state)
        # Kept off the constructor's critical path: the check is a network
        # round-trip, and nothing about it should delay the first paint.
        self._updater = updater.Updater(self)
        if updater.startup_check_enabled():
            QTimer.singleShot(3000, lambda: self._updater.check(silent=True))

    def _check_updates(self):
        self._updater.check(silent=False)

    def _open_at_default_size(self):
        """Open at 90% of the available screen (capped), centred."""
        screen = QApplication.primaryScreen()
        if screen is None:
            self.resize(1280, 900)
            return
        area = screen.availableGeometry()
        w = min(int(area.width() * 0.9), 1600)
        h = min(int(area.height() * 0.9), 1100)
        self.resize(w, h)
        self.move(area.x() + (area.width() - w) // 2,
                  area.y() + (area.height() - h) // 2)

    def _add_svg_cell(self):
        from .svgcell import STARTER_SVG
        self.notebook.add_cell_below("svg", STARTER_SVG)

    def _add_js_cell(self):
        from .jscell import JS_STARTER
        self.notebook.add_cell_below("js", JS_STARTER)

    def _add_note_cell(self):
        from .notecell import NOTE_STARTER
        self.notebook.add_cell_below("note", NOTE_STARTER)

    def _add_file_cell(self):
        """Add a File cell and immediately prompt for a file to attach."""
        cell = self.notebook.add_cell_below("file")
        cell.choose_file()

    def _load_example(self, builder):
        if not self._confirm_discard():
            return
        examples.load_example(self.notebook, builder)
        self.path = None
        self.notebook.set_document_path(None)
        self.dirty = False
        self._update_title()

    def _load_welcome(self):
        """Open with a pre-run example so a new user sees what the
        app does instead of an empty window."""
        from .welcome import load_welcome
        try:
            load_welcome(self.notebook)
        except Exception:
            pass    # an empty notebook is a fine fallback
        self.dirty = False

    # -- UI scaffolding ---------------------------------------------------
    def _build_menus(self):
        m = self.menuBar()
        f = m.addMenu("&File")
        f.addAction(self._act("&New", "Ctrl+N", self.new_file))
        f.addAction(self._act("New &Window", "Ctrl+Shift+N", self.new_window))
        f.addAction(self._act("&Open...", "Ctrl+O", self.open_file))
        f.addAction(self._act("&Save", "Ctrl+S", self.save_file))
        f.addAction(self._act("Save &As...", "Ctrl+Shift+S", self.save_as))
        self.recent_menu = f.addMenu("Open &Recent")
        self.recent_menu.aboutToShow.connect(self._rebuild_recent_menu)
        self._rebuild_recent_menu()
        f.addSeparator()
        f.addAction(self._act("Insert &Image / PDF...", None,
                              self.insert_image_or_pdf))
        f.addAction(self._act("Import &Spreadsheet (.xlsx)...", None,
                              self.import_spreadsheet))
        f.addAction(self._act("&Import Jupyter/Colab (.ipynb)...", None,
                              self.import_ipynb))
        f.addAction(self._act("E&xport as Jupyter/Colab (.ipynb)...", None,
                              self.export_ipynb))
        f.addSeparator()
        f.addAction(self._act("E&xit", "Ctrl+Q", self.close))

        e = m.addMenu("&Edit")
        self.undo_act = self._act("&Undo", "Ctrl+Z", self._smart_undo,
                                  "mdi.undo")
        self.redo_act = self._act("&Redo", "Ctrl+Shift+Z", self._smart_redo,
                                  "mdi.redo")
        e.addAction(self.undo_act)
        e.addAction(self.redo_act)

        c = m.addMenu("&Cell")
        c.addAction(self._act("Add &Code Cell", "Ctrl+Shift+C",
                              lambda: self.notebook.add_cell_below("code")))
        c.addAction(self._act("Add &Markdown Cell", "Ctrl+Shift+M",
                              lambda: self.notebook.add_cell_below("markdown")))
        c.addAction(self._act("Add &Note Cell", "Ctrl+Shift+E",
                              self._add_note_cell))
        c.addAction(self._act("Add &LaTeX Cell", "Ctrl+Shift+L",
                              lambda: self.notebook.add_cell_below("latex")))
        c.addAction(self._act("Add &Sheet Cell", "Ctrl+Shift+T",
                              lambda: self.notebook.add_cell_below("sheet")))
        c.addAction(self._act("Add S&VG Cell", None,
                              self._add_svg_cell))
        c.addAction(self._act("Add &JavaScript Cell", None,
                              self._add_js_cell))
        c.addAction(self._act("Attach &File Cell...", None,
                              self._add_file_cell))
        c.addSeparator()
        c.addAction(self._act("&Run Cell", "Ctrl+Return",
                              self.notebook.run_current))
        c.addAction(self._act("Run &All", "Ctrl+Shift+Return",
                              self.notebook.run_all))
        c.addSeparator()
        c.addAction(self._act("Cu&t Cell", "Ctrl+Shift+X",
                              self.notebook.cut_current))
        c.addAction(self._act("C&opy Cell", "Ctrl+Shift+O",
                              self.notebook.copy_current))
        c.addAction(self._act("&Paste Cell Below", "Ctrl+Shift+V",
                              self.notebook.paste_cell))
        c.addSeparator()
        c.addAction(self._act("Move Cell &Up", "Ctrl+Shift+Up",
                              lambda: self.notebook.move_current(-1)))
        c.addAction(self._act("Move Cell &Down", "Ctrl+Shift+Down",
                              lambda: self.notebook.move_current(1)))
        c.addAction(self._act("&Delete Cell", "Ctrl+Shift+D",
                              self.notebook.remove_current))

        k = m.addMenu("&Kernel")
        k.addAction(self._act("&Restart Kernel", "Ctrl+Shift+R",
                              self.notebook.restart_kernel))

        g = m.addMenu("&Git")
        g.addAction(self._act("&Save Snapshot && Upload", None,
                              self._commit_and_maybe_push,
                              "mdi.cloud-upload-outline",
                              "Save, snapshot this version, and upload it "
                              "to the cloud (GitHub, GitLab, …)"))
        g.addAction(self._act("&Download Latest from Cloud", None,
                              self._pull_from_remote,
                              "mdi.cloud-download-outline",
                              "Download the newest version (e.g. changes a "
                              "collaborator pushed)"))
        g.addSeparator()
        g.addAction(self._act("&Connect to GitHub / GitLab...", None,
                              self._configure_remotes, "mdi.github",
                              "Link this notebook to a cloud repository"))
        g.addSeparator()
        g.addAction(self._act("View &Version History...", None,
                              self._show_history, "mdi.history",
                              "Browse every saved snapshot and what changed"))
        g.addAction(self._act("&Branches...", None, self._show_branches,
                              "mdi.source-branch",
                              "View, create, switch or delete branches"))

        v = m.addMenu("&View")
        self._explorer_toggle = self.explorer.toggleViewAction()
        self._explorer_toggle.setText("&File Explorer")
        self._explorer_toggle.setShortcut("Ctrl+B")
        v.addAction(self._explorer_toggle)
        self._ai_toggle = self.ai_chat.toggleViewAction()
        self._ai_toggle.setText("&AI Assistant")
        self._ai_toggle.setShortcut("Ctrl+Shift+A")
        v.addAction(self._ai_toggle)
        pos = v.addMenu("File Explorer &Position")
        pos.addAction(self._act("&Left", None,
                                lambda: self._dock_explorer(Qt.LeftDockWidgetArea)))
        pos.addAction(self._act("&Right", None,
                                lambda: self._dock_explorer(Qt.RightDockWidgetArea)))
        pos.addAction(self._act("&Floating", None, self._float_explorer))
        v.addSeparator()
        self.page_mode_act = QAction("&Page Mode (continuous)", self,
                                     checkable=True)
        self.page_mode_act.setShortcut("Ctrl+Shift+P")
        page_on = QSettings("Kherve", "KherveBook").value(
            "view/page_mode", False, type=bool)
        self.page_mode_act.setChecked(page_on)
        self.page_mode_act.toggled.connect(self._toggle_page_mode)
        v.addAction(self.page_mode_act)
        if page_on:
            self.notebook.set_page_mode(True)

        self.interactive_act = QAction("&Interactive Plots (zoom/pan)", self,
                                       checkable=True)
        interactive_on = QSettings("Kherve", "KherveBook").value(
            "view/interactive_plots", False, type=bool)
        self.interactive_act.setChecked(interactive_on)
        self.notebook.kernel.interactive_figures = interactive_on
        self.interactive_act.toggled.connect(self._toggle_interactive_plots)
        v.addAction(self.interactive_act)

        theme_menu = v.addMenu("&Theme")
        group = QActionGroup(self)
        group.setExclusive(True)
        for name in style.THEMES:
            act = QAction(name, self, checkable=True)
            act.setChecked(name == style.current_theme())
            act.triggered.connect(lambda _=False, n=name:
                                  self._apply_theme(n))
            group.addAction(act)
            theme_menu.addAction(act)

        ex = m.addMenu("E&xamples")
        categories = {}
        for name, cat, builder in examples.EXAMPLES:
            if cat not in categories:
                categories[cat] = ex.addMenu(cat)
            categories[cat].addAction(self._act(
                name, None,
                lambda _=False, b=builder: self._load_example(b)))

        h = m.addMenu("&Help")
        h.addAction(self._act("&User Guide", "F1", self._user_guide))
        h.addSeparator()
        h.addAction(self._act("Check for &Updates...", None,
                              self._check_updates, "mdi.cloud-download-outline",
                              "See whether a newer KherveBook has been "
                              "released"))
        auto = QAction("Check for Updates on Startup", self, checkable=True)
        auto.setChecked(updater.startup_check_enabled())
        auto.toggled.connect(updater.set_startup_check)
        h.addAction(auto)
        h.addSeparator()
        h.addAction(self._act("Report an &Issue / Feedback...", None,
                              self._report_issue, "mdi.bug-outline",
                              "Open the KherveBook issue tracker on GitHub"))
        h.addAction(self._act("&About", None, self._about))

    #: (label, type-key) pairs for the Jupyter-style cell-type selector.
    CELL_TYPES = [("Code", "code"), ("Markdown", "markdown"),
                  ("Note", "note"), ("LaTeX", "latex"), ("Sheet", "sheet"),
                  ("SVG", "svg"), ("JavaScript", "js"), ("File", "file"),
                  ("KFit", "kfit")]

    def _build_toolbar(self):
        """Jupyter-style main toolbar: file/cell ops, run, cell type."""
        nb = self.notebook
        tb = self._main_tb = QToolBar("Main")
        tb.setMovable(False)
        tb.setIconSize(QSize(32, 32))
        self.addToolBar(tb)

        tb.addAction(self._act("New", None, self.new_file,
                               "mdi.book-plus-outline",
                               "New notebook (Ctrl+N)"))
        tb.addAction(self._act("Open", None, self.open_file,
                               "mdi.folder-open-outline",
                               "Open a notebook (Ctrl+O)"))
        tb.addAction(self._act("Save", None, self.save_file,
                               "mdi.content-save",
                               "Save the notebook (Ctrl+S)"))
        tb.addAction(self._act("Snapshot", None, self._commit_and_maybe_push,
                               "mdi.cloud-upload-outline",
                               "Save a version snapshot and upload it to "
                               "the cloud (GitHub, GitLab, …)"))
        tb.addAction(self._act("History", None, self._show_history,
                               "mdi.history",
                               "Browse this notebook's version history"))
        tb.addSeparator()
        tb.addAction(self._act("Undo", None, self._smart_undo,
                               "mdi.undo", "Undo (Ctrl+Z)"))
        tb.addAction(self._act("Redo", None, self._smart_redo,
                               "mdi.redo", "Redo (Ctrl+Shift+Z)"))
        tb.addSeparator()
        tb.addAction(self._act("Add cell", None,
                               lambda: nb.add_cell_below("code"),
                               "mdi.plus", "Insert a code cell below"))
        tb.addAction(self._act("Cut", None, nb.cut_current,
                               "mdi.content-cut", "Cut the selected cell"))
        tb.addAction(self._act("Copy", None, nb.copy_current,
                               "mdi.content-copy", "Copy the selected cell"))
        tb.addAction(self._act("Paste", None, nb.paste_cell,
                               "mdi.content-paste", "Paste the cell below"))
        tb.addSeparator()
        tb.addAction(self._act("Up", None, lambda: nb.move_current(-1),
                               "mdi.arrow-up", "Move the cell up"))
        tb.addAction(self._act("Down", None, lambda: nb.move_current(1),
                               "mdi.arrow-down", "Move the cell down"))
        tb.addSeparator()
        tb.addAction(self._act("Run", None, nb.run_current,
                               "mdi.play", "Run the selected cell "
                               "(Shift+Enter runs and advances)",
                               color="#27ae60"))
        tb.addAction(self._act("Run continuously", None,
                               lambda: nb.start_loop(),
                               "mdi.repeat", "Re-run the selected cell "
                               "continuously (simulations, animations)"))
        tb.addAction(self._act("Stop", None, nb.stop_loop,
                               "mdi.stop", "Stop the continuous run",
                               color="#c0392b"))
        tb.addAction(self._act("Restart", None, nb.restart_kernel,
                               "mdi.refresh", "Restart the kernel "
                               "(clears all variables)"))
        tb.addAction(self._act("Run all", None, nb.run_all,
                               "mdi.fast-forward",
                               "Restart and run every cell"))
        tb.addSeparator()
        # Side-panel toggles — the same checkable actions as the View menu,
        # so the button, menu item and the dock's own close button all stay
        # in sync. Icons set here so they recolour on a theme rebuild.
        self._explorer_toggle.setIcon(icon("mdi.file-tree"))
        self._explorer_toggle.setToolTip(
            "Show/hide the file explorer (Ctrl+B)")
        tb.addAction(self._explorer_toggle)
        self._ai_toggle.setIcon(icon("mdi.robot-outline"))
        self._ai_toggle.setToolTip(
            "Show/hide the AI assistant (Ctrl+Shift+A)")
        tb.addAction(self._ai_toggle)
        tb.addSeparator()
        # Reuse the View-menu action so the button and menu item share
        # state; set its icon here so it recolours on a theme rebuild.
        self.page_mode_act.setIcon(icon("mdi.view-day"))
        self.page_mode_act.setToolTip(
            "Page Mode: one continuous white page, cell borders hidden "
            "(Ctrl+Shift+P)")
        tb.addAction(self.page_mode_act)
        tb.addSeparator()

        self.cell_type_combo = QComboBox()
        for label, _key in self.CELL_TYPES:
            self.cell_type_combo.addItem(label)
        self.cell_type_combo.setToolTip("Change the selected cell's type")
        self.cell_type_combo.activated.connect(
            lambda i: nb.convert_current(self.CELL_TYPES[i][1]))
        tb.addWidget(self.cell_type_combo)

        # Second row: tools specific to the focused cell's type.
        self.addToolBarBreak()
        self.cell_toolbar = CellToolBar(nb, self)
        self.addToolBar(self.cell_toolbar)

    def _toggle_page_mode(self, on):
        self.notebook.set_page_mode(on)
        QSettings("Kherve", "KherveBook").setValue("view/page_mode", on)

    def _toggle_interactive_plots(self, on):
        """Embed live zoom/pan figures instead of static PNGs (re-run a
        cell to apply). Survives a kernel restart."""
        self.notebook.kernel.interactive_figures = on
        QSettings("Kherve", "KherveBook").setValue(
            "view/interactive_plots", on)

    def _dock_explorer(self, area):
        self.explorer.setFloating(False)
        self.addDockWidget(area, self.explorer)
        self.explorer.show()

    def _float_explorer(self):
        self.explorer.setFloating(True)
        self.explorer.show()

    def _apply_theme(self, name: str):
        """Switch theme live: stylesheet, icons, highlighters, LaTeX."""
        style.apply_style(QApplication.instance(), name)
        # Rebuild toolbars so their icons pick up the theme colour.
        for tb in (self._main_tb, self.cell_toolbar):
            self.removeToolBar(tb)
            tb.deleteLater()
        self._build_toolbar()
        self._on_current_cell(self.notebook.current)
        dark = style.tokens()["dark"]
        for cell in self.notebook.cells:
            hl = getattr(cell, "_highlighter", None)
            if hl is not None:
                hl.set_dark(dark)
            # Re-render LaTeX so its text colour matches the theme.
            if cell.CELL_TYPE == "latex" and cell.view.isVisible():
                cell.execute(self.notebook.kernel)

    def _on_current_cell(self, cell):
        """Follow the focused cell: type selector + contextual toolbar."""
        if cell is None:
            return
        self.cell_toolbar.set_mode(cell.CELL_TYPE)
        for i, (_label, key) in enumerate(self.CELL_TYPES):
            if key == cell.CELL_TYPE:
                self.cell_type_combo.blockSignals(True)
                self.cell_type_combo.setCurrentIndex(i)
                self.cell_type_combo.blockSignals(False)
                break

    def _act(self, text, shortcut, slot, icon_name=None, tip=None,
             color=None):
        action = QAction(text, self)
        if icon_name:
            action.setIcon(icon(icon_name, color) if color
                           else icon(icon_name))
        if shortcut:
            action.setShortcut(shortcut)
        if tip:
            action.setToolTip(tip)
        action.triggered.connect(slot)
        return action

    # -- recent files -------------------------------------------------------
    _MAX_RECENT = 12

    def _recent_files(self) -> list:
        val = QSettings("Kherve", "KherveBook").value("recent_files", [])
        if isinstance(val, str):            # a one-item list comes back as str
            val = [val]
        return [str(x) for x in (val or [])]

    def _add_recent(self, path):
        if not path:
            return
        path = str(Path(path))
        files = [f for f in self._recent_files() if f != path]
        files.insert(0, path)
        del files[self._MAX_RECENT:]
        QSettings("Kherve", "KherveBook").setValue("recent_files", files)

    def _short_path(self, path) -> str:
        p = Path(path)
        parent = str(p.parent)
        home = str(Path.home())
        if parent.startswith(home):
            parent = "~" + parent[len(home):]
        parent = parent.replace("\\", "/")
        if len(parent) > 40:
            parent = parent[:18] + "…" + parent[-20:]
        return f"{p.name}    {parent}"

    def _rebuild_recent_menu(self):
        self.recent_menu.clear()
        files = self._recent_files()
        if not files:
            none = self.recent_menu.addAction("(no recent files)")
            none.setEnabled(False)
            return
        for i, path in enumerate(files):
            accel = f"&{i + 1}" if i < 9 else f"{i + 1}"
            shown = self._short_path(path).replace("&", "&&")
            act = self.recent_menu.addAction(f"{accel}  {shown}")
            act.setToolTip(path)
            act.setEnabled(Path(path).exists())
            act.triggered.connect(lambda _=False, p=path: self._open_path(p))
        self.recent_menu.addSeparator()
        self.recent_menu.addAction("&Clear Recent Files", self._clear_recent)

    def _clear_recent(self):
        QSettings("Kherve", "KherveBook").setValue("recent_files", [])
        self._rebuild_recent_menu()

    # -- file I/O -----------------------------------------------------------
    def new_file(self):
        if not self._confirm_discard():
            return
        self.notebook.load_json('{"cells": []}')
        self.path = None
        self.notebook.set_document_path(None)
        self.dirty = False
        self._update_title()

    @staticmethod
    def _new_instance_command():
        """(args, cwd) that launch another, independent app instance —
        a separate process so its kernel can't block this window's."""
        import os
        import sys
        if getattr(sys, "frozen", False):       # packaged app: re-run the exe
            return [sys.executable], None
        import khervebook
        root = os.path.dirname(os.path.dirname(
            os.path.abspath(khervebook.__file__)))
        return [sys.executable, "-m", "khervebook"], root

    def new_window(self):
        import subprocess
        args, cwd = self._new_instance_command()
        try:
            subprocess.Popen(args, cwd=cwd)
        except Exception as exc:
            QMessageBox.warning(self, APP_NAME,
                                f"Could not open a new window:\n{exc}")

    def open_file(self):
        recent = self._recent_files()
        start = str(Path(recent[0]).parent) if recent else ""
        name, _ = QFileDialog.getOpenFileName(self, "Open notebook",
                                              start, FILE_FILTER)
        if name:
            self._open_path(name)

    def _open_path(self, name: str):
        if not self._confirm_discard():
            return
        try:
            self.notebook.load_json(Path(name).read_text(encoding="utf-8"))
        except Exception as exc:
            QMessageBox.critical(self, APP_NAME, f"Could not open file:\n{exc}")
            return
        self.path = name
        self.notebook.set_document_path(name)
        self.dirty = False
        self._add_recent(name)
        self.explorer.show_file(name)
        self._update_title()

    def save_file(self):
        if self.path is None:
            self.save_as()
            return
        self.notebook.set_document_path(self.path)
        self.notebook.prepare_save()      # externalise large attachments
        Path(self.path).write_text(self.notebook.to_json(), encoding="utf-8")
        self.dirty = False
        self._add_recent(self.path)
        self.explorer.show_file(self.path)
        self._update_title()
        self._git_after_save(Path(self.path))

    def save_as(self):
        recent = self._recent_files()
        start = str(Path(recent[0]).parent) if recent else ""
        name, _ = QFileDialog.getSaveFileName(self, "Save notebook",
                                              start, FILE_FILTER)
        if not name:
            return
        if not name.lower().endswith(".kbook"):
            name += ".kbook"
        self.path = name
        self.save_file()

    IPYNB_FILTER = "Jupyter / Colab notebook (*.ipynb);;All files (*)"

    def import_ipynb(self):
        name, _ = QFileDialog.getOpenFileName(
            self, "Import Jupyter/Colab notebook", "", self.IPYNB_FILTER)
        if not name or not self._confirm_discard():
            return
        try:
            self.notebook.load_ipynb(Path(name).read_text(encoding="utf-8"))
        except Exception as exc:
            QMessageBox.critical(self, APP_NAME,
                                 f"Could not import notebook:\n{exc}")
            return
        self.path = None            # imported content -> save as a new .kbook
        self.dirty = True
        self.explorer.show_file(name)
        self._update_title()

    def export_ipynb(self):
        name, _ = QFileDialog.getSaveFileName(
            self, "Export as Jupyter/Colab notebook", "", self.IPYNB_FILTER)
        if not name:
            return
        if not name.lower().endswith(".ipynb"):
            name += ".ipynb"
        try:
            Path(name).write_text(self.notebook.to_ipynb(), encoding="utf-8")
        except Exception as exc:
            QMessageBox.critical(self, APP_NAME,
                                 f"Could not export notebook:\n{exc}")
            return
        self.explorer.show_file(name)

    IMAGE_FILTER = ("Images and PDF (*.png *.jpg *.jpeg *.gif *.bmp *.pdf);;"
                    "All files (*)")

    def insert_image_or_pdf(self):
        name, _ = QFileDialog.getOpenFileName(
            self, "Insert image or PDF", "", self.IMAGE_FILTER)
        if not name:
            return
        if not self.notebook.open_file_in_cell(name):
            QMessageBox.critical(self, APP_NAME,
                                 f"Could not insert:\n{Path(name).name}")

    SHEET_FILTER = ("Spreadsheets (*.xlsx *.xlsm *.csv *.tsv);;"
                    "All files (*)")

    def import_spreadsheet(self):
        name, _ = QFileDialog.getOpenFileName(
            self, "Import spreadsheet", "", self.SHEET_FILTER)
        if not name:
            return
        if not self.notebook.open_file_in_cell(name):
            QMessageBox.critical(self, APP_NAME,
                                 f"Could not import:\n{Path(name).name}")

    def closeEvent(self, event):
        if self._confirm_discard():
            settings = QSettings("Kherve", "KherveBook")
            settings.setValue("win/geometry_v2", self.saveGeometry())
            settings.setValue("win/state", self.saveState())
            event.accept()
        else:
            event.ignore()

    def _confirm_discard(self) -> bool:
        if not self.dirty:
            return True
        ret = QMessageBox.question(
            self, APP_NAME, "Save changes to the current notebook?",
            QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel)
        if ret == QMessageBox.Save:
            self.save_file()
            return not self.dirty or self.path is not None
        return ret == QMessageBox.Discard

    def _mark_dirty(self):
        if not self.dirty:
            self.dirty = True
            self._update_title()

    def _update_title(self):
        name = Path(self.path).name if self.path else "Untitled"
        star = "*" if self.dirty else ""
        self.setWindowTitle(f"{star}{name} — {APP_NAME} v{__version__}")

    def _smart_undo(self):
        """Undo text in the focused editor first, else a cell-structure step."""
        from PyQt5.QtWidgets import QPlainTextEdit
        fw = QApplication.focusWidget()
        if isinstance(fw, QPlainTextEdit) and fw.document().isUndoAvailable():
            fw.undo()
        else:
            self.notebook.undo()

    def _smart_redo(self):
        from PyQt5.QtWidgets import QPlainTextEdit
        fw = QApplication.focusWidget()
        if isinstance(fw, QPlainTextEdit) and fw.document().isRedoAvailable():
            fw.redo()
        else:
            self.notebook.redo()

    # -- git integration ----------------------------------------------------
    def _git_after_save(self, path: Path):
        """Auto-commit the just-saved notebook and, if a remote is set,
        push it in the background. No-op when pygit2 is unavailable."""
        if not git_backend.is_available():
            self.statusBar().showMessage(
                "Saved (install pygit2 to enable version history)", 5000)
            return
        commit_msg = self._pending_commit_msg or (
            f"Save {path.name} at "
            f"{datetime.now().isoformat(timespec='seconds')}")
        self._pending_commit_msg = None
        try:
            git_backend.init_repo(path.parent)
            oid = git_backend.commit_all(path.parent, commit_msg,
                                         file_stem=path.stem)
        except Exception as exc:
            self.statusBar().showMessage(f"Snapshot failed: {exc}", 5000)
            return
        if not oid:
            self.statusBar().showMessage(
                "Saved (nothing new to snapshot)", 4000)
            return
        if git_backend.get_remotes(path.parent):
            # Push off the main thread so a slow / dead remote can't
            # freeze the window on every Ctrl+S.
            if self._git_worker is not None and self._git_worker.isRunning():
                self.statusBar().showMessage(
                    "Saved and snapshot created (a git upload is already "
                    "running)", 5000)
                return
            self.statusBar().showMessage(
                "Saved and snapshot created — uploading…", 0)
            self._start_git_worker("push", path.parent, "origin")
        else:
            self.statusBar().showMessage(
                "Saved and snapshot created "
                "(use Git → Connect to GitHub to enable cloud backup)", 6000)

    def _commit_and_maybe_push(self):
        if self.path is None:
            # No file yet — saving creates the first snapshot for us.
            self.save_as()
            return
        default_msg = (f"Save {Path(self.path).name} at "
                       f"{datetime.now().isoformat(timespec='seconds')}")
        msg, ok = QInputDialog.getText(
            self, "Commit message", "Describe what you changed:",
            text=default_msg)
        if not ok:
            return
        self._pending_commit_msg = msg.strip() or default_msg
        self.save_file()

    def _start_git_worker(self, op: str, repo_dir: Path, remote_name: str):
        """Spawn a _GitNetworkWorker for pull / push. Held on
        self._git_worker so Qt doesn't GC the thread mid-run."""
        worker = _GitNetworkWorker(op, repo_dir, remote_name)
        worker.finished_with.connect(self._on_git_done)
        self._git_worker = worker
        if op == "pull":
            self.statusBar().showMessage(
                f"Downloading latest from {remote_name}…", 0)
        worker.start()

    def _on_git_done(self, op: str, ok: bool, msg: str):
        if op == "pull":
            if ok:
                if "up to date" in msg.lower():
                    self.statusBar().showMessage(
                        "Already up to date — you have the latest version",
                        5000)
                else:
                    self.statusBar().showMessage(msg, 6000)
                    self._reload_current()
            else:
                self.statusBar().clearMessage()
                QMessageBox.warning(
                    self, "Download failed",
                    f"{msg}\n\n"
                    "What you can try:\n"
                    "  • Check your internet connection\n"
                    "  • Make sure the cloud URL is correct "
                    "(Git → Connect to GitHub)\n"
                    "  • If the problem says \"diverged\", resolve the "
                    "merge from the git command line")
        elif op == "push":
            if ok:
                self.statusBar().showMessage(
                    "Saved, snapshot created, and uploaded to cloud", 5000)
            else:
                self.statusBar().showMessage(
                    "Saved and snapshot created "
                    "(upload failed — see dialog)", 8000)
                self._show_push_failure_dialog(msg)
        self._git_worker = None

    def _show_push_failure_dialog(self, error_msg: str):
        """Surface a real push failure with actionable advice. The most
        common cause on Windows is HTTPS authentication — GitHub needs a
        Personal Access Token stored via Windows Credential Manager
        (which the system `git` CLI talks to)."""
        hints = []
        if "authentication" in error_msg.lower():
            hints.append(
                "GitHub no longer accepts your account password over "
                "HTTPS — you need a <b>Personal Access Token</b>.<br>"
                "&nbsp;&nbsp;1. Go to "
                "<a href='https://github.com/settings/tokens'>"
                "github.com/settings/tokens</a> → Generate new token "
                "(classic)<br>"
                "&nbsp;&nbsp;2. Tick the <code>repo</code> scope, generate, "
                "copy the token<br>"
                "&nbsp;&nbsp;3. Next time the app asks for a password, paste "
                "the token instead.")
        elif "not found" in error_msg.lower() or "404" in error_msg:
            hints.append(
                "GitHub says the repository does not exist. Check that "
                "the URL in <b>Git → Connect to GitHub</b> matches the one "
                "on the repo's GitHub page (Code → HTTPS).")
        elif "rejected" in error_msg.lower() or "non-fast-forward" in error_msg:
            hints.append(
                "Someone else pushed to this branch since you last pulled. "
                "Use <b>Git → Download latest from cloud</b> first, then "
                "save again.")
        if not git_backend._system_git_available():
            hints.append(
                "<i>Tip: install Git for Windows so the app can use your "
                "Windows Credential Manager for HTTPS pushes — "
                "<a href='https://git-scm.com/download/win'>"
                "git-scm.com/download/win</a></i>")
        body = (f"<b>Could not upload to cloud.</b><br><br>"
                f"<code>{error_msg}</code>")
        if hints:
            body += "<br><br>" + "<br><br>".join(hints)
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Warning)
        box.setWindowTitle("Upload failed")
        box.setTextFormat(Qt.RichText)
        box.setTextInteractionFlags(
            Qt.TextSelectableByMouse | Qt.LinksAccessibleByMouse)
        box.setText(body)
        box.exec_()

    def _pull_from_remote(self):
        if self.path is None:
            QMessageBox.information(
                self, "Download latest",
                "You need to save your notebook first.\n\n"
                "Use File → Save (Ctrl+S), then try again.")
            return
        if not git_backend.is_available():
            QMessageBox.warning(
                self, "Download latest",
                "The pygit2 library is not installed, so cloud features "
                "are unavailable.\n\nTo fix this, run:  pip install pygit2")
            return
        repo_dir = Path(self.path).parent
        remotes = git_backend.get_remotes(repo_dir)
        if not remotes:
            ask = QMessageBox.question(
                self, "Download latest",
                "This notebook is not connected to a cloud service yet.\n\n"
                "To download changes you first need to connect to GitHub, "
                "GitLab or another git server.\n\nSet that up now?")
            if ask == QMessageBox.Yes:
                self._configure_remotes()
            return
        if len(remotes) == 1:
            remote_name = remotes[0][0]
        else:
            names = [n for n, _ in remotes]
            chosen, ok = QInputDialog.getItem(
                self, "Download from…", "Which cloud service?",
                names, 0, False)
            if not ok:
                return
            remote_name = chosen
        if self._git_worker is not None and self._git_worker.isRunning():
            self.statusBar().showMessage(
                "A git operation is already in progress, please wait…", 4000)
            return
        self._start_git_worker("pull", repo_dir, remote_name)

    def _configure_remotes(self):
        if self.path is None:
            QMessageBox.information(
                self, "Connect to cloud",
                "You need to save your notebook first so KherveBook knows "
                "where to create the connection.\n\n"
                "Use File → Save (Ctrl+S), then try again.")
            return
        if not git_backend.is_available():
            QMessageBox.warning(
                self, "Connect to cloud",
                "The pygit2 library is not installed, so cloud features "
                "are unavailable.\n\nTo fix this, run:  pip install pygit2")
            return
        from .remote_dialog import RemoteDialog
        RemoteDialog(Path(self.path).parent, self).exec_()

    def _reload_current(self):
        """Re-read the current notebook from disk after an external
        change (e.g. a successful pull or a restore)."""
        if self.path is None or not Path(self.path).exists():
            return
        try:
            self.notebook.load_json(
                Path(self.path).read_text(encoding="utf-8"))
            self.notebook.set_document_path(self.path)
            self.dirty = False
            self._update_title()
        except Exception as exc:
            self.statusBar().showMessage(f"Reload failed: {exc}", 6000)

    def _show_history(self):
        if self.path is None:
            QMessageBox.information(
                self, "Version history",
                "You need to save your notebook at least once before there "
                "is any history to show.\n\n"
                "Use File → Save (Ctrl+S), then try again.")
            return
        if not git_backend.is_available():
            QMessageBox.warning(
                self, "Version history",
                "The pygit2 library is not installed, so version history "
                "is unavailable.\n\nTo fix this, run:  pip install pygit2")
            return
        repo_dir = Path(self.path).parent
        if not git_backend.history_detailed(repo_dir, limit=1):
            QMessageBox.information(
                self, "Version history",
                "No snapshots yet. Every time you save, KherveBook "
                "automatically creates a snapshot.\n\n"
                "Save your notebook and come back to see its history.")
            return
        from .history_dialog import HistoryDialog
        HistoryDialog(repo_dir, self,
                      file_stem=Path(self.path).stem).exec_()

    def _show_branches(self):
        if self.path is None:
            QMessageBox.information(
                self, "Branches",
                "Save your notebook first so the repository exists.")
            return
        if not git_backend.is_available():
            QMessageBox.warning(
                self, "Branches",
                "The pygit2 library is not installed.\n\n"
                "To fix this, run:  pip install pygit2")
            return
        from .history_dialog import HistoryDialog
        HistoryDialog(Path(self.path).parent, self).exec_()

    #: KherveBook's issue tracker (Help > Report an Issue).
    ISSUES_URL = "https://github.com/gkerherve/KherveBook/issues"

    def _report_issue(self):
        from PyQt5.QtCore import QUrl
        from PyQt5.QtGui import QDesktopServices
        QDesktopServices.openUrl(QUrl(self.ISSUES_URL))

    def _user_guide(self):
        from .userguide import show_user_guide
        show_user_guide(self)

    def _about(self):
        import sys

        import matplotlib
        import numpy
        from PyQt5.QtCore import PYQT_VERSION_STR, QT_VERSION_STR

        def _ver(mod):
            try:
                return __import__(mod).__version__
            except Exception:
                return "—"

        box = QMessageBox(self)
        box.setWindowTitle(f"About {APP_NAME}")
        box.setIconPixmap(app_icon().pixmap(64, 64))
        box.setTextFormat(Qt.RichText)
        box.setText(
            f"<h2 style='margin-bottom:0'>"
            f"<span style='color:#3776ab'>Kherve</span>"
            f"<span style='color:#e07b39'>Book</span></h2>"
            f"<p style='color:gray;margin-top:2px'>version {__version__}</p>"
            f"<p>A Jupyter-inspired computational notebook — runnable "
            f"Python, Markdown, LaTeX, live spreadsheets, drawings and "
            f"imported images/PDFs in one native desktop document.</p>"
            f"<hr>"
            f"<p><b>Created by Gwilherm Kerherve</b><br>"
            f"Imperial College London<br>"
            f"<a href='https://github.com/gkerherve'>github.com/gkerherve</a>"
            f"</p>"
            f"<p>Part of the <b>Kherve</b> family of native scientific "
            f"apps — KherveFitting (XPS curve fitting), KherveSheet "
            f"(spreadsheets), KherveTeX (LaTeX), KherveDOC (documents), "
            f"KhervePaint (drawing), KhervePDF and KherveBook.</p>"
            f"<hr>"
            f"<p style='color:gray'><b>Built with</b> "
            f"Python {sys.version.split()[0]}, Qt {QT_VERSION_STR}, "
            f"PyQt5 {PYQT_VERSION_STR}, matplotlib {matplotlib.__version__}, "
            f"NumPy {numpy.__version__}, SciPy {_ver('scipy')}, "
            f"pandas {_ver('pandas')}, SymPy {_ver('sympy')}, "
            f"openpyxl {_ver('openpyxl')}, PyMuPDF {_ver('fitz')}.</p>"
            f"<p>Copyright &copy; 2026 Gwilherm Kerherve — licensed under "
            f"the <a href='https://www.gnu.org/licenses/gpl-3.0.html'>"
            f"GNU GPL v3.0</a>.</p>")
        box.exec_()
