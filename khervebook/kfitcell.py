"""KFit cell — a KherveFitting project inside a notebook.

Holds one ``.kfit`` and shows it two ways, switched by tabs: a **Plot**
drawn the way KherveFitting draws it (raw data, background, shaded fitted
peaks, envelope and residuals, with the axis reversed for binding energy
and FTIR) and a **Data** table of the same numbers, column per curve. A
drop-down picks which sheet — core level, XRD scan, TGA segment, EIS
sweep — is shown; the format keeps every technique in the same three
keys, so the cell plots them all.

Storage matches the File cell: saving the notebook writes the project
into the ``<stem>_files/`` sidecar folder beside it (and so it is
versioned by the notebook's own Git repo) and the document keeps only
the relative path.

Copyright (C) 2026 Gwilherm Kerherve

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.
"""

import json
from pathlib import Path

import numpy as np

from PyQt5.QtCore import QAbstractTableModel, QModelIndex, Qt
from PyQt5.QtWidgets import (QComboBox, QHBoxLayout, QLabel, QPushButton,
                             QTableView, QTabWidget, QVBoxLayout, QWidget)

from . import filedialog, kfitio
from .cells import CELL_CLASSES, CellWidget
from .filecell import _Attachment
from .icons import icon

#: KherveFitting's own plot defaults, so a spectrum looks the same in
#: both apps (its KherveFitting.py sets these as the shipped preferences).
SCATTER_COLOR = "#000000"
SCATTER_SIZE = 4
BACKGROUND_COLOR = "#808080"
BACKGROUND_ALPHA = 0.5
ENVELOPE_COLOR = "#0000FF"
ENVELOPE_ALPHA = 0.6
RESIDUAL_COLOR = "#00FF00"
RESIDUAL_ALPHA = 0.4
PEAK_ALPHA = 0.3
PEAK_LINE_ALPHA = 0.7
PEAK_COLORS = ["#FF0000", "#00FF00", "#0000FF", "#FFFF00", "#FF00FF",
               "#00FFFF", "#800000", "#008000", "#000080", "#808000",
               "#800080", "#008080", "#C0C0C0", "#808080", "#9B30FF"]

#: Above this many points a scatter is unreadable and slow to draw, so the
#: trace becomes a line — TGA and XRD sheets routinely run to 70k points.
_SCATTER_LIMIT = 5000


class _CurveModel(QAbstractTableModel):
    """The sheet's columns as a table.

    A table *model* rather than a QTableWidget because a TGA run is ~70k
    rows: filling that many QTableWidgetItems freezes the window for
    seconds, while a model only ever renders the visible rows.
    """

    def __init__(self, headers, columns, parent=None):
        super().__init__(parent)
        self._headers = headers
        self._columns = columns
        self._rows = max((len(c) for c in columns), default=0)

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else self._rows

    def columnCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self._headers)

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid() or role not in (Qt.DisplayRole, Qt.ToolTipRole):
            return None
        column = self._columns[index.column()]
        if index.row() >= len(column):
            return None
        value = column[index.row()]
        return "" if value is None or not np.isfinite(value) \
            else f"{value:.6g}"

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if role != Qt.DisplayRole:
            return None
        if orientation == Qt.Horizontal:
            return self._headers[section]
        return str(section + 1)


class KFitCell(CellWidget):
    """A cell holding one KherveFitting ``.kfit`` project."""

    CELL_TYPE = "kfit"

    def __init__(self, source=""):
        super().__init__(source)
        self.gutter.setText("kfit")
        self.editor.hide()                 # base plain editor unused here
        self._att = None                   # the held .kfit, as an _Attachment
        self._project = None               # parsed kfitio.KFitProject
        self._error = ""                   # why parsing failed, if it did
        self._doc_dir = None
        self._stem = "notebook"
        self._wanted_sheet = ""            # sheet to restore from the .kbook
        self._origin = ""                  # where it was loaded from, for Refresh
        self._plot = None
        self._card = self._build_card()
        self.column.addWidget(self._card)
        self.setAcceptDrops(True)
        if source:
            self.set_source(source)
        self._reload_project()

    # -- UI shell ---------------------------------------------------------
    def _build_card(self) -> QWidget:
        card = QWidget()
        outer = QVBoxLayout(card)
        outer.setContentsMargins(4, 4, 4, 4)
        outer.setSpacing(6)

        header = QHBoxLayout()
        header.setSpacing(8)
        self._sheet_box = QComboBox()
        self._sheet_box.setMinimumWidth(160)
        self._sheet_box.setToolTip("Which sheet of the project to show")
        self._sheet_box.currentIndexChanged.connect(self._on_sheet_changed)
        header.addWidget(self._sheet_box)
        # Not "_title": CellWidget already owns that name for the cell's
        # own heading, and shadowing it with a widget breaks every later
        # set_title() — and the refresh that follows it.
        self._info = QLabel("")
        self._info.setStyleSheet("color: #57606a;")
        header.addWidget(self._info, 1)

        self._refresh_btn = QPushButton("Refresh")
        self._refresh_btn.setIcon(icon("mdi.refresh"))
        self._refresh_btn.setToolTip(
            "Re-read the .kfit from disk — after re-fitting it elsewhere")
        self._refresh_btn.clicked.connect(self.refresh)
        header.addWidget(self._refresh_btn)

        self._open_btn = QPushButton("Open in KherveFitting")
        self._open_btn.setIcon(icon("mdi.chart-bell-curve"))
        self._open_btn.setToolTip(
            "Open this project in KherveFitting and reload it on save")
        self._open_btn.clicked.connect(self.open_in_khervefitting)
        header.addWidget(self._open_btn)
        load = QPushButton("Load .kfit…")
        load.setIcon(icon("mdi.folder-open-outline"))
        load.clicked.connect(self.choose_file)
        header.addWidget(load)
        outer.addLayout(header)

        self._tabs = QTabWidget()
        self._plot_page = QWidget()
        self._plot_layout = QVBoxLayout(self._plot_page)
        self._plot_layout.setContentsMargins(0, 0, 0, 0)
        self._tabs.addTab(self._plot_page, "Plot")
        self._table = QTableView()
        self._table.setAlternatingRowColors(True)
        self._tabs.addTab(self._table, "Data")
        self._tabs.currentChanged.connect(
            lambda _i: self.content_changed.emit())
        outer.addWidget(self._tabs)

        self._hint = QLabel("")
        self._hint.setWordWrap(True)
        self._hint.setStyleSheet("color: #8a939c; font-style: italic;")
        outer.addWidget(self._hint)
        return card

    # -- loading ----------------------------------------------------------
    def choose_file(self):
        path = filedialog.open_file(
            self, "Open a KherveFitting project", "",
            "KherveFitting project (*.kfit);;All files (*)")
        return self.attach(path) if path else False

    def attach(self, path: str) -> bool:
        p = Path(path)
        try:
            data = p.read_bytes()
        except OSError:
            return False
        self._att = _Attachment(name=p.name, size=len(data), data=data)
        # Remembered so Refresh can pick up a re-fit: the cell holds a copy
        # of the bytes, which would otherwise go stale the moment
        # KherveFitting saves the original again.
        self._origin = str(p.resolve())
        self._wanted_sheet = ""
        self._reload_project()
        self.content_changed.emit()
        return True

    def refresh(self) -> bool:
        """Re-read the .kfit from where it was loaded.

        The cell keeps its own copy so the notebook travels intact, so a
        project re-fitted in KherveFitting since it was loaded needs this
        to catch up. The shown sheet is kept if the new file still has it.
        """
        origin = self._origin
        if not origin:
            self._hint.setText(
                "Nothing to refresh from — this project came from inside "
                "the notebook, not a file on disk. Use “Load .kfit…”.")
            return False
        if not Path(origin).exists():
            self._hint.setText(f"Cannot refresh: {origin} is no longer there.")
            return False
        wanted = self._sheet_box.currentText()
        if not self.attach(origin):
            self._hint.setText(f"Cannot refresh: {origin} could not be read.")
            return False
        self._wanted_sheet = wanted
        self._fill_sheets()
        self._refresh()
        return True

    # -- what code cells and the AI see ------------------------------------
    def project(self):
        """The parsed project, for the ``kfit()`` kernel helper."""
        return self._project

    @property
    def file_name(self) -> str:
        return self._att.name if self._att else ""

    def _reload_project(self):
        """Re-parse the held bytes and repaint. Never raises: a project we
        cannot read says so in the cell instead of breaking the notebook."""
        self._project, self._error = None, ""
        data = self._att.current_bytes(self._doc_dir) if self._att else None
        if data is not None:
            try:
                self._project = kfitio.read_bytes(data)
            except Exception as exc:
                self._error = str(exc)
        self._fill_sheets()
        self._refresh()

    def _fill_sheets(self):
        names = self._project.names if self._project else []
        blocked = self._sheet_box.blockSignals(True)
        self._sheet_box.clear()
        self._sheet_box.addItems(names)
        if self._wanted_sheet in names:
            self._sheet_box.setCurrentIndex(names.index(self._wanted_sheet))
        self._sheet_box.blockSignals(blocked)
        self._sheet_box.setEnabled(bool(names))

    def _on_sheet_changed(self, _index):
        self._refresh()
        self.content_changed.emit()

    # -- views (also driven from the CellToolBar) --------------------------
    def show_plot(self):
        self._tabs.setCurrentIndex(0)

    def show_data(self):
        self._tabs.setCurrentIndex(1)

    # -- the current sheet ------------------------------------------------
    def current_sheet(self):
        if not self._project:
            return None
        name = self._sheet_box.currentText()
        return self._project.sheet(name) if name else None

    def _refresh(self):
        sheet = self.current_sheet()
        self._open_btn.setEnabled(self._att is not None)
        if sheet is None:
            self._info.setText("")
            self._clear_plot()
            self._table.setModel(None)
            self._hint.setText(
                self._error or "No project loaded. Drop a .kfit file here, "
                "or click “Load .kfit…”.")
            return
        name = self._att.name if self._att else ""
        sample = self._project.sample
        self._info.setText(f"{name}  ·  {sheet.summary()}"
                            + (f"  ·  {sample}" if sample
                               and sample != name else ""))
        curves = self._curves(sheet)
        self._draw_plot(sheet, curves)
        self._fill_table(sheet, curves)
        self._hint.setText(self._coverage_note(sheet, curves))

    def _curves(self, sheet):
        """The sheet's traces. Shared with the kfit() kernel helper and the
        AI summary, so the plot, the table and any code cell agree."""
        return sheet.curves()

    @staticmethod
    def _coverage_note(sheet, curves) -> str:
        bits = []
        if curves["skipped"]:
            bits.append("Not drawn — KherveBook has no lineshape for: "
                        + ", ".join(curves["skipped"]))
        if not sheet.peaks:
            bits.append("No fitted peaks in this sheet — showing the raw "
                        "data" + (" and its background."
                                  if sheet.has_background else "."))
        return "  ".join(bits)

    # -- plot -------------------------------------------------------------
    def _clear_plot(self):
        if self._plot is not None:
            self._plot.close_figure()
            self._plot.setParent(None)
            self._plot.deleteLater()
            self._plot = None

    def _draw_plot(self, sheet, curves):
        from matplotlib.figure import Figure
        from .plotcanvas import PlotCanvas

        self._clear_plot()
        figure = Figure(figsize=(6.4, 4.4), tight_layout=True)
        ax = figure.add_subplot(111)
        x = curves["x"]
        y = np.asarray(sheet.y, dtype=float)
        if y.shape != x.shape:
            y = np.zeros_like(x)

        # Photoemission is plotted as points (KherveFitting's default); the
        # other techniques are continuous traces, often tens of thousands
        # of points, where a line is both truer and far faster to draw.
        if len(x) <= _SCATTER_LIMIT and kfitio.is_xps_like(sheet.name):
            ax.scatter(x, y, s=SCATTER_SIZE, c=SCATTER_COLOR,
                       marker="o", label="Raw data", zorder=3)
        else:
            ax.plot(x, y, color=SCATTER_COLOR, lw=1.0, label="Raw data",
                    zorder=3)

        if sheet.has_background:
            ax.plot(x, curves["background"], color=BACKGROUND_COLOR,
                    alpha=BACKGROUND_ALPHA, ls="--", lw=1,
                    label="Background", zorder=2)

        background = curves["background"]
        for i, (name, curve) in enumerate(curves["peaks"]):
            color = PEAK_COLORS[i % len(PEAK_COLORS)]
            top = background + curve
            inside = np.where(curves["mask"], top, np.nan)
            ax.fill_between(x, background, top, where=curves["mask"],
                            color=color, alpha=PEAK_ALPHA, edgecolor="none",
                            label=name, zorder=1)
            ax.plot(x, inside, color=color, alpha=PEAK_LINE_ALPHA, lw=1,
                    zorder=2)

        if curves["envelope"] is not None:
            ax.plot(x, np.where(curves["mask"], curves["envelope"], np.nan),
                    color=ENVELOPE_COLOR, alpha=ENVELOPE_ALPHA, lw=1,
                    label="Envelope", zorder=4)
            self._draw_residuals(ax, x, y, curves)

        ax.set_xlabel(sheet.x_label)
        ax.set_ylabel(sheet.y_label)
        ax.set_title(sheet.name)
        if len(x):
            lo, hi = float(np.nanmin(x)), float(np.nanmax(x))
            ax.set_xlim((hi, lo) if sheet.descending else (lo, hi))
        if 0 < len(curves["peaks"]) <= 12:
            ax.legend(fontsize=7, framealpha=0.6)
        self._plot = PlotCanvas(figure, self._plot_page)
        self._plot_layout.addWidget(self._plot)

    @staticmethod
    def _draw_residuals(ax, x, y, curves):
        """Residuals as their own trace above the spectrum.

        KherveFitting lifts them clear of the data rather than drawing
        them through it, so a small misfit stays visible against a tall
        peak instead of being lost in the trace.
        """
        mask = curves["mask"]
        if not mask.any():
            return
        residual = np.where(mask, y - curves["envelope"], np.nan)
        top = np.nanmax(y[mask]) if mask.any() else 0.0
        span = np.nanmax(np.abs(residual[mask])) if mask.any() else 0.0
        if not np.isfinite(top) or not np.isfinite(span) or span == 0:
            return
        ax.plot(x, residual + top + 1.5 * span, color=RESIDUAL_COLOR,
                alpha=RESIDUAL_ALPHA, lw=1, label="Residuals", zorder=2)

    # -- table ------------------------------------------------------------
    def _fill_table(self, sheet, curves):
        headers = [sheet.x_label, sheet.y_label]
        columns = [curves["x"], np.asarray(sheet.y, dtype=float)]
        if sheet.has_background:
            headers.append("Background")
            columns.append(curves["background"])
        for name, curve in curves["peaks"]:
            headers.append(name)
            columns.append(curves["background"] + curve)
        if curves["envelope"] is not None:
            headers.append("Envelope")
            columns.append(curves["envelope"])
        model = _CurveModel(headers, [np.asarray(c, dtype=float)
                                      for c in columns], self._table)
        self._table.setModel(model)
        self._table.resizeColumnsToContents()

    # -- KherveFitting round trip -----------------------------------------
    def open_in_khervefitting(self):
        """Hand the project to KherveFitting and reload it when it saves."""
        if self._att is None:
            return
        from .appbridge import AppBridge

        if not hasattr(self, "_bridge"):
            self._bridge = AppBridge(self, "KherveFitting", "khervefitting",
                                     ".kfit", self._reload_from_file,
                                     script="KherveFitting.py")
        self._bridge.open(self._write_kfit)

    def _write_kfit(self, path):
        data = self._att.current_bytes(self._doc_dir) if self._att else None
        if data is None:
            raise OSError("this cell holds no project")
        Path(path).write_bytes(data)

    def _reload_from_file(self, path):
        p = Path(path)
        data = p.read_bytes()
        name = self._att.name if self._att else p.name
        self._wanted_sheet = self._sheet_box.currentText()
        self._att = _Attachment(name=name, size=len(data), data=data)
        self._reload_project()
        self.content_changed.emit()

    # -- context (set by the notebook once its path is known) --------------
    def set_context(self, doc_dir, stem: str):
        doc_dir = Path(doc_dir) if doc_dir else None
        if doc_dir != self._doc_dir and self._att is not None:
            self._att.preload_for_move(self._doc_dir)   # survive a Save As
        self._doc_dir = doc_dir
        self._stem = stem or "notebook"
        if self._project is None:
            self._reload_project()      # a sidecar path is resolvable now

    def materialize(self, claimed=None):
        """On save: write the project out to the sidecar folder."""
        if self._doc_dir is not None and self._att is not None:
            self._att.materialize(self._doc_dir, self._stem, claimed)

    # -- drops -------------------------------------------------------------
    def dropEvent(self, event):
        """Accept .kfit only.

        Handing anything else to the base cell would let the notebook
        convert this cell to whatever was dropped, silently destroying the
        project it holds — so a wrong file is refused and says so.
        """
        paths = [u.toLocalFile() for u in event.mimeData().urls()
                 if u.isLocalFile()]
        for path in paths:
            if path.lower().endswith(".kfit"):
                self.attach(path)
                event.acceptProposedAction()
                return
        if paths:
            self._hint.setText(
                f"A KFit cell holds KherveFitting projects only — "
                f"{Path(paths[0]).name} is not a .kfit. Drop it on the "
                f"notebook background instead.")
        event.ignore()

    # -- source / persistence ---------------------------------------------
    def source(self) -> str:
        doc = {"kbook_kfit": 1,
               "sheet": self._sheet_box.currentText(),
               "view": "data" if self._tabs.currentIndex() == 1 else "plot"}
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
        self._wanted_sheet = str(doc.get("sheet") or "")
        self._origin = str(doc.get("origin") or "")
        self._tabs.setCurrentIndex(1 if doc.get("view") == "data" else 0)
        self._reload_project()

    def focus_editor(self):
        self._card.setFocus()


CELL_CLASSES["kfit"] = KFitCell
