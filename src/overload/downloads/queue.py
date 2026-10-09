"""File de téléchargements persistante ; aucune dépendance à l'interface."""

from __future__ import annotations

import json
import os
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass
from pathlib import Path

from overload.core.errors import OverloadError
from overload.downloads.engine import DownloadCancelled, DownloadPaused, download_to
from overload.downloads.files import filename_from_url, plan_destination, sanitize_filename
from overload.downloads.state import TaskState, transition
from overload.downloads.urls import validate_direct_url


@dataclass
class Task:
    id: str
    url: str
    target: str
    state: TaskState
    received: int = 0
    total: int | None = None
    error: str = ""


class DownloadQueue:
    def __init__(self, state_file: Path, *, concurrency: int = 2) -> None:
        if concurrency < 1 or concurrency > 8:
            raise ValueError("concurrency doit être compris entre 1 et 8")
        self.state_file = Path(state_file)
        self._lock = threading.RLock()
        self._executor = ThreadPoolExecutor(max_workers=concurrency)
        self._concurrency = concurrency
        self._tasks: dict[str, Task] = {}
        self._signals: dict[str, tuple[threading.Event, threading.Event]] = {}
        self._closed = False
        if self.state_file.exists():
            try:
                saved = json.loads(self.state_file.read_text(encoding="utf-8"))
                if saved["version"] != 1:
                    raise ValueError("version incompatible")
                for data in saved["tasks"]:
                    task = Task(**data)
                    task.state = TaskState(task.state)
                    if task.state == TaskState.RUNNING:
                        task.state = TaskState.QUEUED
                    elif task.state == TaskState.FINALIZING:
                        task.state = TaskState.QUEUED
                    self._tasks[task.id] = task
            except (ValueError, KeyError, TypeError, OSError) as exc:
                self._executor.shutdown(wait=False)
                raise OverloadError(
                    "Historique des téléchargements illisible.", str(exc),
                    "Sauvegardez le fichier d'état avant toute réparation.",
                ) from exc
        with self._lock:
            self._schedule()

    def snapshot(self) -> list[Task]:
        with self._lock:
            return [Task(**asdict(task)) for task in self._tasks.values()]

    def add(self, url: str, folder: Path, name: str | None = None) -> Task:
        url = validate_direct_url(url)
        if not str(folder).strip():
            raise OverloadError("Choisissez un dossier de destination.")
        folder = Path(folder).expanduser().resolve()
        folder.mkdir(parents=True, exist_ok=True)
        with self._lock:
            self._ensure_open()
            candidate = plan_destination(
                folder, sanitize_filename(name) if name else filename_from_url(url)
            )
            reserved = {
                task.target for task in self._tasks.values() if task.state != TaskState.CANCELLED
            }
            base = candidate
            number = 2
            while str(candidate) in reserved:
                candidate = plan_destination(
                    folder, f"{base.stem} ({number}){base.suffix}"
                )
                number += 1
            task = Task(uuid.uuid4().hex, url, str(candidate), TaskState.QUEUED)
            self._tasks[task.id] = task
            self._save()
            self._schedule()
            return Task(**asdict(task))

    def pause(self, task_id: str) -> None:
        with self._lock:
            task = self._tasks[task_id]
            if task.state == TaskState.RUNNING:
                self._signals[task_id][0].set()
            elif task.state == TaskState.QUEUED:
                task.state = transition(task.state, TaskState.PAUSED)
                self._save()
            else:
                raise OverloadError("Cette tâche ne peut pas être mise en pause.")

    def resume(self, task_id: str) -> None:
        with self._lock:
            task = self._tasks[task_id]
            task.state = transition(task.state, TaskState.QUEUED)
            task.error = ""
            self._save()
            self._schedule()

    def cancel(self, task_id: str) -> None:
        with self._lock:
            task = self._tasks[task_id]
            if task.state == TaskState.RUNNING:
                self._signals[task_id][1].set()
            elif task.state in (TaskState.QUEUED, TaskState.PAUSED):
                task.state = transition(task.state, TaskState.CANCELLED)
                part = Path(task.target + ".part")
                part.unlink(missing_ok=True)
                Path(str(part) + ".json").unlink(missing_ok=True)
                self._save()
            else:
                raise OverloadError("Cette tâche ne peut pas être annulée.")

    def close(self) -> None:
        with self._lock:
            self._closed = True
            for pause, _ in self._signals.values():
                pause.set()
        self._executor.shutdown(wait=True)

    def _ensure_open(self) -> None:
        if self._closed:
            raise OverloadError("La file est fermée.")

    def _save(self) -> None:
        self.state_file.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.state_file.with_name(self.state_file.name + ".tmp")
        try:
            temporary.write_text(json.dumps({
                "version": 1, "tasks": [asdict(task) for task in self._tasks.values()],
            }, ensure_ascii=False, indent=2), encoding="utf-8")
            os.replace(temporary, self.state_file)
        finally:
            temporary.unlink(missing_ok=True)

    def _schedule(self) -> None:
        if self._closed:
            return
        for task in self._tasks.values():
            if len(self._signals) >= self._concurrency:
                break
            if task.state == TaskState.QUEUED:
                task.state = transition(task.state, TaskState.RUNNING)
                pause, cancel = threading.Event(), threading.Event()
                self._signals[task.id] = pause, cancel
                self._save()
                self._executor.submit(self._run, task.id, pause, cancel)

    def _run(self, task_id: str, pause: threading.Event, cancel: threading.Event) -> None:
        with self._lock:
            task = self._tasks[task_id]
            url, target = task.url, Path(task.target)

        def progress(received: int, total: int | None) -> None:
            with self._lock:
                task.received, task.total = received, total

        try:
            download_to(url, target, progress=progress, pause_event=pause, cancel_event=cancel)
        except DownloadPaused:
            state, error = TaskState.PAUSED, ""
        except DownloadCancelled:
            state, error = TaskState.CANCELLED, ""
        except OverloadError as exc:
            state, error = TaskState.FAILED, str(exc)
        except Exception as exc:
            state, error = TaskState.FAILED, f"Erreur inattendue : {exc}"
        else:
            state, error = TaskState.COMPLETED, ""
        with self._lock:
            if state == TaskState.COMPLETED:
                task.state = transition(task.state, TaskState.FINALIZING)
            task.state = transition(task.state, state)
            task.error = error
            self._signals.pop(task_id)
            self._save()
            self._schedule()
