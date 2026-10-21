"""Point d'entrée de l'application (app.py)."""

from __future__ import annotations

import sys


def main() -> int:
    try:
        from PySide6.QtWidgets import QApplication
    except ImportError:
        print("OverLoad : PySide6 n'est pas installé.", file=sys.stderr)
        print("Installez-le avec : pip install PySide6", file=sys.stderr)
        print("Ou lancez les tests de la bibliothèque : pytest -q", file=sys.stderr)
        return 1

    from overload.settings.store import SettingsStore
    from overload.ui.main_window import MainWindow
    from overload.ui.styles import apply_theme

    app = QApplication(sys.argv)
    app.setApplicationName("OverLoad")
    app.setOrganizationName("OverLoad")

    # Thème
    settings = SettingsStore()
    theme = settings.get("theme", "system")
    apply_theme(app, theme)

    w = MainWindow()
    w.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
