"""Thèmes clair et sombre, avec suivi du thème Windows."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication

ACCENT = QColor("#2f6fed")  # bleu lisible sur fond clair et sombre


def _light_palette() -> QPalette:
    p = QPalette()
    p.setColor(QPalette.ColorRole.Window, QColor("#f5f6f8"))
    p.setColor(QPalette.ColorRole.WindowText, QColor("#1b1f24"))
    p.setColor(QPalette.ColorRole.Base, QColor("#ffffff"))
    p.setColor(QPalette.ColorRole.AlternateBase, QColor("#eef1f5"))
    p.setColor(QPalette.ColorRole.Text, QColor("#1b1f24"))
    p.setColor(QPalette.ColorRole.Button, QColor("#e6e9ef"))
    p.setColor(QPalette.ColorRole.ButtonText, QColor("#1b1f24"))
    p.setColor(QPalette.ColorRole.Highlight, ACCENT)
    p.setColor(QPalette.ColorRole.HighlightedText, QColor("#ffffff"))
    p.setColor(QPalette.ColorRole.ToolTipBase, QColor("#ffffff"))
    p.setColor(QPalette.ColorRole.ToolTipText, QColor("#1b1f24"))
    p.setColor(QPalette.ColorRole.PlaceholderText, QColor("#5a6270"))
    p.setColor(QPalette.ColorRole.Link, ACCENT)
    return p


def _dark_palette() -> QPalette:
    p = QPalette()
    p.setColor(QPalette.ColorRole.Window, QColor("#1c1f24"))
    p.setColor(QPalette.ColorRole.WindowText, QColor("#eef1f5"))
    p.setColor(QPalette.ColorRole.Base, QColor("#14161a"))
    p.setColor(QPalette.ColorRole.AlternateBase, QColor("#20242b"))
    p.setColor(QPalette.ColorRole.Text, QColor("#eef1f5"))
    p.setColor(QPalette.ColorRole.Button, QColor("#2a2f38"))
    p.setColor(QPalette.ColorRole.ButtonText, QColor("#eef1f5"))
    p.setColor(QPalette.ColorRole.Highlight, ACCENT)
    p.setColor(QPalette.ColorRole.HighlightedText, QColor("#ffffff"))
    p.setColor(QPalette.ColorRole.ToolTipBase, QColor("#2a2f38"))
    p.setColor(QPalette.ColorRole.ToolTipText, QColor("#eef1f5"))
    p.setColor(QPalette.ColorRole.PlaceholderText, QColor("#9aa3af"))
    p.setColor(QPalette.ColorRole.Link, QColor("#7aa7ff"))
    return p


def system_prefers_dark(app: QApplication) -> bool:
    try:
        return app.styleHints().colorScheme() == Qt.ColorScheme.Dark
    except AttributeError:  # Qt ancien : pas de détection, on reste clair
        return False


def apply_theme(app: QApplication, theme: str) -> None:
    """theme : 'system', 'light' ou 'dark'. Fusion garantit le même rendu partout."""
    app.setStyle("Fusion")
    dark = theme == "dark" or (theme == "system" and system_prefers_dark(app))
    app.setPalette(_dark_palette() if dark else _light_palette())
    app.setStyleSheet(
        """
        QPushButton { padding: 6px 14px; min-height: 22px; border-radius: 6px; }
        QPushButton:default { font-weight: 600; }
        QLineEdit, QSpinBox, QComboBox { padding: 5px 8px; min-height: 22px; }
        QListWidget#nav { padding: 8px 0; border: none; }
        QListWidget#nav::item { padding: 0 16px; border-radius: 6px; }
        QListWidget#nav::item:selected { background: #2f6fed; color: #ffffff; }
        QListWidget#nav::item:hover:!selected { background: rgba(127, 127, 127, 0.15); }
        QLabel#title { font-size: 20pt; font-weight: 600; }
        """
    )
