"""Préférences persistantes (settings.json versionné)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from overload.core.paths import settings_path
from overload.library.organizer import OrganizerConfig

SCHEMA_VERSION = 1

DEFAULTS: dict[str, Any] = {
    "schema_version": SCHEMA_VERSION,
    "language": "fr",
    "theme": "system",  # light / dark / system
    "download_dir": "",
    "organizer": OrganizerConfig().to_dict(),
    "library": {
        "show_thumbnails": True,
        "items_per_page": 100,
    },
}


class SettingsStore:
    def __init__(self, path: Path | None = None) -> None:
        self.path = Path(path) if path else settings_path()
        self._data: dict[str, Any] = {}
        self.load()

    def load(self) -> dict[str, Any]:
        if self.path.exists():
            try:
                self._data = json.loads(self.path.read_text(encoding="utf-8"))
            except Exception:
                self._data = dict(DEFAULTS)
        else:
            self._data = dict(DEFAULTS)
        # Migration douce : compléter les clés manquantes
        for k, v in DEFAULTS.items():
            if k not in self._data:
                self._data[k] = v
        return self._data

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self._data, indent=2, ensure_ascii=False), encoding="utf-8")

    def get(self, key: str, default: Any = None) -> Any:
        return self._data.get(key, default)

    def set(self, key: str, value: Any) -> None:
        self._data[key] = value
        self.save()

    def organizer_config(self) -> OrganizerConfig:
        return OrganizerConfig.from_dict(self._data.get("organizer", {}))

    def set_organizer_config(self, cfg: OrganizerConfig) -> None:
        self._data["organizer"] = cfg.to_dict()
        self.save()

    def download_dir(self) -> Path | None:
        d = self._data.get("download_dir")
        if d:
            return Path(d)
        return None

    def set_download_dir(self, path: Path) -> None:
        self._data["download_dir"] = str(path)
        self.save()
