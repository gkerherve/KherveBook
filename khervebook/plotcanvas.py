"""An embedded, interactive matplotlib figure — Qt canvas + the standard
navigation toolbar (zoom, pan, home, save), like Jupyter's widget mode.

Used by code cells when "Interactive plots" is on; otherwise figures
render as static PNGs.

Copyright (C) 2026 Gwilherm Kerherve

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.
"""

from PyQt5.QtWidgets import QVBoxLayout, QWidget


class PlotCanvas(QWidget):
    """A live matplotlib *fig* with a zoom/pan/save toolbar above it."""

    def __init__(self, fig, parent=None):
        super().__init__(parent)
        from matplotlib.backends.backend_qt5agg import (
            FigureCanvasQTAgg, NavigationToolbar2QT)
        self.figure = fig
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self.canvas = FigureCanvasQTAgg(fig)
        self.toolbar = NavigationToolbar2QT(self.canvas, self)
        layout.addWidget(self.toolbar)
        layout.addWidget(self.canvas)
        # Size the canvas to the figure's natural pixel size.
        w, h = fig.get_size_inches() * fig.dpi
        self.canvas.setMinimumHeight(int(h))
        self.canvas.draw_idle()

    def close_figure(self):
        """Release the matplotlib figure when the cell drops this plot."""
        try:
            import matplotlib.pyplot as plt
            plt.close(self.figure)
        except Exception:
            pass


def make_plot_widget(fig, parent=None) -> "PlotCanvas":
    return PlotCanvas(fig, parent)
