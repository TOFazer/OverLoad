"""Feuilles de style Qt (QSS) sombre et claire pour l'application native OverLoad."""

from __future__ import annotations


def build_stylesheet(theme: str = "dark") -> str:
    dark = theme != "light"
    bg_canvas = "#0b0f16" if dark else "#f1f5f9"
    bg_surface = "#131924" if dark else "#ffffff"
    bg_elevated = "#1a2231" if dark else "#f8fafc"
    bg_input = "#0e141e" if dark else "#ffffff"
    border = "#263244" if dark else "#cbd5e1"
    text_main = "#f1f5f9" if dark else "#0f172a"
    text_sub = "#94a3b8" if dark else "#475569"
    accent = "#f59e0b" if dark else "#d97706"
    accent_hover = "#fbbf24" if dark else "#b45309"
    accent_ink = "#0f172a" if dark else "#ffffff"

    return f"""
    QMainWindow, QWidget#rootWidget {{
        background-color: {bg_canvas};
        color: {text_main};
        font-family: "Segoe UI Variable", "Segoe UI", sans-serif;
        font-size: 13px;
    }}
    QFrame#panelCard {{
        background-color: {bg_surface};
        border: 1px solid {border};
        border-radius: 11px;
    }}
    QFrame#itemCard {{
        background-color: {bg_elevated};
        border: 1px solid {border};
        border-radius: 9px;
    }}
    QFrame#metricBox {{
        background-color: {bg_elevated};
        border: 1px solid {border};
        border-radius: 9px;
    }}
    QLabel {{
        color: {text_main};
        background: transparent;
    }}
    QLabel#mutedLabel {{
        color: {text_sub};
        font-size: 12px;
    }}
    QLabel#titleLabel {{
        font-size: 17px;
        font-weight: 700;
    }}
    QLabel#sectionTitle {{
        font-size: 14px;
        font-weight: 700;
    }}
    QLabel#metricValue {{
        font-size: 15px;
        font-weight: 700;
    }}
    QLabel#issueBanner {{
        background-color: rgba(245, 158, 11, 0.16);
        border: 1px solid {accent};
        border-radius: 6px;
        padding: 5px 9px;
        font-size: 12px;
    }}
    QLabel#errorBanner {{
        background-color: rgba(239, 68, 68, 0.16);
        border: 1px solid #ef4444;
        border-radius: 6px;
        padding: 5px 9px;
        font-size: 12px;
    }}
    QLineEdit, QPlainTextEdit, QComboBox, QSpinBox {{
        background-color: {bg_input};
        color: {text_main};
        border: 1px solid {border};
        border-radius: 7px;
        padding: 6px 10px;
        selection-background-color: {accent};
        selection-color: {accent_ink};
    }}
    QLineEdit:focus, QPlainTextEdit:focus, QComboBox:focus, QSpinBox:focus {{
        border: 1px solid {accent};
    }}
    QPushButton {{
        background-color: {bg_elevated};
        color: {text_main};
        border: 1px solid {border};
        border-radius: 7px;
        padding: 6px 12px;
        font-weight: 600;
    }}
    QPushButton:hover {{
        border: 1px solid {accent};
    }}
    QPushButton#primaryBtn {{
        background-color: {accent};
        color: {accent_ink};
        border: 1px solid {accent};
        font-weight: 700;
    }}
    QPushButton#primaryBtn:hover {{
        background-color: {accent_hover};
    }}
    QPushButton:checked {{
        background-color: {accent};
        color: {accent_ink};
        border: 1px solid {accent};
    }}
    QTabWidget::pane {{
        border: 1px solid {border};
        border-radius: 8px;
        background-color: {bg_surface};
    }}
    QTabBar::tab {{
        background-color: {bg_elevated};
        color: {text_sub};
        padding: 7px 14px;
        margin-right: 4px;
        border-top-left-radius: 7px;
        border-top-right-radius: 7px;
        font-weight: 600;
    }}
    QTabBar::tab:selected {{
        background-color: {accent};
        color: {accent_ink};
    }}
    QScrollArea {{
        border: none;
        background: transparent;
    }}
    QProgressBar {{
        background-color: {bg_input};
        border: 1px solid {border};
        border-radius: 5px;
        height: 10px;
        text-align: center;
    }}
    QProgressBar::chunk {{
        background-color: {accent};
        border-radius: 4px;
    }}
    """
