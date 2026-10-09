"""Gestionnaire de téléchargements en arrière-plan.

Il ne dépend pas de l'interface : l'interface lit des instantanés (`TaskView`)
et envoie des commandes (ajouter, pause, reprise, annulation, relance).

Chaque téléchargement passe par `download_to`, donc par la validation d'URL,
la garde réseau (adresses locales refusées, adresse IP épinglée) et la
vérification du fichier avant « Terminé ».
"""

from __future__ import annotations

import logging
import threading
import time
import uuid
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit

from overload.core.errors import OverloadError
from overload.downloads.engine import DownloadCancelled, DownloadPaused, download_to
from overload.downloads.files import PART_SUFFIX, filename_from_url, plan_destination
from overload.downloads.state import TaskState, transition
from overload.downloads.urls import validate_direct_url

log = logging.getLogger(__name__)

MAX_PARALLEL = 4
_SPEED_WINDOW_SECONDS = 0.5


@dataclass(frozen=True)
class TaskView:
    """Instantané immuable d'une tâche, lisible depuis l'interface."""

    id: str
    url: str
    host: str
    name: str
    directory: Path
    state: TaskState
    target: Path | None
    received: int
    total: int | None
    speed: float
    error: str

    @property
    def progress(self) -> float | None:
        if not self.total:
            return None
        return min(1.0, self.received / self.total)

    @property
    def eta_seconds(self) -> float | None:
        if not self.total or self.speed <= 0:
            return None
        return max(0.0, (self.total - self.received) / self.speed)

    @property
    def result_path(self) -> Path | None:
        return self.target if self.state is TaskState.COMPLETED else None


class _Task:
    def __init__(self, url: str, directory: Path, name: str) -> None:
        self.id = uuid.uuid4().hex
        self.url = url
        self.directory = directory
        self.name = name
        self.state = TaskState.QUEUED
        self.target: Path | None = None
        self.received = 0
        self.total: int | None = None
        self.speed = 0.0
        self.error = ""
        self.cancel_event = threading.Event()
        self.pause_event = threading.Event()
        self.future: Future | None = None
        self._sample_time = time.monotonic()
        self._sample_bytes = 0

    def view(self) -> TaskView:
        return TaskView(
            id=self.id,
            url=self.url,
            host=urlsplit(self.url).hostname or "",
            name=self.name,
            directory=self.directory,
            state=self.state,
            target=self.target,
            received=self.received,
            total=self.total,
            speed=self.speed,
            error=self.error,
        )


class DownloadManager:
    def __init__(self, *, max_workers: int = 2, allow_private_hosts: bool = False) -> None:
        workers = min(MAX_PARALLEL, max(1, int(max_workers)))
        self._allow_private = allow_private_hosts
        self._pool = ThreadPoolExecutor(max_workers=workers, thread_name_prefix="overload-dl")
        self._lock = threading.RLock()
        self._tasks: dict[str, _Task] = {}

    # ----- commandes -------------------------------------------------------
    def submit(self, url: str, directory: Path) -> str:
        """Ajoute une tâche. Lève OverloadError si l'URL ou le dossier est refusé."""
        clean = validate_direct_url(url, allow_private_hosts=self._allow_private)
        directory = Path(directory)
        try:
            directory.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise OverloadError(
                "Le dossier de destination est inaccessible.",
                str(exc),
                "Choisissez un autre dossier dans les paramètres.",
            ) from exc
        task = _Task(clean, directory, filename_from_url(clean))
        with self._lock:
            self._tasks[task.id] = task
            self._start(task)
        log.info("Tâche ajoutée : %s", task.id)
        return task.id

    def pause(self, task_id: str) -> bool:
        """Demande la pause d'une tâche en cours. Le fichier partiel est conservé."""
        with self._lock:
            task = self._get(task_id)
            if task.state is not TaskState.RUNNING:
                return False
            task.pause_event.set()
            return True

    def resume(self, task_id: str) -> bool:
        with self._lock:
            task = self._get(task_id)
            if task.state is not TaskState.PAUSED:
                return False
            task.pause_event.clear()
            self._set_state(task, TaskState.QUEUED)
            self._start(task)
            return True

    def cancel(self, task_id: str) -> bool:
        """Annule une tâche. Le partiel est supprimé, l'original n'est jamais touché."""
        with self._lock:
            task = self._get(task_id)
            if task.state in (TaskState.COMPLETED, TaskState.FAILED, TaskState.CANCELLED):
                return False
            task.cancel_event.set()
            if task.state is TaskState.PAUSED:
                self._delete_partial(task)
                self._set_state(task, TaskState.CANCELLED)
            elif task.state is TaskState.QUEUED and task.future is not None:
                if task.future.cancel():
                    self._delete_partial(task)
                    self._set_state(task, TaskState.CANCELLED)
            return True

    def retry(self, task_id: str) -> bool:
        """Relance une tâche échouée ou annulée. Le partiel éventuel est repris."""
        with self._lock:
            task = self._get(task_id)
            if task.state not in (TaskState.FAILED, TaskState.CANCELLED):
                return False
            task.error = ""
            task.cancel_event = threading.Event()
            task.pause_event = threading.Event()
            self._set_state(task, TaskState.QUEUED)
            self._start(task)
            return True

    def shutdown(self) -> None:
        """Met en pause les tâches (fichiers partiels conservés) puis arrête le pool.

        Les tâches en cours s'arrêtent entre deux blocs de données, donc rapidement.
        """
        with self._lock:
            for task in self._tasks.values():
                if task.state is TaskState.RUNNING:
                    task.pause_event.set()
                elif task.state is TaskState.QUEUED and task.future and task.future.cancel():
                    self._set_state(task, TaskState.PAUSED)
        self._pool.shutdown(wait=True, cancel_futures=True)

    # ----- lecture ---------------------------------------------------------
    def snapshot(self) -> list[TaskView]:
        with self._lock:
            return [task.view() for task in self._tasks.values()]

    def get(self, task_id: str) -> TaskView:
        with self._lock:
            return self._get(task_id).view()

    def active_count(self) -> int:
        with self._lock:
            return sum(
                t.state in (TaskState.QUEUED, TaskState.RUNNING, TaskState.FINALIZING)
                for t in self._tasks.values()
            )

    # ----- interne ---------------------------------------------------------
    def _get(self, task_id: str) -> _Task:
        try:
            return self._tasks[task_id]
        except KeyError as exc:
            raise OverloadError(
                "Tâche introuvable.", "elle a déjà été retirée de la liste."
            ) from exc

    def _start(self, task: _Task) -> None:
        task.future = self._pool.submit(self._run, task)

    def _set_state(self, task: _Task, new: TaskState) -> None:
        if task.state is new:
            return
        task.state = transition(task.state, new)

    def _delete_partial(self, task: _Task) -> None:
        if task.target is not None:
            task.target.with_name(task.target.name + PART_SUFFIX).unlink(missing_ok=True)

    def _on_progress(self, task: _Task, done: int, total: int | None) -> None:
        with self._lock:
            now = time.monotonic()
            task.received = done
            task.total = total
            elapsed = now - task._sample_time
            if elapsed >= _SPEED_WINDOW_SECONDS:
                task.speed = (done - task._sample_bytes) / elapsed
                task._sample_time = now
                task._sample_bytes = done

    def _run(self, task: _Task) -> None:
        cancel_event, pause_event = task.cancel_event, task.pause_event
        with self._lock:
            if cancel_event.is_set():
                self._delete_partial(task)
                self._set_state(task, TaskState.CANCELLED)
                return
            self._set_state(task, TaskState.RUNNING)
            task._sample_time = time.monotonic()
            task._sample_bytes = task.received
            task.speed = 0.0
        try:
            with self._lock:
                if task.target is None or task.target.exists():
                    task.target = plan_destination(task.directory, task.name)
                target = task.target
            path = download_to(
                task.url,
                target,
                allow_private_hosts=self._allow_private,
                progress=lambda d, t: self._on_progress(task, d, t),
                cancel_event=cancel_event,
                pause_event=pause_event,
            )
        except DownloadCancelled:
            self._finish(task, TaskState.CANCELLED)
        except DownloadPaused:
            self._finish(task, TaskState.PAUSED)
        except OverloadError as exc:
            log.warning("Échec du téléchargement %s : %s", task.id, exc.what)
            self._finish(task, TaskState.FAILED, str(exc))
        except Exception:  # erreur inattendue : journalisée, message générique
            log.exception("Erreur inattendue pendant le téléchargement %s", task.id)
            self._finish(
                task,
                TaskState.FAILED,
                "Erreur inattendue pendant le téléchargement.\n"
                "Action : relancez le téléchargement. Si le problème persiste, "
                "joignez le journal technique à votre signalement.",
            )
        else:
            with self._lock:
                self._set_state(task, TaskState.FINALIZING)
                task.received = task.total = path.stat().st_size
                task.speed = 0.0
                self._set_state(task, TaskState.COMPLETED)
            log.info("Téléchargement terminé : %s", path.name)

    def _finish(self, task: _Task, new: TaskState, error: str = "") -> None:
        with self._lock:
            task.speed = 0.0
            task.error = error
            self._set_state(task, new)
