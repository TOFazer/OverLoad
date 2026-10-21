"""Primitives de fichiers partagées par l'espace Créateurs.

Noms sûrs sous Windows, chemins uniques sans écrasement, classification des
médias par extension et parcours de dossiers sans fichiers temporaires.
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator
from pathlib import Path

from overload.creators.models import (
    AUDIO_EXTENSIONS,
    IMAGE_EXTENSIONS,
    SUBTITLE_EXTENSIONS,
    VIDEO_EXTENSIONS,
    MediaKind,
)

MAX_NAME_LENGTH = 80
_FORBIDDEN_CHARS = '<>:"/\\|?*'
TEMPORARY_SUFFIXES = {".part", ".tmp", ".crdownload"}


def sanitize_name(name: str, *, max_length: int = MAX_NAME_LENGTH) -> str:
    """Rend un nom utilisable comme nom de dossier/fichier sous Windows.

    Supprime les caractères interdits, les caractères de contrôle, les points et
    espaces finaux, et borne la longueur. Retourne « Sans titre » si vide.
    """
    cleaned = "".join(ch if ch not in _FORBIDDEN_CHARS else " " for ch in name)
    cleaned = "".join(ch if ch.isprintable() else " " for ch in cleaned)
    cleaned = " ".join(cleaned.split())
    cleaned = cleaned.strip(" .")
    if len(cleaned) > max_length:
        cleaned = cleaned[:max_length].strip(" .")
    return cleaned or "Sans titre"


def unique_path(target: Path) -> Path:
    """Retourne un chemin disponible : « nom (2).ext », « nom (3).ext »… jamais un écrasement."""
    if not target.exists():
        return target
    return unique_path_among(target, set())


def unique_path_among(target: Path, claimed: set[Path]) -> Path:
    """Comme `unique_path` mais en évitant aussi les destinations déjà planifiées."""
    if target not in claimed and not target.exists():
        return target
    stem, suffix, parent = target.stem, target.suffix, target.parent
    counter = 2
    while True:
        candidate = parent / f"{stem} ({counter}){suffix}"
        if candidate not in claimed and not candidate.exists():
            return candidate
        counter += 1


def classify_file(path: Path | str) -> MediaKind:
    """Détermine la catégorie d'un fichier à partir de son extension."""
    suffix = Path(path).suffix.lower()
    if suffix in VIDEO_EXTENSIONS:
        return MediaKind.VIDEO
    if suffix in AUDIO_EXTENSIONS:
        return MediaKind.AUDIO
    if suffix in IMAGE_EXTENSIONS:
        return MediaKind.IMAGE
    if suffix in SUBTITLE_EXTENSIONS:
        return MediaKind.SUBTITLE
    return MediaKind.OTHER


def iter_media_files(folder: Path | str, *, recursive: bool = True) -> Iterator[Path]:
    """Itère les fichiers d'un dossier en ignorant les dossiers cachés et temporaires."""
    root = Path(folder)
    if not root.is_dir():
        return
    iterator = root.rglob("*") if recursive else root.glob("*")
    for candidate in iterator:
        try:
            if not candidate.is_file():
                continue
            relative = candidate.relative_to(root)
        except (OSError, ValueError):
            continue
        if any(part.startswith(".") or part.startswith("~$") for part in relative.parts):
            continue
        if candidate.suffix.lower() in TEMPORARY_SUFFIXES:
            continue
        yield candidate


def expand_sources(sources: Iterable[Path | str], *, recursive: bool = True) -> list[Path]:
    """Résout une sélection mixte (fichiers et/ou dossiers) en liste de fichiers.

    Les doublons (chemins identiques) sont éliminés en conservant l'ordre de saisie.
    """
    seen: set[Path] = set()
    files: list[Path] = []
    for raw in sources:
        candidate = Path(str(raw)).expanduser()
        try:
            resolved = candidate.resolve()
        except OSError:
            resolved = candidate.absolute()
        if not resolved.exists():
            continue
        if resolved.is_dir():
            for media in iter_media_files(resolved, recursive=recursive):
                key = media.resolve() if media.exists() else media
                if key not in seen:
                    seen.add(key)
                    files.append(media)
        elif resolved.is_file() and resolved not in seen:
            seen.add(resolved)
            files.append(resolved)
    return files
