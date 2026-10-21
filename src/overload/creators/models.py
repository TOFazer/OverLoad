"""Modèles de données de l'espace Créateurs (médias, profils, projets, pistes)."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any

VIDEO_EXTENSIONS = {
    ".mp4", ".m4v", ".mov", ".mkv", ".avi", ".webm", ".mxf", ".mpg", ".mpeg",
    ".m2ts", ".mts", ".ts", ".wmv", ".flv", ".f4v", ".3gp", ".3g2", ".ogv",
    ".dv", ".vob",
}

AUDIO_EXTENSIONS = {
    ".wav", ".bwf", ".mp3", ".aac", ".m4a", ".flac", ".ogg", ".oga", ".opus",
    ".aif", ".aiff", ".aifc", ".wma", ".ac3", ".eac3", ".caf", ".amr",
}

IMAGE_EXTENSIONS = {
    ".jpg", ".jpeg", ".jpe", ".png", ".gif", ".bmp", ".tif", ".tiff", ".webp",
    ".svg", ".heic", ".heif", ".avif", ".psd", ".ai", ".exr", ".dpx", ".tga",
    ".cr2", ".cr3", ".nef", ".arw", ".dng", ".jfif",
}

SUBTITLE_EXTENSIONS = {
    ".srt", ".ass", ".ssa", ".vtt", ".sub", ".sbv", ".ttml", ".dfxp",
}


class MediaKind(StrEnum):
    """Catégorie d'un fichier, déterminée par son extension."""

    VIDEO = "video"
    AUDIO = "audio"
    IMAGE = "image"
    SUBTITLE = "subtitle"
    OTHER = "other"

    @property
    def label(self) -> str:
        labels = {
            MediaKind.VIDEO: "Vidéo",
            MediaKind.AUDIO: "Audio",
            MediaKind.IMAGE: "Image",
            MediaKind.SUBTITLE: "Sous-titres",
            MediaKind.OTHER: "Autre",
        }
        return labels[self]

    @property
    def folder_token(self) -> str:
        """Valeur du jeton `{type}` des modèles de renommage."""
        tokens = {
            MediaKind.VIDEO: "Video",
            MediaKind.AUDIO: "Audio",
            MediaKind.IMAGE: "Image",
            MediaKind.SUBTITLE: "SousTitres",
            MediaKind.OTHER: "Autre",
        }
        return tokens[self]


@dataclass(frozen=True)
class EditingProfile:
    """Profil dédié à un logiciel de montage : arborescence et formats recommandés.

    Un profil décrit à la fois la structure de dossiers créée pour chaque projet
    vidéo et les formats (conteneurs, codecs) conseillés pour l'importation dans
    le logiciel de montage correspondant.
    """

    id: str
    name: str
    description: str = ""
    video_folder: str = "01_Videos"
    audio_folder: str = "02_Audio"
    image_folder: str = "03_Images"
    subtitle_folder: str = "04_Sous-titres"
    project_folder: str = "05_Projets"
    export_folder: str = "06_Exports"
    extra_folders: tuple[str, ...] = ()
    recommended_container: str = ""
    recommended_video: str = ""
    recommended_audio: str = ""
    notes: str = ""
    builtin: bool = False

    def folders(self) -> list[str]:
        """Liste ordonnée et sans doublon des dossiers du profil."""
        seen: list[str] = []
        for name in (
            self.video_folder,
            self.audio_folder,
            self.image_folder,
            self.subtitle_folder,
            self.project_folder,
            self.export_folder,
            *self.extra_folders,
        ):
            cleaned = name.strip()
            if cleaned and cleaned not in seen:
                seen.append(cleaned)
        return seen

    def folder_for(self, kind: MediaKind) -> str:
        """Dossier de destination des médias d'une catégorie donnée."""
        return {
            MediaKind.VIDEO: self.video_folder,
            MediaKind.AUDIO: self.audio_folder,
            MediaKind.IMAGE: self.image_folder,
            MediaKind.SUBTITLE: self.subtitle_folder,
            MediaKind.OTHER: self.export_folder,
        }[kind]

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "video_folder": self.video_folder,
            "audio_folder": self.audio_folder,
            "image_folder": self.image_folder,
            "subtitle_folder": self.subtitle_folder,
            "project_folder": self.project_folder,
            "export_folder": self.export_folder,
            "extra_folders": list(self.extra_folders),
            "recommended_container": self.recommended_container,
            "recommended_video": self.recommended_video,
            "recommended_audio": self.recommended_audio,
            "notes": self.notes,
            "builtin": self.builtin,
        }

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> EditingProfile:
        return cls(
            id=str(raw.get("id", "")),
            name=str(raw.get("name", "")),
            description=str(raw.get("description", "")),
            video_folder=str(raw.get("video_folder", "01_Videos")),
            audio_folder=str(raw.get("audio_folder", "02_Audio")),
            image_folder=str(raw.get("image_folder", "03_Images")),
            subtitle_folder=str(raw.get("subtitle_folder", "04_Sous-titres")),
            project_folder=str(raw.get("project_folder", "05_Projets")),
            export_folder=str(raw.get("export_folder", "06_Exports")),
            extra_folders=tuple(str(f) for f in raw.get("extra_folders", []) if str(f).strip()),
            recommended_container=str(raw.get("recommended_container", "")),
            recommended_video=str(raw.get("recommended_video", "")),
            recommended_audio=str(raw.get("recommended_audio", "")),
            notes=str(raw.get("notes", "")),
            builtin=bool(raw.get("builtin", False)),
        )


@dataclass(frozen=True)
class CreatorProject:
    """Projet vidéo enregistré dans l'espace Créateurs."""

    id: str
    name: str
    root_dir: str
    profile_id: str
    created_at: str
    last_opened_at: str = ""
    notes: str = ""

    @property
    def path(self) -> Path:
        return Path(self.root_dir)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "root_dir": self.root_dir,
            "profile_id": self.profile_id,
            "created_at": self.created_at,
            "last_opened_at": self.last_opened_at,
            "notes": self.notes,
        }

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> CreatorProject:
        return cls(
            id=str(raw.get("id", "")),
            name=str(raw.get("name", "")),
            root_dir=str(raw.get("root_dir", "")),
            profile_id=str(raw.get("profile_id", "")),
            created_at=str(raw.get("created_at", "")),
            last_opened_at=str(raw.get("last_opened_at", "")),
            notes=str(raw.get("notes", "")),
        )


@dataclass(frozen=True)
class TrackInfo:
    """Une piste (vidéo, audio ou sous-titres) d'un fichier média."""

    index: int
    kind: str
    kind_index: int
    codec: str
    codec_long: str
    language: str
    title: str
    is_default: bool
    is_forced: bool
    channels: int | None = None
    sample_rate: str = ""
    width: int | None = None
    height: int | None = None

    @property
    def kind_label(self) -> str:
        return {"video": "Vidéo", "audio": "Audio", "subtitle": "Sous-titres"}.get(
            self.kind, self.kind
        )

    def summary(self) -> str:
        """Ligne lisible en français décrivant la piste."""
        parts = [f"{self.kind_label} #{self.kind_index + 1} — {self.codec or 'codec inconnu'}"]
        if self.language:
            parts.append(f"langue {self.language}")
        if self.channels:
            parts.append(f"{self.channels} canal(aux)")
        if self.sample_rate:
            parts.append(f"{self.sample_rate} Hz")
        if self.width and self.height:
            parts.append(f"{self.width}×{self.height}")
        flags = []
        if self.is_default:
            flags.append("par défaut")
        if self.is_forced:
            flags.append("forcée")
        if flags:
            parts.append(f"({', '.join(flags)})")
        return " · ".join(parts)


@dataclass(frozen=True)
class MediaScan:
    """Caractéristiques d'un fichier média relevées lors de l'inventaire."""

    path: Path
    kind: MediaKind
    size_bytes: int
    modified_at: str
    container: str = ""
    duration_seconds: float | None = None
    video_codec: str = ""
    audio_codec: str = ""
    resolution: str = ""
    fps: float | None = None
    bitrate_bps: int | None = None
    video_tracks: int = 0
    audio_tracks: int = 0
    subtitle_tracks: int = 0
    source: str = ""
    probe_error: str = ""

    def duration_human(self) -> str:
        if self.duration_seconds is None or self.duration_seconds <= 0:
            return "—"
        total_ms = int(round(self.duration_seconds * 1000))
        hours, rem = divmod(total_ms, 3_600_000)
        minutes, rem = divmod(rem, 60_000)
        seconds, millis = divmod(rem, 1000)
        if hours:
            return f"{hours:02d}:{minutes:02d}:{seconds:02d}.{millis:03d}"
        return f"{minutes:02d}:{seconds:02d}.{millis:03d}"

    def to_dict(self) -> dict[str, Any]:
        """Dictionnaire prêt pour l'export CSV de l'inventaire."""
        return {
            "Fichier": self.path.name,
            "Dossier": str(self.path.parent),
            "Type": self.kind.label,
            "Taille (octets)": self.size_bytes,
            "Durée": self.duration_human(),
            "Conteneur": self.container,
            "Codec vidéo": self.video_codec,
            "Codec audio": self.audio_codec,
            "Résolution": self.resolution,
            "FPS": f"{self.fps:.3f}".replace(".", ",") if self.fps else "",
            "Pistes vidéo": self.video_tracks,
            "Pistes audio": self.audio_tracks,
            "Sous-titres": self.subtitle_tracks,
            "Source": self.source,
            "Remarque": self.probe_error,
        }


@dataclass(frozen=True)
class RenameStep:
    """Étape de renommage planifiée pour un fichier."""

    original: Path
    new_path: Path
    status: str  # "ok" | "inchangé" | "conflit" | "erreur"
    message: str = ""

    @property
    def changed(self) -> bool:
        return self.status in {"ok", "conflit"}


@dataclass
class RenameResult:
    """Bilan d'un renommage par lots."""

    renamed: list[tuple[Path, Path]] = field(default_factory=list)
    skipped: list[tuple[Path, str]] = field(default_factory=list)
    failed: list[tuple[Path, str]] = field(default_factory=list)

    @property
    def total(self) -> int:
        return len(self.renamed) + len(self.skipped) + len(self.failed)


@dataclass(frozen=True)
class PlannedCopy:
    """Copie planifiée par le mode « Préparer mon projet »."""

    source: Path
    destination: Path
    kind: MediaKind
    collision: bool
    reason: str = ""

    @property
    def status(self) -> str:
        return "conflit" if self.collision else "prêt"


@dataclass
class ImportResult:
    """Bilan d'une organisation de médias dans un projet."""

    copied: list[tuple[Path, Path]] = field(default_factory=list)
    skipped: list[tuple[Path, str]] = field(default_factory=list)
    failed: list[tuple[Path, str]] = field(default_factory=list)

    @property
    def total(self) -> int:
        return len(self.copied) + len(self.skipped) + len(self.failed)
