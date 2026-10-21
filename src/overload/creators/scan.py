"""Inventaire des médias : sources, codecs et caractéristiques, exportable en CSV.

- `scan_file` relève les caractéristiques d'un fichier (taille, date, conteneur,
  codecs, résolution, FPS, pistes) via FFprobe quand il est disponible ;
- `scan_tree` parcourt un dossier et construit l'inventaire complet ;
- `export_inventory_csv` écrit une liste CSV lisible dans Excel en français
  (séparateur « ; », encodage UTF-8 avec BOM).

Aucune de ces opérations ne modifie les fichiers analysés.
"""

from __future__ import annotations

import csv
import json
import subprocess
from collections.abc import Callable, Iterable
from datetime import UTC, datetime
from pathlib import Path

from overload.core.errors import OverloadError
from overload.creators.models import MediaScan
from overload.creators.structure import classify_file, iter_media_files
from overload.media.analyzer import number, run_tool

PROBE_TIMEOUT = 60

ProgressCallback = Callable[[int, int, str], None]


def probe_metadata(path: Path | str, *, timeout: int = PROBE_TIMEOUT) -> dict | None:
    """Retourne les métadonnées FFprobe JSON du fichier, ou `None` si indisponible."""
    try:
        code, raw, _errors = run_tool(
            "ffprobe",
            [
                "-v",
                "error",
                "-protocol_whitelist",
                "file",
                "-show_format",
                "-show_streams",
                "-of",
                "json",
                str(path),
            ],
            timeout,
        )
    except (RuntimeError, subprocess.TimeoutExpired, OSError):
        return None
    if code:
        return None
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def _scan_from_metadata(path: Path, metadata: dict | None) -> dict:
    """Extrait les caractéristiques lisibles d'une réponse FFprobe (jamais d'échec)."""
    if not metadata:
        probe_error = "caractéristiques détaillées indisponibles (FFprobe illisible ou absent)"
        return {"probe_error": probe_error}
    fmt = metadata.get("format", {}) or {}
    streams = [s for s in metadata.get("streams", []) if isinstance(s, dict)]
    data: dict = {
        "container": str(fmt.get("format_name", "") or ""),
        "duration_seconds": number(fmt.get("duration")),
        "bitrate_bps": int(rate)
        if (rate := number(fmt.get("bit_rate"))) and rate <= 2_000_000_000
        else None,
    }
    video_streams = [s for s in streams if s.get("codec_type") == "video"]
    audio_streams = [s for s in streams if s.get("codec_type") == "audio"]
    subtitle_streams = [s for s in streams if s.get("codec_type") == "subtitle"]
    data["video_tracks"] = len(video_streams)
    data["audio_tracks"] = len(audio_streams)
    data["subtitle_tracks"] = len(subtitle_streams)
    if video_streams:
        best = video_streams[0]
        width, height = best.get("width"), best.get("height")
        if isinstance(width, int) and isinstance(height, int) and width > 0 and height > 0:
            data["resolution"] = f"{width}×{height}"
        data["video_codec"] = str(best.get("codec_name", "") or "")
        rate = str(best.get("avg_frame_rate", "") or "")
        try:
            a, b = rate.split("/")
            value = float(a) / float(b) if float(b) else None
        except (ValueError, ZeroDivisionError):
            value = number(rate)
        if value and 1 <= value <= 480:
            data["fps"] = value
    if audio_streams:
        data["audio_codec"] = str(audio_streams[0].get("codec_name", "") or "")
    if not streams:
        data["probe_error"] = "aucune piste reconnue par FFprobe"
    return data


def scan_file(
    path: Path | str,
    *,
    sources: dict[str, str] | None = None,
    probe: bool = True,
) -> MediaScan:
    """Relevé complet d'un fichier : catégorie, taille, codecs, pistes et source."""
    target = Path(path)
    try:
        stat = target.stat()
        size, modified = stat.st_size, datetime.fromtimestamp(stat.st_mtime, UTC).isoformat(
            timespec="seconds"
        )
    except OSError:
        size, modified = 0, ""
    metadata = probe_metadata(target) if probe else None
    details = _scan_from_metadata(target, metadata)
    source_url = ""
    if sources:
        try:
            source_url = sources.get(str(target.resolve()), "")
        except OSError:
            source_url = ""
    return MediaScan(
        path=target,
        kind=classify_file(target),
        size_bytes=size,
        modified_at=modified,
        container=details.get("container", ""),
        duration_seconds=details.get("duration_seconds"),
        video_codec=details.get("video_codec", ""),
        audio_codec=details.get("audio_codec", ""),
        resolution=details.get("resolution", ""),
        fps=details.get("fps"),
        bitrate_bps=details.get("bitrate_bps"),
        video_tracks=details.get("video_tracks", 0),
        audio_tracks=details.get("audio_tracks", 0),
        subtitle_tracks=details.get("subtitle_tracks", 0),
        source=source_url,
        probe_error=details.get("probe_error", ""),
    )


def scan_tree(
    folder: Path | str,
    *,
    recursive: bool = True,
    sources: dict[str, str] | None = None,
    probe: bool = True,
    progress: ProgressCallback | None = None,
) -> list[MediaScan]:
    """Construit l'inventaire de tous les médias d'un dossier (lecture seule)."""
    root = Path(folder)
    if not root.is_dir():
        raise OverloadError(
            "Dossier introuvable.",
            f"le chemin « {root} » ne désigne pas un dossier existant.",
            "Choisissez un dossier présent sur ce disque.",
        )
    files = list(iter_media_files(root, recursive=recursive))
    total = len(files)
    scans: list[MediaScan] = []
    for done, path in enumerate(files, start=1):
        if progress is not None:
            progress(done, total, path.name)
        scans.append(scan_file(path, sources=sources, probe=probe))
    return scans


INVENTORY_COLUMNS = [
    "Fichier",
    "Dossier",
    "Type",
    "Taille (octets)",
    "Durée",
    "Conteneur",
    "Codec vidéo",
    "Codec audio",
    "Résolution",
    "FPS",
    "Pistes vidéo",
    "Pistes audio",
    "Sous-titres",
    "Source",
    "Remarque",
]


def export_inventory_csv(rows: Iterable[MediaScan], destination: Path | str) -> Path:
    """Écrit la liste des sources, codecs et caractéristiques au format CSV.

    Le fichier est écrit en UTF-8 avec BOM et séparateur « ; » pour s'ouvrir
    directement dans Excel en français. Un fichier existant n'est jamais
    écrasé : un suffixe « (2) » est ajouté.
    """
    from overload.creators.structure import unique_path

    target = Path(destination)
    if target.suffix.lower() != ".csv":
        target = target.with_suffix(".csv")
    target = unique_path(target)
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=INVENTORY_COLUMNS, delimiter=";")
            writer.writeheader()
            for row in rows:
                writer.writerow(row.to_dict())
    except OSError as exc:
        raise OverloadError(
            "Impossible d'écrire l'inventaire CSV.",
            str(exc),
            "Vérifiez que le dossier de destination est accessible en écriture.",
        ) from exc
    return target
