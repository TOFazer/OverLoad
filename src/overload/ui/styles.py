"""Thèmes clair / sombre pour OverLoad."""

from __future__ import annotations

DARK = """
QMainWindow, QWidget { background-color: #1e1e2e; color: #cdd6f4; }
QLineEdit, QComboBox, QSpinBox, QDateEdit {
    background-color: #313244; border: 1px solid #45475a; border-radius: 6px; padding: 6px 10px; color: #cdd6f4;
}
QLineEdit:focus, QComboBox:focus { border: 1px solid #89b4fa; }
QPushButton {
    background-color: #89b4fa; color: #1e1e2e; border: none; border-radius: 6px; padding: 8px 16px; font-weight: 600;
}
QPushButton:hover { background-color: #74c7ec; }
QPushButton:pressed { background-color: #6aa3e0; }
QPushButton#secondary { background-color: #313244; color: #cdd6f4; border: 1px solid #45475a; }
QPushButton#secondary:hover { background-color: #45475a; }
QListWidget, QTableWidget, QTreeWidget {
    background-color: #181825; border: 1px solid #313244; border-radius: 8px;
}
QHeaderView::section { background-color: #313244; padding: 6px; border: none; }
QScrollBar:vertical { background: #181825; width: 10px; }
QScrollBar::handle:vertical { background: #585b70; border-radius: 5px; min-height: 30px; }
QScrollBar::handle:vertical:hover { background: #6c7086; }
QLabel#muted { color: #a6adc8; }
QLabel#title { font-size: 16px; font-weight: 700; }
QFrame#card {
    background-color: #313244; border: 1px solid #45475a; border-radius: 10px;
}
QFrame#card:hover { border: 1px solid #89b4fa; }
"""

LIGHT = """
QMainWindow, QWidget { background-color: #eff1f5; color: #4c4f69; }
QLineEdit, QComboBox, QSpinBox, QDateEdit {
    background-color: #ffffff; border: 1px solid #ccd0da; border-radius: 6px; padding: 6px 10px; color: #4c4f69;
}
QLineEdit:focus, QComboBox:focus { border: 1px solid #1e66f5; }
QPushButton {
    background-color: #1e66f5; color: #ffffff; border: none; border-radius: 6px; padding: 8px 16px; font-weight: 600;
}
QPushButton:hover { background-color: #2a7fff; }
QPushButton:pressed { background-color: #1650c0; }
QPushButton#secondary { background-color: #ffffff; color: #4c4f69; border: 1px solid #ccd0da; }
QPushButton#secondary:hover { background-color: #e6e9ef; }
QListWidget, QTableWidget, QTreeWidget {
    background-color: #ffffff; border: 1px solid #ccd0da; border-radius: 8px;
}
QHeaderView::section { background-color: #e6e9ef; padding: 6px; border: none; }
QScrollBar:vertical { background: #eff1f5; width: 10px; }
QScrollBar::handle:vertical { background: #bcc0cc; border-radius: 5px; min-height: 30px; }
QScrollBar::handle:vertical:hover { background: #acb0be; }
QLabel#muted { color: #8c8fa1; }
QLabel#title { font-size: 16px; font-weight: 700; }
QFrame#card {
    background-color: #ffffff; border: 1px solid #ccd0da; border-radius: 10px;
}
QFrame#card:hover { border: 1px solid #1e66f5; }
"""


def apply_theme(app, theme: str = "system") -> None:
    if theme == "dark":
        app.setStyleSheet(DARK)
    elif theme == "light":
        app.setStyleSheet(LIGHT)
    else:
        # system : on laisse Qt décider, mais on applique léger thème clair par défaut
        # On pourrait détecter dark mode via palette, simplifié ici.
        app.setStyleSheet(LIGHT)
