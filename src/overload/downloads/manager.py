"""Gestionnaire de téléchargements intelligent.

Fonctionnalités prises en charge :
- téléchargements simultanés avec limite configurable à chaud (`max_concurrent`) ;
- mise en pause, reprise HTTP Range et reprise automatique après erreur réseau ;
- détection des fichiers déjà présents (dossier cible, file active, historique, `.part`) ;
- limiteur de vitesse global pour ne pas saturer la connexion Internet ;
- téléchargement par lots depuis une liste de liens ou un fichier `.txt` ;
- historique SQLite persistant et ouverture directe du dossier de destination ;
- télémétrie temps réel : vitesse réelle, temps restant estimé et diagnostic réseau.
"""

from __future__ import annotations

import threading
import time
import uuid
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from overload.core.errors import OverloadError
from overload.core.formatting import format_speed
from overload.core.paths import open_folder
from overload.downloads.bandwidth import BandwidthLimiter
from overload.downloads.duplicates import (
    DuplicateDetectedError,
    DuplicateMatch,
    DuplicatePolicy,
    DuplicateSource,
    detect_duplicate,
)
from overload.downloads.engine import DownloadCancelled, DownloadPaused, download_to
from overload.downloads.files import (
    PART_SUFFIX,
    filename_from_url,
    plan_destination,
    sanitize_filename,
)
from overload.downloads.models import BatchResult, ManagerSettings, RejectedLink, TaskSnapshot
from overload.downloads.state import TaskState, transition
from overload.downloads.telemetry import (
    ConnectionIssue,
    IssueKind,
    SpeedEstimator,
    classify_error,
)
from overload.downloads.urls import parse_url_list, validate_direct_url
from overload.downloads.youtube import (
    YoutubeExtractor,
    is_youtube_url,
    normalize_quality,
    youtube_video_id,
)
from overload.history.store import DownloadHistoryStore, HistoryEntry

MIN_CONCURRENT = 1
MAX_CONCURRENT = 16
MAX_BACKOFF_SECONDS = 30.0


@dataclass
class _ManagedTask:
    id: str
    url: str
    filename: str
    target_path: Path
    state: TaskState
    queue_seq: int
    max_retries: int
    speed: SpeedEstimator
    cancel_event: threading.Event = field(default_factory=threading.Event)
    pause_event: threading.Event = field(default_factory=threading.Event)
    downloaded_bytes: int = 0
    total_bytes: int | None = None
    retry_count: int = 0
    next_retry_mono: float | None = None
    resumed_from_part: bool = False
    error_message: str = ""
    issues: list[ConnectionIssue] = field(default_factory=list)
    stall_reported: bool = False
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    started_at: str | None = None
    finished_at: str | None = None
    started_mono: float | None = None
    bytes_at_run_start: int = 0
    provider: str = "http"
    quality: str = "best"
    media_title: str = ""
    thumbnail_url: str = ""


class DownloadManager:
    """Orchestrateur thread-safe des téléchargements d'OverLoad."""

    def __init__(
        self,
        destination_dir: Path | str,
        *,
        history: DownloadHistoryStore | None = None,
        max_concurrent: int = 3,
        speed_limit_bps: int | None = None,
        auto_retry: bool = True,
        max_retries: int = 3,
        retry_initial_delay: float = 1.5,
        duplicate_policy: DuplicatePolicy = DuplicatePolicy.ASK,
        allow_private_hosts: bool = False,
        allowed_local_endpoints: Iterable[tuple[str, int]] = (),
        timeout: float = 30.0,
        stall_threshold_seconds: float = 4.0,
        clock: Callable[[], float] = time.monotonic,
        youtube: YoutubeExtractor | None = None,
        default_quality: str = "best",
    ) -> None:
        dest = Path(destination_dir).expanduser()
        dest.mkdir(parents=True, exist_ok=True)
        if max_concurrent < MIN_CONCURRENT or max_concurrent > MAX_CONCURRENT:
            raise OverloadError(
                "Limite de téléchargements simultanés invalide.",
                f"la valeur doit être comprise entre {MIN_CONCURRENT} et {MAX_CONCURRENT}.",
                "Choisissez un nombre entre 1 et 16.",
            )

        self._lock = threading.RLock()
        self._cond = threading.Condition(self._lock)
        self._clock = clock
        self._destination_dir = dest
        self._history = history
        self._owns_history = False
        self._max_concurrent = max_concurrent
        self._auto_retry = bool(auto_retry)
        self._max_retries = max(0, int(max_retries))
        self._retry_initial_delay = max(0.05, float(retry_initial_delay))
        self._duplicate_policy = DuplicatePolicy(duplicate_policy)
        self._allow_private_hosts = allow_private_hosts
        self._allowed_local_endpoints = frozenset(allowed_local_endpoints)
        self._timeout = max(1.0, float(timeout))
        self._stall_threshold_seconds = max(1.0, float(stall_threshold_seconds))

        self._youtube = youtube if youtube is not None else YoutubeExtractor()
        self._default_quality = normalize_quality(default_quality)
        self._limiter = BandwidthLimiter(limit_bps=speed_limit_bps, clock=clock)
        self._global_speed = SpeedEstimator(
            window_seconds=3.0,
            stall_threshold_seconds=self._stall_threshold_seconds,
            clock=clock,
        )

        self._tasks: dict[str, _ManagedTask] = {}
        self._task_order: list[str] = []
        self._running_ids: set[str] = set()
        self._seq_counter = 0
        self._peak_concurrent = 0
        self._stopping = False

        self._scheduler = threading.Thread(
            target=self._scheduler_loop,
            name="overload-download-scheduler",
            daemon=True,
        )
        self._scheduler.start()

    # ------------------------------------------------------------------
    # Cycle de vie et configuration dynamique
    # ------------------------------------------------------------------

    @property
    def peak_concurrent(self) -> int:
        with self._lock:
            return self._peak_concurrent

    @property
    def history(self) -> DownloadHistoryStore | None:
        return self._history

    @property
    def youtube_available(self) -> bool:
        """Vrai si l'extracteur yt-dlp est présent dans cette installation."""
        return self._youtube.available()

    def settings(self) -> ManagerSettings:
        with self._lock:
            return ManagerSettings(
                destination_dir=self._destination_dir,
                max_concurrent=self._max_concurrent,
                speed_limit_bps=self._limiter.limit_bps,
                auto_retry=self._auto_retry,
                max_retries=self._max_retries,
                retry_initial_delay=self._retry_initial_delay,
                duplicate_policy=self._duplicate_policy,
            )

    def set_max_concurrent(self, value: int) -> ManagerSettings:
        if not isinstance(value, int) or isinstance(value, bool) or not (
            MIN_CONCURRENT <= value <= MAX_CONCURRENT
        ):
            raise OverloadError(
                "Limite de téléchargements simultanés invalide.",
                f"la valeur doit être un entier entre {MIN_CONCURRENT} et {MAX_CONCURRENT}.",
                "Ajustez le nombre de téléchargements simultanés.",
            )
        with self._cond:
            self._max_concurrent = value
            self._cond.notify_all()
            return self.settings()

    def set_speed_limit_bps(self, limit_bps: int | None) -> ManagerSettings:
        if limit_bps is not None and limit_bps < 0:
            raise OverloadError(
                "Limite de vitesse invalide.",
                "la vitesse maximale ne peut pas être négative.",
                "Saisissez une valeur positive ou 0 pour illimitée.",
            )
        self._limiter.set_limit_bps(limit_bps)
        return self.settings()

    def set_auto_retry(
        self,
        enabled: bool,
        *,
        max_retries: int | None = None,
        retry_initial_delay: float | None = None,
    ) -> ManagerSettings:
        with self._cond:
            self._auto_retry = bool(enabled)
            if max_retries is not None:
                if max_retries < 0 or max_retries > 20:
                    raise OverloadError(
                        "Nombre maximal de tentatives invalide.",
                        "choisissez une valeur entre 0 et 20.",
                    )
                self._max_retries = int(max_retries)
            if retry_initial_delay is not None:
                self._retry_initial_delay = max(0.05, float(retry_initial_delay))
            self._cond.notify_all()
            return self.settings()

    def set_duplicate_policy(self, policy: DuplicatePolicy | str) -> ManagerSettings:
        try:
            parsed = DuplicatePolicy(policy)
        except ValueError as exc:
            raise OverloadError(
                "Politique de gestion des doublons inconnue.",
                f"valeur « {policy} » non reconnue.",
            ) from exc
        with self._lock:
            self._duplicate_policy = parsed
            return self.settings()

    def set_destination_dir(self, directory: Path | str) -> ManagerSettings:
        path = Path(directory).expanduser()
        try:
            path.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise OverloadError(
                "Impossible d'utiliser ce dossier de destination.",
                str(exc),
                "Choisissez un dossier accessible en écriture.",
            ) from exc
        with self._lock:
            self._destination_dir = path
            return self.settings()

    def shutdown(self, *, timeout: float = 5.0) -> None:
        with self._cond:
            if self._stopping:
                return
            self._stopping = True
            for task in self._tasks.values():
                if task.state in {TaskState.RUNNING, TaskState.QUEUED}:
                    task.pause_event.set()
            self._limiter.wake_all()
            self._cond.notify_all()
        self._scheduler.join(timeout=timeout)
        if self._owns_history and self._history is not None:
            self._history.close()

    def __enter__(self) -> DownloadManager:
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.shutdown()

    # ------------------------------------------------------------------
    # Inspection préalable & ajout unitaire / par lots
    # ------------------------------------------------------------------

    def _allow_private_for(self, url: str) -> bool:
        if self._allow_private_hosts:
            return True
        if not self._allowed_local_endpoints:
            return False
        try:
            parts = urlsplit(url.strip())
        except ValueError:
            return False
        return (parts.hostname or "", parts.port or -1) in self._allowed_local_endpoints

    # ------------------------------------------------------------------
    # Résolution de la source : fichier direct ou vidéo YouTube
    # ------------------------------------------------------------------
    @staticmethod
    def _display_filename(clean_url: str) -> str:
        """Nom provisoire affiché pendant la validation (sans aucun appel réseau)."""
        if is_youtube_url(clean_url):
            video_id = youtube_video_id(clean_url) or "video"
            return f"YouTube {video_id}.mp4"
        return filename_from_url(clean_url)

    def _prepare_source(
        self,
        url: str,
        *,
        filename: str | None = None,
        quality: str | None = None,
    ) -> tuple[str, str | None, str, str, str, str]:
        """Valide l'adresse et résout son type.

        Retourne `(url_nettoyée, nom_de_fichier, fournisseur, qualité, titre, miniature)`.
        Une adresse YouTube déclenche une seule requête de métadonnées (mise en
        cache par identifiant de vidéo), afin de nommer le fichier avec le titre
        réel de la vidéo et de mémoriser la qualité choisie.
        """
        clean_url = validate_direct_url(
            url, allow_private_hosts=self._allow_private_for(url)
        )
        if not is_youtube_url(clean_url):
            return (clean_url, filename, "http", "best", "", "")

        chosen_quality = (
            self._default_quality if quality is None else normalize_quality(quality)
        )
        info = self._youtube.probe(clean_url)
        title = info.safe_title
        if filename:
            base_name = sanitize_filename(filename)
        else:
            base_name = f"{sanitize_filename(title, strip_path=False)}.mp4"
        if Path(base_name).suffix.lower() != ".mp4":
            base_name = f"{Path(base_name).stem}.mp4"
        return (clean_url, base_name, "youtube", chosen_quality, title, info.thumbnail_url)

    def inspect_media(self, url: str) -> dict[str, Any]:
        """Renseigne l'interface sur une page YouTube (titre, miniature, qualités)."""
        clean_url = validate_direct_url(
            url, allow_private_hosts=self._allow_private_for(url)
        )
        if not is_youtube_url(clean_url):
            raise OverloadError(
                "Cette adresse n'est pas une page YouTube.",
                "seules les vidéos YouTube et les fichiers HTTP(S) directs sont pris en charge.",
                "Collez un lien youtube.com/watch?v=…, youtu.be/… ou une adresse de fichier.",
            )
        info = self._youtube.probe(clean_url)
        payload = info.to_dict(quality=self._default_quality)
        payload["suggested_filename"] = (
            f"{sanitize_filename(info.safe_title, strip_path=False)}.mp4"
        )
        payload["extractor_available"] = self._youtube.available()
        return payload

    def check_duplicate(
        self,
        url: str,
        *,
        filename: str | None = None,
        destination_dir: Path | None = None,
    ) -> DuplicateMatch | None:
        clean_url = validate_direct_url(
            url, allow_private_hosts=self._allow_private_for(url)
        )
        with self._lock:
            dest = Path(destination_dir) if destination_dir is not None else self._destination_dir
            active_items = self._active_items_locked()
        return detect_duplicate(
            clean_url,
            dest,
            filename=filename,
            active_items=active_items,
            history=self._history,
        )

    def inspect_batch(
        self,
        source: str | Iterable[str],
        *,
        destination_dir: Path | None = None,
    ) -> dict[str, Any]:
        """Analyse une liste de liens avant téléchargement (valides, doublons, erreurs)."""
        parsed = parse_url_list(source)
        with self._lock:
            dest = Path(destination_dir) if destination_dir is not None else self._destination_dir
            active_items = list(self._active_items_locked())

        valid: list[dict[str, Any]] = []
        duplicates: list[dict[str, Any]] = []
        rejected: list[dict[str, Any]] = []
        seen_urls: set[str] = set()

        for line_no, raw_url in parsed:
            try:
                clean_url = validate_direct_url(
                    raw_url, allow_private_hosts=self._allow_private_for(raw_url)
                )
            except OverloadError as exc:
                rejected.append(RejectedLink(line=line_no, url=raw_url, error=str(exc)).to_dict())
                continue

            if clean_url in seen_urls:
                name = self._display_filename(clean_url)
                duplicates.append(
                    DuplicateMatch(
                        url=clean_url,
                        filename=name,
                        source=DuplicateSource.ACTIVE_TASK,
                        existing_path=dest / name,
                        existing_size=0,
                        reason="Adresse présente plusieurs fois dans la liste fournie.",
                    ).to_dict()
                )
                continue
            seen_urls.add(clean_url)

            dup = detect_duplicate(
                clean_url,
                dest,
                active_items=active_items,
                history=self._history,
            )
            if dup is not None:
                duplicates.append(dup.to_dict())
            else:
                valid.append(
                    {
                        "line": line_no,
                        "url": clean_url,
                        "filename": self._display_filename(clean_url),
                        "provider": "youtube" if is_youtube_url(clean_url) else "http",
                    }
                )

        return {
            "total_lines": len(parsed),
            "valid": valid,
            "duplicates": duplicates,
            "rejected": rejected,
        }

    def enqueue(
        self,
        url: str,
        *,
        filename: str | None = None,
        destination_dir: Path | None = None,
        duplicate_policy: DuplicatePolicy | str | None = None,
        start_paused: bool = False,
        quality: str | None = None,
    ) -> TaskSnapshot | None:
        """Ajoute un téléchargement unique en file d'attente.

        Retourne `None` uniquement si un doublon est détecté et que la politique
        effective est `DuplicatePolicy.SKIP`. Lève `DuplicateDetectedError` si la
        politique est `DuplicatePolicy.ASK` et qu'un doublon complet existe déjà.
        """
        clean_url, resolved_name, provider, task_quality, title, thumbnail = (
            self._prepare_source(url, filename=filename, quality=quality)
        )
        with self._cond:
            dest = Path(destination_dir) if destination_dir is not None else self._destination_dir
            if not dest.is_dir():
                raise OverloadError(
                    "Le dossier de destination est introuvable.",
                    "il a été supprimé ou n'est pas accessible.",
                    "Choisissez un autre dossier dans les paramètres.",
                )
            policy = (
                DuplicatePolicy(duplicate_policy)
                if duplicate_policy is not None
                else self._duplicate_policy
            )
            dup = detect_duplicate(
                clean_url,
                dest,
                filename=resolved_name,
                active_items=self._active_items_locked(),
                history=self._history,
            )
            target_path, resumed_from_part = self._resolve_target_locked(
                clean_url=clean_url,
                dest=dest,
                filename=resolved_name,
                dup=dup,
                policy=policy,
            )
            if target_path is None:
                return None

            task = self._create_task_locked(
                url=clean_url,
                target_path=target_path,
                resumed_from_part=resumed_from_part,
                start_paused=start_paused,
                provider=provider,
                quality=task_quality,
                media_title=title,
                thumbnail_url=thumbnail,
            )
            self._cond.notify_all()
            return self._snapshot_locked(task)

    def enqueue_batch(
        self,
        source: str | Iterable[str],
        *,
        destination_dir: Path | None = None,
        duplicate_policy: DuplicatePolicy | str | None = None,
        start_paused: bool = False,
        quality: str | None = None,
    ) -> BatchResult:
        """Ajoute une liste de liens en lot sans qu'une erreur individuelle bloque le reste."""
        entries = parse_url_list(source)
        if not entries:
            raise OverloadError(
                "Aucun lien détecté dans la liste.",
                "la zone de saisie ne contient aucune adresse exploitable.",
                "Collez une ou plusieurs adresses http:// ou https:// (une par ligne).",
            )

        added: list[TaskSnapshot] = []
        skipped: list[DuplicateMatch] = []
        conflicts: list[DuplicateMatch] = []
        rejected: list[RejectedLink] = []

        for line_no, raw_url in entries:
            try:
                (
                    clean_url,
                    resolved_name,
                    provider,
                    task_quality,
                    title,
                    thumbnail,
                ) = self._prepare_source(raw_url, quality=quality)
            except OverloadError as exc:
                rejected.append(RejectedLink(line=line_no, url=raw_url, error=str(exc)))
                continue

            try:
                with self._cond:
                    dest = (
                        Path(destination_dir)
                        if destination_dir is not None
                        else self._destination_dir
                    )
                    policy = (
                        DuplicatePolicy(duplicate_policy)
                        if duplicate_policy is not None
                        else self._duplicate_policy
                    )
                    dup = detect_duplicate(
                        clean_url,
                        dest,
                        filename=resolved_name,
                        active_items=self._active_items_locked(),
                        history=self._history,
                    )
                    target_path, resumed_from_part = self._resolve_target_locked(
                        clean_url=clean_url,
                        dest=dest,
                        filename=resolved_name,
                        dup=dup,
                        policy=policy,
                    )
                    if target_path is None:
                        if dup is not None:
                            skipped.append(dup)
                        continue
                    task = self._create_task_locked(
                        url=clean_url,
                        target_path=target_path,
                        resumed_from_part=resumed_from_part,
                        start_paused=start_paused,
                        provider=provider,
                        quality=task_quality,
                        media_title=title,
                        thumbnail_url=thumbnail,
                    )
                    self._cond.notify_all()
                    added.append(self._snapshot_locked(task))
            except DuplicateDetectedError as dup_exc:
                conflicts.append(dup_exc.match)
            except OverloadError as exc:
                rejected.append(RejectedLink(line=line_no, url=raw_url, error=str(exc)))

        return BatchResult(
            added=added,
            skipped_duplicates=skipped,
            conflicts=conflicts,
            rejected=rejected,
        )

    # ------------------------------------------------------------------
    # Contrôle individuel et global des tâches
    # ------------------------------------------------------------------

    def pause_task(self, task_id: str) -> TaskSnapshot:
        with self._cond:
            task = self._get_task_locked(task_id)
            if task.state is TaskState.PAUSED:
                return self._snapshot_locked(task)
            if task.state is TaskState.QUEUED:
                task.state = transition(task.state, TaskState.PAUSED)
                task.next_retry_mono = None
                task.pause_event.set()
                task.speed.reset()
                self._cond.notify_all()
                return self._snapshot_locked(task)
            if task.state is TaskState.RUNNING:
                task.pause_event.set()
                self._limiter.wake_all()
                self._cond.notify_all()
                return self._snapshot_locked(task)
            raise OverloadError(
                "Impossible de mettre ce téléchargement en pause.",
                f"le téléchargement est actuellement dans l'état « {task.state.value} ».",
            )

    def resume_task(self, task_id: str) -> TaskSnapshot:
        with self._cond:
            task = self._get_task_locked(task_id)
            if task.state in {TaskState.RUNNING, TaskState.QUEUED}:
                return self._snapshot_locked(task)
            if task.state is TaskState.PAUSED:
                task.state = transition(task.state, TaskState.QUEUED)
            elif task.state in {TaskState.FAILED, TaskState.CANCELLED}:
                task.state = transition(task.state, TaskState.QUEUED)
            else:
                raise OverloadError(
                    "Impossible de reprendre ce téléchargement.",
                    f"le téléchargement est déjà « {task.state.value} ».",
                )
            part = self._part_path(task.target_path)
            task.downloaded_bytes = part.stat().st_size if part.exists() else 0
            task.resumed_from_part = task.downloaded_bytes > 0
            task.pause_event.clear()
            task.cancel_event.clear()
            task.retry_count = 0
            task.next_retry_mono = None
            task.error_message = ""
            task.finished_at = None
            task.max_retries = self._max_retries
            self._seq_counter += 1
            task.queue_seq = self._seq_counter
            self._cond.notify_all()
            return self._snapshot_locked(task)

    def retry_task(self, task_id: str) -> TaskSnapshot:
        """Alias explicite pour relancer une tâche en échec ou annulée."""
        return self.resume_task(task_id)

    def cancel_task(self, task_id: str) -> TaskSnapshot:
        record_snapshot: _ManagedTask | None = None
        with self._cond:
            task = self._get_task_locked(task_id)
            if task.state is TaskState.CANCELLED:
                return self._snapshot_locked(task)
            if task.state is TaskState.COMPLETED:
                raise OverloadError(
                    "Ce téléchargement est déjà terminé.",
                    "utilisez « Ouvrir le dossier » pour accéder au fichier.",
                )
            if task.state in {TaskState.QUEUED, TaskState.PAUSED}:
                task.state = transition(task.state, TaskState.CANCELLED)
                task.cancel_event.set()
                task.next_retry_mono = None
                task.speed.reset()
                task.finished_at = datetime.now(UTC).isoformat()
                self._discard_partials(task)
                record_snapshot = task
                self._cond.notify_all()
            elif task.state is TaskState.RUNNING:
                task.cancel_event.set()
                self._limiter.wake_all()
                self._cond.notify_all()
            snap = self._snapshot_locked(task)

        if record_snapshot is not None:
            self._record_history(record_snapshot)
        return snap

    def pause_all(self) -> list[TaskSnapshot]:
        with self._cond:
            paused: list[TaskSnapshot] = []
            for task_id in self._task_order:
                task = self._tasks[task_id]
                if task.state is TaskState.QUEUED:
                    task.state = transition(task.state, TaskState.PAUSED)
                    task.next_retry_mono = None
                    task.pause_event.set()
                    task.speed.reset()
                    paused.append(self._snapshot_locked(task))
                elif task.state is TaskState.RUNNING:
                    task.pause_event.set()
                    paused.append(self._snapshot_locked(task))
            self._limiter.wake_all()
            self._cond.notify_all()
            return paused

    def resume_all(self) -> list[TaskSnapshot]:
        with self._cond:
            resumed: list[TaskSnapshot] = []
            for task_id in self._task_order:
                task = self._tasks[task_id]
                if task.state in {TaskState.PAUSED, TaskState.FAILED}:
                    task.state = transition(task.state, TaskState.QUEUED)
                    part = self._part_path(task.target_path)
                    task.downloaded_bytes = part.stat().st_size if part.exists() else 0
                    task.resumed_from_part = task.downloaded_bytes > 0
                    task.pause_event.clear()
                    task.cancel_event.clear()
                    task.retry_count = 0
                    task.next_retry_mono = None
                    task.error_message = ""
                    task.finished_at = None
                    task.max_retries = self._max_retries
                    self._seq_counter += 1
                    task.queue_seq = self._seq_counter
                    resumed.append(self._snapshot_locked(task))
            self._cond.notify_all()
            return resumed

    def remove_task(self, task_id: str) -> None:
        """Retire une tâche terminée/annulée de la liste active sans supprimer le fichier."""
        with self._cond:
            task = self._get_task_locked(task_id)
            if task.state in {TaskState.RUNNING, TaskState.QUEUED, TaskState.FINALIZING}:
                raise OverloadError(
                    "Impossible de retirer un téléchargement actif.",
                    "mettez-le d'abord en pause ou annulez-le.",
                )
            del self._tasks[task_id]
            self._task_order = [tid for tid in self._task_order if tid != task_id]

    def clear_finished(self) -> int:
        """Nettoie les tâches terminées/annulées de la vue courante sans toucher aux fichiers."""
        with self._cond:
            removable = [
                tid
                for tid in self._task_order
                if self._tasks[tid].state in {TaskState.COMPLETED, TaskState.CANCELLED}
            ]
            for tid in removable:
                del self._tasks[tid]
            self._task_order = [tid for tid in self._task_order if tid not in set(removable)]
            return len(removable)

    # ------------------------------------------------------------------
    # Lecture d'état, vitesse globale, diagnostic & ouverture de dossier
    # ------------------------------------------------------------------

    def get_task(self, task_id: str) -> TaskSnapshot:
        with self._lock:
            return self._snapshot_locked(self._get_task_locked(task_id))

    def list_tasks(self) -> list[TaskSnapshot]:
        with self._lock:
            return [self._snapshot_locked(self._tasks[tid]) for tid in self._task_order]

    def status_overview(self) -> dict[str, Any]:
        """Vue synthétique temps réel : vitesse globale, compteurs et santé réseau."""
        with self._lock:
            snapshots = [self._snapshot_locked(self._tasks[tid]) for tid in self._task_order]
            global_bps, _, _ = self._global_speed.snapshot(remaining_bytes=None)
            config = self.settings()

        counts = {state.value: 0 for state in TaskState}
        retrying_count = 0
        stalled_count = 0
        recent_issues: list[dict[str, Any]] = []
        for snap in snapshots:
            counts[snap.state.value] += 1
            if snap.retrying:
                retrying_count += 1
            if snap.stalled:
                stalled_count += 1
            for issue in snap.issues[-2:]:
                item = issue.to_dict()
                item["filename"] = snap.filename
                item["task_id"] = snap.id
                recent_issues.append(item)

        recent_issues.sort(key=lambda item: item["timestamp"], reverse=True)
        active_sum_bps = sum(s.speed_bps for s in snapshots if s.state is TaskState.RUNNING)
        effective_bps = active_sum_bps if counts[TaskState.RUNNING.value] > 0 else 0.0
        if global_bps > 0 and effective_bps > 0:
            effective_bps = max(effective_bps, global_bps)

        if stalled_count > 0 or retrying_count > 0:
            network_health = "degraded"
            network_message = (
                f"{retrying_count + stalled_count} téléchargement(s) rencontrent "
                "des perturbations réseau (reprise automatique active)."
            )
        elif counts[TaskState.FAILED.value] > 0:
            network_health = "warning"
            network_message = (
                f"{counts[TaskState.FAILED.value]} téléchargement(s) en échec — "
                "vérifiez les détails ou relancez."
            )
        else:
            network_health = "healthy"
            network_message = "Connexion stable"

        return {
            "settings": config.to_dict(),
            "total_speed_bps": round(effective_bps, 2),
            "total_speed_human": format_speed(effective_bps),
            "counts": counts,
            "retrying_count": retrying_count,
            "stalled_count": stalled_count,
            "network_health": network_health,
            "network_message": network_message,
            "recent_issues": recent_issues[:8],
            "tasks": [s.to_dict() for s in snapshots],
        }

    def wait_all(self, *, timeout: float = 30.0) -> bool:
        """Attend la fin de toutes les tâches actives et en attente (CLI et tests)."""
        deadline = time.monotonic() + timeout
        with self._cond:
            while True:
                busy = any(
                    t.state in {TaskState.QUEUED, TaskState.RUNNING, TaskState.FINALIZING}
                    for t in self._tasks.values()
                )
                if not busy:
                    return True
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return False
                self._cond.wait(timeout=min(0.2, remaining))

    def open_task_folder(self, task_id: str, *, opener=None) -> Path:  # noqa: ANN001
        snap = self.get_task(task_id)
        return open_folder(snap.target_path, opener=opener)

    def open_history_folder(self, entry_id: str, *, opener=None) -> Path:  # noqa: ANN001
        if self._history is None:
            raise OverloadError("Aucun historique n'est configuré.")
        entry: HistoryEntry = self._history.get_entry(entry_id)
        return open_folder(entry.destination_path, opener=opener)

    def open_downloads_folder(self, *, opener=None) -> Path:  # noqa: ANN001
        with self._lock:
            dest = self._destination_dir
        return open_folder(dest, opener=opener)

    # ------------------------------------------------------------------
    # Planification interne & exécution d'un téléchargement
    # ------------------------------------------------------------------

    @staticmethod
    def _part_path(target: Path) -> Path:
        return target.with_name(target.name + PART_SUFFIX)

    def _discard_partials(self, task: _ManagedTask) -> None:
        """Supprime le `.part` HTTP et les fragments yt-dlp d'une tâche annulée."""
        self._part_path(task.target_path).unlink(missing_ok=True)
        if task.provider != "youtube":
            return
        stem = task.target_path.with_suffix("")
        if not stem.parent.is_dir():
            return
        prefix = stem.name + "."
        for candidate in stem.parent.iterdir():
            if (
                candidate.is_file()
                and candidate.name.startswith(prefix)
                and candidate != task.target_path
            ):
                try:
                    candidate.unlink()
                except OSError:
                    continue

    def _active_items_locked(self) -> list[tuple[str, str, Path]]:
        return [
            (t.id, t.url, t.target_path)
            for t in self._tasks.values()
            if t.state in {
                TaskState.QUEUED,
                TaskState.RUNNING,
                TaskState.PAUSED,
                TaskState.FINALIZING,
            }
        ]

    def _resolve_target_locked(
        self,
        *,
        clean_url: str,
        dest: Path,
        filename: str | None,
        dup: DuplicateMatch | None,
        policy: DuplicatePolicy,
    ) -> tuple[Path | None, bool]:
        base_name = sanitize_filename(filename) if filename else filename_from_url(clean_url)
        reserved = {
            t.target_path for t in self._tasks.values() if t.state is not TaskState.CANCELLED
        }

        if dup is not None:
            if dup.source is DuplicateSource.PARTIAL_FILE and dup.resumable:
                candidate = dest / base_name
                if candidate not in reserved and not candidate.exists():
                    return (candidate, True)
            elif policy is DuplicatePolicy.SKIP:
                return (None, False)
            elif policy is DuplicatePolicy.ASK:
                raise DuplicateDetectedError(dup)
            # En mode RENAME ou RESUME sur doublon complet : plan_destination crée « (2) »

        part_candidate = dest / (base_name + PART_SUFFIX)
        direct_candidate = dest / base_name
        if (
            part_candidate.is_file()
            and not direct_candidate.exists()
            and direct_candidate not in reserved
        ):
            return (direct_candidate, True)

        chosen = plan_destination(dest, base_name)
        counter = 2
        stem, dot, ext = sanitize_filename(base_name).rpartition(".")
        if not dot:
            stem, ext = sanitize_filename(base_name), ""
        suffix = f".{ext}" if ext else ""
        while chosen in reserved:
            chosen = dest / f"{stem} ({counter}){suffix}"
            counter += 1
        return (chosen, False)

    def _create_task_locked(
        self,
        *,
        url: str,
        target_path: Path,
        resumed_from_part: bool,
        start_paused: bool,
        provider: str = "http",
        quality: str = "best",
        media_title: str = "",
        thumbnail_url: str = "",
    ) -> _ManagedTask:
        self._seq_counter += 1
        part = self._part_path(target_path)
        initial_bytes = part.stat().st_size if part.exists() else 0
        task = _ManagedTask(
            id=uuid.uuid4().hex[:10],
            url=url,
            filename=target_path.name,
            target_path=target_path,
            state=TaskState.PAUSED if start_paused else TaskState.QUEUED,
            queue_seq=self._seq_counter,
            max_retries=self._max_retries,
            speed=SpeedEstimator(
                window_seconds=3.0,
                stall_threshold_seconds=self._stall_threshold_seconds,
                clock=self._clock,
            ),
            downloaded_bytes=initial_bytes,
            resumed_from_part=resumed_from_part or initial_bytes > 0,
            provider=provider,
            quality=quality,
            media_title=media_title,
            thumbnail_url=thumbnail_url,
        )
        if start_paused:
            task.pause_event.set()
        self._tasks[task.id] = task
        self._task_order.append(task.id)
        return task

    def _get_task_locked(self, task_id: str) -> _ManagedTask:
        task = self._tasks.get(task_id)
        if task is None:
            raise OverloadError(
                "Téléchargement introuvable.",
                f"l'identifiant « {task_id} » n'existe pas dans la liste active.",
            )
        return task

    def _scheduler_loop(self) -> None:
        while True:
            with self._cond:
                if self._stopping:
                    return

                now = self._clock()
                ready: list[_ManagedTask] = []
                next_wake: float | None = None

                for tid in self._task_order:
                    task = self._tasks[tid]
                    if task.state is not TaskState.QUEUED or task.id in self._running_ids:
                        continue
                    if task.next_retry_mono is not None and task.next_retry_mono > now:
                        wait = task.next_retry_mono - now
                        next_wake = wait if next_wake is None else min(next_wake, wait)
                        continue
                    ready.append(task)

                ready.sort(key=lambda t: t.queue_seq)

                while ready and len(self._running_ids) < self._max_concurrent:
                    task = ready.pop(0)
                    task.state = transition(task.state, TaskState.RUNNING)
                    task.pause_event.clear()
                    task.next_retry_mono = None
                    task.stall_reported = False
                    if task.started_at is None:
                        task.started_at = datetime.now(UTC).isoformat()
                        task.started_mono = now
                    task.bytes_at_run_start = task.downloaded_bytes
                    task.speed.start()
                    self._running_ids.add(task.id)
                    if len(self._running_ids) > self._peak_concurrent:
                        self._peak_concurrent = len(self._running_ids)
                    worker = threading.Thread(
                        target=self._run_worker,
                        args=(task,),
                        name=f"overload-dl-{task.id}",
                        daemon=True,
                    )
                    worker.start()

                sleep_for = min(0.25, max(0.01, next_wake)) if next_wake is not None else 0.5
                self._cond.wait(timeout=sleep_for)

    def _run_worker(self, task: _ManagedTask) -> None:
        last_seen = task.downloaded_bytes

        def on_progress(done: int, total: int | None) -> None:
            nonlocal last_seen
            delta = max(0, done - last_seen)
            last_seen = done
            with self._lock:
                task.downloaded_bytes = done
                if total is not None:
                    task.total_bytes = total
                if delta > 0:
                    task.stall_reported = False
            if delta > 0:
                task.speed.record_bytes(delta)
                self._global_speed.record_bytes(delta)

        def on_issue(issue: ConnectionIssue) -> None:
            with self._lock:
                task.issues.append(issue)

        record_after: _ManagedTask | None = None
        try:
            if task.provider == "youtube":
                # yt-dlp gère lui-même la limite via `ratelimit`, sans double
                # comptage dans le seau à jetons partagé.
                self._youtube.download(
                    task.url,
                    task.target_path,
                    quality=task.quality,
                    progress=on_progress,
                    cancel_event=task.cancel_event,
                    pause_event=task.pause_event,
                    max_rate_bps=self._limiter.limit_bps,
                    timeout=self._timeout,
                )
            else:
                download_to(
                    task.url,
                    task.target_path,
                    allow_private_hosts=self._allow_private_for(task.url),
                    progress=on_progress,
                    cancel_event=task.cancel_event,
                    pause_event=task.pause_event,
                    bandwidth_limiter=self._limiter,
                    on_issue=on_issue,
                    timeout=self._timeout,
                )
            with self._cond:
                task.state = transition(task.state, TaskState.FINALIZING)
                final_size = (
                    task.target_path.stat().st_size
                    if task.target_path.exists()
                    else task.downloaded_bytes
                )
                task.downloaded_bytes = final_size
                task.total_bytes = final_size
                task.error_message = ""
                task.speed.reset()
                task.finished_at = datetime.now(UTC).isoformat()
                task.state = transition(task.state, TaskState.COMPLETED)
                record_after = task
        except DownloadPaused:
            with self._cond:
                part = self._part_path(task.target_path)
                if part.exists():
                    task.downloaded_bytes = part.stat().st_size
                task.speed.reset()
                if task.state is TaskState.RUNNING:
                    task.state = transition(task.state, TaskState.PAUSED)
        except DownloadCancelled:
            with self._cond:
                self._part_path(task.target_path).unlink(missing_ok=True)
                task.speed.reset()
                task.finished_at = datetime.now(UTC).isoformat()
                if task.state is TaskState.RUNNING:
                    task.state = transition(task.state, TaskState.CANCELLED)
                record_after = task
        except Exception as exc:  # noqa: BLE001
            with self._cond:
                part = self._part_path(task.target_path)
                if part.exists():
                    task.downloaded_bytes = part.stat().st_size
                    task.resumed_from_part = task.downloaded_bytes > 0
                task.speed.reset()

                attempt_num = task.retry_count + 1
                recoverable, issue = classify_error(
                    exc,
                    offset_bytes=task.downloaded_bytes,
                    attempt=attempt_num,
                )
                if issue is not None:
                    task.issues.append(issue)

                can_auto_retry = (
                    self._auto_retry
                    and recoverable
                    and task.retry_count < task.max_retries
                    and not self._stopping
                    and not task.cancel_event.is_set()
                    and not task.pause_event.is_set()
                )
                if can_auto_retry:
                    task.retry_count += 1
                    delay = min(
                        MAX_BACKOFF_SECONDS,
                        self._retry_initial_delay * (2 ** (task.retry_count - 1)),
                    )
                    task.next_retry_mono = self._clock() + delay
                    task.error_message = str(exc)
                    task.state = transition(task.state, TaskState.QUEUED)
                else:
                    task.error_message = str(exc)
                    task.finished_at = datetime.now(UTC).isoformat()
                    task.state = transition(task.state, TaskState.FAILED)
                    record_after = task
        finally:
            with self._cond:
                self._running_ids.discard(task.id)
                self._cond.notify_all()

        if record_after is not None:
            self._record_history(record_after)

    def _record_history(self, task: _ManagedTask) -> None:
        if self._history is None:
            return
        now_mono = self._clock()
        duration = (
            max(0.001, now_mono - task.started_mono)
            if task.started_mono is not None
            else 0.0
        )
        avg_speed = task.downloaded_bytes / duration if duration > 0 else 0.0
        self._history.record(
            task_id=task.id,
            url=task.url,
            filename=task.filename,
            destination_path=task.target_path,
            status=task.state.value,
            size_bytes=task.downloaded_bytes,
            average_speed_bps=avg_speed,
            duration_seconds=duration,
            retries_used=task.retry_count,
            issues_count=len(task.issues),
            error_message=task.error_message,
            started_at=task.started_at,
            finished_at=task.finished_at,
        )

    def _snapshot_locked(self, task: _ManagedTask) -> TaskSnapshot:
        now = self._clock()
        remaining = (
            max(0, task.total_bytes - task.downloaded_bytes)
            if task.total_bytes is not None
            else None
        )
        if task.state is TaskState.RUNNING:
            speed_bps, eta_seconds, _ = task.speed.snapshot(remaining_bytes=remaining)
            stalled, stall_secs = task.speed.is_stalled()
            if stalled and not task.stall_reported:
                task.stall_reported = True
                task.issues.append(
                    ConnectionIssue(
                        kind=IssueKind.STALLED,
                        message=(
                            f"Flux figé : aucune donnée reçue depuis {int(stall_secs)} s "
                            "(vérification de la connexion…)."
                        ),
                        offset_bytes=task.downloaded_bytes,
                        recoverable=True,
                    )
                )
        else:
            speed_bps = 0.0
            eta_seconds = 0.0 if task.state is TaskState.COMPLETED else None
            stalled, stall_secs = False, 0.0

        retrying = (
            task.state is TaskState.QUEUED
            and task.retry_count > 0
            and task.next_retry_mono is not None
        )
        retry_in = (
            max(0.0, task.next_retry_mono - now)
            if retrying and task.next_retry_mono is not None
            else None
        )

        progress_pct: float | None = None
        if task.state is TaskState.COMPLETED:
            progress_pct = 100.0
        elif task.total_bytes and task.total_bytes > 0:
            progress_pct = min(100.0, (task.downloaded_bytes / task.total_bytes) * 100.0)

        active_warning = ""
        if retrying:
            wait_txt = f" dans {retry_in:.1f} s" if retry_in is not None else ""
            active_warning = (
                f"Connexion interrompue — reprise automatique "
                f"(tentative {task.retry_count}/{task.max_retries}){wait_txt}."
            )
        elif stalled:
            active_warning = (
                f"Connexion lente ou figée (aucune donnée depuis {int(stall_secs)} s)."
            )
        elif task.issues and task.state in {TaskState.RUNNING, TaskState.FAILED}:
            active_warning = task.issues[-1].message

        return TaskSnapshot(
            id=task.id,
            url=task.url,
            filename=task.filename,
            target_path=task.target_path,
            state=task.state,
            downloaded_bytes=task.downloaded_bytes,
            total_bytes=task.total_bytes,
            progress_percent=progress_pct,
            speed_bps=speed_bps,
            eta_seconds=eta_seconds,
            retry_count=task.retry_count,
            max_retries=task.max_retries,
            retrying=retrying,
            retry_in_seconds=retry_in,
            resumed_from_part=task.resumed_from_part,
            stalled=stalled,
            stall_seconds=stall_secs,
            active_warning=active_warning,
            error_message=task.error_message,
            issues=tuple(task.issues),
            created_at=task.created_at,
            started_at=task.started_at,
            finished_at=task.finished_at,
            provider=task.provider,
            quality=task.quality,
            media_title=task.media_title,
            thumbnail_url=task.thumbnail_url,
        )
