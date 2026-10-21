"""Chemins de données OverLoad (séparés par canal).

Windows :
  stable : %APPDATA%\\OverLoad
  beta   : %APPDATA%\\OverLoad-Beta
  dev    : %APPDATA%\\OverLoad-Dev
Portable : dossier OverLoad-data à côté de l'exe
Linux/macOS (dev local) : ~/.config/overload ou dossier courant.
"""
"""Gestion des dossiers d'application (mode installé, portable .exe ou dev) et Explorateur."""

from __future__ import annotations

import os
import sys
from pathlib import Path


def app_data_dir(channel: str = "stable") -> Path:
    """Retourne le dossier de données selon la plateforme et le canal."""
    # Vérifie le mode portable : OverLoad-data à côté de l'exécutable/script
    exe_dir = Path(sys.executable).parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parents[3]
    portable = exe_dir / "OverLoad-data"
    if portable.exists() or os.environ.get("OVERLOAD_PORTABLE"):
        base = portable
        if channel != "stable":
            base = base.parent / f"OverLoad-data-{channel.capitalize()}"
        base.mkdir(parents=True, exist_ok=True)
        return base

    if os.name == "nt":
        base = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
        names = {"stable": "OverLoad", "beta": "OverLoad-Beta", "dev": "OverLoad-Dev"}
        p = base / names.get(channel, "OverLoad")
        p.mkdir(parents=True, exist_ok=True)
        return p

    # Linux/macOS dev
    xdg = os.environ.get("XDG_CONFIG_HOME", str(Path.home() / ".config"))
    p = Path(xdg) / ("overload" if channel == "stable" else f"overload-{channel}")
    p.mkdir(parents=True, exist_ok=True)
    return p


def library_db_path(channel: str = "stable") -> Path:
    return app_data_dir(channel) / "library.db"


def thumbnail_dir(channel: str = "stable") -> Path:
    p = app_data_dir(channel) / "thumbnails"
    p.mkdir(parents=True, exist_ok=True)
    return p


def settings_path(channel: str = "stable") -> Path:
    return app_data_dir(channel) / "settings.json"


def logs_dir(channel: str = "stable") -> Path:
    p = app_data_dir(channel) / "logs"
    p.mkdir(parents=True, exist_ok=True)
    return p
import subprocess
import sys
from pathlib import Path

from overload.core.errors import OverloadError


def application_dir() -> Path:
    """Retourne le dossier contenant `OverLoad.exe` en mode compilé, ou la racine du projet."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[3]


def default_data_dir() -> Path:
    """Retourne le dossier de données d'OverLoad, en le créant si besoin.

    En mode compilé (`OverLoad.exe`), si un dossier `OverLoad-data` existe à côté de
    l'exécutable, OverLoad fonctionne automatiquement en mode portable isolé.
    """
    override = os.environ.get("OVERLOAD_DATA_DIR")
    if override:
        base = Path(override).expanduser()
    elif getattr(sys, "frozen", False) and (application_dir() / "OverLoad-data").is_dir():
        base = application_dir() / "OverLoad-data"
    elif sys.platform == "win32":
        appdata = os.environ.get("APPDATA")
        base = (Path(appdata) if appdata else Path.home() / "AppData" / "Roaming") / "OverLoad"
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support" / "OverLoad"
    else:
        xdg = os.environ.get("XDG_DATA_HOME")
        base = (Path(xdg) if xdg else Path.home() / ".local" / "share") / "OverLoad"
    base.mkdir(parents=True, exist_ok=True)
    return base


def default_downloads_dir() -> Path:
    """Retourne le dossier de téléchargements par défaut, en le créant si besoin."""
    override = os.environ.get("OVERLOAD_DOWNLOADS_DIR")
    if override:
        folder = Path(override).expanduser()
    elif getattr(sys, "frozen", False) and (application_dir() / "OverLoad-data").is_dir():
        folder = application_dir() / "OverLoad-data" / "Downloads"
    else:
        candidates = [Path.home() / "Downloads", Path.home() / "Téléchargements"]
        existing = next((p for p in candidates if p.is_dir()), None)
        folder = (existing or candidates[0]) / "OverLoad"
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def open_folder(path: Path | str, *, opener=None) -> Path:  # noqa: ANN001
    """Ouvre un dossier (ou sélectionne un fichier dans son dossier parent).

    - Si `path` pointe vers un fichier existant, le révèle dans l'Explorateur
      Windows (`explorer /select,...`) ou Finder macOS (`open -R`), ou ouvre son
      dossier parent sous Linux.
    - Si `path` pointe vers un fichier disparu mais dont le dossier parent existe
      encore, ouvre ce dossier parent afin que l'utilisateur puisse vérifier son contenu.
    - Lève `OverloadError` si ni le fichier ni le dossier parent n'existent.
    """
    target = Path(path).expanduser()
    select_file = False

    if target.is_file():
        folder = target.parent.resolve()
        resolved_target = target.resolve()
        select_file = True
    elif target.is_dir():
        folder = target.resolve()
        resolved_target = folder
    elif target.parent.is_dir():
        folder = target.parent.resolve()
        resolved_target = folder
    else:
        raise OverloadError(
            "Impossible d'ouvrir le dossier de destination.",
            f"le chemin « {target} » est introuvable.",
            "Vérifiez que le dossier n'a pas été déplacé, renommé ou supprimé.",
        )

    if opener is not None:
        opener(resolved_target, select_file=select_file)
        return folder

    try:
        if sys.platform == "win32":
            if select_file:
                subprocess.Popen(["explorer.exe", f"/select,{resolved_target}"])
            else:
                os.startfile(str(folder))  # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            cmd = ["open", "-R", str(resolved_target)] if select_file else ["open", str(folder)]
            subprocess.Popen(cmd)
        else:
            subprocess.Popen(
                ["xdg-open", str(folder)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
    except OSError as exc:
        raise OverloadError(
            "Impossible d'ouvrir l'Explorateur de fichiers.",
            str(exc),
            f"Vous pouvez ouvrir manuellement le dossier : {folder}",
        ) from exc

    return folder
