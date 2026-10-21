"""Point d'entrée unique de l'espace Créateurs : projets, profils, préférences."""

from __future__ import annotations

import json
import os
import threading
from pathlib import Path
from typing import Any

from overload.core.paths import default_data_dir
from overload.creators.profiles import ProfileLibrary
from overload.creators.store import CreatorProjectsStore

PREFERENCES_DEFAULTS: dict[str, Any] = {
    "rename_template": "{projet}_{type}_{date}_{numero:03}",
    "last_profile_id": "universel",
}


class CreatorsWorkspace:
    """Regroupe les magasins persistants de l'espace Créateurs sous `data_dir/creators`."""

    def __init__(self, data_dir: Path | str | None = None) -> None:
        base = Path(data_dir) if data_dir is not None else default_data_dir()
        creators_dir = base / "creators"
        creators_dir.mkdir(parents=True, exist_ok=True)
        self.directory = creators_dir
        self.projects = CreatorProjectsStore(creators_dir / "projects.json")
        self.profiles = ProfileLibrary(creators_dir / "profiles.json")
        self._prefs_path = creators_dir / "preferences.json"
        self._prefs_lock = threading.RLock()
        self._prefs = self._load_preferences()

    def preferences(self) -> dict[str, Any]:
        with self._prefs_lock:
            return dict(self._prefs)

    def update_preferences(self, **changes: Any) -> dict[str, Any]:
        with self._prefs_lock:
            self._prefs = {**self._prefs, **changes}
            self._save_preferences_locked()
            return dict(self._prefs)

    def _load_preferences(self) -> dict[str, Any]:
        merged = dict(PREFERENCES_DEFAULTS)
        if self._prefs_path.is_file():
            try:
                raw = json.loads(self._prefs_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                raw = None
            if isinstance(raw, dict):
                for key in PREFERENCES_DEFAULTS:
                    if key in raw:
                        merged[key] = raw[key]
        return merged

    def _save_preferences_locked(self) -> None:
        tmp = self._prefs_path.with_suffix(".json.tmp")
        tmp.write_text(
            json.dumps(self._prefs, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        os.replace(tmp, self._prefs_path)
