"""Détection intelligente des fichiers déjà présents et politiques de doublons."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any

from overload.core.errors import OverloadError
from overload.core.formatting import format_bytes
from overload.downloads.files import PART_SUFFIX, filename_from_url, sanitize_filename
from overload.history.store import DownloadHistoryStore


class DuplicatePolicy(StrEnum):
    """Comportement lorsqu'un fichier identique est déjà présent."""

    ASK = "ask"        # Signale le doublon (lève DuplicateDetectedError si non confirmé)
    SKIP = "skip"      # Ignore le téléchargement sans erreur
    RENAME = "rename"  # Télécharge sous « nom (2).ext » sans jamais écraser
    RESUME = "resume"  # Reprend un fichier .part existant si disponible, sinon renomme/ignore


class DuplicateSource(StrEnum):
    ACTIVE_TASK = "active_task"
    EXISTING_FILE = "existing_file"
    HISTORY_FILE = "history_file"
    PARTIAL_FILE = "partial_file"


@dataclass(frozen=True)
class DuplicateMatch:
    """Résultat positif de la détection d'un fichier déjà présent ou en cours."""

    url: str
    filename: str
    source: DuplicateSource
    existing_path: Path
    existing_size: int
    reason: str
    resumable: bool = False
    task_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "url": self.url,
            "filename": self.filename,
            "source": self.source.value,
            "existing_path": str(self.existing_path),
            "existing_dir": str(self.existing_path.parent),
            "existing_size": self.existing_size,
            "existing_size_human": format_bytes(self.existing_size),
            "reason": self.reason,
            "resumable": self.resumable,
            "task_id": self.task_id,
        }


class DuplicateDetectedError(OverloadError):
    """Levée en mode `DuplicatePolicy.ASK` lorsqu'un doublon requiert un choix."""

    def __init__(self, match: DuplicateMatch) -> None:
        self.match = match
        super().__init__(
            f"Le fichier « {match.filename} » est déjà présent.",
            match.reason,
            "Ouvrez le dossier existant, ignorez ce lien ou choisissez de conserver une copie.",
        )


def detect_duplicate(
    url: str,
    destination_dir: Path,
    *,
    filename: str | None = None,
    active_items: Iterable[tuple[str, str, Path]] = (),
    history: DownloadHistoryStore | None = None,
) -> DuplicateMatch | None:
    """Vérifie si `url` ou le fichier cible est déjà actif, présent sur disque ou dans l'historique.

    `active_items` contient des triplets `(task_id, task_url, target_path)` pour les
    tâches actuellement actives, en pause ou en file d'attente.
    """
    clean_url = url.strip()
    resolved_name = sanitize_filename(filename) if filename else filename_from_url(clean_url)
    candidate = destination_dir / resolved_name
    part_file = destination_dir / (resolved_name + PART_SUFFIX)

    active_targets: set[Path] = set()
    for task_id, task_url, target_path in active_items:
        active_targets.add(target_path)
        if task_url == clean_url:
            size = (
                target_path.stat().st_size
                if target_path.exists()
                else (
                    Path(str(target_path) + PART_SUFFIX).stat().st_size
                    if Path(str(target_path) + PART_SUFFIX).exists()
                    else 0
                )
            )
            return DuplicateMatch(
                url=clean_url,
                filename=target_path.name,
                source=DuplicateSource.ACTIVE_TASK,
                existing_path=target_path,
                existing_size=size,
                reason="Cette adresse est déjà présente dans la file de téléchargement.",
                resumable=False,
                task_id=task_id,
            )

    if candidate.is_file():
        size = candidate.stat().st_size
        return DuplicateMatch(
            url=clean_url,
            filename=resolved_name,
            source=DuplicateSource.EXISTING_FILE,
            existing_path=candidate,
            existing_size=size,
            reason=(
                f"Un fichier « {resolved_name} » ({format_bytes(size)}) "
                "existe déjà dans le dossier de destination."
            ),
            resumable=False,
        )

    if history is not None:
        past = history.find_completed_by_url(clean_url)
        if past is not None:
            past_path = Path(past.destination_path)
            size = past_path.stat().st_size if past_path.is_file() else past.size_bytes
            return DuplicateMatch(
                url=clean_url,
                filename=past.filename,
                source=DuplicateSource.HISTORY_FILE,
                existing_path=past_path,
                existing_size=size,
                reason=(
                    f"Déjà téléchargé précédemment sous « {past.filename} » "
                    f"({format_bytes(size)})."
                ),
                resumable=False,
            )

    if part_file.is_file() and candidate not in active_targets:
        part_size = part_file.stat().st_size
        return DuplicateMatch(
            url=clean_url,
            filename=resolved_name,
            source=DuplicateSource.PARTIAL_FILE,
            existing_path=part_file,
            existing_size=part_size,
            reason=(
                f"Un téléchargement partiel « {part_file.name} » ({format_bytes(part_size)}) "
                "peut être repris automatiquement."
            ),
            resumable=True,
        )

    return None
