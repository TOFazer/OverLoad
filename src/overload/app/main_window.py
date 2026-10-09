"""Fenêtre principale d'OverLoad : navigation latérale et pages."""

from __future__ import annotations

import logging
from pathlib import Path

from PySide6.QtCore import QSize, QTimer
from PySide6.QtGui import QIcon, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QStackedWidget,
    QWidget,
)

from overload.app import strings as S
from overload.app.pages import DownloadsPage, HelpPage, HomePage, SettingsPage, copy_to_clipboard
from overload.app.theme import apply_theme
from overload.core.errors import OverloadError
from overload.core.paths import logs_dir, resource_path
from overload.core.settings import SECTIONS, Settings, save_settings
from overload.downloads import actions
from overload.downloads.manager import DownloadManager
from overload.downloads.state import TaskState

log = logging.getLogger(__name__)
REFRESH_MS = 400


class MainWindow(QMainWindow):
    def __init__(
        self,
        settings: Settings,
        settings_path: Path,
        manager: DownloadManager,
    ) -> None:
        super().__init__()
        self.settings = settings
        self._settings_path = settings_path
        self._manager = manager

        self.setWindowTitle(S.APP_TITLE)
        self.setMinimumSize(900, 600)
        icon = resource_path("overload.ico")
        if icon.exists():
            self.setWindowIcon(QIcon(str(icon)))

        self.home = HomePage()
        self.downloads = DownloadsPage()
        self.settings_page = SettingsPage()
        self.help = HelpPage()
        self.stack = QStackedWidget()
        for page in (self.home, self.downloads, self.settings_page, self.help):
            self.stack.addWidget(page)

        self.nav = QListWidget()
        self.nav.setObjectName("nav")
        self.nav.setFixedWidth(190)
        self.nav.setAccessibleName("Navigation principale")
        self.nav.setSpacing(4)
        for key in SECTIONS:
            item = QListWidgetItem(S.NAV[key])
            item.setSizeHint(QSize(160, 42))
            self.nav.addItem(item)
        self.nav.currentRowChanged.connect(self.stack.setCurrentIndex)

        central = QWidget()
        layout = QHBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self.nav)
        layout.addWidget(self.stack, 1)
        self.setCentralWidget(central)

        self.home.submitted.connect(self._on_submit)
        self.home.show_downloads.connect(lambda: self._show("downloads"))
        self.home.open_download_folder.connect(self._open_download_folder)
        self.downloads.action_requested.connect(self._on_action)
        self.settings_page.saved.connect(self._on_settings_saved)
        self.settings_page.open_logs.connect(self._open_logs)

        for index, key in enumerate(SECTIONS, start=1):
            shortcut = QShortcut(QKeySequence(f"Ctrl+{index}"), self)
            shortcut.activated.connect(lambda k=key: self._show(k))
        focus_shortcut = QShortcut(QKeySequence("Ctrl+L"), self)
        focus_shortcut.activated.connect(lambda: self._show("home"))

        self.settings_page.load(settings)
        self.settings_page.set_storage(settings_path.parent, logs_dir())
        self.home.set_download_dir(Path(settings.download_dir))
        self._show(settings.last_section)

        self.status = self.statusBar()
        self._timer = QTimer(self)
        self._timer.timeout.connect(self.refresh)
        self._timer.start(REFRESH_MS)
        self.refresh()

    # ----- navigation ------------------------------------------------------
    def _show(self, key: str) -> None:
        self.nav.setCurrentRow(SECTIONS.index(key))
        self.stack.setCurrentIndex(SECTIONS.index(key))
        if key == "home":
            self.home.url_input.setFocus()

    # ----- rafraîchissement ------------------------------------------------
    def refresh(self) -> None:
        views = self._manager.snapshot()
        self.downloads.update_views(views)
        self.home.update_recent(views)
        active = self._manager.active_count()
        self.status.showMessage(
            f"{active} téléchargement(s) en cours" if active else "Prêt",
        )

    # ----- commandes -------------------------------------------------------
    def _on_submit(self, url: str) -> None:
        try:
            self._manager.submit(url, Path(self.settings.download_dir))
        except OverloadError as exc:
            self.home.show_message(f"Erreur : {exc}")
            log.info("Adresse refusée : %s", exc.what)
            return
        self.home.url_input.clear()
        self.home.show_message(S.MSG_ADDED)
        self.refresh()

    def _on_action(self, action: str, task_id: str) -> None:
        try:
            view = self._manager.get(task_id)
            base = Path(self.settings.download_dir)
            if action == "pause":
                if view.state is TaskState.PAUSED:
                    self._manager.resume(task_id)
                else:
                    self._manager.pause(task_id)
            elif action == "cancel":
                self._manager.cancel(task_id)
            elif action == "retry":
                self._manager.retry(task_id)
            elif action == "open_file" and view.result_path:
                actions.open_file(view.result_path, base)
            elif action == "reveal" and view.result_path:
                actions.reveal_file(view.result_path, base)
            elif action == "open_dir":
                actions.open_folder(view.directory)
            elif action == "copy" and view.target:
                copy_to_clipboard(str(view.target))
                self.status.showMessage(S.COPIED, 4000)
        except OverloadError as exc:
            QMessageBox.warning(self, S.ACTION_ERROR_TITLE, str(exc))
        self.refresh()

    def _on_settings_saved(self, new: Settings) -> None:
        self.settings = new.sanitized()
        try:
            save_settings(self._settings_path, self.settings)
        except OSError as exc:
            log.error("Enregistrement des réglages impossible : %s", exc)
            self.settings_page.message.setText(
                f"Erreur : impossible d'enregistrer les paramètres ({exc.strerror or exc})."
            )
            return
        self.home.set_download_dir(Path(self.settings.download_dir))
        apply_theme(QApplication.instance(), self.settings.theme)
        self.settings_page.message.setText(S.SETTINGS_SAVED + " " + S.SETTINGS_PARALLEL_HELP)

    def _open_download_folder(self) -> None:
        try:
            actions.open_folder(Path(self.settings.download_dir))
        except OverloadError as exc:
            QMessageBox.warning(self, S.ACTION_ERROR_TITLE, str(exc))

    def _open_logs(self) -> None:
        try:
            actions.open_folder(logs_dir())
        except OverloadError as exc:
            QMessageBox.warning(self, S.ACTION_ERROR_TITLE, str(exc))

    # ----- fermeture -------------------------------------------------------
    def closeEvent(self, event) -> None:  # noqa: N802 - nom imposé par Qt
        active = self._manager.active_count()
        if active:
            answer = QMessageBox.question(
                self,
                S.APP_TITLE,
                f"{active} téléchargement(s) en cours.\n\n"
                "Ils seront mis en pause : les fichiers partiels sont conservés et "
                "pourront être repris à la prochaine ouverture. Quitter ?",
            )
            if answer != QMessageBox.StandardButton.Yes:
                event.ignore()
                return
        self._timer.stop()
        self._manager.shutdown()
        self.settings.last_section = SECTIONS[self.stack.currentIndex()]
        try:
            save_settings(self._settings_path, self.settings)
        except OSError as exc:
            log.error("Réglages non enregistrés à la fermeture : %s", exc)
        event.accept()
