"""Aligne le paquet et l'installateur sur le tag de la release avant compilation.

Usage : python scripts/set_release_version.py v1.2.3
Préversions acceptées : v1.2.3-alpha.1, v1.2.3-beta.1, v1.2.3-rc.1.
Les modifications restent dans le workspace de build ; aucun commit n'est nécessaire.
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TAG_PATTERN = re.compile(
    r"v?(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)"
    r"(?:-(alpha|beta|rc)\.(0|[1-9][0-9]*))?"
)


def release_versions(tag: str) -> tuple[str, str, str]:
    """Renvoie les versions Python (PEP 440), affichée et numérique Windows."""
    match = TAG_PATTERN.fullmatch(tag)
    if match is None:
        raise ValueError(
            "Tag de release invalide : utilisez v1.2.3 ou v1.2.3-rc.1 "
            "(alpha et beta sont aussi acceptés)."
        )
    major, minor, patch, channel, number = match.groups()
    if any(int(part) > 65535 for part in (major, minor, patch)):
        raise ValueError("Chaque composant de version Windows doit être compris entre 0 et 65535.")
    base = f"{major}.{minor}.{patch}"
    python_version = display_version = base
    if channel:
        suffix = {"alpha": "a", "beta": "b", "rc": "rc"}[channel]
        python_version = f"{base}{suffix}{number}"
        display_version = f"{base}-{channel}.{number}"
    return python_version, display_version, f"{base}.0"


def set_release_version(tag: str, root: Path = ROOT) -> None:
    python_version, display_version, numeric_version = release_versions(tag)
    replacements = {
        root / "pyproject.toml": [(r'^version = "[^"]+"$', f'version = "{python_version}"')],
        root / "src" / "overload" / "__init__.py": [
            (r'^__version__ = "[^"]+"$', f'__version__ = "{python_version}"'),
        ],
        root / "packaging" / "OverLoad.iss": [
            (r'^#define MyAppVersion "[^"]+"$', f'#define MyAppVersion "{display_version}"'),
            (
                r'^#define MyAppNumericVersion "[^"]+"$',
                f'#define MyAppNumericVersion "{numeric_version}"',
            ),
        ],
    }
    # Tout valider avant d'écrire, pour ne pas laisser des versions incohérentes
    # si un fichier change de structure ou si le tag n'est pas pris en charge.
    updates = {}
    for path, rules in replacements.items():
        content = path.read_text(encoding="utf-8")
        for pattern, replacement in rules:
            content, count = re.subn(pattern, replacement, content, flags=re.MULTILINE)
            if count != 1:
                raise ValueError(f"Déclaration de version absente ou ambiguë dans {path}.")
        updates[path] = content
    for path, content in updates.items():
        path.write_text(content, encoding="utf-8")
    print(f"Release {tag} : paquet {python_version}, installateur {display_version}.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("tag", help="Tag Git de la release, par exemple v1.2.3.")
    args = parser.parse_args()
    try:
        set_release_version(args.tag)
    except ValueError as exc:
        parser.error(str(exc))


if __name__ == "__main__":
    main()
