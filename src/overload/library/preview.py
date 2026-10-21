"""Prévisualisation et ouverture de l'emplacement dans l'explorateur."""

from __future__ import annotations

import os
import platform
import subprocess
from pathlib import Path

from overload.core.errors import OverloadError


def open_media(path: Path) -> None:
    """Ouvre le fichier avec l'application par défaut (double-clic système)."""
    path = Path(path)
    if not path.exists():
        raise OverloadError(
            "Fichier introuvable.",
            f"« {path.name} » a été déplacé ou supprimé.",
            "Retirez-le de la bibliothèque ou restaurez-le depuis la corbeille.",
        )
    system = platform.system()
    try:
        if system == "Windows":
            os.startfile(str(path))  # type: ignore[attr-defined]
        elif system == "Darwin":
            subprocess.Popen(["open", str(path)])
        else:
            subprocess.Popen(["xdg-open", str(path)])
    except Exception as exc:
        raise OverloadError(
            "Impossible d'ouvrir ce fichier.",
            str(exc),
            "Vérifiez qu'une application est associée à ce type de fichier.",
        ) from exc


def reveal_in_explorer(path: Path) -> None:
    """Révèle le fichier dans l'explorateur de fichiers (sélectionné)."""
    path = Path(path)
    if not path.exists():
        raise OverloadError(
            "Fichier introuvable pour l'affichage dans le dossier.",
            f"« {path} » n'existe plus.",
        )
    system = platform.system()
    try:
        if system == "Windows":
            # explorer /select,"C:\chemin\fichier.mp4"
            subprocess.Popen(["explorer", f"/select,{str(path)}"])
        elif system == "Darwin":
            subprocess.Popen(["open", "-R", str(path)])
        else:
            # Linux : ouvrir le dossier parent
            subprocess.Popen(["xdg-open", str(path.parent)])
    except Exception as exc:
        raise OverloadError(
            "Impossible d'ouvrir le dossier.",
            str(exc),
        ) from exc


def preview_info(path: Path) -> dict:
    """Infos pour la prévisualisation rapide dans l'UI (sans ouvrir le fichier)."""
    from overload.library.scanner import scan_file

    entry = scan_file(Path(path), compute_hash=False)
    if entry is None:
        raise OverloadError("Aperçu impossible.", "format non pris en charge ou fichier temporaire.")
    return {
        "path": str(entry.path),
        "filename": entry.filename,
        "media_type": entry.media_type.value,
        "size": entry.size,
        "size_human": entry.size_human,
        "mtime": entry.mtime,
        "mtime_human": entry.mtime_dt.strftime("%d/%m/%Y %H:%M"),
        "duration": entry.duration,
        "duration_human": entry.duration_human,
        "width": entry.width,
        "height": entry.height,
        "can_preview": entry.media_type.value in ("image", "video", "audio"),
    }
