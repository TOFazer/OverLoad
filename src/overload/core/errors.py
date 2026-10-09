"""Erreurs utilisateur structurées.

Chaque erreur importante explique : ce qui a échoué, la cause probable,
les conséquences et l'action à essayer. Les traces techniques restent
dans le journal, jamais affichées telles quelles aux débutants.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class OverloadError(Exception):
    """Erreur destinée à être présentée à l'utilisateur."""

    what: str
    cause: str = ""
    action: str = ""

    def __str__(self) -> str:
        parts = [self.what]
        if self.cause:
            parts.append(f"Cause probable : {self.cause}")
        if self.action:
            parts.append(f"Action : {self.action}")
        return "\n".join(parts)
