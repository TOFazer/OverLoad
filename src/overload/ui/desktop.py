"""Application de bureau native OverLoad (PySide6 / QtWidgets, embarquée dans OverLoad.exe).

Conforme à l'architecture cible : aucune logique réseau ou métier ne réside ici.
L'interface pilote exclusivement `DownloadManager`, `DownloadHistoryStore` et
`SettingsStore`.
"""

from __future__ import annotations

import sys
from collections import deque
from pathlib import Path
from typing import TYPE_CHECKING, Any

from overload.core.errors import OverloadError
from overload.core.formatting import format_bytes, format_duration, format_speed
from overload.core.paths import default_data_dir, default_downloads_dir, open_folder
from overload.downloads.duplicates import DuplicateDetectedError, DuplicatePolicy
from overload.downloads.manager import DownloadManager
from overload.downloads.models import TaskSnapshot
from overload.downloads.state import TaskState
from overload.history.store import DownloadHistoryStore, HistoryEntry
from overload.settings.store import SettingsStore
from overload.ui.theme import build_stylesheet

if TYPE_CHECKING:
    from PySide6.QtGui import QIcon
    from PySide6.QtWidgets import QMainWindow


def is_pyside6_available() -> bool:
    try:
        import PySide6.QtWidgets  # noqa: F401
    except ImportError:
        return False
    return True


def create_app_icon() -> QIcon:
    """Dessine vectoriellement l'icône éclair d'OverLoad sans dépendre d'un fichier externe."""
    from PySide6.QtCore import QPointF, Qt
    from PySide6.QtGui import QColor, QIcon, QLinearGradient, QPainter, QPixmap, QPolygonF

    icon = QIcon()
    for size in (16, 32, 48, 64, 128):
        pix = QPixmap(size, size)
        pix.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pix)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        grad = QLinearGradient(0, 0, size, size)
        grad.setColorAt(0.0, QColor("#f59e0b"))
        grad.setColorAt(1.0, QColor("#ea580c"))
        painter.setBrush(grad)
        painter.setPen(Qt.PenStyle.NoPen)
        radius = size * 0.24
        painter.drawRoundedRect(0, 0, size, size, radius, radius)

        bolt = QPolygonF(
            [
                QPointF(size * 0.56, size * 0.14),
                QPointF(size * 0.26, size * 0.54),
                QPointF(size * 0.47, size * 0.54),
                QPointF(size * 0.41, size * 0.86),
                QPointF(size * 0.74, size * 0.45),
                QPointF(size * 0.53, size * 0.45),
            ]
        )
        painter.setBrush(QColor("#ffffff"))
        painter.drawPolygon(bolt)
        painter.end()
        icon.addPixmap(pix)
    return icon


def _state_presentation(snap: TaskSnapshot) -> tuple[str, str]:
    if snap.retrying:
        return (f"Reprise auto {snap.retry_count}/{snap.max_retries}", "#f59e0b")
    mapping = {
        TaskState.RUNNING: ("En cours", "#f59e0b"),
        TaskState.PAUSED: ("En pause", "#38bdf8"),
        TaskState.QUEUED: ("En attente", "#94a3b8"),
        TaskState.FINALIZING: ("Vérification…", "#f59e0b"),
        TaskState.COMPLETED: ("Terminé", "#10b981"),
        TaskState.FAILED: ("Échec", "#ef4444"),
        TaskState.CANCELLED: ("Annulé", "#94a3b8"),
    }
    return mapping.get(snap.state, (snap.state.value, "#94a3b8"))


def create_main_window(
    manager: DownloadManager,
    history: DownloadHistoryStore,
    settings_store: SettingsStore,
) -> QMainWindow:
    """Construit et retourne la fenêtre principale `QMainWindow` d'OverLoad."""
    from PySide6.QtCore import QPointF, Qt, QTimer
    from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen
    from PySide6.QtWidgets import (
        QApplication,
        QCheckBox,
        QComboBox,
        QFileDialog,
        QFrame,
        QHBoxLayout,
        QLabel,
        QLineEdit,
        QMainWindow,
        QMessageBox,
        QPlainTextEdit,
        QProgressBar,
        QPushButton,
        QScrollArea,
        QSpinBox,
        QSplitter,
        QTabWidget,
        QVBoxLayout,
        QWidget,
    )

    class SpeedSparklineWidget(QWidget):
        """Courbe temps réel du débit global."""

        def __init__(self) -> None:
            super().__init__()
            self.samples: deque[float] = deque([0.0] * 40, maxlen=40)
            self.setFixedSize(130, 34)

        def push(self, bps: float) -> None:
            self.samples.append(max(0.0, bps))
            self.update()

        def paintEvent(self, _event: Any) -> None:  # noqa: N802
            painter = QPainter(self)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            w = float(self.width())
            h = float(self.height())
            peak = max(max(self.samples), 1024.0)
            pts = [
                QPointF(
                    (i / max(1, len(self.samples) - 1)) * w,
                    h - 3.0 - (min(val, peak) / peak) * (h - 6.0),
                )
                for i, val in enumerate(self.samples)
            ]
            line_path = QPainterPath(pts[0])
            for pt in pts[1:]:
                line_path.lineTo(pt)

            area_path = QPainterPath(line_path)
            area_path.lineTo(w, h)
            area_path.lineTo(0.0, h)
            area_path.closeSubpath()

            painter.fillPath(area_path, QColor(245, 158, 11, 45))
            pen = QPen(QColor("#f59e0b"), 2.0)
            painter.setPen(pen)
            painter.drawPath(line_path)
            painter.end()

    class TaskCardWidget(QFrame):
        """Carte individuelle de téléchargement avec progression, vitesse, ETA et actions."""

        def __init__(self, task_id: str) -> None:
            super().__init__()
            self.task_id = task_id
            self.setObjectName("itemCard")
            layout = QVBoxLayout(self)
            layout.setContentsMargins(12, 10, 12, 10)
            layout.setSpacing(6)

            top_row = QHBoxLayout()
            self.name_lbl = QLabel()
            self.name_lbl.setStyleSheet("font-weight: 700; font-size: 13.5px;")
            self.state_badge = QLabel()
            self.resume_badge = QLabel("Reprise HTTP Range")
            self.resume_badge.setStyleSheet(
                "color: #38bdf8; font-weight: 600; font-size: 11px; padding: 1px 6px;"
            )
            self.resume_badge.hide()

            top_row.addWidget(self.name_lbl)
            top_row.addWidget(self.state_badge)
            top_row.addWidget(self.resume_badge)
            top_row.addStretch()

            self.pause_btn = QPushButton("⏸ Pause")
            self.resume_btn = QPushButton("▶ Reprendre")
            self.retry_btn = QPushButton("↻ Relancer")
            self.cancel_btn = QPushButton("✕ Annuler")
            self.open_btn = QPushButton("📁 Ouvrir le dossier")
            self.remove_btn = QPushButton("Retirer")

            for b in (
                self.pause_btn,
                self.resume_btn,
                self.retry_btn,
                self.cancel_btn,
                self.open_btn,
                self.remove_btn,
            ):
                top_row.addWidget(b)
            layout.addLayout(top_row)

            self.url_lbl = QLabel()
            self.url_lbl.setObjectName("mutedLabel")
            layout.addWidget(self.url_lbl)

            self.bar = QProgressBar()
            self.bar.setRange(0, 1000)
            self.bar.setTextVisible(False)
            layout.addWidget(self.bar)

            metrics_row = QHBoxLayout()
            self.size_lbl = QLabel()
            self.speed_lbl = QLabel()
            self.eta_lbl = QLabel()
            metrics_row.addWidget(self.size_lbl)
            metrics_row.addStretch()
            metrics_row.addWidget(self.speed_lbl)
            metrics_row.addSpacing(14)
            metrics_row.addWidget(self.eta_lbl)
            layout.addLayout(metrics_row)

            self.issue_lbl = QLabel()
            self.issue_lbl.setWordWrap(True)
            self.issue_lbl.hide()
            layout.addWidget(self.issue_lbl)

            self.pause_btn.clicked.connect(lambda: _safe_call(lambda: manager.pause_task(task_id)))
            self.resume_btn.clicked.connect(
                lambda: _safe_call(lambda: manager.resume_task(task_id))
            )
            self.retry_btn.clicked.connect(lambda: _safe_call(lambda: manager.retry_task(task_id)))
            self.cancel_btn.clicked.connect(
                lambda: _safe_call(lambda: manager.cancel_task(task_id))
            )
            self.open_btn.clicked.connect(
                lambda: _safe_call(lambda: manager.open_task_folder(task_id))
            )
            self.remove_btn.clicked.connect(
                lambda: _safe_call(lambda: manager.remove_task(task_id))
            )

        def refresh_from(self, snap: TaskSnapshot) -> None:
            self.name_lbl.setText(snap.filename)
            label_txt, color = _state_presentation(snap)
            self.state_badge.setText(label_txt)
            self.state_badge.setStyleSheet(
                f"color: {color}; font-weight: 700; font-size: 11.5px; padding: 1px 7px;"
            )
            self.resume_badge.setVisible(snap.resumed_from_part)
            self.url_lbl.setText(snap.url)

            pct = snap.progress_percent if snap.progress_percent is not None else 0.0
            self.bar.setValue(int(round(pct * 10)))
            pct_str = (
                f"{snap.progress_percent:.1f} %"
                if snap.progress_percent is not None
                else "Taille en cours…"
            )
            self.size_lbl.setText(
                f"{format_bytes(snap.downloaded_bytes)} / {format_bytes(snap.total_bytes)} "
                f"({pct_str})"
            )
            self.speed_lbl.setText(f"Vitesse réelle : {format_speed(snap.speed_bps)}")
            eta_txt = (
                "Terminé"
                if snap.state is TaskState.COMPLETED
                else "Suspendu"
                if snap.state is TaskState.PAUSED
                else format_duration(snap.eta_seconds)
            )
            self.eta_lbl.setText(f"Temps restant : {eta_txt}")

            st = snap.state
            self.pause_btn.setVisible(st in {TaskState.RUNNING, TaskState.QUEUED})
            self.resume_btn.setVisible(st is TaskState.PAUSED)
            self.retry_btn.setVisible(st in {TaskState.FAILED, TaskState.CANCELLED})
            self.cancel_btn.setVisible(
                st in {TaskState.RUNNING, TaskState.QUEUED, TaskState.PAUSED}
            )
            self.open_btn.setVisible(st is TaskState.COMPLETED)
            self.remove_btn.setVisible(
                st in {TaskState.COMPLETED, TaskState.FAILED, TaskState.CANCELLED}
            )

            if st is TaskState.FAILED and snap.error_message:
                self.issue_lbl.setObjectName("errorBanner")
                self.issue_lbl.setText(f"⚠ {snap.error_message}")
                self.issue_lbl.show()
            elif snap.active_warning:
                self.issue_lbl.setObjectName("issueBanner")
                self.issue_lbl.setText(f"⚡ {snap.active_warning}")
                self.issue_lbl.show()
            elif snap.issues and st is TaskState.COMPLETED:
                self.issue_lbl.setObjectName("issueBanner")
                self.issue_lbl.setText(
                    f"✓ Terminé avec succès après {snap.retry_count} reprise(s) automatique(s)."
                )
                self.issue_lbl.show()
            else:
                self.issue_lbl.hide()

    class HistoryRowWidget(QFrame):
        """Entrée d'historique avec vérification de présence sur disque et bouton dossier."""

        def __init__(self, entry: HistoryEntry) -> None:
            super().__init__()
            self.setObjectName("itemCard")
            row = QHBoxLayout(self)
            row.setContentsMargins(12, 8, 12, 8)

            info_col = QVBoxLayout()
            status_map = {
                "completed": ("Terminé", "#10b981"),
                "failed": ("Échec", "#ef4444"),
                "cancelled": ("Annulé", "#94a3b8"),
            }
            st_txt, st_col = status_map.get(entry.status, (entry.status, "#94a3b8"))
            title_row = QHBoxLayout()
            name_lbl = QLabel(entry.filename)
            name_lbl.setStyleSheet("font-weight: 700;")
            st_lbl = QLabel(st_txt)
            st_lbl.setStyleSheet(f"color: {st_col}; font-weight: 700; font-size: 11.5px;")
            title_row.addWidget(name_lbl)
            title_row.addWidget(st_lbl)
            title_row.addStretch()
            info_col.addLayout(title_row)

            presence = (
                f"✓ Présent ({format_bytes(entry.size_bytes)})"
                if entry.file_exists
                else "⚠ Fichier déplacé ou supprimé"
                if entry.status == "completed"
                else (entry.error_message.splitlines()[0] if entry.error_message else "—")
            )
            retries_note = (
                f" · ↻ {entry.retries_used} reprise(s) auto" if entry.retries_used > 0 else ""
            )
            meta = QLabel(
                f"{presence} · Débit moyen : {format_speed(entry.average_speed_bps)} · "
                f"Durée : {format_duration(entry.duration_seconds)}{retries_note}"
            )
            meta.setObjectName("mutedLabel")
            info_col.addWidget(meta)
            row.addLayout(info_col, stretch=1)

            reopen_btn = QPushButton("📁 Rouvrir le dossier")
            reopen_btn.clicked.connect(
                lambda: _safe_call(lambda: manager.open_history_folder(entry.id))
            )
            redl_btn = QPushButton("↻ Retélécharger")
            redl_btn.clicked.connect(
                lambda: _safe_call(
                    lambda: manager.enqueue(entry.url, duplicate_policy=DuplicatePolicy.RENAME)
                )
            )
            del_btn = QPushButton("✕")
            del_btn.setFixedWidth(34)
            del_btn.clicked.connect(lambda: _remove_history_entry(entry.id))

            row.addWidget(reopen_btn)
            row.addWidget(redl_btn)
            row.addWidget(del_btn)

    prefs = settings_store.get()
    window = QMainWindow()
    window.setWindowTitle("OverLoad — Gestionnaire de téléchargements intelligent")
    window.resize(1180, 820)
    app_icon = create_app_icon()
    window.setWindowIcon(app_icon)

    root = QWidget()
    root.setObjectName("rootWidget")
    root_vbox = QVBoxLayout(root)
    root_vbox.setContentsMargins(16, 14, 16, 14)
    root_vbox.setSpacing(12)

    def _safe_call(fn: Any) -> Any:
        try:
            return fn()
        except OverloadError as exc:
            QMessageBox.warning(window, "OverLoad", str(exc))
            return None

    # 1. En-tête de télémétrie globale
    topbar = QFrame()
    topbar.setObjectName("panelCard")
    top_layout = QHBoxLayout(topbar)
    top_layout.setContentsMargins(14, 10, 14, 10)

    brand_col = QVBoxLayout()
    title_lbl = QLabel("⚡ OverLoad")
    title_lbl.setObjectName("titleLabel")
    sub_lbl = QLabel("Gestionnaire de téléchargements intelligent")
    sub_lbl.setObjectName("mutedLabel")
    brand_col.addWidget(title_lbl)
    brand_col.addWidget(sub_lbl)
    top_layout.addLayout(brand_col)
    top_layout.addSpacing(16)

    speed_box = QFrame()
    speed_box.setObjectName("metricBox")
    speed_box_layout = QHBoxLayout(speed_box)
    speed_box_layout.setContentsMargins(10, 6, 10, 6)
    speed_meta = QVBoxLayout()
    speed_caption = QLabel("VITESSE RÉELLE GLOBALE")
    speed_caption.setObjectName("mutedLabel")
    global_speed_lbl = QLabel("0 o/s")
    global_speed_lbl.setObjectName("metricValue")
    speed_meta.addWidget(speed_caption)
    speed_meta.addWidget(global_speed_lbl)
    sparkline = SpeedSparklineWidget()
    speed_box_layout.addLayout(speed_meta)
    speed_box_layout.addSpacing(8)
    speed_box_layout.addWidget(sparkline)
    top_layout.addWidget(speed_box)

    slots_box = QFrame()
    slots_box.setObjectName("metricBox")
    slots_layout = QVBoxLayout(slots_box)
    slots_layout.setContentsMargins(10, 6, 10, 6)
    slots_caption = QLabel("FILE ACTIVE")
    slots_caption.setObjectName("mutedLabel")
    slot_usage_lbl = QLabel("0 / 3 actifs")
    slot_usage_lbl.setObjectName("metricValue")
    queue_sub_lbl = QLabel("0 en attente · 0 en pause")
    queue_sub_lbl.setObjectName("mutedLabel")
    slots_layout.addWidget(slots_caption)
    slots_layout.addWidget(slot_usage_lbl)
    slots_layout.addWidget(queue_sub_lbl)
    top_layout.addWidget(slots_box)

    net_box = QFrame()
    net_box.setObjectName("metricBox")
    net_layout = QVBoxLayout(net_box)
    net_layout.setContentsMargins(10, 6, 10, 6)
    net_caption = QLabel("ÉTAT DE LA CONNEXION")
    net_caption.setObjectName("mutedLabel")
    net_status_lbl = QLabel("● Connexion stable")
    net_status_lbl.setStyleSheet("color: #10b981; font-weight: 700;")
    net_layout.addWidget(net_caption)
    net_layout.addWidget(net_status_lbl)
    top_layout.addWidget(net_box, stretch=1)

    open_dest_btn = QPushButton("📁 Ouvrir le dossier")
    change_dest_btn = QPushButton("📂 Dossier…")
    theme_btn = QPushButton("🌓 Thème")
    top_layout.addWidget(open_dest_btn)
    top_layout.addWidget(change_dest_btn)
    top_layout.addWidget(theme_btn)
    root_vbox.addWidget(topbar)

    # 2. Barre de réglages intelligents en direct
    controls_card = QFrame()
    controls_card.setObjectName("panelCard")
    controls_row = QHBoxLayout(controls_card)
    controls_row.setContentsMargins(14, 9, 14, 9)

    conc_spin = QSpinBox()
    conc_spin.setRange(1, 16)
    conc_spin.setValue(prefs.max_concurrent)

    speed_combo = QComboBox()
    presets = [
        ("Illimitée", 0),
        ("250 Ko/s", 250 * 1024),
        ("500 Ko/s", 500 * 1024),
        ("1 Mo/s", 1024 * 1024),
        ("2 Mo/s", 2 * 1024 * 1024),
        ("5 Mo/s", 5 * 1024 * 1024),
        ("10 Mo/s", 10 * 1024 * 1024),
        ("Personnalisée…", -1),
    ]
    for label, val in presets:
        speed_combo.addItem(label, val)

    custom_kbps_spin = QSpinBox()
    custom_kbps_spin.setRange(16, 1_000_000)
    custom_kbps_spin.setSuffix(" Ko/s")
    custom_kbps_spin.setSingleStep(100)
    custom_kbps_spin.setValue(750)
    custom_kbps_spin.hide()

    dup_combo = QComboBox()
    dup_combo.addItem("Demander confirmation", DuplicatePolicy.ASK.value)
    dup_combo.addItem("Ignorer automatiquement", DuplicatePolicy.SKIP.value)
    dup_combo.addItem("Renommer (« nom (2) »)", DuplicatePolicy.RENAME.value)
    idx_dup = dup_combo.findData(prefs.duplicate_policy)
    if idx_dup >= 0:
        dup_combo.setCurrentIndex(idx_dup)

    auto_retry_chk = QCheckBox("Reprise auto après erreur")
    auto_retry_chk.setChecked(prefs.auto_retry)
    retries_spin = QSpinBox()
    retries_spin.setRange(1, 10)
    retries_spin.setSuffix(" essais")
    retries_spin.setValue(max(1, prefs.max_retries))

    controls_row.addWidget(QLabel("Simultanés :"))
    controls_row.addWidget(conc_spin)
    controls_row.addSpacing(12)
    controls_row.addWidget(QLabel("Limite de vitesse :"))
    controls_row.addWidget(speed_combo)
    controls_row.addWidget(custom_kbps_spin)
    controls_row.addSpacing(12)
    controls_row.addWidget(QLabel("Fichiers déjà présents :"))
    controls_row.addWidget(dup_combo)
    controls_row.addSpacing(12)
    controls_row.addWidget(auto_retry_chk)
    controls_row.addWidget(retries_spin)
    controls_row.addStretch()
    root_vbox.addWidget(controls_card)

    # 3. Zone d'ajout (Lien unique + Lot de liens)
    composer_card = QFrame()
    composer_card.setObjectName("panelCard")
    composer_vbox = QVBoxLayout(composer_card)
    composer_vbox.setContentsMargins(14, 10, 14, 10)

    tabs = QTabWidget()

    single_page = QWidget()
    single_vbox = QVBoxLayout(single_page)
    single_row = QHBoxLayout()
    url_edit = QLineEdit()
    url_edit.setPlaceholderText(
        "Collez l'adresse directe HTTP(S) d'un fichier (ex. https://exemple.com/video.mp4)…"
    )
    paste_btn = QPushButton("📋 Coller")
    name_edit = QLineEdit()
    name_edit.setPlaceholderText("Nom du fichier (optionnel)")
    name_edit.setMaximumWidth(230)
    start_paused_chk = QCheckBox("Ajouter en pause")
    add_single_btn = QPushButton("⬇ Télécharger")
    add_single_btn.setObjectName("primaryBtn")

    single_row.addWidget(url_edit, stretch=1)
    single_row.addWidget(paste_btn)
    single_row.addWidget(name_edit)
    single_row.addWidget(start_paused_chk)
    single_row.addWidget(add_single_btn)
    single_vbox.addLayout(single_row)

    precheck_lbl = QLabel("")
    precheck_lbl.setObjectName("mutedLabel")
    precheck_lbl.hide()
    single_vbox.addWidget(precheck_lbl)
    tabs.addTab(single_page, "Lien unique")

    batch_page = QWidget()
    batch_vbox = QVBoxLayout(batch_page)
    batch_edit = QPlainTextEdit()
    batch_edit.setPlaceholderText(
        "Collez une liste de liens (un par ligne, les commentaires # sont ignorés)…"
    )
    batch_edit.setMaximumHeight(96)
    batch_btns_row = QHBoxLayout()
    import_txt_btn = QPushButton("📄 Importer un fichier .txt…")
    inspect_batch_btn = QPushButton("🔍 Vérifier les liens & doublons")
    batch_info_lbl = QLabel("")
    batch_info_lbl.setObjectName("mutedLabel")
    start_batch_btn = QPushButton("⬇ Lancer le lot")
    start_batch_btn.setObjectName("primaryBtn")
    batch_btns_row.addWidget(import_txt_btn)
    batch_btns_row.addWidget(inspect_batch_btn)
    batch_btns_row.addWidget(batch_info_lbl, stretch=1)
    batch_btns_row.addWidget(start_batch_btn)
    batch_vbox.addWidget(batch_edit)
    batch_vbox.addLayout(batch_btns_row)
    tabs.addTab(batch_page, "Téléchargement par lots (liste de liens)")

    from overload.ui.analyzer import create_analyzer_widget

    tabs.addTab(create_analyzer_widget(), "Analyse multimédia")
    composer_vbox.addWidget(tabs)
    root_vbox.addWidget(composer_card)

    # 4. Diviseur vertical : Téléchargements actifs (haut) + Historique SQLite (bas)
    splitter = QSplitter(Qt.Orientation.Vertical)

    tasks_panel = QFrame()
    tasks_panel.setObjectName("panelCard")
    tasks_vbox = QVBoxLayout(tasks_panel)
    tasks_vbox.setContentsMargins(14, 10, 14, 10)

    tasks_hdr = QHBoxLayout()
    tasks_title = QLabel("Téléchargements")
    tasks_title.setObjectName("sectionTitle")
    tasks_hdr.addWidget(tasks_title)
    tasks_hdr.addSpacing(10)

    active_filter = {"value": "all"}
    filter_buttons: dict[str, QPushButton] = {}
    for key, label in [
        ("all", "Tous"),
        ("running", "En cours"),
        ("queued", "En attente"),
        ("paused", "En pause"),
        ("failed", "Problèmes"),
    ]:
        btn = QPushButton(f"{label} (0)")
        btn.setCheckable(True)
        btn.setChecked(key == "all")
        filter_buttons[key] = btn
        tasks_hdr.addWidget(btn)

    tasks_hdr.addStretch()
    pause_all_btn = QPushButton("⏸ Tout suspendre")
    resume_all_btn = QPushButton("▶ Tout reprendre")
    clear_done_btn = QPushButton("Nettoyer les terminés")
    tasks_hdr.addWidget(pause_all_btn)
    tasks_hdr.addWidget(resume_all_btn)
    tasks_hdr.addWidget(clear_done_btn)
    tasks_vbox.addLayout(tasks_hdr)

    tasks_scroll = QScrollArea()
    tasks_scroll.setWidgetResizable(True)
    tasks_container = QWidget()
    tasks_list_layout = QVBoxLayout(tasks_container)
    tasks_list_layout.setContentsMargins(0, 0, 4, 0)
    tasks_list_layout.setSpacing(8)
    empty_tasks_lbl = QLabel(
        "Aucun téléchargement actif. Collez une adresse HTTP(S) ou un lot de liens ci-dessus."
    )
    empty_tasks_lbl.setObjectName("mutedLabel")
    empty_tasks_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
    tasks_list_layout.addWidget(empty_tasks_lbl)
    tasks_list_layout.addStretch()
    tasks_scroll.setWidget(tasks_container)
    tasks_vbox.addWidget(tasks_scroll)
    splitter.addWidget(tasks_panel)

    # Panneau Historique persistant
    hist_panel = QFrame()
    hist_panel.setObjectName("panelCard")
    hist_vbox = QVBoxLayout(hist_panel)
    hist_vbox.setContentsMargins(14, 10, 14, 10)

    hist_hdr = QHBoxLayout()
    hist_title = QLabel("Historique des téléchargements")
    hist_title.setObjectName("sectionTitle")
    hist_hdr.addWidget(hist_title)
    hist_hdr.addStretch()
    hist_search = QLineEdit()
    hist_search.setPlaceholderText("Rechercher un fichier ou une adresse…")
    hist_search.setMaximumWidth(260)
    hist_status = QComboBox()
    hist_status.addItem("Tous les états", "all")
    hist_status.addItem("Terminés", "completed")
    hist_status.addItem("Échecs", "failed")
    hist_status.addItem("Annulés", "cancelled")
    clear_hist_btn = QPushButton("Effacer l'historique")
    hist_hdr.addWidget(hist_search)
    hist_hdr.addWidget(hist_status)
    hist_hdr.addWidget(clear_hist_btn)
    hist_vbox.addLayout(hist_hdr)

    hist_scroll = QScrollArea()
    hist_scroll.setWidgetResizable(True)
    hist_container = QWidget()
    hist_list_layout = QVBoxLayout(hist_container)
    hist_list_layout.setContentsMargins(0, 0, 4, 0)
    hist_list_layout.setSpacing(6)
    hist_list_layout.addStretch()
    hist_scroll.setWidget(hist_container)
    hist_vbox.addWidget(hist_scroll)
    splitter.addWidget(hist_panel)
    splitter.setStretchFactor(0, 3)
    splitter.setStretchFactor(1, 2)
    root_vbox.addWidget(splitter, stretch=1)

    # Gestionnaires d'événements et synchronisation temps réel
    card_widgets: dict[str, TaskCardWidget] = {}
    last_history_sig = {"value": None}

    def set_filter(chosen: str) -> None:
        active_filter["value"] = chosen
        for k, b in filter_buttons.items():
            b.setChecked(k == chosen)
        refresh_ui()

    for key, btn in filter_buttons.items():
        btn.clicked.connect(lambda _checked=False, k=key: set_filter(k))

    def _remove_history_entry(entry_id: str) -> None:
        history.remove_entry(entry_id)
        last_history_sig["value"] = None
        refresh_ui()

    def on_precheck_text_changed(text: str) -> None:
        cleaned = text.strip()
        if not cleaned:
            precheck_lbl.hide()
            return
        res = manager.inspect_batch(cleaned)
        if res["duplicates"]:
            precheck_lbl.setText(f"⚠ Détection doublon : {res['duplicates'][0]['reason']}")
        elif res["rejected"]:
            first_line = res["rejected"][0]["error"].splitlines()[0]
            precheck_lbl.setText(f"✕ {first_line}")
        elif res["valid"]:
            precheck_lbl.setText(f"✓ Prêt à enregistrer sous « {res['valid'][0]['filename']} »")
        precheck_lbl.show()

    def on_add_single() -> None:
        raw = url_edit.text().strip()
        if not raw:
            return
        custom_name = name_edit.text().strip() or None
        paused = start_paused_chk.isChecked()
        try:
            snap = manager.enqueue(raw, filename=custom_name, start_paused=paused)
            if snap is not None:
                url_edit.clear()
                name_edit.clear()
                precheck_lbl.hide()
        except DuplicateDetectedError as dup_err:
            existing_path = dup_err.match.existing_path
            msg = QMessageBox(window)
            msg.setWindowTitle("Fichier déjà présent")
            msg.setText(dup_err.match.reason)
            msg.setInformativeText(f"Emplacement : {existing_path}")
            open_existing = msg.addButton(
                "📁 Ouvrir le dossier existant", QMessageBox.ButtonRole.ActionRole
            )
            rename_copy = msg.addButton(
                "Télécharger une copie (« (2) »)", QMessageBox.ButtonRole.AcceptRole
            )
            msg.addButton("Ignorer", QMessageBox.ButtonRole.RejectRole)
            msg.exec()
            clicked = msg.clickedButton()
            if clicked == open_existing:
                _safe_call(lambda: open_folder(existing_path))
            elif clicked == rename_copy:
                _safe_call(
                    lambda: manager.enqueue(
                        raw,
                        filename=custom_name,
                        duplicate_policy=DuplicatePolicy.RENAME,
                        start_paused=paused,
                    )
                )
                url_edit.clear()
                name_edit.clear()
        except OverloadError as exc:
            QMessageBox.warning(window, "Adresse refusée", str(exc))
        refresh_ui()

    def on_inspect_batch() -> None:
        raw = batch_edit.toPlainText()
        if not raw.strip():
            return
        res = manager.inspect_batch(raw)
        batch_info_lbl.setText(
            f"Analyse : {len(res['valid'])} prêt(s) · "
            f"{len(res['duplicates'])} déjà présent(s) · "
            f"{len(res['rejected'])} invalide(s)."
        )

    def on_start_batch() -> None:
        raw = batch_edit.toPlainText()
        pol = manager.settings().duplicate_policy
        effective = DuplicatePolicy.SKIP if pol is DuplicatePolicy.ASK else pol
        res = _safe_call(
            lambda: manager.enqueue_batch(
                raw,
                duplicate_policy=effective,
                start_paused=start_paused_chk.isChecked(),
            )
        )
        if res is not None:
            if res.added:
                batch_edit.clear()
            batch_info_lbl.setText(
                f"Lot lancé : {len(res.added)} ajouté(s), "
                f"{len(res.skipped_duplicates)} doublon(s) ignoré(s), "
                f"{len(res.rejected)} rejeté(s)."
            )
            refresh_ui()

    def on_import_txt() -> None:
        chosen, _ = QFileDialog.getOpenFileName(
            window, "Importer une liste de liens", "", "Fichiers texte (*.txt);;Tous (*)"
        )
        if chosen:
            content = Path(chosen).read_text(encoding="utf-8", errors="ignore")
            cur = batch_edit.toPlainText().strip()
            batch_edit.setPlainText(f"{cur}\n{content}".strip() if cur else content)
            on_inspect_batch()

    def on_speed_changed() -> None:
        val = int(speed_combo.currentData())
        if val == -1:
            custom_kbps_spin.show()
            bps: int | None = custom_kbps_spin.value() * 1024
        else:
            custom_kbps_spin.hide()
            bps = val if val > 0 else None
        manager.set_speed_limit_bps(bps)
        settings_store.update(speed_limit_bps=bps)

    def on_choose_folder() -> None:
        current_dir = str(manager.settings().destination_dir)
        folder = QFileDialog.getExistingDirectory(
            window, "Choisir le dossier de téléchargements", current_dir
        )
        if folder:
            _safe_call(lambda: manager.set_destination_dir(folder))
            settings_store.update(destination_dir=folder)

    def on_toggle_theme() -> None:
        new_theme = "light" if settings_store.get().theme == "dark" else "dark"
        settings_store.update(theme=new_theme)
        window.setStyleSheet(build_stylesheet(new_theme))

    def refresh_ui() -> None:
        overview = manager.status_overview()
        global_speed_lbl.setText(overview["total_speed_human"])
        sparkline.push(float(overview["total_speed_bps"]))

        c = overview["counts"]
        slot_usage_lbl.setText(f"{c['running']} / {overview['settings']['max_concurrent']} actifs")
        queue_sub_lbl.setText(f"{c['queued']} en attente · {c['paused']} en pause")

        health = overview["network_health"]
        health_colors = {"healthy": "#10b981", "degraded": "#f59e0b"}
        color = health_colors.get(health, "#ef4444")
        net_status_lbl.setText(f"● {overview['network_message']}")
        net_status_lbl.setStyleSheet(f"color: {color}; font-weight: 700;")

        snaps = manager.list_tasks()
        probs = c["failed"] + overview["retrying_count"] + overview["stalled_count"]
        counts_by_filter = {
            "all": len(snaps),
            "running": c["running"],
            "queued": c["queued"],
            "paused": c["paused"],
            "failed": probs,
        }
        labels = {
            "all": "Tous",
            "running": "En cours",
            "queued": "En attente",
            "paused": "En pause",
            "failed": "Problèmes",
        }
        for key, btn in filter_buttons.items():
            btn.setText(f"{labels[key]} ({counts_by_filter[key]})")

        fval = active_filter["value"]
        visible = [
            s
            for s in snaps
            if fval == "all"
            or (fval == "failed" and (s.state is TaskState.FAILED or s.retrying or s.stalled))
            or s.state.value == fval
        ]
        visible_ids = {s.id for s in visible}
        for tid in list(card_widgets):
            if tid not in visible_ids:
                w = card_widgets.pop(tid)
                tasks_list_layout.removeWidget(w)
                w.deleteLater()

        empty_tasks_lbl.setVisible(len(visible) == 0)
        for idx, snap in enumerate(visible):
            card = card_widgets.get(snap.id)
            if card is None:
                card = TaskCardWidget(snap.id)
                card_widgets[snap.id] = card
                tasks_list_layout.insertWidget(idx, card)
            card.refresh_from(snap)

        entries = history.list_entries(
            status=str(hist_status.currentData()),
            query=hist_search.text(),
            limit=80,
        )
        sig = tuple((e.id, e.status, e.file_exists) for e in entries)
        if sig != last_history_sig["value"]:
            last_history_sig["value"] = sig
            while hist_list_layout.count() > 1:
                item = hist_list_layout.takeAt(0)
                if item.widget():
                    item.widget().deleteLater()
            for idx, entry in enumerate(entries):
                hist_list_layout.insertWidget(idx, HistoryRowWidget(entry))

    # Connexions des signaux
    open_dest_btn.clicked.connect(lambda: _safe_call(manager.open_downloads_folder))
    change_dest_btn.clicked.connect(on_choose_folder)
    theme_btn.clicked.connect(on_toggle_theme)

    conc_spin.valueChanged.connect(
        lambda v: (manager.set_max_concurrent(int(v)), settings_store.update(max_concurrent=int(v)))
    )
    speed_combo.currentIndexChanged.connect(lambda _i: on_speed_changed())
    custom_kbps_spin.valueChanged.connect(
        lambda v: (
            manager.set_speed_limit_bps(int(v) * 1024),
            settings_store.update(speed_limit_bps=int(v) * 1024),
        )
    )
    dup_combo.currentIndexChanged.connect(
        lambda _i: (
            manager.set_duplicate_policy(str(dup_combo.currentData())),
            settings_store.update(duplicate_policy=str(dup_combo.currentData())),
        )
    )
    auto_retry_chk.toggled.connect(
        lambda checked: (
            manager.set_auto_retry(checked, max_retries=retries_spin.value()),
            settings_store.update(auto_retry=checked),
        )
    )
    retries_spin.valueChanged.connect(
        lambda n: (
            manager.set_auto_retry(auto_retry_chk.isChecked(), max_retries=int(n)),
            settings_store.update(max_retries=int(n)),
        )
    )

    paste_btn.clicked.connect(lambda: url_edit.setText(QApplication.clipboard().text().strip()))
    url_edit.textChanged.connect(on_precheck_text_changed)
    url_edit.returnPressed.connect(on_add_single)
    add_single_btn.clicked.connect(on_add_single)

    import_txt_btn.clicked.connect(on_import_txt)
    inspect_batch_btn.clicked.connect(on_inspect_batch)
    start_batch_btn.clicked.connect(on_start_batch)

    pause_all_btn.clicked.connect(manager.pause_all)
    resume_all_btn.clicked.connect(manager.resume_all)
    clear_done_btn.clicked.connect(manager.clear_finished)

    hist_search.textChanged.connect(lambda _t: refresh_ui())
    hist_status.currentIndexChanged.connect(lambda _i: refresh_ui())
    clear_hist_btn.clicked.connect(
        lambda: (history.clear(), last_history_sig.update(value=None), refresh_ui())
    )

    # Synchronise le sélecteur initial de vitesse avec les préférences sauvegardées
    if prefs.speed_limit_bps:
        preset_idx = speed_combo.findData(prefs.speed_limit_bps)
        if preset_idx >= 0:
            speed_combo.setCurrentIndex(preset_idx)
        else:
            custom_kbps_spin.setValue(max(16, prefs.speed_limit_bps // 1024))
            speed_combo.setCurrentIndex(speed_combo.findData(-1))

    window.setStyleSheet(build_stylesheet(prefs.theme))
    window.setCentralWidget(root)

    timer = QTimer(window)
    timer.timeout.connect(refresh_ui)
    timer.start(250)
    refresh_ui()
    return window


def launch_desktop_app(
    *,
    destination_dir: Path | None = None,
    data_dir: Path | None = None,
    self_test: bool = False,
) -> int:
    """Démarre l'application native OverLoad (point d'entrée principal de `OverLoad.exe`)."""
    from PySide6.QtWidgets import QApplication

    base_data = data_dir or default_data_dir()
    settings_store = SettingsStore(base_data / "settings.json")
    prefs = settings_store.get()

    dest = Path(destination_dir) if destination_dir is not None else Path(prefs.destination_dir)
    try:
        dest.mkdir(parents=True, exist_ok=True)
    except OSError:
        dest = default_downloads_dir()

    history = DownloadHistoryStore(base_data / "library.db")
    manager = DownloadManager(
        dest,
        history=history,
        max_concurrent=prefs.max_concurrent,
        speed_limit_bps=prefs.speed_limit_bps,
        auto_retry=prefs.auto_retry,
        max_retries=prefs.max_retries,
        duplicate_policy=DuplicatePolicy(prefs.duplicate_policy),
    )

    app = QApplication.instance() or QApplication(sys.argv)
    app.setApplicationName("OverLoad")
    app.setWindowIcon(create_app_icon())

    window = create_main_window(manager, history, settings_store)
    window.show()

    if self_test:
        app.processEvents()
        window.close()
        manager.shutdown()
        history.close()
        return 0

    app.aboutToQuit.connect(manager.shutdown)
    app.aboutToQuit.connect(history.close)
    return int(app.exec())
