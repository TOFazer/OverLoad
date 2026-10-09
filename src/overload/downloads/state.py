"""États d'une tâche de téléchargement.

« Terminé » n'est atteint que depuis l'état FINALIZING, après vérification
du fichier. Les transitions non prévues sont refusées.
"""

from __future__ import annotations

from enum import StrEnum

from overload.core.errors import OverloadError


class TaskState(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    PAUSED = "paused"
    FINALIZING = "finalizing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


_TRANSITIONS: dict[TaskState, frozenset[TaskState]] = {
    TaskState.QUEUED: frozenset({TaskState.RUNNING, TaskState.CANCELLED}),
    TaskState.RUNNING: frozenset(
        {TaskState.PAUSED, TaskState.FINALIZING, TaskState.FAILED, TaskState.CANCELLED}
    ),
    TaskState.PAUSED: frozenset({TaskState.RUNNING, TaskState.CANCELLED}),
    TaskState.FINALIZING: frozenset({TaskState.COMPLETED, TaskState.FAILED}),
    TaskState.FAILED: frozenset({TaskState.QUEUED}),  # relance manuelle
    TaskState.CANCELLED: frozenset({TaskState.QUEUED}),
    TaskState.COMPLETED: frozenset(),
}


def can_transition(current: TaskState, new: TaskState) -> bool:
    return new in _TRANSITIONS[current]


def transition(current: TaskState, new: TaskState) -> TaskState:
    if not can_transition(current, new):
        raise OverloadError(
            "Opération impossible sur cette tâche.",
            f"passage de l'état « {current.value} » à « {new.value} » non autorisé.",
            "Rafraîchissez la liste ; si le problème persiste, consultez le journal.",
        )
    return new
