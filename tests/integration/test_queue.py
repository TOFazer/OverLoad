import json
import threading
import time
from pathlib import Path

from overload.core.errors import OverloadError
from overload.downloads import queue as queue_module
from overload.downloads.engine import DownloadCancelled, DownloadPaused
from overload.downloads.queue import DownloadQueue
from overload.downloads.state import TaskState


def wait_for(predicate, timeout=3):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.01)
    raise AssertionError("la file n'a pas atteint l'état attendu")


def test_queue_limits_concurrency_and_pause_resume(monkeypatch, tmp_path):
    active = 0
    maximum = 0
    started = threading.Event()
    release = threading.Event()
    lock = threading.Lock()

    def fake(url, target, *, progress, pause_event, cancel_event):
        nonlocal active, maximum
        with lock:
            active += 1
            maximum = max(maximum, active)
            started.set()
        try:
            while not release.wait(0.01):
                if pause_event.is_set():
                    raise DownloadPaused("pause")
                if cancel_event.is_set():
                    raise DownloadCancelled("annulé")
            Path(target).write_bytes(b"ok")
            progress(2, 2)
        finally:
            with lock:
                active -= 1

    monkeypatch.setattr(queue_module, "download_to", fake)
    manager = DownloadQueue(tmp_path / "state.json", concurrency=1)
    try:
        a = manager.add("https://example.org/a.bin", tmp_path)
        assert started.wait(2)
        b = manager.add("https://example.org/b.bin", tmp_path)
        assert next(t.state for t in manager.snapshot() if t.id == b.id) == TaskState.QUEUED
        manager.pause(b.id)
        wait_for(lambda: next(t.state for t in manager.snapshot() if t.id == b.id)
                 == TaskState.PAUSED)
        manager.pause(a.id)
        wait_for(lambda: next(t.state for t in manager.snapshot() if t.id == a.id)
                 == TaskState.PAUSED)
        manager.resume(b.id)
        wait_for(lambda: next(t.state for t in manager.snapshot() if t.id == b.id)
                 == TaskState.RUNNING)
        release.set()
        wait_for(lambda: next(t.state for t in manager.snapshot() if t.id == b.id)
                 == TaskState.COMPLETED)
        assert maximum == 1
        assert json.loads((tmp_path / "state.json").read_text())["version"] == 1
    finally:
        release.set()
        manager.close()


def test_queue_restarts_in_progress_and_keeps_paused(monkeypatch, tmp_path):
    state = tmp_path / "state.json"
    state.write_text(json.dumps({"version": 1, "tasks": [
        {"id": "one", "url": "https://example.org/one.bin",
         "target": str(tmp_path / "one.bin"), "state": "running"},
        {"id": "two", "url": "https://example.org/two.bin",
         "target": str(tmp_path / "two.bin"), "state": "paused"},
    ]}))

    def fake(url, target, *, progress, pause_event, cancel_event):
        Path(target).write_bytes(b"ok")
        progress(2, 2)

    monkeypatch.setattr(queue_module, "download_to", fake)
    manager = DownloadQueue(state, concurrency=1)
    try:
        wait_for(lambda: manager.snapshot()[0].state == TaskState.COMPLETED)
        assert manager.snapshot()[1].state == TaskState.PAUSED
        manager.resume("two")
        wait_for(lambda: manager.snapshot()[1].state == TaskState.COMPLETED)
        assert (tmp_path / "two.bin").read_bytes() == b"ok"
    finally:
        manager.close()


def test_queue_bad_state_does_not_overwrite(monkeypatch, tmp_path):
    state = tmp_path / "state.json"
    state.write_text("{broken")
    try:
        DownloadQueue(state)
    except OverloadError as exc:
        assert "Historique" in str(exc)
    else:
        raise AssertionError("état invalide accepté")
    assert state.read_text() == "{broken"


def test_duplicate_queued_names_keep_extension(monkeypatch, tmp_path):
    release = threading.Event()

    def fake(url, target, *, progress, pause_event, cancel_event):
        release.wait(2)
        Path(target).write_bytes(b"done")

    monkeypatch.setattr(queue_module, "download_to", fake)
    manager = DownloadQueue(tmp_path / "state.json", concurrency=1)
    try:
        first = manager.add("https://example.org/clip.mp4", tmp_path)
        second = manager.add("https://example.org/clip.mp4", tmp_path)
        assert first.target.endswith("clip.mp4")
        assert second.target.endswith("clip (2).mp4")
    finally:
        release.set()
        manager.close()
