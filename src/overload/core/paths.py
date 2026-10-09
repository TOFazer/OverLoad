"""Emplacements des fichiers de l'application.

- Mode installé ou par défaut : %LOCALAPPDATA%\\OverLoad (jamais à côté de l'exécutable).
- Mode portable : si un dossier « OverLoad-data » existe à côté de OverLoad.exe,
  les données y sont stockées (l'utilisateur choisit ce mode en créant ce dossier).
- Variable OVERLOAD_DATA_DIR : prioritaire, utilisée par les tests et l'auto-test.

Les fichiers temporaires ne sont jamais mélangés aux fichiers personnels : les
téléchargements vont dans le dossier choisi par l'utilisateur, les réglages et
journaux dans le dossier de données.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

APP_NAME = "OverLoad"
PORTABLE_DIR_NAME = "OverLoad-data"


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def app_root() -> Path:
    """Dossier de l'exécutable (mode figé) ou racine du dépôt (développement)."""
    if is_frozen():
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[3]


def resource_path(*parts: str) -> Path:
    """Chemin d'une ressource embarquée (dossier assets)."""
    if is_frozen() and hasattr(sys, "_MEIPASS"):
        base = Path(sys._MEIPASS)  # type: ignore[attr-defined]
    else:
        base = app_root()
    return base.joinpath("assets", *parts)


def data_dir() -> Path:
    override = os.environ.get("OVERLOAD_DATA_DIR")
    if override:
        path = Path(override)
    elif (app_root() / PORTABLE_DIR_NAME).is_dir():
        path = app_root() / PORTABLE_DIR_NAME
    else:
        local = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
        path = Path(local) / APP_NAME
    path.mkdir(parents=True, exist_ok=True)
    return path


def logs_dir() -> Path:
    path = data_dir() / "logs"
    path.mkdir(parents=True, exist_ok=True)
    return path


def settings_file() -> Path:
    return data_dir() / "settings.json"


def default_download_dir() -> Path:
    return Path.home() / "Downloads" / APP_NAME
