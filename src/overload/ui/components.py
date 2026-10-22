"""Composants visuels réutilisables de l'interface native OverLoad.

Tous les composants dessinés à la main (barres de progression, vignettes,
boutons de navigation, badges) partagent les jetons de `overload.ui.theme` et
exposent `refresh_theme()` pour se mettre à jour instantanément lorsque
l'utilisateur change de thème, d'accent ou de taille d'interface.
"""

from __future__ import annotations

import hashlib
import subprocess
from collections import deque
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlsplit

from PySide6.QtCore import (
    Property,
    QEasingCurve,
    QObject,
    QPointF,
    QPropertyAnimation,
    QRectF,
    QRunnable,
    QSize,
    Qt,
    QThreadPool,
    QTimer,
    Signal,
)
from PySide6.QtGui import (
    QColor,
    QFont,
    QFontMetrics,
    QImage,
    QImageReader,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
    QRadialGradient,
)
from PySide6.QtWidgets import (
    QAbstractButton,
    QFrame,
    QGraphicsOpacityEffect,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from overload.core.formatting import format_bytes, format_duration, format_speed
from overload.core.paths import default_data_dir
from overload.downloads.models import TaskSnapshot
from overload.downloads.state import TaskState
from overload.history.store import HistoryEntry
from overload.library.scan import LibraryFile
from overload.ui import icons
from overload.ui.failure_text import FailureInfo, explain_failure
from overload.ui.theme import Palette, qcolor

VIDEO_EXT = {"mp4", "mkv", "mov", "webm", "avi", "m4v", "wmv", "flv", "mpg", "mpeg", "ts"}
IMAGE_EXT = {"jpg", "jpeg", "png", "webp", "gif", "bmp", "avif", "heic", "tif", "tiff"}
AUDIO_EXT = {"mp3", "wav", "flac", "aac", "ogg", "oga", "m4a", "opus", "wma", "aiff"}


def extension_of(filename: str) -> str:
    return Path(filename).suffix.lstrip(".").lower()


def kind_of(filename: str) -> str:
    ext = extension_of(filename)
    if ext in VIDEO_EXT:
        return "video"
    if ext in IMAGE_EXT:
        return "image"
    if ext in AUDIO_EXT:
        return "audio"
    if ext in {"zip", "rar", "7z", "tar", "gz", "iso"}:
        return "archive"
    return "file"


def host_of(url: str) -> str:
    try:
        host = urlsplit(url).netloc
    except ValueError:
        return ""
    return host[4:] if host.startswith("www.") else host


def human_time_ago(iso: str) -> str:
    try:
        moment = datetime.fromisoformat(iso)
    except (TypeError, ValueError):
        return ""
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=UTC)
    now = datetime.now(UTC)
    delta = max(0, int((now - moment).total_seconds()))
    if delta < 60:
        return "à l'instant"
    if delta < 3600:
        return f"il y a {delta // 60} min"
    if delta < 86400:
        return f"il y a {delta // 3600} h"
    if delta < 172800:
        return "hier"
    return moment.strftime("%d/%m/%Y")


def state_presentation(snap: TaskSnapshot) -> tuple[str, str]:
    """Libellé + clé de couleur d'une tâche."""
    if snap.retrying:
        label = f"Nouvelle tentative {snap.retry_count}/{snap.max_retries}"
        return label, "warning"
    if snap.stalled:
        return "Connexion lente", "warning"
    mapping = {
        TaskState.RUNNING: ("En cours", "running"),
        TaskState.QUEUED: ("En attente", "queued"),
        TaskState.PAUSED: ("En pause", "paused"),
        TaskState.FINALIZING: ("Vérification", "warning"),
        TaskState.COMPLETED: ("Terminé", "completed"),
        TaskState.FAILED: ("Interrompu", "failed"),
        TaskState.CANCELLED: ("Annulé", "neutral"),
    }
    return mapping.get(snap.state, (str(snap.state.value), "neutral"))


def history_presentation(entry: HistoryEntry) -> tuple[str, str]:
    mapping = {
        "completed": ("Terminé", "completed"),
        "failed": ("Interrompu", "failed"),
        "cancelled": ("Annulé", "neutral"),
    }
    return mapping.get(entry.status, (entry.status, "neutral"))


class GlyphBadge(QWidget):
    """Petit médaillon arrondi contenant une icône teintée."""

    def __init__(
        self,
        icon_name: str,
        palette: Palette,
        *,
        size: int = 36,
        color: str | None = None,
        background: str | None = None,
        radius: float | None = None,
        icon_size: int = 18,
    ) -> None:
        super().__init__()
        self._icon_name = icon_name
        self._palette = palette
        self._color = color or palette.accent_text
        self._background = background or palette.accent_soft
        self._radius = radius if radius is not None else size * 0.3
        self._icon_size = icon_size
        self.setFixedSize(size, size)

    def refresh_theme(
        self, palette: Palette, color: str | None = None, background: str | None = None
    ) -> None:
        self._palette = palette
        if color:
            self._color = color
        if background:
            self._background = background
        self.update()

    def set_icon(self, icon_name: str) -> None:
        self._icon_name = icon_name
        self.update()

    def paintEvent(self, _event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(qcolor(self._background))
        painter.drawRoundedRect(QRectF(self.rect()), self._radius, self._radius)
        pix = icons.pixmap(self._icon_name, self._color, self._icon_size)
        target = QRectF(
            (self.width() - self._icon_size) / 2,
            (self.height() - self._icon_size) / 2,
            self._icon_size,
            self._icon_size,
        )
        painter.drawPixmap(target.toRect(), pix)
        painter.end()


class LogoBadge(QWidget):
    """Logo OverLoad : éclair crème sur dégradé accent → teinte profonde."""

    def __init__(self, palette: Palette, size: int = 40) -> None:
        super().__init__()
        self._palette = palette
        self._size = size
        self.setFixedSize(size, size)

    def refresh_theme(self, palette: Palette) -> None:
        self._palette = palette
        self.update()

    def paintEvent(self, _event) -> None:  # noqa: N802
        p = self._palette
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = QRectF(0.5, 0.5, self.width() - 1, self.height() - 1)
        glow = QRadialGradient(rect.center(), rect.width() * 0.72)
        glow.setColorAt(0.0, QColor(*p.accent_rgb(), 90))
        glow.setColorAt(1.0, QColor(*p.accent_rgb(), 0))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(glow)
        painter.drawEllipse(rect.adjusted(-4, -4, 4, 4))
        grad = QLinearGradient(rect.topLeft(), rect.bottomRight())
        grad.setColorAt(0.0, qcolor(p.accent))
        # Forêt : dégradé mousse → sapin ; autres accents : accent → accent pressé.
        grad.setColorAt(1.0, qcolor(p.accent_pressed))
        painter.setBrush(grad)
        radius = rect.width() * 0.3
        painter.drawRoundedRect(rect, radius, radius)
        pix = icons.pixmap("zap", "#EAF1E8", int(self._size * 0.52))
        offset = (self._size - int(self._size * 0.52)) / 2
        painter.drawPixmap(int(offset), int(offset), pix)
        painter.end()


class ElidedLabel(QLabel):
    """QLabel qui abrège proprement son texte au lieu de casser la mise en page."""

    def __init__(self, text: str = "") -> None:
        super().__init__("")
        self._full_text = text
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.setMinimumWidth(40)
        self.setText(text)

    def setText(self, text: str) -> None:  # noqa: N802
        self._full_text = text
        self.setToolTip(text if len(text) > 42 else "")
        self._apply_elide()

    def text(self) -> str:  # noqa: D102
        return self._full_text

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._apply_elide()

    def _apply_elide(self) -> None:
        metrics = QFontMetrics(self.font())
        available = max(20, self.width() - 2)
        super().setText(
            metrics.elidedText(self._full_text, Qt.TextElideMode.ElideMiddle, available)
        )


class NavButton(QAbstractButton):
    """Élément de navigation de la barre latérale, dessiné à la main."""

    def __init__(
        self, key: str, label: str, icon_name: str, palette: Palette, *, scale: float = 1.0
    ) -> None:
        super().__init__()
        self.key = key
        self.label = label
        self.icon_name = icon_name
        self._palette = palette
        self._scale = scale
        self._compact = False
        self._hovered = False
        self._badge = 0
        self.setCheckable(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setAttribute(Qt.WidgetAttribute.WA_Hover, True)
        self.setFixedHeight(round(42 * scale))
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setToolTip(label)
        self._update_font()

    def _update_font(self) -> None:
        font = QFont(self.font())
        font.setPixelSize(max(10, round(13 * self._scale)))
        font.setWeight(QFont.Weight.DemiBold)
        self.setFont(font)

    def sizeHint(self) -> QSize:  # noqa: N802
        return QSize(round(200 * self._scale), round(42 * self._scale))

    def set_badge(self, count: int) -> None:
        """Pastille compteur affichée à droite du libellé (0 = masquée)."""
        count = max(0, int(count))
        if count != self._badge:
            self._badge = count
            self.update()

    def set_compact(self, compact: bool) -> None:
        self._compact = compact
        self.setToolTip(self.label)
        self.update()

    def refresh_theme(self, palette: Palette) -> None:
        self._palette = palette
        self.update()

    def enterEvent(self, event) -> None:  # noqa: N802
        self._hovered = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:  # noqa: N802
        self._hovered = False
        self.update()
        super().leaveEvent(event)

    def paintEvent(self, _event) -> None:  # noqa: N802
        p = self._palette
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        radius = round(10 * self._scale)
        if self.isChecked():
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(qcolor(p.accent_soft))
            painter.drawRoundedRect(rect, radius, radius)
        elif self._hovered:
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(qcolor(p.surface_hover))
            painter.drawRoundedRect(rect, radius, radius)

        if self.isChecked():
            color = p.accent_text
        elif self._hovered:
            color = p.text
        else:
            color = p.text_secondary
        if self.isChecked():
            bar = QRectF(0, rect.center().y() - 9, 3, 18)
            painter.setBrush(qcolor(p.accent))
            painter.drawRoundedRect(bar, 1.5, 1.5)

        icon_size = round(19 * self._scale)
        if self._compact:
            icon_x = (self.width() - icon_size) / 2
            painter.drawPixmap(
                QPointF(icon_x, (self.height() - icon_size) / 2).toPoint(),
                icons.pixmap(self.icon_name, color, icon_size),
            )
        else:
            icon_x = round(15 * self._scale)
            painter.drawPixmap(
                QPointF(icon_x, (self.height() - icon_size) / 2).toPoint(),
                icons.pixmap(self.icon_name, color, icon_size),
            )
            painter.setPen(QColor(color))
            painter.setFont(self.font())
            text_rect = QRectF(
                icon_x + icon_size + round(11 * self._scale),
                0,
                self.width() - icon_x - icon_size - 18,
                self.height(),
            )
            painter.drawText(
                text_rect, Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, self.label
            )
        if self._badge:
            badge_text = str(self._badge) if self._badge < 100 else "99+"
            metrics = QFontMetrics(self.font())
            text_w = metrics.horizontalAdvance(badge_text)
            pill_w = text_w + round(12 * self._scale)
            pill_h = round(18 * self._scale)
            if self._compact:
                pill = QRectF(
                    self.width() / 2 + round(3 * self._scale),
                    rect.center().y() - pill_h - round(3 * self._scale),
                    pill_w,
                    pill_h,
                )
            else:
                pill = QRectF(
                    self.width() - pill_w - round(10 * self._scale),
                    rect.center().y() - pill_h / 2,
                    pill_w,
                    pill_h,
                )
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(qcolor(p.accent))
            painter.drawRoundedRect(pill, pill_h / 2, pill_h / 2)
            painter.setPen(QColor(p.accent_ink))
            badge_font = QFont(self.font())
            badge_font.setPixelSize(max(9, round(10 * self._scale)))
            badge_font.setWeight(QFont.Weight.Bold)
            painter.setFont(badge_font)
            painter.drawText(pill, Qt.AlignmentFlag.AlignCenter, badge_text)
        painter.end()


class IconButton(QPushButton):
    """Bouton icône compact et cohérent (actions de carte, barre supérieure)."""

    def __init__(
        self,
        icon_name: str,
        tooltip: str,
        palette: Palette,
        *,
        size: int = 34,
        icon_size: int = 18,
        danger: bool = False,
    ) -> None:
        super().__init__()
        self._icon_name = icon_name
        self._palette = palette
        self._icon_size = icon_size
        self._danger = danger
        self.setObjectName("iconBtnDanger" if danger else "iconBtn")
        self.setFixedSize(size, size)
        self.setIconSize(QSize(icon_size, icon_size))
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip(tooltip)
        self.refresh_theme(palette)

    def set_icon_name(self, name: str) -> None:
        self._icon_name = name
        self.refresh_theme(self._palette)

    def refresh_theme(self, palette: Palette) -> None:
        self._palette = palette
        color = palette.danger if self._danger else palette.text_secondary
        self.setIcon(icons.icon(self._icon_name, color, self._icon_size))

    def enterEvent(self, event) -> None:  # noqa: N802
        color = self._palette.danger if self._danger else self._palette.text
        self.setIcon(icons.icon(self._icon_name, color, self._icon_size))
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:  # noqa: N802
        color = self._palette.danger if self._danger else self._palette.text_secondary
        self.setIcon(icons.icon(self._icon_name, color, self._icon_size))
        super().leaveEvent(event)


class SegmentedControl(QFrame):
    """Sélecteur segmenté (filtres, thème, taille d'interface)."""

    value_changed = Signal(str)

    def __init__(self, items: list[tuple[str, str]], palette: Palette) -> None:
        super().__init__()
        self.setObjectName("segmented")
        self._buttons: dict[str, QPushButton] = {}
        self._palette = palette
        layout = QHBoxLayout(self)
        layout.setContentsMargins(3, 3, 3, 3)
        layout.setSpacing(2)
        for key, label in items:
            btn = QPushButton(label)
            btn.setObjectName("segment")
            btn.setCheckable(True)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.clicked.connect(lambda _checked=False, k=key: self._select(k, emit=True))
            layout.addWidget(btn)
            self._buttons[key] = btn
        if items:
            self._buttons[items[0][0]].setChecked(True)

    def _select(self, key: str, *, emit: bool) -> None:
        for k, btn in self._buttons.items():
            btn.blockSignals(True)
            btn.setChecked(k == key)
            btn.blockSignals(False)
        if emit:
            self.value_changed.emit(key)

    def set_value(self, key: str, *, emit: bool = False) -> None:
        if key in self._buttons:
            self._select(key, emit=emit)

    def value(self) -> str:
        for key, btn in self._buttons.items():
            if btn.isChecked():
                return key
        return ""

    def set_label(self, key: str, label: str) -> None:
        if key in self._buttons:
            self._buttons[key].setText(label)

    def refresh_theme(self, palette: Palette) -> None:
        self._palette = palette


class StatCard(QFrame):
    """Carte de statistique de l'accueil."""

    def __init__(
        self,
        caption: str,
        value: str,
        hint: str,
        icon_name: str,
        palette: Palette,
        *,
        tone: str = "accent",
    ) -> None:
        super().__init__()
        self.setObjectName("statCard")
        self._palette = palette
        self._tone = tone
        colors = {
            "accent": (palette.accent_text, palette.accent_soft),
            "info": (palette.info, palette.info_soft),
            "success": (palette.success, palette.success_soft),
            "warning": (palette.warning, palette.warning_soft),
        }
        fg, bg = colors.get(tone, colors["accent"])
        self.badge = GlyphBadge(icon_name, palette, size=34, color=fg, background=bg)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(6)
        top = QHBoxLayout()
        top.setSpacing(8)
        caption_label = QLabel(caption.upper())
        caption_label.setObjectName("statCaption")
        top.addWidget(self.badge)
        top.addWidget(caption_label)
        top.addStretch()
        layout.addLayout(top)
        self.value_label = QLabel(value)
        self.value_label.setObjectName("statValue")
        layout.addWidget(self.value_label)
        self.hint_label = QLabel(hint)
        self.hint_label.setObjectName("statHint")
        self.hint_label.setWordWrap(True)
        layout.addWidget(self.hint_label)

    def set_value(self, value: str, hint: str | None = None) -> None:
        self.value_label.setText(value)
        if hint is not None:
            self.hint_label.setText(hint)

    def refresh_theme(self, palette: Palette) -> None:
        self._palette = palette
        colors = {
            "accent": (palette.accent_text, palette.accent_soft),
            "info": (palette.info, palette.info_soft),
            "success": (palette.success, palette.success_soft),
            "warning": (palette.warning, palette.warning_soft),
        }
        fg, bg = colors.get(self._tone, colors["accent"])
        self.badge.refresh_theme(palette, fg, bg)


class ProgressBar(QWidget):
    """Barre de progression animée, arrondie, avec état et mode indéterminé."""

    def __init__(self, palette: Palette, *, compact: bool = False, scale: float = 1.0) -> None:
        super().__init__()
        self._palette = palette
        self._compact = compact
        self._scale = scale
        self._progress = 0.0
        self._state = "queued"
        self._indeterminate = False
        self._phase = 0.0
        self.setFixedHeight(max(5, round((5 if compact else 9) * scale)))
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._anim = QPropertyAnimation(self, b"progress", self)
        self._anim.setDuration(360)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._timer = QTimer(self)
        self._timer.setInterval(33)
        self._timer.timeout.connect(self._tick)

    def get_progress(self) -> float:
        return self._progress

    def set_progress_value(self, value: float) -> None:
        self._progress = max(0.0, min(100.0, float(value)))
        self.update()

    progress = Property(float, get_progress, set_progress_value)

    def set_palette_tokens(self, palette: Palette) -> None:
        self._palette = palette
        self.update()

    def set_state(self, state: str) -> None:
        self._state = state
        self._sync_timer()
        self.update()

    def set_indeterminate(self, enabled: bool) -> None:
        self._indeterminate = enabled
        self._sync_timer()
        self.update()

    def set_value_animated(self, value: float | None) -> None:
        if value is None:
            self.set_indeterminate(True)
            return
        self.set_indeterminate(False)
        target = max(0.0, min(100.0, float(value)))
        if abs(target - self._progress) < 0.2:
            self.set_progress_value(target)
            return
        self._anim.stop()
        self._anim.setStartValue(self._progress)
        self._anim.setEndValue(target)
        self._anim.start()

    def _sync_timer(self) -> None:
        needs = self._indeterminate or self._state == "running"
        if needs and not self._timer.isActive():
            self._timer.start()
        elif not needs and self._timer.isActive():
            self._timer.stop()

    def _tick(self) -> None:
        self._phase = (self._phase + 0.035) % 1.0
        self.update()

    def _chunk_colors(self) -> tuple[QColor, QColor]:
        p = self._palette
        if self._state == "completed":
            return qcolor(p.success), qcolor(p.success)
        if self._state == "paused":
            return qcolor(p.info), qcolor(p.info)
        if self._state == "failed":
            return qcolor(p.danger), qcolor(p.danger)
        if self._state == "warning":
            return qcolor(p.warning), qcolor(p.accent)
        return qcolor(p.accent), qcolor(p.accent_hover)

    def paintEvent(self, _event) -> None:  # noqa: N802
        p = self._palette
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = QRectF(0, 0, self.width(), self.height())
        radius = self.height() / 2
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(qcolor(p.input))
        painter.drawRoundedRect(rect, radius, radius)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QPen(qcolor(p.border), 1))
        painter.drawRoundedRect(rect.adjusted(0.5, 0.5, -0.5, -0.5), radius, radius)

        if self._indeterminate:
            painter.setPen(Qt.PenStyle.NoPen)
            width = max(40.0, self.width() * 0.26)
            travel = self.width() * 1.3
            x = (self._phase * travel) - width
            grad = QLinearGradient(x, 0, x + width, 0)
            c1, c2 = self._chunk_colors()
            grad.setColorAt(0.0, QColor(c1.red(), c1.green(), c1.blue(), 40))
            grad.setColorAt(0.5, QColor(c2.red(), c2.green(), c2.blue(), 220))
            grad.setColorAt(1.0, QColor(c1.red(), c1.green(), c1.blue(), 40))
            painter.setBrush(grad)
            painter.drawRoundedRect(QRectF(x, 0, width, self.height()), radius, radius)
            painter.end()
            return

        if self._progress > 0:
            chunk_w = max(self.height(), (self.width()) * self._progress / 100.0)
            chunk = QRectF(0, 0, min(self.width(), chunk_w), self.height())
            c1, c2 = self._chunk_colors()
            grad = QLinearGradient(chunk.topLeft(), chunk.topRight())
            grad.setColorAt(0.0, c1)
            grad.setColorAt(1.0, c2)
            painter.setBrush(grad)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawRoundedRect(chunk, radius, radius)
            if self._state == "running" and chunk.width() > 24:
                shine_w = max(18.0, chunk.width() * 0.22)
                x = (self._phase * (chunk.width() + shine_w * 2)) - shine_w
                shine = QLinearGradient(x, 0, x + shine_w, 0)
                shine.setColorAt(0.0, QColor(255, 255, 255, 0))
                shine.setColorAt(0.5, QColor(255, 255, 255, 52))
                shine.setColorAt(1.0, QColor(255, 255, 255, 0))
                painter.setBrush(shine)
                painter.save()
                clip = QPainterPath()
                clip.addRoundedRect(chunk, radius, radius)
                painter.setClipPath(clip)
                painter.drawRect(QRectF(x, 0, shine_w, self.height()))
                painter.restore()
        painter.end()


class Sparkline(QWidget):
    """Courbe de débit temps réel."""

    def __init__(self, palette: Palette, *, width: int = 104, height: int = 32) -> None:
        super().__init__()
        self._palette = palette
        self.samples: deque[float] = deque([0.0] * 36, maxlen=36)
        self.setFixedSize(width, height)
        self._phase = 0.0

    def push(self, bps: float) -> None:
        self.samples.append(max(0.0, float(bps)))
        self.update()

    def refresh_theme(self, palette: Palette) -> None:
        self._palette = palette
        self.update()

    def paintEvent(self, _event) -> None:  # noqa: N802
        p = self._palette
        if self.width() < 8 or self.height() < 8:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        w = float(self.width())
        h = float(self.height())
        peak = max(max(self.samples), 1024.0)
        pts = [
            QPointF(
                (i / max(1, len(self.samples) - 1)) * w,
                h - 2.0 - (min(v, peak) / peak) * (h - 5.0),
            )
            for i, v in enumerate(self.samples)
        ]
        line = QPainterPath(pts[0])
        for point in pts[1:]:
            line.lineTo(point)
        area = QPainterPath(line)
        area.lineTo(w, h)
        area.lineTo(0, h)
        area.closeSubpath()
        grad = QLinearGradient(0, 0, 0, h)
        grad.setColorAt(0.0, qcolor(p.accent_hover))
        grad.setColorAt(1.0, qcolor(p.accent))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(qcolor(p.accent))
        painter.setOpacity(0.10)
        painter.drawPath(area)
        painter.setOpacity(1.0)
        pen = QPen(qcolor(p.accent_text), 1.8)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawPath(line)
        painter.end()


class Thumbnail(QWidget):
    """Miniature de fichier avec repli visuel par type (vidéo, audio, image…)."""

    def __init__(self, palette: Palette, *, width: int = 78, height: int = 56) -> None:
        super().__init__()
        self._palette = palette
        self._pixmap: QPixmap | None = None
        self._path: str | None = None
        self._filename = ""
        self._kind = "file"
        self._requested = False
        self.setFixedSize(width, height)

    def refresh_theme(self, palette: Palette) -> None:
        self._palette = palette
        self.update()

    def set_source(self, filename: str, path: str | Path | None = None) -> None:
        new_path = str(path) if path else None
        if filename == self._filename and new_path == self._path:
            return
        self._filename = filename
        self._kind = kind_of(filename)
        self._path = new_path
        self._pixmap = None
        self._requested = False

    def mark_requested(self) -> bool:
        if self._requested:
            return False
        self._requested = True
        return True

    def set_pixmap(self, pixmap: QPixmap) -> None:
        self._pixmap = pixmap
        self.update()

    def _gradient_colors(self) -> tuple[QColor, QColor]:
        p = self._palette
        mapping = {
            "video": ("#6D28D9", "#2563EB"),
            "image": ("#0F766E", "#0891B2"),
            "audio": ("#BE185D", "#D97706"),
            "archive": ("#475569", "#7C3AED"),
        }
        if self._kind in mapping:
            a, b = mapping[self._kind]
        else:
            a, b = p.accent, p.info
        return QColor(a), QColor(b)

    def paintEvent(self, _event) -> None:  # noqa: N802
        from PySide6.QtGui import QBrush

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = QRectF(self.rect())
        radius = 10.0
        clip = QPainterPath()
        clip.addRoundedRect(rect, radius, radius)
        painter.setClipPath(clip)
        if self._pixmap is not None and not self._pixmap.isNull():
            dpr = self.devicePixelRatio()
            scaled = self._pixmap.scaled(
                QSize(int(self.width() * dpr), int(self.height() * dpr)),
                Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                Qt.TransformationMode.SmoothTransformation,
            )
            scaled.setDevicePixelRatio(self.devicePixelRatio())
            painter.drawPixmap(rect.toRect(), scaled)
            overlay = QLinearGradient(0, self.height() * 0.45, 0, self.height())
            overlay.setColorAt(0.0, QColor(0, 0, 0, 0))
            overlay.setColorAt(1.0, QColor(0, 0, 0, 150))
            painter.setBrush(overlay)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawRect(rect)
        else:
            start, end = self._gradient_colors()
            grad = QLinearGradient(rect.topLeft(), rect.bottomRight())
            grad.setColorAt(0.0, start)
            grad.setColorAt(1.0, end)
            painter.setBrush(grad)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawRect(rect)
            painter.setBrush(QColor(255, 255, 255, 26))
            painter.drawEllipse(
                QRectF(
                    -self.width() * 0.25,
                    -self.height() * 0.6,
                    self.width() * 1.1,
                    self.height() * 1.2,
                )
            )
            glyph = {"video": "film", "image": "image", "audio": "music", "archive": "file"}.get(
                self._kind, "file"
            )
            size = int(min(self.width(), self.height()) * 0.36)
            pix = icons.pixmap(glyph, "#FFFFFF", size, 1.6)
            painter.setOpacity(0.88)
            painter.drawPixmap(
                int((self.width() - size) / 2), int((self.height() - size) / 2 - 1), pix
            )
            painter.setOpacity(1.0)

        ext = extension_of(self._filename)
        if ext:
            font = QFont(self.font())
            font.setPixelSize(9)
            font.setWeight(QFont.Weight.Bold)
            painter.setFont(font)
            text = ext.upper()[:5]
            metrics = QFontMetrics(font)
            tw = metrics.horizontalAdvance(text) + 8
            badge = QRectF(5, self.height() - 17, tw, 12)
            painter.setBrush(QColor(0, 0, 0, 130))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawRoundedRect(badge, 4, 4)
            painter.setPen(QColor(255, 255, 255, 220))
            painter.drawText(badge, Qt.AlignmentFlag.AlignCenter, text)

        if self._kind == "video":
            painter.setBrush(QColor(0, 0, 0, 120))
            painter.drawEllipse(QPointF(self.width() - 15, self.height() - 15), 9, 9)
            painter.setBrush(QColor(255, 255, 255, 230))
            pts = [
                QPointF(self.width() - 17.5, self.height() - 19.5),
                QPointF(self.width() - 10.5, self.height() - 15),
                QPointF(self.width() - 17.5, self.height() - 10.5),
            ]
            painter.drawPolygon(pts)
        painter.setClipping(False)
        painter.setBrush(QBrush(Qt.BrushStyle.NoBrush))
        painter.setPen(QPen(QColor(255, 255, 255, 26), 1))
        painter.drawRoundedRect(rect.adjusted(0.5, 0.5, -0.5, -0.5), radius, radius)
        painter.end()


class _ThumbSignals(QObject):
    ready = Signal(str, QImage)


class _ThumbJob(QRunnable):
    def __init__(self, path: str, cache_path: Path, signals: _ThumbSignals) -> None:
        super().__init__()
        self.path = path
        self.cache_path = cache_path
        self.signals = signals

    def run(self) -> None:
        image = QImage()
        try:
            source = Path(self.path)
            kind = kind_of(source.name)
            if kind == "image":
                reader = QImageReader(str(source))
                reader.setAutoTransform(True)
                size = reader.size()
                if size.isValid() and size.width() > 480:
                    reader.setScaledSize(
                        QSize(480, max(1, int(size.height() * 480 / size.width())))
                    )
                image = reader.read()
            elif kind == "video":
                image = self._video_frame(source)
        except Exception:
            image = QImage()
        self.signals.ready.emit(self.path, image)

    def _video_frame(self, source: Path) -> QImage:
        from overload.media.analyzer import tool_path

        if self.cache_path.is_file():
            cached = QImage(str(self.cache_path))
            if not cached.isNull():
                return cached
        try:
            ffmpeg = tool_path("ffmpeg")
        except RuntimeError:
            return QImage()
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        for seek in ("1", "0"):
            args = [
                ffmpeg,
                "-v",
                "error",
                "-y",
                "-ss",
                seek,
                "-i",
                str(source),
                "-frames:v",
                "1",
                "-vf",
                "scale=480:-2",
                str(self.cache_path),
            ]
            try:
                subprocess.run(
                    args,
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    timeout=12,
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                    check=False,
                )
            except (OSError, subprocess.SubprocessError):
                return QImage()
            if self.cache_path.is_file():
                image = QImage(str(self.cache_path))
                if not image.isNull():
                    return image
        return QImage()


class ThumbnailService(QObject):
    """Extrait les miniatures hors du thread graphique (images + vidéos FFmpeg)."""

    def __init__(self, data_dir: Path | None, parent: QObject | None = None) -> None:
        super().__init__(parent)
        base = Path(data_dir) if data_dir is not None else default_data_dir()
        self._cache_dir = base / "thumbnails"
        self._images: dict[str, QImage] = {}
        self._callbacks: dict[str, list] = {}
        self._pending: set[str] = set()
        self._signals = _ThumbSignals()
        self._signals.ready.connect(self._on_ready)
        self._pool = QThreadPool.globalInstance()

    def cached(self, path: str) -> QImage | None:
        return self._images.get(path)

    def request(self, path: str | Path, callback) -> None:
        key = str(path)
        cached = self._images.get(key)
        if cached is not None:
            if not cached.isNull():
                try:
                    callback(QPixmap.fromImage(cached))
                except RuntimeError:
                    pass
            return
        self._callbacks.setdefault(key, []).append(callback)
        if key in self._pending:
            return
        try:
            stat = Path(key).stat()
        except OSError:
            return
        digest = hashlib.sha1(f"{key}:{stat.st_mtime_ns}:{stat.st_size}".encode()).hexdigest()  # noqa: S324
        self._cache_dir.mkdir(parents=True, exist_ok=True)
        self._pending.add(key)
        self._pool.start(_ThumbJob(key, self._cache_dir / f"{digest}.jpg", self._signals))

    def _on_ready(self, path: str, image: QImage) -> None:
        self._pending.discard(path)
        if len(self._images) > 160:
            self._images.clear()
        self._images[path] = image
        callbacks = self._callbacks.pop(path, [])
        if image.isNull():
            return
        pixmap = QPixmap.fromImage(image)
        for callback in callbacks:
            try:
                callback(pixmap)
            except RuntimeError:
                continue


class FailurePanel(QFrame):
    """Encart d'erreur explicite avec action recommandée."""

    def __init__(self, palette: Palette, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("errorPanel")
        self._palette = palette
        self._info: FailureInfo | None = None
        layout = QHBoxLayout(self)
        layout.setContentsMargins(11, 9, 11, 9)
        layout.setSpacing(9)
        self.icon = GlyphBadge(
            "alert", palette, size=28, color=palette.danger, background="transparent", icon_size=17
        )
        layout.addWidget(self.icon, 0, Qt.AlignmentFlag.AlignTop)
        text_col = QVBoxLayout()
        text_col.setSpacing(2)
        header = QHBoxLayout()
        self.title = QLabel()
        self.title.setObjectName("dangerText")
        header.addWidget(self.title)
        header.addStretch()
        self.help_btn = QPushButton("Que faire ?")
        self.help_btn.setObjectName("linkBtn")
        self.help_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.help_btn.clicked.connect(self._show_details)
        header.addWidget(self.help_btn)
        text_col.addLayout(header)
        self.detail = QLabel()
        self.detail.setObjectName("mutedLabel")
        self.detail.setWordWrap(True)
        text_col.addWidget(self.detail)
        layout.addLayout(text_col, 1)

    def set_failure(self, info: FailureInfo) -> None:
        self._info = info
        self.title.setText(info.title)
        self.detail.setText(info.detail)
        self.setToolTip(info.dialog_text())

    def _show_details(self) -> None:
        if self._info is None:
            return
        box = QMessageBox(self.window())
        box.setWindowTitle("Comprendre le problème")
        box.setIcon(QMessageBox.Icon.Warning)
        box.setTextFormat(Qt.TextFormat.PlainText)
        box.setText(self._info.dialog_text())
        box.exec()


class DownloadCard(QFrame):
    """Carte détaillée d'une tâche : miniature, état, progression et actions."""

    def __init__(
        self,
        task_id: str,
        manager,
        palette: Palette,
        thumbnails: ThumbnailService,
        *,
        scale: float = 1.0,
        on_error=None,
    ) -> None:
        super().__init__()
        self.task_id = task_id
        self._manager = manager
        self._palette = palette
        self._thumbnails = thumbnails
        self._on_error = on_error
        self._snap: TaskSnapshot | None = None
        self.setObjectName("taskCard")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(
            round(15 * scale), round(13 * scale), round(15 * scale), round(13 * scale)
        )
        layout.setSpacing(round(9 * scale))

        top = QHBoxLayout()
        top.setSpacing(round(12 * scale))
        self.thumb = Thumbnail(palette, width=round(78 * scale), height=round(56 * scale))
        top.addWidget(self.thumb, 0, Qt.AlignmentFlag.AlignTop)

        info = QVBoxLayout()
        info.setSpacing(4)
        title_row = QHBoxLayout()
        title_row.setSpacing(8)
        self.name = ElidedLabel()
        self.name.setObjectName("cardTitle")
        title_row.addWidget(self.name, 1)
        self.pill = QLabel()
        self.pill.setObjectName("statePill")
        title_row.addWidget(self.pill, 0, Qt.AlignmentFlag.AlignVCenter)
        info.addLayout(title_row)
        self.meta = ElidedLabel()
        self.meta.setObjectName("mutedLabel")
        info.addWidget(self.meta)
        self.chip = QLabel()
        self.chip.setObjectName("formatChip")
        chip_row = QHBoxLayout()
        chip_row.setSpacing(6)
        chip_row.addWidget(self.chip, 0)
        self.resume = QLabel("Reprise")
        self.resume.setObjectName("infoText")
        self.resume.hide()
        chip_row.addWidget(self.resume, 0)
        chip_row.addStretch()
        info.addLayout(chip_row)
        top.addLayout(info, 1)

        actions = QHBoxLayout()
        actions.setSpacing(2)
        self.pause_btn = IconButton("pause", "Mettre en pause", palette)
        self.resume_btn = IconButton("play", "Reprendre", palette)
        self.retry_btn = IconButton("refresh", "Relancer le téléchargement", palette)
        self.cancel_btn = IconButton(
            "x", "Annuler et supprimer le fichier partiel", palette, danger=True
        )
        self.open_file_btn = IconButton(
            "play", "Ouvrir le fichier (application par défaut)", palette
        )
        self.open_btn = IconButton("folder", "Afficher dans le dossier", palette)
        self.remove_btn = IconButton("trash", "Retirer de la liste", palette)
        for btn in (
            self.pause_btn,
            self.resume_btn,
            self.retry_btn,
            self.cancel_btn,
            self.open_file_btn,
            self.open_btn,
            self.remove_btn,
        ):
            actions.addWidget(btn)
        top.addLayout(actions)
        layout.addLayout(top)

        progress_row = QHBoxLayout()
        progress_row.setSpacing(10)
        self.bar = ProgressBar(palette, scale=scale)
        progress_row.addWidget(self.bar, 1)
        self.percent = QLabel("—")
        self.percent.setObjectName("cardTitle")
        self.percent.setFixedWidth(round(52 * scale))
        self.percent.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        progress_row.addWidget(self.percent)
        layout.addLayout(progress_row)

        metrics = QHBoxLayout()
        metrics.setSpacing(16)
        self.size_lbl = QLabel()
        self.size_lbl.setObjectName("mutedLabel")
        self.speed_lbl = QLabel()
        self.speed_lbl.setObjectName("mutedLabel")
        self.eta_lbl = QLabel()
        self.eta_lbl.setObjectName("mutedLabel")
        metrics.addWidget(self.size_lbl)
        metrics.addWidget(self.speed_lbl)
        metrics.addStretch()
        metrics.addWidget(self.eta_lbl)
        layout.addLayout(metrics)

        self.failure = FailurePanel(palette)
        self.failure.hide()
        layout.addWidget(self.failure)

        self.pause_btn.clicked.connect(lambda: self._call("pause_task"))
        self.resume_btn.clicked.connect(lambda: self._call("resume_task"))
        self.retry_btn.clicked.connect(lambda: self._call("retry_task"))
        self.cancel_btn.clicked.connect(lambda: self._call("cancel_task"))
        self.open_file_btn.clicked.connect(lambda: self._call("open_task_file"))
        self.open_btn.clicked.connect(lambda: self._call("open_task_folder"))
        self.remove_btn.clicked.connect(lambda: self._call("remove_task"))

    def _call(self, method: str) -> None:
        try:
            getattr(self._manager, method)(self.task_id)
        except Exception as exc:  # noqa: BLE001
            if self._on_error:
                self._on_error(exc)

    def _set_pill(self, label: str, key: str) -> None:
        self.pill.setText(label)
        if self.pill.property("state") != key:
            self.pill.setProperty("state", key)
            self.pill.style().unpolish(self.pill)
            self.pill.style().polish(self.pill)

    def refresh_theme(self, palette: Palette) -> None:
        self._palette = palette
        for btn in (
            self.pause_btn,
            self.resume_btn,
            self.retry_btn,
            self.cancel_btn,
            self.open_file_btn,
            self.open_btn,
            self.remove_btn,
        ):
            btn.refresh_theme(palette)
        self.thumb.refresh_theme(palette)
        self.bar.set_palette_tokens(palette)
        self.failure.icon.refresh_theme(palette, palette.danger, "transparent")

    def refresh(self, snap: TaskSnapshot) -> None:
        self._snap = snap
        self.name.setText(snap.filename)
        label, key = state_presentation(snap)
        self._set_pill(label, key)
        host = host_of(snap.url) or "lien direct"
        if getattr(snap, "provider", "http") == "youtube":
            quality = getattr(snap, "quality", "best")
            quality_txt = "meilleure qualité" if quality == "best" else quality
            host = f"YouTube · {quality_txt}"
        ext = extension_of(snap.filename).upper() or "FICHIER"
        added = ""
        try:
            moment = datetime.fromisoformat(snap.created_at)
            if moment.tzinfo is None:
                moment = moment.replace(tzinfo=UTC)
            added = f"  ·  ajouté à {moment.astimezone().strftime('%H:%M')}"
        except (TypeError, ValueError):
            added = ""
        self.meta.setText(f"{host}{added}")
        self.chip.setText(ext)
        self.resume.setVisible(snap.resumed_from_part and snap.state is TaskState.RUNNING)

        pct = snap.progress_percent
        self.bar.set_state(key if key != "neutral" else "queued")
        self.bar.set_value_animated(pct)
        if pct is None:
            self.percent.setText("…")
        elif snap.state is TaskState.FINALIZING:
            # Octets reçus, fichier en cours d'écriture/vérification : on dit ce
            # qui se passe au lieu d'afficher un « 100 % » prématuré.
            self.percent.setText("…")
            self.percent.setToolTip("Vérification du fichier en cours…")
        elif snap.state is TaskState.COMPLETED:
            self.percent.setText("100 %")
            self.percent.setToolTip("")
        else:
            # Troncature (jamais d'arrondi vers le haut) : 99,9 % reçu reste « 99 % ».
            self.percent.setText(f"{int(pct)} %")
            self.percent.setToolTip("")

        total = format_bytes(snap.total_bytes) if snap.total_bytes else "taille inconnue"
        starting = (
            snap.state is TaskState.RUNNING
            and snap.downloaded_bytes == 0
            and snap.total_bytes is None
        )
        if starting:
            self.size_lbl.setText("Connexion au serveur…")
        else:
            self.size_lbl.setText(f"{format_bytes(snap.downloaded_bytes)} / {total}")
        if starting:
            self.speed_lbl.setText("")
            self.eta_lbl.setText("En attente de réponse")
        elif snap.state is TaskState.RUNNING:
            self.speed_lbl.setText(format_speed(snap.speed_bps))
            eta = format_duration(snap.eta_seconds)
            self.eta_lbl.setText(f"Reste {eta}" if eta != "Indéterminé" else "Calcul en cours…")
        elif snap.state is TaskState.COMPLETED:
            self.speed_lbl.setText("Fichier vérifié")
            self.eta_lbl.setText("")
        elif snap.state is TaskState.FINALIZING:
            self.speed_lbl.setText("Écriture et vérification du fichier…")
            self.eta_lbl.setText("Presque terminé")
        elif snap.state is TaskState.PAUSED:
            self.speed_lbl.setText("En pause")
            self.eta_lbl.setText("Reprise possible")
        elif snap.state is TaskState.FAILED:
            self.speed_lbl.setText("")
            self.eta_lbl.setText("")
        else:
            self.speed_lbl.setText(label)
            self.eta_lbl.setText("")

        ext_kind = kind_of(snap.filename)
        self.thumb.set_source(
            snap.filename,
            str(snap.target_path)
            if snap.state is TaskState.COMPLETED and snap.file_exists
            else None,
        )
        if (
            snap.state is TaskState.COMPLETED
            and snap.file_exists
            and ext_kind in {"image", "video"}
        ):
            self._request_thumbnail(str(snap.target_path))

        if snap.state is TaskState.FAILED and snap.error_message:
            self.failure.set_failure(explain_failure(snap.error_message))
            self.failure.show()
        elif snap.active_warning:
            self.failure.set_failure(
                FailureInfo(
                    "Connexion instable",
                    snap.active_warning,
                    "La reprise automatique continue ; aucune action n'est nécessaire "
                    "pour l'instant.",
                    snap.active_warning,
                )
            )
            self.failure.show()
        elif snap.retrying:
            delay = snap.retry_in_seconds
            suffix = f" dans {delay:.0f} s" if delay is not None else ""
            self.failure.set_failure(
                FailureInfo(
                    "Nouvelle tentative programmée",
                    f"Le téléchargement reprendra automatiquement{suffix}.",
                    "Vous pouvez patienter ou relancer manuellement la tâche.",
                    snap.error_message or "reprise automatique",
                )
            )
            self.failure.show()
        else:
            self.failure.hide()

        st = snap.state
        self.pause_btn.setVisible(st in {TaskState.RUNNING, TaskState.QUEUED})
        self.resume_btn.setVisible(st is TaskState.PAUSED)
        self.retry_btn.setVisible(st in {TaskState.FAILED, TaskState.CANCELLED})
        self.cancel_btn.setVisible(st in {TaskState.RUNNING, TaskState.QUEUED, TaskState.PAUSED})
        self.open_file_btn.setVisible(st is TaskState.COMPLETED and snap.file_exists)
        self.open_btn.setVisible(st is TaskState.COMPLETED)
        self.remove_btn.setVisible(
            st in {TaskState.COMPLETED, TaskState.FAILED, TaskState.CANCELLED}
        )

    def _request_thumbnail(self, path: str) -> None:
        if not self.thumb.mark_requested():
            return

        def apply(pixmap: QPixmap) -> None:
            self.thumb.set_pixmap(pixmap)

        self._thumbnails.request(path, apply)


class HistoryRow(QFrame):
    """Ligne d'historique avec miniature, présence sur disque et actions."""

    def __init__(
        self,
        entry: HistoryEntry,
        manager,
        palette: Palette,
        thumbnails: ThumbnailService,
        *,
        on_remove,
        on_error=None,
        scale: float = 1.0,
    ) -> None:
        super().__init__()
        self.entry = entry
        self._manager = manager
        self._palette = palette
        self._thumbnails = thumbnails
        self._on_remove = on_remove
        self._on_error = on_error
        self.setObjectName("historyCard")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(
            round(13 * scale), round(11 * scale), round(13 * scale), round(11 * scale)
        )
        layout.setSpacing(round(12 * scale))

        self.thumb = Thumbnail(palette, width=round(66 * scale), height=round(48 * scale))
        self.thumb.set_source(entry.filename, entry.destination_path if entry.file_exists else None)
        layout.addWidget(self.thumb, 0, Qt.AlignmentFlag.AlignTop)

        info = QVBoxLayout()
        info.setSpacing(3)
        title_row = QHBoxLayout()
        title_row.setSpacing(8)
        self.name = ElidedLabel(entry.filename)
        self.name.setObjectName("cardTitle")
        title_row.addWidget(self.name, 1)
        self.pill = QLabel()
        self.pill.setObjectName("statePill")
        label, key = history_presentation(entry)
        self.pill.setText(label)
        self.pill.setProperty("state", key)
        title_row.addWidget(self.pill, 0)
        info.addLayout(title_row)

        presence = (
            f"Présent sur le disque · {format_bytes(entry.size_bytes)}"
            if entry.file_exists
            else "Fichier déplacé ou supprimé"
            if entry.status == "completed"
            else format_bytes(entry.size_bytes)
        )
        folder = Path(entry.destination_dir).name or entry.destination_dir
        self.meta = ElidedLabel(f"{human_time_ago(entry.finished_at)}  ·  {presence}  ·  {folder}")
        self.meta.setToolTip(entry.destination_dir)
        self.meta.setObjectName("mutedLabel")
        info.addWidget(self.meta)

        is_failure = entry.status == "failed" and bool(entry.error_message)
        self.issue = ElidedLabel()
        self.issue.setObjectName("dangerText" if is_failure else "tinyLabel")
        if is_failure:
            info_text = explain_failure(entry.error_message)
            self.issue.setText(f"{info_text.title} — {info_text.action}")
            self.issue.setToolTip(info_text.dialog_text())
        elif entry.retries_used:
            self.issue.setText(f"Repris automatiquement {entry.retries_used} fois")
        info.addWidget(self.issue)
        layout.addLayout(info, 1)

        actions = QHBoxLayout()
        actions.setSpacing(2)
        self.open_file_btn = IconButton(
            "play", "Ouvrir le fichier (application par défaut)", palette
        )
        self.open_file_btn.setVisible(entry.file_exists)
        self.open_btn = IconButton("folder", "Rouvrir le dossier", palette)
        self.redl_btn = IconButton("refresh", "Retélécharger une copie", palette)
        self.del_btn = IconButton(
            "trash", "Retirer de l'historique (le fichier est conservé)", palette
        )
        actions.addWidget(self.open_file_btn)
        actions.addWidget(self.open_btn)
        actions.addWidget(self.redl_btn)
        actions.addWidget(self.del_btn)
        layout.addLayout(actions)

        self.open_file_btn.clicked.connect(self._open_file)
        self.open_btn.clicked.connect(self._open)
        self.redl_btn.clicked.connect(self._redownload)
        self.del_btn.clicked.connect(lambda: self._on_remove(entry.id))

        if entry.file_exists and kind_of(entry.filename) in {"image", "video"}:
            if self.thumb.mark_requested():
                self._thumbnails.request(entry.destination_path, self.thumb.set_pixmap)

    def _open_file(self) -> None:
        try:
            self._manager.open_history_file(self.entry.id)
        except Exception as exc:  # noqa: BLE001
            if self._on_error:
                self._on_error(exc)

    def _open(self) -> None:
        try:
            self._manager.open_history_folder(self.entry.id)
        except Exception as exc:  # noqa: BLE001
            if self._on_error:
                self._on_error(exc)

    def _redownload(self) -> None:
        from overload.downloads.duplicates import DuplicatePolicy

        try:
            self._manager.enqueue(self.entry.url, duplicate_policy=DuplicatePolicy.RENAME)
        except Exception as exc:  # noqa: BLE001
            if self._on_error:
                self._on_error(exc)

    def refresh_theme(self, palette: Palette) -> None:
        self._palette = palette
        for btn in (self.open_file_btn, self.open_btn, self.redl_btn, self.del_btn):
            btn.refresh_theme(palette)
        self.thumb.refresh_theme(palette)


class EmptyState(QWidget):
    """État vide illustré avec appel à l'action."""

    def __init__(
        self,
        palette: Palette,
        icon_name: str,
        title: str,
        text: str,
        *,
        action_text: str | None = None,
        on_action=None,
    ) -> None:
        super().__init__()
        self._palette = palette
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 36, 24, 36)
        layout.setSpacing(10)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.badge = GlyphBadge(
            icon_name,
            palette,
            size=58,
            color=palette.accent_text,
            background=palette.accent_soft,
            radius=18,
            icon_size=26,
        )
        layout.addWidget(self.badge, 0, Qt.AlignmentFlag.AlignHCenter)
        self._title = QLabel(title)
        self._title.setObjectName("emptyTitle")
        self._title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self._title)
        self._text = QLabel(text)
        self._text.setObjectName("emptyText")
        self._text.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._text.setWordWrap(True)
        self._text.setMaximumWidth(460)
        layout.addWidget(self._text)
        self._action = None
        if action_text and on_action is not None:
            self._action = QPushButton(action_text)
            self._action.setObjectName("secondaryBtn")
            self._action.setCursor(Qt.CursorShape.PointingHandCursor)
            self._action.clicked.connect(on_action)
            layout.addWidget(self._action, 0, Qt.AlignmentFlag.AlignHCenter)

    def set_texts(self, title: str, text: str, action_text: str | None = None) -> None:
        self._title.setText(title)
        self._text.setText(text)
        if action_text and self._action is not None:
            self._action.setText(action_text)

    def refresh_theme(self, palette: Palette) -> None:
        self._palette = palette
        self.badge.refresh_theme(palette, palette.accent_text, palette.accent_soft)


class ActivityRow(QFrame):
    """Ligne compacte « téléchargements récents » de l'accueil."""

    def __init__(
        self, entry: HistoryEntry, palette: Palette, thumbnails: ThumbnailService, *, on_open
    ) -> None:
        super().__init__()
        self._palette = palette
        self.entry = entry
        self._on_open = on_open
        self.setObjectName("historyCard")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(10)
        self.thumb = Thumbnail(palette, width=52, height=38)
        self.thumb.set_source(entry.filename, entry.destination_path if entry.file_exists else None)
        layout.addWidget(self.thumb)
        col = QVBoxLayout()
        col.setSpacing(1)
        self.name = ElidedLabel(entry.filename)
        self.name.setObjectName("cardTitle")
        col.addWidget(self.name)
        _, key = history_presentation(entry)
        status = {"completed": "Terminé", "failed": "Interrompu", "cancelled": "Annulé"}.get(
            entry.status, entry.status
        )
        extra = f" · {format_bytes(entry.size_bytes)}" if entry.size_bytes else ""
        meta = QLabel(f"{status}{extra} · {human_time_ago(entry.finished_at)}")
        meta.setObjectName("tinyLabel")
        status_color = (
            palette.success
            if key == "completed"
            else palette.danger
            if key == "failed"
            else palette.text_muted
        )
        meta.setStyleSheet(f"color: {status_color};")
        col.addWidget(meta)
        layout.addLayout(col, 1)
        open_btn = IconButton("external", "Ouvrir le dossier", palette, size=28, icon_size=15)
        open_btn.clicked.connect(lambda: self._on_open(entry))
        layout.addWidget(open_btn)
        if entry.file_exists and kind_of(entry.filename) in {"image", "video"}:
            if self.thumb.mark_requested():
                thumbnails.request(entry.destination_path, self.thumb.set_pixmap)

    def refresh_theme(self, palette: Palette) -> None:
        self._palette = palette
        self.thumb.refresh_theme(palette)


class QueueRow(QWidget):
    """Ligne compacte de la file d'attente de l'accueil."""

    def __init__(self, palette: Palette, snap: TaskSnapshot) -> None:
        super().__init__()
        self._palette = palette
        self.task_id = snap.id
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 4, 0, 4)
        layout.setSpacing(9)
        col = QVBoxLayout()
        col.setSpacing(3)
        top = QHBoxLayout()
        self.name = ElidedLabel(snap.filename)
        self.name.setObjectName("cardTitle")
        top.addWidget(self.name, 1)
        self.pill = QLabel()
        self.pill.setObjectName("statePill")
        top.addWidget(self.pill)
        col.addLayout(top)
        self.bar = ProgressBar(palette, compact=True)
        col.addWidget(self.bar)
        layout.addLayout(col, 1)
        self.refresh(snap)

    def refresh(self, snap: TaskSnapshot) -> None:
        self.name.setText(snap.filename)
        label, key = state_presentation(snap)
        self.pill.setText(label)
        if self.pill.property("state") != key:
            self.pill.setProperty("state", key)
            self.pill.style().unpolish(self.pill)
            self.pill.style().polish(self.pill)
        self.bar.set_state(key if key != "neutral" else "queued")
        self.bar.set_value_animated(snap.progress_percent)

    def refresh_theme(self, palette: Palette) -> None:
        self._palette = palette
        self.bar.set_palette_tokens(palette)


class Toast(QFrame):
    """Notification discrète en bas à droite."""

    def __init__(self, parent: QWidget, palette: Palette) -> None:
        super().__init__(parent)
        self.setObjectName("toast")
        self._palette = palette
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 10, 16, 10)
        layout.setSpacing(9)
        self.badge = GlyphBadge(
            "check",
            palette,
            size=26,
            color=palette.success,
            background=palette.success_soft,
            icon_size=15,
        )
        layout.addWidget(self.badge)
        self.label = QLabel()
        self.label.setObjectName("cardTitle")
        layout.addWidget(self.label)
        self._effect = QGraphicsOpacityEffect(self)
        self._effect.setOpacity(0.0)
        self.setGraphicsEffect(self._effect)
        self._anim = QPropertyAnimation(self._effect, b"opacity", self)
        self._anim.setDuration(180)
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._hide_animated)
        self.hide()

    def show_message(self, text: str, kind: str = "success") -> None:
        colors = {
            "success": (self._palette.success, self._palette.success_soft, "check"),
            "error": (self._palette.danger, self._palette.danger_soft, "alert"),
            "info": (self._palette.info, self._palette.info_soft, "info"),
        }
        fg, bg, glyph = colors.get(kind, colors["info"])
        self.badge.refresh_theme(self._palette, fg, bg)
        self.badge.set_icon(glyph)
        self.label.setText(text)
        self.adjustSize()
        parent = self.parentWidget()
        if parent is not None:
            self.move(
                max(16, parent.width() - self.width() - 26),
                max(16, parent.height() - self.height() - 24),
            )
        self.show()
        self.raise_()
        self._anim.stop()
        self._anim.setStartValue(self._effect.opacity())
        self._anim.setEndValue(1.0)
        self._anim.start()
        self._timer.start(2800)

    def _hide_animated(self) -> None:
        self._anim.stop()
        self._anim.setStartValue(self._effect.opacity())
        self._anim.setEndValue(0.0)
        self._anim.finished.connect(self._hide_once)
        self._anim.start()

    def _hide_once(self) -> None:
        try:
            self._anim.finished.disconnect(self._hide_once)
        except (RuntimeError, TypeError):
            pass
        self.hide()


class AccentSwatch(QAbstractButton):
    """Pastille de choix de la couleur d'accent."""

    def __init__(self, color: str, label: str, palette: Palette) -> None:
        super().__init__()
        self._color = color
        self._palette = palette
        self.setCheckable(True)
        self.setFixedSize(34, 34)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip(label)

    def refresh_theme(self, palette: Palette) -> None:
        self._palette = palette
        self.update()

    def paintEvent(self, _event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        center = self.rect().center()
        r = 12.0
        if self.isChecked():
            painter.setPen(QPen(qcolor(self._palette.text), 2))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawEllipse(QPointF(center), r + 4.5, r + 4.5)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(qcolor(self._color))
        painter.drawEllipse(QPointF(center), r, r)
        if self.isChecked():
            pix = icons.pixmap("check", "#FFFFFF", 14, 2.2)
            painter.drawPixmap(center.x() - 7, center.y() - 7, pix)
        painter.end()


class HeroArt(QWidget):
    """Illustration décorative de la carte d'accueil (anneaux + éclair)."""

    def __init__(self, palette: Palette, size: int = 132) -> None:
        super().__init__()
        self._palette = palette
        self.setFixedSize(size, size)

    def refresh_theme(self, palette: Palette) -> None:
        self._palette = palette
        self.update()

    def paintEvent(self, _event) -> None:  # noqa: N802
        p = self._palette
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        center = QPointF(self.width() / 2, self.height() / 2)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        for i, alpha in enumerate((34, 26, 18)):
            radius = self.width() * (0.5 - i * 0.11)
            painter.setPen(QPen(QColor(*p.accent_rgb(), alpha), 1.2))
            painter.drawEllipse(center, radius, radius)
        grad = QRadialGradient(center, self.width() * 0.34)
        grad.setColorAt(0.0, QColor(*p.accent_rgb(), 70))
        grad.setColorAt(1.0, QColor(*p.accent_rgb(), 0))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(grad)
        painter.drawEllipse(center, self.width() * 0.36, self.width() * 0.36)
        bolt = icons.pixmap("zap", p.accent, int(self.width() * 0.4))
        painter.drawPixmap(
            int(center.x() - self.width() * 0.2),
            int(center.y() - self.width() * 0.2),
            bolt,
        )
        painter.end()


class InfoBanner(QFrame):
    """Bandeau d'information réutilisable (sécurité, astuce, avertissement)."""

    def __init__(
        self,
        palette: Palette,
        icon_name: str,
        text: str,
        *,
        kind: str = "info",
        title: str | None = None,
    ) -> None:
        super().__init__()
        colors = {
            "info": ("infoPanel", palette.info, palette.info_soft),
            "warning": ("warningPanel", palette.warning, palette.warning_soft),
            "success": ("successPanel", palette.success, palette.success_soft),
            "danger": ("errorPanel", palette.danger, palette.danger_soft),
        }
        name, fg, bg = colors.get(kind, colors["info"])
        self.setObjectName(name)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(10)
        self.badge = GlyphBadge(
            icon_name, palette, size=28, color=fg, background="transparent", icon_size=17
        )
        layout.addWidget(self.badge, 0, Qt.AlignmentFlag.AlignTop)
        col = QVBoxLayout()
        col.setSpacing(2)
        if title:
            title_lbl = QLabel(title)
            title_lbl.setStyleSheet(f"color: {fg}; font-weight: 700;")
            col.addWidget(title_lbl)
        self.text = QLabel(text)
        self.text.setObjectName("mutedLabel")
        self.text.setWordWrap(True)
        col.addWidget(self.text)
        layout.addLayout(col, 1)


class StepBadge(QWidget):
    """Pastille numérotée du parcours en étapes (1, 2, 3… ou coche si terminé)."""

    def __init__(self, number: int, palette: Palette, *, size: int = 28) -> None:
        super().__init__()
        self._number = number
        self._palette = palette
        self._done = False
        self.setFixedSize(size, size)

    def set_done(self, done: bool) -> None:
        if done != self._done:
            self._done = done
            self.update()

    def refresh_theme(self, palette: Palette) -> None:
        self._palette = palette
        self.update()

    def paintEvent(self, _event) -> None:  # noqa: N802
        p = self._palette
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(qcolor(p.success if self._done else p.accent))
        painter.drawEllipse(QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5))
        ink = "#101713" if self._done else p.accent_ink
        if self._done:
            pix = icons.pixmap("check", ink, round(self.width() * 0.58), 2.2)
            painter.drawPixmap(
                round((self.width() - pix.width() / pix.devicePixelRatio()) / 2),
                round((self.height() - pix.height() / pix.devicePixelRatio()) / 2),
                pix,
            )
        else:
            font = QFont(self.font())
            font.setPixelSize(max(10, round(self.width() * 0.46)))
            font.setWeight(QFont.Weight.Bold)
            painter.setFont(font)
            painter.setPen(QColor(ink))
            painter.drawText(QRectF(self.rect()), Qt.AlignmentFlag.AlignCenter, str(self._number))
        painter.end()


class ToolCard(QPushButton):
    """Carte d'outil cliquable : à quoi ça sert, quoi fournir, ce qui va se passer.

    Utilisée dans l'espace Créateurs et l'aide pour expliquer chaque outil
    AVANT de l'ouvrir : titre, description courte et ligne « pratique »
    (fichiers acceptés / résultat attendu).
    """

    def __init__(
        self,
        icon_name: str,
        title: str,
        text: str,
        meta: str,
        palette: Palette,
        *,
        on_click=None,
        scale: float = 1.0,
    ) -> None:
        super().__init__()
        self._palette = palette
        self._icon_name = icon_name
        self.setObjectName("toolCard")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setAccessibleName(title)
        self.setToolTip(title)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
        self.setMinimumHeight(round(96 * scale))
        layout = QHBoxLayout(self)
        layout.setContentsMargins(
            round(14 * scale), round(12 * scale), round(12 * scale), round(12 * scale)
        )
        layout.setSpacing(round(11 * scale))
        self.badge = GlyphBadge(
            icon_name, palette, size=round(38 * scale), radius=round(11 * scale), icon_size=19
        )
        layout.addWidget(self.badge, 0, Qt.AlignmentFlag.AlignTop)
        col = QVBoxLayout()
        col.setSpacing(3)
        self.title_label = QLabel(title)
        self.title_label.setObjectName("toolTitle")
        self.title_label.setWordWrap(True)
        col.addWidget(self.title_label)
        self.text_label = QLabel(text)
        self.text_label.setObjectName("toolText")
        self.text_label.setWordWrap(True)
        col.addWidget(self.text_label)
        self.meta_label = QLabel(meta)
        self.meta_label.setObjectName("toolMeta")
        self.meta_label.setWordWrap(True)
        col.addWidget(self.meta_label)
        col.addStretch()
        layout.addLayout(col, 1)
        self.chevron = QLabel()
        self.chevron.setPixmap(icons.pixmap("chevron-right", palette.text_muted, 16))
        layout.addWidget(self.chevron, 0, Qt.AlignmentFlag.AlignVCenter)
        # Les enfants ne doivent jamais intercepter le clic de la carte.
        for child in (self.badge, self.title_label, self.text_label, self.meta_label, self.chevron):
            child.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        if on_click is not None:
            self.clicked.connect(on_click)

    def refresh_theme(self, palette: Palette) -> None:
        self._palette = palette
        self.badge.refresh_theme(palette, palette.accent_text, palette.accent_soft)
        self.chevron.setPixmap(icons.pixmap("chevron-right", palette.text_muted, 16))


class LibraryRow(QFrame):
    """Ligne de la bibliothèque : un fichier local retrouvé sur le disque."""

    def __init__(
        self,
        item: LibraryFile,
        palette: Palette,
        thumbnails: ThumbnailService,
        *,
        source_url: str = "",
        on_open_file=None,
        on_open_folder=None,
        on_analyze=None,
        scale: float = 1.0,
    ) -> None:
        super().__init__()
        self.item = item
        self._palette = palette
        self._on_analyze = on_analyze
        self.setObjectName("historyCard")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(
            round(13 * scale), round(11 * scale), round(13 * scale), round(11 * scale)
        )
        layout.setSpacing(round(12 * scale))

        self.thumb = Thumbnail(palette, width=round(66 * scale), height=round(48 * scale))
        self.thumb.set_source(item.name, str(item.path))
        layout.addWidget(self.thumb, 0, Qt.AlignmentFlag.AlignTop)

        info = QVBoxLayout()
        info.setSpacing(3)
        title_row = QHBoxLayout()
        title_row.setSpacing(8)
        self.name = ElidedLabel(item.name)
        self.name.setObjectName("cardTitle")
        title_row.addWidget(self.name, 1)
        self.chip = QLabel(item.extension.upper() or "FICHIER")
        self.chip.setObjectName("formatChip")
        title_row.addWidget(self.chip, 0)
        info.addLayout(title_row)

        when = human_time_ago(datetime.fromtimestamp(item.modified_at, tz=UTC).isoformat())
        self.meta = ElidedLabel(
            f"{item.kind_label}  ·  {format_bytes(item.size_bytes)}  ·  {when}"
            f"  ·  {item.folder_name}"
        )
        self.meta.setObjectName("mutedLabel")
        self.meta.setToolTip(str(item.path))
        info.addWidget(self.meta)

        self.source = ElidedLabel(
            f"Téléchargé depuis {host_of(source_url)}" if source_url else str(item.path.parent)
        )
        self.source.setObjectName("tinyLabel")
        self.source.setToolTip(source_url or str(item.path.parent))
        info.addWidget(self.source)
        layout.addLayout(info, 1)

        actions = QHBoxLayout()
        actions.setSpacing(2)
        self.open_file_btn = IconButton(
            "play", "Ouvrir le fichier (application par défaut)", palette
        )
        self.open_folder_btn = IconButton("folder", "Afficher dans le dossier", palette)
        self.analyze_btn = IconButton(
            "monitor", "Analyser ce fichier dans l'espace Créateurs", palette
        )
        self.analyze_btn.setVisible(on_analyze is not None and item.kind in {"video", "audio"})
        actions.addWidget(self.open_file_btn)
        actions.addWidget(self.open_folder_btn)
        actions.addWidget(self.analyze_btn)
        layout.addLayout(actions)

        if on_open_file is not None:
            self.open_file_btn.clicked.connect(lambda: on_open_file(item))
        if on_open_folder is not None:
            self.open_folder_btn.clicked.connect(lambda: on_open_folder(item))
        if on_analyze is not None:
            self.analyze_btn.clicked.connect(lambda: on_analyze(item))

        if item.kind in {"image", "video"} and self.thumb.mark_requested():
            thumbnails.request(str(item.path), self.thumb.set_pixmap)

    def refresh_theme(self, palette: Palette) -> None:
        self._palette = palette
        for btn in (self.open_file_btn, self.open_folder_btn, self.analyze_btn):
            btn.refresh_theme(palette)
        self.thumb.refresh_theme(palette)
