"""Registre persistant des projets vidéo de l'espace Créateurs.

Le registre est un petit fichier JSON atomique (`creators/projects.json`).
Supprimer un projet du registre ne supprime JAMAIS le dossier du projet ni
aucun fichier sur le disque : il disparaît simplement de la liste.
"""

from __future__ import annotations

import json
import os
import threading
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from overload.core.errors import OverloadError
from overload.creators.models import CreatorProject

SCHEMA_VERSION = 1


class CreatorProjectsStore:
    """Liste des projets vidéo enregistrés, triés du plus récent au plus ancien."""

    def __init__(self, path: Path | str) -> None:
        self._path = Path(path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._projects: dict[str, CreatorProject] = {}
        self._order: list[str] = []
        self._load()

    @property
    def path(self) -> Path:
        return self._path

    def _load(self) -> None:
        if not self._path.is_file():
            return
        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return
        if not isinstance(raw, dict):
            return
        entries = raw.get("projects", [])
        if not isinstance(entries, list):
            return
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            project = CreatorProject.from_dict(entry)
            if project.id and project.id not in self._projects:
                self._projects[project.id] = project
                self._order.append(project.id)

    def _save_locked(self) -> None:
        payload: dict[str, Any] = {
            "schema_version": SCHEMA_VERSION,
            "projects": [self._projects[pid].to_dict() for pid in self._order],
        }
        tmp = self._path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, self._path)

    def list_projects(self) -> list[CreatorProject]:
        """Projets enregistrés, du plus récemment ouvert/créé au plus ancien."""
        with self._lock:
            return [self._projects[pid] for pid in self._order if pid in self._projects]

    def get(self, project_id: str) -> CreatorProject:
        with self._lock:
            project = self._projects.get(project_id)
        if project is None:
            raise OverloadError(
                "Projet introuvable dans l'espace Créateurs.",
                f"l'identifiant « {project_id} » est inconnu.",
                "Recréez le projet ou rafraîchissez la liste.",
            )
        return project

    def add_project(
        self,
        *,
        name: str,
        root_dir: Path | str,
        profile_id: str,
        notes: str = "",
    ) -> CreatorProject:
        """Enregistre un projet (ou met à jour l'entrée existant au même emplacement)."""
        cleaned = name.strip()
        if not cleaned:
            raise OverloadError(
                "Nom de projet invalide.",
                "le nom du projet est vide.",
                "Saisissez un nom lisible, par exemple « Vlog octobre 2026 ».",
            )
        root = str(Path(root_dir))
        now = datetime.now(UTC).isoformat(timespec="seconds")
        with self._lock:
            for existing in self._projects.values():
                if existing.root_dir == root:
                    updated = CreatorProject(
                        id=existing.id,
                        name=cleaned,
                        root_dir=root,
                        profile_id=profile_id,
                        created_at=existing.created_at,
                        last_opened_at=now,
                        notes=notes or existing.notes,
                    )
                    self._projects[existing.id] = updated
                    self._save_locked()
                    return updated
            project = CreatorProject(
                id=uuid.uuid4().hex[:12],
                name=cleaned,
                root_dir=root,
                profile_id=profile_id,
                created_at=now,
                last_opened_at=now,
                notes=notes,
            )
            self._projects[project.id] = project
            self._order.insert(0, project.id)
            self._save_locked()
            return project

    def remove_project(self, project_id: str) -> bool:
        """Retire le projet de la liste — ne supprime AUCUN fichier sur le disque."""
        with self._lock:
            project = self._projects.pop(project_id, None)
            if project is None:
                return False
            self._order = [pid for pid in self._order if pid != project_id]
            self._save_locked()
            return True

    def touch(self, project_id: str) -> None:
        """Marque le projet comme dernièrement ouvert (ordre de la liste)."""
        with self._lock:
            project = self._projects.get(project_id)
            if project is None:
                return
            updated = CreatorProject(
                **{
                    **project.to_dict(),
                    "last_opened_at": datetime.now(UTC).isoformat(timespec="seconds"),
                }
            )
            self._projects[project_id] = updated
            self._order.remove(project_id)
            self._order.insert(0, project_id)
            self._save_locked()
