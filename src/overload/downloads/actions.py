"""Actions sur les fichiers téléchargés.

Règle de sécurité : OverLoad n'exécute jamais un fichier téléchargé. Ouvrir un
exécutable, un script ou un installateur est refusé ; l'utilisateur peut alors
ouvrir le dossier ou révéler le fichier dans l'Explorateur.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from overload.core.errors import OverloadError
from overload.downloads.files import is_inside

DANGEROUS_EXTENSIONS = frozenset(
    {
        ".exe",
        ".com",
        ".scr",
        ".pif",
        ".bat",
        ".cmd",
        ".ps1",
        ".psm1",
        ".vbs",
        ".vbe",
        ".js",
        ".jse",
        ".wsf",
        ".wsh",
        ".hta",
        ".lnk",
        ".reg",
        ".msi",
        ".msp",
        ".msix",
        ".msixbundle",
        ".appx",
        ".appxbundle",
        ".cpl",
        ".jar",
        ".dll",
        ".sh",
        ".apk",
        ".gadget",
        ".url",
    }  # fmt: skip
)


def is_dangerous(path: Path) -> bool:
    return path.suffix.lower() in DANGEROUS_EXTENSIONS


def _check_inside(path: Path, base: Path) -> None:
    if not is_inside(base, path):
        raise OverloadError(
            "Chemin refusé.",
            "le fichier n'est pas dans le dossier de téléchargement.",
            "Ouvrez le fichier depuis la liste des téléchargements.",
        )


def _open_with_default_app(path: Path) -> None:
    if sys.platform == "win32":
        os.startfile(str(path))  # type: ignore[attr-defined]  # noqa: S606
    else:  # développement hors Windows
        subprocess.Popen(["xdg-open", str(path)])  # noqa: S603


def open_file(path: Path, base: Path) -> None:
    """Ouvre un fichier avec son application par défaut, sauf s'il est exécutable."""
    _check_inside(path, base)
    if not path.is_file():
        raise OverloadError(
            "Le fichier n'existe plus.",
            "il a été déplacé ou supprimé en dehors d'OverLoad.",
            "Relancez le téléchargement ou ouvrez le dossier pour vérifier.",
        )
    if is_dangerous(path):
        raise OverloadError(
            "OverLoad n'ouvre pas les fichiers exécutables ou les scripts.",
            f"le type « {path.suffix} » peut lancer du code.",
            "Utilisez « Ouvrir le dossier » ou « Révéler » pour le contrôler.",
        )
    _open_with_default_app(path)


def open_folder(folder: Path) -> None:
    if not folder.is_dir():
        raise OverloadError(
            "Le dossier est introuvable.",
            "il a été déplacé, renommé ou supprimé.",
            "Choisissez un autre dossier dans les paramètres.",
        )
    if sys.platform == "win32":
        os.startfile(str(folder))  # type: ignore[attr-defined]
    else:
        subprocess.Popen(["xdg-open", str(folder)])  # noqa: S603


def reveal_file(path: Path, base: Path) -> None:
    """Affiche le fichier sélectionné dans l'Explorateur Windows."""
    _check_inside(path, base)
    if not path.exists():
        raise OverloadError(
            "Le fichier n'existe plus.",
            "il a été déplacé ou supprimé en dehors d'OverLoad.",
            "Ouvrez le dossier pour vérifier.",
        )
    if sys.platform == "win32":
        subprocess.Popen(["explorer", f"/select,{path}"])  # noqa: S603
    else:
        open_folder(path.parent)
