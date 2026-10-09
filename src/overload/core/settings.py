"""Réglages persistants.

Un fichier illisible n'est jamais écrasé : il est renommé en « .corrupt-…json »
puis les valeurs par défaut sont utilisées.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import asdict, dataclass, field, fields
from datetime import datetime
from pathlib import Path

from overload.core.paths import default_download_dir

log = logging.getLogger(__name__)

THEMES = ("system", "light", "dark")
SECTIONS = ("home", "downloads", "settings", "help")


@dataclass
class Settings:
    download_dir: str = field(default_factory=lambda: str(default_download_dir()))
    max_parallel: int = 2
    theme: str = "system"
    last_section: str = "home"

    def sanitized(self) -> Settings:
        """Ramène chaque valeur dans son domaine autorisé."""
        return Settings(
            download_dir=str(self.download_dir).strip() or str(default_download_dir()),
            max_parallel=min(4, max(1, int(self.max_parallel))),
            theme=self.theme if self.theme in THEMES else "system",
            last_section=self.last_section if self.last_section in SECTIONS else "home",
        )


def load_settings(path: Path) -> Settings:
    if not path.exists():
        return Settings()
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            raise ValueError("le fichier ne contient pas un objet JSON")
        known = {f.name for f in fields(Settings)}
        values = {k: v for k, v in raw.items() if k in known}
        return Settings(**values).sanitized()
    except (ValueError, TypeError, OSError) as exc:
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        backup = path.with_name(f"settings.corrupt-{stamp}.json")
        try:
            os.replace(path, backup)
            log.warning("Réglages illisibles (%s) ; sauvegardés dans %s", exc, backup)
        except OSError:
            log.warning("Réglages illisibles (%s) et sauvegarde impossible", exc)
        return Settings()


def save_settings(path: Path, settings: Settings) -> None:
    """Écriture atomique : un fichier temporaire puis remplacement."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(
        json.dumps(asdict(settings.sanitized()), ensure_ascii=False, indent=2), encoding="utf-8"
    )
    os.replace(tmp, path)
