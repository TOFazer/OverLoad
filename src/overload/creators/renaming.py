"""Renommage par lots avec modèles personnalisés.

Jetons disponibles dans un modèle :
- `{projet}`   : nom du projet (nettoyé des caractères interdits) ;
- `{nom}`      : nom d'origine du fichier, sans extension ;
- `{origine}`  : nom du dossier parent du fichier ;
- `{type}`     : catégorie (Video, Audio, Image, SousTitres, Autre) ;
- `{ext}`      : extension avec le point (ex. `.mp4`) ;
- `{date}`     : date du jour `AAAA-MM-JJ` ;
- `{annee}` / `{mois}` / `{jour}` : éléments de la date du jour ;
- `{heure}`    : heure actuelle `HHhMM` ;
- `{numero}`   : numéro d'ordre dans le lot, padding possible : `{numero:03}`.

Sécurité : le renommage n'écrase jamais un fichier existant ; en cas de conflit,
un suffixe « (2) », « (3) »… est ajouté (politique RENAME) ou le fichier est
laissé intact (politique SKIP).
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from datetime import UTC, datetime
from pathlib import Path

from overload.core.errors import OverloadError
from overload.creators.fsutil import classify_file, sanitize_name, unique_path, unique_path_among
from overload.creators.models import RenameResult, RenameStep
from overload.downloads.duplicates import DuplicatePolicy

_NUMBER_TOKEN = re.compile(r"\{numero(?::0*(\d+))?\}")

TEMPLATE_HELP = (
    "Jetons : {projet} · {nom} · {origine} · {type} · {ext} · {date} · {annee} · {mois} · "
    "{jour} · {heure} · {numero} (padding possible : {numero:03})"
)

DEFAULT_TEMPLATE = "{projet}_{type}_{date}_{numero:03}"


def _token_values(
    original: Path, *, project_name: str, number: int, now: datetime
) -> dict[str, str]:
    kind = classify_file(original)
    return {
        "projet": sanitize_name(project_name) if project_name else "",
        "nom": sanitize_name(original.stem) or "sans-nom",
        "origine": sanitize_name(original.parent.name) or "sans-dossier",
        "type": kind.folder_token,
        "ext": original.suffix.lower(),
        "date": now.strftime("%Y-%m-%d"),
        "annee": now.strftime("%Y"),
        "mois": now.strftime("%m"),
        "jour": now.strftime("%d"),
        "heure": now.strftime("%Hh%M"),
    }


def render_filename(
    template: str,
    *,
    original: Path,
    project_name: str = "",
    number: int = 1,
    now: datetime | None = None,
) -> str:
    """Applique le modèle pour produire le nouveau nom de fichier (avec extension).

    Si le modèle ne contient pas `{ext}`, l'extension d'origine est conservée.
    Le résultat est nettoyé des caractères interdits sous Windows.
    """
    moment = now or datetime.now(UTC)
    cleaned_template = template.strip()
    if not cleaned_template:
        raise OverloadError(
            "Modèle de renommage vide.",
            "aucun modèle n'a été saisi.",
            f"Exemple de modèle : {DEFAULT_TEMPLATE}",
        )

    padding = 1
    normalized = cleaned_template
    match = _NUMBER_TOKEN.search(normalized)
    if match:
        padding = int(match.group(1) or 1)
        normalized = _NUMBER_TOKEN.sub("\x00NUMERO\x00", normalized)

    values = _token_values(original, project_name=project_name, number=number, now=moment)

    rendered = normalized
    for token, value in values.items():
        rendered = rendered.replace("{" + token + "}", value)
    rendered = rendered.replace("\x00NUMERO\x00", f"{number:0{max(1, padding)}d}")
    # Les jetons inconnus (faute de frappe) sont retirés pour éviter un nom illisible.
    rendered = re.sub(r"\{[a-zA-Z_][a-zA-Z0-9_]*(?::[^{}]*)?\}", "", rendered)

    if not rendered.strip():
        raise OverloadError(
            "Le modèle ne produit aucun nom utilisable.",
            f"le modèle « {cleaned_template} » génère un nom vide pour {original.name}.",
            "Ajoutez au moins un jeton comme {nom} ou {numero}.",
        )
    keep_extension = "{ext}" not in cleaned_template
    name = sanitize_name(rendered).strip(" ._-")
    if keep_extension and original.suffix:
        name = f"{name}{original.suffix.lower()}"
    if not name or name == original.suffix.lower():
        raise OverloadError(
            "Le modèle ne produit aucun nom utilisable.",
            f"le modèle « {cleaned_template} » génère un nom vide pour {original.name}.",
            "Ajoutez au moins un jeton comme {nom} ou {numero}.",
        )
    return name


def _build_steps(
    files: Iterable[Path],
    template: str,
    *,
    project_name: str = "",
    now: datetime | None = None,
) -> list[RenameStep]:
    moment = now or datetime.now(UTC)
    steps: list[RenameStep] = []
    claimed: set[Path] = set()  # destinations déjà réservées par ce lot
    number = 0
    for original in files:
        number += 1
        try:
            new_name = render_filename(
                template, original=original, project_name=project_name, number=number, now=moment
            )
        except OverloadError as exc:
            steps.append(RenameStep(original, original, "erreur", str(exc)))
            continue
        new_path = original.with_name(new_name)
        if new_path == original:
            steps.append(RenameStep(original, new_path, "inchangé"))
            continue
        if new_path in claimed:
            # Deux fichiers du lot visent le même nom : le second reçoit un suffixe.
            resolved = unique_path_among(new_path, claimed)
            steps.append(
                RenameStep(
                    original,
                    resolved,
                    "conflit",
                    "deux fichiers du lot produisent le même nom : suffixe ajouté",
                )
            )
            claimed.add(resolved)
        elif new_path.exists():
            steps.append(
                RenameStep(
                    original,
                    new_path,
                    "conflit",
                    f"un fichier nommé « {new_name} » existe déjà dans ce dossier",
                )
            )
        else:
            steps.append(RenameStep(original, new_path, "ok"))
            claimed.add(new_path)
    return steps


def preview_renaming(
    files: Iterable[Path],
    template: str,
    *,
    project_name: str = "",
    now: datetime | None = None,
) -> list[RenameStep]:
    """Aperçu sans risque du renommage : rien n'est écrit sur le disque."""
    return _build_steps(files, template, project_name=project_name, now=now)


def apply_renaming(
    files: Iterable[Path],
    template: str,
    *,
    project_name: str = "",
    conflict_policy: DuplicatePolicy = DuplicatePolicy.RENAME,
    now: datetime | None = None,
) -> RenameResult:
    """Renomme les fichiers du lot selon le modèle, sans jamais rien écraser.

    - politique RENAME (défaut) : un conflit reçoit un suffixe « (2) », « (3) »… ;
    - politique SKIP : le fichier concerné est laissé intact et signalé.
    """
    steps = _build_steps(files, template, project_name=project_name, now=now)
    result = RenameResult()
    for step in steps:
        if step.status == "erreur":
            result.failed.append((step.original, step.message))
            continue
        if step.status == "inchangé":
            result.skipped.append((step.original, "le nouveau nom est identique"))
            continue
        if step.status == "conflit" and conflict_policy is DuplicatePolicy.SKIP:
            result.skipped.append((step.original, step.message))
            continue
        try:
            target = step.new_path
            if target.exists():
                # Re-vérification au moment appliqué : rien n'est jamais écrasé.
                if conflict_policy is DuplicatePolicy.SKIP:
                    result.skipped.append((step.original, f"« {target.name} » existe déjà"))
                    continue
                target = unique_path(target)
            step.original.rename(target)
            result.renamed.append((step.original, target))
        except OSError as exc:
            result.failed.append((step.original, str(exc)))
    return result
