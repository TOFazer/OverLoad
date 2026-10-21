"""Création de l'arborescence d'un projet vidéo et mode « Préparer mon projet ».

Règles de sécurité :
- `plan_import` ne touche jamais au disque : il ne produit qu'un plan en mémoire ;
- `execute_import` ne crée que des copies : aucun original n'est déplacé, renommé,
  modifié ou supprimé ;
- aucune destination existante n'est écrasée : selon la politique choisie, le
  fichier en conflit est ignoré ou copié sous « nom (2) », « nom (3) »…
"""

from __future__ import annotations

import json
import os
import shutil
from collections.abc import Iterable
from datetime import UTC, datetime
from pathlib import Path

from overload.core.errors import OverloadError
from overload.creators.fsutil import (
    classify_file,
    expand_sources,
    iter_media_files,
    sanitize_name,
    unique_path,
    unique_path_among,
)
from overload.creators.models import EditingProfile, ImportResult, PlannedCopy
from overload.creators.renaming import render_filename
from overload.downloads.duplicates import DuplicatePolicy

MANIFEST_FILENAME = "overload-projet.json"
README_FILENAME = "LISEZ-MOI.txt"

__all__ = [
    "MANIFEST_FILENAME",
    "README_FILENAME",
    "classify_file",
    "create_project_structure",
    "execute_import",
    "expand_sources",
    "iter_media_files",
    "plan_import",
    "sanitize_name",
    "unique_path",
]


def _manifest_payload(project_name: str, profile: EditingProfile) -> dict:
    return {
        "app": "OverLoad",
        "projet": project_name,
        "profil": profile.id,
        "profil_nom": profile.name,
        "cree_le": datetime.now(UTC).isoformat(timespec="seconds"),
        "structure": profile.folders(),
        "regles": [
            "Les fichiers d'origine ne sont jamais déplacés, renommés ni supprimés.",
            "L'organisation du projet ne crée que des copies, après confirmation.",
            "Aucun fichier existant n'est écrasé sans accord explicite.",
        ],
    }


def _readme_text(project_name: str, profile: EditingProfile) -> str:
    lines = [
        f"Projet vidéo « {project_name} »",
        f"Profil de montage : {profile.name}",
        "",
        "Structure de dossiers :",
    ]
    for folder in profile.folders():
        lines.append(f"  - {folder}/")
    lines += [
        "",
        "Formats recommandés pour ce logiciel :",
        f"  - Conteneur : {profile.recommended_container or 'non précisé'}",
        f"  - Vidéo : {profile.recommended_video or 'non précisé'}",
        f"  - Audio : {profile.recommended_audio or 'non précisé'}",
    ]
    if profile.notes:
        lines += ["", f"Conseils : {profile.notes}"]
    lines += [
        "",
        "Règles de sécurité appliquées par OverLoad :",
        "  - vos fichiers d'origine ne sont jamais déplacés, renommés ni supprimés ;",
        "  - seules des copies sont créées dans cette arborescence, après confirmation ;",
        "  - aucun fichier existant n'est écrasé sans votre accord explicite.",
        "",
        "Ce fichier a été généré par OverLoad (https://github.com/TOFazer/OverLoad).",
    ]
    return "\n".join(lines) + "\n"


def create_project_structure(
    root: Path | str,
    *,
    project_name: str,
    profile: EditingProfile,
) -> list[Path]:
    """Prépare le dossier complet d'un projet vidéo : arborescence + LISEZ-MOI + manifeste.

    Si le dossier existe déjà, les sous-dossiers manquants sont simplement créés ;
    le LISEZ-MOI et le manifeste ne sont jamais écrasés s'ils existent déjà.
    """
    base = Path(root)
    created: list[Path] = []
    try:
        base.mkdir(parents=True, exist_ok=True)
        for folder in profile.folders():
            target = base / folder
            if not target.exists():
                target.mkdir(parents=True, exist_ok=True)
                created.append(target)
        readme = base / README_FILENAME
        if not readme.exists():
            readme.write_text(_readme_text(project_name, profile), encoding="utf-8")
        manifest = base / MANIFEST_FILENAME
        if not manifest.exists():
            payload = _manifest_payload(project_name, profile)
            tmp = manifest.with_suffix(".json.tmp")
            tmp.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
            os.replace(tmp, manifest)
    except OSError as exc:
        raise OverloadError(
            "Impossible de créer la structure du projet.",
            str(exc),
            "Vérifiez que le dossier choisi est accessible en écriture et réessayez.",
        ) from exc
    return created


def plan_import(
    sources: Iterable[Path | str],
    destination_root: Path | str,
    profile: EditingProfile,
    *,
    project_name: str = "",
    rename_template: str | None = None,
    classify: bool = True,
    recursive: bool = True,
) -> list[PlannedCopy]:
    """Construit le plan du mode « Préparer mon projet » sans rien écrire sur le disque.

    Chaque fichier source est classé par catégorie puis placé dans le dossier du
    profil correspondant. Les noms sortants peuvent suivre un modèle personnalisé.
    Les collisions (destination déjà présente sur le disque) sont signalées pour
    être confirmées avant toute copie ; les doublons au sein du lot reçoivent
    automatiquement un suffixe « (2) », « (3) »…
    """
    root = Path(destination_root)
    files = expand_sources(sources, recursive=recursive)
    plan: list[PlannedCopy] = []
    claimed: set[Path] = set()
    for number, source in enumerate(files, start=1):
        kind = classify_file(source)
        folder = root / (profile.folder_for(kind) if classify else "")
        filename = source.name
        if rename_template:
            filename = render_filename(
                rename_template,
                original=source,
                project_name=project_name,
                number=number,
            )
        destination = folder / filename
        if destination in claimed:
            destination = unique_path_among(destination, claimed)
        claimed.add(destination)
        plan.append(
            PlannedCopy(
                source=source,
                destination=destination,
                kind=kind,
                collision=destination.exists(),
            )
        )
    return plan


def execute_import(
    plan: Iterable[PlannedCopy],
    *,
    collision_policy: DuplicatePolicy = DuplicatePolicy.RENAME,
) -> ImportResult:
    """Exécute le plan confirmé : uniquement des copies, jamais un écrasement.

    - `collision_policy=SKIP` : les destinations déjà existantes sont ignorées ;
    - `collision_policy=RENAME` : une copie « nom (2) », « nom (3) »… est créée.

    Quelle que soit la politique, un fichier déjà présent sur le disque n'est
    JAMAIS écrasé, et les fichiers sources ne sont ni déplacés ni modifiés.
    """
    result = ImportResult()
    for step in plan:
        source, destination = step.source, step.destination
        try:
            destination.parent.mkdir(parents=True, exist_ok=True)
            if destination.exists():
                if collision_policy is DuplicatePolicy.SKIP:
                    result.skipped.append(
                        (source, f"la destination existe déjà : {destination}")
                    )
                    continue
                destination = unique_path(destination)
            shutil.copy2(source, destination)
            result.copied.append((source, destination))
        except OSError as exc:
            result.failed.append((source, str(exc)))
    return result
