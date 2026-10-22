"""La progression ne doit afficher 100 % que pour un fichier terminé et vérifié."""

from __future__ import annotations

from overload.downloads.manager import DownloadManager, _ManagedTask
from overload.downloads.state import TaskState
from overload.downloads.telemetry import SpeedEstimator


def _task(state: TaskState, downloaded: int, total: int | None) -> _ManagedTask:
    return _ManagedTask(
        id="t1",
        url="https://exemple.com/fichier.mp4",
        filename="fichier.mp4",
        target_path=None,  # type: ignore[arg-type] - non lu par _snapshot_locked
        state=state,
        queue_seq=1,
        max_retries=3,
        speed=SpeedEstimator(),
        downloaded_bytes=downloaded,
        total_bytes=total,
    )


def test_progress_is_capped_before_completion(tmp_path):
    with DownloadManager(tmp_path / "dl") as manager:
        # Tous les octets sont là mais la vérification est en cours : jamais 100 %.
        finalizing = manager._snapshot_locked(_task(TaskState.FINALIZING, 1000, 1000))
        assert finalizing.progress_percent == 99.9

        running = manager._snapshot_locked(_task(TaskState.RUNNING, 1000, 1000))
        assert running.progress_percent == 99.9

        partial = manager._snapshot_locked(_task(TaskState.PAUSED, 250, 1000))
        assert partial.progress_percent == 25.0

        completed = manager._snapshot_locked(_task(TaskState.COMPLETED, 1000, 1000))
        assert completed.progress_percent == 100.0
