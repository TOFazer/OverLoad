"""Point d'entrée de l'application.

- `OverLoad.exe` (fenêtre sans console) lance l'interface.
- `OverLoad.exe --self-test` vérifie que l'application démarre et que ses modules
  sont bien embarqués, puis quitte avec un code 0 (succès) ou 1 (échec).
  Utilisé par la CI Windows après la compilation.
"""

from __future__ import annotations

import logging
import sys
import traceback

from overload.core.logging_setup import setup_logging
from overload.core.paths import data_dir, logs_dir, settings_file
from overload.core.settings import load_settings

log = logging.getLogger("overload")


def _excepthook(exc_type, exc, tb) -> None:  # noqa: ANN001
    """Erreur non prévue : journalisée, présentée simplement à l'utilisateur."""
    log.critical("Erreur non prévue", exc_info=(exc_type, exc, tb))
    try:
        from PySide6.QtWidgets import QApplication, QMessageBox

        if QApplication.instance() is not None:
            QMessageBox.critical(
                None,
                "OverLoad",
                "Une erreur inattendue s'est produite.\n\n"
                f"Le détail technique a été enregistré dans : {logs_dir() / 'overload.log'}\n"
                "Relancez OverLoad. Si le problème revient, joignez ce journal "
                "à votre signalement.",
            )
            return
    except Exception:  # pragma: no cover - dernier recours
        pass
    sys.__stderr__.write("".join(traceback.format_exception(exc_type, exc, tb)))


def self_test() -> int:
    """Crée la fenêtre sans l'afficher : vérifie que l'application est complète."""
    manager = None
    try:
        from PySide6.QtWidgets import QApplication

        from overload.app.main_window import MainWindow
        from overload.downloads.manager import DownloadManager

        app = QApplication.instance() or QApplication(sys.argv[:1])
        settings = load_settings(settings_file())
        manager = DownloadManager(max_workers=1)
        window = MainWindow(settings, settings_file(), manager)
        stack_count = window.stack.count()
        nav_count = window.nav.count()
        ok = stack_count == 4 and nav_count == 4
        log.info("Auto-test : stack=%d, navigation=%d", stack_count, nav_count)
        app.processEvents()
        window.close()
        log.info("Auto-test : %s", "OK" if ok else "ÉCHEC")
        return 0 if ok else 1
    except Exception:
        # En mode fenêtre sans console, conserver l'erreur dans le journal plutôt
        # que d'afficher une boîte modale qui bloquerait l'auto-test de la CI.
        log.exception("Auto-test de démarrage échoué")
        return 1
    finally:
        if manager is not None:
            manager.shutdown()


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    setup_logging(logs_dir())
    log.info("Démarrage d'OverLoad (données : %s)", data_dir())
    sys.excepthook = _excepthook

    if "--self-test" in args:
        return self_test()

    from PySide6.QtWidgets import QApplication

    from overload.app.main_window import MainWindow
    from overload.app.theme import apply_theme
    from overload.downloads.manager import DownloadManager

    app = QApplication.instance() or QApplication(sys.argv[:1])
    app.setApplicationName("OverLoad")
    app.setOrganizationName("TOFazer")

    path = settings_file()
    settings = load_settings(path)
    apply_theme(app, settings.theme)
    manager = DownloadManager(max_workers=settings.max_parallel)
    window = MainWindow(settings, path, manager)
    window.show()
    return app.exec()
