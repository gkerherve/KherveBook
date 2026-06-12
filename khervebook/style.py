"""Application-wide look and feel.

Flat, light, modern theme in the KherveFitting-Qt family style:
light grey chrome, white rounded cell cards, a Jupyter-style blue
bar on the selected cell, and the Kherve teal as accent colour.

Copyright (C) 2026 Gwilherm Kerherve

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.
"""

from PyQt5.QtGui import QColor, QPalette

#: Kherve family accent (KherveFitting teal) and selection blue.
ACCENT = "#50bea0"
SELECT_BLUE = "#2176c7"

STYLESHEET = f"""
QMainWindow, QDialog {{ background: #f4f5f7; }}

QMenuBar {{ background: #fafbfc; border-bottom: 1px solid #e1e4e8; }}
QMenuBar::item {{ padding: 5px 10px; background: transparent; }}
QMenuBar::item:selected {{ background: #e3eef9; border-radius: 4px; }}
QMenu {{ background: #ffffff; border: 1px solid #d0d4d8; padding: 4px; }}
QMenu::item {{ padding: 5px 24px 5px 12px; border-radius: 4px; }}
QMenu::item:selected {{ background: #e3eef9; }}

QToolBar {{
    background: #fafbfc;
    border: none;
    border-bottom: 1px solid #e1e4e8;
    padding: 3px 6px;
    spacing: 2px;
}}
QToolButton {{
    border: none;
    border-radius: 6px;
    padding: 4px;
    margin: 1px;
}}
QToolButton:hover {{ background: #e3eef9; }}
QToolButton:pressed {{ background: #cfe3f6; }}
QToolButton::menu-indicator {{ image: none; }}

QComboBox {{
    background: #ffffff;
    border: 1px solid #d0d4d8;
    border-radius: 6px;
    padding: 4px 10px;
    min-width: 90px;
}}
QComboBox:hover {{ border-color: {SELECT_BLUE}; }}
QComboBox::drop-down {{ border: none; width: 18px; }}

QScrollArea {{ border: none; background: #f4f5f7; }}
QScrollBar:vertical {{
    background: transparent; width: 11px; margin: 2px;
}}
QScrollBar::handle:vertical {{
    background: #c4c9ce; border-radius: 4px; min-height: 30px;
}}
QScrollBar::handle:vertical:hover {{ background: #9aa1a8; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0;
}}
QScrollBar:horizontal {{
    background: transparent; height: 11px; margin: 2px;
}}
QScrollBar::handle:horizontal {{
    background: #c4c9ce; border-radius: 4px; min-width: 30px;
}}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
    width: 0;
}}

/* Cell cards */
QFrame#cell {{
    background: #ffffff;
    border: 1px solid #e1e4e8;
    border-radius: 8px;
}}
QFrame#cell[current="true"] {{
    border: 1px solid {SELECT_BLUE};
    border-left: 5px solid {SELECT_BLUE};
}}
QFrame#cell QPlainTextEdit {{
    background: #f8f9fa;
    border: 1px solid #eceff1;
    border-radius: 5px;
    padding: 4px;
}}
QFrame#cell QPlainTextEdit:focus {{ border-color: #b9d4ef; }}

QStatusBar {{ background: #fafbfc; border-top: 1px solid #e1e4e8; }}

QDockWidget {{ titlebar-close-icon: none; }}
QDockWidget::title {{
    background: #fafbfc; padding: 6px;
    border-bottom: 1px solid #e1e4e8;
}}
QTreeView {{
    background: #fafbfc; border: none;
    alternate-background-color: #f4f5f7;
}}
QTreeView::item {{ padding: 3px; }}
QTreeView::item:selected {{
    background: #e3eef9; color: #1a1a1a; border-radius: 4px;
}}

QTableWidget {{ background: #ffffff; gridline-color: #e1e4e8; }}
QHeaderView::section {{
    background: #f0f2f4; color: #444444;
    border: none; border-right: 1px solid #e1e4e8;
    border-bottom: 1px solid #e1e4e8; padding: 3px 6px;
}}
"""


def light_palette() -> QPalette:
    """Light palette overriding any OS dark theme."""
    p = QPalette()
    p.setColor(QPalette.Window, QColor(244, 245, 247))
    p.setColor(QPalette.WindowText, QColor(26, 26, 26))
    p.setColor(QPalette.Base, QColor(255, 255, 255))
    p.setColor(QPalette.AlternateBase, QColor(245, 245, 245))
    p.setColor(QPalette.Text, QColor(26, 26, 26))
    p.setColor(QPalette.Button, QColor(244, 245, 247))
    p.setColor(QPalette.ButtonText, QColor(26, 26, 26))
    p.setColor(QPalette.ToolTipBase, QColor(255, 255, 220))
    p.setColor(QPalette.ToolTipText, QColor(0, 0, 0))
    p.setColor(QPalette.Highlight, QColor(33, 118, 199))
    p.setColor(QPalette.HighlightedText, QColor(255, 255, 255))
    p.setColor(QPalette.PlaceholderText, QColor(120, 120, 120))
    return p


def apply_style(app):
    """Apply the KherveBook theme to the QApplication."""
    app.setPalette(light_palette())
    app.setStyleSheet(STYLESHEET)
