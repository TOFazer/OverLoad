"""Extraction et téléchargement de vidéos YouTube via `yt-dlp`.

Le moteur HTTP direct (`engine.py`) ne sait télécharger qu'un fichier déjà
exposé par une URL. Une page YouTube n'est pas un fichier : il faut extraire les
flux vidéo et audio, les télécharger puis les fusionner en MP4.

Ce module encapsule `yt-dlp` (bibliothèque Python, licence Unlicense) et
n'accepte que des adresses YouTube publiques. Il ne contourne ni les DRM, ni les
protections d'accès, ni les restrictions d'une plateforme : les vidéos privées,
réservées à un compte ou protégées par un contrôle d'âge sont refusées avec un
message explicite.

Responsabilités :
- reconnaître une adresse YouTube et en extraire l'identifiant de vidéo ;
- interroger les métadonnées (titre, auteur, durée, miniature, qualités) ;
- télécharger vidéo + audio, fusionner en MP4 avec le FFmpeg embarqué ;
- respecter pause, annulation et limite de vitesse ;
- vérifier le fichier final (présence réelle d'une piste vidéo) avant de le
  déclarer terminé.
"""

from __future__ import annotations

import json
import os
import re
import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlsplit

from overload.core.errors import OverloadError
from overload.core.formatting import format_duration
from overload.downloads.engine import DownloadCancelled, DownloadPaused

ProgressCallback = Callable[[int, int | None], None]

YOUTUBE_HOSTS = frozenset(
    {
        "youtube.com",
        "www.youtube.com",
        "m.youtube.com",
        "music.youtube.com",
        "youtube-nocookie.com",
        "www.youtube-nocookie.com",
        "youtu.be",
        "www.youtu.be",
    }
)

# Qualités proposées dans l'interface : « best » puis des hauteurs en pixels.
QUALITY_CHOICES: tuple[tuple[str, str], ...] = (
    ("best", "Meilleure disponible"),
    ("2160p", "2160p (4K)"),
    ("1440p", "1440p (QHD)"),
    ("1080p", "1080p (Full HD)"),
    ("720p", "720p (HD)"),
    ("480p", "480p (SD)"),
    ("360p", "360p (SD)"),
)
QUALITY_VALUES = tuple(value for value, _ in QUALITY_CHOICES)
_QUALITY_LABELS = dict(QUALITY_CHOICES)
_VIDEO_ID_RE = re.compile(r"^[A-Za-z0-9_-]{6,20}$")
_MEDIA_SUFFIXES = frozenset({".mp4", ".mkv", ".webm", ".mov", ".m4a", ".opus"})
_ARTIFACT_SUFFIXES = (".part", ".ytdl", ".temp")


def youtube_video_id(url: str) -> str | None:
    """Retourne l'identifiant de la vidéo si `url` est une adresse YouTube valide."""
    if not isinstance(url, str):
        return None
    text = url.strip()
    if not text:
        return None
    if "://" not in text:
        text = "https://" + text
    try:
        parts = urlsplit(text)
    except ValueError:
        return None
    if parts.scheme.lower() not in {"http", "https"}:
        return None
    host = (parts.hostname or "").lower().rstrip(".")
    if host not in YOUTUBE_HOSTS:
        return None

    if host in {"youtu.be", "www.youtu.be"}:
        candidate = parts.path.strip("/").split("/")[0]
        return candidate if _VIDEO_ID_RE.match(candidate) else None

    segments = [segment for segment in parts.path.split("/") if segment]
    if not segments:
        return None

    if segments[0] in {"watch", "embed", "shorts", "live", "v", "e"}:
        if segments[0] in {"watch", "v"} and len(segments) > 1:
            candidate = segments[1]
        elif len(segments) > 1:
            candidate = segments[1]
        else:
            candidate = parse_qs(parts.query).get("v", [""])[0]
        return candidate if _VIDEO_ID_RE.match(candidate) else None

    query_id = parse_qs(parts.query).get("v", [""])[0]
    if query_id and _VIDEO_ID_RE.match(query_id):
        return query_id
    return None


def is_youtube_url(url: str) -> bool:
    """Vrai si l'adresse désigne une vidéo YouTube prise en charge."""
    return youtube_video_id(url) is not None


def normalize_quality(quality: str | None) -> str:
    """Valide un choix de qualité et retourne sa valeur canonique (`best` par défaut)."""
    if quality is None or not str(quality).strip():
        return "best"
    value = str(quality).strip().lower()
    if value in QUALITY_VALUES:
        return value
    # Tolère « 1080 », « 1080p60 », « bestvideo »…
    match = re.match(r"^(\d{3,4})", value)
    if match:
        candidate = f"{match.group(1)}p"
        if candidate in QUALITY_VALUES:
            return candidate
        return f"{int(match.group(1))}p"
    if value in {"max", "meilleure", "bestvideo", "highest"}:
        return "best"
    raise OverloadError(
        "Qualité vidéo non reconnue.",
        f"la valeur « {quality} » n'est pas proposée.",
        "Choisissez « Meilleure disponible » ou une hauteur (1080p, 720p…).",
    )


def quality_label(quality: str | None) -> str:
    """Libellé lisible d'une qualité, y compris pour une hauteur hors liste."""
    value = normalize_quality(quality)
    return _QUALITY_LABELS.get(value, value.upper() if value.endswith("p") else value)


def format_selector(quality: str | None) -> str:
    """Construit le sélecteur `yt-dlp` privilégiant un MP4 H.264 + AAC lisible partout.

    H.264/AAC dans un conteneur MP4 est le couple le mieux accepté par VLC, Adobe
    Premiere Pro et Windows. Si la vidéo n'existe qu'en VP9/AV1, une solution de
    repli est utilisée puis remuxée en MP4 ; la compatibilité n'est jamais garantie.
    """
    value = normalize_quality(quality)
    if value == "best":
        return (
            "bv*[ext=mp4][vcodec^=avc1]+ba[ext=m4a]/"
            "b[ext=mp4]/"
            "bv*+ba/b"
        )
    height = int(value[:-1])
    return (
        f"bv*[height<={height}][ext=mp4][vcodec^=avc1]+ba[ext=m4a]/"
        f"b[height<={height}][ext=mp4]/"
        f"bv*[height<={height}]+ba/"
        f"b[height<={height}]/"
        "b"
    )


@dataclass(frozen=True)
class MediaInfo:
    """Métadonnées d'une vidéo YouTube, telles qu'affichées avant téléchargement."""

    url: str
    video_id: str
    title: str
    uploader: str = ""
    duration_seconds: float | None = None
    thumbnail_url: str = ""
    heights: tuple[int, ...] = ()
    is_live: bool = False

    @property
    def safe_title(self) -> str:
        return self.title.strip() or f"video-{self.video_id}"

    def to_dict(self, *, quality: str | None = None) -> dict[str, Any]:
        choices = [
            {"value": "best", "label": _QUALITY_LABELS["best"]},
            *[
                {"value": f"{height}p", "label": _QUALITY_LABELS.get(f"{height}p", f"{height}p")}
                for height in self.heights
            ],
        ]
        existing = {item["value"] for item in choices}
        if quality:
            normalized = normalize_quality(quality)
            if normalized not in existing and normalized in QUALITY_VALUES:
                choices.append({"value": normalized, "label": quality_label(normalized)})
        return {
            "provider": "youtube",
            "url": self.url,
            "video_id": self.video_id,
            "title": self.safe_title,
            "uploader": self.uploader,
            "duration_seconds": (
                round(self.duration_seconds, 1) if self.duration_seconds is not None else None
            ),
            "duration_human": format_duration(self.duration_seconds),
            "thumbnail_url": self.thumbnail_url,
            "heights": list(self.heights),
            "is_live": self.is_live,
            "qualities": choices,
            "selected_quality": normalize_quality(quality),
        }


@dataclass
class _ProgressState:
    """Agrège la progression des flux vidéo et audio téléchargés séparément."""

    per_file_done: dict[str, int] = field(default_factory=dict)
    per_file_total: dict[str, int] = field(default_factory=dict)
    reported: int = 0

    def downloaded(self) -> int:
        total = sum(self.per_file_done.values())
        return max(total, self.reported)

    def total(self) -> int | None:
        if not self.per_file_total:
            return None
        total = sum(self.per_file_total.values())
        return max(total, self.downloaded())


class YoutubeExtractor:
    """Façade `yt-dlp` limitée à YouTube, injectable dans le `DownloadManager`."""

    def __init__(
        self,
        *,
        module: Any | None = None,
        ffmpeg_dir: Path | str | None = None,
        socket_timeout: float = 20.0,
        probe_cache_size: int = 64,
        ffprobe_available: Callable[[], bool] | None = None,
    ) -> None:
        self._module = module
        self._ffmpeg_dir = Path(ffmpeg_dir) if ffmpeg_dir is not None else None
        self._socket_timeout = max(5.0, float(socket_timeout))
        self._cache_limit = max(0, int(probe_cache_size))
        self._cache: dict[str, MediaInfo] = {}
        self._lock = threading.RLock()
        self._ffprobe_available = ffprobe_available

    # -- Dépendances -----------------------------------------------------
    def _load(self) -> Any:
        if self._module is None:
            try:
                import yt_dlp  # noqa: PLC0415
            except ImportError as exc:  # pragma: no cover - dépend de l'installation
                raise OverloadError(
                    "Le module YouTube (yt-dlp) est absent de cette installation.",
                    "cette édition d'OverLoad ne contient pas l'extracteur YouTube.",
                    "Utilisez la version Windows complète d'OverLoad ou installez « yt-dlp ».",
                ) from exc
            self._module = yt_dlp
        return self._module

    def available(self) -> bool:
        """Vrai si `yt-dlp` est importable (sans réseau)."""
        try:
            self._load()
        except OverloadError:
            return False
        return True

    def ffmpeg_dir(self) -> str | None:
        """Dossier contenant `ffmpeg.exe`/`ffprobe.exe` à transmettre à yt-dlp."""
        if self._ffmpeg_dir is not None:
            return str(self._ffmpeg_dir)
        try:
            from overload.media.analyzer import tool_path  # noqa: PLC0415
        except Exception:  # noqa: BLE001 - pas de FFmpeg : yt-dlp cherchera dans le PATH
            return None
        try:
            return str(Path(tool_path("ffmpeg")).resolve().parent)
        except RuntimeError:
            return None

    # -- Métadonnées -----------------------------------------------------
    def probe(self, url: str, *, use_cache: bool = True) -> MediaInfo:
        """Récupère titre, durée, miniature et hauteurs disponibles."""
        video_id = youtube_video_id(url)
        if video_id is None:
            raise OverloadError(
                "Cette adresse n'est pas une vidéo YouTube prise en charge.",
                "le lien ne contient pas d'identifiant de vidéo.",
                "Copiez l'adresse d'une vidéo (youtube.com/watch?v=… ou youtu.be/…).",
            )
        if use_cache:
            with self._lock:
                cached = self._cache.get(video_id)
            if cached is not None:
                return cached

        module = self._load()
        options = {
            "quiet": True,
            "no_warnings": True,
            "noplaylist": True,
            "skip_download": True,
            "socket_timeout": self._socket_timeout,
            "extract_flat": False,
        }
        try:
            with module.YoutubeDL(options) as ydl:
                raw = ydl.extract_info(url, download=False)
        except Exception as exc:  # noqa: BLE001 - traduit en erreur utilisateur
            raise self._translate_error(exc) from exc

        if not isinstance(raw, dict):
            raise OverloadError(
                "Informations vidéo indisponibles.",
                "YouTube n'a renvoyé aucune métadonnée exploitable.",
                "Vérifiez le lien ou réessayez plus tard.",
            )
        if raw.get("_type") == "playlist" and raw.get("entries"):
            raw = raw["entries"][0] or {}

        heights = _available_heights(raw)
        info = MediaInfo(
            url=raw.get("webpage_url") or url,
            video_id=str(raw.get("id") or video_id),
            title=str(raw.get("title") or f"video-{video_id}"),
            uploader=str(raw.get("uploader") or raw.get("channel") or ""),
            duration_seconds=_as_float(raw.get("duration")),
            thumbnail_url=str(raw.get("thumbnail") or ""),
            heights=heights,
            is_live=bool(raw.get("is_live")),
        )
        if self._cache_limit:
            with self._lock:
                if len(self._cache) >= self._cache_limit:
                    self._cache.pop(next(iter(self._cache)), None)
                self._cache[video_id] = info
        return info

    # -- Téléchargement --------------------------------------------------
    def download(
        self,
        url: str,
        target: Path,
        *,
        quality: str | None = None,
        progress: ProgressCallback | None = None,
        cancel_event: threading.Event | None = None,
        pause_event: threading.Event | None = None,
        max_rate_bps: int | None = None,
        timeout: float | None = None,
    ) -> MediaInfo:
        """Télécharge la vidéo et la fusionne en MP4 vers `target`.

        Lève `DownloadCancelled` / `DownloadPaused` (mêmes exceptions que le
        moteur HTTP), `OverloadError` pour toute autre erreur utilisateur.
        """
        target = Path(target)
        if target.suffix.lower() != ".mp4":
            target = target.with_suffix(".mp4")
        if target.exists():
            raise OverloadError(
                "Un fichier porte déjà ce nom.",
                "le téléchargement ne remplace jamais un fichier existant.",
                "Choisissez un autre nom de fichier.",
            )
        if not target.parent.is_dir():
            raise OverloadError(
                "Le dossier de destination est introuvable.",
                "il a été supprimé ou il n'est pas accessible.",
                "Choisissez un autre dossier dans les paramètres.",
            )

        module = self._load()
        info = self.probe(url)
        stem = target.with_suffix("")
        state = _ProgressState()

        def report(done: int, total: int | None) -> None:
            state.reported = max(state.reported, done)
            if progress is not None:
                progress(state.reported, total)

        def check_interruptions() -> None:
            if cancel_event is not None and cancel_event.is_set():
                raise DownloadCancelled("Téléchargement annulé.")
            if pause_event is not None and pause_event.is_set():
                raise DownloadPaused("Téléchargement mis en pause.")

        def on_progress(hook: dict[str, Any]) -> None:
            check_interruptions()
            status = hook.get("status")
            if status == "downloading":
                name = str(hook.get("filename") or "")
                done = int(hook.get("downloaded_bytes") or 0)
                total = hook.get("total_bytes") or hook.get("total_bytes_estimate")
                state.per_file_done[name] = max(state.per_file_done.get(name, 0), done)
                if total:
                    state.per_file_total[name] = int(total)
                report(state.downloaded(), state.total())
            elif status == "finished":
                name = str(hook.get("filename") or "")
                done = int(hook.get("total_bytes") or 0)
                if done:
                    state.per_file_done[name] = max(state.per_file_done.get(name, 0), done)
                    state.per_file_total[name] = done
                report(state.downloaded(), state.total())
            elif status == "error":
                check_interruptions()

        def on_postprocessor(hook: dict[str, Any]) -> None:
            check_interruptions()
            if hook.get("status") in {"started", "processing"}:
                done = state.downloaded()
                if progress is not None and done > 0:
                    # La fusion n'émet pas d'octets : on garde la barre pleine
                    # sans prétendre à une progression mesurée.
                    progress(done, done)

        options: dict[str, Any] = {
            "format": format_selector(quality),
            "outtmpl": {"default": _escape_outtmpl(stem) + ".%(ext)s"},
            "merge_output_format": "mp4",
            "noplaylist": True,
            "quiet": True,
            "no_warnings": True,
            "noprogress": True,
            "progress_hooks": [on_progress],
            "postprocessor_hooks": [on_postprocessor],
            "continuedl": True,
            "nopart": False,
            "retries": 3,
            "fragment_retries": 5,
            "socket_timeout": max(5.0, float(timeout or self._socket_timeout)),
            "overwrites": False,
            "windowsfilenames": True,
            "postprocessors": [
                {"key": "FFmpegVideoRemuxer", "preferedformat": "mp4"},
            ],
        }
        ffmpeg_dir = self.ffmpeg_dir()
        if ffmpeg_dir:
            options["ffmpeg_location"] = ffmpeg_dir
        if max_rate_bps is not None and max_rate_bps > 0:
            options["ratelimit"] = int(max_rate_bps)

        try:
            with module.YoutubeDL(options) as ydl:
                ydl.download([url])
        except DownloadPaused:
            raise
        except DownloadCancelled:
            # Une annulation ne laisse aucun fragment derrière elle.
            _cleanup_artifacts(stem)
            raise
        except Exception as exc:  # noqa: BLE001 - traduit en erreur utilisateur
            raise self._translate_error(exc) from exc

        check_interruptions()
        produced = _finalize_output(stem, target)
        verify_downloaded_media(
            produced,
            ffprobe_available=self._ffprobe_available,
        )
        return info

    # -- Traduction des erreurs ------------------------------------------
    def _translate_error(self, exc: BaseException) -> OverloadError:
        if isinstance(exc, OverloadError):
            return exc
        raw = str(exc)
        text = raw.lower()

        if "private video" in text or "this video is private" in text:
            return OverloadError(
                "Cette vidéo YouTube est privée.",
                "son propriétaire ne l'a pas rendue publique.",
                "Utilisez une vidéo publique ou demandez l'accès à son auteur.",
            )
        if "sign in to confirm your age" in text or "age-restricted" in text:
            return OverloadError(
                "Cette vidéo est réservée à un public majeur.",
                "YouTube exige une connexion à un compte pour la lire.",
                "OverLoad ne se connecte à aucun compte : choisissez une autre vidéo.",
            )
        if "members-only" in text or "join this channel" in text:
            return OverloadError(
                "Cette vidéo est réservée aux membres de la chaîne.",
                "un abonnement payant est nécessaire pour la regarder.",
                "Choisissez une vidéo publique.",
            )
        if any(
            marker in text
            for marker in (
                "video unavailable",
                "this video is unavailable",
                "has been removed",
                "no longer available",
                "does not exist",
            )
        ):
            return OverloadError(
                "Cette vidéo YouTube n'est pas disponible.",
                "elle a été supprimée, rendue privée ou bloquée dans votre pays.",
                "Vérifiez le lien ou choisissez une autre vidéo.",
            )
        if "unsupported url" in text or "is not a valid url" in text:
            return OverloadError(
                "Cette adresse n'est pas prise en charge.",
                "le lien ne correspond à aucune vidéo YouTube reconnue.",
                "Copiez l'adresse complète d'une vidéo YouTube.",
            )
        if "http error 429" in text or "too many requests" in text:
            return OverloadError(
                "YouTube limite temporairement les téléchargements.",
                "trop de requêtes ont été envoyées en peu de temps.",
                "Attendez quelques minutes puis relancez le téléchargement.",
            )
        if "requested format is not available" in text:
            return OverloadError(
                "Cette qualité n'est pas disponible pour cette vidéo.",
                "YouTube ne propose pas le format demandé.",
                "Choisissez « Meilleure disponible » ou une qualité inférieure.",
            )
        if "ffmpeg" in text or "ffprobe" in text:
            return OverloadError(
                "La fusion audio/vidéo a échoué.",
                "FFmpeg est introuvable ou n'a pas pu être exécuté.",
                "Réinstallez OverLoad depuis la version Windows complète, puis relancez.",
            )
        if any(
            marker in text
            for marker in (
                "timed out",
                "timeout",
                "temporary failure in name resolution",
                "getaddrinfo",
                "connection reset",
                "connection refused",
                "unable to download webpage",
                "network is unreachable",
                "ssl",
                "certificate",
            )
        ):
            return OverloadError(
                "Connexion impossible ou interrompue.",
                _short(raw),
                "Vérifiez votre connexion Internet puis relancez le téléchargement.",
            )
        return OverloadError(
            "Le téléchargement YouTube a échoué.",
            _short(raw),
            "Vérifiez le lien, puis relancez le téléchargement.",
        )


# ----------------------------------------------------------------------
# Vérification du fichier final
# ----------------------------------------------------------------------
def verify_downloaded_media(
    path: Path,
    *,
    ffprobe_available: Callable[[], bool] | None = None,
) -> dict[str, Any]:
    """Contrôle qu'un vrai média non vide a été produit.

    - fichier présent et non vide ;
    - au moins une piste vidéo décodable (via FFprobe embarqué) ;
    - durée strictement positive.

    Si FFprobe est absent, la vérification se limite à la taille et un
    avertissement est renvoyé (mais aucun fichier vide n'est validé).
    """
    path = Path(path)
    if not path.is_file():
        raise OverloadError(
            "Le fichier vidéo n'a pas été créé.",
            "l'extraction n'a produit aucun fichier final.",
            "Relancez le téléchargement ; si le problème persiste, changez de qualité.",
        )
    size = path.stat().st_size
    if size <= 0:
        path.unlink(missing_ok=True)
        raise OverloadError(
            "Le fichier téléchargé est vide.",
            "aucune donnée vidéo n'a été écrite sur le disque.",
            "Relancez le téléchargement ou choisissez une autre qualité.",
        )

    if ffprobe_available is None:
        try:
            from overload.media.analyzer import run_tool, tool_path  # noqa: PLC0415

            tool_path("ffprobe")
        except Exception:  # noqa: BLE001 - outil absent : vérification partielle
            return {
                "verified": False,
                "size_bytes": size,
                "warning": "FFprobe est introuvable : vérification limitée à la taille du fichier.",
            }
    elif not ffprobe_available():
        return {
            "verified": False,
            "size_bytes": size,
            "warning": "FFprobe est introuvable : vérification limitée à la taille du fichier.",
        }

    from overload.media.analyzer import run_tool  # noqa: PLC0415

    try:
        code, out, err = run_tool(
            "ffprobe",
            [
                "-v",
                "error",
                "-print_format",
                "json",
                "-show_format",
                "-show_streams",
                str(path),
            ],
            timeout=60,
        )
    except Exception as exc:  # noqa: BLE001 - FFprobe indisponible ou en échec
        return {
            "verified": False,
            "size_bytes": size,
            "warning": f"Vérification FFprobe impossible : {_short(str(exc))}",
        }
    if code != 0:
        raise OverloadError(
            "Le fichier téléchargé est illisible.",
            f"FFprobe n'a pas pu l'analyser : {_short(err)}",
            "Relancez le téléchargement ; sinon, choisissez une autre qualité.",
        )
    try:
        payload = json.loads(out or "{}")
    except json.JSONDecodeError:
        return {
            "verified": False,
            "size_bytes": size,
            "warning": "FFprobe a renvoyé une réponse inattendue.",
        }

    streams = payload.get("streams") or []
    if not any(stream.get("codec_type") == "video" for stream in streams):
        raise OverloadError(
            "Le fichier téléchargé ne contient pas de piste vidéo.",
            "seul un flux audio ou aucune piste exploitable a été récupéré.",
            "Relancez le téléchargement ; sinon, choisissez une autre qualité.",
        )
    duration = _as_float((payload.get("format") or {}).get("duration"))
    if duration is not None and duration <= 0:
        raise OverloadError(
            "La vidéo téléchargée a une durée nulle.",
            "le fichier final est inexploitable.",
            "Relancez le téléchargement ou choisissez une autre qualité.",
        )
    return {
        "verified": True,
        "size_bytes": size,
        "duration_seconds": duration,
        "video_streams": sum(1 for s in streams if s.get("codec_type") == "video"),
        "audio_streams": sum(1 for s in streams if s.get("codec_type") == "audio"),
    }


# ----------------------------------------------------------------------
# Utilitaires internes
# ----------------------------------------------------------------------
def _as_float(value: Any) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if result > 0 else None


def _short(text: str, limit: int = 240) -> str:
    cleaned = " ".join(str(text).split())
    return cleaned[:limit] + ("…" if len(cleaned) > limit else "")


def _escape_outtmpl(stem: Path) -> str:
    """Échappe les `%` pour que yt-dlp ne les interprète pas comme des modèles."""
    return str(stem).replace("%", "%%")


def _available_heights(raw: dict[str, Any]) -> tuple[int, ...]:
    heights: set[int] = set()
    for fmt in raw.get("formats") or []:
        if fmt.get("vcodec") in {None, "none"}:
            continue
        height = fmt.get("height")
        try:
            value = int(height)
        except (TypeError, ValueError):
            continue
        if 120 <= value <= 4320:
            heights.add(value)
    single = raw.get("height")
    try:
        if single and 120 <= int(single) <= 4320:
            heights.add(int(single))
    except (TypeError, ValueError):
        pass
    return tuple(sorted(heights, reverse=True))


def _artifact_candidates(stem: Path) -> list[Path]:
    """Fichiers voisins d'un téléchargement (`titre.f137.mp4`, `.part`, `.ytdl`…).

    On compare des noms au lieu d'utiliser `glob` : un titre peut contenir des
    caractères interprétés par les motifs globaux (`[`, `]`).
    """
    if not stem.parent.is_dir():
        return []
    prefix = stem.name + "."
    return [
        item
        for item in stem.parent.iterdir()
        if item.is_file() and item.name.startswith(prefix)
    ]


def _finalize_output(stem: Path, target: Path) -> Path:
    """Retrouve le fichier produit par yt-dlp, le renomme vers `target` et nettoie."""
    candidates: list[Path] = []
    for candidate in _artifact_candidates(stem):
        if candidate == target:
            continue
        if candidate.suffix.lower() in _MEDIA_SUFFIXES and not candidate.name.endswith(
            _ARTIFACT_SUFFIXES
        ):
            candidates.append(candidate)

    if target.is_file() and target.stat().st_size > 0:
        produced = target
    elif candidates:
        primary = max(candidates, key=lambda item: item.stat().st_size)
        os.replace(primary, target)
        produced = target
    else:
        raise OverloadError(
            "Le fichier vidéo n'a pas été créé.",
            "yt-dlp n'a produit aucun fichier lisible à l'emplacement prévu.",
            "Relancez le téléchargement ; si le problème persiste, changez de qualité.",
        )

    _cleanup_artifacts(stem, keep=produced)
    return produced


def _cleanup_artifacts(stem: Path, *, keep: Path | None = None) -> None:
    for candidate in _artifact_candidates(stem):
        if keep is not None and candidate == keep:
            continue
        try:
            candidate.unlink()
        except OSError:
            continue
