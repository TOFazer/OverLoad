"""Préférences persistantes (settings.json versionné)."""
"""Stockage atomique et versionné des préférences utilisateur (`settings.json`)."""

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
import os
import threading
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

from overload.core.paths import default_downloads_dir
from overload.downloads.duplicates import DuplicatePolicy

SETTINGS_SCHEMA_VERSION = 1


@dataclass(frozen=True)
class AppPreferences:
    """Préférences persistantes de l'application OverLoad."""

    destination_dir: str
    max_concurrent: int = 3
    speed_limit_bps: int | None = None
    auto_retry: bool = True
    max_retries: int = 3
    duplicate_policy: str = DuplicatePolicy.ASK.value
    theme: str = "dark"
    schema_version: int = SETTINGS_SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "destination_dir": self.destination_dir,
            "max_concurrent": self.max_concurrent,
            "speed_limit_bps": self.speed_limit_bps,
            "auto_retry": self.auto_retry,
            "max_retries": self.max_retries,
            "duplicate_policy": self.duplicate_policy,
            "theme": self.theme,
        }


class SettingsStore:
    """Gestionnaire thread-safe de lecture/écriture atomique pour `settings.json`."""

    def __init__(self, path: Path | str) -> None:
        self._path = Path(path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._prefs = self._load_or_default()

    @property
    def path(self) -> Path:
        return self._path

    def get(self) -> AppPreferences:
        with self._lock:
            return self._prefs

    def update(self, **changes: Any) -> AppPreferences:
        with self._lock:
            updated = replace(self._prefs, **changes)
            self._save_locked(updated)
            self._prefs = updated
            return updated

    def _load_or_default(self) -> AppPreferences:
        default_dest = str(default_downloads_dir())
        if not self._path.is_file():
            prefs = AppPreferences(destination_dir=default_dest)
            self._save_locked(prefs)
            return prefs

        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return AppPreferences(destination_dir=default_dest)

        if not isinstance(raw, dict):
            return AppPreferences(destination_dir=default_dest)

        raw_limit = raw.get("speed_limit_bps")
        limit = int(raw_limit) if isinstance(raw_limit, int | float) and raw_limit > 0 else None
        policy_raw = str(raw.get("duplicate_policy", DuplicatePolicy.ASK.value))
        if policy_raw not in {p.value for p in DuplicatePolicy}:
            policy_raw = DuplicatePolicy.ASK.value
        theme = "light" if raw.get("theme") == "light" else "dark"

        return AppPreferences(
            destination_dir=str(raw.get("destination_dir") or default_dest),
            max_concurrent=max(1, min(16, int(raw.get("max_concurrent", 3)))),
            speed_limit_bps=limit,
            auto_retry=bool(raw.get("auto_retry", True)),
            max_retries=max(0, min(20, int(raw.get("max_retries", 3)))),
            duplicate_policy=policy_raw,
            theme=theme,
            schema_version=SETTINGS_SCHEMA_VERSION,
        )

    def _save_locked(self, prefs: AppPreferences) -> None:
        tmp = self._path.with_suffix(".json.tmp")
        payload = json.dumps(prefs.to_dict(), indent=2, ensure_ascii=False)
        tmp.write_text(payload, encoding="utf-8")
        os.replace(tmp, self._path)
