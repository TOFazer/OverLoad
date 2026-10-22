"""Fenêtre principale d'OverLoad v2.0 : navigation latérale et pages de travail.

Organisation (barre latérale fixe, zone de travail principale) :
Accueil, Téléchargements, Bibliothèque, Espace Créateurs, Historique,
Paramètres et Aide. L'analyse multimédia vit dans l'espace Créateurs,
avec les autres outils de préparation au montage.

Cette couche ne contient aucune logique métier : elle observe les instantanés
du `DownloadManager`, indexe les fichiers locaux via `overload.library`,
enregistre les préférences via `SettingsStore` et délègue les opérations à
l'historique et au moteur de téléchargement.
"""

from __future__ import annotations

import shutil
import threading
import time
import webbrowser
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from PySide6.QtCore import (
    QEasingCurve,
    QObject,
    QPropertyAnimation,
    QRectF,
    QSize,
    Qt,
    QTimer,
    Signal,
)
from PySide6.QtGui import (
    QAction,
    QColor,
    QIcon,
    QKeySequence,
    QLinearGradient,
    QPainter,
    QPixmap,
    QShortcut,
)
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFrame,
    QGraphicsOpacityEffect,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from overload import __version__
from overload.core.errors import OverloadError
from overload.core.formatting import format_bytes, format_duration
from overload.core.paths import default_data_dir, open_file, open_folder
from overload.downloads.duplicates import DuplicateDetectedError, DuplicatePolicy
from overload.downloads.state import TaskState
from overload.downloads.youtube import QUALITY_CHOICES, is_youtube_url
from overload.library.scan import KIND_FILTERS, SORTS, LibraryScan, filter_files, scan_library
from overload.settings.store import ACCENTS as ACCENT_KEYS
from overload.settings.store import UI_SCALES as UI_SCALE_KEYS
from overload.ui import icons
from overload.ui.components import (
    AccentSwatch,
    ActivityRow,
    DownloadCard,
    ElidedLabel,
    EmptyState,
    GlyphBadge,
    HeroArt,
    HistoryRow,
    IconButton,
    InfoBanner,
    LibraryRow,
    LogoBadge,
    NavButton,
    QueueRow,
    SegmentedControl,
    Sparkline,
    StatCard,
    StepBadge,
    ThumbnailService,
    Toast,
    ToolCard,
)
from overload.ui.failure_text import explain_failure
from overload.ui.filedialogs import choose_directory, choose_open_file
from overload.ui.theme import (
    ACCENTS as ACCENT_DEFS,
)
from overload.ui.theme import (
    UI_SCALE_LABELS,
    apply_appearance,
    scale_factor,
)

PAGE_META: dict[str, tuple[str, str, str, str]] = {
    "home": (
        "Accueil",
        "Tout commence ici : téléchargez et organisez vos médias simplement.",
        "home",
        "accent",
    ),
    "downloads": (
        "Téléchargements",
        "Tâches en cours, en attente, en pause ou à relancer.",
        "download",
        "info",
    ),
    "library": (
        "Bibliothèque",
        "Retrouvez et ouvrez vos fichiers locaux, déjà sur le disque.",
        "library",
        "success",
    ),
    "creators": (
        "Espace Créateurs",
        "Préparez vos projets vidéo sans jamais toucher aux originaux.",
        "film",
        "success",
    ),
    "history": (
        "Historique",
        "Vos téléchargements précédents, même après relance d'OverLoad.",
        "history",
        "warning",
    ),
    "settings": (
        "Paramètres",
        "Destination, apparence, comportement et options avancées.",
        "settings",
        "accent",
    ),
    "help": (
        "Aide",
        "Démarrage rapide, dépannage et informations sur l'application.",
        "help",
        "info",
    ),
}

# Ordre de navigation (barre latérale et raccourcis Ctrl+1…7).
NAV_ORDER = ["home", "downloads", "library", "creators", "history", "settings", "help"]

SPEED_PRESETS = [
    ("Illimitée", 0),
    ("250 Ko/s", 250 * 1024),
    ("500 Ko/s", 500 * 1024),
    ("1 Mo/s", 1024 * 1024),
    ("2 Mo/s", 2 * 1024 * 1024),
    ("5 Mo/s", 5 * 1024 * 1024),
    ("10 Mo/s", 10 * 1024 * 1024),
    ("Personnalisée…", -1),
]


def build_app_icon() -> QIcon:
    """Icône applicative vectorielle : éclair crème sur dégradé mousse → sapin."""
    icon = QIcon()
    for size in (16, 24, 32, 48, 64, 128, 256):
        pix = QPixmap(size, size)
        pix.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pix)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = QRectF(0, 0, size, size)
        grad = QLinearGradient(rect.topLeft(), rect.bottomRight())
        grad.setColorAt(0.0, QColor("#4E7D60"))  # dérivé clair du vert forêt
        grad.setColorAt(1.0, QColor("#101713"))  # vert-noir profond (identité v2.0)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(grad)
        radius = size * 0.27
        painter.drawRoundedRect(rect, radius, radius)
        painter.scale(size / 24.0, size / 24.0)
        icons.draw_glyph(painter, "zap", "#EAF1E8")
        painter.end()
        icon.addPixmap(pix)
    return icon


def _divider() -> QFrame:
    line = QFrame()
    line.setObjectName("divider")
    line.setFixedHeight(1)
    return line


def _clear_rows(layout: QVBoxLayout, keep_last: int = 1) -> None:
    """Retire et masque immédiatement les anciennes lignes (évite les résidus visuels)."""
    while layout.count() > keep_last:
        item = layout.takeAt(0)
        widget = item.widget()
        if widget is not None:
            widget.hide()
            widget.setParent(None)
            widget.deleteLater()


class _MediaProbe(QObject):
    """Interroge YouTube en arrière-plan pour ne jamais figer l'interface."""

    done = Signal(str, object, object)

    def __init__(self, manager, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._manager = manager

    def start(self, url: str) -> None:
        threading.Thread(target=self._run, args=(url,), daemon=True).start()

    def _run(self, url: str) -> None:
        try:
            info = self._manager.inspect_media(url)
        except Exception as exc:  # noqa: BLE001 - message affiché tel quel
            self.done.emit(url, None, str(exc))
        else:
            self.done.emit(url, info, None)


class _LibraryProbe(QObject):
    """Indexe le dossier de la bibliothèque hors du thread graphique."""

    done = Signal(object, object)

    def start(self, root: Path) -> None:
        threading.Thread(target=self._run, args=(root,), daemon=True).start()

    def _run(self, root: Path) -> None:
        try:
            scan = scan_library(root)
        except Exception as exc:  # noqa: BLE001 - message affiché tel quel
            self.done.emit(None, str(exc))
        else:
            self.done.emit(scan, "")


class _DownloadOperation(QObject):
    """Opération de téléchargement exécutée hors du thread graphique.

    L'interface ne se fige jamais : `on_done(résultat, erreur)` est appelé sur le
    thread graphique dès que l'opération se termine, ou après un délai maximal
    avec une erreur explicite. Une finition tardive reste signalée (le succès
    affiche la tâche ajoutée ; un échec tardif est déjà couvert par le délai).
    """

    _result = Signal(object, object)
    settled = Signal()

    def __init__(
        self,
        fn: Any,
        on_done: Any,
        *,
        timeout_ms: int = 30_000,
        timeout_error: OverloadError | None = None,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._on_done = on_done
        self._timeout_error = timeout_error
        self._settled = False
        self._result.connect(self._deliver)
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(max(1, int(timeout_ms)))
        self._timer.timeout.connect(self._on_timeout)
        self._timer.start()
        threading.Thread(target=self._run, args=(fn,), daemon=True).start()

    def _run(self, fn: Any) -> None:
        try:
            result = fn()
        except Exception as exc:  # noqa: BLE001 - remonté tel quel à l'interface
            outcome = (None, exc)
        else:
            outcome = (result, None)
        try:
            self._result.emit(*outcome)
        except RuntimeError:  # fenêtre détruite pendant l'opération
            pass

    def _on_timeout(self) -> None:
        if self._settled:
            return
        self._settled = True
        error = self._timeout_error or OverloadError(
            "L'analyse du lien prend trop de temps.",
            "le service met trop de temps à répondre ou la connexion est instable.",
            "Vérifiez votre connexion Internet, puis réessayez.",
        )
        self.settled.emit()
        self._on_done(None, error)

    def _deliver(self, result: object, error: object) -> None:
        if not self._settled:
            self._settled = True
            self.settled.emit()
            self._on_done(result, error)
            self.deleteLater()
            return
        # Arrivé après le délai maximal : seul un succès reste à signaler, car
        # la tâche existe alors déjà dans le gestionnaire de téléchargements.
        if result is not None:
            self._on_done(result, None)
        self.deleteLater()


class BatchDialog(QDialog):
    """Boîte de dialogue de téléchargement par lot."""

    def __init__(self, window: OverloadWindow) -> None:
        super().__init__(window)
        self.window = window
        self.setWindowTitle("Télécharger plusieurs liens")
        self.resize(720, 520)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 20, 22, 18)
        layout.setSpacing(12)

        title = QLabel("Lot de liens")
        title.setObjectName("pageTitle")
        layout.addWidget(title)
        subtitle = QLabel(
            "Collez une adresse par ligne. Les lignes vides et les commentaires (#) sont ignorés."
        )
        subtitle.setObjectName("mutedLabel")
        subtitle.setWordWrap(True)
        layout.addWidget(subtitle)

        self.edit = QPlainTextEdit()
        self.edit.setPlaceholderText(
            "https://exemple.com/video-1.mp4\nhttps://exemple.com/audio-2.mp3"
        )
        layout.addWidget(self.edit, 1)

        info_row = QHBoxLayout()
        import_btn = QPushButton("Importer un fichier .txt…")
        import_btn.setObjectName("ghostBtn")
        inspect_btn = QPushButton("Vérifier les liens")
        inspect_btn.setObjectName("ghostBtn")
        self.info = QLabel("")
        self.info.setObjectName("mutedLabel")
        info_row.addWidget(import_btn)
        info_row.addWidget(inspect_btn)
        info_row.addWidget(self.info, 1)
        layout.addLayout(info_row)

        quality_row = QHBoxLayout()
        quality_label = QLabel("Qualité YouTube")
        quality_label.setObjectName("mutedLabel")
        self.quality_combo = QComboBox()
        for value, label in QUALITY_CHOICES:
            self.quality_combo.addItem(label, value)
        self.quality_combo.setToolTip(
            "Utilisée pour les liens YouTube ; ignorée pour les fichiers directs."
        )
        quality_row.addWidget(quality_label)
        quality_row.addWidget(self.quality_combo, 1)
        layout.addLayout(quality_row)

        buttons = QDialogButtonBox()
        cancel = buttons.addButton("Annuler", QDialogButtonBox.ButtonRole.RejectRole)
        start = buttons.addButton("Lancer le lot", QDialogButtonBox.ButtonRole.AcceptRole)
        start.setObjectName("primaryBtn")
        layout.addWidget(buttons)

        self.start_btn = start
        import_btn.clicked.connect(self._import_txt)
        inspect_btn.clicked.connect(self._inspect)
        cancel.clicked.connect(self.reject)
        start.clicked.connect(self._start)

    def _import_txt(self) -> None:
        chosen = choose_open_file(
            self,
            "Importer une liste de liens",
            fallback=self.window.settings_store.get().destination_dir,
            name_filter="Fichiers texte (*.txt);;Tous les fichiers (*.*)",
        )
        if not chosen:
            return
        try:
            content = Path(chosen).read_text(encoding="utf-8", errors="ignore")
        except OSError as exc:
            self.window.show_error(exc)
            return
        current = self.edit.toPlainText().strip()
        self.edit.setPlainText(f"{current}\n{content}".strip() if current else content)
        self._inspect()

    def _inspect(self) -> None:
        raw = self.edit.toPlainText()
        if not raw.strip():
            self.info.setText("Collez au moins un lien.")
            return
        result = self.window.manager.inspect_batch(raw)
        self.info.setText(
            f"{len(result['valid'])} prêt(s) · {len(result['duplicates'])} déjà présent(s) · "
            f"{len(result['rejected'])} invalide(s)"
        )

    def _start(self) -> None:
        raw = self.edit.toPlainText()
        if not raw.strip():
            self.info.setText("Collez au moins un lien.")
            return
        policy = self.window.manager.settings().duplicate_policy
        effective = DuplicatePolicy.SKIP if policy is DuplicatePolicy.ASK else policy
        quality = self.quality_combo.currentData()

        def work() -> Any:
            return self.window.manager.enqueue_batch(
                raw,
                duplicate_policy=effective,
                quality=quality,
            )

        def done(result: object, error: object) -> None:
            if error is not None:
                self.window.show_error(error)
                self.info.setText("Le lot n'a pas pu être lancé — réessayez.")
                self.start_btn.setEnabled(True)
                return
            self.window.toast(
                f"Lot lancé : {len(result.added)} ajouté(s), "
                f"{len(result.skipped_duplicates)} doublon(s) ignoré(s)."
            )
            if result.added:
                self.window.maybe_reload_history(force=True)
                self.accept()
            else:
                self.info.setText(
                    f"Aucun lien ajouté · {len(result.rejected)} rejeté(s) · "
                    f"{len(result.skipped_duplicates)} doublon(s)"
                )
                self.start_btn.setEnabled(True)

        # L'analyse réseau du lot ne doit jamais figer la fenêtre.
        self.start_btn.setEnabled(False)
        self.info.setText("Analyse du lot en cours…")
        self.window._run_download_operation(work, done)


class SettingsPage(QWidget):
    """Page de personnalisation et de réglages avancés."""

    def __init__(self, window: OverloadWindow) -> None:
        super().__init__()
        self.window = window
        self._syncing = False
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        outer.addWidget(scroll)
        content = QWidget()
        scroll.setWidget(content)
        layout = QVBoxLayout(content)
        layout.setContentsMargins(26, 20, 26, 26)
        layout.setSpacing(16)

        layout.addWidget(
            self._section_title("Apparence", "Thème, couleur d'accent et taille de l'interface.")
        )
        layout.addWidget(self._build_appearance())
        layout.addWidget(
            self._section_title(
                "Téléchargements", "Dossier, simultanéité et limite de bande passante."
            )
        )
        layout.addWidget(self._build_downloads())
        layout.addWidget(
            self._section_title("Fiabilité", "Reprise automatique après une coupure réseau.")
        )
        layout.addWidget(self._build_reliability())
        layout.addWidget(self._section_title("À propos", "Version, licence et dossiers utilisés."))
        layout.addWidget(self._build_about())
        layout.addStretch()
        self.refresh_from_prefs()

    def _section_title(self, title: str, subtitle: str) -> QWidget:
        box = QWidget()
        col = QVBoxLayout(box)
        col.setContentsMargins(2, 4, 2, 0)
        col.setSpacing(2)
        heading = QLabel(title)
        heading.setObjectName("sectionTitle")
        text = QLabel(subtitle)
        text.setObjectName("mutedLabel")
        col.addWidget(heading)
        col.addWidget(text)
        return box

    def _card(self) -> tuple[QFrame, QVBoxLayout]:
        card = QFrame()
        card.setObjectName("settingCard")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(20, 18, 20, 18)
        layout.setSpacing(16)
        return card, layout

    def _row(self, label: str, description: str, control: QWidget) -> QWidget:
        row = QWidget()
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(18)
        text = QVBoxLayout()
        text.setSpacing(2)
        title = QLabel(label)
        title.setStyleSheet("font-weight: 600;")
        desc = QLabel(description)
        desc.setObjectName("mutedLabel")
        desc.setWordWrap(True)
        text.addWidget(title)
        text.addWidget(desc)
        layout.addLayout(text, 1)
        layout.addWidget(control, 0, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        return row

    def _build_appearance(self) -> QWidget:
        card, layout = self._card()
        self.theme_control = SegmentedControl(
            [("dark", "Sombre"), ("light", "Clair")], self.window.tokens
        )
        layout.addWidget(
            self._row(
                "Thème",
                "Interface sombre premium ou éclaircie pour les journées ensoleillées.",
                self.theme_control,
            )
        )

        accent_row = QWidget()
        accent_layout = QHBoxLayout(accent_row)
        accent_layout.setContentsMargins(0, 0, 0, 0)
        accent_layout.setSpacing(6)
        self._swatches: dict[str, AccentSwatch] = {}
        for key in ACCENT_KEYS:
            definition = ACCENT_DEFS[key]
            swatch = AccentSwatch(definition.dark, definition.label, self.window.tokens)
            swatch.clicked.connect(lambda _checked=False, k=key: self._set_accent(k))
            accent_layout.addWidget(swatch)
            self._swatches[key] = swatch
        layout.addWidget(
            self._row(
                "Couleur d'accent",
                "Utilisée pour les boutons, la progression et les éléments actifs.",
                accent_row,
            )
        )

        self.scale_control = SegmentedControl(
            [(key, UI_SCALE_LABELS[key]) for key in UI_SCALE_KEYS], self.window.tokens
        )
        layout.addWidget(
            self._row(
                "Taille de l'interface",
                "Compacte pour les petits écrans, grande pour le confort visuel.",
                self.scale_control,
            )
        )

        self.theme_control.value_changed.connect(lambda value: self._apply(theme=value))
        self.scale_control.value_changed.connect(lambda value: self._apply(ui_scale=value))
        return card

    def _build_downloads(self) -> QWidget:
        card, layout = self._card()
        dest_row = QWidget()
        dest_layout = QHBoxLayout(dest_row)
        dest_layout.setContentsMargins(0, 0, 0, 0)
        dest_layout.setSpacing(6)
        self.dest_edit = QLineEdit()
        self.dest_edit.setMinimumWidth(300)
        self.dest_edit.setReadOnly(True)
        browse = QPushButton("Parcourir…")
        browse.setObjectName("ghostBtn")
        open_btn = IconButton("folder", "Ouvrir le dossier", self.window.tokens)
        dest_layout.addWidget(self.dest_edit, 1)
        dest_layout.addWidget(browse)
        dest_layout.addWidget(open_btn)
        layout.addWidget(
            self._row(
                "Dossier de destination",
                "Les fichiers sont enregistrés dans ce dossier, sans jamais écraser l'existant.",
                dest_row,
            )
        )

        self.conc_spin = QSpinBox()
        self.conc_spin.setRange(1, 16)
        self.conc_spin.setSuffix(" simultanés")
        layout.addWidget(
            self._row(
                "Téléchargements simultanés",
                "De 1 à 16 téléchargements en parallèle.",
                self.conc_spin,
            )
        )

        speed_row = QWidget()
        speed_layout = QHBoxLayout(speed_row)
        speed_layout.setContentsMargins(0, 0, 0, 0)
        speed_layout.setSpacing(6)
        self.speed_combo = QComboBox()
        for label, value in SPEED_PRESETS:
            self.speed_combo.addItem(label, value)
        self.custom_speed = QSpinBox()
        self.custom_speed.setRange(16, 1_000_000)
        self.custom_speed.setSuffix(" Ko/s")
        self.custom_speed.setSingleStep(100)
        self.custom_speed.hide()
        speed_layout.addWidget(self.speed_combo)
        speed_layout.addWidget(self.custom_speed)
        layout.addWidget(
            self._row(
                "Limite de vitesse",
                "Un plafond global partagé par tous les téléchargements.",
                speed_row,
            )
        )

        self.dup_combo = QComboBox()
        self.dup_combo.addItem("Demander confirmation", DuplicatePolicy.ASK.value)
        self.dup_combo.addItem("Ignorer automatiquement", DuplicatePolicy.SKIP.value)
        self.dup_combo.addItem("Renommer (« nom (2) »)", DuplicatePolicy.RENAME.value)
        layout.addWidget(
            self._row(
                "Fichier déjà présent",
                "Comportement lorsque le nom existe déjà dans le dossier.",
                self.dup_combo,
            )
        )

        browse.clicked.connect(self._browse_destination)
        open_btn.clicked.connect(
            lambda: self.window.safe_call(self.window.manager.open_downloads_folder)
        )
        self.conc_spin.valueChanged.connect(self._on_concurrency)
        self.speed_combo.currentIndexChanged.connect(lambda _i: self._on_speed())
        self.custom_speed.valueChanged.connect(lambda _v: self._on_speed())
        self.dup_combo.currentIndexChanged.connect(self._on_duplicate_policy)
        return card

    def _build_reliability(self) -> QWidget:
        card, layout = self._card()
        retry_row = QWidget()
        retry_layout = QHBoxLayout(retry_row)
        retry_layout.setContentsMargins(0, 0, 0, 0)
        retry_layout.setSpacing(10)
        self.auto_retry = QCheckBox("Activer la reprise automatique")
        self.retries_spin = QSpinBox()
        self.retries_spin.setRange(1, 10)
        self.retries_spin.setSuffix(" essais")
        retry_layout.addWidget(self.auto_retry)
        retry_layout.addWidget(self.retries_spin)
        layout.addWidget(
            self._row(
                "Coupures réseau",
                "OverLoad continue le fichier partiel et réessaie avec un délai croissant.",
                retry_row,
            )
        )
        self.auto_retry.toggled.connect(self._on_auto_retry)
        self.retries_spin.valueChanged.connect(self._on_retries)
        return card

    def _build_about(self) -> QWidget:
        card, layout = self._card()
        version = QLabel(f"OverLoad {__version__}")
        version.setObjectName("cardTitle")
        description = QLabel(
            "Gestionnaire de téléchargements et suite média pour Windows. "
            "Vos fichiers d'origine ne sont jamais modifiés."
        )
        description.setObjectName("mutedLabel")
        description.setWordWrap(True)
        layout.addWidget(version)
        layout.addWidget(description)
        layout.addWidget(_divider())
        actions = QHBoxLayout()
        data_btn = QPushButton("Ouvrir le dossier de données")
        data_btn.setObjectName("ghostBtn")
        project_btn = QPushButton("Projet GitHub")
        project_btn.setObjectName("ghostBtn")
        licence = QLabel("Licence MIT · © TOFazer")
        licence.setObjectName("tinyLabel")
        actions.addWidget(data_btn)
        actions.addWidget(project_btn)
        actions.addStretch()
        actions.addWidget(licence)
        layout.addLayout(actions)
        data_btn.clicked.connect(self.window.open_data_dir)
        project_btn.clicked.connect(lambda: webbrowser.open("https://github.com/TOFazer/OverLoad"))
        return card

    # ------------------------------------------------------------------
    # Synchronisation des contrôles
    # ------------------------------------------------------------------
    def refresh_from_prefs(self) -> None:
        prefs = self.window.settings_store.get()
        self._syncing = True
        try:
            self.theme_control.set_value(prefs.theme)
            self.scale_control.set_value(prefs.ui_scale)
            for key, swatch in self._swatches.items():
                swatch.setChecked(key == prefs.accent)
            self.dest_edit.setText(prefs.destination_dir)
            self.conc_spin.setValue(prefs.max_concurrent)
            preset_index = self.speed_combo.findData(prefs.speed_limit_bps or 0)
            if prefs.speed_limit_bps:
                if preset_index >= 0:
                    self.speed_combo.setCurrentIndex(preset_index)
                    self.custom_speed.hide()
                else:
                    self.custom_speed.setValue(max(16, prefs.speed_limit_bps // 1024))
                    self.speed_combo.setCurrentIndex(self.speed_combo.findData(-1))
                    self.custom_speed.show()
            else:
                self.speed_combo.setCurrentIndex(0)
                self.custom_speed.hide()
            index = self.dup_combo.findData(prefs.duplicate_policy)
            if index >= 0:
                self.dup_combo.setCurrentIndex(index)
            self.auto_retry.setChecked(prefs.auto_retry)
            self.retries_spin.setValue(max(1, prefs.max_retries))
            self.retries_spin.setEnabled(prefs.auto_retry)
        finally:
            self._syncing = False

    def _apply(self, **changes: str) -> None:
        if self._syncing:
            return
        self.window.set_appearance(**changes)

    def _set_accent(self, key: str) -> None:
        if self._syncing:
            return
        self.window.set_appearance(accent=key)

    def _browse_destination(self) -> None:
        current = self.window.settings_store.get().destination_dir
        folder = choose_directory(
            self, "Choisir le dossier de téléchargements", preferred=current
        )
        if not folder:
            return
        if self.window.apply_destination(folder):
            self.dest_edit.setText(folder)

    def _on_concurrency(self, value: int) -> None:
        if self._syncing:
            return
        self.window.safe_call(lambda: self.window.manager.set_max_concurrent(int(value)))
        self.window.settings_store.update(max_concurrent=int(value))

    def _on_speed(self) -> None:
        if self._syncing:
            return
        value = int(self.speed_combo.currentData())
        if value == -1:
            self.custom_speed.show()
            bps: int | None = self.custom_speed.value() * 1024
        else:
            self.custom_speed.hide()
            bps = value if value > 0 else None
        self.window.safe_call(lambda: self.window.manager.set_speed_limit_bps(bps))
        self.window.settings_store.update(speed_limit_bps=bps)

    def _on_duplicate_policy(self) -> None:
        if self._syncing:
            return
        policy = str(self.dup_combo.currentData())
        self.window.safe_call(lambda: self.window.manager.set_duplicate_policy(policy))
        self.window.settings_store.update(duplicate_policy=policy)

    def _on_auto_retry(self, checked: bool) -> None:
        if self._syncing:
            return
        self.retries_spin.setEnabled(checked)
        self.window.safe_call(
            lambda: self.window.manager.set_auto_retry(
                checked, max_retries=self.retries_spin.value()
            )
        )
        self.window.settings_store.update(auto_retry=checked)

    def _on_retries(self, value: int) -> None:
        if self._syncing:
            return
        self.window.safe_call(
            lambda: self.window.manager.set_auto_retry(
                self.auto_retry.isChecked(), max_retries=int(value)
            )
        )
        self.window.settings_store.update(max_retries=int(value))

    def refresh_theme(self) -> None:
        for swatch in self._swatches.values():
            swatch.refresh_theme(self.window.tokens)


class OverloadWindow(QMainWindow):
    """Fenêtre principale de l'application native."""

    def __init__(
        self,
        manager,
        history,
        settings_store,
        *,
        data_dir: Path | None = None,
    ) -> None:
        super().__init__()
        self.manager = manager
        self.history = history
        self.settings_store = settings_store
        self.data_dir = Path(data_dir) if data_dir is not None else default_data_dir()
        prefs = settings_store.get()
        self.tokens = apply_appearance(
            QApplication.instance(), prefs.theme, prefs.accent, prefs.ui_scale
        )
        self.scale = scale_factor(prefs.ui_scale)
        self.thumbnails = ThumbnailService(self.data_dir, self)
        self._cards: dict[str, DownloadCard] = {}
        self._history_rows: list[HistoryRow] = []
        self._recent_rows: list[ActivityRow] = []
        self._queue_rows: list[QueueRow] = []
        self._themed: list[Any] = []
        self._section_labels: list[QLabel] = []
        self._brand_labels: list[QLabel] = []
        self._nav_buttons: dict[str, NavButton] = {}
        self._pages: dict[str, QWidget] = {}
        self._page_meta = PAGE_META
        self._current_page = ""
        self._search = ""
        self._compact: bool | None = None
        self._stats_columns = 4
        self._active_filter = "all"
        self._history_filter = "all"
        self._last_history_at = 0.0
        self._history_all: list = []
        self._history_counts = {"completed": 0, "failed": 0, "today": 0}
        self._recent_sig: tuple | None = None
        self._queue_sig: tuple | None = None
        self._history_sig: tuple | None = None
        self._disk_free: str = "—"
        self._disk_at = 0.0
        self._last_overview: dict[str, Any] = {}
        self._fade: QPropertyAnimation | None = None
        self._media_cache: dict[str, dict[str, Any]] = {}
        self._probe_url: str | None = None
        self._probe = _MediaProbe(manager, self)
        self._probe.done.connect(self._on_media_info)
        self._composer_busy = False
        self.async_timeout_ms = 30_000
        self._library_root: Path | None = None
        self._library_scan: LibraryScan | None = None
        self._library_rows: list[LibraryRow] = []
        self._library_filter = "all"
        self._library_sort = "recent"
        self._library_scanning = False
        self._library_dirty = True
        self._library_probe = _LibraryProbe(self)
        self._library_probe.done.connect(self._on_library_scan)
        self._tool_cards: list[ToolCard] = []

        self.setWindowTitle("OverLoad — Media Manager")
        self.setWindowIcon(build_app_icon())
        self.resize(1280, 860)
        self.setMinimumSize(1000, 680)

        self._build_ui()
        self._wire_shortcuts()
        self._timer = QTimer(self)
        self._timer.setInterval(250)
        self._timer.timeout.connect(self.refresh_all)
        self._timer.start()
        self.maybe_reload_history(force=True)
        self.refresh_all()
        self.go_to("home", focus=False)

    # ------------------------------------------------------------------
    # Construction de l'interface
    # ------------------------------------------------------------------
    def _build_ui(self) -> None:
        root = QWidget()
        root.setObjectName("rootWidget")
        root.setMouseTracking(True)
        root_layout = QHBoxLayout(root)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)
        root_layout.addWidget(self._build_sidebar())

        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(0)
        content_layout.addWidget(self._build_topbar())

        self.stack = QStackedWidget()
        self.stack.setObjectName("pageHost")
        content_layout.addWidget(self.stack, 1)
        root_layout.addWidget(content, 1)
        self.setCentralWidget(root)

        self._add_page("home", self._build_home_page())
        self._add_page("downloads", self._build_downloads_page())
        self._add_page("library", self._build_library_page())
        self._add_page("creators", self._build_creators_page())
        self._add_page("history", self._build_history_page())
        self._add_page("settings", SettingsPage(self))
        self._add_page("help", self._build_help_page())
        self.toast_widget = Toast(root, self.tokens)

    def _build_sidebar(self) -> QFrame:
        self.sidebar = QFrame()
        self.sidebar.setObjectName("sidebar")
        self.sidebar.setFixedWidth(round(252 * self.scale))
        layout = QVBoxLayout(self.sidebar)
        layout.setContentsMargins(14, 18, 14, 14)
        layout.setSpacing(6)

        self.logo_row = QWidget()
        logo_layout = QHBoxLayout(self.logo_row)
        logo_layout.setContentsMargins(6, 0, 6, 0)
        logo_layout.setSpacing(10)
        self.logo = LogoBadge(self.tokens, 40)
        logo_layout.addWidget(self.logo)
        brand = QVBoxLayout()
        brand.setSpacing(0)
        brand_title = QLabel("OverLoad")
        brand_title.setObjectName("brandTitle")
        brand_subtitle = QLabel("MEDIA MANAGER")
        brand_subtitle.setObjectName("brandSubtitle")
        brand.addWidget(brand_title)
        brand.addWidget(brand_subtitle)
        logo_layout.addLayout(brand)
        logo_layout.addStretch()
        self._brand_labels.extend([brand_title, brand_subtitle])
        layout.addWidget(self.logo_row)
        layout.addSpacing(20)

        principal = QLabel("PRINCIPAL")
        principal.setObjectName("navSectionLabel")
        self._section_labels.append(principal)
        layout.addWidget(principal)
        for key, label, icon_name in (
            ("home", "Accueil", "home"),
            ("downloads", "Téléchargements", "download"),
            ("library", "Bibliothèque", "library"),
            ("creators", "Créateurs", "film"),
            ("history", "Historique", "history"),
        ):
            self._add_nav(layout, key, label, icon_name)
        layout.addSpacing(16)

        app_section = QLabel("APPLICATION")
        app_section.setObjectName("navSectionLabel")
        self._section_labels.append(app_section)
        layout.addWidget(app_section)
        for key, label, icon_name in (
            ("settings", "Paramètres", "sliders"),
            ("help", "Aide", "help"),
        ):
            self._add_nav(layout, key, label, icon_name)
        layout.addStretch()

        self.sidebar_status = QFrame()
        self.sidebar_status.setObjectName("innerCard")
        status_layout = QVBoxLayout(self.sidebar_status)
        status_layout.setContentsMargins(12, 10, 12, 10)
        status_layout.setSpacing(3)
        caption = QLabel("DÉBIT GLOBAL")
        caption.setObjectName("statCaption")
        self.sidebar_speed = QLabel("0 o/s")
        self.sidebar_speed.setObjectName("cardTitle")
        self.sidebar_queue = QLabel("Aucune activité")
        self.sidebar_queue.setObjectName("tinyLabel")
        self.sidebar_spark = Sparkline(self.tokens, width=120, height=28)
        status_layout.addWidget(caption)
        status_layout.addWidget(self.sidebar_speed)
        status_layout.addWidget(self.sidebar_spark)
        status_layout.addWidget(self.sidebar_queue)
        layout.addWidget(self.sidebar_status)
        layout.addSpacing(8)
        self.version_label = QLabel(f"OverLoad {__version__}")
        self.version_label.setObjectName("versionLabel")
        self.version_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.version_label)
        return self.sidebar

    def _add_nav(self, layout: QVBoxLayout, key: str, label: str, icon_name: str) -> None:
        button = NavButton(key, label, icon_name, self.tokens, scale=self.scale)
        button.clicked.connect(lambda _checked=False, k=key: self.go_to(k))
        layout.addWidget(button)
        self._nav_buttons[key] = button
        self._themed.append(button)

    def _build_topbar(self) -> QFrame:
        topbar = QFrame()
        self.topbar = topbar
        topbar.setObjectName("topBar")
        topbar.setFixedHeight(round(78 * self.scale))
        layout = QHBoxLayout(topbar)
        layout.setContentsMargins(26, 12, 22, 12)
        layout.setSpacing(12)

        self.page_badge = GlyphBadge("home", self.tokens, size=38, radius=12, icon_size=20)
        layout.addWidget(self.page_badge)
        titles = QVBoxLayout()
        titles.setSpacing(1)
        self.page_title = QLabel("Accueil")
        self.page_title.setObjectName("pageTitle")
        self.page_subtitle = QLabel("Votre espace, prêt en un clic.")
        self.page_subtitle.setObjectName("pageSubtitle")
        titles.addWidget(self.page_title)
        titles.addWidget(self.page_subtitle)
        layout.addLayout(titles)
        layout.addStretch()

        self.search_edit = QLineEdit()
        self.search_edit.setObjectName("searchField")
        self.search_edit.setPlaceholderText("Rechercher un téléchargement…")
        self.search_edit.setClearButtonEnabled(True)
        self.search_edit.setFixedHeight(round(36 * self.scale))
        self.search_edit.setFixedWidth(round(262 * self.scale))
        self._search_icon = icons.icon("search", self.tokens.text_muted, 16)
        self._search_action = self.search_edit.addAction(
            self._search_icon, QLineEdit.ActionPosition.LeadingPosition
        )
        self._search_action.setToolTip("Rechercher")
        self.search_edit.textChanged.connect(self._on_search)
        layout.addWidget(self.search_edit)

        self.new_btn = QPushButton("Télécharger")
        self.new_btn.setObjectName("primaryBtn")
        self.new_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.new_btn.setIcon(icons.icon("download", self.tokens.accent_ink, 16, 2.0))
        self.new_btn.setIconSize(QSize(16, 16))
        self.new_btn.setFixedHeight(round(36 * self.scale))
        self.new_btn.clicked.connect(self.focus_composer)
        layout.addWidget(self.new_btn)

        self.theme_btn = IconButton(
            "sun" if self.tokens.dark else "moon",
            "Basculer entre le thème sombre et clair",
            self.tokens,
            size=round(36 * self.scale),
        )
        self.theme_btn.clicked.connect(self.toggle_theme)
        layout.addWidget(self.theme_btn)

        self.settings_btn = IconButton(
            "sliders", "Paramètres", self.tokens, size=round(36 * self.scale)
        )
        self.settings_btn.clicked.connect(lambda: self.go_to("settings"))
        layout.addWidget(self.settings_btn)
        self._themed.extend([self.theme_btn, self.settings_btn])
        return topbar

    def _add_page(self, key: str, widget: QWidget) -> None:
        self._pages[key] = widget
        self.stack.addWidget(widget)

    def _scroll_page(self) -> tuple[QScrollArea, QVBoxLayout]:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        content = QWidget()
        scroll.setWidget(content)
        layout = QVBoxLayout(content)
        layout.setContentsMargins(26, 20, 26, 26)
        layout.setSpacing(16)
        return scroll, layout

    # ------------------------------------------------------------------
    # Accueil
    # ------------------------------------------------------------------
    def _build_home_page(self) -> QWidget:
        scroll, layout = self._scroll_page()

        hero = QFrame()
        hero.setObjectName("heroCard")
        hero_layout = QVBoxLayout(hero)
        hero_layout.setContentsMargins(24, 22, 24, 22)
        hero_layout.setSpacing(14)

        header_row = QHBoxLayout()
        header_row.setSpacing(18)
        welcome = QVBoxLayout()
        welcome.setSpacing(4)
        eyebrow = QLabel("BIENVENUE DANS OVERLOAD")
        eyebrow.setObjectName("heroEyebrow")
        welcome.addWidget(eyebrow)
        self.hero_title = QLabel()
        self.hero_title.setObjectName("heroTitle")
        self.hero_title.setTextFormat(Qt.TextFormat.RichText)
        welcome.addWidget(self.hero_title)
        self.hero_subtitle = QLabel(
            "Téléchargez et organisez vos médias simplement — puis retrouvez-les "
            "dans la bibliothèque et préparez vos projets sans risquer vos originaux."
        )
        self.hero_subtitle.setObjectName("heroSubtitle")
        self.hero_subtitle.setWordWrap(True)
        welcome.addWidget(self.hero_subtitle)
        header_row.addLayout(welcome, 1)
        self.hero_art = HeroArt(self.tokens, 110)
        header_row.addWidget(self.hero_art, 0, Qt.AlignmentFlag.AlignVCenter)
        self._themed.append(self.hero_art)
        hero_layout.addLayout(header_row)
        hero_layout.addWidget(_divider())

        composer_title = QLabel("Nouveau téléchargement")
        composer_title.setObjectName("sectionTitle")
        hero_layout.addWidget(composer_title)

        def step_card(number: int, title: str, hint: str):
            card = QFrame()
            card.setObjectName("stepCard")
            card_layout = QVBoxLayout(card)
            card_layout.setContentsMargins(14, 12, 14, 12)
            card_layout.setSpacing(9)
            head = QHBoxLayout()
            head.setSpacing(9)
            badge = StepBadge(number, self.tokens, size=round(26 * self.scale))
            self._themed.append(badge)
            head.addWidget(badge, 0, Qt.AlignmentFlag.AlignVCenter)
            texts = QVBoxLayout()
            texts.setSpacing(1)
            title_lbl = QLabel(title)
            title_lbl.setObjectName("stepTitle")
            texts.addWidget(title_lbl)
            hint_lbl = QLabel(hint)
            hint_lbl.setObjectName("stepHint")
            hint_lbl.setWordWrap(True)
            texts.addWidget(hint_lbl)
            head.addLayout(texts, 1)
            card_layout.addLayout(head)
            hero_layout.addWidget(card)
            return card_layout, badge

        # Étape 1 — coller un lien.
        step1_layout, self.step_link_badge = step_card(
            1,
            "Collez un lien",
            "Vidéo YouTube publique ou adresse HTTP(S) directe vers un fichier. "
            "Les vidéos privées, payantes ou protégées ne sont pas prises en charge.",
        )
        composer = QHBoxLayout()
        composer.setSpacing(9)
        self.url_edit = QLineEdit()
        self.url_edit.setObjectName("urlField")
        self.url_edit.setPlaceholderText(
            "Collez un lien YouTube (youtube.com/watch?v=…, youtu.be/…) ou un fichier direct"
        )
        self.url_edit.setMinimumHeight(round(48 * self.scale))
        self.url_edit.addAction(
            icons.icon("link", self.tokens.text_muted, 17), QLineEdit.ActionPosition.LeadingPosition
        )
        self._paste_action = QAction(
            icons.icon("copy", self.tokens.text_muted, 16), "Coller depuis le presse-papiers", self
        )
        self._paste_action.triggered.connect(self.paste_clipboard)
        self.url_edit.addAction(self._paste_action, QLineEdit.ActionPosition.TrailingPosition)
        self.url_edit.textChanged.connect(self._schedule_validation)
        self.url_edit.returnPressed.connect(self.download_from_composer)
        composer.addWidget(self.url_edit, 1)
        self.paste_btn = QPushButton("Coller")
        self.paste_btn.setObjectName("secondaryBtn")
        self.paste_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.paste_btn.setMinimumHeight(round(48 * self.scale))
        self.paste_btn.setIcon(icons.icon("clipboard", self.tokens.accent_text, 16))
        self.paste_btn.setToolTip("Coller le lien depuis le presse-papiers")
        self.paste_btn.clicked.connect(self.paste_clipboard)
        composer.addWidget(self.paste_btn)
        step1_layout.addLayout(composer)
        self.url_hint = QLabel(
            "Liens YouTube publics et fichiers HTTP(S) directs pris en charge."
        )
        self.url_hint.setObjectName("mutedLabel")
        self.url_hint.setWordWrap(True)
        step1_layout.addWidget(self.url_hint)

        # Étape 2 — les options utiles.
        step2_layout, _step2_badge = step_card(
            2,
            "Choisissez les options utiles",
            "Uniquement ce qui change quelque chose pour ce téléchargement.",
        )
        options = QHBoxLayout()
        options.setSpacing(16)
        dest_col = QVBoxLayout()
        dest_col.setSpacing(5)
        dest_title = QLabel("Dossier de destination")
        dest_title.setObjectName("fieldLabel")
        dest_col.addWidget(dest_title)
        dest_row = QHBoxLayout()
        dest_row.setSpacing(7)
        folder_icon = QLabel()
        folder_icon.setPixmap(icons.pixmap("folder", self.tokens.text_muted, 14))
        self.dest_label = ElidedLabel(str(self.manager.settings().destination_dir))
        self.dest_label.setObjectName("tinyLabel")
        change_dest = QPushButton("Modifier")
        change_dest.setObjectName("linkBtn")
        change_dest.setCursor(Qt.CursorShape.PointingHandCursor)
        change_dest.clicked.connect(self.choose_destination)
        open_dest = QPushButton("Ouvrir")
        open_dest.setObjectName("linkBtn")
        open_dest.setCursor(Qt.CursorShape.PointingHandCursor)
        open_dest.clicked.connect(lambda: self.safe_call(self.manager.open_downloads_folder))
        dest_row.addWidget(folder_icon)
        dest_row.addWidget(self.dest_label, 1)
        dest_row.addWidget(change_dest)
        dest_row.addWidget(open_dest)
        dest_col.addLayout(dest_row)
        dest_note = QLabel("Le fichier terminé apparaîtra aussi dans la Bibliothèque.")
        dest_note.setObjectName("tinyLabel")
        dest_col.addWidget(dest_note)
        options.addLayout(dest_col, 3)

        quality_col = QVBoxLayout()
        quality_col.setSpacing(5)
        quality_title = QLabel("Qualité vidéo (YouTube uniquement)")
        quality_title.setObjectName("fieldLabel")
        quality_col.addWidget(quality_title)
        self.quality_combo = QComboBox()
        for value, label in QUALITY_CHOICES:
            self.quality_combo.addItem(label, value)
        self.quality_combo.setMinimumHeight(round(38 * self.scale))
        self.quality_combo.setToolTip(
            "Qualité de la vidéo YouTube. Ignorée pour les fichiers directs, "
            "déjà fournis tels quels par le serveur."
        )
        quality_col.addWidget(self.quality_combo)
        quality_note = QLabel("Sans effet sur les fichiers directs.")
        quality_note.setObjectName("tinyLabel")
        quality_col.addWidget(quality_note)
        options.addLayout(quality_col, 2)
        step2_layout.addLayout(options)
        self.batch_link = QPushButton("Ou télécharger plusieurs liens d'un coup (lot)")
        self.batch_link.setObjectName("linkBtn")
        self.batch_link.setCursor(Qt.CursorShape.PointingHandCursor)
        self.batch_link.clicked.connect(self.open_batch_dialog)
        step2_layout.addWidget(self.batch_link, 0, Qt.AlignmentFlag.AlignLeft)

        # Étape 3 — lancer, avec une progression honnête.
        step3_layout, _step3_badge = step_card(
            3,
            "Lancez le téléchargement",
            "La progression reflète les octets réellement écrits : « Terminé » "
            "signifie fichier complet et vérifié, jamais un 100 % anticipé.",
        )
        launch_row = QHBoxLayout()
        launch_row.setSpacing(10)
        follow_hint = QLabel(
            "Suivi en détail (vitesse, temps restant, pause/reprise) "
            "dans la page Téléchargements."
        )
        follow_hint.setObjectName("mutedLabel")
        follow_hint.setWordWrap(True)
        launch_row.addWidget(follow_hint, 1)
        self.download_btn = QPushButton("Télécharger")
        self.download_btn.setObjectName("primaryBtn")
        self.download_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.download_btn.setMinimumHeight(round(48 * self.scale))
        self.download_btn.setMinimumWidth(round(190 * self.scale))
        self.download_btn.setIcon(icons.icon("download", self.tokens.accent_ink, 18, 2.0))
        self.download_btn.setIconSize(QSize(18, 18))
        self.download_btn.clicked.connect(self.download_from_composer)
        launch_row.addWidget(self.download_btn)
        step3_layout.addLayout(launch_row)
        layout.addWidget(hero)

        stats = QWidget()
        self.stats_grid = QGridLayout(stats)
        self.stats_grid.setContentsMargins(0, 0, 0, 0)
        self.stats_grid.setHorizontalSpacing(10)
        self.stats_grid.setVerticalSpacing(10)
        self.stat_speed = StatCard(
            "Vitesse globale", "0 o/s", "Aucun transfert", "gauge", self.tokens
        )
        self.stat_active = StatCard(
            "File active", "0 / 3", "Rien en attente", "download", self.tokens, tone="info"
        )
        self.stat_done = StatCard(
            "Terminés", "0", "aujourd'hui", "check", self.tokens, tone="success"
        )
        self.stat_disk = StatCard(
            "Espace libre", "—", "sur le disque", "hard-drive", self.tokens, tone="warning"
        )
        self._stat_cards = [self.stat_speed, self.stat_active, self.stat_done, self.stat_disk]
        for index, card in enumerate(self._stat_cards):
            self.stats_grid.addWidget(card, 0, index)
        layout.addWidget(stats)
        self._themed.extend(self._stat_cards)

        bottom = QHBoxLayout()
        bottom.setSpacing(16)
        recent_card = QFrame()
        recent_card.setObjectName("panelCard")
        recent_layout = QVBoxLayout(recent_card)
        recent_layout.setContentsMargins(18, 16, 18, 16)
        recent_layout.setSpacing(9)
        header = QHBoxLayout()
        recent_title = QLabel("Activité récente")
        recent_title.setObjectName("sectionTitle")
        see_all = QPushButton("Tout l'historique")
        see_all.setObjectName("linkBtn")
        see_all.setCursor(Qt.CursorShape.PointingHandCursor)
        see_all.clicked.connect(lambda: self.go_to("history"))
        header.addWidget(recent_title)
        header.addStretch()
        header.addWidget(see_all)
        recent_layout.addLayout(header)
        self.recent_host = QWidget()
        self.recent_list = QVBoxLayout(self.recent_host)
        self.recent_list.setContentsMargins(0, 0, 0, 0)
        self.recent_list.setSpacing(6)
        self.recent_list.addStretch()
        recent_layout.addWidget(self.recent_host, 1)
        self.recent_empty = QLabel(
            "Tes derniers fichiers apparaîtront ici, avec leur miniature et leur statut."
        )
        self.recent_empty.setObjectName("mutedLabel")
        self.recent_empty.setWordWrap(True)
        recent_layout.addWidget(self.recent_empty)
        bottom.addWidget(recent_card, 3)

        right = QVBoxLayout()
        right.setSpacing(14)
        queue_card = QFrame()
        queue_card.setObjectName("panelCard")
        queue_layout = QVBoxLayout(queue_card)
        queue_layout.setContentsMargins(16, 14, 16, 14)
        queue_layout.setSpacing(7)
        queue_header = QHBoxLayout()
        queue_title = QLabel("File d'attente")
        queue_title.setObjectName("sectionTitle")
        queue_link = QPushButton("Gérer")
        queue_link.setObjectName("linkBtn")
        queue_link.setCursor(Qt.CursorShape.PointingHandCursor)
        queue_link.clicked.connect(lambda: self.go_to("downloads"))
        queue_header.addWidget(queue_title)
        queue_header.addStretch()
        queue_header.addWidget(queue_link)
        queue_layout.addLayout(queue_header)
        queue_sub = QLabel("En cours, en pause et à venir")
        queue_sub.setObjectName("tinyLabel")
        queue_layout.addWidget(queue_sub)
        self.queue_host = QWidget()
        self.queue_list = QVBoxLayout(self.queue_host)
        self.queue_list.setContentsMargins(0, 0, 0, 0)
        self.queue_list.setSpacing(7)
        self.queue_list.addStretch()
        queue_layout.addWidget(self.queue_host)
        self.queue_empty = QLabel("Aucun téléchargement en cours.")
        self.queue_empty.setObjectName("mutedLabel")
        self.queue_empty.setWordWrap(True)
        self.queue_empty.setMinimumHeight(46)
        queue_layout.addWidget(self.queue_empty)
        right.addWidget(queue_card)

        library_card = ToolCard(
            "library",
            "Bibliothèque",
            "Retrouvez et ouvrez vos fichiers locaux en un clic.",
            "Vidéos · audio · images · sous-titres",
            self.tokens,
            on_click=lambda: self.go_to("library"),
            scale=self.scale,
        )
        library_card.setMinimumHeight(round(96 * self.scale))
        creators_card = ToolCard(
            "film",
            "Espace Créateurs",
            "Préparez un projet de montage propre, sans toucher aux originaux.",
            "Projets · analyse · sous-titres · renommage",
            self.tokens,
            on_click=lambda: self.go_to("creators"),
            scale=self.scale,
        )
        creators_card.setMinimumHeight(round(96 * self.scale))
        self._tool_cards.extend([library_card, creators_card])
        self._themed.extend([library_card, creators_card])
        right.addWidget(library_card)
        right.addWidget(creators_card)
        right.addStretch()
        bottom.addLayout(right, 2)
        layout.addLayout(bottom)
        layout.addStretch()
        self._themed.extend([self.logo, self.sidebar_spark])
        return scroll

    # ------------------------------------------------------------------
    # Téléchargements
    # ------------------------------------------------------------------
    def _build_downloads_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(26, 18, 26, 22)
        layout.setSpacing(12)

        toolbar = QHBoxLayout()
        toolbar.setSpacing(8)
        self.downloads_summary = QLabel("Aucune tâche pour le moment.")
        self.downloads_summary.setObjectName("cardTitle")
        toolbar.addWidget(self.downloads_summary)
        toolbar.addStretch()
        self.pause_all_btn = IconButton("pause", "Tout suspendre", self.tokens)
        self.resume_all_btn = IconButton("play", "Tout reprendre", self.tokens)
        self.clear_done_btn = IconButton("trash", "Nettoyer les terminés", self.tokens)
        self.pause_all_btn.clicked.connect(lambda: self.safe_call(self.manager.pause_all))
        self.resume_all_btn.clicked.connect(lambda: self.safe_call(self.manager.resume_all))
        self.clear_done_btn.clicked.connect(
            lambda: (
                self.manager.clear_finished(),
                self.toast("Liste nettoyée — les fichiers sont conservés."),
            )
        )
        self.batch_btn = QPushButton("Lot de liens")
        self.batch_btn.setObjectName("secondaryBtn")
        self.batch_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.batch_btn.setIcon(icons.icon("list", self.tokens.accent_text, 16))
        self.batch_btn.clicked.connect(self.open_batch_dialog)
        self.history_link_btn = QPushButton("Historique")
        self.history_link_btn.setObjectName("ghostBtn")
        self.history_link_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.history_link_btn.setIcon(icons.icon("history", self.tokens.text_secondary, 16))
        self.history_link_btn.clicked.connect(lambda: self.go_to("history"))
        toolbar.addWidget(self.pause_all_btn)
        toolbar.addWidget(self.resume_all_btn)
        toolbar.addWidget(self.clear_done_btn)
        toolbar.addWidget(self.batch_btn)
        toolbar.addWidget(self.history_link_btn)
        self._themed.extend([self.pause_all_btn, self.resume_all_btn, self.clear_done_btn])
        layout.addLayout(toolbar)

        filters_row = QHBoxLayout()
        self.filters = SegmentedControl(
            [
                ("all", "Tous"),
                ("running", "En cours"),
                ("queued", "En attente"),
                ("paused", "En pause"),
                ("failed", "Problèmes"),
            ],
            self.tokens,
        )
        self.filters.value_changed.connect(self._set_filter)
        filters_row.addWidget(self.filters)
        filters_row.addStretch()
        self.active_count = QLabel("")
        self.active_count.setObjectName("mutedLabel")
        filters_row.addWidget(self.active_count)
        layout.addLayout(filters_row)

        honesty = QLabel(
            "Chaque carte indique un statut explicite et ses actions (pause, reprise, "
            "relance, annulation, ouverture du fichier ou du dossier). La progression "
            "reflète les données réelles du moteur : 100 % = terminé et vérifié."
        )
        honesty.setObjectName("tinyLabel")
        honesty.setWordWrap(True)
        layout.addWidget(honesty)

        active_scroll = QScrollArea()
        active_scroll.setWidgetResizable(True)
        active_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        active_host = QWidget()
        active_scroll.setWidget(active_host)
        self.active_list = QVBoxLayout(active_host)
        self.active_list.setContentsMargins(0, 0, 4, 0)
        self.active_list.setSpacing(8)
        self.active_empty = EmptyState(
            self.tokens,
            "download",
            "Aucun téléchargement en cours",
            "Collez un lien depuis l'accueil pour démarrer votre premier téléchargement.",
            action_text="Coller un lien",
            on_action=self.focus_composer,
        )
        self.active_list.addWidget(self.active_empty)
        self.active_list.addStretch()
        self._themed.append(self.active_empty)
        layout.addWidget(active_scroll, 1)
        return page

    # ------------------------------------------------------------------
    # Historique
    # ------------------------------------------------------------------
    def _build_history_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(26, 18, 26, 22)
        layout.setSpacing(12)

        toolbar = QHBoxLayout()
        toolbar.setSpacing(8)
        self.history_summary = QLabel("Aucun téléchargement passé pour le moment.")
        self.history_summary.setObjectName("cardTitle")
        toolbar.addWidget(self.history_summary)
        toolbar.addStretch()
        self.history_status = QComboBox()
        self.history_status.addItem("Toutes les entrées", "all")
        self.history_status.addItem("Terminés", "completed")
        self.history_status.addItem("Interrompus", "failed")
        self.history_status.addItem("Annulés", "cancelled")
        self.history_status.currentIndexChanged.connect(self._set_history_filter)
        toolbar.addWidget(self.history_status)
        self.history_count = QLabel("")
        self.history_count.setObjectName("mutedLabel")
        toolbar.addWidget(self.history_count)
        self.clear_history_btn = QPushButton("Effacer l'historique")
        self.clear_history_btn.setObjectName("ghostBtn")
        self.clear_history_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.clear_history_btn.clicked.connect(self._clear_history)
        toolbar.addWidget(self.clear_history_btn)
        layout.addLayout(toolbar)

        note = QLabel(
            "La présence réelle de chaque fichier est revérifiée sur le disque. "
            "Effacer l'historique ne supprime jamais vos fichiers."
        )
        note.setObjectName("tinyLabel")
        note.setWordWrap(True)
        layout.addWidget(note)

        history_scroll = QScrollArea()
        history_scroll.setWidgetResizable(True)
        history_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        history_host = QWidget()
        history_scroll.setWidget(history_host)
        self.history_list = QVBoxLayout(history_host)
        self.history_list.setContentsMargins(0, 0, 4, 0)
        self.history_list.setSpacing(6)
        self.history_empty = EmptyState(
            self.tokens,
            "history",
            "Historique vide",
            "Les téléchargements terminés ou interrompus seront conservés ici, "
            "même après la fermeture d'OverLoad.",
        )
        self.history_list.addWidget(self.history_empty)
        self.history_list.addStretch()
        self._themed.append(self.history_empty)
        layout.addWidget(history_scroll, 1)
        return page

    # ------------------------------------------------------------------
    # Bibliothèque
    # ------------------------------------------------------------------
    def _build_library_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(26, 18, 26, 22)
        layout.setSpacing(12)

        toolbar = QHBoxLayout()
        toolbar.setSpacing(8)
        folder_icon = QLabel()
        folder_icon.setPixmap(icons.pixmap("folder", self.tokens.text_muted, 16))
        toolbar.addWidget(folder_icon)
        self.library_root_label = ElidedLabel("")
        self.library_root_label.setObjectName("cardTitle")
        toolbar.addWidget(self.library_root_label, 1)
        self.library_browse_btn = QPushButton("Parcourir un autre dossier…")
        self.library_browse_btn.setObjectName("ghostBtn")
        self.library_browse_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.library_browse_btn.clicked.connect(self.choose_library_folder)
        toolbar.addWidget(self.library_browse_btn)
        self.library_refresh_btn = IconButton(
            "refresh", "Réanalyser le dossier", self.tokens
        )
        self.library_refresh_btn.clicked.connect(lambda: self.refresh_library(force=True))
        toolbar.addWidget(self.library_refresh_btn)
        self.library_open_btn = IconButton(
            "external", "Ouvrir le dossier dans l'Explorateur", self.tokens
        )
        self.library_open_btn.clicked.connect(
            lambda: self.safe_call(lambda: open_folder(self._library_current_root()))
        )
        toolbar.addWidget(self.library_open_btn)
        self._themed.extend([self.library_refresh_btn, self.library_open_btn])
        layout.addLayout(toolbar)

        self.library_stats = QLabel("Analyse du dossier en cours…")
        self.library_stats.setObjectName("mutedLabel")
        layout.addWidget(self.library_stats)

        filters_row = QHBoxLayout()
        filters_row.setSpacing(8)
        self.library_filters = SegmentedControl(KIND_FILTERS, self.tokens)
        self.library_filters.value_changed.connect(self._set_library_filter)
        filters_row.addWidget(self.library_filters)
        filters_row.addStretch()
        sort_label = QLabel("Trier :")
        sort_label.setObjectName("fieldLabel")
        filters_row.addWidget(sort_label)
        self.library_sort_combo = QComboBox()
        for value, label in SORTS:
            self.library_sort_combo.addItem(label, value)
        self.library_sort_combo.currentIndexChanged.connect(self._set_library_sort)
        filters_row.addWidget(self.library_sort_combo)
        layout.addLayout(filters_row)

        library_scroll = QScrollArea()
        library_scroll.setWidgetResizable(True)
        library_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        library_host = QWidget()
        library_scroll.setWidget(library_host)
        self.library_list = QVBoxLayout(library_host)
        self.library_list.setContentsMargins(0, 0, 4, 0)
        self.library_list.setSpacing(6)
        self.library_empty = EmptyState(
            self.tokens,
            "library",
            "Bibliothèque vide",
            "Téléchargez un premier fichier depuis l'accueil, ou parcourez "
            "un dossier qui contient déjà vos médias.",
            action_text="Nouveau téléchargement",
            on_action=self.focus_composer,
        )
        self.library_list.addWidget(self.library_empty)
        self.library_list.addStretch()
        self._themed.append(self.library_empty)
        layout.addWidget(library_scroll, 1)

        self.library_more = QLabel("")
        self.library_more.setObjectName("tinyLabel")
        self.library_more.setWordWrap(True)
        layout.addWidget(self.library_more)
        return page

    def _library_current_root(self) -> Path:
        if self._library_root is not None:
            return self._library_root
        return Path(self.manager.settings().destination_dir)

    def choose_library_folder(self) -> None:
        folder = choose_directory(
            self, "Dossier à afficher dans la bibliothèque", preferred=self._library_current_root()
        )
        if folder:
            self._library_root = Path(folder)
            self._library_dirty = True
            self.refresh_library(force=True)

    def refresh_library(self, *, force: bool = False) -> None:
        """(Ré)indexe le dossier de la bibliothèque en arrière-plan si nécessaire."""
        root = self._library_current_root()
        self.library_root_label.setText(str(root))
        if self._library_scanning:
            return
        if not force and not self._library_dirty and self._library_scan is not None:
            if self._library_scan.root == root:
                return
        self._library_scanning = True
        self._library_dirty = False
        self.library_stats.setText("Analyse du dossier en cours…")
        self._library_probe.start(root)

    def _on_library_scan(self, scan: object, error: object) -> None:
        self._library_scanning = False
        if error or not isinstance(scan, LibraryScan):
            self.library_stats.setText(f"Analyse impossible : {error}")
            self._library_scan = None
            self._render_library()
            return
        self._library_scan = scan
        self._render_library()

    def _set_library_filter(self, value: str) -> None:
        self._library_filter = value
        self._render_library()

    def _set_library_sort(self, _index: int) -> None:
        self._library_sort = str(self.library_sort_combo.currentData())
        self._render_library()

    def _render_library(self) -> None:
        scan = self._library_scan
        _clear_rows(self.library_list)
        self._library_rows = []
        if scan is None:
            self.library_empty.set_texts(
                "Dossier illisible",
                "Impossible d'analyser ce dossier. Vérifiez qu'il existe encore "
                "ou parcourez-en un autre.",
                "Nouveau téléchargement",
            )
            self.library_empty.show()
            self.library_more.setText("")
            return
        counts = scan.counts()
        total = len(scan.files)
        label_by_kind = dict(KIND_FILTERS)
        parts = [
            f"{counts[k]} {label_by_kind.get(k, k).lower()}"
            for k in ("video", "audio", "image", "subtitle")
            if counts.get(k)
        ]
        self.library_stats.setText(
            f"{total} fichier(s) · {format_bytes(scan.total_size)} au total"
            + (f" — {' · '.join(parts)}" if parts else "")
        )
        query = self._search if self._current_page == "library" else ""
        visible = filter_files(
            scan.files, kind=self._library_filter, query=query, sort=self._library_sort
        )
        sources = {
            entry.destination_path: entry.url for entry in self._history_all if entry.url
        }
        shown = visible[:300]
        for index, item in enumerate(shown):
            row = LibraryRow(
                item,
                self.tokens,
                self.thumbnails,
                source_url=sources.get(str(item.path), ""),
                on_open_file=lambda target: self.safe_call(lambda: open_file(target.path)),
                on_open_folder=lambda target: self.safe_call(lambda: open_folder(target.path)),
                on_analyze=lambda target: self.analyze_path(target.path),
                scale=self.scale,
            )
            self.library_list.insertWidget(index, row)
            self._library_rows.append(row)
        self.library_empty.setVisible(not visible)
        if total and not visible:
            self.library_empty.set_texts(
                "Aucun résultat",
                "Aucun fichier ne correspond à ce type ou à votre recherche "
                "dans ce dossier.",
            )
        else:
            self.library_empty.set_texts(
                "Bibliothèque vide",
                "Téléchargez un premier fichier depuis l'accueil, ou parcourez "
                "un dossier qui contient déjà vos médias.",
                "Nouveau téléchargement",
            )
        notes = []
        if len(visible) > len(shown):
            notes.append(
                f"{len(shown)} fichiers affichés sur {len(visible)}"
                " — affinez le filtre ou la recherche."
            )
        if scan.truncated:
            notes.append("Dossier très volumineux : seuls les premiers fichiers sont indexés.")
        if scan.unreadable:
            notes.append(f"{scan.unreadable} fichier(s) illisible(s) ignoré(s).")
        self.library_more.setText(" ".join(notes))

    def analyze_path(self, path: Path | str) -> None:
        """Ouvre l'analyse de fichier des Créateurs sur le fichier demandé."""
        self.go_to("creators", focus=False)
        widget = getattr(self, "creators_widget", None)
        if widget is not None and hasattr(widget, "show_tool"):
            widget.show_tool("analyze")
            analyzer = getattr(widget, "analyzer", None)
            if analyzer is not None and hasattr(analyzer, "set_file"):
                analyzer.set_file(str(path))
        self.toast("Fichier prêt à analyser dans l'espace Créateurs.")

    # ------------------------------------------------------------------
    # Créateurs / Aide
    # ------------------------------------------------------------------
    def _build_creators_page(self) -> QWidget:
        from overload.ui.creators import SAFETY_NOTE, create_creators_widget

        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(26, 18, 26, 20)
        layout.setSpacing(12)
        banner = InfoBanner(
            self.tokens,
            "shield",
            SAFETY_NOTE,
            kind="info",
            title="Vos fichiers d'origine sont protégés",
        )
        layout.addWidget(banner)

        self.creators_widget = create_creators_widget(
            history=self.history, data_dir=self.data_dir, embedded=True
        )
        show_tool = getattr(self.creators_widget, "show_tool", lambda _key: None)

        hub = QFrame()
        hub.setObjectName("panelCard")
        hub_layout = QVBoxLayout(hub)
        hub_layout.setContentsMargins(14, 12, 14, 12)
        hub_layout.setSpacing(10)
        hub_header = QHBoxLayout()
        hub_title = QLabel("Que voulez-vous faire ?")
        hub_title.setObjectName("sectionTitle")
        hub_header.addWidget(hub_title)
        hub_header.addStretch()
        hub_hint = QLabel("Chaque outil explique son effet avant d'agir.")
        hub_hint.setObjectName("tinyLabel")
        hub_header.addWidget(hub_hint)
        self.hub_toggle = QPushButton("Réduire")
        self.hub_toggle.setObjectName("linkBtn")
        self.hub_toggle.setCursor(Qt.CursorShape.PointingHandCursor)
        hub_header.addWidget(self.hub_toggle)
        hub_layout.addLayout(hub_header)

        self.hub_grid_host = QWidget()
        grid = QGridLayout(self.hub_grid_host)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(10)
        tools = [
            (
                "prepare", "layers", "Préparer un projet",
                "Rassemblez vos médias dispersés dans un dossier de projet rangé.",
                "Fichiers ou dossiers entiers · copies uniquement",
            ),
            (
                "projects", "folder", "Mes projets",
                "Créez l'arborescence d'un projet selon votre logiciel de montage.",
                "Un dossier existant est complété, jamais vidé",
            ),
            (
                "analyze", "monitor", "Analyser un fichier",
                "Format, résolution, durée, codecs et pistes d'un média local.",
                "Vidéo/audio local · lecture seule, 100 % hors ligne",
            ),
            (
                "premiere", "check", "Vérifier pour Premiere Pro",
                "Contrôlez la compatibilité avant import et repérez les risques.",
                "Signale les problèmes · ne convertit ni ne modifie rien",
            ),
            (
                "tracks", "captions", "Sous-titres et pistes",
                "Listez les pistes, extrayez un .srt ou un .wav, créez un modèle.",
                "Le fichier source n'est jamais modifié",
            ),
            (
                "rename", "edit", "Renommer par lots",
                "Renommez des copies selon un modèle, avec aperçu en direct.",
                "Aperçu avant écriture · jamais d'écrasement",
            ),
            (
                "inventory", "list", "Inventaire et export",
                "Listez sources, codecs et caractéristiques, exportez en CSV.",
                "CSV prêt pour Excel · analyse en lecture seule",
            ),
            (
                "profiles", "sliders", "Profils de montage",
                "Premiere Pro, DaVinci Resolve, CapCut… et vos profils maison.",
                "Structures et formats recommandés par logiciel",
            ),
        ]
        for index, (key, icon_name, title, text, meta) in enumerate(tools):
            card = ToolCard(
                icon_name,
                title,
                text,
                meta,
                self.tokens,
                on_click=lambda _checked=False, k=key: show_tool(k),
                scale=self.scale,
            )
            card.setMinimumHeight(round(112 * self.scale))
            grid.addWidget(card, index // 4, index % 4)
            self._tool_cards.append(card)
            self._themed.append(card)
        for column in range(4):
            grid.setColumnStretch(column, 1)
        hub_layout.addWidget(self.hub_grid_host)

        def toggle_hub() -> None:
            visible = not self.hub_grid_host.isVisible()
            self.hub_grid_host.setVisible(visible)
            self.hub_toggle.setText("Réduire" if visible else "Afficher les outils")

        self.hub_toggle.clicked.connect(toggle_hub)
        layout.addWidget(hub)
        layout.addWidget(self.creators_widget, 1)
        return page

    def _build_help_page(self) -> QWidget:
        scroll, layout = self._scroll_page()

        def card(title: str):
            frame = QFrame()
            frame.setObjectName("panelCard")
            inner = QVBoxLayout(frame)
            inner.setContentsMargins(18, 16, 18, 16)
            inner.setSpacing(9)
            title_lbl = QLabel(title)
            title_lbl.setObjectName("sectionTitle")
            inner.addWidget(title_lbl)
            layout.addWidget(frame)
            return inner

        def paragraph(parent_layout, text: str, *, style: str = "mutedLabel") -> QLabel:
            label = QLabel(text)
            label.setObjectName(style)
            label.setWordWrap(True)
            parent_layout.addWidget(label)
            return label

        start = card("Démarrage rapide")
        for number, title, text in (
            (
                1,
                "Collez un lien",
                "Depuis l'accueil : vidéo YouTube publique ou adresse directe "
                "vers un fichier. Le bouton Coller récupère le presse-papiers.",
            ),
            (
                2,
                "Choisissez les options utiles",
                "Dossier de destination, qualité vidéo pour YouTube. "
                "C'est tout — le reste est automatique.",
            ),
            (
                3,
                "Lancez et suivez",
                "Progression réelle, vitesse et temps restant dans "
                "Téléchargements. Le fichier terminé se retrouve dans la Bibliothèque.",
            ),
        ):
            row = QHBoxLayout()
            row.setSpacing(9)
            badge = StepBadge(number, self.tokens, size=24)
            self._themed.append(badge)
            row.addWidget(badge, 0, Qt.AlignmentFlag.AlignTop)
            col = QVBoxLayout()
            col.setSpacing(1)
            step_title = QLabel(title)
            step_title.setObjectName("stepTitle")
            col.addWidget(step_title)
            paragraph(col, text)
            row.addLayout(col, 1)
            start.addLayout(row)
        go_btn = QPushButton("Nouveau téléchargement")
        go_btn.setObjectName("primaryBtn")
        go_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        go_btn.setIcon(icons.icon("download", self.tokens.accent_ink, 16, 2.0))
        go_btn.clicked.connect(self.focus_composer)
        start.addWidget(go_btn, 0, Qt.AlignmentFlag.AlignLeft)

        sources = card("Sources prises en charge")
        paragraph(
            sources,
            "Prises en charge : vidéos YouTube publiques (youtube.com/watch?v=…, "
            "youtu.be/…, youtube.com/shorts/…), téléchargées en MP4 H.264/AAC quand "
            "YouTube fournit ces flux, et adresses HTTP(S) pointant directement "
            "vers un fichier (vidéo, audio, image, archive…).",
        )
        paragraph(
            sources,
            "Non prises en charge : vidéos privées, réservées aux membres, "
            "soumises à un contrôle d'âge ou protégées (DRM), et pages web qui ne "
            "sont pas des fichiers. OverLoad ne se connecte à aucun compte et ne "
            "contourne aucune protection : dans ces cas, le lien est refusé avec "
            "une explication. Téléchargez uniquement ce que vous êtes autorisé "
            "à enregistrer.",
        )

        faq = card("Dépannage")
        questions = [
            (
                "Mon lien est refusé, pourquoi ?",
                "Le champ de l'accueil explique la raison sous le lien (adresse "
                "invalide, source non prise en charge, fichier déjà présent…). "
                "Vérifiez que le lien pointe vers une vidéo YouTube publique ou "
                "directement vers un fichier.",
                "Retour à l'accueil", "home",
            ),
            (
                "Un téléchargement s'est interrompu.",
                "La carte de la tâche donne la cause probable et l'action "
                "recommandée. Utilisez Relancer : quand le serveur l'autorise, "
                "OverLoad reprend depuis le fichier partiel au lieu de tout "
                "recommencer.",
                "Ouvrir Téléchargements", "downloads",
            ),
            (
                "Où est passé mon fichier terminé ?",
                "Il est dans le dossier de destination (visible à l'étape 2 de "
                "l'accueil). Retrouvez-le dans la Bibliothèque, ou via "
                "l'Historique qui revérifie sa présence réelle sur le disque.",
                "Ouvrir la Bibliothèque", "library",
            ),
            (
                "Premiere Pro refuse ou lit mal ma vidéo.",
                "Analysez le fichier dans l'espace Créateurs : codec rare, "
                "cadence variable ou conteneur peu accepté y sont signalés avec "
                "des explications. OverLoad ne convertit jamais l'original en "
                "silence : à vous de décider ensuite.",
                "Analyser un fichier", "analyzer",
            ),
            (
                "C'est lent, ou je veux limiter la bande passante.",
                "Paramètres permet de limiter le débit global et le nombre de "
                "téléchargements simultanés, à chaud, sans relancer les tâches.",
                "Ouvrir Paramètres", "settings",
            ),
        ]
        for question, answer, action, target in questions:
            question_lbl = QLabel(question)
            question_lbl.setObjectName("helpQuestion")
            faq.addWidget(question_lbl)
            paragraph(faq, answer)
            link = QPushButton(action)
            link.setObjectName("linkBtn")
            link.setCursor(Qt.CursorShape.PointingHandCursor)
            link.clicked.connect(lambda _checked=False, k=target: self.go_to(k))
            faq.addWidget(link, 0, Qt.AlignmentFlag.AlignLeft)

        shortcuts = card("Raccourcis clavier")
        for keys, action in (
            ("Ctrl+L", "Aller au champ de lien (nouveau téléchargement)"),
            ("Ctrl+F", "Rechercher dans les téléchargements, l'historique ou la bibliothèque"),
            ("Ctrl+V", "Coller un lien dans le champ de l'accueil"),
            ("Entrée", "Lancer le téléchargement depuis le champ de lien"),
            (
                "Ctrl+1 … Ctrl+7",
                "Naviguer : Accueil, Téléchargements, Bibliothèque, Créateurs, "
                "Historique, Paramètres, Aide",
            ),
        ):
            row = QHBoxLayout()
            key_lbl = QLabel(keys)
            key_lbl.setObjectName("formatChip")
            row.addWidget(key_lbl, 0)
            action_lbl = QLabel(action)
            action_lbl.setObjectName("mutedLabel")
            action_lbl.setWordWrap(True)
            row.addWidget(action_lbl, 1)
            shortcuts.addLayout(row)

        about = card("À propos")
        paragraph(
            about,
            f"OverLoad {__version__} — Media Manager. Téléchargez, organisez et "
            "préparez vos médias dans une application Windows sobre : vert forêt "
            "naturel, statuts explicites, originaux toujours préservés. "
            "Licence MIT ; composants tiers détaillés dans "
            "THIRD_PARTY_LICENSES.md, livré avec l'application (Qt/PySide6, "
            "yt-dlp, FFmpeg/FFprobe LGPL).",
        )
        about_row = QHBoxLayout()
        data_btn = QPushButton("Dossier de données")
        data_btn.setObjectName("secondaryBtn")
        data_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        data_btn.clicked.connect(self.open_data_dir)
        about_row.addWidget(data_btn)
        dest_btn = QPushButton("Dossier de destination")
        dest_btn.setObjectName("secondaryBtn")
        dest_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        dest_btn.clicked.connect(
            lambda: self.safe_call(self.manager.open_downloads_folder)
        )
        about_row.addWidget(dest_btn)
        repo_btn = QPushButton("Code source (GitHub)")
        repo_btn.setObjectName("ghostBtn")
        repo_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        repo_btn.clicked.connect(
            lambda: webbrowser.open("https://github.com/TOFazer/OverLoad")
        )
        about_row.addWidget(repo_btn)
        about_row.addStretch()
        about.addLayout(about_row)

        layout.addStretch()
        return scroll

    # ------------------------------------------------------------------
    # Navigation et apparence
    # ------------------------------------------------------------------
    def go_to(self, key: str, *, focus: bool = True) -> None:
        # Compatibilité v1.x : l'analyse multimédia vit désormais dans
        # l'espace Créateurs, avec les autres outils de montage.
        analyze_after = key == "analyzer"
        if analyze_after:
            key = "creators"
        if key not in self._pages:
            return
        page = self._pages[key]
        if self.stack.currentWidget() is not page:
            self._fade_to(page)
        self._current_page = key
        for nav_key, button in self._nav_buttons.items():
            button.setChecked(nav_key == key)
        title, subtitle, icon_name, tone = self._page_meta[key]
        self.page_title.setText(title)
        self.page_subtitle.setText(subtitle)
        colors = {
            "accent": (self.tokens.accent_text, self.tokens.accent_soft),
            "info": (self.tokens.info, self.tokens.info_soft),
            "success": (self.tokens.success, self.tokens.success_soft),
            "warning": (self.tokens.warning, self.tokens.warning_soft),
        }
        fg, bg = colors.get(tone, colors["accent"])
        self.page_badge.refresh_theme(self.tokens, fg, bg)
        self.page_badge.set_icon(icon_name)
        self.new_btn.setVisible(key != "home")
        placeholders = {
            "downloads": "Rechercher un téléchargement…",
            "history": "Rechercher dans l'historique…",
            "library": "Rechercher un fichier local…",
        }
        self.search_edit.setPlaceholderText(placeholders.get(key, "Rechercher…"))
        if key == "settings" and isinstance(page, SettingsPage):
            page.refresh_from_prefs()
        if key == "library":
            self.refresh_library()
            self._render_library()
        if analyze_after:
            widget = getattr(self, "creators_widget", None)
            if widget is not None and hasattr(widget, "show_tool"):
                widget.show_tool("analyze")
        if key == "home" and focus:
            QTimer.singleShot(80, self.url_edit.setFocus)

    def focus_composer(self) -> None:
        self.go_to("home", focus=False)
        self.url_edit.setFocus()
        self.url_edit.selectAll()

    def _fade_to(self, page: QWidget) -> None:
        self.stack.setCurrentWidget(page)
        effect = QGraphicsOpacityEffect(page)
        effect.setOpacity(0.0)
        page.setGraphicsEffect(effect)
        animation = QPropertyAnimation(effect, b"opacity", self)
        animation.setDuration(170)
        animation.setStartValue(0.0)
        animation.setEndValue(1.0)
        animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        animation.finished.connect(lambda: page.setGraphicsEffect(None))
        animation.start()
        self._fade = animation

    def set_appearance(
        self, *, theme: str | None = None, accent: str | None = None, ui_scale: str | None = None
    ) -> None:
        changes: dict[str, str] = {}
        if theme:
            changes["theme"] = theme
        if accent:
            changes["accent"] = accent
        if ui_scale:
            changes["ui_scale"] = ui_scale
        if not changes:
            return
        self.settings_store.update(**changes)
        prefs = self.settings_store.get()
        self.tokens = apply_appearance(
            QApplication.instance(), prefs.theme, prefs.accent, prefs.ui_scale
        )
        self.scale = scale_factor(prefs.ui_scale)
        self._reskin()
        if isinstance(self._pages.get("settings"), SettingsPage):
            self._pages["settings"].refresh_from_prefs()

    def _reskin(self) -> None:
        for widget in self._themed:
            if hasattr(widget, "refresh_theme"):
                try:
                    widget.refresh_theme(self.tokens)
                except TypeError:
                    continue
        for card in self._cards.values():
            card.refresh_theme(self.tokens)
        for row in self._history_rows:
            row.refresh_theme(self.tokens)
        for row in self._recent_rows:
            row.refresh_theme(self.tokens)
        for row in self._queue_rows:
            row.refresh_theme(self.tokens)
        for row in self._library_rows:
            row.refresh_theme(self.tokens)
        self.page_badge.refresh_theme(self.tokens)
        self.theme_btn.set_icon_name("sun" if self.tokens.dark else "moon")
        self.theme_btn.refresh_theme(self.tokens)
        self.settings_btn.refresh_theme(self.tokens)
        self.new_btn.setIcon(icons.icon("download", self.tokens.accent_ink, 16, 2.0))
        self.download_btn.setIcon(icons.icon("download", self.tokens.accent_ink, 18, 2.0))
        self.batch_btn.setIcon(icons.icon("list", self.tokens.accent_text, 16))
        if hasattr(self, "paste_btn"):
            self.paste_btn.setIcon(icons.icon("clipboard", self.tokens.accent_text, 16))
        if hasattr(self, "history_link_btn"):
            self.history_link_btn.setIcon(
                icons.icon("history", self.tokens.text_secondary, 16)
            )
        self._search_icon = icons.icon("search", self.tokens.text_muted, 16)
        self._search_action.setIcon(self._search_icon)
        self._paste_action.setIcon(icons.icon("copy", self.tokens.text_muted, 16))
        self.toast_widget.badge.refresh_theme(self.tokens)
        self._update_hero_title()
        self._recent_sig = None
        self._queue_sig = None
        self._history_sig = None
        self._apply_responsive()
        self._refresh_history()

    def toggle_theme(self) -> None:
        self.set_appearance(theme="light" if self.tokens.dark else "dark")

    def show_error(self, exc: BaseException) -> None:
        if not isinstance(exc, OverloadError):
            # Toute erreur imprévue devient une explication visible : aucune
            # exception ne doit disparaître silencieusement dans Qt.
            exc = OverloadError(
                "OverLoad a rencontré une erreur inattendue.",
                f"{type(exc).__name__}: {exc}".strip(),
                "Réessayez l'opération ; si le problème persiste, redémarrez OverLoad.",
            )
        info = explain_failure(str(exc))
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Icon.Warning)
        box.setWindowTitle(info.title)
        box.setText(info.detail)
        box.setInformativeText(f"{info.action}\n\nDétail technique :\n{info.technical}")
        box.exec()

    def safe_call(self, function) -> Any:
        try:
            return function()
        except OverloadError as exc:
            self.show_error(exc)
            return None
        except Exception as exc:  # noqa: BLE001
            self.show_error(exc)
            return None

    def toast(self, message: str, kind: str = "success") -> None:
        self.toast_widget.show_message(message, kind)

    def open_data_dir(self) -> None:
        self.safe_call(lambda: open_folder(self.data_dir))

    def paste_clipboard(self) -> None:
        text = QApplication.clipboard().text().strip()
        if text:
            self.url_edit.setText(text)
            self.url_edit.setFocus()
            self._validate_url()

    def choose_destination(self) -> None:
        current = self.settings_store.get().destination_dir
        folder = choose_directory(
            self, "Choisir le dossier de téléchargements", preferred=current
        )
        if folder:
            self.apply_destination(folder)

    def apply_destination(self, folder: str) -> bool:
        path = Path(folder).expanduser()
        if not path.is_dir():
            self.show_error(OverloadError("Dossier introuvable.", f"« {folder} » n'existe pas."))
            return False
        try:
            self.manager.set_destination_dir(path)
        except OverloadError as exc:
            self.show_error(exc)
            return False
        self.settings_store.update(destination_dir=str(path))
        self.dest_label.setText(str(path))
        self.toast("Dossier de destination mis à jour.")
        self._disk_at = 0.0
        return True

    # ------------------------------------------------------------------
    # Téléchargement depuis l'accueil
    # ------------------------------------------------------------------
    def _schedule_validation(self, _text: str) -> None:
        if not hasattr(self, "_validate_timer"):
            self._validate_timer = QTimer(self)
            self._validate_timer.setSingleShot(True)
            self._validate_timer.setInterval(320)
            self._validate_timer.timeout.connect(self._validate_url)
        self._validate_timer.start()

    def _set_url_state(self, state: str) -> None:
        if hasattr(self, "step_link_badge"):
            self.step_link_badge.set_done(state == "valid")
        self.url_edit.setProperty("invalid", state == "invalid")
        self.url_edit.setProperty("valid", state == "valid")
        self.url_edit.style().unpolish(self.url_edit)
        self.url_edit.style().polish(self.url_edit)

    def _validate_url(self) -> None:
        text = self.url_edit.text().strip()
        if not text:
            self._set_url_state("")
            self.url_hint.setObjectName("mutedLabel")
            self.url_hint.setText(
                "Liens YouTube et fichiers HTTP(S) directs pris en charge."
            )
            self._restyle_label(self.url_hint)
            return
        try:
            result = self.manager.inspect_batch(text)
        except Exception:  # noqa: BLE001
            self._set_url_state("")
            return
        if result["duplicates"]:
            self._set_url_state("valid")
            self.url_hint.setObjectName("warningText")
            self.url_hint.setText("Déjà présent : " + result["duplicates"][0]["reason"])
        elif result["rejected"]:
            self._set_url_state("invalid")
            info = explain_failure(result["rejected"][0]["error"])
            self.url_hint.setObjectName("dangerText")
            self.url_hint.setText(f"{info.title} — {info.action}")
        elif result["valid"]:
            entry = result["valid"][0]
            self._set_url_state("valid")
            if entry.get("provider") == "youtube":
                self.url_hint.setObjectName("successText")
                self.url_hint.setText(
                    "Vidéo YouTube détectée — récupération du titre et des qualités…"
                )
                self._restyle_label(self.url_hint)
                self._probe_media(text)
                return
            self.url_hint.setObjectName("successText")
            self.url_hint.setText(f"Prêt à télécharger « {entry['filename']} »")
        else:
            self._set_url_state("")
        self._restyle_label(self.url_hint)

    @staticmethod
    def _restyle_label(label: QLabel) -> None:
        label.style().unpolish(label)
        label.style().polish(label)

    def _probe_media(self, url: str) -> None:
        cached = self._media_cache.get(url)
        if cached is not None:
            self._apply_media_info(cached)
            return
        if self._probe_url == url:
            return
        self._probe_url = url
        self._probe.start(url)

    def _on_media_info(self, url: str, info: object, error: object) -> None:
        if self._probe_url == url:
            self._probe_url = None
        if url != self.url_edit.text().strip():
            return
        if error or not isinstance(info, dict):
            self.url_hint.setObjectName("dangerText")
            message = str(error or "Informations YouTube indisponibles.")
            self.url_hint.setText(message.split("\n")[0])
            self._restyle_label(self.url_hint)
            return
        self._media_cache[url] = info
        self._apply_media_info(info)

    def _apply_media_info(self, info: dict[str, Any]) -> None:
        duration = format_duration(info.get("duration_seconds"))
        if duration == "Indéterminé":
            duration = ""
        details = ["YouTube"]
        if info.get("uploader"):
            details.append(str(info["uploader"]))
        if duration:
            details.append(duration)
        heights = info.get("heights") or []
        if heights:
            details.append(f"qualités jusqu'à {heights[0]}p")
        self.url_hint.setObjectName("successText")
        self.url_hint.setText(f"{info.get('title', 'Vidéo')} — " + " · ".join(details))
        self._restyle_label(self.url_hint)

    def download_from_composer(self) -> None:
        try:
            url = self.url_edit.text().strip()
            if not url:
                self.url_hint.setObjectName("dangerText")
                self.url_hint.setText(
                    "Collez d'abord un lien YouTube ou une adresse directe vers un fichier."
                )
                self._restyle_label(self.url_hint)
                self.url_edit.setFocus()
                return
            if self._composer_busy:
                self.toast("Analyse déjà en cours… patientez quelques instants.", "info")
                return
            kwargs: dict[str, Any] = {}
            if is_youtube_url(url):
                quality = self.quality_combo.currentData()
                if quality:
                    kwargs["quality"] = quality
            self._enqueue(url, **kwargs)
        except Exception as exc:  # noqa: BLE001 - jamais de clic muet
            self.show_error(exc)

    def _enqueue(self, url: str, **kwargs) -> None:
        """Ajoute un téléchargement sans jamais figer le thread graphique."""

        def work() -> Any:
            return self.manager.enqueue(url, **kwargs)

        def done(result: object, error: object) -> None:
            self._on_enqueue_result(url, kwargs, result, error)

        self._set_composer_busy(True)
        op = self._run_download_operation(work, done)
        op.settled.connect(self._on_composer_settled)

    def _on_composer_settled(self) -> None:
        """Le bouton « Télécharger » redevient utilisable dès qu'une réponse arrive."""
        self._set_composer_busy(False)

    def _run_download_operation(self, fn: Any, on_done: Any) -> _DownloadOperation:
        """Exécute `fn` en arrière-plan et rappelle `on_done(résultat, erreur)`.

        Après `async_timeout_ms`, une erreur explicite est affichée au lieu de
        laisser le bouton semble ne rien faire ; l'opération continue en tâche de
        fond et un aboutissement tardif reste signalé à l'utilisateur.
        """
        op = _DownloadOperation(
            fn,
            on_done,
            timeout_ms=self.async_timeout_ms,
            timeout_error=OverloadError(
                "L'analyse du lien prend trop de temps.",
                "YouTube ou le serveur mettent trop de temps à répondre.",
                "Vérifiez votre connexion Internet puis réessayez. Si l'analyse "
                "finit par aboutir, le téléchargement sera ajouté automatiquement.",
            ),
            parent=self,
        )
        return op

    def _set_composer_busy(self, busy: bool) -> None:
        self._composer_busy = busy
        self.download_btn.setEnabled(not busy)
        if busy:
            self.url_hint.setObjectName("mutedLabel")
            self.url_hint.setText(
                "Analyse du lien en cours… YouTube peut prendre quelques secondes."
            )
            self._restyle_label(self.url_hint)

    def _on_enqueue_result(
        self, url: str, kwargs: dict, result: object, error: object
    ) -> None:
        if error is not None:
            if self.url_edit.text().strip() == url:
                self.url_hint.setObjectName("dangerText")
                self.url_hint.setText(
                    "Le téléchargement n'a pas pu démarrer — un message explique pourquoi."
                )
                self._restyle_label(self.url_hint)
            if isinstance(error, DuplicateDetectedError):
                self._duplicate_dialog(url, error, kwargs)
            else:
                self.show_error(error)
            return
        if result is None:
            # Politique « ignorer » sur un doublon : message explicite, jamais muet.
            if self.url_edit.text().strip() == url:
                self.url_hint.setObjectName("mutedLabel")
                self.url_hint.setText("Ce fichier est déjà téléchargé — ajout ignoré.")
                self._restyle_label(self.url_hint)
            self.toast("Déjà présent : téléchargement ignoré.", "info")
            return
        if self.url_edit.text().strip() == url:
            self.url_edit.clear()
            self.url_hint.setObjectName("mutedLabel")
            self.url_hint.setText("Ajouté à la file. Suivez sa progression ci-dessous.")
            self._restyle_label(self.url_hint)
        self.toast(f"« {result.filename} » ajouté à la file.")
        self.maybe_reload_history(force=True)
        self.refresh_all()

    def _duplicate_dialog(self, url: str, duplicate: DuplicateDetectedError, kwargs: dict) -> None:
        box = QMessageBox(self)
        box.setWindowTitle("Fichier déjà présent")
        box.setIcon(QMessageBox.Icon.Information)
        box.setText(duplicate.match.reason)
        box.setInformativeText(f"Emplacement : {duplicate.match.existing_path}")
        open_existing = box.addButton("Ouvrir le dossier", QMessageBox.ButtonRole.ActionRole)
        copy = box.addButton("Télécharger une copie « (2) »", QMessageBox.ButtonRole.AcceptRole)
        box.addButton("Ignorer", QMessageBox.ButtonRole.RejectRole)
        box.exec()
        clicked = box.clickedButton()
        if clicked is open_existing:
            self.safe_call(lambda: open_folder(duplicate.match.existing_path))
        elif clicked is copy:
            self._enqueue(url, duplicate_policy=DuplicatePolicy.RENAME, **kwargs)

    def open_batch_dialog(self) -> None:
        dialog = BatchDialog(self)
        dialog.exec()

    def _on_search(self, text: str) -> None:
        cleaned = text.strip()
        self._search = cleaned
        if cleaned and self._current_page not in {"downloads", "history", "library"}:
            self.go_to("downloads", focus=False)
        self._refresh_tasks(self.manager.list_tasks())
        self._refresh_history()
        self._render_library()

    # ------------------------------------------------------------------
    # Rafraîchissement
    # ------------------------------------------------------------------
    def refresh_all(self) -> None:
        self._last_overview = self.manager.status_overview()
        snapshots = self.manager.list_tasks()
        self._refresh_stats(snapshots)
        self._refresh_tasks(snapshots)
        self.maybe_reload_history()
        self._refresh_home()
        self._refresh_history()
        if self._current_page == "library":
            self.refresh_library()
        self._refresh_sidebar(snapshots)

    def _refresh_stats(self, snapshots) -> None:
        overview = self._last_overview
        counts = overview.get("counts", {})
        running = counts.get(TaskState.RUNNING.value, 0)
        queued = counts.get(TaskState.QUEUED.value, 0)
        paused = counts.get(TaskState.PAUSED.value, 0)
        speed = float(overview.get("total_speed_bps", 0.0))
        self.stat_speed.set_value(
            overview.get("total_speed_human", "0 o/s"),
            f"{running} transfert(s) actif(s)" if running else "Aucun transfert",
        )
        self.stat_active.set_value(
            f"{running} / {overview.get('settings', {}).get('max_concurrent', 3)}",
            f"{queued} en attente · {paused} en pause",
        )
        self.stat_done.set_value(str(self._history_counts["today"]), "aujourd'hui")
        now = time.monotonic()
        if now - self._disk_at > 6:
            self._disk_at = now
            try:
                usage = shutil.disk_usage(self.manager.settings().destination_dir)
                self._disk_free = format_bytes(usage.free)
            except OSError:
                self._disk_free = "—"
        self.stat_disk.set_value(self._disk_free, "libres sur le disque")
        self.sidebar_spark.push(speed)

    def _refresh_sidebar(self, snapshots) -> None:
        overview = self._last_overview
        self.sidebar_speed.setText(overview.get("total_speed_human", "0 o/s"))
        counts = overview.get("counts", {})
        active = counts.get(TaskState.RUNNING.value, 0) + counts.get(TaskState.QUEUED.value, 0)
        paused = counts.get(TaskState.PAUSED.value, 0)
        if active or paused:
            self.sidebar_queue.setText(f"{active} actif(s) · {paused} en pause")
        else:
            self.sidebar_queue.setText("Aucune activité")
        downloads_btn = self._nav_buttons.get("downloads")
        if downloads_btn is not None:
            downloads_btn.set_badge(active + paused)

    def _refresh_tasks(self, snapshots) -> None:
        query = self._search.casefold()
        counts = {
            "all": len(snapshots),
            "running": 0,
            "queued": 0,
            "paused": 0,
            "failed": 0,
        }
        for snap in snapshots:
            if snap.state is TaskState.RUNNING:
                counts["running"] += 1
            elif snap.state is TaskState.QUEUED:
                counts["queued"] += 1
            elif snap.state is TaskState.PAUSED:
                counts["paused"] += 1
            if snap.state is TaskState.FAILED or snap.retrying or snap.stalled:
                counts["failed"] += 1
        labels = {
            "all": "Tous",
            "running": "En cours",
            "queued": "En attente",
            "paused": "En pause",
            "failed": "Problèmes",
        }
        for key, label in labels.items():
            self.filters.set_label(key, f"{label} ({counts[key]})")

        visible = []
        for snap in snapshots:
            if query and query not in snap.filename.casefold() and query not in snap.url.casefold():
                continue
            state = snap.state
            chosen = self._active_filter
            if chosen == "failed":
                if not (state is TaskState.FAILED or snap.retrying or snap.stalled):
                    continue
            elif chosen != "all" and state.value != chosen:
                continue
            visible.append(snap)

        visible_ids = {snap.id for snap in visible}
        for task_id in list(self._cards):
            if task_id not in visible_ids:
                card = self._cards.pop(task_id)
                self.active_list.removeWidget(card)
                card.hide()
                card.setParent(None)
                card.deleteLater()
        insert_at = 1  # après l'état vide
        for index, snap in enumerate(visible):
            card = self._cards.get(snap.id)
            if card is None:
                card = DownloadCard(
                    snap.id,
                    self.manager,
                    self.tokens,
                    self.thumbnails,
                    scale=self.scale,
                    on_error=self.show_error,
                )
                self._cards[snap.id] = card
            card.refresh(snap)
            self.active_list.insertWidget(index + insert_at, card)
        self.active_empty.setVisible(not visible)
        if snapshots and not visible:
            self.active_empty.set_texts(
                "Aucun résultat",
                "Aucun téléchargement ne correspond à ce filtre ou à votre recherche.",
                "Réinitialiser les filtres",
            )
        else:
            self.active_empty.set_texts(
                "Aucun téléchargement en cours",
                "Collez un lien depuis l'accueil pour démarrer votre premier téléchargement.",
                "Coller un lien",
            )
        self.active_count.setText(
            f"{len(visible)} affiché(s) sur {len(snapshots)}" if snapshots else ""
        )
        if hasattr(self, "downloads_summary"):
            if snapshots:
                self.downloads_summary.setText(
                    f"{counts['running']} en cours · {counts['queued']} en attente · "
                    f"{counts['paused']} en pause · {counts['failed']} problème(s)"
                )
            else:
                self.downloads_summary.setText("Aucune tâche pour le moment.")
        if hasattr(self, "pause_all_btn"):
            self.pause_all_btn.setEnabled(counts["running"] + counts["queued"] > 0)
            self.resume_all_btn.setEnabled(counts["paused"] > 0)
            self.clear_done_btn.setEnabled(
                self._last_overview.get("counts", {}).get(TaskState.COMPLETED.value, 0)
                + self._last_overview.get("counts", {}).get(TaskState.CANCELLED.value, 0)
                > 0
            )

    def _refresh_home(self) -> None:
        queue_rows = [
            snap
            for snap in self.manager.list_tasks()
            if snap.state
            in {TaskState.RUNNING, TaskState.QUEUED, TaskState.PAUSED, TaskState.FINALIZING}
        ][:4]
        queue_sig = tuple(snap.id for snap in queue_rows)
        if queue_sig != self._queue_sig:
            self._queue_sig = queue_sig
            _clear_rows(self.queue_list)
            self._queue_rows = []
            for index, snap in enumerate(queue_rows):
                row = QueueRow(self.tokens, snap)
                self.queue_list.insertWidget(index, row)
                row.show()
                self._queue_rows.append(row)
            self.queue_empty.setVisible(not queue_rows)
        else:
            for row, snap in zip(self._queue_rows, queue_rows, strict=False):
                row.refresh(snap)

        recent = self._history_all[:4]
        recent_sig = tuple((entry.id, entry.status, entry.file_exists) for entry in recent)
        if recent_sig != self._recent_sig:
            self._recent_sig = recent_sig
            _clear_rows(self.recent_list)
            self._recent_rows = []
            for index, entry in enumerate(recent):
                row = ActivityRow(
                    entry,
                    self.tokens,
                    self.thumbnails,
                    on_open=lambda item: self.safe_call(
                        lambda: self.manager.open_history_folder(item.id)
                    ),
                )
                self.recent_list.insertWidget(index, row)
                self._recent_rows.append(row)
            self.recent_empty.setVisible(not recent)
            self.recent_host.setVisible(bool(recent))

    def maybe_reload_history(self, *, force: bool = False) -> None:
        now = time.monotonic()
        if not force and now - self._last_history_at < 1.0:
            return
        self._last_history_at = now
        previous_count = len(self._history_all)
        self._history_all = self.history.list_entries(limit=300)
        if len(self._history_all) != previous_count:
            self._library_dirty = True
        today = datetime.now(UTC).date()
        completed_today = 0
        for entry in self._history_all:
            if entry.status == "completed":
                try:
                    finished = datetime.fromisoformat(entry.finished_at)
                    if finished.tzinfo is None:
                        finished = finished.replace(tzinfo=UTC)
                    if finished.date() == today:
                        completed_today += 1
                except (TypeError, ValueError):
                    continue
        self._history_counts = {
            "completed": sum(1 for e in self._history_all if e.status == "completed"),
            "failed": sum(1 for e in self._history_all if e.status == "failed"),
            "today": completed_today,
        }

    def _refresh_history(self) -> None:
        query = self._search.casefold()
        filtered = [
            entry
            for entry in self._history_all
            if (self._history_filter == "all" or entry.status == self._history_filter)
            and (not query or query in entry.filename.casefold() or query in entry.url.casefold())
        ][:200]
        signature = (
            tuple((entry.id, entry.status, entry.file_exists) for entry in filtered),
            query,
            self._history_filter,
        )
        if signature != self._history_sig:
            self._history_sig = signature
            _clear_rows(self.history_list)
            self._history_rows = []
            for index, entry in enumerate(filtered):
                row = HistoryRow(
                    entry,
                    self.manager,
                    self.tokens,
                    self.thumbnails,
                    on_remove=self._remove_history,
                    on_error=self.show_error,
                    scale=self.scale,
                )
                self.history_list.insertWidget(index, row)
                self._history_rows.append(row)
            self.history_empty.setVisible(not filtered)
            if self._history_all and not filtered:
                self.history_empty.set_texts(
                    "Aucun résultat",
                    "Aucune entrée ne correspond à ce statut ou à votre recherche.",
                )
            else:
                self.history_empty.set_texts(
                    "Historique vide",
                    "Les téléchargements terminés ou interrompus seront conservés ici, "
                    "même après la fermeture d'OverLoad.",
                )
            self.history_count.setText(f"{len(filtered)} entrée(s)" if filtered else "")
            if hasattr(self, "history_summary"):
                by_status = {"completed": 0, "failed": 0, "cancelled": 0}
                for entry in self._history_all:
                    if entry.status in by_status:
                        by_status[entry.status] += 1
                if self._history_all:
                    self.history_summary.setText(
                        f"{by_status['completed']} terminé(s) · "
                        f"{by_status['failed']} interrompu(s) · "
                        f"{by_status['cancelled']} annulé(s)"
                    )
                else:
                    self.history_summary.setText(
                        "Aucun téléchargement passé pour le moment."
                    )

    def _set_filter(self, value: str) -> None:
        self._active_filter = value
        self._refresh_tasks(self.manager.list_tasks())

    def _set_history_filter(self, _index: int) -> None:
        self._history_filter = str(self.history_status.currentData())
        self._history_sig = None
        self._refresh_history()

    def _remove_history(self, entry_id: str) -> None:
        self.history.remove_entry(entry_id)
        self.maybe_reload_history(force=True)
        self._recent_sig = None
        self._history_sig = None
        self.refresh_all()

    def _clear_history(self) -> None:
        answer = QMessageBox.question(
            self,
            "Effacer l'historique ?",
            "Les fichiers téléchargés seront conservés sur le disque. Seul l'historique sera vidé.",
        )
        if answer == QMessageBox.StandardButton.Yes:
            self.history.clear()
            self.maybe_reload_history(force=True)
            self._recent_sig = None
            self._history_sig = None
            self.refresh_all()
            self.toast("Historique effacé — vos fichiers restent intacts.")

    def _update_hero_title(self) -> None:
        self.hero_title.setText(
            f'Tout commence <span style="color:{self.tokens.accent_text};">ici.</span>'
        )

    # ------------------------------------------------------------------
    # Responsive
    # ------------------------------------------------------------------
    def showEvent(self, event) -> None:  # noqa: N802
        super().showEvent(event)
        self._apply_responsive()
        self._update_hero_title()

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._apply_responsive()
        if hasattr(self, "toast_widget") and self.toast_widget.isVisible():
            self.toast_widget.move(
                max(16, self.width() - self.toast_widget.width() - 26),
                max(16, self.height() - self.toast_widget.height() - 24),
            )

    def _apply_responsive(self) -> None:
        compact = self.width() < 1160
        self.sidebar.setFixedWidth(round((72 if compact else 252) * self.scale))
        if compact != self._compact:
            self._compact = compact
            for button in self._nav_buttons.values():
                button.set_compact(compact)
            for label in self._brand_labels:
                label.setVisible(not compact)
            for label in self._section_labels:
                label.setVisible(not compact)
            self.sidebar_status.setVisible(not compact)
            self.version_label.setVisible(not compact)
            self.logo_row.layout().setAlignment(
                Qt.AlignmentFlag.AlignCenter if compact else Qt.AlignmentFlag.AlignLeft
            )
        content_width = self.width() - self.sidebar.width()
        if hasattr(self, "hero_art"):
            self.hero_art.setVisible(content_width > 880)
        if hasattr(self, "stats_grid"):
            columns = 2 if content_width < 900 else 4
            if columns != self._stats_columns:
                self._stats_columns = columns
                for card in self._stat_cards:
                    self.stats_grid.removeWidget(card)
                for index, card in enumerate(self._stat_cards):
                    self.stats_grid.addWidget(card, index // columns, index % columns)
                self.stats_grid.setColumnStretch(0, 1)
                self.stats_grid.setColumnStretch(1, 1)
                self.stats_grid.setColumnStretch(2, 1 if columns > 2 else 0)
                self.stats_grid.setColumnStretch(3, 1 if columns > 2 else 0)
        if hasattr(self, "search_edit"):
            self.search_edit.setFixedWidth(
                max(160, min(round(262 * self.scale), round(content_width * 0.3)))
            )

    def _wire_shortcuts(self) -> None:
        search_shortcut = QShortcut(QKeySequence("Ctrl+F"), self)
        search_shortcut.activated.connect(self._focus_search)
        url_shortcut = QShortcut(QKeySequence("Ctrl+L"), self)
        url_shortcut.activated.connect(self.focus_composer)
        self._nav_shortcuts: list[QShortcut] = []
        for index, key in enumerate(NAV_ORDER, start=1):
            shortcut = QShortcut(QKeySequence(f"Ctrl+{index}"), self)
            shortcut.activated.connect(lambda k=key: self.go_to(k))
            self._nav_shortcuts.append(shortcut)

    def _focus_search(self) -> None:
        self.search_edit.setFocus()
        self.search_edit.selectAll()

    def closeEvent(self, event) -> None:  # noqa: N802
        if hasattr(self, "_timer"):
            self._timer.stop()
        if hasattr(self, "_validate_timer"):
            self._validate_timer.stop()
        super().closeEvent(event)
