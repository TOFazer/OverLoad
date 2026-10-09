"""Interface de téléchargement : le moteur reste indépendant de Qt."""

from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import QSettings, Qt, QTimer, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from overload.__main__ import data_directory
from overload.core.errors import OverloadError
from overload.downloads.queue import DownloadQueue, Task
from overload.downloads.state import TaskState

_LABELS = {
    TaskState.QUEUED: "En attente", TaskState.RUNNING: "Téléchargement",
    TaskState.PAUSED: "En pause", TaskState.FINALIZING: "Finalisation",
    TaskState.COMPLETED: "Terminé", TaskState.FAILED: "Échec",
    TaskState.CANCELLED: "Annulé",
}


def _size(value: int) -> str:
    return f"{value / 1024**2:.1f} Mo"


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("OverLoad — Téléchargements directs")
        self.resize(960, 560)
        self.queue = DownloadQueue(data_directory() / "downloads.json")
        self.settings = QSettings("OverLoad", "OverLoad-Dev")
        root = QWidget()
        layout = QVBoxLayout(root)
        layout.addWidget(QLabel(
            "Adresse directe HTTP(S) d’un fichier (pas de page vidéo ni de DRM)"
        ))
        self.url = QLineEdit()
        self.url.setPlaceholderText("https://exemple.org/fichier.mp4")
        self.url.returnPressed.connect(self.add_download)
        layout.addWidget(self.url)
        folder_row = QHBoxLayout()
        self.folder = QLineEdit(str(
            self.settings.value("download_folder", Path.home() / "Downloads")
        ))
        folder_row.addWidget(QLabel("Dossier :"))
        folder_row.addWidget(self.folder)
        browse = QPushButton("Parcourir…")
        browse.clicked.connect(self.browse)
        folder_row.addWidget(browse)
        layout.addLayout(folder_row)
        add_button = QPushButton("Ajouter à la file")
        add_button.clicked.connect(self.add_download)
        layout.addWidget(add_button)
        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["Fichier", "État", "Progression", "Détail"])
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setColumnWidth(0, 260)
        self.table.setColumnWidth(1, 125)
        self.table.setColumnWidth(2, 195)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        layout.addWidget(self.table)
        buttons = QHBoxLayout()
        for label, handler in (
            ("Pause", self.pause), ("Reprendre / Réessayer", self.resume),
            ("Annuler", self.cancel), ("Ouvrir le dossier", self.open_folder),
        ):
            button = QPushButton(label)
            button.clicked.connect(handler)
            buttons.addWidget(button)
        layout.addLayout(buttons)
        layout.addWidget(QLabel(
            "Limite : 2 téléchargements simultanés · 10 Gio par fichier · "
            "les fichiers incomplets restent en .part"
        ))
        self.setCentralWidget(root)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.refresh)
        self.timer.start(300)
        self.refresh()

    def browse(self) -> None:
        folder = QFileDialog.getExistingDirectory(
            self, "Dossier de téléchargement", self.folder.text()
        )
        if folder:
            self.folder.setText(folder)

    def add_download(self) -> None:
        try:
            self.queue.add(self.url.text(), Path(self.folder.text()))
            self.settings.setValue("download_folder", self.folder.text())
            self.url.clear()
            self.refresh()
        except (OverloadError, OSError) as exc:
            QMessageBox.warning(self, "Téléchargement impossible", str(exc))

    def selected(self) -> Task | None:
        row = self.table.currentRow()
        if row < 0:
            return None
        item = self.table.item(row, 0)
        task_id = item.data(Qt.ItemDataRole.UserRole) if item else None
        return next((task for task in self.queue.snapshot() if task.id == task_id), None)

    def _act(self, method: str) -> None:
        task = self.selected()
        if task is None:
            return
        try:
            getattr(self.queue, method)(task.id)
            self.refresh()
        except OverloadError as exc:
            QMessageBox.warning(self, "Opération impossible", str(exc))

    def pause(self) -> None:
        self._act("pause")

    def resume(self) -> None:
        self._act("resume")

    def cancel(self) -> None:
        self._act("cancel")

    def open_folder(self) -> None:
        task = self.selected()
        if task is not None:
            folder = Path(task.target).parent
            if folder.exists():
                QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder)))

    def refresh(self) -> None:
        tasks = self.queue.snapshot()
        selected = self.selected().id if self.table.currentRow() >= 0 and self.selected() else None
        self.table.setRowCount(len(tasks))
        for row, task in enumerate(tasks):
            amount = _size(task.received)
            if task.total:
                amount += f" / {_size(task.total)} ({task.received / task.total:.0%})"
            items = [Path(task.target).name, _LABELS[task.state], amount, task.error]
            for col, value in enumerate(items):
                cell = QTableWidgetItem(value)
                if col == 0:
                    cell.setData(Qt.ItemDataRole.UserRole, task.id)
                self.table.setItem(row, col, cell)
            if task.id == selected:
                self.table.selectRow(row)

    def closeEvent(self, event) -> None:  # noqa: ANN001, N802
        self.timer.stop()
        self.queue.close()  # pause les tâches actives et attend la fin de la lecture en cours
        event.accept()


def launch() -> int:
    app = QApplication(sys.argv)
    try:
        window = MainWindow()
    except OverloadError as exc:
        QMessageBox.critical(None, "OverLoad — état illisible", str(exc))
        return 1
    window.show()
    return app.exec()
