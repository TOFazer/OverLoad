"""Pages de l'interface : accueil, téléchargements, paramètres, aide."""

from __future__ import annotations

import shutil
from collections.abc import Sequence
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from overload.app import strings as S
from overload.core.formatting import format_bytes, format_duration, format_speed
from overload.core.settings import THEMES, Settings
from overload.downloads.manager import TaskView
from overload.downloads.state import TaskState


def _state_label(state: TaskState) -> str:
    return S.STATE_LABELS[state.value]


def _name_item(text: str) -> QTableWidgetItem:
    item = QTableWidgetItem(text)
    item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
    return item


class HomePage(QWidget):
    submitted = Signal(str)
    show_downloads = Signal()
    open_download_folder = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._download_dir = Path.home()

        title = QLabel(S.HOME_TITLE)
        title.setObjectName("title")
        subtitle = QLabel(S.HOME_SUBTITLE)
        subtitle.setWordWrap(True)

        self.url_input = QLineEdit()
        self.url_input.setPlaceholderText(S.URL_PLACEHOLDER)
        self.url_input.setAccessibleName("Adresse du fichier à télécharger")
        self.url_input.returnPressed.connect(self._on_submit)
        self.download_button = QPushButton(S.BTN_DOWNLOAD)
        self.download_button.setMinimumWidth(140)
        self.download_button.setDefault(True)
        self.download_button.setAccessibleName("Lancer le téléchargement")
        self.download_button.clicked.connect(self._on_submit)

        row = QHBoxLayout()
        row.addWidget(self.url_input, 1)
        row.addWidget(self.download_button)

        self.message = QLabel("")
        self.message.setWordWrap(True)
        self.message.setAccessibleName("Résultat de l'action")

        recent_title = QLabel(S.RECENT_TITLE)
        recent_title.setStyleSheet("font-weight: 600; margin-top: 12px;")
        self.recent = QLabel(S.RECENT_EMPTY)
        self.recent.setWordWrap(True)
        self.recent.setTextFormat(Qt.TextFormat.PlainText)

        self.disk = QLabel("")
        self.disk.setAccessibleName("Espace disque disponible")

        buttons = QHBoxLayout()
        show = QPushButton(S.BTN_SHOW_DOWNLOADS)
        show.clicked.connect(self.show_downloads)
        folder = QPushButton(S.BTN_OPEN_FOLDER)
        folder.clicked.connect(self.open_download_folder)
        buttons.addWidget(show)
        buttons.addWidget(folder)
        buttons.addStretch(1)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(10)
        layout.addWidget(title)
        layout.addWidget(subtitle)
        layout.addLayout(row)
        layout.addWidget(self.message)
        layout.addWidget(recent_title)
        layout.addWidget(self.recent)
        layout.addStretch(1)
        layout.addWidget(self.disk)
        layout.addLayout(buttons)

    def set_download_dir(self, folder: Path) -> None:
        self._download_dir = folder
        self.refresh_disk()

    def refresh_disk(self) -> None:
        folder = self._download_dir
        probe = folder if folder.exists() else folder.parent
        try:
            free = shutil.disk_usage(probe).free
            self.disk.setText(S.DISK_LABEL.format(folder=folder, free=format_bytes(free)))
        except OSError:
            self.disk.setText(S.DISK_UNKNOWN)

    def show_message(self, text: str) -> None:
        self.message.setText(text)

    def update_recent(self, views: Sequence[TaskView]) -> None:
        if not views:
            self.recent.setText(S.RECENT_EMPTY)
            return
        lines = [f"• {v.name} — {_state_label(v.state)}" for v in list(views)[-5:][::-1]]
        self.recent.setText("\n".join(lines))

    def _on_submit(self) -> None:
        text = self.url_input.text().strip()
        if not text:
            self.show_message(S.MSG_EMPTY_URL)
            return
        self.submitted.emit(text)


class DownloadsPage(QWidget):
    action_requested = Signal(str, str)  # (action, task_id)

    COLUMNS = S.COLUMNS

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        title = QLabel(S.DOWNLOADS_TITLE)
        title.setObjectName("title")

        self.table = QTableWidget(0, len(self.COLUMNS))
        self.table.setHorizontalHeaderLabels(self.COLUMNS)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.table.setAccessibleName("Liste des téléchargements")
        self.table.itemSelectionChanged.connect(self._on_selection)

        self.empty = QLabel(S.DOWNLOADS_EMPTY)
        self.empty.setWordWrap(True)

        self._buttons: dict[str, QPushButton] = {}
        bar = QHBoxLayout()
        for key, label in [
            ("pause", S.BTN_PAUSE),
            ("cancel", S.BTN_CANCEL),
            ("retry", S.BTN_RETRY),
            ("open_file", S.BTN_OPEN_FILE),
            ("reveal", S.BTN_REVEAL),
            ("open_dir", S.BTN_OPEN_DIR),
            ("copy", S.BTN_COPY_PATH),
        ]:
            button = QPushButton(label)
            button.setEnabled(False)
            if key == "reveal":
                button.setToolTip(S.TIP_REVEAL)
            button.clicked.connect(lambda _=False, k=key: self._emit(k))
            self._buttons[key] = button
            bar.addWidget(button)
        bar.addStretch(1)

        self.details = QLabel(S.DETAILS_NONE)
        self.details.setWordWrap(True)
        self.details.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.details.setAccessibleName("Détails de la tâche sélectionnée")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.addWidget(title)
        layout.addWidget(self.empty)
        layout.addWidget(self.table, 1)
        layout.addLayout(bar)
        layout.addWidget(self.details)
        self._views: dict[str, TaskView] = {}

    def selected_id(self) -> str | None:
        rows = self.table.selectionModel().selectedRows()
        if not rows:
            return None
        item = self.table.item(rows[0].row(), 0)
        return item.data(Qt.ItemDataRole.UserRole) if item else None

    def update_views(self, views: Sequence[TaskView]) -> None:
        keep = self.selected_id()
        self._views = {v.id: v for v in views}
        self.table.setRowCount(len(views))
        for row, view in enumerate(views):
            cells = [
                _name_item(view.name),
                _name_item(view.host or "—"),
                _name_item(_state_label(view.state)),
                _name_item("—" if view.progress is None else f"{view.progress * 100:.0f} %"),
                _name_item(format_speed(view.speed) if view.state is TaskState.RUNNING else "—"),
                _name_item(format_duration(view.eta_seconds)),
                _name_item(str(view.directory)),
            ]
            for col, cell in enumerate(cells):
                if col == 0:
                    cell.setData(Qt.ItemDataRole.UserRole, view.id)
                self.table.setItem(row, col, cell)
        self.empty.setVisible(not views)
        if keep is not None:
            for row, view in enumerate(views):
                if view.id == keep:
                    self.table.selectRow(row)
                    break
        self._refresh_buttons()

    def _on_selection(self) -> None:
        self._refresh_buttons()

    def _refresh_buttons(self) -> None:
        view = self._views.get(self.selected_id() or "")
        if view is None:
            for button in self._buttons.values():
                button.setEnabled(False)
            self.details.setText(S.DETAILS_NONE)
            return
        state = view.state
        self._buttons["pause"].setText(S.BTN_RESUME if state is TaskState.PAUSED else S.BTN_PAUSE)
        self._buttons["pause"].setEnabled(state in (TaskState.RUNNING, TaskState.PAUSED))
        self._buttons["cancel"].setEnabled(
            state in (TaskState.QUEUED, TaskState.RUNNING, TaskState.PAUSED)
        )
        self._buttons["retry"].setEnabled(state in (TaskState.FAILED, TaskState.CANCELLED))
        has_file = view.result_path is not None
        self._buttons["open_file"].setEnabled(has_file)
        self._buttons["reveal"].setEnabled(has_file)
        self._buttons["copy"].setEnabled(view.target is not None)
        self._buttons["open_dir"].setEnabled(True)
        lines = []
        if view.error:
            lines.append(S.DETAILS_ERROR_PREFIX + view.error)
        if view.target is not None:
            lines.append(S.DETAILS_PATH_PREFIX + str(view.target))
        self.details.setText("\n".join(lines) or _state_label(state))

    def _emit(self, key: str) -> None:
        task_id = self.selected_id()
        if task_id:
            self.action_requested.emit(key, task_id)


class SettingsPage(QWidget):
    saved = Signal(object)  # Settings
    open_logs = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        title = QLabel(S.SETTINGS_TITLE)
        title.setObjectName("title")

        self.folder = QLineEdit()
        self.folder.setAccessibleName(S.SETTINGS_FOLDER)
        browse = QPushButton(S.BTN_BROWSE)
        browse.clicked.connect(self._browse)
        folder_row = QHBoxLayout()
        folder_row.addWidget(self.folder, 1)
        folder_row.addWidget(browse)

        self.parallel = QSpinBox()
        self.parallel.setRange(1, 4)
        self.parallel.setAccessibleName(S.SETTINGS_PARALLEL)
        self.theme = QComboBox()
        for key in THEMES:
            self.theme.addItem(S.THEME_LABELS[key], key)
        self.theme.setAccessibleName(S.SETTINGS_THEME)

        form = QFormLayout()
        form.addRow(S.SETTINGS_FOLDER, folder_row)
        form.addRow(S.SETTINGS_PARALLEL, self.parallel)
        form.addRow("", QLabel(S.SETTINGS_PARALLEL_HELP))
        form.addRow(S.SETTINGS_THEME, self.theme)

        self.message = QLabel("")
        self.message.setWordWrap(True)
        save = QPushButton(S.BTN_SAVE)
        save.clicked.connect(self._save)

        self.storage = QLabel("")
        self.storage.setWordWrap(True)
        self.storage.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        logs = QPushButton(S.BTN_OPEN_LOGS)
        logs.clicked.connect(self.open_logs)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.addWidget(title)
        layout.addLayout(form)
        layout.addWidget(self.message)
        layout.addWidget(save, 0, Qt.AlignmentFlag.AlignLeft)
        layout.addSpacing(16)
        storage_title = QLabel(S.SETTINGS_STORAGE)
        storage_title.setStyleSheet("font-weight: 600;")
        layout.addWidget(storage_title)
        layout.addWidget(self.storage)
        layout.addWidget(logs, 0, Qt.AlignmentFlag.AlignLeft)
        layout.addStretch(1)

    def load(self, settings: Settings) -> None:
        self.folder.setText(settings.download_dir)
        self.parallel.setValue(settings.max_parallel)
        index = self.theme.findData(settings.theme)
        self.theme.setCurrentIndex(max(index, 0))

    def set_storage(self, data_path: Path, logs_path: Path) -> None:
        self.storage.setText(
            S.SETTINGS_DATA.format(path=data_path) + "\n" + S.SETTINGS_LOGS.format(path=logs_path)
        )

    def _browse(self) -> None:
        chosen = QFileDialog.getExistingDirectory(self, S.SETTINGS_FOLDER, self.folder.text())
        if chosen:
            self.folder.setText(chosen)

    def _save(self) -> None:
        folder = Path(self.folder.text().strip())
        try:
            folder.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            self.message.setText(S.SETTINGS_BAD_FOLDER.format(error=exc.strerror or exc))
            return
        settings = Settings(
            download_dir=str(folder),
            max_parallel=self.parallel.value(),
            theme=self.theme.currentData(),
        )
        self.message.setText(S.SETTINGS_SAVED)
        self.saved.emit(settings)


class HelpPage(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        title = QLabel(S.HELP_TITLE)
        title.setObjectName("title")
        body = QTextBrowser()
        body.setOpenExternalLinks(True)
        body.setHtml(S.HELP_BODY)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.addWidget(title)
        layout.addWidget(body, 1)


def copy_to_clipboard(text: str) -> None:
    QGuiApplication.clipboard().setText(text)
