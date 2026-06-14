"""MainWindow shell: menus, toolbar, file I/O for .kbook documents.

Copyright (C) 2026 Gwilherm Kerherve

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.
"""

from pathlib import Path

from PyQt5.QtCore import QSettings, QSize, Qt
from PyQt5.QtWidgets import (QAction, QActionGroup, QApplication, QComboBox,
                             QFileDialog, QMainWindow, QMessageBox, QToolBar)

from . import examples, style

from . import APP_NAME, __version__
from .celltoolbar import CellToolBar
from .explorer import FileExplorer
from .icons import app_icon, icon
from .notebook import NotebookWidget

FILE_FILTER = "KherveBook notebook (*.kbook);;All files (*)"


class MainWindow(QMainWindow):

    def __init__(self):
        super().__init__()
        self.notebook = NotebookWidget()
        self.notebook.modified.connect(self._mark_dirty)
        self.setCentralWidget(self.notebook)
        self.path = None
        self.dirty = False
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

    def _load_example(self, builder):
        if not self._confirm_discard():
            return
        examples.load_example(self.notebook, builder)
        self.path = None
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
        f.addAction(self._act("&Open...", "Ctrl+O", self.open_file))
        f.addAction(self._act("&Save", "Ctrl+S", self.save_file))
        f.addAction(self._act("Save &As...", "Ctrl+Shift+S", self.save_as))
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
        c.addAction(self._act("Add &LaTeX Cell", "Ctrl+Shift+L",
                              lambda: self.notebook.add_cell_below("latex")))
        c.addAction(self._act("Add &Sheet Cell", "Ctrl+Shift+T",
                              lambda: self.notebook.add_cell_below("sheet")))
        c.addAction(self._act("Add S&VG Cell", None,
                              self._add_svg_cell))
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

        v = m.addMenu("&View")
        toggle = self.explorer.toggleViewAction()
        toggle.setText("&File Explorer")
        toggle.setShortcut("Ctrl+B")
        v.addAction(toggle)
        ai_toggle = self.ai_chat.toggleViewAction()
        ai_toggle.setText("&AI Assistant")
        ai_toggle.setShortcut("Ctrl+Shift+A")
        v.addAction(ai_toggle)
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
        h.addAction(self._act("&About", None, self._about))

    #: (label, type-key) pairs for the Jupyter-style cell-type selector.
    CELL_TYPES = [("Code", "code"), ("Markdown", "markdown"),
                  ("LaTeX", "latex"), ("Sheet", "sheet"), ("SVG", "svg")]

    def _build_toolbar(self):
        """Jupyter-style main toolbar: file/cell ops, run, cell type."""
        nb = self.notebook
        tb = self._main_tb = QToolBar("Main")
        tb.setMovable(False)
        tb.setIconSize(QSize(32, 32))
        self.addToolBar(tb)

        tb.addAction(self._act("Save", None, self.save_file,
                               "mdi.content-save",
                               "Save the notebook (Ctrl+S)"))
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

    # -- file I/O -----------------------------------------------------------
    def new_file(self):
        if not self._confirm_discard():
            return
        self.notebook.load_json('{"cells": []}')
        self.path = None
        self.dirty = False
        self._update_title()

    def open_file(self):
        name, _ = QFileDialog.getOpenFileName(self, "Open notebook",
                                              "", FILE_FILTER)
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
        self.dirty = False
        self.explorer.show_file(name)
        self._update_title()

    def save_file(self):
        if self.path is None:
            self.save_as()
            return
        Path(self.path).write_text(self.notebook.to_json(), encoding="utf-8")
        self.dirty = False
        self.explorer.show_file(self.path)
        self._update_title()

    def save_as(self):
        name, _ = QFileDialog.getSaveFileName(self, "Save notebook",
                                              "", FILE_FILTER)
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
