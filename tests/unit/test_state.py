import pytest

from overload.core.errors import OverloadError
from overload.downloads.state import TaskState, can_transition, transition


def test_completed_is_terminal():
    assert not any(can_transition(TaskState.COMPLETED, s) for s in TaskState)


def test_completion_only_after_finalizing():
    assert not can_transition(TaskState.RUNNING, TaskState.COMPLETED)
    assert can_transition(TaskState.FINALIZING, TaskState.COMPLETED)


def test_pause_and_resume():
    state = transition(TaskState.QUEUED, TaskState.RUNNING)
    state = transition(state, TaskState.PAUSED)
    assert transition(state, TaskState.RUNNING) is TaskState.RUNNING


def test_failed_task_can_be_retried():
    assert transition(TaskState.FAILED, TaskState.QUEUED) is TaskState.QUEUED


def test_invalid_transition_raises_readable_error():
    with pytest.raises(OverloadError) as info:
        transition(TaskState.QUEUED, TaskState.COMPLETED)
    assert "queued" in info.value.cause
