"""Classement automatique des téléchargements dans des dossiers personnalisables.

L'utilisateur choisit un dossier racine (ex: D:\\OverLoad ou ~/Téléchargements/OverLoad)
et des règles : par type, extension, date.

Aucune suppression ni déplacement sans demande : l'organisateur propose un
chemin de destination, l'appelant décide de déplacer/copier.
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from overload.core.errors import OverloadError
from overload.downloads.files import sanitize_filename
from overload.library.models import MediaEntry, MediaType


@dataclass
class OrganizerConfig:
    """Configuration persistée (serialisable JSON)."""

    enabled: bool = True
    base_directory: str = ""  # vide = dossier de téléchargement choisi par l'utilisateur
    # Sous-dossiers par type de média — l'utilisateur peut les renommer librement.
    folders: dict[str, str] = field(
        default_factory=lambda: {
            MediaType.VIDEO.value: "Vidéos",
            MediaType.AUDIO.value: "Musiques",
            MediaType.IMAGE.value: "Images",
            MediaType.OTHER.value: "Autres",
        }
    )
    # Modèle de sous-dossier par date : "" = pas de sous-dossier, sinon strftime ex: "%Y/%m" ou "%Y-%m"
    date_template: str = "%Y/%m"
    # Surcharges par extension (ex: ".mp3" -> "Musiques/Albums")
    extension_overrides: dict[str, str] = field(default_factory=dict)
    # Ajouter l'année/mois depuis la date du fichier (mtime)
    use_mtime: bool = True

    def folder_for(self, media_type: MediaType | str) -> str:
        key = media_type.value if isinstance(media_type, MediaType) else str(media_type)
        return self.folders.get(key, self.folders.get(MediaType.OTHER.value, "Autres"))

    def to_dict(self) -> dict:
        return {
            "enabled": self.enabled,
            "base_directory": self.base_directory,
            "folders": dict(self.folders),
            "date_template": self.date_template,
            "extension_overrides": dict(self.extension_overrides),
            "use_mtime": self.use_mtime,
        }

    @classmethod
    def from_dict(cls, data: dict) -> OrganizerConfig:
        return cls(
            enabled=data.get("enabled", True),
            base_directory=data.get("base_directory", ""),
            folders=data.get("folders", cls().folders),
            date_template=data.get("date_template", "%Y/%m"),
            extension_overrides=data.get("extension_overrides", {}),
            use_mtime=data.get("use_mtime", True),
        )


def classify_entry(entry: MediaEntry, config: OrganizerConfig) -> Path:
    """Retourne le chemin relatif (sous dossier) où ranger l'entrée.

    Exemple : "Vidéos/2024/10" ou "Musiques".
    """
    ext = entry.extension.lower()
    if ext in config.extension_overrides:
        base = Path(config.extension_overrides[ext])
    else:
        base = Path(config.folder_for(entry.media_type))

    if config.date_template:
        dt = datetime.fromtimestamp(entry.mtime) if config.use_mtime else datetime.now()
        try:
            date_part = dt.strftime(config.date_template)
        except Exception:
            date_part = ""
        if date_part:
            base = base / date_part

    return base


def destination_for(
    entry: MediaEntry | Path,
    config: OrganizerConfig,
    *,
    root: Path | None = None,
    preserve_filename: bool = True,
) -> Path:
    """Chemin complet de destination pour un fichier à organiser.

    - ``entry`` peut être une MediaEntry ou un Path déjà existant.
    - ``root`` surcharge ``config.base_directory``.
    - Ne touche pas au disque : juste du calcul de chemin.
    """
    if isinstance(entry, Path):
        from overload.library.scanner import scan_file

        scanned = scan_file(entry)
        if scanned is None:
            # Fichier ignoré par le scanner (ex: .part) — on classe en "Autres"
            scanned = MediaEntry(
                path=entry.resolve(),
                filename=entry.name,
                media_type=MediaType.OTHER,
                extension=entry.suffix.lower(),
                size=entry.stat().st_size if entry.exists() else 0,
                mtime=entry.stat().st_mtime if entry.exists() else datetime.now().timestamp(),
            )
        entry = scanned

    base_root = Path(root) if root is not None else (Path(config.base_directory) if config.base_directory else Path.cwd())
    relative = classify_entry(entry, config)
    safe_name = sanitize_filename(entry.filename)
    return base_root / relative / safe_name


def ensure_unique_destination(path: Path) -> Path:
    """Si la destination existe déjà, ajoute (2), (3)… sans jamais écraser."""
    if not path.exists():
        return path
    stem = path.stem
    suffix = path.suffix
    parent = path.parent
    counter = 2
    while True:
        candidate = parent / f"{stem} ({counter}){suffix}"
        if not candidate.exists():
            return candidate
        counter += 1
        if counter > 10_000:
            raise OverloadError(
                "Impossible de choisir un nom libre dans le dossier de classement.",
                "trop de fichiers portent le même nom.",
            )


def organize_file(
    source: Path,
    config: OrganizerConfig,
    *,
    root: Path | None = None,
    move: bool = True,
) -> Path:
    """Classe un fichier existant selon les règles et le déplace/copie.

    Retourne le nouveau chemin.
    Lève OverloadError si la source n'existe pas.
    """
    source = Path(source)
    if not source.is_file():
        raise OverloadError(
            "Fichier introuvable pour le classement.",
            f"« {source} » n'existe pas.",
            "Vérifiez que le téléchargement est terminé.",
        )

    # Construire une entrée temporaire pour classer
    from overload.library.scanner import scan_file

    entry = scan_file(source)
    if entry is None:
        entry = MediaEntry(
            path=source.resolve(),
            filename=source.name,
            media_type=MediaType.OTHER,
            extension=source.suffix.lower(),
            size=source.stat().st_size,
            mtime=source.stat().st_mtime,
        )

    dest = destination_for(entry, config, root=root)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest = ensure_unique_destination(dest)

    if move:
        shutil.move(str(source), str(dest))
    else:
        shutil.copy2(str(source), str(dest))
    return dest


def preview_organize(entries: list[MediaEntry], config: OrganizerConfig, root: Path) -> list[tuple[MediaEntry, Path]]:
    """Pour l'aperçu dans les paramètres : où irait chaque fichier ?"""
    return [(e, destination_for(e, config, root=root)) for e in entries]
