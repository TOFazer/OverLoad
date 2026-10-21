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
