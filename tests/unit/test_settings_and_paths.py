import json
import os

from overload.core.formatting import format_bytes, format_duration, format_speed
from overload.core.paths import PORTABLE_DIR_NAME, data_dir, settings_file
from overload.core.settings import Settings, load_settings, save_settings


def test_settings_roundtrip(tmp_path):
    path = tmp_path / "settings.json"
    save_settings(path, Settings(download_dir=str(tmp_path / "dl"), max_parallel=3, theme="dark"))
    loaded = load_settings(path)
    assert loaded.max_parallel == 3 and loaded.theme == "dark"
    assert loaded.download_dir == str(tmp_path / "dl")


def test_missing_settings_gives_defaults(tmp_path):
    assert load_settings(tmp_path / "absent.json").max_parallel == 2


def test_corrupt_settings_are_kept_as_backup(tmp_path):
    path = tmp_path / "settings.json"
    path.write_text("{ pas du json", encoding="utf-8")
    loaded = load_settings(path)
    assert loaded == Settings()
    backups = list(tmp_path.glob("settings.corrupt-*.json"))
    assert len(backups) == 1
    assert not path.exists()


def test_values_are_sanitized(tmp_path):
    path = tmp_path / "settings.json"
    path.write_text(
        json.dumps({"max_parallel": 99, "theme": "neon", "last_section": "x", "extra": 1}),
        encoding="utf-8",
    )
    loaded = load_settings(path)
    assert loaded.max_parallel == 4
    assert loaded.theme == "system"
    assert loaded.last_section == "home"


def test_non_object_json_is_treated_as_corrupt(tmp_path):
    path = tmp_path / "settings.json"
    path.write_text("[1, 2]", encoding="utf-8")
    assert load_settings(path) == Settings()
    assert list(tmp_path.glob("settings.corrupt-*.json"))


def test_data_dir_override_and_portable_mode(tmp_path, monkeypatch):
    monkeypatch.setenv("OVERLOAD_DATA_DIR", str(tmp_path / "custom"))
    assert data_dir() == tmp_path / "custom"
    monkeypatch.delenv("OVERLOAD_DATA_DIR")
    # Mode portable : le dossier OverLoad-data à côté de l'exécutable est utilisé.
    from overload.core import paths

    monkeypatch.setattr(paths, "app_root", lambda: tmp_path)
    (tmp_path / PORTABLE_DIR_NAME).mkdir()
    assert data_dir() == tmp_path / PORTABLE_DIR_NAME
    assert settings_file() == tmp_path / PORTABLE_DIR_NAME / "settings.json"
    assert os.path.isdir(tmp_path / PORTABLE_DIR_NAME)


def test_user_data_never_under_temp_for_default_mode(tmp_path, monkeypatch):
    monkeypatch.delenv("OVERLOAD_DATA_DIR", raising=False)
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "local"))
    from overload.core import paths

    monkeypatch.setattr(paths, "app_root", lambda: tmp_path / "nowhere")
    assert data_dir() == tmp_path / "local" / "OverLoad"


def test_formatting():
    assert format_bytes(None) == "—"
    assert format_bytes(0) == "0 o"
    assert format_bytes(1536) == "1,5 Ko"
    assert format_speed(0) == "—"
    assert format_speed(2 * 1024 * 1024) == "2,0 Mo/s"
    assert format_duration(None) == "—"
    assert format_duration(75) == "1 min 15 s"
    assert format_duration(3725) == "1 h 02 min"
