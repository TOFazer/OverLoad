"""Gestion des pistes disponibles : liste, extraction de sous-titres et de l'audio.

Toutes les opérations sont locales :
- la liste des pistes provient de FFprobe (métadonnées uniquement) ;
- l'extraction d'une piste de sous-titres produit un fichier `.srt` converti ;
- l'extraction d'une piste audio produit un `.wav` PCM non compressé ;
- la création d'un modèle `.srt` ne demande aucun outil : c'est un simple squelette.

Le fichier source n'est jamais modifié : les pistes sont extraites vers un
nouveau fichier dans le dossier de destination choisi.
"""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from overload.core.errors import OverloadError
from overload.creators.models import TrackInfo
from overload.creators.structure import unique_path
from overload.media.analyzer import run_tool

PROBE_TIMEOUT = 60
EXTRACT_TIMEOUT = 1800


@dataclass(frozen=True)
class TracksReport:
    """Résultat de l'analyse des pistes d'un fichier média."""

    path: Path
    container: str = ""
    duration_seconds: float | None = None
    tracks: tuple[TrackInfo, ...] = field(default_factory=tuple)

    def of_kind(self, kind: str) -> list[TrackInfo]:
        return [t for t in self.tracks if t.kind == kind]

    def summary(self) -> str:
        video = len(self.of_kind("video"))
        audio = len(self.of_kind("audio"))
        subs = len(self.of_kind("subtitle"))
        return f"{video} piste(s) vidéo · {audio} piste(s) audio · {subs} piste(s) de sous-titres"


def parse_tracks(metadata: dict) -> tuple[str, float | None, tuple[TrackInfo, ...]]:
    """Convertit une réponse FFprobe JSON en `(conteneur, durée, pistes)`."""
    fmt = metadata.get("format", {})
    container = str(fmt.get("format_name", "") or "")
    duration: float | None = None
    try:
        value = float(str(fmt.get("duration", "")))
        duration = value if value > 0 else None
    except (TypeError, ValueError):
        duration = None

    counters: dict[str, int] = {}
    tracks: list[TrackInfo] = []
    for stream in metadata.get("streams", []):
        kind = str(stream.get("codec_type", "") or "")
        if kind not in {"video", "audio", "subtitle"}:
            continue
        kind_index = counters.get(kind, 0)
        counters[kind] = kind_index + 1
        tags = stream.get("tags", {}) or {}
        disposition = stream.get("disposition", {}) or {}
        channels = stream.get("channels")
        tracks.append(
            TrackInfo(
                index=int(stream.get("index", len(tracks))),
                kind=kind,
                kind_index=kind_index,
                codec=str(stream.get("codec_name", "") or "inconnu"),
                codec_long=str(stream.get("codec_long_name", "") or ""),
                language=str(tags.get("language", "") or ""),
                title=str(tags.get("title", "") or ""),
                is_default=bool(disposition.get("default")),
                is_forced=bool(disposition.get("forced")),
                channels=int(channels) if isinstance(channels, int) else None,
                sample_rate=str(stream.get("sample_rate", "") or ""),
                width=stream.get("width") if isinstance(stream.get("width"), int) else None,
                height=stream.get("height") if isinstance(stream.get("height"), int) else None,
            )
        )
    return container, duration, tuple(tracks)


def probe_tracks(path: Path | str, *, timeout: int = PROBE_TIMEOUT) -> TracksReport:
    """Liste toutes les pistes disponibles d'un fichier local (lecture seule)."""
    target = Path(path).expanduser().resolve()
    if not target.is_file():
        raise OverloadError(
            "Fichier introuvable.",
            f"le chemin « {target} » ne désigne pas un fichier existant.",
            "Choisissez un média présent sur ce disque.",
        )
    try:
        code, raw, errors = run_tool(
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
                str(target),
            ],
            timeout,
        )
    except subprocess.TimeoutExpired as exc:
        raise OverloadError(
            "L'analyse des pistes a pris trop de temps.",
            f"FFprobe n'a pas répondu en {timeout} secondes.",
            "Réessayez : un délai dépassé ne prouve pas que le fichier est endommagé.",
        ) from exc
    except RuntimeError as exc:  # outils FFmpeg absents (développement)
        raise OverloadError(
            "Outils multimédias indisponibles.",
            str(exc),
            "Utilisez l'édition Windows complète d'OverLoad (FFmpeg embarqué).",
        ) from exc
    if code:
        raise OverloadError(
            "Impossible de lire les pistes de ce fichier.",
            (errors.strip() or "FFprobe a refusé le fichier.").splitlines()[0],
            "Vérifiez que le fichier est complet et dans un format pris en charge.",
        )
    try:
        metadata = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise OverloadError(
            "Réponse FFprobe invalide.",
            str(exc),
            "Réessayez ; si le problème persiste, le fichier est peut-être endommagé.",
        ) from exc
    container, duration, tracks = parse_tracks(metadata)
    return TracksReport(path=target, container=container, duration_seconds=duration, tracks=tracks)


def _ffmpeg_extract(
    media: Path,
    *,
    stream_selector: str,
    output_args: list[str],
    destination: Path,
    timeout: int,
) -> Path:
    try:
        code, _, errors = run_tool(
            "ffmpeg",
            [
                "-hide_banner",
                "-v",
                "error",
                "-nostdin",
                "-protocol_whitelist",
                "file",
                "-i",
                str(media),
                "-map",
                stream_selector,
                *output_args,
                "-y",
                str(destination),
            ],
            timeout,
        )
    except subprocess.TimeoutExpired as exc:
        raise OverloadError(
            "L'extraction a été arrêtée : délai maximal atteint.",
            f"FFmpeg n'a pas terminé en {timeout} secondes.",
            "Le fichier est peut-être très long ; réessayez ou extrayez une copie plus courte.",
        ) from exc
    except RuntimeError as exc:
        raise OverloadError(
            "Outils multimédias indisponibles.",
            str(exc),
            "Utilisez l'édition Windows complète d'OverLoad (FFmpeg embarqué).",
        ) from exc
    if code or not destination.exists() or destination.stat().st_size == 0:
        detail = errors.strip().splitlines()[0] if errors.strip() else "code de retour non nul"
        raise OverloadError(
            "L'extraction de la piste a échoué.",
            detail,
            "Cette piste est peut-être vide, dans un format non convertible, ou le fichier "
            "source est incomplet.",
        )
    return destination


def extract_subtitle_track(
    media: Path | str,
    track_number: int,
    destination_dir: Path | str,
    *,
    base_name: str | None = None,
    timeout: int = EXTRACT_TIMEOUT,
) -> Path:
    """Extrait la piste de sous-titres n° `track_number` (0 = première) en `.srt`.

    Le média source n'est jamais modifié ; le `.srt` est écrit dans le dossier de
    destination choisi, sous un nom unique (jamais d'écrasement).
    """
    source = Path(media).expanduser().resolve()
    if not source.is_file():
        raise OverloadError(
            "Fichier introuvable.",
            f"le chemin « {source} » ne désigne pas un fichier existant.",
            "Choisissez un média présent sur ce disque.",
        )
    out_dir = Path(destination_dir)
    try:
        out_dir.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise OverloadError(
            "Dossier de destination inaccessible.",
            str(exc),
            "Choisissez un dossier où vous avez le droit d'écrire.",
        ) from exc
    stem = base_name or source.stem
    destination = unique_path(out_dir / f"{stem} - sous-titres {track_number + 1:02d}.srt")
    return _ffmpeg_extract(
        source,
        stream_selector=f"0:s:{max(0, track_number)}",
        output_args=["-c:s", "srt"],
        destination=destination,
        timeout=timeout,
    )


def extract_audio_track(
    media: Path | str,
    track_number: int,
    destination_dir: Path | str,
    *,
    base_name: str | None = None,
    timeout: int = EXTRACT_TIMEOUT,
) -> Path:
    """Extrait la piste audio n° `track_number` (0 = première) en `.wav` PCM.

    Utile pour préparer une narration ou un mixage dans le logiciel de montage.
    Le média source n'est jamais modifié.
    """
    source = Path(media).expanduser().resolve()
    if not source.is_file():
        raise OverloadError(
            "Fichier introuvable.",
            f"le chemin « {source} » ne désigne pas un fichier existant.",
            "Choisissez un média présent sur ce disque.",
        )
    out_dir = Path(destination_dir)
    try:
        out_dir.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise OverloadError(
            "Dossier de destination inaccessible.",
            str(exc),
            "Choisissez un dossier où vous avez le droit d'écrire.",
        ) from exc
    stem = base_name or source.stem
    destination = unique_path(out_dir / f"{stem} - audio {track_number + 1:02d}.wav")
    return _ffmpeg_extract(
        source,
        stream_selector=f"0:a:{max(0, track_number)}",
        output_args=["-c:a", "pcm_s16le"],
        destination=destination,
        timeout=timeout,
    )


def create_srt_template(
    destination: Path | str,
    *,
    title: str = "",
) -> Path:
    """Crée un modèle de sous-titres `.srt` prêt à compléter (UTF-8, sans outil)."""
    target = Path(destination)
    if target.suffix.lower() != ".srt":
        target = target.with_suffix(".srt")
    target = unique_path(target)
    header_cue = ""
    if title.strip():
        header_cue = (
            "1\n"
            "00:00:00,100 --> 00:00:02,900\n"
            f"{title.strip()}\n"
            "\n"
        )
    body = (
        "2\n"
        "00:00:03,000 --> 00:00:05,800\n"
        "Remplacez ce texte par votre premier sous-titre.\n"
        "\n"
        "3\n"
        "00:00:06,000 --> 00:00:08,800\n"
        "Une ou deux lignes courtes, synchronisées sur la voix.\n"
        "\n"
        "4\n"
        "00:00:09,000 --> 00:00:11,800\n"
        "Enregistrez ce fichier en UTF-8 pour conserver les accents.\n"
    )
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(header_cue + body, encoding="utf-8")
    except OSError as exc:
        raise OverloadError(
            "Impossible de créer le modèle de sous-titres.",
            str(exc),
            "Vérifiez que le dossier de destination est accessible en écriture.",
        ) from exc
    return target
