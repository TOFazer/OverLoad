"""Modèles de données du gestionnaire de téléchargements intelligent."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from overload.core.formatting import format_bytes, format_duration, format_speed
from overload.downloads.duplicates import DuplicateMatch, DuplicatePolicy
from overload.downloads.state import TaskState
from overload.downloads.telemetry import ConnectionIssue


@dataclass(frozen=True)
class ManagerSettings:
    """Configuration active du gestionnaire de téléchargements."""

    destination_dir: Path
    max_concurrent: int = 3
    speed_limit_bps: int | None = None
    auto_retry: bool = True
    max_retries: int = 3
    retry_initial_delay: float = 1.5
    duplicate_policy: DuplicatePolicy = DuplicatePolicy.ASK

    def to_dict(self) -> dict[str, Any]:
        return {
            "destination_dir": str(self.destination_dir),
            "max_concurrent": self.max_concurrent,
            "speed_limit_bps": self.speed_limit_bps,
            "speed_limit_human": (
                format_speed(self.speed_limit_bps)
                if self.speed_limit_bps
                else "Illimitée"
            ),
            "auto_retry": self.auto_retry,
            "max_retries": self.max_retries,
            "retry_initial_delay": self.retry_initial_delay,
            "duplicate_policy": self.duplicate_policy.value,
        }


@dataclass(frozen=True)
class TaskSnapshot:
    """Photographie thread-safe de l'état complet d'une tâche pour l'interface ou les tests."""

    id: str
    url: str
    filename: str
    target_path: Path
    state: TaskState
    downloaded_bytes: int
    total_bytes: int | None
    progress_percent: float | None
    speed_bps: float
    eta_seconds: float | None
    retry_count: int
    max_retries: int
    retrying: bool
    retry_in_seconds: float | None
    resumed_from_part: bool
    stalled: bool
    stall_seconds: float
    active_warning: str
    error_message: str
    issues: tuple[ConnectionIssue, ...]
    created_at: str
    started_at: str | None
    finished_at: str | None
    provider: str = "http"
    quality: str = "best"
    media_title: str = ""
    thumbnail_url: str = ""

    @property
    def file_exists(self) -> bool:
        return self.target_path.is_file()

    @property
    def part_exists(self) -> bool:
        return self.target_path.with_name(self.target_path.name + ".part").is_file()

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "url": self.url,
            "filename": self.filename,
            "target_path": str(self.target_path),
            "destination_dir": str(self.target_path.parent),
            "state": self.state.value,
            "downloaded_bytes": self.downloaded_bytes,
            "downloaded_human": format_bytes(self.downloaded_bytes),
            "total_bytes": self.total_bytes,
            "total_human": format_bytes(self.total_bytes),
            "progress_percent": (
                round(self.progress_percent, 1) if self.progress_percent is not None else None
            ),
            "speed_bps": round(self.speed_bps, 2),
            "speed_human": format_speed(self.speed_bps),
            "eta_seconds": round(self.eta_seconds, 1) if self.eta_seconds is not None else None,
            "eta_human": format_duration(self.eta_seconds),
            "retry_count": self.retry_count,
            "max_retries": self.max_retries,
            "retrying": self.retrying,
            "retry_in_seconds": (
                round(self.retry_in_seconds, 1) if self.retry_in_seconds is not None else None
            ),
            "resumed_from_part": self.resumed_from_part,
            "stalled": self.stalled,
            "stall_seconds": round(self.stall_seconds, 1),
            "active_warning": self.active_warning,
            "error_message": self.error_message,
            "issues": [issue.to_dict() for issue in self.issues],
            "created_at": self.created_at,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "file_exists": self.file_exists,
            "part_exists": self.part_exists,
            "provider": self.provider,
            "quality": self.quality,
            "media_title": self.media_title,
            "thumbnail_url": self.thumbnail_url,
        }


@dataclass(frozen=True)
class RejectedLink:
    """Lien rejeté lors de la validation d'un lot."""

    line: int
    url: str
    error: str

    def to_dict(self) -> dict[str, Any]:
        return {"line": self.line, "url": self.url, "error": self.error}


@dataclass(frozen=True)
class BatchResult:
    """Bilan détaillé d'un ajout par lot."""

    added: list[TaskSnapshot] = field(default_factory=list)
    skipped_duplicates: list[DuplicateMatch] = field(default_factory=list)
    conflicts: list[DuplicateMatch] = field(default_factory=list)
    rejected: list[RejectedLink] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "added": [item.to_dict() for item in self.added],
            "skipped_duplicates": [item.to_dict() for item in self.skipped_duplicates],
            "conflicts": [item.to_dict() for item in self.conflicts],
            "rejected": [item.to_dict() for item in self.rejected],
            "summary": {
                "added_count": len(self.added),
                "skipped_count": len(self.skipped_duplicates),
                "conflict_count": len(self.conflicts),
                "rejected_count": len(self.rejected),
            },
        }
