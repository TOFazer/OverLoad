"""Chemins de données OverLoad (séparés par canal).

Windows :
  stable : %APPDATA%\\OverLoad
  beta   : %APPDATA%\\OverLoad-Beta
  dev    : %APPDATA%\\OverLoad-Dev
Portable : dossier OverLoad-data à côté de l'exe
Linux/macOS (dev local) : ~/.config/overload ou dossier courant.
"""

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
