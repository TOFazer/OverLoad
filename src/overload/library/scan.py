"""Analyse d'un dossier local pour la page « Bibliothèque ».

Ce module ne fait que LIRE le système de fichiers : il ne déplace, ne renomme
ni ne supprime jamais rien. Les fichiers partiels d'OverLoad (`.part`) et les
fragments temporaires de téléchargement sont ignorés, afin que la bibliothèque
ne montre que des fichiers réellement utilisables.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from overload.core.errors import OverloadError

VIDEO_EXT = {"mp4", "mkv", "mov", "webm", "avi", "m4v", "wmv", "flv", "mpg", "mpeg", "ts"}
IMAGE_EXT = {"jpg", "jpeg", "png", "webp", "gif", "bmp", "avif", "heic", "tif", "tiff"}
AUDIO_EXT = {"mp3", "wav", "flac", "aac", "ogg", "oga", "m4a", "opus", "wma", "aiff"}
SUBTITLE_EXT = {"srt", "vtt", "ass", "ssa", "sub"}
ARCHIVE_EXT = {"zip", "rar", "7z", "tar", "gz", "bz2", "xz", "iso"}

KIND_LABELS: dict[str, str] = {
    "video": "Vidéo",
    "audio": "Audio",
    "image": "Image",
    "subtitle": "Sous-titres",
    "archive": "Archive",
    "file": "Fichier",
}

# Filtres proposés dans l'interface, dans l'ordre d'affichage.
KIND_FILTERS: list[tuple[str, str]] = [
    ("all", "Tous"),
    ("video", "Vidéos"),
    ("audio", "Audio"),
    ("image", "Images"),
    ("subtitle", "Sous-titres"),
    ("archive", "Archives"),
    ("file", "Autres"),
]

# Fichiers de travail des téléchargements : jamais présentés comme des médias.
_IGNORED_SUFFIXES = (".part", ".ytdl", ".tmp", ".download", ".crdownload")

SORTS: list[tuple[str, str]] = [
    ("recent", "Plus récents d'abord"),
    ("name", "Nom (A → Z)"),
    ("size", "Taille (plus lourds d'abord)"),
    ("kind", "Type, puis nom"),
]


def classify(filename: str) -> str:
    """Retourne le type logique d'un fichier à partir de son extension."""
    ext = Path(filename).suffix.lstrip(".").lower()
    if ext in VIDEO_EXT:
        return "video"
    if ext in AUDIO_EXT:
        return "audio"
    if ext in IMAGE_EXT:
        return "image"
    if ext in SUBTITLE_EXT:
        return "subtitle"
    if ext in ARCHIVE_EXT:
        return "archive"
    return "file"


@dataclass(frozen=True)
class LibraryFile:
    """Un fichier local indexé par la bibliothèque."""

    path: Path
    kind: str
    size_bytes: int
    modified_at: float

    @property
    def name(self) -> str:
        return self.path.name

    @property
    def extension(self) -> str:
        return self.path.suffix.lstrip(".").lower()

    @property
    def kind_label(self) -> str:
        return KIND_LABELS.get(self.kind, "Fichier")

    @property
    def folder_name(self) -> str:
        return self.path.parent.name or str(self.path.parent)


@dataclass(frozen=True)
class LibraryScan:
    """Résultat d'une analyse de dossier."""

    root: Path
    files: tuple[LibraryFile, ...]
    truncated: bool = False
    unreadable: int = 0

    @property
    def total_size(self) -> int:
        return sum(item.size_bytes for item in self.files)

    def counts(self) -> dict[str, int]:
        result: dict[str, int] = {}
        for item in self.files:
            result[item.kind] = result.get(item.kind, 0) + 1
        return result


def scan_library(
    root: Path | str,
    *,
    recursive: bool = True,
    limit: int = 4000,
    include_hidden: bool = False,
) -> LibraryScan:
    """Indexe les fichiers utilisables d'un dossier (lecture seule).

    - `limit` borne le nombre de fichiers indexés ; `truncated` signale alors
      que le dossier contient davantage de fichiers que ceux affichés.
    - Les dossiers et fichiers cachés (nom commençant par `.`) sont ignorés
      sauf si `include_hidden` vaut vrai.
    - Les erreurs de lecture (permissions, fichier disparu pendant l'analyse)
      sont comptées dans `unreadable` au lieu d'interrompre l'analyse.
    """
    folder = Path(root).expanduser()
    if not folder.is_dir():
        raise OverloadError(
            "Dossier de bibliothèque introuvable.",
            f"le chemin « {folder} » n'existe pas ou n'est pas un dossier.",
            "Choisissez un autre dossier, ou vérifiez qu'il n'a pas été "
            "déplacé ou renommé.",
        )

    found: list[LibraryFile] = []
    truncated = False
    unreadable = 0

    def consider(path: Path) -> bool:
        """Ajoute un fichier s'il est utilisable ; retourne False si limite atteinte."""
        nonlocal truncated, unreadable
        name = path.name
        if not include_hidden and name.startswith("."):
            return True
        if name.lower().endswith(_IGNORED_SUFFIXES):
            return True
        if len(found) >= limit:
            truncated = True
            return False
        try:
            stat = path.stat()
        except OSError:
            unreadable += 1
            return True
        found.append(
            LibraryFile(
                path=path,
                kind=classify(name),
                size_bytes=stat.st_size,
                modified_at=stat.st_mtime,
            )
        )
        return True

    if recursive:
        stop = False
        for dirpath, dirnames, filenames in os.walk(folder, followlinks=False):
            if not include_hidden:
                dirnames[:] = [d for d in dirnames if not d.startswith(".")]
            for filename in filenames:
                if not consider(Path(dirpath) / filename):
                    stop = True
                    break
            if stop:
                break
    else:
        try:
            entries = sorted(folder.iterdir(), key=lambda p: p.name.casefold())
        except OSError as exc:
            raise OverloadError(
                "Impossible de lire le dossier de bibliothèque.",
                str(exc),
                "Vérifiez les permissions du dossier, puis réessayez.",
            ) from exc
        for entry in entries:
            if entry.is_file() and not consider(entry):
                break

    found.sort(key=lambda item: item.modified_at, reverse=True)
    return LibraryScan(
        root=folder,
        files=tuple(found),
        truncated=truncated,
        unreadable=unreadable,
    )


def filter_files(
    files: tuple[LibraryFile, ...] | list[LibraryFile],
    *,
    kind: str = "all",
    query: str = "",
    sort: str = "recent",
) -> list[LibraryFile]:
    """Filtre par type et recherche textuelle, puis trie le résultat."""
    needle = query.strip().casefold()
    selected = [
        item
        for item in files
        if (kind == "all" or item.kind == kind)
        and (not needle or needle in item.name.casefold() or needle in str(item.path).casefold())
    ]
    if sort == "name":
        selected.sort(key=lambda item: item.name.casefold())
    elif sort == "size":
        selected.sort(key=lambda item: item.size_bytes, reverse=True)
    elif sort == "kind":
        order = {key: index for index, (key, _label) in enumerate(KIND_FILTERS)}
        selected.sort(key=lambda item: (order.get(item.kind, 99), item.name.casefold()))
    else:  # "recent"
        selected.sort(key=lambda item: item.modified_at, reverse=True)
    return selected
