import time

import pytest

from overload.core.errors import OverloadError
from overload.downloads.manager import DownloadManager
from overload.downloads.state import TaskState
from tests.conftest import PAYLOAD


def _wait(manager, task_id, states, timeout=15.0):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        view = manager.get(task_id)
        if view.state in states:
            return view
        time.sleep(0.02)
    raise AssertionError(
        f"état {[s.value for s in states]} non atteint : {manager.get(task_id).state.value}"
    )


def _wait_receiving(manager, task_id):
    """Attend qu'un téléchargement lent ait commencé à recevoir des données."""
    end = time.monotonic() + 15
    while time.monotonic() < end:
        view = manager.get(task_id)
        if view.state is TaskState.RUNNING and view.received > 0:
            return view
        time.sleep(0.01)
    raise AssertionError("le téléchargement n'a pas commencé")


@pytest.fixture
def manager():
    m = DownloadManager(max_workers=2, allow_private_hosts=True)
    yield m
    m.shutdown()


def test_successful_task_reaches_completed_with_file(server, manager, tmp_path):
    task_id = manager.submit(f"{server}/ok.bin", tmp_path)
    view = _wait(manager, task_id, {TaskState.COMPLETED, TaskState.FAILED})
    assert view.state is TaskState.COMPLETED
    assert view.result_path.read_bytes() == PAYLOAD
    assert view.progress == 1.0


def test_local_address_refused_at_submit_without_task(tmp_path):
    m = DownloadManager(allow_private_hosts=False)
    try:
        with pytest.raises(OverloadError):
            m.submit("http://127.0.0.1/ok.bin", tmp_path)
        assert m.snapshot() == []
        assert list(tmp_path.iterdir()) == []
    finally:
        m.shutdown()


def test_missing_file_gives_failed_with_readable_error(server, manager, tmp_path):
    task_id = manager.submit(f"{server}/missing.bin", tmp_path)
    view = _wait(manager, task_id, {TaskState.FAILED, TaskState.COMPLETED})
    assert view.state is TaskState.FAILED
    assert "introuvable" in view.error
    assert view.result_path is None


def test_pause_keeps_partial_then_resume_completes(server, manager, tmp_path):
    task_id = manager.submit(f"{server}/slow.bin", tmp_path)
    _wait_receiving(manager, task_id)
    assert manager.pause(task_id)
    view = _wait(manager, task_id, {TaskState.PAUSED, TaskState.COMPLETED})
    assert view.state is TaskState.PAUSED
    assert (tmp_path / "slow.bin.part").exists()
    assert manager.resume(task_id)
    view = _wait(manager, task_id, {TaskState.COMPLETED, TaskState.FAILED})
    assert view.state is TaskState.COMPLETED
    assert sorted(p.name for p in tmp_path.iterdir()) == ["slow.bin"]
    assert view.result_path.read_bytes() == PAYLOAD


def test_cancel_running_task_removes_partial(server, manager, tmp_path):
    task_id = manager.submit(f"{server}/slow.bin", tmp_path)
    _wait_receiving(manager, task_id)
    assert manager.cancel(task_id)
    view = _wait(manager, task_id, {TaskState.CANCELLED, TaskState.COMPLETED})
    assert view.state is TaskState.CANCELLED
    assert list(tmp_path.iterdir()) == []


def test_cancel_paused_task_removes_partial_and_retry_restarts(server, manager, tmp_path):
    task_id = manager.submit(f"{server}/slow.bin", tmp_path)
    _wait_receiving(manager, task_id)
    manager.pause(task_id)
    _wait(manager, task_id, {TaskState.PAUSED})
    assert manager.cancel(task_id)
    assert manager.get(task_id).state is TaskState.CANCELLED
    assert list(tmp_path.iterdir()) == []
    assert manager.retry(task_id)
    view = _wait(manager, task_id, {TaskState.COMPLETED, TaskState.FAILED})
    assert view.state is TaskState.COMPLETED
    assert view.result_path.read_bytes() == PAYLOAD


def test_shutdown_pauses_running_task_and_keeps_partial(server, tmp_path):
    manager = DownloadManager(max_workers=1, allow_private_hosts=True)
    task_id = manager.submit(f"{server}/slow.bin", tmp_path)
    _wait_receiving(manager, task_id)
    manager.shutdown()
    assert manager.get(task_id).state is TaskState.PAUSED
    assert (tmp_path / "slow.bin.part").exists()


def test_truncated_download_fails_and_keeps_partial(server, manager, tmp_path):
    task_id = manager.submit(f"{server}/truncated.bin", tmp_path)
    view = _wait(manager, task_id, {TaskState.FAILED, TaskState.COMPLETED})
    assert view.state is TaskState.FAILED
    assert "incomplet" in view.error
    assert (tmp_path / "truncated.bin.part").exists()
    assert view.result_path is None


def test_cancel_is_refused_for_finished_task(server, manager, tmp_path):
    task_id = manager.submit(f"{server}/ok.bin", tmp_path)
    _wait(manager, task_id, {TaskState.COMPLETED})
    assert manager.cancel(task_id) is False
    assert manager.get(task_id).state is TaskState.COMPLETED
