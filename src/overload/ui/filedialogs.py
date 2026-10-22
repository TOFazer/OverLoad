"""Sélecteurs de fichiers Qt avec un dossier de départ toujours prévisible.

Correctif du bug « le sélecteur m'ouvre n'importe où » : les appels directs à
`QFileDialog` avec un dossier initial vide (``""``) laissaient Qt/Windows
choisir le dossier de travail du processus ou un emplacement mémorisé au
hasard. Tous les boutons « Parcourir… » / « Choisir… » passent désormais par
ces fonctions, qui démarrent :

1. sur le chemin déjà affiché dans le champ associé (fichier → son dossier) ;
2. sinon sur le dernier dossier réellement choisi dans OverLoad ;
3. sinon sur le dossier de repli fourni (destination des téléchargements,
   dossier du projet…) ;
4. sinon dans `~/Downloads` (ou `~/Téléchargements`), puis le dossier
   personnel.

Le dernier dossier choisi est mémorisé pour la session : d'un sélecteur à
l'autre, l'utilisateur reste là où il était au lieu de repartir ailleurs.
"""

from __future__ import annotations

from pathlib import Path

from overload.core.paths import dialog_start_dir

_last_dir: Path | None = None


def reset_last_dir() -> None:
    """Oublie le dernier dossier choisi (utile aux tests)."""
    global _last_dir
    _last_dir = None


def _start_dir(preferred: str | Path | None, fallback: str | Path | None) -> str:
    start = dialog_start_dir(preferred, fallback=_last_dir or fallback)
    return str(start)


def _remember(chosen: str) -> None:
    global _last_dir
    if chosen:
        _last_dir = dialog_start_dir(chosen)


def choose_open_file(
    parent,  # noqa: ANN001 - QWidget parent
    title: str,
    *,
    preferred: str | Path | None = None,
    fallback: str | Path | None = None,
    name_filter: str = "Tous les fichiers (*.*)",
) -> str:
    """Demande un fichier à ouvrir ; retourne ``""`` si l'utilisateur annule."""
    from PySide6.QtWidgets import QFileDialog

    filename, _ = QFileDialog.getOpenFileName(
        parent, title, _start_dir(preferred, fallback), name_filter
    )
    _remember(filename)
    return filename


def choose_open_files(
    parent,  # noqa: ANN001 - QWidget parent
    title: str,
    *,
    preferred: str | Path | None = None,
    fallback: str | Path | None = None,
    name_filter: str = "Tous les fichiers (*.*)",
) -> list[str]:
    """Demande plusieurs fichiers à ouvrir ; liste vide si annulation."""
    from PySide6.QtWidgets import QFileDialog

    files, _ = QFileDialog.getOpenFileNames(
        parent, title, _start_dir(preferred, fallback), name_filter
    )
    if files:
        _remember(files[0])
    return list(files)


def choose_directory(
    parent,  # noqa: ANN001 - QWidget parent
    title: str,
    *,
    preferred: str | Path | None = None,
    fallback: str | Path | None = None,
) -> str:
    """Demande un dossier ; retourne ``""`` si l'utilisateur annule."""
    from PySide6.QtWidgets import QFileDialog

    folder = QFileDialog.getExistingDirectory(
        parent, title, _start_dir(preferred, fallback)
    )
    _remember(folder)
    return folder


def choose_save_file(
    parent,  # noqa: ANN001 - QWidget parent
    title: str,
    *,
    suggested: str | Path | None = None,
    fallback: str | Path | None = None,
    name_filter: str = "Tous les fichiers (*.*)",
) -> str:
    """Demande où enregistrer ; le nom suggéré (fichier inclus) est pré-rempli."""
    from PySide6.QtWidgets import QFileDialog

    start = ""
    if suggested is not None and str(suggested).strip():
        suggested_path = Path(str(suggested).strip()).expanduser()
        # On passe le chemin complet : Qt pré-remplit le nom du fichier et
        # ouvre son dossier parent (jamais un emplacement aléatoire).
        start = str(suggested_path)
        if not suggested_path.parent.is_dir():
            start = _start_dir(suggested_path.parent, fallback)
    else:
        start = _start_dir(None, fallback)
    filename, _ = QFileDialog.getSaveFileName(parent, title, start, name_filter)
    _remember(filename)
    return filename
