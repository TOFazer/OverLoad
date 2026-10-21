
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
from overload.settings.store import SettingsStore


def test_settings_store_persists_atomically_and_reloads(tmp_path):
    cfg_path = tmp_path / "settings.json"
    store = SettingsStore(cfg_path)
    initial = store.get()
    assert initial.max_concurrent == 3
    assert initial.theme == "dark"

    store.update(
        max_concurrent=6,
        speed_limit_bps=1024 * 1024,
        theme="light",
        duplicate_policy="skip",
    )

    reloaded = SettingsStore(cfg_path).get()
    assert reloaded.max_concurrent == 6
    assert reloaded.speed_limit_bps == 1024 * 1024
    assert reloaded.theme == "light"
    assert reloaded.duplicate_policy == "skip"
