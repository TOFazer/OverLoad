"""Application de bureau native OverLoad (PySide6 / QtWidgets).

Aucune logique réseau ou métier ne réside ici : l'interface pilote uniquement
`DownloadManager`, `DownloadHistoryStore` et `SettingsStore`. La mise en page
complète vit dans `overload.ui.window`, importée paresseusement afin que le mode
Web reste utilisable lorsque PySide6 n'est pas installé.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import TYPE_CHECKING

from overload import __version__
from overload.core.paths import default_data_dir, default_downloads_dir
from overload.downloads.duplicates import DuplicatePolicy
from overload.downloads.manager import DownloadManager
from overload.history.store import DownloadHistoryStore
from overload.settings.store import SettingsStore

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
    """Icône vectorielle d'OverLoad (éclair crème sur dégradé mousse → sapin)."""
    from overload.ui.window import build_app_icon

    return build_app_icon()


def create_main_window(
    manager: DownloadManager,
    history: DownloadHistoryStore,
    settings_store: SettingsStore,
    *,
    data_dir: Path | None = None,
) -> QMainWindow:
    """Construit la fenêtre principale moderne d'OverLoad."""
    from overload.ui.window import OverloadWindow

    return OverloadWindow(
        manager,
        history,
        settings_store,
        data_dir=data_dir,
    )


def launch_desktop_app(
    *,
    destination_dir: Path | None = None,
    data_dir: Path | None = None,
    self_test: bool = False,
) -> int:
    """Démarre l'application native OverLoad (point d'entrée de `OverLoad.exe`)."""
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
    app.setApplicationVersion(__version__)
    app.setOrganizationName("TOFazer")
    app.setWindowIcon(create_app_icon())

    window = create_main_window(manager, history, settings_store, data_dir=base_data)
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


__all__: list[str] = [
    "create_app_icon",
    "create_main_window",
    "is_pyside6_available",
    "launch_desktop_app",
]
