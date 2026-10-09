"""Noms de fichiers sûrs et prévention des écrasements."""

from __future__ import annotations

import re
from pathlib import Path
from urllib.parse import unquote, urlsplit

from overload.core.errors import OverloadError

DEFAULT_NAME = "fichier"
MAX_NAME_LENGTH = 180
PART_SUFFIX = ".part"

_RESERVED = frozenset(
    {"CON", "PRN", "AUX", "NUL"}
    | {f"COM{i}" for i in range(1, 10)}
    | {f"LPT{i}" for i in range(1, 10)}
)
_INVALID_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def sanitize_filename(name: str) -> str:
    """Rend un nom utilisable sous Windows, sans séparateur ni nom réservé."""
    base = name.replace("\\", "/").split("/")[-1]
    base = _INVALID_CHARS.sub("_", base).strip().rstrip(". ")
    if not base or base in {".", ".."}:
        return DEFAULT_NAME
    stem, dot, ext = base.rpartition(".")
    if not dot:
        stem, ext = base, ""
    if stem.upper() in _RESERVED:
        stem = f"_{stem}"
    result = f"{stem}.{ext}" if ext else stem
    if len(result) > MAX_NAME_LENGTH:
        keep = MAX_NAME_LENGTH - (len(ext) + 1 if ext else 0)
        result = stem[:keep] + (f".{ext}" if ext else "")
    return result or DEFAULT_NAME


def filename_from_url(url: str) -> str:
    """Déduit un nom de fichier raisonnable à partir de l'URL."""
    path = unquote(urlsplit(url).path)
    return sanitize_filename(path.rsplit("/", 1)[-1])


def is_inside(directory: Path, candidate: Path) -> bool:
    """Vrai si `candidate` reste dans `directory` après résolution des liens."""
    base = directory.resolve()
    target = candidate.resolve()
    return target == base or base in target.parents


def plan_destination(directory: Path, name: str) -> Path:
    """Choisit un chemin qui n'existe pas encore (ni le fichier, ni son .part).

    Ne remplace jamais un fichier existant : ajoute « (2) », « (3) »… au nom.
    """
    safe = sanitize_filename(name)
    stem, dot, ext = safe.rpartition(".")
    if not dot:
        stem, ext = safe, ""
    suffix = f".{ext}" if ext else ""
    candidate = directory / safe
    counter = 2
    while candidate.exists() or (directory / (candidate.name + PART_SUFFIX)).exists():
        candidate = directory / f"{stem} ({counter}){suffix}"
        counter += 1
        if counter > 10_000:
            raise OverloadError(
                "Impossible de choisir un nom de fichier libre.",
                "trop de fichiers portent le même nom.",
                "Choisissez un autre nom ou un autre dossier.",
            )
    if not is_inside(directory, candidate):
        raise OverloadError("Nom de fichier refusé.", "le chemin sort du dossier choisi.")
    return candidate
