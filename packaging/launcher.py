"""Point d'entrée utilisé par PyInstaller (import absolu, sans dépendance au répertoire courant)."""

import sys

from overload.app.entry import main

if __name__ == "__main__":
    sys.exit(main())
