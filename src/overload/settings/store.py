"""Stockage atomique et versionné des préférences utilisateur (`settings.json`)."""

from __future__ import annotations

import json
import os
import threading
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

from overload.core.paths import default_downloads_dir
from overload.downloads.duplicates import DuplicatePolicy

SETTINGS_SCHEMA_VERSION = 3

# « forest » (OverX Forest) est l'accent par défaut depuis la v1.3 ; les autres
# accents restent choisisables dans Paramètres → Apparence.
ACCENTS = ("forest", "violet", "blue", "cyan", "emerald", "amber", "rose")
DEFAULT_ACCENT = "forest"
UI_SCALES = ("compact", "normal", "large")


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
    accent: str = DEFAULT_ACCENT
    ui_scale: str = "normal"
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
            "accent": self.accent,
            "ui_scale": self.ui_scale,
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
        accent = str(raw.get("accent", DEFAULT_ACCENT))
        if accent not in ACCENTS:
            accent = DEFAULT_ACCENT
        # Migration unique (schéma < 3) : « violet » était l'ancien accent par
        # défaut, il devient « forest ». Un violet choisi après la migration
        # (schéma 3) est conservé tel quel.
        raw_schema = raw.get("schema_version")
        stored_schema = raw_schema if isinstance(raw_schema, int) else 1
        if stored_schema < SETTINGS_SCHEMA_VERSION and accent == "violet":
            accent = DEFAULT_ACCENT
        ui_scale = str(raw.get("ui_scale", "normal"))
        if ui_scale not in UI_SCALES:
            ui_scale = "normal"

        return AppPreferences(
            destination_dir=str(raw.get("destination_dir") or default_dest),
            max_concurrent=max(1, min(16, int(raw.get("max_concurrent", 3)))),
            speed_limit_bps=limit,
            auto_retry=bool(raw.get("auto_retry", True)),
            max_retries=max(0, min(20, int(raw.get("max_retries", 3)))),
            duplicate_policy=policy_raw,
            theme=theme,
            accent=accent,
            ui_scale=ui_scale,
            schema_version=SETTINGS_SCHEMA_VERSION,
        )

    def _save_locked(self, prefs: AppPreferences) -> None:
        tmp = self._path.with_suffix(".json.tmp")
        payload = json.dumps(prefs.to_dict(), indent=2, ensure_ascii=False)
        tmp.write_text(payload, encoding="utf-8")
        os.replace(tmp, self._path)
