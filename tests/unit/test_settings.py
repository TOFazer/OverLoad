
from overload.library.organizer import OrganizerConfig
from overload.settings.store import SettingsStore


def test_settings_defaults(tmp_path):
    s = SettingsStore(tmp_path / "settings.json")
    assert s.get("language") == "fr"
    assert s.get("theme") == "system"


def test_settings_persist(tmp_path):
    s = SettingsStore(tmp_path / "settings.json")
    s.set("theme", "dark")
    s2 = SettingsStore(tmp_path / "settings.json")
    assert s2.get("theme") == "dark"


def test_organizer_config_roundtrip(tmp_path):
    s = SettingsStore(tmp_path / "settings.json")
    cfg = OrganizerConfig(base_directory=str(tmp_path), date_template="%Y-%m", folders={"video": "Vids", "audio": "Musics", "image": "Pics", "other": "Other"})
    s.set_organizer_config(cfg)
    loaded = s.organizer_config()
    assert loaded.base_directory == str(tmp_path)
    assert loaded.folders["video"] == "Vids"
    assert loaded.date_template == "%Y-%m"
