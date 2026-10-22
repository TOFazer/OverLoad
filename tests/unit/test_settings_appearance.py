from overload.settings.store import SettingsStore
from overload.ui.theme import ACCENTS, build_stylesheet, palette


def test_appearance_defaults_and_persistence(tmp_path):
    store = SettingsStore(tmp_path / "settings.json")
    prefs = store.get()
    assert prefs.accent == "violet"
    assert prefs.ui_scale == "normal"

    store.update(accent="blue", ui_scale="large")
    reloaded = SettingsStore(tmp_path / "settings.json").get()
    assert reloaded.accent == "blue"
    assert reloaded.ui_scale == "large"


def test_invalid_appearance_values_fall_back(tmp_path):
    path = tmp_path / "settings.json"
    path.write_text('{"accent": "neon", "ui_scale": "geante"}', encoding="utf-8")
    prefs = SettingsStore(path).get()
    assert prefs.accent == "violet"
    assert prefs.ui_scale == "normal"


def test_palette_uses_requested_accent_and_theme():
    dark = palette("dark", "violet")
    assert dark.canvas == "#111318"
    assert dark.surface == "#1B1E27"
    assert dark.accent == ACCENTS["violet"].dark
    light = palette("light", "blue")
    assert light.theme == "light"
    assert light.accent == ACCENTS["blue"].light


def test_stylesheet_scales_with_ui_size():
    normal = build_stylesheet("dark", "violet", "normal")
    large = build_stylesheet("dark", "violet", "large")
    assert "#111318" in normal
    assert normal != large
    assert "font-size: 15px" in large
