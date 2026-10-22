"""Système de design d'OverLoad : palettes, typographie et feuilles de style Qt.

Depuis la v2.0, l'identité d'OverLoad est un vert-noir profond pensé pour un
usage prolongé : fond `#101713`, panneaux `#1A261F`, vert forêt `#315E43` pour
les actions principales et les éléments sélectionnés, vert sauge `#A9C7AE` pour
les détails lumineux. Les couleurs d'état (succès, avertissement, erreur,
information) restent distinctes de l'accent pour ne jamais confondre
« en cours », « terminé » et « problème ». C'est l'accent par défaut ; les
autres accents restent personnalisables sans changer le socle forestier des
fonds. Typographie Manrope / Inter si disponible, sinon Segoe UI Variable sur
Windows. Toutes les valeurs sont centralisées ici afin que les composants
dessinés à la main (barres de progression, vignettes, icônes) et les feuilles
de style QSS restent parfaitement cohérents.
"""

from __future__ import annotations

import re
import zlib
from dataclasses import dataclass
from pathlib import Path

DEFAULT_ACCENT = "forest"

# Identité OverLoad v2.0 : sombre, élégante, vert forêt naturel — aucun vert
# fluo. Ces quatre constantes sont LA référence de l'identité ; les autres
# teintes en sont dérivées (surfaces, bordures, états de survol).
FOREST_NIGHT = "#101713"  # fond principal — vert-noir profond
FOREST_PANEL = "#1A261F"  # panneaux — navigation, zones de contenu, menus
FOREST_BRAND = "#315E43"  # vert forêt — actions principales, sélection, boutons
FOREST_SAGE = "#A9C7AE"  # vert sauge — détails lumineux, accents graphiques
FOREST_CREAM = "#EAF1E8"  # crème naturel — texte principal (sombre)
FOREST_MOSS = "#4E7D60"  # dérivé plus clair du vert forêt (dégradés, illustration)

# Alias historiques (v1.3) conservés pour les imports existants.
FOREST_PINE = FOREST_NIGHT
FOREST_CHARCOAL = FOREST_PANEL


@dataclass(frozen=True)
class Accent:
    """Déclinaison d'une couleur d'accent pour les deux thèmes."""

    key: str
    label: str
    dark: str
    dark_hover: str
    dark_pressed: str
    light: str
    light_hover: str
    light_pressed: str
    ink: str = "#ffffff"

    def base(self, theme: str) -> str:
        return self.light if theme == "light" else self.dark

    def hover(self, theme: str) -> str:
        return self.light_hover if theme == "light" else self.dark_hover

    def pressed(self, theme: str) -> str:
        return self.light_pressed if theme == "light" else self.dark_pressed

    def rgb(self, theme: str) -> tuple[int, int, int]:
        value = self.base(theme).lstrip("#")
        return tuple(int(value[i : i + 2], 16) for i in (0, 2, 4))  # type: ignore[return-value]


ACCENTS: dict[str, Accent] = {
    "forest": Accent(
        key="forest",
        label="Vert forêt",
        # Le vert forêt #315E43 porte les surfaces d'action (boutons,
        # progression, sélection) ; le texte d'accent passe par le vert sauge
        # en thème sombre pour rester lisible (voir `accent_text`).
        dark=FOREST_BRAND,
        dark_hover="#3F7454",
        dark_pressed="#264A35",
        light=FOREST_BRAND,
        light_hover="#3F7454",
        light_pressed="#1F3D2B",
    ),
    "violet": Accent(
        key="violet",
        label="Violet",
        dark="#8B5CF6",
        dark_hover="#A78BFA",
        dark_pressed="#7C3AED",
        light="#7C3AED",
        light_hover="#8B5CF6",
        light_pressed="#6D28D9",
    ),
    "blue": Accent(
        key="blue",
        label="Bleu électrique",
        dark="#3B82F6",
        dark_hover="#60A5FA",
        dark_pressed="#2563EB",
        light="#2563EB",
        light_hover="#3B82F6",
        light_pressed="#1D4ED8",
    ),
    "cyan": Accent(
        key="cyan",
        label="Cyan",
        dark="#22D3EE",
        dark_hover="#67E8F9",
        dark_pressed="#06B6D4",
        light="#0891B2",
        light_hover="#06B6D4",
        light_pressed="#0E7490",
    ),
    "emerald": Accent(
        key="emerald",
        label="Émeraude",
        dark="#34D399",
        dark_hover="#6EE7B7",
        dark_pressed="#10B981",
        light="#059669",
        light_hover="#10B981",
        light_pressed="#047857",
    ),
    "amber": Accent(
        key="amber",
        label="Ambre",
        dark="#FBBF24",
        dark_hover="#FCD34D",
        dark_pressed="#F59E0B",
        light="#D97706",
        light_hover="#F59E0B",
        light_pressed="#B45309",
    ),
    "rose": Accent(
        key="rose",
        label="Rose",
        dark="#FB7185",
        dark_hover="#FDA4AF",
        dark_pressed="#F43F5E",
        light="#E11D48",
        light_hover="#F43F5E",
        light_pressed="#BE123C",
    ),
}

UI_SCALES: dict[str, float] = {"compact": 0.92, "normal": 1.0, "large": 1.12}
UI_SCALE_LABELS: dict[str, str] = {
    "compact": "Compact",
    "normal": "Normal",
    "large": "Grand",
}


@dataclass(frozen=True)
class Palette:
    """Jetons de couleur résolus pour un thème et un accent donnés."""

    theme: str
    accent_key: str
    canvas: str
    canvas_soft: str
    sidebar: str
    surface: str
    surface_alt: str
    surface_hover: str
    input: str
    input_focus: str
    border: str
    border_strong: str
    text: str
    text_secondary: str
    text_muted: str
    accent: str
    accent_hover: str
    accent_pressed: str
    accent_text: str
    accent_ink: str
    accent_soft: str
    accent_softer: str
    info: str
    info_soft: str
    success: str
    success_soft: str
    warning: str
    warning_soft: str
    danger: str
    danger_soft: str
    overlay: str

    @property
    def dark(self) -> bool:
        return self.theme != "light"

    def accent_rgb(self) -> tuple[int, int, int]:
        value = self.accent.lstrip("#")
        return tuple(int(value[i : i + 2], 16) for i in (0, 2, 4))  # type: ignore[return-value]


def _rgba(hex_color: str, alpha: float) -> str:
    value = hex_color.lstrip("#")
    r, g, b = (int(value[i : i + 2], 16) for i in (0, 2, 4))
    return f"rgba({r}, {g}, {b}, {alpha:.3f})"


def palette(theme: str = "dark", accent: str = DEFAULT_ACCENT) -> Palette:
    """Retourne les jetons de couleur du thème demandé."""
    theme = "light" if theme == "light" else "dark"
    accent_def = ACCENTS.get(accent, ACCENTS[DEFAULT_ACCENT])
    base = accent_def.base(theme)
    hover = accent_def.hover(theme)
    pressed = accent_def.pressed(theme)
    if theme == "light":
        # Clair « jour en forêt » : crème et sauge pâle, texte vert-noir.
        # Sur fond clair, le vert forêt sert aussi de texte d'accent.
        return Palette(
            theme=theme,
            accent_key=accent_def.key,
            canvas="#EEF3EB",
            canvas_soft="#E2EBDD",
            sidebar="#F6F9F3",
            surface="#FCFDF9",
            surface_alt="#EDF3E6",
            surface_hover="#DFEBD8",
            input="#FFFFFF",
            input_focus="#F2F8EE",
            border="#C9D8C0",
            border_strong="#9DB894",
            text=FOREST_NIGHT,
            text_secondary="#365341",
            text_muted="#5F7765",
            accent=base,
            accent_hover=hover,
            accent_pressed=pressed,
            accent_text=base,
            accent_ink=accent_def.ink,
            accent_soft=_rgba(base, 0.10),
            accent_softer=_rgba(base, 0.055),
            info="#2C6577",
            info_soft="rgba(44, 101, 119, 0.10)",
            success="#2F7D4A",
            success_soft="rgba(47, 125, 74, 0.10)",
            warning="#8F640E",
            warning_soft="rgba(143, 100, 14, 0.10)",
            danger="#AE3727",
            danger_soft="rgba(174, 55, 39, 0.09)",
            overlay="rgba(252, 253, 249, 0.92)",
        )
    # Sombre : fond vert-noir #101713, panneaux #1A261F, vert forêt #315E43 en
    # action, vert sauge #A9C7AE en détail et en texte d'accent, crème en
    # texte. États volontairement distincts : succès plus lumineux que la
    # sauge, ambre pour les avertissements, terracotta pour les erreurs,
    # bleu-gris pour l'information / pause.
    accent_text = FOREST_SAGE if accent_def.key == "forest" else base
    return Palette(
        theme=theme,
        accent_key=accent_def.key,
        canvas=FOREST_NIGHT,
        canvas_soft="#0B100D",
        sidebar="#0B100D",
        surface=FOREST_PANEL,
        surface_alt="#223129",
        surface_hover="#2C4034",
        input="#131C16",
        input_focus="#18271D",
        border="#2B3E32",
        border_strong="#46604F",
        text=FOREST_CREAM,
        text_secondary=FOREST_SAGE,
        text_muted="#7F9784",
        accent=base,
        accent_hover=hover,
        accent_pressed=pressed,
        accent_text=accent_text,
        accent_ink=accent_def.ink,
        accent_soft=_rgba(accent_text, 0.14),
        accent_softer=_rgba(accent_text, 0.07),
        info="#93BFD0",
        info_soft="rgba(147, 191, 208, 0.13)",
        success="#7FC98F",
        success_soft="rgba(127, 201, 143, 0.13)",
        warning="#E0B96B",
        warning_soft="rgba(224, 185, 107, 0.13)",
        danger="#E88E7B",
        danger_soft="rgba(232, 142, 123, 0.13)",
        overlay="rgba(11, 16, 13, 0.88)",
    )


_ASSET_CACHE: dict[tuple[str, str], dict[str, str]] = {}


def _asset_dir() -> Path:
    import tempfile

    folder = Path(tempfile.gettempdir()) / "overload-ui-assets"
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def _render_asset(name: str, size: int, paint) -> str:  # noqa: ANN001
    """Rend une image QSS en 2x pour rester nette sur les écrans HiDPI."""
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QPainter, QPixmap

    path = _asset_dir() / f"{name}.png"
    if path.is_file():
        return path.as_posix()
    size *= 2
    pix = QPixmap(size, size)
    pix.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pix)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    paint(painter, size)
    painter.end()
    pix.save(str(path), "PNG")
    return path.as_posix()


def _paint_chevron(painter, size: int, color: str, direction: str) -> None:  # noqa: ANN001
    from PySide6.QtCore import QPointF, Qt
    from PySide6.QtGui import QColor, QPen

    pen = QPen(QColor(color), max(1.4, size / 8.5))
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    painter.setPen(pen)
    margin = size * 0.24
    if direction == "down":
        points = [
            QPointF(margin, size * 0.36),
            QPointF(size / 2, size * 0.66),
            QPointF(size - margin, size * 0.36),
        ]
    else:
        points = [
            QPointF(margin, size * 0.64),
            QPointF(size / 2, size * 0.34),
            QPointF(size - margin, size * 0.64),
        ]
    painter.drawPolyline(points)


def _paint_indicator(painter, size: int, theme: Palette, checked: bool, kind: str) -> None:  # noqa: ANN001
    from PySide6.QtCore import QPointF, QRectF, Qt
    from PySide6.QtGui import QColor, QPen

    colors = palette(theme.theme, theme.accent_key)
    if kind == "check":
        painter.setPen(QPen(QColor(colors.accent if checked else colors.border_strong), 1.4))
        painter.setBrush(QColor(colors.accent if checked else colors.input))
        painter.drawRoundedRect(QRectF(1, 1, size - 2, size - 2), 4, 4)
        if checked:
            pen = QPen(QColor("#FFFFFF"), 1.9)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
            painter.setPen(pen)
            painter.drawPolyline(
                [
                    QPointF(size * 0.26, size * 0.52),
                    QPointF(size * 0.43, size * 0.69),
                    QPointF(size * 0.75, size * 0.32),
                ]
            )
        return
    center = QPointF(size / 2, size / 2)
    painter.setPen(QPen(QColor(colors.accent if checked else colors.border_strong), 1.4))
    painter.setBrush(QColor(colors.accent if checked else colors.input))
    painter.drawEllipse(center, size * 0.42, size * 0.42)
    if checked:
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor("#FFFFFF"))
        painter.drawEllipse(center, size * 0.19, size * 0.19)


def theme_assets(theme: str = "dark", accent: str = DEFAULT_ACCENT) -> dict[str, str]:
    """Génère (une seule fois par thème/accent) les images QSS des contrôles natifs."""
    key = (theme, accent)
    cached = _ASSET_CACHE.get(key)
    if cached is not None:
        return cached
    p = palette(theme, accent)
    signature = zlib.crc32(
        "|".join((p.canvas, p.surface, p.input, p.border_strong, p.text_muted, p.accent)).encode(
            "utf-8"
        )
    )
    suffix = f"{p.theme}-{p.accent_key}-{signature:08x}"
    assets = {
        "down": _render_asset(
            f"chevron-down-{suffix}",
            18,
            lambda painter, size: _paint_chevron(painter, size, p.text_muted, "down"),
        ),
        "up": _render_asset(
            f"chevron-up-{suffix}",
            18,
            lambda painter, size: _paint_chevron(painter, size, p.text_muted, "up"),
        ),
        "check_on": _render_asset(
            f"check-on-{suffix}",
            16,
            lambda painter, size: _paint_indicator(painter, size, p, True, "check"),
        ),
        "check_off": _render_asset(
            f"check-off-{suffix}",
            16,
            lambda painter, size: _paint_indicator(painter, size, p, False, "check"),
        ),
        "radio_on": _render_asset(
            f"radio-on-{suffix}",
            16,
            lambda painter, size: _paint_indicator(painter, size, p, True, "radio"),
        ),
        "radio_off": _render_asset(
            f"radio-off-{suffix}",
            16,
            lambda painter, size: _paint_indicator(painter, size, p, False, "radio"),
        ),
    }
    _ASSET_CACHE[key] = assets
    return assets


def scale_factor(ui_scale: str) -> float:
    return UI_SCALES.get(ui_scale, 1.0)


def font_family() -> str:
    # Signature OverX : Manrope / Inter si installées, sinon Segoe UI (Windows).
    return '"Manrope", "Inter", "Segoe UI Variable Text", "Segoe UI Variable", "Segoe UI", "Arial"'


def display_family() -> str:
    return (
        '"Manrope", "Inter", "Segoe UI Variable Display", "Segoe UI Variable", '
        '"Segoe UI", "Arial"'
    )


def build_stylesheet(
    theme: str = "dark",
    accent: str = DEFAULT_ACCENT,
    ui_scale: str = "normal",
) -> str:
    """Construit la feuille de style Qt complète de l'application."""
    p = palette(theme, accent)
    f = scale_factor(ui_scale)
    try:
        assets = theme_assets(p.theme, p.accent_key)
    except Exception:  # sans QGuiApplication, on garde les contrôles natifs par défaut
        assets = {}
    down_arrow = assets.get("down", "")
    up_arrow = assets.get("up", "")
    check_on = assets.get("check_on", "")
    check_off = assets.get("check_off", "")
    radio_on = assets.get("radio_on", "")
    radio_off = assets.get("radio_off", "")
    try:
        assets = theme_assets(p.theme, p.accent_key)
    except Exception:  # sans QGuiApplication, on garde les contrôles natifs par défaut
        assets = {}
    down_arrow = assets.get("down", "")
    up_arrow = assets.get("up", "")
    check_on = assets.get("check_on", "")
    check_off = assets.get("check_off", "")
    radio_on = assets.get("radio_on", "")
    radio_off = assets.get("radio_off", "")

    def s(value: float) -> int:
        return max(1, round(value * f))

    return f"""
    QWidget {{
        color: {p.text};
        font-family: {font_family()};
        font-size: {s(13)}px;
    }}
    QMainWindow, QWidget#rootWidget, QWidget#pageHost, QDialog {{
        background-color: {p.canvas};
    }}
    QFrame#sidebar {{
        background-color: {p.sidebar};
        border: none;
        border-right: 1px solid {p.border};
    }}
    QFrame#topBar {{
        background-color: {p.canvas};
        border: none;
        border-bottom: 1px solid {p.border};
    }}
    QFrame#panelCard {{
        background-color: {p.surface};
        border: 1px solid {p.border};
        border-radius: {s(16)}px;
    }}
    QFrame#settingCard {{
        background-color: {p.surface};
        border: 1px solid {p.border};
        border-radius: {s(16)}px;
    }}
    QFrame#taskCard, QFrame#historyCard {{
        background-color: {p.surface};
        border: 1px solid {p.border};
        border-radius: {s(15)}px;
    }}
    QFrame#taskCard:hover, QFrame#historyCard:hover {{
        background-color: {p.surface_alt};
        border: 1px solid {p.border_strong};
    }}
    QFrame#statCard {{
        background-color: {p.surface};
        border: 1px solid {p.border};
        border-radius: {s(14)}px;
    }}
    QFrame#innerCard {{
        background-color: {p.surface_alt};
        border: 1px solid {p.border};
        border-radius: {s(12)}px;
    }}
    QFrame#heroCard {{
        background-color: {p.surface};
        border: 1px solid {p.accent_soft};
        border-radius: {s(20)}px;
        background-image: qlineargradient(x1:0, y1:0, x2:1, y2:1,
            stop:0 {p.surface}, stop:0.55 {p.surface}, stop:1 {p.accent_softer});
    }}
    QFrame#promoCard {{
        background-color: {p.surface};
        border: 1px solid {p.accent_soft};
        border-radius: {s(16)}px;
        background-image: qlineargradient(x1:0, y1:1, x2:1, y2:0,
            stop:0 {p.surface}, stop:1 {p.accent_softer});
    }}
    QFrame#stepCard {{
        background-color: {p.surface_alt};
        border: 1px solid {p.border};
        border-radius: {s(13)}px;
    }}
    QPushButton#toolCard {{
        background-color: {p.surface};
        border: 1px solid {p.border};
        border-radius: {s(14)}px;
        padding: 0px;
        text-align: left;
    }}
    QPushButton#toolCard:hover {{
        background-color: {p.surface_alt};
        border: 1px solid {_rgba(p.accent_text, 0.6)};
    }}
    QPushButton#toolCard:pressed {{
        background-color: {p.accent_softer};
    }}
    QFrame#segmented {{
        background-color: {p.input};
        border: 1px solid {p.border};
        border-radius: {s(11)}px;
    }}
    QFrame#errorPanel {{
        background-color: {p.danger_soft};
        border: 1px solid {_rgba(p.danger, 0.35)};
        border-radius: {s(10)}px;
    }}
    QFrame#warningPanel {{
        background-color: {p.warning_soft};
        border: 1px solid {_rgba(p.warning, 0.32)};
        border-radius: {s(10)}px;
    }}
    QFrame#infoPanel {{
        background-color: {p.info_soft};
        border: 1px solid {_rgba(p.info, 0.28)};
        border-radius: {s(10)}px;
    }}
    QFrame#successPanel {{
        background-color: {p.success_soft};
        border: 1px solid {_rgba(p.success, 0.28)};
        border-radius: {s(10)}px;
    }}
    QFrame#toast {{
        background-color: {p.surface_alt};
        border: 1px solid {p.border_strong};
        border-radius: {s(12)}px;
    }}
    QFrame#divider {{
        background-color: {p.border};
        border: none;
        max-height: 1px;
    }}
    QLabel {{
        color: {p.text};
        background: transparent;
    }}
    QLabel#pageTitle {{
        font-family: {display_family()};
        font-size: {s(21)}px;
        font-weight: 700;
    }}
    QLabel#pageSubtitle {{
        color: {p.text_secondary};
        font-size: {s(12)}px;
    }}
    QLabel#heroTitle {{
        font-family: {display_family()};
        font-size: {s(26)}px;
        font-weight: 700;
    }}
    QLabel#heroSubtitle {{
        color: {p.text_secondary};
        font-size: {s(13)}px;
    }}
    QLabel#heroEyebrow {{
        color: {p.accent_text};
        font-size: {s(10)}px;
        font-weight: 700;
    }}
    QLabel#stepTitle {{
        font-size: {s(13)}px;
        font-weight: 700;
    }}
    QLabel#stepHint {{
        color: {p.text_secondary};
        font-size: {s(11)}px;
    }}
    QLabel#toolTitle {{
        font-size: {s(13)}px;
        font-weight: 700;
    }}
    QLabel#toolText {{
        color: {p.text_secondary};
        font-size: {s(11)}px;
    }}
    QLabel#toolMeta {{
        color: {p.text_muted};
        font-size: {s(10)}px;
        font-weight: 600;
    }}
    QLabel#helpQuestion {{
        font-size: {s(13)}px;
        font-weight: 700;
    }}
    QLabel#brandTitle {{
        font-family: {display_family()};
        font-size: {s(18)}px;
        font-weight: 700;
    }}
    QLabel#brandSubtitle {{
        color: {p.text_muted};
        font-size: {s(9)}px;
        font-weight: 700;
    }}
    QLabel#sectionTitle {{
        font-family: {display_family()};
        font-size: {s(15)}px;
        font-weight: 700;
    }}
    QLabel#cardTitle {{
        font-size: {s(14)}px;
        font-weight: 600;
    }}
    QLabel#mutedLabel {{
        color: {p.text_secondary};
        font-size: {s(12)}px;
    }}
    QLabel#tinyLabel {{
        color: {p.text_muted};
        font-size: {s(10)}px;
    }}
    QLabel#fieldLabel {{
        color: {p.text_secondary};
        font-size: {s(11)}px;
        font-weight: 600;
    }}
    QLabel#statValue {{
        font-family: {display_family()};
        font-size: {s(21)}px;
        font-weight: 700;
    }}
    QLabel#statCaption {{
        color: {p.text_muted};
        font-size: {s(9)}px;
        font-weight: 700;
    }}
    QLabel#statHint {{
        color: {p.text_secondary};
        font-size: {s(11)}px;
    }}
    QLabel#dangerText {{
        color: {p.danger};
        font-size: {s(12)}px;
        font-weight: 600;
    }}
    QLabel#successText {{
        color: {p.success};
        font-size: {s(12)}px;
        font-weight: 600;
    }}
    QLabel#infoText {{
        color: {p.info};
        font-size: {s(12)}px;
        font-weight: 600;
    }}
    QLabel#warningText {{
        color: {p.warning};
        font-size: {s(12)}px;
        font-weight: 600;
    }}
    QLabel#statePill {{
        border-radius: {s(8)}px;
        padding: {s(2)}px {s(9)}px;
        font-size: {s(10)}px;
        font-weight: 700;
    }}
    QLabel#statePill[state="running"] {{
        color: {p.accent_text};
        background-color: {p.accent_soft};
    }}
    QLabel#statePill[state="queued"] {{
        color: {p.text_secondary};
        background-color: {p.surface_alt};
    }}
    QLabel#statePill[state="paused"] {{
        color: {p.info};
        background-color: {p.info_soft};
    }}
    QLabel#statePill[state="completed"] {{
        color: {p.success};
        background-color: {p.success_soft};
    }}
    QLabel#statePill[state="failed"] {{
        color: {p.danger};
        background-color: {p.danger_soft};
    }}
    QLabel#statePill[state="warning"] {{
        color: {p.warning};
        background-color: {p.warning_soft};
    }}
    QLabel#statePill[state="neutral"] {{
        color: {p.text_secondary};
        background-color: {p.surface_alt};
    }}
    QLabel#formatChip {{
        color: {p.text_secondary};
        background-color: {p.surface_alt};
        border: 1px solid {p.border};
        border-radius: {s(6)}px;
        padding: {s(1)}px {s(6)}px;
        font-size: {s(9)}px;
        font-weight: 700;
    }}
    QLabel#navSectionLabel {{
        color: {p.text_muted};
        font-size: {s(9)}px;
        font-weight: 700;
        padding-left: {s(14)}px;
    }}
    QLabel#versionLabel {{
        color: {p.text_muted};
        font-size: {s(10)}px;
    }}
    QLabel#emptyTitle {{
        font-family: {display_family()};
        font-size: {s(15)}px;
        font-weight: 700;
    }}
    QLabel#emptyText {{
        color: {p.text_secondary};
        font-size: {s(12)}px;
    }}
    QLabel#monoLabel, QPlainTextEdit#analyzerOutput, QPlainTextEdit#creatorsTracksOutput {{
        font-family: "Cascadia Mono", "Consolas", "SFMono-Regular", monospace;
        font-size: {s(12)}px;
    }}
    QLineEdit, QPlainTextEdit, QTextEdit, QComboBox, QSpinBox, QDoubleSpinBox {{
        background-color: {p.input};
        color: {p.text};
        border: 1px solid {p.border};
        border-radius: {s(10)}px;
        padding: {s(6)}px {s(10)}px;
        selection-background-color: {p.accent};
        selection-color: {p.accent_ink};
    }}
    QLineEdit:hover, QPlainTextEdit:hover, QTextEdit:hover, QComboBox:hover, QSpinBox:hover {{
        border: 1px solid {p.border_strong};
    }}
    QLineEdit:focus, QPlainTextEdit:focus, QTextEdit:focus, QComboBox:focus, QSpinBox:focus,
    QDoubleSpinBox:focus {{
        border: 1px solid {p.accent_text};
        background-color: {p.input_focus};
    }}
    QLineEdit:disabled, QPlainTextEdit:disabled, QComboBox:disabled, QSpinBox:disabled {{
        color: {p.text_muted};
        background-color: {p.surface_alt};
    }}
    QLineEdit#searchField {{
        background-color: {p.input};
        border: 1px solid {p.border};
        border-radius: {s(18)}px;
        padding: {s(7)}px {s(14)}px;
        font-size: {s(12)}px;
    }}
    QLineEdit#searchField:focus {{
        border: 1px solid {p.accent_text};
        background-color: {p.input_focus};
    }}
    QLineEdit#urlField {{
        background-color: {p.input};
        border: 1px solid {p.border};
        border-radius: {s(13)}px;
        padding: {s(12)}px {s(14)}px;
        font-size: {s(13)}px;
    }}
    QLineEdit#urlField:focus {{
        border: 1px solid {p.accent_text};
        background-color: {p.input_focus};
    }}
    QLineEdit#urlField[invalid="true"] {{
        border: 1px solid {p.danger};
    }}
    QLineEdit#urlField[valid="true"] {{
        border: 1px solid {_rgba(p.success, 0.65)};
    }}
    QComboBox::drop-down {{
        subcontrol-origin: padding;
        subcontrol-position: center right;
        border: none;
        width: {s(26)}px;
    }}
    QComboBox::down-arrow {{
        image: url("{down_arrow}");
        width: {s(14)}px;
        height: {s(14)}px;
    }}
    QAbstractSpinBox::up-button {{
        subcontrol-origin: border;
        subcontrol-position: top right;
        width: {s(20)}px;
        border-left: 1px solid {p.border};
        border-top-right-radius: {s(10)}px;
        background: transparent;
    }}
    QAbstractSpinBox::down-button {{
        subcontrol-origin: border;
        subcontrol-position: bottom right;
        width: {s(20)}px;
        border-left: 1px solid {p.border};
        border-bottom-right-radius: {s(10)}px;
        background: transparent;
    }}
    QAbstractSpinBox::up-button:hover, QAbstractSpinBox::down-button:hover {{
        background-color: {p.surface_hover};
    }}
    QAbstractSpinBox::up-arrow {{
        image: url("{up_arrow}");
        width: {s(11)}px;
        height: {s(11)}px;
    }}
    QAbstractSpinBox::down-arrow {{
        image: url("{down_arrow}");
        width: {s(11)}px;
        height: {s(11)}px;
    }}
    QComboBox QAbstractItemView {{
        background-color: {p.surface_alt};
        color: {p.text};
        border: 1px solid {p.border};
        border-radius: {s(8)}px;
        padding: {s(4)}px;
        selection-background-color: {p.accent_soft};
        selection-color: {p.text};
        outline: 0;
    }}
    QPushButton {{
        background-color: {p.surface_alt};
        color: {p.text};
        border: 1px solid {p.border};
        border-radius: {s(10)}px;
        padding: {s(6)}px {s(13)}px;
        font-weight: 600;
    }}
    QPushButton:hover {{
        background-color: {p.surface_hover};
        border: 1px solid {p.border_strong};
    }}
    QPushButton:pressed {{
        background-color: {p.surface};
    }}
    QPushButton:disabled {{
        color: {p.text_muted};
        background-color: {p.surface_alt};
        border: 1px solid {p.border};
    }}
    QPushButton#primaryBtn {{
        background-color: {p.accent};
        color: {p.accent_ink};
        border: 1px solid {p.accent};
        font-weight: 700;
    }}
    QPushButton#primaryBtn:hover {{
        background-color: {p.accent_hover};
        border: 1px solid {p.accent_hover};
    }}
    QPushButton#primaryBtn:pressed {{
        background-color: {p.accent_pressed};
        border: 1px solid {p.accent_pressed};
    }}
    QPushButton#secondaryBtn {{
        background-color: {p.accent_soft};
        color: {p.accent_text};
        border: 1px solid transparent;
        font-weight: 700;
    }}
    QPushButton#secondaryBtn:hover {{
        border: 1px solid {_rgba(p.accent_text, 0.55)};
        background-color: {p.accent_softer};
    }}
    QPushButton#dangerBtn {{
        background-color: {p.danger_soft};
        color: {p.danger};
        border: 1px solid transparent;
        font-weight: 600;
    }}
    QPushButton#dangerBtn:hover {{
        border: 1px solid {_rgba(p.danger, 0.5)};
    }}
    QPushButton#ghostBtn {{
        background-color: transparent;
        border: 1px solid transparent;
        color: {p.text_secondary};
        font-weight: 600;
    }}
    QPushButton#ghostBtn:hover {{
        background-color: {p.surface_hover};
        color: {p.text};
    }}
    QPushButton#linkBtn {{
        background-color: transparent;
        border: none;
        color: {p.accent_text};
        padding: 0px;
        font-weight: 600;
        text-align: left;
    }}
    QPushButton#linkBtn:hover {{
        color: {p.text};
    }}
    QPushButton#iconBtn, QPushButton#iconBtnDanger {{
        background-color: transparent;
        border: none;
        border-radius: {s(9)}px;
        padding: 0px;
    }}
    QPushButton#iconBtn:hover {{
        background-color: {p.surface_hover};
    }}
    QPushButton#iconBtn:pressed {{
        background-color: {p.border};
    }}
    QPushButton#iconBtnDanger:hover {{
        background-color: {p.danger_soft};
    }}
    QPushButton#iconBtnDanger:pressed {{
        background-color: {_rgba(p.danger, 0.22)};
    }}
    QPushButton#segment {{
        background-color: transparent;
        border: none;
        border-radius: {s(8)}px;
        padding: {s(5)}px {s(11)}px;
        color: {p.text_secondary};
        font-weight: 600;
        font-size: {s(12)}px;
    }}
    QPushButton#segment:hover {{
        color: {p.text};
        background-color: {p.surface_hover};
    }}
    QPushButton#segment:checked {{
        background-color: {p.surface};
        color: {p.text};
        border: 1px solid {p.border};
    }}
    QPushButton#segment:checked:hover {{
        background-color: {p.surface};
    }}
    QPushButton#chip {{
        background-color: {p.input};
        border: 1px solid {p.border};
        border-radius: {s(14)}px;
        padding: {s(4)}px {s(10)}px;
        color: {p.text_secondary};
        font-size: {s(11)}px;
        font-weight: 600;
    }}
    QPushButton#chip:hover {{
        border-color: {p.border_strong};
        color: {p.text};
    }}
    QPushButton#chip:checked {{
        background-color: {p.accent_soft};
        border-color: {_rgba(p.accent_text, 0.55)};
        color: {p.accent_text};
    }}
    QPushButton#accentSwatch {{
        background: transparent;
        border: none;
        padding: 0px;
    }}
    QTabWidget::pane {{
        border: 1px solid {p.border};
        border-radius: {s(14)}px;
        background-color: {p.surface};
        top: -1px;
    }}
    QTabWidget#creatorsTabs::pane {{
        background-color: {p.surface};
    }}
    QTabBar::tab {{
        background-color: transparent;
        color: {p.text_secondary};
        padding: {s(7)}px {s(12)}px;
        margin: 0px {s(3)}px 0px 0px;
        border-radius: {s(8)}px;
        font-weight: 600;
        font-size: {s(12)}px;
    }}
    QTabBar::tab:hover {{
        color: {p.text};
        background-color: {p.surface_hover};
    }}
    QTabBar::tab:selected {{
        color: {p.accent_text};
        background-color: {p.accent_soft};
    }}
    QScrollArea {{
        border: none;
        background: transparent;
    }}
    QScrollArea > QWidget > QWidget {{
        background: transparent;
    }}
    QScrollBar:vertical {{
        background: transparent;
        width: {s(10)}px;
        margin: {s(2)}px;
    }}
    QScrollBar::handle:vertical {{
        background-color: {p.border_strong};
        border-radius: {s(4)}px;
        min-height: {s(30)}px;
    }}
    QScrollBar::handle:vertical:hover {{
        background-color: {p.text_muted};
    }}
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
        height: 0px;
        background: transparent;
    }}
    QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
        background: transparent;
    }}
    QScrollBar:horizontal {{
        background: transparent;
        height: {s(10)}px;
        margin: {s(2)}px;
    }}
    QScrollBar::handle:horizontal {{
        background-color: {p.border_strong};
        border-radius: {s(4)}px;
        min-width: {s(30)}px;
    }}
    QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
        width: 0px;
        background: transparent;
    }}
    QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {{
        background: transparent;
    }}
    QCheckBox, QRadioButton {{
        color: {p.text};
        spacing: {s(8)}px;
        background: transparent;
    }}
    QCheckBox::indicator {{
        image: url("{check_off}");
        width: {s(16)}px;
        height: {s(16)}px;
    }}
    QCheckBox::indicator:checked {{
        image: url("{check_on}");
    }}
    QRadioButton::indicator {{
        image: url("{radio_off}");
        width: {s(16)}px;
        height: {s(16)}px;
    }}
    QRadioButton::indicator:checked {{
        image: url("{radio_on}");
    }}
    QProgressBar {{
        background-color: {p.input};
        border: 1px solid {p.border};
        border-radius: {s(5)}px;
        height: {s(10)}px;
        text-align: center;
        color: {p.text};
    }}
    QProgressBar::chunk {{
        background-color: {p.accent};
        border-radius: {s(4)}px;
    }}
    QSplitter::handle {{
        background: transparent;
        width: {s(8)}px;
        height: {s(8)}px;
    }}
    QTableWidget, QTreeWidget, QListWidget {{
        background-color: {p.surface};
        alternate-background-color: {p.surface_alt};
        color: {p.text};
        border: 1px solid {p.border};
        border-radius: {s(10)}px;
        gridline-color: {p.border};
        selection-background-color: {p.accent_soft};
        selection-color: {p.text};
        outline: 0;
    }}
    QHeaderView::section {{
        background-color: {p.surface_alt};
        color: {p.text_secondary};
        border: none;
        border-bottom: 1px solid {p.border};
        padding: {s(6)}px {s(8)}px;
        font-weight: 600;
        font-size: {s(11)}px;
    }}
    QTableCornerButton::section {{
        background-color: {p.surface_alt};
        border: none;
    }}
    QMenu {{
        background-color: {p.surface_alt};
        color: {p.text};
        border: 1px solid {p.border};
        border-radius: {s(9)}px;
        padding: {s(5)}px;
    }}
    QMenu::item {{
        padding: {s(6)}px {s(14)}px;
        border-radius: {s(6)}px;
    }}
    QMenu::item:selected {{
        background-color: {p.accent_soft};
        color: {p.text};
    }}
    QToolTip {{
        background-color: {p.surface_alt};
        color: {p.text};
        border: 1px solid {p.border_strong};
        padding: {s(5)}px {s(8)}px;
        font-size: {s(11)}px;
    }}
    QMessageBox {{
        background-color: {p.canvas};
    }}
    QMessageBox QLabel {{
        color: {p.text};
    }}
    QDialogButtonBox QPushButton {{
        min-width: {s(84)}px;
    }}
    """


def _qcolor(hex_color: str):
    from PySide6.QtGui import QColor

    return QColor(hex_color)


def qcolor(value: str):
    """Convertit une couleur QSS (hex ou `rgba(r, g, b, a)`) en QColor valide."""
    from PySide6.QtGui import QColor

    text = value.strip()
    pattern = (
        r"rgba?\(\s*([\d.]+)\s*,\s*([\d.]+)\s*,\s*([\d.]+)"
        r"\s*(?:,\s*([\d.]+)\s*)?\)"
    )
    match = re.fullmatch(pattern, text)
    if match:
        r, g, b = (int(float(match.group(i))) for i in (1, 2, 3))
        alpha_raw = match.group(4)
        alpha = 255 if alpha_raw is None else round(float(alpha_raw) * 255)
        return QColor(r, g, b, max(0, min(255, alpha)))
    return QColor(text)


def apply_appearance(
    app, theme: str = "dark", accent: str = DEFAULT_ACCENT, ui_scale: str = "normal"
):
    """Applique palette, police et feuille de style à toute l'application."""
    from PySide6.QtGui import QFont, QPalette

    p = palette(theme, accent)
    f = scale_factor(ui_scale)

    app.setStyle("Fusion")

    font = QFont()
    font.setFamilies(
        ["Manrope", "Inter", "Segoe UI Variable Text", "Segoe UI Variable", "Segoe UI", "Arial"]
    )
    font.setPixelSize(max(10, round(13 * f)))
    app.setFont(font)

    qt_palette = QPalette()
    qt_palette.setColor(QPalette.ColorRole.Window, _qcolor(p.canvas))
    qt_palette.setColor(QPalette.ColorRole.WindowText, _qcolor(p.text))
    qt_palette.setColor(QPalette.ColorRole.Base, _qcolor(p.input))
    qt_palette.setColor(QPalette.ColorRole.AlternateBase, _qcolor(p.surface_alt))
    qt_palette.setColor(QPalette.ColorRole.ToolTipBase, _qcolor(p.surface_alt))
    qt_palette.setColor(QPalette.ColorRole.ToolTipText, _qcolor(p.text))
    qt_palette.setColor(QPalette.ColorRole.Text, _qcolor(p.text))
    qt_palette.setColor(QPalette.ColorRole.Button, _qcolor(p.surface_alt))
    qt_palette.setColor(QPalette.ColorRole.ButtonText, _qcolor(p.text))
    qt_palette.setColor(QPalette.ColorRole.BrightText, _qcolor(p.danger))
    qt_palette.setColor(QPalette.ColorRole.Link, _qcolor(p.accent_text))
    qt_palette.setColor(QPalette.ColorRole.Highlight, _qcolor(p.accent))
    qt_palette.setColor(QPalette.ColorRole.HighlightedText, _qcolor(p.accent_ink))
    qt_palette.setColor(QPalette.ColorRole.PlaceholderText, _qcolor(p.text_muted))
    qt_palette.setColor(QPalette.ColorRole.Mid, _qcolor(p.border))
    qt_palette.setColor(QPalette.ColorRole.Dark, _qcolor(p.border_strong))
    qt_palette.setColor(QPalette.ColorRole.Light, _qcolor(p.surface))
    app.setPalette(qt_palette)
    app.setStyleSheet(build_stylesheet(theme, accent, ui_scale))
    return p
