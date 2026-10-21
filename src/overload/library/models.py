"""Modèles de la bibliothèque multimédia.

Chaque fichier téléchargé devient une entrée indexée : nom, type, taille,
dates, durée éventuelle, empreinte (hash) pour les doublons et vignette.
"""

from __future__ import annotations

import mimetypes
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from pathlib import Path


class MediaType(StrEnum):
    VIDEO = "video"
    AUDIO = "audio"
    IMAGE = "image"
    OTHER = "other"


# Extensions les plus courantes — la liste est extensible sans migration DB.
VIDEO_EXTS = frozenset(
    {
        ".mp4",
        ".mkv",
        ".avi",
        ".mov",
        ".wmv",
        ".flv",
        ".webm",
        ".m4v",
        ".mpg",
        ".mpeg",
        ".3gp",
        ".ts",
        ".mts",
        ".m2ts",
        ".mxf",
    }
)
AUDIO_EXTS = frozenset(
    {
        ".mp3",
        ".flac",
        ".wav",
        ".aac",
        ".ogg",
        ".wma",
        ".m4a",
        ".opus",
        ".aiff",
        ".alac",
        ".mka",
        ".mp2",
    }
)
IMAGE_EXTS = frozenset(
    {
        ".jpg",
        ".jpeg",
        ".png",
        ".gif",
        ".bmp",
        ".webp",
        ".tiff",
        ".tif",
        ".heic",
        ".heif",
        ".svg",
        ".avif",
        ".ico",
        ".psd",
    }
)

# Pour un affichage humain.
MEDIA_TYPE_LABELS = {
    MediaType.VIDEO: "Vidéos",
    MediaType.AUDIO: "Musiques",
    MediaType.IMAGE: "Images",
    MediaType.OTHER: "Autres",
}

# Icônes emoji de secours (si les icônes Qt ne chargent pas).
MEDIA_TYPE_ICONS = {
    MediaType.VIDEO: "🎬",
    MediaType.AUDIO: "🎵",
    MediaType.IMAGE: "🖼️",
    MediaType.OTHER: "📄",
}


def media_type_from_extension(ext: str) -> MediaType:
    """Déduit le type à partir de l'extension (avec point, insensible à la casse)."""
    ext = ext.lower()
    if ext in VIDEO_EXTS:
        return MediaType.VIDEO
    if ext in AUDIO_EXTS:
        return MediaType.AUDIO
    if ext in IMAGE_EXTS:
        return MediaType.IMAGE
    # Tentative via mimetypes pour les extensions moins courantes.
    mime, _ = mimetypes.guess_type(f"file{ext}")
    if mime:
        if mime.startswith("video/"):
            return MediaType.VIDEO
        if mime.startswith("audio/"):
            return MediaType.AUDIO
        if mime.startswith("image/"):
            return MediaType.IMAGE
    return MediaType.OTHER


def media_type_from_path(path: Path) -> MediaType:
    return media_type_from_extension(path.suffix)


@dataclass(slots=True)
class MediaEntry:
    """Une entrée de la bibliothèque."""

    path: Path
    filename: str
    media_type: MediaType
    extension: str
    size: int
    mtime: float  # timestamp (date de modification fichier)
    # Champs optionnels — renseignés quand disponibles.
    ctime: float | None = None
    duration: float | None = None  # secondes
    width: int | None = None
    height: int | None = None
    hash: str | None = None  # SHA-256 ou BLAKE2b complet
    hash_partial: str | None = None  # hash des premiers 1 Mio (rapide)
    thumbnail_path: Path | None = None
    source_url: str | None = None
    created_at: float | None = None  # quand indexé
    # Base
    id: int | None = None

    @property
    def mtime_dt(self) -> datetime:
        return datetime.fromtimestamp(self.mtime)

    @property
    def size_human(self) -> str:
        return human_size(self.size)

    @property
    def duration_human(self) -> str | None:
        if self.duration is None:
            return None
        return human_duration(self.duration)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "path": str(self.path),
            "filename": self.filename,
            "media_type": self.media_type.value,
            "extension": self.extension,
            "size": self.size,
            "size_human": self.size_human,
            "mtime": self.mtime,
            "mtime_iso": datetime.fromtimestamp(self.mtime).isoformat(),
            "ctime": self.ctime,
            "duration": self.duration,
            "duration_human": self.duration_human,
            "width": self.width,
            "height": self.height,
            "hash": self.hash,
            "thumbnail_path": str(self.thumbnail_path) if self.thumbnail_path else None,
            "source_url": self.source_url,
        }


def human_size(size: int) -> str:
    if size < 1024:
        return f"{size} o"
    if size < 1024 * 1024:
        return f"{size / 1024:.1f} Ko"
    if size < 1024 * 1024 * 1024:
        return f"{size / (1024 * 1024):.1f} Mo"
    return f"{size / (1024 * 1024 * 1024):.2f} Go"


def human_duration(seconds: float) -> str:
    if seconds < 0:
        seconds = 0
    m, s = divmod(int(seconds), 60)
    h, m = divmod(m, 60)
    if h:
        return f"{h:d}h {m:02d}m {s:02d}s"
    if m:
        return f"{m:d}m {s:02d}s"
    return f"{s:d}s"


@dataclass(slots=True)
class DuplicateGroup:
    """Groupe de fichiers identiques (même empreinte)."""

    hash: str
    entries: list[MediaEntry] = field(default_factory=list)

    @property
    def wasted_bytes(self) -> int:
        if len(self.entries) < 2:
            return 0
        # Tout sauf le premier est du gaspillage potentiel.
        return sum(e.size for e in self.entries[1:])

    @property
    def wasted_human(self) -> str:
        return human_size(self.wasted_bytes)
